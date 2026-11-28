# Hazelcast và lưu phiên trên bản đồ dữ liệu phân tán

Spring Session có thể lưu HTTP session trong Hazelcast để nhiều instance Spring cùng truy cập một kho phiên phân tán. Hazelcast cung cấp cấu trúc IMap, một bản đồ key-value phân tán được chia partition giữa các member trong cluster. Mỗi session được nhận diện bằng session ID và được lưu thành một entry trong map; instance xử lý request có thể tìm entry đó dù session được tạo từ instance khác.

Mô hình này phù hợp khi hệ thống đã sử dụng Hazelcast hoặc cần một kho dữ liệu phân tán trong bộ nhớ. Tuy nhiên, session là trạng thái xác thực và trạng thái người dùng, nên cấu hình cluster, backup, thời hạn, serialization, bảo mật mạng và khả năng phục hồi đều phải được thiết kế cẩn thận.

## 1. Hazelcast đóng vai trò gì trong Spring Session?

Trong ứng dụng Servlet, Spring Session thay thế việc giữ HttpSession riêng trong bộ nhớ của từng servlet container bằng một SessionRepository. Với Hazelcast, repository lưu dữ liệu phiên trong một IMap phân tán.

Một request đi qua instance A có thể tạo session và lưu session ID cùng các thuộc tính vào map. Request tiếp theo có thể được load balancer chuyển đến instance B. Instance B dùng cùng Hazelcast cluster và cùng repository để đọc session đó.

Luồng khái quát:

~~~mermaid
flowchart TD
    A["Trình duyệt gửi cookie session ID"] --> B["Instance Spring A hoặc B"]
    B --> C["SessionRepositoryFilter"]
    C --> D["HazelcastIndexedSessionRepository"]
    D --> E["IMap phân tán"]
    E --> F["Partition owner và backup member"]
    F --> E
    E --> D
    D --> C
    C --> G["Controller dùng HttpSession"]
~~~

Các thành phần có trách nhiệm riêng:

- SessionRepositoryFilter nối Servlet API với Spring Session.
- HazelcastIndexedSessionRepository triển khai việc tạo, tìm, lưu và xóa session bằng Hazelcast.
- HazelcastInstance cung cấp kết nối đến member hoặc cluster.
- IMap giữ entry session, phân phối dữ liệu và hỗ trợ backup theo cấu hình.
- Hazelcast cluster xử lý partition, member membership và phục hồi dữ liệu theo topology.

Hazelcast không thay thế cookie. Trình duyệt vẫn gửi session ID qua cookie; Hazelcast lưu dữ liệu phía server. Session ID không nên được lưu trong localStorage hoặc đưa vào URL.

## 2. IMap và cách dữ liệu session được phân phối

IMap<K,V> là distributed map của Hazelcast. Với map session, key thường là session ID và value là dữ liệu session được repository quản lý. Hazelcast chia các entry thành partition; mỗi partition có một member làm owner và có thể có một hoặc nhiều bản sao backup trên member khác.

Khi ứng dụng đọc hoặc ghi một key:

1. Hazelcast xác định partition của key.
2. Request được định tuyến đến member sở hữu partition.
3. Member thực hiện thao tác trên entry.
4. Nếu cấu hình backup, thay đổi được sao chép đến backup member theo cơ chế của Hazelcast.

Điều này cho phép nhiều instance Spring chia sẻ dữ liệu mà không cần sticky session. Sticky routing vẫn có thể được dùng vì lý do hiệu năng, nhưng tính đúng đắn của session không nên phụ thuộc vào việc request luôn quay lại cùng một instance.

Không nhầm IMap với ReplicatedMap. IMap phân phối partition và backup dữ liệu; ReplicatedMap có cách sao chép khác và thường không phải lựa chọn mặc định cho dữ liệu session có thể tăng nhanh. Với Spring Session Hazelcast, dùng repository và cấu trúc map được integration hỗ trợ, không tự thay bằng một map khác chỉ vì tên gọi tương tự.

