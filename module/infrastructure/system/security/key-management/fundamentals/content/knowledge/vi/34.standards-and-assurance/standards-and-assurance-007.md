# FIPS 140 boundary

FIPS 140 boundary là ranh giới xác định những thành phần nào thuộc một cryptographic module được đánh giá và xác thực theo chuẩn FIPS 140. Ranh giới này cho biết phần cứng, firmware, phần mềm, giao diện, dịch vụ mật mã và cơ chế bảo vệ nào nằm trong phạm vi module; đồng thời làm rõ thành phần nào ở bên ngoài và chỉ tương tác với module qua các giao diện được định nghĩa.

Trong module SECURITY_KEY_MANAGEMENT_FUNDAMENTALS, hiểu đúng FIPS 140 boundary giúp đánh giá nơi key material được tạo, lưu, sử dụng và bảo vệ. Một ứng dụng gọi KMS hoặc HSM không tự động có nghĩa toàn bộ ứng dụng, dữ liệu hay mọi thao tác mật mã đều nằm trong phạm vi FIPS validation. Phạm vi được xác định bởi certificate và Security Policy của đúng cryptographic module, phiên bản và cấu hình vận hành.

## 1. FIPS 140 boundary là gì?

FIPS 140 là bộ yêu cầu bảo mật dành cho cryptographic module được sử dụng trong các hệ thống bảo vệ thông tin nhạy cảm. FIPS 140-3 dựa trên các yêu cầu của ISO/IEC 19790 và phương pháp kiểm thử liên quan trong ISO/IEC 24759, cùng tài liệu hướng dẫn của chương trình CMVP.

Cryptographic module là tập hợp phần cứng, phần mềm, firmware hoặc tổ hợp của chúng thực hiện các chức năng mật mã và bảo vệ các tham số bảo mật liên quan. Boundary là ranh giới được định nghĩa để xác định chính xác tập hợp đó.

Ranh giới trả lời các câu hỏi:

- Thành phần nào được tính là một phần của cryptographic module?
- Key material và các tham số bảo mật được bảo vệ ở đâu?
- Dữ liệu đi vào và đi ra qua giao diện nào?
- Ai được phép gọi từng dịch vụ mật mã?
- Những thuật toán và dịch vụ nào được phép trong approved mode?
- Cấu hình phần cứng, firmware, phần mềm và môi trường vận hành nào đã được đánh giá?

Boundary không chỉ là đường viền trên sơ đồ kiến trúc. Nó xác định phạm vi mà certificate và Security Policy áp dụng. Khi một thành phần nằm ngoài boundary, không thể mặc nhiên dùng validation của module để khẳng định thành phần đó cũng được xác thực.

## 2. Physical boundary và logical boundary

Boundary được thể hiện khác nhau tùy loại module:

| Loại boundary | Mô tả | Ví dụ |
|---|---|---|
| Physical boundary | Ranh giới vật lý bao quanh phần cứng mật mã | Vỏ thiết bị HSM hoặc thiết bị mật mã chuyên dụng |
| Logical boundary | Ranh giới logic xác định thành phần phần mềm/firmware thuộc module | Thư viện mật mã, executable, firmware image hoặc tập hợp thành phần được mô tả trong Security Policy |
| Hybrid boundary | Kết hợp thành phần phần cứng và phần mềm/firmware theo thiết kế module | Thiết bị có firmware thực hiện thuật toán và phần cứng bảo vệ key storage |

Với hardware module, physical boundary có thể bao quanh bo mạch, bộ xử lý, bộ nhớ và các thành phần bảo vệ vật lý được mô tả trong tài liệu xác thực. Cổng mạng hoặc máy chủ kết nối với HSM thường ở ngoài boundary, trừ khi Security Policy xác định khác.

