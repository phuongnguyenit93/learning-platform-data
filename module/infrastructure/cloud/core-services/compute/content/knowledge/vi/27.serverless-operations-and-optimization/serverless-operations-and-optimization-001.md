# Cấp danh tính và quyền tối thiểu cho từng hàm

Một hàm serverless thường được kích hoạt bởi API Gateway, hàng đợi, object storage, lịch chạy hoặc một dịch vụ cloud khác. Trong quá trình xử lý, hàm có thể cần đọc dữ liệu, ghi kết quả, gửi message, lấy secret hoặc gọi một dịch vụ nội bộ. Nếu hàm dùng một danh tính có quyền quá rộng, lỗi trong code hoặc việc khai thác lỗ hổng có thể mở rộng thành truy cập trái phép tới nhiều tài nguyên trong tài khoản cloud.

Nguyên tắc quyền tối thiểu (least privilege) yêu cầu mỗi hàm chỉ có đúng những quyền cần thiết để hoàn thành nhiệm vụ, trên đúng tài nguyên, trong đúng thời gian và đúng ngữ cảnh. Danh tính thực thi của hàm cần được tách biệt với danh tính người gọi hàm, danh tính dịch vụ kích hoạt hàm và danh tính của pipeline triển khai. Các danh tính này đại diện cho những chủ thể khác nhau và có quyền hạn khác nhau.

Bài học này trình bày cách cấp danh tính cho từng hàm, thiết kế trust policy và permission policy, bảo vệ secret, giới hạn quyền gọi hàm, xử lý sự kiện giữa các dịch vụ và kiểm toán hoạt động. Sau bài học, bạn có thể:

- Phân biệt danh tính người gọi, danh tính dịch vụ kích hoạt, danh tính thực thi và danh tính triển khai.
- Cấp execution role, managed identity hoặc service account riêng theo trách nhiệm của hàm.
- Viết quyền theo nguyên tắc deny by default, giới hạn action, resource và condition.
- Phân biệt quyền được gọi hàm với quyền mà hàm dùng để truy cập dịch vụ khác.
- Dùng workload identity và credential ngắn hạn thay cho khóa truy cập nhúng trong code.
- Lưu trữ và truy xuất secret an toàn, có rotation và audit.
- Kiểm tra quyền thực tế, phát hiện quyền thừa và xử lý sự cố truy cập.

## 1. Các danh tính khác nhau trong một luồng serverless

Trong một luồng serverless, nhiều principal có thể tham gia. Nếu gom tất cả vào một role hoặc một tài khoản dùng chung, rất khó xác định ai được phép làm gì và khó giới hạn phạm vi khi một thành phần bị xâm phạm.

Ví dụ, một API nhận yêu cầu tạo báo cáo, kích hoạt hàm xử lý, hàm đọc dữ liệu từ bucket, ghi báo cáo sang bucket khác và gửi thông báo vào queue. Luồng này có thể có các danh tính:

1. **Caller identity:** người dùng hoặc ứng dụng gọi API. Danh tính này được xác thực bằng cơ chế phù hợp như OAuth/OIDC, JWT, mTLS hoặc IAM authentication.
2. **Trigger/service identity:** dịch vụ cloud gửi sự kiện hoặc có quyền kích hoạt hàm. Ví dụ, một bucket gửi notification hoặc một scheduler gọi hàm theo lịch.
3. **Function execution identity:** danh tính mà code của hàm sử dụng khi gọi object storage, queue, database, secret manager hoặc logging service.
4. **Deployment identity:** pipeline CI/CD hoặc người vận hành có quyền tạo/cập nhật function, cấu hình role, environment và trigger.
5. **Downstream service identity:** danh tính của dịch vụ đích khi hàm gọi tới nó; có thể là service account, database user hoặc workload identity riêng.

~~~mermaid
flowchart TD
    U["Người dùng / ứng dụng"] -->|Danh tính caller| G["API Gateway"]
    G -->|Quyền invoke| F["Serverless function"]
    T["Event source / scheduler"] -->|Quyền trigger| F
    F -->|Execution identity| S["Object storage / database / queue"]
    F -->|Workload identity| D["Dịch vụ nội bộ"]
    C["CI/CD deployment identity"] -->|Deploy và cấu hình IAM| F
~~~

Điểm quan trọng là danh tính người gọi API không tự động trở thành danh tính thực thi của hàm. Hàm thường chạy bằng execution role hoặc service identity được gắn với runtime. Nếu cần biết người dùng cuối nào đã yêu cầu thao tác, ứng dụng phải truyền context đã xác thực theo cách an toàn và kiểm tra authorization trong logic nghiệp vụ.

### Bốn câu hỏi cần trả lời

- Ai được phép gọi hàm?
- Hàm được phép truy cập tài nguyên nào khi đang chạy?
- Ai được phép thay đổi code, cấu hình, trigger và quyền của hàm?
- Hàm có thể đại diện cho người dùng hoặc workload khác khi gọi dịch vụ tiếp theo không?

