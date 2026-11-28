# Vault key hierarchy: phân cấp khóa bảo vệ credential trong PAM

## 1. Key hierarchy giải quyết vấn đề gì?

Trong quản lý truy cập đặc quyền (Privileged Access Management — PAM), vault có thể lưu mật khẩu quản trị, private key, token của tài khoản dịch vụ và nhiều credential nhạy cảm khác. Những dữ liệu này cần được bảo vệ cả khi lưu trữ, sao lưu, chuyển đổi phiên bản và khôi phục.

**Vault key hierarchy** là cách tổ chức các khóa mật mã theo vai trò và quan hệ bảo vệ. Thay vì dùng một khóa cho mọi dữ liệu và mọi thao tác, hệ thống có thể dùng khóa mã hóa dữ liệu, khóa bảo vệ các khóa đó và một cơ chế bảo vệ cấp cao hơn.

Một mô hình phân cấp giúp làm rõ:

1. Khóa nào trực tiếp bảo vệ credential.
2. Khóa nào bảo vệ khóa khác.
3. Thành phần nào được sử dụng từng khóa.
4. Rotation ở mỗi tầng làm thay đổi điều gì.
5. Những khóa và phiên bản nào cần cho việc khôi phục.
6. Phạm vi ảnh hưởng khi một khóa bị lộ hoặc bị mất.

Ví dụ, đổi khóa bảo vệ DEK có thể chỉ cần bọc lại DEK, không cần mã hóa lại toàn bộ credential. Ngược lại, nếu chính DEK đã bị lộ, chỉ đổi lớp bọc bên ngoài không làm DEK cũ trở nên bí mật.

Tên gọi như master key, root key, barrier key hoặc unseal key phụ thuộc sản phẩm. Bài học dùng các vai trò logic, không mặc định mọi vault có cùng số tầng hoặc cùng ý nghĩa thuật ngữ.

## 2. Phân biệt credential, khóa mã hóa và quyền truy cập

| Đối tượng | Vai trò | Ví dụ |
|---|---|---|
| Credential được lưu | Dữ liệu bí mật dùng để truy cập hệ thống khác | Mật khẩu tài khoản quản trị cơ sở dữ liệu |
| Data Encryption Key — DEK | Khóa trực tiếp mã hóa dữ liệu | Khóa bảo vệ một đối tượng hoặc một nhóm đối tượng |
| Key Encryption Key — KEK | Khóa bảo vệ khóa khác | Khóa bọc các DEK trong một phạm vi |
| Cơ chế bảo vệ cấp cao | Bảo vệ hoặc cho phép sử dụng khóa cấp dưới | Khóa trong KMS/HSM theo kiến trúc |
| Credential quản trị vault | Xác thực hoặc cấp quyền với vault | Token hoặc chứng thư của người quản trị |
| Credential truy cập KMS | Cho phép workload yêu cầu thao tác với khóa | Danh tính dịch vụ được quyền unwrap |
| Share hoặc vật liệu phục hồi | Phục vụ mở khóa hoặc thao tác phục hồi theo thiết kế | Phần chia bí mật hoặc thông tin phục hồi |
| Khóa TLS | Bảo vệ và xác thực kênh truyền | Private key của endpoint vault |

Một private key SSH được lưu như secret trong vault không tự trở thành DEK. Token có quyền quản trị vault cũng không nhất thiết là khóa mật mã dùng để giải mã dữ liệu.

Tương tự, quyền quản trị một đối tượng khóa trong KMS không mặc nhiên đồng nghĩa được phép đọc mọi secret. Tuy nhiên, người có thể sửa policy khóa hoặc cấp quyền giải mã có thể có ảnh hưởng gián tiếp rất lớn. Cần đánh giá khả năng thực tế của từng vai trò.

Phân cấp khóa và phân cấp quyền là hai cấu trúc liên quan nhưng khác nhau:

~~~text
Phân cấp khóa:
  Khóa nào bảo vệ dữ liệu hoặc khóa nào?

Phân cấp quyền:
  Chủ thể nào được yêu cầu thao tác nào trên đối tượng nào?
~~~

Cả hai phải được thiết kế đúng. Mã hóa tốt không bù được việc cấp quyền đọc secret quá rộng.

## 3. Mô hình envelope encryption

**Envelope encryption** là mô hình dùng một khóa để mã hóa dữ liệu, rồi bảo vệ khóa dữ liệu bằng một khóa khác.

Luồng logic:

~~~text
Credential + DEK
  → mã hóa dữ liệu
  → ciphertext của credential.

DEK + KEK
  → wrap hoặc mã hóa khóa theo cơ chế phù hợp
  → wrapped DEK.

Lưu:
  ciphertext + wrapped DEK + metadata cần thiết.
~~~

Khi đọc:

~~~text
Xác thực và ủy quyền yêu cầu
  → xác định KEK và phiên bản phù hợp
  → unwrap DEK
  → giải mã và xác minh dữ liệu
  → trả hoặc sử dụng credential theo policy.
~~~

DEK ở dạng rõ không nên được lưu bên cạnh ciphertext như một trường thông thường. Việc lưu wrapped DEK cùng ciphertext không tự làm mất ý nghĩa mã hóa, miễn là KEK, cơ chế wrap và quyền sử dụng chúng được bảo vệ đúng.

Mô hình hai tầng có thể là:

~~~mermaid
flowchart TD
    I["Danh tính vault được phép"] -->|Yêu cầu thao tác khóa| K["KEK trong KMS hoặc cơ chế quản lý khóa"]
    K -->|Bảo vệ| W["Wrapped DEK"]
    W -->|Unwrap khi đủ điều kiện| D["DEK trong phạm vi xử lý cần thiết"]
    D -->|Mã hóa hoặc giải mã| C["Ciphertext của credential"]
    P["Policy truy cập secret"] --> A["Quyết định của vault"]
    A --> I
~~~

Một kiến trúc khác có thể thêm tầng:

~~~text
Khóa bảo vệ cấp cao
  → KEK theo miền quản lý hoặc tenant
  → DEK theo đối tượng hoặc phạm vi
  → dữ liệu credential.
~~~

Thêm tầng làm tăng khả năng phân vùng và quản lý vòng đời, nhưng cũng tăng phụ thuộc, metadata và độ phức tạp phục hồi. Không phải cứ có nhiều tầng hơn là an toàn hơn.

## 4. Chọn phạm vi cho DEK và KEK

