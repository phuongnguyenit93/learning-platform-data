# Giới hạn liên kết dữ liệu để tránh gán trường ngoài ý muốn

Trong module **MODEL_VIEW_CONTROLLER**, Controller nhận dữ liệu từ form HTML hoặc API rồi chuyển thành đối tượng để tầng ứng dụng xử lý. Cơ chế này giúp giảm mã chuyển đổi thủ công, nhưng cũng tạo ra một rủi ro: nếu ứng dụng tự động liên kết mọi trường mà client gửi vào entity hoặc đối tượng nghiệp vụ, người dùng có thể gán những thuộc tính mà giao diện không hề cho phép sửa.

Rủi ro này thường được gọi là **Mass Assignment** hoặc **Over-posting**. Ví dụ, form chỉ có tên hiển thị và email, nhưng client tự thêm trường role, enabled hoặc ownerId vào request. Nếu Controller bind trực tiếp request vào entity User, các thuộc tính nhạy cảm có thể bị thay đổi ngoài ý muốn.

Biện pháp chính là giới hạn dữ liệu được phép bind bằng allowlist, dùng request DTO/form object chỉ chứa các trường client được phép gửi và ánh xạ tường minh sang command nghiệp vụ. Phân quyền vẫn phải được kiểm tra ở server cho từng thao tác; việc ẩn trường trên giao diện không tạo ra ranh giới bảo mật.

## 1. Data binding và rủi ro Mass Assignment

Data binding là quá trình chuyển dữ liệu từ request thành thuộc tính của một đối tượng. Trong Spring MVC, Controller có thể nhận một form object qua **@ModelAttribute**; framework đọc các tham số request rồi gán vào những thuộc tính có thể truy cập của đối tượng.

Ví dụ form chỉ hiển thị hai trường:

~~~html
<form method="post" action="/profile">
  <label>Tên hiển thị</label>
  <input name="displayName">
  <label>Email</label>
  <input name="email">
  <button type="submit">Lưu</button>
</form>
~~~

Người dùng có thể mở Developer Tools, dùng proxy hoặc tự tạo request để gửi thêm trường:

~~~http
POST /profile
Content-Type: application/x-www-form-urlencoded

displayName=Lan&email=lan@example.test&role=ADMIN&enabled=true
~~~

Trình duyệt không phải nơi thực thi chính sách bảo mật. Các trường ẩn, bị disable hoặc không xuất hiện trong HTML vẫn có thể được thêm vào request bằng công cụ khác.

Nếu Controller bind trực tiếp vào entity:

~~~java
@PostMapping("/users/{id}")
public String update(@PathVariable Long id,
                     @ModelAttribute User user) {
    userService.save(user);
    return "redirect:/users/" + id;
}
~~~

và entity có các thuộc tính role, enabled, ownerId hoặc balance, framework có thể bind những thuộc tính đó nếu chúng có thể được ghi. Khi đó, request có thể thay đổi dữ liệu vượt quá mục đích của form. Ngay cả khi form hiện tại không có trường nhạy cảm, một thuộc tính mới được thêm vào entity trong tương lai có thể vô tình mở rộng bề mặt binding.

## 2. Tách entity khỏi đối tượng nhận dữ liệu

Không nên dùng entity JPA làm form object hoặc request object cho mọi endpoint. Entity thường chứa nhiều thuộc tính phục vụ lưu trữ, quan hệ và quy tắc nội bộ; client chỉ nên được phép gửi một tập dữ liệu nhỏ theo chức năng cụ thể.

Ví dụ entity người dùng có thể có:

~~~java
public class User {
    private Long id;
    private String displayName;
    private String email;
    private String passwordHash;
    private String role;
    private boolean enabled;
    private Long ownerId;
    private Instant createdAt;
}
~~~

Form cập nhật hồ sơ chỉ cần:

~~~java
public class ProfileForm {
    @NotBlank
    @Size(max = 80)
    private String displayName;

    @NotBlank
    @Email
    private String email;

