# Directory boundary — Ranh giới của directory trong kiến trúc IAM

## 1. Một bản ghi tài khoản luôn thuộc một phạm vi cụ thể

Directory là nơi tổ chức thông tin về các đối tượng như người dùng, nhóm, thiết bị hoặc tài khoản dịch vụ. Trong kiến trúc IAM, **directory boundary** giúp xác định thông tin nào nằm trong phạm vi quản lý của directory, ai có quyền đọc hoặc thay đổi thông tin đó và những hệ thống nào được phép dựa vào nó.

Ví dụ, hai doanh nghiệp đều có tài khoản mang tên `admin`. Hai bản ghi này không tự đại diện cho cùng một chủ thể và không có cùng quyền. Muốn hiểu tài khoản nào đang được nói tới, cần biết directory nguồn, namespace và các quy tắc liên kết tương ứng.

Ranh giới directory còn quyết định phạm vi ảnh hưởng khi tài khoản quản trị, connector hoặc dữ liệu danh tính bị can thiệp. Một ứng dụng chỉ cần đọc tên hiển thị nhưng được cấp quyền sửa mọi nhóm trong directory đã có khả năng ảnh hưởng vượt xa chức năng của nó.

Trong bài này, directory boundary là một cách phân tích kiến trúc. Cơ chế thực thi cụ thể phụ thuộc sản phẩm: directory LDAP, Active Directory Domain Services, directory đám mây hoặc một kho danh tính do ứng dụng quản lý không có cùng mô hình ranh giới chỉ vì đều lưu người dùng và nhóm.

## 2. Phân biệt các loại ranh giới

| Loại ranh giới | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Namespace | Một mã đối tượng có ý nghĩa và duy nhất trong phạm vi nào? | Cặp directory nguồn và ID đối tượng |
| Dữ liệu | Ai được thấy đối tượng và thuộc tính nào? | Ứng dụng chỉ đọc các trường hồ sơ được phép |
| Quản trị | Ai được thực hiện thay đổi nào trên phạm vi nào? | Helpdesk được reset phương thức đăng nhập cho một nhóm tài khoản |
| Nguồn thẩm quyền | Thành phần nào quyết định giá trị cuối cùng của thuộc tính? | HR quyết định trạng thái nhân viên; ứng dụng quyết định quyền nghiệp vụ riêng |
| Tin cậy | Hệ thống nào chấp nhận bằng chứng hoặc dữ liệu từ directory này? | IdP sử dụng thuộc tính để phát hành claims cho ứng dụng |
| Bảo mật và cô lập | Sự cố hoặc quản trị viên ở một phạm vi có thể tác động sang đâu? | Quyền quản trị cấp cao có thể vượt qua các vùng ủy quyền bên trong |

Các ranh giới trên có liên quan nhưng không đồng nhất. Một nhóm hoặc container có thể giúp tổ chức dữ liệu, lọc truy vấn và ủy quyền quản trị mà chưa tạo ra sự độc lập trước quản trị viên cấp cao của hệ thống chứa nó.

Ví dụ, chia tài khoản thành hai folder `production` và `test` không tự bảo đảm người quản trị directory không thể sửa cả hai. Muốn đánh giá cô lập, phải kiểm tra quyền hiệu lực, cơ chế kế thừa, quyền của service principal, tài khoản vận hành và đường khôi phục.

## 3. Directory không đồng nghĩa với IdP hoặc hệ thống phân quyền

### 3.1. Directory lưu dữ liệu, IdP phát hành bằng chứng

Directory có thể là nguồn tài khoản và thuộc tính cho IdP. IdP thực hiện luồng xác thực, quản lý phiên hoặc phát hành assertion theo protocol. Một sản phẩm có thể tích hợp cả hai, nhưng về trách nhiệm vẫn cần phân biệt ai lưu trạng thái và ai được phép khẳng định điều gì về chủ thể.

Một directory được đồng bộ vào hai IdP cũng không làm mọi token từ hai IdP tự có cùng phạm vi tin cậy. Bên nhận vẫn phải kiểm tra issuer, audience và quy tắc liên kết được cấu hình. Không thể chấp nhận token chỉ vì email trong token trùng với email ở directory nội bộ.

### 3.2. Nhóm directory là đầu vào, không phải mọi quyết định quyền

Một group có thể được dùng để cấp role hoặc đưa thuộc tính vào policy. Tuy nhiên, hệ thống đích còn cần quyết định role đó cho phép hành động nào trên tài nguyên nào. Cùng tên nhóm `Administrators` ở hai directory không nên tự động được ánh xạ vào cùng một quyền quản trị nội bộ.

