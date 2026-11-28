# PAM với HSM

## 1. Mục tiêu và bối cảnh

Một hệ thống quản lý truy cập đặc quyền (Privileged Access Management — PAM) thường giữ những bí mật có giá trị rất cao: mật khẩu quản trị, credential của service account, khóa SSH hoặc token phục vụ tự động hóa. Nếu kẻ tấn công lấy được bản sao cơ sở dữ liệu vault cùng vật liệu khóa đủ để giải mã, phạm vi ảnh hưởng có thể lan sang nhiều hệ thống khác.

Hardware Security Module (HSM) cung cấp một ranh giới chuyên dụng để tạo, lưu giữ và sử dụng khóa mật mã. Khi tích hợp phù hợp, PAM có thể nhờ HSM bảo vệ một số khóa quan trọng thay vì giữ mọi vật liệu khóa trong cấu hình, ổ đĩa hay bộ nhớ lâu dài của máy chủ PAM.

Tuy nhiên, việc đặt khóa trong HSM không thay thế kiểm soát truy cập đặc quyền. PAM vẫn phải quản lý danh tính, phê duyệt, thời hạn truy cập, luân chuyển credential và bằng chứng kiểm toán. HSM bảo vệ thao tác mật mã; PAM quyết định ai được làm gì, với tài nguyên nào và trong hoàn cảnh nào.

Sau bài học, người học cần giải thích được:

- PAM và HSM bảo vệ những đối tượng khác nhau như thế nào.
- Cách dùng envelope encryption để bảo vệ credential trong vault.
- Vì sao khóa không thể xuất ra vẫn có thể bị lạm dụng.
- Cách tách quyền quản trị PAM, quản trị HSM và quản lý vật liệu khôi phục.
- Cách thiết kế rotation, dự phòng, audit và phản ứng khi HSM không khả dụng.

Bài học dùng một kiến trúc minh họa trung lập với sản phẩm. Cơ chế đăng nhập, quyền trên từng khóa, giao thức và khả năng sao lưu thực tế phải được đối chiếu với HSM và PAM được triển khai.

## 2. Phân biệt ba loại đối tượng cần bảo vệ

Trước khi chọn cách tích hợp, cần phân biệt credential đích, khóa mã hóa vault và credential cho phép PAM sử dụng HSM.

| Đối tượng | Ví dụ | Vai trò |
| --- | --- | --- |
| Credential của hệ thống đích | Mật khẩu DBA, khóa SSH, mật khẩu service account | Cho phép truy cập hoặc thực hiện tác vụ trên hệ thống đích |
| Khóa bảo vệ dữ liệu của vault | Data Encryption Key — DEK | Mã hóa nội dung credential được lưu trong vault |
| Khóa bảo vệ DEK | Key Encryption Key — KEK | Bọc hoặc mở bọc DEK; có thể được giữ trong HSM |
| Danh tính truy cập HSM | Chứng thư, credential ứng dụng, quyền trên partition | Cho phép thành phần PAM gọi các thao tác HSM được cấp quyền |
| Vật liệu quản trị và khôi phục | Thẻ, share, thiết bị hoặc credential theo thiết kế HSM | Quản trị, phục hồi hoặc kích hoạt thao tác nhạy cảm |

Credential của cơ sở dữ liệu không tự trở thành khóa HSM chỉ vì PAM sử dụng HSM. Trong mô hình phổ biến, credential vẫn là dữ liệu của vault; HSM bảo vệ khóa dùng để giải mã dữ liệu đó.

Tương tự, credential đăng nhập vào HSM không phải credential quản trị hệ thống đích. Hai nhóm cần owner, vòng đời và chính sách thu hồi riêng.

Một lỗi thiết kế thường gặp là bảo vệ KEK rất chặt nhưng lưu credential ứng dụng HSM trong một file mà mọi quản trị viên PAM đều đọc được. Trong trường hợp đó, khả năng xuất KEK có thể đã bị chặn, nhưng khả năng sử dụng KEK để mở bọc dữ liệu vẫn bị lạm dụng.

## 3. HSM bổ sung điều gì cho PAM?

### 3.1. Ranh giới bảo vệ khóa

HSM có thể được cấu hình để khóa được tạo và sử dụng bên trong ranh giới của thiết bị, đồng thời hạn chế hoặc cấm xuất khóa dưới dạng rõ. Các thuộc tính này phải được cấu hình và kiểm tra cho từng loại khóa; không nên suy ra chỉ từ việc “khóa nằm trong HSM”.

Lợi ích chính là giảm khả năng sao chép trực tiếp vật liệu khóa từ máy chủ ứng dụng, bản sao cơ sở dữ liệu hoặc bản sao lưu thông thường.

Điều đó khác với việc bảo đảm rằng không ai có thể yêu cầu HSM thực hiện giải mã. Một danh tính hợp lệ nhưng bị chiếm đoạt vẫn có thể gọi các thao tác mà nó được cấp quyền.

### 3.2. Kiểm soát thao tác và phân vai

Tùy khả năng của hệ thống, HSM có thể áp dụng vai trò quản trị, quyền sử dụng khóa, phạm vi partition hoặc cơ chế nhiều người cùng tham gia một số thao tác.

Cần kiểm tra cụ thể:

- Ai được tạo, nhập, hủy, sao lưu hoặc phục hồi khóa?
- Ai được sử dụng khóa để mã hóa, giải mã, bọc hoặc mở bọc?
- Quyền áp dụng ở cấp thiết bị, partition, tài khoản hay từng đối tượng khóa?
- Thao tác nào thực sự cần nhiều người và thao tác nào vẫn được một ứng dụng thực hiện tự động?
- Log nào được tạo cho mỗi nhóm thao tác?

