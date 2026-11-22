# Đặt trạng thái người dùng trong đối tượng dùng chung

## 1. Vấn đề: trạng thái của một request bị chia sẻ cho request khác

Trong ứng dụng Model–View–Controller, Controller tiếp nhận request, gọi Service và chuẩn bị dữ liệu cho View. Với Spring MVC, Controller và Service được đăng ký như singleton bean theo mặc định trong phần lớn trường hợp. Một instance được nhiều request sử dụng đồng thời.

Điều đó phù hợp khi bean giữ dependency dùng chung và hành vi không phụ thuộc trạng thái riêng của một người dùng. Vấn đề xuất hiện khi lập trình viên đặt dữ liệu của request hoặc người dùng vào field có thể thay đổi của bean dùng chung, chẳng hạn `currentUser`, `currentOrder`, `currentForm` hoặc `selectedBook`.

Khi hai request chạy đồng thời, request này có thể ghi đè dữ liệu mà request kia vừa đặt. Kết quả không chỉ là lỗi hiển thị: ứng dụng có thể trả dữ liệu của người này cho người khác, cập nhật nhầm tài nguyên hoặc áp dụng quyền theo sai danh tính.

Ví dụ, người dùng A mở trang hồ sơ cùng lúc người dùng B mở trang hồ sơ. Nếu Controller giữ hồ sơ hiện tại trong một field singleton, hai request có thể ghi và đọc cùng một vị trí nhớ. Đây là lỗi về vòng đời và cô lập dữ liệu, không đơn thuần là vấn đề đồng bộ thread.

## 2. Vì sao lỗi xảy ra trong MVC?

HTTP xử lý request theo từng lần gọi, nhưng các bean singleton tồn tại lâu hơn request. Một bean dùng chung có thể được nhiều thread gọi cùng lúc:

~~~mermaid
sequenceDiagram
    participant A as Request người dùng A
    participant C as Singleton Controller
    participant B as Request người dùng B
    A->>C: Gán currentUser = A
    B->>C: Gán currentUser = B
    A->>C: Đọc currentUser
    C-->>A: Trả về B
    Note over A,B: Trạng thái của hai request đã bị trộn
~~~

Việc này có thể xảy ra ngay cả khi mỗi request đều hợp lệ và không có lỗi trong từng dòng lệnh riêng lẻ. Lịch chạy thread quyết định request nào ghi trước, đọc sau; lỗi có thể xuất hiện không ổn định và khó tái hiện.

Trong Spring MVC, các đối tượng sau thường cần được chú ý:

| Đối tượng | Vòng đời thường gặp | Rủi ro khi chứa state người dùng |
|---|---|---|
| `@Controller` | Singleton | Field mutable bị nhiều request dùng chung |
| `@Service` | Singleton | Lưu `currentUser`, form hoặc kết quả truy vấn vào field |
| `@Repository` | Singleton | Giữ tham số truy vấn hoặc Entity hiện tại trong field |
| `@ControllerAdvice` | Singleton | Giữ thông tin lỗi hoặc người dùng của request trước |
| Mapper/Formatter dùng chung | Thường singleton | Giữ buffer hoặc biến tạm mutable không an toàn luồng |
| Static field hoặc singleton tự tạo | Thường tồn tại suốt process | Chia sẻ state giữa mọi request và có thể giữa tenant |

Không phải mọi field trong singleton đều nguy hiểm. Dependency bất biến, cấu hình, client dùng chung an toàn luồng và cache được thiết kế đúng có thể được chia sẻ. Rủi ro nằm ở dữ liệu thay đổi theo request hoặc người dùng.

## 3. Ví dụ sai: lưu người dùng hiện tại trong Controller

~~~java
@Controller
@RequestMapping("/profile")
public class ProfileController {
    private final ProfileService profileService;

    // Sai: field này được mọi request dùng chung.
    private Profile currentProfile;

    public ProfileController(ProfileService profileService) {
        this.profileService = profileService;
    }

