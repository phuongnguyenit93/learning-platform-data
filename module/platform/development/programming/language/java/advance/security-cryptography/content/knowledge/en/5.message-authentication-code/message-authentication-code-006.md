# 5.6 Kiểm tra tag, dữ liệu bị sửa, sai khóa và giới hạn cắt ngắn tag

Một ứng dụng Java nhận được thông điệp cùng một chuỗi byte được gọi là **tag**. Để quyết định có tin nội dung hay không, ứng dụng phải tính hoặc xác minh tag theo **đúng thuật toán, đúng khóa, đúng bytes, đúng tham số và đúng độ dài**. Nếu bỏ qua một trong các điều kiện đó, dữ liệu bị sửa có thể được chấp nhận hoặc thông điệp hợp lệ bị từ chối.

Bài này tập trung vào ba tình huống: (1) dữ liệu, tag hoặc metadata bị sửa; (2) bên xác minh sử dụng sai khóa; (3) tag bị cắt ngắn hoặc chương trình chấp nhận độ dài tag không đúng chính sách. Những tình huống này gặp trong HMAC của webhook, thông điệp giữa các dịch vụ, AES-GCM bảo vệ dữ liệu lưu trữ và các giao thức xác thực thông điệp khác.

Sau bài học, bạn cần phân biệt được **tag của MAC** với **tag của mã hóa có xác thực (AEAD)**; hiểu giới hạn của mỗi tag; triển khai kiểm tra bằng JCA/JCE; viết negative test cho dữ liệu sai, khóa sai và tag thiếu byte; và thiết kế quy tắc độ dài tag không cho phía gửi tự ý làm yếu kiểm tra.

## 1. Tag là gì? Tag chứng minh được điều gì?

### 1.1. MAC tag: dùng bí mật chung để xác thực thông điệp

Với **Message Authentication Code (MAC)**, bên gửi và bên nhận cùng nắm một khóa bí mật. Bên gửi tính tag từ khóa và thông điệp; bên nhận tính lại trên **chính chuỗi byte nhận được** rồi kiểm tra.

