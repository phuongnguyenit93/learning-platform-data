# Mã hóa S3 và quyền sử dụng KMS key

## Mục tiêu học tập

Hoàn thành bài này, người học có thể:

- Phân biệt **SSE-S3, SSE-KMS, DSSE-KMS, SSE-C** và **mã hóa phía client**; chọn chế độ theo yêu cầu bảo mật, kiểm soát khóa, vận hành và chi phí.
- Giải thích **envelope encryption**, vai trò của **AWS Key Management Service (AWS KMS)**, **data key**, **KMS key** và **encryption context** khi Amazon S3 mã hóa/giải mã đối tượng.
- Xác định các lớp quyền cần thiết: **IAM identity policy**, **S3 bucket/access point policy**, **KMS key policy/grants**, các giới hạn của **SCP**, VPC endpoint policy và các **explicit Deny**.
- Cấu hình mã hóa mặc định của bucket, tải/đọc đối tượng SSE-KMS bằng AWS CLI, xem metadata, giám sát và điều tra lỗi.
- Phân tích vấn đề **truy cập cross-account**, **AWS managed key so với customer managed key**, **S3 Bucket Keys**, **replication/copy**, **multipart upload**, key rotation và các trường hợp gây lỗi `AccessDenied`.
- Đề xuất phương án mã hóa cho ứng dụng trên **EC2/ECS/Lambda**, nơi **IAM, VPC, Region/AZ, khả năng phục hồi, giám sát và chi phí** phải được xem xét cùng nhau.

**Bối cảnh:** Bài thuộc chương **Lưu trữ đối tượng S3** của module **CLOUD_PROVIDERS_AWS**. Trong một hệ thống AWS, S3 thường lưu ảnh sản phẩm, tài liệu hóa đơn, nhật ký, dữ liệu phân tích và bản sao lưu. Mã hóa dữ liệu lưu trữ là một phần của việc thiết kế ứng dụng an toàn; **mã hóa không tự cấp quyền truy cập và không thay thế IAM, mạng, phiên bản dữ liệu, backup hay monitoring**.

> **Giả định:** Ví dụ chủ yếu dùng **S3 general purpose bucket** trong cùng Region với KMS key. Một số đặc tính của **directory bucket/S3 Express One Zone**, kết nối cross-account hoặc tính năng mới có quy tắc riêng. Khi áp dụng thực tế cần đối chiếu tài liệu AWS cho loại bucket, Region và API đang sử dụng.

## 1. Tách ba câu hỏi: dữ liệu có được mã hóa, ai đọc được và khóa do ai quản lý?

Với một đối tượng S3, có ba vấn đề khác nhau:

1. **Encryption at rest:** Nội dung object được bảo vệ thế nào khi lưu trong hạ tầng S3?
2. **Authorization:** Principal nào được phép `PutObject`, `GetObject`, `ListBucket`, `DeleteObject`?
3. **Key authorization/management:** Khi dùng SSE-KMS hoặc DSSE-KMS, principal nào được phép dùng **KMS key** để tạo data key, giải mã, chia sẻ và kiểm toán?

Ví dụ công ty lưu file `invoices/2026/order-1001.pdf` trong S3:

- Bucket cho phép role của một Lambda đọc file bằng `s3:GetObject`.
- Object dùng **SSE-KMS** với customer managed KMS key.
- Role Lambda thiếu `kms:Decrypt` hoặc key policy không cho phép role sử dụng khóa.
- Kết quả: việc gọi `GetObject` **có thể bị AccessDenied dù quyền S3 đúng**.

Ngược lại, cấp `kms:Decrypt` không có nghĩa role tự động có quyền `s3:GetObject`. Hai lớp quyền này kiểm soát hai hành động khác nhau.

~~~mermaid
flowchart LR
  A[Ứng dụng với IAM role] --> B{S3 có cho GetObject?}
  B -->|Không| E[AccessDenied]
  B -->|Có| C{Object dùng SSE-KMS?}
  C -->|Không| D[S3 trả object theo quyền hợp lệ]
  C -->|Có| K{KMS cho quyền Decrypt trên key?}
  K -->|Không| E
  K -->|Có| D
~~~

Sơ đồ là mô hình đơn giản để học; quyết định thực tế còn có **bucket policy Deny, SCP, permissions boundary, session policy, key policy, grants, VPC endpoint policy** và điều kiện theo request.

### Mã hóa khác kiểm soát truy cập ở đâu?

| Cơ chế | Tác dụng | Không tự đảm bảo |
| --- | --- | --- |
| **SSE-S3/SSE-KMS/DSSE-KMS** | Bảo vệ dữ liệu lưu trữ theo chế độ mã hóa S3 | Ai được quyền S3, TLS, application authentication |
| **IAM và bucket policy** | Cho hoặc từ chối các API S3 của principal | KMS key sử dụng được khi SSE-KMS |
| **KMS key policy/IAM/grants** | Kiểm soát việc dùng khóa KMS | Caller có quyền truy cập object S3 |
| **TLS + bucket policy về HTTPS** | Bảo vệ đường truyền và bắt buộc cách kết nối phù hợp | Bảo đảm object vẫn có thể khôi phục sau xóa |
| **Versioning/Object Lock/backup** | Giảm rủi ro xóa nhầm, sửa dữ liệu và hỗ trợ phục hồi theo cấu hình | Quyền truy cập dữ liệu hoặc mã hóa đang đúng |

## 2. Các chế độ mã hóa đối tượng S3

Tất cả object **mới tải lên S3** mặc định được mã hóa phía server bằng **SSE-S3** nếu không có cấu hình/chỉ định khác. Đây là hành vi mặc định của S3 từ năm 2023. Người dùng có thể yêu cầu chế độ mã hóa mạnh hơn về khả năng quản trị khóa theo nhu cầu.

| Chế độ | Ai quản lý vật liệu khóa liên quan? | Khi chọn | Quyền bổ sung phía client |
| --- | --- | --- | --- |
| **SSE-S3** | Amazon S3 quản lý khóa mã hóa dịch vụ | Phần lớn dữ liệu cần encryption at rest tiêu chuẩn, tối giản vận hành | Quyền S3 phù hợp; thường không cần quyền AWS KMS riêng |
| **SSE-KMS** | AWS KMS quản lý KMS key, có **AWS managed key** hoặc **customer managed key** | Cần kiểm soát quyền dùng khóa, audit sử dụng khóa, chính sách key/rotation, truy cập liên tài khoản | Cần quyền S3 **và** quyền KMS thích hợp |
| **DSSE-KMS** | Hai lớp mã hóa phía server, một lớp sử dụng AWS KMS | Trường hợp yêu cầu bổ sung về mã hóa hai lớp theo chính sách/tính năng hỗ trợ | Quyền S3/KMS phù hợp; kiểm tra hạn chế và giá riêng |
| **SSE-C** | Client cung cấp khóa mã hóa cho mỗi yêu cầu; S3 không lưu khóa được cung cấp | Nhu cầu tương thích/chính sách đặc biệt, quản lý khóa hoàn toàn phía client | Client phải cung cấp khóa đúng khi đọc; không dùng KMS key theo mô hình SSE-KMS |
| **Client-side encryption** | Ứng dụng mã hóa trước khi upload; quản trị khóa theo giải pháp của client | Muốn S3 chỉ lưu ciphertext do ứng dụng tạo | Client cần giải mã sau khi tải; có thể kết hợp SSE phía server |

**SSE** là viết tắt của *Server-Side Encryption*. Trong các trường hợp SSE, S3 xử lý mã hóa trước khi ghi dữ liệu lưu trữ và giải mã theo quy trình hợp lệ khi trả object.

### 2.1. SSE-S3: mặc định đơn giản

Với SSE-S3, S3 dùng thuật toán mã hóa mạnh do AWS hỗ trợ (chẳng hạn AES-256) và tự quản lý khóa/luồng mã hóa; ứng dụng không phải tạo một customer managed KMS key.

Phù hợp khi:

- Cần encryption at rest mà không có yêu cầu policy/quyền riêng trên KMS key.
- Khối lượng object/request rất lớn và muốn giảm quản trị KMS.
- Dữ liệu nội bộ hoặc không nhạy cảm ở mức phải có key policy riêng.

SSE-S3 **không có nghĩa object công khai**: đọc/ghi vẫn do IAM, bucket policy, Block Public Access và các lớp bảo mật S3 quyết định.

### 2.2. SSE-KMS: tách quyền S3 và quyền KMS

Với SSE-KMS, bạn chỉ định một **AWS KMS key** trong cùng Region phù hợp. AWS KMS có thể:

