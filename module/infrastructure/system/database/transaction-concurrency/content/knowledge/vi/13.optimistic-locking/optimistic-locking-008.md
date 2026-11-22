# Khóa lạc quan trên một hàng và bất biến nhiều hàng

Khóa lạc quan (optimistic locking) là cách phát hiện xung đột khi nhiều giao dịch cùng đọc rồi cập nhật dữ liệu. Thay vì giữ khóa trong suốt thời gian ứng dụng xử lý, mỗi giao dịch đọc dữ liệu kèm một dấu phiên bản. Khi ghi, giao dịch chỉ được cập nhật nếu phiên bản trong cơ sở dữ liệu vẫn bằng phiên bản mà nó đã đọc. Nếu một giao dịch khác đã thay đổi hàng trước đó, điều kiện phiên bản không còn đúng và lần cập nhật hiện tại không tác động hàng nào.

Cách làm này rất phù hợp khi xung đột không thường xuyên, transaction ngắn và nhiều người dùng có thể đọc cùng một bản ghi. Tuy nhiên, khóa lạc quan theo phiên bản của từng hàng chỉ phát hiện được những giao dịch cùng cạnh tranh trên hàng đó. Một quy tắc nghiệp vụ có thể phụ thuộc vào nhiều hàng, trong khi các giao dịch lại cập nhật các hàng khác nhau. Khi đó, từng lần ghi đều có vẻ hợp lệ nhưng kết quả kết hợp có thể phá vỡ bất biến toàn cục.

Bài học này đi từ cơ chế version trên một hàng đến giới hạn của nó với bất biến nhiều hàng, sau đó trình bày các cách tạo điểm xung đột chung hoặc dùng cơ chế cô lập mạnh hơn.

## 1. Khóa lạc quan là gì?

Giả sử bảng `product` có một hàng biểu diễn tên và giá sản phẩm:

| product_id | name | price | version |
| --- | --- | ---: | ---: |
| 501 | Bàn phím | 750000 | 7 |

Cột `version` là số phiên bản của hàng. Khi người dùng mở trang chỉnh sửa, ứng dụng đọc giá trị cùng `version = 7`. Trong lúc người dùng chỉnh sửa, một người khác có thể thay đổi giá sản phẩm và làm phiên bản tăng lên 8.

Khi người dùng đầu tiên lưu thay đổi, ứng dụng gửi câu lệnh chỉ cập nhật hàng nếu phiên bản vẫn là 7:

```sql
UPDATE product
SET price = 720000,
    version = version + 1
WHERE product_id = 501
  AND version = 7;
```

Nếu hàng vẫn có `version = 7`, câu lệnh cập nhật một hàng và tăng phiên bản lên 8. Nếu một giao dịch khác đã cập nhật trước, phiên bản hiện tại có thể đã là 8; điều kiện `version = 7` không còn đúng và câu lệnh cập nhật 0 hàng.

Ứng dụng dựa vào số hàng bị tác động để nhận biết kết quả:

- **Một hàng được cập nhật:** phiên bản khớp, thay đổi đã được ghi nhận.
- **Không có hàng nào được cập nhật:** dữ liệu đã thay đổi sau lần đọc, hàng đã bị xóa, hoặc điều kiện tìm kiếm không còn đúng. Ứng dụng cần xác định đây là xung đột hay trường hợp không tìm thấy bản ghi.

Điểm cốt lõi là thao tác ghi có điều kiện so sánh phiên bản (compare-and-swap). Việc đọc dữ liệu không giữ một khóa dài hạn để ngăn người khác chỉnh sửa. Xung đột được phát hiện tại thời điểm ghi.

## 2. Quy trình đọc, kiểm tra phiên bản và cập nhật

Một quy trình khóa lạc quan điển hình có các bước:

1. Đọc hàng cần xử lý, bao gồm các cột nghiệp vụ và cột phiên bản.
2. Ứng dụng tính toán thay đổi dựa trên dữ liệu vừa đọc.
3. Gửi `UPDATE` với điều kiện `id` và `version` cũ.
4. Trong cùng câu lệnh, tăng phiên bản để đánh dấu lần cập nhật mới.
5. Kiểm tra số hàng bị tác động. Nếu bằng 0, báo xung đột hoặc thực hiện lại quy trình với dữ liệu mới.
6. Commit transaction nếu mọi thay đổi cần thiết đều thành công.

Ví dụ đầy đủ:

```sql
BEGIN;

SELECT quantity, version
FROM inventory
WHERE product_id = 501;
-- Giả sử đọc được quantity = 12, version = 4.

UPDATE inventory
SET quantity = 10,
    version = version + 1
WHERE product_id = 501
  AND version = 4;

-- Ứng dụng phải kiểm tra số hàng cập nhật.
-- Nếu là 0: ROLLBACK và xử lý xung đột.

COMMIT;
```

Trong ứng dụng thực tế, `quantity = 10` được tính từ dữ liệu đọc ban đầu. Nếu số hàng cập nhật là 0, không được giả định thay đổi đã thành công. Transaction phải rollback các thao tác liên quan, sau đó ứng dụng có thể đọc lại dữ liệu và yêu cầu người dùng xác nhận hoặc tính toán lại.

Điều kiện phiên bản và thao tác tăng phiên bản phải nằm trong cùng một câu `UPDATE` nguyên tử. Nếu ứng dụng chỉ đọc `version`, so sánh ở bộ nhớ rồi cập nhật bằng `WHERE id = ...` mà không kiểm tra lại phiên bản trong câu SQL, một giao dịch khác vẫn có thể ghi xen giữa bước kiểm tra và bước cập nhật.

## 3. Vì sao cần cột version?

Một cột version giúp xác định liệu hàng có thay đổi kể từ lần đọc trước hay không. Có thể dùng số nguyên tăng dần, token ngẫu nhiên hoặc dấu thời gian, nhưng số nguyên thường dễ hiểu và ít phụ thuộc vào độ chính xác đồng hồ.

Ví dụ cấu trúc bảng:

```sql
CREATE TABLE inventory (
    product_id BIGINT PRIMARY KEY,
    quantity INTEGER NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    CHECK (quantity >= 0)
);
```

Mỗi lần cập nhật qua cơ chế khóa lạc quan, câu lệnh phải tăng version:

```sql
UPDATE inventory
SET quantity = :new_quantity,
    version = version + 1
WHERE product_id = :product_id
  AND version = :expected_version;
```

Một số lưu ý khi thiết kế version:

- **Tăng phiên bản trong cơ sở dữ liệu:** `version = version + 1` tránh việc nhiều ứng dụng tự tính cùng một giá trị phiên bản mới.
- **Không bỏ qua cột version ở một đường ghi:** nếu một batch job hoặc câu SQL khác sửa dữ liệu mà không tăng version, giao dịch đang giữ phiên bản cũ có thể không phát hiện được thay đổi đó.
- **Dùng kiểu đủ lớn:** số nguyên 64 bit làm giảm nguy cơ tràn số trong hệ thống cập nhật thường xuyên.
- **Không dùng thời gian tùy tiện làm version:** hai thay đổi có thể có timestamp giống nhau do độ chính xác hoặc cách tạo thời gian; đồng hồ giữa các máy cũng có thể lệch.
- **Tăng version cả khi xóa nếu cần kiểm tra stale delete:** câu `DELETE` cũng có thể dùng `WHERE id = :id AND version = :expected_version`.
- **Không tái sử dụng version cũ:** nếu một hàng bị xóa rồi tạo lại với cùng ID và version quay về giá trị cũ, có thể xuất hiện vấn đề ABA. Có thể dùng sequence đơn điệu, UUID token mới hoặc cơ chế định danh phiên bản không bị tái sử dụng.

Version chỉ có ý nghĩa khi mọi đường ghi liên quan tuân thủ cùng quy ước. Nếu một thao tác cập nhật không tăng version, optimistic locking không thể nhận biết thao tác đó.