Mỗi câu hỏi tương ứng với một ranh giới quyền riêng. Không nên giải quyết tất cả bằng cách gắn một role quản trị vào function.

## 2. Execution identity là gì?

Execution identity là danh tính mà nền tảng cấp cho tiến trình serverless khi hàm thực thi. Tùy cloud, cơ chế có thể mang tên:

- Execution role hoặc IAM role trong một số dịch vụ function.
- Managed identity trong nền tảng cloud hỗ trợ identity do nền tảng quản lý.
- Service account gắn với function hoặc runtime.
- Workload identity được liên kết với service account hoặc identity provider.

Nền tảng thường cung cấp credential tạm thời cho runtime. Code dùng credential đó để ký request tới dịch vụ cloud mà không cần lưu access key dài hạn trong source code.

### So sánh các mô hình phổ biến

| Mô hình | Cách hoạt động | Điểm cần quản lý |
|---|---|---|
| IAM execution role | Function assume role qua trust relationship; runtime nhận credential phiên tạm thời | Trust policy, permission policy, session duration và resource scope |
| Managed identity | Nền tảng cấp danh tính cho tài nguyên compute | Phân quyền identity tới tài nguyên đích và giới hạn nơi identity được gắn |
| Service account | Function chạy dưới service account được chỉ định | IAM binding, quyền impersonation và phạm vi account |
| Workload identity federation | Identity của workload được liên kết với một identity provider | Issuer, subject, audience, trust condition và quyền token exchange |

Tên gọi và cách cấu hình khác nhau giữa nhà cung cấp. Nguyên tắc chung là để nền tảng cấp credential ngắn hạn cho workload, sau đó cấp quyền tối thiểu cho danh tính đó.

### Không dùng tài khoản người dùng làm execution identity

Không nên cấu hình function dùng credential cá nhân của developer hoặc tài khoản quản trị viên. Khi nhân sự rời nhóm, mật khẩu đổi hoặc quyền người dùng thay đổi, function có thể ngừng hoạt động hoặc tiếp tục giữ quyền quá rộng. Execution identity nên thuộc workload, có chủ sở hữu và vòng đời được quản lý cùng ứng dụng.

## 3. Mỗi hàm cần danh tính riêng theo trách nhiệm

Nếu nhiều function dùng chung một role, quyền của role thường phải là hợp của mọi quyền mà tất cả function cần. Một hàm đọc ảnh có thể vô tình được quyền xóa object; một hàm gửi email có thể được quyền đọc dữ liệu khách hàng; một hàm xử lý webhook có thể truy cập secret của hệ thống thanh toán.

Tách execution identity theo chức năng giúp giới hạn phạm vi tác động:

| Hàm | Nhiệm vụ | Quyền tối thiểu minh họa |
|---|---|---|
| image-resizer | Đọc ảnh đầu vào, ghi thumbnail | Read object ở prefix input; write object ở prefix thumbnails |
| invoice-generator | Đọc dữ liệu hóa đơn, ghi PDF | Read các bản ghi cần thiết; write vào bucket invoice-output |
| email-dispatcher | Gửi thông báo | Consume message từ queue; gọi dịch vụ gửi email |
| token-validator | Kiểm tra token | Đọc public key/JWKS hoặc secret xác minh phù hợp; không có quyền ghi dữ liệu nghiệp vụ |
| cleanup-job | Xóa dữ liệu hết hạn | List và delete trong prefix được quản lý; không có quyền xóa bucket |

Một role riêng cho mỗi function là điểm bắt đầu an toàn, đặc biệt khi các hàm có mức tin cậy hoặc dữ liệu khác nhau. Có thể chia sẻ role giữa các function chỉ khi chúng có cùng trách nhiệm, cùng ranh giới dữ liệu, cùng chủ sở hữu và cùng yêu cầu bảo mật. Không nên chia sẻ chỉ vì tiện cấu hình.

### Tách theo môi trường và tenant

Dev, staging và production nên có identity hoặc role riêng. Một function ở môi trường thử nghiệm không nên dùng được quyền ghi vào bucket production. Với hệ thống multi-tenant, nếu các tenant có ranh giới dữ liệu hoặc yêu cầu tuân thủ riêng, cần xác định cách cô lập bằng account/project/subscription, resource policy, condition hoặc lớp authorization ứng dụng.

Không nên coi tên function hoặc biến môi trường tenant là bằng chứng authorization. Client có thể thay đổi input; quyền phải được kiểm tra bằng identity và policy đáng tin cậy ở phía server.

## 4. Phân biệt trust policy và permission policy

Với mô hình role có thể được assume, thường có hai nhóm chính sách:

- **Trust policy:** xác định principal nào được phép assume role hoặc nhận credential của role.
- **Permission policy:** xác định principal sau khi có role được phép thực hiện action nào trên resource nào.

Trust policy trả lời "ai được mang danh tính này?". Permission policy trả lời "danh tính này được làm gì?".

