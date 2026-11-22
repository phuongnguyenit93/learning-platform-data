# IAM Access Analyzer, policy simulator và xử lý AccessDenied

Một ứng dụng chạy trên AWS có thể gặp lỗi **AccessDenied** dù kỹ sư đã gắn một IAM policy có **Effect: Allow**. Nguyên nhân đôi khi là sai principal, sai ARN tài nguyên, thiếu một action, điều kiện không khớp, **explicit deny** ở policy khác, hoặc quyền truy cập liên tài khoản chưa được hai phía chấp nhận. Để xử lý hiệu quả, cần phối hợp **IAM Access Analyzer**, **IAM Policy Simulator**, nhật ký **AWS CloudTrail** và cơ chế đánh giá quyền AWS.

Đây là bài học của chương **IAM và phân quyền**, thuộc mô-đun **CLOUD_PROVIDERS_AWS**. Trong lộ trình khám phá Region/AZ, IAM, VPC, dịch vụ tính toán, lưu trữ, cơ sở dữ liệu, tích hợp và serverless, việc hiểu đúng quyền truy cập giúp người học chọn dịch vụ và triển khai ứng dụng an toàn, có khả năng giám sát, phục hồi và kiểm soát chi phí vận hành.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt mục đích của **IAM Access Analyzer**, **policy validation**, **IAM Policy Simulator** và **CloudTrail**.
2. Giải thích vì sao **Allow** trong một policy chưa đủ kết luận yêu cầu API sẽ thành công.
3. Sử dụng policy validation và policy simulation để kiểm tra lỗi policy, quyền được cấp, context và các giới hạn.
4. Xây dựng quy trình truy vết lỗi AccessDenied ở IAM, S3, KMS và STS AssumeRole, kể cả **cross-account**.
5. Đọc kết quả **allowed**, **explicitDeny**, **implicitDeny** và biết khi nào phải kiểm tra trên môi trường thực tế.
6. Đề xuất cách khắc phục theo nguyên tắc **least privilege**, không mở rộng quyền quá mức chỉ để làm lỗi biến mất.

## 2. Nền tảng: AWS quyết định cho phép hay từ chối thế nào?

Mỗi yêu cầu gọi AWS API có ngữ cảnh gồm **principal** (ai gọi), **action** (làm gì), **resource** (trên tài nguyên nào) và các thuộc tính **condition** (khi nào, từ đâu, thông qua đường nào). Một principal có thể là IAM user, IAM role session hoặc service principal. ARN giúp nhận diện tài nguyên và danh tính.

Ví dụ, một ứng dụng dùng role **ReportReader** để gọi **s3:GetObject** trên object **arn:aws:s3:::training-report-bucket/reports/november.csv**. AWS có thể phải xem xét:

| Lớp kiểm soát | Câu hỏi điều tra |
|---|---|
| **Identity-based policy** | Role/user có được phép thực hiện **s3:GetObject** với đúng ARN không? |
| **Resource-based policy** | Bucket, queue, key hay tài nguyên đích có policy cho phép/từ chối principal không? |
| **Permissions boundary** | Role/user có bị giới hạn trần quyền không? |
| **Session policy** | Phiên STS hiện tại có bị thu hẹp quyền không? |
| **AWS Organizations SCP/RCP** | Tài khoản hoặc tài nguyên có nằm trong giới hạn cấp tổ chức không? |
| **Service-specific controls** | S3 Block Public Access, object ownership, KMS key policy, VPC endpoint policy hoặc hạn chế riêng của dịch vụ có tác động không? |
| **Request context** | Các điều kiện như tag, principal, TLS, IP, Region, source ARN có thực sự khớp không? |

Ba nguyên tắc cơ bản:

- **Implicit deny (từ chối mặc định):** nếu không có Allow hợp lệ, yêu cầu bị từ chối.
- **Explicit allow:** statement **Allow** khớp với yêu cầu có thể cấp quyền, tùy các giới hạn và yêu cầu phía tài nguyên.
- **Explicit deny:** một **Deny** tường minh áp dụng cho yêu cầu sẽ chặn thao tác, kể cả khi tồn tại Allow ở nơi khác.

Trong **cùng tài khoản**, quyền từ identity-based và resource-based policy thường được kết hợp theo phép hợp, nhưng kết quả còn phụ thuộc permissions boundary, session policy, SCP/RCP và cách resource-based policy chỉ định IAM user, role hoặc **role session**. Với **cross-account**, cần kiểm tra quyền của cả **tài khoản có principal** và **tài khoản sở hữu tài nguyên**. Không dùng một công thức phép hợp/giao duy nhất cho mọi kiểu principal và dịch vụ.

## 3. Chọn đúng công cụ

