# @RepositoryRestResource và các thuộc tính điều khiển công bố tài nguyên

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích Spring Data REST công bố một Spring Data repository thành REST resource như thế nào.
- Tùy chỉnh URL của collection và tên quan hệ hypermedia bằng **path**, **collectionResourceRel** và **itemResourceRel**.
- Bật hoặc ẩn repository và từng query method bằng **exported**.
- Cấu hình excerpt projection và mô tả tài nguyên.
- Phân biệt trách nhiệm của **@RepositoryRestResource** với **@RestResource**, đồng thời nhận biết giới hạn bảo mật của hai annotation này.

## 1. Spring Data REST công bố repository

Spring Data REST có thể tự tạo HTTP endpoint từ các Spring Data repository đã được ứng dụng phát hiện. Với một repository quản lý **Member**, framework có thể cung cấp endpoint collection, endpoint cho từng item và endpoint tìm kiếm cho các query method phù hợp.

Ví dụ:

~~~java
public interface MemberRepository extends JpaRepository<Member, Long> {
}
~~~

Repository này có thể được công bố thành REST resource mà không cần viết controller CRUD riêng. Nếu ứng dụng cấu hình base path là **/api**, các endpoint thường có dạng:

| HTTP | Endpoint | Ý nghĩa |
|---|---|---|
| GET | /api/members | Đọc collection, có thể hỗ trợ phân trang và sắp xếp |
| POST | /api/members | Tạo một member |
| GET | /api/members/{id} | Đọc một member |
| PUT / PATCH | /api/members/{id} | Cập nhật member |
| DELETE | /api/members/{id} | Xóa member |
| GET | /api/members/search/... | Gọi query method được công bố |

Các endpoint cụ thể phụ thuộc vào loại repository, những method repository có sẵn và cấu hình của ứng dụng. Spring Data REST thường trả representation theo HAL, trong đó trường **_links** mô tả các tài nguyên và hành động có thể đi tiếp.

**@RepositoryRestResource** dùng để điều khiển cách một repository được công bố. Annotation này đặt trên interface repository. Bạn không cần annotation này chỉ để Spring Data REST phát hiện repository; nó hữu ích khi cần đặt tên, đổi đường dẫn, ẩn hoặc bổ sung metadata cho resource.

## 2. @RepositoryRestResource và các thuộc tính chính

Import annotation:

~~~java
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
~~~

Ví dụ:

~~~java
@RepositoryRestResource(
    path = "members",
    collectionResourceRel = "members",
    itemResourceRel = "member"
)
public interface MemberRepository extends JpaRepository<Member, Long> {
}
~~~

Với base path **/api**, collection được truy cập tại **/api/members**. Ba thuộc tính trên có vai trò khác nhau:

| Thuộc tính | Điều khiển | Ví dụ |
|---|---|---|
| **path** | Đoạn đường dẫn URL của repository resource | **members** |
| **collectionResourceRel** | Tên quan hệ hypermedia trỏ tới collection | **members** |
| **itemResourceRel** | Tên quan hệ hypermedia dùng cho item | **member** |

### path: tên đường dẫn HTTP

**path** quyết định đoạn URL mà client dùng để truy cập resource. Đổi **path** từ tên mặc định sang **members** làm URL collection trở thành **/api/members**.

Đây là cấu hình đường dẫn của repository. Nó không thay đổi tên Java của interface, tên bảng trong database hoặc tên thuộc tính của entity. Nó cũng không thay thế base path toàn ứng dụng.

### collectionResourceRel và itemResourceRel: tên quan hệ HAL

Spring Data REST cung cấp liên kết hypermedia để client khám phá tài nguyên. Các thuộc tính **collectionResourceRel** và **itemResourceRel** điều khiển tên quan hệ của các liên kết đó.

Hãy phân biệt:

- **path** trả lời câu hỏi: client gọi URL nào?
- **collectionResourceRel** và **itemResourceRel** trả lời câu hỏi: client nhìn thấy liên kết dưới tên quan hệ nào trong representation?

Tên quan hệ là một phần của hợp đồng hypermedia. Nếu client dựa vào các relation name này, hãy chọn tên ổn định và nhất quán. Đổi relation name có thể ảnh hưởng client dù URL không đổi.

### exported: có công bố repository hay không

Mặc định repository được công bố. Đặt **exported = false** để giữ repository khỏi REST API:

~~~java
@RepositoryRestResource(exported = false)
public interface InternalAuditRepository
        extends JpaRepository<InternalAudit, Long> {
}
~~~

Repository vẫn là một Spring Data repository và vẫn có thể được inject, gọi từ service hoặc dùng trong code Java. Cấu hình này chỉ điều khiển việc Spring Data REST có xuất bản resource hay không.

Đây là lựa chọn phù hợp cho repository nội bộ, dữ liệu vận hành hoặc repository chỉ dành cho luồng xử lý phía server.

### excerptProjection: representation tóm tắt cho collection

