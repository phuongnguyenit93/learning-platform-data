# Tính count từ cùng bộ lọc và các tối ưu phụ thuộc triển khai

## 1. Count phải trả lời cùng một câu hỏi với dữ liệu trang

Một trang có thể chứa đúng những đơn hàng người dùng được phép xem nhưng vẫn có metadata sai. Ví dụ, query dữ liệu lọc theo tenant và trạng thái, còn query count quên điều kiện tenant. Nội dung nhìn có vẻ đúng, nhưng tổng số phần tử và tổng số trang không còn mô tả cùng một tập dữ liệu.

Vấn đề này không được giải quyết bằng việc count chạy nhanh. Trước khi tối ưu, cần xác định count đang đếm đúng đối tượng, đúng phạm vi và đúng ngữ nghĩa bộ lọc.

Trong Spring Data Commons, `Page<T>` biểu đạt nội dung trang cùng thông tin tổng. Commons không quy định rằng mọi kho dữ liệu phải tạo cùng một câu SQL hoặc luôn thực hiện đúng hai query. Mô-đun repository, provider và kho dữ liệu quyết định cách lấy nội dung, sinh count và áp dụng tối ưu.

Bài học tập trung vào hai yêu cầu đi cùng nhau:

- Giữ query dữ liệu và count cùng hợp đồng về tập kết quả.
- Chỉ áp dụng tối ưu khi các giả định của cách triển khai thực sự đúng.

Các đoạn triển khai bằng Criteria và JPQL thuộc Spring Data JPA cùng Jakarta Persistence. Chúng minh họa nguyên tắc chung, không phải mã dùng nguyên trạng cho MongoDB, JDBC hoặc mọi repository khác.

## 2. Mô hình hóa tập cần đếm trước khi viết query

Giả sử tập các đơn hàng hợp lệ sau toàn bộ điều kiện lọc là S:

```text
S       = các đơn vị kết quả phù hợp trước phân trang
content = một đoạn của S sau khi áp dụng thứ tự, offset và size
total   = số đơn vị kết quả trong S
```

Trong ví dụ trả đơn hàng, đơn vị là một đơn hàng phân biệt. Nếu query trả nhóm theo trạng thái, đơn vị có thể là một nhóm. Nếu query trả dòng hàng, đơn vị lại là dòng hàng.

`content.size()` chỉ cho biết số phần tử của trang hiện tại. Nó không tự bằng total. Một trang có 20 phần tử có thể thuộc bộ lọc với 20, 21 hoặc hàng triệu phần tử.

### 2.1. “Cùng bộ lọc” bao gồm nhiều hơn các trường tìm kiếm trên giao diện

| Nhóm điều kiện | Ví dụ phải giữ nhất quán |
| --- | --- |
| Phạm vi dữ liệu | Tenant, khách hàng, tổ chức hoặc phạm vi được phép xem |
| Trạng thái vòng đời | Đã xóa mềm hay chưa, đã công bố hay chưa |
| Tiêu chí người dùng | Trạng thái đơn, khoảng thời gian, tổng tiền tối thiểu |
| Ngữ nghĩa giá trị | Null, tập rỗng, hoa/thường, chuẩn hóa dữ liệu |
| Điều kiện quan hệ | Có ít nhất một dòng hàng phù hợp, quan hệ bắt buộc |
| Điều kiện tổng hợp | Group, having hoặc quy tắc chọn nhóm |
| Ngữ nghĩa đơn vị kết quả | Entity phân biệt, giá trị phân biệt hay hàng join |

Một count quên điều kiện xóa mềm hoặc thay tập trạng thái rỗng thành “không lọc” cũng sai dù vẫn giữ tenant và ngày tháng.

### 2.2. Cùng ngữ nghĩa không có nghĩa cùng toàn bộ câu query

Query count thường không cần tải entity, fetch graph hoặc thứ tự chỉ dùng để hiển thị trang. Có thể thay biểu thức select bằng aggregate thích hợp và bỏ những thành phần không ảnh hưởng đến tập cần đếm.

Nhưng việc bỏ phải có lý do về ngữ nghĩa. Một join vừa phục vụ lọc vừa phục vụ tải dữ liệu không được xóa chỉ vì query count không cần trả thuộc tính của quan hệ đó.

Trong bài, total được hiểu là số kết quả phù hợp trước phân trang. Nếu một giới hạn hoặc phép chọn top là một phần riêng của yêu cầu nghiệp vụ, cần xác định lại S theo hợp đồng đó trước khi quyết định phần nào được bỏ.

## 3. Ví dụ count khai báo cùng phạm vi trong JPA

