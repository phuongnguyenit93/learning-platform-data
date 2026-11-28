# Phát hiện cloud role mạnh

Trong quản lý truy cập đặc quyền (Privileged Access Management — PAM), discovery không chỉ là tìm tài khoản có tên `admin`. Trên cloud, quyền quản trị có thể được cấp qua role, nhóm, danh tính workload, quan hệ tin cậy liên tài khoản và chính sách đặt trực tiếp trên tài nguyên. Một role không có chữ “administrator” vẫn có thể cho phép đọc bí mật, sửa mã của dịch vụ chạy bằng danh tính mạnh hoặc thay đổi chính sách cấp quyền.

**Cloud role mạnh** trong bài này là role có khả năng gây tác động lớn đến quyền truy cập, dữ liệu, tính sẵn sàng hoặc cơ chế giám sát trong một phạm vi đáng kể. Đây là cách phân loại phục vụ discovery và PAM, không phải một loại role chuẩn chung của mọi nhà cung cấp.

Mục tiêu là xác định role nào cần được quản lý như đặc quyền, ai có thể sử dụng role đó, quyền có thể tác động lên đâu và bằng chứng nào chứng minh kết luận. Kết quả giúp ưu tiên least privilege, JIT/JEA, bảo vệ credential, giám sát phiên và lưu bằng chứng phục vụ kiểm toán, ứng phó sự cố.

## 1. Tên role chỉ là điểm bắt đầu

Một role thường cần được xem qua ba thành phần:

1. **Định nghĩa quyền:** những hành động nào được cho phép hoặc bị loại trừ.
2. **Quan hệ cấp quyền và phạm vi:** ai nhận role, trên tài nguyên nào, có kế thừa từ cấp cha hay không.
3. **Điều kiện sử dụng:** ai có thể kích hoạt hoặc nhận danh tính đó, trong thời gian nào và dưới những ràng buộc nào.

Ví dụ, một role chỉ được khởi động lại một máy ảo thử nghiệm khác rất xa role có thể thay đổi mọi máy ảo sản xuất. Ngược lại, quyền sửa cấu hình một workload có thể rất nhạy cảm nếu workload sử dụng danh tính được đọc kho bí mật của toàn hệ thống.

Không nên đồng nhất các khái niệm sau:

| Khái niệm | Câu hỏi cần trả lời |
| --- | --- |
| Role được định nghĩa | Role chứa những quyền gì? |
| Role được gán | Principal nào nhận role, trực tiếp hoặc thông qua nhóm? |
| Role có thể được sử dụng | Principal có thể assume, kích hoạt hoặc sử dụng danh tính đó trong điều kiện nào? |
| Quyền hiệu lực | Một hành động cụ thể trên một tài nguyên cụ thể có được chấp nhận sau khi xét đầy đủ chính sách không? |
| Quyền đã được sử dụng | Log ghi nhận hành động nào trong khoảng quan sát? |

Một role được định nghĩa nhưng chưa gán vẫn là đối tượng cần kiểm kê. Tuy nhiên, mức phơi nhiễm hiện tại khác role đang được gán thường trực cho nhiều principal. Tương tự, không thấy log sử dụng chưa đủ để kết luận role không còn cần thiết.

## 2. Những nguồn cần kiểm kê

Discovery nên xây dựng tập dữ liệu đủ để nối **principal → quan hệ cấp quyền → role → tài nguyên**, rồi bổ sung các đường chuyển sang danh tính khác.

