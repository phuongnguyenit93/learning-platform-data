# Data Guard Broker, observer và điều kiện tự động failover

Oracle Data Guard duy trì một hoặc nhiều standby database để bảo vệ dữ liệu và tăng khả năng sẵn sàng khi primary database gặp sự cố. Data Guard Broker cung cấp lớp quản trị tập trung để cấu hình, giám sát và điều phối các database trong cấu hình Data Guard. Khi kết hợp Broker với **Fast-Start Failover (FSFO)** và một tiến trình **observer**, Oracle có thể tự động chuyển một standby đủ điều kiện thành primary mà không cần DBA trực tiếp chạy lệnh failover.

Ba thành phần có vai trò khác nhau:

- **Data Guard Broker:** quản lý cấu hình, redo transport, Redo Apply, trạng thái database và các thao tác đổi role.
- **Observer:** tiến trình bên ngoài database, theo dõi khả năng kết nối và trạng thái của primary cùng target standby; master observer quyết định khi nào khởi động FSFO.
- **Fast-Start Failover:** cơ chế do Broker điều phối để tự động chuyển target standby sang primary khi các điều kiện được đáp ứng.

Tự động failover không đơn giản là mất ping đến primary thì standby lập tức lên primary. Broker cần xác định primary thực sự không còn khả dụng theo tiêu chí cấu hình, observer và standby phải thống nhất tình trạng, target standby phải đủ đồng bộ, và cấu hình phải bảo vệ database khỏi tình huống hai nơi cùng nhận vai trò primary.

Bài học này tập trung vào kiến trúc Broker/observer, điều kiện để FSFO được phép chạy, cách chọn threshold và lag limit, các trường hợp failover được kích hoạt, cách kiểm tra trạng thái và các giới hạn cần tính đến khi đưa tự động failover vào production.

## 1. Data Guard Broker là gì?

Data Guard Broker là lớp quản trị cho môi trường Oracle Data Guard. Broker lưu cấu hình và điều phối các thành viên như primary database, physical standby, logical standby và far sync instance.

Broker cung cấp hai cách quản trị chính:

- **DGMGRL:** giao diện dòng lệnh để tạo, sửa, kiểm tra và vận hành cấu hình.
- **Oracle Enterprise Manager Cloud Control:** giao diện quản trị trực quan cho các thao tác và giám sát được hỗ trợ.

Broker sử dụng tiến trình DMON trên các database member để quản lý cấu hình. Các database cần được cấu hình để Broker hoạt động, thường thông qua tham số:

~~~sql
ALTER SYSTEM SET DG_BROKER_START = TRUE SCOPE = BOTH;
~~~

Tham số này cần được cấu hình trên các database tham gia Broker theo yêu cầu của môi trường. Trước khi bật, cần kiểm tra các tham số và kết nối Data Guard hiện có để tránh làm gián đoạn cấu hình đang vận hành.

### 1.1 Broker quản lý những gì?

Broker có thể quản lý và giám sát:

- Danh sách database trong cấu hình và role hiện tại.
- Redo transport từ primary đến standby.
- Redo Apply trên physical standby.
- Protection mode của toàn cấu hình.
- Transport lag và apply lag.
- Các property của database và toàn cấu hình.
- Switchover, manual failover và Fast-Start Failover.
- Observer và trạng thái sẵn sàng tự động failover.
- Reinstatement của primary cũ sau FSFO khi đáp ứng điều kiện.

Broker giúp các thao tác role transition nhất quán hơn vì nó điều phối nhiều bước liên quan đến redo transport, apply service và các standby còn lại. Tuy nhiên, Broker không tự động giải quyết mọi thành phần của ứng dụng như DNS, load balancer, connection pool, cache hay message queue. Những thành phần đó cần được thiết kế để tiếp tục hoạt động sau khi database đổi role.

### 1.2 Cấu hình Broker và database member

Một cấu hình Broker có một tên cấu hình và một hoặc nhiều database member. Mỗi database có DB_UNIQUE_NAME riêng. DB_NAME có thể giống nhau giữa primary và physical standby, còn DB_UNIQUE_NAME phân biệt từng member.

Ví dụ topology:

~~~text
                  +----------------------+
                  |      Observer        |
                  |  DGMGRL process      |
                  +----------+-----------+
                             |
                   monitors both sites
                             |
           +-----------------+-----------------+
           |                                   |
+----------v-----------+            +----------v-----------+
| Primary database     |  redo      | Target standby       |
| DB_UNIQUE_NAME=PRD   +----------->+ DB_UNIQUE_NAME=STB   |
| ROLE=PRIMARY         | transport  | ROLE=PHYSICAL STANDBY|
+----------------------+            +----------------------+
           |                                   |
           +--------------- Broker ------------+
~~~

Trong môi trường thực tế, các member có thể nằm ở những data center, availability zone hoặc vùng địa lý khác nhau. Observer chạy trên một host riêng và kết nối đến các database thông qua Oracle Net.

### 1.3 DGMGRL cơ bản

Kết nối DGMGRL bằng tài khoản quản trị phù hợp, thường là SYS hoặc SYSDG theo chính sách bảo mật:

~~~text
dgmgrl
DGMGRL> CONNECT sysdg@PRD_DG;
DGMGRL> SHOW CONFIGURATION;
DGMGRL> SHOW DATABASE VERBOSE 'PRD';
DGMGRL> SHOW DATABASE VERBOSE 'STB';
~~~

Tên service trong ví dụ là alias Oracle Net đã cấu hình. Không nên đưa mật khẩu rõ vào script hoặc lịch sử shell. Có thể dùng Secure External Password Store hoặc cơ chế credential phù hợp để kết nối tự động.

Khi Broker đã quản lý các member, cần dùng DGMGRL để xem trạng thái và thay đổi Broker property. Không nên vừa chỉnh thủ công các tham số redo transport vừa để Broker quản lý cùng thuộc tính mà không hiểu cơ chế đồng bộ giữa Broker configuration và runtime parameter.

## 2. Switchover, manual failover và Fast-Start Failover

Ba thao tác đổi role có mục đích khác nhau.

| Thao tác | Loại sự kiện | Ai khởi tạo? | Đặc điểm |
|---|---|---|---|
| Switchover | Planned role transition | DBA hoặc quy trình bảo trì | Chuyển primary và standby cho nhau; bảo đảm không mất dữ liệu khi thực hiện đúng điều kiện |
| Manual failover | Unplanned role transition | DBA | DBA chọn standby và ra lệnh chuyển role sau khi primary gặp sự cố |
| Fast-Start Failover | Unplanned automatic role transition | Observer phối hợp với Broker | Tự động chuyển sang target standby khi điều kiện FSFO được thỏa mãn |

### 2.1 Switchover

Switchover dùng cho bảo trì có kế hoạch, ví dụ cần vá hệ điều hành hoặc nâng cấp máy chủ primary. Primary và standby còn giao tiếp được, Broker đồng bộ redo và điều phối quá trình đổi role.

Ví dụ:

~~~text
DGMGRL> SWITCHOVER TO 'STB';
~~~

Sau switchover:

- Standby được chọn trở thành primary.
- Primary cũ chuyển thành standby.
- Broker cấu hình lại redo transport và apply service theo role mới.
- Các standby khác tiếp tục hoặc được điều chỉnh để nhận redo từ primary mới.

Switchover không phải cơ chế xử lý sự cố khi primary đã mất kết nối hoàn toàn. Nó cần hai phía phối hợp.

### 2.2 Manual failover

Manual failover được DBA khởi tạo khi primary không còn hoạt động hoặc không thể khôi phục kịp. DBA chọn standby làm primary mới và dùng DGMGRL để thực hiện.

Ví dụ khái quát:

~~~text
DGMGRL> FAILOVER TO 'STB';
~~~

