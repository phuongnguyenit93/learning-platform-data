# Service trong RAC, phân phối kết nối và ràng buộc vị trí dịch vụ

Trong Oracle Real Application Clusters (RAC), một database có thể chạy trên nhiều instance cùng truy cập một bộ database files. Ứng dụng cần một cách kết nối ổn định và một cơ chế để Oracle phân phối workload giữa các instance. Oracle RAC dùng **database service** làm điểm truy cập logic cho ứng dụng và làm đơn vị quản lý workload, placement, load balancing, high availability và một số chính sách vận hành.

Service cho phép ứng dụng kết nối theo mục đích nghiệp vụ, chẳng hạn OLTP, báo cáo, batch hoặc read-only. Clusterware quản lý service và quyết định service có thể chạy trên instance nào, instance nào được ưu tiên, khi nào service được khởi động và cách service phản ứng khi instance gặp sự cố.

Cần phân biệt ba khái niệm:

- **Service** là tên kết nối logic đại diện cho một workload hoặc nhóm ứng dụng. Ứng dụng dùng service name trong connect descriptor.
- **Service placement** là tập ràng buộc xác định service được chạy trên instance hoặc server pool nào, có bao nhiêu instance phục vụ service và nơi nào là dự phòng.
- **Load balancing** là cách phân phối kết nối hoặc workload đến các instance đang cung cấp service. Việc phân phối kết nối lúc đăng nhập và cân bằng tải trong thời gian chạy là hai cơ chế khác nhau.

## 1. Database service trong Oracle RAC

Một database service là thuộc tính được đăng ký với Oracle Net Listener và được quản lý bởi Oracle Clusterware trong môi trường RAC. Khi ứng dụng kết nối bằng service name, listener tìm instance đang cung cấp service và chuyển kết nối đến instance phù hợp.

Ví dụ một RAC database có ba instance:

| Instance | Vai trò dự kiến |
|---|---|
| RAC1 | Chạy workload OLTP |
| RAC2 | Chạy workload OLTP |
| RAC3 | Có thể nhận OLTP khi RAC1 hoặc RAC2 gặp sự cố |

Có thể tạo service tên **oltp_rw.example.com** cho ứng dụng giao dịch. Service này ưu tiên RAC1 và RAC2, còn RAC3 là instance dự phòng. Ứng dụng chỉ cần cấu hình service name; khi RAC1 gặp sự cố, Clusterware có thể khởi động hoặc chuyển service sang instance còn khả dụng theo placement policy.

Service là một abstraction quan trọng vì ứng dụng không cần gắn cứng với một instance cụ thể. Nếu ứng dụng kết nối trực tiếp đến SID hoặc host của một node, việc chuyển workload khi node gặp sự cố sẽ khó quản lý hơn.

### Vì sao không nên dùng một service chung cho mọi workload?

Các loại workload có đặc điểm khác nhau:

- OLTP cần thời gian phản hồi thấp, nhiều phiên kết nối ngắn và phân phối kết nối linh hoạt.
- Reporting hoặc DSS có truy vấn dài, thường tiêu thụ CPU, I/O và bộ nhớ nhiều hơn.
- Batch có thể cần thời gian chạy ổn định và cửa sổ xử lý riêng.
- Read-only workload có thể được định tuyến đến standby hoặc các instance được dành riêng tùy kiến trúc.

Tạo service riêng cho từng workload giúp quản trị viên điều chỉnh placement, load balancing goal, resource plan, failover policy và theo dõi hiệu năng theo nhóm ứng dụng. Service name cũng có thể được dùng làm thuộc tính nhận diện workload trong quản trị tài nguyên.

Không nên tạo service quá nhỏ cho từng ứng dụng nếu các ứng dụng có cùng yêu cầu vận hành. Mỗi service bổ sung làm tăng độ phức tạp của cấu hình, giám sát và kiểm thử failover.

## 2. Các thành phần tham gia quản lý và kết nối service

### Oracle Clusterware

Oracle Clusterware quản lý tài nguyên database và service trong cluster. Service được khai báo bằng SRVCTL và lưu trong cấu hình Clusterware. Clusterware theo dõi trạng thái instance, node và service để thực hiện start, stop, relocate hoặc failover theo chính sách.

Trong RAC, nên dùng **srvctl** để tạo và quản lý các service do Clusterware kiểm soát. Không nên dùng lệnh tự quản lý service ở database level để thay thế cấu hình placement của Clusterware, vì hai cơ chế có thể không đồng bộ.

