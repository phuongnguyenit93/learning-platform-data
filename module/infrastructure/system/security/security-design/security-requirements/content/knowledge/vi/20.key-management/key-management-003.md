# Key storage

## 1. Lưu khóa là thiết kế một ranh giới tin cậy

Một hệ thống có thể sử dụng thuật toán mã hóa phù hợp nhưng vẫn mất khả năng bảo vệ nếu khóa được đặt cạnh dữ liệu, được ghi vào log hoặc có thể tải xuống bằng một tài khoản quá rộng quyền.

**Key storage** là việc giữ vật liệu khóa cùng metadata và các phụ thuộc cần thiết theo một chính sách về bí mật, toàn vẹn, quyền sử dụng và khả năng phục hồi. Nó bao gồm cả nơi khóa được lưu bền vững lẫn những bản sao xuất hiện khi ứng dụng vận hành.

Trong thiết kế yêu cầu bảo mật, câu “lưu khóa trong vault” chưa đủ. Cần xác định:

1. Khóa nào được lưu và phục vụ mục đích nào?
2. Chủ thể nào có thể lấy vật liệu khóa, chủ thể nào chỉ được dùng khóa?
3. Cơ chế nào bảo vệ khóa khi lưu và khi được mở để sử dụng?
4. Credential dùng để mở kho hoặc gọi dịch vụ khóa được bảo vệ thế nào?
5. Có những bản sao nào trong backup, bộ nhớ, container, máy vận hành hoặc công cụ chẩn đoán?
6. Khi kho lỗi, quyền bị thu hồi hoặc môi trường chính mất, hệ thống xử lý ra sao?

Mục tiêu cần đạt không phải chỉ có một file đã đặt password. Mục tiêu là không có đường lấy hoặc sử dụng khóa ngoài chính sách, đồng thời các tác vụ hợp lệ vẫn khôi phục và sử dụng được khóa theo cam kết.

## 2. Phân loại thứ đang được lưu

Không phải mọi đối tượng có chữ “key” đều cần cùng chính sách, và không phải mọi bí mật đều là khóa mật mã.

| Đối tượng | Thuộc tính cần bảo vệ | Câu hỏi chính |
| --- | --- | --- |
| Khóa mã hóa đối xứng | Bí mật, toàn vẹn, đúng mục đích và phiên bản | Ai có thể giải mã dữ liệu nếu lấy hoặc sử dụng được khóa? |
| Khóa riêng ký số | Bí mật, quyền ký, phạm vi sử dụng | Ai có thể tạo chữ ký được hệ thống khác tin? |
| Khóa riêng TLS | Bí mật và sử dụng cho đúng danh tính dịch vụ | Hạ tầng nào được phép chứng minh danh tính đó? |
| KEK hoặc root key | Bảo vệ nhiều khóa hoặc nhánh dẫn xuất | Phạm vi ảnh hưởng nếu khóa gốc bị lộ hoặc bị lạm dụng? |
| DEK đã được bọc | Toàn vẹn, metadata và quyền tháo bọc | Cần khóa nào để khôi phục và nó thuộc tài nguyên nào? |
| Public key hoặc certificate | Tính đúng nguồn, toàn vẹn và chính sách tin cậy | Ai được phép thay đổi điều mà hệ thống tin? |
| Password, PIN hoặc token mở kho | Bí mật và phạm vi quyền | Nó có trở thành một bản sao quyền sử dụng khóa không? |
| Alias, key ID hoặc key reference | Đúng ánh xạ, đúng môi trường và chính sách | Giá trị đó có trỏ sang khóa ngoài phạm vi được phép không? |

Public key không cần được giữ bí mật như private key, nhưng việc thay một trust anchor có thể làm thay đổi toàn bộ quyết định xác thực. Ngược lại, một key reference không chứa vật liệu bí mật cũng không được coi là quyền giải mã.

Một yêu cầu inventory phải phân biệt các loại này. Nếu ghi tất cả thành một danh sách “secret”, đội có thể bỏ sót rủi ro toàn vẹn của trust store hoặc không nhận ra credential quản trị kho có phạm vi rộng hơn một khóa nghiệp vụ.

## 3. Mô hình đe dọa trước khi chọn nơi lưu

Giả sử hệ thống lưu tài liệu và ký thông báo cho đối tác. Có thể phân tích những trường hợp sau:

| Năng lực của bên tấn công | Rủi ro cần đánh giá | Ranh giới cần kiểm chứng |
| --- | --- | --- |
| Có bản sao repository hoặc image | Bí mật được đóng gói cùng phần mềm | Quy trình build và phân phối cấu hình |
| Có bản sao ổ đĩa hoặc backup | Lấy file keystore cùng vật liệu mở nó | Bảo vệ bản lưu và tách quyền mở kho |
| Có quyền đọc storage dữ liệu | Lấy ciphertext, wrapped key và metadata | Quyền tháo bọc độc lập với quyền đọc bản lưu |
| Có danh tính ứng dụng | Gọi giải mã hoặc ký quá phạm vi | Quyền dùng khóa, resource policy và kiểm tra nghiệp vụ |
| Có quyền quản trị kho | Tự cấp quyền, đổi alias hoặc xóa phụ thuộc | Phân tách trách nhiệm và quy trình thay đổi |
| Chiếm quyền tiến trình | Đọc vật liệu trong bộ nhớ hoặc gọi phép toán với handle đang có | Phạm vi khóa nạp vào và khả năng lạm dụng |
| Sửa trust store hoặc provider | Chuyển ranh giới tin cậy sang một nguồn khác | Toàn vẹn cấu hình, đường nạp và cập nhật |
| Làm kho không khả dụng | Ứng dụng không thể mở dữ liệu hoặc chứng minh danh tính | Hành vi lỗi và khả năng phục hồi |

Không nên đặt một mục tiêu chung như “chống mọi người quản trị” nếu một người vẫn có thể tự cấp cả quyền lấy dữ liệu và quyền sử dụng khóa mà không gặp kiểm soát nào khác.

Một thiết kế tốt nêu rõ điều gì còn nằm trong trusted computing base. Nếu ứng dụng được phép ký bằng một khóa, việc giữ khóa không xuất được chưa tự ngăn ứng dụng đã bị chiếm quyền yêu cầu ký những thông điệp không phù hợp.

## 4. So sánh các mô hình lưu giữ

| Mô hình | Cách ứng dụng tiếp cận khóa | Những điều phải xác định |
| --- | --- | --- |
| File khóa hoặc keystore được bảo vệ | Có thể nạp vật liệu vào tiến trình | Định dạng, quyền file, credential mở, backup và bản sao runtime |
| Kho credential/secret tập trung | Lấy một secret theo danh tính | Ai được đọc giá trị, thời hạn cấp và các kênh làm lộ sau khi lấy |
| KMS hoặc dịch vụ mật mã | Có thể gọi phép toán hoặc thao tác với khóa theo API | Quyền theo operation, key reference, context và giới hạn xuất |
| HSM hoặc token mật mã | Dùng khả năng của module/provider theo chính sách | Thuộc tính khóa, quyền đăng nhập, cơ chế backup và tính sẵn sàng |
| Khóa đã bọc lưu cùng dữ liệu | Tải blob rồi nhờ lớp khác khôi phục | KEK, tính toàn vẹn, binding tài nguyên và quy trình đọc lại |

Tên sản phẩm không đủ kết luận. Một secret manager trả raw key cho ứng dụng và một dịch vụ chỉ nhận yêu cầu ký có hai ranh giới khác nhau, dù cả hai đều có thể được gọi là “vault”.

### Lưu trữ và thực hiện phép toán là hai quyền khác nhau

Đối với khóa có mục tiêu không xuất vật liệu, nên đặc tả theo hành vi:

> Danh tính ứng dụng chỉ được thực hiện tập phép toán đã cấp trên khóa được chọn. Không có API hoặc đường vận hành trong phạm vi của danh tính đó trả vật liệu khóa rõ.

Yêu cầu này phải được kiểm chứng bằng khả năng và policy thật của nền tảng. Không chỉ kiểm tra rằng giao diện chính không có nút Download.

Nếu thiết kế cho phép xuất khóa để backup hoặc chuyển đổi, phải quy định chủ thể, định dạng bảo vệ, điểm đến và quy trình riêng. Không để một tính năng vận hành trở thành quyền xuất mặc định của mọi ứng dụng.

## 5. Khóa được mã hóa cần một điểm neo tin cậy cuối cùng

“Mã hóa khóa rồi lưu xuống database” chỉ có ý nghĩa khi quyền mở khóa mã hóa đó được bảo vệ phù hợp. Nếu password mở keystore được đặt cạnh file với cùng quyền đọc, một bên lấy cả hai có thể vượt qua ranh giới mà thiết kế tưởng đã tạo.

Không thể giải quyết vấn đề bằng một chuỗi vô hạn các khóa mã hóa lẫn nhau mà không xác định nơi neo tin cậy. Hệ thống cuối cùng phải dựa vào một cơ chế như danh tính workload, kho được hệ điều hành bảo vệ, module mật mã hoặc một quy trình mở khóa được kiểm soát.

[OWASP Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html) nhấn mạnh việc bảo vệ khóa trong cả bộ nhớ lẫn nơi lưu bền vững, tránh đưa khóa vào repository/build artifact và áp dụng bảo vệ toàn vẹn. Các nguyên tắc ấy cần được chuyển thành ranh giới cụ thể của dự án.

Ví dụ một chuỗi phụ thuộc có thể được mô tả:

```text
Danh tính workload được nền tảng xác minh
    → quyền gọi dịch vụ khóa trong phạm vi được cấp
    → sử dụng KEK để tháo bọc đúng DEK
    → DEK rõ chỉ xuất hiện trong phạm vi xử lý được phép
    → bản DEK đã bọc được giữ cùng metadata dữ liệu
```

Ở một môi trường khác, điểm neo có thể là token phần cứng và một quy trình đăng nhập vào token. Cả hai đều cần mô tả cách cấp, thu hồi và phục hồi quyền, không chỉ cách lưu một object khóa.

