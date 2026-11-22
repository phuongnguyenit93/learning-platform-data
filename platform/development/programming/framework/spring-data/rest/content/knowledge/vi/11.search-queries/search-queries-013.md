# Giới hạn công bố truy vấn ghi dữ liệu hoặc truy vấn tốn tài nguyên

Spring Data REST có thể tự động công bố các query method của repository thành endpoint dưới tài nguyên **search**. Cơ chế này thuận tiện cho các truy vấn đọc có thể dùng an toàn qua HTTP GET. Tuy nhiên, một số phương thức chỉ phục vụ nội bộ, có tác dụng ghi dữ liệu hoặc chạy truy vấn tốn nhiều tài nguyên không nên xuất hiện trong API công khai.

Cách kiểm soát trực tiếp ở cấp method là dùng **@RestResource(exported = false)**. Annotation này giữ phương thức trong repository để service hoặc code nội bộ tiếp tục gọi, đồng thời yêu cầu Spring Data REST không công bố query resource tương ứng.

## Mục tiêu

Sau bài này, bạn có thể:

- Hiểu query method được Spring Data REST công bố ở đâu và dùng HTTP method nào.
- Ẩn riêng một query method bằng **@RestResource(exported = false)**.
- Phân biệt ẩn query method với ẩn toàn bộ repository hoặc tắt một HTTP method CRUD.
- Xử lý an toàn các phương thức ghi dữ liệu như query có **@Modifying**.
- Giảm rủi ro từ truy vấn đọc tốn tài nguyên bằng phân trang, giới hạn kích thước, thiết kế query và kiểm soát truy cập.
- Kiểm tra API sau khi thay đổi exposure.

## 1. Query method được công bố như thế nào?

Giả sử repository quản lý đơn hàng:

~~~java
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    List<Order> findByStatus(OrderStatus status);
}
~~~

Theo cơ chế mặc định, Spring Data REST có thể công bố query method dựa trên tên phương thức. Với repository path mặc định là orders, endpoint tìm kiếm có dạng:

~~~text
/orders/search/findByStatus?status=PAID
~~~

Nếu repository được tùy chỉnh:

~~~java
@RepositoryRestResource(path = "orders")
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    List<Order> findByStatus(OrderStatus status);
}
~~~

thì query method nằm dưới:

~~~text
/orders/search/findByStatus
~~~

Search resource tại /orders/search trả về các link đến query method đang được công bố. Representation HAL có thể có dạng:

~~~json
{
  "_links": {
    "findByStatus": {
      "href": "http://localhost:8080/orders/search/findByStatus{?status}"
    }
  }
}
~~~

Client khám phá endpoint qua relation và href trong HAL thay vì phải tự đoán tên URL.

Tài liệu Spring Data REST xác định Search resource và Query Method resource là tài nguyên chỉ đọc, hỗ trợ **GET**. Query method resource thực thi phương thức repository tương ứng và trả về kết quả truy vấn.

## 2. Ẩn riêng một query method

Nếu phương thức chỉ phục vụ nội bộ hoặc không nên được gọi qua REST, đặt **@RestResource(exported = false)** ngay trên method:

~~~java
@RepositoryRestResource(path = "orders")
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    List<Order> findByStatus(OrderStatus status);

    @RestResource(exported = false)
    List<Order> findInternalRiskReviewCandidates(
            RiskLevel riskLevel);
}
~~~

Trong ví dụ này:

- findByStatus tiếp tục được công bố dưới /orders/search.
- findInternalRiskReviewCandidates vẫn là phương thức của repository và code Java nội bộ có thể gọi.
- Spring Data REST không công bố query resource cho findInternalRiskReviewCandidates.
- Các phương thức CRUD và query method khác của repository không bị ẩn chỉ vì một method được đánh dấu exported = false.

Đây là lựa chọn phù hợp khi chỉ một số query cần giữ nội bộ.

Có thể kết hợp **@Query** với annotation này:

~~~java
@RepositoryRestResource(path = "orders")
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    @RestResource(exported = false)
    @Query("""
        select o
        from Order o
        where o.riskLevel = :riskLevel
          and o.reviewed = false
        """)
    List<Order> findInternalRiskReviewCandidates(
            @Param("riskLevel") RiskLevel riskLevel);
}
~~~

Query vẫn có thể được gọi từ service hoặc job nội bộ. Annotation chỉ điều khiển việc Spring Data REST công bố method.

## 3. Ẩn toàn bộ repository khi cần

