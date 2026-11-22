# `save` và hành vi tạo mới hoặc thay thế tài liệu theo ID

Trong Spring Data Elasticsearch, `save()` là thao tác ghi một document vào Elasticsearch. Kết quả phụ thuộc chủ yếu vào định danh (`_id`) của document: nếu ID chưa tồn tại trong index, Elasticsearch tạo document mới; nếu ID đã tồn tại, thao tác index thay thế nội dung document cũ bằng nội dung mới. Vì vậy, `save()` phù hợp để ghi một trạng thái document đầy đủ và nhất quán theo ID.

Điểm cần hiểu rõ là `save()` không hoạt động như một phép merge từng thuộc tính giống cách nhiều người hình dung về `save()` trong ORM quan hệ. Khi cần chỉ thay đổi một vài trường và giữ nguyên các trường còn lại, hãy dùng thao tác update một phần. Khi cần ngăn một bản ghi cũ ghi đè lên bản ghi mới hơn, hãy thiết kế cơ chế optimistic locking hoặc kiểm soát phiên bản.

## 1. `save()` trong Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp repository để thao tác với document. Một repository thường kế thừa `ElasticsearchRepository<T, ID>`:

```java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {
}
```

Document class khai báo index và ID:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Long)
    private Long priceMinorUnits;

    @Field(type = FieldType.Boolean)
    private Boolean available;

    // Constructors, getters and setters
}
```

Lưu document:

```java
ProductDocument product = new ProductDocument();
product.setId("p-1001");
product.setName("Máy pha cà phê");
product.setSku("COFFEE-001");
product.setPriceMinorUnits(3250000L);
product.setAvailable(true);

ProductDocument saved = productRepository.save(product);
```

`@Id` ánh xạ thuộc tính Java thành Elasticsearch document ID (`_id`). Với `@Document(indexName = "products")`, thao tác save nhắm tới index `products` hoặc tên logic được cấu hình tại đó, chẳng hạn một alias.

`save()` trả về entity đã lưu. Hãy giữ kết quả trả về, đặc biệt khi ID được Elasticsearch tạo tự động hoặc khi entity có thông tin phiên bản được cập nhật trong quá trình ghi.

## 2. Quy tắc tạo mới hoặc thay thế theo ID

Ở tầng Elasticsearch, thao tác index document theo ID có hai kết quả cơ bản:

| Trạng thái trước khi ghi | Kết quả của `save()`/index theo ID |
|---|---|
| Chưa có document với ID đó trong index đích | Tạo document mới |
| Đã có document với ID đó trong index đích | Thay thế source của document bằng source mới |

Ví dụ, index đang có document:

```json
{
  "_id": "p-1001",
  "name": "Máy pha cà phê",
  "sku": "COFFEE-001",
  "priceMinorUnits": 3250000,
  "available": true,
  "description": "Máy pha tại nhà"
}
```

Sau đó ứng dụng lưu document cùng ID nhưng source mới:

```json
{
  "name": "Máy pha cà phê phiên bản mới",
  "sku": "COFFEE-001",
  "priceMinorUnits": 3490000,
  "available": true
}
```

Document sau khi ghi sẽ có source mới. Trường `description` không có trong source mới sẽ không còn trong document được thay thế. Đây là lý do cần gửi một đối tượng đầy đủ nếu dùng `save()` để thay thế.

### ID được xét trong phạm vi index

ID không phải khóa duy nhất trên toàn cluster. Cùng một `_id` có thể xuất hiện ở hai index vật lý khác nhau. Ví dụ `p-1001` trong `products-v1` và `p-1001` trong `products-v2` là hai document riêng. Nếu ứng dụng ghi qua alias hoặc nhiều index, cần hiểu alias đang định tuyến tới index nào để tránh đọc/ghi nhầm thế hệ.

## 3. ID được khai báo hay được tạo tự động?

Có hai cách phổ biến để xác định document ID.

### Dùng ID ổn định do ứng dụng cung cấp

Với dữ liệu nghiệp vụ có định danh ổn định, nên gán ID trước khi gọi `save()`:

```java
ProductDocument product = new ProductDocument();
product.setId("product-1001");
product.setName("Bàn phím cơ");

