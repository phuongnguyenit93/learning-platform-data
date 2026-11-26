# Kiểm thử hợp đồng ánh xạ độc lập với giao diện

Trong chương **Ánh xạ dữ liệu**, form của người dùng gửi các tham số HTTP để Spring Web Flow bind vào model của flow. Với **SPRING_WEB_FLOW**, hợp đồng ánh xạ xác định tên thuộc tính được nhận, kiểu dữ liệu đích, quy tắc chuyển đổi, validation và event được phép tiếp tục hành trình. Kiểm thử hợp đồng này giúp phát hiện lỗi khi model hoặc flow definition thay đổi, ngay cả khi chưa dựng JSP, HTML hay chạy trình duyệt.

Ta sẽ dùng một màn hình chỉnh sửa hồ sơ để kiểm tra rằng dữ liệu hợp lệ được bind đúng, dữ liệu sai bị chặn, và trường nhạy cảm không nằm trong danh sách cho phép sẽ không bị ghi đè từ request.

## 1. Hợp đồng ánh xạ gồm những gì?

Hãy xem ánh xạ dữ liệu là một giao kèo giữa request và model. Giao kèo này có ít nhất năm phần:

1. **Tên tham số:** request gửi `displayName` thì flow bind vào thuộc tính `displayName`.
2. **Danh sách thuộc tính được phép:** binder xác định những property nào được phép nhận từ request.
3. **Kiểu dữ liệu và chuyển đổi:** ví dụ chuỗi `"32"` được chuyển thành `Integer`; chuỗi không chuyển đổi được phải tạo binding error.
4. **Quy tắc validation:** giá trị chuyển đổi thành công vẫn phải thỏa mãn quy tắc nghiệp vụ, chẳng hạn tuổi phải nằm trong khoảng cho phép.
5. **Kết quả flow:** chỉ khi binding và validation đạt yêu cầu, event `save` mới được phép đưa flow sang state tiếp theo.

Các phần này không phụ thuộc vào cách trình bày giao diện. JSP, Thymeleaf hoặc một client khác đều có thể gửi cùng tên tham số và event. Vì vậy, ta có thể kiểm thử hợp đồng bằng request giả lập và flow execution mà không cần render view.

## 2. Khai báo binder như một danh sách cho phép

Giả sử model `ProfileForm` có ba thuộc tính `displayName`, `age` và `role`. Trong màn hình chỉnh sửa, người dùng chỉ được thay đổi tên hiển thị và tuổi. `role` là thuộc tính nhạy cảm do hệ thống quản lý, không được nhận từ form.

Flow definition khai báo rõ hai thuộc tính được bind:

```xml
<var name="profile" class="com.example.profile.ProfileForm" />

<view-state id="editProfile" model="profile">
    <binder>
        <binding property="displayName" />
        <binding property="age" />
    </binder>

    <transition on="save" to="review">
        <evaluate expression="profileProbe.capture(profile)" />
    </transition>
</view-state>

<view-state id="review" />
```

Khi có `<binder>`, các phần tử `<binding>` liệt kê property được phép nhận dữ liệu. Request có thể chứa thêm tham số `role`, nhưng tham số đó không thuộc hợp đồng ánh xạ của view state này. Không nên dựa vào việc giao diện ẩn trường để bảo vệ dữ liệu; client có thể tự tạo request với bất kỳ tham số nào.

Đoạn `profileProbe.capture(profile)` là điểm quan sát được đăng ký trong môi trường kiểm thử. Nó chạy sau khi binding và validation cho phép transition `save` tiếp tục, giúp test kiểm tra model mà không cần đọc nội dung của view.

## 3. Model và validation cần kiểm thử

Model cần có getter/setter JavaBean cho property được bind. Ví dụ:

```java
package com.example.profile;

import org.springframework.binding.message.MessageBuilder;
import org.springframework.binding.validation.ValidationContext;

public class ProfileForm {
    private String displayName;
    private Integer age;
    private String role = "USER";

    public void validateEditProfile(ValidationContext context) {
        if (displayName == null || displayName.trim().isEmpty()) {
            context.getMessageContext().addMessage(new MessageBuilder()
                    .error()
                    .source("displayName")
                    .defaultText("Tên hiển thị không được để trống.")
                    .build());
        }

        if (age == null || age < 1 || age > 120) {
            context.getMessageContext().addMessage(new MessageBuilder()
                    .error()
                    .source("age")
                    .defaultText("Tuổi phải nằm trong khoảng từ 1 đến 120.")
                    .build());
        }
    }

    public String getDisplayName() { return displayName; }
    public void setDisplayName(String displayName) { this.displayName = displayName; }
    public Integer getAge() { return age; }
    public void setAge(Integer age) { this.age = age; }
    public String getRole() { return role; }
    public void setRole(String role) { this.role = role; }
}
```

Web Flow tìm phương thức validation theo quy ước `validate` cộng với tên state viết theo PascalCase. Với state `editProfile`, phương thức là `validateEditProfile`. `source` của message phải khớp tên property để view có thể hiển thị lỗi đúng trường.

Có hai trường hợp lỗi cần phân biệt:

- **Binding/conversion error:** `age` có kiểu `Integer`, nhưng request gửi `age=thirty`. Giá trị không chuyển đổi được, nên binding thất bại.
- **Validation error:** request gửi `age=0`. Chuỗi chuyển đổi được thành số nguyên, nhưng giá trị vi phạm quy tắc nghiệp vụ.

Trong cả hai trường hợp, transition `save` không được thực hiện và flow ở lại `editProfile`. Kiểm thử nên xác nhận cả nguyên nhân lẫn kết quả này, thay vì chỉ kiểm tra rằng một thông báo lỗi xuất hiện.

## 4. Kiểm thử flow mà không cần giao diện

Spring Web Flow cung cấp test support với `AbstractXmlFlowExecutionTests` và `MockExternalContext`. Test tạo flow execution, gửi event cùng request parameters giả lập, rồi kiểm tra state và kết quả của model. Không cần JSP, trình duyệt hoặc thao tác click.

Ví dụ dưới đây giả định flow XML nằm ở `src/test/resources/flows/profile/profile-flow.xml` và project đã thêm module test support cùng phiên bản Spring Web Flow vào test classpath:

```java
import org.springframework.webflow.engine.builder.FlowBuilderContext;
import org.springframework.webflow.execution.FlowExecution;
import org.springframework.webflow.test.MockExternalContext;
import org.springframework.webflow.test.execution.AbstractXmlFlowExecutionTests;
import org.springframework.webflow.test.execution.FlowDefinitionResource;
import org.springframework.webflow.test.execution.FlowDefinitionResourceFactory;

public class ProfileFlowContractTests extends AbstractXmlFlowExecutionTests {

    private final ProfileProbe profileProbe = new ProfileProbe();

    @Override
    protected FlowDefinitionResource getResource(
            FlowDefinitionResourceFactory resourceFactory) {
        return resourceFactory.createFileResource(
                "src/test/resources/flows/profile/profile-flow.xml");
    }

    @Override
    protected void configureFlowBuilderContext(FlowBuilderContext builderContext) {
        builderContext.registerBean("profileProbe", profileProbe);
    }

    public void testAllowedPropertiesAreBoundAndRoleIsIgnored() {
        FlowExecution execution = getFlowExecution();
        execution.start(new MockExternalContext());

        MockExternalContext request = new MockExternalContext();
        request.setEventId("save");
        request.putRequestParameter("displayName", "Nguyen An");
        request.putRequestParameter("age", "32");
        request.putRequestParameter("role", "ADMIN");
        execution.resume(request);

        assertCurrentStateEquals("review", execution);
        assertEquals("Nguyen An", profileProbe.getDisplayName());
        assertEquals(Integer.valueOf(32), profileProbe.getAge());
        assertEquals("USER", profileProbe.getRole());
    }

    public void testConversionErrorKeepsFlowOnEditState() {
        FlowExecution execution = getFlowExecution();
        execution.start(new MockExternalContext());

        MockExternalContext request = new MockExternalContext();
        request.setEventId("save");
        request.putRequestParameter("displayName", "Nguyen An");
        request.putRequestParameter("age", "thirty");
        execution.resume(request);

        assertCurrentStateEquals("editProfile", execution);
        assertNull(profileProbe.getDisplayName());
    }

    public void testValidationErrorKeepsFlowOnEditState() {
        FlowExecution execution = getFlowExecution();
        execution.start(new MockExternalContext());

        MockExternalContext request = new MockExternalContext();
        request.setEventId("save");
        request.putRequestParameter("displayName", "Nguyen An");
        request.putRequestParameter("age", "0");
        execution.resume(request);

        assertCurrentStateEquals("editProfile", execution);
        assertNull(profileProbe.getDisplayName());
    }
}
```

