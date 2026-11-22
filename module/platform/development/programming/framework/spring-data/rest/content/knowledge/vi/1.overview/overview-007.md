# Các trường hợp phù hợp để sử dụng Spring Data REST

Spring Data REST phù hợp khi ứng dụng đã có các Spring Data repository và cần công bố chúng thành REST API với ít mã kết nối. Thay vì tự viết một controller cho từng thao tác đọc, tạo, cập nhật và xóa, Spring Data REST tạo các resource HTTP từ repository, hỗ trợ phân trang, sắp xếp, các phương thức tìm kiếm và biểu diễn có liên kết theo HATEOAS.

Công cụ này phát huy hiệu quả nhất khi **mô hình tài nguyên gần với aggregate/domain model**, quy tắc nghiệp vụ có thể thực thi trong entity hoặc service hiện có, và API chủ yếu phục vụ CRUD hoặc tra cứu. Nó không tự biến một quy trình nghiệp vụ phức tạp thành API phù hợp; thiết kế repository và ranh giới dữ liệu vẫn quyết định chất lượng của API.

## 1. CRUD cho dữ liệu có vòng đời đơn giản

Đây là trường hợp phù hợp nhất. Một tài nguyên có thể được tạo, xem, sửa và xóa thông qua các thao tác repository quen thuộc. Ví dụ:

- Danh mục sản phẩm, loại hàng, đơn vị tính hoặc dữ liệu tham chiếu.
- Hồ sơ nhân viên, phòng ban, nhóm hoặc địa điểm.
- Danh sách thiết bị, tài sản, tài liệu và trạng thái quản lý cơ bản.
- Bản ghi nghiệp vụ có quy trình tạo/sửa/xóa đơn giản, không cần nhiều bước phê duyệt.

Khi repository được export, Spring Data REST có thể cung cấp các thao tác HTTP tương ứng:

| Nhu cầu | HTTP thường dùng | Resource minh họa |
|---|---|---|
| Xem danh sách | `GET` | `/employees` |
| Xem một bản ghi | `GET` | `/employees/42` |
| Tạo bản ghi | `POST` | `/employees` |
| Thay thế hoặc cập nhật | `PUT` hoặc `PATCH` | `/employees/42` |
| Xóa bản ghi | `DELETE` | `/employees/42` |

Các endpoint thực tế phụ thuộc vào repository được export, các phương thức được cho phép và cấu hình bảo mật. Có endpoint không đồng nghĩa mọi người dùng đều được phép gọi endpoint đó.

Spring Data REST đặc biệt hữu ích khi các thao tác trên tương ứng trực tiếp với hành vi hợp lệ của domain. Nếu một thao tác “đóng đơn hàng” phải kiểm tra tồn kho, ghi nhận thanh toán, phát sự kiện và cập nhật nhiều aggregate trong cùng một quy trình, không nên mô hình hóa nó đơn thuần thành một lệnh cập nhật repository. Hãy đặt quy tắc đó trong service/use case và cung cấp endpoint tường minh.

## 2. Công cụ quản trị và ứng dụng nội bộ

Spring Data REST thường phù hợp với các công cụ chỉ dành cho nhân viên hoặc hệ thống nội bộ, chẳng hạn:

- Màn hình quản trị danh mục và dữ liệu cấu hình.
- Công cụ hỗ trợ khách hàng cần tra cứu, xem và chỉnh sửa một số hồ sơ.
- Trang vận hành nội bộ để quản lý nhân viên, thiết bị hoặc tài nguyên.
- Công cụ nhập liệu và bảo trì dữ liệu cho một nhóm người dùng có quyền rõ ràng.

Lợi ích chính là giảm mã CRUD lặp lại. Frontend có thể gọi các resource có sẵn, đọc các liên kết HAL để điều hướng và dùng phân trang/sắp xếp mà không cần một controller riêng cho mỗi bảng dữ liệu.

Điều kiện quan trọng là **API nội bộ vẫn phải có bảo mật ở tầng ứng dụng**. Không nên xem mạng nội bộ, VPN hoặc việc ẩn URL là cơ chế phân quyền. Khi triển khai, cần:

1. Xác thực người dùng bằng cơ chế phù hợp, thường là Spring Security.
2. Phân quyền theo vai trò và theo thao tác; kiểm tra quyền truy cập từng bản ghi nếu dữ liệu có phạm vi sở hữu.
3. Chỉ export repository và phương thức thực sự cần thiết.
4. Kiểm tra dữ liệu đầu vào, ràng buộc nghiệp vụ và các trường nhạy cảm trước khi cho phép ghi.
5. Kiểm thử cả trường hợp bị từ chối, không chỉ trường hợp gọi API thành công.

Có thể ẩn hoàn toàn một repository bằng `@RepositoryRestResource(exported = false)`. Với một phương thức repository không nên công bố, có thể dùng `@RestResource(exported = false)` trên phương thức được khai báo lại trong interface repository. Đây là cách thu hẹp bề mặt API; phân quyền vẫn cần được cấu hình riêng.

## 3. Tra cứu dữ liệu và các bộ lọc đơn giản

Spring Data REST phù hợp khi ứng dụng cần cung cấp các truy vấn tra cứu quen thuộc:

- Tìm hồ sơ theo tên, mã, trạng thái hoặc phòng ban.
- Lọc danh sách theo một vài thuộc tính.
- Tra cứu danh mục dùng chung cho nhiều màn hình.
- Hiển thị danh sách lớn theo từng trang và cho phép sắp xếp.

Các phương thức truy vấn của repository có thể được công bố dưới resource `search`. Ví dụ, một phương thức `findByDepartmentIgnoreCase` có thể tạo endpoint tìm nhân viên theo phòng ban. Phân trang và sắp xếp giúp client lấy dữ liệu theo từng phần thay vì tải toàn bộ danh sách.

Ví dụ interface dưới đây là **đoạn mã minh họa trong một ứng dụng Spring Boot**, không phải chương trình độc lập. `Employee` cần là entity phù hợp với persistence layer và có thuộc tính `department`.

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;

@RepositoryRestResource(path = "employees")
public interface EmployeeRepository extends JpaRepository<Employee, Long> {

