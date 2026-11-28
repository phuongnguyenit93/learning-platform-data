# NIST SP 800-57

Quản lý khóa mật mã là một chương trình kỹ thuật và vận hành bao gồm việc tạo, phân phối, lưu trữ, sử dụng, bảo vệ, xoay vòng, thu hồi, lưu trữ lịch sử và hủy khóa. Một thuật toán mạnh không thể bù cho việc khóa bị tạo sai, cấp quyền quá rộng, lưu trữ không an toàn hoặc bị hủy trước khi dữ liệu phụ thuộc được xử lý. NIST SP 800-57, *Recommendation for Key Management*, cung cấp khuyến nghị để thiết kế và vận hành chương trình quản lý khóa có kiểm soát.

Tài liệu này giúp tổ chức trả lời các câu hỏi quan trọng: loại khóa nào đang được sử dụng, khóa phục vụ mục đích gì, ai chịu trách nhiệm, khóa được bảo vệ trong suốt vòng đời ra sao, thời gian sử dụng hợp lý là bao lâu và cần bằng chứng nào để chứng minh các quy trình đó đang hoạt động.

## 1. NIST SP 800-57 là gì?

NIST SP 800-57 là bộ khuyến nghị của National Institute of Standards and Technology (NIST) về quản lý khóa mật mã. Tài liệu tập trung vào các nguyên tắc, thực hành và hướng dẫn cần thiết để bảo vệ keying material trong các hệ thống dùng mật mã.

Key management không chỉ là cất một chuỗi khóa vào KMS. Nó bao gồm toàn bộ hoạt động liên quan đến khóa và thông tin cần thiết để sử dụng khóa đúng cách: xác định mục đích, tạo khóa, phân phối, kích hoạt, cấp quyền, theo dõi sử dụng, thay thế, xử lý compromise, lưu trữ khóa lịch sử và hủy khi không còn cần thiết.

NIST SP 800-57 có ba phần với các góc nhìn bổ sung:

| Phần | Trọng tâm | Câu hỏi chính |
|---|---|---|
| Part 1 – General | Nguyên tắc quản lý khóa, thuật ngữ, loại khóa, vòng đời, cryptoperiod, bảo vệ và xử lý sự cố | Một khóa cần được quản lý như thế nào? |
| Part 2 – Best Practices for Key Management Organization | Tổ chức, vai trò, chính sách, trách nhiệm và quy trình vận hành quản lý khóa | Ai chịu trách nhiệm và tổ chức chương trình quản lý khóa ra sao? |
| Part 3 – Application-Specific Key Management Guidance | Hướng dẫn quản lý khóa gắn với những ứng dụng và giao thức cụ thể | Khi áp dụng mật mã trong một hệ thống cụ thể, cần chú ý điều gì? |

Ba phần không thay thế lẫn nhau. Part 1 tạo nền tảng kỹ thuật và khái niệm; Part 2 chuyển nền tảng đó thành năng lực tổ chức; Part 3 giúp áp dụng vào bối cảnh công nghệ cụ thể.

NIST có thể cập nhật các ấn bản và khuyến nghị theo thời gian. Khi xây dựng chính sách, hồ sơ kiểm toán hoặc hợp đồng, tổ chức cần ghi rõ ấn bản được áp dụng và kiểm tra lại danh mục công bố chính thức của NIST thay vì chỉ ghi chung “tuân thủ NIST SP 800-57”.

## 2. Phạm vi và mục tiêu của key management

Một chương trình quản lý khóa tốt cần bảo vệ ba thuộc tính:

- **Confidentiality:** chỉ chủ thể được phép mới có thể tiếp cận key material bí mật hoặc dữ liệu được giải mã.
- **Integrity:** khóa, metadata, phiên bản, policy và trạng thái tin cậy không bị thay đổi trái phép.
- **Availability:** khóa còn cần thiết phải có thể được sử dụng hoặc khôi phục khi hệ thống hợp lệ cần đến.

Ba thuộc tính có thể xung đột. Ví dụ, hủy một khóa bị nghi ngờ compromise có thể giảm rủi ro bí mật nhưng cũng làm dữ liệu lịch sử không thể giải mã. Giữ một khóa quá lâu có thể duy trì khả năng phục hồi nhưng kéo dài thời gian phơi nhiễm. Quản lý khóa phải cân bằng rủi ro và mục tiêu nghiệp vụ dựa trên phân loại dữ liệu, thời gian lưu giữ và khả năng khôi phục.

NIST SP 800-57 hỗ trợ tổ chức thiết lập cách tiếp cận có hệ thống cho các hoạt động như:

- Xác định loại khóa, thuật toán, mục đích và chủ thể sử dụng.
- Chọn mức bảo vệ phù hợp với giá trị tài sản và threat model.
- Thiết lập cryptoperiod và giới hạn sử dụng.
- Quản lý keying material trong các trạng thái khác nhau.
- Bảo vệ việc tạo, phân phối, lưu trữ, backup, recovery và destruction.
- Phân định trách nhiệm giữa người sở hữu, người vận hành, người phê duyệt và người kiểm toán.
- Duy trì bằng chứng để đánh giá chính sách và hiệu quả kiểm soát.

## 3. Thuật ngữ nền tảng cần hiểu

### Key và keying material

