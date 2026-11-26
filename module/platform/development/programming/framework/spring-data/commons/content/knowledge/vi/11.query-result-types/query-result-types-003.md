# Page, Slice và Window theo khả năng của store

Một màn hình cần tổng số trang, một danh sách chỉ cần nút “xem tiếp”, còn một tác vụ xử lý dữ liệu cần vị trí để tiếp tục duyệt. Cả ba đều lấy dữ liệu theo từng phần, nhưng chúng cần những hợp đồng kết quả khác nhau. Dùng cùng một kiểu trả về cho mọi trường hợp có thể khiến ứng dụng đếm dữ liệu không cần thiết hoặc thiếu thông tin để tiếp tục truy vấn đúng cách.

Trong chương **Kiểu kết quả truy vấn** của **SPRING_DATA_COMMONS**, bài này giải thích `Page`, `Slice` và `Window`, liên hệ chúng với `Pageable`, `ScrollPosition`, sắp xếp và projection. Trọng tâm là phân biệt abstraction mà Commons cung cấp với những tổ hợp mà module lưu trữ thực tế hỗ trợ.

## 1. Ba kiểu kết quả trả lời ba nhu cầu

| Kiểu | Caller nhận được gì? | Thông tin không được mặc định có |
| --- | --- | --- |
| `Page<T>` | Nội dung một trang, thông tin trang và metadata tổng số kết quả/trang | Không tự tạo snapshot nhất quán xuyên nhiều lần đọc |
| `Slice<T>` | Nội dung một lát, thông tin trang và khả năng còn lát tiếp theo | Không có `totalElements` hoặc `totalPages` như `Page` |
| `Window<T>` | Nội dung một cửa sổ, khả năng còn kết quả và vị trí để tiếp tục scrolling | Không có tổng số hoặc số trang như hợp đồng `Page` |

`Page` mở rộng `Slice`, nên có các hành vi cơ bản của một lát cùng metadata tổng số. `Window` là một abstraction scrolling riêng, không phải một tên khác cho `Page`.

Cả ba kiểu đều chứa dữ liệu hữu hạn của lần lấy kết quả hiện tại. Chúng không đồng nghĩa với một `Stream` đang mở hoặc một publisher reactive có thể phát dữ liệu về sau.

Điểm quyết định ban đầu là nhu cầu của caller:

```text
Cần tổng số và số trang?
    -> Xem xét Page

Không cần tổng, chỉ cần tiếp tục theo trang?
    -> Xem xét Slice

Cần tiếp tục từ một vị trí scrolling?
    -> Xem xét Window nếu module hỗ trợ
```

Sau lựa chọn này còn phải xác nhận hình dạng truy vấn, bộ phiên bản, module và kho dữ liệu có thực hiện được hợp đồng đó không.

## 2. Phân biệt đầu vào truy vấn với đầu ra kết quả

Các kiểu thường đi cùng nhau nhưng có vai trò khác nhau:

| Vai trò | Abstraction tiêu biểu | Nội dung |
| --- | --- | --- |
| Yêu cầu truy cập theo trang | `Pageable` | Chỉ số trang, kích thước và sort |
| Vị trí tiếp tục scrolling | `ScrollPosition` | Một vị trí offset hoặc keyset theo cơ chế được hỗ trợ |
| Thứ tự | `Sort` | Các thuộc tính và hướng sắp xếp |
| Kết quả có tổng số | `Page<T>` | Nội dung trang và metadata tổng |
| Kết quả không cần tổng | `Slice<T>` | Nội dung lát và thông tin còn lát tiếp |
| Kết quả có vị trí tiếp tục | `Window<T>` | Nội dung cửa sổ và các vị trí scrolling |

`Pageable` không phải một tập kết quả. `Window` không tự định nghĩa kích thước yêu cầu chỉ bằng tên kiểu trả về: kích thước cần đến từ cơ chế giới hạn mà module hỗ trợ, chẳng hạn keyword `First`/`Top` trong một derived query.

Một phương thức trả `List<T>` và nhận `Pageable` cũng không tự trả thêm tổng số hoặc `hasNext`. Kiểu đầu ra là một phần của hợp đồng; không thể suy ra toàn bộ metadata chỉ từ việc phương thức có tham số phân trang.

## 3. Mô hình dùng trong ví dụ

Giả sử domain `PurchaseOrder` có những thuộc tính Java sau:

| Thuộc tính | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `id` | `Long` | Định danh duy nhất |
| `tenantId` | `String` | Phạm vi tổ chức sở hữu dữ liệu |
| `status` | `OrderStatus` | Trạng thái nghiệp vụ |
| `createdAt` | `Instant` | Thời điểm tạo, giả định không null |
| `total` | `BigDecimal` | Tổng tiền |

```java
public enum OrderStatus {
    NEW, PAID, CANCELLED
}
```

Các ví dụ đồng bộ chính bên dưới dùng **Spring Data JPA** với entity đã được ánh xạ đầy đủ. Constructor, accessor, cấu hình persistence và transaction được lược bỏ để tập trung vào hợp đồng kết quả. Ví dụ scrolling giả định bộ phiên bản JPA module đang dùng hỗ trợ derived query trả `Window` và loại `ScrollPosition` tương ứng.

Thứ tự xuyên suốt là:

```text
createdAt ASC, id ASC
```

`id` phân định các đơn có cùng thời điểm tạo. Tên thuộc tính trong `Sort` hoặc tên derived query là tên Java được mapping nhận diện, không phải tên cột SQL vật lý.

Phạm vi tenant và trạng thái phải giữ nguyên khi chuyển từ một phần kết quả sang phần tiếp theo. Một vị trí lấy từ truy vấn trước không tự mang theo hoặc tự áp dụng các điều kiện nghiệp vụ của lần gọi đó.

## 4. Page: một trang cùng tổng số kết quả

### 4.1. Chữ ký và cách gọi

Ví dụ repository Spring Data JPA:

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

Caller truyền yêu cầu trang:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

Sort order = Sort.by(Sort.Direction.ASC, "createdAt")
        .and(Sort.by(Sort.Direction.ASC, "id"));

Page<PurchaseOrder> page = repository.findByTenantIdAndStatus(
        "tenant-a",
        OrderStatus.PAID,
        PageRequest.of(0, 3, order));
```

Chỉ số trang bắt đầu từ `0`. Với kích thước `3`, trang `0` yêu cầu ba kết quả đầu, trang `1` yêu cầu phần tiếp theo theo cơ chế truy cập của module.

Metadata thường được sử dụng:

```java
page.getContent();          // Nội dung trang hiện tại
page.getNumber();           // Chỉ số trang hiện tại
page.getSize();             // Kích thước trang theo yêu cầu
page.getNumberOfElements(); // Số phần tử thực tế trong trang này
page.getTotalElements();    // Tổng số kết quả khớp điều kiện
page.getTotalPages();       // Tổng số trang theo metadata
page.hasNext();            // Có trang sau hay không
```

`getSize()` khác `getNumberOfElements()`: yêu cầu ba phần tử không có nghĩa trang cuối luôn có đủ ba phần tử.

### 4.2. Tổng số có chi phí riêng

Để cung cấp tổng, module có thể thực hiện một truy vấn lấy nội dung và một truy vấn đếm. Framework cũng có thể suy ra tổng từ nội dung và vị trí trang trong một số trường hợp, nên không nên khẳng định mọi lần trả `Page` luôn chạy đúng hai truy vấn.

Điều cần hiểu là `Page` có nghĩa vụ cung cấp metadata tổng, và việc thực hiện nghĩa vụ đó có thể đắt hơn chỉ lấy một lát dữ liệu.

Với truy vấn phức tạp, phép đếm cần giữ đúng:

- Cùng phạm vi tenant và bộ lọc nghiệp vụ.
- Cùng đơn vị cần đếm, chẳng hạn entity gốc thay vì số dòng join trung gian.
- Ngữ nghĩa `distinct`, grouping hoặc projection liên quan.

Trong Spring Data JPA, truy vấn khai báo có thể cần `countQuery` thích hợp nếu không thể suy ra đúng. Việc trả nội dung trang đúng không tự chứng minh tổng số cũng đúng.

### 4.3. Page phù hợp khi caller thật sự cần tổng

Một bảng có “trang 2 trên 8” hoặc “tổng cộng 23 đơn hàng” có lý do dùng `Page`. Nếu màn hình chỉ hiển thị các mục tiếp theo, việc tính tổng có thể không mang lại giá trị tương xứng với chi phí.

Ngoài ra, tổng và nội dung có thể được lấy bằng những thao tác riêng. Mức nhất quán giữa chúng phụ thuộc transaction, mức cô lập và kho dữ liệu. `Page` không tự biến các truy vấn thành một snapshot chung bất biến.

## 5. Slice: biết còn phần tiếp theo mà không yêu cầu tổng

### 5.1. Chữ ký

```java
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;