### Listener, SCAN và đăng ký service

Listener nhận kết nối Oracle Net. Trong RAC, client thường kết nối qua **SCAN (Single Client Access Name)**. SCAN được phân giải DNS thành các SCAN VIP; SCAN listener tiếp nhận kết nối và chuyển hướng client đến local listener của instance đang cung cấp service.

Các instance đăng ký service và endpoint với listener thông qua cơ chế đăng ký động của Oracle Net. Trong cấu hình RAC chuẩn, Clusterware và các tham số listener liên quan đảm nhiệm việc này.

Luồng kết nối khái quát:

~~~text
        Ứng dụng / Connection Pool
                    |
                    | SERVICE_NAME
                    v
             SCAN name (DNS)
                    |
           +--------+--------+
           |        |        |
           v        v        v
       SCAN L1  SCAN L2  SCAN L3
           \        |        /
            \       |       /
             \      v      /
          Listener chọn instance
                    |
             +------+------+
             |             |
             v             v
           RAC1           RAC2
        service OLTP   service OLTP
             \             /
              \           /
                RAC3
             instance dự phòng
~~~

Sơ đồ chỉ mô tả luồng khái niệm. SCAN listener thường redirect client đến local listener phù hợp; kết nối thực tế còn phụ thuộc service registration, trạng thái instance, cấu hình listener và client.

### Client và connection pool

Ứng dụng có thể kết nối trực tiếp hoặc thông qua connection pool. Connection pool quản lý số lượng session, tái sử dụng kết nối và có thể nhận thông báo load balancing/failover từ Oracle khi driver và cấu hình hỗ trợ.

Các thành phần thường gặp:

- Oracle JDBC Thin hoặc OCI driver.
- Oracle Universal Connection Pool (UCP).
- ODP.NET hoặc connection pool tương thích.
- ONS (Oracle Notification Service) để nhận FAN events trong các kiến trúc hỗ trợ.

Khả năng nhận thông báo và xử lý failover phụ thuộc driver, phiên bản, connection pool và cấu hình. Chỉ dùng SCAN connect string không tự động bảo đảm ứng dụng có thể tiếp tục transaction đang chạy khi instance lỗi.

## 3. Ràng buộc vị trí service trên RAC

Service placement xác định nơi service được phép chạy. Cấu hình cụ thể phụ thuộc database dùng **administrator-managed** hay **policy-managed**.

### Administrator-managed database

Trong mô hình administrator-managed, DBA chỉ định các instance cụ thể cho service:

- **Preferred instances**: các instance được ưu tiên chạy service trong điều kiện bình thường.
- **Available instances**: các instance dự phòng có thể nhận service nếu preferred instance không khả dụng.

Ví dụ:

| Service | Preferred | Available |
|---|---|---|
| OLTP | RAC1, RAC2 | RAC3 |
| REPORTING | RAC3 | RAC1, RAC2 |
| BATCH | RAC2 | RAC1 |

Khi service OLTP chạy trên RAC1 và RAC2, RAC3 không nhất thiết chạy service đó trong trạng thái bình thường. Nếu một preferred instance gặp sự cố, Clusterware có thể khởi động service trên instance available theo cấu hình và tài nguyên còn lại.

Available instance là vị trí dự phòng trong chính sách placement. Nó không có nghĩa ứng dụng đã có kết nối đến instance đó từ trước hoặc session đang chạy trên instance lỗi sẽ tự động được di chuyển nguyên trạng.

### Policy-managed database

Trong mô hình policy-managed, service được gắn với server pool thay vì danh sách instance cụ thể. Clusterware quản lý thành viên server pool và phân bổ service theo cardinality.

Hai kiểu cardinality thường gặp:

- **UNIFORM**: service có thể chạy trên tất cả instance phù hợp trong server pool.
- **SINGLETON**: service chỉ chạy trên một instance tại một thời điểm trong phạm vi server pool.

Ví dụ, service batch có thể được cấu hình SINGLETON để chỉ có một instance thực hiện workload đó tại một thời điểm. Khi instance hiện tại gặp sự cố, Clusterware có thể chuyển service sang instance khác trong pool nếu chính sách và tài nguyên cho phép.

Server pool còn có thuộc tính min/max size, importance và các ràng buộc quản trị cluster. Vì vậy, service placement phụ thuộc cả cấu hình service lẫn trạng thái server pool.

### Preferred và available không phải cơ chế load balancing