Collection có thể chứa nhiều entity với nhiều thuộc tính. Nếu client chỉ cần một số trường cơ bản, bạn có thể đặt excerpt projection:

~~~java
@RepositoryRestResource(
    path = "members",
    excerptProjection = MemberSummary.class
)
public interface MemberRepository extends JpaRepository<Member, Long> {
}
~~~

Projection:

~~~java
import org.springframework.data.rest.core.config.Projection;

@Projection(name = "memberSummary", types = Member.class)
public interface MemberSummary {
    String getName();
    String getEmailAddress();
}
~~~

Projection mô tả các thuộc tính xuất hiện trong representation tóm tắt. Với excerpt projection, Spring Data REST dùng projection này cho các item được nhúng trong collection resource. Client vẫn có thể truy cập item resource riêng theo quy tắc projection của API.

Excerpt projection giúp giới hạn payload và tạo representation thuận tiện cho màn hình danh sách. Nó không thay thế DTO/service mapping cho nghiệp vụ phức tạp, và cũng không phải cơ chế phân quyền che dữ liệu nhạy cảm.

### Mô tả collection và item

Bạn có thể cung cấp mô tả cho collection resource và item resource bằng **Description**:

~~~java
import org.springframework.data.rest.core.annotation.Description;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(
    path = "members",
    collectionResourceDescription = @Description("Danh sách thành viên"),
    itemResourceDescription = @Description("Thông tin của một thành viên")
)
public interface MemberRepository extends JpaRepository<Member, Long> {
}
~~~

Các mô tả này là metadata của Spring Data REST, hỗ trợ diễn giải resource trong metadata hypermedia/ALPS. Chúng không tự sinh tài liệu OpenAPI hoặc thay thế tài liệu API mà dự án đang sử dụng.

## 3. Tùy chỉnh query method bằng @RestResource

**@RepositoryRestResource** điều khiển repository resource ở cấp interface. **@RestResource** điều khiển cách một method được công bố.

Import:

~~~java
import org.springframework.data.rest.core.annotation.RestResource;
import org.springframework.data.repository.query.Param;
~~~

Ví dụ query method:

~~~java
@RepositoryRestResource(path = "members")
public interface MemberRepository extends JpaRepository<Member, Long> {

    @RestResource(path = "by-email", rel = "by-email")
    List<Member> findByEmailAddress(@Param("email") String email);
}
~~~

Spring Data REST công bố query method dưới search resource. Với base path **/api**, client có thể gọi:

~~~http
GET /api/members/search/by-email?email=lan%40example.com
~~~

Trong cấu hình này:

- **path = "by-email"** đặt đoạn URL của query method.
- **rel = "by-email"** đặt relation name của liên kết tìm kiếm.
- **@Param("email")** xác định tên query parameter mà client gửi.

**@Param** đặc biệt hữu ích để tên parameter HTTP không phụ thuộc vào việc compiler có lưu tên tham số Java hay không.

Bạn cũng có thể ẩn một query method khỏi REST API:

~~~java
@RepositoryRestResource(path = "members")
public interface MemberRepository extends JpaRepository<Member, Long> {

    @RestResource(path = "by-email", rel = "by-email")
    List<Member> findByEmailAddress(@Param("email") String email);

    @RestResource(exported = false)
    List<Member> findByInternalFlagTrue();
}
~~~

**findByInternalFlagTrue()** vẫn có thể được code phía server gọi thông qua repository. Spring Data REST không công bố method này thành search endpoint.

Có thể dùng **path**, **rel**, **exported** và metadata mô tả trên **@RestResource** để điều khiển từng method. Hãy đảm bảo path của các query method trong cùng resource không xung đột.

## 4. Ví dụ kết hợp

Giả sử ứng dụng có entity **Member** và cần công bố danh sách thành viên cho client. Client cần:

1. Truy cập collection qua URL **/api/members**.
2. Nhận tên relation dễ hiểu trong HAL.
3. Nhìn thấy representation tóm tắt trong danh sách.
4. Tìm kiếm theo email.
5. Không truy cập được query method chỉ dành cho nội bộ.

Repository có thể được khai báo như sau:

~~~java
import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.Description;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;

@RepositoryRestResource(
    path = "members",
    collectionResourceRel = "members",
    itemResourceRel = "member",
    excerptProjection = MemberSummary.class,
    collectionResourceDescription =
        @Description("Danh sách thành viên"),
    itemResourceDescription =
        @Description("Thông tin của một thành viên")
)
public interface MemberRepository extends JpaRepository<Member, Long> {

    @RestResource(path = "by-email", rel = "by-email")
    List<Member> findByEmailAddress(@Param("email") String email);

    @RestResource(exported = false)
    List<Member> findByInternalFlagTrue();
}
~~~

Projection:

~~~java
import org.springframework.data.rest.core.config.Projection;

@Projection(name = "memberSummary", types = Member.class)
public interface MemberSummary {
    String getName();
    String getEmailAddress();
}
~~~