Khả năng mất dữ liệu phụ thuộc protection mode và lượng redo đã nhận/apply tại standby. Sau manual failover, primary cũ thường phải được xử lý, flashback hoặc dựng lại thành standby theo tình trạng thực tế.

### 2.3 Fast-Start Failover

FSFO tự động hóa quyết định failover trong một cấu hình Broker đã chuẩn bị trước. Observer giám sát primary và target standby. Khi primary mất khả năng kết nối theo tiêu chí và target standby đủ điều kiện, observer yêu cầu Broker thực hiện failover.

FSFO không tự chạy chỉ vì đã cài Data Guard Broker. Cần cấu hình target standby, protection mode, redo transport, threshold, observer, kết nối mạng và trạng thái Broker nhất quán.

## 3. Observer là gì?

Observer là tiến trình liên tục chạy từ DGMGRL client-side component. Nó không phải một database instance, không lưu datafile và không apply redo. Nhiệm vụ của nó là quan sát khả năng kết nối và trạng thái của primary cùng target standby, sau đó phối hợp với Broker khi cần FSFO.

Observer thường chạy trên một máy riêng với primary và standby. Vị trí này rất quan trọng: nếu observer nằm cùng failure domain với primary, một sự cố site có thể làm mất cả primary lẫn observer, khiến cơ chế tự động failover không còn đủ thành phần để quyết định.

### 3.1 Observer giám sát những gì?

Observer duy trì kết nối và trao đổi trạng thái với:

- Primary database.
- Target standby database.
- Broker configuration qua các database member.

Observer cần kết nối được tới cả primary và target standby. Nó phải xác nhận target standby đang ở trạng thái hợp lệ để nhận role primary.

Khi observer mất kết nối primary, nó không lập tức failover. Nó bắt đầu theo dõi thời gian mất kết nối theo FastStartFailoverThreshold, thử kết nối lại và kiểm tra trạng thái của target standby.

### 3.2 Master observer và backup observer

Trong các release hỗ trợ nhiều observer, một observer giữ vai trò **master observer**. Master observer là tiến trình điều phối FSFO. Các observer còn lại là backup observer, có thể tiếp quản vai trò master khi observer hiện tại gặp sự cố theo cơ chế Broker.

Số lượng observer tối đa thay đổi theo phiên bản Oracle. Tài liệu Oracle Database 19c mô tả tối đa ba observer cho một cấu hình; các release mới hơn có thể hỗ trợ số lượng khác. Hãy kiểm tra đúng tài liệu của release và Release Update đang triển khai.

Việc chạy nhiều observer không có nghĩa nhiều observer cùng ra lệnh failover độc lập. Broker xác định master observer để tránh các quyết định role transition mâu thuẫn.

### 3.3 Nên đặt observer ở đâu?

Một topology tốt nên phân tách ba thành phần:

- Primary ở site A.
- Target standby ở site B.
- Observer ở site C hoặc một failure domain độc lập.

Ví dụ:

~~~text
+-------------------+      +-------------------+
| Site A            |      | Site B            |
| Primary database  |----->| Standby database  |
+-------------------+ redo +-------------------+
          \                       /
           \                     /
            \                   /
             +-----------------+
             | Site C           |
             | Observer host    |
             +------------------+
~~~

Nếu chỉ có hai site, cần đánh giá observer đặt tại site nào và network path có độc lập đủ hay không. Không có vị trí observer nào loại bỏ hoàn toàn nguy cơ network partition. Mục tiêu là observer có khả năng phân biệt sự cố site với sự cố đường truyền riêng lẻ tốt nhất có thể.

### 3.4 Observer cần Oracle Net và credential

Trên máy observer cần có:

- Oracle Client hoặc Oracle Home có DGMGRL phù hợp.
- TNSNAMES.ORA hoặc naming method tương ứng.
- Connect identifier đến primary.
- Connect identifier đến target standby.
- Credential có quyền quản trị Broker.
- Network route, firewall và DNS hoạt động.
- Quyền ghi log/state file của observer.
- Cơ chế tự khởi động lại observer process nếu host reboot.

Nếu dùng RAC, connect identifier phải cho phép observer kết nối tới các instance cần thiết, không phụ thuộc một node duy nhất. Có thể cấu hình ObserverConnectIdentifier nếu muốn observer dùng connect string riêng với DGConnectIdentifier đang dùng cho redo transport.

## 4. Điều kiện nền tảng trước khi bật FSFO

Broker chỉ cho phép bật Fast-Start Failover khi các prerequisite quan trọng đã đáp ứng. Một cấu hình Data Guard đang chạy bình thường chưa chắc đã đủ điều kiện FSFO.

Các nhóm điều kiện chính:

1. Primary và target standby đã nằm trong cùng Broker configuration.
2. Broker được bật và configuration có trạng thái hợp lệ.
3. Protection mode và redo transport phù hợp.
4. Target standby nhận redo từ primary theo cấu hình được hỗ trợ.
5. Standby redo logs được cấu hình phù hợp.
6. Observer có thể kết nối tới primary và target standby.
7. Các connect identifier, listener và static service đã được kiểm tra.
8. Target standby có trạng thái đồng bộ hoặc lag nằm trong giới hạn.
9. FSFO đã được enable.
10. Observer đang chạy và được Broker nhận diện.

### 4.1 Broker configuration phải hoạt động

Kiểm tra:

~~~text
DGMGRL> SHOW CONFIGURATION;
DGMGRL> SHOW CONFIGURATION VERBOSE;
~~~

Nếu Broker configuration đang disabled, inconsistent hoặc có lỗi transport/apply, cần giải quyết trước khi bật FSFO.

Trên database member, kiểm tra:

~~~sql
SHOW PARAMETER dg_broker_start;
~~~

Nếu cần bật:

~~~sql
ALTER SYSTEM SET DG_BROKER_START = TRUE SCOPE = BOTH;
~~~

Cần xác nhận Broker quản lý được các member và các database có thể giao tiếp qua connect identifier.

### 4.2 Primary và target standby phải kết nối được

Khi enable FSFO, primary và target standby phải đang chạy, có kết nối và thỏa prerequisite. Observer cũng cần truy cập được cả hai.

Có thể kiểm tra Broker network configuration:

~~~text
DGMGRL> VALIDATE NETWORK CONFIGURATION FOR ALL;
~~~

Cú pháp hỗ trợ phụ thuộc release. Nếu lệnh validate không tồn tại ở release đang dùng, kiểm tra từng database bằng các lệnh VALIDATE phù hợp và thử kết nối thực tế từ host observer.

### 4.3 Target standby phải là database có thể nhận role

Far sync instance chỉ chuyển tiếp redo, không phải database và không thể trở thành primary. Target standby có thể nhận redo qua far sync theo cấu hình được hỗ trợ, nhưng chính standby database mới là đích failover.

Snapshot standby không phải target cho switchover hoặc FSFO trong cấu hình được tài liệu Oracle 19c mô tả. Cần chuyển đổi về physical standby và đáp ứng prerequisite trước khi chọn làm FSFO target.

Physical standby thường là lựa chọn phổ biến vì giữ đầy đủ bản sao vật lý và có thể tiếp tục bảo vệ primary mới sau role transition.

## 5. Protection mode và mức dữ liệu có thể mất

Protection mode quyết định mức bảo vệ dữ liệu khi primary mất và standby chưa nhận/apply hết redo.

| Protection mode | Redo transport điển hình | Mục tiêu | Hành vi FSFO |
|---|---|---|---|
| Maximum Protection | SYNC | Bảo đảm không mất dữ liệu; primary có thể dừng nếu không bảo vệ được redo | Target phải đồng bộ theo điều kiện của mode |
| Maximum Availability | SYNC hoặc FASTSYNC theo cấu hình | Ưu tiên zero data loss khi standby khả dụng, vẫn ưu tiên availability | Target phải ở trạng thái synchronized khi failover |
| Maximum Performance | ASYNC | Ưu tiên hiệu năng primary; có thể mất redo chưa truyền/apply | Target phải nằm trong FastStartFailoverLagLimit |

