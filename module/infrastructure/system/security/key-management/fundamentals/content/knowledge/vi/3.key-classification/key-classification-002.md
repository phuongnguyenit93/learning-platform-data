# Key encryption key (KEK): khóa dùng để bảo vệ các khóa khác

## 1. Vì sao cần Key Encryption Key?

Một nền tảng lưu hóa đơn cho hàng triệu khách hàng có thể mã hóa từng hóa đơn bằng **AES-256-GCM**. Tuy nhiên, mã hóa dữ liệu chỉ giải quyết một phần vấn đề: **khóa giải mã hóa đơn được cất ở đâu, ai có thể sử dụng và điều gì xảy ra khi phải thay khóa?**

Nếu lưu khóa AES ở cùng cơ sở dữ liệu với bản mã, người lấy được bản sao cơ sở dữ liệu có thể lấy luôn khóa. Nếu dùng một khóa bí mật chung cho toàn bộ hóa đơn, việc lộ khóa đó có thể ảnh hưởng tới tất cả dữ liệu dùng chung khóa. Nếu mỗi hóa đơn có một khóa riêng nhưng lại lưu tất cả các khóa ở dạng rõ, hệ thống vẫn có điểm yếu tương tự.

**Key Encryption Key (KEK)**, hay **khóa mã hóa khóa**, là khóa mật mã được dùng chủ yếu để **bảo vệ vật liệu khóa khác**, thường là **Data Encryption Key (DEK)**. Thay vì để DEK ở dạng rõ trong kho dữ liệu, hệ thống **bọc (wrap)** DEK dưới KEK và chỉ lưu bản DEK đã bọc. KEK thường được giữ trong hệ thống quản lý khóa như **KMS** hoặc **HSM**, với chính sách truy cập nghiêm ngặt.

~~~text
Dữ liệu hóa đơn --(mã hóa bằng DEK)--> Bản mã dữ liệu
DEK dạng rõ   --(bọc bằng KEK)-------> Wrapped DEK

Kho dữ liệu: bản mã dữ liệu + wrapped DEK + metadata
KMS/HSM:      quản lý KEK, quyền sử dụng và kiểm toán
~~~

Mô hình này thường được gọi là **envelope encryption** (mã hóa phong bì). KEK không làm thuật toán AES tự mạnh hơn; KEK giúp **quản lý, cách ly và kiểm soát việc truy cập DEK**.

Sau bài học, bạn có thể:

- Phân biệt KEK, DEK, master/root key và cặp khóa bất đối xứng.
- Hiểu cách KEK bọc DEK, tại sao cần thuật toán key wrapping phù hợp và cách envelope encryption vận hành.
- Mô tả vòng đời KEK: tạo, phân phối quyền sử dụng, lưu trữ, rotation, thu hồi và hủy.
- Giải thích sự khác nhau giữa **rotate KEK**, **rewrap DEK** và **re-encrypt dữ liệu**.
- Thiết kế chính sách IAM, KMS/HSM, phân tách môi trường/tenant, kiểm toán và phục hồi để hạn chế hậu quả khi khóa hoặc quyền sử dụng khóa bị lộ.

## 2. Thuật ngữ và vị trí của KEK trong hệ phân cấp khóa

### 2.1. KEK khác DEK như thế nào?

| Tiêu chí | DEK (Data Encryption Key) | KEK (Key Encryption Key) |
| --- | --- | --- |
| **Chức năng chính** | Mã hóa hoặc giải mã dữ liệu nghiệp vụ, như bản ghi, tệp, đối tượng | Bọc hoặc mở bọc một hay nhiều DEK |
| **Đầu vào điển hình** | Plaintext/ciphertext của dữ liệu | Vật liệu khóa cần được bảo vệ |
| **Tần suất dùng** | Có thể dùng mỗi khi đọc/ghi dữ liệu | Dùng khi cấp khóa, mở khóa hoặc thay lớp bọc |
| **Phạm vi ảnh hưởng khi bị lộ** | Dữ liệu đã được mã hóa bằng DEK đó | Có thể ảnh hưởng nhiều DEK được bọc bằng cùng KEK |
| **Nơi lưu giữ** | Chỉ hiện diện ở dạng rõ trong thành phần tin cậy khi cần; bản bọc lưu với dữ liệu | Ưu tiên giữ bên trong KMS/HSM hoặc một ranh giới bảo vệ tương đương |
| **Rotation** | Thay DEK thường đòi hỏi mã hóa lại dữ liệu liên quan | Thay KEK có thể chỉ cần bọc lại DEK, không phải mã hóa lại dữ liệu |

**DEK và KEK là hai vai trò sử dụng khóa**, không mặc định là hai loại thuật toán hoàn toàn khác nhau. Ví dụ, cả hai có thể là khóa AES, nhưng DEK dùng với AES-GCM để mã hóa hóa đơn, còn KEK dùng với cơ chế **AES Key Wrap** để bảo vệ DEK.

Một DEK dùng để mã hóa cả tập hợp dữ liệu sẽ có phạm vi ảnh hưởng rộng hơn DEK chỉ dùng cho một đối tượng. Vì vậy, số lượng DEK, thời hạn sử dụng và phạm vi chia sẻ DEK là những quyết định thiết kế quan trọng.

### 2.2. KEK, master key, root key và KMS key không luôn đồng nghĩa

~~~mermaid
flowchart TD
    R["Root / master key (nếu hệ thống có)"] --> K1["KEK: bảo vệ nhóm DEK A"]
    R --> K2["KEK: bảo vệ nhóm DEK B"]
    K1 --> D1["DEK hóa đơn 1"]
    K1 --> D2["DEK hóa đơn 2"]
    K2 --> D3["DEK tệp sao lưu"]
    D1 --> C1["Bản mã hóa đơn 1"]
    D2 --> C2["Bản mã hóa đơn 2"]
    D3 --> C3["Bản mã tệp"]
