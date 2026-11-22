# KMS grant, encryption context và quyền liên tài khoản

AWS Key Management Service (AWS KMS) kiểm soát việc sử dụng khóa bằng key policy, IAM policy và grant. Khi ứng dụng cần quyền tạm thời, cần ràng buộc thao tác giải mã theo ngữ cảnh dữ liệu, hoặc cần dùng khóa do một AWS account khác sở hữu, người thiết kế phải phối hợp đúng các cơ chế này. Một cấu hình thiếu quyền ở một phía thường dẫn đến `AccessDeniedException`; một cấu hình quá rộng có thể cho phép principal sử dụng khóa ngoài phạm vi dự kiến.

Sau bài học, người học có thể:

- Giải thích grant, grantee, grant token, retiring principal và cách thu hồi grant.
- Dùng encryption context để gắn dữ liệu mã hóa với ngữ cảnh nghiệp vụ và giới hạn quyền.
- Thiết kế quyền sử dụng KMS key giữa hai AWS account bằng key policy và IAM policy.
- Kiểm tra, xử lý lỗi quyền và quản lý vòng đời quyền truy cập theo nguyên tắc đặc quyền tối thiểu.

## 1. Mô hình kiểm soát quyền trong AWS KMS

Mỗi KMS key luôn có một **key policy**. Đây là chính sách tài nguyên gắn trực tiếp với key và là nền tảng để xác định ai được sử dụng key, được gọi thao tác nào. Không có principal nào tự động có quyền với key, kể cả người tạo key hoặc root user của account sở hữu key.

Ba cơ chế thường phối hợp với nhau:

| Cơ chế | Vai trò | Khi nên dùng |
|---|---|---|
| Key policy | Xác định quyền ở phía KMS key; có thể chỉ định principal trực tiếp hoặc cho phép account dùng IAM policy để phân quyền | Quyền nền tảng, quản trị key, chia sẻ key giữa account |
| IAM policy | Gắn với user hoặc role để cho phép hay từ chối principal thực hiện thao tác | Quản lý quyền theo nhóm role, ứng dụng hoặc workload |
| Grant | Cấp một tập thao tác cụ thể cho một grantee trên một key; có thể tạo và kết thúc qua API | Quyền tạm thời, quyền cho dịch vụ AWS tích hợp KMS, quyền thay đổi theo vòng đời tài nguyên |

Một `Allow` trong IAM policy không tự tạo quyền dùng KMS key nếu key policy chưa cho phép account sử dụng IAM policy hoặc chưa cấp quyền phù hợp cho principal. Tương tự, grant không thể ghi đè một lệnh `Deny` có hiệu lực. AWS KMS xét các chính sách và grant áp dụng cho yêu cầu; yêu cầu chỉ thành công khi có quyền cho phép phù hợp và không bị từ chối.

Key policy có phạm vi Region: policy của một key chỉ kiểm soát key đó trong Region chứa key. Vì vậy, khi kiểm tra lỗi, hãy xác nhận đúng key ARN, account và Region trước khi phân tích các statement.

## 2. KMS grant: cấp quyền có phạm vi hẹp

### 2.1. Grant là gì?

Grant là một cơ chế cấp quyền cho một principal hoặc AWS service principal thực hiện một số thao tác được hỗ trợ trên đúng một KMS key. Mỗi grant có một grantee và chỉ cho phép thao tác được liệt kê. Grant không có chức năng từ chối quyền.

Một grant thường có các thành phần sau:

- `KeyId`: key mà grant áp dụng.
- `GranteePrincipal` hoặc `GranteeServicePrincipal`: principal nhận quyền. Chỉ chọn một trong hai trường này.
- `Operations`: các thao tác được phép, ví dụ `Decrypt`, `Encrypt`, `GenerateDataKey` hoặc `DescribeKey`.
- `Constraints`: điều kiện giới hạn grant, chẳng hạn encryption context hoặc `SourceArn`.
- `RetiringPrincipal` hoặc `RetiringServicePrincipal`: principal được chỉ định để kết thúc grant khi không còn cần quyền.
- `GrantId` và `GrantToken`: giá trị AWS KMS trả về khi tạo grant; dùng cho các mục đích quản lý và sử dụng grant.