Các cấu hình cụ thể cần đối chiếu với phiên bản, loại standby, far sync và redo transport mode. Bảng này là mô hình khái quát, không thay thế cấu hình Oracle thực tế.

### 5.1 Maximum Protection

Maximum Protection ưu tiên bảo đảm không mất dữ liệu. Primary chỉ tiếp tục xử lý giao dịch khi redo cần thiết được bảo vệ theo mode. Nếu không còn standby đồng bộ đủ điều kiện, primary có thể bị shutdown để tránh tiếp tục chạy mà không đáp ứng mức bảo vệ đã chọn.

FSFO có thể được dùng trong môi trường protection mode phù hợp, nhưng target phải đáp ứng điều kiện đồng bộ. Với Maximum Protection, redo transport cần SYNC và không dùng far sync theo một số giới hạn của cấu hình Oracle.

### 5.2 Maximum Availability

Maximum Availability thường được chọn khi muốn ưu tiên zero data loss trong điều kiện standby đồng bộ nhưng vẫn duy trì khả năng hoạt động khi standby tạm thời không khả dụng theo hành vi của mode.

Để FSFO đạt zero data loss, cấu hình phải dùng redo transport phù hợp, thường SYNC hoặc FASTSYNC theo hướng dẫn Oracle, và target phải ở trạng thái SYNCHRONIZED tại thời điểm primary gặp sự cố.

Không chỉ nhìn tên protection mode rồi kết luận zero data loss. Hãy xác minh trạng thái đồng bộ thực tế và các property Broker.

### 5.3 Maximum Performance

Maximum Performance sử dụng ASYNC để giảm ảnh hưởng redo transport đến primary. Khi primary gặp sự cố, target standby có thể chưa nhận hoặc apply hết redo.

FastStartFailoverLagLimit xác định mức lag apply tối đa (tính theo giây) có thể chấp nhận để FSFO được phép. Nếu target vượt giới hạn, Broker không thực hiện tự động failover vì mức mất dữ liệu có thể vượt chính sách.

Ví dụ cấu hình:

~~~text
DGMGRL> EDIT DATABASE 'PRD' SET PROPERTY LogXptMode = ASYNC;
DGMGRL> EDIT DATABASE 'STB' SET PROPERTY LogXptMode = ASYNC;
DGMGRL> EDIT CONFIGURATION SET PROTECTION MODE AS MaxPerformance;
DGMGRL> EDIT CONFIGURATION SET PROPERTY FastStartFailoverLagLimit = 30;
~~~

Ví dụ 30 giây chỉ là giá trị minh họa. Hãy chọn lag limit theo RPO mà nghiệp vụ chấp nhận và khả năng duy trì apply của standby.

### 5.4 Zero data loss và lag limit

Trong cấu hình Maximum Availability với yêu cầu zero data loss, target phải được Broker xác nhận synchronized. Tài liệu Broker có thể hiển thị Lag Limit bằng 0 trong chế độ zero data loss.

Trong Maximum Performance, FastStartFailoverLagLimit là giới hạn data loss chấp nhận được. Giá trị mặc định trong tài liệu Oracle 19c là 30 giây và giá trị thấp nhất được mô tả cho mode này là 5 giây.

Không nên áp dụng một giá trị lag limit giống nhau cho mọi protection mode. Cần xem mode, redo transport, target state và release cụ thể.

## 6. Chọn target standby cho Fast-Start Failover

Target standby là database được Broker chuẩn bị trước để nhận role primary khi FSFO xảy ra.

Nếu cấu hình chỉ có một standby, có thể không cần khai báo rõ target property theo một số hướng dẫn Broker. Nếu có nhiều standby, cần chỉ định target hoặc danh sách candidate bằng FastStartFailoverTarget trên primary hiện tại.

Ví dụ:

~~~text
DGMGRL> EDIT DATABASE 'PRD' SET PROPERTY FastStartFailoverTarget = 'STB';
~~~

Nếu có nhiều target, Broker xét theo thứ tự được khai báo trong property. Ví dụ cú pháp danh sách và cách đặt dấu phân cách cần kiểm tra theo release đang dùng.

### 6.1 Tiêu chí chọn target

Cần đánh giá:

- Transport lag và apply lag.
- Protection mode và mức dữ liệu có thể mất.
- Network latency từ primary đến standby.
- Băng thông redo transport.
- CPU, memory, storage và I/O của standby.
- Dung lượng để chạy workload production sau failover.
- Khả năng truy cập từ ứng dụng và client.
- Cấu hình service, listener, wallet và kết nối phụ thuộc.
- Khả năng tiếp tục bảo vệ bằng các standby còn lại sau role transition.

Trong cùng loại standby, target có transport lag thấp hơn thường giúp giảm data loss. Với FSFO, ngoài lag còn phải đáp ứng synchronized/within-lag state.

### 6.2 Target không chỉ cần đủ dữ liệu

Một standby có thể nhận đủ redo nhưng cấu hình phần cứng quá nhỏ để gánh tải production. Sau failover, database có thể mở primary nhưng ứng dụng vẫn chậm hoặc không đáp ứng SLA.

Hãy đánh giá năng lực của standby theo tải thực tế: CPU, memory, storage throughput, connection capacity, licensing, backup, monitoring và nhân sự vận hành.

## 7. FastStartFailoverThreshold

FastStartFailoverThreshold là thời gian (giây) master observer chờ và thử kết nối lại primary trước khi khởi động FSFO do primary mất kết nối.

Trong Oracle Database 19c:

- Giá trị mặc định là 30 giây.
- Giá trị nhỏ nhất là 6 giây.
- Giá trị cao hơn làm giảm khả năng failover nhầm do network glitch ngắn.
- Với primary RAC, cần tính thời gian phát hiện lỗi instance và tái cấu hình Clusterware trước khi chọn threshold.

Ví dụ:

~~~text
DGMGRL> EDIT CONFIGURATION SET PROPERTY FastStartFailoverThreshold = 45;
~~~

45 giây là ví dụ, không phải khuyến nghị chung.

### 7.1 Threshold quá thấp

Nếu threshold quá thấp:

- Một đợt network jitter có thể bị xem là primary failure.
- Observer có thể không đủ thời gian phân biệt lỗi tạm thời với sự cố thật.
- Một node RAC đang được Clusterware phục hồi có thể chưa kịp trở lại.
- Failover ngoài ý muốn có thể làm gián đoạn ứng dụng và gây chi phí role transition.

### 7.2 Threshold quá cao

Nếu threshold quá cao:

- Ứng dụng phải chờ lâu hơn trước khi database chuyển role.
- RTO tăng.
- Một primary thực sự đã hỏng có thể làm dịch vụ ngừng lâu hơn cần thiết.

Threshold phải được chọn từ dữ liệu quan sát mạng và thời gian recovery, không phải chỉ chọn số nhỏ để đạt failover nhanh.

### 7.3 Dùng observer histogram

Oracle cung cấp V$FS_OBSERVER_HISTOGRAM trong các release hỗ trợ để xem thống kê về các lần ping thành công giữa observer và primary theo khoảng thời gian.

Thông tin này giúp ước lượng ngưỡng phù hợp với network latency và jitter thực tế. Hãy kết hợp histogram với log observer, broker log và dữ liệu giám sát mạng.

## 8. FastStartFailoverLagLimit

FastStartFailoverLagLimit xác định mức apply lag mà standby được phép có khi FSFO xảy ra trong Maximum Performance mode.

Ví dụ:

~~~text
DGMGRL> EDIT CONFIGURATION SET PROPERTY FastStartFailoverLagLimit = 20;
~~~

Nếu target standby apply point chậm hơn redo generation point của primary vượt mức này, FSFO không được phép thực hiện.

