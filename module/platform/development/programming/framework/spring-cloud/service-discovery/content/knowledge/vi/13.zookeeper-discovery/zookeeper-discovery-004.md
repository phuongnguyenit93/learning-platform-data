# Khởi tạo cụm Zookeeper và cấu hình connect-string

## 1. ZooKeeper làm gì trong Service Discovery?

ZooKeeper là dịch vụ điều phối phân tán, cung cấp cây dữ liệu (znodes), cơ chế đồng bộ và session. Spring Cloud Zookeeper Discovery sử dụng ZooKeeper để lưu thông tin đăng ký service và tìm instance theo tên dịch vụ.

Trong môi trường production, ứng dụng thường kết nối đến một **ensemble** gồm nhiều ZooKeeper server. Các server phối hợp bầu leader, sao chép trạng thái và tiếp tục phục vụ khi một node gặp sự cố, miễn là phần còn lại vẫn giữ được quorum.

Bài này hướng dẫn tạo ensemble ba node, cấu hình các cổng, định danh từng server, kiểm tra quorum và khai báo connect-string cho ứng dụng Spring Cloud.

## 2. Thành phần và cổng mạng

| Cổng ví dụ | Vai trò | Ai cần truy cập? |
|---:|---|---|
| 2181 | Client port: nhận kết nối từ ứng dụng và CLI | Ứng dụng và máy quản trị được cấp quyền |
| 2888 | Peer communication giữa các thành viên ensemble | Các ZooKeeper server |
| 3888 | Leader election giữa các thành viên | Các ZooKeeper server |

Các số cổng là ví dụ phổ biến, có thể thay đổi trong zoo.cfg. Client chỉ kết nối tới client port; không cấu hình Spring Cloud kết nối đến peer port hoặc election port.

~~~mermaid
flowchart TB
    APP[Spring Cloud applications] -->|Client port 2181| Z1[ZooKeeper 1]
    APP -->|Client port 2181| Z2[ZooKeeper 2]
    APP -->|Client port 2181| Z3[ZooKeeper 3]
    Z1 <-->|Peer 2888 / Election 3888| Z2
    Z2 <-->|Peer 2888 / Election 3888| Z3
    Z3 <-->|Peer 2888 / Election 3888| Z1
~~~

Các server cần hostname ổn định và truy cập được qua hai cổng peer/election. Ứng dụng chỉ cần đường mạng đến client port của các server trong connect string.

## 3. Chọn số lượng node và hiểu quorum

ZooKeeper dùng quorum để xác nhận thay đổi. Một ensemble cần đa số thành viên hoạt động để tiếp tục xử lý thao tác ghi và duy trì trạng thái nhất quán.

| Số server | Quorum cần có | Số server có thể mất mà vẫn còn quorum |
|---:|---:|---:|
| 1 | 1 | 0 |
| 3 | 2 | 1 |
| 5 | 3 | 2 |
| 4 | 3 | 1 |

Production thường chọn 3 hoặc 5 server thay vì 2 hoặc 4. Ensemble 4 node vẫn cần 3 node, nên khả năng chịu lỗi tương đương ensemble 3 node nhưng chi phí vận hành cao hơn.

Với ba node, hãy đặt chúng trên các máy hoặc failure domain khác nhau. Nếu cả ba server nằm trên cùng một host vật lý hoặc cùng vùng mạng dễ lỗi, việc có ba tiến trình không mang lại khả năng chịu lỗi thực chất.

Khi mất quorum, client có thể còn giữ session hoặc dữ liệu cục bộ trong một thời gian, nhưng không nên xem registry là sẵn sàng nhận thay đổi mới.

## 4. Chuẩn bị ba ZooKeeper server

Ví dụ dùng ba máy hoặc container có hostname ổn định:

| Server ID | Hostname | Client port | Peer port | Election port |
|---:|---|---:|---:|---:|
| 1 | zk1.internal | 2181 | 2888 | 3888 |
| 2 | zk2.internal | 2181 | 2888 | 3888 |
| 3 | zk3.internal | 2181 | 2888 | 3888 |

Trước khi khởi động:

- Hostname phải phân giải được từ mọi ZooKeeper server.
- Mỗi server có thư mục dữ liệu bền vững, có quyền đọc/ghi phù hợp.
- dataDir của mỗi server phải riêng biệt, không chia sẻ cùng thư mục dữ liệu.
- Mỗi server có file myid chứa đúng ID được khai báo trong zoo.cfg.
- Firewall cho phép peer port và election port giữa các ZooKeeper server.
- Chỉ mở client port cho ứng dụng và máy quản trị được phép kết nối.

