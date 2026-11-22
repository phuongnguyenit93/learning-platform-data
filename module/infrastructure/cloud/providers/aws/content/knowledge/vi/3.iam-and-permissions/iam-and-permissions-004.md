# Identity-based policy và resource-based policy trong AWS IAM

Trong AWS, **IAM (Identity and Access Management)** giúp xác định **ai được phép làm gì đối với tài nguyên nào và trong điều kiện nào**. Hai cách cấp quyền quan trọng nhất là **identity-based policy** (chính sách gắn với danh tính) và **resource-based policy** (chính sách gắn với tài nguyên). Chúng thường cùng xuất hiện trong một kiến trúc: một role được phép đọc dữ liệu, trong khi bucket chứa dữ liệu xác định những principal nào được truy cập.

Bài học thuộc chương **IAM và phân quyền** của mô-đun **CLOUD_PROVIDERS_AWS**, nằm trong lộ trình khám phá AWS từ Region/AZ, IAM, VPC đến compute, storage, database, tích hợp và serverless. Hiểu chính xác cơ chế IAM giúp người học lựa chọn dịch vụ, triển khai ứng dụng theo nguyên tắc đặc quyền tối thiểu (least privilege), giám sát truy cập, phục hồi và kiểm soát rủi ro vận hành.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích chủ thể được gắn policy và thành phần khác nhau giữa hai loại.
2. Đọc, viết policy JSON ở mức cơ bản với **Effect, Action, Resource, Principal, Condition**.
3. Phân biệt truy cập **cùng tài khoản AWS** và **khác tài khoản AWS (cross-account)**.
4. Giải thích quy tắc **implicit deny**, **explicit allow**, **explicit deny** và các giới hạn như permissions boundary, session policy, SCP/RCP.
5. Phân biệt **IAM role trust policy**, **role permissions policy**, **S3 bucket policy** và **KMS key policy**.
6. Chọn nơi đặt quyền, xác minh cấu hình và phát hiện những lỗi phân quyền thường gặp.

## 2. Các khái niệm nền tảng

Một yêu cầu truy cập thường có bốn thành phần chính:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| **Principal** | Danh tính hoặc phiên đang thực hiện yêu cầu | IAM user, IAM role session, AWS service principal |
| **Action** | Thao tác muốn thực hiện | Đọc đối tượng S3 bằng **s3:GetObject** |
| **Resource** | Tài nguyên đích, thường định danh bằng ARN | Đối tượng trong một S3 bucket |
| **Context** | Thông tin đi kèm yêu cầu | Thời gian, nguồn mạng, tag, thuộc tính principal |

**ARN (Amazon Resource Name)** là định danh tài nguyên AWS, ví dụ **arn:aws:s3:::example-reports/2026/report.csv**. ARN của bucket S3 là **arn:aws:s3:::example-reports**, còn ARN đối tượng có phần **/key** phía sau. Một action không nhất thiết hỗ trợ mọi loại ARN; phải kiểm tra bảng **Actions, resources, and condition keys** của dịch vụ tương ứng.

AWS IAM đánh giá yêu cầu dựa trên những policy thực sự áp dụng cho principal và resource. **Policy chứa một câu lệnh Allow không đồng nghĩa yêu cầu chắc chắn được cho phép**: còn phải xét ngữ cảnh, các lớp giới hạn khác và bất kỳ Deny tường minh nào.

## 3. So sánh hai loại policy

