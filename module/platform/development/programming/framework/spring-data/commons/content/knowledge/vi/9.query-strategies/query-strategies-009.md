# Chọn truy vấn khai báo hay fragment khi yêu cầu vượt khả năng suy diễn

## 1. Khi tên phương thức không còn phù hợp

Spring Data cho phép mô tả nhiều truy vấn bằng tên phương thức repository. Cơ chế này hữu ích khi điều kiện ngắn, cấu trúc ổn định và các toán tử được mô-đun kho dữ liệu hỗ trợ. Ví dụ, tìm đơn hàng theo khách hàng và trạng thái có thể được diễn đạt trực tiếp bằng tên.

Khi yêu cầu phát triển, vấn đề không chỉ là tên phương thức dài. Truy vấn có thể cần gom nhóm điều kiện, tham số tùy chọn, join, phép tổng hợp, hàm của kho dữ liệu hoặc nhiều bước thực thi. Lúc đó cần chọn hình thức biểu đạt khác thay vì tiếp tục ghép thêm từ vào tên phương thức.

Trong phạm vi Spring Data Commons, hai hướng quan trọng là:

- **Truy vấn khai báo:** mô tả truy vấn bằng cơ chế khai báo mà mô-đun hỗ trợ, chẳng hạn annotation hoặc named query.
- **Repository fragment:** khai báo hợp đồng tùy chỉnh, cung cấp mã triển khai và ghép hợp đồng đó vào repository.

Commons cung cấp abstraction dùng chung về repository, query method, kiểu kết quả và composition. Ngôn ngữ truy vấn, annotation cụ thể và cách truy cập dữ liệu thuộc mô-đun tích hợp. Lựa chọn phải đồng thời phù hợp yêu cầu và khả năng của kho dữ liệu.

Các ví dụ triển khai trong bài dùng Spring Data JPA. Chúng cần được chuyển sang API tương ứng nếu dùng MongoDB, JDBC hoặc repository reactive.

## 2. Ba lý do để rời derived query

### 2.1. Vẫn suy diễn được nhưng khó đọc

Xét tên phương thức:

```java
findByCustomerIdAndStatusAndTotalGreaterThanEqualOrderByCreatedAtDescIdDesc
```

Tên này có thể phù hợp cú pháp suy diễn nếu thuộc tính và toán tử được mô-đun hỗ trợ. Tuy nhiên, khi người đọc phải tách nhiều thành phần để hiểu một thao tác phổ biến, truy vấn khai báo có thể giúp thể hiện điều kiện và thứ tự rõ hơn.

Không có một số ký tự chung quyết định khi nào phải đổi cách viết. Tiêu chí hữu ích hơn là khả năng đọc, kiểm tra đúng sai và sửa yêu cầu mà không sinh ra hàng loạt phương thức gần giống nhau.

### 2.2. Biểu thức vượt khả năng suy diễn

Yêu cầu có thể cần một phép tổng hợp chuyên biệt, truy vấn con, cấu trúc điều kiện phức tạp hoặc hàm đặc thù mà tên phương thức không biểu đạt rõ hoặc không được hỗ trợ.

Điều đó chưa có nghĩa phải viết fragment. Nếu ngôn ngữ khai báo và cơ chế thực thi của mô-đun đáp ứng được yêu cầu, khai báo vẫn là lựa chọn thích hợp.

### 2.3. Hình dạng truy vấn thay đổi theo đầu vào

Một màn hình tìm kiếm với nhiều bộ lọc tùy chọn có thể cần các tập predicate, join hoặc projection khác nhau. Viết một phương thức cho từng tổ hợp làm số trường hợp tăng nhanh khi thêm bộ lọc.

Khi cần thuật toán xây dựng truy vấn hoặc nhiều bước truy cập dữ liệu, fragment có thể cung cấp ranh giới rõ ràng. Nhưng nếu mô-đun đã có abstraction truy vấn động phù hợp, như Specification trong JPA, có thể dùng abstraction đó mà không nhất thiết tự triển khai toàn bộ fragment.

| Tình huống | Câu hỏi cần trả lời |
| --- | --- |
| Tên dài nhưng cấu trúc cố định | Khai báo truy vấn có dễ đọc và kiểm chứng hơn không? |
| Cần cấu trúc không suy diễn được | Ngôn ngữ khai báo của mô-đun có biểu đạt được không? |
| Nhiều bộ lọc động | Có abstraction xây dựng predicate phù hợp hay cần mã riêng? |
| Nhiều bước thực thi | Đây là thuật toán truy cập dữ liệu hay quy trình nghiệp vụ? |
| Tính năng riêng của hệ quản trị | Khai báo đã hỗ trợ hay cần client/API chuyên biệt? |