Preferred/available xác định tập instance cho service và hành vi placement/failover. Load balancing quyết định phân phối kết nối hoặc workload giữa các instance đang cung cấp service.

Ví dụ service có preferred RAC1 và RAC2. Cả hai instance đều đang chạy service, nhưng nếu connection load balancing không được cấu hình hoặc ứng dụng không sử dụng runtime load balancing, các kết nối vẫn có thể tập trung nhiều ở một instance.

Do đó cần cấu hình riêng:

1. Instance nào được phép cung cấp service.
2. Service chạy trên bao nhiêu instance.
3. Listener phân phối kết nối mới như thế nào.
4. Connection pool có cân bằng các kết nối đang được quản lý trong runtime hay không.

## 4. Tạo và quản lý service bằng SRVCTL

Trước khi tạo service, cần biết database unique name, tên instance, mô hình quản lý database và chính sách workload. Có thể kiểm tra database và cấu hình service bằng các lệnh:

~~~bash
srvctl config database
srvctl config database -db RACDB
srvctl status database -db RACDB
srvctl config service -db RACDB
~~~

Các tên RACDB, RAC1, RAC2 dưới đây là ví dụ. Thay bằng db_unique_name và instance name thực tế.

### Tạo service cho administrator-managed RAC

Ví dụ tạo service OLTP, ưu tiên hai instance RAC1 và RAC2, dùng RAC3 làm vị trí dự phòng:

~~~bash
srvctl add service \
  -db RACDB \
  -service oltp_rw \
  -preferred RAC1,RAC2 \
  -available RAC3 \
  -clbgoal SHORT \
  -rlbgoal SERVICE_TIME \
  -policy AUTOMATIC \
  -role PRIMARY
~~~

Ý nghĩa các tham số chính:

- **-db**: database unique name được Clusterware quản lý.
- **-service**: tên service cần tạo.
- **-preferred**: danh sách instance ưu tiên.
- **-available**: danh sách instance dự phòng.
- **-clbgoal SHORT**: chọn mục tiêu connection load balancing phù hợp với kết nối ngắn, thường gặp ở OLTP.
- **-rlbgoal SERVICE_TIME**: dùng thời gian phục vụ để đánh giá tải khi runtime load balancing được hỗ trợ.
- **-policy AUTOMATIC**: Clusterware quản lý việc khởi động service theo chính sách tự động.
- **-role PRIMARY**: chỉ chạy service khi database có role PRIMARY.

Các tùy chọn và cú pháp SRVCTL có thể khác theo phiên bản Grid Infrastructure và loại database. Hãy kiểm tra help của đúng phiên bản trước khi áp dụng vào production.

### Tạo service cho policy-managed RAC

Với database policy-managed, service được gắn vào server pool và đặt cardinality. Ví dụ minh họa:

~~~bash
srvctl add service \
  -db RACDB \
  -service batch_job \
  -serverpool batch_pool \
  -cardinality SINGLETON \
  -clbgoal LONG \
  -policy AUTOMATIC \
  -role PRIMARY
~~~

Service này chỉ chạy trên một instance trong server pool tại một thời điểm. Cấu hình server pool phải có khả năng cung cấp instance phù hợp. Không dùng tham số preferred/available như mô hình administrator-managed khi cấu hình service theo server pool.

### Khởi động, dừng và xem trạng thái

~~~bash
srvctl start service -db RACDB -service oltp_rw
srvctl status service -db RACDB -service oltp_rw
srvctl config service -db RACDB -service oltp_rw
~~~

Dừng service:

~~~bash
srvctl stop service -db RACDB -service oltp_rw
~~~

Nếu service được cấu hình AUTOMATIC, Clusterware quản lý việc khởi động theo trạng thái database, placement và chính sách. Nếu service dùng MANUAL, quản trị viên hoặc automation phải chủ động start service theo quy trình.

### Thay đổi placement

Có thể thay đổi danh sách instance hoặc thuộc tính service bằng SRVCTL. Ví dụ:

~~~bash
srvctl modify service \
  -db RACDB \
  -service oltp_rw \
  -preferred RAC1,RAC3 \
  -available RAC2
~~~

Sau khi sửa cấu hình, kiểm tra lại:

~~~bash
srvctl config service -db RACDB -service oltp_rw
srvctl status service -db RACDB -service oltp_rw
~~~

Cần lập kế hoạch cho thay đổi placement trong giờ vận hành phù hợp. Việc relocate hoặc stop/start service có thể làm session hiện tại bị ngắt, trừ khi ứng dụng có cơ chế failover/continuity thích hợp.

