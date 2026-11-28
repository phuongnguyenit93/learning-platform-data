# Token issuance

## 1. Audit việc cấp token để hiểu quyền đã được phát hành

**Token issuance** là quá trình một thành phần có thẩm quyền cấp token sau khi các điều kiện của luồng tương ứng được đáp ứng. Trong IAM, đây là điểm chuyển từ việc kiểm tra danh tính, client và quyền sang phát hành một bằng chứng mà bên nhận có thể sử dụng theo mục đích đã định nghĩa.

Audit token issuance cần giúp trả lời:

- Thành phần nào đã cấp token và dựa trên luồng nào?
- Token được cấp cho client nào, đại diện cho chủ thể nào?
- Token dành cho tài nguyên hoặc bên nhận nào, mang phạm vi quyền gì?
- Quyết định dựa trên chính sách, phiên hoặc quan hệ cấp quyền nào?
- Quá trình bị từ chối, gặp lỗi hay đã hoàn tất cấp phát?
- Những lần cấp tiếp, gia hạn, thu hồi và sử dụng sau đó liên quan thế nào?

Mục tiêu không phải lưu token để có thể phát lại nó. Mục tiêu là lưu bằng chứng về quyết định cấp phát và phạm vi đã cấp mà không biến kho log thành nguồn thông tin xác thực.

Một sự kiện cấp token thành công cũng không chứng minh token đã được client nhận, đã được sử dụng hoặc đã được resource server chấp nhận. Những điều đó thuộc các giai đoạn khác của luồng truy cập.

## 2. Phân biệt loại token và ý nghĩa của chúng

| Loại | Mục đích khái quát | Nội dung audit cần phân biệt |
| --- | --- | --- |
| Access token | Bằng chứng truy cập API hoặc tài nguyên theo mô hình cấp quyền | Client, chủ thể, tài nguyên/bên nhận dự kiến, quyền hoặc scope, thời hạn |
| ID token | Truyền kết quả xác thực cho client trong luồng OIDC | Client nhận, chủ thể được xác thực, ngữ cảnh và thời điểm xác thực theo bằng chứng hợp lệ |
| Refresh token | Cho phép client yêu cầu token mới theo điều kiện của grant | Client, grant hoặc family tham chiếu, vòng đời và trạng thái xoay vòng |
| Token nội bộ hoặc phiên bản dành riêng cho hệ thống | Phục vụ một mục đích được tổ chức định nghĩa | Loại, phạm vi, bên phát và bên nhận theo chính sách riêng |

Không gộp mọi loại thành một sự kiện “đăng nhập thành công”. Một workload có thể nhận access token mà không có người dùng tương tác. Một phiên đã đăng nhập có thể tạo ra nhiều lần cấp token. Một lần cấp phát có thể trả về nhiều loại token.

Access token và ID token cũng không thể thay thế nhau chỉ vì cùng là chuỗi có chữ ký. Audit cần giữ đúng loại và mục đích để không khiến người điều tra hiểu nhầm quyền hoặc bằng chứng đã được cấp.

Token có thể tự chứa thông tin hoặc là một giá trị opaque cần tra cứu. Việc thiết kế audit không được phụ thuộc vào khả năng giải mã chuỗi token để đọc toàn bộ nội dung; nguồn cấp phát đã có metadata đáng tin cậy cần thiết cho sự kiện.

## 3. Những chủ thể cần được ghi nhận

### 3.1. Issuer và service cấp phát

Issuer xác định nguồn phát hành trong mô hình tin cậy. Ngoài issuer, sự kiện có thể cần service, môi trường và tenant hoặc phạm vi chính sách tương ứng.

Một token cấp ở môi trường thử nghiệm không nên bị ghép với token production chỉ vì cùng tên client. Khi nhiều nguồn danh tính tham gia, định danh phải được diễn giải trong namespace của đúng nguồn.

### 3.2. Client nhận token

