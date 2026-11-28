# Optimistic locking bằng @Version trên entity

Trong ứng dụng Spring Data Neo4j, nhiều request có thể cùng đọc một node rồi cập nhật nó gần như đồng thời. Ví dụ, hai nhân viên cùng mở thông tin một sản phẩm; cả hai đều thấy còn 10 đơn vị hàng. Người thứ nhất đặt trước 4 đơn vị và lưu thành công. Nếu người thứ hai vẫn lưu bản dữ liệu cũ mà không phát hiện thay đổi trước đó, số lượng mới có thể ghi đè kết quả của người thứ nhất.

**Optimistic locking** giải quyết tình huống này bằng cách gắn một số phiên bản vào entity. Mỗi lần cập nhật thành công, Spring Data Neo4j tăng phiên bản. Khi một entity cũ được lưu với phiên bản không còn khớp database, thao tác bị từ chối và phát sinh `OptimisticLockingFailureException`. Ứng dụng có thể tải dữ liệu mới, tính lại nghiệp vụ và yêu cầu người dùng thử lại khi phù hợp.

## 1. Optimistic locking hoạt động như thế nào?

Optimistic locking giả định xung đột không xảy ra thường xuyên. Nhiều transaction có thể đọc cùng một phiên bản mà không phải giữ khóa trong suốt thời gian người dùng xử lý. Xung đột chỉ được kiểm tra khi ghi.

Giả sử node `InventoryItem` có `version = 5`:

1. Transaction A đọc sản phẩm và nhận phiên bản `5`.
2. Transaction B cũng đọc sản phẩm và nhận phiên bản `5`.
3. A cập nhật số lượng và lưu thành công. Phiên bản trong database tăng thành `6`.
4. B cố lưu entity vẫn mang phiên bản `5`.
5. Spring Data Neo4j phát hiện phiên bản B không còn hiện hành và ném `OptimisticLockingFailureException`.

```text
Database: version = 5
       /                 \
      /                   \
Transaction A          Transaction B
read version 5         read version 5
update                  update
save version 5          save version 5
      |                      |
      v                      v
success                 conflict
database version = 6   OptimisticLockingFailureException
```

Nhờ vậy, thay đổi của A không bị B ghi đè âm thầm. B phải đọc lại trạng thái hiện tại trước khi quyết định có thể tiếp tục nghiệp vụ hay không.

## 2. Khai báo @Version trên entity

Spring Data Neo4j sử dụng annotation `@Version` của Spring Data Commons:

```java
import org.springframework.data.annotation.Version;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("InventoryItem")
public class InventoryItem {

    @Id
    private String sku;

    @Version
    private Long version;

    private long available;

    protected InventoryItem() {
    }

    public InventoryItem(String sku, long available) {
        this.sku = sku;
        this.available = available;
    }

    public String getSku() {
        return sku;
    }

    public Long getVersion() {
        return version;
    }

    public long getAvailable() {
        return available;
    }

    public void reserve(long quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Số lượng phải lớn hơn 0");
        }
        if (available < quantity) {
            throw new IllegalStateException("Không đủ hàng trong kho");
        }
        available -= quantity;
    }
}
```

Các điểm cần nhớ:

- `@Version` được import từ `org.springframework.data.annotation.Version`.
- Trong Spring Data Neo4j, field version phải có kiểu `Long`.
- SDN quản lý giá trị version; không tự tăng, giảm hoặc gán lại version trong service.
- Phiên bản khởi đầu là `0` và được tăng tự động sau mỗi lần cập nhật thành công.
- Một entity chỉ nên có một field version được quản lý.

Ở ví dụ trên, `sku` là business ID do ứng dụng cấp. Với entity dùng business ID, `@Version` còn giúp SDN phân biệt entity mới với entity đã tồn tại. Để version ở trạng thái chưa có giá trị trước lần lưu đầu; SDN sẽ khởi tạo version khi persist. Không tự gán `0L` cho entity mới hoặc sao chép version từ một object khác.

## 3. Dùng repository để cập nhật entity có version

Repository không cần khai báo phương thức đặc biệt cho optimistic locking:

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface InventoryItemRepository
        extends Neo4jRepository<InventoryItem, String> {
}
```

Service đọc entity, áp dụng thay đổi nghiệp vụ rồi lưu:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryService {

    private final InventoryItemRepository repository;

    public InventoryService(InventoryItemRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public InventoryItem reserve(String sku, long quantity) {
        InventoryItem item = repository.findById(sku)
            .orElseThrow(() -> new IllegalArgumentException("Không tìm thấy sản phẩm"));

        item.reserve(quantity);

        return repository.save(item);
    }
}
```

