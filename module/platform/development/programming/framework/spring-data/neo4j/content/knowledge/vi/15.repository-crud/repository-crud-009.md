# Giới hạn tập phương thức công khai theo ca sử dụng

Spring Data Neo4j (SDN) cung cấp repository abstraction để thao tác với entity graph. Các interface như `Neo4jRepository` đem lại nhiều phương thức CRUD sẵn dùng, nhưng một use case thường chỉ cần một phần nhỏ trong số đó. Màn hình tra cứu có thể chỉ cần đọc theo ID và tìm theo trạng thái; chức năng cập nhật hồ sơ cần đọc một entity và lưu; chức năng quản trị mới có thể cần xóa.

Nếu mọi thành phần ứng dụng đều phụ thuộc vào một repository công khai toàn bộ CRUD, chúng có thể gọi các thao tác vượt quá nhu cầu nghiệp vụ. Có thể giới hạn API repository bằng cách kế thừa marker `Repository<T, ID>` và chỉ khai báo những method cần thiết. Khi đó, hợp đồng Java thể hiện rõ các thao tác mà ca sử dụng được phép yêu cầu.

## 1. Repository marker và CRUD repository

`org.springframework.data.repository.Repository<T, ID>` là marker interface để Spring Data nhận diện repository. Nó không tự công khai toàn bộ các method CRUD. Ngược lại, `CrudRepository` cung cấp tập method CRUD cơ bản, còn `Neo4jRepository` là chuyên biệt cho Neo4j và mở rộng thêm các khả năng repository của Spring Data.

| Kiểu interface | Ý nghĩa | Hệ quả với API ứng dụng |
| --- | --- | --- |
| `Repository<T, ID>` | Marker để Spring Data tạo repository proxy | Chỉ có các method được khai báo trong interface kế thừa |
| `CrudRepository<T, ID>` | Cung cấp các thao tác CRUD tổng quát | Công khai các thao tác CRUD mà interface kế thừa |
| `Neo4jRepository<T, ID>` | Repository chuyên biệt cho Neo4j | Cung cấp nhiều thao tác CRUD và chức năng Spring Data Neo4j |

Khi muốn giới hạn method, hãy dùng `Repository<T, ID>` làm nền và khai báo lại đúng các chữ ký cần dùng. Spring Data có thể cung cấp implementation cho các method chuẩn được chọn, ví dụ `findById`, `save` hoặc `deleteById`, miễn là chữ ký và kiểu dữ liệu phù hợp với repository của store.

## 2. Thiết kế repository theo ca sử dụng

Ví dụ ứng dụng quản lý `Person`. Chức năng danh bạ chỉ cần đọc hồ sơ và tìm người theo trạng thái. Repository đọc chỉ công khai những thao tác đó:

~~~java
import java.util.List;
import java.util.Optional;

import org.springframework.data.repository.Repository;

public interface PersonDirectoryRepository extends Repository<Person, String> {
    Optional<Person> findById(String id);

    List<PersonSummary> findByStatus(String status);
}
~~~

Projection dùng cho danh sách chỉ chứa dữ liệu cần hiển thị:

~~~java
public interface PersonSummary {
    String getId();
    String getName();
}
~~~

`PersonDirectoryRepository` không kế thừa `CrudRepository` hoặc `Neo4jRepository`, vì vậy caller không nhìn thấy `save`, `deleteAll` hay `findAll` thông qua interface này. Phương thức `findByStatus` là derived query: Spring Data phân tích tên method và tạo truy vấn dựa trên property `status` của entity.

Nếu một ca sử dụng cần truy vấn graph riêng, có thể khai báo `@Query` trong cùng repository và trả về projection:

~~~java
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

@Query("""
    MATCH (team:Team {id: $teamId})-[:HAS_MEMBER]->(person:Person)
    RETURN person.id AS id, person.name AS name
    ORDER BY name
    """)
List<PersonSummary> findMembersOfTeam(@Param("teamId") String teamId);
~~~

Các alias `id` và `name` trong Cypher tương ứng với getter của projection. Query chỉ trả về các trường cần cho danh sách; nó không cần tải toàn bộ entity và các quan hệ khác của `Person`.

## 3. Tách quyền đọc và ghi

Khi các ca sử dụng đọc và ghi có yêu cầu khác nhau, có thể tạo interface riêng cho mỗi nhóm thao tác. Repository đọc tiếp tục dùng marker `Repository` và chỉ khai báo method truy vấn:

~~~java
public interface PersonReadRepository extends Repository<Person, String> {
    Optional<Person> findById(String id);
    List<PersonSummary> findByStatus(String status);
}
~~~

