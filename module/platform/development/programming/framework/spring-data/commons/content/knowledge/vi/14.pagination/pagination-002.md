# page size, offset và thứ tự sắp xếp

Một yêu cầu phân trang cần làm rõ ba việc: mỗi lần lấy tối đa bao nhiêu kết quả, bắt đầu từ vị trí nào và vị trí đó được tính theo thứ tự nào. Nếu chỉ truyền một số trang mà không thống nhất page size và sort, cùng một con số có thể trỏ đến những tập dữ liệu khác nhau.

Trong chương **Phân trang** của **SPRING_DATA_COMMONS**, bài này giải thích quan hệ giữa page size, page index, offset và thứ tự sắp xếp. Các ví dụ dùng `PageRequest`, `Pageable` và `Sort` của Commons; những chi tiết thực thi bằng JPA, driver hoặc store được phân biệt rõ để không coi phân trang là một phép cắt danh sách đã tải sẵn trong Java.

## 1. Bốn khái niệm cần tách riêng

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Page index | Chỉ số trang theo quy ước của API | `0` là trang đầu trong `PageRequest` |
| Page size | Số phần tử tối đa yêu cầu cho một trang | `4` |
| Offset | Số vị trí cần bỏ qua trước phần kết quả muốn lấy | Trang index `2`, size `4` có offset `8` |
| Sort | Thứ tự xác định các vị trí trong tập kết quả | `createdAt DESC, id DESC` |

Page size không phải tổng số kết quả. Offset không phải id của entity. Page index không phải offset.

Ví dụ id của entity có thể là `1001`, `1007`, `2090`; offset `2` vẫn chỉ có nghĩa bỏ qua hai kết quả đầu trong thứ tự đang xét, không có nghĩa bắt đầu ở entity có id bằng `2`.

### Mô hình logic

```text
Tất cả dữ liệu có thể truy vấn
             |
             v
Lọc đúng predicate và phạm vi nghiệp vụ
             |
             v
Sắp xếp toàn bộ tập phù hợp theo bộ khóa đã chọn
             |
             v
Bỏ qua offset vị trí
             |
             v
Lấy tối đa page size phần tử cho nội dung trang
```

Đây là thứ tự ngữ nghĩa. Store có thể dùng chỉ mục, tối ưu kế hoạch hoặc cơ chế thực thi khác, không nhất thiết materialize toàn bộ tập trung gian như sơ đồ.

## 2. Công thức offset trong PageRequest

`PageRequest` sử dụng chỉ số trang bắt đầu từ `0`:

```text
offset = pageIndex × pageSize
```

Ví dụ page size bằng `4`:

| Page index | Trang hiển thị nếu giao diện bắt đầu từ 1 | Offset |
| --- | --- | --- |
| `0` | `1` | `0` |
| `1` | `2` | `4` |
| `2` | `3` | `8` |
| `3` | `4` | `12` |

Offset chỉ có ý nghĩa đầy đủ khi đi cùng bộ lọc và sort. “Bỏ qua tám đơn hàng” chưa xác định tám đơn nào nếu chưa biết thứ tự và phạm vi tenant/trạng thái.

### PageRequest không nhận offset làm đối số đầu

```java
PageRequest.of(2, 4);
```

Đoạn này tạo yêu cầu trang index `2`, size `4`, tương ứng offset `8`. Nó không tạo yêu cầu bắt đầu ở offset `2`.

Một lỗi thường gặp là API nhận `offset = 20`, `size = 10` nhưng gọi:

```java
PageRequest.of(20, 10);
```

Kết quả là offset `200`, không phải `20`.

### Offset trong Commons có kiểu long

`Pageable.getOffset()` trả `long`. Điều này giúp biểu đạt tích page index và page size mà không phải giữ kết quả trong một `int`.

Nếu tự tính, cần tránh nhân hai `int` trước rồi mới gán sang long:

```java
long wrong = pageIndex * pageSize;
long offset = (long) pageIndex * pageSize;
```

Dòng thứ nhất có thể tràn ở phép nhân int trước khi gán. Khi đã có `Pageable`, thường nên đọc trực tiếp `getOffset()` thay vì tính lại ở nhiều nơi.