**Key** là giá trị được thuật toán mật mã sử dụng để thực hiện một phép toán. **Keying material** là khái niệm rộng hơn, có thể bao gồm key, tham số và thông tin liên quan cần thiết để thiết lập hoặc sử dụng một cơ chế mật mã.

Ví dụ, một phiên TLS có thể liên quan đến private key của máy chủ, chứng thư và public key, khóa phiên, nonce, thuật toán thỏa thuận khóa và các tham số giao thức. Những thành phần này có mức độ nhạy cảm và vòng đời khác nhau.

### Các loại khóa phổ biến

| Loại khóa | Mục đích | Đặc điểm quản lý |
|---|---|---|
| Symmetric encryption key | Mã hóa và giải mã dữ liệu | Cùng một khóa bí mật được dùng cho hai chiều; cần bảo vệ và phân phối kín |
| MAC key | Tạo và xác minh message authentication code | Bên tạo và xác minh thường cùng giữ bí mật; cần tách mục đích khỏi khóa mã hóa |
| Private signing key | Tạo chữ ký số | Phải hạn chế quyền ký và bảo vệ tính toàn vẹn của danh tính ký |
| Public verification key | Xác minh chữ ký | Có thể công bố nhưng phải xác thực nguồn gốc và liên kết với đúng chủ thể |
| Key agreement key pair | Thiết lập bí mật chung | Phải kiểm soát tham số, danh tính peer và kết quả dẫn xuất khóa |
| Key wrapping key / KEK | Bảo vệ khóa khác | Cần bảo vệ chặt vì compromise có thể ảnh hưởng nhiều DEK |
| Data Encryption Key / DEK | Mã hóa dữ liệu | Có thể được tạo theo đối tượng hoặc phạm vi dữ liệu; thường được bọc bởi KEK |
| Key derivation key | Làm đầu vào cho KDF | Cần domain separation và kiểm soát mục đích dẫn xuất |

Không nên dùng cùng một key cho nhiều mục đích mật mã không tương thích. Ví dụ, khóa dùng để mã hóa dữ liệu không nên tự động được tái sử dụng làm MAC key hoặc signing key. Khi một thiết kế cần nhiều khóa liên quan, nên dùng quy trình dẫn xuất khóa được chấp nhận, có phân tách miền (domain separation) và nhãn mục đích rõ ràng.

### Key pair và public key

Trong mật mã bất đối xứng, public key và private key tạo thành một cặp có quan hệ toán học. Private key cần được bảo vệ theo mục đích sử dụng; public key thường có thể phân phối nhưng phải xác minh tính xác thực. Chứng thư số có thể gắn public key với danh tính, thời hạn và thông tin của tổ chức phát hành.

Không nên xem public key là bí mật chỉ vì nó thuộc một key pair. Rủi ro chính với public key thường là bị thay thế, gắn sai danh tính hoặc sử dụng ngoài trạng thái tin cậy.

### Security strength

Security strength biểu thị mức độ khó ước tính để phá vỡ một cơ chế mật mã, thường được diễn đạt bằng số bit an toàn tương đương. Security strength không đồng nhất với độ dài khóa. Hai thuật toán có key length khác nhau có thể cung cấp mức an toàn tương đương khác nhau.

Khi chọn thuật toán và kích thước khóa, cần xét loại thuật toán, mục đích, cách triển khai, mức an toàn cần đạt và thời gian dữ liệu cần được bảo vệ. Không nên chọn key length chỉ theo thói quen hoặc theo giá trị lớn nhất mà thư viện hỗ trợ.

## 4. Vòng đời và trạng thái của khóa

NIST SP 800-57 mô tả việc quản lý khóa theo vòng đời và các trạng thái. Một mô hình trạng thái thường dùng để phân tích gồm:

| Trạng thái | Ý nghĩa | Hành động điển hình |
|---|---|---|
| Pre-activation | Khóa đã được tạo hoặc nhận nhưng chưa được phép dùng cho mục đích hoạt động | Kiểm tra, đăng ký, phân phối và chờ kích hoạt |
| Active | Khóa đang được phép dùng theo purpose và policy đã định | Encrypt, decrypt, sign, verify hoặc thao tác được cấp |
| Deactivated | Khóa không còn được dùng để tạo hoạt động mới theo mục đích ban đầu, nhưng có thể còn cần cho xử lý lịch sử | Chỉ cho phép thao tác lịch sử được phê duyệt, ví dụ decrypt hoặc verify nếu policy cho phép |
| Compromised | Có bằng chứng hoặc nghi ngờ đáng tin cậy rằng khóa hoặc bí mật liên quan đã bị lộ hay mất kiểm soát | Cô lập, đánh giá ảnh hưởng, thay thế, thu hồi và xử lý dữ liệu liên quan |
| Destroyed | Vật liệu khóa đã được hủy theo quy trình được chấp thuận | Không còn khả năng sử dụng vật liệu khóa đã hủy |

Tên trạng thái và cách chuyển đổi cụ thể có thể khác theo loại key, giao thức và sản phẩm KMS/HSM. Một nhà cung cấp có thể biểu diễn trạng thái bằng Enabled, Disabled, PendingDeletion hoặc Destroyed. Không được mặc định rằng trạng thái của nhà cung cấp ánh xạ một-một với trạng thái khái niệm của NIST.