Grantee principal có thể là IAM user, IAM role, assumed role user hoặc account principal. Grantee có thể thuộc account sở hữu key hoặc account khác. IAM group và AWS Organization không phải grantee principal hợp lệ. Khi cấp quyền cho workload, nên ưu tiên IAM role với thông tin xác thực tạm thời thay vì IAM user có access key dài hạn. Khi dùng `GranteeServicePrincipal`, request tạo grant phải có grant constraint `SourceArn` và phải chỉ định `RetiringPrincipal` hoặc `RetiringServicePrincipal`.

Grant chỉ chấp nhận các grant operation mà loại key hỗ trợ. Ví dụ, grant cho symmetric encryption key có thể cấp `Encrypt`, `Decrypt` và `GenerateDataKey`; các thao tác `Sign` hoặc `Verify` không phù hợp với loại key này. Nếu yêu cầu một operation không được key hỗ trợ, `CreateGrant` sẽ thất bại.

### 2.2. Tạo grant có ràng buộc encryption context

Giả sử role `InvoiceWorker` cần giải mã dữ liệu hóa đơn bằng một symmetric KMS key. Ta chỉ muốn role này giải mã ciphertext mang encryption context `Application=Billing`. Quản trị viên có thể tạo grant như sau:

```bash
aws kms create-grant \
  --key-id arn:aws:kms:ap-southeast-1:111122223333:key/11111111-2222-3333-4444-555555555555 \
  --grantee-principal arn:aws:iam::111122223333:role/InvoiceWorker \
  --operations Decrypt \
  --retiring-principal arn:aws:iam::111122223333:role/SecurityAdmin \
  --constraints EncryptionContextSubset={Application=Billing}
```

Trong ví dụ:

- `InvoiceWorker` chỉ nhận quyền `Decrypt` trên key được chỉ định.
- `EncryptionContextSubset` yêu cầu request giải mã phải có cặp `Application=Billing`; request có thể kèm thêm các cặp context khác.
- `SecurityAdmin` có thể retire grant khi công việc kết thúc.
- Principal chạy lệnh phải có quyền `kms:CreateGrant` trên key.

Kết quả `CreateGrant` có `GrantId` và `GrantToken`. Lưu `GrantId` để tra cứu hoặc revoke grant sau này. Nếu ứng dụng cần sử dụng grant ngay sau khi tạo, truyền `GrantToken` vào request KMS tương ứng trong thời gian grant chưa lan truyền đầy đủ.

Ví dụ gọi giải mã với grant token:

```bash
aws kms decrypt \
  --key-id arn:aws:kms:ap-southeast-1:111122223333:key/11111111-2222-3333-4444-555555555555 \
  --ciphertext-blob fileb://ciphertext.bin \
  --encryption-context Application=Billing \
  --grant-tokens "$GRANT_TOKEN"
```

`$GRANT_TOKEN` ở đây là token được lưu từ phản hồi `CreateGrant`. Không cần gửi token mãi mãi: khi grant đã lan truyền trong AWS KMS, grantee có thể sử dụng quyền của grant mà không cần token.

### 2.3. Grant token và eventual consistency

AWS KMS sử dụng mô hình eventual consistency. Sau khi tạo, retire hoặc revoke grant, thay đổi có thể cần một khoảng thời gian ngắn để có hiệu lực trên toàn hệ thống; thường chỉ vài giây nhưng đôi khi có thể kéo dài vài phút. Nếu grantee gọi KMS ngay sau `CreateGrant`, request có thể nhận `AccessDeniedException` dù grant đã được tạo thành công.

Grant token cho phép request tham chiếu đến grant mới ngay lập tức. Token là chuỗi định danh không tiết lộ nội dung grant. Chỉ thao tác `CreateGrant` trả về grant token; `ListGrants` trả về grant ID chứ không trả token. Ứng dụng cần lưu token từ phản hồi tạo grant nếu phải dùng quyền ngay trong cùng luồng xử lý.

Không nên giải quyết lỗi lan truyền bằng cách mở rộng policy một cách vội vàng. Trước tiên hãy kiểm tra phản hồi `CreateGrant`, key ARN, grantee, operation, constraint và việc request có truyền grant token hay chưa.

### 2.4. Kết thúc grant: retire và revoke

Cả retire và revoke đều xóa grant, do đó các quyền chỉ đến từ grant đó không còn hiệu lực sau khi thay đổi được lan truyền.

