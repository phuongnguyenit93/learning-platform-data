# Page, Slice và chi phí biết tổng số kết quả

## 1. Không phải giao diện nào cũng cần biết tổng

Một màn hình tìm kiếm có thể cần hiển thị “trang 2 trên 15”, tổng số đơn hàng và nút chuyển đến trang cuối. Một bảng tin chỉ cần trả thêm một nhóm bài viết khi người dùng bấm “Xem thêm”. Hai giao diện cùng lấy dữ liệu có giới hạn nhưng yêu cầu metadata khác nhau.

Spring Data Commons cung cấp `Page<T>` và `Slice<T>` để diễn đạt sự khác biệt đó:

- `Page<T>` cung cấp nội dung trang cùng thông tin tổng số phần tử và tổng số trang.
- `Slice<T>` cung cấp một phần dữ liệu cùng thông tin điều hướng, đặc biệt là còn phần tiếp theo hay không, mà không yêu cầu biết tổng.

Biết tổng là một yêu cầu dữ liệu bổ sung. Nó có thể đòi hỏi một truy vấn đếm hoặc công việc tương đương trên kho dữ liệu. Nếu người gọi không sử dụng tổng, chọn kiểu kết quả yêu cầu tổng có thể tạo ra công việc không cần thiết.

Ngược lại, bỏ tổng khi giao diện vẫn cần tổng không phải tối ưu cùng chức năng. Trước hết cần xác định hợp đồng người gọi thực sự cần.

Trong phạm vi Spring Data Commons, đây là các abstraction chung. Việc áp dụng phân trang, cách đếm và hỗ trợ kiểu trả về phụ thuộc mô-đun kho dữ liệu. Các ví dụ JPA trong bài được ghi rõ phạm vi, không phải query dùng nguyên trạng cho mọi loại repository.

## 2. Page mở rộng Slice nhưng có thêm trách nhiệm

Về quan hệ kiểu, `Page<T>` mở rộng `Slice<T>`. Vì vậy, một Page cũng cung cấp các thao tác mà người gọi thường dùng ở Slice.

| Thông tin hoặc thao tác | Slice | Page |
| --- | --- | --- |
| `getContent()` | Danh sách phần tử của lát dữ liệu | Danh sách phần tử của trang |
| `getNumber()` | Số trang/lát theo yêu cầu phân trang | Có |
| `getSize()` | Kích thước yêu cầu | Có |
| `getNumberOfElements()` | Số phần tử thực tế trong kết quả hiện tại | Có |
| `hasNext()` | Có còn phần tiếp theo không | Có |
| `hasPrevious()` | Thông tin còn phần trước theo vị trí phân trang | Có |
| `getTotalElements()` | Không thuộc hợp đồng | Tổng số phần tử phù hợp |
| `getTotalPages()` | Không thuộc hợp đồng | Tổng số trang theo thông tin tổng |

Điều cần phân biệt:

- `getSize()` không nhất thiết bằng số phần tử thực tế nhận được.
- `getNumberOfElements()` không phải tổng số bản ghi phù hợp truy vấn.
- `getContent().size()` cũng chỉ phản ánh nội dung hiện tại.
- `hasNext()` trả lời về khả năng đi tiếp, không trả tổng số trang còn lại.

Ví dụ yêu cầu size 20 nhưng trang cuối chỉ có 7 phần tử: size vẫn là kích thước yêu cầu, còn số phần tử thực tế là 7.

### 2.1. Đổi kiểu biến không đổi cách query đã chạy

Nếu repository trả Page, đoạn sau không làm mất chi phí tính tổng:

```java
Slice<PurchaseOrder> result = repository.findPageByCustomerIdAndStatus(
        customerId, status, pageable);
```

Đối tượng được nhìn qua kiểu Slice nhưng query method vẫn có hợp đồng trả Page. Tương tự, lấy `page.getContent()` rồi bỏ qua total trong controller không chứng minh truy vấn đếm chưa được thực hiện.

Muốn thay đổi chiến lược lấy dữ liệu, cần chọn query method hoặc implementation có hợp đồng phù hợp, không chỉ đổi kiểu biến ở phía gọi.

## 3. Pageable xác định phần dữ liệu cần lấy

