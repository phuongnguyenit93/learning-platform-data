# Identity attribute minimization

## 1. Tối thiểu hóa thuộc tính danh tính là gì?

**Identity attribute minimization** là việc giới hạn các thuộc tính danh tính được thu thập, xử lý, truyền đi và lưu giữ ở mức cần thiết cho một mục đích cụ thể. Trong hệ thống IAM, câu hỏi không chỉ là “ứng dụng có lấy được dữ liệu này không?”, mà còn là “ứng dụng cần biết dữ liệu này để thực hiện chức năng nào, trong bao lâu và với độ chi tiết nào?”.

Một tài khoản có thể gắn với họ tên, email, số điện thoại, ngày sinh, đơn vị công tác, chức danh, nhóm quyền, thiết bị và nhiều thuộc tính khác. Việc kho danh tính có các dữ liệu đó không có nghĩa mọi ứng dụng đăng nhập qua SSO đều cần nhận toàn bộ hồ sơ.

Ví dụ, cổng học nội bộ cần nhận biết cùng một người qua nhiều lần đăng nhập để lưu tiến độ. Nó có thể cần một định danh ổn định dành cho ứng dụng, nhưng không nhất thiết cần ngày sinh, địa chỉ nhà hoặc số điện thoại. Nếu chức năng thông báo thực sự dùng email, email cần được cấp cho đúng chức năng đó thay vì tự động đưa vào mọi token và log.

Tối thiểu hóa giúp giảm dữ liệu bị lộ khi token, ứng dụng hoặc log gặp sự cố; giảm khả năng liên kết hoạt động giữa các hệ thống; đồng thời giảm số bản sao phải cập nhật, thu hồi và xử lý khi vòng đời tài khoản thay đổi.

Đây không phải việc xóa mọi thuộc tính hay làm hệ thống không còn đủ thông tin để xác thực, phân quyền và kiểm toán. Mục tiêu là **đủ thông tin cho quyết định được phép thực hiện, với phạm vi và thời gian phù hợp**.

## 2. Những loại dữ liệu cần đưa vào phạm vi xem xét

Trong IAM, thuộc tính danh tính không chỉ là thông tin hồ sơ do người dùng nhập.

| Nhóm | Ví dụ | Câu hỏi cần đặt ra |
| --- | --- | --- |
| Định danh | Subject ID, mã nhân viên, email | Bên nhận cần nhận biết ổn định hay cần biết danh tính ngoài đời? |
| Hồ sơ | Họ tên, ngày sinh, địa chỉ, ảnh | Chức năng nào dùng từng trường và cần độ chi tiết đến đâu? |
| Thuộc tính tổ chức | Phòng ban, đơn vị, chức danh, người quản lý | Cần giá trị gốc hay chỉ cần kết quả đủ điều kiện? |
| Thuộc tính quyền | Role, group, entitlement | Cần quyền của ứng dụng này hay toàn bộ quyền trong tổ chức? |
| Ngữ cảnh xác thực | Thời điểm xác thực, mức bảo đảm, phương thức đã dùng | Quyết định truy cập có yêu cầu thông tin này không? |
| Ngữ cảnh truy cập | Thiết bị, vị trí, tín hiệu rủi ro | Quyết định cần tín hiệu chi tiết hay chỉ trạng thái đã đánh giá? |
| Dữ liệu suy ra | Đủ tuổi, thuộc nhóm đủ điều kiện, trạng thái nhân sự | Bản thân kết quả suy ra có tiết lộ thông tin nhạy cảm không? |

Credential như mật khẩu, khóa riêng, secret của workload và vật liệu khôi phục cần cơ chế bảo vệ riêng; không coi chúng là trường hồ sơ thông thường để phân phối cho ứng dụng. Một ứng dụng dựa vào IdP xác thực thường không cần nhận mật khẩu hoặc mã MFA mà IdP đã dùng.

Ngay cả một giá trị boolean cũng có thể nhạy cảm. `eligible_for_benefit=true` có thể tiết lộ việc thuộc một nhóm cá nhân đặc thù. Do đó “ít byte hơn” chưa chắc đã giảm đủ rủi ro; cần xét ý nghĩa, bên nhận và khả năng kết hợp với dữ liệu khác.

