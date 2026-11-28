# PAM API authentication

## 1. Mục tiêu và bối cảnh

Một hệ thống PAM có thể quản lý mật khẩu quản trị, cấp phiên truy cập đặc quyền, xoay vòng credential và lưu dấu vết kiểm toán. Khi những thao tác này được mở qua API, một pipeline triển khai hoặc một dịch vụ tự động có khả năng tác động đến nhiều tài nguyên nhạy cảm trong thời gian rất ngắn. Xác thực API vì thế là cửa kiểm soát đầu tiên của luồng đặc quyền.

Bài học thuộc chương **API và automation**, tập trung vào cách một chương trình chứng minh danh tính trước PAM và cách vận hành danh tính đó an toàn. Sau bài học, người học có thể:

- Phân biệt danh tính gọi API, credential dùng để xác thực và credential của hệ thống đích.
- Chọn cơ chế xác thực phù hợp cho dịch vụ chạy lâu dài, pipeline ngắn hạn và công cụ do người vận hành sử dụng.
- Thiết kế luồng cấp token với ràng buộc danh tính, môi trường và tài nguyên.
- Xử lý token hết hạn, thu hồi quyền, luân chuyển khóa và sự cố lộ credential.
- Lưu bằng chứng đủ để truy nguyên automation nhưng không đưa bí mật vào log.

Các endpoint, scope, tên trường và mã lỗi PAM trong ví dụ là **hợp đồng minh họa**, không đại diện cho API của một nhà cung cấp cụ thể. Khi triển khai cần đối chiếu đặc tả của sản phẩm, máy chủ cấp token và cơ chế liên kết danh tính thực tế.

## 2. Ba danh tính cần tách biệt

Xét pipeline triển khai ứng dụng thanh toán:

1. Pipeline chạy với danh tính workload của nền tảng CI.
2. Workload dùng danh tính đó để nhận quyền gọi PAM.
3. PAM cấp hoặc sử dụng một credential quản trị cơ sở dữ liệu cho tác vụ đã được phép.

Ba lớp này phục vụ ba mục đích khác nhau:

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Danh tính workload | Chương trình nào đang thực hiện công việc? | Pipeline deploy của dự án payments tại môi trường production |
| Credential xác thực PAM API | Bằng chứng nào khiến PAM hoặc máy chủ cấp token tin danh tính đó? | Chứng thư client, chữ ký bằng khóa riêng, assertion của nền tảng CI |
| Credential hệ thống đích | Tác vụ dùng quyền gì trên tài nguyên được quản lý? | Tài khoản deploy giới hạn trên một database |

Không dùng mật khẩu quản trị database làm API key để gọi PAM. Không dùng token quản trị PAM làm credential triển khai database. Việc tách lớp cho phép thu hồi quyền của pipeline mà không phải thay đồng thời mọi mật khẩu đích, đồng thời giúp nhận diện nguyên nhân khi xảy ra truy cập bất thường.

Một token hợp lệ cũng không đồng nghĩa với việc mọi yêu cầu đều được phép. **Xác thực** thiết lập danh tính; **phân quyền** quyết định danh tính đó có được thực hiện hành động cụ thể trên tài nguyên cụ thể, trong điều kiện cụ thể hay không.

Ví dụ, token của pipeline deploy có thể hợp lệ nhưng vẫn bị từ chối khi yêu cầu sửa policy PAM, lấy credential của môi trường khác hoặc mở phiên truy cập ngoài cửa sổ triển khai.

## 3. Những thành phần trong luồng xác thực

Một kiến trúc thường có các thành phần sau:

- **API client**: chương trình hoặc workload gọi PAM.
- **Nguồn danh tính**: nơi phát hành bằng chứng ban đầu cho workload hoặc người sử dụng.
- **Authorization server**: thành phần xác thực client và cấp access token.
- **PAM API**: resource server kiểm tra token và thực thi policy đối với tài nguyên đặc quyền.
- **Kho khóa hoặc dịch vụ ký**: bảo vệ bí mật, khóa riêng hay chứng thư dùng cho client authentication.
- **Hệ thống audit**: liên kết bằng chứng từ lần chạy automation, lần cấp token và yêu cầu PAM.

Authorization server có thể nằm trong PAM hoặc là dịch vụ bên ngoài được PAM tin cậy. Không mặc định rằng token lấy từ bất kỳ hệ thống SSO nào cũng dùng được cho PAM. Cần cấu hình quan hệ tin cậy, đối tượng nhận token và ánh xạ danh tính rõ ràng.

