# Application identity

## 1. Ứng dụng cũng cần một danh tính

**Application identity** là danh tính bảo mật dùng để nhận diện một ứng dụng khi nó tương tác với hệ thống khác. Danh tính này giúp API, cơ sở dữ liệu hoặc dịch vụ hạ tầng xác định ứng dụng nào đang yêu cầu truy cập và áp dụng quyền phù hợp.

Ví dụ, dịch vụ lập hóa đơn cần đọc đơn hàng và ghi hóa đơn. Nó không nên đăng nhập bằng tài khoản cá nhân của lập trình viên hay dùng chung một tài khoản quản trị với các dịch vụ khác. Hệ thống cần nhận ra một principal dành cho dịch vụ lập hóa đơn và chỉ cấp những quyền phục vụ công việc đó.

Application identity thuộc phạm vi workload identity: chương trình đang chạy có thể cần chứng minh danh tính mà không có con người trực tiếp nhập mật khẩu. Một ứng dụng có thể có nhiều thành phần, môi trường và bản sao đang chạy; cách phân chia identity phải phản ánh ranh giới bảo mật thực tế.

Danh tính ứng dụng không đơn thuần là tên sản phẩm, tên thư mục hoặc tên container. Những nhãn đó chỉ có giá trị bảo mật khi được nền tảng xác minh và liên kết với một principal theo quy tắc tin cậy.

## 2. Tách định danh, credential và quyền

Ba thành phần thường bị nhầm lẫn khi cấu hình ứng dụng:

| Thành phần | Vai trò | Ví dụ khái niệm |
| --- | --- | --- |
| Identity hoặc principal | Chủ thể được hệ thống nhận diện | Danh tính của dịch vụ lập hóa đơn ở production |
| Credential hoặc bằng chứng xác thực | Giúp chứng minh quyền sử dụng identity | Chữ ký bằng khóa riêng, credential do nền tảng cấp hoặc token được liên kết tin cậy |
| Authorization policy | Quyết định identity được làm gì | Đọc đơn hàng của một hệ thống và ghi hóa đơn vào kho được chỉ định |

Client ID hay principal ID thường là định danh, không phải bí mật đủ để chứng minh ứng dụng. Ngược lại, client secret, khóa riêng hoặc token truy cập có thể là credential cần được bảo vệ.

Thay credential không nhất thiết tạo identity mới. Một ứng dụng có thể thay khóa để giữ cùng principal và cùng quyền. Ngược lại, tạo một principal khác nhưng sao chép toàn bộ credential và quyền rộng từ principal cũ không tạo ra sự cô lập có ý nghĩa.

Một access token thường là bằng chứng sử dụng quyền trong một khoảng thời gian và dành cho bên nhận cụ thể. Nó không thay thế toàn bộ hồ sơ quản trị của application identity, chẳng hạn chủ sở hữu, mục đích sử dụng, trạng thái và lịch sử cấp quyền.

## 3. Những lớp đối tượng có thể xuất hiện

Tùy nền tảng, khái niệm “ứng dụng” có thể được thể hiện bằng nhiều đối tượng:

| Lớp | Câu hỏi cần trả lời |
| --- | --- |
| Đăng ký ứng dụng | Đây là ứng dụng logic nào, dùng giao thức gì? |
| Principal tại một phạm vi quản trị | Ứng dụng được đại diện như thế nào trong tenant hoặc hệ thống này? |
| Workload đang chạy | Tiến trình hoặc môi trường nào được phép sử dụng principal đó? |
| Credential | Bằng chứng nào còn hiệu lực và được phát hành bằng cách nào? |
| Gán quyền | Principal được truy cập những tài nguyên nào? |