    // getter và setter
}
~~~

Đối tượng ProfileForm là **allowlist theo cấu trúc**: nó chỉ có những thuộc tính mà chức năng cập nhật hồ sơ chấp nhận. Request không có chỗ để bind role, passwordHash, enabled hoặc ownerId vào đối tượng này.

Khi xử lý, use case nhận danh tính người đang đăng nhập từ security context và chỉ cập nhật các trường được phép:

~~~java
public record UpdateProfileCommand(
        String displayName,
        String email
) {}
~~~

~~~java
@PostMapping("/profile")
public String updateProfile(
        @Valid @ModelAttribute("profileForm") ProfileForm form,
        BindingResult result,
        Authentication authentication) {

    if (result.hasErrors()) {
        return "profile/edit";
    }

    UpdateProfileCommand command = new UpdateProfileCommand(
            form.getDisplayName(),
            form.getEmail()
    );
    profileService.update(authentication.getName(), command);
    return "redirect:/profile";
}
~~~

Ở đây, danh tính tài khoản đến từ Authentication do server xác thực. Client không được quyết định tài khoản đích bằng cách gửi ownerId trong form. Service tìm hồ sơ thuộc về người đang đăng nhập, rồi áp dụng command lên đúng đối tượng.

## 3. Dùng allowlist với Spring WebDataBinder

Với form binding qua **@ModelAttribute**, Spring MVC cung cấp **WebDataBinder** để giới hạn thuộc tính được phép liên kết. Có thể khai báo allowlist trong **@InitBinder**:

~~~java
@Controller
public class ProfileController {

    @InitBinder("profileForm")
    void configureProfileBinder(WebDataBinder binder) {
        binder.setAllowedFields("displayName", "email");
    }

    // Các handler của trang hồ sơ
}
~~~

Tên trong **@InitBinder("profileForm")** phải khớp với tên model attribute mà handler sử dụng:

~~~java
@PostMapping("/profile")
public String update(
        @Valid @ModelAttribute("profileForm") ProfileForm form,
        BindingResult result) {
    // Xử lý form
}
~~~

Khi allowlist được thiết lập, Spring chỉ bind các thuộc tính được chỉ định. Những trường khác bị loại khỏi quá trình binding và có thể được đọc qua **BindingResult.getSuppressedFields()**.

Có thể xử lý các trường bị chặn một cách rõ ràng:

~~~java
if (result.getSuppressedFields().length > 0) {
    result.reject(
            "binding.disallowedFields",
            "Biểu mẫu chứa trường không được phép."
    );
}

if (result.hasErrors()) {
    return "profile/edit";
}
~~~

Tùy chính sách ứng dụng, trường bị chặn có thể khiến toàn bộ request bị từ chối hoặc được bỏ qua và ghi nhận sự kiện bảo mật. Với thao tác nhạy cảm, từ chối request có trường ngoài hợp đồng giúp phát hiện client cũ, lỗi tích hợp hoặc hành vi cố tình over-posting. Không ghi giá trị nhạy cảm của request vào log.

Allowlist nên hẹp và gắn với từng form object. Tránh cấu hình chung cho toàn Controller nếu các endpoint có quyền sửa khác nhau.

## 4. Vì sao allowlist tốt hơn denylist?

Có hai cách giới hạn binding:

- **Allowlist:** chỉ định rõ những trường được phép nhận.
- **Denylist:** chỉ định các trường bị cấm.

Ví dụ denylist:

~~~java
binder.setDisallowedFields("role", "enabled", "ownerId");
~~~

Cách này có thể hữu ích như một lớp bổ sung, nhưng dễ bỏ sót thuộc tính mới. Nếu entity được thêm trường **isAdmin**, **creditLimit** hoặc **approvedAt**, denylist cũ không tự biết rằng các trường đó cũng nhạy cảm.

Allowlist thể hiện trực tiếp hợp đồng của form:

~~~java
binder.setAllowedFields("displayName", "email");
~~~