Quyền sửa membership hoặc sửa thuộc tính được policy sử dụng có thể là quyền tạo ra đặc quyền gián tiếp. Nếu `department=finance` cho phép duyệt chi, tài khoản được tự sửa `department` đã có một đường ảnh hưởng tới quyết định quyền. Phân tích boundary phải bao gồm quyền ghi các đầu vào này, không chỉ quyền tạo hoặc xóa tài khoản.

## 4. Namespace và khóa liên kết khi đi qua nhiều directory

### 4.1. Không dùng tên dễ đọc như một khóa toàn cục

Username, email, tên hiển thị hoặc đường dẫn đối tượng có thể thay đổi theo vòng đời và cơ chế sản phẩm. Tài khoản bị di chuyển, đổi tên hoặc được tạo lại có thể không còn cùng định danh nguồn dù thông tin hiển thị giống nhau.

Một mô hình tham chiếu khái niệm có thể lưu:

```json
{
  "source_directory_ref": "workforce-directory-a",
  "source_object_id": "object-demo-1042",
  "target_directory_ref": "saas-directory-b",
  "target_object_id": "object-demo-9077"
}
```

Các giá trị này là dữ liệu giả để minh họa mapping, không phải tên field chuẩn của mọi directory. Mapping cần gắn với đối tượng đúng tại cả hai phía, được tạo từ một quy trình có thẩm quyền và được bảo vệ khỏi thay đổi tùy ý.

Nếu hai directory đều có `object-demo-1042`, chuỗi đó chưa đủ để kết luận hai đối tượng là một. Cần giữ namespace nguồn trong lookup và lưu trữ. Nếu một tài khoản bị xóa rồi một người khác dùng lại email cũ, không được tự nối người mới vào dữ liệu và quyền của tài khoản cũ.

### 4.2. ID của directory, SCIM và subject trong federation

Các lớp tích hợp có thể dùng định danh khác nhau. ID bản ghi tại directory nguồn không nhất thiết bằng `id` của SCIM resource ở hệ thống đích hoặc `sub` trong một assertion OIDC. Mỗi lớp cần một contract ánh xạ thay vì giả định mọi nơi cùng dùng một mã.

