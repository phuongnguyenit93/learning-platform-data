# Short-lived deployment token

## 1. Vì sao quyền triển khai cần có thời hạn?

Một pipeline triển khai có thể đổi image đang chạy, cấu hình dịch vụ, định tuyến lưu lượng hoặc phiên bản ứng dụng trong môi trường production. Đây là quyền truy cập đặc biệt: người giữ quyền có thể tác động trực tiếp tới tính sẵn sàng và tính toàn vẹn của hệ thống, dù họ không đăng nhập bằng tài khoản quản trị tương tác.

Nếu quyền đó được biểu diễn bằng một token tồn tại nhiều tháng trong kho secret của CI/CD, token có thể tiếp tục sử dụng khi pipeline đã kết thúc, runner đã bị tái sử dụng hoặc người phụ trách đã chuyển nhóm. Mỗi lần token được sao chép sang một project khác còn làm phạm vi rủi ro tăng thêm.

**Short-lived deployment token** là thông tin xác thực cho phép một chủ thể triển khai thực hiện một tập hành động đã xác định trong một khoảng thời gian ngắn. Token được cấp theo nhu cầu của một lần chạy hoặc một tác vụ triển khai, thay vì được lưu sẵn để mọi pipeline dùng chung.

Trong quản lý truy cập đặc quyền (PAM), mục tiêu không chỉ là rút ngắn hạn sử dụng. Thiết kế cần đồng thời trả lời:

- Ai hoặc workload nào đang xin quyền?
- Quyền được cấp cho môi trường và tài nguyên nào?
- Artifact nào được phép triển khai?
- Hành động nào được phép thực hiện?
- Khi nào quyền bắt đầu và kết thúc?
- Có thể truy vết, dừng hoặc điều tra việc sử dụng quyền bằng cách nào?

Một token sống 5 phút nhưng có quyền quản trị toàn bộ hạ tầng vẫn tạo ra rủi ro lớn trong 5 phút đó. Thời hạn ngắn phải đi cùng least privilege, kiểm tra nguồn yêu cầu và bằng chứng sử dụng.

## 2. Ba khái niệm cần tách biệt

### 2.1. Danh tính của job

Danh tính job chứng minh yêu cầu đến từ một lần chạy cụ thể của hệ thống CI/CD. Ví dụ, nền tảng CI phát hành một bằng chứng danh tính có chữ ký cho job sau khi job bắt đầu.

Bằng chứng này có thể chứa thông tin về project, workflow, nhánh, lần chạy và bên nhận dự kiến. Nó giúp broker nhận diện job nhưng không tự động chứng minh job được phép triển khai production.

Đặc biệt, một chuỗi như tên nhánh hoặc tên môi trường do script tự gửi lên không có cùng mức tin cậy với claim được nền tảng CI xác thực. Ngay cả claim có chữ ký cũng chỉ có ý nghĩa trong giới hạn bảo đảm của bên phát hành.

### 2.2. Quyết định cho phép triển khai

Quyết định authorization kết hợp danh tính đã xác minh với chính sách:

~~~text
Job thuộc project được phép
AND workflow triển khai thuộc phiên bản đã được tin cậy
AND nguồn chạy đáp ứng chính sách
AND approval production còn hiệu lực
AND artifact đúng digest đã được duyệt
AND đích triển khai nằm trong phạm vi cho phép
=> có thể cấp quyền triển khai giới hạn
~~~

Việc token danh tính có chữ ký hợp lệ mới trả lời một phần câu hỏi “đây là ai”. Nó chưa trả lời đầy đủ câu hỏi “được làm gì”.

### 2.3. Token hoặc phiên triển khai tại đích

Sau khi phê duyệt, hệ thống có thể cấp:

- Token được deployment gateway chấp nhận.
- Credential tạm thời của nền tảng đích.
- Phiên đặc quyền ngắn hạn để gọi API triển khai.
- Một deployment handle để job theo dõi tác vụ do dịch vụ triển khai thực hiện.

Các cơ chế này không tương đương về thu hồi, cách lưu giữ và phạm vi quyền. Ví dụ, gateway có thể kiểm tra một grant trong cơ sở dữ liệu ở mỗi request, trong khi một đích khác chỉ kiểm tra chữ ký và hạn dùng của token.

Bài học này dùng mô hình **CI job → broker/PAM → deployment gateway → môi trường đích**. Đây là mô hình minh họa trung lập với nhà cung cấp; tên field, endpoint và policy bên dưới là quy ước của ví dụ, không phải cấu hình có thể áp dụng nguyên xi cho một sản phẩm.

## 3. Token dài hạn và token ngắn hạn khác nhau ở đâu?

| Khía cạnh | Token triển khai dài hạn dùng chung | Token ngắn hạn cấp theo job |
|---|---|---|
| Thời điểm có quyền | Quyền thường tồn tại cả khi không triển khai | Quyền chỉ được cấp khi đáp ứng điều kiện |
| Danh tính trong audit | Dễ chỉ thấy một tài khoản dịch vụ chung | Có thể liên kết với project, job và lần chạy |
| Phạm vi | Dễ tích lũy nhiều môi trường hoặc ứng dụng | Có thể giới hạn từng môi trường, dịch vụ, hành động |
| Hậu quả khi bị lộ | Có thể kéo dài tới khi phát hiện và thu hồi | Việc dùng mới bị giới hạn bởi hạn dùng và cơ chế thu hồi |
| Vận hành | Cần phân phối và luân chuyển secret dùng chung | Cần vận hành broker, policy và vòng đời credential |
| Điểm yếu còn lại | Secret có thể bị sao chép, tái sử dụng | Token còn hiệu lực vẫn có thể bị lợi dụng |

