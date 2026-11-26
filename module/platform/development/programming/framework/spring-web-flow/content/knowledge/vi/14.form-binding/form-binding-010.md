# Chọn form model riêng thay cho nhận trực tiếp mọi thuộc tính entity

## 1. Vì sao không nên bind trực tiếp entity vào biểu mẫu?

Trong một ứng dụng Spring Web Flow, form là điểm giao tiếp giữa trình duyệt và flow. Người dùng gửi dữ liệu qua HTTP request; Spring Web Flow liên kết dữ liệu đó vào model của view-state để các transition và action tiếp tục xử lý. Nếu model được chọn là entity đang lưu trong cơ sở dữ liệu, dữ liệu gửi lên có thể tác động tới nhiều thuộc tính hơn những gì màn hình hiển thị.

Ví dụ, màn hình chỉnh sửa hồ sơ chỉ cho phép người dùng đổi tên hiển thị, email và số điện thoại. Entity `User` có thể còn chứa `id`, `role`, `enabled`, `ownerId`, `createdAt`, trạng thái xác minh và các quan hệ nghiệp vụ. Nếu bind request trực tiếp vào entity, một request tự tạo có thể gửi thêm các trường không xuất hiện trên giao diện. Đây là nhóm lỗi thường được gọi là *overposting* hoặc *mass assignment*: ứng dụng nhận và gán nhiều thuộc tính hơn use case cho phép.

Giải pháp là tạo một **form model riêng** (còn gọi là form DTO hoặc command object) chỉ chứa những dữ liệu mà use case cần nhận. Flow bind request vào form model; tầng nghiệp vụ kiểm tra quyền, xác thực dữ liệu và chủ động áp dụng các trường được phép lên entity.

Bài học này thuộc chương **Liên kết biểu mẫu** của module **SPRING_WEB_FLOW**. Khi mô hình hóa hành trình nhiều bước bằng state, event, transition và subflow, form model riêng giúp việc binding và validation rõ ràng, giảm rủi ro cập nhật sai dữ liệu và giúp kiểm thử từng bước của flow dễ dàng hơn.

## 2. Phân biệt entity, form model và view model

Ba loại đối tượng có mục đích khác nhau:

| Loại đối tượng | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| Entity/domain object | Đại diện dữ liệu và quy tắc nghiệp vụ được quản lý lâu dài | `User`, `Booking`, `Order` |
| Form model/command DTO | Mang dữ liệu đầu vào của một thao tác cụ thể | `EditProfileForm`, `CreateBookingForm` |
| View model | Chuẩn bị dữ liệu để hiển thị, có thể gồm dữ liệu tổng hợp hoặc chỉ đọc | `ProfileSummaryView` |

Không nên chọn entity chỉ vì nó đã có sẵn các getter và setter. Một form thường đại diện cho một hành động cụ thể, trong khi entity có vòng đời, quan hệ và thuộc tính rộng hơn hành động đó.

Ví dụ, use case “chỉnh sửa thông tin liên hệ” có thể chỉ nhận:

- Tên hiển thị.
- Địa chỉ email.
- Số điện thoại.

Nó không nên nhận vai trò, trạng thái kích hoạt, quyền quản trị, mã người sở hữu hoặc ngày tạo tài khoản. Những thuộc tính này được quản lý bởi quy trình khác hoặc do hệ thống quyết định.

Một form model tốt có ba đặc điểm:

1. Chỉ chứa trường cần cho use case hiện tại.
2. Có kiểu dữ liệu và ràng buộc validation phù hợp với đầu vào.
3. Không phơi bày cấu trúc nội bộ của entity hoặc quan hệ persistence không cần thiết.

## 3. Thiết kế form model theo use case

### 3.1. Chỉ khai báo thuộc tính được phép nhận

Ví dụ form chỉnh sửa hồ sơ:

~~~java
public class EditProfileForm {

    @NotBlank
    @Size(max = 80)
    private String displayName;

