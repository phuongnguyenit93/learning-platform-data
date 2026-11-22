# Tác động của IDENTITY và SEQUENCE đến khả năng batching

## 1. JDBC batching trong Spring Data JPA

Khi lưu nhiều entity, ứng dụng có thể phát sinh hàng trăm hoặc hàng nghìn câu lệnh INSERT. Nếu gửi từng câu lệnh riêng lẻ, mỗi lần thực thi có thể tạo thêm chi phí gọi JDBC và giao tiếp giữa ứng dụng với database. **JDBC batching** cho phép gom nhiều lần thực thi cùng một prepared statement thành một batch rồi gửi xuống database theo nhóm.

Ví dụ, thay vì gửi lần lượt 100 câu INSERT cho 100 đơn hàng, Hibernate có thể chuẩn bị cùng một mẫu INSERT, gán bộ tham số cho từng đơn hàng rồi gọi cơ chế batch của JDBC. Database vẫn xử lý các bản ghi theo từng lệnh INSERT; batching chủ yếu giảm số lần trao đổi và chi phí gọi JDBC, không biến chúng thành một câu SQL duy nhất.

Trong Spring Data JPA, Hibernate thường là JPA provider. Hibernate quản lý entity trong persistence context, sau đó phát SQL khi flush. Khả năng gom INSERT vào JDBC batch phụ thuộc vào:

- Cấu hình batch size của Hibernate.
- Chiến lược sinh identifier (khóa chính) của entity.
- Các câu SQL có cùng hình dạng để gom vào cùng batch hay không.
- Thời điểm flush, transaction boundary và hành vi của JDBC driver.
- Cấu hình database, dialect và phiên bản Hibernate.

JPA specification không bắt buộc mọi provider phải triển khai JDBC batching theo cùng một cách. Phần giải thích dưới đây tập trung vào Hibernate, là provider phổ biến trong các ứng dụng Spring Data JPA.

## 2. IDENTITY hoạt động như thế nào?

Với chiến lược IDENTITY, database tự sinh khóa chính khi thực hiện INSERT. Ứng dụng chưa biết giá trị ID trước khi câu INSERT được thực thi.

Ví dụ entity dùng cột tự tăng:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String customerName;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String customerName) {
        this.customerName = customerName;
    }
}
~~~

Các hệ quản trị có thể triển khai kiểu này bằng cột identity hoặc auto-increment, chẳng hạn MySQL AUTO_INCREMENT hay SQL Server IDENTITY.

### 2.1. Vì sao IDENTITY cản trở insert batching trong Hibernate?

Sau khi INSERT, Hibernate cần biết ID database vừa tạo để định danh entity trong persistence context, quản lý quan hệ và xử lý các thao tác tiếp theo. Với IDENTITY, giá trị này chỉ có sau khi database thực hiện INSERT và trả generated key.

Do cần lấy ID từ database, Hibernate thường phải thực thi INSERT riêng cho entity dùng IDENTITY. Hibernate vì vậy **vô hiệu hóa JDBC insert batching cho các entity sử dụng identity identifier generator**. Dù đã đặt batch size lớn hơn 0, các INSERT của nhóm entity này vẫn không được gom thành JDBC insert batch.

Hệ quả thực tế:

- Gọi save() nhiều lần hoặc saveAll() không làm cho INSERT IDENTITY tự động trở thành một JDBC batch.
- Tăng hibernate.jdbc.batch_size không khắc phục được giới hạn insert batching của IDENTITY trong Hibernate.
- Các thao tác UPDATE và DELETE vẫn có thể được batch nếu thỏa các điều kiện batching khác.
- Các entity khác dùng SEQUENCE vẫn có thể insert theo batch trong cùng ứng dụng.

Đây là giới hạn của đường thực thi IDENTITY trong Hibernate, không phải quy tắc rằng mọi thao tác SQL trong transaction đều mất batching. Provider JPA khác có thể có cách triển khai riêng, vì vậy cần kiểm tra tài liệu provider đang dùng.