    @GetMapping
    public String show(Principal principal, Model model) {
        currentProfile = profileService.findByUsername(
                principal.getName());
        model.addAttribute("profile", currentProfile);
        return "profile/detail";
    }
}
~~~

Controller mặc định là singleton. Nếu request A gán `currentProfile` rồi request B ghi đè trước khi A đưa dữ liệu vào Model, A có thể nhận hồ sơ của B. Cũng có thể request A render đúng nhưng một request tiếp theo thay đổi field trong lúc A đang dùng đối tượng đó.

Thêm `synchronized` quanh phương thức không phải cách sửa tốt. Nó có thể làm các request phải chờ nhau, giảm throughput, nhưng vẫn giữ kiến trúc phụ thuộc vào một biến trạng thái dùng chung. Nếu một object được giữ trong field và được trả ra View hoặc dùng sau khi lock kết thúc, vấn đề còn có thể tiếp tục.

## 4. Cách đúng: dùng biến cục bộ theo request

Nếu dữ liệu chỉ cần trong một lần xử lý, hãy giữ nó trong biến cục bộ của phương thức:

~~~java
@Controller
@RequestMapping("/profile")
public class ProfileController {
    private final ProfileService profileService;

    public ProfileController(ProfileService profileService) {
        this.profileService = profileService;
    }

    @GetMapping
    public String show(Principal principal, Model model) {
        Profile profile = profileService.findByUsername(
                principal.getName());
        model.addAttribute("profile", profile);
        return "profile/detail";
    }
}
~~~

Mỗi lần gọi `show` có stack frame và biến cục bộ riêng. Request A và B không ghi đè biến `profile` của nhau. Controller vẫn là singleton nhưng không giữ dữ liệu riêng của request sau khi phương thức kết thúc.

Biến cục bộ không tự bảo đảm đối tượng được tham chiếu là bất biến hoặc an toàn luồng. Nếu Service trả về một object mutable được chia sẻ toàn cục, việc thay đổi object đó vẫn có thể ảnh hưởng request khác. Hãy phân biệt vòng đời biến tham chiếu với vòng đời và quyền sở hữu của object mà nó trỏ tới.

## 5. Giữ Service stateless

Service singleton nên giữ dependency và cấu hình dùng chung; dữ liệu thay đổi theo request nên được truyền qua tham số và biến cục bộ.

Ví dụ không nên làm:

~~~java
@Service
public class CheckoutService {
    private UserId currentUserId;
    private Cart currentCart;

    public void checkout(UserId userId) {
        this.currentUserId = userId;
        this.currentCart = loadCart(userId);
        // Xử lý tiếp dựa trên các field dùng chung...
    }
}
~~~

Thiết kế stateless:

~~~java
@Service
public class CheckoutService {
    private final CartRepository carts;
    private final OrderRepository orders;

    public CheckoutService(
            CartRepository carts,
            OrderRepository orders) {
        this.carts = carts;
        this.orders = orders;
    }

    public OrderId checkout(UserId userId) {
        Cart cart = carts.findByOwner(userId)
                .orElseThrow(CartNotFoundException::new);

        Order order = Order.from(cart, userId);
        orders.save(order);
        return order.id();
    }
}
~~~

`userId` được truyền vào use case; `cart` và `order` là biến cục bộ. Service không ghi danh tính hoặc giỏ hàng hiện tại vào field. Nếu cần xác định người gọi, application boundary lấy danh tính đã xác thực rồi truyền vào use case dưới dạng `Actor` hoặc `UserId`.

Stateless không có nghĩa Service không được dùng database, cache hoặc client dùng chung. Nó có nghĩa một lần gọi không dựa vào field mutable chứa dữ liệu riêng của lần gọi khác.

## 6. Truyền danh tính đã xác thực qua application boundary

