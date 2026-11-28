# Root key — Khóa gốc trong hệ thống quản lý khóa mật mã

## 1. Root key là gì?

**Root key (khóa gốc)** là khóa nằm ở cấp cao nhất trong **một miền hoặc một hệ phân cấp khóa đã xác định**, được dùng làm điểm khởi đầu tin cậy để bảo vệ, tạo ra hoặc xác thực các khóa ở cấp dưới. Root key có thể là khóa đối xứng hoặc khóa bất đối xứng, tùy mô hình và mục đích sử dụng.

Tên gọi **root** nói về *vị trí, vai trò và phạm vi tin cậy*, không tự xác định thuật toán, độ dài khóa hay cách lưu trữ. Một tổ chức có thể có nhiều root key cho nhiều hệ thống, tenant, vùng triển khai hoặc miền tin cậy; không nhất thiết tồn tại một khóa gốc duy nhất cho toàn doanh nghiệp.

Trong học phần **Phân loại key** thuộc **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, root key là khái niệm nền tảng để hiểu cách bảo vệ khóa trong suốt vòng đời: **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi và hủy**. Khi quản lý sai root key, hậu quả có thể lan xuống toàn bộ các khóa và tài sản phụ thuộc vào nó.

Ví dụ, hệ thống mã hóa dữ liệu có thể sử dụng một khóa gốc nằm trong HSM để bảo vệ các khóa mã hóa khóa (KEK). Mỗi KEK lại bảo vệ nhiều khóa mã hóa dữ liệu (DEK). Nếu chỉ một DEK bị lộ, phạm vi ảnh hưởng có thể giới hạn ở dữ liệu sử dụng DEK đó. Nếu root key bị lộ **và** kẻ tấn công tiếp cận được các khóa con đã được bọc phù hợp, nhiều miền dữ liệu có thể bị ảnh hưởng cùng lúc.

> **Ghi nhớ:** Root key là vị trí cao nhất **trong một hệ phân cấp cụ thể**. Cần chỉ rõ hệ phân cấp và thao tác mật mã của nó trước khi đánh giá tác động, quyền hạn hoặc biện pháp bảo vệ.

## 2. Root key xuất hiện ở những ngữ cảnh nào?

Thuật ngữ root key thường được dùng trong các kiến trúc khác nhau. Không nên mặc định chúng có cùng chức năng.

| Ngữ cảnh | Root key có thể là gì? | Chức năng điển hình | Điểm cần phân biệt |
| --- | --- | --- | --- |
| **Hệ phân cấp mã hóa dữ liệu** | Khóa đối xứng cấp cao, được bảo vệ trong HSM/KMS | Bọc (wrap) KEK cấp dưới, hoặc làm bí mật gốc để dẫn xuất khóa con | Không nhất thiết trực tiếp mã hóa dữ liệu ứng dụng |
| **PKI / hệ thống chứng chỉ** | Khóa riêng của Root CA | Ký chứng chỉ của Intermediate CA hoặc thực hiện các nghiệp vụ CA được quy định | Khóa công khai trong chứng chỉ gốc có thể là trust anchor; **private key** phải tuyệt đối được bảo vệ |
| **Phần cứng và secure boot** | Khóa bí mật gốc hoặc khóa công khai neo tin cậy lưu trong phần cứng | Khởi tạo chuỗi tin cậy, xác minh firmware, dẫn xuất khóa cho phần cứng | Một trust anchor công khai có thể không cần bí mật; chính sách bảo vệ phụ thuộc loại khóa |
| **Giao thức dẫn xuất khóa** | Bí mật đầu vào cấp cao (root secret) cho một cây KDF | Dẫn xuất các khóa khác nhau cho từng mục đích/ngữ cảnh | Bí mật nguồn phải có entropy đủ mạnh; các khóa con cần được tách mục đích |
| **Dịch vụ quản lý khóa trên cloud** | Khóa gốc nội bộ của dịch vụ hoặc một khóa cấp cao do khách hàng kiểm soát, theo kiến trúc nhà cung cấp | Bảo vệ các tầng khóa và thực thi thao tác mật mã | **KMS key** khách hàng nhìn thấy không đương nhiên là root key nội bộ của nhà cung cấp |