Client là ứng dụng hoặc workload tham gia luồng cấp phát. Cần ghi định danh client đã được xác định qua cơ chế hợp lệ của luồng, cùng trạng thái xác minh liên quan nếu cần.

Không mặc định mọi client đều có cùng cách xác thực. Một public client và một client có khả năng bảo vệ thông tin xác thực có mô hình khác nhau. Audit phải mô tả điều thực tế đã kiểm tra, thay vì luôn gắn một cờ “client đã xác thực bằng secret”.

Trong yêu cầu thất bại, client ID do người gọi khai báo có thể chưa được xác minh. Nếu lưu, cần thể hiện nó là thông tin được khai báo, không phải một danh tính client đã được chứng thực.

### 3.3. Chủ thể mà token đại diện

Với truy cập thay người dùng, token có thể liên quan cả người dùng và client. Với truy cập máy, chủ thể có thể là chính workload. Không tự điền một user ID giả chỉ để mọi sự kiện có cùng hình thức.

Với ủy quyền hoặc chuyển đổi token, cần giữ được quan hệ chủ thể gốc, client hoặc workload thực thi và phạm vi được cấp, theo mô hình mà hệ thống hỗ trợ. Điều này giúp phát hiện việc quyền rộng của một service bị sử dụng để thực hiện yêu cầu ngoài quyền của bên khởi tạo.

Thông tin chủ thể phải lấy từ ngữ cảnh đã kiểm tra. Không ghi tên do client tự gửi thành danh tính đã xác minh hoặc tự liên kết hai tài khoản chỉ vì trùng email.

## 4. Cấp token trải qua những giai đoạn nào?

Một luồng tổng quát có thể gồm:

```text
Nhận yêu cầu cấp token
          |
          v
Xác định luồng, client và bằng chứng đầu vào
          |
          v
Kiểm tra bằng chứng, grant, trạng thái và chính sách
          |
          +------ Không đạt ------> Từ chối
          |
          v
Xác định chủ thể, bên nhận, quyền và thời hạn được cấp
          |
          v
Hoàn tất cấp phát theo cơ chế của hệ thống
          |
          v
Trả phản hồi cho client
          |
          v
Client sử dụng token tại tài nguyên
```

Cần định nghĩa chính xác sự kiện thành công được ghi tại mốc nào. Ví dụ, “issuance completed” có thể có nghĩa thành phần cấp phát đã tạo token và hoàn tất trạng thái cấp phát bắt buộc; nó không có nghĩa chắc chắn client đã lưu được phản hồi.

Các trạng thái thường cần phân biệt là nhận yêu cầu, từ chối, lỗi xử lý, hoàn tất cấp phát và kết quả chưa xác định. Không ghi thành công ngay khi bắt đầu ký token hoặc ngay khi nhận yêu cầu hợp lệ về mặt cú pháp.

Mất phản hồi sau khi cấp phát có thể khiến client thử lại. Không mặc định hai lần yêu cầu là một lần cấp, cũng không mặc định mọi retry đã tạo một token mới; cần dựa vào định danh thao tác và kết quả thực tế của nguồn cấp phát.

Tên sự kiện, trạng thái và schema trong bài là ví dụ nội bộ, không phải định dạng bắt buộc của một giao thức.

## 5. Metadata cần thiết cho một sự kiện cấp phát

