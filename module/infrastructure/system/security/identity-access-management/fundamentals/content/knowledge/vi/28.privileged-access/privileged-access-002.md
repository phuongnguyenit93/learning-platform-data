# Privileged account — tài khoản đặc quyền

## 1. Khi nào một tài khoản được xem là đặc quyền?

**Privileged account** là tài khoản có khả năng thực hiện những hành động nhạy cảm hoặc có phạm vi tác động lớn đối với hệ thống, dữ liệu hay quyền truy cập của các chủ thể khác. Tài khoản đó có thể được con người sử dụng, được phần mềm sử dụng hoặc được dành riêng cho tình huống khẩn cấp.

Một tài khoản quản trị có thể tạo người dùng, thay cấu hình bảo mật hoặc dừng dịch vụ. Một tài khoản khác chỉ được đọc kho sao lưu nhưng kho đó chứa toàn bộ dữ liệu quan trọng của tổ chức. Cả hai đều cần được đánh giá theo tác động thực tế của quyền đang có, thay vì chỉ nhìn tên role.

Ví dụ, người dùng `lan` dùng tài khoản làm việc thông thường để đọc email và xử lý công việc hằng ngày. Khi cần thay cấu hình production, Lan dùng một ngữ cảnh quản trị được cấp đúng quyền. Việc tách hai ngữ cảnh giúp giảm khả năng một sự cố trong hoạt động thông thường kéo theo ngay quyền quản trị.

Tính đặc quyền không nhất thiết là thuộc tính cố định suốt đời của tài khoản. Một account có thể đủ điều kiện nhận quyền nhạy cảm nhưng chỉ thực sự có quyền đó trong một phiên đã được kích hoạt. Ngược lại, account có tên bình thường vẫn có thể trở thành đặc quyền vì được thêm vào một group hoặc được phép đại diện cho account mạnh hơn.

## 2. Phân biệt account, role, credential và session

Các khái niệm này liên quan với nhau nhưng không thay thế cho nhau:

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| Account | Danh tính tồn tại trong một hệ thống quản lý | Tài khoản quản trị cơ sở dữ liệu của Lan |
| Role hoặc permission | Các hành động và phạm vi được cấp | Thay cấu hình một cụm cơ sở dữ liệu |
| Credential | Bằng chứng xác thực | Khóa, token hoặc thông tin xác thực phù hợp |
| Session | Ngữ cảnh truy cập sau khi xác thực và thiết lập quyền | Phiên bảo trì production có thời hạn |

Khóa được lưu an toàn không làm mất đi tác động của role quá rộng. Token hết hạn nhanh không bảo đảm tài khoản không thể xin token mới. Gỡ một role cũng chưa chắc chấm dứt mọi phiên đang mở, vì điều đó phụ thuộc cách hệ thống thực thi quyền và quản lý phiên.

Cần phân biệt thêm **quyền quản lý account** và **quyền mà account có trên tài nguyên**. Một người không được đọc dữ liệu trực tiếp nhưng được đặt lại phương thức xác thực của quản trị viên có thể tạo ra đường tiếp cận đặc quyền gián tiếp. Vì vậy, account quản trị và các đường khôi phục account đều thuộc phạm vi cần bảo vệ.

## 3. Những dạng tài khoản đặc quyền thường gặp

| Dạng tài khoản | Khả năng nhạy cảm điển hình | Trọng tâm quản lý |
| --- | --- | --- |
| Quản trị hệ điều hành cục bộ | Cài phần mềm, sửa cấu hình hoặc tác động tiến trình trên máy | Giới hạn máy đích, người dùng và cách nâng quyền |
| Quản trị danh tính hoặc thư mục | Quản lý account, group, phương thức xác thực và một phần chính sách truy cập | Bảo vệ ranh giới danh tính và đường khôi phục |
| Quản trị nền tảng hoặc hạ tầng | Tạo, thay đổi hoặc xóa tài nguyên vận hành | Giới hạn môi trường, phạm vi quản trị và quyền ủy quyền |
| Quản trị cơ sở dữ liệu | Thay schema, phân quyền hoặc thao tác dữ liệu diện rộng | Phân biệt quyền vận hành với quyền truy cập dữ liệu |
| Quản trị ứng dụng | Đổi thiết lập, cấp quyền hoặc quản lý người dùng trong ứng dụng | Xác định tác động nghiệp vụ và phạm vi tenant |
| Service account đặc quyền | Chạy backup, triển khai, migration hoặc quản lý tài nguyên | Bảo vệ workload và mọi bên có thể đại diện cho account |
| Tài khoản truy cập của đối tác | Hỗ trợ hoặc bảo trì một phần hệ thống | Chủ sở hữu nội bộ, thời hạn và phạm vi được phép |
| Tài khoản khẩn cấp | Khôi phục quyền kiểm soát khi luồng quản trị bình thường không dùng được | Khả năng sẵn sàng, kiểm soát sử dụng và điều tra sau sự kiện |