Vòng đời cần xác định rõ điều kiện chuyển trạng thái, người có quyền thực hiện, approval cần thiết, dữ liệu phụ thuộc và bằng chứng sau mỗi lần chuyển đổi.

~~~mermaid
stateDiagram-v2
    [*] --> PreActivation
    PreActivation --> Active: Kiểm tra và kích hoạt
    Active --> Deactivated: Hết cryptoperiod hoặc thay thế
    Active --> Compromised: Phát hiện compromise
    Deactivated --> Compromised: Phát hiện compromise lịch sử
    Deactivated --> Destroyed: Hết nhu cầu và đủ điều kiện
    Compromised --> Destroyed: Xử lý sự cố và phê duyệt
    Active --> Destroyed: Chỉ khi policy cho phép và đã xử lý phụ thuộc
~~~

### Các giai đoạn vận hành

Có thể chia công việc quản lý khóa thành bốn giai đoạn:

1. **Pre-operational:** tạo hoặc nhận key, xác minh nguồn, đăng ký metadata, phân phối, backup theo yêu cầu và chuẩn bị kích hoạt.
2. **Operational:** sử dụng key trong phạm vi purpose, theo dõi số lần sử dụng, quản lý quyền và giám sát hoạt động.
3. **Post-operational:** ngừng dùng cho hoạt động mới, giữ khả năng xử lý dữ liệu lịch sử nếu cần, lưu trữ hoặc chuyển đổi.
4. **Destruction:** xác minh không còn phụ thuộc, thực hiện hủy, lưu bằng chứng và cập nhật inventory.

Compromise có thể xảy ra ở bất kỳ giai đoạn nào. Vì vậy, xử lý compromise là luồng ứng phó xuyên suốt chứ không chỉ là bước cuối của vòng đời.

## 5. Cryptoperiod và giới hạn sử dụng

Cryptoperiod là khoảng thời gian mà một khóa được phép sử dụng hoặc được xem là phù hợp cho một mục đích nhất định theo chính sách. Cryptoperiod không chỉ là ngày hết hạn được ghi trong metadata. Nó cần được xác định dựa trên loại khóa, mục đích, security strength, lượng dữ liệu hoặc số lần sử dụng, threat model, thời gian lưu giữ và yêu cầu nghiệp vụ.

Một số yếu tố ảnh hưởng:

- Mức nhạy cảm và giá trị của dữ liệu.
- Thuật toán, security strength và giới hạn sử dụng.
- Số lượng dữ liệu hoặc số phép toán đã thực hiện với key.
- Khả năng key bị lộ qua người dùng, workload, bộ nhớ hoặc backup.
- Khả năng phát hiện, cô lập và thay thế khi có sự cố.
- Yêu cầu lưu trữ, pháp lý và khả năng giải mã lịch sử.

Cần phân biệt thời gian dùng key để tạo dữ liệu mới với thời gian key còn cần thiết để xử lý dữ liệu cũ. Ví dụ, một DEK có thể ngừng dùng để mã hóa bản ghi mới nhưng vẫn cần được giữ để giải mã bản ghi lịch sử trong thời hạn lưu giữ.

Với khóa bất đối xứng, thời gian tạo chữ ký bằng private key có thể khác với thời gian cần public key để xác minh chữ ký lịch sử. Với chứng thư, thời hạn chứng thư và cryptoperiod của key là những khái niệm liên quan nhưng không đồng nhất.

Không có một con số thời hạn chung phù hợp cho mọi khóa. Tổ chức cần ghi rõ giả định, căn cứ và chủ thể phê duyệt cho từng loại key hoặc nhóm key.

## 6. Tạo và thiết lập khóa

Một key an toàn phải được tạo hoặc thiết lập theo phương pháp phù hợp với thuật toán và môi trường sử dụng.

Các nguyên tắc chính:

- Dùng nguồn ngẫu nhiên mật mã phù hợp cho key cần entropy.
- Chọn thuật toán và tham số được tổ chức chấp nhận.
- Tạo key theo đúng purpose và key usage đã khai báo.
- Không tự tạo key bằng timestamp, UUID thông thường, tên người dùng hoặc dữ liệu dễ dự đoán.
- Tránh đưa key vào log, telemetry, crash dump hoặc hệ thống build.
- Ghi nhận key ID, thuật toán, security strength, thời điểm tạo, nguồn tạo và owner.
- Kiểm tra quy trình import nếu key được tạo bên ngoài KMS/HSM.

Key có thể được tạo bên trong KMS/HSM để giảm việc key material xuất hiện trong ứng dụng. Nếu phải import, cần có quy trình bảo vệ trong suốt quá trình vận chuyển, xác thực nguồn, kiểm tra tính toàn vẹn và hủy các bản tạm sau khi hoàn tất.

### Key establishment

Key establishment bao gồm các phương pháp giúp hai hoặc nhiều bên có được keying material chung. Có thể là key transport, key agreement hoặc dẫn xuất khóa từ một bí mật gốc theo cơ chế được thiết kế.

Trong key agreement, việc thiết lập bí mật chung cần gắn với xác thực peer và bảo vệ chống man-in-the-middle. Chỉ có cùng một shared secret không đủ nếu hai bên không xác minh được họ đang trao đổi với đúng đối tác.

