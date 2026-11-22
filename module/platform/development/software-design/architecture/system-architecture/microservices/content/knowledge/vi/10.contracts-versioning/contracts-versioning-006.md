# Quản lý phiên bản API và vòng đời ngừng hỗ trợ

## 1. Vì sao API cần chiến lược phiên bản và ngừng hỗ trợ?

Trong hệ thống Microservices, API và event là **hợp đồng giữa các bên có thể triển khai độc lập**. Một producer có thể nâng cấp vào thứ Hai, trong khi một consumer vẫn dùng bản ứng dụng phát hành từ tháng trước, đối tác bên ngoài chỉ triển khai mỗi quý và ứng dụng di động có thể tồn tại nhiều năm trên thiết bị. Vì vậy thay đổi API không đơn thuần là sửa controller, DTO hay đường dẫn; nó ảnh hưởng đến **kỳ vọng về dữ liệu, hành vi, mã lỗi, bảo mật, hiệu năng và quy trình nghiệp vụ** của những hệ thống phụ thuộc.

Nếu thay đổi không tương thích mà không có kế hoạch, một bản triển khai của service có thể khiến consumer đang chạy gặp lỗi parse dữ liệu, hiểu sai trạng thái, tính tiền sai hoặc không biết phải retry hay dừng. Mặt khác, giữ mọi phiên bản mãi mãi làm tăng chi phí bảo trì, kiểm thử, bảo mật, lưu trữ và vận hành.

**Quản lý phiên bản API** là việc định nghĩa, công bố và kiểm soát sự tiến hóa của hợp đồng để producer và consumer có thể nâng cấp có chủ đích.

**Vòng đời ngừng hỗ trợ** là chuỗi hoạt động từ lúc thông báo một khả năng hoặc phiên bản sẽ không được khuyến khích dùng nữa, qua thời gian chuyển đổi, đến khi ngừng phục vụ hoặc chấm dứt cam kết hỗ trợ theo chính sách rõ ràng.

Cả hai phục vụ một mục tiêu: **cho phép thay đổi công nghệ và mô hình nghiệp vụ mà không biến mỗi lần phát hành thành sự kiện buộc mọi consumer cập nhật đồng thời**.

### 1.1. Những câu hỏi cần trả lời

- Phiên bản đang áp dụng cho **hợp đồng**, representation, route hay toàn bộ sản phẩm?
- Thay đổi nào tương thích với client cũ, thay đổi nào phá vỡ hành vi?
- Ai chịu trách nhiệm phê duyệt và công bố phiên bản?
- Consumer được nhận thông báo bằng kênh nào và có thời gian chuyển đổi bao lâu?
- Làm cách nào xác định những consumer còn sử dụng phiên bản cũ?
- Khi nào được đánh dấu deprecated, khi nào hết hạn hỗ trợ và khi nào thật sự tắt endpoint?
- Trong giai đoạn song song, dữ liệu và trạng thái được bảo toàn như thế nào?
- Phải làm gì nếu một consumer chưa thể nâng cấp trước ngày sunset?
- Tiêu chí và bằng chứng nào cho phép gỡ code, route, schema hoặc topic cũ?

### 1.2. Phân biệt các khái niệm

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Implementation version | Phiên bản build/deployment nội bộ | order-service 3.18.2 |
| API contract version | Phiên bản giao diện và hành vi mà consumer sử dụng | Order API v1, v2 |
| Schema version | Phiên bản cấu trúc payload/request/event | OrderCreated schema v3 |
| Resource version | Phiên bản trạng thái của một tài nguyên, phục vụ concurrency | ETag "order-1001-v7" |
| Consumer version | Phiên bản ứng dụng đang gọi API | mobile app 6.4 |
| Deprecation | Tính năng/phiên bản không còn được khuyến nghị cho tích hợp mới | API v1 deprecated |
| Sunset | Mốc dự kiến API/khả năng có thể không còn sẵn sàng | v1 dự kiến ngừng phục vụ |
| Retirement | Hoạt động ngừng phục vụ theo quyết định vận hành | Route v1 bị loại bỏ |
| End of support | Hết cam kết bảo trì/hỗ trợ theo chính sách | Không còn nhận thay đổi thường lệ cho v1 |

**Phiên bản API không nhất thiết bằng phiên bản ứng dụng triển khai.** Order Service có thể phát hành hàng chục lần mà vẫn giữ hợp đồng API v1 tương thích. Ngược lại, một deployment có thể phục vụ v1 và v2 đồng thời.

**Deprecation không đồng nghĩa xóa ngay.** Một endpoint có thể bị đánh dấu không dùng cho tích hợp mới nhưng vẫn hoạt động trong một giai đoạn chuyển đổi. **Sunset** là tín hiệu về thời điểm có thể chấm dứt khả năng sử dụng; **retirement** là hành động loại bỏ thực tế.

## 2. API contract bao gồm những gì?

Hợp đồng API không chỉ là OpenAPI schema hoặc file JSON. Nó bao gồm tất cả những điều consumer được phép dựa vào:

1. **Cách truy cập:** hostname, URI, HTTP method, header, query parameter, media type và cơ chế xác thực.
2. **Cấu trúc dữ liệu:** field, kiểu dữ liệu, required/optional, nullability, enum, ID, định dạng tiền và ngày giờ.
3. **Ngữ nghĩa nghiệp vụ:** ý nghĩa của status, điều kiện chuyển trạng thái, giới hạn số lượng, cách xử lý đồng thời.
4. **Phản hồi HTTP:** mã trạng thái, response header, error code, pagination, cache validator, idempotency.
5. **Cam kết giao tiếp:** timeout, rate limit, retry behavior, tính nhất quán và tính sẵn sàng nếu được công bố.
6. **Quyền truy cập:** scope/permission, tenant boundary, cách ẩn tài nguyên không được phép xem.
7. **Chính sách vận hành:** phiên bản nào được hỗ trợ, thời gian thông báo, lộ trình deprecation và đầu mối hỗ trợ.

Ví dụ, giữ nguyên endpoint **GET /orders/{id}** và kiểu field **status: string** nhưng đổi ý nghĩa **CONFIRMED** từ “đơn đã được chấp nhận” sang “tiền đã được thu” là thay đổi phá vỡ hợp đồng **về ngữ nghĩa**, dù JSON không hề thay đổi.

Tương tự, đổi **amount** từ đơn vị VND sang đơn vị nghìn VND mà không đổi tên/contract cũng là thay đổi nguy hiểm dù cùng kiểu number.

### 2.1. Hợp đồng phải được xác minh bằng hành vi

Một OpenAPI document có thể mô tả rằng **status** là chuỗi nhưng không đủ chỉ rõ các trạng thái hợp lệ hay quá trình chuyển trạng thái. Với API quan trọng, cần thêm:

- Ví dụ nghiệp vụ thành công/thất bại.
- Ma trận trạng thái và điều kiện cho phép chuyển.
- Quy tắc idempotency và cách xử lý timeout.
- Những error code mà client có thể xử lý bằng logic.
- Contract/integration tests, nhất là các trường hợp phá vỡ dữ liệu hoặc tiền.

Nói cách khác, **schema là một phần của contract, không phải toàn bộ contract**.

## 3. Tương thích ngược, tương thích tiến và tương thích về nghĩa

### 3.1. Backward compatibility

Một thay đổi **backward compatible** khi các consumer đang hoạt động theo hợp đồng cũ vẫn tiếp tục hoạt động đúng kỳ vọng sau khi producer được nâng cấp, trong phạm vi cam kết đã công bố.

Ví dụ producer bổ sung một field response **estimatedDeliveryAt** tùy chọn và các client cũ vốn bỏ qua field không biết vẫn đọc đơn như trước. Điều đó có thể tương thích với client cũ.

Nhưng nếu client cũ dùng deserializer nghiêm ngặt từ chối mọi field lạ, thay đổi này vẫn có thể gây lỗi. Do đó tương thích cần được xét với **consumer thực tế**, không chỉ dựa trên nguyên tắc lý thuyết.

### 3.2. Forward compatibility

Một consumer được thiết kế **forward compatible** khi có thể xử lý hợp lý dữ liệu từ producer tương lai trong một số thay đổi dự kiến. Ví dụ consumer không crash khi gặp một field không biết, có nhánh xử lý **UNKNOWN** cho enum trạng thái và không giả định tập enum vĩnh viễn đóng.

Không thể bảo đảm mọi thay đổi tương lai đều tương thích. Nếu quy tắc tiền thay đổi nghĩa, một parser linh hoạt không tự bảo vệ được business logic.

### 3.3. Tương thích cú pháp và ngữ nghĩa