~~~text
Bên gửi                          Bên nhận
--------                         --------
Khóa K + thông điệp M            Khóa K + thông điệp M'
          |                                 |
          v                                 v
      MAC(K, M)                        MAC(K, M')
          |                                 |
       tag T ---------------------->  expected T'
                                             |
                                             v
                                kiểm tra độ dài + so khớp tag
                                             |
                               hợp lệ / từ chối thông điệp
~~~

Nếu dùng thuật toán MAC an toàn, khóa bí mật được bảo vệ và quy trình kiểm tra chính xác, tag hợp lệ cho biết nội dung đã được tạo bởi một chủ thể **biết khóa chung**, và nội dung đó không bị sửa theo cách vượt qua cơ chế MAC. Vì hai bên cùng giữ khóa, HMAC không cho bên thứ ba biết chính xác bên nào đã tạo tag.

**HmacSHA256** trong JCA tạo kết quả đầy đủ **32 byte = 256 bit**. Một giao thức có thể chọn một đoạn đầu cố định của tag theo thiết kế và giới hạn bảo mật, nhưng không để client tùy ý đưa độ dài cần so sánh.

### 1.2. AEAD tag: kiểm tra dữ liệu mã hóa trước khi sử dụng

Với **Authenticated Encryption with Associated Data (AEAD)** như AES-GCM, bên mã hóa dùng khóa, IV/nonce, plaintext và có thể cả AAD để tạo **ciphertext cùng authentication tag**. Bên giải mã phải kiểm tra tag bằng chính thuật toán AEAD. Nếu tag không hợp lệ, thao tác giải mã bị từ chối.

~~~text
AES-GCM encrypt:
  key + IV + plaintext + AAD
              |
              v
       ciphertext || tag

AES-GCM decrypt:
  key + IV + ciphertext || tag + AAD
              |
              v
       kiểm tra tag bằng Cipher.doFinal()
              |
       thành công: plaintext đã xác thực
       thất bại: không sử dụng plaintext
~~~

Trong JCE, **Cipher.getInstance("AES/GCM/NoPadding")** và **GCMParameterSpec** lựa chọn transformation và tag length; **Cipher.doFinal** kiểm tra authentication tag khi giải mã. Khi xác thực thất bại thường nhận **AEADBadTagException**. Không dùng MessageDigest.isEqual để tự thay thế phép xác minh GCM bên trong Cipher.

### 1.3. Phân biệt với SHA-256, chữ ký số và checksum

| Cơ chế | Có khóa bí mật không? | Kiểm tra được gì? | Không tự giải quyết gì? |
| --- | --- | --- | --- |
| SHA-256 thuần | Không | Dấu vân tay dữ liệu; hữu ích khi giá trị chuẩn đến từ nguồn tin cậy | Người sửa thông điệp có thể tính lại hash; không xác thực người gửi. |
| CRC/checksum | Không | Phát hiện một số lỗi truyền dẫn/ngẫu nhiên | Không chống đối thủ chủ động sửa dữ liệu. |
| HMAC-SHA256 | Có, khóa chung | Tính toàn vẹn và xác thực bên biết khóa | Không mã hóa nội dung, không chống replay, không quy trách nhiệm riêng một bên giữ khóa. |
| AES-GCM tag | Có, khóa AEAD | Xác thực ciphertext và AAD, kết hợp bảo mật plaintext | Không kiểm tra quyền người dùng, không ngăn phát lại bản mã hợp lệ. |
| Chữ ký số | Khóa riêng để ký, khóa công khai để kiểm tra | Tính toàn vẹn và nguồn ký khi public key được xác thực | Không tự giữ bí mật nội dung và không thay thế kiểm tra quyền. |

**Một tag hợp lệ không có nghĩa yêu cầu nghiệp vụ được phép thực hiện.** Nó chỉ chứng minh những thuộc tính mật mã cụ thể theo khóa, thuật toán và bytes đã bảo vệ. Ví dụ webhook thanh toán có HMAC đúng vẫn có thể là webhook đã xử lý trước đó hoặc một yêu cầu bị phát lại.

## 2. Điều kiện tiên quyết để kiểm tra tag đúng

Việc so sánh tag chỉ có ý nghĩa khi cả hai bên thống nhất một **hợp đồng mật mã**.

| Thành phần | Điều phải thống nhất | Hệ quả khi sai |
| --- | --- | --- |
| Thuật toán | HmacSHA256, AES-GCM, GMAC hay thuật toán được giao thức quy định | Tính ra tag khác hoặc không thể khởi tạo API. |
| Khóa và phiên bản | Đúng secret/key ID, đúng quyền sử dụng, đúng phiên bản sau rotation | Tag không khớp; đôi khi báo sai khóa với thông điệp hợp lệ. |
| Bytes đầu vào | UTF-8, thứ tự trường, dấu cách, xuống dòng, canonicalization, raw body | Cùng ý nghĩa nghiệp vụ nhưng tag khác. |
| Metadata xác thực | Loại thông điệp, tenant, phiên bản, timestamp, nonce, AAD | Kẻ tấn công có thể sửa phần không được tag bảo vệ. |
| Định dạng tag | Raw bytes, hex, Base64/Base64url, vị trí tag, quy tắc padding | Giải mã nhầm, mất byte 0 hoặc sai độ dài. |
| Độ dài tag | Chính sách cố định theo phiên bản giao thức/khóa | Cắt ngắn nhầm gây lỗi; tự động giảm độ dài gây rủi ro giả mạo. |
| AEAD IV/nonce | IV tương ứng với bản mã, độ dài và quy tắc duy nhất theo khóa | Sai tag hoặc phá vỡ bảo đảm an toàn khi tái sử dụng IV. |
| Thứ tự xử lý | Parse → kiểm tra chính sách → xác thực → xử lý nghiệp vụ | Tin dữ liệu chưa xác thực hoặc trả lỗi lộ thông tin. |

Đặc biệt, MAC được tính trên **byte**, không trên một đối tượng Java trừu tượng. Hai chuỗi JSON có cùng các field nhưng thứ tự field, khoảng trắng, escape, Unicode hay ký tự xuống dòng khác nhau có thể cho tag khác nhau. Với webhook, nếu tài liệu nhà cung cấp yêu cầu HMAC trên **raw request body**, hãy giữ raw bytes thay vì parse JSON rồi serialize lại.

Tránh xây payload bằng cách ghép các field tùy ý như "a" + "bc" và "ab" + "c": hai bộ field khác nhau có thể cho cùng byte sequence. Hãy dùng serialization xác định, tiền tố độ dài hoặc định dạng canonical được giao thức công nhận.

## 3. Quy trình xác minh an toàn

Một pipeline kiểm tra tag nên có thứ tự dễ kiểm chứng:

1. **Nhận dữ liệu như dữ liệu chưa tin cậy.** Giới hạn kích thước request, kiểm tra định dạng envelope, chỉ nhận version/algorithm/key ID trong danh sách cho phép.
2. **Giải mã biểu diễn tag một lần** theo quy tắc cố định (ví dụ Base64url). Giải mã lỗi, thiếu field hoặc dữ liệu rác phải bị từ chối; không tự “sửa” tag để được một giá trị hợp lệ.
3. **Kiểm tra chính sách độ dài trước khi so khớp.** Với HMAC-SHA256-128, tag phải đúng **16 byte sau decode**; không dùng số ký tự Base64/hex như số byte.
4. **Chọn khóa đáng tin cậy** theo phiên bản, tenant hoặc đối tác được cấu hình. Một key ID từ bên ngoài không được phép mở khóa tùy ý hoặc thay đổi thuật toán sang dạng yếu.
5. **Chuẩn bị đúng bytes đã được bảo vệ.** Với HMAC đó là message theo đặc tả; với AES-GCM phải cung cấp đúng IV, AAD, ciphertext và tag.
6. **Xác minh bằng primitive phù hợp.** Với HMAC tự tính tag theo chính sách và so sánh hạn chế timing leak; với AEAD để **Cipher.doFinal** kiểm tra tag.
7. **Nếu thất bại, từ chối trước khi dùng nội dung.** Không fallback từ tag dài sang tag ngắn, không trả plaintext sau khi GCM thất bại, không tự thử nhiều cách canonicalization cho tới khi khớp.
8. **Nếu thành công, tiếp tục kiểm tra freshness, replay, quyền và nghiệp vụ.** Tag không tự chứng minh giao dịch chưa được xử lý, tài nguyên thuộc người gọi hay timestamp còn hạn.

~~~text
Nhận message/tag
    |
    v
Kiểm tra format + version + tag length + key ID
    |
    +-- sai --> REJECT
    |
    v
Chọn khóa hợp lệ + chuẩn bị bytes/AAD chính xác
    |
    v
Verify MAC hoặc AEAD tag
    |
    +-- sai --> REJECT (không dùng nội dung)
    |
    v
Kiểm tra replay / timestamp / authorization / idempotency
    |
    +-- sai --> REJECT
    |
    v
Thực hiện nghiệp vụ
~~~

**Không có “xác thực một nửa”.** Phải hoàn tất toàn bộ xác minh trước khi chấp nhận hoặc thực thi một dữ liệu/thao tác được bảo vệ.

## 4. Dữ liệu bị sửa: những dạng sửa nào phải được phát hiện?

Giả sử bên gửi tính HMAC trên bytes tương ứng với thông điệp **order=42;amount=250000**. Sau đó có kẻ đổi số tiền, thay order ID, sửa timestamp hoặc thay chính tag.

| Thay đổi trên đường truyền | Kết quả mong đợi | Lưu ý |
| --- | --- | --- |
| Thay một byte thuộc message được HMAC bảo vệ | Từ chối | Tính lại bằng khóa đúng sẽ khác với tag đã nhận, trừ khả năng giả mạo cực nhỏ theo độ dài tag. |
| Thay chính một byte tag | Từ chối | So sánh tag phải kiểm tra **toàn bộ độ dài được quy định**. |
| Thay metadata được gắn vào HMAC/AAD | Từ chối | Nếu metadata không nằm trong phạm vi xác thực, tag **không bảo vệ** trường đó. |
| Đổi charset/serialization giữa hai bên | Từ chối tag, dù người dùng thấy nội dung “giống nhau” | Đây có thể là lỗi giao thức, không nhất thiết có tấn công. |
| Thay IV/ciphertext/AAD/tag của AES-GCM | Từ chối giải mã | Phải để AEAD kiểm tra tag; sai IV hoặc khóa cũng có thể gây lỗi tương tự. |
| Gửi lại nguyên thông điệp và tag cũ | Tag vẫn có thể hợp lệ | Chống replay cần timestamp, nonce, transaction ID và trạng thái nghiệp vụ, được bảo vệ bằng tag khi có liên quan. |

**Ranh giới bảo vệ phải trùng ranh giới tin cậy.** Nếu HMAC chỉ bao phủ body mà hệ thống lại tin vào header tenant-id không được bảo vệ, bên trung gian có thể đổi tenant-id mà tag vẫn đúng. Với AEAD, thông tin không cần mã hóa (như record type, version/tenant) nhưng cần xác thực có thể đặt trong **AAD** theo quy tắc chính xác.

### Phân biệt phát hiện sửa đổi và phục hồi nội dung

Xác minh tag trả lời **“nội dung này có hợp lệ theo khóa/giao thức không?”**, chứ không tự sửa nội dung bị hỏng. Khi kiểm tra thất bại, hệ thống thường yêu cầu truyền lại một thông điệp đúng, hoặc báo lỗi có kiểm soát. Không bỏ qua lỗi để “cứ xử lý tạm” vì thông điệp vẫn đọc được một phần.

## 5. Sai khóa: ý nghĩa và các nguyên nhân thường gặp

Dùng một khóa khác với khóa của bên tạo tag dẫn tới kết quả HMAC khác hoặc tag AEAD không hợp lệ với xác suất áp đảo. Dù triệu chứng giống bị sửa dữ liệu, **sai khóa không đồng nghĩa đã có tấn công**: cấu hình, xoay khóa, alias keystore hoặc chọn nhầm tenant cũng có thể là nguyên nhân.

Các trường hợp cần kiểm tra:

- **Key ID sai:** message ghi key-v2 nhưng verifier lấy key-v1; hoặc cơ chế lookup trả khóa của khách hàng khác.
- **Khóa đúng ID nhưng khác bytes:** hai môi trường có secret khác nhau, mã hóa/giải mã Base64 secret sai, copy có thêm newline.
- **Rotation không đồng bộ:** sender đã dùng khóa mới, receiver chưa phân phối/chấp nhận khóa mới theo chính sách.
- **Phân biệt mục đích khóa:** một khóa không nên dùng lẫn cho HMAC, mã hóa và các giao thức khác nếu không có thiết kế derivation/domain separation an toàn.
- **Key handle/provider:** HSM/KMS có thể quản lý khóa qua alias hoặc handle; khóa không xuất được không có nghĩa bị mất, nhưng verifier phải chọn đúng khóa cho đúng phép toán.
- **Khóa sai thuật toán hoặc kích thước:** API có thể ném InvalidKeyException ngay tại init, thay vì đợi bước so khớp tag.

**Phản ứng của hệ thống:** công khai thông điệp lỗi chung như “xác thực thông điệp không thành công”; bên vận hành ghi log an toàn gồm key ID hoặc version đã được phép tiết lộ nội bộ, request ID và loại lỗi kỹ thuật, **không log secret, plaintext nhạy cảm hoặc raw token**.

### Xoay khóa mà vẫn xác minh dữ liệu cũ

Một envelope có thể kèm **key ID/version** nằm trong giao thức đã công bố. Server ánh xạ ID này tới **tập khóa được phép sử dụng**, không làm theo URL/path hay tùy chọn thuật toán do người gửi cung cấp. Với dữ liệu lưu trữ, cần giữ khả năng giải mã các bản ghi cũ cho đến khi migrate hoặc hết thời gian lưu trữ. Với webhook, có thể có cửa sổ chuyển đổi giữa khóa cũ và mới, nhưng phải có hạn rõ và không âm thầm thử vô hạn khóa/thuật toán yếu.

Khi sai khóa, không thể “bỏ kiểm tra tag” để giải mã dữ liệu còn dùng được: chính bước kiểm tra đang ngăn dữ liệu chưa xác thực đi vào xử lý nghiệp vụ.

## 6. Tag dài bao nhiêu là đủ? Hiểu đúng việc cắt ngắn

### 6.1. Phân biệt cắt ngắn được thiết kế và tag bị mất byte

**Cắt ngắn có chủ đích (truncation)** là khi giao thức quy định ngay từ đầu rằng cả hai phía dùng **t bit đầu** của kết quả MAC đầy đủ, với t cố định và mức an toàn được chấp nhận.

**Tag bị thiếu ngoài ý muốn** là khi dữ liệu bị cắt trong lưu trữ, chuyển đổi, log, Base64, copy/paste, serialize hoặc truyền mạng. Tag thiếu byte **phải bị từ chối**, không được xem như một phiên bản bảo mật có độ dài thấp hơn.

Ví dụ với HMAC-SHA256:

| Chính sách | Kích thước nhận | Cách xác minh |
| --- | --- | --- |
| HMAC-SHA256 đầy đủ | 32 byte (256 bit) | Tính đủ 32 byte và so khớp đủ 32 byte. |
| HMAC-SHA256-128 do giao thức quy định | 16 byte (128 bit) | Tính HMAC đủ 32 byte, lấy **16 byte đầu**, buộc tag nhận **đúng 16 byte**, rồi so sánh. |
| Giao thức 16 byte nhưng nhận 15 byte | 15 byte | **Từ chối ngay**; không so sánh 15 byte đầu hoặc tự đổi chính sách. |
| Giao thức 16 byte nhưng nhận 0 byte | 0 byte | **Từ chối ngay**; không chấp nhận tag rỗng. |
| Giao thức 16 byte nhưng nhận 32 byte | 32 byte | **Từ chối**, trừ khi phiên bản giao thức khác được cấu hình rõ ràng. |

Độ dài tag HMAC không phụ thuộc số byte của message. HMAC-SHA256 sinh đủ 32 byte cho message rỗng hay dài; cắt ngắn là **chính sách giao thức**, không phải cách xử lý message ngắn.

### 6.2. Vì sao tag càng ngắn càng dễ bị đoán?

Nếu tag có **t bit đủ khó dự đoán** và thiết kế/giả thiết mật mã thích hợp, một lần thử đoán ngẫu nhiên có xác suất thành công xấp xỉ **2^(-t)**. Sau khoảng q lần thử độc lập, xác suất tổng thể có thể tăng gần mức **q / 2^t** khi q còn nhỏ so với 2^t. Đây chỉ là trực giác bảo mật cho MAC lý tưởng; rủi ro của một chế độ cụ thể còn phụ thuộc số thông điệp, kích thước dữ liệu, nonce, giới hạn thuật toán và thiết kế giao thức.

| Độ dài tag | Số byte | Độ khó đoán trong mô hình đơn giản |
| --- | ---: | --- |
| 32 bit | 4 | Khoảng một trong 2^32 lần thử; không phù hợp làm mặc định cho ứng dụng đa dụng. |
| 64 bit | 8 | Khoảng một trong 2^64; phải đánh giá rất chặt ngân sách giả mạo và vòng đời khóa. |
| 96 bit | 12 | Khoảng một trong 2^96, vẫn phụ thuộc giới hạn thuật toán/giao thức. |
| 128 bit | 16 | Khoảng một trong 2^128 cho một lần đoán trong mô hình lý tưởng. |
| 256 bit | 32 | Kết quả đầy đủ của HMAC-SHA256; không mặc nhiên nâng tổng an toàn hệ thống nếu khóa/quy trình yếu. |

**Không kết luận “tag 64 bit luôn an toàn” chỉ từ con số 2^64.** Một dịch vụ cho hàng tỷ request, nhiều tenant, nhiều khóa hoặc có khả năng thử lại liên tục phải xét ngân sách giả mạo, rate limit, giám sát và tuổi thọ khóa.

RFC 2104, mục 5, mô tả phép truncation HMAC bằng cách lấy các bit bên trái của output và đưa ra khuyến nghị lịch sử **không dưới một nửa độ dài hash và không dưới 80 bit**. Đó không phải giấy phép để tự chọn tag ngắn cho mọi hệ thống hiện đại. Trong bài này, **16 byte (128 bit)** là cấu hình ví dụ rõ ràng cho HMAC-SHA256 khi giao thức cho phép, còn dùng **32 byte đầy đủ** sẽ tránh một quyết định cắt ngắn không cần thiết.

### 6.3. AES-GCM: tag length là tham số của phép mã hóa có xác thực

Với GCM, **GCMParameterSpec(tagLengthBits, iv)** nhận **độ dài tag tính bằng bit**, không phải byte. Chẳng hạn:

- **new GCMParameterSpec(128, iv):** tag 128 bit = 16 byte.
- **iv.length == 12:** IV 96 bit; đây là độ dài IV, **không phải độ dài tag**.
- JCE GCM thường trả về **ciphertext nối tiếp tag** từ Cipher.doFinal khi mã hóa. Khi giải mã với cấu hình tag 128 bit, API xác minh phần tag tương ứng ở cuối input.

NIST SP 800-38D chỉ định các độ dài tag GCM thông dụng **128, 120, 112, 104, 96 bit**; **64 và 32 bit** chỉ dành cho ứng dụng đặc biệt với giới hạn nghiêm ngặt về độ dài dữ liệu và vòng đời khóa. Implementation có thể chỉ hỗ trợ một phần các độ dài đã được nêu. Đừng tự hạ tag length của GCM để giải mã một bản mã bị mất byte; nếu một giao thức hợp lệ dùng độ dài khác, đó phải là **quyết định cố định theo key/profile**, được kiểm thử và có đánh giá an toàn riêng.

**Giới hạn quan trọng khác:** với AES-GCM, không được lặp lại **cặp (khóa, IV)** khi mã hóa thông điệp mới. Lặp IV có thể phá hủy bảo đảm xác thực và bí mật, ngay cả khi tag dài 128 bit. Không dùng độ dài tag lớn để “bù” cho lỗi nonce/IV.

### 6.4. Không thương lượng mức an toàn từ input không đáng tin

Phản ví dụ nguy hiểm về mặt logic:

~~~text
expectedFullTag = HMAC(secret, message)
compareLength = receivedTag.length
accept = compare(first compareLength bytes of expectedFullTag, receivedTag)
~~~

Nếu compareLength do client quyết định, kẻ tấn công có thể giảm số byte phải đoán; **tag rỗng** thậm chí có thể được so sánh với một đoạn rỗng và được chấp nhận trong cách cài đặt thiếu kiểm tra.

Quy tắc đúng: **server chọn thuật toán và số byte tag theo version/khóa đã cấu hình**, kiểm tra tag nhận có đúng độ dài, rồi so sánh chính xác. Không dùng receivedTag.length để cắt expected tag. Không fallback kiểu “thử 16 byte, nếu sai thì thử 8 byte”.

## 7. So sánh HMAC tag trong Java: độ dài cố định và giảm rò rỉ timing

Với **HMAC**, Java cung cấp **javax.crypto.Mac** để tính tag. Khi bên nhận phải so sánh hai tag, nên dùng một cách so sánh không kết thúc sớm phụ thuộc nội dung đối với các mảng có độ dài cố định, chẳng hạn **MessageDigest.isEqual(expected, received)**.

Khác biệt cần hiểu:

- **Arrays.equals** là công cụ so sánh mảng thông thường, không được chọn làm cơ chế chống timing leak cho tag bí mật.
- **MessageDigest.isEqual** trong JDK hiện đại so sánh digest theo cách hạn chế phụ thuộc timing vào **nội dung** của các mảng. Không suy ra từ đó rằng toàn bộ request handler, decode, chọn khóa hay mọi nhánh lỗi là constant-time.
- **Độ dài phải được xác định trước**: từ chối tag null, ngắn hoặc dài hơn chính sách, rồi so sánh hai mảng cùng độ dài.
- Nếu protocol nhận hex hoặc Base64, **decode ra byte[]** trước khi kiểm tra độ dài. Chuỗi hex 32 ký tự chỉ biểu diễn 16 byte; số ký tự không phải số byte.

Trong một ứng dụng thực tế, thực hiện cùng kiểm tra cả hai chiều giao tiếp, áp dụng rate limit và không để bên ngoài phân biệt “key ID có tồn tại”, “tag sai” hay “tag length sai” bằng chi tiết lỗi không cần thiết.

## 8. Ví dụ Java 17+: HMAC-SHA256-128 từ chối tag bị sửa, sai khóa, quá ngắn

Chương trình tạo một khóa HMAC 32 byte bằng SecureRandom, dùng **HmacSHA256**, sau đó lấy **16 byte đầu** làm tag theo chính sách HMAC-SHA256-128. Phía xác minh yêu cầu **đúng 16 byte** và sử dụng MessageDigest.isEqual.

Để chạy, tạo tệp **TagCheckHmacDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class TagCheckHmacDemo {
    private static final int TAG_BYTES = 16;

    private static byte[] hmac(byte[] key, byte[] message) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key, "HmacSHA256"));
        return mac.doFinal(message);
    }

    private static byte[] createTag(byte[] key, byte[] message)
            throws Exception {
        return Arrays.copyOf(hmac(key, message), TAG_BYTES);
    }

    private static boolean verify(
            byte[] key, byte[] message, byte[] receivedTag) throws Exception {
        if (receivedTag == null || receivedTag.length != TAG_BYTES) {
            return false;
        }
        byte[] expected = createTag(key, message);
        return MessageDigest.isEqual(expected, receivedTag);
    }

    public static void main(String[] args) throws Exception {
        byte[] key = new byte[32];
        new SecureRandom().nextBytes(key);
        byte[] original = "amount=250000;order=42"
                .getBytes(StandardCharsets.UTF_8);
        byte[] tag = createTag(key, original);

        byte[] changed = original.clone();
        changed[0] ^= 1;

        byte[] otherKey = key.clone();
        otherKey[0] ^= 1;

        System.out.println("Tag đúng: " + verify(key, original, tag));
        System.out.println("Thông điệp bị sửa: " + verify(key, changed, tag));
        System.out.println("Khóa sai: " + verify(otherKey, original, tag));
        System.out.println("Tag ngắn 15 byte: " +
                verify(key, original, Arrays.copyOf(tag, 15)));
        System.out.println("Tag rỗng: " + verify(key, original, new byte[0]));
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac -encoding UTF-8 --release 17 TagCheckHmacDemo.java
java TagCheckHmacDemo
~~~

Kết quả:

~~~text
Tag đúng: true
Thông điệp bị sửa: false
Khóa sai: false
Tag ngắn 15 byte: false
Tag rỗng: false
~~~

### Giải thích từng điểm bảo mật

1. **Mac.getInstance("HmacSHA256")** tính HMAC đúng thuật toán; **SecretKeySpec** cung cấp khóa bí mật cho phép tính. Đầu ra HMAC gốc là 32 byte.
2. **Arrays.copyOf(..., TAG_BYTES)** chỉ dùng tại **bên tạo expected tag** theo policy cố định 16 byte. Độ dài nhận từ network không ảnh hưởng đến số byte phải đối chiếu.
3. **receivedTag == null hoặc length != 16** dẫn tới từ chối **trước khi so sánh**. Vì thế mảng 15 byte hoặc rỗng không thể làm hệ thống hạ ngưỡng kiểm tra.
4. **MessageDigest.isEqual** nhận hai mảng 16 byte. Với JDK hiện đại, nội dung byte đầu tiên khác nhau không phải điều kiện dừng ngay như một phép so sánh thông thường.
5. **Thay một byte message** làm expected tag khác; **thay khóa** cũng làm expected tag khác. Trong thực tế, xác suất trùng ngẫu nhiên lý thuyết không phải tuyệt đối bằng 0; kết quả kiểm thử trên chỉ mô tả lần chạy với khóa sinh ngẫu nhiên.
6. Mỗi lần gọi **hmac** tạo một **Mac instance riêng**, tránh trộn trạng thái giữa request song song. Khóa và nội dung test chỉ lưu trong bộ nhớ cho chương trình minh họa.

**Khi dùng thật:** đừng dùng khóa hard-coded. Lấy secret từ secret manager/KMS hoặc cơ chế được bảo vệ tương ứng, định danh phiên bản khóa, thêm replay protection theo giao thức và tuyệt đối không log secret. Đừng tự tạo một chính sách truncation khác với đặc tả webhook của nhà cung cấp.

## 9. Ví dụ Java 17+: AES-GCM từ chối ciphertext, khóa, AAD hoặc tag sai

Khác HMAC, **AES-GCM không chỉ phát ra tag** mà còn mã hóa plaintext. Việc so khớp tag do **Cipher.doFinal** thực hiện. Ví dụ dưới đây mã hóa một message với tag **128 bit (16 byte)**, sau đó thực hiện các phép giải mã đúng và sai.

Tạo tệp **TagCheckGcmDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public class TagCheckGcmDemo {
    private static final int TAG_BITS = 128;
    private static final int IV_BYTES = 12;

    private record Sealed(byte[] iv, byte[] ciphertextAndTag) {}

    private static Sealed encrypt(SecretKey key, byte[] plain, byte[] aad)
            throws Exception {
        byte[] iv = new byte[IV_BYTES];
        new SecureRandom().nextBytes(iv);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, iv));
        cipher.updateAAD(aad);
        return new Sealed(iv, cipher.doFinal(plain));
    }

    private static boolean opensAs(SecretKey key, Sealed sealed,
            byte[] aad, byte[] expectedPlain) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, sealed.iv()));
        cipher.updateAAD(aad);
        try {
            byte[] plain = cipher.doFinal(sealed.ciphertextAndTag());
            return Arrays.equals(plain, expectedPlain);
        } catch (AEADBadTagException e) {
            return false;
        }
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128);
        SecretKey key = generator.generateKey();

        byte[] plain = "order=42;amount=250000"
                .getBytes(StandardCharsets.UTF_8);
        byte[] aad = "tenant=A;v=1".getBytes(StandardCharsets.UTF_8);
        Sealed sealed = encrypt(key, plain, aad);

        byte[] changed = sealed.ciphertextAndTag().clone();
        changed[0] ^= 1;

        byte[] wrongKeyBytes = key.getEncoded().clone();
        wrongKeyBytes[0] ^= 1;
        SecretKey wrongKey = new SecretKeySpec(wrongKeyBytes, "AES");

        byte[] wrongAad = "tenant=B;v=1".getBytes(StandardCharsets.UTF_8);
        byte[] shortTag = Arrays.copyOf(sealed.ciphertextAndTag(),
                sealed.ciphertextAndTag().length - 1);

        System.out.println("GCM đúng: " + opensAs(key, sealed, aad, plain));
        System.out.println("Dữ liệu bị sửa: " + opensAs(key,
                new Sealed(sealed.iv(), changed), aad, plain));
        System.out.println("Khóa sai: " +
                opensAs(wrongKey, sealed, aad, plain));
        System.out.println("AAD sai: " +
                opensAs(key, sealed, wrongAad, plain));
        System.out.println("Tag thiếu byte: " + opensAs(key,
                new Sealed(sealed.iv(), shortTag), aad, plain));
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 TagCheckGcmDemo.java
java TagCheckGcmDemo
~~~

