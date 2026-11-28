# Federation error rate

## 1. Chỉ số lỗi liên kết danh tính đo điều gì?

**Identity federation**, hay liên kết danh tính, cho phép một hệ thống dựa vào kết quả xác thực do hệ thống danh tính khác cung cấp. Trong một luồng đăng nhập liên kết, ứng dụng không chỉ cần nhận được phản hồi từ bên ngoài: nó phải xác minh nguồn phát hành, tính toàn vẹn, đối tượng nhận, thời hạn và mối liên hệ với giao dịch đăng nhập đang thực hiện trước khi thiết lập phiên cục bộ.

**Federation error rate** là tỷ lệ giao dịch liên kết danh tính gặp nhóm lỗi đã định nghĩa trong một phạm vi và khoảng thời gian xác định. Chỉ số giúp nhận ra những vấn đề như cấu hình trust sai, lỗi trao đổi code, chứng thư hoặc khóa ký không khớp, lỗi xác minh assertion/token, gián đoạn mạng và lỗi hoàn tất phiên tại ứng dụng.

Các thuật ngữ thường gặp:

| Thuật ngữ | Vai trò trong luồng |
| --- | --- |
| Identity Provider, IdP | Hệ thống cung cấp dịch vụ xác thực và phát hành kết quả danh tính |
| Relying Party, RP | Ứng dụng dựa vào kết quả danh tính, thường dùng trong ngữ cảnh OpenID Connect |
| Service Provider, SP | Ứng dụng sử dụng assertion từ IdP, thường dùng trong ngữ cảnh SAML |
| Identity broker | Trung gian kết nối nhiều IdP với ứng dụng; có thể đóng vai trò khác nhau ở hai phía |
| Trust configuration | Cấu hình xác định bên được tin cậy, khóa/chứng thư, issuer, audience và các ràng buộc liên quan |

Ví dụ, nhân viên đăng nhập cổng nội bộ qua IdP doanh nghiệp bằng OpenID Connect. Người dùng đã hoàn thành MFA tại IdP nhưng ứng dụng vẫn không nhận được phiên đăng nhập vì cấu hình audience sai. Đây là lỗi ở luồng federation sau bước xác thực tại IdP; không thể kết luận MFA hoặc mật khẩu là nguyên nhân.

Ngược lại, người dùng đăng nhập liên kết thành công nhưng không có quyền duyệt hóa đơn là vấn đề authorization. Nếu gộp cả hai loại vào một tỷ lệ, đội vận hành khó xác định nên kiểm tra trust, phiên đăng nhập hay chính sách quyền.

## 2. Xác định ranh giới của một giao dịch

### 2.1. Đo ở góc nhìn của bên sử dụng danh tính

Trong bài này, một giao dịch federation bắt đầu khi RP/SP chấp nhận yêu cầu đăng nhập liên kết và tạo ngữ cảnh tương quan phía máy chủ. Giao dịch thành công khi RP/SP đã chấp nhận kết quả danh tính và hoàn tất việc thiết lập phiên cục bộ theo luồng đã chọn.

```text
RP/SP tạo giao dịch đăng nhập
  → chuyển người dùng sang IdP
  → người dùng tương tác và xác thực tại IdP
  → RP/SP nhận phản hồi liên kết
  → trao đổi code nếu luồng yêu cầu, xác minh kết quả danh tính
  → thiết lập phiên cục bộ
```

Đây là hợp đồng quan sát minh họa, không phải mọi sản phẩm đều đặt ranh giới giống nhau. Có hệ thống chỉ đo đến lúc xác minh assertion/token, còn tạo phiên là một chỉ số riêng. Khi triển khai, phải ghi rõ điểm bắt đầu và điểm kết thúc; không so sánh trực tiếp các tỷ lệ có ranh giới khác nhau.

`OAuth 2.0` tự nó là cơ chế ủy quyền, không phải giao thức đăng nhập danh tính. Trong trường hợp đăng nhập dựa trên OpenID Connect, cần quan sát đúng luồng OIDC và kiểm tra ID token theo hợp đồng của ứng dụng. Không coi việc nhận được một access token bất kỳ là bằng chứng giao dịch đăng nhập liên kết đã hoàn tất.

### 2.2. Phân biệt giao dịch với request và lần thử nội bộ

Một giao dịch có thể gồm nhiều HTTP request: redirect, callback, gọi token endpoint, tải metadata hoặc lấy khóa. Vì vậy số request lỗi không phải số giao dịch federation lỗi.