| Nhóm | Trường minh họa | Mục đích |
| --- | --- | --- |
| Định danh | Event ID, schema version, issuance operation ID | Nhận diện sự kiện, thao tác và xử lý trùng |
| Nguồn | Issuer, service, môi trường | Xác định thành phần có thẩm quyền đã ghi nhận |
| Thời gian | Thời điểm cấp, ghi nhận, tiếp nhận vào kho log | Dựng chuỗi và đánh giá độ trễ |
| Client | Client ID, loại client hoặc cách xác minh đã áp dụng | Biết bên nhận và ngữ cảnh của luồng |
| Chủ thể | Principal ID, nguồn danh tính, loại chủ thể | Phân biệt người dùng và workload |
| Phạm vi | Tenant, resource hoặc audience, quyền được cấp | Hiểu khả năng token được phép mang theo |
| Luồng | Loại cấp phát hoặc grant theo hệ thống | Phân biệt cấp ban đầu, gia hạn và những biến thể khác |
| Kết quả | Thành công, từ chối, lỗi và mã lý do có kiểm soát | Giải thích quyết định và phát hiện hành vi |
| Bằng chứng | Policy ID/phiên bản, grant reference, audit session reference | Truy vết căn cứ mà không lưu bí mật |
| Vòng đời | Loại token, thời hạn, tham chiếu thu hồi hoặc family nếu có | Liên kết cấp tiếp, thu hồi và kiểm chứng |

Phân biệt **scope được yêu cầu** với **scope thực sự được cấp**. Nếu client yêu cầu nhiều quyền nhưng chính sách chỉ cấp một phần, audit phải cho biết kết quả cấp thực tế. Việc lưu yêu cầu cũng cần giới hạn độ dài và lọc dữ liệu không cần thiết.

OAuth scope có ý nghĩa theo API và chính sách của hệ thống. Không suy một scope là quyền quản trị toàn cục, cũng không kết luận nó đủ cho mọi điều kiện nghiệp vụ trên từng bản ghi.

Audience hoặc resource được cấp cần gắn với namespace tương ứng. Một kết quả cấp cho service A không chứng minh quyền truy cập service B. Tương tự, vai trò trong tenant alpha không tự có hiệu lực ở tenant beta.

Nếu ghi ngữ cảnh xác thực, phải phân biệt thời điểm người dùng thực sự được xác thực với thời điểm token được cấp. Cấp token qua refresh không tự chứng minh người dùng vừa thực hiện lại MFA.

## 6. Ví dụ sự kiện thành công không chứa token

```json
{
  "schemaVersion": 1,
  "eventId": "audit-event-5101",
  "eventType": "token.issuance.completed",
  "occurredAt": "2030-01-01T09:00:00Z",
  "source": {
    "issuerId": "workforce-issuer",
    "service": "authorization-service",
    "environment": "production"
  },
  "operation": {
    "id": "issuance-7101",
    "flow": "AUTHORIZATION_CODE"
  },
  "client": {
    "id": "reporting-web",
    "validationPolicy": "reporting-web-token-endpoint"
  },
  "subject": {
    "type": "user",
    "principalId": "principal-1042",
    "identitySource": "corporate-identity"
  },
  "authorization": {
    "tenantId": "alpha",
    "resourceId": "reporting-api",
    "grantedScopes": ["reports.read"],
    "grantRef": "audit-grant-2201",
    "policyVersion": 8
  },
  "issuedArtifacts": [
    {
      "type": "ACCESS_TOKEN",
      "auditRef": "audit-token-6101",
      "expiresAt": "2030-01-01T09:10:00Z"
    }
  ],
  "result": {
    "outcome": "SUCCEEDED",
    "reasonCode": "ISSUANCE_COMPLETED"
  },
  "correlationId": "request-9101"
}
```

ID, scope, thời điểm và thời hạn trên chỉ minh họa; không phải giá trị cấu hình chung cho mọi hệ thống. Sự kiện chỉ liệt kê access token vì ví dụ chỉ mô tả artifact đó, không ngụ ý mọi luồng đều chỉ cấp một loại token.

`auditRef` là tham chiếu truy vết không có khả năng cấp quyền truy cập. Nó không phải access token được che một phần. Nếu hệ thống có thể liên kết tham chiếu này với sự kiện sử dụng hoặc thu hồi, cần bảo vệ cách ánh xạ đó.

