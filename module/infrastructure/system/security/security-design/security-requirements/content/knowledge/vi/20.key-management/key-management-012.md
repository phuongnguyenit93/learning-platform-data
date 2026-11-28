# Data encryption key

## 1. DEK là khóa trực tiếp bảo vệ nội dung dữ liệu

**Data encryption key**, viết tắt **DEK**, là khóa được dùng trực tiếp để mã hóa dữ liệu như nội dung báo cáo, tệp hoặc một nhóm bản ghi theo profile đã chọn. Trong mô hình envelope encryption, DEK lại được bảo vệ bởi một khóa khác, thường gọi là **key encryption key** hoặc **KEK**.

Mối quan hệ khái niệm:

```text
Plaintext --mã hóa bằng DEK--> Ciphertext

DEK --wrap bằng KEK--> Wrapped DEK
```

Hệ thống thường lưu ciphertext, wrapped DEK và metadata cần thiết cùng nhau. KEK được quản lý trong một ranh giới riêng như KMS/HSM hoặc một dịch vụ mật mã được phê duyệt. Khi cần đọc, ứng dụng được phép unwrap DEK rồi sử dụng nó để giải mã dữ liệu theo thiết kế.

Mô hình này được mô tả trong [Google Cloud KMS: Envelope encryption](https://docs.cloud.google.com/kms/docs/envelope-encryption). Các nền tảng có thể khác nhau về nơi sinh DEK và API quản lý; không nên coi một luồng SDK cụ thể là định nghĩa duy nhất của DEK.

Trong thiết kế yêu cầu bảo mật, câu hỏi quan trọng không chỉ là “có dùng DEK không”, mà là DEK bảo vệ phạm vi dữ liệu nào, được sinh và sử dụng ra sao, ai có thể lấy dạng dùng được và điều gì xảy ra khi khóa hoặc dịch vụ quản lý gặp sự cố.

## 2. Phân biệt DEK, KEK và metadata đi kèm

| Thành phần | Vai trò | Yêu cầu bảo vệ chính |
| --- | --- | --- |
| DEK dạng dùng được | Trực tiếp mã hóa/giải mã payload | Không lưu hoặc phát lộ ngoài ranh giới được phép |
| Wrapped DEK | Bản DEK được bảo vệ bởi cơ chế wrapping | Giữ nguyên vẹn, liên kết đúng payload và context |
| KEK hoặc key quản lý | Bảo vệ DEK | Quản lý quyền, vòng đời, trạng thái và khả năng phục hồi |
| Nonce/IV của payload | Tham số của phép mã hóa dữ liệu | Đúng construction, đặc biệt không lặp dưới cùng key khi yêu cầu |
| Authentication tag | Bằng chứng xác thực ciphertext/AAD theo AEAD | Kiểm chứng trước khi tin plaintext |
| Key identity/version | Nhận diện key dùng để wrap hoặc xử lý | Đúng namespace và vật liệu đã dùng |
| Crypto profile | Thuật toán, mode, tham số và giới hạn | Do server/policy kiểm soát, không để client tùy chọn |

“Plaintext DEK” không có nghĩa khóa là một đoạn văn bản đọc được. Nó chỉ nghĩa vật liệu khóa đang ở dạng có thể sử dụng, chưa được bảo vệ bởi lớp wrapping trong ngữ cảnh đang xét. Chuyển các byte đó thành Base64 vẫn không làm khóa được mã hóa bảo mật.

Wrapped DEK không phải salt, password verifier hoặc public key. Lấy nhầm loại dữ liệu có thể dẫn tới thiết kế lưu trữ và vòng đời sai. DEK đối xứng cũng không cần được con người ghi nhớ hoặc dẫn xuất từ một chuỗi mật khẩu ứng dụng tùy ý.

## 3. Ranh giới bảo vệ và mô hình đe dọa

### 3.1. Envelope encryption hữu ích ở đâu?

Giả sử attacker lấy được một bản sao storage chứa dữ liệu báo cáo. Nếu bản sao chỉ có ciphertext và wrapped DEK, còn quyền unwrap được kiểm soát riêng, việc lấy storage không tự đủ để giải mã payload.

Hệ thống cũng có thể quản lý nhiều DEK cho nhiều đơn vị dữ liệu trong khi dùng một số lượng KEK được tổ chức theo tenant, purpose hoặc miền bảo mật. Điều này cho phép giới hạn phạm vi ảnh hưởng khi một DEK bị lộ và hỗ trợ thay lớp bọc mà không nhất thiết xử lý lại toàn bộ dữ liệu.

Tuy nhiên, nếu một service bị chiếm quyền và vẫn có quyền unwrap mọi DEK, mật mã lưu trữ không tự ngăn service đó giải mã trong phạm vi quyền của nó. Cần phối hợp phân quyền dữ liệu, quyền KMS, cô lập workload, audit và giới hạn sử dụng.

### 3.2. Những tài sản cần xác định

Một hồ sơ yêu cầu nên nêu:

- Nội dung payload cần giữ bí mật và xác thực.
- DEK ở dạng dùng được trong bộ nhớ hoặc môi trường xử lý.
- Wrapped DEK và metadata gắn với payload.
- KEK, version và quyền unwrap.
- Các bản sao, backup, cache và artifact đã xuất.
- Khả năng đọc dữ liệu khi một dịch vụ hoặc vùng triển khai gặp sự cố.

Yêu cầu “key tách khỏi dữ liệu” cần được hiểu đúng. Wrapped DEK có thể nằm cùng ciphertext theo thiết kế envelope encryption; điều cần tách ranh giới là vật liệu khóa dùng được hoặc quyền giải bọc, không phải bắt mọi byte có chữ `key` phải nằm trong một database khác.

## 4. Chọn phạm vi của một DEK

### 4.1. Phạm vi quyết định mức chia sẻ rủi ro

| Phương án phạm vi | Lợi ích có thể có | Điều phải kiểm soát |
| --- | --- | --- |
| Một DEK cho một phiên bản object | Tách rõ từng lần ghi, phạm vi ảnh hưởng nhỏ | Số wrapped key, metadata và thao tác quản lý |
| Một DEK cho một object qua nhiều lần ghi | Có thể giảm số lần sinh/unwrap | Nonce, tổng lượng sử dụng và nhiều writer |
| Một DEK cho nhóm dữ liệu có giới hạn | Có thể thuận tiện cho một workload | Ranh giới nhóm, thời gian, số thông điệp và tổng byte |
| Một DEK dùng rộng cho toàn hệ thống | Ít metadata hơn | Phạm vi ảnh hưởng lớn và khó giới hạn sử dụng; cần cơ sở rất rõ nếu xem xét |

Không có lợi ích hiệu năng nào tự cho phép dùng một DEK vô hạn. Phạm vi phải phù hợp thuật toán, dữ liệu, cách dùng và policy. Tách tenant hoặc người dùng cũng phải được đánh giá theo mô hình quyền, không chỉ theo số lượng bản ghi.

### 4.2. Profile minh họa cho báo cáo nhạy cảm

Trong bài này, giả sử chọn:

> Mỗi lần công bố một revision mới của báo cáo, dịch vụ sinh một DEK độc lập cho payload revision đó. DEK không được dùng để bảo vệ báo cáo của tenant khác. Plaintext DEK chỉ tồn tại trong phạm vi xử lý được phép; storage lưu wrapped DEK cùng envelope.

Đây là lựa chọn của ví dụ, không phải tuyên bố mọi hệ thống đều bắt buộc dùng cùng granularity. Một DEK chỉ dùng cho một lần mã hóa vẫn có thể được unwrap nhiều lần để đọc dữ liệu nếu policy cho phép; “dùng một lần để mã hóa” không có nghĩa chỉ được giải mã một lần.

Nếu chuyển sang cache hoặc tái sử dụng DEK, phải cập nhật yêu cầu về nonce, giới hạn số thông điệp, dung lượng, thời gian và thu hồi. Không thay granularity bằng một tối ưu cục bộ mà giữ nguyên hồ sơ rủi ro như trước.

## 5. Sinh DEK từ nguồn được phê duyệt

### 5.1. Sinh cục bộ rồi wrap hoặc sinh qua dịch vụ quản lý

Hai mô hình khái niệm phổ biến:

```text
Mô hình A:
  Bộ sinh khóa được phê duyệt tạo DEK cục bộ
      -> KMS/HSM wrap DEK bằng KEK
      -> dùng DEK cho payload theo profile

Mô hình B:
  Dịch vụ quản lý sinh DEK
      -> trả dạng dùng được và dạng đã được bảo vệ theo API
      -> ứng dụng mã hóa payload bằng DEK
```

Ví dụ, [AWS KMS GenerateDataKey](https://docs.aws.amazon.com/kms/latest/APIReference/API_GenerateDataKey.html) có thể trả plaintext data key và bản encrypted data key để dùng ngoài KMS theo luồng API tương ứng. [Tài liệu data keys của AWS KMS](https://docs.aws.amazon.com/kms/latest/developerguide/data-keys.html) cũng làm rõ ứng dụng phải sử dụng và quản lý data key ở phía ngoài KMS trong mô hình đó.

Không suy rằng gọi một API có tên KMS thì payload tự được mã hóa hoặc mọi vòng đời DEK đã do provider theo dõi. Phải xác định thao tác nào provider thực hiện và phần nào thuộc ứng dụng hoặc SDK client-side encryption.

### 5.2. Các yêu cầu cho nguồn sinh

DEK phải có loại và độ dài đúng profile, đến từ cơ chế mật mã được phép và có quyền sử dụng rõ. Không dùng password, username, timestamp, một UUID được chuyển chuỗi hoặc key hard-code làm DEK theo cách tự thiết kế.

Nếu profile chọn AES-256, key phải có vật liệu phù hợp 256 bit; chuỗi 32 ký tự dễ đoán không tự đạt mức entropy đó. Việc dẫn xuất khóa, nếu có, cần KDF và đầu vào được phê duyệt, không chỉ cắt hoặc hash một định danh nghiệp vụ.

Lỗi sinh hoặc wrap key phải đi theo đường lỗi đã thiết kế. Không dùng một DEK dự phòng dùng chung toàn hệ thống hoặc lưu plaintext để request vẫn có vẻ thành công.

### 5.3. Xác định KEK từ ngữ cảnh đã kiểm tra quyền

Ứng dụng không nên nhận một key URI tùy ý từ client rồi dùng quyền KMS của service để tạo hoặc unwrap key ngoài scope. Tenant, purpose và môi trường phải ánh xạ tới key được phép trong registry hoặc policy tin cậy.

Key ID lưu trong envelope hỗ trợ chọn đúng key lịch sử, nhưng không cấp quyền sử dụng key. Một người biết ID của key tenant B không được làm service giải bọc thay cho tenant B khi chỉ có quyền với tenant A.

## 6. Luồng ghi: từ plaintext đến envelope hoàn chỉnh

### 6.1. Các bước phải được thiết kế cùng nhau

```text
1. Xác minh quyền ghi dữ liệu và ngữ cảnh tenant/purpose.
2. Chọn profile payload và KEK được phép.
3. Sinh DEK mới theo granularity đã chốt.
4. Có được wrapped DEK và identity thực sự dùng để wrap.
5. Mã hóa payload bằng DEK với nonce/AAD đúng profile.
6. Lưu envelope và metadata như một đơn vị nhất quán.
7. Giới hạn thời gian giữ plaintext DEK và thu hồi bản sao ứng dụng quản lý.
```

Thứ tự chi tiết có thể khác theo SDK hoặc construction, nhưng không được công bố payload mã hóa thành công nếu chưa có wrapped DEK hợp lệ để đọc lại. Một ciphertext không còn khả năng lấy DEK có thể trở thành mất dữ liệu.

Nếu storage blob và metadata nằm ở hai hệ thống khác nhau, phải có cơ chế công bố, transaction hoặc quy trình bù phù hợp. Không giả định hai lệnh ghi riêng biệt tự tạo thành một phép ghi nguyên tử.

### 6.2. Envelope mẫu

```json
{
  "envelopeVersion": 1,
  "payloadProfileId": "report-aead-v2",
  "wrappingProfileId": "managed-key-wrap-v1",
  "wrappingKeyRef": "<identity-key-dung-de-wrap>",
  "wrappedDekBase64": "<blob-dek-da-duoc-bao-ve>",
  "payloadNonceBase64": "<nonce-theo-profile>",
  "payloadCiphertextAndTagBase64": "<ciphertext-va-tag>",
  "contextSchemaVersion": 1
}
```

Các giá trị là placeholder, không phải key hoặc ciphertext thật. Không thêm một trường `plaintextDekBase64` vào envelope. Base64 của raw key vẫn là raw key ở dạng biểu diễn khác.

`wrappingKeyRef` phải phản ánh đúng key hoặc abstraction của provider đã dùng. Nếu mã hóa/wrap đi qua alias có thể chuyển, không tra alias một lần riêng rồi gán nhãn theo một version khác với kết quả thực tế.

Nếu provider đưa metadata cần thiết vào blob, phải giữ blob nguyên vẹn theo hợp đồng API. Không parse cấu trúc nội bộ không được công bố rồi phụ thuộc vào nó cho khả năng phục hồi.

### 6.3. Ràng buộc payload với đúng đối tượng

Một context có thể liên quan tới tenant, object, revision và purpose. Cách encode context thành byte phải có version và quy tắc xác định; nối chuỗi mơ hồ có thể làm hai bên hiểu khác nhau.

Với AEAD, payload AAD được xác thực nhưng không được mã hóa. Không đặt secret hoặc dữ liệu cá nhân trực tiếp vào context chỉ vì nó đi cùng ciphertext. Với KMS, một số context còn có thể xuất hiện trong audit log của provider.

Ví dụ, [AWS KMS Encryption context](https://docs.aws.amazon.com/kms/latest/developerguide/encrypt_context.html) mô tả context là dữ liệu không bí mật, được ràng buộc mật mã và cần khớp khi giải mã trong các thao tác hỗ trợ. Context có thể hỗ trợ điều kiện policy, nhưng không thay kiểm tra quyền với tài nguyên ở ứng dụng.

Khi đọc, context mong đợi phải được suy ra từ tài nguyên và policy đã xác lập, không chỉ tin mọi trường trong envelope. Copy nguyên envelope cùng context sang một tài nguyên khác không được tự tạo quyền đọc ở nơi mới.

## 7. Luồng đọc: unwrap DEK rồi xác thực payload

Luồng khái niệm:

```text
Xác minh quyền đọc object/revision
    -> đọc và parse envelope trong giới hạn
    -> kiểm tra profile và key reference đúng scope
    -> yêu cầu unwrap DEK bằng quyền và context được phép
    -> giải mã payload bằng DEK
    -> kiểm chứng tag/AAD
    -> chỉ trả plaintext sau khi xác thực thành công
    -> kết thúc phạm vi sử dụng plaintext DEK
```

Không expose một API nhận wrapped DEK tùy ý rồi trả raw key cho client chỉ vì service có quyền `Decrypt`. Đường unwrap phải gắn với chức năng và dữ liệu được phép; quyền kỹ thuật của service không thay quyền của người dùng.

Unwrap DEK thành công cũng chưa chứng minh payload không bị sửa. Payload phải có cơ chế xác thực theo profile, và tag cần được kiểm chứng trước khi tin plaintext.

Nếu ciphertext, tag, wrapped DEK, profile hoặc context không hợp lệ, không fallback sang key dùng chung hoặc mode không xác thực. Không thử toàn bộ KEK của hệ thống cho đến khi tìm được một kết quả có vẻ đọc được.

Một envelope hợp lệ cũ bị replay còn là vấn đề riêng. Nếu nghiệp vụ cần chống đưa revision cũ trở lại, phải có trạng thái hoặc bằng chứng freshness phù hợp mô hình đe dọa. AEAD không tự biết bản dữ liệu nào là bản mới nhất khi toàn bộ envelope cũ được đưa lại.

## 8. Nonce, AAD và giới hạn sử dụng theo DEK

### 8.1. Nonce phải được xét dưới cùng key

Với AES-GCM, yêu cầu không lặp nonce khi mã hóa áp dụng theo cùng key material. Không chỉ kiểm tra nonce có khác với request trước ở một node hay không. Nhiều writer, retry hoặc cache DEK làm phạm vi kiểm soát rộng hơn.

Nếu mỗi lần ghi dùng một DEK mới độc lập, việc quản lý số phép mã hóa trên mỗi key đơn giản hơn. Tuy nhiên, vẫn phải dùng thư viện và profile nonce đúng; không tự tạo một quy trình bỏ qua điều kiện chỉ vì cho rằng “key chắc khác”.

Hai DEK độc lập có thể dùng cùng giá trị nonce mà không phải cùng trường hợp lặp nonce dưới một key. Ngược lại, đổi nhãn DEK hoặc KEK nhưng giữ nguyên key material không làm lịch sử nonce được reset.

Các yêu cầu IV duy nhất, cung cấp AAD và kiểm chứng tag của Java AEAD được mô tả trong [Java SE 21 Cipher](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Cipher.html).

### 8.2. Retry không được vô tình tái mã hóa với cặp key–nonce cũ

Nếu một thao tác đã tạo envelope hoàn chỉnh và retry chỉ trả lại chính kết quả đã lưu theo idempotency contract, đó khác với việc thực hiện một phép mã hóa mới bằng cùng DEK và nonce.

Thiết kế cần biết retry ở tầng nào: sinh DEK, wrap, mã hóa payload hay commit storage. Không đặt một vòng lặp thử lại toàn bộ hàm nhưng giữ nguyên một nonce đã dùng trong object state.

Một profile có thể chọn sinh DEK/nonce mới cho lần thử mã hóa mới, đồng thời dùng idempotency ở lớp nghiệp vụ để không tạo nhiều revision. Lựa chọn này phải phối hợp với storage, không chỉ sửa nguồn random.

### 8.3. Có ngân sách số thông điệp, tổng byte và thời gian

Nếu DEK được tái sử dụng, cần chốt giới hạn theo construction và policy: số phép mã hóa, dung lượng mỗi thông điệp, tổng dữ liệu, thời gian giữ và điều kiện ngừng. Không suy từ số bit khóa ra một hạn mức dùng vô hạn.

AAD của payload và context wrapping có thể khác nhau. Profile phải chỉ ra lớp nào ràng buộc thông tin nào; không để một bước rewrap sửa một trường vốn được tag payload xác thực rồi bỏ kiểm tra để đọc được.

## 9. Plaintext DEK trong bộ nhớ và log

### 9.1. KMS bảo vệ KEK không có nghĩa DEK không ra ngoài

Trong mô hình ứng dụng mã hóa payload, DEK dạng dùng được có thể đi vào process hoặc một môi trường xử lý chuyên biệt. Đây là ranh giới cần được phân tích, không được che bởi câu “mọi key đều nằm trong KMS”.

Cần hạn chế bản sao, thời gian giữ, quyền debug, heap dump và dữ liệu chẩn đoán. Không log toàn bộ object trả về từ API sinh data key nếu nó có thể chứa plaintext key. Không đưa key vào exception, tracing attribute, message queue hoặc biến cấu hình lâu dài.

Nếu sử dụng môi trường cách ly hoặc API không đưa DEK vào process thông thường, phải đối chiếu kiến trúc và attestation/quyền tương ứng. Không giả định mọi SDK có cùng đặc tính đó.

### 9.2. Giảm thời gian tồn tại, không hứa xóa tuyệt đối khi runtime không bảo đảm

Với Java, byte array có thể được ghi đè khi ứng dụng kiểm soát nó, nhưng provider hoặc lớp khác có thể đã tạo bản sao. Một lệnh `Arrays.fill()` không chứng minh mọi bản key trong runtime đều biến mất.

Yêu cầu nên quy định quản lý vòng đời và bằng chứng phù hợp: dùng API hỗ trợ khi có, tránh chuyển raw key thành `String`, không giữ trong cache ngoài policy và hạn chế công cụ chẩn đoán chứa secret. Nếu cần bảo đảm zeroization hoặc non-exportability mạnh hơn, phải chọn module/kiến trúc cung cấp tính chất đó.

Vấn đề bộ nhớ, key usage và vòng đời được thảo luận trong [OWASP Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html).

### 9.3. Cache DEK thay đổi cả mô hình quyền

Cache plaintext DEK có thể giảm latency và số lần gọi KMS, nhưng tăng thời gian và phạm vi key tồn tại trong ứng dụng. Disable KEK hoặc thu hồi quyền unwrap không tự xóa các DEK đã được cache.

Nếu cho phép cache, cần xác định TTL, số entry, ranh giới tenant/purpose, ngân sách dùng key, invalidation và hành vi khi quyền thay đổi. Không cache theo một ID không đủ namespace hoặc dùng lại DEK của tenant khác vì cache key trùng.

Trong profile minh họa của bài, mặc định không giữ plaintext DEK qua phạm vi xử lý một object revision. Một phương án cache khác cần quyết định riêng và bằng chứng phù hợp, không phải tối ưu mặc định được thêm sau.

## 10. Ví dụ hợp đồng Java cho vòng đời DEK

Một trích đoạn khái niệm có thể biểu đạt ranh giới xử lý:

```java
// Các type bên dưới là hợp đồng ứng dụng minh họa.
// authorizedContext đã được xác minh tenant, object, revision và purpose.
// keyService chọn KEK/profile theo policy, không nhận URI tùy ý từ client.

try (DataKeyLease dataKey = keyService.generateFor(authorizedContext)) {
    byte[] nonce = nonceSource.nextForNewEncryption(dataKey.identity());

    Cipher cipher = Cipher.getInstance(
            "AES/GCM/NoPadding", approvedProvider);
    cipher.init(
            Cipher.ENCRYPT_MODE,
            dataKey.secretKey(),
            new GCMParameterSpec(128, nonce));
    cipher.updateAAD(authorizedContext.payloadAadBytes());

    byte[] ciphertextAndTag = cipher.doFinal(plaintext);

    EncryptedEnvelope envelope = envelopeFactory.create(
            "report-aead-v2",
            dataKey.actualWrappingKeyIdentity(),
            dataKey.wrappedKeyBlob(),
            nonce,
            ciphertextAndTag,
            authorizedContext.contextSchemaVersion());

    repository.publishAtomically(
            reportId, expectedRevision, envelope);
}
```

Đây không phải mã chạy độc lập hoặc một SDK có sẵn với đúng các tên type này. Nó thể hiện các hợp đồng cần có:

- `DataKeyLease` có DEK đúng profile và wrapped blob tương ứng với chính DEK đó.
- Identity wrapping là key thực sự dùng trong thao tác, không phải một lần tra alias rời có thể race.
- Nguồn nonce đáp ứng construction; profile ví dụ sử dụng nonce 96 bit và tag 128 bit.
- Context có encoding xác định và không lấy quyền từ dữ liệu client tự khai.
- `publishAtomically` công bố envelope đầy đủ theo concurrency contract.
- `close()` kết thúc lease và thu hồi các bản sao do implementation quản lý theo bảo đảm đã công bố.

`try-with-resources` chỉ gọi `close()`; nó không tự chứng minh zeroization của key, buffer hay provider. Muốn dùng hợp đồng đó trong sản phẩm, implementation và môi trường phải có bằng chứng tương ứng.

Lớp gọi còn cần giới hạn kích thước plaintext, timeout, xử lý lỗi công khai và điều phối việc commit. Với payload lớn, nên dùng construction/SDK streaming được thiết kế phù hợp; không phát plaintext chưa xác thực từ một vòng lặp giải mã từng phần.

## 11. Phân quyền sinh, wrap và unwrap

### 11.1. Tách trách nhiệm khi nền tảng hỗ trợ

Một workload chỉ ghi dữ liệu có thể cần khả năng tạo DEK mới và bảo vệ nó, nhưng không nhất thiết cần unwrap mọi DEK lịch sử. Workload đọc cần quyền giải bọc trong phạm vi dữ liệu được phép. Quyền quản trị KEK là một trách nhiệm khác.

Thiết kế phải ánh xạ sang khả năng thực tế của provider và SDK. Không gán một role quản trị rộng chỉ để giải quyết lỗi thiếu một permission, và không giả định mọi API có cùng tập quyền.

| Chủ thể minh họa | Khả năng cần đánh giá |
| --- | --- |
| Writer | Tạo/bảo vệ DEK cho purpose và tenant được phép |
| Reader | Unwrap DEK của dữ liệu đã qua kiểm tra quyền |
| Migration worker | Đọc cũ và tạo mới trong dataset được cấp |
| Key administrator | Quản lý vòng đời/key policy theo trách nhiệm |
| Auditor | Xem metadata và sự kiện phù hợp, không cần raw key |

### 11.2. Context hỗ trợ ràng buộc, không tự chứng minh danh tính dữ liệu

Nếu KMS policy kiểm tra context `purpose=report`, service vẫn phải xác định người dùng có được đọc report cụ thể không. Attacker có thể biết các giá trị context không bí mật; quyền không được dựa trên việc họ có thể lặp lại một chuỗi đó.

Đường unwrap cần kiểm soát key namespace, wrapped blob, context và tài nguyên liên quan. Không trở thành một proxy giải mã dùng service credential rộng hơn quyền caller.

## 12. Rotation, rewrap và DEK bị lộ

### 12.1. Đổi KEK không đồng nghĩa đổi DEK

Giả sử payload được mã hóa bằng DEK D, D được wrap bằng KEK K1. Khi chuyển sang K2, hệ thống có thể tạo wrapped D mới dưới K2 mà giữ payload cũ:

```text
Trước: payload_C = Encrypt_D(payload)
       wrapped_D_1 = Wrap_K1(D)

Sau rewrap: payload_C giữ nguyên
            wrapped_D_2 = Wrap_K2(D)
```

Nếu mục tiêu chỉ là thay lớp quản lý key theo policy, điều này có thể phù hợp. Nếu D đã bị lộ, rewrap cùng D không làm attacker quên D; cần đánh giá lại dữ liệu và thực hiện thay DEK/re-encrypt theo kế hoạch.

### 12.2. Thay DEK yêu cầu xử lý payload

Để chuyển nội dung sang DEK D2, cần đọc/giải mã theo quyền, tạo bảo vệ mới, nonce và tag mới, rồi công bố envelope nhất quán. Việc chỉ thay tên `dekId` hoặc wrapping key reference không thực hiện thay DEK.

Migration cần chống ghi đè cập nhật mới của người dùng, hỗ trợ chạy lại và giữ giới hạn KMS/CPU/storage. Không giữ plaintext trung gian trong file tạm hoặc log không được bảo vệ.

### 12.3. Phạm vi ảnh hưởng theo lớp khóa

Một DEK bị lộ ảnh hưởng dữ liệu mà nó đã bảo vệ. KEK bị lộ hoặc quyền unwrap bị chiếm có thể ảnh hưởng nhiều DEK trong phạm vi tương ứng. Tuy nhiên, phạm vi thật còn phụ thuộc dữ liệu attacker có được, key version, context và quyền tại thời điểm đó.

Không đánh đồng mọi sự cố key thành cùng một xử lý “rotate KEK là xong”. Cần ngăn truy cập, xác định tài sản ảnh hưởng, thay các lớp cần thiết và xử lý dữ liệu có thể đã mất bí mật. Mã hóa lại không thu hồi một bản plaintext attacker đã lấy.

## 13. Lỗi dịch vụ, backup và xóa dữ liệu

### 13.1. KMS không sẵn sàng phải có hành vi rõ

Nếu không tạo hoặc unwrap được DEK theo policy, không trả plaintext dự phòng và không ghi dữ liệu chưa mã hóa. Cần phân biệt lỗi tạm thời có thể retry trong cùng hợp đồng với lỗi quyền, key bị disable hoặc ciphertext không hợp lệ.

Giới hạn retry, timeout và số công việc đồng thời để tránh tạo bão request KMS. Envelope có kích thước hoặc profile không hợp lệ nên được chặn trước công việc đắt tiền khi có thể; không cho client kích hoạt unwrap không giới hạn.

Nếu dùng DEK cache, việc tiếp tục hoạt động trong một khoảng thời gian được phép phải là thiết kế đã phê duyệt, có TTL và ranh giới quyền. Nó không được trở thành một đường fallback không có hạn sau khi key bị thu hồi.

### 13.2. Backup cần đủ chuỗi khả năng giải mã

Để đọc dữ liệu sau restore, cần ciphertext, nonce/tag hoặc metadata theo profile, wrapped DEK, key identity/context và quyền dùng KEK còn phù hợp. Backup chỉ có payload ciphertext nhưng mất wrapped DEK có thể không còn khả năng phục hồi.

Ngược lại, không lưu raw DEK cạnh ciphertext chỉ để backup dễ restore. Cần thiết kế khả năng khôi phục key và quyền theo ranh giới bảo vệ đã chốt, gồm region, môi trường, trạng thái key và công cụ phục hồi.

Một ca restore phải thực sự đọc dữ liệu thử từ nhiều thời kỳ key, không chỉ kiểm tra tệp backup tồn tại hoặc wrapped blob còn nguyên độ dài.

### 13.3. Không tuyên bố crypto-erasure chỉ bằng xóa một trường

Xóa wrapped DEK của một object có thể làm object đó không đọc được qua bản ghi hiện tại, nhưng còn có thể có bản sao trong backup, replica, cache hoặc hệ thống khác. Một DEK cũng có thể được wrap dưới nhiều KEK hoặc đã được export theo một luồng được phép.

Nếu có yêu cầu xóa bằng mật mã, phải xác định toàn bộ bản sao có thể dùng để phục hồi key/data và giả định còn lại. Không hứa xóa tuyệt đối chỉ vì một lệnh DELETE ở database đã thành công.

Hủy một KEK dùng chung để xử lý một bản ghi còn có thể ảnh hưởng dữ liệu khác. Granularity DEK/KEK và kế hoạch lưu giữ phải được thiết kế trước; hành động phá khả năng giải mã không nên là một quyết định ứng biến.

## 14. Bộ yêu cầu bảo mật có thể nghiệm thu

| Mã | Yêu cầu minh họa | Bằng chứng nghiệm thu dự kiến |
| --- | --- | --- |
| DEK-01 | Mỗi payload/revision phải dùng DEK trong phạm vi và profile được phê duyệt | Đối chiếu luồng tạo key, granularity và metadata |
| DEK-02 | DEK phải sinh từ nguồn mật mã được phép, không dẫn xuất tùy ý từ định danh | Kiểm tra implementation, cấu hình và test nguồn sinh |
| DEK-03 | Plaintext DEK không được lưu trong envelope, log hoặc queue ngoài policy | Kiểm tra storage, response, tracing và lỗi |
| DEK-04 | Wrapped DEK phải tương ứng đúng payload và key/context thực tế | Ca hoán đổi blob, key reference và context |
| DEK-05 | Payload phải được xác thực trước khi phát plaintext | Sửa ciphertext, nonce, tag hoặc AAD |
| DEK-06 | Unwrap chỉ được thực hiện cho tài nguyên, tenant và purpose được phép | Caller sai quyền, key ngoài namespace và dataset khác |
| DEK-07 | Nonce và usage budget phải áp dụng theo key material thực sự | Retry, nhiều writer, reuse hoặc cache DEK |
| DEK-08 | Envelope và metadata phải công bố nguyên tử theo concurrency contract | Lỗi giữa chừng, retry và cập nhật đồng thời |
| DEK-09 | Cache hoặc lease plaintext DEK phải có phạm vi, thời hạn và hành vi thu hồi rõ | Kết thúc request, disable key, cache hết hạn |
| DEK-10 | Rewrap không được coi là thay DEK hoặc thay profile payload | Đối chiếu lớp bọc và nội dung trước/sau |
| DEK-11 | Lỗi KMS/key không được gây lưu plaintext hoặc dùng key dự phòng ngoài policy | Timeout, quyền thiếu, key bị disable và lỗi xác thực |
| DEK-12 | Backup/restore và retirement phải giữ đúng khả năng phục hồi cần thiết | Phục hồi qua các thời kỳ KEK/DEK và kiểm tra phụ thuộc |

Một yêu cầu tổng hợp có thể ghi:

> Mỗi revision báo cáo dùng một DEK độc lập theo profile được duyệt. Plaintext DEK chỉ được dùng trong phạm vi xử lý được phép và không được lưu cùng dữ liệu. Wrapped DEK, ciphertext và metadata phải nhất quán; giải bọc phải qua quyền tài nguyên và KMS/context đúng scope. Payload chưa được xác thực không được trả cho người dùng hoặc dùng trong nghiệp vụ.

## 15. Kế hoạch nghiệm thu và giới hạn của bằng chứng

Các ca dưới đây là kế hoạch kiểm chứng cho nền tảng giả định, không phải báo cáo đã chạy trên một hệ thống thực tế.

| Ca | Điều kiện | Kết quả cần quan sát |
| --- | --- | --- |
| Ghi/đọc hợp lệ | Người được phép, profile và context đúng | Đọc lại đúng payload với envelope đầy đủ |
| Hai revision | Tạo hai lần ghi theo profile per-revision | Hai DEK độc lập theo cơ chế sinh, không tái dùng do cache sai |
| Storage bị lộ | Kiểm tra bản lưu object/database | Không có raw DEK; có wrapped DEK và metadata đúng |
| Sai tenant | Caller dùng envelope thuộc tenant khác | Không unwrap/trả dữ liệu ngoài quyền |
| Wrapped DEK bị đổi | Ghép key blob của object A vào payload B | Không chấp nhận như payload hợp lệ |
| Key reference bị đổi | Envelope chọn key khác hoặc alias tùy ý | Không mở quyền KMS từ đầu vào không tin cậy |
| Context bị đổi | Tenant/object/revision mong đợi không khớp | Xác thực hoặc policy từ chối đúng lớp |
| Payload bị sửa | Đổi byte ciphertext, nonce hoặc tag | Không phát plaintext chưa xác thực |
| Retry mã hóa | Lỗi xảy ra giữa sinh key và commit | Không tái mã hóa trái nonce policy hoặc tạo revision trùng ngoài hợp đồng |
| Lỗi lưu | Wrapped DEK hoặc metadata chưa lưu thành công | Không công bố payload mất khả năng đọc |
| KMS lỗi | Timeout hoặc quyền bị từ chối | Không fallback plaintext/key cứng; retry có giới hạn |
| Lease/cache | Request kết thúc hoặc policy thu hồi thay đổi | Thời gian và phạm vi giữ DEK khớp hợp đồng |
| Rewrap KEK | Cùng DEK được bọc lại | Wrapped metadata nhất quán; không tuyên bố DEK đã thay |
| Thay DEK | Payload được re-encrypt bằng key mới | Nonce/tag/envelope mới đúng, dữ liệu giữ nguyên theo hợp đồng |
| Restore | Backup thuộc nhiều thế hệ key | Đọc được dữ liệu cần giữ theo quyền và context |
| Xóa dữ liệu | Kiểm tra các bản sao còn khả năng giải mã | Không tuyên bố crypto-erasure vượt bằng chứng |

### 15.1. Hai ciphertext khác nhau chưa chứng minh DEK khác nhau

Cùng DEK với nonce khác có thể tạo ciphertext khác. Vì vậy, không nghiệm thu granularity DEK chỉ bằng cách nhìn output hai lần mã hóa.

Cần kiểm tra hợp đồng nguồn sinh, call path, cache và metadata được phép quan sát. Không dump raw key ra log để so sánh. Nếu dùng instrumentation trong test, phải giới hạn môi trường và không biến phương thức xuất key thành chức năng production.

### 15.2. Round-trip chưa chứng minh quyền và tính toàn vẹn

Một phép encrypt/decrypt thành công không chứng minh caller sai quyền bị chặn, payload bị sửa bị phát hiện hoặc key được thu hồi đúng thời hạn. Cần ca âm và kiểm tra tác dụng phụ, không chỉ assert nội dung bằng nhau.

Với lỗi sau khi đã ghi một phần, phải kiểm tra trạng thái storage và job. Response lỗi không tự chứng minh hệ thống chưa công bố một object không đọc được hoặc một envelope sai metadata.

### 15.3. Đo trên đường xử lý thực tế

SDK, provider, KMS policy, container và công cụ chẩn đoán ảnh hưởng cách DEK được xử lý. Bằng chứng cần gắn với release và môi trường, gồm các đường batch, export hoặc migration nếu chúng dùng cùng cơ chế.

Nếu một yêu cầu cần module được xác nhận hoặc zeroization với mức bảo đảm cụ thể, phải có bằng chứng đúng phạm vi. Không suy từ việc dùng AES hoặc KMS sang việc toàn bộ vòng đời plaintext DEK trong ứng dụng đã đáp ứng mọi yêu cầu đó.

## 16. Một hồ sơ yêu cầu gọn cho DEK

```text
Tài sản: nội dung báo cáo, plaintext DEK và khả năng phục hồi.
Đe dọa: lộ storage, lộ DEK trong process/log, unwrap trái quyền,
        tráo envelope, nonce reuse và mất wrapped key/metadata.

Granularity:
  - Profile minh họa dùng một DEK độc lập cho mỗi object revision.
  - DEK chỉ bảo vệ dữ liệu trong purpose/tenant đã chốt.

Vòng đời:
  - Sinh bằng nguồn mật mã được phép hoặc API quản lý phù hợp.
  - Wrap dưới KEK được chọn từ policy tin cậy.
  - Chỉ giữ dạng dùng được trong phạm vi đã phê duyệt.
  - Không log, lưu hoặc phát raw DEK như metadata thông thường.

Envelope:
  - Wrapped DEK, wrapping identity, profile, nonce, ciphertext/tag
    và context schema phải đúng và nhất quán.
  - Quyền ứng dụng và quyền KMS/context đều được thực thi.
  - Không phát plaintext trước khi xác thực thành công.

Thay đổi và phục hồi:
  - Rewrap KEK khác với thay DEK hoặc re-encrypt payload.
  - Cache, retry, migration và backup nằm trong scope policy.
  - Xóa/hủy không được tuyên bố vượt khả năng kiểm chứng bản sao.
```

DEK có giá trị khi nó tạo một ranh giới bảo vệ nội dung rõ ràng và được quản lý từ lúc sinh tới khi kết thúc sử dụng. Khi yêu cầu nối được phạm vi DEK, quyền unwrap, envelope, bộ nhớ và phục hồi, envelope encryption mới trở thành một thiết kế có thể kiểm chứng thay vì chỉ một bước “mã hóa key bằng key khác”.