Kiểu long ở abstraction không có nghĩa mọi provider hoặc driver đều chấp nhận offset lớn tùy ý. Ví dụ API phân trang JPA truyền thống có giới hạn kiểu số riêng ở mức thực thi. Giá trị hợp lệ ở `PageRequest` vẫn có thể vượt khả năng của một backend hoặc không phù hợp với hiệu năng thực tế.

## 3. Đọc một tập kết quả cụ thể

Giả sử sau khi lọc đúng tenant và trạng thái, thứ tự đã được xác định là:

```text
61, 60, 59, 58, 57, 56, 55, 54, 53, 52, 51
```

Đây là các id trong thứ tự truy vấn, không phải một quy tắc rằng mọi id phải liên tiếp. Tập kết quả có `11` entity, page size bằng `4`.

| Page index | Offset | Nội dung id | Số phần tử thực tế |
| --- | --- | --- | --- |
| `0` | `0` | `61, 60, 59, 58` | `4` |
| `1` | `4` | `57, 56, 55, 54` | `4` |
| `2` | `8` | `53, 52, 51` | `3` |
| `3` | `12` | Rỗng | `0` |

Có thể hình dung bằng khoảng chỉ số, với điểm cuối loại trừ:

```text
Trang 0: [0, 4)
Trang 1: [4, 8)
Trang 2: [8, 12), nhưng dữ liệu chỉ còn đến vị trí 10
```

Framework không tạo thêm một entity để trang cuối đủ bốn phần tử. Page size là kích thước yêu cầu, còn số phần tử thực tế phụ thuộc dữ liệu còn lại.

Một yêu cầu trang vượt cuối thường có thể cho nội dung rỗng theo cách query của module, chứ `PageRequest` không tự biết tổng số để từ chối hoặc tự chuyển về trang cuối. Chính sách ứng dụng có thể quy định cách biểu đạt trường hợp ngoài phạm vi này, nhưng cần tách nó khỏi việc tạo một yêu cầu trang hợp lệ về cấu trúc.

## 4. Tạo Pageable cùng một thứ tự rõ ràng

Giả sử domain `PurchaseOrder` có những thuộc tính Java:

| Thuộc tính | Kiểu | Vai trò |
| --- | --- | --- |
| `id` | `Long` | Định danh duy nhất |
| `tenantId` | `String` | Phạm vi tổ chức |
| `status` | `OrderStatus` | Trạng thái nghiệp vụ |
| `createdAt` | `Instant` | Thời điểm tạo, giả định không null |
| `total` | `BigDecimal` | Tổng tiền |

```java
public enum OrderStatus {
    NEW, PAID, CANCELLED
}
```

Ví dụ **Spring Data JPA**, entity và hạ tầng đã được ánh xạ/cấu hình phù hợp:

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

Caller:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

Sort order = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id"));

PageRequest request = PageRequest.of(0, 4, order);

Page<PurchaseOrder> page = repository.findByTenantIdAndStatus(
        "tenant-a", OrderStatus.PAID, request);
