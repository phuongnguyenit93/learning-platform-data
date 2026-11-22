# Quản lý tài khoản, vai trò, vùng khách hàng (tenant) và quan hệ giữa các thực thể

## Mục tiêu bài học

Dữ liệu kiểm thử quyết định liệu một bài kiểm thử có thể xác minh đúng hành vi của sản phẩm hay không. Với hệ thống nhiều khách hàng hoặc nhiều tổ chức cùng sử dụng, chỉ tạo một vài tài khoản mẫu là chưa đủ. Nhóm cần mô hình hóa người dùng, tài khoản, vai trò, quyền, tenant và các quan hệ giữa thực thể sao cho phản ánh đúng quy tắc nghiệp vụ, đồng thời có thể kiểm tra quyền truy cập, ranh giới dữ liệu và tính toàn vẹn.

Trong chiến lược VALIDATION_TESTING_STRATEGY, dữ liệu kiểm thử cần được thiết kế như một phần của phạm vi kiểm thử. Mỗi fixture phải trả lời được câu hỏi: ai đang thực hiện hành động, thuộc tenant nào, có vai trò gì, được phép thao tác trên dữ liệu nào và quan hệ giữa các bản ghi có hợp lệ không. Một bộ dữ liệu tốt giúp tạo ra cả trường hợp được phép lẫn bị từ chối, trường hợp bình thường lẫn ngoại lệ, và có thể tái tạo trong nhiều lần chạy.

Sau bài học, người học có thể:

- Phân biệt tài khoản, danh tính người dùng, vai trò, quyền và tenant.
- Mô hình hóa quan hệ giữa người dùng, tenant, vai trò và các thực thể nghiệp vụ.
- Thiết kế dữ liệu để kiểm tra quyền truy cập và cô lập dữ liệu giữa tenant.
- Tạo fixture đại diện cho quan hệ một-một, một-nhiều và nhiều-nhiều.
- Kiểm tra các trường hợp hợp lệ, không hợp lệ, biên và dữ liệu tham chiếu bị thiếu.
- Quản lý dữ liệu tổng hợp, dữ liệu nhạy cảm, vòng đời và khả năng tái lập.
- Xây dựng bộ dữ liệu có thể mở rộng, độc lập và dễ chẩn đoán cho kiểm thử tự động.

## 1. Vì sao cần quản lý dữ liệu tài khoản và quan hệ thực thể?

Một hệ thống quản lý khách hàng, nền tảng SaaS hoặc ứng dụng doanh nghiệp thường có nhiều loại đối tượng liên kết với nhau. Một người dùng có thể tham gia nhiều tổ chức; mỗi tổ chức có chính sách quyền riêng; một vai trò có thể cấp nhiều quyền; một hồ sơ hoặc đơn hàng thuộc về một tenant; một người dùng có thể được giao phụ trách nhiều hồ sơ.

Nếu dữ liệu kiểm thử chỉ có một tài khoản quản trị và một bản ghi đơn giản, bộ kiểm thử khó phát hiện những lỗi như:

- Người dùng tenant A đọc được hồ sơ thuộc tenant B.
- Người dùng có vai trò nhân viên thực hiện được thao tác chỉ dành cho quản trị viên.
- Một người dùng bị gán hai vai trò xung đột nhưng hệ thống xử lý sai.
- Tài khoản đã bị vô hiệu hóa vẫn truy cập được dữ liệu qua phiên cũ.
- Bản ghi con được gắn với tenant khác với bản ghi cha.
- Xóa người dùng làm mất lịch sử giao dịch cần lưu.
- Một quan hệ nhiều-nhiều bị tạo trùng hoặc không được thu hồi đúng cách.
- Truy vấn chỉ lọc theo ID mà quên điều kiện tenant.
- Dữ liệu seed không nhất quán khiến test phụ thuộc thứ tự chạy.

Những lỗi này thường nằm ở ranh giới giữa danh tính, quyền và quan hệ dữ liệu. Do đó, bộ dữ liệu kiểm thử cần mô tả được nhiều tenant, nhiều người dùng, nhiều vai trò và những quan hệ có ý nghĩa, thay vì chỉ tạo các bản ghi độc lập.

## 2. Phân biệt các khái niệm dữ liệu cốt lõi

Các khái niệm sau có liên quan nhưng không nên đồng nhất:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Người dùng (user/person) | Chủ thể con người hoặc danh tính được hệ thống nhận diện. | Nhân viên Nguyễn A, khách hàng B. |
| Tài khoản (account) | Thông tin đăng nhập và trạng thái truy cập của một danh tính trong hệ thống. | Tài khoản đang hoạt động, bị khóa hoặc chờ kích hoạt. |
| Tenant | Không gian dữ liệu và cấu hình của một khách hàng, tổ chức hoặc đơn vị sử dụng chung nền tảng. | Công ty Alpha, Công ty Beta. |
| Vai trò (role) | Nhóm trách nhiệm hoặc tập quyền được gán cho người dùng trong một phạm vi. | Tenant Admin, Manager, Staff, Viewer. |
| Quyền (permission) | Hành động cụ thể được cho phép trên một loại tài nguyên hoặc phạm vi dữ liệu. | order.read, order.approve, user.manage. |
| Membership | Quan hệ cho biết một người dùng là thành viên của tenant nào và có trạng thái gì. | User 12 là Manager tại tenant Alpha. |
| Tài nguyên (resource) | Đối tượng nghiệp vụ mà người dùng có thể xem hoặc thao tác. | Đơn hàng, hóa đơn, hồ sơ khách hàng. |
| Quan hệ (relationship) | Liên kết giữa các thực thể, có thể mang thuộc tính và quy tắc riêng. | Người dùng phụ trách hồ sơ; đơn hàng thuộc khách hàng. |

