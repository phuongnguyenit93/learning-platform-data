# Ngăn chi tiết nội bộ rò rỉ qua dữ liệu trả về

Trong module **MODEL_VIEW_CONTROLLER**, Controller tiếp nhận request, gọi tầng ứng dụng hoặc Model rồi chọn response và dữ liệu cho client. Dữ liệu trả về là một hợp đồng công khai: nó cho biết client được phép nhìn thấy thông tin nào và có thể dựa vào cấu trúc nào. Nếu Controller trả thẳng entity hoặc đối tượng nội bộ, ứng dụng có thể vô tình tiết lộ dữ liệu nhạy cảm, cấu trúc lưu trữ hoặc thông tin kỹ thuật không dành cho người dùng.

Để ngăn rò rỉ, hãy xác định rõ dữ liệu nào được phép xuất hiện trong response, chuyển dữ liệu đó thành DTO dành riêng cho đầu ra và kiểm thử nội dung thực tế được tuần tự hóa. Việc ẩn một trường trên giao diện không đủ bảo vệ dữ liệu nếu trường đó vẫn có trong JSON hoặc HTML được gửi đến trình duyệt.

## 1. Rò rỉ chi tiết nội bộ là gì?

Rò rỉ xảy ra khi response chứa thông tin vượt quá nhu cầu của client hoặc tiết lộ chi tiết mà ứng dụng cần giữ riêng. Dữ liệu có thể bị lộ qua HTML, JSON, XML, header, thông báo lỗi, URL hoặc metadata đi kèm.

Một entity người dùng có thể chứa:

~~~java
public class UserEntity {
    private Long id;
    private String displayName;
    private String email;
    private String passwordHash;
    private boolean enabled;
    private String resetToken;
    private Instant lastLoginAt;
    private String internalNote;
    private Instant createdAt;
    // getters và setters
}
~~~

Trang hồ sơ có thể chỉ cần tên hiển thị và email. Nếu Controller trả toàn bộ **UserEntity**, response có nguy cơ chứa password hash, reset token, ghi chú nội bộ hoặc những trường không cần thiết. Ngay cả khi template hiện tại không hiển thị các trường đó, một API serializer có thể tự động đưa chúng vào JSON.

Rò rỉ không chỉ là mật khẩu hoặc token. Một số ví dụ khác:

- Giá mua nội bộ, biên lợi nhuận, ghi chú vận hành hoặc trạng thái kiểm duyệt.
- ID của hệ thống bên ngoài, tên bảng, tên cột hoặc quan hệ giữa các entity.
- Địa chỉ email, số điện thoại hoặc dữ liệu cá nhân không cần cho chức năng.
- Stack trace, câu SQL, đường dẫn file, hostname hoặc thông tin cấu hình.
- Số lượng bản ghi, mã lỗi nội bộ hoặc metadata giúp suy đoán cấu trúc hệ thống.

Thông tin có thể không phải bí mật tuyệt đối nhưng vẫn không nên công khai nếu client không có lý do hợp lệ để nhận nó.

## 2. Vì sao trả trực tiếp entity là rủi ro?

Entity thường được thiết kế để quản lý trạng thái và quan hệ trong miền nghiệp vụ hoặc ánh xạ cơ sở dữ liệu. Response cần một cấu trúc ổn định phục vụ client. Hai mục đích này khác nhau.

Khi serialize entity trực tiếp, các rủi ro thường gặp gồm:

1. **Lộ trường ngoài ý muốn:** một thuộc tính mới được thêm vào entity có thể tự động xuất hiện trong response.
2. **Phụ thuộc vào cấu trúc lưu trữ:** đổi tên cột, quan hệ hoặc kiểu ORM có thể làm thay đổi API.
3. **Lộ quan hệ nội bộ:** serializer có thể đi theo quan hệ lồng nhau và trả về nhiều dữ liệu hơn dự kiến.
4. **Vòng tham chiếu khi serialize:** hai entity tham chiếu qua lại có thể gây lỗi hoặc cấu trúc JSON quá sâu.
5. **Truy vấn ngoài dự kiến:** truy cập quan hệ lazy trong lúc render hoặc serialize có thể tạo nhiều truy vấn và làm response chậm.
6. **Khó kiểm soát quyền:** cùng một entity có thể được nhiều vai trò sử dụng nhưng mỗi vai trò chỉ được xem một tập trường khác nhau.