Ví dụ, lần gọi token endpoint đầu tiên timeout nhưng retry được thực hiện an toàn theo cơ chế của thư viện và giao dịch cuối cùng thành công. Ở mức giao dịch, kết quả là một `success`; ở mức phụ thuộc, vẫn có một lần gọi bị timeout. Cần giữ cả hai góc nhìn để không che giấu độ bất ổn của phụ thuộc, nhưng không cộng timeout nội bộ thành một giao dịch lỗi bổ sung.

Không tự giả định mọi thao tác đều có thể retry. Authorization code thường có ràng buộc sử dụng một lần; sau timeout, bên gọi có thể chưa biết IdP đã xử lý yêu cầu hay chưa. Chiến lược retry phải theo giao thức, thư viện và hợp đồng của nhà cung cấp. Telemetry phản ánh kết quả thực tế thay vì tự gửi lại callback hoặc code để kiểm tra.

Nếu người dùng khởi động một giao dịch đăng nhập mới, đó là một giao dịch khác. Muốn biết bao nhiêu người dùng cuối cùng đăng nhập được sau nhiều lần thử, cần một phép đo hành trình riêng với quy tắc liên kết và bảo vệ dữ liệu phù hợp.

## 3. Định nghĩa công thức bằng các kết quả loại trừ nhau

Không có một con số có ý nghĩa nếu chưa xác định “error” gồm những gì. Trong bài này, mỗi giao dịch có đúng một kết quả cuối cùng:

| `result` | Ý nghĩa | Thuộc tử số lỗi federation? |
| --- | --- | --- |
| `success` | Kết quả danh tính được chấp nhận và phiên cục bộ đã hoàn tất | Không |
| `technical_error` | Không hoàn tất do lỗi xử lý, cấu hình, phụ thuộc hoặc giao thức | Có |
| `validation_rejected` | Phản hồi không vượt qua kiểm tra trust, tính toàn vẹn hoặc tương quan | Có, nhưng cần xem tách riêng |
| `provider_denied` | RP/SP nhận và chấp nhận phản hồi từ chối theo luồng hợp lệ, chẳng hạn không đáp ứng điều kiện truy cập của IdP | Không |
| `user_cancelled` | Có tín hiệu hợp lệ cho biết người dùng đã hủy hoặc từ chối tương tác | Không |
| `expired` | Giao dịch hết hạn mà chưa xác định được một kết quả thuộc các nhóm trên | Không đưa vào công thức chính; theo dõi riêng |

Đây là các nhóm quan sát của hệ thống, không phải danh sách tên lỗi bắt buộc của một giao thức. Cần có quy tắc ánh xạ rõ và ổn định từ kết quả thư viện/giao thức sang từng nhóm. Nếu IdP không cung cấp đủ tín hiệu để phân biệt người dùng hủy với từ chối chính sách, không tự suy đoán: ghi nhận nhóm phù hợp với bằng chứng và giữ một nguyên nhân tổng quát.

Trong cửa sổ thời gian `W`, đặt:

```text
S = số success
E = số technical_error
R = số validation_rejected
D = số provider_denied
C = số user_cancelled

T = S + E + R + D + C

federation_error_rate = (E + R) / T
federation_error_percent = 100 × (E + R) / T
```

`T` là số giao dịch có kết quả đã phân loại trong cửa sổ. `expired` và giao dịch còn đang diễn ra không nằm trong mẫu số này. Quyết định loại chúng ra cần hiển thị rõ trên dashboard, vì tỷ lệ chính có thể ổn định trong khi rất nhiều người dùng không quay lại callback.

Nên trình bày thêm:

```text
technical_error_rate     = E / T
validation_rejected_rate = R / T
federation_success_rate  = S / T
```

`1 - federation_error_rate` không bằng `federation_success_rate`, vì mẫu số còn có từ chối hợp lệ và hủy tương tác. Tương tự, tỷ lệ lỗi thấp không tự động chứng minh trải nghiệm đăng nhập tốt nếu nhiều giao dịch hết hạn hoặc bị từ chối theo chính sách.

### 3.1. Ví dụ số liệu

Trong 15 phút, hệ thống ghi nhận:

| Kết quả đã phân loại | Số giao dịch |
| --- | ---: |
| `success` | 9.400 |
| `technical_error` | 200 |
| `validation_rejected` | 100 |
| `provider_denied` | 200 |
| `user_cancelled` | 100 |
| Tổng `T` | 10.000 |

