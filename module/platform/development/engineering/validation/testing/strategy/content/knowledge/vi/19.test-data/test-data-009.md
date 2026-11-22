# Xác định quyền truy cập, trách nhiệm quản lý và giới hạn chia sẻ

Dữ liệu kiểm thử thường đi qua nhiều vai trò và công cụ: người phân tích yêu cầu, lập trình viên, kỹ sư kiểm thử, nhóm vận hành, nhà cung cấp dịch vụ và hệ thống CI. Nếu không xác định rõ ai được xem, tạo, sửa, sao chép hoặc chia sẻ dữ liệu, nhóm có thể vô tình để lộ thông tin nhạy cảm, dùng dữ liệu sai mục đích hoặc làm mất khả năng truy nguyên.

Quản lý dữ liệu kiểm thử vì vậy cần ba quyết định gắn với nhau: **ai được truy cập**, **ai chịu trách nhiệm quản lý**, và **dữ liệu được phép đi đâu, trong điều kiện nào**. Quyền truy cập phải phù hợp với công việc; trách nhiệm phải có chủ sở hữu rõ; giới hạn chia sẻ phải được xác định theo mức độ nhạy cảm, mục đích sử dụng, môi trường và yêu cầu của tổ chức.

## 1. Vì sao cần quản lý quyền và giới hạn chia sẻ?

Dữ liệu kiểm thử có thể chứa hoặc suy ra thông tin về khách hàng, nhân viên, giao dịch, tài khoản, sức khỏe, vị trí, tài chính, cấu hình hệ thống hoặc hoạt động nội bộ. Ngay cả khi dữ liệu được sao chép sang môi trường thử nghiệm, nó vẫn có thể giữ nguyên giá trị nhạy cảm như dữ liệu ban đầu.

Rủi ro không chỉ đến từ việc một người không có quyền đọc dữ liệu. Một tài khoản hợp lệ nhưng có quyền quá rộng, một bản export được gửi qua kênh không được phép, hoặc một bộ dữ liệu tồn tại lâu sau khi dự án kết thúc đều có thể tạo ra sự cố.

Quản lý quyền và chia sẻ tốt giúp:

- Chỉ người cần dữ liệu để thực hiện nhiệm vụ mới được truy cập.
- Giảm khả năng lộ dữ liệu qua bản sao, log, ảnh chụp màn hình, artifact hoặc công cụ bên ngoài.
- Biết ai chịu trách nhiệm phê duyệt, cấp quyền, rà soát và thu hồi.
- Duy trì tính toàn vẹn và khả năng truy nguyên của dữ liệu kiểm thử.
- Đáp ứng yêu cầu bảo mật, quyền riêng tư, hợp đồng và chính sách lưu trữ.
- Giảm thời gian điều tra khi có truy cập bất thường hoặc chia sẻ nhầm.

Nguyên tắc áp dụng cho cả dữ liệu tổng hợp, dữ liệu giả lập và dữ liệu được lấy từ production. Dữ liệu tổng hợp có thể ít nhạy cảm hơn, nhưng vẫn cần kiểm soát nếu chứa bí mật, thông tin nội bộ hoặc cấu trúc có thể tiết lộ thiết kế hệ thống.

## 2. Phân loại dữ liệu trước khi cấp quyền

Không thể xác định quyền truy cập hợp lý nếu chưa biết dữ liệu cần bảo vệ ở mức nào. Nhóm nên phân loại dữ liệu theo chính sách của tổ chức và xem xét nội dung, khả năng nhận diện, tác động nếu bị lộ, nghĩa vụ hợp đồng và mục đích sử dụng.

Một cách phân loại minh họa:

| Nhóm dữ liệu | Ví dụ | Cách xử lý thường cần cân nhắc |
| --- | --- | --- |
| Công khai | Nội dung đã được phép công bố, dữ liệu demo công khai | Có thể chia sẻ rộng theo giấy phép và điều kiện sử dụng |
| Nội bộ | Mã sản phẩm thử nghiệm, cấu hình không nhạy cảm, dữ liệu tổng hợp nội bộ | Chỉ chia sẻ trong tổ chức hoặc nhóm được phép |
| Mật | Dữ liệu kinh doanh, báo cáo nội bộ, thông tin vận hành chưa công bố | Hạn chế theo vai trò và mục đích; kiểm soát export và lưu trữ |
| Nhạy cảm cao | Thông tin cá nhân, dữ liệu tài chính, thông tin xác thực, dữ liệu sức khỏe hoặc bí mật thương mại quan trọng | Truy cập tối thiểu, phê duyệt rõ, bảo vệ tăng cường và theo dõi chặt |

Đây là ví dụ phân loại, không thay thế hệ thống phân loại chính thức của tổ chức. Nếu tổ chức có nhãn như Restricted, Confidential hoặc Internal, phải dùng đúng định nghĩa và quy trình tương ứng.

### Phân loại theo khả năng nhận diện

Với dữ liệu liên quan đến cá nhân, cần xem xét liệu một người có thể được nhận diện trực tiếp hoặc gián tiếp hay không:

- **Dữ liệu nhận diện trực tiếp:** tên, số điện thoại, email, số định danh hoặc địa chỉ cụ thể.
- **Dữ liệu có thể nhận diện gián tiếp:** tổ hợp ngày sinh, địa điểm, nghề nghiệp, thời điểm giao dịch hoặc thuộc tính hiếm.
- **Dữ liệu giả danh (pseudonymized):** thông tin nhận diện được thay bằng mã hoặc giá trị thay thế, nhưng vẫn có thể liên kết lại nếu còn khóa hoặc bảng ánh xạ.
- **Dữ liệu ẩn danh (anonymized):** đã xử lý để không thể nhận diện cá nhân bằng các phương tiện hợp lý trong bối cảnh sử dụng; cần đánh giá nguy cơ tái nhận diện chứ không chỉ xóa tên.