Trong key transport, bên gửi bảo vệ khóa được chuyển tới bên nhận bằng cơ chế mật mã thích hợp. Hệ thống cần xác định rõ key-encryption key, recipient, thuật toán, context và cách xử lý khi chuyển giao thất bại.

## 7. Phân phối, lưu trữ và bảo vệ key material

Key cần được phân phối tới đúng thành phần có trách nhiệm và chỉ trong phạm vi cần thiết. Đường phân phối phải bảo vệ tính bí mật, toàn vẹn, xác thực nguồn và khả năng chống phát lại khi phù hợp.

Các biện pháp phổ biến:

- Dùng KMS/HSM để giữ key material và thực hiện phép toán bên trong ranh giới bảo vệ.
- Dùng envelope encryption để DEK được bọc bởi KEK.
- Dùng IAM/policy giới hạn principal, resource, action và context.
- Dùng kênh truyền được xác thực và mã hóa khi phải chuyển key.
- Tách môi trường production, staging và development.
- Tách quyền người vận hành, approver, key custodian và auditor.
- Giám sát việc import/export và thay đổi policy.

Một key không exportable giảm nguy cơ bị sao chép trực tiếp, nhưng không ngăn người có quyền gọi decrypt hoặc sign lạm dụng API. Cần bảo vệ cả key material lẫn khả năng yêu cầu thao tác bằng key.

### Envelope encryption

Trong envelope encryption, dữ liệu được mã hóa bằng DEK; DEK được bảo vệ bằng KEK. Cách này cho phép dữ liệu lớn được mã hóa ngoài KMS trong khi KEK được quản lý tập trung.

~~~mermaid
flowchart TD
    A[Ứng dụng] --> B[Tạo hoặc nhận DEK]
    B --> C[Mã hóa dữ liệu]
    B --> D[Bọc DEK bằng KEK]
    C --> E[Ciphertext]
    D --> F[Encrypted DEK]
    E --> G[Lưu dữ liệu]
    F --> G
    H[KMS hoặc HSM giữ KEK] --> D
    G --> I[Khi cần giải mã]
    I --> J[KMS mở bọc DEK]
    J --> K[DEK bản rõ trong phạm vi sử dụng]
    K --> L[Giải mã dữ liệu]
~~~

Khi dùng mô hình này, cần quản lý cả ciphertext, encrypted DEK, key ID/version, encryption context và metadata cần thiết để khôi phục. Nếu mất liên kết tới KEK hoặc phiên bản key, ciphertext có thể không còn giải mã được dù encrypted DEK vẫn còn.

## 8. Sử dụng key đúng purpose

Key chỉ nên được dùng cho mục đích đã được phê duyệt. Metadata và policy cần thể hiện purpose, thuật toán, usage, owner, phạm vi dữ liệu và principal được phép sử dụng.

Ví dụ:

- DEK dùng cho encrypt/decrypt dữ liệu của một ứng dụng.
- KEK dùng để wrap/unwrap DEK.
- Private key dùng để sign.
- Public key dùng để verify.
- MAC key dùng để tạo và kiểm tra MAC.

Việc tái sử dụng key cho nhiều mục đích có thể tạo ra tương tác ngoài dự kiến giữa các giao thức, làm tăng phạm vi ảnh hưởng khi key bị compromise và gây khó khăn khi rotation. Nếu cần tạo nhiều khóa từ một secret gốc, dùng KDF phù hợp với context và nhãn purpose riêng cho từng khóa.

### Giới hạn thao tác và kiểm toán

Quyền sử dụng cần được cấp theo từng operation. Quyền encrypt không tự động bao gồm decrypt; quyền verify không tự động bao gồm sign; quyền quản lý metadata không tự động bao gồm quyền export key material.

Audit cần ghi nhận principal, key ID/version, operation, thời gian, kết quả, context an toàn và approval hoặc ticket khi cần. Không ghi key material, plaintext hoặc credential vào log.

## 9. Backup, recovery và archival

Backup và recovery là thành phần của key management vì dữ liệu đã mã hóa phụ thuộc vào khả năng sử dụng key trong tương lai. Backup key cần được bảo vệ ở mức tương xứng với key gốc và cần tránh tạo ra vòng phụ thuộc khiến không thể khôi phục.

Cần phân biệt:

- **Backup:** bản sao phục vụ khôi phục khi key hoặc hệ thống bị mất.
- **Recovery:** quy trình đưa key hoặc khả năng sử dụng key trở lại trạng thái hoạt động được phê duyệt.
- **Archival:** giữ key ở trạng thái được kiểm soát để xử lý dữ liệu lịch sử hoặc xác minh lâu dài.
- **Replication:** đồng bộ key hoặc trạng thái giữa các vùng; không nhất thiết tương đương backup độc lập.

Không phải mọi key đều nên backup. Một số key phiên ngắn hạn có thể không cần khôi phục; private key hoặc KEK quan trọng có thể cần cơ chế backup được bảo vệ. Việc quyết định cần dựa trên hậu quả mất key, khả năng tạo lại, yêu cầu lịch sử và threat model.

Một quy trình recovery cần kiểm tra danh tính người yêu cầu, phê duyệt, tính toàn vẹn của backup, môi trường khôi phục, phiên bản key và khả năng giải mã dữ liệu kiểm thử. Không nên đưa key vào production chỉ vì đã khôi phục thành công về mặt kỹ thuật.

## 10. Rotation, deactivation và xử lý compromise

