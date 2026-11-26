# KeysetScrollPosition và bộ khóa tiếp tục truy vấn

Khi cuộn qua một tập dữ liệu lớn, ứng dụng không nhất thiết phải nói “bỏ qua 100.000 bản ghi rồi lấy tiếp”. Với keyset scrolling, ứng dụng mô tả một ranh giới bằng các giá trị đã thấy, chẳng hạn: “tiếp tục sau đơn hàng có thời điểm tạo và id này, theo đúng thứ tự đã chọn”.

`KeysetScrollPosition` thuộc Spring Data Commons biểu diễn loại vị trí đó. Nó mang bộ giá trị khóa và hướng cuộn. Module của store phải có khả năng chuyển vị trí này thành điều kiện truy vấn phù hợp.

Một vị trí không tự là một truy vấn hoàn chỉnh: nó không thay thế bộ lọc, quyền truy cập, thứ tự, mapping hay cấu hình nguồn dữ liệu.

Sau bài học, bạn cần có khả năng:

- Giải thích bộ khóa tiếp tục và quan hệ của nó với thứ tự truy vấn.
- Phân biệt keyset position, offset và giới hạn một lần lấy.
- Đọc điều kiện so sánh nhiều khóa theo thứ tự từ điển.
- Tiếp tục từ `Window.positionAt(...)` mà không lặp hoặc bỏ qua ranh giới do lỗi sử dụng API.
- Thiết kế projection và token khôi phục giữ đúng tên, kiểu và độ chính xác của khóa.
- Nhận ra giới hạn về null, index, cập nhật dữ liệu và checkpoint.

## 1. Keyset position biểu diễn ranh giới, không phải số trang

So sánh hai cách mô tả việc lấy tiếp:

| Cách tiếp cận | Thông tin tiếp tục | Ý nghĩa |
|---|---|---|
| Offset | Một số lượng phần tử cần bỏ qua | Bắt đầu sau một vị trí đếm trong tập kết quả |
| Keyset | Giá trị của các thuộc tính sắp xếp tại ranh giới | Tìm những phần tử đứng sau ranh giới theo thứ tự đã xác định |

Ví dụ với thứ tự:

```text
createdAt DESC, id DESC
```

một bộ khóa có thể mang:

```text
createdAt = 2026-04-10T11:00:00Z
id        = 503
```

Nó không có nghĩa “phần tử thứ 503” và cũng không có nghĩa offset bằng 503.

Id có thể có khoảng trống, được cấp theo cơ chế khác hoặc chỉ là một thành phần của định danh. Ý nghĩa tiếp tục đến từ toàn bộ thứ tự, không từ việc id có trông giống một số thứ tự hay không.

### 1.1. Ba thông tin cần phân biệt

- **Bộ lọc:** xác định những đối tượng thuộc tập cần duyệt.
- **Sort:** xác định quan hệ đứng trước/đứng sau.
- **Keyset position:** xác định ranh giới hiện tại trong quan hệ thứ tự đó.

Giới hạn mỗi lần lấy lại là thông tin khác, chẳng hạn 3 hoặc 100 phần tử. Position không phải một `PageRequest` và không cung cấp tổng số phần tử/số trang.

### 1.2. Vị trí ban đầu không phải một khóa giả

Dùng factory của Commons:

```java
import org.springframework.data.domain.KeysetScrollPosition;
import org.springframework.data.domain.ScrollPosition;

KeysetScrollPosition initial = ScrollPosition.keyset();
```

Vị trí ban đầu chưa có bộ giá trị của một bản ghi đã thấy. Nó biểu diễn bắt đầu cuộn, không phải “sau id 0”, “sau timestamp nhỏ nhất” hoặc một hàng đặc biệt.

Không tự tạo khóa giả nếu dữ liệu thực tế có thể nằm ngoài giả định đó.

## 2. Vì sao cần một thứ tự xác định và đủ phân xử?

Giả sử các đơn hàng thuộc cùng tenant và trạng thái, được sắp:

```text
createdAt DESC, id DESC
```

Dữ liệu:

| id | createdAt |
|---:|---|
| 505 | 11:00 |
| 504 | 11:00 |
| 503 | 11:00 |
| 502 | 11:00 |
| 501 | 10:59 |
| 500 | 10:58 |
| 499 | 10:58 |

Một lần lấy tối đa 3 phần tử trả:

```text
[505, 504, 503]
```

Bộ khóa cuối là `(11:00, 503)`. Lần tiếp theo cần nhận:

```text
[502, 501, 500]
```

Nếu chỉ lưu `createdAt = 11:00` rồi yêu cầu `createdAt < 11:00`, đơn 502 bị bỏ qua. Nếu dùng `createdAt <= 11:00`, các đơn đã đọc có thể xuất hiện lại.

Khóa id làm rõ vị trí bên trong nhóm có cùng thời điểm.

### 2.1. Khóa sắp xếp và định danh không phải lúc nào cũng trùng nhau

Bộ khóa tiếp tục có thể gồm:

- Thuộc tính nghiệp vụ dùng để sắp xếp, như `createdAt`, `priority`, `score`.
- Những thành phần định danh cần để phân xử duy nhất.

