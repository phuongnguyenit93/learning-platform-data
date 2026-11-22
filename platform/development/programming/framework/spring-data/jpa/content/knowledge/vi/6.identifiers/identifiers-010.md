# Tác động của chiến lược sinh khóa đến nhập dữ liệu theo lô

## 1. Vì sao chiến lược sinh khóa ảnh hưởng đến batch insert

Khi Hibernate lưu nhiều entity, JDBC batching cho phép gom nhiều lần thực thi cùng một câu lệnh `INSERT` vào một batch. Thay vì gửi từng lệnh riêng lẻ qua mạng tới database, ứng dụng chuẩn bị các tham số cho nhiều bản ghi rồi gọi `executeBatch()`. Điều này giảm số lần trao đổi giữa ứng dụng và database, đặc biệt hữu ích khi nhập dữ liệu số lượng lớn.

Khả năng gom lệnh phụ thuộc vào thời điểm Hibernate lấy được khóa chính. Nếu database chỉ trả về ID sau khi thực hiện `INSERT`, Hibernate có thể phải gửi từng câu lệnh ngay lập tức để lấy ID. Khi ID đã có trước lúc insert, Hibernate có thể xếp nhiều câu lệnh vào batch. Vì vậy, `GenerationType.IDENTITY`, `SEQUENCE`, `TABLE`, UUID và khóa do ứng dụng cấp có thể cho hiệu năng nhập dữ liệu rất khác nhau.

## 2. So sánh các chiến lược sinh khóa

| Chiến lược | Khi có ID | Khả năng JDBC batch insert với Hibernate | Điểm cần cân nhắc |
| --- | --- | --- | --- |
| `IDENTITY` | Sau khi database insert bản ghi | Hibernate không batch insert cho entity dùng IDENTITY | Đơn giản, nhưng mỗi insert cần lấy generated key ngay |
| `SEQUENCE` | Lấy từ sequence trước khi insert | Có thể batch insert | Hiệu quả khi cấp trước một nhóm ID; cần cấu hình sequence phù hợp |
| `TABLE` | Lấy từ bảng quản lý khóa trước khi insert | Có thể batch insert | Bảng generator có thể gây tranh chấp khóa và thêm thao tác đọc/cập nhật |
| `UUID` | Tạo ở phía ứng dụng/provider trước khi insert | Có thể batch insert | Không cần lấy ID từ database; UUID chiếm nhiều byte hơn khóa số và có thể ảnh hưởng locality của index |
| Khóa tự gán | Ứng dụng cấp trước khi persist | Có thể batch insert | Ứng dụng phải đảm bảo tính duy nhất và cách phát hành khóa an toàn |

Với Hibernate ORM 6, entity dùng `IDENTITY` không tham gia JDBC insert batching vì Hibernate cần thực hiện insert để lấy khóa do database sinh. Các chiến lược biết ID trước khi insert như sequence hoặc UUID có thể tận dụng batching nếu phần cấu hình JDBC và transaction cũng phù hợp.

`GenerationType.AUTO` không đảm bảo một chiến lược cụ thể. JPA provider lựa chọn generator theo dialect, phiên bản và cấu hình. Hãy kiểm tra mapping và DDL thực tế thay vì mặc định rằng `AUTO` sẽ dùng sequence.

## 3. IDENTITY: thuận tiện nhưng hạn chế batching

Ví dụ:

```java
@Entity
@Table(name = "customer")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;
}
```

Với IDENTITY, database tạo ID khi nhận câu `INSERT`. Hibernate cần ID để quản lý entity đã được persist và xử lý các quan hệ phụ thuộc, nên phải thực thi insert sớm để đọc generated key. Hibernate không thể gom các insert IDENTITY theo JDBC batch thông thường.

Điều này không có nghĩa IDENTITY luôn chậm hoặc không nên dùng. Với ứng dụng ghi ít, database hỗ trợ identity tốt và luồng nhập không lớn, sự đơn giản có thể quan trọng hơn batching. Nhưng với import hàng chục nghìn bản ghi, đây là giới hạn hiệu năng cần tính đến.

