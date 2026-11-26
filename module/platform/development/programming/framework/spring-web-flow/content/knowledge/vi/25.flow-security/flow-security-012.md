# Xử lý thay đổi đăng nhập, đăng xuất và hết phiên giữa hành trình

> **Chương:** Bảo vệ flow  
> **Module:** SPRING_WEB_FLOW

Trong module **SPRING_WEB_FLOW**, bạn học cách mô hình hóa hành trình web nhiều bước bằng state, event, transition và subflow; tổ chức form binding, validation, scope và phiên; tích hợp Spring MVC; đồng thời kiểm thử và phục hồi luồng khi có lỗi. Một hành trình nhiều bước thường kéo dài qua nhiều request. Trong thời gian đó, người dùng có thể đăng nhập, đăng xuất, đổi tài khoản, bị khóa hoặc để phiên hết hạn. Flow cần kiểm tra lại danh tính và quyền trước các thao tác quan trọng để không tiếp tục bằng thông tin xác thực cũ.

Bài học này tập trung vào cách phối hợp vòng đời flow với Spring Security và HTTP session. Bạn sẽ phân biệt trạng thái đăng nhập với trạng thái thực thi flow, thiết kế các nhánh xử lý khi xác thực thay đổi, bảo vệ dữ liệu tạm và khôi phục công việc sau khi phiên kết thúc.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích vì sao flow còn tồn tại không có nghĩa người dùng vẫn đang đăng nhập.
- Kiểm tra Authentication hiện tại từ Spring Security ở mỗi request hoặc transition nhạy cảm.
- Phân biệt người dùng ẩn danh, người dùng đã đăng nhập, người dùng bị từ chối quyền và tài khoản không còn hợp lệ.
- Phát hiện trường hợp tài khoản hiện tại khác với người đã khởi chạy flow.
- Thiết kế hành vi phù hợp khi đăng xuất hoặc session bị vô hiệu hóa.
- Phục hồi hành trình bằng bản nháp nghiệp vụ được lưu an toàn thay vì phụ thuộc vào dữ liệu phiên đã mất.
- Kiểm thử đăng nhập, đăng xuất, đổi tài khoản, session timeout và flow execution hết hạn.

## 1. Hai vòng đời cần theo dõi riêng

Một flow nhiều bước có thể tồn tại trong một khoảng thời gian dài hơn một request HTTP. Spring Web Flow quản lý trạng thái thực thi của flow; Spring Security quản lý danh tính và quyền của request. Hai cơ chế có liên hệ nhưng không đồng nhất.

| Thành phần | Quản lý điều gì? | Có thể thay đổi khi nào? |
|---|---|---|
| **Flow execution** | State hiện tại, dữ liệu flow, lịch sử và thông tin tiếp tục flow | Khi flow nhận event, kết thúc hoặc execution hết hạn. |
| **HTTP session** | Dữ liệu gắn với phiên trình duyệt phía máy chủ | Khi hết thời gian không hoạt động, logout hoặc ứng dụng vô hiệu hóa session. |
| **SecurityContext** | Authentication được dùng để xác định người dùng của request | Khi đăng nhập, đăng xuất, xác thực lại hoặc thay đổi cơ chế lưu context. |
| **Business draft** | Dữ liệu nghiệp vụ đã được lưu bền vững để tiếp tục công việc | Theo chính sách lưu, hết hạn và xóa của ứng dụng. |

Một flow execution có thể còn được lưu trong session trong khi người dùng vừa bị đăng xuất ở một tab khác. Ngược lại, người dùng có thể vẫn đăng nhập nhưng một flow execution cụ thể đã hết hạn hoặc bị loại khỏi repository.

Do đó, không dùng việc tải được flow execution làm bằng chứng người dùng đã xác thực. Cũng không xem việc còn Authentication là bằng chứng flow cũ vẫn hợp lệ.

~~~mermaid
flowchart TD
    A[Request tiếp tục flow] --> B[Đọc Authentication hiện tại]
    B --> C{Đã xác thực?}
    C -->|Chưa| D[Yêu cầu đăng nhập hoặc kết thúc flow]
    C -->|Rồi| E{Đúng chủ sở hữu flow?}
    E -->|Không| F[Từ chối và đóng đường đi cũ]
    E -->|Có| G{Có quyền với tài nguyên?}
    G -->|Không| H[Access denied]
    G -->|Có| I[Tiếp tục xử lý state]