- **AWS managed key** có alias như `aws/s3`: AWS tạo/quản lý chính sách key cho tích hợp; bạn không tự sửa key policy để cấp cross-account tùy ý.
- **Customer managed key**: bạn tạo/kiểm soát key policy, lifecycle, rotation phù hợp, tags và truy cập liên tài khoản.

**Nếu cần cho principal ở tài khoản AWS khác đọc/ghi object SSE-KMS, thường phải dùng customer managed KMS key có key policy phù hợp.** Chỉ mở bucket policy chưa đủ khi khóa là `aws/s3` do AWS quản lý.

Một trường hợp phổ biến: role ECS ghi object bằng SSE-KMS với customer managed key; role Lambda ở account khác cần đọc object đó và phải được cấp quyền cả ở **bucket/object** và **KMS key**.

### 2.3. DSSE-KMS: mã hóa phía server hai lớp

**Dual-Layer Server-Side Encryption with AWS KMS keys (DSSE-KMS)** cung cấp hai lớp mã hóa độc lập do S3 áp dụng, với một lớp tích hợp AWS KMS. Chế độ này được sử dụng khi yêu cầu kiểm soát/tuân thủ về mã hóa hai lớp phù hợp với loại object và dịch vụ.

Điểm cần lưu ý:

- Không phải chỉ bật SSE-KMS là tự có hai lớp DSSE-KMS.
- **S3 Bucket Keys không được hỗ trợ với DSSE-KMS**; nếu đang tối ưu KMS request bằng Bucket Keys, phải đánh giá lại chi phí.
- Một số tích hợp/tính năng S3 có giới hạn hỗ trợ riêng; kiểm tra trước khi dùng replication, copy hoặc analytics.
- DSSE-KMS không thay thế phân quyền IAM, key policy, TLS hay khóa ứng dụng.

### 2.4. SSE-C và mã hóa phía client

Với **SSE-C**, mỗi yêu cầu cần khóa do khách hàng cung cấp cho S3 theo giao thức được hỗ trợ. Khi đọc object, client phải xuất trình đúng khóa; mất khóa có thể đồng nghĩa mất khả năng đọc dữ liệu. Tránh gửi khóa qua log, URL, header bị ghi lại hoặc kênh không an toàn.

Với **client-side encryption**, ứng dụng mã hóa dữ liệu **trước** khi gửi lên S3. S3 thấy ciphertext; muốn đọc nội dung cần giải mã theo cơ chế của ứng dụng hoặc AWS Encryption SDK/S3 Encryption Client thích hợp. Kịch bản này phức tạp hơn về quản lý khóa, metadata, re-encryption và khả năng chia sẻ.

**Quyết định thực tế:** Nếu chỉ cần mã hóa tiêu chuẩn, bắt đầu từ SSE-S3. Nếu cần **quản trị key policy, audit hoặc cross-account trên KMS**, xem SSE-KMS với customer managed key. Nếu tổ chức bắt buộc hai lớp, đánh giá DSSE-KMS. Không chọn SSE-C/client-side tùy hứng vì chúng chuyển đáng kể trách nhiệm quản lý khóa sang ứng dụng.

## 3. Envelope encryption: S3 dùng KMS key như thế nào?

**Envelope encryption** giúp mã hóa dữ liệu lớn bằng một **data key**, còn KMS key bảo vệ data key đó. Với SSE-KMS, S3 tích hợp AWS KMS để tạo/sử dụng data key phục vụ mã hóa object.

Mô hình khái niệm:

~~~mermaid
sequenceDiagram
    participant App as App IAM role
    participant S3 as Amazon S3
    participant KMS as AWS KMS
    participant Store as S3 encrypted object storage

    App->>S3: PutObject (SSE-KMS, KMS key)
    S3->>KMS: GenerateDataKey (theo quyền/điều kiện phù hợp)
    KMS-->>S3: Data key plaintext + data key mã hóa
    Note over S3: Dùng plaintext data key trong bộ nhớ để mã hóa object
    S3->>Store: Lưu ciphertext + metadata/khóa đã bọc
    S3-->>App: Thành công

    App->>S3: GetObject
    S3->>KMS: Decrypt data key theo key và context hợp lệ
    KMS-->>S3: Data key để giải mã
    S3->>Store: Đọc ciphertext
    S3-->>App: Nội dung object sau giải mã
~~~

Sơ đồ minh họa luồng chính; **S3 Bucket Keys và tối ưu tích hợp KMS** có thể làm giảm số yêu cầu KMS và thay đổi cách data key được sử dụng nội bộ. Đừng dựa vào sơ đồ để dự đoán chính xác mỗi `PutObject` hay `GetObject` luôn tương ứng một lời gọi KMS.

### Các thành phần chính

| Thành phần | Vai trò |
| --- | --- |
| **KMS key** | Khóa logic trong AWS KMS dùng bảo vệ/kiểm soát sử dụng khóa; có key ID/ARN, policy và lifecycle |
| **Data key** | Khóa dữ liệu dùng mã hóa nội dung object tại S3 |
| **Encrypted data key** | Bản data key được bảo vệ bằng KMS key và gắn với dữ liệu/metadata cần thiết |
| **Encryption context** | Cặp khóa–giá trị không bí mật ràng buộc thao tác KMS với ngữ cảnh mã hóa |
| **KMS key policy** | Chính sách tài nguyên quyết định principal/quyền dùng key |
| **IAM identity policy / grant** | Các con đường bổ sung cho phép hành động KMS trong giới hạn key policy và các lớp kiểm soát |

**Không nên nghĩ rằng dữ liệu cả object được gửi sang dịch vụ KMS để KMS mã hóa từng byte.** AWS KMS chủ yếu bảo vệ những khóa dữ liệu nhỏ trong quy trình này; S3 thực hiện mã hóa nội dung object.

### Region của KMS key

KMS key dùng cho **SSE-KMS của S3 object** phải thuộc **cùng AWS Region** với bucket nơi S3 mã hóa object. Khi **copy/replicate sang Region khác**, cần chọn key thích hợp tại Region đích nếu dùng SSE-KMS tại đích. Đừng dùng một ARN khóa Region A cho bucket nằm ở Region B rồi kỳ vọng S3 tự chuyển.

## 4. Bucket default encryption và mã hóa yêu cầu riêng

S3 có **default encryption configuration** ở cấp bucket. Khi object được tải lên mà client **không yêu cầu một chế độ khác**, cấu hình mặc định của bucket được áp dụng.

Ví dụ:

~~~text
Bucket: invoice-data-demo
Region: ap-southeast-1
Default encryption: SSE-KMS
KMS key: arn:aws:kms:ap-southeast-1:111122223333:key/12345678-1234-1234-1234-1234567890ab
Bucket Key: enabled
~~~

Nếu client upload object mới mà không gửi header chọn mã hóa, bucket sẽ áp dụng SSE-KMS theo cấu hình. Tuy nhiên:

- **Default encryption không tự ghi đè mọi yêu cầu mã hóa do client chỉ định**; cần hiểu tương tác với chế độ được yêu cầu và quyền S3/KMS.
- **Đổi cấu hình default encryption không tự mã hóa lại các object đã tồn tại**. Để đổi chế độ/khóa của dữ liệu cũ, cần lên kế hoạch copy/Batch Operations hoặc workflow re-encryption phù hợp.
- **Default encryption không phải bucket policy.** Nó nói S3 mã hóa thế nào khi ghi, còn policy nói principal nào được phép gọi API và điều kiện nào phải được đáp ứng.
- Khi bắt buộc đối tượng phải dùng **một key cụ thể**, cần phối hợp cấu hình bucket, quyền key, policy và quy trình upload theo cơ chế được hỗ trợ.

### Xem cấu hình hiện tại bằng CLI

~~~bash
aws sts get-caller-identity --profile lab

aws s3api get-bucket-encryption \
  --bucket invoice-data-demo \
  --profile lab \
  --region ap-southeast-1
~~~

Kết quả minh họa:

~~~json
{
  "ServerSideEncryptionConfiguration": {
    "Rules": [
      {
        "ApplyServerSideEncryptionByDefault": {
          "SSEAlgorithm": "aws:kms",
          "KMSMasterKeyID": "arn:aws:kms:ap-southeast-1:111122223333:key/12345678-1234-1234-1234-1234567890ab"
        },
        "BucketKeyEnabled": true
      }
    ]
  }
}
~~~

**Các tên bucket, account, key ID đều là ví dụ**; muốn chạy CLI phải thay bằng tài nguyên thật được cấp quyền.

### Cấu hình default SSE-KMS

Trong **S3 Console → Bucket → Properties → Default encryption**, chọn **SSE-KMS**, KMS key phù hợp và tùy chọn **S3 Bucket Key** nếu được hỗ trợ và có lợi cho workload.

Một ví dụ qua AWS CLI, với file cấu hình JSON **do người thực hành tạo riêng trong môi trường lab**:

