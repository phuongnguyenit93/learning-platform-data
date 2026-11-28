# Key management là gì?

> **Chương:** Nền tảng key management  
> **Phạm vi:** SECURITY_KEY_MANAGEMENT_FUNDAMENTALS

## 1. Vì sao hệ thống cần quản lý khóa?

Mã hóa giúp biến dữ liệu đọc được (plaintext) thành dữ liệu khó hiểu nếu không có khóa phù hợp (ciphertext). Tuy nhiên, mức độ an toàn của dữ liệu không chỉ phụ thuộc vào thuật toán mã hóa: nếu kẻ tấn công lấy được khóa, họ có thể giải mã dữ liệu dù hệ thống đang dùng thuật toán mạnh.

Xét một dịch vụ lưu thông tin khách hàng:

- Cơ sở dữ liệu lưu thông tin đã được mã hóa bằng AES-256-GCM.
- Ứng dụng cần khóa để giải mã khi xử lý yêu cầu hợp lệ.
- Nếu khóa được ghi thẳng trong mã nguồn, bản sao mã nguồn bị lộ có thể làm lộ cả dữ liệu.
- Nếu khóa chỉ nằm trên một máy chủ nhưng máy này hỏng mà không có khả năng khôi phục, dữ liệu có thể không bao giờ giải mã lại được.
- Nếu một nhân viên đã mất quyền truy cập nhưng vẫn giữ bản sao khóa, việc xóa tài khoản nhân viên chưa đủ để ngăn truy cập dữ liệu cũ.

Vì vậy, bảo vệ dữ liệu mã hóa đòi hỏi quản lý khóa **trong suốt vòng đời của khóa**, chứ không dừng ở việc chọn thuật toán.

**Key management (quản lý khóa mật mã)** là tập hợp quy trình, chính sách, cơ chế kỹ thuật và trách nhiệm vận hành để **tạo, cấp phát, lưu trữ, sử dụng, phân quyền, giám sát, xoay vòng, thu hồi, lưu giữ phục vụ giải mã dữ liệu cũ và hủy khóa** một cách kiểm soát được.

Hai mục tiêu phải đạt đồng thời:

1. **Bảo mật:** Chỉ chủ thể và dịch vụ được phép mới có thể dùng khóa cho mục đích được phép.
2. **Khả dụng có kiểm soát:** Hệ thống vẫn có thể thực hiện thao tác mật mã hợp lệ, khôi phục sau sự cố và đọc dữ liệu còn thời hạn lưu trữ.

Nếu chỉ quan tâm bảo mật mà xóa nhầm khóa, dữ liệu trở nên không thể khôi phục. Nếu chỉ quan tâm tính sẵn sàng mà sao chép khóa tràn lan, nguy cơ rò rỉ tăng mạnh.

## 2. Key management quản lý những gì?

Một **khóa mật mã** là giá trị được thuật toán mật mã dùng để mã hóa, giải mã, tạo chữ ký, xác minh chữ ký hoặc dẫn xuất vật liệu khóa khác. Cần phân biệt khóa với các thành phần liên quan:

| Thành phần | Mục đích | Điểm cần quản lý |
| --- | --- | --- |
| **Khóa đối xứng** | Cùng một khóa bí mật được dùng cho mã hóa và giải mã, ví dụ AES | Giữ bí mật, kiểm soát quyền dùng, thời hạn và phiên bản khóa |
| **Cặp khóa bất đối xứng** | Khóa công khai (public key) và khóa riêng (private key); ví dụ RSA, ECC | Bảo vệ private key, phân phối public key đáng tin cậy |
| **Khóa ký số** | Private key tạo chữ ký; public key xác minh | Quyền ký, nguồn gốc chữ ký, khóa bị lộ hay bị thu hồi |
| **Khóa mã hóa dữ liệu (DEK)** | Mã hóa trực tiếp dữ liệu ứng dụng | Phạm vi dữ liệu, tuổi thọ, bản mã và thông tin xác thực kèm theo |
| **Khóa mã hóa khóa (KEK)** | Bọc/mã hóa DEK để tránh lưu DEK dạng rõ | Quyền bọc và mở bọc, các phiên bản KEK, phục hồi |
| **Chứng thư số (certificate)** | Gắn public key với một danh tính bằng cơ chế tin cậy | Thời hạn chứng thư, chuỗi tin cậy, thu hồi chứng thư |