### 4.1. Phạm vi DEK ảnh hưởng blast radius

DEK có thể được cấp theo đối tượng, phiên bản, tập dữ liệu hoặc đơn vị lưu trữ tùy kiến trúc.

| Cách phân phạm vi | Lợi ích có thể có | Đánh đổi |
|---|---|---|
| Một DEK cho phạm vi lớn | Ít đối tượng khóa và thao tác quản lý | Một DEK bị lộ có thể ảnh hưởng nhiều dữ liệu |
| DEK theo đối tượng | Giới hạn ảnh hưởng và quản lý vòng đời hẹp hơn | Tăng số khóa và metadata |
| DEK theo phiên bản dữ liệu | Tách vòng đời các phiên bản | Tăng yêu cầu quản lý lịch sử và backup |
| DEK theo nhóm dữ liệu | Cân bằng theo nhu cầu triển khai | Phải hiểu rõ ranh giới nhóm và quyền dùng |

Không suy ra phạm vi ảnh hưởng từ độ dài khóa. Một DEK mạnh về mật mã nhưng dùng cho toàn bộ vault vẫn có phạm vi ảnh hưởng lớn nếu bị lộ.

### 4.2. Phạm vi KEK cần đi cùng quyền sử dụng

Có thể tách KEK theo môi trường, tenant hoặc miền nhạy cảm. Tuy nhiên, nếu một danh tính dịch vụ có quyền unwrap với mọi KEK và đọc mọi ciphertext, ranh giới vận hành vẫn có thể rất rộng.

Cần xem đồng thời:

- Phạm vi dữ liệu được mỗi KEK bảo vệ.
- Danh tính được phép sử dụng KEK.
- Khả năng truy cập wrapped DEK và ciphertext.
- Quyền sửa policy, alias hoặc cấu hình khóa.
- Khả năng phân tách backup và phục hồi.

Tách tên khóa nhưng giữ toàn bộ quyền trong một tài khoản không tạo ra mức cô lập tương đương với các miền quản trị độc lập.

### 4.3. Khóa có mục đích khác nhau cần được quản lý riêng

Không tái sử dụng tùy tiện cùng một vật liệu khóa cho mã hóa credential, ký audit, xác thực giao tiếp và các mục đích khác.

Nếu một thiết kế dùng dẫn xuất khóa, phải có cơ chế tiêu chuẩn, phân tách mục đích và đánh giá mật mã phù hợp. Không tự chế cách tạo khóa con bằng nối chuỗi hoặc băm theo trực giác.

Bài học tập trung vào trách nhiệm của từng tầng, không triển khai thuật toán mật mã tự viết.

## 5. Vai trò của KMS, HSM và lớp bảo vệ cấp cao

### 5.1. KMS và HSM không đồng nghĩa với nhau

KMS là hệ thống cung cấp chức năng quản lý và sử dụng khóa theo mô hình dịch vụ. HSM là thành phần phần cứng bảo vệ khóa và thực hiện những thao tác được hỗ trợ.

Một KMS có thể dùng HSM phía dưới, nhưng hai khái niệm không thể thay thế cho nhau. Khả năng xuất khóa, sao lưu, sao chép, giới hạn thao tác và khôi phục phụ thuộc triển khai.

Cần biết:

- Khóa cấp cao được tạo và giữ ở đâu.
- Khóa có được xuất hay không.
- Danh tính nào có thể yêu cầu decrypt, unwrap hoặc thao tác tương đương.
- Ai có quyền vô hiệu hóa, đổi policy hoặc yêu cầu xóa.
- Vault có phụ thuộc vào kết nối tới dịch vụ khóa trong những tình huống nào.

### 5.2. Non-exportable không có nghĩa không thể bị lạm dụng

Một khóa không cho xuất vật liệu rõ vẫn có thể được sử dụng để giải mã nếu chủ thể gọi có đủ quyền.

Nếu kẻ tấn công chiếm danh tính vault, đọc được wrapped DEK và được phép gọi unwrap, việc không xuất được KEK chưa loại bỏ khả năng tiếp cận dữ liệu.

Cần bảo vệ cả vật liệu khóa, API sử dụng khóa, danh tính workload và đường truy cập ciphertext.

### 5.3. Bảo vệ khóa không loại bỏ plaintext trong luồng sử dụng

Vault có thể cần xử lý DEK hoặc credential ở dạng rõ trong bộ nhớ để phục vụ yêu cầu. Một số kiến trúc giữ một phần thao tác trong phần cứng hoặc dịch vụ khác, nhưng không nên suy ra rằng mọi plaintext luôn nằm trong HSM.

Cần đánh giá tiến trình, bộ nhớ, dump chẩn đoán, agent và cơ chế trả secret cho người dùng hoặc workload. Key hierarchy bảo vệ dữ liệu lưu trữ và vòng đời khóa; nó không tự ngăn lạm dụng một lần đọc hợp lệ hoặc một tiến trình đã bị chiếm quyền.

## 6. Unseal, recovery và quorum

### 6.1. Unseal là chức năng phụ thuộc thiết kế

Một vault có thể có trạng thái khóa hoặc sealed, trong đó nó chưa sử dụng được khóa cần thiết cho những thao tác dữ liệu nhất định.

Việc unseal có thể dựa vào vật liệu được chia, một dịch vụ khóa bên ngoài hoặc cơ chế khác. Không mặc định unseal key là DEK hoặc mật khẩu đăng nhập quản trị.

Cần trả lời:

- Vật liệu nào được khôi phục hoặc cho phép sử dụng?
- Thành phần nào giữ vật liệu sau khi mở khóa?
- Mất dịch vụ KMS có ảnh hưởng tới khởi động, failover hay mọi lần đọc không?
- Những thao tác nào còn hoạt động khi vault chưa mở khóa?

Các câu trả lời có thể khác nhau giữa sản phẩm và chế độ triển khai.

### 6.2. Share phục hồi không phải bản sao của credential

Trong mô hình chia bí mật, một ngưỡng phần chia có thể được dùng để khôi phục một bí mật theo thuật toán đã thiết kế. Một mô hình minh họa có thể yêu cầu ba trong năm phần; đó không phải cấu hình mặc định cho mọi vault.

Quorum phân phối trách nhiệm chỉ có ý nghĩa khi các phần chia được quản lý qua những chủ thể hoặc miền kiểm soát phù hợp. Giữ mọi phần trong cùng một tài khoản lưu trữ làm suy yếu mục tiêu phân tách.

