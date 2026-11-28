# System owner approval — Phê duyệt của chủ hệ thống trong PAM

## 1. Vì sao quyền đặc quyền cần chủ hệ thống phê duyệt?

Một kỹ sư có thể cần quyền quản trị để xử lý lỗi, nhưng việc kỹ sư đó thuộc đội vận hành không tự chứng minh rằng họ được phép thay đổi mọi hệ thống. Quyền quản trị có thể làm gián đoạn dịch vụ, thay đổi cấu hình bảo mật, truy cập dữ liệu nhạy cảm hoặc tạo ra đường truy cập tồn tại sau khi công việc kết thúc.

Trong quản lý truy cập đặc quyền (Privileged Access Management — PAM), **system owner approval** là quyết định của người hoặc vai trò được tổ chức giao thẩm quyền đối với một hệ thống, xác nhận rằng một yêu cầu truy cập cụ thể phù hợp với trách nhiệm và giới hạn của hệ thống đó.

Quyết định cần trả lời được:

- Người yêu cầu có lý do hợp lệ để thao tác trên hệ thống này không?
- Tài nguyên, hành động và mức quyền đề xuất có tương xứng với công việc không?
- Thời điểm và thời lượng truy cập có chấp nhận được về mặt vận hành không?
- Có cần thêm điều kiện về dữ liệu, giám sát, người đi cùng hoặc phê duyệt bổ sung không?
- Ai chịu trách nhiệm nếu quyết định vượt phạm vi hoặc tạo ra rủi ro không được xem xét?

Phê duyệt của chủ hệ thống là một phần của quyết định cấp quyền. Nó không thay thế xác thực danh tính, kiểm tra thiết bị, least privilege, chính sách tách biệt nhiệm vụ hoặc cơ chế thu hồi quyền.

Ví dụ, chủ dịch vụ thanh toán có thể đồng ý cho kỹ sư khởi động lại một dịch vụ trong cửa sổ bảo trì. Quyết định đó không mặc nhiên cho phép kỹ sư xuất dữ liệu khách hàng, chỉnh chính sách IAM hoặc nhận mật khẩu quản trị để sử dụng ngoài PAM.

## 2. Phân biệt chủ hệ thống với các vai trò liên quan

### 2.1. Chủ hệ thống là một thẩm quyền được xác lập

Chủ hệ thống là vai trò chịu trách nhiệm về hệ thống theo mô hình quản trị của tổ chức. Người giữ vai trò có thể đến từ đội sản phẩm, vận hành hoặc đơn vị nghiệp vụ; tên chức danh không quan trọng bằng việc thẩm quyền được ghi nhận rõ ràng.

Không nên suy ra chủ hệ thống chỉ từ:

- Người từng triển khai máy chủ.
- Tài khoản hiện có quyền administrator.
- Người trả lời email nhanh nhất.
- Quản lý trực tiếp của người yêu cầu.
- Người có quyền chỉnh sửa cấu hình workflow PAM.
- Nhãn tài nguyên do chính người yêu cầu có thể tự sửa.

Một chủ hệ thống cần có phạm vi quản lý cụ thể và đủ thông tin để đánh giá tác động của truy cập. Nếu thẩm quyền trong hồ sơ tài sản không rõ ràng, workflow thường phải chuyển sang tuyến xác minh hoặc xử lý ngoại lệ đã định nghĩa, thay vì tự chọn một người có chức danh gần giống.

### 2.2. Các quyết định khác nhau không thay thế lẫn nhau

| Vai trò | Trọng tâm quyết định | Điều không tự động được suy ra |
|---|---|---|
| Quản lý trực tiếp | Người yêu cầu có nhiệm vụ và lý do công việc phù hợp hay không | Có quyền chấp thuận thay đổi trên mọi hệ thống |
| Chủ hệ thống | Tác động, phạm vi và điều kiện truy cập đối với hệ thống mình phụ trách | Có thể bỏ qua mọi chính sách bảo mật hoặc dữ liệu |
| Chủ dữ liệu | Điều kiện truy cập và sử dụng dữ liệu thuộc phạm vi quản lý | Có thể tự cấp quyền quản trị hạ tầng |
| Đội an toàn thông tin | Rủi ro, kiểm soát bổ sung và ngoại lệ theo thẩm quyền | Phê duyệt thay cho chủ hệ thống trong mọi trường hợp |
| Người điều phối thay đổi | Cửa sổ, phụ thuộc và quy trình triển khai thay đổi | Ticket đã được duyệt đồng nghĩa quyền PAM đã được duyệt |
| Quản trị viên nền tảng PAM | Vận hành cơ chế yêu cầu, cấp quyền và thu hồi | Được tự phê duyệt mọi yêu cầu mà mình có thể cấu hình |

Một người có thể giữ nhiều vai trò, nhưng tổ chức phải quy định khi nào việc kiêm nhiệm được chấp nhận. Nếu chính sách yêu cầu hai người độc lập, hai lần bấm duyệt của cùng một người dưới hai vai trò không đáp ứng yêu cầu.

### 2.3. Không phê duyệt vượt thẩm quyền