Rotation là việc thay thế key theo kế hoạch hoặc theo yêu cầu bảo mật. Quy trình cần xác định key mới, thời điểm cutover, dữ liệu mới sử dụng phiên bản nào, dữ liệu cũ còn phụ thuộc vào phiên bản nào và điều kiện loại bỏ key cũ.

Có thể có hai cách chuyển đổi khác nhau:

- **New-write rotation:** dữ liệu mới dùng key mới; key cũ tiếp tục được giữ để giải mã dữ liệu lịch sử.
- **Re-encryption:** dữ liệu cũ được giải mã và mã hóa lại bằng key mới; cần kiểm soát tính toàn vẹn, tính nhất quán và khả năng rollback.

Nếu DEK được bọc bởi KEK, có thể rewrap DEK bằng KEK mới mà không phải mã hóa lại toàn bộ ciphertext, tùy kiến trúc. Rewrap và re-encryption là hai thao tác khác nhau.

Khi key bị nghi ngờ compromise, tổ chức cần xác định loại key, phạm vi sử dụng, thời điểm có thể bị lộ và dữ liệu/chữ ký bị ảnh hưởng. Có thể cần disable hoặc thu hồi key, phát hành key mới, re-encrypt dữ liệu, revoke chứng thư, thay credential và điều tra các thao tác đã được gọi.

Không nên chỉ đổi trạng thái key rồi xem sự cố đã kết thúc. Nếu plaintext đã bị lấy, rotation không thu hồi được bản sao dữ liệu đã lộ. Nếu private signing key bị compromise, chữ ký trái phép có thể đã được tạo; cần xử lý trust và xác minh lịch sử theo loại ứng dụng.

## 11. Destruction và crypto-erasure

Hủy key là bước cuối khi key không còn cần thiết và mọi phụ thuộc đã được xử lý. Trước khi hủy cần xác định:

- Dữ liệu production, bản sao, snapshot, backup, archive và bản sao ở vùng DR có còn cần key không.
- Có yêu cầu pháp lý, hợp đồng hoặc legal hold không.
- Có cần key để giải mã, unwrap, xác minh chữ ký hoặc phục hồi không.
- Các bản key material, share, cache hoặc export có được kiểm soát không.
- Ai phê duyệt và ai thực hiện hủy.
- Hệ thống cung cấp bằng chứng nào để xác nhận trạng thái hủy.

Crypto-erasure có thể làm dữ liệu không thể giải mã bằng cách hủy key cần thiết, nhưng chỉ có ý nghĩa khi mọi bản sao của key material và đường khôi phục đều được kiểm soát. Hủy một phiên bản KEK trong khi một KEK cũ hoặc bản export vẫn tồn tại không chứng minh dữ liệu đã được crypto-erased.

Hành động schedule deletion, disable hoặc revoke của một KMS không nhất thiết đồng nghĩa key material đã bị hủy vĩnh viễn. Cần phân biệt trạng thái chờ xóa, khả năng hủy lịch, xóa vật liệu và bằng chứng hoàn tất theo semantics của nhà cung cấp.

## 12. Tổ chức chương trình quản lý khóa theo Part 2

Part 2 mở rộng từ yêu cầu kỹ thuật sang cách tổ chức và vận hành chương trình quản lý khóa. Một tổ chức cần xác định ai chịu trách nhiệm, quy trình nào được áp dụng, hệ thống nào cung cấp dịch vụ và cách kiểm tra việc tuân thủ.

Các thành phần quản trị cốt lõi:

| Thành phần | Nội dung cần xác định |
|---|---|
| Key management policy | Mục tiêu, phạm vi, nguyên tắc, trách nhiệm và yêu cầu bắt buộc |
| Practice statement / procedures | Cách triển khai thực tế, quy trình vận hành, phê duyệt và xử lý ngoại lệ |
| Roles and responsibilities | Key owner, operator, approver, custodian, auditor và application owner |
| Key inventory | Danh mục key, metadata, owner, purpose, trạng thái, location và dependency |
| Infrastructure | KMS, HSM, PKI, key server, IAM, logging và recovery environment |
| Training | Đào tạo người vận hành, người phê duyệt và người kiểm toán |
| Audit and review | Rà soát policy, quyền, quy trình, bằng chứng và ngoại lệ |
| Incident management | Quy trình xử lý compromise, mất key, lộ credential và sai cấu hình |

### Phân tách nhiệm vụ

Một cá nhân không nên kiểm soát toàn bộ quy trình tạo, phê duyệt, sử dụng, thay đổi policy và hủy key quan trọng. Phân tách nhiệm vụ giúp giảm nguy cơ gian lận, lỗi thao tác và lạm dụng quyền.

Ví dụ, người yêu cầu export key material không nên tự phê duyệt yêu cầu đó. Người thực hiện hủy key không nên là người duy nhất xác nhận rằng mọi dữ liệu phụ thuộc đã hết hạn. Auditor cần quyền đọc bằng chứng độc lập nhưng không nên có quyền sửa policy hoặc xóa log.

### Key management policy và practice statement

Policy mô tả tổ chức yêu cầu điều gì và ai chịu trách nhiệm. Practice statement hoặc bộ quy trình mô tả tổ chức thực hiện các yêu cầu đó như thế nào trong môi trường thực tế.

Ví dụ:

- Policy: mọi key production phải có owner và purpose được đăng ký.
- Procedure: pipeline tạo key phải kiểm tra owner, purpose, environment và key usage trước khi gọi KMS.
- Evidence: inventory record, change record, KMS audit event và kết quả kiểm tra định kỳ.

Nếu policy nói một điều nhưng cấu hình và quy trình thực tế không thực hiện điều đó, chương trình quản lý khóa chưa đạt assurance mong muốn.

## 13. Áp dụng Part 3 vào ứng dụng cụ thể

Part 3 nhấn mạnh rằng quản lý khóa phải gắn với ứng dụng và giao thức. Một nguyên tắc chung có thể cần được triển khai khác nhau tùy cách key được dùng.

| Bối cảnh | Keying material | Điểm quản lý cần chú ý |
|---|---|---|
| TLS và PKI | Private key, public key, chứng thư, khóa phiên | Certificate lifecycle, private-key protection, trust, revocation và session key |
| Database encryption | DEK, KEK, database master key | Envelope encryption, backup, restore và key-version mapping |
| File/object encryption | DEK theo object hoặc nhóm object, KEK | Metadata, context, rewrap và khả năng giải mã lịch sử |
| Code signing | Private signing key, public verification key, certificate | Quyền sign, timestamp, certificate status và audit |
| Message authentication | MAC key | Phân phối bí mật, key separation, rotation và xác minh |
| Network/IPsec hoặc giao thức tương tự | Key agreement, traffic key, authentication key | Session lifetime, rekey, peer authentication và replay protection |

Không thể lấy một cấu hình key policy rồi áp dụng nguyên xi cho mọi giao thức. Ví dụ, private key của CA có thể có cryptoperiod và quy trình ceremony khác hẳn DEK dùng để mã hóa từng object. Khóa phiên của giao thức mạng thường có thời gian sử dụng ngắn và được dẫn xuất theo phiên, trong khi key dùng để xác minh chữ ký lưu trữ có thể cần tồn tại lâu hơn để kiểm tra bằng chứng lịch sử.

## 14. Chọn thuật toán và quản lý chuyển đổi

NIST SP 800-57 gắn quản lý khóa với security strength và việc lựa chọn thuật toán. Tổ chức cần theo dõi thuật toán, key length, implementation, purpose và mức an toàn tương ứng.

Không nên chỉ kiểm tra key length. Cần xem xét:

- Thuật toán và chế độ hoạt động.
- Security strength tương ứng.
- Cách sinh và phân phối key.
- Giới hạn dữ liệu hoặc số lần sử dụng.
- Khả năng tương thích giữa các hệ thống.
- Hỗ trợ của KMS/HSM và thư viện mật mã.
- Yêu cầu bảo vệ trong thời gian dài.
- Lộ trình thay thế khi thuật toán hoặc tham số không còn phù hợp.

Các khuyến nghị về thuật toán có thể được cập nhật trong những tài liệu NIST khác, chẳng hạn hướng dẫn chuyển đổi thuật toán và kích thước khóa. Vì vậy, chương trình cần có quy trình theo dõi thay đổi tiêu chuẩn, đánh giá ảnh hưởng, thử nghiệm tương thích và triển khai migration.

### Algorithm transition

Một kế hoạch chuyển đổi nên bao gồm:

1. Inventory toàn bộ key, certificate, protocol và ứng dụng đang dùng thuật toán liên quan.
2. Xác định mức độ rủi ro và thời hạn cần hoàn tất.
3. Chọn thuật toán hoặc tham số thay thế theo policy hiện hành.
4. Kiểm tra khả năng tương thích và hiệu năng.
5. Triển khai key mới và hỗ trợ giai đoạn chuyển tiếp có kiểm soát.
6. Di chuyển dữ liệu hoặc cấu hình phụ thuộc.
7. Ngừng phát sinh dữ liệu mới bằng cấu hình cũ.
8. Giữ khả năng đọc/xác minh lịch sử trong thời gian cần thiết.
9. Hủy hoặc loại bỏ tài nguyên cũ khi đủ điều kiện.
10. Lưu bằng chứng migration và phê duyệt.

## 15. NIST SP 800-57 và các chuẩn liên quan

NIST SP 800-57 là hướng dẫn quản lý khóa. Nó không tự động chứng nhận rằng một sản phẩm KMS/HSM hoặc toàn bộ tổ chức đã tuân thủ mọi yêu cầu an toàn.

Một số tài liệu và chương trình khác có vai trò bổ sung:

| Tài liệu/chương trình | Trọng tâm | Quan hệ với SP 800-57 |
|---|---|---|
| FIPS 140-3 | Yêu cầu và xác nhận đối với cryptographic module | Đánh giá module mật mã; không thay thế chương trình quản lý khóa toàn tổ chức |
| NIST SP 800-53 | Security and privacy controls cho hệ thống và tổ chức | Cung cấp control framework để ánh xạ kiểm soát quản lý khóa |
| NIST SP 800-131A | Hướng dẫn chuyển đổi và sử dụng thuật toán, key length | Hỗ trợ quyết định thuật toán và lộ trình chuyển đổi |
| NIST SP 800-130 | Framework thiết kế Cryptographic Key Management Systems | Hỗ trợ thiết kế hệ thống quản lý khóa |
| Chính sách nội bộ và yêu cầu ngành | Quy định theo tổ chức, pháp lý hoặc hợp đồng | Bổ sung phạm vi, trách nhiệm, thời hạn và bằng chứng cụ thể |

