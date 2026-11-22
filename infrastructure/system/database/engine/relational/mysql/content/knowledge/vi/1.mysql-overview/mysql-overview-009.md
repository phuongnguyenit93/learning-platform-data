# Community, Enterprise, dịch vụ quản lý và điều kiện sử dụng tính năng

MySQL có thể được triển khai trên máy chủ do đội ngũ tự vận hành hoặc dùng dưới dạng dịch vụ cơ sở dữ liệu trên cloud. Khi lựa chọn, cần trả lời riêng ba câu hỏi: **đang dùng edition và giấy phép nào**, **ai vận hành máy chủ**, và **nhà cung cấp có hỗ trợ tính năng cần thiết trên đúng phiên bản hay không**. Ba câu hỏi này liên quan với nhau nhưng không đồng nghĩa.

Bài học đặt các lựa chọn trong phạm vi `DATABASE_MYSQL`: làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction và kiểm soát đồng thời; đồng thời biết đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý vấn đề vận hành cơ sở dữ liệu quan hệ. Việc chọn Community, Enterprise hay dịch vụ quản lý ảnh hưởng trực tiếp đến những thao tác vận hành và tính năng có thể sử dụng trong các công việc đó.

## 1. Phân biệt edition, mô hình triển khai và dịch vụ cloud

Có ba lớp khái niệm thường bị gộp làm một:

1. **Edition và giấy phép của phần mềm MySQL** xác định quyền sử dụng, thành phần đi kèm, công cụ thương mại và hỗ trợ từ Oracle. Ví dụ: MySQL Community Edition và MySQL Enterprise Edition.
2. **Mô hình triển khai** xác định ai quản lý hệ điều hành, máy chủ, tiến trình MySQL, bản vá, sao lưu và khả năng sẵn sàng. Ví dụ: tự cài MySQL trên máy ảo hoặc thuê dịch vụ cơ sở dữ liệu được quản lý.
3. **Sản phẩm của nhà cung cấp cloud** xác định bộ tính năng cụ thể, cách cấu hình, giới hạn quyền, phiên bản được hỗ trợ và cách tính phí. Ví dụ: Amazon RDS for MySQL, Cloud SQL for MySQL, Azure Database for MySQL Flexible Server hoặc MySQL HeatWave.

Một dịch vụ cloud có thể cung cấp MySQL Community Edition đã được quản lý. Dịch vụ đó có thể bổ sung sao lưu tự động, giám sát và chuyển đổi dự phòng, nhưng điều này **không tự động biến nó thành MySQL Enterprise Edition**. Ngược lại, một tổ chức có thể mua Enterprise Edition nhưng vẫn tự cài đặt và vận hành trên hạ tầng của mình.

Khi đọc tài liệu sản phẩm, hãy tìm chính xác tên engine, edition, phiên bản, dịch vụ và gói dịch vụ. Tên thương mại có chữ “Enterprise” của một nhà cung cấp cloud cũng không nhất thiết là MySQL Enterprise Edition của Oracle.

## 2. MySQL Community Edition

MySQL Community Edition là lựa chọn mã nguồn mở của MySQL, được cung cấp theo giấy phép GPLv2 cùng các điều khoản bổ sung áp dụng cho một số thành phần. Người dùng có thể tải xuống, cài đặt, sử dụng và nghiên cứu mã nguồn theo điều kiện của giấy phép tương ứng. Đây là lựa chọn phổ biến cho học tập, phát triển ứng dụng, thử nghiệm và nhiều hệ thống sản xuất.

### 2.1. Năng lực nền tảng

Community Server cung cấp nền tảng cơ sở dữ liệu quan hệ mà ứng dụng MySQL thường cần, bao gồm:

- Cơ sở dữ liệu, bảng, view, index và các kiểu dữ liệu SQL.
- InnoDB với transaction ACID, commit, rollback, phục hồi sau sự cố và khóa ở mức hàng.
- Ràng buộc dữ liệu, khóa chính, khóa ngoại và tính toàn vẹn tham chiếu.
- Các câu lệnh truy vấn, thao tác dữ liệu, stored routine và trigger theo phạm vi phiên bản.
- Tài khoản, role và cơ chế phân quyền của MySQL.
- Replication và các khả năng sẵn sàng cao được hỗ trợ bởi phiên bản, cấu hình và kiến trúc triển khai.
- Công cụ dòng lệnh và các connector để ứng dụng kết nối qua giao thức MySQL.

Những năng lực này đủ để học và thực hành hầu hết kiến thức SQL cốt lõi: thiết kế schema, chọn kiểu dữ liệu, tạo index, đọc `EXPLAIN`, xử lý transaction, điều tra deadlock, quản lý tài khoản và xây dựng quy trình sao lưu/khôi phục.

### 2.2. Chi phí thực tế

“Miễn phí tải về” không có nghĩa hệ thống không tốn chi phí. Khi tự vận hành Community, tổ chức vẫn phải tính đến:

- Máy chủ, CPU, RAM, lưu trữ, mạng và bản sao dự phòng.
- Nhân sự cài đặt, nâng cấp, vá lỗi, giám sát và xử lý sự cố.
- Thiết kế sao lưu, lưu bản sao ngoài máy chủ chính và kiểm thử khôi phục.
- Thiết lập HA/DR, phân quyền, mã hóa, kiểm toán và quy trình ứng phó sự cố.
- Thời gian đánh giá tương thích khi nâng cấp phiên bản hoặc thay đổi plugin.

Community phù hợp khi đội ngũ có năng lực vận hành cần thiết, tính năng mã nguồn mở đáp ứng yêu cầu và tổ chức chấp nhận tự chịu trách nhiệm về hỗ trợ kỹ thuật cũng như vòng đời hệ thống.

## 3. MySQL Enterprise Edition

MySQL Enterprise Edition là sản phẩm thương mại của Oracle. Edition này bao gồm MySQL Server và bổ sung các thành phần, công cụ quản trị, bảo mật, khả năng mở rộng và dịch vụ hỗ trợ theo gói thương mại. Cả Community và Enterprise đều dựa trên MySQL Server; khác biệt cần quan tâm là những thành phần thương mại, quyền sử dụng và mức hỗ trợ đi kèm.

Các nhóm tính năng thường được nhắc đến trong Enterprise gồm:

| Nhóm | Ví dụ năng lực | Giá trị vận hành |
|---|---|---|
| Sao lưu và phục hồi | MySQL Enterprise Backup, sao lưu nóng, full/incremental/partial backup, phục hồi theo thời điểm | Giảm thời gian dừng khi sao lưu và hỗ trợ khôi phục chi tiết |
| Kiểm toán | MySQL Enterprise Audit | Ghi nhận hoạt động theo chính sách để phục vụ điều tra và yêu cầu tuân thủ |
| Tường lửa cơ sở dữ liệu | MySQL Enterprise Firewall | Xây dựng allowlist câu lệnh SQL, phát hiện hoặc chặn câu lệnh ngoài chính sách |
| Bảo mật dữ liệu | TDE, Enterprise Encryption, Data Masking | Bảo vệ dữ liệu lưu trữ, hỗ trợ thao tác mã hóa và che giấu dữ liệu nhạy cảm |
| Xác thực | Enterprise Authentication | Tích hợp một số cơ chế xác thực bên ngoài như PAM hoặc Windows/Active Directory theo cấu hình hỗ trợ |
| Khả năng mở rộng | MySQL Thread Pool | Quản lý luồng xử lý kết nối/câu lệnh trong những tải phù hợp |
| Giám sát | Enterprise Telemetry và công cụ quản trị liên quan | Thu thập chỉ số, tracing và hỗ trợ theo dõi vận hành |
| Hỗ trợ | Oracle Premier Support theo điều khoản subscription | Có kênh hỗ trợ kỹ thuật và cập nhật theo hợp đồng |

