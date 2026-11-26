# Kiểm thử nâng cấp dependency cùng với dữ liệu và truy vấn thực tế

Nâng cấp dependency của Spring Data không chỉ là đổi phiên bản rồi kiểm tra ứng dụng có khởi động hay không. Một repository vẫn có thể được tạo thành công trong khi truy vấn trả thiếu dữ liệu, thứ tự phân trang thay đổi, projection không ánh xạ được hoặc thao tác ghi không còn đáp ứng hợp đồng nghiệp vụ.

Trong module **SPRING_DATA_COMMONS**, các abstraction như `Repository`, CRUD, derived queries, phân trang, sắp xếp, projection và auditing là những điểm tiếp xúc cần được kiểm tra. Chương **Phiên bản và AOT** bổ sung một yêu cầu: nếu sản phẩm dùng AOT hoặc native image, kết quả trên JVM thông thường chưa đủ để kết luận về artifact triển khai.

Bài này trình bày cách xây dựng bằng chứng nâng cấp bằng dữ liệu có tính đại diện và tập truy vấn thực sự được ứng dụng sử dụng. Mục tiêu là trả lời ba câu hỏi: hành vi nào phải được giữ nguyên, thay đổi nào được chấp nhận có chủ đích và đường thực thi nào chưa có đủ bằng chứng.

## 1. Xác định đúng đối tượng được nâng cấp

### 1.1. Spring Data Commons nằm trong một tập dependency

Spring Data Commons cung cấp các hợp đồng và hạ tầng dùng chung. Module kho dữ liệu, driver, mapper hoặc provider mới là những thành phần tham gia vào việc thực thi cụ thể. Vì vậy, kết quả của một truy vấn có thể thay đổi dù chữ ký repository không đổi.

Tùy ứng dụng, một đợt nâng cấp có thể liên quan đến:

- Spring Framework, Spring Boot nếu dùng và tập phiên bản Spring Data được quản lý cùng nhau.
- Module kho dữ liệu như JPA, JDBC, MongoDB hoặc một module khác.
- ORM provider, database driver, thư viện truy vấn bổ sung và mapper.
- JDK, Kotlin, công cụ AOT và công cụ build native nếu có.
- Phiên bản máy chủ dữ liệu, cấu hình collation, múi giờ và extension liên quan.

Khi sử dụng BOM hoặc cơ chế quản lý dependency của nền tảng, nên đánh giá bộ phiên bản được quản lý trước khi override một artifact riêng lẻ. Biên dịch thành công không chứng minh rằng một tổ hợp override bất kỳ là tổ hợp được hỗ trợ.

### 1.2. Ghi nhận baseline và candidate

**Baseline** là ứng dụng trước nâng cấp với bộ dependency và cấu hình đã xác định. **Candidate** là ứng dụng sau thay đổi đang được đánh giá. Hai phía cần được so sánh trong các điều kiện đủ giống nhau để giải thích được chênh lệch.

| Thành phần | Nội dung cần xác định |
| --- | --- |
| Mã ứng dụng | Revision và thay đổi mã cần thiết để nâng cấp |
| Dependency thực tế | Phiên bản đã được resolve, gồm thành phần bắc cầu có ảnh hưởng |
| Runtime | JDK, JVM hoặc native, cấu hình AOT nếu dùng |
| Kho dữ liệu | Loại, phiên bản, schema, index, collation và timezone liên quan |
| Dữ liệu | Bộ fixture hoặc snapshot, cách khôi phục và thời điểm lấy |
| Cấu hình | Profile, converter, naming strategy, auditing và repository scanning |

Nếu nâng Spring Data và đổi phiên bản database cùng lúc, cần phân biệt tác động của hai thay đổi. Khi có thể, tạo một bước trung gian chỉ đổi một nhóm biến. Khi không thể, kết luận phải phản ánh giới hạn đó thay vì quy toàn bộ khác biệt cho Commons.

Không cần cố định những thứ không liên quan đến hành vi đang xét. Tuy nhiên, thay đổi timezone hoặc collation trong một phép so sánh có thể làm kết quả trông giống lỗi dependency dù nguyên nhân thực tế nằm ở cấu hình dữ liệu.

## 2. Bắt đầu từ hợp đồng nghiệp vụ của repository

Một truy vấn có nhiều khía cạnh hơn danh sách đối tượng trả về:

1. **Tập kết quả:** những bản ghi nào phải có mặt hoặc phải vắng mặt?
2. **Hình dạng:** entity, DTO, interface projection hay wrapper nào được trả về?
3. **Thứ tự:** thứ tự có được cam kết hay chỉ là hệ quả ngẫu nhiên của kế hoạch thực thi?
4. **Biên:** giới hạn thời gian, giá trị `null`, chuỗi rỗng và điều kiện không có kết quả được hiểu thế nào?
5. **Thông tin bổ sung:** tổng số phần tử, `hasNext`, trạng thái auditing và version có đúng không?
6. **Tác động ghi:** dữ liệu được tạo, cập nhật hoặc xóa có đúng sau khi transaction kết thúc không?
7. **Chi phí:** độ trễ, số lần truy cập dữ liệu và mức tài nguyên có còn trong ngưỡng chấp nhận không?