~~~json
{
  "Rules": [
    {
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "aws:kms",
        "KMSMasterKeyID": "arn:aws:kms:ap-southeast-1:111122223333:key/12345678-1234-1234-1234-1234567890ab"
      },
      "BucketKeyEnabled": true
    }
  ]
}
~~~

Sau khi lưu nội dung trên thành `bucket-encryption.json`:

~~~bash
aws s3api put-bucket-encryption \
  --bucket invoice-data-demo \
  --server-side-encryption-configuration file://bucket-encryption.json \
  --region ap-southeast-1 \
  --profile lab
~~~

Để cấu hình này, principal quản trị cần các quyền S3 cấu hình bucket tương ứng và **quyền liên quan tới KMS key** theo trường hợp. Xác minh quyền, ARN key, bucket Region và chính sách theo quy trình của tài khoản trước khi chạy.

**Lưu ý:** Về cơ bản, AWS S3 tự mã hóa object mới theo SSE-S3 từ năm 2023 ngay cả khi bạn chưa tự cấu hình một rule mặc định tùy chỉnh. Đừng hiểu thiếu custom SSE-KMS default rule là dữ liệu lưu trữ plaintext.

## 5. Phân quyền SSE-KMS: ba lớp cần đọc cùng nhau

Đối với SSE-KMS, một đường truy cập thành công thường liên quan:

1. **S3 access:** IAM identity policy và/hoặc bucket/access point policy cho phép `s3:PutObject`, `s3:GetObject` trên resource được yêu cầu. Có thể bị chặn bởi Block Public Access, explicit Deny, SCP, permissions boundary, session policy và VPC endpoint policy.
2. **KMS authorization:** KMS key policy phải cho phép việc dùng key **trực tiếp** hoặc **cho phép IAM policy trong tài khoản cấp quyền**; grants có thể được sử dụng trong tình huống thích hợp. Với truy cập **khác tài khoản**, key policy của chủ khóa và IAM policy ở phía caller thường phải cùng cho phép.
3. **Request context:** KMS key phải enabled/usable, đúng Region, đúng kiểu key và các điều kiện như `kms:ViaService`, encryption context phải khớp. Với luồng dịch vụ, S3 sử dụng key thông qua tích hợp AWS KMS theo quyền của caller và ngữ cảnh được hỗ trợ.

~~~mermaid
flowchart TD
    A[Role/Principal gọi S3 API] --> B{S3 authorization}
    B -->|Deny| X[AccessDenied]
    B -->|Allow| C{Object cần thao tác KMS?}
    C -->|Không| Z[Thực hiện thao tác S3]
    C -->|Có| D{KMS key policy + IAM/grant + conditions}
    D -->|Deny| X
    D -->|Allow| Z
~~~

### KMS permissions thường gặp

| Thao tác S3 | Quyền S3 cần xét | KMS permission thường cần xét |
| --- | --- | --- |
| **PutObject dùng SSE-KMS** | `s3:PutObject` | `kms:GenerateDataKey` |
| **GetObject dùng SSE-KMS** | `s3:GetObject` | `kms:Decrypt` |
| **Multipart upload dùng SSE-KMS** | `s3:PutObject`, quyền bổ sung tùy cách upload | `kms:GenerateDataKey` và trong một số giai đoạn `kms:Decrypt` |
| **CopyObject: nguồn SSE-KMS** | Đọc object nguồn và ghi object đích theo policy | `kms:Decrypt` với key nguồn; quyền phù hợp trên key đích nếu mã hóa đích |
| **Upload/Copy sang SSE-KMS đích** | Quyền ghi object đích | `kms:GenerateDataKey` trên key đích, có thể quyền bổ sung theo workflow |
| **HeadObject (metadata cơ bản)** | `s3:GetObject` hoặc quyền phù hợp theo API | Thường không cần giải mã nội dung; **một số tùy chọn checksum/đặc tính API** có thể đòi KMS permission |
| **ListBucket** | `s3:ListBucket` | Không cần `kms:Decrypt` chỉ để liệt kê tên object |

Bảng mô tả **quyền thường gặp**, không phải bản sao mọi điều kiện API. Với **multipart upload**, copy, replication, Bucket Keys, checksum hoặc tính năng chuyên biệt, kiểm tra quyền bắt buộc trong tài liệu của API tương ứng.

### Tại sao thêm IAM `kms:Decrypt` vẫn chưa đủ?

Một KMS key policy có thể **không cho phép** role dùng key hoặc không cho IAM policy của account đó cấp quyền; key còn có thể bị disabled/pending deletion hay có điều kiện sai. Điều này tạo ra `AccessDenied` ở tầng KMS dù IAM role có `kms:Decrypt` và S3 bucket cho `GetObject`.

Đồng thời, **IAM role trust policy** là một vấn đề khác: nó quyết định ai được assume role. Role assume thành công không suy ra các API S3/KMS được cho phép.

## 6. Ví dụ đầy đủ: role đọc/ghi object SSE-KMS trong cùng account

**Bài toán:** Tài khoản `111122223333`, Region `ap-southeast-1`, bucket `invoice-data-demo`, customer managed KMS key có ARN minh họa:

~~~text
arn:aws:kms:ap-southeast-1:111122223333:key/12345678-1234-1234-1234-1234567890ab
~~~

Role `InvoiceWorkerRole` của Lambda hoặc ECS cần:

- Tải object mới vào `invoices/` bằng SSE-KMS.
- Đọc object dưới `invoices/`.
- Không xóa bucket, sửa bucket policy hay quản trị key.

### 6.1. Identity-based policy gắn vào role

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadWriteInvoiceObjects",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::invoice-data-demo/invoices/*"
    },
    {
      "Sid": "UseInvoiceKMSKey",
      "Effect": "Allow",
      "Action": [
        "kms:GenerateDataKey",
        "kms:Decrypt",
        "kms:DescribeKey"
      ],
      "Resource": "arn:aws:kms:ap-southeast-1:111122223333:key/12345678-1234-1234-1234-1234567890ab"
    }
  ]
}
~~~

**Giải thích:**

- `s3:GetObject` và `s3:PutObject` chỉ áp dụng object dưới prefix `invoices/`.
- `kms:GenerateDataKey` cho phép workflow tạo data key để ghi object SSE-KMS.
- `kms:Decrypt` hỗ trợ đọc object và các workflow như multipart khi cần.
- `kms:DescribeKey` không thay thế quyền encrypt/decrypt; hữu ích cho một số thao tác xác minh.
- Policy không cấp `s3:DeleteObject`, quyền quản lý bucket hay thay key policy.

Nếu ứng dụng cần **list prefix**, phải cấp thêm `s3:ListBucket` trên **bucket ARN**, thường giới hạn prefix bằng condition `s3:prefix`. Không thêm hành động `ListBucket` trên object ARN rồi kỳ vọng hoạt động.

### 6.2. KMS key policy cho phép role dùng khóa

Ví dụ statement đặt trong **key policy** của đúng customer managed KMS key (không phải bucket policy):

~~~json
{
  "Sid": "AllowInvoiceWorkerUseFromS3",
  "Effect": "Allow",
  "Principal": {
    "AWS": "arn:aws:iam::111122223333:role/InvoiceWorkerRole"
  },
  "Action": [
    "kms:GenerateDataKey",
    "kms:Decrypt",
    "kms:DescribeKey"
  ],
  "Resource": "*",
  "Condition": {
    "StringEquals": {
      "kms:ViaService": "s3.ap-southeast-1.amazonaws.com"
    }
  }
}
~~~

Đây là **một statement** để tích hợp vào key policy hợp lệ đang có, **không phải toàn bộ key policy hoàn chỉnh**. KMS key policy cần giữ quyền quản trị và cơ chế phục hồi khóa phù hợp. Trong key policy, `Resource: "*"` biểu thị khóa mà policy đang gắn lên; không có nghĩa cấp quyền cho mọi KMS key của tài khoản.

**Điều kiện `kms:ViaService`:** giới hạn việc sử dụng KMS key thông qua dịch vụ S3 tại Region được chỉ định theo luồng hỗ trợ. Kết hợp điều kiện này với role ARN chính xác giúp hạn chế cách dùng key. Không áp dụng máy móc vào một thao tác KMS trực tiếp của ứng dụng: nếu ứng dụng tự gọi `kms:Decrypt`, điều kiện `kms:ViaService` qua S3 sẽ không thỏa mãn.

**Nuance cùng tài khoản:** Key policy có thể cấp quyền trực tiếp cho role hoặc cho phép IAM identity policies trong account cấp quyền thông qua statement phù hợp. Vì vậy đừng khẳng định **mọi** lần dùng KMS cùng account đều bắt buộc có cả một Allow ở key policy trực tiếp cho role **và** một Allow từ IAM. Ví dụ minh họa chủ động thể hiện cả hai để người học thấy rõ lớp kiểm soát.

