# Mục tiêu bảo mật của key

## 1. Vì sao phải bảo vệ khóa mật mã?

Khóa mật mã (cryptographic key) là giá trị được thuật toán mật mã sử dụng để mã hóa, giải mã, tạo hoặc kiểm tra chữ ký số, xác thực thông điệp và thực hiện nhiều thao tác bảo mật khác. Mức độ an toàn của hệ thống không chỉ phụ thuộc vào thuật toán mạnh mà còn phụ thuộc vào cách tạo, lưu giữ, sử dụng và kết thúc vòng đời của khóa.

Ví dụ, cơ sở dữ liệu chứa toàn bộ thông tin khách hàng có thể đã được mã hóa bằng AES-256-GCM. Tuy nhiên, nếu khóa giải mã được ghi ngay trong mã nguồn, người có bản sao cơ sở dữ liệu và mã nguồn vẫn có thể đọc dữ liệu. Ngược lại, nếu khóa bị mất vĩnh viễn, tổ chức có thể không bao giờ khôi phục được dữ liệu dù ciphertext vẫn còn nguyên.

Trong chương **Nền tảng key management**, câu hỏi trọng tâm của bài này là: **một khóa được xem là an toàn khi những thuộc tính nào được bảo đảm, trước những rủi ro nào và bằng những kiểm soát nào?** Các mục tiêu này là cơ sở để thiết kế quản lý khóa cho mật mã đối xứng, bất đối xứng, chữ ký số, KMS/HSM và envelope encryption.

> **Nguyên tắc nền tảng:** Bảo vệ dữ liệu bằng mật mã chỉ có ý nghĩa khi hệ thống bảo vệ được các khóa cần giữ bí mật, xác thực được các khóa cần tin cậy và kiểm soát được ai có quyền sử dụng khóa cho mục đích gì.

## 2. Mục tiêu phụ thuộc vào loại khóa

Không phải mọi khóa đều cần được giữ bí mật như nhau. Cần xác định chức năng của khóa trước khi đặt mục tiêu bảo mật.

| Loại khóa | Vai trò | Mục tiêu cần ưu tiên |
| --- | --- | --- |
| **Khóa đối xứng** (ví dụ: khóa AES) | Cùng một bí mật được dùng để mã hóa và giải mã, hoặc làm đầu vào cho MAC | Giữ bí mật; bảo đảm tính toàn vẹn; giới hạn quyền sử dụng; duy trì khả năng khôi phục khi cần |
| **Khóa riêng** (private key) | Giải mã trong một số sơ đồ bất đối xứng hoặc tạo chữ ký số | Giữ bí mật; ngăn việc ký/giải mã trái phép; bảo đảm khóa thuộc đúng chủ thể |
| **Khóa công khai** (public key) | Kiểm tra chữ ký hoặc mã hóa cho người sở hữu khóa riêng tương ứng | Bảo đảm tính xác thực, toàn vẹn và liên kết đúng danh tính; thông thường **không** cần bí mật |
| **Data Encryption Key (DEK)** | Mã hóa dữ liệu ứng dụng | Bảo vệ khóa ở dạng rõ; tách biệt khỏi dữ liệu đã mã hóa; kiểm soát phạm vi dữ liệu và quyền giải mã |
| **Key Encryption Key (KEK)** | Mã hóa hoặc bọc (wrap) các khóa khác | Hạn chế khả năng trích xuất, sử dụng và thay đổi; bảo vệ nhiều DEK phụ thuộc vào KEK |

Một lỗi thiết kế phổ biến là yêu cầu giữ bí mật khóa công khai nhưng lại không xác minh được khóa công khai đó có thật sự thuộc về đối tác hay không. Kẻ tấn công có thể thay khóa công khai của đối tác bằng khóa của mình để đánh lừa hệ thống. Vì vậy, **tính xác thực của khóa công khai** thường quan trọng hơn tính bí mật của nó.

## 3. Các mục tiêu bảo mật cốt lõi

### 3.1. Tính bí mật (confidentiality)

Khóa bí mật và khóa riêng chỉ được lộ cho thành phần thực sự cần sử dụng, trong thời gian và phạm vi tối thiểu. Cần bảo vệ khóa ở cả ba trạng thái:

- **Khi lưu trữ (at rest):** Không để khóa dạng rõ trong mã nguồn, Git, tệp cấu hình, cơ sở dữ liệu, bản sao lưu hoặc ảnh máy ảo. Có thể lưu khóa đã được wrap bằng KEK và đặt KEK trong KMS/HSM.
- **Khi truyền (in transit):** Dùng kênh được xác thực và mã hóa như TLS phù hợp; xác minh đầu nhận trước khi cấp phát hoặc truyền vật liệu khóa.
- **Khi sử dụng (in use):** Hạn chế việc đưa khóa dạng rõ ra khỏi ranh giới an toàn. Nếu ứng dụng buộc phải xử lý khóa trong bộ nhớ, cần giới hạn thời gian tồn tại, quyền truy cập tiến trình, khả năng tạo dump và ghi log. Việc xóa mảng byte sau sử dụng có ích ở một số tình huống nhưng không bảo đảm loại bỏ mọi bản sao mà runtime đã tạo.

KMS (Key Management Service) giúp quản lý khóa, chính sách truy cập và thao tác mật mã; HSM (Hardware Security Module) là thành phần phần cứng chuyên bảo vệ vật liệu khóa và thực hiện phép toán mật mã trong một ranh giới được kiểm soát. **Dùng KMS/HSM không tự động bảo vệ khỏi mọi hành vi lạm dụng:** một ứng dụng bị chiếm quyền nhưng vẫn có quyền gọi thao tác giải mã có thể tiếp tục lấy dữ liệu rõ.

### 3.2. Tính toàn vẹn (integrity)

Khóa và thông tin đi kèm phải không bị sửa, thay thế hoặc đánh tráo ngoài ý muốn. Bảo vệ vật liệu khóa là chưa đủ: hệ thống còn phải bảo vệ **định danh khóa, phiên bản, mục đích, chủ sở hữu, trạng thái và chính sách truy cập**.

Ví dụ, nếu ciphertext của khách hàng A bị gán sang hồ sơ khách hàng B mà ứng dụng không ràng buộc ngữ cảnh, dữ liệu có thể được giải mã ở sai vị trí. Mã hóa có xác thực (AEAD), chẳng hạn AES-GCM, cho phép kiểm tra ciphertext/tag và xác thực thêm dữ liệu liên quan (AAD) như mã tenant, định danh bản ghi hay mục đích sử dụng. KMS có hỗ trợ encryption context cũng có thể ràng buộc thao tác wrap/unwrap với ngữ cảnh, tùy đặc tính của dịch vụ.

Đối với khóa công khai, kiểm tra chữ ký với **một khóa bất kỳ** không đủ để xác thực người ký. Cần xác minh nguồn gốc khóa và mối liên hệ đáng tin cậy giữa khóa với danh tính (ví dụ: chuỗi chứng chỉ và quy trình cấp phát/thu hồi chứng chỉ phù hợp).

### 3.3. Tính sẵn sàng và khả năng khôi phục (availability & recoverability)

Những chủ thể hợp lệ phải có khả năng thực hiện thao tác mật mã khi công việc yêu cầu. Nếu khóa giải mã bị mất, có thể mất luôn khả năng khôi phục dữ liệu; nếu KMS ngừng hoạt động, dịch vụ phụ thuộc có thể không xử lý được yêu cầu.

Các kiểm soát thường gồm:

- Thiết kế độ sẵn sàng của KMS/HSM, kết nối mạng và chính sách theo nhu cầu khôi phục của hệ thống.
- Sao lưu hoặc cơ chế khôi phục khóa theo chính sách bảo vệ tương đương khóa chính; thử khôi phục định kỳ, gồm cả quyền hạn và quy trình vận hành.
- Quản lý phụ thuộc: biết DEK nào đang được bảo vệ bởi KEK nào, phiên bản nào còn cần thiết để đọc dữ liệu cũ.
- Đặt quy trình phê duyệt và thời gian chờ phù hợp trước khi vô hiệu hóa/xóa khóa quan trọng.

**Tính sẵn sàng không có nghĩa là cấp quyền rộng hơn.** Khi KMS lỗi, hệ thống không được âm thầm bỏ kiểm tra quyền hoặc lưu khóa bí mật lâu dài ở nơi kém an toàn. Một số hệ thống có thể dùng cache khóa ngắn hạn, nhưng phải đánh giá rõ giới hạn thời gian, phạm vi dữ liệu, rủi ro rò rỉ bộ nhớ và tác động lên khả năng thu hồi quyền.

