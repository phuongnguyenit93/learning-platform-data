# Key revocation (Thu hồi khóa mật mã)

## 1. Key revocation là gì?

**Key revocation** là việc **rút lại quyền sử dụng hoặc mức độ tin cậy đối với một khóa mật mã** trước thời điểm lẽ ra khóa còn được chấp nhận, hoặc khi có sự kiện khiến việc tiếp tục tin dùng khóa trở nên không an toàn. Mục tiêu là ngăn khóa tiếp tục được dùng cho các thao tác không được phép và hạn chế thiệt hại từ những dữ liệu, phiên làm việc hoặc chữ ký đã gắn với khóa đó.

Một khóa có thể được thu hồi vì nhiều lý do:

- **Nghi ngờ hoặc xác nhận lộ khóa**: private key bị sao chép, DEK xuất hiện trong log, KEK bị truy cập trái phép.
- **Chủ sở hữu hoặc quyền hạn thay đổi**: nhân viên rời tổ chức; dịch vụ bị ngừng hoặc mất quyền xử lý dữ liệu.
- **Khóa không còn đáng tin**: quy trình sinh khóa sai, thuật toán/cấu hình bị coi là yếu, chứng chỉ phát hành nhầm hoặc thông tin danh tính không còn đúng.
- **Khóa không còn thuộc phạm vi hoạt động**: kết thúc dự án, chấm dứt quan hệ đối tác hoặc thay đổi chính sách.
- **Ứng phó sự cố**: cần ngăn ngay khả năng giải mã, ký hoặc bọc khóa bằng một phiên bản cụ thể.

Trong module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, key revocation là một phần của vòng đời khóa: **tạo → cấp phát → lưu trữ → sử dụng → xoay vòng → thu hồi → hủy**. Nó liên quan trực tiếp đến mật mã đối xứng, bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, kiểm soát truy cập và kiểm toán.

**Điểm quan trọng:** Thu hồi là một quyết định **về quyền sử dụng và sự tin cậy**, không phải phép toán mật mã có thể tự động làm cho những bản sao khóa đã rò rỉ biến mất. Việc thu hồi có hiệu lực đến đâu phụ thuộc vào nơi khóa tồn tại, nơi quyết định tin cậy được thực thi và khả năng cập nhật của các bên liên quan.

## 2. Phân biệt revocation với rotation, disablement, expiration và destruction

Các thuật ngữ sau thường xuất hiện trong cùng một quy trình nhưng giải quyết vấn đề khác nhau.

| Thuật ngữ | Ý nghĩa | Điều cần lưu ý |
|---|---|---|
| **Key rotation** (xoay vòng khóa) | Sinh/chuyển sang vật liệu khóa hoặc phiên bản mới để thay khóa cũ trong hoạt động | Khóa cũ có thể còn được dùng để đọc dữ liệu lịch sử; rotation đơn lẻ chưa ngăn kẻ tấn công dùng bản sao khóa cũ |
| **Key revocation** (thu hồi khóa) | Rút lại quyền sử dụng hoặc quyết định không còn tin khóa/chứng chỉ | Phải có cơ chế thực thi và thông báo tới các thành phần xác minh/sử dụng |
| **Key disablement** (vô hiệu hóa khóa) | Chuyển khóa sang trạng thái không được dịch vụ quản lý cho phép thực hiện thao tác | Với KMS, đây thường là cơ chế kỹ thuật để thực thi thu hồi; không thể chặn bản sao khóa đã xuất khỏi KMS |
| **Key expiration** (hết hạn) | Khóa hoặc chứng chỉ vượt thời hạn hiệu lực đã quy định | Có thể xảy ra theo lịch, không nhất thiết do sự cố; cần chính sách kiểm tra thời hạn |
| **Key destruction** (hủy khóa) | Loại bỏ khả năng khôi phục/sử dụng vật liệu khóa trong phạm vi kiểm soát | Có thể khiến dữ liệu mã hóa không thể giải mã; yêu cầu xem xét backup, cache và bản sao |
| **Access revocation** (thu hồi quyền) | Tước quyền của một danh tính đối với API/khóa | Khóa vẫn có thể hoạt động cho các danh tính còn lại; có thể là đủ khi không có dấu hiệu khóa bị lộ |

**Ví dụ:** Nhân viên nghỉ việc nhưng private key chưa từng rời HSM, không còn quyền truy cập và không có dấu hiệu xâm phạm. Tổ chức có thể thu hồi quyền tài khoản, thu hồi chứng chỉ gắn với danh tính nếu cần và xem xét rotation theo chính sách. Ngược lại, nếu private key đã bị sao chép, chỉ tắt tài khoản là không đủ: phải ngăn các bên tiếp tục tin khóa cũ, thay khóa và xử lý hậu quả.

