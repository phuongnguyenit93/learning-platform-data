# Rà soát toàn bộ phương thức save, delete và các biến thể được kế thừa trong Spring Data REST

## Mục tiêu

Spring Data REST có thể tự động xuất bản repository thành REST resource. Các thao tác ghi và xóa ở phía Java thường dựa trên những phương thức kế thừa từ Spring Data như save, saveAll, delete, deleteById và các biến thể theo store module.

Khi thiết kế xác thực và phân quyền, không nên chỉ nhìn vào POST hoặc DELETE trên giao diện HTTP. Cần lập danh sách toàn bộ đường có thể làm thay đổi dữ liệu:

- CRUD methods kế thừa từ CrudRepository, ListCrudRepository, PagingAndSortingRepository và JpaRepository.
- Các biến thể save/flush và delete/batch của JPA.
- Derived delete query, custom repository fragment và method tự khai báo.
- REST endpoint chuẩn của Spring Data REST.
- Association resource có thể thay đổi quan hệ.
- Service, controller, batch job, scheduled task và message consumer gọi repository trực tiếp.

Mục tiêu là xác định ai được phép tạo, cập nhật, xóa một entity hoặc xóa hàng loạt; kiểm tra quyền trên từng entity; và bảo đảm mọi đường ghi tuân thủ cùng quy tắc nghiệp vụ.

## 1. Phân biệt repository method và REST endpoint

Spring Data REST ánh xạ một số thao tác HTTP chuẩn tới collection, item và association resource:

| Resource | HTTP method thường gặp | Tác dụng |
|---|---|---|
| Collection, ví dụ /api/people | GET | Đọc collection. |
| Collection | POST | Tạo entity mới. |
| Item, ví dụ /api/people/42 | GET | Đọc entity. |
| Item | PUT | Thay representation theo semantics endpoint. |
| Item | PATCH | Cập nhật một phần representation. |
| Item | DELETE | Xóa entity. |
| Association resource | GET | Đọc quan hệ. |
| Association resource | PUT/POST/DELETE tùy loại quan hệ | Thay đổi hoặc gỡ liên kết. |

Các URI trên là bề mặt HTTP. Spring Data REST không tạo một URL riêng cho mọi method Java như saveAll, deleteAll hoặc saveAndFlush chỉ vì repository kế thừa chúng.

REST exporter dùng repository metadata và repository invoker để thực hiện các thao tác chuẩn. Method cụ thể được gọi có thể phụ thuộc phiên bản Spring Data REST, loại repository và store module. Vì vậy, khi bảo vệ method ở cấp repository, cần kiểm thử đúng HTTP request và repository proxy trong version thực tế.

Ngược lại, các method bulk vẫn có thể được gọi từ service, controller, job hoặc code nội bộ dù không có endpoint REST chuẩn tương ứng.

## 2. Rà soát CrudRepository

CrudRepository cung cấp nhóm thao tác cơ bản. Đây là danh sách khởi đầu khi rà soát:

| Method | Tác dụng | Rủi ro cần kiểm tra |
|---|---|---|
| save(entity) | Lưu entity mới hoặc cập nhật entity. | Có thể ghi property ngoài quyền của caller. |
| saveAll(entities) | Lưu nhiều entity. | Một lần gọi có thể tác động nhiều tenant hoặc owner. |
| deleteById(id) | Xóa theo ID. | ID có thể trỏ tới entity ngoài phạm vi quyền. |
| delete(entity) | Xóa entity được truyền vào. | Caller có thể truyền entity không được phép xóa. |
| deleteAllById(ids) | Xóa nhiều entity theo ID. | Cần kiểm tra toàn bộ ID và giới hạn số lượng. |
| deleteAll(entities) | Xóa các entity trong iterable. | Có thể xóa nhiều entity cùng lúc. |
| deleteAll() | Xóa toàn bộ repository. | Tác động diện rộng, thường chỉ dành cho tác vụ quản trị. |

Không giả định deleteById là đường xóa duy nhất. Nếu code có thể gọi delete(entity), deleteAllById hoặc deleteAll, chính sách phải bao phủ những method đó.

Tương tự, bảo vệ save không tự động chứng minh saveAll được bảo vệ. Hãy rà soát từng method thực sự có trong interface chain và những method được override.

