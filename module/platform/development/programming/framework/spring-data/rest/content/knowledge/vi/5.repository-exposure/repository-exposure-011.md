# Rà soát các biến thể phương thức delete và thiết kế repository chỉ đọc

## 1. Vì sao cần rà soát API xóa trước khi công bố repository?

Spring Data cung cấp các thao tác xóa ở nhiều mức: xóa một entity, xóa theo ID, xóa một tập entity hoặc ID, xóa toàn bộ dữ liệu và xóa theo điều kiện. Những phương thức này có ý nghĩa khác nhau về đầu vào, chi phí thực thi và tác động lên vòng đời entity.

Khi dùng Spring Data REST, repository có thể được công bố thành HTTP API. Vì vậy, việc kế thừa một interface có sẵn các phương thức ghi cũng ảnh hưởng đến bề mặt API. Cần xác định rõ:

- Repository có thật sự cần cho phép xóa không?
- Nếu có, ai được xóa và được xóa ở phạm vi nào?
- Phương thức Java nào đang tồn tại do kế thừa từ interface?
- Phương thức nào được Spring Data REST công bố thành endpoint?
- Cách nào bảo đảm API chỉ đọc ngay cả khi có controller hoặc đường truy cập khác?

Một repository chỉ đọc nên được thiết kế từ hợp đồng Java tối thiểu, sau đó mới cấu hình việc công bố qua Spring Data REST.

## 2. Các biến thể delete trong CrudRepository

Trong Spring Data Commons, CrudRepository định nghĩa các nhóm thao tác xóa phổ biến sau (chữ ký cụ thể có thể khác đôi chút giữa các phiên bản):

~~~~java
void deleteById(ID id);
void delete(T entity);
void deleteAllById(Iterable<? extends ID> ids);
void deleteAll(Iterable<? extends T> entities);
void deleteAll();
~~~~

Ý nghĩa của từng phương thức:

| Phương thức | Phạm vi xóa | Khi nên dùng |
|---|---|---|
| deleteById(id) | Một entity được nhận diện bằng ID | Client hoặc service chỉ có ID và muốn xóa một tài nguyên |
| delete(entity) | Entity được truyền vào | Đã có entity và muốn yêu cầu xóa chính entity đó |
| deleteAllById(ids) | Các entity có ID nằm trong tập đầu vào | Xóa một nhóm bản ghi đã xác định bằng ID |
| deleteAll(entities) | Các entity được truyền vào | Xóa một nhóm đối tượng đã được tải hoặc chọn trước |
| deleteAll() | Toàn bộ entity của repository | Chỉ dùng trong tác vụ quản trị có phạm vi và quyền hạn được kiểm soát chặt |

Các hợp đồng CRUD thường quy định rằng nếu entity không tồn tại thì thao tác xóa có thể được bỏ qua mà không báo lỗi. Tuy nhiên, cần đọc hợp đồng và hành vi của store cụ thể nếu ứng dụng phụ thuộc vào việc phân biệt “đã xóa” với “không tìm thấy”.

### Xóa theo ID và xóa theo entity

**deleteById(id)** phù hợp khi lớp gọi chỉ có khóa định danh. Repository tự thực hiện phần tìm và xóa cần thiết theo implementation của store.

**delete(entity)** nhận một đối tượng. Với JPA, entity có thể detached; implementation phải xử lý trạng thái quản lý và kiểm tra entity tương ứng trong persistence context hoặc database. Không nên giả định truyền một object có ID là luôn tương đương với một câu lệnh SQL DELETE đơn giản.

Hai phương thức có thể dẫn tới cùng kết quả nghiệp vụ, nhưng đường thực thi và chi phí có thể khác nhau. Nếu cần kiểm tra quyền sở hữu, trạng thái hoặc điều kiện trước khi xóa, nên đặt logic đó trong service hoặc một thao tác nghiệp vụ có transaction rõ ràng.

### Xóa nhiều bản ghi

**deleteAllById(ids)** nhận các ID; **deleteAll(entities)** nhận các entity. Hai overload này giúp biểu đạt rõ đầu vào của yêu cầu, nhưng tên phương thức không bảo đảm implementation sẽ phát ra một câu lệnh bulk DELETE duy nhất.

Với nhiều store, thao tác xóa theo danh sách có thể lặp qua từng phần tử. Vì vậy, cần đo hiệu năng với kích thước lô thực tế và kiểm tra cách implementation của module đang dùng xử lý batch, transaction và callback.

### Xóa toàn bộ