Tỷ lệ lỗi federation là `(200 + 100) / 10.000 = 3%`. Trong đó lỗi kỹ thuật chiếm 2%, phản hồi bị từ chối khi xác minh chiếm 1%, còn tỷ lệ thành công trên các kết quả đã phân loại là 94%.

Nếu có thêm 300 giao dịch `expired` trong cùng cửa sổ, cần hiển thị số này ở panel riêng. Không tự cộng chúng vào công thức chính rồi tiếp tục so sánh với baseline 3% có mẫu số khác. Có thể tạo chỉ số trên toàn bộ giao dịch đã đóng gồm cả `expired`, nhưng phải đặt tên và định nghĩa riêng.

Khi `T = 0`, tỷ lệ là không xác định. Không hiển thị 0% như thể hệ thống đã xử lý thành công toàn bộ lưu lượng; có thể đang không có tải, luồng đang treo hoặc pipeline giám sát không nhận được dữ liệu.

## 4. Đếm theo thời điểm kết thúc và xử lý giao dịch hết hạn

### 4.1. Không trộn số bắt đầu với số hoàn tất trong cùng một cửa sổ

Một giao dịch bắt đầu lúc 09:59 có thể kết thúc lúc 10:01. Nếu chia số lỗi kết thúc trong cửa sổ 10:00–10:05 cho số giao dịch bắt đầu trong chính cửa sổ đó, tử và mẫu thuộc hai tập khác nhau. Sai lệch càng rõ khi người dùng cần thời gian nhập MFA hoặc khi lưu lượng tăng giảm nhanh.

Đối với chỉ số vận hành trong bài, cả tử và mẫu được ghi nhận khi giao dịch có kết quả cuối cùng. Đây là cách quan sát theo thời điểm kết thúc. Nếu muốn đo tỷ lệ thành công của tập giao dịch bắt đầu trong một khoảng cụ thể, cần phân tích theo cohort: theo dõi đúng tập đó đến khi kết thúc hoặc đến mốc quan sát đã định, rồi báo cả phần chưa có kết quả.

Không tính `số started - số success trong 5 phút` là số federation error của 5 phút. Phần chênh lệch có thể gồm giao dịch còn tương tác, giao dịch bắt đầu từ trước cửa sổ hoặc giao dịch hết hạn chưa được đóng.

### 4.2. Hết hạn không tự chứng minh IdP bị lỗi

Người dùng có thể đóng trình duyệt, mất mạng, bỏ qua MFA hoặc không muốn tiếp tục. Cũng có thể browser không gửi cookie cần thiết, callback bị chặn hoặc IdP không phản hồi. Nếu không có bằng chứng bổ sung, `expired` chỉ cho biết ngữ cảnh giao dịch đã hết thời gian chờ.

Theo dõi thêm số giao dịch bắt đầu, số đang chờ, phân bố thời gian tồn tại, số hết hạn và độ trễ hoàn tất. Khi tính tỷ lệ hết hạn theo cohort, cần chờ đủ thời gian để tập quan sát trưởng thành; không so sánh một cohort mới bắt đầu với cohort đã có đủ thời gian kết thúc.

### 4.3. Một giao dịch chỉ đóng một lần

Callback trùng, worker xử lý timeout và tác vụ dọn giao dịch hết hạn có thể chạy đồng thời. Cần chuyển trạng thái cuối cùng một cách nguyên tử để chỉ một kết quả được ghi nhận cho mỗi giao dịch tại ranh giới đã chọn.

Nếu giao dịch đã được đóng là `expired`, một callback đến muộn phải xử lý theo chính sách an toàn và ghi sự kiện chẩn đoán phù hợp. Không tăng thêm một kết quả cuối cùng khác cho cùng giao dịch. Việc xử lý phản hồi muộn không được bỏ qua kiểm tra tương quan hoặc mở lại giao dịch một cách tùy tiện.

Định danh nội bộ giúp chống trùng phải độc lập với dữ liệu bí mật. Không đưa nguyên giá trị `state`, authorization code hay assertion vào metric hoặc log để làm khóa đối chiếu.

## 5. Phân loại lỗi theo giai đoạn và bằng chứng

### 5.1. Các giai đoạn quan sát

