# Giao dịch và tính nhất quán

## Đánh giá mức cô lập trong quy trình đọc, kiểm tra rồi cập nhật

Trong module `SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED` — **Học tổ chức phần mềm theo kiến trúc phân tầng** — một ca sử dụng thường đọc dữ liệu hiện tại, kiểm tra điều kiện nghiệp vụ rồi ghi thay đổi. Ví dụ: đọc số lượng hàng còn lại, kiểm tra đủ hàng và trừ kho; đọc số dư, kiểm tra đủ tiền rồi chuyển khoản; hoặc kiểm tra phòng còn trống trước khi xác nhận đặt chỗ.

Quy trình này có vẻ tuần tự trong một request, nhưng nhiều request có thể chạy đồng thời. Nếu hai giao dịch cùng đọc một trạng thái cũ, cả hai có thể cùng vượt qua bước kiểm tra rồi cập nhật theo những giả định không còn đúng. **Mức cô lập (isolation level)** quyết định những thay đổi đồng thời nào một giao dịch có thể quan sát và cách cơ sở dữ liệu xử lý xung đột. Chọn mức cô lập cần dựa trên bất biến nghiệp vụ, loại truy vấn và chi phí khóa hoặc thử lại.

Bài học dùng ví dụ giữ chỗ hàng tồn kho trong Java/Spring và cơ sở dữ liệu quan hệ. Các mức cô lập có tên chuẩn SQL, nhưng chi tiết thực thi và mức mặc định có thể khác giữa PostgreSQL, MySQL/InnoDB, Oracle và các hệ quản trị khác.

## 1. Vì sao đọc rồi kiểm tra rồi cập nhật có thể sai?

Giả sử một sản phẩm chỉ còn một đơn vị hàng. Hai khách hàng gửi yêu cầu mua gần như cùng lúc. Mỗi request chạy trong một transaction riêng:

```text
Thời điểm     Transaction A                 Transaction B
-----------   ----------------------------  ----------------------------
t1            BEGIN
t2            SELECT available -> 1
t3                                          BEGIN
t4                                          SELECT available -> 1
t5            Kiểm tra: 1 >= 1, đạt
t6                                          Kiểm tra: 1 >= 1, đạt
t7            UPDATE available = 0
t8            COMMIT
t9                                          UPDATE available = 0
t10                                         COMMIT
```

Hai transaction đều dựa trên giá trị `1` đã đọc. Nếu mỗi transaction ghi giá trị mới được tính từ bản sao cũ trong bộ nhớ, cả hai có thể hoàn tất dù chỉ có một đơn vị hàng. Đây là một dạng **lost update** (cập nhật bị ghi đè): thay đổi của transaction sau làm mất hiệu lực thay đổi trước. Tùy câu lệnh SQL và cơ chế khóa của hệ quản trị, biểu hiện cụ thể có thể khác; điểm cốt lõi là bước kiểm tra và bước ghi không được bảo vệ như một thao tác nguyên tử.

Một transaction không tự động khiến chuỗi `SELECT -> kiểm tra trong Java -> UPDATE` trở thành một thao tác không thể bị xen ngang. `@Transactional` xác định phạm vi giao dịch, còn isolation, khóa, version hoặc câu lệnh cập nhật có điều kiện mới quyết định cách xử lý cạnh tranh giữa các transaction.

### Bất biến cần bảo vệ

Trước khi chọn isolation, hãy viết điều kiện nghiệp vụ dưới dạng một bất biến có thể kiểm tra. Với kho hàng:

\[
available \geq 0
\]

Và một yêu cầu mua số lượng `q` chỉ được chấp nhận nếu:

\[
available_{before} \geq q
\]

Sau khi chấp nhận, số lượng còn lại phải là:

\[
available_{after} = available_{before} - q
\]

Nếu bất biến chỉ liên quan đến một hàng dữ liệu, một câu lệnh cập nhật có điều kiện có thể bảo vệ nó rất hiệu quả. Nếu điều kiện phụ thuộc nhiều hàng hoặc tổng hợp nhiều bản ghi, cần xem xét khóa hoặc isolation mạnh hơn.

## 2. Các hiện tượng đọc và ghi khi có cạnh tranh

Các thuật ngữ sau mô tả những vấn đề có thể xuất hiện khi nhiều transaction cùng truy cập dữ liệu:

| Hiện tượng | Mô tả | Ví dụ |
| --- | --- | --- |
| Dirty read | Đọc dữ liệu mà transaction khác đã ghi nhưng chưa commit | A đọc số dư mới do B cập nhật; sau đó B rollback |
| Non-repeatable read | Đọc lại cùng một hàng trong một transaction nhưng nhận giá trị khác do transaction khác commit thay đổi | A đọc số lượng là 5; B đổi thành 3 và commit; A đọc lại thấy 3 |
| Phantom read | Chạy lại truy vấn theo một điều kiện và thấy tập hàng thỏa điều kiện thay đổi do transaction khác thêm/xóa hàng hoặc làm hàng bắt đầu/ngừng thỏa điều kiện | A đếm đơn `PENDING`; B thêm một đơn `PENDING`; A đếm lại thấy nhiều hơn |
| Lost update | Một cập nhật dựa trên giá trị cũ ghi đè hoặc làm mất hiệu lực cập nhật đồng thời | Hai transaction cùng đọc 10, cùng tính giá trị mới 9 rồi lần lượt ghi 9 |
| Write skew | Hai transaction đọc cùng một trạng thái tổng thể rồi sửa những hàng khác nhau; từng cập nhật không xung đột trực tiếp nhưng kết quả chung vi phạm bất biến | Hai bác sĩ cùng trực; mỗi người thấy người kia đang trực rồi tự rút ca, khiến không còn ai trực |

Dirty read, non-repeatable read và phantom read là các hiện tượng thường dùng để mô tả mức cô lập theo chuẩn SQL. Lost update và write skew giúp phân tích các xung đột thực tế mà chỉ nhìn vào ba hiện tượng đọc trên có thể chưa đủ. Không phải mọi hệ quản trị đều phân loại hoặc ngăn các hiện tượng này theo cùng một cơ chế.

### Write skew trong điều kiện kiểm tra nhiều hàng

Giả sử quy tắc là luôn phải có ít nhất một nhân viên trực. Hai transaction cùng đọc hai hàng trực và đều thấy cả hai nhân viên đang trực. Transaction A cập nhật nhân viên A thành nghỉ; transaction B cập nhật nhân viên B thành nghỉ. Vì hai transaction ghi hai hàng khác nhau, một số cơ chế cô lập dựa trên snapshot có thể cho cả hai commit, khiến tổng số người trực bằng không.

Đây không đơn thuần là lost update trên cùng một hàng. Muốn ngăn write skew, có thể khóa một hàng đại diện cho lịch trực, dùng một thiết kế dữ liệu có constraint phù hợp, hoặc dùng mức `SERIALIZABLE` và xử lý việc transaction bị từ chối. Khóa riêng từng hàng mà mỗi transaction sửa có thể không đủ nếu điều kiện nghiệp vụ nằm trên tập hàng.

## 3. Đánh giá các mức cô lập

Chuẩn SQL định nghĩa các mức cô lập theo những hiện tượng đọc mà transaction phải ngăn. Bảng sau mô tả cách hiểu tổng quát theo chuẩn; không nên suy ra chính xác cơ chế khóa hay hành vi của mọi hệ quản trị chỉ từ tên mức.

| Mức cô lập | Dirty read | Non-repeatable read | Phantom read | Đặc điểm và chi phí |
| --- | --- | --- | --- | --- |
| `READ UNCOMMITTED` | Có thể xảy ra | Có thể xảy ra | Có thể xảy ra | Mức yếu nhất; một số hệ quản trị không hỗ trợ thực sự và có thể xử lý như `READ COMMITTED` |
| `READ COMMITTED` | Bị ngăn | Có thể xảy ra | Có thể xảy ra | Mỗi câu lệnh chỉ đọc dữ liệu đã commit theo quy tắc của hệ quản trị; thường cân bằng tốt cho CRUD |
| `REPEATABLE READ` | Bị ngăn | Bị ngăn theo định nghĩa chuẩn | Chuẩn cho phép phantom | Giữ kết quả đọc lặp lại ổn định hơn; cách xử lý phantom và snapshot phụ thuộc hệ quản trị |
| `SERIALIZABLE` | Bị ngăn | Bị ngăn | Bị ngăn | Kết quả tương đương một thứ tự chạy tuần tự hợp lệ; có thể khóa, chờ hoặc hủy transaction để tránh lịch thực thi không an toàn |

