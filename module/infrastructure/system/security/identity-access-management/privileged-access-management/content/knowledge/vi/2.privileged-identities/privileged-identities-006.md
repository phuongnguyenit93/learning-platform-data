# Database administrator identity

## Mục tiêu bài học

Trong chương **Danh tính đặc quyền**, database administrator identity là danh tính được trao khả năng quản trị một phần hoặc toàn bộ môi trường cơ sở dữ liệu. Danh tính này có thể thuộc về một DBA, người vận hành được ủy quyền hoặc một tác vụ tự động thực hiện công việc quản trị.

Trong phạm vi **Privileged Access Management (PAM)**, cần kiểm soát cả danh tính quản trị, quyền được cấp, credential, đường kết nối, phiên làm việc và bằng chứng thao tác. Mục tiêu là để người hoặc tác vụ phù hợp thực hiện đúng công việc trên đúng cơ sở dữ liệu, với quyền và thời gian cần thiết.

Sau bài học, bạn có thể:

- Phân biệt danh tính DBA với danh tính ứng dụng và các danh tính quản trị liên quan.
- Nhận diện quyền trực tiếp, quyền gián tiếp và phạm vi tác động của một DBA.
- Thiết kế kiểm soát least privilege, JIT/JEA, vault và luân chuyển credential phù hợp với hoạt động cơ sở dữ liệu.
- Giải thích vì sao đổi mật khẩu hoặc hết hạn cấp quyền chưa chắc đã kết thúc một phiên đang hoạt động.
- Xác định bằng chứng cần thiết để kiểm toán, điều tra và khôi phục sau sự cố.

## 1. Danh tính DBA là gì?

Một danh tính thuộc phạm vi quản trị cơ sở dữ liệu khi nó có thể thực hiện những hành động như:

- Tạo, sửa hoặc xóa cơ sở dữ liệu, schema, đối tượng hay cấu hình.
- Quản lý tài khoản, vai trò, quyền và quan hệ thành viên.
- Thực hiện bảo trì hoặc điều khiển phiên, truy vấn và tác vụ.
- Quản lý sao lưu, phục hồi hoặc sao chép dữ liệu.
- Thay đổi cấu hình audit, mã thực thi bên trong cơ sở dữ liệu hoặc cơ chế bảo vệ khác.

Không phải mọi DBA đều cần tất cả các quyền trên. Một người phụ trách hiệu năng có thể cần xem thông tin vận hành và thực hiện một số thao tác bảo trì, nhưng không cần quyền cấp vai trò quản trị hay xuất toàn bộ dữ liệu khách hàng.

Ngược lại, một tài khoản không mang tên DBA vẫn có thể có quyền quản trị. Ví dụ:

- Tài khoản migration sở hữu schema và được sửa cấu trúc dữ liệu.
- Tài khoản triển khai được thay đổi thủ tục lưu trữ chạy với quyền cao.
- Danh tính quản trị nền tảng có thể phục hồi bản sao dữ liệu sang một môi trường khác.
- Tài khoản có quyền cấp một vai trò mạnh cho chính mình hoặc cho người khác.

Cần nhận diện DBA bằng **khả năng và đường sử dụng quyền**, không chỉ bằng chức danh hoặc tên vai trò.

## 2. Tách danh tính, credential, vai trò và phiên

Các khái niệm này liên quan nhưng không thay thế nhau:

| Khái niệm | Ý nghĩa | Câu hỏi kiểm soát |
| --- | --- | --- |
| Danh tính | Chủ thể mà hệ thống xác thực và ghi nhận | Ai hoặc tác vụ nào đang truy cập? |
| Credential | Phương tiện chứng minh danh tính | Mật khẩu, khóa, chứng thư hoặc token được quản lý thế nào? |
| Vai trò và quyền | Khả năng được cấp cho chủ thể | Được làm gì, trên đối tượng và phạm vi nào? |
| Phiên hoặc kết nối | Ngữ cảnh đang tương tác với hệ thống đích | Khi nào bắt đầu, đang dùng quyền gì và kết thúc bằng cách nào? |

Tùy hệ quản trị, khái niệm login, database user, role, group và owner có thể được tổ chức khác nhau. Không nên giả định rằng cùng một tên gọi sẽ có cùng ngữ nghĩa trên mọi sản phẩm.

Một người có thể:

