# Ngừng API, thu hồi credential và dọn tài liệu

Ngừng một API là một thay đổi bảo mật trong toàn bộ vòng đời dịch vụ. Việc xóa route hoặc tắt một máy chủ chỉ kết thúc một phần của quá trình. Credential cũ có thể vẫn còn hiệu lực, một đường truy cập khác có thể vẫn trỏ đến backend, client chưa di chuyển có thể tiếp tục gửi request và tài liệu cũ có thể hướng người dùng đến endpoint đã bị loại bỏ.

Trong API Security, mỗi endpoint cần được quản lý theo chức năng, đối tượng dữ liệu và luồng nghiệp vụ mà nó phục vụ. Khi endpoint hoặc phiên bản API không còn được hỗ trợ, đội vận hành phải biết ai đang sử dụng nó, dữ liệu nào có thể bị ảnh hưởng, credential nào cấp quyền truy cập và những thành phần nào cần được đóng hoặc lưu trữ. Mục tiêu là kết thúc quyền truy cập một cách có kiểm soát, giữ lại bằng chứng cần thiết và tránh để lại một API “mồ côi” có thể bị khai thác.

## 1. Phân biệt deprecation, sunset và shutdown

Các thuật ngữ này mô tả những thời điểm khác nhau trong vòng đời API:

| Trạng thái | Ý nghĩa | Hành vi dự kiến |
|---|---|---|
| Active | API đang được hỗ trợ | Tiếp tục xử lý request theo hợp đồng đã công bố |
| Deprecated | API đã được thông báo sẽ ngừng hoặc thay thế | Vẫn có thể hoạt động trong thời gian chuyển đổi; client cần lập kế hoạch di chuyển |
| Sunset | Đã đến thời điểm kết thúc được công bố | API ngừng phục vụ theo lịch đã thông báo |
| Shutdown / Retired | API đã bị vô hiệu hóa và hoàn tất các bước kết thúc | Route, quyền truy cập và tài nguyên liên quan được gỡ hoặc lưu trữ theo chính sách |

Deprecation là tín hiệu về trạng thái hỗ trợ; nó không tự động làm request thất bại. Sunset là mốc thời gian dự kiến API không còn hoạt động. Shutdown là hành động kỹ thuật thực tế để chặn truy cập và thu hồi các quyền liên quan. Không nên coi việc gắn nhãn deprecated trong tài liệu là đã hoàn thành việc ngừng API.

Một API có thể bị ngừng vì đã có phiên bản mới, sản phẩm không còn cung cấp chức năng đó, một đối tác chấm dứt tích hợp, endpoint có rủi ro bảo mật không thể khắc phục hoặc hệ thống được hợp nhất. Với trường hợp có dấu hiệu bị khai thác, đội ứng phó sự cố có thể phải vô hiệu hóa khẩn cấp thay vì chờ hết thời gian chuyển đổi thông thường.

## 2. Rủi ro bảo mật khi để lại API cũ

API cũ thường ít được theo dõi và cập nhật hơn API đang hoạt động. Điều này tạo ra nhiều dạng rủi ro:

- **Endpoint không còn chủ sở hữu:** Không ai theo dõi lỗ hổng, cấu hình xác thực hoặc cảnh báo của dịch vụ cũ.
- **Credential tồn tại quá lâu:** API key, client secret, chứng thư hoặc tài khoản dịch vụ vẫn có quyền truy cập dù tích hợp đã kết thúc.
- **Đường truy cập ngoài dự kiến:** Route cũ vẫn có thể truy cập qua origin trực tiếp, hostname nội bộ, gateway khác, IP allowlist hoặc một phiên bản triển khai chưa được gỡ.
- **Chính sách không đồng nhất:** Phiên bản cũ có thể thiếu kiểm tra quyền mức đối tượng, validation, rate limit hoặc ghi audit log như phiên bản mới.
- **Tài liệu gây nhầm lẫn:** OpenAPI, ví dụ mã nguồn và hướng dẫn cũ khiến nhóm phát triển tiếp tục tích hợp vào endpoint sắp bị tắt.
- **Dữ liệu và bí mật bị lộ:** Tệp cấu hình, collection kiểm thử hoặc tài liệu đã xuất bản có thể chứa URL nội bộ, token mẫu còn hiệu lực hoặc thông tin hạ tầng không còn cần thiết.