Đừng lưu người dùng hiện tại bằng cách tự gán vào field singleton. Trong ứng dụng web, danh tính nên đến từ cơ chế xác thực được cấu hình, sau đó được truyền rõ ràng vào use case.

Ví dụ một đối tượng mô tả người thực hiện:

~~~java
public record Actor(UserId userId, TenantId tenantId) {}

public record UpdateProfileCommand(
        Actor actor,
        String displayName
) {}
~~~

Controller có thể lấy principal từ Spring Security rồi chuyển thành `Actor` qua một thành phần chuyên trách:

~~~java
@Controller
@RequestMapping("/profile")
public class ProfileController {
    private final CurrentActor currentActor;
    private final ProfileService profileService;

    public ProfileController(
            CurrentActor currentActor,
            ProfileService profileService) {
        this.currentActor = currentActor;
        this.profileService = profileService;
    }

    @PostMapping
    public String update(
            @Valid @ModelAttribute("form") ProfileForm form,
            BindingResult errors) {
        if (errors.hasErrors()) {
            return "profile/form";
        }
        Actor actor = currentActor.require();
        profileService.update(new UpdateProfileCommand(
                actor, form.getDisplayName()));
        return "redirect:/profile";
    }
}
~~~

`CurrentActor` là abstraction của ứng dụng để lấy danh tính từ security context hiện tại. Cách triển khai có thể dùng `Authentication`/`Principal` hoặc `SecurityContextHolder`; Controller không nhận `userId` từ hidden field hay request body làm nguồn xác thực.

Việc truyền `Actor` tường minh giúp Service dễ unit test và làm rõ use case đang thực hiện thay mặt ai. Service vẫn phải kiểm tra quyền và ownership; việc có `Actor` không tự động chứng minh người đó được phép thao tác.

## 7. Chọn scope đúng với vòng đời dữ liệu

Nếu dữ liệu cần tồn tại lâu hơn một phương thức, hãy chọn nơi lưu dựa trên vòng đời thực tế:

| Nhu cầu | Nơi lưu phù hợp | Ví dụ |
|---|---|---|
| Chỉ dùng trong một lần gọi | Biến cục bộ hoặc tham số | Form đã binding, kết quả truy vấn |
| Dùng trong một HTTP request | Request attribute hoặc request-scoped bean | Correlation ID, dữ liệu phụ trợ cho request |
| Qua nhiều request trong cùng phiên | Session attribute hoặc session-scoped bean | Wizard ngắn, lựa chọn giao diện |
| Tồn tại lâu, cần tiếp tục sau đăng xuất hoặc trên thiết bị khác | Database draft hoặc kho lưu trữ phù hợp | Hồ sơ đang nhập, đơn hàng nháp |
| Dùng chung cho nhiều request | Bean singleton stateless, immutable config hoặc cache có thiết kế an toàn | Service, formatter immutable, HTTP client an toàn luồng |

Đừng chọn session chỉ vì muốn tránh singleton field. Session có vòng đời dài hơn request và thường chứa dữ liệu riêng của một phiên trình duyệt; cần có chính sách hết hạn, phân quyền và xử lý nhiều tab.

### Request-scoped bean

Spring hỗ trợ `@RequestScope` cho đối tượng sống trong phạm vi một HTTP request:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope
public class RequestContext {
    private String correlationId;

    public String getCorrelationId() {
        return correlationId;
    }

    public void setCorrelationId(String correlationId) {
        this.correlationId = correlationId;
    }
}
~~~

Request-scoped bean hữu ích khi nhiều thành phần trong cùng request cần truy cập cùng context. Khi inject vào singleton bean, Spring thường cần scoped proxy hoặc `ObjectProvider` để phân giải instance theo request; không tự giữ một instance request cụ thể trong field sau khi request kết thúc.

Không dùng request scope để lưu trạng thái cần tồn tại qua nhiều request. Khi request hoàn tất, dữ liệu của scope này không còn là nơi lưu trữ tiến trình.

### Session-scoped bean

