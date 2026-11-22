# Giảm dữ liệu trả về bằng source filtering và kích thước trang

Một truy vấn Elasticsearch có thể tìm đúng document nhưng vẫn trả về nhiều dữ liệu hơn ứng dụng cần. Ví dụ màn hình danh sách sản phẩm chỉ hiển thị tên, giá và danh mục, trong khi mỗi document còn chứa mô tả dài, thông tin nhà cung cấp, lịch sử thay đổi và các trường nội bộ. Nếu trả toàn bộ `_source` cho hàng trăm kết quả, response lớn hơn cần thiết, tăng chi phí truyền mạng, deserialize và giữ object trong bộ nhớ.

Có hai cách kiểm soát lượng dữ liệu trả về:

- **Source filtering** chọn các field trong `_source` được gửi về client bằng `_source.includes` và `_source.excludes`.
- **Page size** giới hạn số hit Elasticsearch trả về trong một search request bằng `size`, thường được Spring Data thiết lập qua `Pageable`.

Hai cơ chế giải quyết hai chiều khác nhau: source filtering giảm số field trên mỗi hit; page size giảm số hit trong mỗi response. Kết hợp đúng cả hai giúp response gọn hơn và giới hạn bộ nhớ, nhưng không thay thế việc tối ưu query, mapping, sort hoặc aggregation.

## 1. Vì sao cần giới hạn dữ liệu trả về?

Giả sử document sản phẩm có cấu trúc:

~~~json
{
  "productId": "P-1001",
  "name": "Wireless Keyboard",
  "category": "ACCESSORIES",
  "price": 1299000,
  "description": "A long product description ...",
  "supplier": {
    "name": "Example Supplier",
    "contact": {
      "email": "private@example.com",
      "phone": "+84..."
    }
  },
  "internalNotes": "Internal purchasing notes ...",
  "changeHistory": [
    {
      "changedBy": "admin-01",
      "changedAt": "2026-11-13T08:00:00Z"
    }
  ]
}
~~~

Màn hình danh sách chỉ cần:

- productId
- name
- category
- price

Nếu không chỉ định source filter, Elasticsearch thường trả toàn bộ source của từng hit. Khi page size là 100, response có thể chứa 100 bản sao của các phần mô tả, thông tin supplier và change history dù UI không sử dụng chúng.

Tác động thường thấy:

- Response JSON lớn hơn.
- Tốn băng thông giữa Elasticsearch và ứng dụng.
- Client phải parse và deserialize nhiều field.
- Entity giữ nhiều dữ liệu không cần thiết.
- Downstream API hoặc serializer có thể tiếp tục sao chép dữ liệu lớn.
- Thông tin nội bộ có thể vô tình đi sâu vào tầng xử lý hoặc response nếu mapping không được kiểm soát.

Source filtering và page size là hai giới hạn đơn giản, có thể áp dụng ngay ở search request.

## 2. Source filtering là gì?

Elasticsearch lưu nội dung document trong trường metadata `_source` (nếu index được cấu hình lưu source). Source filtering cho phép chọn field nào trong source sẽ xuất hiện trong kết quả search.

Ví dụ chỉ lấy tên và giá:

~~~http
GET /products/_search
{
  "_source": [
    "name",
    "price"
  ],
  "query": {
    "term": {
      "status": "PUBLISHED"
    }
  }
}
~~~

Kết quả mỗi hit chỉ chứa phần source được chọn:

~~~json
{
  "_index": "products",
  "_id": "P-1001",
  "_source": {
    "name": "Wireless Keyboard",
    "price": 1299000
  }
}
~~~

Document gốc trong index vẫn có thể chứa các field khác. Source filtering chỉ quyết định phần source được trả trong response search.

Có thể biểu diễn includes và excludes tường minh:

~~~json
{
  "_source": {
    "includes": [
      "name",
      "price",
      "category"
    ],
    "excludes": [
      "internalNotes",
      "supplier.contact.*"
    ]
  },
  "query": {
    "match_all": {}
  }
}
~~~

Ý nghĩa:

- `includes`: chỉ định các field được phép xuất hiện trong source trả về.
- `excludes`: loại các field không cần trả.
- Có thể dùng wildcard cho tên field và đường dẫn lồng nhau.
- Nếu không chỉ định includes, source được xem là bao gồm mọi field trừ các field bị exclude.

Khi có cả includes và excludes, hãy thiết kế include set rõ ràng và dùng excludes cho các nhánh cần loại trừ. Tránh dựa vào những quy tắc chồng chéo khó đọc.

## 3. Includes và excludes cho field lồng nhau

Source filtering hỗ trợ đường dẫn field lồng nhau:

~~~json
{
  "_source": {
    "includes": [
      "name",
      "price",
      "supplier.name"
    ],
    "excludes": [
      "supplier.contact",
      "changeHistory"
    ]
  },
  "query": {
    "match_all": {}
  }
}
~~~

Có thể dùng wildcard:

~~~json
{
  "_source": {
    "includes": [
      "name",
      "attributes.*"
    ],
    "excludes": [
      "attributes.internal*"
    ]
  }
}
~~~

Ví dụ nếu source có:

~~~json
{
  "name": "Wireless Keyboard",
  "attributes": {
    "color": "Black",
    "layout": "US",
    "internalSupplierCode": "SUP-SECRET"
  }
}
~~~

Response có thể giữ các thuộc tính được include và bỏ nhánh bị exclude.

Nên dùng đường dẫn cụ thể thay vì wildcard rộng nếu dữ liệu có các nhánh nhạy cảm hoặc phát triển theo thời gian. Một field mới được thêm vào dưới nhánh wildcard có thể tự động xuất hiện trong response sau này.

## 4. Phân biệt source filtering với query filtering

Hai khái niệm có tên gần giống nhưng mục đích hoàn toàn khác nhau:

| Cơ chế | Tác dụng | Thay đổi tập document khớp? |
|---|---|---|
| Query/filter | Chọn document nào được tìm thấy | Có |
| Source filtering | Chọn field nào trong mỗi document được trả | Không |
| Page size | Giới hạn số hit trả trong request | Giới hạn số hit response |
| Sort | Quy định thứ tự hit | Không tự loại document |

Ví dụ query lọc sản phẩm đang xuất bản và source filter chỉ lấy ba field:

~~~json
{
  "_source": {
    "includes": [
      "productId",
      "name",
      "price"
    ]
  },
  "query": {
    "term": {
      "status": "PUBLISHED"
    }
  },
  "size": 25
}
~~~

Query vẫn tìm các document có `status = PUBLISHED`. Source filtering không khiến Elasticsearch bỏ qua document có trạng thái khác; việc đó do query thực hiện.

Ngược lại, source filter loại field `status` khỏi response không có nghĩa điều kiện query không được áp dụng. Một field có thể được dùng để filter hoặc sort mà không cần xuất hiện trong `_source` trả về.

## 5. Dùng FetchSourceFilter trong Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp `FetchSourceFilter` để cấu hình source includes và excludes.

Ví dụ chỉ trả tên, giá và danh mục:

~~~java
import org.springframework.data.elasticsearch.core.query.FetchSourceFilter;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

String[] includes = {
        "productId",
        "name",
        "category",
        "price"
};

String[] excludes = {
        "internalNotes",
        "supplier.contact",
        "changeHistory"
};

NativeQuery query = NativeQuery.builder()
        .withQuery(elasticsearchQuery)
        .withSourceFilter(
                new FetchSourceFilter(includes, excludes)
        )
        .build();
~~~

Các thành phần:

- Mảng `includes` liệt kê field cần trả.
- Mảng `excludes` liệt kê field cần loại.
- `FetchSourceFilter` chuyển cấu hình này thành source filter cho request.
- `withSourceFilter(...)` gắn filter vào `NativeQuery`.

Khi dùng includes, chỉ những field được chọn mới được mong đợi trong source. Khi dùng excludes, các field bị loại không xuất hiện trong source trả về.

Nếu muốn chỉ loại một vài field nhưng vẫn giữ các field còn lại, có thể để includes rỗng:

~~~java
FetchSourceFilter sourceFilter = new FetchSourceFilter(
        new String[] {},
        new String[] {
                "internalNotes",
                "supplier.contact",
                "changeHistory"
        }
);
~~~