Không được giả định mọi HSM đều có quyền chi tiết cho từng khóa hoặc mọi thao tác giải mã đều có dual control.

### 3.3. HSM không cung cấp toàn bộ chính sách PAM

HSM không mặc nhiên biết ticket thay đổi, phê duyệt của quản lý, thời gian JIT hay mục đích phiên quản trị.

Nếu PAM đã cho phép một request không hợp lệ đi tới thành phần giải mã, HSM thường chỉ nhìn thấy một ứng dụng đang gọi thao tác mật mã bằng danh tính được phép.

Vì vậy, các kiểm soát như least privilege, JIT/JEA, kiểm tra phê duyệt và giám sát phiên vẫn phải được thực thi ở PAM và các lớp liên quan.

## 4. Mô hình đe dọa và giới hạn bảo vệ

Không thể đánh giá tích hợp HSM chỉ bằng câu hỏi “khóa có nằm trong phần cứng hay không”. Cần bắt đầu từ hành vi của đối tượng tấn công.

| Tình huống | HSM có thể hỗ trợ | Kiểm soát vẫn cần |
| --- | --- | --- |
| Mất bản sao cơ sở dữ liệu vault | Hạn chế giải mã offline nếu bản sao không kèm quyền hoặc vật liệu mở khóa cần thiết | Bảo vệ backup, metadata, khóa và các bản sao ngoài vault |
| Đọc được ổ đĩa máy chủ PAM | Giảm khả năng lấy KEK dạng rõ nếu KEK được giữ đúng trong HSM | Bảo vệ credential ứng dụng, cấu hình và quyền truy cập HSM |
| Chiếm quyền runtime PAM | Giảm việc xuất KEK, nhưng không ngăn mọi yêu cầu giải mã bằng danh tính PAM | Hạn quyền, phân đoạn mạng, giám sát, cô lập node, kiểm soát ứng dụng |
| Lạm dụng quyền quản trị | Có thể phân vai và yêu cầu nhiều người cho một số thao tác | Phân tách nhiệm vụ, review quyền và bằng chứng độc lập |
| Làm HSM không khả dụng | Không phải lợi ích bảo mật tự động; vault có thể bị ngừng phục vụ | Dự phòng, capacity planning, diễn tập phục hồi và fail closed |

Ba kết luận quan trọng:

1. Không xuất được khóa không đồng nghĩa không sử dụng được khóa trái phép.
2. Bản mã an toàn khi lưu trữ không đồng nghĩa plaintext an toàn trong quá trình sử dụng.
3. HSM làm tăng độ chặt của bảo vệ khóa, đồng thời bổ sung một phụ thuộc quan trọng về tính sẵn sàng.

Trong PAM, nhiều thao tác cần plaintext hoặc một dạng credential có thể sử dụng được ở một thời điểm nào đó. HSM không loại bỏ việc bảo vệ bộ nhớ, connector, log và đường truyền tại thời điểm ấy.

## 5. Kiến trúc minh họa: envelope encryption cho vault

Envelope encryption tách khóa mã hóa dữ liệu khỏi khóa bảo vệ khóa.

- DEK mã hóa một secret hoặc một nhóm dữ liệu theo thiết kế.
- KEK bảo vệ DEK.
- Vault lưu bản mã secret, DEK đã được bọc và metadata cần thiết.
- Trong mô hình của bài học, KEK được tạo và giữ trong HSM theo chính sách không xuất dạng rõ.

Sơ đồ quan hệ:

~~~text
Người dùng / workload
          |
          v
PAM: xác thực, phê duyệt, JIT, kiểm tra quyền
          |
          v
Thành phần vault / dịch vụ mật mã
          |                          |
          | đọc hoặc ghi             | xác thực bằng danh tính ứng dụng
          v                          v
Kho dữ liệu vault                  HSM
- secret ciphertext               - KEK và phiên bản khóa
- wrapped DEK                     - chính sách sử dụng khóa
- metadata mật mã                 - thao tác wrap / unwrap được phép
          |
          v
Connector hoặc phiên PAM tới hệ thống đích
~~~

Đây là sơ đồ chức năng, không bắt buộc mỗi hộp phải là một máy chủ riêng.

### 5.1. Luồng ghi một credential

Một luồng đơn giản có thể gồm:

1. PAM kiểm tra quyền thêm hoặc thay đổi credential.
2. Thành phần mật mã tạo DEK bằng nguồn ngẫu nhiên mật mã phù hợp.
3. Credential được mã hóa bằng cơ chế mã hóa có xác thực.
4. DEK được bọc bằng KEK trong HSM qua cơ chế được hỗ trợ.
5. Vault lưu bản mã, wrapped DEK và metadata liên quan trong một giao dịch nhất quán.
6. Thành phần xử lý giải phóng plaintext và vật liệu khóa tạm sau khi hoàn tất.

Trong mô hình này, DEK có thể tồn tại tạm thời trong bộ nhớ ứng dụng. Nếu yêu cầu bảo mật không cho phép điều đó, cần một kiến trúc khác có khả năng thực hiện các thao tác cần thiết bên trong ranh giới mật mã. Không thể gọi mô hình trên là “mọi khóa luôn nằm trong HSM”.

### 5.2. Luồng sử dụng credential

~~~text
Request hợp lệ
  -> PAM kiểm tra identity + policy + approval + thời hạn
  -> đọc bản mã và metadata của secret
  -> kiểm tra key reference thuộc phạm vi được phép
  -> yêu cầu HSM mở bọc DEK
  -> giải mã và kiểm tra tính toàn vẹn của secret
  -> sử dụng qua connector hoặc cấp phát theo chính sách
  -> kết thúc sử dụng, thu hồi hoặc rotate khi cần
  -> ghi bằng chứng đã loại bỏ dữ liệu nhạy cảm