Một yêu cầu phân trang thường được tạo như sau:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")));
```

Trong mô hình này:

- Số trang bắt đầu từ 0.
- Size 20 nghĩa là yêu cầu tối đa 20 phần tử nội dung cho một trang hoặc lát.
- Sort biểu đạt thứ tự cần dùng khi xác định phần dữ liệu.

Với phân trang offset thông thường, offset được tính từ số trang và kích thước trang. Ví dụ trang 3, size 20 có offset 60.

`Pageable` không tự quyết định người gọi cần tổng hay không. Cùng một yêu cầu Pageable có thể được dùng cho query method trả Page hoặc Slice, nếu mô-đun hỗ trợ.

Thứ tự cần đủ rõ để phân trang. Nếu nhiều đơn hàng có cùng `createdAt`, khóa phụ `id` giúp phân xử các giá trị bằng nhau. Tuy nhiên, thứ tự xác định trên cùng dữ liệu không tự bảo đảm dữ liệu không đổi giữa hai request.

## 4. Page lấy thông tin tổng như thế nào?

### 4.1. Query dữ liệu và query đếm

Một cách thực thi Page phổ biến trong repository quan hệ gồm:

```text
Query dữ liệu: lấy phần kết quả tại offset và limit được yêu cầu.
Query đếm: xác định tổng số phần tử phù hợp cùng điều kiện.
```

Ví dụ ý tưởng SQL, không cố định cú pháp cho mọi hệ quản trị:

```sql
-- Nội dung trang
select ...
from purchase_orders
where customer_id = :customerId
  and status = :status
order by created_at desc, id desc
-- áp dụng offset và limit theo hệ quản trị

-- Tổng số phần tử phù hợp
select count(*)
from purchase_orders
where customer_id = :customerId
  and status = :status
```

Query đếm không chỉ đếm số hàng vừa lấy trong trang. Nếu có 12.500 đơn phù hợp và trang trả 20 đơn, total phải phản ánh 12.500 theo hợp đồng và điều kiện truy vấn, không phải 20.

Giới hạn nội dung trang không tự làm cho việc tính tổng chỉ cần xét cùng 20 hàng đó.

### 4.2. Không phải mỗi Page luôn chạy đúng hai query

Một số cách thực thi có thể suy ra tổng từ số phần tử và vị trí trang trong những trường hợp đủ điều kiện, chẳng hạn đã có bằng chứng về phần cuối của kết quả. Khi đó truy vấn đếm riêng có thể được bỏ qua.

Cơ chế cụ thể phụ thuộc mô-đun, phiên bản và dạng query. Vì vậy, hai phát biểu sau đều không nên được dùng như quy tắc tuyệt đối:

- “Trả Page luôn chạy đúng hai câu SQL.”
- “Trả Page không cần count vì trang hiện tại đã có dữ liệu.”

Hợp đồng cần biết tổng vẫn tồn tại. Framework chỉ có thể tránh một bước nếu có cơ sở khác để xác định thông tin ấy. Cần quan sát đường thực thi thực tế nếu số query hoặc chi phí là điều đang tối ưu.

### 4.3. Total là một phần kết quả, không phải phép đo miễn phí

Với một bộ lọc nhỏ được hỗ trợ tốt bởi index, count có thể tương đối rẻ. Với join, điều kiện phức tạp, nhiều dữ liệu hoặc tổng hợp, công việc đếm có thể đáng kể.

Không nên kết luận mọi count đều quét toàn bộ bảng hoặc luôn chậm hơn query dữ liệu. Cũng không nên mặc định count rẻ chỉ vì không cần tải entity.

## 5. Slice xác định còn dữ liệu bằng cách đọc thêm

Một cách thực thi Slice phổ biến là yêu cầu tối đa `size + 1` phần tử từ vị trí hiện tại. Phần tử đọc thêm được dùng để xác định `hasNext`, sau đó không xuất hiện trong nội dung trả về.

Ví dụ size bằng 3:

```text
Đọc tối đa 4 phần tử.
Nếu nhận 4: trả 3 phần tử đầu và hasNext = true.
Nếu nhận từ 0 đến 3: trả toàn bộ phần đã nhận và hasNext = false.
```

Đây là mẫu thực thi phổ biến, không phải cam kết mọi mô-đun phải có cùng câu query nội bộ. Hợp đồng quan trọng là metadata đi tiếp phải phản ánh cách lấy dữ liệu đúng.

### 5.1. Minh họa với 7 phần tử

Giả sử kết quả đã có thứ tự rõ ràng gồm các id từ 101 đến 107, size bằng 3:

| Lát | Offset | Dữ liệu có thể đọc để quyết định | Nội dung trả | hasNext |
| --- | --- | --- | --- | --- |
| 0 | 0 | 101, 102, 103, 104 | 101, 102, 103 | true |
| 1 | 3 | 104, 105, 106, 107 | 104, 105, 106 | true |
| 2 | 6 | 107 | 107 | false |

Lát 0 có thể biết còn ít nhất một phần tử phía sau, nhưng không biết toàn bộ kết quả có 7 hay 70.000 phần tử.

Một phần tử được dùng làm bằng chứng còn dữ liệu có thể được đọc lại khi truy vấn lát kế tiếp. Đó là công việc nhỏ có chủ đích để tránh yêu cầu tổng.

### 5.2. Đủ size không chứng minh còn phần tiếp theo

Nếu toàn bộ kết quả chỉ có 6 phần tử, lát thứ hai có thể trả đúng 3 phần tử nhưng `hasNext` vẫn là false, vì không có phần tử thứ tư để chứng minh đi tiếp.

Vì vậy, một phương thức trả `List<T>` với size 3 không thể chỉ dựa vào `list.size() == 3` để kết luận `hasNext = true`. Cần cơ chế bổ sung như đọc dư một phần tử hoặc một kiểm tra phù hợp khác.

### 5.3. Đọc size + 1 không phải vấn đề N+1 query

“Đọc thêm một hàng” ở đây khác vấn đề N+1 khi mỗi entity lại gây một query lấy quan hệ. Slice có thể tránh count nhưng vẫn gặp N+1, lazy loading hoặc các truy vấn bổ sung khác do mapping và cách sử dụng dữ liệu.

Không nên hứa rằng trả Slice luôn đồng nghĩa đúng một lần truy cập kho dữ liệu cho toàn bộ request.

## 6. So sánh chi phí theo công việc cần làm

Có thể dùng mô hình đơn giản để thảo luận, không coi là công thức thời gian cố định:

```text
Chi phí Page
  = lấy nội dung
  + xác định tổng khi cần
  + ánh xạ và xử lý dữ liệu liên quan