Ví dụ, nếu **OrderEntity** chứa khách hàng, địa chỉ giao hàng, giao dịch thanh toán và ghi chú vận hành, serialize toàn bộ entity có thể làm lộ các quan hệ và trường mà trang danh sách đơn hàng không cần.

## 3. Dùng response DTO theo nguyên tắc allowlist

Một response DTO định nghĩa rõ những trường được phép gửi ra ngoài. Đây là cách tiếp cận **allowlist**: chỉ khai báo dữ liệu cần công khai, thay vì lấy toàn bộ entity rồi cố gắng loại bỏ từng trường nhạy cảm.

Ví dụ, DTO hồ sơ công khai:

~~~java
public record UserProfileResponse(
        String displayName,
        String email
) {}
~~~

Controller hoặc mapper chuyển entity thành DTO:

~~~java
public UserProfileResponse toProfileResponse(UserEntity user) {
    return new UserProfileResponse(
            user.getDisplayName(),
            user.getEmail()
    );
}
~~~

Endpoint trả DTO:

~~~java
@RestController
@RequestMapping("/api/users")
public class UserController {
    private final UserQuery userQuery;
    private final UserResponseMapper mapper;

    public UserController(UserQuery userQuery, UserResponseMapper mapper) {
        this.userQuery = userQuery;
        this.mapper = mapper;
    }

    @GetMapping("/{id}")
    public UserProfileResponse profile(@PathVariable long id) {
        UserEntity user = userQuery.getById(id);
        return mapper.toProfileResponse(user);
    }
}
~~~

Serializer chỉ nhìn thấy hai trường trong **UserProfileResponse**. Khi entity được bổ sung **resetToken** hoặc **internalNote**, response không tự thay đổi. Hợp đồng đầu ra trở nên rõ ràng và ít bị ảnh hưởng bởi cấu trúc nội bộ.

Với server-side MVC, cùng nguyên tắc áp dụng cho view model. Controller truyền một đối tượng chỉ có trường mà template cần; template không nhận entity đầy đủ rồi tự quyết định trường nào nên ẩn.

## 4. Tách hợp đồng đầu vào và đầu ra

DTO nhận request và DTO trả response phục vụ hai mục đích khác nhau. Dùng chung một lớp cho cả hai hướng có thể khiến client gửi được những trường mà họ không nên điều khiển hoặc khiến response vô tình công khai trường nội bộ.

Ví dụ, không nên nhận một **UserEntity** trực tiếp để cập nhật hồ sơ:

~~~java
@PutMapping("/{id}")
public UserEntity update(
        @PathVariable long id,
        @RequestBody UserEntity user) {
    // Rủi ro: client có thể gửi thêm trường không được phép thay đổi
    return userService.update(id, user);
}
~~~

Thay vào đó, định nghĩa request DTO chỉ có trường được phép sửa và response DTO chỉ có trường được phép xem:

~~~java
public record UpdateProfileRequest(
        @NotBlank @Size(max = 80) String displayName
) {}

public record UserProfileResponse(
        String displayName,
        String email
) {}
~~~

Controller chuyển request thành lệnh nghiệp vụ và chuyển kết quả thành response:

~~~java
@PutMapping("/{id}/profile")
public UserProfileResponse updateProfile(
        @PathVariable long id,
        @Valid @RequestBody UpdateProfileRequest request) {
    UserProfile profile = userService.updateDisplayName(
            id,
            request.displayName()
    );
    return new UserProfileResponse(profile.displayName(), profile.email());
}
~~~

Việc tách hai DTO giúp ngăn **mass assignment**: client không thể tự gửi thêm trường như **role**, **enabled**, **passwordHash** hoặc **accountBalance** rồi mong framework binding chúng vào entity. Use case vẫn phải kiểm tra quyền và quy tắc nghiệp vụ; DTO chỉ giới hạn hình dạng dữ liệu đầu vào.

## 5. Trả dữ liệu khác nhau theo mục đích và quyền truy cập

