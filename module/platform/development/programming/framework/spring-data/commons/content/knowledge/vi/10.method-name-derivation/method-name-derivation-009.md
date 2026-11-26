# OrderBy, First, Top và giới hạn kết quả

Yêu cầu “lấy ba đơn hàng mới nhất” chứa ba quyết định: đơn hàng nào thuộc phạm vi tìm kiếm, thứ tự nào được xem là mới nhất và tối đa bao nhiêu kết quả cần trả về. Trong tên phương thức suy diễn của Spring Data, predicate sau `By` mô tả điều kiện, `OrderBy` mô tả thứ tự tĩnh, còn `First` hoặc `Top` mô tả giới hạn số kết quả.

Bài học thuộc chương **Suy diễn tên phương thức** của **SPRING_DATA_COMMONS**. Mục tiêu là viết được những phương thức lấy kết quả đầu tiên có ý nghĩa rõ ràng, kết hợp đúng với sắp xếp và phân trang, đồng thời không suy từ abstraction chung sang một khả năng không được module lưu trữ hỗ trợ.

## 1. Tách điều kiện, thứ tự và giới hạn

Xét tên phương thức:

```java
findTop3ByTenantIdAndStatusOrderByCreatedAtDescIdDesc
```

Có thể đọc thành ba phần:

```text
findTop3
    Lấy tối đa 3 kết quả

ByTenantIdAndStatus
    Chỉ lấy đơn thuộc tenant và trạng thái được truyền vào

OrderByCreatedAtDescIdDesc
    Sắp xếp createdAt giảm dần, rồi id giảm dần
```

| Thành phần | Câu hỏi được trả lời | Điều không tự quyết định |
| --- | --- | --- |
| Predicate sau `By` | Entity nào được chọn? | Không định nghĩa thứ tự trả về |
| `OrderBy` | Entity được xếp theo tiêu chí nào? | Không tự giới hạn số lượng |
| `First` hoặc `Top` | Tối đa bao nhiêu kết quả được lấy? | Không tự định nghĩa “mới nhất”, “cao nhất” hay “tốt nhất” |
| Kiểu trả về | Caller nhận một giá trị, tập hợp hay metadata phân trang? | Không thay thế điều kiện và thứ tự của truy vấn |

Mô hình khái niệm là:

```text
Lọc đúng phạm vi
      |
      v
Sắp xếp theo các khóa đã chọn
      |
      v
Lấy tối đa N kết quả
      |
      v
Ánh xạ sang kiểu kết quả của phương thức
```

Đây là cách hiểu ngữ nghĩa. Kho dữ liệu có thể thực thi bằng chỉ mục, phép sort, giới hạn phía server hoặc các chiến lược khác. Commons không quy định một execution plan hay một cú pháp SQL duy nhất.

## 2. Mô hình sử dụng trong ví dụ

Các ví dụ repository đồng bộ chính sử dụng **Spring Data JPA** với entity `PurchaseOrder` đã được ánh xạ đầy đủ. Những chữ ký dùng abstraction Commons như `Repository`, `Sort`, `Pageable` và `Page`; cấu hình persistence và mapping chi tiết được lược bỏ.

| Thuộc tính Java | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `id` | `Long` | Định danh duy nhất của đơn hàng |
| `tenantId` | `String` | Phạm vi tổ chức sở hữu đơn |
| `status` | `OrderStatus` | Trạng thái nghiệp vụ |
| `createdAt` | `Instant` | Thời điểm tạo, giả định không null |
| `total` | `BigDecimal` | Tổng tiền, giả định không null |

```java
public enum OrderStatus {
    NEW, PAID, CANCELLED
}
```

Tên trong derived query và tên thuộc tính truyền vào `Sort` là tên thuộc tính Java mà mô hình ánh xạ nhận diện. Ví dụ dùng `createdAt`, không tự đổi sang tên cột SQL `created_at`.

Khi dùng MongoDB, JDBC, R2DBC hoặc kho dữ liệu khác, cần đối chiếu khả năng suy diễn, kiểu trả về và cơ chế giới hạn của module tương ứng. Parser chung nhận ra một cấu trúc tên không đồng nghĩa mọi kho dữ liệu đều có cùng cách thực thi cấu trúc đó.

## 3. OrderBy: sắp xếp tĩnh trong tên phương thức

### 3.1. Một khóa sắp xếp