Với dữ liệu thật sự thuộc phiên người dùng, có thể dùng `@SessionScope` hoặc cơ chế session attribute. Ví dụ trạng thái wizard nhỏ:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.SessionScope;

@Component
@SessionScope
public class RegistrationWizardState {
    private String fullName;
    private String selectedPlan;

    public void updateIdentity(String fullName) {
        this.fullName = fullName;
    }

    public void selectPlan(String selectedPlan) {
        this.selectedPlan = selectedPlan;
    }

    public String fullName() { return fullName; }
    public String selectedPlan() { return selectedPlan; }
}
~~~

Đối tượng này chỉ phù hợp với trạng thái tạm thời của wizard. Không đặt Entity dùng chung, connection, transaction hoặc dữ liệu nhạy cảm không cần thiết vào session. Khi hoàn tất hoặc hủy wizard, xóa state theo cơ chế phù hợp; không chờ session timeout mới dọn.

**Session scope không đồng nghĩa với thread safety.** Một người dùng có thể mở nhiều tab hoặc gửi nhiều request đồng thời trong cùng session. Nếu hai request cùng cập nhật `RegistrationWizardState`, chúng vẫn có thể ghi đè nhau. Dùng flow ID riêng cho từng wizard, cập nhật state bất biến theo phiên bản hoặc cơ chế đồng bộ phù hợp.

## 8. Không dùng static field hoặc singleton tự tạo để giữ người dùng

Đổi field thành `static` không sửa lỗi; nó làm phạm vi chia sẻ rộng hơn. Mọi instance của class trong cùng class loader nhìn thấy cùng giá trị static.

~~~java
public class CurrentUserHolder {
    public static User currentUser;
}
~~~

Cách này khiến request của các người dùng có thể ghi đè cùng một biến, và còn làm test phụ thuộc thứ tự chạy nếu không reset đúng cách. Tương tự, một singleton tự tạo qua `getInstance()` cũng có thể giữ trạng thái dùng chung ngoài phạm vi cần thiết.

Static constant bất biến như `static final int DEFAULT_PAGE_SIZE = 20` không có cùng rủi ro. Vấn đề là dữ liệu mutable thay đổi theo request, người dùng hoặc tenant.

## 9. ThreadLocal không phải kho lưu trạng thái người dùng tùy tiện

`ThreadLocal` tạo một giá trị riêng cho từng thread, vì vậy đôi khi được dùng để giữ correlation ID hoặc context trong quá trình xử lý đồng bộ. Tuy nhiên, servlet container thường tái sử dụng thread cho nhiều request. Nếu không xóa giá trị, request sau có thể đọc dữ liệu của request trước trên cùng thread.

Ví dụ cleanup thủ công phải nằm trong `finally`:

~~~java
private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

public void handle(String requestId) {
    REQUEST_ID.set(requestId);
    try {
        process();
    } finally {
        REQUEST_ID.remove();
    }
}
~~~

Đây chỉ là ví dụ minh họa. Trong ứng dụng Spring Security, không tự tạo một `ThreadLocal<User>` song song với security context. Spring Security đã quản lý `SecurityContext` theo strategy được cấu hình và filter chain có trách nhiệm xóa context sau request.

ThreadLocal cũng không tự truyền sang thread khác. Khi dùng `@Async`, executor hoặc reactive pipeline, không giả định context của request tự có mặt trong tác vụ nền. Hãy truyền dữ liệu cần thiết một cách tường minh hoặc dùng cơ chế context propagation được framework hỗ trợ.

## 10. Không giữ trạng thái người dùng trong View Model dùng chung

View Model hoặc DTO được tạo để hiển thị dữ liệu cho một request nên thường được tạo mới cho request đó. Không tái sử dụng một object mutable toàn cục rồi cập nhật thuộc tính theo người dùng hiện tại.

Ví dụ sai:

~~~java
@Component
public class SharedProfileViewModel {
    private String displayName;
    private String email;