Giả sử `PurchaseOrder` là entity JPA có `id`, `tenantId`, `status`, `deleted`, `createdAt` và `total`. Tenant được xác định từ ngữ cảnh truy cập đáng tin cậy, không phải tùy ý tin một định danh do người dùng gửi.

Một query đơn giản theo tenant và trạng thái có thể khai báo:

```java
@Query(
    value = "select o from PurchaseOrder o "
          + "where o.tenantId = :tenantId "
          + "and o.deleted = false "
          + "and o.status = :status",
    countQuery = "select count(o) from PurchaseOrder o "
          + "where o.tenantId = :tenantId "
          + "and o.deleted = false "
          + "and o.status = :status"
)
Page<PurchaseOrder> findVisibleOrders(
        @Param("tenantId") Long tenantId,
        @Param("status") OrderStatus status,
        Pageable pageable);
```

Đây là phương thức trong một repository JPA phù hợp. Các kiểu sử dụng gồm `org.springframework.data.jpa.repository.Query`, `org.springframework.data.repository.query.Param`, `org.springframework.data.domain.Page` và `org.springframework.data.domain.Pageable`.

Trong ví dụ root không có join làm nhân số hàng, `count(o)` đếm các đơn phù hợp. Query dữ liệu và count giữ cùng ba điều kiện bắt buộc.

Cung cấp `countQuery` cho biết biểu thức đếm dùng khi cần. Nó không có nghĩa mọi lời gọi chắc chắn chạy count riêng bất kể các tối ưu hợp lệ của mô-đun.

### 3.1. Khi nào việc sao chép điều kiện bắt đầu nguy hiểm?

Nếu chỉ có vài điều kiện cố định, hai biểu thức có thể còn dễ đối chiếu. Khi thêm bộ lọc tùy chọn, điều kiện quyền xem hoặc join, việc sửa một biểu thức mà quên biểu thức kia trở nên dễ xảy ra.

Ví dụ dữ liệu thêm `createdAt < :createdBefore` nhưng count vẫn dùng cận trên bao gồm, một đơn đúng tại biên có thể làm hai phần khác nhau. Cả hai query đều chạy thành công nên lỗi không nhất thiết thể hiện bằng exception.

Với truy vấn động, nên chia sẻ quy tắc tạo điều kiện hoặc dùng abstraction của mô-đun phù hợp. Mục tiêu là giảm hai bản định nghĩa độc lập cho cùng một hợp đồng, không phải ép mọi query thành cùng một chuỗi.

## 4. Thiết kế bộ lọc có ngữ nghĩa rõ

Ví dụ tiếp theo tìm đơn hàng theo các quy tắc:

| Tiêu chí | Ngữ nghĩa |
| --- | --- |
| Tenant | Bắt buộc cho cả dữ liệu và count |
| Xóa mềm | Chỉ nhận `deleted = false` |
| `statuses == null` | Không thêm điều kiện trạng thái |
| `statuses` rỗng | Không trạng thái nào được chấp nhận, tập kết quả rỗng |
| `createdFrom` | Cận dưới bao gồm |
| `createdBefore` | Cận trên không bao gồm |
| `minTotal` | Cận dưới tổng tiền khi có giá trị |

Các ví dụ Java dưới dùng Java 17 trở lên. Entity có các thuộc tính tương ứng: id và tenantId là Long, status là OrderStatus, createdAt là Instant, total là BigDecimal, deleted là boolean. Mapping entity và tích hợp JPA là điều kiện của ứng dụng, không được tạo tự động chỉ từ các đoạn mã.

```java
package com.example.orders;

public enum OrderStatus {
    NEW, PAID, CANCELLED
}
```

Đối tượng tiêu chí:

```java
package com.example.orders;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;
import java.util.Set;

public record OrderFilter(
        Long tenantId,
        Set<OrderStatus> statuses,
        Instant createdFrom,
        Instant createdBefore,
        BigDecimal minTotal) {

    public OrderFilter {
        Objects.requireNonNull(tenantId, "tenantId");
        statuses = statuses == null ? null : Set.copyOf(statuses);

        if (createdFrom != null && createdBefore != null
                && !createdFrom.isBefore(createdBefore)) {
            throw new IllegalArgumentException("Khoảng thời gian không hợp lệ");
        }
        if (minTotal != null && minTotal.signum() < 0) {
            throw new IllegalArgumentException("minTotal phải không âm");
        }
    }
}
```

Sao chép tập trạng thái giúp giữ tiêu chí ổn định trong phạm vi sử dụng; `Set.copyOf` cũng từ chối phần tử null. Ngữ nghĩa null khác tập rỗng được giữ nguyên theo hợp đồng đã nêu.

Nếu bộ lọc dùng một mốc như “đến thời điểm bắt đầu request”, nên xác định mốc một lần rồi truyền cùng giá trị vào các query. Việc cùng truyền một mốc thời gian giúp giữ điều kiện nhất quán, nhưng không tự đóng băng toàn bộ trạng thái DB.