```java
List<PurchaseOrder> findByTenantIdAndStatusOrderByCreatedAtDesc(
        String tenantId,
        OrderStatus status);
```

Phương thức chọn đơn của tenant và trạng thái đã cho, sau đó xếp `createdAt` giảm dần. Những đơn có thời điểm tạo lớn hơn xuất hiện trước.

`Asc` là tăng dần; `Desc` là giảm dần. Với thuộc tính thời gian:

- `CreatedAtAsc`: đơn cũ hơn đứng trước.
- `CreatedAtDesc`: đơn mới hơn đứng trước.

Nếu không chỉ rõ hướng, phần sắp xếp được phân tích theo hướng tăng dần mặc định. Trong tên phương thức nghiệp vụ, ghi rõ `Asc` hoặc `Desc` thường giúp người đọc nhận ra ý định ngay.

Chỉ có `OrderBy` không tạo ra giới hạn. Phương thức trên vẫn có thể trả một danh sách rất lớn nếu có nhiều đơn khớp điều kiện.

### 3.2. Nhiều khóa sắp xếp

```java
List<PurchaseOrder> findByTenantIdAndStatusOrderByCreatedAtDescIdDesc(
        String tenantId,
        OrderStatus status);
```

Thứ tự ưu tiên là:

1. So sánh `createdAt` giảm dần.
2. Nếu hai đơn có cùng `createdAt`, so sánh `id` giảm dần.

Các khóa sắp xếp được ghép tiếp nhau sau `OrderBy`; không dùng `And` như khi ghép predicate.

```text
Đúng ý định:  OrderByCreatedAtDescIdDesc

Phần lọc:     TenantIdAndStatus
Phần sort:    CreatedAtDesc + IdDesc
```

Nếu muốn tổng tiền cao trước, khi bằng tiền thì đơn cũ trước, có thể diễn đạt:

```java
List<PurchaseOrder> findByTenantIdAndStatusOrderByTotalDescCreatedAtAscIdAsc(
        String tenantId,
        OrderStatus status);
```

Khóa đầu tiên luôn có ưu tiên cao hơn khóa sau. Đặt `IdDesc` sau `CreatedAtDesc` không có nghĩa toàn bộ kết quả được xếp lại chỉ theo `id`.

### 3.3. Khóa phụ làm rõ các trường hợp bằng nhau

Nếu chỉ sắp theo `createdAt`, hai đơn cùng thời điểm không có thứ tự tương đối được xác định đầy đủ bởi yêu cầu truy vấn. Hệ quản trị có thể trả chúng theo những thứ tự khác nhau giữa các lần thực thi.

Thêm định danh duy nhất làm khóa cuối giúp xác định thứ tự đầy đủ hơn trên tập dữ liệu không đổi. Giả sử `id` là duy nhất, `createdAt DESC, id DESC` không còn trường hợp hai entity khác nhau bằng nhau trên toàn bộ bộ khóa đó.

Tuy nhiên, định danh lớn hơn không tự chứng minh một đơn được commit sau, quan trọng hơn hay mới hơn theo mọi định nghĩa nghiệp vụ. Ở đây `id` chỉ là khóa phân định khi `createdAt` bằng nhau.

## 4. First và Top: giới hạn số kết quả

### 4.1. Hai keyword có thể dùng thay nhau

Trong cơ chế suy diễn hỗ trợ các keyword này, `First` và `Top` biểu đạt cùng loại giới hạn:

```java
List<PurchaseOrder> findTop3ByTenantIdAndStatusOrderByCreatedAtDescIdDesc(
        String tenantId, OrderStatus status);

List<PurchaseOrder> findFirst3ByTenantIdAndStatusOrderByCreatedAtDescIdDesc(
        String tenantId, OrderStatus status);
```

Hai chữ ký là những phương án minh họa tương đương về ý định giới hạn. Không có quy tắc chung rằng `First` xếp tăng dần còn `Top` xếp giảm dần. Hướng sắp xếp đến từ `OrderBy` hoặc một cơ chế sort được hỗ trợ.

Con số sau keyword là số lượng tối đa, không phải số thứ tự của một hàng:

```text
Top3    -> tối đa ba kết quả đầu
First3  -> tối đa ba kết quả đầu
```

`First3` không có nghĩa lấy riêng kết quả ở vị trí thứ ba.

