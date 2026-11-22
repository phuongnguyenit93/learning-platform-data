# Phân biệt default method, repository fragment và dịch vụ nghiệp vụ

Trong Spring Data JPA, cả ba cơ chế đều có thể giúp tổ chức hành vi quanh repository, nhưng chúng giải quyết ba nhu cầu khác nhau:

- **Default method** bổ sung một thao tác Java nhỏ ngay trên interface repository, thường bằng cách kết hợp những phương thức truy vấn đã có.
- **Repository fragment** mở rộng repository bằng một thành phần truy cập dữ liệu tùy biến, phù hợp khi cần viết truy vấn hoặc thao tác persistence phức tạp.
- **Dịch vụ nghiệp vụ (business service)** thực hiện một ca sử dụng của ứng dụng: áp dụng quy tắc nghiệp vụ, phối hợp nhiều repository hoặc dịch vụ khác và xác định ranh giới transaction.

Chọn đúng vị trí giúp repository tập trung vào dữ liệu, service tập trung vào ca sử dụng, và mã nguồn dễ kiểm thử hơn.

## 1. Nhìn tổng thể kiến trúc

Spring Data tạo một proxy cho interface repository. Proxy này kết hợp phần triển khai CRUD/truy vấn có sẵn, các custom fragment mà repository kế thừa, và những default method được khai báo trực tiếp trên interface.

~~~mermaid
flowchart TD
    C[Controller] --> S[Business service]
    S --> R[Spring Data repository proxy]
    R --> D[Default method]
    R --> J[CRUD và query methods]
    R --> F[Custom repository fragment]
    J --> DB[(Database)]
    F --> DB
~~~

Service gọi repository để đọc hoặc ghi dữ liệu. Default method và fragment đều là một phần của API repository; chúng không thay thế vai trò điều phối ca sử dụng của service.

## 2. Default method: tiện ích nhỏ trên repository interface

Default method là phương thức có phần thân được khai báo bằng từ khóa Java **default** trong interface. Repository có thể dùng nó để đặt tên dễ hiểu cho một thao tác được ghép từ các query method đã có.

Ví dụ, giả sử entity PurchaseOrder có các thuộc tính customerId, status và createdAt; enum OrderStatus có giá trị PENDING:

~~~java
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    Optional<PurchaseOrder>
    findFirstByCustomerIdAndStatusOrderByCreatedAtDesc(
            Long customerId, OrderStatus status);

    default Optional<PurchaseOrder> findLatestPendingForCustomer(
            Long customerId) {
        return findFirstByCustomerIdAndStatusOrderByCreatedAtDesc(
                customerId, OrderStatus.PENDING);
    }
}
~~~

Spring Data triển khai query method dựa trên tên phương thức. Default method chỉ gọi lại query method đó và cung cấp một tên nghiệp vụ dễ đọc hơn cho người sử dụng repository.

**Nên dùng khi:**

- Muốn tạo một tên thao tác rõ nghĩa từ một hoặc vài phương thức repository sẵn có.
- Logic ngắn, ít nhánh, chỉ liên quan đến chính repository đó.
- Không cần phối hợp nhiều repository, gọi API bên ngoài hoặc điều phối một quy trình nghiệp vụ.

**Không nên dùng khi:**

- Phương thức có nhiều bước, nhiều nhánh hoặc chứa quy tắc nghiệp vụ thay đổi thường xuyên.
- Cần inject thêm repository, gateway, publisher hoặc thành phần khác vào interface.
- Cần truy vấn tùy biến phức tạp bằng EntityManager, Criteria API hoặc SQL.

Default method không tự tạo một truy vấn SQL mới chỉ vì nó có phần thân. Truy vấn vẫn đến từ query method, derived query, JPQL hoặc cơ chế persistence mà nó gọi. Hãy giữ default method ngắn và xem nó như một tiện ích của API repository.

## 3. Repository fragment: mở rộng phần truy cập dữ liệu

