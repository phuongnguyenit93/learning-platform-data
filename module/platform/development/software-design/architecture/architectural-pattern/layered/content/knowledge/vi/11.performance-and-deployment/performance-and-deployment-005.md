# Tối ưu thao tác theo lô và thời gian giữ giao dịch

> Chương: **Hiệu năng và triển khai**

Trong module **SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED**, chúng ta học cách tổ chức phần mềm theo kiến trúc phân tầng. Khi xử lý nhiều bản ghi, một thiết kế tốt cần cân bằng số lần giao tiếp với database, lượng dữ liệu giữ trong bộ nhớ và thời gian một giao dịch tồn tại. Bài này tập trung vào hai kỹ thuật có liên quan nhưng khác mục tiêu: **batching** để giảm chi phí của nhiều thao tác lặp lại, và **giới hạn thời gian giữ giao dịch** để giảm thời gian chiếm dụng connection, khóa và tài nguyên database.

Batch lớn không đồng nghĩa với giao dịch dài. Có thể gom nhiều câu lệnh vào một batch JDBC nhưng vẫn chia công việc thành các giao dịch theo chunk. Ngược lại, một giao dịch duy nhất có thể chứa hàng nghìn thao tác dù mỗi câu SQL được gửi riêng lẻ. Cần thiết kế cả kích thước batch lẫn ranh giới commit theo yêu cầu nhất quán của nghiệp vụ.

## 1. Vì sao thao tác từng bản ghi gây tốn kém?

Giả sử một tác vụ nhập 10.000 dòng dữ liệu. Nếu mỗi dòng được lưu bằng một lần gọi repository và mỗi lần gọi tạo một round trip tới database, ứng dụng phải chịu nhiều lần chuyển dữ liệu qua mạng, xử lý giao thức, parse/execute câu lệnh và điều phối transaction. Chi phí cố định của từng lần gọi có thể lớn hơn đáng kể so với phần công việc thực tế trên một hàng.

Một vòng lặp đơn giản như sau có thể hoạt động đúng nhưng không nhất thiết hiệu quả:

```java
for (ImportRow row : rows) {
    repository.save(mapToEntity(row));
}
```

Nếu `save` phát sinh một câu lệnh riêng cho mỗi đối tượng, 10.000 dòng có thể tạo ra rất nhiều lần trao đổi với database. Nếu tất cả nằm trong một transaction, thời gian giao dịch còn kéo dài cho tới khi toàn bộ vòng lặp hoàn tất.

Các vấn đề thường gặp gồm:

- Nhiều round trip và lần parse/execute câu lệnh nhỏ.
- ORM giữ quá nhiều entity trong persistence context, làm tăng bộ nhớ và chi phí dirty checking.
- Một transaction dài giữ connection lâu; các thao tác ghi có thể giữ khóa tới khi commit.
- Khi lỗi xảy ra gần cuối, rollback một khối lượng lớn công việc có thể tốn thời gian.
- Các request khác phải chờ tài nguyên hoặc khóa, khiến độ trễ toàn hệ thống tăng.

Batching giảm số lần gửi thao tác lặp lại. Chia chunk và transaction ngắn hơn kiểm soát lượng công việc được commit cùng nhau. Hai kỹ thuật thường được dùng phối hợp.

## 2. Batch là gì và giảm chi phí ở đâu?

**Batching** là gom nhiều thao tác tương tự thành một nhóm để gửi hoặc thực hiện cùng nhau. Với JDBC, thay vì gọi `executeUpdate()` cho từng bản ghi, ứng dụng có thể thêm nhiều bộ tham số vào một `PreparedStatement` rồi gọi `executeBatch()`.

Ví dụ JDBC:

```java
String sql = """
    insert into product_snapshot(product_id, quantity, captured_at)
    values (?, ?, ?)
    """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    int pending = 0;

    for (ProductSnapshot snapshot : snapshots) {
        statement.setObject(1, snapshot.productId());
        statement.setInt(2, snapshot.quantity());
        statement.setTimestamp(3, Timestamp.from(snapshot.capturedAt()));
        statement.addBatch();

        if (++pending == 100) {
            statement.executeBatch();
            statement.clearBatch();
            pending = 0;
        }
    }

    if (pending > 0) {
        statement.executeBatch();
    }
}
```

Đoạn mã minh họa gom tối đa 100 bộ tham số cho mỗi lần `executeBatch()`. Trong ứng dụng thực tế, connection và transaction cần được quản lý bởi transaction manager hoặc cơ chế truy cập dữ liệu của dự án; ví dụ trên lược bỏ phần quản lý đó để tập trung vào batching.

Batching có thể giảm số lần gửi lệnh từ ứng dụng tới database, nhưng không có nghĩa database chỉ thực hiện một thao tác nội bộ. Database vẫn phải kiểm tra constraint, cập nhật index, ghi log và xử lý từng hàng theo ngữ nghĩa của câu lệnh. Lợi ích thực tế phụ thuộc driver, database, kích thước batch, loại câu lệnh và dữ liệu.

## 3. Chọn kích thước batch và chunk

Hai tham số thường được nhắc tới:

- **Batch size:** số thao tác được gom trong một lần gửi batch tới database hoặc một lần flush của ORM.
- **Chunk size:** số bản ghi được xử lý trong một đơn vị công việc, thường là phạm vi một transaction rồi commit.

Ví dụ, một chunk có 500 bản ghi có thể được gửi thành 10 batch, mỗi batch 50 câu lệnh. Khi chunk hoàn tất, transaction commit. Batch size và chunk size không cần bằng nhau.

Không có một con số tối ưu cho mọi hệ thống. Batch quá nhỏ làm giảm lợi ích gom lệnh; batch quá lớn có thể tăng bộ nhớ, tạo gói dữ liệu lớn, giữ tài nguyên lâu hơn hoặc làm lỗi khó khoanh vùng. Chunk quá nhỏ làm tăng số lần commit và overhead transaction; chunk quá lớn làm giao dịch kéo dài và tăng lượng công việc phải rollback khi lỗi.

Hãy bắt đầu bằng một kích thước vừa phải, đo thời gian xử lý, lượng bộ nhớ, số round trip, lock wait và tỷ lệ lỗi. Thử tăng hoặc giảm batch/chunk trên dữ liệu gần thực tế để tìm điểm cân bằng. Đừng chọn kích thước chỉ dựa trên số dòng của một file mẫu nhỏ.

## 4. Batch insert và update với JPA/Hibernate

Hibernate có thể gom các lệnh insert/update thành JDBC batch. Có thể cấu hình các thuộc tính sau trong Spring Boot:

```properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
```

- `hibernate.jdbc.batch_size` đặt số câu lệnh tối đa mà Hibernate gom trong một batch.
- `hibernate.order_inserts` và `hibernate.order_updates` yêu cầu Hibernate sắp xếp thao tác theo loại/entity để có thêm cơ hội gom các câu lệnh tương thích.

Các thuộc tính này bật khả năng batching ở Hibernate; chúng không bảo đảm mọi thao tác sẽ được gom. Cần kiểm tra SQL log hoặc thống kê Hibernate để xác nhận driver và mapping thực tế có tạo batch hay không.

### Lưu nhiều entity không có nghĩa tự động có JDBC batch

`JpaRepository.saveAll(...)` là API lưu một tập entity, nhưng bản thân tên method không bảo đảm một JDBC batch duy nhất. Cách triển khai, cấu hình Hibernate, chiến lược sinh ID và trạng thái entity đều ảnh hưởng số câu lệnh được gửi. Hãy đo SQL thực tế thay vì suy ra hiệu năng từ tên method.

Một điểm cần chú ý là chiến lược sinh khóa `IDENTITY` thường ngăn Hibernate gom insert theo JDBC batch, vì Hibernate cần thực hiện insert để lấy ID được database sinh. Với khối lượng insert lớn, chiến lược ID phù hợp và hỗ trợ của database/provider cần được cân nhắc từ đầu.