### 4.2. Không ghi số thì giới hạn mặc định là một

```java
Optional<PurchaseOrder> findFirstByTenantIdAndStatusOrderByCreatedAtDescIdDesc(
        String tenantId, OrderStatus status);

Optional<PurchaseOrder> findTopByTenantIdAndStatusOrderByCreatedAtDescIdDesc(
        String tenantId, OrderStatus status);
```

Hai phương thức cùng biểu đạt việc tìm tối đa một đơn, ưu tiên thời điểm tạo lớn nhất rồi định danh lớn nhất.

Nếu không có đơn phù hợp, với chữ ký `Optional` được module hỗ trợ, kết quả là `Optional.empty()`. Nếu có nhiều đơn phù hợp với predicate, giới hạn một kết quả được áp dụng để chọn theo thứ tự đã khai báo; đây không phải yêu cầu predicate phải chỉ khớp duy nhất một entity.

Đó là khác biệt với một phương thức trả `Optional<PurchaseOrder>` nhưng **không giới hạn**, chẳng hạn `findByTenantIdAndStatus(...)`: nếu nhiều entity khớp mà hợp đồng chỉ chấp nhận một, nó có thể phát sinh lỗi số lượng kết quả.

### 4.3. Tối đa N không có nghĩa luôn đủ N

Với `Top3`:

| Số entity khớp điều kiện | Số phần tử tối đa trong danh sách kết quả |
| --- | --- |
| `0` | `0` |
| `1` | `1` |
| `2` | `2` |
| `3` | `3` |
| `100` | `3` |

Framework không tạo thêm entity để lấp đầy danh sách. Với một tập dữ liệu đơn giản và query hợp lệ, caller nên chuẩn bị cho mọi kích thước từ `0` đến giới hạn.

### 4.4. Không có sort thì không biết “đầu tiên” theo tiêu chí nào

```java
Optional<PurchaseOrder> findFirstByTenantIdAndStatus(
        String tenantId, OrderStatus status);
```

Tên này có giới hạn nhưng chưa định nghĩa thứ tự nghiệp vụ. Không được mặc định nó lấy đơn mới nhất, cũ nhất, có `id` nhỏ nhất hay là đơn được insert đầu tiên.

Nếu ứng dụng chỉ cần một entity bất kỳ phù hợp, điều đó có thể chấp nhận được. Nếu muốn “đơn mới nhất”, phải bổ sung tiêu chí rõ ràng, chẳng hạn `OrderByCreatedAtDescIdDesc`.

## 5. Đọc kết quả trên một tập dữ liệu cụ thể

Giả sử có các đơn sau, với thời điểm cùng ngày và cùng múi giờ UTC:

| id | tenantId | status | createdAt | total |
| --- | --- | --- | --- | --- |
| `107` | `tenant-a` | `PAID` | `2026-11-20T10:05:00Z` | `120` |
| `106` | `tenant-a` | `PAID` | `2026-11-20T10:05:00Z` | `300` |
| `105` | `tenant-a` | `PAID` | `2026-11-20T10:00:00Z` | `200` |
| `104` | `tenant-a` | `PAID` | `2026-11-20T09:55:00Z` | `500` |
| `103` | `tenant-a` | `PAID` | `2026-11-20T09:55:00Z` | `100` |
| `102` | `tenant-a` | `NEW` | `2026-11-20T10:10:00Z` | `600` |
| `101` | `tenant-b` | `PAID` | `2026-11-20T10:20:00Z` | `700` |

Với tham số `tenant-a` và `PAID`:

| Thứ tự và giới hạn | Các id kỳ vọng |
| --- | --- |
| `Top3 ... OrderByCreatedAtDescIdDesc` | `107, 106, 105` |
| `First ... OrderByCreatedAtAscIdAsc` | `103` |
| `Top3 ... OrderByTotalDescIdDesc` | `104, 106, 105` |
| Không giới hạn, `OrderByCreatedAtDescIdDesc` | `107, 106, 105, 104, 103` |

Đơn `102` không được lấy dù mới hơn vì sai trạng thái. Đơn `101` không được lấy dù vừa mới hơn vừa có tổng tiền cao hơn vì sai tenant. Giới hạn luôn phải được hiểu cùng predicate của truy vấn, không phải chọn top của toàn bộ dữ liệu rồi mới loại các entity ngoài phạm vi ở tầng Java.