| Nhóm dữ liệu | Nội dung cần thu thập | Giá trị cho đánh giá |
| --- | --- | --- |
| Cấu trúc tổ chức | Tổ chức, tenant, account, management group, folder, subscription, project | Xác định ranh giới và quyền kế thừa |
| Danh tính con người | Người dùng, nhóm, principal liên kết qua nhà cung cấp danh tính | Xác định người thực sự có thể nhận quyền |
| Danh tính máy | Service principal, managed identity, service account, IAM role của workload | Phát hiện đặc quyền không gắn với phiên đăng nhập con người |
| Định nghĩa role và policy | Role có sẵn, role tùy chỉnh, policy inline hoặc dùng chung | Xác định hành động, tài nguyên và điều kiện |
| Assignment và binding | Chủ thể được gán, scope, điều kiện, trạng thái kích hoạt hoặc đủ điều kiện | Phân biệt quyền thường trực và quyền có điều kiện |
| Quan hệ tin cậy | Federation, assume role, impersonation, principal bên ngoài | Xác định đường nhận danh tính mạnh |
| Chính sách trên tài nguyên | Quyền đặt trực tiếp trên kho dữ liệu, khóa, vault hoặc tài nguyên tương ứng | Bổ sung những quyền không hiện ra từ role assignment đơn thuần |
| Ràng buộc và bảo vệ | Deny, giới hạn quyền, chính sách tổ chức và điều kiện áp dụng | Tránh đánh giá quá mức hoặc bỏ sót đường truy cập |
| Log và thông tin sở hữu | Sử dụng gần đây, chủ quản, mục đích, mã tác vụ và lịch sử thay đổi | Ưu tiên xử lý và chuẩn bị bằng chứng |

Tên hiển thị không đủ làm khóa định danh. Hai role cùng tên ở hai account hoặc project là hai đối tượng khác nhau. Nên dùng định danh ổn định của nhà cung cấp cùng cloud, tenant hoặc tổ chức, account/project và scope tương ứng.

Đối với tài khoản dịch vụ, cần ghi nhận workload nào đang dùng danh tính, nơi chạy và chủ sở hữu vận hành. Việc thấy một service account mạnh nhưng không biết ứng dụng phụ thuộc vào nó sẽ làm bước thu hẹp quyền hoặc luân chuyển credential dễ gây gián đoạn.

## 3. Các dấu hiệu role có đặc quyền lớn

### 3.1. Quản trị rộng trên phạm vi lớn

Role cho phép nhiều nhóm hành động trên toàn account, subscription, project hoặc cấp tổ chức cần được ưu tiên. Wildcard là một dấu hiệu hữu ích, nhưng phải xét vị trí xuất hiện của wildcard, tài nguyên đích và điều kiện.

Không có wildcard không đồng nghĩa quyền hẹp. Một danh sách hữu hạn các quyền quản lý danh tính hoặc đọc dữ liệu quan trọng vẫn có thể tạo tác động lớn.

### 3.2. Thay đổi ai được cấp quyền

Khả năng tạo hoặc sửa role, gán quyền, sửa trust policy hay thay đổi binding là đặc quyền quan trọng. Người có quyền sửa cơ chế cấp quyền có thể ảnh hưởng tới nhiều danh tính khác ngay cả khi không trực tiếp có quyền đọc dữ liệu.

Cần kiểm tra role có thể cấp những quyền nào, cho ai, trên phạm vi nào và có điều kiện giới hạn không. Một quyền gán role chỉ cho vài role được chỉ định không tương đương quyền gán mọi role.

### 3.3. Sử dụng hoặc cấp phát danh tính khác

Các quyền phát hành token, giả lập danh tính được phép, gắn danh tính vào workload hoặc cung cấp credential cho một dịch vụ là dấu hiệu cần phân tích. Mức rủi ro phụ thuộc quyền của danh tính đích và khả năng thực sự sử dụng nó.

Một quyền chuyển giao danh tính không tự động tạo ra toàn bộ đường leo thang. Có thể còn cần quyền tạo hoặc sửa workload, quyền kích hoạt nó, quan hệ tin cậy hợp lệ và khả năng nhận kết quả. Discovery phải ghi lại các điều kiện đó thay vì suy ra chỉ từ tên quyền.

### 3.4. Truy cập dữ liệu, bí mật và khóa

Role chỉ đọc cũng có thể là đặc quyền nếu được đọc dữ liệu sản xuất, lấy bí mật hoặc sử dụng khóa giải mã. Việc kiểm kê chỉ xét các quyền có động từ `write`, `admin` hoặc `manage` dễ bỏ sót nhóm này.

Đặc biệt, cần phân biệt quyền quản lý một kho bí mật với quyền đọc giá trị bí mật, hoặc quyền quản lý metadata khóa với quyền sử dụng khóa. Quan hệ giữa chúng phụ thuộc mô hình cấp quyền của tài nguyên và nhà cung cấp.