Chủ hệ thống có thể phê duyệt trong phạm vi được giao. Họ không tự có quyền cho phép mọi hành động trên hệ thống đó.

Ví dụ:

- Chủ ứng dụng có thể phê duyệt thao tác restart nhưng việc đọc bảng chứa dữ liệu nhạy cảm cần thêm chủ dữ liệu.
- Chủ cụm máy chủ có thể chấp thuận bảo trì hạ tầng nhưng không tự phê duyệt việc vô hiệu hóa ghi log theo một chính sách do cấp khác quản lý.
- Người phụ trách môi trường thử nghiệm không mặc nhiên là người có thẩm quyền trên môi trường production.

Phê duyệt đúng người nhưng sai phạm vi vẫn là quyết định không hợp lệ.

## 3. Xác định chủ hệ thống từ nguồn có thẩm quyền

### 3.1. Hồ sơ sở hữu tối thiểu

Mỗi tài nguyên hoặc nhóm tài nguyên cần có thông tin đủ để định tuyến yêu cầu:

| Thuộc tính | Mục đích |
|---|---|
| Định danh hệ thống hoặc tài nguyên ổn định | Tránh nhầm tên hiển thị, tên cũ hoặc tài nguyên trùng tên |
| Môi trường và mức quan trọng | Phân biệt production, staging, development và phạm vi rủi ro |
| Chủ hệ thống hoặc nhóm sở hữu | Xác định tuyến phê duyệt có thẩm quyền |
| Phạm vi được phê duyệt | Nêu loại tài nguyên và quyền mà vai trò được phép chấp thuận |
| Người dự phòng hoặc quy tắc ủy quyền | Giải quyết vắng mặt mà không chọn người tùy tiện |
| Thời hạn và trạng thái phân công | Không dùng quyền phê duyệt đã hết hiệu lực |
| Nguồn và phiên bản hồ sơ | Hỗ trợ truy vết việc định tuyến tại thời điểm quyết định |

Nguồn có thể là hệ thống quản lý tài sản, danh mục dịch vụ hoặc một kho phân công trách nhiệm được quản trị. Điều quan trọng là có chủ thể chịu trách nhiệm cập nhật, kiểm soát thay đổi và khả năng xác minh nguồn đó.

### 3.2. Không tin dữ liệu định tuyến do người yêu cầu tự khai

Người yêu cầu có thể đề xuất hệ thống hoặc cung cấp thông tin liên hệ, nhưng không nên được tự quyết định ai là người phê duyệt hợp lệ.

Một lỗi thường gặp là cho nhập tùy ý địa chỉ email người duyệt rồi coi bất kỳ phản hồi đồng ý nào là đủ. Cách này cho phép chuyển yêu cầu đến người không có trách nhiệm hoặc đồng nghiệp cùng nhóm.

Workflow nên phân giải tài nguyên trước, sau đó tìm thẩm quyền từ hồ sơ sở hữu và chính sách. Nếu cho phép người yêu cầu chọn trong danh sách, danh sách đó phải được giới hạn bởi nguồn có thẩm quyền.

### 3.3. Nhóm tài nguyên động cần ranh giới rõ

Yêu cầu “quyền trên tất cả máy có nhãn payments” có thể đổi phạm vi sau khi phê duyệt nếu có máy mới được thêm nhãn.

Có hai cách thiết kế thường gặp:

- Phê duyệt một tập tài nguyên đã chốt; cấp quyền chỉ cho các định danh nằm trong tập đó.
- Phê duyệt một quy tắc chọn tài nguyên được quản trị, với ranh giới và cơ chế đánh giá thay đổi được quy định rõ.

Không được để một nhãn dễ sửa trở thành cách mở rộng quyền ngoài ý định của người duyệt. Khi tập đích thay đổi đáng kể, phải đánh giá lại theo chính sách; không mặc nhiên coi phê duyệt cũ bao phủ mọi tài nguyên mới.

### 3.4. Thay đổi chủ sở hữu khi yêu cầu đang chờ

Nếu người phụ trách chuyển vị trí hoặc hệ thống đổi chủ sở hữu:

- Yêu cầu chưa được quyết định cần được định tuyến lại.
- Quyết định đã có cần được kiểm tra tính còn hiệu lực theo chính sách hiện hành trước khi kích hoạt.
- Các yêu cầu đang hoạt động có thể cần thu hồi hoặc đánh giá lại nếu việc thay đổi chủ sở hữu kéo theo thay đổi rủi ro hoặc thẩm quyền.
- Bằng chứng cũ phải giữ nguyên người đã quyết định và thẩm quyền tại thời điểm đó.

Không ghi đè tên người duyệt trong lịch sử bằng tên chủ hệ thống mới. Lịch sử cần phản ánh đúng sự kiện đã xảy ra.

## 4. Chủ hệ thống cần thấy gì trước khi quyết định?

Một màn hình chỉ có tên người dùng và nút “Approve” không cung cấp đủ thông tin cho một quyết định có trách nhiệm.

### 4.1. Hồ sơ yêu cầu