Chi phí Slice
  = lấy nội dung và đủ bằng chứng về phần tiếp theo
  + ánh xạ và xử lý dữ liệu liên quan
```

Những yếu tố thường ảnh hưởng:

| Yếu tố | Tác động cần xem xét |
| --- | --- |
| Số bản ghi phù hợp | Count có thể phải xét phạm vi lớn hơn nội dung trang |
| Join và khử lặp | Tổng entity có thể khác tổng hàng trung gian |
| Điều kiện lọc | Ảnh hưởng cả query dữ liệu và count |
| Sort | Query dữ liệu có thể phải làm nhiều công việc dù chỉ trả ít hàng |
| Offset sâu | Slice dùng offset vẫn có thể tốn chi phí bỏ qua vùng trước |
| Mapping và quan hệ | Có thể phát sinh thêm query hoặc nhiều dữ liệu được nạp |
| Tần suất request | Một count không quá đắt nhưng chạy liên tục vẫn có chi phí tích lũy |

Chọn Slice có thể loại bỏ yêu cầu tổng khỏi đường gọi. Nó không sửa index, không bỏ join không cần thiết và không tự biến offset thành keyset.

Nếu số lượng query giảm nhưng thời gian gần như không đổi, có thể phần tốn kém đang nằm ở query dữ liệu hoặc xử lý entity. Cần đo đúng thành phần thay vì chỉ nhìn kiểu trả về.

## 7. Repository minh họa: cùng bộ lọc, khác hợp đồng kết quả

Giả sử entity `PurchaseOrder` có các thuộc tính `id` kiểu Long, `customerId` kiểu Long, `status` kiểu String, `createdAt` kiểu Instant và `total` kiểu BigDecimal. Entity đã được ánh xạ đúng với mô-đun kho dữ liệu.

Repository có thể công khai ba phương thức khi mô-đun hỗ trợ các kiểu kết quả tương ứng:

```java
import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.repository.Repository;