### 3.4. Tính xác thực và nguồn gốc (authenticity & provenance)

Hệ thống cần trả lời được: *Khóa này do ai hoặc thành phần nào tạo? Nó thuộc về đối tượng nào? Tôi có đang dùng đúng khóa không?*

Khóa nên được sinh bằng bộ sinh số ngẫu nhiên phù hợp cho mật mã (CSPRNG) hoặc trong KMS/HSM được tin cậy, với độ dài và thuật toán đáp ứng yêu cầu bảo mật. Không dùng chuỗi dễ đoán, timestamp, hàm random thông thường hoặc mật khẩu thô như khóa AES.

Khi phân phối khóa công khai hoặc chứng chỉ, cần kiểm tra chuỗi tin cậy, danh tính và mục đích sử dụng. Khi nhận khóa từ hệ thống khác, cần xác thực nguồn cấp và kiểm tra tính toàn vẹn trước khi đưa vào sử dụng.

### 3.5. Kiểm soát quyền và mục đích sử dụng (authorization & usage control)

Một khóa có thể vẫn bí mật nhưng bị **lạm dụng**: tài khoản bị chiếm quyền gọi API giải mã hàng loạt, nhân viên dùng khóa ký phát hành trái phép, hoặc dịch vụ thử giải mã dữ liệu của tenant khác.

Vì vậy, cần phân biệt **quyền truy xuất vật liệu khóa** và **quyền thực hiện phép toán bằng khóa**. KMS/HSM có thể giữ khóa không xuất được nhưng vẫn cho phép các thao tác mật mã theo chính sách. Các cơ chế quan trọng gồm:

1. **Ít đặc quyền nhất:** Chỉ cấp đúng hành động cần thiết, chẳng hạn Encrypt, Decrypt, Sign hoặc Verify.
2. **Tách nhiệm vụ:** Người quản trị chính sách, người vận hành và ứng dụng sử dụng khóa không mặc nhiên có toàn bộ quyền của nhau.
3. **Ràng buộc danh tính và ngữ cảnh:** Dùng danh tính workload, môi trường, tenant, loại dữ liệu và điều kiện chính sách để giới hạn yêu cầu.
4. **Tách khóa theo mục đích:** Tránh dùng cùng một khóa cho nhiều thuật toán, môi trường hay mục đích không liên quan; tách khóa mã hóa khỏi khóa ký, production khỏi development.
5. **Hạn chế xuất khóa:** Ưu tiên thao tác trong HSM/KMS khi mô hình xử lý cho phép.

Việc gọi API thành công **không chứng minh thao tác đó hợp lệ về nghiệp vụ**. Ứng dụng vẫn phải xác thực người dùng, kiểm tra quyền truy cập bản ghi và ngăn tài khoản hợp lệ đọc dữ liệu ngoài phạm vi.

### 3.6. Khả năng truy vết và kiểm toán (accountability & auditability)

Mỗi thao tác quan trọng cần có dấu vết đủ để điều tra và chứng minh chính sách đang được thực thi: tạo khóa, thay đổi quyền, sử dụng khóa, từ chối truy cập, xoay vòng, vô hiệu hóa, khôi phục và xóa.

Log kiểm toán nên ghi **ai** yêu cầu, **làm gì**, **trên khóa nào**, **khi nào**, **kết quả** và **ngữ cảnh liên quan**. Không ghi khóa dạng rõ, plaintext, bí mật xác thực hay dữ liệu nhạy cảm không cần thiết. Cần bảo vệ log khỏi chỉnh sửa trái phép, quy định thời gian lưu và cảnh báo các dấu hiệu như tăng đột biến yêu cầu Decrypt, thay đổi chính sách bất thường hoặc sử dụng từ workload lạ.

Kiểm toán giúp phát hiện và phân tích sự cố; nó không thay thế cơ chế chặn hành động trái phép ngay từ đầu.

## 4. Mục tiêu phải được duy trì trong toàn bộ vòng đời khóa

