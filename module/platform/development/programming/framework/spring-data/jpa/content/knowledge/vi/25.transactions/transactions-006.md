# Isolation, hiện tượng đọc dữ liệu và khả năng hỗ trợ của cơ sở dữ liệu

## 1. Isolation trong giao dịch là gì?

Một ứng dụng có thể xử lý nhiều giao dịch cùng lúc. Khi hai giao dịch đọc hoặc sửa cùng dữ liệu, kết quả một giao dịch nhìn thấy phụ thuộc vào thời điểm đọc, thời điểm ghi và cách cơ sở dữ liệu điều phối truy cập đồng thời.

**Isolation (tính cô lập)** là thuộc tính ACID quy định mức độ một giao dịch bị ảnh hưởng bởi các giao dịch đang chạy đồng thời. Mức cô lập càng cao thì kết quả càng gần với việc các giao dịch chạy lần lượt, nhưng hệ thống có thể phải giữ khóa lâu hơn, chờ nhiều hơn hoặc hủy một giao dịch khi phát hiện xung đột.

Isolation không đồng nghĩa với việc chỉ có một giao dịch được chạy tại một thời điểm. Cơ sở dữ liệu có thể dùng khóa (locking), phiên bản hàng (MVCC) hoặc kết hợp cả hai để cho phép nhiều giao dịch cùng tiến hành mà vẫn bảo đảm các quy tắc đã chọn.

Trong Spring Data JPA, isolation được cấu hình ở ranh giới transaction của Spring. JPA làm việc với persistence context và transaction manager; mức cô lập thực tế cuối cùng do transaction manager, JDBC connection và hệ quản trị cơ sở dữ liệu phối hợp thực hiện.

## 2. Ba hiện tượng đọc dữ liệu thường gặp

Để dễ theo dõi, giả sử bảng account có một tài khoản với id = 1 và balance = 1000.

### 2.1. Dirty read — đọc dữ liệu chưa commit

Dirty read xảy ra khi giao dịch T2 đọc được thay đổi mà T1 đã ghi nhưng chưa commit. Nếu T1 rollback, giá trị T2 từng đọc chưa bao giờ trở thành dữ liệu đã commit.

~~~sql
-- T1
BEGIN;
UPDATE account SET balance = 500 WHERE id = 1;
-- T1 chưa COMMIT

-- T2, nếu mức cô lập cho phép dirty read
SELECT balance FROM account WHERE id = 1;
-- Có thể đọc được 500 dù T1 chưa commit

-- T1
ROLLBACK;
-- Giá trị 500 bị hủy; dữ liệu đã commit vẫn là 1000
~~~

Hậu quả: T2 có thể đưa ra quyết định dựa trên dữ liệu sẽ bị hủy, chẳng hạn ghi nhận một khoản thanh toán chưa thực sự tồn tại. READ COMMITTED trở lên phải ngăn dirty read theo định nghĩa chuẩn. Một số cơ sở dữ liệu còn không cho phép dirty read dù ứng dụng yêu cầu READ UNCOMMITTED.

### 2.2. Non-repeatable read — đọc cùng một hàng nhưng nhận giá trị khác

Non-repeatable read xảy ra khi T1 đọc một hàng, T2 sửa và commit hàng đó, rồi T1 đọc lại chính hàng ấy và nhận giá trị mới.

~~~sql
-- T1
BEGIN;
SELECT balance FROM account WHERE id = 1; -- 1000

-- T2
BEGIN;
UPDATE account SET balance = 800 WHERE id = 1;
COMMIT;

-- T1
SELECT balance FROM account WHERE id = 1; -- có thể là 800 ở READ COMMITTED
COMMIT;
~~~

T1 không nhận lại cùng một giá trị trong hai lần đọc. Hiện tượng này có thể làm một phép tính trong cùng giao dịch dùng các giá trị không nhất quán. REPEATABLE READ trở lên ngăn non-repeatable read theo định nghĩa chuẩn.

