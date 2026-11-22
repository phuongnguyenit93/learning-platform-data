# Đo traffic trước khi tắt endpoint

Một endpoint được đánh dấu `deprecated` hoặc có phiên bản thay thế không có nghĩa là client đã ngừng sử dụng nó. Ứng dụng mobile cũ có thể còn được cài trên thiết bị, một đối tác có thể chỉ gọi API vào cuối tháng, một job nội bộ có thể chạy mỗi quý, hoặc một client không có owner vẫn đang gửi request tới endpoint cũ. Nếu chỉ nhìn tổng số request trong vài ngày rồi tắt route, tổ chức có thể làm gián đoạn một nghiệp vụ quan trọng mà không biết trước.

Trước khi tắt endpoint, cần đo traffic đủ lâu, xác định ai đang gọi, họ dùng endpoint cho mục đích gì, request còn tạo tác động nghiệp vụ hay không và các consumer đã chuyển sang phiên bản mới chưa. Việc đo phải bao phủ toàn bộ đường truy cập, phân biệt consumer thật với health check/retry/bot, đồng thời giữ dữ liệu quan sát đủ tin cậy để đưa ra quyết định go/no-go.

Trong API Security, đây là một phần của quản lý vòng đời API. Endpoint cũ vẫn phải được bảo vệ cho đến khi retire thực sự; traffic measurement giúp giảm nguy cơ tắt nhầm, phát hiện zombie API và tìm các consumer chưa được quản lý.

Sau bài học, người đọc có thể:

- Xác định phạm vi telemetry cần thu thập trước khi tắt endpoint.
- Đo request volume, unique consumer, last seen, tần suất và tác động nghiệp vụ.
- Chọn cửa sổ đo phù hợp với chu kỳ sử dụng thường xuyên và hiếm gặp.
- Phân biệt traffic của client thật với health check, retry, scanner và traffic nội bộ.
- Lập kế hoạch thông báo deprecation, theo dõi migration và thử nghiệm ngừng phục vụ có kiểm soát.
- Đặt tiêu chí go/no-go, rollback và bằng chứng xác minh sau khi retire.

## 1. Vì sao phải đo traffic trước khi tắt endpoint?

Traffic measurement trả lời một câu hỏi thực tế: endpoint còn được sử dụng ở đâu, bởi ai và cho nghiệp vụ nào? Một endpoint có thể ít request nhưng vẫn rất quan trọng. Ví dụ, API xác nhận bảng lương chỉ được gọi một lần mỗi tháng; API khôi phục tài khoản chỉ được gọi khi có sự cố; webhook đối tác có thể chỉ gửi sự kiện khi một giao dịch hiếm xảy ra.

Không nên dùng một ngưỡng request đơn giản như “dưới 100 request/ngày thì có thể tắt”. Tổng volume không thể hiện số consumer, mức độ quan trọng hoặc thời điểm sử dụng. Một consumer duy nhất có thể là hệ thống thanh toán trọng yếu; hàng triệu request có thể chỉ đến từ một health check cấu hình sai.

### 1.1. Rủi ro khi tắt mà chưa đo đủ

- **Gián đoạn client còn hoạt động:** mobile app hoặc SDK cũ vẫn gọi endpoint.
- **Đứt tích hợp đối tác:** partner có lịch gọi riêng và không thường xuyên.
- **Mất nghiệp vụ định kỳ:** batch cuối tháng, báo cáo quý hoặc tác vụ năm không xuất hiện trong cửa sổ đo ngắn.
- **Bỏ sót đường truy cập:** endpoint được gọi trực tiếp qua load balancer, ingress hoặc host cũ ngoài API Gateway.
- **Không nhận diện consumer:** traffic còn nhưng chỉ có IP hoặc user-agent, không xác định được tổ chức/chủ sở hữu.
- **Đánh giá sai mức độ sử dụng:** retry, bot hoặc health check làm volume cao giả tạo; log sampling làm volume thấp giả tạo.
- **Không có đường rollback:** sau khi tắt mới phát hiện một client quan trọng và không thể khôi phục nhanh.

### 1.2. Đo traffic không thay thế inventory và xác nhận owner

Telemetry cho biết request đã xảy ra, nhưng không luôn cho biết mục đích và mức độ quan trọng. Một endpoint không có traffic trong log có thể do logging bị thiếu; một endpoint có traffic chưa chắc là client hợp lệ. Cần kết hợp inventory, owner confirmation, deployment metadata, client registry, lịch nghiệp vụ và quan sát runtime.

