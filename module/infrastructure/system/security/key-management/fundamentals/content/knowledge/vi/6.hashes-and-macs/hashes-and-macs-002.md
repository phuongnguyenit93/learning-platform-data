# SHA-256 (Secure Hash Algorithm 256-bit)

## 1. SHA-256 là gì?

**SHA-256** là một **hàm băm mật mã (cryptographic hash function)** thuộc họ **SHA-2**. Nó nhận dữ liệu có độ dài thay đổi và tạo ra một **giá trị băm (hash/digest) dài cố định 256 bit = 32 byte**.

~~~text
Dữ liệu đầu vào bất kỳ (byte[])
             |
             v
           SHA-256
             |
             v
      Digest 256 bit (32 byte)
~~~

Ví dụ, chuỗi ASCII **abc** có giá trị SHA-256 ở dạng hexadecimal:

~~~text
Input (UTF-8): "abc"
SHA-256:
ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
~~~

Digest trên có **64 ký tự hex** vì mỗi byte được biểu diễn bằng hai ký tự hex. Đó là cách **hiển thị 32 byte**, không phải 64 byte dữ liệu băm mới.

SHA-256 xuất hiện trong kiểm tra tính toàn vẹn của tệp, cấu trúc dữ liệu định danh nội dung, chữ ký số, HMAC, hàm dẫn xuất khóa và nhiều giao thức bảo mật. Trong chương **Hash và MAC** của module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, SHA-256 là nền tảng để hiểu cách kết hợp **hash, khóa đối xứng/bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, kiểm soát truy cập và kiểm toán**.

> **Phân biệt cốt lõi:** SHA-256 **không phải thuật toán mã hóa, không dùng khóa bí mật và không tự xác thực người gửi**. Muốn bảo vệ một thông điệp trước việc kẻ tấn công tự sửa cả dữ liệu lẫn digest, phải sử dụng **HMAC, chữ ký số hoặc cơ chế xác thực phù hợp**.

## 2. Những thuộc tính bảo mật của SHA-256

| Thuộc tính | Ý nghĩa | Minh họa |
|---|---|---|
| **Deterministic** (xác định) | Cùng một dãy byte đầu vào cho cùng một digest | Hash lại cùng tệp nguyên vẹn cho kết quả giống nhau |
| **Fixed-length output** | Digest luôn là 256 bit | Hash tệp 1 KB hoặc 1 GB đều tạo 32 byte |
| **Preimage resistance** | Khi chỉ có digest, rất khó tìm một đầu vào tạo ra digest ấy | Không thể xem digest là cách nén có thể giải mã |
| **Second-preimage resistance** | Cho trước một thông điệp, rất khó tìm thông điệp khác cho cùng digest | Khó thay thế tài liệu cụ thể mà giữ nguyên hash |
| **Collision resistance** | Khó tìm **bất kỳ hai** thông điệp khác nhau có cùng digest | Chống tạo cặp tài liệu có cùng hash theo cách có chủ đích |
| **Avalanche effect** | Thay một ít bit đầu vào thường làm digest thay đổi lớn | Một byte khác có thể cho chuỗi hex hoàn toàn khác |

Về mô hình tấn công tổng quát, SHA-256 có đầu ra 256 bit:

- **Tìm preimage** bằng vét cạn lý tưởng có độ khó xấp xỉ **2²⁵⁶** lần thử.
- **Tìm collision** bằng birthday attack lý tưởng có độ khó xấp xỉ **2¹²⁸** lần thử.
- **Tìm second preimage** cho một thông điệp ngắn, thông thường được mô tả ở mức khoảng **2²⁵⁶** trong mô hình tổng quát; độ dài thông điệp và cấu trúc thuật toán có thể ảnh hưởng phân tích chi tiết.

Các số trên là **mức tham chiếu bảo mật lý thuyết**, không phải cam kết mọi ứng dụng dùng SHA-256 đều có mức an toàn ấy. Lỗi xác thực, mật khẩu yếu, rò khóa HMAC, JSON không thống nhất, thiếu kiểm tra chứng chỉ hoặc lạm dụng quyền KMS có thể phá hệ thống mà không cần tìm collision.

### 2.1. Có phải hai đầu vào khác nhau luôn cho hai digest khác nhau?

**Không.** SHA-256 ánh xạ vô số dãy byte vào tập hữu hạn **2²⁵⁶** digest, nên về nguyên lý có các cặp dữ liệu khác nhau cùng hash. Thuộc tính bảo mật là **khó tìm ra** collision hữu ích, chứ không phải collision không tồn tại.

Một digest 256 bit cũng **không chứng minh dữ liệu đã được tạo bởi một chủ thể xác định**: bất kỳ ai biết dữ liệu đều có thể tính SHA-256 giống nhau.

### 2.2. Hash không đảo ngược có đồng nghĩa giữ bí mật không?

**Không.** Đầu vào có entropy thấp có thể bị đoán bằng cách thử các ứng viên:

~~~text
Kẻ tấn công biết SHA256("123456")?
  Thử "12345"  -> SHA-256 -> không khớp
  Thử "123456" -> SHA-256 -> khớp
~~~

Vì vậy, lưu **SHA-256(password)** không đủ để bảo vệ mật khẩu người dùng; cần **password hashing/KDF có salt và chi phí tính toán**, chẳng hạn **Argon2id**, scrypt hoặc PBKDF2 theo yêu cầu và chính sách hệ thống.

## 3. SHA-256 xử lý dữ liệu như thế nào?

SHA-256 là hàm băm xây dựng trên **cấu trúc lặp kiểu Merkle–Damgård**, với hàm nén xử lý các khối dữ liệu. Ý tưởng ở mức kiến trúc:

1. Đọc **đúng dãy byte đầu vào**.
2. **Padding:** thêm bit 1, các bit 0 cần thiết và biểu diễn độ dài thông điệp ban đầu theo chuẩn để tổng độ dài là bội của **512 bit**.
3. Chia thông điệp đã padding thành những **khối 512 bit (64 byte)**.
4. Dùng **trạng thái khởi tạo 256 bit**, chia thành tám từ 32 bit.
5. Với mỗi khối, xây dựng lịch thông điệp và chạy **64 vòng** biến đổi bit/từ 32 bit, kết hợp trạng thái với các hằng số của thuật toán.
6. Sau khối cuối, ghép tám từ trạng thái tạo **digest 256 bit**.

~~~mermaid
flowchart LR
    A["Input bytes"] --> B["Padding + độ dài"]
    B --> C["Chia khối 512 bit"]
    I["Trạng thái khởi tạo 256 bit"] --> D["Hàm nén 64 vòng / khối"]
    C --> D
    D --> E["Trạng thái sau mọi khối"]
    E --> F["Digest 256 bit"]
~~~

SHA-256 chuẩn định nghĩa cách biểu diễn độ dài thông điệp (trường độ dài 64 bit khi padding) và chỉ làm việc trên đầu vào trong giới hạn đã quy định. Ứng dụng thông thường sử dụng **thư viện mật mã chuẩn**; không tự triển khai các vòng bitwise để dùng trong sản xuất.

Các điểm kỹ thuật đáng nhớ:

- **SHA-256** và **SHA-512** đều thuộc họ SHA-2 nhưng không chỉ khác nhau bởi việc cắt digest.
- **SHA-256** là thuật toán băm **không khóa**; nó không biết người nào đã nhập dữ liệu.
- **SHA-256 là cơ chế băm**, không phải **trình tạo số ngẫu nhiên mật mã (CSPRNG)** hay cơ chế quản lý khóa.
- Hash một chuỗi ký tự thực chất là hash **byte** sau khi mã hóa ký tự. Hai biểu diễn Unicode khác nhau có thể cho hash khác nhau dù nhìn giống nhau.

## 4. Phân biệt hash, checksum, MAC, mã hóa và chữ ký số

| Cơ chế | Có khóa bí mật? | Tính năng chính | Có xác thực chủ thể tạo dữ liệu không? |
|---|---|---|---|
| **SHA-256** | Không | Digest, chống tìm collision/preimage trong mô hình mật mã | **Không** |
| **CRC32/checksum thường** | Không | Phát hiện lỗi ngẫu nhiên, truyền/lưu dữ liệu | Không; không được thiết kế chống sửa đổi có chủ đích |
| **HMAC-SHA-256** | **Có, khóa đối xứng** | Xác thực thông điệp giữa các bên cùng biết khóa | Có thể xác thực bên **nắm khóa**, nhưng không phân biệt độc lập các bên cùng giữ khóa |
| **AES-GCM** | **Có, khóa đối xứng** | Mã hóa và xác thực bản mã/AAD (AEAD) | Xác thực theo khóa và ngữ cảnh, không tự là chữ ký số |
| **ECDSA với SHA-256** | **Có, private key để ký**; public key để verify | Chữ ký số kiểm chứng thông điệp bằng khóa công khai | Có khi public key được gắn với danh tính đáng tin |
| **KDF dựa trên HMAC-SHA-256** | Có bí mật đầu vào theo mục đích KDF | Dẫn xuất khóa mới | Bản thân KDF không là cơ chế xác thực thông điệp |

**Ví dụ:** Một đối tượng lưu trữ có digest SHA-256, và client tải cả tệp lẫn digest từ cùng một máy chủ vừa bị xâm phạm. Kẻ tấn công có thể **thay cả tệp và digest**. Kiểm tra SHA-256 vẫn qua vì digest khớp với dữ liệu mới. Muốn chứng minh tính xác thực cần **digest từ một kênh đáng tin, manifest có chữ ký số, HMAC hoặc cơ chế bảo vệ khác**.

## 5. Kiểm tra tính toàn vẹn bằng SHA-256

Một trường hợp sử dụng phù hợp là **kiểm tra một tệp có khớp chính xác với digest tham chiếu đã đáng tin hay không**.

~~~text
Bên phát hành đáng tin:
  file.zip -> SHA-256 -> expectedDigest

Bên nhận:
  download file.zip -> SHA-256 -> actualDigest

Kiểm tra:
  actualDigest == expectedDigest ?
      Có  -> byte của file khớp digest tham chiếu
      Không -> file sai hoặc đã bị thay đổi
~~~

Quy trình nên lưu ý:

1. Lấy **digest tham chiếu từ nguồn có xác thực**, ví dụ manifest có chữ ký đã verify bằng public key tin cậy.
2. Hash **đúng dãy byte của file**, không hash tên file hoặc nội dung đã được chuyển đổi tùy tiện.
3. So sánh đầy đủ digest theo định dạng hex/base64 được chuẩn hóa.
4. Xác nhận **file, phiên bản, thuật toán, thời điểm và mục đích** trùng với metadata đáng tin.
5. Nếu digest không khớp, **không** tiếp tục tải/chạy/cài đặt dữ liệu như thể đã xác thực.

Khi so sánh một digest công khai với giá trị tham chiếu, so sánh thông thường đủ cho yêu cầu đối chiếu cơ bản. Khi so sánh **authentication tag/MAC**, nên dùng phép so sánh được thiết kế để giảm rò rỉ thông tin theo thời gian thực thi.

### 5.1. Một hash của nội dung có thể dùng làm định danh không?

SHA-256 thường được dùng trong **content-addressable storage** hoặc deduplication: định danh dữ liệu dựa trên hash nội dung. Đây là cơ chế tiện lợi để kiểm tra có cùng byte, nhưng không tự xác định **quyền sở hữu, quyền truy cập, danh tính người gửi hoặc độ đáng tin của nguồn**.