Do đó, một kế hoạch ngừng API phải xử lý đồng thời endpoint, credential, hạ tầng, dữ liệu, client phụ thuộc và tài liệu.

## 3. Lập danh mục trước khi thay đổi

Không thể thu hồi đúng quyền nếu không biết quyền đó đang được cấp cho ai và được sử dụng ở đâu. Bước đầu tiên là lập danh mục endpoint và các thành phần liên quan.

### 3.1. Xác định phạm vi API cần ngừng

Ghi nhận tối thiểu:

| Thông tin | Câu hỏi cần trả lời |
|---|---|
| API và phiên bản | Tên dịch vụ, base URL, version, route và HTTP method nào sẽ ngừng? |
| Môi trường | API tồn tại ở production, staging, sandbox, vùng triển khai hoặc mạng nội bộ nào? |
| Chủ sở hữu | Ai chịu trách nhiệm nghiệp vụ, kỹ thuật, bảo mật và vận hành? |
| Dữ liệu | Endpoint đọc, ghi, xuất hoặc xóa loại dữ liệu nào? Dữ liệu thuộc tenant nào? |
| Xác thực | API chấp nhận API key, OAuth access token, mTLS, session hay cơ chế riêng? |
| Phân quyền | Scope, role, policy, tenant và quyền mức đối tượng nào được áp dụng? |
| Hạ tầng | Gateway, load balancer, ingress, DNS, CDN, firewall, service mesh và backend nào tham gia? |
| Phụ thuộc | Client, mobile app, đối tác, webhook, batch job, queue consumer hoặc dịch vụ nội bộ nào gọi API? |
| Lưu trữ | Log, backup, dữ liệu nghiệp vụ và audit record được giữ ở đâu, theo thời hạn nào? |

Nguồn dữ liệu có thể gồm API gateway, log truy cập, distributed tracing, service registry, kho cấu hình, hệ thống quản lý credential và danh mục tích hợp. Nên đối chiếu nhiều nguồn vì log có thể không ghi nhận client hoạt động rất ít hoặc client chỉ chạy theo lịch dài ngày.

### 3.2. Tìm client phụ thuộc và chủ sở hữu credential

Với từng client, cần xác định người hoặc hệ thống chịu trách nhiệm di chuyển, endpoint thay thế, thời gian dự kiến hoàn tất và credential đang dùng. Phân biệt credential chỉ dùng cho API sắp ngừng với credential dùng chung cho nhiều API.

Một API key có tên “legacy-client” chưa chắc chỉ được dùng bởi một client. Cần xác minh qua metadata, secret manager, log xác thực và chủ sở hữu tích hợp. Nếu một secret được chia sẻ giữa nhiều dịch vụ, thu hồi ngay có thể làm gián đoạn các API vẫn còn hoạt động. Khi đó, cần cấp credential riêng cho các tích hợp còn lại, di chuyển chúng, rồi mới thu hồi credential cũ.

### 3.3. Xác định thời gian quan sát phù hợp

Không thấy request trong vài giờ không chứng minh API không còn người dùng. Một số tích hợp chỉ chạy cuối tháng, cuối quý hoặc khi có sự kiện hiếm. Khoảng thời gian quan sát phải bao phủ chu kỳ hoạt động dự kiến và các thời điểm nghiệp vụ quan trọng.

Nếu không thể xác định đầy đủ client, cần ghi rõ phần chưa biết và đánh giá rủi ro trước khi chọn cách tắt. Với API truy cập dữ liệu nhạy cảm, một endpoint không có owner hoặc không thể kiểm kê credential là lý do để tăng mức giám sát và giới hạn truy cập trong giai đoạn chuyển tiếp.

## 4. Lập kế hoạch chuyển đổi và thông báo sunset

Kế hoạch cần xác định ngày bắt đầu deprecation, hạn cuối hỗ trợ, API thay thế, thay đổi hợp đồng, hướng dẫn di chuyển và đầu mối xử lý sự cố. Thông báo phải đến được các bên thực sự sử dụng API, gồm nhóm nội bộ và đối tác bên ngoài.

Thông tin chuyển đổi nên nêu:

- Endpoint, phiên bản và chức năng bị ảnh hưởng.
- Thời điểm bắt đầu deprecation và thời điểm dự kiến shutdown, kèm múi giờ rõ ràng.
- URL và tài liệu của API thay thế.
- Thay đổi về schema, status code, scope, quyền, giới hạn tài nguyên và cách xác thực.
- Việc cần làm với API key, OAuth client, chứng thư hoặc webhook secret.
- Cách kiểm thử trong sandbox và cách yêu cầu hỗ trợ.
- Hành vi của API sau thời điểm sunset, ví dụ trả `410 Gone` nếu phù hợp với hợp đồng.

HTTP có các cơ chế tiêu chuẩn để công bố thông tin vòng đời. `Deprecation` được định nghĩa trong RFC 9745 và `Sunset` trong RFC 8594. Có thể cung cấp thêm liên kết tới tài liệu di chuyển bằng quan hệ liên kết `deprecation`.

Ví dụ minh họa response trong giai đoạn chuyển đổi:

```http
HTTP/1.1 200 OK
Deprecation: @<unix-timestamp>
Sunset: Wed, 30 Jun 2027 23:59:59 GMT
Link: <https://developer.example.com/deprecations/orders-v1>; rel="deprecation"
Content-Type: application/json
```

`<unix-timestamp>` là chỗ giữ chỗ cho thời điểm deprecation theo định dạng Structured Field Date; cần thay bằng giá trị thực trước khi phát hành. Ngày trong `Sunset` phải phản ánh lịch đã được thống nhất. Các header này chỉ truyền đạt thông tin cho client; chúng không thay thế việc chặn route hoặc thu hồi credential tại thời điểm shutdown.

Không nên hứa một ngày sunset mà đội vận hành chưa thể thực hiện hoặc không có cách đo lường mức độ di chuyển. Nếu lịch thay đổi, phải cập nhật thông báo và tài liệu cho tất cả bên liên quan.

## 5. Di chuyển client trước khi đóng API

Trong giai đoạn chuyển đổi, giữ một khoảng thời gian để client chuyển sang API thay thế và xác minh hành vi thực tế. Việc di chuyển cần bao gồm cả hợp đồng kỹ thuật và chính sách bảo mật.

Một client được coi là đã di chuyển khi:

1. Gọi đúng base URL và phiên bản mới trong mọi môi trường cần thiết.
2. Dùng credential được cấp riêng cho tích hợp mới và chỉ có scope cần thiết.
3. Xử lý đúng schema, lỗi, pagination, timeout, retry và rate limit của API mới.
4. Được cấp quyền trên đúng tenant và đối tượng dữ liệu.
5. Vượt qua kiểm thử chức năng, kiểm thử bảo mật và kiểm thử vận hành.
6. Không còn request đến endpoint cũ trong khoảng thời gian quan sát đã thống nhất.

Không chỉ kiểm tra số lượng request tổng. Hãy theo dõi theo client ID, API key ID, OAuth client ID, route và môi trường. Dữ liệu quan sát phải đủ để xác định client nào còn phụ thuộc mà không ghi access token hoặc secret vào log.

Có thể tạm thời từ chối các thao tác ghi ở endpoint cũ hoặc chuyển endpoint sang chế độ chỉ đọc nếu nghiệp vụ cho phép và điều này đã được thông báo. Tuy nhiên, thay đổi hành vi giữa giai đoạn chuyển đổi cần được xem xét kỹ vì client có thể dựa vào các hiệu ứng phụ trước đây.

## 6. Thu hồi credential theo đúng phạm vi

Ngừng route và thu hồi credential là hai hành động riêng. Tắt endpoint không làm cho một API key hoặc OAuth token mất hiệu lực ở nơi khác. Ngược lại, thu hồi một credential dùng chung có thể làm hỏng những tích hợp vẫn đang hoạt động.

### 6.1. Lập danh sách credential cần xử lý

| Loại credential | Hành động khi ngừng tích hợp |
|---|---|
| API key | Vô hiệu hóa key ID cụ thể; kiểm tra key có được dùng chung không |
| OAuth client | Ngừng cấp token mới, thu hồi client secret hoặc vô hiệu hóa client theo cơ chế của authorization server |
| Access token | Chờ hết hạn ngắn, introspection hoặc kiểm tra denylist theo chính sách thu hồi |
| Refresh token | Thu hồi token hoặc token family liên quan để không thể tiếp tục cấp access token mới |
| Chứng thư mTLS | Thu hồi hoặc loại bỏ chứng thư client và cập nhật trust store nếu phù hợp |
| Webhook signing secret | Thay secret ở cả hai phía, ngừng chấp nhận secret cũ sau giai đoạn xoay vòng |
| Service account | Gỡ quyền, vô hiệu hóa tài khoản và thu hồi credential gắn với tài khoản |
| Khóa ký hoặc khóa mã hóa | Xoay vòng theo phạm vi sử dụng, đánh giá ảnh hưởng đến token, chữ ký và dữ liệu hiện có |