## 3. Query lookup strategy và composition là hai quyết định khác nhau

Spring Data có khái niệm chiến lược tra cứu truy vấn. Trong những mô-đun hỗ trợ các chiến lược này, ý nghĩa chung là:

| Chiến lược | Cách xử lý về mặt khái niệm |
| --- | --- |
| `CREATE` | Tạo truy vấn từ tên phương thức theo cơ chế của mô-đun |
| `USE_DECLARED_QUERY` | Tìm truy vấn khai báo; không tìm thấy thì không tự chuyển sang suy diễn |
| `CREATE_IF_NOT_FOUND` | Tìm truy vấn khai báo trước; nếu không có thì thử tạo từ tên phương thức |

Cách cấu hình, mức hỗ trợ và thời điểm phát hiện lỗi phụ thuộc mô-đun, phiên bản và chế độ khởi tạo repository. Cần đối chiếu hợp đồng của phiên bản dự án đang dùng thay vì giả định mọi query đều được kiểm tra ở cùng một thời điểm.

Hai điểm cần giữ rõ:

1. **Không tìm thấy khai báo khác với khai báo bị lỗi.** Không nên kỳ vọng một truy vấn đã khai báo nhưng sai cú pháp sẽ tự bị bỏ qua để framework thử derived query.
2. **Fragment là cơ chế composition.** Nó không phải bước dự phòng tự sinh sau khi khai báo và suy diễn thất bại. Ứng dụng phải cung cấp interface, implementation và cấu hình ghép phù hợp.

Nếu fragment không được ghép đúng, framework có thể cố xử lý phương thức ấy như query method và báo lỗi liên quan tên thuộc tính. Khi chẩn đoán, cần kiểm tra composition thay vì chỉ sửa tên phương thức.

## 4. Khi nào nên dùng truy vấn khai báo?

Truy vấn khai báo phù hợp khi yêu cầu có thể được mô tả bằng một biểu thức ổn định:

- Điều kiện và hình dạng kết quả đã rõ.
- Số nhánh theo tham số còn dễ kiểm soát.
- Mô-đun ánh xạ được tham số và kết quả theo hợp đồng mong muốn.
- Phân trang, sắp xếp và đếm có thể được mô tả đúng.
- Đọc truy vấn trực tiếp giúp người bảo trì hiểu thao tác.

Tên phương thức có thể tập trung vào ý định; annotation hoặc named query chứa biểu thức thực thi. Không cần lặp lại toàn bộ điều kiện đã khai báo trong một tên phương thức dài.

Không có một annotation `@Query` dùng hoán đổi cho mọi mô-đun. `org.springframework.data.jpa.repository.Query` thuộc JPA; nội dung có thể là JPQL hoặc truy vấn native theo cấu hình. Annotation cùng tên ở mô-đun khác có thể nhận ngôn ngữ và thuộc tính khác.

## 5. Ví dụ truy vấn khai báo với JPA

Giả sử entity JPA mang tên `PurchaseOrder` có các thuộc tính:

| Thuộc tính | Kiểu Java | Ý nghĩa |
| --- | --- | --- |
| `id` | `Long` | Định danh đơn hàng |
| `customerId` | `Long` | Định danh khách hàng |
| `status` | `OrderStatus` | Trạng thái |
| `total` | `BigDecimal` | Tổng tiền |
| `createdAt` | `Instant` | Thời điểm tạo, không rỗng trong mô hình này |

Các ví dụ giả định entity đã có ánh xạ hợp lệ và repository scanning đã được cấu hình. Chúng tập trung vào chiến lược truy vấn, không cung cấp toàn bộ ứng dụng hoặc cấu trúc bảng.

Yêu cầu là tìm đơn của một khách hàng, có trạng thái xác định và tổng tiền tối thiểu. Kết quả cần một trang dữ liệu cùng tổng số đơn thỏa điều kiện.

