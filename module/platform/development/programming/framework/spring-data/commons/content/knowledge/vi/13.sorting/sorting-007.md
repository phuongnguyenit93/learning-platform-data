# Thứ tự ổn định khi nhiều bản ghi cùng giá trị

Một danh sách đơn hàng được sắp theo `createdAt DESC` có thể vẫn thay đổi thứ tự giữa những đơn có cùng thời điểm tạo. Khi thêm phân trang hoặc giới hạn kết quả, sự mơ hồ đó có thể làm caller thấy một bản ghi hai lần hoặc bỏ qua một bản ghi, ngay cả khi không có yêu cầu nghiệp vụ nào thay đổi thứ tự.

Trong chương **Sắp xếp** của **SPRING_DATA_COMMONS**, bài này giải thích cách tạo thứ tự được xác định đầy đủ bằng nhiều khóa, triển khai bằng `Sort` và tên phương thức suy diễn, rồi kiểm tra hành vi khi các giá trị chính trùng nhau. Cần phân biệt mục tiêu này với việc tạo snapshot nhất quán khi dữ liệu đang thay đổi.

## 1. Sort theo một thuộc tính chưa chắc xác định toàn bộ thứ tự

Giả sử ba đơn hàng có cùng thời điểm tạo:

| id | createdAt |
| --- | --- |
| `41` | `2026-11-25T10:00:00Z` |
| `42` | `2026-11-25T10:00:00Z` |
| `43` | `2026-11-25T10:00:00Z` |

Yêu cầu:

```text
ORDER BY createdAt DESC
```

chỉ nói rằng các đơn có thời điểm lớn hơn phải đứng trước những đơn có thời điểm nhỏ hơn. Nó chưa nói `41`, `42`, `43` phải có thứ tự tương đối ra sao.

Các kết quả sau đều không mâu thuẫn với yêu cầu đó:

```text
41, 42, 43
43, 41, 42
42, 43, 41
```

Không nên dựa vào thứ tự insert, cấu trúc chỉ mục hiện tại hoặc kết quả quan sát được vài lần để suy ra một hợp đồng chưa được khai báo. Thay đổi execution plan, cách đọc dữ liệu hoặc trạng thái store có thể làm thứ tự của nhóm bằng nhau thay đổi.

### “Ổn định” trong bài có nghĩa gì?

Ở đây, mục tiêu là **thứ tự xác định trên cùng một tập dữ liệu và cùng quy tắc so sánh**: mỗi cặp bản ghi khác nhau có thể được phân định bởi bộ khóa sắp xếp đã chọn.

Khái niệm này khác với “stable sort” của một thuật toán trong bộ nhớ. Một thuật toán stable giữ thứ tự đầu vào của các phần tử bằng nhau. Nếu thứ tự đầu vào từ store vốn không có hợp đồng, giữ nguyên thứ tự đó không tự tạo ra một thứ tự nghiệp vụ xác định.

## 2. Thêm khóa phụ để phân định các giá trị bằng nhau

Một cách phổ biến là thêm định danh duy nhất vào cuối bộ khóa:

```text
createdAt DESC, id DESC
```

Cách đọc:

1. So sánh `createdAt`, thời điểm lớn hơn đứng trước.
2. Nếu `createdAt` bằng nhau, so sánh `id`, định danh lớn hơn đứng trước.

Với bảng ở phần trước, kết quả được xác định là:

```text
43, 42, 41
```

Khóa phụ không thay thế khóa chính. Nó chỉ được dùng khi các khóa đứng trước chưa phân định được hai bản ghi.

### Điều kiện để bộ khóa đủ phân định

Giả sử kết quả đang xét là các entity riêng biệt và `id`:

- Không null ở các entity đã được lưu.
- Duy nhất trong phạm vi kết quả.
- Có thể được store sắp xếp theo kiểu và mapping tương ứng.

Khi đó, thêm `id` làm khóa cuối giúp tránh hai entity khác nhau bằng nhau trên toàn bộ bộ khóa.

Không bắt buộc khóa cuối phải mang tên `id`. Nó có thể là một khóa nghiệp vụ hoặc một bộ thuộc tính tạo tính duy nhất, miễn đáp ứng đúng phạm vi và quy tắc so sánh.

