# Cryptoperiod

> **Chương:** Thuật ngữ cốt lõi  
> **Module:** SECURITY_KEY_MANAGEMENT_FUNDAMENTALS — Nền tảng quản lý khóa mật mã

## 1. Cryptoperiod là gì?

**Cryptoperiod (thời hạn sử dụng khóa mật mã được cho phép)** là **khoảng thời gian một khóa mật mã cụ thể được phép sử dụng cho một hoặc nhiều mục đích mật mã đã xác định**. Mục đích có thể là mã hóa dữ liệu mới, giải mã dữ liệu đã mã hóa, tạo chữ ký số, xác minh chữ ký hoặc tính và kiểm tra mã xác thực thông điệp (MAC).

Thuật ngữ này là một phần quan trọng của **key management** vì khóa không nên được sử dụng vô thời hạn chỉ vì nó vẫn tồn tại trong KMS, HSM hay cơ sở dữ liệu. Thời gian sử dụng càng dài, lượng dữ liệu và số thao tác phụ thuộc vào một khóa có thể càng lớn; nếu khóa bị lộ, phạm vi ảnh hưởng thường cũng lớn hơn.

Tuy nhiên, **hết thời gian dùng khóa để bảo vệ dữ liệu mới không nhất thiết đồng nghĩa với việc phải hủy khóa ngay**. Dữ liệu, bản sao lưu hoặc chữ ký được tạo trước đó có thể cần được giải mã hay xác minh trong thời gian dài hơn.

Ví dụ, dịch vụ thanh toán dùng khóa AES phiên bản `v1` để mã hóa giao dịch từ tháng 1 đến hết tháng 3. Từ tháng 4, dịch vụ chỉ mã hóa dữ liệu mới bằng `v2`; nhưng vẫn phải có cách giải mã giao dịch tháng 1–3 bằng `v1` khi thực hiện đối soát. Đây là lý do cryptoperiod phải được thiết kế theo **mục đích sử dụng**, thay vì chỉ đặt một ngày hết hạn chung rồi xóa khóa.

### Các ý chính

- **Cryptoperiod là thời gian khóa được phép dùng**, không đồng nghĩa với toàn bộ thời gian khóa còn được lưu trữ.
- Cùng một khóa có thể có **khoảng thời gian tạo bảo vệ mới** và **khoảng thời gian xử lý dữ liệu đã được bảo vệ** khác nhau.
- Khi hết cryptoperiod, hệ thống phải thay đổi hành vi phù hợp: chọn khóa mới, ngừng thao tác bị cấm, hạn chế truy cập, rồi hủy khóa khi không còn phụ thuộc.
- Độ dài phù hợp phụ thuộc loại khóa, thuật toán, mức độ nhạy cảm của dữ liệu, lượng sử dụng, mô hình đe dọa và yêu cầu lưu giữ; **không có một con số áp dụng an toàn cho mọi khóa**.

## 2. Hai khoảng thời gian quan trọng: originator và recipient

Trong quản lý khóa, có thể phân biệt hai giai đoạn theo vai trò của thao tác mật mã.

| Khoảng thời gian | Ý nghĩa | Ví dụ đối với AES-GCM | Ví dụ đối với chữ ký số |
| --- | --- | --- | --- |
| **Originator-usage period** (thời gian bên tạo dùng khóa) | Khóa được phép **áp dụng bảo vệ mật mã mới** | Mã hóa một bản ghi mới | Private key tạo chữ ký mới |
| **Recipient-usage period** (thời gian bên nhận dùng khóa) | Khóa được phép **xử lý hoặc kiểm tra dữ liệu đã được bảo vệ** | Giải mã bản ghi cũ | Xác minh chữ ký đã tạo |

Tên hai khoảng thời gian phản ánh **vai trò trong thao tác mật mã**, không nhất thiết là hai tổ chức riêng: cùng một backend có thể vừa mã hóa khi ghi dữ liệu vừa giải mã khi đọc dữ liệu.

Với nhiều hệ thống lưu trữ, thời gian được phép giải mã dữ liệu cũ sẽ dài hơn thời gian được phép mã hóa mới. Với chữ ký số, private key có thể chỉ được dùng ký trong một khoảng ngắn, trong khi việc xác minh chữ ký lịch sử vẫn cần public key, chứng thư số và bằng chứng tin cậy thích hợp sau đó.

### Ví dụ mốc thời gian

Các mốc sau chỉ dùng để **minh họa chính sách**, không phải khuyến nghị khoảng thời gian chuẩn:

~~~text
01/01/2027            01/04/2027                       01/04/2028
    |----------------------|----------------------------------|
    |  v1 được mã hóa mới  | v1 chỉ được giải mã dữ liệu cũ   |
    |  và giải mã dữ liệu  |                                  |
    |----------------------|----------------------------------|
                         ↑                                  ↑
                 Bắt đầu dùng v2                   Hết quyền giải mã v1
                                                    (nếu đã xử lý phụ thuộc)
~~~

Một bản sao lưu tạo trong tháng 2 vẫn có thể phụ thuộc vào `v1`. Vì vậy, ngày hết quyền giải mã phải được quyết định cùng **thời hạn giữ backup, nhu cầu phục hồi và kế hoạch di chuyển dữ liệu**. Nếu backup còn cần đọc trong năm 2029, lịch minh họa phía trên phải được điều chỉnh hoặc dữ liệu phải được chuyển sang khóa còn hợp lệ trước khi vô hiệu hóa `v1`.

> **Nguyên tắc thiết kế:** Phân biệt thao tác *tạo bảo vệ mới* (encrypt/sign/MAC generate) và thao tác *xử lý bảo vệ cũ* (decrypt/verify). Cả hai đều phải có giới hạn và quyền cụ thể.

## 3. Cryptoperiod khác gì vòng đời khóa và rotation?

Các khái niệm này liên quan chặt chẽ nhưng giải quyết những câu hỏi khác nhau.

| Khái niệm | Câu hỏi trả lời | Điều dễ nhầm |
| --- | --- | --- |
| **Cryptoperiod** | Khóa **được phép dùng cho thao tác nào, trong khoảng nào**? | Hết thời gian mã hóa mới không có nghĩa mọi thao tác đều phải dừng |
| **Key lifetime / retention** | Khóa **tồn tại hoặc được lưu giữ** đến bao giờ? | Khóa có thể còn tồn tại để giải mã dữ liệu cũ sau khi đã ngừng mã hóa mới |
| **Key rotation** | **Khi nào và bằng cách nào chuyển sang khóa mới**? | Rotation không tự mã hóa lại toàn bộ bản mã cũ |
| **Key expiration / policy cutoff** | **Khi nào quyền hoặc trạng thái sử dụng hết hiệu lực**? | Một trường `expiresAt` duy nhất có thể không phản ánh được hai nhóm thao tác |
| **Key revocation / disable** | **Khi nào phải ngừng tin cậy hoặc chặn sử dụng**? | Khóa bị lộ có thể cần thu hồi trước ngày dự kiến |
| **Key destruction** | **Khi nào được hủy vật liệu khóa**? | Xóa khóa quá sớm có thể khiến backup không thể khôi phục |
| **Certificate validity** | Chứng thư gắn public key với danh tính **có hiệu lực trong khoảng nào**? | Thời hạn chứng thư không tự định nghĩa toàn bộ cryptoperiod của private key |

Vòng đời thực tế thường gồm **tạo → cấp phát → kích hoạt → sử dụng → xoay vòng/ngừng dùng → lưu giữ có kiểm soát → hủy**. Cryptoperiod đặt các giới hạn sử dụng trong vòng đời đó.

~~~mermaid
flowchart LR
    A[Tạo khóa] --> B[Chờ kích hoạt]
    B --> C[Được phép bảo vệ dữ liệu mới]
    C --> D[Chỉ xử lý dữ liệu cũ]
    D --> E[Ngừng mọi sử dụng]
    E --> F[Hủy khi không còn phụ thuộc]
    C -->|Lộ khóa / rủi ro nghiêm trọng| X[Vô hiệu hóa khẩn cấp]
    D -->|Lộ khóa / rủi ro nghiêm trọng| X
    X --> Y[Điều tra, chuyển khóa, xử lý dữ liệu]
~~~

Không phải mọi nền tảng KMS đều có sẵn trạng thái “chỉ giải mã” cho từng khóa hoặc từng phiên bản vật liệu khóa. Khi dịch vụ KMS không hỗ trợ trực tiếp, cần thiết kế **lớp chọn khóa và kiểm tra chính sách trong ứng dụng**, kết hợp IAM/KMS policy và quy trình vận hành. Nếu chỉ tắt hẳn khóa cũ ở KMS, có thể đồng thời chặn cả giải mã dữ liệu hợp lệ.

## 4. Vì sao phải giới hạn cryptoperiod?

### 4.1. Giới hạn phạm vi khi một khóa bị lộ

Một khóa AES dùng cho nhiều năm có thể bảo vệ lượng dữ liệu rất lớn. Nếu khóa đó bị sao chép trái phép, đối tượng tấn công có khả năng giải mã mọi bản mã họ có được dưới khóa ấy, kể cả bản mã đã lưu từ nhiều năm trước.

