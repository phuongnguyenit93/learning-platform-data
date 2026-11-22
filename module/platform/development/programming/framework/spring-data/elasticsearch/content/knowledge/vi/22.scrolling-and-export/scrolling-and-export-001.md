# search_after và vị trí tiếp tục dựa trên sort values

Khi một truy vấn trả về hàng nghìn hoặc hàng triệu document, phân trang bằng offset (from và size) sẽ ngày càng tốn kém khi người dùng đi sâu vào kết quả. Elasticsearch phải tìm và bỏ qua các hit đứng trước offset, đồng thời giới hạn from + size bằng index.max_result_window theo cấu hình mặc định phổ biến.

**search_after** giải quyết việc đi tiếp trong tập kết quả bằng cách dùng các giá trị sort của hit cuối cùng ở trang trước. Thay vì nói “bỏ qua 10.000 hit đầu”, request tiếp theo nói “trả các hit đứng sau vị trí sort này”. Spring Data Elasticsearch giữ các giá trị đó trong metadata của SearchHit và cho phép truyền chúng vào query tiếp theo.

Để phân trang đúng, cần giữ nguyên query và thứ tự sort giữa các request, dùng một thứ tự sắp xếp ổn định, truyền lại sort values nguyên bản và cân nhắc **Point in Time (PIT)** nếu dữ liệu có thể thay đổi trong khi người dùng đang duyệt. Bài học này giải thích cách hoạt động của search_after, cách tích hợp với Spring Data Elasticsearch, cách thiết kế cursor và cách phân biệt nó với scroll.

## 1. Vì sao offset pagination không phù hợp với kết quả sâu?

Với from và size, request đầu có thể lấy 20 kết quả:

~~~http
POST /products/_search
{
  "from": 0,
  "size": 20,
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  }
}
~~~

Trang tiếp theo tăng offset:

~~~http
POST /products/_search
{
  "from": 20,
  "size": 20,
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  }
}
~~~

Cách này dễ hiểu và phù hợp với những trang đầu. Tuy nhiên, để lấy trang có offset lớn, Elasticsearch phải xử lý các kết quả đứng trước vị trí cần trả về trên các shard rồi phối hợp chúng tại coordinating node. Chi phí và bộ nhớ tăng theo độ sâu của trang.

Elasticsearch cũng giới hạn cửa sổ kết quả bằng index.max_result_window; mặc định thường là 10.000 cho from + size. Có thể thay đổi cấu hình index, nhưng tăng giới hạn không làm offset pagination trở nên rẻ hơn.

Ví dụ, request với from: 10000 và size: 20 không phải là một chiến lược tốt cho việc duyệt sâu liên tục. Với use case cần đi tiếp qua nhiều trang, hãy cân nhắc search_after.

### Offset và cursor khác nhau ở đâu?

| Cách phân trang | Request tiếp theo dựa trên | Đặc điểm |
|---|---|---|
| from + size | Số lượng hit cần bỏ qua | Dễ nhảy tới trang số bất kỳ, nhưng tốn kém khi offset sâu |
| search_after | Sort values của hit cuối trang trước | Đi tiếp theo vị trí sort, phù hợp phân trang sâu |
| Scroll | Search context và scroll ID | Duyệt theo batch cho tác vụ đọc/xuất dữ liệu lớn |

search_after không phải cơ chế nhảy thẳng đến trang số 500. Nó cần cursor từ trang trước. Nếu giao diện cần nút “đến trang bất kỳ”, offset hoặc một chiến lược lưu cursor theo trang có thể phù hợp hơn, nhưng phải cân nhắc chi phí và khả năng thay đổi dữ liệu.

## 2. search_after hoạt động dựa trên sort như thế nào?

Elasticsearch cần một thứ tự kết quả xác định để biết hit nào đứng sau hit cuối của trang trước. Vì vậy, search_after luôn đi cùng sort.

Giả sử sort theo giá tăng dần:

~~~http
POST /products/_search
{
  "size": 3,
  "query": {
    "match": {
      "name": "keyboard"
    }
  },
  "sort": [
    {
      "price": {
        "order": "asc"
      }
    }
  ]
}
~~~

Response có ba hit. Mỗi hit chứa một mảng sort tương ứng với thứ tự sort đã khai báo:

~~~json
{
  "hits": {
    "hits": [
      {
        "_id": "p-10",
        "_source": { "price": 49.0 },
        "sort": [49.0]
      },
      {
        "_id": "p-22",
        "_source": { "price": 59.0 },
        "sort": [59.0]
      },
      {
        "_id": "p-31",
        "_source": { "price": 69.0 },
        "sort": [69.0]
      }
    ]
  }
}
~~~

Hit cuối có sort values [69.0]. Request tiếp theo truyền chính mảng đó vào search_after:

~~~http
POST /products/_search
{
  "size": 3,
  "query": {
    "match": {
      "name": "keyboard"
    }
  },
  "sort": [
    {
      "price": {
        "order": "asc"
      }
    }
  ],
  "search_after": [69.0]
}
~~~

Elasticsearch trả về các hit có vị trí sort đứng sau [69.0]. Ứng dụng tiếp tục lấy sort values của hit cuối trong response mới để tạo cursor tiếp theo.

Luồng xử lý:

~~~text
Request trang 1
      |
      v
SearchHits trang 1
      |
      v
Lấy sort values của hit cuối
      |
      v
Gửi search_after với sort values đó
      |
      v
Request trang 2
      |
      v
Lấy sort values của hit cuối trang 2
      |
      +------> Request trang 3 ...
~~~

Giá trị search_after là vị trí tiếp tục trong thứ tự sort, không phải ID document và cũng không phải số thứ tự trang.

## 3. Vì sao sort phải ổn định và có tie-breaker?

Sort theo một field có thể tạo ra nhiều hit cùng giá trị. Ví dụ, nhiều sản phẩm có cùng giá 69.0. Nếu chỉ sort theo price, Elasticsearch không có một thứ tự duy nhất được bảo đảm giữa các document có cùng giá trị đó.

Khi dùng search_after, vị trí tiếp tục phải phân biệt được các hit. Nếu sort không đủ xác định, kết quả có thể bị lặp hoặc bỏ sót khi chuyển trang, đặc biệt khi các shard hoặc dữ liệu thay đổi.

Giải pháp là thêm một tie-breaker có giá trị duy nhất:

~~~http
POST /products/_search
{
  "size": 3,
  "query": {
    "match": {
      "name": "keyboard"
    }
  },
  "sort": [
    {
      "price": {
        "order": "asc"
      }
    },
    {
      "productId": {
        "order": "asc"
      }
    }
  ]
}
~~~

Giả sử productId là field keyword có giá trị duy nhất và hỗ trợ doc values. Sort values của hit có thể là:

~~~json
[69.0, "p-31"]
~~~

Request tiếp theo phải truyền cả hai giá trị:

~~~json
{
  "search_after": [69.0, "p-31"]
}
~~~

Không được chỉ truyền 69.0, vì cursor lúc đó không thể xác định chính xác vị trí giữa các sản phẩm có cùng giá.

### Chọn field tie-breaker

Field tie-breaker nên:

- Có giá trị duy nhất trong phạm vi tập kết quả.
- Có mapping hỗ trợ sort, thường là keyword, numeric hoặc date có doc values.
- Có giá trị ổn định trong suốt quá trình duyệt.
- Được giữ trong cùng thứ tự sort ở mọi request.

Không nên mặc định dùng _id trực tiếp làm field sort. Elasticsearch hạn chế sort và aggregation trên _id; nếu không dùng PIT, có thể copy identifier vào một field keyword riêng như productId và bật doc values để sort.

Nếu dùng PIT, Elasticsearch bổ sung _shard_doc làm tie-breaker nội bộ khi cần. Giá trị này được trả trong sort values và phải được giữ nguyên khi tạo request tiếp theo. PIT và _shard_doc sẽ được trình bày ở phần sau.

### Nhiều tiêu chí sort

Mỗi tiêu chí sort bổ sung thêm một phần tử trong mảng sort. Ví dụ:

~~~json
{
  "sort": [
    { "updatedAt": "desc" },
    { "price": "asc" },
    { "productId": "asc" }
  ]
}
~~~

Sort values của một hit sẽ có cùng thứ tự:

~~~json
[
  "2026-10-20T08:30:00Z",
  69.0,
  "p-31"
]
~~~

Cursor cần chứa đủ ba giá trị, đúng kiểu và đúng thứ tự. Nếu đổi thứ tự sort, direction, format date hoặc field sort giữa các request, cursor cũ không còn hợp lệ.