### Chiều của khóa phụ là một lựa chọn hợp đồng

Cả hai thứ tự dưới đây đều có thể phân định nhóm trùng thời điểm:

```text
createdAt DESC, id DESC
createdAt DESC, id ASC
```

Chúng chọn thứ tự khác nhau trong nhóm bằng nhau. Không có quy tắc rằng khóa phụ luôn phải cùng chiều với khóa chính. Điều cần thiết là ứng dụng chọn rõ một quy ước và giữ nguyên khi phân trang hoặc tiếp tục cùng lượt duyệt.

Một id lớn hơn cũng không tự chứng minh entity được commit muộn hơn hoặc quan trọng hơn. Trong ví dụ, id chỉ giúp phân định các đơn có cùng `createdAt`.

## 3. Mô hình ví dụ và tập dữ liệu

Giả sử `PurchaseOrder` có các thuộc tính Java:

| Thuộc tính | Kiểu | Vai trò |
| --- | --- | --- |
| `id` | `Long` | Định danh duy nhất |
| `tenantId` | `String` | Phạm vi tổ chức |
| `status` | `OrderStatus` | Trạng thái đơn |
| `createdAt` | `Instant` | Thời điểm tạo, giả định không null |
| `total` | `BigDecimal` | Tổng tiền |

```java
public enum OrderStatus {
    NEW, PAID, CANCELLED
}
```

Các ví dụ đồng bộ chính dùng **Spring Data JPA** với entity và hạ tầng đã được ánh xạ phù hợp. `Sort`, `Pageable` và metadata phương thức là các abstraction dùng chung; cách thực thi vẫn thuộc module và store cụ thể.

Sau khi lọc đúng một tenant và trạng thái `PAID`, có dữ liệu:

| id | createdAt |
| --- | --- |
| `41` | `2026-11-25T10:00:00Z` |
| `42` | `2026-11-25T10:00:00Z` |
| `43` | `2026-11-25T10:00:00Z` |
| `44` | `2026-11-25T09:50:00Z` |
| `45` | `2026-11-25T09:50:00Z` |
| `46` | `2026-11-25T09:45:00Z` |

Thứ tự `createdAt DESC, id DESC` cho kết quả:

```text
43, 42, 41, 45, 44, 46
```

Với kích thước trang bằng `2`, trên dữ liệu không đổi:

| Trang, chỉ số từ 0 | Nội dung id |
| --- | --- |
| `0` | `43, 42` |
| `1` | `41, 45` |
| `2` | `44, 46` |

Đây là một hợp đồng có thể kiểm chứng cụ thể, thay vì chỉ nói “kết quả đã được sort”.

## 4. Ghép Sort theo đúng thứ tự ưu tiên

### 4.1. Một Sort có nhiều Order

```java
import org.springframework.data.domain.Sort;

Sort order = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id"));
```

Hoặc ghép bằng `and`:

```java
Sort order = Sort.by(Sort.Direction.DESC, "createdAt")
        .and(Sort.by(Sort.Direction.DESC, "id"));
```

Thứ tự các `Order` trong object là thứ tự ưu tiên. Đặt `id` đầu tiên sẽ tạo một yêu cầu khác:

```java
Sort order = Sort.by(Sort.Direction.DESC, "id")
        .and(Sort.by(Sort.Direction.DESC, "createdAt"));
```

Vì id đã duy nhất, khóa `createdAt` phía sau gần như không còn vai trò phân định giữa các entity khác nhau. Đó không còn là yêu cầu ưu tiên thời điểm tạo.

### 4.2. Sort được ghép bằng giá trị trả về

Mẫu sau không giữ khóa phụ như người viết có thể tưởng:

```java
Sort order = Sort.by(Sort.Direction.DESC, "createdAt");
order.and(Sort.by(Sort.Direction.DESC, "id"));
```

Cần dùng object được trả về từ phép ghép:

```java
order = order.and(Sort.by(Sort.Direction.DESC, "id"));
```

Tương tự, hai lần gán độc lập không tự ghép sort:

```java
Sort order = Sort.by(Sort.Direction.DESC, "createdAt");
order = Sort.by(Sort.Direction.DESC, "id");
```

Sau đoạn này, biến chỉ giữ sort theo id. Khóa thời gian đã bị thay thế.

### 4.3. Khi các hướng khác nhau, hãy viết tường minh

```java
Sort order = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("id"));
```

Cách viết này giúp người đọc không phải suy đoán việc một phép đổi chiều sau cùng có áp dụng cho cả bộ khóa hay không. Thứ tự hỗn hợp hoàn toàn có thể hợp lệ, nhưng mọi điểm tạo sort và tiếp tục truy vấn phải hiểu cùng quy ước.

## 5. Áp dụng vào repository và Pageable

Ví dụ repository:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.repository.Repository;

public interface PurchaseOrderRepository
        extends Repository<PurchaseOrder, Long> {

    Page<PurchaseOrder> findByTenantIdAndStatus(
            String tenantId,
            OrderStatus status,
            Pageable pageable);
}
```

Caller truyền toàn bộ bộ khóa qua `Pageable`:

```java
import org.springframework.data.domain.PageRequest;

Sort order = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id"));

Page<PurchaseOrder> page = repository.findByTenantIdAndStatus(
        "tenant-a",
        OrderStatus.PAID,
        PageRequest.of(0, 2, order));
```

`Pageable` đã chứa sort. Không thiết kế một method đồng thời nhận `Pageable` và một tham số `Sort` riêng để cùng điều khiển thứ tự truy vấn theo các cơ chế chuẩn tương ứng.

Những trang tiếp theo phải giữ nguyên bộ lọc và sort. Nếu trang đầu dùng `createdAt DESC, id DESC` nhưng trang sau chỉ dùng `createdAt DESC`, lượt duyệt không còn dựa trên cùng một hợp đồng thứ tự.

Các tên `createdAt`, `id`, `tenantId` ở đây là thuộc tính Java theo mapping. Không tự thay bằng tên cột vật lý như `created_at` trong `Sort` của một truy vấn entity JPA thông thường.

## 6. Thứ tự tĩnh trong tên phương thức

Nếu truy vấn luôn dùng cùng một thứ tự, có thể diễn đạt trực tiếp trong derived query:

```java
List<PurchaseOrder> findTop5ByTenantIdAndStatusOrderByCreatedAtDescIdDesc(
        String tenantId,
        OrderStatus status);
```

Tên được đọc thành:

```text
Lọc tenantId và status
    -> ưu tiên createdAt lớn hơn
    -> khi bằng thời điểm, ưu tiên id lớn hơn
    -> lấy tối đa 5 entity
