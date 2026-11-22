# Phân biệt lưu trữ bền vững với cache, bản sao và bản sao lưu

Trong mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**, người học tìm hiểu toàn bộ vòng đời lưu trữ dữ liệu của ứng dụng Java: chọn mô hình dữ liệu, thiết kế lược đồ, truy vấn và chỉ mục, bảo vệ giao dịch, xử lý cô lập và cập nhật đồng thời, ứng phó lỗi kết nối, tiến hóa schema, bảo mật, sao lưu và cải thiện hiệu năng. Trước khi chọn công nghệ, cần phân biệt bốn vai trò thường xuất hiện trong kiến trúc: **lưu trữ bền vững (durable storage), cache, bản sao đang phục vụ hệ thống (replica) và bản sao lưu phục hồi (backup)**.

Chúng đều có thể chứa những giá trị nhìn giống nhau, nhưng giải quyết các vấn đề khác nhau. Nhầm lẫn vai trò có thể dẫn đến mất đơn hàng khi cache hết hạn, đọc dữ liệu cũ từ replica, hoặc không khôi phục được sau khi một lệnh xóa nhầm đã được đồng bộ tới mọi máy.

Sau bài này, người học có thể:

- Giải thích “dữ liệu bền vững” dưới một phạm vi sự cố được xác định, và vì sao ghi thành công chưa tự động có nghĩa là an toàn trước mọi thảm họa.
- Chọn đúng nơi lưu dữ liệu gốc, cache, replica và backup dựa trên mục đích, quyền ghi, mức chấp nhận trễ và khả năng phục hồi.
- Phân tích các tình huống crash, mất máy, xóa nhầm, hỏng dữ liệu, lỗi mạng và failover.
- Thiết kế đường đọc/ghi trong Java, đặt yêu cầu về RPO/RTO và xác minh có thể phục hồi.

## 1. Lưu trữ bền vững thực sự cam kết điều gì?

**Durability (tính bền vững)** là thuộc tính cho biết một thay đổi đã được hệ thống xác nhận hoàn tất có thể tồn tại sau những loại sự cố đã được dự liệu. Đây là chữ **D** trong ACID của giao dịch cơ sở dữ liệu. Ví dụ: khi database xác nhận một giao dịch chuyển trạng thái đơn hàng đã `COMMIT`, ứng dụng kỳ vọng bản ghi vẫn còn sau khi tiến trình database khởi động lại.

Tuy nhiên, phải hỏi **“bền vững trước sự cố nào?”**:

| Sự cố | Cần cơ chế gì để giữ hoặc phục hồi dữ liệu? |
| --- | --- |
| Tiến trình Java bị dừng đột ngột | Lưu trạng thái quan trọng ở hệ lưu trữ độc lập với bộ nhớ tiến trình |
| Tiến trình database crash | Nhật ký ghi trước (WAL) hoặc cơ chế journal tương đương, quy trình recovery của database |
| Máy chủ mất nguồn | Ghi xuống thiết bị lưu trữ theo cam kết durability; cấu hình database và thiết bị phải phù hợp |
| Ổ đĩa / máy chủ hỏng hoàn toàn | Dữ liệu dự phòng trên phần cứng hoặc vị trí khác; có thể kết hợp replication và backup |
| Một vùng triển khai mất kết nối | Kiến trúc nhiều vùng, cơ chế failover và quy tắc chọn bản ghi có thẩm quyền |
| Xóa nhầm hoặc phần mềm ghi dữ liệu sai | Backup với lịch sử phục hồi, point-in-time recovery hoặc cơ chế lưu phiên bản/kiểm toán |
| Mã độc sửa hoặc mã hóa cả hệ thống | Backup cách ly, hạn chế quyền ghi/xóa, bản sao bất biến và quy trình phục hồi đã thử nghiệm |

**Một giao dịch commit thành công không bảo đảm dữ liệu sống sót sau mọi lỗi vật lý hoặc thao tác phá hủy.** Cam kết thực tế tùy vào cơ sở dữ liệu, cấu hình đồng bộ nhật ký xuống đĩa, thiết bị lưu trữ, số bản sao, quy trình failover và phương án backup.

### 1.1. Ghi vào bộ nhớ, ghi xuống đĩa và commit

Trong một database giao dịch, đường đi thường có dạng:

1. Ứng dụng Java gửi lệnh SQL trong giao dịch.
2. Database kiểm tra ràng buộc và chuẩn bị thay đổi.
3. Database ghi thông tin cần để khôi phục thay đổi vào WAL/journal theo cấu hình.
4. Database xác nhận `COMMIT` khi đạt điều kiện commit đã cấu hình; các trang dữ liệu có thể được ghi xuống tệp dữ liệu sau đó.
5. Nếu tiến trình crash, cơ chế recovery dùng nhật ký để tái dựng trạng thái giao dịch đã commit.

