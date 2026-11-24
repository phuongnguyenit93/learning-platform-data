# Key management boundary

## 1. Ranh giới quản lý khóa là gì?

Trong một hệ thống khôi phục tài khoản, **key management boundary** là ranh giới xác định thành phần nào được quản lý hoặc sử dụng khóa mật mã, được thực hiện thao tác gì, trên dữ liệu nào và trong điều kiện nào.

Ranh giới này bao gồm cả:

- Nơi vật liệu khóa được tạo, lưu và xử lý.
- Danh tính dịch vụ hoặc con người có quyền gọi thao tác mật mã.
- Quyền thay đổi chính sách, cấp quyền và vòng đời khóa.
- Những dữ liệu nhạy cảm đi ra khỏi thành phần giữ khóa.
- Cách phát hiện, giới hạn và xử lý việc sử dụng khóa sai mục đích.

Một khóa nằm trong KMS hoặc HSM có thể khó bị trích xuất hơn khóa nằm trong file cấu hình. Tuy nhiên, nếu một ứng dụng bị chiếm quyền vẫn gọi được giải mã hoặc ký tùy ý, kẻ tấn công có thể sử dụng khóa mà không cần lấy được các byte của khóa.

Vì vậy, cần phân biệt:

```text
không đọc được vật liệu khóa
    khác với
không sử dụng được quyền của khóa
```

OWASP khuyến nghị xác định các thành phần xử lý vật liệu khóa, giới hạn quyền theo nhu cầu và phân tách mục đích sử dụng khóa. Xem [OWASP Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html).

Các thành phần và tên khóa trong bài là một thiết kế tham khảo cho khôi phục tài khoản. Chúng giúp làm rõ trách nhiệm, không phải sơ đồ triển khai bắt buộc cho mọi sản phẩm.

## 2. Phân biệt khóa hệ thống, token và khóa của người dùng

Một luồng khôi phục có nhiều loại bí mật với chủ sở hữu và vòng đời khác nhau.

| Loại dữ liệu | Ví dụ | Chủ thể quản lý và mục đích |
| --- | --- | --- |
| Token khôi phục | Bí mật dùng một lần trong liên kết | Dịch vụ cấp cho một yêu cầu và phạm vi cụ thể |
| Khóa tạo bộ kiểm chứng | Khóa HMAC cho verifier | Hệ thống dùng để kiểm chứng bí mật token |
| Khóa mã hóa payload gửi | Khóa bảo vệ token trong outbox | Hệ thống dùng để giữ bí mật trong thời gian chuyển thông điệp |
| Khóa ký assertion khôi phục | Private key của bên phát hành | Hệ thống dùng để xác thực nguồn một quyền hoặc kết quả |
| Khóa bảo vệ khóa dữ liệu | KEK bảo vệ DEK | Hạ tầng quản lý khóa dùng cho envelope encryption |
| Khóa riêng của passkey | Khóa do authenticator quản lý | Thuộc cơ chế xác thực của người dùng, không phải khóa mã hóa token của backend |

Token dùng một lần không phải khóa chủ của dịch vụ. Xóa token không có nghĩa đã xóa khóa bảo vệ các token khác; luân chuyển khóa cũng không tự đánh dấu mọi token cũ đã dùng.

Khôi phục mật khẩu của người dùng không được tự cấp quyền quản trị KMS. Tương tự, một nhân viên hỗ trợ khôi phục tài khoản không nên mặc nhiên có khả năng lấy khóa ký hoặc giải mã toàn bộ payload khôi phục.

Với passkey, backend không dùng token khôi phục để tái tạo private key của người dùng. Luồng có thể cho phép đăng ký phương thức thay thế hoặc tiếp tục bằng một cơ chế khôi phục phù hợp của nền tảng, theo bằng chứng và chính sách tương ứng.

## 3. Ba ranh giới cần xem xét riêng

### Ranh giới vật liệu khóa

Câu hỏi là: **các byte khóa bí mật có xuất hiện trong tiến trình nào?**