Việc chuyển sang khóa mới theo cryptoperiod giúp **giảm lượng dữ liệu mới tiếp tục phụ thuộc vào khóa cũ**. Tuy nhiên, **rotation không làm bản mã cũ tự trở nên an toàn nếu khóa cũ đã bị lộ**. Khi có sự cố, cần xác định bản mã nào chịu ảnh hưởng và có thể phải mã hóa lại bằng khóa mới.

### 4.2. Giới hạn lượng thao tác và ràng buộc thuật toán

Một số chế độ mật mã có giới hạn an toàn liên quan tới số lần sử dụng khóa, lượng dữ liệu xử lý, độ dài bản mã hoặc cách tạo nonce. Ví dụ, **AES-GCM yêu cầu không tái sử dụng một cặp (khóa, nonce)**. Dù chưa đến ngày rotation, hệ thống vẫn phải thay khóa hoặc dừng sử dụng nếu không thể tiếp tục bảo đảm tính duy nhất của nonce hoặc đã đến giới hạn sử dụng được thiết kế.

Do đó, chính sách thực tế có thể kết hợp:

~~~text
Kết thúc quyền mã hóa mới khi:
    đã đến hạn thời gian
    HOẶC đã chạm hạn mức thao tác / dữ liệu
    HOẶC có nghi ngờ lộ khóa, sai cấu hình hoặc sự cố
    HOẶC tiêu chuẩn hoặc chính sách buộc thay khóa.
~~~

**Cryptoperiod là giới hạn theo thời gian**, còn hạn mức theo số lần dùng và dung lượng là **ràng buộc bổ sung**; cả hai cần được xét khi quyết định có tiếp tục dùng khóa hay không.

### 4.3. Giảm thời gian quyền truy cập tồn tại

Khi khóa tồn tại lâu, các tài khoản dịch vụ, nhân viên, phiên bản ứng dụng và môi trường cũ có thể giữ quyền sử dụng không còn cần thiết. Quản trị cryptoperiod buộc hệ thống định kỳ rà soát **chủ sở hữu, quyền encrypt/decrypt/sign, chính sách IAM/KMS và nhu cầu dữ liệu cũ**.

### 4.4. Bảo đảm khả năng vận hành và kiểm toán

Việc định nghĩa thời gian rõ ràng giúp tổ chức lên lịch tạo khóa mới, chuyển đổi dữ liệu, thông báo hệ thống phụ thuộc, lưu hồ sơ phê duyệt, kiểm tra backup và lập bằng chứng kiểm toán.

Mục tiêu không phải chỉ “thay khóa thường xuyên”, mà là thay **đúng thời điểm, đúng phạm vi và không làm mất dữ liệu hợp lệ**.

## 5. Xác định cryptoperiod dựa trên yếu tố nào?

Không có một quy tắc kiểu “mọi khóa phải rotation sau 30/90/365 ngày” có thể dùng nguyên xi cho mọi hệ thống. Hãy bắt đầu từ mô hình đe dọa và các yêu cầu cụ thể.

| Yếu tố | Câu hỏi thiết kế | Hướng tác động |
| --- | --- | --- |
| **Mức nhạy cảm của dữ liệu** | Khóa bảo vệ dữ liệu thông thường hay dữ liệu có hậu quả lộ lọt nghiêm trọng? | Dữ liệu rủi ro cao có thể cần thời gian bảo vệ mới ngắn hơn hoặc khóa có phạm vi nhỏ hơn |
| **Lượng dữ liệu/số thao tác** | Khóa xử lý bao nhiêu bản ghi, byte, yêu cầu ký hoặc MAC? | Lưu lượng lớn có thể đòi hỏi hạn mức và rotation sớm hơn |
| **Thuật toán và chế độ** | Có giới hạn thông điệp, nonce, block hoặc yêu cầu tiêu chuẩn riêng không? | Không được vượt giới hạn an toàn dù thời hạn vẫn còn |
| **Phạm vi dùng chung** | Một khóa bảo vệ một bản ghi, một tenant, một dịch vụ hay toàn bộ nền tảng? | Phạm vi càng rộng, thiệt hại tiềm tàng khi bị lộ càng lớn |
| **Khả năng lộ khóa** | Khóa nằm trong HSM, KMS hay thường xuyên được xuất ra RAM nhiều máy? | Khả năng tiếp xúc càng lớn, cần kiểm soát và thời hạn phù hợp hơn |
| **Thời hạn dữ liệu/backup** | Cần giải mã dữ liệu hoặc xác minh chứng cứ trong bao lâu? | Thời gian xử lý dữ liệu cũ và lưu giữ khóa có thể dài hơn thời gian bảo vệ mới |
| **Môi trường và quyền** | Production có tách khỏi dev/staging? Ai được dùng thao tác nào? | Nên tách chính sách theo môi trường, danh tính và nhiệm vụ |
| **Yêu cầu pháp lý/tiêu chuẩn** | Có quy định ngành hoặc chính sách nội bộ được áp dụng không? | Phải kiểm tra giới hạn và cách lưu hồ sơ do chính sách thực tế yêu cầu |
| **Khả năng khôi phục** | Có thể phục hồi khóa, backup và dữ liệu sau sự cố không? | Không hủy hay vô hiệu hóa dữ liệu cũ khi chưa có phương án di chuyển/khôi phục |