| Thay đổi | Khả năng ảnh hưởng | Điểm cần xác minh |
| --- | --- | --- |
| Thêm field response optional | Thường dễ tương thích | Client có bỏ qua field lạ không? |
| Bỏ một field response đang dùng | Thường breaking | Consumer nào còn dùng field? |
| Đổi tên field | Breaking nếu chưa hỗ trợ tên cũ | Có alias/chuyển đổi tạm thời không? |
| Đổi string thành number | Thường breaking | Parser, ID và độ chính xác |
| Đổi đơn vị tiền | Breaking về nghĩa | Currency, scale, phép tính |
| Thêm giá trị enum | Có thể breaking | Client dùng exhaustive switch có nhánh unknown không? |
| Đổi required input | Thường breaking | Consumer cũ có gửi đủ dữ liệu không? |
| Thêm optional input | Thường dễ tương thích | Giá trị mặc định có đổi hành vi cũ không? |
| Đổi HTTP status code | Có thể breaking | Client có logic theo status không? |
| Đổi error code | Có thể breaking | Retry/hiển thị/alert dựa vào code không? |
| Đổi pagination default | Có thể breaking về hành vi | Client có giả định thứ tự/số lượng không? |
| Đổi từ xử lý đồng bộ sang 202 | Có thể breaking | Client có biết poll operation không? |
| Siết quyền truy cập | Có thể breaking | Client hợp lệ cần scope mới nào? |
| Giảm rate limit | Có thể breaking về vận hành | Burst và retry hiện tại có còn phù hợp? |

**Tương thích là một thuộc tính của quan hệ producer–consumer trong một khoảng thời gian**, không phải chỉ của một bản diff giữa hai file JSON.

### 3.4. Contract và implementation có vòng đời khác nhau

Một refactor từ Spring MVC sang WebFlux, đổi database hay chuyển deployment sang Kubernetes không tự đòi API v2 nếu contract không đổi. Ngược lại, một thay đổi nhỏ trong code có thể tạo breaking change nếu đổi ngữ nghĩa field.

Không dùng số phiên bản deployment để suy ra API compatibility. Client chỉ nên phụ thuộc những điều nằm trong hợp đồng đã công bố.

## 4. Thế nào là breaking change?

**Breaking change** là thay đổi khiến một consumer hợp lệ theo hợp đồng đang hỗ trợ có nguy cơ lỗi hoặc cho kết quả nghiệp vụ sai nếu không được sửa.

### 4.1. Breaking ở request

- Xóa hoặc đổi tên endpoint.
- Đổi method, ví dụ từ GET sang POST mà không duy trì phương thức cũ.
- Biến query/body field trước đây optional thành required.
- Đổi type, format, default value hoặc cách diễn giải field.
- Giới hạn những giá trị từng hợp lệ.
- Đổi cơ chế xác thực/authorization mà consumer hiện không đáp ứng.
- Thay đổi idempotency key format hoặc phạm vi hiệu lực một cách không tương thích.

### 4.2. Breaking ở response

- Xóa hoặc đổi tên field đang công bố.
- Đổi field từ bắt buộc thành có thể không xuất hiện mà không có lộ trình.
- Đổi type, nullability hoặc đơn vị.
- Đổi mã HTTP hoặc response body theo cách client không dự kiến.
- Đổi ý nghĩa trạng thái hoặc error code.
- Đổi thứ tự mặc định của danh sách mà client dựa vào.
- Thêm trạng thái nghiệp vụ mà client chưa biết xử lý.
- Giảm tính nhất quán hoặc thời gian chờ vượt mức cam kết.

### 4.3. Breaking ngoài schema

Một thay đổi từ **201 Created** với Location tới **202 Accepted** với operation resource có thể là thay đổi contract lớn: client cũ tưởng đã tạo xong tài nguyên, nhưng thực chất kết quả còn đang chờ.

Tương tự, một endpoint thanh toán trước đây trả kết quả cuối trong 3 giây nhưng giờ chỉ trả trạng thái **PENDING** có thể buộc client thay đổi cách hiển thị và đối soát.

**Không dùng quy tắc “JSON parse được nên không breaking”**. Cần hỏi: *một consumer cũ đang tuân thủ hợp đồng liệu còn thực hiện đúng quyết định nghiệp vụ sau thay đổi này không?*

## 5. Khi nào cần tạo API version mới?

Không phải mọi thay đổi đều cần thêm v2. Việc tạo version mới tăng thêm bề mặt phải bảo trì, tài liệu, kiểm thử và giám sát.

Một hướng quyết định:

~~~text
Thay đổi dự kiến
       |
       v
Có phá vỡ consumer hợp lệ hiện tại?
       |
       +-- Không --> Triển khai tương thích trên contract hiện có
       |             + kiểm thử các consumer quan trọng
       |
       +-- Có --> Có thể hỗ trợ cả nghĩa cũ và mới tạm thời?
                       |
                       +-- Có --> Expand -> Migrate -> Contract
                       |
                       +-- Không hoặc ngữ nghĩa tách rõ
                                  |
                                  v
                          Đề xuất version mới
                          + thời gian hỗ trợ song song
                          + migration guide
                          + deprecation plan
~~~

**Tạo version mới phù hợp khi** có thay đổi ngữ nghĩa lớn, mô hình domain được phân tách lại, cấu trúc request/response không thể cùng thỏa hai nhóm consumer hoặc chiến lược bảo mật/hành vi buộc thay đổi có kiểm soát.

**Không nhất thiết cần version mới khi** chỉ thêm field optional, bổ sung endpoint mới, sửa hiệu năng mà không đổi contract hoặc sửa bug để API hoạt động đúng như hợp đồng vốn đã mô tả.

Tuy nhiên một sửa bug có thể ảnh hưởng consumer đang vô tình phụ thuộc hành vi sai cũ. Khi đó cần cân nhắc rủi ro vận hành và biện pháp chuyển tiếp, dù về mặt đặc tả việc sửa là đúng.

## 6. Chiến lược đặt phiên bản REST API

Không có một cú pháp versioning phù hợp cho mọi sản phẩm. Cần chọn và giữ nhất quán trong phạm vi API family.

### 6.1. Phiên bản trong URL path

~~~http
GET /v1/orders/ORD-1001 HTTP/1.1
~~~

~~~http
GET /v2/orders/ORD-1001 HTTP/1.1
~~~

**Ưu điểm:**

- Dễ nhận biết, định tuyến và quan sát.
- Tài liệu, ví dụ và cache routing tương đối rõ.
- Đối tác có thể khai báo URL v1/v2 độc lập.

**Nhược điểm:**

- Nhân số lượng route/hợp đồng cần duy trì.
- Dễ tạo mã nguồn trùng lặp nếu mỗi version sao chép toàn bộ service.
- Phiên bản xuất hiện trong URI tài nguyên, cần chính sách liên kết và chuyển hướng thận trọng.

Không tự động nhân bản database hoặc deployment cho mỗi URL version. Hai version có thể là hai adapter representation trên cùng domain model, khi điều đó an toàn.

### 6.2. Versioning qua media type / Accept

Ví dụ minh họa:

~~~http
GET /orders/ORD-1001 HTTP/1.1
Accept: application/vnd.example.order-v2+json
~~~

API trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/vnd.example.order-v2+json
Vary: Accept
~~~

**Ưu điểm:** cùng URI định danh tài nguyên, version nằm ở representation được yêu cầu.

**Đổi lại:** cấu hình client, caching và observability phải xem xét header; tài liệu cần giải thích media type; không phải mọi công cụ/đội đều thấy phương án này dễ sử dụng.

### 6.3. Versioning qua header riêng

Ví dụ một hợp đồng nội bộ có thể định nghĩa:

~~~http
GET /orders/ORD-1001 HTTP/1.1
X-Api-Version: 2
~~~

Đây là **quy ước riêng do nhà cung cấp API định nghĩa**, không phải ngữ nghĩa HTTP chuẩn cho mọi API. Khi sử dụng, phải thống nhất cache variation, gateway routing, kiểm thử, fallback khi thiếu header và cách xác thực version.

### 6.4. Versioning qua query parameter

~~~http
GET /orders/ORD-1001?api-version=2 HTTP/1.1
~~~

Dễ thử nghiệm nhưng trộn version selection với query biểu diễn, khiến URI, cache và tài liệu cần kiểm soát chặt. Có thể phù hợp một số hệ thống, nhưng không nên tự ý thêm vào từng endpoint thiếu nhất quán.

### 6.5. Phiên bản theo ngày

Một số API công bố phiên bản theo ngày hoặc giai đoạn, ví dụ **2026-11-11**, thay vì v1/v2. Mô hình này có thể hữu ích nếu mỗi ngày phiên bản là một điểm chốt behavior/schema, nhưng phải quy định cách chọn và các mốc được hỗ trợ; không suy ra mọi ngày đều hợp lệ.

### 6.6. So sánh lựa chọn

| Phương án | Dễ thấy trong log/URL | Có thể giữ URI tài nguyên | Điều kiện áp dụng |
| --- | --- | --- | --- |
| Path /v1, /v2 | Cao | Không hoàn toàn | Public API, công cụ routing đơn giản |
| Media type Accept | Trung bình | Có | API chú trọng representation và content negotiation |
| Custom header | Trung bình | Có | Có quản trị gateway/client rõ |
| Query parameter | Cao trong URL | URI thay đổi theo query | Hệ thống đã có quy ước nhất quán |
| Version không công bố khi additive | Không có version token mới | Có | Contract tiến hóa tương thích, consumer được thiết kế linh hoạt |