Khi entity có thêm thuộc tính mới, form vẫn chỉ bind hai trường đã khai báo. Đây là nguyên tắc an toàn hơn cho những endpoint nhận dữ liệu từ bên ngoài.

## 5. Kiểm soát thuộc tính lồng nhau và collection

Binding không chỉ áp dụng cho thuộc tính ở cấp cao nhất. Một form object có thể chứa đối tượng lồng nhau hoặc danh sách:

~~~java
public class OrderForm {
    private String note;
    private AddressForm shippingAddress;
    private List<OrderLineForm> lines;
}
~~~

Nếu cho phép binding quá rộng, client có thể thử gửi các đường dẫn như thông tin chủ sở hữu của địa chỉ, giá đã duyệt, trạng thái đơn hoặc chỉ số collection rất lớn. Các thuộc tính lồng nhau cũng cần được xem xét như một phần của hợp đồng đầu vào.

Một số nguyên tắc:

- Chỉ cho phép các đường dẫn lồng nhau mà form thực sự cần, chẳng hạn shippingAddress.city và shippingAddress.postalCode.
- Không bind trực tiếp quan hệ entity hoặc object graph lớn.
- Không dùng wildcard rộng cho toàn bộ thuộc tính lồng nhau nếu chưa đánh giá từng đường dẫn.
- Giới hạn số phần tử collection và kích thước request.
- Kiểm tra từng phần tử trong use case; không tin giá, owner hoặc trạng thái do client gửi.

Có thể đặt giới hạn collection growth cho WebDataBinder:

~~~java
@InitBinder("orderForm")
void configureOrderBinder(WebDataBinder binder) {
    binder.setAllowedFields(
            "note",
            "shippingAddress.city",
            "shippingAddress.postalCode",
            "lines[*].productId",
            "lines[*].quantity"
    );
    binder.setAutoGrowCollectionLimit(20);
}
~~~

Ví dụ trên minh họa cách giới hạn đường dẫn và số phần tử có thể tự mở rộng; cú pháp pattern và hành vi cần được xác nhận với phiên bản Spring đang dùng. Không cho phép client gửi đơn giá hoặc tổng tiền nếu server phải tự tính các giá trị đó.

## 6. Constructor binding và DTO bất biến

Một lựa chọn khác là dùng DTO chỉ có các trường cần thiết và khởi tạo qua constructor. Java record phù hợp với các request DTO đơn giản:

~~~java
public record UpdateContactRequest(
        @NotBlank @Size(max = 80) String displayName,
        @NotBlank @Email String email
) {}
~~~

Với API JSON:

~~~java
@PutMapping("/api/me/contact")
public ResponseEntity<Void> updateContact(
        @Valid @RequestBody UpdateContactRequest request,
        @AuthenticationPrincipal AppPrincipal principal) {

    profileService.update(
            principal.userId(),
            new UpdateProfileCommand(
                    request.displayName(),
                    request.email()
            )
    );
    return ResponseEntity.noContent().build();
}
~~~

Record chỉ khai báo displayName và email, nên các trường role hoặc ownerId không phải thành phần của hợp đồng request và không được gán vào entity qua DTO này. Cấu hình Jackson có thể quyết định thuộc tính JSON không biết sẽ bị từ chối hay bỏ qua; cần chọn hành vi nhất quán và kiểm thử. Dù cấu hình bỏ qua trường lạ, DTO vẫn phải chỉ chứa các thuộc tính được phép.

**Lưu ý quan trọng:** WebDataBinder và **@InitBinder** áp dụng cho quá trình binding của Spring MVC, chẳng hạn **@ModelAttribute**. JSON nhận bằng **@RequestBody** thường được giải mã qua HttpMessageConverter/Jackson; allowlist của WebDataBinder không tự giới hạn thuộc tính JSON. Với JSON, cần dùng request DTO riêng và cấu hình/kiểm thử deserialization phù hợp.

## 7. Ánh xạ tường minh thay vì sao chép toàn bộ thuộc tính