### 3.5. Thay đổi workload và bằng chứng giám sát

Quyền triển khai mã, thay image, thay script khởi động hoặc sửa cấu hình có thể dẫn tới thực thi dưới danh tính mạnh của workload. Quyền tắt thu thập log, sửa đích lưu log hoặc xóa bằng chứng làm tăng tác động của các quyền khác.

| Nhóm dấu hiệu | Điều cần đối chiếu thêm |
| --- | --- |
| Quản trị rộng | Scope thực tế, quyền kế thừa và ràng buộc còn hiệu lực |
| Quản lý IAM/RBAC | Những role có thể gán, chủ thể nhận và điều kiện phân quyền |
| Chuyển giao hoặc sử dụng danh tính | Quyền của danh tính đích và các bước còn thiếu |
| Đọc bí mật hoặc giải mã | Tài nguyên cụ thể, điều kiện dữ liệu và log sử dụng |
| Điều khiển workload | Danh tính chạy, quyền sửa mã/cấu hình và khả năng kích hoạt |
| Can thiệp giám sát | Loại log có thể ảnh hưởng, nơi lưu độc lập và quyền xóa |

## 4. Thu thập discovery với quyền tối thiểu

### 4.1. Xác định phạm vi và độ bao phủ

Trước khi thu thập, xác định rõ tổ chức, tài khoản, subscription, project và nhóm tài nguyên nằm trong phạm vi. Cần có nguồn đối chiếu phạm vi đủ tin cậy để biết có nơi nào chưa được quan sát.

Collector phải ghi nhận thời điểm thu thập, nguồn API hoặc bản xuất, lỗi truy cập, trang dữ liệu chưa lấy được và phạm vi không có quyền đọc. Một kết quả rỗng chỉ chứng minh truy vấn không trả đối tượng; nó không tự chứng minh môi trường không có role mạnh.

Nếu chỉ nhìn thấy một số project trong tổ chức, báo cáo phải thể hiện độ bao phủ một phần. Không diễn giải phần không quan sát được thành mức rủi ro thấp.

### 4.2. Tách quyền quan sát khỏi quyền thay đổi

Ưu tiên các API đọc cấu hình và dữ liệu kiểm toán cần thiết. Collector không mặc nhiên cần quyền sửa IAM, assume mọi role, tạo access key hoặc đọc giá trị bí mật để chứng minh role có đặc quyền.

Nếu một phép kiểm chứng yêu cầu thực thi hành động ở đích, phải tách nó thành hoạt động được cho phép và kiểm soát riêng. Discovery cấu hình có thể kết luận một quyền hoặc đường chuyển quyền là ứng viên cần xác minh mà không thử khai thác nó trên môi trường sản xuất.

Credential của collector cũng thuộc phạm vi PAM: có chủ quản, phạm vi tối thiểu, thời hạn phù hợp, cách lưu an toàn và log sử dụng. Tránh tạo một tài khoản discovery có quyền quản trị lâu dài chỉ để tiện thu thập.

### 4.3. Giữ dữ liệu nguồn đủ để truy vết

Nên giữ bản chụp chính sách hoặc tham chiếu phiên bản tương ứng cùng thời điểm quan sát. Chỉ lưu kết luận “role mạnh” sẽ khiến việc kiểm toán khó tái dựng lý do sau khi chính sách thay đổi.

Không cần đưa credential, token hoặc giá trị bí mật vào dữ liệu discovery. Những thông tin như tên principal, quan hệ nhóm và phạm vi tài sản vẫn cần được bảo vệ vì có thể mô tả cấu trúc quyền nhạy cảm của tổ chức.

## 5. Phân tích quyền hiệu lực và đường chuyển quyền

### 5.1. Không cộng cơ học mọi quyền nhìn thấy

Quyền hiệu lực phụ thuộc cơ chế đánh giá của từng nhà cung cấp. Chính sách trên danh tính, chính sách tài nguyên, deny, giới hạn quyền, điều kiện và loại phiên có thể tham gia theo các quy tắc khác nhau. Không nên dùng một công thức hợp nhất chung cho cả AWS, Azure và Google Cloud.