Điều quan trọng hơn cú pháp là **định nghĩa version, phạm vi hỗ trợ, tương thích, tài liệu và lộ trình chuyển đổi**.

## 7. Semantic Versioning có vai trò gì?

Semantic Versioning (SemVer) thường dùng cấu trúc **MAJOR.MINOR.PATCH**, trong đó major biểu thị thay đổi không tương thích theo public API đã định nghĩa của một phần mềm. Nó hữu ích cho thư viện, SDK hoặc các hợp đồng được tổ chức lựa chọn quản trị bằng quy tắc này.

Tuy nhiên:

- **Không mặc định REST API bắt buộc sử dụng SemVer.** Một API có thể dùng v1/v2 hoặc phiên bản theo ngày.
- **Không đồng nhất phiên bản OpenAPI document với phiên bản runtime.** Trường info.version có thể đánh dấu phiên bản tài liệu/hợp đồng theo quy ước của nhóm.
- **Không coi tăng minor luôn an toàn cho mọi consumer** nếu những consumer đó không xử lý field/enum mới theo hợp đồng.
- **Không tạo major version mới cho mỗi lần deploy** khi chỉ có thay đổi cài đặt.

Nếu tổ chức dùng SemVer cho contract, nên ghi rõ: thay đổi nào được xếp PATCH/MINOR/MAJOR, trường hợp ngoại lệ ra sao và ai duyệt. Ngữ nghĩa business vẫn phải được xem xét riêng.

## 8. Tương thích giữa phiên bản producer và consumer

Microservices phát hành độc lập nên trong production có thể đồng thời tồn tại producer mới/consumer cũ và producer cũ/consumer mới.

### 8.1. Ma trận tương thích

| Producer | Consumer | Điều cần xác minh |
| --- | --- | --- |
| v1 | v1 | Baseline contract |
| v2 | v1 | Consumer cũ có đọc và hiểu kết quả mới đúng không? |
| v1 | v2 | Consumer mới có hoạt động khi producer chưa nâng cấp không? |
| v2 | v2 | Hành vi mới được áp dụng đầy đủ chưa? |

Không phải lúc nào cả bốn tổ hợp đều bắt buộc, nhưng **thứ tự triển khai** phải dựa trên ma trận đã công bố.

Một quy tắc thực hành: **mở rộng khả năng của producer trước khi consumer bắt buộc dùng khả năng mới**, sau đó dần chuyển consumer và cuối cùng loại bỏ tương thích cũ. Nếu cần consumer nâng trước, phải đảm bảo nó còn xử lý được dữ liệu/hợp đồng cũ.

### 8.2. Consumer-driven contract testing

Mỗi consumer quan trọng có thể công bố những kỳ vọng thực sự cần từ provider, ví dụ:

- GET Order trả ID và trạng thái có ý nghĩa đã định.
- PaymentCreated có amount/currency đúng đơn vị.
- API trả 409 cho trạng thái cấm chuyển.
- Retry cùng idempotency key không tạo giao dịch thứ hai.

Producer xác minh kỳ vọng đó trong CI/CD trước khi phát hành. Công cụ contract testing có thể hỗ trợ, nhưng **bài kiểm thử và ý nghĩa dữ liệu mới là phần cần tin cậy**.

### 8.3. Unknown fields và unknown enum values

Một consumer có thể bỏ qua field response không dùng, nhưng không nên bỏ qua giá trị enum không biết nếu điều đó dẫn đến quyết định nguy hiểm.

Ví dụ trạng thái thanh toán mới **REQUIRES_REVIEW** không thể được hiểu mặc định như **PAID**. Với logic nghiệp vụ quan trọng, nên có chiến lược **UNKNOWN / NEEDS_RECONCILIATION**, không tự coi giá trị lạ là trạng thái thành công.

## 9. Phiên bản tài nguyên, dữ liệu và hành vi nghiệp vụ

Versioning chỉ có ý nghĩa khi phạm vi được giải thích.

### 9.1. URI và resource identity

Một tài nguyên Order với ID **ORD-1001** có thể được biểu diễn bởi API v1 và v2:

~~~text
GET /v1/orders/ORD-1001
GET /v2/orders/ORD-1001
~~~

Hai URI có thể truy xuất **cùng một thực thể nghiệp vụ** nhưng representation khác nhau. Không nên tự tạo hai đơn hàng vật lý khác nhau chỉ vì người dùng gọi hai version.

### 9.2. API version khác ETag/resource version

**ETag** hoặc trường **version** của một Order thường dùng để kiểm soát cập nhật cạnh tranh. Nó tăng khi trạng thái tài nguyên thay đổi, **không phải khi API chuyển từ v1 sang v2**.

Ví dụ:

~~~http
GET /v2/orders/ORD-1001
ETag: "order-1001-state-9"
~~~

Một request PATCH với **If-Match** có thể thất bại vì state version thay đổi, dù cả producer và consumer đều đang ở API v2.

### 9.3. Dữ liệu được lưu chung có thể phục vụ nhiều contract

Service có thể giữ một domain model chính rồi map thành **OrderV1Response** và **OrderV2Response**. Các adapter này nên rõ ràng, có tests cho cách chuyển đổi.

Không mặc định **v1 = database v1** và **v2 = database v2**. Version hóa database vật lý theo mỗi API route có thể tạo hai nguồn sự thật nếu không có thiết kế chuyển đổi/phối hợp.

## 10. Thiết kế vòng đời API rõ ràng

Một chính sách vòng đời nên có các trạng thái riêng:

| Trạng thái | Ý nghĩa | Hành động mong đợi |
| --- | --- | --- |
| Proposed / Preview | Đang xem xét, có thể thay đổi | Không áp cam kết production như bản ổn định |
| Active / Supported | Được khuyến nghị sử dụng và hỗ trợ | Có tài liệu, kiểm thử, SLO phù hợp |
| Deprecated | Vẫn có thể hoạt động nhưng không nên chọn cho tích hợp mới | Thông báo, công bố phương án thay thế |
| Sunset Scheduled | Có mốc dự kiến chấm dứt khả dụng | Migration guide, lịch và cảnh báo tới consumer |
| End of Support | Hết hỗ trợ theo định nghĩa chính sách | Làm rõ lỗi bảo mật/sự cố có còn được xử lý không |
| Retired / Removed | Không còn được phục vụ | Route/handler cũ đã loại bỏ theo kế hoạch |

Không nhất thiết mọi tổ chức dùng đúng các trạng thái này; cần thống nhất nghĩa và điều kiện chuyển giữa chúng.

**Deprecation** là chính sách/lời khuyến cáo, **sunset** là mốc thời gian dự kiến và **retirement** là kết quả triển khai thực tế. Có thể công bố deprecation trước khi biết ngày sunset, nhưng nếu còn client quan trọng thì kế hoạch migration cần được xác định trước khi gỡ.

### 10.1. Ví dụ timeline minh họa

Giả sử Order API v2 có những thay đổi không tương thích cần giới thiệu:

| Mốc ví dụ | Trạng thái v1 | Hoạt động |
| --- | --- | --- |
| 01/12/2026 | Supported | Công bố v2, tài liệu và SDK |
| 15/01/2027 | Deprecated | Thông báo không tiếp nhận tích hợp mới vào v1 |
| 01/03/2027 | Sunset Scheduled | Công bố lịch dự kiến v1 ngừng phục vụ, gửi thông báo trực tiếp |
| 01/06/2027 | Migration deadline | Consumer cần hoàn thành chuyển đổi hoặc có ngoại lệ được phê duyệt |
| 01/07/2027 | Retired nếu đủ điều kiện | Loại bỏ route v1 theo kế hoạch đã duyệt |

**Các ngày trên chỉ là ví dụ**, không phải thời hạn tiêu chuẩn cho mọi API. Thời gian thông báo cần dựa trên hợp đồng đối tác, tốc độ release của client, app mobile, dữ liệu thực tế và mức rủi ro nghiệp vụ.

### 10.2. Chính sách không nên chỉ là một ngày trên lịch

Một ngày ngừng hỗ trợ không đủ nếu chưa có **bằng chứng về consumer** và khả năng hỗ trợ chuyển đổi. Trước retirement, cần nắm:

- Những client/đối tác nào đang gọi v1.
- Mức sử dụng trong các chu kỳ nghiệp vụ, kể cả job chạy cuối tháng/cuối quý.
- Các migration blocker còn mở.
- Có hay không phần dữ liệu nghiệp vụ chỉ client v1 hiểu.
- Đã thông báo và xác nhận với consumer theo chính sách chưa.
- Có rollback hoặc kế hoạch gia hạn có kiểm soát nếu retirement gây ảnh hưởng lớn không.

## 11. Công bố Deprecation và Sunset qua tài liệu và HTTP

Việc một phiên bản bị deprecated phải **dễ phát hiện bằng con người và công cụ**, không chỉ nằm trong một cuộc họp nội bộ.

### 11.1. Nơi cần thông báo