- **Retire** thường do retiring principal được chỉ định trong grant thực hiện, thường là workload hoặc principal được giao trách nhiệm kết thúc quyền.
- **Revoke** thường do key administrator hoặc principal có quyền quản trị grant thực hiện khi cần chấm dứt quyền từ phía chủ sở hữu key.

Có thể dùng `ListGrants` để tìm grant ID trước khi quản lý grant. Ví dụ:

```bash
aws kms list-grants \
  --key-id arn:aws:kms:ap-southeast-1:111122223333:key/11111111-2222-3333-4444-555555555555

aws kms retire-grant \
  --key-id arn:aws:kms:ap-southeast-1:111122223333:key/11111111-2222-3333-4444-555555555555 \
  --grant-id GRANT_ID
```

Chỉ retire hoặc revoke sau khi xác định đúng key và grant. Nếu grant được tạo cho dịch vụ AWS, cần tuân theo vòng đời tài nguyên và hướng dẫn của dịch vụ đó; xóa grant đang được dịch vụ sử dụng có thể làm thao tác trên tài nguyên thất bại.

Quyền `kms:CreateGrant` có tác động bảo mật lớn: principal được phép tạo grant có thể cấp tiếp quyền sử dụng key cho principal khác, kể cả AWS service. Hãy giới hạn ai được tạo grant, các operation được cấp và điều kiện grant. Khi cấp quyền cho dịch vụ AWS, policy thường cần giới hạn `kms:CreateGrant` bằng điều kiện như `kms:GrantIsForAWSResource`; yêu cầu cụ thể phụ thuộc dịch vụ tích hợp.

## 3. Encryption context: gắn ciphertext với ngữ cảnh dữ liệu

### 3.1. Encryption context hoạt động thế nào?

Encryption context là tập cặp key-value dạng chuỗi mà ứng dụng truyền vào các thao tác mật mã của AWS KMS khi sử dụng **symmetric encryption KMS key**. KMS dùng context như additional authenticated data (AAD): context được ràng buộc về mặt mật mã với ciphertext, giúp kiểm tra rằng dữ liệu được giải mã trong đúng ngữ cảnh đã dùng khi mã hóa.

Ví dụ, khi mã hóa dữ liệu hóa đơn, ứng dụng có thể truyền:

```json
{
  "Application": "Billing",
  "Environment": "Production",
  "RecordType": "Invoice"
}
```

Khi giải mã, ứng dụng phải truyền lại cùng tập cặp key-value. Giá trị phải khớp chính xác và phân biệt chữ hoa chữ thường; thứ tự các cặp trong context không quan trọng. Nếu thiếu một cặp, đổi giá trị hoặc đổi cách viết hoa/thường, thao tác giải mã sẽ thất bại.

Encryption context có ba đặc điểm cần nhớ:

1. **Không bí mật.** Context không được mã hóa và có thể xuất hiện ở dạng plaintext trong AWS CloudTrail log. Không đưa mật khẩu, access token, số thẻ, thông tin cá nhân hoặc dữ liệu nhạy cảm vào context.
2. **Có tính toàn vẹn.** Context được ràng buộc với ciphertext như AAD. Một ciphertext được tạo cho `Application=Billing` sẽ không giải mã thành công nếu request dùng `Application=Analytics`.
3. **Có thể dùng để phân quyền.** Key policy, IAM policy và grant có thể đặt điều kiện dựa trên encryption context để giới hạn thao tác chỉ cho một loại dữ liệu hoặc ứng dụng.

Encryption context không được hỗ trợ trong thao tác mật mã với asymmetric KMS key hoặc HMAC KMS key. Không truyền context cho các loại key này.

### 3.2. Mã hóa và giải mã với context

Ví dụ sau tạo data key cho ứng dụng xử lý hóa đơn. AWS KMS trả về plaintext data key và bản mã hóa của data key; ứng dụng dùng plaintext data key để mã hóa dữ liệu trong bộ nhớ rồi loại bỏ bản rõ theo quy trình quản lý khóa của ứng dụng.

```bash
aws kms generate-data-key \
  --key-id arn:aws:kms:ap-southeast-1:111122223333:key/11111111-2222-3333-4444-555555555555 \
  --key-spec AES_256 \
  --encryption-context Application=Billing,RecordType=Invoice
```

Khi cần giải mã encrypted data key, ứng dụng phải cung cấp cùng context:

```bash
aws kms decrypt \
  --key-id arn:aws:kms:ap-southeast-1:111122223333:key/11111111-2222-3333-4444-555555555555 \
  --ciphertext-blob fileb://encrypted-data-key.bin \
  --encryption-context Application=Billing,RecordType=Invoice
```

Đối với dữ liệu được mã hóa bằng envelope encryption, hãy lưu hoặc tái tạo context theo một quy ước ổn định cùng metadata của ciphertext. Nếu ứng dụng thay đổi tên trường hoặc giá trị context giữa các phiên bản, dữ liệu cũ có thể không giải mã được. Vì vậy, cần quản lý phiên bản schema context và kiểm thử quy trình khôi phục dữ liệu trước khi triển khai thay đổi.

### 3.3. Ràng buộc encryption context trong grant

Grant hỗ trợ hai loại encryption context constraint. Cả hai chỉ áp dụng cho symmetric encryption KMS key:

| Constraint | Quy tắc | Trường hợp sử dụng |
|---|---|---|
| `EncryptionContextEquals` | Request phải chứa chính xác toàn bộ tập cặp key-value được khai báo; so khớp phân biệt hoa thường | Chỉ cho phép thao tác với một context cố định |
| `EncryptionContextSubset` | Request phải chứa mọi cặp đã khai báo; có thể có thêm cặp khác | Bắt buộc một nhãn nghiệp vụ nhưng cho phép metadata bổ sung |

Ví dụ `EncryptionContextEquals={Application=Billing,Environment=Production}` chỉ chấp nhận context có đúng hai cặp trên. Nếu request thêm `RecordType=Invoice`, grant này không khớp. Với `EncryptionContextSubset={Application=Billing}`, cả context chỉ có `Application=Billing` và context có thêm `Environment=Production` đều được chấp nhận.

Constraint context được bỏ qua đối với operation không nhận encryption context như `DescribeKey` và `RetireGrant`. Nếu grant cho phép `CreateGrant`, các grant được tạo tiếp phải có encryption context constraint nghiêm ngặt tương đương hoặc chặt hơn để không mở rộng quyền được ủy quyền.

### 3.4. Ràng buộc context trong policy

Có thể dùng condition key `kms:EncryptionContext:context-key` trong key policy hoặc IAM policy để yêu cầu một cặp context cụ thể. Ví dụ statement dưới đây chỉ cho phép role giải mã khi request có `Application=Billing`:

```json
{
  "Effect": "Allow",
  "Principal": {
    "AWS": "arn:aws:iam::111122223333:role/InvoiceWorker"
  },
  "Action": "kms:Decrypt",
  "Resource": "*",
  "Condition": {
    "StringEquals": {
      "kms:EncryptionContext:Application": "Billing"
    }
  }
}
```

Condition này yêu cầu cặp `Application=Billing`, nhưng vẫn cho phép request có thêm context pair khác. Nếu cần kiểm soát cả tập key được phép xuất hiện, có thể phối hợp `kms:EncryptionContextKeys` với các condition phù hợp. `kms:EncryptionContextKeys` là condition key đa giá trị; `kms:EncryptionContext:context-key` là condition key đơn giá trị. Không dùng `ForAllValues` hoặc `ForAnyValue` với condition key đơn giá trị `kms:EncryptionContext:context-key`, vì có thể tạo policy cho phép request thiếu context ngoài ý muốn.

Cần phân biệt cách so khớp trong thao tác giải mã với cách so khớp trong policy. Context truyền vào thao tác giải mã luôn phải khớp chính xác và phân biệt hoa thường với context ban đầu. Trong policy, tên condition key không phân biệt hoa thường; độ nhạy hoa thường của giá trị phụ thuộc condition operator, ví dụ `StringEquals` phân biệt hoa thường.

## 4. Cấp quyền sử dụng KMS key giữa các AWS account

### 4.1. Hai phía cùng phải cho phép

Giả sử account `111122223333` sở hữu một KMS key trong Region `ap-southeast-1`, còn account `444455556666` có ứng dụng cần mã hóa và giải mã dữ liệu bằng key đó.

Với cách chia sẻ bằng key policy, quyền liên tài khoản cần hai phần:

1. **Key policy ở account sở hữu key** cho phép account bên ngoài hoặc role cụ thể sử dụng key với những operation được chọn.
2. **IAM policy ở account gọi** gắn vào user hoặc role để cho phép principal đó gọi các operation trên key ARN của account sở hữu.

Key policy xác định phạm vi quyền mà account bên ngoài có thể nhận. IAM policy ở account bên ngoài quyết định user hoặc role nào thực sự được dùng các quyền đó. Chỉ sửa một trong hai phía là chưa đủ.

Với customer managed key, account sở hữu cũng có thể chia sẻ key qua AWS Resource Access Manager (AWS RAM). AWS RAM tạo và quản lý key policy bổ sung có tên `AWS_RAM`; account nhận vẫn cần IAM policy cho principal sử dụng key và chỉ được thực hiện các operation trong quyền chia sẻ.

Khi `Principal` trong key policy là `arn:aws:iam::444455556666:root`, đây là **account principal** đại diện cho account `444455556666`, không chỉ riêng root user. Statement này cho phép quản trị viên IAM của account đó dùng IAM policy để phân quyền tiếp trong phạm vi các operation đã được key policy cho phép.

### 4.2. Ví dụ key policy ở account sở hữu key

Thêm statement sau vào key policy của key thuộc account `111122223333`:

```json
{
  "Sid": "AllowBillingAccountUseOfKey",
  "Effect": "Allow",
  "Principal": {
    "AWS": "arn:aws:iam::444455556666:root"
  },
  "Action": [
    "kms:Encrypt",
    "kms:Decrypt",
    "kms:ReEncrypt*",
    "kms:GenerateDataKey*",
    "kms:DescribeKey"
  ],
  "Resource": "*",
  "Condition": {
    "StringEquals": {
      "kms:EncryptionContext:Application": "Billing"
    }
  }
}
```

Statement này cho phép account `444455556666` sử dụng các thao tác được liệt kê khi request có `Application=Billing`. `Resource` trong key policy là `*` vì policy đã gắn với một key cụ thể. Ví dụ này minh họa symmetric encryption key; hãy chọn operation theo loại key và nhu cầu thực tế.

Nếu chỉ muốn cấp quyền cho một role bên ngoài, có thể đặt ARN role đó trong `Principal` thay cho account principal. Cách này giới hạn phạm vi phân quyền chặt hơn, nhưng khi thêm hoặc thay role, cần cập nhật key policy ở account sở hữu key.

### 4.3. Ví dụ IAM policy ở account sử dụng key

