# Team membership

## 1. Team membership trong mô hình ReBAC

Team membership biểu diễn quan hệ một danh tính thuộc về một nhóm cộng tác cụ thể. Trong IAM, quan hệ này thường tham gia vào việc cấp quyền trên repository, tài liệu, dự án hoặc không gian làm việc.

Ví dụ, Lan là thành viên của team Backend. Một tài liệu thiết kế được chia sẻ quyền chỉnh sửa cho các thành viên của team Backend. Hệ thống có thể suy ra Lan được chỉnh sửa tài liệu mà không cần ghi thêm một quyền chỉnh sửa riêng cho Lan trên từng tài liệu.

~~~text
Lan là member của team Backend
Team Backend được cấp editor trên tài liệu Thiết kế API
=> Lan có quyền editor trên tài liệu Thiết kế API
~~~

Phép suy ra chỉ hợp lệ khi mô hình phân quyền định nghĩa rõ đường quan hệ đó. Việc một team tồn tại trong hệ thống nhân sự, một người xuất hiện trong cuộc trò chuyện hoặc tên phòng ban trùng với tên team không tự tạo quyền truy cập.

ReBAC (Relationship-Based Access Control) sử dụng quan hệ giữa các thực thể để xác định quyền. Team membership là một quan hệ đầu vào; quyền trên tài nguyên là kết quả của mô hình cùng dữ liệu quan hệ hiện tại.

Sau bài học, người học cần xác định được ai là thành viên trực tiếp hoặc gián tiếp, lần theo đường cấp quyền qua team, và giải thích điều gì thay đổi khi một người được thêm vào hoặc bị loại khỏi team.

## 2. Tách các khái niệm dễ bị nhầm

| Khái niệm | Câu hỏi được trả lời | Ví dụ |
| --- | --- | --- |
| Identity | Chủ thể này là ai? | user:lan |
| Team membership | Chủ thể thuộc team nào? | Lan là member của Backend |
| Team role | Chủ thể có trách nhiệm gì trong team? | Minh là manager của Backend |
| Resource permission | Chủ thể được làm gì với một đối tượng? | Backend có editor trên tài liệu API |
| Resource ownership | Ai có các quyền của owner theo mô hình? | An là owner của tài liệu API |
| Organization membership | Chủ thể thuộc tổ chức nào? | Lan là member của tenant A |

Một người có thể thuộc nhiều team và mang vai trò khác nhau trên từng team. “Manager của Backend” không có nghĩa “manager của mọi team”. Tương tự, là thành viên tổ chức không mặc nhiên được đọc mọi tài liệu thuộc tổ chức.

Membership cũng khác quyền sở hữu. Một team có thể sở hữu tài nguyên theo thiết kế của ứng dụng, nhưng quyền của thành viên trên tài nguyên đó vẫn cần được định nghĩa. Không nên suy ra rằng mọi member đều được chuyển ownership, xóa team hoặc thêm người khác.

### 2.1. Team không chỉ là một role toàn cục

Một role toàn cục như platform-admin thường áp dụng ở phạm vi nền tảng. Team là một đối tượng có danh tính riêng, chẳng hạn Backend thuộc tenant A và Backend thuộc tenant B là hai team khác nhau.

Có thể kết hợp RBAC và ReBAC: vai trò manager được gắn với một team cụ thể, còn quyền quản lý thành viên được suy ra từ vai trò đó. Điều cần tránh là kiểm tra một cờ “isManager” chung rồi cho phép người gọi sửa membership của team bất kỳ.

### 2.2. Phạm vi nghiệp vụ của team

Team có thể đại diện nhóm dự án, nhóm vận hành, nhóm trực ca hoặc đơn vị tổ chức. Cần chọn ý nghĩa trước khi quyết định ai được cấp membership.

Nếu membership mang theo quyền đọc dữ liệu tài chính, thao tác “thêm vào team” đồng thời là một thao tác cấp quyền tài chính. Giao diện quản trị nhóm trông đơn giản không làm giảm tác động bảo mật của thao tác này.

## 3. Biểu diễn membership bằng relationship tuple

Một cách biểu diễn quan hệ phổ biến là bộ ba chủ thể, quan hệ và đối tượng. Trong các ví dụ của bài, dạng dễ đọc được viết như sau:

~~~text
object#relation@subject

team:tenant-a-backend#direct_member@user:lan
~~~

Đọc từ phải sang trái: user Lan có quan hệ direct_member với team Backend của tenant A.

Khi biểu diễn dưới dạng JSON, tên field có thể là user, relation và object:

~~~json
{
  "user": "user:lan",
  "relation": "direct_member",
  "object": "team:tenant-a-backend"
}
~~~

Các ID trong bài chỉ phục vụ minh họa. Trong hệ thống thực, cần dùng ID ổn định, duy nhất trong phạm vi đã chọn. Đổi tên hiển thị từ Backend thành Platform không nên vô tình tạo một team mới hoặc làm mất các quan hệ hiện có.

### 3.1. Team object và tập thành viên của team

Hai giá trị sau có ý nghĩa khác nhau:

~~~text
team:tenant-a-backend
team:tenant-a-backend#member
~~~

Giá trị thứ nhất định danh đối tượng team. Giá trị thứ hai biểu diễn tập những chủ thể có quan hệ member với team đó, thường được gọi là userset.

Khi chia sẻ tài liệu cho con người trong team, mô hình thường sử dụng tập thành viên. Chỉ ghi một team object làm chủ thể không tự bảo đảm rằng engine sẽ đi tiếp tới từng member; điều đó phụ thuộc kiểu quan hệ và quy tắc đã định nghĩa.