- Developer portal và trang API reference.
- Changelog/release notes.
- Migration guide giữa hai version.
- Email/thông báo trực tiếp cho chủ sở hữu tích hợp, nếu có.
- Dashboard mức sử dụng và trạng thái phiên bản.
- Response header hoặc metadata thích hợp.
- SDK documentation, deprecation annotation và lời cảnh báo trong các công cụ hỗ trợ khi phù hợp.

Một thông báo tốt phải nói rõ **cái gì deprecated, vì sao, thay bằng gì, việc cần làm, thời hạn, tác động nếu không làm và kênh nhận hỗ trợ**.

### 11.2. Header Deprecation và Sunset

Hệ sinh thái HTTP có những tín hiệu được chuẩn hóa để thông báo deprecation/sunset. Cần tuân thủ định dạng theo đặc tả tương ứng và hỗ trợ của gateway/framework.

Ví dụ minh họa response cho một API v1:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Deprecation: @1798761600
Sunset: Thu, 01 Jul 2027 00:00:00 GMT
Link: <https://api.example.com/docs/migrate-orders-v2>; rel="deprecation"
~~~

Trong ví dụ, giá trị **Deprecation** được thể hiện theo dạng ngày cấu trúc, **Sunset** theo HTTP-date, và **Link** dẫn tới tài liệu chuyển đổi. Các giá trị phải được tạo **đúng mốc thực tế đã công bố**; không sao chép timestamp minh họa này vào production. Các header không thay thế thông báo cho consumer quan trọng.

Khi áp dụng tại API Gateway, chú ý header chỉ xuất hiện ở route/version thật sự deprecated, không gắn nhầm lên toàn bộ traffic v2. Nếu CDN/proxy cache response, phải xem xét việc header được cập nhật và phân phối đúng mốc.

### 11.3. Trước và sau mốc sunset

Trước sunset, v1 vẫn có thể phục vụ đúng contract trong thời gian đã cam kết. Sau retirement, nếu một URI không còn tài nguyên hoặc khả năng phục vụ, server có thể trả **404 Not Found** hoặc **410 Gone** nếu biết tài nguyên/khả năng đó đã bị loại bỏ vĩnh viễn, tùy thiết kế và chính sách API.

**Không mặc định “đến ngày sunset thì mọi request phải trả 410”.** Hành vi thực tế, redirect nếu có, tài liệu và quyền hỗ trợ cần được quyết định trước để không tạo chuyển hướng sai hoặc che giấu lỗi quan trọng.

### 11.4. Khi mốc thay đổi

Nếu cần gia hạn, cập nhật header, tài liệu, thông báo và kế hoạch vận hành thống nhất. Không để response công bố một ngày, developer portal công bố ngày khác và hệ thống ticket giữ ngày thứ ba.

## 12. Chọn chính sách hỗ trợ và thời gian chuyển đổi

Thời gian support không nên chỉ do đội API quyết định theo mong muốn giảm chi phí.

### 12.1. Những yếu tố ảnh hưởng

1. **Loại consumer:** microservice nội bộ triển khai liên tục, đối tác B2B triển khai theo quý, mobile app cập nhật không đồng đều.
2. **Mức độ breaking:** chỉ đổi tên field hay thay đổi hoàn toàn vòng đời thanh toán?
3. **Tác động nghiệp vụ:** có rủi ro mất đơn, thu tiền nhầm, mất khả năng đối soát hay chỉ thay đổi một màn hình?
4. **Phụ thuộc pháp lý/hợp đồng:** thời gian thông báo, lưu trữ dữ liệu, kiểm toán và thỏa thuận với đối tác.
5. **Khả năng song song:** có adapter để v1/v2 cùng chạy mà không tạo hai nguồn sự thật không?
6. **Chi phí vận hành:** vá lỗi bảo mật, số pipeline, logging, test matrix, quan sát và on-call.
7. **Chu kỳ dữ liệu:** có job chạy cuối tháng/cuối năm hoặc consumer xử lý theo mùa không?

### 12.2. Quy tắc nội bộ minh họa

Một tổ chức có thể chọn các mức:

- **Non-breaking update:** phát hành theo quy trình thông thường, changelog rõ.
- **Breaking change của internal API:** công bố v2, kiểm tra consumer registry và phối hợp trong một số sprint.
- **Breaking change của public API:** giai đoạn hỗ trợ song song dài hơn, migration guide, thông báo theo hợp đồng và dashboard theo đối tác.
- **Emergency security retirement:** quy trình ngoại lệ có đánh giá rủi ro và thông báo khẩn, có thể rút thời hạn khi cần bảo vệ hệ thống.

Đây là **mô hình chính sách cần nội bộ phê duyệt**, không phải SLA mặc định áp dụng ở mọi tổ chức.

### 12.3. Không duy trì vô hạn mặc định

Một service có thể tạm phục vụ v1/v2 song song, nhưng mỗi version phải có **owner, chính sách bảo mật, tiêu chí loại bỏ và thời điểm xem lại**. Nếu v1 được giữ vô thời hạn chỉ vì không ai biết ai đang sử dụng, vấn đề gốc là thiếu inventory và telemetry, không phải chính sách versioning.

## 13. Inventory consumer: biết ai còn dùng phiên bản cũ

Không thể retirement an toàn nếu chỉ nhìn code của producer. Cần biết các bên tiêu thụ thực tế, bao gồm consumer ít hoạt động nhưng quan trọng.

### 13.1. Consumer registry

Một bản ghi có thể chứa:

| Trường | Ý nghĩa |
| --- | --- |
| Consumer ID | Định danh ứng dụng hoặc tích hợp |
| Owner | Nhóm/người chịu trách nhiệm và kênh liên hệ |
| API family/version | Phiên bản thực sự sử dụng |
| Environment | Production, staging, partner sandbox |
| Authentication identity | Client ID hoặc service identity đã ẩn thông tin nhạy cảm |
| Endpoint usage | Route/method nào đang dùng |
| Last seen | Lần gọi thành công gần nhất |
| Request volume | Lưu lượng và chu kỳ hoạt động |
| Migration plan | Version đích, blocker, người chịu trách nhiệm |
| Deadline/status | Mốc đã cam kết và tình trạng thực tế |
| Exception | Có gia hạn được phê duyệt hay không |

Registry cần kết hợp **khai báo ownership** với **telemetry từ gateway/service**, vì tài liệu tự khai thường lỗi thời.

### 13.2. Dữ liệu usage cần thu

- Requests theo **version + client identity + route + method**.
- Consumer nào còn gọi endpoint deprecated.
- Lần cuối sử dụng trong các chu kỳ nghiệp vụ khác nhau.
- Lỗi 4xx/5xx sau khi chuyển version.
- Retry và timeout có tăng khi consumer thử v2 không.
- Bản mobile app/SDK đang gọi một contract cũ.
- Job batch hoặc luồng đối soát chỉ chạy theo kỳ.

Cần kiểm soát bảo mật và quyền riêng tư khi logging; không lưu token, secret hoặc payload nhạy cảm chỉ để biết ai gọi v1.

### 13.3. Không coi “bảy ngày không thấy traffic” là không có consumer

Một tác vụ xuất báo cáo có thể chạy cuối tháng hoặc một đối tác chỉ gọi khi có khiếu nại. Trước khi tắt, cần cân nhắc mùa vụ, lịch batch, client ít dùng và các chức năng khẩn cấp.

Nếu chưa có đủ telemetry, có thể thêm giai đoạn cảnh báo/chặn thử có kiểm soát trong môi trường phù hợp hoặc liên hệ chủ sở hữu để xác nhận. Không tắt production rồi xem ai báo lỗi làm phương pháp khám phá consumer mặc định.

## 14. Quy trình Expand–Migrate–Contract cho REST API

**Expand–Migrate–Contract** là cách thay đổi có giai đoạn để producer và consumer không buộc triển khai cùng lúc.

### 14.1. Ví dụ đổi amount sang money object

Giả sử Order API v1 trả:

~~~json
{
  "id": "ORD-1001",
  "status": "CONFIRMED",
  "totalAmount": 350000
}
~~~

Giá trị **totalAmount** được ngầm hiểu là VND, không có currency.

API v2 muốn hỗ trợ nhiều đồng tiền:

~~~json
{
  "id": "ORD-1001",
  "status": "CONFIRMED",
  "total": {
    "amount": "350000",
    "currency": "VND"
  }
}
~~~

**Đây là thay đổi breaking** nếu xóa trường **totalAmount** ngay, vì client v1 không biết đọc **total.amount**.

### 14.2. Bước Expand

Producer mở rộng mô hình để có thể phục vụ v1 và v2, hoặc tạm bổ sung trường mới trong representation tương thích theo chính sách:

~~~json
{
  "id": "ORD-1001",
  "status": "CONFIRMED",
  "totalAmount": 350000,
  "total": {
    "amount": "350000",
    "currency": "VND"
  }
}
~~~

Nếu hợp đồng v1 cho phép field mới, response trên có thể là bước chuyển tiếp. Tuy nhiên nếu đơn hàng bắt đầu hỗ trợ nhiều currency, **totalAmount không còn ý nghĩa ngầm VND cho mọi đơn**. Khi đó cần giới hạn phạm vi hoặc cung cấp representation v1 có điều kiện tương thích, tránh tạo giá trị v1 sai về nghiệp vụ.