~~~

Các bước kiểm tra này cần được thực hiện ở phía máy chủ. Việc ẩn nút hoặc chuyển người dùng sang một view khác chỉ là hỗ trợ giao diện, không phải cơ chế bảo vệ.

## 2. Authentication hiện tại đến từ đâu?

Trong ứng dụng tích hợp Spring Security, request đã xác thực thường có Authentication trong SecurityContext. Ứng dụng có thể đọc thông tin này qua SecurityContextHolder:

~~~java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
~~~

Không nên giả định Authentication luôn là một người dùng thật. Tùy cấu hình, request ẩn danh cũng có thể có một Authentication đại diện cho anonymous user. Hãy kiểm tra null, trạng thái xác thực và loại anonymous theo cơ chế của ứng dụng.

Ví dụ provider trả về một thông tin nhận diện tối thiểu:

~~~java
@Component
public class CurrentUserProvider {

    private final AuthenticationTrustResolver trustResolver =
        new AuthenticationTrustResolverImpl();

    public AppUserPrincipal currentUser() {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null
                || !authentication.isAuthenticated()
                || trustResolver.isAnonymous(authentication)) {
            return null;
        }

        Object principal = authentication.getPrincipal();

        if (principal instanceof AppUserPrincipal) {
            return (AppUserPrincipal) principal;
        }

        return null;
    }
}
~~~

AppUserPrincipal là kiểu principal do ứng dụng định nghĩa. Nếu dự án sử dụng UserDetails hoặc một principal khác, hãy chuyển đổi đúng kiểu thực tế. Không ép kiểu mọi principal thành lớp người dùng nội bộ.

Provider nên cung cấp các trường tối thiểu cần thiết, chẳng hạn user id và tên hiển thị. Không đưa mật khẩu, access token, refresh token hoặc toàn bộ đối tượng Authentication vào flow scope để dùng lại ở các state sau.

### Kiểm tra ở thời điểm thực thi

Một số flow có thể lưu user id vào flow scope khi bắt đầu:

~~~java
context.getFlowScope().put("flowOwnerId", currentUser.getId());
~~~

Giá trị này hữu ích để ràng buộc flow với người đã khởi chạy. Nhưng đó chỉ là bản ghi chủ sở hữu lúc bắt đầu, không phải bằng chứng xác thực còn hiệu lực.

Ở mỗi transition nhạy cảm, hãy lấy lại Authentication hiện tại rồi so sánh:

~~~java
String ownerId =
    (String) context.getFlowScope().get("flowOwnerId");

AppUserPrincipal current = currentUserProvider.currentUser();

if (current == null) {
    return result("authenticationRequired");
}

if (!current.getId().equals(ownerId)) {
    return result("differentUser");
}
~~~

Cách kiểm tra này ngăn một flow được khởi chạy bởi tài khoản A tiếp tục thao tác dưới tài khoản B nếu hai tài khoản lần lượt đăng nhập trong cùng trình duyệt. Với dữ liệu quan trọng, service vẫn cần kiểm tra quyền sở hữu tài nguyên trực tiếp trước khi đọc hoặc ghi.

## 3. Xây dựng action kiểm tra danh tính và quyền

Có thể gom các kiểm tra thường dùng vào một action để flow có các event kết quả rõ ràng. Ví dụ, action kiểm tra người dùng hiện tại có được tiếp tục xem đơn đặt chỗ hay không:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.webflow.action.AbstractAction;
import org.springframework.webflow.execution.Event;
import org.springframework.webflow.execution.RequestContext;

@Component("checkFlowAccessAction")
public class CheckFlowAccessAction extends AbstractAction {

    private final CurrentUserProvider currentUserProvider;
    private final BookingAccessService bookingAccessService;

    public CheckFlowAccessAction(
            CurrentUserProvider currentUserProvider,
            BookingAccessService bookingAccessService) {
        this.currentUserProvider = currentUserProvider;
        this.bookingAccessService = bookingAccessService;
    }

