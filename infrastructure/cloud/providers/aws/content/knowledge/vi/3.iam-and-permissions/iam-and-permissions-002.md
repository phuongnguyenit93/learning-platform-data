# Cấu trúc policy với action, resource và condition

> **Chương:** IAM và phân quyền  
> **Học phần:** `CLOUD_PROVIDERS_AWS` — khám phá hệ sinh thái AWS, thiết kế ứng dụng an toàn, có khả năng giám sát, phục hồi và kiểm soát chi phí.

Trong AWS, một tài khoản đăng nhập thành công **không đồng nghĩa** với việc được phép gọi mọi API. AWS Identity and Access Management (**IAM**) dùng **policy** để mô tả ai có thể thực hiện hành động gì, trên tài nguyên nào và trong điều kiện nào. Ba thành phần cần nắm vững để viết một quyền truy cập có giới hạn là **`Action`**, **`Resource`** và **`Condition`**.

Bài học tập trung vào cú pháp và cách suy luận về policy. Các ví dụ dùng tên bucket, số tài khoản và ARN giả định; cần thay bằng giá trị thực, kiểm tra tài liệu dịch vụ và thử nghiệm trong môi trường phù hợp trước khi dùng trong production.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

1. Đọc cấu trúc một IAM policy dạng JSON, hiểu `Version`, `Statement`, `Effect`, `Action`, `Resource` và `Condition`.
2. Phân biệt **identity-based policy**, **resource-based policy** và **role trust policy**; biết trường hợp nào dùng `Principal`.
3. Chọn hành động phù hợp, giới hạn ARN tài nguyên và áp dụng điều kiện theo request context.
4. Giải thích cơ chế allow, implicit deny và explicit deny khi có nhiều statement hoặc nhiều loại policy.
5. Viết và phân tích policy theo nguyên tắc **least privilege**, đồng thời kiểm tra lỗi thông dụng với công cụ AWS.

## 2. IAM policy nằm ở đâu trong quy trình cấp quyền?

IAM policy là tài liệu JSON mô tả các **quy tắc cấp hoặc từ chối quyền**. Chính sách này có thể gắn với identity như IAM user, group hoặc role; cũng có thể gắn trực tiếp với tài nguyên hỗ trợ resource-based policy, như S3 bucket.

Khi một ứng dụng dùng **IAM role** gọi API, AWS xét các thông tin của yêu cầu:

- **Principal:** danh tính đang gọi API, ví dụ một role session từ EC2 hoặc Lambda.
- **Action:** thao tác được yêu cầu, ví dụ `s3:GetObject`.
- **Resource:** đối tượng đích, ví dụ `arn:aws:s3:::example-company-reports-2026/reports/summary.csv`.
- **Context:** các thuộc tính bổ sung như tag, địa chỉ IP, vùng endpoint được gọi, cách kết nối hoặc thông tin xác thực, tùy API và dịch vụ.

AWS sau đó đánh giá các policy áp dụng cùng những giới hạn liên quan. Không nên hiểu “có một statement Allow” là đảm bảo được truy cập: có thể còn **explicit Deny**, permission boundary, session policy, chính sách tổ chức hoặc các điều kiện khác.

### 2.1. Những loại policy thường gặp

| Loại | Nơi gắn | Vai trò |
| --- | --- | --- |
| **Identity-based policy** | IAM user, group, role | Mô tả quyền mà danh tính có thể sử dụng |
| **Resource-based policy** | Tài nguyên có hỗ trợ, ví dụ S3 bucket | Mô tả principal nào được hoặc không được truy cập tài nguyên |
| **Role trust policy** | IAM role | Quy định principal nào được phép đảm nhận role qua STS |
| **Permissions boundary** | IAM user hoặc role | Đặt giới hạn quyền tối đa cho identity, không tự cấp quyền |
| **Service control policy (SCP)** | AWS Organizations (tài khoản/OU) | Giới hạn tối đa đối với principal bị áp dụng trong tổ chức, không tự cấp quyền |
| **Session policy** | Phiên STS phù hợp | Có thể giới hạn quyền của phiên tạm thời |

**Managed policy** là policy quản lý riêng, có thể dùng lại; gồm AWS managed và customer managed policy. **Inline policy** được nhúng trực tiếp vào một identity. Đây là cách **đóng gói/gắn policy**, không thay đổi ý nghĩa cơ bản của `Action`, `Resource` và `Condition`.

## 3. Bộ khung của IAM JSON policy