Các loại trên không tạo thành một thứ bậc cố định cho mọi tổ chức. Quản trị viên của một ứng dụng thử nghiệm không mặc nhiên mạnh hơn người chỉ đọc dữ liệu production nhạy cảm. Mức độ đặc quyền phải xét theo hệ thống, tài nguyên và hành động cụ thể.

Tương tự, một tài khoản quản trị cục bộ không tự động có quyền quản trị toàn bộ tổ chức. Tuy nhiên, nếu người có quyền trên máy đó có thể thu được credential của một account mạnh hơn đang được sử dụng trên máy, phạm vi tác động có thể vượt khỏi quyền cục bộ ban đầu.

## 4. Nhận diện bằng khả năng thực tế

Một account cần được xem xét như tài khoản đặc quyền nếu có một hoặc nhiều khả năng sau:

1. Thay đổi người nào được truy cập hệ thống hoặc dữ liệu.
2. Tạo, thay hoặc thu hồi credential của danh tính khác.
3. Thay cấu hình xác thực, chính sách trust hoặc cơ chế khôi phục.
4. Thực thi mã, triển khai phần mềm hoặc sửa artifact được thành phần đặc quyền sử dụng.
5. Đọc hoặc thay đổi lượng lớn dữ liệu nhạy cảm, secret hay bản sao lưu.
6. Dừng dịch vụ quan trọng, thay cấu hình vận hành hoặc tác động cơ chế bảo vệ.
7. Sửa hoặc làm mất bằng chứng kiểm toán quan trọng.

Không cần account có đầy đủ các khả năng trên mới được phân loại. Quyền đặt lại MFA cho một nhóm quản trị viên có thể đã đủ nhạy cảm, ngay cả khi account không có role mang tên `Administrator`.

### Quyền trực tiếp và gián tiếp

Quyền trực tiếp xuất hiện khi account được phép thực hiện hành động nhạy cảm trên tài nguyên. Quyền gián tiếp xuất hiện khi account có thể kiểm soát một thành phần khác có quyền đó.

Ví dụ, một account có quyền sửa pipeline triển khai và pipeline được phép chạy mã dưới service account quản trị production có thể tạo ra một đường đặc quyền. Đường này phụ thuộc các kiểm soát trên pipeline, phê duyệt, artifact và danh tính runtime; không thể chỉ nhìn role trực tiếp của account đầu tiên để kết luận an toàn.

Những quan hệ cần kiểm tra gồm group, role kế thừa, chính sách trên tài nguyên, khả năng impersonate, quyền gắn account vào workload và quyền thay đổi đường cấp phát credential. Cách kết hợp chúng phụ thuộc mô hình IAM của nền tảng, không có một công thức cộng quyền áp dụng đúng cho mọi hệ thống.

### Những trường hợp dễ đánh giá thiếu

| Tình huống | Vì sao cần xem xét đặc quyền? |
| --- | --- |
| Account chỉ được đọc secret quản trị | Secret có thể cho phép hành động với quyền của một account khác |
| Account hỗ trợ được đặt lại phương thức xác thực | Có thể tác động đường đăng nhập hoặc khôi phục của chủ thể nhạy cảm |
| Account backup được đọc toàn bộ dữ liệu | Có thể gây lộ dữ liệu diện rộng dù không sửa dữ liệu nguồn |
| Account được sửa image mà dịch vụ đặc quyền sẽ chạy | Có thể kiểm soát mã chạy trong ngữ cảnh mạnh hơn nếu các bước còn lại cho phép |
| Account được sửa chính sách ghi log | Có thể làm suy giảm khả năng phát hiện và điều tra hành động đặc quyền |