Ví dụ, “lấy hai đơn đã thanh toán đầu tiên” là mô tả chưa đủ nếu không chỉ rõ thứ tự. Sau nâng cấp, một query planner khác có thể trả hai dòng khác mà vẫn đáp ứng một truy vấn không có `ORDER BY`.

Một hợp đồng kiểm tra tốt hơn là:

> Với dữ liệu cố định, lấy các đơn `PAID`, sắp xếp tăng dần theo `createdAt`, sau đó theo `id`; trang đầu gồm hai đơn có ID 101 và 102, tổng cộng có ba đơn phù hợp.

Hợp đồng này cho phép kiểm tra chính xác tập dữ liệu, thứ tự và phân trang mà không gắn chặt vào chuỗi SQL do provider sinh ra.

## 3. Chọn dữ liệu đại diện cho hành vi cần bảo vệ

### 3.1. Bộ dữ liệu nhỏ và bộ dữ liệu theo quy mô phục vụ hai mục đích

Một bộ fixture nhỏ giúp xác định kết quả mong đợi bằng tay và phát hiện lỗi ngữ nghĩa. Một bộ dữ liệu lớn hơn giúp quan sát kế hoạch truy vấn, phân bố và chi phí ở quy mô gần thực tế.

Không nên dùng một bộ dữ liệu rất lớn nhưng không biết chính xác đáp án để thay thế các ca kiểm tra nghiệp vụ. Ngược lại, năm dòng fixture không chứng minh được truy vấn phân trang còn đáp ứng thời gian phản hồi khi bảng có hàng triệu dòng.

| Loại dữ liệu | Dùng để kiểm tra | Giới hạn |
| --- | --- | --- |
| Fixture nhỏ, xác định được đáp án | Điều kiện lọc, thứ tự, mapping, nullability, biên thời gian | Ít phản ánh chi phí và độ lệch phân bố |
| Snapshot đã xử lý phù hợp cho môi trường kiểm thử | Tổ hợp dữ liệu thực tế và các quan hệ ít gặp | Cần biết nguồn và cách tái lập |
| Dữ liệu tổng hợp có phân bố chủ đích | Quy mô, cardinality, độ lệch và kịch bản tải | Có thể bỏ sót quy tắc lịch sử của dữ liệu thật |

Chỉ đưa vào dữ liệu cần cho mục tiêu kiểm tra; với snapshot, giữ quan hệ và phân bố cần thiết sau khi xử lý thông tin nhạy cảm. Một bộ dữ liệu không giữ được quan hệ cha-con sẽ tạo lỗi khác với tình huống cần đánh giá.

### 3.2. Những lớp dữ liệu dễ làm lộ khác biệt sau nâng cấp

- Giá trị nullable, chuỗi rỗng và thuộc tính không xuất hiện, nếu kho dữ liệu phân biệt các trường hợp đó.
- Chuỗi Unicode, dấu tiếng Việt, chữ hoa/thường và khoảng trắng có ý nghĩa với tìm kiếm.
- Nhiều bản ghi có cùng khóa sắp xếp chính.
- Thời điểm nằm ngay tại biên bắt đầu hoặc kết thúc khoảng truy vấn.
- Số thập phân có scale khác nhau, giá trị 0 và các giới hạn được nghiệp vụ cho phép.
- Dữ liệu có enum, converter, kiểu giá trị hoặc biểu diễn được tạo bởi phiên bản ứng dụng cũ.
- Quan hệ rỗng, nhiều phần tử hoặc thiếu tham chiếu trong phạm vi dữ liệu mà hệ thống cho phép.
- ID được gán trước, version ban đầu và trạng thái đối tượng mới theo cơ chế của module.

Không phải hệ thống nào cũng cần mọi lớp dữ liệu trên. Chọn theo schema, query và hợp đồng thực tế; tránh tạo dữ liệu vi phạm ràng buộc rồi xem lỗi bị từ chối là regression.

### 3.3. Một fixture minh họa có đáp án rõ ràng

Giả sử ứng dụng quản lý đơn hàng với các thuộc tính `id`, `externalRef`, `status`, `createdAt` và `total`. Các ví dụ tiếp theo giả định module kho dữ liệu hỗ trợ các chữ ký repository được dùng.

| id | externalRef | status | createdAt, UTC | total |
| --- | --- | --- | --- | --- |
| 101 | PO-A | PAID | 2026-01-01T10:00:00Z | 100.00 |
| 102 | PO-B | PAID | 2026-01-01T10:00:00Z | 200.00 |
| 103 | PO-C | PAID | 2026-01-01T11:00:00Z | 0.00 |
| 104 | PO-D | DRAFT | 2026-01-01T09:00:00Z | 999.90 |
| 105 | PO-E | CANCELLED | 2026-01-01T12:00:00Z | 50.00 |

Từ fixture này có thể xác định:

- Có ba đơn `PAID`.
- Khi sắp xếp theo `createdAt ASC, id ASC`, các đơn `PAID` có thứ tự 101, 102, 103.
- Trong khoảng nửa mở `[10:00, 11:00)`, chỉ các đơn 101 và 102 phù hợp.
- Đơn 103 có tổng tiền bằng 0 vẫn là dữ liệu hợp lệ trong giả định nghiệp vụ của ví dụ.