OpenFGA mô tả cách gán một quan hệ trên tài nguyên cho tập thành viên của một team, rồi kiểm tra quyền của một người cụ thể qua chuỗi quan hệ ấy. [Hướng dẫn OpenFGA về User Groups](https://openfga.dev/docs/modeling/user-groups).

### 3.2. Membership đã ghi và membership có hiệu lực

Một quan hệ được lưu trực tiếp là dữ kiện. Một quan hệ có hiệu lực có thể được suy ra từ dữ kiện khác theo mô hình.

Ví dụ, nếu mô hình quy định manager cũng là member, Minh có thể thuộc tập member dù không có tuple direct_member dành riêng cho Minh. Vì vậy, đọc danh sách các tuple direct_member không nhất thiết trả về toàn bộ thành viên có hiệu lực.

Cần phân biệt ít nhất hai câu hỏi:

~~~text
Ai được gán trực tiếp vào team?
Ai hiện được tính là member theo toàn bộ mô hình?
~~~

Sự phân biệt này ảnh hưởng đến màn hình quản trị, báo cáo quyền và thao tác thu hồi.

## 4. Mô hình minh họa: team cộng tác trên tài liệu

Xét hệ thống SaaS có nhiều tenant. Ví dụ dưới đây dùng cú pháp mô hình OpenFGA và các quan hệ do bài học tự đặt. Nó minh họa logic quyền; các ràng buộc tenant, trạng thái tài khoản và quản trị tuple sẽ được phân tích riêng.

~~~text
model
  schema 1.1

type user

type team
  relations
    define direct_member: [user]
    define manager: [user]
    define member: direct_member or manager
    define can_manage_members: manager

type document
  relations
    define owner: [user]
    define editor: [user, team#member] or owner
    define viewer: [user, team#member] or editor
    define can_share: owner
~~~

Mô hình này chủ động chọn những quy tắc sau:

- Người được gán direct_member là thành viên của team.
- Manager cũng được tính là member.
- Chỉ manager có can_manage_members trong phạm vi team.
- Document có thể cấp editor hoặc viewer cho người dùng hoặc tập member của team.
- Owner của document có editor, từ đó có viewer và có can_share.
- Editor không tự có can_share hoặc can_manage_members.

Đây là lựa chọn nghiệp vụ của ví dụ. Nếu manager chỉ quản trị danh sách thành viên và không được đọc tài liệu chia sẻ cho team, phải bỏ phần manager khỏi định nghĩa member hoặc dùng một quan hệ riêng phù hợp.

Trong OpenFGA, authorization model quy định kiểu và quan hệ có thể tồn tại; các relationship tuple cung cấp dữ liệu cụ thể để đánh giá. Cú pháp DSL là cách trình bày mô hình, còn API sử dụng dạng mô hình được hỗ trợ tương ứng. [Khái niệm cơ bản của OpenFGA](https://openfga.dev/docs/concepts).

### 4.1. Dữ liệu ban đầu

~~~json
[
  {
    "user": "user:lan",
    "relation": "direct_member",
    "object": "team:tenant-a-backend"
  },
  {
    "user": "user:minh",
    "relation": "manager",
    "object": "team:tenant-a-backend"
  },
  {
    "user": "user:ha",
    "relation": "direct_member",
    "object": "team:tenant-a-frontend"
  },
  {
    "user": "team:tenant-a-backend#member",
    "relation": "editor",
    "object": "document:tenant-a-api-design"
  },
  {
    "user": "user:an",
    "relation": "owner",
    "object": "document:tenant-a-api-design"
  }
]
~~~

Chưa có quan hệ chia sẻ nào cho Frontend trên tài liệu này. Cũng chưa có quyền viewer riêng cho Lan ngoài đường đi qua Backend.

~~~mermaid
flowchart LR
    L["user:lan"] -->|"direct_member"| B["team Backend"]
    M["user:minh"] -->|"manager, suy ra member"| B
    B -->|"member được cấp editor"| D["Tài liệu Thiết kế API"]
    A["user:an"] -->|"owner"| D
    H["user:ha"] -->|"direct_member"| F["team Frontend"]
~~~

Sơ đồ mô tả đường cấp quyền về mặt nghiệp vụ, không quy định cấu trúc chỉ mục hoặc thuật toán lưu trữ nội bộ của engine.

### 4.2. Các kết quả mong đợi

| Chủ thể | Câu hỏi | Kết quả theo dữ liệu ban đầu |
| --- | --- | --- |
| Lan | Là member của Backend? | Có, từ direct_member |
| Lan | Được chỉnh sửa tài liệu API? | Có, qua Backend#member |
| Lan | Được chia sẻ lại tài liệu API? | Không, chưa có owner |
| Lan | Được quản lý member của Backend? | Không, chưa có manager |
| Minh | Được chỉnh sửa tài liệu API? | Có, manager được tính là member |
| Minh | Được quản lý member của Backend? | Có |
| Hà | Được xem tài liệu API? | Không có đường cấp quyền |
| An | Được xem và chia sẻ tài liệu API? | Có, từ owner |
| An | Được quản lý member của Backend? | Không có quan hệ manager |

Kết quả “không có đường cấp quyền” giả định đây là toàn bộ dữ liệu liên quan và engine đã đánh giá thành công. Lỗi kết nối hoặc vượt giới hạn đánh giá không nên bị ghi nhận như một kết quả kiểm tra âm bình thường.

### 4.3. Kiểm tra membership và kiểm tra tài nguyên

Để hỏi Lan có thuộc Backend, truy vấn khái niệm là:

~~~json
{
  "user": "user:lan",
  "relation": "member",
  "object": "team:tenant-a-backend"
}
~~~

Để bảo vệ việc đọc tài liệu, cần hỏi đúng quan hệ trên tài liệu:

~~~json
{
  "user": "user:lan",
  "relation": "viewer",
  "object": "document:tenant-a-api-design"
}
~~~

Biết Lan là member của Backend chưa đủ để cho Lan đọc tài liệu bất kỳ. Phải có quan hệ từ team tới đúng tài nguyên và đúng loại quyền.

Ngược lại, không bắt buộc Lan phải thuộc Backend mới đọc được mọi tài liệu. Lan có thể là owner hoặc được cấp quyền trực tiếp theo mô hình. Kiểm tra tài nguyên cho phép engine xét đầy đủ những đường cấp quyền hợp lệ.

## 5. Vì sao cấp quyền qua team hữu ích?

Giả sử 80 người cần chỉnh sửa 300 tài liệu của một dự án. Ghi một quyền riêng cho từng người trên từng tài liệu có thể tạo đến 24.000 quan hệ chia sẻ nếu tất cả đều có quyền trên tất cả tài liệu.

Trong mô hình team đơn giản, có thể dùng 80 quan hệ membership và 300 quan hệ chia sẻ cho tập thành viên. Đây là phép so sánh số dữ kiện của ví dụ; chi phí kiểm tra thực tế còn tùy mô hình, chỉ mục, cache và engine.

Lợi ích quản trị đáng chú ý là khi thêm một người vào team, người đó nhận những quyền mà mô hình cho member của team. Khi gỡ một đường membership, hệ thống không cần sửa từng tài liệu để loại bỏ đúng đường cấp quyền ấy.

Tuy nhiên, tính tiện lợi này cũng tạo phạm vi ảnh hưởng lớn. Nếu Backend đang được chia sẻ nhiều tài liệu nhạy cảm, thêm nhầm một người vào Backend có thể mở quyền trên toàn bộ tập tài nguyên đó.

Nguyên tắc ít quyền nhất áp dụng cho cả việc thiết kế team: không nên gom mọi người vào một team rất rộng rồi chia sẻ tài nguyên nhạy cảm cho team đó chỉ để giảm số tuple.

## 6. Thêm, mời và kích hoạt thành viên

### 6.1. Lời mời chưa phải membership có hiệu lực

Một luồng mời thường có các trạng thái:

~~~text
INVITED -> ACTIVE -> REMOVED
        -> EXPIRED
~~~

Đây là mô hình trạng thái nghiệp vụ tham khảo, không phải trạng thái được engine ReBAC tự tạo sẵn.

Nếu chỉ membership ACTIVE mới được cấp quyền, tuple direct_member nên được tạo khi lời mời đã được chấp nhận và những kiểm tra cần thiết đã hoàn tất. Không tạo tuple có hiệu lực ngay khi gửi email nếu người nhận chưa được xác minh hoặc chưa đáp ứng điều kiện tham gia.

Email có thể dùng để gửi lời mời, nhưng danh tính được cấp membership cần gắn với tài khoản ổn định sau khi kiểm chứng. Không dựa vào tên hiển thị hoặc một địa chỉ chưa xác minh do client tự nhập để chọn chủ thể được cấp quyền.

Lời mời cũng cần được ràng buộc với team, tenant, người nhận và thời hạn phù hợp. Người đang có quyền nhận lời mời không vì thế có quyền thay team đích trong request chấp nhận.

### 6.2. Ai có quyền thêm người?

Trước khi thêm Lan vào Backend, backend cần kiểm tra người thực hiện có quyền quản lý membership của Backend hay không.

Trong mô hình minh họa, kiểm tra can_manage_members cho actor trên team là một bước. Ngoài ra, cần xác minh tài khoản đích hợp lệ, thuộc phạm vi tổ chức được phép và không vi phạm quy định về khách bên ngoài.

Một manager của Backend không tự được phép:

- Thêm người vào Frontend.
- Cấp vai trò manager cho người khác nếu ứng dụng chỉ cho quản lý member thông thường.
- Mời tài khoản thuộc tenant khác khi chưa có quy trình khách.
- Sửa trực tiếp owner hoặc editor của tài liệu không do mình quản lý.

Quan hệ can_manage_members trong mô hình là một quyền khái quát. Ứng dụng cần định nghĩa rõ nó bao gồm hành động nào. Có thể tách can_add_member, can_remove_member và can_assign_manager khi mức nhạy cảm khác nhau.

### 6.3. Không mở API ghi tuple tùy ý cho người dùng

Engine chấp nhận một tuple đúng kiểu không có nghĩa người gọi được phép tạo tuple ấy về mặt nghiệp vụ.

Nếu client có thể gửi mọi object, relation và user tới một API ghi quan hệ có đặc quyền, một người có thể tự ghi mình thành manager hoặc owner. Backend cần ánh xạ từng thao tác được hỗ trợ sang những thay đổi quan hệ cụ thể, sau khi kiểm tra quyền.

Ví dụ, endpoint thêm member chỉ được tạo direct_member trên team đích đã kiểm chứng. Nó không nhận relation tự do từ client rồi ghi nguyên vẹn bằng credential dịch vụ.

## 7. Thu hồi membership và những quyền còn lại

### 7.1. Xóa một cạnh cấp quyền

Với dữ liệu ban đầu, xóa tuple:

~~~text
team:tenant-a-backend#direct_member@user:lan
~~~

sẽ loại bỏ đường Lan -> Backend#member -> editor của tài liệu API. Nếu không có đường nào khác và dữ liệu mới đã có hiệu lực tại lần kiểm tra, Lan không còn quyền qua đường đó.

Điều này không đồng nghĩa “Lan bị cấm trên mọi tài nguyên”. Mô hình trên cấp quyền theo các đường có thể tồn tại song song.

### 7.2. Các đường thay thế

Giả sử sau đó An chia sẻ viewer trực tiếp cho Lan:

~~~text
document:tenant-a-api-design#viewer@user:lan
~~~

Khi Lan bị gỡ khỏi Backend, Lan vẫn có viewer trực tiếp nhưng mất editor nếu không còn đường editor khác. Việc này phù hợp với mô hình; nó không chứng minh thao tác xóa membership thất bại.

Tương tự, Lan có thể vẫn là member của team khác đang được chia sẻ tài liệu, là manager của Backend hoặc là owner của tài liệu.

Một màn hình quản trị nên diễn đạt chính xác thao tác: “Gỡ khỏi team Backend” chỉ thay quan hệ đó. Nếu yêu cầu là thu hồi mọi quyền trên tài liệu, phải tìm các nguồn cấp quyền liên quan và xử lý theo quyền quản trị được cấp.

### 7.3. Quyền manager cũng có thể duy trì membership

Trong mô hình, member = direct_member hoặc manager. Do đó, xóa direct_member của Minh không loại Minh khỏi member nếu Minh còn manager.

Cần xác định yêu cầu là:

~~~text
Gỡ assignment direct_member
hay
Loại bỏ mọi vai trò làm chủ thể được tính là member của team?
~~~

Hai thao tác khác nhau và có thể cần quyền khác nhau. Không tự xóa vai trò manager chỉ vì giao diện gửi yêu cầu xóa direct_member.

### 7.4. Khóa tài khoản và gỡ team là hai cơ chế

Khóa một tài khoản có thể cần chặn mọi request, kể cả những quyền trực tiếp còn tồn tại trong graph. Một lớp kiểm tra trạng thái danh tính hoặc một điều kiện tương đương trong mô hình phải được thực thi theo thiết kế.

Ngược lại, gỡ khỏi một team không nên vô tình khóa tài khoản hoặc xóa những quyền hợp lệ ở team khác.

Trong xử lý nhân viên rời tổ chức, cần phối hợp phiên đăng nhập, token, membership, direct grant và quyền sở hữu. Chỉ xóa một tuple team không đại diện cho toàn bộ quy trình offboarding.

## 8. Team lồng nhau và chiều suy ra membership

### 8.1. Định nghĩa tường minh việc lồng team

Giả sử mọi member của Backend cũng được tính là member của Engineering. Có thể mở rộng phần direct_member trong mô hình như sau:

~~~text
type team
  relations
    define direct_member: [user, team#member]
    define manager: [user]
    define member: direct_member or manager
    define can_manage_members: manager
~~~

Sau đó ghi:

~~~text
team:tenant-a-engineering#direct_member@team:tenant-a-backend#member
~~~

Điều này đưa tập member của Backend vào tập member của Engineering. Nếu Lan thuộc Backend, Lan có thể được suy ra là member của Engineering.

~~~text
Lan -> member Backend -> member Engineering
~~~

Chiều ngược lại không tự đúng. Một người chỉ là member của Engineering không vì thế là member của Backend.

Sau khi mở rộng kiểu, một direct_member assignment có thể trỏ tới người dùng hoặc một userset. Vì vậy, “được gán trực tiếp” lúc này mô tả một cạnh dữ liệu được ghi, không khẳng định mọi người có hiệu lực đều được gán trực tiếp bằng user ID.

### 8.2. Cấu trúc tổ chức không tự tạo quyền quản trị

Backend nằm trong Engineering về cơ cấu công ty chưa đủ để suy ra mọi quan hệ quyền.

Trong mô hình trên, member được lan truyền qua tuple userset, nhưng manager và can_manage_members không kế thừa theo cấu trúc đó. Manager của Engineering chưa chắc được quản trị membership của Backend.

Ngược lại, manager của Backend có thể tác động gián tiếp tới những tài nguyên chia sẻ cho Engineering bằng cách thêm người vào Backend. Vì vậy, việc lồng một team vào team khác cũng là một thay đổi quyền có phạm vi ảnh hưởng cần xem xét.

### 8.3. Nhiều đường và chu trình

Nếu Lan thuộc cả Backend và Security, và cả hai đều là thành phần của Engineering, xóa membership Backend có thể vẫn để lại đường qua Security.

Không được dừng phân tích ở đường đầu tiên đã bị xóa rồi kết luận tất cả quyền đã mất.

Ứng dụng có thể chọn cấm chu trình team lồng nhau và giới hạn độ sâu hợp lệ. Khi thêm cạnh mới, cần kiểm tra nó có tạo một vòng hay không. Với thay đổi đồng thời, hai kiểm tra độc lập có thể cùng vượt qua rồi tạo vòng; cơ chế ghi phải xử lý cả khả năng đó.

Giới hạn độ sâu hoặc thời gian đánh giá của engine không thay thế chính sách quản trị cấu trúc team. Nếu truy vấn gặp lỗi hoặc vượt giới hạn, backend cần xử lý theo hợp đồng lỗi, không tự chuyển thành cho phép.

## 9. Tenant boundary và nguồn dữ liệu tin cậy

Mô hình OpenFGA minh họa ở trên chưa có ràng buộc tenant. Tiền tố tenant-a trong ID giúp con người đọc dữ liệu; tự nó không ngăn một tuple chia sẻ từ tài liệu tenant A tới team tenant B.

Thiết kế cần bảo vệ ít nhất ba nhóm thay đổi:

1. Thêm danh tính vào team đúng phạm vi tenant.
2. Lồng team vào team khác theo quy tắc cùng tenant hoặc hợp tác liên tenant đã được phê duyệt.
3. Chia sẻ tài nguyên cho user hoặc team có quyền nhận chia sẻ đó.

Nếu chỉ kiểm tra cùng tenant khi thêm member nhưng cho phép chia sẻ tài liệu tùy ý, tài nguyên vẫn có thể bị lộ qua một team bên ngoài.

Backend phải lấy tenant của tài nguyên và team từ dữ liệu được quản trị, không coi header tenant hoặc prefix do client gửi là bằng chứng. Khi cần cơ chế khách bên ngoài, phải xác định rõ tenant chủ tài nguyên, danh tính khách, thời hạn và phạm vi được cấp.

Có thể đưa thêm quan hệ organization vào graph và kết hợp điều kiện để giới hạn quyền, hoặc giữ một số ràng buộc ở lớp nghiệp vụ. Dù chọn cách nào, cần kiểm tra tại mọi đường ghi liên quan và tại điểm thực thi quyền phù hợp.

Trạng thái tài khoản, tenant hiện hành của phiên và yêu cầu MFA có thể là các điều kiện bổ sung ngoài membership. Một đường ReBAC hợp lệ không tự chứng minh rằng phiên hiện tại đáp ứng mọi yêu cầu để xuất dữ liệu hoặc thực hiện thao tác đặc quyền.

## 10. Chọn nguồn chuẩn cho membership

### 10.1. Dữ liệu nghiệp vụ và graph phân quyền

Membership có thể được quản trị trực tiếp trong ứng dụng hoặc đồng bộ từ hệ thống danh tính bên ngoài. Cần xác định nguồn nào có thẩm quyền cho từng loại assignment.

Một kiến trúc tham khảo có:

~~~text
Nguồn chuẩn membership
    -> sự kiện thay đổi có thứ tự
    -> bộ đồng bộ quan hệ
    -> graph phục vụ kiểm tra quyền
~~~

Graph có thể là nơi lưu dữ kiện chuẩn hoặc là một bản chiếu phục vụ truy vấn. Không nên vừa cho người quản trị sửa trực tiếp trong graph, vừa có một tác vụ đồng bộ ghi đè từ hệ thống khác mà không có quy tắc giải quyết xung đột.

Thông tin như người mời, lý do thêm, ngày phê duyệt và nguồn đồng bộ thường cần nằm trong hồ sơ nghiệp vụ hoặc audit. Tuple cơ bản chỉ biểu diễn quan hệ; đừng giả định nó tự chứa toàn bộ lịch sử quản trị.

### 10.2. Nhiều nguồn cùng cấp một membership

Lan có thể được thêm vào Backend theo hai nguồn:

~~~text
Nguồn 1: nhóm đồng bộ từ hệ thống danh tính
Nguồn 2: assignment thủ công đã được duyệt
~~~

Nếu cả hai đều biểu diễn cùng một tuple direct_member, graph có thể chỉ lưu một quan hệ. Khi nguồn 1 báo gỡ, không nên xóa tuple nếu nguồn 2 vẫn còn hiệu lực theo chính sách.

Cần quản lý provenance của từng grant ở nguồn chuẩn, rồi tính membership tổng hợp:

~~~text
effective_direct_membership(user, team)
    = tồn tại ít nhất một grant hợp lệ cho user và team
~~~

Đó là quy tắc hợp của ví dụ. Nếu hệ thống cần chặn một nguồn cấp hoặc có trạng thái cấm, phải mô hình hóa riêng thay vì giả định việc xóa một grant sẽ phủ định mọi grant còn lại.

Chỉ dùng một bộ đếm mà không giữ định danh grant dễ gây sai khi xử lý sự kiện lặp, thiếu hoặc đến sai thứ tự. Một tập grant có ID ổn định cùng cơ chế đối chiếu thường dễ truy vết hơn.

### 10.3. Định danh ổn định và xóa team

Không dùng email hoặc tên team làm ID có thể bị tái sử dụng mà thiếu quy tắc. Nếu team Backend bị xóa rồi một team mới cùng tên được tạo, team mới không nên thừa hưởng mọi chia sẻ cũ chỉ vì dùng lại ID.

Khi xóa team, cần xác định cách xử lý:

- Membership và các vai trò quản trị của team.
- Quan hệ lồng team vào hoặc từ team khác.
- Những tài nguyên đã chia sẻ cho userset của team.
- Ownership của tài nguyên nếu sản phẩm cho team làm owner.
- Audit và nghĩa vụ lưu lịch sử.

Đổi tên hiển thị thường không thay ID. Xóa và tạo lại là vòng đời khác, cần xử lý những tham chiếu cũ phù hợp.

## 11. Thiết kế thao tác thay đổi membership

### 11.1. Luồng thêm thành viên

Mã giả sau minh họa một ứng dụng có nguồn chuẩn nghiệp vụ và graph được đồng bộ qua outbox. Đây là thiết kế tham khảo, không phải API hoặc bảo đảm transaction của OpenFGA.

~~~text
addMember(actorSession, teamId, targetUserId, requestId):
    actor = authenticateAndResolveActor(actorSession)
    team = loadTrustedTeam(teamId)
    target = loadTrustedIdentity(targetUserId)

    require actor.sessionIsValid
    require target.isEligibleForTeam(team)
    require authorizationCheck(
        actor.id, "can_manage_members", team.id
    ) == ALLOWED

    begin transaction on membership source of truth:
        require team is active
        require expected team membership version is current
        require requestId has not been applied with different input

        createOrKeepApprovedGrant(
            team.id, target.id, source="manual"
        )
        advance membership version
        append durable outbox event
        record audit event
    commit

    return synchronization status
~~~

Trong thiết kế này, kiểm tra quyền diễn ra trước transaction nghiệp vụ. Nếu quyền của actor có thể bị thay đổi đồng thời, cần bổ sung cơ chế phù hợp như xác minh phiên bản quyền, kiểm tra lại ở điểm cam kết hoặc một quy trình ghi có mức nhất quán được thiết kế rõ.

Không có một transaction cục bộ nào tự bảo đảm tính nguyên tử trên cả cơ sở dữ liệu ứng dụng, nguồn danh tính và engine graph độc lập.

Nếu API trả về trước khi graph cập nhật, response cần phân biệt “thay đổi đã được ghi nhận” với “quyền đã có hiệu lực tại mọi điểm kiểm tra”. Giao diện nên phản ánh trạng thái thực tế của luồng đồng bộ.

### 11.2. Idempotency và sự kiện đến sai thứ tự

Client có thể gửi lại request khi mất phản hồi. Cùng một requestId và cùng nội dung nên được xử lý nhất quán, tránh tạo thêm grant hoặc audit nghiệp vụ trùng không cần thiết.

Sự kiện thay đổi cũng có thể được chuyển nhiều lần:

~~~text
version 41: ADD Lan vào Backend
version 42: REMOVE grant của Lan khỏi Backend
~~~

Nếu sự kiện 41 đến sau 42 và bộ đồng bộ không kiểm tra thứ tự, membership cũ có thể xuất hiện trở lại.

Có thể dùng version theo phạm vi tổng hợp phù hợp, kiểm tra trạng thái mới nhất tại nguồn chuẩn, hoặc cơ chế xử lý tuần tự. Không chỉ dựa vào thời gian trên máy gửi để giải quyết mọi xung đột.

Tác vụ reconciliation định kỳ có thể so sánh nguồn chuẩn với graph để phát hiện dữ kiện thiếu hoặc thừa. Nó cần tuân thủ chính sách nhiều nguồn grant, tránh xóa assignment hợp lệ chỉ vì một nguồn không liệt kê assignment đó.

### 11.3. Tránh làm team mất người quản trị cuối cùng

Nếu sản phẩm yêu cầu mỗi team phải còn ít nhất một manager, việc gỡ manager cuối cần được kiểm soát.

Hai manager cùng rời team là một tình huống đồng thời quan trọng. Mỗi request có thể nhìn thấy “còn một manager khác”, nhưng cả hai cùng được ghi thì team không còn manager.

Điều kiện này cần được bảo vệ ở nơi ghi trạng thái chuẩn bằng transaction, khóa hoặc kiểm tra phiên bản phù hợp. Một lần đếm ở giao diện không bảo đảm bất biến.

Team đang được khóa, lưu trữ hoặc chuyển ownership cũng có thể cần những quy tắc riêng. Không suy ra quyền quản trị team chỉ từ việc một người đang sở hữu một tài liệu của team.

## 12. Độ mới dữ liệu và thời gian thu hồi quyền

### 12.1. Xóa membership chưa chắc lập tức đổi mọi kết quả

Giả sử Lan bị gỡ khỏi Backend lúc T0. Backend ứng dụng, graph và các cache có thể quan sát thay đổi ở những thời điểm khác nhau.

~~~text
T0: Nguồn chuẩn ghi nhận gỡ membership
T1: Sự kiện đến bộ đồng bộ
T2: Graph ghi nhận tuple bị xóa
T3: Điểm kiểm tra đọc trạng thái mới hoặc cache cũ hết hiệu lực
~~~

Cần xác định cam kết thu hồi quyền từ thời điểm nào và ở phạm vi nào. “Đã xóa trong database” chưa mô tả đầy đủ cửa sổ còn quyền khi request vẫn dùng cache hoặc graph chưa cập nhật.

OpenFGA có lựa chọn nhất quán khi truy vấn. Theo tài liệu, MINIMIZE_LATENCY có thể sử dụng cache, còn HIGHER_CONSISTENCY bỏ qua cache để đọc database. [Tài liệu OpenFGA về Query Consistency](https://openfga.dev/docs/interacting/consistency).

Chọn cách đọc mới hơn trong engine không làm xuất hiện một sự kiện còn chưa được đồng bộ tới engine, và không tự xóa cache nằm ở gateway hoặc ứng dụng. Cần xét toàn bộ đường dữ liệu.

### 12.2. Những cache cần xem xét

Một cache chỉ dùng userId và documentId có thể thiếu action, tenant, phiên bản mô hình hoặc những ngữ cảnh ảnh hưởng quyết định. Với quyền đi qua team, cache còn phụ thuộc membership và quan hệ chia sẻ của team.

Không nên nghĩ chỉ có thay đổi tài liệu mới làm quyền đọc tài liệu thay đổi. Team có thể được thêm người, lồng vào team khác hoặc mất một membership mà tài liệu không hề được sửa.

Những cơ chế thường cần phối hợp gồm TTL phù hợp, sự kiện vô hiệu hóa, phiên bản quyền hoặc đánh giá lại tại thao tác nhạy cảm. Cơ chế cụ thể phụ thuộc kiến trúc và cam kết độ trễ thu hồi của hệ thống.

Token chứa danh sách team cũng có thể giữ thông tin cũ đến khi hết hạn hoặc bị thu hồi. Nếu backend dùng claim đó làm membership, cần định nghĩa độ mới và xử lý việc rời team; chữ ký token không chứng minh membership chưa thay đổi sau lúc phát hành.

### 12.3. Phiên đang chạy và tác vụ dài

Một người đã bắt đầu tác vụ export trước khi bị gỡ team có thể tiếp tục chạy trong nhiều phút. Cần quy định tác vụ sử dụng quyền tại thời điểm bắt đầu hay phải đánh giá lại ở các mốc quan trọng.

Tương tự, kết nối WebSocket hoặc subscription không nhất thiết chạy lại kiểm tra quyền mỗi khi có membership thay đổi. Sản phẩm cần có cách kết thúc hoặc điều chỉnh việc phân phối dữ liệu theo cam kết của mình.

Versioning và dấu vết trạng thái giúp điều tra, nhưng không thay thế điểm kiểm tra thực thi. Quyết định cũ không phải một giấy phép vô thời hạn.

## 13. Danh sách thành viên và dữ liệu được nhìn thấy

### 13.1. Liệt kê assignment khác liệt kê member có hiệu lực

Với mô hình manager cũng là member, hoặc có team lồng nhau, một bảng chỉ liệt kê direct_member sẽ không thể hiện toàn bộ membership có hiệu lực.

Giao diện có thể hiển thị:

~~~text
Lan  -> trực tiếp trong Backend
Minh -> qua vai trò manager của Backend
Hà   -> qua team Frontend được lồng trong Engineering
~~~

Điều này giúp người quản trị hiểu nguồn quyền. Khi gỡ một hàng, giao diện cần chỉ rõ assignment nào sẽ được gỡ và liệu còn nguồn quyền khác.

Không nên cung cấp nút “gỡ hoàn toàn” nếu backend chỉ xóa một cạnh mà không đánh giá các đường còn lại.

### 13.2. Xem danh sách member cũng là một quyền

Danh sách thành viên có thể tiết lộ cấu trúc tổ chức, khách hàng hoặc nhóm vận hành đặc quyền. Cần xác định ai được xem danh sách, ai được xem nguồn quyền và ai được xem thông tin liên hệ.

Có thể cần quan hệ can_view_members riêng thay vì mặc định mọi người đăng nhập đều được liệt kê team bất kỳ. Phân trang, tìm kiếm và endpoint đếm số lượng cũng cần tuân thủ phạm vi được phép.

### 13.3. Membership check không thay thế lọc tài nguyên

Khi trả về danh sách tài liệu, không nên lấy toàn bộ tài liệu của tenant chỉ vì người dùng thuộc một team trong tenant đó.

Danh sách phải phản ánh quyền trên từng đối tượng hoặc sử dụng truy vấn quyền phù hợp với mô hình. Cũng cần bảo vệ endpoint mở tài liệu trực tiếp; một danh sách đã lọc không ngăn người dùng đoán ID rồi gọi endpoint khác.

Dữ liệu tìm kiếm, bộ đếm và tệp đính kèm cần cùng nguyên tắc phạm vi quyền. Quyền đọc tài liệu không tự biến thành quyền quản lý membership của team được chia sẻ tài liệu.

## 14. Audit và giải thích nguồn quyền

Hai loại sự kiện có giá trị khác nhau:

1. Sự kiện quản trị: ai thêm hoặc gỡ membership, thay vai trò, lồng team hay chia sẻ tài nguyên.
2. Sự kiện thực thi: danh tính nào yêu cầu hành động nào, trên tài nguyên nào, kết quả ra sao.

Một bản ghi quản trị minh họa:

~~~json
{
  "event_id": "membership-event-912",
  "actor_id": "user:minh",
  "action": "team.member.add",
  "tenant_id": "tenant-a",
  "team_id": "tenant-a-backend",
  "target_user_id": "user:lan",
  "grant_source": "manual",
  "membership_version": 41,
  "request_id": "request-73",
  "outcome": "SOURCE_COMMITTED",
  "graph_sync_status": "PENDING"
}
~~~

Đây là schema minh họa của ứng dụng. Kết quả SOURCE_COMMITTED ghi nhận nguồn chuẩn đã commit; nó chưa tuyên bố graph đã phục vụ quyền mới.

Đối với một quyết định truy cập, thông tin hữu ích có thể gồm ID model, ID quyết định, quan hệ cần kiểm tra, phiên bản hoặc mức nhất quán quan sát được, cùng kết quả thực thi.

Nếu hệ thống giải thích quyền bằng một đường graph, đường đó là bằng chứng cho một cách có quyền, chưa chắc là danh sách đầy đủ mọi đường. Điều này đặc biệt quan trọng khi lập kế hoạch thu hồi.

Không lưu access token, mật khẩu hoặc dữ liệu tài liệu đầy đủ vào log membership. Quyền đọc log và thời hạn lưu cần phù hợp với thông tin danh tính được ghi.

## 15. Thiết kế kiểm thử cho team membership

Kiểm thử cần dùng mô hình cùng một tập tuple xác định, rồi nêu kết quả mong đợi theo yêu cầu nghiệp vụ. Không coi một kết quả Allow do engine trả về là đúng chỉ vì dữ liệu hợp lệ về kiểu.

OpenFGA hỗ trợ kiểm thử model bằng tệp store có model, tuple và các assertion cho truy vấn. [Tài liệu OpenFGA về Testing Models](https://openfga.dev/docs/modeling/testing).

Ma trận sau áp dụng cho mô hình minh họa và những yêu cầu bổ sung trong bài:

| Tình huống | Kết quả hoặc thuộc tính cần xác nhận |
| --- | --- |
| Lan là direct_member của Backend, Backend có editor | Lan được editor và viewer trên tài liệu |
| Lan chỉ là member, không có manager | Lan không được can_manage_members |
| Minh có manager nhưng không có direct_member | Minh vẫn được member theo union đã chọn |
| Hà chỉ thuộc Frontend, chưa được chia sẻ tài liệu | Hà không được viewer trên tài liệu API |
| An là owner của tài liệu, không là manager Backend | An được can_share tài liệu, không được quản lý team |
| Gỡ đường membership duy nhất của Lan | Quyền qua Backend mất khi trạng thái mới có hiệu lực |
| Lan còn viewer trực tiếp sau khi rời team | Lan vẫn xem được nhưng không tự còn editor |
| Gỡ direct_member trong khi manager còn tồn tại | Member vẫn có hiệu lực theo manager |
| Backend nằm trong Engineering | Member Backend được suy ra vào Engineering, chiều ngược không tự đúng |
| Lan có hai đường qua hai team con | Xóa một đường không xóa đường còn lại |
| Tạo quan hệ giữa team hoặc tài nguyên khác tenant | Bị chặn nếu không có cơ chế liên tenant được duyệt |
| Client đổi relation từ direct_member thành manager | API không tạo vai trò ngoài thao tác được cho phép |
| Lời mời chưa chấp nhận hoặc đã hết hạn | Không tạo quyền membership ACTIVE |
| Sự kiện ADD cũ đến sau REMOVE mới | Không phục hồi membership lỗi thời |
| Gỡ hai manager cuối đồng thời | Giữ đúng quy định không để team mất manager |
| Engine timeout hoặc lỗi đánh giá | Không thực hiện thao tác khi chưa có kết quả cho phép hợp lệ |

Ngoài các ca này, cần kiểm tra trường hợp user, team và tài liệu không tồn tại; team bị xóa; ID được tái sử dụng; tài khoản bị vô hiệu hóa; và một nguồn grant bị gỡ trong khi nguồn khác còn hợp lệ.

Kiểm thử model tập trung vào phép suy ra. Kiểm thử tích hợp cần xác nhận endpoint thực sự kiểm tra actor, kiểm tra tenant, chặn việc ghi tuple tùy ý và xử lý trạng thái đồng bộ đúng hợp đồng.

## 16. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách điều chỉnh |
| --- | --- | --- |
| Chỉ kiểm tra người dùng thuộc một team bất kỳ | Cấp quyền ngoài phạm vi tài nguyên | Kiểm tra đúng quan hệ trên đúng đối tượng |
| Coi member là owner hoặc manager | Mở quyền quản trị vượt yêu cầu | Tách các quan hệ và quyền suy ra |
| Cấp cho team object nhưng mong tự mở rộng tới member | Dữ liệu không có ngữ nghĩa mong muốn | Dùng userset và quy tắc mô hình tương ứng |
| Coi prefix tenant trong ID là rào bảo vệ | Có thể ghi quan hệ liên tenant sai | Kiểm tra dữ liệu tenant ở các đường ghi và thực thi |
| Gỡ một membership rồi báo đã thu hồi mọi quyền | Bỏ sót grant hoặc đường quan hệ khác | Phân tích các nguồn quyền còn hiệu lực |
| Đồng bộ từ nhiều nguồn nhưng không giữ provenance | Một nguồn gỡ làm mất hoặc làm sống lại quyền sai | Quản lý grant và thứ tự cập nhật ở nguồn chuẩn |
| Dùng cache quá cũ sau thao tác gỡ | Quyền tồn tại lâu hơn cam kết | Thiết kế freshness và vô hiệu hóa xuyên các lớp |
| Cho client tự ghi relation tùy ý | Người dùng tự cấp manager hoặc owner | Ánh xạ thao tác qua API quản trị có kiểm tra |
| Tự lan truyền mọi vai trò theo cây tổ chức | Quyền quản trị bị mở rộng ngoài ý định | Chỉ kế thừa những quan hệ được định nghĩa rõ |

## 17. Bài tập vận dụng

### Bài 1: Gỡ khỏi team nhưng vẫn đọc được

Lan đã bị gỡ direct_member khỏi Backend. Lan không còn editor nhưng vẫn đọc được tài liệu API.

Hãy tìm những đường có thể giải thích kết quả: viewer trực tiếp, membership ở team khác được chia sẻ, manager còn tồn tại, ownership hoặc trạng thái cache chưa mới. Phân biệt đường quyền hợp lệ còn lại với lỗi đồng bộ thu hồi.

### Bài 2: Team lồng nhau

Backend và Security đều nằm trong Engineering. Lan thuộc Backend và Security. Engineering được cấp viewer trên tài liệu kiến trúc.

Nếu chỉ gỡ Lan khỏi Backend, quyền viewer qua Security vẫn tồn tại. Hãy xác định cần thay đổi những quan hệ nào nếu yêu cầu thực sự là Lan không còn được đọc tài liệu đó, đồng thời xem xét các quyền quản trị cần thiết để thực hiện.

### Bài 3: Người quản lý team và quyền sở hữu tài nguyên

Minh là manager của Backend. An là owner tài liệu API. Theo mô hình bài học, Minh có thể thêm member vào Backend, nhưng không có can_share trên tài liệu. An có can_share, nhưng không có can_manage_members trên Backend.

Giải thích vì sao việc Minh có thể gián tiếp cấp quyền tài liệu bằng cách thêm người vào team vẫn cần được An hoặc chính sách chia sẻ chấp nhận khi tài liệu được chia sẻ cho team.

### Bài 4: Chuyển một team sang tenant khác

Một yêu cầu vận hành muốn đổi tenant của Backend nhưng giữ nguyên mọi membership và chia sẻ tài liệu.

Hãy phân tích ràng buộc của danh tính thành viên, quan hệ team lồng nhau, các tài nguyên đang chia sẻ và ownership. Không xem đây chỉ là sửa một cột tenant_id; việc chuyển phạm vi có thể làm thay đổi tập người được quyền truy cập dữ liệu.

Khi thiết kế team membership, điều cần giữ rõ là quan hệ được ghi, quyền được suy ra và những điều kiện bổ sung khi thực thi. Mỗi thao tác thêm, gỡ hoặc lồng team đều cần được hiểu theo các đường quyền mà nó tạo ra hoặc loại bỏ.