Nếu repository hoàn toàn không phải là API resource, dùng **@RepositoryRestResource(exported = false)** ở cấp interface:

~~~java
@RepositoryRestResource(exported = false)
public interface InternalAuditRepository
        extends JpaRepository<AuditRecord, Long> {

    List<AuditRecord> findByActorId(String actorId);
}
~~~

Khi đó repository không được Spring Data REST công bố như một repository resource. Các query method của nó cũng không xuất hiện dưới search resource.

Phân biệt hai mức:

| Cấu hình | Phạm vi |
| --- | --- |
| @RestResource(exported = false) trên method | Ẩn một query method hoặc method cụ thể |
| @RepositoryRestResource(exported = false) trên repository | Ẩn repository resource và các resource con của repository |
| Không khai báo method trong repository REST | Method không tham gia hợp đồng repository được công bố |
| RepositoryDetectionStrategy | Quy định repository nào đủ điều kiện được phát hiện/công bố ở cấp repository |

Không dùng annotation cấp repository chỉ để ẩn một query nếu những endpoint khác của repository vẫn cần được sử dụng.

## 4. Giới hạn query có tác dụng ghi dữ liệu

Một repository có thể chứa query dùng để cập nhật dữ liệu:

~~~java
public interface AccountRepository
        extends JpaRepository<Account, Long> {

    @Modifying
    @Transactional
    @Query("""
        update Account a
        set a.status = :status
        where a.id = :id
        """)
    int updateStatus(
            @Param("id") Long id,
            @Param("status") AccountStatus status);
}
~~~

Đây là thao tác ghi dữ liệu, dù nó được khai báo dưới dạng query method. Không nên đưa một thao tác có side effect vào API tìm kiếm chỉ đọc.

Spring Data REST mô tả query method resource là GET-only. Vì thế, hãy giữ các phương thức ghi dữ liệu trong tầng repository/service nội bộ và đánh dấu chúng không được export nếu chúng có thể bị exporter nhận diện như query method:

~~~java
public interface AccountRepository
        extends JpaRepository<Account, Long> {

    @Modifying
    @Transactional
    @RestResource(exported = false)
    @Query("""
        update Account a
        set a.status = :status
        where a.id = :id
        """)
    int updateStatus(
            @Param("id") Long id,
            @Param("status") AccountStatus status);
}
~~~

Khi cần cung cấp thao tác này cho client, hãy tạo endpoint command riêng với HTTP method và hợp đồng request phù hợp, rồi gọi service:

~~~java
@Service
public class AccountService {

    private final AccountRepository repository;

    public AccountService(AccountRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void changeStatus(Long id, AccountStatus status) {
        int updated = repository.updateStatus(id, status);
        if (updated == 0) {
            throw new EntityNotFoundException(
                    "Account not found: " + id);
        }
    }
}
~~~

Ví dụ controller:

~~~java
@RestController
@RequestMapping("/account-commands")
public class AccountCommandController {

    private final AccountService service;

    public AccountCommandController(AccountService service) {
        this.service = service;
    }

    @PatchMapping("/{id}/status")
    @PreAuthorize("hasAuthority('ACCOUNT_STATUS_WRITE')")
    public ResponseEntity<Void> changeStatus(
            @PathVariable Long id,
            @RequestBody ChangeAccountStatusRequest request) {

        service.changeStatus(id, request.status());
        return ResponseEntity.noContent().build();
    }
}
~~~

Controller minh họa một command API tường minh. Hãy dùng DTO, validation, transaction boundary và quyền truy cập theo nghiệp vụ thực tế của ứng dụng. Không đưa câu lệnh update/delete vào một URL tìm kiếm chỉ vì Spring Data có thể thực thi nó.

## 5. Giới hạn query đọc tốn tài nguyên

Không phải mọi query method đều phù hợp để công bố. Một truy vấn có thể tốn nhiều tài nguyên khi:

- Quét bảng lớn mà thiếu điều kiện lọc chọn lọc.
- Join nhiều bảng hoặc fetch một object graph quá rộng.
- Tính tổng số bản ghi trên tập dữ liệu rất lớn.
- Sắp xếp theo cột không có index phù hợp.
- Trả về một collection không giới hạn.
- Chạy báo cáo tổng hợp phức tạp hoặc truy vấn lịch sử dài.
- Cho phép client gửi khoảng ngày, từ khóa hoặc điều kiện làm phạm vi truy vấn quá rộng.

Nếu query chỉ phục vụ báo cáo nội bộ hoặc một luồng vận hành đặc biệt, có thể ẩn method:

~~~java
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    @RestResource(exported = false)
    @Query("""
        select new com.example.ReportRow(
            o.region,
            sum(o.totalAmount),
            count(o.id)
        )
        from Order o
        where o.createdAt >= :from
          and o.createdAt < :to
        group by o.region
        """)
    List<ReportRow> calculateInternalRegionalReport(
            @Param("from") Instant from,
            @Param("to") Instant to);
}
~~~