Cũng cần phân biệt **ngừng dùng khóa để tạo dữ liệu/chữ ký mới** với **ngừng chấp nhận khóa khi đọc hoặc xác minh dữ liệu cũ**. Hệ thống có thể phải giải mã hồ sơ lịch sử bằng phiên bản cũ trong giai đoạn chuyển đổi; khi khóa bị lộ, việc giữ quyền giải mã cho phiên bản cũ là quyết định rủi ro cần kiểm soát chặt chẽ.

## 3. Thu hồi hoạt động khác nhau theo loại khóa

### 3.1. Khóa đối xứng: AES key, DEK và KEK

Khóa đối xứng có thể dùng để mã hóa và giải mã cùng một tập dữ liệu. Nếu **Data Encryption Key (DEK)** bị lộ, người có DEK và bản mã liên quan có thể tự giải mã mà không cần gọi dịch vụ. Vì vậy:

1. Dừng tạo bản mã mới bằng DEK đã lộ và chặn các thao tác sử dụng nó trong dịch vụ.
2. Xác định những dữ liệu, bản sao lưu và hệ thống đang sử dụng DEK.
3. Tạo DEK mới, mã hóa lại dữ liệu cần bảo vệ và chuyển các bên đọc/ghi sang phiên bản mới.
4. Kiểm soát dữ liệu/bản rõ và bản sao cũ; ghi nhận rằng dữ liệu từng bị kẻ tấn công giải mã không thể được làm bí mật trở lại chỉ bằng thay khóa.

Với **Key Encryption Key (KEK)** dùng để bọc DEK trong envelope encryption, cần đánh giá mức độ lộ cụ thể:

- **Rotation định kỳ, không nghi bị lộ**: có thể bọc lại (rewrap) DEK bằng KEK mới mà không mã hóa lại toàn bộ dữ liệu, nếu thiết kế cho phép.
- **KEK bị lộ**: kẻ tấn công có thể có khả năng giải bọc các DEK cũ mà họ đã thu thập cùng với KEK. Rewrap giúp bảo vệ các bản sao đang phục vụ sau khi chuyển đổi, nhưng **không vô hiệu hóa được những encrypted DEK, bản mã hoặc KEK cũ mà kẻ tấn công đã lưu**. Cần điều tra phạm vi, cân nhắc sinh DEK mới và mã hóa lại dữ liệu bị ảnh hưởng.
- **KEK chưa lộ nhưng một dịch vụ bị chiếm quyền decrypt**: tước quyền sử dụng KMS và khắc phục danh tính dịch vụ có thể là biện pháp đầu tiên; vẫn cần đánh giá có DEK/bản rõ nào đã bị lấy đi hay không.

Thu hồi hoặc vô hiệu hóa KEK trong KMS không tự xóa vật liệu DEK đã được ứng dụng lấy ra và giữ trong RAM, bộ nhớ đệm, log hoặc backup.

### 3.2. Private key dùng để ký số

Với chữ ký số, **private key** tạo chữ ký và **public key** xác minh chữ ký. Public key vốn được phép công khai. Khi private key bị lộ:

- Kẻ tấn công có thể tạo chữ ký hợp lệ về mặt toán học.
- Thay private key và thông báo tới các bên xác minh để họ không chấp nhận khóa cũ theo chính sách.
- Nếu sử dụng **chứng chỉ số theo PKI**, cần thu hồi chứng chỉ liên quan, công bố trạng thái qua cơ chế của CA và cập nhật cấu hình tin cậy.
- Nếu ứng dụng tự phân phối public key, cần xóa hoặc đánh dấu không tin cậy tại **mọi verifier**, bao gồm các phiên bản ứng dụng, gateway và cache còn hoạt động.

Một chữ ký cũ **có thể vẫn xác minh đúng về toán học** sau khi private key bị thu hồi. Có chấp nhận chữ ký được tạo **trước thời điểm sự cố** hay không là câu hỏi về thời điểm ký đáng tin, chứng chỉ, timestamp và chính sách xác thực. Không được tự động coi mọi chữ ký quá khứ là giả, cũng không tự động tin mọi chữ ký chỉ vì phép kiểm tra Verify trả về thành công.

### 3.3. Public key dùng cho mã hóa hoặc thỏa thuận khóa