Cũng cần xác định ý nghĩa của “top”: ví dụ tổng tiền chỉ đang xếp theo số tiền trên đơn. Nó không tự quy đổi tiền tệ, tính doanh thu theo khách hàng hoặc chọn top riêng cho từng nhóm.

## 6. Kiểu trả về phải khớp giới hạn và nhu cầu

### 6.1. Một kết quả tùy chọn

```java
Optional<PurchaseOrder> findFirstByTenantIdAndStatusOrderByCreatedAtDescIdDesc(
        String tenantId, OrderStatus status);
```

Phù hợp khi caller cần không có hoặc một đơn mới nhất. Không cần trả `List` rồi để mọi caller tự kiểm tra phần tử đầu nếu hợp đồng thật sự là một kết quả tùy chọn.

### 6.2. Một danh sách có giới hạn

```java
List<PurchaseOrder> findTop5ByTenantIdAndStatusOrderByCreatedAtDescIdDesc(
        String tenantId, OrderStatus status);
```

Phù hợp với widget hiển thị tối đa năm đơn mới nhất. Danh sách không cung cấp sẵn tổng số đơn khớp điều kiện hoặc thông tin còn kết quả tiếp theo.

`Top5` không làm kiểu `Optional<PurchaseOrder>` trở thành một container chứa năm entity. Nếu phương thức có thể trả nhiều entity, cần chọn kiểu kết quả nhiều phần tử được module hỗ trợ.

### 6.3. Projection vẫn là một hợp đồng ánh xạ riêng

Có thể dùng projection thay cho entity nếu module và truy vấn hỗ trợ. Khi đó giới hạn vẫn là giới hạn kết quả của truy vấn, còn projection quyết định hình dạng dữ liệu mà caller nhận.

Không giả định một projection chứa nested collection sẽ giới hạn mỗi collection con về N phần tử chỉ vì phương thức ngoài có `TopN`. Đơn vị được giới hạn và cách tải quan hệ cần được xem theo query/mapping thực tế.

Tương tự, `Distinct` xử lý vấn đề kết quả trùng theo ngữ nghĩa của truy vấn; nó không thay thế thứ tự hoặc tự trở thành phép xếp hạng theo nhóm.

## 7. Sort động: giữ giới hạn cố định, thay thứ tự khi gọi

Nếu số kết quả cố định nhưng tiêu chí xếp hạng thay đổi, có thể dùng `Sort` ở module hỗ trợ:

```java
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.repository.Repository;

public interface PurchaseOrderRepository
        extends Repository<PurchaseOrder, Long> {

    List<PurchaseOrder> findTop3ByTenantIdAndStatus(
            String tenantId,
            OrderStatus status,
            Sort sort);
}
```

Ví dụ lấy ba đơn có tổng tiền cao nhất:

```java
Sort ranking = Sort.by(Sort.Direction.DESC, "total")
        .and(Sort.by(Sort.Direction.DESC, "id"));

List<PurchaseOrder> orders = repository.findTop3ByTenantIdAndStatus(
        "tenant-a", OrderStatus.PAID, ranking);
```

Ở đây `Sort` là tham số đặc biệt, không phải giá trị cho một điều kiện sau `By`. Số lượng vẫn cố định bởi `Top3`, còn thứ tự được xác định từ đối số.

### 7.1. Sort động không nên bị coi là ghi đè toàn bộ OrderBy tĩnh

Với derived query Spring Data JPA, thứ tự tĩnh có thể được kết hợp với thứ tự động, trong đó các khóa tĩnh đi trước các khóa động. Vì vậy không nên viết sẵn `OrderByCreatedAtDesc` rồi kỳ vọng truyền `Sort.by("total")` sẽ đổi ưu tiên chính thành `total`.

Nếu caller cần chọn toàn bộ thứ tự, một phương thức không có `OrderBy` tĩnh như ví dụ trên thường dễ hiểu hơn. Nếu cố ý kết hợp, hãy xác định rõ thứ tự ưu tiên và kiểm tra trường hợp hai bộ khóa có thuộc tính trùng nhau.

Đây là hành vi cần xem theo module; không suy ra một chính sách override phổ quát từ việc cả tên phương thức lẫn chữ ký đều có thông tin sort.

### 7.2. Tên thuộc tính và hướng sort cần được kiểm soát ở tầng ứng dụng