## 5. Chia sẻ quy tắc tạo predicate, không dùng lại đối tượng query

Criteria API tạo các đối tượng gắn với query và root đang xây dựng. Không nên lấy một Predicate từ query dữ liệu rồi gắn nguyên nó sang query count có root khác.

Hãy chia sẻ hàm tạo predicate và gọi lại hàm cho từng root:

```java
package com.example.orders;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

import jakarta.persistence.criteria.CriteriaBuilder;
import jakarta.persistence.criteria.Predicate;
import jakarta.persistence.criteria.Root;

final class OrderPredicates {
    private OrderPredicates() {
    }

    static List<Predicate> build(
            OrderFilter filter,
            CriteriaBuilder cb,
            Root<PurchaseOrder> order) {

        List<Predicate> result = new ArrayList<>();
        result.add(cb.equal(order.get("tenantId"), filter.tenantId()));
        result.add(cb.isFalse(order.<Boolean>get("deleted")));

        if (filter.statuses() != null) {
            if (filter.statuses().isEmpty()) {
                result.add(cb.disjunction());
            } else {
                result.add(order.get("status").in(filter.statuses()));
            }
        }
        if (filter.createdFrom() != null) {
            result.add(cb.greaterThanOrEqualTo(
                    order.<Instant>get("createdAt"), filter.createdFrom()));
        }
        if (filter.createdBefore() != null) {
            result.add(cb.lessThan(
                    order.<Instant>get("createdAt"), filter.createdBefore()));
        }
        if (filter.minTotal() != null) {
            result.add(cb.greaterThanOrEqualTo(
                    order.<BigDecimal>get("total"), filter.minTotal()));
        }
        return result;
    }
}
```

Trong trường hợp tập trạng thái rỗng, `cb.disjunction()` biểu đạt điều kiện sai; khi kết hợp cùng các điều kiện khác bằng AND, tập phù hợp rỗng ở cả hai query.

Hàm không thêm fetch, sort hoặc phân trang. Nó giữ trách nhiệm xác định điều kiện thành viên của tập kết quả. Mỗi lần gọi tạo các Predicate mới cho root được truyền vào.

Tên thuộc tính vẫn là chuỗi cần bảo trì cùng entity. Nếu dự án dùng static metamodel, có thể thay cách tham chiếu thuộc tính theo cấu hình đó. Tái sử dụng quy tắc lọc không tự làm mọi tên thuộc tính an toàn ở thời điểm biên dịch.

## 6. Những thành phần count có thể thay đổi và phải giữ

| Thành phần ở query dữ liệu | Khi xây count |
| --- | --- |
| Tenant và quyền xem | Giữ cùng phạm vi |
| Xóa mềm | Giữ cùng điều kiện |
| Predicate thời gian, trạng thái, số tiền | Giữ cùng ngữ nghĩa và giá trị tham số |
| Thứ tự chỉ để hiển thị | Thường không cần trong count của toàn bộ bộ lọc |
| Offset và size của trang | Không dùng chúng để cắt tổng cần đếm |
| Fetch chỉ phục vụ tải graph | Xem xét bỏ nếu chứng minh không thay đổi tập phù hợp |
| Join có tác dụng lọc | Không được bỏ nếu nó thay đổi điều kiện tồn tại |
| Distinct theo đơn vị kết quả | Giữ ngữ nghĩa phân biệt tương ứng khi đếm |
| Group và having | Xác định count cần đếm nhóm hay đối tượng đầu vào |

Không có quy tắc “count là query dữ liệu bỏ select và order by” đúng cho mọi cấu trúc. Nó có thể đúng với một query root đơn giản nhưng không đủ cho join, group hoặc truy vấn có phép chọn theo thứ hạng.

### 6.1. Phân biệt count hàng, count giá trị và count entity

- `count` trên hàng join có thể lớn hơn số đơn hàng.
- `count` trên một thuộc tính nullable có thể bỏ qua các giá trị null theo ngữ nghĩa aggregate.
- Đếm định danh đơn phân biệt khác với đếm số dòng hàng của các đơn ấy.
- Đếm nhóm trả lời câu hỏi khác với đếm số entity trước khi nhóm.

Nếu một đơn có ba dòng hàng phù hợp bộ lọc, query dữ liệu trả đơn đó một lần thì total cũng phải phản ánh một đơn, không phải ba hàng join.

Với mô hình đơn giản có khóa Long, một query thích hợp có thể cần `count(distinct o.id)`. Tuy nhiên, biểu thức chính xác vẫn phụ thuộc đơn vị kết quả và cấu trúc query. Không dùng count distinct như một cách che join sai hoặc một count nhóm chưa được thiết kế.