Trong SCIM, `id` được service provider cấp và có tính ổn định, không tái gán theo định nghĩa của schema. `externalId` do client cung cấp và được hiểu trong phạm vi provisioning domain của client, nên không nên được coi là khóa toàn cục không cần namespace. [RFC 7643, mục 3.1 — Common Attributes](https://www.rfc-editor.org/rfc/rfc7643.html#section-3.1).

Khi ứng dụng nhận danh tính liên kết, phải hiểu subject trong phạm vi issuer đã xác minh. Tại tầng dữ liệu, tenant cũng có thể là một phần của khóa hoặc điều kiện truy cập, tùy mô hình hệ thống. Ranh giới thực tế phải được biểu diễn trong khóa và kiểm tra phía máy chủ, không chỉ trong tên biến.

## 5. Ranh giới tổ chức không tự tạo cô lập bảo mật

### 5.1. Ví dụ Active Directory Domain Services

Trong AD DS, forest, domain và organizational unit có vai trò khác nhau. Microsoft mô tả forest là ranh giới bảo mật và quản trị cho các đối tượng trong các domain thuộc forest, còn domain là phạm vi quản trị đối tượng. Không nên xem hai domain trong cùng forest như hai hệ thống hoàn toàn độc lập trước mọi sự cố hoặc đặc quyền của forest. [Microsoft Open Specifications — Forest and domain terminology](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-lsad/31ca2a31-0be4-4773-bcef-05ad6cd3ccfb).

OU hữu ích để tổ chức và ủy quyền quản trị, nhưng việc tách OU không tự thay thế việc thiết kế ranh giới forest khi yêu cầu là cô lập độc lập. Tài liệu thiết kế logical structure của Microsoft cũng tách việc chọn forest/domain boundary khỏi việc xây OU để ủy quyền quản lý. [Microsoft Learn — Designing the Logical Structure](https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/plan/designing-the-logical-structure).

Đây là ví dụ theo AD DS. Không nên áp nguyên tên gọi hoặc ngữ nghĩa forest/domain/OU sang mọi directory đám mây hoặc kho LDAP khác.

### 5.2. Ví dụ directory đám mây và tenant

Một tenant riêng có thể tạo phạm vi quản trị directory và cấu hình độc lập theo sản phẩm. Chẳng hạn, tài liệu Microsoft Entra mô tả việc tách tenant để tách quản lý các đối tượng directory, directory role và những kiểm soát liên quan; đồng thời lưu ý chi phí quản trị của kiến trúc nhiều tenant. [Microsoft Learn — Resource isolation with multiple tenants](https://learn.microsoft.com/en-us/entra/architecture/secure-multiple-tenants).

Tuy nhiên, khi nối các tenant bằng ứng dụng đa tenant, guest account, federation hoặc connector, phải phân tích lại quyền được cho phép đi qua. Một app có quyền ghi rộng ở cả hai tenant có thể trở thành đường ảnh hưởng chung dù dữ liệu được lưu tách biệt.

Cũng cần phân biệt security boundary của directory với ranh giới dữ liệu nghiệp vụ của ứng dụng. Một ứng dụng dùng chung IdP cho nhiều khách hàng vẫn phải tự thực thi cô lập tài nguyên theo tenant. Ngược lại, có hai directory không tự làm một database nghiệp vụ dùng chung trở nên an toàn nếu API truy vấn sai tenant.

## 6. Đọc và ghi dữ liệu qua boundary

### 6.1. Quyền đọc cần giới hạn theo đối tượng và thuộc tính

Một ứng dụng tìm đồng nghiệp có thể chỉ cần mã tham chiếu và tên hiển thị, không cần dữ liệu khôi phục tài khoản hoặc toàn bộ nhóm đặc quyền. Cần giới hạn quyền đọc tại dịch vụ cung cấp dữ liệu, đồng thời hạn chế response, export và log của ứng dụng nhận.

Với truy vấn LDAP, search base hoặc filter có thể giúp giới hạn tìm kiếm theo mục đích nhưng không thay thế ACL và quyền của identity thực hiện truy vấn. Nếu tài khoản connector vẫn có thể đọc toàn directory, một lỗi hoặc thay đổi truy vấn có thể vượt khỏi phạm vi dự kiến. Các giá trị đưa vào truy vấn cần được xử lý theo API và cơ chế escaping phù hợp, không nối trực tiếp input không tin cậy vào biểu thức truy vấn.

Với một bản chiếu directory do ứng dụng quản lý, truy vấn khái niệm có thể là:

```sql
SELECT object_id, display_name
FROM directory_projection
WHERE directory_ref = :trusted_directory_ref
  AND tenant_ref = :authorized_tenant_ref
  AND object_id = :requested_object_id;
```

Đây là ví dụ bảng dữ liệu giả định, không phải schema của AD DS hoặc SCIM. Các giá trị `trusted_directory_ref` và `authorized_tenant_ref` phải đến từ ngữ cảnh phía máy chủ đã được xác thực, phân quyền. Đổi tên tham số thành “trusted” không tạo ra tin cậy nếu ứng dụng vẫn lấy nguyên giá trị tenant do client gửi lên mà không kiểm tra.

### 6.2. Quyền ghi cần được đánh giá theo tác động

Một ma trận quyền tối thiểu minh họa:

| Chủ thể tích hợp | Quyền đọc dự kiến | Quyền ghi dự kiến | Quyền không được tự suy ra |
|---|---|---|---|
| Ứng dụng danh bạ | Tập hồ sơ và trường được phép hiển thị | Không cần ghi directory cho chức năng tra cứu | Đọc mọi thuộc tính hoặc sửa membership |
| Connector cấp tài khoản SaaS | Thuộc tính nguồn trong phạm vi đồng bộ | Các trường và tài khoản đích được cấp quyền quản lý | Thay cấu hình trust hoặc cấp directory role đặc quyền |
| Helpdesk | Dữ liệu cần để xử lý yêu cầu hỗ trợ | Thao tác được ủy quyền với nhóm tài khoản cụ thể | Thao tác trên mọi quản trị viên cấp cao |
| Tác vụ kiểm toán | Thông tin cần cho đối soát | Không cần ghi trong chức năng báo cáo | Tự sửa quyền khi phát hiện sai lệch |

Ma trận chỉ có ý nghĩa khi kiểm tra quyền hiệu lực. Một role có tên “Reader” không bảo đảm chỉ đọc nếu chủ thể còn nhận quyền ghi từ group khác, quyền app-only hoặc một credential dùng chung có phạm vi rộng hơn.

Các thao tác cần được bảo vệ trên cả kênh truyền và endpoint: xác thực dịch vụ gọi, quyền theo phạm vi, quản lý credential và audit. Đặt connector trong mạng nội bộ không tự làm mọi thao tác của nó hợp lệ.

## 7. Đồng bộ, replication và federation đi qua ranh giới theo cách khác nhau

| Cơ chế | Điều được truyền hoặc chấp nhận | Điểm cần kiểm soát |
|---|---|---|
| Replication | Bản sao dữ liệu theo cơ chế của directory | Tập dữ liệu được sao, quyền của replica và đường quản trị |
| Provisioning hoặc đồng bộ | Các đối tượng và thuộc tính được mapping sang đích | Phạm vi, nguồn thẩm quyền, quyền connector và xử lý thu hồi |
| Federation | Bằng chứng xác thực hoặc claims do một bên phát hành | Issuer, audience, khóa, mức tin cậy và ánh xạ quyền |
| Tra cứu qua API | Dữ liệu được yêu cầu tại thời điểm gọi | Quyền đọc theo trường, tenant và mục đích |

Federation không tất yếu sao chép mật khẩu hoặc toàn bộ directory. Ngược lại, có đồng bộ tài khoản không tự tạo một trust relationship cho phép chấp nhận mọi assertion từ hệ thống nguồn. Các cơ chế có thể được kết hợp, nhưng cần mô tả riêng tác động của từng cơ chế.

### 7.1. Nguồn thẩm quyền theo từng thuộc tính

Một tài khoản đích có thể lấy tên hiển thị từ directory nguồn, trạng thái nhân viên từ HR và quyền nghiệp vụ từ chủ ứng dụng. Cần xác định field nào do bên nào quản lý, thay đổi nào được phép ghi ngược và cách xử lý xung đột.

Nếu hai connector cùng ghi một field mà không có quy tắc ưu tiên, dữ liệu có thể dao động hoặc bị ghi đè. Nếu thuộc tính đó quyết định quyền, lỗi đồng bộ trở thành vấn đề phân quyền, không chỉ là một lỗi hiển thị hồ sơ.

Không nên để một directory đối tác tự quyết định role quản trị nội bộ chỉ bằng cách gửi tên nhóm hoặc một claim có tên giống role. Mapping qua boundary phải giới hạn chủ thể, thuộc tính và quyền mà nguồn đó được phép khẳng định.

### 7.2. Thu hồi cần được đo tới hệ thống đích

Một tài khoản bị disable ở directory nguồn có thể vẫn còn tài khoản hoạt động, membership hoặc phiên tại ứng dụng đích nếu luồng thu hồi chưa chạy xong. Cần đo độ trễ và xác minh kết quả theo từng nghĩa vụ: gỡ quyền, disable tài khoản, thu hồi credential hoặc xử lý phiên theo khả năng của hệ thống.

Không coi việc gửi một sự kiện đồng bộ là bằng chứng quyền đã hết hiệu lực. Retry, lỗi mapping hoặc API đích không phản hồi đều có thể kéo dài trạng thái không khớp giữa hai phía.

### 7.3. Tránh biến lỗi nguồn thành thay đổi hàng loạt sai

Một truy vấn trả rỗng vì lỗi quyền hoặc một lần đọc nguồn không đầy đủ không nên tự động được hiểu rằng mọi người dùng đã bị xóa. Luồng đồng bộ cần phân biệt snapshot hợp lệ với lỗi thu thập, có kiểm soát đối với thay đổi số lượng lớn và giữ khả năng đối soát.

Khi giảm phạm vi mapping, dữ liệu cũ ở đích cũng không nhất thiết tự biến mất. Cần hiểu cách connector biểu diễn việc bỏ thuộc tính, xóa giá trị hoặc giữ nguyên giá trị hiện có. Thay đổi boundary dữ liệu phải có readback ở hệ thống nhận, không chỉ sửa cấu hình nguồn.

## 8. Một tình huống thiết kế với nhân viên và đối tác

Giả sử doanh nghiệp có directory nhân viên, trong khi đối tác đăng nhập từ IdP riêng để truy cập một cổng cộng tác. Doanh nghiệp muốn đối tác chỉ xem tài liệu của dự án được cấp phép và không được quản trị directory nhân viên.

Một thiết kế có thể tách các trách nhiệm như sau:

1. Directory nhân viên tiếp tục là nguồn tài khoản nội bộ theo vòng đời nhân sự.
2. Federation chỉ chấp nhận các nguồn đối tác được cấu hình và xác minh đúng protocol.
3. Ứng dụng hoặc nền tảng tạo liên kết cục bộ cho danh tính ngoài theo mô hình được chọn, giữ namespace nguồn rõ ràng.
4. Quyền dự án do doanh nghiệp quản lý tại nơi có thẩm quyền; không lấy trực tiếp một tên role tùy ý do đối tác gửi làm quyền quản trị.
5. API cổng cộng tác kiểm tra membership dự án, tenant và hành động đối với tài liệu cụ thể.
6. Luồng kết thúc hợp tác xử lý quyền cục bộ và các phiên còn hiệu lực theo chính sách.

Điểm quan trọng là tin đối tác xác thực một tài khoản không đồng nghĩa giao cho đối tác quyền sửa directory nội bộ hoặc cấp mọi quyền tài nguyên. Nếu doanh nghiệp cho một connector chung quyền ghi rộng vào cả hai phía, phải đánh giá connector như một thành phần có khả năng vượt qua ranh giới đó.

## 9. Vận hành, giám sát và khôi phục

### 9.1. Kiểm tra các đường vượt ranh giới

Khi rà soát thiết kế, cần xem không chỉ quyền người dùng mà cả role cấp cao, ứng dụng tích hợp, tài khoản đồng bộ, máy chủ quản trị, credential và quyền khôi phục. Một tài khoản không có quyền trong giao diện directory vẫn có thể ảnh hưởng dữ liệu nếu nó kiểm soát connector hoặc hạ tầng lưu trữ phía dưới.

Replica, export và backup cũng có phạm vi dữ liệu cùng quyền truy cập riêng. Sao dữ liệu sang một kho khác tạo thêm nơi phải bảo vệ; việc nguồn có ACL chặt chẽ không tự làm bản export thừa hưởng đúng mọi kiểm soát đó.

Tách directory nhưng dùng chung một credential quản trị không giới hạn cho mọi nơi có thể giữ lại đường ảnh hưởng chung. Tương tự, tách production và test nhưng để ứng dụng test có quyền ghi production làm suy giảm mục tiêu cô lập ban đầu.

### 9.2. Quan sát những thay đổi có khả năng tạo quyền

Nên giám sát thay đổi role quản trị, membership nhạy cảm, quyền ứng dụng, cấu hình connector, mapping thuộc tính và trust configuration. Dấu vết cần cho biết chủ thể thực hiện, directory đích, loại thay đổi, kết quả và thông tin tương quan cần thiết.

Với dữ liệu nhạy cảm, chỉ ghi phần cần cho mục đích điều tra; không ghi credential hoặc toàn bộ hồ sơ vào log. Các báo cáo nhiều directory cũng cần giới hạn quyền xem, vì một dashboard tổng có thể vô tình trở thành cách đọc dữ liệu ngoài phạm vi ban đầu.

### 9.3. Khôi phục phải giữ đúng liên kết và trạng thái quyền

Khi phục hồi directory hoặc connector, cần đối soát định danh, mapping và phiên bản dữ liệu. Một bản backup cũ có thể chứa tài khoản từng bị thu hồi hoặc membership không còn hợp lệ. Không thể coi việc dịch vụ đã khởi động là đã khôi phục đúng trạng thái truy cập.

Kế hoạch nên có owner, khả năng xác minh sau khôi phục và cách xử lý thay đổi xảy ra sau thời điểm backup. Những cơ chế truy cập khẩn cấp phải được chuẩn bị và kiểm soát từ trước để không tạo đường quản trị không được giám sát khi directory gặp sự cố.

## 10. Tự kiểm tra cách hiểu

**Hai tài khoản cùng email ở hai directory có mặc nhiên là một người không?**

Không. Cần xác minh nguồn, namespace và quy tắc liên kết. Trùng email chưa đủ để gộp quyền hoặc dữ liệu tài khoản.

**Tách tài khoản vào hai OU có bảo đảm cô lập trước mọi quản trị viên cấp cao không?**

Không. OU có thể phục vụ tổ chức và ủy quyền, nhưng phải đánh giá quyền hiệu lực cùng ranh giới bảo mật của sản phẩm chứa nó. Trong AD DS, không nên dùng tách OU thay cho yêu cầu cô lập ở mức forest.

**Chấp nhận đăng nhập từ IdP đối tác có đồng nghĩa đối tác được quản trị directory nội bộ không?**

Không. Trust xác thực, quyền quản trị directory và quyền với tài nguyên là các quyết định riêng cần được giới hạn rõ ràng.

**Tài khoản nguồn đã bị disable có đủ để khẳng định mọi quyền ở SaaS đã hết hiệu lực không?**

Chưa đủ. Cần kiểm tra luồng đồng bộ, trạng thái đích, credential và phiên tương ứng theo contract của từng hệ thống.

**Một directory boundary được thiết kế rõ cần thể hiện gì?**

Namespace của đối tượng, thẩm quyền từng thuộc tính, quyền đọc và ghi, khả năng của quản trị viên cùng các luồng đồng bộ hoặc tin cậy đi qua. Khi những yếu tố này được thực thi và quan sát được, ranh giới mới hỗ trợ cô lập, ít quyền nhất và kiểm toán trong toàn kiến trúc IAM.