    @Override
    protected Event doExecute(RequestContext context) throws Exception {
        AppUserPrincipal current = currentUserProvider.currentUser();

        if (current == null) {
            return result("authenticationRequired");
        }

        String ownerId =
            (String) context.getFlowScope().get("flowOwnerId");

        if (!current.getId().equals(ownerId)) {
            return result("differentUser");
        }

        String bookingId =
            (String) context.getFlowScope().get("bookingId");

        if (!bookingAccessService.canContinue(current.getId(), bookingId)) {
            return result("accessDenied");
        }

        return result("allowed");
    }
}
~~~

Flow dùng các event để quyết định nhánh tiếp theo:

~~~xml
<action-state id="checkFlowAccess">
    <evaluate expression="checkFlowAccessAction"/>
    <transition on="allowed" to="continueBooking"/>
    <transition on="authenticationRequired" to="loginRequired"/>
    <transition on="differentUser" to="flowOwnedByAnotherUser"/>
    <transition on="accessDenied" to="accessDenied"/>
</action-state>
~~~

Ví dụ minh họa cách tổ chức action và transition. Tên bean, kiểu principal và service phải được thay bằng thành phần của ứng dụng. Quan trọng là kiểm tra danh tính và quyền được thực hiện ở máy chủ trước khi action tiếp theo đọc hoặc cập nhật tài nguyên.

Không dựa vào một biến role hoặc user id được gửi từ form. Giá trị đó do client kiểm soát. Service phải xác định người dùng hiện tại từ ngữ cảnh bảo mật và kiểm tra quyền trên đúng booking hoặc tài nguyên cần thao tác.

## 4. Khi người dùng đăng nhập giữa hành trình

Có hai trường hợp thường gặp:

- Người dùng bắt đầu flow ở trạng thái anonymous, sau đó đăng nhập để tiếp tục.
- Người dùng mở một flow đã yêu cầu xác thực nhưng phiên đăng nhập hết hạn, rồi đăng nhập lại.

Spring Security có thể chuyển request chưa xác thực đến trang login theo cấu hình entry point. Sau khi đăng nhập thành công, success handler hoặc cơ chế saved request có thể đưa người dùng về URL trước đó. Tuy nhiên, URL đó có thể là URL tiếp tục một flow execution đã hết hạn hoặc đã mất cùng session.

Vì vậy, cần xác định rõ hành vi tiếp tục:

1. Nếu flow execution vẫn tồn tại và ứng dụng xác minh được chủ sở hữu, trạng thái nghiệp vụ và quyền, có thể tiếp tục flow.
2. Nếu execution không còn tồn tại, hãy khởi chạy flow mới từ một bản nháp đã lưu bền vững.
3. Nếu không có bản nháp hợp lệ, hướng dẫn người dùng bắt đầu lại.
4. Nếu người đăng nhập không phải chủ sở hữu của bản nháp, từ chối truy cập.

Không mặc định việc Spring Security quay lại URL đã lưu đồng nghĩa flow được khôi phục. Saved request chỉ giúp điều hướng sau xác thực; nó không bảo đảm trạng thái flow hoặc dữ liệu form vẫn còn.

### Không đặt credential vào flow để chờ đăng nhập

Không lưu mật khẩu, mã xác thực, token hoặc đối tượng Authentication vào flow scope để tiếp tục sau login. Hãy để Spring Security quản lý xác thực. Khi request mới đến, provider đọc lại SecurityContext hiện tại.

Nếu cần tiếp tục công việc, chỉ lưu một draft id ngẫu nhiên hoặc mã tham chiếu không đủ quyền truy cập độc lập. Máy chủ phải xác minh draft id gắn với user id đã xác thực, còn hiệu lực và được phép tiếp tục.

## 5. Khi người dùng đăng xuất giữa flow

Logout thường xóa SecurityContext và có thể vô hiệu hóa HTTP session. Với cấu hình Spring Security mặc định phổ biến, endpoint logout được xử lý bằng POST khi CSRF protection đang bật; cấu hình thực tế có thể tùy chỉnh URL và phương thức.

Ví dụ form đăng xuất với Thymeleaf:

~~~html
<form th:action="@{/logout}" method="post">
    <input type="hidden"
           th:name="${_csrf.parameterName}"
           th:value="${_csrf.token}"/>
    <button type="submit">Đăng xuất</button>
</form>
~~~