Repository fragment là một thành phần tùy biến được ghép vào repository. Dùng fragment khi Spring Data query method hoặc JPQL khai báo thông thường không diễn đạt thuận tiện thao tác cần thực hiện, chẳng hạn bộ lọc động, truy vấn Criteria API hoặc cách truy cập dữ liệu chuyên biệt.

Một fragment thường có ba phần:

1. Interface mô tả các thao tác tùy biến.
2. Class triển khai interface đó.
3. Repository chính kế thừa fragment interface.

Ví dụ dưới đây tạo chức năng tìm đơn hàng theo nhiều điều kiện có thể bỏ trống.

**Bước 1 — Khai báo tiêu chí và fragment interface**

~~~java
import java.time.LocalDateTime;
import java.util.List;

public record PurchaseOrderCriteria(
        Long customerId,
        OrderStatus status,
        LocalDateTime createdFrom,
        LocalDateTime createdBefore) {
}

public interface PurchaseOrderSearch {
    List<PurchaseOrder> search(PurchaseOrderCriteria criteria);
}
~~~

Trong ví dụ này, createdFrom là mốc thời gian bao gồm; createdBefore là mốc kết thúc không bao gồm. Nếu một thuộc tính tiêu chí là null, điều kiện tương ứng sẽ không được thêm vào truy vấn.

**Bước 2 — Triển khai fragment bằng Criteria API**

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.persistence.criteria.CriteriaBuilder;
import jakarta.persistence.criteria.CriteriaQuery;
import jakarta.persistence.criteria.Path;
import jakarta.persistence.criteria.Predicate;
import jakarta.persistence.criteria.Root;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

public class PurchaseOrderSearchImpl implements PurchaseOrderSearch {

    @PersistenceContext
    private EntityManager entityManager;

    @Override
    public List<PurchaseOrder> search(PurchaseOrderCriteria criteria) {
        CriteriaBuilder cb = entityManager.getCriteriaBuilder();
        CriteriaQuery<PurchaseOrder> query =
                cb.createQuery(PurchaseOrder.class);
        Root<PurchaseOrder> order = query.from(PurchaseOrder.class);

        List<Predicate> predicates = new ArrayList<>();

        if (criteria.customerId() != null) {
            predicates.add(cb.equal(
                    order.get("customerId"), criteria.customerId()));
        }

        if (criteria.status() != null) {
            predicates.add(cb.equal(
                    order.get("status"), criteria.status()));
        }

        Path<LocalDateTime> createdAt = order.get("createdAt");

        if (criteria.createdFrom() != null) {
            predicates.add(cb.greaterThanOrEqualTo(
                    createdAt, criteria.createdFrom()));
        }

        if (criteria.createdBefore() != null) {
            predicates.add(cb.lessThan(
                    createdAt, criteria.createdBefore()));
        }

        query.select(order);
        if (!predicates.isEmpty()) {
            query.where(predicates.toArray(Predicate[]::new));
        }
        query.orderBy(cb.desc(createdAt));

        return entityManager.createQuery(query).getResultList();
    }
}
~~~

**Bước 3 — Ghép fragment vào repository chính**

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.Optional;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long>, PurchaseOrderSearch {

    Optional<PurchaseOrder>
    findFirstByCustomerIdAndStatusOrderByCreatedAtDesc(
            Long customerId, OrderStatus status);

    default Optional<PurchaseOrder> findLatestPendingForCustomer(
            Long customerId) {
        return findFirstByCustomerIdAndStatusOrderByCreatedAtDesc(
                customerId, OrderStatus.PENDING);
    }
}
~~~

Spring Data nhận diện class triển khai fragment theo quy ước tên: interface PurchaseOrderSearch tương ứng với class PurchaseOrderSearchImpl khi hậu tố mặc định là Impl. Nếu dự án cấu hình hậu tố khác, tên class phải tuân theo cấu hình đó. Đặt các thành phần trong phạm vi package được Spring Data quét để chúng được phát hiện.

