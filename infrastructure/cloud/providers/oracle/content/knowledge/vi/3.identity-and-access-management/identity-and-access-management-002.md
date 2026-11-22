# Groups, application roles và phân tách nhiệm vụ

Một kỹ sư cần xem cấu hình Compute để chẩn đoán sự cố, một nhân viên vận hành cần theo dõi ứng dụng tích hợp, còn một người khác chịu trách nhiệm phê duyệt triển khai production. Nếu cả ba đều được thêm vào nhóm quản trị toàn tenancy, công việc có thể thực hiện được nhưng trách nhiệm và phạm vi ảnh hưởng không còn rõ ràng.

Trong Oracle Cloud Infrastructure (OCI), group giúp tổ chức các danh tính có cùng nhu cầu truy cập. Quyền của thành viên có thể đến từ IAM policy, role quản trị identity domain hoặc application role được gán cho group. Các cơ chế này có phạm vi khác nhau; tên nhóm hoặc tên role không đủ để kết luận một người được làm gì.

Bài học thuộc chương **Danh tính và phân quyền IAM** trong **CLOUD_PROVIDERS_ORACLE**. Mục tiêu là thiết kế cách cấp quyền cho hạ tầng OCI và ứng dụng, đồng thời phân tách những nhiệm vụ có thể xung đột. Những lựa chọn này ảnh hưởng trực tiếp đến việc vận hành VCN, Compute, lưu trữ, dịch vụ cơ sở dữ liệu Oracle, giám sát và tự động hóa.

## 1. Phân biệt group, policy và role

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| User | Danh tính của người sử dụng hệ thống | Kỹ sư vận hành An |
| Group | Tập hợp danh tính để quản lý tư cách thành viên và gán quyền theo nhóm | `ShopComputeReaders` |
| OCI IAM policy | Quy tắc xác định thao tác trên tài nguyên OCI và phạm vi áp dụng | Cho nhóm đọc instance trong một compartment |
| Application role | Quyền hoặc tập quyền do một ứng dụng/dịch vụ định nghĩa | Role giám sát trong một Oracle Integration instance |
| Identity domain administrator role | Quyền quản trị danh tính và cấu hình của identity domain theo vai trò | User administrator |
| Role trong cơ sở dữ liệu | Quyền bên trong hệ quản trị cơ sở dữ liệu | Role được cấp cho tài khoản kết nối database |

Các dòng trong bảng là những góc nhìn để phân tích quyền, không có nghĩa mọi loại role đều được triển khai bằng một cơ chế kỹ thuật hoàn toàn độc lập. Điều cần xác định là **hệ thống nào kiểm tra quyền, trên đối tượng nào và theo phạm vi nào**.

Một người có thể thuộc nhiều group. Một group cũng có thể được dùng trong nhiều IAM policy hoặc được gán nhiều application role. Vì thế, tạo thêm một group “ít quyền” không thu hẹp những quyền người đó đã nhận từ đường khác.

Các câu hỏi cần trả lời riêng:

- Đăng nhập thành công chứng minh điều gì? Danh tính đã được xác thực theo luồng đăng nhập đang dùng.
- Thuộc group chứng minh điều gì? Danh tính có tư cách thành viên của một tập hợp.
- Được làm một thao tác chứng minh điều gì? Hệ thống đích đã chấp nhận quyền cho thao tác, tài nguyên và ngữ cảnh cụ thể.

Không thể thay câu hỏi thứ ba bằng việc chỉ kiểm tra hai câu hỏi đầu.

## 2. Lần theo các đường cấp quyền

Có thể dùng sơ đồ sau để đọc một thiết kế quyền:

```text
Người dùng
  ├── Thành viên group A
  │     └── IAM policy
  │           └── Thao tác trên tài nguyên OCI trong phạm vi được cấp
  │
  ├── Thành viên group B
  │     └── Application role của ứng dụng X
  │           └── Chức năng được ứng dụng X cho phép
  │
  ├── Application role được gán trực tiếp
  │     └── Chức năng của ứng dụng tương ứng
  │
  └── Role quản trị identity domain, trực tiếp hoặc qua group
        └── Nhiệm vụ quản trị danh tính trong phạm vi liên quan
```

Sơ đồ mô tả những đường cần kiểm tra, không khẳng định tất cả ứng dụng đều dùng cùng cơ chế role hoặc token. Một ứng dụng có thể có mô hình quyền nội bộ riêng sau khi nhận danh tính qua SSO.

### 2.1. Group trong IAM policy

Ví dụ sau cấp quyền đọc tài nguyên `instances` cho một group trong identity domain giả định `LearningDomain`:

```text
Allow group 'LearningDomain'/'ShopComputeReaders' to read instances in compartment id <DEV_COMPARTMENT_OCID>
```

Cần thay tên domain, group và placeholder bằng giá trị thực tế. Statement minh họa phạm vi đọc instance; nó không tự cấp quyền đọc nội dung database, sửa VCN hoặc quản lý danh tính.

Ghi rõ identity domain khi tham chiếu group giúp tránh nhầm nhóm cùng tên. OCI cũng hỗ trợ tham chiếu group bằng định danh theo cú pháp policy; tên hiển thị và định danh phải được đối chiếu đúng đối tượng. Xem [Policy Syntax](https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/policysyntax.htm).