Danh sách trên giúp định hướng đánh giá, không phải cam kết rằng mọi tính năng đều có trong mọi phiên bản, mọi hệ điều hành hoặc mọi gói thương mại. Oracle có thể thay đổi danh mục, tên thành phần, điều kiện cấp phép và nền tảng được chứng nhận. Trước khi thiết kế dựa vào một tính năng, cần kiểm tra trang so sánh edition và tài liệu của đúng phiên bản.

### 3.1. Khi nào nên cân nhắc Enterprise?

Enterprise đáng được đánh giá khi yêu cầu của hệ thống cần một hoặc nhiều năng lực thương mại cụ thể, chẳng hạn:

- Chính sách kiểm toán ở mức cơ sở dữ liệu cần công cụ và cơ chế hỗ trợ chuyên biệt.
- Tổ chức cần xác thực tập trung qua hạ tầng danh tính hiện có.
- Yêu cầu mã hóa dữ liệu lưu trữ, quản lý khóa hoặc che giấu dữ liệu cần đối chiếu với các thành phần Enterprise.
- Tải kết nối lớn cần đánh giá Thread Pool bằng benchmark trên workload thực tế.
- Quy trình sao lưu cần các khả năng của Enterprise Backup và cần hỗ trợ chính thức từ Oracle.
- Hợp đồng vận hành yêu cầu kênh hỗ trợ, thời gian phản hồi hoặc phạm vi cập nhật cụ thể.

Không nên mua Enterprise chỉ vì hệ thống “quan trọng” hoặc vì tên edition nghe phù hợp với doanh nghiệp. Hãy chuyển yêu cầu thành tiêu chí kiểm chứng được, xác định tính năng nào đáp ứng tiêu chí đó, rồi so sánh chi phí subscription với chi phí tự xây dựng và vận hành giải pháp tương đương.

## 4. Giấy phép: điều cần xác minh trước khi sử dụng và phân phối

MySQL sử dụng mô hình cấp phép kép. Tùy phần mềm và thành phần, người dùng có thể sử dụng theo GPLv2 hoặc mua giấy phép thương mại từ Oracle. Một số thư viện client còn có ngoại lệ bổ sung như Universal FOSS Exception. Không nên suy luận điều kiện của toàn bộ sản phẩm chỉ từ tên “MySQL” hoặc từ giấy phép của một thư viện riêng lẻ.

Cần phân biệt các tình huống sau:

- **Chạy MySQL cho nhu cầu nội bộ:** xác định giấy phép của bản phân phối và các thành phần thực sự sử dụng; tuân thủ các điều khoản tương ứng.
- **Sửa đổi hoặc phân phối lại MySQL:** phải xem nghĩa vụ đi kèm giấy phép của mã nguồn/binary được sửa đổi và cách phân phối.
- **Nhúng, đóng gói hoặc phân phối MySQL cùng sản phẩm thương mại:** cần rà soát kỹ mô hình dual licensing, thư viện client được liên kết và điều kiện thương mại dành cho OEM/ISV/VAR.
- **Chỉ kết nối ứng dụng đến máy chủ qua giao thức MySQL:** đây là một tình huống kỹ thuật khác với việc nhúng hoặc phân phối binary/thư viện; vẫn cần đánh giá toàn bộ thành phần được dùng và cách phát hành sản phẩm.

Các quy tắc trên là hướng dẫn để nhận diện vấn đề, không thay thế tư vấn pháp lý. Trước khi phát hành sản phẩm, hãy đọc License Information User Manual của đúng bản tải xuống, điều khoản GPL và ngoại lệ liên quan, hợp đồng thương mại nếu có, rồi nhờ bộ phận pháp chế xác nhận trường hợp phân phối cụ thể.

Cũng cần phân biệt **MySQL Standard Edition** với **MySQL Community Edition**. Standard Edition là một lựa chọn thương mại trong danh mục edition của Oracle; không phải tên khác của bản Community miễn phí. So sánh phải dựa trên ma trận sản phẩm hiện hành thay vì suy ra từ chữ “Standard”, “Community” hoặc “Enterprise”.

## 5. Dịch vụ MySQL được quản lý

