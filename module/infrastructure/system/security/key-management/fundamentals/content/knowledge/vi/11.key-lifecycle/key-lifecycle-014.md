# Destroy key — Hủy khóa mật mã an toàn trong vòng đời khóa

## 1. Destroy key là gì?

**Destroy key (hủy khóa mật mã)** là hoạt động kết thúc khả năng sử dụng **vật liệu khóa mật mã (cryptographic key material)** trong một phạm vi quản lý xác định. Đối với khóa bí mật, mục tiêu là làm cho các chủ thể không còn có thể khôi phục hoặc sử dụng vật liệu khóa đó bằng những bản sao nằm trong phạm vi xử lý. Kết quả phải được xác minh và ghi nhận theo chính sách, chứ không chỉ là thay một nhãn trạng thái trên giao diện quản trị.

Ví dụ, một ứng dụng Java mã hóa hồ sơ bằng AES-GCM. Mỗi tập dữ liệu có **DEK (Data Encryption Key)**, DEK được bọc bởi **KEK (Key Encryption Key)** do KMS bảo vệ. Khi hết thời hạn lưu giữ và được phép xóa dữ liệu, tổ chức có thể chọn **hủy DEK** như một phần của quy trình **cryptographic erasure (crypto-shredding)**. Nếu không còn bản sao DEK dạng rõ, bản wrapped DEK có thể giải bọc hoặc nguồn phục hồi khác, các ciphertext phụ thuộc sẽ không còn giải mã được bằng khóa đó.

Tuy nhiên, việc xóa một bản ghi khóa khỏi database **không bảo đảm** đã hủy mọi bản sao: khóa có thể nằm trong backup, snapshot, cache, bộ nhớ ứng dụng, vùng dự phòng của HSM hoặc hệ thống quản lý khóa khác. Ngoài ra, nếu ciphertext phải được đọc cho nghĩa vụ nghiệp vụ/pháp lý, hủy khóa sớm có thể gây **mất dữ liệu không thể phục hồi**.

Trong chương **Key lifecycle** của học phần **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, destroy key là giai đoạn cần kiểm soát sau **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng và thu hồi**. Nó kết nối các chủ đề mã hóa đối xứng, bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, kiểm soát truy cập và kiểm toán.

> **Nguyên tắc cốt lõi:** Chỉ hủy khóa khi đã xác định **mục đích hủy, tập dữ liệu/phụ thuộc, tất cả bản sao có thể dùng để khôi phục, quyền phê duyệt và khả năng xác minh kết quả**. Hủy khóa là hành động có thể không đảo ngược.

## 2. Vì sao hủy khóa quan trọng?

Một khóa bí mật dù không còn được dùng để mã hóa mới vẫn có thể làm lộ dữ liệu cũ nếu kẻ tấn công có khóa và ciphertext tương ứng. Khi khóa hết nghĩa vụ sử dụng, việc giữ khóa vô thời hạn làm tăng thời gian và bề mặt có thể bị lộ.

Hủy khóa đúng cách giúp:

1. **Giảm thời gian phơi nhiễm:** Không tiếp tục giữ một bí mật mà hệ thống không cần nữa.
2. **Giảm phạm vi thiệt hại:** Một sự cố IAM/backup sau này có thể không còn mở được dữ liệu được bảo vệ bằng khóa đã hủy thực sự.
3. **Hỗ trợ crypto-erasure:** Vô hiệu hóa khả năng đọc ciphertext khi điều kiện và mô hình đe dọa cho phép.
4. **Đáp ứng chính sách vòng đời:** Liên kết giữ dữ liệu, hết hạn khóa, kết thúc hợp đồng, đổi tenant và quy trình lưu trữ.
5. **Giảm chi phí vận hành:** Hạn chế số khóa, phiên bản, quyền và bản sao không còn cần bảo vệ.

Nhưng mục tiêu này phải cân bằng với **tính sẵn sàng và khả năng khôi phục**. Hủy key trước khi migrate dữ liệu có thể là một sự cố mất dữ liệu nghiêm trọng, không phải một thành công bảo mật.

## 3. Phân biệt destroy, delete, disable, revoke và rotate

Những thao tác này có thể cùng xuất hiện trong công cụ quản lý khóa, nhưng không tương đương về ý nghĩa.

| Thuật ngữ | Ý nghĩa chính | Khóa hoặc dữ liệu còn dùng được? |
| --- | --- | --- |
| **Rotate key** | Tạo/đưa khóa phiên bản mới vào sử dụng, chuyển dần khỏi khóa cũ | Khóa cũ có thể còn cần để giải mã hoặc xác minh lịch sử |
| **Deactivate/retire** | Ngừng sử dụng khóa cho hoạt động mới theo chính sách | Có thể vẫn cho phép một số thao tác cũ |
| **Disable/suspend** | Chặn tạm hoặc dài hạn khả năng gọi API đối với khóa | Vật liệu khóa có thể vẫn tồn tại và có thể được bật lại |
| **Revoke** | Thu hồi quyền hoặc sự tin cậy, chẳng hạn certificate, token, grant | Không làm biến mất mọi bản sao vật liệu khóa |
| **Delete key metadata/alias** | Xóa đối tượng tham chiếu, nhãn hoặc bản ghi quản lý | Chưa chứng minh vật liệu khóa đã bị hủy |
| **Destroy key material** | Xử lý vật liệu khóa để nó không thể được dùng/khôi phục trong phạm vi quản lý | Có thể không đảo ngược; vẫn phải đánh giá các bản sao ngoài phạm vi |
| **Cryptographic erasure** | Làm dữ liệu được mã hóa trở nên không thể giải mã thông qua hủy khóa thích hợp | Chỉ đạt nếu không còn đường khôi phục khóa hoặc plaintext thay thế |

**Ví dụ:** Thay alias của KEK từ phiên bản v1 sang v2 không làm DEK đã bọc bằng v1 tự động bị hủy, và cũng không tự mã hóa lại ciphertext dữ liệu. Tương tự, đặt khóa ở trạng thái **Disabled** không có nghĩa khóa đã bị zeroize hoặc mọi bản sao đã mất.

### 3.1. Hủy khóa là giai đoạn sau khi hết phụ thuộc

