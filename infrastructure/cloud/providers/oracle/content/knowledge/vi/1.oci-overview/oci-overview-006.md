# Mô hình trách nhiệm chung về bảo mật trên OCI

## 1. Mục tiêu và bối cảnh

Chuyển ứng dụng lên Oracle Cloud Infrastructure (OCI) thay đổi cách phân chia công việc bảo mật. Oracle vận hành hạ tầng cung cấp dịch vụ; tổ chức sử dụng dịch vụ vẫn phải bảo vệ danh tính, dữ liệu, mã ứng dụng và những cấu hình thuộc quyền kiểm soát của mình.

Ví dụ, Oracle có thể vận hành Object Storage đúng thiết kế, nhưng một bucket do khách hàng cấu hình công khai vẫn có thể làm lộ dữ liệu. Tương tự, máy ảo hoạt động trên hạ tầng được bảo vệ không bảo đảm ứng dụng Java bên trong đã được vá hoặc kiểm tra phân quyền đúng.

Bài học thuộc chương **Tổng quan Oracle Cloud Infrastructure** của module **CLOUD_PROVIDERS_ORACLE**. Nội dung giúp người học liên hệ tenancy, compartment, IAM, VCN, Compute, lưu trữ và các dịch vụ cơ sở dữ liệu Oracle với trách nhiệm triển khai, giám sát, tự động hóa, kiểm soát chi phí và duy trì tính sẵn sàng.

Sau bài học, bạn có thể:

- Phân biệt bảo mật hạ tầng đám mây và bảo mật workload sử dụng đám mây.
- Xác định phần việc của Oracle và khách hàng theo từng loại dịch vụ.
- Nhận diện các khoảng trống khi cấu hình IAM, mạng, dữ liệu, cập nhật phần mềm và ghi log.
- Chuyển một yêu cầu bảo mật thành công việc có người phụ trách và bằng chứng kiểm tra.
- Áp dụng mô hình vào một hệ thống Java dùng Compute, Object Storage và Autonomous Database.

## 2. Nguyên tắc của mô hình trách nhiệm chung