Sau khi ghép, code sử dụng repository có thể gọi cả CRUD, default method và phương thức search của fragment trên cùng một bean PurchaseOrderRepository.

**Nên dùng fragment khi:**

- Truy vấn có nhiều điều kiện động hoặc cần Criteria API.
- Cần dùng EntityManager, native SQL, Querydsl hoặc một kỹ thuật persistence chuyên biệt.
- Muốn chia các nhóm hành vi truy cập dữ liệu thành thành phần nhỏ, có thể tái sử dụng và ghép vào nhiều repository.

Fragment vẫn thuộc tầng truy cập dữ liệu. Nó nên tập trung vào cách đọc/ghi dữ liệu, không nên trở thành nơi điều phối quy trình nghiệp vụ như thanh toán, gửi thông báo hay phối hợp nhiều aggregate.

## 4. Dịch vụ nghiệp vụ: thực hiện một ca sử dụng

Business service nằm ở tầng ứng dụng hoặc nghiệp vụ. Nó nhận yêu cầu từ controller hoặc một thành phần gọi khác, kiểm tra quy tắc của ca sử dụng, gọi repository và phối hợp những thành phần cần thiết.

Ví dụ: hủy một đơn hàng chỉ khi trạng thái hiện tại cho phép hủy.

~~~java
import jakarta.persistence.EntityNotFoundException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PurchaseOrderService {

    private final PurchaseOrderRepository repository;

    public PurchaseOrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void cancelOrder(Long orderId) {
        PurchaseOrder order = repository.findById(orderId)
                .orElseThrow(() ->
                        new EntityNotFoundException(
                                "Không tìm thấy đơn hàng: " + orderId));

        if (!order.canBeCancelled()) {
            throw new IllegalStateException(
                    "Đơn hàng hiện tại không thể bị hủy");
        }

        order.cancel();
    }
}
~~~

Ví dụ giả định entity PurchaseOrder có hai phương thức canBeCancelled() và cancel() để đóng gói quy tắc trạng thái của chính đơn hàng. Service điều phối ca sử dụng và đặt transaction bằng @Transactional.

Khi findById được gọi bên trong transaction, entity được quản lý bởi persistence context. Nếu order.cancel() thay đổi entity, JPA dirty checking sẽ ghi thay đổi khi transaction flush/commit; không cần gọi save() chỉ để lưu lại entity đang được quản lý.

Trong một ca sử dụng lớn hơn, service có thể phối hợp PurchaseOrderRepository, PaymentRepository, InventoryService và NotificationPublisher. Service là nơi phù hợp để xác định thứ tự các bước, xử lý kết quả và quản lý transaction của quy trình. Những quy tắc gắn chặt với một entity vẫn nên được đóng gói trong entity hoặc value object; service không nên kéo toàn bộ logic đó ra ngoài.

Cần phân biệt application service và domain service khi thiết kế theo DDD. Application service điều phối một use case và phụ thuộc vào repository hoặc cổng dịch vụ. Domain service chứa quy tắc miền không tự nhiên thuộc về một entity cụ thể. Cả hai có thể được đăng ký bằng @Service trong Spring, nhưng annotation không tự quyết định trách nhiệm của lớp.

## 5. So sánh và chọn đúng cơ chế

| Tiêu chí | Default method | Repository fragment | Business service |
|---|---|---|---|
| Vị trí | Interface repository | Thành phần được repository ghép vào | Tầng ứng dụng/nghiệp vụ |
| Trách nhiệm | Tiện ích Java ngắn quanh API repository | Logic truy cập dữ liệu tùy biến | Điều phối ca sử dụng và quy tắc nghiệp vụ |
| Công cụ thường dùng | Gọi query method có sẵn | EntityManager, Criteria API, Querydsl, SQL | Repository, domain object, gateway, event publisher |
| Phạm vi phối hợp | Một repository | Một nhóm thao tác persistence | Có thể nhiều repository và dịch vụ |
| Ví dụ | findLatestPendingForCustomer | search với bộ lọc động | cancelOrder, checkout, approveOrder |