```java
import java.math.BigDecimal;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.Repository;
import org.springframework.data.repository.query.Param;

public interface PurchaseOrderRepository
        extends Repository<PurchaseOrder, Long> {

    @Query(
        value = "select o from PurchaseOrder o "
              + "where o.customerId = :customerId "
              + "and o.status = :status "
              + "and o.total >= :minTotal "
              + "order by o.createdAt desc, o.id desc",
        countQuery = "select count(o) from PurchaseOrder o "
              + "where o.customerId = :customerId "
              + "and o.status = :status "
              + "and o.total >= :minTotal"
    )
    Page<PurchaseOrder> findForCustomer(
            @Param("customerId") Long customerId,
            @Param("status") OrderStatus status,
            @Param("minTotal") BigDecimal minTotal,
            Pageable pageable);
}
```

Có thể gọi với yêu cầu trang không bổ sung sort:

```java
Pageable pageable = PageRequest.of(0, 20);
Page<PurchaseOrder> result = repository.findForCustomer(
        customerId, OrderStatus.PAID, new BigDecimal("100000"), pageable);
```

Đoạn gọi dùng `org.springframework.data.domain.PageRequest`. Service phải xác định hoặc kiểm tra quyền đối với `customerId` trước khi gọi.

Những điểm quan trọng:

- `PurchaseOrder`, `customerId` và `createdAt` trong JPQL là tên entity và thuộc tính, không phải tên bảng và cột SQL.
- `@Param` liên kết tham số với biểu thức truy vấn; đầu vào không được nối trực tiếp thành JPQL.
- Tên `findForCustomer` diễn đạt ý định, còn điều kiện thực tế nằm trong khai báo.
- `createdAt desc, id desc` cho thứ tự xác định khi nhiều đơn cùng thời điểm tạo. Ví dụ dùng khóa `Long` làm tiêu chí phụ.
- `countQuery` có cùng điều kiện lọc nhưng không cần sắp xếp. Nó phục vụ việc lấy tổng khi cơ chế phân trang cần truy vấn đếm.
- Không nên giả định một phương thức trả `Page` luôn chạy đúng hai truy vấn; có trường hợp framework suy ra thông tin trang mà không cần đếm riêng.

Các tham số lọc trong ví dụ phải có giá trị hợp lệ. Truyền `null` cho `status` không tự có nghĩa bỏ điều kiện trạng thái. Ngữ nghĩa tham số phải được thiết kế rõ.

Truy vấn này đủ gọn để giữ ở dạng khai báo. Tạo fragment chỉ để chuyển nguyên chuỗi JPQL sang `EntityManager` chưa tạo thêm lợi ích cụ thể.

## 6. Khi khai báo bắt đầu khó bảo trì

Yêu cầu mới có thể cho phép chọn tập trạng thái, bỏ bộ lọc tổng tiền, dùng cận thời gian tùy chọn và chỉ trả một số đơn mới nhất. Một cách xử lý là viết nhiều nhánh theo dạng:

```text
tham_số_không_có OR điều_kiện_theo_tham_số
```

Cách này có thể hợp lý nếu ít nhánh, kiểu tham số phù hợp và kế hoạch thực thi chấp nhận được. Khi số nhánh tăng, cần đánh giá:

- Ngữ nghĩa của tham số không có giá trị còn rõ không?
- Danh sách rỗng được xử lý đúng với provider và kho dữ liệu không?
- Một bộ lọc có làm xuất hiện join hay thay đổi projection không?
- Query đếm còn giữ đúng mọi điều kiện không?
- Những nhánh `OR` ảnh hưởng thế nào đến kế hoạch thực thi trên dữ liệu thật?
- Quy tắc lọc có đang bị sao chép giữa nhiều truy vấn không?

Không nên kết luận mọi truy vấn có `OR` đều không sử dụng được index. Khả năng tối ưu phụ thuộc hệ quản trị, dữ liệu, index và biểu thức cụ thể. Viết fragment không tự làm truy vấn nhanh hơn.

Nếu chủ yếu cần tổ hợp predicate, hãy xem abstraction truy vấn động sẵn có của mô-đun. Specification thuộc Spring Data JPA; nó không phải khả năng chung tự có của mọi repository. Query by Example cũng có giới hạn và không thay thế một ngôn ngữ truy vấn tùy ý.

Fragment có giá trị khi đóng gói phần xây dựng hoặc thực thi tùy chỉnh mà các cơ chế sẵn có không diễn đạt gọn và đúng.

## 7. Thiết kế hợp đồng fragment trước khi viết query

Với tìm kiếm động, hợp đồng cần nói rõ cả ý nghĩa bộ lọc lẫn dạng kết quả. Trong ví dụ tiếp theo, quy tắc là:

| Đầu vào | Ngữ nghĩa |
| --- | --- |
| `customerId` | Bắt buộc; do service cung cấp sau khi xác định phạm vi được phép |
| `statuses == null` | Không thêm điều kiện trạng thái |
| `statuses` rỗng | Không có trạng thái được chấp nhận, trả kết quả rỗng |
| `minTotal == null` | Không có cận dưới tổng tiền |
| `minTotal < 0` | Đầu vào không hợp lệ theo hợp đồng này |
| `createdFrom` | Cận dưới bao gồm: `createdAt >= createdFrom` |
| `createdBefore` | Cận trên không bao gồm: `createdAt < createdBefore` |
| Cùng có hai cận thời gian | Cận dưới phải nhỏ hơn cận trên |
| `limit` | Từ 1 đến 100, trả nhiều nhất số phần tử này |
| Kết quả | Danh sách mới nhất trước, không có thông tin tổng |

Phân biệt `null` với tập rỗng giúp tránh một lỗi quan trọng: người gọi muốn không chấp nhận trạng thái nào nhưng implementation lại bỏ điều kiện và trả mọi trạng thái.

Giới hạn và thứ tự cũng là hợp đồng công khai, không nên chỉ là chi tiết người viết implementation biết.

## 8. Fragment xây dựng predicate bằng JPA Criteria

Phần này dùng Java 17 trở lên và Jakarta Persistence. Dự án dùng namespace persistence hoặc nền tảng khác cần điều chỉnh theo phiên bản tích hợp. `EntityManager` và Criteria API ở đây thuộc JPA, không phải API truy vấn chung của Commons.

Các kiểu đặt trong package `com.example.orders`; entity `PurchaseOrder` có các thuộc tính đã mô tả. Khi triển khai, mỗi kiểu `public` nằm trong file riêng. Ví dụ khai báo ở phần 5 cũng có thể đặt vào package này với các kiểu mô hình tương ứng.

### 8.1. Đối tượng tiêu chí

```java
package com.example.orders;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;
import java.util.Set;

public record OrderSearchCriteria(
        Long customerId,
        Set<OrderStatus> statuses,
        BigDecimal minTotal,
        Instant createdFrom,
        Instant createdBefore) {

    public OrderSearchCriteria {
        Objects.requireNonNull(customerId, "customerId");

        // null: không lọc. Tập khác null được sao chép.
        // Set.copyOf cũng từ chối phần tử null.
        statuses = statuses == null ? null : Set.copyOf(statuses);

        if (minTotal != null && minTotal.signum() < 0) {
            throw new IllegalArgumentException("minTotal phải không âm");
        }
        if (createdFrom != null && createdBefore != null
                && !createdFrom.isBefore(createdBefore)) {
            throw new IllegalArgumentException("Khoảng thời gian không hợp lệ");
        }
    }
}
```

Enum minh họa:

```java
package com.example.orders;

public enum OrderStatus {
    NEW, PAID, SHIPPED, CANCELLED
}
```

Mô hình thực tế phải thống nhất enum với cách lưu trữ và quy tắc chuyển trạng thái. Fragment tìm kiếm không tự quyết định quy trình nghiệp vụ của đơn hàng.

### 8.2. Interface fragment

```java
package com.example.orders;

import java.util.List;

public interface PurchaseOrderSearch {
    List<PurchaseOrder> searchLatest(OrderSearchCriteria criteria, int limit);
}
```

Interface diễn đạt nhu cầu người gọi, không công khai `EntityManager`, Criteria API hoặc query builder riêng của provider.

### 8.3. Implementation