Ba cột hiện tượng đọc trong bảng không mô tả đầy đủ mọi dạng xung đột ghi. Đặc biệt, không thể chỉ nhìn tên `REPEATABLE READ` để kết luận lost update hoặc write skew luôn được ngăn; cần xem cơ chế của hệ quản trị, cách câu lệnh cập nhật và cách ứng dụng phát hiện xung đột.

`SERIALIZABLE` không có nghĩa các transaction bắt buộc chạy lần lượt hoàn toàn. Hệ quản trị có thể cho phép chạy đồng thời nếu kết quả tương đương một thứ tự tuần tự; khi phát hiện xung đột không thể sắp xếp an toàn, nó có thể từ chối một transaction. Ứng dụng cần sẵn sàng thử lại transaction bị lỗi serialization khi phù hợp.

### Tên mức giống nhau không bảo đảm hành vi giống nhau

Isolation level là hợp đồng ở mức logic, còn cơ chế thực thi phụ thuộc hệ quản trị:

- PostgreSQL dùng MVCC. `READ COMMITTED` tạo snapshot cho từng câu lệnh; `REPEATABLE READ` giữ snapshot ổn định trong transaction và ngăn phantom theo cách triển khai của PostgreSQL, nhưng vẫn có thể gặp serialization anomaly/write skew. `SERIALIZABLE` dùng Serializable Snapshot Isolation và có thể hủy transaction khi phát hiện nguy cơ.
- MySQL/InnoDB thường mặc định `REPEATABLE READ`. Consistent read, locking read và gap/next-key lock có hành vi khác nhau; locking read như `SELECT ... FOR UPDATE` có thể khóa cả khoảng khóa để bảo vệ một số điều kiện truy vấn.
- Oracle thường dùng `READ COMMITTED` làm mặc định và cung cấp `SERIALIZABLE` với hành vi cần được hiểu theo tài liệu của Oracle.

Vì vậy, hãy kiểm tra tài liệu và cấu hình của đúng hệ quản trị đang chạy. Không nên chọn `REPEATABLE READ` chỉ vì tên nghe có vẻ đủ mạnh; cần xác nhận nó bảo vệ được bất biến cụ thể trong mô hình dữ liệu và loại truy vấn đang dùng.

## 4. Khi nào READ COMMITTED là đủ?

`READ COMMITTED` thường phù hợp khi mỗi câu lệnh có thể chấp nhận nhìn thấy dữ liệu đã commit mới nhất tại thời điểm câu lệnh chạy và nghiệp vụ không cần một snapshot nhất quán xuyên suốt nhiều lần đọc. Nó ngăn dirty read nhưng không tự ngăn hai transaction cùng vượt qua một bước kiểm tra dựa trên dữ liệu cũ.

Ví dụ, nếu màn hình hiển thị thông tin sản phẩm và mỗi truy vấn có thể phản ánh cập nhật mới, `READ COMMITTED` thường đủ. Nhưng nếu ứng dụng đọc tồn kho rồi kiểm tra trước khi trừ, cần thêm cơ chế bảo vệ bước cập nhật.

Không nên tăng isolation cho mọi transaction theo cảm tính. Isolation mạnh hơn có thể làm tăng thời gian chờ, tranh chấp khóa, deadlock hoặc số lần transaction bị hủy và phải thử lại. Hãy xác định chính xác điều gì phải luôn đúng sau khi các transaction kết thúc.

## 5. Bảo vệ quy trình đọc-kiểm tra-cập nhật

Có nhiều cách bảo vệ quy trình này. Lựa chọn phụ thuộc vào việc bất biến liên quan một hàng hay nhiều hàng, mức cạnh tranh, khả năng chờ và chi phí thử lại.

### Cách 1: cập nhật có điều kiện trong một câu lệnh

Nếu chỉ cần trừ số lượng của một sản phẩm, hãy gộp điều kiện và cập nhật vào cùng một câu SQL:

```sql
UPDATE inventory
SET available = available - :quantity
WHERE product_id = :productId
  AND available >= :quantity;
```

Sau khi thực thi, kiểm tra số hàng bị ảnh hưởng:

- `1` hàng được cập nhật: điều kiện còn đủ hàng tại thời điểm ghi, thao tác trừ đã thành công.
- `0` hàng được cập nhật: không tìm thấy sản phẩm hoặc không còn đủ hàng; ứng dụng xử lý theo hợp đồng nghiệp vụ.