Kết quả:

~~~text
GCM đúng: true
Dữ liệu bị sửa: false
Khóa sai: false
AAD sai: false
Tag thiếu byte: false
~~~

### Cách đọc kết quả cho chính xác

- **GCM đúng: true** vì cùng khóa, IV, AAD và ciphertext||tag. Trong ví dụ, opensAs còn so plaintext kết quả với expectedPlain để minh họa test. **Phép xác thực mật mã thực sự được Cipher.doFinal thực hiện**, còn Arrays.equals ở đây chỉ là bước assert của test.
- **Dữ liệu bị sửa: false** vì một byte ciphertext bị thay và tag cũ không còn khớp.
- **Khóa sai: false** vì verifier khởi tạo bằng khóa AES khác. Ứng dụng không nên nói cho client rằng “sai khóa” hay “có tấn công” dựa trên lỗi tag.
- **AAD sai: false** vì AAD được xác thực dù không bị mã hóa. Nếu tenant/version là metadata an ninh, phải đưa các byte tương ứng vào chính sách xác thực.
- **Tag thiếu byte: false** vì mảng đầu vào không còn chứa ciphertext/tag hợp lệ theo profile GCM 128 bit đã cấu hình; **Cipher.doFinal** từ chối.
- **new GCMParameterSpec(TAG_BITS, iv)** nhận **128 bit** và một IV 12 byte; đừng nhầm TAG_BITS với IV_BYTES.
- **new SecureRandom().nextBytes(iv)** tạo IV ngẫu nhiên cho một phép mã hóa. Ví dụ dùng một lần với khóa mới; với ứng dụng có số lượng message lớn hoặc nhiều node, cần thiết kế chiến lược nonce **duy nhất theo cùng khóa**, ngân sách va chạm và vòng đời khóa đúng chuẩn.
- **Sealed** ở đây là record đơn giản chứa mảng byte có thể sửa, để tiện kiểm thử. Record Java không làm mảng bất biến sâu; với production cần kiểm soát ownership/copy dữ liệu và đóng gói version, key ID, IV, ciphertext, tag rõ ràng.