Probe chỉ là bean quan sát dùng trong test:

```java
public class ProfileProbe {
    private String displayName;
    private Integer age;
    private String role;

    public void capture(ProfileForm profile) {
        displayName = profile.getDisplayName();
        age = profile.getAge();
        role = profile.getRole();
    }

    public String getDisplayName() { return displayName; }
    public Integer getAge() { return age; }
    public String getRole() { return role; }
}
```

Trong test đầu tiên, request cố ý gửi thêm `role=ADMIN`. Sau khi flow chuyển sang `review`, probe vẫn nhận `role=USER`, chứng minh property không nằm trong binder không bị ghi đè. Hai test còn lại xác nhận dữ liệu sai không vượt qua được state chỉnh sửa. Nếu dùng JUnit mới hơn hoặc phiên bản Web Flow có API test khác, giữ nguyên các trường hợp kiểm thử và điều chỉnh lớp nền/helper theo phiên bản đang dùng.

## 5. Ma trận kiểm thử hợp đồng

Nên tổ chức test theo các trường hợp đầu vào và kết quả mong đợi:

| Trường hợp | Request mẫu | Kết quả mong đợi |
|---|---|---|
| Dữ liệu hợp lệ | `displayName=An`, `age=32`, event `save` | Model nhận đúng giá trị; flow sang `review`. |
| Sai kiểu dữ liệu | `age=thirty` | Binding error; flow ở lại `editProfile`. |
| Sai quy tắc nghiệp vụ | `age=0` | Validation error; flow ở lại `editProfile`. |
| Thiếu property bắt buộc | Không gửi `displayName` | Validation báo lỗi; không sang `review`. |
| Gửi property ngoài allowlist | `role=ADMIN` | `role` giữ nguyên giá trị do hệ thống đặt. |
| Gửi event không được khai báo | Event khác `save` | Flow không thực hiện transition `save`; kiểm tra lỗi event theo cấu hình flow. |

Với các property có định dạng đặc biệt như ngày, tiền tệ hoặc mã định danh, bổ sung trường hợp kiểm thử cho converter tương ứng. Ví dụ, nếu hợp đồng nhận ngày theo ISO `yyyy-MM-dd`, hãy kiểm tra một ngày hợp lệ, chuỗi sai định dạng và giá trị ngày không hợp lệ theo nghiệp vụ. Đừng chỉ kiểm thử converter riêng; ít nhất một flow execution test cần xác nhận converter thực sự được dùng trong cấu hình binding của state.

## 6. Kiểm thử input/output và kiểu dữ liệu phức hợp

Hợp đồng ánh xạ không chỉ dành cho các chuỗi đơn giản. Model có thể chứa thuộc tính lồng nhau hoặc collection. Ví dụ, form địa chỉ có thể gửi `address.city` và `address.postalCode`. Khi đó:

- Property path phải khớp cấu trúc object và có getter/setter phù hợp.
- Binder chỉ nên cho phép các nhánh thực sự cần cập nhật.
- Kiểm thử cả trường hợp object con đã tồn tại và trường hợp object con chưa được khởi tạo, theo cách model của ứng dụng tạo object.
- Với collection, kiểm tra giới hạn số phần tử và cách xử lý index thiếu hoặc không liên tục.