Token ngắn hạn không loại bỏ nhu cầu bảo vệ runner. Nếu runner đã bị chiếm quyền tại thời điểm job được phép triển khai, mã độc trong cùng môi trường có thể xin hoặc sử dụng token hợp lệ.

Lợi ích chính là giảm quyền thường trực, thu hẹp khoảng thời gian có thể sử dụng credential và tăng khả năng gắn quyền với ngữ cảnh triển khai cụ thể.

## 4. Kiến trúc và ranh giới tin cậy

Một thiết kế có thể phân chia trách nhiệm như sau:

| Thành phần | Trách nhiệm chính | Điều không nên mặc định tin |
|---|---|---|
| Nền tảng CI | Xác thực workload và phát hành bằng chứng danh tính | Mọi workflow trong cùng project đều an toàn |
| Policy engine | Đánh giá điều kiện cấp quyền | Giá trị môi trường do script tự khai là đã được duyệt |
| Broker hoặc PAM | Cấp grant/token, ghi audit, quản lý vòng đời | Runner sẽ tự hủy token đúng lúc |
| Deployment gateway | Kiểm tra quyền tại thời điểm gọi và ràng buộc request | Có token hợp lệ là được đổi mọi dịch vụ |
| Hệ thống đích | Thực thi quyền giới hạn của identity tại đích | Gateway phía trước thay thế được mọi kiểm soát tại đích |
| Audit store | Lưu quan hệ giữa approval, token và deployment | Log do runner gửi lên luôn đầy đủ và không thể sửa |

Luồng điển hình:

~~~mermaid
sequenceDiagram
    participant J as CI job
    participant I as CI identity issuer
    participant B as Broker / PAM
    participant A as Approval / Policy
    participant G as Deployment gateway
    participant T as Môi trường đích

    J->>I: Xin bằng chứng danh tính cho broker
    I-->>J: Bằng chứng danh tính ngắn hạn
    J->>B: Xin quyền cho release và môi trường
    B->>B: Xác minh issuer, audience, thời gian, nguồn job
    B->>A: Kiểm tra approval và policy
    A-->>B: Cho phép phạm vi cụ thể
    B-->>J: Deployment token và thông tin hết hạn
    J->>G: Gửi yêu cầu triển khai với token
    G->>G: Kiểm tra token, grant và request
    G->>T: Thực hiện hành động đã được cho phép
    T-->>G: Kết quả hoặc operation ID
    G-->>J: Deployment ID và trạng thái
    J->>B: Báo kết thúc hoặc yêu cầu đóng grant
~~~

Điểm quan trọng là broker và gateway cùng kiểm tra nhưng kiểm tra ở hai thời điểm khác nhau. Điều kiện đúng lúc cấp token có thể không còn đúng lúc sử dụng: approval bị hủy, job bị cancel hoặc môi trường đã bị khóa do sự cố.

Nếu gateway giữ một credential nền có quyền rộng và dài hạn, việc phát token ngắn hạn cho CI chỉ giải quyết rủi ro ở phía CI. Credential nền đó vẫn cần được kiểm kê, bảo vệ, giới hạn và luân chuyển; khi có thể, nên dùng identity của workload hoặc credential tạm thời ở chính đích.

## 5. Ràng buộc token với một ngữ cảnh triển khai

Một authorization grant tốt cần mô tả rõ phạm vi. Ví dụ:

~~~yaml
# Mô hình policy minh họa, không phải schema của một sản phẩm.
deploymentGrant:
  workload:
    projectId: payments-service
    workflowId: deploy-production
    workflowVersion: reviewed-workflow-revision
    runId: run-8821
    attempt: 1
  target:
    environment: production
    service: payment-api
    namespace: payments
  release:
    artifactDigest: sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
    releaseId: rel-2026-042
  authorization:
    actions:
      - deployment.create
    approvalId: apr-618
    maxLifetimeSeconds: 300
    renewableByDefault: false
  audit:
    changeId: chg-2048
    purpose: approved-release
~~~

Mỗi nhóm ràng buộc giải quyết một loại rủi ro:

- **Workload:** ngăn job ở project hoặc workflow khác xin cùng quyền.
- **Target:** ngăn token production của một dịch vụ dùng cho dịch vụ khác.
- **Release:** ngăn đổi artifact sau khi đã được phê duyệt.
- **Actions:** ngăn deployment token được dùng để tạo user, đổi IAM hoặc đọc toàn bộ secret.
- **Lifetime:** giới hạn thời gian credential còn được chấp nhận.
- **Audit:** tạo liên kết giữa lý do nghiệp vụ và hành động kỹ thuật.

Không phải hệ thống đích nào cũng hỗ trợ ràng buộc artifact digest trong token. Nếu đích chỉ hỗ trợ scope theo namespace, gateway hoặc dịch vụ triển khai phải đối chiếu digest ở mỗi yêu cầu triển khai. Một claim chỉ được ghi vào token nhưng không có thành phần nào kiểm tra thì không tạo ra kiểm soát thực tế.

Tương tự, token mang trường runId không tự khiến người cầm token trở thành đúng job đó. Nếu đây là bearer token, bất kỳ ai chiếm được token có thể sử dụng trong phạm vi mà nơi nhận cho phép. Muốn ràng buộc với bên gửi cần thêm cơ chế được hệ thống hỗ trợ, như khóa chứng minh quyền sở hữu hoặc kênh xác thực workload, cùng cách bảo vệ khóa phù hợp.