Nếu khóa riêng dùng để giải mã bị lộ, dữ liệu từng mã hóa cho public key tương ứng có thể bị đọc nếu kẻ tấn công đã lưu bản mã. Cần thay cặp khóa, ngừng mã hóa dữ liệu mới tới public key cũ, đồng thời đánh giá khả năng phải mã hóa lại dữ liệu lưu trữ.

Với giao thức trao đổi khóa, cần xác định khóa dài hạn nào xác thực danh tính và khóa phiên nào được dẫn xuất. Thu hồi chứng chỉ hoặc private key dài hạn sẽ ảnh hưởng đến **các kết nối mới khi bên kiểm tra đã cập nhật trạng thái**; nó không tự động làm mất hiệu lực mọi phiên đã thiết lập hoặc xóa bí mật phiên đã bị đánh cắp. Cách phản ứng phụ thuộc vào giao thức và tính chất forward secrecy.

### 3.4. Khóa ký JWT, API token và hệ thống phân tán

Khi khóa ký JWT hoặc token bị lộ:

- Kẻ tấn công có thể tạo token có chữ ký hợp lệ cho đến khi verifier từ chối khóa đó.
- Đổi **kid** (key ID) hoặc phát hành khóa mới không tự khiến verifier từ chối token ký bằng khóa cũ.
- Nếu verifier lấy khóa qua JWKS, cần xem **TTL của cache**, cách làm mới khóa và chính sách từ chối một key ID đã bị thu hồi.
- Token đã phát hành có thể còn hiệu lực đến khi hết hạn, trừ khi có cơ chế thu hồi/token denylist, phiên bản phiên hoặc đổi chính sách chấp nhận chữ ký.
- Cần thu hồi refresh token hoặc phiên đăng nhập liên quan nếu mô hình rủi ro yêu cầu.

Đây là ví dụ điển hình cho thấy **revocation có tính phân tán**: mọi bên xác minh phải thực sự nhận và áp dụng thông tin thu hồi.

## 4. Thu hồi chứng chỉ số: CRL, OCSP và giới hạn

Trong **Public Key Infrastructure (PKI)**, một **chứng chỉ số (certificate)** liên kết public key với chủ thể và được tổ chức phát hành chứng chỉ (CA) ký xác nhận. Thu hồi chứng chỉ thông báo rằng chứng chỉ không còn được tin cậy theo chính sách, dù thời hạn ghi trong chứng chỉ chưa hết.

| Cơ chế | Cách làm việc | Giới hạn cần biết |
|---|---|---|
| **CRL (Certificate Revocation List)** | CA công bố danh sách chứng chỉ đã thu hồi; bên kiểm tra tải và kiểm tra theo chính sách | Danh sách có chu kỳ cập nhật, có thể trễ; client phải tải và thực sự kiểm tra |
| **OCSP (Online Certificate Status Protocol)** | Bên kiểm tra hỏi responder về trạng thái một chứng chỉ | Phụ thuộc độ sẵn sàng, cache và chính sách xử lý khi không lấy được kết quả |
| **OCSP stapling** | Server gửi kèm phản hồi trạng thái OCSP đã được ký trong quá trình bắt tay theo giao thức hỗ trợ | Vẫn phụ thuộc độ mới/hạn dùng của phản hồi và cách client xác minh |
| **Danh sách tin cậy/denylist nội bộ** | Hệ thống chủ động từ chối fingerprint, certificate serial hoặc key ID | Phải phân phối đầy đủ và ngăn cache cũ tiếp tục chấp nhận |

Khi kiểm tra trạng thái PKI, cần xác thực nguồn và chữ ký của phản hồi, thời điểm hiệu lực và mối liên hệ với chứng chỉ/CA thích hợp. Nếu không tra cứu được trạng thái, **fail-open** (vẫn chấp nhận) và **fail-closed** (từ chối) đều có hệ quả vận hành và bảo mật; chính sách phụ thuộc loại ứng dụng và yêu cầu tin cậy. Không giả định mọi trình duyệt hoặc thư viện TLS đều xử lý revocation giống nhau.

**Certificate revocation không xóa private key** khỏi thiết bị đã bị xâm phạm. Một kẻ có private key vẫn có thể tạo chữ ký; chữ ký ấy sẽ bị từ chối **chỉ tại những nơi đã áp dụng đúng quy tắc kiểm tra trạng thái/tin cậy**.

## 5. Khi nào phải thu hồi ngay và khi nào theo kế hoạch?