### 6.3. Quyền để dùng role không đồng nghĩa quyền đọc object

Nếu workload chạy trên:

- **Lambda:** cần execution role có trust cho `lambda.amazonaws.com`; gắn policy ở trên.
- **ECS:** thường gắn policy vào **task role** mà container sử dụng, không lẫn với ECS task execution role dành cho image/log.
- **EC2:** dùng role qua instance profile, để SDK lấy temporary credentials.
- **CI/CD:** dùng role được assume từ cơ chế xác thực hợp lệ hoặc federation; không hardcode access key.

Trong mọi trường hợp, **key policy vẫn phải cho phép ngữ cảnh principal thực**. Kiểm tra bằng `aws sts get-caller-identity` từ chính môi trường phát sinh lỗi.

## 7. Bucket policy và yêu cầu bắt buộc SSE-KMS

Có hai mục tiêu rất khác nhau:

- **Mục tiêu A:** “Mọi object mới khi lưu đều dùng SSE-KMS” → đặt **default encryption SSE-KMS** và quản trị quyền/configuration.
- **Mục tiêu B:** “Client bắt buộc gửi header chọn SSE-KMS trong request upload” → có thể dùng **bucket policy Deny** với điều kiện trên request header.

Ví dụ **Deny request PutObject không khai báo SSE-KMS**:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyUploadsWithoutExplicitSSEKMS",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::invoice-data-demo/*",
      "Condition": {
        "StringNotEquals": {
          "s3:x-amz-server-side-encryption": "aws:kms"
        }
      }
    }
  ]
}
~~~

**Cảnh báo về hành vi:** Statement trên từ chối request **không có header SSE-KMS**, ngay cả khi bucket **đã cấu hình default encryption SSE-KMS**. Vì policy kiểm tra **điều kiện của request**, nó không thể suy luận rằng S3 sẽ dùng default SSE-KMS sau đó. Điều này làm hỏng các client upload chỉ dựa vào mặc định. Chỉ áp dụng khi doanh nghiệp thực sự cần **client chỉ định rõ** encryption mode và đã cập nhật toàn bộ client.

### Muốn bắt buộc đúng customer managed key?

Ngoài header `s3:x-amz-server-side-encryption`, có thể dùng điều kiện liên quan:

~~~text
s3:x-amz-server-side-encryption-aws-kms-key-id
~~~

Khi xây dựng bucket policy, cần xét **trường hợp thiếu header**, **key ARN khác**, alias, cách ghi key ID và sự tương tác với default encryption. Đừng lấy một policy mẫu chặn mọi upload rồi nới rộng `Principal` hoặc mở KMS key vô điều kiện để chữa lỗi.

Một phương án quản trị thường đơn giản hơn là **default SSE-KMS bằng key chính thức + kiểm soát ai được thay đổi bucket configuration + giám sát compliance**, đồng thời chỉ dùng Deny theo header khi đó là yêu cầu thiết kế đã được kiểm chứng.

### Bắt buộc HTTPS

Dữ liệu lưu trong S3 đã mã hóa at rest nhưng request vẫn cần bảo vệ **in transit**. Có thể xem bucket policy Deny cho trường hợp `aws:SecureTransport=false`:

~~~json
{
  "Sid": "DenyInsecureTransport",
  "Effect": "Deny",
  "Principal": "*",
  "Action": "s3:*",
  "Resource": [
    "arn:aws:s3:::invoice-data-demo",
    "arn:aws:s3:::invoice-data-demo/*"
  ],
  "Condition": {
    "Bool": {
      "aws:SecureTransport": "false"
    }
  }
}
~~~

Trước khi dùng policy trong môi trường thật, đánh giá các **dịch vụ AWS gọi dịch vụ thay mặt bạn**: một số network context keys bị ẩn đối với service principals, nên tổ chức có thể cần điều kiện ngoại lệ `aws:PrincipalIsAWSService` theo mẫu AWS để không vô tình chặn service-to-service hợp lệ. Đừng thêm ngoại lệ rộng nếu không có nhu cầu được chứng minh.

## 8. Cross-account: tại sao mở bucket thôi vẫn không đọc được?

Giả sử:

- **Account A:** `111122223333`, bucket `invoice-data-demo` và customer managed KMS key.
- **Account B:** `444455556666`, role `ReportConsumerRole` cần **đọc** `reports/` trong bucket của A.
- Truy cập giữa account được cấp cho **role cụ thể**, không chia sẻ static keys.

### 8.1. Ba sự cho phép cần đồng thời phù hợp

| Vị trí | Cấu hình | Vai trò |
| --- | --- | --- |
| **Bucket tại A** | Bucket policy cho role B đọc `reports/*` | Cho phép từ phía tài nguyên S3 |
| **Role tại B** | IAM identity policy cho `s3:GetObject` trên object ARN | Cho phép từ phía caller trong trường hợp cross-account thông thường |
| **KMS key tại A** | Key policy cho phép role/account B dùng `kms:Decrypt` theo điều kiện thích hợp | Cho phép giải mã key của object tại account chủ khóa |
| **Role tại B (KMS)** | IAM identity policy cho `kms:Decrypt` với key ARN A | Hoàn tất quyền KMS cross-account ở phía caller |

**AWS KMS khác cross-account S3 ở chỗ:** đối với KMS key tại account A, chỉ có IAM policy của account B thường **không đủ**; key policy phía A phải cho phép cross-account, đồng thời quyền IAM phía B cũng cần tương ứng. Key phải là loại có khả năng quản lý policy và chia sẻ được, thường là **customer managed key**.

### 8.2. Bucket policy phía A

Ví dụ statement hạn chế prefix:

~~~json
{
  "Sid": "AllowReadReportsFromAccountB",
  "Effect": "Allow",
  "Principal": {
    "AWS": "arn:aws:iam::444455556666:role/ReportConsumerRole"
  },
  "Action": "s3:GetObject",
  "Resource": "arn:aws:s3:::invoice-data-demo/reports/*"
}
~~~

Tùy bối cảnh, chủ bucket cần xem Object Ownership, Block Public Access, explicit Deny hoặc chính sách tổ chức. Nếu yêu cầu `ListBucket`, phải cấp action trên bucket ARN và giới hạn `s3:prefix` tương ứng.

### 8.3. KMS key policy phía A

Statement ví dụ trong customer managed key policy:

~~~json
{
  "Sid": "AllowAccountBReportConsumerDecryptViaS3",
  "Effect": "Allow",
  "Principal": {
    "AWS": "arn:aws:iam::444455556666:role/ReportConsumerRole"
  },
  "Action": [
    "kms:Decrypt",
    "kms:DescribeKey"
  ],
  "Resource": "*",
  "Condition": {
    "StringEquals": {
      "kms:ViaService": "s3.ap-southeast-1.amazonaws.com"
    }
  }
}
~~~

### 8.4. IAM policy của ReportConsumerRole phía B

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::invoice-data-demo/reports/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "kms:Decrypt",
        "kms:DescribeKey"
      ],
      "Resource": "arn:aws:kms:ap-southeast-1:111122223333:key/12345678-1234-1234-1234-1234567890ab"
    }
  ]
}
~~~

Sau khi cấp, thực hiện `GetObject` từ role thực, kiểm tra CloudTrail/S3 response. **Không thay `Principal` thành `"*" ` hoặc mở quyền key cho tất cả các account** khi không cần thiết.

### AWS managed key `aws/s3` là ranh giới quan trọng

Với AWS managed key dành cho S3, bạn không thể tùy chỉnh key policy để cho role ở account B dùng như customer managed key. Khi cần cross-account đọc các object SSE-KMS, hãy:

1. Chọn **customer managed KMS key** tại đúng Region.
2. Cấu hình bucket/object dùng key này.
3. Thiết lập cả **bucket policy, KMS key policy và IAM policy caller** phù hợp.
4. Với object cũ vẫn dùng `aws/s3`, đánh giá **copy/re-encrypt** sang customer managed key trước khi chuyển truy cập.

## 9. Thực hành AWS CLI: tải lên, kiểm tra metadata và đọc object

**Môi trường:** account lab đã có bucket và customer managed KMS key đúng Region. ID dưới đây chỉ là ví dụ. Role thử nghiệm được cấp đúng quyền S3/KMS; không sử dụng dữ liệu bí mật thật và không ghi temporary credentials vào terminal logs.

### 9.1. Xác định danh tính đang gọi AWS

~~~bash
aws sts get-caller-identity --profile lab
aws s3api get-bucket-location --bucket invoice-data-demo --profile lab
aws s3api get-bucket-encryption --bucket invoice-data-demo --profile lab
~~~