Nếu một provider không hỗ trợ biến thể hoặc tham số đã yêu cầu, ứng dụng có thể ném exception khi khởi tạo. **Không nên bắt mọi Exception rồi trả false một cách im lặng**: phân biệt lỗi cấu hình/khả năng hỗ trợ để vận hành, nhưng phản hồi bên ngoài vẫn tránh lộ thông tin nhạy cảm.

## 10. Rủi ro khi giải mã theo nhiều bước và dùng plaintext trước khi kiểm tra tag

Trong AEAD, thiết kế luồng giải mã cần bảo đảm **không đưa plaintext chưa được xác thực tới nghiệp vụ, log, file hoặc hệ thống khác**. Một số provider/API có thể buffer dữ liệu giải mã để chỉ trả plaintext sau khi tag hợp lệ; đừng mặc định mọi provider và mọi cách dùng streaming đều mang lại tính chất đó.

Quy tắc dễ kiểm chứng:

1. Gọi **updateAAD** với toàn bộ AAD trước khi xử lý ciphertext cho GCM/CCM.
2. Cung cấp đúng ciphertext và tag với **độ dài tag theo giao thức**.
3. Hoàn tất và xác minh bằng **doFinal**.
4. **Chỉ sau khi doFinal thành công**, cho phép logic nghiệp vụ tiêu thụ plaintext.
5. Khi **AEADBadTagException** (hoặc lỗi xác thực theo API) xảy ra, bỏ dữ liệu tạm, không cố phân tích/khôi phục plaintext; không tái sử dụng Cipher đang ở trạng thái lỗi như một thao tác mới.
6. Nếu cần giải mã file lớn theo luồng, dùng định dạng AEAD theo chunk/record có nonce và tag riêng cùng quy tắc kết thúc rõ; không tự coi phần đã xử lý là hợp lệ trước khi có xác thực phù hợp.