**Mật khẩu, access token, API key và database password** cũng là bí mật cần bảo vệ, nhưng không nhất thiết là khóa mật mã. Hệ thống *secret management* thường quản lý các bí mật này; hệ thống *key management* tập trung vào vòng đời và các thao tác với khóa mật mã. Hai hệ thống có thể tích hợp, nhưng không nên đánh đồng chức năng.

Tương tự, **hash mật khẩu** không phải là mã hóa có thể giải ngược. Mật khẩu người dùng nên được xử lý bằng thuật toán băm mật khẩu chuyên dụng (chẳng hạn Argon2id, bcrypt hoặc scrypt) cùng tham số phù hợp; không lưu mật khẩu bằng cách mã hóa với một khóa chung rồi coi đó là giải pháp thay thế.

## 3. Vòng đời của một khóa mật mã

Một thiết kế tốt phải trả lời được: ai tạo khóa, ai dùng, khóa nằm ở đâu, khi nào phải thay, dữ liệu cũ còn đọc được không, và khi nào được phép hủy?

~~~mermaid
flowchart LR
    A[Định nghĩa mục đích và chính sách] --> B[Tạo khóa]
    B --> C[Cấp phát và kích hoạt]
    C --> D[Lưu trữ và sử dụng]
    D --> E[Xoay vòng hoặc thay thế]
    E --> D
    D --> F[Ngừng dùng hoặc thu hồi]
    F --> G[Lưu giữ có kiểm soát nếu còn dữ liệu cũ]
    G --> H[Hủy khóa khi hết phụ thuộc]
~~~

### 3.1. Xác định mục đích, thuật toán và phạm vi

Trước khi sinh khóa, cần xác định rõ:

- Khóa phục vụ **mã hóa dữ liệu**, **ký số**, **TLS**, **bọc khóa**, hay mục đích khác?
- Khóa thuộc hệ thống, môi trường, khách hàng hoặc tập dữ liệu nào?
- Dịch vụ nào được **encrypt/decrypt/sign/verify**? Có cần tách quyền theo thao tác không?
- Tuổi thọ dự kiến, chu kỳ xoay vòng, nhu cầu đọc dữ liệu cũ và khả năng khôi phục sau thảm họa là gì?

Không nên dùng cùng một khóa cho nhiều mục đích độc lập. Việc tách khóa theo nhiệm vụ, môi trường và phạm vi dữ liệu giúp giảm phạm vi ảnh hưởng khi một khóa bị lộ.

### 3.2. Tạo khóa (generation)

Khóa phải được tạo bởi nguồn ngẫu nhiên mật mã phù hợp (**CSPRNG**) hoặc một quy trình dẫn xuất khóa được thiết kế cho mục đích đó. Không tạo khóa từ thời gian hệ thống, số tăng dần, chuỗi cố định hay bộ sinh số ngẫu nhiên thông thường.

Ví dụ, ứng dụng Java có thể dùng **KeyGenerator** với thuật toán AES và nguồn ngẫu nhiên mật mã do nền tảng cung cấp. Trong hệ thống thực tế, việc sinh và giữ khóa cấp cao nên do KMS hoặc HSM đảm nhận khi thích hợp.

~~~java
// Ví dụ minh họa: sinh khóa AES dùng cho mã hóa dữ liệu cục bộ.
// Trong kiến trúc KMS, ưu tiên API sinh DEK của KMS khi cần envelope encryption.
KeyGenerator generator = KeyGenerator.getInstance("AES");
generator.init(256);
SecretKey dataKey = generator.generateKey();
~~~