Trong bài này, trọng tâm là **root key trong hệ phân cấp quản lý khóa để bảo vệ dữ liệu**. Các phần về Root CA và phần cứng giúp tránh nhầm lẫn khi kết nối với mật mã bất đối xứng và chữ ký số.

### 2.1. Root key không đồng nghĩa với tài khoản root

**Root key** là vật liệu khóa mật mã hoặc tham chiếu đến vật liệu đó. **Root account**, tài khoản quản trị, mật khẩu và API token là các khái niệm quyền truy cập hoặc xác thực. Một người dùng có quyền quản trị KMS không nhất thiết đọc được root key bên trong HSM; ngược lại, một ứng dụng có quyền thực hiện thao tác bằng khóa cũng không nhất thiết có quyền xuất vật liệu khóa.

Đặc biệt cần tách:

- **Quản lý chính sách:** Tạo, thay đổi, phê duyệt quyền và cấu hình vòng đời khóa.
- **Sử dụng khóa:** Yêu cầu Wrap/Unwrap, Encrypt/Decrypt, Sign/Verify theo quyền được cấp.
- **Truy xuất vật liệu khóa:** Lấy khóa dạng rõ ra ngoài ranh giới bảo vệ. Với root key, thao tác này thường cần bị cấm hoặc giới hạn rất nghiêm ngặt.

## 3. Root key nằm ở đâu trong hệ phân cấp?

Một mô hình phổ biến của **envelope encryption** có ba tầng: root key, KEK và DEK.

~~~mermaid
flowchart TD
    R["Root key<br/>Giữ trong HSM / ranh giới bảo vệ cao"]
    K1["KEK tenant A<br/>Được root bảo vệ"]
    K2["KEK tenant B<br/>Được root bảo vệ"]
    D1["DEK A-01<br/>Được KEK A bảo vệ"]
    D2["DEK A-02<br/>Được KEK A bảo vệ"]
    D3["DEK B-01<br/>Được KEK B bảo vệ"]
    C1["Ciphertext A-01"]
    C2["Ciphertext A-02"]
    C3["Ciphertext B-01"]
    R -->|"Wrap / bảo vệ"| K1
    R -->|"Wrap / bảo vệ"| K2
    K1 -->|"Wrap"| D1
    K1 -->|"Wrap"| D2
    K2 -->|"Wrap"| D3
    D1 -->|"Encrypt"| C1
    D2 -->|"Encrypt"| C2
    D3 -->|"Encrypt"| C3
~~~

Sơ đồ này là **mô hình khái niệm**, không phải tuyên bố rằng mọi KMS đều có thể nhìn thấy hoặc cấu hình trực tiếp tầng root theo cách trên. Dịch vụ thực tế có thể sử dụng thêm các khóa nội bộ, nhiều lớp wrap hoặc kiến trúc khác.

| Tầng | Nhiệm vụ | Phạm vi phụ thuộc thường gặp | Quy tắc bảo vệ |
| --- | --- | --- | --- |
| **Root key** | Bảo vệ hoặc dẫn xuất khóa cấp cao dưới nó | Nhiều KEK, miền hệ thống hoặc nhóm dữ liệu | Quyền rất hạn chế, ưu tiên HSM và thao tác không xuất khóa |
| **KEK (Key Encryption Key)** | Bọc/giải bọc các DEK hoặc khóa con | Nhiều DEK, có thể chia theo tenant/môi trường | Giới hạn mục đích, workload và phạm vi dữ liệu |
| **DEK (Data Encryption Key)** | Mã hóa/giải mã dữ liệu ứng dụng | Một đối tượng, lô bản ghi, tệp hoặc nhóm dữ liệu | Hạn chế lộ dạng rõ, quản lý nonce và phiên bản |