Một **MAC-then-encrypt** hoặc **encrypt-then-MAC** tự thiết kế có thể sinh lỗi thứ tự, phân tách khóa, dữ liệu được MAC và xử lý lỗi. Với bài toán mới, ưu tiên cơ chế **AEAD tiêu chuẩn** được hỗ trợ thay vì tự lắp protocol mật mã không được đánh giá.

## 11. Độ dài tag, encoding và giao thức truyền tải: lỗi Java thường gặp

### 11.1. So sánh chuỗi thay vì tag bytes

Nếu API trả tag ở Base64url, server nên decode và so sánh **byte[]**. Base64 (và hex) chỉ mã hóa cách hiển thị; nó không tăng entropy hay biến tag thành bí mật khác. Không chuyển tag thành BigInteger vì có thể mất byte 0 ở đầu, thêm byte biểu diễn dấu hoặc thay đổi format.

Nếu hợp đồng quy định một canonical Base64url representation, hãy kiểm tra đúng format đó trước decode; đừng âm thầm chấp nhận một loạt biến thể đầu vào khác nhau nếu chúng không thuộc giao thức. Nếu hợp đồng nói rõ raw bytes, không tự chuyển sang String và ngược lại với charset mặc định của JVM.

### 11.2. Thay đổi thông điệp trước khi xác minh