## 2. Xác định chính xác endpoint cần đo

Trước khi tạo dashboard, chuẩn hóa phạm vi cần retire. Không chỉ ghi một path chung như `/v1/orders`; hãy xác định endpoint theo tổ hợp:

- Hostname/base URL và môi trường.
- API/service và phiên bản.
- HTTP method.
- Route template, ví dụ `/v1/orders/{orderId}` thay vì mỗi ID cụ thể.
- Query parameter hoặc content type có ý nghĩa với routing nếu cần.
- Gateway/ingress/load balancer/upstream xử lý request.
- Region/cluster hoặc tenant boundary nếu triển khai phân tán.

Ví dụ, `GET /v1/orders/{id}` và `POST /v1/orders/{id}/refunds` có thể thuộc cùng phiên bản nhưng có consumer, rủi ro và kế hoạch migration khác nhau. Không gộp tất cả traffic của `/v1` thành một số liệu rồi kết luận mọi endpoint đều không còn dùng.

Inventory cần liên kết endpoint cũ với endpoint thay thế, ngày deprecation, ngày dự kiến sunset, owner service, owner client và danh sách consumer đã biết. Nếu API có nhiều hostname hoặc alias, tất cả phải được đưa vào phạm vi đo.

## 3. Thu thập telemetry từ mọi đường truy cập

Không một nguồn log nào bảo đảm nhìn thấy toàn bộ request. Kết hợp các nguồn sau:

| Nguồn | Thông tin hữu ích | Điểm mù cần kiểm tra |
|---|---|---|
| API Gateway/API management | Route, method, client credential ID, status, quota, host | Traffic bypass gateway hoặc gateway khác |
| Ingress/reverse proxy/load balancer | Host, route, upstream, status, request time | Internal service gọi trực tiếp hoặc listener riêng |
| Service access log | Route thực tế, kết quả xử lý, latency, business outcome | Log sampling, log level hoặc instance không đồng nhất |
| Service mesh/network flow | Service caller, destination, port, protocol | Không phải lúc nào cũng thấy HTTP route hoặc consumer cuối |
| WAF/security telemetry | Scanner, bot, request bị chặn, nguồn bất thường | Không đại diện cho request đã tới ứng dụng |
| Distributed tracing | Chuỗi downstream, caller service, correlation ID | Sampling và trace propagation có thể làm thiếu mẫu |
| Client registry/SDK analytics | App version, partner/client ID, phiên bản SDK | Client không đăng ký hoặc telemetry bị tắt |
| CI/CD/cloud inventory | Deployment, hostname, ingress và service version | Không chứng minh request thực sự được sử dụng |

Đối chiếu các nguồn để phát hiện đường truy cập trực tiếp, alias DNS, endpoint chạy trên cluster khác hoặc traffic không đi qua lớp quan sát chính. Nếu hệ thống có nhiều region, cluster, account cloud hoặc gateway, phải xác nhận tất cả đều nằm trong phạm vi.

### 3.1. Kiểm tra độ phủ trước khi bắt đầu cửa sổ đo

Trước khi kết luận endpoint không còn được gọi, xác minh:

1. Mọi host và route liên quan đều được thu thập.
2. Log/metric được bật trên tất cả instance và môi trường production liên quan.
3. Log không bị sampling theo cách làm mất request hiếm hoặc client ít hoạt động.
4. Thời gian hệ thống được đồng bộ và timestamp có thể so sánh.
5. Retention của log dài hơn cửa sổ đo và đủ để truy vấn lại.
6. Route template được chuẩn hóa đúng, không tách cùng endpoint thành nhiều nhãn hoặc gộp nhầm endpoint khác nhau.
7. Có thể phân biệt request thành công, request bị chặn và request lỗi trước khi tới ứng dụng.

Nếu một nguồn telemetry bị mất dữ liệu trong một khoảng thời gian, đánh dấu khoảng đó là **không đủ bằng chứng**; không coi nó là khoảng không có traffic.

## 4. Gắn request với consumer có thể liên hệ

Đếm request theo IP không đủ để xác định ai đang sử dụng API. IP có thể thay đổi, nhiều client dùng chung NAT, proxy hoặc cloud egress; một client có thể chạy ở nhiều vùng. Cần dùng định danh ổn định hơn khi có thể.