Hãy ghi nhận **lý do chọn thời hạn** bằng một quyết định kiến trúc có người chịu trách nhiệm, thay vì chỉ đặt một biến môi trường `KEY_TTL_DAYS` và coi như xong.

## 6. Cryptoperiod cho từng loại khóa

### 6.1. Khóa mã hóa đối xứng (AES, ChaCha20)

Khóa mã hóa dùng trực tiếp cho dữ liệu mới trong giai đoạn originator. Sau khi hết giai đoạn này, khóa cũ có thể chỉ được dùng để **giải mã bản mã cũ** trong thời gian recipient nếu chính sách cho phép.

Ví dụ: một ứng dụng tạo phiên bản khóa AES mới theo quý; ứng dụng mã hóa bằng phiên bản hiện tại và lưu định danh khóa cùng bản mã. Khi đọc, ứng dụng xác định đúng phiên bản cũ để giải mã. Cách chọn khóa theo phiên bản phải tương thích với cơ chế KMS hoặc thư viện mật mã đang sử dụng.

Trong thiết kế **một DEK cho mỗi đối tượng**, thời gian dùng DEK để mã hóa có thể rất ngắn, nhưng quyền giải mã bằng chính DEK đó vẫn cần cho tới khi đối tượng bị xóa hoặc mã hóa lại. DEK dạng rõ trong RAM lại chỉ nên tồn tại trong khoảng ngắn cần thiết cho thao tác. Đây là **ba loại thời gian khác nhau**.

### 6.2. KEK và envelope encryption

Với **envelope encryption**, khóa mã hóa dữ liệu (**DEK**) thực hiện mã hóa trực tiếp; khóa mã hóa khóa (**KEK**) bảo vệ DEK, thường nằm trong KMS/HSM.

~~~mermaid
flowchart TD
    APP[Ứng dụng] -->|Dùng DEK hiện hành| ENC[Mã hóa dữ liệu mới]
    ENC --> STORE[(Ciphertext và metadata)]
    APP -->|Gửi DEK để wrap / nhận wrapped DEK| KMS[KMS / HSM giữ KEK]
    KMS --> WDEK[Wrapped DEK]
    WDEK --> STORE
    STORE -->|Đọc dữ liệu cũ| DEC[Giải mã theo key ID / phiên bản thích hợp]
    DEC -->|Được cấp quyền unwrap| KMS
~~~

Khi cryptoperiod dùng **KEK để bọc khóa mới** kết thúc, hệ thống có thể chuyển sang KEK mới cho các DEK phát sinh về sau. Những wrapped DEK cũ vẫn cần khả năng mở bọc trong thời hạn dữ liệu còn hiệu lực.

**Rewrap DEK** là thay lớp bảo vệ DEK bằng KEK mới (nếu kiến trúc và KMS hỗ trợ) mà không phải mã hóa lại toàn bộ dữ liệu. **Re-encrypt dữ liệu** là giải mã rồi mã hóa lại dữ liệu bằng DEK khác. Hai thao tác khác nhau về chi phí và ảnh hưởng bảo mật.

Một số KMS quản lý phiên bản vật liệu khóa và tự chọn phiên bản để giải mã từ metadata trong ciphertext; một số yêu cầu ứng dụng lưu hoặc cung cấp định danh phiên bản. Cần tuân theo hợp đồng API của KMS cụ thể. **Tự động rotation của KMS không mặc nhiên chặn việc sử dụng khóa cũ, thay chính sách truy cập hay mã hóa lại dữ liệu cũ.**

### 6.3. Private key tạo chữ ký số

**Private key** tạo chữ ký phải có khoảng thời gian **được phép ký mới** rõ ràng. Khi hết thời gian này, quy trình cần chuyển sang private key mới. Hệ thống vẫn có thể cần xác minh chữ ký cũ bằng **public key** tương ứng.

Việc xác minh chữ ký lâu dài không đơn giản là kiểm tra chữ ký toán học: tùy yêu cầu nghiệp vụ, còn cần biết **chứng thư có đáng tin cậy tại thời điểm ký không, chứng thư đã bị thu hồi khi nào và có bằng chứng thời gian đáng tin cậy hay không**. Ngày hết hạn chứng thư số không tự động chứng minh chữ ký đã tạo trước đó là vô hiệu; cũng không được mặc định chữ ký cũ luôn hợp lệ mà bỏ qua trạng thái chứng thư và chính sách xác minh.