ProductDocument saved = productRepository.save(product);
```

Lần lưu tiếp theo với cùng ID và cùng index sẽ nhắm tới cùng document. Điều này hữu ích khi đồng bộ dữ liệu từ cơ sở dữ liệu nghiệp vụ, chạy lại message hoặc thực hiện retry sau lỗi mạng.

### Để Elasticsearch tạo ID

Nếu ID để trống, Elasticsearch có thể sinh ID cho document khi thực hiện thao tác index. Spring Data trả về entity đã lưu với định danh được gán theo cơ chế của phiên bản đang dùng.

```java
ProductDocument product = new ProductDocument();
product.setName("Chuột không dây");

ProductDocument saved = productRepository.save(product);
String generatedId = saved.getId();
```

Khi dùng ID tự sinh, hãy giữ entity đã lưu hoặc lấy ID từ kết quả trả về. Nếu mỗi lần gọi `save()` đều gửi một object mới với ID rỗng, Elasticsearch có thể tạo document mới với ID khác, dẫn đến bản ghi trùng về mặt nghiệp vụ.

### Chọn chiến lược ID

| Tình huống | Chiến lược thường phù hợp |
|---|---|
| Đồng bộ một sản phẩm có ID trong database | Dùng ID sản phẩm ổn định |
| Ghi lại cùng một sự kiện khi consumer retry | Dùng event ID ổn định để thao tác idempotent |
| Ghi log độc lập, mỗi lần ghi là một sự kiện mới | Có thể dùng ID tự sinh |
| Chỉ có mã nghiệp vụ dạng chuỗi | Dùng chuỗi làm `_id` nếu duy nhất trong index |
| ID tăng tuần tự hoặc số lớn | Xem xét định dạng chuỗi để tránh giới hạn số nguyên ở các tầng API |

ID ổn định giúp thao tác ghi có tính lặp an toàn hơn: ghi lại cùng trạng thái vào cùng ID không tạo thêm document mới. Tuy nhiên, nó không tự giải quyết việc hai bản cập nhật đến sai thứ tự; cần version hoặc cơ chế kiểm soát đồng thời nếu điều đó quan trọng.

## 4. `save()` khác với partial update

Đây là khác biệt quan trọng nhất khi làm việc với CRUD.

### `save()` ghi một document đầy đủ

`save()` tương ứng với hành vi index document theo ID. Nếu document đã tồn tại, source cũ được thay bằng source mới. Các trường không xuất hiện trong source mới sẽ không được giữ lại như một phép merge.

### Partial update chỉ thay đổi trường được gửi

Elasticsearch Update API cho phép gửi phần `doc` chứa các trường cần thay đổi. Những trường không có trong phần cập nhật được giữ nguyên.

Ví dụ document hiện tại có `name`, `price`, `available` và `description`. Chỉ muốn cập nhật giá:

```http
POST /products/_update/p-1001
Content-Type: application/json

{
  "doc": {
    "priceMinorUnits": 3490000
  }
}
```

Sau update, các trường `name`, `available` và `description` vẫn giữ nguyên. Đây là hành vi khác với việc gọi `save()` bằng một object chỉ chứa ID và giá mới.

### So sánh `save()` và update

| Tiêu chí | `save()` / index theo ID | Partial update |
|---|---|---|
| Dữ liệu gửi lên | Document source đầy đủ | Các trường hoặc script cần thay đổi |
| ID chưa tồn tại | Tạo document mới | Thường trả về not found nếu không bật upsert |
| ID đã tồn tại | Thay source cũ bằng source mới | Chỉ thay đổi phần được chỉ định |
| Trường không gửi | Không còn trong source mới | Được giữ nguyên |
| Phù hợp | Đồng bộ trạng thái document hoàn chỉnh | Cập nhật một vài thuộc tính |
| Rủi ro chính | Ghi object thiếu trường làm mất dữ liệu cũ | Cập nhật cạnh tranh hoặc script không đúng |

Trong Spring Data Elasticsearch, có thể dùng `ElasticsearchOperations` cùng `UpdateQuery` cho partial update. Cấu trúc builder và kiểu `Document` cụ thể cần theo phiên bản Spring Data của dự án. Nếu cần minh họa hành vi ở cấp server, Update REST API ở trên thể hiện trực tiếp ngữ nghĩa của thao tác.

## 5. Upsert: cập nhật nếu có, tạo mới nếu chưa có

Upsert là kết hợp update và insert. Nếu document tồn tại, Elasticsearch áp dụng phần cập nhật; nếu chưa tồn tại, nó tạo document từ nội dung được chỉ định.

Ví dụ dùng Update API với `doc_as_upsert`:

```http
POST /products/_update/p-1001
Content-Type: application/json