Không phải mọi người dùng đều được xem cùng một tập dữ liệu. Một nhân viên hỗ trợ có thể cần trạng thái xử lý và mã đơn; chủ đơn hàng có thể xem địa chỉ giao hàng; bộ phận tài chính có thể cần thông tin thanh toán theo quyền được cấp.

Có thể thiết kế response theo use case hoặc vai trò:

| Response | Người nhận | Trường ví dụ |
| --- | --- | --- |
| **OrderSummaryResponse** | Danh sách đơn hàng | Mã đơn, ngày tạo, trạng thái, tổng tiền |
| **OrderDetailResponse** | Chủ đơn hàng | Dòng hàng, địa chỉ giao hàng được phép xem, tổng tiền |
| **OrderSupportResponse** | Nhân viên hỗ trợ có quyền | Mã đơn, trạng thái xử lý, thông tin liên hệ cần thiết |
| **OrderFinanceResponse** | Nhân viên tài chính có quyền | Tổng tiền, trạng thái thanh toán, mã giao dịch phù hợp |

Không nên dùng một DTO khổng lồ chứa mọi trường rồi chỉ dựa vào View để ẩn phần không cần. Nếu một trường không được phép gửi cho client, nó không nên xuất hiện trong response body của client đó.

Quyền truy cập cần được kiểm tra trước khi tạo response. Ví dụ, chỉ kiểm tra người dùng đã đăng nhập là chưa đủ; ứng dụng còn phải xác nhận người đó có quyền xem đúng đơn hàng đang yêu cầu. Đây là kiểm tra quyền trên tài nguyên, giúp tránh lỗi truy cập đối tượng trực tiếp (IDOR).

## 6. Kiểm soát dữ liệu lồng nhau và quan hệ

Response DTO có thể chứa DTO con, nhưng mỗi cấp cần được thiết kế có chủ đích. Không nên đặt entity làm trường con trong response DTO rồi kỳ vọng serializer tự biết giới hạn dữ liệu.

Ví dụ:

~~~java
public record OrderSummaryResponse(
        String orderNumber,
        String status,
        List<OrderLineResponse> lines,
        MoneyResponse total
) {}

public record OrderLineResponse(
        String productName,
        int quantity
) {}

public record MoneyResponse(
        long amount,
        String currency
) {}
~~~

Ở đây, **OrderSummaryResponse** chứa các kiểu response đã kiểm soát. Nó không tham chiếu trực tiếp đến **OrderEntity**, **ProductEntity** hoặc đối tượng thanh toán nội bộ.

Khi thiết kế dữ liệu lồng nhau, hãy xem xét:

- Độ sâu của cấu trúc và số lượng phần tử có thể trả về.
- Trường nào cần thiết ở mỗi cấp.
- Có cần phân trang cho danh sách con hay không.
- Có thể tạo vòng tham chiếu hoặc payload quá lớn hay không.
- Người dùng có quyền xem từng tài nguyên liên quan hay không.

Một response gọn thường dễ bảo trì và tiết kiệm băng thông hơn. Nếu client cần dữ liệu chi tiết của một tài nguyên liên quan, có thể cung cấp endpoint riêng hoặc một projection được thiết kế rõ.

## 7. Không tiết lộ chi tiết qua lỗi và metadata

Dữ liệu trả về bao gồm cả lỗi. Một exception có thể chứa tên bảng, đường dẫn file, câu truy vấn, giá trị đầu vào hoặc thông tin môi trường. Trả trực tiếp nội dung exception cho client có thể tiết lộ cách hệ thống hoạt động.

Thay vì:

~~~java
@ExceptionHandler(Exception.class)
public ResponseEntity<String> handle(Exception exception) {
    return ResponseEntity.internalServerError()
            .body(exception.getMessage());
}
~~~

Hãy trả một cấu trúc lỗi công khai, có mã ổn định và thông báo an toàn:

~~~java
public record ApiError(
        String code,
        String message,
        String traceId
) {}

@ExceptionHandler(Exception.class)
public ResponseEntity<ApiError> handleUnexpected(
        Exception exception) {
    // Ghi exception đầy đủ vào log phía server với traceId phù hợp
    ApiError error = new ApiError(
            "INTERNAL_ERROR",
            "Đã xảy ra lỗi. Vui lòng thử lại sau.",
            currentTraceId()
    );
    return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
            .body(error);
}
~~~