    public void load(Profile profile) {
        this.displayName = profile.displayName();
        this.email = profile.email();
    }
}
~~~

Nếu bean trên là singleton, hai request có thể quan sát giá trị bị trộn. Thay vào đó, tạo một record/DTO mới cho từng response:

~~~java
public record ProfileView(
        String displayName,
        String email
) {}

public ProfileView toView(Profile profile) {
    return new ProfileView(
            profile.displayName(),
            profile.email());
}
~~~

Record giúp giới hạn việc thay đổi sau khi tạo. Nếu các trường bên trong chứa collection hoặc object mutable, cần sao chép hoặc cung cấp cấu trúc bất biến phù hợp; `record` chỉ làm reference final, không tự làm mọi object lồng bên trong immutable.

## 11. Cẩn trọng với cache dữ liệu theo người dùng và tenant

Cache dùng chung có thể an toàn nếu key và chính sách dữ liệu được thiết kế đúng. Lỗi thường gặp là cache response cá nhân chỉ theo resource ID:

~~~java
@Cacheable(cacheNames = "profileViews", key = "#p0")
public ProfileView profileView(ProfileId profileId, Actor actor) {
    // Kết quả có thể phụ thuộc quyền và tenant của actor.
    return buildProfileView(profileId, actor);
}
~~~

Với `@Cacheable` không chỉ định `key` hay `keyGenerator`, Spring Cache mặc định tạo key từ toàn bộ tham số phương thức (một tham số thì dùng chính tham số đó; nhiều tham số thì dùng khóa tổng hợp). Lỗi trong ví dụ xảy ra vì key tùy chỉnh chỉ dùng tham số đầu tiên (`#p0`, tức `profileId`), trong khi kết quả lại phụ thuộc `actor`. Người dùng đầu tiên có thể làm cache lưu kết quả được cá nhân hóa; request sau có thể nhận nhầm kết quả đó. Cách sửa là xác định rõ dữ liệu nào thực sự phụ thuộc actor, xây key chứa đủ phạm vi bảo mật hoặc không cache response đã cá nhân hóa. Không dựa vào việc key mặc định có chứa một object actor để thay thế kiểm tra quyền; phải bảo đảm mọi thuộc tính ảnh hưởng đến kết quả đều có trong key và policy vẫn được áp dụng ở mỗi request.

Ví dụ cache dữ liệu công khai theo ID:

~~~java
@Cacheable(cacheNames = "publicBooks", key = "#bookId")
public PublicBookView publicBook(BookId bookId) {
    return bookQuery.publicView(bookId);
}
~~~

Cache public có thể dùng chung nếu nội dung thật sự giống nhau với mọi người và không chứa dữ liệu riêng. Với dữ liệu tenant, key cần có tenant ID. Với kết quả phụ thuộc user hoặc quyền, cần tính cả user/permission context thích hợp hoặc cache dữ liệu nền rồi áp dụng authorization ở mỗi request.

Cache key không thay thế kiểm tra quyền. Dù key có tenant ID, Service vẫn phải xác minh actor được phép truy cập tài nguyên.

## 12. Tác vụ bất đồng bộ không được dựa vào field request

Request có thể kết thúc trong khi tác vụ nền vẫn chạy. Không lưu người dùng hiện tại vào field singleton rồi để task đọc field đó sau:

~~~java
@Service
public class ExportService {
    private UserId currentUserId;

    public void startExport(UserId userId) {
        currentUserId = userId;
        executor.execute(() -> exportFor(currentUserId));
    }
}
~~~

Nếu request B ghi đè `currentUserId` trước khi task A đọc, task A có thể export dữ liệu của B.

Truyền dữ liệu cần thiết vào closure hoặc command bất biến:

~~~java
public void startExport(UserId userId, ExportId exportId) {
    ExportCommand command = new ExportCommand(userId, exportId);
    executor.execute(() -> exportFor(command));
}
~~~