Không nên kỳ vọng chỉ thêm `hibernate.jdbc.batch_size` là khắc phục được giới hạn này. Cần đổi chiến lược sinh khóa nếu mục tiêu là JDBC batch insert với Hibernate.

## 4. SEQUENCE: lựa chọn phổ biến cho batch insert

Sequence cấp ID độc lập với thao tác insert. Hibernate có thể lấy trước một ID hoặc một dải ID, sau đó xếp nhiều lệnh insert vào JDBC batch.

Ví dụ:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.SequenceGenerator;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE, generator = "customer_id_generator")
    @SequenceGenerator(
        name = "customer_id_generator",
        sequenceName = "customer_seq",
        allocationSize = 50
    )
    private Long id;

    @Column(nullable = false)
    private String name;
}
```

`name` là tên generator trong mapping JPA; `sequenceName` là tên sequence trong database. `allocationSize = 50` cho Hibernate biết kích thước cấp phát ID theo nhóm. Hibernate có thể dùng pooled optimizer để giảm số lần gọi sequence khi nhập nhiều bản ghi.

Nếu quản lý DDL bằng Flyway hoặc Liquibase, hãy tạo sequence với cấu hình increment phù hợp với allocation size và optimizer mà Hibernate sử dụng. Ví dụ cho database hỗ trợ sequence:

```sql
CREATE SEQUENCE customer_seq
    START WITH 1
    INCREMENT BY 50;
```

Không sao chép máy móc `INCREMENT BY 50` sang mọi cấu hình. Hãy bảo đảm sequence increment, `allocationSize`, optimizer và cấu hình kiểm tra mismatch của Hibernate thống nhất. Nếu không, Hibernate có thể báo lỗi khi khởi động hoặc việc cấp ID có thể không đúng như dự kiến. Với schema do Hibernate tạo trong môi trường phát triển, kiểm tra DDL được sinh ra để hiểu cấu hình thực tế.

Sequence thường là lựa chọn tốt khi database hỗ trợ sequence và cần nhập dữ liệu theo lô. Đổi từ IDENTITY sang SEQUENCE cần migration schema, kiểm tra dữ liệu hiện có, sequence hiện tại và cách cấp ID trong tất cả các ứng dụng cùng ghi vào bảng.

## 5. TABLE và UUID

### TABLE generator

`GenerationType.TABLE` dùng một bảng riêng để lưu trạng thái cấp ID. Vì generator cần đọc/cập nhật hàng trong bảng đó, nó có thể tạo thêm round-trip và tranh chấp khóa khi nhiều transaction đồng thời cấp ID. Allocation size có thể giảm số lần truy cập generator, nhưng bảng generator vẫn có thể trở thành điểm nóng.

TABLE vẫn biết ID trước khi insert entity nên không chịu giới hạn batching giống IDENTITY. Tuy nhiên, với hệ thống có tải ghi cao, sequence hoặc ID do ứng dụng tạo thường dễ mở rộng hơn. Chỉ chọn TABLE khi có lý do tương thích hoặc yêu cầu cụ thể.

### UUID

Với Jakarta Persistence 3.1 và Hibernate 6, có thể dùng UUID generator:

```java
@Entity
@Table(name = "customer")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    private String name;
}
```

UUID được tạo trước khi insert nên Hibernate có thể batch các câu lệnh. Không cần round-trip tới database chỉ để lấy ID. Đổi lại, UUID thường lớn hơn khóa số và UUID ngẫu nhiên có thể làm các index dạng B-tree kém locality hơn so với khóa tăng dần. Hãy cân nhắc kiểu cột, kích thước index, khả năng sắp xếp và yêu cầu sinh ID giữa nhiều node.

Khóa tự gán như UUID/ULID do ứng dụng tạo cũng có lợi thế biết trước ID. Tuy nhiên, phải bảo đảm generator có chất lượng, không trùng khóa và hoạt động an toàn khi nhiều instance chạy đồng thời.

## 6. Bật JDBC batching trong Spring Boot

Chiến lược ID chỉ là một phần. Cần cấu hình Hibernate để bật JDBC batch:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        jdbc:
          batch_size: 50
          batch_versioned_data: true
        order_inserts: true
        order_updates: true
```