Giả danh hóa không đồng nghĩa với ẩn danh hóa. Nếu còn bảng ánh xạ hoặc có thể liên kết với dữ liệu khác, dữ liệu vẫn cần được bảo vệ theo mức phù hợp. Việc loại bỏ tên nhưng giữ ngày sinh, địa chỉ và lịch sử giao dịch chi tiết có thể vẫn cho phép nhận diện.

### Phân loại toàn bộ bản sao và đầu ra

Phân loại không chỉ áp dụng cho database nguồn. Cần xem cả:

- File CSV, JSON, dump database và bản backup.
- Ảnh chụp màn hình, video kiểm thử và báo cáo lỗi.
- Log, trace, request/response và dữ liệu telemetry.
- Artifact do CI tạo ra, báo cáo coverage và file đính kèm.
- Bản sao trên máy cá nhân, thư mục chia sẻ, chat hoặc công cụ cộng tác.
- Dữ liệu trong môi trường sandbox, staging, demo và đào tạo.

Nếu một artifact chứa dữ liệu nhạy cảm, nó phải được kiểm soát theo mức nhạy cảm đó dù được tạo tự động hoặc chỉ dùng tạm thời.

## 3. Xác định mục đích và mức dữ liệu cần dùng

Trước khi yêu cầu truy cập hoặc chia sẻ dữ liệu, hãy xác định mục đích cụ thể. Ví dụ: kiểm thử quy tắc tính phí, tái hiện lỗi, xác minh migration, kiểm tra phân quyền hoặc đánh giá hiệu năng.

Chỉ dùng các trường và số lượng bản ghi cần thiết cho mục đích đó. Đây là nguyên tắc tối thiểu hóa dữ liệu (data minimization). Nếu kiểm thử chỉ cần xác minh định dạng số tiền và trạng thái giao dịch, có thể dùng dữ liệu tổng hợp thay vì sao chép tên, địa chỉ và thông tin liên hệ của khách hàng.

Các câu hỏi nên trả lời trước khi cấp quyền:

1. Mục đích kiểm thử cụ thể là gì?
2. Dữ liệu nào hoặc trường nào là bắt buộc?
3. Có thể dùng dữ liệu tổng hợp, giả lập, giả danh hoặc dữ liệu đã che thông tin không?
4. Số lượng bản ghi và khoảng thời gian cần thiết là bao nhiêu?
5. Ai cần truy cập và trong bao lâu?
6. Dữ liệu sẽ được lưu ở đâu, qua công cụ nào và có được export không?
7. Khi nào dữ liệu phải được xóa hoặc quyền phải được thu hồi?

Không nên yêu cầu quyền truy cập toàn bộ production chỉ vì việc lấy một tập dữ liệu nhỏ thuận tiện hơn. Mục đích càng cụ thể thì quyền và phạm vi dữ liệu càng dễ giới hạn.

## 4. Phân định vai trò và trách nhiệm quản lý

Quản lý dữ liệu cần phân biệt người quyết định mục đích, người quản lý nghiệp vụ, người vận hành kỹ thuật và người sử dụng dữ liệu. Tên vai trò có thể khác nhau giữa tổ chức, nhưng trách nhiệm không nên bị bỏ trống.

| Vai trò | Trách nhiệm chính | Ví dụ quyết định hoặc công việc |
| --- | --- | --- |
| Data owner / Chủ sở hữu dữ liệu | Chịu trách nhiệm về mục đích, mức phân loại, quyền sử dụng và quyết định chia sẻ | Phê duyệt mục đích dùng dữ liệu khách hàng cho một hoạt động kiểm thử |
| Data steward / Người quản lý dữ liệu | Duy trì định nghĩa, chất lượng, nhãn, quy tắc sử dụng và vòng đời dữ liệu | Xác nhận trường nào cần che, bộ dữ liệu nào còn hiệu lực |
| Data custodian / Đơn vị lưu giữ kỹ thuật | Bảo vệ hạ tầng, lưu trữ, sao lưu, quyền kỹ thuật và nhật ký | Cấp quyền database theo phê duyệt, cấu hình mã hóa và backup |
| Người yêu cầu dữ liệu | Nêu mục đích, phạm vi, người dùng, thời hạn và biện pháp cần thiết | Tạo yêu cầu cấp dữ liệu kiểm thử cho một dự án |
| Người phê duyệt | Xác nhận quyền và chia sẻ theo thẩm quyền | Phê duyệt truy cập dữ liệu nhạy cảm hoặc chia sẻ cho nhà cung cấp |
| Người sử dụng dữ liệu | Dùng đúng mục đích, bảo vệ bản sao và báo cáo sự cố | Chỉ truy vấn các trường cần thiết, không tự gửi file ra ngoài |
| Security / Privacy / Compliance | Tư vấn hoặc kiểm tra yêu cầu bảo mật, quyền riêng tư, hợp đồng và quy định | Đánh giá rủi ro chia sẻ dữ liệu với bên thứ ba |

Một người có thể giữ nhiều vai trò ở nhóm nhỏ, nhưng phải xác định rõ ai có quyền quyết định và ai thực hiện. Người vận hành database không mặc nhiên là người có quyền phê duyệt mục đích sử dụng dữ liệu. Người kiểm thử có quyền đọc một bộ dữ liệu cũng không mặc nhiên có quyền chia sẻ bộ dữ liệu đó cho người khác.

### Chủ sở hữu dữ liệu và chủ sở hữu hệ thống