| Tình huống | Định hướng hành động |
|---|---|
| Private key ký giao dịch bị phát hiện trong kho công khai | Thu hồi/khóa quyền tin cậy ngay, thay cặp khóa và kiểm tra lịch sử chữ ký |
| DEK chứa trong log sản xuất có thể truy cập ngoài phạm vi | Dừng dùng DEK, điều tra dữ liệu bị ảnh hưởng, tạo DEK mới và mã hóa lại nếu cần |
| Tài khoản service bị chiếm quyền gọi KMS decrypt | Tước danh tính/quyền truy cập, khoanh vùng yêu cầu decrypt, đánh giá lộ DEK/bản rõ và quyết định thay khóa |
| Chứng chỉ TLS đang dùng bị xác định sai danh tính hoặc private key lộ | Thu hồi chứng chỉ, cấp chứng chỉ/khóa mới và cập nhật máy chủ/client |
| KEK đến hạn xoay vòng, không có dấu hiệu sự cố | Kích hoạt KEK mới, rewrap hoặc duy trì phiên bản lịch sử theo thiết kế, kiểm thử rồi ngừng KEK cũ |
| Người dùng thông thường nghỉ việc, khóa ở trong HSM và không có dấu hiệu lộ | Thu hồi quyền và danh tính, rà soát chính sách/chứng chỉ, quyết định có thay khóa theo phạm vi trách nhiệm |

Không nên biến mọi sự kiện thành thao tác **hủy khóa ngay lập tức**. Hủy khi chưa kiểm kê dữ liệu phụ thuộc có thể gây mất dữ liệu vĩnh viễn. Nhưng khi có sự cố xâm phạm nghiêm trọng, kéo dài khả năng sử dụng khóa cũ vì tiện vận hành cũng có thể làm tăng thiệt hại. Quy trình cần quy định thẩm quyền, ngưỡng xử lý khẩn cấp và phương án duy trì dịch vụ.

## 6. Quy trình key revocation trong hệ thống thực tế

Một quy trình tốt cần vừa **chặn sử dụng khóa không an toàn**, vừa duy trì khả năng truy cập dữ liệu hợp lệ theo mức rủi ro chấp nhận được.

~~~mermaid
flowchart TD
    A["Phát hiện rủi ro / yêu cầu thu hồi"] --> B["Xác minh danh tính khóa, mục đích và phạm vi ảnh hưởng"]
    B --> C{"Có nghi ngờ lộ khóa hoặc bị lạm dụng?"}
    C -->|Có| D["Cô lập quyền, chặn thao tác và thông báo khẩn"]
    C -->|Không| E["Lập kế hoạch chuyển phiên bản"]
    D --> F["Sinh hoặc kích hoạt khóa thay thế"]
    E --> F
    F --> G["Chuyển ứng dụng, dữ liệu, chứng chỉ và verifier"]
    G --> H["Kiểm tra bản cũ, cache, backup và các bên phụ thuộc"]
    H --> I{"Đã đáp ứng tiêu chí thu hồi?"}
    I -->|Chưa| G
    I -->|Rồi| J["Vô hiệu hóa / thu hồi chính thức"]
    J --> K["Kiểm toán và lên lịch lưu giữ hoặc hủy có kiểm soát"]
~~~

### Bước 1: Nhận diện chính xác khóa và tác động

Thu thập **key ID, key version, thuật toán, key usage, chủ sở hữu, tenant, ứng dụng**, môi trường và mối quan hệ khóa cha/con (KEK/DEK). Xác định khóa nằm trong HSM/KMS hay từng được export, nơi đang cache và nơi cần verifier kiểm tra tin cậy. Đừng chỉ dựa vào alias vì alias có thể trỏ sang phiên bản khác.

### Bước 2: Phân loại sự cố và quyết định cách cô lập

Nếu có dấu hiệu khóa bị lộ, ưu tiên ngăn kẻ xấu tiếp tục gọi API hoặc dùng danh tính đã chiếm quyền. Các biện pháp có thể bao gồm **disable phiên bản khóa**, thu hồi IAM, chặn principal, thu hồi chứng chỉ, tắt endpoint bị lạm dụng và vô hiệu hóa phiên truy cập. Ghi nhận nguy cơ làm gián đoạn đọc dữ liệu lịch sử khi khóa bị disable.

Trường hợp không khẩn cấp có thể duy trì một khoảng **overlap** có kiểm soát để ứng dụng chuyển đổi. Trường hợp khẩn cấp có thể phải chấp nhận giảm chức năng tạm thời vì an toàn.

### Bước 3: Tạo khóa thay thế và chuyển đường ghi mới