Với mỗi phát hiện, nên trả lời một câu hỏi cụ thể:

> Principal P có thể thực hiện hành động A trên tài nguyên R trong điều kiện C bằng đường cấp quyền nào?

Phải phân biệt một grant tiềm năng với quyền có thể thực thi trong bối cảnh hiện tại. Một điều kiện mạng có thể giảm khả năng truy cập từ bên ngoài nhưng không làm biến mất quyền khi principal hoạt động từ mạng được cho phép.

Khi chưa thu thập đủ ràng buộc, ghi kết luận là ứng viên hoặc quyền có khả năng tồn tại. Không tự ghi “đã xác nhận toàn quyền” chỉ vì thấy một policy có dấu `*`.

### 5.2. Dựng đồ thị quan hệ

Có thể mô hình hóa các loại cạnh như sau:

```text
Người dùng --thành viên của--> Nhóm
Nhóm --được gán--> Role
Role --cho phép hành động trên--> Tài nguyên
Principal --có thể nhận danh tính--> Role khác
Principal --có thể sửa--> Workload
Workload --chạy bằng--> Danh tính dịch vụ
Danh tính dịch vụ --được phép đọc--> Kho bí mật
```

Mỗi cạnh cần có bằng chứng, scope, điều kiện và thời điểm quan sát. Một đường trên đồ thị chỉ là đường chuyển quyền khả thi khi những điều kiện cần có thể đồng thời đáp ứng. Không nối hai quyền ở hai scope không liên quan rồi coi đó là đường leo thang đã xác nhận.

Ví dụ, việc người triển khai có thể sửa workload A và workload B có danh tính mạnh không đủ để kết luận người đó nhận được đặc quyền của B. Cần chứng minh đường liên kết đúng workload và khả năng thực thi theo nền tảng.

### 5.3. Phân biệt tác động và độ tin cậy

Nên lưu hai thuộc tính riêng:

- **Mức tác động/rủi ro:** nếu quyền hoặc đường chuyển quyền tồn tại, nó có thể ảnh hưởng tới đâu và dữ liệu nào.
- **Độ tin cậy:** bằng chứng đã đủ để khẳng định tới mức nào; có dữ liệu hoặc điều kiện còn thiếu không.

Một đường có thể dẫn tới quản trị toàn môi trường nhưng thiếu dữ liệu nhóm vẫn cần được ưu tiên xác minh. Tuy nhiên, báo cáo không được biến giả thuyết thành quyền đã xác nhận. Ngược lại, một quyền đọc bí mật trên đúng một hệ thống có thể đã được xác nhận rõ dù scope hẹp.

## 6. Ví dụ nhận diện trên AWS

Trong AWS, cần thu thập IAM role, trust policy, policy gắn trực tiếp hoặc thông qua managed policy, phiên bản policy đang có hiệu lực, permissions boundary nếu có và thông tin ràng buộc liên quan. Với truy cập liên account, phải xem cả phía có thể yêu cầu nhận role và phía tin cậy theo cơ chế đánh giá áp dụng.

### 6.1. Role có policy quản trị rộng

Một role gắn policy `AdministratorAccess` là tín hiệu ưu tiên cao. Sau đó cần xác định ai có thể nhận role, role nằm ở account nào, có giới hạn tổ chức hoặc điều kiện phiên nào áp dụng và tài nguyên nào chịu tác động.

Không kết luận role có toàn quyền hiệu lực chỉ từ tên policy. Cần đọc nội dung policy thực tế được gắn và xét các lớp giới hạn liên quan. Với role tùy chỉnh, tên `ReadOnlyOps` cũng không bảo đảm chỉ có quyền đọc.

### 6.2. Quyền chuyển giao role cho dịch vụ

`iam:PassRole` đáng được xem xét cùng khả năng tạo hoặc sửa tài nguyên dịch vụ chạy bằng role được chuyển giao. Bản thân quyền này không đồng nghĩa người dùng có thể gọi `sts:AssumeRole` để trực tiếp trở thành role đó.