## 7. Fragment dùng cùng hàm tạo điều kiện cho dữ liệu và count

Interface fragment:

```java
package com.example.orders;

import org.springframework.data.domain.Page;

public interface OrderSearch {
    Page<PurchaseOrder> search(OrderFilter filter, int page, int size);
}
```

Implementation minh họa sử dụng utility `PageableExecutionUtils` của Commons ở phiên bản có API tương ứng:

```java
package com.example.orders;

import java.util.List;
import java.util.Objects;

import jakarta.persistence.EntityManager;
import jakarta.persistence.criteria.CriteriaBuilder;
import jakarta.persistence.criteria.CriteriaQuery;
import jakarta.persistence.criteria.Predicate;
import jakarta.persistence.criteria.Root;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.support.PageableExecutionUtils;
import org.springframework.transaction.annotation.Transactional;

public class OrderSearchImpl implements OrderSearch {
    private final EntityManager entityManager;

    public OrderSearchImpl(EntityManager entityManager) {
        this.entityManager = Objects.requireNonNull(entityManager);
    }

    @Override
    @Transactional(readOnly = true)
    public Page<PurchaseOrder> search(OrderFilter filter, int page, int size) {
        Objects.requireNonNull(filter, "filter");
        if (page < 0 || size < 1 || size > 100) {
            throw new IllegalArgumentException(
                    "page phải không âm; size phải trong [1, 100]");
        }

        Pageable pageable = PageRequest.of(page, size, Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")));
        long offset = pageable.getOffset();
        if (offset > Integer.MAX_VALUE) {
            throw new IllegalArgumentException(
                    "Offset vượt giới hạn của API JPA trong ví dụ");
        }

        CriteriaBuilder cb = entityManager.getCriteriaBuilder();
        CriteriaQuery<PurchaseOrder> dataQuery =
                cb.createQuery(PurchaseOrder.class);
        Root<PurchaseOrder> dataRoot = dataQuery.from(PurchaseOrder.class);
        List<Predicate> dataPredicates =
                OrderPredicates.build(filter, cb, dataRoot);

        dataQuery.select(dataRoot)
                .where(dataPredicates.toArray(new Predicate[0]))
                .orderBy(
                        cb.desc(dataRoot.get("createdAt")),
                        cb.desc(dataRoot.get("id")));

        List<PurchaseOrder> content = entityManager.createQuery(dataQuery)
                .setFirstResult((int) offset)
                .setMaxResults(size)
                .getResultList();

        return PageableExecutionUtils.getPage(
                content, pageable, () -> executeCount(filter));
    }

    private long executeCount(OrderFilter filter) {
        CriteriaBuilder cb = entityManager.getCriteriaBuilder();
        CriteriaQuery<Long> countQuery = cb.createQuery(Long.class);
        Root<PurchaseOrder> countRoot = countQuery.from(PurchaseOrder.class);
        List<Predicate> countPredicates =
                OrderPredicates.build(filter, cb, countRoot);

        countQuery.select(cb.count(countRoot))
                .where(countPredicates.toArray(new Predicate[0]));

        return entityManager.createQuery(countQuery).getSingleResult();
    }
}
```

Repository ghép fragment:

```java
package com.example.orders;

import org.springframework.data.repository.Repository;

public interface PurchaseOrderRepository
        extends Repository<PurchaseOrder, Long>, OrderSearch {
}
```

Ví dụ cần entity đã ánh xạ, EntityManager được tích hợp đúng, transaction management và cơ chế phát hiện fragment phù hợp. Trong cấu hình hậu tố `Impl`, tên `OrderSearchImpl` gắn với interface `OrderSearch`; việc đặt tên không thay thế cấu hình của mô-đun.

### 7.1. Những điểm được giữ có chủ đích

- Query dữ liệu và count nhận cùng một OrderFilter.
- Mỗi query có Root và Predicate riêng.
- Tenant, xóa mềm và toàn bộ bộ lọc động được tạo qua cùng quy tắc.
- Count không nhận offset và size của trang.
- Count không tải entity hoặc thêm thứ tự hiển thị.
- Query mẫu chỉ dùng root, nên `count(countRoot)` phù hợp đơn vị là đơn hàng.

Nếu thêm join làm nhân số hàng vào quy tắc lọc, phải đánh giá lại cả query dữ liệu lẫn biểu thức count. Có chung một hàm predicate không tự chứng minh select và count vẫn cùng đơn vị kết quả.

Giới hạn offset trong ví dụ xuất phát từ API phân trang JPA nhận giá trị int. Nó không phải giới hạn chung do Page của Commons áp đặt. Bài toán trang sâu cần được thiết kế theo khả năng kho dữ liệu thay vì ép kiểu một offset lớn làm mất giá trị.