{
  "doc": {
    "priceMinorUnits": 3490000,
    "available": true
  },
  "doc_as_upsert": true
}
```

Nếu `p-1001` tồn tại, các trường được gửi sẽ được cập nhật. Nếu chưa tồn tại, phần `doc` được dùng để tạo document mới. Cần bảo đảm payload upsert có đủ những trường bắt buộc để document mới hợp lệ.

Phân biệt:

- `save()` theo ID đã thực hiện hành vi tạo mới hoặc thay thế source.
- Partial update không có upsert chỉ cập nhật document đã tồn tại.
- Partial update có `doc_as_upsert` cập nhật nếu có, tạo mới nếu chưa có.

Upsert không đồng nghĩa với kiểm tra đầy đủ quy tắc nghiệp vụ. Ví dụ, nếu một document mới cần `sku`, `name` và `currency`, chỉ gửi `price` trong `doc_as_upsert` có thể tạo document thiếu dữ liệu cần thiết.

## 6. Phân biệt index, create và update ở Elasticsearch

Elasticsearch cung cấp các API có ngữ nghĩa khác nhau:

| API | Hành vi khi ID chưa có | Hành vi khi ID đã có |
|---|---|---|
| Index API (`PUT /index/_doc/id`) | Tạo document | Thay thế source |
| Create API (`PUT /index/_create/id`) | Tạo document | Trả lỗi xung đột `409` |
| Update API (`POST /index/_update/id`) | Not found, trừ khi bật upsert | Cập nhật một phần hoặc chạy script |

Ví dụ Create API:

```http
PUT /products/_create/p-1001
Content-Type: application/json

{
  "name": "Máy pha cà phê",
  "sku": "COFFEE-001",
  "priceMinorUnits": 3250000
}
```

Nếu ID `p-1001` đã tồn tại, request trả lỗi xung đột thay vì ghi đè. Đây là lựa chọn phù hợp khi ứng dụng muốn bảo đảm chỉ tạo mới và xem việc ID đã tồn tại là lỗi nghiệp vụ.

Repository `save()` được dùng cho hành vi lưu document theo ID và có thể thay thế source cũ. Nếu cần ngữ nghĩa chỉ tạo mới, hãy dùng API create tương ứng hoặc một thao tác được thiết kế rõ ràng thay vì giả định `save()` sẽ từ chối ID trùng.

## 7. `saveAll()` và ghi hàng loạt

`saveAll()` lưu nhiều entity:

```java
List<ProductDocument> products = List.of(
    productA,
    productB,
    productC
);

Iterable<ProductDocument> savedProducts =
    productRepository.saveAll(products);
```

Spring Data Elasticsearch thường tối ưu thao tác hàng loạt bằng Bulk API thay vì gửi một request riêng cho từng document. Bulk API gom nhiều action trong một request, giảm overhead mạng và tăng throughput.

### Mỗi phần tử trong bulk vẫn có ID và ngữ nghĩa riêng

Khi `saveAll()` nhận document có ID đã tồn tại, action index của document đó thay thế source theo ID. Khi ID chưa tồn tại, document được tạo. Vì vậy, batch có thể chứa cả thao tác tạo mới lẫn thay thế.

### Bulk không phải một transaction nguyên tử

Một bulk request có thể có một số item thành công và một số item thất bại. Không nên giả định toàn bộ batch được commit hoặc rollback như một transaction cơ sở dữ liệu quan hệ. Ứng dụng cần xem lỗi từng item, ghi log/metrics, retry có chọn lọc và bảo đảm ID ổn định để retry không tạo bản ghi trùng.

Với batch lớn:

- Chia thành batch có kích thước phù hợp với payload và năng lực cluster.
- Tránh gửi một request khổng lồ làm tăng áp lực heap, mạng và thời gian xử lý.
- Theo dõi số item thành công/thất bại thay vì chỉ kiểm tra request HTTP tổng thể.
- Retry lỗi tạm thời có backoff; không retry vô hạn lỗi mapping hoặc dữ liệu không hợp lệ.
- Giữ ID ổn định để một lần gửi lại không tạo document mới ngoài ý muốn.

## 8. ID và tính idempotent khi đồng bộ dữ liệu

Idempotency có nghĩa việc xử lý lặp lại cùng một thao tác không làm thay đổi kết quả cuối cùng ngoài ý muốn. Trong pipeline đồng bộ database sang Elasticsearch, ID ổn định là một phần quan trọng để đạt đặc tính này.

Ví dụ, event `product-updated-1001-v7` được gửi lại ba lần. Nếu consumer luôn ghi vào document ID `p-1001`, các lần ghi cùng payload có thể hội tụ về cùng một source thay vì tạo ba document mới.

Tuy nhiên, giả sử hai event đến sai thứ tự:

```text
Version 8: price = 200
Version 7: price = 180
```

Nếu version 8 được ghi trước và version 7 được ghi sau, một lệnh `save()` không có kiểm soát version có thể làm trạng thái cũ ghi đè trạng thái mới. ID ổn định chỉ ngăn tạo bản ghi trùng; nó không tự bảo vệ thứ tự cập nhật.

Để xử lý, có thể:

- Gắn version nghiệp vụ vào event và chỉ chấp nhận phiên bản mới hơn.
- Dùng optimistic concurrency control của Elasticsearch/Spring Data.
- Đảm bảo thứ tự xử lý theo key sản phẩm trong message partition.
- Đọc trạng thái hiện tại từ nguồn có thẩm quyền trước khi dựng document, kết hợp version để tránh ghi cũ.

## 9. Optimistic locking với `@Version`

Khi nhiều tiến trình có thể cùng sửa một document, optimistic locking giúp phát hiện một tiến trình đang ghi dựa trên trạng thái cũ. Spring Data Elasticsearch hỗ trợ thuộc tính version thông qua annotation `@Version`.

Ví dụ:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.elasticsearch.annotations.Document;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Version
    private Long version;

    private String name;
    private Long priceMinorUnits;

    // Constructors, getters and setters
}
```

