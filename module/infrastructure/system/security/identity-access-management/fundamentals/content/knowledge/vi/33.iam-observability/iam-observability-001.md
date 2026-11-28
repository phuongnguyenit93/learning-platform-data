# Authentication rate: quan sát lưu lượng và kết quả xác thực

## 1. Authentication rate đo điều gì?

Trong quan sát hệ thống IAM, **authentication rate** thường chỉ tốc độ xử lý các lượt xác thực trong một khoảng thời gian, chẳng hạn số lượt mỗi giây hoặc mỗi phút.

Tên gọi này dễ bị nhầm với **authentication success rate**, tức tỷ lệ xác thực thành công. Hai chỉ số trả lời hai câu hỏi khác nhau:

- Authentication rate: hệ thống đang nhận hoặc hoàn tất bao nhiêu lượt xác thực theo thời gian?
- Authentication success rate: trong tập lượt đã được định nghĩa, bao nhiêu phần trăm thành công?

Một dashboard chỉ ghi “Authentication rate = 95%” nhưng không nêu mẫu số sẽ khó sử dụng. Người đọc không biết đó là tỷ lệ thành công của đăng nhập, tỷ lệ vượt MFA hay một chỉ số khác.

Ví dụ xuyên suốt: ứng dụng quản lý hợp đồng của An Bình dùng SSO và MFA cho người dùng, đồng thời có workload tự động xin thông tin xác thực. Nhóm vận hành cần biết lưu lượng nào tăng, nhóm nào gặp lỗi và liệu thay đổi có ảnh hưởng đến khả năng đăng nhập hợp lệ hay không.

Mục tiêu của bài học là xây dựng phép đo có ý nghĩa trước khi đặt cảnh báo.

## 2. Chọn đơn vị đo: request, lượt thử hay luồng xác thực

Một luồng đăng nhập có thể gồm nhiều request:

```text
Mở luồng đăng nhập
    -> chuyển đến nhà cung cấp danh tính
    -> xác minh yếu tố đầu tiên
    -> yêu cầu MFA
    -> nhận kết quả MFA
    -> hoàn tất phiên ứng dụng
```

Nếu đếm mọi request là một lượt xác thực, người dùng đi qua MFA có thể tạo nhiều lượt hơn người dùng không cần MFA. Nếu đếm cả retry mạng như lượt thử độc lập, lưu lượng quan sát có thể tăng dù số người thực sự đăng nhập không đổi.

Cần chọn và ghi rõ đơn vị:

| Đơn vị | Câu hỏi phù hợp | Giới hạn |
| --- | --- | --- |
| HTTP request | Endpoint hoặc gateway chịu tải bao nhiêu? | Một luồng xác thực có nhiều request |
| Lượt kiểm tra một yếu tố | Thành phần mật khẩu, MFA hoặc khóa xác thực hoạt động ra sao? | Không đại diện cho kết quả toàn bộ luồng |
| Authentication attempt | Một lượt thử xác thực theo định nghĩa ứng dụng có kết quả gì? | Cần định danh và quy tắc kết thúc rõ |
| Luồng đăng nhập hoàn tất | Người dùng đã đạt mốc đăng nhập nào? | Cần phân biệt thành công ở IdP với phiên ứng dụng đã sẵn sàng |
| Chủ thể duy nhất | Bao nhiêu người hoặc workload xuất hiện? | Là chỉ số khác với số lượt và có yêu cầu riêng tư riêng |

Không có một đơn vị duy nhất thay thế được mọi nhu cầu. Có thể thu thập nhiều lớp, nhưng phải đặt tên để không cộng hoặc so sánh chúng như cùng một đại lượng.

Với ví dụ An Bình, có thể theo dõi riêng tốc độ request tại gateway, lượt kiểm tra MFA và lượt đăng nhập ứng dụng hoàn tất.

## 3. Phân biệt đầu vào, xử lý và kết quả

Tốc độ xác thực tại một điểm đo không nhất thiết bằng tốc độ ở điểm khác.

```text
Lưu lượng đến gateway
    -> request bị giới hạn hoặc chặn
    -> lượt được tiếp nhận vào luồng xác thực
    -> lượt đang xử lý
    -> lượt hoàn tất với kết quả
```