Xác nhận account/role, bucket Region và rule default encryption trước khi upload. Trong một số môi trường, `GetBucketEncryption` bị từ chối do IAM; **AccessDenied khi đọc cấu hình bucket chưa chứng minh object thiếu mã hóa**.

### 9.2. Tạo file thử cục bộ

~~~bash
printf "hello s3 sse-kms lab\n" > invoice-lab.txt
~~~

Lệnh này tạo file đơn giản trên máy người học. Không dùng thông tin cá nhân hoặc dữ liệu nhạy cảm để thử.

### 9.3. Upload SSE-KMS với key ARN cụ thể

~~~bash
aws s3api put-object \
  --bucket invoice-data-demo \
  --key invoices/lab/invoice-lab.txt \
  --body invoice-lab.txt \
  --server-side-encryption aws:kms \
  --ssekms-key-id arn:aws:kms:ap-southeast-1:111122223333:key/12345678-1234-1234-1234-1234567890ab \
  --profile lab \
  --region ap-southeast-1
~~~

S3 CLI sẽ gọi upload; dịch vụ tích hợp KMS theo cấu hình. Nếu thiếu `kms:GenerateDataKey`, key policy sai hoặc quyền S3 bị chặn, thao tác có thể thất bại. KMS key ARN nên được dùng rõ ràng đặc biệt khi account, role hoặc bucket có bối cảnh cross-account.

### 9.4. Kiểm tra metadata mã hóa

~~~bash
aws s3api head-object \
  --bucket invoice-data-demo \
  --key invoices/lab/invoice-lab.txt \
  --query '{SSE:ServerSideEncryption,KMSKey:SSEKMSKeyId,BucketKey:BucketKeyEnabled,Size:ContentLength}' \
  --profile lab \
  --region ap-southeast-1
~~~

Một phản hồi minh họa:

~~~json
{
  "SSE": "aws:kms",
  "KMSKey": "arn:aws:kms:ap-southeast-1:111122223333:key/12345678-1234-1234-1234-1234567890ab",
  "BucketKey": true,
  "Size": 21
}
~~~

Khi sử dụng SSE-S3, metadata thường có `ServerSideEncryption: AES256`; với DSSE-KMS, mã hiển thị có thể là `aws:kms:dsse`. Không giả định **mọi** thuộc tính phản hồi đều luôn có mặt trong mọi loại object/bucket.

### 9.5. Tải về và đọc

~~~bash
aws s3api get-object \
  --bucket invoice-data-demo \
  --key invoices/lab/invoice-lab.txt \
  ./downloaded-invoice-lab.txt \
  --profile lab \
  --region ap-southeast-1
~~~

Nếu object dùng SSE-KMS, role cần quyền giải mã key phù hợp theo workflow. **Không truyền `--server-side-encryption` trong `GetObject`** để yêu cầu S3 “giải mã”: S3 tự xử lý chế độ server-side theo metadata và quyền hợp lệ.

### 9.6. Kiểm chứng cả một đường bị từ chối

Trong lab, có thể thử một **role chỉ có quyền S3 nhưng thiếu quyền KMS** đối với object SSE-KMS. Ghi lại error và CloudTrail, sau đó khôi phục cấu hình hợp lệ. Không tự sửa bucket policy hoặc key policy của production để tạo lỗi demo.

**Kết quả mong đợi:** Người học xác nhận được rằng **mã hóa được ghi vào metadata object** và **quyền S3 đúng chưa đủ khi KMS từ chối**.

## 10. S3 Bucket Keys: giảm KMS request và thay đổi encryption context

Với nhiều object SSE-KMS, S3 có thể phát sinh số lượng lớn lời gọi KMS. **Amazon S3 Bucket Keys** là tính năng giúp giảm đáng kể các request S3 → KMS khi mã hóa SSE-KMS, từ đó giảm chi phí KMS request và tác động quota. Tùy workload, AWS công bố khả năng giảm **tới khoảng 99%** số request KMS liên quan.

### Phù hợp khi nào?

- Bucket có **nhiều object**, tải lên/đọc thường xuyên bằng SSE-KMS.
- Chi phí hoặc quota **KMS requests** là vấn đề thực tế.
- Workload có thể dùng **SSE-KMS thông thường**, không yêu cầu DSSE-KMS.
- Key policy và encryption context đã được xem xét tương thích với Bucket Keys.

### Tại sao cần hiểu encryption context?

KMS encryption context là tập cặp khóa–giá trị gắn với thao tác KMS, hỗ trợ xác thực/điều kiện cấp quyền. Với SSE-KMS thông thường, một khóa context được S3 sử dụng là:

~~~text
kms:EncryptionContext:aws:s3:arn
~~~

Trong nhiều trường hợp **không dùng Bucket Keys**, giá trị là **object ARN**, ví dụ:

~~~text
arn:aws:s3:::invoice-data-demo/invoices/2026/order-1001.pdf
~~~

Khi **dùng S3 Bucket Keys**, context có thể chuyển sang **bucket ARN**:

~~~text
arn:aws:s3:::invoice-data-demo
~~~

Nếu KMS key policy hoặc IAM policy có điều kiện `kms:EncryptionContext:aws:s3:arn` bắt buộc khớp `arn:aws:s3:::invoice-data-demo/invoices/*`, bật Bucket Keys có thể làm request KMS **không thỏa điều kiện**. Cần đánh giá/tái thiết kế điều kiện và kiểm thử quyền khi đổi tính năng.

**Không được đưa dữ liệu bí mật vào encryption context**: các giá trị context có thể xuất hiện trong nhật ký kiểm toán KMS/CloudTrail.

### Bucket Keys có thay IAM/S3 permission không?

Không. Bucket Keys giảm tần suất gọi KMS và thay đổi một số chi tiết xử lý encryption context; **không cấp thêm `s3:GetObject`**, không thay bucket policy và không loại bỏ yêu cầu kiểm soát key hợp lý. Với chia sẻ cross-account và chính sách key hạn chế, hãy kiểm thử request từ từng principal thực tế.

### Chi phí SSE-KMS

Khi dùng **customer managed key**, chi phí có thể bao gồm:

- Phí duy trì key (và chi phí phiên bản/tính năng key nếu áp dụng).
- Phí **AWS KMS API requests** liên quan upload, download, copy, multipart hoặc các workflow khác.
- Phí S3 storage, request, transfer, replication, logging và các dịch vụ hạ tầng liên quan.

**AWS managed key** có mô hình phí quản lý key khác customer managed key, nhưng **KMS requests vẫn có thể bị tính phí**. Với SSE-S3 thông thường, không phát sinh loại phí KMS API này cho ứng dụng.

Không chọn SSE-KMS hoặc SSE-S3 chỉ từ một con số phí; quyết định phải đáp ứng yêu cầu kiểm soát khóa/kiểm toán trước, sau đó tối ưu Bucket Keys và pattern request.

## 11. KMS key policy, grants, rotation và vòng đời khóa

### 11.1. Key policy là nguồn kiểm soát quyền chính của KMS key

AWS KMS khác nhiều dịch vụ ở chỗ **mọi key đều có key policy**. Key policy có thể:

- Cho principal cụ thể dùng key;
- Cho phép **IAM identity policies trong cùng account** được dùng để cấp quyền key theo cấu hình policy;
- Đặt điều kiện như `kms:ViaService` hoặc encryption context;
- Tách quyền **quản trị key** khỏi quyền **encrypt/decrypt**.

**Quyền quản trị key không tự đồng nghĩa được giải mã dữ liệu**; thiết kế nên tách nhân sự quản trị khóa và ứng dụng dùng khóa, trừ khi workflow thực sự cần kết hợp.

Một key policy vô tình **loại bỏ quyền quản trị/khả năng phục hồi** có thể khiến key không quản lý được theo dự kiến. Khi thực hành, giữ những statement quản trị bắt buộc của tổ chức và chỉ bổ sung statement có phạm vi rõ ràng.

### 11.2. KMS grants

**KMS grant** là cơ chế cấp quyền dùng KMS key cho một grantee trong các thao tác cho phép, thường gặp ở những tích hợp dịch vụ AWS. Grant không thay thế hoàn toàn key policy; cơ chế tạo grant phụ thuộc vào key policy/IAM phù hợp và điều kiện hỗ trợ.

Trong một số hệ thống, bạn có thể cần điều tra cả:

- IAM policy của principal;
- KMS key policy;
- Grants hiện hành và constraint của grant;
- Explicit Deny từ các lớp kiểm soát.

Đừng tự cấp `kms:CreateGrant` với phạm vi rộng chỉ để chữa lỗi `AccessDenied`; quyền này có tác động quản trị và nên bị giới hạn theo trường hợp sử dụng.