Thông tin cốt lõi bao gồm:

- Danh tính người yêu cầu, tổ chức hoặc nhà cung cấp, người thực sự thao tác.
- Hệ thống, môi trường và tài nguyên cụ thể.
- Vai trò, entitlement hoặc tập hành động được yêu cầu.
- Lý do nghiệp vụ và tham chiếu ticket hoặc sự cố.
- Thời điểm bắt đầu, kết thúc, múi giờ và thời lượng.
- Phương thức truy cập: phiên qua proxy, chạy tác vụ được giới hạn hay checkout credential.
- Các điều kiện về ghi nhận phiên, thiết bị, mạng và xác thực.
- Thay đổi dự kiến, ảnh hưởng dịch vụ và phương án phục hồi nếu có.
- Các cảnh báo rủi ro hoặc xung đột nhiệm vụ đã được phát hiện.

Không cần đưa bí mật vào hồ sơ phê duyệt. Người duyệt cần biết mức quyền và cách kiểm soát credential, không cần nhìn thấy mật khẩu để ra quyết định.

### 4.2. Phạm vi phải hiểu được về mặt nghiệp vụ

Tên role kỹ thuật có thể không đủ rõ. Một role tên “operations-admin” nên được diễn giải thành các khả năng quan trọng, chẳng hạn:

- Đọc trạng thái và log.
- Khởi động lại dịch vụ.
- Sửa cấu hình.
- Đọc dữ liệu nghiệp vụ.
- Tạo tài khoản hoặc cấp thêm quyền.
- Truy cập credential hoặc thay đổi logging.

Việc diễn giải giúp người duyệt nhận ra quyền vượt nhu cầu. Nếu yêu cầu chỉ là restart, role có thể xuất dữ liệu và cấp quyền cho người khác cần được thu hẹp hoặc giải thích rõ.

Quyết định phù hợp thường là một tập quyền nhỏ hơn, thông qua JEA hoặc tác vụ định sẵn, thay vì cấp một shell toàn quyền chỉ vì đó là đường thao tác quen thuộc.

### 4.3. Thời gian và cơ chế kết thúc

Chủ hệ thống cần biết quyền sẽ kết thúc như thế nào:

- Đến hạn thì từ chối mở phiên mới hay cả phiên đang chạy đều bị xử lý?
- Entitlement tạm thời có được xóa trên đích không?
- Credential có hết hiệu lực hoặc được thay đổi không?
- Có công việc nền được phép tiếp tục sau khi người dùng hết quyền không?
- Ai nhận cảnh báo nếu thu hồi thất bại?

Một yêu cầu ghi “truy cập một giờ” nhưng không có cơ chế hạn chế quyền trên đích chưa phản ánh đầy đủ rủi ro. Chủ hệ thống có thể phê duyệt có điều kiện, nhưng các điều kiện bắt buộc phải được hệ thống thực thi hoặc xác minh trước khi cấp quyền.

## 5. Quyết định phê duyệt phải gắn với phiên bản yêu cầu

### 5.1. Phê duyệt một nội dung cụ thể

Giả sử người duyệt đồng ý với:

~~~text
Người thao tác: engineer-17
Tài nguyên: payments-app-01, payments-app-02
Hành động: đọc trạng thái và restart dịch vụ
Khoảng truy cập: 22:00–23:00
Phương thức: phiên PAM có ghi nhận hoạt động
~~~

Sau đó người yêu cầu sửa thành “toàn bộ máy production, full admin, từ 22:00 đến 06:00”. Phê duyệt cũ không được tái sử dụng cho nội dung mới.

Một quyết định nên liên kết tối thiểu với định danh yêu cầu, phiên bản yêu cầu và phạm vi đã duyệt. Hệ thống có thể thêm bản băm của biểu diễn chuẩn hóa để phát hiện thay đổi, nhưng bản băm không thay thế xác thực người duyệt, kiểm tra thẩm quyền hoặc bảo vệ bản ghi quyết định.

### 5.2. Thay đổi nào cần đánh giá lại?

Thông thường các thay đổi sau có ý nghĩa đối với quyết định:

| Thay đổi | Lý do cần xem xét |
|---|---|
| Thêm tài nguyên hoặc đổi môi trường | Mở rộng vùng tác động |
| Tăng quyền hoặc cho checkout credential | Tăng khả năng thao tác và nguy cơ sử dụng ngoài phiên |
| Kéo dài thời gian hoặc dời sang cửa sổ khác | Thay đổi thời gian phơi nhiễm và điều kiện vận hành |
| Đổi người thao tác | Phê duyệt danh tính cũ không tự chuyển cho danh tính mới |
| Bỏ ghi nhận phiên hoặc điều kiện thiết bị | Giảm kiểm soát đã được người duyệt dựa vào |
| Thay đổi lý do hoặc ticket liên quan | Cơ sở nghiệp vụ có thể không còn phù hợp |

Ngay cả việc thu hẹp phạm vi cũng cần một quy tắc rõ: có thể được phép nếu nằm hoàn toàn trong giới hạn đã duyệt và chính sách cho phép, hoặc phải tạo phiên bản mới và duyệt lại. Không tự suy ra quan hệ “ít quyền hơn” từ tên role; hai role khác tên có thể chứa những khả năng khác nhau.