```java
package com.example.orders;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import jakarta.persistence.EntityManager;
import jakarta.persistence.criteria.CriteriaBuilder;
import jakarta.persistence.criteria.CriteriaQuery;
import jakarta.persistence.criteria.Predicate;
import jakarta.persistence.criteria.Root;
import org.springframework.transaction.annotation.Transactional;

public class PurchaseOrderSearchImpl implements PurchaseOrderSearch {
    private final EntityManager entityManager;

    public PurchaseOrderSearchImpl(EntityManager entityManager) {
        this.entityManager = Objects.requireNonNull(entityManager);
    }

    @Override
    @Transactional(readOnly = true)
    public List<PurchaseOrder> searchLatest(
            OrderSearchCriteria criteria, int limit) {

        Objects.requireNonNull(criteria, "criteria");
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("limit phải nằm trong [1, 100]");
        }

        if (criteria.statuses() != null && criteria.statuses().isEmpty()) {
            return List.of();
        }

        CriteriaBuilder cb = entityManager.getCriteriaBuilder();
        CriteriaQuery<PurchaseOrder> query =
                cb.createQuery(PurchaseOrder.class);
        Root<PurchaseOrder> order = query.from(PurchaseOrder.class);
        List<Predicate> predicates = new ArrayList<>();

        predicates.add(cb.equal(
                order.get("customerId"), criteria.customerId()));

        if (criteria.statuses() != null) {
            predicates.add(order.get("status").in(criteria.statuses()));
        }
        if (criteria.minTotal() != null) {
            predicates.add(cb.greaterThanOrEqualTo(
                    order.<BigDecimal>get("total"), criteria.minTotal()));
        }
        if (criteria.createdFrom() != null) {
            predicates.add(cb.greaterThanOrEqualTo(
                    order.<Instant>get("createdAt"), criteria.createdFrom()));
        }
        if (criteria.createdBefore() != null) {
            predicates.add(cb.lessThan(
                    order.<Instant>get("createdAt"), criteria.createdBefore()));
        }

        query.select(order)
                .where(predicates.toArray(new Predicate[0]))
                .orderBy(
                        cb.desc(order.get("createdAt")),
                        cb.desc(order.get("id")));

        return entityManager.createQuery(query)
                .setMaxResults(limit)
                .getResultList();
    }
}
```

Điều kiện khách hàng luôn được thêm, không phụ thuộc người gọi có chọn bộ lọc tùy chọn hay không. Giá trị đầu vào đi qua Criteria API, không được nối vào chuỗi JPQL.

Tên thuộc tính như `"createdAt"` vẫn là chuỗi phải bảo trì cùng entity. Criteria API không tự làm mọi tên thuộc tính thành an toàn ở thời điểm biên dịch. Dự án có thể dùng static metamodel nếu đã có cấu hình sinh và sử dụng metamodel phù hợp.

`@Transactional(readOnly = true)` thuộc cơ chế transaction của Spring. Ví dụ giả định quản lý transaction đã được bật và implementation được Spring quản lý. Annotation này không cấp quyền và không chứng minh cơ sở dữ liệu sẽ chặn mọi lệnh ghi trong mọi cấu hình.

### 8.4. Ghép vào repository

```java
package com.example.orders;

import java.util.Optional;
import org.springframework.data.repository.Repository;

public interface PurchaseOrderRepository
        extends Repository<PurchaseOrder, Long>, PurchaseOrderSearch {

    Optional<PurchaseOrder> findById(Long id);
}
```

Với cấu hình dùng hậu tố `Impl`, tên `PurchaseOrderSearchImpl` gắn với interface fragment `PurchaseOrderSearch`. Cần đặt implementation trong phạm vi phát hiện phù hợp hoặc đăng ký theo cơ chế custom implementation của mô-đun.

Đây là phiên bản interface minh họa việc ghép fragment, thay cho khai báo interface riêng ở phần 5. Trong ứng dụng có thể giữ thêm `findForCustomer` cùng annotation của nó trên interface này. Một repository có thể đồng thời chứa phương thức suy diễn, khai báo và fragment.

Để chạy ví dụ còn cần entity đã ánh xạ, `EntityManager` được tích hợp đúng, cấu hình JPA và quản lý transaction. Tên implementation đúng không thay thế các bước này.

### 8.5. Phạm vi của kết quả

Fragment xây dựng một query với predicate thay đổi, giới hạn số hàng và sắp xếp ổn định. Nó không tính tổng, không hỗ trợ offset và không tạo `Page`.

Danh sách có đúng `limit` phần tử không chứng minh còn dữ liệu phía sau. Nếu cần thông tin còn phần tiếp theo, phải có cơ chế tương ứng, chẳng hạn đọc thêm một phần tử rồi trả một hợp đồng phù hợp.

`customerId` bắt buộc giúp giữ phạm vi lọc nhưng không tự bảo đảm phân quyền. Service phải xác định khách hàng được phép truy cập, thay vì nhận tùy ý định danh từ request rồi coi việc có điều kiện là đã an toàn.

`findById` cũng không tự thừa hưởng điều kiện khách hàng của `searchLatest`. Nếu chính sách phải áp dụng cho mọi truy cập hoặc mọi tenant, cần thiết kế và kiểm chứng các đường truy cập khác.

## 9. So sánh theo bản chất công việc

Hai ví dụ trên không phải cùng một hợp đồng được viết theo hai kiểu. Khai báo trả trang cùng tổng; fragment trả một danh sách giới hạn theo bộ lọc động và không tính tổng. Khi so sánh hai cách trong dự án, cần giữ hợp đồng tương đương để đánh giá công bằng.