## 6. Cấp token: xác minh gì trước khi ký?

### 6.1. Xác minh bằng chứng danh tính

Broker cần áp dụng quy tắc dành cho loại bằng chứng đang dùng, thay vì chỉ giải mã payload rồi đọc tên project. Với bằng chứng có chữ ký, các kiểm tra thường bao gồm:

1. Issuer thuộc tập tin cậy và khóa xác minh đến từ cấu hình tin cậy.
2. Chữ ký hợp lệ với thuật toán được cho phép.
3. Audience đúng broker hoặc dịch vụ nhận dự kiến.
4. Thời điểm phát hành, bắt đầu hiệu lực và hết hạn đáp ứng chính sách.
5. Subject và các claim nguồn khớp workload được phép.
6. Các claim cần cho quyết định thực sự có mặt và có ngữ nghĩa đã được xác định.

Không lấy địa chỉ khóa xác minh tùy ý từ dữ liệu do bên gọi kiểm soát. Việc một token tự tuyên bố issuer hoặc đưa ra URL chứa khóa không đủ để tạo quan hệ tin cậy.

Nếu dùng JWT, cần phân biệt xác minh chữ ký với authorization. Việc đọc được JSON của JWT không chứng minh token hợp lệ; chữ ký hợp lệ cũng chưa chứng minh request được phép thay đổi production.

### 6.2. Xác minh nguồn chạy và approval

Đối với production, policy có thể yêu cầu workflow tin cậy, nhánh được bảo vệ và bước approval phù hợp với mức rủi ro. Không nên chỉ kiểm tra tên nhánh:

- Pull request từ nguồn không tin cậy có thể chạy code khác với nhánh đích.
- Workflow có thể checkout hoặc gọi script do người gửi thay đổi.
- Dependency hoặc action không được cố định phiên bản có thể đổi sau khi workflow được duyệt.
- Runner dùng chung có thể còn dữ liệu hoặc tiến trình của job trước.
- Artifact được deploy có thể khác artifact đã build và kiểm tra.

Approval nên gắn với tập dữ liệu bất biến hoặc được xác minh lại: release ID, artifact digest, môi trường và dịch vụ. Một approval “cho phép chạy pipeline” quá chung có thể bị tái sử dụng cho mục tiêu khác.

Broker phải có nguồn đáng tin cậy cho trạng thái approval. Không chấp nhận trường approved: true do job tự gửi như bằng chứng phê duyệt.

### 6.3. Cấp quyền vừa đủ

Role của deployment identity cần được thiết kế theo hành động thực tế. Ví dụ, pipeline cập nhật image của payment-api không nhất thiết cần:

- Quản trị cluster.
- Tạo identity hoặc gán role.
- Đọc secret của namespace khác.
- Sửa policy của broker.
- Vô hiệu hóa audit.

Nếu hành động deploy có thể thay service account, mount secret hoặc chạy image tùy ý, khả năng leo thang có thể lớn hơn tên quyền “deploy” thể hiện. Least privilege phải xét hiệu lực của tài nguyên có thể sửa, không chỉ tên API được gọi.

Khi hệ thống chỉ cung cấp role rộng, có thể dùng dịch vụ triển khai nhận yêu cầu khai báo hẹp, đối chiếu policy và thực hiện thay job. Credential rộng của dịch vụ đó vẫn là một tài sản đặc quyền cần quản lý riêng.

## 7. Thiết kế hạn dùng phù hợp với công việc

### 7.1. Thời điểm cấp ảnh hưởng tới mức phơi lộ

Nên cấp token gần thời điểm sử dụng. Nếu pipeline có 20 phút build, 10 phút kiểm tra và 2 phút gửi yêu cầu triển khai, cấp token production ngay từ đầu làm quyền tồn tại trong nhiều bước không cần quyền đó.

Một thứ tự hợp lý là:

~~~text
Build → kiểm tra → xác nhận artifact → approval
→ nhận danh tính job → xin token → gửi deployment
→ theo dõi kết quả bằng quyền đọc phù hợp → đóng grant
~~~

Nếu có khoảng chờ approval kéo dài, nên xin token sau khoảng chờ đó. Không giải quyết việc token hết hạn trong hàng đợi bằng cách cấp một token sống suốt cả ngày.

### 7.2. TTL là quyết định theo thao tác

TTL cần đủ cho việc chuẩn bị kết nối, gửi request và các lần thử lại nằm trong chính sách. Không có một giá trị cố định phù hợp với mọi môi trường.

Ví dụ minh họa:

| Công việc | Cách cấp quyền có thể phù hợp |
|---|---|
| Gửi một yêu cầu rollout mất vài giây | Token ngắn cho quyền tạo deployment |
| Theo dõi rollout trong nhiều phút | Handle hoặc token chỉ đọc dành cho deployment đó |
| Rollout gồm nhiều bước thay đổi có ghi | Mỗi bước xin quyền trong cùng một grant có hạn tổng |
| Công việc chờ operator phê duyệt | Chờ trước, cấp token sau khi approval hợp lệ |
| Tác vụ migration đặc quyền kéo dài | Thiết kế phiên riêng, timeout và khả năng dừng theo rủi ro |

Ví dụ token 300 giây trong bài chỉ nhằm minh họa. Giá trị thực tế cần dựa trên thời gian vận hành đo được, khả năng cấp lại và hậu quả khi credential bị sử dụng sai.

### 7.3. Không nhầm token hết hạn với deployment dừng

Giả sử gateway nhận request lúc 09:00:10, token hết hạn lúc 09:05:00 và rollout kết thúc lúc 09:08:00.