Slice<PurchaseOrder> findSliceByTenantIdAndStatus(
        String tenantId,
        OrderStatus status,
        Pageable pageable);
```

Phần `Slice` trong tên ví dụ là mô tả ở subject trước `By`; kiểu trả về mới xác định hợp đồng kết quả. Phương thức vẫn lọc theo tenant và trạng thái.

Caller có thể dùng cùng `PageRequest` và `Sort` như ví dụ `Page`:

```java
Slice<PurchaseOrder> slice = repository.findSliceByTenantIdAndStatus(
        "tenant-a",
        OrderStatus.PAID,
        PageRequest.of(0, 3, order));

boolean more = slice.hasNext();
```

`Slice` không cung cấp `getTotalElements()` hay `getTotalPages()` như `Page`. Không thể suy ra tổng chính xác chỉ từ kích thước lát hiện tại và một cờ còn dữ liệu.

### 5.2. Cách biết còn kết quả

Cách thực hiện thường gặp là yêu cầu thêm một phần tử so với kích thước lát. Nếu yêu cầu `3`, module có thể đọc tối đa `4` để xác định có phần tiếp theo, rồi trả ba phần tử nội dung.

Đây là mô hình thực hiện phổ biến, không phải cam kết rằng mọi store đều dùng cùng một câu SQL hoặc đúng cùng số lượt truy cập. Điểm của hợp đồng là caller nhận được nội dung và khả năng tiếp tục mà không yêu cầu một tổng số chính xác.

Không nên tự đặt:

```java
boolean hasNext = list.size() == requestedSize;
```

Nếu tổng số kết quả vừa đúng bằng kích thước yêu cầu, danh sách đủ kích thước nhưng không còn phần tử tiếp theo. `Slice` cần thêm thông tin để phân biệt trường hợp đó.

### 5.3. Di chuyển sang lát sau

Trong một vòng lặp đồng bộ với module hỗ trợ, có thể dùng metadata của lát:

```java
Pageable request = PageRequest.of(0, 3, order);

while (true) {
    Slice<PurchaseOrder> slice = repository.findSliceByTenantIdAndStatus(
            tenantId, OrderStatus.PAID, request);

    for (PurchaseOrder purchaseOrder : slice) {
        process(purchaseOrder);
    }

    if (!slice.hasNext()) {
        break;
    }

    request = slice.nextPageable();
}
```

`process(...)` là bước xử lý nghiệp vụ minh họa. Vòng lặp không tự tạo snapshot hay cơ chế khôi phục khi xử lý lỗi.

Quan trọng hơn, đổi `Page` thành `Slice` có thể tránh nhu cầu đếm tổng, nhưng không tự đổi phân trang offset thành keyset. Với một implementation dựa trên offset, các lát ở sâu vẫn có thể tốn chi phí bỏ qua nhiều dữ liệu.

## 6. Window: một cửa sổ kết quả cùng vị trí scrolling

### 6.1. Nội dung và vị trí là hai phần khác nhau

`Window<T>` mô tả một phần dữ liệu khi scrolling. Các thao tác quan trọng gồm:

```java
window.getContent();
window.size();
window.isEmpty();
window.hasNext();
window.positionAt(index);
```

`positionAt(index)` cho vị trí của phần tử tại chỉ số đó theo cơ chế scrolling. Vị trí có thể dùng để yêu cầu phần sau phần tử đã đánh dấu; nó không phải tổng số, số trang hay entity tiếp theo.

`window.size()` là số phần tử thực tế trong cửa sổ. Nó không thay thế cấu hình kích thước yêu cầu cho truy vấn tiếp theo.

### 6.2. Chữ ký scrolling minh họa trong Spring Data JPA

Với bộ phiên bản và hình dạng truy vấn có hỗ trợ:

```java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;

Window<PurchaseOrder> findFirst3ByTenantIdAndStatusOrderByCreatedAtAscIdAsc(
        String tenantId,
        OrderStatus status,
        ScrollPosition position);