Service nội bộ có thể gọi phương thức này khi có quyền phù hợp. Nếu báo cáo cần được cung cấp cho client, hãy thiết kế endpoint riêng với giới hạn thời gian, quyền truy cập và cơ chế chạy phù hợp; với tác vụ rất nặng, cân nhắc xử lý bất đồng bộ và trả về mã tác vụ để client truy vấn trạng thái.

## 6. Phân trang giúp giới hạn lượng dữ liệu trả về

Với query đọc cần công bố, ưu tiên chữ ký có **Pageable**:

~~~java
@RepositoryRestResource(path = "orders")
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    Page<Order> findByStatus(
            OrderStatus status,
            Pageable pageable);
}
~~~

Spring Data REST có thể tạo URI template chứa tham số phân trang:

~~~text
/orders/search/findByStatus?status=PAID&page=0&size=20
~~~

Các tham số phổ biến:

| Tham số | Ý nghĩa |
| --- | --- |
| page | Số trang, bắt đầu từ 0 |
| size | Số phần tử yêu cầu trên một trang |
| sort | Thuộc tính và chiều sắp xếp |

Có thể đặt kích thước trang tối đa ở cấu hình Spring Data REST:

~~~java
@Configuration
public class RestConfiguration
        implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {
        config.setMaxPageSize(100);
    }
}
~~~

Giá trị 100 chỉ là ví dụ. Hãy chọn giới hạn theo kích thước response, tải database và SLA của ứng dụng.

Phân trang giúp giới hạn số phần tử trả về trong một request, nhưng không tự làm query rẻ hơn. Một truy vấn có thể vẫn tốn nhiều tài nguyên do join, sort, count hoặc thiếu index. Với báo cáo lớn, cân nhắc thiết kế query chuyên biệt, projection DTO, index phù hợp hoặc xử lý nền.

## 7. Không nhầm ẩn query với giới hạn truy cập

**@RestResource(exported = false)** điều khiển việc công bố tài nguyên qua Spring Data REST. Nó không phải cơ chế authorization.

Cần phân biệt:

| Cơ chế | Tác dụng |
| --- | --- |
| @RestResource(exported = false) | Không công bố method/resource qua Spring Data REST |
| @RepositoryRestResource(exported = false) | Không công bố repository resource |
| Spring Security | Xác thực và quyết định principal có quyền gọi endpoint hay không |
| @PreAuthorize | Kiểm tra quyền ở method/service/controller |
| Validation và business rule | Kiểm soát dữ liệu đầu vào và trạng thái hợp lệ |
| Rate limit, timeout và giới hạn tải | Hạn chế tần suất hoặc thời gian sử dụng tài nguyên |

Nếu một method bị ẩn khỏi Spring Data REST nhưng được gọi từ controller khác, controller đó vẫn phải áp dụng authorization. Các ứng dụng khác, batch job hoặc code nội bộ vẫn có thể gọi repository method trực tiếp.

Nếu dữ liệu trả về nhạy cảm, cần kiểm soát cả representation, projection và association được công bố. Việc ẩn một query method không tự động bảo vệ cùng dữ liệu khi nó được truy cập qua endpoint hoặc projection khác.

## 8. Phân biệt ẩn query method và ẩn CRUD HTTP method

Repository CRUD method có thể được dùng để cung cấp nhiều HTTP operation. Ví dụ, method save có thể hỗ trợ POST trên collection resource và PUT/PATCH trên item resource.

Khi muốn tắt một CRUD method, có thể override method tương ứng và đặt **@RestResource(exported = false)** trên method override. Tuy nhiên, phải xác định các overload thực sự được Spring Data REST sử dụng.

Ví dụ ẩn thao tác xóa qua repository:

~~~java
@RepositoryRestResource(path = "orders")
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    @Override
    @RestResource(exported = false)
    void deleteById(Long id);
}
~~~

Đây chỉ là ví dụ minh họa cho một chữ ký. Tùy phiên bản Spring Data và interface cha, có thể có các overload delete khác như delete(entity), deleteAllById(…), deleteAll(…) hoặc deleteAll(iterable). Muốn loại bỏ toàn bộ khả năng HTTP DELETE, cần kiểm tra đúng những method mà module repository sử dụng và xác nhận trên runtime.