## 3. Tối thiểu hóa ở nhiều chiều

### 3.1. Số thuộc tính

Không thu thập hoặc phát hành một trường chỉ vì biểu mẫu, SDK hay schema hỗ trợ nó. Nếu chức năng ghi nhận tiến độ học chỉ cần subject, thêm ngày sinh không tạo ra giá trị cho chức năng đó.

### 3.2. Độ chi tiết

Một quyết định có thể cần biết “đủ 18 tuổi” thay vì ngày, tháng, năm sinh; hoặc “thiết bị đáp ứng chính sách” thay vì toàn bộ kết quả kiểm kê thiết bị. Nếu bên có thẩm quyền đã đánh giá điều kiện, bên sử dụng có thể chỉ cần kết quả được bảo vệ cùng thông tin nguồn và hiệu lực cần thiết.

Việc chuyển sang kết quả suy ra không tự loại bỏ rủi ro. Bên phát hành vẫn có thể cần xử lý dữ liệu gốc, và bên nhận phải hiểu phạm vi, độ tin cậy, thời điểm đánh giá của kết quả. Không tạo một boolean thiếu nguồn gốc rồi coi nó là bằng chứng xác thực.

### 3.3. Phạm vi người nhận

Một thuộc tính cần cho hệ thống nhân sự không tự động cần cho cổng học, công cụ chấm công hoặc nhà cung cấp phân tích. Quyền chia sẻ phải gắn với ứng dụng, API và mục đích cụ thể.

### 3.4. Thời gian tồn tại

Dữ liệu cần ở thời điểm ra quyết định chưa chắc cần lưu vào hồ sơ, session hoặc kho phân tích lâu dài. Có thể đọc từ nguồn có thẩm quyền khi cần, giữ một cache có giới hạn hoặc lưu bằng chứng tối thiểu về quyết định thay vì sao chép toàn bộ thuộc tính.

### 3.5. Khả năng liên kết

Một ID toàn cục được gửi cho mọi ứng dụng giúp chúng nối hoạt động của cùng người dùng. Dùng định danh theo phạm vi ứng dụng hoặc miền liên kết phù hợp có thể giảm sự liên kết không cần thiết. Tuy nhiên, email, số điện thoại, cùng một ảnh đại diện hoặc các thuộc tính hiếm vẫn có thể tạo lại liên kết dù ID đã khác nhau.

### 3.6. Khả năng truy cập

Chỉ một thành phần quyết định quyền cần đọc thuộc tính không có nghĩa mọi controller, dịch vụ hỗ trợ và nhân viên vận hành đều cần truy cập. Giới hạn dữ liệu trong nội bộ ứng dụng cũng là một phần của tối thiểu hóa.

## 4. Bắt đầu từ mục đích và quyết định cần thực hiện

### 4.1. Viết mục đích đủ cụ thể

“Phục vụ trải nghiệm người dùng” quá rộng để quyết định cần giữ trường nào. Những mục đích rõ hơn gồm:

- Nhận biết tài khoản qua các lần đăng nhập để lưu tiến độ học.
- Kiểm tra quyền truy cập khóa học thuộc tổ chức hiện tại.
- Gửi thông báo mà người dùng hoặc quy trình nghiệp vụ đã yêu cầu.
- Ghi bằng chứng cho thao tác quản trị quyền.

Với mỗi mục đích, xác định quyết định hoặc kết quả cần tạo ra. Nếu không có thành phần nào sử dụng một thuộc tính để thực hiện mục đích đã xác định, đó là ứng viên để loại bỏ khỏi hợp đồng dữ liệu.

### 4.2. Lập bảng thuộc tính theo từng bên sử dụng

Ví dụ một hệ thống học nội bộ:

| Mục đích | Dữ liệu cần xem xét | Phương án tối thiểu | Dữ liệu không tự động cần |
| --- | --- | --- | --- |
| Đăng nhập và gắn tiến độ | Định danh tài khoản | Subject ổn định trong phạm vi ứng dụng cùng nguồn phát hành đáng tin cậy | Ngày sinh, số điện thoại, mã nhân viên toàn cục |
| Hiển thị lời chào | Tên hiển thị | Tên hiển thị nếu thực sự cần; có thể cho phép bí danh | Hồ sơ nhân sự đầy đủ |
| Xác định khóa học được phép | Quan hệ với tổ chức và entitlement | Tenant context đã xác minh và quyền liên quan đến khóa học | Toàn bộ group của doanh nghiệp |
| Gửi thông báo | Địa chỉ đích | Email ở dịch vụ thông báo khi chức năng yêu cầu | Email trong mọi access token hoặc metric |
| Kiểm toán thay đổi quyền | Người thực hiện, mục tiêu và thay đổi | Tham chiếu danh tính, hành động, kết quả, thời gian, bằng chứng cần thiết | Bản sao nguyên token và toàn bộ hồ sơ |

Bảng không có nghĩa mọi triển khai bắt buộc dùng các trường này. Cần kiểm tra nhu cầu thực của từng chức năng và ràng buộc bảo vệ tài nguyên. Chẳng hạn, định danh tenant có thể cần thiết để ngăn truy cập chéo tổ chức; không được xóa nó chỉ vì muốn token ngắn hơn.

### 4.3. Ghi cả nguồn và vòng đời

Một thuộc tính được giữ lại nên có người chịu trách nhiệm, nguồn có thẩm quyền, bên nhận, mục đích, mức chi tiết, quy tắc cập nhật và thời gian lưu. Phải phân biệt “cần biết tại thời điểm kiểm tra” với “cần lưu lại để sử dụng sau”.

Với thuộc tính dùng để phân quyền, ghi thêm mức độ mới cần có và cách xử lý khi thiếu hoặc không xác minh được. Đây là dữ liệu đầu vào của kiểm soát truy cập, không chỉ là thông tin trang trí trên hồ sơ.

## 5. Chọn định danh vừa đủ để nhận biết người dùng

### 5.1. Không mặc định email là khóa tài khoản

Email có thể thay đổi, có thể được tái cấp và thường có ý nghĩa nhận dạng bên ngoài ứng dụng. Dùng email làm khóa chính còn khiến nhiều hệ thống phải đồng bộ nó vào log, quan hệ dữ liệu và token.

Một định danh nội bộ hoặc subject do IdP cung cấp có thể phù hợp hơn cho liên kết tài khoản, nhưng phải hiểu namespace và tính ổn định mà nhà cung cấp cam kết. Trong OIDC, ứng dụng thường cần xử lý subject trong ngữ cảnh issuer đã được xác minh; không mặc định cùng một chuỗi `sub` từ hai issuer khác nhau là cùng người.

Trong hệ thống đa tenant, cần xác minh và giữ ranh giới tenant phù hợp với mô hình danh tính. Không suy ra tenant từ một tham số request chưa được ràng buộc với danh tính hoặc quyền truy cập hiện tại.

### 5.2. Định danh theo phạm vi ứng dụng

Có thể cấp cho mỗi ứng dụng một tham chiếu khác nhau đến cùng một tài khoản tại kho danh tính. Mô hình subject theo cặp hoặc theo phạm vi được hỗ trợ bởi hệ thống danh tính giúp giảm việc dùng một ID để nối dữ liệu giữa các bên nhận không cần chia sẻ danh tính.

```text
Tài khoản trong kho danh tính
  ├─ cổng học:       subject-learning-A17
  ├─ công cụ hỗ trợ: subject-support-K92
  └─ ứng dụng khác:  subject-app-M35
```

Đây là minh họa phạm vi định danh, không phải thuật toán sinh ID. Không tự chế một phép băm từ email rồi cho rằng đã tạo được định danh an toàn, ổn định và không thể liên kết. Cách sinh, ánh xạ, quản lý khóa nếu có, thay đổi cấu hình và khôi phục tài khoản phải theo thiết kế được kiểm soát.

Subject khác nhau cũng không bảo đảm các ứng dụng hoàn toàn không thể nhận ra cùng người dùng nếu vẫn nhận chung email hoặc thuộc tính đặc trưng. Tối thiểu hóa định danh phải đi cùng tối thiểu hóa các thuộc tính còn lại.

### 5.3. Phân biệt giả danh với ẩn danh

Thay email bằng một ID giả danh vẫn có thể cho phép nối lịch sử hoạt động hoặc truy ngược qua bảng ánh xạ. Băm một giá trị có thể đoán được cũng có thể bị đối chiếu bằng cách thử các ứng viên.

