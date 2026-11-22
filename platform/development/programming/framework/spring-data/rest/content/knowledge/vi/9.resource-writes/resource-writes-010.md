# DELETE tài nguyên và ảnh hưởng của ràng buộc dữ liệu

## Mục tiêu

Spring Data REST cho phép client xóa một entity thông qua HTTP DELETE trên item resource. Ví dụ, nếu repository quản lý Customer và collection path là /customers, item của khách hàng có ID 1001 được truy cập tại:

    DELETE /customers/1001

Request này có thể làm mất dữ liệu thật trong persistence store. Kết quả phụ thuộc vào phương thức delete mà repository công bố, trạng thái entity, quan hệ JPA, foreign key, cascade, trigger và quy tắc nghiệp vụ của ứng dụng.

Khi thiết kế hoặc điều tra DELETE, cần trả lời:

1. URL đang trỏ đến item resource hay association resource?
2. Repository có công bố phương thức xóa nào?
3. Entity có được phép xóa theo quy tắc nghiệp vụ không?
4. Entity khác có đang tham chiếu đến entity cần xóa không?
5. JPA cascade, orphan removal hoặc database ON DELETE có tác động gì?
6. Nếu database từ chối thao tác, transaction và HTTP response sẽ ra sao?

## 1. DELETE trên item resource

Spring Data REST tạo item resource cho từng entity dưới collection resource. Nếu collection là /customers, item thường có URI /customers/{id}.

Ví dụ repository:

    @RepositoryRestResource(path = "customers")
    public interface CustomerRepository
            extends CrudRepository<Customer, Long> {
    }

Request xóa một item:

    curl -i -X DELETE \
      -H "Accept: application/hal+json" \
      http://localhost:8080/customers/1001

DELETE trên item resource yêu cầu xóa entity được đại diện bởi URI đó. Đây là thao tác xóa entity trong repository, khác với việc chỉ bỏ một liên kết association.

### 1.1. Phân biệt item DELETE và association DELETE

Hai URL sau có ý nghĩa khác nhau:

| Request | Ý nghĩa |
|---|---|
| DELETE /customers/1001 | Xóa entity Customer có ID 1001 |
| DELETE /customers/1001/orders | Gỡ liên kết association orders khỏi Customer 1001 |

DELETE trên association resource chỉ unbind association. Nó không mặc nhiên xóa entity được liên kết. Nếu muốn xóa một Order, client phải gọi DELETE trên item resource của Order, theo URL item mà HAL cung cấp.

Phân biệt này đặc biệt quan trọng với quan hệ one-to-many và many-to-many. Gỡ một phần tử khỏi collection association và xóa chính entity là hai thay đổi dữ liệu khác nhau.

### 1.2. HTTP response thành công

Theo mặc định của Spring Data REST, response DELETE phụ thuộc vào header Accept:

- Khi request có Accept header, response có thể trả representation của entity cùng status 200 OK.
- Khi request không có Accept header, response thành công thường không có body và trả 204 No Content.

Có thể thay đổi hành vi này qua RepositoryRestConfiguration.setReturnBodyOnDelete(...).

Ví dụ cấu hình trả body sau khi xóa:

    @Component
    public class RestConfiguration implements RepositoryRestConfigurer {

        @Override
        public void configureRepositoryRestConfiguration(
                RepositoryRestConfiguration config,
                CorsRegistry cors) {
            config.setReturnBodyOnDelete(true);
        }
    }

Cần phân biệt status của thao tác DELETE với kết quả xóa ở database. Response 200 hoặc 204 chỉ nên được trả khi thao tác được xử lý thành công theo contract của endpoint.

### 1.3. DELETE không được export

Spring Data REST chỉ công bố HTTP method khi repository có phương thức tương ứng và phương thức đó được phép export.

Nếu repository không có phương thức delete phù hợp, hoặc phương thức delete bị đánh dấu exported = false, item resource không hỗ trợ DELETE và có thể trả:

    405 Method Not Allowed

Collection resource chỉ hỗ trợ GET và POST theo mặc định. Không gửi DELETE đến /customers để xóa hàng loạt. DELETE chuẩn của item resource phải trỏ đến một item cụ thể.

## 2. Phương thức repository được dùng

Spring Data REST ánh xạ DELETE của item resource tới các phương thức xóa repository. Tài liệu Repository resources mô tả thứ tự tìm phương thức như sau:

1. delete(entity)
2. delete(id)
3. delete(iterable)

Các chữ ký công khai cụ thể thay đổi theo thế hệ Spring Data. Trong CrudRepository hiện đại, các phương thức thường gặp là:

    void delete(T entity);
    void deleteById(ID id);
    void deleteAllById(Iterable<? extends ID> ids);
    void deleteAll(Iterable<? extends T> entities);
    void deleteAll();

Không nên giả định mọi phiên bản đều có cùng tên method. Hãy kiểm tra interface CrudRepository và Spring Data REST version mà ứng dụng đang dùng.

### 2.1. Xóa entity hay xóa theo ID

Có hai cách phổ biến:

- Xóa entity: repository nhận một đối tượng entity rồi xóa nó.
- Xóa theo ID: repository nhận định danh và tìm cách xóa bản ghi tương ứng.

Với Spring Data JPA, xóa entity thường đi qua EntityManager.remove trên entity được quản lý. Repository implementation có thể tải entity trước khi xóa để hỗ trợ lifecycle event và optimistic locking.

Với deleteById, CrudRepository hiện đại quy định rằng nếu ID không tồn tại trong persistence store thì thao tác có thể được bỏ qua một cách im lặng. Tuy nhiên, luồng REST có thể cần tải entity để tạo event hoặc xử lý item resource. Vì vậy, không suy luận status code chỉ từ Javadoc của một repository method; hãy kiểm tra hành vi của Spring Data REST version thực tế.

### 2.2. Xóa nhiều entity không phải DELETE item

Các phương thức như deleteAll(), deleteAllById(...) hoặc deleteAll(Iterable) có phạm vi rộng hơn thao tác xóa một item.

Không nên tự tạo một endpoint DELETE collection để gọi deleteAll() nếu API không có yêu cầu rõ ràng, giới hạn quyền và cơ chế xác nhận. Xóa hàng loạt có thể ảnh hưởng số lượng lớn dữ liệu và cần một contract riêng, thường qua service hoặc endpoint nghiệp vụ được thiết kế rõ ràng.

### 2.3. Ẩn DELETE khỏi REST API

Nếu repository vẫn cần phương thức delete cho logic nội bộ nhưng không muốn client gọi qua HTTP, có thể:

- Đánh dấu các phương thức delete phù hợp bằng @RestResource(exported = false), dựa trên chữ ký của Spring Data version đang dùng.
- Dùng RepositoryRestConfiguration.getExposureConfiguration() để tắt HTTP DELETE cho item resources.

Ví dụ tắt DELETE trên tất cả item resources:

    @Component
    public class RestConfiguration implements RepositoryRestConfigurer {

        @Override
        public void configureRepositoryRestConfiguration(
                RepositoryRestConfiguration config,
                CorsRegistry cors) {

            config.getExposureConfiguration()
                .withItemExposure((metadata, methods) ->
                    methods.disable(HttpMethod.DELETE));
        }
    }

Cấu hình trên áp dụng cho item resources nói chung. Nếu chỉ muốn chặn xóa một domain type, hãy dùng quy tắc exposure theo domain type phù hợp với API của phiên bản đang dùng hoặc tổ chức repository để không công bố delete method cho type đó.

## 3. Luồng xử lý khi DELETE được gọi

Một luồng xóa điển hình có thể được hiểu qua các bước sau:

1. Client gửi DELETE đến item URI.
2. Spring MVC định tuyến request đến item resource của repository.
3. Framework chuyển ID trong URI thành kiểu ID backend và xác định entity cần xử lý.
4. Spring Data REST phát hành BeforeDeleteEvent.
5. Repository delete method được gọi.
6. Persistence provider đánh dấu entity cần xóa và đồng bộ thay đổi xuống database khi flush hoặc commit.
7. Nếu thao tác thành công, Spring Data REST phát hành AfterDeleteEvent và tạo response theo cấu hình.
8. Nếu thao tác thất bại, transaction có thể rollback và exception được chuyển qua cơ chế xử lý lỗi của ứng dụng.

Chi tiết nội bộ có thể khác theo store module và phiên bản. Điều quan trọng là DELETE không chỉ là xóa một dòng SQL: repository, persistence context, event handler và database constraints đều có thể tham gia.

## 4. Foreign key và ràng buộc tham chiếu

Foreign key bảo đảm một hàng con không tham chiếu đến hàng cha không tồn tại. Ví dụ:

- Customer là bảng cha.
- Order có cột customer_id tham chiếu Customer.id.
- Một Customer có thể được tham chiếu bởi nhiều Order.

Nếu Customer 1001 vẫn có Order tham chiếu đến nó, database có thể từ chối DELETE Customer 1001 để bảo vệ tính toàn vẹn dữ liệu.

Ví dụ quan hệ:

    Customer
      id (PK)
       |
       +---- Order.customer_id (FK)

Khi client gửi DELETE /customers/1001, database có thể báo lỗi foreign key constraint nếu còn Order tham chiếu và foreign key được cấu hình RESTRICT hoặc NO ACTION.

### 4.1. Các chính sách ON DELETE thường gặp

| Chính sách | Kết quả khi xóa hàng cha |
|---|---|
| RESTRICT | Từ chối xóa nếu còn hàng con tham chiếu |
| NO ACTION | Kiểm tra ràng buộc theo quy tắc của database; thường từ chối nếu tham chiếu còn tồn tại |
| CASCADE | Database xóa các hàng con tham chiếu |
| SET NULL | Database đặt foreign key ở hàng con thành NULL nếu cột cho phép |
| SET DEFAULT | Database đặt foreign key về giá trị mặc định nếu được hỗ trợ và hợp lệ |

Không phải database nào cũng hỗ trợ mọi chính sách theo cùng cách. Thời điểm kiểm tra constraint cũng có thể khác, ví dụ kiểm tra ngay khi statement chạy hoặc khi transaction commit nếu constraint được khai báo deferred.

### 4.2. Khi nào nên giữ RESTRICT?

RESTRICT phù hợp khi entity con là dữ liệu nghiệp vụ độc lập cần được giữ lại. Ví dụ, không nên xóa Customer nếu các Order đã phát sinh cần được lưu để kiểm toán, hóa đơn hoặc báo cáo.

Trong trường hợp này, ứng dụng có thể:

- Từ chối xóa và yêu cầu người dùng xử lý các Order liên quan.
- Chuyển Customer sang trạng thái inactive hoặc archived.
- Gỡ quan hệ chỉ khi nghiệp vụ cho phép và dữ liệu con có thể tồn tại độc lập.

Không nên bật CASCADE chỉ để tránh lỗi foreign key. Hãy xác định rõ liệu dữ liệu con có thực sự mất ý nghĩa khi entity cha bị xóa hay không.

## 5. JPA CascadeType.REMOVE và orphanRemoval

JPA cung cấp cascade để lan truyền thao tác persistence từ entity này sang entity liên quan. Hai cấu hình thường bị nhầm là CascadeType.REMOVE và orphanRemoval.

### 5.1. CascadeType.REMOVE

CascadeType.REMOVE truyền thao tác remove từ entity nguồn sang entity đích của association được cấu hình cascade.

Ví dụ, một Order sở hữu các OrderLine và OrderLine không có ý nghĩa độc lập:

    @Entity
    public class Order {

        @OneToMany(
            mappedBy = "order",
            cascade = CascadeType.REMOVE
        )
        private List<OrderLine> lines = new ArrayList<>();
    }

Khi xóa Order, JPA cũng xóa các OrderLine được liên kết theo cascade remove.

Cascade có hướng. Xóa một child không tự động xóa parent chỉ vì quan hệ parent-child tồn tại. Với quan hệ one-to-many, thường cấu hình cascade từ parent sang child, vì parent quản lý vòng đời của child.

Jakarta Persistence quy định CascadeType.REMOVE nên được dùng cho quan hệ OneToOne hoặc OneToMany để bảo đảm tính portable. Không tùy tiện đặt REMOVE trên ManyToOne hoặc ManyToMany.

### 5.2. orphanRemoval

orphanRemoval = true dùng cho quan hệ OneToOne và OneToMany. Khi một child bị loại khỏi quan hệ của owner, JPA áp dụng thao tác remove cho child đó khi persistence context flush.

Ví dụ:

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

Nếu OrderLine bị loại khỏi collection lines và không còn được gắn với Order, nó được xem là orphan và sẽ bị xóa.

Phân biệt:

- CascadeType.REMOVE: xóa parent thì lan truyền thao tác xóa sang child.
- orphanRemoval: bỏ child khỏi quan hệ sở hữu thì child bị xóa.
- Gỡ association qua REST: thay đổi liên kết theo API association resource; kết quả cuối cùng còn phụ thuộc mapping và persistence semantics.