Một role có permission rất hẹp nhưng trust policy cho phép mọi workload trong account assume vẫn có thể bị lạm dụng. Ngược lại, trust policy giới hạn đúng function nhưng permission policy cấp quyền administrator vẫn quá rộng.

### Trust policy cần giới hạn

- Đúng dịch vụ runtime hoặc workload identity provider.
- Đúng account, project, subscription hoặc organization.
- Đúng function, service account, namespace hoặc workload subject khi nền tảng hỗ trợ.
- Đúng audience, issuer và subject khi dùng federation.
- Điều kiện chống confused deputy nếu dịch vụ có hỗ trợ external ID hoặc source ARN/account condition.

Không nên dùng wildcard principal rộng nếu không có lý do và biện pháp ràng buộc bổ sung. Với trust federation, kiểm tra chính xác issuer, subject và audience; một pattern quá rộng có thể cho phép workload không liên quan nhận role.

### Permission policy cần giới hạn

- **Action:** chỉ các thao tác cần thiết, ví dụ đọc object thay vì toàn bộ quyền storage.
- **Resource:** ARN, resource ID, bucket/prefix, queue hoặc secret cụ thể.
- **Condition:** giới hạn theo tag, encryption, network, source account, thời gian hoặc context khi nền tảng hỗ trợ.
- **Effect:** mặc định từ chối; chỉ cho phép các trường hợp đã xác định.

Một permission policy tốt cần nói rõ hàm được đọc, ghi, gửi, nhận hoặc gọi gì. Tránh cấp wildcard cho action và resource chỉ để làm cho lỗi AccessDenied biến mất.

## 5. Quyền gọi function khác với quyền function truy cập tài nguyên

Đây là điểm dễ nhầm trong serverless.

### Quyền invoke

Quyền invoke quyết định principal nào được gọi function. Principal có thể là:

- API Gateway hoặc HTTP gateway.
- Event source như object storage, scheduler hoặc notification service.
- Một function khác.
- Người dùng hoặc ứng dụng gọi trực tiếp.

Một số nền tảng dùng resource-based policy gắn trên function để cho phép dịch vụ khác gọi. Một số nền tảng dùng cấu hình trigger, event subscription hoặc binding. Cần xác định cơ chế cụ thể của dịch vụ.

### Quyền execution

Quyền execution quyết định function được làm gì sau khi chạy. Ví dụ, function có thể đọc object từ bucket A và ghi kết quả vào bucket B. Việc API Gateway được phép invoke function không tự cấp quyền cho function đọc bucket A.

Ngược lại, function có quyền đọc bucket không có nghĩa bất kỳ principal nào cũng được gọi function. Hai quyền phải được cấu hình riêng.

### Event push và event pull

Với push-based event, dịch vụ nguồn gọi endpoint hoặc function. Function thường cần quyền cho phép đúng dịch vụ nguồn invoke. Với pull-based event, một event source mapping hoặc poller có thể đọc message từ queue rồi gọi function; quyền đọc queue có thể thuộc execution role hoặc identity của poller tùy nền tảng. Hãy kiểm tra kiến trúc thực tế, không áp dụng một mẫu quyền cho mọi trigger.

## 6. Thiết kế policy theo action, resource và condition

Một cách tiếp cận thực tế là lập bảng quyền trước khi viết policy:

| Hoạt động trong code | Action cần có | Resource | Quyền không cần cấp |
|---|---|---|---|
| Đọc ảnh gốc | Get/read object | Bucket input, prefix uploads/ | Delete bucket, list mọi bucket |
| Ghi thumbnail | Put/write object | Bucket output, prefix thumbnails/ | Read mọi object, delete object nếu không cần |
| Nhận job | Receive/consume message | Queue image-jobs | Purge queue, delete queue |
| Lấy API token | Read secret value | Secret cụ thể | List và sửa mọi secret |
| Ghi log | Create stream/append events | Log group của function | Xóa log group hoặc thay đổi retention |

### Ví dụ permission policy tối thiểu

Ví dụ JSON dưới đây minh họa một function chỉ đọc object trong prefix đầu vào và ghi object trong prefix thumbnail. Tên action và resource ARN là ví dụ theo phong cách IAM; cần thay bằng cú pháp và quyền chính xác của cloud provider đang dùng.

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadUploadedImages",
      "Effect": "Allow",
      "Action": ["s3:GetObject"],
      "Resource": "arn:aws:s3:::media-input/uploads/*"
    },
    {
      "Sid": "WriteThumbnails",
      "Effect": "Allow",
      "Action": ["s3:PutObject"],
      "Resource": "arn:aws:s3:::media-output/thumbnails/*"
    }
  ]
}
~~~

Policy không cấp quyền list bucket, xóa object hoặc truy cập bucket khác. Nếu code cần đọc metadata bằng HeadObject hoặc list một prefix, phải xác định action bổ sung và giới hạn resource/condition tương ứng. Không thêm quyền chỉ vì một ví dụ trên Internet có nhiều action hơn.

### Cẩn thận với wildcard

