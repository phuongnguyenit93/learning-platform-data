# Không tái sử dụng nonce với cùng khóa

## 1. Quy tắc cốt lõi

Trong mã hóa hiện đại kiểu **AEAD (Authenticated Encryption with Associated Data)**, một nonce/IV phải được tạo theo đúng yêu cầu của thuật toán. Với các thuật toán phổ biến như **AES-GCM** và **ChaCha20-Poly1305**, quy tắc quan trọng là:

> **Không được dùng lại cùng một nonce với cùng một khóa mã hóa cho hai lần mã hóa khác nhau.**

Nói chính xác hơn, mỗi lần gọi phép mã hóa AEAD bằng một khóa cụ thể phải có nonce hợp lệ và duy nhất trong phạm vi tất cả các lần mã hóa đã sử dụng khóa đó, theo yêu cầu của thuật toán. Không giới hạn phạm vi ở một method, một object `Cipher`, một thread hay một tiến trình. Nếu nhiều máy chủ, worker, region hoặc dịch vụ dùng chung cùng key material, tất cả phải phối hợp để không tạo ra nonce trùng nhau.

Ví dụ:

```text
Key K + Nonce N  -> Encrypt(message A)   OK
Key K + Nonce N  -> Encrypt(message B)   KHÔNG AN TOÀN

Key K + Nonce N1 -> Encrypt(message A)   OK
Key K + Nonce N2 -> Encrypt(message B)   OK, nếu N1 != N2
Key K2 + Nonce N -> Encrypt(message C)   Một nonce space mới nếu K2 là khóa khác thật sự
```

Nonce **không cần bí mật**. Nó thường được lưu hoặc truyền cùng ciphertext để bên nhận có thể giải mã. Điều cần bảo vệ là **tính duy nhất theo khóa**, không phải che giấu nonce.

Quy tắc này đặc biệt quan trọng với AES-GCM và ChaCha20-Poly1305. Các thuật toán khác có yêu cầu IV/nonce riêng; không nên khái quát rằng mọi chế độ mã hóa đều dùng cùng một quy tắc. Phần dưới tập trung vào các AEAD hiện đại và các API Java còn được hỗ trợ.

Bài thuộc chủ đề cha **“Mật mã ứng dụng”**, đề bài trực tiếp **“Không tái sử dụng nonce với cùng khóa”**. Nội dung bao gồm hậu quả khi vi phạm, cách tạo nonce, quản lý bộ đếm trong hệ thống đồng thời/phân tán, khởi động lại và khôi phục dữ liệu, luân chuyển khóa, lưu nonce cạnh ciphertext và ví dụ Java 17+ có thể chạy.

## 2. Phân biệt key, nonce/IV, plaintext, ciphertext và AAD

Một lời gọi AEAD thường có các thành phần:

| Thành phần | Vai trò | Có cần bí mật? |
| --- | --- | --- |
| Key | Bí mật dùng để mã hóa và xác thực | **Có** |
| Nonce/IV | Tham số phân biệt lần mã hóa, phải tuân thủ yêu cầu của thuật toán | Thường **không** |
| Plaintext | Dữ liệu gốc cần bảo vệ | Tùy dữ liệu |
| Ciphertext | Dữ liệu đã mã hóa, thường kèm authentication tag | Không cần bí mật để giải mã, nhưng cần bảo vệ tính toàn vẹn |
| AAD | Dữ liệu phụ được xác thực nhưng không mã hóa | Không nhất thiết bí mật |
| Authentication tag | Bằng chứng xác thực ciphertext và AAD | Không cần bí mật, nhưng phải được kiểm tra |

`Nonce` là viết tắt của *number used once*. Với AES-GCM, tài liệu Java thường gọi tham số này là **IV (Initialization Vector)**. Trong ngữ cảnh GCM, hai tên thường được dùng để nói đến cùng tham số đầu vào. Với ChaCha20-Poly1305, chuẩn RFC gọi là nonce.

**Không nhầm nonce với key:** nonce không phải mật khẩu, không phải khóa bí mật và không thể thay thế việc bảo vệ key. Một kẻ tấn công có thể nhìn thấy nonce mà vẫn không giải mã được ciphertext nếu key và thuật toán được quản lý đúng.

### 2.1. Nonce phải đi cùng ciphertext để giải mã

Khi mã hóa, bên nhận cần biết đúng nonce đã được dùng:

```text
Encrypt:
  key + fresh nonce + plaintext + AAD
                 |
                 v
       ciphertext + authentication tag

Stored / transmitted envelope:
  algorithm/version + key identifier + nonce + ciphertext/tag + needed metadata

Decrypt:
  same key + stored nonce + same AAD + ciphertext/tag
                 |
                 v
       plaintext only after authentication succeeds
```

Việc dùng lại nonce để **giải mã chính ciphertext tương ứng** là bình thường và cần thiết. Quy tắc cấm tái sử dụng áp dụng cho **các lần mã hóa mới** bằng cùng key. Không nhầm “decryption dùng lại nonce trong envelope” với “encrypt lần nữa bằng nonce cũ”.

### 2.2. AAD khác nonce

AAD có thể là loại bản ghi, tenant ID, phiên bản schema hoặc metadata cần được xác thực nhưng không cần mã hóa. Ví dụ:

```java
cipher.updateAAD("record-type:v1".getBytes(StandardCharsets.UTF_8));
```

AAD được xác thực cùng ciphertext. Đổi AAD **không làm nonce cũ trở nên an toàn để mã hóa lại**. Cặp key/nonce vẫn phải duy nhất theo yêu cầu của AEAD.

## 3. Vì sao nonce reuse nguy hiểm?

Nonce không phải một giá trị trang trí. Các thuật toán AEAD dùng nó để tạo trạng thái mật mã cho từng thông điệp. Tái sử dụng cùng nonce với cùng key phá vỡ các giả định mà thuật toán dựa vào.

### 3.1. Hậu quả với AES-GCM

AES-GCM kết hợp mã hóa kiểu counter mode với xác thực GHASH. Khi cùng key và IV được dùng lại:

- Counter keystream có thể lặp lại. Hai ciphertext có quan hệ XOR trực tiếp với hai plaintext tương ứng; nếu biết hoặc đoán được một plaintext, attacker có thể suy ra phần tương ứng của plaintext kia.
- Cơ chế xác thực GHASH bị đặt vào điều kiện nonce reuse mà thiết kế không cho phép. Các quan hệ giữa authentication tags có thể làm lộ thông tin về khóa xác thực và mở đường cho giả mạo tag.
- Hậu quả có thể là **mất bí mật và mất tính toàn vẹn/xác thực**, không chỉ là hai ciphertext giống nhau.