| Giai đoạn | Điều phải bảo đảm | Sai sót điển hình |
| --- | --- | --- |
| **Tạo (generation)** | Đủ ngẫu nhiên; thuật toán/độ dài phù hợp; biết nguồn tạo và chủ sở hữu | Tạo khóa từ chuỗi đoán được hoặc tái sử dụng khóa ngoài dự kiến |
| **Cấp phát, phân phối (provisioning/distribution)** | Đúng người nhận, đúng môi trường, kênh được xác thực và bảo vệ | Gửi khóa qua kênh không bảo mật hoặc trao cho workload nhầm quyền |
| **Lưu trữ (storage)** | Giữ bí mật, toàn vẹn, phân quyền và sao lưu an toàn | Hardcode key, để key cạnh ciphertext, sao lưu key dạng rõ |
| **Sử dụng (usage)** | Đúng mục đích, chủ thể, ngữ cảnh; giới hạn lộ khóa trong bộ nhớ | Một dịch vụ dùng quyền Decrypt để đọc dữ liệu của mọi tenant |
| **Xoay vòng (rotation)** | Có khóa mới; dữ liệu cũ vẫn đọc được trong giai đoạn chuyển đổi; kiểm soát phiên bản | Xóa khóa cũ quá sớm hoặc tưởng đổi KEK đã tự mã hóa lại toàn bộ dữ liệu |
| **Vô hiệu hóa/thu hồi (disable/revoke)** | Ngăn tiếp tục sử dụng khóa hoặc danh tính không còn được tin cậy; xác định tác động đến dữ liệu | Chỉ sửa cấu hình ở một nơi trong khi bản sao/cache hoặc quyền khác vẫn hoạt động |
| **Hủy (destruction)** | Khóa không còn cần đến được xóa theo chính sách, gồm bản sao có thể khôi phục | Xóa khóa đang phục vụ dữ liệu lưu trữ dài hạn; quên khóa trong backup |

**Xoay vòng, thu hồi và hủy là các hành động khác nhau.** Xoay vòng tạo hoặc chọn khóa mới; thu hồi/vô hiệu hóa chặn khả năng sử dụng theo chính sách; hủy loại bỏ vật liệu khóa khi hết nghĩa vụ bảo tồn. Việc xóa DEK duy nhất có thể khiến dữ liệu không còn giải mã được (cryptographic erasure), nhưng kết luận này chỉ vững nếu không còn bản sao khóa có thể sử dụng ở cache, backup, môi trường dự phòng hoặc hệ thống khác.

Khi phát hiện khóa bị lộ, việc tạo khóa mới **không làm biến mất** các bản sao dữ liệu rõ đã bị lấy trước đó. Cần chặn quyền dùng khóa cũ, xác định phạm vi ảnh hưởng, thay khóa và mã hóa lại dữ liệu bị ảnh hưởng khi cần, rà soát log và xử lý các bản sao/phiên còn hiệu lực. Đối với khóa ký, còn phải cân nhắc chữ ký đã phát hành, mốc thời gian, quy tắc xác minh và cơ chế thu hồi chứng chỉ.

## 5. Ví dụ: Bảo vệ khóa mã hóa dữ liệu khách hàng bằng envelope encryption

Giả sử một ứng dụng Java lưu thông tin khách hàng trong cơ sở dữ liệu. Hệ thống muốn dữ liệu vẫn khó đọc khi kẻ tấn công chỉ lấy được bản sao database.

Thiết kế thường gặp:

- **KEK** được quản lý trong KMS/HSM, với chính sách chỉ cho workload có thẩm quyền thực hiện các thao tác cần thiết.
- **DEK** được tạo riêng cho một phạm vi dữ liệu thích hợp (ví dụ: mỗi đối tượng, nhóm bản ghi hoặc lô dữ liệu). DEK mã hóa dữ liệu bằng thuật toán AEAD như AES-GCM.
- Ứng dụng lưu **ciphertext**, **nonce/IV**, **authentication tag**, **DEK đã wrap**, định danh/phiên bản KEK và các metadata cần thiết. Không lưu DEK dạng rõ lâu dài cùng bản ghi.
- Khi cần giải mã, ứng dụng phải vượt qua kiểm tra quyền nghiệp vụ, rồi mới gọi KMS để unwrap DEK theo đúng ngữ cảnh.

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng Java
    participant KMS as KMS / HSM
    participant DB as Cơ sở dữ liệu
    App->>KMS: Yêu cầu tạo DEK với KEK và ngữ cảnh
    KMS-->>App: DEK rõ tạm thời + DEK đã wrap
    Note over App: Mã hóa AES-GCM, AAD ràng buộc bản ghi
    App->>DB: Lưu ciphertext + nonce + tag + DEK đã wrap + metadata
    Note over App: Giảm thời gian giữ DEK rõ trong bộ nhớ
    App->>DB: Đọc bản ghi đã mã hóa
    DB-->>App: Ciphertext + metadata + DEK đã wrap
    App->>KMS: Unwrap DEK theo danh tính và ngữ cảnh
    KMS-->>App: DEK rõ nếu được phép
    Note over App: Kiểm tra tag/AAD và giải mã