Discovery cần xác định những role nào có thể được chuyển giao, dịch vụ đích nào được phép sử dụng, trust policy có phù hợp không và principal có những quyền vận hành bổ sung nào. Nếu role đích có quyền đọc bí mật hoặc truy cập dữ liệu sản xuất, đây có thể là một đường đặc quyền gián tiếp quan trọng.

Cần tránh quy tắc “có `iam:PassRole` là quản trị viên”. Kết luận hữu ích hơn là: có khả năng chuyển giao role cụ thể cho dịch vụ cụ thể, kết hợp với các quyền đã quan sát, còn những điều kiện nào cần xác minh.

### 6.3. Trust và policy trên tài nguyên

Trust policy xác định quan hệ tin cậy để nhận role, nhưng không thay thế policy mô tả quyền của role sau khi được nhận. Discovery phải xét cả khả năng nhận danh tính và khả năng sử dụng danh tính đó.

Quyền trên bucket, khóa hoặc tài nguyên khác có thể được cấp qua resource-based policy. Nếu chỉ đọc policy của role, việc kiểm kê có thể bỏ sót quyền quan trọng. Mô hình đánh giá phải xử lý đúng loại principal và loại policy, thay vì coi mọi giới hạn danh tính là áp dụng giống nhau cho mọi grant.

Nếu dùng IAM Identity Center hoặc federation, cần nối quyền được cấu hình ở nguồn với principal và role tương ứng ở account đích. Không chỉ kiểm kê người dùng IAM rồi coi đó là toàn bộ người có quyền quản trị.

## 7. Ví dụ nhận diện trên Azure

Trong Azure, cần nối **role definition**, **role assignment**, principal và scope. Scope có thể nằm ở management group, subscription, resource group hoặc tài nguyên, với quyền kế thừa theo cấu trúc áp dụng.

### 7.1. Các role có sẵn là tín hiệu phân loại

- `Owner` là tín hiệu quản trị tài nguyên và quản lý cấp quyền ở scope tương ứng.
- `User Access Administrator` là tín hiệu về khả năng quản lý quyền truy cập; cần xem scope và những điều kiện giới hạn assignment.
- `Contributor` có khả năng quản lý nhiều tài nguyên nhưng không mặc nhiên có quyền tạo role assignment trong Azure RBAC theo role định sẵn này.

Không vì `Contributor` thiếu quyền gán role mà đánh giá nó là quyền thấp. Khả năng thay đổi ứng dụng hoặc máy ảo chạy bằng managed identity mạnh vẫn có thể dẫn tới tác động gián tiếp. Phải xét chính xác quyền sửa workload và tài nguyên liên quan.

Cũng không suy ra từ `Owner` rằng principal luôn trực tiếp đọc được mọi dữ liệu của mọi dịch vụ. Data plane, mô hình quyền của tài nguyên và các điều kiện khác phải được đánh giá riêng.

### 7.2. Đọc nội dung role tùy chỉnh

Với role definition, cần xem `Actions`, `NotActions`, `DataActions` và `NotDataActions`. Những mục loại trừ trong định nghĩa một role không tương đương lệnh cấm toàn cục; quyền có thể đến từ một assignment khác.

`AssignableScopes` mô tả nơi role có thể được gán, không chứng minh role đã được gán tại mọi nơi đó. Scope thực tế phải lấy từ assignment và quan hệ kế thừa.

Cần đối chiếu các deny assignment và điều kiện có liên quan, cùng quyền nhận qua nhóm. Không coi danh sách assignment trực tiếp của một người là toàn bộ quyền của người đó.

### 7.3. Phân biệt quyền đủ điều kiện và đang hoạt động

Nếu sử dụng cơ chế quản lý đặc quyền theo thời hạn như PIM, nên ghi riêng assignment đang hoạt động, assignment đủ điều kiện kích hoạt, lịch hiệu lực và điều kiện kích hoạt. Chúng có mức phơi nhiễm và yêu cầu kiểm soát khác nhau.

