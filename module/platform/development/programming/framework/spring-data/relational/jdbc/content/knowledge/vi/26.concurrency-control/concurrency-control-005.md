# Khóa bi quan bằng @Lock và các LockMode được hỗ trợ

Khi nhiều transaction cùng đọc rồi cập nhật một hàng dữ liệu, chỉ đọc giá trị hiện tại rồi ghi lại có thể dẫn đến mất cập nhật hoặc vi phạm quy tắc nghiệp vụ. **Khóa bi quan (pessimistic locking)** yêu cầu database khóa những hàng được truy vấn để các transaction khác không thể thực hiện thao tác xung đột trong thời gian khóa còn hiệu lực.

Trong Spring Data JDBC, có thể bật khóa cho một phương thức truy vấn suy diễn của repository bằng annotation `@Lock`. Annotation nhận một giá trị `LockMode` để chọn loại khóa. Spring Data Relational hiện hỗ trợ đúng hai mode:

- `PESSIMISTIC_READ`: yêu cầu khóa đọc bi quan, thường tương ứng khóa chia sẻ, nhằm ngăn transaction khác sửa các hàng đang được đọc.
- `PESSIMISTIC_WRITE`: yêu cầu khóa ghi bi quan, thường tương ứng khóa mạnh hơn để bảo vệ thao tác đọc rồi cập nhật.

Khả năng phân biệt hai mode phụ thuộc database. Một số database không có cách biểu diễn riêng cho khóa đọc chia sẻ, nên cả hai mode có thể được chuyển thành khóa ghi bi quan.

Bài học tập trung vào cách khai báo `@Lock` trên derived query method, chọn mode theo mục đích, giữ khóa trong transaction, và hiểu giới hạn khi dùng database dialect hoặc truy vấn SQL viết tay.

## 1. Vì sao cần khóa bi quan?

Giả sử kho hàng có một mặt hàng với số lượng tồn là 5. Hai yêu cầu đặt hàng đến gần như đồng thời, mỗi yêu cầu muốn lấy 4 sản phẩm.

Nếu cả hai transaction cùng đọc số lượng 5 trước khi transaction nào ghi, chúng đều có thể kết luận rằng còn đủ hàng. Sau đó cả hai cùng giảm tồn kho, dẫn đến số lượng bị bán vượt thực tế.

Một lịch thực thi có thể diễn ra như sau:

~~~text
Transaction A                 Transaction B
-------------                 -------------
Đọc available = 5
                              Đọc available = 5
Kiểm tra 5 >= 4
                              Kiểm tra 5 >= 4
Ghi available = 1
                              Ghi available = 1
COMMIT                        COMMIT
~~~

Cả hai yêu cầu đều được chấp nhận dù chỉ có 5 sản phẩm. Kết quả cuối cùng không phản ánh tổng số lượng đã đặt.

Khóa bi quan thay đổi trình tự. Transaction A lấy khóa ghi trên hàng tồn kho trước khi đọc. Transaction B phải chờ transaction A kết thúc mới có thể lấy khóa tương thích. Khi B đọc lại, nó thấy số lượng mới là 1 và từ chối yêu cầu lấy 4 sản phẩm.

~~~text
Transaction A                 Transaction B
-------------                 -------------
BEGIN
SELECT ... FOR UPDATE
Đọc available = 5
                              BEGIN
                              SELECT ... FOR UPDATE
                              Chờ khóa của A
Kiểm tra 5 >= 4
Ghi available = 1
COMMIT
                              Lấy được khóa
                              Đọc available = 1
                              Kiểm tra 1 >= 4
                              Từ chối yêu cầu
                              ROLLBACK
~~~

Đây là tình huống phù hợp với khóa bi quan: xung đột có khả năng xảy ra và ứng dụng cần tuần tự hóa thao tác trên cùng dữ liệu.

## 2. @Lock và LockMode thuộc package nào?

Spring Data JDBC cung cấp annotation `@Lock` trong package `org.springframework.data.relational.repository`. Enum `LockMode` nằm trong package `org.springframework.data.relational.core.sql`.

~~~java
import org.springframework.data.relational.repository.Lock;
import org.springframework.data.relational.core.sql.LockMode;
~~~