**Root key và KEK không phải hai loại loại trừ nhau.** Một root key có thể **đóng vai trò KEK** ở tầng cao nhất. Từ “root” nhấn mạnh vị trí trong cây; “KEK” nhấn mạnh chức năng mã hóa/bọc khóa khác. Tương tự, một khóa có tên “master key” chỉ có nghĩa chính xác khi tài liệu thiết kế chỉ rõ chức năng và quan hệ với các khóa con.

### 3.1. Hai cách sử dụng root key thường gặp

**Cách A — Bảo vệ khóa con bằng key wrapping:** Một KEK được sinh ngẫu nhiên và được bọc bằng root key, sử dụng cơ chế bọc khóa thích hợp. Khi được phép sử dụng, hệ thống giải bọc KEK trong ranh giới bảo mật cần thiết, rồi dùng KEK để bảo vệ DEK. Root key vẫn nằm trong HSM/KMS, nếu dịch vụ hỗ trợ thao tác này mà không xuất khóa gốc.

**Cách B — Dẫn xuất khóa con bằng KDF:** Khóa hoặc bí mật gốc có entropy đủ mạnh làm đầu vào cho một **Key Derivation Function** phù hợp như HKDF (với trường hợp và loại khóa được hỗ trợ). Tham số ngữ cảnh xác định miền, mục đích và phiên bản để tạo các khóa con khác nhau.

~~~text
rootSecret = bí mật gốc có entropy phù hợp, lưu trong ranh giới tin cậy

tenantKeyA = KDF(rootSecret, salt, info="tenant:A|wrap|v1", length=...)
tenantKeyB = KDF(rootSecret, salt, info="tenant:B|wrap|v1", length=...)

tenantKeyA và tenantKeyB dùng cho các miền riêng biệt.
Các tham số thuật toán và độ dài đầu ra phải được quy định rõ.
~~~

Đây là **mã giả để hiểu nguyên tắc**, không phải hướng dẫn tự xây dựng KMS. Thực tế cần chọn KDF đúng chuẩn, xử lý salt/ngữ cảnh nhất quán và có chính sách phiên bản, sao lưu, quyền sử dụng. Dẫn xuất khóa không làm bí mật yếu trở nên có entropy cao. Nếu root secret bị lộ, kẻ tấn công có thể dẫn xuất lại các khóa con khi có đủ tham số liên quan.

## 4. Mục tiêu bảo mật khi quản lý root key

Root key thường có phạm vi ảnh hưởng rộng, vì vậy mức bảo vệ cần tương ứng với các khóa và tài sản phụ thuộc.

### 4.1. Bí mật và giới hạn lộ vật liệu khóa

Đối với **root key bí mật**, yêu cầu là chỉ những thành phần thật sự cần thiết mới được sử dụng; càng ít thành phần có thể nhìn thấy khóa dạng rõ càng tốt.

- Sinh khóa trong **CSPRNG** đáng tin cậy hoặc HSM theo quy trình được kiểm soát.
- Ưu tiên lưu và sử dụng root key trong **HSM** hoặc một ranh giới KMS có kiểm soát. Khi kiến trúc hỗ trợ, đặt chế độ **non-exportable** để vật liệu khóa không được xuất ra API ứng dụng.
- Tránh nhúng root key trong mã nguồn, cấu hình, biến môi trường, bản build, ảnh container, log hoặc cơ sở dữ liệu cùng ciphertext.
- Kiểm soát bộ nhớ tiến trình, crash dump, kênh truyền và bản sao lưu của mọi thành phần được phép xử lý khóa.

**Non-exportable không đồng nghĩa với không thể bị lạm dụng.** Nếu kẻ tấn công chiếm được workload có quyền Wrap/Unwrap hoặc Sign, họ có thể yêu cầu HSM/KMS thực hiện phép toán được cấp quyền. Vì thế, quyền gọi thao tác cũng là tài sản cần bảo vệ.

