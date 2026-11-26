# currentEvent, currentUser và thông tin người dùng

> **Chương:** Biểu thức  
> **Module:** SPRING_WEB_FLOW

Trong module **SPRING_WEB_FLOW**, bạn học cách mô hình hóa hành trình web nhiều bước bằng state, event, transition và subflow; tổ chức form binding, validation, scope và phiên; tích hợp Spring Web Flow với Spring MVC; đồng thời kiểm thử và phục hồi luồng khi có lỗi. Trong chương **Biểu thức**, các giá trị ngữ cảnh giúp flow đọc trạng thái hiện tại và phối hợp với dữ liệu ứng dụng. Hai khái niệm cần phân biệt rõ là **currentEvent**, tức event đang được flow xử lý, và **currentUser**, tức người dùng đã được ứng dụng xác thực hoặc một thông tin người dùng do ứng dụng cung cấp.

Bài học này giải thích cách đọc event hiện tại, cách đưa danh tính người dùng vào biểu thức Spring Web Flow, cách lấy thông tin hồ sơ cần thiết và cách sử dụng dữ liệu đó an toàn trong điều hướng. Trọng tâm là biết dữ liệu đến từ đâu, có đáng tin cậy đến mức nào và nên được giữ trong scope nào.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích currentEvent là event của flow, không phải danh tính người dùng hay một tham số form.
- Đọc id của event hiện tại trong Java hoặc trong biểu thức flow khi ngữ cảnh hỗ trợ.
- Phân biệt currentUser với dữ liệu người dùng do trình duyệt gửi lên.
- Expose người dùng hiện tại qua một bean hoặc biến biểu thức có kiểm soát.
- Lấy thông tin hồ sơ từ service theo danh tính đã xác thực.
- Chọn dữ liệu phù hợp để đưa vào flow scope hoặc view scope.
- Kiểm tra quyền ở phía máy chủ và viết test cho người dùng đã đăng nhập, người dùng ẩn danh và người dùng không có quyền.

## 1. Hai loại ngữ cảnh khác nhau

Một flow xử lý các event để chuyển từ state này sang state khác. Đồng thời, ứng dụng có thể cần biết ai đang thực hiện hành trình đó. Đây là hai nguồn thông tin riêng:

| Giá trị | Trả lời câu hỏi | Nguồn điển hình |
|---|---|---|
| **currentEvent** | Flow vừa nhận event nào? | Event trong lần thực thi flow hiện tại. |
| **currentUser** | Ai đang được xác thực trong request hiện tại? | Security context hoặc dịch vụ nhận diện người dùng của ứng dụng. |
| **user profile** | Hồ sơ nghiệp vụ của người đó gồm những gì? | User service hoặc kho dữ liệu nghiệp vụ. |

Ví dụ, người dùng đang ở state **review** và bấm nút xác nhận. Flow nhận event **confirm**; đó là currentEvent. Request cũng được thực hiện bởi tài khoản đã đăng nhập có mã người dùng **U-204**; đó là danh tính currentUser. Dịch vụ người dùng có thể tra cứu hồ sơ để biết tên hiển thị, trạng thái tài khoản hoặc tổ chức của người đó.

Không dùng event id để suy ra danh tính. Cũng không dùng một user id gửi từ form để thay thế danh tính đã xác thực. Event mô tả ý định điều khiển flow; danh tính đến từ cơ chế xác thực của ứng dụng.

## 2. Đọc currentEvent

**Event** là tín hiệu mà flow nhận để thực hiện transition hoặc xử lý trong state hiện tại. Event có một id, ví dụ **next**, **back**, **confirm**, **cancel** hoặc một tên do ứng dụng quy ước.

Trong Java, action nhận **RequestContext** và có thể đọc event hiện tại qua API ngữ cảnh:

~~~java
import org.springframework.webflow.execution.Event;
import org.springframework.webflow.execution.RequestContext;

public Event inspectCurrentEvent(RequestContext context) {
    Event event = context.getCurrentEvent();

    if (event == null) {
        return null;
    }

    String eventId = event.getId();
    // Dùng eventId cho logic phù hợp với state hiện tại.
    return event;
}
~~~

getCurrentEvent() có thể trả về null khi action chạy ở ngữ cảnh chưa có event hiện tại. Vì vậy, hãy kiểm tra null trước khi đọc id. Không nên giả định mọi lần khởi tạo flow đều bắt đầu bằng một event do người dùng bấm nút.