## 3. Tích hợp Spring Session với Hazelcast

Trong ứng dụng Spring Boot Servlet, thêm dependency Spring Session Hazelcast tương thích với phiên bản Spring Boot/Spring Session đang dùng, cùng Hazelcast client hoặc member library phù hợp với mô hình triển khai.

Ví dụ cấu hình member Hazelcast cùng ứng dụng:

~~~java
import com.hazelcast.config.Config;
import com.hazelcast.config.MapConfig;
import com.hazelcast.core.Hazelcast;
import com.hazelcast.core.HazelcastInstance;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.hazelcast.config.annotation.web.http.EnableHazelcastHttpSession;

@Configuration
@EnableHazelcastHttpSession
class HazelcastSessionConfiguration {

    @Bean
    HazelcastInstance hazelcastInstance() {
        Config config = new Config();
        config.setClusterName("shop-session");

        MapConfig sessions = new MapConfig("spring:session:sessions");
        sessions.setBackupCount(1);
        config.addMapConfig(sessions);

        return Hazelcast.newHazelcastInstance(config);
    }
}
~~~

Đây là cấu hình minh họa cho mô hình embedded member. @EnableHazelcastHttpSession bật tích hợp Spring Session Hazelcast và đăng ký repository theo API của phiên bản tương ứng. Map name mặc định, thuộc tính annotation, package và cách Spring Boot auto-configuration hoạt động có thể thay đổi theo release; hãy xác nhận tài liệu của dependency thực tế. Không tự tạo một SessionRepository thứ hai nếu annotation hoặc auto-configuration đã tạo repository.

Trong môi trường production, ứng dụng thường có thể chạy dưới dạng Hazelcast client để kết nối đến một cluster member độc lập. Khi đó, bean HazelcastInstance phải được tạo bằng client configuration và kết nối đến địa chỉ cluster được quản lý. Không để mọi replica Spring tự tạo cluster độc lập ngoài ý muốn; nếu mỗi instance dùng cluster name, network discovery hoặc namespace khác nhau, chúng sẽ không chia sẻ session.

## 4. Embedded member hay Hazelcast client?

Có hai mô hình triển khai thường gặp:

| Mô hình | Cách hoạt động | Khi cân nhắc |
| --- | --- | --- |
| Embedded member | Mỗi tiến trình ứng dụng Spring cũng là một Hazelcast member trong cluster | Hệ thống nhỏ hoặc muốn ứng dụng vừa xử lý request vừa giữ một phần dữ liệu phân tán |
| Hazelcast client | Ứng dụng Spring kết nối đến Hazelcast cluster chạy độc lập | Muốn tách vòng đời ứng dụng và data grid, quản lý cluster riêng, hoặc triển khai nhiều ứng dụng client |

Embedded member giảm số thành phần cần vận hành nhưng làm tài nguyên heap, CPU và vòng đời Hazelcast gắn với ứng dụng web. Khi scale hoặc rolling restart các replica Spring, membership của Hazelcast cũng thay đổi và có thể phát sinh partition migration.

Client mode tách biệt data grid khỏi web tier. Ứng dụng có thể restart hoặc scale mà không trực tiếp làm thay đổi số member lưu dữ liệu. Đổi lại, cần vận hành cluster riêng, bảo vệ client connection và theo dõi thêm một tầng mạng.

Không có lựa chọn phù hợp cho mọi hệ thống. Cần so sánh số lượng session, tải đọc/ghi, yêu cầu HA, giới hạn bộ nhớ và năng lực vận hành của nhóm.

## 5. Cấu hình map và thời hạn session

Session thường có idle timeout. Khi session không hoạt động trong khoảng thời gian cấu hình, nó không còn hợp lệ. Với Hazelcast, thời hạn có thể được áp dụng thông qua cấu hình Spring Session và cơ chế TTL/expiration của map tùy integration và phiên bản.