Dịch vụ cơ sở dữ liệu được quản lý (managed database service) cung cấp MySQL dưới dạng dịch vụ. Nhà cung cấp đảm nhiệm một phần công việc hạ tầng và vận hành; phạm vi cụ thể tùy sản phẩm, cấu hình và gói dịch vụ.

### 5.1. Phần việc thường được nhà cung cấp đảm nhiệm

Một dịch vụ có thể hỗ trợ các công việc sau:

- Cấp phát máy chủ, CPU, RAM, lưu trữ và mạng.
- Cài đặt engine, quản lý một số bản vá và quy trình bảo trì.
- Sao lưu tự động, sao lưu theo yêu cầu và khôi phục theo thời điểm.
- Giám sát chỉ số, log và cảnh báo.
- Tạo replica, triển khai HA và tự động chuyển đổi dự phòng theo cấu hình.
- Mã hóa dữ liệu lưu trữ hoặc đường truyền theo chính sách của dịch vụ.
- Cấp API, console hoặc công cụ để tạo, thay đổi và quản lý instance.

Không được giả định mọi dịch vụ đều bật sẵn tất cả các khả năng này. Một số khả năng có thể cần cấu hình riêng, có giới hạn theo tier, region, phiên bản, loại instance hoặc mức phí.

### 5.2. Phần trách nhiệm vẫn thuộc về đội ngũ sử dụng

Dùng managed service không loại bỏ trách nhiệm quản trị dữ liệu và ứng dụng. Đội ngũ vẫn phải:

- Thiết kế schema, kiểu dữ liệu, khóa, index và transaction phù hợp.
- Viết và tối ưu SQL; kiểm tra kế hoạch thực thi và tải truy vấn.
- Quản lý user, role, quyền truy cập và thông tin xác thực ở cấp được dịch vụ cho phép.
- Thiết kế mạng, secret, kết nối TLS và ranh giới truy cập từ ứng dụng.
- Chọn retention, lịch backup, mục tiêu RPO/RTO và kiểm thử restore định kỳ.
- Theo dõi dung lượng, hiệu năng, giới hạn kết nối, chi phí và mức tăng trưởng.
- Lập kế hoạch nâng cấp phiên bản, kiểm thử tương thích và chuẩn bị phương án rollback/migration.
- Xác định trách nhiệm ứng phó sự cố, bảo vệ dữ liệu và tuân thủ.

Nhà cung cấp có thể thực hiện backup nhưng tổ chức vẫn cần kiểm chứng rằng bản backup đáp ứng yêu cầu và có thể khôi phục được. Có backup chưa đồng nghĩa đã có quy trình DR tốt.

### 5.3. Ví dụ về các dịch vụ và giới hạn cần kiểm tra

| Dịch vụ | Mô tả khái quát | Điểm cần kiểm tra |
|---|---|---|
| Oracle MySQL HeatWave | Dịch vụ MySQL được quản lý trên OCI; có các khả năng HeatWave cho analytics, machine learning và Lakehouse tùy cấu hình | Phiên bản, cấu hình DB system, tính năng HeatWave được bật, region, giá và giới hạn dịch vụ |
| Amazon RDS for MySQL | Dịch vụ quản lý MySQL; hỗ trợ nhiều khả năng của MySQL và tự động hóa một phần vận hành | Một số tính năng/plugin không được hỗ trợ hoặc bị giới hạn quyền; không có quyền shell trực tiếp vào host |
| Google Cloud SQL for MySQL | Dịch vụ MySQL Community Edition được quản lý, có backup, PITR, HA và giám sát theo cấu hình | Giới hạn plugin, engine, câu lệnh thao tác file và các quyền quản trị cấp cao |
| Azure Database for MySQL Flexible Server | Dịch vụ MySQL được quản lý với lựa chọn compute, storage, backup và HA | Một số quyền như SUPER, FILE, CREATE TABLESPACE bị giới hạn; không truy cập trực tiếp filesystem của máy chủ |