### 2.3. Phantom read — tập hàng thỏa điều kiện thay đổi

Phantom read xảy ra khi T1 chạy lại một truy vấn theo điều kiện và nhận được tập hàng khác, do giao dịch khác đã thêm, xóa hoặc thay đổi hàng để nó bắt đầu hoặc ngừng thỏa điều kiện.

~~~sql
-- T1
BEGIN;
SELECT id FROM orders WHERE total >= 100;
-- Kết quả: đơn hàng 10 và 11

-- T2
BEGIN;
INSERT INTO orders(id, total) VALUES (12, 150);
COMMIT;

-- T1
SELECT id FROM orders WHERE total >= 100;
-- Ở mức cho phép phantom read, kết quả có thêm đơn hàng 12
COMMIT;
~~~

Non-repeatable read tập trung vào giá trị của một hàng đã đọc; phantom read tập trung vào thành viên của tập kết quả theo một điều kiện. Để ngăn phantom, hệ quản trị có thể khóa cả khoảng khóa (key range) hoặc giữ một snapshot nhất quán trong suốt giao dịch.

### 2.4. Một số lỗi đồng thời khác

Ba hiện tượng trên là các hiện tượng đọc được dùng trong định nghĩa mức cô lập của SQL. Chúng không bao quát mọi lỗi đồng thời có thể xảy ra.

- **Lost update (mất cập nhật):** T1 và T2 cùng đọc số dư 1000. T1 cộng 100, T2 trừ 50. Nếu cả hai ghi giá trị dựa trên bản đọc cũ, lần ghi sau có thể ghi đè kết quả lần ghi trước.
- **Read skew:** T1 đọc số dư tài khoản A trước khi T2 chuyển tiền từ A sang B, rồi đọc số dư B sau khi T2 commit. T1 có thể thấy trạng thái kết hợp từ hai thời điểm khác nhau.
- **Write skew:** Hai giao dịch cùng đọc một snapshot thỏa một quy tắc nghiệp vụ, sau đó cập nhật hai hàng khác nhau. Mỗi lần ghi riêng lẻ đều hợp lệ nhưng tổng thể có thể vi phạm quy tắc, ví dụ cả hai bác sĩ cùng tự đánh dấu nghỉ trực dù hệ thống yêu cầu luôn có ít nhất một người trực.

Cần phân biệt các lỗi này với ba hiện tượng đọc chuẩn. Chẳng hạn, REPEATABLE READ không tự động bảo vệ mọi bất biến nghiệp vụ hoặc ngăn mọi lost update trên tất cả hệ quản trị.

## 3. Bốn mức cô lập chuẩn của SQL

Bảng sau mô tả mức bảo đảm tối thiểu theo định nghĩa chuẩn SQL:

| Mức cô lập | Dirty read | Non-repeatable read | Phantom read |
|---|---|---|---|
| READ UNCOMMITTED | Có thể xảy ra | Có thể xảy ra | Có thể xảy ra |
| READ COMMITTED | Bị ngăn | Có thể xảy ra | Có thể xảy ra |
| REPEATABLE READ | Bị ngăn | Bị ngăn | Có thể xảy ra theo chuẩn |
| SERIALIZABLE | Bị ngăn | Bị ngăn | Bị ngăn |

### 3.1. READ UNCOMMITTED

Đây là mức cô lập thấp nhất. Giao dịch có thể đọc thay đổi chưa commit của giao dịch khác. Mức này có thể giảm thời gian chờ đọc trong một số hệ thống, nhưng nguy cơ đọc dữ liệu sẽ rollback khiến kết quả nghiệp vụ không đáng tin cậy.

Không nên chọn mức này chỉ vì muốn truy vấn nhanh. Nhiều hệ quản trị không triển khai dirty read đúng nghĩa hoặc ánh xạ yêu cầu này sang READ COMMITTED.

### 3.2. READ COMMITTED