### 2.2. Khi nào IDENTITY vẫn hợp lý?

IDENTITY đơn giản, dễ cấu hình và phù hợp khi database đã chuẩn hóa việc sinh ID bằng cột tự tăng, lượng insert không lớn hoặc hiệu năng insert chưa phải nút thắt. Nó cũng phù hợp khi tính tương thích với schema hiện hữu quan trọng hơn khả năng batch insert.

Không nên đổi chiến lược chỉ dựa trên giả định rằng sequence luôn nhanh hơn. Hãy đo workload thực tế, xét database đang triển khai và cân nhắc khả năng batching có đem lại lợi ích đáng kể hay không.

## 3. SEQUENCE hoạt động như thế nào?

Với chiến lược SEQUENCE, Hibernate lấy giá trị từ một database sequence trước khi INSERT entity. Vì đã có ID trước lúc gửi INSERT, Hibernate có thể xếp nhiều entity vào persistence context và gom các INSERT tương ứng thành JDBC batch khi flush.

Ví dụ khai báo sequence generator:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.SequenceGenerator;

@Entity
public class PurchaseOrder {
    @Id
    @SequenceGenerator(
        name = "purchase_order_seq_gen",
        sequenceName = "purchase_order_seq",
        allocationSize = 50
    )
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "purchase_order_seq_gen"
    )
    private Long id;

    private String customerName;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String customerName) {
        this.customerName = customerName;
    }
}
~~~

Trong ví dụ, purchase_order_seq_gen là tên generator được tham chiếu trong mapping JPA; purchase_order_seq là tên sequence ở database. allocationSize là số định danh mà provider có thể cấp phát theo cơ chế allocation/optimizer. Giá trị mặc định của allocationSize trong JPA là 50 nếu không khai báo.

### 3.1. Vì sao SEQUENCE cho phép batching?

Quy trình khái quát:

1. Hibernate lấy trước một hoặc nhiều ID từ sequence.
2. Entity được gắn ID và quản lý trong persistence context.
3. Khi flush, Hibernate phát các INSERT có cùng hình dạng SQL.
4. Các INSERT phù hợp được gom thành batch theo cấu hình JDBC.
5. JDBC driver gửi batch đến database.

Hibernate không cần chờ INSERT hoàn tất mới biết ID của entity. Đây là khác biệt then chốt giúp SEQUENCE thuận lợi cho insert batching.

Nếu allocationSize bằng 1, provider có thể phải lấy sequence value thường xuyên hơn. Dù vậy, việc đã biết ID trước INSERT vẫn cho phép gom các INSERT; allocationSize và JDBC batch size là hai thiết lập độc lập.

### 3.2. allocationSize không phải batch size

Hai tham số thường bị nhầm lẫn:

| Tham số | Chức năng |
|---|---|
| allocationSize | Số ID được cấp phát theo cơ chế sequence allocation của JPA provider. |
| hibernate.jdbc.batch_size | Số lệnh JDBC tối đa Hibernate cố gắng gom vào một batch. |

Ví dụ allocationSize bằng 50 và batch_size bằng 50 không có nghĩa hai tính năng là một. Một tham số điều khiển cấp phát ID; tham số còn lại điều khiển số câu lệnh JDBC trong batch.

Hibernate có thể dùng sequence optimizer để cấp phát một block ID, nhờ đó giảm số lần gọi sequence. Cần bảo đảm cấu hình sequence vật lý trên database tương thích với allocationSize và optimizer mà phiên bản Hibernate sử dụng. Nếu tự tạo sequence bằng DDL, hãy kiểm tra giá trị INCREMENT BY và cấu hình mapping theo đúng hướng dẫn của provider; không tự ý thay đổi increment mà chưa kiểm tra.

Sequence allocation có thể tạo khoảng trống trong dãy ID do rollback, block đã cấp nhưng chưa dùng hết, cache của database hoặc ứng dụng dừng giữa chừng. ID sinh tự động không phải số thứ tự nghiệp vụ liên tục và không nên dùng để bảo đảm không có khoảng trống.