Cơ chế nhiều người phê duyệt một thao tác cũng không tự tương đương với cơ chế mật mã chia bí mật. Cần biết hệ thống đang áp dụng loại kiểm soát nào.

### 6.3. Recovery không mặc định thay thế khóa KMS bị mất

Một số vật liệu recovery có thể cho phép thực hiện thao tác quản trị hoặc phục hồi nhất định mà không chứa đủ khả năng giải mã dữ liệu nếu khóa bảo vệ bên ngoài đã mất.

Do đó, không kết luận “có recovery shares nên không cần bảo vệ vòng đời KMS”. Phải hiểu chính xác recovery có thể và không thể phục hồi đối tượng nào.

## 7. Metadata, phiên bản và ràng buộc ngữ cảnh

### 7.1. Một bản ghi cần hơn ciphertext

Một cấu trúc logic có thể gồm:

~~~yaml
encrypted_record:
  object_id: secret-payment-service
  tenant_id: tenant-payments
  payload_version: payload-v8
  crypto_profile: approved-aead-profile
  ciphertext_reference: encrypted-payload-008
  nonce_reference: payload-nonce-008
  dek_id: dek-object-008
  wrapped_dek_reference: wrapped-dek-008
  wrapping_key_id: kek-payments
  wrapping_key_version: key-version-3
  envelope_generation: 12
~~~

Các giá trị chỉ minh họa, không phải cú pháp của sản phẩm hoặc một bản mã có thể chạy trực tiếp. Giá trị nonce phải được lưu hoặc tái tạo theo cơ chế của thiết kế, không phải chỉ là một nhãn không có cách phân giải.

Metadata cần đủ để chọn đúng cơ chế, khóa và phiên bản khi đọc hoặc khôi phục. Nó cũng có thể chứa thông tin nhạy cảm về cấu trúc hệ thống nên phải được bảo vệ phù hợp.

### 7.2. Alias không luôn là định danh phiên bản

Một alias có thể trỏ sang một khóa khác sau rotation. Nếu chỉ lưu alias rồi luôn dùng đích hiện tại, hệ thống có thể không tìm được khóa cần cho bản ghi cũ.

Cần giữ định danh hoặc thông tin giải mã theo cơ chế của dịch vụ khóa. Có dịch vụ chứa thông tin phiên bản trong blob; có thiết kế cần metadata riêng. Không được giả định mọi provider xử lý giống nhau.

### 7.3. Ràng buộc ngữ cảnh bằng cơ chế phù hợp

Mã hóa có xác thực, chẳng hạn một cơ chế AEAD được triển khai đúng, hỗ trợ bảo vệ bí mật và phát hiện sửa đổi trong phạm vi được xác thực.

Associated data có thể ràng buộc dữ liệu với tenant, object ID hoặc phiên bản payload. Associated data được xác thực nhưng không được mã hóa bởi chính cơ chế đó, nên không đặt secret vào đó với kỳ vọng nó được che giấu.

Ngữ cảnh phải được đối chiếu với nguồn tin cậy của yêu cầu. Nếu chỉ tin toàn bộ metadata mà kẻ tấn công có thể thay cùng bản ghi, việc thêm tenant_id chưa tự tạo ra kiểm soát tenant hoàn chỉnh.

Cần phân biệt phiên bản payload với phiên bản lớp bọc. Rewrap KEK không nhất thiết thay nội dung payload; không nên ràng buộc tùy tiện mọi metadata biến đổi vào cùng một ngữ cảnh rồi làm hỏng khả năng chuyển đổi.

## 8. Luồng ghi và đọc một credential

### 8.1. Luồng ghi tham chiếu

1. Xác thực chủ thể và kiểm tra quyền ghi đúng đối tượng.
2. Xác định phạm vi tenant, object và policy từ ngữ cảnh tin cậy.
3. Tạo hoặc lấy DEK theo thiết kế đã duyệt.
4. Mã hóa payload bằng thư viện và crypto profile được hỗ trợ.
5. Bảo đảm các yêu cầu về nonce, ngữ cảnh và giới hạn sử dụng của cơ chế.
6. Wrap DEK bằng đúng KEK và phiên bản.
7. Lưu bản mã, wrapped DEK và metadata nhất quán.
8. Ghi sự kiện kết quả mà không chứa secret hoặc khóa rõ.

Không tự thay cơ chế sinh khóa bằng mật khẩu dễ nhớ hoặc dữ liệu lấy từ tên tài khoản. Cần sử dụng cơ chế sinh số ngẫu nhiên mật mã và quản lý khóa phù hợp của nền tảng.

### 8.2. Luồng đọc tham chiếu

~~~text
Yêu cầu đọc hoặc sử dụng credential
  → xác minh danh tính và quyền PAM
  → chọn đúng bản ghi trong phạm vi được phép
  → kiểm tra metadata và phiên bản
  → yêu cầu unwrap theo quyền của dịch vụ vault
  → giải mã và xác minh tính toàn vẹn
  → trả hoặc sử dụng secret theo policy
  → ghi sự kiện và kết quả.
~~~

Nếu xác minh tính toàn vẹn thất bại, không trả plaintext một phần hoặc tự bỏ bước kiểm tra để cứu dữ liệu. Cần phân loại lỗi metadata, khóa, dữ liệu hoặc triển khai và xử lý theo quy trình.

### 8.3. Giới hạn nonce và cách dùng khóa là một phần của thiết kế

Một số cơ chế mã hóa yêu cầu không tái sử dụng nonce dưới cùng khóa. Vi phạm có thể làm mất bảo mật dù thuật toán được chọn là một thuật toán mạnh.

Vì vậy, cần quản lý việc sinh nonce, giới hạn số lần sử dụng và tình huống khôi phục dữ liệu hoặc trạng thái bộ đếm. Không suy ra rằng nonce là secret cần giấu; tính đúng đắn của việc dùng nonce mới là điều quan trọng theo cơ chế tương ứng.

Không viết lại thuật toán hoặc tự thiết kế định dạng mật mã khi đã có thành phần được hỗ trợ và đánh giá phù hợp.

## 9. Ba loại rotation thường bị nhầm