Lag limit phản ánh mức data loss mà tổ chức chấp nhận, không phải chỉ số thời gian failover. Một lag limit thấp hơn giảm lượng dữ liệu có thể mất nhưng có thể khiến standby không đủ điều kiện failover khi hệ thống đang tải cao hoặc network chậm.

### 8.1 Transport lag và apply lag

Cần phân biệt:

- **Transport lag:** redo được tạo ở primary nhưng chưa được chuyển đến standby.
- **Apply lag:** redo đã nhận nhưng chưa được apply vào datafile standby.

Một standby có transport lag thấp nhưng apply lag cao vẫn có thể không đủ điều kiện. FSFO kiểm tra trạng thái apply/lag theo cơ chế Broker, không chỉ dựa trên một con số transport lag.

### 8.2 Không dùng lag limit để che lỗi apply

Nếu standby thường xuyên vượt lag limit, cần tìm nguyên nhân:

- Băng thông network không đủ.
- Redo generation rate tăng cao.
- Standby thiếu CPU hoặc I/O.
- Recovery parallelism chưa phù hợp.
- Có delay apply được cấu hình.
- Standby bị contention hoặc thiếu dung lượng.
- Redo transport gặp lỗi hoặc bị gián đoạn.

Tăng lag limit chỉ để Broker luôn cho phép failover có thể làm tăng data loss vượt chính sách nghiệp vụ.

## 9. Điều kiện kết nối và nhận diện primary failure

Trong trường hợp mất kết nối thông thường, FSFO dựa trên tín hiệu từ cả observer và target standby.

Mô hình mặc định:

1. Primary mất kết nối với observer.
2. Primary cũng mất kết nối với target standby.
3. Observer bắt đầu thời gian threshold và thử kết nối lại primary.
4. Target standby kiểm tra trạng thái và mức đồng bộ.
5. Nếu hết threshold mà primary vẫn không thể kết nối, target standby vẫn hợp lệ và Broker configuration nhất quán, observer khởi động failover.

Điều này giúp tránh việc observer đơn độc kết luận primary đã hỏng trong khi standby vẫn đang giao tiếp bình thường với primary.

### 9.1 Vì sao cần cả observer và standby xác nhận?

Giả sử đường mạng từ observer đến primary bị đứt nhưng primary vẫn giao tiếp bình thường với standby. Nếu observer tự quyết định failover, có thể xuất hiện hai database cùng tin rằng mình là primary.

Việc standby cũng tham gia xác nhận tình trạng giúp giảm nguy cơ split brain. Broker kiểm tra target standby còn liên lạc với primary hay không và chỉ thực hiện failover khi các điều kiện phù hợp.

### 9.2 ObserverOverride

ObserverOverride là property cho phép observer thực hiện failover khi observer mất kết nối primary, ngay cả khi standby vẫn còn kết nối khỏe với primary.

Giá trị mặc định trong tài liệu Oracle 19c là FALSE.

~~~text
DGMGRL> EDIT CONFIGURATION SET PROPERTY ObserverOverride = TRUE;
~~~

Bật ObserverOverride có thể giúp xử lý một số tình huống network partition cụ thể, nhưng làm thay đổi điều kiện bảo vệ chống split brain. Nếu standby vẫn thấy primary hoạt động, failover có thể tạo ra tình huống primary cũ và primary mới cùng có khả năng phục vụ client.

Không bật ObserverOverride chỉ để rút ngắn thời gian failover. Chỉ cân nhắc khi kiến trúc mạng, fencing, primary shutdown và kịch bản phân vùng mạng đã được thiết kế, thử nghiệm và phê duyệt.

## 10. Primary shutdown để hạn chế split brain

FastStartFailoverPmyShutdown kiểm soát việc primary tự shutdown trong một số tình huống FSFO.

Trong Oracle Database 19c, giá trị mặc định là TRUE. Khi FSFO đang bật và trạng thái FS_FAILOVER_STATUS của primary cho biết STALLED quá FastStartFailoverThreshold, primary có thể shutdown để ngăn một primary bị cô lập tiếp tục phục vụ truy vấn.

Ví dụ xem property:

~~~text
DGMGRL> SHOW CONFIGURATION VERBOSE;
DGMGRL> SHOW FAST_START FAILOVER;
~~~

Property này đặc biệt quan trọng khi primary bị cô lập khỏi observer và target standby. Nếu failover đã xảy ra ở standby, primary cũ không nên tiếp tục nhận ghi từ ứng dụng.

Việc primary shutdown không thay thế thiết kế network fencing và service routing. Ứng dụng cần tránh gửi ghi vào site cũ sau role transition.

## 11. Các điều kiện sức khỏe có thể kích hoạt FSFO

Ngoài điều kiện mất kết nối theo threshold, Broker cho phép cấu hình một số health condition để FSFO xảy ra ngay khi phát hiện tình trạng nghiêm trọng.

Trong tài liệu Oracle 19c, các điều kiện gồm:

| Health condition | Ý nghĩa | Mặc định theo tài liệu 19c |
|---|---|---|
| Datafile Write Errors | Lỗi ghi vào datafile, bao gồm một số file hệ thống, undo và temp | YES |
| Corrupted Dictionary | Dictionary corruption nghiêm trọng | YES |
| Corrupted Controlfile | Control file bị hỏng vĩnh viễn do lỗi thiết bị | YES |
| Inaccessible Logfile | LGWR không thể ghi vào bất kỳ member nào của log group do I/O error | NO |
| Stuck Archiver | Archiver không thể archive redo vì thiết bị đầy hoặc không khả dụng | NO |

Các giá trị mặc định và tập điều kiện có thể thay đổi theo release. Hãy dùng DGMGRL để xem cấu hình thực tế.

### 11.1 Bật một điều kiện bổ sung

Ví dụ cú pháp:

~~~text
DGMGRL> ENABLE FAST_START FAILOVER CONDITION 'Inaccessible Logfile';
~~~

Tắt:

~~~text
DGMGRL> DISABLE FAST_START FAILOVER CONDITION 'Inaccessible Logfile';
~~~

Cần xác nhận đúng tên condition theo release. Những điều kiện này có thể kích hoạt failover mà không chờ FastStartFailoverThreshold.

### 11.2 Vì sao không nên bật tất cả condition?

Một số lỗi có thể chỉ xảy ra ở một instance trong Oracle RAC. Nếu failover do lỗi một instance khi Clusterware có thể phục hồi instance đó, việc chuyển toàn bộ database sang site khác có thể làm giảm availability.

Đặc biệt, Oracle khuyến cáo cân nhắc kỹ Inaccessible Logfile và Stuck Archiver trong RAC vì chúng có thể áp dụng ở cấp một instance và làm mất lợi ích phục hồi do Oracle Clusterware cung cấp.

Hãy chỉ bật health condition khi tổ chức đã xác định rõ lỗi đó không thể xử lý cục bộ và cần chuyển role.

## 12. Normal shutdown không kích hoạt FSFO

Một điểm quan trọng trong vận hành là FSFO không tự động failover khi primary hoặc standby được shutdown bình thường.

Các dạng shutdown bình thường gồm:

- SHUTDOWN NORMAL.
- SHUTDOWN IMMEDIATE.
- SHUTDOWN TRANSACTIONAL.

Trong các trường hợp này, Broker không xem đây là primary crash cần tự động failover. FSFO sẽ không kích hoạt cho đến khi primary và standby kết nối, trao đổi trạng thái trở lại theo yêu cầu.

Ngược lại, SHUTDOWN ABORT hoặc việc tất cả instance primary bị lỗi có thể kích hoạt FSFO nếu các điều kiện còn lại được đáp ứng.

Điều này rất quan trọng khi lập lịch bảo trì. Nếu DBA chủ động shutdown primary, hãy dùng switchover có kế hoạch khi cần chuyển role, không trông chờ FSFO tự làm việc đó.

## 13. Điều kiện sẵn sàng của target standby

Observer không chỉ cần phát hiện primary mất kết nối. Target standby còn phải sẵn sàng trở thành primary.