## 4. So sánh IDENTITY và SEQUENCE đối với batching

| Tiêu chí | IDENTITY | SEQUENCE |
|---|---|---|
| Thời điểm có ID | Sau khi database thực hiện INSERT | Trước INSERT, sau khi lấy sequence value |
| Cách sinh ID | Database sinh từ cột identity/auto-increment | Database cấp từ sequence |
| Insert batching trong Hibernate | Bị vô hiệu hóa cho entity dùng IDENTITY | Có thể gom INSERT vào JDBC batch |
| Cấp phát trước nhiều ID | Không theo cơ chế sequence allocation | Có thể dùng allocationSize/optimizer |
| Khả năng phụ thuộc database | Cần kiểu cột identity hoặc tương đương | Database phải hỗ trợ sequence và provider phải hỗ trợ |
| Tình huống phù hợp | Schema đơn giản, lượng insert vừa phải, ưu tiên auto-increment | Import nhiều bản ghi, insert throughput quan trọng, database hỗ trợ sequence |

Ví dụ, một service import 10.000 entity dùng IDENTITY có thể phải gửi từng INSERT riêng lẻ qua Hibernate. Nếu entity dùng SEQUENCE và cấu hình batching đúng, Hibernate có thể gửi các nhóm INSERT bằng JDBC batch. Kết quả thực tế còn phụ thuộc driver, network, index, constraint, transaction và tải database; không thể suy ra tốc độ tăng theo một tỷ lệ cố định chỉ từ chiến lược ID.

**Kết luận kỹ thuật:** trong Hibernate, SEQUENCE thường là lựa chọn thuận lợi hơn cho workload insert số lượng lớn vì ID được biết trước khi INSERT. IDENTITY vẫn có thể là lựa chọn phù hợp khi yêu cầu schema hoặc workload không cần insert batching.

## 5. Bật JDBC batching trong Spring Boot

Khi dùng Spring Boot với Hibernate, có thể cấu hình trong application.properties:

~~~properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
~~~

Ý nghĩa:

- hibernate.jdbc.batch_size: số lệnh JDBC tối đa Hibernate gom vào một batch. Giá trị 50 chỉ là điểm bắt đầu để đo thử, không phải con số tối ưu cho mọi hệ thống.
- hibernate.order_inserts: yêu cầu Hibernate sắp xếp các thao tác INSERT để các lệnh cùng loại có cơ hội nằm cạnh nhau và tạo batch tốt hơn.
- hibernate.order_updates: sắp xếp thao tác UPDATE để tăng khả năng gom batch và có thể giúp giảm một số xung đột khóa theo thứ tự nhất quán.

Sắp xếp thao tác có chi phí riêng, vì vậy nên benchmark trước và sau khi bật. Các lệnh khác nhau về bảng, cột hoặc hình dạng SQL không nhất thiết gom chung được vào một batch.

Cấu hình batch_size không tự đảm bảo batching đã xảy ra. Nếu entity dùng IDENTITY, giới hạn insert batching vẫn tồn tại trong Hibernate. Nếu transaction flush quá sớm, câu lệnh không cùng nhóm hoặc driver có hành vi đặc biệt, batch thực tế có thể nhỏ hơn mong đợi.

### 5.1. Cấu hình driver

Một số JDBC driver có tùy chọn tối ưu batch riêng. Ví dụ, PostgreSQL JDBC có tùy chọn reWriteBatchedInserts; MySQL Connector/J có rewriteBatchedStatements. Các tùy chọn này có thể giúp driver chuyển đổi hoặc tối ưu cách gửi batch, nhưng cú pháp, mặc định và hiệu quả phụ thuộc phiên bản driver.

Đây là bước tối ưu bổ sung. Trước tiên cần xác nhận Hibernate thật sự gọi JDBC batch; sau đó mới thử tùy chọn driver và đo lại. Không sao chép tùy chọn của một driver sang database khác.