| Tiêu chí | Identity-based policy | Resource-based policy |
|---|---|---|
| Gắn vào | IAM **user**, **group** hoặc **role** | Tài nguyên hỗ trợ policy, chẳng hạn **S3 bucket**, **SQS queue**, **SNS topic**, **KMS key**, **Lambda function**, hoặc **IAM role trust policy** |
| Câu hỏi chính | **Danh tính này được làm gì?** | **Ai được làm gì với tài nguyên này?** |
| Chỉ định người được hưởng quyền | Chính danh tính được gắn policy; thông thường **không có Principal** trong JSON | Dùng **Principal** để nêu tài khoản, role, user, phiên hoặc dịch vụ được phép |
| Phạm vi | Có thể cho phép thao tác trên nhiều tài nguyên/dịch vụ | Kiểm soát quyền đối với tài nguyên nơi policy được gắn |
| Managed/inline | Có **AWS managed**, **customer managed** và **inline** | Là **inline policy** gắn trực tiếp với tài nguyên, không có managed resource policy tương đương |
| Truy cập cross-account | Cấp quyền cho principal ở tài khoản nguồn | Nêu principal ở tài khoản khác được sử dụng tài nguyên đích, nếu dịch vụ hỗ trợ |
| Ví dụ thực tế | Role của ứng dụng được đọc các file báo cáo | Bucket báo cáo chỉ nhận truy cập từ role được định danh |

> **Dễ nhầm:** Identity-based policy vẫn có phần **Resource** chỉ rõ ARN đích. Việc nêu ARN trong policy gắn với role **không biến nó thành resource-based policy**. Cách phân loại phụ thuộc vào **nơi policy được gắn**.

### 3.1. Identity-based policy

Identity-based policy đi theo danh tính hoặc role. Chẳng hạn, một Lambda execution role được phép ghi CloudWatch Logs; một role chạy ứng dụng ECS được phép đọc một prefix trong S3; hoặc một nhóm nhân viên có quyền xem billing theo phạm vi tổ chức cho phép.

Có hai cơ chế quản lý phổ biến:

- **Managed policy:** một policy độc lập có thể gắn cho nhiều danh tính. AWS managed policy do AWS quản lý; customer managed policy do tổ chức tạo và cập nhật. Việc thay đổi managed policy có thể ảnh hưởng đến tất cả danh tính đang gắn policy đó.
- **Inline policy:** nội dung policy được gắn và quản lý trực tiếp trong một user, group hoặc role cụ thể. Thích hợp khi cần quan hệ một-một, nhưng khó tái sử dụng hơn.

Khi gắn quyền cho **IAM group**, các IAM user thuộc group hưởng quyền từ policy gắn với group. Tuy nhiên, một group **không phải principal dùng để đăng nhập hoặc chỉ định trực tiếp trong Principal của bucket policy**.

### 3.2. Resource-based policy

Resource-based policy do chủ sở hữu tài nguyên quản lý. Chính sách thường bao gồm **Principal** để quy định ai được gọi action trên tài nguyên, có thể kèm **Condition** để thu hẹp phạm vi.

Các ví dụ quan trọng:

- **S3 bucket policy:** cho phép hoặc từ chối thao tác lên bucket và các đối tượng trong phạm vi được nêu.
- **SQS queue policy / SNS topic policy:** cho phép principal hoặc dịch vụ được chỉ định gửi/nhận thông điệp theo các action được dịch vụ hỗ trợ.
- **Lambda function resource policy:** có thể cho phép một principal hoặc dịch vụ khác **invoke** function; khác với permissions policy của **Lambda execution role** dùng khi function chạy.
- **KMS key policy:** quyết định ai có thể quản trị hoặc dùng khóa KMS; là thành phần bắt buộc đối với khóa.
- **IAM role trust policy:** là resource-based policy của chính IAM role, quy định ai được **AssumeRole**. Sau khi assume thành công, **permissions policy của role** mới xác định những hành động có thể thực hiện bằng phiên đó.

Không phải dịch vụ nào cũng hỗ trợ resource-based policy. Khi cần chia sẻ một dịch vụ không hỗ trợ cơ chế này giữa các tài khoản, **cross-account role** có thể là phương án phù hợp.

## 4. Cấu trúc policy JSON

Một câu lệnh policy thường có các trường sau:

| Trường | Chức năng | Ghi nhớ |
|---|---|---|
| **Version** | Phiên bản ngôn ngữ policy | Giá trị phổ biến hiện nay: **2012-10-17**; không phải số phiên bản của policy được lưu |
| **Statement** | Một hoặc nhiều quy tắc cấp/từ chối quyền | Là một object hoặc mảng các object |
| **Sid** | Nhãn tùy chọn của statement | Giúp người đọc nhận diện mục đích |
| **Effect** | **Allow** hoặc **Deny** | Deny tường minh được ưu tiên |
| **Action** | API/thao tác được xét | Có thể là tên action hoặc danh sách |
| **Resource** | ARN tài nguyên được xét | Có action yêu cầu hoặc chỉ hỗ trợ **\*** |
| **Principal** | Principal mà resource-based policy áp dụng | Thường có ở resource-based/trust policy; **không đặt trong identity-based policy** |
| **Condition** | Điều kiện để statement có hiệu lực | Ví dụ tag, nguồn gọi, bảo mật kết nối |

### 4.1. Ví dụ identity-based policy: chỉ đọc file trong prefix

Giả sử ứng dụng dùng role **MonthlyReportReader**. Role chỉ cần đọc đối tượng từ đường dẫn **exports/monthly/** của bucket **team-report-demo**. Identity-based policy gắn với role có thể viết như sau:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadMonthlyReportObjectsOnly",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::team-report-demo/exports/monthly/*"
    }
  ]
}
~~~

**Giải thích:** policy này cho phép gọi **GetObject** trên những object ARN khớp prefix đã nêu. Nó **không** tự cấp quyền **s3:PutObject**, **s3:DeleteObject** hoặc **s3:ListBucket**. Để ứng dụng duyệt danh sách object qua API list, cần cấp thêm **s3:ListBucket** trên **ARN của bucket** và có thể dùng điều kiện **s3:prefix** để giới hạn những prefix được liệt kê.

Vì đây là identity-based policy, không có **Principal**: principal đã được xác định bằng danh tính/role được gắn policy.

### 4.2. Ví dụ resource-based policy: bucket cho phép một role khác tài khoản

Xét hai tài khoản minh họa (ID và tên bucket chỉ là giả định):

- **Account A: 111122223333** — sở hữu IAM role **ReportReadRole**, nơi ứng dụng chạy.
- **Account B: 222233334444** — sở hữu S3 bucket **project-report-demo-222233334444**, có dữ liệu ở prefix **exports/**.

Bucket policy gắn ở **Account B**:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowReportReaderFromAccountA",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111122223333:role/ReportReadRole"
      },
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::project-report-demo-222233334444/exports/*"
    }
  ]
}
~~~

**Giải thích:** một role cụ thể trong Account A được nêu ở **Principal**. Chính sách được lưu ở bucket của Account B nên đây là **resource-based policy**. Nó chỉ cho phép đọc object trong prefix **exports/**, không cho phép ghi/xóa hoặc liệt kê bucket.

Để triển khai đường truy cập cross-account thông thường này, **ReportReadRole** ở Account A cũng cần identity-based policy cho phép **s3:GetObject** trên cùng object ARN:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadReportsFromAccountB",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::project-report-demo-222233334444/exports/*"
    }
  ]
}
~~~

Ở ví dụ này, **hai account phải đồng thời cho phép** yêu cầu theo cơ chế đánh giá cross-account. Nếu object mã hóa bằng **SSE-KMS** với customer managed KMS key, có thể còn cần quyền **kms:Decrypt** từ chính sách phù hợp và **KMS key policy**; S3 bucket policy một mình chưa đủ.

~~~mermaid
flowchart LR
    subgraph A["Account A — 111122223333"]
        APP["Ứng dụng dùng ReportReadRole"]
        ID["Identity-based policy\nAllow s3:GetObject"]
        APP --> ID
    end
    subgraph B["Account B — 222233334444"]
        BP["S3 bucket policy\nPrincipal = ReportReadRole"]
        OBJ["S3: exports/report.csv"]
        BP --> OBJ
    end
    ID -->|"Yêu cầu sang Account B"| BP
~~~

Sơ đồ thể hiện **đường truy cập trực tiếp tới S3 qua resource-based policy**. Nó khác với phương án **AssumeRole vào Account B**, được trình bày ở phần sau.

## 5. AWS đánh giá quyền truy cập như thế nào?

### 5.1. Ba nguyên tắc cơ bản

1. **Implicit deny (từ chối mặc định):** nếu không có Allow phù hợp, yêu cầu bị từ chối. Không có câu lệnh cho phép **không phải** là một Deny tường minh.
2. **Explicit allow (cho phép tường minh):** một statement **Effect: Allow** khớp principal, action, resource và condition có thể cho phép yêu cầu, tùy các chính sách liên quan khác.
3. **Explicit deny (từ chối tường minh):** một statement **Effect: Deny** áp dụng cho yêu cầu sẽ thắng các Allow tương ứng.

AWS xét toàn bộ policy áp dụng, không theo thứ tự văn bản mà người viết đặt các statement trong JSON.

### 5.2. Trong cùng một tài khoản: quyền thường là hợp của hai loại policy

Với yêu cầu trong **cùng một tài khoản**, AWS thường kết hợp quyền từ **identity-based** và **resource-based policy** theo phép **hợp (union)**. Chỉ cần một loại có Allow phù hợp là có thể cho phép, miễn không có Deny tường minh hoặc cơ chế giới hạn khác chặn.

| Identity-based | Resource-based | Kết quả cơ bản trong cùng tài khoản |
|---|---|---|
| Không có Allow | Không có Allow | **Deny** do mặc định |
| Allow | Không có Allow | **Allow** nếu không bị giới hạn khác |
| Không có Allow | Allow trực tiếp cho principal phù hợp | **Allow** nếu không bị giới hạn khác |
| Allow | Allow | **Allow** nếu không bị giới hạn khác |
| Explicit Deny | Allow | **Deny** |
| Allow | Explicit Deny | **Deny** |

Bảng là **mô hình cơ bản**, chưa thể hiện mọi giới hạn và ngoại lệ theo loại principal hoặc dịch vụ. Chẳng hạn, **permissions boundary**, **session policy**, **AWS Organizations SCP/RCP** hoặc chính sách đặc thù của dịch vụ có thể thay đổi kết quả.

**Ví dụ:** role trong Account A có quyền **s3:GetObject** trên bucket của chính Account A. Bucket không cần statement Allow lặp lại cho role này trong đa số tình huống; nhưng bucket có Deny áp dụng, hoặc một cơ chế giới hạn quyền khác có hiệu lực, vẫn có thể chặn truy cập.

### 5.3. Khác tài khoản: kiểm tra cả phía người gọi và phía tài nguyên

Với ví dụ S3 ở phần 4.2, yêu cầu phải qua hai đánh giá:

1. **Account A (tài khoản của principal):** identity-based policy của role và các giới hạn áp dụng phải cho phép hành động.
2. **Account B (tài khoản của resource):** bucket policy phải chấp nhận principal/hành động/tài nguyên, đồng thời những chính sách giới hạn hoặc bảo vệ tài nguyên cũng phải cho phép.

Nếu một trong hai phía trả về Deny, yêu cầu không được thực hiện. Không thể cấp quyền đọc bucket của Account B chỉ bằng cách gắn một IAM policy cho role ở Account A.

Lưu ý: kết quả thực tế có thể chịu thêm ảnh hưởng của **S3 Block Public Access**, cơ chế sở hữu đối tượng, chính sách endpoint, KMS key policy, AWS Organizations và các kiểm soát riêng của dịch vụ. Dùng các ví dụ như một mô hình nền tảng, không thay thế việc kiểm tra yêu cầu của từng dịch vụ.

### 5.4. Permissions boundary, session policy, SCP và RCP

Các loại policy khác có vai trò **giới hạn quyền**, không nên hiểu là thêm một nguồn Allow có thể tự cấp quyền như identity-based policy:

- **Permissions boundary:** đặt trần quyền cho IAM user/role trong những ngữ cảnh áp dụng; bản thân boundary không tạo ra quyền mới.
- **Session policy:** có thể thu hẹp quyền có được khi dùng thông tin xác thực tạm thời của phiên.
- **Service control policy (SCP):** giới hạn quyền tối đa của các principal thuộc những tài khoản trong AWS Organizations.
- **Resource control policy (RCP):** giới hạn quyền tối đa áp dụng cho tài nguyên thuộc phạm vi được hỗ trợ trong AWS Organizations.

**Ngoại lệ cần nhận biết:** trong cùng một tài khoản, resource-based policy cấp quyền **trực tiếp cho IAM user ARN hoặc role-session ARN** có các quy tắc liên quan đến implicit deny trong identity-based policy, boundary hoặc session policy khác với policy cấp cho **IAM role ARN**. Ví dụ, grant trực tiếp cho role session có thể không bị chặn chỉ bởi **implicit deny** của boundary/session policy; **explicit deny** vẫn có hiệu lực. Vì vậy không nên coi phép giao đơn giản của tất cả policy là công thức đúng cho mọi trường hợp. Khi thiết kế quyền nâng cao, phải xác minh **loại ARN được nêu ở Principal** và xem tài liệu IAM về đánh giá quyền.

### 5.5. Ví dụ explicit deny và điều kiện

Một S3 bucket policy có thể ngăn thao tác qua kết nối không sử dụng HTTPS:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyInsecureTransport",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": [
        "arn:aws:s3:::team-report-demo",
        "arn:aws:s3:::team-report-demo/*"
      ],
      "Condition": {
        "Bool": {
          "aws:SecureTransport": "false"
        }
      }
    }
  ]
}
~~~

Đây là **Deny theo điều kiện**, không phải statement công khai bucket. **Principal: \*** ở đây chỉ nói Deny áp dụng cho mọi principal phù hợp khi kết nối không an toàn. Một role có identity-based Allow vẫn bị từ chối nếu yêu cầu khớp Deny này.

## 6. Đặc biệt: trust policy của IAM role

IAM role vừa là **danh tính** mang permissions policy, vừa là **tài nguyên** có **trust policy**. Hai policy trả lời hai câu hỏi riêng:

| Loại policy của role | Trả lời | Action thường gặp |
|---|---|---|
| **Trust policy** | Ai hoặc dịch vụ nào được nhận phiên của role này? | **sts:AssumeRole** |
| **Permissions policy** | Sau khi nhận phiên, role được gọi những API nào? | **s3:GetObject**, **dynamodb:Query**, **logs:PutLogEvents**… |

Ví dụ: Account B có role **SharedDataReader**. Trust policy của role cho phép role **ReportReadRole** trong Account A yêu cầu assume:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111122223333:role/ReportReadRole"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

Để mô hình cross-account AssumeRole hoạt động, role gọi ở Account A thường cần **identity-based permission sts:AssumeRole** trên role đích ở B. Sau đó, role **SharedDataReader** ở B cần permissions policy cho phép **s3:GetObject** đối với dữ liệu mà nó phải đọc. Vì phiên giờ mang role của **Account B**, quyền truy cập vào bucket cùng Account B có thể được cấp qua identity-based policy của role đó theo các quy tắc same-account, không nhất thiết phải thêm bucket Allow riêng.

**Không nhầm lẫn:** cho phép **sts:AssumeRole** trong trust policy **không tự cho phép s3:GetObject**. Với Lambda, trust policy cho phép dịch vụ **lambda.amazonaws.com** assume execution role; còn function resource policy kiểm soát ai có thể gọi **lambda:InvokeFunction**. Hai đường phân quyền này khác mục đích.

## 7. Ngoại lệ nổi bật: AWS KMS

**KMS key policy** là resource-based policy mang tính đặc thù. Mỗi KMS key có key policy, và việc IAM identity-based policy ghi **kms:Decrypt: Allow** không tự bảo đảm decrypt được dữ liệu. **Key policy phải cho phép quyền trực tiếp hoặc cho phép IAM policies cấp quyền**, bên cạnh những cơ chế như grants khi phù hợp.

Với truy cập KMS cross-account, cần kiểm tra **key policy tại tài khoản sở hữu khóa** và **IAM policy tại tài khoản gọi**. Nếu object S3 dùng SSE-KMS, lỗi **AccessDenied** có thể xuất phát từ KMS mặc dù cả IAM policy và S3 bucket policy đều cho phép **s3:GetObject**.

KMS key policy được quản lý theo Region của khóa; không nên coi một policy KMS ở Region này tự áp dụng cho khóa ở Region khác.

## 8. Chọn loại policy trong các tình huống thực tế

| Tình huống | Nơi cấp quyền nên cân nhắc | Lý do |
|---|---|---|
| Ứng dụng EC2/ECS/Lambda cần đọc bảng DynamoDB hoặc object S3 | **Identity-based policy** gắn vào execution/task/instance role thích hợp | Quyền đi cùng workload đang gọi API |
| Bucket S3 ở Account B cho phép role cụ thể ở Account A đọc dữ liệu | **Bucket policy** ở B **và** **identity policy** ở A | Hai phía phải đồng ý trong đường truy cập cross-account thông thường |
| Một dịch vụ cần gửi sự kiện vào SQS queue | **SQS queue policy** với service principal và điều kiện hạn chế nguồn thích hợp | Queue là tài nguyên nhận yêu cầu từ dịch vụ khác |
| Principal ở Account A cần đảm nhận vai trò tại Account B | **Role trust policy** tại B; quyền **sts:AssumeRole** ở A; **role permissions policy** tại B | Quy định cả quyền nhận role và quyền thực thi sau khi nhận role |
| Chỉ một role được decrypt qua KMS key | **Key policy** cộng với IAM/grants khi thích hợp | Quyền dùng khóa phụ thuộc cơ chế phân quyền KMS |
| Ngăn truy cập S3 không dùng TLS | **Explicit Deny** trong bucket policy | Áp dụng guardrail trên tài nguyên cho các principal phù hợp |
| Chặn toàn tổ chức dùng một số action nhạy cảm | **SCP/RCP** nếu trường hợp được hỗ trợ, kết hợp IAM/resource policy | Thiết lập trần quyền ở cấp tổ chức |

Nguyên tắc thiết kế là **cấp đúng quyền cần dùng**, gắn quyền ở nơi có trách nhiệm quản lý rõ ràng, và dùng **IAM role với credentials ngắn hạn** cho workload thay vì phát tán access key dài hạn.

## 9. Quy trình thiết kế và kiểm tra policy

### Bước 1 — Xác định luồng yêu cầu

Ghi rõ principal, tài khoản của principal, action API, ARN tài nguyên, tài khoản sở hữu tài nguyên và điều kiện mong muốn. Phân biệt trường hợp **truy cập trực tiếp** với **AssumeRole**.

### Bước 2 — Kiểm tra service có hỗ trợ resource policy hay không

Tra cứu tài liệu IAM tương thích với dịch vụ. Xác minh service hỗ trợ **resource-based policy**, loại principal được phép, action cho từng loại ARN và các condition key có ý nghĩa. Không sao chép policy từ S3 sang dịch vụ khác khi chưa đối chiếu cú pháp và semantics.

### Bước 3 — Viết Allow tối thiểu và Deny cần thiết

- Hạn chế **Action** theo API bắt buộc, tránh **s3:\*** hoặc **iam:\*** nếu chỉ cần một thao tác.
- Hạn chế **Resource** tới ARN/prefix cụ thể khi action hỗ trợ phân quyền cấp tài nguyên.
- Với resource policy, giới hạn **Principal** tới role hoặc principal cụ thể; tránh cấp Allow cho **Principal: \*** trừ khi có thiết kế public access được phê duyệt.
- Dùng **Condition** để hạn chế thêm theo nguồn yêu cầu, tổ chức, tag hoặc TLS nếu dịch vụ/condition key hỗ trợ.
- Xác định các yêu cầu đặc biệt như SSE-KMS, endpoint policy, SCP/RCP, session policy và quyền quản lý tài nguyên.

### Bước 4 — Kiểm tra tài liệu policy và truy cập thực tế

AWS IAM Access Analyzer hỗ trợ **ValidatePolicy** để phát hiện nhiều lỗi, cảnh báo cấu hình và khuyến nghị. Đối với một file **identity policy** đã soạn trong môi trường thử nghiệm, có thể kiểm tra:

~~~bash
aws accessanalyzer validate-policy --policy-type IDENTITY_POLICY --policy-document file://identity-policy.json
~~~

Với resource-based policy, dùng **RESOURCE_POLICY** và kiểm tra các tham số bổ sung mà loại tài nguyên/dịch vụ yêu cầu. Kiểm tra cú pháp chỉ là bước đầu; để đánh giá rủi ro chia sẻ tài nguyên, sử dụng **IAM Access Analyzer** và các chức năng kiểm tra external access phù hợp.

Trước khi truy vết lỗi quyền, xác nhận danh tính đang thực thi bằng:

~~~bash
aws sts get-caller-identity
~~~

Sau đó, kiểm tra policy đính kèm đúng role/session và policy trên đúng tài nguyên. Thử **hành động được phép** và **hành động phải bị từ chối** trong môi trường được phép thử. Có thể dùng **IAM Policy Simulator** cho những tình huống được hỗ trợ, nhưng không nên coi kết quả mô phỏng là bằng chứng đầy đủ cho mọi cơ chế cross-account, resource policy hoặc service-specific controls.

### Bước 5 — Giám sát và rà soát

Sử dụng **AWS CloudTrail** để điều tra thao tác API; xem xét **IAM Access Analyzer** để phát hiện chia sẻ ngoài dự kiến; đánh giá định kỳ permissions đã cấp với hành vi sử dụng thật. Phân quyền cần được cập nhật khi role đổi chức năng, ứng dụng thêm API mới, tài khoản thay đổi hoặc tài nguyên chuyển chủ sở hữu.

## 10. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Role có Allow nhưng vẫn **AccessDenied** khi đọc bucket cross-account | Bucket policy ở tài khoản đích chưa cho phép principal hoặc giới hạn khác đang chặn | Principal ARN trong bucket policy, role identity policy, Deny và điều kiện |
| Truy cập object được nhưng không liệt kê danh sách | Có **s3:GetObject** nhưng thiếu **s3:ListBucket** | Action và ARN bucket so với ARN object |
| AssumeRole thành công nhưng không đọc được dữ liệu | Trust policy chỉ cấp quyền AssumeRole; permissions policy của role đích còn thiếu | Policy của role sau assume và policy của tài nguyên đích |
| IAM policy cho phép decrypt nhưng KMS trả **AccessDenied** | Key policy không cho phép/không mở cơ chế ủy quyền IAM, hoặc thiếu grants/quyền phù hợp | Key ARN, key policy, IAM policy và Region |
| Policy có **Principal** nhưng trình kiểm tra IAM từ chối | Dùng Principal trong identity-based policy | Đặt Principal tại resource policy/trust policy đúng vị trí |
| Bucket policy được lưu nhưng người dùng vẫn bị chặn | Explicit Deny, Block Public Access, condition không khớp hoặc cơ chế bảo vệ khác | Xem request context, SCP/RCP, encryption, policy trên các lớp |
| Dùng **Resource: \*** khắp mọi nơi | Action không được phân tích theo ARN, hoặc copy policy quá rộng | Đối chiếu service authorization reference; thu hẹp khi action hỗ trợ |
| Policy cấp cho **IAM group** nhưng không truy cập như group được | Group không phải danh tính đăng nhập hoặc principal trực tiếp | Gán policy cho group để các user thừa hưởng; dùng role ARN cho resource policy |

## 11. Bài tập vận dụng

**Tình huống 1 — Cùng tài khoản:** Một ứng dụng Lambda trong Account A cần đọc các object thuộc prefix **incoming/** của một bucket S3 cũng ở Account A. Thiết kế tối thiểu nên bắt đầu ở đâu?

**Gợi ý:** gắn identity-based policy cho **Lambda execution role** với **s3:GetObject** trên ARN object thuộc prefix được phép. Thêm **s3:ListBucket** trên ARN bucket nếu code có thao tác list. Xác nhận không có Deny/giới hạn khác. Không phải luôn thêm bucket policy Allow trùng lặp cho role trong cùng tài khoản.

**Tình huống 2 — Khác tài khoản:** Nhóm phân tích ở Account A cần đọc object từ bucket của Account B, không cần đảm nhận role ở B. Nhóm chỉ thêm **s3:GetObject** trong IAM policy ở A rồi gặp AccessDenied.

**Gợi ý:** triển khai resource-based policy trên bucket ở B nêu đúng principal role của A và object ARN, đồng thời giữ identity-based Allow tại A; kiểm tra điều kiện KMS nếu object được mã hóa bằng SSE-KMS. Dùng IAM Access Analyzer và kiểm thử API để phát hiện những giới hạn khác.

**Tình huống 3 — Role trust:** Account B tạo role cho phép role từ Account A assume. Việc này đã đủ để role nguồn có thể xóa object của B chưa?

**Gợi ý:** chưa. Phải kiểm tra quyền **sts:AssumeRole** của caller, trust policy của role đích, quyền **s3:DeleteObject** trong role permissions policy và những giới hạn/bảo vệ của bucket. Khi thiết kế nghiệp vụ chỉ cần đọc, không cấp quyền xóa.

## 12. Checklist trước khi áp dụng IAM policy

- [ ] Đã xác định chính xác **principal**, **action**, **resource ARN**, **account** và **condition**.
- [ ] Đã phân biệt quyền gắn với danh tính và quyền gắn với tài nguyên.
- [ ] Policy JSON có đúng các trường; identity-based policy không chứa **Principal**.
- [ ] Đã áp dụng **least privilege**, tránh Allow quá rộng trên Action, Resource hoặc Principal.
- [ ] Đã xác định yêu cầu cùng tài khoản hay cross-account, truy cập trực tiếp hay AssumeRole.
- [ ] Đã xét permissions boundary, session policy, SCP/RCP và explicit deny khi có.
- [ ] Đã kiểm tra đặc thù của dịch vụ, như S3 Block Public Access và KMS key policy.
- [ ] Đã validate policy và thử cả hành vi được phép lẫn hành vi cần bị từ chối.
- [ ] Đã thiết lập giám sát CloudTrail và đánh giá chia sẻ ngoài dự kiến bằng IAM Access Analyzer.

## 13. Ghi nhớ và tài liệu chính thức

**Identity-based policy** trả lời **“danh tính này được làm gì?”**; **resource-based policy** trả lời **“ai được làm gì với tài nguyên này?”**. Trong cùng tài khoản, hai nguồn quyền thường phối hợp theo phép hợp dưới các giới hạn phù hợp. Khi truy cập cross-account, cần phân tích quyền của cả tài khoản người gọi và tài khoản tài nguyên. **Explicit Deny** và chính sách giới hạn có thể làm một Allow trở nên không đủ. Với IAM role, hãy tách **quyền assume** khỏi **quyền thực thi sau assume**.

Tài liệu AWS nên đối chiếu khi triển khai:

- [Identity-based policies and resource-based policies — AWS IAM](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_identity-vs-resource.html)
- [Policy evaluation logic — AWS IAM](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html)
- [Cross-account policy evaluation logic — AWS IAM](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic-cross-account.html)
- [Permissions boundaries for IAM entities — AWS IAM](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_boundaries.html)
- [Cross account resource access in IAM](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies-cross-account-resource-access.html)
- [Bucket policies — Amazon S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucket-policies.html)
- [Key policies — AWS KMS](https://docs.aws.amazon.com/kms/latest/developerguide/key-policies.html)
- [Access Analyzer policy validation](https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-policy-validation.html)