Trong các module hỗ trợ keyset filtering, framework có thể bổ sung định danh vào sort để bảo đảm tính duy nhất. Ví dụ trong bài vẫn khai báo id tường minh để hợp đồng dễ đọc.

Nếu domain dùng composite id, có thể cần nhiều thành phần định danh. Không mặc định mọi bộ khóa chỉ là `Map.of("id", ...)`.

### 2.2. Các giá trị phải đi cùng đúng Sort

Map khóa không tự nói thuộc tính nào là tiêu chí đầu hoặc tiêu chí nào giảm dần. Thứ tự các key trong một JSON object hay vòng lặp map không thay thế mô tả sort.

Cùng bộ giá trị `createdAt` và `id`, nhưng đổi từ `createdAt DESC, id DESC` sang `id ASC` là đổi quan hệ thứ tự. Không dùng lại position rồi mong framework suy ra ý nghĩa cũ.

## 3. Điều kiện tiếp tục là so sánh theo thứ tự từ điển

Với sort:

```text
createdAt DESC, id DESC
```

và ranh giới `(lastCreatedAt, lastId)`, điều kiện đi tiếp về phía sau của thứ tự này là:

```text
createdAt < lastCreatedAt
OR
(createdAt = lastCreatedAt AND id < lastId)
```

Tiêu chí đầu được xét trước. Chỉ khi bằng nhau mới so tiêu chí tiếp theo.

### 3.1. Minh họa bằng SQL quan hệ

Đây là SQL giải thích ý nghĩa trong một hệ quản trị hỗ trợ cú pháp tương ứng; không phải ngôn ngữ truy vấn chung của Commons:

```sql
SELECT id, tenant_id, status, created_at
FROM purchase_order
WHERE tenant_id = :tenantId
  AND status = :status
  AND (
       created_at < :lastCreatedAt
       OR (
            created_at = :lastCreatedAt
            AND id < :lastId
       )
  )
ORDER BY created_at DESC, id DESC
LIMIT :batchSize
```

Nhóm điều kiện keyset phải được đặt trong đúng ngoặc để cả hai nhánh đều nằm trong tenant/status đã chọn.

Một lỗi đặt ngoặc có thể làm nhánh `OR` thoát khỏi bộ lọc. Keyset position không tự bảo vệ phạm vi dữ liệu khi ứng dụng viết query tùy chỉnh sai.

Ở lần đầu chưa có ranh giới, query bắt đầu từ đầu tập đã lọc theo sort. Không cần gán một timestamp/id giả vào điều kiện trên.

### 3.2. Nhiều tiêu chí có hướng khác nhau

Giả sử sort:

```text
priority DESC, createdAt ASC, id ASC
```

Đi tiếp theo thứ tự đó có dạng logic:

```text
priority < lastPriority

OR (
  priority = lastPriority
  AND createdAt > lastCreatedAt
)

OR (
  priority = lastPriority
  AND createdAt = lastCreatedAt
  AND id > lastId
)
```

Không thể thay bằng một điều kiện đơn `id > lastId` khi id không phải tiêu chí chính.

Cũng không dùng cùng một dấu so sánh cho mọi khóa: chiều ASC/DESC của từng thuộc tính quyết định cách so sánh của nó.

### 3.3. Hướng cuộn khác hướng của từng thuộc tính

`KeysetScrollPosition` còn có hướng cuộn, chẳng hạn đi tới hoặc đi lùi tương đối với thứ tự truy vấn.

- Sort `DESC` không có nghĩa position phải có hướng backward.
- Đi forward theo `createdAt DESC` sẽ đi về các thời điểm nhỏ hơn.
- Đi backward là tìm về phía trước ranh giới trong quan hệ thứ tự đã chọn.

Đi lùi còn cần chọn đúng ranh giới, thường liên quan phần tử đầu của cửa sổ hiện tại. Không chỉ đổi một dấu so sánh trong query nhiều khóa rồi giữ mọi xử lý khác như cũ.

Khả năng đi lùi và cách trình bày thứ tự cửa sổ cần được kiểm chứng trên module sử dụng. Các ví dụ thực thi dưới đây tập trung vào cuộn forward.

## 4. Ví dụ repository trả Window trong phạm vi hỗ trợ

Ví dụ đặt trong Spring Data JPA với derived query và keyset scrolling được module/phiên bản sử dụng hỗ trợ. Giả sử entity `PurchaseOrder` có:

- `id`: định danh kiểu `Long`, duy nhất và không null.
- `tenantId`, `status`: thuộc tính dùng để lọc.
- `createdAt`: thời điểm tạo kiểu `Instant`, không null.

Mapping, kết nối và repository scanning đã được cấu hình.

```java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderScrollRepository
        extends JpaRepository<PurchaseOrder, Long> {

    Window<PurchaseOrder>
    findFirst3ByTenantIdAndStatusOrderByCreatedAtDescIdDesc(
        String tenantId,
        String status,
        ScrollPosition position
    );
}
```

Trong chữ ký:

- `First3` giới hạn kích thước cửa sổ theo cơ chế module hỗ trợ.
- Tenant và status xác định tập cần đọc.
- `OrderByCreatedAtDescIdDesc` xác định thứ tự.
- `ScrollPosition` là tham số điều khiển tiếp tục.
- `Window` mang nội dung, thông tin còn cửa sổ sau và khả năng lấy position tại phần tử.

Ví dụ dùng kiểu tham số `ScrollPosition` chung, nhưng phiên duyệt bên dưới luôn bắt đầu và tiếp tục bằng keyset position. Không đổi loại position giữa phiên mà không thiết kế lại hợp đồng.

### 4.1. Lấy cửa sổ đầu tiên

```java
ScrollPosition position = ScrollPosition.keyset();

Window<PurchaseOrder> window =
    repository
        .findFirst3ByTenantIdAndStatusOrderByCreatedAtDescIdDesc(
            tenantId,
            status,
            position
        );
```

Với dữ liệu đầu bài, nội dung đầu là `[505, 504, 503]`.

Vị trí ban đầu không thêm một ranh giới khóa đã xử lý. Query vẫn có tenant, status, sort và giới hạn.

### 4.2. Lấy position từ phần tử cuối hợp lệ

```java
if (!window.isEmpty() && window.hasNext()) {
    ScrollPosition next =
        window.positionAt(window.size() - 1);

    Window<PurchaseOrder> following =
        repository
            .findFirst3ByTenantIdAndStatusOrderByCreatedAtDescIdDesc(
                tenantId,
                status,
                next
            );
}
```

Position lấy tại phần tử cuối mô tả ranh giới để tiếp tục sau phần tử đó. Nếu tiếp tục đi forward đúng hợp đồng, phần tử ranh giới không được trả lại như phần tử đầu của cửa sổ kế.

Index hợp lệ thuộc nội dung cửa sổ. Không dùng `window.size()` làm index và không gọi `positionAt(-1)` khi cửa sổ rỗng.

### 4.3. Vòng lặp forward

```java
ScrollPosition position = ScrollPosition.keyset();

while (true) {
    Window<PurchaseOrder> window =
        repository
            .findFirst3ByTenantIdAndStatusOrderByCreatedAtDescIdDesc(
                tenantId,
                status,
                position
            );

    if (window.isEmpty()) {
        break;
    }

    for (PurchaseOrder order : window) {
        process(order);
    }

    if (!window.hasNext()) {
        break;
    }

    position = window.positionAt(window.size() - 1);
}
```

`process(order)` là công việc nghiệp vụ của ứng dụng, không phải một phương thức do Commons tự cung cấp.

Vòng lặp này giữ nguyên bộ lọc và sort. Nó chỉ đổi ranh giới sau khi đã xử lý nội dung cửa sổ hiện tại.

Không cần gọi một query đếm để biết tổng số trang trước khi duyệt. Đồng thời, `Window` không cung cấp một tổng chính xác chỉ vì ứng dụng đã duyệt được một vài cửa sổ.

### 4.4. HasNext là metadata của cửa sổ

Module có thể cần lấy thêm dữ liệu để xác định còn cửa sổ sau theo cơ chế của nó. Caller nên sử dụng `window.hasNext()` thay vì tự suy rằng “có đúng 3 phần tử thì chắc chắn còn”.

Một cửa sổ cuối vẫn có thể đầy đúng kích thước. Chỉ nhìn độ dài content chưa đủ để biết đã hết.

## 5. Quan sát bộ khóa từ KeysetScrollPosition

Với một cửa sổ không rỗng:

```java
import java.util.Map;

import org.springframework.data.domain.KeysetScrollPosition;
import org.springframework.data.domain.ScrollPosition;

ScrollPosition continuation =
    window.positionAt(window.size() - 1);

if (continuation instanceof KeysetScrollPosition keyset) {
    Map<String, Object> values = keyset.getKeys();
    ScrollPosition.Direction direction = keyset.getDirection();

    boolean initial = keyset.isInitial();
}
```

Các ví dụ pattern matching trong bài giả định Java 17 trở lên.

Ý nghĩa:

| Thông tin | Vai trò |
|---|---|
| `getKeys()` | Các giá trị thuộc tính cần cho ranh giới keyset |
| `getDirection()` | Hướng cuộn tương đối với sort |
| `isInitial()` | Chưa có ranh giới từ dữ liệu hay đã có |

Với mô hình phẳng đã nêu, position sau đơn 503 có thể chứa các entry cho `createdAt` và `id`.

Tên key cần khớp với cách module mô tả thuộc tính. Không lấy tên cột SQL rồi tự thay tên key chỉ vì cột lưu dưới dạng `created_at`.

### 5.1. Bộ khóa không chỉ là một giá trị id

Khi sort có `createdAt` trước id, chỉ lưu id sẽ làm mất dữ liệu để tạo điều kiện so sánh theo thời gian.

Ngược lại, lưu mỗi thời điểm làm mất vị trí trong nhóm cùng thời điểm. Cần giữ đầy đủ những giá trị mà quá trình keyset của module yêu cầu.