~~~mermaid
sequenceDiagram
    participant W as Workload
    participant I as Nguồn danh tính
    participant A as Máy chủ cấp token
    participant P as PAM API
    participant L as Audit

    W->>I: Yêu cầu bằng chứng danh tính workload
    I-->>W: Assertion hoặc credential ngắn hạn
    W->>A: Xác thực và yêu cầu quyền gọi PAM
    A->>A: Kiểm tra danh tính và policy cấp token
    A-->>W: Access token giới hạn
    W->>P: Yêu cầu API cùng access token
    P->>P: Kiểm tra token, quyền và điều kiện tài nguyên
    P->>L: Ghi danh tính, hành động, tài nguyên, kết quả
    P-->>W: Kết quả hoặc từ chối
~~~

Sơ đồ thể hiện một thiết kế liên kết danh tính. Không phải sản phẩm PAM nào cũng hỗ trợ đầy đủ luồng này; với client dùng mTLS trực tiếp, bước lấy assertion có thể không tồn tại.

## 4. Lựa chọn cơ chế xác thực

### 4.1. Danh tính workload và liên kết danh tính

Với pipeline ngắn hạn, nền tảng chạy job có thể phát hành assertion gắn với workload. Một bên tin cậy xác minh assertion rồi cấp token phù hợp để gọi PAM.

Điểm mạnh là tránh phân phối một client secret tĩnh cho mọi lần chạy. Tuy nhiên, chính sách tin cậy phải xác định workload nào được chấp nhận. Chỉ kiểm tra tên tổ chức hoặc issuer mà bỏ qua project, môi trường hay workflow có thể cho phép một job không liên quan nhận quyền production.

Một ánh xạ minh họa:

~~~yaml
# Policy minh họa, không phải cấu hình của một sản phẩm.
trust:
  issuer: https://ci.example.test
  audience: pam-federation
  workload:
    project: payments
    workflow: deploy
    environment: production
    protected_execution: true
identity:
  pam_principal: payments-deployer-prod
permissions:
  actions:
    - credential.checkout
  resources:
    - database/payments-prod/deploy
~~~

Các thuộc tính phải đến từ bằng chứng đã được nền tảng ký và từ cấu hình tin cậy được quản trị, không lấy trực tiếp từ dữ liệu do người gọi tự khai. Ý nghĩa của branch, environment hoặc protected execution khác nhau giữa các nền tảng; policy cần dựa vào claim được tài liệu hóa của nền tảng thực tế.

### 4.2. OAuth 2.0 client credentials