Các import/package của **Member**, **MemberSummary** và repository cần nằm trong phạm vi component/repository/projection scanning mà ứng dụng cấu hình. Ví dụ dùng **JpaRepository** để minh họa; **@RepositoryRestResource** áp dụng cho repository Spring Data được Spring Data REST quản lý, không chỉ riêng JPA.

## 5. Base path là cấu hình cấp ứng dụng

**path** trên **@RepositoryRestResource** chỉ đặt đường dẫn cho một repository. Nếu muốn tất cả repository REST nằm dưới **/api**, hãy cấu hình base path ở cấp Spring Data REST:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Configuration
public class RestConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {
        config.setBasePath("/api");
    }
}
~~~

Sau cấu hình này, repository có **path = "members"** được truy cập dưới **/api/members**.

Không nên nhầm base path với **path**:

- Base path áp dụng cho toàn bộ Spring Data REST API.
- **path** đặt tên URL cho một repository resource.
- **collectionResourceRel** và **itemResourceRel** đặt tên quan hệ hypermedia.

Nếu dự án đã có **RepositoryRestConfigurer**, hãy bổ sung cấu hình vào cơ chế hiện có thay vì tạo nhiều nơi cùng thay đổi base path.

## 6. Kiểm tra endpoint

Sau khi ứng dụng khởi động, có thể kiểm tra API root và collection:

~~~bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/api
~~~

~~~bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/api/members
~~~

Kiểm tra query method:

~~~bash
curl -i -G -H "Accept: application/hal+json" --data-urlencode "email=lan@example.com" http://localhost:8080/api/members/search/by-email
~~~

Hãy quan sát status code, response body và **_links**. API root giúp xác định resource được công bố; collection cho biết representation và relation name thực tế; liên kết search cho biết query method có được xuất bản hay không.

Khi kiểm tra thao tác ghi, hãy dùng dữ liệu thử nghiệm và xác nhận request body phù hợp với entity/association mà repository quản lý.

## 7. Ranh giới và lỗi thường gặp

### Ẩn resource không đồng nghĩa với bảo mật truy cập

**exported = false** điều khiển việc Spring Data REST công bố endpoint. Nó không phải authorization rule và không thay thế Spring Security.

Với resource được công bố, hãy cấu hình xác thực, phân quyền theo HTTP method/resource và kiểm tra quyền truy cập dữ liệu ở tầng phù hợp. Projection cũng không phải cơ chế bảo vệ dữ liệu nhạy cảm: nếu một trường không được phép tiết lộ, hãy kiểm soát representation và quyền truy cập bằng thiết kế bảo mật của ứng dụng.

### Đổi path không đổi tên relation

Nếu URL đổi nhưng relation name vẫn giữ nguyên, client HAL có thể tiếp tục khám phá liên kết bằng relation name cũ. Ngược lại, đổi relation name không nhất thiết đổi URL. Khi thiết kế API cho client hypermedia, cần quản lý cả hai phần như một hợp đồng.

### Repository không xuất hiện

Kiểm tra dependency Spring Data REST, phạm vi scan repository, base path và giá trị **exported**. Đảm bảo repository là interface Spring Data hợp lệ và được cấu hình cho module persistence đang dùng.

### Search endpoint không xuất hiện

Kiểm tra method có phải query method mà Spring Data hỗ trợ hay không, method có bị **@RestResource(exported = false)** ẩn không, và path có bị trùng không. Kiểm tra tên query parameter với **@Param**.

### Projection không được áp dụng

Kiểm tra projection tham chiếu đúng domain type, các getter tồn tại và projection được Spring Data REST phát hiện theo cấu hình/package của ứng dụng. Xác nhận bạn đang quan sát collection representation, vì excerpt projection được dùng cho các item nhúng trong collection.

### Dùng Spring Data REST cho luồng nghiệp vụ phức tạp

Spring Data REST phù hợp khi API có thể phản ánh trực tiếp thao tác repository. Nếu một endpoint cần phối hợp nhiều repository, áp dụng quy tắc nghiệp vụ, gọi hệ thống ngoài, điều phối transaction hoặc trả DTO theo use case, hãy cân nhắc service và controller riêng. Annotation công bố repository không thay thế lớp điều phối nghiệp vụ.

## 8. Ghi nhớ

- Dùng **@RepositoryRestResource** để cấu hình resource ở cấp repository.
- Dùng **path** cho URL; dùng **collectionResourceRel** và **itemResourceRel** cho tên quan hệ hypermedia.
- Dùng **exported = false** để không công bố repository.
- Dùng **excerptProjection** để chọn representation tóm tắt cho collection.
- Dùng **collectionResourceDescription** và **itemResourceDescription** để bổ sung metadata mô tả.
- Dùng **@RestResource** để tùy chỉnh hoặc ẩn từng query method.
- Dùng **RepositoryRestConfigurer** nếu cần base path chung.
- Dùng Spring Security và thiết kế authorization riêng để bảo vệ dữ liệu và thao tác.