Nếu token chỉ dùng để chấp nhận request ban đầu, việc token hết hạn lúc 09:05 không tự động dừng rollout đã được chấp nhận. Đây có thể là hành vi đúng của dịch vụ bất đồng bộ.

Cần xác định riêng:

- Hạn chót được gửi hoặc chấp nhận hành động mới.
- Hạn của grant triển khai tổng thể.
- Thời gian tối đa operation được chạy.
- Điều kiện được phép tiếp tục từng bước.
- Cơ chế cancel hoặc rollback operation.

Nếu yêu cầu là “sau khi approval bị thu hồi không được thực hiện bước ghi tiếp theo”, bộ điều phối cần kiểm tra lại trạng thái trước từng bước có tác động. Chỉ kiểm tra token lúc nhận request đầu tiên không đáp ứng yêu cầu đó.

### 7.4. Gia hạn cần giới hạn tổng

Một chuỗi token 5 phút có thể tạo ra quyền liên tục nhiều giờ nếu job được gia hạn vô hạn. Do đó cần phân biệt thời hạn token và cửa sổ quyền tổng.

~~~text
Hạn token mới <= thời điểm hiện tại + TTL tối đa cho một token
Hạn token mới <= thời điểm kết thúc grant
Hạn token mới <= hạn approval theo chính sách
~~~

Nếu credential tại đích có vòng đời độc lập, broker phải giới hạn vòng đời đó theo grant hoặc quản lý việc đóng phiên tương ứng. Việc cho phép credential tại đích sống lâu hơn bằng chứng danh tính ban đầu có thể là một quyết định hợp lệ của giao thức, nhưng phải có giới hạn và audit rõ ràng.

Mỗi lần cấp lại cần kiểm tra job, approval, môi trường và policy hiện tại. Không tự động nâng TTL hoặc bỏ qua kiểm tra vì hệ thống đang deploy dở.

## 8. Hợp đồng token và kiểm tra tại nơi sử dụng

Một payload khái niệm có thể có dạng:

~~~json
{
  "iss": "trusted-deployment-broker",
  "sub": "ci:payments-service:run-8821:attempt-1",
  "aud": "production-deployment-gateway",
  "jti": "opaque-token-reference-73",
  "iat": 1800000000,
  "exp": 1800000300,
  "grant_id": "grant-73",
  "deployment_id": "dep-219",
  "environment": "production",
  "service": "payment-api",
  "actions": ["deployment.create"],
  "artifact_digest": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
}
~~~

Đây là dữ liệu minh họa, không phải token thực và không quy định rằng hệ thống bắt buộc dùng JWT. Với opaque token, các thuộc tính tương tự có thể nằm ở phía máy chủ và được tra cứu qua cơ chế xác minh token.

Tại gateway, cần kiểm tra cả tính hợp lệ của token lẫn sự phù hợp giữa token và request:

~~~text
Xác minh token và kiểu token được chấp nhận
Kiểm tra audience, thời gian, issuer và phạm vi
Kiểm tra grant chưa bị đóng hoặc thu hồi theo thiết kế
Đối chiếu môi trường, dịch vụ, digest và hành động với request
Áp dụng idempotency và chính sách chống phát lại cần thiết
Ghi sự kiện chấp nhận hoặc từ chối
Thực hiện đúng hành động đã được cho phép
~~~

Nếu request gửi environment=production nhưng token chỉ cho staging, phải từ chối. Không tự chọn role mạnh hơn, không tự sửa token và không coi môi trường trong URL là lý do bỏ qua scope.

Khi có nhiều nơi kiểm tra, cần tránh cách diễn giải khác nhau. Ví dụ, broker coi actions là danh sách hành động chính xác nhưng gateway lại xử lý chúng như prefix, vô tình cho phép nhiều API hơn.

Đối với thời gian, máy chủ cần đồng bộ đồng hồ và có chính sách dung sai nhỏ đã xác định. Dung sai không nên bị tăng tùy tiện để che lỗi vận hành; ở ranh giới hạn dùng phải hiểu dung sai đang ảnh hưởng tới khoảng thời gian chấp nhận token như thế nào.

## 9. Chống phát lại và thiết kế retry

### 9.1. TTL ngắn không làm bearer token thành token dùng một lần

Một bearer token còn hiệu lực có thể được gửi lại. Trường jti hoặc token ID giúp định danh và audit, nhưng bản thân trường đó không ngăn phát lại.

Muốn có quyền dùng một lần, nơi nhận phải theo dõi trạng thái sử dụng và tiêu thụ quyền theo cách nguyên tử. Trong môi trường nhiều replica, các replica cần thống nhất được trạng thái đó. Nếu mỗi replica chỉ lưu trong bộ nhớ riêng, một token có thể được chấp nhận nhiều lần ở các replica khác nhau.

Một lựa chọn khác là không phát bearer token ra runner: job gửi yêu cầu tới broker, broker thực hiện deployment trong phạm vi hẹp và trả lại deployment handle. Khi đó vẫn cần xác thực yêu cầu, kiểm soát replay và bảo vệ credential của broker.

### 9.2. Retry cần biết request trước đã được nhận chưa

Tình huống thường gặp:

1. Job gửi request tạo deployment.
2. Gateway đã nhận và bắt đầu thực hiện.
3. Kết nối bị đứt trước khi job nhận response.
4. Job gửi lại request.

Nếu mỗi request tạo một deployment mới, retry có thể tạo tác động trùng. Token dùng một lần nhưng không hỗ trợ đọc lại kết quả cũng có thể khiến job không biết deployment trước đã diễn ra hay chưa.