Khi entity được đọc, thông tin version được giữ cùng entity. Khi lưu một entity có version, Spring Data có thể gửi điều kiện concurrency để Elasticsearch phát hiện document đã bị thay đổi kể từ lần đọc. Nếu một tiến trình khác ghi trước, thao tác ghi cũ có thể thất bại với lỗi optimistic locking thay vì âm thầm ghi đè.

Luồng khái niệm:

```text
Client A đọc document version 4
Client B đọc document version 4

Client A lưu thay đổi -> thành công, version mới
Client B lưu dựa trên version 4 -> xung đột
```

Khi gặp xung đột, ứng dụng cần đọc lại document mới nhất, áp dụng lại thay đổi theo quy tắc nghiệp vụ rồi thử lại nếu phù hợp. Không nên retry mù bằng cách gửi lại entity cũ vì nó vẫn chứa trạng thái lỗi thời.

Chi tiết cơ chế version và loại exception có thể khác theo phiên bản Spring Data Elasticsearch/client. Hãy dùng API versioning được phiên bản đang chạy hỗ trợ và kiểm thử trường hợp hai writer cập nhật đồng thời.

## 10. `save()` có làm document xuất hiện ngay trong tìm kiếm không?

Elasticsearch sử dụng refresh để làm các thay đổi đã index có thể được nhìn thấy trong search. Sau khi `save()` trả về thành công, document đã được ghi nhận bởi Elasticsearch nhưng chưa chắc lập tức xuất hiện trong một truy vấn search ngay sau đó.

Điều này là khác biệt giữa:

- Đọc document theo ID qua Get API, có thể nhìn thấy thao tác ghi đã hoàn tất.
- Tìm kiếm bằng Search API, phụ thuộc chu kỳ refresh của index.

Nếu ứng dụng cần search nhìn thấy document ngay sau thao tác ghi, có thể cấu hình refresh policy phù hợp, chẳng hạn `wait_for` trong các API hỗ trợ. Tuy nhiên, không nên ép refresh sau mọi request vì refresh quá thường xuyên làm giảm hiệu năng indexing.

Với luồng thông thường, hãy thiết kế để chấp nhận một độ trễ tìm kiếm ngắn theo refresh interval của index. Nếu cần read-after-write mạnh cho một màn hình, cân nhắc lấy kết quả trực tiếp từ response hoặc đọc theo ID thay vì lập tức chạy search.

## 11. Ví dụ service lưu và cập nhật sản phẩm

Ví dụ service dùng repository để lưu trạng thái document đầy đủ:

```java
import org.springframework.stereotype.Service;

@Service
public class ProductIndexService {

    private final ProductRepository repository;

    public ProductIndexService(ProductRepository repository) {
        this.repository = repository;
    }

    public ProductDocument saveFull(ProductDocument document) {
        return repository.save(document);
    }

    public ProductDocument find(String id) {
        return repository.findById(id).orElse(null);
    }
}
```