Không phải mọi hệ quản trị đều thực hiện các bước giống hệt nhau. Chẳng hạn, cấu hình giảm yêu cầu đồng bộ xuống thiết bị có thể tăng tốc độ ghi nhưng tăng rủi ro mất giao dịch gần thời điểm crash. Việc `write()` vào một file thành công hoặc một đối tượng còn nằm trong `HashMap` của JVM **không tương đương** với một commit bền vững. Dữ liệu đã nằm trên đĩa cũng không tự động an toàn trước hỏng thiết bị hoặc xóa nhầm.

Đồng thời, **bền vững** không đồng nghĩa với **luôn khả dụng**: một máy có thể còn nguyên dữ liệu nhưng tạm thời không phục vụ truy vấn được. Nó cũng không đồng nghĩa với **nhất quán nghiệp vụ**: một giao dịch có thể được lưu bền vững nhưng chứa trạng thái sai nếu quy tắc kiểm tra bị lỗi.

## 2. Bốn vai trò lưu trữ nhìn từ ứng dụng

| Tiêu chí | Lưu trữ bền vững có thẩm quyền | Cache | Replica | Backup |
| --- | --- | --- | --- | --- |
| Mục đích chính | Ghi nhận và bảo toàn trạng thái nghiệp vụ | Tăng tốc độ truy cập, giảm tải nguồn | Mở rộng năng lực đọc hoặc hỗ trợ khả dụng/failover | Khôi phục sau mất mát, hỏng hoặc thay đổi sai |
| Dữ liệu đi vào | Giao dịch/command được xác thực | Sao chép từ nguồn hoặc tính toán lại | Đồng bộ thay đổi từ nguồn đang ghi | Chụp/lưu phiên bản dữ liệu tại các mốc phục hồi |
| Quyền quyết định giá trị đúng | Có, trong phạm vi sở hữu | Thường không | Thường không khi đang là follower; có thể được thăng cấp khi failover | Không dùng để xử lý giao dịch trực tuyến |
| Độ mới | Theo trạng thái commit đã được ghi nhận | Có thể cũ do TTL hoặc lỗi vô hiệu hóa | Có thể trễ nếu replication bất đồng bộ | Cố ý giữ trạng thái ở quá khứ |
| Mất riêng thành phần này | Có thể mất trạng thái nghiệp vụ nếu không có bản dự phòng/khôi phục | Thường tái tạo được từ nguồn | Có thể dựng lại sau khi nguồn còn hoạt động | Mất khả năng khôi phục những thời điểm chỉ backup đó giữ |
| Cách sử dụng điển hình | Database giao dịch, durable log theo thiết kế | Bộ nhớ ứng dụng, Redis, CDN | Database read replica/follower | Full/incremental backup, snapshot nhất quán, lưu trữ WAL |

Đây là **vai trò kiến trúc**, không phải nhãn gắn cứng với sản phẩm. Redis có thể được cấu hình để lưu bền vững và thậm chí làm nguồn chính trong một thiết kế phù hợp. Một replica có thể ghi dữ liệu xuống đĩa bền vững. Một snapshot có thể dùng để tạo backup. Điều quyết định là **hệ thống sử dụng thành phần đó để làm gì, ai được ghi và có quy trình khôi phục hay không**.

### 2.1. “Bản sao” không chỉ có một nghĩa

Trong giao tiếp kỹ thuật, từ “bản sao” dễ gây nhầm:

- **Replica:** một bản sao *đang tham gia hệ thống hoạt động*, nhận thay đổi từ nguồn nhằm phục vụ đọc hoặc hỗ trợ chuyển đổi khi máy chính gặp lỗi.
- **Backup copy:** một bản sao được lưu *để phục hồi*, thường có mốc thời gian, lịch sử phiên bản, retention và cách ly khỏi lỗi thao tác trên nguồn.
- **Read model/materialized view:** dạng dữ liệu đã biến đổi để hiển thị, tìm kiếm hoặc báo cáo; có thể tái dựng từ nguồn hoặc log sự kiện.
- **Archive:** dữ liệu cũ được lưu theo chính sách lưu trữ dài hạn, chi phí thấp hoặc kiểm toán; không mặc nhiên đáp ứng khả năng khôi phục hệ thống trong thời gian ngắn.

Tách rõ các thuật ngữ giúp tránh yêu cầu sai: “có ba replica nên không cần backup”, hoặc “đã sao lưu mỗi đêm nên truy vấn đọc sẽ nhanh hơn”.

## 3. Ví dụ kiến trúc cho hệ thống đặt hàng Java

Giả sử một nền tảng thương mại điện tử nhận hàng nghìn lượt xem sản phẩm và nhiều đơn hàng mỗi ngày. Hệ thống có thể dùng:

- **Database giao dịch:** lưu đơn hàng, tổng tiền và trạng thái thanh toán có thẩm quyền, với transaction và ràng buộc dữ liệu.
- **Cache:** giữ thông tin trang sản phẩm và một số bản tóm tắt đơn hàng để giảm thời gian đọc.
- **Read replica:** phục vụ truy vấn thống kê hoặc lịch sử ít nhạy với độ trễ đồng bộ.
- **Backup:** lưu các điểm phục hồi trên kho lưu trữ cách ly, kết hợp nhật ký giao dịch nếu cần khôi phục tới thời điểm cụ thể.

~~~mermaid
flowchart TB
    A["Java API / ứng dụng"] -->|"Lệnh ghi, đọc cần dữ liệu mới nhất"| P[("Database chính")]
    A -->|"Đọc nhanh"| C[("Cache")]
    C -. "Cache miss / hết hạn" .-> P
    P -->|"Đồng bộ thay đổi"| R[("Read replica")]
    A -->|"Báo cáo chấp nhận trễ"| R
    P -->|"Backup nhất quán + WAL"| B[("Kho backup tách biệt")]
    B -. "Khôi phục khi sự cố" .-> X[("Môi trường phục hồi")]
~~~

Sơ đồ chỉ thể hiện vai trò: trên thực tế, đường cache miss thường do mã Java chủ động truy vấn database rồi ghi lại cache; cache không nhất thiết tự liên lạc với database. Bản replica có thể được thăng cấp khi failover, nhưng phải có cơ chế quyết định thành viên nào được quyền ghi để tránh **split-brain** (hai máy cùng cho rằng mình là primary).

**Nguyên tắc luồng ghi:** đơn hàng được ghi vào database có thẩm quyền và chỉ trả thành công sau điều kiện commit mà ứng dụng đã lựa chọn. Cache và replica nhận dữ liệu để hỗ trợ đọc hoặc sẵn sàng phục vụ; backup lưu các trạng thái có thể phục hồi. Chúng không thay thế đường ghi giao dịch chỉ vì có sẵn dữ liệu tương tự.

## 4. Cache: tối ưu tốc độ, chấp nhận tái tạo và dữ liệu trễ

Cache thường chứa kết quả truy vấn hoặc tính toán đắt tiền. Cache có thể mất nội dung do restart, eviction, TTL hết hạn hoặc thiếu bộ nhớ, nhưng hệ thống vẫn phải có cách lấy lại dữ liệu quan trọng từ nguồn bền vững.

### 4.1. Ba chiến lược phổ biến

| Chiến lược | Cách hoạt động | Ưu điểm | Rủi ro cần xử lý |
| --- | --- | --- | --- |
| **Cache-aside** | Ứng dụng đọc cache; khi miss thì đọc nguồn và ghi cache | Đơn giản, không cache dữ liệu ít được dùng | Dữ liệu cũ, race condition khi làm mới, cache stampede |
| **Write-through** | Đường ghi cập nhật nguồn và cache theo chính sách hệ thống | Cache có thể gần với trạng thái vừa ghi | Thất bại từng phần, chi phí ghi và cần xác định điều kiện hoàn tất |
| **Write-behind/write-back** | Ghi cache trước, đẩy xuống nguồn bền vững sau | Giảm độ trễ ghi trong một số workload | Có thể mất cập nhật chưa flush; chỉ phù hợp khi rủi ro được chấp nhận và có cơ chế bền vững bổ sung |

Với thông tin đơn hàng hoặc thanh toán, **không nên trả lời rằng đơn đã được lưu bền vững chỉ vì dữ liệu đã vào cache**. Nếu ứng dụng dùng write-behind, phải có thiết kế hàng đợi/nhật ký bền vững, retry, thứ tự ghi và xử lý trùng lặp tương ứng với cam kết nghiệp vụ.

### 4.2. Ví dụ đọc cache-aside trong Java

Ví dụ tối giản sau giả định `OrderRepository` đọc từ nguồn có thẩm quyền còn `OrderCache` lưu bản tóm tắt tạm thời. API trả `Optional.empty()` khi bản ghi không tồn tại; `Duration` là thời hạn sử dụng cache do ứng dụng quy định.

~~~java
import java.sql.SQLException;
import java.time.Duration;
import java.util.Optional;

record OrderView(String id, String status, long version) {}

interface OrderRepository {
    Optional<OrderView> findById(String orderId) throws SQLException;
}

interface OrderCache {
    Optional<OrderView> get(String orderId);
    void put(String orderId, OrderView order, Duration ttl);
    void evict(String orderId);
}

public final class OrderQueryService {
    private final OrderRepository repository;
    private final OrderCache cache;

