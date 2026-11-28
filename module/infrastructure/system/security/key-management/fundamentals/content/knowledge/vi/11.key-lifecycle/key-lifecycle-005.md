# Compromised state — Trạng thái khóa mật mã bị xâm phạm

## 1. Compromised state là gì?

**Compromised state** là trạng thái trong vòng đời khóa mật mã cho biết **khóa hoặc khả năng sử dụng khóa không còn đáp ứng giả định tin cậy ban đầu vì đã bị xâm phạm**. Tùy loại khóa và sự kiện, nguyên nhân có thể là **lộ vật liệu khóa bí mật**, bị thay thế/sửa đổi trái phép, hoặc kẻ tấn công **chiếm được quyền thực hiện phép toán mật mã bằng khóa** mà không cần xuất khóa ra ngoài.

Ví dụ, một khóa AES-256 dùng để mã hóa hồ sơ khách hàng bị ghi vào log và log đã bị người không có quyền sao chép. Khóa đó phải được coi là **compromised**: giữ nguyên khóa và tiếp tục mã hóa không còn đáp ứng mục tiêu bảo mật, dù AES-256 vẫn là thuật toán mạnh. Một trường hợp khác: private signing key nằm trong HSM ở chế độ không xuất khóa, nhưng tài khoản ứng dụng có quyền **Sign** bị chiếm. Kẻ tấn công có thể tạo chữ ký hợp lệ mà không đọc được private key; đây vẫn là một **sự cố lạm dụng khóa** cần xử lý, dù kết luận khóa vật lý đã bị trích xuất hay chưa có thể khác nhau.

Trong chương **Key lifecycle** của mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, compromised state là điểm quyết định trong vòng đời **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi và hủy**. Khi khóa bị xâm phạm, mục tiêu không chỉ là chuyển một cờ trạng thái: phải **ngừng hoặc hạn chế thao tác nguy hiểm, đánh giá các khóa/dữ liệu phụ thuộc, chuyển sang khóa đáng tin cậy mới, xử lý bản sao và kiểm toán sự cố**.

> **Quy tắc cốt lõi:** Một khóa bị lộ **không trở nên bí mật trở lại** chỉ vì đổi alias, vô hiệu hóa trong KMS hoặc xóa một bản sao. Trạng thái compromised phải gắn với **quyết định xử lý rủi ro** và lịch sử sự cố có thể truy vết.

## 2. Khi nào một khóa được xem là compromised?

Không phải mọi lỗi sử dụng khóa đều chứng minh vật liệu khóa đã bị lộ. Tuy nhiên, thiếu bằng chứng trích xuất **không đủ** để khẳng định hệ thống vẫn an toàn.

| Tình huống | Đánh giá ban đầu | Nguyên tắc phản ứng |
| --- | --- | --- |
| Raw DEK, MAC key hoặc private key xuất hiện trong kho dữ liệu/log bị truy cập trái phép | Có căn cứ **lộ vật liệu khóa** | Đánh dấu compromised theo quy trình, chặn sử dụng mới, xác định phạm vi ciphertext/chữ ký phụ thuộc |
| HSM báo hành vi sử dụng private signing key từ danh tính lạ | Có căn cứ **lạm dụng quyền sử dụng**; chưa chắc private key đã được xuất | Chặn danh tính và quyền, cô lập hành vi Sign, điều tra chữ ký đã phát hành |
| Một tài khoản quản trị KMS bị nghi chiếm nhưng chưa thấy lệnh sử dụng khóa | **Suspected compromise / under investigation** | Có thể tạm đình chỉ quyền nhạy cảm, giữ bằng chứng, kiểm tra log và phạm vi truy cập |
| DEK bị sinh từ nguồn ngẫu nhiên dự đoán được | Bí mật khóa có thể bị suy đoán, dù chưa thấy exfiltration | Đánh giá khả năng khôi phục khóa, thay khóa, re-encrypt dữ liệu phụ thuộc |
| Public verification key trong key registry bị thay bằng khóa của kẻ tấn công | **Xâm phạm tính xác thực/tin cậy của khóa công khai** | Khôi phục trust source, chặn chấp nhận chữ ký giả và kiểm tra các quyết định Verify |
| Chứng chỉ hết hạn theo kế hoạch, private key không có dấu hiệu bị lộ | **Expired**, không tự đồng nghĩa compromised | Không sử dụng ngoài chính sách; rotate hoặc renew theo quy trình |
| Khóa hết hạn sử dụng và được ngừng tạo bản mã mới bình thường | **Deactivated/retired**, không tự đồng nghĩa compromised | Giữ quyền đọc/xác minh lịch sử nếu được phép |

**Điểm phân biệt:** Trạng thái **compromised** có thể phản ánh mất bí mật, mất tính toàn vẹn hoặc mất kiểm soát quyền sử dụng. Phải ghi rõ **loại sự cố và mức độ tin cậy của bằng chứng**, vì hành động kỹ thuật và phạm vi ảnh hưởng khác nhau.

### 2.1. Confirmed, suspected và exposed

Ba nhãn hữu ích trong điều tra:

- **Suspected:** Có cảnh báo hoặc dấu hiệu đáng ngờ, cần bảo toàn bằng chứng và khoanh vùng. Có thể áp dụng biện pháp khẩn cấp dù chưa xác minh sự cố.
- **Confirmed compromise:** Có đủ căn cứ theo quy trình tổ chức để kết luận khóa/vật liệu khóa hoặc quyền sử dụng đã bị xâm phạm.
- **Exposure:** Khóa xuất hiện ở nơi không đúng chính sách (repository, log, crash dump, backup…). Exposure là dấu hiệu rủi ro lớn nhưng việc ai đã đọc được và trong khoảng thời gian nào có thể cần điều tra thêm.

Các tên này là **nhãn vận hành minh họa**, không phải tập trạng thái bắt buộc cho mọi KMS. Nên tách **trạng thái kỹ thuật** (ví dụ disabled) khỏi **kết luận an ninh** (compromised confirmed) để tránh đánh mất ngữ nghĩa trong điều tra.

## 3. Compromised khác deactivated, revoked và destroyed như thế nào?

Những từ này có liên hệ nhưng không thay thế nhau.