Trong service thực tế, nên phân biệt rõ hai use case:

- **Đồng bộ toàn bộ sản phẩm:** đọc trạng thái có thẩm quyền từ database nghiệp vụ, dựng đầy đủ `ProductDocument`, sau đó gọi `save()` bằng ID ổn định.
- **Cập nhật một trường tìm kiếm:** dùng partial update nếu thực sự muốn giữ nguyên mọi trường khác; hoặc đọc document đầy đủ, sửa rồi save nếu logic cần kiểm soát toàn bộ trạng thái và có concurrency phù hợp.

Không nên nhận một request DTO chỉ có `id` và một vài trường rồi chuyển thẳng thành `ProductDocument` và gọi `save()` nếu ý định là cập nhật một phần. Cách đó có thể thay thế document bằng source thiếu dữ liệu.

## 12. Các lỗi thường gặp

### Gọi `save()` nhiều lần tạo nhiều document

Nguyên nhân thường là ID vẫn rỗng nên mỗi lần lưu Elasticsearch sinh một ID mới. Hãy dùng ID ổn định hoặc giữ lại ID từ entity được trả về.

### Ghi document mới làm mất field cũ

Nguyên nhân là `save()` thay thế toàn bộ source. Nếu chỉ muốn thay đổi một số field, dùng Update API hoặc dựng lại đầy đủ document từ nguồn dữ liệu có thẩm quyền.

### Hai tiến trình ghi đè lẫn nhau

Nguyên nhân là last-write-wins khi không có kiểm soát concurrency. Dùng version/optimistic locking hoặc bảo đảm thứ tự event theo key.

### `save()` thành công nhưng search chưa thấy document

Nguyên nhân có thể là index chưa refresh. Chờ refresh interval, dùng refresh policy phù hợp khi thật sự cần hoặc đọc theo ID.

### `saveAll()` báo lỗi dù một số document đã ghi thành công

Bulk API không nguyên tử. Cần xem chi tiết item lỗi, sửa dữ liệu/mapping hoặc retry riêng các lỗi tạm thời.

### Cùng ID nhưng đọc ra document khác

Kiểm tra index hoặc alias mà thao tác đọc và ghi đang sử dụng. ID chỉ duy nhất trong phạm vi index; alias có thể định tuyến đến index vật lý khác nhau.

## 13. Quy trình chọn thao tác ghi

Trước khi chọn API, hãy xác định ý nghĩa nghiệp vụ của thao tác:

1. Nếu ghi một trạng thái document đầy đủ và ID có thể xác định, dùng `save()`.
2. Nếu ID chưa có và nghiệp vụ yêu cầu từ chối ID trùng, dùng thao tác create-only.
3. Nếu chỉ thay đổi một vài trường và cần giữ các trường còn lại, dùng partial update.
4. Nếu cần update khi có hoặc insert khi chưa có, dùng upsert với payload tạo mới đầy đủ.
5. Nếu ghi nhiều document, cân nhắc `saveAll()`/Bulk API và xử lý lỗi theo từng item.
6. Nếu có nhiều writer, dùng version/optimistic locking hoặc cơ chế thứ tự cập nhật.
7. Nếu cần tìm kiếm thấy ngay sau ghi, đánh giá refresh policy và chi phí hiệu năng.

## 14. Kết luận

Trong Spring Data Elasticsearch, `save()` lưu document theo ID. Nếu ID chưa tồn tại trong index đích, document được tạo; nếu ID đã tồn tại, source cũ được thay thế bằng source mới. ID ổn định giúp đồng bộ và retry an toàn hơn, trong khi ID tự sinh phù hợp với bản ghi độc lập mà mỗi lần ghi là một document mới.

Hãy phân biệt `save()` với partial update và upsert. Dùng `save()` cho trạng thái đầy đủ, Update API khi chỉ thay đổi một phần, và create-only khi ID trùng phải là lỗi. Với `saveAll()`, nhớ rằng Bulk API không phải transaction nguyên tử. Khi có nhiều writer, cần optimistic locking hoặc version nghiệp vụ; khi cần search nhìn thấy ngay sau ghi, phải tính đến refresh. Hiểu đúng các ngữ nghĩa này giúp tránh mất field, tạo document trùng và ghi đè dữ liệu mới bằng trạng thái cũ.