## 5. Tách hoạt động thông thường và hoạt động quản trị

Với con người, một mô hình phổ biến là dùng tài khoản thông thường cho công việc hằng ngày và một tài khoản hoặc ngữ cảnh riêng cho quản trị. Mục tiêu là không mang quyền nhạy cảm vào mọi lần mở tài liệu, đọc email hoặc sử dụng ứng dụng thông thường.

Có thể tách bằng account riêng, role được kích hoạt khi cần hoặc cơ chế nâng quyền có kiểm soát. Cách triển khai phụ thuộc hệ thống, nhưng cần đạt các tính chất sau:

- Người thực hiện được định danh rõ ràng.
- Quyền quản trị không tự động xuất hiện trong mọi phiên làm việc.
- Phạm vi và thời gian có quyền phù hợp với công việc.
- Hoạt động quản trị được ghi nhận và có thể đối chiếu với người thực hiện.

Ví dụ:

| Ngữ cảnh | Hoạt động được phép |
| --- | --- |
| Tài khoản làm việc thông thường của Lan | Email, công cụ cộng tác, ứng dụng nghiệp vụ trong phạm vi được cấp |
| Ngữ cảnh vận hành cơ sở dữ liệu của Lan | Một số thao tác bảo trì trên cụm được phân công |
| Ngữ cảnh quản lý danh tính | Chỉ cấp cho người và công việc thật sự cần thay đổi account hoặc policy |

Không nên xem một account quản trị toàn năng là cách tách quyền đã đầy đủ. Ngữ cảnh quản trị vẫn cần nguyên tắc ít quyền nhất. Người vận hành cơ sở dữ liệu không nhất thiết cần quyền thay cấu hình đăng nhập của cả tổ chức.

Môi trường sử dụng account đặc quyền cũng cần được kiểm soát. Một phiên quản trị trên máy hoặc trình duyệt đã bị xâm nhập có thể làm lộ token và thao tác nhạy cảm. Việc có MFA không loại bỏ mọi rủi ro sau khi đăng nhập.

## 6. Tài khoản cá nhân và tài khoản dùng chung

Tài khoản quản trị gắn với từng người giúp liên hệ sự kiện với một cá nhân cụ thể, quản lý vòng đời khi người đó đổi vai trò hoặc rời tổ chức và áp dụng điều kiện truy cập phù hợp.

Nếu cả nhóm dùng chung một account và chia sẻ credential, log tại hệ thống đích thường chỉ cho thấy account chung. Khi xảy ra thay đổi, rất khó xác định ai đã thực hiện nếu không có bằng chứng bổ sung đáng tin cậy.

Một số hệ thống chỉ có tài khoản kỹ thuật dùng chung ở đích. Trong trường hợp đó, có thể sử dụng cơ chế môi giới truy cập: từng người xác thực bằng danh tính cá nhân, hệ thống kiểm tra quyền rồi mở một phiên được kiểm soát tới account kỹ thuật.

```text
Danh tính cá nhân
    -> kiểm tra quyền và yêu cầu truy cập
    -> phiên truy cập có mã tương quan
    -> account kỹ thuật ở hệ thống đích
    -> hành động trên tài nguyên
```

Thiết kế này cần bảo toàn quan hệ giữa người dùng ban đầu, phiên môi giới và sự kiện tại đích. Chỉ đặt một cổng truy cập ở phía trước không tự bảo đảm trách nhiệm giải trình nếu credential chung vẫn bị phân phối rộng và cho phép đăng nhập trực tiếp ngoài cổng.

Ghi hình hoặc ghi lệnh có thể hỗ trợ điều tra nhưng không tự chứng minh mọi hành động đều hợp lệ. Cần bảo vệ tính toàn vẹn của bằng chứng, kiểm soát người được xem và tránh thu thập bí mật hoặc dữ liệu nhạy cảm không cần thiết.