Sinh khóa bằng CSPRNG/HSM/KMS, xác nhận thuật toán và chính sách truy cập, thử nghiệm với nhóm giới hạn rồi chuyển các tác vụ **encrypt/sign/wrap** mới sang khóa mới. Đồng thời cập nhật chứng chỉ, trust store, JWKS hoặc cấu hình định tuyến theo hệ thống.

### Bước 4: Xử lý dữ liệu và hiện vật cũ

Tùy loại khóa:

- DEK lộ: tạo DEK mới và **giải mã rồi mã hóa lại** những bản ghi bị ảnh hưởng trong kênh được kiểm soát.
- KEK xoay định kỳ: có thể **rewrap DEK**; nếu KEK lộ, phải xét thêm các bản sao encrypted DEK/bản mã cũ mà đối phương đã thu thập.
- Khóa ký lộ: đổi cặp khóa, cập nhật verifier, xử lý token/chứng chỉ và quyết định cách tin các chữ ký lịch sử.
- Khóa mã hóa bất đối xứng lộ: ngừng dùng public key cũ, xem xét dữ liệu đã mã hóa cho nó và thay khóa.
- Phiên làm việc dùng khóa cũ: đánh giá có cần chấm dứt phiên, cấp lại token hoặc thiết lập lại kết nối.

Một hệ thống đang chuyển đổi cần biết rõ bản mã thuộc **phiên bản nào**, nếu không dễ rơi vào tình trạng khóa mới đã hoạt động nhưng dữ liệu cũ không thể giải mã.

### Bước 5: Đồng bộ trạng thái tới mọi nơi thực thi

Trạng thái thu hồi phải được thực thi bởi thành phần có quyền quyết định: KMS/HSM, IAM, ứng dụng xác minh chữ ký, CA, API gateway, thư viện PKI hoặc hệ thống token. Xem xét cache, instance chưa cập nhật, máy khách ngoại tuyến và bản phát hành phần mềm cũ.

### Bước 6: Xác minh và ghi bằng chứng

Xác nhận bằng kiểm thử có chủ đích:

- Yêu cầu **encrypt/sign/unwrap** mới với khóa bị thu hồi phải bị từ chối ở các điểm kiểm soát.
- Luồng dùng khóa thay thế hoạt động đúng và không làm mất dữ liệu.
- Verifier từ chối chữ ký/token mới mang khóa không còn tin cậy theo chính sách.
- Tình huống đọc dữ liệu lịch sử cho kết quả đúng với quyết định của tổ chức.
- Sự kiện **ai yêu cầu, ai phê duyệt, ai thực hiện, kết quả và thời điểm** được ghi vào nhật ký kiểm toán.

Sau khi đáp ứng tiêu chí chuyển đổi, khóa có thể được đánh dấu vô hiệu hóa/thu hồi; vật liệu khóa cũ được giữ hoặc hủy theo chính sách dữ liệu, tuân thủ và khả năng khôi phục.

## 7. Ví dụ: thu hồi KEK trong hệ thống envelope encryption

Giả sử ứng dụng Java lưu hồ sơ khách hàng bằng AES-256-GCM. Mỗi hồ sơ có **DEK** riêng. DEK được mã hóa dưới **KEK v1** do KMS quản lý.

~~~text
Trước khi thay khóa:

Hồ sơ X
  ├── ciphertext + nonce + authentication tag
  ├── encrypted DEK (wrapped bởi KEK v1)
  └── key reference = KEK v1

KMS
  └── KEK v1: ACTIVE
~~~

Nếu KEK v1 đến hạn rotation nhưng chưa lộ:

1. KMS tạo hoặc kích hoạt **KEK v2**.
2. Ứng dụng bắt đầu wrap DEK mới bằng KEK v2.
3. Từng hồ sơ được **rewrap encrypted DEK** từ v1 sang v2 theo quyền truy cập được kiểm soát.
4. Đọc lại hồ sơ được chuyển đổi bằng KEK v2 và kiểm tra AEAD tag/AAD; ghi trạng thái migration theo từng hồ sơ.
5. Khi không còn dữ liệu cần v1 và mọi bản sao lưu được xử lý phù hợp, vô hiệu hóa v1, sau đó xem xét hủy theo chính sách.

~~~text
Sau khi rewrap:

Hồ sơ X
  ├── ciphertext + nonce + authentication tag (không đổi)
  ├── encrypted DEK (wrapped bởi KEK v2)
  └── key reference = KEK v2

KMS
  ├── KEK v1: DISABLED / RETIRED
  └── KEK v2: ACTIVE
~~~