### Giới hạn persistence context bằng flush và clear

Khi persist hàng nghìn entity trong một transaction, Hibernate có thể giữ chúng trong persistence context cho tới khi flush/clear. Điều này làm tăng bộ nhớ và thời gian xử lý dirty checking. Có thể flush và clear theo nhịp:

```java
@Service
public class ProductChunkWriter {
    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void writeChunk(List<ProductImportRow> rows) {
        int count = 0;
        for (ProductImportRow row : rows) {
            entityManager.persist(ProductEntity.from(row));

            if (++count % 50 == 0) {
                entityManager.flush();
                entityManager.clear();
            }
        }

        entityManager.flush();
        entityManager.clear();
    }
}
```

`flush()` đồng bộ các thay đổi đang chờ xuống database trong transaction hiện tại; nó không commit transaction. `clear()` giải phóng các entity đang được quản lý khỏi persistence context. Sau `clear`, những entity trước đó trở thành detached; không nên tiếp tục dựa vào dirty checking của chúng.

Nếu một entity cần được tham chiếu sau khi clear, hãy lưu ID hoặc dữ liệu cần thiết thay vì giữ kỳ vọng rằng instance cũ vẫn được quản lý. Với quan hệ giữa các entity trong cùng chunk, cần persist theo thứ tự phù hợp hoặc dùng cơ chế mapping/flush được thiết kế rõ ràng.

## 5. Tách xử lý thành chunk và transaction ngắn

Để tránh một transaction bao trùm toàn bộ file, có thể chia dữ liệu thành các chunk rồi gọi một writer có transaction riêng cho từng chunk:

```java
@Service
public class ProductImportCoordinator {
    private final ProductChunkWriter writer;

    public ProductImportCoordinator(ProductChunkWriter writer) {
        this.writer = writer;
    }

    public void importAll(Iterator<ProductImportRow> input) {
        while (input.hasNext()) {
            List<ProductImportRow> chunk = new ArrayList<>(500);
            while (input.hasNext() && chunk.size() < 500) {
                chunk.add(input.next());
            }
            writer.writeChunk(chunk);
        }
    }
}
```

`ProductChunkWriter.writeChunk(...)` ở ví dụ trước được gọi qua một Spring bean khác nên `@Transactional` có thể được áp dụng qua proxy. Nếu đặt coordinator và writer trong cùng một class rồi gọi method transactional bằng `this.writeChunk(...)`, lời gọi nội bộ thường không đi qua proxy Spring mặc định, vì vậy annotation có thể không tạo transaction mới như mong đợi.

Mỗi lần `writeChunk` kết thúc thành công, transaction của chunk được commit. Nếu chunk thứ 8 thất bại, các chunk đã commit trước đó vẫn tồn tại; chỉ chunk đang lỗi bị rollback theo transaction của nó. Đây là đánh đổi quan trọng so với một transaction duy nhất bao trùm toàn bộ dữ liệu.

Nếu yêu cầu nghiệp vụ bắt buộc toàn bộ file phải thành công hoặc thất bại như một đơn vị, không thể tự ý commit từng chunk rồi coi như tương đương. Có thể cần một transaction lớn, hoặc một thiết kế khác như nạp vào staging table, kiểm tra toàn bộ, rồi chuyển trạng thái bằng một thao tác có kiểm soát. Chọn cách nào tùy kích thước dữ liệu, giới hạn database và yêu cầu atomicity.

## 6. Đọc dữ liệu theo lô để tránh tải toàn bộ vào bộ nhớ

Batching không chỉ áp dụng cho ghi. Khi xử lý danh sách lớn, tránh gọi `findAll()` rồi giữ toàn bộ entity trong bộ nhớ. Có thể đọc từng trang hoặc từng nhóm ID.

Ví dụ dùng phân trang theo offset:

```java
Pageable pageable = PageRequest.of(0, 500, Sort.by("id"));
Page<Product> page;

do {
    page = productRepository.findAll(pageable);
    process(page.getContent());
    pageable = page.nextPageable();
} while (page.hasNext());
```

Cách này dễ hiểu nhưng offset lớn có thể tốn kém vì database phải bỏ qua nhiều hàng trước khi trả trang sau. Khi dữ liệu rất lớn và có khóa sắp xếp ổn định, keyset pagination có thể hiệu quả hơn: truy vấn trang kế tiếp với điều kiện `id > :lastSeenId`, sắp xếp theo `id` và giới hạn số hàng.

```sql
SELECT id, sku, name
FROM product
WHERE id > :lastSeenId
ORDER BY id
LIMIT 500;
```

Keyset pagination cần thứ tự ổn định và khóa phân trang không bị thay đổi trong quá trình xử lý. Nếu dùng nhiều cột sắp xếp, điều kiện tiếp tục phải so sánh theo đúng thứ tự và có khóa duy nhất làm tiêu chí cuối. Với dữ liệu thay đổi liên tục, cần xác định snapshot hoặc điều kiện lọc để tránh bỏ sót hay xử lý lặp bản ghi.

## 7. Vì sao phải giới hạn thời gian giữ transaction?

Transaction dài có thể gây ra nhiều chi phí:

- **Giữ connection lâu:** một connection trong pool bị chiếm trong suốt transaction, làm giảm số connection còn lại cho request khác.
- **Giữ khóa lâu:** các thao tác ghi thường giữ lock tới commit/rollback; transaction khác có thể phải chờ.
- **Tăng áp lực lên database:** tùy isolation level và engine, snapshot cũ hoặc phiên giao dịch lâu có thể làm chậm việc dọn dẹp phiên bản dữ liệu, tăng log hoặc tài nguyên cần duy trì.
- **Rollback tốn kém:** càng nhiều thao tác đã thực hiện, việc hủy toàn bộ công việc càng có thể mất nhiều thời gian.
- **Tăng xác suất xung đột:** transaction sống lâu có nhiều cơ hội gặp lock contention, deadlock hoặc lỗi serialization.

Một lỗi thiết kế thường gặp là mở transaction rồi gọi dịch vụ bên ngoài:

```java
@Transactional
public void placeOrder(PlaceOrderCommand command) {
    Order order = createOrder(command);
    orderRepository.save(order);

    paymentClient.charge(order); // Gọi mạng trong transaction
    notificationClient.sendConfirmation(order);
}
```

Lời gọi HTTP có thể chậm, timeout hoặc retry trong khi transaction vẫn giữ connection và có thể giữ khóa database. Database transaction cũng không thể rollback một khoản thanh toán đã được nhà cung cấp chấp nhận hoặc một email đã gửi.

Nên giữ transaction tập trung vào phần đọc/ghi cần nhất quán trong database. Với tích hợp bên ngoài, cân nhắc mô hình điều phối phù hợp: ghi trạng thái và outbox event trong cùng transaction, sau commit có worker gửi message; hoặc dùng workflow/saga khi quy trình qua nhiều hệ thống cần hành động bù. Không nên giả định một `@Transactional` của JPA bao trùm được một dịch vụ HTTP độc lập.

## 8. Chọn ranh giới transaction theo yêu cầu nghiệp vụ

Transaction ngắn là mục tiêu hữu ích, nhưng không phải lý do để chia nhỏ tùy tiện. Ranh giới transaction phải bảo vệ những thay đổi cần cùng commit hoặc rollback.