orphanRemoval phù hợp với child thuộc sở hữu riêng của parent. Không dùng nó cho đối tượng được chia sẻ bởi nhiều aggregate hoặc cần tồn tại độc lập.

### 5.3. CascadeType.ALL

CascadeType.ALL bao gồm REMOVE cùng các thao tác cascade khác như PERSIST, MERGE, REFRESH và DETACH.

Không nên chọn ALL chỉ vì muốn xóa child cùng parent. Nếu chỉ cần xóa lan truyền, CascadeType.REMOVE thể hiện ý định hẹp và rõ hơn.

## 6. Database cascade khác JPA cascade

JPA cascade và database ON DELETE CASCADE là hai cơ chế khác nhau.

| Cơ chế | Nơi thực thi | Hành vi |
|---|---|---|
| CascadeType.REMOVE | JPA persistence provider | Lan truyền EntityManager.remove qua association |
| orphanRemoval | JPA persistence provider | Xóa child khi child bị tách khỏi association owner |
| ON DELETE CASCADE | Database foreign key | Database tự xóa hàng con khi hàng cha bị xóa |

Hibernate có annotation riêng @OnDelete(action = CASCADE) để tạo foreign key với ON DELETE CASCADE. Đây là extension của Hibernate, không phải annotation Jakarta Persistence chuẩn.

Khi database tự xóa hàng con, persistence context có thể không biết toàn bộ các hàng đã bị xóa. Các entity đang được quản lý hoặc second-level cache có thể mất đồng bộ nếu ứng dụng không xử lý phù hợp.

Vì vậy, khi chọn database cascade:

- Xác nhận DDL thật sự tạo foreign key với ON DELETE CASCADE.
- Kiểm tra cache và persistence context.
- Xác nhận JPA lifecycle callbacks có cần chạy cho từng child hay không.
- Kiểm tra trigger và audit log.
- Không giả định database cascade sẽ phát ra các JPA entity callbacks giống thao tác remove từng entity.

## 7. Lỗi ràng buộc dữ liệu và transaction

Khi database từ chối DELETE do foreign key hoặc constraint khác, persistence provider thường phát sinh persistence exception. Spring có thể dịch lỗi này thành DataIntegrityViolationException hoặc một DataAccessException phù hợp.

Ví dụ:

    try {
        customerRepository.deleteById(customerId);
        customerRepository.flush();
    } catch (DataIntegrityViolationException ex) {
        // Translate the failure into the API's documented error response.
    }

Ví dụ trên chỉ phù hợp khi repository là JpaRepository và code chạy trong một service có transaction được quản lý đúng. Không bắt exception rồi tiếp tục transaction đã bị đánh dấu rollback-only.

### 7.1. Vì sao lỗi có thể xuất hiện lúc flush hoặc commit?

JPA thường trì hoãn SQL cho đến khi persistence context flush. Vì vậy, lời gọi delete có thể chưa gửi DELETE statement ngay tại thời điểm method trả về.

Lỗi foreign key có thể xuất hiện:

- Ngay trong lời gọi repository nếu provider flush sớm.
- Khi code gọi EntityManager.flush hoặc JpaRepository.flush.
- Khi transaction commit và framework thực hiện flush cuối cùng.

Nếu constraint chỉ được kiểm tra khi commit, catch exception bên trong một method trước commit có thể không bắt được lỗi cuối cùng. Hãy đặt exception handling ở ranh giới transaction phù hợp.

### 7.2. Transaction rollback

Khi DELETE thất bại và transaction rollback:

- Database không giữ một phần thay đổi của transaction đã rollback.
- Entity đã bị đánh dấu removed trong persistence context có thể cần xử lý theo vòng đời của transaction.
- Không nên tiếp tục sử dụng persistence context đã lỗi như thể thao tác xóa thành công.
- API cần trả lỗi nhất quán để client biết entity chưa được xóa thành công.

Không gửi thông báo "đã xóa" hoặc phát event ra hệ thống bên ngoài trước khi transaction commit thành công. Nếu cần phát message sau khi xóa bền vững, cân nhắc TransactionalEventListener với phase AFTER_COMMIT hoặc transactional outbox.

### 7.3. HTTP status khi constraint vi phạm