| Trạng thái / hành động | Ý nghĩa chính | Có khôi phục bí mật đã lộ không? |
| --- | --- | --- |
| **Active** | Khóa đang được phép sử dụng theo mục đích và chính sách | Không áp dụng |
| **Suspended / disabled** | Tạm hoặc chủ động chặn một số thao tác sử dụng | **Không**; chỉ hạn chế đường sử dụng hiện tại |
| **Deactivated / retired** | Ngừng dùng cho hoạt động mới theo kế hoạch; có thể cho phép thao tác lịch sử | **Không** |
| **Compromised** | Khóa hoặc khả năng sử dụng khóa đã mất một thuộc tính tin cậy cần thiết | **Không**; đây là kết luận sự cố |
| **Revoked** | Thu hồi hiệu lực tin cậy/ủy quyền, ví dụ chứng chỉ hoặc quyền dùng khóa | **Không**; giúp hệ thống ngừng tin hay dùng khóa |
| **Destroyed** | Hủy vật liệu khóa có thể sử dụng tại ranh giới được kiểm soát | **Không**, nếu đã có bản sao ngoài kiểm soát |

**Compromised là trạng thái an ninh; disable/revoke/destroy là những biện pháp hoặc trạng thái vận hành liên quan.** Một khóa có thể đồng thời được ghi nhận **compromised** và **disabled**, thậm chí vật liệu khóa trong KMS đã bị destroyed. Hệ thống không nên xóa hồ sơ sự cố khi khóa bị xóa.

### 3.1. Một máy trạng thái khái niệm

~~~mermaid
stateDiagram-v2
    [*] --> PRE_ACTIVE: Tạo và kiểm tra
    PRE_ACTIVE --> ACTIVE: Kích hoạt
    ACTIVE --> SUSPENDED: Nghi ngờ hoặc chính sách
    SUSPENDED --> ACTIVE: Điều tra kết luận an toàn, được phê duyệt
    ACTIVE --> DEACTIVATED: Rotate / nghỉ dùng bình thường
    SUSPENDED --> COMPROMISED: Xác nhận xâm phạm
    ACTIVE --> COMPROMISED: Phát hiện lộ hoặc lạm dụng
    DEACTIVATED --> COMPROMISED: Lộ bản sao khóa cũ
    ACTIVE --> DESTROYED: Hủy đúng quy trình
    DEACTIVATED --> DESTROYED: Hết phụ thuộc và retention
    COMPROMISED --> DESTROYED: Sau ứng phó, xử lý vật liệu còn lại
~~~

Sơ đồ chỉ minh họa; **không có một máy trạng thái duy nhất áp dụng cho mọi nhà cung cấp**. Khi khóa được đánh dấu compromised, nên xem đó là **trạng thái an ninh không tự quay về active**. Nếu điều tra cho thấy cảnh báo là false positive, phải lưu hồ sơ kết luận và phê duyệt theo chính sách; không âm thầm sửa lại lịch sử.

### 3.2. Chặn sử dụng mới khác xử lý dữ liệu cũ

Ví dụ một DEK bị compromised:

- **Encrypt mới:** Nên ngừng ngay việc tạo ciphertext mới bằng DEK đó.
- **Decrypt lịch sử:** Có thể phải chặn API thông thường; trong một số kịch bản khôi phục, quy trình kiểm soát đặc biệt có thể cần đọc dữ liệu cũ để mã hóa lại.
- **Rewrap:** Bọc lại chính DEK đã lộ bằng KEK mới **không khôi phục tính bí mật của DEK**; cần thay DEK và đánh giá re-encrypt.
- **Destroy:** Chỉ hủy khi đã giải quyết nhu cầu đọc/migration và pháp lý/retention, theo thủ tục được phê duyệt. Khẩn cấp an ninh và tính sẵn sàng có thể xung đột; phải ghi quyết định rõ.

## 4. Phạm vi ảnh hưởng phụ thuộc loại khóa

**Một sự cố compromised không có cùng hậu quả cho mọi loại khóa**. Phải lập bản đồ các quan hệ phụ thuộc trước khi quyết định xử lý.

| Loại khóa bị ảnh hưởng | Khả năng thiệt hại | Hành động ưu tiên |
| --- | --- | --- |
| **DEK (Data Encryption Key)** | Ciphertext được mã hóa bằng DEK có thể bị giải mã; với AEAD, nếu kẻ có khóa và quyền truy cập dữ liệu, có thể tạo bản mã/tag hợp lệ | Ngừng encrypt mới, tạo DEK mới, xác định và re-encrypt dữ liệu cần thiết |
| **KEK (Key Encryption Key)** | Kẻ có KEK cùng các wrapped DEK tương ứng có thể giải bọc khóa con | Kiểm kê wrapped DEK, thay KEK, đánh giá thay DEK và re-encrypt dữ liệu; không chỉ rewrap máy móc |
| **Root/master key bí mật** | Nhiều khóa con hoặc miền dữ liệu phụ thuộc có thể bị ảnh hưởng | Kích hoạt ứng phó cấp cao, đánh giá toàn bộ cây khóa và quyền quản trị |
| **Private signing key** | Có thể tạo chữ ký giả, chứng chỉ giả tùy quyền và mục đích | Ngừng Sign, thu hồi chứng chỉ/tin cậy thích hợp, điều tra chữ ký phát hành, phân phối khóa mới |
| **MAC/HMAC key** | Có thể tạo tag xác thực thông điệp giả | Ngừng chấp nhận/tạo tag dưới key cũ theo mức khẩn cấp, cấp phát key mới, rà soát giao dịch |
| **Root CA private key** | Có thể gây mất niềm tin trên toàn chuỗi chứng chỉ được phát hành/phụ thuộc | Quy trình khẩn cấp PKI, trust anchor, chứng chỉ con, client cập nhật và kiểm chứng lịch sử |
| **Private key xác thực TLS dài hạn** | Kẻ tấn công có thể mạo danh endpoint trong những điều kiện phù hợp | Thu hồi và thay cert/key, kiểm tra phiên lạm dụng; đánh giá FS của phiên cũ |
| **Ephemeral DH private / traffic key** | Có thể lộ một hoặc một số phiên thay vì toàn bộ tài sản dài hạn | Cô lập phiên, thiết lập lại với khóa mới, điều tra cache/log và dữ liệu phiên |
| **Pepper cho password hashing** | Nếu đối thủ còn có password hashes, họ có thể kiểm tra phỏng đoán theo công thức đầy đủ | Rotate pepper, xử lý rò hash và tài khoản, migrate/reset mật khẩu, không bỏ Argon2id/salt |

### 4.1. Quan hệ DEK–KEK–root key

Trong **envelope encryption**, DEK trực tiếp mã hóa dữ liệu. KEK bảo vệ DEK dạng đã bọc, và một root key có thể bảo vệ KEK ở tầng cao hơn.

~~~mermaid
flowchart TD
    R["Root key<br/>Điểm tin cậy cấp cao"] --> K1["KEK tenant A"]
    R --> K2["KEK tenant B"]
    K1 --> D1["Wrapped DEK A1"]
    K1 --> D2["Wrapped DEK A2"]
    K2 --> D3["Wrapped DEK B1"]
    D1 --> C1["Ciphertext hồ sơ A1"]
    D2 --> C2["Ciphertext hồ sơ A2"]
    D3 --> C3["Ciphertext hồ sơ B1"]
    INCIDENT["Sự cố root/KEK?"] -.->|"Đánh giá tất cả nhánh phụ thuộc"| R