**Điều kiện an toàn:** Mô tả trên dành cho rotation thông thường. Nếu v1 đã bị đối phương lấy được cùng bản encrypted DEK cũ và bản mã, **chỉ rewrap không thể thu hồi khả năng giải mã từ bộ dữ liệu đối phương đã sao chép**. Cần điều tra phạm vi và có thể phải thay DEK, mã hóa lại các hồ sơ liên quan. Nếu dữ liệu đã bị lộ trước đó, mọi hành động sau sự cố chỉ ngăn rủi ro tương lai và giới hạn tác động thêm.

### Logic ứng dụng minh họa

Đoạn pseudocode theo phong cách Java sau đặt thao tác unwrap tại **KMS**. KMS chịu trách nhiệm xác thực, cấp quyền, kiểm tra trạng thái khóa và từ chối thao tác khi key version bị disable/revoke. Việc ứng dụng tự đọc một cờ trạng thái trong cơ sở dữ liệu không đủ để đảm bảo thu hồi.

~~~java
byte[] readEncryptedRecord(User user, EncryptedRecord record) {
    // Authorizer kiểm tra quyền đọc bản ghi theo user và tenant.
    authorizer.requireRead(user, record.tenantId(), record.recordId());

    // KMS tự xác thực danh tính workload, kiểm tra quyền và trạng thái KEK.
    // Nếu phiên bản khóa không còn được phép dùng, unwrap sẽ thất bại.
    byte[] dek = kms.unwrap(
        record.keyVersion(),
        record.encryptedDek(),
        record.encryptionContext()
    );

    try {
        return aesGcmDecrypt(
            dek,
            record.nonce(),
            record.ciphertextWithTag(),
            record.authenticatedMetadata()
        );
    } finally {
        Arrays.fill(dek, (byte) 0); // Giảm thời gian tồn tại byte[] chứa DEK.
    }
}
~~~

Đây là **pseudocode**: tên interface và method là giả định; API của từng KMS khác nhau. Xóa mảng byte là biện pháp giảm phơi lộ tốt nhất trong phạm vi kiểm soát của ứng dụng, không đảm bảo xóa mọi bản sao trong JVM/provider. Phải tránh log khóa và bản rõ, kiểm soát cache, dùng AAD/ngữ cảnh mã hóa đúng cách và xử lý ngoại lệ khi khóa bị thu hồi như một tình huống vận hành dự kiến.

## 8. Ví dụ: khóa ký bị thu hồi nhưng token vẫn được chấp nhận

Giả sử hệ thống có một gateway và ba dịch vụ xác minh JWT với public key tương ứng **K-sign-v1**:

~~~text
T0: Dịch vụ ký tạo JWT bằng private key v1.
T1: Private key v1 bị lộ; hệ thống phát hiện sự cố.
T2: Dịch vụ ký chuyển sang private key v2.
T3: Gateway cập nhật JWKS; Service A cũng đã cập nhật.
T4: Service B và Service C vẫn giữ cache public key v1.
T5: Kẻ tấn công tạo JWT mới bằng private key v1.
~~~

Nếu Service B/C vẫn chấp nhận khóa v1, JWT giả mạo **vẫn có thể được xác minh hợp lệ về chữ ký** tại hai dịch vụ đó. Vì vậy quy trình thu hồi khóa ký phải xử lý cả chính sách chấp nhận khóa, cache và token đã phát hành. Một số hệ thống phải tăng phiên bản phiên, chặn token theo danh tính và buộc người dùng xác thực lại.

Không được suy rằng xóa public key v1 khỏi endpoint JWKS lập tức loại v1 khỏi mọi cache. Cũng không được đồng nhất chữ ký hợp lệ với quyền truy cập hợp lệ: verifier cần kiểm tra thuật toán cho phép, issuer, audience, thời hạn, scope và các điều kiện ứng dụng.

## 9. Thiết kế chính sách và kiểm toán cho key revocation

Một tổ chức quản lý khóa tốt nên xác định trước **ai được thu hồi**, **điều kiện kích hoạt**, **tốc độ lan truyền**, **ảnh hưởng đến dữ liệu cũ** và **bằng chứng xác nhận**.