Mẫu trên chỉ minh họa **cách sinh** khóa; chưa giải quyết việc lưu trữ, kiểm soát truy cập, bọc khóa và hủy vật liệu khóa trong bộ nhớ. Các yêu cầu ấy là phần cốt lõi của key management.

### 3.3. Cấp phát, kích hoạt và phân phối (provisioning)

Khóa hoặc quyền sử dụng khóa phải được cấp cho đúng chủ thể. Nếu phải truyền vật liệu khóa, kênh truyền cần được bảo vệ và bên nhận phải được xác thực. Với khóa có yêu cầu bảo vệ cao, nên ưu tiên gọi thao tác mật mã qua dịch vụ KMS/HSM thay vì xuất khóa ra nhiều máy.

Một hệ thống thường cấp quyền cho **danh tính dịch vụ** (workload identity/service account), gắn chính sách quyền cụ thể, thay vì dùng một tài khoản quản trị dùng chung cho mọi ứng dụng.

### 3.4. Lưu trữ và sử dụng (storage and use)

Khóa cần được bảo vệ **khi lưu trữ**, **khi truyền qua mạng** và **khi được sử dụng trong bộ nhớ**. Một số nguyên tắc:

- Không nhúng khóa bí mật vào mã nguồn, image container, file cấu hình được commit, tài liệu hay log.
- Tách vai trò người quản trị khóa và dịch vụ sử dụng khóa; tuân thủ nguyên tắc **ít quyền nhất**.
- Hạn chế xuất vật liệu khóa bí mật; ưu tiên khóa không thể xuất khỏi vùng bảo vệ khi có thể.
- Chỉ giữ DEK dạng rõ trong bộ nhớ đủ lâu cho thao tác cần thiết, giảm caching không kiểm soát.
- Gắn **key ID/version**, mục đích, chủ sở hữu, trạng thái và nhật ký thao tác cho mỗi khóa.

**Lưu ý:** mã hóa khóa khi lưu trong cơ sở dữ liệu chỉ chuyển bài toán sang câu hỏi “khóa dùng để mã hóa khóa được bảo vệ ở đâu?”. Vì vậy cần một **ranh giới tin cậy** phù hợp như KMS/HSM, thay vì cất khóa gốc cạnh bản mã với cùng quyền truy cập.

### 3.5. Xoay vòng và thay thế (rotation)

**Rotation** là đưa phiên bản khóa mới vào sử dụng theo chính sách hoặc khi phát hiện rủi ro. Một quy trình thông thường:

1. Tạo phiên bản khóa mới và kiểm tra quyền truy cập.
2. Chuyển các thao tác **mã hóa mới** sang khóa mới.
3. Giữ khả năng giải mã dữ liệu cũ bằng phiên bản khóa phù hợp trong thời gian cần thiết.
4. Lập kế hoạch bọc lại DEK hoặc mã hóa lại dữ liệu cũ nếu mục tiêu an toàn yêu cầu.
5. Ngừng dùng và hủy phiên bản cũ sau khi xác nhận không còn phụ thuộc.

Rotation **không mặc nhiên** khiến toàn bộ dữ liệu cũ được mã hóa lại, cũng không tự thu hồi các bản sao khóa đã lộ. Nếu khóa bị lộ, cần đánh giá phạm vi dữ liệu, thay khóa, mã hóa lại khi cần, thu hồi quyền và điều tra truy cập.

### 3.6. Ngừng dùng, thu hồi, lưu giữ và hủy (retire/revoke/destroy)

Cần phân biệt các trạng thái:

| Trạng thái/hành động | Ý nghĩa thực tế |
| --- | --- |
| **Disable / suspend** | Tạm ngăn các thao tác dùng khóa; thường có thể khôi phục |
| **Retire** | Ngừng sử dụng cho dữ liệu hoặc chữ ký mới; có thể còn cần khóa để đọc dữ liệu cũ |
| **Revoke** | Thu hồi quyền, độ tin cậy hoặc hiệu lực sử dụng theo cơ chế áp dụng; riêng chứng thư số có quy trình thu hồi chứng thư |
| **Destroy / delete** | Hủy vật liệu khóa theo chính sách; có thể khiến dữ liệu phụ thuộc không thể khôi phục |

Khi một khóa mã hóa bị hủy không thể phục hồi và không còn bản sao khả dụng, dữ liệu chỉ có thể giải mã bằng khóa đó có thể trở thành không thể đọc: đây là nguyên lý **cryptographic erasure**. Tuy nhiên, để tuyên bố xóa có hiệu lực, phải xét bản sao khóa trong backup, cache, snapshot, môi trường khác và các bản sao dữ liệu rõ đã tồn tại.

Không hủy phiên bản khóa cũ chỉ vì “đã đổi khóa mới” nếu vẫn có backup, bản ghi lâu dài hoặc đối tác cần giải mã dữ liệu được bảo vệ bằng phiên bản đó.

## 4. Ba thành phần kiến trúc thường gặp: KMS, HSM và envelope encryption

### 4.1. KMS là gì?

**Key Management Service (KMS)** cung cấp API và chính sách để tạo, quản lý và sử dụng khóa. Tùy sản phẩm, KMS có thể hỗ trợ:

- Tạo khóa và quản lý phiên bản, trạng thái, chu kỳ sống;
- Kiểm soát danh tính và quyền như encrypt, decrypt, generate data key, sign;
- Ghi nhật ký kiểm toán và tích hợp hệ thống cảnh báo;
- Tự động hóa rotation, quy trình vô hiệu hóa hoặc lập lịch xóa;
- Bảo vệ khóa bằng hạ tầng HSM hoặc các cơ chế bảo mật khác.

KMS **không tự bảo đảm** ứng dụng an toàn: chính sách cấp quyền quá rộng, cấu hình sai, mã nguồn ghi log plaintext hoặc lưu DEK dạng rõ vẫn có thể gây lộ dữ liệu.

### 4.2. HSM là gì?

**Hardware Security Module (HSM)** là phần cứng chuyên dụng cung cấp ranh giới bảo vệ cho vật liệu khóa và các thao tác mật mã. Thiết bị có thể sinh khóa, giữ private key/khóa cấp cao trong vùng được bảo vệ, thực hiện mã hóa hoặc ký mà không cần xuất khóa bí mật.

KMS là **dịch vụ/quy trình quản lý**, còn HSM là **thành phần bảo vệ bằng phần cứng**; một KMS có thể sử dụng HSM ở phía sau. Không phải mọi hệ thống đều cần vận hành HSM riêng. Quyết định phụ thuộc yêu cầu bảo mật, tuân thủ, chi phí, độ trễ và mức độ kiểm soát khóa.

### 4.3. Envelope encryption là gì?

Khi mã hóa lượng dữ liệu lớn, ứng dụng thường không gửi từng byte qua KMS. Thay vào đó, dùng hai lớp khóa:

- **DEK (Data Encryption Key):** khóa đối xứng để mã hóa nội dung trực tiếp, ví dụ AES-GCM.
- **KEK (Key Encryption Key):** khóa cấp cao trong KMS/HSM dùng để bọc (wrap) DEK.

~~~mermaid
flowchart TD
    APP[Ứng dụng có quyền] -->|Yêu cầu sinh DEK| KMS[KMS/HSM giữ KEK]
    KMS -->|DEK dạng rõ tạm thời + DEK đã bọc| APP
    APP -->|Mã hóa bằng DEK| DATA[Ciphertext + nonce + tag + metadata]
    APP -->|Lưu DEK đã bọc| WDEK[Wrapped DEK + key ID/version]
    DATA --> STORE[(Kho dữ liệu)]
    WDEK --> STORE
~~~

**Luồng mã hóa:**