~~~

**Sơ đồ chỉ là mô hình khái niệm**; KMS thực tế có thể không cho người dùng xem hoặc điều khiển root key nội bộ. Khi root hoặc KEK bị lộ, không mặc định kẻ tấn công đã lấy mọi DEK; phải xác minh **đối thủ có ciphertext, wrapped DEK, quyền Unwrap và những bản sao nào**. Nhưng cũng không được giảm nhẹ rủi ro chỉ vì chưa phát hiện truy xuất dữ liệu.

### 4.2. Compromise khóa ký số và chữ ký lịch sử

Khóa ký bị lộ cho phép **giả mạo chữ ký mới**; việc thu hồi khóa/chứng chỉ phải được truyền tới bên xác minh. Đối với chữ ký đã tạo trước thời điểm xâm phạm, không thể đơn giản kết luận **tất cả đều hợp lệ** hoặc **tất cả đều giả**. Cần xét thời gian ký đáng tin cậy, chứng chỉ/trust anchor, trạng thái thu hồi, bằng chứng thời gian và chính sách của ứng dụng.

Một public verification key không cần bí mật, nhưng nếu **key registry/truststore bị đánh tráo**, phần mềm Verify có thể chấp nhận chữ ký của kẻ tấn công dù private signing key thật không bị lộ. Trường hợp này cũng đòi hỏi xử lý **xâm phạm miền tin cậy**.

### 4.3. Forward secrecy có giới hạn

Khi private signing key dài hạn của server bị lộ, một phiên **TLS 1.3 dùng ephemeral (EC)DHE đúng cách** có thể có **forward secrecy**: chỉ có signing key bị lộ về sau không tự đủ để giải mã traffic cũ đã ghi lại. Nhưng nếu **traffic key/session secret** bị lộ, nếu endpoint đã bị chiếm khi phiên diễn ra, hoặc nếu giao thức không có FS trong cấu hình đó, ảnh hưởng có thể khác.

Do đó không dùng tuyên bố “TLS có FS” để bỏ qua điều tra. Cần xác định **giao thức, cấu hình, thời điểm và loại khóa bị xâm phạm**.

## 5. Dấu hiệu phát hiện và nguồn bằng chứng

Một số dấu hiệu điển hình:

1. **Secret scanning** tìm thấy khóa trong Git, artifact CI/CD, container image, file cấu hình, ticket hoặc log.
2. **KMS/HSM audit log** ghi thao tác Decrypt/Unwrap/Sign từ principal lạ, khung giờ bất thường hoặc tăng đột biến.
3. **IAM thay đổi:** Quyền sử dụng khóa được mở rộng, policy bị sửa, role được cấp quyền export/import hoặc xóa khóa bất thường.
4. **Endpoint/workload compromise:** Mã độc, credential theft, container bị chiếm, crash dump/bộ nhớ bị sao chép.
5. **Sự cố ciphertext/nonce:** GCM tái sử dụng nonce dưới cùng key hoặc dùng RNG yếu, gây mất thuộc tính bảo mật dù key bytes không được đọc.
6. **Chuỗi tin cậy bất thường:** Chứng chỉ không được phê duyệt, JWKS hoặc truststore bị sửa, signer ID đột ngột ánh xạ sang public key khác.
7. **Báo cáo từ bên ngoài:** Đối tác thông báo key bị lộ, chứng chỉ bị thu hồi, bản dump database hoặc secret xuất hiện trên hệ thống công khai.

### 5.1. Thu thập chứng cứ mà không làm lộ thêm khóa

Khi điều tra nên giữ:

- **Key ID, key version, loại khóa và mục đích** thay vì sao chép raw key.
- Chủ thể truy cập, quyền, thời gian, API đã gọi, môi trường/tenant và kết quả.
- Bằng chứng cấu hình, lịch sử thay đổi policy, liên hệ giữa KEK và DEK, các bản mã bị ảnh hưởng.
- Mốc phát hiện, mốc có thể đã bắt đầu bị lộ, quyết định ứng phó và người phê duyệt.

**Không dán private key/DEK vào ticket hoặc log để chứng minh sự cố.** Việc “lưu bằng chứng” phải có ranh giới bảo mật. Nếu cần một mẫu vật liệu khóa cho điều tra, quy trình phải quy định nơi cất, quyền, truy cập và xóa an toàn.

### 5.2. Không nhầm thiếu log với không có compromise

Nhiều hệ thống không log đầy đủ tất cả thao tác tại từng thời điểm. Việc không thấy sự kiện **Decrypt** trong log KMS không chứng minh kẻ tấn công không có raw DEK đã bị lấy qua Git, bộ nhớ, backup hoặc một hệ thống khác.

Khi phạm vi chưa xác định, ghi rõ **mức độ chắc chắn và những nguồn dữ liệu chưa kiểm tra**, rồi áp dụng biện pháp bảo vệ tạm thời theo rủi ro.

## 6. Quy trình ứng phó khi key vào compromised state

Một quy trình có thể gồm sáu nhóm hoạt động, với mức ưu tiên thay đổi theo loại khóa và quy mô sự cố.

### Bước 1 — Phát hiện, phân loại và mở sự cố

Định danh rõ **key ID/version, owner, thuật toán, miền tin cậy, mục đích, trạng thái hiện tại**. Ghi lại dấu hiệu suspected hay confirmed và **incident ID**. Xác định đây là lộ **vật liệu khóa**, **lạm dụng API**, **mất nguồn tin cậy của public key**, hay sự kết hợp.

Không chờ có đủ mọi bằng chứng nếu một hành động khẩn cấp như chặn Sign hoặc Unwrap có thể ngăn thiệt hại đang xảy ra.

### Bước 2 — Cô lập và ngăn sử dụng trái phép

- Thu hồi credential/session nghi bị chiếm và chặn principal không hợp lệ.
- Tạm dừng **Encrypt/Wrap/Sign/GenerateMac** bằng khóa có vấn đề nếu có rủi ro tiếp tục tạo tài sản không tin cậy.
- Đánh dấu trạng thái trong **key registry, KMS policy, secret manager hoặc ứng dụng** theo cơ chế thực tế.
- Nếu KMS hỗ trợ **disable** hoặc **suspend**, sử dụng có kiểm soát; không mặc định thao tác đó tự vô hiệu hóa các bản sao raw key đã phân phối.
- Bảo toàn audit và chứng cứ trước khi xóa bản sao hoặc thay đổi hệ thống có thể làm mất dấu vết.