Vì vậy, nonce trùng trong AES-GCM phải được xem là một sự cố bảo mật nghiêm trọng. Không tiếp tục mã hóa dưới cùng key rồi hy vọng tag vẫn bảo vệ được dữ liệu.

### 3.2. Hậu quả với ChaCha20-Poly1305

ChaCha20-Poly1305 tạo one-time Poly1305 key từ key và nonce. Khi một cặp key/nonce bị tái sử dụng:

- Keystream ChaCha20 lặp lại, làm lộ quan hệ giữa các plaintext.
- One-time key của Poly1305 cũng bị tái sử dụng, phá vỡ giả định xác thực của MAC.
- Attacker có thể có cơ hội giả mạo thông điệp hoặc tag, tùy lượng dữ liệu quan sát được.

RFC 8439 yêu cầu nonce khác nhau cho mỗi lần gọi AEAD với cùng key; tài liệu cũng khuyến nghị dùng counter và nêu rõ nonce không được sinh ngẫu nhiên trong construction ChaCha20/Poly1305 mà RFC mô tả.

### 3.3. Đổi plaintext hoặc AAD không giải quyết nonce reuse

Các cách sau đều **không** sửa được lỗi:

- Mã hóa plaintext khác nhưng dùng lại nonce.
- Dùng AAD khác nhưng vẫn giữ nonce cũ.
- Đổi tên file hoặc record ID nhưng không đổi nonce.
- Tạo object `Cipher` mới nhưng vẫn truyền cùng key và nonce.
- Chạy ở thread khác hoặc máy chủ khác mà không có namespace nonce riêng.

Điều quyết định là **cặp key material và nonce của mỗi lần mã hóa**, không phải tên biến hoặc vị trí code.

### 3.4. Nonce trùng không phải lúc nào cũng làm ciphertext giống hệt

Nếu plaintext khác, ciphertext có thể khác; nếu AAD khác, tag có thể khác. Điều đó **không chứng minh an toàn**. Rủi ro nằm ở việc tái sử dụng trạng thái mật mã bên dưới, không chỉ ở việc output có giống nhau hay không.

## 4. Phạm vi “cùng khóa” phải hiểu trên toàn hệ thống

Một lỗi phổ biến là đảm bảo nonce không lặp trong một object hoặc một tiến trình rồi cho rằng đã đủ. Phạm vi thật sự lớn hơn.

Nonce phải duy nhất trên **tất cả lần mã hóa sử dụng cùng key material**, gồm:

- Nhiều lần gọi một method trong cùng thread.
- Nhiều thread dùng chung một key.
- Nhiều instance của service trong cùng JVM.
- Nhiều process/container/VM/worker.
- Nhiều region hoặc cluster.
- Job batch, scheduled job và API request cùng sử dụng key.
- Những bản triển khai cũ/mới chạy song song trong thời gian rolling deployment.
- Những hệ thống khôi phục từ backup/snapshot nhưng tiếp tục dùng lại key cũ.

Nếu hai key alias trong KMS thực chất tham chiếu **cùng bytes của khóa**, chúng thuộc cùng nonce domain. Đổi alias hoặc key identifier không tự tạo một khóa mới.

### 4.1. Key scope theo thuật toán và mục đích

Nếu một ứng dụng dùng nhiều thuật toán hoặc nhiều protocol, nên tạo khóa riêng biệt theo purpose/algorithm bằng một key-management/KDF design đã được kiểm chứng. Không lấy một key raw rồi tùy tiện dùng lại cho nhiều protocol với các nonce allocator không liên quan.

### 4.2. Nonce uniqueness là điều kiện của encryption, không phải chống replay

Một attacker có thể gửi lại **một ciphertext hợp lệ cũ** mà không cần tạo nonce mới. Nonce uniqueness không tự ngăn replay. Nếu nghiệp vụ cần chống replay, thêm message ID/sequence number, timestamp có xác minh và trạng thái chống phát lại ở tầng protocol. Không nhầm hai mục tiêu này.

## 5. Yêu cầu cụ thể của AES-GCM

NIST SP 800-38D định nghĩa GCM và yêu cầu IV phải duy nhất với mỗi key. Tài liệu khuyến nghị triển khai hỗ trợ IV **96 bit (12 bytes)** để tăng khả năng tương thích, hiệu quả và đơn giản hóa.

Các giá trị thường dùng trong ứng dụng:

- IV/nonce: **12 bytes**.
- Authentication tag: **128 bits (16 bytes)**.
- Transformation trong Java: `AES/GCM/NoPadding`.
- Java parameter object: `GCMParameterSpec(128, iv)`.
- Random source nếu dùng construction ngẫu nhiên: `SecureRandom`.

Không tự thay nonce 12 bytes bằng một chuỗi tùy ý ngắn, counter timestamp, UUID bị cắt ngắn hoặc một giá trị cố định. Nếu một provider/chuẩn cho phép IV length khác, chỉ dùng theo construction và giới hạn được tài liệu hóa; 12 bytes là lựa chọn thông dụng được NIST khuyến nghị.

### 5.1. Giới hạn của random IV theo NIST

NIST SP 800-38D mô tả hai nhóm construction IV: **deterministic** và **RBG-based (random-bit-generator-based)**. Khi dùng construction dựa trên random bits, tiêu chuẩn có giới hạn tổng số lần gọi GCM với cùng key; trong bản SP 800-38D đang được công bố, giới hạn tổng là tối đa **2^32 lần gọi cho một key**, tính trên các instance liên quan theo quy tắc của tiêu chuẩn.

Đây là **giới hạn trên theo construction**, không phải mục tiêu vận hành mặc định. Hệ thống phải tuân thủ đầy đủ các ràng buộc về độ dài IV, cách tạo IV, số lần gọi, kích thước dữ liệu và chính sách key. Không chỉ đếm nonce trong một JVM.

NIST có thông báo rằng SP 800-38D sẽ được sửa đổi; khi triển khai hệ thống mới hoặc cần tuân thủ tiêu chuẩn, hãy kiểm tra bản chính thức mới nhất và quy định của tổ chức tại thời điểm triển khai.

### 5.2. Random 96-bit không tạo ra bảo đảm toán học tuyệt đối

`SecureRandom` sinh đầu ra khó dự đoán và phù hợp cho mục đích bảo mật. Tuy vậy, nếu lấy các chuỗi 96-bit ngẫu nhiên, về mặt toán học vẫn có xác suất trùng. Xác suất tăng theo số lần sinh (birthday bound), xấp xỉ:

```text
P(collision) ≈ q * (q - 1) / 2^97
```

với `q` là số IV ngẫu nhiên đã tạo dưới cùng key, trong vùng xác suất còn nhỏ.

Do đó:
- Dùng `SecureRandom` thay vì `Random`, `ThreadLocalRandom` hoặc `Math.random`.
- Đếm/giới hạn số lần mã hóa theo yêu cầu NIST và policy.
- Tính cả mọi instance dùng chung key.
- Nếu hệ thống cần uniqueness mang tính deterministic, dùng một counter/allocator được thiết kế và lưu bền vững.
- Không gọi một lần test “đã sinh 10.000 nonce khác nhau” là bằng chứng mọi lần sau sẽ không bao giờ trùng.

## 6. Yêu cầu cụ thể của ChaCha20-Poly1305

RFC 8439 định nghĩa AEAD ChaCha20-Poly1305 với:

- Key 256 bits.
- Nonce **96 bits (12 bytes)**.
- Nonce phải khác nhau ở mỗi lần gọi với cùng key.
- Counter là cách triển khai phù hợp để bảo đảm uniqueness; trong trường hợp nhiều sender dùng cùng key, nonce space cần được phân vùng giữa các sender.

RFC 8439 mô tả construction nonce theo cách **không sinh ngẫu nhiên**; nên dùng counter/namespace deterministic và bảo đảm không reset. Vì vậy, không áp dụng hướng dẫn “random IV với SecureRandom” của ví dụ AES-GCM sang ChaCha20-Poly1305 một cách máy móc.

Một cách phân vùng được RFC nêu là dành phần đầu nonce cho định danh sender duy nhất và phần còn lại cho counter. Cách chia cụ thể phải bám theo protocol và phạm vi key; không tự phát minh layout nonce không được các sender thống nhất.

## 7. Hai chiến lược tạo nonce phổ biến

Không có một chiến lược duy nhất phù hợp cho mọi thuật toán. Chọn theo đặc tả của AEAD và kiến trúc hệ thống.

| Chiến lược | Đặc điểm | Điều kiện bắt buộc |
| --- | --- | --- |
| Random CSPRNG | Sinh IV mới bằng SecureRandom; thường dùng cho AES-GCM | Theo construction RBG, giới hạn NIST; collision vẫn có xác suất |
| Deterministic counter | Ghép namespace/fixed field với counter | Counter không lặp, được đồng bộ và lưu bền vững qua restart/restore |
| Per-node/per-sender namespace | Mỗi sender có một vùng nonce riêng, bên trong dùng counter | Namespace không trùng trong phạm vi key; phân bổ có kiểm soát |
| Per-purpose derived key | Mỗi instance/purpose có key riêng được dẫn xuất an toàn | KDF và context separation được thiết kế đúng; không dùng cùng raw key |

### 7.1. Random nonce cho AES-GCM

Mẫu:

```java
byte[] nonce = new byte[12];
SecureRandom random = new SecureRandom();
random.nextBytes(nonce);

GCMParameterSpec parameters =
        new GCMParameterSpec(128, nonce);
```

Đây là cách sinh IV ngẫu nhiên 96-bit cho AES-GCM. Mỗi lần mã hóa phải lấy một nonce mới. Đừng tạo nonce một lần khi khởi tạo service rồi tái sử dụng cho mọi bản ghi.

**Quan trọng:** random không đồng nghĩa chắc chắn không trùng. Hãy quản lý số lần mã hóa theo giới hạn GCM RBG-based và tất cả instance dùng key.

### 7.2. Counter nonce deterministic

Một nonce deterministic có thể được tạo từ:

```text
nonce = fixed_namespace || invocation_counter
```

Trong đó:
- `fixed_namespace` xác định instance/sender/context được phân bổ duy nhất dưới key.
- `invocation_counter` tăng đơn điệu cho mỗi lần mã hóa của instance đó.
- Ghép hai phần tạo đúng độ dài nonce của thuật toán.
- Không được cấp cùng namespace cho hai sender cùng key.
- Counter phải được giữ bền vững, không quay về 0 sau restart.

Đây là mô hình khái niệm. Với AES-GCM, phải tuân theo IV construction trong NIST SP 800-38D; với ChaCha20-Poly1305, tuân theo RFC 8439. Không coi bất kỳ phép ghép bytes tùy ý nào cũng là construction chuẩn.

### 7.3. AtomicLong chỉ giải quyết đồng thời trong một JVM

`AtomicLong.getAndIncrement()` có thể cấp counter khác nhau cho nhiều thread trong **cùng process**. Nó không tự bảo đảm:
- Process khác không dùng cùng counter.
- Container mới không khởi động lại từ 0.
- Backup/restore không làm counter lùi.
- Hai region không cấp cùng namespace.
- Key được chia sẻ giữa nhiều service có allocator chung.

Vì vậy, `AtomicLong` có thể là một thành phần trong allocator cục bộ, nhưng không phải toàn bộ giải pháp uniqueness của hệ thống phân tán.

## 8. Counter phải sống lâu hơn process

Nonce reuse thường xuất hiện sau các sự kiện vận hành:

### 8.1. Restart ứng dụng

Một process dùng counter 0, 1, 2, 3 rồi dừng. Process mới khởi động lại counter từ 0 trong khi vẫn dùng cùng key. Nó sẽ tái sử dụng nonce cũ.

**Giải pháp:** lưu counter bền vững hoặc cấp một namespace mới được bảo đảm duy nhất cho process mới. Không reset counter chỉ vì service đã restart.

### 8.2. Hai instance chạy đồng thời

Hai pod cùng dùng key và cùng khởi tạo counter 0 sẽ tạo nonce trùng ngay ở lần mã hóa đầu tiên.

**Giải pháp:** dùng allocator tập trung/atomic, cấp range counter không giao nhau, namespace sender duy nhất, hoặc key riêng biệt cho mỗi instance theo một thiết kế key derivation đã kiểm chứng.

### 8.3. Khôi phục từ backup/snapshot

Counter có thể bị rollback về một trạng thái cũ trong khi key không đổi. Đây là một nguyên nhân nguy hiểm vì ứng dụng có thể chạy bình thường sau restore nhưng nonce lại trùng với những message đã mã hóa trước backup.