Ví dụ trên chỉ minh họa cấu trúc; cách lấy trace ID và ghi log phụ thuộc vào hệ thống logging. Client nhận mã lỗi và thông báo đủ để xử lý. Nhóm vận hành dùng trace ID để tìm log có kiểm soát quyền truy cập.

Tránh trả các thông tin sau nếu không có lý do công khai rõ ràng:

- Stack trace, tên package, tên class hoặc phiên bản thư viện.
- SQL, cấu trúc bảng, tên máy chủ, địa chỉ mạng nội bộ.
- Token, cookie, header xác thực hoặc dữ liệu phiên.
- Nội dung exception thô hoặc dữ liệu đầu vào nhạy cảm.
- Đường dẫn file tuyệt đối và cấu hình môi trường.

Metadata cũng cần được xem xét. Ví dụ, số lượng bản ghi tổng, thông tin phân trang, mã nội bộ hoặc header debug có thể tiết lộ quy mô và cấu trúc hệ thống. Chỉ công khai những metadata mà hợp đồng yêu cầu.

## 8. Các annotation ẩn trường có đủ không?

Một số thư viện serialize hỗ trợ annotation như **@JsonIgnore** hoặc cấu hình view để loại trường khỏi JSON. Chúng có ích trong một số trường hợp, nhưng không nên là lớp bảo vệ duy nhất cho dữ liệu nhạy cảm.

| Cách làm | Lợi ích | Hạn chế cần lưu ý |
| --- | --- | --- |
| Response DTO riêng | Allowlist rõ ràng, hợp đồng độc lập với entity | Cần mapper hoặc projection |
| **@JsonIgnore** | Nhanh để loại một trường khỏi JSON | Có thể bị quên khi thêm endpoint hoặc dùng serializer khác |
| Serialization view | Có thể chọn nhóm trường theo view | Cấu hình phức tạp hơn, dễ khó theo dõi khi nhiều vai trò |
| Trả entity rồi xóa trường trước khi gửi | Có thể tái sử dụng trong mã ngắn hạn | Dễ bỏ sót trường mới và khó chứng minh dữ liệu nào được phép |

Với response công khai hoặc có dữ liệu nhạy cảm, DTO riêng thường dễ kiểm soát nhất. Nếu dùng annotation trên entity, cần kiểm thử response ở cấp endpoint và rà soát mọi đường serialize. Không xem việc một trường không xuất hiện trong một template là bằng chứng nó không bị gửi đi.

## 9. Hợp đồng response ổn định khi Model thay đổi

Hợp đồng dữ liệu là một phần của giao diện mà client phụ thuộc. Nếu response phản chiếu trực tiếp entity, thay đổi nội bộ có thể trở thành thay đổi API ngoài ý muốn.

Ví dụ, entity ban đầu có trường **name**. Sau này nhóm phát triển đổi thành **displayName** hoặc tách thành **firstName** và **lastName**. Nếu response dùng DTO, mapper có thể tiếp tục cung cấp trường **displayName** cho client. Nếu serialize entity trực tiếp, cấu trúc JSON có thể thay đổi theo refactor nội bộ.

Một số nguyên tắc để giữ hợp đồng ổn định:

- Đặt tên trường theo ngôn ngữ của client và mục đích sử dụng, không theo tên cột cơ sở dữ liệu.
- Chỉ thêm trường mới khi nó có ý nghĩa và không phá vỡ client hiện tại.
- Không đổi kiểu dữ liệu hoặc ý nghĩa của trường một cách âm thầm.
- Khi cần thay đổi không tương thích, dùng versioning hoặc kế hoạch chuyển đổi có thời hạn.
- Quy định rõ giá trị có thể null, trường tùy chọn, định dạng ngày giờ và đơn vị đo.
- Tránh đưa enum nội bộ chưa ổn định ra ngoài nếu tên hoặc ý nghĩa của enum có thể thay đổi.

Ví dụ, response nên ghi rõ tiền tệ thay vì chỉ gửi một số tiền không có đơn vị. Ngày giờ nên có định dạng và múi giờ xác định. Những chi tiết này giúp client hiểu dữ liệu mà không phải suy đoán.

