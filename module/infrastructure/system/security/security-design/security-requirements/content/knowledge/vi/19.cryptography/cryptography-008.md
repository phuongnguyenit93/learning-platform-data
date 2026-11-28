# Key derivation

## 1. Dẫn xuất khóa cần giải quyết vấn đề nào?

Một ứng dụng có thể cần tạo khóa mã hóa từ mật khẩu người dùng, hoặc tạo nhiều khóa có mục đích khác nhau từ một bí mật gốc được quản lý. Hai tình huống đều được gọi là **key derivation**, nhưng có nguồn đầu vào và yêu cầu bảo mật khác nhau.

**Key Derivation Function**, viết tắt là **KDF**, là cơ chế tạo vật liệu khóa từ bí mật đầu vào cùng những tham số được xác định. Đầu ra phải phù hợp với cách sử dụng dự kiến, còn toàn bộ quá trình phải giữ đúng các giả định về entropy, ngữ cảnh và vòng đời bí mật.

Trong thiết kế yêu cầu bảo mật, câu “hash mật khẩu để lấy khóa” hoặc “dùng HKDF” chưa đủ. Cần trả lời:

1. Bí mật đầu vào được tạo thế nào và bên tấn công có thể đoán nó đến mức nào?
2. Mục tiêu là làm tốn chi phí đoán mật khẩu hay tách khóa từ một nguồn bí mật mạnh?
3. Salt, tham số chi phí và ngữ cảnh có ý nghĩa gì trong profile đã chọn?
4. Khóa đầu ra được dùng cho đúng một vai trò hay bị dùng lại cho nhiều mục đích?
5. Những dữ liệu nào phải giữ để dẫn xuất lại và phục hồi dữ liệu?
6. Nếu bí mật gốc bị lộ, đổi mật khẩu hoặc thay profile, hệ thống chuyển đổi ra sao?

Kết quả cần đạt là một hợp đồng có thể triển khai và kiểm chứng, không chỉ một lời gọi thư viện cho ra một mảng byte đủ dài.

## 2. Hai nhóm KDF phải được phân biệt

| Nguồn đầu vào | Vấn đề chính | Hướng thiết kế |
| --- | --- | --- |
| Mật khẩu do con người chọn | Đầu vào có thể thuộc một tập dễ đoán, bị thử offline | Password-based KDF có salt và chi phí phù hợp |
| Bí mật ngẫu nhiên có entropy cao | Cần chuẩn hóa hoặc tách vật liệu cho các mục đích | KDF theo giao thức/profile như HKDF |
| Bí mật được thiết lập qua giao thức trao đổi khóa | Cần chuyển bí mật chung thành khóa sử dụng được và gắn với ngữ cảnh | Dùng KDF đúng đặc tả giao thức đã chọn |
| Giá trị công khai như email, user ID hoặc timestamp | Không có bí mật đầu vào để bảo vệ | Không thể biến thành khóa bí mật chỉ bằng một KDF công khai |

Một chuỗi dài không nhất thiết có entropy cao. Base64 của một mật khẩu ngắn vẫn mang giới hạn của mật khẩu đó. Một UUID hoặc định danh do hệ thống cấp cũng không được tự mặc định là nguồn khóa có thuộc tính mật mã phù hợp.

### Độ dài đầu ra không phải entropy của đầu vào

Nếu người dùng chọn mật khẩu từ một tập nhỏ, việc tạo ra 32 byte không làm bên tấn công phải thử mọi khả năng của một khóa ngẫu nhiên 256 bit. Họ có thể thử các mật khẩu ứng viên rồi chạy cùng quy trình dẫn xuất.

Tương tự, kéo dài khóa gốc yếu thành nhiều khóa dài không tạo ra bí mật mới độc lập với nguồn ban đầu. Yêu cầu về nguồn entropy phải được đặt trước yêu cầu về độ dài đầu ra.

## 3. Mô hình đe dọa tối thiểu

Giả sử ứng dụng lưu một kho tài liệu được mở bằng mật khẩu và có một dịch vụ khác tách khóa theo mục đích từ root secret. Nhóm thiết kế nên phân tích ít nhất:

| Năng lực giả định của bên tấn công | Câu hỏi cần trả lời |
| --- | --- |
| Lấy được ciphertext cùng salt và metadata | Chi phí đoán mật khẩu offline là bao nhiêu trong mô hình đã đánh giá? |
| Sửa metadata KDF | Có thể ép dùng profile yếu hơn hoặc gây tiêu thụ tài nguyên quá mức không? |
| Lấy được một khóa con | Nó có bị dùng lại cho chức năng khác hoặc cho phép mở rộng phạm vi không? |
| Lấy được root secret | Phạm vi khóa có thể dẫn xuất và dữ liệu bị ảnh hưởng là gì? |
| Biết hoặc chọn tenant ID/context | Giá trị công khai có thể làm thay quyết định quyền sử dụng khóa không? |
| Giữ một bản dữ liệu cũ | Profile và bí mật nào còn cho phép khôi phục nó? |
| Gây nhiều request dẫn xuất đồng thời | Bộ nhớ, CPU và hàng đợi có bị vượt ngân sách không? |