Một API có thể cho người dùng chọn “mới nhất” hoặc “giá trị cao nhất”. Tầng ứng dụng nên ánh xạ các lựa chọn đó sang các bộ khóa đã xác định, chẳng hạn:

| Lựa chọn | Sort nội bộ |
| --- | --- |
| Mới nhất | `createdAt DESC, id DESC` |
| Cũ nhất | `createdAt ASC, id ASC` |
| Giá trị cao nhất | `total DESC, id DESC` |

Không cần để caller bên ngoài biết tên cột vật lý hoặc truyền một đoạn SQL tùy ý. `Sort` dùng hợp đồng thuộc tính của mô hình, không phải một chỗ để chèn trực tiếp cú pháp truy vấn.

## 8. Limit động: khi số lượng không cố định trong tên

Nếu phiên bản Commons và module đang dùng hỗ trợ tham số `Limit`, có thể biểu đạt số lượng tại thời điểm gọi thay vì tạo nhiều phương thức `Top3`, `Top5`, `Top10`.

```java
import java.util.List;
import org.springframework.data.domain.Limit;
import org.springframework.data.domain.Sort;

List<PurchaseOrder> findByTenantIdAndStatus(
        String tenantId,
        OrderStatus status,
        Sort sort,
        Limit limit);
```

Ví dụ:

```java
Sort ranking = Sort.by(Sort.Direction.DESC, "createdAt")
        .and(Sort.by(Sort.Direction.DESC, "id"));

List<PurchaseOrder> latest = repository.findByTenantIdAndStatus(
        tenantId,
        OrderStatus.PAID,
        ranking,
        Limit.of(5));
```

Đây là khả năng phải đối chiếu với bộ phiên bản và module thực tế, không phải lời khẳng định rằng mọi repository Spring Data đều đã hỗ trợ cùng một chữ ký.

Những điểm cần giữ rõ:

- Chọn `First`/`Top` hoặc `Limit` làm cơ chế giới hạn cho một phương thức; không trộn keyword giới hạn trong tên với tham số `Limit`.
- `Limit` không chứa offset hay metadata tổng số của một trang.
- Nếu module hỗ trợ `Limit.unlimited()`, giá trị đó biểu đạt không giới hạn theo cơ chế tương ứng; cần chọn giới hạn phù hợp với hợp đồng ứng dụng.
- Khi nhận số lượng từ bên ngoài, tầng ứng dụng nên xác nhận phạm vi theo yêu cầu sản phẩm, ví dụ từ `1` đến `100`, thay vì mặc định mọi số đều phù hợp.

Một giới hạn động rất lớn vẫn có thể gây tải dữ liệu lớn. Khả năng truyền N không thay thế việc thiết kế một API có kích thước kết quả hợp lý.

## 9. Phân biệt giới hạn kết quả với phân trang

### 9.1. TopN không chứa thông tin của Page

`List<PurchaseOrder>` với `Top3` chỉ cho caller danh sách tối đa ba đơn. Từ danh sách có đúng ba phần tử, caller không biết chắc có đơn thứ tư hay tổng cộng có bao nhiêu đơn.

Nếu chỉ có hai phần tử trên một tập truy vấn đơn giản, có thể biết kết quả đang quan sát chưa đạt giới hạn. Nhưng hợp đồng danh sách vẫn không trở thành một `Page` có `totalElements` hoặc một `Slice` có `hasNext` được framework cung cấp.

### 9.2. Pageable mô tả một cửa sổ truy cập theo trang

Một phương thức phân trang thông thường không cần có `Top`:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

Page<PurchaseOrder> findByTenantIdAndStatus(
        String tenantId,
        OrderStatus status,
        Pageable pageable);
```

Ví dụ gọi:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

Sort order = Sort.by(Sort.Direction.DESC, "createdAt")
        .and(Sort.by(Sort.Direction.DESC, "id"));

Page<PurchaseOrder> page = repository.findByTenantIdAndStatus(
        "tenant-a",
        OrderStatus.PAID,
        PageRequest.of(0, 3, order));
```

Chỉ số trang bắt đầu từ `0`. Với dữ liệu minh họa không đổi, trang đầu có nội dung `107, 106, 105`, còn tổng số phù hợp là `5`.

`Page` có thể cần thêm truy vấn đếm để xác định tổng. Framework cũng có thể suy ra tổng trong một số trường hợp, nên không cam kết mỗi lần lấy `Page` luôn chạy đúng hai truy vấn.