```

`First3` đặt kích thước giới hạn của cửa sổ theo cơ chế derived query. `ScrollPosition` là tham số đặc biệt để xác định chỗ tiếp tục, không phải một đối số cho điều kiện lọc.

Kiểu `ScrollPosition` là abstraction chung; module có thể chỉ hỗ trợ một số loại vị trí hoặc có giới hạn theo loại truy vấn. Không đổi chữ ký thành `Window` ở bất kỳ repository nào rồi mặc định nó sẽ hoạt động.

### 6.3. Vòng lặp tiếp tục từ vị trí cuối

Ví dụ duyệt keyset trên module đã xác nhận hỗ trợ:

```java
ScrollPosition position = ScrollPosition.keyset();

while (true) {
    Window<PurchaseOrder> window = repository
            .findFirst3ByTenantIdAndStatusOrderByCreatedAtAscIdAsc(
                    tenantId,
                    OrderStatus.PAID,
                    position);

    if (window.isEmpty()) {
        break;
    }

    for (PurchaseOrder purchaseOrder : window) {
        process(purchaseOrder);
    }

    if (!window.hasNext()) {
        break;
    }

    position = window.positionAt(window.size() - 1);
}
```

Cần kiểm tra rỗng trước khi lấy `size() - 1`. Một cửa sổ cuối có thể chứa ít hơn ba phần tử; số phần tử nhỏ hơn giới hạn không phải lỗi.

Vị trí cuối của cửa sổ đang được dùng như một mốc đã xử lý. Lần truy vấn sau tiếp tục theo cơ chế loại trừ mốc đó, thay vì yêu cầu xử lý lại chính phần tử cuối.

Không tự tạo lại vị trí ban đầu trong mỗi vòng lặp: điều đó có thể khiến ứng dụng đọc lặp lại phần đầu mãi mãi.

## 7. Window không đồng nghĩa với keyset trong mọi trường hợp

### 7.1. Offset scrolling

Offset scrolling tiếp tục theo vị trí dạng offset. Nó vẫn có thể gặp chi phí truy cập sâu hoặc dịch chuyển vị trí khi dữ liệu thay đổi, giống các vấn đề của phân trang offset.

Nếu module hỗ trợ, vị trí ban đầu được biểu đạt bằng:

```java
ScrollPosition initial = ScrollPosition.offset();
```

Cần phân biệt vị trí ban đầu với một vị trí cụ thể:

| Giá trị | Cách hiểu |
| --- | --- |
| `PageRequest.of(0, 3)` | Yêu cầu trang đầu, chỉ số trang bằng `0` |
| `ScrollPosition.offset()` | Vị trí scrolling ban đầu, chưa đi qua phần tử nào |
| `ScrollPosition.offset(0)` | Một vị trí offset cụ thể đã đánh dấu phần tử ở offset `0`; tiếp tục sau mốc đó |
| `window.positionAt(window.size() - 1)` | Vị trí của phần tử cuối trong cửa sổ hiện tại |

Do cơ chế tiếp tục loại trừ mốc đã có, không thay vị trí ban đầu bằng `offset(0)` theo suy luận “trang đầu cũng bắt đầu từ 0”. Hai abstraction dùng các quy ước khác nhau.

### 7.2. Keyset scrolling

Keyset scrolling tiếp tục dựa trên các giá trị khóa sắp xếp của mốc đã đọc, thay vì chỉ yêu cầu bỏ qua N kết quả.

Với sort:

```text
createdAt ASC, id ASC
```

và mốc cuối là `(lastCreatedAt, lastId)`, điều kiện tiếp tục có thể được hình dung như:

```sql
createdAt > :lastCreatedAt
or (createdAt = :lastCreatedAt and id > :lastId)
```

Điều kiện tenant và trạng thái vẫn phải được giữ ở bên ngoài nhóm điều kiện tiếp tục. Đây là mô hình logic để hiểu keyset, không phải câu lệnh phải chép nguyên vào mọi store. Module hỗ trợ có trách nhiệm chuyển vị trí thành truy vấn tương ứng.

Nếu đổi sang thứ tự giảm dần, dấu so sánh và cách tiếp tục cũng phải tương ứng. Không tái sử dụng một vị trí cũ với một bộ sort khác rồi kỳ vọng vẫn duyệt đúng.

### 7.3. Điều kiện cần cho keyset dễ hiểu và hiệu quả

- Bộ khóa sắp xếp cần tạo thứ tự đầy đủ; định danh duy nhất thường là khóa cuối hữu ích.
- Các giá trị khóa phải có sẵn để trích xuất vị trí. Với JPA keyset, những thuộc tính sắp xếp cần thỏa yêu cầu non-null của cơ chế đó.
- Nếu dùng projection trực tiếp, kết quả phải cung cấp những thuộc tính cần cho việc trích xuất keyset theo module.
- Bộ lọc và sort phải nhất quán khi tiếp tục cùng một lượt duyệt.
- Truy vấn và chỉ mục phải phù hợp để tận dụng điều kiện seek; keyset không tự bảo đảm mọi truy vấn đều nhanh.

Một cursor chỉ chứa `id` không đủ để đại diện cho sort `(createdAt, id)` nếu cơ chế cần cả hai giá trị và không có cách hợp lệ để khôi phục chúng.

## 8. So sánh trên cùng một tập dữ liệu

Giả sử truy vấn chọn đúng một tenant và trạng thái `PAID`, với các id theo thứ tự `createdAt ASC, id ASC`:

```text
101, 102, 103, 104, 105, 106, 107
```

Kích thước mỗi lần lấy là `3`, dữ liệu không đổi trong suốt ví dụ.

| Hợp đồng | Lần đầu | Metadata tiêu biểu | Cách đi tiếp |
| --- | --- | --- | --- |
| `Page` | `101, 102, 103` | Tổng `7`, tổng trang `3`, còn trang sau | Yêu cầu trang `1` |
| `Slice` | `101, 102, 103` | Còn lát sau, không yêu cầu tổng `7` | Dùng `nextPageable()` khi `hasNext()` |
| `Window` | `101, 102, 103` | Còn cửa sổ sau và vị trí tại `103` | Truyền vị trí cuối vào truy vấn scrolling |

Lần thứ hai có `104, 105, 106`; lần cuối có `107` và không còn phần tiếp theo.

Sự giống nhau của nội dung không làm ba hợp đồng trở thành tương đương. `Page` thêm tổng số, `Slice` quản lý tiếp tục theo pageable, còn `Window` sử dụng vị trí scrolling có thể là offset hoặc keyset.

Nếu tổng chỉ có đúng ba phần tử, lần đầu vẫn đủ ba phần tử nhưng không còn phần sau. Đây là trường hợp cần có trong dữ liệu kiểm tra để tránh cách tự tính `hasNext` bằng phép so sánh kích thước đơn giản.

## 9. Đánh giá khả năng theo store, module và hình dạng truy vấn

Câu hỏi “Spring Data có kiểu Window không?” chưa đủ để quyết định một method hợp lệ. Cần xét nhiều tầng:

```text
Commons có abstraction
        |
        v