Nếu ứng dụng dùng cấu hình CSRF hoặc logout endpoint khác, form phải tuân theo cấu hình đó. Tránh tạo liên kết GET tùy tiện để thực hiện logout khi ứng dụng yêu cầu POST và CSRF token.

Sau logout, các request tiếp tục flow phải được coi là chưa xác thực. Không để một tab khác tiếp tục thao tác chỉ vì nó còn giữ URL execution cũ hoặc hiển thị nội dung đã cache.

Một số hành vi nên được thiết kế rõ:

- Chặn thao tác đọc hoặc ghi yêu cầu đăng nhập.
- Hiển thị thông báo phiên đã kết thúc.
- Cho phép người dùng đăng nhập lại nếu nghiệp vụ hỗ trợ.
- Xác minh lại user id sau khi đăng nhập.
- Hủy hoặc bỏ qua bản nháp nếu đã hết hạn hoặc không còn thuộc người dùng hiện tại.

Nếu logout đã vô hiệu hóa session, flow execution lưu trong session có thể không còn truy cập được. Không dựa vào flow scope để hoàn tác logout hoặc tự khôi phục Authentication.

## 6. Khi session hết hạn

HTTP session thường hết hạn sau một khoảng không hoạt động hoặc bị ứng dụng vô hiệu hóa. Container không nhất thiết thông báo cho trang đang mở ngay khi thời hạn kết thúc. Người dùng có thể vẫn nhìn thấy màn hình cũ, nhưng request tiếp theo không còn session ban đầu.

Nếu flow execution repository lưu execution trong HTTP session, việc session bị hủy có thể khiến execution đó không thể tiếp tục. Hành vi cụ thể phụ thuộc cấu hình repository, session strategy và phiên bản framework. Không nên hứa rằng người dùng sẽ tiếp tục đúng state cũ sau session timeout.

Một luồng phục hồi phù hợp:

~~~mermaid
flowchart TD
    A[Request tiếp tục flow] --> B{Session và execution còn hợp lệ?}
    B -->|Có| C[Kiểm tra Authentication và quyền]
    B -->|Không| D[Hiển thị phiên đã hết hạn]
    D --> E{Có business draft hợp lệ?}
    E -->|Không| F[Khởi chạy hành trình mới]
    E -->|Có| G[Đăng nhập lại]
    G --> H{Đúng chủ sở hữu draft?}
    H -->|Không| I[Từ chối truy cập]
    H -->|Có| J[Tải draft và khởi chạy flow mới]
    C --> K[Tiếp tục state]
~~~

Thông báo hết phiên nên giúp người dùng hiểu điều gì đã xảy ra và họ có thể làm gì tiếp theo. Nếu dữ liệu chưa lưu chỉ tồn tại trong flow scope, có thể không thể phục hồi sau khi session bị hủy. Với quy trình dài hoặc có giá trị cao, hãy cân nhắc lưu bản nháp định kỳ vào kho dữ liệu bền vững.

### Phân biệt ba loại hết hạn

| Loại hết hạn | Điều gì có thể mất? | Hướng xử lý |
|---|---|---|
| HTTP session timeout | Session và dữ liệu gắn với session; execution session-backed có thể không còn | Xác thực lại và phục hồi từ bản nháp bền vững nếu có. |
| Flow execution timeout hoặc cleanup | Một execution cụ thể không còn trong repository | Báo execution hết hạn và khởi chạy flow mới khi đủ điều kiện. |
| Business draft expiration | Bản nháp nghiệp vụ đã hết thời gian tiếp tục | Yêu cầu tạo yêu cầu mới hoặc thực hiện quy trình gia hạn theo nghiệp vụ. |

Ba thời hạn này có thể được cấu hình độc lập. Không suy ra flow execution vẫn tồn tại chỉ vì HTTP session chưa hết hạn, hoặc bản nháp còn hợp lệ chỉ vì người dùng vẫn đăng nhập.

## 7. Đổi tài khoản trong cùng trình duyệt

Một rủi ro đặc biệt xuất hiện khi người dùng A đăng xuất rồi người dùng B đăng nhập trên cùng trình duyệt. Tab cũ của A có thể vẫn giữ URL flow execution hoặc hiển thị một trang từ cache.

Ở request kế tiếp, SecurityContext phản ánh người dùng B. Nếu action chỉ kiểm tra rằng có Authentication mà không so sánh với chủ sở hữu flow, B có thể tiếp tục một hành trình được tạo bởi A.