## 8. LongSupplier cho phép trì hoãn count, không tự làm count rẻ

Lệnh gọi chính của utility có dạng:

```java
PageableExecutionUtils.getPage(content, pageable, () -> executeCount(filter));
```

Đối số cuối là một `LongSupplier`: cách lấy tổng khi utility cần nó. Lambda chưa chạy count chỉ vì nó được tạo.

Utility có thể tránh gọi supplier khi đủ điều kiện suy ra total từ nội dung và Pageable. Các nhánh tối ưu cụ thể cần được đối chiếu với phiên bản đang sử dụng. Không suy ra mọi query method của mọi mô-đun đều sử dụng đúng utility hoặc cùng chiến lược này.

Ngược lại, đoạn sau đã chạy count trước:

```java
long total = executeCount(filter);
Page<PurchaseOrder> result = PageableExecutionUtils.getPage(
        content, pageable, () -> total);
```

Dù utility không gọi supplier, chi phí count đã phát sinh để tạo biến total. Lambda chỉ trả lại một số đã tính.

### 8.1. Trì hoãn không đồng nghĩa chạy song song

`LongSupplier` trong ví dụ là một hàm đồng bộ được dùng khi utility cần giá trị. Nó không tự mở một tác vụ nền, không tự chạy song song với query dữ liệu và không tạo một transaction mới.

Nếu triển khai khác chọn đếm bất đồng bộ hoặc qua nguồn đọc khác, đó là một thiết kế riêng. Cần giữ an toàn ngữ cảnh truy cập, phạm vi dữ liệu và hợp đồng nhất quán tương ứng.

### 8.2. Utility không phân tích query của bạn

Utility nhận content, Pageable và cách lấy total. Nó không biết query có join, có khử lặp sau giới hạn hay đã lọc bỏ một phần tử ở Java hay không.

Do đó, nó không thể tự sửa:

- Count thiếu điều kiện tenant.
- Query dữ liệu dùng điều kiện khác supplier.
- List content đã bị lọc sau khi query.
- Dữ liệu bị cắt hoặc gom lại theo một đơn vị khác trước khi tạo Page.

Tối ưu metadata chỉ đúng khi content đầu vào đáp ứng những giả định của thuật toán và có quan hệ đúng với Pageable.

## 9. Khi nào có thể suy ra total từ nội dung?

Xét trường hợp query thực sự phân trang một tập kết quả đúng đơn vị, chưa bị lọc hoặc khử lặp sai sau giới hạn. Một số suy luận về mặt thuật toán là:

| Tình huống | Thông tin có thể suy ra |
| --- | --- |
| Trang đầu có ít phần tử hơn size | Có thể biết đã lấy hết tập phù hợp ở lần đọc ấy |
| Trang sau không rỗng nhưng ngắn hơn size | Có thể biết điểm cuối tại offset cộng số phần tử |
| Trang đủ size | Chưa biết còn hàng phía sau hay không chỉ từ content |
| Trang sau rỗng | Không tự biết total bằng 0, bằng offset hay nhỏ hơn offset bao nhiêu |
| Đã lấy toàn bộ tập phù hợp theo hợp đồng unpaged | Kích thước nội dung có thể phản ánh tổng nếu thực sự không có giới hạn ẩn |

Ví dụ offset 60 và nội dung cuối có 7 phần tử có thể cho total 67 khi các tiền đề phân trang đúng. Nhưng offset 60 và nội dung rỗng không cho phép khẳng định total 60: toàn bộ tập có thể chỉ có 12 phần tử.

Đây là giải thích điều kiện suy luận, không phải cam kết thứ tự các nhánh của mọi implementation. Cần dùng hợp đồng và hành vi utility của phiên bản được tích hợp.

### 9.1. Ít entity hơn size chưa luôn chứng minh đã ở phần cuối

Nếu query hoặc bước xử lý kết quả gom nhiều hàng SQL về cùng một entity sau khi giới hạn, số entity nhận được có thể ít hơn size dù còn dữ liệu phù hợp phía sau.

Tương tự, nếu lấy một trang rồi lọc quyền xem hoặc loại các phần tử ở Java, content ngắn không phải bằng chứng query đã chạm phần cuối.

Không được áp dụng suy luận “ngắn hơn size nghĩa là biết tổng” trước khi xác nhận giới hạn được áp dụng đúng ở đơn vị kết quả mong muốn. Bộ lọc xác định phần tử được phép trả cần được đặt ở ranh giới truy vấn hoặc thiết kế dữ liệu phù hợp.

### 9.2. Đừng lấy toàn bộ dữ liệu chỉ để tránh một count