### 5.3. Không tái sử dụng quyết định quá hạn

Phê duyệt có thể có hạn sử dụng riêng, ngoài cửa sổ truy cập. Nếu yêu cầu chưa được kích hoạt sau khoảng chờ cho phép, hệ thống cần đánh giá lại để tránh dùng một quyết định đã cũ trong bối cảnh mới.

Gia hạn truy cập là thay đổi quyền. Trạng thái “đang xin gia hạn” không kéo dài quyền hiện tại, và một comment của người yêu cầu không thay thế quyết định mới của người có thẩm quyền.

## 6. Tách biệt nhiệm vụ và phê duyệt nhiều bên

### 6.1. Chặn tự phê duyệt

Nếu người yêu cầu đồng thời là chủ hệ thống, workflow không nên tự mặc định người đó có thể duyệt chính yêu cầu của mình.

Một chính sách tách biệt nhiệm vụ có thể yêu cầu:

- Người duyệt là một cá nhân khác với người yêu cầu và người thực hiện.
- Người có quyền cấu hình workflow không được dùng quyền đó để tự tạo tuyến duyệt cho mình.
- Ủy quyền không được làm mất tính độc lập bắt buộc.
- Xung đột được phát hiện trước khi cấp quyền, không chỉ khi kiểm toán sau sự kiện.

Trong tổ chức nhỏ, có thể không luôn đủ người để tạo mọi lớp độc lập mong muốn. Trường hợp này cần một tuyến ngoại lệ đã được tổ chức chấp nhận, có phạm vi hạn chế, giám sát và hậu kiểm. Không âm thầm đổi “hai người” thành “một người bấm hai lần”.

### 6.2. Phân biệt đồng thuận theo vai trò với số người duyệt

Ví dụ chính sách yêu cầu:

~~~text
Một người thuộc vai trò chủ hệ thống
VÀ
Một người thuộc vai trò an toàn thông tin
VÀ
Hai người này phải là hai cá nhân khác nhau
~~~

Nếu một người thuộc cả hai nhóm, một quyết định của họ không đủ. Điều kiện theo vai trò và điều kiện số người độc lập phải được đánh giá riêng.

Với nhóm nhiều chủ hệ thống, chính sách cần nói rõ:

- Một thành viên hợp lệ có thể quyết định thay cho nhóm hay cần nhiều người?
- Quyết định từ chối của một người có chặn toàn bộ yêu cầu không?
- Có ai được quyền thay đổi quyết định, trong điều kiện nào?
- Thông báo được gửi cho cả nhóm hay một người được phân công chịu trách nhiệm?

Không dùng số lượng thông báo đã gửi làm bằng chứng rằng đã có đủ số phê duyệt.

### 6.3. Nhiều hệ thống trong một yêu cầu

Nếu yêu cầu truy cập cả ứng dụng và cơ sở dữ liệu với chủ sở hữu khác nhau, cần có một tuyến bao phủ toàn bộ tập tài nguyên.

Có thể chọn một trong hai mô hình đã được quy định:

- Chỉ cấp toàn bộ khi mọi nhánh bắt buộc đều đạt.
- Chia thành các yêu cầu con, chỉ cấp phần đã được duyệt và thể hiện rõ phần chưa được duyệt.

Không để một chủ hệ thống duyệt một tài nguyên rồi hệ thống cấp quyền cho mọi tài nguyên trong yêu cầu. Nếu dùng cấp quyền một phần, người thao tác và người duyệt phải thấy rõ phạm vi thực tế để tránh hiểu nhầm.

## 7. Luồng tham chiếu từ yêu cầu đến thu hồi

~~~mermaid
flowchart TD
    A[Tạo yêu cầu với phạm vi và thời gian] --> B[Phân giải tài nguyên và thẩm quyền]
    B --> C{Có tuyến duyệt hợp lệ?}
    C -- Không --> D[Chặn luồng thường và xử lý định tuyến]
    C -- Có --> E[Chủ hệ thống đánh giá phiên bản yêu cầu]
    E --> F{Quyết định}
    F -- Yêu cầu bổ sung --> G[Cập nhật yêu cầu và tạo phiên bản phù hợp]
    G --> B
    F -- Từ chối --> H[Đóng yêu cầu và ghi lý do]
    F -- Chấp thuận --> I[Kiểm tra các phê duyệt và điều kiện bắt buộc]
    I --> J[Đánh giá lại trước lúc kích hoạt]
    J --> K{Quyết định còn hợp lệ?}
    K -- Không --> L[Từ chối kích hoạt hoặc yêu cầu duyệt lại]
    K -- Có --> M[Cấp quyền JIT có giới hạn]
    M --> N[Giám sát và thu hồi khi hết hạn hoặc bị hủy]
    N --> O[Xác minh kết quả và lưu bằng chứng]
~~~

### 7.1. Trạng thái phê duyệt khác trạng thái cấp quyền