Ví dụ về thuật ngữ của một sản phẩm: Microsoft Entra phân biệt application object ở home tenant và service principal đại diện cho ứng dụng trong một tenant. Không nên dùng app/client ID và object ID của các đối tượng này như những giá trị có thể thay thế nhau. [Microsoft Learn: Application and service principal objects](https://learn.microsoft.com/en-us/entra/identity-platform/app-objects-and-service-principals)

Tên đối tượng và quan hệ cụ thể khác nhau giữa các nền tảng. Khi tích hợp, cần xác định chính xác ID nào được dùng để xác thực, ID nào dùng khi gán quyền và ID nào xuất hiện trong token hoặc audit log.

Một ứng dụng đa tenant cũng không mặc nhiên nhận cùng quyền tại mọi tenant. Việc tồn tại đối tượng đại diện và việc được cấp quyền truy cập tài nguyên là hai quyết định riêng của từng phạm vi quản trị.

## 4. Chọn ranh giới cho application identity

Nếu mọi dịch vụ đều dùng một principal `backend-admin`, hệ thống khó giới hạn tác động khi một dịch vụ bị xâm nhập. Audit log cũng không thể hiện rõ ứng dụng nghiệp vụ nào thực sự thực hiện thao tác.

Một phương án minh họa là tách theo chức năng và môi trường:

| Principal logic | Công việc | Giới hạn mong muốn |
| --- | --- | --- |
| `billing-api-prod` | Xử lý hóa đơn production | Đọc dữ liệu đơn hàng cần thiết và ghi kho hóa đơn production |
| `billing-api-test` | Kiểm thử tính năng lập hóa đơn | Chỉ truy cập tài nguyên test |
| `invoice-export-prod` | Xuất báo cáo hóa đơn | Đọc tập dữ liệu xuất báo cáo, không sửa hóa đơn |
| `deployment-pipeline-prod` | Triển khai phiên bản ứng dụng | Quyền triển khai được kiểm soát, không mặc nhiên là quyền nghiệp vụ runtime |

Các tên trong bảng chỉ minh họa cách đặt ranh giới. Chính sách thực tế cần được gắn với định danh mà hệ thống xác minh, không chỉ so khớp tên hiển thị có thể đổi.

Không nhất thiết tạo một principal lâu dài cho từng replica. Các replica cùng vai trò có thể chia sẻ identity logic nếu phù hợp mô hình tin cậy, trong khi vẫn có thông tin instance riêng để điều tra. Trường hợp có yêu cầu cô lập mạnh hơn, cần phân chia danh tính hoặc ràng buộc credential tương ứng.

IP, tên máy và image tag thường thay đổi khi autoscale hoặc triển khai lại. Chúng có thể là dữ liệu hỗ trợ, nhưng không nên tự trở thành bằng chứng duy nhất rằng một tiến trình được nhận application identity có đặc quyền.

## 5. Ứng dụng chứng minh danh tính bằng cách nào?

Cơ chế xác thực phụ thuộc nền tảng và giao thức, nhưng có thể nhận diện các hướng chính:

| Hướng | Cách chứng minh khái quát | Điều phải quản lý |
| --- | --- | --- |
| Shared secret | Ứng dụng trình bày bí mật đã được cấp | Phân phối, lưu giữ, thay thế và thu hồi secret |
| Khóa bất đối xứng hoặc chứng thư | Chứng minh khả năng sử dụng khóa riêng | Bảo vệ khóa, tin cậy bên cấp và vòng đời chứng thư |
| Identity do nền tảng quản lý | Nền tảng liên kết workload được phép với principal và cấp credential | Quyền gắn identity, tính tin cậy của môi trường chạy và endpoint cấp credential |
| Federation | Chấp nhận bằng chứng từ một issuer bên ngoài theo điều kiện đã cấu hình | Issuer, subject, audience và điều kiện ánh xạ đúng workload |

Trong OAuth 2.0, client credentials cho phép client xin access token bằng credential của nó hoặc cách xác thực được hỗ trợ để truy cập theo quyền đã sắp xếp trước. Grant này dành cho confidential client; không phải cách đặt client secret vào mã JavaScript hoặc ứng dụng người dùng rồi xem đó là bí mật an toàn. [RFC 6749, mục 4.4](https://www.rfc-editor.org/rfc/rfc6749.html#section-4.4)

Một luồng sử dụng identity có thể được hình dung như sau:

```text
Workload được triển khai trong môi trường được cho phép
  -> nền tảng hoặc dịch vụ danh tính xác minh điều kiện nhận identity
  -> workload nhận bằng chứng hoặc token có giới hạn
  -> workload trình bày bằng chứng cho tài nguyên đích
  -> bên nhận xác minh danh tính và kiểm tra quyền
```

Việc ứng dụng không giữ một mật khẩu tĩnh trong file cấu hình không có nghĩa nó không còn credential hoặc không còn ranh giới tin cậy. Credential vẫn có thể tồn tại trong bộ nhớ, được cấp qua endpoint của nền tảng hoặc được tạo từ một khóa cần bảo vệ.

Google Cloud khuyến nghị ưu tiên phương thức thay thế phù hợp để tránh các service account key do người dùng tự quản lý khi có thể, vì key bị lộ có thể được dùng để hành động bằng quyền của service account. Đây là một ví dụ cụ thể cho mục tiêu giảm phân phối credential dài hạn. [Google Cloud: Best practices for managing service account keys](https://docs.cloud.google.com/iam/docs/best-practices-for-managing-service-account-keys)

## 6. Vấn đề khởi tạo niềm tin

Một câu hỏi quan trọng là: trước khi ứng dụng có credential, hệ thống biết nó được nhận identity nào bằng cách nào?

Nếu chỉ cần gửi tên `billing-api-prod` để nhận token production, kẻ tấn công có thể tự gửi cùng tên. Hệ thống cần một cơ sở tin cậy như danh tính môi trường chạy, kết quả kiểm chứng workload hoặc bằng chứng từ issuer đã cấu hình.

Trong mô hình federation cho pipeline, chính sách có thể yêu cầu bằng chứng thuộc đúng tổ chức, repository, môi trường triển khai và audience. Chỉ tin issuer chung của cả nền tảng mà không giới hạn subject hoặc ngữ cảnh có thể khiến một workload khác cũng nhận được quyền production.

Trong môi trường container, một nhãn hoặc service account name có thể tham gia quyết định ánh xạ. Nhưng cần kiểm soát ai được triển khai workload với thuộc tính đó, ai được gắn identity và ai có thể lấy credential. Thuộc tính do bên không tin cậy tự đặt không tự trở thành bằng chứng đủ mạnh.

SPIFFE cung cấp một cách biểu diễn danh tính workload bằng SPIFFE ID và tài liệu có thể xác minh gọi là SVID, với dạng X.509 hoặc JWT. Identity và tài liệu chứng minh identity là các khái niệm riêng trong mô hình này. [SPIFFE Concepts](https://spiffe.io/docs/latest/spiffe-about/spiffe-concepts/)

Điểm cần rút ra khi thiết kế không nằm ở việc sao chép một tên URI. Cần xác định ai có thẩm quyền cấp bằng chứng, workload nào được nhận, bên nhận tin thẩm quyền đó bằng cách nào và điều kiện nào có thể bị người khác thao túng.

## 7. App-only và quyền được ủy quyền từ người dùng

Một ứng dụng có thể hoạt động bằng quyền của chính nó hoặc trong ngữ cảnh được ủy quyền từ người dùng. Hai trường hợp cần được phân biệt ở chính sách và audit:

| Trường hợp | Ngữ cảnh danh tính | Ví dụ |
| --- | --- | --- |
| App-only | Quyền được cấp cho ứng dụng theo mô hình áp dụng | Job đối soát chạy mỗi đêm |
| Delegated | Ứng dụng tham gia sử dụng quyền trong ngữ cảnh người dùng | Nhân viên mở ứng dụng để xem hóa đơn được phép xem |

Một job app-only không cần giả tạo một tài khoản người dùng tên “robot” rồi đăng nhập bằng mật khẩu của tài khoản đó. Cũng không nên suy luận có người dùng đã thực hiện MFA chỉ vì ứng dụng nhận được token hợp lệ.

Ở luồng delegated, việc người dùng có quyền rộng không đồng nghĩa ứng dụng được nhận toàn bộ quyền đó. API phải thực thi cả giới hạn của credential và chính sách áp dụng cho người dùng, client, tenant và tài nguyên.

Nếu một dịch vụ backend nhận request rồi gọi dịch vụ khác bằng identity của chính nó, bên nhận có thể chỉ thấy quyền của backend. Backend không được vô tình trở thành công cụ để người dùng quyền thấp thực hiện thao tác vượt quyền. Cần kiểm tra yêu cầu đầu vào và dùng cơ chế truyền hoặc trao đổi ngữ cảnh ủy quyền phù hợp khi nghiệp vụ đòi hỏi.

## 8. Phân quyền cho ứng dụng theo công việc

Với dịch vụ lập hóa đơn, nhóm thiết kế có thể bắt đầu từ các nhu cầu cụ thể:

```text
Ứng dụng: billing-api-prod

Cần:
  đọc các trường đơn hàng dùng để lập hóa đơn
  tạo và cập nhật hóa đơn trong phạm vi được giao
  ghi sự kiện xử lý vào nơi được chỉ định

Không có nhu cầu:
  quản trị người dùng
  thay đổi chính sách IAM
  đọc secret của dịch vụ khác
  truy cập dữ liệu test và production bằng cùng credential
```

Đây là bản mô tả nhu cầu, không phải cú pháp policy của một nhà cung cấp. Sau đó cần chuyển từng nhu cầu thành action, resource và điều kiện mà nền tảng thực thi được.

Có identity hợp lệ không thay thế kiểm tra quyền ở mức đối tượng. Nếu ứng dụng được phục vụ nhiều tenant, API vẫn cần kiểm tra tài nguyên đang truy cập thuộc tenant nào và principal được phép làm gì tại đó.

Quyền thay đổi credential, thêm liên kết federation, gắn identity vào workload hoặc triển khai mã mới dưới identity có đặc quyền đều nhạy cảm. Một người không có quyền đọc dữ liệu trực tiếp nhưng có thể triển khai mã tùy ý bằng principal đọc dữ liệu vẫn có thể đạt được khả năng tương đương.

Vì vậy, đánh giá quyền ứng dụng cần bao gồm cả đường quản trị identity và pipeline triển khai, thay vì chỉ liệt kê các role gắn ở resource server.

## 9. Quản lý vòng đời application identity

Application identity cần có chủ sở hữu và mục đích rõ ràng ngay từ khi tạo. Một hồ sơ quản trị hữu ích có thể ghi nhận tên logic, principal ID, môi trường, nhóm chịu trách nhiệm, tài nguyên được cấp quyền và cơ chế xác thực.

| Giai đoạn | Việc cần thực hiện |
| --- | --- |
| Tạo mới | Xác minh nhu cầu, chọn ranh giới identity và chỉ định chủ sở hữu |
| Cấp quyền | Gắn quyền tối thiểu, kiểm tra tài nguyên và điều kiện |
| Vận hành | Theo dõi sử dụng, lỗi cấp credential và quyền phát sinh |
| Thay credential | Triển khai bản mới, xác minh sử dụng rồi thu hồi bản cũ theo kế hoạch |
| Đổi mục đích hoặc chủ sở hữu | Xem xét lại quyền, liên kết tin cậy và trách nhiệm vận hành |
| Ngừng ứng dụng | Dừng cấp credential, gỡ quyền và liên kết theo thứ tự an toàn |

Thời hạn access token, thời hạn chứng thư và thời gian tồn tại principal là các mốc khác nhau. Tắt principal hoặc xóa một key không mặc nhiên khiến mọi access token đã phát hành bị từ chối ngay ở mọi API; cần hiểu cơ chế xác minh, cache và thu hồi của hệ thống.

Đối với credential ngắn hạn, ứng dụng cần có cơ chế làm mới và xử lý gián đoạn phù hợp. Khi dịch vụ cấp identity tạm thời không khả dụng, không nên tự chuyển sang một tài khoản quản trị hoặc secret dùng chung không nằm trong thiết kế.

Khi một ứng dụng bị loại bỏ, chỉ xóa mã nguồn hoặc container chưa đủ. Có thể vẫn còn principal, role assignment, credential, liên kết federation và quyền truy cập vào các kho dữ liệu cần được xử lý.

## 10. Audit, xử lý sự cố và kiểm chứng

Audit nên thể hiện principal đã xác minh, ứng dụng logic, môi trường, tài nguyên, hành động và kết quả. Thông tin deployment hoặc instance giúp điều tra bản sao nào đã thực hiện thao tác khi nhiều replica dùng cùng identity logic.

Không ghi client secret, khóa riêng hoặc token đầy đủ vào log. Trạng thái “xác thực thành công” cũng không đủ để chứng minh hành động hợp lệ: cần kết hợp với kết quả kiểm tra quyền và ngữ cảnh nghiệp vụ.

Khi nghi ngờ application identity bị xâm nhập, cần xác định đường kiểm soát đã bị mất: credential bị sao chép, workload bị chiếm, pipeline bị sửa hay chính sách cấp identity quá rộng. Thay secret sẽ không xử lý tận gốc nếu kẻ tấn công vẫn có quyền lấy credential mới hoặc triển khai mã dưới cùng principal.

Các tình huống sau giúp kiểm chứng thiết kế:

| Tình huống | Kết quả cần đạt |
| --- | --- |
| Workload test yêu cầu identity production | Bị từ chối theo ranh giới môi trường |
| Client chỉ biết client ID | Không tự chứng minh được danh tính bằng ID đó |
| Bằng chứng federation sai subject hoặc audience | Không nhận được identity có quyền |
| Ứng dụng hợp lệ gọi API không thuộc audience | Không được chấp nhận chỉ vì cùng issuer |
| Ứng dụng đọc tài nguyên ngoài phạm vi được cấp | Kiểm soát truy cập từ chối |
| Một replica mới được triển khai hợp lệ | Nhận đúng identity và quyền theo thiết kế |
| Credential được thay hoặc làm mới | Ứng dụng hoạt động theo kế hoạch, credential cũ được xử lý đúng |
| Principal ngừng sử dụng | Không tiếp tục được cấp quyền mới hoặc bị bỏ quên trong hạ tầng |
| Người không được phép muốn gắn identity đặc quyền | Đường quản trị và triển khai ngăn được thao tác |

Application identity giúp đưa ứng dụng và workload vào cùng một mô hình quản lý danh tính có trách nhiệm: có chủ thể rõ ràng, bằng chứng xác thực có nguồn tin cậy, quyền giới hạn theo công việc và vòng đời được quản trị. Mức an toàn phụ thuộc cả cách cấp identity lẫn cách tài nguyên thực thi quyền của nó.