Việc kiểm tra và thay đổi cùng nằm trong một câu lệnh nguyên tử ở cơ sở dữ liệu, nên hai transaction không thể cùng thành công dựa trên một giá trị cũ cho cùng điều kiện cập nhật đó. Câu lệnh vẫn cần chạy trong transaction phù hợp nếu nó là một phần của quy trình ghi nhiều dữ liệu liên quan.

Ví dụ Spring Data JPA:

```java
public interface InventoryJpaRepository
        extends JpaRepository<InventoryRow, UUID> {

    @Modifying
    @Query("""
        update InventoryRow i
           set i.available = i.available - :quantity
         where i.productId = :productId
           and i.available >= :quantity
        """)
    int reserveIfAvailable(
        @org.springframework.data.repository.query.Param("productId") UUID productId,
        @org.springframework.data.repository.query.Param("quantity") int quantity);
}
```

```java
@Service
class ReserveInventoryService {
    private final InventoryJpaRepository inventory;

    ReserveInventoryService(InventoryJpaRepository inventory) {
        this.inventory = inventory;
    }

    @Transactional
    public void reserve(UUID productId, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        int updated = inventory.reserveIfAvailable(productId, quantity);
        if (updated == 0) {
            throw new InsufficientInventoryException(productId);
        }
    }
}
```

Đây là ví dụ rút gọn. Cần kiểm tra cách ORM xử lý bulk update, persistence context và việc đồng bộ entity đã được nạp trước đó. Nếu transaction tiếp tục dùng một entity đang được quản lý, có thể cần refresh hoặc clear phù hợp để tránh đọc trạng thái cũ trong bộ nhớ. Ngoài ra, nên có constraint ở database để bảo vệ `available >= 0` như một lớp phòng vệ bổ sung.

### Cách 2: khóa bi quan khi đọc

Khi cần đọc nhiều trường, kiểm tra quy tắc rồi cập nhật cùng một hàng, có thể khóa hàng trước khi kiểm tra. Transaction khác muốn khóa hoặc cập nhật hàng đó phải chờ hoặc thất bại tùy timeout và hệ quản trị.

```java
public interface InventoryJpaRepository
        extends JpaRepository<InventoryRow, UUID> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select i from InventoryRow i where i.productId = :productId")
    Optional<InventoryRow> findForUpdate(
        @org.springframework.data.repository.query.Param("productId") UUID productId);
}
```

```java
@Transactional
public void reserve(UUID productId, int quantity) {
    InventoryRow row = inventory.findForUpdate(productId)
        .orElseThrow(ProductNotFoundException::new);

    if (row.getAvailable() < quantity) {
        throw new InsufficientInventoryException(productId);
    }

    row.setAvailable(row.getAvailable() - quantity);
}
```

Khóa phải được lấy trong transaction và giữ tới khi transaction kết thúc. Transaction thứ hai sẽ đọc/kiểm tra sau khi có thể lấy khóa, vì thế nó nhìn thấy trạng thái đã cập nhật theo cơ chế của hệ quản trị. Khóa bi quan phù hợp khi xung đột thường xuyên và việc chờ có thể chấp nhận, nhưng làm giảm concurrency và có nguy cơ deadlock. Giữ transaction ngắn, lấy nhiều khóa theo thứ tự nhất quán và cấu hình timeout phù hợp.

Khóa một hàng không tự động bảo vệ điều kiện trên những hàng chưa tồn tại hoặc tổng hợp nhiều hàng. Khi truy vấn theo khoảng hoặc predicate, cần hiểu rõ row lock, gap lock, predicate lock hoặc cơ chế tương ứng của hệ quản trị.

### Cách 3: khóa lạc quan với version

Khi xung đột không thường xuyên, có thể dùng optimistic locking. Entity có trường version; khi cập nhật, ORM chỉ ghi nếu version trong database vẫn bằng version đã đọc. Nếu transaction khác đã cập nhật trước, thao tác của transaction hiện tại không cập nhật được và phát sinh lỗi xung đột.

```java
@Entity
class InventoryRow {
    @Id
    private UUID productId;

    private int available;

    @Version
    private long version;
}
```