## 4. Ví dụ hai người cùng sửa một hàng

Ban đầu sản phẩm có giá 750.000 và version 7. Người dùng A và B cùng đọc bản ghi.

| Thời điểm | Giao dịch A | Giao dịch B |
| --- | --- | --- |
| 1 | Đọc giá 750.000, version 7 | |
| 2 | | Đọc giá 750.000, version 7 |
| 3 | Đổi giá thành 720.000, cập nhật với `version = 7` | |
| 4 | Cập nhật 1 hàng; version thành 8 | |
| 5 | COMMIT | |
| 6 | | Đổi giá thành 700.000, cập nhật với `version = 7` |
| 7 | | Cập nhật 0 hàng vì version hiện tại là 8 |

Giao dịch B đã đọc một phiên bản cũ nên không thể âm thầm ghi đè thay đổi của A. Ứng dụng có thể hiển thị thông báo “Dữ liệu đã được người khác cập nhật. Hãy tải lại và kiểm tra thay đổi mới nhất.”

Đây là trường hợp khóa lạc quan hoạt động đúng mục tiêu: hai người cùng sửa một hàng và một trong hai phải xử lý xung đột.

## 5. Xử lý khi optimistic update không thành công

Khi `UPDATE` tác động 0 hàng, ứng dụng không nên luôn thông báo một lỗi chung. Có thể xảy ra một số tình huống:

- Hàng vẫn tồn tại nhưng version đã thay đổi: xung đột cập nhật.
- Hàng đã bị xóa: bản ghi không còn tồn tại.
- Điều kiện nghiệp vụ khác trong `WHERE` không còn đúng: thao tác không còn được phép.
- ID hoặc phạm vi tenant không đúng: bản ghi không thuộc đối tượng người dùng có quyền truy cập.

Nếu cần phân biệt, ứng dụng có thể đọc lại hàng sau khi câu lệnh cập nhật thất bại. Việc đọc này chỉ phục vụ thông báo hoặc quyết định nghiệp vụ; không được dùng để coi lần ghi trước là thành công.

Một số lựa chọn xử lý:

1. **Yêu cầu người dùng tải lại:** phù hợp với màn hình chỉnh sửa, biểu mẫu quản trị hoặc nội dung mà người dùng cần xem và hợp nhất thay đổi.
2. **Tự tính lại và thử lại:** phù hợp khi phép cập nhật có thể tính lại từ dữ liệu mới, ví dụ cộng một lượng tồn kho hoặc tăng bộ đếm.
3. **Trả về lỗi xung đột:** phù hợp với API, có thể ánh xạ sang HTTP `409 Conflict` hoặc một mã lỗi nghiệp vụ tương đương.
4. **Hủy toàn bộ transaction:** cần thiết nếu transaction đã thực hiện thêm thao tác khác mà tính đúng đắn của chúng phụ thuộc vào lần cập nhật thất bại.

Không phải mọi xung đột đều nên retry tự động. Nếu hai người sửa cùng trường `description`, việc tự động ghi lại giá trị của người đến sau có thể làm mất nội dung của người trước. Nếu thao tác là “tăng số lượng thêm 1”, có thể đọc lại giá trị mới rồi áp dụng phép tăng một lần, miễn là ứng dụng bảo đảm không thực hiện trùng tác dụng phụ.

## 6. Optimistic locking trong ORM

Nhiều ORM hỗ trợ versioning để giảm mã SQL thủ công. Ví dụ, trong JPA, một thuộc tính được đánh dấu `@Version`:

```java
@Entity
public class Inventory {
    @Id
    private Long productId;

    private int quantity;

    @Version
    private long version;
}
```

Khi ORM tải entity, nó lưu giá trị version. Khi flush hoặc commit thay đổi, ORM tạo câu cập nhật có điều kiện theo ID và version cũ, đồng thời tăng version. Nếu không có hàng nào được cập nhật vì version đã thay đổi, ORM phát sinh ngoại lệ optimistic locking, chẳng hạn `OptimisticLockException` trong JPA.