### 4.2. Toàn vẹn, nguồn gốc và tính xác thực

Hệ thống cần chứng minh mình đang sử dụng **đúng root key**, đúng phiên bản và đúng mục đích. Metadata như **rootKeyId**, loại thuật toán, phiên bản, trạng thái, quyền và quan hệ phụ thuộc phải được bảo vệ trước sửa đổi trái phép.

Ví dụ, nếu một khóa gốc khác bị gán nhầm cho các KEK đã wrap, thao tác giải bọc sẽ thất bại hoặc gây mất khả năng truy cập. Với Root CA, việc thay khóa công khai neo tin cậy có thể khiến hệ thống xác minh chữ ký của một đối tượng không được tin cậy.

### 4.3. Sẵn sàng và khôi phục

Khi root key bị mất mà không có cơ chế phục hồi hợp lệ, nhiều KEK hoặc khóa con có thể không còn sử dụng được; dữ liệu vẫn tồn tại ở dạng mã hóa nhưng không thể giải mã.

Các hệ thống có yêu cầu khôi phục phải thiết kế **backup/replication theo chính sách**, quy trình phục hồi được kiểm thử và sự phụ thuộc giữa các phiên bản khóa. Đối với root key, bản sao dự phòng phải có mức bảo vệ tương đương bản chính. Không nên mặc định mọi dịch vụ KMS cho phép khách hàng sao lưu hay khôi phục vật liệu khóa gốc: phải đối chiếu khả năng thực tế của nền tảng.

### 4.4. Kiểm soát quyền và tách nhiệm vụ

Root key thường cần mô hình **least privilege** và **separation of duties** nghiêm ngặt:

1. Ứng dụng nghiệp vụ chỉ được dùng API mật mã cần thiết; thường không có quyền quản trị root.
2. Người vận hành không mặc nhiên vừa có quyền tạo bản sao, thay chính sách, sử dụng, vừa xóa root key.
3. Các thao tác nhạy cảm như kích hoạt, xuất khóa (nếu có hỗ trợ), phục hồi, thay chính sách hoặc hủy có thể yêu cầu **dual control/quorum** (nhiều người phê duyệt).
4. Quyền phải được ràng buộc với danh tính workload, môi trường, tenant, mục đích, điều kiện và phạm vi khóa.

Một số mô hình HSM sử dụng **split knowledge** hoặc cơ chế chia sẻ bí mật như Shamir's Secret Sharing để bảo vệ một bí mật nhất định trong quy trình phục hồi. Đây là một lựa chọn kiến trúc, **không phải tính năng mặc định của mọi KMS/HSM**. Phải thiết kế và thử quy trình phục hồi thật trước khi dựa vào nó.

### 4.5. Kiểm toán và khả năng điều tra

Cần ghi lại việc **tạo, nhập (nếu được phép), kích hoạt, sử dụng, đổi quyền, xoay vòng, vô hiệu hóa, phục hồi và hủy** root key. Log nên chứa danh tính, thao tác, key ID/phiên bản, thời điểm, kết quả và ngữ cảnh phù hợp.

Không ghi root key dạng rõ, plaintext, private key, thông tin xác thực hoặc bí mật phục hồi vào log. Bảo vệ log khỏi sửa/xóa trái phép và cảnh báo các sự kiện như thay chính sách bất thường, tăng đột biến Unwrap, yêu cầu từ danh tính mới hoặc thao tác hủy ngoài quy trình.

## 5. Vòng đời root key và những điểm cần kiểm soát