Các chỉ số có thể gồm:

- **Incoming request rate**: request đến điểm vào.
- **Attempt start rate**: lượt xác thực bắt đầu theo định nghĩa.
- **Attempt completion rate**: lượt xác thực kết thúc.
- **In-flight attempts**: số lượt đang xử lý.
- **Blocked request rate**: request bị chặn trước hoặc trong một bước đã định.

Nếu gateway chặn nhiều request trước ứng dụng, counter của ứng dụng không thể cho biết đầy đủ lưu lượng đến gateway.

Nếu start rate tăng trong khi completion rate thấp và số lượt đang xử lý tăng, có thể có độ trễ hoặc tắc nghẽn. Không nên kết luận số đăng nhập giảm chỉ từ một counter hoàn tất.

Các lượt bắt đầu ở cuối cửa sổ có thể kết thúc ở cửa sổ sau. Vì vậy, tỷ lệ “thành công trong phút này chia cho lượt bắt đầu trong phút này” có thể sai ý nghĩa khi thời gian hoàn tất biến động.

## 4. Công thức tốc độ xác thực theo thời gian

Giả sử chọn đơn vị là một lượt xác thực đã kết thúc tại identity service:

```text
Authentication completion rate
    = số lượt hoàn tất trong cửa sổ
      / độ dài cửa sổ
```

Nếu trong 60 giây có 600 lượt hoàn tất:

```text
600 / 60 = 10 lượt/giây
```

Đây là tốc độ trung bình trong cửa sổ đó, không có nghĩa mọi giây đều nhận đúng 10 lượt.

Có thể tách theo kết quả:

```text
Successful authentication rate
    = số lượt thành công / thời gian

Credential rejection rate
    = số lượt bị từ chối do thông tin xác thực / thời gian

Authentication dependency error rate
    = số lượt lỗi phụ thuộc / thời gian
```

Trong ngữ cảnh này, từ “rate” của từng dòng vẫn là tốc độ theo thời gian. Nếu muốn biểu diễn phần trăm, nên gọi rõ là tỷ lệ trên một tập lượt cụ thể.

Với counter tích lũy, cần dùng số gia trong cửa sổ, đồng thời xử lý việc tiến trình khởi động lại và counter bị reset. Không lấy tổng từ lúc khởi động chia cho một cửa sổ gần nhất.

## 5. Định nghĩa kết quả kết thúc trước khi tính tỷ lệ thành công

Một lượt có thể kết thúc theo nhiều cách. Danh mục minh họa:

| Kết quả | Ý nghĩa |
| --- | --- |
| `success` | Đã hoàn tất mốc xác thực được định nghĩa |
| `credential_rejected` | Bằng chứng xác thực được kiểm tra và không được chấp nhận |
| `policy_denied` | Một chính sách không cho hoàn tất luồng |
| `dependency_error` | Không hoàn tất do lỗi phụ thuộc hoặc hạ tầng |
| `expired` | Luồng hết hiệu lực theo quy tắc đã định |
| `cancelled` | Hệ thống có bằng chứng người dùng hoặc bên gọi hủy |

Đây là một mô hình phân loại, không phải schema bắt buộc.

Cần quy định mỗi lượt chỉ được ghi nhận một kết quả kết thúc tại điểm đo. Các sự kiện trung gian như mật khẩu đúng hoặc MFA challenge đã gửi không phải kết quả thành công của toàn bộ luồng.

Một trình duyệt đóng tab có thể không gửi thông báo hủy. Không nên ghi ngay `cancelled` chỉ vì chưa thấy request tiếp theo. Có thể cần chờ hết thời hạn và phân loại theo một quy tắc khác, với ý nghĩa rõ ràng.

Lỗi kết nối đến nguồn danh tính không phải bằng chứng người dùng nhập sai mật khẩu. Nếu gộp hai tình huống này, dashboard sẽ khó phân biệt sự cố dịch vụ với hành vi đăng nhập thất bại thông thường.

## 6. Tỷ lệ thành công cần mẫu số nhất quán

Nếu mẫu số là mọi lượt đã kết thúc trong cửa sổ tại cùng điểm đo:

```text
Authentication success ratio
    = số lượt kết thúc thành công
      / tổng số lượt kết thúc đủ điều kiện
```

Ví dụ trong một cửa sổ 60 giây:

| Kết quả | Số lượt |
| --- | ---: |
| Thành công | 490 |
| Thông tin xác thực bị từ chối | 60 |
| Chính sách từ chối | 20 |
| Lỗi phụ thuộc | 30 |
| Tổng lượt kết thúc | 600 |

Khi đó:

```text
Tốc độ hoàn tất = 600 / 60 = 10 lượt/giây

Tốc độ thành công = 490 / 60 ≈ 8,17 lượt/giây

Tỷ lệ thành công = 490 / 600 ≈ 81,67%

Tỷ lệ lỗi phụ thuộc = 30 / 600 = 5%
```

Cần nêu rõ rằng cửa sổ ví dụ chỉ có bốn nhóm kết quả trên. Nếu có lượt hết hạn, hủy hoặc nhóm khác, chúng phải được tính theo hợp đồng chỉ số.

Một hệ thống có thể định nghĩa thêm tỷ lệ loại trừ một số nhóm để phục vụ mục tiêu khác. Khi đó, phải đổi tên hoặc ghi rõ điều kiện loại trừ, không trình bày hai tỷ lệ có mẫu số khác nhau dưới cùng một nhãn.

Nếu không có lượt kết thúc, tỷ lệ là không có đủ dữ liệu để tính, không nên tự hiển thị là 100% thành công. Tương tự, thiếu dữ liệu thu thập không đồng nghĩa có 0 lượt xác thực.

## 7. Tỷ lệ theo cửa sổ kết thúc và tỷ lệ theo nhóm khởi đầu

Có hai cách nhìn thường cần phân biệt.

### 7.1. Cửa sổ kết thúc

Đếm những lượt có kết quả kết thúc trong cửa sổ, rồi tính tỷ lệ trên các lượt đó.

Cách này hữu ích để quan sát vận hành gần thời gian thực. Tuy nhiên, một phần lượt có thể đã bắt đầu trước cửa sổ.

### 7.2. Nhóm lượt bắt đầu cùng khoảng thời gian

Lấy tất cả lượt bắt đầu trong một khoảng, sau đó theo dõi xem chúng kết thúc ra sao.

Cách này hữu ích để phân tích chuyển đổi của một luồng đăng nhập, nhưng cần thời gian chờ để những lượt còn đang mở kết thúc hoặc hết hạn.

Ví dụ, muốn đánh giá tác động của một giao diện MFA mới, có thể cần theo dõi nhóm lượt bắt đầu sau khi phát hành, không chỉ kết quả kết thúc ngay trong phút phát hành.

Không dùng một phần tử số theo thời gian kết thúc và mẫu số theo thời gian bắt đầu rồi gọi đó là tỷ lệ chính xác của cùng tập lượt.

## 8. Tách loại luồng và nguồn xác thực

### 8.1. Người dùng và workload

Một job tự động có thể xin token thường xuyên hơn số lần một người đăng nhập. Nếu gộp cả hai, lưu lượng workload có thể che giấu việc người dùng đang gặp khó khăn.

Nên có khả năng phân tách:

```text
flow = interactive
flow = workload
flow = refresh
flow = step_up
```

Tên nhóm tùy thiết kế. Việc refresh token hoặc xác thực tăng cường có được tính là một loại authentication attempt riêng hay không phải được định nghĩa.

Không coi mỗi request API trình cùng một access token là một lần người dùng đăng nhập mới. Kiểm tra access token tại resource server là một điểm đo khác, dù cũng liên quan xác minh danh tính.

### 8.2. Nhà cung cấp danh tính và phương thức

Nếu An Bình dùng SSO còn tenant khác dùng một phương thức khác, sự cố tại một nguồn có thể bị che trong tổng toàn nền tảng.

Các chiều có ích có thể gồm loại luồng, provider đã cấu hình, phương thức xác thực, môi trường và vùng triển khai.