Ví dụ cấu hình map có backup và TTL:

~~~java
MapConfig sessions = new MapConfig("spring:session:sessions");
sessions.setBackupCount(1);
sessions.setTimeToLiveSeconds(1800);
config.addMapConfig(sessions);
~~~

Không xem TTL của map và timeout nghiệp vụ của Spring Session là hai khái niệm luôn đồng nhất. Cần xác định integration đang đặt TTL entry như thế nào, có gia hạn khi session được truy cập hay cập nhật không, và liệu map-level TTL có ghi đè thời hạn của từng entry hay không.

Nguyên tắc cấu hình:

- Session timeout của Spring Session phải phản ánh chính sách idle timeout của ứng dụng.
- TTL của map không được ngắn hơn mức khiến session hợp lệ bị xóa sớm.
- Nếu map TTL dài hơn timeout session, repository vẫn phải từ chối session đã hết hạn và cần có cơ chế dọn entry cũ.
- Kiểm thử việc gia hạn session khi request đọc hoặc cập nhật session.
- Không dùng một TTL vô hạn cho dữ liệu phiên nếu không có chính sách dọn rõ ràng.

Với annotation, property hoặc repository API có hỗ trợ timeout, ưu tiên dùng cấu hình chính thức của integration. Nếu đồng thời cấu hình timeout trong annotation, Spring Boot property và MapConfig, hãy xác định thứ tự và hành vi thực tế thay vì giả định một giá trị sẽ tự đồng bộ với các giá trị còn lại.

## 6. Backup và khả năng chịu lỗi

Session có thể chứa trạng thái đăng nhập, nên mất dữ liệu có thể khiến người dùng bị đăng xuất. IMap hỗ trợ backup entry sang member khác. Ví dụ backupCount=1 yêu cầu một backup đồng bộ theo cấu hình map; Hazelcast còn có cấu hình backup bất đồng bộ và các lựa chọn khác tùy phiên bản.

Khi chọn số backup, cân nhắc:

- Một backup giúp chịu lỗi một member trong những điều kiện được Hazelcast hỗ trợ.
- Nhiều backup tăng khả năng chịu lỗi nhưng tiêu thụ thêm bộ nhớ và lưu lượng mạng.
- Không có backup làm giảm chi phí ghi nhưng có thể mất session khi member chứa partition rời cluster.
- Backup không thay thế persistence hoặc backup định kỳ nếu cần phục hồi sau lỗi toàn cluster.

Backup được lưu trên member khác trong cluster, vì vậy các member cần phân bố trên host, zone hoặc rack khác nhau nếu muốn chịu lỗi hạ tầng. Đặt hai member cùng một máy vật lý không bảo vệ được khi máy đó hỏng.

Hiểu rõ sự khác nhau giữa:

- Member failure: một Hazelcast member dừng hoạt động; partition có thể được phục hồi từ backup.
- Network partition: cluster có thể bị chia thành các nhóm không liên lạc được; hành vi phụ thuộc cấu hình split-brain protection và merge policy.
- Cluster-wide outage: toàn bộ member ngừng hoạt động; backup trong cluster không giúp phục hồi nếu không có persistence hoặc bản sao bên ngoài.
- Application instance failure: một web instance dừng; session vẫn có thể tồn tại trên Hazelcast nếu cluster còn khỏe.

Không coi backupCount=1 là bảo đảm tuyệt đối rằng session không bao giờ mất. Cần thử failover thực tế và hiểu consistency, durability cũng như chính sách split-brain của phiên bản Hazelcast.

## 7. Serialization của session

Hazelcast phải chuyển đổi value của map thành dữ liệu có thể lưu và truyền giữa các member. Đối tượng session hoặc các thuộc tính bên trong cần tương thích với serialization mechanism mà Hazelcast/Spring Session đang dùng.