Với software module, logical boundary có thể bao gồm thư viện hoặc tập hợp binary cụ thể chạy trên môi trường vận hành đã xác định. Hệ điều hành, JVM, ứng dụng gọi thư viện và phần mềm quản trị có thể nằm ngoài boundary. Không được tự suy luận rằng toàn bộ process hoặc máy chủ đều thuộc module chỉ vì nó nạp một thư viện đã được xác thực.

## 3. Thành phần nằm trong và ngoài boundary

Một module có thể gồm các thành phần như:

- Thuật toán mật mã và implementation tạo chữ ký, mã hóa, giải mã, hash hoặc derivation.
- Cơ chế tạo, lưu, sử dụng, zeroize và quản lý key material.
- Các giao diện nhận dữ liệu, trả kết quả, nhận lệnh điều khiển và cung cấp trạng thái.
- Cơ chế xác thực người dùng hoặc operator và phân quyền dịch vụ.
- Self-test, error state và cơ chế xử lý lỗi bảo mật.
- Phần cứng, firmware, phần mềm và cấu hình được liệt kê trong Security Policy.

Các thành phần thường nằm ngoài boundary, tùy module cụ thể:

- Ứng dụng nghiệp vụ gọi API mật mã.
- API gateway, load balancer, service mesh hoặc network routing.
- IAM/control plane quản lý danh tính và policy ở cấp dịch vụ.
- Hệ thống audit, SIEM, monitoring và ticketing.
- Cơ sở dữ liệu chứa ciphertext hoặc metadata do ứng dụng quản lý.
- Hệ điều hành, JVM, container runtime hoặc host nếu không được đưa vào phạm vi module.

Không có danh sách chung áp dụng cho mọi sản phẩm. Security Policy của certificate cụ thể là nguồn xác định thành phần bên trong và bên ngoài.

~~~mermaid
flowchart LR
    A[Ứng dụng nghiệp vụ] --> B[API / Provider adapter]
    B --> C
    subgraph C[Cryptographic module boundary]
        D[Crypto services]
        E[Key management]
        F[Self-tests and status]
        G[Protected key storage]
    end
    C --> H[Ciphertext / kết quả]
    I[Audit và SIEM] -. nhận event theo tích hợp .-> B
~~~

Sơ đồ chỉ minh họa một kiến trúc thường gặp. Adapter có thể nằm ngoài hoặc trong boundary tùy cách module được xác thực. Phải đối chiếu sơ đồ với Security Policy của đúng module, không dùng sơ đồ khái niệm này thay cho tài liệu chứng nhận.

## 4. Security Policy là tài liệu xác định boundary

Mỗi cryptographic module đã được xác thực có Security Policy tương ứng. Đây là tài liệu trọng yếu khi đánh giá sản phẩm hoặc thiết kế hệ thống có yêu cầu FIPS 140.

Security Policy thường mô tả:

- Tên module, nhà cung cấp, phiên bản và loại module.
- Certificate number, security level và các caveat/điều kiện áp dụng.
- Sơ đồ physical/logical boundary và thành phần thuộc module.
- Môi trường vận hành được xác thực, gồm cấu hình phần cứng/phần mềm liên quan.
- Các giao diện, vai trò, dịch vụ và quyền truy cập.
- Các thuật toán, key sizes, tham số và dịch vụ được chấp thuận.
- Cách vào, kiểm tra và rời approved mode nếu module hỗ trợ nhiều chế độ.
- Cách quản lý Critical Security Parameters (CSP), zeroization và self-test.
- Cách cài đặt, cấu hình, cập nhật và vận hành module.

Khi xem một sản phẩm được quảng bá là FIPS validated, cần tìm certificate và Security Policy đúng phiên bản. Tên thương mại giống nhau không đủ: phiên bản phần mềm, firmware, phần cứng hoặc môi trường vận hành khác có thể nằm ngoài cấu hình đã được xác thực.

## 5. Boundary và phạm vi của FIPS validation

