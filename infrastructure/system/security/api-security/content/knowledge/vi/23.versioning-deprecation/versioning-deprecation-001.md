# Version trong path, header hoặc media type

API thay đổi theo thời gian: thêm field, đổi quy tắc validation, sửa semantics của một thao tác hoặc loại bỏ chức năng cũ. Versioning giúp server và client thống nhất hợp đồng nào đang được sử dụng. Với API Security, cách chọn version còn ảnh hưởng đến định tuyến, authorization, chữ ký request, cache, gateway, logging và khả năng thu hồi một phiên bản có lỗ hổng.

Ba cách phổ biến để biểu diễn version là đặt trong URL path, gửi qua header hoặc dùng media type trong `Accept`/`Content-Type`. Mỗi cách có ưu điểm vận hành riêng, nhưng không cách nào tự tạo ra ranh giới bảo mật. Một endpoint `/v1` không an toàn hơn `/v2` chỉ vì có số version; server vẫn phải xác thực, phân quyền và validate theo chính sách tương ứng.

## 1. Vì sao API cần version?

Version xác định hợp đồng mà client và server cùng hiểu. Một thay đổi có thể tương thích ngược hoặc phá vỡ client hiện tại.

| Thay đổi | Khả năng tương thích | Ví dụ |
|---|---|---|
| Thêm field response tùy chọn | Thường tương thích nếu client bỏ qua field lạ | Thêm `displayLabel` |
| Thêm endpoint mới | Thường tương thích | `GET /reports/summary` |
| Thêm enum value | Có thể phá client dùng enum đóng | Thêm trạng thái `REVERSED` |
| Đổi kiểu hoặc ý nghĩa field | Thường là breaking change | `amount` từ integer VND sang decimal theo đơn vị tiền tệ |
| Thay đổi semantics của endpoint | Có thể phá client dù schema không đổi | `DELETE` trước đây archive, nay xóa vĩnh viễn |
| Siết validation hoặc authorization | Có thể làm request cũ bị từ chối | Bắt buộc thêm scope hoặc trường xác minh |
| Bỏ field hoặc endpoint | Breaking change | Xóa `legacyAccountId` |

Không nên tăng major version cho mọi thay đổi nhỏ. Cần có chính sách phân loại thay đổi, quy tắc tương thích và quy trình deprecation. Đặc biệt, một thay đổi bảo mật có thể cần triển khai ngay cả khi nó làm client cũ bị từ chối; không nên giữ lỗ hổng chỉ để bảo toàn tương thích.

## 2. Ba vị trí biểu diễn version

| Cách | Ví dụ | Server xác định version từ |
|---|---|---|
| URL path | `/api/v2/orders/ORD-42` | Segment trong request target |
| Custom header | `X-API-Version: 2` | Header được hợp đồng API quy định |
| Media type | `Accept: application/vnd.example.orders.v2+json` | Content negotiation trong header `Accept` hoặc `Content-Type` |

Version nên có một nguồn xác định chính thức cho mỗi API contract. Nếu cùng lúc cho phép version trong path, header và media type, phải định nghĩa thứ tự ưu tiên và hành vi khi các giá trị mâu thuẫn. Cách đơn giản và an toàn hơn thường là chọn một cơ chế chính cho mỗi API surface.

Version cần được parse theo allowlist. Không dùng chuỗi version do client gửi để tạo tên class, tên file, đường dẫn thư mục, tên bảng hoặc URL nội bộ tùy ý.

## 3. Version trong URL path

Path versioning đặt version ngay trong URI:

```http
GET /api/v1/orders/ORD-42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Accept: application/json
```

Phiên bản mới có path riêng:

```http
GET /api/v2/orders/ORD-42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Accept: application/json
```

### 3.1. Ưu điểm

- Dễ nhìn thấy trong log, trace, dashboard, tài liệu và browser history.
- Dễ cấu hình route ở API gateway, reverse proxy và ingress.
- Dễ phân biệt cache key vì URI khác nhau.
- Client có thể gọi trực tiếp version mong muốn mà không cần content negotiation phức tạp.
- Có thể triển khai hoặc rollback từng route version tương đối độc lập.

