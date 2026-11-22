# Projection có thể làm lộ dữ liệu đã ẩn bằng `@JsonIgnore`

## Mục tiêu

`@JsonIgnore` có thể loại một thuộc tính khỏi representation JSON mặc định của entity. Tuy nhiên, Spring Data REST projections tạo ra một representation khác dựa trên các accessor được khai báo trong projection interface. Nếu projection chủ động khai báo getter cho thuộc tính nhạy cảm, thuộc tính đó có thể xuất hiện trở lại trong response projection dù entity đã đánh dấu `@JsonIgnore`.

Vì vậy, không dùng `@JsonIgnore` làm ranh giới bảo mật. Hãy xem từng projection, excerpt projection và nested projection là một phần của API contract cần được kiểm soát riêng.

## Representation mặc định và projection

Giả sử entity `User` chứa tên đăng nhập và giá trị bí mật nội bộ:

    @Entity
    public class User {
        @Id
        private Long id;

        private String username;

        @JsonIgnore
        private String apiKeyHash;

        // getters and setters
    }

Khi serialize entity theo representation mặc định, Jackson bỏ qua `apiKeyHash` theo cấu hình annotation. Response có thể chỉ chứa `id` và `username`.

Projection cho phép định nghĩa một góc nhìn khác của entity. Spring Data REST tạo projection proxy dựa trên các accessor mà interface công bố:

    @Projection(name = "userSummary", types = User.class)
    public interface UserSummary {
        Long getId();
        String getUsername();
    }

Client có thể yêu cầu projection đã đăng ký:

    GET /api/users?projection=userSummary
    GET /api/users/42?projection=userSummary

Response chỉ có các thuộc tính được projection `UserSummary` công bố.

## Vì sao `@JsonIgnore` có thể không bảo vệ projection?

`@JsonIgnore` tác động đến cách Jackson xử lý property trong representation mà entity cung cấp. Projection là một view riêng: interface projection khai báo những property cần đọc từ target object. Khi một projection khai báo accessor cho property bị bỏ qua trong representation mặc định, accessor đó có thể làm property xuất hiện trong JSON của projection.

Ví dụ sau tạo ra nguy cơ lộ dữ liệu:

    @Projection(name = "userWithKey", types = User.class)
    public interface UserWithKey {
        Long getId();
        String getUsername();
        String getApiKeyHash();
    }

Client có thể gọi:

    GET /api/users?projection=userWithKey

Projection `UserWithKey` công bố getter `getApiKeyHash()`. Vì vậy, không được giả định rằng annotation `@JsonIgnore` trên entity sẽ tự động loại property khỏi mọi projection. Nếu projection này được đăng ký và endpoint cho phép dùng nó, giá trị nhạy cảm có thể được serialize trong representation đó.

Điểm cần nhớ: `@JsonIgnore` bảo vệ representation mặc định theo quy tắc Jackson; nó không phải chính sách phân quyền và không thay thế việc thiết kế projection an toàn.

## Excerpt projection cũng cần được kiểm soát

Spring Data REST có thể áp dụng excerpt projection cho các phần tử trong collection. Có thể chỉ định excerpt projection tại repository:

    @RepositoryRestResource(excerptProjection = UserExcerpt.class)
    public interface UserRepository
            extends JpaRepository<User, Long> {
    }

Excerpt projection được dùng để biểu diễn phần tử trong collection hoặc các ngữ cảnh nhúng tương ứng. Nếu excerpt interface chứa getter cho `apiKeyHash`, dữ liệu đó có thể bị lộ ngay khi client đọc collection, dù client không yêu cầu projection có tên bằng query parameter.

Vì vậy, kiểm tra cả projection được yêu cầu tường minh bằng `?projection=...` và excerpt projection được cấu hình tự động. Không đưa trường bí mật vào excerpt chỉ vì response collection cần thêm thông tin.

## Nested projection và property dẫn xuất

Projection có thể tham chiếu projection khác để biểu diễn association lồng nhau. Một projection bên trong cũng có thể công bố property nhạy cảm của entity liên quan:

    @Projection(name = "userView", types = User.class)
    public interface UserView {
        String getUsername();
        DepartmentView getDepartment();
    }

    @Projection(name = "departmentView", types = Department.class)
    public interface DepartmentView {
        String getName();
        String getInternalBudgetCode();
    }

Khi kiểm tra exposure, cần lần theo toàn bộ projection graph, bao gồm association và nested projection. Chỉ kiểm tra các getter trực tiếp trên projection gốc có thể bỏ sót dữ liệu được đưa vào từ projection lồng nhau.