**deleteAll()** có phạm vi ảnh hưởng lớn nhất: toàn bộ entity thuộc repository. Không nên đưa thao tác này vào API công khai nếu nghiệp vụ không có yêu cầu cụ thể. Trong ứng dụng nhiều tenant, cần đặc biệt bảo đảm thao tác không vượt khỏi phạm vi tenant hiện tại.

Với Spring Data JPA, cần phân biệt các phương thức xóa từng entity với các biến thể bulk như **deleteAllInBatch()** hoặc **deleteAllByIdInBatch(ids)** của JpaRepository. Bulk operation có thể thực thi trực tiếp ở database và bỏ qua một số hành vi gắn với vòng đời từng entity, chẳng hạn callback hoặc cascade ở cấp entity. Sau bulk operation, persistence context đang giữ entity cũ cũng có thể không còn phản ánh trạng thái database. Chỉ dùng khi hiểu rõ khác biệt đó và quản lý transaction/persistence context phù hợp.

## 3. Derived delete query và bulk delete

Spring Data hỗ trợ query method có tên bắt đầu bằng **deleteBy** hoặc **removeBy**, ví dụ:

~~~~java
long deleteByStatus(Status status);
void removeByExpiredAtBefore(Instant cutoff);
~~~~

Đây là query method được phân tích từ tên phương thức. Với Spring Data JPA, derived delete query thường tìm các entity phù hợp rồi xóa từng entity, nhờ đó có thể giữ hành vi vòng đời entity như khi xóa từng đối tượng. Kiểu trả về được hỗ trợ phụ thuộc vào module và phiên bản; thường gặp là void hoặc số lượng bản ghi bị xóa.

Một cách khác là khai báo bulk delete bằng @Modifying và @Query:

~~~~java
@Modifying
@Query("delete from Session s where s.expiredAt < :cutoff")
int deleteExpired(@Param("cutoff") Instant cutoff);
~~~~

Bulk JPQL có thể xóa trực tiếp ở database hiệu quả hơn khi có nhiều bản ghi. Đổi lại, nó không đi qua quy trình xóa từng entity, nên callback, cascade ở cấp entity và trạng thái persistence context cần được cân nhắc riêng.

| Tiêu chí | Derived delete query | Bulk delete bằng @Modifying @Query |
|---|---|---|
| Cách xác định dữ liệu | Phân tích tên method | JPQL/SQL do lập trình viên khai báo |
| Thực thi | Thường tải entity phù hợp rồi xóa từng entity (đặc biệt với JPA) | Thực hiện câu lệnh xóa theo tập ở database |
| Vòng đời entity | Có thể chạy callback cho từng entity | Không chạy callback xóa từng entity như thao tác remove thông thường |
| Hiệu năng với tập lớn | Có thể tốn bộ nhớ và nhiều thao tác | Thường phù hợp hơn cho bulk operation |
| Trạng thái persistence context | Entity được xử lý theo vòng đời thông thường | Có thể còn entity cũ trong persistence context; cân nhắc clear/refresh |

Một query method có tác dụng xóa là thao tác ghi, dù tên của nó có hình dạng giống một search method. Không nên để một thao tác phá hủy dữ liệu trở thành API đọc chỉ vì nó được đặt trong nhóm search. Nếu không muốn công bố method đó, dùng @RestResource(exported = false) ở method tương ứng hoặc không đưa nó vào repository được công bố.

## 4. Spring Data REST công bố thao tác xóa như thế nào?

Spring Data REST ánh xạ tài nguyên repository thành các thao tác HTTP theo resource model. Với một item resource, thao tác xóa chuẩn thường có dạng:

~~~~http
DELETE /people/{id}
~~~~

Request này yêu cầu xóa tài nguyên có ID tương ứng. Handler của Spring Data REST dùng repository metadata và repository invoker để thực hiện thao tác xóa. Client làm việc với URL tài nguyên; client không gọi trực tiếp một overload Java cụ thể.

Điều quan trọng là không suy luận rằng mỗi overload trong CrudRepository tự động trở thành một endpoint riêng. Việc một method Java tồn tại và việc method đó được công bố qua REST là hai vấn đề khác nhau. Các route thực tế còn phụ thuộc vào loại repository, method metadata, annotation, phiên bản Spring Data REST và cấu hình ứng dụng.

Đối với method hoặc repository cần ẩn:

- **@RepositoryRestResource(exported = false)** trên repository: không công bố repository đó như REST resource.
- **@RestResource(exported = false)** trên method: ẩn method khỏi REST exposure.
- Để ẩn method kế thừa từ CrudRepository, có thể redeclare đúng chữ ký trong repository con và gắn @RestResource(exported = false), rồi kiểm tra mapping thực tế của phiên bản đang dùng.