Chủ sở hữu hệ thống chịu trách nhiệm về ứng dụng hoặc nền tảng; chủ sở hữu dữ liệu chịu trách nhiệm về việc sử dụng dữ liệu theo mục đích và quy tắc đã xác định. Hai vai trò có thể thuộc cùng một nhóm nhưng không nên giả định chúng luôn trùng nhau.

Ví dụ, nhóm thanh toán sở hữu dịch vụ xử lý giao dịch nhưng dữ liệu khách hàng có thể do bộ phận dữ liệu hoặc nghiệp vụ khác quản lý. Muốn đưa một tập dữ liệu vào môi trường kiểm thử, nhóm cần đáp ứng cả yêu cầu kỹ thuật của hệ thống và thẩm quyền sử dụng dữ liệu.

## 5. Áp dụng nguyên tắc quyền tối thiểu

Nguyên tắc quyền tối thiểu (least privilege) yêu cầu mỗi người, tài khoản dịch vụ hoặc công cụ chỉ có những quyền cần thiết để hoàn thành nhiệm vụ được giao, trong phạm vi và thời gian phù hợp.

Quyền nên được giới hạn theo nhiều chiều:

- **Đối tượng:** database, schema, bảng, bucket, file, topic hoặc tập dữ liệu cụ thể.
- **Hành động:** đọc, tạo, sửa, xóa, export, chia sẻ hoặc quản trị.
- **Phạm vi bản ghi/trường:** chỉ các bản ghi hoặc cột cần thiết.
- **Môi trường:** development, test, staging hoặc production.
- **Thời gian:** quyền thường trực theo vai trò hoặc quyền tạm thời có ngày hết hạn.
- **Ngữ cảnh:** thiết bị, mạng, vị trí truy cập hoặc điều kiện xác thực theo chính sách.

Không nên cấp quyền quản trị nếu người dùng chỉ cần đọc dữ liệu kiểm thử. Tương tự, quyền đọc database không nhất thiết bao gồm quyền export toàn bộ dữ liệu hoặc tạo bản sao trên thiết bị cá nhân.

### Role-based access control (RBAC)

RBAC gán quyền cho vai trò, sau đó gán người dùng vào vai trò phù hợp. Ví dụ:

| Vai trò | Quyền minh họa |
| --- | --- |
| Test data viewer | Đọc bộ dữ liệu tổng hợp đã được phê duyệt trong môi trường test |
| Test data contributor | Tạo và cập nhật dữ liệu kiểm thử trong namespace được phân công |
| Test data steward | Quản lý metadata, nhãn, chất lượng và vòng đời bộ dữ liệu |
| Test environment operator | Quản lý cấu hình lưu trữ và cấp quyền kỹ thuật theo phê duyệt |
| Data approver | Phê duyệt mục đích, phạm vi hoặc yêu cầu chia sẻ theo thẩm quyền |

RBAC dễ quản lý khi trách nhiệm tương đối ổn định. Tuy nhiên, một vai trò quá rộng có thể cấp quyền vượt nhu cầu cho một dự án cụ thể.

### Attribute-based access control (ABAC)

ABAC quyết định quyền dựa trên thuộc tính của người dùng, dữ liệu, hành động và ngữ cảnh. Ví dụ, một kỹ sư kiểm thử có thể đọc bộ dữ liệu giả danh khi:

- Thuộc nhóm dự án được phê duyệt.
- Truy cập từ thiết bị được quản lý.
- Dùng môi trường test đã đăng ký.
- Mục đích truy cập nằm trong thời hạn cho phép.
- Bộ dữ liệu có nhãn phù hợp với vai trò.

RBAC và ABAC có thể được kết hợp. Dù dùng mô hình nào, quy tắc cần được kiểm tra ở nơi dữ liệu được truy cập; ẩn nút trên giao diện không thay thế kiểm soát ở API, database hoặc kho lưu trữ.

## 6. Quản lý danh tính và tài khoản dịch vụ

Truy cập dữ liệu kiểm thử không chỉ do con người thực hiện. CI runner, test automation, migration job, script tạo dữ liệu và service account cũng có thể đọc hoặc ghi dữ liệu.

Các nguyên tắc cần áp dụng:

- Dùng danh tính riêng cho từng ứng dụng hoặc pipeline khi phù hợp, tránh dùng chung tài khoản cá nhân.
- Không nhúng mật khẩu, token hoặc khóa truy cập trực tiếp vào mã nguồn, file test hoặc artifact.
- Lưu bí mật trong secret manager hoặc cơ chế quản lý được tổ chức phê duyệt.
- Cấp quyền theo đúng môi trường và tác vụ; tài khoản chạy test không nên có quyền production nếu không có nhu cầu và phê duyệt riêng.
- Xoay vòng, thu hồi hoặc vô hiệu hóa thông tin xác thực khi hết hạn, thay đổi nhân sự hoặc nghi ngờ bị lộ.
- Ghi nhận chủ sở hữu kỹ thuật và mục đích của từng service account.

Tài khoản dùng chung làm giảm khả năng truy nguyên vì log khó xác định ai hoặc pipeline nào đã thực hiện hành động. Nếu không thể tránh tài khoản kỹ thuật dùng chung trong một thành phần cũ, cần có biện pháp bổ sung để liên kết mỗi hoạt động với job, người khởi chạy và thời điểm.

### Quyền tạm thời và quyền khẩn cấp

Quyền tạm thời (just-in-time access) chỉ được cấp khi có nhu cầu cụ thể và tự hết hiệu lực hoặc được rà soát sau thời hạn. Quyền khẩn cấp cần có quy trình riêng: lý do, người phê duyệt, thời gian, phạm vi, giám sát và rà soát sau khi sử dụng.