Một vài ví dụ cụ thể cho thấy vì sao cần đọc ma trận hỗ trợ:

- Tài liệu Amazon RDS nêu các tính năng MySQL không được hỗ trợ trong RDS, đồng thời cho biết dịch vụ không cung cấp quyền truy cập shell vào DB instance và giới hạn một số quyền/thủ tục hệ thống. Vì vậy, một quy trình vận hành cần SSH vào host hoặc cài plugin tùy ý có thể không phù hợp.
- Cloud SQL for MySQL công bố danh sách engine, plugin, câu lệnh và quyền không hỗ trợ. Ví dụ, dịch vụ không cho phép `INSTALL PLUGIN`, `SELECT ... INTO OUTFILE` hoặc một số thao tác cần quyền FILE; `LOAD DATA LOCAL INFILE` được hỗ trợ trong điều kiện tài liệu nêu.
- Azure Database for MySQL Flexible Server giới hạn một số quyền quản trị cấp cao và không cho truy cập filesystem nền. Tài liệu hiện hành liệt kê InnoDB và MEMORY trong nhóm storage engine hỗ trợ, đồng thời nêu MyISAM là engine không hỗ trợ.
- MySQL HeatWave là một sản phẩm managed service có các khả năng riêng như HeatWave Query Accelerator, AutoML, Lakehouse và GenAI. Đây là phạm vi dịch vụ cần đánh giá theo kiến trúc và gói sử dụng cụ thể.

Các ví dụ này không phải bảng so sánh đầy đủ và có thể thay đổi theo phiên bản. Hãy mở tài liệu chính thức của nhà cung cấp, chọn đúng engine version đang triển khai, rồi xác minh từng tính năng trước khi cam kết kiến trúc.

### 5.4. MySQL-compatible không đồng nghĩa MySQL Server giống hệt

Một số sản phẩm cloud cung cấp engine tương thích MySQL nhưng có kiến trúc và vòng đời riêng. Amazon Aurora MySQL-Compatible là ví dụ: ứng dụng có thể dùng giao thức và nhiều cú pháp quen thuộc của MySQL, nhưng engine, cách lưu trữ, replication, giới hạn và lịch phát hành có thể khác MySQL Community Server hoặc RDS for MySQL.

Khi chuyển giữa các engine tương thích, cần kiểm tra:

- Phiên bản nguồn và phiên bản đích có tương thích hay không.
- SQL, kiểu dữ liệu, collation, function, trigger, stored routine và plugin được hỗ trợ.
- Cách hoạt động của transaction, isolation, locking và replication.
- Giới hạn kết nối, kích thước dữ liệu, index và câu lệnh quản trị.
- Công cụ dump/restore, CDC, migration và thời gian chuyển đổi.
- Hành vi failover, read replica, backup và khôi phục.
- Hiệu năng trên workload thực tế, không chỉ kết quả benchmark tổng hợp.

Tên “MySQL-compatible” là tín hiệu để bắt đầu kiểm tra tương thích, không phải bằng chứng rằng mọi tính năng MySQL đều hoạt động giống nhau.

## 6. Điều kiện để một tính năng có thể sử dụng

Một tính năng chỉ dùng được khi tất cả điều kiện liên quan đều thỏa mãn. Có thể kiểm tra theo các lớp sau:

| Lớp kiểm tra | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Edition và giấy phép | Tính năng thuộc Community hay chỉ có trong edition thương mại? Subscription có hiệu lực không? | Enterprise Audit, Enterprise Backup, Thread Pool |
| Phiên bản engine | Tính năng xuất hiện từ phiên bản nào, có bị deprecated hoặc loại bỏ không? | Plugin hoặc biến cấu hình thay đổi giữa các major version |
| Bản build và hệ điều hành | Nhà cung cấp có build và chứng nhận tính năng cho nền tảng này không? | Plugin phụ thuộc thư viện hệ thống hoặc nền tảng được chứng nhận |
| Dịch vụ cloud | Dịch vụ, region, tier và engine version có hỗ trợ không? | RDS, Cloud SQL hoặc Azure giới hạn một số plugin/câu lệnh |
| Quyền tài khoản | User hiện tại có quyền thực hiện thao tác không? | `SUPER`, `FILE`, `CREATE TABLESPACE` có thể bị giới hạn |
| Cấu hình | Cần bật parameter, component, plugin, option group hay chế độ HA nào? | Bật binary log hoặc cấu hình TLS |
| Kiến trúc | Tính năng có tương thích với replication, failover hoặc topology hiện tại không? | Một số cấu hình replication chỉ được hỗ trợ trên topology nhất định |
| Hợp đồng và vận hành | Tính năng có nằm trong gói hỗ trợ, SLA và quy trình vận hành đã mua không? | Phạm vi support, retention backup, thời gian lưu log |

