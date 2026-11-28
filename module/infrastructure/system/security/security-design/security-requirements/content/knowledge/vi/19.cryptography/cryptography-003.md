# Encryption at rest

## 1. Mã hóa dữ liệu lưu trữ cần bảo vệ trước ai?

Một hệ thống có thể dùng HTTPS cho mọi API nhưng vẫn lưu hồ sơ, file đính kèm hoặc bản sao lưu dưới dạng đọc được nếu người khác lấy được vật mang dữ liệu. Bảo vệ đường truyền không tự bảo vệ những bản dữ liệu đã được ghi xuống nơi lưu trữ.

**Encryption at rest** là việc mã hóa dữ liệu khi dữ liệu được lưu giữ. Mục tiêu là làm cho một bên không có quyền sử dụng khóa phù hợp không thể khôi phục nội dung từ bản lưu mà họ có được, trong phạm vi mô hình đe dọa đã xác định.

Câu “dữ liệu phải được mã hóa at rest” chưa đủ để triển khai. Cần trả lời:

1. Dữ liệu nào cần bảo vệ và nó có những bản sao nào?
2. Bên tấn công có thể lấy ổ đĩa, snapshot, backup, quyền đọc database hay quyền chạy ứng dụng?
3. Mã hóa diễn ra ở lớp nào, và ở đâu dữ liệu trở lại dạng rõ?
4. Ai được sử dụng hoặc quản trị khóa?
5. Nếu dịch vụ khóa lỗi, khóa bị thu hồi hoặc môi trường chính mất, hệ thống ứng xử ra sao?
6. Bằng chứng nào xác nhận cả tính bí mật lẫn khả năng khôi phục đúng?

Trong module yêu cầu bảo mật, điểm xuất phát là rủi ro đối với dữ liệu và khả năng kiểm chứng. Tên một thuật toán hay một checkbox của dịch vụ lưu trữ chỉ là một phần của thiết kế.

## 2. Phân biệt những mục tiêu dễ bị gộp chung

| Mục tiêu hoặc cơ chế | Điều nó giải quyết | Điều không được tự suy ra |
| --- | --- | --- |
| Mã hóa khi truyền | Bảo vệ một chặng truyền giữa các điểm kết thúc | Các bản sao lưu trên đĩa cũng đã được mã hóa |
| Mã hóa khi lưu | Bảo vệ bản lưu theo cơ chế và quyền khóa đã chọn | Người có quyền đọc qua ứng dụng không thể nhận dữ liệu rõ |
| Kiểm soát truy cập | Quyết định chủ thể được phép thực hiện thao tác nào | Bản dữ liệu bị lấy ra ngoài vẫn không đọc được |
| Encoding, chẳng hạn Base64 | Chuyển biểu diễn dữ liệu | Nội dung được giữ bí mật |
| Hashing | Tạo giá trị băm cho một mục đích cụ thể | Có thể giải mã để lấy lại dữ liệu gốc |
| Giảm thiểu dữ liệu | Tránh lưu hoặc công khai dữ liệu không cần thiết | Mọi dữ liệu còn lại tự được bảo vệ |

Nếu ứng dụng cần đọc lại địa chỉ giao hàng, mã hóa có thể là một thành phần phù hợp. Nếu ứng dụng chỉ cần kiểm tra mật khẩu, yêu cầu thường thuộc cơ chế băm mật khẩu chuyên dụng thay vì lưu mật khẩu bằng mã hóa có thể đảo ngược. [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html) nhấn mạnh việc bắt đầu từ threat model, giảm dữ liệu cần lưu và chọn đúng lớp bảo vệ.

Mỗi mục tiêu cần điều kiện hoàn thành riêng. Không dùng bằng chứng HTTPS hoặc một phép băm để thay cho bằng chứng mã hóa bản lưu cần khôi phục.

## 3. Chọn lớp mã hóa theo ranh giới tấn công

Mã hóa có thể được đặt ở nhiều lớp. Thiết kế cần nêu ai nhìn thấy dữ liệu rõ tại mỗi lớp và người tấn công đang được giả định có quyền gì.

| Lớp | Ví dụ kiến trúc | Ranh giới cần phân tích |
| --- | --- | --- |
| Thiết bị, volume hoặc filesystem | Ổ đĩa được mã hóa và mở khóa khi hệ thống chạy | Mất vật mang dữ liệu so với truy cập vào máy đã mở khóa |
| Storage service | Object hoặc block được dịch vụ lưu dưới dạng mã hóa | Quyền lấy object qua API của dịch vụ và quyền dùng khóa |
| Database | Mã hóa file/page/log theo cơ chế của sản phẩm | Bản file bị lấy ngoài hệ thống so với truy vấn hợp lệ qua database |
| Ứng dụng | Trường hoặc tài liệu được mã hóa trước khi gửi tới nơi lưu | Database/storage có thể giữ ciphertext trong khi dịch vụ được phép mới giải mã |
| Client phía người dùng | Client mã hóa trước khi server nhận | Phân phối khóa, phục hồi, chia sẻ và những xử lý server còn có thể thực hiện |