Hãy ràng buộc flow với user id lúc khởi chạy:

~~~java
context.getFlowScope().put("flowOwnerId", currentUser.getId());
~~~

Trước mỗi thao tác nhạy cảm, so sánh user id hiện tại với flowOwnerId và kiểm tra quyền tài nguyên qua service. Nếu không khớp, trả về event riêng như differentUser rồi đưa người dùng đến trang thông báo hoặc đóng flow theo chính sách.

Không dùng session id làm mã chủ sở hữu nghiệp vụ. Session có thể được thay đổi khi đăng nhập do cơ chế bảo vệ session fixation; user id và quyền sở hữu tài nguyên phải đến từ hệ thống danh tính và dữ liệu nghiệp vụ.

### Session fixation và đổi session id

Spring Security thường có cơ chế bảo vệ session fixation khi xác thực thành công. Tùy servlet container và cấu hình, session id có thể được thay đổi trong khi thuộc tính session được di chuyển, hoặc session mới được tạo. Vì thế:

- Không giả định session id giữ nguyên sau login.
- Không dùng session id để ràng buộc chủ sở hữu flow.
- Không tự lưu session id trong flow scope hoặc database.
- Kiểm thử flow execution có còn hoạt động sau đăng nhập theo đúng cấu hình triển khai hay không.
- Dù execution còn tồn tại, vẫn kiểm tra Authentication và owner id trước khi tiếp tục.

## 8. Lưu bản nháp để phục hồi an toàn

Nếu dữ liệu chỉ nằm trong flow scope, session timeout có thể làm mất dữ liệu đó. Với hành trình quan trọng, hãy tạo business draft ở tầng service và lưu vào kho dữ liệu.

Một bản nháp nên có ít nhất:

| Trường | Mục đích |
|---|---|
| draftId | Định danh bản nháp ngẫu nhiên, không phải credential. |
| ownerId | Người dùng sở hữu bản nháp. |
| status | Trạng thái như DRAFT, SUBMITTED, EXPIRED hoặc CANCELLED. |
| payload | Dữ liệu nghiệp vụ đã được kiểm soát và cần để tiếp tục. |
| createdAt / updatedAt | Theo dõi thời điểm tạo và cập nhật. |
| expiresAt | Giới hạn thời gian có thể tiếp tục. |
| version | Hỗ trợ phát hiện cập nhật đồng thời nếu cần. |

Ví dụ service tạo và tải bản nháp:

~~~java
public Draft createDraft(String ownerId, BookingForm form) {
    return draftRepository.save(
        Draft.newDraft(ownerId, form, clock.instant())
    );
}

public Draft loadDraftForUser(String draftId, String currentUserId) {
    Draft draft = draftRepository.findById(draftId)
        .orElseThrow(DraftNotFoundException::new);

    if (!draft.getOwnerId().equals(currentUserId)) {
        throw new AccessDeniedException("Draft access denied");
    }

    if (draft.isExpired(clock.instant())
            || !draft.isResumable()) {
        throw new DraftNotResumableException();
    }

    return draft;
}
~~~

Các kiểu exception và phương thức trong ví dụ là minh họa cho service của ứng dụng. Điểm quan trọng là kiểm tra owner, hạn sử dụng và trạng thái trước khi trả dữ liệu. Không tải bản nháp chỉ dựa trên draftId do client gửi.

Khi khôi phục, hãy tạo một flow execution mới từ bản nháp đã được xác minh. Việc này giúp tránh phụ thuộc vào snapshot cũ và cho phép ứng dụng áp dụng lại quy tắc hiện hành. Trước khi tiếp tục, service nên kiểm tra lại giá, tồn kho, trạng thái tài nguyên và quyền vì những thông tin này có thể đã thay đổi kể từ lúc bản nháp được lưu.

Không lưu credential, session cookie, CSRF token hoặc access token trong payload của bản nháp.

## 9. Xử lý thay đổi trạng thái tài khoản và quyền

Người dùng có thể vẫn đăng nhập nhưng tài khoản bị khóa, bị thu hồi vai trò hoặc mất quyền với tài nguyên giữa hành trình. Chỉ kiểm tra Authentication tồn tại là chưa đủ.