1. Ứng dụng xác thực với KMS và được phép sinh hoặc bọc DEK.
2. KMS tạo/cấp DEK và bản DEK đã được bọc bằng KEK. Trong một số thiết kế, API hoặc luồng dữ liệu khác nhau; cần tuân theo hợp đồng của KMS đang dùng.
3. Ứng dụng dùng **DEK dạng rõ trong bộ nhớ** để mã hóa dữ liệu bằng thuật toán mã hóa có xác thực, chẳng hạn AES-GCM.
4. Ứng dụng lưu **ciphertext + nonce/IV + authentication tag + wrapped DEK + key ID/version** và metadata cần thiết; không lưu DEK dạng rõ.
5. Ứng dụng giảm tối đa thời gian giữ DEK dạng rõ trong bộ nhớ.

**Luồng giải mã:** ứng dụng lấy wrapped DEK và metadata, gọi KMS mở bọc (unwrap/decrypt) nếu được cấp quyền, rồi dùng DEK nhận được để giải mã và xác minh tag. Nếu ciphertext hoặc thông tin xác thực bị sửa trái phép, thao tác giải mã có xác thực phải thất bại.

Với AES-GCM, **nonce/IV phải không bị tái sử dụng cùng một khóa**. Thực tế hay dùng IV ngẫu nhiên 96 bit với quy trình kiểm soát số lần mã hóa theo khóa và nguy cơ trùng lặp, hoặc dùng phương án tạo nonce bảo đảm tính duy nhất. Cần xử lý đúng **AAD (Additional Authenticated Data)** nếu muốn ràng buộc ciphertext với tenant ID, record ID, phiên bản định dạng hay ngữ cảnh tương ứng; khi giải mã phải cung cấp chính xác AAD đã dùng.

Một thiết kế payload có thể như sau (minh họa, không phải tiêu chuẩn bắt buộc):

~~~json
{
  "formatVersion": 1,
  "algorithm": "AES-256-GCM",
  "kekKeyId": "customer-data-key",
  "kekVersion": "v3",
  "wrappedDek": "<base64>",
  "nonce": "<base64>",
  "ciphertextAndTag": "<base64>",
  "aadContext": {
    "tenantId": "tenant-42",
    "recordId": "record-1001"
  }
}
~~~

Khi **xoay KEK**, có thể **rewrap DEK** bằng KEK mới mà không cần mã hóa lại toàn bộ dữ liệu, nếu kiến trúc và API cho phép. Khi **thay DEK**, dữ liệu do DEK cũ bảo vệ thường cần được giải mã rồi mã hóa lại bằng DEK mới. Hai thao tác có chi phí và ý nghĩa bảo mật khác nhau.

## 5. Một ví dụ end-to-end trong ứng dụng thực tế

Giả sử dịch vụ **Customer Profile** lưu số định danh cá nhân của khách hàng. Hệ thống có nhiều tenant, dùng cơ sở dữ liệu chung và KMS tập trung.

**Khi ghi dữ liệu:**

1. Dịch vụ xác thực bằng danh tính workload; chính sách cho phép tạo DEK dưới KEK của đúng môi trường.
2. Dịch vụ sinh DEK mới cho phạm vi đã chọn (ví dụ mỗi bản ghi hoặc mỗi nhóm dữ liệu tùy thiết kế).
3. Dịch vụ mã hóa trường nhạy cảm bằng AES-GCM, dùng tenant ID và record ID làm AAD.
4. Dịch vụ lưu bản mã, nonce, tag, wrapped DEK, key ID và phiên bản định dạng.
5. Dịch vụ chỉ ghi log request ID, kết quả và mã lỗi phù hợp; không log DEK, plaintext hay thông tin định danh nhạy cảm.

**Khi đọc dữ liệu:**