Do đó không tự gọi dữ liệu là ẩn danh chỉ vì không còn họ tên. Cần xét khả năng liên kết, nguồn dữ liệu phụ và ai có thể truy cập ánh xạ. Bảng ánh xạ, nếu cần, nên được bảo vệ và phân quyền riêng thay vì sao chép vào mọi hệ thống.

## 6. Áp dụng vào token, claims và liên kết danh tính

### 6.1. Token không phải bản sao hồ sơ

Token thường đi qua trình duyệt, gateway, API và các thành phần xử lý lỗi. Mỗi claim thừa có thể làm tăng dữ liệu hiện diện ở nhiều nơi. Một JWT được ký không vì thế mà có payload bí mật; các bên có được chuỗi token thường có thể đọc phần payload nếu token không được mã hóa.

Trước khi đưa thuộc tính vào token, cần xác định bên nhận, mục đích, kiểu dữ liệu, thời gian hiệu lực và nơi dữ liệu có thể bị lưu lại. Không nhét toàn bộ group hoặc hồ sơ nhân sự vào mọi token để các ứng dụng tự chọn những gì muốn dùng.

Ví dụ một payload quá rộng cho cổng học:

```json
{
  "sub": "global-employee-1842",
  "email": "learner@example.org",
  "phone_number": "+84000000000",
  "birthdate": "1995-01-01",
  "home_address": "dia-chi-minh-hoa",
  "employee_number": "EMP-1842",
  "manager_email": "manager@example.org",
  "all_enterprise_groups": ["group-a", "group-b", "group-c"],
  "learning_role": "learner"
}
```

Đây chỉ là ví dụ các trường có thể bị phát hành thừa, không phải token hoàn chỉnh hoặc hợp lệ để sử dụng. Nếu mục đích là đăng nhập và nhận biết tài khoản, hợp đồng danh tính có thể chỉ cần subject cùng các claims giao thức cần thiết. Quyền học khóa nào có thể do dịch vụ nghiệp vụ tra cứu riêng.

Một payload danh tính minh họa gọn hơn:

```json
{
  "iss": "https://id.example.org",
  "sub": "subject-learning-A17",
  "aud": "learning-portal",
  "iat": 1760000000,
  "exp": 1760000300
}
```

Payload này minh họa ý tưởng thu hẹp dữ liệu, không phải mẫu triển khai OIDC hoàn chỉnh; các claims và kiểm tra cần có còn phụ thuộc flow và thư viện được sử dụng. Không dùng ID token thay cho access token của API hoặc bỏ các ràng buộc bảo mật giao thức chỉ để giảm số trường.

### 6.2. Cấp thuộc tính theo đúng bên nhận

Các cơ chế như scope, cấu hình claim release, endpoint thông tin người dùng và audience có thể hỗ trợ giới hạn dữ liệu được phát hành. Tuy nhiên, yêu cầu một scope hẹp không bảo đảm mọi sản phẩm tự động loại mọi claim thừa. Cần kiểm tra dữ liệu thực sự được phát hành và được trả về bởi từng endpoint.

IdP nên có hợp đồng thuộc tính theo từng ứng dụng hoặc nhóm ứng dụng có cùng nhu cầu được xác định. Ứng dụng cũng cần giới hạn các trường nhập vào model nội bộ và dữ liệu trả ra ngoài. Không chỉ kiểm soát ở một phía rồi tin rằng các tầng sau sẽ tự bảo toàn phạm vi.

Ứng dụng được quyền đọc thuộc tính không có nghĩa mọi API downstream cũng được quyền nhận nó. Khi gọi một API khác, dùng credential và dữ liệu dành cho bên nhận đó; không chuyển nguyên token hoặc toàn bộ principal xuyên qua chuỗi dịch vụ cho tiện.

### 6.3. Chỉ lấy thuộc tính bổ sung khi cần

Nếu chức năng thông báo mới cần email, có thể lấy email qua một đường truy cập được phân quyền ở thời điểm sử dụng hoặc giao dịch vụ thông báo xử lý địa chỉ đích. Cách này giảm số nơi luôn mang email, nhưng phải xét thêm độ sẵn sàng, độ trễ, cache và quyền truy cập của endpoint thuộc tính.