## 7. Tài khoản đặc quyền của phần mềm

Một service account chạy tác vụ backup, triển khai hoặc sửa hạ tầng có thể có quyền rất lớn mà không bao giờ mở màn hình đăng nhập. Vì vậy, danh sách tài khoản đặc quyền không được giới hạn ở tài khoản quản trị của con người.

Đối với account của phần mềm, cần biết:

1. Workload nào đang sử dụng danh tính đó?
2. Nhóm nào chịu trách nhiệm và quyết định vòng đời quyền?
3. Credential được cấp và làm mới bằng cách nào?
4. Những bên nào có thể tạo credential, xin token hoặc chạy mã dưới account đó?
5. Tài nguyên nào có thể bị tác động khi workload bị xâm nhập?

Không nên dùng cùng một account đặc quyền cho pipeline triển khai và tiến trình phục vụ nghiệp vụ nếu nhu cầu của chúng khác nhau. Account triển khai có thể được thay cấu hình; account runtime thường chỉ cần gọi một tập API phục vụ chức năng của ứng dụng.

Xác thực tương tác bằng MFA không phù hợp với mọi workload tự động. Thay vào đó, cần kiểm soát danh tính nguồn, chính sách trust, đường cấp credential, môi trường chạy và quyền đại diện cho account. Các thao tác quản trị account của phần mềm vẫn phải chịu kiểm soát phù hợp đối với người thực hiện.

Credential ngắn hạn hoặc danh tính do nền tảng quản lý có thể giảm việc phân phối secret dài hạn. Chúng không tự thu hẹp role đã cấp, cũng không ngăn kẻ kiểm soát workload tiếp tục xin credential nếu đường cấp phát vẫn cho phép.

## 8. Vòng đời của một privileged account

### 8.1. Tạo account theo nhu cầu đã xác định

Trước khi tạo, cần mô tả mục đích, chủ sở hữu, tài nguyên đích, quyền cần thiết và thời hạn hoặc điều kiện rà soát. Account không có chủ sở hữu rõ ràng rất dễ tồn tại sau khi nhu cầu ban đầu kết thúc.

Quyết định tạo account và cấp quyền nhạy cảm cần có sự xem xét độc lập phù hợp với mức tác động. Người yêu cầu không nên có khả năng tự tạo account, tự cấp quyền rộng và tự xóa bằng chứng mà không có kiểm soát khác.

### 8.2. Cấp quyền trong phạm vi cần thiết

Quyền cần được phân theo hành động và tài nguyên, thay vì cấp role toàn cục chỉ vì dễ vận hành. Có thể giới hạn theo môi trường, nhóm máy, cụm dữ liệu, tenant hoặc công việc cụ thể nếu cơ chế thực thi hỗ trợ.

Với quyền được kích hoạt theo yêu cầu, cần phân biệt trạng thái **đủ điều kiện** và trạng thái **đang có quyền**. Một người đủ điều kiện quản trị chưa chắc được phép thực hiện ngay mọi hành động; họ có thể cần kích hoạt, xác thực bổ sung hoặc đáp ứng điều kiện khác.

### 8.3. Sử dụng trong một ngữ cảnh có thể kiểm toán

Một phiên đặc quyền cần xác định được principal, mục tiêu, thời điểm bắt đầu, quyền đang dùng và kết quả các thao tác quan trọng. Nếu có delegation hoặc impersonation, nên giữ liên hệ với actor ban đầu theo khả năng của hệ thống.

Lý do truy cập hoặc mã yêu cầu thay đổi có thể giúp đối chiếu hành động với mục đích. Tuy nhiên, một lý do do người dùng nhập không tự làm cho hành động trở thành được phép; chính sách vẫn cần được thực thi tại điểm truy cập và tài nguyên.

### 8.4. Kết thúc quyền và xử lý phiên

Khi công việc hoàn tất hoặc thời hạn kết thúc, cần xác minh quyền không còn hiệu lực theo thiết kế. Có thể phải gỡ role tạm, đóng phiên, ngăn cấp token mới hoặc thu hồi credential.