1. Đăng nhập vào hệ thống PAM bằng danh tính cá nhân.
2. Được chấp nhận một yêu cầu quản trị có thời hạn.
3. Mở kết nối tới cơ sở dữ liệu dưới một principal được cho phép.
4. Thực hiện công việc trong một hoặc nhiều phiên.
5. Kết thúc phiên và bị thu hồi quyền theo chính sách.

Nếu phía cơ sở dữ liệu dùng tài khoản kỹ thuật chung, cần bằng chứng liên kết nó với người và phiên tương ứng. Chỉ biết ai từng lấy mật khẩu không đủ chứng minh ai đã thực hiện từng thao tác sau đó.

## 3. Phân biệt DBA với các danh tính lân cận

| Danh tính | Nhiệm vụ chính | Điểm cần tách hoặc kiểm tra |
| --- | --- | --- |
| Người dùng nghiệp vụ | Sử dụng chức năng và dữ liệu được giao | Không mặc định cần thay đổi schema hay cấp quyền |
| Danh tính ứng dụng | Thực hiện truy vấn phục vụ ứng dụng | Không dùng tài khoản quản trị tổng quát chỉ để đơn giản hóa kết nối |
| Danh tính migration | Thay đổi cấu trúc theo đợt phát hành | Nên tách khỏi quyền chạy thường xuyên của ứng dụng khi có ranh giới phù hợp |
| DBA vận hành | Bảo trì, xử lý hiệu năng, điều khiển hoạt động được giao | Cần giới hạn phạm vi, thao tác và môi trường |
| Quản trị bảo mật cơ sở dữ liệu | Quản lý quyền hoặc chính sách xác thực | Kiểm tra khả năng tự cấp lại quyền dữ liệu hoặc mở rộng đặc quyền |
| Danh tính sao lưu, phục hồi | Tạo và sử dụng bản sao lưu | Dữ liệu trong bản sao lưu vẫn nhạy cảm; quyền phục hồi có thể tạo đường tiếp cận dữ liệu |
| Quản trị hệ điều hành hoặc nền tảng | Quản lý máy chủ, dịch vụ hoặc tài nguyên bao quanh | Có thể tác động file, cấu hình, tiến trình hoặc đường cấp quyền, tùy kiến trúc |
| Quản trị dịch vụ cơ sở dữ liệu được quản lý | Quản lý tài nguyên qua control plane của nền tảng | Quyền control plane và quyền bên trong cơ sở dữ liệu là hai lớp cần đánh giá cùng nhau |

Tách tên vai trò chưa đủ để tạo tách biệt nhiệm vụ. Nếu một vai trò có thể tự gán lại mọi quyền đã bị tách, ranh giới kiểm soát thực tế có thể không đạt mục tiêu.

Trong dịch vụ được quản lý, danh tính quản trị khách hàng không nhất thiết có mọi đặc quyền của quản trị viên hệ thống tự vận hành. Ngược lại, một số thao tác ở control plane có thể ảnh hưởng thông tin xác thực, mạng, cấu hình hoặc bản sao dữ liệu. Phải kiểm tra năng lực thực tế của dịch vụ đang dùng.

## 4. Vì sao danh tính DBA có mức tác động lớn?

### 4.1. Tập trung quyền đối với dữ liệu nhạy cảm

Một cơ sở dữ liệu có thể tập trung dữ liệu của nhiều khách hàng, bộ phận hoặc ứng dụng. Quyền đọc diện rộng có thể cho phép truy cập dữ liệu vượt quá nhu cầu công việc dù không làm thay đổi hệ thống.

Tuy nhiên, quyền quản trị và quyền đọc dữ liệu không có quan hệ giống nhau trên mọi hệ quản trị. Cần xác minh:

- Vai trò có được đọc trực tiếp không?
- Có thể nhận thêm quyền đọc hoặc thay đổi chủ sở hữu không?
- Có thể phục hồi, xuất hoặc sao chép dữ liệu qua đường khác không?
- Có cơ chế bảo vệ dữ liệu mà vai trò quản trị này không kiểm soát được không?

Việc không có quyền đọc được gán trực tiếp không tự chứng minh danh tính không thể tiếp cận dữ liệu.

### 4.2. Có thể ảnh hưởng tính toàn vẹn và sẵn sàng

Một thay đổi cấu trúc, cấu hình hoặc thao tác hàng loạt có thể:

- Làm ứng dụng lỗi do không còn tương thích.
- Tạo khóa hoặc tranh chấp tài nguyên kéo dài.
- Xóa hoặc sửa dữ liệu ngoài phạm vi dự kiến.
- Làm gián đoạn kết nối và tác vụ nghiệp vụ.
- Tăng thời gian phục hồi do tác động đến bản sao lưu hoặc cấu hình khôi phục.

Các rủi ro này tồn tại cả với người thao tác hợp lệ. Kiểm soát DBA phải giảm hậu quả của nhầm lẫn, không chỉ ngăn người tấn công.

### 4.3. Có quyền gián tiếp qua mã và quyền sở hữu

Quyền sở hữu đối tượng hoặc quyền thay đổi thủ tục, hàm, tác vụ có thể tạo ảnh hưởng vượt ra ngoài một thao tác dữ liệu đơn lẻ.

Một số cơ chế cho phép mã chạy với quyền khác người gọi. Nếu người có quyền thấp sửa được phần mã chạy với quyền cao, ranh giới phân quyền có thể bị phá vỡ.

Cần kiểm tra cả:

- Ai sửa được đối tượng thực thi?
- Mã chạy với quyền nào?
- Tham số, đối tượng đích và ngữ cảnh thực thi có bị giới hạn không?
- Có thể biến một giao diện quản trị hẹp thành khả năng thực thi tùy ý không?

### 4.4. Có thể làm giảm chất lượng bằng chứng

Quyền quản trị audit, quyền xóa log hoặc quyền điều khiển nơi lưu bằng chứng có thể làm khó việc phát hiện và điều tra.

Một dòng log chỉ ghi tài khoản chung, thiếu người dùng thực tế hoặc thiếu định danh phiên cũng có thể không đủ để quy trách nhiệm. Vì vậy, cần bảo vệ cả **nội dung bằng chứng** lẫn **khả năng liên kết bằng chứng với chủ thể**.

## 5. Kiểm kê quyền DBA theo khả năng

Một bản kiểm kê hữu ích nên thể hiện nhiều hơn tên tài khoản và tên role.

| Nhóm khả năng | Nội dung cần kiểm tra | Tác động đáng chú ý |
| --- | --- | --- |
| Quản trị danh tính | Tạo tài khoản, cấp vai trò, đổi cơ chế xác thực | Cấp quyền tiếp, duy trì truy cập |
| Đọc và xuất dữ liệu | Đọc diện rộng, truy cập dữ liệu nhạy cảm, xuất dữ liệu | Lộ dữ liệu ngay cả khi không thay đổi dữ liệu |
| Quản lý cấu trúc | Sở hữu schema, tạo hoặc sửa đối tượng | Ảnh hưởng ứng dụng và các đường thực thi |
| Điều khiển vận hành | Kết thúc phiên, thay cấu hình, bảo trì | Gián đoạn hoặc thay đổi hành vi hệ thống |
| Mã thực thi | Sửa thủ tục, hàm, tác vụ hoặc thành phần mở rộng | Sử dụng quyền gián tiếp tùy cơ chế hệ quản trị |
| Sao lưu và phục hồi | Tạo, đọc, sao chép, xóa hoặc phục hồi bản sao lưu | Lộ dữ liệu, mất khả năng khôi phục |
| Giám sát và audit | Xem dữ liệu vận hành, sửa cấu hình ghi log | Lộ thông tin truy vấn hoặc giảm khả năng điều tra |
| Tương tác nền tảng | Quản lý tài nguyên, lưu trữ, khóa hoặc thông tin xác thực từ bên ngoài | Tạo đường tác động không hiện trong danh sách quyền SQL |

Với mỗi danh tính, cần xác định:

- Chủ sở hữu và mục đích sử dụng.
- Loại chủ thể: con người hay tác vụ tự động.
- Môi trường, cơ sở dữ liệu, schema và tập đối tượng được giao.
- Quyền trực tiếp, quyền kế thừa, quyền sở hữu và đường nhận thêm quyền.
- Credential đang dùng, nơi phân phối và bên phụ thuộc.
- Đường truy cập, công cụ kết nối và khả năng đi vòng quy trình PAM.
- Cách cấp, thu hồi, giám sát và xử lý khi xảy ra sự cố.

Không lưu giá trị credential trong bảng kiểm kê; chỉ lưu định danh tham chiếu phù hợp.

## 6. Least privilege cho công việc quản trị cơ sở dữ liệu