Không xuất private key khỏi HSM/KMS chỉ để hỗ trợ xác minh lịch sử: **xác minh dùng public key**, cùng chứng cứ và chính sách tin cậy phù hợp.

### 6.4. Khóa HMAC

Khóa HMAC có thể dùng để tạo MAC cho webhook hoặc thông điệp giữa các dịch vụ. Khi thay khóa, bên nhận có thể cần chấp nhận MAC tạo từ khóa cũ trong một **cửa sổ chuyển đổi có giới hạn** để xử lý yêu cầu đang truyền hoặc retry hợp lệ.

Không nên giữ khóa HMAC cũ có khả năng tạo thông điệp hợp lệ vô thời hạn. Cần kết hợp **timestamp, ID sự kiện/nonce, giới hạn thời gian chấp nhận và chống phát lại**; rotation mà vẫn chấp nhận chữ ký HMAC cũ vô hạn sẽ làm yếu mục tiêu loại bỏ khóa cũ.

### 6.5. Khóa TLS và chứng thư số

Private key dùng xác thực TLS và chứng thư số liên quan có lịch thay đổi riêng. **Thời hạn chứng thư**, **cryptoperiod của private key** và **thời hạn tồn tại của khóa phiên** là những khái niệm khác nhau. Giao thức TLS hiện đại thường tạo các bí mật phiên tạm thời; không nên đánh đồng thời hạn khóa phiên với chu kỳ thay private key trên máy chủ.

## 7. Thiết kế chính sách cryptoperiod trong hệ thống

Một bản ghi quản lý khóa nên mô tả ít nhất:

| Trường | Mục đích | Giá trị minh họa |
| --- | --- | --- |
| `keyId` / `version` | Xác định khóa hoặc phiên bản | `payment-dek-v4` |
| `purpose` | Tác vụ được phép | `ENCRYPT_DECRYPT` |
| `activatedAt` | Bắt đầu cho phép sử dụng | `2027-01-01T00:00:00Z` |
| `protectUntil` | Mốc ngừng **tạo bảo vệ mới** | `2027-04-01T00:00:00Z` |
| `processOldUntil` | Mốc ngừng **xử lý dữ liệu cũ** theo chính sách | `2028-04-01T00:00:00Z` |
| `status` | Trạng thái vận hành | `ACTIVE`, `RETIRED`, `SUSPENDED`... |
| `owner` | Nhóm hoặc dịch vụ chịu trách nhiệm | `payments-security` |
| `usageLimit` / `usageCount` | Giới hạn bổ sung theo thuật toán và rủi ro | Hạn mức do thiết kế xác định |
| `retentionDependencies` | Backup/dữ liệu cần giữ khóa | Danh sách liên kết hoặc mã chính sách |

Các trường trên là **mô hình minh họa**, không phải schema bắt buộc của mọi KMS. Hệ thống nên dùng thời gian có múi giờ xác định (thường UTC), quy định rõ mốc **bao gồm/không bao gồm**, đồng bộ đồng hồ và ghi nhận thay đổi chính sách.

### Tách kiểm tra “được phép mã hóa” và “được phép giải mã”

Ví dụ Java 17 dưới đây cho thấy hai quyết định khác nhau. Code thể hiện **lớp kiểm soát chính sách**, không thực hiện phép toán mã hóa:

~~~java
import java.time.Instant;

enum KeyState {
    ACTIVE, RETIRED, SUSPENDED, COMPROMISED, DESTROYED
}

record KeyCryptoperiod(
    String keyId,
    Instant activatedAt,
    Instant protectUntil,
    Instant processOldUntil,
    KeyState state
) {
    KeyCryptoperiod {
        if (keyId == null || keyId.isBlank()
                || activatedAt == null
                || protectUntil == null
                || processOldUntil == null
                || state == null
                || !activatedAt.isBefore(protectUntil)
                || processOldUntil.isBefore(protectUntil)) {
            throw new IllegalArgumentException("Invalid key policy");
        }
    }

    boolean mayEncryptNew(Instant now) {
        return state == KeyState.ACTIVE
                && !now.isBefore(activatedAt)
                && now.isBefore(protectUntil);
    }

    boolean mayDecryptOld(Instant now) {
        return (state == KeyState.ACTIVE
                    || state == KeyState.RETIRED)
                && !now.isBefore(activatedAt)
                && now.isBefore(processOldUntil);
    }
}