Tác vụ nền nên dùng danh tính và quyền đã được xác định rõ tại thời điểm tạo job, hoặc xác thực lại theo policy khi thực thi nếu yêu cầu nghiệp vụ đòi hỏi quyền hiện tại. Không truyền `HttpServletRequest`, session object hoặc một request-scoped bean vào task chạy lâu.

Nếu tác vụ cần `SecurityContext`, dùng cơ chế truyền context được hỗ trợ như `DelegatingSecurityContextExecutor` khi phù hợp, hoặc truyền Actor/ID tường minh. Chỉ truyền các thuộc tính cần thiết; không sao chép toàn bộ session hoặc request vào job.

## 13. Bảo vệ dữ liệu đa người dùng và đa tenant

Ranh giới dữ liệu không chỉ là mỗi người dùng có một field riêng. Mọi truy vấn và thao tác cần xác định phạm vi truy cập theo danh tính đã xác thực.

Ví dụ Service nhận actor và Repository giới hạn truy vấn theo tenant:

~~~java
public ProfileView getProfile(Actor actor, UserId targetUserId) {
    Profile profile = profiles.findByUserIdAndTenantId(
            targetUserId, actor.tenantId())
            .orElseThrow(ProfileNotFoundException::new);

    profilePolicy.requireCanView(actor, profile);
    return profileMapper.toView(profile);
}
~~~

Việc giới hạn truy vấn theo tenant giảm nguy cơ vô tình tải dữ liệu ngoài phạm vi. Policy vẫn cần kiểm tra quyền cụ thể như chủ sở hữu, vai trò quản lý hoặc quan hệ được phép. Không lấy `tenantId` từ form làm nguồn có thẩm quyền; actor cần đến từ security context hoặc một cơ chế xác thực tin cậy.

Đừng dùng một field `currentTenant` trong singleton để tránh phải truyền tenant ID. Hãy truyền phạm vi rõ ràng qua tham số hoặc một abstraction request-scoped được quản lý đúng vòng đời.

## 14. Kiểm thử lỗi chia sẻ state

Test tuần tự có thể không phát hiện race condition. Cần kiểm tra cả hai loại tình huống:

1. **Cô lập giữa các request tuần tự:** request A kết thúc, request B bắt đầu; response B không chứa dữ liệu còn sót từ A.
2. **Cô lập giữa các request đồng thời:** hai request chạy chồng lấn; mỗi response chỉ chứa dữ liệu của đúng người dùng.

Ma trận kiểm thử gợi ý:

| Tình huống | Kết quả cần xác minh |
|---|---|
| A xem hồ sơ rồi B xem hồ sơ | Mỗi response có đúng hồ sơ tương ứng |
| A và B gọi endpoint đồng thời | Không có dữ liệu chéo giữa hai response |
| Hai request cùng session cập nhật wizard | Xung đột được xử lý theo flow ID/version hoặc policy đã chọn |
| Request A phát sinh exception | Request B không nhận state hoặc lỗi còn sót từ A |
| Tác vụ export A và B chạy đồng thời | Mỗi job dùng đúng Actor/UserId đã truyền khi tạo job |
| Cache được truy cập bởi hai tenant | Không trả view hoặc dữ liệu của tenant khác |
| Request dùng lại thread trong pool | ThreadLocal đã được remove trước request tiếp theo |

### Test phát hiện state singleton bị ghi đè

Có thể tạo test điều khiển thứ tự thực thi bằng `CountDownLatch` hoặc `CyclicBarrier`, thay vì dựa vào việc gửi nhiều request ngẫu nhiên. Một fake Service có thể tạm dừng request A sau khi Controller bắt đầu xử lý, cho request B chạy qua, rồi tiếp tục A. Nếu Controller dùng field `currentProfile`, test sẽ phát hiện response A có thể nhận dữ liệu B.

Với endpoint web, dùng MockMvc hoặc HTTP integration test với hai principal khác nhau. Xác minh response body/model, không chỉ status code. Đồng thời kiểm tra Service được gọi với đúng actor và ID.