**Fail closed** tại đường sử dụng bị nghi xâm phạm: không tự động chuyển sang khóa mặc định, bỏ kiểm tra chữ ký, bật plaintext hoặc dùng lại key cũ khi KMS/HSM không sẵn sàng.

### Bước 3 — Đánh giá phụ thuộc và phạm vi dữ liệu

Kiểm kê theo:

- **Khóa:** Root → KEK → wrapped DEK, hoặc signer → certificates → relying parties.
- **Dữ liệu:** Ciphertext, backup, snapshot, message đã ký, token đã phát hành, webhook, phiên TLS và dữ liệu lịch sử.
- **Quyền:** Workload, IAM role, service account, tenant, endpoint/API có thể thực thi phép toán bằng khóa.
- **Thời gian:** Khoảng từ mốc lộ sớm nhất có cơ sở đến lúc chặn sử dụng và triển khai khóa mới.
- **Bản sao:** File, cấu hình, bộ nhớ/cache, CI/CD artifact, hệ thống dự phòng, region, môi trường test và backup.

**Không chỉ đếm số khóa:** một khóa có thể bảo vệ hàng triệu bản ghi, còn một private signing key có thể xác thực cho nhiều dịch vụ.

### Bước 4 — Thay vật liệu khóa và chuyển phụ thuộc

Tạo khóa mới bằng **CSPRNG/KMS/HSM đáng tin cậy**, với key ID/version mới và quyền hạn tối thiểu. Kiểm thử đường sử dụng, cập nhật workload và thực hiện chuyển đổi theo loại khóa:

- **DEK bị lộ:** Sinh DEK mới, kiểm tra khả năng đọc dữ liệu cũ và **re-encrypt** các bản mã cần chuyển. Không giữ DEK cũ cho ghi mới.
- **KEK bị lộ:** Thay KEK, kiểm kê wrapped DEK từng phụ thuộc, đánh giá có cần **thay DEK** và re-encrypt hay không. Chỉ rewrap không đủ nếu kẻ tấn công đã biết DEK hoặc vẫn có ciphertext cũ và bản wrapped DEK cũ.
- **Root key bị lộ:** Lập kế hoạch di chuyển các nhánh phụ thuộc theo kiến trúc thực tế và chính sách của nhà cung cấp; có thể là sự cố tổ chức trên diện rộng.
- **Khóa ký bị lộ:** Tạo cặp khóa mới, phân phối public verification key tin cậy, thu hồi chứng chỉ/khóa theo cơ chế PKI/JWKS ứng dụng; xử lý token và chữ ký còn hiệu lực.
- **MAC key hoặc pepper bị lộ:** Cấp phát secret mới; với MAC, điều phối thời điểm chấp nhận key mới/cũ; với pepper, cần migration bằng mật khẩu khi login/reset vì password hash một chiều.

### Bước 5 — Xác minh an toàn và phục hồi

Kiểm thử:

1. Không tạo bản mã/chữ ký mới bằng khóa bị compromised.
2. Các bên nhận không còn tin khóa/kid/cert đã thu hồi ngoài chính sách lịch sử được phép.
3. Dữ liệu hợp lệ vẫn đọc được bằng **khóa phiên bản mới** hoặc qua đường migration đã phê duyệt.
4. Cache, bản sao, các region và pipeline triển khai không phát lại trạng thái hoặc vật liệu khóa cũ.
5. Audit, cảnh báo, backup và thử nghiệm phục hồi vẫn hoạt động mà không phải hạ mức xác thực.

### Bước 6 — Hoàn tất, hủy và cải tiến

Chỉ thực hiện **destruction** khi đã đánh giá lưu giữ dữ liệu, khôi phục và nghĩa vụ pháp lý. Ghi nhận **những bản sao đã hủy, bản sao không thể thu hồi, thời điểm hoàn tất, rủi ro tồn dư**, và khắc phục nguyên nhân gốc như logging secret, IAM quá rộng hoặc quản lý nonce sai.

Giữ **hồ sơ compromised state và incident ID** theo retention; không xóa lịch sử chỉ vì key material đã bị hủy.

~~~mermaid
flowchart TD
    ALERT["Cảnh báo lộ hoặc lạm dụng khóa"] --> TRIAGE["Phân loại suspected/confirmed<br/>Ghi incident ID và key ID"]
    TRIAGE --> CONTAIN["Cô lập quyền và thao tác nguy hiểm<br/>Bảo toàn bằng chứng"]
    CONTAIN --> SCOPE["Kiểm kê keys, dữ liệu, chữ ký,<br/>tenant, bản sao, thời gian"]
    SCOPE --> REPLACE["Tạo và kích hoạt khóa tin cậy mới"]
    REPLACE --> MIGRATE["Re-encrypt / rewrap / phân phối trust<br/>tùy loại khóa và phạm vi sự cố"]
    MIGRATE --> TEST{"Đã kiểm thử và hết phụ thuộc<br/>không được phép?"}
    TEST -->|"Chưa"| SCOPE
    TEST -->|"Đã đạt"| RETIRE["Thu hồi/hủy theo policy<br/>Giữ hồ sơ điều tra và audit"]
~~~

## 7. Compromised key và envelope encryption: rewrap hay re-encrypt?

Đây là quyết định dễ sai vì **thay khóa bọc** và **thay khóa mã hóa dữ liệu** là hai thao tác khác nhau.

| Sự kiện | Có thể làm gì? | Khi nào chưa đủ? |
| --- | --- | --- |
| KEK bình thường cần rotate định kỳ, không có sự cố lộ | Có thể **unwrap/rewrap DEK** bằng KEK mới trong ranh giới được bảo vệ, giữ nguyên ciphertext | Nếu chính sách yêu cầu thay DEK hoặc thay mode/thuật toán |
| KEK đã lộ nhưng dữ liệu con/wrapped DEK chưa chắc bị tiếp cận | Rotate KEK, đánh giá access logs, phạm vi bản wrapped DEK, backup và quyết định rủi ro | **Rewrap đơn thuần** không loại bỏ khả năng giải mã bản wrapped DEK cũ đã bị sao chép |
| DEK đã lộ dạng rõ | **Thay DEK và re-encrypt dữ liệu** liên quan là phương án để bảo vệ những bản mã mới | Chỉ rewrap chính DEK cũ không khôi phục bí mật; plaintext/ciphertext cũ đã sao chép vẫn có thể bị đọc |
| Root key lộ, bảo vệ nhiều KEK/DEK | Đánh giá **toàn cây**, chuyển các khóa con và quyền sử dụng theo kế hoạch nhiều giai đoạn | Chỉ đổi alias hoặc một KEK không đủ nếu có các nhánh khác phụ thuộc |
| Chỉ quyền **Decrypt/Unwrap** bị lạm dụng nhưng raw key không được xuất | Cô lập principal, giám sát và đánh giá nội dung đã trả về, thay khóa theo rủi ro | Thu hồi IAM không thu hồi được plaintext đã bị đọc hoặc bản sao DEK được trả từ API |