Một thao tác ký bằng khóa không xuất được có thể diễn ra trong HSM. Ứng dụng gửi dữ liệu, nhận chữ ký và không thấy private key.

Trong envelope encryption, khóa bảo vệ có thể nằm trong KMS, nhưng DEK dạng rõ có thể được trả về để ứng dụng mã hóa dữ liệu cục bộ. Khi đó, bộ nhớ ứng dụng nằm trong phạm vi cần bảo vệ đối với DEK.

Ví dụ, API `GenerateDataKey` thông thường của AWS KMS trả về cả bản plaintext của data key và bản được mã hóa. Điều này khác với việc mọi khóa luôn ở bên trong KMS. Xem [AWS KMS — GenerateDataKey](https://docs.aws.amazon.com/kms/latest/APIReference/API_GenerateDataKey.html).

Không nên mô tả kiến trúc là “khóa không bao giờ ra ngoài KMS” nếu DEK plaintext thực tế được ứng dụng sử dụng.

### Ranh giới quyền gọi thao tác

Câu hỏi là: **ai được yêu cầu khóa thực hiện việc gì?**

Quyền đọc ciphertext khác quyền giải mã. Quyền kiểm tra chữ ký bằng public key khác quyền tạo chữ ký. Quyền kiểm tra MAC trong một giao diện được kiểm soát cũng khác việc giữ trực tiếp khóa MAC.

Nếu verifier giữ raw key HMAC trong tiến trình, việc gọi nó là dịch vụ “chỉ kiểm tra” không ngăn tiến trình tự tính MAC. Muốn giới hạn ở mức thao tác, cần một cơ chế thực thi quyền phù hợp, chẳng hạn dịch vụ mật mã cung cấp thao tác kiểm chứng riêng và không cấp thao tác tạo MAC cho bên đó.

### Ranh giới quyết định nghiệp vụ

Câu hỏi là: **ai được quyết định rằng một tài khoản có thể được khôi phục?**

Một phép giải mã thành công chỉ chứng minh dữ liệu có thể được mở với khóa và ngữ cảnh phù hợp. Nó không chứng minh người yêu cầu đủ bằng chứng danh tính.

Một chữ ký hợp lệ chứng minh tính toàn vẹn và nguồn theo cấu hình tin cậy. Bên nhận vẫn phải kiểm tra tài khoản, tenant, mục đích, thời hạn, trạng thái dùng một lần và các điều kiện khôi phục.

Cả ba ranh giới cần khớp nhau. Tách vật liệu khóa ra khỏi ứng dụng nhưng để API ký tự do dữ liệu do client chọn vẫn có thể cấp cho client một quyền nguy hiểm.

## 4. Phân tách quyền sử dụng và quyền quản trị

Có thể chia quyền thành hai nhóm:

| Nhóm | Ví dụ | Rủi ro nếu cấp quá rộng |
| --- | --- | --- |
| Sử dụng khóa | Encrypt, Decrypt, Sign, Verify, GenerateMac, VerifyMac, tạo data key | Đọc bí mật hoặc tạo dữ liệu được hệ thống tin cậy |
| Quản trị khóa | Sửa policy, tạo grant, đổi alias, vô hiệu hóa, lập lịch xóa | Mở rộng quyền hoặc làm dịch vụ mất khả năng sử dụng dữ liệu |

Tên thao tác cụ thể phụ thuộc sản phẩm và loại khóa. Không phải hệ thống quản lý khóa nào cũng hỗ trợ mọi phép toán trong bảng.

AWS KMS phân biệt các quyền quản trị và các quyền sử dụng khóa trong mô hình key policy. Xem [AWS KMS — Default key policy](https://docs.aws.amazon.com/kms/latest/developerguide/key-policy-default.html).

Tuy nhiên, quyền quản trị có thể tạo ra quyền sử dụng gián tiếp. Nếu một người không có quyền Decrypt nhưng được tự sửa policy để cấp Decrypt cho chính mình, ranh giới phân tách chưa ngăn được đường leo thang đó.

Thiết kế cần xem xét cả:

- Ai được sửa policy hoặc tạo quyền ủy nhiệm?
- Ai được thay đổi danh tính mà workload sử dụng?
- Ai được triển khai mã chạy dưới danh tính có quyền giải mã?
- Ai được đổi key alias hoặc registry để ứng dụng dùng khóa khác?
- Ai có thể mở một đường truy cập khẩn cấp và đường đó được giới hạn ra sao?

Một quy trình phê duyệt thay đổi, vai trò tách biệt và audit độc lập có thể hỗ trợ kiểm soát các đường này. Chỉ có hai tên vai trò khác nhau chưa chứng minh có hai miền quyền độc lập.

## 5. Một sơ đồ trách nhiệm cho khôi phục tài khoản

Thiết kế minh họa:

```text
Người dùng
    |
    v
Recovery API ------> Quy trình xác minh và quyết định khôi phục
    |                                  |
    v                                  v
Token issuer --------------------> Kho token và trạng thái
    |
    v
Payload gửi được mã hóa ----------> Delivery worker ------> Kênh gửi
                                         |
                                         v
                                  Dịch vụ mật mã/KMS

Token redeemer ------------------> Kho verifier và trạng thái hiện hành
```

Một ma trận quyền có thể bắt đầu như sau:

| Thành phần | Quyền cần thiết trong mô hình | Quyền không nên có mặc định |
| --- | --- | --- |
| Recovery API công khai | Tiếp nhận yêu cầu, gọi nghiệp vụ đã giới hạn | Ký hoặc giải mã dữ liệu tùy ý theo body |
| Token issuer | Tạo token và verifier, ghi quyền đã được phê duyệt | Sửa policy khóa hoặc lấy mọi khóa khác |
| Token redeemer | Kiểm chứng token, kiểm tra quyền và hoàn tất đúng thao tác | Đọc lại mọi token plaintext đã phát hành |
| Delivery worker | Giải mã payload của công việc được giao và gửi đến đích đã ràng buộc | Ký assertion khôi phục hoặc thay bằng chứng danh tính |
| Người đọc backup | Đọc dữ liệu backup theo nhiệm vụ | Đồng thời có quyền giải mã mọi payload |
| Quản trị khóa | Quản lý vòng đời theo quy trình được kiểm soát | Tự động có quyền thao tác credential của người dùng |
| Nhân viên hỗ trợ | Thực hiện nhánh hỗ trợ được cấp quyền | Export khóa hoặc xem raw token hàng loạt |

Đây là điểm bắt đầu để phân tích, không phải một policy có thể sao chép nguyên xi. Một ứng dụng nhỏ có thể gộp một số thành phần, nhưng cần hiểu phạm vi ảnh hưởng tăng lên khi gộp quyền.

Delivery worker được phép thấy token để gửi thì bản thân nó là một thành phần được tin cậy đối với token đó. Giới hạn quyền KMS không làm mất khả năng nhìn thấy plaintext mà nghiệp vụ đã yêu cầu worker xử lý. Cần tiếp tục giới hạn công việc, thời hạn token, đích gửi và quyền truy cập dữ liệu.

## 6. Tách khóa theo mục đích, môi trường và phạm vi

Không dùng một khóa chung cho mọi chức năng chỉ vì cả hệ thống cùng gọi là “authentication”.

Một nhóm khóa tham khảo:

```text
K_recovery_verifier_prod
    tạo hoặc kiểm tra verifier token

K_recovery_delivery_prod
    mã hóa payload chờ gửi

K_recovery_assertion_signing_prod
    ký assertion khôi phục có phạm vi rõ ràng

K_recovery_wrapping_prod
    bảo vệ khóa dữ liệu theo kiến trúc envelope
```

Nếu không dùng một chức năng, không cần tạo thêm khóa chỉ để đủ danh sách. Chẳng hạn, token opaque ngẫu nhiên được kiểm chứng bằng hàm băm có thể không cần khóa HMAC cho verifier.

Các khóa của môi trường thử nghiệm cần tách khỏi production. Một workload thử nghiệm không được có khả năng dùng khóa production hoặc tạo ra token được production chấp nhận.

Phân tách theo tenant cũng là một lựa chọn:

| Cách tổ chức | Lợi ích | Điều phải đánh giá |
| --- | --- | --- |
| Một khóa cho nhiều tenant | Quản lý ít đối tượng hơn | Quyền dùng khóa có thể ảnh hưởng nhiều tenant |
| Khóa riêng cho tenant hoặc nhóm tenant | Giới hạn phạm vi một số sự cố và thao tác vòng đời | Chi phí vận hành, quota, registry và quyền truy cập |
| Khóa chung nhưng ràng buộc ngữ cảnh và policy | Có thể giới hạn thao tác theo điều kiện | Hiệu quả phụ thuộc nguồn ngữ cảnh và quyền thực tế của principal |

Khóa riêng không tự tạo cô lập nếu cùng một principal có quyền dùng tất cả khóa. Ngược lại, một trường `tenantId` trong request không tự tạo cô lập nếu principal được tự chọn mọi tenant.

Nếu cần dẫn xuất các khóa con, phải dùng cơ chế KDF được thiết kế và quản lý đúng, với phân tách miền rõ ràng. Không tự tạo khóa mới bằng cách nối tên tenant vào khóa cũ hoặc cắt một đoạn chuỗi bí mật.

## 7. Dùng ngữ cảnh để giới hạn thao tác, không chỉ để ghi nhãn

Một lệnh giải mã nên được gắn với mục đích và ngữ cảnh mong đợi, ví dụ:

```json
{
  "service": "account-recovery",
  "environment": "production",
  "purpose": "delivery-payload",
  "tenantRef": "tenant_demo_1"
}
```

Đây là dữ liệu minh họa, không chứa token, OTP hoặc email người dùng.

Ngữ cảnh có hai vai trò cần phân biệt:

1. **Ràng buộc mật mã:** ciphertext không được chấp nhận nếu ngữ cảnh được xác thực không khớp.
2. **Điều kiện cấp quyền:** principal chỉ được gọi thao tác khi điều kiện policy phù hợp.

Ở AWS KMS, encryption context của thao tác với khóa mã hóa đối xứng được gắn với ciphertext và có thể được dùng trong policy hoặc grant. Context không được mã hóa và có thể xuất hiện trong log, nên không chứa bí mật. Cơ chế này không áp dụng nguyên xi cho khóa bất đối xứng hoặc HMAC của KMS. Xem [AWS KMS — Encryption context](https://docs.aws.amazon.com/kms/latest/developerguide/encrypt_context.html).

Với chữ ký hoặc MAC, nếu cần ràng buộc tenant và mục đích trong dữ liệu được xác thực, phải định nghĩa chúng trong thông điệp theo giao thức phù hợp, đồng thời kiểm soát quyền gọi riêng.

### Ngữ cảnh do ai xác định?

Nếu một worker có quyền giải mã cho mọi tenant và được tự đặt `tenantRef`, thêm trường này chưa ngăn worker bị chiếm quyền đọc dữ liệu của các tenant khác.

Ngữ cảnh phải được đối chiếu với nguồn tin cậy: danh tính workload, công việc được giao, quyền truy cập bản ghi và các điều kiện policy tương ứng. Những phần client được phép nhập không được tự nâng thành thuộc tính cấp quyền.

AAD hoặc encryption context không thay thế authorization. Một ciphertext thuộc đúng tenant vẫn không có nghĩa mọi người dùng trong tenant được phép giải mã nó.

## 8. Thiết kế giao diện mật mã theo nghiệp vụ

Một giao diện quá rộng có thể biến dịch vụ thành nơi giải mã hộ người gửi:

```text
POST /crypto/decrypt
    keyId
    ciphertext
    context
    destination
```

Nếu API chỉ chuyển các trường đó đến KMS bằng danh tính đặc quyền của ứng dụng, người gọi có thể lợi dụng quyền của ứng dụng. Vấn đề này vẫn tồn tại dù KMS xác thực workload chính xác.

Một giao diện phù hợp hơn với việc gửi token có thể nhận **định danh công việc đã được cấp quyền**, rồi tự xác định dữ liệu và khóa cần dùng.

Mã giả:

```text
deliverRecoveryMessage(jobId, authenticatedWorkload):
    xác thực workload và quyền nhận công việc
    job = đọc công việc từ kho có thẩm quyền

    kiểm tra job thuộc phạm vi được giao cho workload
    kiểm tra request còn cho phép gửi
    kiểm tra tenant, account, purpose và thời hạn
    kiểm tra đích gửi đã được ràng buộc theo chính sách

    keyReference = chọn từ registry tin cậy của ứng dụng
    expectedContext = dựng từ dữ liệu máy chủ đã xác minh

    plaintext = giải mã payload bằng keyReference và expectedContext
    gửi đến đích của job
    kết thúc vòng đời plaintext và payload theo retention
```

Các trường `keyReference`, tenant và đích gửi không được thay thế bằng giá trị tùy ý trong request.

API cũng không trả plaintext token cho trình duyệt chỉ vì công việc gửi tồn tại. Nếu có công cụ hỗ trợ, nó nên hiển thị trạng thái và định danh truy vết phù hợp, thay vì mở một chức năng xem mọi bí mật.

### Không để registry trở thành đường chọn khóa tùy ý

Token hoặc envelope có thể chứa `kid` hay phiên bản khóa. Đây là dữ liệu dùng để tìm trong tập cấu hình được chấp nhận, không phải quyền lựa chọn bất kỳ khóa nào.

Bên nhận cần đối chiếu:

```text
issuer dự kiến
+ môi trường
+ mục đích khóa
+ thuật toán được cho phép
+ tập khóa/phiên bản được chấp nhận
```

Không diễn giải `kid` thành đường dẫn file hoặc URL tùy ý do người gửi kiểm soát. Không thử lần lượt mọi khóa của hệ thống đến khi một khóa cho kết quả thành công.

Alias có thể thay đổi theo nhà cung cấp. Cần phân biệt tên logic của khóa, định danh tài nguyên và phiên bản vật liệu khóa thực tế, rồi thiết kế cách đọc dữ liệu cũ phù hợp với semantics của nền tảng.

## 9. Ranh giới quản lý khóa trong phát hành và kiểm chứng token

### Với token opaque

Một token ngẫu nhiên được ràng buộc bằng bản ghi phía máy chủ. Nếu dùng HMAC để lưu verifier, quyền tạo HMAC không tự tạo ra một token được chấp nhận nếu kẻ gọi không thể tạo bản ghi cấp quyền hợp lệ.

Tuy nhiên, nếu cùng principal có thể tạo verifier, ghi tùy ý account ID và đánh dấu request đã được phê duyệt, nó có thể vượt qua nhiều lớp kiểm soát. Phải xét tổ hợp quyền trên cả KMS, database và dịch vụ quyết định.

### Với token hoặc assertion tự chứa có chữ ký

Một private key ký thường có ảnh hưởng trực tiếp đến khả năng tạo thông điệp được các bên nhận tin cậy. Dịch vụ có quyền ký cần giới hạn dữ liệu được ký, issuer, audience, purpose và quy trình cấp quyền.

Một dịch vụ kiểm tra chữ ký có thể chỉ cần public key. Đây là một lợi ích phân tách quyền: kiểm chứng không đòi hỏi giữ khả năng tạo chữ ký.

Dù chữ ký hợp lệ, endpoint vẫn kiểm tra phạm vi, thời gian và các trạng thái bắt buộc. Một khóa đang hoạt động không biến mọi claim được ký thành quyền khôi phục hợp lệ.

### Với MAC đối xứng

Nếu một bên giữ trực tiếp khóa MAC dùng chung, nó có thể tạo MAC theo thuật toán. Muốn giới hạn ở “chỉ kiểm tra” cần một ranh giới dịch vụ hoặc module thực thi quyền đó; đặt tên phương thức `verifyOnly` trong cùng tiến trình giữ raw key không đủ.

Chọn chữ ký hay MAC cần dựa trên mô hình tin cậy và yêu cầu của giao thức. Không thay thuật toán chỉ để tránh thiết kế quyền truy cập.

## 10. Vòng đời khóa phải đi cùng vòng đời quyền khôi phục

### Tạo và đưa khóa vào sử dụng

Khóa cần có chủ thể chịu trách nhiệm, mục đích, môi trường, thuật toán và quy tắc sử dụng rõ ràng. Workload dùng danh tính của chính nó để truy cập, thay vì dùng chung một credential quản trị dài hạn.

Không đóng gói khóa thật trong repository hoặc image để các instance đều có thể chạy. Việc dùng secret manager hay KMS cần đi cùng chính sách giới hạn principal được truy cập.

### Luân chuyển thông thường

Một kế hoạch có thể chuyển việc ký hoặc mã hóa mới sang khóa mới, trong khi chỉ cho phép một tập thao tác có giới hạn với khóa cũ để xử lý dữ liệu còn cần.

Cần phân biệt:

- Khóa còn được dùng để phát hành quyền mới không?
- Khóa còn được phép giải mã payload cũ không?
- Public key cũ còn được dùng để kiểm tra dữ liệu nào?
- Các token gắn với khóa cũ còn được hệ thống chấp nhận không?

Đổi khóa hiện hành không tự làm token cũ hết hạn. Việc chấp nhận quyền cũ là quyết định của dịch vụ khôi phục.

### Khi principal hoặc khóa bị nghi lộ

Xử lý cần xem xét cả quyền gọi lẫn vật liệu khóa:

```text
principal bị chiếm quyền
    -> chặn khả năng tiếp tục dùng quyền
    -> xác định dữ liệu/thao tác đã bị tác động
    -> xử lý token, request và credential có nguy cơ

khóa bị lộ
    -> dừng tạo dữ liệu mới dưới khóa đó
    -> áp dụng kế hoạch thay khóa và xử lý dữ liệu cũ
    -> vô hiệu hóa quyền có nguy cơ khi chính sách yêu cầu
```

Không chỉ đổi credential workload rồi coi các token đã bị đọc là an toàn trở lại. Kẻ tấn công có thể giữ raw token hoặc chữ ký đã tạo trước khi bị chặn.

Vô hiệu hóa một khóa trong KMS cũng không xóa các DEK đã được cache hoặc các bí mật đã rời khỏi dịch vụ. Phạm vi và thời gian giữ cache khóa cần được tính vào hợp đồng ứng phó sự cố.

### Mất khả dụng và khôi phục

Nếu KMS không sẵn sàng, không tự chuyển sang một khóa debug trong source hoặc cho phép khôi phục thiếu bước kiểm chứng.

Hệ thống cần chính sách retry có giới hạn, thông báo phù hợp và phương án tiếp tục được thiết kế trước. Nhánh hỗ trợ khẩn cấp vẫn phải giữ bằng chứng, phạm vi quyền và audit.

Khả năng phục hồi khóa cũng phải phù hợp với dữ liệu. Payload khôi phục ngắn hạn có thể được hủy và phát hành lại theo quy trình, trong khi dữ liệu lưu trữ dài hạn có yêu cầu khác. Không giữ mọi khóa mãi mãi chỉ vì chưa phân loại nhu cầu.

## 11. Những thành phần thường bị bỏ sót khỏi ranh giới

### Pipeline triển khai

Một principal chỉ có quyền triển khai mã vẫn có thể gây ảnh hưởng lớn nếu nó thay được chương trình chạy dưới danh tính có quyền ký hoặc giải mã.

Cần coi quyền sửa mã, cấu hình runtime, service account và cơ chế triển khai là các đường có thể dẫn tới quyền sử dụng khóa. Tách tài khoản database với KMS không đủ nếu cùng một credential CI quản trị toàn bộ hai phía.

### Bộ nhớ và công cụ chẩn đoán

DEK, token đã giải mã và kết quả ký có thể xuất hiện trong heap dump, core dump, log request hoặc công cụ theo dõi lỗi.

Một hệ thống không export được khóa gốc vẫn có thể lộ dữ liệu đã giải mã. Cần hạn chế thu thập và truy cập các bản chẩn đoán có chứa bí mật, đồng thời giảm thời gian giữ plaintext.

### Backup và môi trường khôi phục sự cố

Người đọc backup không nên mặc nhiên có quyền unwrap mọi DEK. Môi trường phục hồi cần danh tính và phạm vi quyền riêng phù hợp với nhiệm vụ.

Khôi phục database cũ có thể đưa lại token hoặc trạng thái trước khi thu hồi. Khôi phục quyền truy cập khóa không được tự khôi phục hiệu lực nghiệp vụ của các token đó.

### Nhà cung cấp kênh gửi

Kênh email hoặc SMS nhận nội dung token theo nhu cầu chuyển thông điệp. Nó trở thành một phần của phạm vi tin cậy đối với bí mật đã chuyển, dù không có quyền quản lý khóa của backend.

Cần biết dữ liệu nào rời khỏi hệ thống, được giữ bao lâu và ai có thể truy cập. Mã hóa tại database không che token khỏi bên được giao nhiệm vụ gửi plaintext đó.

## 12. Ghi nhận và đối chiếu ranh giới

Audit nên liên kết được thao tác dùng khóa với một hành động cụ thể:

```text
workloadIdentity
logicalKeyPurpose
keyReference hoặc phiên bản phù hợp
operation
recoveryRequestRef
tokenRecordRef
correlationId
timestamp
result
```

Không đưa raw key, DEK plaintext, token, OTP hoặc toàn bộ payload giải mã vào log.

Một lệnh KMS thành công chỉ chứng minh principal được policy cho phép gọi thao tác. Nó không chứng minh yêu cầu khôi phục ban đầu là hợp lệ. Muốn điều tra đầy đủ, cần nối được audit khóa với quyết định nghiệp vụ và trạng thái request.

Các tình huống minh họa để xác định ranh giới:

| Tình huống | Bảo đảm cần có trong thiết kế |
| --- | --- |
| Người đọc database lấy được ciphertext | Không mặc nhiên có quyền giải mã |
| Delivery worker yêu cầu ký assertion | Bị giới hạn bởi quyền và mục đích khóa |
| Token redeemer chỉ cần kiểm chứng | Không mặc nhiên được đọc lại mọi token plaintext |
| Quản trị viên sửa policy để tự cấp quyền | Được xem là đường thay đổi đặc quyền, có kiểm soát tương ứng |
| Workload thử nghiệm chọn khóa production | Không vượt qua ranh giới môi trường |
| Request tự chọn tenant trong context | Không được coi là bằng chứng quyền của tenant đó |
| Client gửi URL hoặc đường dẫn trong kid | Không khiến dịch vụ tải khóa tùy ý |
| KMS bị gián đoạn | Không tự bỏ điều kiện bảo mật hoặc dùng khóa tạm không được quản lý |
| Principal bị thu hồi nhưng còn cache DEK | Được tính vào phạm vi sự cố và thời gian chấp nhận rủi ro |
| Backup cũ được phục hồi | Không hồi sinh quyền khôi phục đã kết thúc |

Ranh giới quản lý khóa có giá trị khi **vật liệu khóa, quyền gọi thao tác, quyền đổi chính sách và quyết định khôi phục được gắn với trách nhiệm rõ ràng**. Việc đặt khóa trong một kho chuyên dụng là một phần của thiết kế; khả năng sử dụng khóa thực tế và tác động nghiệp vụ của nó cần được giới hạn xuyên suốt hệ thống.