~~~

Sơ đồ minh họa một **hệ phân cấp khóa**, không phải cấu trúc bắt buộc của mọi nhà cung cấp.

- **DEK:** khóa trực tiếp bảo vệ dữ liệu.
- **KEK:** khóa bảo vệ các khóa, thường là DEK. Có thể có nhiều tầng KEK.
- **Master/root key:** thuật ngữ dành cho khóa ở tầng cao hơn trong một thiết kế phân cấp. Khóa gốc có thể bảo vệ KEK, nhưng không phải hệ thống nào cũng công khai hay triển khai một tầng như vậy.
- **KMS key:** trong dịch vụ KMS, có thể là tài nguyên khóa logic có **key ID**, chính sách và các phiên bản vật liệu khóa. Tài nguyên đó có thể đóng vai trò KEK; tên gọi và cách quản lý phiên bản phụ thuộc nhà cung cấp.
- **CMK (Customer Master Key / Customer-Managed Key):** tên gọi dễ gây nhầm lẫn giữa các nền tảng và phiên bản tài liệu. Khi thiết kế, nên xác định **chức năng và API thực tế của khóa**, thay vì suy luận từ chữ “master”.

**Ví dụ:** một doanh nghiệp quản lý KEK riêng cho production và staging. Trong production, mỗi dịch vụ hoặc từng miền dữ liệu nhạy cảm có KEK riêng; DEK có thể được sinh theo từng tệp hoặc từng nhóm bản ghi. Cách phân lớp giúp giảm phạm vi ảnh hưởng khi một quyền hoặc khóa bị lộ.

### 2.3. KEK có thể đối xứng hoặc bất đối xứng

**KEK đối xứng:** cùng vật liệu khóa bí mật được dùng cho thao tác wrap/unwrap theo một cơ chế đối xứng phù hợp, ví dụ AES-KW hoặc AES-KWP. Đây là mô hình thường gặp trong các dịch vụ KMS bảo vệ DEK.

**KEK bất đối xứng:** public key của bên nhận có thể được dùng để mã hóa/bọc hoặc đóng gói khóa dữ liệu theo cơ chế thích hợp; private key tương ứng cần được bảo vệ để giải mã hoặc khôi phục DEK. Ví dụ, RSA-OAEP có thể mã hóa lượng dữ liệu khóa giới hạn; những thiết kế hiện đại khác dùng **KEM + KDF + mã hóa đối xứng** trong một giao thức đã được phân tích.

Trong thiết kế bất đối xứng, **public key có thể phân phối**, nhưng phải xác thực đúng chủ sở hữu và đúng mục đích. **Private key** phải được kiểm soát chặt. Không dùng Ed25519 (chữ ký số) như thuật toán bọc khóa; không suy diễn rằng mọi public key đều có chức năng mã hóa.

## 3. Bọc khóa (key wrapping) là gì?

**Key wrapping** là quá trình biến một khóa cần bảo vệ (ví dụ DEK) thành dạng đã được mã hóa và kiểm tra toàn vẹn bởi cơ chế phù hợp, sử dụng KEK. Kết quả thường được gọi là **wrapped key**, **encrypted data key** hoặc **encrypted DEK**.

~~~text
Wrap(KEK, DEK, các tham số/ngữ cảnh) -> WrappedDEK
Unwrap(KEK, WrappedDEK, các tham số/ngữ cảnh) -> DEK hoặc lỗi xác thực
~~~

**Không phải phép mã hóa tùy ý nào cũng nên dùng để bọc khóa.** Vật liệu khóa có giá trị cao, nên phương pháp wrap cần đáp ứng các yêu cầu bảo mật và tính toàn vẹn theo mô hình đe dọa:

| Cơ chế | Phù hợp khi | Điểm cần lưu ý |
| --- | --- | --- |
| **AES-KW (RFC 3394)** | Bọc vật liệu khóa có độ dài phù hợp theo quy định của chuẩn | Bao gồm kiểm tra toàn vẹn theo cơ chế của chuẩn; chỉ áp dụng cho những độ dài và điều kiện được hỗ trợ |
| **AES-KWP (RFC 5649)** | Cần bọc khóa/dữ liệu khóa có độ dài linh hoạt hơn | Có cơ chế padding và kiểm tra toàn vẹn theo chuẩn; dùng thư viện tin cậy |
| **AES-GCM làm AEAD wrap** | Giao thức cho phép mã hóa khóa với xác thực và AAD | Phải bảo đảm nonce **không lặp lại dưới cùng KEK**; lưu tag/nonce, xác thực trước khi chấp nhận DEK |
| **RSA-OAEP** | Cần bọc một lượng vật liệu khóa nhỏ cho bên giữ private key tương ứng | Kích thước plaintext bị giới hạn; xác thực public key của người nhận |
| **KEM hoặc hybrid encryption chuẩn hóa** | Trao đổi/đóng gói bí mật chung rồi dẫn xuất khóa bọc | Phải dùng toàn bộ giao thức KEM/KDF/DEM được chỉ định, không ghép nguyên thủy tùy ý |
| **KMS Encrypt/Decrypt/ReEncrypt hoặc Wrap/Unwrap** | Muốn ủy quyền thao tác bảo vệ DEK cho dịch vụ quản lý khóa | Tên, giới hạn payload, cách định danh khóa và xử lý ngữ cảnh tùy nhà cung cấp |

Không nên dùng **AES-ECB**, “RSA thô”, phép XOR tự chế hoặc một đoạn mã hóa tùy tiện để bọc khóa. Nếu dùng AES-GCM cho cả DEK và KEK, cần phân biệt rõ vai trò khóa, nonce và ngữ cảnh; không tái sử dụng cùng khóa cho những mục đích khác nhau mà không có thiết kế phân tách khóa được phân tích.