**Không tự động kết luận rewrap hay re-encrypt luôn đủ:** quyết định phụ thuộc kẻ tấn công đã có những gì, có bao nhiêu phiên bản ciphertext/wrapped key còn tồn tại và dữ liệu cần giữ bí mật bao lâu.

### 7.1. Ciphertext cũ vẫn là một tài sản cần bảo vệ

Giả sử kẻ tấn công đã tải bản sao ciphertext và DEK v1. Ngày hôm sau hệ thống re-encrypt toàn bộ database sang DEK v2. Dữ liệu **trong database hiện tại** có thể được bảo vệ bởi v2, nhưng kẻ tấn công vẫn có thể giải mã **bản sao v1 đã lấy**. Việc thay khóa **không thể đảo ngược rò rỉ quá khứ**.

Vì vậy, incident response cần xác định **mức độ lộ dữ liệu**, nghĩa vụ thông báo và các hành động bảo vệ tài khoản/khách hàng liên quan chứ không chỉ kiểm tra rằng khóa mới hoạt động.

### 7.2. Xoay vòng key alias không phải thay vật liệu khóa

Một **alias** trong KMS có thể trỏ tới key ID hoặc version khác, nhưng thay alias không có nghĩa tất cả ciphertext cũ tự mã hóa lại. Ngược lại, một số dịch vụ KMS có **automatic rotation** nội bộ mà ứng dụng vẫn thấy một key ID logic. Hành vi cụ thể phải được xác minh trên **dịch vụ/KMS đang sử dụng**, không suy đoán từ tên API.

Lưu **key ID/version và metadata thuật toán** với dữ liệu là yêu cầu quan trọng để xác định các bản mã cần di chuyển sau sự cố.

## 8. Khóa ký số, chứng chỉ và thu hồi tin cậy

Một private signing key bị compromised có thể tạo chữ ký hợp lệ cho thông điệp giả. Với **Root CA** hoặc Intermediate CA, tác động có thể lan tới các chứng chỉ và dịch vụ tin tưởng chuỗi CA đó.

### 8.1. Các lớp xử lý khác nhau

1. **Khóa ký riêng:** Chặn **Sign**, thu hồi quyền workload, điều tra thao tác ký trái phép và thay vật liệu khóa.
2. **Chứng chỉ X.509:** Thực hiện thủ tục thu hồi (ví dụ CRL/OCSP) và phát hành lại chứng chỉ theo PKI/chính sách. Việc đánh dấu key disabled trong KMS **không tự cập nhật** trạng thái tin cậy tại client.
3. **JWT/JWKS:** Phân phối public verification key mới qua issuer đáng tin cậy, ngừng chấp nhận kid cũ khi cần, kiểm soát cache và chính sách token đã phát hành. Xóa một key khỏi JWKS có thể làm hỏng việc xác minh token cũ nhưng không luôn thu hồi ngay mọi cache.
4. **Trust anchor:** Khi root of trust bị xâm phạm, cần phương án cập nhật truststore/client, có thể cần chuyển nhiều chứng chỉ và kiểm soát các thiết bị không cập nhật được.
5. **Chữ ký lịch sử:** Lưu chứng cứ thời gian, chứng chỉ và sự kiện thu hồi theo chính sách trước khi quyết định việc chấp nhận một chữ ký quá khứ.

### 8.2. Chữ ký đúng về toán học không phải quyết định cuối

**Verify(signature, publicKey) = true** cho biết phép kiểm tra mật mã hợp lệ đối với byte đã ký và public key đầu vào. Nếu private key đã bị lộ, kẻ tấn công có thể tạo chữ ký tương tự. Vì vậy, bên Verify phải xét thêm **định danh signer, purpose, hiệu lực, trạng thái compromised/revoked, mốc thời gian và quyền nghiệp vụ**.

Đối với chữ ký có giá trị lâu dài, không quyết định bằng một điều kiện máy móc như “chứng chỉ đang revoked nên mọi chữ ký quá khứ đều giả”. Cần một chính sách rõ cho **thời điểm ký, thời điểm khóa bị xâm phạm và bằng chứng thời gian đáng tin cậy**.

## 9. KMS/HSM: chặn lạm dụng nhưng không bảo đảm khóa chưa bị compromise

**KMS (Key Management Service)** và **HSM (Hardware Security Module)** có thể tạo, lưu và sử dụng khóa trong ranh giới bảo vệ. Chúng hỗ trợ policy, logging, rotation và đôi khi non-exportable private keys. Nhưng vẫn có hai rủi ro khác nhau:

- **Key material compromise:** Kẻ tấn công có raw key hoặc có thể tái tạo key; việc disable KMS chưa vô hiệu hóa bản sao ngoài KMS.
- **Authorized API abuse:** Kẻ tấn công chiếm IAM principal có quyền **Decrypt, Unwrap, Sign hoặc GenerateMac**, yêu cầu KMS/HSM thực hiện phép toán hợp lệ mà không xuất khóa gốc.

### 9.1. Các quyền cần phân tách

| Quyền / vai trò | Nguy cơ khi bị chiếm | Biện pháp |
| --- | --- | --- |
| **Encrypt / GenerateDataKey** | Tạo ciphertext hoặc DEK ngoài ý định | Giới hạn workload, môi trường, tenant, purpose |
| **Decrypt / Unwrap** | Truy xuất plaintext/DEK từ bản mã có quyền | Kiểm tra quyền nghiệp vụ, giới hạn context và giám sát |
| **Sign / GenerateMac** | Tạo chữ ký hoặc tag xác thực hợp lệ cho thông điệp giả | Giới hạn message types/issuer, phê duyệt khi cần, phát hiện bất thường |
| **Admin/Change policy** | Mở rộng quyền hoặc thay trạng thái khóa | Tách nhiệm vụ, phê duyệt hai người cho thao tác nhạy cảm khi phù hợp |
| **Export/Import/Backup** | Đưa vật liệu khóa ra ngoài hoặc chèn khóa sai | Hạn chế tối đa, quy trình kiểm soát và ghi vết |
| **Disable/Delete/Destroy** | Gây gián đoạn hoặc mất khả năng giải mã | Giới hạn vai trò, xác nhận phụ thuộc, bảo vệ khỏi xóa nhầm |