Khi `save(item)` cập nhật entity có `@Version`, SDN kiểm tra phiên bản mà entity đang mang. Nếu phiên bản vẫn khớp, cập nhật được ghi và version tăng. Nếu phiên bản đã thay đổi do transaction khác, thao tác thất bại bằng `OptimisticLockingFailureException`.

Transaction ở service giúp các thao tác đọc, kiểm tra và ghi thuộc cùng một đơn vị nghiệp vụ. Tuy nhiên, optimistic locking vẫn cần thiết: transaction không có nghĩa là hai request đọc cùng dữ liệu sẽ tự động biết request còn lại đã cập nhật.

## 4. Vòng đời của version

Với một entity mới dùng business ID, version ban đầu chưa có giá trị. Sau lần lưu đầu, SDN khởi tạo version trong database là `0`. Mỗi lần cập nhật thành công tiếp theo, version tăng thêm một đơn vị.

| Thời điểm | Version trong entity/database |
|---|---:|
| Entity mới trước khi lưu | `null` trong object mới |
| Sau lần lưu đầu | `0` |
| Sau lần cập nhật thứ nhất | `1` |
| Sau lần cập nhật thứ hai | `2` |
| Một entity cũ được đọc ở version `1` nhưng database đã là `2` | Lưu bị từ chối |

Không dùng version làm số lần người dùng chỉnh sửa, mã sự kiện hoặc timestamp. Đây là metadata kỹ thuật để phát hiện cập nhật cạnh tranh. Nếu cần lịch sử thay đổi, hãy lưu audit event hoặc các trường auditing riêng.

## 5. Điều gì xảy ra khi hai request cùng cập nhật?

Giả sử số lượng ban đầu là 10 và version là 3. Hai request cùng đọc entity:

| Bước | Request A | Request B | Database |
|---|---|---|---|
| 1 | Đọc `available=10`, `version=3` | | `10`, version `3` |
| 2 | | Đọc `available=10`, `version=3` | `10`, version `3` |
| 3 | Đặt trước 4, lưu thành công | | `6`, version `4` |
| 4 | | Đặt trước 7 trên object cũ | `6`, version `4` |
| 5 | | Lưu với version `3`, bị từ chối | `6`, version `4` |

Request B không được phép ghi số lượng `3` dựa trên bản đọc cũ. Sau khi nhận conflict, ứng dụng phải tải lại sản phẩm. Lúc này số lượng chỉ còn 6, nên yêu cầu đặt trước 7 sẽ bị từ chối vì không đủ hàng.

Optimistic locking vì thế bảo vệ cả tính nhất quán dữ liệu lẫn cơ hội kiểm tra lại quy tắc nghiệp vụ trên trạng thái mới nhất.

## 6. Xử lý OptimisticLockingFailureException

`OptimisticLockingFailureException` thuộc hệ thống exception của Spring DAO. Đây là xung đột cập nhật, không phải lỗi cú pháp Cypher hay lỗi kết nối database.

Thông thường, service nên để exception thoát khỏi transaction hiện tại để transaction rollback. Tầng API có thể chuyển xung đột thành phản hồi phù hợp, thường là HTTP `409 Conflict`, để client biết dữ liệu đã được người khác thay đổi.

Ví dụ xử lý ở tầng web:

```java
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(OptimisticLockingFailureException.class)
    public ResponseEntity<String> handleOptimisticLockingFailure(
            OptimisticLockingFailureException exception) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
            .body("Dữ liệu đã được cập nhật bởi một thao tác khác. Hãy tải lại và thử lại.");
    }
}
```

Không trả stack trace hoặc chi tiết nội bộ database cho client.

Không nên bắt exception trong service rồi tiếp tục dùng chính entity cũ. Object đó đã mang version lỗi thời. Nếu muốn thử lại tự động, cần:

1. Kết thúc transaction đã thất bại.
2. Mở transaction mới.
3. Đọc lại entity để nhận version hiện hành.
4. Áp dụng lại command nghiệp vụ trên dữ liệu mới.
5. Kiểm tra lại các điều kiện như số lượng, trạng thái hoặc giới hạn.
6. Chỉ thử lại với số lần giới hạn và khi thao tác có thể thực hiện an toàn.

Retry không có nghĩa là gửi lại nguyên object cũ. Phải đọc lại và tính lại thay đổi; nếu quy tắc nghiệp vụ không còn thỏa mãn thì trả conflict cho người gọi.

## 7. Vì sao không nên tự sửa version?

Field version thuộc quyền quản lý của Spring Data Neo4j. Nếu service tự tăng version trước khi gọi `save`, giá trị được gửi có thể không còn tương ứng với phiên bản đã đọc từ database. Không nên nhận version từ request rồi gán trực tiếp vào entity. Nếu client gửi version để bảo vệ thao tác cập nhật, hãy dùng nó như một điều kiện nghiệp vụ ở tầng API/service, so sánh với version hiện tại hoặc thiết kế DTO cập nhật riêng. SDN vẫn phải là thành phần quản lý version field trong entity.

