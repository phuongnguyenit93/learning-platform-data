# Key Management Practices Statement (KMPS)

> **Chương:** Nền tảng key management  
> **Phạm vi:** SECURITY_KEY_MANAGEMENT_FUNDAMENTALS — hiểu và quản trị toàn bộ vòng đời khóa mật mã, từ tạo, cấp phát, lưu trữ, sử dụng, xoay vòng đến thu hồi và hủy; kết nối mật mã đối xứng, bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, kiểm soát truy cập và kiểm toán.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **Key Management Practices Statement (KMPS)** là gì và vì sao một tổ chức cần tài liệu này khi vận hành hệ thống dùng khóa mật mã.
2. Phân biệt **Key Management Policy (KMP)**, **KMPS**, quy trình thao tác (SOP/runbook) và bằng chứng triển khai.
3. Xây dựng nội dung KMPS cho các loại khóa như khóa mã hóa dữ liệu (DEK), khóa bọc khóa (KEK), khóa ký số, khóa TLS và khóa gốc trong KMS/HSM.
4. Ánh xạ từng giai đoạn của vòng đời khóa tới biện pháp kiểm soát, người chịu trách nhiệm, nhật ký và cơ chế khôi phục.
5. Phát hiện những KMPS chỉ nói chung chung, thiếu khả năng kiểm chứng hoặc bỏ sót rủi ro thực tế.

## 2. KMPS là gì?

**Key Management Practices Statement** là bản mô tả có kiểm soát về **những thực hành mà một tổ chức thực sự áp dụng để quản lý khóa mật mã**. KMPS giải thích tổ chức triển khai các yêu cầu của chính sách quản lý khóa bằng hệ thống, quy trình và trách nhiệm cụ thể ra sao, trong phạm vi nào, với bằng chứng nào.

Chẳng hạn, câu “khóa mã hóa sản xuất phải được bảo vệ” chưa đủ để người vận hành biết phải làm gì và người kiểm toán biết kiểm tra điều gì. Một KMPS có thể làm rõ: khóa bọc dữ liệu được quản lý trong KMS; quyền dùng khóa gắn với danh tính workload; tài khoản quản trị không mặc nhiên có quyền giải mã dữ liệu; thao tác thay đổi chính sách phải qua phê duyệt; mọi lần gọi API nhạy cảm được ghi nhận trong hệ thống audit tập trung.

KMPS là **cam kết mô tả thực hành đang vận hành**, không phải một danh sách mong muốn. Nếu bản tuyên bố nói “phân tách nhiệm vụ” nhưng một tài khoản có thể tự phê duyệt, xuất khóa, xóa log và hủy khóa thì nội dung đó không phản ánh thực tế.

Trong kiến trúc key management, có thể xem bốn lớp tài liệu như sau:

| Lớp | Câu hỏi trả lời | Ví dụ |
| --- | --- | --- |
| **KMP — chính sách** | *Phải đáp ứng yêu cầu nào?* | Khóa sản xuất phải có chủ sở hữu, giới hạn mục đích sử dụng và được kiểm toán. |
| **KMPS — tuyên bố thực hành** | *Tổ chức thực hiện yêu cầu ấy bằng cách nào?* | KEK sản xuất được tạo trong KMS, chỉ workload có danh tính được cấp quyền sử dụng, thay đổi quyền có phê duyệt và lưu audit log. |
| **SOP/runbook — hướng dẫn thao tác** | *Người trực vận hành thực hiện từng bước gì?* | Các bước đề nghị tạo khóa, kiểm tra cấu hình, phê duyệt, kích hoạt, rollback và xử lý lỗi. |
| **Bằng chứng** | *Làm sao chứng minh những điều trên đang diễn ra?* | Cấu hình IAM/KMS, phiếu phê duyệt, log sự kiện, báo cáo kiểm tra và biên bản diễn tập khôi phục. |

Tài liệu chuyên về **Certificate Practice Statement (CPS)** của hệ thống PKI tập trung vào thực hành của tổ chức cung cấp chứng thư số, chẳng hạn CA. KMPS có phạm vi rộng hơn về quản lý **vật liệu khóa** trong hệ thống: khóa đối xứng, khóa bất đối xứng, khóa ký số, khóa bọc, khóa sao lưu và các thực hành liên quan. Một tổ chức có thể cần cả hai nếu đồng thời quản lý PKI và những hệ thống mã hóa khác.

### Vì sao KMPS cần thiết?

- **Nhất quán:** Các đội phát triển, an ninh, vận hành và kiểm toán cùng hiểu một cách xử lý khóa.
- **Truy xuất trách nhiệm:** Biết ai sở hữu khóa, ai phê duyệt, ai được phép sử dụng và ai có quyền thay đổi cấu hình.
- **Giảm rủi ro phụ thuộc cá nhân:** Quy trình không chỉ tồn tại trong trí nhớ của người thiết lập KMS.
- **Kiểm toán và cải tiến:** Có thể đối chiếu cam kết với cấu hình, nhật ký, kiểm thử và các ngoại lệ đã chấp thuận.
- **Ứng phó sự cố:** Khi nghi khóa bị lộ, tổ chức biết phải cô lập, thay khóa, mã hóa lại, giữ bằng chứng và phục hồi như thế nào.

## 3. Xác định phạm vi trước khi viết

Không có một cách quản lý phù hợp cho mọi loại khóa. Ví dụ, khóa TLS phục vụ xác thực kênh truyền khác DEK mã hóa dữ liệu lưu trữ, và khác khóa riêng dùng ký bản phát hành phần mềm. Vì vậy KMPS phải nói rõ **hệ thống, loại khóa, môi trường và ranh giới tin cậy** mà nó bao phủ.

Các thông tin tối thiểu cần xác định:

| Thuộc tính | Cần ghi rõ điều gì? | Hậu quả nếu bỏ trống |
| --- | --- | --- |
| Hệ thống/dữ liệu | Dịch vụ nào, phân loại dữ liệu nào, môi trường dev/staging/prod nào | Khóa thử nghiệm có thể bị dùng lẫn với sản xuất |
| Loại khóa và mục đích | DEK, KEK, ký số, TLS, khóa gốc; mã hóa, bọc khóa hay ký | Một khóa bị dùng chéo mục đích và mở rộng phạm vi thiệt hại |
| Chủ sở hữu | Đội, vai trò và đầu mối chịu trách nhiệm | Khóa “mồ côi”, không ai quyết định thay hoặc hủy |
| Nguồn tạo và nơi lưu | KMS, HSM, module mật mã phần mềm được chấp thuận; khu vực triển khai | Không biết ranh giới bảo vệ hay nơi có bản sao khóa |
| Hệ thống sử dụng | Danh tính dịch vụ, ứng dụng, tài khoản và quyền cần thiết | Quyền giải mã quá rộng |
| Vòng đời | Điều kiện tạo, kích hoạt, xoay vòng, vô hiệu, lưu giữ, hủy | Dữ liệu không giải mã được hoặc khóa lộ còn dùng được |
| Phụ thuộc | Bản sao lưu, dữ liệu cũ, dịch vụ khác, vùng khôi phục | Xóa khóa làm gián đoạn phục hồi dữ liệu |
| Bằng chứng | Log, chính sách truy cập, yêu cầu thay đổi, kết quả diễn tập | Không thể chứng minh việc tuân thủ |

Một **key inventory** (danh mục khóa) hữu ích nên có mã tham chiếu khóa, chủ sở hữu, loại/mục đích, phạm vi dữ liệu, hệ thống dùng, nơi quản lý, trạng thái, thời điểm tạo/kích hoạt, chính sách thời hạn sử dụng, lịch thay khóa, quy tắc lưu bản cũ, phụ thuộc khôi phục và liên kết tới tài liệu phê duyệt. Danh mục này lưu **metadata**, tuyệt đối không dùng làm nơi chứa khóa bí mật dạng rõ.

### Ví dụ về ranh giới tin cậy

Giả sử một ứng dụng đặt hàng mã hóa địa chỉ giao hàng trong cơ sở dữ liệu. Dữ liệu nằm ở DB, ứng dụng chạy trong cluster, KEK nằm trong dịch vụ KMS. KMPS phải chỉ rõ các ranh giới:

1. Workload được xác thực bằng danh tính riêng trước khi gọi KMS.
2. KMS quyết định có cho phép bọc/mở bọc DEK hay không.
3. DEK dạng rõ chỉ hiện diện trong bộ nhớ của thành phần được phép mã hóa/giải mã, trong khoảng thời gian cần thiết; không ghi log hay lưu vào DB.
4. DB chỉ lưu ciphertext, DEK đã bọc và metadata phiên bản/thuật toán cần thiết để giải mã.
5. Quản trị DB không mặc nhiên trở thành người có thể gọi KMS để giải mã.

Nếu người có quyền đọc toàn bộ DB **đồng thời** có quyền gọi KMS để giải mã tùy ý, KMPS phải nhận diện đường tấn công này và yêu cầu hạn chế quyền theo workload, dữ liệu, ngữ cảnh và môi trường.

## 4. Các phần cốt lõi của một KMPS

KMPS thường được tổ chức thành các phần sau. Tổ chức có thể thay đổi tên mục, nhưng các quyết định quan trọng cần **đủ cụ thể để kiểm chứng**.

| Phần | Nội dung cần nêu |
| --- | --- |
| Kiểm soát tài liệu | Mã tài liệu, phiên bản, chủ sở hữu, người duyệt, ngày hiệu lực, chu kỳ rà soát, quy trình thay đổi |
| Mục đích và phạm vi | Hệ thống, dữ liệu, môi trường, loại khóa, đối tượng áp dụng và ngoại lệ |
| Căn cứ chính sách | Yêu cầu nội bộ, yêu cầu pháp lý/hợp đồng liên quan, chuẩn tham chiếu phù hợp |
| Quản trị và phân quyền | Vai trò tạo, dùng, quản trị, phê duyệt, kiểm toán; phân tách nhiệm vụ, quyền khẩn cấp |
| Thiết kế mật mã | Mục đích khóa, thuật toán/bộ tham số được duyệt, giải pháp KMS/HSM, cách sử dụng khóa |
| Vòng đời khóa | Sinh khóa, cấp phát, kích hoạt, lưu trữ, dùng, sao lưu, khôi phục, xoay vòng, thu hồi và hủy |
| Bảo vệ và phân phối | Kiểm soát truy cập, kênh truyền, xuất/nhập khóa, bảo vệ plaintext key, vùng địa lý |
| Giám sát và xử lý sự cố | Log, cảnh báo, quy trình nghi lộ khóa, ứng phó mất khóa/KMS mất khả dụng |
| Bằng chứng và đánh giá | Chứng cứ tuân thủ, người thu thập, lưu giữ, kiểm thử định kỳ và xử lý sai lệch |
| Phê duyệt ngoại lệ | Lý do, đánh giá rủi ro, người chấp thuận, biện pháp bù trừ, hạn hết hiệu lực |

**Nguyên tắc viết:** Mỗi phát biểu quan trọng nên xác định được **đối tượng + hành động + điều kiện/quyền hạn + điểm thực thi + bằng chứng**.

Ví dụ:

- Mơ hồ: “Tất cả khóa quan trọng đều được bảo vệ tốt”.
- Có thể kiểm chứng: “KEK dùng cho dữ liệu khách hàng ở môi trường prod được tạo và giữ trong dịch vụ KMS được phê duyệt; quyền giải mã chỉ cấp cho danh tính dịch vụ đã đăng ký; mọi thay đổi quyền cần phiếu thay đổi được phê duyệt; sự kiện dùng khóa và thay đổi chính sách được gửi đến hệ thống audit”.

KMPS **không nên** đưa toàn bộ giá trị cấu hình bí mật, đường dẫn credential, seed, secret, token, hoặc vật liệu khóa vào tài liệu. Chỉ cần tham chiếu mã tài nguyên và vị trí lưu bằng chứng an toàn.

## 5. Phân định vai trò và trách nhiệm