Hai dòng 101 và 102 cố ý trùng `createdAt` để kiểm tra vai trò của khóa sắp xếp phụ. Nếu dữ liệu mẫu chỉ chứa thời điểm duy nhất, một truy vấn thiếu khóa phụ có thể vượt kiểm tra dù chưa ổn định.

## 4. Lập tập truy vấn từ đường sử dụng thực tế

### 4.1. Không chỉ kiểm tra phương thức được gọi nhiều nhất

Một tập truy vấn hữu ích cần bao phủ cả mức độ sử dụng và mức độ khác biệt về cơ chế. Nhiều phương thức derived query đơn giản có thể đi cùng một đường hạ tầng; một projection hiếm gặp lại có thể đi qua constructor hoặc proxy riêng.

Nên lấy đầu vào từ các màn hình, API, tác vụ nền và nghiệp vụ ghi đang sử dụng repository. Với mỗi phương thức, ghi rõ kiểu trả về, tham số đại diện, dữ liệu đầu vào và kết quả cần kiểm tra. Những dữ liệu này là thiết kế kiểm thử của dự án, không phải một định dạng bắt buộc của Spring Data.

| Nhóm | Ví dụ cần bao phủ | Lý do |
| --- | --- | --- |
| CRUD | Tạo mới, đọc lại, cập nhật, xóa | Kiểm tra entity state và persistence |
| Derived query | Điều kiện kết hợp, khoảng thời gian, tồn tại | Kiểm tra diễn giải thuộc tính và toán tử |
| Truy vấn khai báo hoặc tùy biến | Truy vấn nghiệp vụ quan trọng | Có thể phụ thuộc parser hoặc provider khác |
| Pagination | Trang đầu, trang tiếp, trang rỗng | Kiểm tra dữ liệu và metadata phân trang |
| Projection | DTO, interface, dynamic projection nếu dùng | Kiểm tra hình dạng và cách dựng kết quả |
| Auditing | Tạo mới, cập nhật, người thực hiện | Kiểm tra callback và metadata kiểm toán |
| Tích hợp bổ sung | Querydsl, coroutine hoặc reactive nếu dùng | Mỗi đường có cơ chế và lifecycle riêng |

Với API chỉ trả một giá trị, cần kiểm tra trường hợp không có bản ghi và trường hợp nhiều bản ghi khi dữ liệu cho phép. Không mặc định rằng `Optional<T>` có nghĩa framework sẽ tự chọn một dòng tùy ý nếu truy vấn trả nhiều kết quả.

### 4.2. Repository minh họa

Các kiểu domain và mapping phải được định nghĩa theo module kho dữ liệu của ứng dụng. Phần dưới chỉ mô tả hợp đồng repository; đây không phải cấu hình dùng chung nguyên trạng cho mọi module.

```java
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    Optional<PurchaseOrder> findByExternalRef(String externalRef);

    boolean existsByExternalRef(String externalRef);

    Page<OrderSummary> findByStatus(
            OrderStatus status, Pageable pageable);

    List<PurchaseOrder>
    findByStatusAndCreatedAtGreaterThanEqualAndCreatedAtLessThan(
            OrderStatus status,
            Instant fromInclusive,
            Instant toExclusive);

    <T> List<T> findByStatus(
            OrderStatus status, Class<T> projectionType);
}
```

DTO minh họa:

```java
import java.math.BigDecimal;
import java.time.Instant;

public record OrderSummary(
        Long id,
        String externalRef,
        Instant createdAt,
        BigDecimal total) {
}
```

Tên thành phần của DTO tương ứng thuộc tính domain. Khả năng ánh xạ DTO và chữ ký dynamic projection phải được xác nhận trong module và bộ phiên bản đang dùng. Khai báo generic không khiến mọi kiểu đích trở thành hợp lệ.

## 5. Viết assertion về kết quả thay vì chỉ kiểm tra không ném lỗi

### 5.1. Kiểm tra phân trang bằng đáp án xác định

Ví dụ JUnit và AssertJ sau giả định repository đã được nối với kho dữ liệu kiểm thử, fixture ở phần trước đã được nạp và không có tác vụ khác sửa dữ liệu. Hàm này có thể được gọi từ bài kiểm tra tích hợp của ứng dụng.

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import static org.assertj.core.api.Assertions.assertThat;

static void assertPaidOrderPagination(
        PurchaseOrderRepository repository) {

    Sort order = Sort.by(
            Sort.Order.asc("createdAt"),
            Sort.Order.asc("id"));

    Page<OrderSummary> first = repository.findByStatus(
            OrderStatus.PAID, PageRequest.of(0, 2, order));

    assertThat(first.getContent())
            .extracting(OrderSummary::id)
            .containsExactly(101L, 102L);
    assertThat(first.getTotalElements()).isEqualTo(3L);
    assertThat(first.getTotalPages()).isEqualTo(2);
    assertThat(first.hasNext()).isTrue();

    Page<OrderSummary> second = repository.findByStatus(
            OrderStatus.PAID, PageRequest.of(1, 2, order));

    assertThat(second.getContent())
            .extracting(OrderSummary::id)
            .containsExactly(103L);
    assertThat(second.hasNext()).isFalse();
}
```

Kiểm tra này bảo vệ cả nội dung trang và thông tin tổng số. Nó không yêu cầu provider phải tạo đúng một chuỗi SQL cố định hoặc phải thực hiện một số câu lệnh cố định trong mọi trường hợp. Một module có thể tối ưu việc xác định tổng số khi đã có đủ thông tin từ nội dung trang.

Nếu ứng dụng dùng `Slice`, cần kiểm tra nội dung và `hasNext` theo hợp đồng `Slice`; không yêu cầu tổng số như `Page`. Nếu dùng cơ chế cuộn hoặc keyset pagination, cần kiểm tra vị trí tiếp tục và điều kiện sắp xếp theo API tương ứng, thay vì áp dụng nguyên bài kiểm tra offset pagination.

### 5.2. Kiểm tra khoảng thời gian và các biên

```java
import java.time.Instant;
import java.util.List;
import static org.assertj.core.api.Assertions.assertThat;