Không nên giữ quyền khẩn cấp thành quyền thường trực. Sau khi xử lý sự cố hoặc hoàn tất điều tra, cần thu hồi quyền tăng cường và xác nhận các bản sao dữ liệu được tạo trong quá trình đó đã được quản lý đúng.

## 7. Xác định giới hạn chia sẻ theo người nhận và kênh

Chia sẻ dữ liệu là việc làm cho người hoặc hệ thống khác có thể truy cập dữ liệu, dù bằng cách gửi file, cấp quyền thư mục, cung cấp API, tạo bản sao hay hiển thị trong công cụ. Mỗi hình thức đều cần được xem xét.

### Chia sẻ nội bộ

Chia sẻ trong cùng tổ chức vẫn phải theo mục đích và mức phân loại. Một nhóm phát triển không mặc nhiên được xem dữ liệu của mọi nhóm nghiệp vụ. Cần xác định:

- Nhóm nhận có nhiệm vụ cần dữ liệu không?
- Có thể chia sẻ một tập dữ liệu nhỏ hơn hoặc chỉ các trường cần thiết không?
- Người nhận có môi trường lưu trữ và quyền truy cập phù hợp không?
- Có thời hạn chia sẻ và người chịu trách nhiệm thu hồi không?

### Chia sẻ với nhà cung cấp hoặc bên thứ ba

Trước khi chia sẻ ra ngoài tổ chức, cần xác minh thẩm quyền và điều kiện hợp đồng. Có thể phải đánh giá:

- Mục đích xử lý và loại dữ liệu được phép chuyển.
- Vai trò và trách nhiệm của bên nhận, bên xử lý và bên kiểm soát dữ liệu theo thỏa thuận áp dụng.
- Địa điểm lưu trữ, khu vực xử lý và luồng chuyển dữ liệu.
- Biện pháp bảo vệ, mã hóa, kiểm soát nhân sự và nhật ký truy cập.
- Thời hạn lưu, cách xóa và xác nhận xóa khi kết thúc.
- Quyền sử dụng tiếp, tạo bản sao hoặc chuyển tiếp cho nhà thầu phụ.
- Cơ chế thông báo và phối hợp khi có sự cố.

Không gửi dữ liệu thật cho nhà cung cấp chỉ vì họ có thể hỗ trợ kiểm thử. Ưu tiên dữ liệu tổng hợp hoặc dữ liệu đã được xử lý phù hợp. Nếu vẫn cần dữ liệu nhạy cảm, phải có căn cứ, phê duyệt và biện pháp bảo vệ theo chính sách và yêu cầu pháp lý/hợp đồng liên quan.

### Chia sẻ qua công cụ và kênh

Trước khi đưa dữ liệu vào chat, email, hệ thống ticket, kho mã, dịch vụ lưu trữ, công cụ phân tích hoặc nền tảng AI, hãy xác định công cụ đó được phép xử lý loại dữ liệu nào.

Không mặc định rằng:

- Kênh chat nội bộ có thể nhận mọi loại dữ liệu.
- Ticket lỗi có thể đính kèm dump database hoặc token.
- Kho mã riêng tư là nơi phù hợp để lưu file dữ liệu khách hàng.
- Dịch vụ chia sẻ file có liên kết riêng tư sẽ tự động đáp ứng chính sách.
- Ảnh chụp màn hình không chứa dữ liệu nhạy cảm chỉ vì đã che tên.

Nếu cần chia sẻ để tái hiện lỗi, hãy tạo bản ghi tối thiểu, che thông tin nhận diện, loại bỏ bí mật và dùng kênh được phê duyệt. Chỉ cấp quyền cho người nhận cần thiết và đặt thời hạn liên kết hoặc quyền truy cập khi công cụ hỗ trợ.

## 8. Giới hạn chia sẻ giữa các môi trường

Môi trường development, test, staging và production có mục đích, quyền và mức độ bảo vệ khác nhau. Không nên sao chép dữ liệu giữa các môi trường mà không xem xét mục đích và biện pháp bảo vệ.

| Môi trường | Mục đích thường gặp | Quy tắc dữ liệu cần chú ý |
| --- | --- | --- |
| Development | Phát triển và gỡ lỗi | Ưu tiên dữ liệu tổng hợp/giả lập; tránh dữ liệu nhạy cảm production trên máy cá nhân |
| Test/QA | Kiểm thử chức năng, tích hợp và hồi quy | Dùng bộ dữ liệu được phê duyệt, có thể reset và giới hạn quyền theo dự án |
| Staging | Xác minh gần điều kiện phát hành | Bảo vệ tương đương mức rủi ro của dữ liệu và cấu hình; không xem staging là môi trường công khai |
| Production | Phục vụ người dùng thật | Quyền chặt chẽ, truy cập có lý do, giám sát và quy trình riêng; không dùng làm nơi thử nghiệm tùy tiện |

Staging gần production về cấu hình không có nghĩa cần sao chép toàn bộ dữ liệu production. Có thể dùng dữ liệu tổng hợp với phân bố và kích thước tương đương. Nếu cần một bản sao đã xử lý, phải xác định phương pháp, người phê duyệt, vùng lưu trữ, thời hạn và cách xác minh việc xử lý.

### Ngăn dữ liệu kiểm thử quay lại production

Dữ liệu tổng hợp hoặc tài khoản thử không nên được nhập nhầm vào hệ thống thật. Có thể dùng:

- Tách biệt tài khoản, khóa, endpoint và network giữa môi trường.
- Nhãn hoặc namespace rõ ràng cho dữ liệu thử.
- Kiểm tra cấu hình trước khi chạy migration hoặc job ghi dữ liệu.
- Chặn các giao dịch thử tới nhà cung cấp thật.
- Quy tắc dọn dẹp dữ liệu test và kiểm tra trước khi import.