## 4. Quy trình phân trang search_after

Một luồng phân trang thông thường có các bước:

1. Chuẩn hóa filter và keyword của người dùng.
2. Tạo một query cố định cho toàn bộ phiên duyệt.
3. Khai báo thứ tự sort ổn định và tie-breaker.
4. Gửi request đầu với size mong muốn và không có search_after.
5. Nhận kết quả và lấy sort values của hit cuối.
6. Đưa sort values đó vào request tiếp theo.
7. Lặp lại cho đến khi response không còn hit.

Nếu response rỗng, không có hit cuối để tạo cursor mới. API nên báo đã hết dữ liệu hoặc không trả nextCursor.

### Chú ý: không tăng from khi dùng search_after

Khi phân trang bằng search_after, hãy giữ from ở 0 hoặc bỏ hẳn trường này. Không kết hợp cursor với offset tăng dần như from: 20, from: 40. Vị trí tiếp tục đã được xác định bởi sort values.

### Kích thước trang

size vẫn quyết định số hit tối đa của mỗi response. Ví dụ size 50 nghĩa là mỗi request lấy tối đa 50 hit sau cursor.

Không nên đặt size quá lớn chỉ để giảm số request. Page size cần cân bằng giữa:

- Kích thước document và payload.
- Độ trễ mỗi request.
- Bộ nhớ của ứng dụng.
- Số lượng request mà client có thể thực hiện.
- Giới hạn và tải của Elasticsearch cluster.

## 5. Giữ nguyên query và sort giữa các request

search_after chỉ có ý nghĩa khi request sau tiếp tục cùng một tập kết quả theo cùng thứ tự.

Các thành phần cần giữ nhất quán gồm:

- Query full-text.
- Filter nghiệp vụ.
- Sort field và sort direction.
- Missing-value behavior.
- Nested sort hoặc các tùy chọn sort khác.
- Routing và index/alias được truy vấn.
- Các tùy chọn ảnh hưởng tới tập kết quả.

Ví dụ trang đầu lọc category accessories, nhưng trang sau bỏ filter category thì cursor đang chỉ một vị trí trong tập kết quả khác. Kết quả sẽ không còn là phần tiếp theo của trang trước.

Tương tự, nếu trang đầu sort theo price asc, productId asc, trang sau đổi thành price desc, productId asc, sort values không còn đại diện cho cùng một thứ tự.

### Tạo query fingerprint cho cursor

Ở tầng ứng dụng, có thể tạo một fingerprint từ các thành phần ảnh hưởng đến tập kết quả:

- Query keyword đã chuẩn hóa.
- Filter đã chuẩn hóa.
- Index hoặc alias.
- Sort definition.
- Các tùy chọn liên quan đến mapping/query.

Fingerprint giúp server xác nhận cursor được dùng với đúng bộ điều kiện ban đầu. Không nhất thiết phải lưu toàn bộ query JSON trong token; có thể lưu ID phiên tìm kiếm phía server hoặc hash của cấu trúc đã chuẩn hóa.

## 6. Dữ liệu thay đổi trong lúc người dùng phân trang

Nếu index tiếp tục nhận document mới, cập nhật hoặc xóa document giữa hai request, cùng một query và sort vẫn có thể cho tập kết quả khác nhau.

Ví dụ:

1. Trang đầu trả các sản phẩm có giá từ 20 đến 40.
2. Một sản phẩm mới được index với giá 25.
3. Client gửi request tiếp theo dùng cursor của trang đầu.
4. Tập kết quả đã thay đổi; vị trí sort có thể khiến client gặp kết quả khác với snapshot ban đầu.

Tie-breaker giải quyết tính duy nhất của thứ tự sort, nhưng không tự tạo snapshot dữ liệu. Để giữ góc nhìn nhất quán qua nhiều request, dùng **Point in Time (PIT)** nếu phiên bản Elasticsearch và Spring Data hỗ trợ use case đó.

## 7. Kết hợp search_after với Point in Time (PIT)

PIT mở một góc nhìn ổn định của index tại một thời điểm. Các request tìm kiếm tiếp theo dùng cùng PIT để duyệt dữ liệu trong snapshot đó, kể cả khi index bên dưới tiếp tục thay đổi.

Luồng khái quát:

1. Mở PIT trên index hoặc alias cần tìm.
2. Gửi search request với PIT, query, sort và page size.
3. Lấy sort values của hit cuối.
4. Dùng PIT ID mới nhất cùng sort values trong request tiếp theo.
5. Gia hạn keep-alive khi tiếp tục duyệt, theo API hỗ trợ.
6. Đóng PIT khi người dùng kết thúc hoặc phiên hết hạn.

Ví dụ request mở đầu theo Elasticsearch REST API:

~~~http
POST /products/_pit?keep_alive=1m
~~~

Response trả về PIT ID. Search request dùng PIT:

~~~http
POST /_search
{
  "size": 50,
  "pit": {
    "id": "PIT_ID_FROM_OPEN_RESPONSE",
    "keep_alive": "1m"
  },
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  },
  "sort": [
    { "price": "asc" }
  ]
}
~~~

Khi dùng PIT, Elasticsearch bổ sung _shard_doc làm tie-breaker nếu sort chưa có tie-breaker phù hợp. Vì vậy, sort values có thể chứa thêm giá trị này. Phải truyền lại toàn bộ mảng sort values mà hit trả về, kể cả phần tử _shard_doc.

Request tiếp theo:

~~~http
POST /_search
{
  "size": 50,
  "pit": {
    "id": "LATEST_PIT_ID",
    "keep_alive": "1m"
  },
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  },
  "sort": [
    { "price": "asc" }
  ],
  "search_after": [
    69.0,
    4294967298
  ]
}
~~~

Các giá trị trên chỉ là minh họa. Trong thực tế, phải lấy PIT ID mới nhất nếu response trả ID mới và dùng sort values thật của hit cuối. Không tự tính _shard_doc.

### Quản lý vòng đời PIT

PIT giữ tài nguyên search context trên cluster. Ứng dụng nên:

- Đặt keep-alive vừa đủ cho thời gian người dùng tiếp tục thao tác.
- Gia hạn khi có request tiếp theo, theo quy tắc của API.
- Đóng PIT khi phiên duyệt hoàn tất.
- Có cơ chế hết hạn để giải phóng PIT bị bỏ quên.
- Xử lý trường hợp PIT hết hạn hoặc ID không còn hợp lệ.
- Giới hạn số phiên PIT đồng thời theo tải hệ thống.

Không mở PIT mới cho mỗi trang. Các trang thuộc cùng một phiên phân trang cần dùng cùng PIT để duy trì snapshot.

## 8. Lấy sort values từ Spring Data Elasticsearch

Khi gọi search qua ElasticsearchOperations, kết quả thường là SearchHits<T>, trong đó mỗi SearchHit<T> giữ content và metadata của hit.

SearchHit.getSortValues() trả về các giá trị sort mà Elasticsearch cung cấp:

~~~java
SearchHits<Product> hits =
    operations.search(query, Product.class);

if (!hits.getSearchHits().isEmpty()) {
    SearchHit<Product> lastHit =
        hits.getSearchHits().get(
            hits.getSearchHits().size() - 1
        );

    List<Object> nextPosition = lastHit.getSortValues();
}
~~~

Đây là nguồn chính xác để lấy vị trí tiếp tục. Không tự tạo list từ các property của entity, vì sort values có thể chứa field ẩn, tie-breaker, giá trị đã chuẩn hóa hoặc thứ tự mà Elasticsearch quyết định.

### Sort values phụ thuộc sort definition

Ví dụ query sort:

~~~json
{
  "sort": [
    { "updatedAt": "desc" },
    { "productId": "asc" }
  ]
}
~~~

getSortValues() trả các giá trị tương ứng với updatedAt rồi productId. Nếu query có PIT và Elasticsearch bổ sung _shard_doc, danh sách có thể có thêm một phần tử.

Không giả định sortValues.get(0) luôn là ID, score hay timestamp. Hãy hiểu thứ tự sort của query đang chạy và truyền lại toàn bộ list.

## 9. Dùng NativeQuery để truyền search_after

Với Spring Data Elasticsearch hiện đại, NativeQuery cho phép khai báo Query DSL, sort, pageable và search-after values. API builder có thể thay đổi theo release train và phiên bản Elasticsearch Java API Client.

Ví dụ dưới đây minh họa cấu trúc triển khai; các overload sort/query cần đối chiếu dependency thực tế:

~~~java
NativeQueryBuilder builder = NativeQuery.builder()
    .withQuery(q -> q.match(m -> m
        .field("name")
        .query("wireless keyboard")
    ))
    .withSort(SortOptions.of(s -> s.field(f -> f
        .field("price")
        .order(SortOrder.Asc)
    )))
    .withSort(SortOptions.of(s -> s.field(f -> f
        .field("productId")
        .order(SortOrder.Asc)
    )))
    .withPageable(PageRequest.of(0, 50));

if (searchAfterValues != null && !searchAfterValues.isEmpty()) {
    builder.withSearchAfter(searchAfterValues);
}

NativeQuery query = builder.build();

SearchHits<Product> hits =
    operations.search(query, Product.class);
~~~

Request đầu truyền searchAfterValues là null hoặc danh sách rỗng. Request tiếp theo dùng sort values lấy từ hit cuối của response trước.

Một helper có thể tách việc lấy cursor:

~~~java
private List<Object> nextSearchAfter(SearchHits<Product> hits) {
    List<SearchHit<Product>> page = hits.getSearchHits();

    if (page.isEmpty()) {
        return List.of();
    }

    return page.get(page.size() - 1).getSortValues();
}
~~~

Nếu dùng Pageable, giữ page number ở 0 cho các request search_after và thay đổi cursor giữa các lần gọi. Pageable lúc này chủ yếu giúp truyền page size và các thông tin paging được API hỗ trợ; không dùng page number để tăng offset.

### Không trộn sort của Pageable với sort của NativeQuery tùy tiện

Một query có thể nhận sort từ nhiều nguồn. Nếu vừa cấu hình sort trong NativeQuery vừa truyền sort khác trong Pageable, cần hiểu thứ tự hợp nhất của phiên bản Spring Data đang dùng. Tốt nhất chỉ có một nguồn định nghĩa sort cho cursor và dùng đúng thứ tự đó trong mọi request.

## 10. Thiết kế cursor cho API

Không nên bắt frontend tự tạo search_after từ các field hiển thị. Server nên trả một cursor đại diện cho vị trí tiếp tục.

Ví dụ response API:

~~~json
{
  "items": [
    {
      "id": "p-31",
      "name": "Wireless Mechanical Keyboard",
      "price": 69.0
    }
  ],
  "nextCursor": "opaque-cursor-token",
  "hasMore": true
}
~~~

Request tiếp theo:

~~~http
GET /products/search?cursor=opaque-cursor-token
~~~

Server giải mã cursor, kiểm tra tính hợp lệ rồi tạo request Elasticsearch với đúng query, sort, PIT và search_after values.

### Nội dung cursor có thể gồm những gì?

Một cursor phía server có thể lưu hoặc tham chiếu đến:

- Sort values của hit cuối trang.
- PIT ID nếu đang dùng PIT.
- Query fingerprint hoặc search session ID.
- Sort definition hoặc version của nó.
- Index/alias được tìm kiếm.
- Thời điểm hết hạn.
- Phiên bản định dạng cursor.

Có hai cách phổ biến:

**Cursor tự chứa:** token mã hóa hoặc ký dữ liệu cần thiết. Cách này giảm lưu session ở server nhưng cần kiểm soát kích thước và bảo vệ nội dung.

**Cursor tham chiếu server-side:** token ngẫu nhiên trỏ tới session lưu trong cache/database. Server giữ PIT ID, sort values và query state. Cách này dễ thu hồi và che giấu metadata Elasticsearch, nhưng cần quản lý session.

Base64 chỉ là encoding, không phải bảo mật. Nếu cursor chứa PIT ID hoặc dữ liệu nội bộ, dùng token có chữ ký hoặc mã hóa phù hợp; không tin dữ liệu cursor do client tự sửa.

### Cursor phải gắn với query ban đầu

Nếu client gửi cursor của truy vấn “keyboard” nhưng thay keyword thành “mouse”, server không nên tiếp tục dùng vị trí sort cũ. Tương tự, không cho phép thay filter hoặc sort giữa phiên duyệt mà không bắt đầu một cursor mới.

Một cách làm là lưu fingerprint của query trong cursor. Khi nhận request tiếp theo, server tính fingerprint từ tiêu chí hiện tại và so sánh. Nếu khác, từ chối cursor hoặc yêu cầu bắt đầu tìm kiếm mới.

## 11. Phân biệt search_after và scroll

Cả search_after và scroll đều hỗ trợ duyệt nhiều kết quả, nhưng phục vụ những kiểu công việc khác nhau.