Cần dùng đúng import của Spring Data Elasticsearch: `org.springframework.data.elasticsearch.core.query.FetchSourceFilter`. Không nhầm nó với các lớp source filter của Elasticsearch Java API Client.

## 6. Kết hợp source filtering và Pageable

Page size giới hạn số hit Elasticsearch trả về trong một request. Trong Spring Data Elasticsearch, có thể thiết lập qua `PageRequest` và `withPageable(...)`.

Ví dụ lấy 50 sản phẩm đầu tiên và chỉ trả các field cần thiết:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.FetchSourceFilter;

NativeQuery query = NativeQuery.builder()
        .withQuery(elasticsearchQuery)
        .withSourceFilter(
                new FetchSourceFilter(
                        new String[] {
                                "productId",
                                "name",
                                "category",
                                "price"
                        },
                        new String[] {
                                "internalNotes",
                                "changeHistory"
                        }
                )
        )
        .withPageable(PageRequest.of(0, 50))
        .build();
~~~

Trong ví dụ:

- `PageRequest.of(0, 50)`: trang đầu, tối đa 50 hit.
- `FetchSourceFilter`: giới hạn field của mỗi hit.
- `withQuery(...)`: giữ điều kiện tìm kiếm nghiệp vụ.

Có thể hình dung kích thước response phụ thuộc cả hai yếu tố:

~~~text
Số hit tối đa trong response  = page size
Số field trong mỗi hit        = source filter
~~~

Nếu mỗi document có source lớn, chỉ giảm page size có thể chưa đủ. Nếu mỗi document nhỏ nhưng lấy hàng chục nghìn hit, chỉ source filtering cũng chưa đủ.

## 7. Tạo query có page size theo yêu cầu API

Không nên dùng trực tiếp page size do client gửi lên mà không giới hạn. Một API có thể chuẩn hóa page và size:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

private Pageable createPageable(
        int requestedPage,
        int requestedSize
) {
    int page = Math.max(requestedPage, 0);

    int defaultSize = 25;
    int maxSize = 200;

    int size = requestedSize <= 0
            ? defaultSize
            : Math.min(requestedSize, maxSize);

    return PageRequest.of(
            page,
            size,
            Sort.by(
                    Sort.Order.asc("name"),
                    Sort.Order.asc("productId")
            )
    );
}
~~~

Các quy tắc:

- Page index bắt đầu từ 0.
- Size phải lớn hơn 0.
- Size không vượt giới hạn service cho phép.
- Sort nên ổn định, có tie-breaker duy nhất.
- Không để client tự chọn tùy ý field sort nếu điều đó có thể gây truy vấn tốn kém hoặc truy cập field ngoài ý muốn.

Sau đó:

~~~java
NativeQuery query = NativeQuery.builder()
        .withQuery(elasticsearchQuery)
        .withSourceFilter(sourceFilter)
        .withPageable(createPageable(page, size))
        .build();
~~~

Giới hạn service nên dựa trên kích thước document, latency, heap và yêu cầu UI. Không có page size tối ưu cho mọi loại index.

## 8. Đọc kết quả bằng ElasticsearchOperations

Với query đã có source filter và page size, có thể thực thi qua `ElasticsearchOperations`:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;

SearchHits<ProductDocument> searchHits =
        operations.search(
                query,
                ProductDocument.class,
                IndexCoordinates.of("products")
        );
~~~

`SearchHits<T>` chứa các hit được trả về trong request. Có thể đọc từng hit:

~~~java
searchHits.getSearchHits().forEach(hit -> {
    ProductDocument product = hit.getContent();

    System.out.println(product.getName());
    System.out.println(product.getPrice());
});
~~~

Hoặc ánh xạ sang danh sách:

~~~java
List<ProductDocument> products =
        searchHits.getSearchHits().stream()
                .map(SearchHit::getContent)
                .toList();
~~~

Source filtering tác động lên source được deserialize. Những property không được trả về sẽ không có dữ liệu từ response; với field object thông thường chúng có thể nhận giá trị null hoặc default theo cách constructor/property mapping được triển khai.