DataIntegrityViolationException là exception ở tầng truy cập dữ liệu. Spring Data REST và Spring MVC có thể ánh xạ exception qua các handler khác nhau tùy phiên bản và cấu hình.

Không nên giả định mọi lỗi foreign key luôn tự động trả 409 Conflict. Nếu API cần contract rõ ràng, hãy cấu hình exception handler để chuyển các trường hợp phù hợp thành status code có chủ đích, ví dụ:

- 409 Conflict: entity vẫn đang được tham chiếu hoặc trạng thái nghiệp vụ ngăn xóa.
- 422 Unprocessable Content: request hợp lệ về cú pháp nhưng không thể thực hiện theo quy tắc nghiệp vụ, nếu API chọn dùng status này.
- 404 Not Found: resource không tồn tại theo contract của endpoint.
- 405 Method Not Allowed: DELETE không được export hoặc không được phép trên resource đó.

Response body nên có mã lỗi ổn định và thông điệp dễ hiểu. Không trả raw SQL, tên bảng nội bộ, giá trị nhạy cảm hoặc stack trace cho client.

## 8. Spring Data REST events và JPA lifecycle callbacks

Spring Data REST phát ra các event trong quá trình thao tác repository, gồm:

- BeforeDeleteEvent: trước khi entity được xóa.
- AfterDeleteEvent: sau khi thao tác xóa entity được thực hiện.

Có thể dùng annotated handler:

    @Component
    @RepositoryEventHandler(Customer.class)
    public class CustomerDeleteHandler {

        @HandleBeforeDelete
        public void beforeDelete(Customer customer) {
            if (customer.isProtected()) {
                throw new IllegalStateException(
                    "Customer cannot be deleted");
            }
        }

        @HandleAfterDelete
        public void afterDelete(Customer customer) {
            // Record application-level notification.
        }
    }

BeforeDelete handler có thể kiểm tra quy tắc nghiệp vụ và từ chối request bằng exception. Hãy ánh xạ exception đó thành API error phù hợp.

JPA cũng có entity lifecycle callbacks như @PreRemove và @PostRemove:

    @PreRemove
    public void beforeRemove() {
        // Local entity lifecycle validation or bookkeeping.
    }

Khác biệt:

| Cơ chế | Phạm vi |
|---|---|
| BeforeDeleteEvent / AfterDeleteEvent | Event của Spring Data REST khi REST exporter xử lý entity |
| @HandleBeforeDelete / @HandleAfterDelete | Handler có thể lọc theo domain type |
| @PreRemove / @PostRemove | Lifecycle callback của JPA entity khi persistence provider thực hiện remove |

Không phải mọi cách xóa dữ liệu đều đi qua cùng một pipeline. Bulk JPQL delete, native SQL hoặc database cascade có thể bỏ qua một số entity lifecycle callbacks. Hãy chọn cơ chế phù hợp với đường xóa mà ứng dụng thực sự sử dụng.

Spring application events mặc định được xử lý đồng bộ. Tuy nhiên, AfterDeleteEvent không nên được xem như bằng chứng rằng transaction đã commit bền vững. Với side effect bên ngoài như gửi email, gọi webhook hoặc publish message, hãy xử lý ở ranh giới AFTER_COMMIT hoặc dùng outbox để tránh thông báo đã xóa trong khi transaction cuối cùng rollback.

## 9. Thiết kế soft delete

Soft delete không xóa hàng vật lý khỏi database. Thay vào đó, ứng dụng đánh dấu entity là deleted hoặc archived.

Ví dụ:

    @Entity
    public class Customer {

        @Id
        private Long id;

        private boolean deleted;
        private Instant deletedAt;
    }

Khi client gửi DELETE, service có thể cập nhật deleted = true và deletedAt thay vì gọi repository delete vật lý.

Cần thiết kế rõ:

- GET collection và GET item có ẩn entity soft-deleted không?
- Có endpoint restore không?
- Unique constraint có tính đến entity đã soft-delete không?
- Các association và query method có loại trừ dữ liệu đã xóa không?
- Ai được phép xem dữ liệu archived?
- Audit log giữ thông tin người xóa và thời điểm xóa ở đâu?

Spring Data REST mặc định hiểu DELETE là thao tác xóa repository. Soft delete thường cần custom repository implementation, service hoặc custom REST endpoint để thay đổi trạng thái theo nghiệp vụ. Không nên chỉ đổi tên một method rồi giả định mọi resource và query đều tự động lọc dữ liệu đã xóa.

