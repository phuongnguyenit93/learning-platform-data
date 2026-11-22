# Cập nhật nguyên tử bằng điều kiện nghiệp vụ và kiểm tra số dòng

Trong các hệ thống có nhiều request cùng thay đổi một dữ liệu, cách đọc entity, kiểm tra điều kiện trong Java rồi mới ghi có thể tạo ra race condition. Hai transaction có thể cùng đọc một giá trị cũ, cả hai đều thấy điều kiện hợp lệ và cùng thực hiện thay đổi. Kết quả cuối cùng có thể vi phạm quy tắc nghiệp vụ.

Spring Data JPA cho phép thực hiện một câu lệnh `UPDATE` có điều kiện ngay tại cơ sở dữ liệu. Câu lệnh vừa kiểm tra điều kiện vừa thay đổi dữ liệu trong cùng một thao tác. Giá trị số dòng bị ảnh hưởng cho biết thao tác có thành công hay không. Đây là cách triển khai dạng **conditional update** hoặc **compare-and-set**.

## 1. Vấn đề của quy trình đọc rồi ghi

Giả sử kho còn 5 sản phẩm và hai khách hàng cùng đặt 4 sản phẩm. Một quy trình dễ gặp là:

1. Đọc số lượng tồn kho.
2. Kiểm tra số lượng tồn kho có đủ hay không.
3. Trừ số lượng tồn kho.
4. Lưu entity.

Nếu hai transaction cùng đọc được giá trị 5 trước khi transaction nào ghi dữ liệu, cả hai đều có thể vượt qua bước kiểm tra. Mỗi transaction sau đó trừ 4, mặc dù kho chỉ có 5 sản phẩm.

Nguyên nhân là bước kiểm tra và bước cập nhật nằm ở hai thao tác tách biệt. Transaction giúp nhóm thao tác có ranh giới commit/rollback, nhưng bản thân việc đánh dấu một phương thức là `@Transactional` không tự biến chuỗi đọc rồi ghi thành một phép cập nhật có điều kiện nguyên tử.

## 2. Đưa điều kiện nghiệp vụ vào câu lệnh UPDATE

Thay vì tải entity về Java để kiểm tra, hãy đưa điều kiện vào mệnh đề `WHERE` của câu lệnh cập nhật. Ví dụ, chỉ trừ tồn kho khi sản phẩm đang hoạt động và số lượng còn lại đủ đáp ứng yêu cầu.

Giả sử entity có các trường `id`, `available` và `active`:

```java
@Entity
public class Inventory {

    @Id
    private Long id;

    private int available;

    private boolean active;

    protected Inventory() {
    }

    // Constructors, getters and other domain methods
}
```

Khai báo phương thức repository:

```java
package com.example.repository;

import com.example.domain.Inventory;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface InventoryRepository
        extends JpaRepository<Inventory, Long> {

    @Modifying(
        flushAutomatically = true,
        clearAutomatically = true
    )
    @Query("""
        update Inventory i
           set i.available = i.available - :quantity
         where i.id = :id
           and i.active = true
           and :quantity > 0
           and i.available >= :quantity
        """)
    int reserveIfAvailable(
            @Param("id") Long id,
            @Param("quantity") int quantity);
}
```

Các thành phần quan trọng:

- `@Query` khai báo câu lệnh JPQL. Tên `Inventory`, `available`, `active` là tên entity và thuộc tính Java, không phải tên bảng hay tên cột SQL.
- `@Modifying` cho Spring Data JPA biết đây là truy vấn thay đổi dữ liệu. Annotation này cần thiết khi dùng `@Query` cho `UPDATE` hoặc `DELETE`.
- `@Param` liên kết tham số Java với các named parameter trong JPQL.
- Điều kiện `i.available >= :quantity` bảo đảm số lượng còn lại đủ trước khi trừ.
- Điều kiện `:quantity > 0` ngăn số lượng âm làm tăng tồn kho. Service cũng nên xác thực đầu vào để trả lỗi rõ ràng.
- Giá trị trả về kiểu `int` là số dòng bị ảnh hưởng bởi câu lệnh.

Một câu lệnh SQL tương đương về ý tưởng là:

```sql
UPDATE inventory
SET available = available - ?
WHERE id = ?
  AND active = true
  AND ? > 0
  AND available >= ?;
```

JPQL trong repository sử dụng tên thuộc tính của entity; câu SQL minh họa sử dụng tên bảng và cột của database.

## 3. Kiểm tra số dòng bị ảnh hưởng

Với điều kiện `id` là khóa chính, câu lệnh trên thường chỉ có hai kết quả:

| Số dòng bị ảnh hưởng | Ý nghĩa |
|---:|---|
| 1 | Tìm thấy bản ghi thỏa điều kiện và đã cập nhật thành công |
| 0 | Không có bản ghi nào thỏa toàn bộ điều kiện |