Với sort, projection hoặc composite id khác, bộ key có thể khác ví dụ. Ưu tiên lấy position từ kết quả do module cung cấp thay vì tự đoán tên và số thành phần.

### 5.2. Position không giữ toàn bộ ngữ cảnh truy vấn

Bộ khóa không tự bảo đảm:

- Tenant hiện tại còn giống tenant lúc tạo position.
- Bộ lọc status không thay đổi.
- Caller vẫn có cùng quyền truy cập.
- Sort vẫn có cùng thứ tự và hướng.
- Mapping hoặc quy tắc collation vẫn tương thích.
- Nội dung được đọc ở cùng snapshot.

Ứng dụng phải giữ hoặc kiểm tra những điều kiện đó khi khôi phục phiên duyệt.

### 5.3. Không dùng thứ tự của Map làm thứ tự so sánh

Ngay cả khi một lần in map cho thấy id đứng trước createdAt, sort của query vẫn là nguồn xác định thứ tự so sánh.

JSON parser, kiểu map hoặc cách serialize có thể thay thứ tự entry. Đừng xây lại sort bằng cách lặp các entry rồi lấy thứ tự xuất hiện làm hợp đồng.

## 6. Khôi phục một position đã biết khóa

Factory của `ScrollPosition` có thể tạo position với bộ khóa và hướng tương ứng. Ví dụ forward cho đúng mô hình đang học:

```java
import java.time.Instant;
import java.util.Map;

Instant lastCreatedAt =
    Instant.parse("2026-04-10T11:00:00Z");
Long lastId = 503L;

Map<String, Object> keys = Map.of(
    "createdAt", lastCreatedAt,
    "id", lastId
);

KeysetScrollPosition restored =
    ScrollPosition.forward(keys);
```

Đối tượng này chỉ mang metadata. Tạo được nó không chứng minh key đủ, kiểu đúng hay query hiện tại tương thích.

Trước khi gọi repository, ứng dụng phải xác định rằng:

- Bộ khóa thực sự thuộc sort/query được cho phép.
- Giá trị có đúng kiểu domain.
- Direction được API cho phép.
- Ngữ cảnh tenant và bộ lọc vẫn phù hợp.

Factory backward biểu diễn một hướng khác; nó không tự biến token forward thành một thao tác “trang trước” đầy đủ mà không chọn đúng ranh giới.

### 6.1. Không cần tải lại bản ghi ranh giới chỉ để biết các khóa

Nếu đã giữ đủ giá trị, điều kiện tiếp tục có thể được tạo từ chúng ngay cả khi bản ghi ranh giới đã bị xóa.

Chỉ lưu id rồi phụ thuộc vào việc tìm lại bản ghi để lấy createdAt tạo thêm một phụ thuộc: bản ghi đó có thể không còn hoặc thuộc tính đã bị sửa.

Điều này không làm keyset trở thành snapshot. Nó chỉ cho thấy vì sao cần giữ bộ giá trị của ranh giới, thay vì coi position là một lời nhắc “đi tìm lại entity cũ”.

## 7. Điều kiện để keyset filtering hoạt động đúng

### 7.1. Các thuộc tính khóa cần không null

Keyset filtering dựa trên các phép so sánh lớn hơn/nhỏ hơn và bằng nhau. Null không tham gia những phép so sánh đó như một giá trị thông thường.

Trong cơ chế keyset filtering của Spring Data đang xét, các thuộc tính tham gia bộ khóa cần không null. Không giả định thêm một hint `nullsLast()` là đã giải quyết khả năng tiếp tục qua các hàng null.

Cần xem cả:

- Ràng buộc domain.
- Mapping và schema thực tế.
- Dữ liệu đã tồn tại.
- Kết quả projection có thật sự cung cấp giá trị không null không.

Một annotation non-null trên API chưa chứng minh database không có null.

Nếu use case có giá trị thiếu, cần chọn cách biểu diễn hoặc mô hình truy vấn phù hợp mà store/module hỗ trợ. Đừng tự đặt một giá trị thay thế khác nghĩa trong token rồi áp lại lên cột gốc.

### 7.2. Phải lấy được đầy đủ khóa từ kết quả

Muốn tạo position tại một phần tử, hạ tầng phải đọc được các giá trị cần thiết của phần tử đó.

Ví dụ, nếu query chỉ trả một DTO chứa `total` mà sort cần `createdAt` và id, module không có đủ dữ liệu để trích xuất ranh giới theo hợp đồng keyset.

Một projection nội bộ phù hợp cho mô hình này có thể gồm:

```java
import java.time.Instant;

public interface OrderCursorView {
    Long getId();

    Instant getCreatedAt();
}
```

Projection thực tế còn có thể mang các trường nghiệp vụ khác. Những thuộc tính dùng để sort và phân xử cần có trong kết quả theo cơ chế module yêu cầu.

Đây là yêu cầu tại lớp truy vấn/projection. Không chỉ sửa JSON response để thêm một field rỗng rồi coi dữ liệu khóa đã tồn tại.

### 7.3. DTO công khai có thể khác kết quả nội bộ

Ứng dụng có thể:

```text
Lấy Window có đủ khóa
      ↓
Trích xuất position từ nội dung hợp lệ
      ↓
Chuyển nội dung sang DTO công khai
      ↓
Trả DTO cùng next cursor đã thiết kế
```

Nhờ vậy API không nhất thiết công khai mọi trường phục vụ cuộn dưới dạng thuộc tính hiển thị.

Điều quan trọng là không bỏ khóa trước thời điểm hạ tầng cần trích xuất. Query trả projection thiếu khóa khác với việc service đã lấy đủ dữ liệu rồi chủ động chọn DTO nhỏ hơn.

### 7.4. Store phải hỗ trợ đường truy vấn đó

Commons cung cấp kiểu vị trí. Bộ query creator của module thực hiện việc diễn giải.

Không suy từ ví dụ JPA rằng:

- Mọi module đều hỗ trợ keyset scrolling.
- Query khai báo bằng chuỗi hoặc native query đều có cùng hỗ trợ.
- Có thể dùng cùng cơ chế với mọi join, group, projection hay biểu thức sort.
- Một engine có toán tử so sánh là đủ để repository tự cung cấp toàn bộ contract.

Cần đối chiếu module, phiên bản, loại query và mapping thực tế. Nếu triển khai fragment riêng, ứng dụng phải chịu trách nhiệm toàn bộ logic ranh giới và metadata trả về.

## 8. Index và chi phí truy vấn

Keyset có thể tránh chi phí bỏ qua một offset lớn khi store có đường truy cập phù hợp. Tuy nhiên, nó không bảo đảm mọi query sẽ nhanh hoặc có chi phí hằng số.

Với ví dụ quan hệ:

```text
filter: tenantId, status
sort:   createdAt DESC, id DESC
```

thiết kế index cần xem cả điều kiện lọc và thứ tự. Chi tiết phụ thuộc hệ quản trị, dữ liệu và kế hoạch thực thi.

Cần quan sát:

- Store có thể tìm tới vùng ranh giới bằng index không.
- Có phải đọc nhiều hàng rồi lọc bỏ mới lấy đủ cửa sổ không.
- Sort còn phải xử lý một tập trung gian lớn không.
- Join hoặc biểu thức tính toán có làm thay đổi chi phí không.
- Projection có làm tăng lượng dữ liệu phải đọc/truyền không.

Không tạo một bộ khóa bằng tay rồi coi đó là bằng chứng query đã dùng index.

### 8.1. Batch size là giới hạn công việc, không phải position

Batch size ảnh hưởng lượng dữ liệu mỗi lần đọc, bộ nhớ và thời gian xử lý. Nó không phải một thành phần khóa so sánh chỉ vì được dùng cùng position.

Có thể thiết kế API cho phép đổi kích thước cửa sổ trong giới hạn cho phép mà vẫn giữ cùng ranh giới, nếu hợp đồng và module hỗ trợ. Không nhầm yêu cầu giữ nguyên sort/filter với một quy tắc bắt buộc mọi lần phải có cùng batch size.

Trong ví dụ `First3`, kích thước đã được cố định bởi phương thức để việc học đơn giản hơn.

## 9. Thiết kế token tiếp tục cho API

`KeysetScrollPosition` là kiểu nội bộ Java. Không nên coi một cách serialize tùy ý của object đó là giao thức API ổn định.

Một schema token do ứng dụng quản lý có thể biểu diễn:

```json
{
  "version": 1,
  "query": "paid-orders-created-desc-id-desc-v1",
  "scope": "tenant-42",
  "direction": "FORWARD",
  "keys": {
    "createdAt": "2026-04-10T11:00:00.123456Z",
    "id": "503"
  }
}
```

Đây là cấu trúc minh họa, không phải định dạng bắt buộc của Commons. Trong API thực tế, payload có thể được mã hóa thành token opaque hoặc lưu trạng thái phía server.

### 9.1. Vì sao cần query/version?

Nếu API đổi sort từ `createdAt DESC, id DESC` sang `total DESC, id DESC`, token cũ không còn đủ khóa hoặc đúng ý nghĩa.

Version/query identifier giúp nhận diện một hợp đồng đã biết thay vì để client tự quyết định:

- Danh sách thuộc tính.
- Thứ tự tiêu chí.
- Hướng ASC/DESC.
- Bộ lọc cố định.
- Cách chuyển đổi kiểu.

Khi hợp đồng đổi không tương thích, cần từ chối hoặc chuyển đổi token theo một chính sách rõ, không áp lại các key cũ vào query mới một cách im lặng.

### 9.2. Giữ đúng kiểu và độ chính xác

Các điểm thường gây lỗi:

| Loại khóa | Rủi ro khi serialize/restore |
|---|---|
| `Instant`/timestamp | Làm tròn mất phần giây hoặc đổi múi giờ/cách diễn giải |
| `Long` | Đi qua kiểu số không giữ chính xác mọi giá trị lớn |
| `BigDecimal` | Đổi sang số thực làm mất độ chính xác so sánh |
| UUID/enum | Khôi phục thành một chuỗi không khớp kiểu domain/converter |
| Composite id | Làm mất một thành phần hoặc đổi tên key |