Nếu chỉ cần biết còn lát tiếp theo mà không cần tổng số, một module có hỗ trợ `Slice` có thể dùng chữ ký như:

```java
Slice<PurchaseOrder> findSliceByTenantIdAndStatus(
        String tenantId,
        OrderStatus status,
        Pageable pageable);
```

`Slice` thường lấy thêm một phần tử để xác định còn kết quả hay không; nó không cung cấp tổng số như `Page`. Phần `Slice` trước `By` trong tên ví dụ là mô tả subject, còn kiểu trả về mới là hợp đồng kết quả cần được module hỗ trợ.

### 9.3. Không đặt các tham số đặc biệt chồng chức năng

`Pageable` đã chứa sort và kích thước trang. Không thiết kế cùng một phương thức nhận đồng thời:

```text
Pageable + Sort
Pageable + Limit
```

Những tổ hợp đó trùng vai trò và không phải chữ ký hợp lệ cần dùng cho các cơ chế truy vấn chuẩn tương ứng. Đưa sort vào `Pageable`; dùng kích thước trang cho phân trang, hoặc dùng `Sort` với `Limit` ở một phương thức giới hạn được module hỗ trợ.

### 9.4. Top kết hợp Pageable cần được hiểu theo module

Một số module hỗ trợ kết hợp keyword `Top`/`First` với `Pageable`. Khi đó cả giới hạn tổng của truy vấn lẫn thông tin trang đều tham gia vào việc lấy kết quả. Không nên tự suy ra rằng hai số chỉ được xử lý như một phép `min`, hoặc `totalElements` chắc chắn là tổng của toàn bộ dữ liệu không giới hạn.

Nếu thực sự cần kết hợp, phải xác nhận ngữ nghĩa giới hạn, offset và metadata trang của module/phiên bản đang dùng bằng các trường hợp trang đầu, trang sau và trang cuối. Khi nhu cầu chỉ là “trang thứ hai, kích thước ba”, phương thức không có `Top` như phần trên thường là hợp đồng rõ ràng hơn.

Khi nhu cầu là “năm đơn mới nhất cho một widget”, phương thức `Top5` trả danh sách thường đủ và tránh việc đếm tổng không cần thiết.

## 10. Thứ tự xác định không đồng nghĩa snapshot nhất quán

Khóa phụ duy nhất giúp tránh thứ tự mơ hồ giữa các hàng bằng nhau. Nhưng giữa hai lần gọi, dữ liệu có thể thay đổi:

1. Caller lấy trang đầu theo `createdAt DESC, id DESC`.
2. Một đơn mới được thêm vào trước các đơn cũ theo thứ tự đó.
3. Caller lấy trang tiếp theo bằng offset.

Đơn mới có thể đẩy vị trí các đơn cũ sang trang sau. Caller có thể thấy trùng hoặc bỏ sót so với một lần duyệt lý tưởng trên snapshot ban đầu, dù mỗi truy vấn đều dùng thứ tự xác định.

Vì vậy cần phân biệt:

- **Tie-breaker:** giải quyết thứ tự của các entity bằng nhau trên khóa chính.
- **Snapshot/transaction consistency:** xác định phiên bản dữ liệu được nhìn thấy qua nhiều truy vấn.
- **Cách di chuyển:** offset hay một cơ chế seek/keyset được module hỗ trợ.

Nếu cần duyệt tập dữ liệu lớn hoặc đang thay đổi, có thể phải chọn cơ chế scrolling/keyset và bộ khóa phù hợp với khả năng module. Việc thêm `Top100` không tự tạo ra một cursor hoặc một snapshot xuyên nhiều lần đọc.

Các ví dụ giả định `createdAt` và `total` không null. Nếu cho phép null, cần xác định ngữ nghĩa thứ tự null của kho dữ liệu. Gợi ý null handling trong sort không phải cam kết rằng mọi module đều thực thi giống nhau.

## 11. Giới hạn ở repository khác với cắt danh sách trong Java

Ví dụ chỉ cắt sau khi đã nhận danh sách:

```java
List<PurchaseOrder> all = repository
        .findByTenantIdAndStatusOrderByCreatedAtDescIdDesc(tenantId, status);

List<PurchaseOrder> firstThree = all.stream().limit(3).toList();
```