Không nên kết luận một tính năng “không có” chỉ vì lệnh hiện tại báo lỗi. Nguyên nhân có thể là thiếu quyền, chưa bật cấu hình, khác phiên bản hoặc nhà cung cấp đã chủ động chặn thao tác. Ngược lại, lệnh tạo được object cũng không chứng minh rằng toàn bộ hành vi vận hành đã được hỗ trợ trong production.

### 6.1. Kiểm tra thông tin máy chủ đang kết nối

Các lệnh sau giúp nhận diện môi trường cơ bản:

    SELECT VERSION() AS mysql_version,
           @@version_comment AS distribution;

    SHOW ENGINES;
    SHOW PLUGINS;
    SHOW GRANTS;

Ý nghĩa:

- `VERSION()` cho biết phiên bản engine mà client đang kết nối.
- `@@version_comment` cung cấp thông tin mô tả bản phân phối.
- `SHOW ENGINES` liệt kê storage engine và trạng thái hỗ trợ mà server công bố.
- `SHOW PLUGINS` liệt kê plugin được nạp và trạng thái của chúng.
- `SHOW GRANTS` cho biết quyền của tài khoản hiện tại.

Các lệnh trên không tạo ra một báo cáo tương thích đầy đủ. Một số dịch vụ có thể lọc thông tin hoặc giới hạn câu lệnh quản trị; một số thành phần được triển khai dưới dạng component thay vì plugin. Hãy kết hợp kết quả với tài liệu edition, release notes và feature support của nhà cung cấp.

### 6.2. Lập ma trận tính năng trước khi chọn nền tảng

Ví dụ, nếu ứng dụng cần backup theo thời điểm, kiểm toán, plugin tùy chỉnh và quyền quản trị hệ điều hành, có thể lập bảng kiểm tra như sau:

| Yêu cầu | Cách xác minh | Kết quả cần ghi |
|---|---|---|
| Point-in-time recovery | Đọc chính sách backup/binlog và thử restore tới mốc thời gian | Có/không, thời gian lưu, RPO |
| Audit database | Xác định audit cần ghi sự kiện nào; kiểm tra edition hoặc dịch vụ có hỗ trợ | Thành phần, loại sự kiện, nơi lưu log |
| Cài plugin riêng | Kiểm tra quyền cài plugin và danh sách plugin được dịch vụ cho phép | Được phép/bị chặn, phương án thay thế |
| Truy cập host | Kiểm tra mô hình quản lý và quyền truy cập máy chủ | Có/không, cơ chế hỗ trợ sự cố |
| HA và failover | Đọc giới hạn topology; thử chuyển đổi dự phòng | RTO thực đo, ảnh hưởng kết nối |
| Khôi phục dữ liệu | Khôi phục vào môi trường riêng và xác minh dữ liệu | Thời gian restore, tính toàn vẹn, quy trình |

Ghi lại phiên bản, ngày kiểm tra, region, cấu hình, gói dịch vụ và đường dẫn tài liệu. Ma trận có ngày kiểm tra giúp đội ngũ nhận ra khi nào cần đánh giá lại sau khi nhà cung cấp cập nhật dịch vụ.

## 7. Chọn Community, Enterprise hay managed service?