Không chuyển từ “mọi token đều chứa hồ sơ” sang “mọi service đều có API đọc toàn bộ hồ sơ”. Cả hai đều mở rộng phạm vi tiếp cận dữ liệu. Endpoint bổ sung cần giới hạn theo người gọi, người được truy vấn, trường dữ liệu và mục đích sử dụng.

## 7. Tối thiểu hóa mà vẫn giữ phân quyền đúng

### 7.1. RBAC: quyền của ứng dụng thay vì toàn bộ cấu trúc tổ chức

Một ứng dụng chỉ cần biết người dùng có quyền đọc tài liệu hoặc quản trị khóa học, không nhất thiết cần toàn bộ group doanh nghiệp. Có thể ánh xạ từ nhóm ở nguồn sang role/permission dành cho ứng dụng tại thành phần có thẩm quyền.

Quá trình ánh xạ phải giữ đúng ngữ nghĩa và phạm vi. Không biến mọi loại quản trị thành một role `admin` toàn cục chỉ để làm dữ liệu gọn hơn; như vậy làm mất ranh giới quyền và có thể gây cấp quyền quá mức.

### 7.2. ABAC: thuộc tính tối thiểu cho một quyết định cụ thể

Một policy cho phép sửa hồ sơ trong cùng tenant có thể cần subject, tenant context, tenant của tài nguyên và quyền thao tác. Một policy khác cần biết người dùng có thuộc nhóm đủ điều kiện hay không. Hai quyết định không tự động cần cùng một hồ sơ đầu vào.

Có thể để điểm quyết định chính sách đọc thuộc tính chi tiết, rồi trả `allow`/`deny` cùng nghĩa vụ thực thi cần thiết cho điểm thực thi. Khi đó ứng dụng có thể không cần nhận dữ liệu gốc. Tuy nhiên, kết quả phải gắn với đúng subject, hành động, tài nguyên, ngữ cảnh và thời hạn; không tái sử dụng một `allow` chung cho mọi thao tác sau này.

```text
Nguồn thuộc tính có thẩm quyền
  → thành phần quyết định đọc các trường cần cho policy
  → quyết định được ràng buộc với yêu cầu cụ thể
  → thành phần thực thi nhận kết quả và nghĩa vụ cần thiết
```

Đây là phân tách trách nhiệm, không phải bảo đảm tự động rằng dữ liệu không bị lộ. Điểm quyết định, cache và log của nó vẫn cần được xem xét trong phạm vi tối thiểu hóa.

### 7.3. Không đánh đổi nguồn gốc và độ mới

Một claim ít trường nhưng do client tự khai không thể thay thế thuộc tính đáng tin cậy từ nguồn có thẩm quyền. Với các dữ liệu như tình trạng nhân sự, tenant membership hoặc entitlement, phải biết nguồn phát hành và mức độ mới phù hợp với rủi ro.

Nếu policy cần một thuộc tính nhưng nó bị thiếu, hết hiệu lực hoặc không xác minh được, phải xử lý theo hợp đồng đã thiết kế. Không mặc định “thiếu nghĩa là được phép”, không suy ra giá trị từ email hoặc tên hiển thị và không lấy một giá trị cũ không giới hạn từ session để tránh lỗi.

Thời hạn token ngắn có thể giảm thời gian mang dữ liệu cũ nhưng không tự bảo đảm quyền được thu hồi ngay. Cần xét session, cache, API thuộc tính và cơ chế cập nhật/thu hồi trong toàn bộ đường ra quyết định.

## 8. Provisioning và vòng đời dữ liệu

### 8.1. Cấp phát chỉ những trường hệ thống đích cần

Connector provisioning không nên đồng bộ mọi trường chỉ vì schema đích có chỗ chứa. Với từng ứng dụng, xác định trường dùng để tạo/liên kết tài khoản, trường dùng cho quyền, trường phục vụ liên hệ và trường tùy chọn.

Nếu đích cần một định danh ngoài để đối chiếu tài khoản, có thể dùng một định danh tích hợp phù hợp thay vì số giấy tờ hoặc mã nhân sự toàn cục. Mapping phải đủ ổn định để cập nhật và deprovision đúng người, tránh tạo trùng hoặc liên kết nhầm khi thuộc tính hiển thị thay đổi.