### 3.2. Hạn chế

- Version trở thành một phần của resource URI; cùng một dữ liệu có nhiều URI theo từng contract.
- Link, callback, webhook destination và tài liệu client cần được cập nhật khi chuyển version.
- Gateway và backend phải thống nhất route normalization; alias hoặc path encoding sai có thể đưa request tới handler khác.
- Nếu policy chỉ bảo vệ `/api/v1/**` mà quên `/api/v2/**`, phiên bản mới có thể bị bỏ sót authorization.

### 3.3. Kiểm soát bảo mật

Định tuyến theo path version phải dùng route matcher chính xác. Tránh rule prefix mơ hồ như `startsWith("/api/v1")` nếu có thể khớp nhầm `/api/v10` hoặc route khác. Kiểm thử trailing slash, encoded path segment, duplicate slash và API version cũ.

Không xem version trong path là bằng chứng về quyền. Token hợp lệ cho API audience vẫn cần scope/permission phù hợp với endpoint và version. Nếu version mới có hành động nhạy cảm hơn, phải định nghĩa permission và object-level authorization riêng.

Ví dụ, `GET /api/v1/users/{id}` và `GET /api/v2/users/{id}` có thể trả response khác nhau nhưng đều phải kiểm tra cùng quyền đọc hồ sơ và cùng tenant scope. Không để version mới bỏ qua kiểm tra chỉ vì controller hoặc DTO được viết lại.

## 4. Version trong custom header

Header versioning giữ URI ổn định và gửi version riêng:

```http
GET /api/orders/ORD-42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
X-API-Version: 2
Accept: application/json
```

Tên header là một phần hợp đồng do nhà cung cấp API lựa chọn. Có thể dùng `X-API-Version`, `Api-Version` hoặc một tên khác; cần công bố duy nhất và xử lý nhất quán.

### 4.1. Ưu điểm

- URI mô tả resource ổn định, không chứa thông tin phiên bản.
- Có thể triển khai nhiều contract trên cùng route.
- Dễ chuyển client bằng cách đổi header mà không phải thay mọi URL.
- Hữu ích khi hệ thống đã có một gateway hoặc SDK quản lý header chung.

### 4.2. Hạn chế

- Version khó nhìn thấy hơn trong URL, access log hoặc khi kiểm tra thủ công nếu log không ghi header đã chuẩn hóa.
- Shared cache có thể trả response của version khác nếu cache key không tính header.
- Một số proxy, CDN hoặc client library có thể bỏ header tùy chỉnh.
- Header trùng lặp hoặc nhiều giá trị có thể được các tầng diễn giải khác nhau.
- CORS cần cho phép header này trong preflight nếu browser client gửi nó.

### 4.3. Kiểm soát bảo mật

Server cần từ chối version thiếu, sai định dạng hoặc không được hỗ trợ theo hợp đồng. Không âm thầm fallback sang version cũ hoặc version mới nhất vì hành vi đó có thể làm client gọi nhầm semantics và policy.

Với header đơn trị, từ chối nếu header xuất hiện nhiều lần hoặc có giá trị nhập nhằng. Gateway và backend phải dùng cùng một giá trị sau chuẩn hóa. Không để gateway kiểm tra `X-API-Version: 1` nhưng backend chọn giá trị thứ hai `2`.

Nếu browser client cần gửi header version, CORS policy phải cho phép đúng header cần thiết. CORS chỉ cho phép trình duyệt gửi/đọc response theo origin; request vẫn phải được xác thực và phân quyền.

## 5. Version qua media type

Media type versioning dùng content negotiation để xác định representation hoặc contract. Client thường gửi media type mong muốn qua `Accept`:

```http
GET /api/orders/ORD-42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Accept: application/vnd.example.orders.v2+json
```

Với request có body, `Content-Type` mô tả định dạng representation được gửi lên; ví dụ:

```http
POST /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Content-Type: application/vnd.example.orders.v2+json
Accept: application/vnd.example.orders.v2+json

{"reference":"WEB-42","items":[]}
```

