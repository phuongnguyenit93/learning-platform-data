Trong Azure Repos, một kỹ sư thuộc hai nhóm bảo mật: nhóm dự án cấp Allow cho quyền Read, nhưng nhóm khác cấp Deny cho chính quyền đó trên cùng repository. Khi quyền đều đang có hiệu lực, điều gì xảy ra khi kỹ sư thử đọc mã nguồn?
A. Allow từ nhóm dự án luôn ghi đè Deny được đặt trên repository.
B. Deny có hiệu lực sẽ chặn Read dù một nhóm khác đang cấp Allow.
C. Read được quyết định theo nhóm mà kỹ sư tham gia sớm nhất.
D. Deny chỉ có tác dụng ở cấp project, không ảnh hưởng repository.
Đáp án đúng: B

Một nhóm muốn mọi cập nhật vào nhánh main của Azure Repos phải qua pull request và có người duyệt, kể cả khi người tạo thay đổi có quyền chỉnh sửa mã nguồn. Tổ hợp kiểm soát nào phù hợp nhất?
A. Bật số reviewer tối thiểu nhưng vẫn cho phép push trực tiếp vào main.
B. Cấm force push và cho phép Contribute trực tiếp trên nhánh main.
C. Chỉ bắt buộc build thành công lúc merge, giữ quyền push vào main.
D. Yêu cầu reviewer cho PR và hạn chế quyền push trực tiếp vào main.
Đáp án đúng: D

Repository Azure Repos có thư mục security chứa chính sách xác thực. Trưởng nhóm muốn pull request sửa tệp trong thư mục này tự yêu cầu nhóm bảo mật review, nhưng PR chỉ sửa tài liệu ở nơi khác không cần họ tham gia. Branch policy nào đáp ứng đúng?
A. Đặt build validation với bộ lọc đường dẫn cho thư mục cần duyệt.
B. Đặt automatically included reviewers với lọc đường dẫn thư mục cần duyệt.
C. Đặt check for linked work items với lọc đường dẫn thư mục cần duyệt.
D. Đặt limit merge types với bộ lọc đường dẫn cho thư mục cần duyệt.
Đáp án đúng: B

Một pull request đã có hai phiếu phê duyệt, sau đó tác giả đẩy thêm commit sửa logic kiểm tra quyền truy cập. Nhóm muốn tránh việc phiếu duyệt cũ tự động được coi là chấp thuận cho mã mới. Cấu hình branch policy nào sát mục tiêu nhất?
A. Bật đặt lại phiếu phê duyệt khi nhánh nguồn có thay đổi mới.
B. Bật kiểm tra liên kết work item cho mỗi lần gửi yêu cầu review.
C. Chỉ cho phép squash merge để các commit không còn tồn tại riêng.
D. Chạy lại build validation khi sửa tệp nằm trong thư mục API.
Đáp án đúng: A

Một Azure Pipeline kiểm thử nhánh main hằng đêm đều thành công, nhưng pull request thay đổi mã thanh toán vẫn có thể được merge khi bộ kiểm thử trên nhánh PR thất bại. Nhóm muốn chặn hoàn tất PR nếu kết quả kiểm thử thay đổi chưa đạt. Nên cấu hình gì?
A. Chạy thêm build theo lịch trên nhánh main trước mỗi ngày phát hành.
B. Gắn release tag khi nhánh main vượt qua toàn bộ kiểm thử đêm.
C. Chỉ thêm CI trigger cho mọi push lên nhánh đích của repository.
D. Đặt required build validation branch policy trên nhánh đích của PR.
Đáp án đúng: D

Một pull request trong Azure Repos đã đủ số reviewer chấp thuận và build thành công, nhưng vẫn còn luồng bình luận về lỗ hổng bảo mật chưa được đánh dấu đã xử lý. Nhóm muốn các thảo luận như vậy phải được giải quyết trước khi merge. Chính sách nào phù hợp?
A. Bật Check for comment resolution trong chính sách nhánh đích.
B. Bật Check for linked work items trong chính sách nhánh đích.
C. Bật Limit merge types trong các quy tắc của nhánh đích.
D. Bật Build validation trong các quy tắc của nhánh đích.
Đáp án đúng: A

Nhánh tính năng chứa nhiều commit chỉnh lỗi nhỏ, nhưng đội phát triển muốn nhánh main chỉ nhận một commit tổng hợp cho mỗi pull request để lịch sử phát hành gọn hơn. Chiến lược hoàn tất PR nào tạo ra kết quả mong muốn?
A. Merge commit, giữ từng commit từ nhánh nguồn trong lịch sử đích.
B. Rebase and fast-forward, áp từng commit lên đầu nhánh đích.
C. Squash merge, gom thay đổi nguồn thành một commit trên nhánh đích.
D. Rebase with merge commit, thêm merge commit và giữ commit nguồn.
Đáp án đúng: C

Trong một sự cố production, nhóm trực cần hoàn tất một pull request khẩn cấp trên nhánh được bảo vệ dù PR chưa đạt đủ số approval; họ không được phép đẩy thẳng commit vào nhánh đó. Quyền ngoại lệ nào đúng với phạm vi nhu cầu?
A. Cấp Bypass policies when pushing cho nhóm, vẫn giữ quy tắc PR.
B. Cấp Force push trên nhánh đích, giữ chính sách review đang bật.
C. Cấp Bypass policies when completing pull requests cho nhóm trực.
D. Cấp Edit policies để nhóm sửa chính sách nhánh trước mỗi lần merge.
Đáp án đúng: C

