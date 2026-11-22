# Phân tách quyền quản trị khóa với quyền sử dụng dữ liệu

Trong một hệ thống chạy trên Google Cloud, nhóm bảo mật có thể chịu trách nhiệm tạo và luân chuyển khóa mã hóa, trong khi ứng dụng chỉ cần dùng khóa để mã hóa hoặc giải mã dữ liệu phục vụ nghiệp vụ. Nếu cấp cùng một quyền rộng cho cả hai nhóm, một lỗi trong ứng dụng hoặc một tài khoản bị lộ có thể dẫn đến việc thay đổi cấu hình khóa, cấp thêm quyền truy cập hoặc ảnh hưởng đến nhiều dữ liệu hơn mức cần thiết.

Thiết kế an toàn cần tách ba việc: quản lý vòng đời và chính sách của khóa, thực hiện thao tác mật mã bằng khóa, và đọc hoặc ghi dữ liệu của ứng dụng. Google Cloud IAM cho phép cấp các quyền này cho những danh tính khác nhau. Khi đặt quyền đúng phạm vi, nhóm vận hành khóa có thể quản lý tài nguyên mã hóa, còn workload chỉ được sử dụng đúng khóa mà nó cần.

## 1. Ba lớp quyền cần phân biệt

Cloud Key Management Service (Cloud KMS) tổ chức tài nguyên theo cấu trúc project, key ring, CryptoKey và key version. CryptoKey là tài nguyên đại diện cho khóa; các phiên bản của nó chứa vật liệu khóa tương ứng. IAM policy có thể được gắn ở nhiều cấp và quyền từ cấp cha có thể kế thừa xuống tài nguyên con. Vì vậy, phạm vi gắn role quan trọng không kém tên role.

| Lớp quyền | Công việc | Danh tính thường được cấp |
| --- | --- | --- |
| Quản trị khóa | Tạo key ring và CryptoKey, cấu hình luân chuyển, quản lý trạng thái key version, xem hoặc thay đổi chính sách IAM | Nhóm bảo mật hoặc nhóm nền tảng |
| Sử dụng khóa | Gọi thao tác encrypt, decrypt, sign hoặc verify tùy loại khóa | Service account của ứng dụng hoặc service agent của dịch vụ Google Cloud |
| Truy cập dữ liệu | Đọc, ghi, liệt kê hoặc quản lý đối tượng, bản ghi và bí mật nghiệp vụ | Người dùng và service account thực hiện nghiệp vụ |

Ba lớp này không thay thế cho nhau. Một ứng dụng có quyền đọc object trong Cloud Storage chưa chắc có quyền gọi Cloud KMS trực tiếp. Ngược lại, một service account được phép dùng CryptoKey cũng không tự động có quyền đọc object trong bucket hoặc truy cập dữ liệu trong cơ sở dữ liệu.

Ví dụ, project **security-prod** lưu các khóa dùng chung, còn project **orders-prod** chạy dịch vụ đơn hàng. Nhóm bảo mật quản lý khóa trong **security-prod**; service account của dịch vụ đơn hàng chỉ được dùng một CryptoKey cụ thể; quyền đọc và ghi dữ liệu đơn hàng được cấp riêng trong project chứa dữ liệu.

## 2. Chọn IAM role theo nhiệm vụ

Các predefined role của Cloud KMS giúp thể hiện rõ mục đích của từng danh tính:

| Role | Mục đích sử dụng | Nơi nên cấp |
| --- | --- | --- |
| **roles/cloudkms.admin** | Quản lý tài nguyên Cloud KMS và chính sách truy cập khóa | Project hoặc key ring thuộc phạm vi nhóm quản trị |
| **roles/cloudkms.cryptoKeyEncrypterDecrypter** | Mã hóa và giải mã bằng CryptoKey | CryptoKey cụ thể mà workload cần dùng |
| **roles/cloudkms.cryptoKeyEncrypter** | Chỉ mã hóa bằng CryptoKey | CryptoKey cụ thể, nếu workload không cần giải mã |
| **roles/cloudkms.cryptoKeyDecrypter** | Chỉ giải mã bằng CryptoKey | CryptoKey cụ thể, nếu workload chỉ xử lý dữ liệu đã mã hóa |
| **roles/cloudkms.viewer** | Xem thông tin tài nguyên Cloud KMS | Nhóm cần kiểm tra metadata mà không quản lý khóa |

Nhóm quản trị thường cần quyền quản lý key ring, CryptoKey, key version và cấu hình IAM. Ứng dụng thường chỉ cần role sử dụng khóa. Nếu một workload chỉ mã hóa dữ liệu gửi đi và không giải mã dữ liệu, có thể cân nhắc role encrypter riêng để thu hẹp quyền. Hãy kiểm tra các quyền thực tế của role và phạm vi kế thừa trong IAM policy trước khi triển khai.