Một identity-based policy đơn giản:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadReports",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::example-company-reports-2026/reports/*"
    }
  ]
}
~~~

Policy này cho phép danh tính được gắn policy gọi `s3:GetObject` đối với các object có key bắt đầu bằng `reports/` trong bucket minh họa. Nó **không** cấp quyền liệt kê bucket, tải lên object hay đọc object ngoài tiền tố đó.

| Trường | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `Version` | Phiên bản ngôn ngữ policy | Thường dùng `"2012-10-17"`; đây **không phải** ngày tạo policy |
| `Statement` | Một statement hoặc danh sách statement | Mỗi statement mô tả một nhóm quy tắc |
| `Sid` | Mã hoặc nhãn cho statement (tùy chọn) | Giúp kiểm tra, không phải yếu tố cấp quyền |
| `Effect` | `"Allow"` hoặc `"Deny"` | Mô tả kết quả nếu statement khớp |
| `Action` / `NotAction` | Hành động được nhắm đến | Thông thường dùng `Action` để phạm vi rõ ràng |
| `Resource` / `NotResource` | Tài nguyên được nhắm đến | Phải tương thích với khả năng hỗ trợ resource-level của action |
| `Condition` | Điều kiện bổ sung (tùy chọn) | Kiểm tra các condition key trong request context |
| `Principal` / `NotPrincipal` | Danh tính áp dụng trên resource-based policy/trust policy | **Không đặt `Principal` trong identity-based policy** |

Một tài liệu có thể chứa nhiều statement. Chúng **không chạy từ trên xuống dưới như câu lệnh lập trình** và `Sid` không tạo ưu tiên. Mọi statement liên quan đều có thể ảnh hưởng đến kết quả: một explicit Deny phù hợp sẽ thắng Allow.

## 4. Action: được làm thao tác gì?

### 4.1. Cú pháp `service:ActionName`

Thông thường một hành động IAM có dạng:

~~~text
s3:GetObject
s3:ListBucket
s3:PutObject
ec2:DescribeInstances
ec2:StartInstances
lambda:InvokeFunction
~~~

Phần trước dấu `:` là **service prefix**; phần sau là tên action theo IAM. Tên action thường gần với tên API nhưng không phải mọi thao tác ứng dụng đều ánh xạ một-một với tên API; tra **Service Authorization Reference** của dịch vụ để chọn đúng quyền.

`Action` có thể là chuỗi hoặc mảng:

~~~json
{
  "Effect": "Allow",
  "Action": [
    "s3:GetObject",
    "s3:GetObjectVersion"
  ],
  "Resource": "arn:aws:s3:::example-company-reports-2026/reports/*"
}
~~~

Statement trên là một **mảnh minh họa**, không phải policy đầy đủ vì chưa có `Version` và `Statement` bọc ngoài.

### 4.2. Ký tự đại diện trong Action

AWS hỗ trợ wildcard `*` và `?` trong nhiều vị trí của chuỗi action. Ví dụ:

- `s3:Get*`: có thể khớp nhiều thao tác bắt đầu bằng `Get` thuộc S3; tập action thực tế có thể rộng hơn dự kiến.
- `ec2:Describe*`: bao phủ nhiều thao tác mô tả EC2.
- `"*"`: mọi action của mọi dịch vụ mà policy có thể xét, nên rất rộng.

Không dùng wildcard chỉ vì muốn rút ngắn policy. Nếu chỉ đọc một loại dữ liệu, hãy liệt kê những action thật sự cần. `NotAction` có nghĩa “mọi action ngoại trừ những action nêu ra” trong phạm vi statement phù hợp; dễ vô tình mở rộng quyền và cần được đánh giá rất cẩn thận.

### 4.3. Một thao tác nghiệp vụ có thể cần nhiều action

Ví dụ, để hiển thị các tệp trong bucket rồi tải một tệp về, ứng dụng có thể cần:

1. `s3:ListBucket` để liệt kê tên object.
2. `s3:GetObject` để đọc nội dung object.

Hai action này dùng **loại ARN khác nhau**. Nếu object được mã hóa SSE-KMS bằng customer managed key, thao tác đọc còn có thể cần quyền KMS thích hợp và key policy phù hợp. Khi cấp quyền, phân tích toàn bộ đường đi thực tế thay vì chỉ nhìn tên API ở tầng ứng dụng.

## 5. Resource: thao tác đó tác động lên tài nguyên nào?