### Relocate service thủ công

Trong administrator-managed RAC, có thể chuyển service từ instance cũ sang instance mới:

~~~bash
srvctl relocate service \
  -db RACDB \
  -service oltp_rw \
  -oldinst RAC1 \
  -newinst RAC3
~~~

Lệnh minh họa cho trường hợp service đang chạy trên RAC1 và cần chuyển sang RAC3. Tên tham số có thể thay đổi theo phiên bản; xem trợ giúp SRVCTL tương ứng. Trước khi relocate, xác nhận RAC3 có đủ CPU, bộ nhớ, kết nối storage và năng lực phục vụ workload.

## 5. Phân phối kết nối lúc đăng nhập (connect-time load balancing)

Connect-time load balancing phân phối các kết nối mới đến những instance đang cung cấp service. Mục tiêu là tránh để mọi client mới dồn vào một instance trong khi instance khác còn nhiều tài nguyên.

Trong RAC, SCAN và listener giúp client kết nối thông qua một điểm truy cập chung. Khi có nhiều SCAN listener, DNS có thể trả về nhiều SCAN VIP. Client có thể thử các địa chỉ theo connect descriptor, còn listener định tuyến kết nối đến instance cung cấp service.

Ví dụ connect descriptor:

~~~text
(DESCRIPTION =
  (CONNECT_TIMEOUT = 5)
  (RETRY_COUNT = 3)
  (RETRY_DELAY = 2)
  (ADDRESS =
    (PROTOCOL = TCP)
    (HOST = rac-scan.example.com)
    (PORT = 1521)
  )
  (CONNECT_DATA =
    (SERVICE_NAME = oltp_rw.example.com)
  )
)
~~~

Có thể dùng Easy Connect:

~~~text
//rac-scan.example.com:1521/oltp_rw.example.com
~~~

Client nên sử dụng **SERVICE_NAME**. Trong RAC, không nên dùng SID của một instance làm địa chỉ kết nối chung cho ứng dụng cần HA và phân phối kết nối.

### Load balance trong ADDRESS_LIST

Một connect descriptor có thể có nhiều địa chỉ listener. Thuộc tính LOAD_BALANCE điều khiển cách Oracle Net lựa chọn giữa các địa chỉ trong ADDRESS_LIST. Đây là lựa chọn địa chỉ kết nối ở tầng Oracle Net; nó không thay thế service-level connection load balancing hoặc runtime load balancing.

Ví dụ tổng quát với nhiều địa chỉ listener:

~~~text
(DESCRIPTION =
  (LOAD_BALANCE = ON)
  (ADDRESS_LIST =
    (ADDRESS = (PROTOCOL = TCP) (HOST = listener-a.example.com) (PORT = 1521))
    (ADDRESS = (PROTOCOL = TCP) (HOST = listener-b.example.com) (PORT = 1521))
  )
  (CONNECT_DATA =
    (SERVICE_NAME = oltp_rw.example.com)
  )
)
~~~

LOAD_BALANCE trong ADDRESS_LIST có ý nghĩa khi descriptor có nhiều ADDRESS; nó điều khiển cách Oracle Net thử các địa chỉ listener trong danh sách. Ví dụ trên minh họa cơ chế Oracle Net tổng quát, không phải yêu cầu tạo hai SCAN name. Với RAC, thông thường client chỉ cần dùng một SCAN name; DNS trả về các SCAN VIP và SCAN listener thực hiện định tuyến đến local listener phù hợp. Không nên tự liệt kê địa chỉ VIP của từng node để thay thế SCAN.

### Connection load balancing goal

Service có thuộc tính CLB goal để định hướng cách listener phân phối kết nối:

- **SHORT**: phù hợp với workload có kết nối ngắn, số lần kết nối lớn và thời gian xử lý mỗi request tương đối ngắn. Mục tiêu là phân phối kết nối dựa trên tải service/instance để giảm thời gian phản hồi.
- **LONG**: phù hợp với các kết nối tồn tại lâu, ví dụ connection pool giữ session trong thời gian dài. Listener sử dụng cách đánh giá tải phù hợp với kết nối dài thay vì chỉ tối ưu cho thời gian thiết lập kết nối ngắn.

CLB goal không phải cam kết mọi instance sẽ có đúng số session bằng nhau. Tải CPU, thời gian xử lý, số session, cấu hình listener và chính sách service đều có thể ảnh hưởng phân phối.