| Giai đoạn | Yêu cầu đối với root key | Lỗi thường gặp |
| --- | --- | --- |
| **Thiết kế/tạo** | Xác định miền tin cậy, thuật toán, độ dài khóa, nơi sinh, quyền và người chịu trách nhiệm; sinh khóa ngẫu nhiên hoặc tạo cặp khóa theo chuẩn | Sử dụng secret yếu, dùng chung root cho các môi trường không liên quan |
| **Cấp phát/khởi tạo** | Đưa khóa vào ranh giới tin cậy với quy trình xác thực, kiểm soát nhiều người nếu cần; ghi nhận key ID và phiên bản | Truyền khóa qua kênh không an toàn, thay khóa không rõ nguồn |
| **Lưu trữ** | Giữ trong HSM/KMS hoặc hệ bảo vệ tương ứng; kế hoạch khôi phục và quản lý bản sao có kiểm soát | Sao lưu root key dạng rõ, để cạnh tập KEK đã wrap |
| **Sử dụng** | Chỉ thao tác đúng chức năng, đúng chủ thể và đúng phạm vi; giám sát các sự kiện bất thường | Cấp quyền Unwrap hoặc Sign quá rộng cho ứng dụng |
| **Xoay vòng** | Có phiên bản root mới và kế hoạch chuyển toàn bộ phụ thuộc, đồng thời giữ khả năng truy cập dữ liệu cũ | Hủy root cũ trước khi KEK/chuỗi chứng chỉ liên quan được chuyển đổi |
| **Vô hiệu hóa/thu hồi** | Chặn quyền sử dụng theo chính sách, xử lý phiên, cache, bản sao và các tin cậy liên quan | Chỉ tắt một alias trong khi đường sử dụng khác vẫn hoạt động |
| **Hủy** | Xác nhận không còn nghĩa vụ đọc/xác minh hoặc dữ liệu phụ thuộc, phê duyệt theo quy trình; xử lý mọi bản sao khả dụng | Hủy nhầm làm mất dữ liệu dài hạn hoặc còn bản sao khóa ở nơi kém an toàn |

### 5.1. Xoay vòng root key khác xoay vòng DEK

Giả sử root v1 đang bảo vệ KEK của các tenant A/B. Khi triển khai root v2:

1. Tạo root v2 trong ranh giới tin cậy; đặt chính sách và kiểm thử khả năng sử dụng.
2. Lập danh sách **mọi KEK/khóa con** đang phụ thuộc root v1 cùng phiên bản, môi trường và trạng thái.
3. Nếu dùng wrapping, thực hiện **unwrap/rewrap** KEK bằng root v1 và root v2 trong ranh giới được bảo vệ, hoặc dùng chức năng chuyển đổi khóa do KMS/HSM hỗ trợ.
4. Nếu dùng dẫn xuất bằng KDF, các khóa con dẫn xuất từ root mới thường **khác** khóa cũ. Phải chuyển đổi vật liệu được bảo vệ hoặc duy trì khóa cũ theo chính sách cho đến khi chuyển đổi xong.
5. Cập nhật metadata và quy tắc chọn phiên bản; kiểm thử toàn bộ các đường đọc/giải mã trước khi ngừng sử dụng root v1.
6. Chỉ vô hiệu hóa/hủy root v1 sau khi xác định không còn phụ thuộc cần thiết và đáp ứng yêu cầu lưu giữ, khôi phục, kiểm toán.

**Không mặc định “rotate root” tự động mã hóa lại dữ liệu.** Trong hệ bọc khóa nhiều tầng, rewrap KEK có thể không cần mã hóa lại ciphertext do DEK tạo ra. Nhưng nếu đổi chính DEK, phải mã hóa lại dữ liệu phụ thuộc. Hành vi thật phụ thuộc API, thuật toán và kiến trúc KMS/HSM.

### 5.2. Root key bị lộ hoặc nghi bị lạm dụng

Root key bị lộ có thể ảnh hưởng **nhiều khóa con** và nhiều phiên bản dữ liệu; hành vi lạm dụng quyền Sign/Unwrap cũng có thể gây hậu quả lớn ngay cả khi root key không xuất khỏi HSM.

Quy trình ứng phó cần:

- Chặn danh tính/quyền hoặc endpoint đáng ngờ, cô lập phạm vi bị ảnh hưởng và bảo toàn log phục vụ điều tra.
- Xác định root key, các khóa con, tenant, môi trường và dữ liệu phụ thuộc; kiểm tra đường sử dụng khóa và bản sao.
- Tạo root mới và chuyển đổi khóa/con đường mật mã theo kế hoạch; đánh giá nhu cầu thay DEK và mã hóa lại dữ liệu.
- Nếu là khóa ký, xác định chữ ký/chứng chỉ đã phát hành, quy trình thu hồi, phân phối trust anchor mới và tác động đến xác minh.
- Nhận diện dữ liệu đã bị giải mã hoặc chữ ký đã bị tạo trái phép; việc thay khóa **không thể tự thu hồi** plaintext đã bị sao chép hay chữ ký đã tồn tại.

## 6. Root key trong PKI và chữ ký số

Trong **Public Key Infrastructure (PKI)**, Root CA thường có một cặp khóa bất đối xứng:

- **Root CA private key:** Bí mật, dùng để ký chứng chỉ của các CA cấp dưới và những nghiệp vụ được chính sách CA cho phép. Với hệ thống lớn, khóa riêng có thể được giữ trong HSM và **Root CA thường vận hành offline** để giảm nguy cơ bị chiếm quyền.
- **Root CA public key:** Thường được phân phối trong chứng chỉ gốc. Hệ thống tin cậy khóa công khai này như **trust anchor** theo chính sách quản lý chứng chỉ. Khóa công khai không cần bí mật nhưng nguồn gốc của nó phải được bảo vệ.
- **Intermediate CA private key:** Ký chứng chỉ cấp dưới hoặc chứng chỉ end-entity tùy chuỗi CA; giúp giới hạn tác động vận hành so với việc dùng Root CA private key cho mọi thao tác thường ngày.

~~~mermaid
flowchart TD
    RA["Root CA<br/>Khóa riêng ký CA cấp dưới"]
    IA["Intermediate CA<br/>Khóa riêng ký chứng chỉ dịch vụ"]
    EE["Chứng chỉ TLS của dịch vụ<br/>Public key và định danh"]
    RV["Bộ xác minh<br/>Trust anchor được quản lý"]
    RA -->|"Ký chứng chỉ CA"| IA
    IA -->|"Ký chứng chỉ dịch vụ"| EE
    RV -.->|"Kiểm tra chuỗi tin cậy"| EE
~~~

Ở đây, Root CA private key phục vụ **chữ ký/chứng thực**, khác với root key đối xứng dùng **key wrapping**. Việc **xoay vòng Root CA** liên quan đến phân phối trust anchor, tương thích client, chứng chỉ đang sử dụng và chính sách thời gian hiệu lực; không thể áp dụng nguyên xi quy trình rewrap KEK.

**Lưu ý:** Việc một chứng chỉ Root CA thường tự ký (self-signed) không tự khiến nó đáng tin. Mức tin cậy đến từ quá trình quản lý và phân phối trust anchor đúng cách. Cũng không nên nhầm việc thu hồi chứng chỉ với xóa private key: chúng xử lý các khía cạnh khác nhau của tin cậy và vòng đời.

## 7. Ví dụ thực tế: ứng dụng Java dùng KMS nhưng không đọc root key

Giả sử dịch vụ Java lưu hồ sơ khách hàng, dùng **AES-GCM** với DEK riêng cho từng nhóm dữ liệu. KMS/HSM quản lý KEK và các tầng khóa cao hơn. Ứng dụng chỉ được yêu cầu tạo DEK và giải bọc DEK khi người dùng có quyền truy cập bản ghi.

~~~text
Kiến trúc (minh họa):

  Root key nội bộ KMS/HSM
      └── Bảo vệ KEK của ứng dụng (tenant-specific, versioned)
              └── Wrap DEK AES cho từng tập dữ liệu
                      └── AES-GCM mã hóa bản ghi