### 8.2. Theo dõi nơi tạo bản sao

Một thuộc tính có thể xuất hiện trong kho danh tính, ứng dụng, session, cache, hàng đợi provisioning, dead-letter queue, ticket hỗ trợ, bản xuất dữ liệu và bản sao lưu. Chỉ bỏ nó khỏi giao diện không làm các bản sao đó biến mất.

Khi ngừng dùng một trường, cần kiểm tra nguồn phát hành, consumer, schema lưu trữ và các đường xuất dữ liệu. Việc xóa hoặc ngừng giữ bản sao phải theo vòng đời và ràng buộc lưu trữ của hệ thống; không xóa bằng chứng hoặc dữ liệu đang có nhu cầu giữ hợp lệ một cách tùy tiện.

### 8.3. Tài khoản nghỉ hoạt động

Khóa hoặc xóa quyền đăng nhập không tự làm dữ liệu hồ sơ biến mất ở ứng dụng downstream. Cần phân biệt thu hồi truy cập, vô hiệu hóa tài khoản, xóa thuộc tính không còn cần và duy trì tham chiếu kiểm toán cần thiết.

Có thể giữ tham chiếu tối thiểu để giải thích một thao tác quá khứ trong khi hạn chế hồ sơ chi tiết, nếu phù hợp với nhu cầu lưu giữ đã xác định. Không sử dụng cùng một cờ “disabled” để giả định đã hoàn tất mọi công việc vòng đời dữ liệu.

## 9. Session, log, audit và phân tích

### 9.1. Session và model nội bộ

Không serialize toàn bộ đối tượng principal hoặc phản hồi IdP vào session chỉ vì thuận tiện. Session cần dữ liệu phục vụ chức năng và quyết định hiện tại, với thời gian tồn tại phù hợp. Một bản sao lớn và cũ của hồ sơ trong session có thể vừa tăng phạm vi lộ vừa làm policy dùng thông tin lỗi thời.

Tách model bảo mật khỏi DTO trả cho giao diện. Backend có thể cần tenant context hoặc thông tin xác thực để ra quyết định, nhưng giao diện không nhất thiết cần nhận tất cả các trường đó.

### 9.2. Log phục vụ vận hành

Ghi sự kiện có cấu trúc với các trường được cho phép thay vì log nguyên request, token, principal hoặc profile. Lỗi xác minh token không phải lý do để in token ra log; lỗi claim mapping cũng không yêu cầu dump toàn bộ hồ sơ.

Một sự kiện audit minh họa:

```json
{
  "event_type": "role_assignment_changed",
  "actor_ref": "actor-internal-7",
  "target_ref": "subject-internal-42",
  "action": "grant_learning_editor",
  "resource_scope": "course-scope-12",
  "result": "success",
  "timestamp": "2026-01-15T08:30:00Z",
  "request_ref": "request-example-52"
}
```

Đây là ví dụ trường tối thiểu cho một tình huống, không phải schema audit đủ cho mọi nghiệp vụ. Có trường hợp cần giá trị trước/sau, phiên bản policy, người phê duyệt hoặc bằng chứng xác thực bổ sung. Hãy giữ bằng chứng cần để giải thích thao tác, nhưng không sao chép token, email, số điện thoại và toàn bộ hồ sơ khi các dữ liệu đó không phục vụ mục đích kiểm toán.

`actor_ref`, `target_ref`, phạm vi tài nguyên và lịch sử hành động vẫn có thể nhận diện hoặc liên kết hoạt động của một người. Cần phân quyền, giới hạn truy vấn, kiểm soát xuất dữ liệu và thời gian lưu; dùng tham chiếu không biến audit thành dữ liệu vô danh.

### 9.3. Metric và phân tích

Metric tổng hợp thường cần nhóm dịch vụ, hành động và kết quả, không cần email hoặc user ID làm nhãn. Định danh động tạo nhiều chuỗi thời gian và làm dữ liệu cá nhân lan sang hạ tầng giám sát.