Hết thời hạn phê duyệt không tự động đồng nghĩa mọi kết nối đang tồn tại đã bị cắt. Một số hệ thống đánh giá quyền khi bắt đầu phiên, một số đánh giá trên từng yêu cầu. Cần biết rõ cơ chế của tài nguyên đích và giới hạn thời gian phản ánh thay đổi.

### 8.5. Rà soát, vô hiệu hóa và dọn dẹp

Khi người dùng đổi công việc, đối tác kết thúc hợp đồng hoặc workload bị thay thế, cần rà soát account và quyền liên quan. Việc xóa người dùng khỏi một group không bảo đảm đã xử lý hết các credential, phiên hoặc quan hệ ủy quyền khác.

Trước khi xóa account kỹ thuật, cần kiểm tra phụ thuộc để tránh gián đoạn. Sau khi không còn nhu cầu, xử lý cả quyền, credential, trust, phiên và các bản cấu hình có tham chiếu tới account theo quy trình phù hợp.

## 9. Tài khoản khẩn cấp

Tài khoản khẩn cấp, thường được gọi là break-glass account, phục vụ việc lấy lại quyền kiểm soát khi cách quản trị bình thường không còn sử dụng được. Ví dụ, luồng liên kết danh tính gặp lỗi khiến quản trị viên không thể dùng đường đăng nhập quen thuộc.

Đường khẩn cấp cần được thiết kế để vẫn hoạt động trong kịch bản sự cố đã xác định. Nếu nó phụ thuộc hoàn toàn vào cùng thành phần đang hỏng, nó không giải quyết được kịch bản đó. Tuy nhiên, khả năng độc lập không có nghĩa được bỏ mọi yêu cầu bảo vệ.

Các nguyên tắc cần có gồm:

- Mục đích sử dụng và người chịu trách nhiệm rõ ràng.
- Phương thức bảo vệ, lưu giữ và tiếp cận credential được kiểm soát.
- Cảnh báo khi account được sử dụng và bằng chứng đủ để điều tra.
- Kiểm tra định kỳ khả năng sử dụng trong phạm vi được phép.
- Rà soát sau lần sử dụng và thay hoặc xử lý credential theo cơ chế phù hợp.

Không dùng account khẩn cấp cho bảo trì thường ngày vì như vậy sẽ biến ngoại lệ thành đường quản trị thường trực. Cũng không nên đưa ra một quy tắc chung rằng mọi account khẩn cấp phải tắt MFA; phương án xác thực cần phù hợp với kịch bản lỗi, yêu cầu sẵn sàng và mô hình bảo vệ cụ thể.

## 10. Lập danh mục và đánh giá mức rủi ro

Một danh mục privileged account có thể ghi nhận:

```text
Account: db-ops-prod-lan
Loại: tài khoản quản trị cá nhân
Chủ sở hữu sử dụng: Lan
Nhóm chịu trách nhiệm: vận hành cơ sở dữ liệu
Mục đích: bảo trì cụm dữ liệu production được phân công
Quyền nhạy cảm: thay một số cấu hình và thực hiện tác vụ vận hành đã xác định
Cách có quyền: kích hoạt role trong thời hạn được cấp
Đường truy cập: môi trường quản trị được cho phép
Quan hệ phụ thuộc: hệ thống danh tính, cơ chế truy cập và cụm dữ liệu đích
Trạng thái: đang sử dụng
Điều kiện rà soát: thay đổi vai trò, phạm vi công việc hoặc cấu hình quyền
```

Đây là mô tả quản trị, không phải cú pháp cấu hình của một sản phẩm cụ thể. Mục danh mục cũng cần liên kết tới nguồn cấu hình thực để tránh tình trạng tài liệu nói một phạm vi còn hệ thống cấp một phạm vi khác.

Khi đánh giá rủi ro, nên xét ít nhất bốn chiều:

| Chiều đánh giá | Câu hỏi |
| --- | --- |
| Phạm vi tác động | Account có thể tác động bao nhiêu hệ thống và loại dữ liệu nào? |
| Khả năng duy trì truy cập | Account có thể tạo credential, cấp thêm quyền hoặc sửa trust không? |
| Khả năng bị sử dụng sai | Ai và workload nào có thể đại diện cho account? |
| Khả năng phát hiện, thu hồi | Có thể truy vết, chặn sử dụng và xử lý phiên trong bao lâu? |