Một mô hình trạng thái đơn giản có thể gồm:

| Trạng thái | Ý nghĩa |
|---|---|
| DRAFT | Chưa gửi yêu cầu |
| PENDING_APPROVAL | Đang chờ các quyết định bắt buộc |
| NEEDS_INFORMATION | Chưa đủ thông tin để quyết định |
| REJECTED | Yêu cầu bị từ chối |
| APPROVED | Phiên bản yêu cầu đã đủ phê duyệt, chưa khẳng định đã có quyền |
| ACTIVE | Quyền thực tế đã được cấp và còn hiệu lực |
| EXPIRED hoặc CANCELLED | Không còn được kích hoạt theo yêu cầu cũ |
| REVOCATION_PENDING | Đã yêu cầu kết thúc nhưng chưa xác minh thu hồi hoàn tất |
| CLOSED | Hoàn tất quy trình theo điều kiện đóng đã định nghĩa |

Tên trạng thái chỉ là minh họa. Một triển khai có thể dùng các trạng thái khác, nhưng cần tách rõ quyết định, cấp quyền và kết quả thu hồi.

Nếu provisioning thất bại, không báo cho người dùng rằng quyền đang hoạt động chỉ vì phê duyệt đã xong. Ngược lại, nếu thu hồi thất bại, không đánh dấu CLOSED như thể quyền đã biến mất.

### 7.2. Kiểm tra lại trước khi kích hoạt

Khoảng thời gian giữa phê duyệt và sử dụng có thể phát sinh thay đổi:

- Người dùng bị khóa hoặc ngừng hợp đồng.
- Ticket bị hủy.
- Phê duyệt hết hạn hoặc bị thu hồi.
- Tập tài nguyên hoặc vai trò thay đổi.
- Chính sách mới yêu cầu thêm một phê duyệt.
- Điều kiện thiết bị hoặc rủi ro không còn đạt.

Do đó cần đánh giá lại tại thời điểm cấp quyền. Quyết định phê duyệt hợp lệ là một đầu vào; nó không phải một token cho phép bỏ qua mọi điều kiện về sau.

### 7.3. Hủy và thu hồi

Chủ hệ thống có thể cần hủy yêu cầu trước khi kích hoạt hoặc đề nghị chấm dứt quyền đang hoạt động theo thẩm quyền. Hệ thống phải phân biệt:

- Thu hồi quyết định cho lần kích hoạt chưa xảy ra.
- Ngăn phiên mới.
- Kết thúc hoặc hạn chế phiên hiện hữu theo chính sách.
- Xóa entitlement trên đích.
- Thu hồi hoặc thay đổi credential liên quan.
- Xác minh trạng thái thực tế sau các hành động đó.

Một trường “approval_revoked” không tự đóng mọi phiên hoặc vô hiệu hóa credential đã phát hành.

## 8. Ủy quyền, vắng mặt và thời hạn xử lý

### 8.1. Ủy quyền có giới hạn

Ủy quyền giúp hệ thống vận hành khi chủ hệ thống vắng mặt. Một bản ghi ủy quyền nên nêu:

- Người hoặc vai trò ủy quyền và người nhận.
- Hệ thống, môi trường và loại quyền được bao phủ.
- Thời điểm bắt đầu, kết thúc.
- Mức rủi ro hoặc giới hạn mà người nhận được phép duyệt.
- Có cho phép ủy quyền tiếp hay không.
- Yêu cầu độc lập với người yêu cầu.
- Cơ sở tạo, thay đổi và thu hồi ủy quyền.

Khi người được ủy quyền quyết định, bằng chứng phải ghi danh tính của họ và liên kết tới thẩm quyền ủy quyền. Không ghi như thể chủ hệ thống gốc đã trực tiếp bấm duyệt.

### 8.2. SLA là thời hạn phản hồi, không phải quyền tự duyệt

Nếu chủ hệ thống không phản hồi trong thời hạn vận hành, workflow có thể nhắc việc hoặc chuyển tuyến đến người dự phòng có thẩm quyền.

Hết thời gian chờ không tự biến yêu cầu thành chấp thuận. Các lựa chọn phù hợp phải được định nghĩa trước, chẳng hạn:

- Chuyển đến nhóm chủ sở hữu dự phòng.
- Hết hạn yêu cầu để người dùng tạo yêu cầu phù hợp hơn.
- Chuyển sang tuyến ngoại lệ theo mức độ khẩn cấp.
- Từ chối kích hoạt nếu không có đủ phê duyệt.

Không chuyển tự động sang một nhóm quản trị viên rộng chỉ vì nhóm đó dễ phản hồi.

### 8.3. Không tìm thấy chủ hệ thống

Đây là vấn đề chất lượng hồ sơ và trách nhiệm quản trị, không phải cơ sở để bỏ qua phê duyệt.

Hệ thống nên giữ yêu cầu chưa được cấp, thông báo rõ nguyên nhân và chuyển đến tuyến có trách nhiệm xác minh sở hữu. Việc sửa hồ sơ sở hữu cần có kiểm soát riêng; người yêu cầu không nên được tự gán chủ mới rồi lập tức dùng người đó để duyệt yêu cầu đang chờ.