Nếu chỉ muốn tắt một HTTP method trên một nhóm resource mà không thay đổi hợp đồng repository, Spring Data REST cung cấp **ExposureConfiguration** để cấu hình exposure theo domain type hoặc loại resource.

Ví dụ cấu hình tắt PATCH trên item resource:

~~~java
@Configuration
public class RestConfiguration
        implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.getExposureConfiguration()
            .withItemExposure((metadata, methods) ->
                methods.disable(HttpMethod.PATCH));
    }
}
~~~

Đây là cấu hình phạm vi item resource theo rule đã khai báo. Nếu chỉ muốn giới hạn một domain type, dùng cấu hình theo domain type thay vì áp dụng toàn cục. Kiểm tra API của phiên bản Spring Data REST đang sử dụng vì các overload và rule có thể thay đổi theo phiên bản.

## 9. Tùy chỉnh path không đồng nghĩa với ẩn method

Có thể đổi URL và link relation của query method bằng **@RestResource(path = ..., rel = ...)**:

~~~java
@RepositoryRestResource(path = "orders")
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    @RestResource(path = "by-status", rel = "ordersByStatus")
    Page<Order> findByStatus(
            OrderStatus status,
            Pageable pageable);
}
~~~

Khi đó endpoint có thể là:

~~~text
/orders/search/by-status?status=PAID&page=0&size=20
~~~

Link relation trong HAL là ordersByStatus.

Cấu hình path/rel chỉ đổi tên đường dẫn và link relation. Method vẫn được công bố. Muốn ẩn method, phải dùng exported = false.

Có thể kết hợp các thuộc tính khi cần, nhưng với một method không được export, path và rel không tạo ra endpoint công khai:

~~~java
@RestResource(
    path = "internal-report",
    rel = "internalReport",
    exported = false
)
Page<ReportRow> calculateInternalReport(
        ReportFilter filter,
        Pageable pageable);
~~~

## 10. Kiểm tra API sau khi giới hạn exposure

Sau khi thay đổi annotation hoặc cấu hình, kiểm tra cả discovery link và endpoint trực tiếp.

**Bước 1 — Đọc collection resource**

~~~http
GET /orders
Accept: application/hal+json
~~~

Xác nhận link search xuất hiện khi repository còn ít nhất một query method được công bố.

**Bước 2 — Đọc search resource**

~~~http
GET /orders/search
Accept: application/hal+json
~~~

Xác nhận query method công khai vẫn có link, còn method đã đánh dấu exported = false không xuất hiện.

**Bước 3 — Gọi query công khai**

~~~http
GET /orders/search/findByStatus?status=PAID&page=0&size=20
Accept: application/hal+json
~~~

Xác nhận query trả về kết quả và page metadata như mong muốn.

**Bước 4 — Thử endpoint đã ẩn**

Gọi URI trước đây của method đã bị ẩn. Tài nguyên không còn được công bố; thường không có link discovery và direct request không còn được route tới query method đó. Xác nhận status thực tế của phiên bản ứng dụng, thường là 404.

**Bước 5 — Kiểm tra method nội bộ**

Chạy unit/integration test hoặc gọi service để xác nhận code nội bộ vẫn sử dụng được repository method sau khi ẩn khỏi REST.

**Bước 6 — Kiểm tra quyền và tải**

Thử user không có quyền, request có phạm vi dữ liệu quá rộng, page size vượt giới hạn và trường hợp query timeout. Xác nhận các giới hạn bảo vệ được thực thi.

Ví dụ kiểm tra nhanh bằng curl:

~~~bash
curl -i -H "Accept: application/hal+json" \
  http://localhost:8080/orders/search
~~~