Mỗi câu lệnh chỉ đọc dữ liệu đã commit tại thời điểm câu lệnh bắt đầu hoặc theo cơ chế tương ứng của hệ quản trị. Dirty read bị ngăn, nhưng hai câu SELECT trong cùng transaction vẫn có thể thấy các phiên bản đã commit khác nhau.

Đây là mức mặc định phổ biến, cân bằng giữa tính nhất quán và khả năng chạy đồng thời. Nó phù hợp với nhiều nghiệp vụ thông thường, nhưng một quy trình đọc nhiều lần rồi quyết định dựa trên một snapshot xuyên suốt có thể cần mức cao hơn hoặc cơ chế khóa riêng.

### 3.3. REPEATABLE READ

Các lần đọc lặp lại trong một transaction phải giữ được tính nhất quán đối với hàng đã đọc theo bảo đảm của mức này. Theo định nghĩa chuẩn, phantom read vẫn có thể xảy ra vì một truy vấn theo điều kiện có thể nhận thêm hàng phù hợp.

Cách triển khai phụ thuộc hệ quản trị. Một số hệ thống dùng snapshot ở cấp transaction và ngăn cả phantom read trong các truy vấn đọc thông thường; điều đó không có nghĩa mọi bất thường đồng thời đều biến mất. Write skew hoặc serialization anomaly vẫn có thể xuất hiện trong một số mô hình snapshot isolation.

### 3.4. SERIALIZABLE

Đây là mức cô lập cao nhất trong bốn mức chuẩn. Kết quả của các transaction đồng thời phải tương đương với một thứ tự chạy tuần tự nào đó. Hệ quản trị có thể đạt điều này bằng khóa hoặc phát hiện xung đột.

Mức này phù hợp khi nhiều giao dịch cùng tác động đến một quy tắc nghiệp vụ phức tạp mà khóa hàng đơn lẻ hoặc kiểm tra ở tầng ứng dụng chưa đủ bảo vệ. Đổi lại, giao dịch có thể phải chờ, gặp deadlock hoặc bị hủy do xung đột tuần tự hóa. Ứng dụng cần xử lý và có thể retry toàn bộ transaction khi hệ quản trị trả lỗi serialization phù hợp.

## 4. Khả năng hỗ trợ ở một số hệ quản trị cơ sở dữ liệu

Tên mức cô lập giống nhau không bảo đảm mọi hệ quản trị có hành vi hoàn toàn giống nhau. Bảng dưới đây mô tả các cấu hình phổ biến; phiên bản, engine, tùy chọn database và cấu hình session có thể làm thay đổi hành vi.

| Hệ quản trị | Mức mặc định thường gặp | Khả năng hỗ trợ và điểm cần lưu ý |
|---|---|---|
| PostgreSQL | READ COMMITTED | Chấp nhận bốn mức chuẩn. READ UNCOMMITTED được xử lý như READ COMMITTED, nên không tạo dirty read. REPEATABLE READ dùng snapshot cấp transaction và ngăn cả phantom read, nhưng vẫn có thể có serialization anomaly. SERIALIZABLE dùng cơ chế phát hiện xung đột và có thể hủy transaction để bảo đảm tuần tự hóa. |
| MySQL với InnoDB | REPEATABLE READ | Hỗ trợ bốn mức chuẩn. Ở REPEATABLE READ, consistent read thông thường dùng snapshot được thiết lập trong transaction; locking read và thao tác trên khoảng khóa dùng cơ chế khóa, gồm next-key lock, để kiểm soát phantom. READ UNCOMMITTED có thể đọc thay đổi chưa commit. Cần xác nhận bảng dùng engine có hỗ trợ transaction, thường là InnoDB. |
| Microsoft SQL Server | READ COMMITTED | Hỗ trợ bốn mức chuẩn và có mức riêng SNAPSHOT. REPEATABLE READ giữ khóa trên hàng đã đọc nhưng vẫn có thể cho phép hàng mới phù hợp điều kiện xuất hiện; SERIALIZABLE dùng key-range lock để ngăn phantom. Tùy chọn READ_COMMITTED_SNAPSHOT làm READ COMMITTED dùng row versioning ở cấp câu lệnh; SNAPSHOT ở cấp transaction cần được bật riêng bằng cấu hình database. |
| Oracle Database | READ COMMITTED | Các mức transaction isolation có thể chọn là READ COMMITTED và SERIALIZABLE; Oracle không cung cấp READ UNCOMMITTED hoặc REPEATABLE READ như các mức có thể chọn. Oracle dùng read consistency để tránh dirty read; READ COMMITTED có tính nhất quán ở cấp câu lệnh, còn SERIALIZABLE cung cấp snapshot ở cấp transaction. Chế độ READ ONLY là chế độ transaction riêng, không phải mức thứ ba trong bốn mức chuẩn. |