**Non-exportable** không ngăn được mọi hành vi lạm dụng. Cần bảo vệ **cả vật liệu khóa và quyền yêu cầu phép toán**.

### 9.2. Trạng thái trong KMS có thể không trùng mô hình ứng dụng

Một nhà cung cấp có thể hỗ trợ **Enabled, Disabled, Pending deletion** hoặc những tên trạng thái khác nhưng không có trường **Compromised**. Khi đó hệ thống có thể:

1. Lưu **incident/security status** trong **key registry** do ứng dụng quản lý.
2. Thực hiện thao tác Disable, revoke grant, chặn IAM và luồng API theo nền tảng.
3. Cập nhật metadata/alias và pipeline để ứng dụng không sử dụng key bị ảnh hưởng.
4. Kiểm thử thực tế rằng các đường **Encrypt/Decrypt/Sign** không còn hoạt động trái chính sách.

Không ghi nhận **“đã thu hồi khóa”** chỉ vì đổi một field trong cơ sở dữ liệu, nếu các hệ thống cũ vẫn có quyền sử dụng key thông qua API.

## 10. Java: mô hình kiểm soát thao tác theo key state

Đoạn mã dưới đây minh họa một **policy gate** cho dịch vụ Java. Nó **không thao tác với vật liệu khóa**: chỉ cho thấy cách kiểm tra **key ID, version, mục đích và trạng thái** trước khi gọi KMS/HSM.

Để đơn giản, chính sách ví dụ **fail closed**: khóa **SUSPENDED, COMPROMISED hoặc DESTROYED** không được tự động sử dụng; khóa **DEACTIVATED** chỉ được Verify chữ ký lịch sử nếu mục đích được phép. Một hệ thống thật có thể có đường **recovery/re-encryption** riêng được phê duyệt, nhưng không được mở đường đó cho mọi request.

~~~java
import java.util.Set;

public final class CompromisedKeyPolicyDemo {
    enum State {
        PRE_ACTIVE, ACTIVE, SUSPENDED,
        DEACTIVATED, COMPROMISED, DESTROYED
    }

    enum Operation {
        ENCRYPT, DECRYPT, WRAP, UNWRAP, SIGN, VERIFY, GENERATE_MAC
    }

    record KeyRecord(
            String keyId,
            int version,
            State state,
            Set<Operation> permittedPurposes
    ) {}

    static boolean isOperationAllowed(
            KeyRecord key, Operation operation
    ) {
        if (key == null || operation == null) {
            return false;
        }
        if (!key.permittedPurposes().contains(operation)) {
            return false; // Đúng mục đích/key usage trước.
        }

        return switch (key.state()) {
            case ACTIVE -> true;
            case DEACTIVATED -> operation == Operation.VERIFY;
            case PRE_ACTIVE, SUSPENDED, COMPROMISED, DESTROYED -> false;
        };
    }

    static void requireAllowed(
            KeyRecord key, Operation operation
    ) {
        if (!isOperationAllowed(key, operation)) {
            throw new SecurityException(
                    "Key operation denied by lifecycle policy");
        }
    }

    public static void main(String[] args) {
        KeyRecord active = new KeyRecord(
                "invoice-signer", 2, State.ACTIVE,
                Set.of(Operation.SIGN, Operation.VERIFY)
        );

        KeyRecord compromised = new KeyRecord(
                "invoice-signer", 1, State.COMPROMISED,
                Set.of(Operation.SIGN, Operation.VERIFY)
        );

        System.out.println("Sign with active key: " +
                isOperationAllowed(active, Operation.SIGN));
        System.out.println("Sign with compromised key: " +
                isOperationAllowed(compromised, Operation.SIGN));
        System.out.println("Verify with compromised key: " +
                isOperationAllowed(compromised, Operation.VERIFY));

        // Trong ứng dụng thực:
        // 1. Đọc metadata từ registry đáng tin cậy.
        // 2. Kiểm tra quyền user/workload và version đã xác thực.
        // 3. Gọi requireAllowed(key, operation).
        // 4. Chỉ sau đó mới gọi API KMS/HSM.
    }
}
~~~

Kết quả dự kiến:

~~~text
Sign with active key: true
Sign with compromised key: false
Verify with compromised key: false
~~~

### 10.1. Vì sao policy gate phải đi cùng IAM và dữ liệu tin cậy?

Chỉ kiểm tra **state** là chưa đủ. Ví dụ:

- Một người dùng có thể sửa một trường **keyId** trong request để chọn khóa khác nếu API không ràng buộc tenant và resource.
- Registry có thể bị đánh tráo trạng thái thành ACTIVE; cần bảo vệ quyền ghi, lịch sử thay đổi và tính toàn vẹn dữ liệu.
- Trạng thái mới có thể chưa lan tới các instance vì cache; cần cơ chế **invalidation/versioning** và fail-closed phù hợp mức khẩn cấp.
- KMS có thể vẫn chấp nhận Decrypt hoặc Sign nếu IAM/KMS policy chưa được cập nhật; phải áp dụng **defense in depth**.
- **VERIFY lịch sử** có thể được phép theo một quy trình pháp lý/forensic riêng; ví dụ trên từ chối mặc định để tránh tự động tin khóa đã bị compromised.

**KeyRecord là một minh họa policy**, không phải schema chuẩn KMS. Với production, hệ thống cần kiểm soát trạng thái bằng cơ chế bền vững, cập nhật nguyên tử hoặc xử lý tranh chấp phiên bản khi cần, audit và kiểm thử tình huống race condition.

### 10.2. Một luồng ứng dụng nên xử lý sự cố ra sao?

~~~text
Incident event:
    keyId = dek-invoices-v7
    reason = plaintext key found in exposed artifact

Security control plane:
    recordIncident(keyId, evidenceRef, timestamp)
    setSecurityStatus(keyId, COMPROMISED)
    revokePrincipalAccess(...)
    disableNewEncryptOrSign(keyId)
    scheduleMigrationToNewKey(...)

Data plane:
    rejectNewWriteUsingCompromisedKey()
    permitOnlyApprovedRecoveryPathWhenNeeded()
    logKeyIdOperationAndDecisionWithoutSecretMaterial()

Post-incident:
    verifyMigrationAndBackupCoverage()
    retireAndDestroyWhenApproved()
    retainIncidentMetadataForAudit()
~~~

Đây là **mã giả quy trình**, không phải lời gọi API cụ thể của KMS. Không thực hiện quy trình có nguy cơ hủy dữ liệu mà không kiểm kê dependency và phương án khôi phục.

## 11. Tình huống thực tế: lộ KEK trong hệ thống nhiều tenant

