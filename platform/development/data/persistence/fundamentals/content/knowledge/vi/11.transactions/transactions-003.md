# Phân biệt nhất quán của bất biến với nhất quán giữa các bản sao

## 1. Vì sao cần phân biệt?

Trong ứng dụng có dữ liệu bền vững, từ **nhất quán** (consistency) thường xuất hiện ở hai câu hỏi khác nhau:

1. **Dữ liệu đã ghi có còn thỏa quy tắc nghiệp vụ không?** Ví dụ: tồn kho không âm, một ghế không được bán cho hai người, tổng tiền chuyển khỏi tài khoản phải bằng tổng tiền chuyển vào tài khoản khác.
2. **Các nơi đang giữ hoặc đọc dữ liệu có nhìn thấy cùng một trạng thái không?** Ví dụ: sau khi đơn hàng đã xác nhận, bản sao phục vụ trang sản phẩm vẫn hiển thị còn một sản phẩm trong vài trăm mili giây.

Câu hỏi thứ nhất nói về **nhất quán của bất biến** (invariant consistency). Câu hỏi thứ hai nói về **nhất quán giữa các bản sao** (replica consistency). Chúng có liên quan, nhưng không thay thế nhau. Một hệ thống có thể bảo vệ chính xác mọi bất biến trên nguồn dữ liệu có thẩm quyền trong khi các bản sao đọc chậm cập nhật. Ngược lại, mọi bản sao có thể đồng ý với nhau về một trạng thái vốn đã sai quy tắc nghiệp vụ.

Chủ đề này thuộc phạm vi **DATA_PERSISTENCE_FUNDAMENTALS**: thiết kế mô hình dữ liệu và ranh giới persistence trong Java, sử dụng giao dịch, cơ chế cô lập và kiểm soát đồng thời để bảo vệ dữ liệu; đồng thời lựa chọn cách đọc từ bản sao theo yêu cầu độ trễ, khả dụng và độ mới của dữ liệu.

## 2. Nhất quán của bất biến là gì?

**Bất biến** là mệnh đề phải đúng tại mọi trạng thái đã được chấp nhận theo ranh giới nghiệp vụ đã định. Trong cơ sở dữ liệu giao dịch, ta thường yêu cầu bất biến đúng tại mỗi trạng thái **đã commit**; các thay đổi trung gian trong một transaction chưa được công bố không nhất thiết phải tự thỏa mọi ràng buộc đa bước.

Các ví dụ:

| Bối cảnh | Bất biến cần giữ | Cách bảo vệ thường gặp |
| --- | --- | --- |
| Bán hàng | `available >= 0` cho mỗi mã sản phẩm | `CHECK`, cập nhật có điều kiện, khóa hàng |
| Đặt chỗ | Mỗi ghế của một chuyến chỉ có tối đa một đặt chỗ đang có hiệu lực | `UNIQUE` theo khóa phù hợp, giao dịch |
| Chuyển tiền | Một lệnh chuyển không tự tạo hoặc làm mất tiền giữa hai tài khoản nội bộ | Cập nhật cả hai số dư trong cùng transaction, sổ cái đối ứng |
| Hạn mức | Tổng hạn mức đã phân bổ không vượt hạn mức gốc | Kiểm tra và ghi trong ranh giới cô lập đủ mạnh |
| Xử lý yêu cầu | Một mã yêu cầu không sinh hai tác động nghiệp vụ | Khóa idempotency duy nhất, kiểm tra trạng thái kết quả |

Đối với một trạng thái `S`, có thể hình dung một bất biến là vị từ `I(S)`. Một thao tác được chấp nhận phải biến `S` thành `S'` sao cho `I(S') = true`. Nhưng kiểm tra trên một bản đọc cũ rồi mới ghi không tự bảo đảm điều đó: hai transaction có thể đều thấy điều kiện đúng và đồng thời tạo ra trạng thái sai.

### Vai trò của ACID và transaction

Chữ **C (Consistency)** trong ACID nói tới việc transaction chuyển trạng thái hợp lệ thành trạng thái hợp lệ theo các quy tắc được áp đặt. Cơ sở dữ liệu tự bảo vệ những điều được khai báo như khóa chính, khóa ngoại, `UNIQUE` và `CHECK`; các quy tắc nghiệp vụ không được khai báo vẫn cần logic ứng dụng hoặc thiết kế transaction thích hợp.