### 6.1. Mô tả công việc trước khi chọn role

Yêu cầu “cần DBA để xử lý chậm” còn quá rộng. Cần chuyển thành các nhu cầu cụ thể, chẳng hạn:

> Trong sự cố của ứng dụng A, người vận hành cần xem trạng thái kết nối, thông tin chờ và thống kê phù hợp của cơ sở dữ liệu A; chỉ được thực hiện thao tác điều khiển đã xác định khi có lý do và thẩm quyền tương ứng.

Những nhiệm vụ khác nhau nên được đánh giá riêng:

| Công việc | Hướng cấp quyền |
| --- | --- |
| Quan sát hiệu năng | Bắt đầu từ quyền xem thông tin vận hành cần thiết |
| Bảo trì đối tượng | Giới hạn cơ sở dữ liệu, schema hoặc tập đối tượng được giao |
| Migration | Gắn với đợt phát hành, nội dung thay đổi và danh tính riêng khi phù hợp |
| Quản lý người dùng | Tách khỏi hoạt động truy vấn dữ liệu khi kiến trúc cho phép |
| Sao lưu | Tách quyền tạo hoặc ghi bản sao lưu khỏi quyền xóa và thay cơ chế bảo vệ khi cần |
| Phục hồi khẩn cấp | Dùng quy trình riêng với quyền mạnh được quản lý và xem xét sau sử dụng |

Thông tin giám sát không phải lúc nào cũng vô hại. Văn bản truy vấn, tham số, mẫu dữ liệu hoặc thông tin kết nối có thể chứa dữ liệu nhạy cảm. Cần xem phạm vi dữ liệu mà quyền quan sát thực sự tiết lộ.

### 6.2. Kiểm tra quyền sở hữu và quyền cấp tiếp

Một vai trò không có quyền đọc trực tiếp nhưng có thể sửa chính sách để tự cấp quyền đọc vẫn là một đường đặc quyền.

Khi xác nhận least privilege, cần kiểm tra cả khả năng:

- Gán vai trò mạnh cho mình hoặc chủ thể khác.
- Thay đổi chủ sở hữu đối tượng.
- Sửa phần mã hoặc tác vụ chạy với quyền cao.
- Sửa cơ chế audit hoặc cơ chế cấp credential.
- Tạo bản sao dữ liệu ngoài ranh giới đang kiểm soát.

### 6.3. Tách tài khoản thường và tài khoản quản trị

Một DBA có thể dùng danh tính thông thường cho công việc hằng ngày và chỉ nhận quyền quản trị qua luồng được kiểm soát.

Nếu hệ thống đích cần tài khoản quản trị kỹ thuật, nên hạn chế chia sẻ trực tiếp credential. Khi nhiều người phải đi qua cùng principal ở đích, cần liên kết rõ người yêu cầu, tài khoản đích và phiên thực tế.

Không dùng tài khoản DBA làm credential chạy thường xuyên cho ứng dụng chỉ để tránh xử lý thiếu quyền. Điều đó biến một lỗ hổng ở ứng dụng thành đường tiếp cận quyền quản trị.

## 7. Áp dụng JIT và JEA vào danh tính DBA

### JIT: giới hạn thời gian có quyền

Just-in-Time có thể được thể hiện bằng cấp vai trò tạm thời, phát hành credential có thời hạn hoặc mở một luồng truy cập trong khoảng thời gian xác định.

Một yêu cầu có thể nêu:

- Người hoặc tác vụ thực hiện.
- Cơ sở dữ liệu và môi trường đích.
- Nhóm hành động cần thiết.
- Lý do, mã sự cố hoặc yêu cầu thay đổi.
- Khoảng thời gian và điều kiện kết thúc.
- Người hoặc chính sách chấp nhận quyền.

Điểm quan trọng là xác định khi hết hạn điều gì thực sự xảy ra. Hết thời hạn yêu cầu trong PAM không mặc nhiên làm phiên cơ sở dữ liệu đang mở mất mọi khả năng thao tác.

### JEA: giới hạn khả năng quản trị

Just Enough Administration là nguyên tắc chỉ cho phép tập hành động đủ cho nhiệm vụ. Với cơ sở dữ liệu, có thể thể hiện qua role hẹp, giao diện thao tác có kiểm soát hoặc tác vụ quản trị được ràng buộc.