Ví dụ, một HSM có chứng nhận theo FIPS 140-3 không chứng minh rằng tổ chức đã cấp quyền đúng, backup đầy đủ, rotation đúng thời điểm hoặc hủy key an toàn. Ngược lại, một quy trình được viết theo SP 800-57 không chứng minh module mật mã đang dùng đã được xác nhận theo FIPS 140-3.

Cần phân biệt **chuẩn thiết kế**, **chuẩn kiểm soát**, **xác nhận module** và **bằng chứng vận hành**. Chúng bổ sung cho nhau nhưng không thể dùng thay thế lẫn nhau.

## 16. Từ khuyến nghị thành assurance và bằng chứng

Assurance là khả năng chứng minh bằng bằng chứng có thể kiểm tra rằng các yêu cầu quản lý khóa đã được thiết kế, triển khai và vận hành hiệu quả. Một tài liệu policy đơn lẻ không đủ. Cần có cấu hình, log, record, test và review tương ứng.

Có thể dùng ma trận sau:

| Yêu cầu | Kiểm soát triển khai | Bằng chứng có thể kiểm tra |
|---|---|---|
| Mỗi key có mục đích rõ ràng | Bắt buộc purpose và owner trong quy trình tạo key | Key inventory, metadata, approval |
| Key được tạo an toàn | Chỉ dùng KMS/HSM hoặc generator được phê duyệt | Cấu hình, audit event, module information |
| Quyền sử dụng được giới hạn | IAM policy theo principal, key, operation và context | Policy export, access review, denied/allowed event |
| Cryptoperiod được quản lý | Lịch rotation và quy tắc deactivation | Rotation record, key version history |
| Backup có thể khôi phục | Backup policy và restore drill | Backup manifest, test report, approval |
| Compromise được xử lý | Incident runbook và quyền containment | Incident record, timeline, revocation/rotation evidence |
| Hủy key có kiểm soát | Destruction gate và approval | Dependency clearance, deletion record, audit event |
| Trách nhiệm được phân tách | SoD và approval workflow | Role matrix, approval log, access review |
| Thuật toán được duy trì phù hợp | Algorithm inventory và transition plan | Crypto inventory, risk assessment, migration record |

### Mô hình assurance theo chuỗi

~~~mermaid
flowchart LR
    A[Khuyến nghị NIST SP 800-57] --> B[Yêu cầu nội bộ]
    B --> C[Kiểm soát và quy trình]
    C --> D[Cấu hình KMS/HSM và ứng dụng]
    D --> E[Hoạt động thực tế]
    E --> F[Log, record và test]
    F --> G[Review và đánh giá assurance]
    G --> H[Khắc phục và cải tiến]
    H --> B
~~~

Một bằng chứng tốt cần có nguồn gốc, thời điểm, phạm vi, người chịu trách nhiệm và khả năng kiểm tra lại. Ví dụ, ảnh chụp màn hình cho thấy rotation được bật không chứng minh rotation đã chạy thành công. Cần có lịch sử phiên bản, audit event, trạng thái sau thay đổi và kết quả kiểm tra dữ liệu phụ thuộc.

### Kiểm tra thiết kế và kiểm tra vận hành

- **Design assessment:** policy có phân loại key, xác định owner, purpose, cryptoperiod và trách nhiệm chưa?
- **Implementation assessment:** cấu hình IAM, KMS/HSM, backup và logging có hiện thực đúng policy không?
- **Operating effectiveness:** kiểm soát có chạy đều, có phê duyệt và có xử lý ngoại lệ đúng quy trình không?
- **Recovery validation:** tổ chức có thể phục hồi và sử dụng key đúng cách khi cần không?
- **Evidence review:** bằng chứng có đầy đủ, không bị sửa trái phép và liên kết được với yêu cầu không?

## 17. Ví dụ thực tế: quản lý key mã hóa dữ liệu thanh toán

Một nền tảng thanh toán lưu dữ liệu giao dịch nhạy cảm. Mỗi nhóm dữ liệu được mã hóa bằng DEK; DEK được bọc bởi KEK trong KMS. Private key riêng được dùng để ký một số thông điệp nghiệp vụ.

Áp dụng các nguyên tắc từ NIST SP 800-57:

**Phân loại và inventory:** mỗi key có ID, owner, purpose, thuật toán, security strength, môi trường, trạng thái, cryptoperiod, key version và dữ liệu phụ thuộc.

**Tạo và bảo vệ:** DEK được tạo bằng nguồn ngẫu nhiên phù hợp; KEK được quản lý trong KMS/HSM. Private signing key được giới hạn quyền sign và bảo vệ khỏi export.

**Phân quyền:** workload thanh toán được phép gọi encrypt/decrypt theo policy. Con người có quyền đọc metadata; quyền decrypt production cần JIT, ticket và phê duyệt. Auditor chỉ đọc audit log.

**Rotation:** DEK/KEK mới được đưa vào sử dụng cho dữ liệu mới. DEK cũ vẫn có thể cần để đọc giao dịch lịch sử. Nếu thay KEK, hệ thống đánh giá rewrap các DEK và kiểm tra backup trước khi loại bỏ phiên bản cũ.