    public OrderQueryService(OrderRepository repository, OrderCache cache) {
        this.repository = repository;
        this.cache = cache;
    }

    public Optional<OrderView> findById(String orderId) throws SQLException {
        Optional<OrderView> cached = cache.get(orderId);
        if (cached.isPresent()) {
            return cached;
        }

        Optional<OrderView> current = repository.findById(orderId);
        current.ifPresent(order ->
            cache.put(orderId, order, Duration.ofSeconds(30))
        );
        return current;
    }
}
~~~

Đây là ví dụ minh họa **vai trò đọc**, chưa phải triển khai production: cần kiểm soát độ trễ chấp nhận được, timeout, lỗi cache, thông tin nhạy cảm, race condition và monitoring. Khi cache không truy cập được, ứng dụng có thể bỏ qua cache và đọc từ database nếu chính sách vận hành cho phép. Khi nghiệp vụ yêu cầu kết quả vừa commit, hãy đọc đường có bảo đảm độ mới phù hợp thay vì mặc định tin cache.

### 4.3. Vô hiệu hóa cache vẫn có thể thất bại

Giả sử ứng dụng thực hiện:

1. Commit trạng thái đơn hàng mới vào database.
2. Gọi `cache.evict(orderId)`.
3. Trả kết quả cho người dùng.

Nếu bước 1 đã thành công nhưng bước 2 thất bại, cache có thể tiếp tục chứa trạng thái cũ. Đặt TTL giới hạn thời gian dùng bản cũ, nhưng **TTL không tự bảo đảm đọc được dữ liệu mới ngay sau ghi**. Với yêu cầu chặt chẽ hơn, có thể dùng outbox hoặc luồng thay đổi đáng tin cậy để chuyển sự kiện vô hiệu hóa, kiểm tra `version` của bản ghi, hoặc đọc trực tiếp primary trong những luồng nhạy cảm.

Thậm chí khi lệnh evict thành công, một truy vấn cache miss chạy song song có thể lấy giá trị cũ rồi ghi trở lại cache *sau* khi evict. Nếu hệ thống đòi hỏi độ mới cao, hãy thiết kế thêm quy tắc phiên bản, tuần tự hóa hoặc bảo đảm nhất quán thích hợp. Cache-aside không mặc nhiên cung cấp strong consistency.

## 5. Replica: mở rộng đọc và hỗ trợ khả dụng

**Replication** sao chép thay đổi giữa các nút lưu trữ để hệ thống phân tải và có thêm lựa chọn khi một nút gặp sự cố. Ứng dụng Java có thể dùng một `DataSource` cho thao tác ghi và một `DataSource` cho một số truy vấn đọc ít đòi hỏi dữ liệu mới nhất. Nhưng cần xác định **mức trễ sao chép** và quy tắc khi primary hỏng.

### 5.1. Đồng bộ và bất đồng bộ

- **Bất đồng bộ (asynchronous):** primary có thể báo commit trước khi replica nhận đầy đủ thay đổi. Đổi lại độ trễ ghi thấp hơn trong nhiều cấu hình, nhưng replica có thể bị trễ và có nguy cơ chưa nhận các commit cuối cùng nếu primary mất hoàn toàn.
- **Đồng bộ (synchronous):** commit chờ xác nhận từ một hoặc nhiều thành viên theo chính sách cấu hình. Có thể giảm cửa sổ mất dữ liệu, nhưng tăng độ trễ và có thể giảm khả dụng khi thành viên cần thiết không phản hồi. **Xác nhận từ replica không luôn đồng nghĩa với việc đã flush bền vững trên mọi thiết bị**; phải kiểm tra semantics của hệ thống cụ thể.

Ví dụ, khách hàng vừa thanh toán và chuyển về trang đơn hàng. Nếu trang này đọc một replica bất đồng bộ còn trễ hai giây, người dùng có thể vẫn nhìn thấy “chờ thanh toán”. Khi cần **read-your-writes**, có thể đọc primary sau thao tác ghi, sử dụng token/vị trí replication để chờ replica bắt kịp, hoặc áp dụng cơ chế nhất quán mà nền tảng cung cấp.

### 5.2. Failover không biến replica thành backup

Khi primary mất, hệ thống có thể chọn một replica đủ điều kiện để thăng cấp. Quy trình phải xác định bản nào mới nhất, chặn primary cũ tiếp tục nhận ghi, đổi đường kết nối của ứng dụng và kiểm tra dữ liệu sau khi chuyển. Nếu replica chưa nhận hết commit, việc thăng cấp có thể làm mất những cập nhật vừa được primary xác nhận.

Replica thường **nhận cả thao tác sai hợp lệ về mặt kỹ thuật**. Nếu quản trị viên vô tình chạy `DELETE FROM orders` rồi commit, thay đổi đó cũng có thể được sao chép tới mọi follower. Vì vậy, replica không tạo ra lịch sử độc lập để quay lại trước thời điểm xóa.