Không có lựa chọn tốt nhất cho mọi hệ thống. Hãy bắt đầu từ yêu cầu vận hành và năng lực của đội ngũ.

| Tình huống | Hướng lựa chọn để đánh giá | Lý do |
|---|---|---|
| Học SQL, phát triển ứng dụng, thử nghiệm tính năng lõi | Community Server | Dễ tiếp cận, phù hợp thực hành nền tảng |
| Tự quản lý hạ tầng và cần quyền kiểm soát host/plugin | Community hoặc Enterprise tự triển khai | Chủ động cấu hình hệ điều hành, engine và topology |
| Cần tính năng bảo mật, audit, backup hoặc support thương mại cụ thể | Đánh giá Enterprise Edition | Có các thành phần thương mại và hợp đồng hỗ trợ tương ứng |
| Muốn giảm công việc cấp phát, vá lỗi, backup và HA | Đánh giá managed service | Nhà cung cấp đảm nhiệm một phần vận hành hạ tầng |
| Cần plugin hoặc quyền quản trị đặc biệt | Ưu tiên kiểm thử self-managed hoặc tìm dịch vụ xác nhận hỗ trợ | Managed service thường giới hạn quyền host và thao tác hệ thống |
| Cần analytics/ML tích hợp với MySQL | Đánh giá MySQL HeatWave và kiến trúc dữ liệu | Có các khả năng phân tích riêng của dịch vụ |
| Đang chuyển từ MySQL sang engine tương thích | Thực hiện kiểm thử tương thích và benchmark | Cú pháp tương tự không bảo đảm hành vi giống nhau |

Một quy trình chọn lựa thực tế:

1. **Liệt kê yêu cầu bắt buộc.** Ví dụ: PITR tối thiểu 7 ngày, audit thao tác quản trị, mã hóa at-rest, HA đa vùng, plugin riêng hoặc quyền truy cập host.
2. **Phân loại yêu cầu theo tầng.** Yêu cầu nào thuộc engine, edition, hệ điều hành, cloud provider, network hay quy trình vận hành?
3. **Chọn phiên bản mục tiêu.** Dùng đúng major/minor version dự kiến triển khai để kiểm tra release notes và ma trận hỗ trợ.
4. **Đối chiếu giấy phép.** Xác định cách sử dụng, sửa đổi, nhúng và phân phối phần mềm; kiểm tra hợp đồng thương mại nếu cần.
5. **Thử nghiệm trên đúng dịch vụ.** Dùng cùng phiên bản, region, tier, parameter group và quyền user như môi trường dự kiến.
6. **Đo vận hành và chi phí.** Kiểm tra hiệu năng, failover, backup/restore, giám sát, giới hạn và tổng chi phí.
7. **Ghi quyết định và điều kiện thay đổi.** Lưu lại lý do chọn, tính năng phụ thuộc, giới hạn đã chấp nhận và dấu hiệu cần đánh giá lại.

## 8. Tình huống thực hành: ứng dụng cần import dữ liệu và plugin riêng

Giả sử một ứng dụng có hai yêu cầu:

- Import tệp dữ liệu bằng `LOAD DATA INFILE`.
- Cài một plugin riêng để tích hợp với hệ thống nội bộ.

Nhóm phát triển thử trên MySQL cài trực tiếp và cả hai thao tác đều hoạt động. Sau đó nhóm chuyển sang managed service và gặp lỗi quyền hoặc lỗi không hỗ trợ câu lệnh.

Không nên xử lý bằng cách cấp thêm quyền một cách mù quáng. Hãy điều tra theo thứ tự:

1. Xác nhận dịch vụ và phiên bản thực tế bằng `SELECT VERSION(), @@version_comment;`.
2. Tra tài liệu feature support của đúng dịch vụ và phiên bản để biết câu lệnh/plugin có được hỗ trợ không.
3. Phân biệt lỗi quyền với giới hạn sản phẩm. Nếu dịch vụ chặn `INSTALL PLUGIN` hoặc không hỗ trợ plugin đó, quyền quản trị cao hơn trong database cũng không giải quyết được.
4. Với import, xác định dịch vụ có hỗ trợ `LOAD DATA LOCAL INFILE`, cơ chế upload/import riêng hoặc đường truyền dữ liệu thay thế hay không.
5. Nếu plugin là yêu cầu không thể thay thế, so sánh self-managed MySQL với các dịch vụ cho phép plugin đó.
6. Chạy lại kiểm thử bảo mật, hiệu năng và khôi phục trên kiến trúc được chọn.