~~~mermaid
stateDiagram-v2
    [*] --> PRE_ACTIVE: Tạo và kiểm tra
    PRE_ACTIVE --> ACTIVE: Kích hoạt
    ACTIVE --> DEACTIVATED: Rotate / ngừng dùng mới
    ACTIVE --> COMPROMISED: Phát hiện xâm phạm
    DEACTIVATED --> PENDING_DESTRUCTION: Hết mục đích, phê duyệt
    COMPROMISED --> PENDING_DESTRUCTION: Cô lập, xử lý phụ thuộc
    PENDING_DESTRUCTION --> DEACTIVATED: Hoãn/hủy lịch theo quyền và policy
    PENDING_DESTRUCTION --> DESTROYED: Hủy vật liệu khóa thành công
    DESTROYED --> [*]
~~~

Đây là **mô hình khái niệm**, không phải bộ trạng thái có sẵn của mọi KMS/HSM. Nhiều nhà cung cấp sử dụng những trạng thái như Enabled, Disabled hoặc Pending deletion. Cần ánh xạ chính xác giữa **trạng thái vận hành của nền tảng** và **trạng thái vòng đời/an ninh của tổ chức**.

## 4. Câu hỏi đầu tiên: đang hủy loại khóa nào?

Mỗi loại khóa có mức phụ thuộc khác nhau. Không thể dùng một câu lệnh xóa chung cho mọi tình huống.

| Loại khóa | Dùng để làm gì? | Điều cần kiểm tra trước khi hủy |
| --- | --- | --- |
| **DEK đối xứng** | Mã hóa trực tiếp dữ liệu, ví dụ AES-GCM | Còn ciphertext, bản sao lưu, dữ liệu lịch sử hoặc yêu cầu khôi phục không? |
| **KEK** | Bọc/giải bọc các DEK hoặc khóa con | Có bao nhiêu wrapped key còn phụ thuộc? Đã rewrap đúng chưa? |
| **Root/master key** | Bảo vệ nhánh khóa trong hệ phân cấp | Còn KEK, DEK, phiên bản hoặc tenant nào phụ thuộc? Có quyền tác động trực tiếp đến root không? |
| **Private encryption key** | Giải mã khóa/bí mật trong sơ đồ bất đối xứng | Còn ciphertext/envelope được mã hóa cho public key tương ứng không? |
| **Private signing key** | Tạo chữ ký số | Đã ngừng Sign, xử lý chứng chỉ, trust và bản sao private key chưa? |
| **Public verification key** | Xác minh chữ ký cũ và mới | Còn chứng từ, chữ ký lịch sử, nghĩa vụ kiểm chứng hay bằng chứng thời gian không? |
| **MAC/HMAC key** | Tạo và kiểm tra tag thông điệp | Còn webhook, message hoặc archive cần xác minh không? |
| **Pepper** | Bí mật bổ sung cho password hashing | Còn tài khoản chứa verifier phụ thuộc pepper cũ không? |
| **Ephemeral/session key** | Bảo vệ phiên kết nối | Phiên đã kết thúc, cache/worker/bộ nhớ đã xử lý đúng theo giao thức chưa? |

### 4.1. Hủy một DEK khác hủy một KEK

Trong **envelope encryption**, DEK mã hóa payload; KEK bảo vệ DEK. Nếu hủy **DEK duy nhất có thể sử dụng** để mở một ciphertext, dữ liệu đó có thể mất khả năng giải mã. Nếu chỉ hủy **KEK** nhưng ứng dụng vẫn giữ DEK dạng rõ hoặc có bản wrapped DEK dưới KEK khác, hệ quả sẽ khác.

Điều quan trọng là **liệt kê đường phụ thuộc thực sự** chứ không chỉ đếm key ID.

~~~mermaid
flowchart TD
    ROOT["Root/trust boundary trong KMS/HSM"] --> KEKA["KEK A v1"]
    ROOT --> KEKB["KEK B v2"]
    KEKA --> DEK1["Wrapped DEK hồ sơ 1"]
    KEKA --> DEK2["Wrapped DEK hồ sơ 2"]
    KEKB --> DEK3["Wrapped DEK backup"]
    DEK1 --> C1["Ciphertext hồ sơ 1"]
    DEK2 --> C2["Ciphertext hồ sơ 2"]
    DEK3 --> C3["Ciphertext bản sao lưu"]
    P["Yêu cầu hủy KEK A v1"] --> CHECK{"Còn DEK cần unwrap<br/>bằng KEK A v1?"}
    CHECK -->|"Có"| MIGRATE["Rewrap/migrate, xác minh đọc"]
    CHECK -->|"Không"| APPROVE["Xét điều kiện phê duyệt hủy"]
    MIGRATE --> APPROVE
~~~

Một KMS thực tế có thể không cho truy cập trực tiếp root key nội bộ; sơ đồ không hàm ý ứng dụng có thể hoặc nên hủy root key của nhà cung cấp.

### 4.2. Hủy khóa ký khác ngừng tin chữ ký

Đối với **private signing key**, có thể ngừng ký mới rồi hủy vật liệu private key khi được phê duyệt. Nhưng **public verification key hoặc chứng chỉ** có thể vẫn cần lưu để xác minh tài liệu cũ.

Hủy private key **không xóa chữ ký đã phát hành**. Nếu khóa ký bị xâm phạm, phải xử lý thu hồi chứng chỉ/niềm tin và đánh giá chữ ký theo thời điểm có bằng chứng, không chỉ xóa file private key.

### 4.3. Hủy pepper có thể làm tài khoản không đăng nhập được

Pepper dùng trong sơ đồ password hashing là một bí mật không thể tự thay thế chỉ bằng việc đổi ID. Nếu verifier của tài khoản còn phụ thuộc pepper v1, hủy v1 có thể khiến hệ thống **không xác minh được mật khẩu** của tài khoản đó.

Thường cần **migrate trên lần đăng nhập hợp lệ** khi người dùng cung cấp mật khẩu, hoặc áp dụng **quy trình reset**. Hệ thống phải kiểm kê tỷ lệ bản ghi còn phụ thuộc pepper cũ trước khi hủy.

## 5. Các điều kiện bắt buộc trước khi hủy khóa

Nên có một **pre-destruction checklist** được đánh giá độc lập với yêu cầu xóa:

1. **Danh tính khóa:** Key ID, phiên bản, thuật toán, mục đích, owner, tenant, môi trường và nguồn lưu trữ chính xác.
2. **Lý do hủy:** Hết hạn dữ liệu, kết thúc hợp đồng, hoàn tất rotation, thay thuật toán, sự cố lộ khóa hay mục đích khác.
3. **Trạng thái:** Khóa đã ngừng dùng cho thao tác mới chưa? Có quy trình xử lý compromised riêng nếu đang bị xâm phạm không?
4. **Phụ thuộc:** Đã kiểm kê ciphertext, wrapped DEK, chứng chỉ, chữ ký, token, message, password verifier và dịch vụ sử dụng khóa?
5. **Khả năng khôi phục:** Đã kiểm tra backup/snapshot, vùng DR, bản sao ở region khác, cache và bản xuất?
6. **Retention/legal hold:** Còn nghĩa vụ giữ dữ liệu, tranh chấp hoặc lệnh giữ chứng cứ không? Có xung đột cần phê duyệt không?
7. **Migration:** Đã rewrap/re-encrypt/cập nhật tin cậy hoặc reset/migrate mật khẩu khi cần?
8. **Kiểm thử:** Đã xác minh khả năng giải mã/xác minh bằng key mới và kiểm thử các bản ghi cũ theo chính sách?
9. **Phê duyệt:** Người yêu cầu và người phê duyệt có được tách vai trò, thực hiện dual control khi cần không?
10. **Khả năng đảo ngược:** Có giai đoạn pending deletion/cancellation không? Thời điểm nào là không thể khôi phục?
11. **Kế hoạch phản ứng:** Nếu hủy gây gián đoạn hoặc phát hiện phụ thuộc muộn, có kế hoạch xử lý không dựa vào giả định phục hồi khóa đã hủy?
12. **Bằng chứng:** Sẽ lưu log, xác nhận từ KMS/HSM, kết quả kiểm thử và quyết định như thế nào mà không lưu raw key?

**Nếu không thể chứng minh một phụ thuộc đã được xử lý, không mặc nhiên cho phép hủy.** Tùy mức khẩn cấp, tổ chức có thể **cô lập hoặc disable** trước rồi điều tra, thay vì thực hiện ngay hành động không đảo ngược.

## 6. Cryptographic erasure (crypto-shredding) hoạt động thế nào?

**Crypto-shredding** là phương án giảm hoặc loại bỏ khả năng đọc dữ liệu mã hóa bằng cách hủy khóa cần thiết để giải mã. Đây có thể là một phần của chiến lược xóa dữ liệu trong hệ thống lưu trữ phân tán, nơi việc xóa tức thời mọi bản sao dữ liệu vật lý khó bảo đảm.

### 6.1. Ví dụ: một tenant rời nền tảng

Giả sử tenant A có dữ liệu được mã hóa bằng **DEK-A**, còn tenant B dùng **DEK-B** riêng. Sau khi hết thời hạn lưu trữ và được phép xóa:

1. Xác nhận toàn bộ dữ liệu của A thuộc phạm vi xóa và không còn legal hold.
2. Ngừng các thao tác tạo thêm bản mã của A bằng DEK-A.
3. Kiểm kê bản ghi, object storage, backup, cache và mọi bản sao DEK-A.
4. Kiểm tra rằng không có tenant khác, nhóm dữ liệu khác hoặc luồng restore hợp lệ còn phụ thuộc DEK-A.
5. Hủy vật liệu DEK-A và những đường khôi phục nó theo cơ chế đã được thẩm định.
6. Kiểm tra trạng thái hủy ở các ranh giới quản lý, xác nhận các đường giải mã không còn hoạt động, lưu bằng chứng.
7. Thực hiện thêm quy trình xóa dữ liệu theo nghĩa vụ pháp lý và chính sách áp dụng.

Nếu A và B **dùng chung DEK**, hủy DEK để xóa riêng A sẽ có thể làm mất dữ liệu của B. Do đó, **phân vùng khóa theo miền xóa** là quyết định phải được thiết kế ngay từ đầu.

### 6.2. Vì sao hủy KEK chưa chắc đã crypto-shred dữ liệu?

Một ciphertext có thể vẫn đọc được nếu:

- Một bản **plaintext DEK** còn trong cache, log, backup hoặc máy trạm.
- DEK được wrap dưới **KEK thứ hai** hoặc thuộc đường khôi phục có thể sử dụng.
- Hệ thống vẫn giữ **key material trong HSM backup/replica** theo quy trình phục hồi.
- Có **bản sao plaintext** của dữ liệu bên ngoài ranh giới mã hóa.
- Kẻ tấn công đã sao chép cả DEK và ciphertext **trước thời điểm hủy**.

Vì thế, **crypto-erasure chỉ có hiệu quả trong phạm vi mô hình đe dọa và bản sao đã kiểm soát**. Nó không tự chứng minh rằng mọi plaintext đã biến mất khỏi thế giới.

### 6.3. Tính bất khả phục hồi là đặc tính hai mặt

Nếu DEK duy nhất bị hủy thực sự, bên không có khóa sẽ khó giải mã ciphertext; nhưng chính tổ chức cũng có thể **mất dữ liệu vĩnh viễn**. Khi dữ liệu còn cần truy cập, phải hoàn tất migration trước khi hủy.

**Không thiết kế “đường khôi phục bí mật” không được kiểm soát** chỉ để phòng hủy nhầm: một bản sao khóa không được quản trị sẽ phá vỡ giả định crypto-shredding và trở thành điểm rò rỉ mới.

## 7. Hủy vật liệu khóa trong những nơi lưu trữ khác nhau

Không có một câu lệnh kỹ thuật duy nhất phù hợp với tất cả hệ thống.

| Nơi chứa khóa | Cơ chế xử lý thường gặp | Giới hạn cần ghi rõ |
| --- | --- | --- |
| **Java heap/process memory** | Giảm thời gian sống, xóa các mảng byte ứng dụng kiểm soát, kết thúc session/process khi cần | JVM/provider có thể giữ bản sao; không thể bảo đảm zeroize mọi bản sao chỉ bằng Arrays.fill |
| **Secret manager** | Xóa phiên bản bí mật hoặc vô hiệu hóa theo API/chính sách | Backup, lịch sử version, replica và cache có thể còn |
| **KMS được quản lý** | Lên lịch xóa/hủy key material hoặc phiên bản khi dịch vụ hỗ trợ | Semantics, thời gian chờ, khả năng hủy lịch, replication và recovery tùy nhà cung cấp |
| **HSM** | Dùng thao tác zeroization/destruction, lifecycle và chính sách bảo vệ của thiết bị | Phải kiểm tra backup, clone, cluster, domain và chứng cứ từ HSM |
| **Java keystore / file mã hóa** | Xóa khóa và các bản sao file, cập nhật keystore/password/backup theo chính sách | Xóa file thông thường không đồng nghĩa secure erase trên SSD, snapshot hoặc backup |
| **Database** | Xóa record/wrapped key, migration và xóa bản sao theo retention | Database page, WAL, backup và replica có thể còn dữ liệu |
| **Container/CI/CD** | Loại bỏ secrets khỏi image/artifact, biến môi trường, pipeline logs và cache | Image layers, artifact store và hệ thống build cũ cần được xử lý riêng |