Thiết kế quyền quản lý khóa phải dựa trên **least privilege** và **separation of duties**. Trong một hệ thống thực tế, vai trò có thể gộp hoặc tách tùy quy mô và mức rủi ro, nhưng KMPS phải nêu rõ lựa chọn và biện pháp kiểm soát.

| Vai trò | Trách nhiệm điển hình | Giới hạn cần xác định |
| --- | --- | --- |
| **Data/System Owner** | Phân loại dữ liệu, phê duyệt nhu cầu dùng khóa, quyết định thời gian lưu dữ liệu | Không có quyền trực tiếp đọc khóa chỉ vì là chủ hệ thống |
| **Key Custodian / KMS Administrator** | Cấp phát, cấu hình, thay đổi trạng thái khóa theo quy trình | Không tự động có quyền giải mã dữ liệu nghiệp vụ |
| **Security/Approver** | Phê duyệt kiểm soát, ngoại lệ, thay khóa rủi ro cao, xử lý sự cố | Không tự ý bỏ qua dấu vết kiểm toán |
| **Application/Workload Identity** | Gọi thao tác mã hóa, giải mã, ký/xác minh đúng mục đích | Không được sửa policy, xuất khóa hoặc xóa khóa |
| **Auditor/Monitor** | Đọc bằng chứng, kiểm tra thay đổi và phát hiện bất thường | Quyền đọc log/cấu hình không đồng nghĩa quyền dùng khóa |
| **Incident Responder** | Cô lập danh tính, vô hiệu khóa, phối hợp thay khóa và phục hồi | Quyền khẩn cấp cần giới hạn thời gian và được hậu kiểm |

Với khóa gốc, khóa bảo vệ số lượng lớn dữ liệu hoặc khóa ký có giá trị cao, có thể bổ sung **dual control** (hai người cùng tham gia/phê duyệt) và **split knowledge** (không một cá nhân nắm toàn bộ bí mật, khi kiến trúc yêu cầu). Hai cơ chế này khác nhau: hai người phê duyệt thao tác chưa chắc làm cho vật liệu khóa được chia thành các phần.

Quyền khẩn cấp (**break-glass**) phải có điều kiện kích hoạt, thời gian hiệu lực, ghi log độc lập, thông báo và xem xét sau sự kiện. Không thể coi tài khoản quản trị toàn quyền không giám sát là một quy trình khẩn cấp an toàn.

## 6. Tuyên bố thực hành theo vòng đời khóa

Một KMPS tốt không dừng ở câu “có cơ chế xoay vòng khóa”; tài liệu phải mô tả những hành động và bằng chứng ở **từng giai đoạn**.

| Giai đoạn | Thực hành cần mô tả | Bằng chứng có thể kiểm tra |
| --- | --- | --- |
| **1. Yêu cầu/tạo lập** | Phê duyệt mục đích khóa, phân loại, loại khóa; tạo bằng bộ sinh số ngẫu nhiên mật mã phù hợp hoặc trong hệ thống được chấp thuận | Yêu cầu cấp khóa, cấu hình thuật toán, sự kiện tạo khóa |
| **2. Đăng ký/cấp phát** | Gắn mã khóa, owner, môi trường, purpose, policy và quyền sử dụng | Key inventory, cấu hình IAM/KMS, ticket |
| **3. Phân phối/kích hoạt** | Giao quyền cho đúng workload; nếu chuyển vật liệu khóa thì dùng kênh/cơ chế bảo vệ được phê duyệt | Log cấp quyền, kiểm tra quyền, biên bản chuyển giao |
| **4. Lưu trữ** | Bảo vệ khóa tại nơi lưu; kiểm soát xuất khóa, bản sao, vùng dự phòng; quản lý khóa gốc/KEK | KMS/HSM policy, cấu hình sao lưu và hạn chế xuất |
| **5. Sử dụng** | Chỉ cho phép thao tác đúng mục đích; kiểm tra danh tính và ngữ cảnh; hạn chế hiện diện khóa dạng rõ | Log API KMS, kiểm tra quyền workload, kết quả kiểm thử |
| **6. Thay/xoay vòng** | Điều kiện thay theo chính sách, rủi ro hoặc sự cố; chuyển dữ liệu/ứng dụng sang khóa mới; kế hoạch rollback | Kế hoạch thay khóa, log phiên bản khóa, kết quả kiểm tra dữ liệu |
| **7. Tạm ngừng/thu hồi** | Khóa bị nghi lộ hoặc không còn được dùng phải ngăn sử dụng mới; đánh giá tác động tới dữ liệu cũ | Sự kiện disable/revoke, phiếu xử lý, log truy cập bị chặn |
| **8. Lưu giữ/khôi phục** | Xác định khóa cũ nào còn cần để đọc dữ liệu hoặc xác minh chữ ký; bảo vệ bản lưu và thử khôi phục | Kiểm thử restore, danh mục bản phụ thuộc, nhật ký truy cập |
| **9. Hủy** | Phê duyệt, kiểm tra phụ thuộc, hủy mọi bản còn liên quan theo khả năng kỹ thuật và quy định lưu giữ | Hồ sơ phê duyệt, log/sự kiện hủy, biên bản xác nhận |

### 6.1. Sinh khóa và lựa chọn thuật toán

KMPS phải yêu cầu khóa được sinh từ nguồn ngẫu nhiên có chất lượng mật mã phù hợp, thông qua thư viện hoặc mô-đun được tổ chức phê duyệt. **Không** lấy timestamp, ID tăng dần, mật khẩu người dùng hay hàm random thông thường làm khóa.

Với mỗi loại khóa, nêu rõ họ thuật toán, tham số/bậc an toàn được phép, mục đích sử dụng và cách thay đổi khi thuật toán không còn phù hợp. Chẳng hạn:

- **Khóa đối xứng:** mã hóa dữ liệu bằng thuật toán và chế độ mã hóa có xác thực (ví dụ AES-GCM với quản lý nonce đúng quy tắc); tránh tái sử dụng nonce dưới cùng một khóa nếu cấu hình yêu cầu nonce duy nhất.
- **Khóa bất đối xứng:** phân biệt cặp khóa để ký/xác minh với cặp khóa để trao đổi hoặc bao gói khóa; hạn chế dùng lại một cặp khóa cho nhiều mục đích.
- **Khóa ký số:** bảo vệ khóa riêng ở ranh giới tin cậy phù hợp; khóa công khai và metadata chứng thư có thể cần được lưu để xác minh chữ ký cũ.
- **TLS:** mô tả nguồn quản lý khóa riêng của máy chủ, chứng thư, cơ chế gia hạn và quyền truy cập; không đồng nhất việc gia hạn chứng thư với việc thay khóa cho dữ liệu lưu trữ.

Chọn độ dài khóa và thuật toán theo mô hình đe dọa, chính sách và yêu cầu pháp lý áp dụng. KMPS có thể viện dẫn bộ tiêu chuẩn của tổ chức (ví dụ các hướng dẫn NIST SP 800-57) nhưng vẫn phải chỉ rõ **cấu hình thực tế** và cách kiểm soát thay đổi của hệ thống.

### 6.2. Quản lý lưu trữ, truy cập và xuất khóa

**KMS** cung cấp các chức năng quản lý vòng đời khóa và chính sách sử dụng. **HSM** là thiết bị/mô-đun chuyên dụng bảo vệ thao tác mật mã và vật liệu khóa dưới một ranh giới bảo mật xác định. Một dịch vụ KMS có thể được hậu thuẫn bằng HSM; điều đó không mặc định có nghĩa mọi khóa và mọi thao tác của hệ thống đều ở bên trong HSM.

KMPS cần nêu:

1. Loại khóa nào được tạo và giữ bên trong KMS/HSM, loại nào được nhập từ bên ngoài; ai có quyền yêu cầu thao tác.
2. Vật liệu khóa có được phép xuất hay không, dưới điều kiện nào, bằng phương thức bảo vệ nào; ai xác nhận và lưu bằng chứng.
3. Phân biệt quyền **quản trị tài nguyên khóa**, **sử dụng khóa** và **đọc dữ liệu đã mã hóa**.
4. Cách xác thực workload (ví dụ workload identity và thông tin xác thực ngắn hạn), hạn chế theo môi trường, dự án, vùng hoặc ngữ cảnh mã hóa.
5. Cách thu hồi quyền khi nhân sự rời vị trí, workload bị xâm nhập hoặc quan hệ tin cậy hết hạn.

Đối với khóa không xuất được, một API “decrypt” được cấp quá rộng vẫn có thể trở thành **oracle giải mã**: kẻ tấn công không cần lấy được byte của KEK, chỉ cần lạm dụng quyền gọi dịch vụ. Vì vậy yêu cầu “non-exportable” không thay thế kiểm soát truy cập và giám sát.

### 6.3. Envelope encryption: DEK và KEK

**Envelope encryption** chia trách nhiệm:

- **DEK (Data Encryption Key):** trực tiếp mã hóa dữ liệu.
- **KEK (Key Encryption Key):** bọc/bảo vệ DEK; thường được quản lý bằng KMS/HSM.
- **Wrapped DEK:** DEK đã được mã hóa/bọc bằng KEK; có thể lưu cạnh ciphertext nếu kiểm soát truy cập và metadata phù hợp.

~~~mermaid
flowchart TD
    A[Ứng dụng có danh tính được cấp quyền] -->|Yêu cầu DEK hoặc giải bọc DEK| B[KMS/HSM quản lý KEK]
    B -->|Kiểm tra policy và thực hiện thao tác khóa| A
    A -->|Dùng DEK trong bộ nhớ để mã hóa| C[Ciphertext]
    A -->|Lưu DEK đã bọc| D[Wrapped DEK]
    C --> E[(Kho lưu dữ liệu)]
    D --> E
    E -->|Đọc ciphertext và wrapped DEK| A
~~~

Ở một số mô hình, API tạo DEK trả về cả DEK dạng rõ và wrapped DEK cho ứng dụng; ở mô hình khác thao tác được thực hiện trong mô-đun tin cậy. KMPS phải mô tả **mô hình thực sự dùng**, cách giới hạn thời gian lưu DEK dạng rõ trong bộ nhớ và cách ngăn lộ qua log, crash dump, telemetry hoặc cache.

Ba khái niệm thường bị nhầm:

| Thao tác | Điều gì thay đổi? | Có tự khắc phục mọi rủi ro lộ khóa không? |
| --- | --- | --- |
| **Xoay KEK** | Tạo/chọn phiên bản KEK mới cho các thao tác bọc khóa tiếp theo | Không. Ciphertext cũ và wrapped DEK cũ vẫn có thể phụ thuộc KEK cũ. |
| **Rewrap DEK** | Mở bọc rồi bọc lại **cùng DEK** dưới KEK mới, theo quy trình an toàn | Không. Nếu chính DEK đã lộ thì dữ liệu mã hóa bằng DEK ấy vẫn có rủi ro. |
| **Đổi DEK và mã hóa lại dữ liệu** | Sinh DEK mới, giải mã/mã hóa lại dữ liệu hoặc thay cơ chế lưu trữ tương đương | Giảm phụ thuộc DEK cũ, nhưng còn phải xử lý bản sao dữ liệu, backup, quyền truy cập và bằng chứng sự cố. |

KMPS phải chỉ rõ khi xoay KEK thì dữ liệu cũ được đọc như thế nào, có rewrap hay không, thời hạn loại bỏ phiên bản cũ là bao lâu và cách xác minh khả năng khôi phục. Không được mô tả xoay KEK như một bảo đảm rằng toàn bộ dữ liệu đã được mã hóa lại.

### 6.4. Cryptoperiod, xoay vòng và thay khóa do sự cố

**Cryptoperiod** là khoảng thời gian khóa được cho phép dùng cho một hay nhiều chức năng mật mã cụ thể. Thời gian **dùng để mã hóa/ký mới** có thể khác thời gian cần **giữ khóa để giải mã/xác minh dữ liệu cũ**.

KMPS nên xác định:

- Căn cứ chọn thời hạn: mức nhạy cảm dữ liệu, khối lượng sử dụng, thuật toán, mức độ lộ diện, yêu cầu lưu giữ và khả năng vận hành.
- Sự kiện kích hoạt thay sớm: nghi xâm nhập workload, thay đổi nhân sự có đặc quyền, lộ secret, cấu hình sai, phát hiện thuật toán không còn phù hợp, thay hệ thống quản lý khóa.
- Phương thức thay: tạo key/version mới, cấp quyền, chuyển traffic, mã hóa lại/rewrap (nếu cần), xác minh tương thích, ngừng dùng khóa cũ, thu hồi quyền.
- Quy tắc khóa cũ: chỉ cho phép giải mã dữ liệu lịch sử nếu còn cần, lưu ở trạng thái hạn chế, không tiếp tục mã hóa dữ liệu mới.
- Cơ chế phát hiện khóa quá hạn và ghi nhận ngoại lệ có thời hạn.

**Không có một chu kỳ xoay vòng cố định phù hợp mọi loại khóa.** Ví dụ “thay KEK mỗi 180 ngày” có thể là một quyết định trong KMPS của *một hệ thống minh họa*, không phải chuẩn bắt buộc cho mọi hệ thống. Xoay khóa quá thường xuyên nhưng thiếu kế hoạch kiểm thử và khôi phục cũng có thể gây mất dữ liệu.

### 6.5. Sao lưu, khôi phục, lưu trữ dài hạn và hủy

Khả năng **giữ bí mật khóa** và **khả năng khôi phục khóa khi xảy ra sự cố** đều quan trọng. Phải đánh giá rủi ro thất lạc khóa: dữ liệu vẫn còn trên đĩa nhưng có thể không bao giờ giải mã được.

KMPS cần mô tả các trường hợp phục hồi (mất vùng hạ tầng, xóa nhầm, lỗi policy, bị khóa tài khoản, KMS/HSM không khả dụng), phương án bảo vệ bản sao, người phê duyệt phục hồi, các bước diễn tập và cách xác minh dữ liệu mẫu sau khôi phục. Một số khóa HSM/KMS **không cho phép xuất vật liệu**; khi đó kế hoạch khả dụng có thể dựa vào khả năng dự phòng, nhân bản hoặc phương thức khôi phục mà nhà cung cấp hỗ trợ, thay vì sao lưu byte khóa ra ngoài.

Đối với khóa ký số, giữ được thông tin để **xác minh chữ ký cũ** khác với việc tiếp tục cho phép **tạo chữ ký mới**. Khóa ký riêng đã thu hồi không nên tiếp tục ký; việc xác minh lịch sử có thể cần khóa công khai, chứng thư, bằng chứng trạng thái chứng thư và thời điểm ký.

Trước khi hủy khóa, phải kiểm tra dữ liệu gốc, dữ liệu trong backup, snapshot, bản sao chéo vùng, lịch sử phiên bản và nghĩa vụ lưu giữ. **Cryptographic erasure** chỉ có cơ sở khi dữ liệu thực sự phụ thuộc vào khóa đó và không còn bản sao khóa hữu dụng nào khác; nút “schedule deletion” của KMS không tự chứng minh rằng tất cả ciphertext, bản sao khóa và bộ nhớ đệm đã bị xử lý ngay.

### 6.6. Thu hồi: phải mô tả hệ quả kỹ thuật

**Disable/revoke** có thể ngăn sử dụng khóa trong tương lai theo chính sách của hệ thống quản lý khóa, nhưng không thu hồi dữ liệu đã bị giải mã hoặc các byte khóa đã bị sao chép trước đó.

Một KMPS rõ ràng phải phân biệt:

- **Khóa đối xứng/DEK lộ:** cần xác định phạm vi ciphertext bị ảnh hưởng, thay DEK và mã hóa lại phần dữ liệu cần bảo vệ.
- **KEK hoặc quyền giải bọc lộ:** khóa/thu hồi quyền truy cập, đánh giá lịch sử sử dụng và các DEK có khả năng bị giải bọc; thay KEK/rewrap và có thể thay cả DEK theo phân tích sự cố.
- **Khóa ký riêng lộ:** chặn ký mới, thu hồi chứng thư nếu có, phát hành khóa/chứng thư thay thế, điều tra chữ ký bất thường; không mặc định coi mọi chữ ký lịch sử là hợp lệ hay không hợp lệ khi chưa đánh giá.
- **Danh tính workload lộ:** thu hồi token/credential, sửa chính sách và khóa quyền; xem xét liệu kẻ tấn công đã gọi API KMS hợp lệ trong thời gian bị xâm nhập.

Những thao tác này phải có owner, mốc thời gian, cách giám sát và điều kiện xác nhận hoàn tất.

## 7. Kiểm toán, giám sát và xử lý ngoại lệ

Tài liệu KMPS nên quy định các sự kiện cần ghi nhận: tạo khóa, cấp/thu hồi quyền, thay chính sách, import/export nếu được phép, sử dụng encrypt/decrypt/sign/unwrap theo mức độ có thể quan sát, disable, lịch xóa, hủy, restore và truy cập break-glass.

Với mỗi lớp sự kiện, chỉ rõ **thời gian, danh tính gọi, tài nguyên khóa, hành động, kết quả, nguồn gọi và correlation ID** khi khả dụng. Nhật ký không được ghi vật liệu khóa dạng rõ, plaintext nhạy cảm hoặc thông tin xác thực. Log cần được bảo vệ trước sửa/xóa trái phép, có chính sách lưu giữ và cách truy vấn khi điều tra.

Các chỉ báo cần theo dõi có thể gồm:

- Workload dev bất ngờ gọi khóa prod hoặc yêu cầu giải mã từ vị trí bất thường.
- Danh tính chưa từng được cấp quyền gọi decrypt/unwrap nhiều lần, hoặc số lần lỗi tăng mạnh.
- Thay đổi policy cho phép nhóm quản trị rộng hơn sử dụng khóa.
- Yêu cầu xuất khóa, lên lịch xóa khóa hoặc thay trạng thái khóa ngoài khung thay đổi đã phê duyệt.
- Không có audit log trong khoảng thời gian mà hệ thống đáng lẽ phải phát sự kiện.