Client credentials phù hợp với client bí mật có khả năng bảo vệ credential và hoạt động bằng quyền đã cấp cho chính client. Luồng này không đại diện cho một người dùng vừa đăng nhập. Theo [RFC 6749, mục 4.4](https://www.rfc-editor.org/rfc/rfc6749.html#section-4.4), client xác thực tại token endpoint rồi nhận access token; không nên cấp refresh token cho luồng này.

Ví dụ HTTP khái niệm khi client được đăng ký dùng mTLS:

~~~http
POST /oauth2/token HTTP/1.1
Host: identity.example.test
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=client_credentials&client_id=payments-deployer-prod&scope=pam.checkout
~~~

Kết nối TLS của yêu cầu trên phải trình chứng thư client và chứng minh quyền sở hữu khóa riêng tương ứng. Trường client_id chỉ định danh client; tự gửi trường này không phải bằng chứng xác thực.

Phản hồi minh họa:

~~~json
{
  "access_token": "<REDACTED>",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "pam.checkout"
}
~~~

Thời hạn 300 giây là lựa chọn minh họa của thiết kế, không phải giá trị bắt buộc của giao thức. Client dùng thời hạn thực sự do máy chủ trả về và policy của hệ thống để lập lịch cấp lại.

### 4.3. mTLS và token ràng buộc chứng thư

mTLS bổ sung việc kiểm tra danh tính client trong kết nối TLS bằng chứng thư. Hệ thống vẫn cần ánh xạ chứng thư đã được chấp nhận tới đúng client, kiểm tra thời hạn và thực hiện policy tin cậy.

Cần phân biệt hai khả năng:

- **mTLS client authentication**: dùng chứng thư để xác thực client tại máy chủ cấp token.
- **Certificate-bound access token**: token được ràng buộc với chứng thư và PAM kiểm tra sự ràng buộc khi nhận yêu cầu.

Dùng mTLS ở token endpoint chưa tự động biến token thành token ràng buộc chứng thư. Hai khả năng này được định nghĩa riêng trong [RFC 8705](https://www.rfc-editor.org/rfc/rfc8705.html).

Nếu TLS kết thúc ở gateway, thiết kế phải bảo vệ đoạn từ gateway đến PAM và tính xác thực của dữ liệu chứng thư được chuyển tiếp. PAM không được tin một header danh tính do client Internet tự gửi. Quyền thêm header đó phải thuộc thành phần trung gian đã được xác thực; các header trùng tên từ bên ngoài cần bị loại bỏ hoặc từ chối theo thiết kế.

### 4.4. Xác thực client bằng khóa bất đối xứng

Một client có thể ký bằng chứng bằng khóa riêng và để phía xác thực kiểm tra bằng khóa công khai đã đăng ký. Cơ chế này giảm nhu cầu chia sẻ cùng một secret giữa client và máy chủ.

Dù khóa riêng không được gửi qua mạng, nó vẫn là tài sản đặc quyền. Khi khóa nằm trong một file có thể bị sao chép, kẻ lấy được file có thể giả mạo client trong phạm vi hiệu lực của khóa. Nếu hạ tầng hỗ trợ, sử dụng dịch vụ ký hoặc cơ chế bảo vệ khóa phù hợp để hạn chế khả năng xuất khóa.

Bằng chứng có chữ ký cần được kiểm tra theo profile đã chọn, gồm đối tượng nhận, thời hạn, danh tính và các biện pháp chống phát lại của profile đó. Không tự tạo một định dạng chữ ký riêng nếu sản phẩm đã hỗ trợ một giao thức được kiểm chứng.

### 4.5. Client secret hoặc API key

Một số tích hợp chỉ hỗ trợ client secret, API key hoặc cơ chế đăng nhập API riêng. Khi phải dùng chúng:

- Cấp riêng cho từng tích hợp và môi trường, có owner chịu trách nhiệm.
- Giới hạn quyền ngay tại PAM, thay vì cấp admin rồi kỳ vọng chương trình tự hạn chế.
- Lưu trong kho bí mật phù hợp; không nhúng trong repository, image hoặc template dùng chung.
- Thiết lập hạn dùng, lịch thay và đường thu hồi rõ ràng.
- Truyền qua kênh TLS được kiểm tra đúng; tránh URL và nơi có khả năng ghi nhận giá trị bí mật.
- Theo dõi thời điểm sử dụng cuối và thu hồi tích hợp không còn hoạt động.

Một API key có thể đồng thời đóng vai trò định danh và bằng chứng sở hữu. Nó không mặc nhiên có scope, thời hạn, khả năng ràng buộc người gửi hoặc mô hình ủy quyền như access token.

### 4.6. Công cụ tương tác của người vận hành

Công cụ do con người sử dụng cần giữ được danh tính người thực hiện và các yêu cầu xác thực của tổ chức, ví dụ SSO, MFA hoặc bước xác minh bổ sung trước hành động đặc quyền. Không chuyển mật khẩu cá nhân và mã OTP vào một script chạy nền để làm cơ chế tự động hóa lâu dài.

Với ứng dụng tương tác, chọn flow được hệ thống danh tính hỗ trợ cho đúng loại client. Tài khoản máy nên có policy riêng; việc nó không thực hiện thao tác MFA của con người phải được bù bằng bằng chứng workload, giới hạn quyền, bảo vệ khóa và kiểm soát môi trường chạy.

| Bối cảnh | Hướng thiết kế cần đánh giá | Điều kiện quyết định |
|---|---|---|
| Job CI ngắn hạn | Liên kết danh tính workload | Claim đủ chặt, token dùng đúng audience |
| Dịch vụ backend có danh tính ổn định | mTLS hoặc xác thực bằng khóa | Vận hành vòng đời chứng thư, khóa và trust |
| Sản phẩm chỉ hỗ trợ shared secret | Secret riêng từng client | Rotation, giới hạn quyền, owner và thu hồi |
| CLI do quản trị viên sử dụng | Luồng đăng nhập tương tác | Ghi nhận đúng người, áp dụng policy người dùng |

Việc lựa chọn phụ thuộc khả năng hai đầu và mức độ trưởng thành vận hành. Cơ chế dùng khóa nhưng không kiểm soát được quyền đọc khóa vẫn có thể kém an toàn hơn một secret được quản trị tốt.

## 5. Từ danh tính tới quyền PAM

Xác thực nên dẫn đến một principal ổn định, có thể truy nguyên tới owner. Sau đó PAM áp dụng giới hạn theo hành động và tài nguyên.

Ví dụ yêu cầu nghiệp vụ:

> Pipeline payments production chỉ được checkout credential deploy của database payments trong cửa sổ triển khai đã được phê duyệt.

Từ yêu cầu này có thể hình thành policy minh họa:

~~~yaml
principal: payments-deployer-prod
owner: team-payments-platform
environment: production
allowed:
  action: credential.checkout
  resource: database/payments-prod/deploy
conditions:
  deployment_approval_required: true
  maximum_lease_seconds: 600
denied_capabilities:
  - policy.admin
  - identity.admin
  - audit.delete
  - credential.checkout.other-resources
~~~

Không xem chuỗi scope trong token là toàn bộ mô hình phân quyền. Scope có thể là quyền tương đối rộng, còn tài nguyên, môi trường, cửa sổ JIT và approval cần được PAM kiểm tra tại thời điểm yêu cầu.

Nhãn ticket hoặc correlation ID do client gửi chỉ hỗ trợ liên kết bằng chứng. Nó không tự chứng minh rằng approval tồn tại. Nếu policy yêu cầu phê duyệt, hệ thống phải xác minh trạng thái phê duyệt qua một nguồn tin cậy hoặc một workflow PAM đã kiểm soát.

Tương tự, việc token còn hạn không có nghĩa cửa sổ JIT hoặc lease của credential đích vẫn còn hiệu lực. Đây là những điều kiện khác nhau.

## 6. Kiểm tra token đúng nơi, đúng mục đích

Access token có thể là chuỗi opaque hoặc một token có cấu trúc như JWT. Client không nên giả định mọi token đều có thể giải mã cục bộ.

Với token opaque, PAM dùng cơ chế xác minh hoặc introspection mà sản phẩm hỗ trợ. Với JWT, việc xác minh phải theo profile token và cấu hình tin cậy của triển khai. Đọc payload của JWT chỉ là giải mã dữ liệu, chưa phải xác thực token.

Các điểm cần thiết kế rõ:

| Kiểm tra | Mục đích | Sai sót cần tránh |
|---|---|---|
| Nguồn phát hành tin cậy | Chỉ chấp nhận token từ nơi đã cấu hình | Lấy issuer do token tự khai rồi tự động tin mọi issuer |
| Chữ ký hoặc trạng thái token | Xác minh token còn hợp lệ theo cơ chế đã chọn | Chỉ đọc claim và bỏ qua xác minh |
| Đối tượng nhận | Token phải được cấp để dùng cho PAM tương ứng | Dùng token của dịch vụ khác tại PAM |
| Thời hạn và thời điểm hiệu lực | Giới hạn cửa sổ sử dụng | Dùng độ lệch đồng hồ quá rộng để chấp nhận token cũ |
| Danh tính client hoặc chủ thể | Ánh xạ tới principal được quản trị | Gán quyền từ một tên tự khai trong request |
| Ràng buộc người gửi, nếu có | Hạn chế sử dụng token bị sao chép | Coi mTLS khi cấp token là đủ cho mọi lần gọi |
| Quyền và điều kiện tài nguyên | Kiểm soát hành động được yêu cầu | Chỉ kiểm tra token có tồn tại |

Danh sách tên claim cụ thể phụ thuộc profile và loại token. Không yêu cầu một claim tùy ý chỉ vì ví dụ của hệ thống khác có trường đó, cũng không bỏ qua trường bắt buộc mà profile thực tế quy định.

Đặc biệt, một ID token phục vụ đăng nhập không phải access token mặc định để gọi PAM. PAM chỉ chấp nhận loại token được thiết kế và cấu hình cho API của mình.

## 7. Bảo vệ access token và credential khởi đầu

### 7.1. Token ngắn hạn vẫn là bí mật

Bearer token bị sao chép có thể được dùng bởi bên khác nếu không có cơ chế ràng buộc người gửi được thực thi. Hạn dùng ngắn làm giảm thời gian khai thác, không ngăn việc sử dụng trái phép ngay sau khi rò rỉ.

Các vùng thường làm lộ token gồm:

- Log HTTP của client, gateway hoặc cơ chế debug.
- Thông báo exception có kèm toàn bộ request.
- Trace tự động thu header Authorization.
- Artifact của pipeline, file cấu hình tạm và output được lưu lâu dài.
- Công cụ hỗ trợ chụp toàn bộ dữ liệu chẩn đoán.
- Lịch sử lệnh hoặc tham số tiến trình nếu đưa bí mật vào câu lệnh.

Nếu có thể, giữ token trong bộ nhớ của tiến trình và dùng một thư viện HTTP có cấu hình che bí mật rõ ràng. Nếu bắt buộc dùng file tạm, hạn chế quyền đọc, đặt vòng đời ngắn và kiểm tra cơ chế dọn dẹp. Đừng xem thao tác xóa file đơn thuần là bảo đảm không thể khôi phục dữ liệu.

### 7.2. Bài toán bootstrap

Một câu hỏi thường gặp là: “Nếu credential gọi PAM cũng nằm trong chính PAM, chương trình lấy credential đầu tiên bằng cách nào?”

Cần một gốc tin cậy bên ngoài luồng lấy bí mật đó, ví dụ:

- Danh tính workload do nền tảng chạy chương trình cung cấp.
- Chứng thư máy được cấp qua cơ chế provisioning đã kiểm soát.
- Khóa được dịch vụ ký bảo vệ và chỉ workload hợp lệ được sử dụng.
- Secret khởi đầu được phân phối từ một kho độc lập theo policy của tổ chức.

Không giải quyết bootstrap bằng cách sao chép một tài khoản quản trị chung vào tất cả máy chạy job. Mỗi gốc tin cậy phải có owner, quy trình cấp ban đầu và cách thay thế khi bị mất hoặc lộ.

### 7.3. Không chuyển hướng tùy ý mang theo credential

Client cần cố định endpoint tin cậy và kiểm tra TLS. Không tắt kiểm tra chứng thư để “sửa nhanh” lỗi kết nối. Không cho dữ liệu đầu vào tùy ý chọn host nhận client credential hoặc access token.

Nếu HTTP client có tính năng theo redirect, cần cấu hình để credential không bị chuyển tiếp sang origin khác; với endpoint nhạy cảm, có thể từ chối redirect ngoài thiết kế. Việc proxy doanh nghiệp chấm dứt TLS cũng cần được đánh giá trong mô hình tin cậy thực tế.

## 8. Luồng gọi API minh họa

Giả sử client đã nhận access token qua một cơ chế được hỗ trợ. Yêu cầu checkout minh họa:

~~~http
POST /api/v1/credential-checkouts HTTP/1.1
Host: pam.example.test
Authorization: Bearer <ACCESS_TOKEN>
Content-Type: application/json
X-Correlation-ID: deploy-payments-prod-1042

{
  "resource": "database/payments-prod/deploy",
  "purpose": "approved deployment",
  "approval_reference": "DEPLOY-1042",
  "requested_lease_seconds": 600
}
~~~

Ở phía PAM, thứ tự xử lý hợp lý là:

1. Kiểm tra kết nối và bằng chứng xác thực theo hợp đồng.
2. Xác định principal của client.
3. Kiểm tra quyền trên resource được yêu cầu.
4. Kiểm tra approval, JIT và điều kiện policy còn hiệu lực.
5. Cấp checkout hoặc lease theo giới hạn thực tế.
6. Ghi audit kết quả, rồi trả về dữ liệu tối thiểu cần thiết.

Token API có thể sống 300 giây trong khi lease được cấp có giới hạn khác. Hệ thống phải xác định điều gì xảy ra khi token hết hạn giữa lúc job còn giữ credential đích: job có thể cần xác thực lại để gọi API tiếp theo, nhưng credential đích đã cấp không tự biến mất chỉ vì access token hết hạn.

Tương tự, thu hồi API client ngăn những lần gọi mới theo cơ chế của hệ thống; nó không bảo đảm chấm dứt mọi session hoặc mọi bản sao credential đích đã được phát hành. Quy trình thu hồi cần xử lý các đối tượng đó riêng.

## 9. Quản lý token trong một chương trình tự động

Một client vận hành ổn định nên tách ba trách nhiệm:

- **Token provider**: nhận, giữ và thay token đúng hạn.
- **PAM client**: gửi yêu cầu nghiệp vụ và xử lý response.
- **Operation policy**: quyết định yêu cầu nào được retry và cách chống thực hiện trùng.

Mã giả dưới đây mô tả thiết kế, không phải một SDK có thể chạy trực tiếp:

~~~text
function runApprovedDeployment(context):
    identity = workloadIdentityProvider.obtain()
    token = tokenProvider.obtain(identity, requiredPamAudience, requiredScope)

    response = pamClient.checkout(
        token = token,
        resource = configuredDeploymentResource,
        approval = context.approvalReference,
        correlationId = context.runId
    )

    if response indicates invalid_token:
        tokenProvider.invalidate(token)
        newToken = tokenProvider.obtainFresh(identity)

        if checkoutOutcomeIsKnownNotCreated(response):
            response = pamClient.checkout(
                token = newToken,
                sameOperationContext = context
            )
        else:
            response = reconcileCheckoutOutcome(context)

    if response is successful:
        useGrantedCredentialForApprovedTask(response)
        closeOrReleaseLeaseAsSupported(response.leaseId)
    else:
        recordSanitizedFailure(response, context.runId)
        stopWithControlledError()
~~~

Điểm cần chú ý:

- Xác thực lại không đồng nghĩa được phép lặp vô hạn một thao tác tạo checkout hoặc xoay mật khẩu.
- Nếu kết nối ngắt sau khi server đã thực hiện thao tác, client có thể không biết kết quả. Cần tra cứu trạng thái hoặc dùng idempotency theo đúng hợp đồng API, nếu có.
- Không tự thêm một header “idempotency” rồi cho rằng server sẽ chống trùng.
- Token cache phải tách theo principal, môi trường, audience, scope và ràng buộc credential có liên quan.
- Khi nhiều thread cần token mới cùng lúc, dùng cơ chế phối hợp để tránh hàng trăm yêu cầu cấp token đồng thời.
- Thiết lập timeout và retry có giới hạn; không biến sự cố xác thực thành vòng lặp gây tải cho PAM.

Một cách lập lịch thay token là dựa trên thời điểm nhận token và expires_in, chừa một khoảng đệm phù hợp cho độ trễ và độ lệch đồng hồ. Với clock của tiến trình, cần tính đến các thay đổi đồng hồ hệ thống; không kéo dài hiệu lực token tại client.

## 10. Xử lý lỗi theo nguyên nhân

Mã HTTP và mã lỗi chi tiết phụ thuộc API. Bảng sau là cách diễn giải phổ biến cần đối chiếu với hợp đồng triển khai:

| Tình huống | Hành động của client | Thông tin cần kiểm tra |
|---|---|---|
| TLS handshake thất bại | Dừng yêu cầu, báo lỗi kết nối an toàn | CA tin cậy, hostname, hạn chứng thư, chứng thư client |
| Token endpoint báo invalid_client | Không retry liên tục cùng credential | Đăng ký client, khóa, chứng thư, trạng thái kích hoạt |
| Token endpoint báo invalid_scope | Sửa cấu hình yêu cầu hoặc policy qua quy trình quản trị | Scope hỗ trợ và quyền thực tế của client |
| PAM báo token không hợp lệ hoặc hết hạn | Cấp lại token có giới hạn, cân nhắc trạng thái thao tác | Audience, issuer, thời hạn, ràng buộc chứng thư |
| PAM báo thiếu quyền | Dừng thao tác và đối chiếu policy | Resource, action, approval, JIT, môi trường |
| Bị giới hạn tần suất | Backoff theo hướng dẫn server, giới hạn đồng thời | Quota, số lần cấp token, token cache |
| Timeout hoặc lỗi server | Retry có kiểm soát khi an toàn | Kết quả thao tác trước, khả năng idempotency |

Không “khắc phục” lỗi thiếu quyền bằng cách tự động thử lần lượt các API key khác hoặc chuyển sang tài khoản admin chung. Cách đó làm sai mô hình danh tính và có thể che một cấu hình phân quyền cần sửa.

Với 401 hoặc 403, không chỉ nhìn số mã HTTP. Xem mã lỗi đã được chuẩn hóa của sản phẩm, nhưng che dữ liệu nhạy cảm trước khi đưa vào log. Một số hệ thống cố ý không tiết lộ tài nguyên có tồn tại hay không cho client thiếu quyền.

## 11. Vòng đời client, khóa và chứng thư

### 11.1. Cấp mới

Một hồ sơ client nên có:

- Tên principal và mục đích tích hợp.
- Owner kỹ thuật và đầu mối xử lý sự cố.
- Môi trường, nền tảng chạy và tài nguyên được phép tác động.
- Cơ chế xác thực cùng vị trí bảo vệ credential.
- Hạn dùng, lịch rà soát và cách thu hồi.
- Yêu cầu audit, cảnh báo và giới hạn tần suất.

Quyền production cần được tách khỏi quyền thử nghiệm. Việc tách có thể dựa trên client, policy và phạm vi tin cậy; không chỉ dựa vào một tham số environment mà người gọi tự chọn.

### 11.2. Thay credential có khoảng chồng lấn

Khi sản phẩm hỗ trợ hai credential hợp lệ đồng thời, có thể thay theo trình tự:

1. Tạo khóa hoặc chứng thư mới trong cơ chế bảo vệ đã chọn.
2. Đăng ký credential mới và giữ credential cũ trong khoảng chuyển tiếp có giới hạn.
3. Triển khai workload sử dụng credential mới.
4. Kiểm tra thành công của token mới và lần gọi PAM theo danh tính dự kiến.
5. Xác nhận các instance, runner hoặc job còn sống đã chuyển đổi.
6. Thu hồi credential cũ và xác nhận nó không còn được chấp nhận.

Khoảng chồng lấn phải có điểm kết thúc. Nếu sản phẩm không hỗ trợ song song, thiết kế một cửa sổ chuyển đổi phù hợp thay vì giả định luôn có thể zero-downtime.

Với token ràng buộc chứng thư, token gắn với chứng thư cũ thường không thể dùng cùng chứng thư mới. Client cần quản lý cặp token và chứng thư tương ứng trong giai đoạn chuyển đổi, theo cơ chế thực tế của hệ thống.

### 11.3. Thu hồi

Cần phân biệt ít nhất ba hành động:

| Hành động | Đối tượng tác động | Điều cần xác minh thêm |
|---|---|---|
| Vô hiệu hóa credential của client | Các lần xác thực mới | Token đã cấp còn được chấp nhận đến khi nào |
| Thu hồi hoặc chặn access token | Các lần gọi API dùng token | Độ trễ cache, introspection hoặc policy tại gateway |
| Đóng lease, session hoặc thay credential đích | Quyền đã được PAM cấp ra | Phạm vi ảnh hưởng và khả năng tác vụ còn tiếp diễn |

JWT được xác minh cục bộ có thể còn được chấp nhận đến hết hạn nếu kiến trúc không có cơ chế chặn sớm. Ngược lại, việc introspection cũng có độ trễ và cache cần xác định. Không tuyên bố “thu hồi tức thì” nếu chưa có bằng chứng từ toàn bộ đường đi yêu cầu.

## 12. Audit có giá trị mà không lộ bí mật

Audit nên trả lời được: workload nào, chạy lần nào, dùng danh tính nào, yêu cầu hành động gì, trên tài nguyên nào, được cho phép vì policy nào và kết quả ra sao.

Bản ghi minh họa:

~~~json
{
  "event": "pam.api.request",
  "principal": "payments-deployer-prod",
  "authentication_method": "mtls",
  "credential_reference": "client-cert-version-7",
  "operation": "credential.checkout",
  "resource_reference": "database/payments-prod/deploy",
  "correlation_id": "deploy-payments-prod-1042",
  "approval_reference": "DEPLOY-1042",
  "decision": "allow",
  "policy_reference": "payments-deployment-policy",
  "result": "checkout_created",
  "lease_reference": "lease-example-1042"
}
~~~

Không ghi access token, client secret, khóa riêng, mật khẩu đích hoặc response có chứa bí mật. Thông tin tham chiếu chứng thư hoặc credential chỉ phục vụ nhận diện phiên bản, không phải nội dung credential.

Đồng bộ thời gian giữa nguồn danh tính, máy chủ cấp token, PAM và hệ thống audit để ghép sự kiện. Correlation ID là dữ liệu truy vết, không phải bằng chứng xác thực; giá trị từ client cần được kiểm tra định dạng và không được dùng trực tiếp để cấp quyền.

Cảnh báo hữu ích gồm:

- Client gọi API từ môi trường chạy hoặc tuyến mạng chưa từng được phê duyệt.
- Tăng nhanh số lần cấp token hoặc lỗi xác thực.
- Client yêu cầu scope, action hay resource ngoài lịch sử được phép.
- Credential sắp hết hạn nhưng chưa có kế hoạch thay.
- Credential cũ vẫn được sử dụng sau mốc chuyển đổi.
- Một danh tính không hoạt động lâu ngày bỗng checkout hàng loạt.
- Token cấp cho môi trường thử nghiệm xuất hiện trên API production.

Cảnh báo phải gắn với phản ứng cụ thể: liên hệ owner, chặn client, thu hồi token, dừng job hoặc kiểm tra lease. Chỉ thu log mà không có người chịu trách nhiệm xử lý thì giá trị kiểm soát bị giới hạn.

## 13. Tình huống thực hành: token bị lộ trong log pipeline

### Bối cảnh

Một pipeline được phép checkout credential deploy cho database payments. Trong lúc debug, thư viện HTTP in toàn bộ header Authorization vào log. Log được nhiều thành viên dự án đọc; token chưa hết hạn và có thể gọi từ mạng của runner.

### Phân tích

Điểm lộ là token truy cập PAM, chưa có bằng chứng rằng khóa xác thực gốc đã bị lộ. Tuy vậy, token có thể đã được dùng để tạo thêm checkout, và credential đích có thể đã được phát hành. Phạm vi điều tra phải theo chuỗi cấp quyền, không dừng ở việc xóa dòng log.

### Xử lý

1. Dừng đường ghi lộ bí mật và giới hạn quyền truy cập log theo quy trình sự cố.
2. Ghi lại các mốc thời gian và tham chiếu cần điều tra mà không sao chép token vào ticket.
3. Chặn token hoặc danh tính bị ảnh hưởng bằng cơ chế hệ thống hỗ trợ.
4. Đối chiếu audit cấp token, checkout, phiên truy cập và hoạt động trên database.
5. Đóng lease hoặc session không hợp lệ; thay credential đích nếu có nguy cơ đã bị lấy.
6. Thay credential khởi đầu nếu có bằng chứng nó cũng bị lộ hoặc không thể loại trừ phạm vi lộ đó.
7. Khôi phục pipeline sau khi kiểm tra cấu hình che bí mật và chính sách truy cập.

Không mặc định thay client secret sẽ vô hiệu hóa token đã phát hành. Cũng không mặc định hết hạn access token sẽ làm một session database đang hoạt động tự kết thúc.

### Cải thiện thiết kế

Giới hạn token vào audience PAM, thu hẹp quyền checkout, giữ thời hạn phù hợp và ngăn log thu Authorization. Nếu cả hai đầu hỗ trợ và vận hành được, đánh giá token có ràng buộc người gửi để giảm khả năng dùng lại bản sao token. Bản thân kiểm soát đó vẫn cần bảo vệ khóa và môi trường workload.

## 14. Các phép thử chấp nhận cho tích hợp

Thực hiện trong môi trường kiểm thử với tài nguyên và credential giả lập phù hợp. Không lấy credential production chỉ để chứng minh một bài kiểm tra xác thực.

| Phép thử | Kết quả cần quan sát |
|---|---|
| Workload đúng danh tính, đúng quyền và approval | Yêu cầu thành công, audit gắn đúng principal và lần chạy |
| Thiếu hoặc sai bằng chứng xác thực | Bị từ chối, không tạo checkout |
| Token hết hạn hoặc chưa có hiệu lực | Bị từ chối theo policy thời gian |
| Token của dịch vụ khác | Bị từ chối do đối tượng nhận không phù hợp |
| Token hợp lệ nhưng sai resource | Bị từ chối bởi phân quyền tài nguyên |
| Job thử nghiệm yêu cầu quyền production | Không nhận được quyền production |
| Token ràng buộc chứng thư được dùng với chứng thư khác | Bị từ chối khi cơ chế ràng buộc đã được hỗ trợ và bật |
| Credential cũ sau thời điểm thu hồi | Không thể xác thực mới bằng credential đó |
| Thu hồi client khi token đã được cấp | Hành vi thực tế phù hợp cam kết về độ trễ thu hồi |
| Timeout sau khi gửi một thao tác thay đổi trạng thái | Client kiểm tra kết quả trước khi thực hiện lại |
| Bật chế độ log thông thường và chế độ lỗi | Không xuất hiện token hay credential đích |
| Nhiều thread cùng cần token | Số yêu cầu cấp token vẫn được kiểm soát |

Lưu bằng chứng dưới dạng status, mã lỗi đã che bí mật, tham chiếu audit và kết quả tài nguyên. Không đưa token vào báo cáo kiểm thử.

Đây là các gợi ý kiểm chứng khi triển khai tích hợp. Hoàn tất một lượt gọi thành công chỉ chứng minh đường đi hợp lệ hoạt động; các phép thử bị từ chối mới giúp kiểm tra ranh giới quyền.

## 15. Những ngộ nhận cần tránh

**“Có TLS là đã xác thực client.”** TLS một chiều thường giúp client xác minh server và bảo vệ đường truyền. Danh tính chương trình gọi API vẫn cần cơ chế xác thực phù hợp.

**“client_id là bí mật.”** client_id chủ yếu là định danh. Bên xác thực cần kiểm tra credential hoặc bằng chứng gắn với định danh đó.

**“JWT đọc được thì dùng được.”** Đọc payload không kiểm tra chữ ký, audience, issuer hay thời hạn.

**“Token ngắn hạn thì không cần che log.”** Token có thể bị khai thác ngay trong thời gian còn hiệu lực.

**“mTLS lúc lấy token là token đã chống sao chép.”** Chỉ đúng khi token có ràng buộc phù hợp và phía nhận thực thi kiểm tra ràng buộc.

**“API client cần quyền admin để automation chạy ổn định.”** Quyền phải xuất phát từ các hành động và tài nguyên của nghiệp vụ, không từ mong muốn tránh lỗi phân quyền.

**“Đóng API client là đóng mọi quyền đích.”** Token, lease, session và credential đích có vòng đời riêng cần được xử lý.

**“Có ticket ID trong request là đủ approval.”** Tham chiếu do client gửi cần được đối chiếu với bằng chứng phê duyệt đáng tin cậy.

## 16. Tự kiểm tra kiến thức

1. Nếu client secret đã bị vô hiệu hóa nhưng access token còn hạn vẫn gọi được PAM, cần kiểm tra cơ chế nào trước khi kết luận thu hồi bị lỗi?
2. Một token hợp lệ có scope checkout nhưng bị từ chối khi truy cập một database khác. Sự từ chối này nói gì về phân quyền tài nguyên?
3. Vì sao một pipeline của cùng tổ chức nhưng khác project không nên tự động được dùng danh tính deploy production?
4. Cần xác minh thêm điều gì khi gateway kết thúc mTLS rồi chuyển tiếp yêu cầu tới PAM?
5. Sau khi token bị lộ và đã dùng để checkout mật khẩu, vì sao chỉ thu hồi token chưa đủ?
6. Khi timeout xảy ra sau yêu cầu tạo checkout, bằng chứng nào giúp quyết định có thể thử lại an toàn?

Gợi ý: tách xác thực mới khỏi token đã cấp; phân biệt scope và resource policy; ràng buộc trust tới workload cụ thể; bảo vệ chuỗi chuyển tiếp danh tính; lần theo lease và credential đích; xác minh kết quả thao tác thay vì đoán từ lỗi mạng.

## 17. Tài liệu tham khảo

Các nguồn sau giải thích giao thức; endpoint và policy PAM trong bài vẫn là thiết kế minh họa:

- [RFC 6749 — OAuth 2.0, luồng client credentials](https://www.rfc-editor.org/rfc/rfc6749.html#section-4.4).
- [RFC 8705 — mTLS client authentication và certificate-bound access tokens](https://www.rfc-editor.org/rfc/rfc8705.html).
- [RFC 9700 — thực hành bảo mật OAuth 2.0](https://www.rfc-editor.org/rfc/rfc9700.html): xem định hướng về xác thực client, giới hạn quyền của token và giảm nguy cơ phát lại; khả năng áp dụng phụ thuộc profile và sản phẩm.