### 7.1. Zeroization là gì?

**Zeroization** là thao tác xóa hoặc ghi đè vật liệu bí mật trong ranh giới thiết bị/bộ nhớ để hạn chế khả năng khôi phục. Cách thực hiện, bảo đảm và bằng chứng khác nhau theo phần cứng, hệ điều hành và thư viện.

Trong Java, **Arrays.fill(rawBytes, (byte) 0)** hữu ích để giảm thời gian tồn tại của **mảng byte mà ứng dụng đang sở hữu**, nhưng không bảo đảm xóa:

- Bản sao của khóa nằm trong đối tượng **SecretKey** hoặc provider.
- Byte được sao chép vào các buffer khác hoặc vào native memory.
- Dữ liệu trong heap dump, swap, crash dump hoặc snapshot đã được tạo.
- Key bytes được giữ trong cache của ứng dụng khác.

Do đó, **zeroization trong JVM không phải bằng chứng hoàn chỉnh của key destruction toàn hệ thống**.

### 7.2. Không đánh đồng xóa file với secure erase

Xóa một file trên hệ thống lưu trữ có thể chỉ xóa metadata tham chiếu. Trên SSD, hệ thống dùng wear leveling, snapshot hoặc object storage versioning, việc ghi đè một file không chắc đã đụng tới mọi bản sao vật lý.

Tùy yêu cầu, cần sử dụng phương pháp xóa dữ liệu/thiết bị được phê duyệt hoặc **crypto-erasure** với quản lý khóa đúng từ đầu. Nếu môi trường đòi hỏi chứng nhận hoặc kiểm chứng việc xử lý thiết bị, tuân thủ quy trình lưu trữ và chuẩn an toàn thích hợp; không tự tuyên bố đạt chuẩn chỉ vì gọi một lệnh xóa.

### 7.3. Cloud KMS và thời gian chờ xóa

Một số KMS hỗ trợ **scheduled deletion** với thời gian chờ và khả năng hủy trước mốc thực thi. Một số sản phẩm khác có semantics **destroy key version** hoặc cơ chế khôi phục khác.

Vì vậy cần phân biệt:

- **Requested:** Yêu cầu hủy đã được gửi.
- **Pending:** Đang trong khoảng chờ; khóa có thể bị vô hiệu hóa hoặc vẫn có một số khả năng khôi phục theo dịch vụ.
- **Executed:** Dịch vụ xác nhận đã thực hiện hành động hủy/xóa.
- **Verified:** Bằng chứng từ nhà cung cấp và kiểm thử ứng dụng phù hợp cho thấy key không còn được dùng/khôi phục qua các đường đã kiểm soát.

**Không tuyên bố khóa đã bị hủy ngay khi API chỉ trả kết quả “scheduled”.** Cũng không tự gán thời gian chờ cố định cho mọi KMS mà không đọc hợp đồng API thực tế.

## 8. Quy trình hủy khóa có phê duyệt và kiểm toán

Một quy trình an toàn nên tách **control plane** (đề xuất/phê duyệt/quản lý trạng thái) khỏi **data plane** (mã hóa/giải mã sử dụng khóa).

~~~mermaid
flowchart TD
    REQUEST["Yêu cầu Destroy(keyId, version, reason)"] --> INVENTORY["Kiểm kê phụ thuộc, bản sao,<br/>backup và legal hold"]
    INVENTORY --> READY{"Có thể hủy mà không làm mất<br/>dữ liệu cần giữ?"}
    READY -->|"Chưa"| HOLD["BLOCK/DEFER: migrate, điều tra,<br/>hoặc xin quyết định bổ sung"]
    HOLD --> INVENTORY
    READY -->|"Có"| APPROVAL["Phê duyệt độc lập / dual control<br/>nếu policy yêu cầu"]
    APPROVAL --> STOP["Ngừng thao tác mới,<br/>đồng bộ trạng thái/cache"]
    STOP --> SCHEDULE["Gọi KMS/HSM destruction API<br/>theo đặc tả nền tảng"]
    SCHEDULE --> WAIT{"Pending hay đã executed?"}
    WAIT -->|"Pending"| TRACK["Theo dõi deadline, quyền cancel,<br/>không tự báo thành công"]
    TRACK --> WAIT
    WAIT -->|"Executed"| VERIFY["Xác minh trạng thái, đường gọi,<br/>replica và bằng chứng"]
    VERIFY --> AUDIT["Ghi hồ sơ/attestation<br/>không chứa vật liệu khóa"]
~~~

### Bước 1 — Mở yêu cầu và xác minh chủ thể

Yêu cầu phải chứa **key ID/version, loại khóa, owner, môi trường, mục đích, lý do hủy, ticket/incident ID và thời điểm dự kiến**. Không chấp nhận chỉ một tên alias có thể trỏ sang khóa khác.

Kiểm tra requester có quyền **đề xuất hủy** theo tenant và môi trường. Với khóa sản xuất hoặc root/KEK nhiều phụ thuộc, cần thêm phê duyệt của chủ dữ liệu và người chịu trách nhiệm bảo mật theo chính sách.

### Bước 2 — Lập bản đồ phụ thuộc

Thu thập **metadata đủ để biết dữ liệu nào sẽ mất khả năng đọc**. Không đưa raw DEK/private key vào hệ thống quản trị chỉ để kiểm kê.

Các đầu mối thường gồm encryption context, key registry, bản ghi có key ID/version, database schema, object metadata, backup catalog, dịch vụ dùng khóa, chứng chỉ liên quan và các bản sao được phép.

### Bước 3 — Hoàn tất migration và thử khôi phục

Nếu khóa cũ còn bảo vệ dữ liệu được phép giữ:

- Đối với **DEK**, giải mã và **re-encrypt** bằng DEK mới theo chính sách.
- Đối với **KEK**, **rewrap** các DEK dưới KEK mới; kiểm tra khả năng đọc dữ liệu, không nhầm rewrap với re-encrypt.
- Đối với **private key giải mã bất đối xứng**, giải bọc/di chuyển các bí mật phụ thuộc nếu được phép và cần thiết.
- Đối với **private signing key**, ngừng Sign và bảo đảm bên Verify đã biết khóa mới; giữ public verification material cho lịch sử nếu cần.
- Đối với **MAC key/pepper**, hoàn tất cập nhật bên nhận hoặc migration verifier theo chính sách.