Một người có thể có một danh tính nhưng nhiều membership. Vai trò của họ có thể khác nhau ở từng tenant. Ví dụ, cùng một người là quản trị viên ở tổ chức Alpha nhưng chỉ là người xem ở tổ chức Beta. Vì vậy, vai trò thường cần được gắn với membership hoặc phạm vi tài nguyên, không nên luôn lưu như thuộc tính toàn cục của tài khoản.

### 2.1. Danh tính, xác thực và phân quyền

Ba khái niệm này cần được tách rõ:

- **Danh tính (identity):** xác định ai đang sử dụng hệ thống.
- **Xác thực (authentication):** kiểm tra người dùng có chứng minh được danh tính hay không.
- **Phân quyền (authorization):** quyết định danh tính đã xác thực có được thực hiện hành động trên tài nguyên cụ thể hay không.

Kiểm thử đăng nhập thành công không chứng minh phân quyền đúng. Một tài khoản hợp lệ vẫn có thể không được xem dữ liệu của tenant khác. Bộ dữ liệu nên cho phép kiểm tra riêng xác thực, trạng thái tài khoản, membership, vai trò, quyền và phạm vi tài nguyên.

### 2.2. Tenant là ranh giới dữ liệu

Trong kiến trúc multi-tenant, tenant thường đại diện cho một khách hàng hoặc tổ chức dùng chung hạ tầng ứng dụng. Mỗi tenant có thể có người dùng, cấu hình, dữ liệu và chính sách riêng.

Một số mô hình lưu trữ phổ biến:

- **Database riêng cho mỗi tenant:** mức cô lập cao nhưng quản lý vận hành phức tạp hơn.
- **Schema riêng cho mỗi tenant:** phân tách ở cấp schema, vẫn dùng chung một database.
- **Bảng dùng chung có tenant_id:** các bản ghi mang định danh tenant và truy vấn cần lọc đúng phạm vi.

Mỗi mô hình tạo ra rủi ro khác nhau. Với bảng dùng chung, thiếu điều kiện tenant trong truy vấn có thể làm lộ dữ liệu. Với database hoặc schema riêng, lỗi định tuyến kết nối hoặc cấu hình tenant có thể đưa request đến nhầm nơi. Kiểm thử cần phản ánh mô hình thực tế của sản phẩm.

## 3. Mô hình hóa quan hệ giữa các thực thể

Dữ liệu kiểm thử nên tuân thủ quan hệ và ràng buộc giống hệ thống. Quan hệ sai có thể khiến test thất bại vì fixture không hợp lệ hoặc che giấu lỗi sản phẩm.

### 3.1. Quan hệ một-một, một-nhiều và nhiều-nhiều

| Kiểu quan hệ | Ý nghĩa | Ví dụ | Rủi ro cần kiểm tra |
|---|---|---|---|
| Một-một (1:1) | Một thực thể liên kết tối đa một thực thể khác trong phạm vi quy định. | User và hồ sơ cá nhân. | Tạo trùng, thiếu hồ sơ hoặc liên kết nhầm. |
| Một-nhiều (1:N) | Một thực thể cha có nhiều thực thể con. | Tenant có nhiều membership; khách hàng có nhiều đơn hàng. | Bản ghi con mồ côi, sai khóa ngoại, thiếu lọc tenant. |
| Nhiều-nhiều (N:M) | Nhiều thực thể ở hai phía có thể liên kết với nhau thông qua bảng liên kết. | User tham gia nhiều tenant; role được gán cho nhiều membership. | Quan hệ trùng, thu hồi sai hoặc áp dụng quyền ngoài phạm vi. |

### 3.2. Quan hệ có thuộc tính riêng

Một quan hệ không phải lúc nào cũng chỉ là hai khóa ngoại. Membership có thể chứa:

- Trạng thái tham gia: invited, active, suspended, removed.
- Ngày bắt đầu và ngày kết thúc.
- Người mời hoặc người phê duyệt.
- Vai trò trong tenant.
- Nhóm hoặc phòng ban.
- Cờ xác nhận lời mời.
- Nguồn gán quyền hoặc lý do thay đổi.

Khi quan hệ mang thuộc tính, nên mô hình hóa nó thành thực thể riêng thay vì lưu một danh sách đơn giản trong User. Điều này cho phép kiểm thử trạng thái và lịch sử của quan hệ một cách rõ ràng.

### 3.3. Sơ đồ quan hệ minh họa