Wildcard trong resource có thể hữu ích để giới hạn theo prefix, nhưng cần xem cách provider đánh giá ARN và condition. Wildcard ở action như storage:* hoặc iam:* thường mở rộng quyền rất lớn. Hãy ưu tiên liệt kê action cụ thể và kiểm tra policy bằng công cụ phân tích quyền của nhà cung cấp.

### Permission boundary và organization policy

Ở môi trường lớn, có thể dùng permission boundary, service control policy, organization policy hoặc guardrail tương đương để giới hạn mức quyền tối đa mà role/function có thể nhận. Các lớp này không thay thế permission policy của workload; chúng đặt trần hoặc ràng buộc bổ sung.

Khi điều tra AccessDenied, cần kiểm tra cả policy gắn trực tiếp, resource policy, boundary, organization policy, session policy và condition. Một Allow ở một nơi không bảo đảm request được phép nếu có explicit Deny hoặc condition không thỏa.

## 7. Ví dụ end-to-end: function xử lý ảnh

Giả sử hệ thống có bucket input nhận ảnh, function resize ảnh, bucket output chứa thumbnail và queue ghi nhận lỗi xử lý.

Danh tính được tách như sau:

| Principal | Quyền |
|---|---|
| Object storage event service | Chỉ được invoke function từ bucket input được chỉ định |
| Execution role của image-resizer | Đọc object trong prefix uploads; ghi object trong prefix thumbnails; ghi log |
| Deployment pipeline | Cập nhật code và cấu hình function; gắn role đã được phê duyệt |
| Người dùng upload | Chỉ được upload theo cơ chế được cấp, không assume execution role |

Luồng xử lý:

1. Người dùng tải ảnh lên bucket qua API hoặc URL ký sẵn.
2. Object storage phát sự kiện cho function.
3. Trigger policy xác minh đúng nguồn được phép invoke.
4. Function nhận execution identity của riêng nó.
5. Function đọc object đầu vào, tạo thumbnail và ghi object đầu ra.
6. Nếu lỗi, function ghi log và có thể gửi message tới queue lỗi theo quyền đã cấp.

Function không cần quyền xóa bucket, quản lý IAM, tạo user, đọc secret không liên quan hoặc truy cập dữ liệu của tenant khác. Nếu hàm cần gọi một dịch vụ khác, hãy thêm đúng quyền cho resource đó sau khi xác định yêu cầu.

## 8. Cấp danh tính cho AWS Lambda, Azure Functions và Google Cloud

Tên gọi và giao diện khác nhau, nhưng mô hình tương đồng: gắn danh tính workload vào function rồi cấp quyền cho danh tính đó trên tài nguyên đích.

### AWS Lambda

- Gắn execution role cho Lambda function.
- Trust policy cho phép dịch vụ Lambda assume role theo đúng phạm vi cần thiết.
- Permission policies trên role xác định function có thể gọi dịch vụ nào.
- Resource-based policy của function có thể cho phép API Gateway, S3 hoặc principal cụ thể invoke function.
- Dùng STS credential tạm thời do runtime cung cấp; không nhúng access key dài hạn vào biến môi trường.

Ví dụ trust policy tối giản theo mô hình AWS:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

Trong production, trust relationship có thể cần condition bổ sung để giới hạn account hoặc nguồn theo hướng dẫn của AWS và mô hình triển khai. Execution role cũng cần quyền ghi log và quyền nghiệp vụ tối thiểu.

### Azure Functions

- Dùng system-assigned hoặc user-assigned managed identity nếu hosting plan và runtime hỗ trợ.
- Gán role phù hợp trên storage, Key Vault, Service Bus hoặc dịch vụ đích.
- Ưu tiên managed identity để lấy token từ nền tảng thay vì lưu client secret.
- Với trigger/binding, xác định identity nào được dùng để truy cập nguồn sự kiện; hành vi phụ thuộc extension, cấu hình và phiên bản runtime.

System-assigned identity có vòng đời gắn với function app; user-assigned identity có thể được gắn vào nhiều tài nguyên nếu có lý do vận hành rõ ràng. Dùng chung identity làm tăng phạm vi ảnh hưởng, vì vậy cần kiểm tra kỹ trước khi chia sẻ.

### Google Cloud Functions và Cloud Run functions

- Chọn service account runtime riêng cho function hoặc nhóm workload có cùng trách nhiệm.
- Cấp IAM role ở mức resource cần thiết, chẳng hạn object cụ thể, Pub/Sub subscription hoặc Secret Manager secret.
- Phân biệt service account runtime với service account của build/deploy.
- Dùng Application Default Credentials hoặc cơ chế identity của runtime để lấy credential ngắn hạn.
- Giới hạn quyền impersonate service account và quyền deploy function.

Một service account có thể được gắn vào nhiều workload, nhưng mỗi binding cần được đánh giá theo ranh giới tin cậy. Không cấp Editor/Owner cho service account runtime chỉ để tránh lỗi permission.

## 9. Secret, token và credential

Secret bao gồm API key, password database, private key, webhook signing secret và token mà ứng dụng cần để xác thực với hệ thống khác. Không nên:

- Hard-code secret trong source code hoặc container image.
- Commit secret vào Git hoặc file cấu hình.
- Đưa secret dài hạn vào build argument.
- Ghi secret vào log, exception hoặc trace.
- Dùng chung một secret cho nhiều function không liên quan.

### Dùng Secret Manager hoặc Key Vault

Function nên lấy secret từ dịch vụ quản lý secret bằng execution identity. Cấp quyền đọc đúng secret và đúng version nếu nền tảng hỗ trợ. Nếu secret chỉ cần lúc khởi động, cân nhắc nạp một lần và quản lý cache trong giới hạn vòng đời runtime. Nếu secret cần rotation nhanh, cần có cách làm mới mà không yêu cầu redeploy toàn bộ function.

Secret manager thường cung cấp encryption at rest, access policy, versioning, audit và rotation integration. Các tính năng này không tự động làm ứng dụng an toàn nếu function được quyền đọc mọi secret hoặc log lộ giá trị secret.

### Credential ngắn hạn

Credential ngắn hạn giảm thời gian hữu dụng của token bị lộ. Hãy:

- Dùng identity do nền tảng cấp.
- Hạn chế thời gian sống token theo khả năng dịch vụ.
- Không lưu token vào filesystem hoặc cache dùng chung nếu không cần.
- Không gửi token tới client hoặc dịch vụ không đáng tin cậy.
- Xử lý refresh/renew theo SDK và runtime chính thức.
- Thu hồi hoặc giảm quyền identity khi phát hiện xâm phạm.

Không tự tạo cơ chế ký token hoặc lưu credential riêng nếu cloud provider đã cung cấp workload identity phù hợp.

## 10. Truyền danh tính người dùng tới function và dịch vụ downstream

Function có thể cần thực hiện hành động thay mặt người dùng, ví dụ đọc báo cáo mà người dùng được phép xem. Có hai mô hình thường gặp:

### Authorization trong ứng dụng

API Gateway xác thực caller và truyền claims đã xác minh tới function. Function kiểm tra tenant, role và quyền nghiệp vụ trước khi đọc dữ liệu. Execution role của function vẫn là danh tính kỹ thuật để truy cập dịch vụ cloud; code phải áp dụng authorization theo caller context.

### Token exchange hoặc delegated identity

Trong một số kiến trúc, function cần gọi downstream service dưới danh nghĩa người dùng. Có thể dùng OAuth token exchange, on-behalf-of flow hoặc cơ chế delegation tương đương. Khi đó cần giới hạn audience, scope, thời hạn và loại token được phép trao đổi.

Không nên chuyển nguyên bearer token của caller sang mọi downstream service. Token có thể có audience không phù hợp, quyền quá rộng hoặc bị lộ qua log. Chỉ chuyển token khi thiết kế xác thực và authorization yêu cầu rõ ràng.

### Không tin input để quyết định quyền

Một payload có trường userId, tenantId hoặc role=admin không chứng minh người gửi sở hữu danh tính đó. Function phải lấy caller identity từ context đã được gateway hoặc identity provider xác minh, sau đó đối chiếu quyền với dữ liệu tin cậy.

## 11. Quyền cho event source và trigger

Mỗi loại trigger có mô hình quyền khác nhau:

| Trigger | Quyền cần xem xét |
|---|---|
| HTTP/API Gateway | Caller được phép gọi route; gateway được phép invoke function; function có execution permissions riêng |
| Object storage notification | Dịch vụ storage được phép gửi sự kiện hoặc invoke function; giới hạn bucket/account nguồn |
| Scheduler | Scheduler có quyền invoke function; execution role của function tách biệt |
| Queue | Poller/event source mapping cần quyền đọc queue và quản lý visibility/acknowledgement theo nền tảng |
| Pub/Sub hoặc event bus | Publisher được phép publish; subscription/consumer được phép nhận; function được kích hoạt theo cấu hình |
| Database stream | Consumer cần quyền đọc stream/checkpoint; function cần quyền downstream riêng |

Với event push, resource policy có thể giới hạn service principal và nguồn cụ thể. Với event pull, dịch vụ tích hợp có thể sử dụng role của function hoặc identity riêng cho event source mapping. Cần kiểm tra quyền thực tế của từng dịch vụ.

### Chống confused deputy

Confused deputy xảy ra khi một dịch vụ có quyền hợp lệ bị bên khác lừa sử dụng quyền đó thay cho tài nguyên không được phép. Để giảm rủi ro:

- Giới hạn nguồn invoke bằng source account, resource ARN, organization hoặc condition tương đương.
- Dùng external ID khi mô hình cross-account yêu cầu.
- Không cho một service principal chung invoke mọi function.
- Tách quyền publisher, subscriber và execution.
- Kiểm tra tenant/account của sự kiện trước khi xử lý.

Không chỉ dựa trên tên event hoặc trường do caller gửi; xác minh nguồn qua metadata và policy của nền tảng.

## 12. Gọi dịch vụ downstream và xác thực giữa workload