Thử **restore từ backup** trong môi trường được bảo vệ để bảo đảm kết quả kỳ vọng, đồng thời xác minh backup không âm thầm giữ đường phục hồi bị cấm.

### Bước 4 — Phê duyệt và khóa đường sử dụng mới

Tùy độ nhạy cảm, dùng **four-eyes principle / dual control**: người đề xuất không phải người cuối cùng phê duyệt. Ghi rõ điều kiện phê duyệt, bất kỳ ngoại lệ nào và ảnh hưởng được chấp nhận.

Chặn việc tạo ciphertext hoặc chữ ký mới bằng khóa sắp hủy. Kiểm tra **cache, workload, job đang chạy và IAM/KMS grants**; nếu còn thao tác mới, cần dừng hoặc chuyển phiên bản trước khi đi tiếp.

### Bước 5 — Thực thi hủy qua API phù hợp

Gọi thao tác do **KMS/HSM/secret manager** cung cấp, bằng định danh khóa chính xác. Đối với thiết bị lưu trữ hoặc file, dùng phương pháp xóa được phê duyệt và xử lý các bản sao.

Nếu hành động có **pending period**, theo dõi cho đến khi thực thi. Nếu API lỗi hoặc timeout, **không tự giả định đã xóa**; tra trạng thái thật và thực hiện retry idempotent theo hợp đồng API.

### Bước 6 — Xác minh và đóng hồ sơ

Kiểm tra trạng thái key và quyền sử dụng từ hệ thống chủ quản; xác minh ứng dụng không thể gọi các thao tác bị cấm. Kiểm tra bản sao, backup và các vùng quản lý có liên quan theo khả năng và chính sách.

Lưu **bằng chứng của hành động hủy**, người phê duyệt, timestamp, key ID/version, loại chứng cứ, kết quả đối soát và tồn dư chưa giải quyết. **Không đưa secret material vào audit log.**

## 9. Java: chặn Destroy khi còn phụ thuộc

Ví dụ sau sử dụng Java 17 để minh họa **preflight policy gate** trước khi điều phối lệnh hủy. Mã **không gọi KMS, không tự xóa khóa và không khẳng định đã hủy thành công**. Mục tiêu là tách rõ:

- Quyết định khóa **có đủ điều kiện** bắt đầu quy trình hủy hay không.
- Quyền phê duyệt của chủ thể có trách nhiệm.
- Trạng thái **READY, PENDING và DESTROYED** chỉ được cập nhật sau bằng chứng từ hệ thống thực.

~~~java
import java.util.List;
import java.util.Objects;
import java.util.Set;

public final class KeyDestructionGate {
    enum State {
        ACTIVE, DEACTIVATED, COMPROMISED,
        PENDING_DESTRUCTION, DESTROYED
    }

    record KeyRef(String id, int version, State state) {}

    record DependencyReport(
            boolean currentWritesStopped,
            boolean hasRequiredCiphertext,
            boolean hasRequiredWrappedKeys,
            boolean hasRequiredHistoricalVerification,
            boolean backupsReviewed,
            boolean replicasReviewed,
            boolean legalHoldActive,
            boolean migrationVerified
    ) {}

    record Approval(
            String requester,
            String approver,
            String incidentOrChangeId,
            boolean authorized
    ) {}

    static List<String> blockers(
            KeyRef key,
            DependencyReport deps,
            Approval approval
    ) {
        Objects.requireNonNull(key);
        Objects.requireNonNull(deps);
        Objects.requireNonNull(approval);

        var failures = new java.util.ArrayList<String>();

        if (key.id() == null || key.id().isBlank() || key.version() < 1) {
            failures.add("Invalid key identity/version");
        }
        if (key.state() != State.DEACTIVATED &&
                key.state() != State.COMPROMISED) {
            failures.add("Key must be retired/contained first");
        }
        if (!deps.currentWritesStopped()) {
            failures.add("New writes/signatures still use this key");
        }
        if (deps.hasRequiredCiphertext() ||
                deps.hasRequiredWrappedKeys() ||
                deps.hasRequiredHistoricalVerification()) {
            failures.add("Unresolved key dependencies");
        }
        if (!deps.backupsReviewed() || !deps.replicasReviewed()) {
            failures.add("Backup/replica inventory is incomplete");
        }
        if (deps.legalHoldActive()) {
            failures.add("Legal hold prohibits destruction");
        }
        if (!deps.migrationVerified()) {
            failures.add("Migration/recovery checks not verified");
        }
        if (!approval.authorized() ||
                approval.incidentOrChangeId() == null ||
                approval.incidentOrChangeId().isBlank()) {
            failures.add("Missing authorized approval/change record");
        }
        if (Objects.equals(approval.requester(), approval.approver())) {
            failures.add("Requester cannot approve own request");
        }
        return List.copyOf(failures);
    }

    public static void main(String[] args) {
        var key = new KeyRef(
                "invoice-dek", 7, State.DEACTIVATED);
        var deps = new DependencyReport(
                true,  // no new writes
                false, // no required ciphertext remains
                false, // no wrapped-key dependencies
                false, // no historical verification requirement
                true,  // backup reviewed
                true,  // replicas reviewed
                false, // no legal hold
                true   // migration verified
        );
        var approval = new Approval(
                "app-owner", "security-reviewer", "CHG-2026-42", true);

        List<String> failures = blockers(key, deps, approval);
        System.out.println("Eligible for destruction request: " +
                failures.isEmpty());

        if (failures.isEmpty()) {
            System.out.println(
                    "Next step: request KMS deletion; do not claim destroyed.");
        } else {
            failures.forEach(System.out::println);
        }
    }
}
~~~

**Kết quả dự kiến:**

~~~text
Eligible for destruction request: true
Next step: request KMS deletion; do not claim destroyed.
~~~

### 9.1. Ranh giới của ví dụ

1. **DependencyReport không tự chứng minh các phụ thuộc đã hết.** Trong production, các cờ cần đến từ inventory, truy vấn data catalog, migration checks và bằng chứng được kiểm soát.
2. **Approval.authorized** không đủ để xác thực một người thật. Cần tích hợp IAM, chữ ký/phê duyệt workflow, version và quyền theo phạm vi khóa.
3. Kiểm tra **requester khác approver** là minh họa cho dual control; một tổ chức có thể yêu cầu nhiều cấp, hardware quorum hoặc separation of duties mạnh hơn.
4. Policy gate không thay cho API KMS/HSM. Khi API trả về **pending**, trạng thái ứng dụng không được tự chuyển sang **destroyed**.
5. Phải xử lý **race condition**: sau preflight, một workload có thể ghi ciphertext mới bằng key cũ nếu chưa chặn thành công. Cần đóng quyền sử dụng, đồng bộ metadata, xác minh không có write mới rồi mới thực thi lệnh.
6. Trong trường hợp **compromised**, chính sách có thể yêu cầu containment khẩn cấp dù migration chưa hoàn tất. Quy trình cần đường xử lý ngoại lệ được phê duyệt, không dùng bỏ qua mặc định.