Nếu kết quả là 0, có thể bản ghi không tồn tại, sản phẩm đã ngừng hoạt động hoặc tồn kho không đủ. Chỉ dựa vào số dòng bị ảnh hưởng thì không phân biệt được chính xác nguyên nhân nào.

Có thể xử lý kết quả tại service:

```java
package com.example.service;

import com.example.repository.InventoryRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryService {

    private final InventoryRepository inventoryRepository;

    public InventoryService(InventoryRepository inventoryRepository) {
        this.inventoryRepository = inventoryRepository;
    }

    @Transactional
    public boolean reserve(Long inventoryId, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "Quantity must be greater than zero");
        }

        int affected = inventoryRepository.reserveIfAvailable(
                inventoryId, quantity);

        if (affected > 1) {
            throw new IllegalStateException(
                    "An inventory ID updated more than one row");
        }

        return affected == 1;
    }
}
```

Service mở transaction cho thao tác nghiệp vụ. Khi repository trả về 1, việc giữ hàng thành công. Khi trả về 0, service có thể trả kết quả thất bại để tầng gọi quyết định cách phản hồi, chẳng hạn báo sản phẩm không còn đủ số lượng. Việc kiểm tra số dòng phải được thực hiện ngay sau câu lệnh cập nhật và nằm trong luồng xử lý của cùng transaction.

Với khóa chính, số dòng lớn hơn 1 là tình huống bất thường. Nếu cập nhật theo một điều kiện không duy nhất, hãy xác định rõ liệu số dòng lớn hơn 1 là kết quả hợp lệ hay dấu hiệu sai phạm vi cập nhật.

## 4. Vì sao cập nhật có điều kiện an toàn hơn khi có cạnh tranh?

Giả sử tồn kho ban đầu là 5 và hai transaction cùng yêu cầu giữ 4 sản phẩm. Mỗi transaction gửi câu lệnh có điều kiện:

```sql
UPDATE inventory
SET available = available - 4
WHERE id = 10 AND available >= 4;
```

Database điều phối các cập nhật đồng thời theo cơ chế khóa và mức cô lập của nó. Một transaction cập nhật thành công, tồn kho còn 1. Khi transaction còn lại thực hiện điều kiện trên phiên bản dữ liệu hiện hành, điều kiện `available >= 4` không còn đúng nên không cập nhật dòng nào.

Kết quả mong đợi là một transaction nhận số dòng bị ảnh hưởng bằng 1 và transaction còn lại nhận 0. Quyết định kiểm tra và ghi dữ liệu được thực hiện trong cùng câu lệnh, tránh khoảng thời gian giữa một lần đọc và một lần ghi riêng biệt.

Cơ chế cụ thể vẫn phụ thuộc database và isolation level. Với các thao tác cạnh tranh quan trọng, hãy kiểm thử bằng đúng hệ quản trị cơ sở dữ liệu và cấu hình transaction mà ứng dụng sử dụng.

## 5. Áp dụng cho chuyển trạng thái theo điều kiện nghiệp vụ

Conditional update cũng phù hợp khi một bản ghi chỉ được chuyển trạng thái nếu trạng thái hiện tại vẫn đúng như mong đợi. Ví dụ, chỉ chuyển đơn hàng từ `PENDING` sang `CONFIRMED` nếu nó vẫn đang ở trạng thái `PENDING`:

```java
@Modifying(clearAutomatically = true, flushAutomatically = true)
@Query("""
    update PurchaseOrder o
       set o.status = :newStatus
     where o.id = :id
       and o.status = :expectedStatus
    """)
int changeStatusIfExpected(
        @Param("id") Long id,
        @Param("expectedStatus") OrderStatus expectedStatus,
        @Param("newStatus") OrderStatus newStatus);
```

Nếu hai request cùng cố xác nhận một đơn hàng, request đầu tiên có thể cập nhật trạng thái. Request tiếp theo không còn thấy trạng thái hiện tại khớp với `expectedStatus`, nên nhận số dòng bị ảnh hưởng bằng 0. Service có thể coi đây là xung đột trạng thái hoặc yêu cầu đã được xử lý trước đó.

Cách này thường được gọi là compare-and-set: chỉ ghi giá trị mới nếu giá trị hiện tại vẫn bằng giá trị kỳ vọng.

## 6. Kết hợp với optimistic locking bằng @Version

JPA hỗ trợ optimistic locking qua thuộc tính `@Version`. Khi thao tác thông thường qua entity được quản lý, provider có thể dùng version để phát hiện dữ liệu đã bị transaction khác thay đổi.

Tuy nhiên, JPQL bulk update là thao tác trực tiếp trên database. Nó bỏ qua cơ chế dirty checking của các entity đang được quản lý và không tự động thực hiện kiểm tra hoặc tăng version như một lần cập nhật entity thông thường.