| Cách tổ chức | Đặc điểm | Khi phù hợp |
|---|---|---|
| Một transaction cho toàn bộ công việc | Tất cả thay đổi cùng thành công hoặc rollback | Dữ liệu vừa phải và yêu cầu atomicity toàn bộ là bắt buộc |
| Một transaction cho mỗi chunk | Mỗi nhóm được commit độc lập | Nhập/xuất khối lượng lớn, chấp nhận tiến độ từng phần và có checkpoint |
| Một transaction cho từng bản ghi | Lỗi được cô lập nhỏ, nhưng số lần commit lớn | Xử lý độc lập, khối lượng vừa phải hoặc cần cô lập lỗi từng mục |
| Staging rồi chuyển đổi | Dữ liệu được nạp và kiểm tra trước, sau đó áp dụng có kiểm soát | Cần xử lý lượng lớn nhưng vẫn cần một bước công bố kết quả rõ ràng |

Hãy xác định rõ điều gì được phép xảy ra khi một phần công việc thất bại. Nếu mỗi chunk commit riêng, hệ thống cần biết chunk nào đã hoàn tất và cách tiếp tục. Nếu mọi thứ phải atomic, hãy tính cả thời gian transaction, dung lượng log, lock và giới hạn vận hành.

## 9. Idempotency, checkpoint và retry

Khi mỗi chunk commit riêng, tiến trình có thể bị dừng sau khi một số chunk đã hoàn thành. Để tiếp tục an toàn, cần lưu checkpoint hoặc xác định lại phạm vi đã xử lý. Một checkpoint có thể là ID cuối cùng đã commit, số thứ tự chunk hoặc một khóa nguồn ổn định.

Retry cũng cần được thiết kế cẩn thận. Nếu client hoặc worker không biết lần ghi đã commit hay chưa, chạy lại có thể tạo dữ liệu trùng. Dùng khóa idempotency, unique constraint, upsert có điều kiện hoặc đánh dấu trạng thái xử lý để một bản ghi được áp dụng đúng một lần theo ngữ nghĩa nghiệp vụ.

Với lỗi tạm thời như deadlock hoặc serialization failure, có thể retry toàn bộ transaction/chunk với số lần giới hạn và backoff. Không nên chỉ retry câu SQL cuối khi các bước trước đó đã dựa trên một snapshot hoặc trạng thái có thể không còn hợp lệ. Lỗi validation hoặc dữ liệu sai có tính xác định thường không tự hết khi retry; cần ghi nhận để xử lý dữ liệu nguồn.

Nếu một chunk chứa nhiều bản ghi và chỉ một bản ghi sai, có hai chiến lược phổ biến:

- Rollback cả chunk, ghi nhận lỗi và xử lý lại chunk sau khi sửa dữ liệu.
- Tách bản ghi lỗi ra, chỉ ghi những bản ghi hợp lệ theo chính sách nghiệp vụ được xác định trước.

Chiến lược thứ hai có thể hữu ích cho nhập dữ liệu không yêu cầu toàn bộ file atomic, nhưng cần báo cáo rõ bản ghi nào bị từ chối. Không nên âm thầm bỏ qua lỗi constraint.

## 10. Đo hiệu quả và phát hiện transaction kéo dài

Không thể biết batching có cải thiện hiệu năng chỉ bằng cách nhìn code. Hãy đo:

- Số câu SQL và số lần round trip cho mỗi chunk.
- Thời gian xử lý trung bình và percentile của một chunk.
- Kích thước persistence context và mức sử dụng heap.
- Thời gian transaction từ lúc bắt đầu tới commit.
- Connection pool active/idle, thời gian chờ lấy connection.
- Lock wait, deadlock, rollback và timeout.
- Throughput tổng thể khi có tải đồng thời, không chỉ tốc độ chạy đơn lẻ.

Với Hibernate, bật SQL/batch logging hoặc thống kê trong môi trường phát triển để xác nhận batch thực sự được gửi. Với database, xem slow query log, execution plan, lock monitoring và metric transaction tùy hệ quản trị. Không để log SQL nhạy cảm hoặc bật log chi tiết không cần thiết trong production nếu nó làm lộ dữ liệu hay gây overhead.

Hãy đo trên dữ liệu có phân bố và kích thước gần production. Một batch chạy nhanh trên 100 dòng có thể hoạt động rất khác khi có hàng triệu dòng, nhiều index, trigger, constraint và người dùng đồng thời.