Không tự trim, lower-case, bỏ ký tự xuống dòng, parse số tiền rồi stringify lại hoặc serialize JSON mới trước HMAC nếu giao thức ký raw body. Ví dụ:

~~~text
Raw body A: {"amount":250000,"order":42}
Raw body B: { "order": 42, "amount": 250000 }

Ý nghĩa dữ liệu có thể tương đương,
nhưng HMAC(raw A) và HMAC(raw B) thường khác nhau.
~~~

Để có canonicalization thật sự, hai phía phải dùng **cùng một quy tắc được định nghĩa rõ**. Không lặp lại nhiều phép biến đổi cho tới khi một cách tính “tình cờ” khớp tag.

### 11.3. Tag bị cắt bởi giới hạn cột, buffer hoặc serialization

Kiểm tra đơn vị đo:

- HMAC-SHA256 **32 byte** có **64 ký tự hex**, hoặc độ dài chuỗi Base64 tùy padding/profile.
- HMAC-SHA256-128 **16 byte** có **32 ký tự hex**; một chuỗi ngắn hơn có thể là lỗi truyền hay encoding, không tự đổi policy.
- AES-GCM với tag 16 byte thường trả **ciphertext||tag**; nếu cắt mất byte cuối mảng, cần coi envelope không hợp lệ.
- Với JCE, **GCMParameterSpec(128, iv)** chọn độ dài tag 128 **bit**, không phải 128 byte. Độ dài IV cần xét riêng.
- Trong API lưu trữ, giới hạn ký tự của field Base64 không bằng giới hạn byte đã decode.

Không dùng cách khôi phục bằng padding byte 0 hoặc tự thêm ký tự vào tag bị cắt. Phải sửa nguồn lỗi truyền/lưu trữ, xác minh lại với bên gửi.

### 11.4. Sai tham số khi thay đổi provider/JDK

Một provider có thể không hỗ trợ một tag length GCM cụ thể dù chuẩn cho phép; việc lựa chọn transformation, key type, IV length và AAD còn phụ thuộc implementation. Ghi nhận provider và kết quả kiểm thử tương thích ở môi trường triển khai; **không tự giảm độ dài tag khi một provider từ chối tham số**.

### 11.5. So sánh byte không đổi thời gian nội dung chưa đủ cho toàn hệ thống

Dù dùng MessageDigest.isEqual, thời gian xử lý vẫn có thể khác ở bước parse Base64, key lookup, đọc database, exception hoặc truy cập KMS/HSM. Giải pháp là thiết kế lỗi có kiểm soát, rate limit, không tiết lộ bí mật; không khẳng định cả endpoint constant-time chỉ nhờ một hàm so sánh mảng.

## 12. Ví dụ vận dụng: xác minh webhook thanh toán

Giả sử cổng thanh toán gửi request có timestamp, transaction ID, raw body và HMAC. Một luồng xác minh đúng cần:

1. Nhận **raw body bytes** với giới hạn kích thước; lấy tag, timestamp, key ID từ những header **được giao thức định nghĩa**.
2. Parse header an toàn, kiểm tra định dạng và độ dài decoded tag **đúng policy**.
3. Tìm secret đúng đối tác và key version từ cấu hình tin cậy; không lấy secret trực tiếp từ request.
4. Tạo byte sequence được HMAC bảo vệ theo đặc tả nhà cung cấp (ví dụ có timestamp + body với delimiter/canonicalization rõ). Không được tự chế nếu bên gửi có đặc tả khác.
5. Tính HMAC và so sánh đúng số byte; thất bại thì từ chối, **chưa xử lý thanh toán**.
6. Kiểm tra timestamp/freshness và ID giao dịch theo chính sách; đảm bảo các trường dùng để chống replay cũng nằm trong phạm vi xác thực hoặc được gắn với ngữ cảnh tin cậy.
7. Kiểm tra trạng thái giao dịch hiện tại và xử lý **idempotent**. Webhook hợp lệ gửi lại không được cộng tiền hoặc phát hành hàng nhiều lần.
8. Đưa ra kết quả chung phù hợp cho phía gửi, ghi log an toàn phục vụ truy vết nhưng không chứa khóa hoặc thông tin nhạy cảm.

Ví dụ: kẻ tấn công lấy được một webhook đã ký hợp lệ và gửi lại **nguyên văn**. HMAC vẫn hợp lệ vì bytes và tag không thay đổi; ứng dụng phải dùng transaction ID, timestamp, nonce hoặc dữ liệu nghiệp vụ để từ chối thao tác lặp. Ngược lại, nếu kẻ tấn công sửa amount nhưng không có khóa, tag không hợp lệ và bị từ chối tại bước xác minh.

Nếu giao thức dùng **chữ ký số** thay vì HMAC, luồng tương tự về nguyên tắc kiểm tra bytes và freshness, nhưng dùng **Signature.verify** cùng public key được xác minh nguồn; không tự ép thông điệp sang HMAC.

## 13. Thiết kế envelope và quản lý phiên bản cho dữ liệu lưu trữ

Với một ứng dụng Java lưu bản mã AES-GCM, có thể thiết kế một record versioned ở cấp ứng dụng:

~~~text
RecordV1:
  version       = 1
  keyId         = ID khóa dùng để chọn đúng khóa AES đã được cấp phép
  iv            = 12 byte theo chính sách nonce
  ciphertext    = bytes mã hóa
  tag           = 16 byte cuối của AES-GCM output
  aad           = bytes ràng buộc tenant + loại record + version
~~~

Đây là **ví dụ hợp đồng ứng dụng**, không phải định dạng lưu trữ tiêu chuẩn do JCA tự sinh. Những điểm phải chốt rõ:

- Nếu đưa version/keyId/tenant vào AAD, cần có **quy tắc serialization bytes chính xác**, tránh ghép chuỗi mơ hồ.
- Khóa giải mã phải được truy xuất theo **định danh được phép** và theo đúng tenant; người gửi không được điều khiển nơi tìm secret tùy ý.
- Bộ kiểm tra phải biết **tag length** từ profile đã được cấu hình, không lấy length tùy ý từ dữ liệu chưa xác thực.
- IV phải duy nhất **trong toàn bộ phạm vi cùng khóa AES khi mã hóa**, kể cả khi có nhiều node, restart và backup/restore.
- Bản ghi cũ cần có key version/format version đủ để giải mã hoặc migrate sau rotation; không ghi đè tag length/algorithm một cách mập mờ.
- Một record bị hỏng, tag sai hoặc không có khóa thích hợp phải được phân loại là không thể xác minh; không khôi phục plaintext bằng cách bỏ bước xác thực.

**MAC tag không bảo vệ thông tin không nằm trong input MAC/AAD.** Nếu cần bảo vệ key ID hoặc version khỏi bị đổi, có thể ràng buộc metadata đã được quy định với chính sách AAD/cấu trúc xác thực, đồng thời kiểm tra nó theo ngữ cảnh tin cậy của ứng dụng.

## 14. Kế hoạch kiểm thử: cả happy path lẫn các dạng từ chối

Chỉ test một tag đúng là chưa đủ. Các test cần thể hiện điều kiện **chấp nhận duy nhất khi đầy đủ**.

| Ca kiểm thử | Dữ liệu đưa vào | Kỳ vọng |
| --- | --- | --- |
| HMAC hợp lệ | Đúng message bytes + đúng key + đúng 16-byte tag theo profile | Accept. |
| HMAC sửa một byte message | Giữ tag cũ, đổi message bytes | Reject. |
| HMAC sửa một byte tag | Giữ message, đổi tag bytes | Reject. |
| HMAC sai khóa | Key khác key của bên tạo | Reject. |
| HMAC tag rỗng | byte[0] | Reject trước so khớp. |
| HMAC tag 15 byte | Thiếu một byte khi policy 16 byte | Reject, không so khớp prefix. |
| HMAC tag 17 hoặc 32 byte | Dài hơn policy 16 byte | Reject nếu không có profile khác đã thỏa thuận. |
| HMAC sai encoding | Body bị serialize lại khác bytes | Reject; sửa lỗi canonicalization ở giao thức. |
| GCM hợp lệ | Đúng key, IV, AAD, ciphertext và tag 128 bit | Decrypt thành công rồi dùng plaintext. |
| GCM sửa ciphertext/tag | Đảo bit nhưng giữ metadata cũ | Reject qua doFinal, không xử lý plaintext. |
| GCM sai AAD | Tenant/version không khớp | Reject qua doFinal. |
| GCM sai IV | IV không phải IV đã dùng mã hóa | Reject qua doFinal. |
| GCM sai khóa | Khóa khác | Reject hoặc báo lỗi khởi tạo có kiểm soát tùy nguyên nhân. |
| GCM ciphertext/tag bị cắt | Thiếu bytes so với envelope/tag policy | Reject; không tự giảm tagLength. |
| Replay | Gửi lại message + tag đã từng hợp lệ | MAC vẫn có thể đúng; replay/idempotency phải chặn xử lý lặp. |
| Key rotation | Message v1/v2 và key ID phù hợp | Dùng khóa được phép theo version và chính sách còn hiệu lực. |
| Tải đồng thời | Nhiều yêu cầu xác minh khác nhau qua thread pool | Không trộn trạng thái Mac/Cipher hay buffer giữa các request. |

Một bộ test thực tế nên chạy trên provider/JDK triển khai. Thử cả bytes không phải ASCII, dấu tiếng Việt, newline, ký tự Unicode kết hợp và input lớn để phát hiện bất đồng encoding/canonicalization. Test lỗi nên quan sát rằng **không có side effect nghiệp vụ** trước xác thực; chỉ assert exception mà vẫn đã lưu thanh toán là chưa đạt yêu cầu.

### Phân biệt lỗi chấp nhận sai và lỗi từ chối sai