Ví dụ, tài liệu [Microsoft về TDE](https://learn.microsoft.com/en-us/sql/relational-databases/security/encryption/transparent-data-encryption) mô tả mã hóa/giải mã I/O của data file và log file, đồng thời có yêu cầu riêng với vật liệu bảo vệ khóa khi phục hồi. Đây là một cơ chế cụ thể của sản phẩm; không nên suy rộng rằng bật mã hóa database tự bao phủ mọi export hoặc file phụ của ứng dụng.

Một yêu cầu của dự án có thể là:

> Snapshot lưu trữ bị sao chép ra ngoài, khi không kèm quyền khóa được cấp theo chính sách, không được cho phép khôi phục nội dung hồ sơ trong phạm vi đã xác định.

Một yêu cầu khác có thể mạnh hơn:

> Người chỉ có quyền đọc kho object không được nhận nội dung tài liệu rõ; việc giải mã phải đi qua danh tính dịch vụ và chính sách khóa tách biệt.

Hai yêu cầu không tương đương. Cơ chế đáp ứng yêu cầu thứ nhất có thể chưa đáp ứng yêu cầu thứ hai nếu API kho object tự giải mã cho người được quyền đọc.

### Không coi nhãn “mã hóa mặc định” là toàn bộ hợp đồng

Các nền tảng có mô hình quản lý khóa và phạm vi mã hóa khác nhau. Ví dụ, [tài liệu default encryption của Google Cloud](https://cloud.google.com/docs/security/encryption/default-encryption) phân biệt khóa do nền tảng quản lý với các lựa chọn có mức kiểm soát khách hàng khác nhau.

Trong dự án, cần kiểm tra đúng dịch vụ, loại dữ liệu, quyền sử dụng khóa và cơ chế sao chép. Không suy từ một tuyên bố chung rằng tổ chức đã có quyền audit, luân chuyển hoặc hủy khóa theo mọi yêu cầu của mình.

## 4. Inventory phải theo dữ liệu, không chỉ theo database chính

Một hồ sơ có thể đi qua nhiều nơi lưu trước khi hết vòng đời. Nếu chỉ mã hóa bảng chính, hệ thống vẫn có thể để lộ bản export hoặc một bản ghi trung gian.

Ví dụ một inventory cho chức năng lưu tài liệu:

| Nơi dữ liệu được giữ | Dữ liệu có thể tồn tại | Điều phải xác nhận |
| --- | --- | --- |
| Database chính | Metadata, trường nhạy cảm, tham chiếu tài liệu | Cơ chế, trạng thái mã hóa và quyền đọc |
| Kho file/object | Nội dung tài liệu và phiên bản cũ | Chính sách object, khóa và các bản sao |
| Replica hoặc vùng dự phòng | Bản phục vụ đọc, bản phục hồi | Cấu hình và khả năng dùng khóa tại đích |
| Snapshot và backup | Dữ liệu ở thời điểm trước | Mã hóa, retention, khóa cần cho restore |
| Export và báo cáo | CSV, PDF, archive hoặc file tải xuống | Thời gian tồn tại, nơi lưu, người được nhận |
| Search index | Trích đoạn, trường tìm kiếm, dữ liệu dẫn xuất | Phạm vi thông tin lộ qua chỉ mục |
| Hàng đợi bền vững và dead-letter | Payload công việc, sự kiện lỗi | Dữ liệu nào được ghi và trong bao lâu |
| Cache có persistence | Snapshot hoặc log phục hồi của cache | Phân biệt dữ liệu trong bộ nhớ với bản được ghi xuống |
| File tạm và thư mục xử lý | Nội dung sau upload, chuyển đổi hoặc giải nén | Lớp bảo vệ, cleanup và quyền truy cập |
| Log, trace và bản chẩn đoán | Giá trị trường, request, lỗi hoặc dump | Giảm dữ liệu, quyền đọc và bảo vệ bản lưu |

Danh mục này là ví dụ kiểm kê, không phải khẳng định mọi hệ thống đều có từng thành phần. Những nơi không dùng cần được ghi nhận rõ, thay vì bị bỏ qua vì chưa ai xác nhận.

Với mỗi mục, đặc tả nên có chủ sở hữu, phân loại dữ liệu, thời gian giữ, cơ chế mã hóa, nguồn khóa và bằng chứng trạng thái thực tế. Các trường dẫn xuất cũng cần được xét: một chỉ mục không có file gốc vẫn có thể chứa đủ nội dung để làm lộ thông tin.

## 5. Mô hình đe dọa cho dữ liệu lưu trữ

Giả sử hệ thống quản lý tài liệu nội bộ cho nhiều tenant. Nhóm thiết kế cần phân biệt các năng lực tấn công sau:

| Năng lực giả định của bên tấn công | Câu hỏi cần kiểm chứng |
| --- | --- |
| Có bản sao ổ đĩa hoặc snapshot nhưng không có quyền khóa | Nội dung có thể được khôi phục ngoài hệ thống hay không? |
| Có quyền đọc object lưu trữ nhưng không có quyền giải mã ứng dụng | Luồng đọc có tự trả plaintext hay giữ ciphertext? |
| Có credential database có thể SELECT | Dữ liệu nào đã được database tự giải mã và dữ liệu nào còn được bảo vệ ở lớp khác? |
| Chiếm quyền một dịch vụ được phép giải mã | Phạm vi tài liệu và tenant mà dịch vụ đó có thể truy cập là gì? |
| Có quyền quản trị chính sách khóa | Có thể tự cấp quyền sử dụng khóa hoặc phá khả năng khôi phục không? |
| Có bản backup cũ cùng vật liệu khóa cũ | Chính sách luân chuyển, giữ khóa và thu hồi ảnh hưởng thế nào? |
| Có thể thay ciphertext hoặc metadata | Hệ thống có phát hiện sai lệch và từ chối xử lý không? |

Không đặt mục tiêu “bảo vệ trước mọi admin” nếu kiến trúc vẫn cho một admin tự cấp cả quyền lấy dữ liệu lẫn quyền giải mã mà không có kiểm soát khác. Cũng không khẳng định mã hóa giữ bí mật trước một tiến trình đã bị chiếm quyền và đang có đủ quyền đọc dữ liệu rõ.

Một mô hình tốt ghi rõ những giả định còn lại. Ví dụ, mã hóa ở ứng dụng có thể giảm rủi ro từ quyền đọc storage, nhưng ứng dụng vẫn cần phân quyền và giới hạn khả năng giải mã theo nhiệm vụ.

## 6. Envelope encryption và vai trò của các loại khóa

Envelope encryption tách khóa mã hóa dữ liệu khỏi khóa bảo vệ khóa đó. **DEK** là khóa dùng cho dữ liệu; **KEK** bảo vệ DEK. Bản DEK đã được bọc có thể đi cùng ciphertext, còn quyền khôi phục DEK được kiểm soát qua hệ thống khóa. Mô hình này được giải thích trong [tài liệu envelope encryption của Cloud KMS](https://cloud.google.com/kms/docs/envelope-encryption).

Sơ đồ khái niệm:

```text
Nội dung rõ ── dùng DEK ──> Nội dung mã hóa
                              │
DEK ── được bảo vệ bằng KEK ──> DEK đã bọc
                              │
                    Lưu envelope có phiên bản

Khi đọc:
Quyền hợp lệ → hệ thống khóa khôi phục DEK
            → xác minh và giải mã nội dung
            → dùng dữ liệu rõ trong phạm vi được phép
```

Các câu hỏi của yêu cầu bảo mật không biến mất khi dùng mô hình này:

- Một DEK phục vụ tài liệu, nhóm dữ liệu hay đơn vị nào?
- KEK được gắn với tenant hoặc môi trường theo quy tắc nào?
- Danh tính nào được bọc khóa, tháo bọc và quản trị khóa?
- DEK rõ có tồn tại trong tiến trình nào, trong bao lâu?
- Những metadata nào cần để đọc lại và chúng được kiểm tra thế nào?
- Khi một khóa không còn được dùng để ghi mới, dữ liệu cũ được xử lý ra sao?

Trong profile minh họa của dự án, KEK có thể được giữ trong KMS/HSM theo cơ chế không xuất vật liệu khóa ra ứng dụng. DEK rõ vẫn có thể cần xuất hiện trong tiến trình thực hiện mã hóa dữ liệu. Vì vậy, không được kết luận rằng “dùng KMS” đồng nghĩa không có khóa nhạy cảm trong bộ nhớ ứng dụng.

## 7. Bí mật, tính toàn vẹn và ngữ cảnh dữ liệu

Nếu ứng dụng tự mã hóa tài liệu, thiết kế thường cần cả bảo mật nội dung lẫn phát hiện thay đổi trái phép. Primitive AEAD cung cấp mã hóa có xác thực; associated data được xác thực nhưng không được giữ bí mật. Những thuộc tính này được mô tả trong [tài liệu AEAD của Tink](https://developers.google.com/tink/aead).

Ví dụ, dự án có thể muốn một ciphertext của tài liệu A không được chấp nhận như tài liệu B hoặc chuyển từ tenant này sang tenant khác. Thiết kế có thể ràng buộc ngữ cảnh mong đợi bằng cơ chế associated data của profile đã chọn.

Một tập ngữ cảnh minh họa:

```json
{
  "purpose": "document-content",
  "tenantRef": "tenant-demo-01",
  "documentRef": "doc-demo-1042",
  "formatVersion": 1
}
```

Các giá trị phải được lựa chọn theo chính sách metadata. Không đưa mật khẩu, nội dung tài liệu hoặc thông tin cá nhân vào associated data chỉ vì nó nằm gần thao tác mã hóa.

Với một dịch vụ cụ thể, ý nghĩa “context” cần được đọc đúng tài liệu. Chẳng hạn [AWS KMS encryption context](https://docs.aws.amazon.com/kms/latest/developerguide/encrypt_context.html) không được mã hóa và có thể xuất hiện trong audit log. Không mặc định metadata mật mã là một kênh giữ bí mật.

### Ngữ cảnh mong đợi không chỉ lấy từ envelope không tin cậy

Giả sử một request được phép đọc tài liệu của tenant A. Nếu ứng dụng lấy `tenantRef` trong envelope bị thay rồi tự dùng nó làm nguồn quyết định duy nhất, việc ràng buộc không phản ánh tài nguyên mà request thực sự được phép truy cập.

Trong thiết kế minh họa, ngữ cảnh mong đợi phải được xây dựng từ danh tính, tài nguyên và metadata có thẩm quyền của luồng xử lý. Envelope cung cấp dữ liệu cần để giải mã, nhưng không tự cấp quyền cho tenant hoặc tài liệu được ghi trong nó.

### Nonce, IV và giới hạn sử dụng khóa

Các bộ mã hóa có quy tắc khác nhau về nonce/IV, kích thước và số lần sử dụng dưới một khóa. Profile phải chọn bộ thuật toán cùng implementation được duyệt và nêu cách tuân thủ các giới hạn đó.

Không đặt một nonce cố định để dễ kiểm thử, không suy từ record ID sang nonce một cách tùy ý và không cho rằng retry thao tác ghi luôn được tái sử dụng mọi vật liệu trước đó. Cần dùng cơ chế quản lý nonce của thư viện hoặc thiết kế đã được kiểm chứng cho profile cụ thể.

Đối với file lớn hoặc xử lý theo chunk, ranh giới chunk, thứ tự và xác thực toàn bộ luồng cần thuộc một định dạng được thiết kế phù hợp. Không tự chia file rồi lặp một tham số mật mã cho mọi phần.

### Xác thực ciphertext không đồng nghĩa chống rollback nghiệp vụ

Một bản ciphertext cũ nhưng hợp lệ có thể vẫn vượt qua kiểm tra mật mã. Nếu nghiệp vụ phải ngăn việc phục hồi một phiên bản cũ trái phép, hệ thống cần kiểm soát version hoặc trạng thái hiện hành phù hợp.

Không dùng một tag hợp lệ làm bằng chứng rằng dữ liệu là phiên bản mới nhất hoặc rằng người gọi được phép xem nó.

## 8. Định dạng bản lưu phải có khả năng quản lý phiên bản

Một envelope minh họa có thể gồm:

```json
{
  "formatVersion": 1,
  "cryptoProfile": "document-aead-v1",
  "keyRef": "tenant-demo-document-key",
  "wrappedDataKey": "<encoded-wrapped-key>",
  "payload": "<encoded-authenticated-ciphertext>"
}
```

Đây là mô hình minh họa, không phải định dạng bắt buộc của một nhà cung cấp. Tùy thư viện, nonce và tag có thể nằm trong payload hoặc được biểu diễn thành trường riêng. Các placeholder không chứa vật liệu thật.

Yêu cầu của dự án cần xác định:

1. Danh mục profile và phiên bản được phép đọc, ghi.
2. Cách parse có giới hạn, kiểm tra kích thước và từ chối dữ liệu không được hỗ trợ.
3. Cách chọn khóa từ danh mục được phép, không từ một URL hoặc đường dẫn tùy ý trong bản lưu.
4. Những metadata nào được ràng buộc bằng cơ chế mật mã.
5. Cách cập nhật envelope và metadata nghiệp vụ nhất quán khi ghi.
6. Cách chuyển đổi dữ liệu mà không tạo một nhánh fallback plaintext ngoài kiểm soát.

Một tên key hoặc profile trong bản lưu không tự chứng minh rằng nó được phép dùng cho request hiện tại. Việc giải quyết key reference phải đi qua chính sách tin cậy và phạm vi tenant/môi trường.

Không thử giải mã theo hàng loạt profile tùy ý rồi trả kết quả đầu tiên parse được. Cũng không coi một lỗi parse là dấu hiệu chắc chắn dữ liệu thuộc định dạng plaintext cũ.

## 9. Luồng ghi và đọc có kiểm soát

Mã giả dưới đây thể hiện trách nhiệm của một kiến trúc envelope ở ứng dụng, không phải implementation mật mã có thể sao chép thay cho thư viện.

### Luồng ghi

```text
storeDocument(identity, documentRef, plaintext):
    authorizeDocumentWrite(identity, documentRef)
    enforceInputAndClassificationPolicy(plaintext)

    profile = selectApprovedProfile(identity, documentRef)
    context = buildExpectedContextFromTrustedState(identity, documentRef, profile)
    keyMaterial = obtainDataKeyUnderApprovedKeyPolicy(profile, context)

    try:
        sealedPayload = approvedEncryption.encrypt(
            keyMaterial.plaintextDataKey,
            plaintext,
            context
        )

        envelope = encodeVersionedEnvelope(
            profile,
            keyMaterial.wrappedDataKey,
            sealedPayload
        )

        persistAccordingToConsistencyContract(documentRef, envelope)
    finally:
        releaseSensitiveMaterialAccordingToRuntimeCapabilities(keyMaterial)
```

### Luồng đọc

```text
readDocument(identity, documentRef):
    authorizeDocumentRead(identity, documentRef)
    envelope = readEnvelopeForAuthorizedResource(documentRef)
    profile = validateAndResolveAllowedProfile(envelope, identity, documentRef)
    context = buildExpectedContextFromTrustedState(identity, documentRef, profile)
    keyMaterial = recoverDataKeyUnderApprovedKeyPolicy(envelope, profile, context)

    try:
        plaintext = approvedEncryption.decryptAndVerify(
            keyMaterial,
            envelope.payload,
            context
        )
        return exposeOnlyThroughAuthorizedOutput(plaintext)
    finally:
        releaseSensitiveMaterialAccordingToRuntimeCapabilities(keyMaterial)
```

Trong implementation thực, cần bảo đảm không sử dụng dữ liệu như đã hợp lệ trước khi bước xác minh tương ứng hoàn tất. Với streaming, hành vi này phải theo bảo đảm của primitive và định dạng luồng được chọn.

Tên hàm dọn vật liệu nhạy cảm không phải lời hứa rằng runtime đã xóa mọi bản sao trong bộ nhớ. Đặc biệt với Java, object, chuỗi và hoạt động của runtime có thể tạo các bản sao ngoài kiểm soát trực tiếp. Yêu cầu cần phản ánh khả năng thực tế, hạn chế lưu giữ và bảo vệ bản chẩn đoán thay vì cam kết xóa sạch tuyệt đối không có bằng chứng.

## 10. Quyền dữ liệu và quyền khóa phải được xét cùng nhau

Một principal có thể được phép lấy ciphertext nhưng không được phép giải mã. Một principal khác có quyền quản trị khóa nhưng không nên trực tiếp đọc nội dung nghiệp vụ. Thiết kế cần phân biệt rõ các quyền này.

Ví dụ ma trận cho dự án tài liệu:

| Chủ thể | Đọc bản lưu | Sử dụng khóa giải mã | Quản trị khóa | Mục đích |
| --- | --- | --- | --- | --- |
| Dịch vụ tài liệu | Trong phạm vi được cấp | Theo profile và chính sách | Không mặc định | Phục vụ request đã phân quyền |
| Dịch vụ sao lưu | Bản dữ liệu cần sao lưu | Chỉ khi thiết kế thật sự cần | Không mặc định | Tạo và kiểm tra backup |
| Người quản trị storage | Theo nhiệm vụ vận hành | Không tự suy ra từ quyền storage | Không mặc định | Quản lý hạ tầng lưu trữ |
| Người quản trị khóa | Theo nhiệm vụ được cấp | Có thể tách khỏi quyền dùng khóa | Theo quy trình thay đổi | Quản lý vòng đời khóa |
| Tác vụ phục hồi | Theo phiên diễn tập/sự cố được cấp | Đúng khóa và phạm vi cần phục hồi | Không mặc định | Restore có kiểm soát |

Đây là ví dụ phân tách trách nhiệm, không phải mô hình IAM áp dụng sẵn cho mọi sản phẩm. Cần kiểm tra khả năng một chủ thể tự cấp thêm quyền hoặc đi qua một đường khác để kết hợp quyền dữ liệu và khóa.

### Nhiều tenant không tự được cách ly chỉ vì có nhiều key ID

Một key cho mỗi tenant có thể hỗ trợ phân tách, nhưng nếu cùng dịch vụ được phép giải mã mọi key mà không kiểm tra tenant, tên khóa riêng không sửa được lỗi truy cập chéo.

Yêu cầu cần ràng buộc danh tính, tài nguyên, key reference và context có thẩm quyền. Việc client tự gửi tenant ID không được coi là quyết định cho phép chọn khóa tương ứng.

Phạm vi môi trường cũng cần rõ: dữ liệu và khóa production không nên tự chảy sang môi trường phát triển chỉ vì một công cụ restore hỗ trợ điều đó.

## 11. Luân chuyển, rewrap và mã hóa lại là các thao tác khác nhau

Trong một mô hình khóa nhiều lớp, “đã rotate” có thể nói về nhiều việc:

| Thao tác | Điều thay đổi | Câu hỏi cần kiểm chứng |
| --- | --- | --- |
| Chọn khóa hoặc phiên bản cho ghi mới | Chính sách của những lần mã hóa sau | Dữ liệu mới thực sự dùng lựa chọn đã duyệt chưa? |
| Thay vật liệu khóa trong dịch vụ khóa | Vật liệu hiện hành theo cơ chế nhà cung cấp | Dữ liệu cũ được đọc bằng cơ chế nào? |
| Rewrap DEK | Bản bọc của khóa dữ liệu | Ciphertext dữ liệu và metadata có còn nhất quán không? |
| Mã hóa lại payload | Ciphertext và có thể DEK/profile | Có migration đầy đủ, xác minh và phục hồi lỗi từng phần không? |

Ví dụ, [AWS KMS mô tả rotation](https://docs.aws.amazon.com/kms/latest/developerguide/rotate-keys.html) là thay vật liệu hiện hành, đồng thời vẫn sử dụng vật liệu tương ứng để giải mã ciphertext cũ. Vì vậy, không được coi một sự kiện rotation là bằng chứng mọi payload và mọi bản backup đã được mã hóa lại.

Yêu cầu của dự án nên nêu trigger, thời hạn và phạm vi từng loại thay đổi. Những trigger có thể gồm lịch chính sách, nghi lộ khóa, đổi profile hoặc chuyển môi trường.

### Migration cần có trạng thái và khả năng kiểm tra

Một kế hoạch có thể chia dữ liệu thành các nhóm phiên bản, ghi mới theo profile mục tiêu và chuyển dữ liệu cũ theo một tác vụ có theo dõi. Cần xử lý được lỗi giữa chừng, request đồng thời và việc một bản ghi đã được cập nhật trong lúc migration chạy.

Không chỉ dùng tỷ lệ “đã đổi được đa số” để tuyên bố hoàn tất nếu yêu cầu bao phủ toàn bộ tập dữ liệu. Cần kiểm kê những mục còn lại, bản sao lịch sử và ngoại lệ có owner.

Trong thời gian tương thích, việc hỗ trợ đọc dữ liệu cũ phải có ranh giới định dạng và thời hạn rõ. Không mở một nhánh tự đoán plaintext cho mọi lỗi giải mã.

## 12. Backup và phục hồi phải bao gồm phụ thuộc khóa

Một file backup tồn tại chưa đủ chứng minh hệ thống có thể phục hồi. Ngoài dữ liệu, môi trường đích có thể cần đúng vật liệu khóa hoặc quyền sử dụng dịch vụ khóa, metadata, phiên bản định dạng và cấu hình liên quan.

Với một sản phẩm cụ thể như SQL Server TDE, [Microsoft nêu yêu cầu bảo quản certificate và private key phù hợp để mở lại backup được bảo vệ](https://learn.microsoft.com/en-us/sql/relational-databases/security/encryption/transparent-data-encryption#tde-and-backups). Phụ thuộc thực tế của các nền tảng khác phải được xác nhận theo đúng cơ chế đang dùng.

Một yêu cầu phục hồi của dự án nên nêu:

1. Tập dữ liệu và thời điểm cần khôi phục.
2. Khóa hoặc phiên bản nào vẫn cần cho các bản lưu còn retention.
3. Ai được cấp quyền phục hồi và trong môi trường nào.
4. Cách khôi phục quyền khóa mà không phát tán vật liệu rõ tùy tiện.
5. Thời gian và mức mất dữ liệu chấp nhận được theo mục tiêu hệ thống.
6. Cách xác minh dữ liệu đúng mà không đưa nội dung nhạy cảm vào báo cáo kiểm thử.

Diễn tập nên thực hiện trên môi trường được kiểm soát với dữ liệu phù hợp. Không coi việc ứng dụng vẫn đọc được database hiện tại là bằng chứng rằng backup tại một vùng khác có thể được mở sau sự cố mất môi trường chính.

### Bản sao cũ vẫn thuộc phạm vi yêu cầu

Nếu một bản export hoặc backup cũ còn lưu plaintext, bật mã hóa cho dữ liệu mới không làm bản cũ tự được bảo vệ. Kế hoạch cần xác định cách xử lý các bản lưu trước thay đổi theo retention và quyền thao tác được cấp.

Không xóa vật liệu khóa còn cần cho backup chỉ vì payload hoạt động đã được chuyển sang profile mới. Việc ngừng dùng để ghi và việc không còn cần để đọc là hai mốc khác nhau.

## 13. Khi dịch vụ khóa hoặc thao tác giải mã thất bại

Các tình huống cần được đặc tả riêng gồm:

- Dịch vụ khóa không khả dụng hoặc timeout.
- Danh tính dịch vụ không còn quyền dùng khóa.
- Key reference không thuộc danh mục được phép.
- Khóa hoặc phiên bản cần thiết không thể sử dụng theo trạng thái hiện tại.
- Ciphertext, tag hoặc context không đáp ứng kiểm tra.
- Bản lưu thiếu hoặc sai metadata.

Thuộc tính bắt buộc trong thiết kế minh họa là **không rơi về lưu hoặc trả plaintext ngoài chính sách để giữ khả dụng**.

Nếu không thể mã hóa dữ liệu cần bảo vệ, luồng ghi phải thất bại theo hợp đồng hoặc dùng một đường đệm đã được bảo vệ và phê duyệt từ trước. Không ghi tạm nội dung rõ vào một thư mục không thuộc inventory rồi hứa sẽ mã hóa sau.

Nếu không thể xác minh và giải mã, không trả dữ liệu rỗng như thể thành công, không dùng một bản cũ tùy ý và không gửi chi tiết khóa hoặc nội dung bản lưu trong response lỗi.

### Cache khóa làm thay đổi độ trễ thu hồi

Nếu ứng dụng cache DEK hoặc vật liệu có thể dùng để giải mã, việc thay quyền ở dịch vụ khóa không nhất thiết chặn ngay mọi thao tác trong tiến trình đã có vật liệu đó. Cache plaintext sau giải mã còn tạo một phụ thuộc khác.

Chính sách phải quy định phạm vi, thời gian giữ và hành vi invalidation. Không cam kết “thu hồi khóa có hiệu lực tức thì ở mọi nơi” nếu thiết kế vẫn có các bản sao vật liệu hoặc dữ liệu rõ chưa được kiểm soát.

Khả năng retry cũng cần gắn với tính nhất quán của thao tác. Timeout lúc lưu envelope không tự chứng minh dữ liệu chưa được ghi; cơ chế phục hồi phải tránh tạo bản trùng hoặc mất đồng bộ metadata.

## 14. Xóa khóa và xóa dữ liệu không thể đánh đồng

Tổ chức có thể dùng việc loại bỏ khả năng giải mã như một phần của chiến lược kết thúc vòng đời dữ liệu. Để có ý nghĩa, cần biết những khóa nào thực sự bảo vệ tập dữ liệu, có bản sao vật liệu ở đâu và liệu plaintext đã tồn tại ngoài lớp đó hay chưa.

Một khóa dùng chung cho nhiều tenant hoặc nhiều nhóm dữ liệu có thể không phù hợp để xóa riêng một hồ sơ. Ngược lại, chỉ xóa một bản wrapped DEK ở database hoạt động chưa giải quyết các bản sao lịch sử có thể còn giữ cùng thông tin.

Yêu cầu cần xác định:

- Đơn vị dữ liệu được áp dụng chính sách xóa.
- Quan hệ giữa đơn vị đó và hệ thống khóa.
- Các bản backup, replica, export cùng cache liên quan.
- Quy trình quyền hạn và kiểm tra phụ thuộc trước thao tác khó phục hồi.
- Bằng chứng hoàn tất và giới hạn của kết luận.

Không dùng bài thử hủy khóa production để chứng minh cơ chế. Những phép thử ảnh hưởng khả năng khôi phục phải dùng dữ liệu và khóa thử trong môi trường thích hợp, cùng mục tiêu kiểm chứng đã được xác định.

## 15. Dữ liệu rõ vẫn xuất hiện ở nơi sử dụng hợp lệ

Khi một dịch vụ được phép giải mã để xử lý, dữ liệu rõ có thể đi vào bộ nhớ, serializer, response, file xử lý hoặc thư viện bên ngoài. Mã hóa bản lưu không giảm trách nhiệm kiểm soát các đường này.

Ví dụ, một pipeline giải mã tài liệu rồi ghi toàn bộ nội dung vào log để chẩn đoán đã tạo một bản lưu mới. Một công cụ chuyển đổi file có thể ghi file tạm ngoài volume được bảo vệ. Một search index có thể giữ trích đoạn quá rộng.

Vì vậy, các yêu cầu bổ sung nên gồm:

- Chỉ giải mã phần dữ liệu cần cho tác vụ được phép.
- Giới hạn thời gian giữ plaintext và quyền đọc kênh xử lý.
- Không đưa key material hoặc nội dung nhạy cảm vào log/trace theo mặc định.
- Quản lý file tạm, dump và bản chẩn đoán theo inventory.
- Áp dụng phân quyền và giảm thiểu dữ liệu trước khi tạo response.
- Bảo vệ đường truyền giữa các thành phần khi dữ liệu di chuyển.

Mã hóa cũng không nhất thiết che mọi metadata như kích thước, thời điểm, số bản ghi hoặc quan hệ truy cập. Nếu những thông tin đó nhạy cảm với mô hình đe dọa, cần yêu cầu riêng thay vì mặc định ciphertext đã giấu mọi thứ.

### Nhu cầu tìm kiếm không phải lý do tự đổi cơ chế mật mã

Ứng dụng có thể cần tìm theo một trường đã được bảo vệ. Không tự chuyển sang một chế độ xác định hoặc tạo hash của dữ liệu dễ đoán chỉ để truy vấn hoạt động.

Thiết kế tìm kiếm trên dữ liệu được bảo vệ phải nêu khả năng rò rỉ mẫu, tập dữ liệu ứng viên và quyền truy vấn. Nếu chức năng không cần giữ toàn bộ nội dung, giảm dữ liệu hoặc đổi mô hình nghiệp vụ có thể là một phần của giải pháp.

## 16. Mẫu yêu cầu bảo mật có thể nghiệm thu

| ID | Yêu cầu | Bằng chứng nghiệm thu |
| --- | --- | --- |
| REST-ENC-01 | Có inventory các nơi lưu dữ liệu thuộc phân loại cần bảo vệ, gồm bản sao và dữ liệu dẫn xuất | Đối chiếu luồng dữ liệu với database, file, backup, export và kênh trung gian |
| REST-ENC-02 | Mỗi nhóm dữ liệu có threat model và lớp mã hóa phù hợp với quyền tấn công giả định | Tài liệu nêu rõ điểm plaintext xuất hiện và những quyền mã hóa không thay thế |
| REST-ENC-03 | Profile thuật toán, thư viện và tham số được kiểm soát; không có cơ chế tự sáng tác | Danh mục profile và đường thực thi khớp cấu hình đang dùng |
| REST-ENC-04 | Quyền dữ liệu, quyền sử dụng khóa và quyền quản trị khóa được phân định theo nhiệm vụ | Thử quyền với các danh tính khác nhau trong môi trường kiểm chứng |
| REST-ENC-05 | Bản lưu ứng dụng có định dạng phiên bản và ràng buộc ngữ cảnh phù hợp | Thử metadata sai, context sai và chuyển bản lưu giữa tài nguyên/tenant |
| REST-ENC-06 | Nonce và các giới hạn sử dụng được quản lý theo profile, bao gồm retry và xử lý file lớn | Đối chiếu cơ chế thư viện, quy tắc cấp vật liệu và các đường ghi |
| REST-ENC-07 | Lỗi khóa hoặc xác minh không tạo fallback plaintext hay dữ liệu giả thành công | Gây lỗi có kiểm soát và kiểm tra cả storage lẫn output |
| REST-ENC-08 | Rotation, rewrap và mã hóa lại có phạm vi cùng tiêu chí hoàn tất riêng | Báo cáo theo phiên bản, dữ liệu tồn đọng và bản sao liên quan |
| REST-ENC-09 | Backup được bảo vệ và có thể restore với quyền, khóa, metadata cần thiết | Diễn tập phục hồi ở môi trường đích đã xác định |
| REST-ENC-10 | Chính sách cache vật liệu khóa và dữ liệu rõ nêu giới hạn ảnh hưởng thu hồi | Đo hành vi khi thay quyền/khả năng dùng khóa trong điều kiện thử |
| REST-ENC-11 | Log, file tạm, index và bản chẩn đoán không trở thành đường lưu rõ ngoài chính sách | Kiểm tra bằng dữ liệu tổng hợp có thể nhận diện và quyền truy cập phù hợp |
| REST-ENC-12 | Ngừng hoặc hủy khóa có kiểm tra phụ thuộc dữ liệu/backup và quyền hạn riêng | Hồ sơ phụ thuộc cùng bằng chứng phép thử trên khóa, dữ liệu thử |

Đây là ví dụ đặc tả cho dự án, không phải chứng nhận đáp ứng một tiêu chuẩn pháp lý hoặc một sản phẩm cụ thể. Mỗi yêu cầu cần được gắn với dữ liệu, owner và môi trường kiểm chứng thật.

## 17. Kịch bản chấp nhận minh họa

### 17.1. Bản lưu bị sao chép nhưng không có quyền khóa

```text
Given:
  Tài liệu kiểm thử thuộc phạm vi mã hóa đã xác định.
  Có một bản lưu theo đúng lớp và định dạng đang được đánh giá.
  Danh tính thử không có quyền khôi phục khóa cần thiết.

When:
  Thử truy cập bản lưu trong môi trường kiểm chứng được phép.

Then:
  Không khôi phục được nội dung rõ qua đường thuộc phạm vi yêu cầu.
  Không có key material rõ đi kèm bản lưu ngoài chính sách.
  Kết luận ghi rõ đang kiểm tra lớp lưu trữ nào và quyền nào.
```

### 17.2. Đọc hợp lệ và đọc chéo tenant

```text
Given:
  Có tài liệu của tenant A và tenant B.
  Request chỉ có quyền trên tài liệu của A.

When:
  Luồng xử lý gặp key reference hoặc envelope thuộc B.

Then:
  Chính sách không cho phép chọn khóa và giải mã chỉ vì metadata tự khai là B.
  Không trả nội dung của B.
  Luồng hợp lệ của A vẫn đọc đúng dữ liệu theo quyền được cấp.
```

### 17.3. Ciphertext hoặc ngữ cảnh bị thay đổi

```text
Given:
  Profile tài liệu có xác thực ciphertext và ngữ cảnh.
  Có một bản dữ liệu tổng hợp để thử thay đổi.

When:
  Sửa payload, vật liệu xác thực hoặc context theo kịch bản thử.

Then:
  Không sử dụng nội dung như dữ liệu đã được xác minh.
  Không fallback sang plaintext hoặc profile không được phép.
  Response lỗi và log không chứa khóa hay nội dung tài liệu.
```

### 17.4. Dịch vụ khóa không khả dụng

```text
Given:
  Luồng ghi cần mã hóa dữ liệu thuộc phân loại được bảo vệ.
  Không có vật liệu cache còn hợp lệ theo chính sách cho thao tác đó.

When:
  Dịch vụ khóa không đáp ứng yêu cầu.

Then:
  Luồng xử lý không lưu plaintext ngoài một cơ chế đã được phê duyệt.
  Client nhận kết quả lỗi theo hợp đồng khả dụng.
  Không báo thành công khi chưa lưu được dữ liệu đúng yêu cầu.
```

### 17.5. Phục hồi backup sau thay đổi khóa

```text
Given:
  Backup kiểm thử được tạo dưới một profile hoặc phiên bản khóa trước.
  Hệ thống hiện đã có chính sách ghi mới khác.

When:
  Thực hiện restore trong môi trường được cấp quyền theo runbook.

Then:
  Có đủ phụ thuộc cần thiết để đọc đúng dữ liệu theo mục tiêu phục hồi.
  Không cần sao chép plaintext sang nơi ngoài chính sách để hoàn thành phép thử.
  Báo cáo chỉ ra dữ liệu/khóa cũ nào vẫn cần được giữ.
```

## 18. Bằng chứng kỹ thuật và giới hạn của kết luận

| Bằng chứng | Điều có thể hỗ trợ | Điều chưa chứng minh một mình |
| --- | --- | --- |
| Cấu hình bật mã hóa | Chính sách được khai báo ở một tài nguyên | Mọi dữ liệu cũ và mọi bản sao đã được chuyển xong |
| Trạng thái mã hóa từ nền tảng | Tiến trình/trạng thái của lớp tương ứng | Export hoặc nơi lưu khác cũng có cùng bảo vệ |
| Đọc lại thành công | Có khả năng sử dụng dữ liệu theo luồng thử | Chủ thể không có quyền cũng bị chặn đúng |
| Thử thiếu quyền khóa | Một ranh giới quyền hoạt động theo kịch bản | Mọi principal và mọi đường bypass đều đã được bao phủ |
| Thử sửa dữ liệu | Profile phát hiện những sai lệch đã thử | Dữ liệu luôn mới nhất hoặc nghiệp vụ luôn đúng |
| Restore thành công | Backup cùng phụ thuộc thử có thể khôi phục | Mọi thời điểm retention và mọi vùng đích đều được hỗ trợ |
| Không tìm thấy chuỗi đánh dấu rõ | Một dấu hiệu hỗ trợ kiểm tra đường lưu | Một chứng minh mật mã đầy đủ chỉ từ quan sát byte |

Không đánh giá chất lượng mã hóa bằng việc ciphertext “trông ngẫu nhiên” hoặc chỉ vì dữ liệu đã chuyển thành Base64. Bằng chứng phải kết hợp profile, cấu hình, quyền, hành vi và các đường dữ liệu thực tế.

Khi lớp mã hóa trong suốt tự giải mã cho client hợp lệ, một logical export có thể phản ánh luồng đọc đã được cấp quyền thay vì trạng thái vật lý của bản lưu. Phép thử cần chọn đúng ranh giới muốn đánh giá, không dùng một đường đọc rồi suy kết luận cho lớp khác.

Các thử nghiệm nên dùng dữ liệu tổng hợp và quyền được cấp cho môi trường kiểm chứng. Nội dung hồ sơ thật hoặc vật liệu khóa thật không nên được đưa vào báo cáo để làm minh chứng.

## 19. Duy trì yêu cầu khi hệ thống thay đổi

Khi thêm một export, chỉ mục tìm kiếm, hàng đợi hoặc vùng dự phòng, nhóm cần cập nhật inventory dữ liệu và phụ thuộc khóa trước khi coi chức năng mới đã thừa hưởng đầy đủ bảo vệ. Khi thay provider hoặc thư viện, cần giữ khả năng đọc dữ liệu theo những phiên bản còn thuộc retention.

Khi quyền dịch vụ thay đổi, đánh giá cả quyền lấy bản lưu và quyền giải mã. Khi triển khai cache để giảm độ trễ, xem lại thời gian hiệu lực thu hồi. Khi lên kế hoạch xóa dữ liệu hoặc ngừng khóa, kiểm tra các bản sao lịch sử và nhu cầu phục hồi còn tồn tại.

Thiết kế mã hóa at rest đạt mục tiêu khi bản lưu được bảo vệ đúng trước năng lực tấn công đã xác định, quyền dùng khóa có thể kiểm soát và dữ liệu vẫn khôi phục được theo cam kết. Thuật toán phù hợp, phạm vi dữ liệu đầy đủ, quản lý khóa và bằng chứng phục hồi phải cùng tạo thành yêu cầu; không thành phần nào tự thay thế phần còn lại.