~~~

Nếu bước xác thực bản mã thất bại, không được tiếp tục sử dụng phần dữ liệu đã giải mã hoặc thử “đọc tạm” dưới dạng không xác thực.

HSM không nên được dùng như một dịch vụ giải mã tùy ý nhận mọi key ID hoặc ciphertext do client gửi lên. Thành phần PAM phải tự xác định bản ghi hợp lệ và phạm vi khóa được phép sử dụng.

### 5.3. HSM không nhất thiết xử lý toàn bộ payload

Gọi HSM cho mọi byte của dữ liệu vault có thể gây giới hạn hiệu năng không cần thiết. Envelope encryption cho phép giữ thao tác bảo vệ khóa trong HSM, còn dữ liệu được xử lý bởi thành phần ứng dụng phù hợp.

Đổi lại, phải bảo vệ vòng đời DEK trong bộ nhớ ứng dụng. Quyết định này cần được ghi rõ trong mô hình đe dọa, thay vì mô tả chung chung rằng “vault đã mã hóa bằng HSM”.

## 6. Thiết kế metadata và ràng buộc ngữ cảnh

Một bản ghi mật mã cần đủ thông tin để xác định cách giải mã đúng, nhưng không được chứa bí mật ở dạng rõ.

Ví dụ khái niệm:

~~~yaml
record_id: cred-example-0042
tenant_id: tenant-example
secret_version: 7
crypto_format_version: 1
encryption_profile: approved-aead-profile
key_reference: pam-prod-vault-kek
key_version: 12
wrapped_dek: <opaque-bytes>
nonce: <nonce-or-iv-required-by-profile>
ciphertext: <opaque-bytes>
authentication_tag: <tag-if-stored-separately>
~~~

Đây là cấu trúc minh họa, không phải schema hay cấu hình có thể đưa trực tiếp vào sản phẩm.

Những điều phải xác định trong thiết kế:

- Trường nào được xác thực cùng bản mã?
- Cách mã hóa metadata có nhất quán, không mơ hồ không?
- Có thể lấy wrapped DEK của bản ghi A gắn vào bản ghi B không?
- Có thể thay key reference để ép ứng dụng gọi một khóa khác không?
- Làm thế nào chống khôi phục một phiên bản secret cũ ngoài chính sách?

Mã hóa có xác thực và Additional Authenticated Data (AAD) có thể ràng buộc bản mã với ngữ cảnh như tenant, record ID và phiên bản. AAD cần tái tạo ổn định; nó được xác thực nhưng không được giữ bí mật bởi chính cơ chế AAD.

Không nên tùy tiện đưa mọi metadata có thể thay đổi vào AAD. Nếu key version hoặc wrapped DEK bị thay đổi trong quy trình rewrap, thiết kế phải xác định phần nào được ràng buộc bằng cơ chế nào và cập nhật tính toàn vẹn ra sao. Thay một trường đã được xác thực có thể đòi hỏi tạo lại dữ liệu xác thực, không chỉ sửa YAML hoặc database.

Mã hóa có xác thực cũng không tự giải quyết rollback: một bản mã cũ nhưng hợp lệ vẫn có thể vượt qua kiểm tra mật mã. Chống rollback cần trạng thái phiên bản đáng tin cậy và chính sách kiểm tra riêng.

## 7. Chọn cách kết nối PAM với HSM

Có thể gặp các kiểu tích hợp sau:

| Kiểu tích hợp | Ý nghĩa | Điểm cần kiểm tra |
| --- | --- | --- |
| Provider hoặc thư viện mật mã | PAM dùng giao diện như PKCS#11 hoặc provider phù hợp với runtime | Cơ chế được hỗ trợ, quản lý session, tương thích và xử lý lỗi |
| Dịch vụ mật mã trung gian | PAM gọi một dịch vụ chịu trách nhiệm truy cập HSM | Dịch vụ trở thành ranh giới tin cậy; cần authentication, authorization và audit |
| Dịch vụ quản lý khóa có HSM phía dưới | PAM dùng API quản lý khóa của một dịch vụ | Ranh giới HSM, quyền sử dụng, quyền quản trị, backup và trách nhiệm các bên |

Việc một dịch vụ dùng HSM ở phía dưới không có nghĩa PAM trực tiếp quản lý HSM đó. Cần phân biệt quyền trên API dịch vụ với quyền trên thiết bị và khóa thực tế.

Các giao diện như PKCS#11 mô tả cách ứng dụng làm việc với đối tượng và thao tác mật mã; chúng không tự cung cấp chính sách phê duyệt của PAM. Tương tự, khả năng hỗ trợ một giao thức không có nghĩa sản phẩm tự hỗ trợ đầy đủ mọi luồng tích hợp mong muốn.

Khi đánh giá một kết nối cụ thể, cần trả lời:

1. PAM xác thực HSM hoặc dịch vụ mật mã như thế nào?
2. HSM hoặc dịch vụ xác thực thành phần PAM như thế nào?
3. Danh tính ấy được phép dùng khóa nào và thực hiện thao tác nào?
4. Làm thế nào thu hồi quyền của một node PAM mà các node khác vẫn hoạt động?
5. Lỗi kết nối, lỗi xác thực và lỗi mật mã được phân biệt ra sao?
6. Khi cấu hình sai, hệ thống có dừng an toàn hay tự chuyển sang một đường giải mã khác?

Với HSM kết nối qua mạng, phải bảo vệ kênh truyền theo cơ chế tích hợp được hỗ trợ. Nếu chỉ dùng provider cục bộ, vẫn phải kiểm soát truy cập process, thư viện, thiết bị và credential liên quan.