## 6. Backup: bảo vệ khả năng quay về trạng thái đã biết

**Backup** là dữ liệu và thông tin hỗ trợ khôi phục được lưu theo chính sách thời gian, phạm vi và quyền truy cập. Một bản sao chỉ trở thành giải pháp backup hữu dụng khi có thể **phục hồi thành hệ thống nhất quán** trong điều kiện và thời gian mà doanh nghiệp chấp nhận.

Các hình thức thường gặp:

| Hình thức | Nội dung | Lưu ý |
| --- | --- | --- |
| **Full backup** | Toàn bộ dữ liệu trong phạm vi sao lưu tại một điểm nhất quán | Kích thước lớn; thường là nền để phục hồi |
| **Incremental backup** | Phần thay đổi kể từ mốc backup đã định (thường là lần gần nhất theo chuỗi) | Phục hồi phụ thuộc chuỗi bản cần thiết |
| **Differential backup** | Phần thay đổi kể từ full backup nền | Có thể đơn giản hóa phục hồi hơn chuỗi nhiều incremental, đổi lại dung lượng |
| **Storage snapshot** | Ảnh chụp trạng thái lưu trữ tại một thời điểm | Cần bảo đảm nhất quán ở cấp database; snapshot cùng miền lỗi không đủ cách ly |
| **WAL/binlog archiving** | Lưu nhật ký thay đổi theo thứ tự để phục hồi tiếp sau backup nền | Cần bảo toàn đủ chuỗi log, cấu hình, mốc thời gian và kiểm chứng khôi phục |

**Point-in-time recovery (PITR)** là khả năng khôi phục tới một thời điểm xác định, chẳng hạn ngay trước một lệnh xóa sai. Thông thường cần một backup nền nhất quán **và** chuỗi log đầy đủ tới mốc mong muốn. Tên công nghệ và chi tiết thực hiện khác nhau giữa PostgreSQL, MySQL, SQL Server và các hệ khác.

Đừng chỉ sao chép các file dữ liệu đang mở của database và cho rằng bản sao đó dùng được. Sao chép thiếu file, sai thứ tự hoặc không bảo đảm snapshot nhất quán có thể dẫn đến bộ dữ liệu không phục hồi được. Nên dùng cơ chế backup được hệ quản trị hỗ trợ, kèm cấu hình cần thiết và phương án bảo vệ khóa mã hóa.

### 6.1. RPO và RTO: hai yêu cầu phải thiết kế từ đầu

**RPO (Recovery Point Objective)** là khoảng mất dữ liệu tối đa chấp nhận được nếu cần phục hồi sau sự cố. **RTO (Recovery Time Objective)** là khoảng thời gian mục tiêu để khôi phục dịch vụ.

Giả sử hệ thống có full backup lúc 02:00 hằng ngày, không giữ WAL để khôi phục tiếp. Nếu database chính và mọi replica cùng mất vào 17:00, điểm phục hồi gần nhất có thể là 02:00: hệ thống có nguy cơ mất khoảng **15 giờ** cập nhật. Điều đó không đáp ứng RPO 15 phút, dù thao tác sao lưu đã báo “thành công”. Việc tăng tần suất backup hoặc lưu WAL gần liên tục có thể giảm mức mất dữ liệu **nếu các bản đó thực sự được chuyển tới nơi an toàn và khôi phục được**.

Nếu tại 17:00 hệ thống có thể khôi phục tới 16:55, mất dữ liệu trong trường hợp đó là 5 phút. Nhưng nếu tải dữ liệu, phục hồi WAL, kiểm tra tính toàn vẹn và chuyển lưu lượng mất 4 giờ thì RTO thực tế vẫn khoảng 4 giờ. Hai mục tiêu phải đo riêng.

### 6.2. Backup đáng tin cậy cần điều kiện nào?

1. **Có lịch sử:** lưu nhiều điểm phục hồi để quay lại trước lúc lỗi logic hoặc dữ liệu bị hỏng phát sinh.
2. **Có cách ly:** backup nằm ngoài miền lỗi chính, hạn chế tài khoản vận hành có quyền xóa, dùng bản bất biến/không thể sửa trong thời gian lưu khi phù hợp.
3. **Có bảo vệ:** mã hóa, phân quyền tối thiểu, kiểm soát truy cập đến dữ liệu nhạy cảm và khóa giải mã.
4. **Có tính nhất quán:** snapshot, bản full và chuỗi log tạo thành một trạng thái có thể mở và kiểm tra.
5. **Có kiểm chứng:** định kỳ restore vào môi trường tách biệt, chạy kiểm tra dữ liệu và chức năng quan trọng, ghi lại RPO/RTO đo được.
6. **Có quy trình:** chỉ rõ người chịu trách nhiệm, phiên bản schema, cấu hình ứng dụng, DNS/kết nối và các bước đưa dịch vụ hoạt động lại.