| Nội dung chính sách | Câu hỏi thiết kế |
|---|---|
| **Quyền thao tác** | Vai trò nào có thể disable/revoke key version, sửa policy, tạo khóa thay thế hoặc schedule deletion? |
| **Phân tách nhiệm vụ** | Có cần một người phê duyệt và một người thực hiện cho hành động hủy không? Có đường xử lý khẩn cấp được kiểm toán không? |
| **Phạm vi ảnh hưởng** | Ứng dụng, tenant, hồ sơ, chứng chỉ, token và backup nào dựa vào phiên bản khóa? |
| **RTO của thu hồi** | Hệ thống cần chặn sử dụng khóa bị lộ trong khoảng thời gian tối đa nào? |
| **Lan truyền trạng thái** | Cache, thiết bị ngoại tuyến, gateway và verifier cập nhật chính sách như thế nào? |
| **Lưu giữ khóa cũ** | Cần giải mã dữ liệu lịch sử bao lâu? Khi nào được hủy? |
| **Khôi phục** | Có phương án khôi phục dữ liệu hợp pháp mà không vô tình kích hoạt lại khóa bị xâm phạm không? |
| **Kiểm toán** | Lưu ai/yêu cầu nào/phê duyệt nào/thao tác nào/key ID/version nào/kết quả gì, nhưng tránh ghi vật liệu khóa hoặc bản rõ? |

Các sự kiện có giá trị kiểm toán gồm: phát hiện dấu hiệu lộ, yêu cầu thu hồi, phê duyệt, disable hoặc revoke, tạo và kích hoạt phiên bản mới, rewrap/re-encrypt, thay chứng chỉ, cập nhật verifier, kiểm thử phủ định, lịch hủy và xác nhận hoàn thành.

Không nên ghi **DEK dạng rõ, private key, access token còn hiệu lực hoặc nội dung dữ liệu nhạy cảm** vào bản ghi sự cố. Quyền đọc audit log cần được giới hạn tương xứng.

## 10. Các thất bại thường gặp và biện pháp phòng ngừa

| Lỗi thiết kế/vận hành | Hệ quả | Cách hạn chế |
|---|---|---|
| Chỉ đổi alias/kid rồi cho rằng khóa cũ đã bị thu hồi | Verifier hoặc ứng dụng vẫn dùng vật liệu khóa cũ | Thực thi từ chối tại KMS và mọi verifier, kiểm tra từ nhiều điểm |
| Tắt khóa KMS nhưng còn bản sao key material ngoài KMS | Người giữ bản sao vẫn tự giải mã/ký | Kiểm kê export, cache và backup; giảm số nơi được xuất khóa |
| Thu hồi nhầm KEK trước khi chuyển dữ liệu | Dữ liệu hợp lệ không thể giải mã | Phân loại sự cố, chuẩn bị kế hoạch migration và chế độ khẩn cấp |
| Chỉ rewrap DEK khi KEK bị lộ và dữ liệu cũ đã bị sao chép | Không khắc phục được khả năng giải mã bộ dữ liệu đã bị đánh cắp | Đánh giá phạm vi, thay DEK và mã hóa lại khi cần |
| Bỏ qua CRL/OCSP/trust store và cache | Client vẫn tin chứng chỉ đã bị thu hồi | Kiểm tra trạng thái thực tế, chính sách cache và khả năng lan truyền |
| Quên JWT, phiên đang hoạt động hoặc client ngoại tuyến | Token và kết nối không an toàn còn được chấp nhận | Chính sách invalidation, session renewal và kiểm soát độ trễ |
| Không biết hồ sơ thuộc key version nào | Không thể chuyển đổi/khôi phục chính xác | Lưu key ID/version và metadata cần thiết cùng bản mã |
| Không có runbook hay rehearsal | Ứng phó chậm, thao tác sai, gián đoạn dài | Diễn tập quy trình thu hồi, kiểm thử thất bại và rollback an toàn |
| Hủy khóa khi backup vẫn cần giải mã | Mất dữ liệu không thể phục hồi | Kiểm tra phụ thuộc và retention trước khi hủy |
| Xem chữ ký lịch sử hợp lệ là mặc nhiên đáng tin | Có thể chấp nhận hiện vật giả tạo sau khi khóa bị lộ | Áp dụng timestamp, bằng chứng và chính sách tin cậy theo thời điểm |

## 11. Tiêu chí kiểm thử để xác nhận thu hồi thành công

Revocation cần được kiểm thử ở **điểm thực thi thật**, không chỉ trong bảng metadata. Có thể dùng ma trận sau trong môi trường thử nghiệm:

| Kịch bản | Kết quả mong đợi |
|---|---|
| Gọi KMS decrypt/unwrap bằng phiên bản đang ACTIVE và đúng quyền | Được xử lý bình thường |
| Disable phiên bản khóa; tiếp tục gọi decrypt/unwrap qua KMS | KMS từ chối theo trạng thái và chính sách |
| Principal mất quyền KMS nhưng key version vẫn ACTIVE | Principal ấy bị từ chối; dịch vụ có quyền phù hợp vẫn hoạt động |
| Dịch vụ ký chuyển sang v2; verifier đã thu hồi v1 | Chữ ký/token mới dựa vào v1 bị từ chối theo chính sách |
| Verifier chưa cập nhật hoặc còn cache v1 | Phát hiện nguy cơ tiếp tục chấp nhận v1; kích hoạt cơ chế xử lý cache |
| Hồ sơ được rewrap dưới KEK v2 | Được đọc bằng đường v2; không âm thầm phụ thuộc v1 |
| Khóa cũ bị hủy sau migration | Không còn bản ghi/backup bắt buộc cần khóa ấy để khôi phục hợp pháp |
| Thao tác thu hồi bị người không có quyền gọi | Bị từ chối và ghi log kiểm toán thích hợp |

Kết quả kiểm thử cần ghi lại thời điểm, phiên bản, danh tính gọi, môi trường và lỗi từ chối. Một phép thử thành công trên một instance chưa chứng minh tất cả các instance, vùng triển khai hay client đã áp dụng trạng thái thu hồi.

## 12. Câu hỏi tự kiểm tra

**1. Nếu KEK bị disable trong KMS, người đã có bản sao KEK dạng rõ có bị mất khả năng giải bọc DEK không?**

**Trả lời:** Không. Việc disable chặn đường sử dụng đi qua KMS; không ngăn người đã có vật liệu khóa tự chạy thuật toán bên ngoài KMS.

**2. Rotation và revocation có thể xảy ra cùng lúc không?**

**Trả lời:** Có. Khi thu hồi khóa cũ do bị lộ, hệ thống thường tạo/kích hoạt khóa mới và chuyển phụ thuộc sang khóa mới. Nhưng rotation không tự thay thế thao tác thu hồi quyền tin cậy đối với khóa cũ.

**3. Tại sao thu hồi private key ký JWT không tự làm tất cả token cũ mất hiệu lực?**

**Trả lời:** Vì các verifier có thể tiếp tục chấp nhận public key cũ hoặc còn cache. Token có thể vẫn đạt điều kiện thời hạn và kiểm tra chữ ký. Cần cập nhật chính sách xác minh, cache và xử lý phiên/token theo mô hình hệ thống.

**4. Tại sao thu hồi chứng chỉ số không đồng nghĩa xóa private key?**

**Trả lời:** Certificate revocation là cơ chế thông báo/rút lại tin cậy. Nó không xóa một private key đã được sao chép; các client phải thực hiện kiểm tra và từ chối chứng chỉ theo chính sách.

**5. Khi nào cần re-encrypt thay vì chỉ rewrap?**

**Trả lời:** Thay DEK hoặc khi cần giảm khả năng khai thác dữ liệu từ DEK/KEK bị lộ có thể đòi hỏi mã hóa lại dữ liệu với DEK mới. Rewrap thông thường chỉ thay lớp bảo vệ DEK; không thay bản mã dữ liệu và không xóa những bản sao cũ đối phương đã lấy.

**6. Kiểm thử nào chứng minh được việc thu hồi tốt hơn chỉ nhìn thấy cờ trạng thái REVOKED?**

**Trả lời:** Kiểm thử yêu cầu mật mã thực tế bị từ chối tại KMS/verifier, xác nhận cache và các instance đã cập nhật, dữ liệu hợp lệ vẫn được xử lý đúng và các sự kiện có chứng cứ kiểm toán.

## 13. Ghi nhớ

**Key revocation** là quá trình rút lại **quyền sử dụng và sự tin cậy** đối với khóa trong phạm vi có thể kiểm soát. Một quy trình thu hồi an toàn phải trả lời được: **Khóa nào? Vì sao thu hồi? Ai thực thi? Bên nào còn tin hoặc giữ bản sao? Dữ liệu/chữ ký/token nào bị ảnh hưởng? Khi nào có thể vô hiệu hóa và hủy hoàn toàn?**

Vì thế, thu hồi khóa phải được thiết kế cùng **vòng đời khóa, IAM, KMS/HSM, certificate validation, rotation, envelope encryption, quản lý phiên bản, kiểm toán và khôi phục dữ liệu**. Điều quyết định hiệu quả không chỉ là thao tác đổi trạng thái, mà là kiểm chứng rằng những thành phần còn hoạt động đã ngừng sử dụng hoặc tin khóa không an toàn đúng theo chính sách.