Khi function gọi database, internal API hoặc service khác, hãy dùng danh tính workload phù hợp:

- Database authentication bằng IAM token hoặc identity integration nếu hỗ trợ.
- OAuth client credentials hoặc workload federation cho internal API.
- mTLS khi cần xác thực hai chiều giữa workload.
- Service account/managed identity với quyền được gán trên tài nguyên đích.

Tránh lưu password database lâu dài trong environment variable nếu có thể dùng token hoặc secret manager. Nếu buộc phải dùng password, lưu trong secret manager, giới hạn quyền đọc và có kế hoạch rotation.

### Một function không nên kế thừa quyền của function khác

Nếu function A gọi function B, không nên mặc định chia sẻ execution role của A cho B. A chỉ cần quyền invoke B; B có execution identity riêng để truy cập dữ liệu của nó. Việc tách này giúp giới hạn tác động nếu A bị xâm phạm.

## 13. Network policy không thay thế IAM

Private subnet, firewall, security group hoặc VPC connector có thể giới hạn đường mạng mà function sử dụng. Tuy nhiên, network reachability không đồng nghĩa authorization.

- Một function có route tới database vẫn cần credential và quyền database phù hợp.
- Một function không có public IP vẫn có thể có IAM permission quá rộng.
- Một API nội bộ có thể reachable qua private network nhưng vẫn cần xác thực caller.
- Egress restriction giúp giảm khả năng exfiltration nhưng không thay thế permission policy.

Kết hợp identity policy, resource policy, network segmentation, TLS và authorization ứng dụng để bảo vệ cả đường truy cập lẫn thao tác được phép.

## 14. Quản lý danh tính trong CI/CD và IaC

Pipeline triển khai thường cần quyền tạo/cập nhật function, gắn execution role, cấu hình trigger và phát hành code. Đây là quyền quản trị control plane, khác với quyền runtime của function.

### Tách deployment identity và runtime identity

Deployment identity có thể được phép:

- Tạo hoặc cập nhật function trong project/account cụ thể.
- Gắn một execution role đã được phê duyệt.
- Cập nhật alias, version hoặc trigger trong phạm vi ứng dụng.
- Đọc trạng thái triển khai và logs cần thiết.

Deployment identity không nên mặc nhiên có quyền quản trị mọi IAM role hoặc tự tạo policy tùy ý. Nếu pipeline có thể gắn bất kỳ role nào vào function, người kiểm soát pipeline có thể gián tiếp nhận quyền rất rộng.

### Infrastructure as Code

Định nghĩa role, trust policy, permission policy, trigger và function bằng IaC giúp review và tái lập. Trong pull request, cần kiểm tra:

- Quyền mới được thêm và lý do nghiệp vụ.
- Resource ARN hoặc scope có bị mở rộng không.
- Có wildcard action/resource không.
- Trust principal có bị mở rộng không.
- Có secret hoặc credential bị đưa vào state/plan/log không.
- Role cũ có quyền thừa cần thu hồi không.

State file của IaC có thể chứa thông tin nhạy cảm; lưu ở backend được bảo vệ, mã hóa và giới hạn quyền.

### Federation cho CI

Ưu tiên OIDC/workload federation giữa CI provider và cloud thay vì access key dài hạn. Trust condition nên giới hạn repository, branch, environment hoặc workflow identity. Một token từ fork hoặc branch không đáng tin cậy không nên có quyền deploy production.

## 15. Kiểm toán và quan sát quyền

Để biết function thực sự dùng quyền nào, cần kết hợp:

- Audit log của IAM/control plane.
- Log truy cập dịch vụ như object storage, queue, secret manager và database.
- Runtime logs và distributed traces.
- Policy simulator hoặc công cụ phân tích quyền của nhà cung cấp.
- Cloud asset inventory và phát hiện credential/policy thay đổi.

Theo dõi các sự kiện:

- Assume role, token issuance hoặc managed identity token request.
- Invoke function thành công/thất bại.
- AccessDenied hoặc authorization failure ở downstream.
- Thay đổi trust policy, permission policy hoặc resource policy.
- Thay đổi trigger, environment và execution identity.
- Secret access bất thường hoặc tăng đột biến.

Không ghi raw access token, private key, password hoặc toàn bộ secret vào log. Log nên có request ID, principal ID, resource, action, outcome và context cần thiết mà không làm lộ credential.

### Phát hiện quyền không dùng

Định kỳ xem lại:

- Action được cấp nhưng không xuất hiện trong audit log trong khoảng thời gian phù hợp.
- Resource không còn được workload truy cập.
- Role không còn function nào sử dụng.
- Quyền quản trị được cấp tạm thời nhưng chưa thu hồi.
- Secret cũ hoặc version không còn dùng.

Không xóa quyền chỉ dựa trên một cửa sổ log ngắn. Có thể có job theo mùa hoặc tác vụ khẩn cấp ít chạy. Kết hợp owner, lịch nghiệp vụ và thử nghiệm trước khi thu hồi.

## 16. Quy trình cấp quyền tối thiểu cho một function mới