**Bọc khóa khác mã hóa dữ liệu:** đối tượng đầu vào của key wrapping là **một khóa**, thường chỉ vài chục byte; dữ liệu nghiệp vụ có thể rất lớn. Envelope encryption khai thác sự khác biệt này để giữ thao tác KMS nhỏ và giới hạn số lần cần dùng KEK.

## 4. Envelope encryption: KEK tham gia như thế nào?

Xét dịch vụ Java lưu hóa đơn. Một luồng thông dụng dùng **KEK trong KMS** và **DEK AES-256**:

~~~mermaid
sequenceDiagram
    participant S as InvoiceService
    participant K as KMS/HSM
    participant D as Database
    Note over S,K: Ghi hóa đơn
    S->>K: GenerateDataKey với KEK và context được phép
    K-->>S: DEK rõ tạm thời + wrappedDEK + thông tin khóa
    S->>S: AES-GCM mã hóa hóa đơn bằng DEK, nonce duy nhất, AAD
    S->>D: Lưu ciphertext, tag, nonce, wrappedDEK, key ID/version, metadata
    S->>S: Giảm thời gian tồn tại DEK rõ trong bộ nhớ
    Note over S,K: Đọc hóa đơn
    S->>D: Đọc ciphertext và wrappedDEK
    D-->>S: Ciphertext + wrappedDEK + metadata
    S->>S: Kiểm tra quyền nghiệp vụ của người dùng/tenant
    S->>K: Decrypt/Unwrap wrappedDEK với context hợp lệ
    K-->>S: DEK rõ tạm thời nếu được cấp quyền
    S->>S: Xác thực tag GCM và giải mã, trả về dữ liệu hợp lệ
~~~

Trong mô hình minh họa, KMS có API tương tự **GenerateDataKey** và **Decrypt**; không phải mọi KMS đều dùng tên hay cách trả kết quả như vậy. Một số hệ thống có thể thực hiện unwrap ngay trong HSM hoặc ứng dụng và phải quản lý ranh giới bộ nhớ khác nhau.

### 4.1. Những gì được lưu với bản mã

~~~json
{
  "ciphertext": "<base64 ciphertext and GCM tag>",
  "nonce": "<base64 unique GCM nonce>",
  "wrappedDek": "<base64 key wrapped by the KEK>",
  "kekId": "invoice-production-kek",
  "kekVersion": "v4",
  "dekAlgorithm": "AES-256-GCM",
  "wrapAlgorithm": "<KMS-managed algorithm>",
  "tenantId": "tenant-42",
  "invoiceId": "inv-2026-001"
}
~~~

Đây chỉ là **cấu trúc minh họa**, không phải một bản mã có thể giải mã. Tùy KMS, blob wrapped DEK có thể đã tự chứa thông tin về khóa hoặc phiên bản; vẫn cần lưu metadata cần thiết để phục hồi và điều tra. **Nonce, ciphertext, tag và key ID thường không phải bí mật**, nhưng phải được xử lý đúng và xác thực phù hợp. **DEK dạng rõ và KEK bí mật tuyệt đối không được ghi kèm bản mã**.

Metadata có thể được ràng buộc với nội dung bằng **AAD** của AES-GCM, và với wrapped DEK bằng **encryption context/AAD của KMS** nếu được hỗ trợ. Chẳng hạn, tenant ID và loại tài liệu có thể được xác thực ở hai tầng để hạn chế tráo bản ghi giữa tenant. Ngữ cảnh dùng làm kiểm soát bảo mật phải bắt nguồn từ danh tính/phân quyền đã xác thực; không chỉ tin giá trị do client tự gửi. Ngoài ra, **encryption context có thể xuất hiện trong audit log của KMS**, nên không đưa dữ liệu bí mật vào đó.

### 4.2. KEK giảm rủi ro gì và không giải quyết được gì?

Với kẻ tấn công chỉ đọc được bản sao database, việc lưu **wrapped DEK** thay vì DEK rõ tạo ra một ranh giới bảo vệ: kẻ đó chưa có KEK hoặc quyền unwrap, nên chưa thể giải mã dữ liệu.

Tuy nhiên, nếu kẻ tấn công chiếm tài khoản ứng dụng có quyền **Decrypt/Unwrap** rộng, KMS có thể trả DEK cho kẻ tấn công theo một yêu cầu hợp lệ về mặt kỹ thuật. Nếu ứng dụng đã giải mã dữ liệu trong bộ nhớ, kẻ chiếm tiến trình cũng có thể đọc plaintext. **KEK không thay thế kiểm soát truy cập, quyền nghiệp vụ, tách tenant và kiểm toán.**

## 5. Vòng đời của Key Encryption Key

KEK là tài sản bảo mật có phạm vi ảnh hưởng lớn: một KEK có thể bảo vệ hàng nghìn hoặc hàng triệu DEK. Việc quản lý KEK cần được thiết kế như một quy trình xuyên suốt.