| Giai đoạn | Ví dụ vấn đề | Hướng kiểm tra |
| --- | --- | --- |
| Khởi tạo và chọn kết nối | Chọn sai cấu hình IdP, client hoặc trust relationship | Cấu hình ứng dụng và kết nối thực tế được sử dụng |
| Chuyển hướng và tương tác | URI không khớp, trình duyệt không quay lại, người dùng hủy | Nhật ký an toàn của RP/IdP, cấu hình redirect và hành vi trình duyệt |
| Nhận callback/phản hồi | Thiếu ngữ cảnh giao dịch, phản hồi trùng, không ghép được tương quan | Kho giao dịch, cookie cần thiết, thời gian tồn tại, tầng cân bằng tải |
| Trao đổi code | Timeout, client authentication thất bại, code không được chấp nhận | Kết quả token endpoint và cấu hình client; không log code/secret |
| Xác minh kết quả | Chữ ký không hợp lệ, issuer/audience sai, assertion/token hết hạn | Khóa/chứng thư và ràng buộc được cấu hình cho đúng kết nối |
| Hoàn tất phiên cục bộ | Không tạo được session, lỗi lưu trạng thái hoặc mapping danh tính | Kho session, quy tắc mapping và ràng buộc tài khoản cục bộ |

Một số giai đoạn không xuất hiện trong mọi giao thức hoặc mọi flow. Luồng OIDC authorization code thường có bước đổi code tại token endpoint; một luồng SAML dùng assertion không vì thế mà có cùng bước đổi code. Chỉ đưa vào dashboard các giai đoạn có ý nghĩa với cấu hình được hỗ trợ.

### 5.2. Nhóm xác minh cần tách khỏi lỗi hạ tầng

Các nguyên nhân như `signature_invalid`, `issuer_mismatch`, `audience_mismatch`, `correlation_failed` hoặc `replay_detected` nên được phân biệt trong sự kiện chẩn đoán. Chúng có thể xuất phát từ cấu hình sai, dữ liệu cũ, giao dịch bị trộn hoặc một phản hồi không đáng tin cậy.

`validation_rejected` không tự động chứng minh có tấn công. Sau luân chuyển khóa, một tập ứng dụng giữ metadata cũ có thể từ chối phản hồi hợp lệ của IdP. Tuy vậy, cũng không được coi mọi phản hồi bị từ chối là lỗi thư viện rồi tắt kiểm tra chữ ký để “khôi phục đăng nhập”.

Với SAML, kiểm tra phải theo profile và flow được hỗ trợ, gồm nguồn phát hành, chữ ký, thời hạn, đối tượng nhận và quy tắc tương quan thích hợp. Không áp dụng máy móc một điều kiện của luồng SP-initiated cho mọi luồng IdP-initiated mà không xét hợp đồng đã thiết kế.

Với OIDC, việc xác minh ID token và ràng buộc giao dịch cần theo flow, thư viện và cấu hình của RP. Các tín hiệu như issuer, audience, chữ ký, thời hạn, `state` và `nonce` có vai trò khác nhau; không thay thế tất cả bằng việc giải mã payload hoặc nhìn thấy HTTP 200.

### 5.3. Không phân loại chỉ bằng mã HTTP hoặc chuỗi lỗi

Callback trả 200 có thể chỉ là trang báo đăng nhập thất bại. Redirect 302 có thể dẫn đến phiên thành công hoặc trang lỗi. Token endpoint trả lỗi cũng chưa đủ để kết luận IdP mất sẵn sàng: yêu cầu có thể dùng sai client authentication hoặc code đã hết hiệu lực.

Tương tự, một phản hồi mang `access_denied` cần được xử lý trong đúng ngữ cảnh giao dịch trước khi được tính là từ chối hợp lệ. Nếu phản hồi không vượt qua kiểm tra tương quan, không tin ngay nội dung lỗi do bên ngoài gửi để phân loại nó thành `provider_denied`.

Ánh xạ nên dựa trên kết quả xử lý cuối cùng của thư viện và ứng dụng, kèm giai đoạn cùng nguyên nhân đã chuẩn hóa. Không dùng toàn bộ thông báo lỗi từ upstream làm nhãn metric hoặc hiển thị trực tiếp cho người dùng.

## 6. Thiết kế metric và sự kiện chẩn đoán

### 6.1. Counter giao dịch

Một metric minh họa:

```text
iam_federation_transactions_total{
  environment="production",
  service="employee-portal",
  protocol="oidc",
  connection="corporate",
  result="technical_error"
}
```

Counter tăng một lần khi giao dịch đóng, kể cả nhóm `expired` nếu hệ thống có tác vụ đóng giao dịch hết hạn. Mỗi nhãn phải có tập giá trị được quản lý: môi trường, ứng dụng, giao thức và alias của kết nối đã cấu hình. Với hệ thống có hàng nghìn kết nối khách hàng, cần đánh giá cách tổng hợp và giới hạn nhãn thay vì mặc định tạo mọi kết hợp trên toàn bộ hạ tầng.