Số lượng role hoặc số permission đơn thuần không phản ánh đầy đủ rủi ro. Một quyền tạo credential cho account quản trị có thể quan trọng hơn nhiều quyền đọc metadata ít nhạy cảm.

Danh mục cũng không chỉ lấy từ một màn hình quản lý tập trung. Account cục bộ, account tích hợp ứng dụng, danh tính pipeline và tài khoản kỹ thuật của hệ thống cũ có thể tồn tại ngoài công cụ đang được dùng để quản lý truy cập đặc quyền.

## 11. Ví dụ nhận diện và xử lý

Một tổ chức có ba account sau:

| Account | Quyền hiện tại | Đánh giá |
| --- | --- | --- |
| `mai-support` | Đặt lại thông tin xác thực của một nhóm người dùng | Nhạy cảm vì có thể ảnh hưởng đường truy cập; cần xét kỹ phạm vi người dùng được hỗ trợ |
| `deploy-prod` | Triển khai mã vào dịch vụ production | Cần đánh giá cả danh tính runtime và các bước phê duyệt trước khi mã được thực thi |
| `backup-reader` | Đọc toàn bộ bản sao lưu dữ liệu khách hàng | Nhạy cảm về bảo mật dữ liệu dù không có quyền sửa dữ liệu nguồn |

Nếu chỉ tìm role có chữ `Admin`, cả ba account có thể bị bỏ sót. Cách xử lý phù hợp bắt đầu từ khả năng thực tế: giới hạn nhóm người dùng mà bộ phận hỗ trợ được tác động; kiểm soát mã, artifact và danh tính được pipeline sử dụng; giới hạn dữ liệu backup và các workload được đọc.

Sau đó kiểm chứng cả trường hợp hợp lệ và trường hợp ngoài phạm vi. Ví dụ, account hỗ trợ không được đặt lại xác thực của quản trị viên ngoài phạm vi được giao; pipeline staging không nhận được danh tính production; account backup không tự cấp thêm quyền IAM.

Những kiểm chứng này phải dùng đúng danh tính mục tiêu. Một công cụ vô tình sử dụng credential quản trị viên đang đăng nhập có thể làm kết quả thử nghiệm sai lệch.

## 12. Những ngộ nhận cần tránh

| Ngộ nhận | Cách hiểu phù hợp |
| --- | --- |
| Chỉ account tên root hoặc administrator mới là đặc quyền | Cần xét hành động, dữ liệu và các đường quyền gián tiếp |
| Đã có MFA thì account an toàn trong mọi phiên | Cần bảo vệ cả thiết bị, token, phiên và quyền sau đăng nhập |
| Tách account thường và account admin là đủ | Account admin vẫn cần giới hạn quyền, đường sử dụng và vòng đời |
| Service account không phải con người nên không thuộc quản lý đặc quyền | Account của phần mềm có thể kiểm soát tài nguyên rất nhạy cảm |
| Account dùng chung chỉ cần lưu mật khẩu trong kho secret | Cần xác định người sử dụng thực tế và ngăn đường truy cập ngoài kiểm soát |
| Hết thời hạn cấp quyền là mọi phiên lập tức kết thúc | Phải xác minh cơ chế token, phiên, cache và thực thi tại tài nguyên |
| Account khẩn cấp không cần giám sát vì ít sử dụng | Mỗi lần sử dụng cần có cảnh báo, bằng chứng và rà soát |
| Account không hoạt động thì không còn tác động | Quyền, credential và quan hệ trust có thể vẫn tồn tại |

Một privileged account cần được nhận diện qua quyền hiệu lực và khả năng đại diện cho nó. Quản lý đầy đủ bao gồm xác định chủ sở hữu, giới hạn phạm vi, kiểm soát cách sử dụng, duy trì dấu vết kiểm toán và thu hồi quyền khi mục đích hoặc điều kiện tin cậy thay đổi.