### 14.3. Bước Migrate

- Cập nhật OpenAPI v2 và migration guide.
- Consumer mới đọc **total.amount + total.currency**.
- Consumer cũ tiếp tục đọc **totalAmount** trong phạm vi hợp đồng còn hợp lệ.
- Chạy consumer-driven contract tests.
- Theo dõi usage theo version/field nếu có thể.
- Di chuyển SDK, job batch, dashboard và tích hợp đối tác.
- Chặn tích hợp mới vào v1 theo chính sách deprecated.

Nếu muốn chuyển đường dẫn:

~~~text
GET /v1/orders/ORD-1001
GET /v2/orders/ORD-1001
~~~

Cả hai có thể đọc cùng dữ liệu nguồn sự thật và map representation riêng. Không cần nhân đôi Order trong DB.

### 14.4. Bước Contract

Khi consumer cũ đã chuyển, dữ liệu được đối soát và thời hạn hỗ trợ đã kết thúc:

1. Ngừng tiếp nhận contract mới v1.
2. Đánh dấu deprecated/sunset rõ ràng.
3. Gỡ tuyến xử lý v1 và adapter chỉ còn phục vụ v1, theo một đợt retirement có giám sát.
4. Loại bỏ field/schema cũ trong domain hoặc persistence **nếu không còn phụ thuộc khác**.
5. Cập nhật tài liệu, SDK, dashboard, consumer inventory và ADR.

**Không xóa field database chỉ vì API v1 ngừng chạy.** Có thể còn ETL, báo cáo hoặc consumer dữ liệu khác cần migration riêng.

## 15. Thay đổi hợp đồng có dữ liệu ghi: tránh dual write nguy hiểm

Chuyển API request từ v1 sang v2 không chỉ là mapping nếu phiên bản mới thay đổi quyền sở hữu hoặc giao dịch.

### 15.1. Hai API version cùng cập nhật một thực thể

Nếu **PUT /v1/orders/{id}** và **PATCH /v2/orders/{id}** đều sửa Order, cần cùng đi qua các bất biến của Order domain. Không tạo hai luồng business logic độc lập dẫn tới trạng thái khác nhau.

Một kiến trúc hợp lý:

~~~text
V1 HTTP Adapter ----\
                     \
                      --> Order Application Service
                     /         |
V2 HTTP Adapter ----/          v
                         Domain invariants
                                |
                                v
                          Order data store
~~~

Các adapter xử lý contract/representation khác nhau. Quyền quyết định nghiệp vụ nằm ở application/domain layer chung khi cùng bounded context.

### 15.2. Dữ liệu mới không biểu diễn được ở v1

Nếu v2 thêm một trạng thái hoặc loại sản phẩm mà v1 hoàn toàn không hiểu, không cố map giả thành một trạng thái cũ có nghĩa khác. Có thể:

- Giữ API v1 chỉ cho tập nghiệp vụ còn tương thích.
- Trả một lỗi có hợp đồng rõ khi tài nguyên không thể biểu diễn an toàn ở v1.
- Cung cấp một trường hợp “UNKNOWN” nếu v1 đã dự liệu.
- Yêu cầu consumer nâng cấp trước khi dùng khả năng mới.

Lựa chọn nào cũng phải được công bố và kiểm thử với các consumer quan trọng.

### 15.3. Versioning không thay thế data migration

Khi thay đổi database, nên có trình tự schema **expand → backfill → switch reads/writes → contract** phù hợp. Consumer API v1/v2 không nhất thiết biết bước migration nội bộ này, nhưng thời điểm chuyển phải tránh mất dữ liệu và phá bất biến.

Nếu thay đổi bao gồm chuyển source of truth sang service khác, cần thêm ownership handoff, idempotency, outbox/inbox và reconciliation. Phiên bản API chỉ là một phần bề mặt của thay đổi.

## 16. Quản lý những thay đổi ngữ nghĩa khó phát hiện

Một số thay đổi “cùng shape” nhưng làm consumer sai.

### 16.1. Trạng thái và enum

**Ví dụ:** v1 có **PENDING**, **CONFIRMED**, **CANCELLED**. V2 thêm **UNDER_REVIEW**.

Nếu một consumer dùng switch exhaustiveness và gặp giá trị mới, có thể crash. Nguy hiểm hơn, nếu mặc định coi mọi giá trị ngoài CANCELLED là CONFIRMED, ứng dụng có thể giao hàng trước khi duyệt.

Một quy tắc tốt: **công bố enum có mở rộng được hay không**; client có nhánh unknown an toàn, và business logic quan trọng không suy luận thành công từ giá trị chưa biết.

### 16.2. Tiền và độ chính xác

Đổi **amount: 10000** từ đơn vị VND sang cent hoặc đổi kiểu **number** sang decimal string có thể phá client. Luôn có currency và quy ước scale/range rõ, kiểm thử tổng tiền, giảm giá, hoàn tiền và các tình huống rounding.

Không dùng JSON floating point không kiểm soát cho giá trị tài chính cần chính xác; API có thể chọn integer minor units hoặc decimal string với quy tắc công bố rõ.

### 16.3. Ngày giờ, timezone và lịch

Đổi từ ngày kinh doanh theo múi giờ địa phương sang UTC timestamp có thể khiến báo cáo cuối ngày sai lệch dù JSON hợp lệ. Cần phân biệt **instant**, **local date**, **business date** và timezone trong contract.

### 16.4. Phân trang và sắp xếp

Nếu v1 trả 100 phần tử mặc định còn v2 chỉ trả 20, một consumer vốn không xử lý nextCursor có thể mất dữ liệu. Thay đổi pagination defaults, sort stability hoặc filter semantics cũng cần xem xét breaking.

### 16.5. Kết quả bất đồng bộ

Chuyển POST từ “trả 201 khi hoàn thành” sang “trả 202 khi đã xếp hàng” thay đổi thời điểm có thể khẳng định business outcome. Client phải biết kiểm tra operation resource, nhận callback hoặc chờ event phù hợp.

### 16.6. Quyền truy cập

Thay đổi scopes hoặc chính sách tenant có thể khiến consumer hợp lệ bị 403. Có thể cần một giai đoạn thông báo và migration credential; không giảm mức bảo mật bắt buộc chỉ để giữ tương thích vô thời hạn.

## 17. Versioning với event và message contract

Trong Microservices, hợp đồng không chỉ là REST. Event như **OrderPlaced**, **PaymentCaptured**, **InventoryReserved** cũng có consumer và vòng đời.

### 17.1. Phiên bản schema cho event

Ví dụ event v1:

~~~json
{
  "eventId": "evt-100",
  "eventType": "PaymentCaptured",
  "schemaVersion": 1,
  "paymentId": "PAY-100",
  "amount": 150000
}
~~~

V2 bổ sung currency và thay đổi biểu diễn tiền:

~~~json
{
  "eventId": "evt-101",
  "eventType": "PaymentCaptured",
  "schemaVersion": 2,
  "paymentId": "PAY-101",
  "money": {
    "amount": "150000",
    "currency": "VND"
  }
}
~~~

Consumer v1 có thể không đọc được v2 nếu trường **amount** biến mất. Hệ thống cần chính sách schema evolution, registry khi phù hợp, contract testing và thời gian consumer song song.

### 17.2. Các chiến lược triển khai event version mới

- **Cùng topic, schema có version:** consumer phân biệt schemaVersion và hỗ trợ một số phiên bản.
- **Topic mới:** producer và consumer chuyển dần, có thể cần publish song song có kiểm soát.
- **Upcaster/adapter:** chuyển sự kiện lịch sử hoặc representation cũ sang mô hình hiện tại khi đọc.
- **Dual publish tạm thời:** cần định danh để không coi hai representation là hai business event độc lập.

Nếu dual publish v1/v2 của **cùng một PaymentCaptured**, consumer không được tính tổng tiền hai lần. Giữ business event identity hoặc mapping rõ và kiểm soát subscriber theo từng topic/version.

### 17.3. Retention và replay

Một consumer có thể replay event cũ sau nhiều tháng. Khi producer đã ngừng phát schema v1, log/archive vẫn có thể chứa record v1. Chính sách retirement của **event producer contract** không có nghĩa xóa khả năng đọc dữ liệu lịch sử ngay nếu còn yêu cầu replay.

Cần xác định:

- Consumer nào cần đọc event cũ?
- Có upcaster hoặc schema reader phù hợp?
- Nếu đổi topic, điểm bắt đầu/offset/checkpoint được quản lý thế nào?
- Replay có tạo side effect nghiệp vụ trùng không?
- Retention và archive giữ đủ dữ liệu cho khôi phục không?

### 17.4. API và event có vòng đời khác nhau

Việc tắt REST v1 không tự cho phép xóa event schema v1. Ngược lại, một event schema mới có thể được triển khai trong khi public REST vẫn là v1, nếu hai contract có phạm vi độc lập và được kiểm thử.

## 18. API Gateway, BFF và compatibility adapter

Các lớp biên có thể giúp chuyển tiếp nhiều version, nhưng không nên che giấu sự khác biệt ngữ nghĩa quan trọng.