Trong biểu thức của flow, **currentEvent** là biến ngữ cảnh biểu thị event hiện tại. Có thể đọc id của event trực tiếp bằng thuộc tính:

~~~xml
<transition on="confirm" to="completed">
    <evaluate expression="@auditService.record(currentEvent.id)"/>
</transition>
~~~

Ví dụ ghi lại event **confirm** trước khi flow đi đến state **completed**. Biến này phản ánh event của lần thực thi flow hiện tại; nó không phải tên nút HTML hay tham số tùy ý của request. Trong Java action, có thể đọc cùng ngữ cảnh qua **RequestContext.getCurrentEvent()**. Nếu action chạy ở thời điểm chưa có event, hãy kiểm tra null trước khi đọc id.

Một cách khác là chuyển việc đọc event vào một action Java. Cách này phù hợp khi cần kiểm tra null, ghi log có cấu trúc hoặc xử lý nhiều loại event:

~~~java
public Event doExecute(RequestContext context) throws Exception {
    Event current = context.getCurrentEvent();

    if (current == null) {
        return result("noCurrentEvent");
    }

    String eventId = current.getId();
    auditService.record(eventId);

    return success();
}
~~~

Action có thể trả về **noCurrentEvent** nếu đó là một trường hợp được flow thiết kế rõ ràng. Nếu không có transition cho kết quả này, hãy chọn cách xử lý phù hợp với hợp đồng của action thay vì phát ra một event tùy ý.

### Dùng currentEvent đúng mục đích

currentEvent hữu ích khi cần:

- Ghi lại thao tác điều hướng mà flow vừa nhận.
- Phân biệt các event trong cùng một action hoặc transition.
- Chẩn đoán vì sao flow chọn một nhánh cụ thể.
- Gọi logic nghiệp vụ theo event đã được định nghĩa trong flow.

Không dùng currentEvent để quyết định quyền truy cập. Một event **confirm** chỉ cho biết người dùng đã gửi yêu cầu xác nhận; nó không chứng minh người dùng được phép xác nhận đối tượng đang mở.

## 3. currentUser đến từ đâu?

Spring Web Flow cung cấp ngữ cảnh flow, nhưng ứng dụng vẫn phải xác định cơ chế nhận diện và xác thực người dùng. Trong ứng dụng tích hợp Spring Security, thông tin xác thực thường nằm trong **SecurityContextHolder**. Principal có thể là đối tượng **UserDetails**, một lớp principal riêng của ứng dụng hoặc kiểu principal do nhà cung cấp OpenID Connect trả về.

Không nên giả định **currentUser** là một biến có sẵn trong mọi expression context. Nếu muốn dùng tên này trong flow expression, hãy expose một bean hoặc đăng ký một biến biểu thức có hợp đồng rõ ràng. Ví dụ dưới đây dùng bean **currentUserProvider**.

Một provider đơn giản có thể đọc Authentication và chuyển principal thành một đối tượng thông tin tối thiểu:

~~~java
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;

@Component("currentUserProvider")
public class CurrentUserProvider {

    private final AuthenticationTrustResolver trustResolver =
        new AuthenticationTrustResolverImpl();

    public UserSummary getCurrentUser() {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null
                || !authentication.isAuthenticated()
                || trustResolver.isAnonymous(authentication)) {
            return null;
        }

        Object principal = authentication.getPrincipal();

        if (principal instanceof AppUserPrincipal) {
            AppUserPrincipal user = (AppUserPrincipal) principal;
            return new UserSummary(user.getId(), user.getDisplayName());
        }

        return null;
    }
}
~~~

**AppUserPrincipal** và **UserSummary** là các kiểu do ứng dụng định nghĩa. Provider cần biết principal thực tế mà cơ chế xác thực của dự án tạo ra. Nếu ứng dụng dùng một loại principal khác, hãy chuyển đổi loại đó một cách tường minh. Không ép kiểu mọi principal thành lớp User của hệ thống.

**AuthenticationTrustResolver** giúp phân biệt tài khoản ẩn danh với người dùng đã xác thực. Chỉ kiểm tra isAuthenticated() là chưa đủ trong một số cấu hình, vì authentication dành cho anonymous có thể vẫn được đánh dấu đã xác thực.

### Đưa currentUser vào biểu thức flow

Khi bean đã được đăng ký và expression context cho phép truy cập bean theo cú pháp Spring EL, có thể lấy thông tin người dùng như sau:

~~~xml
<evaluate expression="@currentUserProvider.currentUser"
          result="flowScope.currentUser"/>
~~~

Biểu thức **@currentUserProvider.currentUser** đọc thuộc tính currentUser từ bean currentUserProvider, tương ứng với getter getCurrentUser(). Kết quả được lưu vào **flowScope.currentUser** để các state tiếp theo có thể dùng.

Sau đó, biểu thức có thể truy cập một thuộc tính an toàn của đối tượng:

~~~xml
<evaluate expression="@welcomeService.prepare(flowScope.currentUser.id)"
          result="flowScope.welcomeData"/>
~~~

Chỉ dùng biểu thức này sau khi đã xác nhận người dùng tồn tại. Nếu flow cho phép khách chưa đăng nhập, cần có nhánh xử lý null hoặc một state yêu cầu đăng nhập trước khi truy cập id.

Có thể dùng dữ liệu đã lưu trong flow scope để hiển thị tên:

~~~html
<p>Xin chào, <span th:text="*{currentUser.displayName}"></span></p>
~~~

Đây chỉ là ví dụ minh họa cho view engine có cú pháp tương ứng; cách truy cập model thực tế phụ thuộc công nghệ view và cách ứng dụng đưa flow scope vào model. Hãy tránh giả định mọi view engine đều dùng cùng một cú pháp.

## 4. Lấy thông tin người dùng theo từng nhu cầu

Danh tính đã xác thực thường chỉ cung cấp mã định danh và thông tin xác thực cần thiết. Những thông tin nghiệp vụ như địa chỉ, đơn vị, trạng thái hồ sơ hoặc tùy chọn cá nhân nên được lấy qua service chuyên trách.

Ví dụ service:

~~~java
public interface UserProfileService {
    UserProfile findProfile(String userId);
}
~~~

Action hoặc bean phục vụ flow có thể kết hợp currentUserProvider với UserProfileService:

~~~java
UserSummary user = currentUserProvider.getCurrentUser();

if (user == null) {
    return result("authenticationRequired");
}

UserProfile profile = userProfileService.findProfile(user.getId());

if (profile == null) {
    return result("profileMissing");
}

context.getFlowScope().put("userProfile", profile);
return success();
~~~

Đoạn code cho thấy ba lớp thông tin có mục đích khác nhau:

- **Authentication:** bằng chứng xác thực và principal do hệ thống xác thực cung cấp.
- **UserSummary:** thông tin nhận diện tối thiểu mà flow cần để điều hướng hoặc hiển thị.
- **UserProfile:** dữ liệu nghiệp vụ được tải từ service theo user id đã xác thực.

Không cần tải toàn bộ hồ sơ người dùng ở đầu flow nếu các state sau không sử dụng đến. Lấy dữ liệu vừa đủ giúp giảm truy vấn và hạn chế thông tin cá nhân được giữ trong phiên.

### Chọn dữ liệu nào được phép đưa vào flow

| Dữ liệu | Có thể đưa vào flow scope? | Lưu ý |
|---|---|---|
| User id đã xác thực | Có, khi flow cần dùng qua nhiều state | Vẫn phải kiểm tra quyền trên từng tài nguyên. |
| Tên hiển thị | Có, nếu cần hiển thị trong hành trình | Có thể cũ nếu hồ sơ được cập nhật trong lúc flow đang chạy. |
| Vai trò hoặc quyền | Chỉ khi có nhu cầu rõ ràng | Không dùng bản sao cũ làm căn cứ phân quyền lâu dài. |
| Email, số điện thoại, địa chỉ | Chỉ khi flow thực sự cần | Hạn chế phạm vi và thời gian lưu giữ. |
| Mật khẩu, access token, refresh token | Không đưa vào flow scope để hiển thị hoặc truyền giữa các state | Để cơ chế bảo mật quản lý credential và token. |
| Toàn bộ đối tượng Authentication | Không nên | Có thể chứa thông tin bảo mật hoặc phụ thuộc implementation. |

Flow scope sống trong vòng đời flow execution. Nó không phải kho hồ sơ và cũng không thay thế session bảo mật. Nếu người dùng đăng xuất, quyền bị thu hồi hoặc tài khoản bị khóa trong khi flow vẫn tồn tại, ứng dụng cần kiểm tra lại trạng thái xác thực và quyền trước thao tác nhạy cảm.

## 5. Dùng thông tin người dùng trong điều hướng