Đừng nhầm annotation này với `jakarta.persistence.Lock` hoặc enum `jakarta.persistence.LockModeType` của JPA. Spring Data JDBC có API khóa riêng và chỉ công bố hai giá trị `PESSIMISTIC_READ` cùng `PESSIMISTIC_WRITE`.

Annotation được đặt trên **method** của repository:

~~~java
@Lock(LockMode.PESSIMISTIC_WRITE)
Optional<StockItem> findBySku(String sku);
~~~

Spring Data dùng mode đã khai báo để bổ sung lock clause phù hợp vào câu SELECT do derived query method tạo ra.

## 3. Hai LockMode được hỗ trợ

<text color="secondary" size="sm">Enum: org.springframework.data.relational.core.sql.LockMode</text>

| LockMode | Ý nghĩa | Trường hợp phù hợp |
| --- | --- | --- |
| `PESSIMISTIC_READ` | Yêu cầu khóa đọc chia sẻ để ngăn transaction khác sửa hàng đang đọc | Đọc dữ liệu cần giữ ổn định trong lúc thực hiện một quyết định |
| `PESSIMISTIC_WRITE` | Yêu cầu khóa ghi để ngăn các thao tác ghi xung đột | Đọc, kiểm tra điều kiện rồi cập nhật cùng một hàng |

### 3.1. PESSIMISTIC_READ

Khóa đọc bi quan thường được database triển khai như shared lock. Nhiều transaction có thể cùng giữ khóa đọc tương thích trên một hàng, trong khi transaction muốn sửa hàng đó phải chờ.

Ví dụ, một tiến trình đọc thông tin hạn mức và cần đảm bảo không có transaction khác sửa hạn mức trong lúc nó thực hiện một quyết định:

~~~java
@Lock(LockMode.PESSIMISTIC_READ)
Optional<AccountLimit> findByAccountNumber(String accountNumber);
~~~

Mode này phù hợp khi thao tác chính là đọc và cần ngăn thay đổi cạnh tranh trong một khoảng thời gian ngắn.

Không nên tự động chọn PESSIMISTIC_READ cho mọi truy vấn chỉ đọc. Nếu không có quyết định nghiệp vụ nào cần bảo vệ khỏi thay đổi đồng thời, một SELECT thông thường thường đủ. Khóa làm giảm khả năng xử lý song song và có thể khiến transaction khác phải chờ.

### 3.2. PESSIMISTIC_WRITE

Khóa ghi bi quan yêu cầu database lấy khóa mạnh hơn trên các hàng được truy vấn. Transaction khác muốn sửa cùng hàng hoặc lấy khóa xung đột sẽ phải chờ hoặc nhận lỗi theo chính sách timeout/lock của database.

Ví dụ:

~~~java
@Lock(LockMode.PESSIMISTIC_WRITE)
Optional<StockItem> findBySku(String sku);
~~~

Đây là mode phù hợp với luồng đọc số lượng, kiểm tra số lượng còn lại rồi giảm tồn kho. Khóa được lấy khi câu SELECT thực thi, trước khi ứng dụng đọc và xử lý giá trị trả về.

Khóa ghi không có nghĩa mọi transaction khác đều không thể đọc hàng đó. Với database dùng MVCC, các truy vấn đọc thông thường có thể vẫn đọc snapshot cũ. Điều bị ngăn là những thao tác xung đột theo semantics khóa và isolation level của database.

### 3.3. Database có thể coi hai mode là một

Spring Data JDBC không thể bảo đảm mọi database đều có hai loại khóa với hành vi khác nhau. Tài liệu Spring nêu rõ một số database không phân biệt PESSIMISTIC_READ và PESSIMISTIC_WRITE; trong trường hợp đó cả hai có thể tương đương PESSIMISTIC_WRITE.

Vì vậy:

- Chọn mode theo ý định của nghiệp vụ.
- Kiểm tra cách dialect của database chuyển mode thành SQL.
- Kiểm thử với đúng hệ quản trị và isolation level của môi trường triển khai.
- Không suy luận rằng PESSIMISTIC_READ luôn cho phép nhiều reader cùng khóa trên mọi database.

### 3.4. Các mode không có trong Spring Data JDBC