| Tiêu chí | search_after | Scroll |
|---|---|---|
| Cách tiếp tục | Sort values của hit cuối | Scroll ID/search context |
| Thứ tự kết quả | Bắt buộc có sort ổn định | Có thể dùng thứ tự phù hợp với batch export |
| Use case phổ biến | Phân trang sâu, cursor API | Đọc/xuất lượng lớn theo batch |
| Snapshot ổn định | Kết hợp PIT | Scroll giữ search context trong thời gian scroll |
| Nhảy tới vị trí tùy ý | Không | Không |
| Quản lý trạng thái | Cursor và có thể PIT | Scroll ID |
| Kết thúc phiên | Hết trang hoặc đóng PIT | Clear scroll |

Với trải nghiệm tìm kiếm tương tác, search_after kết hợp PIT thường là lựa chọn phù hợp khi cần phân trang sâu và kết quả nhất quán. Với tác vụ xuất toàn bộ dữ liệu theo batch, scroll vẫn là một lựa chọn trong các use case phù hợp; PIT kết hợp search_after cũng có thể được dùng để duyệt tập dữ liệu lớn theo thứ tự.

Không nên giữ scroll context lâu chỉ để người dùng mở một trang rồi quay lại nhiều giờ sau. Search context và PIT đều có chi phí tài nguyên, cần quản lý vòng đời phiên.

## 12. Khi nào không nên dùng search_after?

search_after không phù hợp với mọi giao diện.

Không nên chọn nó nếu:

- Người dùng phải nhảy trực tiếp đến một trang số bất kỳ.
- Ứng dụng cần offset nhỏ và ổn định, ví dụ vài trang đầu.
- Sort không thể tạo ra thứ tự ổn định.
- Client không thể giữ hoặc gửi cursor giữa các request.
- Query hoặc sort thay đổi hoàn toàn sau mỗi lần chuyển trang.
- Use case cần xuất dữ liệu theo một cơ chế batch khác đã phù hợp hơn.

Với tập kết quả nhỏ, from và size đơn giản hơn. Với thao tác duyệt sâu tuần tự, search_after hiệu quả hơn offset. Với xuất dữ liệu lớn, hãy so sánh PIT + search_after và scroll theo yêu cầu về snapshot, thứ tự và vòng đời phiên.

## 13. Các lỗi thường gặp khi dùng search_after

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Kết quả bị lặp giữa hai trang | Sort không đủ ổn định hoặc cursor không lấy từ hit cuối | Thêm tie-breaker và lấy sort values của hit cuối |
| Một số hit bị bỏ qua | Chỉ truyền một phần sort values hoặc thứ tự sort thay đổi | Truyền toàn bộ list theo đúng thứ tự |
| Request tiếp theo báo lỗi sort | Kiểu giá trị cursor không khớp sort field | Giữ nguyên kiểu và giá trị server trả về |
| Trang sau có dữ liệu khác tập ban đầu | Index thay đổi giữa các request | Dùng PIT cho phiên duyệt ổn định |
| Cursor cũ trả kết quả sai | Query, filter hoặc sort đã thay đổi | Gắn cursor với query fingerprint |
| Không có next cursor dù trang có dữ liệu | Lấy sort values từ hit đầu hoặc xử lý nhầm danh sách rỗng | Lấy hit cuối và kiểm tra size |
| Cursor hoạt động với một sort nhưng hỏng với sort khác | Cấu trúc sort values khác nhau | Cursor phải mang sort definition/version |
| Vẫn gặp giới hạn offset | Tiếp tục tăng from cùng search_after | Giữ from ở 0 hoặc bỏ khỏi request |
| PIT hết hạn | Keep-alive quá ngắn hoặc session bị bỏ lâu | Xử lý expiry và bắt đầu phiên mới |
| Tốn tài nguyên do nhiều phiên mở | Không đóng PIT hoặc TTL quá dài | Đóng và giới hạn vòng đời session |

### Dùng sort values từ entity thay vì response

Một lỗi thường gặp là tự tạo cursor:

~~~java
List<Object> cursor = List.of(
    lastProduct.getPrice(),
    lastProduct.getProductId()
);
~~~

Cách này có thể tình cờ đúng khi query chỉ sort theo đúng hai property đó. Tuy nhiên, nó dễ sai khi query có format, missing-value handling, script sort, nested sort hoặc PIT tie-breaker.

