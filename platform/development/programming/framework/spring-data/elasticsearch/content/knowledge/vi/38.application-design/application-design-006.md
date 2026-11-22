# Thiết kế API phân trang, con trỏ và giới hạn truy cập

Một API tìm kiếm cần xác định rõ người dùng có thể lấy bao nhiêu kết quả, theo thứ tự nào, và bằng cách nào tiếp tục từ vị trí đang xem. Với Spring Data Elasticsearch, lựa chọn phân trang ảnh hưởng trực tiếp đến hiệu năng cluster, tính nhất quán của kết quả và mức độ an toàn của API. Một endpoint cho phép page number rất lớn, page size không giới hạn hoặc cursor có thể sửa tùy ý sẽ tạo ra rủi ro cả về tải hệ thống lẫn truy cập dữ liệu ngoài phạm vi.

Thiết kế tốt bắt đầu từ hợp đồng API: dùng page number khi cần nhảy tới trang trong một cửa sổ nhỏ; dùng cursor khi người dùng chỉ cần đi tiếp; dùng PIT kết hợp search_after khi cần duyệt một snapshot ổn định; và dùng quy trình batch riêng cho export. Mọi lựa chọn đều cần giới hạn page size, thời gian xử lý, độ phức tạp query và phạm vi dữ liệu mà principal được phép xem.

Bài này giải thích cách thiết kế API phân trang và cursor trong ngữ cảnh Spring Data Elasticsearch, gồm response contract, offset pagination, search_after, Point in Time (PIT), cursor token an toàn, tenant/authorization binding, giới hạn truy cập, kiểm thử và vận hành.

## 1. Bắt đầu từ nhu cầu của API

Trước khi chọn kỹ thuật, xác định người dùng cần điều hướng kết quả như thế nào.

| Nhu cầu | Kiểu API thường phù hợp |
|---|---|
| Nhảy tới trang số cụ thể | Page number với from/size, có giới hạn |
| Xem vài trang đầu của danh sách | Page number |
| Nút Next hoặc Load more | Cursor pagination |
| Duyệt tập dữ liệu lớn, cần snapshot | PIT + search_after |
| Export hoặc xử lý toàn bộ kết quả | Batch job với cursor/PIT hoặc cơ chế phù hợp |
| Chỉ cần số liệu tổng hợp | Aggregation, không tải hit không cần thiết |

Không nên chọn cursor chỉ vì nó có vẻ hiện đại. Nếu giao diện cần nhảy từ trang 2 tới trang 30, page number có thể phù hợp hơn trong giới hạn nhỏ. Ngược lại, nếu người dùng chỉ cuộn liên tục qua kết quả, cursor tránh được offset lớn và không cần tính page number.

Cũng cần xác định kết quả có thể thay đổi trong lúc người dùng duyệt hay không. Danh sách cập nhật liên tục có thể cần snapshot; danh sách ít thay đổi có thể chấp nhận semantics đơn giản hơn.

## 2. Định nghĩa hợp đồng request và response

Một API page-number có thể nhận:

~~~http
GET /api/products?q=keyboard&page=0&size=20&sort=createdAt,desc
~~~

Response ví dụ:

~~~json
{
  "items": [
    {
      "id": "p-1001",
      "name": "Mechanical Keyboard"
    }
  ],
  "page": 0,
  "size": 20,
  "totalElements": 135,
  "totalPages": 7,
  "hasNext": true,
  "hasPrevious": false
}
~~~

Một API cursor có thể nhận cursor tùy chọn:

~~~http
GET /api/products?q=keyboard&limit=20
~~~

Response:

~~~json
{
  "items": [
    {
      "id": "p-1001",
      "name": "Mechanical Keyboard"
    }
  ],
  "nextCursor": "opaque-token",
  "hasNext": true
}
~~~

Request tiếp theo:

~~~http
GET /api/products?cursor=opaque-token&limit=20
~~~

Cursor nên được xem là token opaque. Client chỉ lưu và gửi lại; không cần biết bên trong có sort values, PIT ID hoặc query fingerprint.

Hợp đồng API cần nói rõ:

- Page number bắt đầu từ 0 hay 1.
- Size mặc định và tối đa.
- Những sort field được phép.
- Hướng sort mặc định.
- Cursor có thời hạn bao lâu.
- Cursor có gắn với filter và principal hay không.
- Khi cursor hết hạn hoặc không hợp lệ, API trả lỗi gì.
- Tổng số hit có chính xác hay chỉ là ước lượng.
- Dữ liệu giữa các trang có snapshot consistency hay không.

Không để client phải đoán semantics từ implementation Elasticsearch.

## 3. Giới hạn page size ở tầng API

Không nhận size tùy ý từ client rồi chuyển thẳng vào Elasticsearch. Một request size rất lớn có thể tạo response nặng, tốn heap, tăng network và kéo dài thời gian xử lý.

Ví dụ chính sách:

- Default page size: 20.
- Maximum page size: 100.
- Page number không âm.
- Chỉ chấp nhận một số sort field cho phép.
- Giới hạn độ dài từ khóa tìm kiếm.
- Giới hạn số filter và độ phức tạp query.
- Đặt timeout ở API và Elasticsearch client.

Một helper validation:

~~~java
public Pageable validatePageRequest(
        int page,
        int size,
        Sort sort) {

    int defaultSize = 20;
    int maxSize = 100;

    if (page < 0) {
        throw new InvalidPageRequestException("Page must be non-negative");
    }

    int effectiveSize = size <= 0 ? defaultSize : size;

    if (effectiveSize > maxSize) {
        throw new InvalidPageRequestException("Page size is too large");
    }

    Sort safeSort = validateSort(sort);

    return PageRequest.of(page, effectiveSize, safeSort);
}
~~~