Đoạn trên có thể đã tải toàn bộ entity khớp điều kiện trước khi giữ ba phần tử trong Java. Một derived query `Top3` biểu đạt nhu cầu giới hạn ngay tại tầng truy vấn, cho phép module áp dụng cơ chế phù hợp.

Tuy nhiên, giới hạn nhỏ không bảo đảm chi phí nhỏ trong mọi trường hợp:

- Cơ sở dữ liệu có thể phải quét hoặc sort nhiều dữ liệu để tìm ba hàng đầu.
- Chỉ mục không phù hợp có thể khiến predicate và thứ tự tốn kém.
- Join và việc tải quan hệ có thể làm số dòng trung gian lớn hơn số entity trả về.
- Một số cấu trúc fetch join với phân trang/giới hạn trong JPA có hạn chế riêng hoặc có thể dẫn tới xử lý trong bộ nhớ, tùy provider và cấu hình.

Với ví dụ lọc theo tenant, trạng thái rồi xếp theo thời điểm, có thể xem xét chỉ mục phù hợp với hình dạng truy vấn. Lựa chọn cụ thể phải dựa trên hệ quản trị, phân bố dữ liệu và execution plan thực tế, không chỉ dựa trên việc tên phương thức có chữ `Top`.

Cũng không suy từ `findTop100By...` sang kết luận `deleteTop100By...` sẽ xóa theo lô đúng 100 entity. Hỗ trợ giới hạn cho truy vấn đọc không tự áp dụng cho thao tác xóa ở mọi module.

## 12. Tên phương thức chỉ có hiệu lực theo nguồn truy vấn đang được dùng

Những diễn giải trong bài dành cho truy vấn được suy diễn từ tên. Nếu phương thức có implementation từ fragment hoặc được giải quyết bằng một truy vấn khai báo, phải xem hợp đồng của cơ chế đó.

Đặc biệt, thêm `First` vào tên của một phương thức có `@Query` không phải một cách phổ quát để sửa nội dung JPQL/SQL đã khai báo thành truy vấn có giới hạn. Tương tự, `OrderBy` trong tên không được mặc định là sẽ viết lại mọi named query.

Nếu có truy vấn khai báo, cần dùng cách sort, paging hoặc giới hạn mà module hỗ trợ cho loại truy vấn đó. Trước khi chẩn đoán “Top không hoạt động”, hãy xác định liệu phương thức có thật sự đang đi qua cơ chế suy diễn hay không.

Metadata auditing cũng cần được hiểu riêng. Một trường thời gian được hạ tầng auditing ghi nhận có thể được dùng làm khóa sort nếu mapping cho phép, nhưng auditing không tự chọn thứ tự mặc định hay bảo đảm giá trị đó biểu đạt đúng khái niệm “mới nhất” mà nghiệp vụ yêu cầu.

## 13. Các lỗi dễ gặp và cách chỉnh

| Biểu hiện | Nguyên nhân có thể có | Hướng xử lý |
| --- | --- | --- |
| Lấy một đơn nhưng không phải đơn mới nhất | Có `First` nhưng không có sort phù hợp | Thêm `OrderByCreatedAtDesc` và khóa phụ thích hợp |
| Kết quả đổi thứ tự khi trùng thời điểm | Thiếu khóa cuối phân định duy nhất | Thêm `id` hoặc bộ khóa duy nhất phù hợp |
| Phương thức trả rất nhiều entity | Có `OrderBy` nhưng không có giới hạn/phân trang | Chọn `TopN`, `Limit` hoặc `Pageable` theo nhu cầu |
| Lỗi thuộc tính trong tên hoặc Sort | Dùng tên cột SQL hay tên Java cũ | Đối chiếu metadata domain và đường dẫn thuộc tính |
| `Top5` trả hai phần tử | Chỉ có hai entity khớp điều kiện | Xem đó là kết quả bình thường nếu dữ liệu đúng |
| `Optional` không phù hợp với Top nhiều kết quả | Hợp đồng cardinality không khớp | Chọn kiểu nhiều phần tử được module hỗ trợ |
| Truyền sort mà ưu tiên chính không đổi | Vẫn có OrderBy tĩnh được kết hợp trước | Thiết kế một nguồn thứ tự rõ ràng hoặc kiểm tra thứ tự kết hợp |
| Không biết còn dữ liệu sau TopN hay không | Danh sách không có metadata tiếp tục | Chọn `Slice`/`Page` hoặc API phù hợp với module |
| Top mỗi nhóm bị hiểu thành Top toàn tập | Giới hạn toàn truy vấn không phải phép xếp hạng từng nhóm | Thiết kế truy vấn grouping/ranking riêng khi cần |
| Tên có First nhưng truy vấn khai báo không giới hạn | Giả định keyword tên sẽ sửa truy vấn khai báo | Kiểm tra nguồn truy vấn và cơ chế giới hạn tương ứng |