Trong schema minh họa, id được viết thành chuỗi để ứng dụng có thể giữ chính xác giá trị khi đi qua những client có giới hạn số nguyên. Phía Java vẫn phải parse lại thành đúng kiểu `Long`.

Ví dụ khôi phục các giá trị đã được kiểm tra:

```java
Instant createdAt = Instant.parse(cursorCreatedAt);
Long id = Long.valueOf(cursorId);

KeysetScrollPosition restored = ScrollPosition.forward(
    Map.of(
        "createdAt", createdAt,
        "id", id
    )
);
```

Không truyền nguyên `Map<String, Object>` từ JSON vào factory rồi kỳ vọng mọi kiểu được sửa đúng. Converter của một store có thể hỗ trợ một số chuyển đổi, nhưng protocol của API vẫn cần hợp đồng rõ.

### 9.3. Không làm tròn timestamp của ranh giới

Nếu khóa thực tế là:

```text
2026-04-10T11:00:00.123456Z
```

nhưng token chỉ giữ:

```text
2026-04-10T11:00:00Z
```

điều kiện tiếp tục đã dùng một ranh giới khác. Một nhóm bản ghi có thể bị lặp hoặc bỏ qua.

Cần giữ giá trị theo độ chính xác mà query/mapping thực tế sử dụng. Không lấy chuỗi thời gian đã định dạng để hiển thị làm khóa nếu nó đã mất thông tin.

### 9.4. Token không phải bằng chứng quyền truy cập

Khi nhận cursor, server cần xác định tenant/phạm vi từ ngữ cảnh đã được xác thực và kiểm tra token tương thích. Field `scope` trong payload không tự cấp quyền đọc tenant đó.

Cũng không nhận tên thuộc tính sort tùy ý từ map token rồi đưa trực tiếp vào query. Dùng một hợp đồng query đã biết và các tên khóa cho phép.

Nếu client có thể sửa token, ứng dụng có thể dùng cơ chế bảo vệ tính toàn vẹn hoặc một token tham chiếu tới trạng thái phía server. Base64 chỉ thay cách biểu diễn, không bảo vệ payload khỏi bị thay đổi.

Bộ khóa có thể chứa dữ liệu không muốn công khai, chẳng hạn tên hoặc email nếu chúng tham gia sort. Khi đó cần chọn cách biểu diễn token phù hợp, không chỉ cân nhắc khả năng parse.

### 9.5. Bắt đầu và kết thúc phiên

Một API có thể quy ước:

- Không có cursor đầu vào: dùng `ScrollPosition.keyset()`.
- Có cursor hợp lệ: khôi phục bộ khóa và hướng theo contract.
- `hasNext = false`: không trả một next cursor như thể còn dữ liệu.

Với job nội bộ cần checkpoint, có thể vẫn lưu vị trí phần tử đã xử lý cuối cùng cùng trạng thái hoàn tất. Checkpoint của job và next cursor công khai có mục đích khác nhau.

## 10. Checkpoint và thay đổi dữ liệu trong lúc cuộn

### 10.1. Lưu position sau phần việc đã xử lý thành công

Một job đọc theo cửa sổ có thể cần lưu checkpoint. Không nên lưu ranh giới cuối cửa sổ trước khi các phần tử tương ứng đã được xử lý thành công.

Nếu job đọc 3 phần tử, xử lý được 1 rồi lỗi nhưng đã lưu position của phần tử thứ 3, lần chạy lại có thể bỏ qua 2 phần tử chưa xử lý.

Nếu cần checkpoint theo từng phần tử, position tại index đã xử lý có thể cung cấp ranh giới tương ứng. Tuy nhiên, cách lưu checkpoint và tác động nghiệp vụ còn phải được thiết kế cùng nhau.

### 10.2. Keyset không cung cấp exactly-once cho công việc

Có thể xảy ra:

```text
Xử lý nghiệp vụ thành công
      ↓
Tiến trình dừng trước khi ghi checkpoint
      ↓
Chạy lại từ checkpoint cũ
      ↓
Một phần công việc được thực hiện lại
```

Việc điều kiện keyset không trả lại phần tử ranh giới không giải quyết sự cố giữa xử lý và lưu trạng thái. Job có thể cần idempotency hoặc cơ chế transaction phù hợp.

Đừng gộp “không lặp bản ghi do điều kiện tiếp tục” với “không bao giờ thực hiện lại tác động nghiệp vụ”.

### 10.3. Keyset không cố định tập dữ liệu

Trong một phiên duyệt, có thể xảy ra:

- Bản ghi mới được thêm ở phía trước ranh giới, nên phiên forward hiện tại không đọc nó.
- Một bản ghi chưa đọc bị sửa khóa sort và chuyển về phía đã đi qua, nên có thể bị bỏ lỡ.
- Một bản ghi đã đọc bị sửa khóa sort và chuyển về phía chưa đi qua, nên có thể xuất hiện lại.
- Bản ghi bị xóa làm số phần tử còn lại giảm.