Gắn IAM policy sau vào role ứng dụng trong account `444455556666`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "UseBillingKeyInOwnerAccount",
      "Effect": "Allow",
      "Action": [
        "kms:Encrypt",
        "kms:Decrypt",
        "kms:ReEncrypt*",
        "kms:GenerateDataKey*",
        "kms:DescribeKey"
      ],
      "Resource": "arn:aws:kms:ap-southeast-1:111122223333:key/11111111-2222-3333-4444-555555555555"
    }
  ]
}
```

IAM policy sử dụng key ARN đầy đủ để chỉ định đúng key ở account và Region sở hữu. Role ứng dụng vẫn phải gửi encryption context đáp ứng condition trong key policy. Việc IAM policy cho phép `kms:Decrypt` không thể vượt qua điều kiện `Application=Billing` của key policy.

### 4.4. Giới hạn của quyền liên tài khoản

Quyền liên tài khoản đối với KMS key chỉ có hiệu lực với các nhóm operation được AWS KMS hỗ trợ, gồm:

- Các thao tác mật mã như `Encrypt`, `Decrypt`, `ReEncrypt` và `GenerateDataKey` phù hợp với loại key.
- `CreateGrant`, `DescribeKey`, `GetKeyRotationStatus`, `GetPublicKey`, `ListGrants`, `RetireGrant` và `RevokeGrant`.

Cấp quyền `kms:ListKeys` hoặc `kms:ScheduleKeyDeletion` cho principal ở account khác không làm các thao tác đó trở nên hợp lệ trên key của account sở hữu. Hãy đối chiếu cột Cross-account use trong tài liệu quyền AWS KMS trước khi thêm operation vào policy.

Account bên ngoài cũng phải được bật Region chứa key. Khi gọi thao tác cross-account, dùng key ARN để xác định key. Nếu ứng dụng sử dụng KMS key thông qua một AWS service như Amazon S3 hoặc AWS Secrets Manager, cần cấp thêm quyền cho service và principal theo hướng dẫn mã hóa của chính service đó. Ví dụ policy tổng quát ở trên không thay thế danh sách quyền riêng của từng dịch vụ.

### 4.5. Dùng grant cho principal ở account khác

Grantee của grant có thể thuộc account khác với account sở hữu key. Cách này hữu ích khi quyền cần cấp theo thời hạn hoặc thay đổi theo vòng đời workload. Tuy nhiên, grant không loại bỏ yêu cầu phân quyền IAM ở account gọi: principal bên ngoài vẫn cần identity-based policy cho phép gọi operation trên key ARN. Grant phải được tạo bởi principal có `kms:CreateGrant`, và grant chỉ nên liệt kê operation cùng constraint cần thiết.

Nếu chọn chia sẻ key lâu dài, key policy cộng IAM policy thường dễ kiểm tra và quản trị. Nếu chọn grant, hãy xác định rõ ai tạo grant, ai là grantee, ai được retire, constraint nào bắt buộc và quy trình thu hồi khi workload kết thúc. Tránh cấp `kms:CreateGrant` rộng cho role ứng dụng nếu role đó không cần ủy quyền tiếp.

## 5. Quy trình thiết kế và vận hành

Có thể áp dụng quy trình sau khi một ứng dụng cần sử dụng KMS key:

1. **Xác định chủ sở hữu và người gọi.** Ghi lại account ID, role ARN, Region và key ARN. Xác nhận account nào sở hữu key và account nào gửi request.
2. **Chọn operation tối thiểu.** Ứng dụng chỉ mã hóa thì không tự động cấp `Decrypt`; ứng dụng chỉ đọc dữ liệu thì không cần `ScheduleKeyDeletion` hoặc quyền quản trị key.
3. **Chọn cơ chế cấp quyền.** Dùng key policy và IAM policy cho quyền ổn định; dùng grant cho quyền có vòng đời rõ ràng hoặc cho tích hợp dịch vụ cần grant.
4. **Thiết kế encryption context.** Chọn tên và giá trị ổn định, không nhạy cảm, phản ánh mục đích hoặc loại dữ liệu. Đảm bảo mọi luồng mã hóa và giải mã dùng cùng quy ước.
5. **Thêm điều kiện và giới hạn.** Dùng grant constraint hoặc policy condition để ràng buộc context. Với service principal, giới hạn nguồn request bằng `SourceArn` theo yêu cầu của KMS.
6. **Kiểm thử bằng role thật.** Thử request hợp lệ, request thiếu context, request sai context và request từ role không được cấp quyền. Xác nhận chỉ request hợp lệ thành công.
7. **Theo dõi và kết thúc quyền.** Dùng CloudTrail để xem hoạt động KMS; kiểm tra grant bằng `ListGrants`; retire hoặc revoke grant khi không còn nhu cầu. Thao tác cross-account với key có thể được ghi nhận trong CloudTrail ở cả account gọi và account sở hữu key.

Khi cấp quyền `kms:CreateGrant` cho dịch vụ AWS, chỉ cho phép các trường hợp cần thiết. Một mẫu điều kiện thường gặp là `kms:GrantIsForAWSResource=true`, nhưng phải xác minh dịch vụ cụ thể cần những operation nào và có yêu cầu điều kiện bổ sung hay không.

## 6. Xử lý lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| `AccessDeniedException` khi dùng key trong cùng account | Key policy chưa cho phép IAM policy hoặc principal; thiếu IAM `Allow`; có explicit `Deny` | Kiểm tra key policy, IAM policy, permission boundary, SCP và các điều kiện áp dụng |
| `AccessDeniedException` khi dùng key từ account khác | Thiếu quyền ở key policy phía chủ sở hữu hoặc thiếu IAM policy phía caller | Xác nhận account principal/role trong key policy và IAM policy gắn đúng role ở account gọi |
| Giải mã thất bại dù có `kms:Decrypt` | Encryption context thiếu, sai giá trị hoặc sai chữ hoa/thường | So sánh context của thao tác mã hóa và giải mã; kiểm tra cả grant constraint và policy condition |
| Vừa tạo grant nhưng request bị từ chối | Grant chưa lan truyền; request chưa gửi grant token | Lấy token từ phản hồi `CreateGrant`, truyền token vào request và kiểm tra lại sau khi grant lan truyền |
| `CreateGrant` trả lỗi validation | Operation không được key hỗ trợ hoặc tham số grantee/constraint không hợp lệ | Kiểm tra loại key, danh sách grant operation và yêu cầu `SourceArn`/retiring principal nếu dùng service principal |
| Dịch vụ AWS không dùng được key | Policy chưa có quyền hoặc grant mà dịch vụ yêu cầu; thiếu điều kiện nguồn | Đọc hướng dẫn mã hóa của dịch vụ, xác minh `kms:CreateGrant`, `kms:GrantIsForAWSResource` và `SourceArn` khi cần |
| Principal bên ngoài gọi được một số API nhưng không gọi được API quản trị | API không hỗ trợ cross-account | Kiểm tra cột Cross-account use của operation trong AWS KMS permissions reference |

Không nên khắc phục lỗi bằng cách đặt `Principal` thành `*`, cấp `kms:*` hoặc bỏ điều kiện context. Hãy xác định chính xác lớp quyền đang thiếu và chỉ sửa statement liên quan.

## 7. Bài tập tình huống

Một công ty có hai account:

- Account `111122223333` sở hữu symmetric KMS key `BillingKey` ở `ap-southeast-1`.
- Account `444455556666` chạy role `InvoiceWorker` để giải mã data key của hóa đơn.
- Dữ liệu hóa đơn luôn dùng encryption context `Application=Billing` và `RecordType=Invoice`.
- Nhóm bảo mật muốn role chỉ có quyền giải mã dữ liệu hóa đơn và có thể kết thúc quyền khi workload bị gỡ bỏ.

**Yêu cầu:** Đề xuất cách cấp quyền, constraint phù hợp và cách kết thúc quyền.

**Gợi ý lời giải:**

1. Ở account sở hữu key, cho phép account `444455556666` hoặc trực tiếp role `InvoiceWorker` sử dụng `kms:Decrypt` trên key. Có thể thêm condition yêu cầu `Application=Billing` và `RecordType=Invoice`.
2. Ở account `444455556666`, gắn IAM policy cho role `InvoiceWorker` với action `kms:Decrypt` và resource là key ARN đầy đủ của account `111122223333`.
3. Nếu cần quyền có thời hạn, tạo grant cho `InvoiceWorker` với operation `Decrypt`, chỉ định retiring principal và dùng `EncryptionContextEquals` để buộc đúng hai cặp context. Nếu workload có thêm context pair hợp lệ khác, cân nhắc `EncryptionContextSubset` và đánh giá phạm vi mở rộng.
4. Khi grant mới tạo chưa lan truyền, dùng `GrantToken` trả về từ `CreateGrant` cho request giải mã đầu tiên.
5. Khi workload kết thúc, retiring principal gọi `RetireGrant`; key administrator có thể `RevokeGrant` nếu cần chấm dứt quyền từ phía quản trị. Kiểm tra grant đã được xóa và thử lại request để xác nhận quyền không còn hiệu lực.

**Câu hỏi tự kiểm tra:**

1. Vì sao một IAM policy `Allow kms:Decrypt` trong account gọi chưa đủ để sử dụng key của account khác?
2. `EncryptionContextEquals` khác `EncryptionContextSubset` ở điểm nào?
3. Grant token giải quyết vấn đề gì và khi nào grantee có thể không cần truyền token nữa?
4. Vì sao không nên đặt mã khách hàng hoặc thông tin cá nhân vào encryption context?

## 8. Tài liệu tham khảo

- [Grants in AWS KMS](https://docs.aws.amazon.com/kms/latest/developerguide/grants.html)
- [Creating grants and using grant constraints](https://docs.aws.amazon.com/kms/latest/developerguide/create-grant-overview.html)
- [Encryption context](https://docs.aws.amazon.com/kms/latest/developerguide/encrypt_context.html)
- [AWS KMS condition keys](https://docs.aws.amazon.com/kms/latest/developerguide/conditions-kms.html)
- [Allowing users in other accounts to use a KMS key](https://docs.aws.amazon.com/kms/latest/developerguide/key-policy-modifying-external-accounts.html)
- [Troubleshooting AWS KMS permissions](https://docs.aws.amazon.com/kms/latest/developerguide/policy-evaluation.html)