### 18.1. Những việc gateway làm tốt

- Route theo path, header hoặc API version đã chọn.
- Thực thi xác thực/ủy quyền ở biên theo trách nhiệm được giao.
- Áp rate limiting và logging theo version/client.
- Thêm header Deprecation/Sunset phù hợp.
- Quan sát usage, lỗi và mốc migration.
- Chuyển đổi format đơn giản khi không làm sai domain semantics.

### 18.2. Những việc gateway không nên tự quyết

Gateway không nên tự biến **PENDING_REVIEW** thành **PAID** để client v1 tiếp tục chạy; đó là quyết định business nguy hiểm. Nếu representation không thể dịch an toàn, phải trả một lỗi có nghĩa, giới hạn tính năng hoặc yêu cầu nâng cấp.

### 18.3. BFF và client mobile

Backend-for-Frontend có thể che bớt khác biệt giữa public mobile API và các internal microservices, giúp mobile app ít bị buộc cập nhật hơn. Tuy nhiên BFF cũng là producer có contract, cần lifecycle, telemetry và kế hoạch sunset với mobile version cũ.

Một client mobile bị ngừng hỗ trợ có thể tiếp tục tồn tại trên thiết bị. Trước retirement, cần xác định trải nghiệm: hiển thị yêu cầu cập nhật, cho truy cập read-only hoặc từ chối có thông báo, tùy chính sách và rủi ro.

## 19. Tài liệu chuyển đổi (migration guide) cần viết gì?

Một thông báo “v1 sẽ tắt, hãy dùng v2” không đủ. Migration guide nên cho consumer thấy **trước – sau – cách kiểm chứng**.

### 19.1. Cấu trúc gợi ý

1. **Phạm vi:** endpoint/event nào bị ảnh hưởng, version cũ và mới.
2. **Lý do thay đổi:** bối cảnh nghiệp vụ và hạn chế hợp đồng cũ.
3. **Những khác biệt breaking:** field, enum, unit, status code, authentication và behavior.
4. **Mapping:** trường cũ sang trường mới, có hay không mapping một-một.
5. **Ví dụ request/response:** before/after kèm lỗi phổ biến.
6. **Thứ tự nâng cấp:** producer/client, SDK và môi trường kiểm thử.
7. **Các bước thay đổi code:** cách đọc, validate, retry, cache, pagination và idempotency.
8. **Test cases:** những tình huống cần kiểm tra trước production.
9. **Timeline:** deprecation, ngày cần chuyển, sunset và phương án hỗ trợ.
10. **Liên hệ:** owner, kênh hỏi đáp, nơi báo lỗi/migration blocker.

### 19.2. Bảng mapping minh họa

| v1 | v2 | Cách chuyển |
| --- | --- | --- |
| totalAmount: number, mặc định VND | total.amount: decimal string | Parse số theo quy tắc tiền; không đổi đơn vị ngầm |
| Không có currency | total.currency: string | Không được mặc định VND cho mọi giao dịch |
| status=PROCESSING | status=PAYMENT_PENDING hoặc REVIEW_REQUIRED | Có thể không map một-một; cập nhật state machine |
| Trang danh sách kiểu offset | Cursor pagination | Đọc nextCursor thay vì tự tăng offset |
| Error message tự do | Problem Details/code | Điều chỉnh client đọc code ổn định |

Nếu mapping không thể chính xác về nghĩa, migration guide phải nói rõ điều đó. Không cung cấp ví dụ “đơn giản hóa” khiến client tính sai tiền hoặc coi yêu cầu chờ là đã hoàn tất.

## 20. CI/CD và kiểm thử để chặn breaking change ngoài ý muốn

Một thay đổi API cần được kiểm tra tự động ở nhiều tầng.

### 20.1. OpenAPI/schema diff

So sánh contract trước và sau để phát hiện:

- Endpoint/method bị xóa hoặc đổi.
- Field required/optional thay đổi.
- Data type, schema, enum và nullability thay đổi.
- Response status, media type, header và security scheme bị thay đổi.
- Schema mới không còn đáp ứng những client quan trọng.

Công cụ diff là **bộ phát hiện dấu hiệu**, không thay thế đánh giá semantics.

### 20.2. Consumer contract tests

Producer chạy tests cho kỳ vọng của consumer. Ví dụ Order API phải tiếp tục trả **201 Created** khi tạo Order đã được ghi nhận theo contract, và một lần retry với idempotency key cũ không tạo hai Order.

### 20.3. Provider integration tests

Kiểm tra các use case thực với database, authorization và downstream quan trọng. Đặc biệt thử:

- Unknown enum và field mới.
- Mã lỗi và Problem Details.
- Pagination boundary và cursor.
- Concurrency với ETag/If-Match.
- Retry và timeout gây side effect.
- Các bản dữ liệu lịch sử có schema cũ.
- Điều kiện quyền theo tenant và service identity.

### 20.4. Compatibility matrix trong release

Nếu producer v2 dự kiến chạy song song consumer v1, pipeline cần có bằng chứng rằng tổ hợp đó hoạt động. Tùy hệ thống, có thể dùng môi trường test chạy v1 client + v2 producer, schema fixtures, consumer contracts hoặc traffic replay đã loại bỏ dữ liệu nhạy cảm.

**Không chỉ test v2 với v2**, vì failure thường xảy ra ở thời gian chuyển tiếp giữa các phiên bản.

### 20.5. Các mức kiểm soát release

- **Build-time gate:** chặn thay đổi schema breaking không được khai báo.
- **Review-time gate:** owner đánh giá ngữ nghĩa và consumer impact.
- **Deployment-time gate:** canary/feature flag, rollback plan và monitoring.
- **Retirement-time gate:** usage bằng chứng, xác nhận migration và kế hoạch thu hồi.

Không cần tạo một quy trình quá nặng cho mọi field mới. Nâng mức kiểm soát theo ảnh hưởng của thay đổi.

## 21. Migration rollout có kiểm soát

### 21.1. Chuẩn bị

- Công bố contract mới và tài liệu có thể thử nghiệm.
- Đảm bảo producer phục vụ song song đúng quyền và ngữ nghĩa.
- Có consumer registry và owner cho từng tích hợp.
- Định nghĩa metric, SLO và cutover criteria.
- Chuẩn bị rollback/roll-forward của route, SDK và dữ liệu.
- Xác định ngày deprecated/sunset thực tế.

### 21.2. Chuyển từng nhóm consumer

Một thứ tự phù hợp có thể là:

1. Consumer nội bộ dễ kiểm soát và có test đầy đủ.
2. Client/staging của đối tác.
3. Một nhóm production traffic có thể quan sát.
4. Những đối tác lưu lượng cao hoặc nghiệp vụ nhạy cảm.
5. Batch jobs, hệ thống reporting và consumer ít hoạt động.
6. Mobile versions hoặc thiết bị cập nhật chậm theo chính sách.

Không nhất thiết áp đúng thứ tự trên; ưu tiên theo **rủi ro, khả năng rollback, mức ảnh hưởng và dependency**.

### 21.3. Canary và shadow

**Canary:** một phần request thật đi qua v2 và được giám sát để xem lỗi, latency, business outcome trước khi mở rộng.

**Shadow:** gửi bản sao read-only traffic hoặc tính toán phụ để so sánh hai representation mà không thực hiện thêm side effect. **Không shadow lệnh thanh toán/đặt hàng tạo giao dịch thật hai lần.** Với thao tác ghi, chỉ so sánh logic trong môi trường an toàn hoặc trên bản ghi đã được khử side effect.

### 21.4. Rollback không phải khôi phục dữ liệu tự động

Nếu v2 đã ghi một trạng thái mới mà v1 không hiểu, rollback route về v1 có thể làm client cũ sai. Kế hoạch release phải chỉ rõ **những gì có thể rollback, những gì phải roll-forward và những trạng thái cần đối soát**.

Đối với API chỉ đọc, rollback thường dễ hơn. Với API tạo tiền/đơn/hoàn tiền, cần idempotency, nguồn sự thật và cách xử lý các lệnh đã được thực hiện.

## 22. Đo lường và điều kiện ngừng phiên bản cũ

Một quyết định retirement nên dựa trên cả **mức sử dụng, kết quả nghiệp vụ và rủi ro vận hành**.

### 22.1. Dashboard theo version

| Chỉ số | Ý nghĩa |
| --- | --- |
| Request count by version/client | Có consumer nào còn dùng v1 không? |
| Unique active consumers | Mức độ phân tán của migration |
| Last seen by endpoint | Endpoint cụ thể đã hết sử dụng chưa? |
| Error rate 4xx/5xx by version | Client có lỗi sau khi đổi không? |
| p95/p99 latency | v2 có gây suy giảm độ trễ không? |
| Retry/idempotency conflicts | Có request lặp hoặc đổi nghĩa request không? |
| Business completion/failure rate | Tính năng mới có cho kết quả đúng không? |
| Deprecated usage trend | Tiến độ giảm phụ thuộc v1 |
| Contract test pass rate | Các consumer được biết còn tương thích không? |
| Exception backlog | Bao nhiêu consumer cần gia hạn và vì sao? |