Giả sử một dịch vụ thương mại điện tử dùng **KMS** bảo vệ **KEK**; mỗi tenant có DEK để mã hóa đơn hàng bằng **AES-GCM**. Trong một lần triển khai, credential có quyền Unwrap của KEK đã bị lộ trong hệ thống CI/CD; log ghi nhận một số lệnh Unwrap bất thường.

**Điều biết chắc:** Có nghi vấn quyền sử dụng KEK đã bị lạm dụng. **Điều chưa biết:** Đối thủ có nhận raw DEK hay chỉ gọi các API không xuất plaintext? Đã sao chép wrapped DEK hoặc ciphertext nào? Khoảng thời gian ảnh hưởng đến đâu?

### 11.1. Cách phân loại và xử lý

1. **Bảo toàn log**, ghi incident ID, key ID/version, account/role, time window và kết quả API.
2. **Thu hồi credential/grant bị lộ**; tạm dừng những đường Unwrap không cần thiết và phân quyền thay thế cho luồng kinh doanh đã kiểm chứng.
3. **Đánh giá phạm vi**: đối tác/tenant nào dùng KEK, bao nhiêu DEK được wrap, các bản sao/backup trong thời gian bị lộ.
4. **Tạo KEK mới** và cập nhật policy; không tái sử dụng credential bị xâm phạm.
5. Quyết định **rewrap** hay **thay DEK và re-encrypt** dựa trên khả năng DEK bị lộ và mức bảo vệ cần đạt.
6. Kiểm thử truy cập dữ liệu mới và cũ theo quyền; chặn đường dùng KEK cũ; xử lý các instance cache và key alias.
7. Điều tra các truy vấn và bản ghi có thể đã bị đọc; rà soát rủi ro dữ liệu, thông báo khi chính sách/yêu cầu áp dụng.
8. Ghi kết luận sự cố, chi phí khắc phục, nguyên nhân gốc và cải tiến IAM, secret scanning, cấu hình pipeline, logging.

### 11.2. Điều gì không nên làm?

- **Không** chỉ đổi một KMS alias rồi tuyên bố đã sửa toàn bộ sự cố.
- **Không** xóa KEK cũ ngay khi vẫn còn dữ liệu cần được di chuyển, trừ khi có quyết định khẩn cấp xử lý mất khả năng đọc đã được chấp nhận.
- **Không** giả định rằng HSM không xuất khóa thì mọi thao tác Unwrap đều vô hại.
- **Không** sao chép raw DEK vào file nội bộ để “debug” cuộc điều tra.
- **Không** giữ tất cả tenant dùng cùng quyền Unwrap chỉ để giảm công quản trị.

### 11.3. Bảng quyết định nhanh

| Câu hỏi | Nếu câu trả lời là có | Ảnh hưởng đến quyết định |
| --- | --- | --- |
| Kẻ tấn công có raw KEK hoặc có thể giải bọc từ bản sao? | Có nguy cơ với wrapped DEK đã thu thập | Cần xem xét toàn bộ dữ liệu con và bản sao cũ, không chỉ rewrap |
| Kẻ tấn công có raw DEK? | DEK đã compromised | Ưu tiên thay DEK/re-encrypt và đánh giá plaintext cũ |
| Chỉ có quyền Unwrap bị lạm dụng? | Chưa chắc KEK bytes bị lộ | Thu hồi principal, xem output API, scope, log và chính sách |
| Có nhiều tenant dùng chung KEK? | Phạm vi tác động lớn | Phân vùng khóa và quyền để giảm blast radius |
| Backup chứa wrapped DEK cũ? | Bản cũ vẫn có thể bị sao chép/giải bọc | Kiểm tra retention, khả năng restore và bảo vệ backup |
| KMS API còn cho phép gọi bằng principal cũ? | Biện pháp cô lập chưa đủ | Chặn quyền và kiểm thử đường gọi thực tế |

## 12. Kiểm toán, cảnh báo và mục tiêu vận hành

Một hệ thống quản lý khóa an toàn cần **nhìn thấy và phản ứng** được với sự cố. Những sự kiện nên có audit, tùy khả năng nền tảng:

- Tạo/import key, thay key policy, cấp và thu hồi grant, export key (nếu hỗ trợ).
- Encrypt/Decrypt, Wrap/Unwrap, Sign/GenerateMac từ workload và key ID cụ thể.
- Đổi trạng thái Active/Suspended/Compromised, thu hồi chứng chỉ, disable và schedule deletion.
- Thay alias, thay truststore/JWKS, rotation và migration của DEK/KEK.
- Lỗi xác thực, lượt sử dụng bất thường, thao tác từ role mới hoặc tenant không phù hợp.

### 12.1. Những chỉ số cần theo dõi

| Chỉ số | Vì sao có ích? |
| --- | --- |
| **Time to detect** | Thời gian từ sự kiện có thể bắt đầu xâm phạm đến lúc phát hiện |
| **Time to contain** | Thời gian chặn credential và đường lạm dụng khóa |
| **Affected key versions** | Số phiên bản khóa thuộc phạm vi sự cố |
| **Dependent assets** | Ciphertext, wrapped DEK, chữ ký, token hoặc hệ thống phụ thuộc |
| **Migration coverage** | Tỷ lệ tài sản đã chuyển sang khóa mới và đã kiểm thử |
| **Residual legacy usage** | Lượt dùng khóa cũ vẫn xảy ra sau mốc chặn |
| **Recovery success** | Khả năng khôi phục dữ liệu hợp lệ sau thay khóa |

Không ghi **secret material, DEK plaintext, private key hoặc dữ liệu khách hàng nhạy cảm** vào log chỉ để tăng khả năng quan sát.

### 12.2. Phân biệt log mật mã và log nghiệp vụ

KMS có thể ghi một lệnh Decrypt thành công, nhưng chưa biết lệnh đó có đúng **quyền xem hóa đơn** hay không. Cần kết nối:

**KMS log** (principal, key ID, operation) + **application log** (user, tenant, record, authorization decision) + **incident timeline**.

Việc kết nối giúp xác định dữ liệu bị truy cập trái phép mà không cần đưa raw key vào hệ thống phân tích.

## 13. Các lỗi sai phổ biến khi xử lý compromised state