Ở thao tác quan trọng, hãy xác minh:

1. Principal hiện tại có hợp lệ theo chính sách tài khoản không.
2. Tài khoản có đang hoạt động và không bị khóa không.
3. Người dùng có quyền thực hiện thao tác hiện tại không.
4. Người dùng có quyền trên đúng tài nguyên được tham chiếu không.
5. Trạng thái nghiệp vụ có còn cho phép chuyển tiếp không.

Ví dụ, người dùng mở form xác nhận đơn hàng khi còn quyền, nhưng quản trị viên thu hồi quyền trước khi họ bấm Xác nhận. Action xác nhận phải kiểm tra quyền mới nhất qua service. Không dùng một danh sách role đã copy vào flow scope từ lúc bắt đầu để thay thế kiểm tra hiện tại.

Có thể phân biệt các event:

- **authenticationRequired:** không có người dùng đã xác thực.
- **accountDisabled:** tài khoản hiện tại không còn hoạt động.
- **differentUser:** người đang đăng nhập không phải chủ sở hữu flow.
- **accessDenied:** người dùng đã xác thực nhưng không có quyền.
- **draftExpired:** bản nháp không còn được tiếp tục.
- **allowed:** có thể tiếp tục bước hiện tại sau khi các kiểm tra đạt.

Tên event cần khớp với transition trong flow definition. Không đưa chi tiết nhạy cảm về lý do khóa tài khoản hoặc dữ liệu của chủ sở hữu khác vào thông báo hiển thị.

## 10. Kiểm thử thay đổi đăng nhập và hết phiên

Hãy kiểm thử ở cả tầng action/service, flow execution và trình duyệt. Các tình huống nên bao gồm:

| Kịch bản | Cách thực hiện | Kết quả mong đợi |
|---|---|---|
| Đang đăng nhập, tiếp tục flow | Khởi chạy flow với tài khoản A và gửi event tiếp theo | Action đọc Authentication hiện tại và kiểm tra quyền trước khi xử lý. |
| Anonymous truy cập flow cần đăng nhập | Mở URL flow khi chưa đăng nhập | Chuyển đến login hoặc nhánh authenticationRequired. |
| Login giữa hành trình | Bắt đầu ở trạng thái anonymous rồi đăng nhập | Chỉ tiếp tục execution nếu execution còn hợp lệ và owner được xác minh; nếu không thì khôi phục từ draft hoặc bắt đầu mới. |
| Logout ở tab khác | Mở flow ở tab A, đăng xuất ở tab B rồi gửi request từ tab A | Request tab A bị yêu cầu xác thực lại hoặc bị chặn. |
| Đổi tài khoản | Tài khoản A khởi chạy flow, logout rồi tài khoản B login và mở tab cũ | B không thể tiếp tục flow của A. |
| Session timeout | Để session hết hạn rồi gửi request tiếp theo | Hiển thị thông báo hết phiên và phục hồi theo chính sách. |
| Flow execution hết hạn | Giữ session nhưng dùng execution đã hết hạn | Báo execution không còn hợp lệ; không giả định flow scope còn nguyên. |
| Draft thuộc người khác | Đăng nhập B và gửi draftId của A | Service từ chối truy cập. |
| Draft đã hết hạn | Tiếp tục draft sau expiresAt | Không khôi phục; yêu cầu tạo hành trình mới. |
| Quyền bị thu hồi | Thu hồi quyền sau khi mở form rồi gửi event confirm | Service từ chối thao tác tại thời điểm thực thi. |
| Submit lặp sau login | Gửi lại request sau redirect hoặc refresh | Nghiệp vụ không bị thực hiện hai lần. |

### Kiểm thử action

Mock CurrentUserProvider hoặc thiết lập SecurityContext trong test để kiểm tra:

- Authentication không tồn tại.
- Authentication anonymous.
- Principal hợp lệ.
- Principal không đúng kiểu ứng dụng hỗ trợ.
- User id hiện tại khác flowOwnerId.
- Service xác nhận người dùng không còn quyền.

Xác nhận action trả về đúng event id và không gọi service ghi dữ liệu khi kiểm tra thất bại.

### Kiểm thử flow và trình duyệt