Nếu cần optimistic concurrency cho một bulk update, hãy đưa version kỳ vọng vào `WHERE` và chủ động tăng version trong `SET`. Ví dụ, entity có trường:

```java
@Version
private long version;
```

Phương thức cập nhật có thể có dạng:

```java
@Modifying(clearAutomatically = true, flushAutomatically = true)
@Query("""
    update Inventory i
       set i.available = i.available - :quantity,
           i.version = i.version + 1
     where i.id = :id
       and i.version = :expectedVersion
       and i.available >= :quantity
       and :quantity > 0
    """)
int reserveWithVersion(
        @Param("id") Long id,
        @Param("quantity") int quantity,
        @Param("expectedVersion") long expectedVersion);
```

Nếu version hiện tại không còn bằng `expectedVersion`, câu lệnh không cập nhật dòng nào. Số dòng bằng 0 báo rằng ít nhất một điều kiện không còn đúng. Khi sử dụng cách này, cần quản lý version nhất quán cho mọi đường ghi dữ liệu và kiểm thử với JPA provider cụ thể của dự án.

## 7. Ảnh hưởng của bulk update đến persistence context

Một câu lệnh bulk update tác động trực tiếp lên các dòng trong database. Persistence context hiện tại không tự đồng bộ lại các entity đã được tải trước đó. Vì thế, một entity đang được quản lý có thể vẫn giữ giá trị cũ trong bộ nhớ sau khi câu lệnh cập nhật thành công.

Hai thuộc tính của `@Modifying` trong ví dụ giải quyết vấn đề này:

- `flushAutomatically = true`: yêu cầu flush các thay đổi đang chờ trước khi chạy truy vấn cập nhật.
- `clearAutomatically = true`: yêu cầu clear persistence context sau khi chạy truy vấn, tránh tiếp tục sử dụng các entity đã lỗi thời.

Clear persistence context sẽ detach tất cả entity đang được quản lý trong context đó, không chỉ entity vừa cập nhật. Nếu không muốn clear toàn bộ, có thể bỏ tùy chọn này và chủ động refresh hoặc tải lại entity cần dùng sau bulk update. Không nên đọc lại một entity đã nằm trong persistence context rồi giả định rằng nó tự phản ánh giá trị database mới.

Bulk update cũng không thực hiện cascade như thao tác cập nhật entity thông thường và không gọi các callback vòng đời như `@PreUpdate` cho từng entity. Các quy tắc nghiệp vụ phụ thuộc callback, entity listener hoặc dirty checking cần được xử lý riêng khi dùng bulk update.

## 8. Lỗi thường gặp

- **Chỉ dùng `@Query` mà quên `@Modifying`:** Spring Data xử lý truy vấn như truy vấn đọc. Thêm `@Modifying` cho JPQL `UPDATE` hoặc `DELETE`.
- **Không có transaction:** câu lệnh thay đổi dữ liệu cần chạy trong transaction. Đặt `@Transactional` ở service bao quanh thao tác nghiệp vụ hoặc cấu hình transaction phù hợp ở repository.
- **Đọc entity rồi kiểm tra trước khi cập nhật:** điều kiện có thể lỗi thời khi transaction khác thay đổi cùng bản ghi. Đưa điều kiện quyết định vào `WHERE`.
- **Bỏ qua giá trị trả về:** ứng dụng có thể báo thành công dù không dòng nào được cập nhật. Luôn kiểm tra số dòng bị ảnh hưởng.
- **Coi số 0 là một nguyên nhân duy nhất:** số 0 chỉ cho biết không có dòng nào thỏa tất cả điều kiện. Hãy dùng thông báo tổng quát hoặc thực hiện bước chẩn đoán riêng nếu nghiệp vụ cần phân biệt.
- **Dùng entity đã tải trước bulk update:** entity trong persistence context có thể chứa dữ liệu cũ. Clear, refresh hoặc tải lại theo chiến lược phù hợp.
- **Cho rằng bulk update tự tăng `@Version`:** bulk update bỏ qua xử lý version tự động. Nếu cần kiểm tra version, hãy đưa version vào điều kiện và tăng nó một cách tường minh.
- **Để điều kiện cập nhật quá rộng:** câu lệnh có thể thay đổi nhiều dòng hơn dự kiến. Xác định khóa hoặc điều kiện nghiệp vụ đủ chặt và đánh giá số dòng trả về.

## 9. Ghi nhớ

Cập nhật nguyên tử bằng điều kiện nghiệp vụ giúp gom kiểm tra và thay đổi dữ liệu vào cùng một câu lệnh database. Trong Spring Data JPA, hãy khai báo JPQL `UPDATE` với `@Modifying`, đặt điều kiện bảo vệ dữ liệu trong `WHERE`, chạy trong transaction và kiểm tra số dòng bị ảnh hưởng. Đồng thời, cần xử lý trạng thái persistence context và version một cách chủ động vì bulk update không đi qua quy trình cập nhật entity thông thường.