Một vài hệ quả khi đọc bảng:

- Nếu đặt READ_UNCOMMITTED trên PostgreSQL, ứng dụng vẫn không đọc dirty data vì PostgreSQL thực hiện nó như READ_COMMITTED.
- Không thể kết luận rằng mọi hệ quản trị có REPEATABLE_READ đều xử lý phantom giống nhau. SQL Server có thể cho phantom ở mức này; PostgreSQL và InnoDB thường cung cấp bảo đảm mạnh hơn cho các kiểu đọc snapshot tương ứng.
- SNAPSHOT của SQL Server là mức riêng của nhà cung cấp, không phải một hằng trong bốn mức chuẩn của Spring.
- Với MySQL, phải xét đúng storage engine. Không nên suy luận rằng mọi bảng hoặc mọi cấu hình MySQL đều có cùng ngữ nghĩa transaction như InnoDB.

## 5. Cấu hình isolation trong Spring Data JPA

Spring cung cấp enum Isolation trong package org.springframework.transaction.annotation. Có thể đặt mức cô lập trên @Transactional:

| Giá trị Spring | Ý nghĩa |
|---|---|
| Isolation.DEFAULT | Dùng mức mặc định của database hoặc connection; đây là giá trị mặc định của annotation. |
| Isolation.READ_UNCOMMITTED | Yêu cầu READ UNCOMMITTED. |
| Isolation.READ_COMMITTED | Yêu cầu READ COMMITTED. |
| Isolation.REPEATABLE_READ | Yêu cầu REPEATABLE READ. |
| Isolation.SERIALIZABLE | Yêu cầu SERIALIZABLE. |

Ví dụ một service xác nhận đơn hàng:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final OrderRepository orders;

    public OrderService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public void confirm(Long id) {
        Order order = orders.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("Order not found: " + id));

        order.confirm();
    }
}
~~~

Đây là đoạn mã minh họa cho service; Order, OrderRepository và phương thức confirm() thuộc mô hình của ứng dụng. Khi phương thức được gọi qua Spring proxy, transaction được mở theo cấu hình của transaction manager. Entity được quản lý trong persistence context sẽ được đồng bộ xuống database khi flush hoặc commit.

Nên đặt ranh giới transaction ở service khi một nghiệp vụ gồm nhiều thao tác repository. Như vậy các lần đọc và ghi cùng tham gia một transaction, và chính sách isolation được áp dụng cho toàn bộ nghiệp vụ. Các phương thức CRUD kế thừa của Spring Data repository có cấu hình transaction mặc định; với query method tự khai báo, hãy cấu hình transaction rõ ràng hoặc gọi nó bên trong transaction của service.

### 5.1. Những giới hạn quan trọng của @Transactional

**Isolation chỉ được áp dụng khi bắt đầu transaction mới.** Với propagation mặc định REQUIRED, nếu service được gọi trong một transaction đã tồn tại, lời gọi sẽ tham gia transaction đó và dùng isolation của transaction bên ngoài. Khai báo isolation khác ở phương thức bên trong không tự đổi isolation của transaction đang chạy.