## 6. Ví dụ lưu nhiều entity theo từng nhóm

Giả sử entity mới dùng SEQUENCE và repository kế thừa JpaRepository:

~~~java
import java.util.List;

import jakarta.persistence.EntityManager;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderImportService {
    private static final int CHUNK_SIZE = 50;

    private final PurchaseOrderRepository repository;
    private final EntityManager entityManager;

    public OrderImportService(
            PurchaseOrderRepository repository,
            EntityManager entityManager) {
        this.repository = repository;
        this.entityManager = entityManager;
    }

    @Transactional
    public void importOrders(List<PurchaseOrder> orders) {
        for (int start = 0; start < orders.size(); start += CHUNK_SIZE) {
            int end = Math.min(start + CHUNK_SIZE, orders.size());
            List<PurchaseOrder> chunk = orders.subList(start, end);

            repository.saveAll(chunk);

            entityManager.flush();
            entityManager.clear();
        }
    }
}
~~~

Ví dụ giả định các đối tượng trong danh sách đều là entity mới, repository đã được khai báo và mapping identifier dùng SEQUENCE. Phương thức import chạy trong một transaction của service; các lời gọi saveAll tham gia transaction đó theo propagation mặc định.

- saveAll() lưu các entity vào persistence context. Bản thân saveAll() chủ yếu lặp qua các entity và gọi cơ chế save; tên phương thức không bảo đảm database nhận một câu INSERT hàng loạt.
- flush() yêu cầu EntityManager đồng bộ các thay đổi đang chờ xuống database. Hibernate có thể gửi các INSERT đã đủ điều kiện bằng JDBC batch.
- clear() xóa toàn bộ entity đang được quản lý khỏi persistence context, giúp giới hạn bộ nhớ khi import lượng lớn. Các entity sau đó trở thành detached.

Phải flush trước clear để không làm mất các thay đổi còn đang chờ đồng bộ. Sau clear, không nên tiếp tục giả định các entity cũ vẫn được quản lý hoặc các thay đổi tiếp theo trên chúng sẽ tự động được lưu.

CHUNK_SIZE trong ví dụ là kích thước nhóm xử lý ở tầng ứng dụng; hibernate.jdbc.batch_size là kích thước JDBC batch. Hai giá trị có thể bằng nhau để dễ theo dõi, nhưng không bắt buộc phải giống nhau.

### 6.1. Flush và commit khác nhau

flush() đẩy SQL xuống database trong transaction hiện tại, nhưng không commit transaction. Các thay đổi vẫn có thể rollback cho đến khi transaction commit.

Nếu toàn bộ import nằm trong một transaction, việc flush và clear theo nhóm giúp giảm lượng entity giữ trong persistence context, nhưng không làm transaction ngắn hơn. Khóa database, log transaction và phạm vi rollback vẫn có thể kéo dài đến cuối import.

Nếu cần commit từng nhóm để giới hạn thời gian transaction, phải thiết kế ranh giới transaction riêng cho từng nhóm. Cách này thay đổi tính nguyên tử: nhóm trước có thể đã commit dù nhóm sau thất bại. Không nên thêm REQUIRES_NEW hoặc gọi transaction nội bộ một cách tùy tiện; cần thiết kế rõ cách xử lý lỗi, retry và dữ liệu đã commit.

## 7. saveAll(), saveAllAndFlush() và JDBC batch

Các phương thức repository thường bị hiểu nhầm:

- **saveAll(entities):** lưu từng entity thông qua cơ chế save của Spring Data JPA. Nó không tự biến danh sách thành một câu SQL multi-row INSERT và cũng không bảo đảm JDBC batch.
- **saveAllAndFlush(entities):** gọi lưu danh sách rồi flush persistence context. Flush có thể khiến Hibernate thực thi JDBC batch nếu cấu hình và identifier strategy cho phép.
- **EntityManager.persist(entity):** đánh dấu entity mới để persistence provider quản lý. Đây là API JPA trực tiếp; dùng persist trong vòng lặp không tự bảo đảm batching nếu provider hoặc ID strategy không hỗ trợ.