Nếu flow nhận dữ liệu từ subflow, hãy kiểm thử riêng mapping input và output: flow cha truyền đúng giá trị đầu vào; subflow trả đúng outcome; output chỉ cập nhật thuộc tính mà flow cha cho phép. Điều này giữ hợp đồng giữa các flow rõ ràng, không phụ thuộc vào giao diện của từng flow.

Không nên bind trực tiếp các thuộc tính nhạy cảm như `role`, `accountStatus`, `ownerId` hoặc `approved`. Hãy đặt các giá trị đó từ service hoặc từ ngữ cảnh đã xác thực ở phía máy chủ. Binder là một lớp giới hạn đầu vào hữu ích, nhưng không thay thế việc kiểm tra quyền ở tầng nghiệp vụ.

## 7. Phân tách test hợp đồng và test giao diện

Hai nhóm test trả lời hai câu hỏi khác nhau:

| Test hợp đồng ánh xạ | Test giao diện |
|---|---|
| Request parameter nào được nhận? | Form có hiển thị đúng label và input không? |
| Property nào được phép thay đổi? | Nút submit có gửi đúng event không? |
| Chuỗi được chuyển thành kiểu Java nào? | Lỗi có xuất hiện đúng vị trí và dễ hiểu không? |
| Validation có chặn transition không? | Người dùng có thể sửa và gửi lại form thuận tiện không? |
| Flow có đi đến state đúng không? | Bố cục, accessibility và hành vi responsive có đúng không? |

Test hợp đồng nên chạy nhanh, ổn định và không phụ thuộc browser driver, CSS hoặc template engine. Test giao diện vẫn cần thiết để xác nhận form thực tế dùng đúng tên tham số và event. Hai lớp test bổ sung cho nhau: test hợp đồng bảo vệ logic ánh xạ, test giao diện bảo vệ trải nghiệm người dùng.

## 8. Khi hợp đồng thay đổi

Đổi tên property, kiểu dữ liệu hoặc danh sách binder có thể ảnh hưởng đến mọi client gửi request cho flow. Trước khi thay đổi:

1. Xác định tên tham số hiện tại và các client đang sử dụng nó.
2. Cập nhật binder, model, converter và validation đồng bộ.
3. Chạy test hợp đồng cho dữ liệu hợp lệ, dữ liệu sai và property ngoài allowlist.
4. Cập nhật form hoặc client để gửi đúng tên tham số mới.
5. Nếu cần tương thích ngược, hỗ trợ ánh xạ cũ trong một khoảng chuyển đổi có kiểm soát rồi mới loại bỏ.

Không đổi tên property chỉ vì muốn đổi label hiển thị. Label là nội dung giao diện; tên property là một phần hợp đồng dữ liệu. Giữ hai khái niệm tách biệt giúp thay đổi giao diện ít ảnh hưởng đến flow.

## 9. Thực hành

Tạo flow chỉnh sửa hồ sơ có ba property `displayName`, `age` và `role`, trong đó chỉ hai property đầu được phép bind từ request.

1. Khai báo `ProfileForm` và state `editProfile` với binder chỉ chứa `displayName` và `age`.
2. Viết `validateEditProfile` để kiểm tra tên không rỗng và tuổi từ 1 đến 120.
3. Thêm transition `save` sang `review` và một probe test để quan sát model sau binding.
4. Viết test gửi dữ liệu hợp lệ và xác nhận flow sang `review` với giá trị Java đúng kiểu.
5. Gửi `age=thirty` và `age=0` trong hai test riêng; xác nhận cả hai đều ở lại `editProfile`.
6. Gửi thêm `role=ADMIN`; xác nhận giá trị `role` vẫn là `USER`.
7. Đổi tên một property trong model nhưng không đổi binder, quan sát test hợp đồng thất bại, sau đó cập nhật đồng bộ binder và client.

Bạn hoàn thành bài khi có thể chứng minh hợp đồng ánh xạ bằng request giả lập, phân biệt binding error với validation error, kiểm tra allowlist property và xác nhận state chuyển đúng mà không cần dựng giao diện.