Quyền cấp tại compartment cha có thể áp dụng xuống các compartment con. Một policy hẹp mới không thu hồi grant rộng đã có ở cấp trên. Khi kiểm tra tài khoản, phải xét các group liên quan và đường kế thừa của policy. Xem [Policy Inheritance](https://docs.oracle.com/en-us/iaas/Content/Identity/policieshow/Policy_Inheritance.htm).

### 2.2. Group được gán application role

Ví dụ, group `ShopIntegrationMonitors` được gán role giám sát của một ứng dụng Oracle đã tích hợp với identity domain. Các thành viên nhận quyền tương ứng trong ứng dụng theo mô hình gán role của dịch vụ đó.

Điều này không tự sinh một IAM policy cho phép đọc Compute hoặc sửa Object Storage. Tương tự, quyền tạo tài nguyên dịch vụ trên OCI không nên được dùng làm bằng chứng rằng người dùng đã có mọi chức năng bên trong ứng dụng được dịch vụ cung cấp.

Tài liệu Oracle Integration phân biệt người quản trị tài nguyên OCI với người dùng có service role trong instance. Đây là một ví dụ thực tế về hai phạm vi cần thiết kế riêng. Xem [Learn About Users and Resources](https://docs.oracle.com/en/cloud/paas/application-integration/security/learn-users-resources.html).

### 2.3. Role quản trị identity domain

Role quản trị identity domain dùng để ủy quyền các nhiệm vụ như quản lý người dùng, ứng dụng hoặc cấu hình bảo mật. Một số vai trò tiêu biểu:

| Role | Trọng tâm quyền |
| --- | --- |
| Identity domain administrator | Quản trị đầy đủ identity domain liên quan |
| User administrator | Quản lý users, groups và memberships trong domain |
| Application administrator | Quản lý ứng dụng và cấp/thu hồi truy cập ứng dụng |
| Security administrator | Quản lý cấu hình và thiết lập bảo mật của domain |
| Audit administrator | Chạy báo cáo của identity domain |

Bảng là tóm tắt để phân biệt trách nhiệm; phải đọc đầy đủ phạm vi của role trước khi cấp. Xem [Understanding Administrator Roles](https://docs.oracle.com/en-us/iaas/Content/Identity/roles/understand-administrator-roles.htm).

Với domain khác Default, quyền Identity domain administrator thuộc phạm vi domain đó, không mặc nhiên là quản trị toàn tenancy. Với Default domain và các danh tính quản trị ban đầu, cần xem xét đặc quyền và policy liên quan, không áp dụng máy móc kết luận của secondary domain. OCI đánh giá cả policy và administrator role trong việc xác định quyền liên quan. Xem [Overview of IAM](https://docs.oracle.com/en-us/iaas/Content/Identity/getstarted/identity-domains.htm).

Không nên xóa một người khỏi một group rồi mặc định họ đã mất role quản trị. Có thể còn assignment trực tiếp hoặc qua group khác. Tài liệu Oracle nêu rõ một số group quản trị được liên kết với role, nhưng việc gán role trực tiếp không đồng nghĩa người đó được thêm vào group tương ứng. Xem [Groups](https://docs.oracle.com/en-us/iaas/Content/Identity/conversion/groups.htm).

## 3. Thiết kế group theo công việc và phạm vi

### 3.1. Mỗi group cần có một mục đích quản trị rõ ràng

Thay vì dùng một group `IT-Team` để nhận mọi quyền, có thể tách thành:

| Group minh họa | Mục đích | Không tự suy ra |
| --- | --- | --- |
| `ShopDevComputeReaders` | Đọc thông tin Compute của môi trường dev | Có quyền sửa hoặc xóa instance |
| `ShopProdOperators` | Thực hiện các thao tác production đã được phân tích | Có quyền quản lý IAM |
| `ShopIntegrationMonitors` | Nhận role giám sát của ứng dụng tích hợp cụ thể | Có quyền trên mọi ứng dụng khác |
| `ShopReleaseApprovers` | Đại diện những người được phê duyệt trong quy trình phát hành | OCI tự chặn mọi hành vi tự phê duyệt |
| `ShopAccessReviewers` | Kiểm tra bằng chứng và rà soát quyền được giao | Được sửa membership hoặc cấp role |

Tên group là quy ước của ví dụ, không phải tên mặc định bắt buộc của OCI. Nhóm chỉ có quyền như dự kiến khi policy, role assignment và ứng dụng thực thi đúng thiết kế.

Không cần tạo một group cho từng user hoặc từng API nếu điều đó làm mô hình khó quản lý. Nên gom các nhiệm vụ tương đồng, đồng thời tách khi khác môi trường, phạm vi tài nguyên, mức nhạy cảm hoặc người phê duyệt.

### 3.2. Ghi lại chủ sở hữu và đường cấp quyền

Mỗi group nên có tối thiểu:

- Mục đích và phạm vi môi trường.
- Chủ sở hữu nghiệp vụ hoặc kỹ thuật.
- Nguồn quản lý membership: tại OCI hay một hệ thống danh tính bên ngoài.
- Policy, administrator role và application role đang gán.
- Điều kiện gia nhập, người phê duyệt và thời hạn nếu là quyền tạm.
- Các group hoặc nhiệm vụ xung đột cần kiểm tra.
- Cách thu hồi và người chịu trách nhiệm xác minh.

Nếu membership được đồng bộ từ IdP hoặc hệ thống nguồn, cần xác định nơi có thẩm quyền sửa. Xóa thủ công tại đích trong khi nguồn vẫn cấp quyền có thể khiến membership quay trở lại ở đợt đồng bộ sau. Cách đồng bộ và mapping phải được kiểm tra theo tích hợp đang dùng.

Đặc biệt, phải xem xét trước khi gán quyền nhạy cảm cho group có phạm vi thành viên rất rộng, chẳng hạn nhóm chứa mọi người dùng trong domain. Việc thuận tiện khi onboarding không bù được quyền vô tình cấp cho những người không có nhiệm vụ tương ứng.

### 3.3. Người sửa membership cũng tham gia vào quá trình cấp quyền

Một policy có thể rất chặt nhưng vẫn bị vô hiệu về mặt quản trị nếu bất kỳ ai cũng có thể tự thêm mình vào group nhận policy đó. Điều tương tự xảy ra với group được gán application role mạnh.

Cần kiểm tra thao tác thật sự được ủy quyền: người quản lý group có sửa được membership của group nhạy cảm không, có tự thêm tài khoản khác của mình không, và thay đổi có cần người thứ hai duyệt không? Không nên suy ra câu trả lời chỉ từ chức danh “quản trị người dùng”.

Mức nhạy cảm của quyền quản lý group phụ thuộc **những quyền phía sau group**, không chỉ số lượng thành viên hoặc tên group.

## 4. Hiểu application role theo đúng ứng dụng

### 4.1. Application role có ý nghĩa trong phạm vi cụ thể

Một application role không phải “role dùng chung cho toàn bộ Oracle Cloud”. Muốn đọc đúng một assignment, cần biết:

- Ứng dụng hoặc service instance nào sở hữu role.
- Role cho phép những chức năng nào trong phiên bản và tính năng đang sử dụng.
- Assignment là trực tiếp cho user hay gián tiếp qua group.
- Có role khác, quyền nội bộ hoặc mapping khác mở rộng quyền hay không.
- Quyền có được đồng bộ sang ứng dụng hay được đánh giá khi truy cập.

Ví dụ thực tế từ Oracle Integration:

| Role | Ý nghĩa khái quát trong instance |
| --- | --- |
| `ServiceMonitor` | Theo dõi các tính năng được hỗ trợ cho role |
| `ServiceDeveloper` | Phát triển các thành phần mà tính năng tương ứng cho phép |
| `ServiceAdministrator` | Quản trị các tính năng được cung cấp trong instance |

Quyền chi tiết khác nhau theo tính năng. Không đọc tên `ServiceDeployer` rồi kết luận nó là role triển khai mọi integration; tài liệu hiện hành giới hạn role này cho RPA và nêu nó không áp dụng cho tính năng Integrations. Xem [Oracle Integration: Service Roles](https://docs.oracle.com/en-us/iaas/application-integration/doc/oracle-integration-roles.html).

Đối với một dịch vụ khác, tên role và khả năng tạo role tùy biến có thể khác. Không tự bịa application role rồi cho rằng có thể thêm nó vào mọi Oracle application. Nếu bộ role có sẵn quá rộng, cần xem khả năng phân quyền chi tiết mà dịch vụ thực sự hỗ trợ hoặc bổ sung kiểm soát ở quy trình liên quan.

### 4.2. Ưu tiên gán qua group khi phù hợp

Gán role qua group giúp thay đổi nhân sự mà không phải sửa từng assignment của ứng dụng. Mô hình ví dụ:

```text
An, Bình
    └── ShopIntegrationMonitors
          └── ServiceMonitor của instance tích hợp được giao
```

Nếu An chuyển nhiệm vụ, người quản trị thu hồi membership phù hợp và kiểm tra lại quyền. Tuy nhiên, An vẫn có thể giữ role qua assignment trực tiếp hoặc group khác. Danh sách member của một group chỉ là một phần bằng chứng.

Gán trực tiếp có thể cần cho một số trường hợp cụ thể, nhưng nên được ghi nhận cùng lý do, người duyệt và thời hạn. Tránh một quy trình thông thường dùng group trong khi các trường hợp đặc biệt lại tích lũy quyền trực tiếp không được rà soát.

Khi import assignment, cần phân biệt tạo role với thêm thành viên vào role có sẵn. Chức năng import users/groups cho Oracle application roles nhập **membership**; role phải tồn tại trước. Xem [Importing Users and Groups for Oracle Application Roles](https://docs.oracle.com/en-us/iaas/Content/Identity/datatransfer/import-users-and-groups-oracle-application-roles.htm).

### 4.3. SSO, OAuth scope và application role không đồng nhất

SSO giúp ứng dụng nhận danh tính đã xác thực. Ứng dụng vẫn cần xác định người đó có quyền thực hiện nghiệp vụ nào. Việc biểu tượng ứng dụng xuất hiện hoặc đăng nhập thành công chưa chứng minh quyền phê duyệt, cấu hình hoặc đọc dữ liệu nhạy cảm.

Với ứng dụng tùy biến, nhóm phát triển phải xác định hợp đồng tích hợp: role được lấy từ đâu, claim nào được tin cậy, có gọi API lấy quyền hay không và ai duy trì mapping sang quyền nội bộ. Không giả định mọi token đều tự chứa mọi group hoặc application role.

OAuth scope là một thành phần của cơ chế ủy quyền API. Nó không phải tên gọi thay thế cho mọi application role. Cần kiểm tra cấu hình của client, tài nguyên đích và cách ứng dụng xác minh token thay vì chỉ tìm một chuỗi có vẻ giống tên role.

## 5. Phân tách nhiệm vụ là gì?

Phân tách nhiệm vụ, thường gọi là **Separation/Segregation of Duties (SoD)**, hạn chế việc một người tự hoàn tất một chuỗi hành động có thể gây sai phạm hoặc sai sót mà không có kiểm tra độc lập.

Ví dụ:

- Người yêu cầu quyền production không tự duyệt yêu cầu của mình.
- Người chuẩn bị thay đổi không tự phê duyệt thay đổi đó.
- Người được rà soát quyền không tự xác nhận toàn bộ quyền của chính mình.
- Người triển khai ứng dụng không mặc nhiên được sửa cơ chế phê duyệt và cấu hình cấp quyền cho pipeline.

SoD khác với việc chỉ chia thành nhiều group. Hai group có tên khác nhau nhưng cùng một người sở hữu toàn bộ quyền vẫn có thể tạo ra xung đột.

### 5.1. Phân tách tĩnh và phân tách theo giao dịch

| Cách phân tách | Quy tắc minh họa | Nơi cần thực thi |
| --- | --- | --- |
| Tĩnh | Một người không đồng thời nhận hai gói quyền xung đột trong cùng phạm vi | Quy trình cấp quyền, công cụ governance hoặc hệ thống quản lý quyền |
| Theo giao dịch | Một người có thể làm nhiều vai trò nhưng không duyệt yêu cầu do chính mình tạo | Logic nghiệp vụ hoặc workflow kiểm tra từng giao dịch |
| Theo môi trường | Quyền phát triển không tự mở quyền triển khai production | Group, policy, role assignment và đường triển khai |
| Theo quản trị | Người dùng quyền nhạy cảm không tự thay đổi cơ chế cấp quyền đó | Phân quyền quản trị và kiểm soát thay đổi |
| Theo bằng chứng | Người thực hiện hoạt động không toàn quyền kiểm soát nơi lưu bằng chứng kiểm tra | Thiết kế thu thập, truy cập và bảo vệ chứng cứ |

Trong bài này, “tĩnh” và “theo giao dịch” là các mẫu thiết kế SoD, không phải lời khẳng định rằng OCI tự tạo quy tắc loại trừ chỉ từ tên group.

Một người có thể có nhiều tài khoản ở nhiều domain. Nếu yêu cầu là phân tách giữa **hai người độc lập**, việc dùng hai username của cùng một người chưa đáp ứng yêu cầu. Cần có cách liên kết tài khoản với chủ thể thực trong phạm vi quản trị của tổ chức.

### 5.2. Chỉ cấm những tổ hợp thật sự xung đột

Không phải mọi kiêm nhiệm đều có vấn đề. Kỹ sư phát triển đồng thời có quyền giám sát môi trường dev có thể là nhu cầu bình thường.

Quy tắc xung đột nên có cấu trúc:

```text
Hai nhiệm vụ xung đột
+ Phạm vi hệ thống hoặc dữ liệu
+ Môi trường
+ Điều kiện được chấp nhận
+ Cách phát hiện và xử lý
```

Ví dụ, “chuẩn bị và tự phê duyệt cùng một bản phát hành Shop production” rõ ràng hơn “không được vừa là developer vừa là operator”. Quy tắc quá rộng có thể làm gián đoạn công việc hợp lệ và tạo ra nhiều ngoại lệ khó kiểm soát.

### 5.3. Phân biệt ngăn chặn và phát hiện

Kiểm soát ngăn chặn từ chối hành vi trước khi nó hoàn tất, chẳng hạn backend không cho người tạo yêu cầu tự phê duyệt.

Kiểm soát phát hiện tìm ra vấn đề sau khi phát sinh, chẳng hạn báo cáo cho thấy một người đã đồng thời giữ hai gói quyền xung đột. Báo cáo hữu ích nhưng không thay thế một chốt phê duyệt bắt buộc nếu nghiệp vụ yêu cầu ngăn chặn trước.

Mỗi quy tắc cần nêu rõ nó thuộc loại nào. Một email báo cho nhóm kiểm tra sau triển khai không có cùng tác dụng với việc chặn triển khai chưa được phê duyệt.

## 6. Thiết kế một quy trình phát hành có phân tách nhiệm vụ

Giả sử Shop có một cổng yêu cầu phát hành, một pipeline triển khai lên OCI và một ứng dụng tích hợp để theo dõi các luồng liên quan. Các nhóm dưới đây là mô hình tổ chức minh họa; không phải danh sách role dựng sẵn của OCI.

| Vai trò công việc | Trách nhiệm chính | Quyền cần tách |
| --- | --- | --- |
| Người chuẩn bị thay đổi | Tạo yêu cầu và cung cấp artifact cần triển khai | Tự duyệt yêu cầu của chính mình |
| Người phê duyệt | Kiểm tra và phê duyệt nội dung đã định danh | Sửa artifact sau khi duyệt mà không duyệt lại |
| Danh tính pipeline | Triển khai nội dung đã được phép vào phạm vi OCI được giao | Tự tạo bằng chứng phê duyệt của con người |
| Người quản trị quyền | Thực hiện thay đổi membership/assignment đã được chấp thuận | Tự phê duyệt quyền nhạy cảm cho bản thân |
| Người rà soát | Đọc bằng chứng và đánh giá các ngoại lệ | Tự sửa kết quả hoặc cơ chế lưu bằng chứng đang kiểm tra |

Danh tính pipeline là một danh tính tự động hóa được thiết kế riêng, không phải mặc định một human user trong group. Cách cấp quyền cho workload phải phù hợp dịch vụ thực thi; không dùng mật khẩu chung của nhóm nhân viên làm cơ chế triển khai.

### 6.1. Group chỉ giải quyết một phần của mô hình

Có thể tạo group `ShopReleaseRequesters` và `ShopReleaseApprovers` để biểu diễn hai tập người. Cổng phát hành tùy biến phải ánh xạ chúng sang quyền nghiệp vụ tương ứng và kiểm tra điều kiện của từng yêu cầu.

Mã giả dưới đây minh họa logic cần có ở phía máy chủ:

```text
Khi phê duyệt:
    xác thực người thao tác
    kiểm tra quyền phê duyệt đối với Shop production
    kiểm tra người phê duyệt khác người tạo yêu cầu
    kiểm tra yêu cầu còn ở trạng thái cho phép phê duyệt
    ghi người duyệt, mã yêu cầu, định danh artifact và thời điểm

Khi triển khai:
    kiểm tra có phê duyệt hợp lệ và còn hiệu lực
    kiểm tra artifact đúng với bản đã được duyệt
    kiểm tra phạm vi triển khai đúng với phạm vi được duyệt
    triển khai bằng danh tính pipeline được cấp quyền phù hợp
    ghi kết quả và liên kết với yêu cầu, phê duyệt, artifact
```

Danh tính, thông tin người tạo và trạng thái phê duyệt phải đến từ nguồn được máy chủ kiểm chứng. Không tin một trường `approved=true` hoặc tên người duyệt do client tùy ý gửi lên. Kiểm tra và cập nhật trạng thái phải tránh tình huống yêu cầu bị đổi nội dung trong lúc phê duyệt.

Nếu dùng một nền tảng workflow có sẵn, cần kiểm tra khả năng cấu hình của nền tảng đó thay vì tự thêm logic ở một giao diện phụ. Ẩn nút Approve trên màn hình không đủ nếu API phía sau vẫn cho phép gọi.

### 6.2. Bảo vệ cả đường đi ngoài pipeline

Một người không được bấm Deploy trong pipeline nhưng có quyền trực tiếp thay đổi workload production vẫn có thể triển khai bằng CLI hoặc API. Khi đó, chốt phê duyệt của pipeline chưa bao phủ đầy đủ đường thực hiện.

Cần kiểm tra đồng thời:

- Quyền của con người trên tài nguyên production.
- Quyền sử dụng hoặc thay đổi danh tính triển khai.
- Quyền sửa pipeline và quy tắc phê duyệt.
- Quyền thay artifact hoặc biến cấu hình sau phê duyệt.
- Quyền sửa membership của các group có quyền trên những thành phần này.

Không có nghĩa phải loại bỏ mọi truy cập vận hành trực tiếp. Các thao tác sửa sự cố có thể cần thiết, nhưng phải được thiết kế như một đường truy cập có chủ sở hữu, phạm vi và bằng chứng rõ ràng.

### 6.3. Kiểm soát ngoại lệ và truy cập khẩn cấp

Một tổ chức nhỏ có thể chưa đủ người để tách mọi nhiệm vụ. Khi cần ngoại lệ, nên xác định rõ người chấp thuận độc lập, thời gian áp dụng, phạm vi tác động và hoạt động rà soát sau đó. Ngoại lệ lâu dài không được ghi nhận dễ trở thành mô hình quyền mặc định.

Các tài khoản hoặc group quản trị mạnh nên được quản lý theo cơ chế truy cập đặc quyền của tổ chức. Oracle khuyến nghị không dùng tài khoản quản trị toàn tenancy cho công việc hằng ngày và ủy quyền theo trách nhiệm. Xem [Security: OCI Administrators Group](https://docs.oracle.com/en-us/iaas/Content/Identity/conversion/security.htm).

Phân tách trách nhiệm không được làm mất khả năng phục hồi quyền quản trị. Không thực hành bằng cách xóa những nhóm quản trị được OCI bảo vệ hoặc thu hồi mọi đường quản trị của domain/tenancy.

## 7. Kiểm tra quyền hiệu lực trước khi kết luận đã phân tách

### 7.1. Đánh giá theo hệ thống đích

Không nên lập một phép cộng chung rồi coi mọi quyền OCI và quyền ứng dụng là cùng một tập được kiểm tra ở một nơi. Với từng thao tác, hãy xác định hệ thống quyết định quyền và những nguồn nó sử dụng.

| Thao tác cần kiểm tra | Đường quyền cần lần theo |
| --- | --- |
| Đọc thông tin instance | Danh tính, memberships, IAM policy, compartment và điều kiện liên quan |
| Quản lý danh tính | Administrator role của domain và các IAM policy liên quan |
| Theo dõi ứng dụng tích hợp | Role của đúng application/service instance, assignment và quyền chi tiết của tính năng |
| Duyệt yêu cầu phát hành | Quyền nghiệp vụ và điều kiện phê duyệt của workflow |
| Triển khai qua pipeline | Quyền kích hoạt, quy tắc phê duyệt, danh tính thực thi và policy tài nguyên |

Khi phân tích một user, cần tìm cả:

- Group được cấp trực tiếp hoặc được quản lý qua tích hợp danh tính.
- Assignment application role trực tiếp và qua các group khác nhau.
- Role quản trị identity domain.
- Policy rộng hơn ở compartment cha hoặc tenancy.
- Quyền trong chính ứng dụng và các cơ chế ủy quyền khác mà ứng dụng hỗ trợ.

OCI có IAM deny policies dưới dạng tính năng cần bật chủ động. Nếu tenancy đã dùng deny, phải xét cả deny khi kiểm tra quyền OCI. Tuy nhiên, deny không thay thế thiết kế mọi lớp quyền; tài liệu Oracle nêu deny policies không ghi đè identity domain administration roles. Xem [Deny Policies](https://docs.oracle.com/en-us/iaas/Content/Identity/policysyntax/denypolicies.htm) và [Deny Policies Known Issues](https://docs.oracle.com/en-us/iaas/Content/Identity/known-issues/known-issues-deny-policies.htm).

### 7.2. Dùng phép thử có quyền và không có quyền

Kiểm thử chỉ có tình huống thành công sẽ bỏ sót quyền thừa. Ví dụ, tài khoản đọc Compute cần đọc được instance trong phạm vi lab, đồng thời không đọc được instance ngoài phạm vi nếu không có grant khác.

Phải dùng tài khoản đại diện cho bộ quyền dự kiến. Tài khoản thuộc nhóm quản trị toàn tenancy không phải công cụ thích hợp để chứng minh người dùng hạn chế đã bị chặn.

Không dùng mỗi việc một nút bị ẩn hoặc một danh sách rỗng để chứng minh không có quyền. Cần kiểm tra đúng thao tác, định danh tài nguyên, compartment, region và application instance. Thông báo không tìm thấy tài nguyên có thể liên quan đến cả quyền lẫn định danh hoặc vị trí sai.

## 8. Thực hành: tách quyền Compute, application role và phê duyệt

### 8.1. Chuẩn bị phạm vi lab

Chuẩn bị:

- Một identity domain được phép sử dụng cho bài học.
- Tài khoản quản trị thiết lập lab và hai tài khoản kiểm thử không có quyền quản trị rộng.
- Một compartment lab cùng một instance mẫu đã biết OCID.
- Một instance mẫu khác trong compartment lab ngoài phạm vi cấp quyền để thử truy cập bị từ chối.
- Nếu thực hành application role: một Oracle application/service instance có sẵn và được phép thử, cùng tài liệu role của dịch vụ đó.

Không cần tạo dịch vụ trả phí chỉ để kiểm tra phần application role. Nếu môi trường chưa có ứng dụng phù hợp, có thể làm phần thiết kế assignment và ghi rõ chưa kiểm chứng đường quyền ứng dụng.

Nếu một người dùng hai tài khoản để học cách kiểm thử, đó là mô phỏng các vai trò. Kết quả này chưa chứng minh tổ chức đã có hai người độc lập thực hiện nhiệm vụ.

### 8.2. Tạo group và ghi nhận assignment dự kiến

Tạo hai group trong đúng domain:

| Group lab | Assignment dự kiến |
| --- | --- |
| `LabComputeReaders` | IAM policy đọc instance trong compartment lab được giao |
| `LabAppMonitors` | Application role giám sát của đúng ứng dụng thử nghiệm |

Trên Console, mở domain, vào khu vực quản lý Groups và tạo group với tên, mô tả rõ ràng. Sau đó thêm từng tài khoản kiểm thử vào group tương ứng. Không chọn group có sẵn chỉ vì tên gần giống nếu chưa xác minh chủ sở hữu và các assignment đang có. Xem [Creating a Group](https://docs.oracle.com/en-us/iaas/Content/Identity/groups/create-groups.htm).

Bảng trạng thái ban đầu nên thể hiện:

```text
lab-reader  -> LabComputeReaders
lab-monitor -> LabAppMonitors

lab-reader:
  không có role ứng dụng giám sát qua đường khác

lab-monitor:
  không có policy đọc Compute qua group hoặc quyền rộng khác
```

Đây là trạng thái cần kiểm tra, không phải điều tự động được bảo đảm bởi tên tài khoản.

### 8.3. Gán policy OCI đúng phạm vi

Người có trách nhiệm quản lý policy tạo statement sau tại nơi gắn policy phù hợp:

```text
Allow group 'LearningDomain'/'LabComputeReaders' to read instances in compartment id <LAB_COMPARTMENT_OCID>
```

Thay `LearningDomain` và placeholder bằng giá trị của lab. Dùng compartment riêng của bài học; không mở rộng thành `in tenancy` chỉ để bỏ qua lỗi thiếu quyền.

Nếu người đọc dùng Console nhưng không thấy bộ chọn hoặc thông tin phụ thuộc cần thiết, hãy phân tích từng yêu cầu còn thiếu. Không biến một grant phục vụ quan sát thành `manage all-resources`.

### 8.4. Gán application role cho group riêng

Với ứng dụng được phép thực hành:

1. Xác nhận đúng identity domain và đúng đối tượng ứng dụng hoặc service instance.
2. Mở phần quản lý application roles của ứng dụng đó.
3. Chọn một role giám sát hoặc chỉ xem thực sự được dịch vụ hỗ trợ.
4. Gán group `LabAppMonitors` vào role theo luồng quản trị của dịch vụ.
5. Kiểm tra danh sách group và user được gán trực tiếp.
6. Đăng nhập bằng `lab-monitor` để xác minh chức năng được phép và chức năng bị hạn chế.

Nếu dùng Oracle Integration, có thể xem xét `ServiceMonitor` theo phạm vi tính năng của môi trường đang có. Không tự tạo role tên `Monitor` hoặc đổi thành `ServiceAdministrator` chỉ vì chưa tìm thấy màn hình tương ứng.

Gán group cho ứng dụng và gán group cho application role là những thao tác cần phân biệt theo mô hình của dịch vụ. Quy trình lab phải kiểm tra role thực tế được cấp, thay vì chỉ ghi rằng “đã thêm group vào app”.

### 8.5. Thử truy cập OCI bằng đúng tài khoản

Có thể dùng OCI CLI profile đã cấu hình cho `lab-reader`. Các lệnh sau chỉ đọc thông tin:

```powershell
# Thay các placeholder bằng giá trị thật của lab.
oci compute instance get `
    --instance-id '<INSTANCE_TRONG_PHAM_VI_LAB>' `
    --region '<REGION_IDENTIFIER>' `
    --profile 'lab-reader'

# Kiểm tra tài nguyên mẫu ngoài phạm vi đã cấp.
oci compute instance get `
    --instance-id '<INSTANCE_LAB_NGOAI_PHAM_VI>' `
    --region '<REGION_IDENTIFIER>' `
    --profile 'lab-reader'
```

Lệnh thứ nhất được kỳ vọng thành công khi grant đã có hiệu lực và mọi định danh đều đúng. Lệnh thứ hai được kỳ vọng bị từ chối theo mô hình lab không có grant ngoài phạm vi.

Để xác định nguyên nhân của phép thử bị từ chối, người quản trị đối chiếu rằng tài nguyên thật sự tồn tại ở region và compartment đã ghi. Không sửa policy thành quyền rộng trước khi kiểm tra các điều kiện này.

### 8.6. Kiểm tra cả ba phạm vi trách nhiệm

| Tình huống | Kết quả mong đợi theo thiết kế lab |
| --- | --- |
| `lab-reader` đọc instance trong phạm vi | Thành công |
| `lab-reader` đọc instance ngoài phạm vi | Bị từ chối nếu không có grant khác |
| `lab-reader` vào chức năng ứng dụng cần role giám sát | Không được cấp chỉ nhờ policy đọc Compute |
| `lab-monitor` dùng chức năng giám sát được giao | Thành công trong ứng dụng đã gán |
| `lab-monitor` đọc Compute khi không có policy tương ứng | Bị từ chối |
| Người tạo yêu cầu tự phê duyệt | Bị từ chối nếu workflow đã thực thi quy tắc SoD |
| Người khác có quyền phê duyệt duyệt đúng yêu cầu | Thành công nếu đủ điều kiện nghiệp vụ |
| Artifact bị đổi sau phê duyệt | Cần phê duyệt lại theo thiết kế quy trình |

Hai tình huống phê duyệt và tình huống artifact chỉ có thể kiểm chứng khi có workflow tương ứng. Việc tạo group trong OCI không tự triển khai các kiểm soát này.

Ghi lại bằng chứng riêng cho phần đã kiểm thử thực tế và phần mới hoàn thành thiết kế. Không đánh dấu đã kiểm chứng application role hoặc SoD chỉ từ kết quả đọc Compute.

## 9. Quản lý vòng đời cấp và thu hồi quyền

### 9.1. Cấp quyền theo yêu cầu có thể giải trình

Một yêu cầu truy cập nên nêu được:

- Người nhận quyền và danh tính/domain tương ứng.
- Công việc cần làm, hệ thống và môi trường liên quan.
- Group hoặc application role cần nhận.
- Người duyệt và người thực hiện thay đổi.
- Ngày bắt đầu, thời hạn nếu có và điều kiện thu hồi.
- Kết quả kiểm tra xung đột nhiệm vụ.

Tách người phê duyệt khỏi người thực hiện thay đổi giúp tránh việc thao tác kỹ thuật bị hiểu nhầm là quyết định nghiệp vụ. Người có thể thêm member chưa chắc là người có thẩm quyền đồng ý cấp quyền đó.

### 9.2. Thu hồi hết đường quyền liên quan

Khi một người chuyển vai trò hoặc rời dự án, thực hiện theo danh sách đường cấp quyền đã ghi nhận:

1. Cập nhật nguồn membership có thẩm quyền nếu có đồng bộ.
2. Thu hồi membership không còn cần thiết.
3. Kiểm tra application role gán trực tiếp và qua group khác.
4. Kiểm tra administrator role của identity domain.
5. Đánh giá session, token và credential liên quan theo loại truy cập.
6. Thử lại thao tác cần bị chặn sau khi thay đổi đã được áp dụng.
7. Lưu bằng chứng và đóng yêu cầu.

Xóa membership không đồng nghĩa hủy mọi session hoặc credential. Với OAuth, access token có thể được resource server xác minh mà không truy vấn lại identity domain; token sống lâu cần được xét trong kế hoạch thu hồi. Oracle khuyến nghị thiết kế thời hạn access token phù hợp và xử lý refresh token khi cần thu hồi kịp thời. Xem [Managing Authorization Using the API](https://docs.oracle.com/en-us/iaas/Content/Identity/api-getstarted/api-managing-authorization.htm).

Không áp dụng một thao tác “đăng xuất” chung cho mọi ứng dụng rồi kết luận toàn bộ quyền đã bị thu hồi. Session ứng dụng, session SSO và các loại credential có vòng đời khác nhau. Cần xác minh theo các đường truy cập mà người đó thực sự dùng.

Nếu chỉ thu hồi một nhiệm vụ nhưng người dùng vẫn tiếp tục làm công việc khác, tránh xóa tài khoản hoặc credential một cách tùy tiện. Phạm vi thu hồi phải phù hợp quyết định truy cập và tình huống xử lý.

### 9.3. Rà soát định kỳ và bằng chứng

Rà soát nên đối chiếu **người → group → policy/role → thao tác thực tế**, thay vì chỉ đếm số group. Đặc biệt kiểm tra các quyền trực tiếp, quyền khẩn cấp chưa được thu hồi và sự thay đổi quyền phía sau một group có sẵn.

Identity domain có báo cáo **Application Role Privileges** để xem việc cấp và thu hồi application role cho users và groups. Báo cáo Audit Log hỗ trợ xem các hoạt động quản trị và đăng nhập được ghi nhận. Xem [Types of Reports](https://docs.oracle.com/en-us/iaas/Content/Identity/reports/understand-types-reports.htm).

Bằng chứng hữu ích gồm người thực hiện, đối tượng thay đổi, trạng thái trước/sau, thời điểm, lý do và liên kết với phê duyệt. Đối với pipeline, cần liên kết thêm phiên bản cấu hình, artifact và danh tính thực thi. Không mặc định một nguồn log có thể chứng minh mọi thao tác ở tất cả hệ thống.

Nếu tổ chức đã triển khai công cụ access governance, có thể dùng nó để hỗ trợ rà soát và điều phối cấp quyền. Công cụ chỉ có giá trị khi thu thập đủ dữ liệu và quy tắc phản ánh đúng phạm vi công việc; việc tạo group không mặc nhiên bật một hệ thống governance như vậy.

## 10. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách điều chỉnh |
| --- | --- | --- |
| Coi group có tên `Admin` là một loại quyền cố định | Hiểu sai quyền thực tế | Lần theo policy và mọi role assignment |
| Dùng chung một group cho nhiều hệ thống không liên quan | Thêm member cho một việc làm mở nhiều quyền khác | Tách theo gói công việc và phạm vi có chủ sở hữu |
| Nhầm application role với IAM policy | Người dùng có quyền sai lớp hoặc vẫn không thực hiện được công việc | Xác định hệ thống nào quyết định từng thao tác |
| Tạo group Approver rồi cho rằng đã có SoD | Người tạo vẫn có thể tự duyệt qua ứng dụng hoặc API | Thực thi và kiểm thử điều kiện tại workflow |
| Chỉ kiểm tra tên tài khoản | Một người dùng nhiều tài khoản để kiêm nhiệm | Đối chiếu chủ thể thực khi yêu cầu hai người độc lập |
| Tách người triển khai nhưng không tách người sửa pipeline | Có thể bỏ qua chốt phê duyệt | Kiểm soát quyền thay đổi cơ chế thực thi |
| Xóa một membership rồi đóng yêu cầu thu hồi | Assignment trực tiếp hoặc đường khác còn tồn tại | Kiểm tra toàn bộ đường quyền liên quan |
| Thử quyền bằng tài khoản toàn quyền | Không phát hiện cấu hình cấp thừa hoặc thiếu cho user thường | Dùng danh tính đại diện đúng bộ quyền |
| Đồng nhất vai trò Audit administrator với mọi quyền đọc OCI | Người rà soát không có đúng bằng chứng hoặc có quyền thừa | Phân biệt báo cáo domain, tài nguyên OCI và dữ liệu ứng dụng |
| Chỉ yêu cầu MFA rồi coi như đã phân tách nhiệm vụ | Một người vẫn có thể tự thực hiện toàn bộ chuỗi hành động | Thiết kế riêng việc xác thực và việc tách trách nhiệm |

## 11. Tiêu chí hoàn tất thiết kế

Một thiết kế groups, application roles và SoD có thể được đưa vào vận hành khi:

- Mỗi group và role assignment có mục đích, phạm vi và chủ sở hữu.
- Mô hình phân biệt quyền OCI, quyền ứng dụng và quyền quản trị danh tính.
- Người quản trị membership/assignment được cấp quyền theo trách nhiệm đã phân tích.
- Các tổ hợp nhiệm vụ xung đột được xác định theo hệ thống, môi trường và nghiệp vụ.
- Kiểm soát tại thời điểm cấp quyền và tại thời điểm giao dịch được mô tả đúng nơi thực thi.
- Những đường thực hiện ngoài pipeline hoặc ngoài giao diện chính đã được đánh giá.
- Có phép thử thành công, phép thử bị từ chối và phép thử sau thu hồi quyền.
- Có quy trình ngoại lệ, truy cập khẩn cấp và rà soát bằng chứng.
- Phần mới thiết kế và phần đã kiểm chứng được ghi nhận rõ ràng.

Kết quả cần đạt là người dùng thực hiện được công việc của mình, trong khi những chuỗi hành động cần kiểm tra độc lập thực sự đòi hỏi sự tham gia độc lập. Group và application role là công cụ để biểu diễn, cấp và quản lý quyền; chất lượng phân tách nhiệm vụ phụ thuộc cả cách tổ chức quyền lẫn cách từng hệ thống thực thi quy trình.