Không dùng email, subject ID, tenant ID động, URL callback nguyên bản, issuer tùy ý từ request hoặc `transaction_id` làm nhãn. Không để dữ liệu do bên ngoài gửi tạo ra chuỗi thời gian mới không giới hạn. Khi cần phân tích chi tiết theo khách hàng, dùng hệ thống sự kiện có kiểm soát truy cập và cơ chế truy vấn phù hợp.

Nên có thêm metric cho độ trễ hoàn tất, giao dịch đang chờ và sức khỏe các phụ thuộc. Độ trễ toàn giao dịch có thể bao gồm thời gian người dùng nhập mật khẩu/MFA; phải tách khỏi độ trễ máy chủ, gọi token endpoint hoặc tải khóa để chẩn đoán đúng.

### 6.2. Event phục vụ điều tra

Ví dụ một sự kiện đã giảm dữ liệu nhạy cảm:

```json
{
  "event_type": "federation_transaction_closed",
  "timestamp": "2026-01-15T08:30:00Z",
  "environment": "production",
  "service": "employee-portal",
  "protocol": "oidc",
  "connection": "corporate",
  "transaction_ref": "fed-example-021",
  "trace_id": "trace-example-864",
  "result": "validation_rejected",
  "stage": "identity_validation",
  "reason_class": "audience_mismatch",
  "trust_config_version": "corporate-trust-v8",
  "application_version": "portal-example-v23",
  "elapsed_ms": 4280
}
```

`transaction_ref` là định danh nội bộ dành cho quan sát, không phải bản sao authorization code hoặc giá trị `state`. Có thể lưu thêm một số thông tin vận hành có kiểm soát như alias khóa đang dùng hoặc dấu mốc refresh metadata, nhưng tránh lưu toàn bộ tài liệu định danh chỉ để phục vụ tìm lỗi.

Không ghi raw ID token, access token, refresh token, SAML assertion, client secret, session cookie hoặc URL chứa code. Những dữ liệu này có thể chứa thông tin cá nhân hoặc vật liệu truy cập. Thông báo lỗi chi tiết của nhà cung cấp cũng cần lọc trước khi lưu vì có thể chứa nội dung yêu cầu.

### 6.3. Độ đầy đủ của telemetry

Tỷ lệ tính từ log lấy mẫu không đồng đều có thể sai. Nếu giữ mọi lỗi nhưng chỉ giữ 1% sự kiện thành công, phép chia trên số log thô sẽ phóng đại tỷ lệ lỗi. Counter giao dịch đầy đủ và log chẩn đoán có kiểm soát thường phục vụ hai mục đích khác nhau.

Theo dõi lỗi xuất metric/event, số sự kiện bị bỏ, độ trễ pipeline và độ phủ của các instance. Với pipeline có cơ chế gửi lại, phải chống trùng khi tổng hợp event thành counter. Không cộng trực tiếp log RP, log broker và log IdP như thể đó là các giao dịch độc lập ở cùng một ranh giới.

## 7. Ví dụ tính tỷ lệ bằng PromQL

Các truy vấn dưới đây giả định metric có đúng sáu nhóm `result` đã định nghĩa. Tử số và mẫu số dùng cùng tập nhãn tổng hợp.

### 7.1. Tỷ lệ lỗi theo dịch vụ và kết nối trong 15 phút

```promql
100 *
sum by (environment, service, connection, protocol) (
  rate(iam_federation_transactions_total{
    result=~"technical_error|validation_rejected"
  }[15m])
)
/
sum by (environment, service, connection, protocol) (
  rate(iam_federation_transactions_total{
    result=~"success|technical_error|validation_rejected|provider_denied|user_cancelled"
  }[15m])
)
```

Kết quả có đơn vị phần trăm. Dùng `rate()` trên từng counter trước khi cộng để xử lý counter reset của từng tiến trình. Nhóm `expired` được loại rõ bằng bộ lọc mẫu số.

Đặt cạnh tỷ lệ là số giao dịch đã phân loại:

```promql
sum by (environment, service, connection, protocol) (
  increase(iam_federation_transactions_total{
    result=~"success|technical_error|validation_rejected|provider_denied|user_cancelled"
  }[15m])
)
```

`increase()` dựa trên dữ liệu scrape và có thể cho số không nguyên; nó phục vụ vận hành, không thay thế bản ghi audit cần đối soát chính xác từng giao dịch.

### 7.2. Xem lỗi theo từng nhóm kết quả