Các lựa chọn serialization của Hazelcast có thể bao gồm Java serialization, IdentifiedDataSerializable, Portable ở các thế hệ cũ, Compact Serialization ở các phiên bản mới hoặc custom serializer. Tên API và khả năng tương thích phụ thuộc phiên bản Hazelcast.

Khi dùng Java serialization, các lớp trong object graph cần triển khai Serializable và nên khai báo serialVersionUID tường minh. Khi dùng serializer riêng, mọi instance phải có cùng serializer registration, type identifier và cấu hình tương thích.

Trong rolling deployment:

1. Phiên bản cũ ghi session object theo định dạng cũ.
2. Phiên bản mới đọc session đó.
3. Phiên bản mới có thể cập nhật và ghi lại dữ liệu.
4. Một request khác có thể được chuyển về replica cũ trong thời gian rollout.

Vì vậy cần kiểm tra cả chiều cũ đọc dữ liệu mới và mới đọc dữ liệu cũ nếu hai phiên bản có thể cùng chạy. Thay đổi tên field, kiểu dữ liệu hoặc serializer có thể khiến dữ liệu cũ không đọc được hoặc mang ý nghĩa sai.

Ưu tiên DTO nhỏ, ổn định. Tránh lưu trực tiếp entity ORM, servlet object, connection, thread, proxy framework hoặc object graph lớn. Không đổi serializer khi session cũ còn hiệu lực mà chưa có kế hoạch migration, hết hạn hoặc chuyển sang namespace mới.

## 8. Chỉ mục và tìm session theo principal

Một số tính năng Spring Session cần tìm session theo tên principal, ví dụ giới hạn số phiên đăng nhập hoặc thu hồi phiên của một người dùng. Hazelcast integration có thể cung cấp repository dạng indexed để hỗ trợ truy vấn theo principal.

Nếu dùng FindByIndexNameSessionRepository, hãy xác nhận repository Hazelcast của phiên bản đang chạy triển khai interface này và cách nó tạo, cập nhật chỉ mục. Không tự giả định mọi Hazelcast repository đều có cùng khả năng index.

Khi ứng dụng tự quản lý thuộc tính principal:

- Dùng một giá trị ổn định, đã chuẩn hóa.
- Không đưa access token, mật khẩu hoặc dữ liệu bí mật vào index.
- Giữ cùng cách chuẩn hóa trên mọi instance.
- Kiểm thử trường hợp đăng nhập, đổi principal, logout và session hết hạn.
- Khi thay đổi cách lập chỉ mục, xử lý session cũ có index theo định dạng trước đó.

Nếu ứng dụng dùng Spring Security, cần xác nhận resolver mặc định có nhận diện principal từ SecurityContext hay không. Thay thế index resolver mà không giữ logic mặc định có thể làm chức năng tìm session theo người dùng ngừng hoạt động.

## 9. Cluster discovery và cấu hình mạng

Các member Hazelcast cần tìm thấy nhau để tham gia cùng cluster. Discovery có thể dựa trên TCP/IP, Kubernetes discovery plugin, cloud discovery hoặc cơ chế được hỗ trợ bởi môi trường triển khai.

Những giá trị cần đồng nhất:

- Cluster name.
- Cấu hình discovery và danh sách địa chỉ hoặc discovery plugin.
- Cấu hình TLS và xác thực member/client.
- Phiên bản Hazelcast và cấu hình serialization.
- Map name và MapConfig của session.
- Các thiết lập partition, backup và split-brain protection.

Không mở multicast hoặc port Hazelcast ra Internet công khai. Member-to-member traffic và client-to-cluster traffic nên nằm trong mạng riêng, được giới hạn bằng firewall/security group và được mã hóa theo yêu cầu hạ tầng.

Nếu dùng Kubernetes, có thể dùng discovery plugin hoặc service discovery phù hợp. Cần bảo đảm service trả về các member Hazelcast thực sự, không phải các pod web không chạy member. Kiểm tra readiness, membership và partition state trước khi cho ứng dụng nhận tải lớn.