Không đưa một issuer hoặc tên phương thức tùy ý do client gửi thành nhãn metrics. Cần ánh xạ vào danh mục được kiểm soát, với nhóm `unknown` hoặc xử lý đầu vào không hợp lệ theo thiết kế.

### 8.3. Thành công tại IdP và tại ứng dụng

Một lần xác thực thành công tại nhà cung cấp danh tính không bảo đảm ứng dụng đã tạo được phiên.

Có thể xảy ra lỗi callback, ánh xạ danh tính, kiểm tra tenant hoặc lưu phiên sau khi IdP đã xác thực xong. Theo dõi riêng các mốc giúp tránh tình trạng dashboard IdP báo tốt trong khi người dùng không vào được ứng dụng.

## 9. Thiết kế metrics mà không tạo quá nhiều chuỗi dữ liệu

Một bộ tên minh họa:

```text
iam_auth_attempts_started_total
iam_auth_attempts_completed_total
iam_auth_attempts_inflight
iam_auth_attempt_duration_seconds
iam_auth_dependency_failures_total
```

Các tên này chỉ minh họa, không tuyên bố tuân theo một chuẩn đặt tên hoặc công cụ cụ thể.

Ví dụ nhãn có số giá trị được kiểm soát:

```text
flow = interactive
outcome = dependency_error
provider = corporate_sso
environment = production
region = region_a
```

Những nhãn như user ID, email, token, request ID hoặc URL đầy đủ thường làm số tổ hợp giá trị tăng rất lớn. Chúng còn tạo rủi ro riêng tư hoặc lộ bí mật.

Có thể để chi tiết đối chiếu trong log hoặc trace được kiểm soát quyền, rồi dùng tham chiếu phù hợp từ công cụ quan sát khi cần. Không biến metrics thành nơi lưu mọi chi tiết của mỗi lần đăng nhập.

Tenant ID cũng có thể tạo nhiều chuỗi dữ liệu. Nếu cần phân tích theo tenant, phải đánh giá quy mô, quyền xem và mô hình lưu trữ; không mặc định mọi tenant đều là một nhãn toàn cục không giới hạn.

## 10. Cộng gộp đúng giữa các instance

Khi có nhiều instance, cần tính trên số lượt của cùng cửa sổ và cùng định nghĩa.

Ví dụ:

| Instance | Thành công | Tổng lượt kết thúc | Tỷ lệ |
| --- | ---: | ---: | ---: |
| A | 90 | 100 | 90% |
| B | 1 | 10 | 10% |

Tỷ lệ toàn hệ thống:

```text
(90 + 1) / (100 + 10) = 91 / 110 ≈ 82,73%
```

Không lấy trung bình đơn giản:

```text
(90% + 10%) / 2 = 50%
```

Hai instance có số lượt khác nhau nên không có trọng số bằng nhau.

Tương tự, cần xử lý counter reset từng chuỗi trước khi cộng gộp số gia hoặc tốc độ theo cách phù hợp với hệ thống metrics. Cộng tổng không đúng có thể che việc một instance vừa khởi động lại.

Cũng cần tránh đếm trùng một lượt tại gateway, identity service và ứng dụng rồi cộng thành tổng lượt của toàn hệ thống. Đó là ba điểm quan sát khác nhau của cùng một luồng hoặc của những đơn vị khác nhau.

## 11. Liên kết metrics với log và trace

Metrics cho biết mức độ và phạm vi thay đổi; log hoặc trace giúp tìm một đường xử lý cụ thể.

Một sự kiện minh họa:

```json
{
  "eventType": "AUTHENTICATION_ATTEMPT_COMPLETED",
  "attemptReference": "auth-attempt-251",
  "flow": "interactive",
  "provider": "corporate_sso",
  "outcome": "dependency_error",
  "reasonCode": "SESSION_STORE_UNAVAILABLE",
  "durationMs": 840,
  "service": "identity-service",
  "environment": "production",
  "correlationId": "corr-92"
}
```

Tham chiếu lượt thử không được là token, cookie phiên hoặc một mã có thể sử dụng để chiếm luồng đăng nhập.