Nếu một triển khai nạp toàn bộ S vào bộ nhớ rồi dùng `size()` để biết total, con số có thể đúng với tập đã nạp nhưng chi phí có thể lớn hơn nhiều so với lấy một trang và count hợp lý.

“Tổng đã có trong bộ nhớ” chỉ hữu ích khi dữ liệu ấy vốn cần được lấy theo hợp đồng. Nó không phải một lý do mặc định để bỏ phân trang thực sự.

## 10. Tối ưu thuộc tầng nào?

| Tầng | Trách nhiệm hoặc khả năng tối ưu | Điều không được mặc định |
| --- | --- | --- |
| Abstraction Page | Mang nội dung và metadata tổng | Tự kiểm chứng query count đúng |
| Pageable | Mô tả phần dữ liệu và thứ tự yêu cầu | Tự tính tổng |
| Utility tạo Page | Có thể suy ra tổng khi đủ điều kiện | Hiểu toàn bộ query và dữ liệu đã biến đổi |
| Mô-đun Spring Data | Chọn cách thực thi, sinh hoặc dùng query count | Mọi mô-đun sinh cùng dạng query |
| Provider hoặc client kho dữ liệu | Ánh xạ, dịch hoặc thực thi truy vấn | Mọi cấu trúc query đều được tối ưu giống nhau |
| Hệ quản trị | Chọn kế hoạch thực thi dựa trên query, index, thống kê | Count luôn rẻ hoặc luôn quét toàn bộ bảng |
| Ứng dụng | Cache, thống kê riêng, chọn Page hay Slice | Metadata cũ tự tương đương total hiện tại |

Một query root đơn giản có thể được suy ra count thuận lợi. Query native, projection phức tạp, group hoặc cấu trúc đặc thù có thể cần khai báo hay triển khai riêng tùy mô-đun và phiên bản.

Khi thay phiên bản, provider hoặc kho dữ liệu, số query thực thi hoặc hình dạng câu lệnh có thể đổi dù hợp đồng quan sát được vẫn cần giữ. Không nên viết quy tắc nghiệp vụ phụ thuộc vào tên lớp nội bộ hoặc một nhánh tối ưu quan sát được khi debug.

## 11. Những hướng giảm chi phí và đánh đổi tương ứng

### 11.1. Làm query count phù hợp hơn

Có thể xem xét loại bỏ phần tải dữ liệu không cần thiết, dùng biểu thức count đúng đơn vị, tránh join không có tác dụng lọc và kiểm tra index theo bộ lọc thực tế.

Mọi thay đổi phải giữ tập S. Bỏ một join mà trước đó có tác dụng yêu cầu tồn tại quan hệ có thể làm count nhanh hơn nhưng sai.

Index và kế hoạch thực thi cần được đánh giá trên dữ liệu đại diện. Không có một kiểu index chung làm mọi count nhanh, cũng không thể kết luận count luôn cần đọc toàn bộ bảng vật lý.

### 11.2. Không yêu cầu total nếu người gọi không cần

Nếu giao diện chỉ cần nội dung và còn phần tiếp theo, Slice có thể phù hợp hơn Page. Khi ấy không còn hợp đồng bắt buộc xác định tổng cho mỗi lần gọi.

Nhưng đổi kiểu biến từ Page sang Slice sau khi query Page đã chạy không loại bỏ count. Cần chọn đường query hoặc implementation phù hợp và điều chỉnh API nếu trước đó API công khai tổng.

### 11.3. Thống kê hoặc cache tổng cần phạm vi và thời điểm rõ

Nếu dùng cache, khóa phải bao phủ những yếu tố xác định tập kết quả: tenant, bộ lọc, quy tắc quyền xem và các trạng thái liên quan. Cache chỉ theo trạng thái đơn mà quên tenant sẽ không giữ đúng hợp đồng.

Ngoài khóa, cần chính sách cập nhật, vô hiệu hóa và độ trễ chấp nhận được. Một tổng từ thời điểm trước không tự tương đương count theo dữ liệu hiện tại.

Nếu dùng số ước lượng hoặc thống kê không đồng thời với nội dung, nên mô tả bằng metadata có tên và ý nghĩa rõ. Không điền một con số ước lượng vào total rồi để người tiêu thụ hiểu nó là count chính xác của cùng phạm vi đọc.

### 11.4. Ít câu lệnh không tự đồng nghĩa ít công việc

Một triển khai có thể kết hợp nội dung và tổng bằng cơ chế truy vấn đặc thù, chẳng hạn khả năng tổng hợp hoặc hàm cửa sổ của kho dữ liệu. Việc giảm số lượt trao đổi không làm việc xác định tổng tự miễn phí.