```promql
sum by (environment, service, connection, protocol, result) (
  increase(iam_federation_transactions_total{
    result=~"technical_error|validation_rejected|expired"
  }[15m])
)
```

Truy vấn này trả số lượng theo nhóm, không phải tỷ lệ. Nó giúp nhận ra một đợt tăng chỉ thuộc `validation_rejected`, hoặc tỷ lệ chính ít biến động nhưng `expired` tăng mạnh. Muốn nhìn giai đoạn hay nguyên nhân sâu hơn, truy vấn event theo kết nối và khoảng thời gian tương ứng.

Nếu một kết quả chưa từng xuất hiện, chuỗi metric có thể chưa được tạo. Cần khởi tạo trước các tổ hợp nhãn hữu hạn cần thiết hoặc xử lý trường hợp thiếu chuỗi theo thiết kế dashboard. Không dùng giá trị 0 mặc định để che mất dữ liệu. Mẫu số bằng 0 và mất thu thập phải có trạng thái quan sát riêng.

### 7.3. Ngưỡng cảnh báo phải đi cùng lưu lượng và ý nghĩa lỗi

Một rule minh họa có thể yêu cầu tỷ lệ lỗi vượt 2%, ít nhất 500 kết quả đã phân loại trong 15 phút và điều kiện duy trì 10 phút. Đây là ví dụ cách giảm cảnh báo nhiễu, không phải ngưỡng chuẩn cho mọi hệ thống.

Đối với kết nối ít người dùng nhưng quan trọng, điều kiện 500 có thể khiến một sự cố toàn phần không bao giờ cảnh báo. Cần thêm phép thử tổng hợp hoặc rule theo số lần thất bại liên tiếp. Một đợt `validation_rejected` lớn cũng cần tuyến điều tra riêng vì có thể liên quan trust hoặc phản hồi đáng ngờ, không chỉ mất sẵn sàng.

So sánh baseline theo ứng dụng, giao thức và kết nối. Không lấy trung bình đơn giản các phần trăm của nhiều IdP để ra tỷ lệ toàn hệ thống; cần cộng tử số và mẫu số tương ứng rồi chia, đồng thời giữ panel chi tiết để không che một kết nối nhỏ đang hỏng.

## 8. Các mẫu biến động và giả thuyết cần kiểm chứng

| Mẫu quan sát | Giả thuyết | Bằng chứng cần đối chiếu |
| --- | --- | --- |
| Lỗi chữ ký tăng sau luân chuyển khóa | RP/SP còn dùng khóa cũ hoặc trust mới không đúng | Phiên bản cấu hình, thời điểm refresh, kết quả xác minh khóa |
| Audience/issuer mismatch chỉ ở một ứng dụng | Cấu hình client hoặc trust relationship sai | Kết nối thực tế, môi trường, audience/issuer được cấu hình |
| Timeout ở nhiều ứng dụng cùng kết nối | Vấn đề mạng hoặc phụ thuộc IdP/broker | DNS, TLS, độ trễ và lỗi của endpoint liên quan |
| Correlation failed chỉ ở một nhóm trình duyệt | Ngữ cảnh giao dịch hoặc cookie không được giữ đúng | Thuộc tính cookie, redirect, kho giao dịch, tuyến xử lý callback |
| Giao dịch hết hạn tăng nhưng ít phản hồi lỗi | Người dùng không quay lại hoặc callback không tới nơi | Giao dịch đang chờ, truy cập callback, tín hiệu phía IdP nếu có |
| Provider denied tăng, lỗi kỹ thuật ổn định | Chính sách IdP, consent hoặc điều kiện truy cập thay đổi | Sự kiện policy và kết quả đã được xác nhận từ IdP |
| Federation thành công nhưng API trả 403 | Quyền ứng dụng hoặc mapping role có vấn đề sau đăng nhập | Quyết định authorization và quyền dự kiến |
| Chỉ lỗi khi tải tăng | Nút thắt kho giao dịch/session hoặc phụ thuộc | Độ trễ, timeout, độ đầy đủ và phân bố tải giữa instance |

Mỗi hàng là một giả thuyết để điều tra. Không khẳng định IdP gặp sự cố chỉ vì RP ghi nhiều lỗi, và không khẳng định có tấn công chỉ vì xuất hiện chữ ký không hợp lệ. Bằng chứng phải đi cùng giai đoạn, phạm vi và thời điểm thay đổi.