## 6. Runtime load balancing và FAN

Connect-time load balancing chỉ quyết định nơi đặt kết nối mới khi client đăng nhập. Sau khi một connection pool đã tạo nhiều session và giữ chúng lâu dài, tải giữa các instance có thể thay đổi. Một instance có thể trở nên bận hơn trong khi các kết nối vẫn đang nằm trong pool.

**Runtime load balancing (RLB)** sử dụng thông tin tải service được Oracle cung cấp trong lúc database hoạt động. Connection pool tương thích có thể dùng thông tin này để chọn instance phù hợp khi cấp một kết nối cho request mới.

### RLB goal

Service có thể dùng một trong các mục tiêu phổ biến:

| RLB goal | Ý nghĩa | Workload phù hợp |
|---|---|---|
| SERVICE_TIME | Cân bằng theo thời gian phục vụ/response time | OLTP, request cần độ trễ thấp |
| THROUGHPUT | Cân bằng theo thông lượng | Batch hoặc workload xử lý khối lượng lớn |

Chọn goal theo mục tiêu thực tế của ứng dụng. Một workload ưu tiên response time có thể chọn SERVICE_TIME; workload cần throughput tổng thể có thể chọn THROUGHPUT. RLB chỉ phát huy tác dụng khi client pool/driver hỗ trợ và được cấu hình để nhận, sử dụng thông tin runtime load balancing.

### FAN events

Fast Application Notification (FAN) cung cấp thông báo về sự kiện trong cluster như instance up/down, service up/down và thay đổi trạng thái. Ứng dụng hoặc connection pool có tích hợp FAN có thể nhanh chóng loại bỏ kết nối đến instance lỗi, nhận biết service được khởi động ở instance khác và cấp kết nối mới đến nơi phù hợp.

Service notification có thể được bật trong cấu hình service:

~~~bash
srvctl modify service \
  -db RACDB \
  -service oltp_rw \
  -notification TRUE
~~~

FAN notification cần hạ tầng ONS và client tương thích. Chỉ bật notification trong cấu hình service không tự động làm một ứng dụng bất kỳ xử lý được sự kiện. Cần kiểm tra cấu hình ONS, driver, pool và cơ chế xử lý connection invalidation.

### Connection pool và runtime balancing

Trong môi trường Java, Oracle UCP có thể tích hợp với FAN và runtime load balancing. Connection pool nhận thông tin về trạng thái service/instance và sử dụng chúng khi chọn connection cho request. Với JDBC Thin, cần dùng đúng phiên bản driver và cấu hình pool hỗ trợ tính năng cần thiết.

Nếu ứng dụng dùng pool không tích hợp FAN/RLB, các kết nối đã được tạo có thể tiếp tục dồn ở một instance ngay cả khi tải đã thay đổi. Khi đó, cần cân nhắc chiến lược pool, thời gian sống connection, giới hạn pool và cơ chế reconnect.

## 7. Service placement theo role của database

Trong kiến trúc Data Guard, một database có thể chuyển role giữa PRIMARY và PHYSICAL STANDBY. Một số service chỉ nên chạy khi database là PRIMARY; service khác dành cho báo cáo trên standby.

Có thể ràng buộc service với role:

~~~bash
srvctl add service \
  -db RACDB \
  -service oltp_rw \
  -preferred RAC1,RAC2 \
  -available RAC3 \
  -role PRIMARY \
  -policy AUTOMATIC
~~~

Ví dụ service chỉ dành cho truy vấn báo cáo trên physical standby:

~~~bash
srvctl add service \
  -db RACSTBY \
  -service reporting_ro \
  -preferred STBY1,STBY2 \
  -role PHYSICAL_STANDBY \
  -policy AUTOMATIC
~~~

Tên database, instance và role là ví dụ. Trong môi trường Data Guard, cần phối hợp service role với Data Guard Broker, Clusterware và quy trình switchover/failover. Sau khi database đổi role, service phù hợp có thể được khởi động hoặc dừng theo cấu hình role. Điều này giúp ứng dụng tiếp tục dùng cùng service name sau khi role chuyển đổi nếu kiến trúc và cấu hình connect string được thiết kế tương ứng.

Service role không tự biến một service read-write thành read-only hoặc ngược lại. Cần bảo đảm open mode, database role, session permissions và cấu hình ứng dụng phù hợp.

## 8. Service và high availability khi instance lỗi