| Giai đoạn | Việc cần thực hiện | Rủi ro nếu làm sai |
| --- | --- | --- |
| **1. Tạo khóa** | Sinh vật liệu KEK bằng nguồn ngẫu nhiên mật mã đủ mạnh; chọn thuật toán/độ dài, định danh, mục đích, owner và chính sách | KEK đoán được, tái sử dụng sai mục đích hoặc không rõ ai chịu trách nhiệm |
| **2. Đăng ký và cấp phát** | Tạo KEK trong KMS/HSM, chỉ cấp quyền thao tác cần thiết cho workload được xác thực | KEK bị xuất, nhân bản vào cấu hình hoặc cấp quyền unwrap cho sai dịch vụ |
| **3. Lưu trữ và backup** | Giữ KEK trong ranh giới tin cậy; kiểm soát backup/replica, khôi phục và vòng đời bản sao | Lộ KEK qua bản sao lưu hoặc mất toàn bộ khả năng mở DEK |
| **4. Sử dụng** | Dùng key wrapping/unwrap đúng chuẩn; áp dụng IAM, context, chính sách tenant và hạn mức phù hợp | Kẻ chiếm tài khoản có thể mở hàng loạt DEK dù không lấy được KEK |
| **5. Rotation** | Chuyển sang phiên bản KEK mới, lên kế hoạch dùng khóa mới cho wrap và xử lý wrapped DEK cũ | Hệ thống mới dùng khóa mới nhưng không thể đọc dữ liệu cũ |
| **6. Thu hồi/vô hiệu hóa** | Chặn quyền hoặc phiên bản bị ảnh hưởng; điều tra phạm vi lộ, bản mã và DEK phụ thuộc | Khóa đã lộ tiếp tục được sử dụng, hoặc ứng dụng ngừng hoạt động đột ngột |
| **7. Lưu giữ và hủy** | Duy trì khả năng giải mã dữ liệu/backup theo thời hạn; hủy khi đã kiểm kê hết phụ thuộc | Xóa sớm làm dữ liệu không khôi phục được; giữ quá lâu tăng diện tấn công |

### 5.1. Tạo và lưu KEK

Ưu tiên sinh KEK bằng cơ chế quản lý khóa chuyên dụng, thay vì dùng chuỗi từ mật khẩu, timestamp, số thứ tự hoặc khóa cố định trong source code. Độ dài và loại khóa phải tương thích với thuật toán wrapping cũng như chính sách tổ chức.

Với KEK được đánh dấu **non-exportable** trong HSM/KMS, ứng dụng gọi API wrap/unwrap; vật liệu KEK không cần đi vào tiến trình Java. Điều này giảm một đường rò rỉ quan trọng nhưng **không đồng nghĩa quyền sử dụng KEK là vô hại**: tài khoản có thể gọi Decrypt với mọi wrapped DEK vẫn có thể bị lạm dụng.

Nếu cần backup/replication KEK, phải biết rõ nhà cung cấp có hỗ trợ hay không, phạm vi vùng/hệ thống, cơ chế mã hóa và phục hồi, quyền duyệt quy trình và hậu quả nếu mất backup. Không tự xuất KEK ra tệp không được bảo vệ chỉ để “có bản dự phòng”.

### 5.2. Cấp quyền sử dụng KEK theo nhiệm vụ

**Least privilege** áp dụng cho *ai được dùng khóa*, *dùng để làm gì*, *ở đâu* và *cho dữ liệu nào*.

| Danh tính hoặc vai trò | Nhu cầu | Quyền và ranh giới gợi ý |
| --- | --- | --- |
| **invoice-writer** | Mã hóa hóa đơn mới | Được sinh DEK và lấy wrapped DEK dưới KEK đúng môi trường; không có quyền quản trị/xóa KEK |
| **invoice-reader** | Giải mã hóa đơn được phân quyền | Được unwrap DEK chỉ trong phạm vi dữ liệu/tenant hợp lệ và sau kiểm tra quyền ứng dụng |
| **key-admin** | Quản trị chính sách và vòng đời | Quản trị KEK theo cơ chế phê duyệt; không mặc nhiên có quyền đọc mọi hóa đơn |
| **security-auditor** | Theo dõi thay đổi và hành vi | Quyền xem metadata/log; không cần quyền unwrap hoặc xuất khóa |
| **backup-restore** | Khôi phục có kiểm soát | Quyền tạm thời, có phê duyệt và audit; kiểm tra tương thích phiên bản KEK |

Đối với API **GenerateDataKey**, dịch vụ có thể nhận **DEK dạng rõ** để mã hóa. Vì thế đây vẫn là quyền nhạy cảm, không nên coi là hoàn toàn an toàn chỉ vì tên thao tác không phải Decrypt. Quyền của writer và reader ở trên chỉ là mẫu: giới hạn chính xác phụ thuộc API KMS và quy tắc nghiệp vụ.

Nên tách KEK giữa **production, staging, development**, giữa tổ chức hoặc miền dữ liệu có yêu cầu bảo mật khác nhau, và giữa chức năng không có lý do chia sẻ. Một KEK chung cho mọi tenant giúp đơn giản hóa vận hành nhưng cũng tạo **blast radius** lớn hơn và làm phân tách quyền phức tạp hơn.

## 6. Rotation KEK, rewrap DEK và re-encrypt khác nhau ra sao?

Ba thao tác thường bị gọi chung là “đổi khóa”, dù chi phí và tác động bảo mật hoàn toàn khác nhau.

| Thao tác | Khóa nào thay đổi? | Có cần đổi bản mã dữ liệu? | Ý nghĩa |
| --- | --- | --- | --- |
| **Rotate KEK** | Tạo hoặc chuyển sang vật liệu/phiên bản KEK mới | **Không nhất thiết** | Dữ liệu mới dùng cơ chế bọc với KEK mới; wrapped DEK cũ cần được hỗ trợ hoặc xử lý |
| **Rewrap DEK** | Thay lớp bọc quanh **cùng một DEK** bằng KEK mới | **Không** | Chuyển DEK từ sự phụ thuộc KEK cũ sang KEK mới; dữ liệu vẫn mã hóa bằng DEK cũ |
| **Rotate DEK + re-encrypt** | Thay DEK bảo vệ dữ liệu | **Có** | Mã hóa lại nội dung bằng DEK mới, nonce mới và metadata phù hợp |
| **Disable KEK cũ** | Thay trạng thái/quyền dùng KEK | Không tự động | Có thể khiến dữ liệu chưa rewrap không thể đọc |
| **Destroy KEK cũ** | Hủy vật liệu KEK và bản sao liên quan | Không tự động | Có thể làm wrapped DEK cũ không còn mở được vĩnh viễn |