Enum `org.springframework.data.relational.core.sql.LockMode` hiện chỉ có hai hằng số. Các tên sau không thuộc enum này:

- `OPTIMISTIC`
- `OPTIMISTIC_FORCE_INCREMENT`
- `PESSIMISTIC_FORCE_INCREMENT`
- `PESSIMISTIC_READ` với timeout tùy chỉnh
- `PESSIMISTIC_WRITE` với tùy chọn NOWAIT hoặc SKIP LOCKED

Đây là điểm khác biệt với một số API JPA hoặc Hibernate. Không thể truyền các mode đó vào `@Lock` của Spring Data JDBC. Optimistic locking trong Spring Data JDBC được triển khai riêng bằng annotation `@Version` trên aggregate root.

## 4. Mô hình ví dụ: tồn kho theo SKU và kho hàng

Ta dùng entity `StockItem` làm ví dụ. Mỗi tổ hợp SKU và kho hàng chỉ có một hàng tồn kho. Hai trường này được đặt unique constraint để bảo đảm truy vấn theo SKU và warehouse trả về tối đa một hàng.

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("stock_items")
public class StockItem {

    @Id
    private Long id;

    private String sku;
    private String warehouseCode;
    private int available;

    protected StockItem() {
    }

    public StockItem(
            String sku,
            String warehouseCode,
            int available) {
        this.sku = sku;
        this.warehouseCode = warehouseCode;
        this.available = available;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getWarehouseCode() {
        return warehouseCode;
    }

    public int getAvailable() {
        return available;
    }

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive"
            );
        }

        if (available < quantity) {
            throw new InsufficientStockException(sku);
        }

        available -= quantity;
    }
}
~~~

Schema minh họa:

~~~sql
CREATE TABLE stock_items (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(80) NOT NULL,
    warehouse_code VARCHAR(40) NOT NULL,
    available INTEGER NOT NULL CHECK (available >= 0),
    CONSTRAINT uk_stock_sku_warehouse
        UNIQUE (sku, warehouse_code)
);
~~~

Unique constraint rất quan trọng. Khóa bi quan bảo vệ những hàng đã tồn tại và được truy vấn; nó không tự tạo tính duy nhất cho SKU/kho hàng.

## 5. Khai báo @Lock trên repository method

Repository có thể cung cấp các phương thức khóa theo mục đích:

~~~java
import java.util.List;
import java.util.Optional;

import org.springframework.data.repository.CrudRepository;
import org.springframework.data.relational.repository.Lock;
import org.springframework.data.relational.core.sql.LockMode;

public interface StockItemRepository
        extends CrudRepository<StockItem, Long> {

    @Lock(LockMode.PESSIMISTIC_READ)
    List<StockItem> findByWarehouseCode(String warehouseCode);

    @Lock(LockMode.PESSIMISTIC_WRITE)
    Optional<StockItem> findBySkuAndWarehouseCode(
        String sku,
        String warehouseCode
    );
}
~~~

Hai phương thức đều là derived query method:

- `findByWarehouseCode` được phân tích thành điều kiện lọc theo property `warehouseCode`.
- `findBySkuAndWarehouseCode` được phân tích thành điều kiện kết hợp theo hai property `sku` và `warehouseCode`.

Annotation `@Lock` cung cấp lock mode cho câu SELECT tương ứng. Phương thức thứ hai dùng `PESSIMISTIC_WRITE` vì nó phục vụ luồng cập nhật số lượng tồn.

### Chọn kiểu trả về

Kiểu trả về cần phản ánh số hàng mà điều kiện có thể tìm thấy:

- `Optional<StockItem>` phù hợp khi unique constraint bảo đảm chỉ có tối đa một hàng.
- `List<StockItem>` phù hợp khi một warehouse có nhiều mặt hàng.
- Không dùng `Optional` cho truy vấn có thể trả về nhiều hàng nếu database không có constraint bảo đảm duy nhất.

Nếu truy vấn trả về nhiều hàng, khóa được áp dụng cho các hàng được SELECT trả về theo SQL và semantics của database. Cần cân nhắc số lượng hàng có thể bị khóa.

## 6. SQL được tạo phụ thuộc dialect