static void assertPaidOrdersInWindow(
        PurchaseOrderRepository repository) {

    List<PurchaseOrder> found = repository
            .findByStatusAndCreatedAtGreaterThanEqualAndCreatedAtLessThan(
                    OrderStatus.PAID,
                    Instant.parse("2026-01-01T10:00:00Z"),
                    Instant.parse("2026-01-01T11:00:00Z"));

    assertThat(found)
            .extracting(PurchaseOrder::getId)
            .containsExactlyInAnyOrder(101L, 102L);
}
```

Ở đây không cam kết thứ tự nên assertion kiểm tra tập phần tử. Giá trị 11:00 phải bị loại vì biên phải là exclusive. Nếu nghiệp vụ dùng ngày theo múi giờ địa phương, cần xác định cách chuyển ngày sang khoảng thời gian trước khi đối chiếu với giá trị lưu trữ.

Độ chính xác của timestamp cần phù hợp với kho dữ liệu. Một môi trường lưu microsecond và một môi trường lưu millisecond có thể làm khác biệt khi so sánh tại biên rất nhỏ. Hãy chọn giá trị kiểm tra theo hợp đồng lưu trữ hoặc kiểm tra rõ quy tắc làm tròn, thay vì bỏ qua toàn bộ sai khác thời gian.

### 5.3. Kiểm tra số thập phân theo nghĩa nghiệp vụ

Nếu `100.0` và `100.00` có cùng ý nghĩa trong nghiệp vụ, phép so sánh nên dựa trên giá trị số. Nếu scale được dùng để bảo toàn một định dạng hoặc hợp đồng xuất dữ liệu, phải kiểm tra scale riêng.

```java
assertThat(summary.total())
        .isEqualByComparingTo("100.00");