Một số điểm cần nhớ:

- Ngoại lệ có thể xuất hiện tại lúc flush hoặc commit, không nhất thiết ngay tại lời gọi setter.
- Nếu transaction đã thất bại do optimistic conflict, thường cần rollback transaction và bắt đầu transaction mới trước khi thử lại.
- Entity detached hoặc dữ liệu được gửi từ client vẫn cần mang version đã đọc. Không nên thay version cũ bằng version hiện tại ở server rồi ghi đè, vì như vậy sẽ bỏ qua mục tiêu phát hiện stale update.
- Các câu SQL bulk update hoặc native query có thể bỏ qua cơ chế version tự động của ORM. Nếu dùng chúng, cần tự tăng và kiểm tra version, đồng thời đồng bộ lại persistence context khi cần.
- Version của một entity bảo vệ hàng mà entity đại diện. Nó không tự động bảo vệ mọi hàng liên quan hoặc mọi điều kiện nghiệp vụ trong các bảng khác.

## 7. Vì sao version của từng hàng chưa bảo vệ bất biến nhiều hàng?

Bất biến (invariant) là điều kiện phải luôn đúng trong trạng thái dữ liệu đã commit. Một số bất biến chỉ phụ thuộc một hàng, chẳng hạn `quantity >= 0`. Một số khác phụ thuộc nhiều hàng hoặc cả tập dữ liệu, ví dụ:

- Luôn phải có ít nhất một bác sĩ đang trực.
- Tổng số chỗ đã đặt không được vượt sức chứa.
- Tổng số tiền phân bổ không được vượt ngân sách.
- Không có hai lịch đặt phòng giao nhau.
- Một nhóm phải luôn có ít nhất một quản trị viên đang hoạt động.

Khóa lạc quan theo hàng chỉ so sánh version của hàng được cập nhật. Nếu hai transaction cập nhật hai hàng khác nhau, cả hai có thể thành công dù chúng cùng dựa trên một điều kiện toàn cục.

### Ví dụ: luôn phải có ít nhất một người trực

Ban đầu có hai bác sĩ đang trực:

| doctor_id | on_call | version |
| --- | --- | ---: |
| 10 | TRUE | 5 |
| 20 | TRUE | 8 |

T1 muốn cho bác sĩ 10 nghỉ. T2 muốn cho bác sĩ 20 nghỉ. Cả hai cùng đọc danh sách bác sĩ và thấy có hai người trực.

```sql
-- T1: cập nhật hàng của bác sĩ 10
UPDATE doctor_shift
SET on_call = FALSE,
    version = version + 1
WHERE doctor_id = 10
  AND version = 5;

-- T2: cập nhật hàng của bác sĩ 20
UPDATE doctor_shift
SET on_call = FALSE,
    version = version + 1
WHERE doctor_id = 20
  AND version = 8;
```

Mỗi câu lệnh cập nhật đúng một hàng có version chưa thay đổi. Vì T1 ghi hàng 10 còn T2 ghi hàng 20, không có xung đột version trên cùng hàng. Cả hai có thể commit, khiến không còn ai trực.

| Transaction | Hàng được cập nhật | Version được kiểm tra | Kết quả riêng lẻ |
| --- | --- | ---: | --- |
| T1 | Bác sĩ 10 | 5 | Thành công |
| T2 | Bác sĩ 20 | 8 | Thành công |

Từng thao tác đều hợp lệ theo version của hàng nó sửa, nhưng trạng thái cuối vi phạm bất biến “phải còn ít nhất một người trực”. Đây là dạng write skew. Việc thêm cột version cho mọi hàng không tự động phát hiện xung đột trên điều kiện `COUNT(*)`.

## 8. Bảo vệ bất biến nhiều hàng bằng điểm xung đột chung

Một cách phổ biến là tạo một hàng đại diện cho quy tắc hoặc nhóm dữ liệu. Mọi transaction có thể làm thay đổi bất biến phải cùng cập nhật hàng này bằng optimistic compare-and-swap. Khi đó, dù chúng sửa các hàng chi tiết khác nhau, chúng vẫn cạnh tranh trên cùng một version.