    @NotBlank
    @Email
    @Size(max = 254)
    private String email;

    @Size(max = 30)
    private String phone;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public String getPhone() {
        return phone;
    }

    public void setPhone(String phone) {
        this.phone = phone;
    }
}
~~~

Các annotation trong ví dụ minh họa ràng buộc Bean Validation. Tùy thế hệ Spring và Bean Validation đang dùng, package annotation có thể là `javax.validation` hoặc `jakarta.validation`. Hãy dùng package tương ứng với phiên bản của dự án.

Form không có các thuộc tính `id`, `role`, `enabled` hoặc `ownerId`. Vì vậy, request gửi thêm các thuộc tính này không có chỗ hợp lệ để ghi vào form model. Đây là lớp bảo vệ đầu tiên, nhưng vẫn cần giới hạn binding trong cấu hình flow và kiểm tra quyền tại service.

### 3.2. Tạo form riêng cho từng thao tác

Không nên tạo một DTO lớn dùng chung cho mọi thao tác chỉ vì nhiều form có một số trường trùng nhau.

Ví dụ:

| Use case | Form model phù hợp |
| --- | --- |
| Người dùng tự sửa thông tin liên hệ | `EditProfileForm` |
| Quản trị viên cập nhật trạng thái tài khoản | `AdminUpdateAccountForm` |
| Người dùng đăng ký tài khoản | `RegistrationForm` |
| Người dùng đổi mật khẩu | `ChangePasswordForm` |
| Tìm kiếm hồ sơ | `ProfileSearchForm` |

Form của quản trị viên có thể có trường trạng thái tài khoản nếu use case và quyền cho phép; form của người dùng thông thường không nên có trường đó. Việc tách model khiến ranh giới chức năng dễ đọc và tránh vô tình mở rộng quyền ghi khi một form được tái sử dụng ở màn hình khác.

### 3.3. Không dùng form model để mang mọi trạng thái nghiệp vụ

Form model chỉ nên mang dữ liệu đầu vào của thao tác. Các giá trị như người dùng đang đăng nhập, vai trò, quyền sở hữu, giá tiền do máy chủ tính, trạng thái thanh toán hoặc kết quả phê duyệt phải được lấy từ nguồn tin cậy phía máy chủ.

Nếu biểu mẫu cần hiển thị một giá trị chỉ đọc, có thể đưa giá trị đó vào view model hoặc model hiển thị. Không cần biến nó thành thuộc tính có thể binding ngược từ request.

## 4. Giới hạn thuộc tính được phép binding trong Spring Web Flow

Form model đã thu hẹp tập thuộc tính, nhưng flow cũng nên khai báo rõ các thuộc tính được phép nhận. Trong Spring Web Flow, view-state có thể chỉ định model và danh sách binding thông qua phần `binder`.

Ví dụ minh họa flow chỉnh sửa hồ sơ:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow">

    <on-start>
        <evaluate
            expression="profileService.loadCurrentUserProfileForm()"
            result="flowScope.profileForm"/>
    </on-start>

    <view-state id="editProfile"
                view="profile/edit"
                model="profileForm">
        <binder>
            <binding property="displayName"/>
            <binding property="email"/>
            <binding property="phone"/>
        </binder>

        <transition on="save" to="profileUpdated">
            <evaluate
                expression="profileValidator.validate(profileForm, messageContext)"/>
            <evaluate
                expression="profileService.updateCurrentUserProfile(profileForm)"/>
        </transition>
    </view-state>

    <end-state id="profileUpdated"/>
</flow>
~~~

Đây là cấu hình minh họa: tên bean, view, cách đăng ký validator và hành vi khi validation lỗi cần khớp cấu hình thực tế của ứng dụng. Các điểm chính là:

- `model="profileForm"` chỉ rõ đối tượng dùng làm model của view-state.
- `binder` liệt kê các thuộc tính mà biểu mẫu được phép binding.
- Flow giữ form model trong `flowScope` để dữ liệu vẫn có mặt khi xử lý các bước tiếp theo của cùng execution.
- Validator kiểm tra form trước khi service cập nhật dữ liệu nghiệp vụ.

Khai báo binding tường minh tạo một allowlist. Nếu form có thêm thuộc tính mới trong tương lai, thuộc tính đó không tự động trở thành trường được phép nhận nếu chưa được bổ sung vào binder. Điều này buộc thay đổi hợp đồng biểu mẫu phải được xem xét có chủ đích.

Nếu form chỉ tồn tại trong một view-state, có thể chọn vòng đời hẹp hơn tùy cách tổ chức flow. Nếu dữ liệu cần đi qua nhiều view-state hoặc subflow, hãy chọn scope và cách truyền dữ liệu phù hợp; không mặc định mọi form đều cần conversation scope.

## 5. Validation ở form model và quy tắc nghiệp vụ

Validation nên diễn ra ở nhiều lớp vì mỗi lớp giải quyết một loại vấn đề.

### 5.1. Kiểm tra cấu trúc và định dạng

Bean Validation phù hợp với các ràng buộc trên từng trường:

- Trường bắt buộc không được rỗng.
- Email phải có định dạng hợp lệ.
- Chuỗi không vượt quá độ dài cho phép.
- Số lượng hoặc ngày tháng nằm trong phạm vi hợp lệ.

Ví dụ, `@NotBlank`, `@Email` và `@Size` giúp mô tả hợp đồng đầu vào ngay trong form model.

### 5.2. Kiểm tra nhiều trường và ngữ cảnh

Một số quy tắc cần so sánh nhiều thuộc tính hoặc tra cứu dữ liệu:

- Ngày kết thúc phải sau ngày bắt đầu.
- Email mới chưa được tài khoản khác sử dụng.
- Mã khuyến mại còn hiệu lực tại thời điểm gửi.
- Địa chỉ giao hàng phải thuộc vùng phục vụ.

Các quy tắc này có thể nằm trong validator chuyên biệt hoặc service nghiệp vụ tùy bản chất. Validator có thể đưa lỗi vào `MessageContext` để view-state hiển thị thông báo cho người dùng. Cần giữ người dùng ở bước biểu mẫu khi dữ liệu không hợp lệ, thay vì chuyển sang bước xác nhận.

### 5.3. Kiểm tra bất biến và quyền tại service/domain

Validation trên form không thay thế kiểm tra nghiệp vụ. Service vẫn phải kiểm tra trạng thái hiện tại, quyền thao tác, giới hạn nghiệp vụ và các điều kiện có thể thay đổi giữa lúc hiển thị form và lúc người dùng gửi lại.

Ví dụ, email có thể còn trống khi trang được tải nhưng đã được tài khoản khác đăng ký trước khi người dùng bấm lưu. Service cần kiểm tra lại trong giao dịch cập nhật. Tương tự, việc form không có trường `role` không thay thế authorization: service vẫn phải bảo đảm chỉ use case được cấp quyền mới thay đổi vai trò.

## 6. Ánh xạ form model sang entity một cách tường minh

Sau khi form hợp lệ, service nên tải entity từ kho dữ liệu bằng danh tính hoặc khóa đáng tin cậy, kiểm tra quyền và chỉ áp dụng những trường use case cho phép.

Ví dụ:

~~~java
@Service
public class ProfileService {

    private final UserRepository userRepository;
    private final CurrentUserProvider currentUserProvider;

    public ProfileService(
            UserRepository userRepository,
            CurrentUserProvider currentUserProvider) {
        this.userRepository = userRepository;
        this.currentUserProvider = currentUserProvider;
    }