### 5.1. Đọc một ARN

ARN (**Amazon Resource Name**) định danh tài nguyên AWS. Dạng tổng quát thường gặp:

~~~text
arn:partition:service:region:account-id:resource
~~~

Ví dụ:

~~~text
arn:aws:ec2:ap-southeast-1:123456789012:instance/i-0123456789abcdef0
arn:aws:lambda:ap-southeast-1:123456789012:function:report-processor
arn:aws:s3:::example-company-reports-2026
arn:aws:s3:::example-company-reports-2026/reports/summary.csv
~~~

ARN của S3 không điền Region và account ID trong hai vị trí đó. Cách viết phần `resource` thay đổi theo dịch vụ: có nơi dùng dấu `/`, có nơi dùng dấu `:`; không nên tự suy ra ARN mà không kiểm tra tài liệu.

### 5.2. S3 bucket và S3 object là hai phạm vi khác nhau

| Quyền | Resource phù hợp | Ý nghĩa |
| --- | --- | --- |
| `s3:ListBucket` | `arn:aws:s3:::example-company-reports-2026` | Xem danh sách các object trong bucket |
| `s3:GetObject` | `arn:aws:s3:::example-company-reports-2026/reports/*` | Đọc object dưới prefix `reports/` |
| `s3:PutObject` | `arn:aws:s3:::example-company-reports-2026/uploads/*` | Tải object lên prefix `uploads/` |
| `ec2:StartInstances` | `arn:aws:ec2:ap-southeast-1:123456789012:instance/*` | Khởi động các instance khớp phạm vi ARN và điều kiện |

Vì `s3:ListBucket` nhắm đến **bucket**, gắn nó với ARN `.../reports/*` không cho phép liệt kê thư mục như kỳ vọng. Ngược lại, `s3:GetObject` nhắm đến **object**, không phải ARN bucket trần.

### 5.3. Resource `"*"` có luôn sai không?

Không. Một số IAM action **không hỗ trợ** giới hạn ở cấp tài nguyên cụ thể; khi cho phép action đó, `Resource` buộc phải là `"*"`. Ví dụ `ec2:DescribeInstances` thường được cấp trên `"*"`. Với action hỗ trợ resource-level permission, nên ưu tiên ARN cụ thể.

Một số action cần phân quyền nhiều loại tài nguyên trong cùng hoạt động, hoặc có condition key hỗ trợ khác nhau theo loại tài nguyên. Luôn đối chiếu bảng **Actions, resources, and condition keys** trong tài liệu ủy quyền của dịch vụ.

### 5.4. Wildcard trong Resource

`arn:aws:s3:::example-company-reports-2026/reports/*` bao phủ mọi object key bắt đầu bằng `reports/`, gồm cả các đường dẫn lồng nhau. S3 dùng **object key prefix**, không có hệ thống thư mục vật lý với quyền tự kế thừa như hệ thống tệp truyền thống.

Wildcard trong ARN của đối tượng cần được rà soát vì có thể bao trùm nhiều tài nguyên hơn dự định. `NotResource` đảo cách chọn tài nguyên và rất dễ gây phạm vi cấp quyền ngoài ý muốn nếu đặt cùng Allow; thường nên mô tả trực tiếp những ARN được phép.

## 6. Condition: chỉ cho phép khi ngữ cảnh đáp ứng điều kiện

`Condition` bổ sung các ràng buộc như “chỉ được khởi động EC2 mang tag `Environment=dev`” hoặc “chỉ được xử lý lệnh qua HTTPS”.

Một condition có cấu trúc:

~~~json
"Condition": {
  "StringEquals": {
    "ec2:ResourceTag/Environment": "dev"
  }
}
~~~

Trong đó:

- **Condition operator**: `StringEquals` xác định cách so sánh.
- **Condition key**: `ec2:ResourceTag/Environment` là thuộc tính của tài nguyên do EC2 cung cấp trong ngữ cảnh cho action phù hợp.
- **Value**: `"dev"` là giá trị yêu cầu.

### 6.1. Các nhóm toán tử hữu ích