Khi một instance gặp sự cố, Clusterware phát hiện trạng thái lỗi và thực hiện chính sách resource recovery. Nếu service có available instance hoặc server pool có instance thay thế, Clusterware có thể khởi động service trên nơi phù hợp.

Cần phân biệt ba lớp:

1. **Service failover/relocation**: service được khởi động trên instance khác để nhận các kết nối mới.
2. **Client reconnect**: ứng dụng kết nối lại qua SCAN/service name và được listener định tuyến đến instance đang cung cấp service.
3. **Session hoặc transaction continuity**: ứng dụng tiếp tục session hoặc transaction theo cơ chế như TAF, Application Continuity hoặc Transaction Guard khi điều kiện, driver và cấu hình hỗ trợ.

Việc service xuất hiện trên instance khác không có nghĩa session cũ tự di chuyển nguyên trạng. Session trên instance lỗi thường bị mất. Client cần reconnect; nếu muốn tiếp tục xử lý request hoặc replay transaction, cần cấu hình và kiểm thử cơ chế continuity phù hợp.

### TAF

Transparent Application Failover (TAF) hỗ trợ client kết nối lại và trong một số trường hợp phục hồi session hoặc cursor/select theo cấu hình và giới hạn của TAF. TAF có thể dùng failover type SESSION hoặc SELECT tùy driver và service.

Ví dụ cấu hình minh họa cho service:

~~~bash
srvctl modify service \
  -db RACDB \
  -service reporting_ro \
  -failovertype SELECT \
  -failovermethod BASIC \
  -failoverretry 30 \
  -failoverdelay 5
~~~

Các tùy chọn failover và khả năng hỗ trợ phụ thuộc phiên bản Oracle, loại client và workload. SELECT failover có thể thử lại truy vấn đang fetch trong một số điều kiện; không đồng nghĩa với việc mọi transaction đang chạy đều được khôi phục.

### Application Continuity và Transaction Guard

Application Continuity (AC) có thể replay một request/transaction đủ điều kiện sau lỗi kết nối, giúp ứng dụng giảm tác động của gián đoạn. Transaction Guard hỗ trợ xác định kết quả commit của transaction để tránh ứng dụng tự ý thực hiện lại một giao dịch mà kết quả commit chưa rõ.

Các service hỗ trợ AC có thể cần các thuộc tính như failover type TRANSACTION, commit outcome, replay initialization time và session state consistency. Ví dụ dưới đây chỉ minh họa nhóm tham số, phải kiểm tra phiên bản và driver tương thích trước khi triển khai:

~~~bash
srvctl modify service \
  -db RACDB \
  -service oltp_rw \
  -failovertype TRANSACTION \
  -commit_outcome TRUE \
  -replay_init_time 600 \
  -session_state_consistency DYNAMIC
~~~

Không nên bật các thuộc tính này mà chưa xác định ứng dụng có đáp ứng điều kiện replay hay không. Ứng dụng có external side effect, thao tác không idempotent hoặc session state không được quản lý phù hợp có thể cần xử lý riêng. Phải kiểm thử các tình huống lỗi thực tế trước khi xem AC là cơ chế bảo đảm transaction continuity.

## 9. Service và quản lý tài nguyên workload

Service còn có thể làm căn cứ để phân loại workload trong Oracle Database Resource Manager. DBA có thể gắn consumer group cho session theo service name, module, action hoặc thuộc tính khác.

Ví dụ, service OLTP và REPORTING có thể được gắn vào consumer group riêng để kiểm soát mức ưu tiên CPU, parallelism hoặc các giới hạn tài nguyên. Điều này giúp workload báo cáo lớn không chiếm hết tài nguyên mà ứng dụng giao dịch cần.

Một service không tự tạo ra resource plan. Cần cấu hình Resource Manager plan và mapping rule phù hợp. Có thể kiểm tra service và session bằng các view như:

~~~sql
SELECT inst_id,
       name,
       network_name,
       goal,
       clb_goal
FROM   gv$services
ORDER BY name, inst_id;
~~~

Với session đang kết nối:

~~~sql
SELECT inst_id,
       sid,
       serial#,
       service_name,
       username,
       machine,
       program
FROM   gv$session
WHERE  type = 'USER'
ORDER BY service_name, inst_id;
~~~

Các view GV$ cho phép quan sát nhiều instance trong RAC. Quyền truy cập phụ thuộc tài khoản và quyền dictionary. Cột hiển thị có thể thay đổi theo phiên bản; kiểm tra data dictionary khi truy vấn trên phiên bản cụ thể.