Không ghi mật khẩu, mã MFA, access token, refresh token hoặc toàn bộ callback vào dữ liệu chẩn đoán. Lỗi xác thực thường khiến nhóm vận hành muốn xem thêm chi tiết; cần mở rộng đúng trường cần thiết thay vì ghi nguyên request.

Nếu metrics được dựng từ sự kiện, cần xem xét trùng sự kiện, mất sự kiện, đến muộn và thay đổi schema. Không giả định dữ liệu sự kiện tự động tạo ra một counter chính xác.

Nếu metrics được tăng tại nguồn còn log được lấy mẫu, số log có thể ít hơn số lượt metrics. Đây là khác biệt thiết kế cần biết, không nhất thiết là lỗi.

## 12. Đọc các mẫu thay đổi phổ biến

| Quan sát | Các khả năng cần đối chiếu |
| --- | --- |
| Lưu lượng bắt đầu tăng, tỷ lệ thành công ổn định | Giờ cao điểm, chiến dịch sử dụng hoặc workload thay lịch |
| Lưu lượng tăng, từ chối credential tăng | Người dùng gặp khó khăn, client cấu hình sai hoặc hoạt động thử đăng nhập |
| Lỗi phụ thuộc tăng ở một provider | Nguồn danh tính, mạng hoặc tích hợp có vấn đề |
| IdP thành công nhưng hoàn tất phiên ứng dụng giảm | Callback, ánh xạ danh tính, tenant hoặc kho phiên có thể lỗi |
| Start rate cao, completion rate thấp, in-flight tăng | Luồng chậm, phụ thuộc bị treo hoặc xử lý chưa kết thúc |
| Rate tại ứng dụng giảm nhưng gateway chặn tăng | Lưu lượng bị ngăn trước điểm đo ứng dụng |
| Tỷ lệ thành công tăng bất thường | Có thể là cải thiện, thay đổi mẫu số hoặc một kiểm soát bị bỏ qua |
| Metrics ngừng xuất hiện | Có thể là lỗi thu thập, không nên mặc định không có người đăng nhập |

Một tỷ lệ thất bại cao không tự chứng minh có tấn công. Một tỷ lệ thành công cao cũng không chứng minh hệ thống an toàn: bên không được phép có thể đang dùng credential hợp lệ bị đánh cắp, hoặc kiểm soát đã bị vô hiệu hóa.

Cần đối chiếu với thay đổi triển khai, chính sách, nhà cung cấp, nguồn lưu lượng và các tín hiệu bảo mật khác.

## 13. Cảnh báo cần có ngữ cảnh và hành động tiếp theo

Một cảnh báo có ích nên nêu rõ:

- Chỉ số, định nghĩa và cửa sổ đo.
- Phạm vi luồng, provider, môi trường hoặc vùng.
- Mức thay đổi so với nền hoặc mục tiêu đã xác định.
- Khối lượng tối thiểu cần để kết luận có ý nghĩa.
- Nơi xem bằng chứng chi tiết.
- Nhóm chịu trách nhiệm và bước kiểm tra đầu tiên.

Không có một ngưỡng authentication rate phù hợp cho mọi sản phẩm. Cần xét giờ cao điểm, lịch job, quy mô người dùng và lịch thay đổi.

Một cửa sổ ngắn có thể phát hiện sự cố nhanh nhưng dễ dao động. Một cửa sổ dài ổn định hơn nhưng có thể che các đợt lỗi ngắn. Có thể dùng nhiều cửa sổ theo mục tiêu, với hợp đồng rõ ràng để người trực hiểu vì sao cảnh báo xuất hiện.

Khi số lượt rất ít, vài lỗi có thể làm tỷ lệ giảm mạnh. Cần kết hợp số lượng và tỷ lệ, không đánh giá phần trăm tách khỏi mẫu số.

Tự động phản ứng cũng phải có phạm vi: không khóa hàng loạt người dùng chỉ vì lỗi phụ thuộc tăng, và không bỏ MFA để làm tỷ lệ thành công đẹp hơn.

## 14. Authentication rate không phải toàn bộ SLO xác thực

Nếu muốn đánh giá độ tin cậy dịch vụ, cần chọn một chỉ số phản ánh khả năng hoàn thành yêu cầu hợp lệ trong điều kiện đã định.