public interface PurchaseOrderRepository
        extends Repository<PurchaseOrder, Long> {

    Page<PurchaseOrder> findPageByCustomerIdAndStatus(
            Long customerId, String status, Pageable pageable);

    Slice<PurchaseOrder> findSliceByCustomerIdAndStatus(
            Long customerId, String status, Pageable pageable);

    List<PurchaseOrder> findListByCustomerIdAndStatus(
            Long customerId, String status, Pageable pageable);
}
```

`Page`, `Slice` hoặc `List` trong phần tên trước `By` giúp phân biệt các phương thức cho người đọc. Hợp đồng kiểu trả về mới là thông tin quan trọng để chọn cách xử lý kết quả; không phải cứ đặt chữ `Slice` vào tên là một phương thức trả Page sẽ tránh count.

Java không cho overload hai phương thức chỉ bằng kiểu trả về. Dùng các tên khác nhau trong ví dụ giúp so sánh rõ ba hợp đồng mà không tạo chữ ký trùng.

### 7.1. Service chọn đúng nhu cầu

Ví dụ service sau dùng cùng một cách kiểm tra và tạo Pageable:

```java
import java.util.Objects;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Sort;

public final class OrderReadService {
    private final PurchaseOrderRepository repository;

    public OrderReadService(PurchaseOrderRepository repository) {
        this.repository = Objects.requireNonNull(repository);
    }

    public Page<PurchaseOrder> searchWithTotal(
            Long customerId, String status, int page, int size) {
        Objects.requireNonNull(customerId, "customerId");
        Objects.requireNonNull(status, "status");
        return repository.findPageByCustomerIdAndStatus(
                customerId, status, request(page, size));
    }

    public Slice<PurchaseOrder> loadMore(
            Long customerId, String status, int page, int size) {
        Objects.requireNonNull(customerId, "customerId");
        Objects.requireNonNull(status, "status");
        return repository.findSliceByCustomerIdAndStatus(
                customerId, status, request(page, size));
    }