## 8. Danh tính ứng dụng và bài toán bootstrap

PAM cần một cách nhận diện hợp lệ trước khi có thể yêu cầu HSM mở bọc khóa. Không thể giải quyết vòng lặp khởi động bằng cách lưu credential HSM duy nhất bên trong chính vault cần credential ấy để mở.

Một thiết kế bootstrap cần xác định rõ:

- Danh tính nào được cấp cho mỗi node hoặc workload PAM.
- Cách cấp danh tính lần đầu và xác minh node hợp lệ.
- Nơi lưu hoặc cơ chế cung cấp credential khởi động.
- Quyền tối thiểu của danh tính sau khi kết nối.
- Cách thay thế, thu hồi và phục hồi danh tính khi node bị mất.

Tùy khả năng của môi trường, có thể sử dụng danh tính workload, chứng thư được cấp qua quy trình tin cậy hoặc một cơ chế cấp phát credential được bảo vệ bên ngoài vault. Không có một phương án duy nhất đúng cho mọi HSM.

Những cách triển khai cần tránh gồm dùng một credential chung không thể truy vết cho toàn bộ cụm, đặt credential trong repository, truyền qua dòng lệnh dễ bị quan sát hoặc để nó xuất hiện trong log khởi động.

Phân biệt hai sự kiện:

- Rotate credential truy cập HSM: thay cách một ứng dụng chứng minh danh tính hoặc quyền truy cập.
- Rotate KEK: thay khóa bảo vệ DEK của vault.

Hai sự kiện này có thể phối hợp trong một kế hoạch nhưng không đồng nghĩa. Rotate một credential HSM cũng không tự vô hiệu hóa những phiên đang hoạt động; cần kiểm tra hành vi thực tế và kết thúc phiên hoặc cô lập node khi cần.

## 9. Phân tách nhiệm vụ và dual control

Một người có thể quản trị hạ tầng PAM nhưng không nên mặc nhiên có khả năng mở mọi secret, thay policy và xóa dấu vết sử dụng.

Ma trận vai trò minh họa:

| Vai trò | Trách nhiệm | Quyền cần giới hạn |
| --- | --- | --- |
| PAM policy administrator | Cấu hình luồng phê duyệt và phạm vi truy cập | Không tự phê duyệt hoặc cấp quyền đọc toàn bộ vault |
| PAM runtime identity | Thực hiện thao tác mật mã để phục vụ request hợp lệ | Không quản trị hoặc hủy KEK |
| HSM administrator | Quản trị cấu hình, tài khoản và nền tảng HSM | Không mặc nhiên có quyền đọc credential PAM |
| Key custodian | Tham gia các thao tác vòng đời khóa được chỉ định | Không đồng thời giữ toàn bộ vật liệu khôi phục và quyền vận hành |
| Auditor | Đối chiếu policy, thao tác khóa và hoạt động PAM | Không có quyền giải mã hoặc thay đổi bằng chứng |

Đây là mục tiêu phân vai. Cần kiểm tra sản phẩm có thực thi đúng mức phân tách ấy hay chỉ tạo ra các tài khoản khác tên nhưng quyền thực tế vẫn chồng lấn.

Dual control là yêu cầu hai người hoặc nhiều người cùng tham gia một thao tác. Một cơ chế quorum M-of-N là một cách triển khai, trong đó cần tối thiểu M phần trong tổng số N phần để thực hiện thao tác được thiết kế.

Không được suy diễn rằng có quorum khi khôi phục khóa thì mọi request giải mã runtime đều cần quorum. Cũng không được mặc nhiên đặt con người vào mỗi lần unwrap; điều đó có thể làm hệ thống vận hành không khả thi.

Các điểm thường đáng xem xét áp dụng nhiều người gồm khởi tạo quyền quản trị gốc, phục hồi vật liệu khóa, hủy khóa quan trọng hoặc thay đổi chính sách có tác động diện rộng. Phạm vi thật sự phải được xác nhận và diễn tập.

## 10. Vòng đời khóa và credential

### 10.1. Tạo và đưa khóa vào sử dụng

Mỗi KEK cần có owner, mục đích, môi trường, phạm vi dữ liệu, cơ chế được phép, chính sách xuất khóa và kế hoạch phục hồi.

Cần tránh dùng một khóa chung cho production, test và development. Tách môi trường giúp hạn chế tác động của credential bị lộ, lỗi cấu hình và thao tác xóa nhầm.

Trước khi kích hoạt khóa cho dữ liệu thật:

1. Tạo khóa theo quy trình được kiểm soát.
2. Ghi nhận định danh và phiên bản ổn định.
3. Kiểm tra quyền của danh tính runtime và các vai trò quản trị.
4. Thử wrap, unwrap và kiểm tra sai quyền trên dữ liệu thử.
5. Xác minh khả năng dự phòng hoặc khôi phục theo thiết kế.
6. Chỉ sau đó mới cho phép tạo bản ghi production bằng khóa.

### 10.2. Rotate KEK

Trong envelope encryption, rotate KEK thường có thể thực hiện bằng rewrap DEK. Điều đó không nhất thiết yêu cầu giải mã và mã hóa lại toàn bộ credential, nếu định dạng mật mã và cơ chế được hỗ trợ cho phép.

Một quy trình có thể gồm:

1. Tạo KEK phiên bản mới.
2. Cho bản ghi mới sử dụng phiên bản mới.
3. Giữ khả năng đọc phiên bản cũ trong giai đoạn chuyển tiếp được phê duyệt.
4. Rewrap từng DEK sang KEK mới theo lô có kiểm soát.
5. Kiểm tra tính toàn vẹn và khả năng đọc sau chuyển đổi.
6. Cập nhật metadata nhất quán, có checkpoint và khả năng thử lại an toàn.
7. Kiểm kê dữ liệu hiện hành, lịch sử và backup còn phụ thuộc khóa cũ.
8. Ngừng sử dụng hoặc hủy khóa cũ theo chính sách đã xác minh.

Rewrap có thể được hỗ trợ trực tiếp trong ranh giới mật mã hoặc cần một luồng xử lý khác. Nếu DEK phải ra bộ nhớ ứng dụng, phải ghi nhận sự khác biệt đó trong thiết kế bảo vệ.

Không được xóa wrapped DEK cũ trước khi bản ghi mới được ghi thành công và xác minh. Với dữ liệu có cập nhật đồng thời, cần kiểm soát phiên bản hoặc giao dịch phù hợp để không ghi đè một secret vừa được rotate.

### 10.3. Rotate DEK và rotate credential đích

Ba thao tác khác nhau cần được quản lý riêng:

| Thao tác | Dữ liệu nào thay đổi? | Không tự bảo đảm |
| --- | --- | --- |
| Rotate KEK | Khóa bọc và có thể wrapped DEK | Credential đích đã đổi |
| Rotate DEK | Khóa mã hóa dữ liệu và bản mã liên quan | Credential đích đã đổi |
| Rotate credential đích | Mật khẩu, token hoặc khóa được hệ thống đích chấp nhận | Khóa bảo vệ vault đã đổi |

Nếu mật khẩu quản trị đã bị lộ, chỉ rewrap DEK không làm mật khẩu đó mất hiệu lực. Cần đổi credential tại hệ thống đích và xử lý phiên, token hoặc cơ chế truy cập liên quan theo tình huống.

### 10.4. Ngừng sử dụng và hủy khóa

Hủy khóa không thể khôi phục có thể khiến dữ liệu còn phụ thuộc khóa ấy mất khả năng đọc. Trước khi hủy, phải xác minh phụ thuộc của dữ liệu hiện hành, bản lịch sử, bản sao lưu và môi trường phục hồi.

Không nên tuyên bố rằng hủy một khóa đã xóa toàn bộ dữ liệu nếu vẫn còn bản sao khóa, plaintext, export hoặc đường giải mã khác. Hiệu quả xóa bằng mật mã phụ thuộc vào toàn bộ vòng đời dữ liệu và khóa.

## 11. Tính sẵn sàng, hiệu năng và bộ nhớ đệm

### 11.1. HSM là phụ thuộc trên đường phục vụ

Nếu unwrap DEK nằm trong luồng truy cập credential, lỗi HSM có thể làm gián đoạn phiên quản trị, ứng dụng tự động hóa và quy trình phản ứng sự cố.

Thiết kế cần phân biệt:

- HSM hoặc dịch vụ mật mã không khả dụng.
- Lỗi mạng giữa PAM và HSM.
- Credential ứng dụng hết hạn hoặc bị thu hồi.
- Key reference không tồn tại hoặc không được phép.
- Giới hạn session, hàng đợi hoặc năng lực xử lý.
- Bản mã hoặc metadata không hợp lệ.

Không phải lỗi nào cũng nên retry. Lỗi xác thực, sai quyền hoặc thất bại kiểm tra tính toàn vẹn cần xử lý khác với một lỗi mạng tạm thời.

Retry phải có giới hạn và backoff; nếu mọi node cùng retry dồn dập, một lỗi nhỏ có thể trở thành quá tải kéo dài.

### 11.2. Đo hiệu năng bằng luồng thật

Các chỉ số hữu ích gồm độ trễ unwrap, độ trễ truy cập vault đầu cuối, số lỗi theo nhóm nguyên nhân, số session đang dùng và mức hàng đợi.

Không thể lấy thông lượng quảng cáo của HSM làm thông lượng thực tế của PAM. Kết quả còn phụ thuộc cơ chế mật mã, số lần gọi mỗi request, đường truyền, provider, session pooling và hành vi ứng dụng.

Cần kiểm thử cả thời điểm tải tăng mạnh: khởi động đồng thời nhiều node, ứng dụng đồng loạt lấy credential hoặc failover sang tài nguyên dự phòng.

### 11.3. Cache DEK là quyết định về rủi ro

Cache DEK có thể giảm số lần gọi HSM nhưng kéo dài thời gian vật liệu khóa ở bộ nhớ ứng dụng.

Nếu cho phép cache, cần xác định:

- Dữ liệu nào được cache và tối đa bao lâu.
- Phạm vi process, node và tenant.
- Điều kiện xóa cache khi thu hồi quyền hoặc thay đổi phiên bản.
- Hành vi khi node bị cô lập hoặc HSM không khả dụng.
- Mức đảm bảo và giới hạn của runtime đối với việc xóa bộ nhớ.

Trong runtime có garbage collector hoặc nhiều lớp native, không nên hứa rằng mọi bản sao plaintext được xóa tức thời chỉ bằng cách gán biến về rỗng.

Thu hồi quyền truy cập HSM không tự xóa DEK đã cache ở một node bị chiếm đoạt. Phương án xử lý phải bao gồm cô lập hoặc dừng node và cân nhắc thay đổi credential đích theo phạm vi phơi lộ.

## 12. Fail closed và truy cập khẩn cấp

Fail closed nghĩa là hệ thống từ chối thao tác cần mật mã khi không thể thực hiện đúng các điều kiện bắt buộc. Một ví dụ là từ chối giải mã nếu HSM không khả dụng và không có phương án đã được thiết kế, kiểm soát rõ ràng.