Oracle mô tả bảo mật trên OCI là trách nhiệm chung: Oracle bảo vệ hạ tầng và hoạt động cung cấp dịch vụ, còn khách hàng phải cấu hình tài nguyên an toàn và bảo vệ workload của mình. [Oracle: Shared Security Model](https://docs.oracle.com/en-us/iaas/Content/cloud-adoption-framework/security.htm)

Có thể nhìn mô hình qua hai phạm vi:

| Phạm vi | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| Security **of** the cloud | Dịch vụ đám mây được xây dựng và vận hành an toàn thế nào? | Bảo vệ trung tâm dữ liệu, phần cứng và hạ tầng mạng do Oracle vận hành |
| Security **in** the cloud | Tổ chức sử dụng dịch vụ an toàn thế nào? | Giới hạn IAM policy, bảo vệ secret, cấu hình mạng và bảo mật mã ứng dụng |

Đây không phải cách chia đều 50/50. Một dịch vụ càng được quản lý nhiều thì khách hàng càng ít trực tiếp vận hành các lớp bên dưới, nhưng vẫn phải quyết định ai được truy cập, dữ liệu nào được đưa lên và cấu hình nào đáp ứng yêu cầu của workload.

~~~mermaid
flowchart TB
    O["Oracle: hạ tầng và phần dịch vụ do Oracle vận hành"]
    C["Khách hàng: danh tính, dữ liệu, ứng dụng và cấu hình được giao"]
    O --> B["Điểm kết nối: API, cấu hình, quyền, log và thông báo"]
    C --> B
    B --> W["Workload cần được bảo vệ và kiểm chứng"]
~~~

Một kiểm soát thường gồm nhiều phần việc. Với quản lý truy cập, Oracle cung cấp cơ chế IAM; khách hàng thiết kế group, policy, quy trình cấp quyền và việc thu hồi. Với mã hóa, dịch vụ thực hiện thao tác mã hóa theo cơ chế của nó; khách hàng vẫn phải chọn cách quản lý khóa, quyền giải mã và phạm vi chia sẻ dữ liệu phù hợp.

Vì vậy, khi ghi “hai bên cùng chịu trách nhiệm”, cần tách thành các đầu việc rõ ràng. Nếu không có ai phụ trách việc rà soát quyền hoặc xử lý cảnh báo thì đó là khoảng trống vận hành, dù công cụ bảo mật đã tồn tại.

### 2.1. Ba câu hỏi để xác định ranh giới

Với mỗi thành phần, hãy trả lời:

1. **Ai vận hành lớp này?** Ví dụ Oracle vận hành máy chủ vật lý; khách hàng vận hành hệ điều hành bên trong máy ảo Compute thông thường.
2. **Ai quyết định cấu hình?** Ví dụ khách hàng quyết định mạng nào được phép tới cổng dịch vụ.
3. **Ai phải kiểm tra kết quả?** Ví dụ đội vận hành phải xác nhận cảnh báo đến đúng người và bản sao lưu có thể khôi phục.

Không suy rộng trách nhiệm từ tên nhà cung cấp. Một cơ sở dữ liệu Oracle tự cài trên Compute và một Autonomous Database đều sử dụng công nghệ Oracle, nhưng có ranh giới vận hành khác nhau.

## 3. Bảng trách nhiệm theo lớp

Bảng sau là định hướng cho workload phổ biến trên OCI public cloud. Khi triển khai, cần đối chiếu đúng dịch vụ và mô hình vận hành đang dùng; không áp nguyên bảng cho mọi biến thể Cloud@Customer hoặc dịch vụ chuyên biệt.

| Lớp hoặc kiểm soát | Phần Oracle vận hành/cung cấp | Phần khách hàng phải tổ chức thực hiện |
| --- | --- | --- |
| Trung tâm dữ liệu và phần cứng OCI | Bảo vệ và vận hành cơ sở hạ tầng thuộc dịch vụ | Chọn kiến trúc và vị trí triển khai phù hợp yêu cầu workload |
| Hạ tầng mạng đám mây | Mạng nền tảng và cơ chế cách ly dịch vụ | Thiết kế VCN, subnet, route và quy tắc truy cập |
| IAM | Nền tảng nhận dạng, xác thực và phân quyền | Bảo vệ credential, cấp quyền tối thiểu, rà soát và thu hồi quyền |
| Compute VM thông thường | Hạ tầng chạy máy ảo | Bảo vệ hệ điều hành guest, tài khoản máy chủ, runtime và ứng dụng |
| Object Storage | Vận hành dịch vụ lưu trữ | Phân quyền bucket/object, kiểm soát chia sẻ và vòng đời dữ liệu |
| Phần mềm tự cài | Hạ tầng hoặc dịch vụ bên dưới theo sản phẩm | Chọn phiên bản, cấu hình, vá và theo dõi phần mềm tự quản lý |
| Dữ liệu và nghiệp vụ | Các khả năng bảo vệ dữ liệu của dịch vụ | Phân loại dữ liệu, giới hạn truy cập và xác định cách sử dụng |
| Log và phát hiện | Cơ chế ghi nhận, giám sát hoặc phát hiện được dịch vụ cung cấp | Chọn nguồn log, cấu hình phạm vi, xử lý cảnh báo và lưu bằng chứng |
| Khôi phục hệ thống | Những khả năng sao lưu và phục hồi theo dịch vụ | Chọn mục tiêu khôi phục, cấu hình và thử phục hồi workload |
| Thiết bị truy cập OCI | Giao diện và API của dịch vụ | Bảo vệ laptop, trình duyệt, máy CI/CD và công cụ quản trị |

Oracle phân biệt trách nhiệm bảo vệ hạ tầng với trách nhiệm bảo vệ hệ điều hành, ứng dụng và tài nguyên do khách hàng cấu hình; phạm vi khách hàng quản lý còn tăng khi sử dụng bare metal và tự vận hành toàn bộ software stack. [Oracle: Security Overview](https://docs.oracle.com/en-us/iaas/Content/Security/Concepts/security_overview.htm)

Điểm quan trọng khi dùng bảng là tìm **công việc chưa được giao**, không chỉ đánh dấu cột “Oracle” hay “khách hàng”. Một bucket riêng tư hôm nay có thể bị thay đổi ngày mai; một chính sách đúng lúc triển khai có thể không còn phù hợp sau khi nhân viên chuyển vị trí.

## 4. Ranh giới thay đổi theo dịch vụ

### 4.1. Compute VM và bare metal

Với máy ảo Compute thông thường, đội vận hành phải quản lý hệ điều hành bên trong máy ảo, tài khoản đăng nhập, cấu hình SSH, phần mềm ứng dụng và quá trình cập nhật. Oracle cung cấp hạ tầng; việc giữ phần mềm do khách hàng chạy luôn được vá là công việc khách hàng cần thực hiện. [Oracle: Securing Compute](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/compute_security.htm)

Ví dụ với Java trên VM:

- Đội nền tảng cập nhật hệ điều hành và giới hạn quyền quản trị máy chủ.
- Đội ứng dụng cập nhật JDK, thư viện và mã nghiệp vụ theo phân công nội bộ.
- Hai đội phối hợp kiểm tra bản phát hành và khả năng quay lại phiên bản an toàn.

Tạo một image mới đã vá không tự thay đổi những VM đang chạy từ image cũ. Cần có phương án cập nhật tại chỗ hoặc thay thế instance và kiểm tra kết quả.

Với bare metal, không mặc định có một hypervisor Oracle quản lý thay cho khách hàng. Phần mềm khách hàng cài, kể cả lớp ảo hóa nếu tự triển khai, phải có người chịu trách nhiệm rõ ràng.

### 4.2. Cơ sở dữ liệu tự cài trên Compute

Nếu tự cài Oracle Database lên Compute, không thể xem nó là một Autonomous Database chỉ vì chạy trên OCI. Đội sử dụng phải quản lý lớp phần mềm tự cài, bản vá, cấu hình, tài khoản, sao lưu và phục hồi theo kiến trúc đã chọn.

Đây là lựa chọn đem lại quyền kiểm soát lớn nhưng cũng làm tăng số công việc phải vận hành. Cần tính cả nhân lực, cửa sổ bảo trì và khả năng xử lý sự cố khi đánh giá tổng chi phí.

### 4.3. Base Database Service

Base Database Service cung cấp các khả năng quản trị và công cụ của dịch vụ, nhưng không có nghĩa Oracle tự thực hiện mọi nhiệm vụ quản trị tenant database. Tài liệu trách nhiệm bảo mật của dịch vụ phân biệt việc Oracle bảo trì hạ tầng và đưa ra bản vá với việc quản trị viên khách hàng thực hiện, kiểm thử bản vá trên tenant instance. [Oracle: Security Guide for Base Database Service](https://docs.oracle.com/en/cloud/paas/base-database/guide/security-guide.html)

Trước khi vận hành, cần xác định cụ thể ai:

- Theo dõi và phê duyệt bản vá hệ điều hành, phần mềm cơ sở dữ liệu trong phạm vi khách hàng quản lý.
- Lên lịch, thực thi hoặc điều phối công cụ cập nhật.
- Kiểm thử kết nối và chức năng ứng dụng sau cập nhật.
- Quản lý user, quyền dữ liệu và phương án khôi phục.

“Có công cụ tự động hóa” và “Oracle chịu trách nhiệm hoàn tất công việc đó cho workload” là hai điều khác nhau.

### 4.4. Autonomous Database

Với Autonomous Database, Oracle đảm nhận nhiều tác vụ quản trị, trong đó có vá và nâng cấp các tài nguyên Autonomous Database. Khách hàng vẫn chịu trách nhiệm về bảo mật ứng dụng, quyền truy cập tài nguyên và dữ liệu, kết nối mạng, cũng như theo dõi sức khỏe và hiệu năng ứng dụng. Một số tác vụ cần khách hàng yêu cầu hoặc lựa chọn cấu hình thực hiện. [Oracle: Autonomous Database Responsibility Model](https://docs.oracle.com/en/cloud/paas/autonomous-database/shared-responsibility-model.html)

Như vậy, chọn dịch vụ này có thể giảm việc tự quản lý nền tảng database, nhưng không xử lý thay lỗi SQL injection, truy vấn trả dữ liệu sai người hoặc mật khẩu ứng dụng bị lộ.

### 4.5. Các dịch vụ được quản lý khác

Áp dụng cùng cách phân tích cho những dịch vụ như Load Balancing, API Gateway hoặc Functions: tách phần dịch vụ Oracle vận hành khỏi mã, route, backend, quyền và thiết lập mà khách hàng kiểm soát.

Không dùng nhãn IaaS hoặc PaaS như một danh sách nhiệm vụ đầy đủ. Tên dịch vụ, biến thể triển khai và cấu hình thực tế mới quyết định ai phải làm từng việc.

## 5. IAM: Oracle cung cấp cơ chế, khách hàng quyết định quyền

Trong tenancy, một policy có quyền rộng có thể cho phép sửa mạng, đọc dữ liệu hoặc tạo tài nguyên tính phí. Vì vậy, bảo vệ IAM là công việc xuyên suốt mọi dịch vụ.

Các đầu việc khách hàng cần giao rõ:

1. Dùng tài khoản cá nhân và định danh workload phù hợp thay cho tài khoản chia sẻ.
2. Bảo vệ đăng nhập bằng phương thức xác thực và MFA phù hợp.
3. Giới hạn quyền theo nhiệm vụ, môi trường và phạm vi tài nguyên.
4. Rà soát membership, vai trò quản trị và quyền của tự động hóa.
5. Thu hồi quyền, phiên và credential theo quy trình khi không còn nhu cầu.
6. Bảo vệ máy CI/CD, laptop quản trị và nơi lưu cấu hình truy cập.

Compartment giúp tổ chức tài nguyên và làm phạm vi cấp quyền. Việc đặt tài nguyên vào compartment riêng chỉ có ý nghĩa bảo vệ khi policy liên quan được thiết kế đúng; tên compartment không tự tạo thành hàng rào quyền hạn.

### 5.1. Tách ba đường kiểm soát

| Đường truy cập | Ví dụ | Câu hỏi kiểm tra |
| --- | --- | --- |
| Quản trị tài nguyên OCI | Sửa VCN, thay cấu hình bucket, quản lý instance | IAM cho phép ai thực hiện thao tác nào? |
| Sử dụng dịch vụ và dữ liệu | Đọc object hoặc kết nối tới database | Cơ chế quyền của dịch vụ và endpoint có giới hạn đúng không? |
| Nghiệp vụ ứng dụng | Người dùng xem đơn hàng hoặc tải hóa đơn | Ứng dụng đã kiểm tra người dùng có quyền với bản ghi đó chưa? |

Một người bị hạn chế quyền quản trị OCI vẫn có thể truy cập dữ liệu qua một đường được ứng dụng chia sẻ. Ngược lại, tài khoản ứng dụng ít quyền nghiệp vụ không bảo đảm credential hạ tầng dùng bên dưới cũng ít quyền.

Do đó, phải kiểm tra toàn bộ đường đi của yêu cầu thay vì chỉ xem một màn hình policy.

## 6. Mạng: hạ tầng an toàn vẫn cần cấu hình đúng

Oracle cung cấp những thành phần mạng và cơ chế kiểm soát; khách hàng lựa chọn cách kết nối chúng. VCN, subnet, route, gateway, Network Security Group (NSG) và security list cần phản ánh đúng luồng nghiệp vụ. [Oracle: Securing Networking: VCN, Load Balancers, and DNS](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/networking_security.htm)

Với một dịch vụ web thông thường, có thể thiết kế:

- Điểm tiếp nhận lưu lượng bên ngoài được xác định rõ.
- Backend ứng dụng không cần public IP nếu kiến trúc không yêu cầu.
- Database chỉ nhận những kết nối phục vụ ứng dụng và quản trị đã được duyệt.
- Đường quản trị tách khỏi đường người dùng cuối.
- Lưu lượng đi ra có mục đích và phạm vi được xem xét.

Đây là gợi ý kiến trúc, không phải cấu hình mặc định Oracle tự triển khai cho mọi ứng dụng.

### 6.1. Quy tắc mạng và quyền dữ liệu giải quyết việc khác nhau

Một NSG cho phép kết nối tới cổng database chỉ xác định đường mạng có thể đi qua. Nó không bảo đảm tài khoản database chỉ đọc đúng bảng cần thiết.

Tương tự, một subnet riêng không giải quyết lỗi phân quyền trong ứng dụng. Nếu ứng dụng có thể kết nối database bằng tài khoản quá mạnh, một lỗi ở ứng dụng vẫn có thể ảnh hưởng dữ liệu dù database không công khai trên Internet.

Khi triển khai quy tắc mạng, phải kiểm tra tất cả các lớp có liên quan: route, gateway, NSG, security list, host firewall và cấu hình lắng nghe của dịch vụ. Không kết luận đã chặn truy cập chỉ vì sửa một quy tắc trong một lớp.

### 6.2. Đường truyền riêng và mã hóa

Kết nối qua mạng riêng và bảo vệ dữ liệu bằng TLS đáp ứng những mục tiêu khác nhau. Mạng riêng giúp kiểm soát đường đi; TLS bảo vệ kết nối theo cơ chế xác thực và mã hóa của giao thức.

Với ứng dụng Java, vẫn phải cấu hình trust store, kiểm tra chứng chỉ và quản lý thời hạn chứng chỉ phù hợp. Không tắt kiểm tra chứng chỉ để “sửa nhanh” lỗi kết nối rồi xem kết nối đó là an toàn vì nằm trong VCN.

## 7. Dữ liệu, mã hóa và secret

### 7.1. Mã hóa không thay thế phân quyền

Object Storage mã hóa object ở phía máy chủ; khóa mã hóa có thể do Oracle quản lý hoặc sử dụng khóa qua Vault theo cấu hình. Việc mã hóa này bảo vệ dữ liệu lưu trữ theo cơ chế dịch vụ, không thay thế quyết định ai được đọc dữ liệu qua API. [Oracle: Object Storage Data Encryption](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/encryption.htm)

Nếu một yêu cầu đọc được hệ thống cho phép hợp lệ, dữ liệu có thể được dịch vụ giải mã để trả về. Vì vậy, bucket được mã hóa vẫn có thể làm lộ dữ liệu khi bị chia sẻ sai.

Khách hàng phải xác định:

- Loại dữ liệu và mức nhạy cảm.
- Ai được đọc, ghi, xóa hoặc chia sẻ.
- Dữ liệu được lưu ở đâu và cần lưu bao lâu.
- Cách bảo vệ bản sao, bản xuất và dữ liệu trong môi trường thử nghiệm.
- Phương án phát hiện và xử lý truy cập bất thường.

### 7.2. Bucket riêng tư và liên kết chia sẻ

Một bucket có cấu hình không công khai vẫn cần kiểm tra các đường chia sẻ khác, chẳng hạn pre-authenticated request (PAR). PAR cho phép truy cập theo URL được tạo với phạm vi và thời hạn tương ứng; vì vậy cần quản lý URL đó như một phương tiện cấp quyền, tránh đưa vào log công khai hoặc tài liệu không kiểm soát. [Oracle: Securing Object Storage](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/objectstorage_security.htm)

Khi rà soát bucket, cần xem cả policy, loại truy cập công khai, PAR, tài khoản ứng dụng và những cơ chế tích hợp khác đang dùng. Chỉ nhìn biểu tượng “private” chưa đủ để kết luận mọi dữ liệu đều được giới hạn như mong muốn.

### 7.3. Khóa mã hóa và secret ứng dụng

Khóa mã hóa và secret phục vụ những mục đích khác nhau. Một mật khẩu database hoặc token truy cập không trở thành an toàn chỉ vì dữ liệu trên ổ đĩa được mã hóa.

Quy trình vận hành nên nêu rõ:

- Ai được tạo, sử dụng, thay đổi và thu hồi khóa hoặc secret.
- Ứng dụng lấy secret bằng cơ chế nào và với định danh nào.
- Khi thay secret, các thành phần phụ thuộc được cập nhật và kiểm tra ra sao.
- Nếu khóa không khả dụng, workload nào sẽ bị ảnh hưởng.
- Làm thế nào để tránh secret xuất hiện trong mã nguồn, image, log hoặc đầu ra pipeline.

Với khóa do khách hàng quản lý, cần kiểm tra ảnh hưởng trước khi vô hiệu hóa hoặc xóa. Một hành động nhằm tăng bảo mật có thể làm mất khả năng truy cập dữ liệu nếu không xét các dịch vụ phụ thuộc.

## 8. Cập nhật phần mềm và chuỗi cung ứng

Mô hình trách nhiệm chung cần đi vào từng gói phần mềm đang chạy. Một dịch vụ cloud cập nhật nền tảng không tự cập nhật mọi thư viện mà đội ứng dụng đưa vào.

Ví dụ với ứng dụng Java trên VM, danh mục cần người phụ trách có thể gồm:

| Thành phần | Người phụ trách nội bộ gợi ý | Bằng chứng cần có |
| --- | --- | --- |
| Hệ điều hành guest | Đội nền tảng | Phiên bản đang chạy và kết quả cập nhật |
| JDK/runtime | Đội nền tảng hoặc đội ứng dụng theo thỏa thuận | Phiên bản thực tế trong môi trường triển khai |
| Thư viện Java | Đội phát triển | Danh mục phụ thuộc, kết quả rà soát và bản phát hành sửa lỗi |
| Web server hoặc reverse proxy tự cài | Đội được giao vận hành thành phần đó | Cấu hình và lịch cập nhật |
| Image hoặc gói triển khai | Đội CI/CD | Nguồn tạo, phiên bản và dấu vết phát hành |
| Mã nghiệp vụ | Đội ứng dụng | Kiểm tra xác thực, phân quyền và xử lý đầu vào |

Bảng là ví dụ phân công của tổ chức. Oracle không biết quy trình nội bộ đã giao JDK cho đội nào; khách hàng phải giải quyết điểm đó.

Quy trình xử lý lỗ hổng cần nối đủ các bước: phát hiện thành phần bị ảnh hưởng, đánh giá khả năng khai thác, chọn phương án sửa, kiểm thử, triển khai và xác minh phiên bản đã chạy. Nếu chỉ đóng cảnh báo sau khi cập nhật một file cấu hình nhưng instance chưa được thay thế, rủi ro có thể vẫn tồn tại.

Tự động hóa nên giúp thực thi quy trình này lặp lại được. Nó vẫn cần người quản lý quyền pipeline, nguồn artifact, ngoại lệ và tình huống triển khai thất bại.

## 9. Log, phát hiện và phản ứng

### 9.1. Có log khác với có khả năng phát hiện

OCI Audit tự ghi nhận các lời gọi tới những API public được hỗ trợ. Điều đó không đồng nghĩa Audit chứa mọi hành động trong hệ điều hành, mọi truy vấn SQL hoặc mọi lần ứng dụng trả dữ liệu. Phải chọn thêm log dịch vụ, database, hệ điều hành và ứng dụng theo điều cần quan sát. [Oracle: Overview of Audit](https://docs.oracle.com/en-us/iaas/Content/Audit/Concepts/auditoverview.htm)

Ví dụ, muốn điều tra một file hóa đơn bị tải trái phép, có thể cần ghép:

- Thay đổi cấu hình và quyền tài nguyên.
- Log truy cập dữ liệu của dịch vụ phù hợp.
- Log xác thực và phân quyền của ứng dụng.
- Dấu thời gian, định danh người dùng và request ID để liên kết sự kiện.

Không ghi mật khẩu, token hoặc nội dung dữ liệu nhạy cảm không cần thiết vào log. Kho log cũng cần được phân quyền, bảo vệ khỏi sửa/xóa trái phép và quản lý thời gian lưu.

### 9.2. Công cụ phát hiện vẫn cần phạm vi và người xử lý

Cloud Guard sử dụng target và detector để xác định phạm vi và vấn đề cần phát hiện. Responder cung cấp hành động khắc phục theo cơ chế và quyền được cấu hình. Khách hàng cần xác định tài nguyên nào được kiểm tra, ai xử lý vấn đề và khi nào cho phép tự động sửa. [Oracle: Getting Started with Cloud Guard](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/part-start.htm), [Oracle: About OCI Responder Recipes](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/respond-recipes-about.htm)

Không xem “đã bật Cloud Guard” là bằng chứng mọi cấu hình sai sẽ tự được sửa. Một hành động tự động cũng có thể tác động đến ứng dụng, nên phải kiểm tra quyền, phạm vi và đường khôi phục của hành động đó.

### 9.3. Bằng chứng cho một kiểm soát

Một kiểm soát như “bucket hóa đơn không được công khai” nên có:

1. Quy tắc mong muốn và phạm vi tài nguyên áp dụng.
2. Đội có trách nhiệm giữ cấu hình đúng.
3. Kết quả đọc cấu hình hiện tại và kiểm tra đường truy cập liên quan.
4. Cơ chế phát hiện thay đổi ngoài dự kiến.
5. Người nhận cảnh báo và thời hạn xử lý theo mức rủi ro.
6. Quy trình khắc phục cùng bằng chứng đã kiểm tra lại.

Cách làm này biến một khẩu hiệu bảo mật thành công việc vận hành có thể đánh giá.

## 10. Khả năng phục hồi, chi phí và tuân thủ

### 10.1. Hạ tầng sẵn sàng không thay thế thiết kế khôi phục

Oracle cung cấp hạ tầng và các khả năng hỗ trợ tính sẵn sàng. Khách hàng vẫn phải xác định mục tiêu liên tục kinh doanh, thiết kế workload và kiểm thử phương án HA/DR phù hợp. Không mặc định OCI tự sao chép và failover toàn bộ ứng dụng sang region khác. [Oracle: Shared Responsibility Model for Resiliency](https://docs.oracle.com/en-us/iaas/Content/cloud-adoption-framework/oci-shared-responsibility.htm)

Hai mục tiêu cần làm rõ:

- **RPO:** mức mất dữ liệu có thể chấp nhận, thường được thể hiện bằng khoảng thời gian.
- **RTO:** thời gian khôi phục dịch vụ mục tiêu sau gián đoạn.

Ví dụ, ứng dụng cần trở lại trong 30 phút và chấp nhận mất tối đa 5 phút dữ liệu phải có phương án phù hợp với cả hai mục tiêu. Việc đã có một bản backup không tự chứng minh đạt yêu cầu đó.

Backup, replication và tính sẵn sàng giải quyết những tình huống khác nhau. Một thay đổi dữ liệu sai có thể được sao chép sang bản replica; do đó phải kiểm tra cả khả năng phục hồi về thời điểm phù hợp và khả năng vận hành lại ứng dụng.

### 10.2. Bảo mật liên quan đến kiểm soát chi phí

Credential bị lộ hoặc quyền tạo tài nguyên quá rộng có thể dẫn đến sử dụng ngoài kế hoạch. Tổ chức cần phối hợp IAM, hạn mức phù hợp, phát hiện bất thường và quản lý tài nguyên.

OCI Budgets là cơ chế đặt ngưỡng chi tiêu mềm và cảnh báo; không nên xem ngân sách là công tắc tự động chặn mọi chi phí phát sinh khi chạm ngưỡng. [Oracle: Budgets](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/budgetsoverview.htm)

Đội phụ trách cần biết ai nhận thông báo, ai kiểm tra tài nguyên bất thường và ai có thẩm quyền cô lập hoặc dừng hoạt động gây chi phí. Các quyết định dừng workload phải xét tác động nghiệp vụ, thay vì chỉ dựa vào một cảnh báo đơn lẻ.

### 10.3. Bằng chứng của nhà cung cấp và bằng chứng của workload

Tài liệu hoặc chứng nhận của dịch vụ hỗ trợ đánh giá phần hạ tầng và quy trình do Oracle cung cấp. Tổ chức vẫn cần chứng minh cấu hình và hoạt động của chính workload đáp ứng yêu cầu đã xác định.

Ví dụ, bằng chứng kiểm soát trung tâm dữ liệu không thay thế lịch sử duyệt quyền truy cập hóa đơn. Phần việc của khách hàng gồm phân loại dữ liệu, chọn kiểm soát, lưu bằng chứng và rà soát thực tế sử dụng theo yêu cầu tổ chức.

## 11. Ví dụ: ứng dụng Java trên OCI

Giả sử nhóm phát triển xây dựng ứng dụng quản lý đơn hàng gồm:

- Load Balancer tiếp nhận HTTPS.
- Ứng dụng Java chạy trên Compute VM trong subnet ứng dụng.
- Autonomous Database lưu đơn hàng.
- Object Storage lưu file hóa đơn.
- Các nguồn log và cảnh báo phục vụ vận hành.

~~~mermaid
flowchart LR
    U["Người dùng"] --> L["Load Balancer HTTPS"]
    L --> J["Java trên Compute VM"]
    J --> D["Autonomous Database"]
    J --> O["Object Storage"]
    J --> M["Log ứng dụng và hệ điều hành"]
    L --> M
    D --> M
    O --> M
    M --> T["Đội vận hành tiếp nhận và xử lý"]
~~~

Sơ đồ là kiến trúc khái niệm. Những mũi tên tới log biểu thị nhu cầu quan sát, không khẳng định mọi loại log tự được bật và chuyển về một nơi.

### 11.1. Phân công trách nhiệm cụ thể

| Yêu cầu | Phần Oracle cung cấp/vận hành | Phần tổ chức phải hoàn thành |
| --- | --- | --- |
| VM chạy trên hạ tầng được bảo vệ | Hạ tầng Compute theo dịch vụ | Vá guest OS, quản lý tài khoản và giới hạn đường quản trị |
| Database được vận hành theo mô hình Autonomous | Phần quản trị nền tảng của dịch vụ | Quản lý quyền dữ liệu, kết nối và cấu hình ứng dụng |
| Chỉ khách hàng sở hữu đơn hàng được tải hóa đơn | Cơ chế lưu trữ và truy cập của dịch vụ | Kiểm tra quyền nghiệp vụ trước khi trả file hoặc cấp đường tải |
| Secret kết nối không bị lộ | Các cơ chế quản lý khóa/secret khi được lựa chọn | Phân quyền sử dụng, tích hợp ứng dụng và tránh ghi secret vào log |
| Truy cập bất thường được phát hiện | Nguồn log và công cụ phát hiện tương ứng | Bật nguồn cần thiết, xây cảnh báo và có người trực xử lý |
| Hệ thống có thể khôi phục | Các tính năng sao lưu và phục hồi theo sản phẩm | Chọn mục tiêu, phối hợp thành phần và diễn tập khôi phục |

Trong ví dụ này, một lỗi kiểm tra quyền tải hóa đơn nằm ở ứng dụng dù file được lưu trong dịch vụ có mã hóa. Chọn Autonomous Database cũng không làm mất trách nhiệm vá JDK trên VM ứng dụng.

### 11.2. Một đường yêu cầu cần nhiều kiểm soát

Khi người dùng tải hóa đơn, các câu hỏi cần được giải quyết gồm:

1. Người dùng đã được ứng dụng xác thực chưa?
2. Hóa đơn có thuộc đơn hàng mà người đó được phép xem không?
3. Danh tính workload chỉ được đọc đúng phạm vi lưu trữ cần thiết không?
4. Nếu tạo liên kết tải, phạm vi và thời hạn có phù hợp không?
5. Hoạt động tải có được ghi nhận mà không làm lộ dữ liệu hoặc token không?

Một thiết kế an toàn cần nối được các lớp này. Chỉ giới hạn NSG hoặc chỉ bật mã hóa không đủ để trả lời toàn bộ câu hỏi.

## 12. Xử lý sự cố: bucket hóa đơn bị chia sẻ sai

Giả sử đội vận hành phát hiện bucket chứa hóa đơn đã bị chuyển sang truy cập công khai. Chưa có bằng chứng cho thấy hạ tầng Object Storage bị xâm nhập.

### 12.1. Phần việc của khách hàng

Theo runbook đã phê duyệt, đội phụ trách cần:

1. Xác nhận đúng bucket, loại dữ liệu và thời điểm phát hiện.
2. Bảo toàn những bằng chứng cần thiết như cấu hình và lịch sử thay đổi.
3. Chặn đường chia sẻ sai và kiểm tra thêm PAR, policy hoặc credential liên quan.
4. Xác định tài khoản hoặc pipeline nào đã thực hiện thay đổi.
5. Điều tra phạm vi truy cập bằng những nguồn log phù hợp; ghi rõ phần dữ liệu chưa đủ để kết luận.
6. Xử lý credential nếu có dấu hiệu bị lộ hoặc sử dụng trái phép.
7. Sửa cấu hình nguồn, pipeline hoặc quy trình để tránh tái diễn.
8. Kiểm tra lại quyền truy cập và cập nhật hồ sơ sự cố.

Không kết luận chắc chắn “chưa bị tải dữ liệu” chỉ vì không thấy sự kiện trong một nguồn log không bao phủ thao tác đó.

### 12.2. Khi nào cần phối hợp Oracle?

Nếu có dấu hiệu lỗi cơ chế phân quyền của dịch vụ, kết quả API không khớp cấu hình, hoặc nghi vấn phần hạ tầng do Oracle vận hành, cần cung cấp thông tin kỹ thuật qua kênh hỗ trợ phù hợp: tài nguyên, region, mốc thời gian, request ID và mô tả có thể tái hiện.

Oracle xử lý phần thuộc dịch vụ do mình vận hành; khách hàng vẫn phải cô lập rủi ro và phối hợp điều tra workload của mình. Việc mở yêu cầu hỗ trợ không thay thế các bước ứng phó thuộc thẩm quyền tổ chức.

Không gửi mật khẩu, private key hoặc token bí mật trong nội dung hỗ trợ. Cung cấp dấu vết kỹ thuật đủ để điều tra bằng cơ chế trao đổi được chấp nhận.

## 13. Bài thực hành: lập hồ sơ trách nhiệm và kiểm chứng

Bài thực hành tập trung vào phân tích và kiểm tra cấu hình. Không cần tạo tài nguyên tính phí hoặc cố tình công khai dữ liệu để tạo tình huống.

### 13.1. Chuẩn bị

Chọn một kiến trúc thử nghiệm hoặc sơ đồ gồm Compute, VCN, một bucket và một dịch vụ database. Nếu đọc tài nguyên thật, chỉ dùng tài khoản có quyền phù hợp và dữ liệu thử nghiệm được cho phép.

Xác định trước tên tenancy, compartment và region cần xem. Không đánh giá nhầm môi trường phát triển thành môi trường sản xuất hoặc ngược lại.

### 13.2. Các bước thực hiện

**Bước 1 — Liệt kê các lớp.**

Ghi riêng hạ tầng, guest OS, JDK, thư viện, mạng, IAM, dữ liệu, secret, log và phục hồi. Với database, nêu rõ tự cài trên Compute, Base Database hay Autonomous Database.

**Bước 2 — Tách phần việc theo dịch vụ.**

Với từng lớp, xác định phần Oracle vận hành và phần thuộc quyền kiểm soát của tổ chức. Nếu chưa biết, đánh dấu cần xác minh bằng tài liệu dịch vụ; không tự chuyển trách nhiệm sang Oracle.

**Bước 3 — Giao người phụ trách nội bộ.**

Chọn đội nền tảng, đội ứng dụng, quản trị database hoặc đội an ninh theo thực tế. Mỗi công việc phải có đầu mối chịu trách nhiệm hoàn thành, kể cả khi nhiều đội cùng tham gia.

**Bước 4 — Chọn ba kiểm soát để kiểm tra.**

Ví dụ:

- Bucket hóa đơn không được chia sẻ ngoài phạm vi đã duyệt.
- Máy ứng dụng chỉ nhận lưu lượng từ đường đã thiết kế.
- Phần mềm Java và hệ điều hành đang chạy có thông tin phiên bản và người phụ trách cập nhật.

**Bước 5 — Thu thập bằng chứng hiện tại.**

Đọc cấu hình bucket và cơ chế chia sẻ liên quan; xem các lớp quy tắc mạng; lấy bằng chứng phiên bản từ môi trường đang chạy hoặc hệ thống quản lý được tin cậy. Không thay đổi quyền hoặc mở đường mạng chỉ để việc kiểm tra thuận tiện hơn.

**Bước 6 — Xác định cơ chế phát hiện sai lệch.**

Ghi rõ loại log, kiểm tra cấu hình hoặc công cụ phát hiện nào sẽ báo khi kiểm soát bị thay đổi. Nếu dùng Cloud Guard, xác nhận target và detector phù hợp; nếu dựa vào pipeline, xác định cách phát hiện thay đổi ngoài pipeline.

**Bước 7 — Diễn tập bằng tình huống trên giấy.**

Giả sử một kiểm soát bị vi phạm: ai nhận cảnh báo, ai có quyền xử lý, cần lưu bằng chứng gì và ai kiểm tra khôi phục? Không cần tạo vi phạm trên tài nguyên thật.

### 13.3. Mẫu hồ sơ một kiểm soát

Mẫu sau là dữ liệu minh họa cho bài tập, không phải schema cấu hình của OCI:

~~~json
{
  "control": "Invoice bucket sharing is restricted",
  "scope": "Compartment thu nghiem, bucket hoa don gia lap",
  "provider_part": "Van hanh co che luu tru va truy cap cua dich vu",
  "customer_owner": "Doi nen tang",
  "customer_action": "Kiem tra policy, public access va PAR",
  "evidence": "Ket qua doc cau hinh va kiem tra duong truy cap",
  "detection_owner": "Doi van hanh",
  "verification_status": "NOT_VERIFIED"
}
~~~

Chỉ đổi kết quả kiểm tra của hồ sơ khi đã thu thập bằng chứng. Không dùng mẫu điền sẵn làm bằng chứng rằng tài nguyên thật đang an toàn.

### 13.4. Tiêu chí hoàn thành

Bài thực hành đạt khi:

- Mỗi lớp quan trọng có ranh giới trách nhiệm được mô tả đúng theo dịch vụ đã chọn.
- Mỗi đầu việc phía khách hàng có đội phụ trách cụ thể.
- Ba kiểm soát được chọn có kết quả kiểm tra hoặc được ghi rõ chưa thể xác minh.
- Có luồng tiếp nhận, xử lý và kiểm tra lại khi phát hiện vi phạm.
- Những khoảng trống được ghi nhận thành công việc tiếp theo với người phụ trách.

## 14. Những ngộ nhận dễ tạo khoảng trống

| Ngộ nhận | Cách hiểu cần áp dụng |
| --- | --- |
| “Chạy trên OCI thì Oracle vá toàn bộ phần mềm.” | Xác định ai vận hành từng lớp; phần mềm tự quản lý vẫn cần quy trình cập nhật. |
| “Database được quản lý thì ứng dụng không cần bảo mật.” | Quyền dữ liệu, mã ứng dụng và đường kết nối vẫn phải được kiểm soát. |
| “Dữ liệu đã mã hóa nên chia sẻ rộng cũng an toàn.” | Mã hóa và phân quyền bảo vệ những khía cạnh khác nhau. |
| “Subnet riêng ngăn được mọi rủi ro.” | Cần xét quyền, luồng kết nối, phần mềm và phân quyền nghiệp vụ. |
| “Bật công cụ phát hiện là đã hoàn tất vận hành.” | Phải có phạm vi kiểm tra, người nhận và người xử lý cảnh báo. |
| “Có backup là đáp ứng khôi phục.” | Phải kiểm tra khả năng phục hồi dữ liệu và ứng dụng theo RPO/RTO. |
| “Ngân sách sẽ tự chặn mọi khoản chi vượt ngưỡng.” | Budget là ngưỡng mềm; cần thêm quy trình và kiểm soát sử dụng tài nguyên. |
| “Có chứng nhận hạ tầng thì workload tự đáp ứng mọi yêu cầu.” | Tổ chức vẫn phải đánh giá cấu hình và thực tế sử dụng của mình. |

Khi thiết kế một workload OCI, hãy chuyển từng yêu cầu bảo mật thành bốn yếu tố: **phạm vi kiểm soát, người phụ trách, cách thực hiện và bằng chứng kiểm chứng**. Cách làm đó giúp mô hình trách nhiệm chung trở thành nền tảng vận hành hằng ngày của tenancy thay vì chỉ là một sơ đồ giới thiệu dịch vụ.