    @Transactional
    public void updateCurrentUserProfile(EditProfileForm form) {
        String userId = currentUserProvider.requireUserId();

        User user = userRepository.findById(userId)
            .orElseThrow(UserNotFoundException::new);

        user.updateContactDetails(
            form.getDisplayName(),
            form.getEmail(),
            form.getPhone()
        );

        userRepository.save(user);
    }
}
~~~

Ví dụ trên cho thấy service lấy ID từ ngữ cảnh xác thực phía máy chủ, tải entity hiện tại và gọi phương thức nghiệp vụ với đúng ba trường được phép. Nó không lấy `userId` hoặc `role` từ request rồi gán trực tiếp vào entity.

Nếu use case cho phép một người chỉnh sửa tài nguyên của người khác, service cần nhận định danh tài nguyên từ nguồn phù hợp của flow và kiểm tra authorization rõ ràng trước khi thay đổi. Một ID nằm trong hidden input, form model hoặc flow scope không tự chứng minh người gửi request có quyền thao tác.

Tránh các cách ánh xạ rộng như:

~~~java
BeanUtils.copyProperties(form, user);
~~~

hoặc bind toàn bộ request vào entity rồi cố gắng loại bỏ một vài trường nguy hiểm sau đó. Những cách này dễ khiến thuộc tính mới được thêm vào form/entity vô tình trở thành trường có thể ghi. Việc gán từng trường được phép làm rõ hợp đồng cập nhật và dễ review hơn.

## 7. Dữ liệu nhạy cảm, trường ẩn và quan hệ entity

### 7.1. Hidden input vẫn là dữ liệu do client gửi

Trường ẩn trong HTML không phải dữ liệu tin cậy. Người dùng có thể sửa request bằng công cụ trình duyệt hoặc gửi request thủ công. Không dùng hidden input để xác định quyền, vai trò, giá tiền cuối cùng, trạng thái đã phê duyệt hoặc chủ sở hữu tài nguyên.

Nếu cần gửi một ID để điều hướng, máy chủ vẫn phải tải đối tượng tương ứng và kiểm tra quyền trước khi sử dụng. Với dữ liệu nhạy cảm, chỉ giữ tham chiếu tối thiểu trong flow state và truy xuất lại từ nguồn tin cậy khi cần.

### 7.2. Không bind trực tiếp collection và quan hệ persistence rộng

Entity có thể chứa collection các đối tượng liên quan, ví dụ danh sách quyền, địa chỉ, hóa đơn hoặc dòng đơn hàng. Binding trực tiếp những collection này có thể mở rộng bề mặt cập nhật: request có thể thêm, xóa hoặc thay đổi quan hệ ngoài ý định của form.

Nếu use case cần chỉnh sửa một danh sách con, hãy tạo form con có trường cụ thể và giới hạn phần tử/thuộc tính được phép. Service phải xác minh từng phần tử thuộc aggregate hoặc tài nguyên mà người dùng được phép sửa. Không nhận nguyên một entity lồng nhau từ trình duyệt rồi gắn vào persistence context.

### 7.3. Không đưa bí mật vào form model

Mật khẩu hiện tại, token truy cập, khóa tích hợp và dữ liệu thanh toán nhạy cảm cần quy trình chuyên biệt. Nếu form cần nhận mật khẩu mới, hãy dùng form riêng cho thao tác đổi mật khẩu, không đưa mật khẩu vào form chỉnh sửa hồ sơ tổng quát. Không ghi giá trị bí mật vào log hoặc thông báo validation.

## 8. Chọn vòng đời form model trong flow

Form model cần tồn tại đủ lâu để phục vụ bước hiện tại và các bước liên quan, nhưng không rộng hơn cần thiết.

| Tình huống | Cách tổ chức thường phù hợp |
| --- | --- |
| Form một màn hình, submit xong kết thúc | Model gắn với view-state hoặc scope ngắn phù hợp |
| Form được sửa, xem lại và xác nhận qua nhiều state | Đặt form/command cần thiết trong `flowScope` |
| Flow cha và subflow cùng cần một phần dữ liệu | Truyền input/output tường minh; dùng `conversationScope` khi thực sự cần chia sẻ |
| Dữ liệu đã lưu và cần tồn tại sau flow | Tải/lưu qua service và repository |
| Dữ liệu chỉ để hiển thị | View model hoặc dữ liệu render, không cần binding ngược |