Không nên tự động tạo một “khóa dự phòng mềm” trên đĩa để vượt qua lỗi kết nối HSM. Nếu có đường dự phòng, đường đó là một phần của mô hình bảo vệ khóa và phải được đánh giá ngang với đường chính.

Break-glass cần giải quyết cả vấn đề khởi động:

> Khi PAM hoặc HSM đang hỏng, đội vận hành lấy quyền sửa hệ thống từ đâu?

Một cơ chế truy cập khẩn cấp có thể cần nằm ngoài chuỗi phụ thuộc đang hỏng. Thiết kế phải chỉ rõ ai được kích hoạt, cách phê duyệt, thời hạn, nơi ghi bằng chứng và cách thu hồi sau sử dụng.

Truy cập khẩn cấp không nên mặc nhiên cho phép xuất KEK hoặc vô hiệu hóa mọi lớp audit. Tùy kiến trúc, đó có thể là credential phục hồi hệ thống đích được quản lý riêng, thay vì một lối tắt mở toàn bộ vault.

Sau một lần break-glass, phải đối chiếu hoạt động thực tế, đóng quyền khẩn cấp và rotate credential liên quan khi chính sách hoặc mức phơi lộ yêu cầu.

## 13. Sao lưu và khôi phục

Sao lưu cơ sở dữ liệu PAM không bảo đảm có thể phục hồi nếu khóa hoặc quyền truy cập khóa không còn.

Một bộ kế hoạch phục hồi cần bao phủ:

- Dữ liệu vault, bản lịch sử và metadata mật mã.
- Khóa hoặc cơ chế phục hồi khóa theo HSM được sử dụng.
- Quyền, vai trò và chính sách cần để sử dụng khóa.
- Cấu hình kết nối và khả năng khôi phục danh tính ứng dụng.
- Vật liệu cần thiết cho quorum nếu cơ chế đó được áp dụng.
- Phiên bản định dạng và khả năng tương thích của thành phần tích hợp.

Backup HSM không mặc nhiên là export khóa dạng rõ. Tùy thiết kế, vật liệu backup có thể được bảo vệ và chỉ khôi phục trong một phạm vi hoặc với một quy trình nhất định.

Cần phân biệt nhân bản dự phòng với sao lưu: nếu việc hủy hoặc thay đổi sai được đồng bộ tới các thành phần dự phòng, bản sao đồng bộ không nhất thiết giúp quay lại trạng thái trước sự cố.

Một buổi diễn tập khôi phục nên chứng minh được:

1. Khôi phục dữ liệu trong môi trường cô lập.
2. Khôi phục hoặc truy cập đúng khóa và phiên bản cần thiết.
3. Cấp đúng danh tính runtime mà không dùng quyền quản trị quá rộng.
4. Đọc được bản ghi ở nhiều phiên bản khóa.
5. Từ chối bản ghi bị thay đổi hoặc sai quyền.
6. Ghi đủ bằng chứng về người tham gia, thời gian và kết quả.
7. Đo RTO và RPO thực tế theo dữ liệu đã phục hồi.

Không dùng thời gian dự kiến trong tài liệu làm bằng chứng đáp ứng RTO. Khả năng truy cập vật liệu quorum, quy trình cấp lại chứng thư và khả năng tương thích đều có thể kéo dài thời gian phục hồi.

## 14. Audit và liên kết bằng chứng

PAM cần biết request nào được phê duyệt và credential nào được sử dụng. HSM hoặc dịch vụ mật mã cung cấp bằng chứng về thao tác khóa ở mức mà cơ chế audit hỗ trợ.

Hai nguồn dữ liệu nên được liên kết theo chuỗi:

~~~text
Ticket / approval
      -> request PAM
      -> quyết định policy
      -> thao tác vault
      -> thao tác khóa
      -> connector hoặc phiên quản trị
      -> kết thúc và thu hồi / rotation
~~~

Các trường có thể hữu ích:

| Trường | Mục đích |
| --- | --- |
| Thời gian đã đồng bộ | Đối chiếu chuỗi sự kiện |
| Request ID hoặc correlation ID | Liên kết các lớp xử lý khi được hỗ trợ |
| Danh tính người yêu cầu và danh tính runtime | Phân biệt chủ thể nghiệp vụ với ứng dụng gọi HSM |
| Định danh bản ghi và phiên bản secret | Xác định dữ liệu được sử dụng mà không ghi plaintext |
| Key reference, key version, loại thao tác | Xác định phụ thuộc mật mã |
| Kết quả và mã lỗi đã chuẩn hóa | Điều tra thành công, từ chối và lỗi |
| Policy hoặc approval reference | Chứng minh điều kiện cho phép truy cập |

Không phải HSM nào cũng ghi request ID của PAM hoặc audit riêng từng thao tác mật mã. Nếu lớp HSM không hỗ trợ, có thể cần log ở dịch vụ trung gian và đối chiếu bằng danh tính runtime, thời gian, khóa và loại thao tác. Phải mô tả giới hạn quy kết, tránh tuyên bố khả năng truy vết từng secret nếu bằng chứng không đủ.

Không ghi mật khẩu, token, PIN, plaintext DEK, vật liệu khôi phục hoặc nội dung credential vào log. Ngay cả wrapped DEK và bản mã cũng không nên được đưa vào log tùy tiện, vì tạo thêm bản sao dữ liệu nhạy cảm và phụ thuộc lưu trữ.

Các cảnh báo đáng chú ý gồm thao tác mở bọc tăng đột biến ngoài đường gọi bình thường, danh tính runtime mới xuất hiện, thay đổi quyền sử dụng khóa, thử hủy khóa hoặc nhiều lỗi xác thực liên tiếp.