Giả sử ứng dụng có flow xem và chỉnh sửa hồ sơ. Người dùng đã đăng nhập có thể xem hồ sơ của mình; một số người dùng có quyền quản trị có thể xem hồ sơ thuộc phạm vi được phân công.

Có thể mô hình hóa các nhánh sau:

~~~mermaid
flowchart TD
    A[Khởi chạy flow] --> B{Có currentUser?}
    B -->|Không| C[Yêu cầu đăng nhập]
    B -->|Có| D[Tải hồ sơ theo user id]
    D --> E{Có quyền truy cập?}
    E -->|Không| F[Hiển thị từ chối truy cập]
    E -->|Có| G[Hiển thị hồ sơ]
    G --> H{Người dùng chọn gì?}
    H -->|Xem| I[View profile]
    H -->|Sửa| J[Kiểm tra quyền sửa và cập nhật]
~~~

Ví dụ flow XML có thể thể hiện các kết quả từ action:

~~~xml
<action-state id="loadProfile">
    <evaluate expression="loadProfileAction"/>
    <transition on="success" to="showProfile"/>
    <transition on="authenticationRequired" to="loginRequired"/>
    <transition on="profileMissing" to="profileNotFound"/>
    <transition on="accessDenied" to="accessDenied"/>
</action-state>
~~~

Trong action loadProfileAction, ứng dụng cần:

1. Lấy danh tính đã xác thực từ provider.
2. Kiểm tra danh tính có tồn tại và tài khoản có còn hiệu lực.
3. Xác định hồ sơ hoặc tài nguyên cần truy cập.
4. Gọi service kiểm tra quyền sở hữu hoặc quyền quản trị.
5. Chỉ đưa dữ liệu được phép xem vào scope.
6. Trả về event phù hợp với kết quả.

Đừng chỉ kiểm tra một vai trò tổng quát rồi cho phép truy cập mọi hồ sơ. Quyền truy cập thường còn phụ thuộc tài nguyên cụ thể: người dùng có thể được xem hồ sơ của mình nhưng không được xem hồ sơ của người khác. Service nghiệp vụ cần kiểm tra quyền với đúng đối tượng trước khi đọc hoặc ghi dữ liệu.

## 6. currentUser không thay thế kiểm tra phân quyền

Có danh tính không có nghĩa là có quyền. Một người dùng đã đăng nhập vẫn có thể không được xem hoặc cập nhật một tài nguyên cụ thể.

Các quy tắc cần tuân thủ:

- Không tin user id, role hoặc owner id gửi từ query string hay form.
- Lấy danh tính từ SecurityContext hoặc provider đã được ứng dụng tin cậy cấu hình.
- Kiểm tra quyền ở service hoặc tầng bảo mật phía máy chủ trước khi đọc, cập nhật hay xóa tài nguyên.
- Với thao tác quan trọng, kiểm tra lại quyền tại thời điểm thực thi để tránh dùng quyền đã thay đổi.
- Dùng cơ chế bảo vệ route, method security hoặc Spring Security integration phù hợp với ứng dụng; flow expression chỉ hỗ trợ điều phối nhánh giao diện.
- Khi người dùng chưa xác thực, trả về nhánh đăng nhập hoặc kết thúc flow theo chính sách ứng dụng.

Ví dụ, biểu thức gọi service:

~~~xml
<evaluate expression="@profileService.updateForCurrentUser(
    flowScope.currentUser.id,
    flowScope.profileForm)"/>
~~~

Service updateForCurrentUser phải tự xác minh người dùng hiện tại được phép sửa hồ sơ tương ứng. Không nên chỉ dựa vào việc flow đã đi qua state editProfile để coi yêu cầu là hợp lệ. Người dùng có thể gửi request trực tiếp hoặc cố tiếp tục một flow execution cũ; mọi thao tác nhạy cảm vẫn phải được kiểm tra ở phía máy chủ.

## 7. Tránh nhầm lẫn giữa dữ liệu người dùng và dữ liệu request

Một số giá trị trông giống nhau nhưng có độ tin cậy khác nhau:

| Giá trị | Ví dụ | Cách sử dụng |
|---|---|---|
| Principal đã xác thực | AppUserPrincipal | Nguồn nhận diện người dùng theo cơ chế bảo mật. |
| currentUser trong flow | UserSummary | Bản thông tin tối thiểu do ứng dụng cung cấp cho biểu thức. |
| User id từ form | targetUserId | Đầu vào không đáng tin; phải kiểm tra quyền và quan hệ với tài nguyên. |
| User profile | UserProfile | Dữ liệu nghiệp vụ do service truy vấn. |
| currentEvent id | confirm | Tín hiệu điều khiển flow, không phải user id hay quyền. |