Trong kiến trúc có broker, nên có góc nhìn đầu cuối tại RP và các góc nhìn từng chặng tại broker. Một giao dịch đầu cuối lỗi có thể làm nhiều chặng ghi sự kiện; các số liệu này hỗ trợ tương quan, không được cộng thành số người dùng bị ảnh hưởng. Có thể dùng định danh liên kết nội bộ phù hợp nhưng không chuyển credential hoặc dữ liệu nhận dạng không cần thiết qua toàn bộ hệ thống log.

## 9. Runbook điều tra lỗi federation

### Bước 1: Xác minh định nghĩa và dữ liệu

Kiểm tra đúng counter, ranh giới giao dịch, bộ lọc kết quả, mẫu số và cửa sổ thời gian. Nhìn cả số lỗi, số thành công, từ chối hợp lệ và hết hạn. Kiểm tra mất scrape, thay đổi schema, lấy mẫu log hoặc lỗi xuất telemetry trước khi kết luận có sự cố đăng nhập.

### Bước 2: Khoanh vùng kết nối và giai đoạn

Xác định ứng dụng, môi trường, giao thức, kết nối và nhóm kết quả tăng. Nếu chỉ một RP bị ảnh hưởng trong khi các RP khác dùng cùng IdP vẫn hoạt động, ưu tiên kiểm tra cấu hình và phiên bản tại RP đó. Nếu nhiều RP cùng lỗi, mở rộng kiểm tra các phụ thuộc chung nhưng vẫn cần bằng chứng ở từng chặng.

### Bước 3: Đối chiếu thay đổi và sự kiện đại diện

Tương quan thời điểm tăng lỗi với deploy ứng dụng, đổi redirect URI, luân chuyển secret/khóa/chứng thư, refresh metadata, thay đổi chính sách IdP hoặc hạ tầng mạng. Lấy một số giao dịch đại diện, dùng `transaction_ref`/trace để theo dõi mà không trích xuất raw token hoặc assertion vào ticket.

### Bước 4: Kiểm tra trust và trạng thái giao dịch

Xác minh ứng dụng đang dùng đúng kết nối, issuer, audience, khóa/chứng thư và cấu hình flow. Kiểm tra đồng hồ hệ thống, thời hạn giao dịch, kho tương quan và việc duy trì trạng thái qua callback. Với các lỗi hết hạn, phân biệt thời gian người dùng tương tác với độ trễ xử lý máy chủ.

Không tùy tiện tăng clock skew hoặc thời hạn giao dịch để làm hết lỗi. Nếu đồng hồ sai, cần sửa nguồn đồng bộ thời gian; nếu cấu hình trust sai, cần sửa đúng quan hệ tin cậy. Mọi dung sai phải nằm trong thiết kế và phạm vi đã được chấp nhận.

### Bước 5: Khắc phục đúng nguyên nhân

Có thể sửa một mapping cấu hình, cập nhật trust đã xác minh, khôi phục kết nối mạng hoặc phục hồi kho session. Việc thay khóa/chứng thư hay rollback phải tuân theo kế hoạch trust và luân chuyển để không khôi phục một khóa đã bị thu hồi.

Không bỏ kiểm tra chữ ký, audience, issuer hoặc tương quan để phục hồi tỷ lệ thành công. Không dùng một IdP bất kỳ làm fallback chỉ vì endpoint đó phản hồi được. Phương án dự phòng, nếu có, phải thuộc thiết kế truy cập đã được kiểm soát.

### Bước 6: Xác nhận phục hồi ở cả hai phía

Xác nhận giao dịch hợp lệ tạo được phiên, các phản hồi không hợp lệ vẫn bị từ chối và không phát sinh lỗi tương quan mới. Theo dõi kết quả trên các instance, kết nối và khoảng thời gian đủ để thấy tác động cache/metadata. Kiểm tra các giao dịch hết hạn không bị bỏ quên khỏi báo cáo chỉ vì tỷ lệ chính đã giảm.

Ghi lại nguyên nhân, thời điểm ảnh hưởng, cấu hình đã sửa và bằng chứng khôi phục. Một tỷ lệ giảm sau thay đổi chỉ là tín hiệu hỗ trợ; cần kết hợp với phép thử và xác minh bảo vệ trust còn hoạt động.

## 10. Tình huống minh họa: lỗi sau thay đổi audience

Một cổng nhân viên sử dụng OIDC qua kết nối `corporate`. Trước deploy, tỷ lệ lỗi federation dưới baseline nội bộ. Sau deploy, trong 15 phút có 7.600 `success`, 200 `technical_error`, 1.800 `validation_rejected`, 300 `provider_denied` và 100 `user_cancelled`.

