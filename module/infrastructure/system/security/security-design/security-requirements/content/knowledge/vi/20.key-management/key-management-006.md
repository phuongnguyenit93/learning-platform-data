# Key versioning

## 1. Mục tiêu: biết dữ liệu được bảo vệ bằng khóa nào

Một hệ thống có thể tạo khóa mới thành công nhưng vẫn gặp sự cố vì không biết ciphertext cũ thuộc khóa nào, một alias đã trỏ sang vật liệu khác hoặc các node dùng cache không đồng bộ. Xoay khóa mà không có mô hình phiên bản rõ ràng dễ dẫn đến mất khả năng giải mã, xác minh sai hoặc tiếp tục dùng khóa đã ngừng cho dữ liệu mới.

**Key versioning** là cách định danh và quản lý các thế hệ khóa theo vòng đời sử dụng. Nó giúp hệ thống xác định khóa dùng cho thao tác mới, tìm lại đúng vật liệu cho dữ liệu lịch sử và áp dụng chính sách theo từng thế hệ.

Một yêu cầu chưa đủ rõ:

> Khóa phải có version và được rotate định kỳ.

Yêu cầu có thể kiểm chứng hơn:

> Mỗi kết quả mật mã phải có khả năng liên kết chắc chắn với vật liệu khóa thực sự đã dùng, bằng metadata bất biến hoặc định dạng ciphertext do dịch vụ mật mã quản lý. Khi chuyển sang thế hệ mới, dữ liệu mới phải dùng phiên bản theo policy; dữ liệu cũ vẫn được đọc hoặc xác minh bằng phiên bản tương ứng nếu còn được phép.

Versioning là một phần của quản lý vòng đời khóa, không thay việc tạo khóa an toàn, phân quyền, quản lý nonce, bảo vệ key material và phục hồi. Bối cảnh các trách nhiệm này được trình bày trong [OWASP Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html).

## 2. Phân biệt key logic, vật liệu, version và alias

### 2.1. Các khái niệm không được dùng thay nhau

| Khái niệm | Ý nghĩa | Ví dụ khái niệm |
| --- | --- | --- |
| Logical key | Định danh một mục đích hoặc tài nguyên khóa được quản lý | `report-note-key` |
| Key material | Bí mật hoặc cặp khóa thực hiện phép mật mã | Các byte khóa do KMS/HSM quản lý |
| Key version | Một thế hệ được định danh trong mô hình của nền tảng | Version 17 của một logical key |
| Alias hoặc current pointer | Tham chiếu có thể chuyển để chọn khóa/phiên bản hiện hành | `report-note-current` |
| Crypto profile | Thuật toán, mode, tham số và cách sử dụng | `report-storage-aead-v2` |
| Envelope version | Phiên bản định dạng dữ liệu bao gói | `envelopeVersion: 1` |
| Record version | Phiên bản nghiệp vụ phục vụ concurrency | Revision 42 của báo cáo |

Một alias mới trỏ tới cùng vật liệu không tự tạo một key mới. Đổi profile hoặc định dạng envelope cũng không đồng nghĩa đã đổi key material. Các chiều phiên bản phải được lưu và kiểm soát theo đúng vai trò.

### 2.2. Alias dùng để chọn hiện tại, không đủ để mô tả quá khứ

Giả sử:

```text
Trước chuyển đổi:
  report-note-current -> key version 17

Sau chuyển đổi:
  report-note-current -> key version 18
```

Nếu bản ghi cũ chỉ lưu chuỗi `report-note-current` rồi khi đọc luôn tìm alias hiện tại, hệ thống có thể chọn version 18 để giải mã dữ liệu do version 17 tạo. Một alias có ích cho thao tác mới nhưng không phải bằng chứng bất biến về thao tác đã xảy ra.

Thiết kế cần lưu identity đủ để đọc lại đúng, hoặc giữ nguyên ciphertext blob có metadata tương ứng được nhà cung cấp quản lý. Không nhất thiết mọi provider đều yêu cầu ứng dụng tự lưu một số version rời; điều kiện bắt buộc là liên kết với đúng vật liệu không bị mất.

### 2.3. Một nhãn version không được âm thầm đổi ý nghĩa

Trong mô hình ứng dụng, nếu `key-version-17` đã đại diện cho một thế hệ, không được gán lại tên đó cho vật liệu hoàn toàn khác để “đỡ sửa dữ liệu”. Việc tái dùng nhãn có thể làm ciphertext hoặc chữ ký lịch sử được xử lý sai.

ID cần có namespace phù hợp: môi trường, provider hoặc miền quản lý, logical key và thế hệ. Một chuỗi `v1` không đủ nếu nhiều tenant, nhiều issuer hoặc nhiều môi trường đều dùng nó với ý nghĩa khác nhau.