## 14. Bài tập thực hành

### Bài 1: Đọc đúng tên phương thức

Đọc chữ ký sau thành yêu cầu nghiệp vụ:

```java
List<PurchaseOrder> findTop5ByTenantIdAndStatusOrderByTotalDescCreatedAtAscIdAsc(
        String tenantId,
        OrderStatus status);
```

**Gợi ý:** chọn đơn đúng tenant và trạng thái, ưu tiên tổng tiền lớn hơn, nếu bằng tiền ưu tiên thời điểm tạo sớm hơn, nếu vẫn bằng thì dùng id tăng dần, cuối cùng trả tối đa năm đơn.

### Bài 2: Sửa hợp đồng “đơn mới nhất”

Một phương thức đang là:

```java
Optional<PurchaseOrder> findFirstByTenantIdAndStatus(
        String tenantId, OrderStatus status);
```

Caller dùng nó như “đơn mới nhất”. Hãy sửa tên để ý định rõ ràng trên mô hình đã cho.

**Gợi ý:** dùng `findFirstByTenantIdAndStatusOrderByCreatedAtDescIdDesc(...)`. Sau đó xác nhận `createdAt` thật sự là thời điểm mà nghiệp vụ muốn so sánh.

### Bài 3: Chọn danh sách, Slice hay Page

Chọn hợp đồng khởi đầu cho ba màn hình:

1. Widget hiển thị tối đa năm đơn mới nhất.
2. Danh sách có nút “xem tiếp”, không hiển thị tổng số.
3. Bảng có chỉ số trang và tổng số kết quả.

**Gợi ý:** lần lượt xem xét danh sách giới hạn `Top5`, `Slice` với `Pageable`, và `Page` với `Pageable`, sau khi xác nhận module hỗ trợ các kiểu kết quả tương ứng.

### Bài 4: Kiểm tra các trường hợp làm lộ lỗi thứ tự

Khi tích hợp phương thức Top3 vào ứng dụng, dữ liệu kiểm tra nên có:

- Nhiều hơn ba đơn khớp điều kiện để giới hạn thực sự có tác dụng.
- Hai đơn trùng `createdAt` để xác nhận khóa phụ `id`.
- Một đơn mới hơn nhưng sai tenant hoặc sai trạng thái để kiểm tra phạm vi lọc.
- Ít hơn ba đơn và không có đơn nào để xác nhận kích thước kết quả hợp lệ.

Nếu còn kiểm tra phân trang, cần đi qua trang sau và metadata tổng/tiếp tục theo hợp đồng đã chọn. Chỉ kiểm tra danh sách đầu có ba phần tử không đủ để chứng minh thứ tự, phạm vi lọc và semantics trang đều đúng.

## 15. Các điểm cần nhớ

- `OrderBy` mô tả thứ tự tĩnh, `First` và `Top` mô tả giới hạn; thiếu sort thì “đầu tiên” chưa có nghĩa nghiệp vụ xác định.
- `First` và `Top` có thể dùng thay nhau trong cơ chế suy diễn tương ứng; không ghi số thì giới hạn mặc định là một.
- Giới hạn N là tối đa N kết quả, không phải cam kết luôn đủ N và không phải lấy riêng phần tử thứ N.
- Khóa phụ duy nhất giúp thứ tự rõ ràng trên dữ liệu không đổi, nhưng không tạo snapshot nhất quán giữa nhiều lần truy vấn.
- `Sort`, `Limit`, `Pageable`, `Slice` và `Page` giải quyết những nhu cầu khác nhau; cần chọn tổ hợp được module hỗ trợ và kiểu trả về phù hợp.
- Giới hạn kết quả, ánh xạ projection, hiệu năng và khả năng của từng kho dữ liệu phải được xét cùng nhau; tên phương thức không thay thế việc hiểu nguồn truy vấn thực tế.