`@Lock` không yêu cầu lập trình viên tự nối chuỗi SQL. Spring Data JDBC sử dụng dialect để tạo lock clause phù hợp với database.

Ví dụ khái niệm cho khóa ghi:

~~~sql
SELECT *
FROM stock_items
WHERE sku = ?
  AND warehouse_code = ?
FOR UPDATE;
~~~

Ví dụ trong tài liệu Spring cho `PESSIMISTIC_READ` với MySQL Dialect:

~~~sql
SELECT *
FROM user_table
WHERE lastname = ?
LOCK IN SHARE MODE;
~~~

Cú pháp thực tế phụ thuộc database và phiên bản. Một số database dùng `FOR SHARE` cho khóa chia sẻ; một số dùng cú pháp khác hoặc chuyển yêu cầu khóa đọc thành khóa ghi. Không nên sao chép lock clause của MySQL sang PostgreSQL, SQL Server hay database khác mà chưa kiểm tra.

Spring Data Relational có abstraction `Dialect` và `LockClause` để xử lý khác biệt cú pháp. Ứng dụng thông thường chỉ khai báo `@Lock` và để dialect tạo SQL.

## 7. Giữ khóa trong transaction

Đây là phần quan trọng nhất khi triển khai khóa bi quan.

Database giữ row lock cho đến khi transaction kết thúc bằng COMMIT hoặc ROLLBACK. `@Lock` chỉ yêu cầu khóa khi thực hiện SELECT; nó không tự tạo một transaction dài bao quanh toàn bộ logic nghiệp vụ.

Nếu query chạy trong auto-commit, transaction có thể kết thúc ngay sau câu SELECT. Khi đó lock được giải phóng trước khi service kịp kiểm tra số lượng và cập nhật hàng.

Hãy đặt transaction ở service boundary:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class StockService {

    private final StockItemRepository stockItems;

    public StockService(StockItemRepository stockItems) {
        this.stockItems = stockItems;
    }

    @Transactional
    public void reserve(
            String sku,
            String warehouseCode,
            int quantity) {

        StockItem item = stockItems
            .findBySkuAndWarehouseCode(sku, warehouseCode)
            .orElseThrow(() ->
                new StockItemNotFoundException(sku)
            );

        item.reserve(quantity);

        stockItems.save(item);
    }
}
~~~

Trình tự trong một lần gọi service:

1. Spring mở transaction.
2. Repository chạy SELECT có PESSIMISTIC_WRITE.
3. Database cấp khóa cho hàng phù hợp.
4. Service kiểm tra số lượng và thay đổi object.
5. Repository lưu thay đổi.
6. Transaction commit và database giải phóng khóa.

Nếu `item.reserve` ném exception hoặc thao tác lưu thất bại, transaction có thể rollback theo quy tắc rollback của Spring. Với exception unchecked như `InsufficientStockException` nếu kế thừa RuntimeException, transaction mặc định được rollback.

### Không đặt readOnly cho luồng cập nhật

Luồng reserve vừa đọc vừa ghi nên dùng transaction ghi thông thường:

~~~java
@Transactional
public void reserve(...) {
    // lock, validate, update
}
~~~

`@Transactional(readOnly = true)` không phù hợp với luồng cần gọi `save`. Thuộc tính readOnly chủ yếu là hint được truyền xuống driver/transaction manager; nó không phải cơ chế thay thế cho lock và không bảo đảm mọi database đều chặn thao tác ghi.

### Query method cũng cần transaction

Các phương thức query tự khai báo trong repository không mặc nhiên có cùng cấu hình transaction như CRUD method kế thừa. Tài liệu Spring Data JDBC khuyến nghị làm cho query method có transaction, vì việc materialize aggregate có thể phát sinh nhiều câu query.

Khi query method được gọi từ service có `@Transactional`, lời gọi repository tham gia transaction bên ngoài. Đây là cách thuận tiện để giữ khóa xuyên suốt bước đọc, kiểm tra và ghi.

Nếu query method được gọi độc lập, có thể khai báo transaction ở repository interface hoặc method. Tuy nhiên, transaction chỉ bao quanh method repository sẽ kết thúc khi method trả về. Nếu service cần tiếp tục xử lý rồi ghi, transaction nên bao quanh toàn bộ use case ở service.