### Ví dụ: hàng guard cho lịch trực

Tạo hàng `shift_policy` cho một nhóm:

| group_id | version |
| --- | ---: |
| 1 | 12 |

Mọi thao tác thay đổi trạng thái trực của nhóm 1 phải cập nhật version của hàng guard trong cùng transaction. Giả sử T1 và T2 đều đã đọc `version = 12`:

```sql
-- T1 và T2 đều cố giành quyền thay đổi nhóm bằng cùng version.
UPDATE shift_policy
SET version = version + 1
WHERE group_id = 1
  AND version = 12;
```

Chỉ một transaction có thể cập nhật hàng guard từ version 12. Transaction còn lại sẽ gặp xung đột ghi hoặc cập nhật 0 hàng sau khi transaction thắng commit, tùy isolation level và hệ quản trị. Transaction thất bại phải rollback cả thay đổi bác sĩ đã thực hiện trước đó.

Quy trình khái quát:

1. Đọc version của hàng guard và trạng thái các bác sĩ liên quan.
2. Tính toán thay đổi và kiểm tra bất biến trên dữ liệu đã đọc.
3. Cập nhật các hàng chi tiết bằng version tương ứng.
4. Cập nhật hàng guard với điều kiện version cũ.
5. Nếu bất kỳ cập nhật nào không thành công, rollback toàn bộ transaction.
6. Nếu mọi cập nhật thành công, commit.

Có thể cập nhật hàng guard ở đầu transaction để các transaction cùng nhóm nhanh chóng cạnh tranh trên một điểm. Tuy nhiên, nếu transaction đã tạo snapshot trước khi chờ guard, nó có thể tiếp tục đọc snapshot cũ tùy isolation level. Vì vậy, cần kiểm tra thứ tự tạo snapshot của hệ quản trị, hoặc dùng isolation level/cơ chế đảm bảo transaction kiểm tra lại dữ liệu sau khi giành được guard. Dùng Serializable là lựa chọn rõ ràng hơn khi không thể chứng minh tính đúng đắn của thứ tự đọc và khóa.

Hàng guard chỉ có tác dụng khi **mọi đường ghi có thể ảnh hưởng đến bất biến đều cập nhật nó**. Nếu một batch job, API khác hoặc thao tác quản trị thay đổi lịch trực mà bỏ qua hàng guard, cơ chế bảo vệ sẽ bị phá vỡ.

## 9. Bảo vệ tổng số bằng hàng tổng hợp và cập nhật có điều kiện

Với bất biến về sức chứa hoặc ngân sách, có thể lưu giá trị tổng hợp trong một hàng và cập nhật nguyên tử bằng điều kiện. Ví dụ phòng có sức chứa 10 người, hiện đã đặt 7 chỗ. Một giao dịch muốn thêm 2 chỗ:

```sql
UPDATE room_capacity
SET reserved_count = reserved_count + 2,
    version = version + 1
WHERE room_id = 7
  AND reserved_count + 2 <= capacity;
```

Ứng dụng kiểm tra số hàng được cập nhật:

- Một hàng: giữ chỗ thành công.
- Không hàng nào: phòng không tồn tại hoặc không còn đủ sức chứa.

Mọi giao dịch đặt chỗ của phòng 7 đều cập nhật cùng hàng `room_capacity`, nên các lần ghi cạnh tranh trên cùng một hàng. Sau khi cập nhật bộ đếm thành công, transaction chèn chi tiết reservation trong cùng transaction. Nếu chèn chi tiết thất bại, rollback phải hoàn tác cả bộ đếm.

Có thể thêm constraint để bảo vệ phạm vi của bộ đếm:

```sql
ALTER TABLE room_capacity
ADD CONSTRAINT ck_reserved_capacity
CHECK (reserved_count >= 0 AND reserved_count <= capacity);
```