Không dùng localhost trong danh sách server của một ensemble phân tán. Mỗi node phải nhận diện đúng hostname của mình và kết nối được đến các peer.

## 5. Cấu hình zoo.cfg

ZooKeeper sử dụng file cấu hình thường có tên zoo.cfg. Các thành viên trong ensemble cần khai báo cùng danh sách server và cùng tham số quorum.

Ví dụ cấu hình dùng cho cả ba node:

~~~properties
tickTime=2000
initLimit=10
syncLimit=5
dataDir=/var/lib/zookeeper
clientPort=2181

server.1=zk1.internal:2888:3888
server.2=zk2.internal:2888:3888
server.3=zk3.internal:2888:3888
~~~

| Thuộc tính | Ý nghĩa |
|---|---|
| tickTime | Đơn vị thời gian cơ bản của ZooKeeper, tính bằng mili giây |
| initLimit | Số tick tối đa dành cho follower khởi tạo và đồng bộ với leader |
| syncLimit | Số tick tối đa follower có thể trễ so với leader trong quá trình đồng bộ |
| dataDir | Thư mục lưu snapshot và transaction log theo cấu hình lưu trữ của phiên bản |
| clientPort | Cổng tiếp nhận kết nối client |
| server.X | Khai báo thành viên ensemble với server ID, peer port và election port |

Với tickTime=2000, một tick tương ứng 2 giây. initLimit=10 và syncLimit=5 được tính theo số tick, không phải số giây trực tiếp. Giá trị trong ví dụ là điểm bắt đầu phổ biến; cần điều chỉnh theo độ trễ mạng, tốc độ đĩa và tải thực tế.

### 5.1. Định danh từng server bằng myid

Trong thư mục dataDir, ZooKeeper cần file myid chứa ID của node. Với cấu hình trên:

Trên zk1.internal:

~~~bash
mkdir -p /var/lib/zookeeper
echo 1 > /var/lib/zookeeper/myid
~~~

Trên zk2.internal:

~~~bash
mkdir -p /var/lib/zookeeper
echo 2 > /var/lib/zookeeper/myid
~~~

Trên zk3.internal:

~~~bash
mkdir -p /var/lib/zookeeper
echo 3 > /var/lib/zookeeper/myid
~~~

Mỗi node chỉ có một myid và ID đó phải khớp hậu tố trong server.X. Không sao chép file myid từ node này sang node khác. Nếu hai server dùng cùng ID, quá trình khởi động hoặc bầu chọn thành viên có thể thất bại.

### 5.2. Khác biệt cấu hình theo node

Danh sách server.1, server.2, server.3 cần nhất quán trên cả ba server. Các giá trị riêng theo máy gồm:

- dataDir trỏ đến thư mục dữ liệu cục bộ của node đó.
- myid chứa ID riêng của node.
- clientPort có thể giống nhau nếu mỗi server chạy trên máy/container riêng; nếu chạy nhiều tiến trình trên cùng host thì phải dùng cổng khác nhau.
- Nếu bind client port vào một interface cụ thể, địa chỉ bind phải phù hợp với mạng triển khai.

Không chia sẻ cùng một dataDir giữa nhiều server và không đặt myid vào thư mục dùng chung.

## 6. Khởi động và kiểm tra ensemble

Khởi động ZooKeeper bằng script đi kèm bản phân phối. Tên script và đường dẫn có thể khác tùy cách cài đặt:

~~~bash
bin/zkServer.sh start
~~~

Kiểm tra trạng thái trên từng node:

~~~bash
bin/zkServer.sh status
~~~

Trong ensemble khỏe mạnh, một node thường được bầu làm **leader**, các node còn lại là **follower**. Với phiên bản và chế độ cấu hình khác nhau, lệnh status có thể hiển thị thêm thông tin về node hoặc chế độ đang chạy.

Kết nối bằng CLI đến từng server:

~~~bash
bin/zkCli.sh -server zk1.internal:2181
~~~

Trong CLI, có thể đọc root znode:

~~~text
ls /
~~~

Nếu CLI kết nối thành công, điều đó chứng minh client port có thể nhận kết nối và session được tạo. Để xác minh ensemble, cần kiểm tra thêm trạng thái leader/follower trên các node và log quorum; chỉ kết nối được một client port chưa chứng minh toàn bộ ensemble có quorum.