Ví dụ không an toàn là lấy userId từ form rồi tải hồ sơ trực tiếp:

~~~java
String userId = context.getRequestParameters().get("userId");
UserProfile profile = userProfileService.findProfile(userId);
~~~

Nếu không có kiểm tra quyền, người dùng có thể thay đổi tham số để thử đọc hồ sơ của người khác. Thay vào đó, hãy lấy danh tính đã xác thực từ provider và kiểm tra quyền với tài nguyên đích:

~~~java
UserSummary current = currentUserProvider.getCurrentUser();

if (current == null) {
    return result("authenticationRequired");
}

String requestedProfileId =
    context.getRequestParameters().get("profileId");

if (!profileService.canView(current.getId(), requestedProfileId)) {
    return result("accessDenied");
}

UserProfile profile = profileService.findById(requestedProfileId);
context.getFlowScope().put("userProfile", profile);

return success();
~~~

Ngay cả khi profileId là đầu vào hợp lệ của nghiệp vụ, nó vẫn là dữ liệu do client gửi. Việc kiểm tra quyền phải diễn ra trước khi đưa hồ sơ vào flow scope hoặc render dữ liệu ra view.

## 8. Vòng đời, scope và thay đổi phiên đăng nhập

Thông tin người dùng có thể được lấy lại ở mỗi request hoặc chụp thành một bản tóm tắt lúc flow bắt đầu. Chọn cách nào tùy theo mục đích:

- Nếu chỉ cần hiển thị tên trong một vài state, có thể lấy UserSummary và lưu vào flow scope.
- Nếu cần trạng thái tài khoản hoặc quyền hiện hành, hãy truy vấn lại qua provider/service ở thời điểm thực hiện thao tác.
- Nếu flow có thời gian sống dài, không xem dữ liệu currentUser đã lưu lúc bắt đầu là bằng chứng xác thực còn hiệu lực.
- Nếu người dùng đăng xuất, đổi tài khoản hoặc session hết hạn, flow cần xử lý lại trạng thái xác thực thay vì tiếp tục bằng dữ liệu cũ.

Không đặt thông tin xác thực hoặc đối tượng chứa credential vào view scope, flow scope hay conversation scope. Không đưa access token, refresh token, mật khẩu hoặc session id vào biểu thức hiển thị. Các dữ liệu này phải được quản lý bởi cơ chế bảo mật thích hợp.

Nếu ứng dụng cho phép một flow chạy lâu, hãy quyết định rõ hành vi khi phiên đăng nhập thay đổi: yêu cầu xác thực lại, kết thúc flow cũ hoặc tải lại thông tin người dùng. Không để một flow khởi chạy bởi tài khoản A tiếp tục thực hiện thao tác dưới tài khoản B chỉ vì dữ liệu cũ còn nằm trong scope.

## 9. Lỗi thường gặp và cách điều tra

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| currentEvent bị null | Action chạy trước khi có event hoặc ngoài ngữ cảnh transition | Kiểm tra vị trí action và xử lý null. |
| Không đọc được currentEvent | Expression đang chạy ngoài ngữ cảnh có event hoặc expression context không cung cấp biến này | Kiểm tra vị trí đánh giá và phiên bản Spring Web Flow; đọc event qua RequestContext trong action Java nếu phù hợp. |
| Biểu thức currentUser không được nhận diện | Ứng dụng chưa đăng ký biến hoặc bean tương ứng | Expose provider và dùng bean reference đúng cấu hình. |
| currentUser trả về null | Chưa đăng nhập, phiên hết hạn, anonymous hoặc provider không nhận diện principal | Kiểm tra Authentication và loại principal thực tế. |
| Lỗi ép kiểu principal | Ứng dụng dùng principal khác kiểu mà code giả định | Kiểm tra kiểu runtime và chuyển đổi tường minh. |
| Tên người dùng hiển thị cũ | Flow scope đang giữ snapshot từ trước | Tải lại hồ sơ khi cần thông tin mới. |
| Người dùng xem được hồ sơ người khác | Dùng user id từ request mà không kiểm tra quyền | Lấy danh tính từ security context và kiểm tra quyền trên tài nguyên. |
| Flow vẫn thao tác sau khi logout | Dữ liệu user cũ còn trong scope | Kiểm tra xác thực lại ở thao tác nhạy cảm và xử lý flow cũ. |
| Event đúng nhưng đi sai state | Event id không khớp transition hoặc state hiện tại khác dự kiến | Ghi log state, event id và transition được chọn. |