Không nên gọi method yêu cầu một field đã bị source filter loại bỏ rồi giả định nó vẫn có giá trị.

## 9. Dùng projection/DTO nhỏ cho màn hình tìm kiếm

Một cách rõ ràng là tạo kiểu dữ liệu chỉ chứa các field cần cho màn hình danh sách:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductSearchView {

    @Id
    private String id;

    private String productId;

    private String name;

    private String category;

    @Field(type = FieldType.Double)
    private Double price;

    // Constructor, getters and setters
}
~~~

Search bằng kiểu kết quả này:

~~~java
SearchHits<ProductSearchView> hits =
        operations.search(
                query,
                ProductSearchView.class,
                IndexCoordinates.of("products")
        );
~~~

Ưu điểm:

- Kiểu trả về thể hiện rõ dữ liệu UI cần.
- Service không vô tình phụ thuộc vào các field nội bộ.
- Dễ kiểm soát response API.
- Có thể kết hợp source filter để giảm payload trên mạng và phần deserialize.

Lưu ý: DTO không tự làm source filtering. Nếu không thêm source filter, Elasticsearch vẫn có thể trả toàn bộ source; converter chỉ ánh xạ các field DTO biết đến. Muốn giảm dữ liệu truyền qua mạng, vẫn cần cấu hình source filter ở query.

Nếu DTO có `@Id`, giá trị ID có thể được lấy từ metadata `_id` của hit. `_id` không phải field thông thường trong `_source`; không cần include một field source tên `_id` trừ khi ứng dụng thực sự lưu field đó trong source.

## 10. Những field nào nên giữ trong response?

Chọn field theo mục đích của endpoint.

Ví dụ:

| Use case | Field có thể cần |
|---|---|
| Danh sách sản phẩm | productId, name, thumbnail, price |
| Chi tiết sản phẩm | name, description, attributes, images, price |
| Gợi ý autocomplete | name, productId |
| Báo cáo theo danh mục | Có thể chỉ cần aggregation, không cần source hit |
| Kiểm tra trạng thái | productId, status, updatedAt |
| Export dữ liệu | Chỉ các cột nằm trong file export |

Không có danh sách field cố định cho mọi ứng dụng. Mỗi endpoint nên xác định một response contract cụ thể.

Đặc biệt, đừng trả toàn bộ object persistence chỉ vì UI có thể cần thêm field trong tương lai. Khi contract thay đổi, cập nhật source filter và DTO một cách có chủ đích.

## 11. Source filtering có giảm chi phí query không?

Source filtering chủ yếu giảm phần dữ liệu source được trả về trong search response. Nó có thể giảm:

- Kích thước JSON response.
- Network transfer.
- Chi phí parse/deserialize ở client.
- Số field được giữ trong object phía ứng dụng.
- Khả năng vô tình chuyển tiếp dữ liệu không cần thiết.

Nhưng source filtering **không tự giảm**:

- Số document Elasticsearch phải tìm.
- Chi phí query/filter.
- Chi phí scoring.
- Chi phí sort.
- Số bucket aggregation cần tính.
- Số shard được truy vấn.
- Dung lượng source đã lưu trên index.

Elasticsearch vẫn phải thực hiện search và lấy source để áp dụng source filter trong fetch phase. Vì vậy, source filtering là tối ưu response/fetch payload, không phải thay thế query optimization hoặc mapping/index design.

Nếu truy vấn cần lọc theo `status`, hãy index field phù hợp và dùng query/filter. Việc exclude `status` khỏi source trả về không làm query rẻ hơn theo cách thay đổi tập dữ liệu.

## 12. Source filtering và doc values/fields API

Không phải lúc nào ứng dụng cũng cần source JSON. Nếu chỉ cần các giá trị của field đã được mapping phù hợp, Elasticsearch còn có Fields API hoặc `docvalue_fields` cho một số kiểu field.

Phân biệt:

| Cách lấy dữ liệu | Nguồn | Khi phù hợp |
|---|---|---|
| `_source.includes/excludes` | JSON source đã lưu | Cần một phần document gốc, bao gồm cấu trúc object |
| `fields` | Giá trị field theo mapping/format | Cần giá trị field đã được Elasticsearch xử lý theo mapping |
| `docvalue_fields` | Doc values của field hỗ trợ | Cần đọc giá trị column-oriented, thường cho sort/aggregation-friendly fields |
| `stored_fields` | Field được cấu hình store riêng | Chỉ khi mapping và use case chủ động dùng stored field |

Ví dụ `docvalue_fields`:

~~~json
{
  "query": {
    "match_all": {}
  },
  "docvalue_fields": [
    "price",
    "createdAt"
  ],
  "_source": false
}
~~~

Không phải mọi field đều có doc values. Field `text` thường không có doc values mặc định, trong khi keyword, numeric và date thường hỗ trợ. Cần xác nhận mapping và định dạng response.

`stored_fields` cũng không tự động hoạt động cho mọi field; field phải được mapping với `store: true`. Đừng bật store cho tất cả field chỉ để thay source filtering.

Với phần lớn API trả document, source filtering là lựa chọn đơn giản. Chỉ dùng fields/doc values khi ứng dụng thực sự cần semantics và format của các API đó.

## 13. Khi _source bị tắt

Source filtering dựa trên `_source`. Nếu index được tạo với `_source.enabled: false`, ứng dụng không thể yêu cầu một phần source theo cách thông thường.

Ví dụ mapping:

~~~json
{
  "mappings": {
    "_source": {
      "enabled": false
    },
    "properties": {
      "productId": {
        "type": "keyword"
      },
      "price": {
        "type": "double"
      }
    }
  }
}
~~~

Khi source bị tắt:

- Không thể lấy lại JSON source gốc qua search hit.
- Source filtering không có source để lọc.
- Cần dựa vào stored fields hoặc fields/doc values phù hợp.
- Các chức năng cần reindex/update dựa trên source có thể bị ảnh hưởng.

Không tắt source chỉ để giảm response payload. Thông thường giữ source và chọn field trả về theo từng query linh hoạt hơn. Việc tắt source là quyết định mapping/lưu trữ có ảnh hưởng rộng, cần cân nhắc khả năng update, reindex, debugging và recovery.

## 14. Giới hạn page size và from/size

`PageRequest.of(page, size)` thường được chuyển thành offset pagination với `from` và `size`.

Công thức:

\[
from = page \times size
\]

Ví dụ `page = 20`, `size = 50` sẽ bắt đầu từ offset 1.000.

Elasticsearch có giới hạn `index.max_result_window`; giá trị mặc định phổ biến là 10.000. Request có `from + size` vượt giới hạn có thể bị từ chối.

Tăng page size hoặc `max_result_window` không phải cách phù hợp để đọc toàn bộ index lớn. Deep pagination bằng offset khiến Elasticsearch phải xử lý các kết quả trước vị trí cần trả về.

Dùng `from/size` cho phân trang giao diện ở độ sâu vừa phải. Với export hoặc đọc hàng trăm nghìn document, cân nhắc `search_after` kết hợp Point in Time (PIT).

## 15. Sort ổn định khi phân trang

Để trang kế tiếp không lặp hoặc bỏ sót kết quả do các hit có cùng sort value, hãy dùng thứ tự sort ổn định.

Ví dụ:

~~~java
Pageable pageable = PageRequest.of(
        page,
        size,
        Sort.by(
                Sort.Order.asc("createdAt"),
                Sort.Order.asc("productId")
        )
);
~~~

`productId` nên là field keyword có giá trị duy nhất trong tập dữ liệu đang phân trang.

Nếu chỉ sort theo `createdAt`, nhiều document có cùng timestamp có thể không có thứ tự tương đối ổn định giữa các request. Tie-breaker giúp tạo thứ tự xác định hơn.

Sort ổn định không tạo snapshot dữ liệu. Nếu document được thêm/xóa giữa các request offset, vị trí trang vẫn có thể dịch chuyển. Nếu cần cùng một snapshot qua nhiều trang, dùng PIT với search_after.

## 16. Source filtering khi dùng search_after

Source filter không phụ thuộc cơ chế pagination. Có thể giữ cùng filter khi dùng `search_after`:

~~~java
NativeQuery firstPage = NativeQuery.builder()
        .withQuery(elasticsearchQuery)
        .withSourceFilter(sourceFilter)
        .withSort(byCreatedAt, byProductId)
        .withPageable(PageRequest.of(0, 500))
        .build();
~~~

Sau khi nhận trang đầu, lấy sort values của hit cuối:

~~~java
List<SearchHit<ProductSearchView>> hits =
        searchHits.getSearchHits();

List<Object> cursor = hits
        .get(hits.size() - 1)
        .getSortValues();
~~~

Query tiếp theo giữ nguyên source filter, query và sort:

~~~java
NativeQuery nextPage = NativeQuery.builder()
        .withQuery(elasticsearchQuery)
        .withSourceFilter(sourceFilter)
        .withSort(byCreatedAt, byProductId)
        .withPageable(PageRequest.of(0, 500))
        .withSearchAfter(cursor)
        .build();
~~~

Source filter giảm field trả về của từng hit. `search_after` xác định vị trí tiếp tục. Hai chức năng độc lập và có thể kết hợp.

Khi dùng PIT, gắn PIT vào từng request theo API của phiên bản client, cập nhật PIT ID mới nhất nếu response trả về và đóng PIT khi hoàn tất.

## 17. Chỉ lấy aggregation khi không cần document source

Nếu endpoint chỉ hiển thị thống kê, không cần trả danh sách document. Có thể yêu cầu `size = 0` và chỉ lấy aggregation.

Ví dụ:

~~~java
NativeQuery aggregationQuery = NativeQuery.builder()
        .withQuery(elasticsearchQuery)
        .withAggregation("by_category", categoryAggregation)
        .withMaxResults(0)
        .build();
~~~

Khi không trả hits:

- Không cần source filter cho document hits.
- Response tập trung vào aggregation results.
- Không phải deserialize danh sách entity không được sử dụng.

Đây là tối ưu phù hợp cho dashboard, số lượng theo danh mục hoặc metric. Nếu query có aggregation và đồng thời cần một vài document mẫu, hãy đặt page size nhỏ theo nhu cầu.

## 18. Đo kích thước response và hiệu quả

Không nên chỉ giả định source filter luôn cải thiện hiệu năng đáng kể. Hãy đo trên dữ liệu có kích thước gần production.

Một phép so sánh có thể thực hiện:

1. Chạy query không có source filter với cùng query, sort và page size.
2. Ghi nhận response bytes và thời gian.
3. Chạy lại với source includes/excludes.
4. So sánh response bytes, latency, CPU và heap allocation phía client.
5. Giữ nguyên điều kiện query để so sánh công bằng.
6. Lặp lại với page size nhỏ/lớn để thấy ảnh hưởng riêng của số hit.

Các chỉ số nên quan sát:

| Chỉ số | Điều cần biết |
|---|---|
| Response bytes | Payload mạng giảm bao nhiêu |
| Elasticsearch took | Thời gian xử lý request phía Elasticsearch |
| Client latency | Tổng thời gian từ ứng dụng |
| Deserialize time | Chi phí chuyển JSON thành object |
| Heap allocation | Bộ nhớ dùng khi xử lý kết quả |
| Hit count | Số document trả về |
| Page count | Số request cần để đọc hết tập dữ liệu |
| Error/timeout rate | Ảnh hưởng khi page size quá lớn |

`hits.total` là tổng số document phù hợp query theo semantics tracking, còn số hit thực tế trong `hits.hits` bị giới hạn bởi page size. Đừng dùng số hit trong response để suy ra tổng số document của index.

## 19. Những lỗi thường gặp

### Chỉ giảm page size nhưng vẫn trả toàn bộ source

Response vẫn lớn nếu mỗi document có nhiều field hoặc mảng lồng nhau. Thêm source filter theo nhu cầu endpoint.

### Chỉ dùng source filter nhưng page size quá lớn

Mỗi hit nhỏ hơn nhưng hàng chục nghìn hit vẫn tạo response lớn và tốn bộ nhớ. Giới hạn cả page size.

### Nghĩ source filtering giảm chi phí query

Source filtering không thay thế query/filter, sort hoặc aggregation optimization. Nó chủ yếu giảm dữ liệu source được trả.