Chỉ số và log phải đủ để điều tra nhưng không làm lộ bí mật trong quá trình xử lý sự cố.

## 15. Ứng phó sự cố

### 15.1. Mất credential ứng dụng truy cập HSM

Trình tự cần xem xét:

1. Xác định danh tính, node, khóa và thao tác có thể bị lạm dụng.
2. Thu hồi hoặc hạn chế danh tính bị lộ, cô lập node khi cần.
3. Xử lý các phiên đang hoạt động và vật liệu đã cache.
4. Đối chiếu log PAM, HSM và hạ tầng trong khoảng thời gian ảnh hưởng.
5. Cấp lại danh tính runtime sạch theo quy trình bootstrap.
6. Rotate credential đích có nguy cơ đã bị giải mã.
7. Đánh giá yêu cầu thay khóa bảo vệ vault theo bằng chứng và mô hình đe dọa.

Chỉ đổi KEK không vô hiệu hóa bản sao plaintext mà đối tượng tấn công đã lấy. Cũng không thể kết luận credential an toàn chỉ vì KEK không bị xuất khỏi HSM.

### 15.2. Hủy nhầm hoặc mất quyền truy cập khóa

Trước hết cần phân biệt khóa thực sự không còn, quyền bị thay đổi, key reference sai hay kết nối lỗi. Các tình huống này có mức độ phục hồi khác nhau.

Dừng các hành động phá hủy tiếp theo, giữ bằng chứng và sử dụng quy trình phục hồi đã diễn tập. Không tạo khóa mới cùng tên rồi kỳ vọng giải mã được dữ liệu của khóa cũ: tên giống nhau không tạo ra cùng vật liệu khóa.

### 15.3. Nghi ngờ lạm dụng quyền quản trị HSM

Cần kiểm tra thay đổi tài khoản, quyền, policy, backup, restore, tạo khóa và hủy khóa trong phạm vi audit có sẵn.

Tách bằng chứng khỏi hệ thống đang bị nghi ngờ, sử dụng vai trò ứng phó độc lập và kiểm tra khả năng tiếp tục tin cậy môi trường. Quyết định thay khóa, phục hồi hay thay nền tảng phải dựa trên phạm vi sự cố, không chỉ dựa vào một thông báo “HSM vẫn hoạt động”.

## 16. Ví dụ triển khai trong doanh nghiệp

Một doanh nghiệp có cụm PAM phục vụ quản trị cơ sở dữ liệu production và cấp credential cho một số workload tự động.

Thiết kế ban đầu lưu vault database và vật liệu mở khóa trên cùng miền quản trị. Mục tiêu tích hợp HSM là giảm nguy cơ giải mã offline khi mất backup và tách quản trị khóa khỏi quản trị ứng dụng.

Phương án minh họa:

- KEK của production được tạo trong phạm vi HSM dành riêng cho production.
- Vault dùng DEK để mã hóa credential; HSM bảo vệ DEK theo mô hình envelope encryption.
- Mỗi node PAM có danh tính có thể thu hồi riêng.
- Danh tính runtime chỉ được dùng các khóa và cơ chế cần thiết.
- Việc thay đổi quyền và phục hồi khóa có người tham gia độc lập với quản trị PAM.
- Backup vault và vật liệu phục hồi khóa được bảo vệ theo quy trình riêng.
- PAM kiểm tra approval trước khi gọi luồng mở bọc và sử dụng credential.
- Thao tác khóa và phiên quản trị được đối chiếu bằng bằng chứng phù hợp.

Một request DBA được phê duyệt trong 30 phút không đồng nghĩa HSM tự cấp quyền 30 phút cho DBA. PAM thực thi thời hạn truy cập, còn danh tính runtime của PAM thực hiện thao tác mật mã cần thiết.

Nếu node PAM bị chiếm quyền, doanh nghiệp thu hồi danh tính node và cô lập node đó. Sau đó phải đánh giá secret đã được giải mã, cache và phiên đang mở; việc thu hồi danh tính HSM chỉ là một phần của ứng phó.

Nếu HSM mất kết nối, PAM từ chối những thao tác không thể thực hiện an toàn, chuyển sang tài nguyên dự phòng theo thiết kế và chỉ sử dụng break-glass qua quy trình được kiểm soát. Không tự động đưa khóa dạng rõ lên node để giữ dịch vụ hoạt động.

## 17. Kiểm thử chấp nhận tích hợp

Các phép thử sau nên thực hiện bằng dữ liệu thử, trong phạm vi được phép và có phương án phục hồi. Đây là kiểm thử thiết kế tích hợp, không phải yêu cầu thực hiện thao tác phá hủy trên production.

| Tình huống kiểm thử | Kết quả cần chứng minh |
| --- | --- |
| Sao chép database mà không cấp quyền dùng HSM | Không đọc được secret bằng bản sao dữ liệu đơn thuần |
| Danh tính runtime gọi thao tác quản trị khóa | Bị từ chối theo quyền đã thiết kế |
| Request PAM thiếu approval hợp lệ | Bị chặn trước khi giải mã credential |
| Node mất quyền dùng HSM | Thao tác mới bị từ chối; hành vi session và cache được ghi nhận |
| HSM không khả dụng | Không có đường fallback ngoài thiết kế; lỗi có giới hạn và cảnh báo |
| Wrapped DEK hoặc bản mã bị sửa | Phát hiện lỗi; không sử dụng plaintext chưa được xác thực |
| Metadata bị thay sang tenant hoặc record khác | Bị ngăn theo thiết kế ràng buộc ngữ cảnh |
| Rewrap bị ngắt giữa chừng | Có thể tiếp tục an toàn, không mất tham chiếu khóa |
| Đọc bản ghi còn dùng KEK cũ | Đọc được trong giai đoạn chuyển tiếp được phê duyệt |
| Restore backup có nhiều phiên bản khóa | Phục hồi và đọc được các bản ghi cần thiết |
| Thu thập log khi lỗi tích hợp | Có bằng chứng nhưng không lộ secret hoặc vật liệu khóa |