| Thay đổi | Đối tượng được đổi | Dữ liệu có thể cần xử lý |
|---|---|---|
| Rotation credential tại đích | Mật khẩu, token, khóa đăng nhập hoặc danh tính liên quan | Cập nhật đích, vault và consumer |
| Rotation DEK | Khóa trực tiếp mã hóa payload | Giải mã và mã hóa lại dữ liệu bằng DEK mới |
| Rotation KEK | Khóa bảo vệ DEK hoặc khóa cấp dưới | Có thể rewrap khóa cấp dưới, tùy thiết kế |
| Rotation lớp bảo vệ cao hơn | Khóa hoặc cơ chế bảo vệ tầng dưới | Có thể chỉ đổi lớp bọc của khóa trung gian |

### 9.1. Rotation credential không phải rotation khóa mã hóa vault

Đổi mật khẩu của tài khoản quản trị có thể tạo một payload mới trong vault. Nó không chứng minh KEK đã được rotation.

Ngược lại, đổi DEK hoặc KEK không làm mật khẩu quản trị tại cơ sở dữ liệu, máy chủ hoặc thiết bị mạng tự thay đổi.

Hai vòng đời cần được theo dõi riêng vì chúng xử lý những rủi ro khác nhau.

### 9.2. Rewrap khác re-encrypt

**Rewrap** thay lớp bảo vệ của một DEK hoặc khóa cấp dưới. Payload có thể giữ nguyên, và DEK cũng có thể giữ nguyên.

**Re-encrypt payload** giải mã rồi mã hóa lại dữ liệu bằng cấu hình phù hợp, thường khi thay DEK hoặc thay định dạng mật mã. Thao tác này phải tuân thủ yêu cầu nonce và ngữ cảnh của cơ chế.

~~~text
Trước:
  KEK-v1 bảo vệ DEK-A
  DEK-A bảo vệ payload-P.

Rewrap:
  KEK-v2 bảo vệ cùng DEK-A
  DEK-A vẫn bảo vệ cùng payload-P.

Đổi DEK:
  KEK phù hợp bảo vệ DEK-B
  DEK-B bảo vệ một bản mã mới của payload.
~~~

Nếu dịch vụ khóa hỗ trợ chuyển lớp bọc mà không đưa vật liệu khóa rõ ra ngoài ranh giới của nó, có thể dùng khả năng đó theo thiết kế. Không giả định mọi KMS hoặc mọi đường chuyển đổi đều hỗ trợ.

### 9.3. Tạo phiên bản khóa mới chưa chứng minh đã chuyển dữ liệu

Một cơ chế rotation tự động có thể tạo phiên bản mới cho các lần sử dụng tiếp theo trong khi vẫn giữ khả năng đọc dữ liệu cũ. Điều đó không tự có nghĩa mọi wrapped DEK hoặc bản mã đã được chuyển đổi.

Cần phân biệt:

~~~text
Khóa mới được tạo
  ≠ khóa mới đã được dùng để ghi
  ≠ dữ liệu cũ đã chuyển
  ≠ backup không còn cần khóa cũ
  ≠ khóa cũ có thể xóa.
~~~

Chỉ số và bằng chứng rotation phải cho biết đang xác nhận bước nào.

## 10. Chuyển đổi KEK hoặc DEK có kiểm soát

### 10.1. Giai đoạn chuẩn bị

Trước khi chuyển đổi, cần kiểm kê:

- Tập đối tượng đang dùng từng phiên bản.
- Các phiên bản payload còn được giữ.
- Backup, bản sao và môi trường phục hồi liên quan.
- Quyền sử dụng khóa cũ và khóa mới.
- Định dạng metadata, ngữ cảnh và khả năng đọc.
- Khả năng phục hồi khi thao tác từng phần thất bại.
- Những writer có thể tiếp tục tạo dữ liệu.

Không chỉ đếm bản ghi hiện tại. Lịch sử phiên bản hoặc snapshot có thể vẫn phụ thuộc vào khóa cũ.

### 10.2. Giai đoạn hỗ trợ đọc và ghi

Một cách chuyển đổi có thể là:

~~~text
Chuẩn bị khóa mới
  → xác minh quyền và khả năng dùng
  → ghi mới theo phiên bản mới
  → đọc được các phiên bản còn hợp lệ
  → chuyển dữ liệu cũ theo từng phần
  → đối soát kết quả
  → xử lý vòng đời khóa cũ.
~~~

Việc cho phép đọc khóa cũ phải có mục đích và phạm vi rõ. Không cần để mọi workload được dùng mọi phiên bản chỉ vì hệ thống đang migration.

### 10.3. Xử lý ghi đồng thời

Một tác vụ rewrap có thể đọc bản ghi cũ trong lúc tác vụ khác vừa cập nhật credential.

Nếu tác vụ chuyển đổi ghi đè không kiểm tra phiên bản, nó có thể đưa metadata cũ trở lại hoặc làm mất thay đổi hợp lệ.

Có thể cần kiểm tra generation, cơ chế compare-and-swap hoặc giao dịch lưu trữ phù hợp:

~~~text
Đọc envelope generation g
  → tạo bản chuyển đổi
  → chỉ công bố nếu bản ghi vẫn ở generation g
  → nếu đã đổi, đọc lại và đánh giá lại.
~~~

Đây là yêu cầu logic. Tính nguyên tử của một thao tác trong cơ sở dữ liệu không tự biến toàn bộ luồng với KMS thành một giao dịch xuyên hệ thống.

### 10.4. Khi timeout hoặc tiến trình dừng

Cần biết tác vụ đang ở bước nào: chưa tạo lớp bọc mới, đã tạo nhưng chưa lưu, hay đã lưu nhưng chưa xác minh.

Thử lại phải dựa trên định danh và trạng thái, tránh cập nhật mù. Nên giữ đủ thông tin để phát hiện bản ghi dùng khóa cũ, bản chuyển đổi lỗi hoặc đối tượng không có đường giải mã hợp lệ.

Một tác vụ kết thúc không đồng nghĩa migration đã hoàn tất toàn bộ phạm vi.

### 10.5. Rollback không chỉ là đổi alias về khóa cũ

Sau khi writer đã dùng khóa mới, dữ liệu mới có thể cần khóa mới để đọc. Đổi alias về khóa cũ không tự đảo ngược dữ liệu đã ghi và có thể làm một phần bản ghi không đọc được.

Phương án phục hồi cần giữ khả năng xử lý các phiên bản đã phát sinh hoặc chuyển đổi theo cơ chế được xác minh. Không xóa khóa mới chỉ vì muốn đưa cấu hình về trạng thái trước migration.