Khi debug, hãy ghi nhận event id, flow id và mã người dùng nội bộ ở mức tối thiểu cần thiết. Không ghi principal đầy đủ, credential, token, cookie hoặc thông tin cá nhân không cần thiết vào log. Log cần đủ để truy vết nhưng không trở thành nơi lưu trữ dữ liệu nhạy cảm.

## 10. Kiểm thử currentEvent và currentUser

Kiểm thử nên tách provider, action và flow:

### Kiểm thử provider người dùng

Bao phủ các trường hợp:

- SecurityContext chưa có Authentication.
- Authentication là anonymous.
- Principal thuộc kiểu ứng dụng hỗ trợ.
- Principal thuộc kiểu khác và provider xử lý an toàn.
- Tài khoản bị khóa hoặc không còn hợp lệ theo chính sách ứng dụng.

Xác nhận provider trả về UserSummary với các trường cần thiết và không đưa credential vào kết quả.

### Kiểm thử action đọc currentEvent

Tạo RequestContext có event phù hợp bằng test fixture của phiên bản Spring Web Flow đang dùng. Xác nhận action đọc đúng event id, xử lý được trường hợp không có event và trả về kết quả đúng. Không kiểm tra event chỉ bằng cách so sánh chuỗi được hard-code trong test mà không xác nhận nguồn event thực tế.

### Kiểm thử flow expression và transition

Dùng kiểm thử tích hợp flow để xác nhận:

- Event **confirm** được nhận ở đúng state.
- Biểu thức ghi audit đọc được id của currentEvent.
- Provider được gọi trong expression context.
- Người dùng ẩn danh đi đến nhánh yêu cầu đăng nhập.
- Người dùng đã xác thực nhưng thiếu quyền đi đến nhánh từ chối.
- Người dùng có quyền đi đến state xem hoặc sửa hồ sơ phù hợp.
- Dữ liệu hồ sơ trong scope chỉ chứa các trường cần thiết.

### Kiểm thử an toàn truy cập

Thử thay đổi user id hoặc profile id trong request. Kết quả phải vẫn tuân theo quyền của principal đã xác thực. Kiểm thử thêm tình huống đăng xuất hoặc hết hạn phiên trong khi flow còn tồn tại để bảo đảm thao tác nhạy cảm không tiếp tục bằng thông tin cũ.

## 11. Checklist khi dùng currentEvent và currentUser

- [ ] currentEvent được đọc từ đúng ngữ cảnh flow và có kiểm tra null.
- [ ] Event id được dùng cho điều phối hoặc audit, không dùng như thông tin xác thực.
- [ ] currentUser được expose qua provider hoặc expression variable có cấu hình rõ ràng.
- [ ] Provider phân biệt người dùng đã xác thực với anonymous.
- [ ] Principal được chuyển thành kiểu dữ liệu ứng dụng có kiểm soát.
- [ ] Hồ sơ người dùng được lấy qua service theo danh tính đã xác thực.
- [ ] Không tin user id hoặc role do client gửi.
- [ ] Service kiểm tra quyền trên đúng tài nguyên ở phía máy chủ.
- [ ] Flow scope chỉ giữ thông tin cần thiết và có thời hạn phù hợp.
- [ ] Logout, session timeout và thay đổi quyền được xử lý.
- [ ] Log và view không làm lộ credential hoặc dữ liệu cá nhân không cần thiết.
- [ ] Có test cho event, principal, anonymous, access denied và các nhánh transition.

## Kết luận

currentEvent cho biết flow đang xử lý tín hiệu nào; currentUser biểu đạt danh tính người dùng mà ứng dụng đã xác thực và expose cho expression context. Hãy đọc event từ RequestContext hoặc flow request context, cung cấp thông tin người dùng qua một provider rõ ràng, lấy hồ sơ qua service và kiểm tra quyền trên từng tài nguyên ở phía máy chủ. Khi tách biệt event, danh tính, hồ sơ và dữ liệu request, các biểu thức trong Spring Web Flow sẽ dễ hiểu, dễ kiểm thử và an toàn hơn.