Tỷ lệ thành công của mọi lượt đăng nhập có thể chịu ảnh hưởng bởi mật khẩu sai, yêu cầu không hợp lệ, bot hoặc người dùng chủ động hủy. Vì vậy, nó không tự là tỷ lệ sẵn sàng của hạ tầng IAM.

Có thể cần các phép đo bổ sung:

- Tỷ lệ lỗi hệ thống trên tập yêu cầu đủ điều kiện.
- Độ trễ xử lý của các mốc được kiểm soát.
- Tốc độ hoàn tất của một luồng kiểm tra tổng hợp được quản lý.
- Tình trạng phụ thuộc và độ trễ tạo phiên.
- Độ trễ truyền thay đổi bảo mật liên quan.

Luồng kiểm tra tổng hợp có thể phát hiện một đường đăng nhập cụ thể bị lỗi, nhưng không chứng minh mọi provider, tenant hoặc phương thức đều hoạt động. Tài khoản kiểm tra cũng cần quyền tối thiểu và quản lý credential phù hợp.

Cần phân biệt độ trễ xử lý server với thời gian người dùng chờ và nhập MFA. Cả hai đều có ích, nhưng không nên coi toàn bộ thời gian thao tác của con người là độ trễ một dịch vụ backend.

## 15. Kiểm tra tính đúng của phép đo

| Tình huống kiểm tra | Kết quả cần đạt |
| --- | --- |
| Một lượt đăng nhập thành công có nhiều request | Counter lượt thử không tăng theo mọi request trung gian |
| Mật khẩu đúng nhưng MFA thất bại | Không ghi thành công toàn luồng |
| IdP thành công nhưng tạo phiên ứng dụng lỗi | Thấy khác biệt giữa hai mốc |
| Client retry vì mất response | Hành vi đếm phù hợp định nghĩa lượt thử, có thể đối chiếu |
| Một instance khởi động lại | Không tạo số âm hoặc đỉnh rate giả do counter reset |
| Sự kiện đến muộn hoặc bị gửi trùng | Cách tổng hợp phản ánh quy tắc đã định |
| Không có lượt trong cửa sổ | Không tự biến thành 100% thành công |
| Bộ thu thập mất kết nối | Hiển thị thiếu dữ liệu thay vì 0 lưu lượng |
| Một provider lỗi nhưng provider khác vẫn tốt | Có thể thấy phạm vi bị ảnh hưởng |
| Lưu lượng workload tăng mạnh | Không che khuất luồng đăng nhập người dùng |
| Giá trị nhãn do client tạo tùy ý | Không tạo số chuỗi metrics không giới hạn |
| Kiểm tra dữ liệu metrics, log và trace | Không xuất hiện mật khẩu, token hoặc mã MFA |

Ngoài thử giá trị counter, cần so sánh với các luồng mẫu đã biết và điểm quan sát thực tế. Một biểu đồ có vẻ hợp lý vẫn có thể sai nếu phép đo bắt đầu hoặc kết thúc ở mốc khác với tên hiển thị.

## 16. Áp dụng vào An Bình

Nhóm vận hành tách lưu lượng đăng nhập tương tác, refresh và workload. Với đăng nhập tương tác, họ định nghĩa rõ một attempt và coi thành công là khi ứng dụng hoàn tất mốc phiên đã chọn.

Khi tỷ lệ thành công giảm, nhóm xem số lượt, nhóm kết quả và provider. Nếu `dependency_error` tăng còn từ chối credential ổn định, họ ưu tiên kiểm tra phụ thuộc thay vì yêu cầu toàn bộ người dùng đổi mật khẩu.

Nếu metrics tại identity service giảm nhưng gateway chặn tăng, họ không kết luận hệ thống không còn tải. Nếu IdP vẫn tốt nhưng phiên ứng dụng không được tạo, họ theo luồng từ callback đến kho phiên.

Authentication rate trở nên hữu ích khi người đọc biết đang đếm đơn vị nào, tại điểm nào, theo cửa sổ nào và với mẫu số nào. Từ nền tảng đó, chỉ số mới hỗ trợ được cả vận hành IAM và phân tích hành vi bảo mật.