### 6.1. Rotation trong trạng thái bình thường

Ví dụ tại thời điểm T0, hóa đơn cũ dùng DEK-A, bản DEK-A được bọc bằng **KEK-v1**. Đến T1, hệ thống chuyển sang **KEK-v2**:

~~~text
Trước:
  Ciphertext-A --dùng--> DEK-A
  WrappedDEK-A = Wrap(KEK-v1, DEK-A)

Sau khi rotate KEK cho thao tác mới:
  Ciphertext-A vẫn như cũ
  WrappedDEK-A vẫn dưới KEK-v1 (nếu chưa rewrap)
  DEK-B mới được bọc bằng KEK-v2

Sau khi rewrap DEK-A:
  Ciphertext-A vẫn như cũ
  WrappedDEK-A' = Wrap(KEK-v2, DEK-A)
~~~

Nhiều KMS hỗ trợ tự động giữ các phiên bản vật liệu khóa để **Decrypt dữ liệu cũ sau rotation**. Tuy nhiên cơ chế này không đồng nhất giữa dịch vụ và loại khóa; phải kiểm tra tài liệu API và chính sách cryptoperiod thực tế. **Không tự giả định rằng tạo khóa mới sẽ tự động đổi toàn bộ wrapped DEK cũ.**

Quy trình chuyển đổi an toàn thường là:

1. Kiểm kê dữ liệu, backup, wrapped DEK và phiên bản KEK đang phụ thuộc.
2. Tạo/cho phép KEK mới; cấu hình chính sách và giám sát.
3. Chuyển thao tác wrap mới sang KEK mới; giữ đường unwrap cho dữ liệu cũ trong giai đoạn chuyển đổi được kiểm soát.
4. Rewrap DEK cũ nếu chính sách yêu cầu; ưu tiên API **ReEncrypt/rewrap bên trong KMS/HSM** nếu được hỗ trợ để hạn chế lộ DEK ra ứng dụng.
5. Xác minh một mẫu dữ liệu đại diện và backup có thể đọc bằng đường mới; ghi nhận tỷ lệ hoàn thành theo từng phiên bản.
6. Chỉ hạn chế rồi hủy quyền dùng KEK cũ sau khi đã xử lý các phụ thuộc và kiểm tra khôi phục.

### 6.2. Nếu KEK bị lộ thì rewrap đã đủ chưa?

**Chưa chắc.** Rewrap giúp giảm phụ thuộc vào KEK cũ trong tương lai, nhưng không thể xóa những bản sao **wrapped DEK cũ** mà kẻ tấn công đã lấy trước đó. Nếu kẻ tấn công đã có cả **KEK-v1** và **WrappedDEK-A** trong bản sao dữ liệu, họ vẫn có thể mở DEK-A ngoại tuyến. Nếu chỉ có quyền gọi KMS Decrypt bị lạm dụng, hệ thống phải điều tra các DEK và dữ liệu mà quyền đó đã mở.

Cần phân biệt các tình huống:

- **Lộ thông tin đăng nhập/role có quyền unwrap nhưng KEK chưa lộ:** thu hồi credential/quyền, giám sát và điều tra các lời gọi KMS, đánh giá dữ liệu đã bị giải mã; đổi khóa có thể cần tùy phạm vi sự cố.
- **Lộ vật liệu KEK cùng wrapped DEK:** có thể phải **tạo DEK mới và re-encrypt** dữ liệu liên quan, bên cạnh thay KEK và thu hồi quyền cũ. Rewrap bằng KEK mới không làm bí mật lại một DEK đã bị tính ra trước đó.
- **Lộ DEK:** thay KEK không giải quyết được; dữ liệu được mã hóa bằng DEK bị lộ cần được đánh giá và thường phải mã hóa lại bằng DEK mới.
- **Mất KEK mà không có đường khôi phục:** wrapped DEK có thể trở nên vô dụng ngay cả khi bản mã còn nguyên vẹn. Đây là sự cố **availability** chứ không nhất thiết là rò rỉ.

Nguyên tắc phản ứng sự cố: xác định **khóa nào bị ảnh hưởng, phạm vi wrapped DEK/bản mã, bản sao lưu, log, người có quyền sử dụng và cửa sổ thời gian**, rồi lập kế hoạch khóa mới và dữ liệu cần tái mã hóa.

## 7. Ví dụ Java: dùng KMS để quản lý KEK cho hóa đơn