**Không nên xem “backup job thành công” là bằng chứng đủ.** Một bản backup thiếu khóa mã hóa, thiếu WAL, chỉ nằm trên cùng ổ đĩa hoặc chưa từng restore thử có thể thất bại khi thật sự cần.

## 7. Chọn cơ chế theo tình huống hỏng

| Tình huống | Cache | Replica | Backup | Quyết định chính |
| --- | --- | --- | --- | --- |
| Cache hết TTL hoặc bị restart | Tự mất bản tạm | Thường không liên quan | Không cần restore | Đọc lại nguồn chuẩn và nạp cache |
| Java API crash khi giao dịch đã commit | Tạo lại dữ liệu đọc từ nguồn | Có thể phục vụ đọc | Thường không cần | Xác định giao dịch đã commit chưa trước khi retry |
| Primary ngừng phục vụ nhưng dữ liệu trên replica còn đầy đủ | Không cứu dữ liệu gốc | Có thể failover | Là phương án dự phòng khác | Chọn và thăng cấp bản có thẩm quyền, tránh split-brain |
| Primary mất khi replica còn trễ | Không bảo vệ cập nhật mới | Có thể thiếu commit gần nhất | Có thể khôi phục thêm tùy log/backup | Đánh giá chính sách commit, mất dữ liệu và đối soát |
| `DELETE` nhầm đã đồng bộ sang replica | Có thể còn dữ liệu cũ nhưng không đáng tin | Thường cũng bị xóa | Có thể quay về trước khi xóa | PITR, đối soát và xử lý những ghi phát sinh sau mốc khôi phục |
| Database bị mã độc phá hủy | Có thể cùng bị ảnh hưởng | Có thể cùng bị ảnh hưởng | Hữu ích nếu tách biệt và chống xóa/sửa | Khôi phục từ bản an toàn và xử lý nguyên nhân xâm nhập |
| Mô hình đọc báo cáo sai | Có thể xóa để tạo lại | Không giải quyết logic biến đổi | Dữ liệu gốc/nhật ký giúp phục dựng | Sửa logic và tái dựng mô hình đọc |

Không phải sự cố nào cũng cần chạy quy trình khôi phục toàn bộ hệ thống. Cần chọn **cách xử lý nhỏ nhất đáp ứng tính đúng đắn**: cache miss thường chỉ cần đọc lại; mất primary có thể failover; xóa nhầm cần mốc lịch sử phục hồi; lỗi logic có thể cần sửa chương trình và tính lại dữ liệu.

## 8. Đường ghi và đường đọc trong Java: đặt đúng sự bảo đảm

Giả sử người dùng thanh toán thành công và Order phải ghi trạng thái mới. Đường ghi nên là:

1. Nhận lệnh với định danh giao dịch/request ID để chống xử lý trùng.
2. Kiểm tra quy tắc nghiệp vụ và trạng thái hiện tại tại nguồn có thẩm quyền.
3. Trong một transaction, cập nhật bản ghi, ghi dấu vết cần thiết và thông tin outbox nếu có phát sự kiện.
4. Commit với chính sách durability đã chọn; chỉ báo thành công theo điều kiện nghiệp vụ tương ứng.
5. Sau commit, thông báo hoặc vô hiệu hóa cache, đồng bộ replica và vận hành backup bằng cơ chế riêng.

Ví dụ SQL **minh họa** hai thay đổi cần commit nguyên tử trong cùng database; câu lệnh giả định các bảng `orders` và `outbox_events` đã tồn tại, `order_id` và `event_id` là khóa duy nhất:

~~~sql
BEGIN;

UPDATE orders
SET payment_status = 'PAID',
    version = version + 1
WHERE order_id = :order_id
  AND payment_status = 'PENDING';

-- Chỉ ghi sự kiện khi đúng một dòng đơn hàng đã được chuyển trạng thái.
INSERT INTO outbox_events(event_id, aggregate_id, event_type, payload)
VALUES (:event_id, :order_id, 'OrderPaid', :event_payload);

COMMIT;
~~~

Trong code thực tế, ứng dụng phải kiểm tra số dòng `UPDATE` trả về là **1** trước khi `INSERT`, và rollback nếu không đúng; cú pháp tham số `:` ở trên là ký hiệu minh họa, JDBC `PreparedStatement` thường dùng dấu `?`. Mục tiêu của outbox là không để tình huống “database đã commit nhưng gửi sự kiện sang cache, message broker hoặc dịch vụ khác thất bại” làm mất luôn ý định đồng bộ. Một tiến trình riêng gửi các event đã commit và xử lý retry; consumer phải chịu được event lặp.