| Công cụ | Câu hỏi chính | Đầu ra | Giới hạn cần nhớ |
|---|---|---|---|
| **IAM Access Analyzer — external access findings** | Tài nguyên nào có thể truy cập được từ principal ngoài ranh giới tin cậy đã định? | Findings về quyền truy cập ngoài dự kiến, theo loại tài nguyên được hỗ trợ | Không phải mọi dịch vụ/tài nguyên đều được phân tích; finding phản ánh chính sách và phạm vi analyzer, không chứng minh đã xảy ra truy cập |
| **IAM Access Analyzer — unused access findings** | Quyền, vai trò hoặc user nào có dấu hiệu không được sử dụng trong cửa sổ phân tích? | Findings giúp rà soát quyền dư thừa | Dữ liệu lịch sử/quan sát có giới hạn; quyền không thấy dùng chưa chắc không còn cần cho tình huống hiếm |
| **IAM Access Analyzer — policy validation** | JSON policy có lỗi, cảnh báo, khuyến nghị hoặc vấn đề bảo mật đã biết không? | Finding theo mức độ: error, security warning, warning, suggestion tùy loại | Kiểm tra tĩnh, **không xác nhận API sẽ được Allow** |
| **IAM Policy Simulator** | Với action, resource và context giả lập, principal có khả năng được Allow hay Deny? | **allowed**, **explicitDeny**, **implicitDeny**, chi tiết statement/context khi được hỗ trợ | Mô phỏng không tái hiện toàn bộ kiểm soát của mọi dịch vụ và trạng thái thực tế |
| **AWS CloudTrail** | Đã có lời gọi API nào? Ai gọi, gọi lúc nào, trên endpoint nào, nhận lỗi gì? | Sự kiện về yêu cầu thực tế và các trường liên quan | Cần xem loại sự kiện được ghi; **S3 object-level data events** thường phải được cấu hình để có |
| **STS get-caller-identity** | Credentials hiện tại thực sự đại diện cho principal nào? | Account, UserId, ARN | Cho biết danh tính, **không xác nhận quyền thực thi action đích** |

Thứ tự sử dụng thường hiệu quả:

1. Dùng **Access Analyzer** để phát hiện chia sẻ ngoài ý muốn và kiểm tra cấu trúc policy trước hoặc sau thay đổi.
2. Dùng **Policy Simulator** để tìm policy/condition có khả năng ảnh hưởng đến một hành động cụ thể.
3. Dùng **CloudTrail** và lời gọi thử có kiểm soát để xác thực hành vi thật, nhất là khi có cross-account hoặc service-specific policy.

## 4. IAM Access Analyzer: phân tích quyền ở mức chính sách

IAM Access Analyzer gồm những tính năng có mục tiêu khác nhau. Cần phân biệt **access findings** của analyzer đã tạo với chức năng **policy validation** chạy trên nội dung JSON; hai loại kết quả không tương đương.

### 4.1. External access findings: tài nguyên bị chia sẻ ra ngoài

Khi tạo analyzer phù hợp, bạn xác định một **zone of trust**, thường là tài khoản AWS hoặc tổ chức AWS Organizations. Access Analyzer xem xét policy của **các loại tài nguyên được hỗ trợ** để phát hiện quyền truy cập có thể được cấp cho principal **ngoài** ranh giới tin cậy này.

Ví dụ: một S3 bucket policy vô tình cho phép role của tài khoản đối tác không nằm trong tổ chức. Analyzer có thể tạo finding để nhóm bảo mật kiểm tra lại tính chủ ý của việc chia sẻ.

Quy trình:

1. Chọn đúng **Region**, tài khoản và phạm vi analyzer phù hợp; một số loại analyzer/findings có yêu cầu Region hoặc hỗ trợ dịch vụ riêng.
2. Xem principal, tài nguyên, action, điều kiện, trạng thái và căn cứ tạo finding.
3. Phân loại quyền chia sẻ đó là **chủ ý và có kiểm soát** hay **ngoài dự kiến**.
4. Với truy cập không mong muốn, chỉnh sửa resource policy/trust policy hoặc biện pháp bảo vệ liên quan.
5. Với ngoại lệ được phê duyệt, lưu lý do, chủ sở hữu và lịch rà soát; quản lý finding/archive rule theo quy trình tổ chức.

**Lưu ý:** không có finding không có nghĩa **mọi truy cập đều an toàn**. Analyzer có phạm vi, loại tài nguyên hỗ trợ và mô hình suy luận riêng; findings về **khả năng truy cập** cũng không khẳng định một principal đã thực sự đọc dữ liệu.

### 4.2. Unused access findings: rà soát quyền không sử dụng

Các kết quả phân tích quyền không sử dụng có thể giúp phát hiện IAM user/role hoặc quyền có thể đang dư thừa trong khoảng thời gian được cấu hình. Đây là căn cứ để **thu hẹp quyền**, giảm phạm vi ảnh hưởng nếu credentials bị lộ.

Ví dụ, một role được cấp **s3:GetObject**, **s3:PutObject** và **s3:DeleteObject**, nhưng dữ liệu sử dụng được ghi nhận chủ yếu chỉ liên quan đến hành động đọc. Nhóm kỹ thuật cần kiểm tra xem thao tác xóa có phải dành cho quy trình định kỳ hiếm khi xảy ra hay không, sau đó mới quyết định loại bỏ.