## 3. Không áp một mô hình version cho mọi KMS

### 3.1. Version công khai và rotation vật liệu trong tài nguyên ổn định

Các dịch vụ quản lý khóa có abstraction khác nhau:

| Mô hình | Cách ứng dụng cần suy nghĩ |
| --- | --- |
| Key có version resource rõ ràng | Có thể tham chiếu thế hệ cụ thể theo API và định dạng provider |
| Logical key ổn định, vật liệu được rotate bên trong | Không được tự suy key ID ổn định là một version vật liệu |
| Alias trỏ tới một key resource khác | Phải giữ identity của kết quả đã dùng, không chỉ alias hiện tại |
| Key cục bộ do ứng dụng quản lý | Ứng dụng phải tự duy trì registry, lưu trữ và vòng đời đúng policy |

Google Cloud KMS phân biệt key và key version, đồng thời có primary version cho symmetric encryption. Xem [Cloud KMS resources](https://docs.cloud.google.com/kms/docs/resource-hierarchy).

Với rotation vật liệu của một AWS KMS key phù hợp, tài nguyên key và key ID có thể giữ nguyên; AWS KMS chọn vật liệu thích hợp khi giải mã ciphertext tương ứng. Ứng dụng không được giả định cơ chế này giống một API cho phép tự chọn mọi version vật liệu. Xem [Rotate AWS KMS keys](https://docs.aws.amazon.com/kms/latest/developerguide/rotate-keys.html).

Azure Key Vault cũng có khái niệm version và hướng dẫn lưu versioned key URI với dữ liệu để phục vụ decrypt/unwrap trong thiết kế tương ứng. Xem [Configure cryptographic key auto-rotation in Azure Key Vault](https://learn.microsoft.com/en-us/azure/key-vault/keys/how-to-configure-key-rotation).

Đây là các ví dụ về khác biệt mô hình, không phải hướng dẫn dùng chung một SDK hoặc định dạng cho mọi hệ thống. Khi triển khai phải đối chiếu chính xác key type, thao tác, API và phiên bản dịch vụ đang sử dụng.

### 3.2. Yêu cầu nên nêu tính chất trước, ánh xạ công nghệ sau

Thay vì yêu cầu cứng “mọi ciphertext phải có cột integer keyVersion”, có thể viết:

> Kết quả mã hóa phải mang đủ thông tin để chọn đúng vật liệu giải mã trong phạm vi key được phép, kể cả sau rotation. Thông tin này được lưu nguyên vẹn cùng ciphertext; nếu provider tự quản lý trong blob, ứng dụng không được làm mất hoặc sửa phần metadata đó.

Sau đó, thiết kế chi tiết xác định thuộc tính API, trường dữ liệu và bằng chứng phù hợp nền tảng. Cách này tránh một cột version có vẻ đầy đủ nhưng không khớp với vật liệu thực sự được provider dùng.

## 4. Trạng thái theo version phải gắn với loại thao tác

### 4.1. Primary khác với enabled

Một key version có thể còn khả dụng để đọc dữ liệu cũ nhưng không còn được chọn cho ghi mới. Chuyển primary không nhất thiết vô hiệu hóa version cũ.

Một ma trận ý định sử dụng minh họa:

| Trạng thái ứng dụng | Mã hóa hoặc ký mới | Giải mã hoặc xác minh lịch sử |
| --- | --- | --- |
| Prepared | Chưa cho luồng thường lệ | Theo quy trình chuẩn bị/kiểm chứng |
| Current for new use | Cho phép đúng purpose | Cho phép đúng purpose |
| Historical use only | Không dùng mới | Cho phép trong phạm vi và thời hạn |
| Suspended | Không | Theo chính sách tạm dừng và loại key |
| Compromised | Không | Theo quyết định ứng phó, không mặc nhiên tin cậy |
| Destroyed | Không | Không còn dùng key material đã hủy |

Đây là trạng thái policy của ứng dụng, không phải danh sách enum chung của mọi nhà cung cấp. Một trạng thái như `decrypt-only` có thể cần được thực thi bằng kiến trúc, quyền hoặc wrapper chứ không có sẵn dưới cùng tên trong KMS.

### 4.2. Quyền theo version phụ thuộc nền tảng

Không giả định mọi KMS cho phép cấp IAM độc lập cho từng version. Chẳng hạn, tài liệu Cloud KMS nêu quyền áp dụng ở key thay vì được điều khiển riêng cho từng key version. Khi cần hạn chế tạo mới bằng thế hệ cũ, phải chọn điểm thực thi phù hợp với khả năng nền tảng.

Nếu một quyền dùng key còn cho phép nhiều version đang enabled, đổi primary không tự chứng minh không có đường nào chọn version cũ. Thiết kế cần kiểm soát API chọn version, service được gọi hoặc cách tách logical key khi cần mức phân quyền khác.

Một yêu cầu không thể được đánh dấu đạt chỉ bằng một nhãn trong registry nếu principal vẫn có thể dùng trực tiếp một đường khác để mã hóa với thế hệ đã ngừng dùng mới.

## 5. Metadata cho dữ liệu được mã hóa trực tiếp

### 5.1. Lưu identity cùng một kết quả mật mã

Với mã hóa trực tiếp do ứng dụng điều phối, một envelope khái niệm có thể là:

```json
{
  "envelopeVersion": 1,
  "profileId": "report-storage-aead-v2",
  "keyVersionRef": "prod/report-note-key/versions/18",
  "contextEncodingVersion": 1,
  "nonceBase64": "<nonce-theo-profile>",
  "ciphertextAndTagBase64": "<ket-qua-ma-hoa>"
}
```

Đây là ví dụ dữ liệu với placeholder, không phải ciphertext thật hoặc resource ID chuẩn của một nhà cung cấp. Các trường, định dạng encoding và giới hạn phải được đặc tả trong schema thực tế.

Profile quy định thuật toán và tham số; key reference xác định key trong miền được phép. Không để `profileId` trở thành tên transformation tùy ý hoặc `keyVersionRef` trở thành URL mà server tự động truy cập.

### 5.2. Metadata phải được xác thực ở lớp thích hợp

Thay một key reference hoặc context không được khiến ứng dụng chấp nhận ciphertext cho tenant khác. Cần ràng buộc danh tính dữ liệu, purpose, profile và các metadata quan trọng bằng cơ chế xác thực của construction hoặc provider.

Với AEAD, AAD có thể ràng buộc một ngữ cảnh được mã hóa thành byte một cách xác định. Khi đọc, ngữ cảnh mong đợi phải đến từ tài nguyên đã được kiểm tra quyền, không chỉ từ envelope mà attacker có thể thay.

Không giải mã thành công bằng một key nào đó là đủ. Hệ thống còn phải biết đó là key được phép cho đúng tenant, purpose và dataset.

### 5.3. Ghi nguyên tử body và metadata

Ciphertext, nonce, key identity và profile phải được lưu như một đơn vị nhất quán. Không ghi ciphertext mới rồi để `keyVersionRef` cũ vì một cập nhật tiếp theo thất bại.

Nếu lưu blob ở object storage và metadata ở database, cần quy trình công bố, transaction hoặc cơ chế phối hợp phù hợp. Chỉ các object hoàn tất với metadata tương ứng mới được coi là dữ liệu có thể đọc. Không mặc định hai lệnh ghi độc lập tạo ra tính nguyên tử.

## 6. Tránh race khi chọn version trong lúc rotation

### 6.1. Hai lần nhìn alias có thể thấy hai thế hệ

Một luồng dễ sai:

```text
1. Đọc alias current, thấy version 17.
2. Alias được chuyển sang version 18.
3. Gọi mã hóa qua alias current, thao tác thực tế dùng version 18.
4. Lưu ciphertext kèm metadata version 17 đã đọc ở bước 1.
```

Kết quả là một bản ghi gắn nhãn không đúng key material. Lỗi này có thể chỉ xuất hiện đúng lúc rotation, nên một ca mã hóa/giải mã bình thường trước đó không phát hiện được.

Có hai cách khái niệm để tránh:

- Resolve một version cụ thể được phép, giữ tham chiếu đó và thực hiện thao tác bằng đúng version đã chọn nếu API hỗ trợ.
- Gọi API có khả năng chọn current và lấy key identity thực sự đã dùng từ chính kết quả hoặc giữ nguyên blob tự mô tả mà provider bảo đảm.

Không suy version của ciphertext bằng một lần tra alias riêng trước hoặc sau thao tác.

### 6.2. Hợp đồng Java nên trả kết quả cùng identity

Một trích đoạn minh họa ở lớp dịch vụ:

```java
// Các type và phương thức là hợp đồng ứng dụng minh họa.
EncryptionResult result = cryptography.encryptCurrent(
        authorizedContext, plaintext);

encryptedRecords.storeAtomically(
        recordId,
        expectedRecordVersion,
        result.envelopeBytes(),
        result.actualKeyIdentity(),
        result.profileId());
```

`encryptCurrent` phải trả một kết quả có identity tương ứng với chính phép mã hóa đó; tên phương thức không tự thực hiện bảo đảm này. `storeAtomically` phải có semantics lưu và concurrency rõ, không phải một wrapper gọi nhiều lệnh ghi rời.

Nếu provider không lộ version vật liệu ở mức ứng dụng, `actualKeyIdentity` có thể là identity đúng abstraction của provider, còn thông tin chọn vật liệu lịch sử nằm trong envelope/blob được lưu nguyên vẹn. Không tự tạo một số version giả chỉ để khớp interface.

Không cần export raw key để ghi identity. Version reference và key material là hai dữ liệu khác nhau; lấy key bytes ra khỏi HSM chỉ để xác định “đang dùng version nào” có thể phá ranh giới bảo vệ.

### 6.3. Rotation không reset điều kiện nonce của cùng vật liệu

GCM cần IV/nonce không lặp khi mã hóa với cùng key. Đổi alias, đổi nhãn version hoặc reimport cùng vật liệu không làm điều kiện đó bắt đầu lại từ đầu. Yêu cầu này được nêu trong [Java Cipher API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Cipher.html).

Nếu khôi phục lại version cũ cho ghi mới, phải xét cả lịch sử nonce và usage budget của vật liệu đó. Không khởi tạo counter lại từ zero chỉ vì version vừa được promote lần nữa.

Các bản sao key cùng vật liệu ở nhiều region hoặc môi trường cũng cần được đánh giá theo construction. Một nhãn khác không tự làm chúng thành các key độc lập về mặt mật mã.

## 7. Chuyển version cho ghi mới trong hệ thống nhiều node

### 7.1. Tách cutover chọn key và cutover commit

Giả sử T0 là lúc chuyển current từ 17 sang 18. Một request có thể đã chọn version 17 trước T0 nhưng hoàn tất ghi sau T0. Hợp đồng phải xác định trường hợp đó có được phép trong giai đoạn drain hay không.

Hai yêu cầu có ý nghĩa khác nhau:

```text
A. Mọi lựa chọn key mới sau T0 dùng version 18.
B. Mọi bản ghi commit sau T0 phải được mã hóa bằng version 18.
```

Yêu cầu B chặt hơn và có thể cần generation/epoch, fencing hoặc kiểm tra nguyên tử tại điểm công bố dữ liệu. Chỉ đổi một alias không tự bảo đảm B trên mọi writer đang chạy.

Nếu chấp nhận cửa sổ chuyển đổi, phải công bố thời hạn, phạm vi request đang chạy và cách phát hiện writer chưa cập nhật. Không mô tả một TTL cache như bảo đảm “ngay lập tức” khi request cũ vẫn có thể tiếp tục.

### 7.2. Cache current và cache theo version có vai trò khác nhau

| Loại cache | Rủi ro cần kiểm soát |
| --- | --- |
| Current pointer | Node tiếp tục chọn thế hệ cũ sau cutover |
| Metadata theo version | Dùng trạng thái quyền hoặc policy đã lỗi thời |
| Key material trong bộ nhớ | Disable tại KMS chưa chắc ngăn local operation ngay |
| Public key xác minh | Chưa biết key mới hoặc tiếp tục tin key bị thu hồi |
| Negative cache cho ID không biết | Key mới hợp lệ bị coi là không tồn tại quá lâu |

Khóa cache phải có namespace phù hợp, không chỉ `v18`. Quy tắc refresh, TTL, invalidation và hành vi khi nguồn không sẵn sàng cần gắn với yêu cầu thu hồi và sẵn sàng.

Nếu cache raw key được phép, thời gian giữ và cách sử dụng phải được đánh giá rõ. Không tuyên bố disable một version ở dịch vụ quản lý sẽ lập tức xóa mọi bản sao trong process đã lấy key trước đó.

### 7.3. Theo dõi writer cũ bằng bằng chứng

Có thể ghi nhận số thao tác mới theo logical key, version identity phù hợp provider, purpose, release và node group. Việc không có lỗi giải mã không chứng minh mọi node đã chuyển sang ghi mới bằng version 18.

Một cảnh báo có ích là phát hiện thao tác tạo mới bằng thế hệ không còn được phép sau mốc/cửa sổ đã chốt. Phải phân biệt thao tác đọc lịch sử hợp lệ với writer còn dùng thế hệ cũ.

## 8. Đọc dữ liệu lịch sử: chọn đúng version, không chọn latest

Luồng đọc cần:

```text
Xác minh quyền với tài nguyên
    -> parse envelope trong giới hạn
    -> kiểm tra profile và key namespace được phép
    -> xác định version hoặc để provider xử lý blob theo hợp đồng
    -> áp dụng trạng thái/purpose của key
    -> giải mã và xác thực
    -> chỉ phát plaintext sau khi thành công
```

Không dùng current/latest thay metadata của bản ghi. Không thử lần lượt mọi key trong hệ thống khi một version không tồn tại hoặc tag không khớp. Cách thử đó che lỗi metadata, tăng chi phí và có thể mở một đường giải mã ngoài scope.

Key version không phải credential của người gọi. Một người biết version ID vẫn phải qua quyền đọc dữ liệu và quyền sử dụng key theo kiến trúc. Service có quyền KMS cũng không được trở thành một “confused deputy” nhận key reference bất kỳ rồi giải mã thay mọi client.

Các lỗi key không biết, key bị disable, quyền thiếu, metadata hỏng và ciphertext sai phải được xử lý theo hợp đồng. Không đổi sang plaintext hoặc một key dự phòng hard-code để giữ response thành công.

## 9. Envelope encryption có nhiều lớp version

### 9.1. Phân biệt DEK và KEK

Trong envelope encryption, DEK bảo vệ payload; KEK hoặc key quản lý dùng để wrap DEK. Một envelope có thể có các thông tin khái niệm:

```text
payloadProfileId
payloadNonce
payloadCiphertextAndTag
wrappedDataKey
wrappingKeyIdentity
wrappingProfileId
envelopeVersion
```

Version của wrapping key không nhất thiết là version của data key. Một DEK có thể được bọc lại bằng KEK mới mà payload không đổi.

### 9.2. Rotation, rewrap và re-encrypt không cùng một việc

| Thao tác | Thay đổi chính | Không tự chứng minh |
| --- | --- | --- |
| Tạo/promote key version | Lựa chọn vật liệu cho thao tác mới | Dữ liệu cũ đã chuyển sang thế hệ mới |
| Rewrap DEK | Lớp bọc key dữ liệu | Payload đã đổi DEK, mode hoặc profile |
| Re-encrypt payload | Bảo vệ nội dung dữ liệu | Mọi backup và quyền truy cập cũ đã được xử lý |

Tài liệu [Google Cloud KMS key rotation](https://docs.cloud.google.com/kms/docs/key-rotation) và [AWS KMS rotation](https://docs.aws.amazon.com/kms/latest/developerguide/rotate-keys.html) đều lưu ý việc rotation key không tự mã hóa lại dữ liệu đã được bảo vệ. Tính chất ứng dụng cần được xác định theo lớp mà nó muốn chuyển đổi.

Nếu DEK đã bị lộ, chỉ đổi KEK và rewrap cùng DEK không khắc phục việc attacker có DEK đó. Nếu mục tiêu chỉ là đổi lớp bọc quản lý theo policy, rewrap có thể phù hợp mà không cần giải mã toàn payload.

### 9.3. Metadata thay đổi cần đúng lớp xác thực

Nếu muốn rewrap mà không xử lý lại payload, thiết kế không nên vô tình buộc một tham chiếu KEK có thể đổi vào AAD bất biến của payload rồi vẫn kỳ vọng chỉ sửa header được.

Profile phải nêu metadata nào được ràng buộc tại lớp payload, metadata nào được bảo vệ bởi cơ chế wrapping và cách ghi chúng nhất quán. Không sửa một trường vốn được xác thực rồi bỏ kiểm tra tag để “cho tương thích”.

Khi rewrap, cập nhật wrapped DEK và wrapping key identity cùng một đơn vị dữ liệu. Nếu record thay đổi đồng thời, cần concurrency control để không gắn wrapped DEK của bản này vào payload của bản khác.

## 10. Key versioning cho chữ ký và token

### 10.1. Public key mới phải tới nơi xác minh trước khi dùng rộng rãi

Một quy trình chuyển key ký minh họa:

```text
Tạo key ký mới và metadata
    -> công bố public key mới qua kênh tin cậy
    -> kiểm chứng các verifier nhận được key theo policy cache
    -> bắt đầu ký mới bằng thế hệ mới
    -> giữ public key cũ cho dữ liệu còn được chấp nhận
    -> ngừng tin cậy hoặc lưu lịch sử theo điều kiện đã chốt
```

Không cần giữ private key cũ chỉ để xác minh chữ ký nếu mô hình chỉ cần public key. Quyền tạo chữ ký mới và khả năng xác minh lịch sử có vòng đời khác nhau.

Thời gian giữ public key hoặc chấp nhận key cũ phụ thuộc thời hạn đối tượng đã ký, clock skew được phép, cache và chính sách thu hồi. Một tài liệu lưu lâu không có cùng vòng đời với một access token ngắn hạn.

### 10.2. `kid` là bộ chọn, không phải bằng chứng tin cậy

Trong JWK/JWS, `kid` hỗ trợ khớp một key, gồm trường hợp rollover. [RFC 7517, mục 4.5](https://www.rfc-editor.org/rfc/rfc7517.html#section-4.5) mô tả vai trò này. Ứng dụng nên có namespace và quy tắc phân biệt key phù hợp tập key của mình, không tái dùng một `kid` cho vật liệu mới theo cách làm mơ hồ dữ liệu còn hiệu lực.

Key lookup phải nằm trong issuer hoặc trust domain đã được cấu hình. Không lấy `kid` làm đường dẫn tệp, câu truy vấn được nối chuỗi hoặc URL KMS tùy ý. Các rủi ro lookup và việc tin URL như `jku`/`x5u` được nêu trong [RFC 8725, mục 3.10](https://www.rfc-editor.org/rfc/rfc8725.html#section-3.10).

Không biết `kid` không được dẫn tới bỏ kiểm tra chữ ký. Có thể refresh tập key từ nguồn tin cậy với giới hạn và cache phù hợp, nhưng không tạo một lần fetch không giới hạn cho mỗi giá trị attacker gửi.

### 10.3. Rotation thường lệ khác xử lý key bị lộ

Trong rotation thường lệ, hệ thống có thể giữ một cửa sổ overlap để dữ liệu hợp lệ cũ tiếp tục được xác minh. Khi key bị lộ, chính sách có thể cần ngừng tin cậy sớm hơn và làm một số token hoặc chữ ký không còn được chấp nhận.

Không giữ một key bị coi là compromised chỉ vì chưa hết TTL cache. Đồng thời, yêu cầu thu hồi phải khả thi với kiến trúc: cache cục bộ, verifier offline và key material đã phân phối ảnh hưởng thời gian phản ánh quyết định.

Versioning giúp nhận diện phạm vi, nhưng không khôi phục bí mật đã mất hoặc tự phân biệt mọi chữ ký giả được tạo bằng private key bị lộ. Cần quy trình ứng phó phù hợp với tài sản.

## 11. Migration, backup và phục hồi theo version

### 11.1. Biết tập dữ liệu còn phụ thuộc mỗi thế hệ

Inventory cần hỗ trợ xác định ciphertext, wrapped DEK, chữ ký hoặc backup còn phụ thuộc một key identity. Có thể dùng metadata và sổ theo dõi được thiết kế, không cần quét plaintext.

Đừng chỉ tính dữ liệu đang online. Bản backup, snapshot, archive, cache lâu hạn hoặc artifact xuất cho đối tác có thể còn cần thế hệ cũ. Số request decrypt bằng zero trong một tuần không chứng minh key không còn cần.

### 11.2. Migration phải nguyên tử và có thể chạy lại

Luồng chuyển một record có thể đọc bằng version cũ, tạo envelope mới bằng version hiện hành và cập nhật nếu record version chưa đổi. Nếu lỗi giữa chừng, không công bố metadata/body lệch nhau.

Tiến độ cần phân biệt đã chuyển, chưa chuyển, lỗi và record đã bị sửa đồng thời. Không ghi log “migrated” trước khi commit hoàn tất. Một lần chạy lại không được gây mất dữ liệu hoặc đẩy record trở về version cũ.

Nếu công cụ migration tạo nhiều phép mã hóa, vẫn phải tôn trọng usage budget và nonce policy. Rotation của KEK không tự reset ngân sách của DEK còn được dùng lại.

### 11.3. Restore không được tùy ý quay current pointer về quá khứ

Một backup database có thể chứa trạng thái registry cũ trong khi KMS và writer đã chuyển sang thế hệ mới. Khôi phục rồi ghi đè current pointer bằng bản cũ có thể làm hệ thống tạo mới bằng key không còn được phép.

Thiết kế cần xác định nguồn chuẩn của control plane, cách đối chiếu version và điều kiện cho phép writer hoạt động sau restore. Có thể cần giai đoạn chỉ đọc hoặc kiểm tra capability trước khi mở ghi, tùy rủi ro.

Nếu sao lưu hoặc chuyển vật liệu sang môi trường khác được phép, cần giữ mapping và provenance đúng. Import lại cùng vật liệu không được gọi là rotation sang key độc lập rồi reset nonce/counter. Nếu vật liệu thực sự khác, không gán lại identity lịch sử để giả vờ dữ liệu cũ vẫn khớp.

### 11.4. Disable và destroy có hậu quả khác nhau

Disable có thể là biện pháp tạm thời theo khả năng provider; destroy key material có thể làm dữ liệu không còn phục hồi được. Điều kiện ngừng phải dựa trên dataset, backup, thời hạn và yêu cầu ứng phó, không chỉ tuổi key.

Quyết định hủy cần được quản lý như thay đổi có tác động dữ liệu. Versioning phải giúp biết hậu quả trước khi thực hiện, thay vì chỉ tạo một danh sách key đã cũ.

## 12. Bộ yêu cầu bảo mật có thể triển khai

| Mã | Yêu cầu minh họa | Bằng chứng nghiệm thu dự kiến |
| --- | --- | --- |
| KEY-VER-01 | Mỗi thế hệ phải có identity không mơ hồ trong trust domain | Registry, namespace, provider mapping và dữ liệu mẫu |
| KEY-VER-02 | Kết quả mật mã phải liên kết với key thực sự đã dùng | Ca rotation xen giữa resolve và thao tác |
| KEY-VER-03 | Ghi mới phải chọn current theo semantics cutover đã chốt | Writer nhiều node, cache và request đang chạy |
| KEY-VER-04 | Đọc lịch sử không được chọn latest thay metadata đúng | Ciphertext cũ sau nhiều lần rotation |
| KEY-VER-05 | Quyền tạo mới và đọc lịch sử phải được thực thi đúng khả năng nền tảng | Thử dùng version cũ trực tiếp và qua adapter |
| KEY-VER-06 | Metadata, ciphertext và wrapped key phải được ghi nhất quán | Lỗi giữa chừng, concurrency và migration chạy lại |
| KEY-VER-07 | Key reference không biết hoặc ngoài scope phải bị từ chối | Tenant khác, purpose khác, alias tùy ý và ID không tồn tại |
| KEY-VER-08 | Cache không được làm quyết định thu hồi vượt thời hạn được phép | Disable/compromise trong khi cache còn dữ liệu |
| KEY-VER-09 | Rotation, rewrap và re-encrypt phải có mục tiêu riêng | Đối chiếu payload profile, DEK và wrapping identity |
| KEY-VER-10 | Restore phải giữ khả năng đọc và không mở ghi bằng thế hệ trái policy | Diễn tập database/KMS/control-plane recovery |
| KEY-VER-11 | Ngừng/hủy version phải có đối chiếu dữ liệu còn phụ thuộc | Online, backup, artifact và phê duyệt retirement |
| KEY-VER-12 | Audit phải ghi đúng identity và thao tác mà không lộ key material | So sự kiện tạo, promote, sử dụng và retirement |

Một yêu cầu hoàn chỉnh có thể ghi:

> Dịch vụ phải lưu đủ metadata hoặc blob của provider để xác định đúng key material cho từng kết quả. Chuyển current không thay nghĩa identity lịch sử. Tạo mới, đọc lịch sử và thu hồi được kiểm soát theo purpose; các writer, cache và công cụ restore phải tuân theo cùng hợp đồng cutover và vòng đời.

## 13. Kế hoạch nghiệm thu theo các tình huống chuyển version

Các ca sau là kế hoạch kiểm chứng cho một nền tảng giả định, không phải báo cáo đã chạy trên dự án cụ thể.

| Ca | Chuẩn bị | Kết quả cần quan sát |
| --- | --- | --- |
| Trước rotation | Tạo dữ liệu bằng thế hệ 17 | Identity lưu khớp phép mã hóa và đọc lại đúng |
| Sau rotation | Current chuyển sang 18 | Ghi mới theo policy dùng 18; dữ liệu 17 vẫn đọc đúng nếu được phép |
| Race alias | Chuyển current giữa resolve và thao tác | Không gắn nhãn 17 cho kết quả thực tế dùng 18 |
| Writer đang chạy | Request bắt đầu trước cutover, commit sau | Hành vi đúng quy tắc drain hoặc commit fencing đã chốt |
| Node cache cũ | Một node giữ current cũ | Không vượt cửa sổ cho phép; có phát hiện writer lệch |
| Đọc bằng latest | Cố thay metadata cũ bằng current | Không dùng đường sai như một fallback thành công |
| ID không biết | Envelope hoặc token chứa key ID lạ | Từ chối/refresh có giới hạn theo policy, không thử mọi key |
| Sai tenant/purpose | Key tồn tại nhưng ngoài scope | Không mở quyền dùng key từ metadata |
| Metadata bị sửa | Đổi profile, context hoặc key reference | Không chấp nhận dữ liệu trong ngữ cảnh sai |
| Version cũ enabled | Thử dùng trực tiếp để ghi mới | Kiểm soát đúng intent historical-only theo kiến trúc |
| Disable/compromise | Key đã được cache trước đó | Độ trễ thu hồi và đường lỗi khớp hợp đồng |
| Rewrap | Chỉ thay lớp bọc DEK | Wrapped key và metadata nhất quán; không tuyên bố payload đã đổi key |
| Lỗi migration | Ngắt trước/giữa commit hoặc cập nhật đồng thời | Không mất dữ liệu, không record nửa chuyển |
| Rollover chữ ký | Public key mới được công bố và key ký đổi | Key mới được nhận theo policy; key cũ có overlap phù hợp |
| Negative cache | `kid` mới từng bị coi là không biết | Không bị từ chối quá thời hạn đã thiết kế |
| Restore | Backup cũ, KMS/control plane hiện tại | Đọc đúng các thế hệ cần giữ, không lùi policy ghi mới |
| Key material được sao chép | Hai identity cùng vật liệu theo quy trình được phép | Không reset điều kiện nonce chỉ vì tên khác |
| Retirement | Version còn/không còn phụ thuộc backup | Quyết định ngừng dựa trên bằng chứng đầy đủ |

### 13.1. Không chỉ thử encrypt/decrypt trong một process

Một round-trip trước rotation chỉ chứng minh tình huống đơn giản. Cần các ca chuyển key, cache cũ, lỗi network, race và dữ liệu nhiều thế hệ để đánh giá yêu cầu versioning.

Nếu provider tự quản lý version trong blob, test phải giữ blob nguyên vẹn và kiểm chứng đọc sau rotation theo API của provider. Không parse cấu trúc nội bộ không được công bố để tạo một bằng chứng mong manh.

### 13.2. Kiểm tra hành vi bị cấm

Phải có ca yêu cầu ghi mới bằng thế hệ historical-only, dùng key ID ngoài trust domain và đọc với metadata bị sửa. Chỉ có ca version đúng hoạt động không chứng minh giới hạn quyền đã có hiệu lực.

Với request bị từ chối, quan sát storage và tác dụng phụ, không chỉ mã lỗi. Một response lỗi sau khi dữ liệu đã ghi bằng key không được phép vẫn là vi phạm.

### 13.3. Bằng chứng không được chứa raw key

Có thể ghi profile, provider, version reference theo chính sách, release, thời điểm và loại thao tác. Không cần dump key bytes, plaintext hoặc token thật để chứng minh lựa chọn version.

Metadata vẫn cần kiểm soát quyền vì có thể tiết lộ kiến trúc hoặc phạm vi dữ liệu. Nhãn metric nên có cardinality được quản lý; không đưa mọi key ID tùy ý từ request vào nhãn không giới hạn.

## 14. Theo dõi và quản trị thay đổi version

Các sự kiện quan trọng gồm tạo/import version, promote current, đổi quyền, suspend, đánh dấu compromised, rewrap, migrate và ngừng/hủy. Sự kiện cần liên kết actor, logical key, identity phù hợp provider, purpose, kết quả và định danh thay đổi.

Một bản ghi audit cho promote không đủ chứng minh mọi writer đã dùng key mới. Cần đối chiếu telemetry sử dụng và điều kiện cutover. Ngược lại, còn decrypt bằng version cũ có thể là hoạt động hợp lệ của dữ liệu lịch sử, không tự là lỗi rotation.

Khi thay provider hoặc mô hình key, cần cập nhật schema, mapping identity, quyền, cache và đường phục hồi. Không ép một key ID ổn định của nền tảng này mang ý nghĩa như version resource của nền tảng khác.

Nếu có ngoại lệ tiếp tục dùng thế hệ cũ để ghi mới, phải có scope, owner, thời hạn và đánh giá rủi ro. Không biến việc đổi alias tạm để khắc phục sự cố thành một quyết định dùng key cũ vô thời hạn.

## 15. Một hồ sơ yêu cầu gọn cho key versioning

```text
Tài sản: dữ liệu mã hóa, wrapped DEK, chữ ký và khả năng phục hồi.
Đe dọa: mất mapping key, alias race, dùng lại thế hệ cũ trái policy,
        thu hồi không có hiệu lực hoặc hủy key còn phụ thuộc.

Định danh:
  - Tách logical key, key material, version, alias, profile và envelope.
  - Identity lịch sử không bị gán lại âm thầm cho vật liệu khác.
  - Ciphertext/blob và metadata phản ánh đúng thao tác đã thực hiện.

Sử dụng:
  - Ghi mới theo current và semantics cutover đã chốt.
  - Đọc lịch sử theo identity đúng, không dùng latest thay thế.
  - Quyền theo purpose/tenant và khả năng KMS được thực thi rõ.
  - Cache và nonce không reset chỉ vì đổi tên hoặc promote lại.

Vòng đời:
  - Rotation không tự đồng nghĩa rewrap hoặc re-encrypt dữ liệu.
  - Migration, rollback và restore giữ metadata/body nhất quán.
  - Retirement dựa trên inventory online, backup và artifact.

Kiểm chứng:
  - Dữ liệu trước/sau rotation; alias race; nhiều node; cache cũ.
  - Key ID sai scope; trạng thái thu hồi; migration và phục hồi.
  - Bằng chứng dùng đúng key identity, không xuất key material.
```

Key versioning có giá trị khi hệ thống nhận diện đúng vật liệu đã dùng, chọn đúng thế hệ cho thao tác mới và giữ được khả năng xử lý lịch sử theo policy. Một số version trong cấu hình chưa đủ; cần hợp đồng metadata, quyền, cutover và phục hồi có thể kiểm chứng trên toàn đường xử lý.