```

`Top5` chỉ là giới hạn. Chính `OrderByCreatedAtDescIdDesc` xác định nhóm năm entity nào được ưu tiên.

Nếu chỉ có `findTop5By...` mà không có thứ tự phù hợp, không mặc định kết quả là năm đơn mới nhất. Nếu chỉ có `OrderByCreatedAtDesc` mà thiếu khóa phụ, vị trí trong nhóm trùng thời điểm vẫn chưa được mô tả đầy đủ.

### Thứ tự tĩnh và động có thể kết hợp

Với derived query Spring Data JPA, sort tĩnh có thể đứng trước sort động khi hai nguồn được kết hợp. Vì vậy, không nên khai báo tĩnh `OrderByIdDesc` rồi kỳ vọng một `Sort` động theo `createdAt` sẽ biến thời gian thành ưu tiên chính.

Nếu caller cần quyết định toàn bộ thứ tự, phương thức không có `OrderBy` tĩnh thường dễ quản lý hơn. Nếu cố ý kết hợp, cần xác nhận rõ thứ tự ưu tiên và trường hợp thuộc tính bị lặp ở hai nguồn.

Đây là chi tiết cần xem theo module; Commons không biến mọi nguồn khai báo truy vấn thành một quy tắc override duy nhất.

## 7. Vì sao thiếu khóa phụ có thể làm phân trang sai?

Giả sử dữ liệu không đổi, nhưng truy vấn chỉ xếp theo `createdAt DESC`.

Một lần lấy trang đầu có thể quan sát thứ tự hợp lệ:

```text
41, 42, 43, 44, 45, 46
```

Trang `0`, kích thước `2`, trả `41, 42`.

Một lần lấy trang sau có thể quan sát một thứ tự khác nhưng vẫn hợp lệ với cùng khóa chính:

```text
42, 43, 41, 45, 44, 46
```

Trang `1` bỏ qua hai vị trí đầu và trả `41, 45`. Caller đã thấy lại `41`.

Vấn đề không nhất thiết đến từ dữ liệu mới được chèn. Hai truy vấn độc lập chưa hề được yêu cầu thống nhất thứ tự trong nhóm bằng nhau.

Nếu sort đầy đủ là `createdAt DESC, id DESC`, cùng một tập dữ liệu và quy tắc so sánh sẽ cho cùng thứ tự logic. Đây là lý do khóa phụ quan trọng ngay cả với dữ liệu tĩnh.

Cùng vấn đề cũng ảnh hưởng giới hạn `First`/`Top`, chọn entity đại diện, hiển thị bảng và export theo từng phần. Chỉ kiểm tra tổng số entity phù hợp không phát hiện được việc một lượt duyệt bị lặp hoặc bỏ sót.

## 8. Thứ tự xác định không tạo snapshot khi dữ liệu thay đổi

Tiếp tục dùng bộ khóa đầy đủ `createdAt DESC, id DESC`:

```text
43, 42, 41, 45, 44, 46
```

Caller lấy trang đầu `43, 42`. Sau đó một đơn `47` được thêm với cùng thời điểm tạo như `43`:

```text
47, 43, 42, 41, 45, 44, 46
```

Trang tiếp theo bằng offset `2` trả `42, 41`. Entity `42` xuất hiện lại dù mỗi truy vấn đều có thứ tự đầy đủ.

Cần phân biệt ba bài toán:

| Bài toán | Cơ chế cần xem xét |
| --- | --- |
| Phân định các entity bằng nhau trên khóa chính | Khóa phụ hoặc bộ khóa duy nhất |
| Tiếp tục từ một mốc thay vì số vị trí đã bỏ qua | Seek/keyset/scrolling nếu module hỗ trợ |
| Cùng nhìn một phiên bản dữ liệu qua nhiều lần đọc | Transaction, snapshot, mốc chốt hoặc cơ chế nhất quán phù hợp store |

Thêm id giải quyết bài toán đầu. Nó không tự giải quyết đầy đủ hai bài toán sau.

### Khóa có thể thay đổi cần được đánh giá riêng

Nếu đang duyệt theo `updatedAt`, mỗi lần cập nhật entity có thể làm nó chuyển vị trí. Ngay cả keyset cũng cần đánh giá trường hợp entity đi qua mốc đã đọc.

`createdAt` thường thuận tiện nếu thực sự không đổi theo hợp đồng domain, nhưng không được coi tính bất biến đó là mặc định của mọi mapping. Hạ tầng auditing có thể cung cấp timestamp; nó không tự làm timestamp duy nhất hoặc tạo snapshot.

Tăng độ chính xác timestamp cũng không thay thế khóa phụ: nhiều thao tác có thể cùng giá trị và store có thể lưu với độ chính xác thấp hơn object Java ban đầu.

## 9. Bộ khóa đầy đủ là nền tảng cho keyset

Nếu module và loại truy vấn hỗ trợ keyset scrolling, vị trí tiếp tục cần phù hợp toàn bộ bộ khóa.

Ví dụ sort giảm dần:

```text
createdAt DESC, id DESC
```

Sau mốc `(lastCreatedAt, lastId)`, điều kiện tiếp tục về mặt logic là:

```sql
createdAt < :lastCreatedAt
or (createdAt = :lastCreatedAt and id < :lastId)
```

Điều kiện tenant và trạng thái vẫn phải được kết hợp đúng bên ngoài nhóm này. Đây là mô hình để hiểu so sánh bộ khóa, không phải một câu SQL phải chép nguyên vào mọi store.

Nếu thứ tự đổi thành `createdAt DESC, id ASC`, phần so sánh id trong cùng nhóm thời gian cũng phải đổi tương ứng. Không tái sử dụng cursor được tạo theo một thứ tự khác.

### Cursor phải giữ đủ thông tin

Một cursor chỉ có id không tự đại diện cho bộ khóa `(createdAt, id)`. Module phải trích xuất được những giá trị cần thiết để tiếp tục đúng.

Nếu dùng projection trực tiếp, cần bảo đảm các khóa phục vụ keyset có trong kết quả theo yêu cầu module. Đối với keyset JPA, điều kiện non-null của các thuộc tính sort cũng cần được thỏa mãn.

Keyset không tự là snapshot. Nếu entity đã đọc bị sửa khóa để chuyển về phía sau mốc, hoặc entity chưa đọc chuyển lên phía trước mốc, một lượt duyệt vẫn có thể bị ảnh hưởng. Cần chọn mức nhất quán phù hợp với feed, export hoặc tác vụ xử lý cụ thể.

## 10. Chọn khóa phụ theo phạm vi và đơn vị kết quả

### 10.1. Duy nhất trong một tenant khác với duy nhất toàn tập

Giả sử `localNumber` chỉ duy nhất trong một tenant. Khi truy vấn cố định một tenant, nó có thể là khóa cuối phù hợp nếu các điều kiện khác được thỏa mãn.

Nếu truy vấn trả nhiều tenant, `localNumber` riêng lẻ có thể trùng. Cần một bộ khóa đủ phân định, chẳng hạn gồm cả `tenantId` và `localNumber`, hoặc dùng định danh toàn cục phù hợp.

Với composite id, tên đường dẫn sort phải theo mapping thực tế, ví dụ các thuộc tính bên trong embedded id. Không tự giả định mọi module chấp nhận cùng một cú pháp đường dẫn.

### 10.2. Định danh entity gốc chưa chắc duy nhất cho dòng join

Một đơn hàng có nhiều dòng chi tiết. Nếu truy vấn trả từng dòng join, nhiều kết quả có cùng `order.id`.

Khi đó thêm `order.id` không đủ phân định mọi dòng. Cần xác định đơn vị mà API đang trả:

- Nếu trả từng đơn hàng, cần thiết kế truy vấn và việc loại trùng/phân trang phù hợp với đơn vị entity gốc.
- Nếu trả từng dòng chi tiết, khóa cuối có thể cần định danh dòng chi tiết hoặc một bộ khóa tương đương.
- Nếu trả nhóm tổng hợp, cần bộ khóa phân định các nhóm kết quả.

Không thêm `distinct` như một cách sửa mọi vấn đề mà chưa xác định entity, dòng hay nhóm nào đang được sắp và đếm.

### 10.3. Khóa phải thực sự sắp xếp được ở store

Một khóa duy nhất trong mô hình không tự bảo đảm mọi backend hoặc loại truy vấn đều cho sort theo khóa đó. Cần xác nhận kiểu dữ liệu, mapping, chỉ mục và khả năng của module.

Đặc biệt, một cursor backend hoặc một field điểm số của hệ tìm kiếm không tự trở thành thuộc tính sort Commons có cùng ngữ nghĩa trên mọi store. Hợp đồng thứ tự phải phù hợp API thực tế được sử dụng.

## 11. Null, collation và cách so sánh

### 11.1. Null ordering phải được hiểu rõ

Nếu khóa chính cho phép null, cần quyết định null đứng trước hay sau trong hợp đồng hiển thị và kiểm tra store có thực thi được yêu cầu đó không.

Commons có cách biểu đạt gợi ý như:

```java
Sort order = Sort.by(
        Sort.Order.desc("createdAt").nullsLast(),
        Sort.Order.desc("id"));