Với JPA, lỗi thường xuất hiện dưới dạng `OptimisticLockException` hoặc ngoại lệ Spring bọc tương ứng như `ObjectOptimisticLockingFailureException`. Ứng dụng cần coi đây là xung đột đồng thời, không phải kết quả thành công. Có thể báo người dùng thử lại hoặc thực hiện retry có giới hạn nếu thao tác có tính idempotent và nghiệp vụ cho phép.

Optimistic locking phù hợp khi đọc nhiều hơn ghi và xung đột hiếm. Nó bảo vệ cập nhật cạnh tranh trên entity có version; nó không tự động bảo vệ một bất biến phụ thuộc vào nhiều hàng độc lập nếu các hàng đó không được version/kiểm tra trong cùng một cơ chế.

### Cách 4: SERIALIZABLE cho bất biến phức tạp

Nếu điều kiện phụ thuộc một tập hàng, ví dụ tổng số phòng đã đặt không vượt quá sức chứa, hoặc luôn phải có ít nhất một nhân viên trực, có thể cần `SERIALIZABLE` nếu không thể diễn đạt bất biến bằng constraint, cập nhật nguyên tử hoặc khóa phù hợp.

```java
@Transactional(isolation = Isolation.SERIALIZABLE)
public void confirmBooking(BookingCommand command) {
    // Đọc số chỗ đã dùng và giới hạn.
    // Kiểm tra điều kiện nghiệp vụ.
    // Ghi booking mới.
}
```

Ở mức này, database có thể chặn, trì hoãn hoặc hủy một transaction để đảm bảo kết quả tương đương thứ tự tuần tự. Lỗi serialization hoặc deadlock có thể xảy ra dù code không có lỗi cú pháp. Nếu retry, phải chạy lại **toàn bộ transaction** từ đầu với dữ liệu mới; không chỉ lặp lại câu UPDATE cuối cùng.

`SERIALIZABLE` là công cụ mạnh nhưng không miễn phí. Chỉ dùng khi bất biến cần bảo vệ đòi hỏi nó và nhóm đã thiết kế xử lý retry, timeout cùng tác dụng phụ. Không gửi email, gọi cổng thanh toán hoặc phát thông điệp không thể thu hồi trước khi transaction commit thành công; có thể dùng transactional outbox cho thông điệp cần phát sau commit.

## 6. Chọn chiến lược theo dạng bất biến

| Dạng điều kiện | Cách thường nên cân nhắc trước | Khi nào cần isolation/khóa mạnh hơn |
| --- | --- | --- |
| Một hàng có điều kiện số học, như số lượng không âm | `UPDATE ... WHERE available >= :q` và kiểm tra số hàng cập nhật | Khi còn các thay đổi liên quan khác phải nhất quán cùng lúc |
| Một entity được nhiều người sửa, xung đột hiếm | Optimistic locking với `@Version` | Khi xung đột thường xuyên hoặc phải chờ để đọc trạng thái mới nhất |
| Một hàng phải được đọc rồi quyết định nhiều bước, xung đột cao | Pessimistic write lock | Khi khóa hàng không đủ bảo vệ điều kiện trên tập dữ liệu |
| Bất biến liên quan nhiều hàng hoặc predicate | Constraint, thiết kế dữ liệu, khóa phạm vi phù hợp hoặc `SERIALIZABLE` | Khi không thể chứng minh các cách yếu hơn bảo vệ được bất biến |
| Dữ liệu chỉ dùng để hiển thị và chấp nhận hơi cũ | `READ COMMITTED` hoặc mô hình đọc phù hợp | Khi dữ liệu được dùng để quyết định một ghi có tác động nghiệp vụ |

Hãy chọn cơ chế nhỏ nhất có thể bảo vệ đầy đủ bất biến, rồi xác minh bằng kiểm thử cạnh tranh trên hệ quản trị thực tế. Một transaction có thể dùng isolation mặc định của hệ quản trị; một transaction khác cần mức mạnh hơn. Không nhất thiết tăng isolation cho toàn bộ ứng dụng.

## 7. Cấu hình isolation trong Spring

Spring cho phép khai báo isolation ở `@Transactional`:

```java
@Transactional(isolation = Isolation.READ_COMMITTED)
public OrderSummary getOrderSummary(OrderId id) {
    // Đọc dữ liệu phục vụ truy vấn.
}
```