FIPS validation áp dụng cho cryptographic module được xác định trong certificate, theo cấu hình và điều kiện được mô tả. Nó không tự động xác thực toàn bộ sản phẩm, ứng dụng hoặc hệ thống sử dụng module.

Ví dụ:

- Một HSM có cryptographic module đã được CMVP xác thực. Máy chủ ứng dụng kết nối tới HSM thường nằm ngoài boundary.
- Một thư viện mật mã được xác thực có thể là module, nhưng ứng dụng Java gọi thư viện đó không vì thế mà tự động trở thành module đã xác thực.
- Một dịch vụ cloud có thể dùng module đã xác thực ở backend. API endpoint, IAM, logging, storage và mọi thành phần dịch vụ không mặc nhiên nằm trong cùng boundary.
- Một thiết bị có thể có nhiều phiên bản firmware; certificate chỉ áp dụng cho các phiên bản/cấu hình được liệt kê.

Do đó, phát biểu “hệ thống này FIPS validated” thường quá rộng nếu không chỉ rõ module nào, certificate nào, phiên bản nào và thao tác nào được thực hiện bên trong boundary. Cách diễn đạt chính xác cần phân biệt module validation với việc thiết kế, cấu hình và vận hành toàn hệ thống theo yêu cầu FIPS.

## 6. Boundary trong Java JCA/JCE

Ứng dụng Java thường gọi mật mã qua JCA/JCE. Provider cung cấp implementation cho Cipher, Signature, MessageDigest, KeyStore và các service khác. Trong kiến trúc có FIPS module, provider có thể là một phần của module đã xác thực hoặc là adapter kết nối tới module bên ngoài.

Ví dụ kiến trúc PKCS#11:

~~~mermaid
flowchart LR
    A[Java application] --> B[JCA/JCE API]
    B --> C[Provider / PKCS#11 adapter]
    C --> D
    subgraph D[Validated cryptographic module boundary]
        E[HSM crypto services]
        F[Protected key objects]
    end
~~~

Không thể chỉ nhìn tên provider hoặc gọi Cipher.getInstance() thành công để kết luận thao tác nằm trong FIPS boundary. Cần kiểm tra:

1. Provider và phiên bản có đúng như Security Policy yêu cầu không.
2. Adapter/provider có thuộc boundary hay chỉ là lớp kết nối bên ngoài.
3. Key object thực sự được tạo và giữ ở đâu.
4. Thao tác mật mã có được thực hiện bởi module đã xác thực hay bởi provider phần mềm khác.
5. JDK, OS, native library, HSM firmware và cấu hình có nằm trong operational environment được xác thực không.
6. Ứng dụng có vô tình fallback sang provider khác khi module không khả dụng không.

Nếu ứng dụng bắt buộc dùng module cụ thể, cần chỉ định provider/route theo tài liệu tích hợp và kiểm tra provider thực tế được chọn. Không tự động fallback sang implementation phần mềm nếu điều đó làm thao tác ra ngoài boundary đã yêu cầu.

## 7. Boundary và KMS/HSM trong cloud

KMS thường cung cấp API để tạo key, mã hóa, giải mã, ký hoặc tạo data key. Tuy nhiên, API KMS và cryptographic module bên dưới là hai phạm vi có thể khác nhau.

Một dịch vụ KMS có thể gồm:

- API endpoint và lớp xác thực request.
- IAM, key policy và authorization engine.
- Control plane quản lý key metadata, version và lifecycle.
- Audit logging và monitoring.
- Cryptographic module hoặc HSM thực hiện các thao tác mật mã.
- Storage và replication cho metadata hoặc encrypted key material.

Cryptographic module được xác thực có thể chỉ là một thành phần của dịch vụ. Security documentation của nhà cung cấp cần chỉ rõ module/certificate nào thực hiện thao tác, cách request được đưa vào module và giới hạn vùng/endpoint/configuration.

Một endpoint có tên hoặc nhãn “FIPS” không tự chứng minh mọi thao tác mật mã của ứng dụng diễn ra bên trong validated boundary. Cũng cần phân biệt TLS bảo vệ kết nối tới endpoint với module thực hiện Encrypt/Decrypt/Sign cho dữ liệu ứng dụng.

Với HSM on-premises, boundary thường gắn với thiết bị hoặc partition theo Security Policy. Server, PKCS#11 client, network và ứng dụng thường là thành phần bên ngoài; HSM thực thi thao tác trên key object bên trong module theo cơ chế được xác thực.

## 8. Key material và Critical Security Parameters (CSP)

Boundary có ý nghĩa đặc biệt đối với việc bảo vệ CSP. CSP là các tham số bảo mật quan trọng cần được bảo vệ khỏi tiết lộ và sửa đổi trái phép. Ví dụ điển hình:

- Secret key đối xứng.
- Private key bất đối xứng.
- Key-encryption key hoặc key derivation secret.
- Authentication data hoặc tham số bí mật dùng để kiểm soát truy cập module.

FIPS 140-3 cũng sử dụng khái niệm Sensitive Security Parameters (SSP), bao gồm CSP và các public security parameters theo định nghĩa của chuẩn. Public key, certificate và các tham số công khai vẫn có thể cần integrity/authenticity protection dù không cần giữ bí mật như private key.

Khi kiểm tra boundary, cần xác định:

- CSP được tạo bên trong module hay được import từ bên ngoài.
- CSP có được phép export không, và nếu có thì chỉ ở dạng nào.
- Key wrapping hoặc transport protection được áp dụng ra sao.
- CSP được lưu trong bộ nhớ, storage hoặc backup nào.
- Khi kết thúc sử dụng hoặc có lỗi, zeroization được thực hiện thế nào.
- Log, crash dump, telemetry và debug interface có thể làm lộ CSP không.

Không giả định mọi key đều phải không thể export. Một số module hỗ trợ export CSP ở dạng được bảo vệ; một số key object có thuộc tính non-extractable. Hành vi được phép phải khớp Security Policy và mục đích sử dụng.

## 9. Dữ liệu đi qua boundary

Boundary phân định nơi dữ liệu và key material đi vào, được xử lý và đi ra. Cần xem xét từng luồng:

| Luồng | Câu hỏi kiểm soát |
|---|---|
| Plaintext input | Dữ liệu nhạy cảm đi vào module qua giao diện nào? |
| Ciphertext output | Kết quả có được trả ra theo đúng service không? |
| Key import | Ai được import key, theo định dạng và cơ chế bảo vệ nào? |
| Key export | Có được phép export không, có bắt buộc wrap không? |
| CSP internal storage | Key có được giữ trong vùng bảo vệ của module không? |
| Authentication data | Credential xác thực module được bảo vệ và thay mới thế nào? |
| Status/error output | Lỗi có làm lộ CSP hoặc trạng thái nội bộ nhạy cảm không? |

Ví dụ, nếu module nhận plaintext và trả ciphertext, thao tác mã hóa có thể diễn ra bên trong boundary. Nếu module chỉ unwrap một DEK rồi trả plaintext DEK cho ứng dụng để ứng dụng tự mã hóa dữ liệu, thao tác mã hóa dữ liệu cuối cùng xảy ra ở ngoài boundary.

Vì vậy, cần lập data-flow diagram và đánh dấu boundary trên từng luồng. Chỉ ghi “dùng KMS/HSM” trong kiến trúc không đủ để xác định nơi thuật toán được thực thi.

## 10. Approved mode và dịch vụ được phép

Một module đã được xác thực có thể có cách vận hành theo approved mode được Security Policy mô tả. Trong chế độ này, module chỉ cung cấp hoặc chỉ cho phép các thuật toán, dịch vụ, tham số và cấu hình được chấp thuận theo yêu cầu áp dụng.

Khi đánh giá approved mode:

- Xác định cách bật hoặc cấu hình chế độ theo Security Policy.
- Kiểm tra trạng thái mode bằng cơ chế/indicator mà module cung cấp.
- Xác định dịch vụ nào được phép và dịch vụ nào không được phép.
- Kiểm tra thuật toán, key size và tham số có nằm trong danh sách được chấp thuận không.
- Xác minh module không chuyển sang mode khác hoặc provider khác khi có lỗi.
- Ghi nhận trạng thái và cấu hình trong bằng chứng vận hành.

Không phải mọi module đều có cùng một lệnh bật approved mode hoặc cùng cách hiển thị trạng thái. Không tự suy luận từ tên thuật toán hoặc tên provider. Làm theo hướng dẫn của đúng module và certificate.

Một API có thể vẫn tồn tại trong provider nhưng bị giới hạn hoặc không được chấp thuận trong approved mode. Do đó, test cần kiểm tra cả thuật toán và service indicator/operation status theo tài liệu.

## 11. Self-test, lỗi và zeroization tại boundary

FIPS 140 quy định các yêu cầu về self-test và xử lý trạng thái lỗi của module. Mục đích là phát hiện một số lỗi nghiêm trọng trong implementation hoặc quá trình vận hành trước khi tiếp tục cung cấp dịch vụ mật mã.

Các điểm cần xem xét:

- Self-test được thực hiện khi khởi tạo và theo điều kiện nào trong vận hành.
- Known-answer test hoặc test tương ứng được áp dụng cho thuật toán nào.
- Điều gì xảy ra khi self-test thất bại.
- Module chuyển sang error state nào và dịch vụ nào bị chặn.
- CSP được zeroize khi nào và bằng cơ chế nào.
- Operator nhận được status/error indication nào.
- Việc reset hoặc khôi phục sau lỗi có yêu cầu xác thực/phê duyệt không.

Zeroization cần được hiểu trong phạm vi module và theo cơ chế được mô tả. Nó không tự xóa plaintext, key copy hoặc dữ liệu đã xuất khỏi boundary trước đó. Nếu ứng dụng nhận plaintext DEK, module không thể tự bảo đảm ứng dụng đã xóa mọi bản sao trong heap, dump hoặc log.

## 12. Security levels và ý nghĩa đối với boundary

FIPS 140 xác định các security level khác nhau. Các level đặt ra mức yêu cầu bảo đảm khác nhau trên nhiều lĩnh vực, có thể gồm physical security, authentication, quản lý CSP, self-test, môi trường vận hành và các biện pháp bảo vệ khác.

Không nên hiểu level cao hơn đơn giản là thuật toán mạnh hơn hoặc mọi rủi ro đều thấp hơn. Security level mô tả mức yêu cầu của module theo chuẩn; nó không thay thế threat model của hệ thống, kiểm soát vận hành hoặc đánh giá kiến trúc.

Khi so sánh hai module:

- Xem certificate và Security Policy của từng module.
- Xác định level áp dụng và caveat.
- So sánh loại module, physical/logical boundary và operational environment.
- Kiểm tra thuật toán/dịch vụ được phép và khả năng quản lý key.
- Đánh giá module có phù hợp use case và yêu cầu hệ thống hay không.

Không chọn module chỉ dựa vào một con số security level mà bỏ qua boundary, cấu hình, dịch vụ và cách tích hợp.

## 13. Phân biệt module validation với algorithm validation

Algorithm validation và cryptographic module validation là hai việc khác nhau:

| Loại xác thực | Đánh giá điều gì? | Không tự chứng minh điều gì? |
|---|---|---|
| Algorithm validation (ví dụ chương trình CAVP/ACVP phù hợp) | Implementation của thuật toán mật mã theo test vectors và yêu cầu tương ứng | Toàn bộ module, boundary, key management, interfaces hoặc operational environment đã được xác thực |
| Cryptographic module validation (CMVP) | Module theo yêu cầu FIPS 140, gồm boundary và các lĩnh vực bảo mật liên quan | Toàn bộ ứng dụng hoặc hệ thống tích hợp module tự động tuân thủ |

Một thuật toán có chứng nhận/validation riêng không có nghĩa bất kỳ thư viện nào triển khai thuật toán đó cũng là FIPS 140 validated. Tương tự, module có certificate không có nghĩa mọi thuật toán hoặc mọi service của module đều được phép trong approved mode.

Khi rà soát tài liệu, phải xác định certificate của module và các algorithm certificate liên quan, sau đó kiểm tra chúng có khớp phiên bản, cấu hình và dịch vụ đang sử dụng không.

## 14. Ví dụ: envelope encryption và boundary

Giả sử một ứng dụng Java sử dụng KMS/HSM để bảo vệ KEK và tạo DEK:

1. Ứng dụng gửi yêu cầu GenerateDataKey tới KMS.
2. Cryptographic module trong phạm vi được xác thực tạo DEK và tạo bản encrypted DEK theo cơ chế của dịch vụ.
3. KMS trả plaintext DEK và encrypted DEK cho ứng dụng.
4. Ứng dụng Java dùng plaintext DEK với AES-GCM để mã hóa dữ liệu.
5. Ứng dụng lưu ciphertext và encrypted DEK.

Trong thiết kế này, thao tác tạo/bao bọc DEK có thể diễn ra trong module; nhưng thao tác AES-GCM trên dữ liệu nghiệp vụ diễn ra trong ứng dụng nếu ứng dụng tự gọi provider phần mềm bên ngoài boundary.

Điều này có thể là thiết kế bảo vệ key hợp lý, nhưng nếu yêu cầu là thao tác mã hóa dữ liệu phải được thực hiện bên trong một validated cryptographic module, cần dùng một đường thực thi mà Security Policy bao phủ. Phải đánh giá cả nơi tạo DEK, nơi thực hiện AES-GCM, cách key được đưa vào và nơi plaintext tồn tại.

## 15. Cách đánh giá một FIPS boundary trong thực tế

Khi đánh giá module hoặc kiến trúc, thực hiện lần lượt:

1. **Xác định module:** lấy tên, nhà cung cấp, model/phiên bản và certificate number.
2. **Đọc Security Policy:** xác định boundary, sơ đồ, thành phần bên trong và bên ngoài.
3. **Xác minh cấu hình:** đối chiếu phần cứng, firmware, phần mềm, JDK, OS và operational environment với cấu hình được xác thực.
4. **Xác định dịch vụ:** lập danh sách Encrypt, Decrypt, Sign, Verify, GenerateKey, Derive, Import/Export và key storage đang dùng.
5. **Theo dõi luồng key:** xác định CSP được tạo, import, lưu, wrap, export, zeroize ở đâu.
6. **Kiểm tra approved mode:** xác minh chế độ và thuật toán/tham số được phép.
7. **Kiểm tra tích hợp:** xác định provider, adapter, API gateway, application và KMS control plane nằm ở đâu so với boundary.
8. **Đối chiếu bằng chứng:** certificate, Security Policy, cấu hình triển khai, log và tài liệu nhà cung cấp.
9. **Ghi caveat:** liệt kê khác biệt hoặc điều kiện chưa được chứng minh.

Kết quả nên là sơ đồ boundary có chú thích, bảng luồng dữ liệu/key, cấu hình thực tế và kết luận rõ thao tác nào được thực hiện bên trong module đã xác thực.

## 16. Kiểm thử và bằng chứng liên quan đến boundary

Đội triển khai có thể kiểm thử để xác minh hệ thống đang dùng đúng module và cấu hình. Những kiểm tra thường hữu ích:

- So sánh module name/version và certificate với inventory.
- Xác nhận provider và module thực sự được chọn cho từng service.
- Xác minh key object được tạo/lưu trong module theo policy.
- Kiểm tra quyền export/non-extractability và đường đi của CSP.
- Xác minh approved mode và các service được phép.
- Thử lỗi provider/HSM unavailable để bảo đảm không fallback trái phép.
- Kiểm tra audit event có principal, action, key reference và kết quả.
- Kiểm tra self-test/error status theo hướng dẫn nhà cung cấp.
- Xác minh thay đổi firmware, provider, JDK hoặc cấu hình có nằm trong phạm vi đã xác thực.

Các kiểm tra nội bộ này giúp xác minh cấu hình triển khai. Chúng không thay thế kiểm thử của phòng lab được công nhận hoặc quy trình CMVP và không tự cấp FIPS validation cho một module mới.

## 17. Rủi ro và hiểu nhầm thường gặp

| Hiểu nhầm/lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Toàn bộ ứng dụng gọi HSM được coi là nằm trong boundary | Mở rộng sai phạm vi validation | Vẽ boundary theo Security Policy và đánh dấu thành phần ngoài |
| Dùng endpoint có chữ FIPS là đủ | Nhầm endpoint/TLS với module thực hiện crypto | Xác minh module backend, certificate và service path |
| Provider có thuật toán được hỗ trợ nghĩa là FIPS approved | Có thể dùng service hoặc tham số không được chấp thuận | Kiểm tra approved mode và Security Policy |
| Algorithm validation được coi là module validation | Bỏ qua boundary, CSP, interfaces và self-test | Kiểm tra certificate CMVP của module |
| Certificate của một version áp dụng cho mọi version | Có thể triển khai ngoài validated configuration | Đối chiếu version, firmware, OS và caveat |
| Plaintext DEK trả về app vẫn được coi là nằm trong HSM | Bỏ sót key/data exposure ngoài boundary | Theo dõi luồng DEK và thao tác mã hóa ở ứng dụng |
| Module level được coi là thước đo duy nhất | Bỏ qua threat model và cách tích hợp | Đánh giá level cùng boundary, use case và vận hành |
| Thay provider hoặc firmware không cần đánh giá lại | Có thể rời khỏi cấu hình đã xác thực | Kiểm tra certificate, Security Policy và hướng dẫn thay đổi |

## 18. Checklist đánh giá FIPS 140 boundary

- [ ] Xác định cryptographic module và certificate CMVP cụ thể.
- [ ] Đọc đúng Security Policy và sơ đồ boundary của phiên bản đang triển khai.
- [ ] Phân biệt physical boundary, logical boundary và các thành phần bên ngoài.
- [ ] Đối chiếu module version, firmware, software và operational environment.
- [ ] Xác định JCA/JCE provider hoặc PKCS#11 adapter nằm trong hay ngoài boundary.
- [ ] Liệt kê dịch vụ và thao tác mật mã thực tế được thực hiện.
- [ ] Theo dõi CSP/SSP từ lúc tạo/import đến lưu, sử dụng, export và zeroize.
- [ ] Xác minh approved mode và thuật toán/tham số được phép.
- [ ] Đánh giá luồng plaintext, ciphertext và DEK qua boundary.
- [ ] Kiểm tra hành vi fallback khi module không khả dụng.
- [ ] Lưu certificate, Security Policy, cấu hình và bằng chứng audit.
- [ ] Ghi rõ caveat và phần hệ thống nằm ngoài phạm vi validation.

FIPS 140 boundary xác định phạm vi chính xác của cryptographic module đã được xác thực. Muốn đưa ra kết luận đúng, phải đối chiếu certificate và Security Policy với module, phiên bản, cấu hình và luồng key thực tế; đồng thời phân biệt rõ phần xử lý bên trong module với ứng dụng, dịch vụ và hạ tầng nằm bên ngoài.