Nên gắn role sử dụng khóa trực tiếp trên CryptoKey cần dùng. Cấp role ở cấp project có thể khiến service account sử dụng được nhiều khóa khác trong project, làm tăng phạm vi ảnh hưởng khi danh tính ứng dụng bị xâm phạm. Nếu một ứng dụng cần ba khóa cho ba mục đích khác nhau, hãy cấp quyền trên từng khóa tương ứng.

### Quyền thay đổi IAM policy cũng cần được kiểm soát

Tách role quản trị và role sử dụng là bước đầu. Một principal có quyền thay đổi IAM policy của key ring hoặc CryptoKey có thể thêm binding mới, kể cả binding cấp quyền sử dụng khóa cho chính principal đó. Vì vậy, nếu yêu cầu phân tách nhiệm vụ phải chặt chẽ, cần kiểm soát cả quyền **setIamPolicy**.

Có thể dùng custom role cho một số nhiệm vụ vòng đời khóa mà không bao gồm quyền thay đổi IAM policy, sau đó giao việc phê duyệt và cập nhật policy cho nhóm IAM hoặc bảo mật riêng. Với predefined role có quyền quản lý policy, hãy áp dụng quy trình phê duyệt thay đổi, rà soát định kỳ binding và theo dõi audit log. Không nên xem việc chia hai nhóm tên khác nhau là bằng chứng đủ cho separation of duties nếu một nhóm vẫn có thể tự cấp quyền cho mình.

## 3. Cấp quyền cho đúng danh tính thực hiện thao tác mật mã

Với ứng dụng gọi Cloud KMS API trực tiếp, danh tính cần được cấp quyền là service account mà ứng dụng thực sự sử dụng khi chạy. Không nên cấp role cho tài khoản cá nhân của lập trình viên rồi để ứng dụng dùng chung thông tin xác thực đó. Hãy dùng service account riêng cho từng workload hoặc ranh giới tin cậy phù hợp.

Ví dụ, dịch vụ đơn hàng chạy bằng service account **orders-api@orders-prod.iam.gserviceaccount.com** và cần mã hóa, giải mã bằng CryptoKey **orders-data-key** trong project **security-prod**. Nhóm quản trị tạo khóa và thiết lập policy; sau khi policy được phê duyệt, cấp quyền sử dụng khóa cho service account:

~~~bash
gcloud kms keys add-iam-policy-binding orders-data-key \
  --keyring=prod \
  --location=asia-southeast1 \
  --project=security-prod \
  --member="serviceAccount:orders-api@orders-prod.iam.gserviceaccount.com" \
  --role="roles/cloudkms.cryptoKeyEncrypterDecrypter"
~~~

Lệnh trên gắn role trên đúng CryptoKey trong project sở hữu khóa. Tên project, key ring, location, CryptoKey và service account trong ví dụ cần được thay bằng tài nguyên thực tế. Vị trí khóa phải tương thích với yêu cầu vị trí của dịch vụ sử dụng nó.

Ứng dụng tiếp tục nhận quyền dữ liệu ở nơi dữ liệu được lưu. Chẳng hạn, nếu ứng dụng cần đọc và ghi object, cấp role Cloud Storage phù hợp trên bucket hoặc project dữ liệu. Không cấp **roles/cloudkms.admin** cho service account chạy ứng dụng chỉ để khắc phục lỗi thiếu quyền encrypt hoặc decrypt.

Với dữ liệu lớn, ứng dụng có thể dùng envelope encryption: ứng dụng mã hóa dữ liệu bằng data encryption key (DEK), rồi dùng Cloud KMS để bảo vệ DEK bằng key encryption key (KEK). Cloud KMS bảo vệ khóa dữ liệu; ứng dụng vẫn phải kiểm soát quyền đọc dữ liệu mã hóa, lưu DEK đã được bảo vệ và xử lý plaintext trong bộ nhớ. Mô hình này không loại bỏ nhu cầu tách quyền dữ liệu và quyền sử dụng khóa.

## 4. Phân biệt ứng dụng gọi Cloud KMS với dịch vụ dùng CMEK

Không phải lúc nào service account của ứng dụng cũng trực tiếp gọi Cloud KMS. Khi bật customer-managed encryption keys (CMEK) cho một dịch vụ được quản lý như Cloud Storage, BigQuery hoặc Cloud SQL, dịch vụ Google Cloud thường thực hiện thao tác mã hóa và giải mã thông qua service agent của dịch vụ đó.

Trong trường hợp CMEK:

1. Xác định service agent mà dịch vụ quản lý tài nguyên sử dụng.
2. Cấp **roles/cloudkms.cryptoKeyEncrypterDecrypter** cho service agent trên CryptoKey được chọn.
3. Cấp quyền dữ liệu cho người dùng hoặc service account của ứng dụng trên bucket, dataset, instance hoặc tài nguyên tương ứng.
4. Giữ quyền quản trị CryptoKey trong phạm vi nhóm bảo mật hoặc nền tảng.

Ví dụ với một bucket dùng CMEK, service agent của Cloud Storage cần quyền sử dụng CryptoKey để mã hóa và giải mã object. Service account của ứng dụng cần quyền Cloud Storage để đọc hoặc ghi object theo nghiệp vụ. Ứng dụng không nhất thiết cần quyền Cloud KMS trực tiếp khi Cloud Storage thực hiện thao tác mật mã thay mặt tài nguyên.

Hãy lấy đúng service agent do dịch vụ tạo hoặc chỉ định theo hướng dẫn của dịch vụ đó; không đoán địa chỉ email service agent từ tên project. Khi cấu hình CMEK liên project, cần kiểm tra project sở hữu khóa, project chứa tài nguyên, danh tính service agent và policy trên CryptoKey.

## 5. Secret Manager có lớp quyền riêng

Secret Manager dùng để lưu và quản lý giá trị bí mật như mật khẩu, token hoặc API key. Cloud KMS dùng để quản lý khóa mật mã và thực hiện các thao tác mật mã. Hai dịch vụ có thể phối hợp, nhưng quyền truy cập secret vẫn là một lớp quyền riêng.

Ví dụ:

- Nhóm quản trị bí mật quản lý vòng đời secret và phiên bản secret.
- Service account của ứng dụng nhận **roles/secretmanager.secretAccessor** trên đúng secret cần đọc.
- Nếu secret được cấu hình CMEK, service agent của Secret Manager cần quyền sử dụng CryptoKey tương ứng.
- Ứng dụng chỉ nhận quyền Cloud KMS trực tiếp khi chính ứng dụng gọi Cloud KMS API.

Không cấp **roles/secretmanager.admin** cho ứng dụng chỉ để đọc giá trị secret. Tương tự, không cấp quyền Cloud KMS rộng cho ứng dụng chỉ vì secret đang được mã hóa bằng CMEK. Cấp đúng quyền cho danh tính thực hiện từng thao tác giúp giới hạn ảnh hưởng khi một credential bị lộ.

## 6. Luồng phân tách quyền trong một hệ thống

Sơ đồ dưới đây minh họa hai cách sử dụng khóa. Luồng bên trái là ứng dụng gọi Cloud KMS trực tiếp; luồng bên phải là dịch vụ Google Cloud sử dụng CMEK thông qua service agent.

~~~mermaid
flowchart LR
  subgraph Security["Project bảo mật"]
    Admin["Nhóm quản trị khóa"]
    KMS["Cloud KMS CryptoKey"]
    Admin -->|"Quản lý vòng đời và policy"| KMS
  end

  subgraph Workload["Project workload"]
    App["Service account ứng dụng"]
    Data["Bucket / database"]
    App -->|"Quyền dữ liệu"| Data
  end

  App -->|"Encrypt / decrypt khi gọi API trực tiếp"| KMS
  Agent["Service agent của dịch vụ"] -->|"Dùng khóa cho CMEK"| KMS
  Agent -->|"Thao tác dữ liệu theo cấu hình dịch vụ"| Data
~~~

Hai luồng có thể cùng xuất hiện trong một kiến trúc, nhưng cần xác định rõ danh tính nào thực sự gọi Cloud KMS. Tránh cấp quyền trùng lặp cho cả ứng dụng và service agent nếu chỉ một trong hai danh tính cần thực hiện thao tác mật mã.

## 7. Quy trình triển khai và kiểm tra

Có thể áp dụng trình tự sau cho một workload mới:

1. **Xác định luồng mã hóa.** Chọn ứng dụng gọi Cloud KMS trực tiếp, envelope encryption hay CMEK do dịch vụ quản lý. Xác định rõ principal thực hiện thao tác encrypt/decrypt.
2. **Chọn ranh giới tài nguyên.** Đặt khóa trong project và location phù hợp. Tổ chức key ring theo môi trường hoặc miền quản trị; tránh gom các khóa có chủ sở hữu và mức độ nhạy cảm khác nhau vào cùng một phạm vi IAM quá rộng.
3. **Phân công quản trị.** Cấp quyền quản lý vòng đời khóa cho nhóm có trách nhiệm. Tách người thay đổi IAM policy khỏi workload sử dụng khóa khi yêu cầu kiểm soát cần mức phân tách cao.
4. **Cấp quyền sử dụng tối thiểu.** Gắn role encrypt/decrypt hoặc role hẹp hơn cho service account hay service agent trên đúng CryptoKey.
5. **Cấp quyền dữ liệu độc lập.** Cấp quyền Storage, BigQuery, Cloud SQL hoặc Secret Manager theo thao tác nghiệp vụ. Kiểm tra riêng cả quyền truy cập dữ liệu và quyền sử dụng khóa.
6. **Kiểm thử bằng danh tính thật.** Xác minh workload thực hiện được thao tác cần thiết; đồng thời xác minh workload không thể tạo khóa, đổi policy, vô hiệu hóa key version hoặc truy cập dữ liệu ngoài phạm vi.
7. **Theo dõi và rà soát.** Bật cấu hình Cloud Audit Logs phù hợp cho hoạt động quản trị và Data Access, theo dõi thay đổi IAM policy cùng các thao tác mật mã, và định kỳ loại bỏ binding không còn cần thiết.

Khi luân chuyển khóa, cần hiểu tác động của key version. Việc đặt lịch rotation tạo phiên bản khóa mới làm phiên bản chính cho các thao tác mã hóa tiếp theo; bản thân Cloud KMS không tự mã hóa lại toàn bộ dữ liệu cũ. Hệ thống vẫn cần các phiên bản cũ còn hiệu lực để giải mã dữ liệu đã được mã hóa bằng chúng, trừ khi dữ liệu đã được chuyển đổi theo quy trình của dịch vụ. Không vô hiệu hóa hoặc lên lịch hủy một key version trước khi xác minh dữ liệu, bản sao lưu và workload không còn phụ thuộc vào phiên bản đó.

## 8. Những lỗi phân quyền thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Cấp **roles/cloudkms.admin** cho service account ứng dụng | Ứng dụng có phạm vi quản trị lớn hơn nhu cầu nghiệp vụ | Chỉ cấp role sử dụng khóa trên CryptoKey cần thiết |
| Cấp quyền sử dụng khóa ở cấp project | Workload có thể dùng nhiều khóa ngoài phạm vi cần thiết | Thu hẹp binding xuống CryptoKey |
| Chỉ cấp quyền đọc object nhưng quên quyền CMEK cho service agent | Dịch vụ có thể không đọc hoặc ghi được dữ liệu đã mã hóa bằng khóa khách hàng quản lý | Kiểm tra danh tính service agent và policy của CryptoKey |
| Cấp quyền Cloud KMS trực tiếp cho ứng dụng khi dịch vụ đã dùng service agent | Tăng số principal có thể sử dụng khóa | Xác định principal thực hiện thao tác mật mã và bỏ binding thừa |
| Để nhóm quản trị khóa tự thay đổi policy mà không có kiểm soát | Một principal có thể tự mở rộng quyền sử dụng khóa | Tách quyền **setIamPolicy**, yêu cầu phê duyệt và rà soát audit log |
| Vô hiệu hóa hoặc hủy key version khi dữ liệu vẫn phụ thuộc | Ứng dụng hoặc dịch vụ có thể mất khả năng giải mã dữ liệu | Kiểm tra phụ thuộc, bản sao lưu và kế hoạch khôi phục trước khi thay đổi trạng thái |

## 9. Tiêu chí xác nhận thiết kế

Trước khi đưa workload vào vận hành, hãy kiểm tra các câu hỏi sau:

- Mỗi CryptoKey có chủ sở hữu quản trị và mục đích sử dụng rõ ràng không?
- Service account hoặc service agent được cấp quyền có đúng là danh tính thực hiện thao tác mật mã không?
- Role sử dụng khóa được gắn ở phạm vi CryptoKey cần thiết chưa?
- Quyền đọc/ghi dữ liệu và quyền dùng khóa đã được cấp, kiểm thử độc lập chưa?
- Danh tính quản trị có thể tự thay đổi policy để cấp quyền cho chính mình không? Nếu có, cơ chế phê duyệt và giám sát đã đủ chặt chưa?
- Các thao tác quản trị, thay đổi policy và sử dụng khóa có thể được truy vết qua audit log không?
- Kế hoạch rotation, vô hiệu hóa và hủy key version đã xét đến dữ liệu cũ và bản sao lưu chưa?

Một thiết kế tốt giúp nhóm bảo mật kiểm soát vòng đời khóa, ứng dụng chỉ sử dụng đúng năng lực mật mã cần thiết, và người dùng chỉ truy cập dữ liệu theo quyền nghiệp vụ. Khi ba lớp quyền được cấp riêng và kiểm tra độc lập, một credential bị lộ sẽ có phạm vi ảnh hưởng nhỏ hơn, đồng thời việc điều tra và thu hồi quyền cũng rõ ràng hơn.