Không chỉ mô tả “KDF chống brute force”. Với một nguồn mật khẩu, điều cần đo là chi phí mỗi lần thử và giới hạn thực tế của mật khẩu. Với một nguồn mạnh, điều cần kiểm tra có thể chủ yếu là tách ngữ cảnh, quản lý root và độ đúng của implementation.

## 4. Password-based KDF: tăng chi phí đoán, không xóa được rủi ro đoán

Một password-based KDF nhận mật khẩu và các tham số để tạo giá trị dẫn xuất. Profile phải chọn cơ chế phù hợp, thay vì dùng một phép hash nhanh đơn lẻ hoặc tự lặp hash theo công thức riêng.

PBKDF2 mô hình hóa mật khẩu, salt, iteration count, PRF và độ dài đầu ra; các tham số này được trình bày tại [RFC 8018, mục 5.2](https://www.rfc-editor.org/rfc/rfc8018#section-5.2). Nếu chọn PBKDF2, PRF và tham số phải được chỉ rõ, không phụ thuộc một giá trị mặc định không ai kiểm soát.

Argon2 là một họ hàm memory-hard. Với một profile dùng Argon2id, cần xác định biến thể, phiên bản, ngân sách bộ nhớ, số pass, mức song song và độ dài đầu ra. [RFC 9106](https://www.rfc-editor.org/rfc/rfc9106) mô tả các tham số và test vector của họ hàm này.

Không nên chọn một hàm chỉ vì nó có trong runtime đang dùng. Cũng không chọn chi phí thật thấp chỉ để một endpoint chạy nhanh trong thử nghiệm đơn người dùng.

### Profile phải được hiệu chỉnh trên môi trường thật

[OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html) nhấn mạnh việc cân bằng work factor với năng lực hệ thống và đánh giá chi phí trên hạ tầng phù hợp. Các khuyến nghị tham số có thể thay đổi; dự án cần quản lý profile và chu kỳ đánh giá thay vì chép một con số cũ thành cam kết vô thời hạn.

Trong thiết kế dự án, việc hiệu chỉnh nên nêu:

- Tập thiết bị hoặc máy chủ phải hỗ trợ.
- Độ trễ mục tiêu của tác vụ hợp lệ.
- Ngân sách bộ nhớ và CPU cho mỗi tác vụ.
- Số tác vụ đồng thời và hành vi khi hàng đợi đầy.
- Giới hạn request và biện pháp chống lạm dụng trực tuyến.
- Người chịu trách nhiệm đánh giá lại khi hạ tầng hoặc threat model đổi.

Không có một bộ tham số tối ưu cho mọi server, điện thoại và client trong trình duyệt. Một profile chỉ được chấp nhận khi đáp ứng cả mức bảo vệ đã chọn và điều kiện vận hành cụ thể.

### Offline và online là hai tình huống khác nhau

Rate limiting endpoint giúp giảm một số cách thử trực tuyến. Nó không giới hạn máy tính của người đã lấy được bản mã và metadata rồi thử mật khẩu offline.

Nếu định dạng mã hóa có cơ chế xác minh kết quả, bên thử có thể dùng cơ chế đó để biết một mật khẩu ứng viên có phù hợp hay không. KDF làm tăng chi phí của quá trình thử, nhưng không làm một mật khẩu dễ đoán tự trở thành an toàn.

Nếu hệ thống thêm một bí mật server riêng vào thiết kế, cần mô tả tác động của bí mật đó lên quyền truy cập, backup, phục hồi và sự cố. Không gọi nó là salt rồi giả định thuộc tính giống salt công khai.

## 5. Salt, context và nonce không có cùng vai trò

| Giá trị | Vai trò trong thiết kế | Điều không nên nhầm |
| --- | --- | --- |
| Password | Bí mật có thể cần làm chậm việc đoán | Không phải khóa ngẫu nhiên chỉ vì đã encode |
| Root secret hoặc IKM | Nguồn bí mật cho một KDF theo profile | Không được thay bằng định danh công khai |
| Salt của password-based KDF | Phân tách các lần dẫn xuất, chống tái sử dụng phép tính giữa những bản có salt khác | Không phải bí mật thay cho mật khẩu |
| Salt trong HKDF | Đầu vào của bước Extract theo đặc tả/profile | Không áp nguyên mọi quy tắc password salt cho mọi giao thức HKDF |
| Context hoặc info | Gắn khóa với mục đích và ngữ cảnh | Không tự tạo quyền truy cập hoặc entropy bí mật |
| Nonce/IV của mã hóa | Tham số của cơ chế mã hóa sử dụng khóa | Salt KDF không tự đáp ứng quy tắc nonce của cipher |
| Bí mật bổ sung của server | Một thành phần bí mật riêng nếu thiết kế có dùng | Không được lưu và quản lý như metadata công khai |

Đối với profile password-based của dự án, nên xác định cách tạo salt bằng nguồn ngẫu nhiên mật mã phù hợp, độ dài và phạm vi tạo mới. Salt thường cần được lưu cùng metadata để có thể tái tạo khóa; việc nó không cần giữ bí mật không làm tính toàn vẹn của metadata trở nên không quan trọng.

Không dùng cùng một salt cố định cho mọi kho người dùng chỉ để đơn giản hóa database. Không dùng user ID làm một giá trị thay thế ngẫu nhiên mà không có cơ sở của profile. Khi tạo một đối tượng mã hóa độc lập mới, quy tắc tạo salt phải được thực thi theo hợp đồng đã chọn.

Trong một giao thức đã quy định salt HKDF cụ thể hoặc cách xử lý khi không có salt, implementation phải theo giao thức đó. Không tự sửa tham số trên một phía rồi mong các bên vẫn dẫn xuất cùng kết quả.

## 6. HKDF và giới hạn của nó

HKDF có hai bước Extract và Expand. Extract tạo PRK từ IKM cùng salt; Expand tạo vật liệu đầu ra theo PRK, info và độ dài. `info` hỗ trợ ràng buộc ngữ cảnh. HKDF không được thiết kế để làm chậm việc đoán mật khẩu; nó không tăng entropy vốn có của đầu vào. [RFC 5869](https://www.rfc-editor.org/rfc/rfc5869) mô tả rõ sự khác biệt này.

Công thức khái niệm:

```text
PRK = HKDF-Extract(salt, IKM)
OKM = HKDF-Expand(PRK, info, L)
```

`L` là số byte của vật liệu đầu ra trong biểu diễn này. Với HKDF, đầu ra có giới hạn theo kích thước hash; profile phải kiểm tra giới hạn của cơ chế và thư viện, không chỉ kiểm tra `L > 0`.

Không thay password-based KDF bằng HKDF chỉ vì HKDF tạo được khóa đúng kích thước. Nếu thiết kế bắt đầu từ mật khẩu, có thể cần một bước password-based được kiểm soát trước khi tiếp tục tách các khóa theo mục đích, nhưng toàn bộ composition phải thuộc một profile được xác định.

Đối với bí mật từ trao đổi khóa, KDF cũng không tự xác thực peer hoặc sửa một giao thức trao đổi không an toàn. Những kiểm tra về khóa công khai và danh tính phải thuộc giao thức cùng thư viện đã chọn.

## 7. Domain separation: tách khóa theo mục đích rõ ràng

Giả sử dịch vụ cần một khóa bảo vệ nội dung và một khóa khác cho một chức năng MAC độc lập. Không nên dùng trực tiếp cùng một mảng byte cho cả hai chỉ vì cùng có độ dài chấp nhận được.

Một lịch dẫn xuất minh họa có thể là:

```text
Root secret được quản lý
    → bước dẫn xuất được profile cho phép
        ├── context: document-encryption / suite-A / version-1
        └── context: event-authentication / suite-B / version-1
```

Đây là ví dụ phân tách mục đích, không phải yêu cầu phải tự ghép mã hóa với MAC thay cho một primitive AEAD phù hợp. Những khóa nào thực sự cần tồn tại phải do kiến trúc quyết định.

### Context phải có cấu trúc không mơ hồ

Ví dụ một context logic:

```text
encode_fields(
    protocolVersion = 1,
    service = "document-service",
    purpose = "document-encryption",
    tenantRef = "tenant-demo-01",
    algorithmProfile = "approved-suite-A",
    outputLengthBytes = 32
)
```

`encode_fields` biểu thị một cách mã hóa trường đã được định nghĩa và quản lý phiên bản. Nó không phải lời khuyên nối các chuỗi tùy ý bằng một ký tự phân cách.

Yêu cầu cần xác định:

- Tên và thứ tự trường hoặc một định dạng chuẩn hóa tương ứng.
- Đơn vị, kiểu và giới hạn độ dài của từng trường.
- Cách xử lý trường vắng mặt so với trường rỗng.
- Cách biểu diễn chuỗi và số.
- Những trường nào có nguồn gốc từ trạng thái có thẩm quyền.
- Cách thay đổi version mà không vô tình tái sử dụng cùng ngữ cảnh cho mục đích khác.

Đừng dựa vào việc “hai JSON trông giống nhau” nếu cách serialization không được cố định cho thao tác mật mã. Thứ tự, encoding và quy tắc chuẩn hóa phải tạo ra cùng byte ở các implementation cần tương tác.

### Đổi độ dài không phải một cơ chế tách mục đích độc lập

Với HKDF-Expand giữ cùng PRK và info, thay `L` có thể tạo các đầu ra có quan hệ tiền tố. Vì vậy, không nên lấy 16 byte cho mục đích A và 32 byte cho mục đích B với cùng mọi đầu vào rồi coi đó là hai miền độc lập.

Đặc tả của dự án nên dùng nhãn mục đích khác nhau và đưa các thuộc tính cần thiết vào context theo lịch dẫn xuất đã chọn. Độ dài khóa là một tham số của profile, không thay thế nhãn sử dụng.

## 8. Khóa con không tự tạo ranh giới phân quyền

Một hệ thống nhiều tenant có thể dẫn xuất khóa theo tenant ID. Điều đó không có nghĩa người biết tenant ID được phép yêu cầu khóa tương ứng.

Luồng xử lý phải kiểm tra danh tính và quyền trên tài nguyên trước khi quyết định ngữ cảnh được phép. Không lấy một giá trị từ body request làm nguồn có thẩm quyền cho quyền sử dụng root secret.

Ví dụ:

```text
Request của chủ thể A
    → xác minh danh tính và quyền với tài nguyên
    → xác định tenant từ trạng thái có thẩm quyền
    → chọn profile và nguồn bí mật được phép
    → tạo context đúng mục đích
    → dẫn xuất và sử dụng khóa trong phạm vi tác vụ
```

### Root quyết định phạm vi ảnh hưởng

Nếu cùng một root có thể tạo khóa cho nhiều tenant, chiếm được root hoặc quyền sử dụng root quá rộng có thể ảnh hưởng nhiều tenant. Một nhãn tenant khác nhau hỗ trợ phân tách ngữ cảnh, nhưng không biến một root chung thành các bí mật gốc hoàn toàn độc lập.

Nếu yêu cầu cần thu hồi, xóa hoặc giao quyền quản lý riêng từng tenant, phải kiểm tra cây khóa có đáp ứng được mục tiêu đó hay không. Có thể cần những ranh giới vật liệu khóa hoặc chính sách sử dụng riêng thay vì chỉ thêm tenant ID vào context.

Tương tự, không dùng một khóa con vừa làm khóa mã hóa vừa làm root tự do cho các tác vụ khác. Vai trò và phạm vi dẫn xuất tiếp phải được định nghĩa, nếu kiến trúc thực sự cần một cây khóa nhiều cấp.

## 9. Metadata dẫn xuất là một phần của định dạng dữ liệu

Để đọc lại một đối tượng được bảo vệ bằng mật khẩu, ứng dụng có thể cần salt, profile ID và những tham số liên quan. Để dẫn xuất từ root được quản lý, nó có thể cần root version, context version cùng danh mục profile.

Một metadata minh họa:

```json
{
  "formatVersion": 1,
  "kdfProfile": "vault-password-profile-3",
  "salt": "<encoded-random-salt>",
  "contextVersion": 1,
  "keyLengthBytes": 32,
  "encryptedPayload": "<encoded-authenticated-payload>"
}
```

Đây là một định dạng giả định. Các placeholder không phải giá trị mật mã thật. Profile ID phải ánh xạ tới một tập tham số cụ thể, được quản lý và giữ đủ lâu cho nhu cầu đọc dữ liệu.

### Không tin tham số chỉ vì chúng nằm trong file của ứng dụng

Một bản lưu bị sửa có thể yêu cầu số vòng lặp rất lớn, bộ nhớ vượt ngân sách hoặc độ dài đầu ra không hợp lý. Cần kiểm tra cấu trúc, kiểu, kích thước và giới hạn chính sách trước khi chạy thao tác tốn tài nguyên.

Ngược lại, nếu cho bên gọi chọn số vòng lặp thấp hoặc profile yếu tùy ý, hệ thống có thể tạo dữ liệu mới không đạt chính sách. Profile cho ghi mới và profile được phép đọc dữ liệu cũ nên được quản lý riêng.

Nếu metadata được xác thực cùng ciphertext, việc xác minh đó có thể chỉ diễn ra sau khi đã dẫn xuất được khóa. Do đó, kiểm tra giới hạn trước KDF vẫn cần thiết; không thể trông chờ một bước xác thực ở cuối bảo vệ mọi chi phí trước đó.

### Metadata công khai vẫn có thể nhạy cảm

Salt và nhãn mục đích thường không phải secret, nhưng context có thể chứa thông tin về tenant, đối tượng hoặc người dùng. Chỉ đưa những giá trị cần thiết vào định dạng và xem xét nơi chúng sẽ được lưu hoặc ghi log.

Không nhét mật khẩu, root secret hay khóa đầu ra vào metadata để tiện debug hoặc phục hồi.

## 10. Hợp đồng mật khẩu và tính tương tác giữa implementation

Một KDF làm việc trên biểu diễn đầu vào xác định. Hai chương trình nhận cùng chuỗi hiển thị nhưng chuyển sang byte khác nhau có thể tạo khóa khác nhau.

Yêu cầu nên nêu rõ:

1. Dữ liệu đầu vào là byte hay chuỗi theo giao diện nào.
2. Encoding và quy tắc Unicode mà giao thức lựa chọn.
3. Có chuẩn hóa hay không, và version nào quyết định hành vi đó.
4. Có cho phép ký tự NUL hoặc các chuỗi không hợp lệ theo giao diện không.
5. Giới hạn độ dài tính bằng ký tự, code unit hay byte.
6. Không trim, đổi hoa/thường hoặc cắt bớt âm thầm.

Không tự chuẩn hóa mật khẩu sau một lần nâng phiên bản thư viện nếu hành vi cũ chưa làm vậy. Điều này có thể làm người dùng không mở được dữ liệu dù họ nhập mật khẩu mà họ vẫn sử dụng trước đó.

Trong Java, API như `PBEKeySpec` có quy tắc về mảng ký tự, bản sao nội bộ và `clearPassword()`. Chi tiết phải được hiểu theo [tài liệu PBEKeySpec của Java](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/spec/PBEKeySpec.html), cơ chế PBE và provider được chọn; không suy rằng mọi cơ chế luôn diễn giải ký tự giống nhau.

Ví dụ điểm tích hợp về mặt hình dạng API:

```text
PBEKeySpec(
    passwordCharacters,
    saltBytes,
    approvedIterationCount,
    outputKeyLengthBits
)
```

Đây không phải một cấu hình PBKDF2 hoàn chỉnh: còn cần PRF, provider, policy và nơi sử dụng kết quả. Cũng cần chú ý tên tham số tính bằng bit ở giao diện này khác với byte trong nhiều đặc tả và API khác. Khóa 32 byte tương ứng 256 bit, không phải 32 bit.

Các test vector chuẩn và vector riêng của định dạng dự án giúp phát hiện lỗi encoding, đơn vị và phiên bản. Việc hai chương trình đều tạo ra một kết quả dài 32 byte không đủ chứng minh chúng tương tác đúng.

## 11. Hai luồng xử lý minh họa

Mã giả dưới đây mô tả trách nhiệm, không phải implementation mật mã để thay cho thư viện được duyệt.

### 11.1. Tạo một kho được mở bằng mật khẩu

```text
createVault(identity, password, plaintext):
    authorizeVaultCreation(identity)
    profile = selectTrustedWriteProfile()
    validatePasswordInputAccordingToProfile(password, profile)
    salt = generateSaltAccordingToProfile(profile)

    derivedSecret = approvedPasswordKdf.derive(password, salt, profile)

    try:
        context = buildVersionedContextFromTrustedState(identity, profile)
        encryptionKey = derivePurposeKeyIfProfileRequires(derivedSecret, context)
        payload = approvedEncryption.encryptAndAuthenticate(
            encryptionKey,
            plaintext,
            authenticatedMetadata(profile, salt, context)
        )
        persistVersionedVault(profile, salt, context, payload)
    finally:
        releaseSensitiveMaterialAccordingToRuntimeCapabilities()
```

Profile có thể chọn mã hóa trực tiếp bằng khóa phù hợp hoặc dùng khóa dẫn xuất để bảo vệ một DEK ngẫu nhiên. Hai mô hình có ảnh hưởng khác nhau tới đổi mật khẩu và khối lượng dữ liệu phải mã hóa lại.

### 11.2. Dẫn xuất khóa từ root cho một tác vụ dịch vụ

```text
usePurposeKey(identity, resourceRef, operation):
    resource = resolveAuthorizedResource(identity, resourceRef, operation)
    profile = selectTrustedServiceProfile(resource, operation)
    context = encodeApprovedContext(resource, operation, profile)

    rootCapability = obtainAuthorizedRootCapability(profile, resource)
    purposeKey = approvedKdf.derive(rootCapability, context, profile)

    try:
        performOnlyApprovedOperation(purposeKey, resource, operation)
    finally:
        releaseSensitiveMaterialAccordingToRuntimeCapabilities()
```

Trong một triển khai, root có thể được sử dụng qua dịch vụ hoặc phần cứng thay vì đưa vật liệu rõ vào ứng dụng. Yêu cầu phải nói đúng khả năng của cơ chế được chọn, không hứa rằng mọi KMS đều thực hiện cùng một loại KDF hoặc cùng một giao diện.

Ở cả hai luồng, lỗi dẫn xuất không được khiến hệ thống chuyển sang khóa cố định, mật khẩu rút ngắn hoặc một thuật toán yếu hơn để tiếp tục xử lý.

## 12. Quản lý tài nguyên là một phần của yêu cầu KDF

Một cơ chế làm tốn CPU/bộ nhớ có chủ đích cũng cần được bảo vệ khỏi lạm dụng tài nguyên của hệ thống.

Đối với profile dùng mật khẩu, dự án nên quy định:

- Tập profile và bộ tham số được phép.
- Trần bộ nhớ, số pass/iteration và độ dài đầu ra có thể chấp nhận khi đọc.
- Giới hạn kích thước đầu vào và cách xử lý dữ liệu sai cấu trúc.
- Số tác vụ đồng thời, ngân sách hàng đợi và hành vi từ chối khi quá tải.
- Chính sách rate limit hoặc điều kiện truy cập cho đường gọi trực tuyến.
- Cách đo độ trễ trên những thiết bị thuộc phạm vi hỗ trợ.

Đừng cho một giá trị metadata yêu cầu cấp phát hàng gigabyte trước khi được kiểm tra. Cũng không giảm chi phí xuống dưới chính sách một cách tự động khi server bận; điều đó thay đổi thuộc tính bảo mật của dữ liệu được tạo.

Nếu dùng cache kết quả dẫn xuất để giảm độ trễ, cache đang giữ vật liệu nhạy cảm. Cần xác định phạm vi, thời gian sống, quyền truy cập và ảnh hưởng khi mật khẩu hoặc quyền sử dụng root thay đổi.

Độ trễ KDF không phải một cơ chế xác thực caller. Một bên đã có quyền gọi endpoint vẫn cần chịu các giới hạn thích hợp; một request chờ lâu không tự trở thành đáng tin.

## 13. Không dùng verifier mật khẩu làm khóa mã hóa

Giá trị lưu để kiểm tra đăng nhập và khóa dùng để mở dữ liệu có mục đích khác nhau. Không nên lấy trực tiếp giá trị password verifier trong database làm khóa mã hóa vì tiện tái sử dụng.

Nếu một bên lấy được database verifier, thiết kế như vậy có thể biến chính giá trị lưu đó thành vật liệu mở dữ liệu, thay vì vẫn phải có bí mật người dùng theo mục tiêu ban đầu.

Nếu một sản phẩm cần cả đăng nhập lẫn giải mã dựa trên mật khẩu, kiến trúc phải quy định rõ cách tách các mục đích, salt/profile tương ứng và các bí mật nào từng thành phần thực sự biết. Không tự ghép một hash đăng nhập với một cipher rồi mặc định đã có một hệ thống kho mật khẩu an toàn.

Việc cùng mật khẩu tạo ra các giá trị khác nhau theo profile cũng không xóa rủi ro từ chính mật khẩu ấy. Nếu một đường khác để lộ một verifier yếu hơn giúp tìm được mật khẩu, dữ liệu dùng cùng mật khẩu có thể tiếp tục bị ảnh hưởng.

## 14. Đổi mật khẩu, nâng profile và khả năng phục hồi

### Đổi mật khẩu không chỉ là sửa metadata

Nếu dữ liệu được mã hóa trực tiếp bằng khóa dẫn xuất từ mật khẩu cũ, mật khẩu mới tạo ra vật liệu khác. Không thể chỉ ghi đè salt hoặc profile ID rồi kỳ vọng ciphertext cũ tự mở được.

Một mô hình dùng DEK ngẫu nhiên được bảo vệ bằng khóa từ mật khẩu có thể cần rewrap DEK thay vì mã hóa lại toàn bộ dữ liệu. Tuy nhiên, việc này vẫn cần quyền, kiểm tra kết quả, tính nhất quán và phục hồi khi lỗi giữa chừng.

### Nâng tham số phải có migration

Khi nâng profile password-based, cần xác định lúc nào có đủ bí mật để chuyển dữ liệu, những đối tượng nào còn profile cũ và cách theo dõi hoàn tất. Với kho mã hóa phía người dùng, server có thể không tự thực hiện được nếu không có mật khẩu hoặc một cơ chế khôi phục khác đã thiết kế.

Không suy từ việc đã nâng cấu hình ghi mới rằng dữ liệu cũ đã được chuyển. Profile đọc cũ cần thời hạn hỗ trợ và chính sách rõ, không một nhánh fallback vô thời hạn chấp nhận mọi tham số yếu.

### Quên mật khẩu và reset tài khoản

Reset credential đăng nhập không tự khôi phục khóa mà người dùng không còn biết. Nếu yêu cầu sản phẩm cần phục hồi dữ liệu sau khi quên mật khẩu, phải có một kiến trúc khôi phục riêng cùng mô hình đe dọa và quyền hạn tương ứng.

Khả năng khôi phục có thể đồng thời tạo thêm chủ thể có thể mở dữ liệu. Đó là quyết định thiết kế phải được thể hiện trung thực, không thể hứa vừa không ai khác có khả năng giải mã vừa luôn reset được mà không có phụ thuộc bí mật nào.

## 15. Root bị lộ, thu hồi và giới hạn của dẫn xuất tất định

Đối với một lịch dẫn xuất tất định, giữ nguyên bí mật gốc và các đầu vào cần thiết cho phép tạo lại cùng vật liệu theo profile. Đây là điều hữu ích cho khả năng tái tạo, nhưng có hệ quả về thu hồi và xóa.

### Đổi label không xử lý việc lộ root

Nếu bên tấn công đã có root cùng profile, việc đổi `version-1` thành `version-2` trong context công khai không tự tạo một bí mật mới ngoài khả năng của họ. Khi root bị lộ, phương án xử lý phải xét thay nguồn bí mật và dữ liệu đã được bảo vệ dưới nguồn cũ.

Không mô tả việc tăng một số version như rotation vật liệu bí mật nếu root không thay đổi. Tên gọi trong vận hành cần phản ánh thao tác thực tế.

### Xóa khóa con chưa chắc làm dữ liệu không thể mở lại

Nếu root và ngữ cảnh vẫn tồn tại, việc xóa một bản khóa con trong cache hoặc database có thể không ngăn việc dẫn xuất lại. Một yêu cầu xóa khả năng giải mã phải xét toàn bộ nguồn bí mật và bản sao có thể tái tạo vật liệu đó.

Nếu nhiều đối tượng chung một root, không được mặc định có thể hủy riêng một đối tượng bằng cách hủy root mà không ảnh hưởng các đối tượng khác. Cấu trúc khóa cần phù hợp đơn vị thu hồi và retention của sản phẩm.

### Không tự có forward secrecy

Một thiết kế giữ root lâu dài cùng metadata lịch sử có thể cho phép tái tạo khóa cũ khi root bị lộ. Việc thêm ngày tháng hoặc request ID công khai vào context không tự tạo forward secrecy.

Nếu mục tiêu cần giới hạn tác động tới dữ liệu lịch sử, phải có thiết kế vòng đời bí mật phù hợp và bằng chứng riêng. Không gán thuộc tính đó cho KDF chỉ vì các khóa đầu ra khác nhau.

## 16. Bảo vệ vật liệu và thông tin chẩn đoán

Mật khẩu, root, PRK và khóa dẫn xuất đều là vật liệu cần bảo vệ theo vai trò của chúng. Không log đầu vào/đầu ra để so sánh hai implementation trong môi trường dùng bí mật thật.

Những yêu cầu vận hành nên bao gồm:

- Không lưu mật khẩu hoặc root cùng ciphertext dưới dạng có thể sử dụng trực tiếp ngoài chính sách.
- Chỉ giữ vật liệu dẫn xuất trong phạm vi tác vụ hoặc cache được phê duyệt.
- Không dùng mảng hoặc object chứa khóa làm nội dung thông báo lỗi.
- Bảo vệ heap dump, crash dump, trace và công cụ hỗ trợ có thể chụp bộ nhớ.
- Dọn các bản sao theo khả năng runtime, không hứa xóa mọi bản sao nếu không có cơ sở.
- Ghi mã profile, phiên bản và kết quả theo cách không làm lộ bí mật.

Thông báo công khai nên đủ để client xử lý lỗi mà không tiết lộ khóa hoặc chi tiết nội bộ. Cần phân biệt trong kênh chẩn đoán được bảo vệ những tình huống như profile không hỗ trợ, tham số vượt giới hạn, nguồn khóa không khả dụng và dữ liệu không vượt qua xác minh.

Không dùng việc ứng dụng trả cùng một thông báo chung làm bằng chứng rằng đã xử lý mọi kênh rò rỉ hoặc mọi vấn đề về chi phí. Tính quan sát và giới hạn tài nguyên vẫn phải được kiểm tra riêng.

## 17. Mẫu yêu cầu bảo mật có thể nghiệm thu

| ID | Yêu cầu | Bằng chứng nghiệm thu |
| --- | --- | --- |
| KDF-01 | Mỗi trường hợp dẫn xuất được phân loại theo nguồn bí mật và mục đích sử dụng | Inventory chỉ rõ password-based, root-based hoặc profile giao thức |
| KDF-02 | KDF, tham số, encoding và độ dài có profile được quản lý phiên bản | Cấu hình và implementation ánh xạ tới cùng một tập quy tắc cụ thể |
| KDF-03 | Password-based profile có salt và chi phí được chọn theo chính sách, được đo trên môi trường hỗ trợ | Báo cáo hiệu chỉnh, độ trễ và giới hạn đồng thời phù hợp |
| KDF-04 | Không dùng HKDF hoặc hash nhanh như cơ chế làm chậm đoán mật khẩu | Đối chiếu nguồn đầu vào và đường dẫn xuất thực tế |
| KDF-05 | Các mục đích sử dụng khóa được tách bằng lịch dẫn xuất rõ ràng | Kiểm tra nhãn, context, vai trò khóa và các đường sử dụng |
| KDF-06 | Context có encoding không mơ hồ và lấy giá trị quyền hạn từ nguồn có thẩm quyền | Vector tương tác và thử thay tenant/purpose từ request |
| KDF-07 | Metadata được parse có giới hạn trước thao tác tốn tài nguyên | Thử bộ nhớ, iteration và độ dài vượt ngưỡng mà không cấp phát không kiểm soát |
| KDF-08 | Profile ghi mới và khả năng đọc legacy được quản lý riêng, không có downgrade tùy ý | Thử profile yếu, profile lạ và migration dữ liệu cũ |
| KDF-09 | Đổi mật khẩu, đổi root và nâng profile có kế hoạch chuyển dữ liệu nhất quán | Kiểm tra đọc trước/sau thay đổi, lỗi giữa chừng và dữ liệu tồn đọng |
| KDF-10 | Root và khóa dẫn xuất không vượt phạm vi quyền, môi trường hoặc thời gian giữ đã định | Kiểm tra quyền gọi, cache, kênh log và dữ liệu chẩn đoán |
| KDF-11 | Yêu cầu thu hồi/xóa xét khả năng tái tạo từ root và bản sao | Phân tích cây khóa, retention và phép thử với vật liệu tổng hợp |
| KDF-12 | Độ đúng được đối chiếu bằng vector phù hợp, không chỉ round-trip nội bộ | Kết quả khớp vector độc lập và giao tiếp giữa các implementation cần hỗ trợ |

Các yêu cầu là ví dụ của dự án. Tập profile, nguồn entropy, ngưỡng tài nguyên và owner phải được điền bằng quyết định cụ thể trước khi dùng làm gate chính thức.

## 18. Kịch bản chấp nhận minh họa

### 18.1. Tái tạo kết quả đúng profile

```text
Given:
  Có vector kiểm thử tổng hợp với đầu vào và tham số đã xác định.
  Implementation sử dụng profile tương ứng.

When:
  Dẫn xuất theo encoding và đơn vị đã công bố.

Then:
  Đầu ra khớp giá trị kỳ vọng của vector.
  Không chỉ kiểm tra bằng chính implementation tạo dữ liệu ban đầu.
  Không ghi bí mật thật để làm bằng chứng.
```

### 18.2. Phân tách mục đích

```text
Given:
  Cùng một root kiểm thử được phép dùng cho hai mục đích theo lịch đã duyệt.
  Hai purpose context được mã hóa theo profile.

When:
  Dẫn xuất và sử dụng khóa theo từng mục đích.

Then:
  Mỗi thao tác dùng đúng nhánh và loại khóa đã quy định.
  Không tái sử dụng cùng output trực tiếp cho vai trò khác.
  Có kiểm tra cấu trúc context, không chỉ quan sát hai chuỗi đầu ra khác nhau.
```

### 18.3. Tham số metadata gây tải

```text
Given:
  Một bản dữ liệu kiểm thử có metadata vượt giới hạn policy.

When:
  Hệ thống thử mở bản đó.

Then:
  Request bị từ chối có kiểm soát trước tác vụ KDF vượt ngân sách.
  Không tự giảm tham số rồi tiếp tục như một lần thành công.
  Response và log không chứa password, root hoặc output key.
```

### 18.4. Đổi mật khẩu

```text
Given:
  Kho kiểm thử đang được bảo vệ theo profile hiện hành.
  Người dùng được phép thực hiện luồng đổi mật khẩu.

When:
  Chuyển bảo vệ sang mật khẩu mới theo thiết kế.

Then:
  Dữ liệu vẫn khôi phục đúng bằng ngữ cảnh mới sau khi thay đổi hoàn tất.
  Có hành vi nhất quán nếu lỗi xảy ra giữa chừng.
  Không chỉ thay salt/profile metadata mà bỏ qua vật liệu bảo vệ dữ liệu.
```

### 18.5. Root bị thay đổi sau sự cố

```text
Given:
  Root kiểm thử cũ được xem là đã lộ trong mô hình diễn tập.
  Có kế hoạch thay nguồn bí mật và chuyển dữ liệu.

When:
  Thực hiện quy trình chuyển đổi trong môi trường được phép.

Then:
  Không coi một label mới dưới root cũ là đã xử lý xong sự cố.
  Báo cáo phân biệt dữ liệu mới, dữ liệu cũ và những bản sao còn liên quan.
  Mục tiêu thu hồi/khôi phục được đánh giá theo đúng phạm vi.
```

## 19. Ma trận kiểm chứng nên chuẩn bị

| Nhóm kiểm chứng | Điều cần xác nhận |
| --- | --- |
| Vector chuẩn hoặc vector độc lập | Thuật toán, tham số và encoding được triển khai đúng |
| Bit so với byte | Không tạo khóa sai kích thước vì nhầm đơn vị |
| Mật khẩu Unicode, khoảng trắng và ký tự đặc biệt | Không trim, cắt hoặc đổi biểu diễn ngoài hợp đồng |
| Salt mới và salt đã lưu | Cấp phát, lưu và tái tạo đúng theo profile |
| Purpose, tenant, algorithm và version | Context tách đúng miền và không bị request tự quyết định quyền |
| Metadata hỏng hoặc profile không biết | Từ chối có giới hạn, không fallback hash/khóa cố định |
| Tham số rất lớn hoặc quá yếu | Trần tài nguyên và policy cho ghi/đọc được thực thi |
| Nhiều request đồng thời | CPU, bộ nhớ và hàng đợi giữ trong ngân sách đã duyệt |
| Đổi password/root/profile | Dữ liệu và metadata chuyển nhất quán, có xử lý lỗi từng phần |
| Backup và môi trường khôi phục | Giữ đủ profile, tham số và bí mật được phép để mở dữ liệu |
| Cache và log | Không lộ hoặc giữ vật liệu vượt phạm vi đã công bố |
| Thu hồi và xóa | Không bỏ sót khả năng tái tạo từ nguồn bí mật còn tồn tại |

Một phép thử encrypt–decrypt bằng cùng một hàm KDF có thể thành công ngay cả khi cả hai phía cùng mắc một lỗi encoding. Vì vậy, round-trip là một bằng chứng hữu ích nhưng chưa thay được vector và kiểm tra tương tác độc lập.

Việc hai context tạo hai output khác nhau cũng chưa phải một chứng minh đầy đủ về tách khóa. Cần kiểm tra thiết kế, thuật toán được chọn, nguồn bí mật và cách implementation dùng các đầu ra.

## 20. Duy trì yêu cầu theo vòng đời mật mã

Khi thêm một mục đích sử dụng khóa, nhóm cần mở rộng lịch dẫn xuất theo quy tắc có phiên bản thay vì tái sử dụng một output đang có. Khi thay thư viện hoặc provider, cần giữ tương thích với những bản dữ liệu thuộc thời gian lưu giữ.

Khi đổi chính sách mật khẩu hoặc hiệu chỉnh chi phí, cần phân biệt cấu hình ghi mới với dữ liệu đã tồn tại. Khi lên kế hoạch thu hồi hoặc xóa, cần kiểm tra bí mật nào vẫn có khả năng tái tạo khóa chứ không chỉ nhìn các key object đã được lưu.

Thiết kế key derivation đạt mục tiêu khi nguồn bí mật phù hợp với cơ chế, các mục đích được phân tách rõ, tham số được kiểm soát và khả năng phục hồi được mô tả trung thực. KDF tạo vật liệu khóa theo giả định đã chọn; entropy, quyền sử dụng, quản lý root và vòng đời dữ liệu vẫn phải được bảo đảm bởi toàn bộ thiết kế.