- **Atomicity:** một tập thay đổi cùng thành công hoặc cùng rollback; hữu ích khi một nghiệp vụ cập nhật nhiều bảng.
- **Isolation:** kiểm soát cách các transaction xen kẽ và quan sát nhau. Mức cô lập quá yếu có thể làm sai một bất biến dù từng transaction riêng lẻ có vẻ hợp lệ.
- **Durability:** dữ liệu đã commit được lưu bền vững theo cam kết của hệ thống lưu trữ. Durability khác với việc mọi bản sao đọc đã nhận bản ghi đó.

Một transaction có tính atomic **chưa đủ** để bảo vệ bất biến cần so sánh nhiều dòng khi có truy cập đồng thời. Ví dụ, hai bác sĩ cùng kiểm tra “phải còn ít nhất một người trực” rồi cập nhật trạng thái trực của *hai dòng khác nhau*: dưới một số triển khai snapshot isolation, cả hai có thể commit và không còn ai trực (write skew). Khi đó cần transaction **serializable**, khóa đúng tập dữ liệu, hoặc tổ chức lại mô hình để ràng buộc được kiểm tra nguyên tử.

## 3. Nhất quán giữa các bản sao là gì?

Hệ thống có thể duy trì một cơ sở dữ liệu chính (leader/primary), nhiều bản sao đọc (replica/follower), cache hoặc các projection được cập nhật từ sự kiện. Nhất quán giữa các bản sao mô tả **khi nào và theo thứ tự nào** bản cập nhật trở nên quan sát được ở những nơi đó.

Một số mức bảo đảm thường gặp:

| Bảo đảm đọc/ghi | Ý nghĩa thực tiễn | Điều cần lưu ý |
| --- | --- | --- |
| **Eventual consistency** | Nếu ngừng ghi và quá trình đồng bộ thành công, các bản sao cuối cùng hội tụ | Trong lúc đồng bộ, đọc có thể thấy dữ liệu cũ |
| **Read-your-writes** | Trong một phiên, người dùng đọc thấy ít nhất các ghi đã xác nhận của chính mình | Cần giữ phiên tại nguồn phù hợp, token phiên bản hoặc chờ replica bắt kịp |
| **Monotonic reads** | Cùng phiên không bị quay ngược về phiên bản cũ hơn đã đọc | Đổi replica tùy ý có thể làm mất bảo đảm này |
| **Causal consistency** | Các thao tác có quan hệ nhân quả được quan sát theo đúng thứ tự phụ thuộc | Không bắt buộc tạo một thứ tự toàn cục cho mọi thao tác độc lập |
| **Linearizability** | Mỗi thao tác có vẻ diễn ra tại một thời điểm giữa lúc bắt đầu và lúc trả kết quả; đọc sau một ghi hoàn tất thấy giá trị phù hợp | Bảo đảm mạnh cho thao tác/đối tượng trong phạm vi áp dụng, thường đòi hỏi phối hợp |

**Không đồng nhất linearizability với serializability.** Serializability kiểm soát thứ tự các **transaction** để kết quả tương đương một lịch tuần tự; linearizability bổ sung yêu cầu tôn trọng thứ tự thời gian thực giữa các **thao tác**. Khi cần cả hai đặc tính cho transaction, thuật ngữ thường dùng là **strict serializability**. Việc đọc/ghi từng khóa theo kiểu linearizable vẫn chưa tự tạo ra transaction nguyên tử qua nhiều khóa.

Những nhãn “synchronous replication”, “quorum” hay “primary–replica” cũng chưa đủ để kết luận một hệ thống cung cấp linearizable read hoặc mọi bất biến đa khóa. Cần xem chính xác cơ chế đồng thuận, quy tắc xác nhận ghi, đường đọc, chuyển vai trò leader và mức cô lập giao dịch.

## 4. Ví dụ: kho chỉ còn một sản phẩm

Giả sử nguồn dữ liệu có thẩm quyền giữ `inventory(sku='LAPTOP-1', available=1)` và một read replica dùng để hiển thị trang sản phẩm.