### 11.3. Rotation không mã hóa lại dữ liệu hiện có

**KMS automatic rotation** cho customer managed key được hỗ trợ giúp AWS KMS tạo vật liệu khóa mới theo chính sách/tần suất được cấu hình. Key ID/ARN logic vẫn tồn tại và AWS KMS còn duy trì vật liệu khóa cũ cần thiết để giải mã ciphertext trước đó.

**Điểm quan trọng:** Bật automatic key rotation **không tự ghi lại mọi S3 object hoặc thay SSE mode**. Nếu mục tiêu là **chuyển toàn bộ object sang KMS key mới có ARN khác**, cần workflow re-encryption/copy object.

### 11.4. Disable hoặc delete KMS key ảnh hưởng dữ liệu thế nào?

- Khi key bị **disabled** hoặc chưa có quyền, object SSE-KMS phụ thuộc key có thể **không đọc/ghi được** theo luồng yêu cầu KMS.
- **Scheduled deletion** và việc key thực sự bị xóa có thể dẫn tới **mất khả năng giải mã vĩnh viễn** với dữ liệu chỉ có thể giải mã nhờ key đó.
- Backup/copy/replication mã hóa bằng key khác cần được kiểm tra và bảo đảm quyền truy cập trước khi thay đổi lifecycle.
- Thiết lập cảnh báo qua CloudTrail/EventBridge/CloudWatch cho thay đổi trạng thái và policy của key quan trọng.

Khi đổi key hoặc xử lý nghi rò rỉ, cần có kế hoạch **kiểm kê object phụ thuộc**, giữ quyền giải mã data cũ trong thời gian migration và diễn tập restore. Đây là rủi ro vận hành lớn hơn nhiều so với chỉ đổi một thuộc tính cấu hình bucket.

## 12. Copy, multipart upload, replication và object cũ

### 12.1. CopyObject giữa hai key

Giả sử object nguồn dùng `KMS-Key-A`, object đích được copy với `KMS-Key-B`. Workflow có thể cần:

- `s3:GetObject` trên nguồn và `s3:PutObject` trên đích;
- `kms:Decrypt` với key A;
- `kms:GenerateDataKey` và quyền KMS cần thiết với key B;
- quyền bucket/object policies cùng các giới hạn KMS tương ứng.

Nếu copy object trong cùng bucket mà muốn đổi key, **copy lại object** có thể tạo **version mới** khi bật versioning, ảnh hưởng ETag/metadata theo API và làm tăng phí. Đối với hàng triệu object, cân nhắc **S3 Batch Operations** và một kế hoạch theo dõi/lỗi có kiểm soát.

### 12.2. Multipart upload và SSE-KMS

Upload file lớn theo multipart chia thành nhiều part. Với SSE-KMS, ngoài `s3:PutObject`, cần xác nhận các quyền KMS dùng trong từng giai đoạn, đặc biệt `kms:GenerateDataKey` và `kms:Decrypt` theo tài liệu S3 multipart. Một role upload được file nhỏ nhưng **multipart bị AccessDenied** có thể đang thiếu quyền KMS cho workflow này.

### 12.3. Replication đối với SSE-KMS

Một số mục tiêu:

- Sao chép object từ bucket nguồn sang bucket đích ở cùng Region hoặc Region khác.
- Giữ dữ liệu ở account dự phòng.
- Mã hóa bản sao bằng **KMS key tại Region đích**.

Với SSE-KMS, replication cần cấu hình **opt-in** cho object được mã hóa bằng SSE-KMS và chỉ định key đích phù hợp theo quy tắc replication; IAM role của replication cần quyền S3 và KMS liên quan. Có thể cần quyền giải mã source key và mã hóa destination key, cùng key policies phù hợp. **Không mặc định bật replication rule là mọi object SSE-KMS tự được sao chép.**

Cần bật versioning nếu được yêu cầu cho replication, xác nhận Object Ownership, KMS cross-account, bucket policy, quyền role, phí request/data transfer và giám sát replication status.

### 12.4. Default encryption mới không xử lý lịch sử dữ liệu

Ví dụ bucket từng dùng SSE-S3; hôm nay chuyển default SSE-KMS. Kể từ đó các upload mới dùng cấu hình mới theo điều kiện. **Các object cũ không tự biến thành SSE-KMS**.

Quy trình migration:

1. **Inventory** trạng thái mã hóa/key ARN của object.
2. Xác định nhóm object cần chuyển, có versioning/Object Lock/replication không.
3. Chuẩn bị KMS key, IAM role, key/bucket policy và quota.
4. Chạy thử copy/re-encrypt trên mẫu đại diện; xác minh metadata và đọc/khôi phục.
5. Chuyển dữ liệu theo batch có retry, quan sát lỗi và ngân sách.
6. Kiểm tra ứng dụng, presigned URL, metadata và các tác động tới phiên bản/dedup nếu có.
7. Chỉ dọn phiên bản/khóa cũ khi đã chứng minh dữ liệu mới đọc được và có backup.

## 13. Kết hợp S3 SSE-KMS với EC2, ECS, Lambda, VPC và dịch vụ dữ liệu

Một kiến trúc mẫu lưu hóa đơn của ứng dụng bán hàng:

~~~mermaid
flowchart TB
    U[Người dùng] --> API[API Gateway / ALB]
    API --> App[Lambda hoặc ECS: tạo hóa đơn]
    App -->|PutObject SSE-KMS| S3[(S3 invoice bucket)]
    App -. IAM role .-> IAM[IAM permissions]
    S3 -->|GenerateDataKey / Decrypt theo workflow| KMS[AWS KMS key]
    IAM -. KMS permissions .-> KMS
    S3 --> Log[CloudTrail / S3 access logs]
    KMS --> Audit[CloudTrail key events]
    App --> Obs[CloudWatch alarms]
    S3 --> Backup[Versioning / backup / replication]
~~~

**Từng lớp có nhiệm vụ riêng:**

- **IAM role** cho Lambda/ECS/EC2 cấp `s3:PutObject`, `s3:GetObject` và KMS permissions đúng key/action. Role được gắn theo phương thức tích hợp của từng service.
- **VPC và network** quyết định runtime có đường tới endpoint của S3 hay không; với workload private có thể dùng **S3 gateway endpoint** hoặc endpoint phù hợp. Network path đúng không thay quyền IAM/KMS.
- **S3 default encryption** dùng SSE-KMS; role và bucket policy giới hạn prefix, TLS, yêu cầu truy cập.
- **KMS key** có key policy phù hợp, có audit và quy trình rotation/recovery.
- **CloudTrail** hỗ trợ điều tra API S3/KMS; muốn ghi đầy đủ object-level S3 data events thường phải bật/cấu hình riêng.
- **Versioning/replication/backup** hỗ trợ khôi phục object bị xóa/ghi đè, giải quyết mục tiêu phục hồi theo RPO/RTO.
- **AWS Budgets/Cost Explorer** giám sát storage, KMS requests, API requests, replication, transfer, logs.

### Mã hóa object có phụ thuộc AZ không?

S3 general purpose bucket là tài nguyên cấp **Region**, không gắn một AZ như EBS volume. KMS key cho SSE-KMS phải ở đúng Region bucket, còn workload EC2/Lambda có thể chạy qua nhiều AZ. Dù S3 có đặc tính bền vững cấp dịch vụ, **mất/không có quyền KMS key vẫn có thể làm ứng dụng không đọc được object**, nên xem key policy/lifecycle như một phụ thuộc sẵn sàng quan trọng.

### Cấp quyền cho presigned URL

Một ứng dụng có thể tạo **presigned URL** để người dùng tải file lên/xuống S3 theo phạm vi quyền của principal ký URL. Điều này tránh cấp AWS credentials dài hạn cho người dùng cuối, nhưng presigned URL là một bearer capability có thời hạn; phải bảo vệ URL và áp dụng đúng content type/header, key prefix, expiration và giới hạn hành động.

Với SSE-KMS, **principal ký request** và workflow S3/KMS phải có quyền phù hợp. Người dùng cuối không cần được gửi trực tiếp KMS credentials; nhưng request upload presigned URL phải dùng **headers khớp chữ ký** nếu đã ký header SSE-KMS. Đừng đưa KMS key material hoặc bí mật ứng dụng vào URL.

## 14. Giám sát mã hóa, kiểm toán và kiểm soát chi phí

### 14.1. Kiểm tra trạng thái mã hóa

Dùng nhiều nguồn:

- **Bucket default encryption configuration:** cho biết cách S3 áp dụng mã hóa cho upload mới theo mặc định.
- **Object metadata từ HeadObject:** cho biết mode SSE của object và key ID/ARN khi được trả.
- **S3 Inventory/Storage Lens và các công cụ kiểm kê được hỗ trợ:** hữu ích khi phải kiểm tra hàng triệu object.
- **AWS Config / Security Hub** với rule/control phù hợp: giám sát thay đổi cấu hình hoặc không tuân thủ.
- **CloudTrail:** theo dõi ai sửa bucket encryption policy, ai thay key policy, ai disabled/scheduled deletion key, và S3 data events khi đã cấu hình.

**Không chỉ dựa vào default encryption của bucket để khẳng định 100% object lịch sử đã dùng key mới.** Cần kiểm tra object metadata hoặc kết quả inventory.

### 14.2. CloudTrail: đừng nhầm hai nguồn log

| Nguồn | Có thể giúp xác định | Giới hạn |
| --- | --- | --- |
| **CloudTrail S3 management events** | Ai thay bucket encryption, policy, public access, replication configuration | Không tự ghi mọi `GetObject` của client |
| **CloudTrail S3 data events** | Object-level actions như `GetObject`, `PutObject` khi bật đúng scope | Có cấu hình riêng, chi phí, cần chọn bucket/prefix/scope |
| **CloudTrail AWS KMS events** | Một số thao tác key như `GenerateDataKey`, `Decrypt`, thay đổi chính sách/trạng thái | Số lần gọi không nhất thiết 1:1 với object khi có Bucket Keys/caching |
| **CloudWatch** | Metric/alarms ứng dụng, lỗi, latency, API behavior | Phải cấu hình metric, alarm, log retention phù hợp |

KMS encryption context có thể hiện trong CloudTrail; không đặt password, token hoặc dữ liệu bí mật vào đó.

### 14.3. Lập mô hình chi phí

Với SSE-KMS, tách các khoản:

\[
C_{\text{total}}
\approx C_{\text{S3 storage}}
+ C_{\text{S3 requests/transfer}}
+ C_{\text{KMS keys}}
+ C_{\text{KMS requests}}
+ C_{\text{replication/logs/backup}}
\]

Một workload có nhiều object nhỏ, đọc/ghi liên tục, có thể phát sinh **KMS request cost đáng kể** so với chi phí dung lượng. **Bucket Keys** là ứng viên tối ưu nhưng cần tính toán tác động điều kiện encryption context và trường hợp không hỗ trợ.

### Ví dụ so sánh theo số request

Giả sử dịch vụ tạo 2 triệu object/tháng và đọc 10 triệu lần/tháng. Với SSE-KMS **không dùng Bucket Keys**, tổng số KMS API được tính phí có thể tăng theo số thao tác S3; nhưng **không thể lấy cứng 12 triệu yêu cầu KMS** nếu chưa xét caching, multipart, copy và cách S3 tích hợp KMS.

Quy trình:

1. Đo KMS request metrics/billing và CloudTrail thực tế.
2. Phân nhóm bucket/prefix/workload có nhiều request.
3. Xem khả năng dùng Bucket Keys cùng key policy hiện hành.
4. Dùng **AWS Pricing Calculator/Cost Explorer** tính theo Region, loại key và biểu giá đang áp dụng.
5. So sánh kết quả thực sau khi bật với số liệu trước đó.

## 15. Troubleshooting: khi nào S3 báo AccessDenied vì KMS?

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra trọng tâm |
| --- | --- | --- |
| **PutObject SSE-KMS bị AccessDenied** | Thiếu `s3:PutObject`, `kms:GenerateDataKey`, key policy không cho role, bucket policy từ chối header | Caller ARN, bucket policy, KMS key policy, đúng KMS ARN/Region |
| **GetObject SSE-KMS bị AccessDenied** | S3 cho đọc nhưng thiếu `kms:Decrypt`; key policy/SCP/boundary Deny | Xem encryption metadata, role thực và KMS key trạng thái |
| **Cross-account đọc object SSE-KMS thất bại** | Bucket đã cấp nhưng key `aws/s3` không chia sẻ được, hoặc thiếu caller IAM/KMS key policy | Dùng customer managed key, cấp đúng role B ở A và IAM policy ở B |
| **Chỉ multipart upload thất bại** | Thiếu KMS permission trong workflow multipart | Xem `GenerateDataKey`/`Decrypt`, API giai đoạn lỗi và CloudTrail |
| **Client không gửi SSE header và PutObject bị Deny** | Bucket policy yêu cầu header, dù default encryption SSE-KMS đã bật | So policy condition `s3:x-amz-server-side-encryption` và header thực |
| **Bật S3 Bucket Keys rồi phát sinh AccessDenied** | Condition trên `kms:EncryptionContext:aws:s3:arn` chỉ chấp nhận object ARN | Kiểm tra bucket ARN context và cập nhật điều kiện có kiểm soát |
| **Đổi default encryption nhưng object cũ vẫn SSE-S3** | Default encryption chỉ tác động upload mới | Kiểm kê object lịch sử, lập kế hoạch re-encryption |
| **Key disabled/pending deletion** | KMS key không usable hoặc bị khóa theo lifecycle | `kms:DescribeKey`, CloudTrail, owner, quy trình phục hồi key |
| **SSE-KMS upload vào bucket Region khác lỗi** | KMS key khác Region với bucket | Xác nhận bucket Region và key ARN |
| **Copy/replication bị KMS AccessDenied** | Thiếu decrypt source/encrypt dest, key policies cross-account, role replication | Review nguồn/đích, phiên bản, key ARN/Region, replication status |
| **HeadObject được nhưng GetObject không được** | Metadata không cần giải mã nội dung nhưng đọc cần KMS | So `s3:GetObject`, `kms:Decrypt` và các Deny |
| **KMS Throttling/RequestLimitExceeded** | Quá nhiều thao tác KMS hoặc quota/giới hạn key/API | Đo KMS request, retry backoff, Bucket Keys, quota/chi phí |
| **Role đã có IAM KMS Allow nhưng vẫn lỗi** | Key policy chưa cho phép IAM trong account/role, explicit Deny hoặc condition không khớp | Đối chiếu key policy, grants, context, `kms:ViaService`, SCP |

### Quy trình điều tra bảy bước

~~~text
1. Xác định caller thật: aws sts get-caller-identity (đúng role/profile/workload).
2. Xác định bucket, object key, Region và action đang lỗi (Put/Get/Copy/Multipart).
3. Đọc encryption metadata của object (nếu có quyền) và default config bucket.
4. Kiểm tra IAM + bucket policy: Allow/Deny, prefix, endpoint, SecureTransport.
5. Nếu SSE-KMS: kiểm tra key ARN/Region/state, KMS key policy, caller IAM,
   grants, boundary/SCP, kms:ViaService và encryption context.
6. Xem CloudTrail S3/KMS tương ứng thời điểm lỗi, kể cả request id khi có;
   kiểm tra Bucket Keys, replication và request headers.
7. Chỉnh đúng quyền/điều kiện tối thiểu trong lab, thử lại upload/download,
   xác minh các thao tác ngoài phạm vi vẫn bị từ chối.
~~~

**Đừng giải quyết lỗi bằng cách mở** `s3:*`, `kms:*` hoặc principal `*` trên toàn bộ tài nguyên. Cách làm đó có thể che khuất nguyên nhân thật và tạo đường truy cập quá rộng, đặc biệt nguy hiểm với customer managed KMS key.

## 16. Sai lầm phổ biến khi thiết kế mã hóa S3

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “S3 không có default encryption nếu tôi chưa bật rule.” | S3 mặc định SSE-S3 cho object mới; rule riêng dùng khi cần SSE-KMS/DSSE-KMS hoặc cấu hình khác. |
| “SSE-KMS chỉ cần quyền S3.” | Thao tác có thể cần quyền AWS KMS riêng trên key tương ứng. |
| “Tôi có `kms:Decrypt` nên chắc chắn đọc được S3 object.” | Vẫn cần `s3:GetObject` và không bị các Deny/điều kiện khác chặn. |
| “Key policy không quan trọng nếu IAM policy có Allow.” | Key policy là phần cốt lõi của authorization AWS KMS. |
| “AWS managed key `aws/s3` chia sẻ dễ dàng liên tài khoản.” | Thường cần customer managed KMS key để cho phép cross-account use có kiểm soát. |
| “Bật default SSE-KMS là đổi mã hóa mọi object cũ.” | Cấu hình mặc định chủ yếu tác động object mới, cần re-encrypt dữ liệu lịch sử. |
| “Bắt buộc client gửi SSE-KMS header không ảnh hưởng upload mặc định.” | Bucket Deny theo request header có thể chặn client dựa vào default encryption. |
| “S3 Bucket Keys chỉ là giảm phí, không ảnh hưởng policy.” | Encryption context có thể dùng bucket ARN thay object ARN, ảnh hưởng điều kiện KMS. |
| “KMS key rotation tự rewrite mọi S3 object.” | Automatic rotation của cùng logical key không thay chế độ mã hóa/ARN object. |
| “S3 encryption là backup.” | Mã hóa không bảo vệ khỏi xóa nhầm, ghi đè hay mất khả năng giải mã do xóa key. |
| “SSE-KMS làm traffic network tự đi private.” | Mã hóa at rest không quyết định VPC routing, endpoints hay TLS. |
| “CloudTrail tự ghi mọi GetObject của S3.” | Object-level data events thường phải cấu hình riêng theo yêu cầu. |