**Không in raw key hoặc plaintext vào log** để theo dõi quy trình hủy. Các log cần tập trung vào key ID/version, quyết định policy, caller, thay đổi trạng thái và chứng cứ của KMS/HSM.

## 10. Hủy khóa bị compromised: xử lý khác hủy định kỳ

Khóa đã **compromised** là khóa đã mất một thuộc tính tin cậy do lộ vật liệu khóa hoặc lạm dụng quyền sử dụng. Không nên chờ đủ điều kiện hủy thông thường rồi tiếp tục dùng khóa đó như cũ.

### 10.1. Thứ tự ưu tiên khi có sự cố

1. **Contain:** Chặn Encrypt/Sign/Unwrap mới bằng khóa hoặc principal bị ảnh hưởng ở những ranh giới phù hợp.
2. **Investigate:** Bảo toàn chứng cứ, xác định raw key có bị lộ hay chỉ API bị lạm dụng, khoảng thời gian và dữ liệu phụ thuộc.
3. **Replace:** Tạo vật liệu khóa mới, triển khai quyền tối thiểu và chuyển ứng dụng sang khóa mới.
4. **Migrate:** Thay DEK/re-encrypt khi có nguy cơ DEK lộ; rewrap khi chỉ đúng với mục tiêu, đánh giá cả các bản sao cũ.
5. **Destroy:** Hủy các bản vật liệu khóa cũ còn kiểm soát được khi nghĩa vụ phục hồi cho phép.
6. **Address impact:** Xử lý dữ liệu đã bị đọc, chữ ký giả, token hợp lệ được phát hành hoặc giao dịch đã thực hiện trái phép.

**Hủy khóa không thu hồi được plaintext đã bị lấy.** Nếu kẻ tấn công có **DEK v1 và ciphertext v1**, việc hủy DEK v1 trong KMS sau sự cố không làm mất bản sao của kẻ đó.

### 10.2. Khi nào cần chọn disable trước destroy?

Trong lúc chưa biết còn dữ liệu cần phục hồi, **disable/revoke grants** có thể giảm thiểu thao tác lạm dụng ngay mà chưa phá hủy đường khôi phục được kiểm soát. Nhưng nếu chính sách sự cố yêu cầu hủy khẩn cấp do hậu quả còn lớn hơn mất dữ liệu, quyết định phải được ghi nhận rõ cùng phê duyệt rủi ro.

**Không coi “disable” là đích cuối** cho khóa bị lộ: vật liệu khóa ngoài KMS vẫn có thể tồn tại và kẻ đã có bản sao vẫn có thể sử dụng nó.

## 11. Sao lưu, HSM cluster và khả năng phục hồi

### 11.1. Những bản sao dễ bị bỏ quên

Một key có thể được sao chép hoặc sử dụng ở:

- Vùng dự phòng, region khác hoặc replica của KMS/HSM.
- HSM backup, key import/export package hoặc recovery domain được phép.
- Database backup, object versioning, file snapshot, transaction log và băng lưu trữ.
- Container image, CI/CD artifact, build cache và repository.
- Ứng dụng Java đang chạy, secret cache, heap/core dump, swap hoặc crash report.
- Máy trạm quản trị, kho secrets cũ, staging, development và hệ thống điều tra.

**Không phải tất cả bản sao đều có thể truy cập và xóa trực tiếp.** Cần xác định chủ thể kiểm soát, phạm vi bảo đảm của nhà cung cấp và những rủi ro tồn dư để ra quyết định minh bạch.

### 11.2. Restore backup sau khi đã destroy

Một rủi ro lớn là **khôi phục backup cũ** rồi vô tình đưa khóa, policy hoặc dịch vụ dùng khóa cũ quay lại hoạt động.

Cần lưu một **tombstone/record trạng thái hủy** trong hệ thống điều phối sao cho việc restore không tự khôi phục quyền sử dụng khóa đã hủy. Nếu có thể khôi phục raw key từ backup thì tuyên bố hủy phải được giới hạn chính xác theo phạm vi và thời điểm, không được coi là crypto-erasure hoàn chỉnh.

Ngược lại, nếu backup ciphertext cần được phục hồi cho nghĩa vụ kinh doanh nhưng khóa đã hủy, việc restore chỉ phục hồi được **ciphertext không đọc được**. Đó có thể là kết quả dự kiến của xóa dữ liệu, nhưng là sự cố nếu dữ liệu còn phải giữ.

### 11.3. Khóa trong HSM cluster

Với HSM, phải xem xét **quorum, domain, key replication, backup và bản sao DR**. Thao tác xóa một slot hoặc một object trên một thiết bị không tự chứng minh mọi replica đã được zeroize.

Nếu cần chứng cứ hủy, sử dụng **attestation, audit hoặc cơ chế xác nhận** do nền tảng hỗ trợ; đánh giá các giới hạn của bằng chứng. Không khẳng định đã xóa vật lý toàn bộ bản sao chỉ dựa vào phản hồi thành công của một API nếu điều đó không nằm trong hợp đồng dịch vụ.

## 12. Kiểm toán và bằng chứng hủy khóa

Sau khi destroy, tổ chức vẫn cần **metadata và bằng chứng** để giải thích quyết định, điều tra sự cố hoặc chứng minh tuân thủ. **Không giữ lại raw key** chỉ để có “bằng chứng rằng từng tồn tại khóa”.

Một hồ sơ hủy có thể ghi:

| Trường | Ví dụ | Vai trò |
| --- | --- | --- |
| **Destruction request ID** | DEL-2026-104 | Liên kết các bước phê duyệt, gọi API và kiểm tra |
| **Key ID/version** | tenant-a-dek / v7 | Xác định đúng vật liệu khóa, tránh nhầm alias |
| **Owner, tenant, environment** | payments / tenant-a / production | Trách nhiệm và phạm vi ảnh hưởng |
| **Reason** | Retention expired / compromised / migration complete | Cơ sở quyết định |
| **Dependency inventory reference** | INV-429 | Kết quả kiểm kê bản ghi, wrapped key và bản sao |
| **Approval records** | Requester, independent approver, timestamps | Separation of duties |
| **KMS/HSM operation** | Scheduled deletion / destroy version / zeroize | Hành động thật theo API |
| **Effective timestamp/status** | Pending rồi executed | Tránh nhầm đã yêu cầu với đã hủy |
| **Verification evidence** | API response ID, provider audit, readback test | Xác minh theo phạm vi kỹ thuật |
| **Residual risk** | Backup ngoài phạm vi, dữ liệu cũ đã bị lộ | Giới hạn của kết luận |