Đặc biệt, các tài khoản thử nghiệm không nên có quyền thực hiện giao dịch thật hoặc gửi thông báo tới người dùng thật nếu không có kiểm soát riêng.

## 9. Chọn phương pháp tạo dữ liệu an toàn

Giới hạn chia sẻ có thể được giảm bằng cách chọn phương pháp dữ liệu phù hợp:

- **Dữ liệu tổng hợp (synthetic data):** tạo mới theo quy tắc và phân bố cần thiết. Có thể mô phỏng trường hợp biên, dữ liệu hiếm và tải lớn mà không sao chép bản ghi cá nhân.
- **Che dữ liệu (masking):** thay đổi hoặc ẩn các trường nhạy cảm. Cần kiểm tra các trường liên kết và tổ hợp thuộc tính để tránh tái nhận diện.
- **Giả danh hóa (pseudonymization):** thay định danh trực tiếp bằng mã hoặc token. Nếu có bảng ánh xạ, bảng đó phải được bảo vệ riêng.
- **Tokenization:** thay dữ liệu nhạy cảm bằng token không mang ý nghĩa trực tiếp; hệ thống giữ token-vault hoặc cơ chế ánh xạ cần kiểm soát chặt.
- **Lấy mẫu có kiểm soát:** chọn một phần dữ liệu với mục đích rõ và loại bỏ trường không cần thiết; lấy mẫu không tự làm dữ liệu trở nên an toàn.

Không có phương pháp nào tự động phù hợp cho mọi trường hợp. Dữ liệu giả lập có thể không đại diện phân bố thực; dữ liệu đã mask có thể vẫn tái nhận diện; token có thể bị lộ nếu mapping không được bảo vệ. Cần đánh giá phương pháp theo rủi ro và kiểm thử chất lượng dữ liệu sau xử lý.

### Kiểm tra dữ liệu sau xử lý

Trước khi chia sẻ bộ dữ liệu đã xử lý, hãy xác minh:

- Trường nhận diện trực tiếp đã được loại bỏ hoặc thay thế theo yêu cầu.
- Tổ hợp trường có thể nhận diện gián tiếp đã được đánh giá.
- Giá trị bí mật như token, mật khẩu, khóa API và thông tin xác thực đã bị loại bỏ.
- Quan hệ tham chiếu và tính nhất quán cần thiết cho kiểm thử vẫn được duy trì.
- Phân bố, biên, giá trị null và trạng thái cần thiết vẫn đại diện cho mục tiêu.
- Không còn dữ liệu nhạy cảm trong metadata, comment, log hoặc tên file.
- Có thể truy nguyên phiên bản dữ liệu, phương pháp xử lý và người phê duyệt.

Không nên chỉ dựa vào tên file “masked” hoặc “anonymized” để kết luận dữ liệu an toàn. Cần có bước kiểm tra và ghi nhận kết quả.

## 10. Quy trình yêu cầu và phê duyệt truy cập

Một quy trình rõ ràng giúp cấp quyền đúng và tránh xử lý yêu cầu qua tin nhắn không lưu vết.

1. **Gửi yêu cầu:** người yêu cầu nêu mục đích, dự án, bộ dữ liệu, trường cần dùng, hành động, người truy cập, môi trường và thời hạn.
2. **Xác định phân loại:** data steward hoặc người được giao xác nhận nhãn, mức nhạy cảm và hạn chế áp dụng.
3. **Đánh giá phương án:** xem có thể dùng dữ liệu tổng hợp, giả lập, mask hoặc tập dữ liệu nhỏ hơn không.
4. **Xin phê duyệt:** chủ sở hữu dữ liệu và các vai trò liên quan phê duyệt theo mức rủi ro và quy định.
5. **Cấp quyền:** custodian hoặc quản trị viên áp dụng đúng quyền, phạm vi và thời hạn đã duyệt.
6. **Thông báo điều kiện sử dụng:** người nhận biết nơi lưu, kênh chia sẻ, hạn, hành động bị cấm và cách báo sự cố.
7. **Theo dõi và rà soát:** kiểm tra quyền còn cần thiết, hoạt động bất thường và thay đổi mục đích.
8. **Thu hồi và kết thúc:** gỡ quyền, xóa hoặc lưu trữ theo chính sách, xác nhận các bản sao đã được xử lý.

Không nên cấp quyền trước rồi mới xin phê duyệt sau, trừ quy trình khẩn cấp đã được tổ chức quy định. Nếu yêu cầu thay đổi mục đích, người nhận, dữ liệu hoặc thời hạn, cần đánh giá lại thay vì coi phê duyệt cũ tự động bao phủ.

### Mẫu yêu cầu truy cập

```text
REQUEST-ID: TDATA-REQ-024
PROJECT: Checkout regression testing
PURPOSE: Verify payment status mapping and reconciliation
DATASET: Synthetic payment transactions, version 3
CLASSIFICATION: Internal
FIELDS: transaction_id, amount, currency, status, created_at
ACTIONS: Read; create test records in assigned namespace
ENVIRONMENT: Test
REQUESTERS / USERS: Checkout QA group
STORAGE: Approved test database; no local export
VALIDITY: 2027-08-01 through 2027-08-15
ALTERNATIVE REVIEW: Synthetic data is sufficient
APPROVER: Data owner
IMPLEMENTER: Test environment custodian
REVIEW DATE: 2027-08-12
```

Mẫu trên chỉ minh họa cách mô tả yêu cầu. Thông tin và vai trò thực tế cần tuân theo quy trình của tổ chức.

## 11. Bảo vệ dữ liệu khi lưu trữ và truyền

Quyền truy cập là một lớp kiểm soát; dữ liệu cũng cần được bảo vệ khi lưu và truyền.