Không dùng một phép thử thành công để kết luận toàn bộ mô hình đe dọa đã được giải quyết. Ví dụ, việc bản sao database không giải mã được không chứng minh node runtime bị chiếm quyền cũng không thể đọc credential.

## 18. Những lỗi thiết kế thường gặp

**“Có HSM nên mọi quản trị viên PAM đều có thể được cấp quyền rộng.”**  
HSM không thay thế least privilege. Quản trị viên có thể thay policy, chiếm danh tính runtime hoặc gọi đường giải mã hợp lệ nếu không có phân tách nhiệm vụ.

**“Khóa không xuất được nên không thể mất secret.”**  
Secret vẫn có thể bị giải mã bằng quyền sử dụng khóa hoặc bị lấy ở connector, phiên quản trị và bộ nhớ ứng dụng.

**“Rotate KEK là đã xử lý mật khẩu quản trị bị lộ.”**  
Mật khẩu cũ vẫn có thể hoạt động ở hệ thống đích. Cần rotate đúng credential đích và xử lý phiên liên quan.

**“Chỉ cần backup database vault.”**  
Backup không đọc được nếu mất khóa, phiên bản, quyền hoặc khả năng phục hồi HSM tương ứng.

**“Bật cache DEK để mọi thứ luôn chạy khi HSM lỗi.”**  
Cache làm thay đổi thời gian phơi lộ và hiệu lực thu hồi. Cần chính sách rõ ràng thay vì dùng cache như lối thoát mặc định.

**“HSM audit chứng minh ai đã xem từng mật khẩu.”**  
HSM có thể chỉ thấy danh tính ứng dụng và thao tác khóa. Việc quy kết tới người dùng cần bằng chứng PAM và khả năng liên kết đã xác minh.

**“Một HSM dùng chung nghĩa là đã tách mọi môi trường.”**  
Tách biệt phụ thuộc vào khóa, partition, danh tính, quyền và cách quản trị thực tế. Cùng thiết bị không tự tạo ra cách ly đầy đủ.

**“Đổi tên khóa hoặc tạo khóa cùng tên sẽ phục hồi dữ liệu.”**  
Khả năng giải mã phụ thuộc vật liệu khóa đúng và metadata đúng, không chỉ phụ thuộc tên.

## 19. Bài tập tự kiểm tra

### Tình huống 1: Mất backup

Đội bảo mật phát hiện một backup vault database bị sao chép ra ngoài. KEK nằm trong HSM và không được xuất dạng rõ.

Hãy xác định những điều cần kiểm tra trước khi kết luận dữ liệu chưa bị lộ.

Gợi ý: backup có kèm credential ứng dụng, DEK dạng rõ, dữ liệu export, cấu hình hoặc đường truy cập HSM không? Có log sử dụng khóa bất thường không? Có bản sao plaintext từ pipeline backup không?

### Tình huống 2: Runtime bị chiếm quyền

Một node PAM đã bị chiếm quyền trong hai giờ. Danh tính node có quyền unwrap DEK nhưng không có quyền export KEK.

Hãy giải thích vì sao phạm vi ảnh hưởng không thể chỉ được mô tả là “khóa vẫn an toàn”.

Gợi ý: xét quyền gọi giải mã, secret đã sử dụng, cache, phiên còn mở, log và khả năng lạm dụng credential tại hệ thống đích.

### Tình huống 3: Rotation bị gián đoạn

Một tác vụ rewrap đã hoàn thành một nửa số bản ghi thì dừng. Bản ghi mới dùng KEK phiên bản mới, một số bản ghi cũ vẫn dùng phiên bản trước.

Hãy mô tả dữ liệu cần lưu để tác vụ tiếp tục mà không làm mất khả năng đọc.

Gợi ý: định danh và phiên bản khóa, trạng thái từng bản ghi, kiểm soát cập nhật đồng thời, tính toàn vẹn metadata và cơ chế thử lại có kiểm soát.

### Tình huống 4: HSM lỗi trong sự cố production

HSM không khả dụng đúng lúc đội vận hành cần quyền quản trị để sửa hệ thống.

Hãy thiết kế một chuỗi phục hồi không phụ thuộc vòng tròn vào vault đang bị khóa.

Gợi ý: xác định đường dự phòng, quyền khẩn cấp, người phê duyệt, vật liệu khôi phục, bằng chứng và các credential cần thay sau sử dụng.

## 20. Điểm cần nhớ

PAM quản lý việc sử dụng quyền đặc biệt; HSM bảo vệ khóa và thực hiện thao tác mật mã trong ranh giới được thiết kế. Giá trị của tích hợp nằm ở cách hai lớp phối hợp, không chỉ ở việc bổ sung một thiết bị.

Một thiết kế tốt phải mô tả rõ dữ liệu nào được mã hóa, khóa nào nằm trong HSM, DEK có ra bộ nhớ ứng dụng hay không, danh tính nào được sử dụng khóa và bằng chứng nào chứng minh các thao tác.

Khả năng phục hồi, hiệu lực thu hồi, luân chuyển khóa và luân chuyển credential đích phải được kiểm chứng riêng. Khóa được bảo vệ tốt chỉ phát huy tác dụng khi luồng truy cập, vận hành và ứng phó của PAM cũng được kiểm soát đầy đủ.