## 11. Khi nào được ngừng dùng hoặc hủy khóa?

### 11.1. Vòng đời logic

Một mô hình quản lý có thể phân biệt:

~~~text
Được chuẩn bị
  → đang dùng cho ghi mới
  → chỉ còn phục vụ đọc hoặc phục hồi có giới hạn
  → ngừng sử dụng sau khi hết phụ thuộc
  → hủy theo quy trình được cho phép.
~~~

Đây là trạng thái logic, không phải tên trạng thái chính xác của một provider.

Cần tách quyết định không dùng cho ghi mới khỏi quyết định không cho giải mã và quyết định hủy vật liệu khóa. Các quyết định có ảnh hưởng khác nhau tới khả năng phục hồi.

### 11.2. Xác minh phụ thuộc trước khi hủy

Một khóa cũ có thể vẫn cần cho:

- Bản ghi chưa chuyển.
- Lịch sử credential được phép giữ.
- Backup hoặc bản sao phục hồi.
- Dữ liệu ở môi trường dự phòng.
- Bản ghi audit hoặc dữ liệu khác nếu kiến trúc dùng khóa đó.
- Tác vụ chuyển đổi chưa hoàn tất.

Không coi số bản ghi hiện tại bằng không là bằng chứng đủ cho mọi phụ thuộc.

### 11.3. Crypto-erasure có điều kiện

Hủy các khóa cần thiết có thể làm dữ liệu mã hóa không còn khả năng giải mã trong mô hình tương ứng. Hiệu quả phụ thuộc việc không còn bản sao khóa hoặc plaintext có thể sử dụng.

Cần đánh giá các bản xuất, cache, bộ nhớ, backup, vật liệu phục hồi và những bên đã lấy dữ liệu. Không hứa rằng hủy một đối tượng KEK sẽ xóa mọi bản sao secret từng được trả cho người dùng.

Đây là thao tác có thể làm mất dữ liệu không khôi phục được. Trách nhiệm, phạm vi và bằng chứng phải phù hợp quyết định vòng đời thực tế.

## 12. Backup và khôi phục theo toàn bộ chuỗi phụ thuộc

### 12.1. Backup ciphertext chưa đủ

Để khôi phục một đối tượng, có thể cần:

~~~text
Ciphertext
  + wrapped DEK
  + metadata và ngữ cảnh hợp lệ
  + khóa hoặc dịch vụ cho phép unwrap
  + danh tính và quyền cần thiết
  + phần mềm hiểu định dạng
  + phụ thuộc vận hành liên quan.
~~~

Mất một mắt xích có thể làm backup không dùng được dù tệp sao lưu vẫn nguyên vẹn.

Bản sao KEK cũng không đủ nếu thiếu metadata hoặc wrapped DEK tương ứng. Phục hồi cần kiểm tra toàn bộ đường đọc.

### 12.2. Khôi phục trong môi trường có kiểm soát

Nên có khả năng kiểm tra backup bằng dữ liệu và phạm vi được cho phép, đồng thời giữ quyền truy cập tới môi trường phục hồi chặt chẽ.

Không mở rộng mọi quyền KMS hoặc tắt điều kiện ràng buộc tenant chỉ để chạy được một lần diễn tập. Nếu môi trường phục hồi có danh tính khác, cần thiết kế quyền và ngữ cảnh phù hợp.

Kết quả cần chứng minh bản backup cụ thể có thể được giải mã và sử dụng theo phạm vi, không chỉ chứng minh tải được tệp từ nơi lưu.

### 12.3. Khóa không xuất được cần phương án phục hồi tương ứng

Nếu vật liệu khóa không được xuất, không thể tự tạo một bản sao rõ bằng quy trình thông thường. Phương án có thể dựa trên khả năng phục hồi, sao chép hoặc tính sẵn sàng được hệ thống khóa hỗ trợ.

Cần xác minh các giới hạn của phương án được chọn: cùng khu vực lỗi, quyền quản trị chung, cấu hình bị xóa hoặc khóa bị vô hiệu hóa có thể tạo điểm hỏng chung.

Không giả định recovery shares luôn thay thế được một KMS key đã mất.

### 12.4. Phục hồi vault không đồng nghĩa rollback credential tại đích

Một snapshot cũ có thể chứa mật khẩu cũ của tài khoản dịch vụ trong khi hệ thống đích đã được rotation nhiều lần.

Sau phục hồi, cần đối soát credential, phiên bản và consumer theo thiết kế. Key hierarchy giúp đọc được dữ liệu đã sao lưu; nó không chứng minh credential trong dữ liệu đó còn hợp lệ tại hệ thống bên ngoài.

## 13. Phân tách nhiệm vụ và quyền đặc quyền với khóa

Một mô hình trách nhiệm có thể gồm:

| Vai trò | Trách nhiệm có thể giao | Quyền cần xem xét đặc biệt |
|---|---|---|
| Ứng dụng vault | Sử dụng khóa trong phạm vi phục vụ dữ liệu | Khả năng unwrap và truy cập nhiều tenant |
| Người quản lý policy khóa | Quản trị phạm vi chủ thể và thao tác | Khả năng tự cấp quyền giải mã |
| Người vận hành vault | Duy trì dịch vụ và cấu hình | Truy cập tiến trình, bộ nhớ, plugin và danh tính dịch vụ |
| Người quản lý backup | Sao lưu và phục hồi dữ liệu | Kết hợp ciphertext với quyền dùng khóa |
| Chủ thể phục hồi | Thực hiện recovery theo thẩm quyền | Vật liệu phục hồi hoặc quyền mở khóa |
| Kiểm toán hoặc giám sát | Kiểm tra thay đổi và sử dụng khóa | Quyền đọc bằng chứng nhưng không cần nhận secret rõ |

Phân tách vai trò phải được kiểm tra theo quyền hiệu lực. Nếu một người có thể sửa policy để tự cấp decrypt, việc giao diện không hiển thị nút đọc secret không bảo đảm họ không thể tiếp cận dữ liệu.

Có thể áp dụng JIT cho quyền vận hành nhạy cảm và giới hạn tác vụ quản trị theo nhu cầu. Điều đó cần cơ chế thực thi ở IAM, KMS, nền tảng chạy vault hoặc các lớp liên quan; tên role không tự tạo ra giới hạn.