### Khi lưu trữ

- Lưu dữ liệu ở kho, database hoặc bucket được tổ chức phê duyệt.
- Áp dụng mã hóa khi lưu theo phân loại và chính sách.
- Giới hạn quyền đọc, ghi, xóa và quản trị riêng biệt khi phù hợp.
- Không lưu bản sao dữ liệu nhạy cảm trên máy cá nhân hoặc thiết bị không được quản lý.
- Quản lý backup, snapshot và bản sao tạm theo cùng quy tắc phân loại.
- Tách bí mật và khóa mã hóa khỏi dữ liệu được bảo vệ.

### Khi truyền

- Dùng giao thức và kênh truyền được phê duyệt, có bảo vệ phù hợp.
- Xác minh người nhận và quyền của họ trước khi gửi.
- Không đưa dữ liệu nhạy cảm vào URL, query string, log hoặc tên file.
- Hạn chế tải xuống; nếu bắt buộc, bảo vệ file và đặt thời hạn xóa.
- Tránh gửi mật khẩu hoặc khóa giải mã qua cùng kênh với file dữ liệu.
- Ghi nhận việc chia sẻ theo quy trình, nhất là với dữ liệu mật hoặc bên thứ ba.

### Artifact và log của kiểm thử

Pipeline có thể tạo log, screenshot, video, báo cáo và file dump khi thất bại. Cần cấu hình để:

- Che hoặc loại bỏ token, cookie, header xác thực và trường dữ liệu nhạy cảm.
- Hạn chế quyền truy cập artifact theo nhóm dự án.
- Đặt thời gian lưu phù hợp với nhu cầu điều tra và chính sách.
- Không đính kèm toàn bộ request/response nếu chỉ cần một phần để tái hiện.
- Kiểm tra artifact trước khi chia sẻ cho nhà cung cấp hoặc đính kèm vào ticket.

Ví dụ, khi báo lỗi thanh toán, nhóm thường chỉ cần mã giao dịch giả lập, số tiền, tiền tệ, trạng thái và dấu thời gian. Không cần đính kèm thông tin thẻ, token truy cập hoặc thông tin liên hệ thật.

## 12. Nhật ký truy cập và rà soát quyền

Nhật ký giúp biết ai hoặc hệ thống nào đã truy cập dữ liệu, thực hiện hành động gì và vào thời điểm nào. Với dữ liệu nhạy cảm, cần ghi nhận phù hợp:

- Danh tính người dùng hoặc service account.
- Bộ dữ liệu, kho, bảng hoặc tài nguyên được truy cập.
- Hành động như đọc, sửa, xóa, export hoặc thay đổi quyền.
- Thời điểm, nguồn truy cập và môi trường.
- Mã yêu cầu hoặc mục đích khi chính sách yêu cầu.
- Kết quả thành công/thất bại và dấu hiệu bất thường.

Log phải được bảo vệ để người không có thẩm quyền không thể sửa hoặc xóa dấu vết. Không ghi nội dung nhạy cảm vào log chỉ để có thể theo dõi truy cập; nên ghi metadata đủ để điều tra.

### Rà soát định kỳ

Quyền đã cấp có thể trở nên không cần thiết khi dự án kết thúc, nhân sự chuyển nhóm hoặc mục đích thay đổi. Cần rà soát:

- Thành viên còn thuộc dự án hoặc vai trò không?
- Quyền có rộng hơn nhiệm vụ hiện tại không?
- Quyền tạm thời đã hết hạn chưa?
- Service account nào không còn được dùng?
- Có hoạt động export hoặc truy cập bất thường không?
- Bộ dữ liệu nào đã hết mục đích sử dụng?

Tần suất rà soát cần dựa trên mức nhạy cảm và rủi ro. Quyền với dữ liệu nhạy cảm cao cần được xem xét thường xuyên hơn quyền đọc dữ liệu tổng hợp công khai trong nội bộ.

## 13. Quản lý vòng đời, thời hạn và xóa dữ liệu

Dữ liệu kiểm thử không nên được lưu vô thời hạn chỉ vì có thể hữu ích trong tương lai. Cần xác định vòng đời:

1. **Tạo hoặc tiếp nhận:** ghi nguồn, mục đích, phân loại, phiên bản và chủ sở hữu.
2. **Sử dụng:** áp dụng quyền, môi trường, giới hạn chia sẻ và thời hạn.
3. **Rà soát:** xác nhận dữ liệu còn cần thiết, đúng chất lượng và đúng mục đích.
4. **Lưu trữ:** nếu cần giữ bằng chứng, áp dụng quyền và thời hạn lưu phù hợp.
5. **Xóa hoặc hủy:** xóa dữ liệu hoạt động và xử lý bản sao, backup hoặc cache theo chính sách.
6. **Xác nhận kết thúc:** ghi nhận ai thực hiện, thời điểm, phạm vi và ngoại lệ nếu có.

Thời hạn lưu có thể phụ thuộc vào mục đích kiểm thử, yêu cầu audit, hợp đồng, quy định và chính sách nội bộ. Không nên tự đặt một thời hạn chung cho mọi bộ dữ liệu.

### Xóa dữ liệu và bản sao

Khi hết mục đích, cần xem xét mọi nơi dữ liệu có thể tồn tại:

- Database và schema test.
- File export, thư mục dùng chung và máy trạm.
- Artifact CI, báo cáo lỗi, screenshot và video.
- Cache, queue, dead-letter queue và object storage.
- Snapshot, backup và bản sao phục hồi.
- Bản sao do nhà cung cấp hoặc nhóm khác tạo.