### 6.2. Thu hồi OAuth token và JWT đúng cách

Với OAuth, authorization server có thể hỗ trợ token revocation theo RFC 7009. Cần thu hồi refresh token và access token theo khả năng của hệ thống, đồng thời vô hiệu hóa hoặc giới hạn OAuth client nếu client không còn được phép hoạt động.

JWT access token tự chứa có thể tiếp tục được API chấp nhận đến `exp` nếu resource server chỉ xác minh chữ ký và claim cục bộ. Để rút ngắn thời gian credential còn hiệu lực, có thể dùng access token ngắn hạn, token introspection, danh sách thu hồi theo `jti` hoặc kiểm tra phiên bản bảo mật hiện tại. Lựa chọn phụ thuộc vào yêu cầu thu hồi và kiến trúc xác thực.

Không nên xoay vòng khóa ký toàn hệ thống chỉ để thu hồi một client nếu việc đó làm vô hiệu token của các client khác hoặc gây gián đoạn diện rộng. Hãy ưu tiên thu hồi theo client, token family hoặc phạm vi khóa cụ thể khi hệ thống hỗ trợ. Nếu bắt buộc thay khóa ký, phải có kế hoạch phân phối khóa mới, thời gian chấp nhận khóa cũ, xử lý token đang lưu hành và kiểm thử toàn bộ resource server.

### 6.3. Thực hiện theo thứ tự có kiểm soát

Một thứ tự thường dùng là:

1. Dừng phát hành credential mới cho tích hợp cũ.
2. Xác nhận client đã chuyển sang credential và endpoint mới.
3. Thu hồi refresh token, API key, client secret, chứng thư hoặc tài khoản dịch vụ thuộc phạm vi ngừng.
4. Xử lý access token còn hiệu lực theo chính sách đã chọn; ghi nhận thời gian tối đa token cũ còn có thể được chấp nhận.
5. Kiểm tra các lần xác thực thất bại và request còn phát sinh từ credential cũ.
6. Xác nhận credential dùng chung đã được tách hoặc các phụ thuộc còn lại đã được di chuyển trước khi thu hồi.

Nếu credential bị lộ hoặc API đang bị khai thác, ưu tiên chặn truy cập và thu hồi ngay theo quy trình ứng phó sự cố. Tính liên tục của dịch vụ khi đó được xử lý cùng kế hoạch khôi phục riêng, không phải lý do để duy trì credential bị xâm phạm.

### 6.4. Lưu dấu vết thu hồi

Audit record nên cho biết credential ID nào đã bị thu hồi, ai hoặc hệ thống nào thực hiện, thời điểm, lý do, phạm vi ảnh hưởng và kết quả. Không ghi giá trị bí mật của credential vào log. Việc lưu dấu vết giúp chứng minh quyền đã được kết thúc và hỗ trợ điều tra nếu có request bất thường sau shutdown.

## 7. Đóng endpoint và gỡ hạ tầng liên quan

Sau khi client đã di chuyển và credential cũ được xử lý, tiến hành đóng API trên tất cả đường truy cập.

### 7.1. Chặn route ở lớp công khai và lớp nội bộ

Kiểm tra và gỡ cấu hình ở:

- API gateway và route theo hostname, path, method.
- Ingress controller, load balancer và reverse proxy.
- Service mesh, internal gateway và service discovery.
- Backend application, controller, handler và scheduled job.
- Firewall, security group, network policy và allowlist.
- DNS record, CDN, cache và origin mapping.

Chỉ xóa route ở gateway có thể chưa đủ nếu client vẫn truy cập trực tiếp origin hoặc một hostname nội bộ. Cần kiểm tra mọi đường đi có thể tới backend, bao gồm đường truy cập giữa các mạng và các môi trường cũ.

### 7.2. Chọn phản hồi sau shutdown