### 22.2. Điều kiện retirement ví dụ

- Phiên bản đích đã ổn định và đáp ứng các SLO cần thiết.
- Các consumer có owner đã chuyển hoặc có ngoại lệ được phê duyệt.
- Usage của v1 đã được kiểm chứng trong thời gian đủ bao phủ chu kỳ nghiệp vụ.
- Đối tác quan trọng đã nhận thông báo theo cam kết.
- Không còn job/consumer ngầm cần v1.
- Dữ liệu và trạng thái từ các request v1 vẫn có thể truy cập/đối soát hợp lệ ở hệ mới.
- Có runbook cho lỗi phát sinh trong đợt tắt.
- Tài liệu, SDK, gateway và monitoring phản ánh trạng thái thực.

Không cần đặt một ngưỡng kiểu “0 request trong 24 giờ” cho mọi API. Quy tắc phải do tổ chức quyết định theo mức rủi ro và loại consumer.

## 23. Vận hành ngày ngừng hỗ trợ

Việc tắt một version cần được quản lý như một **thay đổi production có rủi ro**, không phải xóa nhánh code trong lúc dọn repository.

### 23.1. Trước cutover

1. Xác nhận danh sách endpoint, schema, SDK và các route bị tác động.
2. Đối chiếu consumer inventory với gateway telemetry.
3. Kiểm tra thông báo pháp lý/hợp đồng và ngoại lệ còn mở.
4. Chốt người quyết định, thời điểm và cửa sổ theo dõi.
5. Có bản ghi trạng thái, cấu hình route và phương án hồi phục.
6. Kiểm tra v2 handling cho dữ liệu đã tạo qua v1.
7. Đảm bảo bảo mật/observability của route mới đã hoạt động.

### 23.2. Trong cutover

- Tắt hoặc chuyển route v1 theo phương án đã thông báo.
- Theo dõi các request bất thường, lỗi 4xx/5xx, các consumer chưa chuyển và outcome nghiệp vụ.
- Không tự động redirect POST sang v2 nếu thay đổi phương thức/payload/semantics có thể làm tăng hoặc lặp side effect.
- Nếu phát hiện consumer quan trọng bị ảnh hưởng, dùng quyết định đã phê duyệt: gia hạn ngắn, compatibility adapter, rollback routing hoặc roll-forward khẩn.
- Ghi lại thao tác và người phụ trách.

### 23.3. Sau cutover

- Theo dõi đủ qua chu kỳ hoạt động, không chỉ vài phút.
- Gỡ code và contract cũ khi không còn phụ thuộc thật.
- Cập nhật developer portal, changelog, SDK, OpenAPI và ADR.
- Rà soát permission/secret, route, WAF/rate limit và các dashboards không còn dùng.
- Lưu bằng chứng retirement và bài học sự cố nếu có.

Đừng xóa dữ liệu lịch sử hoặc audit chỉ vì một endpoint cũ không còn public.

## 24. Vấn đề bảo mật trong API deprecated

Phiên bản cũ vẫn hoạt động nghĩa là vẫn có thể bị tấn công. Dù không phát triển tính năng mới, tổ chức phải xác định trách nhiệm vá lỗ hổng, cập nhật dependency và theo dõi lạm dụng trong thời gian hỗ trợ.

### 24.1. Những rủi ro thường gặp

- API v1 sử dụng authorization model cũ chưa kiểm tra tenant đầy đủ.
- Endpoint cũ không còn được kiểm thử với dependency mới.
- Client legacy dùng authentication yếu hơn.
- Một adapter compatibility bỏ qua validation mới.
- Version routing ở gateway cho phép gọi route nội bộ ngoài ý muốn.
- Monitoring chỉ tập trung v2, bỏ qua abuse/vulnerabilities của v1.

Một lý do quan trọng để có sunset policy là **giảm thời gian tồn tại của bề mặt tấn công legacy**, nhưng không được tắt thiếu kế hoạch khi còn dữ liệu/giao dịch quan trọng.

### 24.2. Emergency deprecation

Nếu có lỗ hổng nghiêm trọng, có thể cần rút thời gian hỗ trợ theo quy trình ứng phó sự cố. Phải phối hợp security, API owner và các consumer bị ảnh hưởng, cân nhắc các phương án như rate limit, kiểm soát quyền, chặn chức năng nguy hiểm hoặc tắt một endpoint cụ thể thay vì mọi route.

Trường hợp khẩn cấp là ngoại lệ có căn cứ; không dùng “security” chung chung làm lý do bỏ nghĩa vụ thông báo.

## 25. Ownership và tài liệu quyết định

API versioning cần một người/đội chịu trách nhiệm, không thể chỉ dựa vào pipeline tự động.

### 25.1. API catalog

Mỗi API family có thể ghi:

~~~yaml
apiId: order-public-api
ownerTeam: order-platform
currentRecommendedVersion: v2
supportedVersions:
  - version: v1
    state: Deprecated
    docs: /docs/orders/v1
    migrationGuide: /docs/orders/v1-to-v2
    sunsetDate: 2027-07-01
  - version: v2
    state: Active
    docs: /docs/orders/v2
contact: api-support
~~~

Đoạn YAML chỉ là **ví dụ mô hình quản lý**, không phải cấu hình triển khai bắt buộc. Thời điểm, owner và URL phải được thay bằng dữ liệu của hệ thống thực.

### 25.2. ADR cho breaking version

Một quyết định đáng ghi ADR gồm:

- Bối cảnh và vấn đề nghiệp vụ.
- Hợp đồng nào bị phá vỡ, vì sao không thể sửa tương thích.
- Các lựa chọn đã cân nhắc.
- Versioning strategy.
- Dữ liệu/ownership và ranh giới service có thay đổi không.
- Consumer migration timeline.
- Security, vận hành và trade-off.
- Deprecation/sunset policy.
- Điều kiện chứng minh hoàn thành và ngày xem xét lại.

### 25.3. Changelog có ích với consumer

Changelog cần nêu **điều đổi, mức ảnh hưởng và cách xử lý**, không chỉ ghi “fix Order API”. Ví dụ:

~~~markdown
## Order API v2

### Breaking changes
- totalAmount duoc thay boi total.amount va total.currency.
- status PAYMENT_PENDING khac voi CONFIRMED.

### Migration
- Cap nhat SDK v2.
- Doc price/currency theo hop dong moi.
- Xu ly enum khong biet bang trang thai an toan.
- Kiem tra pagination va loi Problem Details.

### Deprecation
- v1 deprecated: [ngay duoc cong bo]
- sunset du kien: [ngay duoc cong bo]
- Migration guide: [duong dan]
~~~

Đây là ví dụ cấu trúc, không phải lịch version cụ thể của một API đang chạy.

## 26. Trường hợp đặc biệt: đối tác bên ngoài và mobile app

### 26.1. Đối tác B2B

Đối tác có thể chịu quy trình kiểm thử, phê duyệt bảo mật và ngày phát hành không do API provider quyết định. Kế hoạch migration cần tính:

- Thời gian cung cấp sandbox và test data.
- Các thay đổi credentials và IP allowlist.
- Hợp đồng hỗ trợ và thông báo chính thức.
- Môi trường staging giống production về behavior quan trọng.
- Thỏa thuận xử lý giao dịch tồn trong lúc cutover.
- Đầu mối xác nhận kết quả và kênh incident.

Không chỉ gửi thông báo email rồi mặc định đối tác đã chuyển.

### 26.2. Mobile app và SDK

Một bản mobile app cũ có thể tiếp tục gọi API nhiều tháng. Khi retire v1, cần theo dõi tỷ lệ client version, xác định điều kiện tối thiểu để truy cập và thông báo nâng cấp có thể hiểu được.

Nếu có thể, sử dụng BFF hoặc capability negotiation để giảm mức độ buộc người dùng cập nhật app khi internal service đổi. Nhưng không tạo lớp dịch mà phải đoán sai nghĩa trạng thái hoặc vô hiệu hóa security.

### 26.3. Batch, scheduler và consumer ít xuất hiện

Một job đối soát cuối tháng hoặc xử lý cuối năm có thể không tạo traffic trong tuần gần nhất. Consumer registry cần ghi những luồng theo lịch và cách chạy thử trước retirement.

## 27. Anti-patterns thường gặp

### 27.1. Tăng API version cho mọi lần phát hành

Số version tăng nhanh làm nổ số hợp đồng hỗ trợ. Nếu behavior tương thích, có thể phát hành mà không tạo API major version mới.

### 27.2. Không bao giờ version, chỉ sửa trực tiếp v1

Thay đổi breaking âm thầm khiến client cũ sai. Cần đánh giá tương thích, hợp đồng chuyển đổi và thông báo.

### 27.3. Xem thêm enum là luôn non-breaking

Một consumer có exhaustive switch có thể crash; một nhánh default có thể ra quyết định sai. Phải công bố tính mở của enum và hành vi unknown an toàn.

### 27.4. Duy trì hai version với hai nguồn dữ liệu khác nhau