Không nên lưu nguyên entity có quan hệ lớn vào flow state nếu chỉ cần vài trường biểu mẫu. Form DTO gọn nhẹ giúp giảm dữ liệu cần giữ trong execution, tránh vấn đề tuần tự hóa và làm rõ những gì cần được cập nhật.

Nếu flow cần giữ form qua nhiều request, phải xem xét hành vi repository của flow execution và vòng đời session theo cấu hình ứng dụng. Khi flow hết hạn, không khôi phục dữ liệu nhạy cảm chỉ từ payload do trình duyệt gửi lại; hãy kiểm tra lại quyền và tải dữ liệu cần thiết từ server.

## 9. Lỗi thường gặp khi bind trực tiếp entity

| Triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Người dùng thường có thể gửi thêm trường `role` | Entity có setter và binder nhận trường ngoài use case | Dùng form DTO không có `role` và binder allowlist |
| Giá trị `ownerId` bị thay đổi qua request | Tin ID do client gửi | Lấy danh tính từ security context hoặc kiểm tra quyền sở hữu tại service |
| Một form sửa được nhiều thuộc tính không liên quan | Dùng chung entity hoặc DTO quá rộng | Tạo form riêng theo use case |
| Thay đổi form làm cập nhật cả quan hệ entity | Binding collection/association trực tiếp | Dùng form con hẹp và ánh xạ tường minh |
| Validation trên giao diện đã qua nhưng lưu vẫn sai | Chỉ kiểm tra phía client hoặc validator chưa kiểm tra quy tắc nghiệp vụ | Kiểm tra lại ở server/service trong giao dịch |
| Trường mới của entity bất ngờ được nhận | Binding mặc định quá rộng hoặc sao chép thuộc tính hàng loạt | Dùng allowlist và gán từng trường được phép |
| Người dùng sửa hidden input để đổi tài nguyên | Xem trường ẩn là tin cậy | Tải tài nguyên từ server và authorization trước thao tác |

## 10. Kiểm thử form model và ranh giới cập nhật

Một bộ kiểm thử tốt cần chứng minh form nhận đúng dữ liệu, từ chối dữ liệu không hợp lệ và không cho phép request sửa thuộc tính ngoài use case.

### 10.1. Kiểm thử binding

- Gửi các trường được cho phép và xác nhận chúng được binding vào form model.
- Gửi thêm `role`, `enabled`, `ownerId` hoặc thuộc tính không khai báo và xác nhận chúng không làm thay đổi dữ liệu nghiệp vụ.
- Gửi giá trị sai định dạng, quá dài hoặc thiếu trường bắt buộc và xác nhận lỗi được đưa về view phù hợp.
- Kiểm tra binder chỉ liệt kê các thuộc tính dự kiến.

### 10.2. Kiểm thử validation

- Kiểm tra từng ràng buộc trường.
- Kiểm tra quy tắc liên trường và quy tắc phụ thuộc dữ liệu hiện tại.
- Gửi form không hợp lệ và xác nhận flow ở lại màn hình để người dùng sửa.
- Kiểm tra lỗi nghiệp vụ phát sinh giữa thời điểm render và submit vẫn được service phát hiện.

### 10.3. Kiểm thử service và authorization

- Xác nhận service chỉ thay đổi các trường mà use case cho phép.
- Xác nhận ID người dùng được lấy từ ngữ cảnh xác thực hoặc được kiểm tra quyền sở hữu.
- Xác nhận người dùng A không thể dùng ID hoặc hidden input để sửa tài nguyên của người dùng B.
- Xác nhận trường ngoài form như vai trò, trạng thái tài khoản và ngày tạo không bị thay đổi.
- Xác nhận giao dịch không lưu thay đổi một phần khi quy tắc nghiệp vụ thất bại.