Khi ghi:
  1. Xác thực người dùng + kiểm tra quyền ghi của tenant.
  2. Gọi KMS tạo DEK theo KEK và encryption context tương ứng.
  3. Dùng DEK rõ tạm thời để mã hóa AES-GCM với nonce duy nhất.
  4. Lưu ciphertext, nonce, tag, wrapped DEK, key ID/version, metadata.
  5. Giảm tối đa thời gian lưu DEK rõ trong bộ nhớ.

Khi đọc:
  1. Xác thực người dùng + kiểm tra quyền đọc bản ghi/tenant.
  2. Đọc wrapped DEK và metadata gắn với ciphertext.
  3. Yêu cầu KMS giải bọc DEK theo quyền workload và context.
  4. Dùng DEK để kiểm tra tag/AAD, giải mã; từ chối khi xác thực lỗi.
  5. Ghi log key ID, thao tác, quyết định quyền và kết quả; không ghi key rõ.
~~~

Trong luồng này, ứng dụng không biết vật liệu root key. Nếu KMS thực tế không công bố tầng root nội bộ, ứng dụng cũng **không nên giả định** root key nằm ở cấp nào, sử dụng thuật toán nào hoặc có thể rotate trực tiếp. Kiến trúc phải dựa trên hợp đồng API và tài liệu của dịch vụ đang dùng.

Một thiết kế Java tốt nên **tham chiếu đến key ID/alias** thay vì chứa bytes của root key trong source code. Dưới đây là ví dụ về ranh giới API ở mức khái niệm:

~~~java
// Interface minh họa của ứng dụng, không phải SDK của nhà cung cấp KMS.
interface KeyService {
    WrappedDataKey generateDataKey(String kekId, String context);

    byte[] unwrapDataKey(
            String kekId,
            byte[] wrappedKey,
            String context
    );
}

record WrappedDataKey(byte[] plaintextDek, byte[] wrappedDek) {}

// Business service chỉ biết kekId/context; không nhận root key.
// Quyền và chính sách thao tác được thực thi ở KMS/HSM.
~~~

Ví dụ này nhằm minh họa **phân quyền theo tầng**. Thực tế, trả DEK rõ khiến ứng dụng phải bảo vệ byte trong bộ nhớ; có thể dùng API không xuất khóa hoặc thao tác trong HSM nếu mô hình và hiệu năng phù hợp. Để chạy ứng dụng thật cần triển khai adapter KMS, kiểm tra quyền nghiệp vụ, xử lý lỗi, quản lý nonce/AAD và chính sách vòng đời hoàn chỉnh.

## 8. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả tiềm ẩn | Cách khắc phục |
| --- | --- | --- |
| Một root key được dùng chung không kiểm soát cho mọi môi trường và tenant | Khi bị lộ, phạm vi ảnh hưởng lan rộng | Chia miền tin cậy, phân tách root/KEK hoặc giới hạn quyền phù hợp |
| Root key tồn tại dạng rõ trong file cấu hình hoặc repository | Rò rỉ qua Git, pipeline, backup hoặc quyền truy cập máy | Sinh/lưu trong HSM/KMS, giới hạn xuất khóa, thay và xử lý khóa đã lộ |
| Ứng dụng có quyền quản trị/xóa root key cùng quyền giải mã | Một workload bị chiếm có thể lạm dụng hoặc phá hủy hệ thống | Tách người quản trị, ứng dụng và người phê duyệt; least privilege |
| Không có danh sách khóa phụ thuộc và phiên bản | Xoay vòng hoặc hủy nhầm gây lỗi giải mã hàng loạt | Lưu key ID/version, metadata quan hệ root–KEK–DEK và kế hoạch migration |
| Giữ duy nhất một bản root key, không có phương án khôi phục khi cần | Lỗi phần cứng hoặc xóa nhầm có thể làm mất dữ liệu | Dùng cơ chế dự phòng, khôi phục được hỗ trợ và kiểm thử định kỳ |
| Tưởng rằng root key không xuất được thì không thể bị khai thác | API được phép vẫn có thể bị gọi trái mục đích | Ràng buộc danh tính, ngữ cảnh, giám sát và quyền nghiệp vụ |
| Dùng Root CA private key để ký mọi chứng chỉ dịch vụ hàng ngày | Tăng bề mặt tấn công đối với điểm neo tin cậy | Phân tầng Root CA/Intermediate CA, bảo vệ khóa gốc và quy trình ký |
| Đổi root key nhưng bỏ qua các bản sao, cache và dữ liệu cũ | Dữ liệu mất khả năng đọc hoặc khóa đã lộ vẫn dùng được | Kiểm kê phụ thuộc, chuyển đổi có kiểm thử, thu hồi và xử lý bản sao |