Nên lấy trực tiếp:

~~~java
List<Object> cursor =
    lastHit.getSortValues();
~~~

### Không truyền đủ giá trị

Nếu sort gồm updatedAt, price và productId, cursor cần đủ ba giá trị. Nếu dùng PIT và response có thêm _shard_doc, cũng phải giữ giá trị đó. Không tự bỏ phần tử mà mình không hiểu.

## 14. Kiểm thử phân trang và cursor

Một integration test nên tạo dữ liệu có giá trị sort trùng nhau để chứng minh tie-breaker hoạt động.

Ví dụ dữ liệu:

| productId | price |
|---|---:|
| p-01 | 50 |
| p-02 | 50 |
| p-03 | 50 |
| p-04 | 70 |
| p-05 | 70 |
| p-06 | 90 |

Với page size 2 và sort price asc, productId asc, các trang kỳ vọng:

| Trang | Kết quả |
|---|---|
| 1 | p-01, p-02 |
| 2 | p-03, p-04 |
| 3 | p-05, p-06 |

Test cần xác nhận:

- Không có document xuất hiện hai lần.
- Không có document nào bị bỏ sót.
- Thứ tự giữa các hit cùng giá vẫn xác định.
- Cursor được lấy từ hit cuối mỗi response.
- Request sau giữ nguyên query và sort.
- Khi response rỗng, API không tạo cursor mới.
- Cursor không thể dùng với filter hoặc sort khác.
- PIT được đóng hoặc hết hạn theo chính sách.

Skeleton test:

~~~java
@Test
void traversesAllHitsWithSearchAfter() {
    // Index sáu sản phẩm, trong đó nhiều sản phẩm có cùng giá.
    // Tạo query sort theo price asc rồi productId asc.
    // Lấy trang đầu và ghi lại ID cùng sort values của hit cuối.
    // Gửi request tiếp theo với search_after.
    // Lặp tới khi response rỗng.
    // Xác nhận sáu ID xuất hiện đúng một lần và đúng thứ tự.
}
~~~

Đây là skeleton mô tả kịch bản. Cấu hình Elasticsearch test và API tạo query phụ thuộc phiên bản Spring Data Elasticsearch của dự án.

Với PIT, cần thêm test cho trường hợp index được cập nhật giữa hai request. Kết quả trong cùng PIT phải phản ánh snapshot đã mở; một phiên mới có thể nhìn thấy document mới. Đồng thời kiểm tra xử lý PIT hết hạn và giải phóng context.

## 15. Checklist trước khi phát hành phân trang search_after

- [ ] Query và filter được chuẩn hóa và giữ nguyên trong suốt phiên duyệt.
- [ ] Sort có thứ tự xác định và tie-breaker duy nhất.
- [ ] Mọi field sort đều hỗ trợ sort/doc values phù hợp.
- [ ] Không dựa vào _id trực tiếp làm field sort thông thường.
- [ ] Request tiếp theo truyền toàn bộ sort values của hit cuối.
- [ ] Giữ đúng kiểu dữ liệu và thứ tự sort values.
- [ ] Không tăng from khi dùng search_after.
- [ ] Page size được giới hạn.
- [ ] Cursor gắn với query, filter, sort và index/alias tương ứng.
- [ ] Cursor được ký, mã hóa hoặc tham chiếu server-side nếu cần bảo vệ.
- [ ] Dùng PIT khi cần snapshot nhất quán qua nhiều request.
- [ ] PIT ID mới nhất được giữ và keep-alive được gia hạn đúng cách.
- [ ] PIT được đóng hoặc có cơ chế hết hạn.
- [ ] Response rỗng được xử lý như hết dữ liệu.
- [ ] Integration test có dữ liệu trùng sort value và kiểm tra không lặp/bỏ sót.

search_after biến phân trang sâu thành việc tiếp tục từ một vị trí trong thứ tự sort. SearchHit.getSortValues() cung cấp vị trí đó; ứng dụng giữ nguyên các giá trị và gửi lại cùng query, sort trong request kế tiếp. Khi cần một tập kết quả ổn định giữa những lần gọi, kết hợp search_after với PIT và quản lý cursor có vòng đời rõ ràng. Cách làm này phù hợp cho cursor-based search và những luồng duyệt tuần tự có lượng kết quả lớn.