Repository ghi chỉ công khai thao tác lưu và xóa nếu nghiệp vụ thực sự cần:

~~~java
public interface PersonWriteRepository extends Repository<Person, String> {
    <S extends Person> S save(S entity);
    void deleteById(String id);
}
~~~

Hai interface trên đều là repository Spring Data cho cùng entity nhưng có hợp đồng khác nhau. Các service tra cứu chỉ cần phụ thuộc vào `PersonReadRepository`; service chỉnh sửa có thể nhận cả repository đọc và ghi. Nếu dự án không cần tách bean, một interface marker duy nhất với một tập method nhỏ cũng là lựa chọn hợp lệ. Hãy chọn cách tổ chức ít phức tạp nhất mà vẫn làm rõ quyền thao tác của từng ca sử dụng.

## 4. Đặt quy tắc nghiệp vụ ở service

Repository giới hạn các thao tác persistence có thể gọi. Service vẫn chịu trách nhiệm thực thi quy tắc nghiệp vụ, kiểm tra dữ liệu đầu vào và quản lý transaction.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PersonProfileService {
    private final PersonReadRepository readRepository;
    private final PersonWriteRepository writeRepository;

    public PersonProfileService(PersonReadRepository readRepository,
                                PersonWriteRepository writeRepository) {
        this.readRepository = readRepository;
        this.writeRepository = writeRepository;
    }

    @Transactional
    public void rename(String personId, String newName) {
        Person person = readRepository.findById(personId)
            .orElseThrow(() -> new IllegalArgumentException("Không tìm thấy Person"));

        person.rename(newName);
        writeRepository.save(person);
    }
}
~~~

Ví dụ giả định entity `Person` có phương thức nghiệp vụ `rename`. Service đọc entity, kiểm tra sự tồn tại, gọi hành vi domain rồi lưu thay đổi trong transaction. Repository không quyết định tên mới có hợp lệ hay người gọi có quyền đổi tên hay không; những quy tắc đó thuộc tầng nghiệp vụ và bảo mật.

Nếu chỉ cập nhật một trường bằng Cypher tùy chỉnh, hãy cân nhắc một method command có tên thể hiện mục đích, ví dụ `changeDisplayName`, thay vì mở rộng `save` cho mọi caller. Với query ghi tùy chỉnh, kiểm tra cách phiên bản SDN đang dùng xử lý kết quả và transaction; không giả định rằng mọi truy vấn `@Query` đều tự động áp dụng optimistic locking như thao tác lưu entity.

## 5. Chỉ công khai method CRUD thực sự cần thiết

Không phải repository nào cũng cần toàn bộ CRUD. Có thể dùng các nguyên tắc sau:

- **Tra cứu:** công khai `findById`, các derived query hoặc truy vấn `@Query` cụ thể. Dùng projection khi caller chỉ cần một phần dữ liệu.
- **Tạo hoặc cập nhật:** công khai `save` ở nơi thực sự cần lưu entity. Đặt kiểm tra nghiệp vụ trong service trước khi gọi.
- **Xóa:** chỉ công khai `deleteById` hoặc method xóa chuyên biệt nếu có use case xóa rõ ràng. Tránh cung cấp `deleteAll` cho service thông thường.
- **Kiểm tra tồn tại:** dùng `existsById` hoặc derived query `existsBy...` khi chỉ cần boolean, thay vì tải toàn bộ entity.
- **Đọc theo lô:** chỉ thêm `findAllById` khi ca sử dụng cần đọc nhiều định danh. Nếu danh sách có thể lớn, hãy cân nhắc phân trang hoặc truy vấn có giới hạn.

Một interface tối giản giúp compiler và IDE phát hiện sớm khi code cố gọi method không thuộc hợp đồng của ca sử dụng. Nó cũng giúp người đọc hiểu được repository đang hỗ trợ hành vi nào.

## 6. Tái sử dụng method chung mà vẫn giữ API nhỏ

Nếu nhiều repository cần một tập method cơ bản giống nhau, có thể tạo interface chung không được đăng ký thành repository độc lập bằng `@NoRepositoryBean`:

~~~java
import java.util.Optional;

import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.repository.Repository;

@NoRepositoryBean
public interface ReadByIdRepository<T, ID> extends Repository<T, ID> {
    Optional<T> findById(ID id);
}
~~~

Repository cụ thể kế thừa interface này:

~~~java
public interface PersonDirectoryRepository
        extends ReadByIdRepository<Person, String> {
    List<PersonSummary> findByStatus(String status);
}
~~~