Không được tự động xóa tất cả quyền được gắn nhãn unused mà không xem nhu cầu nghiệp vụ, sự kiện khôi phục thảm họa, thao tác theo mùa và giới hạn dữ liệu quan sát. Việc khả dụng và chi phí của các tính năng phân tích cần được xác minh trong tài khoản/Region đang dùng.

### 4.3. Validate policy: phát hiện lỗi trước khi triển khai

**Policy validation** nhận nội dung JSON và phân tích các vấn đề như cú pháp, phần tử không hỗ trợ, hành động/tài nguyên hoặc cách sử dụng policy không phù hợp. Kết quả có thể gồm **ERROR**, **SECURITY_WARNING**, **WARNING** và **SUGGESTION**, kèm vị trí và hướng dẫn khi được cung cấp.

Ví dụ identity-based policy hợp lệ về cú pháp, chỉ cho phép đọc object thuộc prefix:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadReports",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::learning-reports-demo/reports/*"
    }
  ]
}
~~~

Giả sử nội dung nằm trong tệp **identity-policy.json** trong môi trường thử nghiệm. Lệnh kiểm tra:

~~~bash
aws accessanalyzer validate-policy \
  --policy-type IDENTITY_POLICY \
  --policy-document file://identity-policy.json
~~~

Với resource-based policy, chọn **RESOURCE_POLICY** và điền các tham số phù hợp nếu API yêu cầu đối với loại tài nguyên. Người học cần đọc từng finding để hiểu ý nghĩa; một policy **không có finding** vẫn có thể thiếu **s3:GetObject** cho ARN thực tế, sai principal hoặc bị Deny bởi policy khác.

**Policy validation là kiểm tra tĩnh, không phải mô phỏng một lời gọi API.**

### 4.4. Sinh policy từ hoạt động đã quan sát

IAM Access Analyzer có khả năng hỗ trợ tạo chính sách dựa trên hoạt động được ghi trong **CloudTrail** đối với những phạm vi được hỗ trợ. Chức năng này giúp nhóm vận hành bắt đầu từ hoạt động thực tế để thu hẹp policy quá rộng.

Nhưng policy sinh từ lịch sử không bảo đảm đã bao quát các API hiếm dùng hoặc các điều kiện/tài nguyên phù hợp nhất. Người học phải xem lại action cần thiết, ARN, condition, thao tác quản trị/khôi phục, rồi kiểm thử trước khi đưa vào production.

## 5. IAM Policy Simulator: mô phỏng quyết định cho phép/từ chối

IAM Policy Simulator cho phép đưa vào **principal hoặc tập policy**, **action**, **resource** và đôi khi **context** để tính kết quả dự kiến. Công cụ có giao diện web và API như **SimulatePrincipalPolicy**, **SimulateCustomPolicy**.

### 5.1. Mô phỏng role có được đọc S3 object?

Giả sử có role **ReportReader** thuộc tài khoản **111122223333** với policy như phần 4.3:

~~~bash
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::111122223333:role/ReportReader \
  --action-names s3:GetObject \
  --resource-arns arn:aws:s3:::learning-reports-demo/reports/november.csv \
  --query 'EvaluationResults[].[EvalActionName,EvalResourceName,EvalDecision,MissingContextValues]' \
  --output json
~~~

Đây là lệnh **mô phỏng**; không đọc object và không sửa quyền thật. ARN, tài khoản và bucket là dữ liệu minh họa; cần thay bằng các giá trị trong lab được ủy quyền. Để chạy thành công, credentials của người thực hiện cũng phải có quyền gọi API mô phỏng tương ứng.

Kết quả **EvalDecision** thường có các giá trị:

| Kết quả | Ý nghĩa | Bước kiểm tra tiếp |
|---|---|---|
| **allowed** | Trong mô hình đã cung cấp, các policy/context được mô phỏng cho phép yêu cầu | Kiểm tra resource policy, dịch vụ đích, phiên thực tế và các giới hạn không được mô phỏng đầy đủ |
| **implicitDeny** | Không tìm được Allow hiệu lực cho yêu cầu trong phạm vi mô phỏng | Kiểm tra action, Resource ARN, principal và context còn thiếu |
| **explicitDeny** | Có Deny tường minh áp dụng trong policy được xét | Xem statement Deny, điều kiện và mục tiêu bảo vệ trước khi thay đổi |

**MissingContextValues** báo các context key cần bổ sung để công cụ đánh giá chính xác những điều kiện trong policy. Một kết quả **implicitDeny** có thể do thiếu context, nhưng cũng có thể do không có Allow phù hợp.

### 5.2. Chạy nhiều action để định vị quyền thiếu

Một ứng dụng dùng SDK có thể làm **ListObjectsV2** trước khi **GetObject**. Các action này yêu cầu tài nguyên khác nhau:

- **s3:GetObject** áp dụng cho ARN **object**, ví dụ **arn:aws:s3:::learning-reports-demo/reports/file.csv**.
- **s3:ListBucket** áp dụng cho ARN **bucket**, ví dụ **arn:aws:s3:::learning-reports-demo**.