```

Những giá trị đầu vào có thể kiểm tra trực tiếp:

```java
request.getPageNumber(); // 0
request.getPageSize();   // 4
request.getOffset();     // 0L
request.getSort();       // createdAt DESC, rồi id DESC
```

Tên thuộc tính trong `Sort` là tên Java theo mapping của truy vấn entity, không tự đổi sang tên cột SQL như `created_at`.

`Pageable` đã có sort. Không thiết kế chữ ký cùng lúc nhận `Pageable` và một `Sort` riêng để cùng điều khiển truy vấn theo các cơ chế repository chuẩn tương ứng.

## 5. Vì sao sort là một phần bắt buộc của ý nghĩa trang?

### 5.1. Không có sort thì vị trí chưa có hợp đồng nghiệp vụ

```java
PageRequest.of(0, 4);
```

Yêu cầu này không tự có nghĩa “bốn đơn mới nhất”. Không được mặc định thứ tự mặc nhiên của store là thứ tự insert, id hoặc thời gian tạo.

Nếu caller cần một danh sách có thể duyệt nhất quán trên dữ liệu không đổi, cần bộ khóa được xác định rõ.

### 5.2. Một khóa có thể chưa đủ

Sort `createdAt DESC` vẫn để ngỏ thứ tự giữa các đơn cùng thời điểm. Thêm một khóa duy nhất như `id DESC` giúp phân định nhóm đó:

```text
createdAt DESC, id DESC
```

Khóa thời gian quyết định ưu tiên chính; id chỉ phân định khi thời gian bằng nhau. Đổi thành `id DESC, createdAt DESC` là một yêu cầu khác.

Việc ghép nhiều khóa không tự sửa null ordering, collation hoặc hạn chế của module. Ví dụ chính giả định các khóa đã có giá trị hợp lệ và được store sắp xếp đúng theo mapping.

### 5.3. Phải sort trước khi cắt trang về mặt ngữ nghĩa

Giả sử dữ liệu chưa sort có giá trị tiền:

```text
A:90, B:10, C:80, D:20, E:70, F:30
```

Cắt ba phần tử đầu rồi sort trong Java cho:

```text
B:10, C:80, A:90
```

Nhưng trang đầu của toàn bộ dữ liệu sort theo tổng tiền tăng dần phải là:

```text
B:10, D:20, F:30
```

Hai kết quả khác nhau vì một cách chỉ sắp phần đã cắt, còn cách kia chọn trang từ tập đã được xếp đúng toàn cục.

Do đó không lấy một trang không sort từ store rồi sort nội dung trang để tuyên bố đã phân trang theo tiêu chí đó. Yêu cầu sort cần được chuyển vào cơ chế truy vấn phù hợp của module.

## 6. Metadata yêu cầu khác với metadata kết quả

Với `Page`:

```java
page.getSize();             // Kích thước trang theo yêu cầu
page.getNumberOfElements();// Số phần tử nội dung thực tế
page.getNumber();           // Chỉ số trang
page.getTotalElements();    // Tổng số kết quả theo metadata
page.getTotalPages();       // Tổng số trang theo metadata
page.hasNext();            // Có trang sau theo hợp đồng Page
```

Trong ví dụ tổng `11`, size `4`, trang index `2`:

```text
getSize()             = 4
getNumberOfElements() = 3
getNumber()           = 2
getTotalElements()    = 11
getTotalPages()       = 3
hasNext()            = false
```

Các con số trên giả định dữ liệu ổn định và phép đếm có cùng predicate với truy vấn nội dung.

### Page size không tự quyết định cần count hay không

Kiểu trả về còn quyết định metadata:

| Hợp đồng | Nội dung từng phần | Tổng số | Cách biết còn phần tiếp |
| --- | --- | --- | --- |
| `Page<T>` | Có | Có metadata tổng | Theo hợp đồng trang và tổng |
| `Slice<T>` | Có | Không yêu cầu tổng như Page | Thường lấy thêm thông tin, chẳng hạn một phần tử dư |
| `List<T>` với Pageable nếu module hỗ trợ | Có | Không tự có | Không có metadata tiếp tục chỉ từ kiểu List |

Với `Slice`, page size yêu cầu `4` không có nghĩa store chỉ được đọc đúng bốn hàng: implementation có thể đọc thêm để xác định `hasNext`, rồi chỉ trả bốn phần tử nội dung.

Với `Page`, framework có thể cần một truy vấn đếm riêng hoặc suy ra tổng ở một số trường hợp. Không khẳng định mọi yêu cầu trang luôn thực hiện đúng hai truy vấn.

## 7. Quy ước trang từ giao diện phải được chuyển đổi một lần

Giao diện thường hiển thị trang `1`, còn `PageRequest` dùng index `0`. Nếu API của ứng dụng được thiết kế nhận số trang từ `1`, có thể chuyển ở một ranh giới rõ ràng:

```text
pageIndex = pageNumberFromOne - 1
```

Ví dụ helper Java:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

static Pageable fromOneBasedPage(int pageNumberFromOne, int size) {
    if (pageNumberFromOne < 1) {
        throw new IllegalArgumentException("page must start at 1");
    }
    if (size < 1 || size > 100) {
        throw new IllegalArgumentException("size must be between 1 and 100");
    }

    Sort order = Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.desc("id"));

    return PageRequest.of(pageNumberFromOne - 1, size, order);
}
```

Giới hạn `100` là chính sách minh họa của ứng dụng, không phải giới hạn cố định của Commons.