Không phải nhà cung cấp nào cũng cung cấp cùng loại log hoặc cùng độ chi tiết cho mọi API. KMPS phải phản ánh **khả năng giám sát thực tế**, xác định lỗ hổng quan sát và nêu biện pháp bù trừ, chẳng hạn audit ở lớp ứng dụng hoặc cơ chế đối soát.

### Sự cố: mô hình quyết định

~~~mermaid
flowchart TD
    A[Phát hiện nghi lộ khóa hoặc lạm dụng quyền] --> B[Phân loại khóa và xác định dữ liệu, hệ thống liên quan]
    B --> C[Chặn quyền truy cập hoặc vô hiệu khóa theo phương án ứng phó]
    C --> D[Giữ bằng chứng, phân tích thời gian và phạm vi tác động]
    D --> E{Chỉ lộ quyền dùng khóa hay có khả năng lộ vật liệu khóa/DEK?}
    E -->|Quyền dùng| F[Thu hồi danh tính, rà soát lịch sử gọi API]
    E -->|Có thể lộ khóa| G[Thay khóa, rewrap hoặc mã hóa lại theo phạm vi]
    F --> H[Kiểm tra phục hồi và giám sát tái diễn]
    G --> H
    H --> I[Cập nhật KMPS, chính sách, runbook và bằng chứng]
~~~

Trong xử lý sự cố, việc disable khóa có thể khiến dịch vụ ngừng giải mã dữ liệu hợp lệ. Vì vậy phải có phương án cô lập hợp lý, phân quyền quyết định và thử nghiệm khôi phục trước đó. Không vì ưu tiên tính sẵn sàng mà bỏ qua nguy cơ dữ liệu đã bị xâm phạm.

**Ngoại lệ KMPS** phải được quản lý rõ ràng: yêu cầu nào chưa đáp ứng, phạm vi, lý do kinh doanh, đánh giá rủi ro, biện pháp bù trừ, người chấp thuận, ngày hết hạn và người phụ trách đóng ngoại lệ. Ngoại lệ không thể biến một thực hành chưa triển khai thành cam kết đã đáp ứng.

## 8. Ví dụ: KMPS rút gọn cho ứng dụng đặt hàng

Đây là **ví dụ giả định dùng để học**, không phải quy định bắt buộc cho mọi hệ thống. Ứng dụng “OrderLab” lưu địa chỉ giao hàng được mã hóa trong cơ sở dữ liệu. Workload chạy trên hạ tầng đám mây và dùng KMS để bảo vệ KEK; dữ liệu được mã hóa bằng DEK.

### 8.1. Bản tuyên bố thực hành mẫu

| ID | Cam kết và cách triển khai cụ thể | Trách nhiệm | Bằng chứng |
| --- | --- | --- | --- |
| KM-01 | Mọi KEK ở prod có mã quản lý, owner, môi trường, mục đích và hệ thống sử dụng trong key inventory | Security + System Owner | Danh mục khóa đối chiếu tài nguyên KMS |
| KM-02 | KEK prod do KMS được phê duyệt quản lý; không xuất vật liệu KEK nếu hệ thống không cho phép và policy cấm yêu cầu xuất | KMS Administrator | Cấu hình key origin/policy và kết quả kiểm tra |
| KM-03 | Mỗi đối tượng dữ liệu được mã hóa bằng DEK theo thiết kế ứng dụng; DB chỉ giữ ciphertext, wrapped DEK và metadata cần thiết | Development Lead | Kiểm tra mô hình dữ liệu, test tích hợp |
| KM-04 | Chỉ danh tính dịch vụ OrderLab-prod được phép gọi unwrap/decrypt cho đúng phạm vi khóa; môi trường dev/staging dùng khóa tách biệt | Security + Platform | IAM/KMS policy, kiểm thử truy cập được phép/bị từ chối |
| KM-05 | Quyền thay chính sách khóa tách khỏi quyền nghiệp vụ giải mã; thay đổi quyền phải được phê duyệt và hậu kiểm | Security Approver | Phiếu thay đổi, log IAM/KMS |
| KM-06 | DEK dạng rõ chỉ dùng tạm trong bộ nhớ khi cần, không ghi vào DB, log, tracing hoặc cấu hình | Development Lead | Code review, kiểm thử log, scan rò rỉ secret |
| KM-07 | Xoay KEK theo thời hạn do chính sách nội bộ quyết định hoặc sớm hơn khi có sự cố; có kế hoạch chuyển đổi khóa cũ và kiểm thử giải mã | Key Owner + Platform | Lịch/phiếu thay, kết quả kiểm tra dữ liệu cũ |
| KM-08 | Khi nghi lộ DEK, đánh giá dữ liệu liên quan và thay DEK/mã hóa lại theo kế hoạch ứng phó; chỉ rewrap không đủ | Incident Commander | Hồ sơ sự cố, log migration, kiểm tra checksum/tính toàn vẹn |
| KM-09 | Có phương án đọc dữ liệu hợp lệ trong khôi phục thảm họa và diễn tập định kỳ trên dữ liệu thử nghiệm | SRE + Data Owner | Kết quả diễn tập, biên bản restore |
| KM-10 | Sự kiện dùng khóa và thay policy được gom vào audit tập trung; cảnh báo cho thay đổi có rủi ro và truy cập bất thường | SOC/Platform | Truy vấn log, mẫu cảnh báo, báo cáo kiểm tra |
| KM-11 | Chỉ yêu cầu hủy khóa sau khi xác nhận không còn dữ liệu/bản sao cần giải mã và đã qua phê duyệt | Data Owner + Security | Danh sách phụ thuộc và phiếu phê duyệt hủy |
| KM-12 | KMPS được rà soát khi thay kiến trúc, nhà cung cấp KMS, thuật toán hoặc sau sự cố, ngoài lịch định kỳ | Document Owner | Lịch sử phiên bản, biên bản rà soát |

Ví dụ có thể được mô tả thêm bằng cấu trúc rút gọn:

~~~yaml
document:
  id: KMPS-ORDERLAB-PROD
  version: 1.0
  owner: Security Engineering
  scope: "OrderLab production, dữ liệu địa chỉ giao hàng"
  approval: "Security Owner + Data Owner"
key_classes:
  - id: orderlab-dek
    purpose: "Mã hóa dữ liệu ứng dụng"
    storage: "Chỉ dùng dạng rõ trong bộ nhớ ứng dụng khi cần"
    persisted_form: "Wrapped DEK"
  - id: orderlab-kek
    purpose: "Bọc/mở bọc DEK"
    custody: "KMS được phê duyệt, theo policy riêng prod"
access:
  use_identity: "orderlab-prod workload identity"
  administrative_changes: "Phải có phê duyệt và audit"
lifecycle:
  key_rotation: "Theo chính sách và sự kiện rủi ro; có kiểm thử dữ liệu cũ"
  incident: "Thu hồi quyền, đánh giá lộ DEK, thay khóa/mã hóa lại khi cần"
  destruction: "Phê duyệt sau khi kiểm tra tất cả phụ thuộc khôi phục"
evidence:
  - "Key inventory và KMS policy"
  - "Audit log và hồ sơ thay đổi"
  - "Kết quả kiểm thử truy cập, xoay khóa, khôi phục"
~~~

Bản mẫu này đủ để nêu hướng triển khai nhưng **chưa phải bản KMPS được phê duyệt**. Khi áp dụng thật, cần điền giá trị cụ thể: hệ thống KMS, key IDs/tham chiếu, thuật toán/chế độ, lịch sử phiên bản, đầu mối phê duyệt, thời hạn lưu giữ bằng chứng, ngưỡng cảnh báo, thông số cryptoperiod, kết quả kiểm thử và liên kết runbook. Không để những cụm như “theo chính sách” trở thành chỗ trống vĩnh viễn.

### 8.2. Tình huống đánh giá mẫu

Sau khi triển khai, một quản trị viên đề xuất tự động thay KEK hằng tháng và kết luận “mọi dữ liệu cũ đã an toàn với khóa mới”. Kiểm tra cho thấy DB vẫn chứa wrapped DEK do KEK phiên bản cũ tạo ra.

Nhận định cần đưa vào đánh giá:

1. **Thay KEK mới chưa đủ kết luận dữ liệu cũ đã được bảo vệ bằng KEK mới.** Cần xác minh cách KMS lưu phiên bản, cách unwrap dữ liệu cũ và liệu đã rewrap hay chưa.
2. Nếu **DEK cũ đã lộ**, chỉ rewrap nó bằng KEK mới không làm mất khả năng giải mã của kẻ đã lấy được DEK. Có thể phải sinh DEK mới và mã hóa lại dữ liệu bị ảnh hưởng.
3. Trước khi ngừng hoặc hủy phiên bản KEK cũ, cần thử giải mã dữ liệu lịch sử, snapshot và backup theo phương án phục hồi.
4. KMPS phải ghi rõ người phê duyệt, điều kiện chuyển đổi, bằng chứng kiểm thử và tiêu chí hoàn tất, thay vì chỉ ghi “auto rotation = enabled”.

## 9. Kiểm chứng KMPS đã khớp thực tế hay chưa

Một phương pháp đánh giá đơn giản là lần lượt đi từ **cam kết → điểm thực thi → bằng chứng → kiểm thử**.

| Phát biểu trong KMPS | Cần đối chiếu | Cách phát hiện sai lệch |
| --- | --- | --- |
| “Chỉ workload prod được giải mã” | KMS/IAM policy, danh tính thực tế | Thử gọi bằng workload staging hoặc tài khoản vận hành |
| “Khóa không xuất được” | Thuộc tính khóa, API và quyền xuất/backup | Kiểm tra chính sách và cơ chế tạo/import khóa |
| “Có phân tách nhiệm vụ” | Ma trận vai trò, quyền thực tế, thay đổi IAM | Tìm một danh tính có thể vừa sửa policy vừa giải mã/che log |
| “Xoay khóa an toàn” | Các phiên bản khóa, dữ liệu cũ, backup, runbook | Diễn tập thay khóa và giải mã bộ dữ liệu trước/sau |
| “Có thể phục hồi” | Dự phòng, quyền khôi phục, kịch bản DR | Restore dữ liệu thử trong điều kiện hạn chế quyền |
| “Ghi đủ nhật ký” | Cấu hình audit, pipeline lưu log, quy tắc cảnh báo | Tạo sự kiện kiểm thử và tìm đủ trường dữ liệu |
| “Hủy khóa đúng quy định” | Phụ thuộc dữ liệu, retention, lịch xóa, phê duyệt | Xác nhận không còn đối tượng cần giải mã bằng khóa đó |

Một vòng rà soát thực tế gồm:

1. **Lấy mẫu khóa và workload:** chọn khóa có mức rủi ro cao, khóa mới, khóa sắp hết thời hạn và khóa đã ngừng hoạt động.
2. **So sánh tuyên bố với cấu hình hiện tại:** quyền, kiểu khóa, trạng thái, vùng lưu trữ, trạng thái log, cảnh báo.
3. **Kiểm thử tình huống âm:** người không có quyền không giải mã được; workload môi trường khác không dùng lẫn khóa; không thể sử dụng khóa đã vô hiệu theo thiết kế.
4. **Diễn tập có kiểm soát:** thay khóa, khôi phục từ backup và xử lý yêu cầu hủy; kiểm tra tác động đến dữ liệu còn tồn tại.
5. **Ghi nhận kết quả:** sai lệch, mức rủi ro, owner, hạn xử lý, ngoại lệ và phiên bản KMPS cần cập nhật.

Kiểm toán không nên chỉ kiểm tra có tệp KMPS hay không; yếu tố quan trọng là **độ chính xác của các tuyên bố so với triển khai**.

## 10. Những lỗi thường gặp khi soạn hoặc vận hành KMPS