Nếu chỉ thử **s3:GetObject**, kết quả **allowed** không giúp giải thích vì sao bước liệt kê bị lỗi. Phải mô phỏng đúng action và ARN ứng với API bị từ chối:

~~~bash
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::111122223333:role/ReportReader \
  --action-names s3:ListBucket \
  --resource-arns arn:aws:s3:::learning-reports-demo
~~~

Sau khi xác định thiếu quyền và xác nhận nghiệp vụ cần liệt kê, có thể thiết kế **s3:ListBucket** với điều kiện **s3:prefix** phù hợp, thay vì cấp **s3:***.

### 5.3. Mô phỏng context: điều kiện có thể làm thay đổi kết quả

Một policy có thể giới hạn yêu cầu theo source IP, principal tag, resource tag, MFA hoặc các context key đặc thù. Nếu người học bỏ qua context, kết quả sẽ không đại diện cho yêu cầu thật.

Ví dụ, một Allow chỉ có hiệu lực khi **aws:PrincipalTag/team** có giá trị **finance**. Mô phỏng mà không truyền tag này có thể đưa ra kết quả thiếu context hoặc khác kết quả mà người dùng mong đợi. Cần lấy các key liên quan từ policy và truyền giá trị chính xác, có thể dùng API **GetContextKeysForPrincipalPolicy** khi phù hợp.

**Không tự giả lập giá trị condition thuận tiện** nếu giá trị đó khác phiên thật. Mục tiêu là tái hiện yêu cầu, không tạo một trường hợp giả định dễ được Allow hơn.

### 5.4. Giới hạn của simulator

- Không mô phỏng đầy đủ mọi **resource-based policy**, **IAM role trust policy**, **SCP/RCP**, kiểm soát mạng hoặc quy tắc riêng của dịch vụ. Khả năng hỗ trợ phụ thuộc loại principal, policy và API.
- Kết quả chỉ đúng theo **policy, resource và context thực sự được đưa vào**. Thay đổi policy sau khi mô phỏng làm kết quả cũ không còn đại diện.
- **Allowed** không chứng minh S3 bucket thực sự tồn tại, object có sẵn, ứng dụng kết nối được, KMS cho phép decrypt hoặc gọi API production sẽ thành công.
- Với truy cập cross-account, phải xét chính sách cả phía caller và phía tài nguyên; một phép mô phỏng identity policy đơn lẻ là chưa đủ.

Hãy dùng simulator để **thu hẹp phạm vi điều tra**, sau đó đối chiếu với policy của tài nguyên và lời gọi thực tế.

## 6. CloudTrail và STS: tìm bằng chứng về lời gọi thực

### 6.1. Xác nhận principal trước tiên

Sai principal là nguyên nhân rất phổ biến. Môi trường local dùng một profile, EC2 dùng instance role, ECS dùng task role, Lambda dùng execution role, còn CI/CD thường dùng phiên STS ngắn hạn.

~~~bash
aws sts get-caller-identity
~~~

Ví dụ kết quả giả định:

~~~json
{
  "UserId": "AROAXAMPLE:report-job-17",
  "Account": "111122223333",
  "Arn": "arn:aws:sts::111122223333:assumed-role/ReportReader/report-job-17"
}
~~~

Đây là **assumed role session ARN**, không phải ARN role gốc **arn:aws:iam::111122223333:role/ReportReader**. Khi điều tra phải lần về role gốc để tìm permissions policy, boundary và trust policy; đồng thời xem các session policy hoặc session tag có thể đi kèm phiên STS.

Nếu người học kiểm tra role **ReportReader** nhưng ứng dụng thực sự dùng role **DeploymentRole**, việc gắn thêm quyền vào ReportReader sẽ không sửa được lỗi.

### 6.2. Đọc một sự kiện AccessDenied

Trong CloudTrail (Event history, trail hoặc CloudTrail Lake tùy phạm vi), tìm sự kiện khớp thời gian và thao tác. Các trường nên kiểm tra:

| Trường thường gặp | Thông tin cần lấy |
|---|---|
| **eventTime**, **eventSource**, **eventName** | Khi nào, dịch vụ nào, API nào đã gọi |
| **awsRegion** | Region/endpoint của yêu cầu, đặc biệt khi điều tra tài nguyên Regional |
| **userIdentity** | IAM user, assumed role session hoặc principal dịch vụ |
| **recipientAccountId** | Tài khoản nhận yêu cầu khi có thông tin này |
| **requestParameters**, **resources** | Bucket/key, ARN role, KMS key, hoặc resource liên quan khi được ghi |
| **errorCode**, **errorMessage** | Mã lỗi và mô tả từ chối, nếu sự kiện cung cấp |
| **sourceIPAddress**, **userAgent**, **additionalEventData** | Nguồn kết nối và ngữ cảnh bổ sung khi có |