## 9. Checklist đánh giá root key

Trước khi đưa một kiến trúc quản lý khóa vào production, hãy trả lời:

1. **Định nghĩa:** Root key đang nói đến khóa mã hóa gốc, bí mật dẫn xuất, Root CA private key hay trust anchor phần cứng?
2. **Phạm vi:** Khóa bảo vệ những hệ thống, tenant, môi trường và loại dữ liệu nào? Có phân vùng hợp lý để hạn chế phạm vi sự cố không?
3. **Tạo và lưu:** Khóa được sinh ở đâu, bằng cơ chế nào và có thể bị xuất dạng rõ không?
4. **Quyền:** Ai được quản trị, ai được Wrap/Unwrap hoặc Sign, ai được phê duyệt thao tác nhạy cảm?
5. **Tin cậy:** Hệ thống xác thực được đúng key ID, phiên bản, mục đích và chuỗi tin cậy hay không?
6. **Phụ thuộc:** Có theo dõi được KEK, DEK, chứng chỉ và dữ liệu nào phụ thuộc root key không?
7. **Khôi phục:** Nếu HSM/KMS lỗi hoặc root key mất, có cơ chế phục hồi hợp lệ và đã kiểm thử không?
8. **Xoay vòng:** Có phương án chuyển đổi khóa con, dữ liệu và trust anchor trước khi khóa cũ ngừng hoạt động không?
9. **Thu hồi/hủy:** Biện pháp vô hiệu hóa có xét đến bản sao, phiên bản cũ, dữ liệu đang lưu và nghĩa vụ lưu trữ không?
10. **Kiểm toán:** Có thể điều tra mọi thay đổi và thao tác quan trọng mà không làm lộ vật liệu khóa không?

## 10. Tổng kết

- **Root key** là khóa cấp cao nhất trong một miền phân cấp khóa xác định; vai trò thực tế phụ thuộc kiến trúc.
- Trong hệ mã hóa dữ liệu, root key có thể **bảo vệ KEK**; KEK bảo vệ **DEK**; DEK mã hóa dữ liệu. Root key cũng có thể là bí mật đầu vào cho **KDF**.
- Trong **PKI**, root private key là khóa ký của Root CA, còn khóa công khai được quản lý như **trust anchor**. Vai trò này khác với khóa đối xứng dùng để wrap DEK.
- **KMS/HSM** giúp giới hạn tiếp xúc với vật liệu khóa, nhưng vẫn phải kiểm soát danh tính, thao tác được phép, metadata, cache, kiểm toán và quyền nghiệp vụ.
- Root key cần được bảo vệ xuyên suốt **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi và hủy**. Sai sót ở cấp root có thể tác động đến nhiều khóa và tài sản phụ thuộc hơn sai sót ở cấp DEK.

Khi thiết kế hệ thống bảo vệ khóa, hãy xác định **root key nào, nằm ở miền tin cậy nào, bảo vệ các khóa con nào và điều gì xảy ra khi nó bị lộ hoặc mất**. Những câu hỏi đó quyết định cách phân quyền, phục hồi, xoay vòng và ứng phó sự cố.