### 6.1. Kiểm tra lệnh bốn ký tự (Four Letter Words)

Một số bản ZooKeeper hỗ trợ lệnh quản trị bốn ký tự như ruok, srvr và mntr. Trên các phiên bản hiện đại, lệnh cần được cho phép rõ ràng qua cấu hình, ví dụ:

~~~properties
4lw.commands.whitelist=ruok,srvr,mntr
~~~

Sau khi cấu hình và khởi động lại theo quy trình vận hành, có thể kiểm tra:

~~~bash
echo ruok | nc zk1.internal 2181
echo srvr | nc zk1.internal 2181
~~~

ruok trả về imok cho biết tiến trình đang phản hồi lệnh. Nó không tự chứng minh node đang có quorum hoặc có thể commit ghi. Dùng srvr, mntr, zkServer.sh status và log để xác minh vai trò cùng trạng thái đồng bộ.

Chỉ bật các lệnh quản trị cần thiết và giới hạn truy cập client port. Không mở các lệnh chẩn đoán cho mạng công cộng.

## 7. Hiểu connect-string

Connect string là danh sách endpoint client của ZooKeeper mà ứng dụng có thể thử kết nối. Cú pháp cơ bản:

~~~text
zk1.internal:2181,zk2.internal:2181,zk3.internal:2181
~~~

Các endpoint được phân tách bằng dấu phẩy. Client sử dụng danh sách này để thiết lập session và có thể thử server khác khi kết nối hiện tại bị lỗi hoặc node không còn phục vụ. Danh sách nên chứa nhiều thành viên của ensemble để ứng dụng có lựa chọn khi một node dừng.

Connect string không phải danh sách peer port. Ứng dụng luôn dùng **client port** (2181 trong ví dụ), còn peer port và election port chỉ dành cho giao tiếp giữa các server.

### 7.1. Connect string có chroot path

ZooKeeper cho phép client gắn một chroot path vào cuối connect string:

~~~text
zk1.internal:2181,zk2.internal:2181,zk3.internal:2181/spring-cloud
~~~

Khi dùng chroot /spring-cloud, client nhìn cây dữ liệu bắt đầu từ path này như thể đó là root riêng của nó. Các ứng dụng khác có thể dùng chroot khác để tách namespace logic trên cùng ensemble.

Path chroot phải được tạo trước khi client kết nối. Ví dụ, kết nối CLI không dùng chroot rồi tạo path:

~~~bash
bin/zkCli.sh -server zk1.internal:2181
~~~

~~~text
create /spring-cloud "service-discovery-root"
~~~

Sau đó ứng dụng mới dùng connect string có hậu tố /spring-cloud. Nếu path chưa tồn tại, client có thể gặp lỗi NoNode khi sử dụng namespace đó.

Chroot chỉ tách không gian tên mà client quan sát; nó không tạo một ensemble riêng, không thay thế ACL và không phải ranh giới bảo mật độc lập.

## 8. Cấu hình connect-string trong Spring Cloud Zookeeper

Ứng dụng Spring Boot dùng Spring Cloud Zookeeper Discovery thường khai báo starter phù hợp và endpoint ZooKeeper trong application.yml.

Với Maven, dependency thường dùng:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-zookeeper-discovery</artifactId>
</dependency>
~~~

Phiên bản starter cần được quản lý bằng Spring Cloud BOM tương thích với Spring Boot đang dùng. Không tự ghép version của starter từ release train khác.

Cấu hình client kết nối đến ensemble:

~~~yaml
spring:
  application:
    name: payment-service
  cloud:
    zookeeper:
      connect-string: zk1.internal:2181,zk2.internal:2181,zk3.internal:2181
      discovery:
        enabled: true
~~~

Thuộc tính spring.cloud.zookeeper.connect-string xác định danh sách ZooKeeper server mà Spring Cloud Zookeeper sử dụng. spring.cloud.zookeeper.discovery.enabled bật tích hợp service discovery; giá trị mặc định có thể phụ thuộc phiên bản và starter, nên khai báo tường minh giúp cấu hình dễ đọc.

Nếu dùng namespace riêng:

~~~yaml
spring:
  cloud:
    zookeeper:
      connect-string: zk1.internal:2181,zk2.internal:2181,zk3.internal:2181/spring-cloud
~~~

Đảm bảo /spring-cloud đã tồn tại trước khi khởi động ứng dụng. Nếu có nhiều service cùng dùng một ensemble, nên thống nhất chroot path để chúng cùng nhìn thấy một registry namespace.