```

Không chuẩn hóa mọi khác biệt một cách tự động. Việc biến `null` thành 0 để so sánh có thể che mất một regression mapping quan trọng.

## 6. CRUD cần được đọc lại từ trạng thái đã lưu

### 6.1. `save` không chỉ là phép gán vào bộ nhớ

Một bài kiểm tra ghi cần phân biệt đối tượng đầu vào, đối tượng trả về và dữ liệu thực sự lưu trong kho. Hãy sử dụng đối tượng mà `save` trả về theo hợp đồng của repository; một module có thể trả về đối tượng khác do cơ chế mapping hoặc persistence của nó.

Các ca cần xem xét gồm:

- Tạo mới với ID và version ban đầu đúng mô hình.
- Tạo mới có ID được gán trước nếu ứng dụng hỗ trợ; kiểm tra cơ chế nhận biết đối tượng mới.
- Cập nhật một đối tượng hiện hữu và bảo toàn những thuộc tính không cần thay đổi.
- Xóa rồi đọc lại bằng một đường truy cập phù hợp để xác nhận tác động.
- Vi phạm ràng buộc nghiệp vụ hoặc ràng buộc dữ liệu và quan sát lỗi ở đúng ranh giới transaction.

Không mặc định `save` luôn là insert hoặc luôn là update. Cơ chế xác định đối tượng mới có thể liên quan đến ID, version, `Persistable` hoặc metadata của module. Đây là vùng cần đưa vào kiểm tra nếu ứng dụng có ID tự gán hoặc trạng thái mới tùy biến.

### 6.2. Tránh đọc lại từ cùng một cache rồi tưởng đã kiểm tra persistence

Với JPA, persistence context có thể giữ đối tượng đang quản lý. Sau khi ghi, một lần gọi đọc trong cùng context chưa chắc chứng minh được rằng dữ liệu có thể được tải lại đúng từ database.

Tùy mục tiêu kiểm tra, có thể cần flush, clear hoặc dùng transaction/context mới. Với module khác, dùng cơ chế kiểm tra persistence tương ứng; không sao chép cách xử lý JPA sang MongoDB hay JDBC như một quy tắc chung.

Cũng cần chú ý thời điểm lỗi xuất hiện. Lỗi ràng buộc có thể xuất hiện ở thao tác ghi, flush hoặc commit tùy cơ chế. Một bài kiểm tra rollback tự động trước khi đi qua đường cần kiểm tra có thể bỏ sót hành vi mà người dùng gặp khi transaction thực sự hoàn tất.

### 6.3. Kiểm tra optimistic locking bằng hai luồng trạng thái độc lập

Nếu ứng dụng dùng version để chống ghi đè, một ca kiểm tra có ý nghĩa là:

1. Hai transaction hoặc context độc lập cùng đọc một bản ghi ở cùng version.
2. Transaction thứ nhất cập nhật và hoàn tất thành công.
3. Transaction thứ hai cố cập nhật từ trạng thái cũ.
4. Xác nhận xung đột được báo theo hợp đồng của module và tầng ứng dụng xử lý đúng.
5. Đọc lại để bảo đảm dữ liệu của lần ghi thắng không bị mất.

Đọc hai lần trong cùng một persistence context có thể trả cùng một đối tượng và không mô phỏng được xung đột. Cần kiểm tra cả cơ chế persistence và phản hồi nghiệp vụ, ví dụ API trả lỗi xung đột thay vì ghi đè im lặng.

## 7. Projection và query tùy biến cần được kiểm tra theo từng đường

### 7.1. Đừng chỉ kiểm tra entity rồi suy ra DTO cũng đúng

Projection có thể dùng constructor, accessor proxy, biểu thức hoặc kết quả truy vấn được viết lại. Một entity đọc đúng chưa chứng minh các cơ chế đó đều đúng sau nâng cấp.

Với mỗi projection đang dùng, kiểm tra:

- Kiểu kết quả và các trường quan trọng.
- Giá trị nullable và hành vi khi không có kết quả.
- Constructor được chọn đối với DTO có nhiều constructor.
- Accessor lồng nhau hoặc biểu thức nếu projection có dùng.
- Phân trang và truy vấn đếm nếu projection được bọc trong `Page`.

Với interface projection, nên gọi các accessor trong bài kiểm tra. Chỉ kiểm tra danh sách không rỗng có thể chưa chạm đến nhánh xử lý xảy ra khi đọc một thuộc tính.

Với dynamic projection, gọi riêng từng kiểu đích được ứng dụng cho phép. Một lần chạy với domain type không đại diện cho lần chạy với DTO hoặc interface projection.

### 7.2. Querydsl và truy vấn khai báo cần dữ liệu đặc trưng

Nếu ứng dụng dùng Querydsl, cần kiểm tra Q-types được sinh và biên dịch, nhưng đó mới là điều kiện đầu vào. Bài kiểm tra tích hợp vẫn phải thực thi predicate, projection và binding từ request nếu có.

Với query khai báo trực tiếp hoặc custom repository fragment, chú ý:

- Binding tham số và converter tương ứng.
- Sự khác nhau giữa truy vấn lấy nội dung và truy vấn đếm.
- Join hoặc truy vấn liên quan có thể tạo nhiều dòng cho cùng một đối tượng.
- Alias và hình dạng kết quả dùng cho projection.
- Truy vấn sửa dữ liệu và trạng thái của context hoặc cache sau đó.

Không mặc định một phương án đếm hoặc loại bỏ trùng lặp là đúng cho mọi mô hình. Hãy tạo fixture có một đối tượng liên quan đến nhiều dòng để kiểm tra hợp đồng “một đơn hàng xuất hiện một lần” nếu nghiệp vụ yêu cầu như vậy.

## 8. Auditing và converter phải có đầu vào kiểm soát được

### 8.1. Kiểm tra cả tạo mới lẫn cập nhật

Nếu ứng dụng dùng auditing, cần xác định hợp đồng cụ thể: trường nào được điền khi tạo mới, trường nào đổi khi cập nhật và người thực hiện được lấy từ đâu.

Để kiểm tra ổn định, nên cung cấp nguồn thời gian và nguồn người dùng xác định được qua cơ chế cấu hình mà ứng dụng đang sử dụng, chẳng hạn `DateTimeProvider` và `AuditorAware` trong những tích hợp thích hợp.

| Thao tác | Kết quả cần đối chiếu theo cấu hình ứng dụng |
| --- | --- |
| Tạo mới | Thông tin tạo được thiết lập, thông tin sửa tuân theo cấu hình auditing |
| Cập nhật | Thông tin tạo được giữ đúng, thông tin sửa phản ánh lần cập nhật |
| Không có người dùng | Hành vi phù hợp hợp đồng của auditor và kiểu dữ liệu |
| Tác vụ nền | Người thực hiện và thời gian theo mô hình của tác vụ nền |

Không mặc định `lastModified` phải khác `created` khi tạo mới; một cấu hình auditing có thể điền cả hai ở cùng thời điểm. Bài kiểm tra cần bảo vệ cấu hình đã chọn, không áp đặt quy tắc ngầm.

### 8.2. Converter có thể làm khác biệt giữa dữ liệu cũ và mới

Dữ liệu đã ghi trước nâng cấp cần đọc được nếu đó là cam kết tương thích của ứng dụng. Tạo mới dữ liệu bằng candidate rồi đọc lại chỉ kiểm tra vòng ghi-đọc của chính candidate, chưa bao phủ dữ liệu lịch sử.

Với converter hoặc kiểu giá trị, nên có hai hướng kiểm tra:

1. Đọc các biểu diễn đã tồn tại trong kho trước nâng cấp.
2. Ghi giá trị bằng candidate rồi đọc lại và xác nhận biểu diễn lưu trữ khi biểu diễn đó thuộc hợp đồng cần bảo vệ.

Nếu có migration, cần phân biệt lỗi chuyển đổi schema với lỗi mapping repository. Đừng để quá trình nạp fixture vô tình chuyển hết dữ liệu cũ sang định dạng mới trước khi bài kiểm tra tương thích chạy.

## 9. Dùng kho dữ liệu phù hợp với mục tiêu kiểm tra

Một database nhúng hoặc fake repository hữu ích cho một số loại kiểm tra, nhưng không thay thế được việc kiểm tra ngữ nghĩa của engine triển khai thực tế. Khác biệt có thể xuất hiện ở collation, xử lý `null`, timezone, kiểu JSON, precision, join và index.

Nếu ứng dụng triển khai trên PostgreSQL, một bài kiểm tra chỉ chạy trên database nhúng không đủ làm bằng chứng về mọi truy vấn PostgreSQL. Tương tự, mô phỏng document store bằng một cấu trúc trong bộ nhớ không kiểm tra được pipeline và converter của máy chủ thật.

Có thể dùng môi trường dữ liệu tạm thời hoặc container kiểm thử để tái lập phiên bản engine. Việc lựa chọn phải phù hợp với module và hạ tầng của dự án. Điều quan trọng là hiểu môi trường đang mô phỏng điều gì, không phải bắt buộc mọi kiểm tra đều chạy cùng một loại môi trường.

Các giá trị cấu hình cần khớp với mục tiêu gồm:

- Schema và index áp dụng khi chạy ứng dụng.
- Timezone, collation và locale nếu ảnh hưởng đến truy vấn.
- Transaction isolation và cơ chế consistency có liên quan.
- Cấu hình converter, naming và mapping.

Một bài kiểm tra có đáp án ổn định vẫn cần kiểm soát việc ghi đồng thời. Nếu dữ liệu thay đổi giữa truy vấn lấy nội dung và truy vấn đếm, khác biệt có thể đến từ ranh giới consistency, không nhất thiết từ dependency mới.

## 10. Tách regression chức năng khỏi regression hiệu năng

### 10.1. Kết quả đúng nhưng đường truy cập đắt hơn

Một truy vấn có thể trả cùng dữ liệu sau nâng cấp nhưng phát sinh N+1, dùng index kém hơn hoặc thực hiện truy vấn đếm tốn chi phí. Vì vậy, cần kiểm tra hiệu năng cho những đường quan trọng trên dữ liệu có phân bố phù hợp.

Các chỉ số nên liên hệ với nhu cầu sử dụng:

| Chỉ số | Cách diễn giải |
| --- | --- |
| Độ trễ theo phân vị | Người dùng hoặc tác vụ nền có còn đáp ứng mục tiêu không? |
| Số lượt truy cập dữ liệu | Có xuất hiện truy vấn lặp theo số dòng hoặc số quan hệ không? |
| Số dòng đọc so với số dòng trả | Kế hoạch truy vấn có xử lý quá nhiều dữ liệu không? |
| CPU, bộ nhớ và allocation | Chi phí mapping, projection hoặc runtime có tăng đáng kể không? |
| Chi phí truy vấn đếm | `Page` có làm chậm luồng sử dụng cụ thể không? |

Không đặt một số lượng query duy nhất làm hợp đồng cho mọi repository. Có thể dùng ngân sách truy vấn cho một flow cụ thể khi đã hiểu cache và chiến lược fetch. Một thay đổi hợp lệ ở cơ chế tối ưu count có thể làm số query khác đi mà vẫn cải thiện hành vi.

### 10.2. So sánh trong điều kiện kiểm soát được

Dùng cùng dữ liệu, tài nguyên và cấu hình giữa baseline và candidate. Phân biệt lần chạy lạnh với trạng thái đã warm-up, tránh so một phía có cache với một phía chưa có cache.

Nên chạy đủ lần để nhận diện nhiễu, nhưng không dùng một phép đo nhanh trên máy đang bận làm kết luận về regression. Khi thấy chênh lệch đáng kể, xem kế hoạch thực thi, số truy vấn và dữ liệu đọc để giải thích nguyên nhân.

Tối ưu hóa có thể thay đổi SQL hoặc hình dạng query mà không vi phạm hợp đồng. Vì vậy, snapshot chuỗi SQL thường là công cụ chẩn đoán có chọn lọc, không phải oracle mặc định cho mọi nâng cấp.

## 11. Bổ sung lớp kiểm tra AOT và native nếu sản phẩm sử dụng

### 11.1. Kiểm tra theo các chế độ cần triển khai

Nếu sản phẩm chỉ triển khai JVM thông thường, không cần xem native image như điều kiện bắt buộc chỉ vì chương này đề cập AOT. Nếu sản phẩm triển khai native, tập bằng chứng phải có native executable thực tế.

| Chế độ | Điều kiểm tra được | Khoảng trống còn lại |
| --- | --- | --- |
| JVM thông thường | Logic và mapping trong cấu hình JVM | Chưa chứng minh metadata và giới hạn native |
| JVM dùng kết quả AOT, nếu toolchain hỗ trợ | Mã và cấu hình khởi tạo đã sinh | Chưa bao phủ đầy đủ native runtime |
| Native executable | Các đường repository đã thực thi trên artifact đích | Chưa bao phủ nhánh hoặc cấu hình không được chạy |

Một lần native build thành công hoặc health check trả thành công không thay thế các truy vấn có dữ liệu. Projection thứ hai chỉ được chọn ở một màn hình ít dùng vẫn có thể là nhánh chưa được bao phủ.

### 11.2. Các ca nên chạy trên artifact native

Ưu tiên những đường có cơ chế khác biệt:

- Mỗi kiểu dynamic projection thực sự được cho phép.
- DTO constructor, interface projection và accessor lồng nhau nếu dùng.
- Querydsl hoặc custom repository fragment đang phục vụ nghiệp vụ.
- Auditing khi ghi, không chỉ truy vấn đọc.
- Kotlin constructor mapping, nullability và coroutine nếu ứng dụng dùng các cơ chế đó.
- Phân trang có count và đường sắp xếp đang được công bố.

Dùng dữ liệu cũ đã lưu giúp phát hiện lỗi chỉ xuất hiện khi mapper gặp một kiểu hoặc một giá trị chưa được kích hoạt trong dữ liệu rỗng. Dùng đúng cấu hình build AOT giúp tránh nhầm giữa lỗi metadata và khác biệt do tập bean được tạo từ profile khác.

Nếu JVM đúng nhưng native lỗi, hãy xác định nhánh, kiểu và thành phần chịu trách nhiệm trước khi thêm runtime hints. Hint không sửa được một query sai hoặc một tích hợp chưa hỗ trợ cơ chế runtime cần thiết.

## 12. Quy trình so sánh baseline với candidate

Một quy trình thực dụng có thể đi theo các bước sau:

1. Xác định phạm vi nâng cấp và tiêu chí chấp nhận cho các flow quan trọng.
2. Chốt dữ liệu, schema và cấu hình kiểm thử; chuẩn bị các môi trường độc lập khi có ghi dữ liệu.
3. Chạy baseline để xác nhận fixture và assertion phản ánh đúng hợp đồng hiện tại.
4. Chạy candidate với cùng đầu vào và thu các kết quả tương ứng.
5. Phân loại khác biệt theo nghiệp vụ, mapping, transaction, hiệu năng hoặc chế độ runtime.
6. Điều chỉnh mã hoặc cấu hình theo thay đổi đã hiểu, rồi chạy lại những đường bị ảnh hưởng.
7. Kết luận riêng phần đã có bằng chứng và phần chưa được bao phủ.

Không chạy baseline và candidate ghi nối tiếp lên cùng dữ liệu đã bị biến đổi rồi so sánh như hai phép thử tương đương. Cần khôi phục dữ liệu đầu vào hoặc dùng các bản sao độc lập. Với ID tự sinh, xác định cách đối chiếu bằng khóa nghiệp vụ thay vì mặc định hai lượt chạy phải sinh cùng ID.

### 12.1. Baseline không phải chân lý cho mọi trường hợp

Nếu baseline đang có lỗi, việc candidate khác baseline có thể là một cải thiện. Ngược lại, nếu cả hai đều sai theo yêu cầu nghiệp vụ, phép so sánh ngang bằng sẽ không phát hiện được.

Nên kết hợp ba loại bằng chứng:

- Kết quả mong đợi được xác định từ yêu cầu và fixture.
- Hành vi baseline đã được ghi nhận.
- Thay đổi được chủ động chấp nhận theo phạm vi nâng cấp.

Ví dụ, một bản nâng cấp sửa cách diễn giải biên truy vấn có thể làm một ca cũ thay đổi. Cần xác nhận hợp đồng đúng rồi cập nhật bài kiểm tra có giải thích. Không cập nhật hàng loạt kết quả mong đợi chỉ vì candidate trả về kết quả mới.

### 12.2. Mẫu phân loại khác biệt

| Quan sát | Câu hỏi cần trả lời | Hướng xử lý |
| --- | --- | --- |
| Khác tập ID | Điều kiện truy vấn, converter hay dữ liệu đã thay đổi? | Thu hẹp query và kiểm tra giá trị tại biên |
| Cùng tập ID, khác thứ tự | Hợp đồng có thứ tự toàn phần không? | Bổ sung khóa phụ nếu nghiệp vụ cần ổn định |
| Nội dung đúng, tổng số sai | Query count có cùng ngữ nghĩa lọc và loại trùng không? | Kiểm tra đường count và fixture có quan hệ nhiều dòng |
| DTO lỗi, entity đúng | Constructor, alias hoặc proxy nào khác? | Kiểm tra riêng projection bị lỗi |
| Ghi thành công nhưng đọc lại sai | Cache, converter, commit hay schema gây khác biệt? | Đọc từ context độc lập và quan sát giá trị lưu |
| JVM đúng, native sai | Nhánh nào thiếu hỗ trợ hoặc metadata? | Kiểm tra artifact và cơ chế AOT cụ thể |
| Kết quả đúng, độ trễ tăng | Tăng round-trip, đổi kế hoạch hay nhiễu đo? | Đo lại có kiểm soát và xem execution plan |

## 13. Nâng cấp dependency và migration dữ liệu là hai trục khác nhau

Có những đợt nâng cấp chỉ đổi thư viện, không đổi schema. Cũng có đợt cần migration schema hoặc dữ liệu. Hai loại thay đổi này cần được kiểm tra riêng khi có thể.

Nếu có migration, một chuỗi kiểm tra hữu ích là:

```text
Dữ liệu và schema hiện tại
    -> bản sao dành cho kiểm thử
    -> migration theo quy trình dự kiến
    -> ứng dụng candidate
    -> đọc dữ liệu lịch sử
    -> ghi dữ liệu mới
    -> đọc lại và chạy truy vấn nghiệp vụ