## 8. Ví dụ hai transaction cạnh tranh

Giả sử hàng tồn kho ban đầu có `available = 5`. Hai request A và B đều gọi `reserve(sku, warehouse, 4)`.

Khi A lấy được PESSIMISTIC_WRITE, B phải chờ ở câu SELECT có khóa. A giảm số lượng còn 1 và commit. Sau đó B mới đọc được hàng theo transaction của mình, thấy số lượng là 1 và phát sinh `InsufficientStockException`.

Kết quả:

| Transaction | Số lượng đọc được | Số lượng yêu cầu | Kết quả |
| --- | ---: | ---: | --- |
| A | 5 | 4 | Thành công, còn 1 |
| B | 1 | 4 | Bị từ chối |

Không có tình huống cả hai cùng dựa trên số lượng cũ là 5 để xác nhận đơn hàng.

Điều kiện để ví dụ hoạt động:

- Hai transaction truy cập cùng hàng dữ liệu.
- Câu SELECT lấy khóa ghi trước khi đọc giá trị dùng cho quyết định.
- Khóa còn hiệu lực trong suốt bước kiểm tra và cập nhật.
- Database hỗ trợ lock semantics mà dialect yêu cầu.
- Mọi đường ghi liên quan đều tuân thủ cùng quy tắc nghiệp vụ.

Khóa bi quan không bảo vệ một luồng ghi khác nếu luồng đó không xung đột với hàng đang khóa hoặc thực hiện trên một bảng/đối tượng khác.

## 9. @Lock hiện chỉ áp dụng cho derived query method

Trong Spring Data JDBC hiện hành, `@Lock` được hỗ trợ trên **derived query method**.

Ví dụ được hỗ trợ:

~~~java
@Lock(LockMode.PESSIMISTIC_WRITE)
Optional<StockItem> findBySkuAndWarehouseCode(
    String sku,
    String warehouseCode
);
~~~

Với method này, Spring Data tự tạo SELECT từ tên phương thức và gắn lock clause theo dialect.

### Không dùng @Lock với string-based @Query

`@Lock` hiện không được áp dụng cho query method khai báo SQL bằng `@Query`:

~~~java
@Lock(LockMode.PESSIMISTIC_WRITE)
@Query("SELECT * FROM stock_items WHERE sku = :sku")
Optional<StockItem> findLockedBySku(String sku);
~~~

Trong Spring Data JDBC, locking information từ `@Lock` trên string-based query sẽ bị bỏ qua và framework ghi warning trong log. Tài liệu hiện tại nói các phiên bản tương lai sẽ ném exception cho trường hợp này.

Nếu cần SQL tùy chỉnh kèm khóa:

- Viết lock clause trực tiếp trong SQL theo database mục tiêu.
- Hoặc triển khai custom repository bằng JDBC API phù hợp.
- Đảm bảo câu SQL chạy trong transaction đang bao quanh use case.
- Kiểm thử câu SQL và lock behavior trên database thực tế.

Không dựa vào annotation `@Lock` để khóa một câu SQL tùy chỉnh.

## 10. Phạm vi khóa và những gì @Lock không bảo vệ

Khóa bi quan tác động đến những hàng database được câu SELECT khóa. Phạm vi cụ thể còn phụ thuộc SQL được tạo, query plan, index, isolation level và cơ chế lock của database.

### 10.1. Không có hàng phù hợp thì không có row lock

Nếu truy vấn không tìm thấy SKU, không có hàng hiện hữu để khóa. Hai transaction cùng kiểm tra một SKU chưa tồn tại vẫn có thể cùng nhận kết quả rỗng rồi cùng thử insert.

Để bảo vệ trường hợp tạo mới:

- Dùng unique constraint để database bảo đảm không có hai hàng trùng khóa nghiệp vụ.
- Bắt và xử lý lỗi duplicate key theo quy tắc nghiệp vụ.
- Nếu cần tuần tự hóa cả trường hợp key chưa tồn tại, cân nhắc khóa một hàng cha đã tồn tại hoặc cơ chế khóa đặc thù của database.

Không giả định SELECT FOR UPDATE trên một kết quả rỗng sẽ khóa được một key chưa có.