```mermaid
sequenceDiagram
    participant A as Khách A
    participant P as Primary
    participant R as Read replica
    participant B as Khách B
    A->>P: Đặt 1 sản phẩm
    P->>P: UPDATE có điều kiện: 1 → 0; COMMIT
    P-->>A: Xác nhận đặt hàng
    Note over P,R: Sao chép bất đồng bộ, replica còn available=1
    B->>R: Xem số lượng còn
    R-->>B: available=1 (thông tin cũ)
    B->>P: Thử đặt 1 sản phẩm
    P-->>B: Không đủ hàng (0 dòng được cập nhật)
    P-->>R: Đồng bộ trạng thái available=0
```

Diễn tiến:

1. **T0:** primary và replica đều có `available=1`.
2. **T1:** primary commit đơn hàng A, cập nhật `available=0`; bất biến `available >= 0` vẫn đúng.
3. **T2:** replica chưa nhận thay đổi, nên B thấy “còn hàng”. Đây là **đọc cũ từ replica**, không phải bằng chứng đã bán quá số lượng.
4. **T3:** yêu cầu đặt hàng của B chạy cập nhật có điều kiện **tại primary**; cập nhật thất bại nên B không có đơn được xác nhận.
5. **T4:** replica nhận bản cập nhật và hiển thị hết hàng.

Nếu thay T3 bằng việc B tự quyết định thành công dựa vào kết quả đọc cũ, hoặc hai vùng độc lập cùng ghi nhận một suất mà không phối hợp, hệ thống **có thể vi phạm bất biến toàn cục**. Độ trễ sao chép lúc đó biến thành lỗi nghiệp vụ vì đường ghi đã dựa vào một bằng chứng không còn đủ tin cậy.

### Hai câu hỏi cần kiểm tra riêng

- “Sau hai yêu cầu đặt hàng thành công, tồn kho có âm hoặc số đơn đã xác nhận có vượt số lượng không?” → kiểm tra **bất biến**.
- “Sau khi A mua xong, B mở trang ngay có còn thấy ‘1 sản phẩm’ không?” → kiểm tra **độ mới/nhất quán của bản đọc**.

Muốn trải nghiệm tốt có thể cần cả hai: bảo vệ giao dịch đặt hàng trên primary và dùng read-your-writes hoặc một lần đọc lại từ primary trên màn hình xác nhận.

## 5. Thực thi bất biến trên persistence boundary của Java

Với một cơ sở dữ liệu quan hệ hỗ trợ giao dịch, thiết kế tối thiểu cho tồn kho có thể là:

```sql
CREATE TABLE inventory (
    sku VARCHAR(64) PRIMARY KEY,
    available INTEGER NOT NULL CHECK (available >= 0)
);

CREATE TABLE orders (
    order_id VARCHAR(36) PRIMARY KEY,
    sku VARCHAR(64) NOT NULL REFERENCES inventory(sku),
    quantity INTEGER NOT NULL CHECK (quantity > 0)
);
```

**Mẫu sai** là đọc `available` từ replica, kiểm tra trong Java rằng số lượng đủ, rồi ghi một giá trị mới dựa trên phép tính đó. Ngay cả khi đọc tại primary, hai transaction cùng đọc–sửa–ghi mà thiếu đồng bộ vẫn có thể gây lost update hoặc đặt quá số lượng.

**Mẫu phù hợp hơn** là cập nhật có điều kiện trong cơ sở dữ liệu có thẩm quyền và ghi đơn trong **cùng transaction**:

```sql
UPDATE inventory
SET available = available - :quantity
WHERE sku = :sku AND available >= :quantity;
-- Chỉ ghi đơn hàng nếu affected_rows = 1; nếu không, từ chối hoặc rollback.
```

Trong JDBC, có thể tổ chức ranh giới giao dịch rõ ràng như sau:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.UUID;
import javax.sql.DataSource;

public final class OrderRepository {
    private final DataSource dataSource;