## 10. Kiểm tra service placement và kết nối

### Xem cấu hình service

~~~bash
srvctl config service -db RACDB
srvctl config service -db RACDB -service oltp_rw
~~~

Thông tin cần xác nhận:

- Service name và network name.
- Preferred/available instance hoặc server pool/cardinality.
- Management policy AUTOMATIC hay MANUAL.
- Database role được phép chạy service.
- CLB goal và RLB goal.
- Notification và các thuộc tính failover/continuity.
- Các thuộc tính liên quan đến resource plan hoặc workload nếu có.

### Xem trạng thái service trên cluster

~~~bash
srvctl status service -db RACDB
srvctl status service -db RACDB -service oltp_rw
~~~

Kết quả giúp xác định service đang chạy trên instance nào. Nếu service không chạy ở vị trí mong muốn, kiểm tra trạng thái instance, placement policy, server pool, resource dependency và log Clusterware.

### Kiểm tra listener

Từ máy chủ database hoặc máy có Oracle Net tools, có thể xem listener service registration bằng:

~~~bash
lsnrctl services LISTENER
~~~

Tên listener có thể khác theo môi trường. Với SCAN listener, dùng tên listener tương ứng hoặc công cụ quản trị Grid Infrastructure. Kiểm tra service đã được đăng ký, handler có trạng thái sẵn sàng và listener có nhận đúng network service name hay không.

### Kiểm tra service trong database

~~~sql
SELECT inst_id,
       name,
       network_name,
       creation_date
FROM   gv$services
ORDER BY name, inst_id;
~~~

Để biết session đang kết nối qua service nào:

~~~sql
SELECT inst_id,
       service_name,
       COUNT(*) AS session_count
FROM   gv$session
WHERE  type = 'USER'
GROUP BY inst_id, service_name
ORDER BY service_name, inst_id;
~~~

Session count chỉ là một chỉ số. Một instance có ít session hơn vẫn có thể bận hơn nếu các session đó chạy truy vấn dài hoặc tiêu thụ tài nguyên lớn. Hãy kết hợp session count với CPU, response time, active sessions, wait events và thông tin service runtime load balancing.

## 11. Thay đổi service và kiểm thử failover

Trước khi thay đổi service trong production, cần xác định ảnh hưởng đến session đang hoạt động, pool và ứng dụng. Một số thay đổi có thể yêu cầu service restart hoặc relocate để có hiệu lực.

Quy trình kiểm thử nên bao gồm:

1. Ghi nhận cấu hình hiện tại bằng SRVCTL và trạng thái service.
2. Xác nhận ứng dụng đang kết nối qua SCAN và SERVICE_NAME.
3. Ghi nhận số session, tải CPU, response time và phân phối kết nối trên từng instance.
4. Thử stop hoặc relocate service trong môi trường kiểm thử.
5. Quan sát listener redirect, FAN events và hành vi connection pool.
6. Thử tình huống instance lỗi, service được khởi động ở instance dự phòng và client reconnect.
7. Nếu dùng TAF/AC, kiểm thử truy vấn đang fetch, transaction đang chạy và kết quả commit.
8. Khôi phục cấu hình sau kiểm thử và xác nhận service chạy đúng placement.

Không nên thử dừng instance production chỉ để chứng minh failover nếu chưa có cửa sổ bảo trì và kế hoạch phối hợp ứng dụng. Có thể kiểm thử bằng relocate service hoặc môi trường staging phù hợp trước.

## 12. Các vấn đề thường gặp

### Ứng dụng kết nối vào một instance cố định

Nguyên nhân thường là connect string dùng host/VIP node hoặc SID thay vì SCAN và service name. Kiểm tra datasource URL, tnsnames.ora và cấu hình pool. Dùng SCAN hostname cùng SERVICE_NAME để client có thể được định tuyến đến instance cung cấp service.

### Service không chạy trên instance dự kiến

Kiểm tra preferred/available instances, server pool, cardinality, role, management policy và trạng thái instance. Nếu instance không thuộc placement constraint hoặc không đủ điều kiện, Clusterware sẽ không chạy service ở đó.

### Service đã chạy nhưng kết nối không cân bằng

Kiểm tra CLB goal, listener registration, trạng thái các handler và cách client tạo kết nối. Với pool giữ session lâu, connect-time load balancing chỉ ảnh hưởng kết nối mới. Muốn cân bằng runtime cần driver/pool hỗ trợ RLB và FAN.