    @RestResource(path = "by-department", rel = "by-department")
    Page<Employee> findByDepartmentIgnoreCase(
        @Param("name") String department,
        Pageable pageable
    );
}
```

Nếu cấu hình base path là:

```properties
spring.data.rest.base-path=/api
```

client có thể gọi:

```http
GET /api/employees
GET /api/employees/42
GET /api/employees/search/by-department?name=Sales&page=0&size=20&sort=fullName,asc
```

Trong ví dụ cuối, `name` là tham số truy vấn được khai báo bằng `@Param`; `page`, `size` và `sort` điều khiển phân trang/sắp xếp. Tên thuộc tính dùng để sắp xếp phải phù hợp với model và cấu hình repository. Ứng dụng cần dependency Spring Data REST cùng persistence module tương ứng, ví dụ `spring-boot-starter-data-rest` và `spring-boot-starter-data-jpa`.

Kiểu tra cứu này thích hợp cho bộ lọc đơn giản, có thể diễn đạt rõ bằng repository query method. Với tìm kiếm toàn văn, xếp hạng kết quả, truy vấn tổng hợp nhiều nguồn, bộ lọc động phức tạp hoặc yêu cầu tối ưu truy vấn đặc thù, nên xây dựng query/service và endpoint riêng để kiểm soát hành vi.

## 4. Khi nào nên chọn và khi nào nên dùng controller riêng?

| Tình huống | Mức độ phù hợp | Lý do |
|---|---|---|
| CRUD chuẩn trên một aggregate | Cao | Repository và thao tác HTTP tương ứng trực tiếp |
| Quản trị dữ liệu nội bộ | Cao | Giảm controller lặp lại; có thể dùng HAL và phân trang |
| Tra cứu theo vài thuộc tính, có phân trang | Cao | Query method và cơ chế search đáp ứng tốt |
| API chỉ đọc cho danh mục đơn giản | Khá cao | Có thể ẩn các thao tác ghi và chỉ export truy vấn cần thiết |
| Quy trình nhiều bước hoặc tác động nhiều aggregate | Thấp | Cần orchestration, giao dịch và phản hồi nghiệp vụ tường minh |
| API công khai cần DTO/contract ổn định, versioning chặt | Thường thấp | Mô hình repository/domain có thể làm lộ cấu trúc nội bộ |
| Phân quyền theo từng bản ghi hoặc quy tắc truy cập phức tạp | Cần cân nhắc kỹ | Phải cấu hình và kiểm thử authorization chi tiết |
| Tìm kiếm nâng cao hoặc yêu cầu hiệu năng đặc thù | Thường thấp | Cần kiểm soát query, projection, cache và payload rõ hơn |

Hãy cân nhắc controller/service riêng khi endpoint đại diện cho **một hành động nghiệp vụ** thay vì một thao tác trên repository. Ví dụ, `POST /orders/{id}/approve` thể hiện ý nghĩa nghiệp vụ rõ hơn việc cho phép client sửa trực tiếp một trường `status`. Controller riêng cũng phù hợp khi API cần DTO riêng, quy tắc versioning, định dạng lỗi hoặc payload không nên phụ thuộc vào entity.

Spring Data REST có các cơ chế mở rộng như projection, excerpt, event handler và cấu hình resource. Những cơ chế đó hữu ích cho tùy biến vừa phải. Nếu phải tùy biến gần như mọi endpoint, chuyển đổi sâu cấu trúc dữ liệu hoặc điều phối nhiều bước nghiệp vụ, controller/service tường minh thường dễ đọc, kiểm thử và duy trì hơn.

## 5. Các giới hạn cần kiểm tra trước khi đưa vào sử dụng

- **Bề mặt API:** Không export mọi repository theo thói quen. Lập danh sách resource được phép công bố; ẩn repository/phương thức nội bộ.
- **Mô hình dữ liệu:** Chỉ công bố aggregate root phù hợp. Tránh vô tình để client thao tác trực tiếp lên các bảng/entity nội bộ.
- **Bảo mật:** Cấu hình xác thực, authorization ở cấp endpoint và bản ghi, cũng như quyền đọc/ghi từng trường khi cần. Kiểm thử truy cập trái phép.
- **Validation và nghiệp vụ:** Đảm bảo các invariant được thực thi ở server. Không phụ thuộc vào việc frontend đã kiểm tra dữ liệu.
- **Hiệu năng:** Kiểm tra truy vấn sinh ra, phân trang, sắp xếp, lazy relationship, N+1 và kích thước payload. Không để endpoint trả về một tập dữ liệu lớn không giới hạn.
- **Biểu diễn dữ liệu:** Client phải chấp nhận cách biểu diễn và liên kết HAL mặc định, hoặc nhóm phát triển phải chủ động cấu hình projection/representation phù hợp.
- **Khả năng tương thích:** Nếu nhiều client bên ngoài phụ thuộc lâu dài vào API, cần có chiến lược giữ ổn định contract và kiểm thử tương thích khi domain/repository thay đổi.

## 6. Checklist quyết định

Trước khi chọn Spring Data REST cho một module, hãy trả lời “có” cho phần lớn câu hỏi sau:

1. Tài nguyên REST có tương ứng rõ ràng với một aggregate/repository không?
2. CRUD có phản ánh đúng các hành động hợp lệ của nghiệp vụ không?
3. Quy tắc nghiệp vụ có thể được bảo vệ ở server mà không cần một quy trình điều phối phức tạp không?
4. Các truy vấn cần thiết có thể diễn đạt bằng repository query method và phân trang/sắp xếp thông thường không?
5. Client có thể sử dụng HAL hoặc representation đã cấu hình mà không cần một DTO/contract riêng cho từng endpoint không?
6. Nhóm phát triển có thể giới hạn repository được export và cấu hình đầy đủ xác thực, phân quyền, validation không?

Nếu câu trả lời chủ yếu là “có”, Spring Data REST là lựa chọn tốt để tạo API CRUD và tra cứu nhanh, đặc biệt cho công cụ nội bộ. Nếu nhiều câu trả lời là “không”, hãy giữ repository làm tầng truy cập dữ liệu và xây dựng API qua controller/service để thể hiện rõ use case, quyền truy cập và contract.

## Kết luận

Spring Data REST phù hợp nhất với **CRUD có quy tắc đơn giản, công cụ quản trị nội bộ và tra cứu dữ liệu bằng truy vấn repository**. Giá trị của nó nằm ở việc giảm mã API lặp lại và cung cấp resource có liên kết, phân trang, sắp xếp. Chỉ nên công bố những repository thực sự thuộc contract của ứng dụng; với workflow phức tạp, API công khai cần contract riêng hoặc truy vấn nâng cao, endpoint tường minh qua controller/service thường là lựa chọn phù hợp hơn.