| Lỗi | Vì sao nguy hiểm? | Cách sửa |
| --- | --- | --- |
| Sao chép nguyên một chính sách thành KMPS | Chỉ có yêu cầu, không mô tả cách triển khai | Bổ sung hệ thống thực thi, vai trò, điều kiện và bằng chứng |
| Ghi “toàn bộ khóa nằm trong HSM” khi ứng dụng xử lý DEK dạng rõ | Che khuất nơi khóa có thể bị lộ | Vẽ luồng dữ liệu, nói rõ ranh giới bảo vệ của từng khóa |
| Chỉ kiểm tra việc bật automatic rotation | Bỏ sót dữ liệu cũ, wrapped DEK, backup và khóa đã lộ | Quy định cách rewrap, re-encrypt và kiểm thử khôi phục |
| Cấp tài khoản quản trị cả quyền decrypt và sửa policy | Mất phân tách nhiệm vụ, tăng nguy cơ lạm dụng | Tách role, hạn chế điều kiện gọi và giám sát |
| Không xác định ai sở hữu khóa | Không ai chịu trách nhiệm thay, phục hồi và hủy | Dùng inventory gắn owner và vòng đời |
| Ghi plaintext key, token hoặc secret vào log/tài liệu | Biến bằng chứng thành nguồn rò rỉ | Chỉ lưu metadata và tham chiếu an toàn |
| Xóa khóa vì “không còn traffic” | Dữ liệu cũ, snapshot hoặc backup có thể mất khả năng giải mã | Kiểm tra toàn bộ phụ thuộc trước khi hủy |
| Không theo dõi ngoại lệ | Thực hành ngoài chính sách kéo dài vô thời hạn | Ghi rủi ro, thời hạn, biện pháp bù trừ và người chịu trách nhiệm |
| Cập nhật kiến trúc nhưng không cập nhật KMPS | Cam kết trở nên sai so với hệ thống thật | Đưa rà soát KMPS vào quy trình thay đổi kiến trúc |

## 11. Bài tập tự kiểm tra

**Tình huống A.** Tổ chức có KMP yêu cầu “không người nào có thể một mình xuất khóa gốc”. KMPS ghi “chúng tôi tuân thủ nguyên tắc hai người”, nhưng HSM vẫn cho tài khoản admin xuất vật liệu khóa qua một thao tác duy nhất. Có đạt yêu cầu không?

**Gợi ý:** Không. Phải xác định cơ chế thực thi dual control/split knowledge nếu áp dụng, kiểm tra quyền thật, quy trình phê duyệt và bằng chứng thao tác. Một câu khẳng định không thay thế kiểm soát kỹ thuật.

**Tình huống B.** Một dịch vụ bị lộ credential có quyền gọi API KMS để giải mã. KEK được đánh dấu non-exportable. Có thể kết luận dữ liệu an toàn không?

**Gợi ý:** Không. Kẻ tấn công có thể gọi API giải mã dù không xuất được KEK. Cần thu hồi credential, kiểm tra log và dữ liệu đã bị truy cập, rà soát quyền, đánh giá việc thay DEK/KEK và cập nhật KMPS.

**Tình huống C.** Sau khi vô hiệu hóa khóa ký riêng, hệ thống vẫn cần xác minh chữ ký của hồ sơ phát hành từ năm trước. Có phải khôi phục quyền ký mới không?

**Gợi ý:** Không. Phải tách quyền ký mới khỏi chức năng xác minh chữ ký lịch sử; lưu khóa công khai và bằng chứng liên quan theo chính sách xác minh.

**Tình huống D.** Team vận hành có log tạo và xóa khóa nhưng không có log gọi decrypt. KMPS ghi “ghi nhận mọi lần sử dụng khóa”. Kết quả đánh giá?

**Gợi ý:** Đây là sai lệch giữa tuyên bố và khả năng quan sát. Cần kiểm tra khả năng audit của KMS hiện tại; cập nhật cấu hình, bổ sung audit ở tầng ứng dụng nếu cần và sửa KMPS cho chính xác.

## 12. Ghi nhớ khi áp dụng

**KMPS biến chính sách quản lý khóa thành những tuyên bố triển khai có thể kiểm tra.** Một KMPS hữu ích phải trả lời được: **khóa nào**, **phục vụ mục đích gì**, **ai được thao tác**, **khóa ở đâu**, **được bảo vệ và thay đổi thế nào**, **nếu mất hoặc lộ khóa thì sao**, và **bằng chứng nào xác nhận mọi điều đó**.

Đặc biệt, hãy giữ ba nguyên tắc xuyên suốt:

1. **Bảo vệ khóa không chỉ là giữ kín byte khóa:** quyền gọi KMS, log, danh tính workload, backup và quy trình khẩn cấp cũng là một phần của ranh giới bảo mật.
2. **Các giai đoạn vòng đời gắn với nhau:** xoay KEK, rewrap DEK, thay DEK, thu hồi quyền, mã hóa lại và hủy khóa là các thao tác khác nhau với hệ quả khác nhau.
3. **Mọi tuyên bố cần kiểm chứng được:** KMPS phải phản ánh thực tế vận hành, được cập nhật khi hệ thống thay đổi, và có owner cùng bằng chứng đi kèm.

### Tài liệu tham chiếu để học sâu

- **NIST SP 800-57 Part 1:** hướng dẫn chung về quản lý khóa mật mã, loại khóa, cryptoperiod và vòng đời khóa.
- **NIST SP 800-57 Part 2:** thực hành quản lý khóa ở cấp tổ chức, bao gồm quan hệ giữa chính sách, tuyên bố thực hành và trách nhiệm quản trị.
- **NIST SP 800-130:** khung thiết kế hệ thống quản lý khóa mật mã, hữu ích khi xác định các chức năng và ranh giới hệ thống.
- **RFC 3647:** khung chính sách chứng thư và tuyên bố thực hành chứng thực trong PKI, hữu ích để phân biệt CPS với KMPS.

Các tài liệu tham chiếu cung cấp khung tư duy; nội dung KMPS áp dụng phải được đối chiếu với chính sách, yêu cầu tuân thủ và khả năng thực tế của hệ thống mà tổ chức quản lý.