| Toán tử ví dụ | Dùng cho | Ví dụ tình huống |
| --- | --- | --- |
| `StringEquals` | Chuỗi phải trùng giá trị | Môi trường có tag `dev` |
| `StringLike` | Chuỗi có thể chứa pattern `*`, `?` | Prefix object bắt đầu `reports/` |
| `Bool` | Điều kiện Boolean | Kiểm tra `aws:SecureTransport` |
| `IpAddress` | IPv4/IPv6 và CIDR phù hợp | Hạn chế theo địa chỉ IP nguồn ở trường hợp hỗ trợ |
| `NumericLessThanEquals` | So sánh số | Giới hạn tham số số của API có condition key tương ứng |
| `DateLessThan` | So sánh thời điểm | Quyền có thời hạn theo giá trị thời gian |
| `ArnEquals`, `ArnLike` | So sánh ARN | Giới hạn ARN nguồn trong resource-based policy |
| `Null` | Kiểm tra sự có mặt/vắng mặt của key | Yêu cầu request mang một thuộc tính |

AWS có **global condition keys** như `aws:RequestedRegion`, `aws:PrincipalTag/...`, `aws:SecureTransport`, và **service-specific condition keys** như `s3:prefix` hoặc `ec2:ResourceTag/...`. Không phải condition key nào cũng tồn tại cho mọi request/action.

### 6.2. Nhiều điều kiện phối hợp thế nào?

Với những toán tử khẳng định thông thường:

- **Các operator khác nhau** trong cùng `Condition` cần đồng thời thỏa.
- **Các condition key khác nhau** cùng toán tử cũng cần đồng thời thỏa.
- **Nhiều giá trị** dưới cùng một key thường là lựa chọn thay thế nhau, ví dụ một chuỗi khớp một trong hai prefix.

Ví dụ:

~~~json
"Condition": {
  "StringEquals": {
    "ec2:ResourceTag/Environment": "dev",
    "aws:RequestedRegion": "ap-southeast-1"
  }
}
~~~

Yêu cầu cần khớp **cả hai key**. Với toán tử phủ định, tập giá trị nhiều phần tử, hoặc các tiền tố `ForAnyValue:` và `ForAllValues:`, quy tắc đánh giá có khác biệt; không nên suy diễn chúng giống hoàn toàn quy tắc trên.

### 6.3. Điều gì xảy ra khi condition key vắng mặt?

Nhiều phép so sánh khẳng định như `StringEquals` không khớp nếu key cần kiểm tra vắng mặt. Tuy vậy, các toán tử có hậu tố `IfExists`, `Null` hoặc phép so sánh phủ định có quy tắc riêng. Đặc biệt, `...IfExists` trong một statement **Deny** có thể gây hiệu ứng khác trực giác.

Điều này quan trọng vì ngữ cảnh request có thể khác nhau giữa IAM user, role session, AWS service principal, yêu cầu qua VPC endpoint và truy cập từ Internet. Khi dùng điều kiện bảo mật, phải biết **dịch vụ/action có cung cấp key đó không** và kiểm tra các đường gọi thực tế.

### 6.4. Hai condition key hay bị hiểu sai

- `aws:RequestedRegion` xét **Region của endpoint được gọi** ở những request phù hợp; nó **không** tự bảo đảm dữ liệu hoặc mọi tác động của dịch vụ chỉ tồn tại trong Region đó. Một số dịch vụ toàn cầu cần xử lý riêng.
- `aws:MultiFactorAuthPresent` cần hiểu theo loại thông tin xác thực và phiên STS. Không thể chỉ thêm một điều kiện MFA rồi cho rằng mọi luồng đăng nhập qua federation hoặc mọi API key được kiểm soát đúng; cần xác định phương thức xác thực và test.

## 7. Ví dụ đầy đủ 1: chỉ đọc báo cáo trong một prefix S3

**Bài toán:** một ứng dụng báo cáo cần liệt kê và đọc object dưới `reports/`, nhưng không được tải lên, xóa hoặc xem object dưới `private/`.