// Mã hóa mới:
// if (!currentKey.mayEncryptNew(Instant.now())) {
//     throw new SecurityException("Key not authorized for encryption");
// }
//
// Giải mã bản mã cũ:
// KeyCryptoperiod historicalKey = lookupByKeyId(ciphertext.keyId());
// if (!historicalKey.mayDecryptOld(Instant.now())) {
//     throw new SecurityException("Key not authorized for decryption");
// }
~~~

Các mốc được hiểu là khoảng thời gian **[bắt đầu, kết thúc)**: đúng thời điểm `protectUntil`, hệ thống **không được mã hóa mới** bằng khóa đó nữa. `RETIRED` trong ví dụ nghĩa là **ngừng mã hóa mới nhưng có thể giải mã cũ**; nó không tương đương trạng thái `DISABLED` của mọi nhà cung cấp KMS.

**Giới hạn của ví dụ:**

- Quyết định cuối còn phải xét **quyền IAM/KMS, quyền truy cập dữ liệu nghiệp vụ, hạn mức số thao tác, trạng thái sự cố và chính sách tenant**.
- Không tin `keyId`, `now` hay metadata do client bên ngoài cung cấp để tự quyết định quyền; dùng đồng hồ hệ thống và metadata đã xác thực.
- Khi private key/DEK bị nghi lộ, có thể phải **chặn cả giải mã**, đưa vào quy trình khôi phục có kiểm soát và đánh giá dữ liệu liên quan.
- Nếu KMS đã từ chối thao tác, ứng dụng không được “bỏ qua” kiểm tra bằng bản sao khóa ngoài luồng.
- Khi nhiều instance cùng mã hóa, phải **chuyển khóa nhất quán**, quản lý nonce và cập nhật trạng thái mà không tạo cửa sổ sử dụng khóa quá hạn.

## 8. Thực hiện rotation khi cryptoperiod sắp kết thúc

Quy trình tham khảo cho hệ thống dùng KMS/HSM và envelope encryption:

1. **Kiểm kê:** xác định khóa, mục đích, chủ sở hữu, lượng dữ liệu bảo vệ, các bản sao lưu và hệ thống phụ thuộc.
2. **Đánh giá chính sách:** kiểm tra ngày kết thúc, mức sử dụng, yêu cầu tiêu chuẩn, biến động nguy cơ và khả năng khôi phục.
3. **Tạo khóa/phiên bản kế tiếp:** dùng nguồn mật mã an toàn; thiết lập quyền KMS tối thiểu, kiểm tra khả năng mã hóa và giải mã.
4. **Chuyển luồng ghi:** ứng dụng chọn khóa mới cho tất cả dữ liệu cần bảo vệ từ mốc hiệu lực, lưu metadata đủ để tìm đúng khóa khi đọc.
5. **Giữ luồng đọc cần thiết:** duy trì khả năng giải mã các bản mã cũ trong khoảng đã phê duyệt, giới hạn quyền và giám sát truy cập.
6. **Di chuyển phụ thuộc:** rewrap DEK hoặc re-encrypt dữ liệu nếu cần; kiểm tra restore backup, dữ liệu ở các vùng và hệ thống tích hợp.
7. **Ngừng sử dụng và hủy:** chỉ xóa vật liệu khóa cũ khi đã chứng minh không còn phụ thuộc hoặc đã hết thời hạn hợp lệ; ghi lại người phê duyệt và bằng chứng kiểm tra.

~~~mermaid
sequenceDiagram
    participant Ops as Nhóm quản lý khóa
    participant KMS as KMS/HSM
    participant App as Ứng dụng
    participant Store as Kho dữ liệu
    Ops->>KMS: Tạo phiên bản v2, cấu hình quyền
    Ops->>App: Chuyển khóa mã hóa mới sang v2
    App->>KMS: Sinh / bọc DEK dưới v2
    App->>Store: Ghi bản mã mới cùng key metadata
    App->>Store: Đọc bản mã lịch sử của v1
    Store-->>App: Ciphertext + wrapped DEK cũ
    App->>KMS: Mở bọc bằng phiên bản thích hợp
    KMS-->>App: Kết quả nếu còn quyền
    Ops->>Ops: Kiểm tra backup, di chuyển và audit
    Ops->>KMS: Ngừng / hủy v1 khi đã đủ điều kiện
~~~

**Trường hợp khẩn cấp:** nếu khóa bị lộ, không đợi hết cryptoperiod. Cần xử lý sự cố ngay: cô lập danh tính bị chiếm, hạn chế hoặc vô hiệu hóa khóa theo mức rủi ro, xác định bản mã có thể đã bị đọc, chuyển khóa và mã hóa lại dữ liệu phù hợp. Sự cố có thể buộc chấp nhận gián đoạn dịch vụ có kiểm soát để ngăn tiếp tục lộ dữ liệu.