Constraint trên bảo vệ bất biến của chính hàng `room_capacity`. Nó không tự chứng minh rằng `reserved_count` luôn bằng tổng `guest_count` trong bảng reservation. Tính đồng nhất giữa số tổng hợp và dữ liệu chi tiết cần được duy trì bằng cách buộc mọi thao tác chèn, sửa, hủy reservation cập nhật bộ đếm trong cùng transaction, hoặc bằng một mô hình dữ liệu khác có bảo đảm tương đương.

Mẫu tương tự dùng được cho ngân sách:

```sql
UPDATE project_budget
SET allocated_amount = allocated_amount + :amount,
    version = version + 1
WHERE project_id = :project_id
  AND allocated_amount + :amount <= budget_limit
  AND version = :expected_version;
```

Nếu cập nhật không tác động hàng nào, ứng dụng không được chèn chi tiết phân bổ như thể đã thành công. Cần rollback hoặc xử lý kết quả không đủ ngân sách/xung đột version.

## 10. Constraint, Serializable và các cách phối hợp

Không phải bất biến nào cũng nên giải quyết bằng hàng guard. Hãy chọn cơ chế phù hợp với bản chất của quy tắc:

| Loại bất biến | Cơ chế thường phù hợp | Lý do |
| --- | --- | --- |
| Một hàng không được có số lượng âm | `CHECK (quantity >= 0)` và cập nhật có điều kiện | Điều kiện nằm hoàn toàn trong một hàng |
| Email hoặc mã nghiệp vụ phải duy nhất | `UNIQUE` | Cơ sở dữ liệu kiểm tra tính duy nhất trên mọi luồng ghi |
| Không được có hai lịch đặt giao nhau | Exclusion constraint nếu hỗ trợ, hoặc Serializable/range locking | Điều kiện liên quan đến khoảng dữ liệu, kể cả hàng mới |
| Tổng số chỗ không vượt sức chứa | Hàng tổng hợp cập nhật nguyên tử hoặc Serializable | Các lần đặt phải cạnh tranh trên cùng tổng hoặc được tuần tự hóa |
| Luôn còn ít nhất một người trực | Hàng guard chung hoặc Serializable | Các transaction sửa hàng khác nhau nhưng cùng ảnh hưởng một điều kiện tập hợp |
| Chuyển tiền giữa hai tài khoản | Version cho cả hai hàng, cập nhật nguyên tử và constraint phù hợp | Cần phát hiện thay đổi trên từng tài khoản và giữ cân bằng trong cùng transaction |

### Serializable

Serializable yêu cầu kết quả transaction tương đương một thứ tự chạy tuần tự. Tùy hệ quản trị, cơ chế thực hiện có thể dùng khóa, predicate/range lock hoặc theo dõi phụ thuộc rồi hủy transaction có nguy cơ. Với Serializable Snapshot Isolation, transaction vẫn có thể đọc snapshot nhưng có thể nhận serialization failure khi commit hoặc trong quá trình thực thi.

Ứng dụng phải sẵn sàng rollback và retry **toàn bộ transaction** với snapshot mới. Không nên chỉ retry câu UPDATE cuối vì quyết định nghiệp vụ được đưa ra từ dữ liệu đã đọc trước đó.

### Constraint

Constraint thường là lựa chọn mạnh cho quy tắc cơ sở dữ liệu có thể biểu diễn trực tiếp. `UNIQUE`, `PRIMARY KEY`, `FOREIGN KEY` và `CHECK` giúp bảo vệ dữ liệu ngay cả khi có nhiều ứng dụng hoặc batch job cùng ghi. Nhưng một `CHECK` thông thường thường chỉ biểu diễn điều kiện trên hàng hiện tại; không nên giả định nó kiểm tra an toàn tổng `COUNT` hoặc `SUM` trên các hàng khác.

### Hàng guard hoặc hàng tổng hợp