Một số điều kiện khiến FSFO không thể xảy ra:

- FSFO đã bị disable.
- Master observer không chạy.
- Observer không kết nối được target standby.
- Observer và target standby có trạng thái Broker configuration không nhất quán.
- Target standby không còn kết nối với observer.
- Target standby không đồng bộ trong Maximum Availability hoặc Maximum Protection.
- Target standby vượt FastStartFailoverLagLimit trong Maximum Performance.
- Target standby vẫn có kết nối primary, trong khi ObserverOverride là FALSE.
- Target standby có FS_FAILOVER_STATUS chỉ ra lý do không thể failover.
- Một manual failover đang diễn ra.
- Primary đã được shutdown bình thường thay vì ABORT.

### 13.1 Kiểm tra trạng thái target

Trên target standby:

~~~sql
SELECT database_role,
       open_mode,
       switchover_status,
       fs_failover_status,
       fs_failover_observer_present
FROM v$database;
~~~

Các cột này giúp xác nhận role, trạng thái mở và trạng thái liên quan FSFO. Tên/cột và trạng thái có thể khác theo release.

Trong Maximum Availability, trạng thái sẵn sàng có thể được thể hiện là SYNCHRONIZED. Trong Maximum Performance, trạng thái có thể là TARGET UNDER LAG LIMIT khi target nằm trong giới hạn.

### 13.2 Kiểm tra qua DGMGRL

~~~text
DGMGRL> SHOW FAST_START FAILOVER;
DGMGRL> SHOW DATABASE VERBOSE 'STB';
DGMGRL> SHOW CONFIGURATION VERBOSE;
~~~

Đầu ra SHOW FAST_START FAILOVER có thể cho biết:

- FSFO đang enabled hay disabled.
- Protection mode.
- Lag limit.
- Threshold.
- Active target và potential targets.
- Observer hiện tại.
- Shutdown Primary.
- Auto-reinstate.
- Observer reconnect và override.
- Các health condition đang bật.

Không nên chỉ kiểm tra dòng Enabled. Cần xem target có trạng thái valid, observer có được nhận diện và database có đủ điều kiện failover hay không.

## 14. Bật Fast-Start Failover theo quy trình

Phần này trình bày khung cấu hình cho một primary và một physical standby đã được thiết lập Data Guard Broker. Tên database, service và giá trị phải được thay bằng thông tin thật của môi trường.

### Bước 1: Xác nhận cấu hình Broker

~~~text
DGMGRL> SHOW CONFIGURATION;
DGMGRL> SHOW DATABASE VERBOSE 'PRD';
DGMGRL> SHOW DATABASE VERBOSE 'STB';
~~~

Xác nhận primary và standby đều enabled, transport/apply không có lỗi chưa xử lý.

### Bước 2: Xác nhận redo transport và standby redo logs

Kiểm tra LogXptMode phù hợp với protection mode. Primary và target standby cần standby redo logs được cấu hình đúng kích thước, số lượng và thread cho role tương ứng.

Trong môi trường RAC, cần kiểm tra từng thread. Một cấu hình SRL chỉ đủ cho một instance có thể không đáp ứng khi role transition hoặc nhiều thread cùng hoạt động.

### Bước 3: Chọn target standby

Nếu có nhiều standby, đặt FastStartFailoverTarget trên primary:

~~~text
DGMGRL> EDIT DATABASE 'PRD' SET PROPERTY FastStartFailoverTarget = 'STB';
~~~

Chỉ thay đổi target theo quy trình Broker; trong nhiều release cần disable FSFO, sửa target rồi enable lại.

### Bước 4: Chọn protection mode

Ví dụ Maximum Availability:

~~~text
DGMGRL> EDIT DATABASE 'PRD' SET PROPERTY LogXptMode = SYNC;
DGMGRL> EDIT DATABASE 'STB' SET PROPERTY LogXptMode = SYNC;
DGMGRL> EDIT CONFIGURATION SET PROTECTION MODE AS MaxAvailability;
~~~

Nếu dùng FASTSYNC hoặc far sync, phải xác nhận kiến trúc và release hỗ trợ đúng cấu hình đó. Với Maximum Performance, đặt ASYNC và chọn lag limit theo RPO.

### Bước 5: Đặt threshold

~~~text
DGMGRL> EDIT CONFIGURATION SET PROPERTY FastStartFailoverThreshold = 30;
~~~

30 giây là giá trị mặc định trong tài liệu Oracle 19c. Trong production, hãy dựa vào network latency, RAC failover time và observer histogram.

### Bước 6: Xem các property liên quan

~~~text
DGMGRL> SHOW CONFIGURATION VERBOSE;
DGMGRL> SHOW FAST_START FAILOVER;
~~~

Xác nhận các property như FastStartFailoverPmyShutdown, FastStartFailoverAutoReinstate, FastStartFailoverLagLimit, ObserverOverride và ObserverReconnect.

### Bước 7: Kiểm tra kết nối từ observer host

Trên host observer, xác nhận Oracle Net có thể kết nối đến primary và target standby bằng đúng connect identifier. Không chỉ kiểm tra từ laptop DBA hoặc host primary.

Nếu không dùng Oracle Clusterware hoặc Oracle Restart, cấu hình static service phù hợp để Broker có thể khởi động lại database trong quá trình reinstatement. Dùng lệnh VALIDATE STATIC CONNECT IDENTIFIER theo release để kiểm tra.

### Bước 8: Enable FSFO

~~~text
DGMGRL> ENABLE FAST_START FAILOVER;
~~~

Lệnh này cho phép Broker thực hiện automatic failover nếu điều kiện xảy ra. Nó không tự gây failover ngay tại thời điểm bật.

### Bước 9: Khởi động observer

Trên host observer, kết nối DGMGRL đến cấu hình và chạy:

~~~text
DGMGRL> START OBSERVER IN BACKGROUND;
~~~

Có thể chạy foreground bằng START OBSERVER, nhưng command prompt sẽ không trả lại cho đến khi observer được dừng từ DGMGRL session khác. Chạy background thường thuận tiện hơn cho vận hành.

### Bước 10: Xác nhận trạng thái cuối

~~~text
DGMGRL> SHOW FAST_START FAILOVER;
DGMGRL> SHOW CONFIGURATION VERBOSE;
DGMGRL> SHOW DATABASE VERBOSE 'STB';
~~~

Xác nhận observer xuất hiện, target valid, FSFO enabled, protection mode và lag state đúng với RPO.

## 15. Observe-only mode: diễn tập trước khi cho phép failover thật

Observe-only mode cho phép quan sát những điều kiện mà FSFO sẽ xử lý mà không thực hiện role transition thật.

Bật:

~~~text
DGMGRL> ENABLE FAST_START FAILOVER OBSERVE ONLY;
~~~

Trong chế độ này, Broker/observer ghi log cho biết nếu failover thật thì điều kiện có được thỏa mãn hay không và hành động nào sẽ được thực hiện. Không có role change tự động.

Observe-only mode hữu ích để:

- Đo thời gian phát hiện primary unavailable.
- Kiểm tra network giữa observer và các database.
- Xác minh target standby có trạng thái synchronized/within-lag.
- Kiểm tra observer log và broker log.
- Xác định false positive do network jitter.
- Đánh giá threshold trước khi bật automatic role transition.

Lưu ý: Observe-only không có cùng enforcement như FSFO thực. Một số precondition có thể được bỏ qua trong mode quan sát, vì vậy không dùng một kết quả observe-only đơn lẻ để kết luận failover thật chắc chắn sẽ thành công.

## 16. Observer hoạt động ra sao khi primary gặp sự cố?

Luồng xử lý điển hình:

~~~text
Primary đang hoạt động
        |
        v
Observer và standby theo dõi primary
        |
        v
Primary mất kết nối
        |
        v