### 8.1. Đưa connect string ra biến môi trường

Không nên ghi địa chỉ hạ tầng khác nhau vào mã nguồn. Spring Boot hỗ trợ ánh xạ biến môi trường vào property; có thể đặt:

~~~bash
export SPRING_CLOUD_ZOOKEEPER_CONNECTSTRING=zk1.internal:2181,zk2.internal:2181,zk3.internal:2181
~~~

Trên Windows PowerShell:

~~~powershell
$env:SPRING_CLOUD_ZOOKEEPER_CONNECTSTRING = "zk1.internal:2181,zk2.internal:2181,zk3.internal:2181"
~~~

Giá trị này được ánh xạ tới spring.cloud.zookeeper.connect-string. Mỗi môi trường có thể cấp danh sách endpoint riêng qua deployment manifest hoặc configuration store. Nếu thiếu biến trong production, hãy kiểm tra cấu hình khi khởi động để phát hiện thiếu endpoint sớm; không để ứng dụng âm thầm kết nối đến localhost.

## 9. Kết nối, session và khả năng phục hồi

ZooKeeper client tạo session với ensemble. Session có timeout; nếu client mất kết nối quá lâu và session hết hạn, ephemeral znode gắn với session có thể bị xóa. Spring Cloud Zookeeper Discovery sử dụng cơ chế này để quản lý vòng đời đăng ký instance.

Connect string có nhiều server giúp client thử endpoint khác trong ensemble, nhưng không làm session tồn tại vô hạn. Khi kết nối gián đoạn:

- Client có thể chuyển sang server khác trong cùng ensemble.
- Nếu gián đoạn ngắn và session còn hiệu lực, client có thể khôi phục session.
- Nếu session hết hạn, client cần tạo session mới và cơ chế discovery có thể đăng ký lại instance.
- Nếu ensemble mất quorum, các thao tác ghi và cập nhật registry không thể được bảo đảm hoạt động bình thường.

Do đó, connect string nên liệt kê nhiều node, session timeout cần phù hợp với mạng và thời gian pause của JVM, còn ứng dụng cần xử lý trạng thái kết nối lại.

Không nhầm lẫn giữa connect-string và timeout. Connect string chỉ cung cấp địa chỉ để tìm server; session timeout điều khiển khoảng thời gian session có thể không liên lạc trước khi hết hạn.

## 10. Kiểm tra ứng dụng đã kết nối và đăng ký

Sau khi khởi động ZooKeeper ensemble, khởi động một service Spring Cloud có cấu hình connect string. Kiểm tra theo thứ tự:

1. Xác nhận log ứng dụng cho thấy client kết nối được tới ZooKeeper.
2. Kiểm tra không có lỗi DNS, connection refused, timeout hoặc authentication.
3. Dùng ZooKeeper CLI kết nối vào đúng ensemble và đúng chroot namespace.
4. Kiểm tra cây discovery mà Spring Cloud Zookeeper sử dụng. Mặc định phổ biến là /services, nhưng có thể thay đổi theo cấu hình discovery root của phiên bản đang dùng.
5. Xác nhận service ID và instance node xuất hiện sau khi ứng dụng đăng ký.
6. Dừng ứng dụng có trật tự, sau đó quan sát node đăng ký được xóa theo cơ chế lifecycle.
7. Thử dừng một ZooKeeper server để xác minh client vẫn kết nối được đến ensemble còn quorum.

Ví dụ kiểm tra root và namespace:

~~~bash
bin/zkCli.sh -server zk1.internal:2181
~~~

~~~text
ls /
ls /spring-cloud
ls /spring-cloud/services
~~~

Nếu không dùng chroot, kiểm tra path discovery root tương ứng, ví dụ /services. Path cụ thể phụ thuộc cấu hình và phiên bản; hãy xác minh bằng cấu hình Spring Cloud Zookeeper đang chạy thay vì tạo tùy tiện nhiều cây khác nhau.

## 11. Bảo mật và vận hành kết nối

ZooKeeper lưu dữ liệu điều phối và thông tin đăng ký dịch vụ. Trong môi trường production, cần bảo vệ cả client port lẫn kênh peer:

- Chỉ cho phép workload và máy quản trị hợp lệ truy cập client port.
- Chỉ cho phép các thành viên ensemble giao tiếp qua peer port và election port.
- Bật xác thực và ACL phù hợp; giới hạn quyền đọc/ghi theo namespace và ứng dụng.
- Cân nhắc TLS và cơ chế bảo mật kết nối theo khả năng của phiên bản ZooKeeper và client library.
- Dùng storage bền vững cho dataDir, giám sát dung lượng đĩa và độ trễ I/O.
- Theo dõi leader election, số follower đồng bộ, session expiration, request latency và tình trạng quorum.
- Sao lưu theo quy trình phù hợp và kiểm thử phục hồi; không sao chép trực tiếp thư mục dữ liệu đang hoạt động giữa các node.

Chroot path không thay thế ACL. Nếu hai ứng dụng dùng hai chroot khác nhau nhưng cùng có quyền truy cập root rộng, việc tách namespace không đủ để ngăn truy cập trái phép.

## 12. Lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Server không khởi động | myid thiếu hoặc không khớp server.X | Kiểm tra dataDir/myid và danh sách server |
| Node không tham gia quorum | Peer port/election port bị chặn hoặc DNS sai | Kiểm tra hostname, firewall và log quorum |
| Client báo connection refused | Dùng sai port hoặc server chưa lắng nghe client port | Kiểm tra clientPort, tiến trình và endpoint |
| Client chỉ kết nối được một node | Connect string thiếu node hoặc mạng chỉ cho phép một endpoint | Kiểm tra danh sách host và firewall từ workload |
| Chroot báo NoNode | Path chroot chưa được tạo | Tạo path trước khi dùng connect string có chroot |
| Ứng dụng không thấy service | Namespace hoặc discovery root không thống nhất | Kiểm tra chroot, discovery root và cây znode |
| Instance biến mất sau gián đoạn mạng | Session hết hạn và ephemeral node bị xóa | Kiểm tra session timeout, reconnect và đăng ký lại |
| Ensemble không thể ghi | Mất quorum | Kiểm tra trạng thái leader/follower và khả năng truy cập peer |

Khi điều tra, hãy phân biệt lỗi kết nối client với lỗi quorum. Client có thể mở TCP đến một server nhưng ensemble vẫn mất quorum và không thể xử lý thay đổi registry.

## 13. Quy trình triển khai mẫu

Một quy trình triển khai ba node có thể thực hiện như sau:

1. Chuẩn bị ba host/container có DNS ổn định và failure domain phù hợp.
2. Mở client port cho ứng dụng; mở peer/election port giữa các ZooKeeper server.
3. Cài cùng phiên bản ZooKeeper tương thích trên các node.
4. Tạo zoo.cfg với cùng danh sách server.X và tham số quorum.
5. Tạo dataDir riêng và file myid đúng ID trên từng node.
6. Khởi động các server và xác nhận một leader cùng các follower.
7. Kiểm tra client port bằng ZooKeeper CLI và xác minh quorum bằng trạng thái server.
8. Tạo chroot path nếu cần.
9. Cấu hình spring.cloud.zookeeper.connect-string chứa nhiều client endpoint.
10. Khởi động service Spring Cloud, xác nhận znode đăng ký và thử dừng một node để kiểm tra khả năng phục hồi.

~~~mermaid
flowchart TD
    A[Chuẩn bị host, DNS và firewall] --> B[Cấu hình zoo.cfg giống nhau]
    B --> C[Tạo dataDir và myid riêng]
    C --> D[Khởi động ensemble]
    D --> E{Có leader và quorum?}
    E -->|Không| F[Kiểm tra peer, election, DNS và myid]
    F --> D
    E -->|Có| G[Tạo chroot nếu cần]
    G --> H[Cấu hình Spring connect-string]
    H --> I[Khởi động service và xác minh znode]
~~~

## 14. Tổng kết

Một ZooKeeper ensemble production thường có 3 hoặc 5 server để duy trì quorum khi một hoặc nhiều node gặp sự cố. Các server dùng cùng danh sách server.X, mỗi node có myid và dataDir riêng, đồng thời giao tiếp qua peer port và election port. Ứng dụng kết nối qua client port.

Connect-string là danh sách nhiều host:clientPort, có thể kèm chroot path để tách namespace logic. Spring Cloud Zookeeper cấu hình danh sách này qua spring.cloud.zookeeper.connect-string; starter discovery sử dụng ensemble để đăng ký và tra cứu service. Muốn hệ thống hoạt động tin cậy, cần xác minh DNS, cổng mạng, quorum, session, chroot, ACL và khả năng reconnect thay vì chỉ kiểm tra một TCP connection thành công.