Ví dụ: một nhiệm vụ chỉ cần xem trạng thái và yêu cầu bảo trì một tập đối tượng xác định không cần trở thành khả năng gửi mọi câu lệnh với quyền quản trị.

Nếu dùng thủ tục hoặc dịch vụ trung gian chạy với quyền cao, cần bảo vệ:

- Quyền sửa phần triển khai.
- Tham số và danh sách đối tượng được chấp nhận.
- Cách phân giải tên và ngữ cảnh thực thi theo cơ chế hệ quản trị.
- Các đường tạo câu lệnh hoặc thực thi tùy ý.
- Quyền gọi và bằng chứng thực hiện.

Một thủ tục chạy với quyền cao nhưng nhận chuỗi lệnh tùy ý không tạo ra ranh giới hành động hẹp.

JEA trong bài này là nguyên tắc giới hạn quản trị. Không giả định mọi hệ quản trị đều có một tính năng cùng tên hoặc cùng cách cấu hình.

## 8. Vault, xác thực và luân chuyển credential DBA

### 8.1. Kiểm soát phương tiện xác thực

Tùy hệ thống, DBA có thể xác thực bằng mật khẩu, chứng thư, token, danh tính liên kết hoặc cơ chế do nền tảng cung cấp.

Đối với mật khẩu hoặc credential dài hạn:

- Đặt trong vault phù hợp thay vì ghi trong hướng dẫn dùng chung hoặc lịch sử công cụ.
- Giới hạn ai được lấy và cho mục đích nào.
- Có chủ sở hữu, quy trình đổi và thu hồi.
- Kiểm soát bản sao ở công cụ quản trị, file kết nối và máy vận hành.
- Ghi sự kiện sử dụng credential theo định danh an toàn, không ghi giá trị bí mật.

Đối với credential ngắn hạn, vẫn phải bảo vệ đường phát hành, phạm vi quyền, khả năng gia hạn và những phiên được tạo từ credential đó.

### 8.2. MFA và đường kết nối

MFA phù hợp với nhiều luồng truy cập của con người. Cơ chế áp dụng có thể nằm ở nhà cung cấp danh tính, gateway, PAM hoặc hệ thống đích, tùy khả năng tích hợp.

Cần kiểm tra:

- Các công cụ và giao thức kết nối thực tế có đi qua bước kiểm soát không?
- Có đường kết nối trực tiếp dùng credential tĩnh để bỏ qua luồng đó không?
- Người dùng có thể xuất hoặc sao chép credential để mở phiên khác không?
- Tác vụ tự động có cơ chế xác thực riêng phù hợp không?

Không buộc tác vụ tự động vận hành bằng cách chia sẻ mã MFA của một DBA. Tác vụ quản trị cần danh tính riêng và vòng đời quyền được kiểm soát.

### 8.3. Đổi credential cần hiểu phụ thuộc

Một tài khoản quản trị cũ có thể đang được dùng bởi job bảo trì, công cụ sao lưu, kiểm tra vận hành hoặc dịch vụ mà đội quản lý chưa biết.

Trước khi luân chuyển, cần nhận diện và tách các phụ thuộc không phù hợp. Nếu hệ thống hỗ trợ chuyển tiếp giữa nhiều credential, có thể dùng cơ chế đó theo kế hoạch; nếu không, cần điều phối thời điểm và phương án phù hợp.

Luân chuyển thành công cần được xác nhận bằng khả năng dùng credential mới và xử lý credential cũ theo cơ chế của hệ thống. Việc cập nhật một mục trong vault chưa chứng minh mọi bên sử dụng đã chuyển đổi.

## 9. Quản lý phiên, connection pool và thu hồi quyền

### 9.1. Một lần xác thực có thể tạo phiên tồn tại lâu

Cơ sở dữ liệu thường phục vụ kết nối dài hạn. Một công cụ quản trị có thể mở nhiều kết nối; một pool có thể giữ kết nối vật lý qua nhiều tác vụ.

Vì thế cần phân biệt:

```text
Thời hạn yêu cầu truy cập trong PAM
              |
              +--> Thời hạn vai trò hoặc credential
              |
              +--> Thời gian tồn tại của từng kết nối
              |
              +--> Thời gian giao dịch hoặc tác vụ đang chạy
```

Các khoảng thời gian này không nhất thiết kết thúc cùng lúc.

### 9.2. Không giả định đổi mật khẩu sẽ ngắt kết nối