Nếu dữ liệu được kiểm tra có độ entropy thấp, công khai digest có thể giúp suy đoán nội dung qua việc thử ứng viên. Không tự coi digest là **mã ẩn danh an toàn tuyệt đối** cho email, số điện thoại, mật khẩu hoặc dữ liệu nhạy cảm.

## 6. SHA-256 trong chữ ký số bất đối xứng

Các thuật toán chữ ký số thường ký trên một **giá trị băm của thông điệp** theo chuẩn thuật toán. Chẳng hạn, trong Java:

- **SHA256withECDSA**: provider hash thông điệp bằng SHA-256 rồi dùng ECDSA để tạo chữ ký.
- **RSASSA-PSS với SHA-256**: sử dụng SHA-256 trong sơ đồ ký RSA-PSS với các tham số nhất quán, bao gồm MGF và salt length theo giao thức.
- Một số API **KMS/HSM Sign** nhận **toàn thông điệp** và tự hash; API khác nhận **digest đã băm**. Phải biết rõ API đang mong đầu vào nào để tránh double hashing.

~~~mermaid
flowchart LR
    M["Thông điệp m"] --> H["SHA-256(m)"]
    H --> S["Thuật toán ký + private key"]
    S --> SIG["Chữ ký"]
    M --> V["Bên xác minh"]
    SIG --> V
    P["Public key đáng tin"] --> V
    V --> A{"Chữ ký hợp lệ?"}
    A -->|Có| K["Kiểm tra quyền, thời hạn, ngữ cảnh"]
    A -->|Không| R["Từ chối"]
~~~

**Không đồng nhất SHA-256 với ECDSA.** SHA-256 tạo digest và không yêu cầu key; ECDSA dùng private key để ký và public key để xác minh. Ngay cả khi verify trả về true, ứng dụng vẫn phải kiểm tra **chứng chỉ, danh tính, trạng thái thu hồi, thời hạn, quyền nghiệp vụ và chống replay**.

### 6.1. Phải ký chính xác byte nào?

Ví dụ hai chuỗi JSON sau có thể cùng ý nghĩa nghiệp vụ nhưng dãy byte khác:

~~~json
{"amount":1000,"currency":"VND"}
~~~

~~~json
{ "currency": "VND", "amount": 1000 }
~~~

SHA-256 của chúng sẽ khác nhau. Chữ ký của chuỗi thứ nhất **không tự xác minh cho chuỗi thứ hai**. Hệ thống phải quy định **canonicalization** hoặc ký một dạng byte đã chuẩn hóa rõ ràng. Điều này đặc biệt quan trọng khi nhiều ngôn ngữ hoặc dịch vụ ký/xác minh cùng một giao dịch.

Thông điệp đã ký nên ràng buộc **mã giao dịch, phiên bản, danh tính hoặc tenant, mục đích, thời điểm và nonce nghiệp vụ** nếu giao thức cần chống tráo đổi ngữ cảnh hoặc replay.

## 7. HMAC-SHA-256: khi hash cần xác thực bằng khóa bí mật

**HMAC (Hash-based Message Authentication Code)** xây dựng một **MAC có khóa bí mật** từ hàm hash như SHA-256. **HMAC-SHA-256** tạo tag 256 bit (32 byte) trước khi có cắt ngắn theo quy định giao thức.

Ký hiệu khái niệm:

\[
\operatorname{HMAC}_K(m)
= H\big((K' \oplus \mathrm{opad}) \parallel
H((K' \oplus \mathrm{ipad}) \parallel m)\big)
\]

Trong đó H là SHA-256, K' là khóa đã chuẩn hóa theo quy tắc HMAC, ipad/opad là các hằng số đệm và m là dãy byte thông điệp. **Thư viện HMAC sẽ thực hiện toàn bộ phép tính; ứng dụng không tự lắp ghép byte bằng công thức.**

~~~text
                 Khóa HMAC bí mật K
                         |
Thông điệp m ----------> HMAC-SHA-256 ----> Tag (32 byte)
                                                 |
Người nhận cùng có K ----> HMAC-SHA-256(m) --------+--> So sánh tag
                                                     khớp / không khớp
~~~

Tình huống điển hình: webhook giữa hai backend cùng sở hữu shared secret. Bên gửi tính HMAC của nội dung byte chính xác; bên nhận tính lại và chỉ xử lý khi tag hợp lệ.

**HMAC-SHA-256 khác SHA-256(message):**

| Tiêu chí | SHA-256 | HMAC-SHA-256 |
|---|---|---|
| Đầu vào bí mật | Không có | Khóa K |
| Ai tính được kết quả? | Bất kỳ ai có thông điệp | Người có khóa K |
| Có chứng minh nguồn gửi theo bí mật chia sẻ? | Không | Có thể chứng minh người gửi biết K theo mô hình tin cậy |
| Chống sửa đổi có chủ đích | Không nếu đối phương thay được cả dữ liệu và digest | Có, nếu K bí mật và giao thức dùng đúng |
| Lĩnh vực sử dụng | Digest, kiểm tra nội dung, thành phần chữ ký/KDF | API authentication, webhook signatures, KDF |
| Quản lý vòng đời khóa | Không có khóa SHA-256 riêng | Cần sinh, cấp phát, lưu, xoay, thu hồi, hủy **HMAC key** |

### 7.1. Khóa HMAC và kiểm soát truy cập

Khóa HMAC là **symmetric secret key**, không phải chính digest SHA-256. Trong triển khai thực tế:

- Sinh khóa bằng **CSPRNG** với entropy đầy đủ, ví dụ **32 byte ngẫu nhiên** cho HMAC-SHA-256 nếu phù hợp chính sách.
- Cấp phát qua **secret store, KMS hoặc HSM** cùng danh tính dịch vụ đã xác thực; không hard-code vào source/repository/image.
- Gắn **key ID/version, mục đích, môi trường, đối tác/tenant** và quyền sử dụng.
- Tránh dùng cùng một secret tùy tiện cho **HMAC, AES-GCM, JWT và mục đích khác**. Khi cần nhiều khóa từ một bí mật chất lượng cao, dùng KDF và domain separation theo giao thức.
- Phân tách quyền **GenerateMac/VerifyMac** nếu KMS cung cấp, quyền quản trị policy, rotation và deletion.
- Audit thao tác bất thường nhưng không ghi **secret key, bearer token hoặc payload nhạy cảm** vào log.

### 7.2. HMAC không tự chống replay

Một HMAC hợp lệ của thông điệp **vẫn hợp lệ khi bị phát lại nguyên vẹn**. Để chống replay, cần thêm thông tin được MAC xác thực như **timestamp, nonce yêu cầu, request ID, phiên bản giao thức hoặc sequence number** và kiểm tra **cửa sổ thời gian/trạng thái đã dùng** ở bên nhận.

Ví dụ cấu trúc dữ liệu được ký MAC:

~~~text
"v1\n" ||
timestamp_utc || "\n" ||
request_id || "\n" ||
tenant_id || "\n" ||
method || "\n" ||
path || "\n" ||
hex(SHA256(raw_body))
~~~

Đây chỉ là **mẫu giao thức minh họa**. Ứng dụng phải định nghĩa quy tắc mã hóa byte, thứ tự trường, escaping, độ dài, canonicalization và cách kiểm tra request ID; không lấy việc nối chuỗi tùy tiện làm chuẩn bảo mật. Timestamp/nonce đã được HMAC xác thực chỉ ngăn replay khi bên nhận **thực sự kiểm tra** thời gian và sự trùng lặp.

## 8. Rủi ro length-extension: vì sao không tự ghép secret vào SHA-256?

SHA-256 có cấu trúc lặp và hỗ trợ khả năng xử lý thông điệp theo khối. Với cách thiết kế **MAC tự chế** như:

~~~text
Tag = SHA256(secret_key || message)
~~~

một kẻ có tag và nội dung message có thể khai thác **length-extension** trong một số mô hình nếu đoán được độ dài của secret, để tạo tag cho thông điệp mở rộng chứa padding thích hợp mà không biết secret.

**Điểm dễ nhầm:** Kẻ tấn công không cần giải được SHA-256; vấn đề là **cách dùng SHA-256 như một MAC không đúng**.

Không thay bằng **SHA256(message || secret)** rồi mặc định coi là MAC an toàn; các công thức ghép đơn giản không có những bảo đảm, chuẩn hóa và phân tích bảo mật như HMAC, và còn phụ thuộc khả năng collision/định dạng đầu vào.

**Cách đúng:** dùng **HMAC-SHA-256** qua API chuẩn, không tự tạo MAC bằng cách nối secret trước/sau thông điệp. HMAC được thiết kế để tránh lớp lỗi length-extension trên.

Tương tự, **SHA-256(data || salt)** không là cơ chế xác thực nếu salt công khai; salt không phải HMAC key và không đóng vai trò bí mật chia sẻ.

## 9. SHA-256 trong KDF và mật khẩu: cùng tên, mục đích khác nhau

SHA-256 còn xuất hiện trong một số **Key Derivation Function (KDF)**. Cần phân biệt **dẫn xuất khóa từ bí mật mật mã** với **hash mật khẩu người dùng**.

| Nhu cầu | Công cụ phù hợp | Vì sao |
|---|---|---|
| Tính digest tài liệu | **SHA-256** | Không yêu cầu secret, dùng để kiểm tra byte |
| Xác thực thông điệp giữa hai dịch vụ có shared secret | **HMAC-SHA-256** | MAC có khóa bí mật |
| Dẫn xuất nhiều khóa từ một bí mật mật mã chất lượng cao | **HKDF-SHA-256** | Extract/expand, domain separation bằng salt/info |
| Lưu mật khẩu người dùng | **Argon2id** hoặc password KDF phù hợp | Chống thử mật khẩu hàng loạt nhờ chi phí tính toán/bộ nhớ |
| Môi trường bắt buộc PBKDF2 | **PBKDF2-HMAC-SHA-256** với salt và số vòng phù hợp | Tăng chi phí kiểm tra ứng viên mật khẩu theo cấu hình |
| Mã hóa dữ liệu | **AES-GCM** với DEK | SHA-256 không mã hóa hay giải mã |

### 9.1. HKDF-SHA-256

**HKDF** dựa trên HMAC, thường được mô tả bằng hai giai đoạn:

~~~text
IKM (input keying material) + salt
                |
          HKDF-Extract
                |
              PRK
                |
        HKDF-Expand(info, L)
                |
       Output Key Material
       |           |           |
     ENC key     MAC key    other key
~~~

**Info** có thể ràng buộc phiên bản giao thức, mục đích, tenant hoặc vai trò của khóa. Việc ràng buộc ngữ cảnh giúp **tách khóa theo mục đích** thay vì dùng cùng một khóa thô cho nhiều thuật toán.

HKDF **không tự biến mật khẩu dễ đoán thành khóa mạnh**. Khi đầu vào là mật khẩu người dùng, trước tiên cần password KDF thích hợp. HKDF thường dùng với input keying material có entropy phù hợp (ví dụ bí mật từ giao thức trao đổi khóa).

### 9.2. Vì sao không lưu SHA256(password)?

Mật khẩu thường có entropy thấp hơn rất nhiều so với 256 bit đầu ra. Kẻ tấn công có thể thử hàng triệu ứng viên phổ biến bằng cách hash từng ứng viên và so sánh. Thêm **salt** giúp tránh dùng chung hash và giảm tác dụng của bảng tra cứu sẵn, nhưng **một vòng SHA-256 vẫn quá nhanh** để làm giải pháp lưu mật khẩu chung.

Hệ thống nên lưu **salt riêng cho từng tài khoản cùng đầu ra của password hashing/KDF đã được cấu hình phù hợp**, cộng metadata thuật toán và tham số để sau này nâng cấp. Không tự chế **SHA256(salt || password)** như một phương án tương đương Argon2id.

## 10. Java JCA: tính SHA-256 và xác thực HMAC-SHA-256

Java cung cấp **MessageDigest** cho SHA-256 và **Mac** cho HMAC-SHA-256. Ví dụ Java 17+ sau có thể chạy độc lập; khóa HMAC được sinh ngẫu nhiên để minh họa và chỉ tồn tại trong bộ nhớ của tiến trình demo.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class Sha256AndHmacDemo {

    static byte[] sha256(byte[] input) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        return digest.digest(input);
    }

    static byte[] hmacSha256(byte[] secret, byte[] message)
            throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return mac.doFinal(message);
    }

    static boolean verifyMac(
            byte[] secret, byte[] message, byte[] receivedTag)
            throws Exception {
        byte[] expectedTag = hmacSha256(secret, message);
        // Giảm rủi ro timing leak khi so sánh authentication tag.
        return MessageDigest.isEqual(expectedTag, receivedTag);
    }

    public static void main(String[] args) throws Exception {
        // Test vector nổi tiếng: SHA-256("abc").
        byte[] digest = sha256("abc".getBytes(StandardCharsets.UTF_8));
        String actualHex = HexFormat.of().formatHex(digest);
        String expectedHex =
            "ba7816bf8f01cfea414140de5dae2223b00361"
          + "a396177a9cb410ff61f20015ad";

        if (!expectedHex.equals(actualHex)) {
            throw new IllegalStateException("SHA-256 test vector mismatch");
        }

        // Demo một shared secret cho HMAC; không hard-code secret.
        byte[] secret = new byte[32];
        new SecureRandom().nextBytes(secret);

        byte[] message = "tenant=42;order=123;amount=5000"
            .getBytes(StandardCharsets.UTF_8);
        byte[] tag = hmacSha256(secret, message);

        boolean originalAccepted = verifyMac(secret, message, tag);
        byte[] tampered = "tenant=42;order=123;amount=9000"
            .getBytes(StandardCharsets.UTF_8);
        boolean tamperedAccepted = verifyMac(secret, tampered, tag);

        if (!originalAccepted || tamperedAccepted) {
            throw new IllegalStateException("HMAC verification error");
        }

        System.out.println("SHA-256 test vector OK");
        System.out.println("HMAC verification OK");

        // Giảm thời gian secret tồn tại ở một mảng byte có thể kiểm soát.
        Arrays.fill(secret, (byte) 0);
    }
}
~~~

**Giải thích:**

1. **MessageDigest.getInstance("SHA-256")** tạo hash không khóa. Kết quả là **byte[32]**, có thể đổi sang hex để lưu hoặc hiển thị.
2. **Mac.getInstance("HmacSHA256")** là MAC với **secret key**. HMAC không tương đương một phép gọi MessageDigest rồi nối khóa.
3. Khi verify HMAC, **tự tính lại tag từ cùng secret và chính xác byte của thông điệp**. Dùng **MessageDigest.isEqual** để giảm khác biệt thời gian so sánh; vẫn cần kiểm tra độ dài tag, khóa đúng phiên bản và chính sách giao thức.
4. **MessageDigest** và **Mac** là các đối tượng có trạng thái; không dùng chung một instance qua nhiều thread mà không đồng bộ. Ví dụ tạo instance mới cho mỗi lời gọi.
5. **Các bản sao secret trong SecretKeySpec/provider/JVM có thể tồn tại** sau khi xóa mảng ban đầu; thao tác **Arrays.fill** không bảo đảm xóa sạch mọi bản sao bí mật trong bộ nhớ. Đưa vào sản xuất cần cơ chế bảo vệ khóa phù hợp.
6. Trong hệ thống thật, secret nên ở **KMS/HSM hoặc secret store**; một số KMS có API **GenerateMac/VerifyMac** thực hiện HMAC mà không xuất key material. Nếu ứng dụng tự tính HMAC, cần kiểm soát đường cấp phát và vòng đời secret.

### 10.1. Kiểm tra SHA-256 cho tệp lớn bằng streaming

Không cần nạp toàn bộ tệp vào RAM. Tạo **MessageDigest** rồi cập nhật bằng từng khối:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;

public final class FileSha256 {
    public static String hash(Path path) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");

        try (InputStream in = Files.newInputStream(path)) {
            byte[] buffer = new byte[8192];
            int n;
            while ((n = in.read(buffer)) != -1) {
                if (n > 0) {
                    md.update(buffer, 0, n);
                }
            }
        }

        return HexFormat.of().formatHex(md.digest());
    }
}
~~~

Hàm trên chỉ **tính digest**, chưa xác nhận tệp đến từ nguồn đáng tin. Khi so sánh với digest tham chiếu, ứng dụng cần kiểm tra nguồn cung cấp digest, quyền đọc tệp và khả năng tệp bị thay đổi đồng thời trong quá trình xử lý.

## 11. SHA-256 trong hệ thống KMS/HSM và envelope encryption

Mỗi cơ chế bảo vệ dữ liệu thực hiện một chức năng riêng:

~~~mermaid
flowchart TD
    D["Dữ liệu gốc"] --> A["AES-GCM với DEK"]
    A --> C["Ciphertext + nonce + tag"]
    K["KMS/HSM giữ KEK"] --> W["Wrap/unwrap DEK"]
    W --> E["Encrypted DEK"]
    C --> S["Kho lưu trữ"]
    E --> S
    D --> H["SHA-256 digest (tùy nhu cầu kiểm tra nội dung)"]
    H --> M["Manifest / metadata"]
    P["Private signing key trong KMS/HSM"] --> SIG["Ký manifest bằng thuật toán chữ ký phù hợp"]
    M --> SIG
    SIG --> T["Chữ ký để bên nhận xác minh"]
~~~

Trong sơ đồ:

- **DEK** (Data Encryption Key) dùng cho **AES-GCM** để bảo vệ bí mật và tính toàn vẹn có xác thực của dữ liệu.
- **KEK** (Key Encryption Key) trong KMS/HSM dùng **wrap/unwrap** DEK; cơ chế wrap tuân theo thuật toán của KMS, không phải mặc định là SHA-256.
- **SHA-256** có thể tạo digest của nội dung hoặc manifest để kiểm tra byte và hỗ trợ chữ ký số.
- **ECDSA/RSA-PSS** có thể dùng SHA-256 như một thành phần của sơ đồ ký để ràng buộc manifest với **private key ký**.
- **HMAC-SHA-256** có thể xác thực một thông điệp giữa các thành phần cùng nắm shared secret.

**Không được dùng SHA-256 làm "encryption key" bằng cách hash một mật khẩu yếu một lần.** Khóa AES phải có entropy đủ mạnh và được cấp phát/dẫn xuất bằng cơ chế thích hợp. Không xem SHA-256 là thay thế cho authenticated encryption: nếu đã dùng AES-GCM đúng, tag GCM là phần quan trọng của kiểm tra tính toàn vẹn dữ liệu mã hóa; một digest công khai thêm vào **không thay thế tag**.

### 11.1. Key fingerprint và định danh khóa

Đôi khi hệ thống dùng **SHA-256 của public key** hoặc encoding của public key để tạo fingerprint dùng nhận biết và đối chiếu khóa công khai. Nhưng **fingerprint không tự xác thực danh tính**: phải so với nguồn tin cậy.

Với **secret key**, không nên công khai SHA-256(key material) một cách tùy tiện. Digest của một bí mật có entropy thấp có thể hỗ trợ đoán bí mật; việc đưa metadata khóa vào log cũng cần được rà soát theo chính sách. **Key ID do KMS cấp** và **SHA-256 fingerprint** là những khái niệm khác nhau.

## 12. Quản lý vòng đời khóa cho HMAC-SHA-256

Bản thân SHA-256 không có secret key để xoay vòng. Tuy nhiên, **HMAC-SHA-256 cần khóa đối xứng K**, và khóa này phải đi qua đầy đủ vòng đời:

~~~mermaid
flowchart LR
    G["Sinh secret K bằng CSPRNG"] --> P["Cấp phát qua kênh bảo mật"]
    P --> U["MAC / Verify theo quyền"]
    U --> R["Rotation: K1 sang K2"]
    R --> T["Chuyển signer và verifier"]
    T --> V["Thu hồi K1 theo chính sách"]
    V --> X["Hủy sau khi xử lý phụ thuộc"]
~~~

| Giai đoạn | Câu hỏi cần trả lời |
|---|---|
| **Generation** | K có entropy phù hợp? CSPRNG hoặc KMS/HSM có được tin cậy? |
| **Distribution** | Ai nhận shared secret, bằng kênh xác thực nào, có bản sao ở đâu? |
| **Storage** | Khóa có nằm trong source, log, image, backup hoặc file cấu hình không bảo vệ? |
| **Usage** | Ai có quyền GenerateMac/VerifyMac? HMAC bảo vệ đúng dữ liệu và ngữ cảnh chưa? |
| **Rotation** | Có key ID/version, cách chuyển signer và verifier không gián đoạn? |
| **Revocation** | K1 lộ thì chặn token/webhook gắn với K1 thế nào, có cache verifier hoặc secret đã xuất không? |
| **Destruction** | Khi nào được xóa K1 mà không ảnh hưởng thông điệp lịch sử cần xác minh? |

Khóa HMAC thường là **bí mật chia sẻ**. Khi hai phía cùng biết khóa, cả hai đều có khả năng tính HMAC hợp lệ; HMAC không cung cấp tính chất quy trách nhiệm độc lập tương đương hệ chữ ký số mà chỉ một phía có private key.

### 12.1. Vấn đề rotation trong hệ thống phân tán

Giả sử webhook dùng HMAC-SHA-256 với **K1**. Khi chuyển sang **K2**:

1. Sinh K2, lưu trong KMS/secret store, định nghĩa quyền truy cập tối thiểu.
2. Cấp key ID/version hoặc cơ chế nhận biết phiên bản cho cả bên gửi và bên nhận.
3. Bên nhận chuẩn bị **verify K2** trước khi bên gửi chuyển sang **sign/MAC bằng K2**.
4. Bên gửi bắt đầu dùng K2; chỉ duy trì cửa sổ kiểm tra K1 có kiểm soát khi phù hợp rủi ro.
5. Nếu K1 bị **lộ**, có thể cần **từ chối K1 ngay**, thu hồi phiên/token liên quan và chấp nhận gián đoạn một số thông điệp.
6. Kiểm thử thực tế trên tất cả instance và cache, audit ngày chuyển đổi, sau đó hủy K1 khi được phép.

Không đồng nhất **đổi alias** với **thay key material**. Nếu K1 và K2 vẫn là cùng secret, rotation không làm giảm hậu quả của việc secret đã bị lộ.

## 13. Những sai lầm thường gặp với SHA-256

| Sai lầm | Rủi ro | Cách xử lý |
|---|---|---|
| Dùng SHA-256 để "mã hóa" dữ liệu và muốn giải mã lại | Hash không có thao tác decrypt | Dùng AES-GCM hoặc cơ chế mã hóa được chuẩn hóa |
| Dùng SHA-256(payload) làm chữ ký webhook | Kẻ tấn công thay cả payload và hash | Dùng HMAC-SHA-256 hoặc chữ ký số |
| Dùng SHA256(secret || message) làm MAC | Có thể gặp **length-extension** | Dùng API HMAC chuẩn |
| Lưu SHA256(password) | Rất dễ thử mật khẩu ứng viên quy mô lớn | Argon2id hoặc password KDF phù hợp với salt riêng |
| Coi digest công khai là danh tính người gửi | Bất kỳ ai cũng tính được SHA-256 | Kiểm tra nguồn digest đã xác thực hoặc chữ ký/MAC |
| Hash chuỗi ở các hệ thống với encoding khác nhau | Digest lệch dù nội dung trông giống nhau | Chuẩn hóa bytes, charset, JSON canonicalization |
| Nhầm 256 bit đầu ra với độ dài khóa HMAC bắt buộc | Cấp phát secret entropy thấp dù "đủ ký tự" | Sinh khóa ngẫu nhiên đủ entropy và quản lý vòng đời |
| Dùng lại cùng secret cho AES và HMAC tùy tiện | Trộn mục đích/không có domain separation | Dẫn xuất khóa riêng qua KDF chuẩn và context |
| Đưa secret HMAC vào log để debug | Lộ khả năng giả mạo thông điệp | Audit key ID/version và trạng thái, che dữ liệu nhạy cảm |
| Cho rằng HMAC tự chống replay | Bản tin hợp lệ có thể phát lại | Nonce/timestamp/request ID đã xác thực và trạng thái chống replay |
| Không kiểm tra chữ ký/trust policy, chỉ kiểm tra hash | Chấp nhận manifest giả mạo | Verify bằng public key được tin và kiểm tra chứng chỉ/quyền |
| Rotate KMS nhưng vẫn chấp nhận phiên bản HMAC cũ vô thời hạn | Tiếp tục nhận thông điệp có thể bị giả mạo | Kế hoạch cutover, TTL, revocation và kiểm thử verifier |
| Hash file nhưng cho file bị sửa giữa lúc đọc và dùng | Kết quả kiểm tra không gắn với nội dung đã dùng | Thiết kế quy trình đọc, xác minh và sử dụng cùng một hiện vật tin cậy |

## 14. Tình huống thực tế: API nhận yêu cầu thanh toán

Giả sử hệ thống **Partner A** gửi một yêu cầu chuyển tiền tới **Payment API**. Hai phía cùng có một khóa HMAC-SHA-256 được cấp qua kênh an toàn.

**Thiết kế ban đầu:**

~~~text
POST /payments
Body: {"orderId":"X1","amount":100000}
Header: X-Body-Hash: SHA256(raw_body)
~~~

Vấn đề: nếu kẻ tấn công sửa amount và tính lại header X-Body-Hash, API vẫn thấy hash khớp. Hash chỉ kiểm tra tính khớp byte với một giá trị **không được xác thực**.

**Thiết kế được cải thiện:**

~~~text
POST /payments
X-Key-Id: partner-A-v3
X-Timestamp: 2026-11-28T02:00:00Z
X-Request-Id: 7d6e... (ID duy nhất)
X-Signature: HMAC-SHA256(secret_v3, canonical_request_bytes)

canonical_request_bytes chứa:
  version + method + path + timestamp + requestId
  + partnerId + hash(raw_body) theo quy tắc byte xác định
~~~

Bên nhận phải:

1. **Xác thực đối tác và tra đúng key ID/version** đã được cấp quyền; không để client chọn một secret bất kỳ.
2. Dựng lại **canonical_request_bytes** theo cùng hợp đồng byte, không bỏ sót trường quan trọng.
3. **Verify HMAC** bằng khóa của đối tác và từ chối ngay khi không khớp; không xử lý thanh toán trước verify.
4. Kiểm tra **timestamp** trong cửa sổ cho phép và **requestId** chưa từng được xử lý; duy trì trạng thái chống replay.
5. Kiểm tra quyền của đối tác, hạn mức tiền, tính duy nhất của order, logic nghiệp vụ và các điều kiện chống gian lận.
6. Audit **partnerId, key version, requestId, thời điểm, kết quả** mà không ghi secret hoặc thông tin tài chính nhạy cảm vượt nhu cầu.

Ngay cả khi HMAC hợp lệ, **quyền thanh toán vẫn phải được kiểm tra riêng**. HMAC chứng minh người gửi có khả năng dùng shared secret tương ứng, không chứng minh giao dịch luôn được phép.

## 15. Kiểm thử và kiểm toán SHA-256 / HMAC-SHA-256

| Tình huống thử | Kết quả mong đợi |
|---|---|
| SHA-256 của chuỗi UTF-8 **abc** | Khớp test vector đã công bố |
| Hash cùng byte dữ liệu nhiều lần | Kết quả giống nhau |
| Thay một byte đầu vào | Digest gần như chắc chắn khác; không dùng đây để "chứng minh" collision resistance |
| HMAC đúng message và key | Verify thành công |
| Thay body nhưng giữ tag cũ | Verify thất bại |
| Dùng key version khác | Verify thất bại trừ trường hợp key material trùng ngoài ý muốn |
| Chặn quyền GenerateMac của service | Không thể tạo MAC qua KMS theo chính sách |
| Thu hồi HMAC key K1 | Verifier từ chối K1 theo chính sách và thời điểm chuyển đổi |
| Gửi lại nguyên request có HMAC hợp lệ, requestId đã dùng | Bị **cơ chế chống replay** từ chối |
| Input JSON tương đương về ý nghĩa nhưng khác byte | Hệ thống xử lý đúng theo quy tắc canonicalization đã thỏa thuận |
| Khách gửi digest tệp không được xác thực rồi thay tệp và digest | Không được coi là bằng chứng nguồn gốc đáng tin |
| Tài khoản chưa được cấp quyền tải secret HMAC | Bị từ chối và sự kiện được kiểm toán |

**Kiểm toán** phải giúp xác định khóa HMAC nào đã dùng, ai có quyền sử dụng, phiên bản khi rotate, lỗi verify tăng đột biến và hành vi bất thường. Không ghi lại **secret key, plaintext nhạy cảm, password, bearer token** hoặc toàn bộ payload chỉ để dễ theo dõi.

Ngoài test tích cực, cần test **fail-closed**: thiếu tag, sai thuật toán, sai key ID, dữ liệu sai format, payload không khớp, timestamp lệch, requestId trùng và KMS không khả dụng. Trong giao thức yêu cầu xác thực, không được bỏ qua verify chỉ vì dịch vụ quản lý khóa gặp lỗi.

## 16. Câu hỏi tự kiểm tra

**Câu 1. SHA-256 của một tệp có giúp giải mã tệp đó không?**

**Trả lời:** Không. SHA-256 là hàm băm một chiều; muốn giải mã cần hệ mã hóa phù hợp và khóa giải mã.

**Câu 2. Digest SHA-256 có luôn dài 64 byte không?**

**Trả lời:** Không. Digest dài **32 byte (256 bit)**; dạng **hex** dùng 64 ký tự.

**Câu 3. Vì sao SHA-256 của password không đủ để lưu mật khẩu?**

**Trả lời:** SHA-256 quá nhanh cho dữ liệu dễ đoán. Cần password hashing/KDF được thiết kế chống thử mật khẩu hàng loạt, chẳng hạn Argon2id, với salt và tham số phù hợp.

**Câu 4. SHA-256 có thể đảm bảo kẻ tấn công không thay dữ liệu đã tải không?**

**Trả lời:** Chỉ khi digest tham chiếu đến từ **nguồn được tin cậy** và được ràng buộc đúng tệp/phiên bản. Nếu kẻ tấn công thay được cả file và hash tham chiếu, kiểm tra digest không phát hiện giả mạo.

**Câu 5. SHA-256 và HMAC-SHA-256 khác nhau ở đâu?**

**Trả lời:** SHA-256 băm không cần khóa; HMAC-SHA-256 dùng **khóa bí mật** để tạo và kiểm tra tag, phục vụ xác thực thông điệp.

**Câu 6. Tại sao không dùng SHA256(key || message) như HMAC?**

**Trả lời:** Cách ghép này có thể gặp **length-extension** và thiếu bảo đảm của MAC chuẩn. Dùng HMAC-SHA-256.

**Câu 7. HMAC-SHA-256 có tạo chữ ký số có thể xác minh công khai không?**

**Trả lời:** Không. HMAC dùng shared secret; các bên biết secret đều có thể tạo tag. Chữ ký số bất đối xứng như ECDSA dùng private key để ký và public key để xác minh.

**Câu 8. Dùng SHA256withECDSA của Java có cần hash thông điệp trước không?**

**Trả lời:** Thông thường **không**: tên thuật toán cho biết provider đã hash bằng SHA-256 trong thao tác Sign. Nếu dùng API nhận digest, phải làm đúng hợp đồng cụ thể để tránh double hashing.

**Câu 9. Vì sao HMAC hợp lệ vẫn chưa đủ để xử lý giao dịch tài chính?**

**Trả lời:** HMAC không tự kiểm tra quyền chi tiền, hạn mức, trạng thái đơn hàng hoặc replay. Cần các kiểm soát nghiệp vụ và xác thực danh tính/phạm vi độc lập.

**Câu 10. Khi thay khóa HMAC, cần cập nhật những thành phần nào?**

**Trả lời:** Nơi cấp phát và lưu secret, signer, verifier, key ID/version, cache, chính sách quyền, kiểm toán, thời điểm chấp nhận khóa cũ và kế hoạch thu hồi.

**Câu 11. HKDF-SHA-256 và SHA-256(password) có tương đương nhau không?**

**Trả lời:** Không. HKDF dùng để dẫn xuất key material từ bí mật thích hợp; SHA-256(password) là một phép hash nhanh và không đáp ứng nhu cầu lưu mật khẩu an toàn.

**Câu 12. Có nên dùng SHA-256 của public key làm key ID không?**

**Trả lời:** Có thể dùng fingerprint SHA-256 để nhận biết public key theo thiết kế, nhưng fingerprint không tự xác thực danh tính. Với KMS, nên phân biệt fingerprint với **key ID/version** được quản lý và xác thực.

## 17. Ghi nhớ và checklist áp dụng

Trước khi triển khai SHA-256 trong một hệ thống bảo mật, hãy xác định:

- **Mục đích:** cần digest để kiểm tra byte, MAC để xác thực thông điệp, chữ ký số để xác minh bằng public key, hay KDF để tạo khóa?
- **Nguồn tin cậy:** digest tham chiếu, public key hoặc shared secret đến từ đâu và có được xác thực không?
- **Đầu vào:** các bên có thống nhất đúng dãy byte, encoding, canonicalization, thứ tự trường và ngữ cảnh không?
- **Khóa (nếu có):** HMAC key/private signing key được tạo, cấp phát, lưu, giới hạn quyền, xoay vòng, thu hồi và hủy ra sao?
- **Thuật toán và API:** ứng dụng có chọn đúng SHA-256, HmacSHA256, SHA256withECDSA hay chế độ KDF tương ứng không? Có nguy cơ double hashing hoặc định dạng sai không?
- **Chống replay và quyền nghiệp vụ:** token, webhook và giao dịch đã kiểm tra timestamp, request ID, quyền và trạng thái chưa?
- **Giám sát:** audit log có đủ key ID/version, danh tính, kết quả và lỗi mà không làm rò secret hoặc dữ liệu nhạy cảm không?

**SHA-256 là công cụ nền tảng để tạo digest 256 bit; độ an toàn hệ thống phụ thuộc việc dùng nó đúng vai trò.** Muốn xác thực thông điệp dùng **HMAC-SHA-256** với khóa được quản lý, muốn ký số dùng **thuật toán chữ ký** với private key được bảo vệ, muốn mã hóa dữ liệu dùng **AEAD như AES-GCM**. Phân biệt những vai trò này giúp thiết kế vòng đời khóa, **KMS/HSM, envelope encryption, kiểm soát truy cập và kiểm toán** một cách nhất quán.