| Tiêu chí | Nghiêng về khai báo | Nghiêng về fragment |
| --- | --- | --- |
| Cấu trúc | Ổn định, một biểu thức dễ đọc | Có thuật toán tạo query hoặc nhiều nhánh cấu trúc |
| Tham số tùy chọn | Ít, ý nghĩa rõ | Nhiều, cần thêm hoặc bỏ predicate/join có chọn lọc |
| Khả năng kho dữ liệu | Annotation hoặc named query đã hỗ trợ | Cần API/client chưa được đường khai báo bao phủ |
| Hình dạng kết quả | Ánh xạ được bằng cơ chế có sẵn | Cần kết hợp hoặc xử lý tùy chỉnh có ranh giới rõ |
| Bước thực thi | Một query cùng count nếu cần | Nhiều bước truy cập dữ liệu có chủ đích |
| Khả năng bảo trì | Câu truy vấn thể hiện rõ yêu cầu | Mã xây dựng dễ hiểu hơn khai báo quá nhiều nhánh |
| Transaction | Phải đúng với cấu hình phương thức và mô-đun | Phải giữ đúng hợp đồng cho thao tác tùy chỉnh |
| Hiệu năng | Cần đo trên truy vấn thực tế | Cũng cần đo trên truy vấn thực tế |

Một SQL phức tạp nhưng cố định có thể phù hợp dạng khai báo native nếu mô-đun hỗ trợ tham số, ánh xạ và phân trang cần thiết. Một truy vấn đơn giản nhưng cấu trúc thay đổi theo nhiều lựa chọn lại có thể phù hợp query builder.

Độ dài SQL hoặc số dòng Java không phải thước đo duy nhất. Hãy đánh giá tính đúng, khả năng đọc, mức kiểm soát cần thiết và chi phí bảo trì.

## 10. Thiết kế phân trang, sắp xếp và projection cùng với query

### 10.1. Chọn đúng hợp đồng kết quả

- `List<T>` phù hợp khi cần tập kết quả mà không cam kết metadata phân trang.
- `Slice<T>` phù hợp khi cần một lát dữ liệu cùng thông tin còn phần tiếp theo, theo khả năng tích hợp của mô-đun.
- `Page<T>` phù hợp khi cần tổng số phần tử hoặc số trang và có cơ sở xác định tổng.
- Projection hoặc DTO phù hợp khi cần một phần dữ liệu hay kết quả tổng hợp cụ thể.

Không bọc một danh sách vào `Page` rồi lấy kích thước danh sách làm tổng, trừ khi có bằng chứng đã đọc toàn bộ tập kết quả tương ứng.

### 10.2. Query dữ liệu và query đếm phải cùng ngữ nghĩa

Nếu dữ liệu được giới hạn theo quyền xem, trạng thái hoặc tenant, count cũng phải có các điều kiện tương ứng. Tổng đếm sai có thể làm giao diện phân trang sai và tiết lộ thông tin ngoài phạm vi người dùng.

Join một-nhiều có thể làm entity gốc xuất hiện ở nhiều hàng trung gian. Cần xác định mục tiêu là đếm entity, hàng chi tiết hay nhóm tổng hợp. `count`, `count(distinct ...)` và đếm nhóm không thể hoán đổi máy móc.

Khi tự xây query và count bằng Criteria, không tái sử dụng nguyên `Predicate` hoặc `Root` từ query này cho query khác. Chúng gắn với cấu trúc query đang xây dựng. Có thể dùng chung hàm tạo quy tắc, rồi tạo predicate mới cho từng query và root.

### 10.3. Sắp xếp cần quy tắc rõ

Sort nhận từ người dùng phải được ánh xạ qua các thuộc tính hoặc lựa chọn được phép. Tham số bind thông thường dành cho giá trị, không biến chuỗi bất kỳ thành tên cột hay biểu thức `ORDER BY` an toàn.

Fragment không tự áp dụng `Pageable` hoặc `Sort` chỉ vì tham số có kiểu đó. Implementation phải dùng đúng ngữ nghĩa hoặc từ chối lựa chọn không hỗ trợ.

Khóa phụ tạo thứ tự xác định khi giá trị chính trùng nhau. Tuy nhiên, thứ tự ấy không ngăn dữ liệu thay đổi giữa hai lần đọc trang. Nếu cần tính nhất quán khi có ghi đồng thời, phải xem xét transaction, snapshot hoặc chiến lược phân trang phù hợp.