Spring transaction manager có tùy chọn validateExistingTransaction để từ chối tham gia một transaction có isolation không tương thích. Đây là lựa chọn cấu hình khi ứng dụng cần phát hiện việc truyền transaction sai mức; nó không tự nâng isolation của transaction hiện tại.

**Transaction manager và database phải hỗ trợ mức được yêu cầu.** @Transactional là cấu hình của Spring, không làm cho một database hỗ trợ mức mà nó không có. Khả năng áp dụng mức cô lập còn phụ thuộc transaction manager, JPA dialect và JDBC driver. Với JpaTransactionManager, dialect phải có khả năng áp dụng cấu hình isolation cho JDBC connection. Hãy kiểm tra cấu hình và hành vi thực tế trên database đích.

**Lời gọi nội bộ trong cùng bean có thể bỏ qua proxy.** Ở chế độ proxy mặc định, một phương thức gọi phương thức @Transactional khác trên chính đối tượng đó không đi qua Spring proxy. Khi ấy cấu hình transaction trên phương thức được gọi có thể không được kích hoạt. Nên gọi qua một Spring bean khác hoặc tổ chức lại ranh giới transaction.

**Isolation không thay thế các cơ chế đồng thời ở tầng dữ liệu.** @Version hỗ trợ optimistic locking bằng cách phát hiện cập nhật dựa trên phiên bản cũ của entity. @Lock với PESSIMISTIC_WRITE có thể yêu cầu khóa ghi cho một truy vấn repository. Ràng buộc UNIQUE, FOREIGN KEY, CHECK và câu lệnh cập nhật có điều kiện cũng là các công cụ bảo vệ bất biến dữ liệu. Hãy chọn cơ chế phù hợp với quy tắc nghiệp vụ thay vì chỉ tăng isolation cho mọi transaction.

### 5.2. Lưu ý riêng về persistence context của JPA

JPA giữ entity đã tải trong first-level cache của persistence context. Nếu gọi findById() lần nữa trong cùng persistence context, EntityManager có thể trả lại entity đang được quản lý mà không phát sinh SELECT mới. Vì vậy, khi kiểm tra non-repeatable read hoặc phantom read, kết quả quan sát ở Java có thể bị ảnh hưởng bởi cache của JPA.

Để kiểm thử đúng hành vi database, cần kiểm soát thời điểm flush, clear persistence context, câu SQL thực sự được phát ra và transaction của từng luồng. Việc gọi lại một phương thức repository không nhất thiết đồng nghĩa database đã thực hiện lại đúng câu SELECT.

## 6. Chọn mức cô lập theo nghiệp vụ

- **Dùng DEFAULT khi có thể:** để database áp dụng cấu hình mặc định đã được vận hành và kiểm thử. Đây thường là lựa chọn tốt cho CRUD thông thường.
- **Dùng READ COMMITTED cho phần lớn nghiệp vụ thông thường:** ngăn dirty read và cho phép mức đồng thời tốt. Nếu một nghiệp vụ cần snapshot ổn định qua nhiều lần đọc, hãy đánh giá thêm.
- **Dùng REPEATABLE READ khi cần đọc lặp lại nhất quán:** kiểm tra chính xác hành vi phantom, snapshot và cập nhật đồng thời của hệ quản trị đang dùng.
- **Dùng SERIALIZABLE khi cần bảo vệ bất biến phức tạp:** ví dụ giới hạn tổng số chỗ, hạn mức dùng chung hoặc quy tắc phụ thuộc nhiều hàng. Thiết kế retry khi transaction bị hủy do xung đột.
- **Hạn chế READ UNCOMMITTED:** chỉ dùng khi chấp nhận dữ liệu chưa commit và đã hiểu cách database triển khai. Với dữ liệu nghiệp vụ, dirty read thường tạo rủi ro lớn hơn lợi ích.

Khi xử lý cập nhật đồng thời, cân nhắc thêm:

1. Dùng @Version cho optimistic locking khi nhiều người dùng có thể sửa cùng một entity. Nếu phiên bản đã thay đổi, ứng dụng nhận xung đột thay vì âm thầm ghi đè.
2. Dùng pessimistic lock cho vùng dữ liệu cần khóa trong thời gian xử lý ngắn, ví dụ giữ một bản ghi tồn kho trước khi trừ số lượng. Phải giữ transaction ngắn để tránh khóa lâu và deadlock.
3. Đưa quy tắc vào constraint hoặc câu lệnh cập nhật có điều kiện khi có thể. Ví dụ cập nhật tồn kho chỉ khi quantity >= :requestedQuantity, rồi kiểm tra số hàng được cập nhật.
4. Với SERIALIZABLE hoặc snapshot isolation, chuẩn bị xử lý lỗi xung đột và retry toàn bộ đơn vị công việc. Không chỉ retry một câu lệnh ở giữa transaction đã bị hủy.
5. Kiểm thử trên cùng loại database và cấu hình gần production. H2 hoặc database giả lập có thể có ngữ nghĩa isolation khác PostgreSQL, MySQL, SQL Server hay Oracle.

## 7. Cách kiểm thử hiện tượng đọc

Một bài kiểm thử isolation cần ít nhất hai transaction độc lập, thường chạy trên hai thread hoặc hai connection. Điều khiển thứ tự thao tác bằng latch/barrier để bảo đảm T1 đọc trước, T2 ghi và commit, rồi T1 đọc lại. Nếu dùng cùng một EntityManager hoặc cùng transaction, bài kiểm thử có thể không mô phỏng đúng cạnh tranh giữa hai transaction.

Quy trình kiểm thử cơ bản:

1. Tạo dữ liệu ban đầu đã commit.
2. Mở transaction T1 và thực hiện lần đọc thứ nhất.
3. Mở transaction T2 độc lập, sửa hoặc thêm dữ liệu, sau đó commit.
4. Trong T1, chạy lại truy vấn cần kiểm tra.
5. So sánh kết quả với bảo đảm của isolation level trên database đang dùng.
6. Kiểm tra thêm trường hợp rollback, lock wait, deadlock hoặc serialization failure nếu nghiệp vụ có thể gặp.

Không nên chỉ dựa vào một unit test chạy tuần tự để kết luận isolation đúng. Hãy dùng integration test với database thực tế (ví dụ Testcontainers cho engine mà ứng dụng triển khai), vì hành vi khóa, MVCC, snapshot và lỗi đồng thời phụ thuộc hệ quản trị.

## 8. Những nhầm lẫn thường gặp

- **Isolation khác propagation:** isolation nói về mức cô lập dữ liệu; propagation nói transaction được tạo mới, tham gia hay tách khỏi transaction hiện tại như thế nào.
- **Isolation khác locking:** mức cô lập là chính sách tổng thể; database có thể dùng khóa, MVCC hoặc cả hai để thực hiện chính sách đó.
- **readOnly = true không phải isolation level:** đây là gợi ý tối ưu hoặc chế độ hạn chế ghi tùy transaction manager/database, không tự ngăn các transaction khác cập nhật dữ liệu.
- **REPEATABLE READ không đồng nghĩa SERIALIZABLE:** một số bất thường như write skew vẫn có thể xảy ra dưới snapshot isolation.
- **@Version không thay thế isolation:** nó bảo vệ cập nhật entity có version, nhưng không tự bảo vệ mọi quy tắc liên quan nhiều hàng.
- **Không nên giả định mọi database hỗ trợ giống nhau:** luôn đối chiếu tài liệu engine, cấu hình session và kiểm thử trên hệ thống đích.

Khi thiết kế giao dịch trong Spring Data JPA, hãy bắt đầu từ bất biến nghiệp vụ cần bảo vệ, xác định hiện tượng đồng thời nào có thể làm sai kết quả, rồi chọn mức isolation hoặc cơ chế khóa phù hợp. Cách này giúp cân bằng tính đúng đắn, khả năng xử lý đồng thời và chi phí vận hành.