    public OrderRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void placeOrder(UUID orderId, String sku, int quantity)
            throws SQLException {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        // DataSource cần kết nối tới primary cho luồng ghi này.
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try {
                int changed;
                try (PreparedStatement update = connection.prepareStatement(
                        "UPDATE inventory SET available = available - ? " +
                        "WHERE sku = ? AND available >= ?")) {
                    update.setInt(1, quantity);
                    update.setString(2, sku);
                    update.setInt(3, quantity);
                    changed = update.executeUpdate();
                }

                if (changed != 1) {
                    throw new IllegalStateException("Not enough inventory");
                }

                try (PreparedStatement insert = connection.prepareStatement(
                        "INSERT INTO orders(order_id, sku, quantity) VALUES (?, ?, ?)")) {
                    insert.setString(1, orderId.toString());
                    insert.setString(2, sku);
                    insert.setInt(3, quantity);
                    insert.executeUpdate();
                }

                connection.commit();
            } catch (SQLException | RuntimeException error) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            }
        }
    }
}
```

Đoạn mã minh họa hai tính chất: cập nhật tồn kho là **một thao tác có điều kiện tại primary** và bản ghi đơn hàng được commit **cùng giao dịch** với việc trừ kho. Nếu insert đơn hàng thất bại, rollback khôi phục thay đổi tồn kho. Ràng buộc `CHECK` là lớp phòng vệ bổ sung nếu một đường ghi khác cố làm tồn kho âm.

Phạm vi bảo đảm cần được nêu rõ:

- Mọi luồng làm giảm kho phải đi qua cùng nguồn dữ liệu có thẩm quyền hoặc một giao thức phối hợp tương đương; chỉ sửa một repository không thể bảo vệ các đường ghi nằm ngoài nó.
- Với quy tắc liên quan nhiều dòng hoặc nhiều bảng, cập nhật có điều kiện trên một dòng có thể chưa đủ. Cân nhắc `UNIQUE`, `SELECT ... FOR UPDATE`, optimistic locking với cột phiên bản, hoặc transaction **SERIALIZABLE** tùy bất biến và đặc tính DBMS.
- Mã `order_id` duy nhất giúp phát hiện yêu cầu trùng. Tuy nhiên đoạn mã trên **chưa hoàn chỉnh cho idempotent retry**: khi client không biết commit đã thành công hay chưa (ví dụ timeout lúc nhận kết quả), server cần tra cứu theo khóa idempotency và trả lại kết quả cũ, không tự động coi mọi lần gọi lại là giao dịch mới.
- Mức cô lập, hành vi khóa, thời điểm kiểm tra constraint và cách xử lý lỗi có thể khác nhau giữa các DBMS; hãy xác minh trên hệ quản trị thực tế.

## 6. Khi nào replica trở thành nguồn gây vi phạm bất biến?

### Trường hợp A: Bản sao chỉ phục vụ hiển thị

Trang danh mục lấy dữ liệu từ replica đã cũ, nhưng toàn bộ thao tác thanh toán đều kiểm tra tồn kho hoặc giữ chỗ tại primary trong transaction. Kết quả có thể là thông báo “còn hàng” bị trễ, nhưng **đơn không bị xác nhận quá số lượng**. Đây là lỗi trải nghiệm/độ mới nếu yêu cầu sản phẩm đòi số liệu tức thời, không nhất thiết là lỗi bất biến.

### Trường hợp B: Quyết định nghiệp vụ được chốt từ bản sao cũ

Ứng dụng lấy số lượng từ replica rồi phát hành xác nhận đơn hàng trước khi primary chấp nhận cập nhật có điều kiện. Lúc này một bản đọc cũ đã vượt qua **ranh giới ra quyết định**, nên lỗi độ mới có thể trở thành lỗi bất biến. Cách sửa là đưa điểm quyết định vào transaction trên nguồn có thẩm quyền và chỉ xác nhận sau khi commit.

### Trường hợp C: Hai vùng đều có quyền ghi

Hai region cùng có quota tổng là 1 và tạm mất liên lạc. Mỗi region đọc trạng thái địa phương “còn 1”, cùng tạo một đơn và giảm quota cục bộ xuống 0. Mỗi bản sao **tự thỏa** quy tắc “tồn kho địa phương không âm”, nhưng **tổng số đơn toàn hệ thống = 2** vi phạm quy tắc “tối đa 1 đơn”.

Để giữ bất biến toàn cục, cần một cơ chế tương xứng: điều phối ghi vào một authority, giao dịch/đồng thuận phân tán phù hợp, hoặc **chia trước hạn mức** (escrow/quota partitioning), ví dụ cấp 60 suất cho vùng A và 40 suất cho vùng B khi tổng thực có 100. Mỗi vùng chỉ được bán trong ngân sách riêng đã cấp; việc chuyển quota giữa vùng phải được kiểm soát.

Các cấu trúc hợp nhất dữ liệu như CRDT hữu ích cho một số loại cập nhật đồng thời, nhưng **hội tụ tự động không có nghĩa mọi ràng buộc toàn cục được bảo toàn**. Quy tắc như “không vượt tổng 100” cần được thiết kế riêng.

## 7. Chọn chiến lược đọc theo nhu cầu, chọn chiến lược ghi theo bất biến

| Tác vụ | Bảo đảm tối thiểu cần xem xét | Chiến lược khả thi |
| --- | --- | --- |
| Trừ tồn kho / giữ một ghế | Không vượt quota và không ghi trùng | Ghi nguyên tử trên authority; transaction và constraint phù hợp |
| Xem trang danh mục | Có thể chấp nhận độ trễ được công bố | Read replica/cache với ngân sách staleness và theo dõi replication lag |
| Xem đơn vừa đặt | Người đặt thấy kết quả vừa commit | Read-your-writes: đọc primary, pin phiên, hoặc chờ replica đạt phiên bản yêu cầu |
| Nạp trang nhiều lần | Không hiển thị phiên bản cũ hơn phiên đã đọc | Monotonic reads bằng session token/định tuyến theo phiên |
| Báo cáo thống kê | Có thể chậm vài phút nhưng cần biết mốc dữ liệu | Projection bất đồng bộ, watermark hoặc thời điểm cập nhật gần nhất |
| Chuyển tiền / xử lý hạn mức | Bất biến đa bước và thứ tự cạnh tranh | Transaction đủ cô lập, khóa/constraint, kiểm tra xung đột và retry hợp lý |

Một số cách hiện thực read-your-writes:

1. Đọc trực tiếp từ primary cho các request ngay sau ghi; cách này dễ hiểu nhưng tăng tải và phụ thuộc vào primary.
2. Đính kèm **vị trí log/phiên bản commit** vào kết quả ghi; khi đọc replica, chờ cho tới khi nó đã áp dụng ít nhất vị trí tương ứng, có giới hạn thời gian chờ và fallback rõ ràng.
3. Dùng session affinity đến replica đã bắt kịp, đồng thời xử lý trường hợp replica đổi vai trò hoặc phiên hết hạn.

Chỉ định tuyến tất cả request về “một replica cố định” không tự đảm bảo read-your-writes: replica đó vẫn có thể chưa nhận bản ghi vừa commit.

## 8. Giao dịch, sự kiện và ranh giới nhất quán

Trong hệ thống Java thường có một DB giao dịch cho lệnh đặt hàng và các thành phần khác phục vụ email, tìm kiếm, báo cáo hoặc cache. Nên phân biệt:

- **Bất biến cốt lõi:** đơn được tạo và kho được giảm trong cùng transaction của DB nguồn. Các điều kiện như uniqueness, giới hạn số dư hoặc khả năng chuyển trạng thái hợp lệ phải được bảo vệ tại điểm commit.
- **Bản sao hoặc projection:** chỉ mục tìm kiếm và thống kê có thể cập nhật sau commit. Độ trễ ở đây cần được đo và phản ánh trong cách đọc, nhưng không tự làm transaction gốc mất hiệu lực.
- **Tác động bên ngoài:** gửi email hoặc gọi API thanh toán ngoài DB không trở thành atomic chỉ vì nằm giữa hai lệnh JDBC. Có thể dùng **transactional outbox** để ghi sự kiện trong transaction nguồn rồi chuyển đi bất đồng bộ, kết hợp consumer idempotent. Điều này cải thiện việc phát sự kiện tin cậy; nó không biến tất cả dịch vụ thành một transaction toàn cục.

Khi primary gặp sự cố, cũng phải xác minh **đã xác nhận ghi theo tiêu chí nào** và quy trình failover có giữ lại bản ghi đó hay không. Một hệ thống chấp nhận ghi tại primary rồi sao chép bất đồng bộ có thể mất các ghi gần nhất khi chuyển sang replica chưa bắt kịp; đây là vấn đề durability và chính sách failover, cần đánh giá bên cạnh độ trễ đọc.

## 9. Cách kiểm thử và chẩn đoán

Đừng chỉ chạy một đường đi tuần tự. Cần kiểm thử riêng việc **bảo toàn bất biến khi cạnh tranh ghi** và **độ mới của dữ liệu khi đọc qua replica**.

**Kiểm thử bất biến:** khởi tạo tồn kho 1, cho nhiều request đặt hàng chạy đồng thời với các `order_id` khác nhau; yêu cầu cuối cùng chỉ có tối đa một đơn thành công và tồn kho không âm. Với bất biến đa dòng, dựng tình huống hai transaction cùng kiểm tra điều kiện rồi sửa các dòng khác nhau. Chạy với mức cô lập thực tế, có kiểm thử retry, timeout quanh commit và xung đột khóa.

**Kiểm thử replica:** cố ý tạo hoặc mô phỏng độ trễ sao chép; sau khi đơn đã commit, đọc từ replica và đo độ trễ cho tới khi thấy phiên bản mới. Kiểm tra read-your-writes, monotonic reads, tình huống đổi replica, failover và chính sách timeout/fallback. Việc UI hiện số cũ cần được ghi nhận độc lập với kết quả kiểm thử “không bán vượt kho”.

Các câu hỏi thiết kế đáng trả lời:

1. Bất biến chính xác là gì, áp dụng trên **một dòng, nhiều dòng, hay toàn bộ nhiều vùng**?
2. Nguồn ghi có thẩm quyền là đâu? Mọi thao tác nghiệp vụ có đi qua cùng ranh giới bảo vệ không?
3. Constraint, khóa hoặc mức cô lập nào bảo đảm bất biến trước cạnh tranh thực tế?
4. Người đọc chấp nhận dữ liệu cũ trong bao lâu? Có yêu cầu read-your-writes hoặc monotonic reads không?
5. Nếu ghi đã commit nhưng phản hồi bị mất, retry xác định kết quả cũ như thế nào?
6. Nếu replication bị chậm hoặc một node lỗi, ứng dụng báo độ trễ, fallback và phục hồi ra sao?

## 10. Tự kiểm tra

**Tình huống 1.** Khách A vừa đặt ghế số 12 thành công; trang sơ đồ ghế của khách B vẫn hiển thị ghế trống trong 2 giây. B thử đặt nhưng bị từ chối tại primary. Có vi phạm bất biến “một ghế chỉ có một đặt chỗ” không?

**Tình huống 2.** Hai transaction cùng đọc rằng đang có 4/5 suất; mỗi transaction thêm một dòng đặt chỗ khác nhau rồi commit, kết quả là 6/5 suất. Replica đã đồng bộ hoàn toàn. Lỗi thuộc nhóm nào?

**Tình huống 3.** Một lệnh ghi thành công trả về cho người dùng; request xem trạng thái ngay sau đó được điều hướng tới một replica đang chậm. Cần thêm bảo đảm đọc nào để người dùng thấy lệnh của mình?

**Gợi ý trả lời:** (1) Chưa; bất biến vẫn được giữ, nhưng replica đang đọc cũ. (2) Vi phạm bất biến do kiểm soát đồng thời/transaction không đủ mạnh, dù bản sao đã hội tụ. (3) Read-your-writes, chẳng hạn đọc primary hoặc đợi replica đạt phiên bản commit.

## Kết luận

**Nhất quán của bất biến** hỏi liệu mọi trạng thái nghiệp vụ được chấp nhận có hợp lệ hay không; phải thiết kế transaction, constraint và cơ chế đồng thời tại ranh giới ghi. **Nhất quán giữa các bản sao** hỏi người đọc ở mỗi nơi được thấy phiên bản nào và khi nào; phải thiết kế replication, chiến lược đọc và yêu cầu phiên. Đảm bảo một loại không tự kéo theo loại kia. Khi thiết kế persistence cho Java, hãy phát biểu rõ cả **bất biến khi commit** lẫn **độ mới cần thiết khi đọc** để chọn công cụ đúng cho từng vấn đề.