Còn phải xem số hàng được xét, chi phí sắp xếp, dữ liệu trả về và cách xử lý trường hợp trang không có hàng để mang metadata. Đây là lựa chọn phụ thuộc kho dữ liệu, không phải bảo đảm của Page trong Commons.

## 12. Cùng bộ lọc khác với cùng snapshot

### 12.1. Hai yêu cầu độc lập

Cùng bộ lọc bảo đảm hai query đặt cùng câu hỏi về tập phù hợp. Cùng snapshot bảo đảm chúng quan sát một trạng thái dữ liệu nhất quán theo hợp đồng đọc đã chọn.

Ngay cả khi predicate giống nhau hoàn toàn, một đơn mới được thêm hoặc đổi trạng thái giữa query dữ liệu và count vẫn có thể làm hai phần phản ánh các thời điểm khác nhau.

Annotation transaction read-only trong ví dụ không tự bảo đảm mọi DB và mức isolation cung cấp cùng snapshot cho mọi câu lệnh. Cần đối chiếu cấu hình transaction, nguồn đọc và đặc tính kho dữ liệu khi yêu cầu này quan trọng.

### 12.2. Đổi nguồn count cũng là một thay đổi hợp đồng đọc

Nếu dữ liệu trang đến từ một nguồn còn count đến từ cache hoặc nguồn đọc có độ trễ, predicate giống nhau vẫn chưa đủ. Cần xác định trạng thái dữ liệu mà mỗi nguồn phản ánh.

Tương tự, dùng một mốc thời gian cố định trong filter chỉ cố định điều kiện so sánh với mốc đó. Nó không ngăn một bản ghi đáp ứng điều kiện được ghi thêm sau khi query đầu đã chạy.

### 12.3. Metadata không thay thế việc đọc lại khi cần

Total phục vụ hợp đồng phân trang và thống kê của lần đọc. Nó không bảo đảm một đơn cụ thể vẫn còn tồn tại hoặc còn phù hợp khi người dùng thực hiện thao tác tiếp theo.

Nếu cần quyết định một thay đổi nghiệp vụ, vẫn phải áp dụng điều kiện và cơ chế nhất quán của thao tác ấy. Không dùng total của một trang trước để suy ra trạng thái hiện tại của từng bản ghi.

## 13. Kiểm chứng bộ lọc và đường count thực sự

Một bộ dữ liệu kiểm chứng nên có các bản ghi dễ làm lộ điều kiện bị quên. Ví dụ filter là tenant 1, trạng thái PAID, khoảng thời gian từ đầu tháng 1 đến trước đầu tháng 2, tổng tiền tối thiểu 100.

Các thời điểm biên trong bảng được hiểu là 00:00 UTC của ngày ghi tương ứng:

| Đơn | Tenant | Status | Deleted | CreatedAt | Total | Phù hợp? |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | PAID | false | 01-01 | 100 | Có |
| 2 | 1 | PAID | false | 01-02 | 100 | Không, đúng cận trên bị loại |
| 3 | 2 | PAID | false | 15-01 | 100 | Không, tenant khác |
| 4 | 1 | PAID | true | 15-01 | 100 | Không, đã xóa mềm |
| 5 | 1 | NEW | false | 15-01 | 100 | Không, trạng thái khác |
| 6 | 1 | PAID | false | 15-01 | 90 | Không, dưới cận tiền |

Dữ liệu trong bảng thuộc cùng một năm minh họa; cách ghi ngày là ngày-tháng. Với các điều kiện ấy, total mong muốn là 1.

### 13.1. Một Page đúng total chưa chứng minh count query đúng

Nếu trang đầu chỉ có một phần tử trong khi size là 20, một đường tối ưu có thể suy ra total và không gọi supplier. Khi đó kết quả total bằng 1 chưa chứng minh câu query count đã được thực thi đúng.

Cần có ca kiểm chứng đi qua đường thực sự xác định tổng bằng count, hoặc kiểm chứng riêng phần thực thi count theo thiết kế phù hợp. Quan sát query thực tế giúp phân biệt nhánh suy luận với nhánh đếm.

Không biến điều này thành assertion cứng rằng mọi Page luôn phải có đúng hai query. Mục tiêu là kiểm chứng cả tính đúng của count và tính hợp lệ của tối ưu, không khóa chặt implementation vào một số câu lệnh ở mọi trường hợp.

### 13.2. Ma trận tình huống cần bao phủ