1. **Mô tả nhiệm vụ:** function nhận input nào, tạo output nào và gọi dịch vụ nào.
2. **Liệt kê tài nguyên:** bucket, queue, table, secret, log group, API và key mã hóa.
3. **Xác định principal:** caller, trigger, execution và deployment identity.
4. **Tạo identity riêng:** role, managed identity hoặc service account phù hợp.
5. **Giới hạn trust:** chỉ runtime/function hoặc workload được phép nhận identity.
6. **Viết permission policy:** action cụ thể, resource cụ thể và condition cần thiết.
7. **Cấu hình invoke:** chỉ cho phép gateway/event source/principal dự kiến gọi.
8. **Kiểm thử dương:** thao tác hợp lệ hoạt động.
9. **Kiểm thử âm:** truy cập ngoài scope bị từ chối.
10. **Bật audit và cảnh báo:** theo dõi assume, invoke và downstream access.
11. **Review sau triển khai:** so sánh quyền khai báo với quyền thực tế, thu hồi quyền thừa.

### Kiểm thử dương và âm

Ví dụ với function xử lý ảnh:

- Dương: đọc được object trong prefix uploads.
- Dương: ghi được thumbnail vào prefix thumbnails.
- Âm: không đọc được bucket payroll.
- Âm: không xóa object đầu vào nếu nhiệm vụ không cần.
- Âm: không sửa IAM policy hoặc tạo user.
- Âm: principal ngoài event source được phê duyệt không thể invoke function.

Kiểm thử âm giúp xác minh policy thực sự giới hạn quyền, thay vì chỉ kiểm tra luồng thành công.

## 17. Troubleshooting lỗi danh tính và quyền

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Function không khởi động do assume role thất bại | Trust policy sai, service principal hoặc subject không khớp | Kiểm tra trust relationship, account, issuer, audience |
| Function chạy nhưng nhận AccessDenied | Permission policy thiếu action/resource hoặc condition không thỏa | Xác định API call, principal, resource và explicit Deny |
| Trigger không gọi được function | Thiếu invoke permission hoặc event source mapping lỗi | Kiểm tra resource policy, subscription, mapping và source scope |
| Đọc được bucket A nhưng không bucket B | Policy chỉ cho phép resource A | Xác minh yêu cầu và thêm quyền đúng prefix nếu hợp lệ |
| Secret retrieval thất bại | Thiếu quyền secret, KMS decrypt hoặc network route | Kiểm tra secret policy, key policy, identity và endpoint |
| Credential hết hạn giữa xử lý | Ứng dụng cache token sai hoặc không refresh | Dùng SDK/runtime credential provider chính thức |
| Chỉ production lỗi | Identity, resource policy hoặc secret khác môi trường | So sánh role binding, trust, account và secret version |
| CI deploy được nhưng function không truy cập dịch vụ | Deployment identity có quyền deploy nhưng execution identity thiếu quyền runtime | Kiểm tra hai identity riêng biệt |
| Function gọi downstream bị từ chối | Audience, scope, token exchange hoặc service account binding sai | Kiểm tra token claims và policy đích |
| Quyền mở rộng ngoài dự kiến | Role dùng chung hoặc deployment identity được phép gắn role tùy ý | Rà soát role attachment, trust và deployment permissions |

Khi gặp AccessDenied, không thêm quyền administrator để thử. Hãy lấy thông tin action, resource, principal và request context từ log; sau đó xác định policy nào đang đánh giá request.

## 18. Ví dụ policy theo từng function

Giả sử một hệ thống có ba function:

| Function | Tài nguyên cần truy cập | Quyền được cấp |
|---|---|---|
| order-validator | Public key set và bảng đọc đơn hàng | Read key material được phê duyệt; read đúng table/index |
| order-writer | Bảng đơn hàng và queue event | Insert/update đúng bảng; publish đúng queue |
| notification-sender | Queue notification và secret provider gửi tin | Consume queue; read một secret; gửi qua provider |

Nếu dùng một role chung, cả ba function có thể nhận toàn bộ quyền của ba nhóm. Nếu tách identity, một lỗ hổng trong notification-sender không tự động cho phép sửa bảng đơn hàng. Đây là lợi ích của việc phân tách theo trách nhiệm.

### Ví dụ quyền AWS cho queue consumer

Policy minh họa:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ConsumeNotificationQueue",
      "Effect": "Allow",
      "Action": [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes"
      ],
      "Resource": "arn:aws:sqs:ap-southeast-1:111122223333:notification-jobs"
    }
  ]
}
~~~

Danh sách action thực tế cần đối chiếu với event source mapping, cách polling và cấu hình mã hóa của queue. Nếu queue dùng customer-managed KMS key, có thể cần quyền giải mã trên đúng key và key policy phải cho phép principal. Không cấp quyền purge queue hoặc quản lý queue nếu function chỉ cần tiêu thụ message.

## 19. Những sai lầm thường gặp