## 10. Kiểm thử để phát hiện rò rỉ

Kiểm thử response nên xác minh cả những trường bắt buộc phải có và những trường tuyệt đối không được xuất hiện. Chỉ kiểm tra status 200 hoặc kiểm tra template render thành công là chưa đủ.

Một số tình huống nên có:

- Hồ sơ công khai chỉ chứa tên hiển thị và email được phép công khai.
- Response không chứa password hash, reset token, internal note hoặc role nội bộ nếu client không được phép xem.
- Người dùng không thể lấy response của tài nguyên thuộc người khác bằng cách thay ID.
- DTO lồng nhau không kéo theo entity hoặc quan hệ ngoài dự kiến.
- Lỗi 500 không chứa stack trace, SQL hoặc thông tin môi trường.
- Thêm trường mới vào entity không tự động làm response công khai thay đổi.
- Response của từng vai trò chỉ chứa dữ liệu mà vai trò đó được phép nhận.

Ví dụ kiểm thử JSON với Spring MockMvc:

~~~java
@WebMvcTest(UserController.class)
class UserControllerTest {
    @Autowired
    MockMvc mvc;

    @MockBean
    UserQuery userQuery;

    @Test
    void profileDoesNotExposeInternalFields() throws Exception {
        given(userQuery.getProfile(7L))
                .willReturn(new UserProfileResponse(
                        "Lan",
                        "lan@example.test"
                ));

        mvc.perform(get("/api/users/7"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.displayName").value("Lan"))
                .andExpect(jsonPath("$.email").value("lan@example.test"))
                .andExpect(jsonPath("$.passwordHash").doesNotExist())
                .andExpect(jsonPath("$.resetToken").doesNotExist())
                .andExpect(jsonPath("$.internalNote").doesNotExist());
    }
}
~~~

Đây là ví dụ minh họa; cần điều chỉnh kiểu trả về, route và cấu hình mock theo ứng dụng. Có thể bổ sung kiểm thử contract để xác nhận nhiều endpoint hoặc phiên bản API vẫn tuân thủ cấu trúc response đã công bố.

## 11. Quy trình thiết kế response an toàn

Khi xây dựng endpoint hoặc View mới, hãy thực hiện theo trình tự:

1. Xác định ai sẽ nhận response và mục đích sử dụng dữ liệu.
2. Liệt kê trường cần thiết để hoàn thành chức năng.
3. Phân loại trường công khai, trường chỉ dành cho vai trò cụ thể và trường nội bộ không được gửi ra.
4. Tạo response DTO hoặc view model theo allowlist.
5. Chuyển dữ liệu từ Model sang DTO qua mapper hoặc projection có kiểm soát.
6. Kiểm tra quyền truy cập trên tài nguyên trước khi lấy và trả dữ liệu.
7. Dùng cấu trúc lỗi công khai, giữ chi tiết kỹ thuật trong log phía server.
8. Kiểm thử payload thực tế, bao gồm trường bị cấm và dữ liệu lồng nhau.
9. Xem xét tác động tương thích khi hợp đồng thay đổi.

Với một trang chi tiết đơn hàng, có thể bắt đầu từ câu hỏi: người mua cần thấy gì để theo dõi đơn? Từ đó tạo **OrderDetailResponse** gồm mã đơn, trạng thái, dòng hàng và tổng tiền. Ghi chú vận hành, cờ chống gian lận và mã tích hợp nội bộ không thuộc hợp đồng của người mua. Một màn hình hỗ trợ nội bộ có thể cần thêm một số trường, nhưng phải dùng response riêng và kiểm tra quyền tương ứng.

## Kết luận

Response là hợp đồng công khai giữa ứng dụng và client. Để ngăn rò rỉ chi tiết nội bộ, hãy dùng response DTO hoặc view model theo allowlist, tách DTO đầu vào khỏi đầu ra, kiểm soát dữ liệu lồng nhau, xác minh quyền truy cập và ánh xạ lỗi thành thông báo an toàn. Kiểm thử payload thực tế giúp phát hiện trường ngoài ý muốn và giữ cho thay đổi ở Model không âm thầm làm lộ dữ liệu hoặc phá vỡ hợp đồng của ứng dụng MVC.