Backup có thể có chu kỳ lưu và cơ chế xóa khác dữ liệu hoạt động. Nếu không thể xóa ngay khỏi backup, cần bảo đảm backup được bảo vệ, không được dùng lại ngoài mục đích phục hồi và sẽ hết hạn theo lịch đã xác định. Phải ghi rõ ngoại lệ và biện pháp kiểm soát.

## 14. Thu hồi quyền và xử lý sự cố chia sẻ

Quyền cần được thu hồi khi:

- Người dùng rời dự án, chuyển vai trò hoặc không còn nhiệm vụ.
- Hết thời hạn phê duyệt.
- Mục đích sử dụng kết thúc hoặc thay đổi.
- Có nghi ngờ tài khoản, thiết bị hoặc thông tin xác thực bị xâm phạm.
- Phát hiện dữ liệu được chia sẻ sai người hoặc sai kênh.

Khi nghi ngờ chia sẻ nhầm hoặc truy cập trái phép, cần:

1. Báo ngay theo quy trình sự cố của tổ chức.
2. Hạn chế tiếp tục truy cập hoặc chia sẻ; thu hồi liên kết, token hoặc quyền khi được phép.
3. Giữ lại bằng chứng cần thiết như thời điểm, người nhận, loại dữ liệu và kênh chia sẻ; không tự ý xóa log điều tra.
4. Xác định dữ liệu nào bị ảnh hưởng, ai có thể đã truy cập và bản sao có thể tồn tại ở đâu.
5. Phối hợp với Security, Privacy, Legal hoặc nhóm chịu trách nhiệm để đánh giá nghĩa vụ thông báo và xử lý.
6. Xác nhận biện pháp khắc phục, xóa bản sao theo hướng dẫn và ghi nhận bài học.

Không tự gửi thêm dữ liệu để giải thích sự cố. Việc thông báo cho người nhận, cơ quan hoặc bên liên quan phải theo quy trình và thẩm quyền của tổ chức.

## 15. Ví dụ: chia sẻ dữ liệu kiểm thử cho nhóm tích hợp thanh toán

Giả sử nhóm QA cần tái hiện lỗi ánh xạ trạng thái thanh toán giữa Checkout Service và một nhà cung cấp. Báo cáo lỗi ban đầu có một số request/response từ môi trường thật, chứa mã giao dịch, thời gian, số tiền và thông tin nhận diện khách hàng.

Nhóm không nên gửi nguyên file log cho tất cả thành viên hoặc nhà cung cấp. Có thể xử lý theo trình tự:

1. Xác định mục tiêu: tái hiện ánh xạ trạng thái và xử lý timeout.
2. Liệt kê trường cần thiết: mã giao dịch giả, số tiền, tiền tệ, trạng thái, mã phản hồi và dấu thời gian.
3. Loại bỏ tên, email, số điện thoại, địa chỉ, token, cookie, thông tin thẻ và header xác thực.
4. Tạo bộ dữ liệu tổng hợp giữ lại các trạng thái quan trọng như `PENDING`, `APPROVED`, `DECLINED` và `UNKNOWN`.
5. Data steward kiểm tra dữ liệu sau xử lý và xác nhận không còn trường nhận diện hoặc bí mật.
6. Chủ sở hữu dữ liệu phê duyệt mục đích, nhóm nhận và thời hạn nếu cần chia sẻ ngoài nhóm.
7. Custodian lưu dữ liệu trong kho test được phê duyệt và cấp quyền đọc cho nhóm QA, quyền ghi cho pipeline riêng.
8. Kết quả kiểm thử được lưu dưới dạng artifact đã lọc, có quyền truy cập giới hạn và thời hạn lưu.
9. Khi điều tra hoàn tất, thu hồi quyền chia sẻ và xóa bản sao theo chính sách; giữ lại báo cáo đã loại bỏ dữ liệu nhạy cảm nếu cần.

Trong ví dụ này, nhóm vẫn có đủ thông tin để kiểm tra quy tắc trạng thái và lỗi timeout. Nếu cần xác minh một hành vi chỉ tái hiện với dữ liệu thật, phải có đánh giá riêng về căn cứ, phạm vi, quyền và biện pháp bảo vệ; không mở rộng chia sẻ chỉ vì một bộ dữ liệu tổng hợp chưa tái hiện được lỗi.

## 16. Mẫu ma trận quyền truy cập và chia sẻ

Có thể dùng ma trận để rà soát quyền trước khi cấp hoặc chia sẻ dữ liệu:

| Vai trò/nhóm | Dữ liệu tổng hợp test | Dữ liệu giả danh nhạy cảm | Dữ liệu production | Export/chia sẻ ngoài |
| --- | --- | --- | --- | --- |
| Kỹ sư kiểm thử thuộc dự án | Đọc/ghi trong namespace được giao | Đọc khi có phê duyệt và thời hạn | Không mặc định; cần quy trình riêng | Không mặc định; cần phê duyệt riêng |
| Lập trình viên thuộc dự án | Đọc/ghi theo nhiệm vụ | Chỉ trường/phạm vi cần thiết khi được duyệt | Không mặc định | Không mặc định |
| Data steward | Quản lý metadata và chất lượng | Quản lý theo nhiệm vụ và chính sách | Theo thẩm quyền dữ liệu | Đánh giá và phối hợp phê duyệt |
| Custodian | Cấp quyền và vận hành kho | Cấp quyền kỹ thuật theo phê duyệt | Theo quy trình production | Không tự quyết định mục đích chia sẻ |
| Nhà cung cấp | Chỉ khi hợp đồng và phê duyệt cho phép | Chỉ khi có căn cứ, phê duyệt và biện pháp phù hợp | Không mặc định | Theo hợp đồng và phê duyệt cụ thể |