    private static Pageable request(int page, int size) {
        if (page < 0 || size < 1 || size > 100) {
            throw new IllegalArgumentException(
                    "page phải không âm; size phải trong [1, 100]");
        }
        return PageRequest.of(page, size, Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")));
    }
}
```

Service giả định phạm vi `customerId` đã được xác định hoặc kiểm tra quyền ở ranh giới ứng dụng phù hợp. Một điều kiện customerId không tự thay thế toàn bộ chính sách truy cập.

Hai phương thức có cùng bộ lọc và thứ tự, nhưng người gọi chủ động chọn có cần thông tin tổng hay không. Đây là một cách thể hiện khác biệt nghiệp vụ trong hợp đồng, thay vì lấy Page ở mọi nơi rồi bỏ total khi không dùng.

### 7.2. List với Pageable chưa đủ thay Slice

Phương thức trả List có thể phù hợp nếu chỉ cần nội dung có giới hạn. Tuy nhiên, List không cung cấp `hasNext()` và không nói tổng số phần tử phù hợp.

Nếu gọi `findListByCustomerIdAndStatus` với size 20 rồi nhận đúng 20 phần tử, vẫn chưa biết còn hàng thứ 21 hay không. Không thể tự gán một metadata chính xác chỉ từ độ dài ấy.

## 8. Count phải đếm đúng đối tượng mà trang đang trả

### 8.1. Ví dụ khai báo count riêng trong JPA

Với Spring Data JPA, có thể cung cấp query dữ liệu và query count rõ ràng:

```java
@Query(
    value = "select o from PurchaseOrder o "
          + "where o.customerId = :customerId "
          + "and o.status = :status",
    countQuery = "select count(o) from PurchaseOrder o "
          + "where o.customerId = :customerId "
          + "and o.status = :status"
)
Page<PurchaseOrder> searchWithDeclaredCount(
        @Param("customerId") Long customerId,
        @Param("status") String status,
        Pageable pageable);
```

Đây là phương thức đặt trong repository JPA phù hợp, dùng `org.springframework.data.jpa.repository.Query` và `org.springframework.data.repository.query.Param`. Annotation Query này thuộc mô-đun JPA, không phải annotation chung dùng nguyên trạng cho mọi loại kho dữ liệu.

Trong ví dụ, Sort của Pageable cung cấp thứ tự cho query dữ liệu theo khả năng tích hợp của JPA. Query count không cần trả entity và không cần phần sắp xếp của trang.

Khai báo `countQuery` giúp xác định biểu thức dùng khi cần đếm; nó không có nghĩa mọi lần gọi nhất thiết phải thực hiện count riêng bất kể các tối ưu hợp lệ của mô-đun.

### 8.2. Điều kiện count phải giữ đúng phạm vi

Nếu query dữ liệu lọc theo khách hàng, trạng thái, tenant hoặc quyền xem, count cũng phải đếm cùng phạm vi tương ứng.

Một query lấy đúng 20 đơn của khách hàng hiện tại nhưng count toàn bộ đơn trong hệ thống sẽ tạo metadata sai. Nó còn có thể làm lộ thông tin tổng ngoài phạm vi được phép xem.

Cần dùng cùng ý nghĩa tham số và bộ lọc. Không chỉ sao chép một phần điều kiện vì cho rằng count là chi tiết phụ của giao diện.

### 8.3. Join làm số hàng khác số entity

Nếu một đơn có nhiều dòng hàng phù hợp, join có thể tạo nhiều hàng trung gian cho cùng một đơn. Query nội dung có thể trả entity phân biệt, trong khi một count đơn giản lại đếm số hàng join.

Cần xác định rõ đơn vị kết quả:

- Đơn hàng.
- Dòng hàng.
- Cặp quan hệ.
- Nhóm tổng hợp.

Với mô hình đơn giản có id Long, đếm các đơn phân biệt có thể cần biểu thức như `count(distinct o.id)` trong query thích hợp. Không áp dụng công thức đó máy móc nếu yêu cầu thực sự là đếm nhóm hoặc có cấu trúc khóa khác.

Một query tổng hợp có `GROUP BY` cũng cần xác định tổng là số nhóm hay số entity đầu vào. Hai giá trị đó không thay thế nhau.

### 8.4. Count đúng chưa sửa mọi vấn đề của query nội dung

Collection fetch join cùng phân trang có thể gặp vấn đề về số hàng đọc, giới hạn hoặc cách provider xử lý. Viết count riêng đúng không tự làm query dữ liệu đó phù hợp với mọi trường hợp.

Có thể cần thay fetch plan, dùng projection hoặc thiết kế hai bước lấy định danh rồi đọc dữ liệu. Mỗi hướng phải giữ thứ tự, bộ lọc và metadata đúng, đồng thời được kiểm chứng với mô-đun và provider thực tế.

## 9. Tự triển khai Slice trong fragment

Khi repository đã hỗ trợ query method trả Slice phù hợp, nên dùng cơ chế đó. Với fragment cần điều khiển query riêng, có thể áp dụng mẫu đọc dư một phần tử.

Các bước về mặt thuật toán:

1. Kiểm tra yêu cầu phân trang và giới hạn size theo chính sách.
2. Áp dụng cùng bộ lọc và thứ tự vào query.
3. Dùng offset hoặc vị trí tiếp tục phù hợp.
4. Đọc nhiều nhất size + 1 phần tử theo cơ chế kho dữ liệu.
5. Dùng phần tử dư để xác định `hasNext`.
6. Chỉ đưa size phần tử đầu vào nội dung Slice.

Một helper chuyển kết quả đã đọc đúng sang Slice có thể là:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.SliceImpl;

public final class SliceResults {
    private SliceResults() {
    }

    public static <T> Slice<T> fromFetched(
            List<T> fetched, Pageable pageable) {
        Objects.requireNonNull(fetched, "fetched");
        Objects.requireNonNull(pageable, "pageable");
        if (pageable.isUnpaged()) {
            throw new IllegalArgumentException("Cần yêu cầu phân trang");
        }

        int size = pageable.getPageSize();
        boolean hasNext = fetched.size() > size;
        int end = Math.min(size, fetched.size());
        List<T> content = new ArrayList<>(fetched.subList(0, end));

        return new SliceImpl<>(content, pageable, hasNext);
    }
}
```

Helper giả định query trước đó đã đọc đúng phần dữ liệu tại vị trí yêu cầu và đã cố đọc thêm một phần tử. Nó không tự truy vấn DB, không tự áp dụng offset, không tự giới hạn query và không kiểm chứng được những việc ấy chỉ từ List đầu vào.

Không đọc toàn bộ tập kết quả lớn rồi dùng helper để cắt trong bộ nhớ và gọi đó là tối ưu Slice. Việc tránh count không có nhiều ý nghĩa nếu implementation vẫn nạp toàn bộ dữ liệu.

Cũng không gọi helper với một List chỉ được đọc đúng size rồi kỳ vọng metadata `hasNext` luôn đúng. Khi thiếu bằng chứng phần tử dư, helper không thể biết một hàng chưa được lấy.

## 10. Hợp đồng API khi trả Page hoặc Slice

Một API có thể dùng DTO riêng để thể hiện rõ metadata muốn công khai. Ví dụ với trang đầu có size 2 và tổng 5 đơn:

```json
{
  "items": [{"id": 101}, {"id": 102}],
  "page": 0,
  "size": 2,
  "hasNext": true,
  "totalElements": 5,
  "totalPages": 3
}
```

Nếu API chỉ cung cấp Slice:

```json
{
  "items": [{"id": 101}, {"id": 102}],
  "page": 0,
  "size": 2,
  "hasNext": true
}
```

Không điền `totalElements = 0` chỉ vì không biết tổng. Số 0 có nghĩa có thông tin tổng và tổng bằng 0; nó không phải ký hiệu chung cho “chưa tính”.

Nếu có tổng ước lượng hoặc tổng tính ở thời điểm khác, nên dùng một hợp đồng có tên và ý nghĩa rõ, chẳng hạn trường ước lượng hoặc thời điểm thống kê. Đừng biến một giá trị ước lượng thành total của Page mà để người dùng hiểu là cùng mức chính xác với count hiện tại.

### 10.1. Map giữ metadata, filter có thể thay đổi ngữ nghĩa

Page và Slice có cơ chế `map` để ánh xạ phần tử. Ví dụ một record DTO dùng Java 17 trở lên:

```java
public record OrderItem(Long id, BigDecimal total) {
}
```

Ánh xạ Page:

```java
Page<OrderItem> result = page.map(order ->
        new OrderItem(order.getId(), order.getTotal()));
```

Record cần import `java.math.BigDecimal`. Phép map giữ hợp đồng nội dung và metadata tương ứng; bản thân việc map không yêu cầu một count mới. Cách truy cập dữ liệu trong mapper vẫn cần tránh phát sinh tải quan hệ ngoài ý muốn.

Ngược lại, lấy nội dung rồi lọc bỏ một số đơn có thể làm số lượng hiển thị không còn cùng đơn vị với total hoặc `hasNext`. Nếu đó là điều kiện xác định phần tử được phép trả, thường phải đưa vào query phù hợp trước bước phân trang.

### 10.2. Không dựng Page với một tổng bịa từ Slice

Một Slice có 20 phần tử không chứng minh tổng bằng 20. Việc tạo Page từ nội dung Slice rồi dùng kích thước nội dung làm total có thể làm sai tổng số trang và điều hướng.

Nếu thực sự cần Page, phải có cơ sở xác định tổng tương ứng. Nếu chưa cần tổng, giữ hợp đồng Slice thay vì điền metadata cho đủ hình dạng phản hồi.

## 11. Tổng chính xác trong bối cảnh dữ liệu thay đổi

### 11.1. Hai query có thể quan sát hai trạng thái

Query dữ liệu và count có thể chạy ở những thời điểm khác nhau. Nếu dữ liệu được thêm, xóa hoặc đổi trạng thái giữa hai bước, nội dung và total có thể không phản ánh cùng một snapshot.

Một transaction read-only không tự bảo đảm mọi hệ quản trị và mức isolation đều cung cấp cùng một snapshot cho tất cả câu lệnh. Cần xác định hợp đồng transaction và khả năng kho dữ liệu nếu tính nhất quán này quan trọng.

Có total không có nghĩa một bản ghi chắc chắn còn tồn tại khi người dùng mở trang tiếp theo hoặc thực hiện thao tác ghi sau đó.

### 11.2. Slice cũng chỉ có thông tin tại lần đọc đó

`hasNext = true` là bằng chứng còn dữ liệu theo cách lấy kết quả tại thời điểm truy vấn. Một request sau vẫn có thể thấy thay đổi nếu các bản ghi đã bị xóa hoặc không còn phù hợp bộ lọc.

Tương tự, `hasNext = false` không khẳng định sẽ không bao giờ có dữ liệu mới được thêm sau đó. Cần đọc metadata trong phạm vi thời điểm và điều kiện truy vấn.

### 11.3. Trang vượt phạm vi có thể rỗng dù tổng lớn hơn 0

Giả sử có 75 phần tử, size 20, các trang chứa dữ liệu được đánh số 0 đến 3. Nếu người dùng yêu cầu trang 4, nội dung có thể rỗng trong khi một Page vẫn có total 75 khi tổng được xác định.

Do đó, `page.getContent().isEmpty()` không tự chứng minh toàn bộ bộ lọc không có kết quả. Với Slice không có tổng, một lát rỗng cũng không đủ để phân biệt mọi nguyên nhân như yêu cầu vượt phần cuối hoặc dữ liệu vừa thay đổi.

API cần quyết định cách xử lý yêu cầu vượt phạm vi: trả nội dung rỗng, báo lỗi theo hợp đồng hoặc hướng người dùng về vị trí phù hợp. Không thể suy ra chính sách ấy chỉ từ kiểu trả về.

## 12. Tránh count không đồng nghĩa tránh offset sâu

Một Slice được lấy bằng `PageRequest.of(10000, 20, sort)` vẫn có thể dùng offset lớn. Kho dữ liệu có thể phải làm nhiều công việc để xác định hoặc bỏ qua phần kết quả trước vị trí đó.

Vì vậy, cần tách hai mục tiêu:

- Không tính tổng khi không cần: xem xét Slice.
- Tránh chi phí và đặc tính của offset sâu: xem xét cơ chế tiếp tục theo khóa hoặc cursor nếu mô-đun hỗ trợ.

Một Window hoặc cơ chế scrolling phù hợp có thể giải quyết một phần bài toán tiếp tục đọc, nhưng mức hỗ trợ, điều kiện sort và giới hạn thuộc mô-đun. Nó không tự cung cấp tổng chính xác miễn phí.

Với tác vụ xử lý toàn bộ dữ liệu, cũng cần xem khả năng dừng, ghi nhận vị trí tiếp tục và ảnh hưởng của dữ liệu đổi trong quá trình chạy. Chỉ thay Page bằng Slice chưa hoàn thành thiết kế một quy trình đọc lớn.

## 13. Lựa chọn theo nhu cầu sản phẩm

| Nhu cầu | Hợp đồng nên xem xét | Chi phí hoặc giới hạn cần chấp nhận |
| --- | --- | --- |
| Hiển thị tổng, số trang, chuyển trang cuối | Page | Cần xác định tổng đúng, có thể phát sinh count đáng kể |
| Nút Xem thêm hoặc đọc tiếp một lát | Slice | Không có tổng số trang hoặc tổng phần tử |
| Chỉ trả một tập con có giới hạn | List với cơ chế giới hạn phù hợp | Không có `hasNext` chính xác chỉ từ việc đủ size |
| Cần tổng khi người dùng chủ động hỏi | Nội dung và thao tác thống kê riêng theo hợp đồng | Tổng có thời điểm và phạm vi cần làm rõ |
| Chấp nhận số ước lượng | DTO có metadata ước lượng rõ ràng | Không gọi ước lượng là total chính xác của cùng snapshot |
| Đọc tiếp ở tập dữ liệu lớn, trang sâu | Scrolling/keyset/cursor được mô-đun hỗ trợ | Có yêu cầu riêng về khóa, sort và khả năng điều hướng |

Page không phải lựa chọn sai nếu người dùng cần tổng và count có chi phí phù hợp. Slice cũng không phải lựa chọn tốt hơn trong mọi trường hợp: nó bỏ một phần thông tin mà một số giao diện cần.

Có thể dùng Page cho màn hình tìm kiếm quản trị và Slice cho bảng tin trong cùng ứng dụng. Không cần ép toàn bộ repository về một kiểu duy nhất khi câu hỏi người gọi khác nhau.

## 14. Đánh giá hiệu năng và độ đúng cùng nhau

Trong dự án thực tế, khi so sánh Page và Slice, nên giữ cùng:

- Điều kiện lọc và phạm vi truy cập.
- Thứ tự, kích thước và vị trí yêu cầu.
- Dạng dữ liệu cần trả và cách tải các quan hệ.
- Dữ liệu đại diện, gồm số lượng và phân bố các giá trị.

Sau đó mới xác định phần khác biệt mong muốn là việc có hoặc không tính tổng.

Những điều cần quan sát có thể gồm thời gian query nội dung, count, số hàng xử lý, số query phát sinh do quan hệ và chi phí mapping. Số query ít hơn không tự bảo đảm request nhanh hơn trong mọi tình huống.

Không kết luận rằng Slice cải thiện count chỉ bằng một bộ dữ liệu rất nhỏ. Cũng không quy mọi khác biệt cho count nếu hai đường thực thi đang chọn cột, join hoặc kích thước khác nhau.

Nếu framework bỏ count trong một ca Page cụ thể, hãy xem thêm một ca mà count thực sự cần được xác định. Nếu dữ liệu luôn ít hơn size, chưa đủ bằng chứng cho chi phí của đường tìm kiếm có nhiều trang.

## 15. Các ca kiểm chứng có ý nghĩa

| Ca | Điều cần bảo vệ |
| --- | --- |
| Không có phần tử phù hợp | Nội dung rỗng và metadata đúng hợp đồng |
| Ít hơn size phần tử | Slice không báo đi tiếp khi không có dữ liệu dư |
| Đúng size phần tử, không còn hàng sau | Không suy ra `hasNext = true` chỉ vì đủ size |
| Size + 1 phần tử | Nội dung chỉ có size phần tử, `hasNext = true` |
| Nhiều trang với phần cuối ngắn | Không mất hoặc lặp phần tử trên dữ liệu ổn định và sort xác định |
| Nhiều giá trị bằng tiêu chí sort chính | Khóa phụ phân xử rõ thứ tự |
| Query join làm nhân số hàng | Total đếm đúng đơn vị kết quả |
| Có bộ lọc tenant hoặc quyền xem | Count và nội dung cùng phạm vi |
| Trang vượt phần cuối | Không nhầm nội dung rỗng với total toàn bộ bằng 0 |
| Mapping sang DTO | Giữ metadata khi chỉ map một-một |
| Chuyển Page sang Slice | Hợp đồng API và người tiêu thụ được điều chỉnh phù hợp |
| Đường query phức tạp | Count sinh tự động hoặc khai báo riêng thực thi đúng trên kho dữ liệu |

Kiểm chứng helper Java có thể bảo vệ logic cắt phần tử dư. Nó không chứng minh query trước helper đã áp dụng đúng offset, limit và sort. Những đặc tính ấy cần kiểm chứng tích hợp phù hợp với mô-đun.

Về hiệu năng, cần quan sát câu truy vấn thực tế và kế hoạch thực thi khi cần, thay vì khóa kiểm thử vào giả định “mọi Page luôn hai query” hoặc “mọi Slice luôn một query”.

## 16. Tình huống tự đánh giá

### A. Giao diện không dùng total

Repository trả Page nhưng controller chỉ gửi content và `hasNext`. Nhóm muốn bỏ truy vấn đếm bằng cách đổi kiểu biến trong controller sang Slice.

Giải thích vì sao thay đổi này chưa đủ. Nêu nơi cần đổi hợp đồng và những phần API phải kiểm tra lại.

### B. Danh sách đầy không chứng minh có trang sau

Một phương thức trả List nhận size 20. Người viết đặt `hasNext = list.size() == 20`, trong khi toàn bộ bộ lọc chỉ có đúng 20 kết quả.

Chỉ ra metadata sai và cách lấy đủ bằng chứng để trả Slice đúng.

### C. Count hàng join thay vì count đơn

Một đơn hàng có ba dòng phù hợp bộ lọc. Query nội dung trả mỗi đơn một lần, nhưng count đếm ba hàng join cho đơn ấy.

Xác định đơn vị cần đếm và cách thiết kế lại count. Giải thích vì sao chỉ tối ưu thời gian count mà không sửa ngữ nghĩa vẫn làm Page sai.

### D. Slice ở trang rất sâu vẫn chậm

Sau khi chuyển Page sang Slice, request ở trang 10.000 vẫn mất nhiều thời gian dù count đã được bỏ.

Phân biệt chi phí tổng với chi phí offset. Nêu dữ liệu cần quan sát và cơ chế tiếp tục có thể đánh giá theo khả năng mô-đun.

### E. Đặt total bằng kích thước Slice

Một adapter tạo phản hồi có total từ `slice.getNumberOfElements()` để giữ hình dạng API cũ. Kết quả đầu có 20 phần tử nhưng bộ lọc thực tế có nhiều trang.

Giải thích thông tin đã bị bịa và lựa chọn đúng giữa giữ Page với tổng thật hoặc thay hợp đồng API sang Slice.

### F. Có dữ liệu thay đổi giữa content và count

Một đơn được thêm vào sau khi query nội dung chạy nhưng trước khi count chạy. Hai phần metadata không phản ánh cùng trạng thái.

Xác định yêu cầu nhất quán cần làm rõ. Giải thích vì sao chỉ thêm read-only không đủ để khẳng định mọi môi trường đều có cùng snapshot.