Hành vi thu hồi phụ thuộc hệ quản trị, loại credential và cách kiểm tra quyền:

- Chặn đăng nhập mới có thể không kết thúc phiên hiện tại.
- Đổi mật khẩu có thể chỉ ảnh hưởng lần xác thực tiếp theo.
- Thu hồi vai trò có thể tác động khác nhau đến quyền trong phiên và thao tác đang thực hiện.
- Vô hiệu hóa đường cấp token có thể không thu hồi credential đích đã phát hành.
- Kết thúc phiên có thể ảnh hưởng giao dịch, gây rollback hoặc kéo dài thời gian phục hồi.

Thiết kế cần xác định rõ cơ chế nào chặn truy cập mới, cơ chế nào xử lý phiên đã tồn tại và điều gì xảy ra với công việc đang chạy.

### 9.3. Pool không được làm mất ranh giới quyền

Nếu nhiều nhiệm vụ dùng chung kết nối được mở bằng một danh tính mạnh, việc hết hạn quyền của một người ở phía ngoài chưa chắc thay đổi principal của kết nối đó.

Cần kiểm tra vòng đời kết nối, trạng thái vai trò hoặc ngữ cảnh phiên, cách làm sạch trạng thái giữa các lượt sử dụng và cách liên kết người dùng thực tế.

Một nhãn người dùng do client tự gửi chỉ hữu ích trong phạm vi cơ chế bảo vệ của nó. Nếu người dùng có thể tự khai nhãn đó, không nên coi nó là bằng chứng xác thực độc lập.

## 10. Ví dụ: cấp quyền xử lý sự cố hiệu năng

Ứng dụng A ở production có độ trễ tăng cao. Người trực vận hành cần chẩn đoán cơ sở dữ liệu A.

### Thiết kế yêu cầu

Ví dụ sau là **mô tả ý định kiểm soát**, không phải cấu hình cho một sản phẩm:

```yaml
request:
  actor: database-operator-a
  reason: incident-example-73
  target: production/database-a
  purpose: diagnose-performance

access:
  identity: database-a-diagnostic-operator
  capabilities:
    - view-approved-operational-state
  sensitive_actions:
    - require-separate-authorization
  excluded_capabilities:
    - manage-identities
    - change-audit-policy
    - unrestricted-data-export

lifecycle:
  grant: bounded-by-incident-task
  expiry: explicit
  active_sessions: handled-by-database-specific-policy

evidence:
  correlate:
    - request-id
    - personal-identity
    - target-principal
    - database-session-id
    - action-result
```

Danh sách loại trừ ở đây thể hiện yêu cầu thiết kế; không phải cú pháp bảo đảm hệ quản trị đã áp dụng một chính sách từ chối. Khi triển khai, phải kiểm tra quyền hiệu lực và các đường cấp quyền khác.

### Luồng sử dụng

1. Người trực xác thực bằng danh tính cá nhân và yêu cầu quyền cho cơ sở dữ liệu A.
2. Hệ thống kiểm tra điều kiện, ghi quyết định và mở luồng truy cập phù hợp.
3. Người vận hành xem thông tin cần thiết bằng role chẩn đoán.
4. Nếu cần một thao tác có tác động lớn hơn, yêu cầu được đánh giá bổ sung thay vì mặc nhiên nâng lên quyền quản trị toàn hệ thống.
5. Khi công việc kết thúc, phiên và quyền được xử lý theo cơ chế đã xác định.
6. Bằng chứng được liên kết với mã sự cố và kết quả xử lý.

Một thao tác như kết thúc phiên có thể ảnh hưởng nghiệp vụ và giao dịch đang chạy. Không nên coi nó luôn an toàn chỉ vì thường xuất hiện trong công việc vận hành.

## 11. Bằng chứng nào cần giữ?

Một chuỗi bằng chứng hữu ích trả lời được:

> Ai hoặc tác vụ nào nhận quyền gì, trên hệ thống nào, vì lý do gì, đã làm gì, và quyền cùng phiên đã kết thúc thế nào?