Các thuộc tính nên thu thập:

| Thuộc tính | Ví dụ | Lưu ý |
|---|---|---|
| OAuth `client_id` | `mobile-app-prod` | Thường là khóa nhận diện client tốt nếu được quản lý đúng |
| API key identifier | ID/key label đã cấp | Chỉ lưu ID hoặc fingerprint; không lưu API key thô |
| Service/workload identity | `billing-worker` | Hữu ích cho traffic nội bộ và service-to-service |
| Partner/integration ID | `partner-042` | Liên kết với hợp đồng và technical contact |
| App/SDK version | `ios-5.8.1` | Giúp nhận diện client cũ cần nâng cấp |
| Tenant/account ID | `tenant-17` | Chỉ thu thập khi cần và được phép; bảo vệ dữ liệu định danh |
| User-Agent family | `Android app`, `Java SDK` | Tín hiệu phụ, có thể giả mạo hoặc không ổn định |
| Source network | IP range hoặc ASN | Dùng bổ trợ, không làm định danh duy nhất |
| Correlation/request ID | `req-abc123` | Liên kết log qua nhiều service, không dùng làm identity |

Không dùng `User-Agent` hoặc IP làm bằng chứng duy nhất về consumer. Ưu tiên danh tính client được xác thực như OAuth client ID, mTLS workload identity hoặc API key identifier. Nếu chưa có định danh, ghi nhận consumer là `UNKNOWN`, kèm nguồn và mức tin cậy để triage.

### 4.1. Bảo vệ dữ liệu telemetry

Log traffic có thể chứa định danh cá nhân, ID tài khoản, query string, token hoặc dữ liệu nghiệp vụ. Chỉ thu thập metadata cần thiết để đo mức sử dụng. Không ghi `Authorization`, cookie, API key, refresh token hoặc request body nhạy cảm. Có thể hash/pseudonymize định danh để phân tích unique consumer, áp dụng quyền truy cập log và retention phù hợp.

Không đưa user ID, email, token hoặc object ID có cardinality lớn vào metric label nếu điều đó làm lộ dữ liệu hoặc tạo chi phí lưu trữ cao. Dùng metric tổng hợp và truy vấn log có kiểm soát khi cần điều tra một consumer cụ thể.

## 5. Đo những chỉ số nào?

Một dashboard trước khi retire nên thể hiện nhiều chiều, không chỉ tổng request.

### 5.1. Request volume và phân bố theo thời gian

- Tổng request theo ngày/tuần/tháng.
- Request theo method, route, version, host và environment.
- Peak traffic theo giờ và ngày trong tuần.
- Tỷ lệ thành công, `4xx`, `5xx`, timeout và request bị WAF/gateway chặn.
- Tỷ lệ retry và request trùng nếu có thể nhận diện.

Volume giúp hiểu xu hướng nhưng không chứng minh client nào còn hoạt động. Hãy xem cả tổng số và phân bố theo consumer.

### 5.2. Unique consumer và last seen

Với mỗi consumer, ghi nhận:

- Lần đầu nhìn thấy (`first seen`).
- Lần cuối nhìn thấy (`last seen`).
- Số ngày có hoạt động và số request trong cửa sổ đo.
- Tần suất và lịch gọi thường gặp.
- Endpoint/method được sử dụng.
- Status code và tỷ lệ thành công.
- Owner, ứng dụng, phiên bản và mục đích nghiệp vụ đã xác nhận.
- Endpoint thay thế và trạng thái migration.

Một client chỉ gọi một request trong 90 ngày vẫn là consumer đang hoạt động nếu request đó là một nghiệp vụ hợp lệ. `Last seen` cần được xem cùng lịch nghiệp vụ và owner confirmation.

### 5.3. Tác động nghiệp vụ

Request volume không cho biết request có tạo giao dịch thành công hay không. Với endpoint quan trọng, đo thêm business event hoặc kết quả xử lý:

- Số đơn hàng được tạo qua endpoint cũ.
- Số payment/refund/webhook được xử lý thành công.
- Số export hoặc báo cáo hoàn tất.
- Số callback đối tác được chấp nhận.
- Số tác vụ nền được khởi tạo hoặc hoàn thành.

Chỉ thu thập business metric ở mức tổng hợp và không ghi dữ liệu nhạy cảm không cần thiết. Đối chiếu request với event giúp phân biệt traffic thử nghiệm, health check và giao dịch thực.