Nếu endpoint đã ngừng vĩnh viễn và có thể phản hồi có kiểm soát, `410 Gone` thường diễn đạt rõ tài nguyên đã bị loại bỏ. `404 Not Found` có thể phù hợp khi chính sách không muốn tiết lộ endpoint hoặc khi route không còn tồn tại trong hệ thống. `401 Unauthorized` và `403 Forbidden` phục vụ các tình huống xác thực/phân quyền khác, không nên dùng thay cho thông báo vòng đời nếu điều đó gây hiểu nhầm.

Ví dụ response cho một endpoint đã được công bố sunset:

```http
HTTP/1.1 410 Gone
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/api-retired",
  "title": "API version retired",
  "status": 410,
  "detail": "Use the current Orders API version."
}
```

Không trả về chi tiết nội bộ như hostname backend, tên máy chủ, đường dẫn file cấu hình hoặc stack trace. Nếu endpoint không còn được route tới ứng dụng, gateway có thể tạo response này mà không cần giữ backend cũ hoạt động.

### 7.3. Xử lý request đến muộn và dữ liệu đang xử lý

Trước khi tắt backend, xác định cách xử lý request đang chạy, message trong queue, webhook đang retry và batch job chưa hoàn tất. Không xóa hàng đợi hoặc dừng worker một cách đột ngột nếu việc đó làm mất giao dịch hay tạo trạng thái dữ liệu không nhất quán.

Có thể cần ngừng nhận công việc mới, drain request hiện tại, hoàn tất hoặc chuyển các message còn tồn đọng sang luồng thay thế, rồi mới gỡ worker. Với thao tác ghi nhạy cảm, kiểm tra tính idempotent và khả năng retry để tránh xử lý hai lần khi chuyển đổi.

## 8. Dọn tài liệu, mã nguồn mẫu và bí mật

Tài liệu cũ là một phần của bề mặt tấn công và có thể khiến tích hợp tiếp tục sử dụng endpoint không còn được hỗ trợ. Tuy nhiên, dọn tài liệu không đồng nghĩa xóa toàn bộ lịch sử kỹ thuật hoặc bằng chứng kiểm toán.

### 8.1. Cập nhật nguồn tài liệu chính

Rà soát các nơi công bố API:

| Tài sản | Việc cần làm |
|---|---|
| API portal và developer portal | Đánh dấu deprecated/retired, ghi ngày sunset và liên kết API thay thế |
| OpenAPI / Swagger | Cập nhật trạng thái, loại bỏ khỏi danh mục API đang hoạt động hoặc lưu bản lịch sử có nhãn rõ ràng |
| README và hướng dẫn tích hợp | Thay ví dụ cũ, hướng dẫn migration và chỉ dẫn liên hệ |
| SDK và thư viện client | Ngừng phát hành phiên bản mới cho API cũ; ghi rõ phiên bản cuối và cách chuyển đổi |
| Postman collection và file môi trường | Xóa khỏi bộ sưu tập đang dùng hoặc chuyển sang kho lưu trữ; loại bỏ token và secret |
| Ví dụ mã nguồn, tutorial và snippet | Cập nhật URL, scope và cơ chế xác thực; kiểm tra bản sao được nhúng ở nơi khác |
| Runbook và sơ đồ kiến trúc | Ghi nhận thời điểm shutdown, thành phần đã gỡ và người sở hữu lưu trữ |
| Catalog nội bộ và service registry | Đổi trạng thái, owner và endpoint để tránh tự động khám phá API đã ngừng |

Nếu cần giữ tài liệu để tra cứu hoặc phục vụ kiểm toán, hãy chuyển vào kho lưu trữ có quyền truy cập phù hợp và gắn nhãn “retired” cùng ngày hiệu lực. Tránh để tài liệu lịch sử xuất hiện trong kết quả tìm kiếm như một hướng dẫn triển khai hiện hành.

### 8.2. Tìm và xử lý bí mật trong tài liệu

Rà soát token mẫu, API key, client secret, private key, chứng thư, mật khẩu, URL có thông tin xác thực và dữ liệu cá nhân trong:

- File `.env`, cấu hình mẫu và file export của công cụ kiểm thử.
- README, wiki, ticket, pull request, issue và lịch sử commit.
- Log, trace, ảnh chụp màn hình và tệp đính kèm.
- Pipeline CI/CD, biến môi trường và artifact build.
- Kho secret manager, vault, hệ thống quản lý chứng thư và bản sao cấu hình.