Để test ổn định, điều khiển interleaving bằng latch/barrier và timeout hữu hạn; tránh `Thread.sleep()` để hy vọng hai thread đụng nhau. Chạy test lặp lại có thể bổ sung độ tin cậy nhưng không thay thế việc điều khiển thứ tự.

## 15. Checklist khi review Controller và Service

Trước khi đưa một bean vào dùng chung, hãy hỏi:

- Bean có scope singleton hoặc được giữ trong static field không?
- Field nào thay đổi sau khi bean được tạo?
- Giá trị đó có phụ thuộc request, user, tenant hoặc màn hình không?
- Có thể chuyển field thành tham số hoặc biến cục bộ không?
- Object được trả về có mutable và được chia sẻ với nơi khác không?
- Nếu cần request/session scope, vòng đời và cleanup đã rõ chưa?
- Hai request đồng thời trong cùng session có thể cập nhật cùng state không?
- Cache key có bao gồm mọi phạm vi bảo mật ảnh hưởng đến kết quả không?
- Tác vụ nền có nhận dữ liệu cần thiết qua command riêng không?
- Có test tuần tự và test đồng thời cho hai danh tính khác nhau không?

Quy tắc thực hành hữu ích: singleton giữ dependency và cấu hình bất biến; request giữ dữ liệu request; session giữ state phiên có chủ đích; database giữ tiến trình cần tồn tại lâu; cache chỉ giữ dữ liệu dùng chung theo key và policy rõ ràng.

## 16. Những sai lầm thường gặp

- **Lưu `currentUser` trong field Controller:** request khác có thể ghi đè và gây rò dữ liệu.
- **Lưu form hoặc Entity hiện tại trong Service singleton:** dữ liệu của các lần gọi có thể bị trộn.
- **Chuyển field thành static:** mở rộng phạm vi chia sẻ ra toàn process.
- **Thêm `synchronized` để chữa singleton state:** che triệu chứng, gây tuần tự hóa request và không sửa sai vòng đời.
- **Dùng session cho mọi dữ liệu người dùng:** làm state tồn tại quá lâu và phát sinh xung đột giữa nhiều tab.
- **Cho rằng `@SessionScope` tự thread-safe:** nhiều request cùng session vẫn có thể chạy đồng thời.
- **Dùng ThreadLocal mà không remove:** thread pool có thể mang state của request trước sang request sau.
- **Truyền request/session object vào tác vụ nền:** tác vụ có thể chạy sau khi scope đã kết thúc.
- **Cache view cá nhân chỉ theo resource ID:** có thể trả dữ liệu của user hoặc tenant khác.
- **Dùng record nhưng giữ collection mutable bên trong:** state vẫn có thể bị thay đổi gián tiếp.
- **Chỉ test từng request riêng lẻ:** không phát hiện interleaving hoặc dữ liệu tồn dư giữa các request.

## 17. Kết luận

Đặt trạng thái người dùng trong đối tượng dùng chung là lỗi thiết kế nghiêm trọng trong MVC vì Controller, Service, Repository và nhiều thành phần Spring thường là singleton được nhiều request sử dụng đồng thời. Field mutable chứa user, form, Entity hoặc tenant có thể bị ghi đè, làm request nhận nhầm dữ liệu và gây rò rỉ giữa người dùng.

Hãy giữ dữ liệu của một lần gọi trong biến cục bộ, truyền Actor/UserId qua application boundary, dùng request scope hoặc session scope đúng vòng đời, và lưu tiến trình dài hạn ở nơi lưu trữ phù hợp. Với cache và tác vụ nền, xác định rõ phạm vi dữ liệu và truyền context cần thiết một cách tường minh. Kiểm thử hai người dùng tuần tự lẫn đồng thời để xác nhận mỗi request chỉ nhìn thấy dữ liệu mà nó được phép truy cập.