Ví dụ sau dùng **Java 17+** và API JCA cho phần AES-GCM. **KEK được giả định nằm trong KMS**, ứng dụng chỉ có một giao diện trừu tượng để sinh và mở DEK. Đây là mã minh họa luồng tích hợp; adapter KMS, phân quyền và cách lưu bản mã phải triển khai theo nhà cung cấp thực tế.

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Map;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public class InvoiceEnvelopeEncryption {
    private static final SecureRandom RNG = new SecureRandom();

    // Phần triển khai thực tế gọi SDK của KMS/HSM; không giữ KEK trong Java.
    public interface Kms {
        DataKey generateDataKey(
            String kekAlias, Map<String, String> context) throws Exception;

        byte[] unwrapDataKey(
            String kekId, String kekVersion, byte[] wrappedDek,
            Map<String, String> context) throws Exception;
    }

    public record DataKey(
        byte[] plaintextDek, byte[] wrappedDek, String kekId, String kekVersion) {}

    public record Envelope(
        byte[] ciphertextAndTag, byte[] nonce, byte[] wrappedDek,
        String kekId, String kekVersion, String tenantId, String invoiceId) {}

    private final Kms kms;

    public InvoiceEnvelopeEncryption(Kms kms) {
        this.kms = kms;
    }

    public Envelope encrypt(
        byte[] plaintext, String trustedTenantId, String invoiceId) throws Exception {

        // trustedTenantId lấy từ identity/quyền đã xác thực, không tin client.
        Map<String, String> context = Map.of(
            "tenantId", trustedTenantId,
            "purpose", "invoice");
        DataKey key = kms.generateDataKey("invoice-prod-kek", context);
        byte[] rawDek = key.plaintextDek();

        try {
            if (rawDek.length != 32) {
                throw new GeneralSecurityException("Expected 256-bit DEK");
            }
            byte[] nonce = new byte[12];
            RNG.nextBytes(nonce); // Phải đảm bảo không lặp với cùng DEK.

            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE,
                new SecretKeySpec(rawDek, "AES"),
                new GCMParameterSpec(128, nonce));

            cipher.updateAAD(aad(trustedTenantId, invoiceId));
            byte[] ciphertextAndTag = cipher.doFinal(plaintext);
            return new Envelope(
                ciphertextAndTag, nonce, key.wrappedDek(),
                key.kekId(), key.kekVersion(), trustedTenantId, invoiceId);
        } finally {
            Arrays.fill(rawDek, (byte) 0); // Giảm thời gian DEK rõ tồn tại.
        }
    }

    public byte[] decrypt(
        Envelope stored, String trustedTenantId, String invoiceId) throws Exception {

        // Trong ứng dụng thật, kiểm tra phân quyền nghiệp vụ trước khi đến đây.
        if (!stored.tenantId().equals(trustedTenantId)
                || !stored.invoiceId().equals(invoiceId)) {
            throw new GeneralSecurityException("Context mismatch");
        }
        Map<String, String> context = Map.of(
            "tenantId", trustedTenantId,
            "purpose", "invoice");

        byte[] rawDek = kms.unwrapDataKey(
            stored.kekId(), stored.kekVersion(), stored.wrappedDek(), context);

        try {
            if (rawDek.length != 32) {
                throw new GeneralSecurityException("Expected 256-bit DEK");
            }
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE,
                new SecretKeySpec(rawDek, "AES"),
                new GCMParameterSpec(128, stored.nonce()));

            cipher.updateAAD(aad(trustedTenantId, invoiceId));
            // doFinal xác thực GCM tag; lỗi xác thực phải dẫn tới từ chối.
            return cipher.doFinal(stored.ciphertextAndTag());
        } finally {
            Arrays.fill(rawDek, (byte) 0);
        }
    }

    // Mã hóa AAD có phân định độ dài để tránh nhập nhằng giá trị.
    private static byte[] aad(String tenantId, String invoiceId) {
        byte[] tenant = tenantId.getBytes(StandardCharsets.UTF_8);
        byte[] invoice = invoiceId.getBytes(StandardCharsets.UTF_8);
        return ByteBuffer.allocate(8 + tenant.length + invoice.length)
            .putInt(tenant.length).put(tenant)
            .putInt(invoice.length).put(invoice).array();
    }
}
~~~

**Cách đọc ví dụ:**

- KMS cấp **DEK 256 bit** ở dạng rõ tạm thời và một **wrapped DEK** đã được bảo vệ dưới KEK.
- **KEK không xuất hiện** trong mã, biến môi trường hay bản ghi dữ liệu. Ứng dụng chỉ gọi KMS với key alias và **context** được phép.
- **Ciphertext, GCM tag, nonce, wrapped DEK, KEK ID/version** phải được lưu đầy đủ để khôi phục sau này.
- Khi giải mã, hệ thống kiểm tra tenant/invoice, dùng đúng context với KMS và AAD AES-GCM, chỉ trả plaintext nếu xác thực tag thành công.
- Thao tác **xóa mảng DEK** chỉ giúp giảm thời gian một bản sao DEK ở dạng rõ tồn tại; JVM, SecretKeySpec hoặc thư viện có thể tạo bản sao khác. Không thể bảo đảm xóa hoàn toàn vật liệu nhạy cảm khỏi bộ nhớ managed runtime.

**Những phần cố ý chưa được triển khai trong ví dụ:** SDK KMS thật, nguồn định danh đã xác thực, phân quyền người dùng, kiểm soát tenant, lưu trữ bất biến, retry/idempotency, hạn mức thao tác, bảo vệ metadata, chiến lược nonce khi dùng lại DEK, quản lý version và xử lý sự cố. Đặc biệt, nếu KMS không có cơ chế ràng buộc encryption context như giao diện giả định, phải thiết kế kiểm soát tương đương ở tầng IAM/ứng dụng.

## 8. Thiết kế bảo vệ KEK trong KMS/HSM

Đặt KEK trong KMS/HSM là một lớp bảo vệ quan trọng, nhưng thiết kế an toàn cần kết hợp nhiều kiểm soát.

### 8.1. Bảo vệ khóa và quyền sử dụng

- **Ưu tiên khóa không xuất được** khi nền tảng hỗ trợ và phù hợp yêu cầu di chuyển/khôi phục. Tránh đưa KEK vào source code, file cấu hình, log, container image hoặc cùng backup với wrapped DEK.
- **Tách nhiệm vụ:** người quản trị KEK không mặc nhiên có quyền Decrypt; người đọc dữ liệu không có quyền thay policy/xóa khóa; thao tác phá hủy nên có xác nhận hoặc phê duyệt theo quy trình.
- **Xác thực workload:** dùng service identity được xác thực, token ngắn hạn và gắn quyền theo workload thay vì tài khoản dùng chung hoặc khóa API dài hạn.
- **Hạn chế tài nguyên/phạm vi:** mỗi principal chỉ sử dụng KEK cần thiết; có thể giới hạn bằng resource policy, grants, encryption context và phân tách tenant nếu nhà cung cấp hỗ trợ.
- **Theo dõi API:** cảnh báo tăng đột biến số lần unwrap, thay policy, tạo grant, vô hiệu hóa khóa, lên lịch xóa hoặc truy cập từ môi trường bất thường.
- **Kế hoạch sẵn sàng:** đánh giá độ trễ KMS, hạn mức, lỗi vùng dịch vụ, thời gian lưu cache DEK và chiến lược phục hồi phù hợp mô hình đe dọa.