Projection dùng `@Value` hoặc SpEL cũng cần được xem xét. Một getter tính toán có thể trả về dữ liệu nhạy cảm dù tên property không tồn tại trực tiếp trên entity. Hãy kiểm tra giá trị mà biểu thức truy cập, không chỉ kiểm tra tên accessor.

## Cách thiết kế projection an toàn

1. **Mặc định theo allowlist:** chỉ khai báo getter cho các trường thực sự cần xuất ra client. Không tạo projection tổng quát chứa mọi property của entity.
2. **Tách dữ liệu công khai và nội bộ:** tạo projection riêng cho use case công khai; không đưa token, mật khẩu, hash, thông tin định danh nhạy cảm hoặc trường vận hành nội bộ vào đó.
3. **Giữ excerpt tối giản:** excerpt projection thường xuất hiện tự động trong collection, vì vậy chỉ chứa các trường an toàn để công khai rộng rãi.
4. **Kiểm soát nested projection:** rà soát các association projection và getter dẫn xuất có thể mở đường đến dữ liệu nhạy cảm.
5. **Giới hạn quyền truy cập:** dùng Spring Security và authorization ở endpoint/service khi dữ liệu chỉ dành cho một số người dùng. Không xem tên projection hoặc việc client biết query parameter là cơ chế bảo vệ.
6. **Dùng DTO hoặc controller riêng khi cần phân quyền theo ngữ cảnh:** nếu hai nhóm người dùng được phép thấy hai tập trường khác nhau, tạo representation có kiểm soát ở tầng service/controller và áp dụng authorization trước khi trả dữ liệu.

Ví dụ projection công khai chỉ đưa ra các trường cần thiết:

    @Projection(name = "publicUser", types = User.class)
    public interface PublicUser {
        Long getId();
        String getUsername();
    }

Không khai báo `getApiKeyHash()` trong `PublicUser`. Việc bỏ getter khỏi projection là cách trực tiếp để không đưa property đó vào view này.

## Kiểm tra dữ liệu có bị lộ hay không

Kiểm tra từng representation mà ứng dụng thực sự công bố:

1. Gọi endpoint mặc định của item và collection; xác nhận property có `@JsonIgnore` không xuất hiện.
2. Gọi item và collection với từng projection được đăng ký qua `?projection=...`.
3. Kiểm tra excerpt projection được cấu hình trên repository.
4. Kiểm tra nested projection, association và các getter dùng SpEL.
5. Thử bằng tài khoản có quyền thấp và tài khoản có quyền cao để xác nhận authorization được áp dụng đúng.
6. Viết integration test kiểm tra response body không chứa tên property hoặc giá trị bí mật, thay vì chỉ kiểm tra status `200 OK`.

Ví dụ test cần kiểm tra cả representation mặc định lẫn projection:

    mockMvc.perform(get("/api/users/42"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.apiKeyHash").doesNotExist());

    mockMvc.perform(get("/api/users/42")
            .param("projection", "publicUser"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.apiKeyHash").doesNotExist());

Điều chỉnh JSON path theo media type và cấu trúc response HAL của ứng dụng. Nếu property nằm trong `_embedded` hoặc object lồng nhau, kiểm tra đúng đường dẫn JSON tương ứng. Nên dùng giá trị bí mật giả trong test để phát hiện trường hợp dữ liệu bị đưa ra dưới tên khác.

## Khi cần bảo vệ dữ liệu nhạy cảm

- Đánh dấu `@JsonIgnore` để loại property khỏi representation mặc định khi phù hợp.
- Không khai báo property nhạy cảm trong bất kỳ projection công khai, excerpt projection hoặc nested projection nào.
- Nếu cần cho phép một số người dùng xem dữ liệu, thực hiện authorization ở server và trả representation theo quyền của người gọi.
- Cân nhắc không expose repository trực tiếp cho entity chứa bí mật; dùng DTO hoặc custom endpoint để kiểm soát rõ dữ liệu trả về.
- Kiểm tra response sau khi thêm projection mới hoặc thay đổi `excerptProjection`, vì đó là thay đổi bề mặt dữ liệu API.

`@JsonIgnore` không bảo đảm dữ liệu vắng mặt trong mọi representation do Spring Data REST tạo ra. Mỗi projection là một hợp đồng hiển thị riêng; chỉ công bố các trường an toàn và bảo vệ dữ liệu bằng authorization ở phía server.