Có thể dùng vendor media type như `application/vnd.example.orders.v2+json` hoặc media type parameter theo hợp đồng, chẳng hạn `application/json;version=2`. Cần chọn một dạng và định nghĩa rõ cách parse, so khớp và xử lý quality value (`q`).

### 5.1. Ưu điểm

- Version gắn với representation được yêu cầu hoặc gửi lên.
- Cùng URI có thể cung cấp nhiều representation.
- Content negotiation là cơ chế HTTP quen thuộc.
- Có thể version request và response độc lập nếu hợp đồng cho phép và định nghĩa rõ.

### 5.2. Hạn chế

- Client và công cụ trung gian cần hỗ trợ `Accept`/`Content-Type` chính xác.
- Cấu hình cache phải tính đến `Accept` hoặc header negotiation liên quan.
- API gateway, WAF và observability cần hiểu vendor media type.
- Dễ nhầm lẫn giữa version của representation và version của business behavior nếu hợp đồng không rõ.
- `Accept` có thể chứa nhiều media type và quality value, nên server cần quy tắc lựa chọn xác định.

### 5.3. Kiểm soát bảo mật

Không chọn version bằng cách lấy chuỗi con bất kỳ từ `Accept`. Dùng parser media type chuẩn, allowlist chính xác các loại được hỗ trợ và từ chối giá trị không hợp lệ. Nếu client gửi nhiều media type, chọn theo quy tắc negotiation đã công bố; nếu không có representation phù hợp, trả `406 Not Acceptable`.

Với request body, `Content-Type` không được hỗ trợ thường trả `415 Unsupported Media Type`. Không để server parse body theo một schema nhưng serialize hoặc authorize như version khác.

Nếu request signing được sử dụng, các header quyết định version hoặc representation phải được bao phủ trong chữ ký theo giao thức. Nếu không, một bên trung gian có thể thay `Accept` hoặc `Content-Type` và làm server diễn giải payload theo contract khác.

## 6. So sánh và chọn cơ chế

| Tiêu chí | Path | Header | Media type |
|---|---|---|---|
| Dễ quan sát | Cao | Trung bình | Trung bình/thấp |
| Cấu hình gateway | Thường đơn giản | Cần header-aware routing | Cần content negotiation support |
| Cache | URI tự phân biệt version | Cần `Vary`/cache key theo header | Cần `Vary: Accept` hoặc header phù hợp |
| Browser/CORS | Ít cấu hình bổ sung | Cần allow custom header | Thường dùng header chuẩn đã hỗ trợ |
| Một URI cho nhiều contract | Không | Có | Có |
| Phân biệt request/response representation | Hạn chế | Theo custom policy | Tự nhiên hơn qua Content-Type/Accept |
| Độ phức tạp | Thấp đến trung bình | Trung bình | Trung bình đến cao |

Chọn dựa trên cách client tích hợp, khả năng gateway, caching, observability và nhu cầu representation. Path versioning thường dễ vận hành với public REST API. Header hoặc media type có thể phù hợp khi muốn giữ URI ổn định hoặc cần content negotiation. Điều quan trọng hơn vị trí đặt version là mọi tầng phải hiểu cùng một version và áp dụng cùng policy.

## 7. Tránh version ambiguity và downgrade

Version ambiguity xảy ra khi request chứa nhiều tín hiệu version hoặc các tầng xử lý không thống nhất. Ví dụ:

```http
GET /api/v1/orders/ORD-42 HTTP/1.1
X-API-Version: 2
Accept: application/vnd.example.orders.v3+json
```

Nếu path, header và media type cùng xuất hiện nhưng chỉ một tầng kiểm tra, gateway có thể áp dụng policy cho v1 trong khi backend chạy v3. Không nên chấp nhận trạng thái nhập nhằng này.

Các nguyên tắc:

- Chọn một nguồn version chính thức cho mỗi API surface.
- Nếu hỗ trợ nhiều nguồn, định nghĩa precedence và từ chối khi các nguồn mâu thuẫn.
- Không fallback âm thầm khi version thiếu hoặc không hỗ trợ.
- Không cho client ép downgrade sang version có policy yếu hơn nếu version đó đã bị vô hiệu hóa.
- Không để route alias hoặc rewrite rule bỏ qua kiểm tra version.
- Ghi version đã chuẩn hóa vào log/trace để đối chiếu định tuyến và policy.

Một version cũ vẫn có thể tồn tại trong thời gian migration, nhưng cần áp dụng cùng baseline security hiện tại. Nếu version có lỗ hổng nghiêm trọng, tổ chức có thể phải chặn nó sớm và yêu cầu client nâng cấp.

## 8. Version không phải ranh giới authorization

Không nên gắn quyền chỉ với số version, ví dụ “mọi request v2 là admin” hoặc “v1 chỉ dành cho user thường”. Version mô tả contract; danh tính và permission xác định caller được làm gì.

Với mỗi version, cần xác minh:

- Authentication vẫn kiểm tra issuer, audience, expiry và token type theo đúng trust policy.
- Scope/permission được ánh xạ đúng với hành động trong version đó.
- Object-level authorization và tenant isolation không bị bỏ qua.
- Property filtering không trả thêm field nhạy cảm do DTO mới.
- Validation và business state transition vẫn được thực thi.
- Rate limit, quota và anti-abuse policy không bị reset hoặc nới lỏng ngoài chủ đích.
- Audit ghi được version và policy đã áp dụng.

Nếu v2 thay đổi cách biểu diễn role hoặc scope, cần migration mapping rõ ràng. Không tin claim version do client tự gửi nếu token hoặc credential không ràng buộc nó. Version của API cũng không thay thế `aud` của access token: token phải được phát hành cho resource server phù hợp.

## 9. Versioning và request signature

API sử dụng HMAC, HTTP Message Signatures hoặc chữ ký request riêng cần xác định version ảnh hưởng đến canonical request như thế nào.

Với path versioning, path thường nằm trong request target và có thể được chữ ký bao phủ. Với header versioning, header version cần nằm trong danh sách thành phần được ký nếu nó ảnh hưởng đến cách diễn giải request. Với media type versioning, `Accept` và `Content-Type` có thể cần được ký theo giao thức.

Nếu chữ ký không bao phủ thông tin quyết định version, một request có thể bị chuyển từ contract này sang contract khác mà chữ ký vẫn hợp lệ. Ngược lại, nếu canonicalization giữa client, gateway và backend khác nhau, request hợp lệ có thể bị từ chối hoặc được diễn giải khác nhau.

Hãy kiểm thử:

- Signature được xác minh trên đúng path/header/media type đã chuẩn hóa.
- Proxy không thay đổi thành phần đã ký sau khi xác minh.
- Gateway và backend dùng cùng version và cùng canonical request.
- Không có header trùng lặp hoặc path alias làm thay đổi version sau kiểm tra.
- Key rotation và thuật toán ký được áp dụng đồng nhất trên các version còn hỗ trợ.

Không tự thêm thành phần vào chữ ký nếu giao thức provider quy định canonical string cụ thể. Với giao thức tiêu chuẩn, tuân thủ đúng spec và thư viện tương thích.

## 10. Cache, CDN và content negotiation

Cache là một điểm dễ gây lẫn response giữa các version. Nếu cùng URL được dùng cho v1 và v2 qua header, shared cache phải phân biệt representation theo header version. Nếu không, client có thể nhận schema hoặc dữ liệu của version khác.

Ví dụ với custom header:

```http
Vary: X-API-Version
```

Với media type negotiation:

```http
Vary: Accept
```

Nếu response còn phụ thuộc `Accept-Language`, encoding hoặc các header khác, `Vary` cần phản ánh các chiều đó. Không đưa Authorization token vào cache key theo cách gây lưu credential; với response cá nhân hoặc nhạy cảm, dùng cache policy phù hợp như `private` hoặc `no-store`.