~~~

Đây là luồng **minh họa**: tùy KMS, thao tác tạo DEK có thể trả cả DEK dạng rõ và bản đã wrap. Cách này giúp giảm việc lưu DEK rõ, nhưng trong thời điểm mã hóa/giải mã ứng dụng vẫn phải bảo vệ DEK trong bộ nhớ. Một số thiết kế khác dùng thao tác mật mã trực tiếp trong KMS/HSM hoặc các cơ chế cấp khóa khác.

Các mục tiêu bảo mật thể hiện ở đây:

| Mục tiêu | Cách đáp ứng trong thiết kế |
| --- | --- |
| Bí mật | KEK được bảo vệ trong KMS/HSM; DEK lưu trữ dưới dạng đã wrap; database không giữ DEK rõ |
| Toàn vẹn | AES-GCM kiểm tra tag; AAD gắn ciphertext với bản ghi/tenant; metadata và định danh khóa được kiểm soát |
| Quyền sử dụng | KMS kiểm tra quyền của workload; ứng dụng kiểm tra người dùng có quyền đọc bản ghi hay không |
| Sẵn sàng | Duy trì phiên bản KEK cần thiết để unwrap dữ liệu cũ; có kế hoạch phục hồi KMS/khóa |
| Truy vết | Ghi nhận thao tác tạo, unwrap và thay đổi chính sách mà không làm lộ DEK/khách hàng |

Một luồng xử lý khái niệm:

~~~text
Ghi dữ liệu:
  xác thực người dùng và kiểm tra quyền ghi
  (DEK, wrappedDEK) = KMS.generateDataKey(KEK, context)
  nonce = CSPRNG.generateNonce()         # không tái sử dụng nonce với cùng DEK
  (ciphertext, tag) = AEAD.encrypt(DEK, nonce, plaintext, AAD)
  lưu(ciphertext, tag, nonce, wrappedDEK, keyId, contextMetadata)
  giảm thời gian giữ DEK rõ trong bộ nhớ

Đọc dữ liệu:
  xác thực người dùng và kiểm tra quyền đọc bản ghi
  đọc(ciphertext, tag, nonce, wrappedDEK, keyId, contextMetadata)
  DEK = KMS.unwrap(wrappedDEK, keyId, context)
  plaintext = AEAD.decryptAndVerify(DEK, nonce, ciphertext, tag, AAD)
  chỉ trả dữ liệu khi xác minh tag/AAD thành công
~~~

**Lưu ý khi triển khai thực tế:** Với AES-GCM, nonce phải không trùng cho các lần mã hóa dưới cùng một khóa; cách tạo nonce phải phù hợp giới hạn của thuật toán và tần suất mã hóa. AAD khi giải mã phải khớp với AAD lúc mã hóa. Không tự triển khai thuật toán mật mã; dùng thư viện và API đã được kiểm chứng, xử lý lỗi xác thực như một thất bại toàn bộ thao tác.

### Khi xoay vòng khóa

Nếu chỉ **đổi KEK**, có thể unwrap từng DEK cũ bằng KEK cũ rồi wrap lại bằng KEK mới, tùy khả năng dịch vụ; ciphertext của dữ liệu thường không cần thay đổi. Nếu **đổi DEK**, cần giải mã và mã hóa lại phần dữ liệu mà DEK đó bảo vệ. Hệ thống phải duy trì thông tin phiên bản và kế hoạch chuyển đổi để không mất khả năng giải mã dữ liệu đang tồn tại.

## 6. Những tình huống thất bại cần nhận diện