### Exclude field nhạy cảm nhưng lại include wildcard rộng

Wildcard có thể đưa field mới vào response khi schema thay đổi. Ưu tiên allowlist includes cho endpoint công khai.

### Nghĩ DTO tự giảm payload mạng

DTO chỉ giới hạn field được ánh xạ ở client. Nếu request không có source filter, toàn bộ source vẫn có thể được truyền qua mạng.

### Gọi getter của field đã bị lọc

Field bị loại khỏi source có thể null hoặc mang default value. Chỉ truy cập những field query đã yêu cầu.

### Nhầm _id với field trong _source

Document ID là metadata của hit. Không cần include một field source tên _id để nhận document ID.

### Tăng max_result_window để export toàn index

Offset sâu tốn tài nguyên. Dùng search_after và PIT cho đọc sâu.

### Sort theo field không duy nhất

Nhiều document có cùng sort value có thể làm thứ tự trang thiếu ổn định. Thêm tie-breaker duy nhất.

### Tắt _source chỉ để response nhỏ

Tắt source ảnh hưởng update/reindex và khả năng lấy document gốc. Dùng source filtering theo request khi cần chọn field.

### Quên giới hạn page size từ API client

Client có thể gửi size rất lớn gây tải lên cluster và heap. Chuẩn hóa page/size ở server.

## 20. Quy trình triển khai

Khi tối ưu search response bằng source filtering và page size:

1. Xác định endpoint cần field nào trong mỗi hit.
2. Ưu tiên allowlist includes cho response có cấu trúc rõ ràng.
3. Dùng excludes để bỏ các nhánh lớn hoặc nội bộ khi phù hợp.
4. Tạo `FetchSourceFilter` và gắn vào `NativeQuery`.
5. Chọn page size mặc định và giới hạn tối đa ở service.
6. Dùng `Pageable` để điều khiển trang và sort.
7. Dùng DTO/projection nhỏ để thể hiện response contract.
8. Không gọi logic phụ thuộc vào field đã bị lọc.
9. Với export sâu, dùng search_after và PIT thay cho offset lớn.
10. Với báo cáo chỉ cần aggregation, đặt max results bằng 0.
11. Đo response bytes, latency, deserialize và heap allocation.
12. Kiểm thử trường hợp field lồng nhau, wildcard, source rỗng và mapping thay đổi.
13. Kiểm tra quyền truy cập và không để field nhạy cảm xuất hiện trong response.
14. Theo dõi page size, page count, timeout và lỗi giới hạn result window.

## Tài liệu tham khảo

- [Elasticsearch — Retrieve selected fields from a search](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-fields.html)
- [Elasticsearch — The _source field](https://www.elastic.co/guide/en/elasticsearch/reference/current/mapping-source-field.html)
- [Elasticsearch — Search API](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-search.html)
- [Elasticsearch — Paginate search results](https://www.elastic.co/guide/en/elasticsearch/reference/current/paginate-search-results.html)
- [Elasticsearch — Point in time API](https://www.elastic.co/guide/en/elasticsearch/reference/current/point-in-time-api.html)
- [Spring Data Elasticsearch — NativeQuery API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/client/elc/NativeQuery.html)
- [Spring Data Elasticsearch — FetchSourceFilter API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/query/FetchSourceFilter.html)
- [Spring Data Elasticsearch — Pageable search operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)

## Kết luận

Source filtering chọn field được trả về trong mỗi hit bằng includes/excludes; page size giới hạn số hit trong một search request. Trong Spring Data Elasticsearch, kết hợp `FetchSourceFilter` với `NativeQuery.withPageable(PageRequest.of(...))` để giảm payload theo cả chiều rộng và số lượng. Dùng DTO nhỏ để thể hiện response contract, nhưng vẫn cấu hình source filter nếu muốn giảm dữ liệu truyền qua mạng. Source filtering không làm query rẻ hơn ở mọi giai đoạn và không thay thế tối ưu mapping, filter hay sort. Với phân trang sâu, dùng `search_after` cùng sort ổn định và PIT; với truy vấn chỉ cần thống kê, không trả hits.