## 3. ListCrudRepository và PagingAndSortingRepository

Tùy phiên bản Spring Data, repository có thể kế thừa ListCrudRepository và PagingAndSortingRepository.

ListCrudRepository cung cấp thao tác CRUD tương tự nhưng một số method trả List thay vì Iterable, ví dụ:

~~~java
<S extends T> List<S> saveAll(Iterable<S> entities);
List<T> findAll();
List<T> findAllById(Iterable<ID> ids);
~~~

saveAll vẫn là thao tác ghi hàng loạt và cần cùng mức kiểm soát với biến thể khác.

PagingAndSortingRepository chủ yếu bổ sung khả năng đọc phân trang và sắp xếp. Tuy không phải nhóm ghi, vẫn cần xem toàn bộ interface chain để biết repository thực sự kế thừa những gì.

Không dựa vào trí nhớ về một phiên bản Spring Data khác. Hierarchy, chữ ký method và kiểu trả về có thể thay đổi theo version. Hãy xem dependency đang dùng và interface thực tế của repository.

## 4. Các biến thể ghi và xóa của JpaRepository

JpaRepository bổ sung các method liên quan tới flush và batch.

### Nhóm save

| Method | Tác dụng | Kiểm soát cần có |
|---|---|---|
| save(entity) | Lưu một entity. | Quyền create/update và property được phép ghi. |
| saveAll(entities) | Lưu nhiều entity. | Quyền trên từng entity và giới hạn batch. |
| saveAndFlush(entity) | Lưu rồi flush persistence context. | Cùng policy với save; flush không thêm authorization. |
| saveAllAndFlush(entities) | Lưu nhiều entity rồi flush. | Cùng policy với saveAll; kiểm soát phạm vi bulk. |

### Nhóm delete

| Method | Tác dụng | Kiểm soát cần có |
|---|---|---|
| delete(entity) | Xóa một entity. | Kiểm tra entity, tenant, owner và trạng thái. |
| deleteById(id) | Xóa theo ID. | Không tin ID; kiểm tra quyền trên entity đích. |
| deleteAll(entities) | Xóa các entity được truyền vào. | Kiểm tra từng entity hoặc giới hạn tập dữ liệu. |
| deleteAllById(ids) | Xóa theo danh sách ID. | Kiểm tra toàn bộ ID và giới hạn số lượng. |
| deleteAll() | Xóa toàn bộ repository. | Quyền đặc biệt và quy trình quản trị. |
| deleteAllInBatch(entities) | Xóa nhiều entity bằng batch. | Kiểm soát tập dữ liệu và semantics JPA. |
| deleteAllByIdInBatch(ids) | Xóa theo ID bằng batch. | Kiểm soát tenant, ownership và số lượng. |
| deleteAllInBatch() | Xóa toàn bộ dữ liệu bằng batch. | Tác động rất rộng; không cho phép caller thông thường. |

Một số version có method cũ như deleteInBatch(entities), có thể đã deprecated hoặc được thay thế. Nếu codebase còn gọi method đó, vẫn phải đưa vào danh sách rà soát.

### Flush không phải ranh giới bảo mật

saveAndFlush và saveAllAndFlush thay đổi thời điểm đồng bộ persistence context với database. Chúng không tự thêm authorization hoặc validation.

Batch delete có thể chạy trực tiếp qua query, không tải từng entity để thực hiện đầy đủ lifecycle callback. Nó có thể không tuân theo cascade và entity lifecycle semantics giống xóa từng entity. Persistence context đang giữ entity có thể không phản ánh ngay trạng thái database sau bulk operation.

Trước khi dùng batch method, cần hiểu tác động tới transaction, foreign key, cascade, callback và flush/clear của JPA provider.

## 5. Không bỏ sót custom và derived mutation method

Repository còn có thể định nghĩa các đường thay đổi dữ liệu khác:

- Derived delete method như deleteByStatus hoặc removeByStatus.
- Query có @Modifying.
- Custom repository fragment.
- Default method trong interface.
- Store-specific method.
- Service dùng EntityManager hoặc template trực tiếp.
- Controller gọi repository theo logic riêng.

Ví dụ:

~~~java
public interface PersonRepository
        extends JpaRepository<Person, Long>, PersonRepositoryCustom {

    long deleteByStatus(PersonStatus status);
}
~~~

deleteByStatus là một đường xóa dù không có tên deleteAll. Nếu được gọi từ ứng dụng hoặc công bố qua custom API, cần kiểm tra quyền, tenant scope, số lượng bản ghi và audit.

Custom fragment cũng cần xem implementation. Method tên archive, purge, reassignOwner hoặc transferTenant vẫn có thể thay đổi dữ liệu dù không có chữ save/delete.

## 6. Method security trên repository method

Spring Security method security có thể bảo vệ lời gọi qua repository proxy. Bật method security:

~~~java
@Configuration
@EnableMethodSecurity
class SecurityConfiguration {
}
~~~

Có thể override method kế thừa trong repository để khai báo policy:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository
        extends JpaRepository<Person, Long> {

    @Override
    @PreAuthorize("hasAuthority('people:write')")
    <S extends Person> S save(S entity);

    @Override
    @PreAuthorize("hasAuthority('people:write')")
    List<Person> saveAll(Iterable<Person> entities);

    @Override
    @PreAuthorize("hasAuthority('people:delete')")
    void deleteById(Long id);

    @Override
    @PreAuthorize("hasAuthority('people:delete')")
    void delete(Person entity);
}
~~~

Đây là ví dụ minh họa. Chữ ký phải khớp interface và version thực tế; kiểu trả về của saveAll có thể là Iterable hoặc List tùy interface được kế thừa.

Nếu chỉ annotate deleteById, caller nội bộ vẫn có thể gọi delete(entity), deleteAllById, deleteAll hoặc batch delete. Cần khai báo policy cho toàn bộ method được sử dụng.

Ví dụ nhóm bulk delete cần được bảo vệ riêng:

~~~java
@Override
@PreAuthorize("hasAuthority('people:delete:bulk')")
void deleteAllById(Iterable<? extends Long> ids);

@Override
@PreAuthorize("hasAuthority('people:delete:bulk')")
void deleteAll();

@Override
@PreAuthorize("hasAuthority('people:delete:bulk')")
void deleteAllInBatch(Iterable<Person> entities);

@Override
@PreAuthorize("hasAuthority('people:delete:bulk')")
void deleteAllByIdInBatch(Iterable<Long> ids);

@Override
@PreAuthorize("hasAuthority('people:delete:bulk')")
void deleteAllInBatch();
~~~

Các chữ ký trên cần điều chỉnh theo JpaRepository version đang dùng. Nếu method không cần thiết, có thể loại bỏ khỏi service API hoặc ẩn khỏi REST exporter nếu không muốn client gọi qua HTTP.

### save không tự phân biệt create và update

save có thể được dùng cho cả entity mới và entity hiện có. Một annotation chung trên save không tự tách quyền create khỏi quyền update.

Nếu create và update có quyền khác nhau, nên dùng service command riêng hoặc policy kiểm tra entity state phù hợp. Service có thể kiểm tra ID/trạng thái, principal và tenant trước khi gọi repository.

## 7. Phân biệt method security và REST exposure

Hai cơ chế có mục đích khác nhau:

- REST exposure quyết định Spring Data REST có công bố HTTP operation hay không.
- Method security bảo vệ lời gọi method qua repository proxy, bao gồm caller nội bộ nếu đi qua proxy được bảo vệ.

Có thể ẩn inherited method khỏi Spring Data REST bằng override và exported=false:

~~~java
@Override
@RestResource(exported = false)
void deleteAll();
~~~

Cấu hình này điều khiển việc export method qua REST. Nó không ngăn code Java khác gọi repository.deleteAll().

Nếu toàn bộ repository không nên được công bố qua REST:

~~~java
@RepositoryRestResource(exported = false)
public interface InternalPersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

Ẩn repository là quyết định ở cấp resource. Nó không thay thế authorization cho service hoặc repository vẫn được inject và gọi nội bộ.

## 8. Giới hạn HTTP method bằng ExposureConfiguration

Spring Data REST cho phép điều khiển HTTP method trên collection và item resource theo domain type.

Ví dụ chỉ cho phép đọc Person qua repository REST:

~~~java
@Configuration
class RestExposureConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.getExposureConfiguration()
            .forDomainType(Person.class)
            .withCollectionExposure((metadata, methods) ->
                methods.disable(HttpMethod.POST))
            .withItemExposure((metadata, methods) ->
                methods.disable(
                    HttpMethod.PUT,
                    HttpMethod.PATCH,
                    HttpMethod.DELETE
                ));
    }
}
~~~

POST trên collection bị tắt; PUT/PATCH/DELETE trên item bị tắt. GET vẫn có thể được giữ lại.

Exposure configuration kiểm soát bề mặt HTTP của Spring Data REST. Nó không vô hiệu hóa saveAll, deleteAllInBatch hoặc lời gọi repository từ service/job. Association resource cũng cần được xem xét riêng nếu client có thể thay đổi quan hệ.

## 9. Tách quyền create, update, delete và bulk

Một policy dễ kiểm tra thường tách quyền theo tác vụ:

| Authority ví dụ | Phạm vi |
|---|---|
| people:read | Đọc collection và item. |
| people:create | Tạo Person. |
| people:update | Cập nhật Person hiện có. |
| people:delete | Xóa một Person trong phạm vi cho phép. |
| people:delete:bulk | Xóa nhiều Person. |
| people:admin | Thao tác quản trị đặc biệt. |

Tên authority là ví dụ; hãy thống nhất với permission model thực tế.

Không nhất thiết dùng một quyền people:write cho mọi method. Bulk delete thường có tác động lớn hơn xóa một item. deleteAll hoặc deleteAllInBatch có thể xóa toàn bộ repository, vì vậy cần quyền riêng hoặc không cung cấp cho luồng vận hành thông thường.

## 10. Kiểm tra tenant, owner và trạng thái trước khi ghi/xóa

Authorization không chỉ là kiểm tra role. Với dữ liệu multi-tenant hoặc ownership, phải kiểm tra entity đích.

Ví dụ service xóa Person:

~~~java
@Transactional
public void deletePerson(Long id, CurrentUser user) {
    Person person = repository.findById(id)
        .orElseThrow(() -> new EntityNotFoundException());

    if (!person.getTenantId().equals(user.tenantId())) {
        throw new AccessDeniedException("Not allowed");
    }

    if (!user.canDeletePeople()) {
        throw new AccessDeniedException("Not allowed");
    }

    repository.delete(person);
}
~~~

Thứ tự là tải entity, kiểm tra tenant/ownership, kiểm tra quyền nghiệp vụ rồi mới gọi delete.

Với bulk delete, không kiểm tra một ID đại diện. Cần xác định toàn bộ tập entity bị tác động, xác minh tất cả thuộc phạm vi được phép và áp dụng giới hạn số lượng. Với tập dữ liệu lớn, dùng service operation chuyên biệt có điều kiện truy vấn rõ ràng và audit đầy đủ.

Đối với save/update, kiểm tra trạng thái hiện tại lẫn dữ liệu mới. Ví dụ Person đã APPROVED có thể không được đổi owner hoặc tenant dù caller có quyền sửa profile.

## 11. Kiểm soát association update

Spring Data REST có thể cho phép client thay đổi association qua URI của entity đích. Vì vậy, không chỉ kiểm tra POST/PUT/PATCH/DELETE trên item mà còn kiểm tra association resource.

Khi gán một association, server cần xác minh:

- Principal có quyền sửa entity nguồn không.
- Entity nguồn thuộc tenant/owner nào.
- Entity đích có tồn tại và có thuộc phạm vi được phép không.
- Quan hệ có hợp lệ ở trạng thái workflow hiện tại không.
- Cascade, orphan removal hoặc foreign key có thể ảnh hưởng dữ liệu nào.

Ẩn association link không đủ để bảo vệ endpoint. Client có thể gọi URI trực tiếp. Kiểm thử cả association request và JSON binding vào property quan hệ.

## 12. Bulk operation và audit

Các method deleteAll, deleteAllById, deleteAllInBatch và deleteAllByIdInBatch có phạm vi tác động lớn. Nên:

- Xác định tập bản ghi trước khi thực hiện.
- Không tin danh sách ID từ client.
- Giới hạn số lượng bản ghi mỗi lần gọi.
- Dùng quyền riêng cho thao tác bulk.
- Ghi audit người thực hiện, điều kiện truy vấn, số bản ghi và thời điểm.
- Cân nhắc soft delete/archive nếu cần khôi phục.
- Kiểm tra foreign key và dữ liệu liên quan.
- Hiểu khác biệt giữa xóa entity từng cái và bulk query.

Batch delete có thể bỏ qua entity lifecycle callback và cascade semantics thông thường. Cần cân nhắc flush/clear và transaction boundary theo JPA provider.

Không dùng bulk method chỉ vì muốn tối ưu hiệu năng trước khi hiểu tác động nghiệp vụ và bảo mật.

## 13. Rà soát interface chain và codebase

Một quy trình rà soát:

1. Tìm tất cả repository interface.
2. Ghi lại interface cha: CrudRepository, ListCrudRepository, PagingAndSortingRepository, JpaRepository hoặc store-specific interface.
3. Liệt kê method ghi/xóa được kế thừa.
4. Kiểm tra method nào được override trong repository con.
5. Kiểm tra @PreAuthorize, @Secured, @RolesAllowed hoặc policy tương ứng.
6. Tìm custom repository fragment và default method.
7. Tìm derived delete method và query có @Modifying.
8. Tìm controller/service gọi save/delete trực tiếp.
9. Tìm batch job, scheduled task, listener và message consumer.
10. Kiểm tra Spring Data REST exposure configuration.
11. Kiểm thử lời gọi qua HTTP và qua repository proxy.

Các từ khóa tìm kiếm hữu ích:

~~~text
save(
saveAll(
saveAndFlush(
saveAllAndFlush(
delete(
deleteById(
deleteAll(
deleteAllById(
deleteAllInBatch(
deleteAllByIdInBatch(
deleteInBatch(
deleteBy
removeBy
@Modifying
~~~

Đây là điểm bắt đầu; cần mở rộng theo custom repository API và store module của ứng dụng.

## 14. Ma trận kiểm thử authorization

Không chỉ kiểm thử endpoint REST. Hãy kiểm tra method security trên repository proxy và service path.

Ma trận ví dụ:

| Caller | save | saveAll | deleteById | deleteAll | deleteAllInBatch |
|---|---|---|---|---|---|
| Anonymous | Từ chối | Từ chối | Từ chối | Từ chối | Từ chối |
| User chỉ có read | Từ chối | Từ chối | Từ chối | Từ chối | Từ chối |
| User có update | Theo scope | Theo policy bulk | Từ chối nếu thiếu quyền delete | Từ chối | Từ chối |
| Admin có bulk permission | Cho phép | Theo scope | Cho phép | Theo policy | Theo policy |

Đây là policy minh họa; thay bằng permission model của ứng dụng.

Các test nên bao gồm:

- POST collection khi không có quyền create.
- PUT/PATCH item khi không có quyền update.
- DELETE item khi không có quyền delete.
- Gọi save và saveAll qua repository proxy.
- Gọi từng biến thể delete được ứng dụng sử dụng.
- Bulk delete với ID thuộc tenant khác.
- deleteAll bằng user chỉ có quyền xóa một item.
- Method bị ẩn qua exposure không được chấp nhận qua REST.
- Lời gọi Java vẫn bị method security bảo vệ nếu method còn tồn tại.
- Database không đổi sau request bị từ chối.

Với Spring Security 6, @EnableMethodSecurity bật method security. Dự án cũ có thể dùng @EnableGlobalMethodSecurity(prePostEnabled = true); hãy dùng cấu hình tương thích với version thực tế.

## 15. Những lỗi thường gặp

1. **Chỉ bảo vệ save và deleteById.** saveAll, delete(entity), deleteAllById và batch delete vẫn có thể được gọi.
2. **Cho rằng mỗi repository method có một URL riêng.** Spring Data REST ánh xạ các thao tác HTTP chuẩn, không tự tạo endpoint cho mọi method Java.
3. **Ẩn HTTP method rồi cho rằng service không thể gọi repository.** Exposure chỉ kiểm soát bề mặt REST.
4. **Đánh dấu exported=false rồi cho rằng method Java bị vô hiệu hóa.** Nó điều khiển export, không chặn lời gọi nội bộ.
5. **Bỏ qua method kế thừa.** Cần rà soát toàn bộ interface chain.
6. **Bỏ qua saveAll.** Ghi nhiều entity có phạm vi tác động khác save đơn lẻ.
7. **Bỏ qua deleteAllInBatch.** Batch delete có thể xóa lượng dữ liệu lớn và có semantics JPA khác.
8. **Dùng cùng quyền cho xóa một item và xóa toàn repository.** Bulk operation cần quyền riêng.
9. **Tin ID do client gửi.** Phải kiểm tra entity đích, tenant và ownership.
10. **Cho rằng flush thêm bảo mật.** Flush chỉ đồng bộ persistence context với database.
11. **Quên custom fragment và derived delete query.** Method tên khác vẫn có thể xóa dữ liệu.
12. **Chỉ test HTTP endpoint.** Job/service nội bộ có thể gọi repository trực tiếp.
13. **Chỉ kiểm tra role.** Quyền có thể phụ thuộc tenant, owner hoặc workflow state.
14. **Dùng batch delete mà không hiểu cascade/lifecycle.** Bulk query có thể bỏ qua callback và cascade semantics.
15. **Dựa vào UI hoặc HAL link để bảo vệ thao tác.** Server phải thực thi quyền trên mỗi request và method invocation.

## 16. Checklist trước production

- Đã liệt kê đầy đủ interface cha và method kế thừa.
- Đã rà soát save, saveAll, saveAndFlush và saveAllAndFlush.
- Đã rà soát delete, deleteById, deleteAll và deleteAllById.
- Đã rà soát JPA batch delete và method deprecated còn được dùng.
- Đã rà soát derived delete, custom fragment và method tự khai báo.
- Đã xác định REST endpoint nào gọi thao tác ghi/xóa.
- Đã cấu hình exposure cho collection, item và association resource.
- Đã áp dụng method security cho các đường ghi cần bảo vệ.
- Đã tách quyền create, update, delete một item và bulk delete.
- Đã kiểm tra tenant, owner, trạng thái và association ở server.
- Đã giới hạn số lượng cho bulk operation.
- Đã ghi audit cho thao tác nhạy cảm.
- Đã kiểm thử qua HTTP và repository proxy.
- Đã xác nhận request bị từ chối không làm thay đổi database.
- Đã hiểu transaction, cascade, lifecycle callback và persistence context của batch operation.

## Tóm tắt

Khi rà soát xác thực và phân quyền cho Spring Data REST, cần kiểm tra toàn bộ phương thức ghi/xóa kế thừa từ repository, không chỉ endpoint POST và DELETE. Nhóm cơ bản gồm save, saveAll, delete, deleteById, deleteAll và deleteAllById. Với JPA, cần xem thêm saveAndFlush, saveAllAndFlush, deleteAllInBatch, deleteAllByIdInBatch và các biến thể còn tồn tại theo version.

Exposure configuration và @RestResource(exported = false) kiểm soát việc công bố API. @PreAuthorize cùng method security bảo vệ lời gọi repository/service. Validation, tenant/ownership checks và domain rules quyết định thay đổi có hợp lệ hay không. Bulk operation cần policy riêng vì có thể ảnh hưởng nhiều bản ghi và có semantics persistence khác xóa từng entity.

Hãy rà soát interface chain, custom repository, controller, service, batch job và scheduled task; sau đó kiểm thử từng đường gọi với principal khác nhau và xác nhận database không đổi khi thao tác bị từ chối.

## Tài liệu tham khảo

- [Spring Data Commons — Repository Core Concepts](https://docs.spring.io/spring-data/commons/reference/repositories/core-concepts.html)
- [Spring Data Commons — CrudRepository API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/CrudRepository.html)
- [Spring Data JPA — JpaRepository API](https://docs.spring.io/spring-data/jpa/docs/current/api/org/springframework/data/jpa/repository/JpaRepository.html)
- [Spring Data REST — Reference Documentation](https://docs.spring.io/spring-data/rest/reference/)
- [Spring Data REST — Configuring the REST URL Path and Exposure](https://docs.spring.io/spring-data/rest/reference/customizing/configuring-the-rest-url-path.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