Trong một lần cấp có nhiều artifact, có thể dùng một sự kiện tổng hợp với danh sách như trên hoặc các sự kiện con có cùng operation ID. Dù cách nào, cần tránh đếm ba artifact là ba lần đăng nhập của người dùng.

Thông tin về khóa ký, nếu cần cho điều tra, có thể được ghi dưới dạng định danh khóa đã được nguồn cấp phát lựa chọn. Không ghi khóa riêng hoặc coi một giá trị định danh khóa chưa xác minh trong dữ liệu đầu vào là metadata đáng tin cậy của token đã cấp.

## 7. Audit yêu cầu bị từ chối và lỗi xử lý

Các lý do có thể gồm bằng chứng không hợp lệ, client không được phép dùng luồng, grant đã hết hiệu lực, scope không được cấp, tài khoản không còn hoạt động hoặc yêu cầu nằm ngoài phạm vi tenant.

Nên sử dụng mã lý do được kiểm soát, với ý nghĩa rõ cho người vận hành. Không đưa nguyên giá trị token, authorization code, mật khẩu hoặc nội dung assertion vào thông báo lỗi chỉ để dễ gỡ lỗi.

Một sự kiện từ chối có thể ghi:

```text
eventType: token.issuance.denied
operationId: issuance-7102
claimedClientId: reporting-web
clientIdentityVerified: false
outcome: DENIED
reasonCode: CLIENT_VALIDATION_FAILED
subject: chưa xác lập
```

Ví dụ này không khẳng định `reporting-web` thực sự là bên gửi, vì danh tính client chưa được xác minh. Nếu ghép mọi yêu cầu sai mang tên một client vào thống kê hành vi đã xác thực của client đó, có thể tạo kết luận sai.

Lỗi hạ tầng cũng cần tách khỏi từ chối do chính sách. Ví dụ, nguồn quyền không trả lời khác với việc chủ thể đã được xác minh là thiếu quyền. Mỗi trường hợp cần kết quả và hướng xử lý phù hợp với hệ thống.

Thông tin chi tiết phục vụ điều tra nội bộ không nhất thiết được trả nguyên vẹn cho client. Phản hồi giao thức và sự kiện audit có thể khác mức chi tiết, nhưng phải cùng mô tả đúng kết quả và không tiết lộ bí mật.

## 8. Những giá trị không được đưa vào log

Không ghi các giá trị có thể dùng để lấy hoặc sử dụng quyền truy cập:

- Access token, refresh token và ID token nguyên văn.
- Authorization code, secret của client hoặc assertion nhạy cảm.
- Authorization header, cookie phiên, mật khẩu và OTP.
- Khóa ký, khóa bí mật hoặc dữ liệu khôi phục thông tin xác thực.
- Request/response toàn phần từ token endpoint nếu chứa các giá trị trên.

Một JWT có thể đọc được nội dung không có nghĩa nó an toàn để ghi log. Token có chữ ký nhưng chưa hết hạn vẫn có thể là bằng chứng truy cập; các claim bên trong cũng có thể chứa dữ liệu danh tính nhạy cảm.

Không chỉ che vài ký tự rồi mặc định dữ liệu đã an toàn. Nên dùng metadata theo danh sách cho phép và tham chiếu audit được thiết kế riêng. Nếu dùng fingerprint hoặc định danh từ token để tương quan, cần đánh giá khả năng suy ngược, va chạm, phạm vi sử dụng và bảo vệ dữ liệu; nó không nên trở thành một bằng chứng có thể đem đổi lấy token thật.

Từ ID token hoặc access token, không sao chép toàn bộ claim vào log. Chỉ ghi các trường cần thiết mà nguồn cấp phát đã xác lập, với quyền truy cập và thời hạn lưu phù hợp.

Việc lọc phải bao phủ cả ứng dụng, gateway, HTTP client, tracing, thông báo lỗi và công cụ theo dõi request. Một audit event an toàn vẫn không bảo vệ được hệ thống nếu lớp debug bên dưới ghi toàn bộ phản hồi cấp token.