Vì vậy nên có idempotency key gắn với deployment và nội dung yêu cầu:

~~~text
Idempotency-Key: dep-219-create-v1

Request binding:
  project     = payments-service
  environment = production
  service     = payment-api
  digest      = sha256:aaaa...
  operation   = deployment.create
~~~

Gateway có thể trả lại operation đã tạo khi nhận cùng key và cùng nội dung. Nếu cùng key nhưng digest hoặc đích khác, gateway cần từ chối thay vì diễn giải thành một yêu cầu mới.

Việc ghi nhận idempotency key và chấp nhận tác động cần phối hợp để tránh hai request đồng thời cùng được thực hiện. Nếu hệ thống đích không hỗ trợ giao dịch chung với gateway, thiết kế phải xử lý trạng thái trung gian và đối soát; một bảng key riêng không tự bảo đảm đúng một lần thực thi ở đích.

### 9.3. Retry không phải đường vòng authorization

Idempotency giải quyết trùng tác động, không cấp lại quyền. Chính sách phải xác định rõ trường hợp token cũ đã hết hạn:

- Job có thể xin token mới sau khi được đánh giá lại để tiếp tục một yêu cầu chưa được chấp nhận.
- Job có thể dùng quyền đọc giới hạn để tra cứu kết quả của operation đã được chấp nhận.
- Job không được dùng idempotency key như một mật khẩu thay thế token.
- Việc gửi lại nội dung khác phải qua quyết định authorization mới.

Một idempotency key không nên là bí mật duy nhất để truy cập thông tin deployment.

## 10. Sử dụng token trong pipeline mà hạn chế lộ lọt

### 10.1. Giữ token trong bước có quyền

Đặt bước xin token và bước gửi deployment trong phạm vi nhỏ nhất. Không truyền token qua build artifact, output công khai, cache hoặc nhiều job nếu không có nhu cầu đã được đánh giá.

Các lựa chọn lưu giữ có đánh đổi riêng:

| Cách giữ token | Rủi ro cần xét |
|---|---|
| Trong bộ nhớ tiến trình | Tiến trình bị chiếm quyền hoặc dump vẫn có thể lộ |
| Biến môi trường | Có thể bị tiến trình con kế thừa hoặc xuất hiện trong thông tin chẩn đoán |
| File tạm với quyền truy cập hạn chế | Có thể tồn tại trên disk hoặc trong snapshot nếu cleanup không đủ |
| Kênh của credential helper | Cần tin cậy helper và kiểm soát bên có thể gọi |
| Broker giữ token, job nhận handle | Giảm số nơi thấy token nhưng broker trở thành thành phần đặc quyền |

Không có lựa chọn nào thay thế cách ly workload. Runner đặc quyền, mount socket quản trị hoặc cho phép job khác đọc cùng filesystem có thể làm các biện pháp trên mất hiệu lực.

### 10.2. Tránh đưa token vào nơi thường được ghi log

Không đưa token vào URL, query string, tên artifact hoặc tham số dòng lệnh nếu có thể tránh. Log shell, log HTTP, reverse proxy và dữ liệu chẩn đoán có thể ghi lại các vị trí này.

Ngay cả khi CI có tính năng che secret, không nên dựa hoàn toàn vào nó. Token có thể bị mã hóa, chia nhỏ, biến đổi hoặc xuất hiện ở một hệ thống log chưa biết giá trị để che.

Với HTTP, credential thường đi qua header được dịch vụ thiết kế cho authentication. Client và hệ thống trung gian vẫn cần được cấu hình để không ghi giá trị header đó.

Không chép token vào báo lỗi. Khi cần hỗ trợ, dùng grant ID, deployment ID, token reference và error code để đối soát.

### 10.3. Giảm thời gian lưu và xử lý cleanup

Sau khi gửi deployment, nếu các bước tiếp theo chỉ cần quyền đọc thì không tiếp tục giữ token có quyền ghi.

Cleanup ở phía runner có thể đóng client, xóa file tạm và ngừng truyền credential cho bước sau. Tuy nhiên:

- Xóa file không bảo đảm mọi bản sao trong cache, snapshot hoặc vùng lưu trữ đều biến mất.
- Gán biến thành rỗng không bảo đảm xóa toàn bộ bản sao trong bộ nhớ runtime.
- Job bị kill có thể không chạy được khối cleanup.
- Runner bị chiếm quyền có thể đã sao chép token trước khi cleanup.

Do đó expiry và đóng grant ở phía máy chủ là lớp kiểm soát độc lập. Không coi cleanup thành công trên runner là bằng chứng token chưa từng bị lộ.

## 11. Ví dụ một lần triển khai có kiểm soát

Giả sử nhóm Payments muốn triển khai payment-api lên production. Pipeline đã build artifact, kiểm tra và nhận approval cho digest cụ thể.

### 11.1. Yêu cầu cấp quyền

~~~http
POST /deployment-grants
Authorization: Bearer <CI_WORKLOAD_IDENTITY>
Content-Type: application/json

{
  "releaseId": "rel-2026-042",
  "environment": "production",
  "service": "payment-api",
  "artifactDigest": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "approvalId": "apr-618",
  "requestedActions": ["deployment.create"],
  "requestedLifetimeSeconds": 300
}
~~~

Broker không tin các field trên chỉ vì chúng xuất hiện trong JSON. Broker xác minh danh tính job, tra release và approval qua nguồn tin cậy, rồi lấy giao giữa quyền job được phép, quyền approval cho phép và quyền request yêu cầu.