Đội kiểm toán muốn mỗi pull request hoàn tất trên nhánh release của Azure Repos đều liên kết với ít nhất một yêu cầu đã ghi nhận trên Azure Boards. Trường hợp nào thiết lập kiểm soát trực tiếp cho yêu cầu đó?
A. Đặt Check for comment resolution trên nhánh release cần bảo vệ.
B. Đặt Build validation để kiểm thử mỗi pull request được gửi lên.
C. Đặt Automatically included reviewers để bổ sung người phê duyệt.
D. Đặt Check for linked work items để yêu cầu gắn item từ Boards.
Đáp án đúng: D

Một kỹ sư muốn thông điệp commit trong Azure Repos tự tạo liên kết tới work item có ID 482 trên Azure Boards, thay vì phải mở giao diện web liên kết thủ công. Cách ghi tham chiếu nào được Azure DevOps hỗ trợ?
A. Dùng mã #482 trong thông điệp commit trước khi đẩy lên Repos.
B. Dùng mã AB#482 trong thông điệp commit trước khi đẩy lên Repos.
C. Dùng mã WI-482 trong thông điệp commit trước khi đẩy lên Repos.
D. Dùng mã ADO:482 trong thông điệp commit trước khi đẩy lên Repos.
Đáp án đúng: B

Một pipeline YAML chạy build và unit test thành công, nhưng stage deploy bị từ chối sử dụng service connection đã được tạo sẵn vì resource này chỉ cho phép một số pipeline được chỉ định. Cách cấp quyền nào giải quyết vấn đề đúng phạm vi nhất?
A. Đổi chủ sở hữu service connection sang tài khoản quản trị toàn project.
B. Mở quyền đọc secret cho tất cả pipeline trong Azure DevOps organization.
C. Chia sẻ service connection cho mọi project đang tồn tại trong organization.
D. Ủy quyền pipeline cụ thể sử dụng đúng service connection cần thiết.
Đáp án đúng: D

Một Azure Pipeline sử dụng System.AccessToken để đọc repository riêng tư trong project Azure DevOps khác, nhưng job nhận lỗi truy cập dù người kích hoạt pipeline có thể clone repository đó bằng tài khoản cá nhân. Nhóm nên kiểm tra điều gì?
A. Mở phạm vi token tới organization nhưng không xét quyền repository.
B. Bật persistCredentials cho checkout mà không xét quyền repository.
C. Kiểm tra phạm vi job token và quyền Read của build identity ở repo.
D. Cấp quyền cho người chạy job mà bỏ qua danh tính của pipeline.
Đáp án đúng: C

Một đội lưu package trong Azure Artifacts feed chung. Gói từ pipeline thử nghiệm chưa được chấp thuận không nên nằm trong danh sách phiên bản được nhóm production sử dụng, nhưng họ không muốn sao chép package sang feed khác khi phê duyệt. Cơ chế nào phù hợp?
A. Dùng retention policy để chỉ giữ package thử nghiệm trong thời gian ngắn.
B. Dùng feed views để phân loại gói đã duyệt và gói còn thử nghiệm.
C. Dùng branch policy để giới hạn ai có thể tải package trong feed.
D. Dùng pipeline variable để đổi nội dung package khi chuẩn bị phát hành.
Đáp án đúng: B

Một nhóm triển khai qua Azure Pipelines muốn bảo đảm bản production là đúng tệp nhị phân đã vượt qua integration test ở staging. Pipeline hiện build lại ứng dụng ở từng môi trường dù dùng chung commit. Cách tổ chức artifact nào đáp ứng mục tiêu?
A. Build lại gói tại staging và production từ cùng commit đã ghim.
B. Tạo gói riêng từ release tag ngay trước mỗi lần triển khai đích.
C. Quảng bá cùng một artifact đã kiểm thử qua các stage phát hành.
D. Đổi tên phiên bản gói theo tên môi trường tại lúc triển khai.
Đáp án đúng: C

Một stage production trong Azure Pipelines phải chờ quản lý vận hành phê duyệt trước khi sử dụng Environment, kể cả nếu tác giả pull request sửa nội dung pipeline YAML. Cơ chế nào đặt cổng phê duyệt ngoài chính mã pipeline?
A. Đặt approvals and checks ngay trên Environment của production.
B. Thêm bước nhập xác nhận trong YAML do tác giả PR tự chỉnh sửa.
C. Đặt reviewer tối thiểu cho tất cả nhánh feature trong Repos.
D. Bật automatic reviewers cho các tệp pipeline trong Azure Repos.
Đáp án đúng: A

Một work item trên Azure Boards có Iteration Path thuộc sprint mà team A đã cấu hình, nhưng không hiện trên sprint backlog của team A trong khi team B vẫn xem được. Hai team gần đây chia lại phạm vi quản lý module. Nên kiểm tra cấu hình nào đầu tiên?
A. Đối chiếu Area Path của item với phạm vi area team A đang theo dõi.
B. Đối chiếu trạng thái item với category các cột trên Kanban board.
C. Đối chiếu mức ưu tiên item với giới hạn WIP của sprint board.
D. Đối chiếu người được giao item với danh sách tham dự sprint planning.
Đáp án đúng: A