Cần thống nhất API nhận chỉ số từ `0` hay số trang từ `1`. Nếu một web argument resolver đã được cấu hình để chuyển đổi trước khi cung cấp `Pageable`, tầng service không được tiếp tục trừ một lần nữa.

Không âm thầm đổi mọi số trang không hợp lệ về trang đầu nếu hợp đồng API yêu cầu báo lỗi. Cách xử lý đầu vào là một quyết định công khai của ứng dụng, không nên phụ thuộc ngẫu nhiên vào nơi tạo `PageRequest`.

### Điều kiện cấu trúc của PageRequest

- Page index phải không âm.
- Page size phải lớn hơn không.
- Khi cung cấp `Sort`, dùng một giá trị hợp lệ như `Sort.unsorted()` thay vì null nếu muốn không có sort.

Size bằng `0` không có nghĩa “lấy tất cả”. Nếu một thao tác thật sự được phép không phân trang, Commons có `Pageable.unpaged()` cho hợp đồng đó. Không thay việc không phân trang bằng một số size cực lớn rồi coi hai cách là tương đương.

Khi xử lý `Pageable` có thể unpaged, kiểm tra `isPaged()` hoặc `isUnpaged()` trước khi giả định các getter như offset/page size có cùng ý nghĩa truy cập như một yêu cầu đã phân trang.

## 8. Không phải mọi offset đều biểu diễn chính xác bằng PageRequest

Giả sử API nhận:

```text
offset = 25
size   = 10
```

Nếu tính:

```text
pageIndex = offset / size = 2
```

rồi dùng `PageRequest.of(2, 10)`, offset thực tế là `20`. Năm vị trí đã bị thay đổi so với yêu cầu ban đầu.

Để chuyển chính xác một offset sang PageRequest có cùng size, cần:

```text
offset không âm
size dương
offset chia hết cho size
pageIndex thu được nằm trong phạm vi kiểu/khả năng được hỗ trợ
```

Nếu không chia hết, không được tự làm tròn mà vẫn quảng bá như giữ nguyên offset. Có thể:

- Thiết kế API nhận page index và page size thay vì offset tùy ý.
- Dùng một cơ chế offset/limit mà module hoặc implementation tùy biến thực sự hỗ trợ.
- Thiết kế cách tiếp tục theo cursor nếu phù hợp yêu cầu.

Một custom `Pageable` cũng phải tuân hợp đồng và khả năng module; không chỉ viết một getter offset rồi mặc định mọi navigation và metadata đều đúng.

## 9. Thay đổi page size hoặc sort làm thay đổi vị trí đang xem

### 9.1. Giữ page index không giữ offset

Với page index `2`:

| Page size | Offset |
| --- | --- |
| `4` | `8` |
| `6` | `12` |
| `10` | `20` |

Đổi size từ `4` sang `6` nhưng giữ index `2` làm điểm bắt đầu chuyển từ vị trí `8` sang vị trí `12`. Đó không phải cùng một cửa sổ dữ liệu.

Một chính sách giao diện dễ hiểu là trở về trang đầu khi đổi size. Nếu sản phẩm muốn giữ một entity neo tại vị trí đang xem, cần thiết kế hành vi neo rõ ràng; phép chia offset mới không phải lúc nào cũng biểu diễn chính xác entity đó trên ranh giới trang.

### 9.2. Giữ index khi đổi sort cũng không giữ cùng nội dung

Trang `2` theo `createdAt DESC` khác trang `2` theo `total DESC`. Page index không phải một định danh độc lập với sort.

Tương tự, đổi tenant, trạng thái hoặc các bộ lọc khác làm tập kết quả thay đổi. Ứng dụng cần quyết định reset về trang đầu hoặc xử lý vị trí hiện tại theo chính sách cụ thể.

### 9.3. Điều hướng nên giữ nguyên yêu cầu liên quan

Với `PageRequest`, có thể dùng navigation thay vì dựng lại thiếu thông tin:

```java
Pageable next = request.next();
Pageable first = request.first();
Pageable previous = request.previousOrFirst();
```

Các thao tác này điều chỉnh vị trí theo hợp đồng của request và giữ kích thước/sort tương ứng. Chúng không gọi store và không xác nhận trang đích có dữ liệu.