```

Gợi ý null handling không phải một cam kết mọi module, provider hoặc truy vấn native đều hỗ trợ giống nhau. Ví dụ chính của bài giả định `createdAt` không null để tập trung vào tie-breaker.

Một khóa id duy nhất có thể phân định các entity trong cùng nhóm giá trị null nếu store có thứ tự và mapping phù hợp. Nhưng điều đó không loại bỏ các hạn chế non-null của một cơ chế keyset cụ thể.

### 11.2. Các giá trị khác nhau có thể được so là bằng nhau

Khi sort chuỗi, collation có thể coi hai cách viết hoa/thường hoặc dấu khác nhau là tương đương ở một mức so sánh nào đó. Vì vậy không chỉ nhìn giá trị source khác nhau rồi kết luận nó đủ phân định theo comparator của store.

Ví dụ, sort theo tên không phân biệt hoa thường vẫn cần khóa phụ để phân định hai khách hàng được coi là bằng nhau theo tên. Một định danh số duy nhất thường giúp ví dụ dễ hiểu, nhưng khả năng cụ thể vẫn phụ thuộc store.

Nếu một backend và Java dùng quy tắc so sánh khác nhau, sort lại phần nội dung trong Java có thể tạo một thứ tự khác. Không nên dựa vào hai comparator khác nhau cho hai phần của cùng một lượt phân trang mà không có thiết kế rõ ràng.

## 12. Chuẩn hóa sort ở một ranh giới chung

Nếu nhiều endpoint cho chọn sort, có thể tập trung chính sách bổ sung khóa phụ để giảm việc mỗi caller tự ghép khác nhau.

Ví dụ hàm Java minh họa, nhận một `Sort` đã được tầng ứng dụng kiểm tra thuộc tính và hướng hợp lệ:

```java
static Sort withIdTieBreaker(Sort requested) {
    if (requested.isUnsorted()) {
        return Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id"));
    }

    if (requested.getOrderFor("id") != null) {
        return requested;
    }

    return requested.and(Sort.by(Sort.Direction.DESC, "id"));
}
```

Hàm này dựa trên giả định id là duy nhất trong đơn vị kết quả. Nếu caller đã yêu cầu sort theo id ở một vị trí, bộ khóa đã có khả năng phân định các entity, nên ví dụ không thêm lại id với hướng khác.

Đây không phải một bộ chuẩn hóa dùng được nguyên vẹn cho mọi domain. Với composite key, join hoặc nhóm tổng hợp, chính sách phải khác. Nếu một API chỉ hỗ trợ vài thứ tự nghiệp vụ, có thể ánh xạ trực tiếp:

| Lựa chọn API | Bộ khóa nội bộ |
| --- | --- |
| Mới nhất | `createdAt DESC, id DESC` |
| Cũ nhất | `createdAt ASC, id ASC` |
| Giá trị cao nhất | `total DESC, id DESC` |

Điều quan trọng là cùng một lựa chọn luôn tạo cùng toàn bộ bộ khóa, và lần truy vấn tiếp theo không làm mất phần khóa phụ.

## 13. Chỉ mục và chi phí thực thi

Thêm khóa phụ làm hợp đồng rõ ràng, nhưng cũng thay đổi yêu cầu sắp xếp của truy vấn. Chỉ mục chỉ hỗ trợ một phần bộ lọc hoặc bộ khóa có thể khiến store cần thêm công việc sort.

Với mẫu lọc `tenantId`, `status` rồi sort `createdAt`, `id`, cần đánh giá chỉ mục theo toàn bộ hình dạng truy vấn trên hệ quản trị thực tế. Hướng khóa, phân bố dữ liệu và khả năng tận dụng thứ tự của chỉ mục khác nhau theo backend.

Không coi đây là lý do bỏ khóa phụ để có một kế hoạch có vẻ nhanh hơn trên dữ liệu nhỏ. Trước hết cần giữ đúng hợp đồng kết quả, sau đó đánh giá execution plan và thiết kế truy cập phù hợp.

Tương tự, `Top5` hoặc kích thước trang nhỏ không bảo đảm store chỉ phải đọc đúng năm dòng. Nó có thể cần lọc/sort một tập lớn hoặc xử lý join trước khi tạo nội dung cuối.

Không có index hint hay annotation Commons chung nào tự chứng minh truy vấn đã được tối ưu chỉ vì bộ khóa đủ phân định.

## 14. Kiểm thử thứ tự khi có giá trị trùng

### 14.1. Fixture phải thật sự tạo tie

Một test chỉ có các thời điểm khác nhau không kiểm tra được vai trò của id. Cần tạo nhiều entity có cùng giá trị khóa chính, với số lượng đủ để nhóm bằng nhau đi qua ranh giới trang hoặc giới hạn.

Những giá trị thời gian được kỳ vọng bằng nhau nên bằng nhau sau khi lưu và đọc theo độ chính xác của store. Không chỉ dựa vào khác biệt nanosecond trên object Java nếu database sẽ làm tròn hoặc cắt độ chính xác.

### 14.2. Kiểm tra cả thứ tự, không chỉ tập id

Với dữ liệu minh họa, truy vấn đầy đủ kỳ vọng:

```text
43, 42, 41, 45, 44, 46
```

Một assertion chỉ so sánh `Set` của các id có thể pass dù thứ tự hoàn toàn khác. Cần kiểm tra chuỗi có thứ tự hoặc các thuộc tính thứ tự theo hợp đồng.

Ví dụ assertion JUnit minh họa sau khi đã lấy kết quả từ fixture có id như bảng:

```java
List<Long> actualIds = result.stream()
        .map(PurchaseOrder::getId)
        .toList();