Đừng chỉ dựa vào việc không thấy link trong HAL. Hãy gọi trực tiếp URL cũ để xác nhận exporter không còn công bố route và kiểm tra các endpoint khác có thể truy cập cùng dữ liệu.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Query vẫn xuất hiện trong /search | Annotation đặt nhầm trên repository hoặc field thay vì method; ứng dụng chưa nạp bản build mới | Đặt @RestResource(exported = false) trực tiếp trên query method, rebuild và khởi động lại |
| Method đã ẩn nhưng service nội bộ không gọi được | Method signature hoặc repository wiring bị thay đổi khi chỉnh interface | Giữ method trong interface và chỉ đổi thuộc tính exported |
| Ẩn một query nhưng toàn bộ repository biến mất | Dùng @RepositoryRestResource(exported = false) ở cấp interface | Chuyển annotation xuống method cần ẩn |
| Query nặng vẫn chạy qua endpoint khác | Cùng dữ liệu được truy cập qua collection, projection, custom controller hoặc endpoint khác | Kiểm kê các đường truy cập dữ liệu và áp dụng authorization/giới hạn ở từng nơi |
| Kết quả trả quá nhiều dữ liệu | Method không hỗ trợ Pageable hoặc giới hạn page size quá cao | Dùng Pageable, cấu hình max page size và giới hạn response |
| Query vẫn chậm dù đã phân trang | Join, sort, count hoặc query plan tốn kém | Kiểm tra execution plan, index, projection và cách tính tổng số bản ghi |
| GET gây thay đổi dữ liệu | Method được thiết kế có side effect nhưng bị đưa vào đường truy vấn đọc | Ẩn method, chuyển command sang endpoint có HTTP method phù hợp và bảo vệ bằng authorization |
| Tắt một CRUD method nhưng HTTP method vẫn hoạt động | Còn overload khác được dùng để phục vụ resource | Kiểm tra Repository resources reference và method exposure thực tế của phiên bản đang chạy |

## 12. Quy trình áp dụng

1. Liệt kê query method đang xuất hiện dưới /search.
2. Phân loại từng method: đọc thông thường, báo cáo tốn tài nguyên, truy vấn nhạy cảm hoặc thao tác có side effect.
3. Với query chỉ dùng nội bộ, thêm @RestResource(exported = false) trên method.
4. Với repository hoàn toàn nội bộ, cân nhắc @RepositoryRestResource(exported = false).
5. Với truy vấn đọc cần công bố, thiết kế tham số giới hạn, Pageable và page size tối đa.
6. Với truy vấn ghi dữ liệu, giữ trong service/repository và cung cấp command endpoint riêng nếu cần cho client.
7. Áp dụng authorization, validation, timeout và rate limit theo mức độ rủi ro.
8. Kiểm tra search link, gọi trực tiếp endpoint đã ẩn và chạy test cho đường gọi nội bộ.
9. Kiểm tra query plan và log tải đối với endpoint truy vấn tốn tài nguyên.

## 13. Checklist nhanh

- [ ] Đã xác định method nào được công bố dưới /search.
- [ ] Query ghi dữ liệu hoặc có side effect không được đưa vào API tìm kiếm công khai.
- [ ] Query chỉ dùng nội bộ có @RestResource(exported = false).
- [ ] Chỉ ẩn toàn bộ repository khi mọi REST resource của nó đều không cần công bố.
- [ ] Không nhầm path/rel với exported.
- [ ] Query đọc công khai có phạm vi lọc và phân trang hợp lý.
- [ ] Đã cấu hình max page size phù hợp.
- [ ] Đã kiểm tra sort, count, join và index cho query nặng.
- [ ] Authorization được áp dụng cho controller/service và các đường truy cập khác.
- [ ] Đã kiểm tra HAL discovery, direct URL, HTTP status và đường gọi nội bộ.

## 14. Ghi nhớ

Muốn giới hạn công bố một query method, đặt annotation trên chính method đó:

~~~java
@RestResource(exported = false)
List<Order> findInternalRiskReviewCandidates(
        RiskLevel riskLevel);
~~~

Method vẫn tồn tại trong repository và có thể được code nội bộ gọi. Spring Data REST không công bố query resource của method đó.

Dùng **@RepositoryRestResource(exported = false)** khi cần ẩn cả repository. Với truy vấn đọc tốn tài nguyên nhưng vẫn cần công khai, kết hợp Pageable, giới hạn page size, query có index phù hợp, timeout và authorization. Với thao tác ghi dữ liệu, cung cấp command endpoint riêng theo HTTP semantics và kiểm soát quyền rõ ràng.

## Tài liệu tham khảo

- Spring Data REST Reference — Configuring the REST URL Path, Hiding Certain Repositories, Query Methods, or Fields: https://docs.spring.io/spring-data/rest/reference/customizing/configuring-the-rest-url-path.html
- Spring Data REST Reference — Repository resources, Search Resource and Query Method Resource: https://docs.spring.io/spring-data/rest/reference/repository-resources.html
- Spring Data REST Reference — Customizing supported HTTP methods and repository exposure: https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr.html
- Spring Data REST API — RestResource: https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/annotation/RestResource.html
- Spring Data JPA Reference — Modifying Queries: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html