| Ca | Mục tiêu kiểm chứng |
| --- | --- |
| Mỗi điều kiện loại đúng một bản ghi | Dữ liệu và count không lệch predicate |
| Statuses null | Cùng hiểu là không thêm bộ lọc trạng thái |
| Statuses rỗng | Cùng hiểu là tập kết quả rỗng |
| Bằng cận thời gian và cận tiền | Giữ đúng bao gồm hoặc không bao gồm |
| Trang đầu ngắn | Suy luận total đúng khi đủ tiền đề |
| Trang đủ size | Đường xác định tổng không dựa vào kích thước trang đơn thuần |
| Trang sau rỗng | Không gán total bằng offset hoặc 0 một cách tùy tiện |
| Join có nhiều hàng cho một entity | Count đúng đơn vị kết quả |
| Group và having | Count đúng số nhóm cần phân trang |
| Content bị lọc sau query | Phát hiện suy luận total không còn hợp lệ |
| Cache hoặc nguồn count riêng | Phạm vi và độ trễ được thể hiện đúng hợp đồng |
| Dữ liệu thay đổi giữa hai query | Hành vi phù hợp mức nhất quán đã chọn |

Mock repository trả sẵn một Page chỉ kiểm chứng được cách service dùng Page đó. Nó không chứng minh query count, Criteria, mapping hoặc kế hoạch thực thi đang đúng.

## 14. Quy trình tối ưu một đường phân trang

1. **Viết rõ tập S và đơn vị kết quả.** Xác định total là số đơn, số dòng, giá trị phân biệt hay số nhóm.
2. **Liệt kê toàn bộ điều kiện thành viên.** Bao gồm tenant, quyền xem, xóa mềm và ngữ nghĩa null/tập rỗng.
3. **Giữ một định nghĩa quy tắc lọc khi có thể.** Tạo Predicate mới cho mỗi query hoặc dùng abstraction tương ứng của mô-đun.
4. **Kiểm chứng count trước khi đo tốc độ.** Count nhanh nhưng sai không phải một giải pháp.
5. **Xác định count có thực sự chạy không.** Đừng đo một ca luôn bỏ qua count rồi suy ra chi phí của mọi trang.
6. **Tách chi phí nội dung, tổng và mapping.** Offset sâu hoặc N+1 có thể là phần tốn kém khác.
7. **Chọn tối ưu theo khả năng triển khai.** Count riêng, supplier, index, Slice, thống kê hoặc cache đều có điều kiện áp dụng.
8. **Ghi rõ đánh đổi về thông tin và nhất quán.** Không biến số ước lượng thành tổng chính xác hoặc thay đổi phạm vi lọc để đạt thời gian thấp hơn.
9. **Giữ kiểm chứng theo hợp đồng khi nâng cấp.** Hình dạng query có thể đổi, nhưng tập kết quả và metadata vẫn phải có ý nghĩa đúng.

## 15. Tình huống tự đánh giá

### A. Nội dung đúng, total của tenant khác

Query dữ liệu có tenant và trạng thái. Count chỉ lọc trạng thái. Người dùng thấy đúng đơn hàng nhưng tổng số trang lớn bất thường.

Hãy xác định hợp đồng bị vi phạm, dữ liệu kiểm chứng làm lộ lỗi và lý do không thể chỉ sửa metadata ở giao diện.

### B. Tái sử dụng nguyên Predicate

Một fragment xây Predicate cho root của query dữ liệu rồi dùng nguyên các đối tượng đó trong query count có root khác.

Giải thích vì sao nên chia sẻ hàm tạo quy tắc thay vì các đối tượng Criteria đã gắn với query. Nêu phần nào của query vẫn cần được thiết kế riêng.

### C. Supplier nhưng count vẫn chạy mọi lần

Người viết tính `long total = executeCount(filter)` rồi truyền `() -> total` cho utility tạo Page.

Chỉ ra thời điểm chi phí đã phát sinh và cách truyền hành vi lấy tổng thay vì giá trị tính sẵn.

### D. Ít entity hơn size do khử lặp

Query có join trả nhiều hàng cho một entity, sau đó kết quả được gom còn ít entity hơn size. Một helper suy ra đã tới trang cuối.

Xác định tiền đề đã sai và cách kiểm tra lại đơn vị phân trang, giới hạn và count.

### E. Bài kiểm chứng không hề chạy count

Bộ dữ liệu chỉ có hai bản ghi, size là 20. Page luôn có total đúng, nhưng khi triển khai với nhiều trang thì count bị lỗi.

Giải thích đường tối ưu có thể đã che phần chưa được kiểm chứng. Đề xuất những ca cần bổ sung mà không khóa mọi phiên bản vào giả định luôn có hai query.

### F. Giữ predicate nhưng đổi count sang cache

Nội dung được đọc từ dữ liệu hiện tại, count lấy từ cache theo tenant và trạng thái, nhưng filter còn có khoảng thời gian và tổng tiền.

Nêu các yếu tố còn thiếu trong khóa hoặc hợp đồng cache. Phân biệt việc sửa khóa với việc giải quyết độ trễ và tính nhất quán của total.