Path versioning thường tạo URI khác nhau nên cache phân biệt tự nhiên hơn, nhưng vẫn cần kiểm soát query, authorization context và các header ảnh hưởng response. Không cache response riêng tư ở shared cache chỉ vì URL chứa version.

## 11. Gateway, routing và observability

API gateway có thể route version đến backend khác nhau, áp dụng rate limit, TLS policy và một số kiểm soát authorization. Tuy nhiên, backend vẫn cần bảo vệ chức năng nếu có thể được gọi trực tiếp từ mạng nội bộ hoặc một route khác.

Với mọi cơ chế versioning, hãy bảo đảm:

- Gateway và backend parse version theo cùng quy tắc.
- Unknown version bị từ chối; không route về backend mặc định.
- Rewrite/strip prefix không làm thay đổi route sau authorization.
- Header version do client gửi được giữ nguyên hoặc chuẩn hóa có kiểm soát.
- Media type không bị proxy thay đổi mà backend không biết.
- OpenAPI document và schema đúng với version được route.
- Metric, log và trace ghi version đã chọn, không ghi credential.

Theo dõi số request theo version, client, endpoint, status và lỗi validation/authentication. Không dùng raw user ID hoặc token làm metric label. Dashboard cần phát hiện version cũ còn được sử dụng, lỗi tăng sau migration, route version không có traffic hoặc version bị gọi với permission bất thường.

## 12. Deprecation và sunset

Versioning chỉ hữu ích nếu có vòng đời rõ ràng. Khi một version sắp ngừng hỗ trợ, cần thông báo thời điểm deprecation, thời điểm sunset, client bị ảnh hưởng và đường nâng cấp.

Một kế hoạch deprecation nên có:

1. Xác định version và endpoint bị ảnh hưởng.
2. Công bố replacement version và tài liệu migration.
3. Thông báo cho owner/client đang sử dụng version cũ.
4. Theo dõi traffic theo client và endpoint để xác định mức độ chuyển đổi.
5. Có thời hạn hỗ trợ và ngày sunset rõ ràng.
6. Gửi cảnh báo qua response header hoặc kênh quản trị nếu hợp đồng hỗ trợ.
7. Chặn version cũ sau khi hoàn tất migration hoặc sớm hơn nếu có rủi ro bảo mật nghiêm trọng.

Có thể sử dụng các header như `Deprecation`, `Sunset` và `Link` theo quy ước hoặc chuẩn được áp dụng. Ví dụ minh họa:

```http
HTTP/1.1 200 OK
Deprecation: true
Sunset: Wed, 30 Jun 2027 23:59:59 GMT
Link: <https://api.example.test/docs/migrations/v1-to-v2>; rel="deprecation"
```

Header cụ thể và định dạng ngày phải tuân theo spec mà hệ thống chọn. Không gửi ngày sunset giả định hoặc thay đổi liên tục mà không thông báo. Client cần được hướng dẫn xử lý trước khi version bị tắt.

### 12.1. Không kéo dài version có lỗ hổng chỉ vì còn client

Nếu version cũ có lỗ hổng authorization, token validation yếu hoặc lộ dữ liệu, cần đánh giá việc vô hiệu hóa khẩn cấp. Có thể cung cấp migration path hoặc biện pháp giảm thiểu tạm thời, nhưng không nên để một version dễ bị khai thác tồn tại vô thời hạn chỉ vì một số client chưa nâng cấp.

## 13. Ví dụ cấu hình và kiểm thử

### 13.1. Định tuyến path version trong Spring

```java
@RestController
@RequestMapping("/api/v1/orders")
class OrdersV1Controller {
    @GetMapping("/{id}")
    OrderV1Response get(@PathVariable UUID id) {
        return orderService.getV1(id);
    }
}

@RestController
@RequestMapping("/api/v2/orders")
class OrdersV2Controller {
    @GetMapping("/{id}")
    OrderV2Response get(@PathVariable UUID id) {
        return orderService.getV2(id);
    }
}
```

Hai controller minh họa hai response contract. Authorization nên được đặt ở service hoặc method security dùng chung, hoặc được khai báo rõ trên cả hai controller và service. Không để v2 gọi một service method bỏ qua kiểm tra object/tenant chỉ vì response model khác.