Quản trị khóa và credential truy cập KMS cũng thuộc phạm vi PAM. Chúng cần owner, vòng đời, bằng chứng sử dụng và phương án ứng phó.

## 14. Audit và giám sát key hierarchy

### 14.1. Các sự kiện có ý nghĩa

Nên xem xét thu thập theo khả năng hệ thống:

- Tạo, đổi phiên bản và thay trạng thái khóa.
- Thay đổi policy, grant hoặc alias.
- Yêu cầu wrap, unwrap, decrypt hoặc thao tác tương ứng.
- Thất bại xác thực, ủy quyền hoặc ràng buộc ngữ cảnh.
- Bắt đầu, tiến độ và kết quả chuyển đổi.
- Sử dụng vật liệu phục hồi hoặc unseal.
- Vô hiệu hóa, yêu cầu hủy và kết quả hủy.
- Thay đổi danh tính workload sử dụng khóa.

Không ghi raw DEK, KEK, private key hoặc plaintext credential vào sự kiện. Cũng không cần sao chép toàn bộ payload mã hóa vào log chỉ để tạo định danh tương quan.

### 14.2. Nối sự kiện khóa với quyết định PAM

Một lần KMS cho phép unwrap không tự chứng minh người dùng cuối được phép đọc secret. Đó có thể là một thao tác của danh tính vault có phạm vi rộng.

Cần liên kết bằng các định danh phù hợp:

~~~text
Người dùng hoặc workload yêu cầu
  → policy PAM có hiệu lực
  → đối tượng và phiên bản secret
  → thao tác khóa của dịch vụ vault
  → kết quả đọc hoặc sử dụng
  → phiên hoặc hoạt động tại đích nếu liên quan.
~~~

Một số mô hình cache khóa làm nhiều lần đọc secret không tương ứng với nhiều lần gọi KMS. Không dùng số lần unwrap làm số lần đọc secret nếu kiến trúc không bảo đảm quan hệ đó.

### 14.3. Bằng chứng chuyển đổi và vòng đời

Báo cáo nên phân biệt khóa đã được tạo, đang dùng cho ghi, dữ liệu đã chuyển và phụ thuộc còn giữ.

Các chỉ số có ích gồm số đối tượng theo phiên bản, số lỗi chuyển đổi, bản ghi không xác định, phụ thuộc backup vào khóa cũ và thay đổi quyền nhạy cảm.

Không đánh dấu rotation hoàn tất chỉ từ thời điểm tạo một key version mới.

## 15. Các tình huống lỗi và giới hạn kiểm soát

### 15.1. Ma trận tình huống

| Tình huống | Ảnh hưởng có thể xảy ra | Điều cần xác minh |
|---|---|---|
| KMS hoặc HSM không sẵn sàng | Không mở khóa, không unwrap hoặc không ghi được dữ liệu mới | Vault cần gọi dịch vụ khóa ở thời điểm nào |
| Quyền của danh tính vault bị thu hồi | Các thao tác khóa mới bị từ chối | Có khóa hoặc plaintext còn được cache không |
| KEK bị vô hiệu hóa | Có thể mất khả năng giải mã các đối tượng phụ thuộc | Những phiên bản và bản sao nào còn dùng KEK đó |
| KEK bị hủy | Có thể mất dữ liệu không khôi phục được | Có cơ chế hoặc vật liệu phục hồi hợp lệ không |
| Wrapped DEK hoặc metadata bị hỏng | Không chọn được khóa hoặc xác minh thất bại | Phạm vi lỗi và khả năng khôi phục từ bản sao đúng |
| Alias trỏ nhầm khóa | Luồng mới lỗi hoặc sử dụng sai cấu hình | Phiên bản thực tế và thông tin trong bản ghi |
| Chuyển đổi dừng giữa chừng | Nhiều phiên bản cùng tồn tại | Trạng thái từng nhóm bản ghi và khả năng tiếp tục |
| Bản ghi cũ hợp lệ bị đưa trở lại | Dữ liệu lỗi thời có thể được chấp nhận | Cơ chế xác định phiên bản hiện hành có đáng tin cậy không |

### 15.2. Tính toàn vẹn không tự bảo đảm tính mới nhất

Một bản mã cũ từng hợp lệ có thể vẫn vượt qua xác minh mật mã. Nếu kẻ tấn công thay bản hiện tại bằng cả envelope cũ, cơ chế AEAD không tự biết đó là một lần phát lại dữ liệu.

Cần cơ chế quản lý phiên bản, trạng thái hiện hành và chống rollback phù hợp với mô hình đe dọa. Một trường version nằm trong cùng tập dữ liệu mà kẻ tấn công có thể thay toàn bộ chưa đủ để chứng minh tính mới nhất.

Không đồng nhất “tag hợp lệ” với “đây là credential hiện tại mà tổ chức muốn sử dụng”.

### 15.3. Cache làm thay đổi hiệu lực thu hồi

Nếu DEK hoặc khóa cấp dưới được giữ trong bộ nhớ, vô hiệu hóa KEK tại KMS có thể chưa lập tức chặn mọi lần giải mã tại vault đang chạy.

Cần biết loại dữ liệu được cache, thời gian tồn tại, cách mất hiệu lực và hành vi khi thay policy. Đồng thời phải kiểm soát quyết định truy cập secret, không chỉ trông chờ vào việc gọi lại KMS.

Nếu credential đã được trả cho người dùng hoặc workload, thu hồi quyền dùng KEK không làm bản sao đó mất hiệu lực tại đích. Phải xử lý credential và phiên theo vòng đời riêng.

### 15.4. Mất khả năng giải mã không phải là bằng chứng không bị lộ

Một khóa bị hủy có thể làm tổ chức không đọc được dữ liệu. Điều đó không chứng minh đối thủ chưa từng lấy plaintext hoặc một bản sao khóa trước đó.

Tính sẵn sàng, tính bí mật và tính toàn vẹn là các mục tiêu cần đánh giá riêng trong quá trình xử lý.

## 16. Ứng phó khi nghi lộ khóa

### 16.1. Xác định lớp và điều kiện bị ảnh hưởng

Cần làm rõ:

- Lộ vật liệu DEK, KEK hay chỉ một credential truy cập API?
- Chủ thể có khả năng dùng khóa nhưng không xuất khóa hay đã có bản sao vật liệu?
- Những ciphertext, wrapped DEK và backup nào có thể đã bị lấy?
- Khóa được dùng cho phạm vi dữ liệu nào?
- Có policy hoặc cấu hình tin cậy nào bị sửa không?
- Plaintext credential có thể đã bị đọc hoặc sử dụng ở đâu?