**Identity-based policy:**

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListOnlyReportsPrefix",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::example-company-reports-2026",
      "Condition": {
        "StringLike": {
          "s3:prefix": [
            "reports/",
            "reports/*"
          ]
        }
      }
    },
    {
      "Sid": "ReadOnlyReportObjects",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::example-company-reports-2026/reports/*"
    }
  ]
}
~~~

**Phân tích:**

1. Statement `ListOnlyReportsPrefix` có `Action=s3:ListBucket`, `Resource` là ARN **bucket**, và `Condition` chỉ chấp nhận tham số prefix tương ứng.
2. Statement `ReadOnlyReportObjects` có `Action=s3:GetObject` trên ARN **object**, giới hạn đường dẫn `reports/*`.
3. Không có statement Allow cho `s3:PutObject`, `s3:DeleteObject` hoặc `s3:GetObject` tại `private/*`.
4. Nếu request không có prefix phù hợp, policy này không cấp quyền `ListBucket`; ứng dụng cần truyền prefix tương ứng khi gọi API liệt kê.

**Bảng tự kiểm tra (chỉ xét policy minh họa này):**

| Request | Kết quả theo các Allow trong policy | Giải thích |
| --- | --- | --- |
| `ListBucket` với `prefix=reports/` | Khớp Allow | Đúng ARN bucket và condition |
| `ListBucket` với `prefix=private/` | Không có Allow | Sai `s3:prefix` |
| `GetObject` trên `reports/summary.csv` | Khớp Allow | ARN object khớp `reports/*` |
| `GetObject` trên `private/payroll.csv` | Không có Allow | Object nằm ngoài phạm vi |
| `PutObject` vào `reports/new.csv` | Không có Allow | Action chưa được cấp |

“Khớp Allow” ở đây chưa chắc là kết quả cuối cùng của hệ thống: bucket policy, permission boundary, SCP, KMS key policy hoặc explicit Deny từ nơi khác vẫn có thể ảnh hưởng.

## 8. Ví dụ đầy đủ 2: chỉ khởi động EC2 trong môi trường dev

**Bài toán:** nhóm phát triển chỉ được bật các EC2 instance đã gắn tag `Environment=dev` ở Region Singapore, thuộc tài khoản minh họa `123456789012`.

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "StartDevInstancesInSingapore",
      "Effect": "Allow",
      "Action": "ec2:StartInstances",
      "Resource": "arn:aws:ec2:ap-southeast-1:123456789012:instance/*",
      "Condition": {
        "StringEquals": {
          "ec2:ResourceTag/Environment": "dev",
          "aws:RequestedRegion": "ap-southeast-1"
        }
      }
    }
  ]
}
~~~

Trong ví dụ này:

- **Action** là `ec2:StartInstances`; policy không cấp quyền dừng hay xóa instance.
- **Resource** bị giới hạn vào các EC2 instance của một Region và một account.
- **Condition** yêu cầu tag `Environment=dev`, đồng thời xét endpoint Region đã chỉ định.
- Nếu instance không có tag, hoặc tag mang giá trị khác, statement này không cấp quyền khởi động.

Tag là dữ liệu quản trị. **Nếu chính người dùng có quyền tự gắn/sửa tag**, họ có thể khiến một instance trước đó không khớp nay khớp policy. Vì vậy, kiến trúc phân quyền theo tag phải kiểm soát các quyền như `ec2:CreateTags` và `ec2:DeleteTags`, kể cả khi thao tác qua automation.

### 8.1. Mở rộng thành ABAC bằng tag

Trong **Attribute-Based Access Control (ABAC)**, thay vì viết policy riêng cho từng đội, có thể so sánh tag của principal với tag của tài nguyên.

Ví dụ phần Condition minh họa:

~~~json
"Condition": {
  "StringEquals": {
    "ec2:ResourceTag/Team": "${aws:PrincipalTag/Team}"
  }
}
~~~

`${aws:PrincipalTag/Team}` trong đoạn trên biểu thị **policy variable** `${aws:PrincipalTag/Team}`, được AWS thay bằng tag `Team` của principal trong ngữ cảnh thích hợp. Để tránh nhầm khi tái sử dụng, người học cần kiểm tra principal tag có được phát hành/kiểm soát đáng tin cậy hay không, condition key có được hỗ trợ cho action hay không và quyền chỉnh sửa tag có bị hạn chế không.

## 9. Ví dụ 3: explicit Deny trong bucket policy

Một **resource-based policy** có thể yêu cầu kết nối an toàn ngay cả khi principal có identity-based policy cho phép đọc object.

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyPlainHttpRequests",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": [
        "arn:aws:s3:::example-company-reports-2026",
        "arn:aws:s3:::example-company-reports-2026/*"
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

Ở đây:

- `Principal="*"` cho biết statement resource-based áp dụng với mọi principal phù hợp.
- `Effect="Deny"` chặn các request S3 khớp điều kiện vận chuyển không an toàn.
- Cả ARN bucket và object được đưa vào để phù hợp với các loại action khác nhau.
- Đây là **Deny**, không tự cấp quyền HTTPS. Request qua HTTPS vẫn cần một nguồn Allow hợp lệ và phải qua các kiểm tra khác.

Trong thực tế, một số cuộc gọi AWS service-to-service có thể không chuyển đầy đủ network context keys đến dịch vụ đích. Nếu bucket được AWS service khác truy cập, hãy đọc hướng dẫn chính thức về `aws:PrincipalIsAWSService`, kiểm tra các đường tích hợp và điều chỉnh điều kiện Deny phù hợp để tránh chặn dịch vụ ngoài ý muốn.

### 9.1. Vì sao `Principal` không có trong ví dụ 7 và 8?

Ví dụ 7 và 8 là **identity-based policies**, nên chủ thể áp dụng chính là danh tính được gắn policy. Chèn `Principal` vào loại policy đó không đúng cấu trúc.

Ngược lại, ví dụ 9 là **S3 bucket policy**, một loại **resource-based policy**; tại đây `Principal` giúp xác định những danh tính mà statement áp dụng.

## 10. Role trust policy: ai được đảm nhận role?

Một IAM role thường có ít nhất hai phần liên quan nhưng thực hiện hai chức năng khác nhau:

1. **Trust policy:** principal nào được gọi `sts:AssumeRole` (hoặc cơ chế liên quan) để đảm nhận role.
2. **Permissions policy:** khi phiên role hoạt động, nó được gọi action gì trên resource nào.

Ví dụ trust policy cho role thực thi Lambda:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowLambdaServiceToAssumeRole",
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

Trust policy là một dạng resource-based policy gắn với role, nên **không cần `Resource`** trong statement ví dụ: bản thân role chứa trust policy chính là tài nguyên được xác định. Policy này **không** cấp cho function quyền đọc S3, ghi DynamoDB hoặc gọi API khác; cần gắn permissions policy phù hợp với role.

Với trust policy cho tài khoản hoặc role bên ngoài, thường cần kiểm tra principal cụ thể và các điều kiện bổ sung như `sts:ExternalId` khi thích hợp. Không nên mở trust policy rộng thành mọi principal để “sửa lỗi AssumeRole”.

## 11. AWS đánh giá nhiều policy cùng lúc như thế nào?

Cách suy luận nền tảng:

1. **Mặc định bị từ chối** (*implicit deny*) nếu không có cơ sở Allow phù hợp.
2. Một **explicit Deny** khớp từ policy có hiệu lực sẽ từ chối yêu cầu, kể cả nơi khác có Allow.
3. Một hoặc nhiều Allow cần phù hợp action, resource và condition. Kết quả còn phụ thuộc các giới hạn và loại principal liên quan.

~~~mermaid
flowchart TD
    R["Yêu cầu: principal + action + resource + context"] --> D{"Có explicit Deny áp dụng?"}
    D -->|Có| NO["Deny"]
    D -->|Không| A{"Có Allow phù hợp?"}
    A -->|Không| NO
    A -->|Có| G{"Các giới hạn khác cho phép?"}
    G -->|Không| NO
    G -->|Có| YES["Allow"]
~~~

**Sơ đồ là mô hình tư duy rút gọn**, không thay thế thuật toán đánh giá chính thức của IAM. Các chi tiết có thể khác theo loại policy, principal, phiên role và việc truy cập cùng tài khoản hay khác tài khoản. Ví dụ, quan hệ giữa resource-based policy và permissions boundary có trường hợp đặc biệt; cần tra tài liệu trước khi kết luận một cấu hình cụ thể.

### 11.1. Ghép các ràng buộc khi thiết kế hệ thống

Giả sử một role có:

- Identity policy cấp `s3:GetObject` ở `reports/*`.
- Một SCP giới hạn các dịch vụ được dùng trong tài khoản.
- Một permissions boundary giới hạn quyền của role.
- Một S3 bucket policy có explicit Deny khi request không đáp ứng điều kiện vận chuyển an toàn.

Một request đọc báo cáo chỉ có thể thành công khi **không bị Deny**, có cấp quyền phù hợp và vượt qua các giới hạn đang áp dụng. SCP và permissions boundary **không tự cấp Allow**. Việc có identity-based Allow cũng không bỏ qua mọi điều kiện từ bucket policy.

Đối với yêu cầu từ **cross-account**, phải xem cả chính sách của bên gọi và bên tài nguyên, cùng trust/assume-role nếu có. Một Allow của tài khoản bên gọi không mặc nhiên mở tài nguyên ở tài khoản khác.

## 12. Quy trình viết policy theo least privilege

Thực hành hữu ích là đi từ **thao tác nghiệp vụ thật** đến policy, không bắt đầu bằng `Action="*"`.

1. **Xác định principal:** role nào chạy ứng dụng? Người dùng, CI/CD, EC2 hay Lambda đảm nhận role bằng cách nào?
2. **Liệt kê API cần gọi:** ghi lại hành động cụ thể từ SDK, CloudTrail hoặc yêu cầu dịch vụ. Phân biệt hành động đọc, ghi, quản trị.
3. **Chọn Resource:** dùng ARN hẹp nhất nếu action hỗ trợ; biết lúc nào buộc dùng `"*"`.
4. **Thêm Condition:** chỉ thêm các key được action hỗ trợ và có giá trị đáng tin cậy trong request context.
5. **Tách statement:** khi các action đòi loại ARN hoặc condition khác nhau, tách chúng ra để tránh phạm vi sai.
6. **Kiểm tra các policy liên quan:** role trust, resource policy, KMS key policy, SCP, permissions boundary và session policy.
7. **Xác thực và thử nghiệm:** dùng IAM Access Analyzer, simulator, API thực tế trong môi trường thử, CloudTrail và theo dõi yêu cầu bị từ chối.
8. **Rà soát định kỳ:** bỏ quyền không còn dùng, kiểm soát quyền sửa tag/role/policy, tránh cấp quyền tồn tại vĩnh viễn khi chỉ cần theo phiên.

### 12.1. Công cụ hỗ trợ

**IAM Access Analyzer policy validation** giúp nhận diện lỗi cấu trúc, cảnh báo bảo mật và gợi ý cải thiện. Ví dụ giả sử bạn lưu identity policy trong `policy.json`:

~~~bash
aws accessanalyzer validate-policy \
  --region ap-southeast-1 \
  --policy-type IDENTITY_POLICY \
  --policy-document file://policy.json
~~~

**IAM Policy Simulator** có thể kiểm tra một số tổ hợp principal/action/resource. Ví dụ với role minh họa:

~~~bash
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::123456789012:role/ReportReader \
  --action-names s3:GetObject \
  --resource-arns arn:aws:s3:::example-company-reports-2026/reports/summary.csv
~~~

Các lệnh trên chỉ dùng để kiểm tra; yêu cầu AWS CLI có credentials và quyền phù hợp. Cần thay ARN, tên file và Region cho môi trường thật. **Simulator có giới hạn** và không mô phỏng đầy đủ mọi loại policy/điều kiện hoặc hành vi dịch vụ; kết quả mô phỏng không thay thế kiểm thử truy cập thực tế.

Khi request thật bị từ chối, hãy xem **action chính xác**, ARN, condition key có hiện diện hay không, thông báo lỗi và các sự kiện liên quan trong **AWS CloudTrail**. CloudTrail giúp điều tra nhưng không nên mặc định mọi loại request hay mọi thao tác dữ liệu đều được ghi sẵn; cần cấu hình event logging tương ứng.

## 13. Lỗi thường gặp và cách sửa

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Đã Allow `s3:ListBucket` nhưng không thấy tệp | Dùng object ARN thay vì bucket ARN; `s3:prefix` không khớp | Kiểm tra ARN bucket và tham số prefix của request |
| Đã Allow `s3:GetObject` mà vẫn `AccessDenied` | Bucket/key policy Deny; SSE-KMS thiếu quyền; sai object ARN | Xem tất cả policy, quyền KMS, encryption và log |
| Policy `StartInstances` không hoạt động | Instance không có tag dev, sai account hoặc Region | Đối chiếu resource ARN, action và condition key |
| Thêm `Principal` vào identity policy rồi lỗi validation | `Principal` chỉ dùng trong loại policy phù hợp | Gỡ `Principal` khỏi identity-based policy |
| Dùng `Action="s3:*"` để “chỉ đọc S3” | Wildcard cấp cả thao tác ghi/quản trị có thể phù hợp | Thay bằng các action đọc cần thiết |
| Thêm `Allow` mới nhưng vẫn bị Deny | Có explicit Deny hoặc giới hạn tổ chức/boundary | Truy nguyên nơi Deny/giới hạn đang áp dụng |
| Role không được sử dụng bởi Lambda | Trust policy không cho service principal đảm nhận role | Kiểm tra trust policy và vai trò execution role |
| Giới hạn theo tag nhưng người dùng tự thay tag được | Quyền quản trị tag quá rộng | Giới hạn sửa tag và bảo vệ các tag phân quyền |
| Dùng `aws:SourceIp` để chặn mọi truy cập ngoài văn phòng | Network context có thể khác khi dùng proxy, VPC endpoint hoặc AWS service | Kiểm tra các đường truy cập và condition key thực tế |

## 14. Bài thực hành suy luận policy

### Bài tập A — điền ba mảnh còn thiếu

Ứng dụng xử lý hóa đơn phải **chỉ tải lên** object ở prefix `invoices/incoming/` của bucket `example-invoice-store-2026`. Hãy xác định:

1. `Action` cần dùng là gì?
2. `Resource` nên là ARN bucket hay ARN object?
3. Nếu muốn chỉ cho phép các yêu cầu từ một VPC endpoint được chỉ định, có thể nghiên cứu condition key nào? Trong trường hợp nào key đó có thể không xuất hiện?

**Đáp án gợi ý:** `s3:PutObject`; `arn:aws:s3:::example-invoice-store-2026/invoices/incoming/*`; xem `aws:SourceVpce` cho đường truy cập S3 qua VPC endpoint phù hợp, đồng thời kiểm tra các yêu cầu không đi qua endpoint. Đừng dùng điều kiện này một cách máy móc cho mọi đường tích hợp.

### Bài tập B — giải thích kết quả

Cho hai statement áp dụng đến cùng một object:

~~~json
[
  {
    "Effect": "Allow",
    "Action": "s3:GetObject",
    "Resource": "arn:aws:s3:::example-company-reports-2026/reports/*"
  },
  {
    "Effect": "Deny",
    "Action": "s3:GetObject",
    "Resource": "arn:aws:s3:::example-company-reports-2026/reports/secret/*"
  }
]
~~~

Giả sử không có policy nào khác ảnh hưởng, hãy suy luận:

- Đọc `reports/summary.csv`: **Allow**, vì statement Allow khớp và không có Deny phù hợp.
- Đọc `reports/secret/finance.csv`: **Deny**, vì statement Deny có hiệu lực dù Allow cũng khớp.
- Ghi `reports/summary.csv`: **implicit Deny**, do không có Allow cho `s3:PutObject`.

### Bài tập C — thiết kế cho hệ thống thực tế

Một dịch vụ Lambda nhận yêu cầu API và ghi ảnh do người dùng tải lên S3; một nhóm quản trị cần xem log nhưng không được đọc ảnh riêng tư. Hãy:

1. Vẽ luồng principal: ai assume execution role của Lambda, ai gọi API, ai đọc CloudWatch Logs?
2. Đề xuất **hai policy khác nhau** cho role ứng dụng và role hỗ trợ vận hành.
3. Chỉ rõ `Action`, `Resource`, `Condition` cần giới hạn và những trường hợp phải dùng ARN pattern.
4. Thử nghĩ một đường thoát quyền: nếu nhóm vận hành được sửa policy của chính role, họ có thể vượt qua giới hạn “chỉ xem log” bằng cách nào? Quyền quản trị IAM nào cần kiểm soát?

## 15. Ghi nhớ

Một statement IAM trả lời ba câu hỏi chính:

- **`Action`:** thao tác nào?
- **`Resource`:** trên đối tượng nào?
- **`Condition`:** chỉ trong ngữ cảnh nào?

`Effect` xác định Allow hay Deny; loại policy xác định phạm vi áp dụng và việc có cần `Principal` hay không. **Least privilege** đạt được khi cả action, resource, condition và quyền sửa chính sách đều được giới hạn đúng nhu cầu, sau đó kiểm chứng bằng công cụ và hành vi thực tế.

### Tài liệu AWS chính thức

- [IAM JSON policy elements reference](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements.html) — cấu trúc, `Action`, `Resource`, `Condition` và các phần tử liên quan.
- [IAM JSON policy elements: Action](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_action.html) — cách chỉ định action.
- [IAM JSON policy elements: Resource](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_resource.html) — resource ARN và wildcard.
- [IAM JSON policy elements: Condition](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_condition.html) — condition operators, keys và giá trị.
- [Policy evaluation logic](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html) — cách phối hợp policy, boundary, SCP và Deny.
- [Actions, resources, and condition keys for AWS services](https://docs.aws.amazon.com/service-authorization/latest/reference/reference.html) — tra quyền theo từng dịch vụ/API.
- [IAM Access Analyzer policy validation](https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-policy-validation.html) — kiểm tra cấu trúc và cảnh báo policy.