- **False accept:** hệ thống chấp nhận tag không hợp lệ; nguy hiểm nhất vì có thể cho phép giả mạo hoặc thay nội dung.
- **False reject:** tag hợp lệ bị từ chối do chọn sai khóa, format, IV, AAD hoặc canonicalization; gây lỗi tích hợp nhưng không nên “sửa” bằng việc bỏ kiểm tra.
- **Provider/configuration error:** thuật toán/khóa/tham số không được hỗ trợ hoặc key store không hoạt động; cần xử lý như lỗi hệ thống và giữ nguyên nguyên tắc từ chối dữ liệu chưa xác thực.

## 15. Những lỗi tư duy và code cần tránh

1. **So sánh prefix theo tagLength do client gửi:** tạo nguy cơ downgrade, đặc biệt khi nhận tag rỗng hoặc rất ngắn.
2. **Cho phép 8, 12 hoặc 16 byte tùy message mà không có version/profile tin cậy:** không còn một ngưỡng xác thực rõ.
3. **Dùng equals/toString để so tag biểu diễn:** dễ sai encoding, mất byte, hoặc dùng so sánh không được thiết kế chống timing leak.
4. **Dùng SHA-256(message) làm MAC:** không có khóa bí mật và đối thủ có thể tính lại sau khi sửa message.
5. **Đưa chỉ một phần request vào HMAC trong khi tin toàn bộ request:** các field ngoài phạm vi tag có thể bị đổi.
6. **Bỏ qua AEADBadTagException để vẫn dùng plaintext:** làm mất chức năng bảo vệ cốt lõi của AEAD.
7. **Nhầm tag length với IV length:** GCMParameterSpec(128, iv) có tag 128 bit, còn 12 byte là IV thường gặp.
8. **Dùng lại cặp AES-GCM key/IV:** có thể dẫn tới tấn công nghiêm trọng dù tag đủ dài.
9. **Đổi từ tag 128 bit sang 64 bit để “đọc được dữ liệu cũ”:** hạ bảo đảm và có thể không thuộc policy/protocol; phải sửa định dạng hay key/parameter mismatch đúng nguyên nhân.
10. **Không phân biệt verify thất bại với lỗi kỹ thuật:** xử lý lỗi phải giữ tính an toàn, đồng thời giúp vận hành chẩn đoán mà không lộ secret.
11. **Chỉ test đầu vào đúng:** không phát hiện cắt tag, sai khóa, sai tenant/AAD hoặc replay.
12. **Tin tag đồng nghĩa đã phân quyền:** tag chỉ xác thực bytes theo khóa; nghiệp vụ vẫn cần authorization, kiểm tra trạng thái và chống thao tác lặp.

## 16. Tự kiểm tra kiến thức

**Câu 1.** Giao thức dùng HMAC-SHA256-128 nhưng nhận 15 byte. Có nên so sánh 15 byte đầu của expected tag không?  
**Trả lời:** Không. Chính sách yêu cầu **đúng 16 byte**. Từ chối tag 15 byte, dù 15 byte đầu có khớp, bởi độ dài không do client thương lượng.

**Câu 2.** HMAC của body hợp lệ nhưng header tenant ID bị thay đổi. Điều gì có thể xảy ra?  
**Trả lời:** Nếu tenant ID không được bảo vệ bởi MAC hoặc gắn với ngữ cảnh tin cậy, tag trên body vẫn có thể đúng. Phải xác định chính xác metadata nào được HMAC bao phủ và kiểm tra quyền theo tenant ở server.

**Câu 3.** Dùng đúng AES-GCM key và ciphertext, nhưng AAD khác. Java trả gì?  
**Trả lời:** Việc xác minh tag thất bại; với JCE GCM, **Cipher.doFinal** có thể ném **AEADBadTagException**. Không thể kết luận chắc chắn có tấn công chỉ từ exception, vì sai AAD cũng gây ra lỗi.

**Câu 4.** GCMParameterSpec(128, iv) với iv dài 12 byte có nghĩa tag dài 128 byte không?  
**Trả lời:** Không. 128 là **bit tag = 16 byte**; IV dài 12 byte là một tham số khác.

**Câu 5.** Nếu server thấy tag 8 byte, vì sao không tự chuyển sang GCM 64-bit tag để thử giải mã?  
**Trả lời:** Tag length là quyết định của giao thức và chính sách khóa; độ dài ngắn hơn có giới hạn bảo mật nghiêm ngặt và có thể không được provider hỗ trợ. Dữ liệu bị cắt không được hợp thức hóa bằng downgrade.

**Câu 6.** Tag hợp lệ có chứng minh webhook chưa từng được xử lý không?  
**Trả lời:** Không. Cần thêm timestamp/nonce, transaction ID, kiểm tra trạng thái và idempotency được tích hợp vào giao thức.

**Câu 7.** HMAC-SHA256 trả 32 byte nhưng hệ thống dùng 16 byte. Khi xác minh, có tính HMAC trên “nửa message” không?  
**Trả lời:** Không. **Luôn tính HMAC trên toàn bộ message bytes**; chỉ lấy **16 byte đầu output** theo profile HMAC-SHA256-128 được quy định.

**Câu 8.** MessageDigest.isEqual có làm toàn bộ endpoint trở thành constant-time không?  
**Trả lời:** Không. Nó hỗ trợ so sánh digest hạn chế timing leak theo nội dung trong điều kiện thích hợp, nhưng decode, key lookup, rate limit, exception và các bước xử lý khác vẫn có hành vi thời gian riêng.

## 17. Kết luận và tài liệu đối chiếu

Một cơ chế kiểm tra tag đúng đòi hỏi đủ ba bất biến: **(1) đúng khóa và đúng bytes được bảo vệ; (2) thuật toán/tham số và độ dài tag theo policy cố định; (3) xác thực thất bại thì không sử dụng nội dung**. HMAC xác minh bằng cách tính MAC và so sánh tag; AES-GCM xác minh bằng chính Cipher.doFinal. Tag dài bảo vệ tốt hơn trước đoán giả mạo trong các giới hạn thuật toán, nhưng không thay thế quản lý khóa, IV duy nhất, phân quyền, chống replay và kiểm soát vận hành.

Tài liệu kỹ thuật đáng tham khảo:

- [RFC 2104 — HMAC: Keyed-Hashing for Message Authentication, mục 5 về truncated output](https://www.rfc-editor.org/rfc/rfc2104.html)
- [NIST SP 800-38D — Galois/Counter Mode (GCM) and GMAC](https://csrc.nist.gov/pubs/sp/800/38/d/final)
- [Java SE 21 — Mac API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Mac.html)
- [Java SE 21 — Cipher API, GCM/AEAD](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Cipher.html)
- [Java SE 21 — MessageDigest.isEqual](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/MessageDigest.html)
- [Java SE 21 — GCMParameterSpec](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html)