**Không tin hoàn toàn encryption context do client cung cấp.** Nếu người dùng có thể tự thay tenant ID, trong khi chính sách KMS chỉ kiểm tra trường context mà không ràng buộc với danh tính hoặc quyền nghiệp vụ, kẻ tấn công có thể gửi context của tenant khác. Kiểm tra quyền ứng dụng là lớp bắt buộc.

### 8.2. Khi nào nên dùng nhiều KEK?

| Phương án | Ưu điểm | Đánh đổi |
| --- | --- | --- |
| Một KEK cho toàn bộ dữ liệu | Ít khóa, policy dễ thiết lập ban đầu | Quyền unwrap và sự cố có phạm vi rộng; khó tách owner/tenant |
| Một KEK theo môi trường | Ngăn dev/staging đụng vào khóa production | Mỗi môi trường vẫn có thể có nhiều loại dữ liệu/tenant |
| Một KEK theo dịch vụ hoặc nhóm dữ liệu | Giới hạn phạm vi sự cố, policy có chủ sở hữu rõ | Tăng quản trị, theo dõi rotation và chi phí KMS |
| Một KEK theo tenant nhạy cảm | Cách ly tenant và chính sách chuyên biệt | Tăng số lượng khóa, quota, chi phí và độ phức tạp vận hành |

Không có một mức phân chia KEK phù hợp mọi hệ thống. Quyết định dựa trên **phân loại dữ liệu, ranh giới quyền, tần suất sử dụng, yêu cầu tuân thủ, blast radius, chi phí và khả năng vận hành**.

## 9. Kiểm toán, sao lưu và phục hồi

Đối với KEK, audit quan trọng vì bản thân vật liệu khóa thường không thể xem trực tiếp. Sự kiện cần theo dõi gồm: tạo KEK, thay đổi policy/grant, yêu cầu Wrap/Unwrap/GenerateDataKey, rotation, lỗi quyền, disable, re-enable, rewrap, thay cấu hình backup và hủy khóa.

Một bản ghi kiểm toán hữu ích có thể gồm **thời gian, principal/workload, key ID/version, API, mục đích hoặc context không nhạy cảm, kết quả, request ID và nguồn yêu cầu**. Tránh ghi **KEK, DEK rõ, private key, token, bản rõ dữ liệu**; kiểm soát quyền và tính toàn vẹn của chính audit log.

### Phục hồi phải kiểm thử cả dữ liệu và khóa

Nếu chỉ sao lưu ciphertext và wrapped DEK nhưng **không còn đường mở KEK**, dữ liệu có thể không thể khôi phục. Ngược lại, backup được bảo vệ bởi cùng quyền admin như dữ liệu chính có thể bị lộ hoặc phá hủy đồng thời.

Cần có kịch bản khôi phục cho:

1. **Mất hoặc vô hiệu hóa nhầm KEK:** ai được phê duyệt khôi phục, có key version và wrapped DEK phù hợp không?
2. **KMS/HSM hoặc vùng dịch vụ gián đoạn:** yêu cầu RTO/RPO là gì, có replica hoặc chiến lược dự phòng được phê duyệt không?
3. **Khóa cũ sắp bị hủy:** backup lâu năm có còn wrapped DEK phụ thuộc khóa đó không?
4. **Di chuyển sang KMS mới:** có cơ chế rewrap hoặc re-encrypt an toàn, theo dõi tiến độ và xác minh dữ liệu trước khi chuyển không?
5. **Sự cố lộ quyền/KMS credential:** cách giới hạn số lần unwrap, điều tra audit log, thu hồi quyền và xử lý DEK đã được mở là gì?

**Hủy KEK có thể tương đương hủy quyền truy cập vĩnh viễn vào một lượng dữ liệu rất lớn.** Trước khi hủy, phải kiểm kê đủ dữ liệu, bản sao và ràng buộc lưu trữ; thử nghiệm đường khôi phục và có phê duyệt phù hợp.

## 10. Các hiểu nhầm và lỗi thiết kế thường gặp

**“Có AES-256 cho dữ liệu rồi thì không cần KEK.”** Nếu DEK lưu ngay cạnh bản mã hoặc cấp cho mọi dịch vụ, độ mạnh AES không giải quyết rủi ro lộ khóa. KEK giúp tạo thêm ranh giới quản lý DEK, nhưng không phải hệ thống nhỏ nào cũng bắt buộc dùng cấu trúc nhiều tầng; phải đánh giá mô hình đe dọa.

**“KEK chỉ là một tên khác của DEK.”** Hai khóa có vai trò khác nhau; dùng một khóa cho cả mã hóa dữ liệu và wrapping thường làm phạm vi sử dụng và chính sách khó kiểm soát. Cần tách mục đích khóa.

**“KEK ở HSM nên không ai giải mã trái phép được.”** HSM bảo vệ vật liệu KEK nhưng một workload có quyền unwrap quá rộng vẫn có thể lấy DEK. Phải bảo vệ **quyền sử dụng** như bảo vệ bản thân khóa.

**“Rotation KEK sẽ tự động mã hóa lại mọi bản ghi.”** Rotation KEK và re-encrypt dữ liệu khác nhau. Một DEK cũ có thể tiếp tục mã hóa dữ liệu cũ dù lớp bọc của nó đã được thay.