Thời hạn thực cấp có thể ngắn hơn thời hạn job yêu cầu. Nếu request vượt phạm vi, cách xử lý phải được xác định rõ; không âm thầm cấp quyền rộng hơn để pipeline chạy được.

Response giả định:

~~~json
{
  "grantId": "grant-73",
  "token": "<REDACTED_DEPLOYMENT_TOKEN>",
  "expiresAt": "<server-issued-expiration>",
  "deploymentId": "dep-219",
  "allowedActions": ["deployment.create"]
}
~~~

Pipeline dùng thông tin hết hạn do server cấp để quản lý việc sử dụng token, không tự cho rằng token có đúng 300 giây còn lại khi bắt đầu gọi.

### 11.2. Gửi yêu cầu triển khai

~~~http
POST /deployments/dep-219
Authorization: Bearer <DEPLOYMENT_TOKEN>
Idempotency-Key: dep-219-create-v1
Content-Type: application/json

{
  "environment": "production",
  "service": "payment-api",
  "artifactDigest": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
}
~~~

Gateway đối chiếu request với grant. Nó không cho phép pipeline thay digest sau approval hoặc thêm trường cấu hình khiến workload chạy bằng một identity quản trị ngoài phạm vi đã được duyệt.

Gateway trả về operation ID. Sau đó pipeline chỉ cần theo dõi operation đó bằng credential có quyền đọc phù hợp hoặc cơ chế theo dõi đã được xác thực.

### 11.3. Mã giả cho vòng đời

~~~text
release = load_verified_release_reference()
approval = resolve_approved_deployment(release)

identity = obtain_workload_identity(audience = trusted_broker)
grant = broker.issue(identity, release, approval)

try:
    operation = gateway.create_deployment(
        token = grant.token,
        deployment_id = grant.deployment_id,
        artifact_digest = release.digest,
        idempotency_key = stable_key_for_this_deployment
    )
    discard_write_token_when_no_longer_needed()

    result = observe_operation_with_scoped_read_access(operation.id)
    record_pipeline_result(operation.id, result)
finally:
    request_grant_closure_if_supported(grant.id)
    cleanup_local_credential_material()
~~~

Đây là mã giả mô tả trách nhiệm, không phải SDK cụ thể. Khối finally chỉ tăng khả năng cleanup trong những lỗi mà tiến trình còn xử lý được. Broker vẫn cần tự kết thúc grant theo hạn tổng và cơ chế kiểm tra trạng thái.

Một lần triển khai tiếp theo hoặc một lần rerun mới phải có định danh attempt và quyết định cấp quyền rõ ràng. Không mặc định dùng lại token còn sót từ lần chạy trước.

## 12. Thu hồi, hủy job và ứng phó sự cố

### 12.1. Thu hồi có hiệu lực phụ thuộc nơi thực thi

Nếu gateway kiểm tra trạng thái grant ở mỗi request, việc đóng grant có thể chặn request tiếp theo khi trạng thái mới đã có hiệu lực. Độ trễ còn phụ thuộc cache, đồng bộ dữ liệu và khả năng truy cập nơi kiểm tra.

Nếu nơi nhận chỉ xác minh token tự chứa và thời gian, token đã phát hành có thể vẫn được chấp nhận tới khi hết hạn, trừ khi có thêm cơ chế từ chối được nơi nhận hỗ trợ. Đổi trạng thái trong cơ sở dữ liệu của broker không tự truyền thành quyết định thu hồi ở mọi nơi nhận.

Không nên dùng thay khóa ký toàn hệ thống làm cách thu hồi thường ngày cho một job. Hành động đó có phạm vi ảnh hưởng rộng và còn phụ thuộc cách các nơi nhận cập nhật khóa, cache và chính sách xác minh.

### 12.2. Hủy job cần xử lý nhiều lớp

Khi job bị cancel hoặc nghi bị chiếm quyền, có thể cần:

1. Ngăn broker phát token mới cho run hoặc attempt liên quan.
2. Đóng grant và thu hồi credential tại đích nếu hệ thống hỗ trợ.
3. Chặn sử dụng token đã phát ở các điểm thực thi có khả năng thu hồi.
4. Kiểm tra operation đang chạy và quyết định tiếp tục, cancel hoặc rollback.
5. Cách ly runner và bảo toàn bằng chứng cần cho điều tra.
6. Xác minh có thay đổi quyền, cấu hình hoặc credential phát sinh hay không.

Không tự động rollback trong mọi sự cố chỉ vì token bị lộ. Rollback là một hành động có tác động riêng và có thể làm gián đoạn hệ thống; cần dựa trên trạng thái thực tế và quy trình ứng phó đã định.

### 12.3. Token hết hạn không xóa tác động đã tạo

Trong thời gian còn hiệu lực, token có thể đã được dùng để triển khai image khác, sửa cấu hình hoặc tạo tài nguyên. Các tác động đó có thể tồn tại lâu hơn token.

Vì vậy việc điều tra phải xét hành động và trạng thái hệ thống, không chỉ xác nhận exp đã qua. Cần đối chiếu artifact đang chạy, thay đổi quyền và các operation liên quan.

Đây cũng là lý do không cấp quyền tạo credential dài hạn hoặc quyền thay đổi IAM cho một deployment token thông thường. Nếu token ngắn hạn tạo được quyền lâu dài, lợi ích của hạn dùng có thể bị vượt qua.

## 13. Audit: lưu bằng chứng để nối được toàn bộ chuỗi

Một sự kiện token được cấp thành công chưa đủ để chứng minh một deployment đã được kiểm soát. Cần nối được:

~~~text
Change / release
→ approval
→ workload identity đã xác minh
→ grant được cấp
→ request được chấp nhận
→ operation tại đích
→ kết quả triển khai và đóng grant
~~~

Các trường có ích gồm:

| Nhóm | Ví dụ dữ liệu cần lưu |
|---|---|
| Nguồn yêu cầu | Project ID, workflow ID/revision, run ID, attempt |
| Quyết định | Policy ID/version, decision ID, kết quả và lý do |
| Approval | Approval ID, đối tượng được duyệt, thời gian còn hiệu lực |
| Phạm vi | Môi trường, dịch vụ, namespace, action, artifact digest |
| Vòng đời quyền | Grant ID, token reference, thời điểm cấp, hết hạn, đóng hoặc thu hồi |
| Thực thi | Deployment ID, operation ID, idempotency key, trạng thái tại đích |
| Điều tra lỗi | Mã từ chối, thời điểm, điểm thực thi và correlation ID |

Không ghi giá trị token, private key hoặc toàn bộ header Authorization vào audit. Một reference không mang quyền truy cập thường hữu ích hơn việc lưu credential để “dễ điều tra”.

Bằng chứng từ broker và gateway nên được lưu ở nơi job không có quyền sửa hoặc xóa. Log của pipeline hỗ trợ quan sát nhưng không nên là bằng chứng duy nhất, nhất là khi đang điều tra runner bị chiếm quyền.

Thời điểm và ID phải đủ nhất quán để nối sự kiện giữa các hệ thống. Cũng cần quy định retention, người được xem log và việc bảo vệ metadata nhạy cảm của môi trường production.

## 14. Những tình huống lỗi cần định nghĩa trước

| Tình huống | Cách xử lý phù hợp với nguyên tắc đặc quyền tối thiểu |
|---|---|
| Token hết hạn trước khi request được chấp nhận | Xin token mới sau khi kiểm tra lại điều kiện; không tăng TTL tự động |
| Mất response sau khi gateway đã nhận request | Tra operation theo định danh ổn định và áp dụng idempotency |
| Approval bị hủy giữa lúc cấp và dùng token | Gateway kiểm tra trạng thái theo thiết kế; từ chối bước ghi mới nếu điều kiện không còn |
| Broker không truy cập được policy hoặc approval | Không cấp mới theo phỏng đoán; phát lỗi rõ để xử lý vận hành |
| Điểm xác minh không truy cập được trạng thái thu hồi | Thực hiện chính sách đã định theo mức rủi ro, nêu rõ ảnh hưởng của cache và độ trễ |
| Job chạy lại cùng commit | Xác định run/attempt và approval được phép; không dùng token cache của attempt cũ |
| Artifact trong request khác digest được duyệt | Từ chối và ghi lý do sai ràng buộc |
| Runner bị hủy trước cleanup | Dựa vào hạn dùng và vòng đời server; kiểm tra credential và operation còn lại |
| Đích triển khai không hỗ trợ credential ngắn hạn | Dùng gateway với quyền nền được quản lý hoặc thay cơ chế xác thực, nêu rõ giới hạn |
| Rollout kéo dài hơn TTL | Theo dõi operation đã nhận hoặc cấp quyền theo bước; không tự coi TTL là timeout của rollout |

Đối với production, thiết kế thường cần dừng việc cấp quyền mới khi không xác minh được điều kiện bắt buộc. Một đường khẩn cấp, nếu có, phải là cơ chế break-glass được quản trị riêng với người chịu trách nhiệm và bằng chứng; không cài sẵn token quản trị dài hạn như một fallback ẩn.

Cache quyết định authorization giúp giảm phụ thuộc và độ trễ nhưng làm tăng thời gian phản ứng với thu hồi. Cần định lượng thời gian cache, phạm vi quyết định được cache và tình huống buộc kiểm tra lại.

## 15. Các thiết kế dễ tạo cảm giác an toàn sai

### “Chỉ cần hạ TTL là đủ”

TTL không giảm scope. Token tồn tại 60 giây nhưng có thể tạo admin user vẫn rất nguy hiểm. Cần giới hạn hành động và kiểm soát khả năng tạo quyền tồn tại lâu hơn token.

### “Đặt token trong vault thì không cần đổi cơ chế”

Vault giúp bảo vệ và quản lý secret, nhưng một deployment token dài hạn lấy từ vault vẫn có thể là credential dài hạn khi bị sao chép ra runner.

Nếu vault hoặc broker tạo credential động và quản lý lease, cần xác minh đích thực thi hạn dùng và thu hồi như thế nào. Tên gọi lease trong một hệ thống không tự bảo đảm mọi phiên hoặc credential phát sinh cùng kết thúc.

### “OIDC nghĩa là không còn secret hay rủi ro token”

Liên kết danh tính workload có thể giảm việc phân phối secret tĩnh cho CI. Bằng chứng danh tính và credential tạm thời được cấp vẫn cần bảo vệ; các thành phần phát hành, khóa và quan hệ tin cậy vẫn là tài sản nhạy cảm.

Một cấu hình tin cậy cho phép mọi project hoặc mọi workflow có thể cấp quyền sai dù giao thức xác thực hoạt động đúng.

### “Có approval là có thể deploy bất kỳ artifact nào”

Approval phải gắn với đúng đối tượng và đích triển khai. Nếu artifact được xác định bằng tag có thể thay đổi, approval có thể không còn mô tả nội dung thực sự được triển khai.