Nếu đang có `Page` hoặc `Slice`, dùng `hasNext()` trước khi tiếp tục theo metadata của kết quả khi đó là nhu cầu của caller. Không coi việc tạo được một `Pageable` tiếp theo là bằng chứng còn kết quả.

## 10. Dữ liệu thay đổi giữa hai lần đọc

Giả sử thứ tự cố định là:

```text
61, 60, 59, 58, 57, 56, 55, 54, 53, 52, 51
```

Caller đọc trang đầu size `4`: `61, 60, 59, 58`.

Một đơn mới `62` được thêm và đứng trước chúng:

```text
62, 61, 60, 59, 58, 57, 56, 55, 54, 53, 52, 51
```

Trang index `1` bỏ qua bốn vị trí và trả `58, 57, 56, 55`. Entity `58` đã xuất hiện ở trang trước.

Điều này có thể xảy ra dù sort đã có khóa phụ duy nhất. Bộ khóa đầy đủ giải quyết sự mơ hồ giữa các giá trị bằng nhau, nhưng không tạo một snapshot xuyên nhiều truy vấn.

Cần phân biệt:

| Yêu cầu | Cơ chế cần đánh giá |
| --- | --- |
| Thứ tự xác định trên cùng dữ liệu | Sort đầy đủ, thường có khóa cuối duy nhất |
| Tiếp tục từ một mốc thay vì số vị trí bỏ qua | Seek/keyset/scrolling theo khả năng module |
| Nhìn cùng một phiên bản dữ liệu khi duyệt | Transaction, snapshot hoặc mốc chốt phù hợp store |

Đối với màn hình tương tác, một mức thay đổi giữa các trang có thể là đặc tính được chấp nhận. Đối với export hoặc tác vụ xử lý không được bỏ sót, cần thiết kế mức nhất quán và cơ chế tiếp tục phù hợp, thay vì chỉ tăng page size.

Metadata tổng của `Page` cũng không tự bảo đảm nội dung và count được đọc từ một snapshot chung; điều đó phụ thuộc cách thực thi và ranh giới transaction.

## 11. Chi phí page size và offset thuộc những chiều khác nhau

### 11.1. Page size lớn làm tăng lượng dữ liệu mỗi lần

Tăng size có thể giảm số lần gọi nhưng làm tăng:

- Số entity hoặc projection cần ánh xạ.
- Dữ liệu truyền giữa store, ứng dụng và caller.
- Bộ nhớ cần giữ cho nội dung hiện tại.
- Công việc tải quan hệ tùy mapping.

Không có một page size tốt nhất cho mọi ứng dụng. Cần chọn theo nhu cầu sử dụng và đo trên hình dạng dữ liệu thực tế. Một màn hình chỉ hiển thị vài chục dòng thường không cần một nội dung trang khổng lồ chỉ vì backend cho phép tạo request đó.

### 11.2. Offset sâu có thể đắt dù size nhỏ

```text
pageIndex = 100000
pageSize  = 20
offset    = 2000000
```

Yêu cầu chỉ trả tối đa hai mươi phần tử nhưng có thể khiến store phải đi qua hoặc bỏ qua nhiều kết quả trước vị trí mong muốn. Chi phí cụ thể phụ thuộc execution plan, chỉ mục và backend; không có cam kết chung rằng nó luôn tỉ lệ tuyến tính hoặc luôn được tối ưu rẻ.

Đổi `Page` thành `Slice` có thể tránh nhu cầu đếm tổng nhưng không tự loại bỏ offset sâu. Nếu cách truy cập vẫn dựa trên offset, bài toán tìm vị trí vẫn còn.

### 11.3. Sort và chỉ mục cần được xem cùng predicate

Một truy vấn lọc tenant/trạng thái rồi sort thời gian/id cần được đánh giá theo toàn bộ hình dạng đó. Chỉ mục không phù hợp có thể khiến store sort một tập lớn trước khi trả trang.

Phân trang có giới hạn không có nghĩa chỉ đọc đúng số entity trong page size. Join, fetch quan hệ, grouping và count có thể làm công việc thực tế lớn hơn nhiều.

## 12. Phải xác định đơn vị được phân trang theo store và query