**Compromise:** nếu private signing key bị nghi ngờ lộ, tổ chức cô lập quyền sign, đánh giá chữ ký có thể bị tạo trái phép, phát hành key/certificate thay thế và cập nhật trust theo quy trình.

**Recovery:** backup được lưu trong miền phục hồi độc lập; restore drill xác nhận có thể mở bọc DEK và giải mã dữ liệu kiểm thử.

**Destruction:** chỉ hủy key khi inventory chứng minh không còn dữ liệu, backup, archive hoặc legal hold cần key đó; hành động có approval và audit evidence.

Kết quả là chương trình quản lý khóa có thể giải thích được key nào tồn tại, tại sao cần key, ai được phép sử dụng, dữ liệu nào phụ thuộc và điều kiện nào cho phép thay thế hoặc hủy.

## 18. Những hiểu lầm thường gặp

**Cho rằng NIST SP 800-57 là một cấu hình KMS.** Tài liệu đưa ra khuyến nghị và khung quản lý. Cấu hình cụ thể phải được thiết kế theo sản phẩm, kiến trúc và policy của tổ chức.

**Cho rằng dùng HSM là đã hoàn thành key management.** HSM có thể bảo vệ key material, nhưng không tự quyết định owner, quyền ứng dụng, cryptoperiod, backup, recovery hay destruction.

**Cho rằng key length lớn hơn luôn có nghĩa an toàn hơn.** Cần xem security strength, thuật toán, implementation, purpose và thời gian cần bảo vệ.

**Cho rằng mọi key đều có cùng cryptoperiod.** Key mã hóa dữ liệu, key ký số, key phiên và key wrapping có mục đích và rủi ro khác nhau.

**Cho rằng hết cryptoperiod là phải hủy ngay.** Có thể cần giữ key cũ cho decrypt, unwrap hoặc verify lịch sử. Việc ngừng sử dụng cho hoạt động mới và hủy vật liệu là hai quyết định khác nhau.

**Cho rằng chứng nhận FIPS 140-3 đồng nghĩa cả tổ chức tuân thủ SP 800-57.** Xác nhận module và assurance của chương trình quản lý khóa là các phạm vi khác nhau.

**Cho rằng policy là đủ để chứng minh kiểm soát.** Cần bằng chứng cấu hình và vận hành như audit event, approval, inventory, rotation record, backup test và destruction evidence.

**Cho rằng rotation giải quyết mọi compromise.** Rotation không thu hồi dữ liệu plaintext đã bị lấy hoặc chữ ký trái phép đã được tạo. Cần đánh giá tác động và ứng phó theo loại key.

## 19. Checklist triển khai chương trình theo NIST SP 800-57

- [ ] Xác định ấn bản NIST SP 800-57 được tổ chức áp dụng.
- [ ] Phân loại dữ liệu, hệ thống và mục đích dùng key.
- [ ] Có inventory tập trung cho key và keying material.
- [ ] Mỗi key có owner, purpose, algorithm, security strength và trạng thái.
- [ ] Xác định cryptoperiod và giới hạn sử dụng phù hợp.
- [ ] Chọn thuật toán và tham số theo policy hiện hành.
- [ ] Dùng nguồn tạo key và key establishment được chấp nhận.
- [ ] Bảo vệ key material trong KMS/HSM hoặc ranh giới phù hợp.
- [ ] Phân tách quyền theo principal, resource, operation và context.
- [ ] Có policy và quy trình phân phối, backup, recovery, archival và destruction.
- [ ] Tách vai trò owner, operator, approver, custodian và auditor.
- [ ] Có quy trình rotation và giữ key lịch sử khi dữ liệu còn phụ thuộc.
- [ ] Có quy trình compromise, disable, revoke và replacement.
- [ ] Kiểm tra backup và recovery bằng diễn tập thực tế.
- [ ] Kiểm soát việc import/export và key ceremony.
- [ ] Audit các thao tác key và bảo vệ log độc lập.
- [ ] Rà soát quyền và policy định kỳ.
- [ ] Theo dõi thay đổi thuật toán, security strength và khuyến nghị NIST.
- [ ] Có ma trận ánh xạ yêu cầu, kiểm soát và bằng chứng.
- [ ] Kiểm tra hiệu quả vận hành và theo dõi khắc phục phát hiện.

## 20. Kết luận

NIST SP 800-57 cung cấp nền tảng để quản lý khóa mật mã xuyên suốt vòng đời. Part 1 trình bày nguyên tắc và yêu cầu kỹ thuật; Part 2 giúp tổ chức xác định chính sách, vai trò và quy trình; Part 3 hỗ trợ áp dụng các nguyên tắc đó vào từng ứng dụng và giao thức.

Để chương trình có assurance, tổ chức cần chuyển khuyến nghị thành yêu cầu nội bộ, kiểm soát cụ thể, cấu hình có thể kiểm tra và bằng chứng vận hành. Inventory, cryptoperiod, phân quyền, backup/recovery, xử lý compromise, rotation và destruction phải liên kết với nhau. Một key chỉ được quản lý tốt khi tổ chức hiểu mục đích, biết ai chịu trách nhiệm, kiểm soát được cách sử dụng và chứng minh được rằng các quy trình bảo vệ vẫn hoạt động trong thực tế.