## 9. An toàn của hành động phê duyệt

### 9.1. Xác thực và quyền thực hiện quyết định

Một hành động phê duyệt cần được xử lý phía máy chủ với danh tính đã xác thực và kiểm tra quyền trên đúng yêu cầu.

Thông báo email hoặc ứng dụng nhắn tin có thể dùng để dẫn người duyệt đến giao diện chính thức. Nếu hệ thống hỗ trợ quyết định trực tiếp từ thông báo, cơ chế đó phải bảo đảm danh tính, tính toàn vẹn, thời hạn và việc chống sử dụng lại. Không coi việc sở hữu một liên kết có thể chuyển tiếp là đủ bằng chứng về thẩm quyền.

Đối với quyền rủi ro cao, chính sách có thể yêu cầu xác thực bổ sung tại lúc quyết định. Yêu cầu này cần tương xứng với rủi ro, không phải một cấu hình bắt buộc giống nhau cho mọi tình huống.

### 9.2. Mã giả kiểm tra quyết định

Mã giả sau minh họa logic, không phải API của một sản phẩm PAM cụ thể:

~~~text
approve(actor, request_id, expected_revision, decision):
    authenticate(actor)

    request = load_request(request_id)

    require(request.state == PENDING_APPROVAL)
    require(request.revision == expected_revision)
    require(request.not_expired)

    authority = resolve_current_authority(
        actor,
        request.targets,
        request.requested_capabilities
    )

    require(authority.covers_required_scope)
    require(delegation_is_valid_if_used(authority))
    require(separation_of_duties_is_satisfied(actor, request))

    record_decision_atomically(
        request_id,
        expected_revision,
        actor,
        authority_reference,
        decision,
        trusted_server_time
    )

    evaluate_required_approval_routes_for_same_revision()
~~~

Trong triển khai thực tế, việc kiểm tra phiên bản và ghi quyết định cần tránh khoảng đua với một thay đổi yêu cầu hoặc quyết định hủy. Có thể dùng giao dịch, kiểm soát phiên bản hoặc cơ chế tương đương phù hợp với kiến trúc.

Lệnh phê duyệt gửi lại do lỗi mạng phải được xử lý nhất quán. Không để một lần retry tạo ra hai người duyệt giả hoặc hai lần cấp quyền. Thông báo phê duyệt cũng cần gắn đúng phiên bản; một liên kết cũ không được quyết định cho nội dung mới mà không hiển thị và kiểm tra lại.

### 9.3. Chính sách minh họa

Cấu hình dưới đây chỉ diễn đạt ý định thiết kế:

~~~yaml
approval_policy:
  resource_scope: "payments-production"
  required_routes:
    - role: "system-owner"
      minimum_decisions: 1
    - role: "security-reviewer"
      minimum_decisions: 1
  separation:
    requester_cannot_approve: true
    executor_cannot_approve: true
    distinct_people_across_routes: true
  binding:
    request_revision_required: true
    target_scope_must_match: true
    capability_scope_must_match: true
    access_window_must_match: true
  delegation:
    active_assignment_required: true
    scope_check_required: true
  activation:
    reevaluate_before_grant: true
    approval_is_not_provisioning: true
  timeout:
    action: "escalate-to-authorized-backup"
    automatic_approval: false
~~~

Không sao chép cấu hình này như một tiêu chuẩn phổ quát. Hệ thống ít rủi ro có thể có tuyến khác, còn truy cập dữ liệu hoặc quyền đặc biệt nhạy cảm có thể cần nhiều quyết định hơn.

## 10. Truy cập lặp lại và tình huống khẩn cấp

### 10.1. Tránh phê duyệt hình thức do quá nhiều yêu cầu

Nếu một chủ hệ thống phải bấm duyệt hàng trăm tác vụ giống nhau mỗi ngày, họ dễ chuyển sang phê duyệt máy móc.

Có thể giảm tải bằng cách:

- Thu hẹp thành các tác vụ định sẵn có quyền tối thiểu.
- Xác lập tiêu chí đủ điều kiện cho công việc thường xuyên.
- Cho chủ hệ thống phê duyệt một chính sách hoặc mẫu truy cập có giới hạn, nếu mô hình quản trị cho phép.
- Tự động đánh giá từng lần sử dụng theo chính sách còn hiệu lực.
- Yêu cầu duyệt riêng khi vượt phạm vi, thời gian hoặc mức rủi ro của mẫu.
- Định kỳ xem lại mẫu, người đủ điều kiện và kết quả sử dụng.

Cần phân biệt rõ **phê duyệt chính sách trước** với **phê duyệt thủ công từng yêu cầu**. Không ghi người chủ hệ thống là người trực tiếp duyệt một lần truy cập nếu thực tế lần đó được hệ thống tự động cho phép theo chính sách đã ban hành.

Tự động hóa không nên biến mẫu “restart một dịch vụ” thành quyền quản trị thường trực. Mỗi lần cấp vẫn cần giới hạn, khả năng truy vết và cơ chế thu hồi.