Commons mô tả yêu cầu và kiểu kết quả chung, nhưng module quyết định cách áp dụng chúng.

| Bối cảnh | Điều cần xác nhận |
| --- | --- |
| Derived query JPA trên entity | Predicate, sort, offset/limit và kiểu kết quả được hỗ trợ |
| JPA join hoặc fetch quan hệ một-nhiều | Số dòng trung gian, entity trùng, giới hạn và count đúng đơn vị nghiệp vụ |
| JPQL/SQL khai báo | Cơ chế áp dụng paging/sort, count query và giới hạn theo provider/phiên bản |
| Kho tài liệu hoặc công cụ tìm kiếm | Khả năng sort, giới hạn truy cập sâu và cơ chế tiếp tục của module |
| Reactive repository | Hình dạng publisher được hỗ trợ; Pageable không tự tạo metadata Page |
| Scrolling API | Phân biệt offset/keyset và quy ước vị trí tiếp tục với page index |

Ví dụ, một đơn hàng có nhiều dòng chi tiết. Nếu query trả dòng join, “size bằng 4” cần được hiểu theo đơn vị kết quả mà module/provider tạo, không tự đồng nghĩa bốn đơn hàng độc lập đúng theo mọi hình dạng fetch.

Projection có thể giảm các trường dữ liệu trả về nếu module hỗ trợ, nhưng không tự sửa bộ lọc, count hoặc đơn vị giới hạn sai. Metadata auditing cũng không tự thêm sort mặc định hay tạo snapshot.

Nếu cần keyset hoặc một cursor của backend, phải xác nhận API hỗ trợ. Không thay một offset số bằng token bất kỳ rồi coi nó là cùng hợp đồng `PageRequest`.

## 13. Các lỗi dễ gặp

| Biểu hiện | Nguyên nhân có thể có | Cách chỉnh |
| --- | --- | --- |
| Giao diện trang đầu lại lấy phần thứ hai | Trộn số trang từ 1 và index từ 0 | Chuyển đổi đúng một lần tại ranh giới đã chọn |
| API offset 20 nhưng query offset 200 | Truyền offset vào đối số page index | Đọc lại công thức và hợp đồng đầu vào |
| Offset bị lệch khi không chia hết cho size | Làm tròn phép chia để tạo PageRequest | Không quảng bá phép chuyển không chính xác |
| Trang cuối ít phần tử bị coi là lỗi | Nhầm size yêu cầu với số phần tử thực tế | Dùng `getNumberOfElements()` cho nội dung hiện tại |
| Đổi size nhưng nội dung nhảy xa | Giữ index trong khi offset đã đổi | Reset trang hoặc thiết kế hành vi neo rõ ràng |
| Các bản ghi bằng thời gian đổi chỗ | Thiếu khóa phụ | Thêm khóa đủ phân định, giữ cùng sort qua các trang |
| Từng trang đã sort nhưng toàn bộ danh sách không đúng | Sort trong Java sau khi store đã cắt trang | Đưa sort vào truy vấn trước phép cắt về mặt ngữ nghĩa |
| Có lặp dù sort đầy đủ | Dữ liệu đổi giữa các lần đọc offset | Đánh giá consistency và cơ chế tiếp tục |
| Size nhỏ nhưng trang sâu vẫn chậm | Offset lớn hoặc sort/count tốn kém | Quan sát query plan và khả năng keyset phù hợp |
| Size 0 được dùng để lấy tất cả | Nhầm yêu cầu không phân trang với size không hợp lệ | Dùng hợp đồng unpaged được cho phép một cách tường minh |

## 14. Kiểm tra tích hợp có ý nghĩa

Khi đưa một phương thức phân trang vào ứng dụng, fixture cần làm lộ các lỗi vị trí và thứ tự:

| Trường hợp | Điều cần xác nhận |
| --- | --- |
| Trang đầu index 0 | Offset bằng 0 và lấy đúng các phần tử đầu theo sort |
| Trang thứ hai | Bỏ qua đúng page size vị trí, không dùng page index như offset |
| Trang cuối thiếu phần tử | Nội dung ngắn hơn size vẫn hợp lệ |
| Không có dữ liệu phù hợp | Nội dung rỗng, metadata theo hợp đồng kết quả |
| Trang vượt cuối | Hành vi ngoài phạm vi phù hợp chính sách ứng dụng |
| Trùng giá trị khóa sort chính | Khóa phụ giữ thứ tự xác định trên dữ liệu không đổi |
| Có entity sai tenant/trạng thái | Không lọt vào nội dung hoặc count |
| Đổi page size | Offset và vị trí mới đúng chính sách đã chọn |
| Đầu vào không hợp lệ | Bị xử lý tại đúng ranh giới, không âm thầm đổi nghĩa |

Với bộ dữ liệu `11` phần tử và size `4`, nên kiểm tra cả ba trang có dữ liệu, không chỉ trang đầu. Assert thứ tự id bằng một sequence, không chỉ so tập hợp.

Nếu kiểm tra phân trang qua API, thêm trường hợp quy ước trang từ `1` và xác nhận service không chuyển đổi lần thứ hai. Nếu API nhận offset, cần một trường hợp offset không chia hết cho size để ngăn chuyển đổi làm tròn ngoài ý định.

Kịch bản dữ liệu thay đổi đồng thời cần được kiểm tra riêng theo yêu cầu nhất quán. Không dùng việc fixture tĩnh đi qua đủ trang để tuyên bố hệ thống luôn không lặp/bỏ sót dưới mọi cập nhật.

## 15. Bài tập thực hành

### Bài 1: Tính offset

Với `PageRequest.of(3, 25)`, offset là bao nhiêu? Nếu giao diện nói “trang thứ ba”, cần dùng index nào theo quy ước hiển thị từ `1`?

**Gợi ý:** request đầu có offset `75`. Trang thứ ba của giao diện tương ứng index `2`, size `25`, offset `50`.

### Bài 2: Chuyển offset tùy ý

API nhận offset `25`, size `10`. Có thể dùng `PageRequest.of(2, 10)` mà giữ nguyên nghĩa không?

**Phân tích:** không. Request đó có offset `20`. Cần đổi hợp đồng hoặc dùng cơ chế hỗ trợ offset tùy ý, thay vì làm tròn âm thầm.

### Bài 3: Đổi page size

Caller đang ở index `2`, size `4`, rồi chuyển sang size `6` nhưng giữ index.

**Phân tích:** offset đổi từ `8` sang `12`. Nếu yêu cầu là trở về đầu danh sách sau khi đổi size, cần đặt index về `0`. Nếu muốn giữ một entity neo, phải thiết kế hành vi khác rõ ràng.

### Bài 4: Sort sau khi lấy trang

Một service lấy bốn entity không sort, rồi gọi sort theo tổng tiền trong Java để hiển thị “bốn đơn có tổng thấp nhất”.

**Phân tích:** service mới chọn bốn entity rồi sắp chúng, chưa chọn bốn entity nhỏ nhất của toàn bộ tập phù hợp. Cần đưa thứ tự vào truy vấn và có khóa phụ nếu giá trị tổng tiền bằng nhau.

### Bài 5: Page size và total

Tập kết quả ổn định có `11` entity, size `4`, đang đọc index `2`.

**Gợi ý:** nội dung có ba phần tử, offset bằng `8`; với `Page` và count đúng, tổng số là `11`, tổng trang là `3`. Size yêu cầu vẫn là `4`.

## 16. Các điểm cần nhớ

- `PageRequest` dùng page index từ `0`; offset bằng page index nhân page size và không phải một entity id.
- Page size là kích thước yêu cầu, không phải tổng dữ liệu hoặc cam kết trang cuối luôn đủ phần tử.
- Predicate và sort xác định tập có thứ tự trước khi áp dụng offset/limit về mặt ngữ nghĩa.
- Bộ khóa đủ phân định giúp thứ tự rõ ràng trên dữ liệu không đổi, nhưng không tạo snapshot khi dữ liệu thay đổi.
- Đổi size, sort hoặc bộ lọc có thể thay đổi ý nghĩa của cùng một page index; quy ước API cần được chuyển đổi ở một nơi rõ ràng.
- Page, Slice, List, truy cập offset sâu và scrolling có những hợp đồng/chi phí khác nhau, cần được xét theo module và store thực tế.