1. Tầng nghiệp vụ kiểm tra quyền xem thông tin khách hàng.
2. Dịch vụ lấy đúng ciphertext và wrapped DEK của bản ghi.
3. KMS kiểm tra danh tính dịch vụ và quyền mở bọc, đồng thời ghi sự kiện sử dụng khóa.
4. Dịch vụ giải mã bằng AAD khớp với tenant và record hiện tại. Nếu bản mã bị tráo giữa tenant, xác minh tag sẽ thất bại khi AAD được dùng đúng.
5. Dịch vụ trả dữ liệu rõ **chỉ cho luồng xử lý được phép**, tránh lưu cache plaintext lâu hoặc chuyển sang log/tracing.

**Khi khóa bị nghi ngờ lộ:** nhóm vận hành xác định khóa nào và phiên bản nào liên quan, chặn quyền dùng không hợp lệ, rà soát nhật ký KMS và dữ liệu bị ảnh hưởng, chuẩn bị khóa mới, thay các DEK/KEK và mã hóa lại khi cần, rồi xử lý vòng đời khóa cũ. Việc tự động rotation không thay thế quy trình ứng phó sự cố.

Ví dụ cho thấy có **hai lớp kiểm soát độc lập**: phân quyền nghiệp vụ quyết định *ai được xem thông tin khách hàng*; phân quyền KMS quyết định *workload nào được dùng khóa*. Quyền giải mã bằng KMS không tự chứng minh rằng người dùng cuối có quyền xem bản ghi.

## 6. Kiểm soát truy cập và kiểm toán khóa

Trong thực tế, lỗi quản lý khóa thường bắt đầu từ quyền và quy trình vận hành hơn là việc AES hoặc RSA bị phá.

### 6.1. Least privilege và phân tách nhiệm vụ

Một mô hình vai trò tham khảo:

| Vai trò | Quyền nên có | Quyền cần hạn chế |
| --- | --- | --- |
| Dịch vụ ghi dữ liệu | Encrypt / GenerateDataKey với khóa đúng phạm vi | Xóa khóa, sửa policy, truy cập khóa của tenant khác |
| Dịch vụ đọc dữ liệu | Decrypt/Unwrap trong phạm vi đã phê duyệt | Quản trị khóa, mở bọc mọi khóa không giới hạn |
| Key administrator | Tạo khóa, quản lý policy, rotation, trạng thái | Đọc plaintext nghiệp vụ nếu không có nhu cầu |
| Security auditor | Đọc cấu hình chính sách và nhật ký | Dùng khóa để giải mã hoặc thay đổi policy |
| Quy trình khôi phục khẩn cấp | Quyền đặc biệt có thời hạn, kiểm soát và kiểm toán | Quyền thường trực dùng chung, không ghi dấu vết |

Không dùng một identity cho cả ứng dụng và quản trị khóa. Hạn chế quyền wildcard, yêu cầu xác thực mạnh với thao tác quản trị nhạy cảm, và kiểm tra cả quyền tại IAM, chính sách khóa lẫn quyền truy cập vào dữ liệu.

### 6.2. Nhật ký và giám sát

Các sự kiện cần có khả năng truy vết gồm: tạo/nhập khóa, thay policy, thay trạng thái, rotation, yêu cầu dùng khóa (theo khả năng ghi log của nền tảng), thất bại do từ chối quyền, lập lịch xóa và phục hồi khóa.

Với mỗi sự kiện, thường cần **thời điểm, danh tính gọi, loại thao tác, key ID, kết quả, nguồn yêu cầu và correlation/request ID**. Nhật ký phải được bảo vệ khỏi sửa/xóa trái phép và có chính sách lưu giữ rõ ràng.

Ví dụ tín hiệu đáng báo động:

- Một dịch vụ vốn chỉ mã hóa đột nhiên gọi giải mã hàng loạt.
- Key policy mở rộng cho tài khoản hoặc môi trường không liên quan.
- Số yêu cầu giải mã thất bại hoặc các lần bị từ chối quyền tăng bất thường.
- Có thao tác disable/delete key ngoài quy trình thay đổi được phê duyệt.