Với phân tích hành vi, cân nhắc dữ liệu tổng hợp, mức chi tiết thời gian và nhu cầu giữ lịch sử từng người. Tách mục đích vận hành IAM khỏi phân tích sản phẩm; việc một hệ thống đã có dữ liệu đăng nhập không tự làm mọi cách sử dụng lại đều cần thiết.

## 10. Thực thi bằng hợp đồng dữ liệu và danh sách cho phép

### 10.1. Cho phép rõ từng trường

Một hợp đồng thuộc tính nên nêu ứng dụng/bên nhận, mục đích, thuộc tính bắt buộc, thuộc tính tùy chọn, nguồn, độ mới và thời gian lưu. Danh sách cho phép giúp các thuộc tính mới xuất hiện ở IdP không tự động chảy sang mọi ứng dụng.

Ví dụ hợp đồng minh họa cho một chức năng ghi nhận tiến độ:

```yaml
purpose: track_learning_progress
consumer: learning-progress-service
required:
  - trusted_subject_reference
  - verified_tenant_context
optional: []
profile_storage: none
```

Đây không phải cấu hình chuẩn cho một sản phẩm IAM cụ thể. Các tên trường thể hiện ý định thiết kế; cách ánh xạ từ claims đã xác minh cần theo kiến trúc thực tế. Nếu chức năng cần dữ liệu khác để thực hiện đúng kiểm soát quyền, phải bổ sung có lý do thay vì áp dụng máy móc danh sách này.

### 10.2. Xác minh trước, sau đó thu hẹp dữ liệu cho bên sử dụng

Một trình tự hợp lý là:

```text
Nhận dữ liệu danh tính
  → xác minh theo giao thức, nguồn tin cậy và bên nhận
  → tạo security context với ngữ nghĩa đã kiểm tra
  → thực hiện kiểm soát truy cập bằng thuộc tính cần thiết
  → tạo model/DTO riêng theo danh sách trường được phép
  → truyền hoặc lưu đúng dữ liệu chức năng cần
```

Không cắt bỏ các claims cần xác minh trước khi thành phần bảo mật xử lý rồi coi phần còn lại là danh tính đáng tin. Không sửa payload của token đã ký để “xóa trường thừa” và chuyển nó như token gốc; cần thay đổi cấu hình phát hành, cấp token phù hợp hoặc tạo model nội bộ không phải credential thay thế.

### 10.3. Chặn rò rỉ qua đường phụ

Ngay cả khi API chính có DTO tối thiểu, profile vẫn có thể bị lộ qua endpoint debug, error handler, tracing, cache hoặc đối tượng được serialize tự động. Cần kiểm soát các điểm xuất dữ liệu này theo cùng hợp đồng.

Cho phép thuộc tính mới nên là một thay đổi có chủ đích: ghi mục đích, cập nhật hợp đồng, đánh giá consumer và xác minh payload thực tế. Không dùng wildcard như “copy mọi claim” trong một lớp mapping rồi trông chờ tất cả bên nhận tự loại bỏ dữ liệu thừa.

## 11. Tình huống minh họa: thu hẹp hồ sơ trong cổng học

Ban đầu, cổng học nhận từ IdP hồ sơ gồm email, điện thoại, ngày sinh, địa chỉ, mã nhân viên, người quản lý và toàn bộ group. Middleware lưu nguyên profile vào session; error handler còn đưa profile vào log khi xử lý lỗi.

Kiểm kê chức năng cho thấy việc lưu tiến độ chỉ cần nhận biết tài khoản; quyền học cần tenant context và entitlement liên quan; thông báo cần địa chỉ email ở đúng dịch vụ gửi. Những chức năng này không cần ngày sinh, địa chỉ nhà hoặc group của các ứng dụng khác.

Nhóm triển khai thay đổi hợp đồng claim release cho cổng học, dùng subject trong phạm vi phù hợp và giữ những claims giao thức cần thiết. Dịch vụ quyền cung cấp entitlement dành cho khóa học; dịch vụ thông báo truy cập địa chỉ đích theo hợp đồng riêng. Session chỉ giữ các tham chiếu và ngữ cảnh cần thiết, còn DTO giao diện không serialize principal.