```java
@Transactional(isolation = Isolation.REPEATABLE_READ)
public ReportSnapshot buildReport(ReportFilter filter) {
    // Nhiều lần đọc cần snapshot nhất quán theo semantics của DB.
}
```

`Isolation.DEFAULT` dùng mức mặc định của transaction manager/database. Do đó, cùng một cấu hình ứng dụng có thể có hành vi khác khi chuyển hệ quản trị hoặc thay đổi cấu hình server. `@Transactional` cũng thường được áp dụng qua proxy của Spring; gọi một phương thức transactional khác trong cùng object (self-invocation) không đi qua proxy theo cách thông thường. Hãy đặt ranh giới transaction ở bean/phương thức được gọi qua proxy hoặc cấu hình transaction rõ ràng.

Nếu một phương thức tham gia transaction đã tồn tại, thuộc tính isolation của lời gọi lồng nhau không nhất thiết thay đổi isolation đang có. Cần hiểu propagation và transaction manager của ứng dụng; không giả định một annotation ở phương thức con sẽ nâng mức cô lập cho transaction cha.

## 8. Retry, lỗi đồng thời và tác dụng phụ

Khi database báo optimistic conflict, serialization failure hoặc deadlock, ứng dụng cần phân loại lỗi và quyết định có thử lại hay không:

- Chỉ retry lỗi có thể phục hồi và có giới hạn số lần, khoảng chờ hoặc backoff.
- Retry toàn bộ đơn vị công việc trong transaction mới để đọc lại trạng thái mới nhất.
- Đảm bảo thao tác có idempotency hoặc dùng idempotency key để không tạo đơn, thanh toán hay ghi nhận trùng.
- Không retry lỗi nghiệp vụ ổn định như thiếu hàng hoặc không đủ số dư nếu không có dữ liệu mới làm điều kiện thay đổi.
- Tránh thực hiện tác dụng phụ bên ngoài trước commit; dùng outbox hoặc quy trình bù trừ khi cần phối hợp nhiều hệ thống.

Không nên đặt vòng lặp retry bên trong transaction đã bị đánh dấu rollback-only rồi tiếp tục sử dụng transaction đó. Retry cần được thực hiện ở ranh giới có thể mở transaction mới, chẳng hạn một lớp điều phối bên ngoài hoặc cơ chế retry được cấu hình phù hợp với transaction interceptor.

## 9. Kiểm thử quy trình đồng thời

Kiểm thử thông thường với một transaction đơn lẻ không thể chứng minh quy trình read-check-update an toàn. Cần tạo cạnh tranh thật:

1. Dùng ít nhất hai connection/transaction độc lập tới loại database mà ứng dụng chạy.
2. Dùng latch hoặc barrier để hai transaction cùng đọc trước khi cho phép cập nhật, qua đó tái tạo race có kiểm soát.
3. Chạy nhiều request cùng giữ chỗ khi chỉ còn số lượng giới hạn.
4. Xác nhận số lượng không âm, số yêu cầu thành công không vượt quá số lượng ban đầu và các request thất bại nhận đúng kết quả nghiệp vụ.
5. Với optimistic locking hoặc `SERIALIZABLE`, xác nhận lỗi xung đột được phát hiện và retry không tạo tác dụng phụ trùng lặp.

Không nên chỉ dựa vào H2 hoặc database giả lập nếu hành vi khóa, snapshot và isolation khác hệ quản trị production. Với quy tắc quan trọng, hãy kiểm thử tích hợp trên cùng engine hoặc cấu hình tương thích. Kiểm thử cần xác nhận cả kết quả cuối cùng và cách ứng dụng xử lý lỗi đồng thời.

## Tự kiểm tra

1. Vì sao `@Transactional` ở mức mặc định không tự bảo vệ bước đọc, kiểm tra rồi cập nhật?
2. `READ COMMITTED` ngăn hiện tượng nào nhưng vẫn cho phép những vấn đề nào trong một quy trình read-check-update?
3. Khi nào một câu `UPDATE ... WHERE available >= :quantity` có thể bảo vệ bất biến tốt hơn việc đọc rồi cập nhật trong Java?
4. Optimistic locking với `@Version` phát hiện xung đột ra sao và giới hạn của nó là gì?
5. Vì sao write skew trên nhiều hàng có thể tồn tại dù hai transaction không cập nhật cùng một hàng?
6. Khi database hủy transaction vì serialization failure, retry nên được thực hiện ở phạm vi nào?