Ví dụ ẩn các thao tác ghi kế thừa:

~~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends CrudRepository<Person, Long> {

    @Override
    @RestResource(exported = false)
    <S extends Person> S save(S entity);

    @Override
    @RestResource(exported = false)
    <S extends Person> Iterable<S> saveAll(Iterable<S> entities);

    @Override
    @RestResource(exported = false)
    void deleteById(Long id);

    @Override
    @RestResource(exported = false)
    void delete(Person entity);

    @Override
    @RestResource(exported = false)
    void deleteAllById(Iterable<? extends Long> ids);

    @Override
    @RestResource(exported = false)
    void deleteAll(Iterable<? extends Person> entities);

    @Override
    @RestResource(exported = false)
    void deleteAll();
}
~~~~

Đây là ví dụ minh họa cho cách redeclare method và tắt export. Cần đối chiếu chữ ký generic với phiên bản Spring Data Commons trong dự án. Nếu repository còn kế thừa các API ghi đặc thù của JpaRepository, chẳng hạn saveAndFlush, deleteAllInBatch hoặc deleteAllByIdInBatch, cần rà soát chúng riêng; ẩn các method của CrudRepository không tự động ẩn mọi method ghi do interface khác cung cấp.

## 5. Thiết kế repository chỉ đọc từ đầu

Cách rõ ràng nhất để giới hạn hợp đồng là kế thừa marker interface **Repository<T, ID>** và chỉ khai báo các phương thức đọc cần thiết. Không kế thừa CrudRepository, JpaRepository hoặc một interface khác mang theo các phương thức ghi nếu ứng dụng không cần chúng.

Ví dụ:

~~~~java
@RepositoryRestResource(path = "articles")
public interface ArticleReadRepository extends Repository<Article, Long> {

    Optional<Article> findById(Long id);

    Page<Article> findAll(Pageable pageable);

    List<Article> findAll(Sort sort);

    List<Article> findByStatus(ArticleStatus status);

    Optional<Article> findBySlug(String slug);

    boolean existsBySlug(String slug);

    long countByStatus(ArticleStatus status);
}
~~~~

Trong ví dụ này:

- Repository vẫn là Spring Data repository vì kế thừa Repository<T, ID>.
- Chỉ các phương thức đọc được khai báo.
- Spring Data có thể tạo query từ tên method hoặc xử lý các method đọc đã khai báo.
- Spring Data REST có thể công bố các resource và search method đọc theo cấu hình.
- Không có save, delete hoặc deleteAll trong hợp đồng mà client có thể vô tình sử dụng qua repository này.

Có thể khai báo thêm Page, Slice, Sort, projection hoặc query method theo nhu cầu. Chỉ đưa vào interface những thao tác đọc mà API thực sự cần hỗ trợ.

### Khi phải kế thừa CrudRepository

Đôi khi service nội bộ cần CRUD đầy đủ nhưng API công khai chỉ được đọc. Khi đó có hai lựa chọn:

1. Tách thành hai interface: một repository nội bộ có quyền ghi và một repository đọc dành cho Spring Data REST. Cần đặt tên và cấu hình scan cẩn thận để tránh tạo hai repository bean cùng quản lý một domain type ngoài ý muốn.
2. Giữ một repository kế thừa CrudRepository nhưng redeclare mọi method ghi với @RestResource(exported = false). Cách này giữ một bean repository, nhưng phải duy trì danh sách method ghi khi nâng cấp Spring Data hoặc bổ sung interface.

Nếu chỉ có nhu cầu đọc ở cả tầng service lẫn REST, kế thừa Repository<T, ID> thường là hợp đồng đơn giản hơn.

## 6. Chọn cách công bố phù hợp

| Nhu cầu | Cách thiết kế |
|---|---|
| Chỉ đọc ở mọi nơi | Kế thừa Repository<T, ID>, chỉ khai báo finder/read method |
| Repository nội bộ cần ghi, REST chỉ đọc | Tách API đọc hoặc ẩn toàn bộ method ghi bằng @RestResource(exported = false) |
| Không cho REST truy cập repository | @RepositoryRestResource(exported = false) |
| Cho phép đọc và xóa từng item | Công bố repository có chọn lọc; kiểm tra item DELETE và phân quyền |
| Cho phép xóa theo điều kiện | Thiết kế endpoint nghiệp vụ riêng, có HTTP method, quyền, validation và transaction rõ ràng |
| Cho phép xóa hàng loạt | Chỉ dành cho vai trò quản trị; giới hạn phạm vi, kích thước batch, audit và xác nhận nghiệp vụ |