Spring Data JPA xác định entity mới hay đã tồn tại để chọn persist hoặc merge. Nếu entity bị nhận diện là đã tồn tại, merge có thể phát sinh SELECT hoặc xử lý khác với đường persist cho entity mới. Khi tối ưu import, hãy kiểm tra trạng thái entity và cách Spring Data xác định isNew.

Nếu cần cập nhật nhiều hàng theo cùng một điều kiện, JPQL bulk UPDATE hoặc DELETE có thể phù hợp hơn batching các entity. Tuy nhiên bulk DML có ngữ nghĩa khác: nó thực thi trực tiếp ở database, không cập nhật từng entity đang nằm trong persistence context và có thể bỏ qua lifecycle callback hoặc cơ chế version theo cách thao tác entity thông thường. Cần đồng bộ hoặc clear persistence context phù hợp sau bulk DML.

## 8. Những yếu tố khác ảnh hưởng đến batching

Ngoài IDENTITY và SEQUENCE, hãy kiểm tra các yếu tố sau:

1. **Transaction boundary:** Các thao tác phải nằm trong transaction phù hợp. Gọi từng repository method trong nhiều transaction nhỏ có thể làm mất cơ hội gom các lệnh vào cùng batch.
2. **Flush mode và thời điểm flush:** Hibernate có thể flush trước một số truy vấn hoặc khi transaction commit. Flush quá thường xuyên làm batch nhỏ lại.
3. **Cùng hình dạng SQL:** Hibernate chỉ gom được các lệnh tương thích về câu SQL. Entity khác loại hoặc câu INSERT có tập cột khác nhau có thể thuộc các batch khác nhau.
4. **Thứ tự thao tác:** order_inserts và order_updates có thể cải thiện việc nhóm lệnh. Quan hệ khóa ngoại và thứ tự phụ thuộc dữ liệu vẫn phải được provider xử lý hợp lệ.
5. **Optimistic locking:** Entity dùng @Version có thể được UPDATE kèm điều kiện version. Việc batch các UPDATE có version phụ thuộc khả năng driver trả update count chính xác và cấu hình Hibernate tương ứng. Hãy kiểm tra phiên bản provider và driver trước khi thay đổi tùy chọn batch cho versioned data.
6. **Driver và database:** Giới hạn kích thước packet, tham số, khả năng batch rewrite và cách driver triển khai executeBatch có thể ảnh hưởng hiệu năng.
7. **Index và constraint:** Database vẫn phải duy trì index, kiểm tra khóa ngoại và constraint cho từng bản ghi. Batching giảm chi phí giao tiếp nhưng không loại bỏ chi phí này.
8. **Kích thước persistence context:** Giữ hàng chục nghìn entity managed cùng lúc có thể tiêu tốn nhiều bộ nhớ. Dùng flush/clear theo nhóm khi cần, đồng thời hiểu tác động của clear đến các entity đang được quản lý.

Không nên chọn batch size quá lớn ngay từ đầu. Batch quá lớn có thể tăng bộ nhớ phía ứng dụng/driver, kích thước request và thời gian xử lý một lần. Hãy đo với dữ liệu và tải gần production, thử nhiều mức hợp lý như 20, 50 hoặc 100 rồi chọn theo kết quả.

## 9. Kiểm tra batching có thực sự hoạt động

Để xác minh, không chỉ nhìn vào số lần gọi save() hoặc saveAll(). Cần quan sát việc Hibernate gửi batch qua JDBC.

Quy trình kiểm tra gợi ý:

1. Dùng cùng một database engine và JDBC driver với môi trường triển khai. Testcontainers giúp integration test chạy trên database thật thay vì chỉ dựa vào H2.
2. Tạo một lượng entity đủ lớn, ví dụ vài trăm bản ghi, và thực hiện trong một transaction.
3. Thử riêng mapping IDENTITY và SEQUENCE, giữ các điều kiện còn lại tương đương.
4. Bật cấu hình hibernate.jdbc.batch_size và kiểm tra log/metrics của Hibernate, JDBC driver hoặc datasource proxy để thấy các lần executeBatch.
5. So sánh số batch, số lần round trip, thời gian, lượng bộ nhớ và kết quả dữ liệu.
6. Kiểm tra thêm rollback, lỗi constraint và quan hệ khóa ngoại để chắc chắn tối ưu không làm thay đổi tính đúng đắn.

Có thể bật Hibernate statistics trong môi trường kiểm thử:

~~~properties
spring.jpa.properties.hibernate.generate_statistics=true
~~~

Statistics và log giúp quan sát hoạt động ORM; để xác nhận chính xác JDBC batch, có thể dùng datasource proxy hoặc công cụ quan sát JDBC có hiển thị executeBatch. Log SQL đơn thuần có thể in từng câu INSERT riêng biệt dù driver đã nhận chúng qua batch, vì vậy cần xem đúng lớp đo lường.

Một phép đo nên so sánh ít nhất ba trường hợp: IDENTITY với batching bật, SEQUENCE với batch_size bằng 1, và SEQUENCE với batch_size lớn hơn 1. Cách so sánh này giúp tách ảnh hưởng của identifier generation khỏi lợi ích của JDBC batching.

## 10. Khả năng hỗ trợ theo database và cách chọn chiến lược

Khả năng dùng SEQUENCE phụ thuộc hệ quản trị cơ sở dữ liệu:

| Database | Sequence và identity | Lưu ý |
|---|---|---|
| PostgreSQL | Hỗ trợ sequence và identity column | SEQUENCE là lựa chọn tự nhiên cho Hibernate insert batching; cần cấu hình sequence/optimizer phù hợp. |
| Oracle Database | Hỗ trợ sequence | Sequence thường được dùng để cấp ID trước INSERT; có thể kết hợp JDBC batching. |
| Microsoft SQL Server | Hỗ trợ sequence và IDENTITY | Có thể chọn sequence object nếu schema và ứng dụng cho phép. |
| MySQL | Dùng AUTO_INCREMENT; không có sequence object native | IDENTITY/AUTO_INCREMENT là lựa chọn phổ biến; không giả định GenerationType.SEQUENCE có cùng khả năng như PostgreSQL hoặc Oracle. |

Cách chọn:

- **Chọn IDENTITY** nếu schema hiện tại dùng auto-increment, lượng insert không lớn hoặc sự đơn giản quan trọng hơn insert throughput. Chấp nhận rằng Hibernate thường không batch INSERT cho entity IDENTITY.
- **Chọn SEQUENCE** nếu database hỗ trợ sequence và ứng dụng thường insert nhiều entity. Kết hợp allocationSize phù hợp với optimizer để giảm số lần lấy ID và bật JDBC batching để gom INSERT.
- **Đừng dựa vào AUTO khi cần hành vi hiệu năng dự đoán được:** provider có thể chọn chiến lược khác nhau tùy database và dialect. Với workload nhạy cảm, khai báo rõ chiến lược và kiểm tra schema.
- **Đo trên database đích:** không kết luận chỉ từ unit test hoặc H2, vì cách sinh ID, locking, sequence và batching phụ thuộc engine/driver.
- **Giữ tính đúng đắn của transaction:** tối ưu batch không được làm mất kiểm soát rollback, khóa ngoại, optimistic locking hay trạng thái persistence context.

Khi import dữ liệu lớn bằng Spring Data JPA và Hibernate, lựa chọn SEQUENCE thường tạo điều kiện tốt hơn cho JDBC insert batching vì ID có trước khi INSERT. Tuy nhiên hiệu quả cuối cùng chỉ xuất hiện khi identifier generator, batch size, transaction, flush/clear và JDBC driver được cấu hình đồng bộ và được đo kiểm trong môi trường gần production.