Có thể quyết định theo ba câu hỏi:

- **Chỉ cần đặt tên rõ hơn cho một thao tác repository hoặc ghép vài query method đơn giản?** Dùng default method.
- **Cần tự xây dựng cách truy vấn hoặc thao tác persistence?** Dùng repository fragment.
- **Cần thực hiện một use case, áp dụng quy tắc nghiệp vụ hoặc phối hợp nhiều thành phần?** Dùng business service.

Một service được phép gọi phương thức fragment. Ví dụ, service có thể gọi repository.search(criteria), sau đó áp dụng quy tắc nghiệp vụ lên kết quả. Việc truy vấn thuộc fragment; quyết định nghiệp vụ và điều phối thuộc service.

## 6. Những lỗi thiết kế thường gặp

**Đưa quy trình dài vào default method.** Interface repository dần chứa nhiều nhánh nghiệp vụ, khó kiểm thử và khó mở rộng. Hãy chuyển phần điều phối sang service; giữ default method cho tiện ích nhỏ.

**Đặt quy tắc nghiệp vụ vào fragment.** Fragment có thể truy cập EntityManager nên dễ bị biến thành nơi xử lý mọi thứ. Hãy để fragment giải quyết truy vấn và persistence; để service hoặc domain model xử lý quy tắc nghiệp vụ.

**Để service tự viết truy vấn dữ liệu phức tạp.** Điều này làm service phụ thuộc chi tiết JPA và khó tái sử dụng. Hãy đóng gói truy vấn trong repository query method hoặc fragment.

**Đặt sai tên class triển khai fragment.** Nếu interface là PurchaseOrderSearch nhưng class không tuân theo hậu tố cấu hình, Spring Data có thể không ghép fragment vào repository. Kiểm tra tên, package và cấu hình repository scanning khi phương thức tùy biến không được nhận diện.

**Dùng transaction không đúng ranh giới.** Một use case cập nhật nhiều dữ liệu thường cần transaction ở service để các bước có cùng ranh giới nhất quán. Với truy vấn chỉ đọc, cân nhắc @Transactional(readOnly = true) tại phương thức hoặc lớp phù hợp. Không giả định mọi query method đều tự có transaction chỉ vì nó thuộc repository.

**Viết service chỉ chuyển tiếp không có trách nhiệm rõ ràng.** Một lớp service chỉ gọi đúng một repository method có thể không tạo thêm giá trị. Tuy nhiên, service vẫn hữu ích khi nó là ranh giới use case, nơi đặt authorization, transaction, orchestration hoặc chính sách ứng dụng. Hãy để tên và trách nhiệm của lớp phản ánh vai trò thực tế.

## 7. Kiểm thử theo đúng trách nhiệm

- **Default method:** kiểm thử tích hợp repository với cơ sở dữ liệu để xác nhận default method gọi đúng query method và trả về kết quả đúng.
- **Repository fragment:** kiểm thử tích hợp với JPA để xác nhận bộ lọc, điều kiện biên, thứ tự sắp xếp và hành vi khi không có tiêu chí.
- **Business service:** kiểm thử các nhánh nghiệp vụ như tìm thấy/không tìm thấy đơn hàng, trạng thái được phép/không được phép hủy và sự phối hợp giữa các dependency. Dùng kiểm thử tích hợp khi cần xác nhận transaction và dirty checking.

## Kết luận

Default method giúp API repository gọn và dễ đọc; fragment bổ sung năng lực truy cập dữ liệu tùy biến; business service tổ chức các bước của một ca sử dụng và thực thi quy tắc nghiệp vụ. Khi mỗi thành phần giữ đúng trách nhiệm, mã nguồn Spring Data JPA dễ bảo trì, kiểm thử và mở rộng hơn.