### 5.4. Đo theo trạng thái consumer

Phân loại consumer thành các trạng thái có thể hành động:

| Trạng thái | Ý nghĩa | Hành động |
|---|---|---|
| `ACTIVE_CONFIRMED` | Có traffic gần đây và owner xác nhận còn dùng | Chưa tắt; hoàn tất migration |
| `ACTIVE_UNKNOWN_OWNER` | Có traffic nhưng chưa biết ai sở hữu | Tìm owner, không retire tự động |
| `MIGRATING` | Đã có traffic trên API mới nhưng vẫn gọi API cũ | Theo dõi song song và xác minh cutover |
| `NO_RECENT_TRAFFIC` | Không thấy traffic trong cửa sổ đã đo | Kiểm tra chu kỳ hiếm, độ phủ và owner |
| `MIGRATED_CONFIRMED` | Owner xác nhận chuyển xong, API mới hoạt động | Có thể đưa vào giai đoạn disable có kiểm soát |
| `EXEMPTED` | Có exception được phê duyệt và hạn chót | Ghi rõ lý do, owner, ngày hết hạn |

Không tự động đổi `NO_RECENT_TRAFFIC` thành `MIGRATED_CONFIRMED`. Hai trạng thái này có ý nghĩa khác nhau.

## 6. Chọn cửa sổ đo phù hợp với chu kỳ sử dụng

Độ dài cửa sổ cần dựa trên chu kỳ nghiệp vụ dài nhất mà endpoint có thể phục vụ, không chỉ dựa trên sự tiện lợi của dashboard.

Ví dụ:

- API được gọi liên tục bởi ứng dụng người dùng: cửa sổ vài tuần có thể cho thấy xu hướng, nhưng cần xét release cycle và người dùng hoạt động theo mùa.
- API tích hợp đối tác chạy hàng tháng: cần quan sát ít nhất một chu kỳ tháng đầy đủ, cộng thời gian để đối tác chạy job và xử lý retry.
- API báo cáo quý hoặc tác vụ cuối năm: cửa sổ 30 ngày không đủ; cần dữ liệu lịch sử dài hơn và xác nhận owner.
- API phục vụ sự kiện theo mùa: cần đối chiếu cùng mùa của năm trước hoặc kế hoạch sự kiện sắp tới.
- API khôi phục tài khoản/khẩn cấp: traffic hiếm không đồng nghĩa không cần; cần xác nhận có đường thay thế và quy trình hỗ trợ.

Không có một con số ngày phù hợp cho mọi endpoint. Hãy xác định chu kỳ tối đa dự kiến, thêm khoảng đệm cho lịch chạy trễ, ngày nghỉ, retry và sự cố; sau đó ghi rõ cửa sổ đo và các giới hạn dữ liệu.

### 6.1. Ví dụ chọn cửa sổ đo

Giả sử endpoint `/v1/reports/monthly` được gọi vào ngày làm việc đầu tiên của tháng. Nếu bắt đầu đo giữa tháng và kết thúc sau 30 ngày, cửa sổ có thể bỏ lỡ một lần gọi do lịch chạy đầu tháng. Cần đo qua ít nhất một chu kỳ chạy hoàn chỉnh và xác minh với owner rằng không có lịch quý/năm hoặc job thủ công.

Với endpoint thanh toán của đối tác, một tháng không có request có thể chỉ là tháng không có giao dịch. Cần xem hợp đồng tích hợp, webhook registration và kiểm tra đối tác có thể gửi sự kiện bất cứ lúc nào hay không. Có thể phải giữ endpoint callback hoặc chuyển tiếp endpoint cũ trong thời gian dài hơn.

### 6.2. Đừng coi log không có record là bằng chứng không có traffic

Trước khi kết luận zero traffic, xác minh retention, sampling, log pipeline, parser route và các khoảng mất dữ liệu. Kiểm tra cả metric gateway, access log upstream, trace và business event. Nếu một instance không gửi log hoặc một region không được thu thập, dữ liệu không đủ để đưa ra quyết định tắt.

## 7. Phân biệt consumer thật với traffic gây nhiễu

Traffic có thể đến từ nhiều nguồn không đại diện cho client nghiệp vụ:

- Health check và readiness/liveness probe.
- Synthetic monitoring hoặc uptime check.
- WAF scanner, crawler và bot.
- Retry của gateway, client SDK hoặc service mesh.
- Request nội bộ dùng để warm cache hoặc kiểm tra tương thích.
- Traffic test/staging bị gửi nhầm vào production.
- Client thử nghiệm hoặc script một lần.

Không xóa tất cả traffic này khỏi dữ liệu. Hãy phân loại và hiển thị riêng để hiểu tải thực tế. Ví dụ health check có thể cần giữ route `/health` nhưng không phải consumer của business endpoint; retry có thể làm số request cao hơn số giao dịch; synthetic test có thể chứng minh route còn hoạt động nhưng không chứng minh có client nghiệp vụ.

Đối với mỗi nhóm, xác định nguồn nhận diện và quy tắc phân loại. Không loại bỏ traffic chỉ vì nó có user-agent giống bot; client hợp lệ có thể dùng thư viện HTTP tự động. Giữ lại raw/aggregated evidence đủ để điều tra khi cần.

## 8. Đối chiếu traffic với inventory và owner

Sau khi thu thập dữ liệu, tạo bảng consumer cho từng endpoint/version. Ví dụ:

| Consumer | Last seen | Mức sử dụng | Owner | Migration | Quyết định |
|---|---|---:|---|---|---|
| `mobile-app-v4` | Hôm qua | Cao | Mobile team | Đang chuyển v2 | Chưa tắt |
| `partner-042` | 2 ngày trước | Thấp | Partner integration | Chưa xác nhận | Liên hệ partner |
| `billing-worker` | 30 ngày trước | 1 lần/tháng | Billing team | Đã có v2 nhưng chưa cutover | Chờ chu kỳ kế tiếp |
| `synthetic-monitor` | 1 phút trước | Rất cao | SRE | Không phải business consumer | Tách riêng, cập nhật probe |
| `unknown-client` | 10 ngày trước | Thấp | Chưa rõ | Chưa biết | Triage, chưa tắt |

Đây là ví dụ minh họa; trạng thái và thời gian phải lấy từ telemetry thực tế. Mỗi consumer còn hoạt động cần có owner/contact, mục đích, phiên bản client, dữ liệu sử dụng và kế hoạch chuyển đổi. Nếu không tìm được owner, ghi nhận là rủi ro tồn đọng thay vì coi như traffic vô danh có thể bỏ qua.

### 8.1. Liên hệ consumer và xác nhận migration

Đối với client nội bộ, liên hệ owner service/repository và xác minh deployment đang dùng endpoint mới. Đối với đối tác, dùng contact trong hợp đồng/portal, gửi ngày deprecation và hướng dẫn migration. Đối với mobile app, xem tỷ lệ phiên bản còn hoạt động và thời gian người dùng cập nhật app; không giả định mọi thiết bị cập nhật ngay sau khi phát hành bản mới.

Yêu cầu owner xác nhận bằng chứng cụ thể:

- Phiên bản client đã chuyển sang endpoint mới.
- Request trên endpoint mới thành công trong production.
- Các luồng lỗi, retry, webhook và tác vụ nền đã được chuyển.
- Không còn dependency hoặc cấu hình fallback trỏ tới endpoint cũ.
- Có kế hoạch rollback ở phía client nếu endpoint mới gặp sự cố.

## 9. Phát thông báo deprecation và theo dõi migration

Đo traffic nên bắt đầu trước ngày tắt đủ lâu để thông báo tới consumer và cho họ thời gian chuyển đổi. Một kế hoạch thường có các giai đoạn:

1. **Announce:** công bố endpoint/version bị ảnh hưởng, lý do, phiên bản thay thế, hướng dẫn và mốc thời gian.
2. **Observe:** thêm telemetry để nhận diện consumer, theo dõi traffic cũ/mới và xác minh độ phủ.
3. **Migrate:** hỗ trợ client, theo dõi tỷ lệ chuyển đổi, xử lý consumer chưa rõ owner.
4. **Warn:** phát tín hiệu deprecation và sunset trong response/documentation khi phù hợp.
5. **Rehearse:** mô phỏng việc từ chối hoặc tắt theo nhóm consumer trong môi trường an toàn.
6. **Disable:** tắt route theo kế hoạch đã phê duyệt, có rollback và giám sát.
7. **Verify:** xác minh không còn route, credential, DNS hoặc deployment ngoài dự kiến; cập nhật inventory.

### 9.1. Header deprecation và sunset