| Nguồn bằng chứng | Nội dung cần liên kết |
| --- | --- |
| Yêu cầu truy cập | Người hoặc workload, lý do, phạm vi, thời gian, quyết định chấp nhận |
| Xác thực và cấp credential | Principal, phương thức xác thực, định danh credential hoặc phiên phù hợp |
| PAM hoặc gateway | Người dùng thực tế, tài khoản đích, phiên trung gian, thời gian và kết quả |
| Audit cơ sở dữ liệu | Principal đích, phiên, hành động, đối tượng, thời gian, kết quả |
| Quản lý thay đổi | Mã thay đổi, phiên bản hoặc nội dung được chấp nhận, trạng thái triển khai |
| Hệ thống nền tảng và sao lưu | Thay đổi cấu hình, bản sao, phục hồi, quyền và tài nguyên liên quan |
| Thu hồi | Thời điểm ngừng cấp quyền, xử lý phiên, kết quả và ngoại lệ |

Không phải mọi hệ thống đều cung cấp đầy đủ các trường trên. Cần nhận diện khoảng trống và thiết kế cách đối chiếu thay vì giả định một bản ghi riêng lẻ đã đủ.

### Bảo vệ dữ liệu trong audit

Văn bản truy vấn có thể chứa dữ liệu cá nhân, giá trị bí mật hoặc dữ liệu nghiệp vụ. Ghi mọi câu lệnh cùng mọi tham số không phải lúc nào cũng là lựa chọn phù hợp.

Cần xác định:

- Những hành động nào cần audit.
- Mức chi tiết cần cho điều tra.
- Cách giảm hoặc che dữ liệu nhạy cảm khi khả thi.
- Ai được xem và xuất log.
- Nơi lưu, thời hạn lưu và bảo vệ khỏi sửa hoặc xóa trái phép.

Thời gian giữa các nguồn cần đủ nhất quán để đối chiếu. Chính sách lưu bằng chứng phải dựa trên nhu cầu và yêu cầu áp dụng của tổ chức, không chọn một thời hạn cố định cho mọi cơ sở dữ liệu.

## 12. Những giới hạn cần hiểu đúng

### Mã hóa lưu trữ không tự ngăn DBA đọc dữ liệu

Mã hóa dữ liệu lưu trữ bảo vệ một số đường tiếp cận vật lý hoặc bản sao theo thiết kế. Nếu cơ sở dữ liệu giải mã để phục vụ một phiên được phép đọc, mã hóa lưu trữ không tự ngăn phiên đó nhận dữ liệu rõ.

Muốn giới hạn DBA tiếp cận nội dung, cần đánh giá cơ chế phân quyền, kiến trúc mã hóa, quyền quản lý khóa và các đường nhận lại dữ liệu. Không nên suy luận mức bảo vệ chỉ từ nhãn “encrypted”.

### Tách quản trị và dữ liệu cần xem cả đường vòng

Một DBA không được cấp quyền đọc trực tiếp vẫn có thể có đường tiếp cận qua cấp quyền, mã thực thi, phục hồi hoặc quản trị nền tảng, tùy thiết kế.

Ranh giới có ý nghĩa khi các đường đó cũng được kiểm soát. Cần làm rõ ai có thể thay chính sách, thay khóa, phục hồi bản sao và xem bằng chứng.

### PAM không thay thế tính đúng đắn của thay đổi

Một phiên được xác thực mạnh, cấp quyền đúng và ghi audit đầy đủ vẫn có thể chứa một thay đổi sai.

Thay đổi có ảnh hưởng lớn còn cần quy trình xem xét, kiểm tra trước, kế hoạch khôi phục và xác nhận kết quả tương xứng. PAM giúp kiểm soát người và quyền thực hiện, đồng thời cung cấp bằng chứng; nó không tự chứng minh nội dung thay đổi an toàn.

## 13. Ứng phó khi nghi danh tính DBA bị lạm dụng

Giả sử audit ghi nhận một tài khoản quản trị dùng chung cấp thêm quyền ngoài lịch bảo trì.

Một hướng xử lý có phối hợp:

1. **Xác định chủ thể và phạm vi.** Đối chiếu yêu cầu, log lấy credential, phiên PAM, phiên cơ sở dữ liệu và nguồn kết nối.
2. **Chặn đường truy cập mới phù hợp.** Hạn chế principal, đường cấp credential hoặc đường kết nối liên quan theo đánh giá sự cố.
3. **Xử lý phiên đang tồn tại.** Kiểm tra phiên nào có quyền, tác vụ nào đang chạy và tác động của việc kết thúc chúng.
4. **Kiểm tra quyền và phương tiện truy cập phát sinh.** Tìm tài khoản, role, credential, thay đổi mã hoặc cấu hình liên quan.
5. **Đánh giá tác động đến dữ liệu và phục hồi.** Kiểm tra đọc hoặc xuất dữ liệu, thay đổi dữ liệu, schema, bản sao lưu và cơ chế audit trong phạm vi có bằng chứng.
6. **Bảo toàn bằng chứng và khôi phục.** Giữ log cần thiết, sửa nguyên nhân, xử lý credential liên quan và phục hồi theo kế hoạch.
7. **Xác nhận thu hồi và hoạt động bình thường.** Kiểm tra đường truy cập cũ, quyền gián tiếp và các ngoại lệ còn tồn tại.

Không thể kết luận dữ liệu đã bị lấy đi chỉ từ một sự kiện cấp role; cần bằng chứng bổ sung. Ngược lại, không thấy sự kiện xuất dữ liệu trong một nguồn log thiếu chi tiết cũng chưa đủ để kết luận dữ liệu không bị truy cập.

## 14. Tình huống tự đánh giá

Một đội có các điều kiện sau:

- Bốn DBA dùng chung tài khoản quản trị mạnh.
- Mật khẩu được lưu trong vault và đổi định kỳ.
- Công cụ quản trị có thể giữ kết nối qua nhiều giờ.
- Tài khoản có quyền sửa schema, cấp quyền và thay cấu hình audit.
- Tài khoản này còn được một job migration sử dụng.
- Nhóm cho rằng hết thời hạn lấy mật khẩu trong vault là mọi quyền đã hết hạn.

### Phân tích

**Danh tính bị dùng chung:** người vận hành và job migration không có ranh giới thu hồi, trách nhiệm và mục đích rõ ràng.

**Phạm vi quyền quá rộng cho nhiều nhiệm vụ:** công việc chẩn đoán hoặc migration không đương nhiên cần quyền quản lý audit và cấp mọi quyền.

**Nhầm vòng đời credential với phiên:** hết thời hạn lấy bí mật không thu hồi bản sao đã lấy, không tự kết thúc kết nối và không tự thu hồi quyền ở đích.

**Bằng chứng cần bổ sung:** log vault cần được liên kết với người dùng, phiên trung gian, phiên cơ sở dữ liệu và hành động. Quyền sửa audit cũng cần kiểm soát và ghi nhận.

### Hướng cải thiện

- Tách danh tính con người và job migration.
- Dùng danh tính cá nhân ở luồng yêu cầu; giới hạn việc sử dụng trực tiếp tài khoản chung.
- Tách quyền theo nhiệm vụ, cơ sở dữ liệu và môi trường.
- Cấp quyền có thời hạn khi phù hợp và xác định cách xử lý phiên còn sống.
- Quản lý credential trong vault cùng với kế hoạch luân chuyển, phụ thuộc và thu hồi.
- Bảo vệ cấu hình audit, lưu bằng chứng ở nơi có kiểm soát phù hợp.
- Duy trì tài khoản khẩn cấp theo quy trình riêng, có chủ sở hữu, cảnh báo và xem xét sau sử dụng.

Các cải thiện cần được triển khai có kiểm tra khả năng vận hành và phục hồi. Không nên xóa hoặc đổi một tài khoản đang có phụ thuộc chưa rõ rồi coi gián đoạn là kết quả tất yếu của least privilege.

## 15. Những điểm cần ghi nhớ

- Danh tính DBA được xác định bằng khả năng quản trị thực tế, gồm cả quyền sở hữu, cấp quyền tiếp và những đường gián tiếp.
- Quyền bên trong cơ sở dữ liệu, quyền hệ điều hành, control plane, sao lưu và khóa bảo vệ cần được đánh giá trong cùng phạm vi tác động.
- Least privilege và JEA giới hạn hành động; JIT giới hạn thời gian; vault và luân chuyển quản lý credential.
- Thời hạn quyền, credential, kết nối và giao dịch có thể khác nhau. Thu hồi cần xử lý đúng từng lớp.
- Bằng chứng phải liên kết được người hoặc tác vụ, principal đích, phiên, hành động và kết quả; đồng thời được bảo vệ khỏi lộ hoặc sửa trái phép.
- Một thiết kế PAM cho DBA cần trả lời rõ: **ai được quản trị phần nào, bằng đường nào, trong bao lâu, với khả năng gì và thu hồi ra sao**.