## 9. Liên kết cấp ban đầu, refresh và thu hồi

Một chuỗi có thể diễn ra như sau:

```text
Grant được thiết lập hoặc chấp thuận
                  |
                  v
Lần cấp token ban đầu
                  |
                  v
Các lần sử dụng và đánh giá quyền tại tài nguyên
                  |
                  v
Yêu cầu refresh -> cấp token tiếp theo nếu còn đủ điều kiện
                  |
                  v
Grant / phiên / token bị thu hồi hoặc hết hiệu lực
```

Grant reference, operation ID, audit session reference và token audit reference giúp nối các giai đoạn. Không dùng chính refresh token làm khóa tương quan trong kho log.

Nếu hệ thống xoay vòng refresh token, sự kiện cần mô tả đúng việc thay thế và liên kết family hoặc grant theo mô hình thực tế. Phát hiện sử dụng lại một bằng chứng đã vô hiệu hóa có thể có giá trị điều tra, nhưng cần hiểu cả khả năng retry đồng thời và hành vi client hợp lệ trước khi kết luận.

Từ chối refresh không tự chứng minh access token trước đó đã bị chặn tại mọi resource server. Sự kiện thu hồi, trạng thái tại điểm thực thi và log sử dụng token phải được kiểm chứng riêng nếu yêu cầu bảo vệ cần điều đó.

Tương tự, thời điểm cấp token mới không tự kéo dài mọi quyền cũ. Audit nên phản ánh tập quyền, phạm vi và thời hạn thực tế được đánh giá và cấp ở lần đó.

## 10. Độ bền, thứ tự và tính nhất quán của bằng chứng

Thiết kế phải tránh hai kết quả sai: log thành công khi cấp phát chưa hoàn tất và đã cấp phát nhưng mất hoàn toàn bằng chứng liên quan.

Với luồng có trạng thái bền vững, chẳng hạn lưu grant hoặc xoay vòng refresh token, có thể liên kết việc cập nhật trạng thái với một bản ghi audit/outbox trong cùng giao dịch nếu kiến trúc hỗ trợ. Khi phát sự kiện ra hệ thống tập trung, cần xử lý gửi lại và quan sát tồn đọng.

Một thiết kế phát token tự chứa mà không lưu giao dịch cấp phát vẫn cần xác định cách bảo đảm audit theo yêu cầu. Không thể mặc định chỉ gọi logger sau khi ký token là đã có bằng chứng bền vững hoặc tính nguyên tử với phản hồi mạng.

Cần định nghĩa các mốc riêng: hoàn tất cấp phát, lưu sự kiện tại nguồn, phát đi, tiếp nhận tại kho log và phản hồi cho client. Kho log trung tâm đã nhận cũng không chứng minh client đã nhận token; hai đường này có thể có kết quả khác nhau.

Về xử lý trùng, phải phân biệt:

- Một sự kiện được gửi lại nhiều lần: giữ cùng event ID và không đếm thành các lần cấp mới.
- Một request tạo ra một lần cấp mới thật sự: có operation hoặc artifact reference tương ứng.
- Một lần cấp nhiều artifact: liên kết được chúng trong cùng thao tác.

Thời gian cấp và thời gian thu thập có thể khác nhau. Quản lý đồng hồ, lưu múi giờ rõ ràng và dùng liên kết thao tác để dựng diễn biến; không suy thứ tự nhân quả chỉ từ các timestamp gần nhau ở hai nguồn.

Khi audit không sẵn sàng, hành vi của nguồn cấp phát phải được thiết kế theo yêu cầu bảo vệ và khả năng vận hành: lưu đệm bền vững, giới hạn, hoãn hoặc từ chối theo phạm vi phù hợp. Không âm thầm bỏ toàn bộ bằng chứng mà vẫn tuyên bố pipeline audit đang đầy đủ.