### 8.1. Ví dụ khung giao dịch với JDBC

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class OrderPaymentWriter {
    private final DataSource dataSource;

    public OrderPaymentWriter(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean markPaid(String orderId, String eventId, String payload)
            throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try {
                int updated;
                try (PreparedStatement statement = connection.prepareStatement(
                        "UPDATE orders SET payment_status = 'PAID', "
                      + "version = version + 1 "
                      + "WHERE order_id = ? AND payment_status = 'PENDING'")) {
                    statement.setString(1, orderId);
                    updated = statement.executeUpdate();
                }

                if (updated != 1) {
                    connection.rollback();
                    return false;
                }

                try (PreparedStatement statement = connection.prepareStatement(
                        "INSERT INTO outbox_events "
                      + "(event_id, aggregate_id, event_type, payload) "
                      + "VALUES (?, ?, 'OrderPaid', ?)")) {
                    statement.setString(1, eventId);
                    statement.setString(2, orderId);
                    statement.setString(3, payload);
                    statement.executeUpdate();
                }

                connection.commit();
                return true;
            } catch (SQLException | RuntimeException error) {
                connection.rollback();
                throw error;
            }
        }
    }
}
~~~

Ví dụ minh họa tính nguyên tử giữa bản ghi nghiệp vụ và outbox: lỗi `INSERT` khiến giao dịch rollback, không để trạng thái đơn đã đổi nhưng thiếu thông tin phát sự kiện. Để dùng thật, phải xác thực kết quả thanh toán, quản lý định danh sự kiện, xử lý yêu cầu lặp, giao dịch đã commit nhưng client mất phản hồi, và đảm bảo mã gọi quyết định phù hợp với trạng thái hiện tại. Một lỗi kết nối ngay lúc `COMMIT` có thể khiến client **không biết** giao dịch đã hoàn tất hay chưa; không được kết luận chắc chắn rollback hoặc retry mù một tác động có thể lặp.

Ở đường đọc, lựa chọn phụ thuộc mức nhất quán cần thiết:

| Loại truy vấn | Đường đọc khuyến nghị | Lý do |
| --- | --- | --- |
| Mở trang mô tả sản phẩm ít thay đổi | Cache với TTL/invalidation | Tối ưu thời gian phản hồi, chấp nhận độ trễ nhỏ |
| Kiểm tra trạng thái ngay sau khi thanh toán | Nguồn ghi hoặc đường đọc có bảo đảm read-your-writes | Tránh hiển thị trạng thái cũ từ replica/cache |
| Báo cáo bán hàng theo giờ | Replica hoặc mô hình đọc được xây từ dữ liệu gốc | Giảm tải database giao dịch, có thể chấp nhận trễ |
| Quyết định trừ tồn kho | Ghi có điều kiện trong transaction tại nơi sở hữu tồn kho | Không ra quyết định dựa trên snapshot hoặc cache cũ |
| Khôi phục đơn hàng bị xóa nhầm | Backup/PITR và nhật ký kiểm toán | Cần trạng thái lịch sử trước khi xóa, không phải bản đọc hiện tại |

## 9. Thiết kế phục hồi song hành với hiệu năng và bảo mật

Tối ưu persistence không nên chỉ nhìn độ trễ truy vấn hay tốc độ ghi. Cache có thể giảm tải đọc; chỉ mục giúp truy vấn bền vững nhanh hơn; replica hỗ trợ đọc song song; backup gây tải I/O cần lên lịch và điều phối. Mỗi quyết định ảnh hưởng tới mức nhất quán, chi phí, băng thông, giám sát và khả năng khôi phục.

Khi chọn giải pháp, ghi rõ:

| Câu hỏi | Ví dụ yêu cầu |
| --- | --- |
| Dữ liệu nào không được mất? | Đơn hàng đã xác nhận và kết quả thanh toán |
| Trễ dữ liệu tối đa cho mỗi màn hình là bao nhiêu? | Danh sách tìm kiếm chấp nhận trễ ngắn, màn hình sau thanh toán cần cập nhật ngay |
| Mất dữ liệu tối đa sau thảm họa là bao nhiêu? | RPO xác định theo mức chấp nhận kinh doanh |
| Dịch vụ có thể gián đoạn bao lâu? | RTO bao gồm restore, kiểm tra và chuyển lưu lượng |
| Ai được ghi và ai được xóa? | Tài khoản ứng dụng chỉ có quyền cần thiết; backup tách quyền quản trị |
| Có thể khôi phục tới một thời điểm bất kỳ không? | Dựa trên backup nền nhất quán và chuỗi nhật ký đầy đủ |
| Làm sao biết replication/backup đang hoạt động? | Theo dõi lag, thời điểm backup cuối, lỗi job, lần restore thử gần nhất |