Observer bắt đầu FastStartFailoverThreshold
        |
        +---- Primary kết nối lại trước hạn? ---- Có ----> Dừng failover attempt
        |
       Không
        |
        v
Observer kiểm tra target standby
        |
        +---- Target không đủ điều kiện? ---- Có ----> Chưa failover; tiếp tục theo dõi
        |
       Không
        |
        v
Broker chuyển target standby thành primary
        |
        v
Primary cũ được shutdown/fencing theo cấu hình
        |
        v
Ứng dụng kết nối tới service ở primary mới
        |
        v
Primary cũ được reinstate thành standby khi đủ điều kiện
~~~

Đây là mô hình logic. Thời gian thực tế còn phụ thuộc threshold, thời gian phát hiện, apply backlog, recovery, mở database, service startup và thời gian ứng dụng kết nối lại.

### 16.1 Primary mất kết nối với cả observer và standby

Đây là trường hợp mặc định điển hình. Observer và target standby cùng xác nhận không còn giao tiếp được với primary. Sau threshold, nếu target đủ điều kiện, FSFO được thực hiện.

### 16.2 Chỉ observer mất kết nối primary

Nếu target standby vẫn giao tiếp với primary, mặc định Broker không cho failover để tránh split brain. ObserverOverride có thể thay đổi hành vi này, nhưng cần đánh giá rủi ro kỹ.

### 16.3 Observer bị dừng

Nếu không có master observer đang hoạt động, FSFO không thể được điều phối bình thường. Backup observer có thể tiếp quản nếu đã được cấu hình và chạy theo cơ chế của release.

Observer là một thành phần của availability architecture. Cần giám sát process, host, log, network và restart policy của nó như một dịch vụ production.

### 16.4 Primary RAC mất một instance

Với primary RAC, FSFO không nên failover chỉ vì một instance bị lỗi nếu các instance khác vẫn hoạt động. Observer kiểm tra các instance còn lại; failover chỉ được xét khi tất cả instance primary được xem là đã thất bại hoặc không thể kết nối theo logic Broker.

Đây là lý do threshold cần đủ lớn để tính thời gian Clusterware phát hiện và phục hồi instance, tránh chuyển role chỉ vì một node tạm thời bị lỗi.

## 17. FastStartFailoverAutoReinstate

Sau khi FSFO thành công, primary cũ có thể được đưa trở lại cấu hình như một standby mới. Property FastStartFailoverAutoReinstate điều khiển việc tự động reinstatement trong một số tình huống.

Trong Oracle Database 19c, giá trị mặc định là TRUE.

Tuy nhiên, auto-reinstate không phải lúc nào cũng xảy ra. Các điều kiện thường cần:

- Flashback Database được bật trên database cần reinstatement và target/new primary theo yêu cầu Oracle.
- Flashback logs còn đủ để đưa primary cũ về SCN phù hợp.
- Observer kết nối lại được primary cũ.
- Primary cũ và new primary có thể giao tiếp.
- Broker configuration còn FSFO enabled và các điều kiện khác phù hợp.
- Failover không xuất phát từ user-configurable condition hoặc ứng dụng gọi DBMS_DG.INITIATE_FS_FAILOVER trong những trường hợp Oracle không tự reinstatement.

### 17.1 Kiểm tra Flashback Database

Trên các database liên quan:

~~~sql
SELECT name, flashback_on
FROM v$database;
~~~

Nếu yêu cầu auto-reinstate, cần thiết kế FRA và retention để giữ flashback logs đủ lâu. Chỉ bật FLASHBACK_ON không bảo đảm có đủ log khi sự cố xảy ra sau một thời gian dài.

### 17.2 Reinstatement thủ công

Nếu auto-reinstate không thực hiện được, DBA có thể cần sửa nguyên nhân và dùng Broker để reinstate:

~~~text
DGMGRL> REINSTATE DATABASE 'PRD';
~~~

Lệnh này chỉ chạy khi database đáp ứng điều kiện reinstatement. Nếu flashback logs không đủ hoặc primary cũ không thể flashback về điểm cần thiết, có thể phải dựng lại standby từ primary mới bằng quy trình phù hợp.

## 18. Ứng dụng kết nối sau failover

Data Guard Broker chuyển role database, nhưng ứng dụng phải biết cách tìm primary mới.

Cần chuẩn bị:

- Service chỉ chạy trên database có role PRIMARY.
- Listener và service registration đúng ở cả hai site.
- TNS connect descriptor có thể kết nối tới site mới.
- DNS hoặc load balancer cập nhật theo thiết kế.
- Connection pool có khả năng loại bỏ connection cũ và tạo connection mới.
- FAN, TAF hoặc Application Continuity nếu ứng dụng và Oracle stack hỗ trợ.
- Job, scheduler, integration endpoint và database link được kiểm tra sau role change.

### 18.1 Role-based services

Một service có thể được cấu hình để chỉ chạy khi database ở role PRIMARY thông qua Oracle Clusterware hoặc Oracle Restart. Khi role transition xảy ra, service được khởi động ở primary mới theo cấu hình.

Không nên để service ghi dữ liệu chạy đồng thời trên cả primary cũ và standby mới. Cần kiểm tra cấu hình role, preferred/available instances và service management trước khi triển khai FSFO.

### 18.2 Client retry và transaction outcome

Nếu connection bị đứt trong lúc commit, ứng dụng có thể không biết transaction đã commit hay chưa. Đây là vấn đề transaction outcome, không chỉ là kết nối lại.

Ứng dụng nên thiết kế idempotency key, retry logic có kiểm soát và quy trình đối soát cho các thao tác ghi quan trọng. Application Continuity có thể hỗ trợ một số trường hợp replay, nhưng cần kiểm tra driver, service và loại transaction được hỗ trợ.

## 19. Giám sát trạng thái FSFO

Không nên đợi đến lúc failover mới kiểm tra observer. Cần giám sát liên tục trạng thái Broker và target standby.

### 19.1 DGMGRL

Các lệnh thường dùng:

~~~text
DGMGRL> SHOW CONFIGURATION VERBOSE;
DGMGRL> SHOW FAST_START FAILOVER;
DGMGRL> SHOW DATABASE VERBOSE 'PRD';
DGMGRL> SHOW DATABASE VERBOSE 'STB';
DGMGRL> VALIDATE DATABASE VERBOSE 'STB';
DGMGRL> VALIDATE NETWORK CONFIGURATION FOR ALL;
~~~

Lệnh VALIDATE có thể hiển thị cảnh báo hoặc điều kiện cần sửa trước khi role transition. Cú pháp chi tiết phụ thuộc release.

### 19.2 V$DATABASE

~~~sql
SELECT name,
       database_role,
       open_mode,
       fs_failover_status,
       fs_failover_observer_present,
       fs_failover_current_target,
       fs_failover_threshold
FROM v$database;
~~~

Các cột liên quan FSFO cho biết trạng thái failover, observer hiện diện, target và threshold. Hãy xác minh cột được hỗ trợ trong phiên bản đang dùng bằng tài liệu Oracle Database Reference.

### 19.3 Fast-Start Failover statistics

V$FS_FAILOVER_STATS cung cấp thống kê về các lần FSFO. Ví dụ:

~~~sql
SELECT last_failover_time,
       last_failover_reason
FROM v$fs_failover_stats;
~~~

V$FS_OBSERVER_HISTOGRAM có thể hỗ trợ chọn threshold bằng thống kê ping. Ngoài database views, cần thu thập observer log, broker log và alert log từ các site.

### 19.4 Các chỉ số nên cảnh báo

- Observer process không chạy hoặc không được Broker nhận diện.
- FSFO bị disable.
- Target standby không valid.
- FS_FAILOVER_STATUS không ở trạng thái sẵn sàng.
- Apply lag vượt ngưỡng.
- Redo transport lỗi.
- Broker configuration inconsistent.
- FRA hoặc flashback log space sắp cạn.
- Observer mất kết nối một trong hai database.
- Primary bị STALLED.
- Service primary-role không chạy sau role transition.