Kiểm thử tích hợp flow để xác nhận mỗi event dẫn đến state dự kiến. Kiểm thử đầu cuối trên trình duyệt để xác nhận redirect login, logout, session cookie, nhiều tab, Back và URL execution cũ.

Không chỉ kiểm tra trang login xuất hiện. Hãy xác nhận sau login người dùng không thể tiếp tục execution của tài khoản khác và mọi thao tác ghi đều được kiểm tra lại.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Flow tiếp tục dù người dùng đã logout | Action chỉ kiểm tra flow execution còn tồn tại | Đọc lại Authentication ở mỗi request hoặc transition nhạy cảm. |
| Người dùng B thấy dữ liệu flow của A | Không ràng buộc owner id với flow hoặc draft | So sánh principal hiện tại với owner và kiểm tra quyền tài nguyên. |
| Login thành công nhưng URL cũ báo lỗi | Execution nằm trong session đã mất hoặc không còn trong repository | Khôi phục từ draft đã xác minh hoặc khởi chạy flow mới. |
| Login xong bị quay về trang bắt đầu | Saved request hoặc flow execution cũ không còn hợp lệ | Xử lý riêng URL trở về và trạng thái nghiệp vụ; không hứa khôi phục snapshot cũ. |
| Dữ liệu form mất sau timeout | Dữ liệu chỉ nằm trong flow scope/session | Lưu draft bền vững theo chính sách phù hợp nếu nghiệp vụ cần phục hồi. |
| Session id thay đổi sau login làm flow lỗi | Giả định session id hoặc repository giữ execution theo cách cố định | Kiểm tra session fixation strategy và repository của phiên bản đang dùng. |
| Tài khoản bị khóa nhưng flow vẫn xác nhận được | Quyền hoặc trạng thái tài khoản chỉ được kiểm tra lúc khởi chạy | Kiểm tra lại tại thao tác nhạy cảm trong service. |
| Draft id bị dùng để đọc dữ liệu người khác | Service không xác minh owner id | Ràng buộc draft với principal hiện tại ở phía máy chủ. |
| Logout không hoạt động hoặc bị từ chối | Sai endpoint, method hoặc CSRF token | Kiểm tra Spring Security logout configuration và form gửi request. |
| Request từ tab cũ gây lỗi execution | Tab giữ URL hoặc snapshot đã hết hạn | Hiển thị hướng dẫn bắt đầu lại hoặc phục hồi từ draft. |

## 12. Checklist bảo vệ flow

- [ ] Flow owner được ghi nhận bằng user id lấy từ principal đã xác thực.
- [ ] Authentication được đọc lại từ SecurityContext trong request hiện tại.
- [ ] Anonymous được phân biệt với người dùng đã xác thực.
- [ ] Mỗi thao tác nhạy cảm kiểm tra quyền trên đúng tài nguyên.
- [ ] Flow không giữ mật khẩu, token, cookie hoặc toàn bộ Authentication trong scope.
- [ ] Người dùng khác không thể tiếp tục flow hoặc draft của chủ sở hữu trước.
- [ ] Logout xử lý đúng endpoint, method và CSRF policy.
- [ ] Session timeout và flow execution timeout được xử lý riêng.
- [ ] Có thông báo rõ ràng khi phiên hoặc execution đã hết hạn.
- [ ] Bản nháp cần phục hồi được lưu bền vững, có owner và expiresAt.
- [ ] Khôi phục tạo flow mới sau khi xác minh draft và quyền.
- [ ] Trạng thái tài khoản, quyền và dữ liệu nghiệp vụ được kiểm tra lại trước khi ghi.
- [ ] Đã kiểm thử nhiều tab, đổi tài khoản, logout, timeout, Back và submit lặp.

## Kết luận

Spring Web Flow quản lý hành trình và snapshot của flow execution; Spring Security xác định người dùng của request; HTTP session có vòng đời riêng. Khi đăng nhập, đăng xuất, đổi tài khoản hoặc hết phiên giữa hành trình, hãy đọc lại Authentication, so sánh chủ sở hữu flow, kiểm tra quyền trên tài nguyên và xử lý execution cũ theo chính sách phục hồi. Với quy trình cần tiếp tục sau timeout, lưu một bản nháp nghiệp vụ có chủ sở hữu và thời hạn rõ ràng rồi khởi chạy flow mới từ bản nháp đã được xác minh.