- `hibernate.jdbc.batch_size` là số statement tối đa Hibernate gom vào một batch. Bắt đầu thử với 25 hoặc 50, sau đó đo theo driver, database, kích thước bản ghi và tải thực tế.
- `hibernate.order_inserts` sắp xếp insert theo entity/table để các câu lệnh cùng dạng có cơ hội nằm cạnh nhau và được batch.
- `hibernate.order_updates` sắp xếp update, có thể tăng khả năng batching update và giảm một số deadlock trong workload phù hợp.
- `hibernate.jdbc.batch_versioned_data` cho phép batching các thao tác trên entity có version khi driver trả về số hàng cập nhật đáng tin cậy theo yêu cầu Hibernate.

Batch size 50 không có nghĩa database chắc chắn nhận một câu SQL duy nhất chứa 50 bộ giá trị. JDBC batching thường gửi cùng prepared statement nhiều lần qua `addBatch()`/`executeBatch()`. Một số driver có tùy chọn rewrite batch thành multi-row insert; đây là tối ưu riêng của driver và cần kiểm tra tài liệu của database đang dùng.

`@BatchSize` hoặc `hibernate.default_batch_fetch_size` liên quan đến batch fetching khi đọc quan hệ, không thay thế `hibernate.jdbc.batch_size` cho insert.

## 7. Nhập dữ liệu theo lô với flush và clear

Ví dụ dùng `EntityManager` và sequence generator:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.List;