Có thể dùng các HTTP response header tiêu chuẩn để thông báo vòng đời:

- `Deprecation` theo RFC 9745 biểu thị tài nguyên/API đã bị đánh dấu deprecated; header có định dạng Structured Field Date. Có thể kèm `Link` với quan hệ `deprecation` để trỏ tới tài liệu giải thích.
- `Sunset` theo RFC 8594 thông báo thời điểm tài nguyên dự kiến không còn khả dụng; giá trị dùng định dạng HTTP-date.

Ví dụ `Sunset`:

```http
HTTP/1.1 200 OK
Sunset: Fri, 30 Apr 2027 00:00:00 GMT
Link: <https://developer.example.com/migrations/orders-v1>; rel="deprecation"
```

Ví dụ trên minh họa `Sunset` và link tài liệu. Khi phát `Deprecation`, cần serialize đúng Structured Field Date theo RFC 9745; không tự dùng chuỗi ngày tùy ý nếu thư viện không hỗ trợ định dạng này. Header chỉ là tín hiệu bổ sung: cần thông báo qua developer portal, email liên hệ đã đăng ký, changelog và tài liệu tích hợp.

Không dùng header deprecation thay cho xác nhận consumer. Một client có thể không đọc hoặc không ghi log các header này; một SDK cũ có thể bỏ qua chúng.

### 9.2. Theo dõi traffic cũ và traffic mới song song

Dashboard nên hiển thị:

- Request cũ theo consumer và endpoint.
- Request mới theo consumer và endpoint tương ứng.
- Consumer đã có traffic mới nhưng vẫn còn traffic cũ.
- Consumer chỉ có traffic cũ.
- Consumer chưa thấy ở cả hai phiên bản.
- Tỷ lệ lỗi và kết quả nghiệp vụ ở API mới.

Một consumer có request ở API mới chưa chắc đã cutover hoàn toàn. Có thể một luồng đã chuyển nhưng webhook hoặc fallback vẫn gọi API cũ. Cần đối chiếu theo use case/operation chứ không chỉ theo client ID tổng thể.

## 10. Thử nghiệm trước khi disable

Trước khi tắt production, thực hiện một buổi diễn tập có kiểm soát:

- Kiểm tra route mới xử lý các use case mà endpoint cũ từng hỗ trợ.
- Chạy contract/integration test với phiên bản client được hỗ trợ.
- Tìm hard-coded URL, DNS alias, config và retry fallback trong source code/deployment.
- Tắt endpoint trong staging hoặc môi trường tương đương để quan sát lỗi client.
- Nếu hạ tầng hỗ trợ, dùng chế độ shadow decision để ghi nhận request nào sẽ bị chặn nhưng vẫn cho phép xử lý trong giai đoạn diễn tập.
- Có thể thử deny theo một nhóm consumer đã xác nhận, với allowlist rollback và giám sát sát sao.

Không thực hiện “shadow disable” bằng cách giả vờ trả thành công nếu nghiệp vụ thực tế không được xử lý; điều đó có thể khiến client tin giao dịch đã hoàn tất. Chế độ quan sát chỉ nên ghi quyết định dự kiến, còn response thật phải phản ánh đúng kết quả xử lý.

### 10.1. Phản hồi khi endpoint đã retired

Sau khi tắt, có thể trả `410 Gone` để biểu thị endpoint/tài nguyên không còn khả dụng và việc ngừng là có chủ đích. `404 Not Found` có thể phù hợp nếu chính sách không muốn tiết lộ route hoặc nếu hạ tầng không phân biệt được. Hãy thống nhất hành vi và cung cấp đường dẫn migration an toàn nếu phù hợp.

Không redirect tự động mọi request cũ sang endpoint mới nếu method, body, authorization hoặc ngữ nghĩa nghiệp vụ đã thay đổi. Redirect có thể làm client gửi credential hoặc payload tới host/path khác; với request ghi dữ liệu, hành vi redirect còn phụ thuộc status code và client. Tốt hơn là trả lỗi có hướng dẫn rõ ràng để client chủ động migration.

## 11. Tiêu chí go/no-go trước khi tắt

Quyết định disable nên dựa trên bằng chứng và được owner/service owner phê duyệt.

### Go — có thể tiến hành tắt khi