Nếu `createdAt` là một giá trị bất biến và id ổn định, một số rủi ro dịch chuyển giảm đi. Nhưng điều đó vẫn chưa tạo snapshot cho toàn bộ filter hoặc dữ liệu nghiệp vụ.

### 10.4. Watermark cần hợp đồng riêng

Một job có thể thêm điều kiện như “chỉ đọc dữ liệu thuộc phạm vi đã xác định lúc bắt đầu” bằng một watermark hoặc phiên bản dữ liệu. Điều kiện đó phải được giữ trong các lần tiếp tục.

Một mốc thời gian đơn lẻ không tự đóng băng mọi cập nhật, xóa hoặc bản ghi được nhập với thời điểm lùi về quá khứ. Nếu cần một tập chính xác tại một thời điểm, hãy chọn cơ chế snapshot/versioning/nhất quán mà nguồn hỗ trợ.

Keyset position chỉ là một phần của giao thức đọc, không thay thế toàn bộ thiết kế tính nhất quán.

## 11. Chẩn đoán những lỗi điển hình

| Hiện tượng | Nguyên nhân có thể có | Điều cần kiểm tra |
|---|---|---|
| Bỏ qua một số bản ghi cùng thời điểm | Chỉ giữ createdAt, thiếu khóa phân xử | Toàn bộ bộ khóa và sort |
| Bản ghi ranh giới xuất hiện lại | Điều kiện không loại trừ ranh giới trong query tùy chỉnh | Phép so sánh và nhánh bằng nhau |
| Các cửa sổ chồng lặp nhiều | Tiếp tục từ phần tử đầu thay vì phần tử cuối đã xử lý | Index truyền vào `positionAt` |
| Lỗi khi lấy position | Cửa sổ rỗng hoặc index bằng size | Kiểm tra nội dung và index hợp lệ |
| Không trích xuất được keyset | Projection thiếu thuộc tính hoặc khóa null | Dữ liệu kết quả và mapping |
| Token parse được nhưng query lỗi | Kiểu khóa hoặc tên thuộc tính sai | Chuyển đổi từ protocol sang kiểu domain |
| Dữ liệu sau token đổi thứ tự | Sort/query version đã thay đổi | Hợp đồng gắn với cursor |
| Có dữ liệu ngoài phạm vi mong muốn | Bộ lọc bị đổi hoặc nhánh OR thoát scope | Ngữ cảnh và nhóm điều kiện |
| Cuộn vẫn chậm ở dữ liệu lớn | Index/đường truy cập chưa phù hợp | Query thực tế và kế hoạch thực thi |
| Job chạy lại làm lặp tác động | Checkpoint không nguyên tử với công việc | Idempotency và thiết kế xử lý |
| Dữ liệu bị lặp/mất khi đang cập nhật | Khóa sort hoặc tập lọc thay đổi | Yêu cầu snapshot và tính bất biến |

### 11.1. Lỗi dựng position khác lỗi thực thi

`ScrollPosition.forward(keys)` tạo được object không chứng minh:

- Repository hỗ trợ keyset.
- Tên key có trong domain.
- Projection có thể tạo position tương ứng cho cửa sổ sau.
- Sort đã đầy đủ phân xử.
- Index có thể phục vụ query.

Cần quan sát kết quả và truy vấn thực tế của module trong dự án.

### 11.2. Không dùng vị trí làm số thứ tự hiển thị tuyệt đối

Đếm “đã đọc 3 cửa sổ” có thể hữu ích cho tiến độ nội bộ, nhưng keyset không tự cung cấp thứ hạng tuyệt đối hoặc khả năng nhảy tới “trang 100” khi chưa biết ranh giới ở đó.

Nếu giao diện cần tổng số trang và nhảy ngẫu nhiên theo số trang, cần đánh giá một hợp đồng phân trang khác hoặc một thiết kế lưu ranh giới phù hợp.

## 12. Kỳ vọng kiểm chứng với dữ liệu mẫu

Với sort và dữ liệu đã nêu, kích thước cửa sổ là 3:

| Lần đọc | Position đầu vào | Nội dung mong đợi | Has next |
|---|---|---|---|
| 1 | Initial keyset | 505, 504, 503 | true |
| 2 | Sau `(11:00, 503)` | 502, 501, 500 | true |
| 3 | Sau `(10:58, 500)` | 499 | false |

Những tình huống cần kiểm chứng thêm trong dự án thực tế:

1. Tập dữ liệu rỗng: không gọi positionAt trên nội dung rỗng.
2. Tổng số phần tử đúng bằng kích thước cửa sổ: không suy hasNext chỉ từ độ dài.
3. Nhiều hơn một cửa sổ có cùng giá trị sort chính: không bỏ các phần tử cùng thời điểm.
4. Khôi phục token giữ đúng kiểu và độ chính xác.
5. Bản ghi ranh giới bị xóa nhưng bộ khóa còn đầy đủ.
6. Projection thiếu một khóa: nhận diện lỗi thay vì tạo token sai.
7. Khóa null trong dữ liệu: xác định vi phạm điều kiện sử dụng.
8. Token thuộc sort/filter/tenant khác: được xử lý theo chính sách từ chối phù hợp.
9. Cập nhật khóa sort trong lúc duyệt: đánh giá hành vi theo yêu cầu nhất quán.
10. Job dừng giữa xử lý và lưu checkpoint: xác định khả năng chạy lại.