## 11. Phân tích và phát hiện hành vi cần xem xét

Các mẫu có thể cần điều tra bao gồm:

- Một client đột ngột nhận token cho tài nguyên hoặc tenant ngoài mô hình hoạt động đã biết.
- Tập quyền được cấp tăng sau một lần sửa cấu hình client hoặc chính sách.
- Nhiều lần từ chối do scope không hợp lệ hoặc sai bằng chứng, rồi có lần cấp thành công qua một luồng khác.
- Workload nhận token đại diện cho người dùng trong tình huống không phù hợp với chức năng được giao.
- Lần cấp tiếp xuất hiện sau sự kiện vô hiệu hóa tài khoản hoặc thu hồi grant, vượt độ trễ đã thiết kế.
- Nguồn cấp phát vẫn hoạt động nhưng kho log không còn nhận sự kiện tương ứng.

Lưu lượng token cao không tự là tấn công: workload và ứng dụng có chu kỳ gia hạn, retry và mô hình tải khác nhau. Cần xét theo client, loại luồng, phạm vi tài nguyên và trạng thái vận hành.

Một sự kiện issuance cũng không đủ để kết luận đã đọc hoặc xuất dữ liệu. Muốn xác định tác động thực tế cần ghép với log tại API, quyết định phân quyền và kết quả nghiệp vụ tương ứng.

## 12. Bảo vệ kho log và kiểm chứng toàn luồng

Metadata cấp token có thể tiết lộ quan hệ người dùng, client, tenant và tài nguyên. Quyền ghi, đọc, xuất và xóa log cần được giới hạn. Tenant không nên đọc được audit của tenant khác chỉ vì cùng dùng một nền tảng.

Cần tách quyền vận hành cấp phát khỏi khả năng tùy ý sửa dấu vết khi yêu cầu quản trị đặt ra ranh giới đó. Cơ chế chống sửa đổi, lưu trữ và thời gian giữ dữ liệu phải gắn với mục đích điều tra và yêu cầu áp dụng, không dựa vào việc giữ càng nhiều càng tốt.

Các tình huống kiểm chứng:

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Cấp access token thành công | Ghi đúng issuer, client, chủ thể, phạm vi và thời hạn thực tế |
| Một thao tác cấp nhiều loại token | Phân biệt artifact và liên kết đúng thao tác |
| Refresh tạo access token mới | Không ghi nhầm thành lần MFA hoặc đăng nhập tương tác mới |
| Client khai tên hợp lệ nhưng xác minh thất bại | Không gán danh tính đã xác minh sai cho bên gửi |
| Scope được cấp hẹp hơn scope yêu cầu | Audit thể hiện quyền cấp thực tế |
| Token dành cho một tài nguyên hoặc tenant | Không bị phân tích thành quyền toàn cục |
| Phản hồi cấp token bị mất | Không khẳng định client đã nhận; retry được nhận diện đúng |
| Sự kiện được phát lại | Không đếm thành nhiều lần cấp phát |
| Token endpoint trả lỗi có dữ liệu nhạy cảm nội bộ | Không rò bí mật qua exception, tracing hoặc log tự động |
| Kho log trung tâm gián đoạn | Có trạng thái, phục hồi và quan sát khoảng thiếu/chậm dữ liệu |
| Thu hồi grant nhưng còn access token đã cấp | Phân biệt kết quả cấp tiếp và hiệu lực tại tài nguyên |
| Hai issuer có chủ thể cùng chuỗi ID | Giữ đúng namespace và nguồn danh tính |

Audit Token issuance có ích khi mô tả chính xác quyền đã được cấp và căn cứ cấp phát, đồng thời giữ bí mật của token ngoài kho log. Liên kết được sự kiện cấp với sử dụng, gia hạn và thu hồi mới giúp đánh giá đầy đủ vòng đời truy cập trong IAM.