Sau khi binding, ứng dụng cần chuyển dữ liệu đầu vào thành thay đổi nghiệp vụ có chủ đích. Tránh sao chép hàng loạt thuộc tính từ request object sang entity nếu không kiểm soát chính xác trường nào được phép cập nhật.

Ví dụ không nên dùng cách sao chép tổng quát:

~~~java
BeanUtils.copyProperties(request, user);
~~~

Nếu request object hoặc entity thay đổi theo thời gian, việc sao chép có thể đưa thêm thuộc tính ngoài dự kiến vào luồng cập nhật. Hãy gán tường minh:

~~~java
public void updateProfile(User user, UpdateProfileCommand command) {
    user.changeDisplayName(command.displayName());
    user.changeEmail(command.email());
}
~~~

Các thay đổi nhạy cảm như đổi vai trò, kích hoạt tài khoản, đổi chủ sở hữu hoặc điều chỉnh hạn mức nên đi qua use case riêng, có quyền tương ứng và quy tắc nghiệp vụ riêng. Việc cập nhật hồ sơ không nên vô tình trở thành API thay đổi quyền.

## 8. Phân biệt binding, validation và authorization

Ba bước này có mục tiêu khác nhau:

| Cơ chế | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Binding** | Trường nào được phép nhận từ request? | Chỉ bind displayName và email |
| **Validation** | Giá trị nhận được có đúng định dạng và ràng buộc không? | Email đúng định dạng, tên không rỗng |
| **Authorization** | Người dùng có quyền thực hiện hành động trên tài nguyên này không? | Người dùng chỉ sửa hồ sơ của chính mình |

Validation không ngăn mass assignment nếu entity vẫn nhận trường role hợp lệ về kiểu dữ liệu. Authorization cũng không tự ngăn một thuộc tính nhạy cảm bị bind vào object trước khi use case chạy. Cần giới hạn binding, xác thực dữ liệu và kiểm tra quyền ở các ranh giới tương ứng.

Ví dụ, một request có email hợp lệ và role là ADMIN vẫn phải bị loại bỏ hoặc từ chối nếu chức năng chỉ cho phép sửa thông tin liên hệ. Việc người gửi đã đăng nhập không có nghĩa họ được phép gán mọi thuộc tính.

## 9. Không tin trường ẩn, trường chỉ đọc hoặc ID do client gửi

Các thuộc tính sau vẫn do client kiểm soát khi xuất hiện trong request:

- Hidden input chứa userId, ownerId hoặc tenantId.
- Input có thuộc tính readonly hoặc disabled.
- Giá trị được đưa vào query string hoặc URL path.
- Trường version, status hoặc role trong JSON.
- ID của đối tượng lồng nhau hoặc phần tử collection.

Thuộc tính disabled thường không được trình duyệt gửi theo form chuẩn, nhưng client có thể tự tạo request chứa nó. Hidden và readonly chỉ ảnh hưởng giao diện, không phải cơ chế bảo mật.

Nếu endpoint cần một resource ID trong URL, server có thể dùng ID đó để xác định tài nguyên, nhưng vẫn phải truy vấn trong phạm vi người gọi được phép:

~~~java
Order order = orderRepository
        .findByIdAndOwnerId(orderId, principal.userId())
        .orElseThrow(OrderNotFoundException::new);
~~~

Không dùng ownerId do client gửi làm bằng chứng quyền sở hữu. Với ứng dụng multi-tenant, tenant hiện tại cũng cần được xác định và xác minh từ security context hoặc cơ chế chọn tenant đã được kiểm tra.

## 10. Thiết kế PATCH và cập nhật một phần

Endpoint PATCH thường chỉ cập nhật một số trường. Cần phân biệt rõ ba trạng thái:

1. Trường không xuất hiện trong request: người dùng không yêu cầu thay đổi trường đó.
2. Trường xuất hiện với giá trị hợp lệ: cập nhật trường theo giá trị mới.
3. Trường xuất hiện với null hoặc chuỗi rỗng: có thể là yêu cầu xóa giá trị, hoặc dữ liệu không hợp lệ, tùy hợp đồng.