```

Không chỉ kiểm tra database tạo mới từ đầu. Một schema sạch có thể hoạt động trong khi dữ liệu lâu năm thiếu giá trị mà mapper mới đang giả định là bắt buộc.

Nếu kế hoạch triển khai có chạy đồng thời hai phiên bản ứng dụng, cần kiểm tra tổ hợp đọc-ghi phù hợp với giai đoạn chuyển tiếp. Khả năng quay về phiên bản cũ cũng phụ thuộc schema và biểu diễn dữ liệu đã ghi; đổi lại dependency không tự đảo ngược migration.

Độ sâu của phần kiểm tra này nên tương ứng với cách triển khai thực tế. Một ứng dụng không có giai đoạn chạy song song không cần giả định mọi tổ hợp đều là yêu cầu bắt buộc.

## 14. Tiêu chí chấp nhận phải gắn với phạm vi đã kiểm tra

Một quyết định nâng cấp có căn cứ thường dựa trên các điều kiện sau:

- Các hợp đồng repository quan trọng đã vượt kiểm tra bằng dữ liệu có đáp án xác định.
- Dữ liệu lịch sử và các dạng giá trị ứng dụng thực sự lưu vẫn đọc được theo cam kết tương thích.
- Các flow ghi, transaction và auditing đã được kiểm tra ở ranh giới phù hợp.
- Pagination, projection và truy vấn tùy biến có bằng chứng riêng thay vì được suy ra từ CRUD cơ bản.
- Hiệu năng của đường quan trọng nằm trong ngưỡng đã xác định hoặc có thay đổi được chấp nhận rõ ràng.
- Các chế độ JVM, AOT hoặc native cần triển khai đã được kiểm tra tương ứng.
- Mọi khác biệt còn lại có giải thích và người phụ trách biết ảnh hưởng của chúng.

Ví dụ, kết luận có thể là: “Candidate giữ đúng tập kết quả và thứ tự của các API danh sách, đọc được dữ liệu lịch sử và vượt kiểm tra projection trên native; chưa đánh giá tác vụ xuất báo cáo vì nó sử dụng một query riêng chưa nằm trong đợt này.” Cách ghi này thể hiện đúng mức bằng chứng và giúp xác định phần còn thiếu trước khi triển khai nếu báo cáo nằm trong phạm vi bắt buộc.

Không nên kết luận “nâng cấp an toàn” chỉ từ việc context khởi động, unit test dùng mock repository vượt kiểm tra hoặc một vài API trả HTTP 200. Những dấu hiệu đó có giá trị trong phạm vi hẹp nhưng chưa chứng minh ngữ nghĩa truy cập dữ liệu.

## 15. Những lỗi thường gặp khi thiết kế bài kiểm tra nâng cấp

1. **Chỉ dùng bảng rỗng.** Không kích hoạt mapping, projection và các biên dữ liệu; cần fixture có kết quả thực.
2. **Tự tạo lại toàn bộ dữ liệu bằng candidate.** Bỏ sót khả năng đọc dữ liệu lịch sử; cần giữ đầu vào từ định dạng cũ khi nó thuộc cam kết tương thích.
3. **So thứ tự của một truy vấn không có sort.** Dễ báo regression giả; chỉ so thứ tự khi hợp đồng có thứ tự xác định.
4. **Kiểm tra `Page` chỉ bằng số phần tử trong trang.** Có thể bỏ qua tổng số sai, thiếu dòng hoặc lặp dòng giữa các trang.
5. **Đọc lại từ cùng context sau ghi.** Có thể chỉ nhìn thấy trạng thái trong bộ nhớ; cần kiểm tra persistence theo cơ chế module.
6. **Dùng mock làm bằng chứng tích hợp.** Mock không thực thi parser, mapper, driver hoặc query engine.
7. **Thay cả môi trường và dependency mà không ghi nhận.** Khó giải thích khác biệt; cần biết biến nào đã đổi.
8. **Chỉ kiểm tra native startup.** Chưa chạy các nhánh repository và kiểu projection được người dùng sử dụng.
9. **Cập nhật expected result để làm bài kiểm tra xanh.** Có thể hợp thức hóa lỗi; phải hiểu thay đổi trước khi chấp nhận.
10. **Khóa chặt mọi chuỗi SQL.** Dễ báo lỗi cho tối ưu hóa hợp lệ; ưu tiên hợp đồng kết quả và ngân sách hiệu năng có ý nghĩa.

Kiểm thử nâng cấp Spring Data có giá trị khi nó nối được dependency với dữ liệu, truy vấn và hành vi mà ứng dụng cam kết. Hãy dùng fixture nhỏ để có đáp án chính xác, dữ liệu đại diện để quan sát thực tế, và artifact triển khai để kiểm tra những cơ chế chỉ xuất hiện trong môi trường đích.