Tương tự, không dùng cùng một field version cho mục đích khác như số thứ tự nghiệp vụ, revision của tài liệu hoặc timestamp. Những khái niệm đó cần property riêng.

## 8. Business ID và vai trò của @Version

Khi dùng ID do ứng dụng cấp, ví dụ `sku`, `customerId` hoặc `orderNumber`, ID đã có giá trị ngay khi tạo object. Chỉ nhìn ID thì SDN không thể biết object đó mới hay đã được lưu trước đó.

`@Version` cung cấp thông tin cần thiết để phân biệt trạng thái này. Do đó, với entity sử dụng business ID, version field là bắt buộc theo hướng dẫn của Spring Data Neo4j. Hãy khai báo `Long` nullable và để SDN quản lý giá trị của nó.

Nếu dùng ID sinh tự động bằng `@GeneratedValue`, SDN có thể nhận diện entity mới thông qua ID chưa được cấp. Dù vậy, vẫn có thể thêm `@Version` để bảo vệ các lần cập nhật đồng thời.

## 9. Phạm vi bảo vệ của @Version

Optimistic locking gắn với entity có field `@Version` và các thao tác ghi được thực hiện qua cơ chế mapping của Spring Data Neo4j. Không nên hiểu rằng chỉ cần đặt version trên một node là mọi thay đổi ở bất kỳ node hoặc relationship nào trong toàn bộ graph đều được bảo vệ tự động.

Khi thiết kế aggregate:

- Xác định entity nào là điểm cập nhật chính và mang version.
- Đảm bảo các luồng ghi nghiệp vụ đều đi qua cơ chế SDN có kiểm tra version.
- Nếu nhiều aggregate có thể được cập nhật độc lập, xác định version/concurrency policy riêng cho từng aggregate.
- Kiểm thử rõ hành vi khi lưu entity có relationship properties, nhất là khi nhiều request thay đổi cùng một relationship.

`@Version` cũng không tự áp dụng cho mọi câu Cypher tùy chỉnh. Một câu `@Query`, `Neo4jClient` hoặc thao tác trực tiếp bằng Neo4j Driver có thể cập nhật property mà không kiểm tra version nếu truy vấn không tự đưa điều kiện version vào.

Nếu cần optimistic locking trong Cypher trực tiếp, phải tự thực hiện compare-and-set trong cùng câu lệnh. Ví dụ:

```cypher
MATCH (item:InventoryItem {sku: $sku})
WHERE item.version = $expectedVersion
  AND item.available >= $quantity
SET item.available = item.available - $quantity,
    item.version = item.version + 1
RETURN item.sku AS sku,
       item.available AS available,
       item.version AS version
```

Nếu truy vấn không trả dòng nào, có thể do sản phẩm không tồn tại, version không còn khớp hoặc số lượng không đủ. Ứng dụng cần phân biệt các trường hợp này bằng truy vấn/kiểm tra phù hợp. Khi dùng Cypher trực tiếp, chính ứng dụng chịu trách nhiệm tăng version và xử lý conflict; SDN không tự chèn cơ chế `@Version` vào câu lệnh đó.

## 10. Optimistic locking khác gì pessimistic locking?

| Tiêu chí | Optimistic locking | Pessimistic locking |
|---|---|---|
| Cách tiếp cận | Cho phép nhiều transaction đọc; kiểm tra version khi ghi | Cố gắng khóa tài nguyên trước khi thay đổi |
| Xung đột | Phát hiện lúc cập nhật và từ chối writer dùng version cũ | Writer khác có thể phải chờ hoặc không lấy được khóa |
| Chi phí | Thấp khi xung đột ít | Có thể tốn chi phí giữ khóa và chờ |
| Phù hợp | Dữ liệu đọc nhiều, cập nhật cạnh tranh không thường xuyên | Tình huống cần điều phối truy cập chặt chẽ và có chiến lược khóa phù hợp |
| Cơ chế trong bài | `@Version` trên entity | Cơ chế khóa/điều phối riêng của database và ứng dụng |

`@Version` không khóa node trong suốt thời gian người dùng mở màn hình. Nó chỉ phát hiện rằng trạng thái đã thay đổi trước khi cập nhật được ghi. Vì vậy, nó phù hợp với nhiều ứng dụng có nhiều lượt đọc và số lần ghi cạnh tranh thấp hoặc vừa phải.

## 11. Kiểm thử optimistic locking

Integration test nên mô phỏng hai bản entity được đọc từ cùng một version. Kịch bản cơ bản:

1. Tạo và lưu một `InventoryItem`; xác nhận version khởi tạo là `0`.
2. Đọc cùng sản phẩm thành hai object độc lập, `firstCopy` và `secondCopy`.
3. Thay đổi `firstCopy`, lưu thành công và xác nhận version tăng thành `1`.
4. Thay đổi `secondCopy` mà không đọc lại database.
5. Gọi `save(secondCopy)` và xác nhận phát sinh `OptimisticLockingFailureException`.
6. Đọc lại sản phẩm trong transaction mới và xác nhận giá trị của lần cập nhật thứ nhất vẫn còn.
7. Thực hiện một lần cập nhật mới dựa trên entity vừa đọc và xác nhận lưu thành công.

Để kiểm thử race condition thật sự giữa hai transaction, chạy hai luồng độc lập và điều phối để cả hai đọc cùng version trước khi một luồng ghi. Không dùng chung một transaction hoặc một object Java cho cả hai luồng, vì điều đó không mô phỏng hai writer độc lập.

Test cần xác nhận cả exception và trạng thái cuối trong database. Chỉ kiểm tra version trong object không đủ để chứng minh thay đổi đã được commit hoặc rollback đúng.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Entity business ID luôn bị xem như mới | Thiếu field `@Version` để SDN nhận diện trạng thái persist | Thêm `@Version` kiểu `Long` cho entity dùng business ID. |
| Lưu entity cũ phát sinh conflict | Một transaction khác đã tăng version | Đọc lại entity và tính lại nghiệp vụ trên trạng thái mới. |
| Version tăng sai hoặc save thất bại | Service tự gán hoặc tăng field version | Để SDN quản lý version, không sửa trong domain/service. |
| Dùng primitive cho version | Primitive không biểu diễn được trạng thái chưa có version | Dùng `Long` theo yêu cầu của SDN. |
| Custom Cypher ghi đè dữ liệu mà không có conflict | Câu Cypher trực tiếp không tự áp dụng `@Version` | Thêm điều kiện version và tăng version trong cùng câu lệnh, hoặc dùng luồng save được SDN quản lý. |
| Retry liên tục vẫn thất bại | Retry lại entity cũ hoặc không giới hạn số lần thử | Mỗi lần thử phải đọc lại, kiểm tra lại nghiệp vụ và giới hạn retry. |
| Nghĩ version của node gốc bảo vệ mọi node liên quan | Phạm vi version bị hiểu rộng hơn entity được quản lý | Xác định aggregate boundary và concurrency policy cho từng phần dữ liệu. |

## 13. Quy trình áp dụng @Version

1. Xác định entity nào có thể được nhiều request cập nhật đồng thời.
2. Thêm field `@Version` kiểu `Long` và import annotation từ Spring Data Commons.
3. Với business ID, giữ version null trên entity mới để SDN nhận diện trạng thái chưa persist.
4. Không sửa version thủ công trong service, controller hoặc request DTO.
5. Thực hiện đọc, kiểm tra nghiệp vụ và lưu trong service transaction.
6. Bắt hoặc chuyển `OptimisticLockingFailureException` ở ranh giới phù hợp; thường trả HTTP `409 Conflict`.
7. Nếu retry, mở transaction mới, đọc entity mới và áp dụng lại command thay vì lưu object cũ.
8. Rà soát các đường ghi bằng custom Cypher/Driver vì chúng không tự động được bảo vệ bởi annotation.
9. Viết integration test với hai bản entity cùng version và xác nhận writer thứ hai bị từ chối.

## 14. Ghi nhớ

`@Version` cho phép Spring Data Neo4j phát hiện cập nhật cạnh tranh khi lưu entity. Field version có kiểu `Long`, được khởi tạo ở `0` và tăng tự động sau mỗi lần cập nhật thành công. Nếu hai transaction cùng đọc version `x`, writer đầu tiên có thể lưu và tăng version thành `x + 1`; writer còn lại dùng version cũ sẽ nhận `OptimisticLockingFailureException`.

Không tự sửa version. Khi có conflict, hãy rollback transaction hiện tại, đọc lại entity trong transaction mới và đánh giá lại nghiệp vụ trước khi thử tiếp. Với business ID, `@Version` còn giúp SDN nhận biết entity mới hay đã tồn tại. Các câu Cypher trực tiếp cần tự thực hiện kiểm tra và tăng version nếu muốn có cùng hành vi. Hãy xác định đúng phạm vi entity được bảo vệ và kiểm thử bằng hai bản entity độc lập để tránh ghi đè dữ liệu khi nhiều request cùng cập nhật.

## Tài liệu tham khảo

- [Spring Data Neo4j – Metadata-based Mapping: Optimistic locking with @Version](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/metadata-based-mapping.html#mapping-ids)
- [Spring Data Neo4j – Handling and provisioning of unique IDs](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/mapping-ids.html)
- [Spring Data Commons – Optimistic Locking](https://docs.spring.io/spring-data/commons/reference/repositories/core-concepts.html)