### 13.2. Ma trận kiểm thử version

| Tình huống | Kết quả cần xác minh |
|---|---|
| Path version được hỗ trợ | Route tới đúng contract và policy |
| Header version hợp lệ | Chọn đúng contract; cache phân biệt theo header |
| Media type hợp lệ | Negotiation chọn đúng representation |
| Version thiếu khi bắt buộc | Bị từ chối hoặc dùng default đã công bố, không fallback ngầm |
| Version không hỗ trợ | Trả lỗi phù hợp, không route sang backend mặc định |
| Path v1 nhưng header v2 | Từ chối nếu hai nguồn mâu thuẫn |
| Header xuất hiện hai lần | Từ chối giá trị nhập nhằng |
| Accept có nhiều media type | Chọn theo negotiation rule đã công bố |
| Content-Type không hỗ trợ | `415 Unsupported Media Type` |
| Accept không có representation phù hợp | `406 Not Acceptable` |
| Token thiếu scope trên v2 | Bị từ chối; version không cấp thêm quyền |
| Cùng token gọi resource tenant khác qua v1/v2 | Object authorization vẫn từ chối |
| Cache nhận response v1 rồi request v2 | Không trả nhầm representation |
| Request signature không bao phủ version header | Test phát hiện version có thể bị thay đổi |
| Gateway rewrite path | Backend và gateway thống nhất version/route |
| Version cũ đã sunset | Bị chặn theo kế hoạch và có phản hồi hướng dẫn |

Nên có contract test cho từng version, authorization regression test, cache integration test và test routing qua gateway. Test một controller riêng lẻ không đủ để chứng minh request đi qua đúng route và đúng policy trong môi trường triển khai.

## 14. Checklist chọn và triển khai versioning

- [ ] Đã xác định thay đổi nào là breaking change và cần version mới.
- [ ] Mỗi API surface có một cơ chế version chính: path, header hoặc media type.
- [ ] Version được parse bằng allowlist và unknown version bị từ chối rõ ràng.
- [ ] Không có fallback ngầm hoặc version ambiguity giữa path/header/media type.
- [ ] Gateway, proxy và backend dùng cùng quy tắc normalization/routing.
- [ ] Authentication, audience, scope và function authorization không bị nới lỏng ở version mới.
- [ ] Object authorization, tenant isolation và property filtering được kiểm tra trên mọi version.
- [ ] Request signature bao phủ thành phần version ảnh hưởng cách diễn giải request.
- [ ] Cache key/Vary phân biệt representation theo version và không làm lộ response riêng tư.
- [ ] OpenAPI/schema, SDK và tài liệu được phát hành đúng version.
- [ ] Deprecation, sunset, migration owner và lịch hỗ trợ được công bố.
- [ ] Có test unknown version, downgrade, conflicting signals, cache, gateway và quyền truy cập.
- [ ] Có khả năng tắt version có lỗ hổng nghiêm trọng và theo dõi client còn sử dụng.

## 15. Nguyên tắc thiết kế

Path, header và media type đều có thể biểu diễn version hợp lệ. Path dễ quan sát và định tuyến; header giữ URI ổn định nhưng cần quản lý cache/CORS; media type phù hợp content negotiation nhưng đòi hỏi parser và gateway hỗ trợ đúng. Chọn một cách phù hợp với hệ sinh thái client và vận hành, sau đó công bố hợp đồng và quy tắc chuyển đổi rõ ràng.

Trong mọi trường hợp, version chỉ xác định contract được áp dụng. Nó không thay thế authentication, authorization, validation, tenant isolation hoặc output filtering. Gateway và backend phải thống nhất version đã chọn; cache và chữ ký phải ràng buộc với đúng representation; version cũ cần có deprecation/sunset và khả năng bị vô hiệu hóa khi có lỗ hổng. **Một API version an toàn là version có hợp đồng rõ ràng, được định tuyến nhất quán và chịu cùng chuẩn bảo mật nghiêm ngặt như mọi phiên bản khác.**