Quyền trong Microsoft Entra ở tầng thư mục và Azure RBAC ở tầng tài nguyên cũng cần được phân biệt trong dữ liệu. Hai hệ thống liên quan tới danh tính nhưng không phải cùng một danh sách role hay cùng cơ chế scope.

## 8. Ví dụ nhận diện trên Google Cloud

Trong Google Cloud, cần thu thập IAM policy và binding ở các cấp phù hợp như organization, folder, project và tài nguyên hỗ trợ. Phải nối quyền kế thừa, nhóm và các điều kiện áp dụng.

### 8.1. Role rộng và role tùy chỉnh

Các basic role như `roles/owner` và `roles/editor` là tín hiệu cần rà soát vì phạm vi quyền rộng. Không diễn giải chúng thành quyền giống nhau hoặc khả năng thực hiện mọi hành động IAM.

Với custom role, cần đọc danh sách permission thực tế. Một role có khả năng sửa IAM policy của tài nguyên cần được phân tích theo nơi quyền đó áp dụng và những quyền mà principal có thể cấp thông qua thay đổi policy.

Ngoài allow policy, cần xét deny policy và các ràng buộc liên quan theo đúng cơ chế và phạm vi chúng thực sự tác động. Một chính sách tổ chức có thể hạn chế cấu hình hoặc hành vi nhất định; không nên mặc định nó thu hẹp mọi permission của một role rộng.

### 8.2. Service account impersonation và quyền gắn danh tính

`roles/iam.serviceAccountTokenCreator` là tín hiệu cần xem xét về khả năng tạo thông tin xác thực ngắn hạn cho service account đích, tùy quyền và điều kiện áp dụng. Cần nối service account đó tới các role và tài nguyên mà nó được truy cập.

`roles/iam.serviceAccountUser` với khả năng `iam.serviceAccounts.actAs` không đồng nghĩa có cùng khả năng tạo token như Token Creator. Tuy nhiên, khi kết hợp với quyền tạo hoặc thay đổi workload có thể chạy bằng service account, nó có thể tạo đường sử dụng quyền gián tiếp.

Quyền tạo khóa service account cũng cần ưu tiên vì có thể tạo credential tồn tại ngoài một phiên quản trị ngắn. Discovery cần đánh giá quyền và metadata liên quan; không cần thực sự tạo khóa để chứng minh rủi ro.

Nếu service account nhận quyền mạnh ở project khác hoặc tài nguyên khác, không dừng phân tích ở project chứa service account. Đồng thời, phải ghi rõ phần liên kết liên project nào chưa quan sát được để tránh kết luận thiếu căn cứ.

## 9. Tạo bản ghi phát hiện có thể kiểm chứng

Một phát hiện nên mô tả cả quyền trực tiếp và đường gián tiếp, nhưng không trộn chúng thành một kết luận mơ hồ. Có thể dùng cấu trúc dữ liệu nội bộ với các trường sau; đây là gợi ý thiết kế, không phải schema chung của nhà cung cấp.

| Trường thông tin | Nội dung cần thể hiện |
| --- | --- |
| Định danh | Mã phát hiện, cloud, tenant/account/project, role và assignment/binding |
| Principal | Danh tính được cấp, loại danh tính, nhóm trung gian và chủ sở hữu |
| Scope | Tài nguyên hoặc cấp tổ chức chịu tác động; nguồn quyền kế thừa nếu có |
| Khả năng đặc quyền | Hành động nhạy cảm trực tiếp hoặc đường chuyển quyền được quan sát |
| Điều kiện và giới hạn | Điều kiện kích hoạt, deny, giới hạn quyền và các ràng buộc đã kiểm tra |
| Bằng chứng nguồn | Nội dung hoặc phiên bản policy, assignment và quan hệ tin cậy liên quan |
| Thời điểm | Thời gian quan sát, thời gian sử dụng gần nhất nếu có, độ mới dữ liệu |
| Đánh giá | Mức tác động, độ tin cậy, phần dữ liệu còn thiếu và lý do ưu tiên |
| Quản lý tiếp theo | Chủ quản xử lý, biện pháp đề nghị, trạng thái xác minh và quyết định ngoại lệ |

Một kết luận cụ thể có thể viết như sau:

> Nhóm vận hành được gán role có quyền thay đổi chính sách truy cập ở phạm vi sản xuất. Assignment được kế thừa từ cấp cha; đã thu thập định nghĩa role và thành viên nhóm tại thời điểm quan sát. Cần xác minh thêm điều kiện hạn chế gán một số role trước khi kết luận phạm vi cấp quyền có thể thay đổi.

Phát hiện này hữu ích hơn câu “có admin” vì nêu được quan hệ cấp quyền, phạm vi, bằng chứng và giới hạn kết luận.

Khi thông tin thành viên nhóm nằm ở hệ thống danh tính khác mà collector không được đọc, cần ghi trạng thái chưa phân giải. Không tự coi nhóm rỗng và cũng không mặc định mọi người trong tổ chức là thành viên.

## 10. Ví dụ phân tích một role triển khai ứng dụng

Giả sử discovery quan sát được các dữ kiện sau trong một môi trường cloud:

1. Nhóm `release-team` được phép cập nhật mã hoặc cấu hình chạy của workload `payment-worker`.
2. Workload này sử dụng danh tính `payment-runtime`.
3. `payment-runtime` được quyền đọc một tập bí mật phục vụ thanh toán.
4. Chưa có bằng chứng nhóm triển khai được trực tiếp đọc bí mật bằng danh tính người dùng.

Nếu chỉ kiểm tra role cấp cho người dùng có quyền đọc vault hay không, nhóm triển khai có thể bị bỏ qua. Tuy nhiên, khả năng thay đổi mã được workload thực thi dưới danh tính `payment-runtime` là một đường tác động cần ưu tiên phân tích.

Các điểm cần xác minh tiếp gồm:

- Quyền cập nhật có thực sự cho phép thay thành phần được thực thi hay chỉ sửa metadata không nhạy cảm.
- Có cơ chế kiểm tra, phê duyệt hoặc kiểm soát tính toàn vẹn ngăn nội dung tùy ý được chạy không.
- Danh tính nào được dùng tại thời điểm thực thi và quyền đọc bí mật áp dụng trên những tài nguyên nào.
- Người cập nhật có thể kích hoạt hoặc chờ workload chạy trong những điều kiện nào.
- Các ràng buộc mạng, điều kiện danh tính và cơ chế giám sát còn lại có ảnh hưởng thế nào tới đường tác động.

Không cần triển khai mã đọc bí mật để phát hiện đường quyền này. Có thể ghi nhận bằng chứng cấu hình và trạng thái “cần xác minh khả năng sử dụng gián tiếp” cho tới khi đủ dữ liệu hoặc có phép kiểm chứng được cho phép.

Sau xác minh, biện pháp có thể bao gồm tách danh tính theo môi trường, thu hẹp tập bí mật mà workload được đọc, đưa thay đổi mã qua phê duyệt và giới hạn ai có quyền triển khai sản xuất. Chỉ đổi tên role triển khai sẽ không giảm khả năng thực tế của nó.

## 11. Chuyển kết quả discovery sang quản lý PAM

Discovery tạo đầu vào cho quyết định kiểm soát; nó không tự thực hiện việc thu hồi hoặc thay đổi role. Cần xác định chủ sở hữu, tác vụ hợp lệ và phụ thuộc vận hành trước khi đưa ra thay đổi.

| Kết quả phát hiện | Hướng xử lý PAM cần xem xét |
| --- | --- |
| Con người có quyền quản trị rộng và thường trực | Tách vai trò theo tác vụ, giới hạn scope, dùng kích hoạt JIT và phê duyệt phù hợp |
| Quyền điều khiển workload gắn danh tính mạnh | Tách quyền triển khai, danh tính chạy và quyền truy cập dữ liệu; kiểm soát chuỗi thay đổi |
| Quyền phát hành credential hoặc token cho danh tính mạnh | Giới hạn principal được nhận quyền, đối tượng đích và điều kiện sử dụng; giám sát phát hành |
| Tài khoản dịch vụ không có chủ sở hữu rõ ràng | Xác định workload phụ thuộc, chủ quản, vòng đời và kế hoạch xử lý |
| Credential dài hạn hoặc khóa có thể được tạo rộng | Ưu tiên cơ chế danh tính ngắn hạn được hỗ trợ; bảo vệ và luân chuyển bí mật còn cần dùng |
| Quyền từ bên ngoài tổ chức | Xác minh bên được tin cậy, nhu cầu, điều kiện và cơ chế chấm dứt quan hệ |
| Quyền can thiệp bằng chứng cùng quyền quản trị hệ thống | Tách quản trị log, bảo vệ nơi lưu và tăng khả năng đối chiếu độc lập |