Cảnh báo phải được gửi qua một kênh độc lập với primary site. Nếu hệ thống cảnh báo chỉ nằm trên primary, chính sự cố primary có thể làm mất khả năng thông báo.

## 20. Troubleshooting thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| FSFO enable thất bại | Chưa đủ prerequisite, target hoặc protection mode không hợp lệ | Đọc DGMGRL error, validate primary/standby, redo transport và Broker state |
| ORA-16819 hoặc cảnh báo observer | FSFO enabled nhưng observer chưa chạy/không được nhận diện | Kiểm tra observer host, DGMGRL, TNS và log |
| Target không valid | Apply lag, transport error, Broker inconsistent hoặc target không hỗ trợ | SHOW DATABASE VERBOSE, kiểm tra FS_FAILOVER_STATUS và redo apply |
| Observer không kết nối standby | TNS alias, listener, firewall, DNS hoặc credential | Test kết nối ngay từ host observer |
| Primary bị STALLED | Không nhận xác nhận từ observer/standby theo protection policy | Kiểm tra network, observer và standby; đọc alert/broker log |
| Failover không xảy ra sau primary crash | Observer không chạy, target không synchronized/within lag, hoặc FSFO disabled | Kiểm tra toàn bộ điều kiện, không chỉ threshold |
| Failover xảy ra quá sớm | Threshold thấp, network jitter hoặc health condition bật | Xem observer log, histogram, configurable conditions |
| Primary cũ không tự reinstate | Flashback không bật/không đủ log, network hoặc điều kiện reinstatement không đạt | Kiểm tra FRA, flashback logs, broker status và dùng REINSTATE khi phù hợp |
| Ứng dụng không kết nối primary mới | Service/listener/client connect descriptor chưa chuyển role | Kiểm tra role-based service, DNS, pool và retry |
| Standby thường xuyên vượt lag limit | Network, apply throughput hoặc tải standby | Điều tra transport/apply bottleneck; không tăng limit tùy tiện |

### 20.1 Observer không được nhận diện

Kiểm tra:

- Process observer còn chạy không?
- Observer đang kết nối đúng Broker configuration không?
- Host observer có TNS alias và credential hợp lệ không?
- Primary và target standby có nhận observer không?
- Observer state/log file có bị xóa hoặc không thể ghi không?
- Có nhiều observer và master election đang diễn ra không?

Khởi động lại observer cần thực hiện theo hướng dẫn release và quy trình vận hành, tránh chạy nhiều observer không kiểm soát hoặc xóa state file đang cần cho việc khôi phục.

### 20.2 FSFO bị disable nhưng observer vẫn chạy

Disable FSFO không nhất thiết dừng observer process. Observer có thể vẫn tồn tại nhưng không được phép khởi động automatic failover.

Kiểm tra trạng thái bằng:

~~~text
DGMGRL> SHOW FAST_START FAILOVER;
~~~

Nếu cần dừng observer, dùng STOP OBSERVER từ một DGMGRL session phù hợp. Không nhầm thao tác disable FSFO với stop observer.

### 20.3 Cẩn trọng với DISABLE FAST_START FAILOVER FORCE

Khi network bị phân vùng, lệnh FORCE có thể không truyền được trạng thái disable tới mọi database member. Nếu chỉ disable ở primary trong khi target standby vẫn còn FSFO enabled, observer vẫn có thể failover và tạo ra nguy cơ hai database cùng nhận role primary.

Oracle cảnh báo cần xử lý target standby cẩn thận trong các tình huống mất kết nối. Không chạy FORCE như một lệnh chữa lỗi chung. Trước khi dùng, xác định observer, primary và target standby đang ở đâu, database nào đã chuyển role và cách ngăn split brain.

## 21. Thiết kế observer và network chống false failover

Observer cần một đường mạng đủ ổn định để kiểm tra primary và target. Một cấu hình tốt cần xem xét:

- Network giữa observer và primary.
- Network giữa observer và standby.
- Network redo transport giữa primary và standby.
- DNS và Oracle Net name resolution.
- Firewall idle timeout và session timeout.
- Network routing khi một site bị cô lập.
- Latency/jitter theo giờ cao điểm.
- Observer host reboot, patching và process supervision.
- Credential expiration và wallet availability.

### 21.1 Độc lập failure domain

Nếu observer và primary cùng phụ thuộc một router, power domain hoặc data center, một sự cố chung có thể làm observer mất khả năng quan sát chính xác.

Observer nên có đường truy cập độc lập nhất có thể. Với ba site, đặt primary, standby và observer ở ba failure domain khác nhau thường là topology dễ suy luận hơn.

### 21.2 Threshold theo dữ liệu thực tế

Không chọn threshold chỉ vì một bài hướng dẫn dùng 30 giây. Đo thời gian ping, network failover, RAC reconfiguration và observer reconnect trong các điều kiện tải thật.

Threshold nên đủ lớn để tránh failover nhầm, nhưng đủ nhỏ để đáp ứng RTO. Cần thử cả trường hợp mất node, mất network, listener down và site outage.

### 21.3 Backup observer

Nếu release hỗ trợ nhiều observer, có thể triển khai backup observer trên host khác. Cần kiểm tra observer registration, master/backup status, network và chính sách credential.

Backup observer không thay thế monitoring. Nếu mọi observer cùng bị ảnh hưởng bởi một lỗi cấu hình hoặc một credential hết hạn, FSFO vẫn có thể mất khả năng tự động.

## 22. Kiểm thử failover có kiểm soát

Không nên kiểm thử FSFO lần đầu trong một sự cố production. Hãy dựng môi trường thử có cùng protection mode, redo transport, observer topology và network behavior gần với production.

Một kế hoạch kiểm thử có thể gồm:

1. Kiểm tra Broker configuration và target standby.
2. Xác nhận observer đang chạy và được nhận diện.
3. Bật observe-only mode để quan sát điều kiện.
4. Tạo một lần network interruption có kiểm soát trong môi trường thử.
5. Đo thời gian observer phát hiện lỗi.
6. Xác nhận target standby có synchronized/within-lag state.
7. Đọc observer log và broker log.
8. Sau khi hiểu hành vi, bật FSFO thực trong môi trường thử.
9. Thực hiện một failure injection được phê duyệt.
10. Xác nhận role transition, service startup và client reconnection.
11. Xác nhận primary cũ được reinstate hoặc dựng lại thành standby.
12. Backup và kiểm tra lại cấu hình sau failover.

Không cố tình gây SHUTDOWN ABORT hoặc cắt network ở production chỉ để kiểm tra nếu chưa có kế hoạch và cửa sổ bảo trì được phê duyệt.

### 22.1 Kịch bản cần kiểm tra

- Primary instance đơn lẻ crash.
- Một instance trong primary RAC crash nhưng các instance còn lại vẫn hoạt động.
- Toàn bộ primary RAC mất.
- Observer mất kết nối nhưng standby vẫn kết nối primary.
- Standby mất kết nối observer.
- Primary và standby mất kết nối redo transport.
- Apply lag vượt FastStartFailoverLagLimit.
- Observer host reboot.
- Network partition giữa ba site.
- Primary shutdown bình thường.
- Primary shutdown abort.
- Một health condition được cấu hình xảy ra.

Kết quả cần ghi nhận là failover có xảy ra hay không, thời điểm xảy ra, lý do, dữ liệu có thể mất, ứng dụng reconnect và primary cũ được xử lý thế nào.

## 23. RPO, RTO và kỳ vọng tự động failover

FSFO cải thiện RTO bằng cách tự động hóa quyết định failover. Nó không bảo đảm dịch vụ phục hồi tức thì.

RTO thực tế gồm nhiều khoảng thời gian:

- Thời gian phát hiện lỗi.
- FastStartFailoverThreshold.
- Thời gian Broker chuyển role.
- Thời gian database recovery/open.
- Thời gian service được khởi động.
- Thời gian client phát hiện connection lỗi và reconnect.
- Thời gian ứng dụng kiểm tra transaction outcome.

RPO phụ thuộc protection mode và trạng thái redo tại thời điểm sự cố:

- Maximum Availability/Maximum Protection với target synchronized có thể đạt zero data loss theo điều kiện cấu hình.
- Maximum Performance cho phép mức data loss đến giới hạn được cấu hình, nếu target vẫn nằm trong lag limit.
- Nếu target vượt lag limit, FSFO có thể không xảy ra thay vì chấp nhận data loss vượt chính sách.

Không nên cam kết một con số RTO/RPO chỉ dựa vào threshold. Cần đo toàn bộ luồng ứng dụng trong diễn tập.

## 24. Các giới hạn cần hiểu

FSFO không thể khắc phục mọi loại lỗi:

- Không bảo vệ khỏi dữ liệu logic sai được replicate sang standby.
- Không thay thế backup và recovery.
- Không tự sửa corruption đã được truyền sang standby trong mọi tình huống.
- Không bảo đảm failover khi target standby không đủ đồng bộ.
- Không bảo đảm failover nếu observer và target không thể kết nối.
- Không tự giải quyết client retry hoặc transaction outcome.
- Không bảo đảm các hệ thống ngoài database chuyển role cùng lúc.
- Không thay thế RAC cho lỗi instance cục bộ.
- Không thay thế Clusterware trong việc phục hồi instance.
- Không loại bỏ rủi ro split brain nếu network partition và observer override được cấu hình thiếu thận trọng.

Data Guard bảo vệ bản sao ở site khác; backup bảo vệ khả năng phục hồi lịch sử; RAC bảo vệ availability trong cluster; Clusterware quản lý tài nguyên và instance; ứng dụng phải xử lý reconnect và transaction semantics. Các lớp này bổ sung cho nhau.

## 25. Ví dụ cấu hình minh họa từ đầu đến cuối

Giả sử:

- Primary có DB_UNIQUE_NAME là PRD.
- Physical standby có DB_UNIQUE_NAME là STB.
- Observer chạy trên máy OBS01.
- Broker đã quản lý PRD và STB.
- Mục tiêu là Maximum Availability.
- Observer có thể kết nối đến cả hai database.

Trên primary và standby, xác nhận Broker đang chạy:

~~~sql
SHOW PARAMETER dg_broker_start;
~~~

Trong DGMGRL:

~~~text
DGMGRL> SHOW CONFIGURATION;
DGMGRL> SHOW DATABASE VERBOSE 'PRD';
DGMGRL> SHOW DATABASE VERBOSE 'STB';
~~~

Cấu hình redo transport và protection mode theo thiết kế:

~~~text
DGMGRL> EDIT DATABASE 'PRD' SET PROPERTY LogXptMode = SYNC;
DGMGRL> EDIT DATABASE 'STB' SET PROPERTY LogXptMode = SYNC;
DGMGRL> EDIT CONFIGURATION SET PROTECTION MODE AS MaxAvailability;
~~~

Đặt target và threshold:

~~~text
DGMGRL> EDIT DATABASE 'PRD' SET PROPERTY FastStartFailoverTarget = 'STB';
DGMGRL> EDIT CONFIGURATION SET PROPERTY FastStartFailoverThreshold = 30;
~~~

Kiểm tra kết nối và database:

~~~text
DGMGRL> VALIDATE DATABASE VERBOSE 'STB';
DGMGRL> VALIDATE NETWORK CONFIGURATION FOR ALL;
~~~

Enable và start observer:

~~~text
DGMGRL> ENABLE FAST_START FAILOVER;
DGMGRL> START OBSERVER IN BACKGROUND;
~~~

Kiểm tra:

~~~text
DGMGRL> SHOW FAST_START FAILOVER;
DGMGRL> SHOW CONFIGURATION VERBOSE;
DGMGRL> SHOW DATABASE VERBOSE 'STB';
~~~

Trong môi trường thử nghiệm, có thể chạy observe-only trước khi bật failover thực. Sau khi kiểm thử thành công, cần hoàn thiện service role, client connection, monitoring, backup và quy trình reinstatement.

Các lệnh trên là ví dụ học tập. Cần xác nhận cú pháp, property và prerequisite của Oracle Database release đang chạy trước khi dùng trong production.

## 26. Checklist vận hành Data Guard Broker và observer

### Trước khi enable FSFO

- [ ] Primary và standby nằm trong Broker configuration.
- [ ] DG_BROKER_START được bật trên các member.
- [ ] SHOW CONFIGURATION không có lỗi chưa xử lý.
- [ ] Target standby đã được chọn và có thể nhận role primary.
- [ ] FastStartFailoverTarget được cấu hình đúng nếu có nhiều standby.
- [ ] Protection mode và LogXptMode phù hợp RPO.
- [ ] Standby redo logs được cấu hình đúng cho primary/standby và RAC thread.
- [ ] Redo transport và apply hoạt động ổn định.
- [ ] Target không có apply delay ngoài chủ đích.
- [ ] Observer có DGMGRL, Oracle Net và credential.
- [ ] Observer kết nối được tới primary và target.
- [ ] Static connect identifier được validate nếu cần.
- [ ] Threshold và lag limit được chọn theo số liệu.
- [ ] Service ứng dụng có role PRIMARY và client reconnect được kiểm thử.
- [ ] Flashback Database được bật nếu cần auto-reinstate.

### Khi FSFO đang chạy

- [ ] Observer process đang hoạt động.
- [ ] Broker nhận diện observer/master observer.
- [ ] FSFO status là Enabled.
- [ ] Target standby valid.
- [ ] FS_FAILOVER_STATUS thể hiện synchronized/within-lag theo protection mode.
- [ ] Redo transport không có lỗi.
- [ ] Apply lag nằm trong giới hạn.
- [ ] FRA và flashback logs còn đủ dung lượng.
- [ ] Observer log, broker log và alert log được giám sát.
- [ ] Cảnh báo được gửi qua hệ thống độc lập với primary site.

### Sau một lần failover

- [ ] Xác nhận database mới có DATABASE_ROLE là PRIMARY.
- [ ] Xác nhận database cũ không tiếp tục nhận ghi như primary.
- [ ] Xác nhận service và listener ở site mới.
- [ ] Kiểm tra ứng dụng reconnect và transaction outcome.
- [ ] Kiểm tra standby còn lại và redo transport mới.
- [ ] Reinstatement primary cũ hoặc dựng lại standby.
- [ ] Kiểm tra flashback và backup.
- [ ] Backup database sau role transition theo quy trình.
- [ ] Ghi lại nguyên nhân, timeline, RPO/RTO và hành động khắc phục.

## 27. Kết luận

Data Guard Broker quản lý cấu hình và điều phối role transition; observer theo dõi primary và target standby; Fast-Start Failover tự động chuyển target đủ điều kiện thành primary khi điều kiện cấu hình được thỏa mãn.

Để FSFO hoạt động đáng tin cậy, cần chọn target phù hợp, cấu hình protection mode và redo transport đúng RPO, đặt threshold và lag limit dựa trên dữ liệu thực tế, duy trì observer độc lập, kiểm tra trạng thái Broker và chuẩn bị service/client cho role transition. Điều kiện mặc định yêu cầu observer và target standby cùng nhận biết primary không còn khả dụng; target phải synchronized hoặc nằm trong lag limit tương ứng. ObserverOverride và health conditions có thể thay đổi hành vi, nên cần được đánh giá kỹ để tránh false failover và split brain.

Tự động failover chỉ là một phần của high availability. Backup, recovery, flashback, network, Clusterware, service management, ứng dụng và quy trình diễn tập vẫn cần được thiết kế đồng bộ để database mới thực sự tiếp tục phục vụ nghiệp vụ.