**Không đưa khóa bí mật, DEK dạng rõ, access token hoặc plaintext vào log**, kể cả log của hệ thống kiểm toán.

## 7. Rủi ro khi quản lý khóa sai cách

| Sai sót | Hậu quả có thể xảy ra | Biện pháp giảm thiểu |
| --- | --- | --- |
| Hard-code khóa trong source hoặc container image | Ai có bản sao source/image có thể lấy được khóa | KMS/secret store phù hợp, scan rò rỉ, thu hồi và thay khóa bị lộ |
| Lưu KEK cạnh ciphertext với cùng quyền | Chiếm quyền kho dữ liệu có thể lấy cả bản mã lẫn khóa | Tách ranh giới bảo mật, dùng KMS/HSM và IAM riêng |
| Mọi dịch vụ dùng chung một khóa | Một vụ lộ lan sang nhiều hệ thống, tenant hoặc môi trường | Tách khóa theo mục đích, dữ liệu và môi trường |
| Cấp quyền decrypt quá rộng | Tài khoản bị chiếm có thể giải mã lượng lớn dữ liệu | Least privilege, điều kiện truy cập, quan sát hành vi |
| Xoay khóa nhưng không xét dữ liệu cũ | Dữ liệu cũ không giải được hoặc tiếp tục phơi nhiễm | Lập kế hoạch phiên bản, rewrap/re-encrypt và khả năng đọc cũ |
| Xóa khóa trước khi kiểm tra backup | Mất dữ liệu không thể phục hồi | Kiểm tra phụ thuộc, lịch xóa, diễn tập phục hồi |
| Dùng lại nonce với cùng khóa AES-GCM | Phá vỡ giả định an toàn của GCM, có thể làm lộ thông tin | Chính sách tạo nonce duy nhất và giới hạn sử dụng DEK |
| Không lưu key ID/phiên bản trong metadata | Không biết dùng khóa nào để giải mã sau rotation | Lưu metadata phiên bản cùng bản mã |
| Không có audit và cảnh báo | Khó phát hiện lạm dụng, khó điều tra sự cố | Audit bất biến theo khả năng, cảnh báo bất thường |
| Chỉ bảo vệ khóa trên đĩa | Plaintext/DEK lộ qua memory dump, debug hoặc log | Giảm thời gian giữ khóa, kiểm soát môi trường chạy và dữ liệu quan sát |

## 8. Các quyết định thiết kế cần làm rõ

**Chọn ranh giới khóa:** mỗi môi trường (dev, staging, production) nên có quyền và khóa riêng. Với nhiều tenant, cân nhắc khóa tách theo tenant hoặc các cơ chế kiểm soát ngữ cảnh nghiêm ngặt; quyết định dựa trên mô hình đe dọa, quy mô, chi phí và khả năng vận hành.

**Chọn nơi thực hiện mật mã:** mã hóa tại ứng dụng giúp bảo vệ dữ liệu trước một số tình huống lộ cơ sở dữ liệu; mã hóa ổ đĩa/cơ sở dữ liệu giúp bảo vệ lớp lưu trữ nhưng có thể không bảo vệ dữ liệu khỏi tài khoản ứng dụng bị chiếm. Có thể kết hợp nhiều lớp.

**Chọn tính sẵn sàng và khôi phục:** cần biết KMS mất kết nối thì ứng dụng xử lý thế nào, có được cache DEK không và trong bao lâu, khóa/backup có khôi phục đa vùng được không, ai được phép khôi phục. Không tự sao chép private key hoặc KEK giữa vùng chỉ để “cho chắc” khi chưa có chính sách bảo vệ bản sao.

**Chọn chiến lược rotation:** chính sách nên dựa trên rủi ro, yêu cầu pháp lý/nội bộ, khả năng của thuật toán và sản phẩm KMS, lượng dữ liệu cần tái mã hóa. Cần phân biệt rotation định kỳ với phản ứng khi lộ khóa. Đừng coi một khoảng thời gian cố định là bảo đảm an toàn cho mọi hệ thống.