### 10.2. Không tự động khóa mọi entity con

Trong Spring Data JDBC, aggregate có thể gồm root và các entity con ở bảng khác. Annotation `@Lock` trên query method khóa SELECT mà repository method tạo ra. Không nên mặc định rằng khóa root đồng nghĩa với khóa mọi hàng child, hàng ở aggregate khác hoặc mọi bảng được tham chiếu.

Nếu invariant nghiệp vụ phụ thuộc vào nhiều hàng, hãy xác định rõ những hàng cần khóa và thiết kế truy vấn/transaction tương ứng. Khóa nhiều hàng theo thứ tự nhất quán giúp giảm nguy cơ deadlock.

### 10.3. Không thay thế constraint

Khóa bi quan bảo vệ thao tác đồng thời, còn constraint bảo vệ tính hợp lệ của dữ liệu ở database.

Ví dụ:

- `CHECK (available >= 0)` ngăn số lượng tồn âm.
- `UNIQUE (sku, warehouse_code)` ngăn trùng hàng tồn kho.
- `FOREIGN KEY` bảo vệ quan hệ tham chiếu.

Nên kết hợp transaction, khóa và constraint khi invariant cần được bảo vệ ở nhiều lớp.

## 11. Khóa bi quan và optimistic locking bằng @Version

Spring Data JDBC cũng hỗ trợ optimistic locking qua property số có annotation `@Version` trên aggregate root. Cơ chế này khác với `@Lock`.

| Tiêu chí | Pessimistic locking | Optimistic locking |
| --- | --- | --- |
| Cách bảo vệ | Lấy database lock trước khi xử lý | So sánh version khi cập nhật |
| Thời điểm phát hiện xung đột | Khi lấy khóa hoặc chờ khóa | Khi update/delete kiểm tra version |
| Giữ database lock trong lúc xử lý | Có | Không yêu cầu lock bi quan kéo dài |
| Phù hợp | Xung đột thường xuyên, cần tuần tự hóa | Xung đột ít, ưu tiên nhiều transaction chạy song song |
| API Spring Data JDBC | `@Lock` + `LockMode` | `@Version` |

Ví dụ optimistic locking:

~~~java
@Table("stock_items")
public class StockItem {

    @Id
    private Long id;

    @Version
    private Long version;

    private int available;
}
~~~

Khi cập nhật, Spring Data JDBC đưa version hiện tại vào điều kiện UPDATE. Nếu một transaction khác đã cập nhật và tăng version, update dùng version cũ không còn khớp và Spring ném `OptimisticLockingFailureException`.

Không có mode `OPTIMISTIC` trong enum `LockMode` của Spring Data JDBC. `@Version` là cơ chế riêng để phát hiện dữ liệu đã thay đổi.

Có thể chọn theo đặc điểm workload:

- Một hàng tồn kho nóng có nhiều yêu cầu đặt hàng đồng thời có thể phù hợp với PESSIMISTIC_WRITE.
- Một hồ sơ ít bị cập nhật đồng thời có thể phù hợp với optimistic locking.
- Một số use case cần kết hợp kiểm tra version với transaction boundary và constraint để xử lý cả dữ liệu cũ lẫn cạnh tranh ghi.

## 12. Deadlock, lock wait và thời gian giữ khóa

Khóa bi quan làm transaction phải chờ khi có xung đột. Nếu nhiều transaction khóa các hàng theo thứ tự khác nhau, chúng có thể tạo deadlock.

Ví dụ:

~~~text
Transaction A                 Transaction B
-------------                 -------------
Khóa hàng 1                   Khóa hàng 2
Chờ hàng 2                    Chờ hàng 1
~~~

A giữ hàng 1 và chờ hàng 2; B giữ hàng 2 và chờ hàng 1. Database phát hiện vòng chờ và hủy một transaction theo chính sách của nó.

Một số nguyên tắc giúp giảm rủi ro:

1. Giữ transaction ngắn, chỉ bao quanh thao tác cần bảo vệ.
2. Khóa nhiều hàng theo cùng một thứ tự ở mọi luồng xử lý.
3. Tránh gọi API mạng, gửi email hoặc chờ người dùng trong lúc đang giữ lock.
4. Tạo index phù hợp để database tìm đúng hàng nhanh.
5. Xử lý timeout và deadlock ở transaction boundary.
6. Nếu cần retry, retry toàn bộ transaction bằng một transaction mới sau khi transaction cũ rollback.