### 12.1. Mức độ xác nhận khác nhau

Phải tách những phát biểu:

- **“Đã gửi yêu cầu hủy”**: hệ thống nhận request, chưa chắc đã thực thi.
- **“KMS xác nhận vật liệu khóa đã bị hủy trong phạm vi dịch vụ”**: có chứng cứ từ KMS nhưng chưa chắc mọi bản sao bên ngoài được xử lý.
- **“Đã loại bỏ mọi đường khôi phục khóa và plaintext trong phạm vi được kiểm soát”**: cần chứng cứ bổ sung từ backup, ứng dụng, DR và inventory.
- **“Dữ liệu đã được xóa theo nghĩa vụ áp dụng”**: có thể còn yêu cầu xử lý dữ liệu vật lý, metadata và lưu giữ chứng cứ riêng ngoài việc hủy khóa.

Không báo **SUCCESS** cho cấp độ cao hơn mức thực tế có bằng chứng.

### 12.2. Sự kiện cần cảnh báo

- Một khóa được hủy hoặc lên lịch hủy **ngoài change ticket**.
- Người yêu cầu và người phê duyệt trùng nhau khi policy yêu cầu dual control.
- Vẫn có **Encrypt/Sign/Unwrap** bằng khóa đã nghỉ dùng.
- Bản mã vẫn tham chiếu tới key version nằm trong lịch hủy.
- Hủy thất bại, pending kéo dài ngoài giới hạn hoặc KMS báo trạng thái không nhất quán.
- Backup restore khiến metadata khóa đã hủy **xuất hiện trở lại**.
- Xuất key hoặc sửa IAM/policy sát thời điểm hủy ngoài quy trình.

Ghi log đủ chi tiết để điều tra nhưng tránh raw key, DEK plaintext hoặc dữ liệu khách hàng không cần thiết.

## 13. Tình huống thực tế: xóa dữ liệu tenant sau hết thời hạn lưu giữ

Một nền tảng đa tenant có:

- **Tenant A**: 1 triệu bản ghi đã mã hóa bằng AES-GCM, DEK-A được quản lý qua envelope encryption.
- **Tenant B**: 2 triệu bản ghi, dùng DEK-B riêng.
- **KMS**: Bảo vệ KEK theo miền; database lưu key ID, IV/nonce, tag và wrapped DEK.
- **Backup**: Hệ thống giữ bản sao snapshot định kỳ theo retention.

Tenant A kết thúc hợp đồng. Sau khi hết nghĩa vụ lưu trữ và được phê duyệt, đội vận hành muốn hủy DEK-A để crypto-shred dữ liệu A.

### 13.1. Quy trình đúng

1. Xác định **DEK-A có thực sự chỉ mã hóa dữ liệu của A**. Nếu DEK dùng chung với B, chưa thể hủy chỉ để xóa A.
2. Xác định **key version và bản mã liên quan**, gồm object storage, audit archive, backup và vùng DR.
3. Kiểm tra **legal hold, retention và yêu cầu khôi phục**. Nếu còn, hoãn hủy hoặc điều chỉnh kế hoạch.
4. Ngừng việc ghi dữ liệu mới của A bằng DEK-A và đóng các phiên cache sử dụng khóa.
5. Kiểm tra có hay không **DEK-A dạng rõ, DEK-A được wrap dưới KEK khác và các đường backup** còn phục hồi được.
6. Tổ chức phê duyệt; thực hiện hủy đúng DEK/version và các bản sao trong phạm vi bảo vệ.
7. Theo dõi KMS/HSM nếu thao tác có **pending period**; chỉ xác nhận destroyed khi đã có bằng chứng thực thi.
8. Kiểm thử các đường giải mã bị cấm không còn thành công; kiểm tra dữ liệu tenant B vẫn đọc được.
9. Ghi bằng chứng, rủi ro tồn dư, hoàn tất xóa dữ liệu theo chính sách và bảo vệ audit metadata cần lưu.

### 13.2. Các test case cần chạy

| Kiểm thử | Kết quả mong đợi |
| --- | --- |
| Đọc ciphertext A sau khi destruction thực thi đầy đủ | Không thể giải mã qua đường khóa đã hủy; phản hồi được kiểm soát |
| Đọc ciphertext B | Vẫn hoạt động bình thường |
| Thử tạo ciphertext mới dưới DEK-A | Bị từ chối ngay từ policy/KMS/ứng dụng |
| Khôi phục snapshot cũ | Không tự làm sống lại quyền sử dụng khóa đã hủy; nhận diện metadata/tombstone |
| Một bản wrapped DEK-A dưới KEK khác vẫn tồn tại | Preflight phải phát hiện và chặn kết luận crypto-erasure hoàn chỉnh |
| Thao tác scheduled deletion chưa đến hạn | Trạng thái là pending, **không báo destroyed** |
| KMS lỗi hoặc timeout trong lúc xóa | Kiểm tra lại trạng thái; không ghi nhận hủy thành công theo giả định |
| Legal hold được kích hoạt trước khi thực thi | Có cơ chế hoãn/hủy lịch nếu nền tảng còn cho phép; quyết định được lưu vết |
| Bản sao plaintext tồn tại ngoài miền mã hóa | Ghi rõ crypto-shredding không xử lý được bản sao đó |

**Bài học:** Thiết kế **khóa riêng theo miền retention/tenant**, không phân phối DEK tràn lan và kiểm kê backup ngay từ đầu sẽ giúp đáp ứng yêu cầu destroy an toàn hơn nhiều so với việc chỉ viết thêm một API DeleteKey khi hệ thống đã vận hành.

## 14. Những sai lầm phổ biến khi destroy key