## 10. Bảo vệ dữ liệu session trong Hazelcast

Session ID là thông tin nhạy cảm. Người có session ID hợp lệ có thể có khả năng sử dụng phiên của người khác. Hazelcast lưu dữ liệu session phía server, vì vậy cần bảo vệ cả đường truyền lẫn quyền truy cập cluster.

Các biện pháp cần cân nhắc:

- Dùng xác thực Hazelcast client/member và tài khoản riêng cho ứng dụng.
- Giới hạn quyền truy cập map session theo nguyên tắc tối thiểu.
- Bật TLS cho member-to-member và client-to-cluster traffic khi phù hợp.
- Không cho phép ứng dụng không liên quan đọc hoặc ghi map session.
- Không ghi session ID, cookie hoặc toàn bộ session object vào log.
- Bảo vệ backup, persistence store và snapshot vì chúng có thể chứa dữ liệu phiên.
- Dùng cookie HttpOnly, Secure và SameSite phù hợp ở tầng trình duyệt.
- Giữ CSRF protection nếu session cookie dùng để xác thực request.

Không xem cluster name là cơ chế xác thực. Cluster name chỉ giúp phân biệt cluster; nó không thay thế credentials, network isolation hoặc TLS.

## 11. Nhiều ứng dụng và namespace session

Nếu nhiều ứng dụng cùng dùng một Hazelcast cluster, không nên mặc định chúng chia sẻ cùng map session. Dùng map hoặc namespace riêng cho từng ứng dụng để tránh xung đột session ID, cấu hình TTL và kiểu dữ liệu.

Ví dụ:

- shop:session:sessions
- admin:session:sessions
- portal:session:sessions

Tên map thực tế phải khớp với cấu hình của repository. Không tự đổi map name bằng cách tạo một IMap khác nếu repository vẫn dùng map mặc định. Kiểm tra extension point hoặc thuộc tính được integration hỗ trợ ở đúng phiên bản.

Tách map giúp cô lập dữ liệu và chính sách expiration, nhưng không thay thế phân quyền Hazelcast. Ứng dụng chỉ nên truy cập map mà nó cần. Nếu mọi client đều có quyền đọc mọi map, việc đặt tên riêng không tạo ranh giới bảo mật thực sự.

## 12. Kiểm thử tích hợp và failover

Kiểm thử Hazelcast session cần xác nhận repository, cookie và cluster hoạt động cùng nhau. Một bộ kiểm thử nên bao gồm:

1. Tạo session qua HTTP request ở instance A.
2. Lưu cookie nhận được và gửi request tiếp theo đến instance B.
3. Xác nhận B đọc được thuộc tính do A ghi.
4. Cập nhật session ở B và xác nhận A đọc được thay đổi sau đó.
5. Kiểm tra idle timeout và expiration.
6. Kiểm tra logout làm session không còn hợp lệ.
7. Dừng một member và xác nhận backup/partition recovery theo cấu hình.
8. Khởi động lại một web instance và xác nhận session vẫn tồn tại khi Hazelcast cluster còn khỏe.
9. Kiểm tra serialization giữa hai phiên bản ứng dụng nếu có rolling deployment.
10. Kiểm tra hành vi khi cluster mất quorum hoặc có network partition theo chính sách đã chọn.

Có thể dùng Hazelcast Testcontainers hoặc một cluster test riêng phù hợp với phiên bản. Mock SessionRepository chỉ kiểm tra logic controller; nó không chứng minh partition, backup, discovery, serialization hoặc failover hoạt động.

Không chạy bài test xóa member hoặc tạo network partition trên cluster production. Dùng môi trường staging có topology gần với production và dữ liệu giả.

## 13. Giám sát và vận hành

Theo dõi các chỉ số của cả Spring Session và Hazelcast:

- Số lượng session và kích thước map.
- Heap usage, native memory và garbage collection của member.
- Partition count, partition migration và backup synchronization.
- Member count, cluster state và client connection.
- Độ trễ thao tác map, timeout, retry và lỗi serialization.
- Số lần session không tìm thấy hoặc người dùng phải xác thực lại bất thường.
- Số entry hết hạn và tốc độ dọn dữ liệu.
- Network throughput giữa member và client.

Nếu member rời cluster, Hazelcast có thể thực hiện partition migration. Trong thời gian đó, độ trễ map có thể tăng. Cần đặt ngưỡng cảnh báo cho cluster state, member count, migration backlog và memory pressure.

Không để map session tăng không giới hạn. Chọn timeout phù hợp, backup count hợp lý, theo dõi số entry và cấu hình capacity/eviction theo yêu cầu. Eviction không được thiết kế tùy tiện: xóa entry session trước timeout có thể khiến người dùng bị đăng xuất bất ngờ. Nếu dùng eviction, phải hiểu rõ sự khác biệt giữa eviction do áp lực bộ nhớ và expiration theo TTL.

## 14. Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Mỗi instance có session riêng | Các ứng dụng không kết nối cùng Hazelcast cluster hoặc map | Kiểm tra cluster name, discovery, endpoint và map name |
| Session biến mất sau restart một member | Không có backup phù hợp hoặc topology không chịu được lỗi đó | Kiểm tra backup count, phân bố member và persistence |
| Session hết hạn sớm | TTL map ngắn hơn chính sách Spring Session | Đồng bộ timeout và kiểm thử gia hạn |
| Session không hết hạn như mong đợi | TTL hoặc cleanup không được áp dụng theo cấu hình | Kiểm tra repository, map config và thời gian entry |
| Lỗi serialization sau deploy | Các phiên bản dùng class hoặc serializer không tương thích | Đồng bộ serializer, kiểm thử fixture và triển khai theo giai đoạn |
| Không tìm được session theo username | Index resolver hoặc indexed repository không được cấu hình đúng | Kiểm tra repository capability và principal index |
| Cluster tạo nhiều nhóm riêng | Discovery, cluster name hoặc network bị cấu hình sai | Kiểm tra membership và split-brain protection |
| Độ trễ tăng khi scale | Partition migration, backup hoặc network contention | Theo dõi migration, heap, network và tải map |

Khi chẩn đoán, kiểm tra session cookie trước, sau đó xác nhận request đã đến instance nào, repository đang dùng map nào và Hazelcast member/client có cùng cluster hay không. Đừng kết luận session mất chỉ từ log của một instance.

## 15. Quy trình triển khai

- [ ] Chọn embedded member hay Hazelcast client dựa trên mô hình vận hành.
- [ ] Dùng phiên bản Hazelcast tương thích với Spring Session integration.
- [ ] Cấu hình đúng HazelcastInstance và bật repository Hazelcast.
- [ ] Đồng nhất cluster name, discovery, map name và serialization giữa các instance.
- [ ] Cấu hình idle timeout và map TTL không xung đột.
- [ ] Chọn backup count và phân bố member theo yêu cầu HA.
- [ ] Bảo vệ client/member bằng authentication, TLS và network policy.
- [ ] Kiểm thử create/read/update/delete và cookie qua nhiều instance.
- [ ] Kiểm thử member failure, partition migration và serialization khi rolling deployment.
- [ ] Giám sát map size, memory, cluster state, latency và expiration.

Hazelcast cho phép Spring Session lưu phiên trong IMap phân tán để nhiều instance ứng dụng cùng truy cập. Lợi ích chỉ đạt được khi các instance thực sự dùng chung cluster, map, serializer và chính sách timeout. Thiết kế backup, discovery, bảo mật và kiểm thử failover quyết định khả năng vận hành ổn định; vì session gắn với xác thực người dùng, không nên đánh đổi tính đúng đắn của phiên chỉ để giảm chi phí bộ nhớ hoặc thao tác ghi.