### 10.4. Join và projection có thể thay đổi chi phí

Fetch join collection cùng phân trang có thể gây vấn đề về số hàng, lượng dữ liệu đọc hoặc cách provider áp dụng giới hạn. Thêm `distinct` không phải giải pháp luôn đủ.

Một phương án là lấy trang định danh trước rồi đọc dữ liệu liên quan cho tập định danh đó. Cách này phải giữ thứ tự, phạm vi truy cập và ngữ nghĩa nhất quán giữa các bước; chỉ nên chọn khi phù hợp mô-đun và kết quả đo.

Projection giúp biểu đạt dữ liệu trả về nhưng không bảo đảm mọi query đều chỉ đọc đúng các cột bạn hình dung. Cần kiểm tra truy vấn thực thi và cách xử lý projection, nhất là khi có quan hệ lồng nhau hoặc biểu thức bổ sung.

## 11. Sai lầm thường gặp

### Tạo fragment cho mọi query dài

Nếu một query cố định được diễn đạt rõ bằng khai báo, chuyển sang fragment có thể chỉ tăng mã và trách nhiệm cấu hình. Cần xác định lợi ích cụ thể từ việc chuyển đổi.

### Dồn mọi nhánh vào một khai báo khó đọc

Khi khó phân biệt “không có tham số”, “không có giá trị phù hợp” và “không có quyền”, việc thêm nhánh đặc biệt rất dễ làm sai ngữ nghĩa. Hãy tách hợp đồng tìm kiếm và đánh giá abstraction truy vấn động hoặc fragment.

### Coi fragment là cách triển khai chung cho mọi kho dữ liệu

Interface fragment có thể độc lập với kho dữ liệu, nhưng implementation dùng `EntityManager` là JPA. Chuyển kho dữ liệu cần implementation và đánh giá ngữ nghĩa tương ứng, không chỉ đổi dependency.

### Nối đầu vào vào câu truy vấn

Fragment cho phép mã tùy chỉnh nên cũng cho phép viết mã không an toàn. Không nối trực tiếp giá trị request vào JPQL hay SQL. Cấu trúc động và tên trường cần được ánh xạ qua lựa chọn kiểm soát; giá trị cần đi qua cơ chế tham số hóa của API.

### Biến lỗi thành kết quả rỗng

Lỗi cú pháp, lỗi kết nối và trường hợp không có dữ liệu có ý nghĩa khác nhau. Bắt mọi exception rồi trả danh sách rỗng khiến người gọi không thể phân biệt và xử lý đúng.

### Đặt quy trình nhiều hệ thống trong fragment

Thao tác đọc đơn, gọi cổng thanh toán, gửi email rồi cập nhật trạng thái thường cần service hoặc thành phần điều phối nghiệp vụ. Fragment phù hợp để đóng gói truy cập dữ liệu tùy chỉnh, không phải nơi mặc định cho mọi thao tác liên quan đơn hàng.

### Cho rằng viết mã tự làm query nhanh hơn

Fragment vẫn có thể tạo N+1, thiếu điều kiện index, đọc quá nhiều dữ liệu hoặc chạy count không cần thiết. Hiệu năng phụ thuộc truy vấn thực thi và khối lượng công việc, không phụ thuộc nơi chứa biểu thức truy vấn.

## 12. Kiểm chứng khi chuyển cách triển khai trong dự án

Khi thay derived query bằng khai báo hoặc fragment, trước hết cần xác định hành vi được giữ và hành vi thay đổi có chủ đích.

| Nhóm kiểm chứng | Ca cần xem xét |
| --- | --- |
| Phạm vi bắt buộc | Đơn của khách hàng khác không xuất hiện |
| Trạng thái | Không có bộ lọc, một trạng thái, nhiều trạng thái, tập rỗng |
| Cận tổng tiền | Bằng cận, nhỏ hơn cận, không có cận |
| Cận thời gian | Bằng cận dưới được nhận, bằng cận trên bị loại |
| Thứ tự | Nhiều đơn cùng `createdAt` vẫn có thứ tự phụ xác định |
| Giới hạn | Từ chối ngoài phạm vi; số hàng không vượt giới hạn |
| Phân trang | Tổng đúng điều kiện, không đếm lặp ngoài ý định |
| Composition | Lời gọi qua repository bean thật đến đúng fragment |
| Lỗi hạ tầng | Không bị chuyển thành kết quả rỗng gây hiểu nhầm |
| Khả năng mô-đun | Mapping, kiểu tham số và query đúng provider sử dụng |