**Giải pháp:** sau rollback không thể chứng minh counter tiếp tục lớn hơn mọi giá trị đã dùng, hãy **ngừng mã hóa bằng key đó và chuyển sang key mới** hoặc cấp một nonce namespace mới được bảo đảm chưa từng sử dụng.

### 8.4. Cấp trước các dải counter

Một thiết kế phân tán có thể cấp mỗi worker một range không trùng nhau:

```text
Worker A: [0, 1_000_000)
Worker B: [1_000_000, 2_000_000)
Worker C: [2_000_000, 3_000_000)
```

Range phải được cấp **bền vững trước khi dùng** và không được tái cấp cho worker khác khi chưa chứng minh worker cũ chưa dùng bất kỳ counter nào trong đó. Nếu worker crash, phần range chưa dùng cũng nên được coi là đã tiêu thụ; bỏ phí nonce an toàn hơn tái sử dụng.

### 8.5. Đừng dùng thời gian làm nonce duy nhất

Các mẫu như `System.currentTimeMillis()` hoặc timestamp ghép với process ID không tự bảo đảm duy nhất:
- Hai message có thể được mã hóa trong cùng một tick.
- Clock có thể lùi khi NTP/VM restore.
- Hai máy có đồng hồ và ID trùng.
- Precision timestamp có thể thấp hơn throughput.
- Clock không phải bộ cấp sequence atomic.

Timestamp có thể là một phần metadata, nhưng không thay thế nonce allocator có contract rõ.

## 9. Key rotation và phạm vi nonce mới

Nonce uniqueness gắn với **key material thực tế**.

- Khi tạo key mới độc lập, nonce space có thể bắt đầu lại theo construction đã chọn.
- Nếu chỉ đổi key alias/version label nhưng bytes khóa không đổi, vẫn là cùng key và không được reset nonce.
- Nếu key cũ còn được dùng để mã hóa ở một service, mọi service khác phải tiếp tục tránh nonce trùng với service đó.
- Nếu key cũ đã chuyển sang decrypt-only, không được dùng lại để encrypt.
- Nếu không thể khôi phục counter/namespace sau sự cố, phương án an toàn là tạo key mới theo quy trình quản lý khóa.

Key rotation cần cập nhật metadata để decrypt biết ciphertext được tạo bằng key version nào. Không đưa key bí mật vào envelope. Lưu một key identifier không nhạy cảm, nonce và ciphertext/tag.

### 9.1. Đừng luân chuyển khóa bằng cách đổi tên

Một thao tác rename/alias trong KMS không nhất thiết tạo key bytes mới. Trước khi reset counter, cần xác minh đó là key material mới thật sự.

### 9.2. Không tự derive key bằng phép nối chuỗi

Nếu mỗi sender cần key riêng, dùng một KDF chuẩn và context separation được thiết kế cẩn thận (ví dụ HKDF theo RFC 5869 hoặc cơ chế của thư viện key management). Không tự viết KDF, không dùng hash ghép tùy tiện và không lưu master key trong source code.

## 10. Xử lý retry và lỗi giữa chừng

Mỗi lần thử mã hóa mới cần một nonce mới. Nếu một lần mã hóa đã cấp nonce nhưng operation gặp lỗi, cách an toàn là **đánh dấu nonce đó đã tiêu thụ**. Đừng đưa nonce về pool để dùng lại vì khó biết provider hoặc pipeline đã dùng nó tới đâu.

Nếu ứng dụng retry cùng plaintext:
- Có thể mã hóa lại với nonce mới.
- Không mã hóa lại với nonce cũ chỉ vì lần trước timeout hoặc không nhận được response.
- Nếu ciphertext lần đầu có thể đã được gửi/lưu thành công nhưng ACK bị mất, ưu tiên retry **gửi lại chính envelope/ciphertext đã tạo** nếu protocol cho phép; không tạo lần mã hóa mới với cùng nonce.

Đây là khác biệt giữa retry transport và retry encryption. **Gửi lại cùng ciphertext hợp lệ** không phải tạo một lần mã hóa mới. Nếu tạo ciphertext mới, cần nonce mới.

## 11. Lưu và truyền nonce đúng cách

Một envelope thực tế có thể gồm:

```text
format_version
algorithm_id
key_id
nonce_or_iv
ciphertext_and_authentication_tag
authenticated_metadata (nếu protocol yêu cầu)
```

Với AES-GCM trong Java JCA, `Cipher.doFinal()` trả ciphertext kèm authentication tag theo output của provider. Lưu đủ bytes đó cùng nonce. Không cắt tag, không bỏ nonce và không lưu mỗi ciphertext rồi hy vọng decrypt tự suy ra IV.

### 11.1. Nonce không cần mã hóa

Nonce thường có thể đặt cạnh ciphertext ở dạng bytes. Người nhận cần đọc nonce trước khi khởi tạo Cipher decryption. Bảo vệ tính toàn vẹn của envelope bằng AEAD tag và protocol format; nếu một metadata field cần được xác thực, đưa nó vào AAD.

### 11.2. Xác thực phải hoàn tất trước khi tin plaintext

Với AEAD, tag phải được xác minh. Trong Java, lỗi xác thực có thể xuất hiện tại `Cipher.doFinal()` dưới dạng `AEADBadTagException`. Không dùng plaintext trung gian chưa được xác thực làm dữ liệu nghiệp vụ hoặc phát ra cho client trước khi kiểm tra tag hoàn tất.

### 11.3. AAD phải tái tạo chính xác

Nếu encryption dùng AAD, decryption phải cung cấp đúng AAD. Ví dụ tenant ID, record type hoặc format version cần có canonical encoding nhất quán. AAD sai làm tag verification thất bại; nó không phải cách để hợp thức hóa nonce reuse.

## 12. Java JCA: AES-GCM với nonce ngẫu nhiên mới