Digest giúp tham chiếu nội dung bất biến; nó không tự chứng minh artifact an toàn hoặc được build bởi nguồn tin cậy. Nguồn gốc và kiểm tra artifact là các điều kiện bổ sung khi chính sách yêu cầu.

### “Token hết hạn thì mọi phiên đã mở cũng kết thúc”

Một dịch vụ có thể dùng token để mở session, tạo credential khác hoặc bắt đầu operation. Cần theo dõi vòng đời của các đối tượng đó. Hạn token đầu vào không mặc nhiên là hạn của mọi quyền được tạo ra từ nó.

### “Deployment handle không phải token nên có thể công khai”

Nếu chỉ cần cầm handle là có thể xem dữ liệu nhạy cảm hoặc cancel deployment, handle đang mang tính chất capability. Nó cần được bảo vệ hoặc đi kèm xác thực và authorization phù hợp.

## 16. Áp dụng với mô hình triển khai trực tiếp và GitOps

Trong triển khai trực tiếp, CI gọi API của đích hoặc gateway để thay đổi môi trường. Deployment token ngắn hạn gắn với hành động đó và cần giới hạn quyền tại đích.

Trong một mô hình GitOps, CI có thể chỉ cập nhật nguồn khai báo, còn controller trong môi trường chịu trách nhiệm đồng bộ. Khi đó cần tách hai quyền:

- Quyền ngắn hạn của CI để đề xuất hoặc cập nhật thay đổi vào kho khai báo.
- Quyền của controller để áp dụng thay đổi lên môi trường.

Token ngắn hạn cho CI không tự làm quyền của controller thành ngắn hạn. Controller vẫn là một workload đặc quyền cần identity riêng, phân tách môi trường, giới hạn tài nguyên và audit.

Ngoài ra, nếu CI sửa được nguồn mà controller tin cậy tuyệt đối, quyền sửa nguồn đó có thể tương đương quyền tác động production. Vì vậy ràng buộc approval, artifact digest, nhánh được bảo vệ và nội dung thay đổi vẫn cần được thực thi tại ranh giới phù hợp.

Không cấp thêm quyền triển khai trực tiếp cho CI chỉ để tránh một bước kiểm soát trong quy trình GitOps. Hãy xác định rõ hệ thống nào là nơi quyết định và thực thi thay đổi production.

## 17. Bài tập thiết kế

Một pipeline triển khai hai ứng dụng, order-api và billing-api. Nó dùng chung token sống 90 ngày để cập nhật cả staging và production. Job build từ pull request chạy trên runner dùng lại. Khi deploy lỗi, pipeline tự retry toàn bộ bước triển khai.

Hãy thiết kế lại cơ chế truy cập theo các yêu cầu sau:

1. Job từ nguồn chưa tin cậy không thể nhận quyền production.
2. Approval chỉ cho phép một dịch vụ và một artifact digest.
3. Token được cấp ngay trước bước sử dụng.
4. Quyền triển khai không bao gồm sửa IAM hay đọc secret ngoài nhu cầu.
5. Retry không tạo hai deployment cho cùng một yêu cầu.
6. Cancel job chặn cấp quyền mới và có quy trình xử lý operation đang chạy.
7. Audit nối được approval, run, grant và deployment.

Một phương án hợp lý là dùng danh tính workload của job tin cậy để xin grant riêng cho từng dịch vụ và môi trường. Broker xác minh approval và digest; gateway áp dụng cùng ràng buộc khi nhận request. Mỗi deployment có idempotency key ổn định và operation ID để theo dõi.

Phần build không cần token triển khai. Job chỉ theo dõi operation dùng quyền đọc phù hợp. Grant có hạn tổng, không gia hạn vô hạn. Credential nền tại đích, nếu còn cần, phải được quản lý riêng thay vì xem như rủi ro đã biến mất.

Các câu hỏi tự kiểm tra:

- Một token production của order-api có dùng cho billing-api được không? Thành phần nào từ chối?
- Nếu token bị lộ trong phút cuối còn hiệu lực, hành động tối đa kẻ giữ token có thể làm là gì?
- Nếu job timeout sau khi request đã được nhận, làm sao xác định trạng thái mà không tạo deployment mới?
- Nếu approval bị hủy, mất bao lâu mọi điểm thực thi ngừng chấp nhận bước ghi mới?
- Nếu token hết hạn nhưng rollout còn chạy, ai quyết định có tiếp tục hay không?
- Bằng chứng nào cho thấy artifact đang chạy đúng là artifact đã được duyệt?

Trả lời được các câu hỏi này bằng policy, điểm kiểm tra và dữ liệu audit cụ thể cho thấy thiết kế đã vượt khỏi việc chỉ đặt một giá trị TTL.

## 18. Các điểm cần ghi nhớ

Short-lived deployment token đưa quyền triển khai vào một cửa sổ thời gian có kiểm soát. Trong PAM, hiệu quả của nó phụ thuộc vào việc xác minh đúng workload, cấp đúng phạm vi và kiểm tra quyền ở nơi thực thi.

Một thiết kế đầy đủ liên kết được danh tính job, approval, môi trường, dịch vụ, artifact và hành động. Nó phân biệt hạn token với hạn grant, vòng đời session và thời gian operation chạy; đồng thời xử lý retry, thu hồi và bằng chứng sử dụng.

Token càng ngắn hạn càng có thể giảm khoảng thời gian credential bị lạm dụng, nhưng không xóa tác động đã xảy ra. Quyền tối thiểu, cách ly runner, kiểm soát nguồn triển khai và audit là những phần cùng tạo nên cơ chế triển khai đặc quyền có thể quản lý.