Nếu dùng DTO mà mọi trường đều nullable rồi sao chép các giá trị khác null, ứng dụng có thể không phân biệt được trường bị bỏ qua với trường người dùng muốn xóa. Hãy định nghĩa rõ semantics của PATCH, dùng kiểu biểu diễn có trạng thái hiện diện (presence-aware) khi cần, và chỉ cho phép các trường nằm trong allowlist.

Ví dụ, chức năng cập nhật địa chỉ có thể cho phép street, city và postalCode. Không nên nhận thêm status, ownerId hoặc verifiedAt chỉ vì entity địa chỉ có những thuộc tính đó.

## 11. Các lớp bảo vệ bổ sung

Giới hạn binding là một phần của thiết kế đầu vào. Có thể kết hợp với:

- **Authentication:** xác định danh tính người gửi từ session hoặc token đã được xác thực.
- **Authorization:** kiểm tra quyền trên từng use case và tài nguyên.
- **CSRF protection:** bảo vệ form dựa trên cookie session khỏi một số request giả mạo từ website khác.
- **Validation:** giới hạn kiểu, độ dài, miền giá trị và quan hệ giữa các trường.
- **Rate limiting:** hạn chế tần suất thao tác nhạy cảm hoặc tốn tài nguyên.
- **Audit log:** ghi nhận thay đổi quyền, trạng thái và dữ liệu quan trọng với danh tính thực hiện.

CSRF token không ngăn mass assignment. Một request có token CSRF hợp lệ vẫn có thể chứa trường role ngoài ý muốn nếu server bind quá rộng. Tương tự, HTTPS bảo vệ dữ liệu trên đường truyền nhưng không quyết định trường nào được phép cập nhật.

## 12. Kiểm thử chống Mass Assignment

Kiểm thử nên mô phỏng client gửi thêm các trường không có trong form hoặc request DTO. Cần xác nhận các trường được phép vẫn hoạt động, trường nhạy cảm bị chặn và trạng thái trong database không thay đổi ngoài ý muốn.

Ví dụ với Spring MockMvc, giả sử Controller dùng allowlist cho profileForm và từ chối khi có suppressed field:

~~~java
@WebMvcTest(ProfileController.class)
class ProfileControllerTest {
    @Autowired
    MockMvc mvc;

    @MockBean
    ProfileService profileService;

    @Test
    @WithMockUser(username = "lan")
    void rejectsUnexpectedRoleField() throws Exception {
        mvc.perform(post("/profile").with(csrf())
                        .param("displayName", "Lan")
                        .param("email", "lan@example.test")
                        .param("role", "ADMIN")
                        .param("enabled", "true"))
                .andExpect(status().isOk())
                .andExpect(view().name("profile/edit"))
                .andExpect(model().attributeHasErrors("profileForm"));

        verifyNoInteractions(profileService);
    }
}
~~~

Đây là ví dụ kiểm thử theo chính sách từ chối trường ngoài hợp đồng. Cấu hình security, tên view và cách tạo form object cần khớp ứng dụng thực tế. Nếu chính sách là bỏ qua trường bị chặn, test cần xác nhận service chỉ nhận các giá trị hợp lệ và role/enabled không thay đổi.

Các trường hợp nên có:

- Gửi role, enabled, ownerId, passwordHash hoặc thuộc tính nội bộ cùng form hợp lệ.
- Gửi đường dẫn thuộc tính lồng nhau không được cho phép.
- Gửi index collection rất lớn hoặc số phần tử vượt giới hạn.
- Gửi ID của người dùng khác và xác nhận truy vấn vẫn bị giới hạn theo chủ sở hữu.
- Gửi JSON có thêm trường nhạy cảm vào endpoint dùng @RequestBody.
- Kiểm tra cập nhật một phần khi trường bị bỏ qua, null hoặc rỗng.
- Xác nhận các chức năng quản trị hợp lệ vẫn hoạt động qua use case có quyền riêng.
- Kiểm tra entity sau thao tác để bảo đảm role, owner, enabled và các trường nội bộ không bị thay đổi.

