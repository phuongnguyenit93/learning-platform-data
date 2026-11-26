# Lựa chọn entity, interface projection hoặc DTO theo ca sử dụng

Trong chương **DTO và projection động** của module **SPRING_DATA_COMMONS**, kiểu kết quả repository cần xuất phát từ công việc phía gọi sẽ thực hiện. Một lệnh hủy đơn hàng, một bảng danh sách và một tệp xuất dữ liệu có thể cùng dùng dữ liệu đơn hàng nhưng cần những hợp đồng khác nhau.

**Chọn entity khi cần làm việc với hành vi và trạng thái của aggregate; cân nhắc interface projection cho góc nhìn đọc theo property; chọn DTO khi cần một cấu trúc giá trị được kiểm soát rõ.** Một ca sử dụng cũng có thể đọc bằng projection rồi chuyển thành DTO ở ranh giới phản hồi. Không bắt buộc một lựa chọn phải được dùng cho mọi tầng.

## 1. So sánh theo trách nhiệm

Spring Data cho phép query method trả về các góc nhìn riêng của aggregate thay vì luôn trả aggregate root. Interface projection được cung cấp bằng proxy; class-based projection tạo instance DTO qua cơ chế khởi tạo phù hợp. Xem [Spring Data Commons — Projections](https://docs.spring.io/spring-data/commons/reference/repositories/projections.html).

| Tiêu chí | Entity/aggregate | Interface projection | DTO/class/record |
| --- | --- | --- | --- |
| Mục đích chính | Biểu diễn đối tượng nghiệp vụ và trạng thái được lưu | Đọc một góc nhìn qua accessor | Mang một tập giá trị có hình dạng xác định |
| Hợp đồng nổi bật | Định danh, trạng thái, hành vi | Getter khớp dữ liệu nguồn hoặc cơ chế tính toán được hỗ trợ | Constructor, component và API đọc dữ liệu |
| Cách sử dụng thường gặp | Áp dụng quy tắc rồi lưu thay đổi | Đọc các trường cần cho chức năng nội bộ | Phản hồi API, xuất dữ liệu, kết quả báo cáo |
| Điều cần chú ý | Giao dịch, vòng đời và mapping của store | Nguồn proxy, null, property lồng | Cách tạo DTO, tên/kiểu tham số, dữ liệu đã được sao chép đến mức nào |
| Có tự bảo đảm truy vấn nhẹ hơn không? | Không | Không | Không |

Các cột là định hướng thiết kế, không phải một luật rằng DTO chỉ dùng ngoài hệ thống hay interface chỉ dùng trong repository.

### Entity không đồng nghĩa với một đồ thị đã tải hết

“Trả entity” mô tả kiểu đối tượng nhận được, không cam kết mọi quan hệ và collection đều đã tải. Ngược lại, một projection có ít getter cũng không cam kết mọi store chỉ đọc đúng số field tương ứng.

Vòng đời entity còn phụ thuộc store. Không mang giả định về JPA persistence context, lazy loading hoặc dirty checking áp dụng chung cho tất cả module Spring Data.

### DTO có hai cách xuất hiện khác nhau

Cần tách rõ:

1. **DTO projection tại query:** repository yêu cầu trả một kiểu DTO; store và hạ tầng query quyết định cách tạo dữ liệu đó.
2. **DTO phản hồi do ứng dụng tạo:** service ánh xạ từ entity hoặc projection đã đọc sang cấu trúc bên gọi cần.

Hai cách có thể cho JSON giống nhau nhưng đọc dữ liệu tại nguồn theo những đường khác nhau. Nhìn hình dạng phản hồi không đủ kết luận hiệu năng truy vấn.

## 2. Một mô hình đơn hàng, ba nhu cầu

Giả sử domain type `PurchaseOrder` đã được ánh xạ trong ứng dụng:

| Property | Kiểu Java | Vai trò |
| --- | --- | --- |
| `id` | `Long` | Định danh đơn |
| `customerName` | `String` | Tên khách hàng |
| `status` | `OrderStatus` | Trạng thái đơn |
| `total` | `BigDecimal` | Giá trị đơn |
| `currency` | `String` | Mã tiền tệ |
| `createdAt` | `Instant` | Thời điểm tạo |
| `internalNote` | `String` | Ghi chú xử lý nội bộ |

Enum minh họa:

```java
public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
```

Ba ca sử dụng:

| Ca sử dụng | Việc cần làm | Dữ liệu hoặc hành vi cần |
| --- | --- | --- |
| Hủy một đơn | Kiểm tra quy tắc trạng thái và ghi thay đổi | Hành vi hủy của aggregate |
| Xem danh sách đơn đã thanh toán | Hiển thị các giá trị đơn giản | Mã, khách, trạng thái, tổng tiền, tiền tệ |
| Xuất dữ liệu đơn đã thanh toán | Tạo các hàng có cấu trúc ổn định | Các giá trị trên và thời điểm tạo |

Trong bài, giả định `PurchaseOrder.cancel()` chứa quy tắc chỉ cho phép hủy đơn ở trạng thái `NEW`. Đây là quy tắc nghiệp vụ của ví dụ, không phải chức năng Spring Data tự cung cấp.

Các kiểu Java bên dưới được dùng trong cùng package ví dụ. Domain type và cấu hình store đã có sẵn; đoạn mã không lựa chọn annotation ánh xạ dành cho một store cụ thể.

## 3. Ca sử dụng có hành vi: làm việc với entity

Với thao tác hủy, cần một đối tượng có hành vi nghiệp vụ chứ không chỉ một tập getter cho màn hình.

Kết quả phản hồi của lệnh có thể rất nhỏ:

```java
public record OrderCommandResult(Long id, OrderStatus status) {
}
```

Phần xử lý minh họa trong service:

```java
public OrderCommandResult cancel(Long orderId) {
    PurchaseOrder order = repository.findById(orderId)
            .orElseThrow(() -> new IllegalArgumentException(
                    "Order not found"));

    order.cancel();

    PurchaseOrder saved = repository.save(order);

    return new OrderCommandResult(
            saved.getId(),
            saved.getStatus());
}
```

Ở đây `repository` là `OrderRepository` khai báo ở mục 6; giả định entity cung cấp các getter tương ứng. Luồng xử lý cần ranh giới giao dịch và kiểm soát cạnh tranh phù hợp với store.

`CrudRepository` định nghĩa các thao tác tìm và lưu theo kiểu domain của repository. Khi cần tiếp tục sử dụng đối tượng đã lưu, dùng instance trả về từ `save`. Xem [API CrudRepository](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/CrudRepository.html).

Với JPA, service thường là nơi xác định transaction bao trùm các lời gọi repository của một đơn vị công việc. Quy tắc giao dịch cụ thể thuộc module JPA; xem [Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html).

### Vì sao không đọc một view rồi tự dựng entity để lưu?

Giả sử view danh sách không có `internalNote` và các trạng thái liên quan khác của aggregate. Tạo một `PurchaseOrder` mới từ view rồi gọi `save` không có nghĩa các giá trị thiếu sẽ tự được giữ nguyên.

Khi cần cập nhật, chọn một đường ghi có hợp đồng rõ ràng. Ví dụ này dùng aggregate để giữ quy tắc hủy tại đúng nơi; không dùng góc nhìn đọc làm bản thay thế ngầm cho toàn bộ đối tượng được lưu.

### Entity trong xử lý không buộc phải là phản hồi ngoài cùng

Service đã dùng entity để thực hiện hành vi nhưng chỉ trả `OrderCommandResult`. Đây là một kết hợp hợp lý: đối tượng dùng để quyết định và cập nhật có trách nhiệm khác với dữ liệu thông báo kết quả.

Nếu entity đã có sẵn sau thao tác, việc tạo phản hồi từ nó cũng có thể tránh một truy vấn projection chỉ để đọc lại vài giá trị vừa nhận được.

## 4. Góc nhìn đọc theo property: interface projection

Bảng danh sách không hủy đơn, không cần ghi chú nội bộ và không cần toàn bộ API của aggregate. Có thể biểu đạt tập dữ liệu cần đọc:

```java
import java.math.BigDecimal;

public interface OrderListView {

    Long getId();

    String getCustomerName();

    OrderStatus getStatus();

    BigDecimal getTotal();

    String getCurrency();
}
```

Các accessor khớp các property của `PurchaseOrder`. Interface này được thiết kế như một projection riêng, nằm ngoài hệ thống kế thừa của domain type.

Ưu điểm trong ca sử dụng này:

- Chữ ký đọc cho thấy đúng những giá trị bảng cần.
- Phần sử dụng view không có các phương thức hủy hoặc cập nhật đơn.
- Tập property dễ đối chiếu với yêu cầu hiển thị.
- Có thể mở rộng phần đọc mà không trả thêm toàn bộ cấu trúc domain.

Tuy nhiên, proxy projection vẫn có nguồn dữ liệu đằng sau. Getter có thể đọc từ map, đối tượng hoặc kết quả do store thích nghi. Một interface chỉ có getter không tự tạo một bản sao bất biến của mọi dữ liệu nguồn.

### Khi interface là lựa chọn gọn

Một service nội bộ đọc vài property rồi tính toán hoặc tạo response ngay có thể dùng interface projection thuận tiện. Không cần tự tạo một class chỉ để chứa đúng các getter này.

Nếu yêu cầu chuyển sang một kết quả có quy tắc equality theo giá trị, cần được tạo thủ công ở nhiều nơi hoặc cần rời ngữ cảnh đọc dưới dạng dữ liệu độc lập, DTO có thể diễn đạt hợp đồng rõ hơn.

### Giữ getter phục vụ một nhu cầu cụ thể

Không thêm danh sách dòng hàng, toàn bộ khách hàng, lịch sử thanh toán và metadata chỉ để dùng một interface cho mọi màn hình. Mỗi getter mới có thể mở rộng lượng dữ liệu hoặc đường truy cập mà query cần hỗ trợ.

Một interface projection tốt không nhất thiết là nhỏ nhất có thể; nó cần đủ dữ liệu cho một nhu cầu đọc đã xác định. View quá hẹp khiến service phải truy vấn bổ sung cho từng hàng cũng là một thiết kế cần xem lại.

## 5. Hợp đồng giá trị rõ ràng: DTO và record

Với tệp xuất dữ liệu, ứng dụng cần một hàng gồm các giá trị cụ thể. Record minh họa sau dùng Java 17 trở lên:

```java
import java.math.BigDecimal;
import java.time.Instant;

public record OrderExportRow(
        Long id,
        String customerName,
        OrderStatus status,
        BigDecimal total,
        String currency,
        Instant createdAt) {
}
```

Đây là cấu trúc dữ liệu của hàng xuất, không phải entity đơn hàng. Nó không cần biết cách hủy đơn hoặc lưu thay đổi.

Java record cung cấp các component, canonical constructor và các phương thức theo giá trị như `equals`, `hashCode`, `toString`. Record có tính bất biến nông; xem [Java Record](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Record.html).

Trong ví dụ, các component dùng kiểu giá trị phù hợp để mang dữ liệu đã đọc. Nếu một DTO chứa collection mutable hoặc một entity bên trong, bản thân việc khai báo record không biến các đối tượng được tham chiếu thành bất biến.

### DTO có thể tạo tại query hoặc sau khi đọc

Repository có thể trả trực tiếp `OrderExportRow` nếu store và loại query hỗ trợ DTO projection. Khi đó hợp đồng constructor/component tham gia vào quá trình ánh xạ kết quả.

Ứng dụng cũng có thể tạo DTO từ entity hoặc interface projection đã đọc. Lựa chọn này ổn định hình dạng dữ liệu đầu ra, nhưng không làm giảm ngược lượng dữ liệu của truy vấn đã hoàn tất.

Nếu DTO là class nhiều constructor thay vì record, cần bảo đảm framework nhận diện đúng constructor dùng cho projection, chẳng hạn dùng `@PersistenceCreator` khi cần. Việc chọn constructor và ánh xạ giá trị vẫn phải theo hợp đồng query của store.

### DTO phù hợp cho kết quả tổng hợp riêng

Một báo cáo doanh thu theo trạng thái và tiền tệ có thể cần:

```java
import java.math.BigDecimal;

public record RevenueSummaryRow(
        String currency,
        OrderStatus status,
        Long orderCount,
        BigDecimal revenue) {
}
```

Một hàng như vậy tổng hợp nhiều đơn; nó không phải một `PurchaseOrder` bị bỏ bớt field. Chọn một kiểu báo cáo riêng giúp tránh tạo entity có định danh hoặc trạng thái không còn đúng ý nghĩa.

Truy vấn tổng hợp và kiểu giá trị trả về phải được thiết kế theo store. Mã trên chỉ biểu đạt cấu trúc mong muốn; nó không tự thực hiện việc đếm hay cộng doanh thu.

## 6. Một repository có thể phục vụ nhiều kiểu kết quả

Giả sử các kiểu ví dụ nằm trong cùng package và ứng dụng đã cấu hình module store phù hợp:

```java
import java.util.List;

import org.springframework.data.repository.CrudRepository;

public interface OrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    List<OrderListView> findByStatusOrderByCreatedAtDescIdDesc(
            OrderStatus status);

    List<OrderExportRow> findExportByStatusOrderByCreatedAtDescIdDesc(
            OrderStatus status);

    <T> List<T> findByStatusOrderByCreatedAtDescIdDesc(
            OrderStatus status,
            Class<T> projectionType);
}
```

Ý nghĩa của các phương thức:

| Đường sử dụng | Kiểu kết quả | Ca sử dụng |
| --- | --- | --- |
| `findById` kế thừa từ CRUD | `Optional<PurchaseOrder>` | Lấy aggregate để xử lý nghiệp vụ |
| Query trả `OrderListView` | Interface projection | Danh sách đọc nội bộ |
| Query trả `OrderExportRow` | DTO projection | Hàng xuất dữ liệu |
| Query nhận `Class<T>` | Kiểu được chọn lúc gọi | Nhiều góc nhìn trên cùng một điều kiện đọc |

Phần `Export` trước `By` trong tên query method mang tính mô tả; điều kiện vẫn là property `status`. Nó giúp phân biệt phương thức trả DTO với phương thức trả interface mà không thay hợp đồng CRUD.

Không khai báo lại một base method như `findById` với kiểu trả về không tương thích rồi kỳ vọng biến nó thành projection query. Hãy giữ đường entity và đặt query method riêng cho góc nhìn cần đọc.

### Lời gọi cố định thể hiện mục đích ngay trong API

```java
List<OrderListView> views =
        repository.findByStatusOrderByCreatedAtDescIdDesc(
                OrderStatus.PAID);

List<OrderExportRow> rows =
        repository.findExportByStatusOrderByCreatedAtDescIdDesc(
                OrderStatus.PAID);
```

Hai phương thức có cùng bộ lọc nghiệp vụ nhưng trả hai cấu trúc phục vụ hai nơi dùng khác nhau. Đây có thể là lựa chọn rõ ràng hơn một phương thức tổng quát nếu service chỉ có vài nhu cầu ổn định.

### Projection động giúp chọn hình dạng lúc gọi

```java
List<OrderExportRow> rows =
        repository.findByStatusOrderByCreatedAtDescIdDesc(
                OrderStatus.PAID,
                OrderExportRow.class);
```

`Class<T>` lựa chọn kiểu kết quả, không tự thay đổi điều kiện `status` hoặc các quy tắc nghiệp vụ. Kiểu được chọn vẫn phải có cấu trúc projection mà store xử lý được.

Projection động phù hợp khi việc chọn góc nhìn theo lời gọi mang lại lợi ích rõ. Nó không có nghĩa một repository method sẽ hỗ trợ tùy ý mọi class ứng dụng truyền vào.

## 7. Kết hợp interface ở lớp đọc với DTO phản hồi

Giả sử API muốn tên trường khác property domain:

```java
import java.math.BigDecimal;

public record OrderCard(
        Long orderId,
        String customer,
        OrderStatus status,
        BigDecimal amount,
        String currency) {

    public static OrderCard from(OrderListView view) {
        return new OrderCard(
                view.getId(),
                view.getCustomerName(),
                view.getStatus(),
                view.getTotal(),
                view.getCurrency());
    }
}
```

Service có thể ánh xạ rõ ràng:

```java
List<OrderCard> cards = repository
        .findByStatusOrderByCreatedAtDescIdDesc(OrderStatus.PAID)
        .stream()
        .map(OrderCard::from)
        .toList();
```

Trong luồng này:

| Tầng | Kiểu | Tên dữ liệu tiêu biểu |
| --- | --- | --- |
| Domain và query | `PurchaseOrder` | `id`, `customerName`, `total` |
| Góc nhìn đọc | `OrderListView` | Getter tương ứng với property nguồn |
| Hợp đồng phản hồi | `OrderCard` | `orderId`, `customer`, `amount` |

Không truyền `OrderCard.class` vào một derived dynamic projection rồi mặc định các tên `orderId`, `customer`, `amount` sẽ tự ánh xạ sang các property khác tên. Đoạn mapper trên thể hiện chính xác sự tương ứng đó. Một query tự khai báo có thể có hợp đồng mapping khác, nhưng cần thiết kế riêng.

### Khi nào cần bước ánh xạ này?

Nó hữu ích khi hợp đồng phản hồi cần được đặt tên và phát triển độc lập với mô hình đọc repository, hoặc khi cần tạo một đối tượng giá trị cụ thể để sử dụng sau bước đọc.

Nếu một chức năng nội bộ chỉ dùng vài getter ngay tại nơi gọi và không cần hợp đồng dữ liệu riêng, có thể dùng `OrderListView` trực tiếp. Không cần tạo thêm DTO chỉ vì mọi tầng trong sơ đồ đều phải có một class khác nhau.

DTO phản hồi cũng không phải cơ chế tự bảo đảm tính nhất quán của nhiều lần đọc. Một record có các giá trị đã nhận không tạo ra transaction hoặc snapshot dữ liệu cho cả một loạt truy vấn trước đó.

## 8. Ma trận lựa chọn theo ca sử dụng

| Tình huống | Lựa chọn nên cân nhắc trước | Điều kiện hoặc giới hạn |
| --- | --- | --- |
| Hủy đơn theo quy tắc trạng thái | Entity/aggregate trong luồng ghi | Có ranh giới giao dịch và cơ chế lưu phù hợp |
| Bảng nội bộ chỉ đọc các property đơn giản | Interface projection | Getter khớp dữ liệu và store hỗ trợ query đó |
| Phản hồi API có tên trường và cấu trúc riêng | DTO phản hồi | Có bước ánh xạ rõ từ nguồn |
| Tệp xuất có cấu trúc hàng ổn định | DTO/record | Chọn cách tạo trực tiếp tại query hoặc ánh xạ sau đọc |
| Báo cáo tổng hợp nhiều đơn | Kiểu DTO báo cáo riêng | Query tổng hợp có kiểu, nhóm và đơn vị dữ liệu rõ |
| Một màn hình chi tiết chỉ đọc | Projection hoặc DTO đủ cho màn hình | Không bắt buộc entity chỉ vì tên màn hình là “chi tiết” |
| Cần kiểm tra tồn tại | `existsBy…` phù hợp | Không cần tạo một đối tượng kết quả nhiều field |
| Chỉ cần số lượng | Truy vấn đếm phù hợp | Kết quả là giá trị số |
| Entity đã được tải để xử lý lệnh | Tạo phản hồi từ entity hiện có nếu đủ | Không mặc định phải truy vấn lại projection |
| Nhiều cách hiển thị cùng bộ lọc | Projection động hoặc các query method riêng | Chọn theo mức độ rõ ràng của API và khả năng store |

Các dạng trả về như scalar, collection, projection và các wrapper được mô tả trong [Repository query return types](https://docs.spring.io/spring-data/commons/reference/repositories/query-return-types-reference.html). Danh sách đó là khả năng chung; cần đối chiếu module store để biết tổ hợp thực sự hỗ trợ.

Để dùng ma trận, hãy bắt đầu bằng câu hỏi nghiệp vụ. “Cần hủy đơn” và “cần hiện trạng thái đơn” là hai yêu cầu khác nhau dù cùng có property `status`.

## 9. Đánh giá chi phí truy vấn theo nhiều chiều

Không xếp hạng cố định “DTO nhanh nhất, interface đứng thứ hai, entity chậm nhất”. Kết quả phụ thuộc query, dữ liệu, mapping, provider và cách sử dụng.

### Số thuộc tính mỗi kết quả

Closed interface projection có các accessor khớp property giúp hạ tầng xác định dữ liệu cần thiết. DTO projection có hợp đồng constructor/component cho mục tiêu tương tự. Tuy nhiên, dùng biểu thức động hoặc query tự khai báo có thể thay đổi khả năng tối ưu.

Đối với JPA, lựa chọn các property cấp cao nhất và việc truy cập property lồng có các giới hạn khác nhau; property lồng dẫn đến join có thể khiến phần join được materialize rộng hơn mong đợi. Xem [Projections với JPA](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html).

### Số hàng kết quả

Một DTO nhỏ cho mỗi đơn vẫn không giải quyết bài toán tải hàng triệu đơn vào một `List`. Thiết kế phân trang, slicing hoặc scrolling độc lập với việc chọn entity/projection/DTO.

Các ví dụ dùng `List` để minh họa với tập dữ liệu có giới hạn. Với danh sách tăng lớn, chọn wrapper và cơ chế lấy từng phần phù hợp với store.

### Số lượt truy vấn

Một projection quá hẹp có thể khiến service truy vấn thêm entity cho từng hàng. Ví dụ, đọc 100 view rồi gọi `findById` 100 lần để lấy phần dữ liệu còn thiếu tạo thêm 100 lời gọi đọc.

Cần xác định đủ dữ liệu cho chức năng ngay từ thiết kế query, hoặc chọn một cách tải bổ sung có chủ đích. Không đánh giá hiệu quả chỉ bằng số getter của view đầu tiên.

### Chi phí tạo đối tượng và sử dụng sau khi đọc

Interface projection có cơ chế proxy; DTO có chi phí tạo và giữ các giá trị. Mapper phản hồi tạo thêm các đối tượng đầu ra. Đây là các chi phí cần quan sát theo dữ liệu thực tế, không phải lý do để tự động bỏ một thiết kế có hợp đồng rõ.

Khi đánh giá tại dự án, đối chiếu query thực thi, dữ liệu truyền, số lượt đọc và thời gian xử lý với cùng yêu cầu chức năng. Không so sánh hai query lấy dữ liệu khác nhau rồi kết luận một kiểu kết quả luôn ưu việt hơn.

## 10. Những nhầm lẫn dẫn đến chọn sai kiểu

### “Chỉ đọc thì luôn dùng projection”

Một luồng đọc có thể đã có entity cần thiết, hoặc cần dùng hành vi tính toán của mô hình trên trạng thái phù hợp. Chọn projection chỉ vì đó là thao tác đọc có thể làm phát sinh lần đọc lại không cần thiết.

Ngược lại, một màn hình chi tiết không cần hành vi domain vẫn có thể dùng một DTO hoặc view dành riêng. Quyết định cần dựa trên công việc thực tế.

### “Interface chỉ có getter nên là snapshot bất biến”

Projection proxy có nguồn đằng sau; không có setter trong interface chỉ giới hạn API mà bên gọi sử dụng. Nó không tự sao chép hoặc đóng băng mọi đối tượng nguồn.

Nếu cần kết quả độc lập để truyền qua ranh giới ứng dụng, hãy thiết kế dữ liệu DTO và thời điểm ánh xạ rõ ràng. Với DTO chứa tham chiếu mutable, tiếp tục xác định mức sao chép cần thiết.

### “DTO là entity nhưng ít field hơn”

DTO không phải một phần trạng thái an toàn để tùy ý chuyển ngược thành entity rồi lưu. Các giá trị không có trong DTO cần được xử lý theo luồng cập nhật được thiết kế rõ.

Trong ví dụ, `OrderExportRow` phục vụ xuất dữ liệu. Nó không thể thay cho hợp đồng hủy đơn của `PurchaseOrder`.

### “DTO equality cũng chính là định danh nghiệp vụ”

Record sinh equality theo các component. Nếu yêu cầu là mỗi đơn xuất hiện một lần theo `id`, cần biểu đạt quy tắc đó bằng định danh đơn.

Hai hàng có cùng `id` nhưng khác giá trị được đọc ở hai thời điểm có thể không bằng nhau theo equality của record. Ngược lại, một DTO báo cáo có thể không đại diện cho một đơn riêng lẻ để dùng `id` theo cách đó.

### “Thêm tất cả getter sẽ dùng chung được lâu hơn”

Một view bao phủ mọi màn hình thường tăng dần dữ liệu cần đọc và sự phụ thuộc. Một DTO quá nhỏ nhưng buộc mọi bên gọi lấy thêm dữ liệu cũng gây khó khăn.

Thiết kế hợp đồng vừa đủ cho một nhóm ca sử dụng có yêu cầu giống nhau, đặt tên rõ và xem lại khi nhu cầu thay đổi. Không tối ưu số lượng class bằng cách che các khác biệt nghiệp vụ.

### “Đổi kiểu trả về là đủ cho mọi store”

Cùng khai báo Commons không đồng nghĩa mọi query của JPA, MongoDB hoặc store khác có cùng khả năng projection, constructor mapping và xử lý quan hệ.

Khi tích hợp, xác nhận đúng module, loại query và phiên bản. Với DTO nhiều constructor, native query hoặc kết quả tổng hợp, kiểm tra thêm hợp đồng tạo đối tượng thay vì chỉ đổi generic của `List`.

## 11. Bài thực hành lựa chọn và giải thích

Dùng mô hình đơn hàng trong bài, thực hiện lần lượt:

1. Mô tả dữ liệu và hành vi cần cho thao tác hủy, danh sách đơn thanh toán và tệp xuất.
2. Chọn kiểu đọc cho từng ca sử dụng; giải thích bằng trách nhiệm thay vì độ ngắn của mã.
3. Khai báo `OrderListView`, `OrderExportRow` và các query method tương ứng.
4. Giữ `findById` của CRUD cho luồng làm việc với entity.
5. Ánh xạ view sang `OrderCard`; chỉ ra vì sao tên trường phản hồi không cần trùng property domain ở bước này.
6. Dùng phương thức projection động với `OrderExportRow.class`; xác định điều kiện và thứ tự truy vấn vẫn giữ nguyên.
7. Thiết kế riêng hình dạng một hàng báo cáo theo trạng thái và tiền tệ, thay vì dùng entity giả cho kết quả tổng hợp.
8. Xác định cách lấy từng phần nếu số đơn lớn; không chỉ thu hẹp field rồi tải toàn bộ.
9. Nêu dữ liệu cần quan sát trước khi kết luận lựa chọn projection hoặc DTO giúp giảm chi phí đọc.

Các đoạn mã và tình huống là ví dụ thiết kế, không phải báo cáo chạy kiểm thử hay benchmark. Kết quả cần đạt là một hợp đồng phù hợp ở mỗi ranh giới: đúng đối tượng để thực hiện nghiệp vụ, đủ dữ liệu để hoàn thành việc đọc và cấu trúc phản hồi có ý nghĩa với bên sử dụng.