Thông báo từ một số dịch vụ và tình huống same-account có thể nêu loại policy gây **explicit deny** hoặc cho biết **không có identity-based policy Allow**. Tuy nhiên, **không phải mọi lỗi AccessDenied đều có thông báo chi tiết**; đặc biệt với các luồng cross-account, service-specific hoặc chính sách tổ chức, nội dung có thể thiếu hoặc bị giới hạn.

**Chú ý đến loại sự kiện:** CloudTrail Event history mặc định chủ yếu cung cấp **management events**. Những hoạt động trên object S3 như **GetObject** là **data events**, thường không sẵn trong Event history nếu chưa cấu hình thu thập phù hợp qua trail hoặc CloudTrail Lake. Không thấy GetObject trong Event history không chứng minh GetObject chưa từng được gọi.

### 6.3. Thu thập bằng chứng theo từng lớp

Khi có **AccessDenied**, kết hợp các bằng chứng:

1. Lệnh/lỗi thật với thời điểm, action, account, Region và ARN.
2. Danh tính thực qua **get-caller-identity**, cùng session name/tag khi liên quan.
3. IAM policy gắn vào user/role và các **permissions boundary/session policy**.
4. Resource policy, role trust policy hoặc KMS key policy trên tài nguyên đích.
5. SCP/RCP, endpoint policy và các kiểm soát đặc thù nếu có.
6. Kết quả policy simulation cùng **context** đã dùng.
7. CloudTrail event hoặc log ứng dụng tương ứng để xác nhận yêu cầu thực tế.

Ưu tiên bằng chứng cụ thể để tìm **mắt xích từ chối**, không thêm quyền vô hạn vào role theo cảm tính.

## 7. Quy trình xử lý AccessDenied từ đầu đến cuối

~~~mermaid
flowchart TD
    A["Ghi nhận AccessDenied\\nAPI, thời gian, ARN, Region"] --> B["Xác định principal thật\\nSTS GetCallerIdentity"]
    B --> C["Xác định action và resource ARN\\nĐúng loại bucket/object/key/role?"]
    C --> D{"Truy cập cùng account\\nhay cross-account?"}
    D -->|"Cùng account"| E["Kiểm tra IAM + resource policy\\nvà mọi explicit deny"]
    D -->|"Cross-account"| F["Kiểm tra hai phía\\ncaller và resource owner"]
    E --> G["Kiểm tra boundary/session\\nSCP, RCP và condition"]
    F --> G
    G --> H["ValidatePolicy + Policy Simulator\\ntrong phạm vi hỗ trợ"]
    H --> I["Đối chiếu CloudTrail\\nvà quy tắc riêng dịch vụ"]
    I --> J["Sửa quyền tối thiểu\\nchỉ sau khi xác nhận nguyên nhân"]
    J --> K["Kiểm thử hành động cần Allow\\nvà hành động cần Deny"]
~~~

### Bước 1 — Sao chép lỗi đủ ngữ cảnh

Thu thập **tên API**, **thời điểm**, **principal**, **ARN**, **account**, **Region**, **nguồn gọi** và **mã lỗi**. Ví dụ: ứng dụng chạy bằng role **ReportReader** gọi **s3:GetObject** trên **arn:aws:s3:::learning-reports-demo/reports/november.csv** tại thời điểm xác định. Tránh chỉ ghi “S3 không cho truy cập”.

### Bước 2 — Xác minh credential và phiên hiện tại

Chạy **sts get-caller-identity** bằng đúng profile hoặc môi trường đang báo lỗi. Nếu ứng dụng chạy trên Lambda/ECS/EC2, xem cấu hình role của workload thực. Với **AssumeRole**, phân biệt **caller role**, **target role**, **role session** và session policy.

### Bước 3 — Đối chiếu action với ARN

Nhiều lỗi đến từ việc cấp đúng action nhưng sai dạng Resource:

- **s3:ListBucket** cần ARN bucket; **s3:GetObject** cần ARN object.
- **sts:AssumeRole** cần đối chiếu ARN của role đích và trust policy.
- **kms:Decrypt** cần quyền đối với key thích hợp; đối chiếu cả KMS key policy.
- Một số action chỉ hỗ trợ **Resource: \\*** trong identity-based policy. Kiểm tra bảng service authorization reference trước khi áp dụng.

### Bước 4 — Tìm Deny và Allow còn thiếu

Lấy danh sách identity-based policy, resource policy, boundary/session policy và các giới hạn tổ chức đang áp dụng. Với **implicit deny**, xác định chính xác chỗ thiếu Allow trong ngữ cảnh tương ứng. Với **explicit deny**, đọc **Condition** và lý do bảo vệ trước khi thay đổi; đôi khi Deny được thiết lập cố ý vì yêu cầu an toàn.

### Bước 5 — Kiểm tra đường đi cross-account

Nếu resource thuộc account khác, xác định cơ chế:

- **Truy cập trực tiếp qua resource-based policy:** bên caller cần quyền phù hợp và bên resource phải chấp nhận principal (theo cơ chế của dịch vụ).
- **AssumeRole vào account đích:** caller phải được phép assume, trust policy role đích phải tin cậy caller, rồi permissions của **role đích** phải cho phép action cuối cùng.

Không sửa nhầm policy tại account A trong khi Deny thực sự nằm tại bucket policy hoặc key policy của account B.

### Bước 6 — Dùng công cụ để kiểm tra giả thuyết

Chạy **ValidatePolicy** với policy được xem xét; **Policy Simulator** với đúng action, ARN, principal và context. Nếu simulator trả **allowed** nhưng API thật vẫn AccessDenied, tập trung kiểm tra những yếu tố chưa được mô phỏng đầy đủ: resource policy, KMS, endpoint policy, SCP/RCP, trạng thái phiên, Request condition hoặc sự khác biệt của principal thật.

### Bước 7 — Áp dụng bản sửa tối thiểu và kiểm tra lại

Chỉ sửa statement gây lỗi và giới hạn quyền theo **least privilege**. Thử cả trường hợp **cần cho phép** lẫn **cần từ chối**; xác minh trong CloudTrail hoặc log thích hợp. Ghi nguyên nhân gốc, policy thay đổi, chủ sở hữu và kết quả sau sửa.

## 8. Tình huống thực tế A: Lambda đọc S3 nhưng thiếu quyền ListBucket