Ví dụ Java 17+ bên dưới:
- Tạo key AES tạm thời trong lần chạy.
- Dùng `SecureRandom` tạo IV 96-bit cho **mỗi lần mã hóa**.
- Dùng AES-GCM với tag 128-bit.
- Lưu nonce cạnh ciphertext trong object envelope.
- Cung cấp đúng nonce và AAD khi decrypt.
- Xác nhận dữ liệu round-trip.
- Sửa một byte ciphertext và xác nhận tag verification thất bại.

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.Set;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class NonceReuseDemo {
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;

    static final class EncryptedMessage {
        private final byte[] nonce;
        private final byte[] ciphertextAndTag;

        EncryptedMessage(byte[] nonce, byte[] ciphertextAndTag) {
            this.nonce = nonce.clone();
            this.ciphertextAndTag = ciphertextAndTag.clone();
        }

        byte[] nonce() {
            return nonce.clone();
        }

        byte[] ciphertextAndTag() {
            return ciphertextAndTag.clone();
        }
    }

    static final class AesGcm {
        private final SecretKey key;
        private final SecureRandom random;

        AesGcm(SecretKey key, SecureRandom random) {
            this.key = key;
            this.random = random;
        }

        EncryptedMessage encrypt(byte[] plaintext, byte[] aad)
                throws GeneralSecurityException {
            // Mỗi lần encrypt phải sinh IV mới.
            byte[] nonce = new byte[NONCE_BYTES];
            random.nextBytes(nonce);

            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(
                    Cipher.ENCRYPT_MODE,
                    key,
                    new GCMParameterSpec(TAG_BITS, nonce));

            if (aad != null) {
                cipher.updateAAD(aad);
            }

            byte[] ciphertextAndTag = cipher.doFinal(plaintext);
            return new EncryptedMessage(nonce, ciphertextAndTag);
        }

        byte[] decrypt(EncryptedMessage message, byte[] aad)
                throws GeneralSecurityException {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(
                    Cipher.DECRYPT_MODE,
                    key,
                    new GCMParameterSpec(TAG_BITS, message.nonce()));

            if (aad != null) {
                cipher.updateAAD(aad);
            }

            return cipher.doFinal(message.ciphertextAndTag());
        }
    }

    static void check(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) throws Exception {
        SecureRandom random = new SecureRandom();
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128, random);
        SecretKey key = generator.generateKey();

        AesGcm gcm = new AesGcm(key, random);
        byte[] aad =
                "record-type:v1".getBytes(StandardCharsets.UTF_8);

        byte[][] plaintexts = {
            "alpha".getBytes(StandardCharsets.UTF_8),
            "beta".getBytes(StandardCharsets.UTF_8),
            "gamma".getBytes(StandardCharsets.UTF_8)
        };

        Set<String> observedNonces = new HashSet<>();
        boolean roundTrip = true;
        EncryptedMessage first = null;

        for (int i = 0; i < plaintexts.length; i++) {
            EncryptedMessage message =
                    gcm.encrypt(plaintexts[i], aad);

            if (first == null) {
                first = message;
            }

            byte[] nonce = message.nonce();
            check(nonce.length == NONCE_BYTES, "nonce length");

            check(
                    observedNonces.add(
                            HexFormat.of().formatHex(nonce)),
                    "nonce repeated in this sample");

            byte[] recovered = gcm.decrypt(message, aad);
            roundTrip &= Arrays.equals(plaintexts[i], recovered);
        }

        check(roundTrip, "round trip");

        byte[] tamperedCiphertext = first.ciphertextAndTag();
        tamperedCiphertext[0] ^= 1;

        EncryptedMessage tampered =
                new EncryptedMessage(
                        first.nonce(), tamperedCiphertext);

        boolean tamperRejected = false;
        try {
            gcm.decrypt(tampered, aad);
        } catch (AEADBadTagException expected) {
            tamperRejected = true;
        }

        check(tamperRejected, "tampered ciphertext");

        System.out.println("algorithm=AES/GCM/NoPadding");
        System.out.println("nonceBytes=" + NONCE_BYTES);
        System.out.println("tagBits=" + TAG_BITS);
        System.out.println("messagesEncrypted=" + plaintexts.length);
        System.out.println("roundTrip=" + roundTrip);
        System.out.println("uniqueNoncesInSample="
                + (observedNonces.size() == plaintexts.length));
        System.out.println("tamperRejected=" + tamperRejected);
        System.out.println("ALL CHECKS PASSED");
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac NonceReuseDemo.java
java NonceReuseDemo
```

Stdout:

```text
algorithm=AES/GCM/NoPadding
nonceBytes=12
tagBits=128
messagesEncrypted=3
roundTrip=true
uniqueNoncesInSample=true
tamperRejected=true
ALL CHECKS PASSED
```

### 12.1. Giải thích kết quả

- `nonceBytes=12`: IV đúng 96 bits theo cấu hình ví dụ.
- `tagBits=128`: tag 128 bits.
- `messagesEncrypted=3`: ba lần mã hóa độc lập, mỗi lần gọi `SecureRandom.nextBytes`.
- `roundTrip=true`: decrypt với đúng key, nonce và AAD khôi phục plaintext.
- `uniqueNoncesInSample=true`: ba nonce trong lần chạy này không trùng nhau; đây là sanity check nhỏ, **không phải bằng chứng uniqueness toàn hệ thống hoặc bảo đảm toán học**.
- `tamperRejected=true`: sửa ciphertext làm authentication tag không hợp lệ, provider ném `AEADBadTagException`.
- `ALL CHECKS PASSED`: mọi assertion của demo đều qua.

### 12.2. Giới hạn có chủ đích của demo

Key trong chương trình được tạo mới mỗi lần chạy và counter không được lưu bền vững. Đây là **demo AES-GCM trong một JVM**, không phải một nonce service production cho key cố định qua nhiều lần restart hoặc nhiều node.

Khi chuyển sang production, phải quyết định rõ random IV construction hay deterministic IV construction, giới hạn số lần dùng key, cách phối hợp giữa mọi instance và nơi lưu nonce/ciphertext. Không sao chép code demo rồi bỏ qua các điều kiện đó.

### 12.3. Không tái sử dụng một Cipher với nonce cũ

Một object `Cipher` có thể được khởi tạo lại cho operation mới, nhưng mỗi lần encrypt bằng cùng key phải có IV mới. Tạo object Cipher mới **không tự bảo đảm** nonce mới nếu caller vẫn truyền nonce cũ. Trong demo, mỗi operation có Cipher mới và nonce mới để lifecycle dễ đọc.

## 13. Counter design cho hệ thống phân tán

Nếu chọn deterministic nonce, một thiết kế thường cần các phần:

```text
per-key nonce allocator
  +-- unique sender/instance namespace
  +-- durable invocation counter
  +-- atomic reservation
  +-- exhaustion limit
  +-- crash/restore policy
  +-- key rotation integration
```

### 13.1. Namespace được phân bổ, không tự chọn ngẫu nhiên rồi mặc định duy nhất

Nếu hai instance tự chọn cùng một prefix, counter của chúng có thể tạo nonce trùng. Namespace cần được phân bổ hoặc dẫn xuất theo cơ chế được thiết kế để không đụng nhau trong phạm vi key.

Một phương án là dùng key riêng cho từng instance bằng KDF với context duy nhất; khi đó nonce uniqueness được quản lý trong từng key domain. Việc tạo và phân phối key vẫn phải theo key-management design có kiểm chứng.

### 13.2. Reserve counter range trước khi dùng

Một allocator có thể cấp block counter cho từng worker. Phải ghi nhận range đã cấp bền vững **trước khi worker dùng**. Khi process crash, không cấp lại range đó chỉ vì một phần có thể chưa được dùng; bỏ phí counter an toàn hơn tái sử dụng.

### 13.3. Không wrap counter

Khi counter sắp hết miền:
- Dừng cấp nonce dưới key hiện tại.
- Không quay vòng về 0.
- Không xóa trạng thái để “làm mới”.
- Thực hiện key rotation theo policy.
- Bảo đảm key mới thực sự là key material mới.

### 13.4. Atomic và durable là hai thuộc tính khác nhau

`AtomicLong.getAndIncrement()` giúp các thread lấy giá trị khác nhau trong một process. Nó không đảm bảo counter tồn tại sau crash. Database transaction, durable sequence hoặc central allocator có thể cung cấp tính bền vững, nhưng phải xác minh isolation/rollback và không để restore snapshot làm bộ đếm lùi.

## 14. Điều gì xảy ra nếu nghi ngờ đã tái sử dụng nonce?

Không nên coi nonce collision là lỗi hiển thị vô hại. Quy trình xử lý sự cố nên bao gồm:

1. **Dừng mã hóa mới bằng key bị ảnh hưởng** cho đến khi đã khống chế được allocator.
2. Xác định các lần mã hóa, ciphertext và các instance có thể đã dùng trùng cặp key/nonce.
3. Kiểm tra log/metadata nonce nếu hệ thống lưu; tránh thu thập plaintext nhạy cảm không cần thiết.
4. Tạo và triển khai key mới qua key management đã phê duyệt.
5. Đánh dấu key cũ decrypt-only khi cần đọc dữ liệu cũ; không tiếp tục dùng nó để encrypt.
6. Đánh giá khả năng lộ plaintext/giả mạo và thông báo theo quy trình security incident của tổ chức.
7. Sửa nguyên nhân gốc: allocator, restart/restore, concurrency, key sharing hoặc key rotation.
8. Thêm regression tests và telemetry để phát hiện nonce collision/allocator rollback.

**Không thể “sửa” ciphertext cũ bằng cách đổi nonce ở metadata.** Nonce phải đúng với phép mã hóa đã tạo ciphertext/tag. Nếu cần tái mã hóa dữ liệu, decrypt và encrypt lại bằng key/nonce mới trong một quy trình được bảo vệ.

## 15. Những lỗi phổ biến

### Lỗi 1. Tạo một IV cố định cho mọi bản ghi

Ví dụ `byte[] iv = new byte[12]` rồi tái sử dụng. Mảng toàn 0 không phải nonce mới. **Sửa:** cấp nonce mới cho mỗi lần encrypt theo construction đã chọn.

### Lỗi 2. Dùng cùng nonce vì plaintext giống nhau

Cùng plaintext không làm reuse an toàn. **Sửa:** vẫn cấp nonce mới cho từng encryption invocation.

### Lỗi 3. Nghĩ AAD khác nhau là đủ

AAD không tạo nonce space mới. **Sửa:** uniqueness vẫn áp dụng cho key/nonce.

### Lỗi 4. Tạo Cipher mới nhưng truyền lại IV cũ

Object mới không thay đổi input mật mã. **Sửa:** mỗi lần mã hóa phải có nonce mới.

### Lỗi 5. Dùng java.util.Random hoặc ThreadLocalRandom

Các RNG này không phải CSPRNG cho mục đích bảo mật. **Sửa:** dùng SecureRandom khi thuật toán/IV construction cho phép random generation.

### Lỗi 6. Cho rằng random 96-bit chắc chắn không trùng

Collision vẫn có xác suất. **Sửa:** tuân thủ giới hạn GCM RBG construction và tính trên toàn bộ instance dùng key.

### Lỗi 7. Dùng random nonce cho ChaCha20-Poly1305 theo ví dụ GCM

RFC 8439 yêu cầu nonce unique và mô tả counter-based construction, không random. **Sửa:** theo đúng RFC/protocol nonce allocator.

### Lỗi 8. Dùng timestamp làm nonce

Clock không đảm bảo uniqueness/monotonicity. **Sửa:** counter hoặc CSPRNG construction đúng thuật toán.

### Lỗi 9. Counter reset sau restart

Process mới có thể tái sử dụng nonce cũ. **Sửa:** durable counter hoặc namespace mới đã được cấp chắc chắn.

### Lỗi 10. Dùng AtomicLong như global allocator

AtomicLong chỉ đồng bộ trong process. **Sửa:** phối hợp giữa các process/region hoặc dùng key riêng theo instance với KDF design phù hợp.

### Lỗi 11. Backup restore làm counter lùi

Key cũ vẫn hoạt động nhưng counter quay lại. **Sửa:** không encrypt với key đó nếu không chứng minh được uniqueness; rotate key.

### Lỗi 12. Cấp cùng sender ID/prefix cho nhiều worker

Các counter riêng vẫn va chạm khi prefix giống nhau. **Sửa:** namespace phải unique dưới cùng key.

### Lỗi 13. Retry encrypt bằng nonce vừa dùng

Có thể tái sử dụng nonce sau timeout/lỗi. **Sửa:** burn nonce đã cấp; retry encryption với nonce mới hoặc resend envelope cũ.

### Lỗi 14. Nhầm resend ciphertext với encrypt lại

Resend cùng envelope là gửi lại kết quả cũ; tạo ciphertext mới là một encryption invocation mới. **Sửa:** tách retry transport khỏi retry crypto.

### Lỗi 15. Không lưu nonce cùng ciphertext

Bên nhận không thể khôi phục tham số giải mã. **Sửa:** envelope chứa algorithm/version, key ID, nonce, ciphertext/tag.

### Lỗi 16. Giữ nonce bí mật nhưng không giữ key bí mật

Nonce không thay key. **Sửa:** bảo vệ key trong KMS/HSM/secret management; nonce có thể lưu cạnh ciphertext.

### Lỗi 17. Chỉ đếm nonce trong một JVM

Các service khác có thể cùng dùng key. **Sửa:** inventory tất cả producer/instances có key material đó.

### Lỗi 18. Đổi alias rồi reset counter

Alias khác có thể trỏ cùng key bytes. **Sửa:** xác minh key material mới trước khi bắt đầu nonce space mới.

### Lỗi 19. Thay key nhưng không lưu key ID trong envelope

Decrypt có thể dùng nhầm key hoặc thử nhiều key không kiểm soát. **Sửa:** lưu key identifier/version không nhạy cảm và quản lý key rotation.

### Lỗi 20. Bỏ qua AAD khi decrypt

Tag verification thất bại hoặc code vô tình không xác thực metadata cần bảo vệ. **Sửa:** tái tạo AAD chính xác như lúc encrypt.

### Lỗi 21. Dùng plaintext trước khi GCM tag xác thực hoàn tất

Dữ liệu trung gian có thể chưa được xác thực. **Sửa:** chỉ chấp nhận plaintext sau khi doFinal hoàn thành thành công.

### Lỗi 22. Tưởng nonce uniqueness chống replay

Nonce không tự ngăn gửi lại một ciphertext cũ. **Sửa:** dùng message ID/sequence state và replay policy riêng.

### Lỗi 23. Trộn nonce của các thuật toán mà không có protocol

Độ dài và yêu cầu nonce khác nhau theo thuật toán. **Sửa:** quản lý riêng theo AEAD algorithm và format version.

### Lỗi 24. Dùng chung key raw cho nhiều protocol

Một lỗi ở nonce allocator của protocol này có thể ảnh hưởng protocol khác. **Sửa:** key separation qua KDF/context và key management có kiểm chứng.

### Lỗi 25. Chỉ kiểm tra nonce không trùng trong unit test nhỏ

Một mẫu nhỏ không chứng minh uniqueness phân tán. **Sửa:** test allocator restart/concurrency/range và audit vận hành.

### Lỗi 26. Không có giới hạn số lần dùng key

Một hệ thống có thể vượt giới hạn của IV construction hoặc algorithm. **Sửa:** enforce invocation/data-volume limits và rotation policy.

### Lỗi 27. Tái dùng key cũ sau khi counter state mất

Không biết counter đã dùng tới đâu. **Sửa:** key mới; không đoán counter cũ.

### Lỗi 28. Tự sửa nonce trong ciphertext metadata

Tag không còn khớp. **Sửa:** giữ đúng nonce đã dùng; nếu cần chuyển đổi, decrypt rồi encrypt lại.

## 16. Bài tập thực hành và đáp án

**Bài 1.** Với AES-GCM, cùng key và cùng IV có thể dùng để encrypt hai plaintext khác nhau không?

**Đáp án:** Không. IV phải duy nhất cho mỗi lần mã hóa với key đó.

**Bài 2.** Nonce có cần được giữ bí mật như AES key không?

**Đáp án:** Không. Nonce thường được lưu/truyền cùng ciphertext; key mới là bí mật.

**Bài 3.** Khi decrypt một ciphertext, có dùng lại nonce lúc encrypt không?

**Đáp án:** Có. Decrypt phải dùng đúng nonce đã lưu với ciphertext. Quy tắc cấm là dùng lại nonce cho một lần **encrypt mới** cùng key.

**Bài 4.** Thay AAD có cho phép tái sử dụng nonce không?

**Đáp án:** Không. AAD khác không sửa vi phạm key/nonce uniqueness.

**Bài 5.** AES-GCM thường dùng IV bao nhiêu bytes theo khuyến nghị NIST?

**Đáp án:** 12 bytes (96 bits).

**Bài 6.** `GCMParameterSpec(128, nonce)` có nghĩa gì?

**Đáp án:** Authentication tag dài 128 bits và IV được cung cấp bởi mảng nonce.

**Bài 7.** Có nên dùng `new Random()` để tạo IV bảo mật?

**Đáp án:** Không. Dùng SecureRandom nếu random IV construction phù hợp với thuật toán.

**Bài 8.** Random 96-bit nonce có bảo đảm tuyệt đối không bao giờ trùng không?

**Đáp án:** Không. Nó làm xác suất rất nhỏ; vẫn phải tuân thủ giới hạn số lần gọi và phạm vi key.

**Bài 9.** NIST SP 800-38D đặt giới hạn global nào cho RBG-based IV construction?

**Đáp án:** Bản tiêu chuẩn đang công bố quy định tổng không quá 2^32 lần gọi với một key, trên các instance liên quan; phải tuân thủ thêm các điều kiện chi tiết khác.

**Bài 10.** Có thể dùng random nonce trong ChaCha20-Poly1305 theo hướng dẫn AES-GCM không?

**Đáp án:** Không nên. RFC 8439 yêu cầu nonce unique và mô tả deterministic/counter construction, không random generation.

**Bài 11.** AtomicLong đảm bảo uniqueness giữa hai pod không?

**Đáp án:** Không. Nó chỉ atomic trong một JVM/process.

**Bài 12.** Counter có thể reset sau khi service restart nếu key vẫn giữ nguyên không?

**Đáp án:** Không. Counter/namespace phải tiếp tục bền vững hoặc dùng một namespace mới đã được cấp bảo đảm.

**Bài 13.** Nếu backup restore làm counter lùi nhưng key cũ còn dùng, nên làm gì?

**Đáp án:** Ngừng encrypt bằng key đó cho tới khi uniqueness được chứng minh; thường cần rotate sang key mới.

**Bài 14.** Hai key alias có cùng key bytes có dùng chung nonce domain không?

**Đáp án:** Có. Alias khác không tạo key material khác.

**Bài 15.** Có thể bỏ phí một dải counter khi worker crash không?

**Đáp án:** Có. Bỏ phí an toàn hơn cấp lại range có thể đã được sử dụng.

**Bài 16.** Nếu encrypt bị timeout, có thể retry cùng nonce không?

**Đáp án:** Không. Dùng nonce mới cho lần encrypt mới, hoặc gửi lại chính envelope/ciphertext đã tạo nếu đó chỉ là retry transport.

**Bài 17.** Nonce có cần lưu trong DB cạnh ciphertext không?

**Đáp án:** Có, hoặc truyền qua một envelope khác để decrypt nhận đúng nonce.

**Bài 18.** Nonce uniqueness có chống replay một ciphertext cũ không?

**Đáp án:** Không. Cần message ID/sequence state và replay detection ở protocol/application.

**Bài 19.** Nếu nonce trùng nhưng plaintext cũng giống hệt, có an toàn không?

**Đáp án:** Không. Vẫn vi phạm yêu cầu uniqueness và tạo điều kiện lộ cấu trúc/ảnh hưởng xác thực.

**Bài 20.** GCM tag verification thường báo lỗi gì trong Java?

**Đáp án:** `AEADBadTagException` khi authentication tag không hợp lệ, ví dụ ciphertext/AAD/nonce/key không khớp hoặc dữ liệu bị sửa.

**Bài 21.** Đổi AAD có thể khôi phục ciphertext đã mã hóa bằng nonce trùng không?

**Đáp án:** Không. AAD không sửa nonce reuse.

**Bài 22.** Tạo Cipher object mới mỗi lần có đủ tránh nonce reuse không?

**Đáp án:** Không nếu code vẫn truyền lại cùng key và nonce. Cần nonce allocator đúng.

**Bài 23.** Nếu key mới được tạo thật sự độc lập, nonce counter có thể bắt đầu lại không?

**Đáp án:** Có, trong nonce domain của key mới, theo construction và key-management policy. Đổi alias cho cùng bytes thì không.

**Bài 24.** GCM IV 12 bytes và ChaCha20-Poly1305 nonce 12 bytes có nghĩa hai thuật toán dùng chung một nonce allocator tùy ý không?

**Đáp án:** Không. Chúng có quy tắc construction riêng; quản lý theo thuật toán/protocol và key separation.

**Bài 25.** Trong Java demo, vì sao nonce được clone khi lưu vào EncryptedMessage?

**Đáp án:** Tránh caller thay đổi mảng bytes sau khi envelope được tạo, làm nonce giải mã khác nonce lúc mã hóa.

## 17. Checklist production

- [ ] Xác định thuật toán AEAD cụ thể và nonce/IV requirement của đúng chuẩn.
- [ ] Với AES-GCM, dùng construction IV hợp lệ; 96-bit là lựa chọn NIST khuyến nghị phổ biến.
- [ ] Với ChaCha20-Poly1305 theo RFC 8439, dùng nonce 96-bit unique và counter/deterministic allocation phù hợp.
- [ ] Không áp dụng random-IV strategy của GCM cho ChaCha20-Poly1305.
- [ ] Mỗi lần encrypt bằng cùng key có nonce mới theo contract.
- [ ] Tính uniqueness trên mọi thread/process/instance/region dùng cùng key material.
- [ ] Không xem alias/key ID khác nhau là key khác nếu raw bytes vẫn giống nhau.
- [ ] Nếu dùng random GCM IV, dùng SecureRandom và enforce NIST RBG-based limits trên toàn key scope.
- [ ] Không dùng Random, ThreadLocalRandom, Math.random, timestamp hoặc fixed nonce thay cho construction hợp lệ.
- [ ] Nếu dùng counter, có namespace unique, counter atomic và durable.
- [ ] Counter không reset khi restart, deploy, failover, backup restore hoặc rollback.
- [ ] Range đã cấp cho worker được xem là consumed khi không chứng minh chắc phần chưa dùng.
- [ ] Có exhaustion policy; không wrap counter.
- [ ] Mỗi key rotation tạo key material mới thật sự; old key chuyển decrypt-only nếu cần.
- [ ] Tách key theo algorithm/purpose bằng key management/KDF chuẩn, không tự thiết kế.
- [ ] Mỗi retry encryption dùng nonce mới; retry transport có thể gửi lại envelope cũ.
- [ ] Lưu nonce cùng ciphertext/tag và key identifier/version.
- [ ] AAD được canonicalize và tái tạo đúng ở phía decrypt.
- [ ] Chỉ chấp nhận plaintext sau khi authentication tag verification thành công.
- [ ] Có replay protection riêng nếu protocol yêu cầu chống gửi lại ciphertext.
- [ ] Có telemetry về invocation count, allocator state, key version và exhaustion; không log key/plaintext nhạy cảm.
- [ ] Unit/integration tests có concurrency, restart, multi-process allocation, range reservation, rollback và key rotation.
- [ ] Nếu nghi nonce reuse, dừng encrypt với key bị ảnh hưởng, điều tra và rotate theo incident procedure.
- [ ] Không thay nonce metadata của ciphertext đã tạo; cần đổi thì decrypt và encrypt lại.

## 18. Tài liệu chuẩn và nguồn tham khảo hiện hành

1. [NIST SP 800-38D — Galois/Counter Mode (GCM) and GMAC: IV uniqueness, 96-bit recommendation, deterministic/RBG constructions và limits](https://csrc.nist.gov/pubs/sp/800/38/d/final)
2. [NIST SP 800-38D, Appendix A — Importance of the Uniqueness Requirement on IVs](https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=51288)
3. [RFC 8439 — ChaCha20 and Poly1305 for IETF Protocols: 96-bit nonce và yêu cầu unique per key](https://datatracker.ietf.org/doc/rfc8439/)
4. [Oracle Java SE 26 — Java Cryptography Architecture Reference Guide: AES/GCM/NoPadding, AAD và không reuse key/IV](https://docs.oracle.com/en/java/javase/26/security/java-cryptography-architecture-jca-reference-guide.html)
5. [Oracle Java SE 26 — Cipher: khởi tạo cipher, parameter generation và IV retrieval](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/crypto/Cipher.html)
6. [Oracle Java SE 26 — GCMParameterSpec: IV và authentication tag length](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html)
7. [Oracle Java SE 26 — SecureRandom: cryptographically strong random number generator](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/SecureRandom.html)
8. [Oracle Java SE 26 — AEADBadTagException: lỗi xác thực tag](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/crypto/AEADBadTagException.html)
9. [OWASP Cryptographic Storage Cheat Sheet: authenticated encryption, secure randomness, IV/nonce handling và key rotation](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html)
10. [RFC 5869 — HMAC-based Extract-and-Expand Key Derivation Function (HKDF): context-separated key derivation](https://datatracker.ietf.org/doc/html/rfc5869)

**Ghi nhớ cuối cùng:** Nonce không phải bí mật, nhưng **không được tái sử dụng với cùng key trong các lần mã hóa AEAD yêu cầu uniqueness**. Phạm vi kiểm tra là toàn bộ hệ thống đang dùng key material đó. Với AES-GCM, random 96-bit IV bằng SecureRandom là một construction phổ biến nhưng có xác suất va chạm và giới hạn invocation; deterministic allocator phải duy trì uniqueness qua thread, process, restart và restore. Với ChaCha20-Poly1305, theo RFC 8439 dùng nonce unique/counter, không áp dụng random-IV recipe của GCM. Khi không thể chứng minh nonce allocator còn tiếp tục từ trạng thái an toàn, dừng encrypt bằng key cũ và chuyển sang key mới theo quy trình quản lý khóa.