Hai lỗi đáng chú ý khi tiến hóa schema và khôi phục: backup cũ có thể đi cùng phiên bản lược đồ cũ, còn ứng dụng mới có thể không đọc được trực tiếp. Quy trình khôi phục cần bao gồm version của database, migration tương thích và mã ứng dụng tương ứng. Ngoài ra, phục hồi database mà thiếu event/outbox hoặc khóa mã hóa cần thiết có thể khiến toàn hệ thống chưa sẵn sàng, dù các bảng đã xuất hiện.

## 10. Bài tập tình huống

Một ứng dụng Java có database chính, Redis làm cache, một read replica bất đồng bộ và full backup vào 01:00 mỗi ngày. Lúc 14:20, quản trị viên vô tình xóa toàn bộ đơn hàng rồi commit; lệnh xóa nhanh chóng lan đến replica. Cache vẫn hiển thị một số đơn hàng cũ.

Hãy xác định:

1. Có nên lấy các đơn hàng còn xuất hiện trong Redis để coi là dữ liệu chuẩn không? Vì sao?
2. Replica có giúp quay về trạng thái trước lúc xóa không?
3. Nếu chỉ có full backup lúc 01:00, có nguy cơ mất các đơn được tạo sau giờ đó không?
4. Nếu hệ thống còn giữ chuỗi WAL/binlog đầy đủ, có thể khôi phục về mốc 14:19:59 không?
5. Sau khi restore, cần xác minh những gì trước khi mở lại lưu lượng ghi?

**Gợi ý phân tích:**

- Redis có thể còn bản cũ, thiếu bản ghi mới hoặc có dữ liệu đã hết hạn; không đủ căn cứ khẳng định trạng thái nghiệp vụ đầy đủ và đúng.
- Replica thường đã nhận lệnh xóa, nên việc tồn tại thêm một nút không tạo ra điểm quay lại trước lỗi.
- Full backup 01:00 không chứa những commit đến sau đó; nếu không có log bổ sung, mất dữ liệu từ 01:00 đến 14:20 là rủi ro thực tế.
- PITR có thể giúp khôi phục tới mốc trước lỗi **nếu** backup nền và chuỗi log phù hợp đầy đủ, có thể áp dụng đúng mốc, và chính sách khôi phục hỗ trợ thao tác này. Mốc theo thời gian cần xử lý cả múi giờ và thứ tự transaction; đôi khi xác định transaction/LSN an toàn hơn một con số giây.
- Sau restore, kiểm tra toàn vẹn và số lượng bản ghi, giao dịch thanh toán liên quan, outbox/sự kiện, tính tương thích schema, phân quyền, và xử lý các ghi mới phát sinh sau thời điểm phục hồi. Thử trong môi trường cách ly trước khi đưa dữ liệu phục hồi vào phục vụ.

## 11. Checklist áp dụng

Trước khi đưa một hệ thống lưu trữ dữ liệu Java vào vận hành:

- [ ] Biết nguồn có thẩm quyền cho từng loại dữ liệu, và nơi nào được phép ghi.
- [ ] Hiểu rõ database xác nhận `COMMIT` theo chính sách durability nào.
- [ ] Dùng cache cho mục tiêu tăng tốc, có TTL/invalidation, cách xử lý cache miss và cache down.
- [ ] Biết replica đang đồng bộ hay bất đồng bộ, lag được theo dõi và ứng dụng xử lý read-after-write ra sao.
- [ ] Có thiết kế failover, quy tắc tránh hai primary và cách phát hiện giao dịch chưa được sao chép.
- [ ] Backup được cách ly, có phiên bản lịch sử, bảo mật, retention và nhật ký cần cho PITR.
- [ ] RPO/RTO được định nghĩa và đo bằng các lần khôi phục thử thực tế.
- [ ] Đã diễn tập các tình huống xóa nhầm, database mất máy, lỗi kết nối lúc commit và khôi phục schema.
- [ ] Có giám sát độ trễ replication, tỷ lệ cache hit/miss, thời điểm backup và kết quả restore thử.
- [ ] Các quyết định tối ưu hiệu năng không làm thay đổi ngầm cam kết toàn vẹn và phục hồi dữ liệu.

**Ghi nhớ:** *Lưu trữ bền vững* giữ trạng thái được xác nhận trong một phạm vi sự cố nhất định; *cache* làm truy cập nhanh hơn; *replica* giúp đọc hoặc chuyển đổi khi sự cố; *backup* cho phép quay về một trạng thái lịch sử có thể khôi phục. Một hệ thống đáng tin cậy thường cần phối hợp cả bốn, với trách nhiệm, mức nhất quán và cách kiểm chứng riêng cho từng vai trò.