Hàng guard tạo một điểm xung đột chung bằng version; hàng tổng hợp lưu một giá trị như `reserved_count` để cập nhật nguyên tử. Cả hai đều có thể tăng contention vì nhiều transaction cùng cập nhật một hàng. Cần cân nhắc mức tranh chấp, độ nóng của tài nguyên và khả năng chia nhỏ nhóm dữ liệu.

## 11. Bảo vệ transaction cập nhật nhiều hàng

Một transaction có thể cần cập nhật nhiều hàng, ví dụ chuyển tiền giữa hai tài khoản. Optimistic locking có thể kiểm tra version trên từng hàng:

```sql
BEGIN;

UPDATE account
SET balance = balance - 50,
    version = version + 1
WHERE account_id = 100
  AND version = :version_100
  AND balance >= 50;

-- Phải kiểm tra cập nhật đúng 1 hàng.

UPDATE account
SET balance = balance + 50,
    version = version + 1
WHERE account_id = 200
  AND version = :version_200;

-- Phải kiểm tra cập nhật đúng 1 hàng.

COMMIT;
```

Nếu một trong hai câu lệnh cập nhật 0 hàng, transaction phải rollback để không trừ tiền mà không cộng tiền, hoặc ngược lại. Việc kiểm tra version ở cả hai hàng phát hiện thay đổi đồng thời trên một trong hai tài khoản.

Để giảm deadlock trong những đường ghi dùng khóa, các giao dịch nên xử lý tài khoản theo thứ tự ID nhất quán. Với optimistic update thuần túy, cơ sở dữ liệu vẫn có thể khóa nội bộ khi thực thi UPDATE; thứ tự cập nhật nhất quán cũng giúp giảm tình trạng chờ vòng.

Nếu bất biến là tổng tiền giữa hai tài khoản phải được bảo toàn, việc cập nhật cả hai hàng trong cùng transaction là thiết yếu. Không được commit giữa hai câu lệnh. Constraint có thể bảo vệ các giới hạn từng hàng, còn transaction bảo đảm hai thay đổi cùng thành công hoặc cùng bị rollback.

## 12. Khi nào nên dùng optimistic locking?

Khóa lạc quan thường phù hợp khi:

- Nhiều thao tác chủ yếu đọc và chỉ một tỷ lệ nhỏ thao tác ghi đụng cùng một hàng.
- Người dùng có thể giữ biểu mẫu mở lâu; ứng dụng muốn phát hiện bản ghi đã thay đổi trước khi lưu.
- Transaction ngắn, có thể tính lại kết quả sau xung đột.
- Việc giữ khóa trong suốt thời gian xử lý sẽ gây chờ không cần thiết.
- Ứng dụng cần phản hồi rõ ràng khi dữ liệu người dùng đang sửa đã bị thay đổi.

Khóa bi quan hoặc cơ chế tuần tự hóa có thể phù hợp hơn khi xung đột xảy ra thường xuyên, thao tác cần bảo đảm tức thời trên tài nguyên nóng, hoặc retry tốn kém. Một số hệ thống kết hợp cả hai: dùng optimistic version cho chỉnh sửa thông thường, dùng transaction Serializable hoặc khóa điều phối cho các nghiệp vụ có bất biến nhiều hàng.

## 13. Những lỗi thiết kế thường gặp

### So sánh version ở ứng dụng nhưng không đưa vào câu UPDATE

Đọc version rồi kiểm tra trong Java hoặc trong service không đủ. Giao dịch khác vẫn có thể cập nhật sau bước kiểm tra. Version cũ phải nằm trong điều kiện `WHERE` của câu lệnh ghi.

### Quên tăng version ở một đường ghi

Nếu một câu SQL, batch job hoặc native query cập nhật hàng mà không tăng version, các client đang giữ version cũ có thể không phát hiện thay đổi. Mọi đường ghi cần tuân thủ quy ước version.

### Bỏ qua số hàng bị cập nhật

Một câu `UPDATE` trả về 0 hàng không phải là thành công. Nếu ứng dụng vẫn tiếp tục commit các thay đổi phụ thuộc vào nó, trạng thái dữ liệu có thể sai.