| Sai lầm | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Đổi key alias rồi coi như đã hủy khóa cũ | Vật liệu khóa và các ciphertext phụ thuộc vẫn tồn tại | Kiểm tra key ID/version thực, theo dõi thao tác hủy vật liệu khóa |
| Disable xong báo destroyed | Có thể bật lại hoặc còn raw key ngoài hệ thống | Phân biệt trạng thái và chứng cứ hủy |
| Hủy KEK khi DEK chưa rewrap | Không thể mở DEK để đọc dữ liệu cần giữ | Kiểm kê wrapped key, rewrap và kiểm thử đọc trước |
| Hủy DEK khi dữ liệu cần retention | Mất dữ liệu không phục hồi | Thẩm định retention/legal hold, phê duyệt và thử backup |
| Chỉ xóa khóa trong database | Backup, cache, HSM replica hoặc file khác còn key | Kiểm kê và xử lý toàn bộ bản sao thuộc phạm vi |
| Xem xóa file là zeroize vật lý mọi byte | SSD/snapshot/backup có thể còn dữ liệu | Dùng kỹ thuật và quy trình xóa phù hợp với môi trường |
| Thấy API trả “pending” đã ghi success | Chưa chắc hủy thực tế, có thể cancel | Theo dõi đến executed và xác minh |
| Dùng một DEK chung cho nhiều tenant | Không thể crypto-shred một tenant độc lập | Phân vùng DEK theo phạm vi xóa hợp lý |
| Chỉ rewrap DEK khi DEK đã bị lộ | Kẻ tấn công vẫn có thể đọc ciphertext cũ | Thay DEK, re-encrypt và đánh giá sự cố dữ liệu |
| Hủy private signing key và xóa luôn public verify key | Chữ ký lịch sử khó hoặc không thể xác minh | Lưu public key/chứng cứ theo retention và chính sách |
| Hủy pepper cũ khi còn verifier phụ thuộc | Người dùng không đăng nhập được | Migrate khi đăng nhập/reset và theo dõi phiên bản |
| Không chặn ghi mới trong khi preflight destroy | Phụ thuộc mới xuất hiện sau khi đã kiểm kê | Đóng quyền, đồng bộ trạng thái, kiểm soát race condition |
| Cho một admin tự đề xuất và phê duyệt hủy khóa sản xuất | Tăng nguy cơ thao tác sai hoặc lạm dụng | Separation of duties, dual control/quorum theo policy |
| Không lưu audit vì “khóa đã bị xóa” | Không chứng minh được hành động và phạm vi xử lý | Giữ metadata/bằng chứng không bí mật theo retention |
| Cho phép fallback sang khóa cũ khi KMS hủy lỗi | Có thể phục hồi đường sử dụng khóa không được phép | Fail closed và xử lý lỗi theo state machine |

## 15. Checklist review quy trình hủy khóa

Trước khi báo hoàn tất, hãy trả lời:

1. **Định danh:** Đúng key ID/version/thuật toán/tenant/môi trường chưa, hay mới chỉ có alias?
2. **Mục đích:** Vì sao hủy, ai sở hữu khóa và ai chịu trách nhiệm phê duyệt?
3. **Tài sản:** Khóa là DEK, KEK, root, signing, MAC, pepper hay session key? Còn phụ thuộc nào?
4. **Dữ liệu:** Còn ciphertext, wrapped DEK, token, chứng chỉ, chữ ký, password verifier hoặc thông điệp nào cần khóa?
5. **Retention:** Đã xử lý legal hold, thời hạn lưu giữ, nghĩa vụ khôi phục và lịch sử xác minh chưa?
6. **Migration:** Đã rewrap/re-encrypt/reset/đổi trust đúng theo loại khóa và kiểm thử đọc dữ liệu cần giữ?
7. **Bản sao:** Đã kiểm kê DR, backup, replica, HSM cluster, secret cache, image, log và dump?
8. **Quyền:** Đã chặn thao tác mới bằng khóa cũ và cập nhật IAM/grant/cache ở mọi dịch vụ liên quan?
9. **Phê duyệt:** Có quy trình dual control hoặc kiểm soát tương ứng với mức độ nhạy cảm?
10. **Thực thi:** Đã dùng API đúng của KMS/HSM hoặc phương pháp xóa được phê duyệt? Có theo dõi pending period?
11. **Xác minh:** Chứng cứ nào chứng minh vật liệu khóa không còn dùng/khôi phục được trong phạm vi đã xác định?
12. **Phân tán:** Restore backup hoặc deploy lại có vô tình hồi sinh khóa/alias/policy cũ không?
13. **Sự cố:** Nếu khóa đã compromised, có đánh giá dữ liệu/phiên/chữ ký bị ảnh hưởng và các bản sao ngoài kiểm soát?
14. **Kiểm toán:** Đã lưu incident/change ID, phê duyệt, thời điểm, kết quả API và rủi ro tồn dư không chứa bí mật?
15. **Kết luận:** Trạng thái báo cáo là requested, pending, executed hay verified? Có đang tuyên bố vượt quá bằng chứng?

## 16. Ghi nhớ

- **Destroy key** là hủy khả năng sử dụng/khôi phục vật liệu khóa trong **phạm vi kiểm soát xác định**, không đồng nghĩa xóa một alias, một file hoặc đặt key thành Disabled.
- Hủy khóa phải theo **thứ tự an toàn**: kiểm kê phụ thuộc → xử lý retention → migration/recovery test → phê duyệt → chặn thao tác mới → hủy → xác minh → audit.
- **DEK, KEK và root key có mức ảnh hưởng khác nhau.** Hủy DEK có thể khiến ciphertext không thể đọc; hủy KEK có thể làm mất khả năng unwrap hàng loạt DEK.
- **Crypto-shredding** chỉ có hiệu lực khi không còn đường khôi phục khóa và bản sao plaintext trong phạm vi mục tiêu; dữ liệu kẻ tấn công đã sao chép trước đó không tự biến mất.
- **KMS/HSM, secret manager và Java heap** có khả năng, trạng thái và giới hạn xóa khác nhau. Luôn kiểm tra API và chứng cứ thực tế; không báo success khi mới pending.
- **Private signing key** có thể cần hủy, nhưng **public verification key/chứng chỉ** có thể phải giữ để xác minh lịch sử. **Pepper** không được hủy khi còn verifier cần dùng nó.
- **Separation of duties, least privilege, kiểm toán và phương án khôi phục** quan trọng ngang thao tác hủy kỹ thuật; sai một bước có thể gây mất dữ liệu không thể đảo ngược.

Trước khi chọn **Destroy**, hãy hỏi: **“Khóa này còn bảo vệ điều gì?”, “Có bản sao nào khiến việc hủy không đạt mục tiêu hoặc khiến dữ liệu còn cần bị mất?”, “Chúng ta sẽ chứng minh được điều gì đã thật sự bị hủy?”** Chỉ khi có câu trả lời và bằng chứng phù hợp, việc hủy mới là một bước kết thúc an toàn của vòng đời khóa.