Phạm vi ảnh hưởng phụ thuộc cả khóa lẫn dữ liệu và quyền mà đối thủ có thể tiếp cận. Không tự kết luận mọi đối tượng đều đã bị đọc, nhưng cũng không coi không có log là bằng chứng chắc chắn chưa lộ.

### 16.2. Nếu DEK bị lộ

Cần xem xét dữ liệu được DEK đó bảo vệ, các bản sao và hoạt động truy cập liên quan.

Thay DEK và mã hóa lại dữ liệu có thể bảo vệ các bản lưu mới. Nó không làm mất hiệu lực plaintext đã bị biết hoặc bản mã cũ mà đối thủ có thể giải mã bằng DEK cũ.

Nếu dữ liệu là mật khẩu hoặc token còn dùng được, cần xử lý credential tại đích theo phạm vi sự cố.

### 16.3. Nếu KEK hoặc quyền unwrap bị lạm dụng

Cần giới hạn đường truy cập, xử lý danh tính bị chiếm, xác minh policy và đánh giá những DEK có thể đã bị mở.

**Rewrap dưới KEK mới không thu hồi khả năng giải mã các bản sao cũ** khi đối thủ đã giữ KEK cũ và wrapped DEK tương ứng. Với DEK có thể đã lộ, cần đánh giá thay DEK và xử lý dữ liệu hoặc credential liên quan.

Nếu vấn đề là danh tính được quyền gọi KMS, chỉ đổi phiên bản KEK mà giữ nguyên quyền bị chiếm có thể không giải quyết đường lạm dụng.

### 16.4. Khôi phục trạng thái tin cậy

Phương án có thể gồm cô lập thành phần, thu hồi quyền, phục hồi cấu hình, tạo khóa trong môi trường tin cậy và chuyển đổi dữ liệu theo phạm vi đã xác định.

Cần giữ bằng chứng trước và trong xử lý, kiểm tra phụ thuộc phục hồi và hạn chế gián đoạn. Không hủy khóa cũ theo phản xạ nếu hành động đó có thể làm mất dữ liệu hoặc bằng chứng mà chưa đạt mục tiêu bảo mật.

Kết thúc sự cố cần có trạng thái khóa, quyền, dữ liệu, credential tại đích và phiên liên quan. Một tác vụ rotation thành công chưa đủ để thay thế các phần đó.

## 17. Tình huống xuyên suốt: chuyển KEK cho một miền production

### 17.1. Bối cảnh

Một vault quản lý credential của dịch vụ thanh toán trong miền production. Mô hình giả định sử dụng:

~~~text
KEK payments-v1
  → các DEK theo đối tượng
  → payload credential.

Backup giữ:
  ciphertext + wrapped DEK + metadata.
~~~

Tổ chức muốn chuyển sang payments-v2 để phục vụ vòng đời khóa. Trong tình huống này chưa có bằng chứng KEK cũ bị lộ.

### 17.2. Kế hoạch chuyển đổi

Đội triển khai xác định tập bản ghi hiện hành, phiên bản được giữ và các backup còn phụ thuộc vào payments-v1.

Khóa mới được chuẩn bị với quyền đúng phạm vi. Writer bắt đầu dùng phiên bản mới theo cấu hình, trong khi đường đọc vẫn xử lý được những phiên bản còn được cho phép.

Tác vụ rewrap chuyển lớp bọc của DEK. Payload không thay chỉ vì KEK thay đổi. Việc cập nhật kiểm tra generation để tránh ghi đè credential vừa được rotation bởi tác vụ khác.

### 17.3. Timeout ở giữa tác vụ

Một yêu cầu tạo lớp bọc mới timeout. Hệ thống không được mặc định rằng toàn bộ đối tượng chưa thay hoặc đã thay xong.

Tác vụ đối soát bản ghi đã công bố, generation và khả năng đọc theo quyền phù hợp. Khi cần thử lại, nó thực hiện theo trạng thái đã xác minh thay vì ghi mù metadata.

Báo cáo tiến độ phân biệt:

- Đối tượng dùng phiên bản mới.
- Đối tượng còn dùng phiên bản cũ.
- Đối tượng đang có lỗi hoặc trạng thái chưa xác định.
- Backup vẫn cần khóa cũ.

### 17.4. Nghiệm thu

Có thể nghiệm thu chuyển đổi dữ liệu hiện hành khi phạm vi đó đã được kiểm tra đầy đủ và không còn trạng thái chưa xử lý.

Tuy nhiên, payments-v1 chưa được hủy nếu backup hoặc lịch sử vẫn cần nó. Quyền sử dụng khóa cũ có thể được giới hạn theo mục đích phục hồi phù hợp với cơ chế và chính sách.

Một lần kiểm tra restore phải dùng đúng chuỗi phụ thuộc của bản backup được chọn. Chỉ đọc thành công dữ liệu hiện hành không chứng minh mọi backup còn khôi phục được.

### 17.5. Nếu sau đó phát hiện khóa cũ bị lộ

Đánh giá sự cố phải bổ sung khả năng đối thủ đã có các wrapped DEK cũ. Không coi rewrap đã thực hiện trước đó là bằng chứng mọi dữ liệu lịch sử an toàn.

Cần xem xét DEK có thể đã lộ, ciphertext bị lấy, credential còn hiệu lực và việc sử dụng tại đích. Phương án xử lý có thể rộng hơn rotation KEK thông thường.

## 18. Kiểm chứng thiết kế và khả năng vận hành

| Nhóm kiểm chứng | Kết quả cần quan sát |
|---|---|
| Phân quyền | Chủ thể không có quyền không đọc hoặc sử dụng secret được |
| Phân vùng | Danh tính của một phạm vi không được mở khóa ngoài phạm vi đã duyệt |
| Metadata và ngữ cảnh | Không chấp nhận tráo đối tượng hoặc ngữ cảnh không phù hợp |
| Toàn vẹn | Dữ liệu bị sửa không được trả thành plaintext hợp lệ |
| Phiên bản | Đọc đúng bản ghi theo định danh và phiên bản thực tế |
| Rotation KEK | Phân biệt tạo khóa, dùng khóa và chuyển dữ liệu |
| Rotation DEK | Bản mã mới được tạo đúng cơ chế và còn đọc được |
| Ghi đồng thời | Chuyển đổi không ghi đè cập nhật hợp lệ |
| Timeout | Có thể xác định và tiếp tục trạng thái từng phần |
| Mất KMS | Hành vi khởi động, ghi và đọc đúng thiết kế |
| Cache | Hiệu lực thay policy hoặc thu hồi được hiểu và đo |
| Backup | Khôi phục được với đúng khóa, metadata và quyền |
| Hủy khóa | Phạm vi phụ thuộc được xác minh trước quyết định |
| Audit | Nối được chủ thể, policy, đối tượng và thao tác khóa |