Kiểm thử tích hợp với database thường hữu ích hơn việc chỉ kiểm tra response HTML, vì mục tiêu cuối cùng là bảo đảm trạng thái lưu trữ không bị thay đổi trái phép.

## 13. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Bind request trực tiếp vào JPA entity | Client có thể gán thuộc tính nội bộ | Dùng form object/request DTO riêng |
| Chỉ ẩn trường trên giao diện | Client vẫn có thể tự gửi trường | Kiểm soát binding ở server |
| Chỉ dùng denylist | Thuộc tính mới có thể bị bỏ sót | Dùng allowlist theo từng chức năng |
| Cho phép binding object graph rộng | Có thể sửa quan hệ hoặc thuộc tính lồng nhau | Chỉ cho phép đường dẫn cần thiết |
| Dùng @InitBinder cho JSON @RequestBody | Hiểu nhầm rằng JSON đã được giới hạn | Dùng DTO JSON và kiểm soát Jackson |
| Sao chép toàn bộ request vào entity | Trường mới có thể được cập nhật ngoài ý muốn | Ánh xạ tường minh |
| Tin userId/ownerId từ form | Có nguy cơ truy cập chéo tài khoản | Lấy danh tính từ principal và giới hạn truy vấn |
| Xem validation là authorization | Giá trị đúng kiểu vẫn có thể vượt quyền | Kiểm tra quyền riêng ở use case |
| Dùng một DTO cho cả request và response | Hợp đồng đầu vào có thể chứa trường chỉ dành cho server | Tách request DTO và response DTO |

## 14. Quy trình thiết kế binding an toàn

Khi tạo một endpoint MVC nhận dữ liệu, hãy thực hiện theo trình tự:

1. Xác định chức năng cho phép người dùng thay đổi những trường nào.
2. Tạo form object hoặc request DTO riêng, chỉ chứa các trường đó.
3. Với @ModelAttribute, cấu hình WebDataBinder bằng allowlist phù hợp với từng form.
4. Kiểm soát thuộc tính lồng nhau, collection và giới hạn kích thước request.
5. Với @RequestBody JSON, dùng DTO riêng và kiểm thử hành vi deserialization; không dựa vào @InitBinder.
6. Lấy user ID và tenant ID từ danh tính/ngữ cảnh đã được xác thực ở server.
7. Validate dữ liệu và kiểm tra quyền trên tài nguyên trong use case.
8. Ánh xạ tường minh DTO thành command và chỉ cập nhật các thuộc tính được phép.
9. Xử lý suppressed fields theo chính sách rõ ràng và không log dữ liệu nhạy cảm.
10. Kiểm thử over-posting, nested properties, IDOR và trạng thái database sau cập nhật.

Ví dụ chức năng cập nhật hồ sơ chỉ nhận displayName và email. Controller bind hai trường này, lấy tài khoản hiện tại từ security context, rồi gọi use case cập nhật đúng hồ sơ. Nếu sau này entity User có thêm trường isAdmin hoặc accountLocked, hợp đồng của form vẫn không thay đổi và hai trường đó không tự nhiên trở thành dữ liệu có thể bind.

## Kết luận

Giới hạn liên kết dữ liệu giúp bảo đảm client chỉ có thể yêu cầu thay đổi những thuộc tính mà chức năng công khai. Trong Spring MVC, hãy tách entity khỏi form object, dùng allowlist với WebDataBinder cho @ModelAttribute, dùng request DTO riêng cho JSON @RequestBody và ánh xạ tường minh sang command. Kết hợp với xác thực, phân quyền, validation và kiểm thử nhiều trường hợp over-posting, ứng dụng giảm nguy cơ người dùng tự gán role, owner, trạng thái hoặc dữ liệu nội bộ ngoài ý muốn.