Kết quả có thể là thay đổi quy trình import, thay plugin bằng một thành phần ở tầng ứng dụng, chọn managed service khác hoặc tự vận hành MySQL. Quyết định phải dựa trên yêu cầu nghiệp vụ và giới hạn được xác minh, không dựa vào tên sản phẩm.

## 9. Checklist trước khi đưa vào production

- [ ] Đã xác định rõ Community, Enterprise, Standard hay engine MySQL-compatible.
- [ ] Đã đọc điều khoản giấy phép của đúng bản phân phối và thư viện được sử dụng.
- [ ] Đã xác minh cách sử dụng/đóng gói/phân phối sản phẩm với bộ phận phụ trách pháp lý khi cần.
- [ ] Đã ghi lại engine version, edition, provider, region, tier và cấu hình.
- [ ] Đã đối chiếu mọi tính năng bắt buộc với tài liệu chính thức của đúng phiên bản.
- [ ] Đã kiểm tra quyền tài khoản, plugin/component, storage engine và tham số liên quan.
- [ ] Đã thử backup và restore; có RPO/RTO mục tiêu và kết quả đo thực tế.
- [ ] Đã thử HA/failover và hành vi kết nối lại của ứng dụng.
- [ ] Đã đo tải truy vấn, index, transaction, lock và giới hạn kết nối trên môi trường tương đương production.
- [ ] Đã xác định phần việc của nhà cung cấp và phần việc của đội ngũ.
- [ ] Đã tính chi phí compute, storage, I/O, backup, network, support và nhân lực vận hành.
- [ ] Đã lưu ma trận tương thích, ngày xác minh và kế hoạch đánh giá lại khi nâng cấp.

## 10. Kết luận

Community và Enterprise là lựa chọn về edition, giấy phép, thành phần và hỗ trợ của MySQL. Managed service là lựa chọn về mô hình vận hành do nhà cung cấp thực hiện một phần. Một dịch vụ quản lý có thể dựa trên MySQL Community nhưng cung cấp backup, HA và giám sát; đồng thời dịch vụ đó có thể giới hạn plugin, quyền quản trị hoặc câu lệnh hệ thống.

Để chọn đúng, hãy biến yêu cầu thành danh sách tính năng và mục tiêu vận hành, xác minh trên đúng phiên bản/edition/dịch vụ, rồi thử nghiệm backup, restore, failover và workload thật. Cách làm này giúp tránh chọn nền tảng chỉ dựa vào tên edition hoặc lời giới thiệu tổng quát.

## Tài liệu tham khảo chính thức

- [MySQL 8.4 Reference Manual – General Information và mô hình dual licensing](https://dev.mysql.com/doc/refman/8.4/en/introduction.html)
- [MySQL – Compare Editions](https://www.mysql.com/products/enterprise/compare/)
- [MySQL – Enterprise Edition](https://www.mysql.com/products/enterprise/)
- [MySQL – Commercial License for OEMs, ISVs and VARs](https://www.mysql.com/about/legal/licensing/oem/)
- [Amazon RDS – MySQL feature support](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/MySQL.Concepts.FeatureSupport.html)
- [Google Cloud – Cloud SQL for MySQL features](https://docs.cloud.google.com/sql/docs/mysql/features)
- [Microsoft Learn – Azure Database for MySQL Flexible Server limitations](https://learn.microsoft.com/en-us/azure/mysql/flexible-server/concepts-limitations)
- [Oracle Cloud Infrastructure – MySQL HeatWave documentation](https://docs.oracle.com/en-us/iaas/mysql-database/home.htm)