## 10. Bảo vệ endpoint DELETE

Export một repository qua REST không đồng nghĩa mọi người dùng đều được quyền xóa entity.

Cần cấu hình authorization riêng cho DELETE:

- Chỉ role phù hợp mới được xóa.
- Kiểm tra tenant hoặc ownership trước khi xóa.
- Không tin ID do client gửi là đủ để chứng minh quyền truy cập.
- Xem xét CSRF nếu API dùng cookie-based authentication.
- Ghi audit actor, entity ID, thời điểm và lý do xóa theo yêu cầu nghiệp vụ.
- Không để event handler thực hiện side effect không thể rollback trước khi transaction commit.

Với dữ liệu quan trọng, có thể cần quy trình xác nhận, trạng thái archived hoặc phê duyệt thay vì xóa vật lý trực tiếp.

## 11. Checklist điều tra DELETE thất bại

Khi DELETE không thành công, kiểm tra theo thứ tự:

1. URI có phải item resource của entity cần xóa không?
2. Repository có method delete phù hợp và method đó có được export không?
3. HTTP DELETE có bị tắt bởi RepositoryRestConfiguration hoặc Spring Security không?
4. ID trong URI có chuyển đổi được thành backend ID không?
5. Entity có tồn tại trong repository không?
6. BeforeDelete handler hoặc business rule có từ chối thao tác không?
7. Có entity khác đang tham chiếu qua foreign key không?
8. Mapping JPA có CascadeType.REMOVE hoặc orphanRemoval phù hợp không?
9. Database foreign key đang dùng RESTRICT, NO ACTION, CASCADE hay SET NULL?
10. Có trigger, check constraint hoặc rule database khác không?
11. Exception xảy ra tại repository call, flush hay transaction commit?
12. Transaction đã rollback chưa?
13. HTTP status và response body có đúng API contract không?
14. Nếu dùng cache hoặc message event, dữ liệu ngoài database có được đồng bộ sau commit không?

Không nên sửa lỗi bằng cách tắt foreign key hoặc bật cascade một cách mù quáng. Trước hết cần xác định quan hệ dữ liệu và ý nghĩa nghiệp vụ của từng entity.

## 12. Kiểm thử DELETE

Một integration test tốt nên xác minh cả HTTP response và trạng thái persistence.

Các trường hợp nên có:

| Trường hợp | Điều cần xác nhận |
|---|---|
| Xóa entity tồn tại, không có dependent rows | Repository xóa entity và response đúng cấu hình |
| Xóa entity không tồn tại | Status và body theo contract thực tế |
| Xóa entity đang được child tham chiếu với RESTRICT | Database từ chối, transaction rollback |
| Xóa parent có CascadeType.REMOVE | Các child được xóa theo mapping |
| Xóa parent có orphanRemoval | Child bị tách khỏi association được xóa khi flush |
| Xóa association resource | Chỉ unbind association, không mặc nhiên xóa entity liên quan |
| Repository không export delete | Item DELETE trả 405 |
| BeforeDelete handler từ chối | Không có thay đổi bền vững và API trả lỗi nghiệp vụ |
| Constraint lỗi lúc commit | Exception được bắt ở ranh giới transaction phù hợp |
| Soft delete | Entity được đánh dấu deleted và không còn xuất hiện trong query công khai |

Ví dụ kiểm thử trạng thái:

    mockMvc.perform(delete("/customers/{id}", customerId))
        .andExpect(status().isNoContent());

    assertThat(customerRepository.existsById(customerId)).isFalse();

Ví dụ trên giả định cấu hình không trả response body và entity không có ràng buộc ngăn xóa. Trong test thực tế, hãy dùng status code và trạng thái dữ liệu mà API đã định nghĩa.

## Tài liệu tham khảo

- [Spring Data REST — Repository resources, item DELETE and association DELETE](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Customizing supported HTTP methods](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html)
- [Spring Data REST — Events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [Spring Data Commons — CrudRepository API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/CrudRepository.html)
- [Spring Data JPA — Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html)
- [Jakarta Persistence — Entity removal and orphan removal](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html)
- [Hibernate — OnDelete annotation](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/annotations/OnDelete.html)
- [Spring Framework — DataIntegrityViolationException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/DataIntegrityViolationException.html)