Khi chuyển đổi, nhóm vẫn kiểm tra liên kết với tài khoản cũ. Nếu thay subject hoặc cách mapping mà không có kế hoạch, hệ thống có thể tạo tài khoản mới và làm người dùng mất liên kết tiến độ. Migration phải bảo đảm đúng người, tránh gắn nhầm tài khoản theo email trùng hoặc đã được tái cấp.

Nhóm cũng dừng việc log profile và xử lý các bản sao cũ theo chính sách lưu giữ đã xác định. Chỉ sửa token mới sẽ không giải quyết dữ liệu còn trong session cũ, cache hoặc log lịch sử.

Kết quả cần xác nhận là đăng nhập và tiến độ vẫn hoạt động, ranh giới tenant và quyền khóa học vẫn đúng, trong khi mỗi bên nhận chỉ còn dữ liệu phục vụ chức năng của mình. Không đánh giá thành công chỉ bằng việc payload ngắn hơn.

## 12. Những tình huống cần kiểm tra trong thiết kế

| Tình huống | Hành vi cần có |
| --- | --- |
| IdP bổ sung một trường hồ sơ mới | Không tự động xuất hiện trong DTO/token của consumer không được cấp |
| User thay email | Quan hệ tài khoản và tiến độ không bị gắn nhầm chỉ vì đổi địa chỉ liên hệ |
| Token thiếu thuộc tính bắt buộc cho policy | Xử lý theo hợp đồng an toàn; không mặc định cho phép |
| User thuộc tenant khác | Ranh giới truy cập vẫn được kiểm tra dù hồ sơ đã được thu hẹp |
| Một role bị thu hồi | Quyết định mới phản ánh vòng đời quyền theo thiết kế, không dùng bản sao cũ vô thời hạn |
| Lỗi claim mapping hoặc token validation | Log có thông tin chẩn đoán cần thiết, không chứa token hay toàn bộ profile |
| Tài khoản bị vô hiệu hóa | Thu hồi truy cập và xử lý vòng đời thuộc tính được thực hiện như các công việc rõ ràng |
| Consumer xin thêm thuộc tính | Có mục đích, phạm vi, nguồn và thời hạn trước khi mở rộng hợp đồng |

Các tình huống này giúp kiểm tra tính đầy đủ của thiết kế tối thiểu hóa. Chúng không thay thế việc xác minh quyền thực tế hoặc kiểm tra bảo mật giao thức trong hệ thống được triển khai.

## 13. Những cách hiểu dễ dẫn đến sai lầm

- Cho rằng đã mã hóa dữ liệu thì có thể thu thập và giữ bao nhiêu cũng được. Mã hóa bảo vệ dữ liệu hiện có, không chứng minh dữ liệu đó cần thiết.
- Xóa tenant context, audience hoặc thông tin nguồn để token ngắn hơn. Một số dữ liệu là điều kiện bảo vệ danh tính và phân quyền đúng.
- Giữ email toàn cục trong mọi ứng dụng rồi coi subject khác nhau là đủ để ngăn liên kết.
- Chỉ bỏ thuộc tính khỏi giao diện, trong khi session, log, cache và pipeline provisioning vẫn giữ nguyên.
- Dùng phép băm email như bằng chứng dữ liệu đã ẩn danh.
- Thay thuộc tính gốc bằng boolean rồi bỏ qua nguồn gốc, hiệu lực và ý nghĩa nhạy cảm của boolean đó.
- Ánh xạ toàn bộ group doanh nghiệp vào mọi token cho tiện phát triển.
- Lưu toàn bộ token để kiểm toán thay vì thiết kế bản ghi audit có mục đích rõ.
- Coi thời hạn token là thời hạn lưu của mọi bản sao dữ liệu.
- Loại bỏ thuộc tính mà không kiểm tra consumer, khiến policy mặc định sai hoặc liên kết tài khoản bị đứt.

Tối thiểu hóa thuộc tính danh tính là một quyết định thiết kế xuyên suốt từ nguồn danh tính đến token, ứng dụng, kiểm soát quyền và dữ liệu vận hành. Mỗi thuộc tính được giữ lại cần có mục đích, bên nhận và vòng đời rõ ràng; mỗi phần bị loại bỏ cần được thực hiện mà vẫn bảo toàn khả năng xác thực, phân quyền và kiểm toán cần thiết.