## 9. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Đặt một `expiresAt` rồi dùng cho cả encrypt và decrypt | Hết hạn ghi cũng làm mất khả năng đọc bản mã cũ | Tách chính sách bảo vệ mới và xử lý dữ liệu cũ |
| Thay alias khóa nhưng không kiểm tra dữ liệu cũ | Luồng giải mã/khôi phục có thể thất bại | Kiểm tra phiên bản, metadata và khả năng giải mã trước rollout |
| Cho phép dùng khóa cũ để mã hóa vô hạn | Dữ liệu mới vẫn phụ thuộc khóa cần nghỉ hưu | Cưỡng chế mốc kết thúc tại luồng tạo bảo vệ mới |
| Chỉ đặt thời hạn, bỏ qua giới hạn AES-GCM/nonce | Rủi ro mật mã có thể tăng trước khi hết hạn | Quản lý nonce, số lần dùng và giới hạn thuật toán |
| Xem KMS rotation là giải pháp hoàn chỉnh khi khóa lộ | Bản mã cũ đã thu thập có thể vẫn bị giải mã | Điều tra sự cố, đánh giá rewrap/re-encrypt |
| Vô hiệu hóa/xóa KEK trong lúc backup còn phụ thuộc | Không thể giải mã hoặc phục hồi dữ liệu | Kiểm kê wrapped DEK, diễn tập phục hồi, lên lịch hủy |
| Tin rằng chứng thư hết hạn thì chữ ký lịch sử vô hiệu | Kết luận sai về hồ sơ đã ký | Xác minh theo thời điểm ký, trạng thái chứng thư và bằng chứng tin cậy |
| Giữ private key cũ để “kiểm tra chữ ký” | Tăng nguy cơ lộ khóa ký | Dùng public key cùng chứng cứ xác minh lịch sử |
| Không có owner, giám sát hay cảnh báo gần hết hạn | Đổi khóa bị trễ, gián đoạn khi chuyển đổi | Có chủ sở hữu, lịch cảnh báo, quy trình và audit |
| Cho client tự gửi thời gian/key ID để vượt kiểm tra | Có thể dùng khóa quá hạn hoặc sai tenant | Dùng metadata tin cậy, kiểm tra quyền và đồng hồ hệ thống |

## 10. Tình huống thực tế: dữ liệu khách hàng cần lưu hai năm

Giả sử dịch vụ lưu hồ sơ khách hàng dùng AES-GCM để mã hóa dữ liệu; **DEK được bọc bằng KEK trong KMS**. Quy định nghiệp vụ cần giữ dữ liệu hai năm. Nhóm kỹ thuật định nghĩa rằng khóa dùng để **bọc DEK mới** phải được thay định kỳ; các khóa cũ vẫn có thể cần mở bọc dữ liệu còn trong thời hạn lưu giữ.

**Tại thời điểm chuyển KEK từ `v1` sang `v2`:**

- Dịch vụ ghi mới yêu cầu KMS dùng `v2` cho các wrapped DEK được tạo tiếp theo.
- Những hồ sơ cũ tiếp tục chứa metadata cần thiết để KMS mở bọc bằng phiên bản phù hợp.
- Luồng đọc chỉ được phép giải mã hồ sơ mà người gọi có quyền truy cập; có quyền dùng KEK không thay thế kiểm tra quyền nghiệp vụ.
- Đội vận hành đánh giá có cần **rewrap** các wrapped DEK cũ, đặc biệt khi có nghi ngờ khóa bị lộ hoặc muốn chấm dứt phụ thuộc vào `v1`.
- Trước khi vô hiệu hóa `v1`, nhóm kiểm tra restore từ backup, dữ liệu lâu năm và các vùng triển khai. Nếu còn dữ liệu hợp lệ không thể mở bọc sau khi tắt `v1`, kế hoạch phải được điều chỉnh.

**Nếu đến hạn dùng `v1` nhưng `v2` chưa sẵn sàng:** không âm thầm cho phép mọi request tiếp tục dùng `v1` vô thời hạn. Cần kích hoạt quy trình xử lý ngoại lệ có phê duyệt, cân nhắc rủi ro và cảnh báo, hoặc tạm dừng thao tác bảo vệ mới theo thiết kế an toàn của hệ thống.

**Nếu `v1` bị lộ:** phải đánh giá khả năng kẻ tấn công đã lấy wrapped DEK và ciphertext, xác định phạm vi dữ liệu, hạn chế quyền, chuyển khóa và rewrap/re-encrypt khi cần. Chỉ đổi KEK cho bản ghi mới không thể loại bỏ ảnh hưởng của dữ liệu cũ đã bị thu thập.