Không nhất thiết kiểm chứng hành động phá hủy trên dữ liệu production. Cách diễn tập cần phù hợp phạm vi và mục tiêu đã xác định.

Không nên tạo một bản demo tự viết mật mã rồi coi đó là bằng chứng triển khai vault an toàn. Điều cần kiểm chứng là cơ chế thực tế, quyền hiệu lực và chuỗi vận hành được dùng.

## 19. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Gọi mọi bí mật là master key | Nhầm quyền quản trị, credential và vật liệu mã hóa | Mô tả theo vai trò và đối tượng cụ thể |
| Một khóa phục vụ mọi mục đích | Phạm vi ảnh hưởng lớn, khó quản lý vòng đời | Phân tách mục đích và phạm vi theo thiết kế |
| Có HSM nên bỏ kiểm soát tiến trình vault | Bỏ sót lạm dụng decrypt hoặc plaintext trong bộ nhớ | Bảo vệ cả API, workload và luồng sử dụng |
| Tạo key version mới là coi rotation hoàn tất | Dữ liệu cũ vẫn phụ thuộc khóa cũ | Theo dõi ghi mới, chuyển đổi và phụ thuộc |
| Rewrap được coi là thay DEK | Không xử lý DEK đã lộ | Phân biệt lớp bọc và khóa payload |
| Rotation KEK được coi là đổi password tại đích | Credential bị lộ vẫn dùng được | Quản lý vòng đời credential riêng |
| Chỉ lưu alias | Không tìm đúng phiên bản khi đọc hoặc restore | Giữ thông tin theo cơ chế giải mã thực tế |
| Coi AEAD là chống mọi lần phát lại | Có thể chấp nhận envelope cũ hợp lệ | Quản lý trạng thái và phiên bản hiện hành |
| Thu hồi KMS là coi mọi bản sao mất hiệu lực ngay | Cache hoặc credential đã xuất vẫn dùng được | Xử lý cache, policy, credential và phiên |
| Có backup ciphertext là coi khôi phục được | Thiếu khóa, metadata hoặc quyền | Kiểm tra toàn bộ chuỗi phục hồi |
| Recovery shares thay được mọi khóa bị mất | Hiểu sai chức năng phục hồi | Xác minh chính xác khả năng recovery |
| Hủy khóa cũ chỉ dựa trên dữ liệu hiện hành | Backup hoặc lịch sử không đọc được | Kiểm kê đầy đủ phụ thuộc |
| Lưu raw key vào log để dễ debug | Tạo thêm đường lộ vật liệu khóa | Ghi định danh và metadata cần thiết |
| Tách KEK nhưng một tài khoản có mọi quyền | Ranh giới quản trị vẫn rất rộng | Đánh giá quyền hiệu lực và miền kiểm soát |

## 20. Bài tập áp dụng

Một vault dùng DEK theo đối tượng và KEK trong dịch vụ khóa. Sau khi tạo KEK-v2, đội vận hành đổi alias sang phiên bản mới rồi muốn xóa KEK-v1.

Tình trạng hiện tại:

~~~text
Một số wrapped DEK vẫn dùng KEK-v1.
Backup tháng trước còn envelope cũ.
Vault cache DEK trong bộ nhớ.
Danh tính vault có quyền unwrap trên cả hai phiên bản.
Một số người dùng đã xuất mật khẩu quản trị trước đó.
~~~

Hãy trả lời:

1. Việc đổi alias đã chứng minh những gì và chưa chứng minh những gì?
2. Rewrap có cần đổi mật khẩu quản trị tại đích không?
3. Xóa KEK-v1 có thể ảnh hưởng những dữ liệu nào?
4. Vô hiệu hóa KEK-v1 có chặn ngay mọi lần đọc ở vault đang chạy không?
5. Nếu KEK-v1 bị lộ cùng wrapped DEK cũ, rewrap có đủ không?
6. Cần bằng chứng nào trước khi ngừng dùng phiên bản cũ?
7. Những người đã biết mật khẩu có còn dùng được sau rotation KEK không?

Hướng phân tích:

- Alias thay đổi cấu hình chọn khóa theo cơ chế tương ứng, chưa chứng minh dữ liệu cũ đã chuyển.
- Rewrap xử lý lớp bảo vệ DEK; mật khẩu tại đích có vòng đời riêng.
- Dữ liệu hiện hành, lịch sử và backup có thể còn phụ thuộc phiên bản cũ.
- Cache có thể làm hiệu lực thu hồi khác với kỳ vọng, nên cần hiểu đường đọc thực tế.
- Đối thủ có khóa và envelope cũ có thể tiếp tục giải mã bản sao tương ứng; cần đánh giá thay DEK và xử lý credential.
- Bằng chứng phải bao phủ bản ghi, backup, quyền, cache và khả năng phục hồi trong phạm vi.
- Rotation khóa mã hóa vault không làm mật khẩu đã được biết mất hiệu lực tại hệ thống đích.

## 21. Các điểm cần nắm

Vault key hierarchy phân chia trách nhiệm giữa khóa bảo vệ dữ liệu, khóa bảo vệ khóa và cơ chế bảo vệ cấp cao. Giá trị của mô hình nằm ở phạm vi ảnh hưởng, quyền sử dụng, khả năng chuyển đổi và phục hồi có kiểm chứng.

Rewrap, đổi DEK, rotation credential, unseal và recovery là những thao tác khác nhau. Mỗi thao tác có mục tiêu và giới hạn riêng.

Khi đánh giá một thiết kế, hãy lần theo một credential từ ciphertext qua metadata, wrapped DEK, khóa cấp trên, danh tính được phép và đường khôi phục. Chỉ khi biết toàn bộ chuỗi phụ thuộc mới có thể quyết định rotation, thu hồi hoặc hủy khóa một cách đúng phạm vi.