~~~mermaid
erDiagram
    USER ||--o{ MEMBERSHIP : joins
    TENANT ||--o{ MEMBERSHIP : contains
    MEMBERSHIP ||--o{ MEMBERSHIP_ROLE : has
    ROLE ||--o{ MEMBERSHIP_ROLE : assigned
    ROLE ||--o{ ROLE_PERMISSION : grants
    PERMISSION ||--o{ ROLE_PERMISSION : included
    TENANT ||--o{ CUSTOMER : owns
    CUSTOMER ||--o{ ORDER : places
    USER ||--o{ RESOURCE_ASSIGNMENT : assigned
    ORDER ||--o{ RESOURCE_ASSIGNMENT : linked
~~~

Sơ đồ thể hiện một mô hình ví dụ: người dùng có thể tham gia nhiều tenant; mỗi membership có thể có một hoặc nhiều vai trò; vai trò liên kết với quyền; dữ liệu nghiệp vụ thuộc tenant. Một hệ thống cụ thể có thể dùng cấu trúc khác, nhưng các ranh giới và bất biến cần được xác định tương đương.

## 4. Thiết kế dữ liệu kiểm thử cho nhiều tenant

Để kiểm tra tenant isolation, ít nhất cần có hai tenant độc lập và các tài nguyên có thể phân biệt. Chỉ có một tenant thì không thể chứng minh hệ thống ngăn truy cập chéo tenant.

Một bộ dữ liệu cơ sở có thể gồm:

| Mã | Tenant | Người dùng | Membership | Vai trò | Tài nguyên |
|---|---|---|---|---|---|
| A1 | Alpha | Alice | Active | Tenant Admin | Khách hàng A, đơn hàng A |
| A2 | Alpha | An | Active | Staff | Khách hàng A2, đơn hàng A2 |
| A3 | Alpha | Anh | Suspended | Manager | Không được thao tác khi bị đình chỉ |
| B1 | Beta | Bình | Active | Tenant Admin | Khách hàng B, đơn hàng B |
| B2 | Beta | Bảo | Active | Viewer | Chỉ xem tài nguyên Beta |
| C1 | Gamma | Chi | Invited | Staff | Chưa kích hoạt membership |

Dữ liệu này cho phép kiểm tra:

- Alice có thể quản trị tenant Alpha nhưng không được truy cập Beta.
- An có thể thực hiện các thao tác dành cho Staff trong Alpha.
- Anh có vai trò Manager nhưng membership bị Suspended nên không được thao tác.
- Bình có quyền quản trị Beta nhưng không có quyền trên Alpha.
- Bảo chỉ xem được tài nguyên Beta, không được sửa.
- Chi chưa kích hoạt membership nên không được truy cập tenant Gamma.

### 4.1. Kiểm tra truy cập cùng tenant và khác tenant

Với mỗi loại tài nguyên, cần có cả trường hợp hợp lệ và không hợp lệ:

| Chủ thể | Tài nguyên | Kết quả mong đợi |
|---|---|---|
| Alice (Alpha Admin) | Đơn hàng Alpha | Được phép theo quyền quản trị. |
| An (Alpha Staff) | Đơn hàng Alpha được phép xem | Được phép. |
| An (Alpha Staff) | Thao tác quản trị người dùng Alpha | Bị từ chối nếu không có quyền. |
| Alice (Alpha Admin) | Đơn hàng Beta | Bị từ chối hoặc không tìm thấy theo chính sách API. |
| Bình (Beta Admin) | Đơn hàng Alpha | Bị từ chối. |
| Bảo (Beta Viewer) | Đọc đơn hàng Beta | Được phép. |
| Bảo (Beta Viewer) | Sửa đơn hàng Beta | Bị từ chối. |
| Anh (Alpha Manager, Suspended) | Đơn hàng Alpha | Bị từ chối do membership không hoạt động. |

Cần kiểm tra cả đường truy cập trực tiếp bằng ID, truy vấn danh sách, tìm kiếm, xuất dữ liệu, tải tệp đính kèm và API phụ trợ. Lọc tenant ở màn hình danh sách không đủ nếu endpoint chi tiết hoặc export vẫn có thể truy cập dữ liệu ngoài phạm vi.

### 4.2. Không chỉ kiểm tra phản hồi HTTP

Khi truy cập chéo tenant bị từ chối, cần xác minh dữ liệu không bị lộ qua:

- Nội dung response.
- Thông báo lỗi chứa tên hoặc thông tin của tài nguyên.
- Metadata, số lượng bản ghi hoặc gợi ý tìm kiếm.
- File export hoặc URL tải xuống.
- Log hoặc event được gửi đến consumer không có quyền.
- Cache dùng chung giữa tenant.

Tùy chính sách sản phẩm, API có thể trả 403 hoặc 404. Điều quan trọng là hành vi được thống nhất và không tiết lộ thông tin trái phép. Test nên kiểm tra cả mã phản hồi và tác dụng phụ liên quan.

## 5. Thiết kế ma trận vai trò và quyền

Vai trò giúp gom nhóm quyền theo trách nhiệm. Tuy nhiên, tên vai trò không đủ để chứng minh quyền đúng. Nhóm cần có ma trận quyền xác định hành động nào được phép trên tài nguyên nào và trong phạm vi nào.

### 5.1. Ma trận quyền cơ bản

Ví dụ cho một ứng dụng quản lý đơn hàng:

| Hành động | Viewer | Staff | Manager | Tenant Admin |
|---|---:|---:|---:|---:|
| Xem đơn hàng trong tenant | Có | Có | Có | Có |
| Tạo đơn hàng | Không | Có | Có | Có |
| Sửa đơn hàng của người khác | Không | Theo quy tắc | Có | Có |
| Phê duyệt đơn hàng | Không | Không | Có | Có |
| Hoàn tiền | Không | Theo ủy quyền | Có | Có |
| Quản lý thành viên | Không | Không | Theo phạm vi | Có |
| Thay đổi cấu hình tenant | Không | Không | Không | Có |

Ma trận chỉ là ví dụ. Quyền thực tế phải đến từ chính sách sản phẩm. Nếu quyền phụ thuộc sở hữu tài nguyên, phòng ban, hạn mức hoặc trạng thái giao dịch, cần bổ sung các điều kiện đó.

### 5.2. Kiểm tra quyền theo hành động và phạm vi

Một người dùng có thể có quyền order.update nhưng chỉ trên đơn hàng do họ phụ trách hoặc trong một nhóm cụ thể. Vì vậy, kiểm thử cần phân biệt:

- Có quyền ở mức chức năng.
- Có quyền trên loại tài nguyên.
- Có quyền trong tenant.
- Có quyền trên tài nguyên cụ thể.
- Có quyền trong trạng thái nghiệp vụ hiện tại.
- Có quyền trong giới hạn thời gian hoặc hạn mức.

Ví dụ, Manager có thể phê duyệt đơn hàng thuộc tenant của mình nhưng không thể phê duyệt đơn hàng đã bị hủy hoặc đơn hàng thuộc tenant khác.

### 5.3. Quyền kế thừa và xung đột

Nếu sản phẩm hỗ trợ nhiều vai trò, nhóm cần xác định cách hợp nhất quyền:

- Quyền được cộng dồn hay có quy tắc ưu tiên?
- Một quyền bị từ chối có thể ghi đè quyền được cấp từ vai trò khác không?
- Vai trò cấp tenant có áp dụng cho mọi tài nguyên trong tenant không?
- Quyền tạm thời hết hiệu lực lúc nào?
- Thu hồi một vai trò có làm mất quyền ngay lập tức hay sau khi phiên được làm mới?

Không nên tự giả định rằng nhiều vai trò luôn cộng dồn quyền. Cần kiểm thử theo chính sách đã thống nhất, đặc biệt khi có deny rule, quyền tạm thời hoặc quyền kế thừa.

## 6. Kiểm thử vòng đời tài khoản và membership

Tài khoản và membership có vòng đời riêng. Một tài khoản có thể đang hoạt động nhưng membership trong một tenant đã bị đình chỉ. Ngược lại, người dùng có thể có lời mời vào tenant nhưng chưa kích hoạt tài khoản.

### 6.1. Trạng thái tài khoản

Các trạng thái thường gặp:

- Pending activation: chờ kích hoạt.
- Active: đang hoạt động.
- Locked: bị khóa do chính sách bảo mật.
- Disabled: bị vô hiệu hóa.
- Password reset required: cần đổi mật khẩu.
- Deleted hoặc anonymized: đã xóa hoặc ẩn danh theo chính sách.

### 6.2. Trạng thái membership

- Invited: đã được mời nhưng chưa chấp nhận.
- Active: đang là thành viên.
- Suspended: tạm đình chỉ.
- Removed: đã bị gỡ khỏi tenant.
- Expired: quyền tham gia đã hết hạn.

Cần kiểm tra sự kết hợp giữa trạng thái account và membership. Ví dụ:

| Account | Membership | Kết quả kỳ vọng |
|---|---|---|
| Active | Active | Có thể truy cập nếu quyền phù hợp. |
| Active | Suspended | Không được truy cập tenant đó. |
| Disabled | Active | Không được đăng nhập hoặc thao tác. |
| Pending | Invited | Chỉ được thực hiện luồng chấp nhận lời mời nếu chính sách cho phép. |
| Active | Removed | Không còn quyền trong tenant. |
| Locked | Active | Không thể dùng tài khoản trong thời gian khóa. |

### 6.3. Phiên đăng nhập và thu hồi quyền

Thay đổi trạng thái tài khoản hoặc membership có thể cần vô hiệu hóa phiên hoặc token đang tồn tại. Kiểm thử nên xác minh:

- Tài khoản bị khóa không thể tạo phiên mới.
- Membership bị đình chỉ làm mất quyền truy cập tenant tương ứng.
- Thu hồi vai trò có hiệu lực theo thời gian đã quy định.
- Token cũ không tiếp tục cấp quyền ngoài chính sách.
- Người dùng vẫn có thể truy cập tenant khác nếu tài khoản và membership ở tenant đó còn hợp lệ.

Trường hợp cuối đặc biệt quan trọng với người dùng tham gia nhiều tenant: đình chỉ ở một tổ chức không nhất thiết đồng nghĩa vô hiệu hóa toàn bộ danh tính.

## 7. Thiết kế fixture cho quan hệ thực thể

Fixture là tập dữ liệu và trạng thái được tạo để phục vụ một hoặc nhiều kiểm thử. Fixture cần đủ nhỏ để hiểu, đủ thực tế để kiểm tra và có thể tái tạo.

### 7.1. Tạo theo cụm nghiệp vụ

Thay vì tạo từng bản ghi rời rạc, có thể tạo một cụm gồm:

1. Tenant.
2. Người dùng và tài khoản.
3. Membership.
4. Vai trò và quyền.
5. Khách hàng hoặc đối tượng nghiệp vụ.
6. Tài nguyên thuộc tenant.
7. Quan hệ phân công hoặc sở hữu.

Cụm dữ liệu giúp người đọc thấy rõ ngữ cảnh. Tuy nhiên, không nên tạo toàn bộ hệ thống cho mỗi test nếu test chỉ cần một phần nhỏ. Tạo fixture theo mục tiêu và chỉ thêm thực thể có liên quan.

### 7.2. Dùng factory hoặc builder

Ví dụ minh họa bằng Java:

~~~java
Tenant alpha = tenantFactory.create("tenant-alpha");
User alice = userFactory.createActive("alice@example.test");
Membership membership = membershipFactory.create(
    alice,
    alpha,
    MembershipStatus.ACTIVE
);
membershipRoleRepository.assign(membership, Role.TENANT_ADMIN);

Customer customer = customerFactory.createInTenant(alpha);
Order order = orderFactory.createFor(customer);
~~~

Các factory cần bảo đảm khóa ngoại, tenant và trạng thái nhất quán. Test nên nhìn thấy những thuộc tính quan trọng như tenant, role và membership status thay vì để helper tạo ngầm các giá trị có ảnh hưởng đến kết quả.

### 7.3. Dữ liệu mặc định an toàn

Một builder có thể cung cấp mặc định hợp lệ để giảm lặp, nhưng mặc định không nên cấp quyền cao nhất hoặc gắn mọi thực thể vào một tenant chung. Mặc định quá rộng có thể khiến test vô tình vượt qua vì tài khoản được cấp quyền không cần thiết.

Nên chọn nguyên tắc:

- Vai trò mặc định là quyền tối thiểu cần thiết.
- Tenant phải được chỉ định rõ với dữ liệu thuộc tenant.
- Trạng thái account và membership phải hiển thị khi liên quan.
- ID và email kiểm thử phải duy nhất hoặc có namespace.
- Quan hệ được tạo rõ ràng, không phụ thuộc dữ liệu tồn dư.
- Mỗi test chỉ tạo dữ liệu cần cho mục tiêu của nó.

## 8. Kiểm tra tính toàn vẹn và các quan hệ bất thường

Ngoài quyền truy cập, cần kiểm tra các quy tắc dữ liệu bảo đảm quan hệ hợp lệ.

### 8.1. Khóa ngoại và bản ghi mồ côi

Các trường hợp cần kiểm tra:

- Membership không được tham chiếu đến user hoặc tenant không tồn tại.
- Đơn hàng không được tham chiếu đến khách hàng đã bị xóa theo cách vi phạm chính sách.
- Quan hệ phân công không được gắn đến tài nguyên không tồn tại.
- Vai trò được gán phải tồn tại và được phép dùng trong tenant.
- Xóa tenant cần xử lý các bản ghi con theo chính sách lưu trữ hoặc xóa.

### 8.2. Quan hệ trùng lặp

Nếu một user chỉ được có một membership active trong một tenant, cần kiểm tra ràng buộc duy nhất. Nếu một membership không thể được gán cùng một role hai lần, hệ thống phải từ chối hoặc xử lý idempotent theo thiết kế.

Ví dụ các trường hợp:

- Tạo membership trùng cho cùng user và tenant.
- Gán cùng role nhiều lần.
- Gán một user vào cùng nhóm hai lần.
- Tạo hai quan hệ sở hữu trái ngược cho một tài nguyên chỉ có một chủ sở hữu.
- Gán một tài nguyên cho hai tenant khác nhau.

### 8.3. Quan hệ bị thay đổi theo thời gian

Một số quan hệ cần lịch sử thay vì ghi đè. Ví dụ, một đơn hàng đổi người phụ trách hoặc một nhân viên chuyển phòng ban. Kiểm thử nên xác minh:

- Lịch sử cũ được giữ theo chính sách.
- Quan hệ hiện tại được cập nhật đúng.
- Báo cáo lịch sử phản ánh thời điểm hiệu lực.
- Thu hồi quan hệ không xóa nhầm tài nguyên.
- Thời gian bắt đầu/kết thúc không tạo khoảng trống hoặc chồng lấn trái phép.

### 8.4. Xóa mềm và ẩn danh

Xóa user hoặc tenant có thể không đồng nghĩa xóa mọi dữ liệu liên quan. Hệ thống có thể phải giữ lịch sử giao dịch, audit log hoặc hồ sơ theo nghĩa vụ lưu trữ. Test cần phân biệt:

- Vô hiệu hóa tài khoản.
- Gỡ membership.
- Xóa mềm thực thể.
- Ẩn danh dữ liệu cá nhân.
- Xóa vật lý khi được phép.
- Giữ lại dữ liệu nghiệp vụ cần thiết.

Không nên viết fixture cleanup xóa toàn bộ bản ghi liên quan nếu điều đó không phản ánh chính sách sản phẩm. Dữ liệu dùng trong kiểm thử cần được dọn dẹp an toàn, nhưng logic xóa của sản phẩm phải được kiểm tra theo quy tắc riêng.

## 9. Kiểm thử truy vấn và ranh giới tenant

Với mô hình bảng dùng chung, mọi truy vấn truy cập tài nguyên cần áp dụng phạm vi tenant theo chính sách. Kiểm thử nên kiểm tra cả truy vấn đọc và thao tác ghi.

### 9.1. Đọc và tìm kiếm

- Danh sách chỉ trả về tài nguyên trong tenant hiện tại.
- Truy vấn chi tiết bằng ID không vượt qua ranh giới tenant.
- Bộ lọc, tìm kiếm, phân trang và sắp xếp không trộn dữ liệu.
- Số lượng tổng hợp và dashboard không tính dữ liệu tenant khác.
- Export và báo cáo chỉ bao gồm phạm vi được phép.

### 9.2. Ghi và cập nhật

- Tạo tài nguyên phải gắn với tenant hợp lệ.
- Client không thể tự gửi tenant_id tùy ý để ghi sang tenant khác.
- Cập nhật không thể đổi tenant của tài nguyên nếu chính sách không cho phép.
- Quan hệ giữa bản ghi cha và con phải thuộc cùng phạm vi tenant khi yêu cầu.
- Thao tác hàng loạt không được tác động đến ID ngoài tenant.

### 9.3. Tác vụ nền và cache

Ranh giới tenant không chỉ áp dụng cho request đồng bộ. Cần kiểm tra:

- Job nền mang đúng tenant context khi chạy.
- Event hoặc message có đủ định danh tenant và được consumer xác minh.
- Cache key phân biệt tenant khi dữ liệu phụ thuộc tenant.
- File hoặc object storage dùng đường dẫn và quyền truy cập đúng tenant.
- Search index và báo cáo phân vùng dữ liệu đúng.
- Retry hoặc dead-letter processing không làm mất tenant context.

Một test API pass không chứng minh mọi tác vụ nền và cache đều cô lập đúng. Hãy chọn kiểm thử tại các ranh giới có rủi ro.

## 10. Dữ liệu tổng hợp và bảo vệ thông tin nhạy cảm

Dữ liệu kiểm thử cần đại diện cho thực tế nhưng không nên tạo rủi ro lộ thông tin. Ưu tiên dữ liệu tổng hợp (synthetic data) được tạo cho kiểm thử.

### 10.1. Nguyên tắc tạo dữ liệu tổng hợp

- Dùng tên, email, số điện thoại và địa chỉ giả lập với miền hoặc dải được dành cho kiểm thử.
- Không dùng mật khẩu production hoặc bí mật thật.
- Tạo dữ liệu có định dạng hợp lệ để kiểm tra luồng, nhưng không trùng dữ liệu cá nhân thật.
- Tạo giá trị biên và dữ liệu không hợp lệ có chủ đích.
- Dùng ID dễ nhận biết trong log nhưng không chứa thông tin cá nhân.
- Kiểm soát seed để có thể tái tạo cùng tập dữ liệu.
- Gắn nhãn hoặc namespace cho dữ liệu kiểm thử để tránh nhầm với dữ liệu thật.

### 10.2. Khi cần dữ liệu gần thực tế

Nếu cần kiểm tra khối lượng, phân bố hoặc cấu trúc dữ liệu giống production, có thể dùng dữ liệu tổng hợp theo thống kê hoặc dữ liệu đã được ẩn danh đúng cách. Cần đánh giá khả năng tái nhận diện và tuân thủ chính sách dữ liệu trước khi sử dụng.

Không nên coi việc thay tên là ẩn danh đầy đủ nếu các trường khác vẫn có thể xác định một cá nhân. Cũng không nên đưa dữ liệu nhạy cảm vào log, screenshot, báo cáo hoặc artifact CI.

## 11. Vòng đời dữ liệu kiểm thử

Dữ liệu kiểm thử cần có quy trình từ tạo đến dọn dẹp:

1. **Thiết kế:** xác định thực thể, quan hệ, trạng thái và ràng buộc cần kiểm tra.
2. **Tạo:** dùng factory, builder, seed hoặc fixture có phiên bản.
3. **Gán phạm vi:** đặt namespace, tenant hoặc mã lần chạy để cô lập.
4. **Xác minh:** kiểm tra fixture hợp lệ trước khi chạy test chính.
5. **Sử dụng:** chỉ cho phép test sở hữu hoặc nhóm test được chỉ định thao tác.
6. **Thu thập bằng chứng:** lưu mã tham chiếu, trạng thái và log cần thiết.
7. **Dọn dẹp:** xóa hoặc reset đúng tài nguyên do test tạo.
8. **Rà soát:** kiểm tra dữ liệu tồn dư, fixture lỗi thời và thay đổi schema.

### 11.1. Tái lập và độc lập

Một test không nên phụ thuộc vào dữ liệu được tạo bởi một test khác. Mỗi test cần tạo tenant, user, membership và tài nguyên cần thiết hoặc dùng fixture dùng chung chỉ đọc, được quản lý rõ ràng.

Nếu nhiều test chạy song song, namespace nên bao gồm mã lần chạy hoặc worker. Cleanup phải chỉ xóa namespace của test hiện tại. Tránh lệnh xóa rộng theo tenant dùng chung vì có thể làm hỏng test khác đang chạy.

### 11.2. Seed dữ liệu có phiên bản

Seed hoặc factory có thể thay đổi khi schema và quy tắc nghiệp vụ thay đổi. Cần quản lý phiên bản fixture, bảo đảm dữ liệu seed tương thích với schema đang kiểm thử và có cách cập nhật có kiểm soát.

Không nên để một file seed khổng lồ chứa nhiều thực thể và trạng thái không liên quan. Chia fixture theo mục tiêu như tenant-isolation, role-permission, membership-lifecycle hoặc relationship-integrity để dễ hiểu và bảo trì.

## 12. Ví dụ bộ dữ liệu cho một hệ thống SaaS

Giả sử hệ thống SaaS phục vụ ba tổ chức Alpha, Beta và Gamma. Mỗi tổ chức có người dùng và dữ liệu khách hàng riêng. Một số người dùng tham gia nhiều tenant.

### 12.1. Dữ liệu nền

| Thực thể | Định danh | Thuộc tenant | Trạng thái/quan hệ |
|---|---|---|---|
| Tenant | T-ALPHA | — | Active |
| Tenant | T-BETA | — | Active |
| Tenant | T-GAMMA | — | Suspended |
| User | U-ALICE | — | Account Active |
| User | U-AN | — | Account Active |
| User | U-BAO | — | Account Active |
| Membership | M-1 | T-ALPHA | Alice, Admin, Active |
| Membership | M-2 | T-BETA | Alice, Viewer, Active |
| Membership | M-3 | T-ALPHA | An, Staff, Active |
| Membership | M-4 | T-BETA | Bảo, Manager, Active |
| Membership | M-5 | T-GAMMA | An, Staff, Suspended |

Alice có hai membership và hai vai trò khác nhau. Điều này cho phép kiểm tra việc chọn tenant hiện hành và việc quyền không bị rò từ Alpha sang Beta. An có membership bị đình chỉ ở Gamma nhưng vẫn hoạt động tại Alpha.

### 12.2. Các ca kiểm thử đại diện

| Ca kiểm thử | Điều kiện | Kết quả mong đợi |
|---|---|---|
| Tạo tài nguyên trong tenant hiện hành | Alice chọn Alpha và tạo khách hàng mới. | Tài nguyên thuộc Alpha. |
| Chuyển tenant | Alice chuyển từ Alpha sang Beta. | Quyền được tính lại theo membership Beta là Viewer. |
| Truy cập chéo tenant | Alice ở Beta yêu cầu ID tài nguyên thuộc Alpha. | Không truy xuất được dữ liệu Alpha. |
| Membership bị đình chỉ | An chọn Gamma. | Bị từ chối dù tài khoản toàn cục còn Active. |
| Vai trò Viewer ghi dữ liệu | Alice ở Beta thử sửa hồ sơ. | Bị từ chối theo ma trận quyền. |
| Gán vai trò trùng | Gán Manager hai lần cho cùng membership. | Không tạo quan hệ trùng; xử lý theo hợp đồng. |
| Quan hệ cha-con sai tenant | Tạo order Beta nhưng gắn customer Alpha. | Bị từ chối hoặc vi phạm ràng buộc. |
| Xóa membership | Gỡ Alice khỏi Alpha. | Quyền Alpha bị thu hồi; membership Beta vẫn còn. |
| Tài khoản bị vô hiệu hóa | Disable Alice. | Không thể đăng nhập; các membership không cấp quyền truy cập qua tài khoản bị vô hiệu hóa. |

### 12.3. Kiểm tra bất biến dữ liệu

Ngoài từng ca, nhóm có thể xác minh các bất biến:

- Mọi membership tham chiếu đến một user và tenant tồn tại.
- Không có hai membership active trùng user-tenant nếu chính sách yêu cầu duy nhất.
- Mọi role assignment thuộc một membership hợp lệ.
- Mọi resource có tenant owner rõ ràng.
- Quan hệ giữa resource và thực thể cha không vượt tenant nếu quy tắc yêu cầu cùng tenant.
- Người dùng không có membership active không thể truy cập tenant.
- Thay đổi membership ở tenant này không làm thay đổi quyền tại tenant khác.
- Xóa hoặc vô hiệu hóa không phá hủy lịch sử cần lưu.

## 13. Đo lường chất lượng dữ liệu kiểm thử

Không chỉ đo số lượng tài khoản hoặc bản ghi. Cần đánh giá bộ dữ liệu có bao phủ các quan hệ và rủi ro cần thiết hay không.

| Chỉ số | Ý nghĩa | Cách sử dụng |
|---|---|---|
| Bao phủ trạng thái tài khoản | Các trạng thái account quan trọng đã có dữ liệu chưa? | Phát hiện thiếu trường hợp active, locked, disabled hoặc pending. |
| Bao phủ membership | Có dữ liệu cho các trạng thái invited, active, suspended, removed không? | Kiểm tra vòng đời thành viên tenant. |
| Bao phủ vai trò/quyền | Các vai trò và hành động quan trọng có cặp cho phép/từ chối chưa? | Đánh giá ma trận phân quyền. |
| Bao phủ tenant | Có ít nhất hai tenant độc lập và dữ liệu riêng không? | Bảo vệ tenant isolation. |
| Bao phủ quan hệ | Các quan hệ 1:1, 1:N, N:M và trạng thái quan hệ quan trọng đã được kiểm tra chưa? | Phát hiện lỗi liên kết và dữ liệu mồ côi. |
| Tính nhất quán | Fixture có tuân thủ khóa ngoại, tenant và bất biến nghiệp vụ không? | Tránh test thất bại do dữ liệu tự tạo sai. |
| Khả năng tái lập | Cùng fixture/seed có tạo được cùng trạng thái không? | Hỗ trợ điều tra và chạy lại. |
| Dữ liệu tồn dư | Có tài nguyên bị bỏ lại sau test không? | Ngăn xung đột và tăng chi phí môi trường. |

Một bộ dữ liệu có nhiều bản ghi nhưng chỉ một tenant hoặc một vai trò không tạo được bằng chứng về cô lập và phân quyền. Hãy đo theo trạng thái, quan hệ, hành động và ranh giới cần bảo vệ.

## 14. Những sai lầm thường gặp

- **Dùng một tenant duy nhất:** không thể kiểm tra truy cập chéo tenant.
- **Gán vai trò toàn cục cho người dùng:** bỏ qua việc một người có quyền khác nhau ở từng tenant.
- **Chỉ kiểm tra vai trò, không kiểm tra tài nguyên:** bỏ sót quyền theo sở hữu, nhóm hoặc trạng thái nghiệp vụ.
- **Dùng tài khoản quản trị cho mọi test:** che giấu lỗi phân quyền và tạo quyền quá rộng.
- **Tạo quan hệ không nhất quán:** fixture có khóa ngoại hoặc tenant sai nhưng test vẫn cố chạy.
- **Chỉ kiểm tra API danh sách:** bỏ sót endpoint chi tiết, export, cache, job và event.
- **Không kiểm tra trạng thái membership:** tài khoản Active có thể bị hiểu nhầm là được truy cập mọi tenant.
- **Dùng dữ liệu production không kiểm soát:** tạo rủi ro quyền riêng tư và bảo mật.
- **Dùng ID cố định trong test song song:** gây va chạm và xung đột dữ liệu.
- **Cleanup quá rộng:** xóa dữ liệu do test khác hoặc nhóm khác tạo.
- **Không kiểm tra thu hồi quyền:** người dùng tiếp tục truy cập bằng phiên hoặc token cũ.
- **Chỉ đếm số lượng fixture:** bỏ qua chất lượng và tính đại diện của quan hệ.

## 15. Checklist trước khi chốt bộ dữ liệu kiểm thử

- [ ] Đã xác định các thực thể, khóa và quan hệ trong phạm vi kiểm thử.
- [ ] Đã phân biệt user, account, tenant, membership, role và permission.
- [ ] Có ít nhất hai tenant độc lập cho kiểm tra cô lập dữ liệu.
- [ ] Có người dùng thuộc nhiều tenant với vai trò khác nhau nếu sản phẩm hỗ trợ.
- [ ] Có trạng thái account và membership bình thường, biên và ngoại lệ.
- [ ] Ma trận quyền bao phủ cả thao tác được phép và bị từ chối.
- [ ] Có dữ liệu kiểm tra truy cập chéo tenant ở nhiều loại endpoint.
- [ ] Quan hệ cha-con, một-một, một-nhiều và nhiều-nhiều được tạo hợp lệ.
- [ ] Có trường hợp quan hệ trùng, thiếu, hết hạn, thu hồi hoặc bị xóa.
- [ ] Fixture tuân thủ khóa ngoại, ràng buộc duy nhất và bất biến nghiệp vụ.
- [ ] Dữ liệu tổng hợp không chứa thông tin nhạy cảm không cần thiết.
- [ ] ID, namespace và cleanup an toàn khi chạy song song.
- [ ] Có thể tái tạo fixture bằng seed hoặc factory có kiểm soát.
- [ ] Test kiểm tra cả quyền, dữ liệu trả về và tác dụng phụ.
- [ ] Dữ liệu và fixture được rà soát khi schema hoặc chính sách quyền thay đổi.

## Kết luận

Quản lý dữ liệu kiểm thử cho tài khoản, vai trò, tenant và quan hệ thực thể cần phản ánh đúng ranh giới danh tính, quyền và sở hữu dữ liệu. Hãy tạo nhiều tenant độc lập, mô hình hóa membership và vai trò theo phạm vi, kiểm tra cả hành động được phép lẫn bị từ chối, đồng thời bảo vệ tính toàn vẹn của quan hệ. Fixture cần an toàn, nhất quán, có thể tái lập và độc lập khi chạy song song. Một bộ dữ liệu được thiết kế có chủ đích giúp phát hiện sớm lỗi phân quyền, rò rỉ chéo tenant, quan hệ sai và các vấn đề vòng đời tài khoản trước khi ảnh hưởng đến người dùng thật.