**Chọn chính sách xóa:** xác định thời hạn lưu giữ dữ liệu, trách nhiệm hủy, cơ chế khôi phục có kiểm soát và điều kiện xác nhận không còn dữ liệu phụ thuộc trước khi hủy vật liệu khóa.

## 9. Checklist triển khai cho kỹ sư

Trước khi đưa tính năng mã hóa vào production, nên tự trả lời:

- [ ] Dữ liệu/tác vụ nào cần bảo vệ? Mối đe dọa và ranh giới tin cậy là gì?
- [ ] Thuật toán, mục đích, phạm vi và danh tính sở hữu của mỗi khóa đã rõ chưa?
- [ ] Khóa được sinh bằng nguồn mật mã an toàn và bảo vệ bằng KMS/HSM hoặc giải pháp phù hợp chưa?
- [ ] Quyền encrypt, decrypt, sign và quản trị được tách và cấp tối thiểu chưa?
- [ ] Ứng dụng có tránh lưu khóa dạng rõ trong source, log, cấu hình, bản ghi và backup không?
- [ ] Payload có metadata cần thiết: key ID, version, algorithm/format, nonce, tag, wrapped DEK và AAD context không?
- [ ] Rotation có bảo đảm đọc dữ liệu cũ; rewrap và re-encrypt có quy trình riêng không?
- [ ] Có quy trình disable, thu hồi, ứng phó lộ khóa, diễn tập khôi phục và hủy khóa không?
- [ ] Audit và cảnh báo truy cập bất thường có hoạt động, không làm lộ bí mật không?
- [ ] Hệ thống đã kiểm tra trường hợp KMS lỗi, sai quyền, bản mã bị sửa, khóa cũ bị vô hiệu và mất kết nối chưa?

## 10. Câu hỏi tự kiểm tra

**1. Vì sao mã hóa AES-256 không đủ để kết luận dữ liệu đã an toàn?**  
Vì khóa có thể bị lộ qua source code, cấu hình, quyền sử dụng quá rộng hoặc bộ nhớ; ngoài ra còn có rủi ro mất khóa khiến dữ liệu không thể đọc.

**2. KMS và HSM có phải một thứ không?**  
Không. KMS là dịch vụ/cơ chế quản lý khóa và chính sách sử dụng. HSM là thiết bị bảo vệ vật liệu khóa và thực hiện thao tác mật mã; KMS có thể được xây dựng trên HSM.

**3. Khi rotation KEK, có bắt buộc mã hóa lại tất cả dữ liệu không?**  
Không nhất thiết. Trong envelope encryption, có thể bọc lại DEK dưới KEK mới. Nếu DEK cũ bị lộ hoặc yêu cầu thay khóa bảo vệ dữ liệu trực tiếp, có thể cần giải mã và mã hóa lại dữ liệu.

**4. Vì sao không nên xóa khóa cũ ngay sau rotation?**  
Backup và bản mã cũ có thể vẫn cần khóa đó để giải mã. Chỉ hủy sau khi đã kiểm tra đầy đủ phụ thuộc và chính sách lưu giữ.

**5. Nếu dịch vụ có quyền KMS Decrypt, người dùng gọi dịch vụ có tự động được xem mọi dữ liệu không?**  
Không. Kiểm soát truy cập ứng dụng đối với người dùng và dữ liệu phải được thực thi riêng với chính sách sử dụng khóa của dịch vụ.

## Ghi nhớ

Key management là **quản trị toàn bộ vòng đời và quyền sử dụng khóa mật mã**. Một kiến trúc mã hóa tốt cần kết hợp thuật toán phù hợp, khóa được sinh an toàn, ranh giới bảo vệ như KMS/HSM, envelope encryption khi cần, chính sách ít quyền nhất, nhật ký kiểm toán, rotation có kế hoạch và khả năng thu hồi/hủy không làm mất dữ liệu ngoài ý muốn.