**Bối cảnh:** Lambda sử dụng execution role **DailyReportJob**. Policy role chỉ có:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::learning-reports-demo/reports/*"
    }
  ]
}
~~~

Ứng dụng gọi **ListObjectsV2** để tìm báo cáo mới, rồi mới gọi **GetObject**. Lỗi xuất hiện tại thao tác đầu tiên.

**Phân tích:** **ListObjectsV2** kiểm tra quyền IAM **s3:ListBucket**, không phải **s3:GetObject**. Simulator có thể trả **allowed** với GetObject nhưng **implicitDeny** với ListBucket trên ARN bucket.

Nếu nghiệp vụ thực sự cần liệt kê prefix báo cáo, thêm statement sau vào **identity-based policy** gắn với role:

~~~json
{
  "Sid": "ListOnlyReportsPrefix",
  "Effect": "Allow",
  "Action": "s3:ListBucket",
  "Resource": "arn:aws:s3:::learning-reports-demo",
  "Condition": {
    "StringLike": {
      "s3:prefix": [
        "reports/",
        "reports/*"
      ]
    }
  }
}
~~~

Statement minh họa cách giới hạn danh sách theo prefix. Code ứng dụng cần truyền prefix khớp điều kiện; đồng thời kiểm tra các giới hạn khác nếu có. **Không cấp s3:*** chỉ để xử lý việc liệt kê.

## 9. Tình huống thực tế B: truy cập S3 cross-account và KMS

Giả sử:

- **Account A — 111122223333:** role **AnalyticsReader** chạy ứng dụng đọc dữ liệu.
- **Account B — 222233334444:** S3 bucket **shared-data-demo-222233334444** chứa object mã hóa bằng SSE-KMS với customer managed key.

Với **truy cập S3 trực tiếp bằng role Account A**, thường cần:

1. Identity-based policy của **AnalyticsReader** tại A cho phép **s3:GetObject** trên object ARN trong B.
2. Bucket policy của B cho phép role cụ thể trong A đọc những object tương ứng.
3. Nếu dùng customer managed KMS key, quyền **kms:Decrypt** thích hợp tại caller cùng với **KMS key policy** ở tài khoản sở hữu key.
4. Không có Deny hoặc kiểm soát bổ sung chặn đường truy cập (SCP/RCP, endpoint policy, condition, v.v.).

**Cách chẩn đoán theo từng bước:**

| Kiểm tra | Dấu hiệu | Hướng xử lý |
|---|---|---|
| Identity policy của role A | Không có Allow s3:GetObject | Thêm action và object ARN tối thiểu |
| Bucket policy ở B | Không chấp nhận role A | Sửa Principal/Resource và điều kiện theo đường chia sẻ được phê duyệt |
| KMS key policy | S3 cho đọc nhưng decrypt bị từ chối | Xác minh KMS key ARN, key policy, quyền kms:Decrypt và context |
| SCP/RCP/boundary/endpoint | Simulator đơn lẻ Allow nhưng API thật Deny | Kiểm tra các chính sách giới hạn và request context |

Nếu chọn **AssumeRole vào Account B** thay cho truy cập trực tiếp, phân tích lại theo phiên role đích; tránh trộn hai mô hình. Điều chỉnh bucket policy hoặc key policy chỉ khi có căn cứ và quyền quản trị phù hợp.

## 10. Tình huống thực tế C: lỗi sts:AssumeRole

Giả sử pipeline tại Account A muốn assume role **DeploymentRole** của Account B. Có hai phía cần xem:

- **Caller permissions:** identity-based policy của principal nguồn thường phải cho phép **sts:AssumeRole** trên ARN role đích.
- **Target trust policy:** trust policy của **DeploymentRole** ở B phải cho phép principal nguồn assume, đồng thời các điều kiện như **sts:ExternalId**, MFA, principal tag hoặc nguồn truy cập phải được đáp ứng nếu được cấu hình.

Ví dụ trust policy minh họa dành cho một role được biết trước:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TrustDeploymentCaller",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111122223333:role/CICDCaller"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

Nếu caller thật là role khác, hoặc caller bị SCP chặn, cấu hình trên không đủ. Sau khi **AssumeRole thành công**, permissions policy của **DeploymentRole** quyết định pipeline được thao tác trên dịch vụ nào; trust policy không tự cấp **cloudformation:CreateStack**, **s3:PutObject** hoặc những quyền triển khai khác.

### Ví dụ đọc sai kết quả mô phỏng

Kỹ sư mô phỏng **s3:GetObject** trên **role nguồn** và thấy allowed, rồi kết luận deployment sau AssumeRole phải đọc được object. Kết luận này sai vì ứng dụng sau AssumeRole dùng **role session của DeploymentRole**, không còn quyền hiệu lực giống role nguồn. Phải kiểm tra đúng principal **tại thời điểm API xảy ra**.

## 11. Những nguyên nhân AccessDenied thường gặp

| Lỗi/dấu hiệu | Nguyên nhân khả dĩ | Công cụ hoặc bằng chứng ưu tiên |
|---|---|---|
| Lời gọi từ CLI thành công, từ Lambda thất bại | CLI và Lambda dùng principal khác nhau | **STS get-caller-identity**, cấu hình execution role, CloudTrail |
| **implicitDeny** với GetObject | Sai action, ARN object hoặc không có Allow | Policy Simulator, identity policy |
| **explicitDeny** dù có Allow | Deny trong bucket, IAM, boundary hoặc cấp tổ chức | Chi tiết lỗi, policy áp dụng, condition |
| GetObject được, ListObjectsV2 bị từ chối | Thiếu **s3:ListBucket** trên ARN bucket | Action thực, simulator, Service Authorization Reference |
| Read S3 cross-account không thành công | Thiếu quyền một phía hoặc điều kiện không khớp | IAM role policy ở A, bucket policy ở B |
| Đọc object SSE-KMS bị AccessDenied | Thiếu quyền KMS hoặc key policy chưa cấp quyền | KMS key policy, IAM policy, key ARN |
| AssumeRole bị từ chối | Trust policy, caller permission hoặc condition chưa đúng | CloudTrail STS, role trust policy, SCP |
| Simulator cho **allowed** nhưng API thật Deny | Bỏ sót resource policy, session/context, SCP/RCP hoặc quy tắc dịch vụ | CloudTrail, request context, kiểm tra end-to-end |
| Access Analyzer không có finding dù dữ liệu bị đọc ngoài ý muốn | Analyzer không phủ toàn bộ đường truy cập, loại tài nguyên hoặc lịch sử | Kiểm tra phạm vi analyzer; CloudTrail/data events, log thực tế |
| Lỗi xuất hiện sau đổi tag hoặc nguồn mạng | Condition key không còn khớp | Session/principal/resource tags, SourceIp, VPC endpoint, log |
| S3 bucket cho phép nhưng anonymous/public access vẫn bị chặn | S3 Block Public Access và cấu hình dịch vụ | S3 Block Public Access, bucket policy và ownership |
| Thông báo không nêu policy gây Deny | Dịch vụ/tình huống không trả chi tiết | Tập hợp tất cả lớp policy, dùng simulator và lời gọi thử |

## 12. Các thực hành cần tránh

**Không thêm quyền rộng như Action: "*" hoặc Resource: "*" chỉ để hết lỗi.** Có thể khiến thao tác thử thành công nhưng mở đường cho truy cập trái phép.

**Không gỡ bỏ explicit deny khi chưa hiểu mục đích.** Deny có thể bảo vệ dữ liệu nhạy cảm, bắt buộc TLS, giới hạn Region hoặc chặn hành động nguy hiểm.

**Không coi “policy hợp lệ” là “quyền đủ”.** IAM Access Analyzer policy validation không biết toàn bộ yêu cầu của ứng dụng.

**Không coi “simulator: allowed” là bằng chứng cuối.** Policy Simulator không nắm chắc tài nguyên, phiên và mọi chính sách của dịch vụ tại thời điểm gọi thật.

**Không kết luận “CloudTrail không có log” nghĩa là chưa có truy cập.** Kiểm tra đã bật loại event cần thiết, Region, account, thời gian giữ log và cơ chế ghi dữ liệu.

**Không sửa policy của danh tính không thực sự gọi API.** Xác định principal và credentials trước khi thay đổi bất kỳ quyền nào.

**Không đổi chính sách production chỉ dựa trên một mô phỏng.** Thử trong môi trường phù hợp, ghi nhận tác động và quy trình phê duyệt.

## 13. Bài thực hành: phân tích lỗi và đề xuất bản sửa tối thiểu

**Đề bài:** một job báo cáo chạy bằng role **ReportReader** tại Account A cần:

- Liệt kê các object trong prefix **reports/** của bucket **learning-reports-demo**.
- Đọc CSV trong prefix đó.
- Không ghi, sửa, xóa hoặc đọc các prefix khác.

Policy đang dùng chỉ chứa **s3:GetObject** trên các object có tiền tố **reports/** trong bucket. Sau khi chạy job, người học gặp lỗi **AccessDenied** ở thao tác liệt kê.

### Nhiệm vụ

1. Xác định action thật của API **ListObjectsV2** và resource ARN cần sử dụng.
2. Dùng simulator để dự đoán GetObject được phép và ListBucket bị implicit deny, nếu không có policy khác tác động.
3. Viết thêm statement **s3:ListBucket** với điều kiện prefix phù hợp.
4. Dùng **ValidatePolicy** để kiểm tra JSON hoàn chỉnh, rồi thử một yêu cầu ListObjectsV2 với prefix **reports/**.
5. Kiểm thử trường hợp **s3:DeleteObject** hoặc truy cập prefix khác vẫn bị từ chối.
6. Ghi rõ những giả định chưa được simulator bao phủ, ví dụ bucket policy, SCP và các hạn chế khác.

**Kết quả mong đợi:** phân biệt được **thiếu Allow ở action cụ thể** với **explicit deny**, biết cách cấp quyền liệt kê giới hạn mà không mở rộng quyền đọc/ghi, và mô tả được cách xác thực bằng lời gọi thật.

### Câu hỏi mở rộng

Giả sử có thêm bucket policy **Deny** tất cả kết nối không dùng TLS (**aws:SecureTransport = false**). Vì sao sau khi thêm ListBucket, một request qua HTTP vẫn không thành công?

**Gợi ý:** explicit deny phù hợp sẽ thắng Allow; người học phải sửa cách kết nối và xác minh request context, không xóa Deny vốn nhằm bảo vệ dữ liệu.

## 14. Checklist xử lý lỗi trước khi đóng sự cố

- [ ] Đã ghi lại **thời điểm**, **API/action**, **Region**, **resource ARN** và thông báo lỗi.
- [ ] Đã xác nhận principal thật, kể cả **assumed role session**.
- [ ] Đã xác định same-account hay cross-account, truy cập trực tiếp hay AssumeRole.
- [ ] Đã rà soát Allow/Deny trong identity policy, resource policy và trust policy nếu liên quan.
- [ ] Đã kiểm tra permissions boundary, session policy, SCP/RCP và những condition quan trọng.
- [ ] Đã xét KMS, S3 Block Public Access, endpoint policy và yêu cầu riêng của dịch vụ.
- [ ] Đã validate JSON và mô phỏng đúng action, ARN, principal/context trong phạm vi được hỗ trợ.
- [ ] Đã đối chiếu với CloudTrail hoặc log thực tế, xác nhận loại event được thu thập.
- [ ] Đã sửa đúng nguyên nhân theo **least privilege**, không thêm quyền quá rộng.
- [ ] Đã thử lại thao tác cần cho phép, thao tác cần từ chối và ghi lại kết quả.

## 15. Ghi nhớ

**IAM Access Analyzer** giúp phát hiện quyền truy cập ngoài phạm vi tin cậy, quyền có thể dư thừa và vấn đề policy trước khi triển khai. **Policy Simulator** giúp trả lời câu hỏi “với action, resource và context này, policy dự kiến quyết định thế nào?”. **CloudTrail** cung cấp bằng chứng về những lời gọi API thực sự được ghi. Khi xử lý **AccessDenied**, thứ tự quan trọng nhất là **xác định đúng principal → xác định đúng action/resource → kiểm tra Allow/Deny và các giới hạn → mô phỏng/đối chiếu log → sửa tối thiểu và thử lại**.

### Tài liệu AWS chính thức để đối chiếu khi triển khai

- [AWS IAM Access Analyzer — User Guide](https://docs.aws.amazon.com/IAM/latest/UserGuide/what-is-access-analyzer.html) — phạm vi analyzer và chức năng chính.
- [Validate your IAM policies](https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-policy-validation.html) — các dạng finding khi kiểm tra policy.
- [IAM Policy Simulator](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_testing-policies.html) — cách mô phỏng và các giới hạn.
- [Policy evaluation logic](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html) — nguyên tắc Allow, Deny và các lớp giới hạn.
- [Troubleshoot access denied error messages](https://docs.aws.amazon.com/IAM/latest/UserGuide/troubleshoot_access-denied.html) — giải thích lỗi truy cập bị từ chối.
- [Cross-account policy evaluation](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic-cross-account.html) — đánh giá quyền qua hai tài khoản.
- [CloudTrail concepts](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-concepts.html) — management/data events và sự kiện API.
- [Actions, resources, and condition keys for AWS services](https://docs.aws.amazon.com/service-authorization/latest/reference/reference_policies_actions-resources-contextkeys.html) — tra cứu action và Resource ARN phù hợp.