assertEquals(List.of(43L, 42L, 41L, 45L, 44L, 46L), actualIds);
```

Nếu id được store sinh tự động, không ép giá trị cố định như bảng. Hãy xây fixture và expected result từ các định danh thật đã lưu, đồng thời giữ rõ những nhóm nào phải bằng nhau ở khóa chính.

### 14.3. Kiểm tra ranh giới trang

Trên dữ liệu không đổi, lấy lần lượt các trang và xác nhận:

- Nội dung từng trang khớp bộ khóa đã chọn.
- Nhóm có cùng thời điểm được chia qua trang đúng theo id.
- Ghép nội dung các trang không lặp và không thiếu entity phù hợp.
- Entity ngoài tenant/trạng thái không xuất hiện.
- Sort trong yêu cầu tiếp theo vẫn có khóa phụ.

Nếu query trả `Page`, tổng số vẫn cần được kiểm tra đúng bộ lọc; một tổng đúng không tự chứng minh thứ tự đúng.

### 14.4. Không trông chờ truy vấn thiếu khóa phụ luôn biểu hiện lỗi

Một database có thể tình cờ trả cùng thứ tự của nhóm bằng nhau trong nhiều lần chạy. Vì vậy test không nên yêu cầu truy vấn thiếu id “chắc chắn phải đảo thứ tự” để chứng minh vấn đề.

Mục tiêu của test là xác nhận hợp đồng có khóa phụ cho kết quả đúng với fixture tạo tie. Việc một truy vấn thiếu hợp đồng chưa biểu hiện lỗi trong môi trường thử không biến nó thành một thứ tự được bảo đảm.

Nếu ứng dụng có yêu cầu với insert/update đồng thời, cần thêm kịch bản riêng để kiểm tra mô hình nhất quán đã chọn. Không dùng kết quả trên fixture tĩnh để tuyên bố phân trang luôn không lặp trong mọi điều kiện.

## 15. Lỗi thường gặp và cách chỉnh

| Biểu hiện | Nguyên nhân có thể có | Hướng xử lý |
| --- | --- | --- |
| Các đơn trùng thời điểm đổi vị trí | Chỉ sort theo `createdAt` | Thêm khóa đủ phân định, giữ đúng ưu tiên |
| Đã gọi `and` nhưng query vẫn thiếu id | Bỏ qua object Sort trả về | Ghép và gán/return toàn bộ Sort |
| Đơn mới nhất không đứng đầu | Id vô tình trở thành khóa đầu | Đặt khóa nghiệp vụ trước, khóa phụ sau |
| Phân trang lặp dù có id | Dữ liệu thay đổi giữa các lần đọc hoặc sort không được giữ nguyên | Tách vấn đề snapshot, offset và tie-breaker |
| TopN chọn khác nhau trong nhóm bằng nhau | Thiếu sort đầy đủ trước giới hạn | Bổ sung OrderBy hoặc Sort phù hợp |
| Id không phân định được mọi dòng | Query trả dòng join hoặc id chỉ duy nhất cục bộ | Xác định đơn vị kết quả và bộ khóa đúng phạm vi |
| Cursor không tiếp tục đúng | Thiếu khóa, đổi sort hoặc khóa đã biến đổi | Đối chiếu bộ khóa và cơ chế scrolling của module |
| Null ordering không như yêu cầu | Store không hỗ trợ gợi ý theo cách dự kiến | Xác nhận khả năng module/provider và hợp đồng null |
| Test pass nhưng không kiểm chứng tie | Fixture chỉ có giá trị khóa chính khác nhau | Thêm dữ liệu trùng và ranh giới trang phù hợp |
| Chỉ so sánh Set của id | Assertion bỏ qua thứ tự | Assert một sequence có thứ tự |

## 16. Bài tập phân tích

### Bài 1: Hoàn thiện sort mới nhất

Một method đang nhận:

```java
Sort.by(Sort.Direction.DESC, "createdAt")
```

Trong domain, nhiều entity có cùng `createdAt`, id là số duy nhất và không null sau khi lưu. Hãy công bố một quy ước phân định rõ ràng.

**Gợi ý:** ghép `id DESC` để có `createdAt DESC, id DESC`, hoặc chọn một hướng id khác nếu hợp đồng ứng dụng yêu cầu. Điều cần xác nhận là toàn bộ bộ khóa được giữ trong mọi lần gọi.

### Bài 2: Hai trang trên dữ liệu đang đổi

Caller đọc `43, 42`, sau đó entity `47` được chèn vào trước chúng. Trang offset tiếp theo trả lại `42`.

**Phân tích:** khóa phụ vẫn có thể đúng; đây là sự dịch chuyển vị trí do dữ liệu thay đổi. Cần đánh giá offset, keyset và yêu cầu snapshot, không xóa khóa phụ hoặc đảo hướng sort ngẫu nhiên.

### Bài 3: Một khóa chỉ duy nhất trong tenant

Mỗi tenant có `localNumber` bắt đầu từ cùng một dải số. Một báo cáo trả dữ liệu nhiều tenant, sort theo `createdAt DESC, localNumber DESC`.

**Phân tích:** hai entity ở hai tenant có thể cùng thời điểm và localNumber. Cần thêm khóa đủ phân định trong toàn bộ kết quả, chẳng hạn tenantId cùng localNumber ở vị trí phù hợp, hoặc một id toàn cục.

### Bài 4: Root id trên kết quả join

Một đơn có ba dòng chi tiết. Query trả ba dòng nhưng đều có cùng `orderId`; người viết thêm `orderId` làm khóa cuối.

**Phân tích:** orderId không duy nhất cho đơn vị kết quả là dòng chi tiết. Cần khóa của dòng, hoặc thay đổi query để thực sự trả một kết quả trên mỗi đơn theo yêu cầu sản phẩm.

### Bài 5: Test đúng phần cần chứng minh

Một kiểm tra so sánh tập id trên dữ liệu chỉ có timestamp khác nhau, rồi kết luận tie-breaker đã đúng.

**Phân tích:** test chưa có tie và cũng bỏ qua thứ tự. Cần fixture có nhiều giá trị chính bằng nhau, rồi assert thứ tự và ranh giới trang theo bộ khóa đầy đủ.

## 17. Các điểm cần nhớ

- Một khóa sort có thể chỉ xác định thứ tự giữa các nhóm, chưa xác định thứ tự bên trong nhóm bằng nhau.
- Khóa phụ duy nhất trong đúng phạm vi và đúng đơn vị kết quả giúp bộ khóa phân định đầy đủ trên dữ liệu không đổi.
- Thứ tự các `Sort.Order` là thứ tự ưu tiên; phép ghép cần giữ giá trị trả về và không làm mất khóa nghiệp vụ ban đầu.
- Tên derived query, Sort động và Pageable phải cùng thể hiện hợp đồng thứ tự nhất quán.
- Thứ tự xác định, keyset và snapshot là các bài toán liên quan nhưng khác nhau; thêm id không tự giải quyết mọi thay đổi đồng thời.
- Null, collation, projection, join, chỉ mục và khả năng của store đều có thể ảnh hưởng việc thực thi và kiểm chứng bộ khóa.