### Bootstrap credential không được bị bỏ khỏi inventory

Nếu ứng dụng dùng một access token dài hạn để mở kho, access token đó có thể trở thành bí mật quan trọng nhất trong chuỗi. Cần xét nơi nó được cấp, được giữ, được làm mới và ai có thể sử dụng nó.

Danh tính ngắn hạn hoặc workload identity có thể giảm nhu cầu giữ credential dài hạn trong ứng dụng, nhưng vẫn cần cấu hình trust, audience, phạm vi quyền và nguồn cấp phù hợp. Không mặc định mọi token do môi trường cung cấp đều được phép dùng cho mọi kho.

## 6. Envelope key và ranh giới bộ nhớ ứng dụng

Trong một mô hình envelope, KEK và DEK có thể có chính sách lưu giữ khác nhau. Một KEK được dùng qua dịch vụ mật mã không có nghĩa DEK của ứng dụng cũng luôn ở trong dịch vụ đó.

Ví dụ, [AWS KMS về data key](https://docs.aws.amazon.com/kms/latest/developerguide/data-keys.html) phân biệt symmetric KMS key không tải về với data key có thể được trả ở dạng rõ để dùng bên ngoài KMS và dạng mã hóa để lưu. Vì vậy, đánh giá key storage phải đi theo từng loại vật liệu chứ không dừng ở việc ứng dụng gọi KMS.

Một hợp đồng của dự án có thể quy định:

- KEK chỉ được dùng qua operation và danh tính đã phê duyệt.
- DEK rõ chỉ được giữ trong tác vụ hoặc cache có thời hạn cụ thể.
- Wrapped DEK có định dạng phiên bản, key reference và ngữ cảnh liên quan.
- Không lưu thêm một bản DEK rõ trong database, file tạm hoặc log.
- Quyền lấy wrapped DEK không tự cấp quyền tháo bọc.
- Các bản sao backup giữ đủ metadata nhưng không mở thêm đường giữ khóa rõ.

Wrapped key có thể được lưu cùng ciphertext theo thiết kế mà không làm mất sự phân lớp. Điều cần tách là khả năng khôi phục vật liệu rõ và quyền dùng lớp bảo vệ nó, không chỉ là hai chuỗi nằm ở hai thư mục khác nhau.

Không coi Base64 của một raw key là wrapped key. Encoding chỉ thay biểu diễn; key wrapping hoặc cơ chế bảo vệ khóa phải là một phần mật mã có thuộc tính được xác định.

## 7. Java KeyStore: API không tự quyết định toàn bộ mức bảo vệ

Java `KeyStore` là abstraction lưu khóa và certificate với các loại entry khác nhau. Backend lưu giữ và cơ chế bảo vệ phụ thuộc implementation/provider. [Tài liệu KeyStore của Java](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/KeyStore.html) mô tả private key entry, secret key entry, trusted certificate entry và alias; không nên hiểu tên lớp là một bảo đảm rằng mọi vật liệu luôn nằm trong phần cứng.

Ví dụ các điểm lựa chọn khác nhau:

```java
KeyStore fileStore = KeyStore.getInstance("PKCS12");
KeyStore tokenStore = KeyStore.getInstance("PKCS11", approvedProvider);
```

Đây là minh họa lựa chọn type/provider, không phải cấu hình hoàn chỉnh để nạp hoặc sử dụng khóa. `approvedProvider` phải đến từ cấu hình được kiểm soát; không phải đối tượng hay tên tùy ý do request cung cấp.

### Với keystore dạng file

Một profile cần nêu rõ:

1. Định dạng và cơ chế bảo vệ được chấp nhận trên runtime mục tiêu.
2. Password hoặc protection parameter được cấp qua kênh nào.
3. Ai có thể đọc file, sửa file, thay alias hoặc tạo bản sao.
4. Ứng dụng nạp đúng file và đúng loại entry thế nào.
5. Cách cập nhật mà không tạo file tạm rõ hoặc làm hỏng bản đang hoạt động.
6. Nhu cầu backup và phụ thuộc để mở lại ở môi trường phục hồi.

Không để đường dẫn, alias hoặc type keystore từ một request trực tiếp quyết định file hay khóa mà tiến trình có quyền mở. Key selection phải gắn với mục đích và danh mục tài nguyên được phép.

Phần mở rộng `.p12`, `.jks` hoặc `.pem` không tự chứng minh một profile đáp ứng yêu cầu. Cần biết định dạng, tham số bảo vệ, provider và quyền truy cập thực sự.

### Với provider kết nối token hoặc HSM

[Oracle PKCS#11 Reference Guide](https://docs.oracle.com/en/java/javase/25/security/pkcs11-reference-guide1.html) giải thích kiến trúc provider và vai trò cầu nối tới implementation PKCS#11. Do đó, yêu cầu phải bao gồm cấu hình module, thư viện nhà cung cấp, cơ chế hỗ trợ và cách ứng dụng đăng nhập theo môi trường thực tế.

Không suy rằng mọi object `PrivateKey` đều cho phép hoặc đều không cho phép xuất byte. Thuộc tính cần chứng minh nằm ở loại khóa, provider và policy của module đang dùng.

Một lần gọi phương thức trả về `null` hoặc một cờ metadata riêng lẻ chưa phải bằng chứng rằng mọi đường export, backup hoặc quyền quản trị đều đã bị chặn. Ma trận kiểm chứng phải bao phủ những khả năng trong phạm vi của từng danh tính.

## 8. Trust store cần được bảo vệ về toàn vẹn

Trust store thường giữ certificate hoặc public key mà ứng dụng dùng để quyết định tin nguồn nào. Dữ liệu không nhất thiết bí mật, nhưng thay đổi nó có thể làm ứng dụng chấp nhận một đối tác hoặc máy chủ không thuộc chính sách.

Một yêu cầu của dự án nên xác định:

- Nguồn phát hành trust material được chấp nhận.
- Người hoặc dịch vụ có quyền thêm, bỏ, thay certificate.
- Cách phân phối và xác nhận tính toàn vẹn của bản cập nhật.
- Phạm vi ứng dụng thực sự dùng trust store nào.
- Cách quay lại một trạng thái hợp lệ khi cập nhật sai.
- Cách theo dõi version và owner.

Không thay một lỗi trust bằng việc tắt xác minh certificate hoặc chấp nhận mọi certificate. Cách xử lý đó làm thay mục tiêu bảo mật, không chỉ thay nơi lưu khóa.

Một ứng dụng cũng không nên tin một trust store chỉ vì file nằm ở đường dẫn quen thuộc. Quyền sửa file, cấu hình đường nạp và gói phân phối đều thuộc ranh giới phải bảo vệ.

## 9. Container, biến môi trường và secret được cấp lúc chạy

Việc không commit key vào source là cần thiết nhưng chưa đủ nếu key được đóng vào image, đưa vào build argument, ghi ở log CI hoặc sao chép sang artifact khác.

Một chính sách triển khai nên phân biệt:

| Kênh | Rủi ro cần đánh giá | Yêu cầu phù hợp với dự án |
| --- | --- | --- |
| Repository và lịch sử phiên bản | Bí mật bị sao chép rộng và tồn tại lâu | Chỉ chứa reference/cấu hình không bí mật; có phát hiện và ứng phó rò rỉ |
| Image hoặc binary | Khóa đi cùng mọi bản triển khai | Không đóng vật liệu thật vào artifact dùng chung |
| Tham số dòng lệnh | Công cụ vận hành hoặc log có thể ghi nhận giá trị | Không dùng như kênh mặc định cho khóa/PIN nhạy cảm |
| Biến môi trường | Có thể xuất hiện trong dump, debug hoặc công cụ có quyền xem môi trường | Phạm vi cấp, quyền quan sát và chính sách chẩn đoán rõ ràng |
| Secret mount | File và quyền đọc xuất hiện trong workload | Chỉ mount cho thành phần cần dùng, bảo vệ đường nạp và bản sao |
| SDK lấy secret/operation tại runtime | Danh tính ứng dụng trở thành quyền tiếp cận | Cấp quyền tối thiểu, xác minh endpoint và giới hạn thời gian |

Không có một kênh duy nhất tự an toàn trong mọi mô hình. Cần đánh giá quyền mà hệ điều hành, container runtime và công cụ chẩn đoán thực sự cung cấp.

### Đối tượng mang tên Secret không tự đủ bảo vệ

[Tài liệu Kubernetes Secrets](https://kubernetes.io/docs/concepts/configuration/secret/) nêu rõ mặc định lưu Secret không mã hóa trong etcd và cần cấu hình encryption at rest cùng quyền truy cập phù hợp. Base64 trong manifest không phải cơ chế giữ bí mật.

Với một hệ thống dùng Kubernetes, inventory phải xét cả quyền đọc Secret trực tiếp và những quyền workload có thể dẫn tới việc nạp Secret. Không chỉ kiểm tra một danh sách quyền API hẹp mà bỏ qua khả năng tạo hoặc sửa workload được cấp bí mật.

Không sao chép một manifest có raw key thật vào repository để tiện áp dụng. Cấu hình triển khai nên giữ reference và đường cấp bí mật theo mô hình đã chọn.

## 10. Phân tách quyền đọc, sử dụng, quản trị và phục hồi

Một chủ thể không nên tự động có mọi quyền chỉ vì có trách nhiệm vận hành một dịch vụ. Quyền cần được biểu diễn theo operation và phạm vi tài nguyên.

Ví dụ ma trận cho dịch vụ ký thông báo:

| Chủ thể | Phép toán được cấp | Xuất vật liệu rõ | Đổi policy/alias | Phục hồi |
| --- | --- | --- | --- | --- |
| Workload ký thông báo | Ký theo profile và khóa được cấp | Không thuộc quyền mặc định | Không | Không |
| Workload kiểm tra chữ ký | Lấy public material phù hợp | Không cần private key | Không | Không |
| Đội quản trị khóa | Thay đổi theo quy trình được duyệt | Theo policy riêng, không mặc định | Theo quyền được cấp | Theo nhiệm vụ |
| Tác vụ sao lưu | Tạo bản bảo vệ theo cơ chế hỗ trợ | Không tự suy ra từ quyền backup | Không | Chỉ nếu được cấp riêng |
| Tác vụ phục hồi sự cố | Khôi phục đúng phạm vi được giao | Không xuất tùy ý | Theo kế hoạch sự cố | Có kiểm soát |

Đây là một ví dụ thiết kế, không phải role có sẵn của một sản phẩm. Khi áp dụng, phải kiểm tra một chủ thể có thể tự cấp thêm quyền, thay resource policy hoặc dùng một danh tính khác để đi vòng hay không.

### Quyền dùng khóa cần phù hợp quyền nghiệp vụ

Một dịch vụ có quyền ký không được trở thành endpoint ký mọi dữ liệu mà caller gửi. Trước phép toán mật mã, nó vẫn cần xác minh caller, kiểm tra hành động và tạo đúng thông điệp nghiệp vụ theo hợp đồng.

Nếu dịch vụ được quyền tháo bọc DEK, cần ràng buộc quyền đó với tài nguyên hoặc context của tác vụ. Không dựa vào một tenant ID tự khai để chọn bất kỳ key reference nào.

Quyền quản trị và quyền sử dụng cũng có thể gián tiếp giao nhau. Người không được gọi Decrypt nhưng có thể tự sửa policy để cấp Decrypt vẫn thuộc một ranh giới cần được quản lý.

## 11. Metadata, alias và toàn vẹn việc chọn khóa

Một bản ghi inventory không chứa vật liệu khóa có thể như sau:

```yaml
logicalKey: document-wrapping-key
environment: production
purpose: wrap-document-data-keys
owner: platform-security-team
storageModel: isolated-crypto-service
materialExportPolicy: non-exportable-for-application
allowedOperations:
  - wrap
  - unwrap
recoveryPolicy: protected-provider-recovery
```

Đây là ví dụ mô tả yêu cầu, không phải schema hoặc file cần tạo trong dự án. Các tên operation cũng là tên logic, không mặc định ánh xạ trực tiếp tới API của mọi nhà cung cấp.

Metadata cần hỗ trợ xác định khóa thuộc môi trường nào, được phép làm gì, ai sở hữu và các phiên bản nào còn cần cho dữ liệu lịch sử.

### Key reference không được là một nguồn tải tùy ý

Một envelope hoặc request có thể chứa key ID. Hệ thống phải giải quyết nó trong danh mục được phép, không biến nó thành URL, đường dẫn file hoặc tên provider mà caller có thể điều khiển.

Nếu alias có thể đổi đích, yêu cầu cần nêu hành vi của tác vụ đang chạy, cách pin phiên bản khi cần và cách xác minh policy sau thay đổi. Việc cùng alias vẫn tồn tại chưa chứng minh vật liệu hoặc quyền sử dụng giữ nguyên.

Tính toàn vẹn của mapping khóa là một phần của key storage. Một khóa bí mật được giữ tốt nhưng ứng dụng bị chuyển sang khóa của bên khác vẫn có thể làm hỏng mục tiêu bảo vệ.

## 12. Backup và phục hồi phải theo mục đích của khóa

Không phải mọi khóa đều cần một bản backup có cùng thời hạn. Chính sách phải xuất phát từ dữ liệu hoặc phép toán phụ thuộc khóa.

| Mục đích | Phụ thuộc cần xem xét |
| --- | --- |
| Giải mã dữ liệu lịch sử | Khóa và metadata còn cần cho ciphertext thuộc retention |
| Tháo bọc DEK | KEK/phiên bản cùng quyền dùng còn cần cho wrapped DEK |
| Ký dữ liệu mới | Khóa đang được phép ký và quy tắc dừng ký bằng khóa cũ |
| Kiểm tra chữ ký lịch sử | Public material và chính sách kiểm tra tương ứng; không tự cần private key chỉ để verify |
| Khóa tạm thời của giao thức | Vòng đời đã chọn có thể không yêu cầu lưu lâu dài hoặc backup |
| Danh tính TLS | Khả năng cung cấp dịch vụ, thay khóa/certificate và khôi phục đúng danh tính |

Backup phải dùng cơ chế bảo vệ và quyền phù hợp với nền tảng. Nếu module hỗ trợ bản backup được bảo vệ hoặc replication, cần kiểm tra chính khả năng đó; không tự xuất raw private key ra một file dùng chung cho “dễ restore”.

### Phục hồi là một đường truy cập khóa riêng

Runbook cần trả lời:

1. Mất môi trường chính thì lấy được bản dữ liệu và bản khóa ở đâu?
2. Danh tính phục hồi được xác thực và cấp quyền như thế nào?
3. Có cần credential, trust material, provider hoặc phiên bản phần mềm nào khác?
4. Ai có thể thực hiện và ai xác nhận phạm vi?
5. Bao lâu có thể khôi phục theo mục tiêu khả dụng?
6. Bằng chứng nào xác nhận đã dùng đúng khóa mà không đưa khóa vào báo cáo?

Không đặt mọi credential phục hồi trong chính kho duy nhất mà kịch bản giả định đã mất khả năng truy cập. Cũng không tạo một bản sao không kiểm soát ngoài hệ thống rồi coi đó là giải pháp cho mọi sự cố bootstrap.

### Không xóa bản khóa còn là phụ thuộc

Việc một khóa không còn dùng để ghi mới không chứng minh nó hết giá trị với dữ liệu cũ. Kế hoạch loại bỏ phải đối chiếu backup, retention, wrapped key và các môi trường đích còn liên quan.

Ngược lại, giữ vô thời hạn mọi bản private key cũng có chi phí rủi ro. Chính sách cần cân bằng mục tiêu khôi phục và giới hạn thời gian giữ theo đúng vai trò.

## 13. Khóa trong bộ nhớ và cache

Một file hoặc dịch vụ lưu trữ được bảo vệ có thể trả vật liệu vào tiến trình. Từ thời điểm đó, key storage còn bao gồm cache, object, bản sao tạm và khả năng công cụ chẩn đoán chụp chúng.

Những yêu cầu nên được xác định gồm:

- Chỉ nạp khóa hoặc khả năng sử dụng cần cho tác vụ.
- Giới hạn thời gian và phạm vi cache.
- Không chuyển byte khóa thành chuỗi để log hoặc so sánh trực quan.
- Bảo vệ quyền tạo/đọc dump, debug session và công cụ hỗ trợ.
- Dọn vật liệu theo khả năng runtime và thư viện.
- Không cam kết mọi bản sao đã bị xóa nếu không có bằng chứng tương ứng.

Đối với Java, việc xóa một mảng đang nắm giữ là một biện pháp cụ thể nhưng không tự chứng minh không có bản sao trong object khác, provider hoặc runtime. Thiết kế nên giảm số lần sao chép và giới hạn công cụ có thể quan sát bộ nhớ thay vì dựa vào một lời hứa tuyệt đối.

### Thu hồi quyền và vật liệu đã cache

Nếu một ứng dụng đã có raw key, thay ACL của kho không tự lấy lại byte khóa đã được tải. Nếu ứng dụng chỉ có handle, hiệu lực thu hồi vẫn cần xét session, cache và hành vi dịch vụ thực tế.

Do đó, yêu cầu thu hồi nên có độ trễ tối đa cùng cơ chế tương ứng. Không đánh dấu “thu hồi tức thì” chỉ vì API quản trị trả thành công.

Khóa đã bị sao chép ra ngoài còn cần xử lý theo quy trình compromise; không thể giải quyết chỉ bằng việc xóa một entry ở kho gốc.

## 14. Khi kho, provider hoặc credential mở kho bị lỗi

Lỗi key storage có thể xuất hiện lúc khởi động hoặc giữa một tác vụ. Cần phân loại ít nhất:

- Kho không truy cập được hoặc dịch vụ khóa timeout.
- Workload không có quyền theo policy.
- Credential mở kho không còn hợp lệ.
- Key reference, alias hoặc loại entry không đúng.
- Bản lưu, metadata hoặc trust configuration không vượt qua kiểm tra.
- Phiên bản khóa cần thiết không còn có thể sử dụng.

Hành vi phải giữ mục tiêu bảo mật. Không dùng khóa hard-code dự phòng, không tự tạo khóa mới mà giả vờ dữ liệu cũ vẫn tương thích và không ghi plaintext ra một đường tạm chưa được phê duyệt.

Ứng dụng có thể cần không sẵn sàng cho chức năng phụ thuộc khóa, hoặc trả lỗi khả dụng theo hợp đồng. Phạm vi ảnh hưởng cần được mô tả: một chức năng công khai không dùng khóa có thể có hành vi khác chức năng mở dữ liệu nhạy cảm.

### Không chữa lỗi trust bằng cách bỏ kiểm tra

Nếu client không xác minh được dịch vụ khóa, không chuyển sang chế độ tin mọi certificate. Nếu provider đúng chưa được nạp, không âm thầm dùng một backend khác có thuộc tính xuất khóa khác với profile.

Nếu có hạ tầng dự phòng, nó phải đáp ứng cùng yêu cầu về danh tính, quyền và vật liệu khóa cần thiết. Một URL khác chưa được quản lý không phải phương án phục hồi chỉ vì kết nối được.

### Lỗi không được làm lộ vật liệu

Response công khai không cần chứa đường dẫn keystore, PIN, password, raw key, token quản trị hoặc payload import. Kênh chẩn đoán nên có mã lý do, định danh tác vụ và metadata được cho phép theo quyền đọc riêng.

## 15. Audit và quản lý những bản sao không dự kiến

Một bản audit hữu ích có thể ghi được ai đã thực hiện operation nào, trên tài nguyên khóa nào, kết quả ra sao và theo thay đổi quyền nào. Nó không cần ghi vật liệu khóa để chứng minh phép toán đã xảy ra.

Các nhóm sự kiện nên được xem xét:

- Cấp hoặc thay quyền dùng khóa.
- Thay mapping/alias và cấu hình trust.
- Yêu cầu xuất hoặc backup vật liệu theo cơ chế được hỗ trợ.
- Sử dụng khóa ngoài mẫu hoạt động mong đợi.
- Thay đổi trạng thái ảnh hưởng khả năng dùng hoặc phục hồi.
- Đăng nhập quản trị và thực hiện quy trình khẩn cấp.

Khả năng audit khác nhau theo nền tảng và operation. Yêu cầu phải nêu nguồn sự kiện, độ trễ và dữ liệu có thể quan sát, không hứa theo dõi mọi lần dùng raw key cục bộ bằng log của kho từ xa.

### Repository và artifact đã lộ cần xử lý theo sự cố

Nếu key thật từng xuất hiện trong repository, xóa dòng hiện tại không chứng minh các bản clone, lịch sử hoặc artifact đã mất giá trị đó. Quy trình cần đánh giá phạm vi ảnh hưởng và thay credential/vật liệu theo rủi ro tương ứng.

Tương tự, một bản keystore được gửi qua kênh hỗ trợ có thể trở thành một bản sao ngoài inventory. Quy tắc hỗ trợ nên dùng dữ liệu tổng hợp, metadata và định danh thay cho việc yêu cầu người dùng gửi vật liệu thật.

## 16. Mẫu yêu cầu bảo mật có thể nghiệm thu

| ID | Yêu cầu | Bằng chứng nghiệm thu |
| --- | --- | --- |
| KEY-STORE-01 | Có inventory vật liệu khóa, reference, credential mở kho và các bản sao | Đối chiếu lưu bền vững, runtime, backup và kênh vận hành |
| KEY-STORE-02 | Mỗi loại khóa có mục đích, owner, môi trường và mô hình bảo vệ được xác định | Bản profile khớp nền tảng, provider và kiến trúc đang dùng |
| KEY-STORE-03 | Không đưa vật liệu thật vào repository, image hoặc artifact ngoài cơ chế được duyệt | Kiểm tra pipeline và dữ liệu tổng hợp có thể nhận diện |
| KEY-STORE-04 | Quyền sử dụng khóa được tách khỏi quyền xuất và quyền quản trị theo nhiệm vụ | Thử ma trận principal–operation trên tài nguyên thử |
| KEY-STORE-05 | Credential bootstrap có nguồn cấp, thời hạn, phạm vi và phương án phục hồi rõ | Kiểm tra khởi động, làm mới, thu hồi và sự cố kho |
| KEY-STORE-06 | Bản lưu khóa/wrapped key có bảo vệ bí mật và toàn vẹn phù hợp profile | Thử đọc không quyền, thay đổi blob/metadata và mapping sai |
| KEY-STORE-07 | Key selection không do request hoặc bản lưu tự cấp quyền | Thử reference của tenant khác, môi trường khác và đường dẫn ngoài danh mục |
| KEY-STORE-08 | Trust store và provider configuration chỉ được thay qua nguồn được cho phép | Thử thay trust material/cấu hình trong phạm vi kiểm chứng |
| KEY-STORE-09 | Cache và bộ nhớ có phạm vi, thời hạn cùng giới hạn thu hồi được mô tả | Đo hành vi sau thay quyền, kiểm tra kênh dump/log theo chính sách |
| KEY-STORE-10 | Backup và restore không tạo đường xuất raw key ngoài chính sách | Diễn tập phục hồi bằng cơ chế bảo vệ được hỗ trợ |
| KEY-STORE-11 | Kho/provider lỗi không dẫn tới khóa cố định, plaintext hoặc bỏ xác minh | Gây lỗi có kiểm soát trước và trong tác vụ |
| KEY-STORE-12 | Audit hỗ trợ đối chiếu thay đổi và sử dụng trong khả năng nền tảng mà không lộ khóa | Kiểm tra tập sự kiện, quyền đọc và dữ liệu được ghi |

Đây là bảng yêu cầu minh họa. Dự án cần chốt nền tảng, principal, operation, thời gian giữ và mục tiêu khôi phục trước khi dùng làm gate chính thức.

## 17. Kịch bản chấp nhận minh họa

### 17.1. Workload được dùng khóa nhưng không được lấy vật liệu

```text
Given:
  Khóa thử có profile không xuất vật liệu cho ứng dụng.
  Workload A chỉ được operation ký trên đúng khóa và phạm vi đã cấp.

When:
  A thực hiện thao tác hợp lệ và thử các đường export thuộc khả năng nền tảng.

Then:
  Operation hợp lệ hoạt động theo profile.
  A không nhận raw private key qua các đường ngoài chính sách.
  Không suy từ quyền ký ra quyền quản trị hoặc backup.
```

### 17.2. Lấy bản lưu không đồng nghĩa mở được khóa

```text
Given:
  Có bản keystore hoặc wrapped key thử theo mô hình được đánh giá.
  Principal B được đọc bản lưu nhưng không có credential/quyền mở tương ứng.

When:
  B truy cập trong môi trường kiểm chứng được cấp.

Then:
  Không khôi phục được vật liệu rõ qua ranh giới đang đánh giá.
  Vật liệu mở không nằm kèm bản lưu với cùng quyền ngoài chính sách.
  Báo cáo nêu đúng cơ chế và giả định của phép thử.
```

### 17.3. Key reference ngoài phạm vi

```text
Given:
  Request chỉ được thao tác với tài nguyên của tenant A.
  Một key reference của tenant B hoặc môi trường khác được cung cấp.

When:
  Hệ thống giải quyết khóa cho tác vụ.

Then:
  Reference không tự làm phát sinh quyền sử dụng.
  Không tải file, URL hoặc provider tùy ý từ giá trị đó.
  Không thực hiện phép toán bằng khóa ngoài phạm vi đã cấp.
```

### 17.4. Mất truy cập kho lúc vận hành

```text
Given:
  Tác vụ cần dùng khóa theo profile đã chọn.
  Không có vật liệu/khả năng cache còn hợp lệ để hoàn tất tác vụ.

When:
  Kho hoặc provider không đáp ứng yêu cầu.

Then:
  Chức năng phụ thuộc thất bại theo hợp đồng khả dụng.
  Không dùng khóa mặc định hoặc tự tạo một khóa thay thế không tương thích.
  Response và log không công khai credential hay vật liệu khóa.
```

### 17.5. Phục hồi trong môi trường dự phòng

```text
Given:
  Có dữ liệu thử, bản bảo vệ khóa và runbook phù hợp.
  Môi trường đích được cấp quyền đúng phạm vi.

When:
  Thực hiện quy trình phục hồi đã định.

Then:
  Tác vụ được khôi phục mà không tạo raw key ngoài cơ chế đã phê duyệt.
  Những phụ thuộc credential, trust và provider đều được xác nhận.
  Báo cáo không chứa vật liệu thật và ghi rõ thời gian phục hồi đạt được.
```

## 18. Những loại bằng chứng cần kết hợp

| Bằng chứng | Điều có thể xác nhận | Giới hạn |
| --- | --- | --- |
| Cấu hình key storage | Mô hình và policy được khai báo | Chưa chứng minh mọi đường dùng đều đi qua nó |
| Metadata về thuộc tính khóa | Profile của đối tượng ở nền tảng | Cần xét cả quyền thay thuộc tính, export và backup |
| Thao tác hợp lệ thành công | Ứng dụng có khả năng dùng theo kịch bản | Chưa chứng minh quyền không hợp lệ bị chặn |
| Thử quyền âm theo principal–operation | Những đường ngoài policy được từ chối | Phải bao phủ các quyền gián tiếp trong phạm vi |
| Kiểm tra artifact và kênh quan sát | Không có vật liệu thử rò theo các đường đã xét | Không tự chứng minh không còn bất kỳ bản sao nào khác |
| Diễn tập phục hồi | Bản lưu và phụ thuộc thử có thể khôi phục | Không thay cho kiểm kê mọi phiên bản/retention cần hỗ trợ |
| Audit operation và thay đổi quyền | Có thể đối chiếu sự kiện trong phạm vi nền tảng | Raw key đã xuất có thể được dùng ngoài nguồn audit đó |

Không dùng ảnh chụp một entry trong giao diện vault làm toàn bộ bằng chứng. Cũng không in byte khóa ra báo cáo để chứng minh ứng dụng đã đọc đúng; có thể kiểm tra một phép toán trên dữ liệu tổng hợp cùng định danh phù hợp.

Các phép thử ảnh hưởng khả năng khôi phục, như hủy khóa hoặc thay policy quan trọng, cần dùng tài nguyên và vật liệu thử trong môi trường được phép. Không thực hiện thao tác khó phục hồi trên dữ liệu thật chỉ để hoàn thiện bằng chứng.

## 19. Duy trì yêu cầu theo vòng đời hệ thống

Khi thêm một workload, một người quản trị hoặc một đường backup, nhóm cần xem lại ai có thể lấy, sử dụng và thay đổi khóa. Khi đổi provider, JDK hoặc định dạng keystore, cần xác nhận các thuộc tính bảo vệ và khả năng mở dữ liệu còn thuộc retention.

Khi thêm cache hoặc công cụ chẩn đoán, inventory vật liệu khóa cần phản ánh các bản sao mới. Khi bàn giao dịch vụ, owner của khóa, credential bootstrap, trust configuration và runbook phục hồi phải được bàn giao cùng nhau.

Thiết kế key storage đạt mục tiêu khi vật liệu và quyền sử dụng khóa được giữ trong ranh giới đã xác định, những bản sao có owner rõ và phục hồi được kiểm chứng mà không phá ranh giới đó. Nơi lưu, danh tính mở kho, policy phép toán, bộ nhớ runtime và quy trình vận hành phải cùng tạo thành yêu cầu; một tên công cụ không thay thế được toàn bộ thiết kế.