### 10.4. Kiểm thử tích hợp flow

Khởi chạy flow, render view, gửi event save với dữ liệu hợp lệ và không hợp lệ. Kiểm tra state đích, thông báo, dữ liệu trong scope và kết quả persistence. Khi có nhiều flow execution, xác nhận form model của một execution không bị trộn với execution khác.

## 11. Quy trình thiết kế một form an toàn

Khi thêm một biểu mẫu mới vào Spring Web Flow, hãy làm theo trình tự:

1. **Mô tả use case.** Người dùng đang thực hiện thao tác gì và cần thay đổi những dữ liệu nào?
2. **Tạo form model riêng.** Chỉ khai báo các trường đầu vào cần thiết cho thao tác đó.
3. **Định nghĩa binding allowlist.** Liệt kê rõ các thuộc tính được phép nhận trong binder của view-state.
4. **Thiết lập validation.** Kiểm tra định dạng, ràng buộc liên trường và điều kiện nghiệp vụ.
5. **Xác định nguồn danh tính và tài nguyên.** Không lấy quyền hoặc chủ sở hữu từ các trường form không đáng tin cậy.
6. **Ánh xạ tường minh.** Tải entity trong service, kiểm tra quyền và chỉ cập nhật các trường được phép.
7. **Kiểm thử overposting.** Gửi thêm thuộc tính ngoài form để chứng minh chúng không thể thay đổi entity.
8. **Kiểm thử vòng đời flow.** Xác nhận form model tồn tại đúng scope và được xử lý đúng khi flow hoàn tất hoặc hết hạn.

Với ví dụ hồ sơ người dùng, flow nhận `EditProfileForm` gồm tên hiển thị, email và số điện thoại; binder chỉ cho phép ba trường này; validator kiểm tra dữ liệu; service lấy người dùng hiện tại từ ngữ cảnh xác thực và cập nhật đúng ba thuộc tính nghiệp vụ. Entity `User` vẫn giữ quyền sở hữu, vai trò và trạng thái tài khoản dưới sự kiểm soát của tầng nghiệp vụ.

## 12. Tự kiểm tra

- Vì sao không nên bind trực tiếp entity vào form? Vì entity thường có nhiều thuộc tính và quan hệ ngoài phạm vi use case; request có thể gửi thêm trường ngoài giao diện.
- Form model nên chứa gì? Chỉ các trường đầu vào mà thao tác hiện tại cần.
- Binder allowlist có tác dụng gì? Giới hạn thuộc tính của model được phép nhận từ biểu mẫu.
- Form DTO có thay thế authorization không? Không. Service vẫn kiểm tra danh tính, quyền và quyền sở hữu.
- Hidden input có đáng tin không? Không. Giá trị đó vẫn do client gửi.
- Sau khi validation thành công, có nên sao chép mọi thuộc tính form vào entity không? Không. Chỉ ánh xạ các trường được use case cho phép.
- Dữ liệu cần tồn tại qua nhiều state nên được quản lý thế nào? Chọn scope phù hợp, thường là `flowScope`, và không giữ toàn bộ entity nếu chỉ cần form model nhỏ.
- Đơn hàng hoặc hồ sơ đã cập nhật có nên chỉ tồn tại trong flow state không? Không. Dữ liệu nghiệp vụ lâu dài cần được lưu qua repository hoặc dịch vụ dữ liệu.

Dùng form model riêng giúp hợp đồng giữa trình duyệt và flow nhỏ, rõ ràng và dễ kiểm soát. Kết hợp binder allowlist, validation phía server, authorization và ánh xạ entity tường minh sẽ giảm nguy cơ overposting, đồng thời giúp các hành trình Spring Web Flow dễ kiểm thử và bảo trì.