| Tình huống | Mục tiêu bị vi phạm | Hậu quả và hướng xử lý |
| --- | --- | --- |
| Khóa AES nằm trong repository cùng code | Bí mật, kiểm soát sử dụng | Người có code có thể giải mã dữ liệu; loại bỏ đường cấp phát cũ, thay khóa, đánh giá dữ liệu bị ảnh hưởng và đưa bí mật sang cơ chế quản lý phù hợp |
| Kẻ tấn công thay khóa công khai của đối tác | Xác thực, toàn vẹn | Dữ liệu mã hóa sai người nhận hoặc chữ ký bị gán nhầm danh tính; xác minh kênh phân phối và chuỗi tin cậy |
| Tài khoản dịch vụ có quyền Decrypt trên toàn bộ khóa | Phân quyền, truy vết | Một lần lộ thông tin xác thực mở rộng phạm vi bị ảnh hưởng; chia phạm vi khóa/quyền theo workload và môi trường, giám sát bất thường |
| Nhân viên vô tình xóa KEK đang sử dụng | Sẵn sàng, khôi phục | Nhiều DEK không thể unwrap, dữ liệu không đọc được; giới hạn quyền xóa, có phê duyệt và kế hoạch phục hồi |
| Chỉ đổi khóa mới nhưng tiếp tục dùng khóa cũ ở các tiến trình khác | Thu hồi, nhất quán vòng đời | Kẻ tấn công có thể tiếp tục dùng khóa đã lộ; quản lý trạng thái, phiên bản, cache và thời điểm vô hiệu hóa trên toàn hệ thống |
| Log ghi lại raw DEK hoặc nội dung giải mã | Bí mật, kiểm toán an toàn | Log trở thành nơi lộ bí mật; che/redact dữ liệu nhạy cảm, giới hạn truy cập và xử lý bản sao đã phát tán |

## 7. Các câu hỏi để đánh giá một thiết kế quản lý khóa

Khi review một dịch vụ, có thể kiểm tra lần lượt:

1. **Định danh:** Khóa này thuộc loại nào, bảo vệ tài sản gì, ai sở hữu và đang dùng ở môi trường nào?
2. **Sinh khóa:** Khóa có được tạo bằng cơ chế ngẫu nhiên phù hợp, thuật toán và độ dài đáp ứng yêu cầu không?
3. **Bí mật:** Khóa nào bắt buộc phải bí mật? Có xuất hiện dạng rõ trong code, biến môi trường, log, dump, bản sao lưu hoặc hệ thống giám sát không?
4. **Tin cậy:** Nếu là khóa công khai/chứng chỉ, hệ thống chứng minh được nó thuộc đúng chủ thể bằng cách nào?
5. **Quyền:** Ai được dùng khóa, được thực hiện hành động nào, trong hoàn cảnh nào? Một workload bị chiếm quyền có thể ảnh hưởng bao nhiêu dữ liệu?
6. **Toàn vẹn:** Có kiểm tra ciphertext/tag và ràng buộc đúng tenant, bản ghi, phiên bản khóa và metadata không?
7. **Khôi phục:** Nếu KMS ngừng hoạt động hoặc một khóa bị xóa nhầm, dữ liệu nào ngừng đọc được, và quy trình khôi phục đã được thử chưa?
8. **Thay đổi:** Có kế hoạch xoay vòng, phản ứng khi nghi lộ khóa, thu hồi quyền và chuyển đổi dữ liệu phụ thuộc không?
9. **Hủy:** Khi hết thời hạn lưu trữ, đã xác định được các bản sao và hệ thống phụ thuộc trước khi hủy khóa chưa?
10. **Kiểm toán:** Có thể xác định ai đã dùng/thay đổi khóa và phát hiện hành vi bất thường mà không ghi lộ bí mật không?

## 8. Ghi nhớ

- **Bí mật** bảo vệ khóa không được công khai; **toàn vẹn và xác thực** bảo đảm đang dùng đúng khóa, đúng nguồn; **sẵn sàng** duy trì khả năng truy cập hợp lệ.
- **Phân quyền theo mục đích** giảm thiểu tác hại ngay cả khi vật liệu khóa không bị lộ. KMS/HSM là thành phần quan trọng nhưng ứng dụng vẫn phải kiểm soát quyền truy cập dữ liệu.
- **Quản lý vòng đời** giữ các mục tiêu trên nhất quán từ khi tạo đến khi hủy, kể cả phiên bản, backup, cache và quá trình ứng phó sự cố.
- **Truy vết** cung cấp bằng chứng để giám sát và điều tra, đồng thời bản thân log phải được bảo vệ.

Một thiết kế key management tốt luôn bắt đầu bằng việc xác định **khóa nào phải bí mật, khóa nào phải được xác thực, ai được phép sử dụng và điều gì xảy ra nếu khóa bị lộ, bị thay thế hoặc không còn sẵn dùng**.