Nếu phát hiện secret thật đã từng được công bố, phải coi secret đó có khả năng bị lộ. Thu hồi hoặc xoay vòng secret tại hệ thống phát hành trước, sau đó mới dọn các bản sao có thể chỉnh sửa. Xóa chuỗi bí mật khỏi tài liệu hiện tại không làm cho giá trị đó mất hiệu lực; cũng không thể đảm bảo bí mật biến mất khỏi lịch sử Git, cache, bản sao lưu hoặc bản tải xuống của người khác.

Không xóa audit log, bằng chứng sự cố hoặc dữ liệu cần lưu theo chính sách lưu trữ chỉ để làm sạch tài liệu. Hãy phân biệt tài liệu hướng dẫn đã lỗi thời, bí mật cần thu hồi và hồ sơ cần bảo tồn. Việc truy cập các hồ sơ được giữ lại phải được giới hạn.

### 8.3. Gỡ quyền truy cập tài liệu và công cụ

Thu hồi quyền của nhóm đối tác, tài khoản dịch vụ, bot hoặc nhóm vận hành không còn cần truy cập repository, workspace, dashboard, API portal, collection và kho cấu hình cũ. Xóa webhook, automation và integration token chỉ phục vụ API đã ngừng sau khi xác nhận không còn tác vụ khác phụ thuộc.

## 9. Kiểm chứng sau shutdown

Một kế hoạch chỉ hoàn tất khi có bằng chứng cho thấy endpoint đã ngừng ở mọi nơi, credential cũ không còn được chấp nhận và client hợp lệ đã chuyển sang hệ thống mới.

### 9.1. Ma trận kiểm chứng

| Kiểm tra | Kết quả cần đạt |
|---|---|
| Gọi endpoint cũ từ Internet | Bị chặn hoặc nhận response retired đã định nghĩa |
| Gọi origin trực tiếp bỏ qua gateway | Không truy cập được backend cũ |
| Gọi qua hostname hoặc mạng nội bộ cũ | Route không còn phục vụ chức năng đã ngừng |
| Dùng API key cũ | Bị từ chối tại mọi resource server liên quan |
| Dùng OAuth client hoặc refresh token cũ | Không thể lấy credential mới; token cũ bị xử lý theo chính sách thu hồi |
| Dùng chứng thư mTLS hoặc webhook secret cũ | Không được chấp nhận sau thời điểm kết thúc đã công bố |
| Tìm request theo client/credential ID | Không còn traffic hợp lệ từ tích hợp đã ngừng; request còn lại được điều tra |
| Kiểm tra gateway, DNS, ingress và service registry | Không còn đường truy cập ngoài dự kiến |
| Tìm kiếm tài liệu hiện hành | Không còn hướng dẫn cũ gây nhầm lẫn |
| Kiểm tra kho secret và CI/CD | Không còn credential hoạt động không cần thiết cho API cũ |
| Kiểm tra log và audit record | Có dấu vết đầy đủ về người thực hiện, thời điểm và kết quả shutdown |

Các phép thử nên được thực hiện từ nhiều vùng mạng và bằng danh tính đại diện cho client cũ. Không nên chỉ dùng tài khoản quản trị để thử vì tài khoản đó có thể đi qua một đường truy cập đặc biệt mà client thông thường không có.

### 9.2. Giám sát sau khi đóng

Tiếp tục theo dõi request đến route cũ, lỗi xác thực bằng credential đã thu hồi, DNS query, kết nối đến origin và cảnh báo từ WAF hoặc gateway. Một lượng request tăng đột biến sau sunset có thể cho thấy client chưa di chuyển, một tài liệu cũ vẫn được sử dụng hoặc có người đang dò quét endpoint.

Đặt thời hạn giám sát theo mức độ rủi ro và chu kỳ hoạt động của client. Khi phát hiện request từ tích hợp hợp lệ còn sót lại, xác minh chủ sở hữu và hướng dẫn chuyển đổi qua kênh hỗ trợ đã công bố. Không cấp lại credential cũ chỉ để làm request chạy tiếp; mọi ngoại lệ phải có phạm vi, thời hạn và người phê duyệt rõ ràng.

## 10. Quy trình shutdown khẩn cấp khi có sự cố