1. **Dùng một role quản trị cho mọi function:** một lỗ hổng nhỏ có thể mở quyền trên toàn hệ thống.
2. **Nhầm quyền invoke với quyền execution:** gateway gọi được function nhưng function vẫn không có quyền truy cập tài nguyên, hoặc ngược lại.
3. **Dùng credential cá nhân:** vòng đời function bị gắn với tài khoản nhân viên và quyền thường quá rộng.
4. **Nhúng access key vào code hoặc environment:** secret có thể bị lộ qua repository, log hoặc snapshot cấu hình.
5. **Chỉ giới hạn action mà không giới hạn resource:** function có thể thao tác trên mọi bucket, queue hoặc secret.
6. **Trust policy quá rộng:** workload không liên quan có thể assume role.
7. **Tin tenantId hoặc userId từ input:** client có thể giả mạo context authorization.
8. **Dùng chung identity giữa môi trường:** staging có thể truy cập production.
9. **Quên quyền KMS hoặc resource policy:** policy của function cho phép nhưng tài nguyên đích vẫn từ chối.
10. **Không kiểm thử quyền âm:** chỉ chứng minh thao tác hợp lệ, không chứng minh thao tác ngoài scope bị chặn.
11. **Không thu hồi quyền tạm:** quyền debug hoặc quyền triển khai tồn tại lâu hơn cần thiết.
12. **Ghi token/secret vào log:** tạo thêm đường rò rỉ credential.

## 20. Checklist cấp danh tính cho từng hàm

- [ ] Đã mô tả caller, trigger, execution và deployment identity.
- [ ] Function có role/managed identity/service account riêng theo trách nhiệm.
- [ ] Trust policy chỉ cho đúng runtime hoặc workload được assume.
- [ ] Permission policy chỉ có action cần thiết.
- [ ] Resource scope giới hạn tới đúng bucket, prefix, queue, table, secret hoặc key.
- [ ] Condition và explicit deny được dùng khi cần để bảo vệ ranh giới.
- [ ] Quyền invoke được cấu hình riêng với quyền execution.
- [ ] Push trigger và pull event source được xử lý theo đúng mô hình của nền tảng.
- [ ] Không dùng access key dài hạn hoặc credential cá nhân trong function.
- [ ] Secret được lưu trong secret manager và có rotation.
- [ ] Caller identity được xác minh; không tin trường user/tenant do client tự gửi.
- [ ] Deployment identity không thể tùy ý gắn role quản trị vào function.
- [ ] Network policy bổ trợ cho IAM và authorization ứng dụng.
- [ ] Audit log ghi principal, action, resource và kết quả mà không lộ secret.
- [ ] Đã kiểm thử cả thao tác được phép và thao tác phải bị từ chối.
- [ ] Có owner, quy trình review và thời hạn thu hồi quyền không còn dùng.

## 21. Bài tập vận dụng

Một hệ thống serverless có hai function:

- invoice-reader đọc dữ liệu hóa đơn từ database và tạo file PDF trong bucket invoice-output.
- email-sender nhận message từ queue, lấy API key của nhà cung cấp email từ secret manager và gửi email cho khách hàng.

Hiện tại cả hai function dùng chung một execution role có quyền đọc/ghi mọi bucket, đọc mọi secret, quản lý queue và cập nhật IAM policy.

1. Hãy liệt kê các rủi ro của việc dùng chung role hiện tại.
2. Đề xuất execution identity riêng và permission tối thiểu cho từng function.
3. Principal nào cần quyền invoke mỗi function? Quyền đó nên được cấu hình ở đâu?
4. Vì sao deployment identity cần được tách khỏi execution identity?
5. Hãy nêu ít nhất ba kiểm thử âm để chứng minh quyền được giới hạn đúng.
6. Nếu email-sender bị khai thác, kiến trúc mới giúp giới hạn phạm vi ảnh hưởng như thế nào?

Gợi ý: invoice-reader chỉ cần đọc đúng database/table và ghi PDF vào prefix invoice-output. email-sender chỉ cần consume queue cụ thể, đọc một secret và gọi endpoint gửi email. Trigger service hoặc caller được phép invoke theo resource policy/event configuration; execution role của từng function không thay thế quyền invoke. Deployment pipeline chỉ được cập nhật function và gắn role đã phê duyệt. Kiểm thử âm gồm đọc secret khác, xóa bucket, cập nhật IAM, đọc bảng ngoài phạm vi hoặc invoke function từ principal không được phép.

## Kết luận

Cấp danh tính và quyền tối thiểu cho từng hàm bắt đầu bằng việc phân biệt caller, trigger, execution và deployment identity. Mỗi function nên chạy bằng workload identity phù hợp với trách nhiệm riêng; trust policy giới hạn ai được nhận danh tính, còn permission policy giới hạn action, resource và condition. Quyền invoke phải được quản lý riêng với quyền truy cập dịch vụ downstream. Dùng credential ngắn hạn, secret manager, audit log, IaC review và kiểm thử âm giúp giảm phạm vi ảnh hưởng khi code, dependency hoặc một principal bị xâm phạm.