### Dùng version của một hàng để đại diện cho cả nhóm nhưng không cập nhật ở mọi luồng

Hàng guard chỉ bảo vệ được bất biến nếu tất cả giao dịch có thể thay đổi bất biến đều cùng cập nhật hàng đó. Một luồng ghi bỏ qua guard là đủ để phá vỡ quy tắc.

### Chỉ kiểm tra từng hàng dù quy tắc nằm trên nhiều hàng

Hai version riêng biệt có thể đều khớp khi hai giao dịch sửa hai hàng khác nhau. Cần tạo điểm xung đột chung, dùng constraint thích hợp hoặc Serializable để bảo vệ điều kiện tập hợp.

### Retry một phần transaction

Khi optimistic conflict hoặc serialization failure xảy ra, dữ liệu mà quyết định nghiệp vụ dựa vào có thể đã lỗi thời. Cần rollback và chạy lại toàn bộ đơn vị công việc có liên quan, không chỉ gửi lại câu lệnh cuối một cách máy móc.

## 14. Quy trình kiểm thử

Để kiểm tra optimistic locking trên một hàng:

1. Tạo một hàng với version ban đầu, ví dụ 1.
2. Mở hai phiên làm việc và cho cả hai đọc cùng giá trị cùng version.
3. Cho phiên A cập nhật với `WHERE version = 1`, tăng version lên 2 và commit.
4. Cho phiên B cập nhật với `WHERE version = 1`.
5. Xác nhận phiên B cập nhật 0 hàng hoặc nhận lỗi xung đột phù hợp với ORM/engine.
6. Xác nhận ứng dụng không ghi đè dữ liệu của A và có xử lý xung đột rõ ràng.

Để kiểm tra bất biến nhiều hàng:

1. Tạo trạng thái ban đầu thỏa điều kiện, ví dụ hai người đang trực.
2. Cho T1 và T2 cùng đọc trạng thái đó.
3. T1 cập nhật hàng người trực thứ nhất; T2 cập nhật hàng thứ hai, mỗi câu dùng version riêng.
4. Commit theo lịch xen kẽ.
5. Nếu cả hai cùng commit và điều kiện bị phá vỡ, version từng hàng chưa bảo vệ được bất biến.
6. Bật cơ chế hàng guard, hàng tổng hợp, constraint hoặc Serializable rồi chạy lại cùng lịch.
7. Xác nhận một transaction bị từ chối, phải retry hoặc bị tuần tự hóa, và trạng thái cuối vẫn thỏa điều kiện.

Kiểm thử cần chạy với isolation level và hệ quản trị thật của ứng dụng. Mô phỏng trong một test tuần tự không thể tái hiện đầy đủ cuộc đua giữa các transaction.

## 15. Những điểm cần ghi nhớ

- Optimistic locking dùng version hoặc token để phát hiện hàng đã thay đổi kể từ lần đọc.
- Câu UPDATE phải so sánh version cũ trong `WHERE`, tăng version trong cùng câu lệnh và kiểm tra số hàng bị tác động.
- Khi version không khớp, ứng dụng cần xử lý xung đột, tải lại hoặc retry toàn bộ transaction khi phù hợp.
- Version của một hàng bảo vệ cạnh tranh trên hàng đó; nó không tự động bảo vệ điều kiện phụ thuộc nhiều hàng.
- Write skew có thể xảy ra khi các transaction đọc cùng trạng thái nhưng cập nhật những hàng khác nhau, khiến bất biến tập hợp bị vi phạm.
- Có thể bảo vệ bất biến nhiều hàng bằng constraint, hàng guard/version chung, hàng tổng hợp cập nhật nguyên tử hoặc Serializable.
- Mọi đường ghi phải tuân thủ cùng quy ước version/guard; một đường ghi bỏ qua cơ chế có thể làm mất bảo đảm.
- Với transaction cập nhật nhiều hàng, mọi bước phải nằm trong cùng transaction và bất kỳ xung đột nào cũng phải dẫn đến rollback toàn bộ thay đổi phụ thuộc.