## 17. Checklist áp dụng vào hệ thống AWS

- [ ] Đã xác định dữ liệu nào cần SSE-S3, SSE-KMS, DSSE-KMS hoặc client-side encryption theo yêu cầu thật.
- [ ] Đã kiểm tra **bucket Region, loại bucket** và KMS key ARN/Region phù hợp.
- [ ] Nếu dùng SSE-KMS: đã chọn AWS managed key hay customer managed key bằng lý do rõ ràng, nhất là khi cross-account.
- [ ] Bucket default encryption được cấu hình đúng; đã hiểu cấu hình này **không tự xử lý object cũ**.
- [ ] Principal thực của EC2/ECS/Lambda/CI được xác nhận; không dùng static credentials dài hạn để “né” KMS.
- [ ] Identity policy, bucket policy, key policy/grants, SCP/boundary/session/endpoint policy đã được xem cùng nhau.
- [ ] Upload có quyền `kms:GenerateDataKey`, đọc có `kms:Decrypt` theo workflow; multipart/copy/replication kiểm tra quyền riêng.
- [ ] Nếu có điều kiện `kms:ViaService` hoặc encryption context, đã kiểm tra đúng Region, bucket ARN/object ARN và tương tác Bucket Keys.
- [ ] Nếu bắt buộc SSE-KMS header, toàn bộ client thực sự gửi header tương thích với bucket policy.
- [ ] Có HTTPS/TLS, Block Public Access và giới hạn S3 access; mã hóa không bị hiểu nhầm là authorization.
- [ ] Có kế hoạch lifecycle/rotation/disable/delete KMS key an toàn và cơ chế khôi phục khi key không dùng được.
- [ ] Có versioning/backup/replication và **restore test** đáp ứng RTO/RPO dữ liệu.
- [ ] Có CloudTrail S3/KMS, CloudWatch alarms, log retention, audit thay đổi cấu hình/khóa.
- [ ] Đã dự toán storage, request, KMS key/request, Bucket Keys, copy/replication và logging theo Region.
- [ ] Đã kiểm chứng upload/download thành công và một **request ngoài phạm vi bị Deny** trong môi trường lab.

## 18. Bài tập tình huống

### Tình huống A — Lambda upload được nhưng không đọc được

Một Lambda dùng role `InvoiceWorkerRole` có `s3:PutObject`, `s3:GetObject` và `kms:GenerateDataKey`. Bucket mặc định SSE-KMS bằng customer managed key. Upload thành công, nhưng tải lại object báo AccessDenied.

**Yêu cầu:**

1. Xác định quyền KMS nào có thể còn thiếu.
2. Nêu vì sao `GetObject` và `PutObject` dùng những hành động KMS khác nhau.
3. Đối chiếu key policy, IAM policy, Region, role thực và CloudTrail.
4. Đề xuất sửa tối thiểu, kiểm tra lại và chứng minh không được phép xóa object.

**Gợi ý:** Quyền `kms:Decrypt` thường cần khi đọc object SSE-KMS; đồng thời kiểm tra explicit Deny và key policy.

### Tình huống B — Chia sẻ dữ liệu báo cáo cho account khác

Account A có bucket mã hóa bằng AWS managed key `aws/s3`; account B đã được bucket policy cấp `s3:GetObject` nhưng vẫn không thể giải mã.

**Yêu cầu:** Đề xuất lộ trình dùng customer managed KMS key đúng Region, cấu hình cả hai account, migration object cũ và kiểm chứng CloudTrail.

**Gợi ý:** Cross-account KMS cần quyền từ chủ khóa và account caller, trong khi key policy của AWS managed key không thể tùy chỉnh giống customer managed key.

### Tình huống C — Sau khi bật Bucket Keys, request bắt đầu bị từ chối

Một IAM/KMS policy trước đó có điều kiện:

~~~json
{
  "StringLike": {
    "kms:EncryptionContext:aws:s3:arn": "arn:aws:s3:::invoice-data-demo/invoices/*"
  }
}
~~~

Sau khi bật S3 Bucket Keys, một số thao tác SSE-KMS thất bại.

**Yêu cầu:** Giải thích sự khác biệt object ARN/bucket ARN trong encryption context; đề xuất cách chỉnh điều kiện và bảo vệ prefix bằng S3 IAM/bucket policy; xây test kiểm chứng trước/sau.

**Gợi ý:** Bucket Keys có thể sử dụng bucket ARN trong encryption context; phân quyền prefix object nên đặt ở S3 policy thay vì dựa hoàn toàn vào context trên KMS.

### Tình huống D — Ước lượng chi phí cho 50 triệu object

Một ứng dụng có hàng chục triệu object nhỏ, nhiều request `GetObject`, bắt buộc customer managed KMS key.

**Yêu cầu:** Lập bảng biến đầu vào cần đo: storage, uploads, downloads, multipart, KMS requests, key count, replication, CloudTrail/logs, Region; so sánh khi bật/tắt Bucket Keys và nêu cách xác nhận quyền KMS không bị hỏng.

**Gợi ý:** Không tự nhân mỗi S3 request thành một KMS request khi chưa đo; Bucket Keys làm giảm đáng kể tần suất KMS request trong điều kiện hỗ trợ.

## 19. Kết luận

**S3 mặc định mã hóa object mới phía server bằng SSE-S3**. Khi hệ thống cần quyền sử dụng khóa độc lập, khả năng quản trị KMS và chia sẻ an toàn giữa account, **SSE-KMS với customer managed key** thường là lựa chọn đáng đánh giá; **DSSE-KMS** đáp ứng yêu cầu mã hóa hai lớp chuyên biệt. Kết quả truy cập phụ thuộc đồng thời vào **quyền S3, quyền AWS KMS, trạng thái khóa, điều kiện request và các lớp Deny**.

Thao tác thiết kế đáng tin cậy là: **xác định yêu cầu → chọn chế độ mã hóa/key → cấu hình bucket/role/key policy → thử upload và download → giám sát, sao lưu, phục hồi → tối ưu chi phí**. Trong hệ sinh thái AWS, IAM, VPC, Region/AZ, Lambda/ECS/EC2, S3, CloudWatch và AWS Budgets phải được đánh giá cùng nhau để bảo đảm ứng dụng **an toàn, giám sát được, khôi phục được và vận hành trong ngân sách**.

### Tài liệu AWS chính thức để tham khảo khi triển khai

- [Protecting data with server-side encryption — Amazon S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/serv-side-encryption.html)
- [Using SSE-KMS encryption](https://docs.aws.amazon.com/AmazonS3/latest/userguide/UsingKMSEncryption.html)
- [S3 Bucket Keys](https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucket-key.html)
- [Using server-side encryption with dual-layer encryption keys](https://docs.aws.amazon.com/AmazonS3/latest/userguide/dual-layer-server-side-encryption.html)
- [Setting default server-side encryption behavior for S3 buckets](https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucket-encryption.html)
- [Replicating objects created with server-side encryption](https://docs.aws.amazon.com/AmazonS3/latest/userguide/replication-config-for-kms-objects.html)
- [AWS KMS key policies](https://docs.aws.amazon.com/kms/latest/developerguide/key-policies.html)
- [AWS KMS cross-account access](https://docs.aws.amazon.com/kms/latest/developerguide/key-policy-modifying-external-accounts.html)
- [AWS KMS encryption context](https://docs.aws.amazon.com/kms/latest/developerguide/encrypt_context.html)
- [AWS KMS permissions](https://docs.aws.amazon.com/kms/latest/developerguide/kms-api-permissions-reference.html)
- [AWS CLI S3 API command reference](https://docs.aws.amazon.com/cli/latest/reference/s3api/)
- [AWS KMS pricing](https://aws.amazon.com/kms/pricing/) và [Amazon S3 pricing](https://aws.amazon.com/s3/pricing/)

Quyền theo API, biểu giá, chế độ mã hóa và tính năng hỗ trợ có thể thay đổi theo Region, loại bucket và thời điểm. Luôn kiểm tra tài liệu mới nhất và policy thực tế trước khi triển khai production.