Nếu API muốn từ chối size bằng 0 hoặc âm thay vì thay bằng default, hãy quy định rõ và test. Không âm thầm clamp một request sai thành một request khác nếu client cần biết giới hạn.

## 4. Tính offset an toàn

Với page number, offset được tính:

\[
from = page \times size
\]

Cần dùng kiểu số đủ lớn khi kiểm tra để tránh integer overflow:

~~~java
long from = (long) page * size;
long window = from + size;

if (window > maxResultWindow) {
    throw new DeepPaginationNotSupportedException();
}
~~~

Nếu nhân hai số int trước rồi mới gán vào long, phép nhân có thể overflow trước khi chuyển kiểu. Hãy cast trước phép nhân.

Ví dụ với max result window 10.000 và size 20:

| Page (zero-based) | from | from + size | Kết quả |
|---:|---:|---:|---|
| 0 | 0 | 20 | Cho phép |
| 10 | 200 | 220 | Cho phép |
| 100 | 2.000 | 2.020 | Cho phép |
| 499 | 9.980 | 10.000 | Cho phép |
| 500 | 10.000 | 10.020 | Từ chối hoặc chuyển cursor |

Giới hạn API nên được cấu hình rõ ràng. Elasticsearch có setting index.max_result_window, mặc định phổ biến là 10.000, nhưng ứng dụng có thể chọn ngưỡng thấp hơn.

## 5. Không để page number trở thành đường gây quá tải

Một client có thể gửi page=999999999 hoặc size=1000000. Nếu API chuyển thẳng request xuống Elasticsearch, ứng dụng đang cho phép người dùng điều khiển chi phí truy vấn.

Nên:

- Validate page và size trước khi tạo query.
- Giới hạn page depth theo API contract.
- Giới hạn request rate theo principal hoặc client.
- Đặt timeout.
- Giới hạn query complexity và số lượng filter.
- Ghi nhận request bị từ chối do deep pagination.
- Không retry tự động khi lỗi là result window exceeded.

Nếu API hỗ trợ nhiều index có max_result_window khác nhau, đừng expose setting thô của từng index cho client. Hãy định nghĩa một giới hạn API nhất quán hoặc chọn policy theo loại endpoint.

## 6. Offset pagination trong Spring Data Elasticsearch

Với repository hỗ trợ Pageable:

~~~java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("productId")
        )
);

Page<Product> result =
        productRepository.findByStatus("ACTIVE", pageable);
~~~

Với ElasticsearchOperations và NativeQuery:

~~~java
Query query = NativeQuery.builder()
        .withQuery(q -> q.term(t -> t
                .field("status")
                .value("ACTIVE")
        ))
        .withPageable(PageRequest.of(0, 20))
        .build();

SearchHits<Product> hits =
        operations.search(query, Product.class);
~~~

Pageable được chuyển thành offset và size trong search request. Vì vậy, page number lớn vẫn có thể vượt max_result_window.

Chữ ký repository và NativeQuery builder phụ thuộc phiên bản Spring Data Elasticsearch. Cần xác nhận API thực tế của dependency dự án, đặc biệt khi kết hợp custom query, sort và pageable.

## 7. Sort phải được kiểm soát bởi server

Không nên nhận tên field bất kỳ từ client rồi đưa thẳng vào sort. Chỉ cho phép field đã được thiết kế để sort và có mapping phù hợp.

Ví dụ allowlist:

~~~java
private static final Map<String, String> ALLOWED_SORT_FIELDS = Map.of(
        "createdAt", "createdAt",
        "price", "price",
        "name", "name.keyword"
);
~~~

Validate:

~~~java
public Sort validateSort(String field, String direction) {
    String mappedField = ALLOWED_SORT_FIELDS.get(field);

    if (mappedField == null) {
        throw new InvalidSortException("Unsupported sort field");
    }

    Sort.Direction sortDirection =
            Sort.Direction.fromString(direction);

    return Sort.by(new Sort.Order(sortDirection, mappedField));
}
~~~

Allowlist tránh lỗi sort trên field text, field không có doc values hoặc field nhạy cảm không nên expose. Nó cũng ngăn client tạo query quá đắt bằng cách sort theo một field không được thiết kế cho use case.

Với multi-field sort, server nên xác định thứ tự sort hoàn chỉnh thay vì cho client gửi một danh sách tùy ý không giới hạn.

## 8. Dùng tie-breaker để có thứ tự xác định

Nếu nhiều document có cùng sort value, thứ tự giữa chúng không được bảo đảm ổn định. Điều này đặc biệt quan trọng khi phân trang.

Ví dụ chỉ sort theo createdAt:

~~~json
"sort": [
  { "createdAt": "desc" }
]
~~~

Nếu nhiều document cùng timestamp, một hit có thể đổi vị trí giữa các lần search. Hãy thêm một tie-breaker duy nhất:

~~~json
"sort": [
  { "createdAt": "desc" },
  { "productId": "asc" }
]
~~~

productId nên có mapping keyword và duy nhất trong phạm vi kết quả. Nếu search qua nhiều tenant, bảo đảm tie-breaker duy nhất toàn tập kết quả hoặc kết hợp thêm tenantId.

Không dựa vào thứ tự mặc định của Elasticsearch khi sort values bằng nhau. Với PIT, Elasticsearch có thể bổ sung tie-breaker nội bộ như _shard_doc trong một số luồng, nhưng API vẫn phải giữ sort values chính xác từ response.

## 9. Vì sao cursor phù hợp với next-page API?

Offset pagination nói rằng “bỏ qua N kết quả đầu tiên”. Cursor pagination nói rằng “tiếp tục sau kết quả cuối cùng tôi đã nhận”.

Với from/size, trang 1.000 có thể yêu cầu Elasticsearch xử lý 20.000 hit trung gian dù client chỉ nhận 20. Với search_after, client gửi sort values của hit cuối để tiếp tục từ vị trí đó.