Tình huống này cho thấy **cryptoperiod phải đi cùng chính sách retention, quyền truy cập, kiểm toán và khả năng phục hồi**, vì thời điểm ngừng một thao tác và thời điểm hủy khóa thường khác nhau.

## 11. Checklist trước khi áp dụng vào production

- [ ] Đã xác định khóa dùng cho mã hóa, giải mã, ký, xác minh, HMAC hay bọc khóa?
- [ ] Có thời gian **được phép tạo bảo vệ mới** và thời gian **được phép xử lý dữ liệu cũ** theo từng mục đích?
- [ ] Đã nêu lý do chọn thời hạn dựa trên rủi ro, loại khóa, lưu lượng và yêu cầu áp dụng?
- [ ] Đã xét hạn mức thuật toán, số lần dùng và quy tắc nonce ngoài lịch theo thời gian?
- [ ] Có key ID/version hoặc metadata thích hợp để đọc dữ liệu cũ sau rotation?
- [ ] Đã tách quyền KMS cho encrypt/decrypt/sign và quyền quản trị theo nguyên tắc ít quyền nhất?
- [ ] Đã có cảnh báo trước hạn, người phụ trách và quy trình chuyển đổi khi khóa mới lỗi?
- [ ] Đã thử đọc dữ liệu cũ, mở backup và phục hồi sau rotation?
- [ ] Đã phân biệt rewrap DEK với re-encrypt dữ liệu, và đánh giá trường hợp khóa bị lộ?
- [ ] Đã xác định điều kiện ngừng sử dụng, thu hồi, lưu giữ, hủy khóa và bằng chứng kiểm toán?
- [ ] Có cách ngăn dùng khóa quá hạn ngay cả khi nhiều ứng dụng hoặc instance chạy song song?

## 12. Câu hỏi tự kiểm tra

**1. Cryptoperiod có phải là thời gian từ khi sinh khóa đến khi xóa khóa không?**  
Không. Cryptoperiod là khoảng thời gian khóa được phép sử dụng cho một mục đích. Khóa có thể được tạo trước khi có hiệu lực và có thể được lưu giữ để xử lý dữ liệu cũ sau khi ngừng bảo vệ dữ liệu mới.

**2. Vì sao cần tách originator-usage period và recipient-usage period?**  
Vì khóa có thể phải ngừng dùng mã hóa/ký mới trong khi dữ liệu/chữ ký cũ vẫn cần giải mã hoặc xác minh. Tách hai khoảng tránh vừa kéo dài quyền không cần thiết vừa làm mất khả năng đọc dữ liệu.

**3. Khi KEK được rotation, mọi DEK và ciphertext có tự được mã hóa lại không?**  
Không. Điều đó phụ thuộc sản phẩm KMS và kiến trúc. Hệ thống có thể cần rewrap DEK; nếu DEK bị lộ hoặc dữ liệu phải thay khóa mã hóa trực tiếp thì có thể cần re-encrypt.

**4. Tại sao chưa đến ngày kết thúc cryptoperiod vẫn có thể phải thay khóa sớm?**  
Vì khóa có thể bị lộ, chính sách thay đổi, đạt hạn mức thao tác hoặc xuất hiện nguy cơ tái sử dụng nonce khiến điều kiện an toàn không còn được bảo đảm.

**5. Chứng thư ký số hết hạn có làm mọi chữ ký đã tạo trước đó vô hiệu?**  
Không tự động. Việc xác minh chữ ký lịch sử cần xem chính sách tin cậy, thời điểm ký đáng tin cậy, tình trạng chứng thư và bằng chứng liên quan.

**6. Có thể xóa phiên bản khóa cũ ngay sau khi chuyển sang khóa mới không?**  
Chỉ khi đã xác minh không còn dữ liệu, wrapped DEK, backup hay quy trình hợp lệ cần đến nó. Nếu chưa, phải di chuyển phụ thuộc hoặc giữ khóa dưới quyền hạn được kiểm soát.

## Ghi nhớ

**Cryptoperiod xác định khi nào và cho mục đích nào một khóa mật mã còn được phép sử dụng.** Trong key management, thời gian **tạo bảo vệ mới** thường khác thời gian **xử lý dữ liệu đã được bảo vệ**. Thiết kế cryptoperiod hiệu quả phải gắn với loại khóa và thuật toán, giới hạn sử dụng, KMS/HSM, envelope encryption, rotation, kiểm soát truy cập, kiểm toán, lưu giữ dữ liệu, khả năng khôi phục và quy trình thu hồi/hủy. Đặt ngày hết hạn chỉ là một phần nhỏ của việc quản lý thời gian sử dụng khóa an toàn.