## 11. Những sai lầm thường gặp

- **Cho tất cả dữ liệu vào một transaction:** dễ đạt atomicity nhưng có thể giữ connection/lock quá lâu và làm rollback nặng.
- **Nghĩ `saveAll()` luôn là batch insert:** API cấp cao không bảo đảm driver nhận JDBC batch.
- **Đặt batch size thật lớn ngay từ đầu:** có thể tăng bộ nhớ và độ trễ, hoặc không tương thích với driver/giới hạn database.
- **Nhầm `flush()` với `commit()`:** flush gửi thay đổi xuống database trong transaction; commit mới kết thúc transaction thành công.
- **Gọi `clear()` mà vẫn dùng entity như đang managed:** entity sau clear đã detached, dirty checking không còn theo dõi chúng.
- **Gọi API bên ngoài trong transaction dài:** thời gian mạng kéo dài thời gian giữ tài nguyên database mà không tạo atomicity phân tán.
- **Commit từng chunk nhưng không có checkpoint/idempotency:** tiến trình chạy lại có thể ghi trùng hoặc bỏ sót dữ liệu.
- **Chia transaction quá nhỏ mà không tính tính nhất quán:** các bản ghi cần cập nhật cùng nhau có thể bị commit ở trạng thái dở dang.

## 12. Checklist khi thiết kế xử lý theo lô

Trước khi triển khai, hãy trả lời:

1. Khối lượng dữ liệu lớn đến mức nào và có cần tải toàn bộ vào bộ nhớ không?
2. Thao tác nào có thể gom thành JDBC/ORM batch? Driver và ID strategy có hỗ trợ không?
3. Batch size và chunk size ban đầu là bao nhiêu, dựa trên phép đo nào?
4. Mỗi chunk cần atomic riêng hay toàn bộ công việc phải atomic?
5. Transaction có đang bao trùm xử lý CPU lâu, chờ người dùng hoặc gọi dịch vụ mạng không?
6. Sau `flush`/`clear`, entity nào trở thành detached và còn được dùng ở đâu?
7. Nếu tiến trình dừng giữa chừng, checkpoint và retry sẽ hoạt động thế nào?
8. Làm sao tránh ghi trùng khi một chunk được chạy lại?
9. Metric nào sẽ xác nhận số round trip, thời gian transaction, lock wait và throughput đã cải thiện?

Một quy trình xử lý tốt thường đọc dữ liệu theo nhóm vừa phải, chuyển đổi ngoài thời gian giữ transaction khi có thể, ghi bằng batch phù hợp, commit theo ranh giới nghiệp vụ và lưu checkpoint để phục hồi. Hãy xác minh bằng số đo thực tế và điều chỉnh batch/chunk theo tải, thay vì áp dụng một con số cố định cho mọi môi trường.

## Ghi nhớ

- Batching giảm chi phí nhiều lần giao tiếp với database; batch size là số thao tác gom trong một lần gửi.
- Chunk size thường xác định lượng dữ liệu xử lý trong một đơn vị công việc hoặc transaction; batch size và chunk size có thể khác nhau.
- Hibernate cần được cấu hình và kiểm tra SQL thực tế; `saveAll()` không tự bảo đảm JDBC batching, và IDENTITY generation thường hạn chế batching insert.
- `flush()` đồng bộ thay đổi trong transaction; `clear()` detach entity khỏi persistence context; cả hai không thay thế commit.
- Transaction dài giữ connection và có thể giữ khóa/snapshot lâu, làm tăng contention và chi phí rollback.
- Chọn transaction boundary theo yêu cầu atomicity; commit từng chunk cần checkpoint, idempotency và chính sách retry rõ ràng.
- Tránh gọi dịch vụ bên ngoài trong transaction database dài; dùng outbox hoặc workflow phù hợp khi cần phối hợp nhiều hệ thống.
- Đo round trip, throughput, heap, transaction duration, connection pool và lock wait để xác nhận tối ưu có hiệu quả.