Không dùng **@RepositoryRestResource(exported = false)** khi mục tiêu là “read-only”: annotation đó tắt cả resource, gồm cả GET. Muốn giữ đọc và tắt ghi, phải giới hạn method ghi hoặc xây dựng interface chỉ đọc.

## 7. Read-only ở REST không đồng nghĩa database không thể bị ghi

Ẩn các method ghi khỏi Spring Data REST chỉ giới hạn bề mặt endpoint được công bố. Nó không ngăn:

- Một controller tùy chỉnh gọi repository để ghi.
- Service nội bộ hoặc scheduled job thay đổi dữ liệu.
- Một ứng dụng khác truy cập database bằng tài khoản có quyền ghi.
- Một custom query method có side effect được gọi qua đường khác.

Vì vậy, với dữ liệu cần bảo vệ nghiêm ngặt, nên kết hợp nhiều lớp:

- **Repository contract:** chỉ khai báo method đọc trong repository được công bố.
- **REST exposure:** ẩn method ghi và không công bố endpoint phá hủy ngoài chủ đích.
- **Authorization:** giới hạn endpoint theo role/authority; không dựa vào việc URL khó đoán.
- **Database permissions:** dùng database account chỉ có SELECT cho ứng dụng hoặc thành phần thực sự chỉ đọc khi kiến trúc cho phép.
- **Transaction:** dùng @Transactional(readOnly = true) cho luồng đọc để thể hiện ý định và hỗ trợ tối ưu của persistence provider. Đây là hint/transaction setting, không thay thế quyền truy cập database và không phải cơ chế bảo mật tuyệt đối.
- **Audit và logging:** ghi nhận các thao tác xóa ở những luồng có quyền ghi.

Nếu một ứng dụng cần vừa đọc vừa ghi ở các chức năng khác nhau, có thể dùng các database role hoặc service boundary riêng để giới hạn quyền theo đúng nhu cầu.

## 8. Kiểm thử repository chỉ đọc

Nên kiểm tra cả hợp đồng Java lẫn HTTP API:

1. **Kiểm tra interface:** repository được công bố chỉ kế thừa Repository và không khai báo method ghi.
2. **Kiểm tra GET:** collection, item, paging/sorting và search resource đọc hoạt động đúng.
3. **Kiểm tra HTTP write:** POST, PUT, PATCH và DELETE không được công bố hoặc bị từ chối theo cấu hình dự kiến. Status cụ thể có thể phụ thuộc mapping và security filter; kiểm tra hành vi thực tế thay vì mặc định luôn là 404 hoặc 405.
4. **Kiểm tra method ẩn:** với cách redeclare và @RestResource(exported = false), xác nhận các route tương ứng không xuất hiện trong API profile/mappings.
5. **Kiểm tra quyền:** user chỉ có role đọc không thể gọi endpoint ghi của controller khác.
6. **Kiểm tra database:** nếu yêu cầu bảo đảm ở mức dữ liệu, thử thao tác ghi bằng database account chỉ đọc và xác nhận database từ chối.

Có thể dùng MockMvc hoặc test tích hợp với Spring Boot để kiểm tra request thực tế. Trong môi trường phát triển, HAL links/profile và Actuator mappings (nếu được bật) cũng giúp xác nhận những affordance và handler nào đang được công bố.

## 9. Kết luận

Các overload delete biểu đạt những phạm vi xóa khác nhau: theo ID, theo entity, theo tập ID, theo tập entity hoặc toàn bộ repository. Derived delete query và bulk delete còn khác nhau về cách thực thi và vòng đời entity. Không nên coi chúng là các lựa chọn tương đương về hiệu năng hoặc tác động.

Nếu mục tiêu là công bố một API chỉ đọc, hãy ưu tiên repository kế thừa Repository<T, ID> và chỉ khai báo method đọc. Nếu bắt buộc kế thừa CRUD, cần ẩn toàn bộ method ghi, kể cả các method mở rộng của store cụ thể, rồi kiểm thử mapping. Cuối cùng, kết hợp authorization và quyền database nếu cần bảo đảm không có đường ghi nào vượt qua REST layer.

## Tài liệu tham khảo

- [Spring Data Commons — CrudRepository API](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/repository/CrudRepository.html)
- [Spring Data Commons — Repository marker interface](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/repository/Repository.html)
- [Spring Data REST — Hiding repository resources and methods](https://docs.spring.io/spring-data/rest/reference/customizing/visibility.html)
- [Spring Data JPA — Derived delete queries](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Spring Data JPA — JpaRepository API](https://docs.spring.io/spring-data/jpa/reference/api/java/org/springframework/data/jpa/repository/JpaRepository.html)