### 10.2. Break-glass là một tuyến riêng

Trong sự cố nghiêm trọng, không thể luôn chờ tuyến phê duyệt thông thường. Tổ chức có thể có quy trình break-glass được chấp thuận trước, xác định:

- Ai được kích hoạt.
- Hệ thống và quyền nào được bao phủ.
- Điều kiện chứng minh tính khẩn cấp.
- Thời hạn ngắn và cách kết thúc quyền.
- Thông báo cho chủ hệ thống và bên giám sát.
- Bằng chứng sử dụng và trách nhiệm hậu kiểm.

Phê duyệt hoặc xác nhận sau sự cố không được ghi lùi thời gian như thể đã có trước lúc cấp quyền. Bằng chứng phải thể hiện đúng rằng truy cập được thực hiện theo cơ chế khẩn cấp, ai kích hoạt và ai xem xét sau đó.

Nếu khẩn cấp bị dùng thường xuyên cho công việc có thể dự kiến, cần xem lại quy trình và năng lực vận hành thay vì coi đó là cách thông thường để né thời gian chờ.

## 11. Bằng chứng kiểm toán và trách nhiệm sau phê duyệt

### 11.1. Một chuỗi bằng chứng xuyên suốt

Một quyết định nên có các thông tin sau:

| Nhóm | Dữ liệu cần lưu |
|---|---|
| Yêu cầu | ID, phiên bản, người yêu cầu, người thực hiện, lý do và ticket |
| Phạm vi | Định danh tài nguyên, môi trường, quyền, phương thức và khoảng thời gian |
| Thẩm quyền | Vai trò chủ hệ thống, nguồn phân công, phạm vi và ủy quyền nếu có |
| Quyết định | Danh tính người duyệt, thời điểm máy chủ, chấp thuận hoặc từ chối, lý do và điều kiện |
| Chính sách | Phiên bản chính sách, các tuyến bắt buộc và kết quả kiểm tra độc lập |
| Cấp quyền | Entitlement, lease hoặc session liên quan; thời điểm và kết quả cấp |
| Kết thúc | Hết hạn, hủy hoặc thu hồi; kết quả xác minh trên điểm thực thi |

Bản ghi cần được bảo vệ khỏi sửa đổi trái phép và có cơ chế phát hiện thay đổi phù hợp. Quyền đọc bằng chứng cũng cần kiểm soát vì lý do công việc, log phiên và danh sách tài nguyên có thể nhạy cảm.

Không lưu credential có thể dùng lại trong comment phê duyệt. Nếu cần trao đổi thông tin bổ sung, dùng tham chiếu đến nơi lưu phù hợp thay vì chép bí mật vào ticket.

### 11.2. Không nhầm chấp thuận rủi ro với miễn trách nhiệm thực thi

Người duyệt chịu trách nhiệm về quyết định trong phạm vi thẩm quyền. Đội PAM và các điểm thực thi vẫn chịu trách nhiệm cấp đúng quyền, đúng hạn và thu hồi đúng cơ chế.

Nếu người duyệt đồng ý một giờ nhưng hệ thống cấp quyền không thời hạn, đó không phải là việc người duyệt đã “chấp nhận” quyền vĩnh viễn. Điều kiện đã duyệt và thực tế cấp quyền phải được đối chiếu.

Chủ hệ thống cũng cần xem lại định kỳ:

- Danh sách người được phép yêu cầu các quyền nhạy cảm.
- Quyền tạm thời không được thu hồi hoàn tất.
- Các mẫu truy cập và ủy quyền vẫn còn phù hợp.
- Yêu cầu lặp lại hoặc gia hạn nhiều lần.
- Các lần break-glass và kết quả hậu kiểm.

### 11.3. Chỉ số có ý nghĩa

Có thể theo dõi thời gian phản hồi và tỷ lệ yêu cầu bị định tuyến sai để cải thiện quy trình. Đồng thời cần theo dõi các chỉ số phản ánh chất lượng kiểm soát:

- Số lần chặn tự phê duyệt hoặc sai thẩm quyền.
- Số yêu cầu thay đổi phạm vi sau khi đã có quyết định.
- Số lần kích hoạt bị chặn vì quyết định cũ không còn hợp lệ.
- Số quyền thực cấp khác với phạm vi đã duyệt.
- Số lần quá hạn thu hồi hoặc thiếu bằng chứng kết thúc.
- Tỷ lệ sử dụng ngoại lệ và break-glass.

Thời gian phê duyệt rất ngắn không tự chứng minh quy trình hiệu quả; nó có thể là dấu hiệu người duyệt không xem xét đầy đủ. Chỉ số cần được đọc cùng mức rủi ro và chất lượng hồ sơ, không dùng để ép mọi yêu cầu thành “duyệt càng nhanh càng tốt”.

## 12. Tình huống: kỹ sư nhà cung cấp sửa dịch vụ thanh toán

Một nhà cung cấp yêu cầu quyền full administrator trên toàn bộ cụm production trong bốn giờ để sửa lỗi kết nối.

Chủ hệ thống xem hồ sơ và phát hiện:

- Lỗi được khoanh vùng ở hai máy ứng dụng.
- Công việc dự kiến chỉ cần đọc trạng thái và restart một dịch vụ.
- Không cần đọc dữ liệu khách hàng hoặc sửa cơ sở dữ liệu.
- Nhóm cung cấp đã có tài khoản định danh riêng, không cần dùng chung tài khoản cá nhân.
- Thời lượng bốn giờ chưa có cơ sở rõ ràng.

Chủ hệ thống không nên chấp thuận yêu cầu rộng rồi chỉ ghi comment “hãy dùng cẩn thận”. Họ yêu cầu cập nhật thành hai tài nguyên cụ thể, tập hành động giới hạn và cửa sổ một giờ. Hồ sơ mới có phiên bản mới, và các quyết định được gắn vào phiên bản đó.

Trong tổ chức này, truy cập production của nhà cung cấp còn cần một người thuộc vai trò an toàn thông tin độc lập. Chỉ sau khi cả hai tuyến đạt, yêu cầu mới ở trạng thái APPROVED.

Đến giờ truy cập, PAM kiểm tra lại tài khoản, cửa sổ, ticket, phạm vi và điều kiện thiết bị trước khi cấp quyền JIT. Người dùng thao tác qua phiên được giám sát, không được nhận một mật khẩu quản trị dùng lại tùy ý.

Trong lúc làm việc, kỹ sư phát hiện có thể cần sửa cấu hình cơ sở dữ liệu. Quyền hiện tại không bao phủ hành động đó. Họ phải tạo thay đổi phạm vi và lấy các quyết định tương ứng, bao gồm tuyến của chủ hệ thống cơ sở dữ liệu nếu chính sách yêu cầu. Sự tồn tại của ticket ban đầu không tự mở rộng quyền.

Khi công việc kết thúc, quyền tạm thời được thu hồi và kết quả được xác minh. Hồ sơ cuối liên kết được từ yêu cầu ban đầu, lần thu hẹp phạm vi, các quyết định, phiên thực tế đến bằng chứng kết thúc.

Bài học từ tình huống này là chủ hệ thống tạo ra một ranh giới quyền có thể thực thi. Giá trị của phê duyệt nằm ở phạm vi và điều kiện rõ ràng, không chỉ ở việc lưu một dấu “đã đồng ý”.

## 13. Kiểm chứng workflow trước khi vận hành

Kiểm thử cần bao phủ quyết định phía máy chủ và quyền thực tế, không chỉ nút trên giao diện.

| Tình huống | Kết quả cần đạt |
|---|---|
| Người yêu cầu tự gọi API duyệt chính mình | Bị chặn theo chính sách tách biệt nhiệm vụ |
| Một người có hai vai trò nhưng cần hai cá nhân | Không được tính là đủ hai người |
| Người không còn thuộc nhóm chủ hệ thống | Không được thực hiện quyết định mới |
| Người được ủy quyền đã hết hạn | Không thể phê duyệt theo ủy quyền cũ |
| Chủ hệ thống chỉ phụ trách staging | Không duyệt được quyền production ngoài phạm vi |
| Thay đổi tài nguyên sau khi có phê duyệt | Quyết định cũ không âm thầm bao phủ phạm vi mới |
| Gửi lại quyết định cho phiên bản cũ | Bị từ chối hoặc yêu cầu xem lại phiên bản hiện hành |
| Liên kết thông báo bị chuyển tiếp | Không đủ để người không có thẩm quyền quyết định |
| Hai thao tác duyệt và hủy xảy ra gần đồng thời | Trạng thái cuối nhất quán, không cấp quyền từ quyết định đã mất hiệu lực |
| Chỉ một trong nhiều hệ thống được duyệt | Không cấp toàn bộ ngoài mô hình đã định nghĩa |
| Hết SLA nhưng không có người duyệt | Nhắc hoặc chuyển tuyến hợp lệ, không tự chấp thuận |
| Đã duyệt nhưng ticket bị hủy trước kích hoạt | Không cấp quyền theo quyết định cũ |
| Cấp quyền trên đích thất bại | Không báo ACTIVE sai thực tế |
| Thu hồi quyền trên đích thất bại | Giữ trạng thái cần xử lý và phát cảnh báo |
| Sử dụng break-glass | Ghi đúng tuyến khẩn cấp và hậu kiểm, không giả lập phê duyệt trước |

Có thể bắt đầu với một tập hệ thống nhỏ có hồ sơ sở hữu rõ, quan sát việc định tuyến và đối chiếu cấp quyền thực tế. Mở rộng khi đã giải quyết được các trường hợp vắng mặt, xung đột vai trò, thay đổi yêu cầu và lỗi thu hồi.

Một workflow phê duyệt tốt bảo đảm người có đúng thẩm quyền quyết định trên đúng phiên bản yêu cầu, trong phạm vi có thể hiểu và kiểm soát. PAM phải biến quyết định đó thành quyền tối thiểu có thời hạn, đồng thời giữ đủ bằng chứng để xác minh cả việc cấp lẫn kết thúc quyền.