| Sai lầm | Vì sao nguy hiểm? | Cách khắc phục |
| --- | --- | --- |
| Chỉ đặt **status=COMPROMISED** trong database | KMS/API, cache hoặc service khác vẫn có thể sử dụng khóa | Đồng bộ policy, revoke grants, vô hiệu hóa đường sử dụng và kiểm thử |
| Coi khóa non-exportable là không thể bị lạm dụng | Workload bị chiếm có thể gọi Sign/Unwrap hợp lệ | Kiểm soát API, phân quyền ngữ cảnh, giám sát và điều tra |
| Chỉ rewrap DEK đã lộ | DEK cũ vẫn giải mã được ciphertext cũ | Thay DEK và re-encrypt khi rủi ro yêu cầu |
| Chỉ rotate KEK khi root key đã bị lộ | Các nhánh khóa khác vẫn phụ thuộc root compromised | Kiểm kê toàn bộ cây khóa và thiết kế migration |
| Hủy khóa ngay khi phát hiện | Có thể mất khả năng đọc dữ liệu/backup, phá bằng chứng | Cô lập trước; hủy sau khi đánh giá sự cố, migration và retention |
| Giữ key cũ mãi để tương thích | Tăng cửa sổ lạm dụng, nhất là khi đã lộ | Đặt thời hạn, đường phục hồi đặc biệt và điều kiện ngừng dùng |
| Cho hệ thống tự fallback sang key cũ | Khóa compromised tiếp tục tạo bản mã/chữ ký mới | Fail closed; không cho fallback làm giảm bảo mật |
| Nghĩ cập nhật chứng chỉ ở server là mọi client đã ngừng tin | Cache JWKS/truststore có thể còn khóa cũ | Phân phối và xác minh trạng thái của bên nhận, timeout/refresh |
| Xem chữ ký có Verify=true là hợp lệ tuyệt đối | Signer key có thể bị lộ, ký sai thời điểm hoặc sai mục đích | Xét trạng thái trust, thời gian, danh tính và quyền nghiệp vụ |
| Chỉ điều tra key ID mà không kiểm tra phiên bản/alias | Bỏ sót ciphertext và nhánh phụ thuộc | Lưu metadata version, quan hệ DEK/KEK và asset inventory |
| Xem không có log là không có sự cố | Log có thể thiếu hoặc key đã bị sao chép qua nơi khác | Đánh giá nguồn bằng chứng, ghi nhận bất định và giảm rủi ro |
| Quên backup và môi trường dự phòng | Restore đưa key cũ và policy cũ quay lại production | Kiểm tra/điều chỉnh backup, region và quy trình recovery |
| Ghi raw key vào ticket điều tra | Khuếch đại chính sự cố lộ khóa | Dùng key ID, fingerprint phù hợp, evidence reference và kho bảo vệ |
| Xóa hồ sơ khi key đã destroyed | Mất khả năng truy vết, chứng minh ứng phó và cải tiến | Lưu hồ sơ sự cố độc lập với vật liệu khóa |

## 14. Checklist xử lý một khóa compromised

Trước khi đóng sự cố, hãy trả lời:

1. **Nhận diện:** Khóa nào, ID/version nào, loại và thuật toán gì, mục đích và miền tin cậy nào?
2. **Bằng chứng:** Sự cố là suspected hay confirmed? Lộ bytes, lạm dụng API hay thay public trust? Khoảng thời gian nào?
3. **Containment:** Đã ngừng Encrypt/Sign/Wrap/Unwrap nguy hiểm, revoke principal và ngăn fallback sang key cũ?
4. **Phụ thuộc:** Đã kiểm kê root–KEK–DEK, ciphertext, message signatures, token, tenant, region và backup liên quan?
5. **Bảo vệ dữ liệu:** Đã đánh giá bên tấn công có raw key, wrapped key, ciphertext hoặc plaintext đã lấy được không?
6. **Thay khóa:** Khóa mới có được sinh bằng nguồn đáng tin cậy và policy quyền tối thiểu?
7. **Migration:** Đã lựa chọn đúng rewrap/re-encrypt, thay signer/MAC key, update truststore/JWKS hoặc reset password theo loại khóa?
8. **Tương thích:** Đã kiểm tra key ID/version, khả năng đọc dữ liệu lịch sử và các hệ thống chưa cập nhật?
9. **Tin cậy:** Các bên Verify đã ngừng tin khóa đã thu hồi theo thời gian và chính sách chưa?
10. **Sẵn sàng:** Có kế hoạch khôi phục dữ liệu, backup và rollback an toàn mà không hồi sinh key compromised?
11. **Kiểm toán:** Có bằng chứng ai thay policy, ai đã dùng key, dữ liệu/đối tác nào ảnh hưởng và kết quả chuyển đổi?
12. **Hủy:** Điều kiện destruction, xử lý bản sao và nghĩa vụ retention đã được phê duyệt?
13. **Nguyên nhân gốc:** Đã sửa IAM, logging, source code, CI/CD, RNG, nonce hoặc quy trình gây sự cố?
14. **Rủi ro tồn dư:** Có ghi rõ những bản sao không thể thu hồi và dữ liệu có thể đã bị lộ không?

## 15. Ghi nhớ

- **Compromised state** phản ánh khóa hoặc quyền sử dụng khóa đã mất thuộc tính tin cậy quan trọng; nguyên nhân có thể là **lộ vật liệu khóa**, **lạm dụng API** hoặc **đánh tráo nguồn tin cậy**.
- **Compromised không đồng nghĩa deactivated, revoked hay destroyed.** Những thao tác sau là biện pháp hoặc trạng thái vận hành; chúng không làm một bí mật đã lộ trở lại bí mật.
- **Phạm vi hậu quả phụ thuộc loại khóa.** DEK ảnh hưởng ciphertext, KEK/root ảnh hưởng các khóa con, signing/MAC key ảnh hưởng tính xác thực và pepper ảnh hưởng khả năng dò mật khẩu khi có dữ liệu hash.
- **Rewrap khác re-encrypt.** Nếu DEK đã lộ, chỉ dùng KEK mới để bọc lại DEK cũ không đủ để phục hồi bảo mật.
- **KMS/HSM giảm nguy cơ lộ raw key nhưng không loại bỏ việc lạm dụng quyền** Decrypt/Unwrap/Sign khi workload bị xâm phạm.
- **Incident response là một vòng đời xử lý hoàn chỉnh:** phát hiện → cô lập → đánh giá phạm vi → thay khóa → chuyển phụ thuộc → kiểm thử → thu hồi/hủy → giữ hồ sơ và cải tiến.
- **Không có cách “xóa” dữ liệu hay chữ ký đã bị sao chép chỉ bằng rotation.** Phải điều tra và xử lý hậu quả nghiệp vụ/tuân thủ tương ứng.

Khi một khóa đi vào **compromised state**, ba câu hỏi quyết định hướng xử lý là: **“Kẻ tấn công đã có những gì?”, “Những khóa, bản mã, chữ ký và dịch vụ nào phụ thuộc vào khóa đó?”, “Cần thay và chuyển những tài sản nào để phục hồi tin cậy mà không làm mất dữ liệu hợp lệ?”** Trả lời được ba câu hỏi đó giúp biến một trạng thái trong key registry thành hành động bảo vệ hệ thống thực tế.