Nếu API có lỗ hổng đang bị khai thác, credential bị lộ hoặc endpoint cho phép truy cập trái phép dữ liệu nhạy cảm, quy trình khẩn cấp có thể rút ngắn hoặc bỏ qua giai đoạn deprecation thông thường.

Một trình tự phản ứng có thể gồm:

1. Xác định route, dữ liệu, tenant và credential có khả năng bị ảnh hưởng.
2. Chặn endpoint hoặc giới hạn truy cập tại gateway, firewall hay lớp có thể thực thi nhanh nhất.
3. Thu hồi credential bị xâm phạm và ngăn cấp credential mới cho tích hợp liên quan.
4. Bảo toàn log, trace, cấu hình và bằng chứng cần cho điều tra trước khi thay đổi làm mất dấu vết.
5. Đánh giá giao dịch, dữ liệu và tài khoản có thể đã bị tác động; thực hiện quy trình ứng phó sự cố tương ứng.
6. Thông báo cho chủ sở hữu dữ liệu, client và các bên cần biết theo quy trình của tổ chức.
7. Kiểm chứng đường truy cập đã bị đóng và tiếp tục giám sát các dấu hiệu sử dụng credential cũ.

Nếu phải giữ API hoạt động tạm thời để tránh gián đoạn nghiêm trọng, hãy áp dụng biện pháp giảm thiểu cụ thể như allowlist client, giới hạn chức năng, thu hẹp scope, rate limit hoặc yêu cầu xác minh bổ sung. Ngoại lệ phải có thời hạn kết thúc và người chịu trách nhiệm; không để cấu hình tạm thời trở thành trạng thái vĩnh viễn.

## 11. Checklist hoàn tất vòng đời

Trước khi đánh dấu API đã retired, người phụ trách nên xác nhận các mục sau:

- [ ] Đã xác định đầy đủ route, phiên bản, môi trường, owner và dữ liệu liên quan.
- [ ] Đã lập danh sách client, đối tác, job, webhook và credential phụ thuộc.
- [ ] Đã thông báo deprecation, sunset, API thay thế và thay đổi bảo mật cho các bên sử dụng.
- [ ] Đã xác minh client cần tiếp tục hoạt động đã di chuyển và vượt qua kiểm thử.
- [ ] Đã ngừng cấp credential mới cho tích hợp cũ.
- [ ] Đã thu hồi API key, OAuth client, refresh token, chứng thư, webhook secret và service account trong phạm vi.
- [ ] Đã xử lý access token còn hiệu lực và thời gian chấp nhận token cũ.
- [ ] Đã đóng route ở gateway, origin, mạng nội bộ và các môi trường triển khai.
- [ ] Đã drain request, queue và job đang xử lý theo kế hoạch dữ liệu.
- [ ] Đã cập nhật hoặc lưu trữ OpenAPI, SDK, portal, ví dụ, runbook và service catalog.
- [ ] Đã tìm và thu hồi secret bị lộ; đã dọn bản sao không còn cần thiết.
- [ ] Đã bảo toàn audit log, bằng chứng sự cố và dữ liệu phải lưu theo chính sách.
- [ ] Đã kiểm thử endpoint cũ, credential cũ và đường truy cập trực tiếp.
- [ ] Đã thiết lập giám sát sau shutdown, owner lưu trữ và thời hạn đóng công việc.

## 12. Nguyên tắc thiết kế

Quản lý vòng đời API cần được đưa vào thiết kế ngay từ khi tạo endpoint. Mỗi API nên có owner, danh mục client, cơ chế cấp và thu hồi credential, chính sách lưu log, quy trình thông báo thay đổi và kế hoạch kết thúc hỗ trợ. Credential nên được cấp riêng theo client và có phạm vi quyền tối thiểu để có thể thu hồi chính xác mà không ảnh hưởng dịch vụ khác.

Khi ngừng API, hãy coi endpoint, credential, dữ liệu, hạ tầng và tài liệu là các phần của cùng một bề mặt bảo mật. Chỉ đánh dấu retired khi đã có bằng chứng về việc chặn mọi đường truy cập, kết thúc đúng quyền đã cấp, cập nhật tài liệu hiện hành và giữ lại hồ sơ cần thiết. Cách làm này giúp giảm API mồ côi, hạn chế credential tồn đọng và bảo đảm các quyết định trong toàn bộ vòng đời API có thể được kiểm chứng.