Tổng kết quả đã phân loại là 10.000; tỷ lệ lỗi `(200 + 1.800) / 10.000 = 20%`. Nhìn riêng nhóm kết quả cho thấy vấn đề chủ yếu là phản hồi bị từ chối khi xác minh, không phải timeout phụ thuộc.

Event đại diện ghi `audience_mismatch`, tập trung ở instance chạy bản ứng dụng mới. Người dùng đã hoàn thành xác thực tại IdP, còn các ứng dụng khác dùng cùng IdP vẫn đăng nhập được. Đối chiếu cấu hình cho thấy bản mới dùng nhầm audience của môi trường kiểm thử.

Đội vận hành sửa cấu hình theo trust dành cho production và triển khai có kiểm soát. Sau đó kiểm tra danh tính hợp lệ tạo được phiên, đồng thời token phát hành cho ứng dụng khác vẫn bị từ chối. Lỗi giảm về baseline đi cùng các bằng chứng này mới đủ để xác nhận khắc phục.

Nếu chỉ bỏ kiểm tra audience, biểu đồ cũng có thể giảm nhưng ứng dụng sẽ chấp nhận kết quả không dành cho mình. Đây là lý do federation error rate luôn phải được đọc cùng hiệu lực của các kiểm tra trust.

## 11. Kiểm tra tổng hợp và trải nghiệm người dùng

Một phép thử tổng hợp dùng tài khoản chuyên dụng có thể quan sát toàn bộ luồng đăng nhập hợp lệ, thời gian hoàn tất và khả năng thiết lập phiên. Cần phân biệt lưu lượng kiểm thử với người dùng thực để tần suất chạy test không làm thay đổi ý nghĩa tỷ lệ chung.

Có thể bổ sung kiểm thử có kiểm soát cho trường hợp audience sai, phản hồi hết hạn hoặc giao dịch không tương quan trong môi trường phù hợp. Kết quả mong muốn của các phép thử âm tính là bị từ chối; không đưa chúng vào cùng baseline người dùng thực mà không phân biệt mục đích.

Tài khoản tổng hợp không đại diện cho mọi người dùng. Nó có thể không đi qua cùng điều kiện MFA, consent, thiết bị, tenant hoặc trình duyệt. Vì vậy cần ghép phép thử với tỷ lệ giao dịch thật, phản ánh hỗ trợ người dùng và dữ liệu từ từng kết nối.

Ở giao diện, nên cung cấp thông báo an toàn và mã tham chiếu nội bộ để hỗ trợ tra cứu. Không hiển thị token, assertion, nội dung chính sách hoặc chi tiết trust nhạy cảm. Với một giao dịch đã thất bại hoặc hết hạn, việc bắt đầu lại cần tạo ngữ cảnh mới theo luồng được hỗ trợ, không tái sử dụng tùy tiện vật liệu đăng nhập cũ.

## 12. Những sai lầm khi sử dụng chỉ số

- Đếm mọi HTTP 4xx/5xx là federation error, dù lỗi xuất hiện trước hoặc sau ranh giới đo.
- Tính mỗi lần retry hoặc mỗi chặng broker thành một giao dịch đầu cuối bị lỗi.
- Coi MFA thành công ở IdP là phiên ứng dụng chắc chắn đã hoàn tất.
- Trộn từ chối chính sách IdP, người dùng hủy và lỗi kỹ thuật mà không công bố định nghĩa.
- Bỏ qua `expired`, khiến dashboard xanh dù nhiều người dùng không hoàn tất hành trình.
- Chia số lỗi kết thúc cho số giao dịch bắt đầu trong cùng cửa sổ mà không xét cohort.
- Tin chuỗi lỗi trong callback trước khi xác minh ngữ cảnh và tương quan phản hồi.
- Tính tỷ lệ từ log lỗi đầy đủ nhưng log thành công đã lấy mẫu, không có hiệu chỉnh.
- Dùng raw token, assertion hoặc định danh có cardinality cao trong metric/log.
- Giảm tỷ lệ bằng cách nới kiểm tra trust hoặc coi một kết nối không được phê duyệt là fallback.

Federation error rate có giá trị khi chỉ rõ ranh giới giao dịch, nhóm kết quả và mẫu số. Khi kết hợp số lượng, giai đoạn lỗi, trạng thái hết hạn, phiên bản trust và bằng chứng hoàn tất phiên, người vận hành có thể xác định luồng liên kết danh tính hỏng ở đâu mà vẫn giữ các kiểm tra bảo vệ danh tính hoạt động đúng.