Module có hỗ trợ kiểu kết quả và tham số này
        |
        v
Loại truy vấn cụ thể có hỗ trợ cơ chế đó
        |
        v
Provider / driver / store đáp ứng điều kiện thực thi
        |
        v
Mapping và dữ liệu thỏa hợp đồng
```

| Bối cảnh | Điều cần xác nhận |
| --- | --- |
| Repository JPA với derived query | Khả năng trả `Page`/`Slice`, scrolling theo bộ phiên bản, kiểu vị trí, mapping và sort |
| JPA với JPQL/SQL khai báo, named query hoặc procedure | Không suy từ hỗ trợ derived scrolling sang hỗ trợ mọi nguồn truy vấn; kiểm tra riêng paging, count, sort và scrolling |
| Repository tài liệu như MongoDB | Kiểu kết quả/phương thức được module hỗ trợ, semantics sort, count và scrolling của hình dạng truy vấn đang dùng |
| JDBC và R2DBC | Phân biệt module đồng bộ với reactive; cùng dùng cơ sở dữ liệu quan hệ không làm hợp đồng kết quả giống nhau |
| Công cụ tìm kiếm hoặc dịch vụ có continuation token riêng | Token của backend có thể thuộc API riêng, không tự đồng nhất với `ScrollPosition` hoặc `Window` |
| Repository fragment tùy biến | Implementation phải thực sự tạo được metadata đúng, không chỉ trả một object mang tên kiểu mong muốn |

Một API backend có cursor không chứng minh Spring Data module đã ánh xạ nó thành `Window`. Ngược lại, trả `Window` cũng không chứng minh implementation đang dùng cursor server-side hay keyset; có thể nó đang dùng offset.

### 9.1. Không suy diễn hỗ trợ reactive từ một wrapper

Commons có `Page`, `Slice` và `Window` không đồng nghĩa mọi reactive repository chấp nhận:

```text
Mono<Page<T>>
Mono<Slice<T>>
Mono<Window<T>>
```

Cần xem module có hỗ trợ chữ ký cụ thể không. Một module có thể hỗ trợ publisher của entity cùng yêu cầu giới hạn/phân trang nhưng không tự cung cấp tổng số qua cùng một kiểu wrapper.

Nếu thiết kế ứng dụng cần dữ liệu và tổng trong luồng reactive, có thể cần phối hợp các truy vấn riêng theo khả năng module. Khi đó vẫn phải xác định chi phí và mức nhất quán, không chỉ bọc kết quả vào một DTO có trường `total`.

### 9.2. Tránh tuyên bố tuyệt đối theo tên store

Ngay trong một module, hỗ trợ có thể khác nhau giữa derived query, truy vấn chuỗi, native query, projection hoặc procedure. Do đó bảng quyết định của một dự án nên ghi rõ bộ phiên bản và loại truy vấn đã xác nhận, thay vì chỉ ghi “JPA hỗ trợ” hoặc “MongoDB không hỗ trợ” cho toàn bộ mọi trường hợp.

## 10. Projection, chuyển đổi kết quả và thông tin tiếp tục

`Page`, `Slice` và `Window` có thể chứa entity hoặc một kiểu projection được module hỗ trợ. Ví dụ, caller chỉ cần id và tổng tiền thì không nhất thiết phải công bố toàn bộ entity.

Tuy nhiên, projection trực tiếp cho keyset cần giữ các khóa mà cơ chế scrolling dùng để tạo vị trí. Nếu sort theo `createdAt` và `id` nhưng kết quả chỉ có `total`, module có thể không trích xuất được keyset hợp lệ.

Cần phân biệt hai tình huống:

1. **Truy vấn trực tiếp ra projection thiếu khóa:** có thể làm mất thông tin cần cho scrolling ngay ở tầng truy vấn.
2. **Đã nhận Window hợp lệ rồi map nội dung sang DTO:** thao tác `map` của container được thiết kế để chuyển nội dung trong khi giữ hợp đồng metadata/vị trí liên quan.

Tương tự, dùng `page.map(...)` hoặc `slice.map(...)` giúp giữ metadata khi chuyển nội dung. Nếu chỉ lấy `getContent()`, map sang một `List` rồi tự dựng container mới, ứng dụng phải chịu trách nhiệm không làm sai tổng, thông tin tiếp tục hoặc vị trí.

Auditing cũng là một vấn đề riêng: trường `createdAt` được hạ tầng auditing ghi nhận có thể dùng làm khóa sort, nhưng auditing không tự bảo đảm tính duy nhất, snapshot hoặc một cursor vẫn hợp lệ khi dữ liệu thay đổi.

## 11. Nhất quán dữ liệu và chi phí khi duyệt nhiều phần

### 11.1. Offset có thể bị dịch chuyển

Caller đọc phần đầu rồi một hàng mới được chèn phía trước thứ tự hiện tại. Lần lấy phần sau theo offset có thể bị dịch chuyển và trả lại một hàng đã thấy hoặc bỏ qua một hàng so với một lượt duyệt trên snapshot ban đầu.

Thêm khóa phụ duy nhất giải quyết trường hợp bằng nhau trong sort; nó không ngăn sự dịch chuyển do insert/delete giữa hai lần truy vấn.

### 11.2. Keyset cũng không phải snapshot tự động

Keyset tiếp tục theo bộ giá trị khóa, nên tránh phụ thuộc trực tiếp vào số hàng đã bị bỏ qua. Nhưng nếu một entity đổi giá trị khóa sắp xếp hoặc đổi trạng thái lọc trong lúc duyệt, nó có thể di chuyển qua mốc tiếp tục.

Cần phân biệt mục tiêu:

- Feed hiển thị dữ liệu đang thay đổi có thể chấp nhận một mức dịch chuyển nhất định.
- Export cần tập kết quả nhất quán có thể đòi hỏi snapshot, mốc chốt hoặc cơ chế transaction phù hợp với store.
- Tác vụ xử lý có thể phải lưu checkpoint và có tính idempotent khi chạy lại sau lỗi.

`Window` chỉ cung cấp hợp đồng phần kết quả và vị trí; nó không tự triển khai đầy đủ các cơ chế đó.

### 11.3. Không duy trì mọi entity trong bộ nhớ chỉ vì đã chia cửa sổ

Đọc từng cửa sổ giúp giới hạn nội dung trả về mỗi lần. Nhưng nếu ứng dụng gom tất cả vào một danh sách, hoặc giữ một persistence context JPA quá lâu với nhiều entity được quản lý, bộ nhớ vẫn có thể tăng đáng kể.

Việc tổ chức transaction theo phần, quản lý tài nguyên và checkpoint cần được thiết kế theo tác vụ. Không nên thay đổi ranh giới transaction chỉ để giảm bộ nhớ mà bỏ qua yêu cầu nhất quán của nghiệp vụ.

### 11.4. Count, offset và seek là các loại chi phí khác nhau

| Cơ chế | Chi phí cần quan sát |
| --- | --- |
| Tổng số của `Page` | Phép đếm có thể quét nhiều dữ liệu hoặc xử lý join/grouping |
| Truy cập offset sâu | Store có thể phải đi qua/bỏ qua nhiều kết quả trước vị trí cần lấy |
| Keyset | Cần điều kiện seek, thứ tự đầy đủ và chỉ mục phù hợp |
| Bất kỳ nội dung entity nào | Mapping, tải quan hệ và số dòng trung gian vẫn có thể đáng kể |

Không chọn `Window` chỉ theo một khẩu hiệu “luôn nhanh nhất”. Hợp đồng đáp ứng caller và cách store thực thi mới quyết định lựa chọn phù hợp.

## 12. Thiết kế hợp đồng ứng dụng phía trên repository

Nếu trả kết quả qua API, nên biểu đạt thông tin thực sự có sẵn:

| Hợp đồng ứng dụng | Thông tin phù hợp |
| --- | --- |
| Bảng theo số trang | Nội dung, chỉ số trang, kích thước, tổng số và tổng trang nếu chọn `Page` |
| Danh sách xem tiếp | Nội dung và `hasNext`, không bịa tổng số |
| Luồng dựa trên cursor | Nội dung, `hasNext` và token tiếp tục được ứng dụng định nghĩa |

Không lấy số phần tử của một `Slice` rồi gọi nó là `totalElements`. Không lấy một offset trong `Window` rồi mặc định nó là số trang.

`ScrollPosition` là abstraction nội bộ cho scrolling; nó không tự định nghĩa một định dạng cursor công khai ổn định qua các phiên bản ứng dụng. Nếu cần cursor ở API, cần thiết kế cách biểu diễn và kiểm tra nó cùng phạm vi truy vấn, bộ lọc và sort.

Không tái sử dụng token của một lượt duyệt cho tenant, trạng thái hoặc thứ tự khác. Khi thay đổi các điều kiện đó, caller nên bắt đầu một lượt duyệt mới theo hợp đồng ứng dụng.

## 13. Lỗi thường gặp và hướng kiểm tra

| Biểu hiện | Nguyên nhân có thể có | Hướng kiểm tra |
| --- | --- | --- |
| Dùng Slice nhưng vẫn cố đọc tổng số | Chọn sai hợp đồng metadata | Chuyển sang `Page` nếu tổng thật sự cần thiết |
| Trả Page nhưng tổng sai | Count query hoặc đơn vị đếm không khớp nội dung | Đối chiếu bộ lọc, join, distinct và projection |
| Có đúng N phần tử nên báo còn dữ liệu sai | Tự suy `hasNext` từ kích thước | Dùng cơ chế lấy thêm thông tin tiếp tục của module |
| Đổi sang Slice nhưng trang sâu vẫn chậm | Vẫn dùng offset | Đánh giá cách truy cập và khả năng keyset của store |
| Window lặp mãi phần đầu | Luôn truyền vị trí ban đầu | Tiếp tục từ vị trí cuối đã xử lý |
| Lỗi khi lấy vị trí cuối | Window rỗng nhưng vẫn gọi `positionAt(-1)` | Kiểm tra rỗng trước khi lấy vị trí |
| Bỏ mất phần tử đầu ở offset scrolling | Nhầm initial position với offset cụ thể `0` | Dùng `ScrollPosition.offset()` cho khởi đầu phù hợp |
| Không tạo được keyset cho projection | Thiếu khóa sort hoặc dữ liệu khóa không hợp lệ | Đối chiếu projection, yêu cầu non-null và mapping |
| Chữ ký Window bị từ chối | Module, phiên bản hoặc nguồn truy vấn chưa hỗ trợ | Kiểm tra đúng tổ hợp thay vì chỉ import được class |
| Có lặp/bỏ sót khi dữ liệu thay đổi | Nhầm thứ tự xác định với snapshot | Đánh giá concurrency, khóa sort và mô hình nhất quán |

## 14. Bài tập thực hành

### Bài 1: Chọn kiểu kết quả

Chọn một điểm bắt đầu cho các yêu cầu:

1. Trang quản trị phải hiển thị tổng số đơn và số trang.
2. Danh sách trên điện thoại chỉ có nút tải tiếp, không cần tổng.
3. Tác vụ duyệt nhiều đơn theo mốc tiếp tục, module đã xác nhận hỗ trợ keyset scrolling.

**Gợi ý:** lần lượt là `Page`, `Slice`, `Window`. Sau đó cần xác nhận hình dạng truy vấn và bộ phiên bản phù hợp; tên abstraction chưa đủ để bảo đảm chữ ký hợp lệ.

### Bài 2: Phân biệt kích thước và phần tiếp theo

Một lát yêu cầu ba phần tử. Xét hai bộ dữ liệu có tổng lần lượt là ba và bốn entity phù hợp.

**Phân tích:** cả hai lần lấy đầu đều có thể trả ba phần tử, nhưng `hasNext` phải khác nhau. Đây là lý do `content.size() == 3` không đủ để tính tiếp tục.

Nếu dùng `Page`, metadata tổng kỳ vọng là ba và bốn trên bộ dữ liệu ổn định. Nếu dùng `Slice`, không yêu cầu cung cấp hai con số tổng đó.

### Bài 3: Xác định khóa cần cho keyset

Truy vấn sort theo `createdAt ASC, id ASC`, nhưng projection chỉ công bố `total`.

**Phân tích:** projection không cung cấp các giá trị cần để trích xuất vị trí theo bộ khóa. Cần điều chỉnh projection hoặc cách truy vấn theo yêu cầu của module. Chỉ đổi `Slice` thành `Window` không tự bổ sung đầy đủ dữ liệu keyset.

### Bài 4: Lập các trường hợp kiểm tra có ý nghĩa

Khi tích hợp repository vào ứng dụng, chuẩn bị các trường hợp:

- Không có entity phù hợp: container rỗng và không cố lấy vị trí ở chỉ số âm.
- Có đúng kích thước yêu cầu: không báo phần tiếp theo nếu thật sự hết dữ liệu.
- Có nhiều hơn một phần: lấy tiếp đúng các entity chưa xử lý trên dữ liệu không đổi.
- Nhiều entity trùng `createdAt`: thứ tự vẫn được phân định bằng `id`.
- Có entity sai tenant hoặc trạng thái: chúng không lọt vào nội dung hoặc phép đếm.
- Projection trực tiếp: có đủ khóa nếu dùng keyset.
- Query khai báo phức tạp: tổng của `Page` được kiểm tra cùng bộ lọc với nội dung.

Nếu yêu cầu tác vụ có tính nhất quán khi dữ liệu thay đổi, cần thêm kịch bản đồng thời phù hợp với yêu cầu đó. Không lấy kết quả của một bộ dữ liệu tĩnh làm bằng chứng rằng mọi cách duyệt đều tạo snapshot.

## 15. Các điểm cần nhớ

- `Page` cung cấp tổng số, `Slice` cung cấp thông tin tiếp tục theo trang, còn `Window` cung cấp vị trí scrolling; chúng không thay thế nhau chỉ bằng cách đổi kiểu trả về.
- Tránh tổng số không tự loại bỏ offset; dùng `Window` cũng không tự bảo đảm keyset.
- Vị trí scrolling ban đầu, offset cụ thể và chỉ số trang là những khái niệm khác nhau.
- Keyset cần thứ tự đầy đủ, giá trị khóa phù hợp và khả năng trích xuất khóa từ kết quả theo yêu cầu module.
- Commons cung cấp abstraction; module, phiên bản, loại truy vấn và mapping quyết định chữ ký thực tế có được hỗ trợ hay không.
- Mỗi lựa chọn cần được đánh giá cùng projection, chi phí truy vấn, transaction, nhất quán dữ liệu và hợp đồng ứng dụng.