Role cloud không đồng nhất với một mật khẩu cần đưa vào vault. Có trường hợp cơ chế phù hợp là federation hoặc token ngắn hạn; có trường hợp vẫn phải bảo vệ bí mật của ứng dụng. Cần chọn kiểm soát theo loại danh tính và cách sử dụng thực tế.

Khi áp dụng JIT cho role, phải phân biệt thời hạn assignment với hiệu lực của phiên hoặc token đã phát hành. Việc gỡ assignment không mặc nhiên chấm dứt mọi hoạt động đang diễn ra. Kết quả discovery nên hỗ trợ lập bản đồ các thành phần cần cưỡng chế và giám sát.

Cũng không tự động xóa role chỉ vì chưa thấy sử dụng trong log. Cần xét độ bao phủ log, thời gian lưu, tác vụ định kỳ và vai trò khẩn cấp. Nếu role được giữ lại vì ngoại lệ, lưu người chịu trách nhiệm, lý do, điều kiện và mốc rà soát.

## 12. Kiểm chứng collector và duy trì độ mới

Khi triển khai quy trình discovery, cần kiểm chứng khả năng phát hiện bằng tập tình huống có kết quả dự kiến rõ ràng:

| Tình huống mẫu | Kỳ vọng đối với kết quả discovery |
| --- | --- |
| Role tên bình thường nhưng có quyền quản trị rộng | Được nhận diện từ nội dung quyền |
| Role tên quản trị nhưng bị giới hạn scope và hành động | Ghi đúng phạm vi, không kết luận vượt bằng chứng |
| Quyền được kế thừa từ cấp cha hoặc nhận qua nhóm | Nối được nguồn cấp quyền hoặc nêu rõ phần chưa phân giải |
| Grant nằm trên policy của tài nguyên | Không bị bỏ sót chỉ vì thiếu assignment trực tiếp |
| Có điều kiện hoặc deny làm thay đổi kết quả | Phản ánh đúng phạm vi áp dụng và độ tin cậy |
| Quyền đặc biệt chỉ xuất hiện khi kết hợp nhiều quan hệ | Ghi đường liên kết cùng các điều kiện cần thiết |
| Thiếu quyền đọc, lỗi phân trang hoặc thiếu tài khoản trong phạm vi | Báo độ bao phủ chưa đầy đủ |
| Policy đổi sau lần quét | Đánh dấu dữ liệu cũ và tính lại kết luận liên quan |

Role mạnh có thể xuất hiện sau thay đổi policy, thêm thành viên nhóm, đổi trust, thay danh tính workload hoặc mở rộng scope kế thừa. Vì vậy, nên kết hợp kiểm kê định kỳ với xử lý sự kiện thay đổi theo khả năng nền tảng. Khi xử lý sự kiện, cần có cách đối soát đầy đủ để phát hiện sự kiện bị thiếu.

Các chỉ số hữu ích gồm tỷ lệ scope đã thu thập thành công, tuổi của bản chụp quyền, số nhóm chưa phân giải, số role mạnh chưa có chủ sở hữu, số đường chuyển quyền chưa xác minh và thời gian từ phát hiện đến quyết định xử lý.

Giá trị của discovery nằm ở một bản đồ quyền có bằng chứng: role nào mạnh, principal nào có thể sử dụng, tác động tới đâu và những điều kiện nào còn ràng buộc. Bản đồ đó giúp PAM quản lý đặc quyền dựa trên khả năng thực tế của danh tính thay vì dựa vào tên role hoặc một danh sách quản trị viên tĩnh.