### Service chuyển instance nhưng ứng dụng vẫn lỗi

Service relocation chỉ tạo điểm tiếp nhận kết nối mới. Ứng dụng có thể còn giữ connection cũ hoặc transaction bị gián đoạn. Kiểm tra FAN integration, timeout, retry, TAF hoặc Application Continuity và logic xử lý lỗi của ứng dụng.

### FAN event không đến connection pool

Kiểm tra service notification, ONS configuration, network connectivity giữa client và ONS, driver version và cấu hình pool. FAN chỉ hữu ích khi ứng dụng có thành phần nhận và xử lý event.

### Preferred instance bị lỗi nhưng service không chuyển

Kiểm tra danh sách available instance, policy AUTOMATIC/MANUAL, role, server pool và trạng thái resource Clusterware. Xem log CRS/Clusterware và output SRVCTL để xác định vì sao service không được start trên vị trí dự phòng.

### Phân phối kết nối không đều dù DOP hoặc CLB đã đặt

CLB goal không bảo đảm số session tuyệt đối bằng nhau. Kết nối có thời gian sống khác nhau, connection pool có thể giữ session lâu, và một số instance có năng lực hoặc workload khác nhau. Đánh giá theo response time, throughput, active sessions và tải thực tế thay vì chỉ đếm session.

## 13. Quy trình thiết kế service cho RAC

1. **Phân nhóm workload.** Xác định OLTP, reporting, batch và read-only workload có yêu cầu khác nhau về độ trễ, throughput và thời gian chạy.
2. **Đặt service name rõ ràng.** Dùng tên thể hiện chức năng và môi trường, ví dụ oltp_rw hoặc reporting_ro.
3. **Xác định mô hình database.** Kiểm tra administrator-managed hay policy-managed để chọn preferred/available hoặc server pool/cardinality.
4. **Đặt placement constraints.** Xác định instance ưu tiên, instance dự phòng, số instance chạy service và role database được phép cung cấp service.
5. **Chọn CLB/RLB goal.** Dựa trên workload ngắn/dài và mục tiêu response time/throughput.
6. **Cấu hình kết nối.** Dùng SCAN và SERVICE_NAME; đặt timeout/retry hợp lý trong connect descriptor hoặc driver.
7. **Cấu hình HA.** Chọn notification, FAN, TAF hoặc Application Continuity phù hợp khả năng client và yêu cầu transaction.
8. **Tích hợp quản lý tài nguyên.** Gắn service với consumer group/resource plan khi cần cô lập workload.
9. **Kiểm tra runtime.** Quan sát service placement, listener registration, session distribution và response time trên từng instance.
10. **Diễn tập failover.** Kiểm tra instance failure, service relocation, client reconnect và transaction continuity theo kịch bản ứng dụng.

## 14. Nguyên tắc vận hành quan trọng

- Dùng service name làm điểm kết nối ổn định cho ứng dụng RAC; ưu tiên SCAN thay cho host/VIP của một node.
- Thiết kế service theo workload để có thể áp dụng placement, load balancing và resource plan phù hợp.
- Dùng preferred/available cho administrator-managed database; dùng server pool/cardinality cho policy-managed database.
- Phân biệt placement với load balancing. Service có thể chạy đúng instance nhưng kết nối vẫn phân phối chưa hợp lý.
- Cấu hình CLB goal và RLB goal theo mục tiêu thực tế; kiểm tra client pool có hỗ trợ runtime load balancing hay không.
- Bật FAN notification khi ứng dụng và connection pool có thể nhận, xử lý event.
- Không giả định service relocation tự phục hồi session hoặc transaction. Cần cơ chế client reconnect, TAF hoặc Application Continuity phù hợp.
- Với Data Guard, ràng buộc service theo database role để workload chỉ chạy trên role đúng.
- Kiểm tra SRVCTL, listener registration, GV$SERVICES và GV$SESSION sau khi thay đổi.
- Kiểm thử relocate/failover trong môi trường phù hợp và theo dõi tác động đến ứng dụng.

Service là đơn vị kết nối và quản lý workload quan trọng trong Oracle RAC. Khi kết hợp placement constraints, SCAN/listener, connect-time load balancing, runtime load balancing và cơ chế client failover đúng cách, ứng dụng có thể sử dụng cluster linh hoạt hơn, phân phối tải hợp lý và phục hồi kết nối tốt hơn khi instance gặp sự cố.