Đây là ma trận minh họa. Quyền thực tế phải dựa trên phân loại dữ liệu, vai trò và chính sách của tổ chức. Không nên dùng bảng mẫu để cấp quyền trực tiếp nếu chưa được chủ sở hữu dữ liệu phê duyệt.

## 17. Những lỗi quản lý thường gặp

- **Cấp quyền theo sự tiện lợi:** thêm người dùng vào nhóm quản trị để tránh xử lý yêu cầu chi tiết.
- **Không có chủ sở hữu:** không ai chịu trách nhiệm xác nhận mục đích, thời hạn hoặc việc xóa dữ liệu.
- **Dùng chung tài khoản:** không truy nguyên được hành động của từng người hoặc pipeline.
- **Coi dữ liệu đã mask là dữ liệu công khai:** bỏ qua nguy cơ nhận diện gián tiếp hoặc bảng ánh xạ.
- **Chia sẻ qua kênh không được duyệt:** gửi file qua chat, email cá nhân hoặc kho mã mà không đánh giá.
- **Không kiểm soát artifact:** screenshot, log và report giữ lại token hoặc thông tin cá nhân.
- **Trộn dữ liệu giữa môi trường:** sao chép production vào development hoặc dùng tài khoản test trên production.
- **Không đặt ngày hết hạn:** quyền và bản sao tồn tại lâu hơn mục đích.
- **Chỉ xóa bản chính:** quên file export, backup, cache, artifact hoặc bản sao của nhà cung cấp.
- **Không rà soát quyền sau thay đổi nhân sự:** người không còn nhiệm vụ vẫn truy cập được.
- **Không có quy trình sự cố:** khi chia sẻ nhầm, nhóm không biết ai cần được thông báo và cách thu hồi.

## 18. Checklist trước khi cấp hoặc chia sẻ dữ liệu

- [ ] Mục đích sử dụng được mô tả cụ thể và phù hợp với nhiệm vụ.
- [ ] Bộ dữ liệu và trường cần thiết đã được tối thiểu hóa.
- [ ] Phân loại dữ liệu và khả năng nhận diện trực tiếp/gián tiếp đã được xác định.
- [ ] Đã xem xét dữ liệu tổng hợp, giả lập, mask hoặc giả danh như phương án thay thế.
- [ ] Chủ sở hữu dữ liệu và người phê duyệt đúng thẩm quyền đã được xác định.
- [ ] Người nhận, service account và công cụ có quyền phù hợp với nhiệm vụ.
- [ ] Quyền được giới hạn theo hành động, tài nguyên, môi trường và thời gian.
- [ ] Kênh truyền, kho lưu trữ và vị trí xử lý được phép cho loại dữ liệu đó.
- [ ] Việc export, tạo bản sao và chia sẻ tiếp được cho phép rõ ràng.
- [ ] Log, screenshot, artifact và report đã được kiểm tra để loại bỏ bí mật/dữ liệu không cần thiết.
- [ ] Thời hạn lưu, lịch rà soát, cách thu hồi quyền và cách xóa bản sao đã được xác định.
- [ ] Có nhật ký truy cập và quy trình báo cáo sự cố phù hợp.

## 19. Những điểm cần ghi nhớ

- Xác định quyền truy cập, trách nhiệm quản lý và giới hạn chia sẻ trước khi đưa dữ liệu vào hoạt động kiểm thử.
- Phân loại dữ liệu theo mức nhạy cảm và khả năng nhận diện; áp dụng quy tắc cho cả bản sao, log và artifact.
- Chỉ dùng dữ liệu và trường cần thiết cho mục đích kiểm thử cụ thể.
- Phân biệt chủ sở hữu dữ liệu, người quản lý dữ liệu, đơn vị lưu giữ kỹ thuật, người phê duyệt và người sử dụng.
- Áp dụng quyền tối thiểu theo người, hành động, tài nguyên, môi trường và thời hạn.
- Quản lý riêng danh tính con người và tài khoản dịch vụ; không nhúng bí mật vào mã hoặc artifact.
- Chia sẻ nội bộ, với nhà cung cấp và qua công cụ đều cần căn cứ, người nhận và kênh phù hợp.
- Giả danh hóa không đồng nghĩa ẩn danh hóa; phải đánh giá nguy cơ tái nhận diện.
- Kiểm soát dữ liệu khi lưu, truyền, export, lưu log, tạo backup và xóa.
- Rà soát, thu hồi quyền và xử lý bản sao khi mục đích kết thúc hoặc có sự cố.

## Câu hỏi tự kiểm tra

1. Vì sao dữ liệu kiểm thử vẫn cần được phân loại và bảo vệ dù đã được sao chép khỏi production?
2. Phân biệt chủ sở hữu dữ liệu, data steward và data custodian. Ai nên phê duyệt mục đích sử dụng?
3. Nguyên tắc quyền tối thiểu áp dụng như thế nào với kỹ sư kiểm thử và service account của CI?
4. Vì sao xóa tên và email chưa đủ để kết luận một bộ dữ liệu đã ẩn danh?
5. Trước khi chia sẻ dữ liệu cho nhà cung cấp, nhóm cần xác minh những điều kiện nào?
6. Hãy đề xuất quyền truy cập cho một nhóm QA cần đọc dữ liệu giao dịch giả danh trong hai tuần. Nêu phạm vi, hành động và cách thu hồi.
7. Những bản sao nào cần được xem xét khi kết thúc một dự án kiểm thử?
8. Nếu một file log chứa token và thông tin khách hàng bị gửi nhầm qua kênh không được phép, nhóm cần thực hiện những bước đầu tiên nào?
9. Hãy lập một ma trận quyền truy cập cho dữ liệu tổng hợp, dữ liệu giả danh và dữ liệu production trong dự án bạn biết.