- Phạm vi host, method, route, version và môi trường đã được xác định đầy đủ.
- Telemetry bao phủ tất cả đường truy cập và cửa sổ đo đủ dài so với chu kỳ nghiệp vụ.
- Không còn consumer hợp lệ chưa được giải quyết; mọi consumer đã xác nhận migration hoặc có exception được phê duyệt.
- Traffic còn lại chỉ là traffic đã phân loại và có kế hoạch xử lý, ví dụ probe đã được chuyển hoặc scanner không phải client nghiệp vụ.
- Endpoint thay thế đã được xác minh trong production cho các use case cần thiết.
- Owner, đối tác và đội hỗ trợ đã nhận thông báo theo kế hoạch.
- Có rollback plan, người trực và dashboard giám sát trong thời gian disable.

### No-go — chưa được tắt khi

- Có traffic thành công từ consumer chưa rõ owner.
- Cửa sổ đo không bao phủ chu kỳ tháng/quý/năm hoặc mùa cao điểm liên quan.
- Một region, gateway, host hoặc instance không có telemetry đáng tin cậy.
- Client mới chỉ được phát hành nhưng chưa có bằng chứng production migration.
- Endpoint mới chưa hỗ trợ đầy đủ webhook, batch, error handling hoặc use case đặc biệt.
- Có exception chưa được phê duyệt hoặc chưa có hạn chót.
- Không có cách khôi phục route/credential/config nếu phát sinh sự cố.

Không nên đặt tiêu chí “zero request trong 7 ngày” làm điều kiện duy nhất. Một endpoint ít dùng có thể hợp lệ; ngược lại, một endpoint có traffic cao do scanner không có nghĩa cần giữ nó. Cần đánh giá consumer và tác động nghiệp vụ.

## 12. Kế hoạch rollback và xác minh sau khi tắt

Rollback cần được chuẩn bị trước, không đợi đến khi client gặp lỗi mới tìm cách khôi phục.

Kế hoạch nên xác định:

- Ai có quyền bật lại route và trong thời gian bao lâu?
- Cấu hình gateway/ingress, deployment và DNS nào cần khôi phục?
- Credential/client registration cũ đã thu hồi chưa; có thể khôi phục an toàn hay phải cấp credential mới?
- Có thay đổi database hoặc schema khiến API cũ không còn tương thích không?
- Cách nhận diện request thất bại và liên hệ consumer bị ảnh hưởng?
- Điều kiện kết thúc rollback và kế hoạch migration lại?

Trong một khoảng giám sát sau disable, theo dõi request bị từ chối tới route cũ, `404`/`410`, lỗi từ client, ticket hỗ trợ, webhook thất bại và business metric bị giảm. Không log payload/token chỉ để biết client nào bị ảnh hưởng; dùng client ID, request ID và metadata đã chuẩn hóa.

Sau khi xác minh ổn định:

1. Tắt route và deployment liên quan.
2. Thu hồi API key, OAuth client registration hoặc credential không còn cần.
3. Gỡ DNS/ingress/load balancer/certificate liên quan nếu không dùng cho tài sản khác.
4. Xóa hoặc cập nhật tài liệu và SDK cũ; giữ migration guide/lịch sử cần thiết.
5. Cập nhật inventory thành `RETIRED` cùng ngày, owner và bằng chứng.
6. Xác minh lại bằng discovery từ gateway, cloud, DNS, source và runtime.

## 13. Ví dụ truy vấn tổng hợp traffic

Giả sử access log đã được chuẩn hóa vào bảng `api_access_events`. Truy vấn dưới đây minh họa cách tổng hợp theo consumer và route:

```sql
SELECT
    api_version,
    http_method,
    route_template,
    client_id,
    MAX(event_time) AS last_seen,
    COUNT(*) AS request_count,
    COUNT(DISTINCT CAST(event_time AS DATE)) AS active_days,
    SUM(CASE WHEN status_code BETWEEN 200 AND 299
             THEN 1 ELSE 0 END) AS success_count,
    SUM(CASE WHEN status_code BETWEEN 400 AND 599
             THEN 1 ELSE 0 END) AS error_count
FROM api_access_events
WHERE environment = 'production'
  AND host = 'legacy-api.example.com'
  AND route_template = '/v1/orders/{orderId}'
  AND event_time >= :windowStart
  AND event_time < :windowEnd
GROUP BY api_version, http_method, route_template, client_id
ORDER BY last_seen DESC;
```

