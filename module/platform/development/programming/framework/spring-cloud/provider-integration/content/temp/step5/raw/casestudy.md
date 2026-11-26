Một ứng dụng Spring Boot dùng Spring Cloud AWS truy cập S3 thành công trên laptop nhờ AWS profile cá nhân, nhưng pod production không có vai trò IAM phù hợp nên không thể đọc dữ liệu.
Nhóm chuyển dịch vụ nhận đơn từ EC2 sang EKS và vẫn giả định instance profile sẽ cấp quyền cho container, khiến các lời gọi AWS SDK trong pod bị từ chối.
Một workload Spring Boot trên EKS sử dụng IAM Roles for Service Accounts nhưng service account Kubernetes gắn sai role ARN, khiến listener SQS chỉ lỗi khi nhận message đầu tiên.
Đội triển khai container lên ECS định dùng task role để truy cập Secrets Manager, nhưng quyền chỉ được cấp cho task execution role nên ứng dụng không đọc được secret.
Một service AWS chạy trên hai account khác nhau cần lấy file từ S3 dùng chung, nhưng policy bucket và role truy cập chéo account không nhất quán khiến một môi trường báo AccessDenied.
Nhóm sử dụng temporary credentials từ STS cho AWS integration nhưng giữ một bản token quá lâu trong bean khởi tạo, khiến lời gọi SQS thất bại sau vài giờ chạy.
Ứng dụng Spring Boot có quyền truy cập S3 tại vùng Singapore nhưng cấu hình region của client khác region bucket, khiến thao tác upload có chuyển hướng hoặc lỗi endpoint không mong muốn.
Đội đưa ứng dụng vào private subnet AWS và bật kết nối S3 qua endpoint riêng, nhưng policy endpoint chỉ cho phép bucket cũ nên một tính năng mới bị từ chối.
Một service Spring Cloud AWS gọi AWS Secrets Manager ngay khi startup, nhưng hạ tầng cấp quyền IAM sau khi pod khởi tạo khiến lần triển khai đầu thất bại còn restart lại thành công.
Nhóm thay region của các thành phần AWS trong cấu hình Spring Boot nhưng không cập nhật region của SQS client, khiến message được gửi vào queue cùng tên ở vùng khác.
Ứng dụng ký request AWS với đồng hồ của container bị lệch nhiều phút so với thực tế, khiến lỗi xác thực xuất hiện dù role và secret đều hợp lệ.
Đội bảo mật cấp quyền IAM wildcard cho một ứng dụng chỉ cần đọc S3, làm workload có khả năng thay đổi dữ liệu ở nhiều bucket ngoài phạm vi công việc.
Một SQS consumer chạy được với quyền ReceiveMessage nhưng không được phép DeleteMessage, khiến các message đã ghi database được phân phối trở lại sau thời hạn visibility timeout.
Ứng dụng lưu tài liệu trong bucket S3 dùng SSE-KMS nhưng IAM role chỉ có quyền đọc S3 mà thiếu quyền sử dụng khóa KMS nên một số object không thể tải xuống.
Nhóm dùng hai AWS profiles trên máy dev để chạy ứng dụng Spring Boot, nhưng thứ tự tìm credentials không được kiểm soát khiến test ghi file vào account không dự định.
Một hệ thống lưu CloudTrail cho thao tác quản trị nhưng không có dấu vết phù hợp về truy cập object S3 nhạy cảm, khiến đội kiểm toán khó xác định workload nào đã đọc dữ liệu.
Đội vận hành xoay IAM role policy khi dịch vụ đang xử lý nhiều yêu cầu, khiến một phần thao tác AWS bị từ chối giữa batch dù các request trước đó thành công.
Một service chạy cả trên EKS và Lambda sử dụng cùng thư viện Spring Cloud AWS, nhưng nguồn identity ở hai runtime khác nhau khiến cách kiểm tra quyền trong test local không phản ánh production.
Nhóm cấp quyền đọc một AWS resource bằng tên ARN quá rộng và tách staging/production không chặt, khiến ứng dụng thử nghiệm có thể truy cập dữ liệu thật.
Ứng dụng gọi S3 từ container có proxy mạng nội bộ, nhưng cấu hình proxy làm sai đường dẫn tới endpoint ký request khiến chỉ các thao tác trên object có tên đặc biệt gặp lỗi.
Một Spring Boot service upload hồ sơ khách lên Amazon S3 bằng tên file gốc, khiến hai khách có tên file giống nhau ghi đè tài liệu khi object key không mang ngữ cảnh định danh.
Nhóm dùng Spring Cloud AWS S3 integration để gửi tệp lớn nhưng giữ toàn bộ file trong bộ nhớ trước khi upload, khiến pod hết RAM trong đợt nhập hồ sơ hàng loạt.
Một ứng dụng lưu video lên S3 theo multipart upload nhưng bị ngắt kết nối giữa chừng, khiến các phần upload chưa hoàn tất tích tụ và làm tăng chi phí lưu trữ.
Đội triển khai HTTP API trả link tải hồ sơ bằng presigned S3 URL, nhưng thời hạn URL ngắn hơn thời gian phê duyệt khiến khách hàng nhận lỗi khi mở thông báo muộn.
Một service Spring Boot upload object với Content-Type không đúng loại dữ liệu, khiến trình duyệt tải tệp PDF theo cách khác dự kiến và client tích hợp xử lý sai nội dung.
Nhóm sử dụng S3 versioning để lưu bản hợp đồng, nhưng API tải lại chỉ sử dụng object key thay vì version cụ thể nên kiểm toán viên đôi khi xem nhầm bản mới.
Một ứng dụng ghi dữ liệu giao dịch vào S3 tại một vùng rồi đọc từ bucket sao chép liên vùng ngay sau đó, khiến bản sao chưa sẵn sàng trong thời gian replication còn trễ.
Đội tạo bucket S3 dùng để trao đổi tài liệu với đối tác, nhưng chính sách public access và quyền bucket thay đổi giữa các môi trường khiến kiểm thử tải lên không phản ánh production.
Ứng dụng xử lý danh sách S3 objects bằng một request listing duy nhất, khiến dữ liệu của những ngày có hàng nghìn tệp không được nhập đầy đủ.
Nhóm thiết lập S3 lifecycle xóa object tạm sau vài ngày nhưng quy trình đối soát giao dịch mất nhiều tuần, khiến bằng chứng cần điều tra đã bị dọn trước hạn.
Một service dùng object tags để phân biệt tài liệu cần lưu giữ, nhưng bước upload của adapter không gắn tag nên các file mới rơi vào chính sách retention sai.
Đội tích hợp tải object S3 lớn qua Spring Boot rồi đọc toàn bộ response thành chuỗi, khiến dữ liệu nhị phân và bộ nhớ JVM bị xử lý không phù hợp.
Một bucket S3 dùng key có dấu tiếng Việt và ký tự đặc biệt, nhưng ứng dụng tự ghép URL thay vì dùng định dạng khóa nhất quán khiến một số file không tải được.
Nhóm gửi message khi object đã upload lên S3, nhưng bước publish lỗi sau khi upload thành công và hệ thống downstream không nhận thông báo về file mới.
Ứng dụng dùng sự kiện S3 để khởi tạo pipeline xử lý ảnh, nhưng object bị ghi đè trước khi consumer tải về nên dữ liệu xử lý khác với version đã kích hoạt sự kiện.
Một service tạo URL cho khách upload thẳng lên S3 nhưng thiếu giới hạn nội dung và phạm vi object key, khiến khách có thể gửi tệp ngoài thư mục hồ sơ của họ.
Nhóm dùng S3 object lock cho dữ liệu kiểm toán nhưng quy trình xóa tài khoản vẫn cố loại bỏ tất cả object ngay lập tức, khiến chức năng xóa báo lỗi ở một nhóm hồ sơ.
Ứng dụng chuyển xử lý S3 sang bucket của account đối tác nhưng chưa xét quyền của KMS key bên account đó, khiến tải object bị từ chối dù bucket policy cho phép.
Đội vận hành đổi lớp lưu trữ S3 của hồ sơ ít truy cập, nhưng một tính năng cần đọc lại ngay không tính đến tình trạng object cần khôi phục trước khi sử dụng.
Một service xử lý tệp đầu vào qua event S3 nhưng không xét event có thể được giao trùng, khiến cùng hóa đơn được import vào PostgreSQL hai lần.
Nhóm xây API upload S3 theo tên khách và số hợp đồng nhưng sử dụng giá trị chưa chuẩn hóa, khiến một khách có nhiều đường dẫn object khác nhau cho cùng hồ sơ.
Ứng dụng dùng SQS với Spring Cloud AWS để nhận lệnh gửi hàng, nhưng thời gian xử lý dài hơn visibility timeout nên hai consumer cùng xử lý một lệnh.
Một @SqsListener trong Spring Boot ghi đơn hàng rồi lỗi trước bước xác nhận xử lý, khiến SQS phân phối lại và hệ thống tạo phiếu xuất kho trùng.
Đội nâng concurrency của consumer SQS để giảm backlog nhưng database đích không tăng số kết nối, khiến thời gian xử lý một message và lượng message đang ẩn tăng.
Nhóm cấu hình SQS dead-letter queue sau nhiều lần nhận thất bại nhưng không có báo cáo nguồn và mã lỗi, khiến đội hỗ trợ không biết message nào an toàn để phát lại.
Một producer gửi message vượt kích thước tối đa cho phép của SQS, khiến các đơn hàng chứa danh sách mặt hàng rất lớn bị lỗi trong khi đơn nhỏ hoạt động bình thường.
Ứng dụng chuyển từ SQS standard queue sang FIFO queue nhưng producer thiếu MessageGroupId phù hợp, khiến chỉ một phần luồng nghiệp vụ được publish thành công.
Một hệ thống cần thứ tự cập nhật theo tài khoản trên SQS FIFO nhưng producer dùng group ID theo request, khiến những event của cùng tài khoản không còn nối tiếp đúng kỳ vọng.
Nhóm tin rằng SQS FIFO loại trừ vĩnh viễn mọi lệnh trùng, nhưng cùng yêu cầu thanh toán được gửi lại ngoài khoảng deduplication và tạo tác dụng phụ lần hai.
Một listener SQS dùng long polling để giảm request rỗng, nhưng môi trường production đặt timeout của HTTP client ngắn hơn thời gian chờ khiến kết nối bị ngắt liên tục.
Đội triển khai lại message từ DLQ về queue chính sau khi sửa lỗi JSON, nhưng một số lệnh đã có tác dụng phụ trước khi thất bại và bị thực hiện thêm lần nữa.
Ứng dụng lưu thông điệp SQS chỉ với payload JSON mà thiếu version, khiến consumer mới không biết cách đọc những message đã nằm trong queue từ trước deploy.
Nhóm dùng SQS để nhận yêu cầu xuất báo cáo nhưng producer đánh dấu tác vụ hoàn tất ngay sau SendMessage, khiến khách nghĩ file đã sẵn sàng trong khi consumer còn chờ.
Một service tích hợp SNS topic và SQS subscription nhưng filter policy không khớp thuộc tính event mới, khiến thông báo của một loại đơn hàng không đi đến queue nhận.
Nhóm chuyển SNS subscription sang raw message delivery nhưng consumer vẫn kỳ vọng envelope JSON của SNS, khiến deserialization thất bại sau cập nhật cấu hình.
Một hệ thống sử dụng SNS fanout để gửi sự kiện cập nhật khách đến nhiều queue, nhưng một service đăng ký cùng topic bằng hai subscription khác nhau và xử lý trùng.
Ứng dụng nhận SNS notification qua HTTP endpoint nhưng chưa kiểm tra nguồn và chữ ký của thông điệp, khiến request giả có thể kích hoạt quy trình thay đổi dữ liệu.
Đội triển khai cùng SNS topic cho thông báo nhạy cảm và công khai nhưng filter policy không phản ánh quyền nhận, khiến một subscriber nhận dữ liệu vượt phạm vi.
Một Spring Boot producer gửi message SNS bất đồng bộ nhưng chỉ ghi nhận việc gọi API bắt đầu, khiến lỗi publish sau đó không xuất hiện trong trạng thái nghiệp vụ.
Nhóm tích hợp SNS và SQS qua nhiều account, nhưng resource policy của queue không cho SNS topic đúng ARN gửi message khiến subscription tồn tại nhưng queue rỗng.
Một consumer Spring Cloud AWS nhận sự kiện từ SQS với message body đã chuyển qua converter, nhưng header và metadata của SNS bị mất khiến trace không nối được nguồn.
Ứng dụng xử lý yêu cầu đặt chỗ qua SQS và gọi API đối tác; khi API timeout sau khi đã thực hiện thành công, message redelivery khiến đối tác giữ chỗ hai lần.
Nhóm cấu hình queue retry bằng SQS DelaySeconds nhưng nhu cầu chờ vượt thời gian delay được hỗ trợ, khiến nghiệp vụ không thể hẹn xử lý đúng mốc mong muốn.
Một service đọc SQS message có trường accountId nhưng không xác minh quyền của tài khoản producer, khiến dữ liệu từ đối tác có thể ghi nhầm tenant.
Đội thử tích hợp SNS bằng một mock luôn xác nhận publish, nhưng production có lỗi quyền Publish trên topic và message không bao giờ được phân phối.
Một ứng dụng đặt tên queue SQS giống nhau cho nhiều vùng, nhưng policy của Spring Boot lấy region mặc định từ môi trường nên chỉ một vùng xử lý lệnh chính xác.
Nhóm tăng batch send SQS để cải thiện throughput nhưng chỉ kiểm tra mã trạng thái chung, khiến các message lỗi riêng lẻ trong batch không được đưa vào cơ chế retry.
Một consumer SQS nhận thông báo object S3 đã tạo nhưng không lưu object version, khiến khi tệp bị thay thế trước thời điểm xử lý nó lấy bản nội dung không còn khớp event.
Một ứng dụng cần giám sát thời gian chờ ở SQS nhưng dashboard chỉ đo số lần listener được gọi, khiến backlog tăng hàng giờ mà chỉ số xử lý vẫn hiển thị bình thường.
Nhóm lưu API token của đối tác trong AWS Secrets Manager nhưng cấu hình ứng dụng vẫn chứa bản token cũ ở environment variable có độ ưu tiên cao hơn nguồn secret.
Ứng dụng Spring Cloud AWS đọc Secrets Manager ở startup nhưng thiếu quyền truy cập đúng secret ARN, khiến lỗi xuất hiện trước khi Health endpoint sẵn sàng.
Đội xoay mật khẩu trong Secrets Manager nhưng datasource HikariCP đã giữ thông tin cũ, khiến các kết nối mới bị từ chối còn kết nối đang mở vẫn hoạt động.
Một hệ thống lưu cấu hình chung trong Systems Manager Parameter Store, nhưng một số pod sử dụng đường dẫn tham số của staging khiến request production đi đến endpoint thử nghiệm.
Nhóm dùng tham số SSM loại SecureString nhưng IAM role có quyền đọc parameter mà thiếu quyền KMS phù hợp, khiến một nhóm ứng dụng không giải mã được cấu hình.
Ứng dụng cache kết quả Secrets Manager quá lâu để giảm độ trễ, khiến khi secret bị thu hồi công cụ vẫn gửi credential đã hết hiệu lực cho dịch vụ đích.
Đội chuyển thông tin xác thực từ file JAR sang Parameter Store nhưng không kiểm thử thứ tự ưu tiên property sources, khiến giá trị nhúng sẵn vẫn được sử dụng.
Nhóm dùng secret JSON chứa nhiều khóa kết nối nhưng một phần cấu hình thiếu field bắt buộc ở vùng dự phòng, khiến pod failover không khởi tạo được client.
Một service quản lý nhiều tenant dùng tên secret suy ra từ dữ liệu request không kiểm soát, khiến workload có thể thử truy xuất secret của tenant khác trong cùng account.
Đội ghi log configuration properties để gỡ lỗi Secret Manager và vô tình đưa giá trị được giải mã vào nền tảng tập trung mà nhiều nhóm có quyền đọc.
Ứng dụng dùng Amazon RDS PostgreSQL với IAM database authentication, nhưng pool giữ credential hết hiệu lực khi tạo kết nối mới khiến lỗi chỉ xuất hiện sau thời gian dài chạy.
Nhóm triển khai Spring Boot lên Lambda và để mỗi invocation tạo pool RDS riêng, khiến đợt tăng concurrency làm database đạt ngưỡng kết nối.
Một service truy cập Aurora sau failover nhưng cache DNS và kết nối cũ trong pool chưa được làm mới, khiến nhiều yêu cầu ghi vào writer endpoint không thành công.
Đội phát triển chạy test RDS với PostgreSQL local nhưng production dùng tính năng bảo mật IAM/TLS đặc thù, khiến bản phát hành đầu tiên không kết nối được dữ liệu.
Ứng dụng ghi dữ liệu idempotency vào DynamoDB nhưng dùng thao tác ghi không có điều kiện, khiến hai consumer song song cùng chấp nhận một lệnh thanh toán.
Nhóm thiết kế DynamoDB partition key chỉ dựa trên ngày xử lý khiến toàn bộ traffic cao điểm đổ vào một số partition, làm thao tác ghi bị throttling.
Một dịch vụ đọc trạng thái mới ghi ở DynamoDB qua đường đọc eventual consistency, khiến màn hình người dùng nhận dữ liệu cũ ngay sau khi cập nhật.
Đội dùng DynamoDB TTL để dọn dữ liệu phiên và giả định bản ghi sẽ biến mất chính xác ở thời điểm hết hạn, khiến thông tin cũ vẫn được đọc thêm một khoảng thời gian.
Một service Spring Boot quét bảng DynamoDB để lấy tất cả đơn chưa hoàn tất, nhưng số trang kết quả tăng lớn làm độ trễ batch vượt cửa sổ xử lý.
Nhóm chuyển từ RDS sang DynamoDB cho một loại giao dịch nhưng giữ giả định về join và transaction như SQL, khiến quy trình đối soát không phản ánh cùng mức nhất quán.
Một ứng dụng Spring Cloud Azure sử dụng DefaultAzureCredential để truy cập Blob Storage, nhưng local lấy tài khoản lập trình viên còn AKS không có identity phù hợp nên production bị từ chối.
Nhóm di chuyển Spring Boot từ VM Azure sang AKS và quên ánh xạ workload identity cho service account, khiến SDK không lấy được token cho Key Vault.
Một service Azure sử dụng user-assigned managed identity nhưng pod không chỉ rõ identity cần dùng khi có nhiều danh tính, khiến quyền truy cập Storage thay đổi theo môi trường.
Đội cấp role Contributor ở cấp resource group cho workload đọc blob nhưng không kiểm tra quyền data-plane tương ứng, khiến API vẫn trả lỗi quyền khi tải object.
Ứng dụng gọi Key Vault qua token Azure đã cache nhưng cấu hình endpoint thuộc tenant khác, khiến request được ký hợp lệ về cấu trúc nhưng không được chấp nhận.
Một Spring Boot client được cấp quyền vào Azure Blob Storage bằng account key dùng chung, nhưng key bị xoay khi một service cũ vẫn lưu trong cấu hình đóng gói.
Nhóm chạy Azure integration trong cloud sovereign nhưng SDK và cấu hình identity vẫn dùng endpoint của public cloud, khiến xác thực và truy cập resource thất bại.
Ứng dụng sử dụng managed identity để đọc dữ liệu từ Azure SQL nhưng local test vẫn dựa trên password, khiến cơ chế cấp token cho datasource không được kiểm chứng trước release.
Đội vận hành cấp quyền Azure RBAC ở subscription quá rộng cho một service chỉ cần đọc một container blob, làm nguy cơ truy cập chéo sản phẩm tăng.
Nhóm sử dụng cùng tên managed identity trên nhiều môi trường nhưng định danh tài nguyên khác nhau, khiến pipeline thiết lập nhầm quyền cho workload production.
Một service Spring Cloud Azure chuyển vùng triển khai mà private endpoint DNS của storage chưa được đồng bộ, khiến pod kết nối tới địa chỉ public bị network policy chặn.
Đội tích hợp nhiều Azure resources với một token provider tự viết nhưng không phân biệt audience của từng resource, khiến Service Bus nhận token dành cho Storage.
Một ứng dụng đọc thông tin tenantId từ claim người dùng để chọn resource Azure, nhưng không ràng buộc danh tính workload với quyền được cấp ở backend.
Nhóm xoay chứng chỉ federation cho Azure workload identity nhưng một cluster không cập nhật cấu hình trust, khiến chỉ nhóm pod vừa rollout không lấy được token.
Ứng dụng tải hồ sơ lên Azure Blob Storage qua Spring Cloud Azure nhưng ghi chung một blob name cho các đợt đồng bộ, khiến bản mới ghi đè bằng chứng của đợt trước.
Đội dùng SAS URL để khách tải file từ Azure Blob, nhưng SAS hết hạn trước khi đối tác hoàn tất quy trình phê duyệt nên người nhận không mở được tệp.
Một hệ thống phát SAS token với quyền ghi rộng cho cả container thay vì phạm vi object dự kiến, khiến client bên ngoài có thể thay đổi nhiều tệp.
Nhóm triển khai Azure Blob upload cho file lớn nhưng không giới hạn bộ nhớ khi đọc body HTTP, làm pod OOM khi nhiều khách gửi video cùng lúc.
Ứng dụng cập nhật tài liệu trên Azure Blob bằng cách upload mới nhưng không xét ETag của bản đang lưu, khiến hai nhân viên ghi đè chỉnh sửa của nhau.
Đội dùng block blob upload theo nhiều phần nhưng tiến trình bị dừng trước khi commit block list, khiến file không xuất hiện mặc dù một số block đã được tải lên.
Một service lưu tệp trong Azure Blob với soft delete và versioning nhưng chức năng xóa tài khoản chỉ nhìn thấy bản hiện tại, khiến dữ liệu đã xóa vẫn còn trong bản cũ.
Nhóm đặt lifecycle policy chuyển blob ít dùng sang archive tier, nhưng quy trình đối soát cần đọc ngay khi có khiếu nại và không tính đến thời gian rehydrate.
Ứng dụng liệt kê blob theo prefix bằng một trang duy nhất, khiến bộ nhập dữ liệu bỏ sót tệp khi số lượng vượt giới hạn của một lần list.
Một hệ thống chia sẻ Blob container giữa nhiều tenant nhưng đường dẫn blob thiếu tenant ID ổn định, khiến khách cùng tên tài liệu truy cập nhầm file.
Đội đổi thiết lập public network access của Storage Account sang private only nhưng pod kiểm thử không nằm trong VNet phù hợp, khiến chỉ môi trường cloud báo timeout.
Ứng dụng ghi metadata Content-Type cho Azure Blob không đúng định dạng, khiến trình duyệt và hệ thống downstream đọc file CSV như văn bản không phù hợp.
Nhóm dùng Azure Event Grid để nhận thông báo khi blob tạo mới, nhưng cùng event được giao lại sau lỗi endpoint khiến pipeline import xử lý một file hai lần.
Một service lưu bản backup trên Azure Blob và dùng khóa mã hóa do khách hàng quản lý, nhưng quyền Key Vault bị thu hồi khiến việc đọc lại backup thất bại.
Đội dự tính di chuyển tệp từ S3 sang Azure Blob bằng cách giữ nguyên object metadata, nhưng một trường metadata hợp lệ ở nguồn không được biểu diễn giống ở đích.
Một ứng dụng gửi lệnh xuất hàng qua Azure Service Bus queue nhưng thời gian xử lý lớn hơn message lock duration, khiến lệnh được giao thêm lần nữa khi consumer đầu vẫn chạy.
Nhóm xử lý Service Bus message bằng chế độ hoàn tất tự động nhưng handler bắt exception rồi chỉ ghi log, khiến thông điệp lỗi bị đánh dấu đã xử lý.
Một service cần giữ thứ tự lệnh theo customerId trên Azure Service Bus nhưng gửi vào queue không bật session, khiến các consumer đồng thời áp trạng thái sai thứ tự.
Đội triển khai Service Bus session-enabled queue nhưng listener không chấp nhận session phù hợp, khiến backlog tăng dù pod vẫn healthy.
Ứng dụng dùng duplicate detection của Azure Service Bus và giả định nó bảo vệ vĩnh viễn mọi message ID, khiến các lệnh gửi lại sau khoảng phát hiện vẫn được xử lý trùng.
Nhóm phát lệnh theo lịch bằng scheduled messages trên Service Bus nhưng quy trình hủy đơn không hủy lịch đã phát, khiến một lệnh giao hàng hết hiệu lực vẫn tới consumer.
Một service gửi message vượt giới hạn kích thước của tier Service Bus đang dùng, khiến một số yêu cầu chứa báo cáo lớn bị từ chối trước khi ghi hàng đợi.
Đội dùng Service Bus topic và subscription để fanout sự kiện nhưng filter rule quá rộng, khiến hệ thống kiểm toán nhận cả dữ liệu thử nghiệm không liên quan.
Ứng dụng cấu hình dead-letter queue cho Service Bus nhưng không mang theo thông tin lỗi nghiệp vụ, khiến đội trực không xác định được thông điệp nào cần sửa dữ liệu.
Nhóm replay dead-letter message từ Service Bus sau deploy mà không có khóa idempotency, khiến nhiều side effect đã thành công một phần được thực hiện lại.
Một Service Bus consumer phát sinh transaction database sau khi nhận message, nhưng việc settle message xảy ra không cùng ranh giới với DB commit khiến crash gây redelivery.
Đội tăng maxConcurrentCalls cho Service Bus processor nhưng downstream Azure SQL không tăng tài nguyên, làm các lệnh thanh toán bị timeout và khóa message hết hạn.
Ứng dụng dùng Azure Event Hubs để nhập dữ liệu telemetry nhưng coi nó như hàng đợi lệnh xóa từng thông điệp sau khi xử lý, khiến thiết kế checkpoint không phản ánh yêu cầu nghiệp vụ.
Nhóm phân vùng Event Hubs theo thiết bị nhưng producer dùng partition key không ổn định, khiến thứ tự sự kiện của cùng thiết bị không được bảo đảm.
Một hệ thống có nhiều Event Hubs consumers trong một consumer group và cùng checkpoint store, nhưng cách phân chia partition thay đổi khi autoscale gây xử lý lại ở biên.
Đội dùng Azure Blob để lưu checkpoint Event Hubs nhưng managed identity không có quyền ghi blob, khiến processor xử lý dữ liệu rồi không lưu được tiến độ.
Ứng dụng tăng số lượng event trong mỗi batch Event Hubs nhưng không tăng ngân sách bộ nhớ, khiến consumer tụt lag khi gặp payload lớn.
Nhóm đổi retention Event Hubs để giảm chi phí nhưng job đồng bộ dừng lâu hơn thời gian giữ sự kiện, khiến dữ liệu cũ không còn để replay.
Một service chuyển từ Service Bus queue sang Event Hubs cho command nghiệp vụ mà không kiểm tra khác biệt giữa settlement và checkpoint, khiến những lỗi lệnh riêng lẻ khó cô lập.
Đội dùng Azure Event Grid cho webhook sự kiện tạo resource nhưng endpoint Spring Boot không xác minh nguồn phù hợp, khiến request giả có thể kích hoạt tác vụ nhập dữ liệu.
Ứng dụng đăng ký Event Grid subscription trỏ tới URL cũ sau đợt chuyển gateway, khiến sự kiện từ Azure không tới service dù producer vẫn hoạt động.
Nhóm tạo Azure Key Vault secret cho tài khoản đối tác nhưng ứng dụng đang dùng cùng tên property từ biến môi trường có ưu tiên cao hơn, khiến secret mới không được áp dụng.
Một Spring Boot service đọc Key Vault bằng managed identity nhưng chỉ được cấp quyền trên management plane, khiến lần đọc secret đầu tiên bị từ chối.
Đội xoay secret Azure SQL trong Key Vault nhưng pool kết nối vẫn giữ credential cũ và nhiều connection mới bắt đầu lỗi sau thời điểm thu hồi.
Ứng dụng gắn Key Vault làm nguồn cấu hình ở giai đoạn startup nhưng mạng tới vault tạm ngắt, khiến rollout bị chặn trước khi endpoint health xuất hiện.
Nhóm sử dụng nhiều Key Vault cho staging và production nhưng cấu hình URI bị sao chép nhầm, khiến pod thử nghiệm truy xuất dữ liệu mật của môi trường thật.
Đội bảo mật bật soft delete cho Key Vault secrets nhưng quy trình hủy tài khoản chỉ xóa phiên bản hiện tại, khiến bản cũ vẫn có thể được khôi phục trái kỳ vọng.
Một hệ thống dùng Key Vault certificate cho mTLS tới đối tác nhưng cert bị xoay trước khi client reload, khiến các kết nối mới thất bại còn kết nối cũ hoạt động.
Nhóm ghi log cấu hình Spring Cloud Azure quá chi tiết, khiến thông tin bí mật lấy từ Key Vault xuất hiện trong bản đính kèm lỗi CI.
Ứng dụng muốn cô lập quyền truy cập secret theo từng đội nhưng sử dụng một managed identity chung cho nhiều microservice, khiến ranh giới bảo mật không rõ ràng.
Đội vận hành cần khôi phục bản cấu hình secret trước khi xoay khóa, nhưng thiếu liên kết giữa version Key Vault được dùng và release Spring Boot đang chạy.
Một service ghi dữ liệu vào Azure Cosmos DB bằng partition key lấy từ trường region, nhưng traffic tập trung vào một vùng khiến request bị throttling dù tổng RU vẫn còn.
Nhóm kiểm thử Cosmos DB với vài document nhỏ nhưng production có payload lớn và query xuyên partition, khiến mức tiêu thụ request units vượt ngân sách.
Ứng dụng đòi đọc trạng thái mới ghi trên Cosmos DB ở vùng khác nhưng chưa xét consistency level, khiến người dùng thấy đơn hàng chưa cập nhật ngay sau khi thanh toán.
Đội bật TTL mặc định cho Azure Cosmos DB container chứa cả phiên ngắn hạn và hồ sơ cần lưu để đối soát, khiến tài liệu kiểm toán có thể bị xóa theo chính sách của phiên.
Một Spring Boot service dùng Azure SQL Managed Identity nhưng mã truy cập database vẫn cache mật khẩu từ cấu hình local, khiến đường xác thực production không được thử đúng.
Nhóm triển khai Azure SQL failover group cho ứng dụng vừa giao dịch vừa báo cáo, nhưng hai datasource đều dùng endpoint ghi khiến truy vấn phân tích nặng tranh chấp tài nguyên với giao dịch.
Một ứng dụng dùng Cosmos DB thay RDBMS cho lịch sử thanh toán nhưng giữ giả định transaction đa tài khoản luôn thực hiện nguyên tử, khiến dữ liệu đối soát bị lệch.
Đội sử dụng Cosmos DB emulator trong integration test nhưng không mô phỏng RU throttling và replication đa vùng, khiến production gặp lỗi chưa từng xuất hiện trong CI.
Một ứng dụng Spring Cloud GCP dùng Application Default Credentials chạy tốt trên laptop nhờ tài khoản cá nhân, nhưng workload GKE không có service account phù hợp để đọc Cloud Storage.
Nhóm triển khai Workload Identity Federation for GKE nhưng Kubernetes service account không gắn đúng quyền của Google service account, khiến Pub/Sub consumer nhận lỗi 403.
Một service GCP dùng service account key JSON đóng trong container thay vì danh tính workload, làm khóa bí mật đi cùng image tới mọi môi trường triển khai.
Đội cấu hình project ID mặc định khác project chứa Pub/Sub subscription, khiến Spring Boot kết nối tới tài nguyên không tồn tại dù thông tin đăng nhập hợp lệ.
Ứng dụng chạy trên Cloud Run nhưng service account runtime không có quyền Secret Manager, khiến request đầu tiên cần token đối tác thất bại sau cold start.
Nhóm dùng cùng danh tính GCP để truy cập Cloud Storage và BigQuery ở nhiều project, nhưng IAM binding không tách phạm vi khiến một service có quyền đọc dữ liệu nhạy cảm quá mức.
Một Spring Boot client GCP dùng service account impersonation trên CI nhưng runner chưa được cấp quyền impersonate tài khoản đích, khiến pipeline không chạy được integration test.
Đội chuyển workload từ GKE sang Cloud Run và tái sử dụng giả định về quyền truy cập metadata server, khiến một nhánh code tự lấy token không hoạt động.
Ứng dụng chạy ở khu vực có network policy cấm egress tới Google APIs, nhưng health endpoint chỉ báo tiến trình UP nên lỗi xác thực và storage không được phát hiện sớm.
Nhóm xoay service account credentials trong môi trường local nhưng một test giữ client được khởi tạo bằng khóa cũ, khiến kết quả kiểm thử không phản ánh danh tính mới.
Một hệ thống nhiều tenant dùng project GCP tách biệt nhưng provider client được tạo bằng project mặc định, khiến sự kiện Pub/Sub từ tenant A có nguy cơ đi vào project B.
Đội cấp quyền Google Cloud IAM ở cấp organization cho service chỉ cần đọc một bucket GCS, gây rủi ro lộ dữ liệu ngoài phạm vi tích hợp được phê duyệt.
Một Spring Boot service upload file lên Google Cloud Storage nhưng object name chỉ lấy tên tệp gốc, khiến hai đợt upload của khách ghi đè nhau trong cùng bucket.
Nhóm sử dụng signed URL trên GCS cho khách tải hợp đồng nhưng thời hạn hiệu lực ngắn hơn quy trình phê duyệt, khiến link trong email hết hạn trước khi được mở.
Ứng dụng cần cập nhật metadata của object GCS nhưng không dùng generation precondition phù hợp, khiến hai worker ghi đè thay đổi của nhau khi chạy đồng thời.
Đội tải tệp nhiều gigabyte từ Cloud Storage về Spring Boot API nhưng đọc toàn bộ vào RAM, khiến container hết bộ nhớ khi có vài request tải đồng thời.
Một bucket GCS bật uniform bucket-level access trong khi luồng tích hợp cũ còn gán object ACL, khiến thao tác upload gặp lỗi quyền sau thay đổi cấu hình.
Nhóm dùng Cloud Storage lifecycle xóa bản ghi tạm nhưng lịch đối soát kéo dài hơn thời hạn lưu giữ, khiến một số tệp chưa được kiểm tra đã biến mất.
Ứng dụng xử lý sự kiện object finalized của GCS qua Pub/Sub nhưng sự kiện được giao lại sau lỗi ACK, khiến cùng tệp được import vào database hai lần.
Đội lưu object GCS với customer-managed encryption key nhưng service account thiếu quyền dùng Cloud KMS, khiến object cũ còn đọc được trong khi object mới thất bại.
Một service liệt kê object GCS bằng một trang dữ liệu duy nhất, khiến các tệp nằm sau page token không được đồng bộ vào hệ thống báo cáo.
Nhóm sử dụng Cloud Storage versioning nhưng API tra cứu chỉ lấy bản hiện tại, khiến kiểm toán viên không thể tái dựng đúng nội dung hồ sơ vào thời điểm giao dịch.
Ứng dụng lưu nội dung tiếng Việt vào GCS với metadata charset thiếu nhất quán, khiến hệ thống nhận tệp CSV giải mã sai ký tự và tạo bản ghi lỗi.
Đội chuyển bucket Cloud Storage sang vùng có chính sách lưu dữ liệu khác, nhưng job đồng bộ không kiểm tra yêu cầu data residency của từng khách.
Một service upload file từ HTTP qua GCS nhưng client mất kết nối sau khi object được ghi, khiến thao tác thử lại tạo ra bản thứ hai với khóa khác dù dữ liệu giống nhau.
Một Spring Boot consumer nhận Google Pub/Sub message và ghi PostgreSQL nhưng ACK trước khi transaction commit, khiến lỗi SQL dẫn đến mất yêu cầu nghiệp vụ.
Nhóm xử lý Pub/Sub message lâu hơn ack deadline mà không gia hạn phù hợp, khiến message được giao lại cho một instance khác khi tiến trình đầu còn đang chạy.
Ứng dụng dùng Pub/Sub ordering key theo loại sự kiện thay vì accountId, khiến những thay đổi của cùng tài khoản không còn giữ thứ tự như nghiệp vụ yêu cầu.
Đội tăng số lượng Pub/Sub subscriber để giảm backlog nhưng downstream database không chịu được tải đồng thời, khiến số message được giao lại tăng.
Một subscription Pub/Sub dùng dead-letter topic nhưng service account của Pub/Sub không có quyền publish phù hợp, khiến cơ chế xử lý message lỗi không như mong đợi.
Nhóm dùng exactly-once delivery của Pub/Sub subscription để khẳng định side effect database sẽ không bao giờ trùng, nhưng crash giữa commit và ACK vẫn cần được phân tích.
Một ứng dụng xử lý event Pub/Sub có schema thay đổi theo phiên bản, nhưng consumer mới không đọc được message cũ đang tồn trong subscription sau deploy.
Đội triển khai push subscription Pub/Sub tới endpoint Spring Boot nhưng chưa thiết lập xác thực nguồn phù hợp, khiến endpoint public có nguy cơ nhận request giả.
Một service gửi thông báo qua Pub/Sub publisher nhưng chỉ kiểm tra API trả về ngay lập tức, không ghi nhận kết quả bất đồng bộ của việc publish khi mạng lỗi.
Nhóm thiết lập subscription filter dựa trên message attributes nhưng publisher không gắn thuộc tính ở một loại event, khiến dữ liệu bị loại trước khi consumer nhìn thấy.
Ứng dụng nhận Pub/Sub message có payload lớn rồi chuyển JSON trong bộ nhớ, khiến các batch phát từ producer nội bộ làm tăng heap vượt giới hạn container.
Đội dùng Pub/Sub emulator cho mọi integration test nhưng production có IAM và giới hạn quota khác, khiến kiểm thử không phát hiện lỗi phân quyền thực tế.
Một service xử lý thông điệp Pub/Sub từ nhiều project nhưng chỉ dùng message ID trong một kho dedup chung, khiến việc đối soát không có ngữ cảnh nguồn.
Nhóm muốn replay event Pub/Sub để sửa lỗi lịch sử nhưng retention subscription ngắn hơn thời gian hệ thống bị gián đoạn, khiến dữ liệu cũ không còn để đọc lại.
Một Pub/Sub consumer dùng flow control không phù hợp với kích thước message lớn, khiến số message đang xử lý vượt khả năng RAM dù throughput broker còn cao.
Đội chuyển quy trình từ Pub/Sub pull subscriber sang Cloud Run push endpoint nhưng không kiểm thử sự khác nhau về timeout và retry, khiến request bị xử lý lặp sau khi quá hạn.
Một service dùng Google Cloud Secret Manager để lấy API key đối tác nhưng production role chỉ được quyền xem metadata, khiến lần đọc secret payload thất bại.
Nhóm xoay phiên bản secret trên Google Secret Manager nhưng ứng dụng giữ secret trong singleton đến khi pod restart, khiến việc thu hồi khóa cũ không có hiệu lực ngay.
Đội sử dụng alias phiên bản secret đang hoạt động nhưng không ghi version cụ thể vào audit, khiến khó xác định credential nào đã được dùng khi xảy ra sự cố.
Ứng dụng kết hợp Spring Cloud GCP Secret Manager với biến môi trường cùng tên, khiến khi thay secret ở cloud hành vi thực tế vẫn theo giá trị cũ trong pod.
Nhóm đặt secret của nhiều tenant cùng trong một project nhưng cấp quyền Secret Accessor rộng cho mọi service, khiến ranh giới dữ liệu khách bị phá vỡ.
Một service khởi động cùng lúc hàng trăm pod và mỗi pod gọi Secret Manager để tải nhiều giá trị, khiến quota và độ trễ startup tăng bất thường trong đợt rollout.
Đội dùng Cloud SQL PostgreSQL qua Cloud SQL connector nhưng môi trường CI chỉ thử kết nối TCP trực tiếp, khiến cơ chế IAM và TLS production không được xác minh.
Một Spring Boot service scale nhanh trên Cloud Run và mỗi instance tạo pool Cloud SQL lớn, khiến database chạm giới hạn connections trong đợt lưu lượng tăng.
Nhóm triển khai Cloud SQL failover nhưng JDBC pool không loại kết nối đã hỏng, khiến ứng dụng tiếp tục lỗi ghi sau khi instance mới đã sẵn sàng.
Ứng dụng dùng Cloud Spanner để lưu sự kiện kế toán nhưng một thao tác transaction có tranh chấp bị retry ngoài luồng, khiến side effect HTTP bên ngoài chạy nhiều lần.
Đội thiết kế Cloud Spanner schema cho dữ liệu đơn hàng nhưng chọn khóa hàng tăng tuần tự, khiến ghi tập trung vào phạm vi nóng và latency tăng trong giờ cao điểm.
Một dịch vụ truy vấn Firestore theo nhiều trường mới nhưng index cần thiết chưa tồn tại, khiến tính năng tìm kiếm chỉ thất bại với điều kiện lọc production.
Nhóm dùng Firestore transaction để cập nhật hai hồ sơ nhưng đặt gọi API thanh toán trong callback có thể được thực thi lại khi tranh chấp, khiến đối tác nhận lệnh trùng.
Một ứng dụng Spring Boot ghi log phân tích vào BigQuery theo từng dòng bằng lời gọi nhỏ lẻ, khiến độ trễ và chi phí thao tác tăng mạnh khi lượng sự kiện tăng.
Đội thiết lập partition cho bảng BigQuery theo ngày nhưng job báo cáo lọc sai trường thời gian, khiến truy vấn quét nhiều dữ liệu hơn dự tính và vượt ngân sách.
Một hệ thống dùng Cloud Storage và Pub/Sub để chuyển dữ liệu sang BigQuery nhưng không lưu checkpoint end-to-end, khiến một batch đã nạp thành công vẫn được nhập thêm sau crash.
Nhóm phát hành cùng một chức năng lưu tài liệu trên AWS S3, Azure Blob và Google Cloud Storage, nhưng abstraction chung giả định cả ba hỗ trợ object version và quyền tải giống hệt nhau.
Một thư viện Spring Boot định nghĩa interface lưu object dùng chung ba cloud, nhưng provider Azure cần SAS còn AWS/GCP dùng kiểu URL ký khác khiến API public không nhất quán về hạn truy cập.
Đội chuyển event pipeline từ AWS SQS sang Azure Service Bus mà giữ giả định về visibility timeout, khiến consumer không xử lý đúng message lock và trạng thái hoàn tất.
Một hệ thống tích hợp SNS, Azure Event Grid và Google Pub/Sub nhưng không lưu nguồn và phiên bản event, khiến cùng một sự kiện từ hai tuyến bị ghi nhận thành hai giao dịch.
Nhóm dùng một model Java cho Pub/Sub, Event Hubs và Kafka nhưng không phân biệt ordering key/partition/session, khiến giả định thứ tự xử lý khác nhau giữa provider.
Ứng dụng có cơ chế retry chung cho SQS, Service Bus và Pub/Sub mà không xét dead-letter policy và ACK/settlement từng nền tảng, khiến cùng lỗi có kết quả xử lý khác nhau.
Đội phát triển tái sử dụng cùng cấu hình credentials cho AWS, Azure và GCP qua profile Spring, nhưng thứ tự nạp biến môi trường làm workload staging dùng nhầm quyền production.
Một service tích hợp đa cloud theo customer region nhưng chọn storage provider dựa trên header từ client không kiểm chứng, khiến hồ sơ có thể bị lưu ngoài vùng được phép.
Nhóm đánh giá chi phí object storage chỉ theo dung lượng, bỏ qua số request, data egress và replication giữa AWS, Azure, GCP khiến tổng chi phí triển khai vượt ngân sách.
Một hệ thống di trú tệp từ S3 sang Blob Storage và GCS nhưng không giữ checksum end-to-end, khiến một số object bị thay đổi encoding mà quy trình đối soát không phát hiện.
Đội thử cùng một luồng nghiệp vụ trên LocalStack, Azurite và Pub/Sub emulator, nhưng giả định rằng giả lập hỗ trợ đầy đủ IAM, SLA và semantics của dịch vụ managed thật.
Một pipeline CI chạy integration test chỉ với mock AWS SDK rồi phát hành bản triển khai Azure, khiến lỗi managed identity và Service Bus lock chỉ xuất hiện sau khi lên production.
Nhóm dùng Testcontainers để chạy database cục bộ cho cả ba cloud, nhưng không có bài kiểm thử kết nối thật tới RDS, Azure SQL và Cloud SQL qua cơ chế xác thực production.
Ứng dụng kết nối storage qua endpoint private của từng cloud nhưng bài test chỉ chạy trên máy có internet công cộng, khiến lỗi private DNS không được phát hiện trước rollout.
Đội xây dashboard chung cho AWS SQS, Azure Service Bus và GCP Pub/Sub nhưng gộp mọi chỉ số backlog theo một tên không xét cách đo khác nhau, khiến so sánh SLA sai lệch.
Một hệ thống dùng cùng correlation ID xuyên S3 event, Azure Service Bus và Pub/Sub, nhưng một adapter chuyển message làm mất attributes khiến không thể lần theo vòng đời giao dịch.
Nhóm bật log debug để điều tra lỗi SDK đa cloud, khiến SAS token Azure, đường dẫn signed URL và metadata chứa dữ liệu khách bị sao chép vào kho log tập trung.
Một service dùng Spring profiles để chọn nhà cung cấp cloud nhưng artifact chứa cả bộ cấu hình endpoint, khiến khi đổi profile production một adapter không cần thiết vẫn khởi tạo client.
Đội triển khai Spring Cloud AWS, Spring Cloud Azure và Spring Cloud GCP vào cùng ứng dụng nhưng các BOM/starter phụ thuộc phiên bản không tương thích gây lỗi khởi tạo bean khi upgrade.
Một tổ chức di chuyển từ cloud này sang cloud khác nhưng không duy trì bản đồ tính năng Secret Manager, Key Vault và Google Secret Manager, khiến kế hoạch xoay khóa có khoảng trống bảo mật.
Nhóm triển khai active-active trên AWS và GCP với hai queue riêng nhưng không xác định nguồn phát lệnh chính, khiến một yêu cầu thanh toán được gửi xử lý ở cả hai vùng.
Ứng dụng ghi cùng bản ghi nghiệp vụ vào DynamoDB và Cosmos DB trong một HTTP request rồi coi thao tác như transaction nguyên tử, khiến dữ liệu hai cloud lệch sau lỗi mạng.
Đội thử failover giữa Azure SQL và Cloud SQL nhưng không xác minh điểm đồng bộ cuối và khóa idempotency, khiến sau chuyển vùng một số giao dịch bị mất hoặc thực hiện lại.
Một service xử lý dữ liệu khách thuộc nhiều quốc gia bằng storage ở ba cloud, nhưng chỉ cấu hình khu vực lưu trữ mà không kiểm tra nơi log, backup và event metadata được lưu.
Nhóm chạy smoke test sau deploy bằng cách đọc health endpoint Spring Boot, nhưng các quyền IAM, Azure RBAC và GCP IAM của từng adapter chỉ lỗi khi có request thực.
Đội định triển khai thay đổi quyền workload mà không thay artifact, nhưng không có audit liên kết IAM role, managed identity và service account với phiên bản ứng dụng đang chạy.
Một tổ chức xây bộ contract test dùng chung cho storage và messaging, nhưng chỉ xác minh kết quả thành công mà bỏ qua lỗi throttling, expired credentials và redelivery khác nhau giữa ba provider.
Nhóm chuẩn hóa lỗi AWS SDK, Azure SDK và Google Cloud client thành một exception chung, khiến API không phân biệt được quota tạm thời với lỗi quyền cần can thiệp vận hành.
Một hệ thống xử lý event liên cloud nhưng thời gian đồng hồ của các nguồn không đồng bộ, khiến dashboard xếp sai thứ tự thay đổi khi dùng timestamp phía producer.
Đội vận hành đặt health check cho ba cloud bằng lời gọi đọc dữ liệu thật mỗi giây, khiến các API quản trị và storage tăng chi phí cùng nguy cơ bị rate limited trong giờ cao điểm.
Nhóm thay cloud provider của một tenant bằng feature flag nhưng không đảm bảo các message cũ trong queue đã hoàn tất, khiến bản ghi lịch sử vẫn cập nhật vào hệ thống cũ sau chuyển đổi.
Một ứng dụng serverless trên AWS và container Azure cùng dùng một thư viện Spring Boot tích hợp, nhưng giới hạn concurrency, thời gian sống và connection pooling khác nhau gây lỗi ở một runtime.
Đội audit yêu cầu chứng minh từng hóa đơn được lưu và phát event dưới danh tính cloud nào, nhưng trace không mang tên account/subscription/project và version cấu hình tương ứng.
Một đội thử nghiệm phá kết nối mạng giữa Spring Boot và AWS, Azure, GCP trong lúc ghi dữ liệu nhưng không xác minh xem backend đã commit hay chưa, khiến chính sách retry tạo bản sao sau khi mạng phục hồi.
Một hệ thống có quy trình xóa dữ liệu người dùng nhưng bản gốc ở S3 đã xóa còn bản sao trong Azure Blob và GCS vẫn tồn tại, khiến cam kết xóa xuyên cloud không được đáp ứng.
Nhóm muốn đo tổng chi phí chuyển dữ liệu từ AWS sang Azure và GCP nhưng telemetry chỉ có lưu lượng nội bộ ứng dụng, không phản ánh các khoản egress được nhà cung cấp tính phí.
Một service phát hành ra ba cloud cùng lúc nhưng các chính sách secret rotation và certificate trust không được kiểm thử ở cả ba môi trường, khiến chỉ một vùng bị gián đoạn sau đợt đổi khóa.