`@NoRepositoryBean` báo Spring Data không tạo bean repository cho interface generic trung gian. Các interface cụ thể mới được khởi tạo. Chỉ nên đưa vào interface chung những method thực sự phù hợp với tất cả repository kế thừa; đừng biến nó thành một CRUD base interface lớn rồi làm mất mục tiêu giới hạn API.

## 7. Repository API không thay thế phân quyền

Việc không khai báo `deleteById` trên một interface đọc giúp code dùng interface đó không gọi được method xóa qua hợp đồng này. Tuy nhiên, đây là giới hạn ở thiết kế code, không phải cơ chế bảo mật database. Một thành phần khác vẫn có thể inject repository ghi hoặc dùng `Neo4jClient` nếu ứng dụng cho phép.

Quyền truy cập cần được kiểm tra ở tầng service hoặc security phù hợp với ứng dụng. Tài khoản Neo4j cũng cần có quyền database tối thiểu theo vai trò triển khai. Không dùng việc ẩn method repository làm ranh giới xác thực người dùng.

Ngoài ra, nếu một interface kế thừa `Neo4jRepository<Person, String>`, tất cả method được kế thừa vẫn nằm trong API của interface đó. Khai báo thêm vài method chọn lọc không làm các method CRUD còn lại biến mất. Muốn giới hạn thực sự, hãy bắt đầu từ marker `Repository` hoặc một base interface nhỏ do ứng dụng định nghĩa.

## 8. Những lỗi thiết kế thường gặp

| Thiết kế | Vấn đề | Cách cải thiện |
| --- | --- | --- |
| Mọi service đều inject `Neo4jRepository` đầy đủ | Caller có thể dùng nhiều thao tác không liên quan đến use case | Tạo repository marker với method cần thiết |
| Repository đọc trả entity đầy đủ cho danh sách | Tải thêm property và relationship không cần thiết | Dùng projection hoặc DTO |
| Đặt quy tắc nghiệp vụ trong tên method repository | Repository trở thành nơi chứa logic domain và khó kiểm thử | Đưa quy tắc vào service/domain, repository chỉ thực hiện truy vấn |
| Dùng `deleteAll` cho thao tác xóa một nhóm nhỏ | Phạm vi xóa quá rộng và khó kiểm soát | Dùng method xóa theo ID hoặc điều kiện cụ thể |
| Tưởng interface đọc không có `save` là bảo mật tuyệt đối | Component khác vẫn có thể dùng API ghi hoặc kết nối khác | Kiểm tra quyền tại service/security và database |
| Kế thừa `Neo4jRepository` rồi chỉ gọi vài method | Toàn bộ method kế thừa vẫn được công khai | Dùng `Repository<T, ID>` nếu cần giới hạn hợp đồng |

## 9. Quy trình thiết kế repository cho một use case

Trước khi khai báo repository, hãy mô tả use case bằng động từ nghiệp vụ: xem hồ sơ, tìm người đang hoạt động, đổi tên, thêm thành viên, hoặc xóa một hồ sơ. Sau đó xác định dữ liệu đầu vào, kiểu dữ liệu cần trả về và thao tác ghi có cần thiết hay không.

Một quy trình ngắn:

1. Xác định ca sử dụng là đọc, ghi hay kết hợp cả hai.
2. Liệt kê method persistence tối thiểu cần dùng.
3. Chọn `Repository<T, ID>` làm marker nếu cần ẩn các CRUD method không dùng.
4. Chọn entity, projection hoặc DTO theo lượng dữ liệu cần trả về.
5. Đặt validation, authorization và transaction ở tầng service phù hợp.
6. Kiểm tra interface không vô tình kế thừa một CRUD API rộng hơn yêu cầu.

## 10. Bài tập tự kiểm tra

1. `Repository<T, ID>` khác `CrudRepository<T, ID>` ở vai trò nào?
2. Vì sao thêm method `findById` và `save` vào một interface kế thừa `Repository` có thể tạo API hẹp hơn `Neo4jRepository`?
3. Thiết kế repository chỉ cho phép tra cứu người theo trạng thái và xem hồ sơ theo ID. Những method nào cần công khai?
4. Một service cần đổi tên `Person`. Vì sao nên đặt validation trong service/domain thay vì repository?
5. `@NoRepositoryBean` có tác dụng gì với interface generic trung gian?
6. Vì sao giới hạn method repository không thay thế authorization?

Khi hoàn thành bài học, bạn cần có thể thiết kế repository theo nhu cầu cụ thể của từng ca sử dụng, chỉ công khai những thao tác persistence cần thiết và giữ rõ ranh giới giữa truy vấn dữ liệu, quy tắc nghiệp vụ, transaction và phân quyền trong ứng dụng Spring Data Neo4j.