Đây là truy vấn minh họa; cú pháp date cast và schema log phụ thuộc database. Cần lọc đúng method/version/host, loại trừ hoặc phân nhóm probe/test traffic và xử lý client ID null thành nhóm `UNKNOWN`. Nếu log bị sampling, `COUNT(*)` không phải tổng request thực tế; cần dùng metric counter không sampling để đo volume và log để điều tra consumer.

Không đưa raw token, API key hoặc user PII vào bảng sự kiện. `client_id` phải là định danh đã được xác thực hoặc đã pseudonymize theo chính sách.

## 14. Kiểm thử trước và sau khi disable

| Kịch bản | Cách kiểm tra | Kết quả mong đợi |
|---|---|---|
| Consumer hoạt động thường xuyên | Gọi endpoint từ client đã đăng ký | Có telemetry đúng client, route và method |
| Consumer định kỳ | Chạy job theo lịch tháng/quý trong test | Cửa sổ đo/owner xác nhận phản ánh chu kỳ |
| Consumer không có ID | Gọi qua đường chưa xác thực hoặc credential không map được | Ghi nhóm unknown để triage |
| Traffic bypass gateway | Gọi qua ingress/host trực tiếp trong môi trường test | Nguồn telemetry khác phát hiện request |
| Log pipeline mất dữ liệu | Tắt collector hoặc tạo khoảng gap test | Dashboard đánh dấu coverage thiếu, không kết luận zero traffic |
| Retry/synthetic traffic | Tạo probe và retry có nhận diện | Phân nhóm riêng, không tính nhầm thành consumer nghiệp vụ |
| Client đã migration | Gọi API mới và cũ theo từng use case | Xác nhận không còn luồng quan trọng gọi API cũ |
| Endpoint mới lỗi | Tạo lỗi có kiểm soát trong staging | Go/no-go bị chặn nếu use case chưa đáp ứng |
| Disable canary | Chặn một nhóm consumer test | Phát hiện lỗi và rollback hoạt động |
| Request sau retirement | Gọi route đã tắt | Trả `410`/`404` theo contract, không xử lý nghiệp vụ |
| Credential cũ | Thử credential sau khi thu hồi | Bị từ chối và không có fallback quyền rộng |
| Discovery sau retire | Quét lại các nguồn inventory | Không còn route/deployment/alias ngoài dự kiến |

## 15. Checklist trước khi tắt endpoint

- [ ] Đã xác định host, environment, version, method và route template chính xác.
- [ ] Đã đo từ gateway, ingress/load balancer, service log, mesh và các đường truy cập trực tiếp.
- [ ] Đã kiểm tra telemetry coverage, sampling, retention và khoảng mất dữ liệu.
- [ ] Đã nhận diện consumer bằng client/workload/partner ID; không dựa riêng vào IP hoặc User-Agent.
- [ ] Đã đo volume, unique consumer, last seen, active days và business outcome.
- [ ] Đã phân loại health check, scanner, retry, test và traffic nghiệp vụ.
- [ ] Cửa sổ đo bao phủ chu kỳ sử dụng dài nhất có liên quan và có buffer phù hợp.
- [ ] Consumer chưa rõ owner đã được triage; consumer còn hoạt động có owner và migration plan.
- [ ] API mới đã được kiểm chứng production cho tất cả use case, webhook và batch cần thiết.
- [ ] Đã thông báo deprecation/sunset và theo dõi traffic cũ/mới song song.
- [ ] Đã diễn tập disable/canary và có tiêu chí go/no-go rõ ràng.
- [ ] Có rollback plan, người trực, dashboard và cách khôi phục route/credential.
- [ ] Sau khi tắt, đã xác minh route, DNS, ingress, deployment và credential được xử lý đúng.
- [ ] Inventory được cập nhật `RETIRED` với bằng chứng và thời điểm xác minh.

## Kết luận

Đo traffic trước khi tắt endpoint là quá trình xác định consumer và tác động nghiệp vụ bằng telemetry có độ phủ đủ tin cậy. Cần đo theo host, method, route, version và client identity; xem cả last seen, unique consumer, lịch gọi và business outcome; chọn cửa sổ phù hợp với chu kỳ sử dụng; rồi đối chiếu với inventory và xác nhận owner. Chỉ disable khi migration đã được chứng minh, consumer còn lại đã được xử lý và rollback sẵn sàng. Traffic bằng không trong một khoảng ngắn không phải bằng chứng đủ để retire API an toàn.