**“Rewrap là đủ sau mọi sự cố lộ khóa.”** Nếu DEK hoặc cả KEK lẫn wrapped DEK đã bị lấy, kẻ tấn công có thể đã giải mã bản sao cũ. Trường hợp đó phải đánh giá việc thay DEK và re-encrypt dữ liệu.

**“Wrapped DEK không cần kiểm tra toàn vẹn.”** Lớp wrapping phải dùng cơ chế phù hợp và xử lý lỗi xác thực; không dùng raw ECB hoặc thuật toán tự chế.

**“Hủy KEK cũ giúp an toàn ngay lập tức.”** Hủy quá sớm có thể làm hóa đơn và backup còn giá trị nghiệp vụ trở nên không thể đọc. Phải hiểu đầy đủ phụ thuộc.

## 11. Checklist triển khai KEK

1. **Mục đích:** KEK bọc những DEK nào, theo thuật toán/chuẩn nào, với phạm vi dữ liệu gì?
2. **Phân tách:** production, staging, các dịch vụ và tenant quan trọng có KEK riêng khi phù hợp không?
3. **Sinh và lưu:** KEK được tạo từ nguồn ngẫu nhiên mật mã tin cậy, giữ trong KMS/HSM, hạn chế xuất và có kế hoạch backup/khôi phục không?
4. **Quyền:** ai có thể wrap, unwrap, generate data key, thay policy, disable và destroy KEK? Có tách quản trị với truy cập dữ liệu không?
5. **Ngữ cảnh:** KMS encryption context/AAD và AAD dữ liệu được gắn với identity và quyền nghiệp vụ đã xác thực chưa?
6. **Lưu trữ:** mỗi bản mã có đủ wrapped DEK, key ID/version, nonce/tag, định dạng/thuật toán để giải mã trong tương lai không?
7. **Rotation:** đã xác định trạng thái khóa cũ, thời hạn chuyển đổi, kế hoạch rewrap và điều kiện hủy chưa?
8. **Incident:** nếu lộ KEK, DEK hoặc quyền unwrap, có biết cần điều tra, revoke hay re-encrypt những dữ liệu nào không?
9. **Audit:** có log thao tác quản trị/unwrap, phát hiện bất thường mà không làm lộ DEK/KEK không?
10. **Recovery:** có thể đọc dữ liệu và backup cũ sau khi xoay khóa, khôi phục dịch vụ hoặc di chuyển KMS không?

### Câu hỏi tự kiểm tra

**Câu 1.** Database chứa ciphertext và wrapped DEK, nhưng KEK được giữ trong KMS. Nếu kẻ tấn công chỉ đọc được database, lợi ích bảo mật chính của KEK là gì?

**Gợi ý đáp án:** Kẻ tấn công chưa có vật liệu KEK hoặc quyền unwrap để lấy DEK dạng rõ, nên chưa thể giải mã dữ liệu chỉ từ bản sao database khi các lớp mật mã được triển khai đúng.

**Câu 2.** Sau khi thay KEK-v1 bằng KEK-v2, ứng dụng xóa KEK-v1 ngay nhưng chưa rewrap DEK cũ. Điều gì có thể xảy ra?

**Đáp án:** Wrapped DEK được bọc bằng KEK-v1 có thể không mở được; các bản mã phụ thuộc có nguy cơ mất khả năng giải mã và backup không thể phục hồi.

**Câu 3.** Công ty phát hiện kẻ tấn công đã sao chép KEK-v1 và toàn bộ wrapped DEK từ backup. Chỉ rewrap bằng KEK-v2 có đủ khắc phục rủi ro bí mật dữ liệu không?

**Đáp án:** Không. Kẻ tấn công vẫn có bản sao KEK-v1 và wrapped DEK cũ để khôi phục DEK. Cần đánh giá phạm vi, đổi DEK và re-encrypt dữ liệu liên quan, cùng thu hồi quyền và điều tra sự cố.

**Câu 4.** Vì sao người quản trị key policy không nên mặc nhiên có quyền Decrypt mọi DEK?

**Đáp án:** Tách nhiệm vụ hạn chế một tài khoản vừa thay chính sách vừa đọc mọi dữ liệu, giảm rủi ro lạm dụng nội bộ và hậu quả khi tài khoản quản trị bị chiếm.

**Câu 5.** Một dịch vụ gọi KMS GenerateDataKey và nhận DEK dạng rõ. Quyền đó có phải quyền không nhạy cảm vì dịch vụ không được gọi Decrypt?

**Đáp án:** Không. Quyền tạo DEK vẫn đưa vật liệu khóa bí mật vào bộ nhớ ứng dụng. Phải kiểm soát workflow, phạm vi dữ liệu, môi trường và nhật ký sử dụng.

## Kết luận

**KEK là khóa bảo vệ những khóa khác.** Trong envelope encryption, nó phân tách vật liệu mã hóa dữ liệu (DEK) khỏi lớp quản lý và cấp quyền sử dụng khóa, qua đó hỗ trợ phân quyền, rotation, audit và giảm phạm vi ảnh hưởng nếu kho bản mã bị lộ.

Giá trị bảo mật của KEK đến từ **cả cơ chế wrapping đúng chuẩn lẫn quản lý vòng đời**: tạo khóa an toàn, lưu trong KMS/HSM, xác thực workload, cấp quyền tối thiểu, dùng ngữ cảnh đúng, rewrap hoặc re-encrypt có kế hoạch, thu hồi khi sự cố và hủy khi không còn phụ thuộc. Thuật toán mạnh chỉ bảo vệ dữ liệu khi các khóa và quyền dùng khóa cũng được bảo vệ.