@Service
public class CustomerImportService {
    private static final int BATCH_SIZE = 50;

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void importCustomers(List<Customer> customers) {
        for (int i = 0; i < customers.size(); i++) {
            entityManager.persist(customers.get(i));

            if ((i + 1) % BATCH_SIZE == 0) {
                entityManager.flush();
                entityManager.clear();
            }
        }
    }
}
```

`flush()` đồng bộ các thay đổi đang chờ với database; Hibernate có cơ hội thực thi JDBC batch tại thời điểm này. `clear()` giải phóng các entity khỏi persistence context, tránh giữ hàng chục nghìn đối tượng managed trong bộ nhớ. Khi vòng lặp kết thúc, transaction commit sẽ flush phần còn lại chưa đủ một batch.

Ví dụ trên vẫn dùng một transaction cho toàn bộ phương thức. Nếu import rất lớn và cần commit từng phần để giới hạn thời gian transaction, phải thiết kế ranh giới transaction riêng cho từng chunk và quyết định rõ cách xử lý lỗi/rollback. Chỉ gọi `flush()` không commit transaction.

Không tiếp tục dùng các entity đã bị `clear()` như thể chúng vẫn managed. Nếu cần cập nhật một entity sau khi clear, phải tải lại hoặc merge theo đúng quy tắc vòng đời entity.

## 8. saveAll không đồng nghĩa với một câu INSERT

`JpaRepository.saveAll()` thường lặp qua các entity và gọi `save()` cho từng phần tử. Nó không tự tạo một câu `INSERT` nhiều dòng và cũng không bảo đảm JDBC batching đã được bật. Khi transaction, generator và Hibernate config phù hợp, các lệnh do `saveAll()` tạo ra vẫn có thể được Hibernate gom batch.

`saveAllAndFlush()` gọi flush sau khi lưu danh sách, nhưng không biến các lệnh thành một câu SQL duy nhất. Với import rất lớn, vòng lặp `persist` kết hợp `flush/clear` theo chunk giúp kiểm soát persistence context rõ hơn. Chú ý entity mới và entity detached có thể đi qua các nhánh persist/merge khác nhau trong `save()`.

## 9. Điều kiện để batch thực sự hoạt động

- Các entity phải được ghi trong cùng transaction đủ dài để Hibernate tích lũy statement.
- Phải dùng generator cho phép biết ID trước insert; với Hibernate 6, IDENTITY chặn JDBC insert batching.
- Các insert phải có SQL shape tương thích. Nhiều loại entity hoặc câu insert có tập cột khác nhau sẽ được batch riêng.
- Bật `hibernate.jdbc.batch_size` với giá trị lớn hơn 0.
- Driver JDBC và database phải hỗ trợ batching đúng cách; kiểm tra giới hạn, lỗi và hành vi generated key của driver.
- Dùng `flush/clear` theo chunk cho import lớn để giới hạn bộ nhớ persistence context.
- Kiểm tra các trigger, cascade, association và callback có tạo thêm câu SQL hoặc làm thay đổi thứ tự ghi hay không.

Batching giảm chi phí giao tiếp nhưng không loại bỏ chi phí index, constraint, trigger, ghi log transaction hoặc kiểm tra dữ liệu ở database. Tăng batch size quá lớn có thể làm tăng bộ nhớ, thời gian giữ lock và kích thước transaction.

## 10. Cách đo và chẩn đoán

Không kết luận batching thành công chỉ vì đã đặt `batch_size`. Hãy so sánh cùng một bộ dữ liệu trên cùng database, cùng cấu hình connection pool và cùng kích thước transaction.

1. Ghi nhận thời gian nhập, số bản ghi mỗi giây, CPU, bộ nhớ và tải database.
2. Xác nhận SQL insert thực tế và ID generator mà Hibernate đang dùng.
3. Dùng log JDBC, datasource proxy hoặc công cụ quan sát driver để xác nhận có lời gọi batch `executeBatch()` và kích thước batch.
4. So sánh IDENTITY với SEQUENCE/UUID khi database hỗ trợ, giữ nguyên các yếu tố khác.
5. Thử nhiều batch size như 25, 50 và 100; chọn theo số liệu thay vì chọn giá trị lớn nhất.
6. Đo riêng chi phí lấy sequence, insert, flush và commit nếu import vẫn chậm.

`org.hibernate.SQL` giúp xem câu SQL được tạo nhưng chỉ nhìn thấy nhiều dòng insert trong log chưa chứng minh JDBC batch đã được gửi. Dùng công cụ quan sát ở tầng JDBC/driver để xác nhận batching. Có thể bật Hibernate statistics trong môi trường thử nghiệm để bổ sung số liệu, nhưng tránh bật thống kê hoặc log chi tiết thường trực nếu chúng tạo overhead.

## 11. Chọn chiến lược theo tình huống

| Tình huống | Hướng cân nhắc |
| --- | --- |
| Database hỗ trợ sequence, cần nhập nhiều bản ghi | `SEQUENCE` với allocation phù hợp và JDBC batching |
| Ứng dụng nhỏ, ghi ít, đang dùng identity | Giữ `IDENTITY` nếu sự đơn giản quan trọng hơn throughput batch |
| Cần ID sinh độc lập giữa nhiều node | UUID/ULID được tạo trước insert; đánh giá kích thước và locality index |
| Phải tích hợp schema legacy | Dùng generator/schema hiện có; đo tác động của TABLE hoặc cơ chế cấp ID hiện tại |
| Import hàng trăm nghìn bản ghi | Sequence/UUID, JDBC batching, chunk `flush/clear`, transaction có ranh giới phù hợp |

## 12. Checklist trước khi triển khai

- Xác định database, JDBC driver, Hibernate version và chiến lược ID thực tế.
- Kiểm tra IDENTITY có đang ngăn JDBC insert batching hay không.
- Nếu dùng SEQUENCE, đồng bộ `allocationSize`, optimizer và DDL sequence.
- Bật `hibernate.jdbc.batch_size` và cân nhắc `order_inserts`.
- Dùng transaction phù hợp; với import lớn, flush/clear theo chunk.
- Đo bằng công cụ JDBC/driver và so sánh throughput trên dữ liệu đại diện.
- Kiểm tra tính đúng đắn của ID, rollback, constraint, cascade và xử lý lỗi khi một chunk thất bại.

Chiến lược sinh khóa quyết định Hibernate có thể chuẩn bị ID trước insert hay phải chờ database trả ID sau insert. Với luồng nhập dữ liệu lớn, SEQUENCE được cấp phát theo nhóm hoặc UUID thường tạo điều kiện tốt cho JDBC batching; kết quả cuối cùng vẫn cần được xác nhận bằng đo đạc trên database và driver thực tế.