Cùng một đơn nhưng v1 ghi database A, v2 ghi database B không có reconciliation có thể tạo sự thật mâu thuẫn. Ưu tiên một nguồn sự thật và adapter representation khi phù hợp.

### 27.5. Tắt v1 chỉ vì dashboard không có request trong vài ngày

Job theo kỳ, đối tác hiếm khi sử dụng và phiên bản mobile cũ có thể vẫn phụ thuộc. Phải kiểm tra đúng chu kỳ nghiệp vụ.

### 27.6. API Gateway tự dịch ngữ nghĩa bất khả thi

Chuyển status **REVIEW_REQUIRED** thành **PAID** để “giữ tương thích” làm mất tính đúng đắn nghiệp vụ. Tính nhất quán quan trọng hơn vẻ ngoài hoạt động.

### 27.7. Chỉ kiểm thử client mới

Producer v2 có thể chạy tốt với consumer v2 nhưng làm consumer v1 lỗi. Phải kiểm tra compatibility matrix thực tế.

### 27.8. Deprecation nhưng không có đường thay thế

Consumer không thể chuyển nếu không có migration guide, SDK, sandbox, ownership và chính sách lỗi. Deprecation là một workflow, không phải một nhãn.

### 27.9. Không quản trị những ngoại lệ gia hạn

Nếu mọi đối tác đều được gia hạn vô thời hạn, trạng thái deprecated không dẫn tới retirement. Cần owner, lý do, phạm vi, ngày xem lại và chi phí bảo trì ngoại lệ.

### 27.10. Lẫn lộn versioning schema và HTTP resource

Một response ETag có thể đổi sau mỗi cập nhật đơn; nó không phải API major version. Phân biệt state version, contract version và deployment version.

### 27.11. Xóa dữ liệu lịch sử cùng với endpoint

Ngừng phục vụ route không đồng nghĩa hết nghĩa vụ lưu trữ, đối soát hoặc audit. Data retention là quyết định riêng.

### 27.12. Chỉ nêu thời hạn mà không có đo lường

Một lịch sunset không có usage metrics và consumer owner khiến quyết định tắt là phỏng đoán. Phải có evidence.

## 28. Checklist trước khi công bố API v2

**Thiết kế hợp đồng**

- Đã xác định rõ lý do cần breaking version thay vì thay đổi tương thích?
- Đã liệt kê thay đổi request/response, status, errors, auth, pagination và behavior?
- Đã xác định API version khác implementation version và resource state version?
- Đã chọn chiến lược path/header/media/query nhất quán với hệ thống?
- Đã có OpenAPI và ví dụ các ca quan trọng?
- Đã bảo vệ business invariant và một nguồn sự thật khi v1/v2 song song?

**Kiểm thử và vận hành**

- Đã có contract tests cho các consumer quan trọng?
- Đã kiểm tra producer mới với consumer cũ theo compatibility matrix?
- Đã có metrics theo version/client và tracing?
- Đã có phương án canary/rollback/roll-forward cho các request có side effect?
- Đã kiểm tra security, tenant isolation và rate limiting của cả v1/v2?

**Chuyển đổi**

- Đã có migration guide, SDK/sample code và môi trường thử nghiệm?
- Đã lập consumer registry và định danh owner?
- Đã có lịch thông báo/deprecation/sunset được phê duyệt?
- Đã có đầu mối hỗ trợ, quy trình exception và thời điểm xem lại?
- Đã tính tới mobile, batch, partner và các consumer có chu kỳ dài?

## 29. Checklist trước khi retire API v1

- Đã qua mốc thông báo và nghĩa vụ hợp đồng đã được thực hiện?
- Phiên bản mới đang hoạt động ổn định và đủ chức năng thay thế?
- Consumer trọng yếu đã chuyển và kiểm chứng outcome nghiệp vụ?
- Telemetry cho thấy v1 không còn phụ thuộc trong chu kỳ quan sát phù hợp?
- Các exception còn mở đã được xử lý hoặc có quyết định rõ?
- Dữ liệu cũ, giao dịch đang xử lý và event lịch sử vẫn được đối soát?
- Có runbook, owner, cửa sổ cutover và kế hoạch phục hồi?
- Có cơ chế phát hiện request v1 bất thường sau retirement?
- Đã cập nhật tài liệu, dashboard và SDK?
- Việc dọn code/schema cũ không làm hỏng luồng dữ liệu ngoài API?

**Retirement chỉ hoàn tất khi đã loại bỏ phụ thuộc thật và xác nhận tác động vận hành**, không phải ngay khi xóa một route trong repository.

## 30. Bài thực hành: chuyển Checkout API từ v1 sang v2

Một nền tảng thương mại điện tử cung cấp:

~~~text
POST /v1/checkouts
GET  /v1/checkouts/{id}
~~~

Response v1:

~~~json
{
  "checkoutId": "CHK-1001",
  "amount": 200000,
  "status": "DONE"
}
~~~

Do mở rộng sang nhiều thị trường, doanh nghiệp cần:

- Tiền có currency, mức chính xác được xác định rõ.
- Trạng thái phân biệt **ORDER_CREATED**, **PAYMENT_PENDING**, **PAYMENT_CONFIRMED** và **MANUAL_REVIEW**.
- Một checkout có thể hoàn tất đặt đơn nhưng thanh toán còn pending.
- Client phải dùng idempotency key khi gửi POST.
- Mobile app cũ, đối tác B2B và batch job đều đang dùng v1.

### Bài A — Phân loại breaking

Phân tích thay đổi field **amount**, **status**, thời điểm trả kết quả POST và yêu cầu idempotency. Điều nào là thay đổi cú pháp, điều nào là thay đổi ngữ nghĩa?

### Bài B — Chọn chiến lược version

Chọn path **/v2/checkouts** hoặc chiến lược khác; nêu ưu điểm, chi phí và quy tắc fallback khi client không chỉ định version.

### Bài C — Thiết kế hợp đồng v2

Viết request và response có **money.amount**, **money.currency**, **checkoutId**, **orderId** và trạng thái đủ rõ. Quy định khi nào trả **201**, **202**, **409** và lỗi có cấu trúc. Nêu cách chống tạo checkout hoặc thu tiền hai lần.

### Bài D — Migration guide

Lập bảng mapping v1 → v2 và chỉ rõ giá trị **DONE** không thể luôn map một-một sang “đã thanh toán”. Viết danh sách test consumer cần thực hiện.

### Bài E — Lifecycle

Đề xuất lịch **Active → Deprecated → Sunset Scheduled → Retired** với thời hạn do nhóm tự giả định; ghi lý do chọn thời hạn cho mobile/đối tác/batch.

### Bài F — Cutover

Mô tả cách phục vụ song song v1/v2 mà không tạo hai nguồn dữ liệu, cách đo usage và điều kiện xác nhận không còn consumer quan trọng ở v1. Nêu xử lý khi xuất hiện một job chỉ chạy cuối quý.

Bài thực hành hoàn thành khi có thể chứng minh **client cũ được bảo vệ trong thời gian đã cam kết, client mới nhận đúng ngữ nghĩa, và v1 chỉ bị retire khi việc chuyển đổi đã có bằng chứng**.

## 31. Tổng kết

Quản lý phiên bản API là quản lý **hợp đồng giữa các dịch vụ và client có tốc độ nâng cấp khác nhau**. Phiên bản chỉ có giá trị khi nó phản ánh sự khác biệt thực sự về contract và có quy tắc tương thích, tài liệu, kiểm thử và quyền sở hữu.

Vòng đời ngừng hỗ trợ nên là một quá trình có kiểm soát:

~~~text
Thay đổi nghiệp vụ / kỹ thuật
          |
          v
Đánh giá tương thích và impact
          |
          +-- Tương thích --> phát hành trên contract hiện tại
          |
          +-- Breaking ----> thiết kế contract mới
                                |
                                v
                          Publish v2 + test
                                |
                                v
                          Expand khả năng
                                |
                                v
                          Di chuyển consumer
                                |
                                v
                          Deprecated v1
                                |
                                v
                          Công bố sunset
                                |
                                v
                          Quan sát usage + xử lý ngoại lệ
                                |
                                v
                          Retirement có kiểm soát
                                |
                                v
                          Gỡ adapter cũ, cập nhật catalog
~~~

**Ba nguyên tắc cốt lõi:**

1. **Version hợp đồng, không version theo mỗi deployment.** Đánh giá thay đổi dựa trên consumer thực và ý nghĩa nghiệp vụ, không chỉ JSON schema.
2. **Deprecation là cam kết chuyển đổi, không phải xóa ngay.** Cần migration guide, thời gian thông báo, consumer inventory, owner và bằng chứng sử dụng.
3. **Retirement là hoạt động production có rủi ro.** Chỉ ngừng API cũ sau khi xác minh consumer, dữ liệu, bảo mật, khả năng khôi phục và kết quả nghiệp vụ phù hợp.

Khi thực hiện đúng, microservices có thể **phát triển độc lập nhưng vẫn giữ được niềm tin của consumer**: hệ thống thay đổi theo thời gian mà không buộc mọi ứng dụng phải triển khai cùng lúc hoặc chịu một thay đổi không được thông báo.