`@Lock` chỉ nhận một `LockMode`. Annotation không cung cấp thuộc tính timeout, NOWAIT hoặc SKIP LOCKED. Những tính năng đó nếu cần phải được triển khai theo khả năng của database và cách truy cập SQL mà ứng dụng sử dụng.

## 13. Kiểm thử khóa bi quan

Unit test cho service có thể kiểm tra quy tắc nghiệp vụ như số lượng không hợp lệ hoặc tồn kho không đủ. Tuy nhiên, unit test không chứng minh database thực sự giữ row lock.

Để kiểm tra concurrency, nên dùng integration test với database cùng loại với production:

1. Tạo hàng tồn kho có số lượng ban đầu.
2. Mở transaction A và gọi repository method có PESSIMISTIC_WRITE.
3. Giữ transaction A chưa commit bằng barrier/latch trong test.
4. Từ transaction B, gọi cùng repository method trên cùng hàng.
5. Xác nhận B phải chờ hoặc nhận kết quả theo semantics của database.
6. Cho A cập nhật rồi commit.
7. Xác nhận B tiếp tục và đọc trạng thái mới trước khi quyết định cập nhật.

Không nên chỉ dùng H2 để suy luận hành vi khóa của PostgreSQL hoặc MySQL. Cú pháp lock, isolation level, MVCC và timeout có thể khác nhau. Hãy kiểm thử trên hệ quản trị thật hoặc Testcontainers với đúng database image cần hỗ trợ.

### Quan sát SQL

Bật logging SQL hoặc quan sát statement ở database để xác nhận câu SELECT có lock clause. Điều này giúp phát hiện trường hợp:

- Annotation bị đặt nhầm trên method.
- Method đang dùng string-based `@Query`.
- Dialect không hỗ trợ cú pháp mong muốn.
- Cấu hình transaction khiến khóa được giải phóng sớm.

Đọc được câu SQL có lock clause vẫn chưa chứng minh toàn bộ use case an toàn. Cần kiểm tra cả thời gian transaction, các đường ghi khác và kết quả khi hai transaction chạy đồng thời.

## 14. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Transaction khác vẫn cập nhật được sau khi query trả về | Transaction đã kết thúc và lock được giải phóng | Đặt `@Transactional` ở service bao quanh đọc và ghi |
| @Lock không tạo hiệu ứng trên query | Đặt trên string-based `@Query` | Dùng derived query hoặc tự viết SQL lock clause |
| PESSIMISTIC_READ cũng chặn reader khác | Database ánh xạ cả hai mode thành write lock | Kiểm tra dialect và semantics database |
| Hai request vẫn cùng tạo một SKU | Không có hàng tồn tại để khóa | Dùng unique constraint và xử lý insert conflict |
| Deadlock khi xử lý nhiều mặt hàng | Các transaction khóa hàng theo thứ tự khác nhau | Sắp xếp ID/SKU theo thứ tự nhất quán trước khi khóa |
| Query chậm trong lúc giữ lock | Điều kiện không dùng index phù hợp hoặc transaction quá dài | Tối ưu index và rút ngắn transaction |
| Optional nhận nhiều kết quả | Điều kiện không được bảo đảm duy nhất | Dùng List hoặc thêm unique constraint |
| Nhầm LockMode với JPA | Import sai package hoặc dùng enum JPA | Dùng Lock và LockMode của Spring Data Relational |
| Mong có NOWAIT/SKIP LOCKED | Enum chỉ có hai mode | Dùng SQL/API riêng theo database |
| Nghĩ khóa root tự khóa mọi bảng con | Phạm vi lock phụ thuộc SELECT và database | Xác định rõ từng hàng cần bảo vệ |

## 15. Quy trình chọn và triển khai LockMode

Khi cần bảo vệ một use case, hãy làm theo thứ tự:

1. Xác định invariant nghiệp vụ cần bảo vệ, ví dụ số lượng tồn không được âm.
2. Xác định các hàng database mà invariant phụ thuộc.
3. Chọn derived query method trả về đúng hàng cần khóa.
4. Dùng `PESSIMISTIC_READ` nếu cần khóa chia sẻ cho một thao tác đọc được bảo vệ.
5. Dùng `PESSIMISTIC_WRITE` nếu cần đọc, kiểm tra rồi cập nhật.
6. Đặt `@Transactional` ở service để giữ lock đến khi hoàn tất use case.
7. Bổ sung unique/check/foreign key constraints cho invariant tương ứng.
8. Kiểm tra SQL được dialect sinh ra và test trên database mục tiêu.
9. Đo thời gian giữ lock, xử lý timeout/deadlock và chỉ retry toàn bộ transaction khi phù hợp.

Đừng dùng khóa bi quan chỉ vì có nhiều người dùng. Chỉ khóa dữ liệu mà use case thực sự cần bảo vệ; giữ lock lâu và khóa quá nhiều hàng sẽ giảm throughput của hệ thống.

## 16. Bài tập tự thực hành

### Bài 1 — Khai báo @Lock

Tạo repository cho `StockItem`. Viết một method dùng `PESSIMISTIC_READ` và một method dùng `PESSIMISTIC_WRITE`. Giải thích khác biệt giữa hai mục đích.

### Bài 2 — Bảo vệ tồn kho

Viết service `reserve` có `@Transactional`. Dùng repository method khóa ghi, kiểm tra số lượng và giảm tồn kho. Chạy hai yêu cầu đồng thời để xác nhận không thể bán vượt số lượng.

### Bài 3 — Quan sát SQL

Bật log SQL hoặc quan sát statement ở database. Xác định lock clause được tạo cho từng LockMode trên database đang dùng.

### Bài 4 — Thử database khác

Chạy cùng integration test trên PostgreSQL và MySQL. So sánh cú pháp khóa và hành vi của PESSIMISTIC_READ/PESSIMISTIC_WRITE.

### Bài 5 — Query method và @Query

Tạo một derived query có `@Lock` và một method dùng string-based `@Query` có gắn `@Lock`. Quan sát warning và xác nhận annotation không áp dụng cho query viết bằng chuỗi.

### Bài 6 — Hàng chưa tồn tại

Thử hai transaction cùng tạo SKU chưa có. Giải thích vì sao row lock không khóa được hàng chưa tồn tại và dùng unique constraint để bảo vệ dữ liệu.

### Bài 7 — Deadlock

Tạo hai transaction khóa hai hàng theo thứ tự ngược nhau. Quan sát deadlock, sau đó sửa để cả hai transaction khóa theo cùng thứ tự.

### Bài 8 — So sánh với @Version

Thêm property `@Version` vào aggregate root. Thử cập nhật đồng thời bằng optimistic locking và so sánh với PESSIMISTIC_WRITE về thời điểm phát hiện xung đột.

## 17. Tài liệu tham khảo chính thức

- [Spring Data Relational — Transactionality and JDBC Locking](https://docs.spring.io/spring-data/relational/reference/jdbc/transactions.html): cách bật khóa bằng `@Lock` trên derived query method, hai LockMode được hỗ trợ, ví dụ SQL MySQL và giới hạn với string-based `@Query`.
- [Spring Data Relational — @Lock API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/repository/Lock.html): annotation đặt trên method và thuộc tính `value` nhận LockMode.
- [Spring Data Relational — LockMode API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/sql/LockMode.html): enum và danh sách hằng số được hỗ trợ.
- [Spring Data Relational — Optimistic Locking](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html): cơ chế optimistic locking qua `@Version` trên aggregate root.

`@Lock` cho phép Spring Data JDBC yêu cầu database khóa các hàng được truy vấn bằng derived query method. Hai mode hiện được hỗ trợ là `PESSIMISTIC_READ` và `PESSIMISTIC_WRITE`. Để khóa thực sự bảo vệ một use case, hãy đặt truy vấn và thao tác cập nhật trong cùng transaction, hiểu cách database triển khai từng mode, đồng thời dùng constraint để bảo vệ các trường hợp không có hàng hiện hữu hoặc có nhiều đường ghi cạnh tranh.