Cursor phù hợp khi:

- Giao diện dùng Next hoặc Load more.
- Kết quả có thể lớn hơn max_result_window.
- Không cần nhảy tùy ý tới trang bất kỳ.
- Sort có thể xác định và giữ ổn định.
- Client có thể lưu cursor cho request tiếp theo.

Cursor không tự bảo đảm snapshot consistency. Nếu dữ liệu thay đổi giữa các request, cần PIT hoặc chấp nhận semantics dữ liệu mới có thể xuất hiện/lệch vị trí.

## 10. search_after trong Elasticsearch

Trang đầu:

~~~http
POST /products/_search
{
  "size": 20,
  "sort": [
    { "createdAt": "desc" },
    { "productId": "asc" }
  ],
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
~~~

Giả sử hit cuối trang có sort values:

~~~json
[
  "2026-11-13T08:30:00Z",
  "p-020"
]
~~~

Trang kế tiếp:

~~~http
POST /products/_search
{
  "size": 20,
  "sort": [
    { "createdAt": "desc" },
    { "productId": "asc" }
  ],
  "search_after": [
    "2026-11-13T08:30:00Z",
    "p-020"
  ],
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
~~~

Các request tiếp theo phải giữ nguyên query và sort semantics. Cursor lấy từ hit cuối phải chứa tất cả sort values theo đúng thứ tự và kiểu dữ liệu.

Không tự tạo cursor chỉ từ productId nếu sort có cả createdAt và productId. Không đổi direction giữa các request. Không dùng giá trị do client tự tính thay cho sort values từ Elasticsearch.

## 11. PIT khi cần một snapshot nhất quán

Khi index thay đổi trong lúc người dùng duyệt trang, search_after không tự bảo đảm mọi trang thuộc cùng một snapshot. **Point in Time (PIT)** giữ một view nhất quán trong khoảng thời gian được chỉ định.

Luồng:

~~~text
Client                  API                    Elasticsearch
  |                      |                           |
  | GET first page       |                           |
  |--------------------->| Open PIT                  |
  |                      |-------------------------->|
  |                      |<--------------------------|
  |                      | Search with PIT           |
  |                      |-------------------------->|
  |                      |<--------------------------|
  |<---------------------| items + nextCursor        |
  |                      |                           |
  | GET next page        |                           |
  |--------------------->| Search with PIT + after   |
  |                      |-------------------------->|
  |                      |<--------------------------|
  |<---------------------| items + nextCursor        |
  |                      |                           |
  | Close / expiry       | Close PIT                 |
  |                      |-------------------------->|
~~~

Mở PIT:

~~~http
POST /products/_pit?keep_alive=1m
~~~

Search với PIT:

~~~http
POST /_search
{
  "size": 20,
  "pit": {
    "id": "PIT_ID",
    "keep_alive": "1m"
  },
  "sort": [
    { "createdAt": "desc" },
    { "productId": "asc" }
  ],
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
~~~

Trang kế tiếp dùng PIT ID mới nhất nếu response trả ID mới và thêm search_after từ hit cuối. Khi hoàn tất, đóng PIT:

~~~http
DELETE /_pit
{
  "id": "PIT_ID"
}
~~~

PIT giữ search context và tiêu thụ tài nguyên. Keep_alive cần vừa đủ cho thời gian người dùng có thể tiếp tục; phải đóng PIT khi hoàn tất và có cơ chế hết hạn khi client bỏ dở.

## 12. Thiết kế cursor token opaque

Không nên bắt client tự gửi raw JSON chứa PIT ID, sort values, index và query. Thay vào đó, API trả một token opaque.

Cursor có thể đại diện cho payload nội bộ:

~~~json
{
  "version": 1,
  "pitId": "PIT_ID",
  "searchAfter": [
    "2026-11-13T08:30:00Z",
    "p-020"
  ],
  "queryHash": "sha256-of-normalized-query",
  "sort": [
    "createdAt:desc",
    "productId:asc"
  ],
  "tenantId": "tenant-a",
  "subject": "alice",
  "expiresAt": "2026-11-13T09:00:00Z"
}
~~~

Đây là cấu trúc nội bộ minh họa, không phải định dạng bắt buộc. API có thể:

- Mã hóa và ký payload bằng HMAC hoặc chữ ký số.
- Mã hóa payload nếu nội dung cần được giữ bí mật.
- Dùng random token trỏ tới state lưu server-side.
- Kết hợp token ngẫu nhiên với state trong Redis hoặc database.

Ký token giúp phát hiện sửa đổi nhưng không che giấu nội dung. Nếu token chứa PIT ID hoặc thông tin nhạy cảm, dùng mã hóa hoặc lưu state server-side. Không xem Base64 là mã hóa hay bảo vệ.

## 13. Gắn cursor với query và filter

Cursor chỉ hợp lệ cho query mà nó được tạo ra. Nếu người dùng lấy cursor cho từ khóa keyboard rồi gửi lại với từ khóa monitor, backend không nên tiếp tục dùng cursor cũ với query mới.

Tạo query fingerprint từ các thành phần đã chuẩn hóa:

- Search text sau validation/normalization.
- Filter nghiệp vụ.
- Sort field và direction.
- Tenant scope.
- Các tham số ảnh hưởng kết quả.
- Phiên bản query/API.

Không đưa raw query string chưa chuẩn hóa vào fingerprint nếu thứ tự filter có thể thay đổi nhưng semantics không đổi. Tốt hơn là serialize một cấu trúc canonical.

Khi nhận cursor, backend dựng lại query từ request đã xác thực, tính fingerprint và so sánh với fingerprint trong cursor. Nếu không khớp, trả lỗi cursor không hợp lệ hoặc yêu cầu bắt đầu phiên tìm kiếm mới.

Không tin query hash do client gửi. Fingerprint phải được tính ở server.

## 14. Gắn cursor với principal và tenant

Trong hệ thống nhiều tenant, cursor phải thuộc phạm vi dữ liệu mà người tạo nó được phép xem.

Ví dụ Alice thuộc tenant-a lấy cursor. Bob thuộc tenant-b không được dùng cursor của Alice để tiếp tục đọc kết quả tenant-a.

Cursor state nên ràng buộc với:

- Subject hoặc user ID đã xác thực.
- Tenant ID lấy từ principal hoặc context được ủy quyền.
- Role/permission scope nếu quyền ảnh hưởng tập kết quả.
- Query fingerprint.
- Thời điểm hết hạn.
- Phiên bản policy nếu cần.

Mỗi request tiếp theo vẫn phải xác thực và authorize principal hiện tại. Cursor không phải access token và không thay thế JWT/session.

Nếu quyền của user thay đổi trong lúc cursor còn hiệu lực, ứng dụng có thể cần kiểm tra permission version hoặc re-authorize từng request. Không dựa vào quyền tại thời điểm tạo cursor nếu policy yêu cầu thu hồi quyền có hiệu lực ngay.

## 15. Không cho cursor quyết định index hoặc tenant tùy ý

Không đưa index name, alias hoặc tenant ID do client tự kiểm soát vào request Elasticsearch mà không validate. Một cursor bị sửa có thể trở thành cách truy cập index khác hoặc tenant khác.

Server nên:

1. Xác thực cursor signature/state.
2. Kiểm tra expiry.
3. Xác thực principal hiện tại.
4. Lấy tenant scope từ security context.
5. So khớp tenant/subject với cursor state.
6. Dựng lại query và filter từ server policy.
7. Chọn index/alias từ cấu hình server.
8. Chỉ dùng sort values và PIT ID sau khi token đã được xác minh.

Dù cursor được ký, query vẫn cần tenant filter ở server. Không coi token hợp lệ là lý do bỏ qua authorization.

## 16. Hết hạn, hủy và quản lý vòng đời cursor

Cursor/PIT không nên tồn tại vô hạn. Hãy quy định:

- Cursor TTL.
- PIT keep_alive.
- Số cursor/PIT tối đa trên mỗi user hoặc tenant.
- Cách đóng PIT khi người dùng hoàn tất.
- Dọn state khi cursor hết hạn.
- Cách xử lý khi PIT đã hết hạn ở Elasticsearch.
- Cách xử lý khi index alias được chuyển sang index mới.

Cursor state server-side nên có TTL và cơ chế cleanup. Nếu client tạo nhiều cursor nhưng không dùng, cần giới hạn để tránh giữ quá nhiều PIT context.

Có thể đóng PIT khi API biết người dùng đã hoàn tất, nhưng trong HTTP stateless flow server thường không biết chính xác khi nào client bỏ dở. TTL là hàng rào cần thiết; endpoint close tùy chọn giúp giải phóng sớm.

## 17. Response cursor không cần total count chính xác

Một API cursor thường chỉ cần biết có trang tiếp theo hay không. Có thể yêu cầu size + 1 hit:

1. Request Elasticsearch size = pageSize + 1.
2. Nếu nhận nhiều hơn pageSize, đặt hasNext = true.
3. Chỉ trả pageSize item đầu.
4. Cursor tiếp theo lấy từ hit cuối cùng trong số item thực sự trả về.
5. Nếu không có item thừa, hasNext = false.

Ví dụ page size 20, request lấy 21 hit. Nếu có 21, API trả 20 và báo còn trang tiếp theo.

Cần lấy cursor từ hit thứ 20, không lấy hit thứ 21 bị giữ lại làm lookahead. Nếu dùng hit thứ 21, request tiếp theo có thể bỏ qua document đó.

Cách size + 1 giúp tránh exact total count trong nhiều use case. Tuy nhiên, với PIT và search_after, cần giữ đúng snapshot và sort semantics cho cả lookahead.

## 18. track_total_hits và chính sách total

Exact total hits có thể tốn chi phí, nhất là với query phức tạp hoặc dữ liệu lớn. Elasticsearch hỗ trợ track_total_hits để điều khiển việc đếm.

~~~http
POST /products/_search
{
  "track_total_hits": false,
  "size": 20,
  "query": {
    "match": {
      "name": "keyboard"
    }
  }
}
~~~

Hoặc giới hạn số lượng cần đếm:

~~~json
"track_total_hits": 10000
~~~

Khi không yêu cầu exact total, response có thể trả total relation dạng gte thay vì eq. API nên biểu diễn rõ:

~~~json
{
  "total": {
    "value": 10000,
    "relation": "gte"
  }
}
~~~

Không gắn nhãn total này là chính xác nếu relation là gte. Nếu UI chỉ cần hasNext, size + 1 thường đủ.

Page-number API có thể cần totalPages, nhưng cursor API thường không cần. Hãy chọn theo nhu cầu thực tế thay vì mặc định mọi endpoint đều tính exact total.

## 19. Giới hạn truy cập không chỉ là page size

Một API phân trang an toàn cần kiểm soát nhiều chiều:

| Giới hạn | Mục tiêu |
|---|---|
| page size | Giới hạn số hit trả về |
| max offset | Ngăn deep pagination |
| query timeout | Giới hạn thời gian xử lý |
| rate limit | Giới hạn tần suất request |
| concurrent search limit | Ngăn một principal mở quá nhiều search |
| filter complexity | Giới hạn số/loại điều kiện |
| sort allowlist | Chỉ sort trên field được hỗ trợ |
| aggregation limit | Giới hạn bucket và độ phức tạp |
| cursor TTL | Giới hạn thời gian giữ state |
| PIT quota | Giới hạn search context |
| response byte limit | Ngăn payload quá lớn |
| export quota | Kiểm soát tác vụ dài và dữ liệu lớn |

Một page size nhỏ không đủ nếu client có thể gửi hàng nghìn request đồng thời hoặc yêu cầu aggregation hàng triệu bucket.

## 20. Rate limit và concurrency limit

Rate limit kiểm soát số request trong một khoảng thời gian; concurrency limit kiểm soát số request đang chạy đồng thời.

Có thể áp dụng theo:

- User/principal.
- Tenant.
- API key/client application.
- Endpoint hoặc loại query.
- Global capacity của cluster.

Ví dụ policy:

- Search thông thường: 60 request/phút/user.
- Cursor continuation: 120 request/phút/user.
- Export: 2 job đồng thời/tenant.
- PIT đang mở: tối đa một số lượng nhỏ trên mỗi user.

Đây chỉ là số minh họa. Giá trị thực tế cần dựa trên tải và SLO.

Khi vượt rate limit, API có thể trả HTTP 429 Too Many Requests và Retry-After nếu phù hợp. Khi vượt concurrency limit, có thể trả 429 hoặc 503 tùy semantics. Không retry ngay lập tức từ client mà không tôn trọng backoff.

## 21. Giới hạn aggregation và query complexity

Một request size=20 vẫn có thể rất đắt nếu aggregation có nhiều nhánh, terms cardinality cao hoặc nested aggregation sâu.

API nên kiểm soát:

- Số aggregation được phép.
- Terms size tối đa.
- Composite page size.
- Độ sâu nested aggregation.
- Số field được phép query.
- Wildcard/regexp/fuzzy query có giới hạn.
- Script query chỉ dành cho use case được kiểm soát.
- Timeout và circuit breaker behavior.

Không nhận nguyên Query DSL từ client cho một API công khai trừ khi có lớp validation/authorization rất chặt. Tốt hơn là expose các tham số nghiệp vụ có schema rõ ràng và backend tự dựng query.

## 22. Giới hạn response payload

Page size không phản ánh đầy đủ kích thước response. Một hit có thể chứa description dài, nested object lớn hoặc nhiều highlight fragments.

Có thể giới hạn:

- Số field trả về bằng DTO/source filtering.
- Kích thước text field.
- Số highlight fragments.
- Fragment size.
- Số bucket aggregation.
- Tổng byte response.
- Export thành file/job thay vì response đồng bộ.

Không trả toàn bộ Elasticsearch source nếu API chỉ cần vài field. DTO giúp ổn định hợp đồng và tránh vô tình expose metadata nội bộ.

## 23. Ví dụ controller page-number với WebFlux

Một controller có thể validate page/size rồi trả DTO:

~~~java
@GetMapping("/products")
public Mono<ProductPageResponse> search(
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size,
        @RequestParam String q,
        @AuthenticationPrincipal Jwt jwt) {

    String tenantId = jwt.getClaimAsString("tenant_id");

    Pageable pageable =
            paginationPolicy.validate(page, size, "createdAt", "desc");

    return productSearchService.searchPage(tenantId, q, pageable)
            .map(ProductPageResponse::from);
}
~~~

Service cần luôn gắn tenant filter:

~~~java
public Mono<ProductPageResponse> searchPage(
        String tenantId,
        String text,
        Pageable pageable) {

    Query query = buildTenantScopedQuery(tenantId, text, pageable);

    return operations.searchForPage(query, Product.class)
            .map(ProductPageResponse::from);
}
~~~

Tên phương thức như searchForPage và cách chuyển SearchHits sang Page tùy API/version; ví dụ minh họa kiến trúc. Điểm quan trọng là tenantId lấy từ principal, pageable đã validate và query được dựng ở server.

## 24. Ví dụ response DTO cho page-number API

~~~java
public record ProductPageResponse(
        List<ProductView> items,
        int page,
        int size,
        long totalElements,
        int totalPages,
        boolean hasNext,
        boolean hasPrevious
) {
    static ProductPageResponse from(Page<Product> page) {
        return new ProductPageResponse(
                page.getContent().stream()
                        .map(ProductView::from)
                        .toList(),
                page.getNumber(),
                page.getSize(),
                page.getTotalElements(),
                page.getTotalPages(),
                page.hasNext(),
                page.hasPrevious()
        );
    }
}
~~~

DTO nên dùng kiểu dữ liệu rõ ràng và không trả toàn bộ entity nếu entity có field nội bộ. Với reactive repository, Page có thể được bọc trong Mono; cách map tương tự nhưng publisher phải được giữ xuyên suốt.

## 25. Ví dụ cursor service

Một cursor service có thể tách thành các bước:

~~~java
public Mono<ProductCursorPage> searchNext(
        SearchRequest request,
        Authentication authentication) {

    return cursorService.resolveAndValidate(
                    request.cursor(),
                    request.filters(),
                    authentication
            )
            .flatMap(state ->
                    elasticsearchSearch.search(
                            state.query(),
                            state.pitId(),
                            state.searchAfter(),
                            request.limit() + 1
                    )
                    .map(response ->
                            cursorService.toPage(
                                    response,
                                    state,
                                    request.limit()
                            )
                    )
            );
}
~~~

Ví dụ chỉ thể hiện cấu trúc. Cursor service cần xác minh signature/lookup state, principal, tenant, query fingerprint, sort và expiry trước khi gọi Elasticsearch.

Không để controller tự parse token rồi tự ghép query. Tách trách nhiệm giúp test security và pagination độc lập.

## 26. Đóng gói cursor và ký token

Nếu lưu state trong token, một cách phổ biến là serialize payload canonical rồi ký HMAC:

~~~text
payloadBytes = UTF8(canonicalJson(cursorState))
signature = HMAC_SHA256(secretKey, payloadBytes)
token = base64url(payloadBytes) + "." + base64url(signature)
~~~

Khi nhận token:

1. Tách payload và signature.
2. Tính lại HMAC từ payload.
3. So sánh signature theo constant-time comparison.
4. Chỉ parse payload sau khi xác minh chữ ký.
5. Kiểm tra version và expiry.
6. Kiểm tra subject/tenant/query binding.
7. Tiếp tục search.

HMAC cung cấp integrity/authenticity, không cung cấp confidentiality. Người nhận token vẫn có thể đọc payload nếu chỉ Base64URL encode. Nếu payload chứa PIT ID hoặc thông tin nội bộ, dùng authenticated encryption hoặc lưu state server-side.

Secret key cần được quản lý qua secret manager/configuration bảo mật, có kế hoạch rotation và key ID nếu cần hỗ trợ nhiều key trong thời gian chuyển đổi.

## 27. Cursor opaque lưu state phía server

Một cách khác là tạo token ngẫu nhiên đủ entropy và lưu state trong Redis hoặc database:

~~~text
cursor token -> server-side state
                 - PIT ID
                 - search_after
                 - query fingerprint
                 - subject / tenant
                 - expiresAt
~~~

Ưu điểm:

- Client không nhìn thấy PIT ID hoặc sort values.
- Có thể thu hồi cursor.
- Có thể kiểm soát số cursor đang mở.
- Có thể đóng PIT khi state bị xóa hoặc hết hạn.

Nhược điểm:

- Cần storage và cleanup.
- Mỗi request continuation có thể cần đọc state.
- Phải xử lý state store availability.
- Cần tránh race condition nếu cùng cursor được dùng đồng thời.

Token nên ngẫu nhiên, không tuần tự và không chứa user ID trực tiếp. State store cần TTL và giới hạn số record để tránh bị lạm dụng tạo nhiều cursor.

## 28. Xử lý cursor sai, hết hạn và không còn PIT

API nên phân biệt các trường hợp:

| Tình huống | Hành vi API gợi ý |
|---|---|
| Token không đúng định dạng/chữ ký | 400 Invalid cursor |
| Cursor hết hạn | 410 Gone hoặc 400 theo contract |
| Cursor thuộc user/tenant khác | 403 hoặc 404 theo chính sách |
| Query/filter không khớp | 400 Cursor does not match request |
| PIT đã hết hạn | 410 Restart search |
| Index/alias đã thay đổi không tương thích | Yêu cầu bắt đầu search mới |
| State store không sẵn sàng | 503 Service Unavailable |

Không trả raw PIT ID, index name, query DSL hoặc stack trace trong error body.

Khi PIT hết hạn, không tự mở PIT mới rồi tiếp tục bằng sort values cũ mà không thông báo. PIT mới có snapshot khác; kết quả có thể lặp hoặc bỏ sót. Hãy yêu cầu client bắt đầu phiên tìm kiếm mới hoặc dùng một chiến lược recovery đã được định nghĩa.

## 29. Quyền truy cập và tenant isolation trong mọi trang

Tenant filter phải được áp dụng ở mọi request search, kể cả request cursor tiếp theo. Không nghĩ rằng cursor đã được tạo hợp lệ thì các request sau không cần authorize lại.

Mỗi lần continuation:

- Xác thực access token/session.
- Lấy tenant từ principal hiện tại.
- Kiểm tra cursor thuộc đúng subject/tenant.
- Kiểm tra role/permission hiện tại.
- Dựng lại query có tenant filter.
- Dùng PIT/search_after đã xác minh.
- Chỉ trả DTO được phép.

Nếu user mất quyền giữa hai trang, policy cần quy định có tiếp tục hay không. Với quyền nhạy cảm, nên re-authorize mỗi request và có thể gắn permission version vào cursor để thu hồi cursor cũ.

## 30. Không để client kiểm soát sort values hoặc query DSL

Client chỉ nên gửi các tham số nghiệp vụ đã được allowlist:

~~~http
GET /products?q=keyboard&sort=price,asc&limit=20
~~~

Backend ánh xạ sort=price thành field price đã được kiểm soát. Cursor giữ sort values do Elasticsearch trả về.

Không nhận raw sort JSON hoặc raw Query DSL từ client rồi chuyển thẳng xuống cluster. Nếu cần query builder linh hoạt cho người dùng nội bộ, phải có parser/allowlist và giới hạn complexity.

Các field như tenantId, ownerId, internalCost, permissions hoặc index routing không nên được client tự chọn để thay đổi phạm vi truy vấn.

## 31. Bảo vệ cursor khỏi replay và chia sẻ ngoài ý muốn

Một cursor hợp lệ có thể bị copy sang thiết bị hoặc người dùng khác. Có thể ràng buộc cursor với subject/tenant và expiry để giới hạn việc chia sẻ.

Tùy use case, có thể:

- Cho phép cursor được dùng lại bởi cùng user.
- Chỉ cho phép một lần sử dụng nếu cần stateful continuation.
- Gắn token với session/device nếu chính sách cần.
- Giới hạn số lần continuation.
- Thu hồi cursor khi logout hoặc quyền thay đổi.
- Không ghi cursor đầy đủ vào log/analytics.

Không cần ràng buộc quá chặt nếu sản phẩm cần hỗ trợ người dùng mở nhiều tab hoặc retry request do network. Chọn semantics phù hợp và test concurrent continuation.

Nếu cùng cursor được gửi đồng thời, stateful cursor có thể cần optimistic lock hoặc version để tránh đóng PIT sớm hoặc cập nhật state sai thứ tự.

## 32. Cache và cursor

Nếu cache response search, cache key phải bao gồm những yếu tố ảnh hưởng đến kết quả:

- Query fingerprint.
- Tenant.
- Principal/permission scope nếu field visibility khác nhau.
- Sort.
- Cursor hoặc search-after position.
- Page size.
- Snapshot/PIT context nếu kết quả cần nhất quán.

Không cache một response chỉ theo từ khóa nếu hai tenant có thể nhìn thấy tập dữ liệu khác nhau.

Cursor state cũng không nên được chia sẻ giữa các request chỉ vì query string giống nhau. Hai user cùng search keyboard vẫn có thể có quyền khác nhau.

## 33. Export không nên là một page-size rất lớn

Một yêu cầu “tải tất cả sản phẩm” không nên được xử lý bằng cách cho client gửi size=1000000 hoặc page=50000.

Hãy tạo export job:

1. Xác thực quyền export.
2. Lấy tenant và filter từ principal/policy.
3. Tạo job có giới hạn số bản ghi và thời gian.
4. Duyệt dữ liệu bằng PIT + search_after hoặc cơ chế batch phù hợp.
5. Ghi file theo stream/batch.
6. Lưu trạng thái và tiến độ.
7. Cấp link tải có thời hạn.
8. Kiểm tra quyền khi tải file.
9. Dọn PIT, file tạm và job state sau retention.

Export có thể có quota riêng theo tenant và role. Không để một request HTTP giữ kết nối mở hàng giờ để tạo file lớn.

## 34. Error handling và HTTP semantics

Một số status code thường dùng:

| Status | Ý nghĩa |
|---|---|
| 400 | Page/size/sort/cursor format không hợp lệ |
| 401 | Chưa xác thực |
| 403 | Không có quyền |
| 404 | Resource/cursor state không tồn tại hoặc bị che theo policy |
| 410 | Cursor/PIT đã hết hạn |
| 422 | Tham số hợp lệ về cú pháp nhưng không phù hợp policy, nếu API dùng semantics này |
| 429 | Vượt rate limit hoặc quota |
| 503 | Elasticsearch/state store tạm thời không sẵn sàng |
| 504 | Timeout ở gateway/API |

Chọn status nhất quán với contract và framework. Không trả 200 với danh sách rỗng khi thực tế request bị từ chối do deep pagination; điều đó khiến client hiểu nhầm không có dữ liệu.

Error body nên có mã lỗi ổn định, thông điệp an toàn và correlation ID:

~~~json
{
  "code": "CURSOR_EXPIRED",
  "message": "Search session has expired. Start a new search.",
  "requestId": "req-123"
}
~~~

Không đưa raw Elasticsearch exception hoặc token vào response.

## 35. Quan sát và vận hành pagination

Theo dõi:

- Search request count và latency p50/p95/p99.
- Page size distribution.
- Offset depth distribution.
- Số request bị từ chối do max window.
- Cursor create/continue/expire/invalid count.
- PIT đang mở và tuổi PIT.
- Rate limit và concurrency rejection.
- Search timeout và 429.
- Response byte size.
- Exact total hits request rate.
- Aggregation bucket count.
- Cursor state store hit/miss/error.

Metric tag nên có cardinality thấp. Không gắn cursor token, document ID hoặc user ID trực tiếp vào metric labels. Có thể dùng structured logs/traces đã masking để điều tra một request cụ thể.

Alert khi PIT count tăng bất thường, cursor state không được cleanup, deep page request tăng đột biến hoặc p95 search latency vượt SLO.

## 36. Kiểm thử page-number limits

Test validation ở tầng unit:

~~~java
@Test
void rejectsPageBeyondResultWindow() {
    assertThatThrownBy(() ->
            policy.validate(page(500), size(20))
    ).isInstanceOf(DeepPaginationNotSupportedException.class);
}
~~~

Test integration với Elasticsearch nên tạo index test có max_result_window nhỏ, ví dụ 100:

- from=80, size=20 phải hợp lệ.
- from=81, size=20 phải bị từ chối.
- from=0, size=101 phải bị từ chối.
- API phải trả error contract phù hợp.
- Không retry cùng request vượt giới hạn.

Không chỉ test helper; cần xác nhận query thật được gửi với offset/size đã validate.

## 37. Kiểm thử cursor không bị sửa

Với cursor ký HMAC, test cần:

- Token hợp lệ được chấp nhận.
- Sửa một byte payload bị từ chối.
- Sửa signature bị từ chối.
- Token sai định dạng bị từ chối.
- Token version không hỗ trợ bị từ chối.
- Token hết hạn bị từ chối.
- Token không được parse trước khi signature được xác minh.
- Error response không tiết lộ secret hoặc payload nội bộ.

Với cursor stateful, test thêm token ngẫu nhiên không tồn tại, state hết TTL, state bị thu hồi và state store lỗi.

## 38. Kiểm thử cursor gắn với user và tenant

Tạo Alice thuộc tenant-a và Bob thuộc tenant-b:

1. Alice bắt đầu search và nhận cursor.
2. Alice tiếp tục bằng cursor: thành công.
3. Bob gửi cursor của Alice: bị từ chối.
4. Alice đổi query/filter nhưng dùng cursor cũ: bị từ chối.
5. Alice đổi sort nhưng dùng cursor cũ: bị từ chối.
6. Alice mất quyền rồi tiếp tục: kết quả theo policy thu hồi quyền.
7. Cursor hết hạn: API yêu cầu bắt đầu search mới.

Test cần kiểm tra response không chứa dữ liệu tenant khác, kể cả thông qua error detail hoặc metadata.

## 39. Kiểm thử PIT lifecycle

Integration test nên xác nhận:

- Trang đầu tạo hoặc dùng PIT đúng.
- Cursor chứa tham chiếu tới đúng PIT state.
- Trang tiếp theo dùng PIT ID mới nhất nếu response đổi ID.
- PIT giữ snapshot khi document mới được index.
- Cursor không dùng được sau khi PIT hết hạn.
- Close endpoint đóng PIT.
- TTL cleanup giải phóng state.
- User không thể đóng PIT của user khác bằng cursor giả mạo.
- Lỗi Elasticsearch khi PIT hết hạn được chuyển thành error contract phù hợp.

PIT là tài nguyên cluster. Test lifecycle cần xác nhận cả đường thành công lẫn cancellation/abandonment.

## 40. Kiểm thử pagination không lặp và không bỏ sót

Tạo fixture cố định có nhiều document cùng sort value, ví dụ 257 sản phẩm, page size 50.

Với cursor flow:

1. Lấy trang đầu.
2. Lưu ID.
3. Lấy nextCursor.
4. Tiếp tục đến khi hết.
5. Kiểm tra số ID bằng fixture count.
6. Kiểm tra mọi ID là duy nhất.
7. Kiểm tra tập ID bằng tập fixture.
8. Kiểm tra sort order toàn cục.
9. Kiểm tra trang cuối có hasNext=false và cursor null theo contract.

Nếu dùng PIT, thêm một document mới giữa các trang và xác nhận snapshot hiện tại không bị thay đổi; một search session mới có thể nhìn thấy document mới.

## 41. Kiểm thử rate limit và query complexity

Test cần chứng minh các giới hạn có hiệu lực:

- Vượt request quota trả 429.
- Response có Retry-After nếu policy cung cấp.
- Quota được tính đúng theo user/tenant/client.
- Một user không thể làm cạn toàn bộ quota của tenant nếu policy tách quota.
- Export có quota riêng.
- Aggregation size vượt ngưỡng bị từ chối.
- Sort field không allowlist bị từ chối.
- Query quá dài hoặc quá phức tạp bị từ chối.
- Concurrent PIT vượt giới hạn không tạo thêm search context.

Test concurrency cần chạy với điều kiện kiểm soát để tránh flaky. Có thể dùng fake clock hoặc rate limiter test mode thay vì sleep thật.

## 42. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| API chậm ở trang sâu | Offset lớn | Giới hạn page depth hoặc cursor |
| Page size rất lớn gây OOM | Không validate size | Default và max size |
| Sort không ổn định giữa trang | Thiếu tie-breaker | Thêm unique keyword field |
| Cursor dùng được với query khác | Không gắn query fingerprint | Canonicalize và so khớp query |
| Cursor tenant A dùng ở tenant B | Không ràng buộc principal/tenant | Bind subject/tenant và re-authorize |
| Cursor sửa được | Token chỉ Base64 | HMAC/AEAD hoặc state server-side |
| PIT tồn tại lâu | Thiếu TTL/close | Quota, keep_alive và cleanup |
| Trang tiếp theo bỏ qua item | Lấy cursor từ hit lookahead | Lấy sort values từ hit cuối được trả |
| Cursor cũ tiếp tục trên PIT mới | Tự mở PIT thay thế không thông báo | Yêu cầu restart search |
| Count chậm | Luôn yêu cầu exact total | track_total_hits policy hoặc size+1 |
| Export gây tải cao | Dùng page size cực lớn | Background batch job |
| Rate limit bị né bằng nhiều token | Chỉ limit theo token | Limit theo principal/tenant/client policy |
| Error lộ PIT/query | Trả raw exception | Error DTO an toàn |

## 43. Quy trình thiết kế API phân trang

1. Xác định UI cần nhảy trang hay chỉ đi tiếp.
2. Chọn from/size hoặc cursor theo nhu cầu.
3. Định nghĩa page size mặc định và tối đa.
4. Kiểm tra offset bằng phép tính an toàn.
5. Allowlist sort fields và direction.
6. Thêm tie-breaker duy nhất.
7. Quyết định có cần snapshot consistency hay không.
8. Nếu cần snapshot, dùng PIT + search_after.
9. Thiết kế cursor opaque, có chữ ký hoặc state server-side.
10. Bind cursor với query, sort, principal, tenant và expiry.
11. Re-authorize ở mỗi request continuation.
12. Đặt rate, concurrency, aggregation và response limits.
13. Chỉ yêu cầu exact total khi cần.
14. Tách export thành job/batch.
15. Viết integration test cho giới hạn, cursor, PIT và tenant boundary.
16. Theo dõi latency, cursor/PIT lifecycle và request bị từ chối.

## 44. Nguyên tắc thiết kế

- Page-number API phù hợp cho cửa sổ kết quả nhỏ và cần nhảy trang.
- Cursor API phù hợp với next/load more và tập kết quả lớn.
- Không cho page size hoặc offset tùy ý.
- Tính from bằng long để tránh overflow.
- Dùng sort allowlist và tie-breaker ổn định.
- Dùng search_after để tiếp tục từ sort values của hit cuối.
- Dùng PIT khi cần snapshot nhất quán.
- Cursor phải opaque, có integrity protection hoặc state server-side.
- Bind cursor với query fingerprint, principal, tenant và expiry.
- Re-authorize mỗi request, không xem cursor là credential.
- Quản lý PIT quota, keep_alive, close và cleanup.
- Giới hạn rate, concurrency, aggregation complexity và response size.
- Không yêu cầu exact total nếu UX không cần.
- Tách export thành background job.
- Kiểm thử cả pagination boundaries và security boundaries.
- Không để error response lộ PIT ID, query nội bộ hoặc dữ liệu nhạy cảm.

Thiết kế API phân trang cho Spring Data Elasticsearch là quyết định về cả trải nghiệm người dùng, hiệu năng và bảo mật. from/size phù hợp với danh sách vừa phải nhưng cần giới hạn offset và page size; search_after phù hợp với điều hướng tuần tự; PIT giúp giữ snapshot khi dữ liệu thay đổi. Cursor cần được bảo vệ khỏi sửa đổi, gắn với query và principal, có thời hạn và được kiểm tra quyền ở mọi request. Kết hợp sort ổn định, giới hạn rate/concurrency/aggregation, response DTO và integration test giúp API phục vụ dữ liệu lớn mà không tạo ra truy vấn quá đắt hoặc mở rộng phạm vi truy cập ngoài ý muốn.