Kiểm thử đơn vị có thể bảo vệ việc kiểm tra tiêu chí nhưng không chứng minh JPQL hoặc Criteria được provider thực thi đúng. Cần kiểm chứng tích hợp phù hợp kho dữ liệu của dự án.

Với tính năng riêng của hệ quản trị, không chỉ dựa vào một cơ sở dữ liệu thử nghiệm khác rồi kết luận tương thích hoàn toàn. Kế hoạch thực thi và ngữ nghĩa biểu thức có thể khác.

Nếu mục tiêu là hiệu năng, cần so sánh cùng bộ lọc, dạng kết quả và dữ liệu đại diện. Bỏ count để trả `List` giảm một loại công việc nhưng đổi hợp đồng so với `Page`; đó chưa phải bằng chứng fragment nhanh hơn với cùng chức năng.

## 13. Quy trình lựa chọn trong công việc

1. **Viết hợp đồng truy vấn:** phạm vi dữ liệu, bộ lọc, `null`/tập rỗng, thứ tự, giới hạn, kết quả và lỗi.
2. **Kiểm tra khả năng suy diễn:** nếu tên ngắn, đúng ngữ nghĩa và được hỗ trợ, có thể tiếp tục dùng.
3. **Thử biểu đạt bằng khai báo:** ưu tiên một biểu thức ổn định, dễ đọc, ánh xạ được bởi mô-đun.
4. **Đánh giá abstraction động:** nếu chủ yếu tổ hợp predicate, xem giải pháp có sẵn của mô-đun.
5. **Chọn fragment có lý do cụ thể:** giữ hợp đồng gọn và đóng gói phụ thuộc kho dữ liệu trong implementation.
6. **Thiết kế kết quả cùng query và count:** đối chiếu yêu cầu trước khi quyết định `Page`, `Slice`, `List` hoặc projection.
7. **Kiểm chứng đường gọi thật:** bao gồm composition, transaction, mapping và trường hợp biên cần bảo vệ.
8. **Ghi lý do lựa chọn:** ví dụ query cố định, count riêng cho join hoặc fragment để xây join tùy bộ lọc.

Có thể chuyển một phương thức sang fragment và giữ các phương thức khai báo khác trên cùng repository. Không cần áp dụng duy nhất một cơ chế cho cả module khi các truy vấn có bản chất khác nhau.

## 14. Tình huống tự đánh giá

### A. Nhiều join nhưng cấu trúc cố định

Báo cáo tổng hợp trên ba quan hệ luôn có cùng điều kiện và trả DTO cố định. Ngôn ngữ khai báo của mô-đun hỗ trợ cả query lẫn mapping.

Giải thích vì sao số join chưa đủ để quyết định dùng fragment. Xác định các yếu tố về count, ánh xạ và provider cần kiểm tra.

### B. Tập trạng thái rỗng

Endpoint nhận tập rỗng với nghĩa không trạng thái nào được chọn để xem. Implementation bỏ điều kiện `IN` rồi trả mọi đơn của khách hàng.

Xác định điểm sai của hợp đồng, cách sửa và ca cần kiểm chứng. Phân biệt “không áp dụng bộ lọc” với “không phần tử nào được chấp nhận”.

### C. Khai báo bị lỗi nhưng kỳ vọng fallback

Dự án tìm query khai báo trước và chỉ suy diễn khi không có. Một query khai báo tham chiếu sai thuộc tính; người viết kỳ vọng framework tự dùng tên phương thức thay thế.

Giải thích vì sao không nên dựa vào kỳ vọng đó. Nêu các yếu tố ảnh hưởng thời điểm phát hiện lỗi.

### D. Fragment nhanh hơn vì bỏ count

Nhóm chuyển từ `Page<PurchaseOrder>` sang fragment trả `List<PurchaseOrder>` và thấy thời gian giảm. Giao diện vẫn cần tổng số trang.

Chỉ ra hợp đồng đã thay đổi, phần chi phí bị bỏ và cách so sánh lại hai giải pháp với cùng yêu cầu.

### E. Chuyển kho dữ liệu

Ứng dụng muốn giữ `PurchaseOrderSearch`, nhưng implementation hiện dùng Jakarta Persistence Criteria API.

Phân tách phần hợp đồng có thể giữ và implementation phải thay. Đánh giá lại phân trang, kiểu thời gian, thứ tự, transaction và khả năng biểu đạt bộ lọc của mô-đun mới.