Một mock repository trả sẵn `Window` không chứng minh query creator tạo đúng điều kiện keyset. Nó có thể hữu ích cho logic vòng lặp, nhưng việc lọc theo khóa phải được kiểm chứng với hạ tầng tương ứng.

Không cần chạy query đếm để xác nhận kiểu vị trí. Những phép kiểm chứng về tổng và những phép kiểm chứng về ranh giới là hai mục tiêu khác nhau.

## 13. Bài tập vận dụng

### Bài tập 1: Bộ khóa chỉ có thời điểm

Cửa sổ đầu có id 505, 504, 503, cùng createdAt bằng 11:00. Vẫn còn id 502 ở cùng thời điểm. Vì sao chỉ dùng `createdAt < 11:00` là sai?

**Gợi ý lời giải:** Điều kiện bỏ qua id 502. Cần bộ khóa có tiêu chí phân xử và nhánh bằng createdAt rồi so id theo hướng tương ứng.

### Bài tập 2: Không thay so sánh từ điển bằng AND đơn giản

Một người viết:

```text
createdAt < lastCreatedAt AND id < lastId
```

Vì sao không tương đương điều kiện tiếp tục theo `createdAt DESC, id DESC`?

**Gợi ý lời giải:** Khi createdAt đã nhỏ hơn, bản ghi đứng sau ranh giới bất kể id lớn hay nhỏ hơn lastId. Điều kiện AND loại nhầm những bản ghi có thời điểm cũ hơn nhưng id lớn hơn. Cần so tiêu chí đầu trước, chỉ xét id khi thời điểm bằng nhau.

### Bài tập 3: Chọn index của position

Một cửa sổ có 3 phần tử. Muốn tiếp tục sau tất cả phần tử đã xử lý, dùng index 0, 2 hay 3?

**Gợi ý lời giải:** Dùng 2, tức `size() - 1`. Index 0 tiếp tục sau phần tử đầu và có thể đọc lại phần còn lại đã xử lý; index 3 nằm ngoài nội dung.

### Bài tập 4: DESC có phải backward không?

Query sắp `createdAt DESC`. Ứng dụng muốn đọc từ mới tới cũ theo đúng thứ tự query. Có bắt buộc tạo backward position không?

**Gợi ý lời giải:** Không. Đó là forward theo một sort giảm dần. Direction của position khác hướng ASC/DESC của thuộc tính.

### Bài tập 5: Đổi kiểu khóa khi khôi phục

Token có id dạng chuỗi `"503"` và createdAt dạng ISO timestamp. Có nên đưa nguyên map JSON vào query mà không kiểm tra không?

**Gợi ý lời giải:** Không. Cần khôi phục đúng kiểu domain, kiểm tra tên khóa theo query đã biết, giữ độ chính xác và xác nhận token thuộc đúng ngữ cảnh.

### Bài tập 6: Bản ghi ranh giới bị xóa

Đã giữ đầy đủ `createdAt` và id của bản ghi cuối. Bản ghi đó bị xóa trước lần đọc tiếp. Có bắt buộc tải lại bản ghi để tiếp tục không?

**Gợi ý lời giải:** Không chỉ để biết bộ giá trị ranh giới, vì đã giữ chúng. Query có thể so sánh từ các giá trị đó. Tuy nhiên, dữ liệu toàn tập vẫn có thể thay đổi và không có snapshot chỉ nhờ keyset.

### Bài tập 7: Projection chỉ có tổng tiền

Sort cần createdAt và id, nhưng query projection chỉ chứa total. Có thể tạo position đúng chỉ từ projection đó không?

**Gợi ý lời giải:** Thiếu các giá trị cần thiết để hạ tầng trích xuất bộ khóa. Query/projection nội bộ phải cung cấp đầy đủ thuộc tính theo yêu cầu module; DTO công khai có thể được tạo sau khi position đã được lấy đúng.

## 14. Những điều cần ghi nhớ

- `KeysetScrollPosition` biểu diễn bộ giá trị ranh giới và hướng, không phải offset hay số trang.
- Query cần sort xác định, đủ phân xử; bộ khóa phải bao quát các thành phần cần cho thứ tự đó.
- Tiếp tục nhiều khóa là so sánh theo thứ tự từ điển, có nhánh bằng nhau cho các tiêu chí trước.
- Dùng position do `Window` cung cấp tại phần tử hợp lệ; kiểm tra rỗng và hasNext.
- Hướng forward/backward không đồng nghĩa hướng ASC/DESC.
- Khóa cần không null và phải lấy được từ kết quả/projection trong phạm vi module hỗ trợ.
- Token phải giữ đúng kiểu, độ chính xác và ngữ cảnh query; metadata không tự cấp quyền truy cập.
- Keyset không tạo snapshot và không bảo đảm exactly-once; checkpoint và tính nhất quán cần thiết kế riêng.
