# Ranh giới xác thực, phân quyền và kiểm tra dữ liệu

Một flow đặt lịch có thể đi qua các màn hình **nhập thông tin → xem lại → xác nhận → hoàn tất**. Spring Web Flow (SWF) giúp mô tả hành trình đó bằng `view-state`, `action-state`, `event` và `transition`, giữ dữ liệu qua các bước trong `flowScope` hoặc `conversationScope`. Nhưng một flow chạy đúng về mặt điều hướng vẫn có thể không an toàn: người dùng chưa đăng nhập có thể truy cập một URL, người dùng A có thể gửi ID bản nháp của người B, hoặc client cố tình gửi event và trường form khác với giao diện.

Chủ đề của bài là **ranh giới xác thực, phân quyền và kiểm tra dữ liệu** trong module `SPRING_WEB_FLOW`. Mục tiêu là biết mỗi lớp chịu trách nhiệm bảo vệ điều gì, cách phối hợp Spring Security với Spring MVC/Web Flow, và cách kiểm thử cả đường đi hợp lệ lẫn yêu cầu bị sửa đổi. Các ví dụ mô tả nguyên tắc an toàn; API và cấu hình cụ thể phải được kiểm tra theo dòng Spring Framework/Web Flow đang dùng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **authentication**, **authorization**, **data binding**, **validation** và **business invariants**.
2. Vẽ được các ranh giới tin cậy từ trình duyệt tới servlet filter, Spring MVC, Web Flow, service và database.
3. Xác định điểm kiểm tra quyền ở **URL/flow/state** và tại **đối tượng nghiệp vụ/hành động thực sự**.
4. Hiểu vì sao `_eventId`, `execution`, dữ liệu `flowScope` và session ID đều không tự chứng minh người gửi được phép thực hiện một thao tác.
5. Giới hạn các field được bind, validate cả dữ liệu lẫn quy tắc nghiệp vụ và bảo vệ thao tác ghi trước CSRF hoặc submit lặp.
6. Thiết kế kiểm thử cho chuyển state, subflow, quyền sở hữu bản nháp, session timeout, nhiều tab và khôi phục sau lỗi.

Ví dụ xuyên suốt là flow đặt lịch khám:

~~~mermaid
stateDiagram-v2
    [*] --> details
    details --> review: next
    details --> cancelled: cancel
    review --> details: back
    review --> confirm: confirm
    confirm --> finished: success
    confirm --> review: validationError
    finished --> [*]
    cancelled --> [*]
~~~

Người dùng được phép chỉnh sửa bản nháp của mình, nhưng chỉ được xác nhận khi đã đăng nhập, sở hữu bản nháp, dữ liệu còn hợp lệ và slot lịch chưa bị người khác đặt. Giao diện có thể ẩn nút “Xác nhận” khi thiếu quyền; **server vẫn phải kiểm tra các điều kiện đó**.

## 2. Từ ngữ dễ nhầm: năm loại kiểm tra độc lập

| Loại kiểm tra | Câu hỏi phải trả lời | Ví dụ với flow đặt lịch |
| --- | --- | --- |
| **Xác thực (authentication)** | Người gửi request là ai? | Session đã đăng nhập dưới tài khoản nào? |
| **Phân quyền (authorization)** | Người này có được làm hành động trên tài nguyên này? | Người A có quyền xác nhận bản nháp #42 không? |
| **Binding** | Những trường nào từ request được ghi vào model? | Chỉ nhận `phone` và `appointmentDate`, không nhận `ownerId` |
| **Validation** | Dữ liệu có đúng định dạng, phạm vi và quan hệ hợp lệ? | Ngày hẹn hợp lệ, số điện thoại đúng định dạng |
| **Ràng buộc nghiệp vụ (invariants)** | Thao tác còn hợp lệ trong trạng thái hiện tại của hệ thống? | Slot còn trống, bản nháp chưa xác nhận, không tạo hai lịch trùng |

**Một kiểm tra không thay cho kiểm tra khác.** Bean Validation có thể xác nhận `appointmentDate` là ngày tương lai, nhưng không biết người gửi có sở hữu bản nháp hay slot vừa bị người khác giữ. Spring Security xác nhận tài khoản, nhưng không tự biết tất cả quy tắc của nghiệp vụ đặt lịch.

Vì HTTP request và các tham số đến từ client, hãy xem mọi giá trị do trình duyệt gửi là **không đáng tin cậy cho tới khi server kiểm tra**, kể cả những giá trị xuất hiện trong một hidden field hoặc URL đã được Web Flow tạo ra.

## 3. Bản đồ ranh giới tin cậy của một flow

~~~mermaid
flowchart TD
    A["Trình duyệt / HTTP request<br/>event, form, cookie, URL"] --> B["Servlet Filter Chain<br/>Spring Security: authentication, CSRF"]
    B --> C["DispatcherServlet / MVC Handler<br/>URL và request mapping"]
    C --> D["Spring Web Flow<br/>flow execution, state, event, transition"]
    D --> E["Binding + Validation<br/>allowed fields, constraints"]
    E --> F["Service / Method Security<br/>ownership, permission, state, transaction"]
    F --> G["Repository / Database<br/>constraints, version, durability"]
    G --> F
    F --> D
    D --> H["View rendering / HTTP response"]
    H --> A
~~~

Sơ đồ biểu diễn **các lớp kiểm soát**, không khẳng định mọi yêu cầu luôn chạy qua mọi hộp theo đúng thứ tự minh họa. Chẳng hạn, một request bị từ chối ở security filter sẽ không vào flow; một request chỉ render view có thể không gọi service ghi dữ liệu.

### 3.1. Ranh giới 1 — từ client tới HTTP server

Client có thể:

- Sửa query string, form body, hidden field và `_eventId`.
- Gửi lại request đã từng thành công; mở hai tab với các execution khác nhau.
- Giữ một URL hoặc execution key cũ rồi thử dùng sau timeout/logout.
- Gửi trực tiếp POST mà không bấm nút trên giao diện.
- Tạo request qua trình duyệt nạn nhân nếu ứng dụng không chống CSRF phù hợp.

Vì vậy **không dùng điều kiện hiển thị nút** hay validation JavaScript làm hàng rào bảo mật. Chúng cải thiện trải nghiệm, còn mọi quyết định có ảnh hưởng nghiệp vụ phải được kiểm tra tại server.

### 3.2. Ranh giới 2 — Spring Security và Spring MVC

Security filter chain có thể xác định danh tính, duy trì security context, kiểm soát URL, áp dụng CSRF, thiết lập session policy và xử lý lỗi chưa đăng nhập hoặc bị từ chối. `DispatcherServlet` và Web Flow tiếp tục xử lý request đã qua tầng này.

**URL authorization** trả lời “có được truy cập endpoint flow không?” nhưng thường **không đủ** để trả lời “có được xác nhận bản nháp cụ thể không?”. Một đường dẫn như `/booking` có thể phục vụ cả việc nhập form lẫn event cuối cùng tạo giao dịch.

### 3.3. Ranh giới 3 — Web Flow execution và state

Web Flow biết **state hiện tại** và **những transition được định nghĩa**. Ví dụ event `confirm` gửi khi đang ở `details` không nên được xem như đang ở `review`. Tuy vậy, nếu transition `confirm` hợp lệ ở `review` thì điều đó chỉ cho biết hành trình **cho phép sự kiện**, không chứng minh người gửi có quyền tác động lên bản nháp hay dữ liệu vẫn còn hợp lệ.

### 3.4. Ranh giới 4 — service và database

Service quyết định **ai được phép làm gì trên bản ghi nào**, kiểm tra dữ liệu ở thời điểm commit và bao bọc transaction. Database cung cấp ràng buộc duy nhất, khóa/concurrency control hoặc optimistic locking tùy thiết kế.

Kiểm tra quyền sở hữu ở service giúp bảo vệ hành động dù nó được gọi từ **Web Flow, REST API, batch job hay một controller khác**. Chỉ dựa vào flow XML sẽ để ngỏ những đường gọi khác.

## 4. Xác thực: bảo vệ điểm vào và duy trì danh tính

**Xác thực** trả lời danh tính của principal. Trong ứng dụng Servlet dùng Spring Security, security filter chain thường xử lý đăng nhập và security context. Sau khi người dùng đăng nhập, Web Flow vẫn cần tích hợp đúng với request, session và cơ chế phục hồi flow execution.

Ví dụ cấu hình Spring Security theo phong cách **Spring Framework 6 / Spring Security 6**, giả định ứng dụng thực sự ánh xạ flow vào `/booking` hoặc `/booking/**`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/assets/**").permitAll()
                .requestMatchers("/booking", "/booking/**").authenticated()
                .anyRequest().denyAll())
            .formLogin(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .build();
    }
}
~~~

Đây là **đoạn cấu hình mẫu**: cần đối chiếu URL thật, các endpoint logout/error/static assets, session policy và security configuration hiện có. Nếu ứng dụng có API, nhiều `SecurityFilterChain` hoặc đường dẫn flow khác, áp dụng chính sách theo đúng request matcher và thứ tự chain; không ghép máy móc đoạn mẫu vào production. Cú pháp và module Spring Security thay đổi theo thế hệ Spring; mã này không dành trực tiếp cho Spring Security cấu hình `WebSecurityConfigurerAdapter` cũ.

Điểm cần hiểu:

- `authenticated()` buộc request khớp đường dẫn phải có principal đã xác thực.
- `csrf(Customizer.withDefaults())` giữ bảo vệ CSRF theo cấu hình mặc định; **form POST phải gửi token hợp lệ**.
- URL bắt đầu một flow và URL tiếp tục flow execution có thể khác nhau tùy mapping. Cần kiểm tra **cả hai**, kể cả URL sau redirect.
- Luồng đăng nhập thành công **không cấp quyền tự động** đối với mọi bản nháp đặt lịch.

### 4.1. Khi session hoặc trạng thái đăng nhập thay đổi

Một flow đang dở có thể gặp logout, session timeout, đổi tài khoản hoặc quy tắc phân quyền thay đổi giữa các bước. Vì vậy:

1. Khi tiếp tục flow, server phải nhận diện đúng principal theo session/security context hiện tại.
2. Quyền trên bản ghi phải được kiểm tra **lại ở thao tác nhạy cảm**, đặc biệt tại `confirm`.
3. Nếu không còn xác thực hoặc không còn quyền, tránh tiết lộ bản nháp; điều hướng về nơi đăng nhập/khởi tạo lại phù hợp.
4. Không coi việc đã vượt qua bước xác thực ở đầu flow là giấy phép cố định cho toàn bộ thời gian sống của flow.

Không lưu mật khẩu, access token, private key hay dữ liệu xác thực nhạy cảm vào `flowScope`, hidden field hoặc flow execution URL. Những scope đó phục vụ trạng thái hành trình, không phải kho bí mật.

## 5. Phân quyền: flow/state là kiểm soát bổ sung, service là chốt cuối

Có **ba cấp độ** phân quyền thường cần phối hợp:

| Cấp | Ví dụ | Điểm hạn chế nếu dùng một mình |
| --- | --- | --- |
| **URL/entry** | Chỉ tài khoản đăng nhập được mở `/booking` | Không xác định bản nháp của ai |
| **Flow/state/transition** | Chỉ vai trò `ROLE_RECEPTIONIST` được vào state quản trị | Không tự giải quyết quyền ở mức từng bản ghi |
| **Service/object** | Chỉ chủ bản nháp hoặc nhân viên được phân công mới được xác nhận | Cần thiết kế và thực thi đầy đủ chính sách nghiệp vụ |

### 5.1. Phân quyền khai báo trong Web Flow

Spring Web Flow có hỗ trợ khai báo security constraint ở mức **flow/state** thông qua phần tử `<secured>` khi dùng tích hợp Spring Security và listener tương ứng. Ví dụ minh họa:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow">
    <secured attributes="ROLE_USER"/>

    <view-state id="details" view="booking/details">
        <transition on="next" to="review"/>
    </view-state>
    <view-state id="review" view="booking/review">
        <transition on="back" to="details"/>
        <transition on="confirm" to="done"/>
    </view-state>
    <end-state id="done" view="booking/done"/>
</flow>
~~~

Đoạn XML chỉ minh họa **khai báo yêu cầu vai trò**; để nó thực sự có tác dụng, ứng dụng phải cấu hình đúng integration Spring Security của SWF, chẳng hạn `SecurityFlowExecutionListener`, theo **reference của phiên bản đang sử dụng**. Không xem một thẻ `<secured>` đặt trong XML là bằng chứng bảo mật đã được kích hoạt.

Security attributes/roles như `ROLE_USER` mô tả chính sách chung. Với quyền cấp theo **bookingId cụ thể**, phải xác minh ở service; không cố nhồi mọi điều kiện sở hữu bản ghi vào logic ẩn/hiện màn hình.

### 5.2. Phân quyền theo đối tượng và quyền nghiệp vụ

Ví dụ một service chỉ cho tài khoản có authority phù hợp xác nhận bản nháp của mình:

~~~java
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookingService {
    private final BookingRepository bookingRepository;

    public BookingService(BookingRepository bookingRepository) {
        this.bookingRepository = bookingRepository;
    }

    @PreAuthorize("hasAuthority('BOOKING_CONFIRM')")
    @Transactional
    public void confirm(long bookingId, Authentication authentication) {
        BookingDraft draft = bookingRepository.findByIdForUpdate(bookingId)
            .orElseThrow(() -> new AccessDeniedException("Không được truy cập bản nháp"));

        if (!draft.getOwnerUsername().equals(authentication.getName())) {
            throw new AccessDeniedException("Không có quyền xác nhận bản nháp");
        }

        if (!draft.isReadyForConfirmation()) {
            throw new IllegalStateException("Bản nháp chưa đủ điều kiện");
        }

        // Kiểm tra slot còn trống, ràng buộc trùng lặp và lưu trong transaction.
        draft.confirm();
        bookingRepository.save(draft);
    }
}
~~~

Đoạn mã **minh họa ranh giới bảo mật**, không phải lớp có thể biên dịch độc lập: `BookingRepository`, `BookingDraft`, repository locking và kiểm tra slot phải do ứng dụng cung cấp. `@PreAuthorize` chỉ hoạt động nếu method security được bật (ví dụ `@EnableMethodSecurity` ở cấu hình phù hợp) và lời gọi đi qua cơ chế proxy/interception của Spring; lời gọi nội bộ cùng bean có thể không đi qua proxy. Với request HTTP, lấy `Authentication` đáng tin cậy từ Spring Security, **không** từ form field `username` do client cung cấp.

Thiết kế production thường thêm kiểm soát cạnh tranh, transaction isolation, idempotency và constraint ở database. Việc dùng `findByIdForUpdate` chỉ là một chiến lược; nếu chọn optimistic locking bằng `@Version`, cách xử lý xung đột sẽ khác.

### 5.3. Check quyền ở đâu khi nhiều transition dùng chung service?

Giả sử có cả:

- flow dành cho khách: `confirm` bản nháp của chính họ;
- flow dành cho nhân viên: `approve` bản nháp được phân công;
- API nội bộ thực hiện thao tác tương tự.

Mỗi hành động phải có **quy tắc quyền tương ứng tại service**, không mặc định vì một flow gọi vào service nghĩa là đã được cấp phép. Người có quyền `BOOKING_CONFIRM` chưa chắc có `BOOKING_APPROVE`; chủ sở hữu bản nháp không nhất thiết có quyền thao tác trên mọi trạng thái hồ sơ.

Nguyên tắc **deny by default**: đường không có chính sách hợp lệ phải bị từ chối; kiểm tra quyền càng sát hành động ghi càng khó bị bỏ sót do thay đổi giao diện.

## 6. Ranh giới dữ liệu: binding không phải validation

Trong form nhiều bước, trình duyệt có thể gửi:

~~~http
POST /booking?execution=e1s2 HTTP/1.1
Content-Type: application/x-www-form-urlencoded

_eventId=next&phone=0900000000&ownerId=another-user&price=0
~~~

`ownerId` và `price` có thể chưa bao giờ xuất hiện trên giao diện nhưng người gửi vẫn thêm được vào request. Nếu model binder ghi tự động mọi thuộc tính, dữ liệu bất hợp pháp có thể chui vào bản nháp.

### 6.1. Khai báo danh sách field được phép bind

Trong Web Flow, phần tử `<binder>` cho phép khai báo các property được nhận từ request tại một `view-state`:

~~~xml
<view-state id="details" view="booking/details" model="bookingForm">
    <binder>
        <binding property="phone" required="true"/>
        <binding property="appointmentDate" required="true"/>
        <binding property="note"/>
    </binder>

    <transition on="next" to="review"/>
</view-state>
~~~

Đây là một **đoạn flow**; class `BookingForm` và validator phải được định nghĩa trong ứng dụng. Danh sách trên dự kiến chỉ tiếp nhận `phone`, `appointmentDate` và `note`; các trường `ownerId`, `price`, `status`, `role` hay `approvedBy` **không thuộc input có thể sửa**. Luôn kiểm chứng cách binder, converter và validation xử lý field không hợp lệ với phiên bản SWF đang dùng.

Một hướng thiết kế tốt là tách:

- **Form object**: chỉ gồm dữ liệu client được phép khai báo.
- **Flow draft / domain object**: chứa trạng thái nghiệp vụ server kiểm soát.
- **Entity/database record**: chứa owner, price, status và version được quyết định ở server.

Không gắn trực tiếp entity có trường đặc quyền làm model bind tự động rồi trông chờ validation phát hiện mọi thay đổi. **Mass assignment** xảy ra trước cả khi kiểm tra business rule nếu cho phép binding quá rộng.

### 6.2. Validation theo từng state và trước khi commit

Có thể đặt các mức:

| Lớp kiểm tra | Kiểm tra gì? | Ví dụ |
| --- | --- | --- |
| Client-side UX | Gợi ý nhanh về field | Nhắc nhập số điện thoại |
| Binding/conversion | Chuỗi thành ngày, số, enum; property được phép | `appointmentDate` đúng kiểu |
| Field/Bean Validation | Định dạng, bắt buộc, độ dài, phạm vi | `phone` đúng pattern, ghi chú không quá dài |
| Cross-field validation | Các field có quan hệ logic | Ngày hẹn nằm trong khoảng cho phép |
| Domain/service validation | Quy tắc nghiệp vụ, quyền, trạng thái mới nhất | Slot còn trống, thuộc đúng chủ sở hữu |
| Database constraints | Ngăn dữ liệu không nhất quán khi cạnh tranh | Unique/index/check/locking |

Một form ở bước `details` có thể hợp lệ lúc nhấn `next`, nhưng lịch hẹn đã bị đặt bởi người khác khi tới `review`. Vì vậy phải **kiểm tra lại điều kiện nghiệp vụ ngay trước khi xác nhận**, trong transaction phù hợp.

Với Web Flow, cơ chế gọi validator và thời điểm validation phụ thuộc `view-state`, model và cấu hình transition; các tùy chọn bỏ qua validation phải được kiểm tra đặc biệt ở transition nhạy cảm. Không xem việc chuyển tới `review` là chứng chỉ dữ liệu đã được xác thực cho mọi bước về sau.

### 6.3. Lỗi validation không nên rò dữ liệu nhạy cảm

Thông báo như “Thông tin chưa hợp lệ” và lỗi theo field là phù hợp cho người dùng. Không đưa stack trace, câu SQL, token, chi tiết policy nội bộ hoặc dữ liệu thuộc tài khoản khác ra view. Mã lỗi phía server có thể được log bằng correlation ID, nhưng tránh ghi nguyên session ID, token hoặc toàn bộ body chứa dữ liệu cá nhân.

## 7. Sự kiện điều hướng không phải lệnh được tin tưởng

Web Flow nhận event để chọn transition. Một form có thể gửi:

~~~html
<form method="post" action="/booking?execution=e1s2">
  <!-- Thêm CSRF token theo cơ chế Spring Security/view rendering của dự án -->
  <input name="phone" value="0900000000">
  <button type="submit" name="_eventId_next">Tiếp tục</button>
</form>
~~~

Tên tham số event nêu trên là **mẫu thường gặp của Web Flow**, nhưng URL, flow execution key và cách render CSRF token phải theo tích hợp MVC/view thực tế. Đoạn HTML chưa hoàn chỉnh để triển khai production.

### 7.1. Client có thể tự gửi event

Kẻ gửi request có thể thay `_eventId=next` bằng `_eventId=confirm` hoặc gửi một event hợp lệ mà nút đã bị ẩn. Engine phải chỉ thực hiện **transition được định nghĩa cho state hiện tại**; song với transition hợp lệ, **action phía server vẫn cần authorization và validation**.

Ví dụ:

~~~mermaid
flowchart TD
    R["POST event confirm"] --> S{"State hiện tại có transition confirm?"}
    S -->|"Không"| X["Xử lý event không hợp lệ / lỗi theo cấu hình"]
    S -->|"Có"| A{"Principal có quyền trên bookingId?"}
    A -->|"Không"| D["Access denied; không thay đổi nghiệp vụ"]
    A -->|"Có"| V{"Dữ liệu và trạng thái còn hợp lệ?"}
    V -->|"Không"| E["Thông báo lỗi an toàn / quay về review"]
    V -->|"Có"| T["Commit một lần trong transaction"]
~~~

Hệ thống không cho client chỉ định state đích tùy ý. Tuy nhiên policy bảo mật vẫn phải được kiểm tra tại những action có hiệu ứng, ngay cả khi state graph đã định nghĩa đầy đủ.

### 7.2. `execution` và cookie phiên không phải bằng chứng phân quyền

Một số cấu hình SWF dùng execution key trong URL để tìm flow execution hoặc snapshot. Giá trị như `execution=e1s2` giúp server xác định ngữ cảnh tiếp tục, **không chứng minh quyền sở hữu dữ liệu**. Session ID xác định phiên HTTP; security context xác định danh tính theo cấu hình; service vẫn phải xác định quyền trên booking ID.

Do execution key và URL có thể xuất hiện trong browser history, Referer hoặc log, tránh đặt secret, dữ liệu cá nhân hay access token trong chúng. Nếu triển khai có nhiều node, phải kiểm tra chính sách repository, session replication/sticky routing và timeout để flow không bị phục hồi sai.

## 8. CSRF, XSS và phương thức HTTP

### 8.1. CSRF là vấn đề khác với authentication

Một người dùng đã đăng nhập vẫn có thể bị website khác kích hoạt một request thay đổi trạng thái nếu trình duyệt tự đính cookie phiên vào request và server không có biện pháp chống CSRF thích hợp.

Đối với flow sử dụng **session cookie và form POST**:

1. Bật CSRF protection của Spring Security cho các request thay đổi trạng thái.
2. Đảm bảo **tất cả form POST trong các view-state** gửi token hợp lệ. Tùy view engine, token có thể được tự chèn bởi integration hoặc cần khai báo rõ.
3. Kiểm tra transition POST, Ajax/fragment request và endpoint phụ có gửi token đúng cách.
4. Không chuyển hành động ghi sang GET để né vấn đề token.
5. Cấu hình cookie phù hợp (`Secure`, `HttpOnly`, `SameSite`) và HTTPS; `SameSite` hỗ trợ giảm rủi ro nhưng không thay thế chính sách CSRF đầy đủ.

Nếu ứng dụng có API stateless với mô hình xác thực khác, thiết kế CSRF phải được đánh giá dựa trên **cách trình duyệt gửi thông tin xác thực**, không chỉ dựa trên tên API.

### 8.2. XSS trong view có thể phá nhiều hàng rào bảo vệ

Dữ liệu form có thể được hiển thị lại ở trang review. Nếu template in raw HTML từ field người dùng, nội dung độc hại có thể chạy trong origin của ứng dụng, làm suy yếu cả CSRF protection và session safety.

- Escape/encode output theo context HTML, attribute, JavaScript hoặc URL; không nối chuỗi người dùng vào JavaScript không kiểm soát.
- Ưu tiên template engine mặc định escape, tránh dùng các biểu thức render HTML thô cho dữ liệu người dùng.
- Cân nhắc CSP và giới hạn thông tin nhạy cảm trên view.
- Validation input là hữu ích nhưng **không thay thế output encoding**.

### 8.3. GET chỉ nên đọc

Truy cập `GET /booking` có thể khởi tạo flow hoặc hiển thị state. Không dùng GET để xác nhận giao dịch, xóa dữ liệu, gửi email hoặc thực hiện thao tác có tác dụng phụ nghiệp vụ. Browser history, preview bot, cache và link prefetch có thể kích hoạt GET ngoài mong đợi.

## 9. Scope và session: dữ liệu sống lâu không làm tăng độ tin cậy

Web Flow có `requestScope`, `flashScope`, `viewScope`, `flowScope`, `conversationScope`, và có thể truy cập `sessionScope` trong cấu hình phù hợp. **Vòng đời dài hơn chỉ có nghĩa dữ liệu được giữ lại lâu hơn**, không chứng minh dữ liệu đúng hay có quyền.

| Nơi giữ dữ liệu | Ví dụ phù hợp | Rủi ro nếu dùng sai |
| --- | --- | --- |
| `requestScope` | Giá trị tạm của một request | Nhầm tưởng request sau còn giữ |
| `flashScope` | Thông báo trong quá trình chuyển bước | Đưa bí mật vào thông báo/view |
| `viewScope` | Dữ liệu phục vụ view-state | Gắn quyền dài hạn vào state hiển thị |
| `flowScope` | Bản nháp một execution | Xem dữ liệu cached là đã được ủy quyền vĩnh viễn |
| `conversationScope` | Ngữ cảnh chung của flow cha và subflow | Rò/chia sẻ dữ liệu quá rộng giữa subflow |
| `sessionScope` / `HttpSession` | Thông tin thuộc cả phiên thực sự cần thiết | Dùng chung qua nhiều flow/tab, phình bộ nhớ, dữ liệu cũ |
| Database | Lịch hẹn đã xác nhận, owner và version | Thiếu transaction, constraint và phân quyền truy vấn |

### 9.1. Tình huống đổi tài khoản khi flow chưa kết thúc

Giả sử người A mở bản nháp #42, logout rồi người B đăng nhập trên cùng trình duyệt. Một execution còn tồn tại không thể là cơ sở cho B xác nhận bản nháp A.

Điểm kiểm tra:

1. Security context hiện tại là ai?
2. Bản nháp #42 thuộc ai và đang ở trạng thái nào?
3. Có quyền tiếp tục, xem lại hoặc xác nhận trên bản nháp đó không?
4. Khi không đủ quyền, ứng dụng có chặn hành động và không render thông tin A cho B không?

Cần bảo đảm cơ chế session fixation protection, logout invalidation và security context lifecycle được cấu hình đúng ở Spring Security. Không tự tạo cơ chế “đã đăng nhập” bằng cách lưu chuỗi username vào `flowScope` rồi tin chuỗi đó ở bước cuối.

### 9.2. Nhiều tab và cạnh tranh dữ liệu

Một HTTP session có thể chứa nhiều execution hoặc nhiều tab cùng tham gia một execution. Người dùng có thể xác nhận hai lần hoặc quay lại snapshot cũ. Vì vậy:

- Dùng **idempotency key**, unique constraint hoặc cơ chế nghiệp vụ tương ứng để ngăn xử lý lặp.
- Dùng **optimistic locking**/phiên bản bản ghi hoặc khóa transaction để phát hiện thay đổi cạnh tranh.
- Không coi xử lý request trên cùng session là tuần tự/atomic.
- Nếu flow execution hoặc snapshot đã hết hạn, trả thông báo phù hợp; không cố gắng tái sử dụng dữ liệu cũ để commit.

Trong hệ thống phân tán, cần kiểm tra session repository và flow execution repository có hoạt động đúng khi request chuyển node hay không. Session store chia sẻ không thay thế authorization theo đối tượng.

## 10. Subflow và các nhánh lỗi cũng cần bảo vệ

Subflow cho phép tái sử dụng một hành trình nhỏ trong flow lớn, ví dụ xác minh danh tính hoặc chọn phương thức thanh toán. Input của subflow có thể đến từ flow cha, nhưng **nguồn gốc từ một flow khác không làm dữ liệu tự an toàn**.

Ví dụ conceptual:

~~~mermaid
flowchart LR
    A["Main flow: review"] -->|"bookingId"| B["Subflow: verifyIdentity"]
    B -->|"verified event"| C["Main flow: confirm"]
    C --> D["Service: recheck owner + allowed action"]
    D --> E["Database"]
~~~

Phải kiểm tra:

- **Input boundary:** subflow chỉ nhận input cần thiết; tham số như `bookingId` phải được kiểm tra nguồn và quyền sở hữu.
- **Event/output boundary:** event `verified` từ subflow mô tả một kết quả, không tự cấp quyền vô hạn cho các service khác.
- **Permission changes:** quyền và dữ liệu có thể đổi giữa lúc subflow bắt đầu và kết thúc.
- **Exception/recovery:** khi service bị từ chối quyền hoặc bản ghi không còn hợp lệ, không được chuyển bừa sang end-state thành công.
- **Data isolation:** tránh để thông tin của một subflow trong `conversationScope` nếu các nhánh khác không cần đọc.

Các exception như `AccessDeniedException` và lỗi nghiệp vụ cần được xử lý theo đúng chính sách. Không cố ý bắt mọi exception rồi trả event `success`; việc đó che mất lỗi bảo mật hoặc làm người dùng tưởng giao dịch đã hoàn tất.

## 11. Ví dụ kết nối flow với service bảo mật

Giả sử `bookingId` là định danh server tạo và được gắn với principal đã xác thực. Một flow có thể chứa đoạn chuyển:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow">
    <input name="bookingId" required="true"/>

    <view-state id="review" view="booking/review">
        <transition on="back" to="details"/>
        <transition on="confirm" to="done">
            <evaluate expression="bookingService.confirm(bookingId, currentUser)"/>
        </transition>
    </view-state>

    <end-state id="done" view="booking/done"/>
</flow>
~~~

Đoạn XML này là **minh họa ý định điều phối**, không phải một flow chạy độc lập. `currentUser` phải do tích hợp bảo mật phía server cung cấp, không phải biến tự khai từ hidden field; class/bean, input mapping, view, exception handling và trạng thái `details` phải được định nghĩa ở flow thực tế. Khi triển khai, tránh lấy principal từ tham số request: service có thể truy cập authentication qua Spring Security hoặc nhận đối tượng principal được Spring resolve đáng tin cậy.

Một phương án khác là chỉ truyền `bookingId` vào service rồi service xác định principal từ `SecurityContextHolder` trong ngữ cảnh request:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

if (authentication == null || !authentication.isAuthenticated()) {
    throw new org.springframework.security.access.AccessDeniedException(
        "Yêu cầu đăng nhập");
}

// Service tiếp tục kiểm tra authority, owner, trạng thái và transaction.
~~~

Đây là đoạn mã tham khảo nằm **bên trong phương thức service**, không phải đoạn class hoàn chỉnh. Nếu sử dụng cơ chế authentication đặc biệt như anonymous, phải áp dụng policy nhận diện principal phù hợp thay vì chỉ dựa vào `isAuthenticated()`.

### 11.1. Trình tự xác nhận an toàn

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant HTTP as Security Filter
    participant Flow as Web Flow
    participant Svc as BookingService
    participant DB as Database
    User->>HTTP: POST confirm + CSRF token + cookie
    HTTP->>HTTP: Xác thực + kiểm tra CSRF
    HTTP->>Flow: Request được phép đi tiếp
    Flow->>Flow: Đối chiếu execution/state/transition
    Flow->>Svc: confirm(bookingId) với security context
    Svc->>Svc: Kiểm tra authority, owner, trạng thái
    Svc->>DB: Giao dịch + constraint / locking
    DB-->>Svc: Commit hoặc conflict
    Svc-->>Flow: Thành công hoặc lỗi có kiểm soát
    Flow-->>User: View kết quả tương ứng
~~~

Nếu người dùng không có quyền, service phải dừng **trước khi ghi**. Nếu dữ liệu không còn hợp lệ, flow cần hiển thị lỗi và hướng phục hồi theo chính sách. Nếu commit đã thành công mà browser gửi request lại, service phải tránh tạo bản ghi thứ hai.

## 12. Ma trận đe dọa và biện pháp kiểm soát

| Đe dọa / sai sót | Ranh giới bị tác động | Biện pháp chính | Kiểm thử quan trọng |
| --- | --- | --- | --- |
| Chưa đăng nhập vẫn mở flow | HTTP/Spring Security | Route authentication; deny by default | GET/POST chưa login bị chặn |
| Người A mở `bookingId` của B | Service/object authorization | Kiểm tra owner và authority trên server | Thay ID vẫn nhận 403/404 theo policy, không rò nội dung |
| Gửi event `confirm` khi nút bị ẩn | Flow và service | State transition + reauthorization | Event trực tiếp không bypass permission |
| Gửi `price=0` / `role=ADMIN` | Binder/domain | Whitelist field; server tính field đặc quyền | Field lạ không sửa dữ liệu |
| Form thiếu/sai dữ liệu | Validation | Converter, field/cross-field validation | Hiện lỗi, không commit |
| Slot bị người khác đặt trước commit | Service/database | Kiểm tra lại trong transaction, locking/constraint | Cạnh tranh đồng thời được xử lý |
| Gửi POST từ website khác | CSRF boundary | CSRF token hợp lệ; cookie/security phù hợp | Thiếu hoặc sai token bị chặn |
| Script trong ghi chú người dùng | View/XSS | Output encoding theo context, CSP nếu phù hợp | Review không chạy HTML/JS nhập vào |
| Refresh/submit hai lần | Service/database | Idempotency, unique constraint | Chỉ một tác dụng nghiệp vụ |
| Session hết hạn giữa flow | Security/session/repository | Xử lý execution không còn hợp lệ | Không lộ dữ liệu; có đường bắt đầu lại |
| Subflow nhận input giả | Subflow/service | Validate input, kiểm tra quyền theo đối tượng | Input không thuộc phiên bị từ chối |
| Error handler coi lỗi là thành công | Flow/error handling | Phân loại lỗi, giữ transaction semantics | Exception không tạo end-state success |
| Log session ID và token | Observability | Mask/loại secret khỏi log | Log không chứa credential |

## 13. Kịch bản kiểm thử bảo mật thực hành

### 13.1. Bộ dữ liệu thử

Chuẩn bị trong môi trường test:

- **User A** có authority `BOOKING_CONFIRM`, sở hữu bản nháp `draft-A`.
- **User B** có cùng authority, chỉ sở hữu `draft-B`.
- **User C** đã đăng nhập nhưng không có authority xác nhận.
- **Anonymous** chưa đăng nhập.
- Một slot lịch có thể bị chiếm bởi transaction song song.

Không dùng tài khoản thật hoặc dữ liệu khách hàng thật trong kiểm thử.

### 13.2. Bảng test theo ranh giới

| Test | Tác động | Kỳ vọng |
| --- | --- | --- |
| T01 | Anonymous mở `/booking` | Không vào flow cần xác thực |
| T02 | User A mở `draft-A` | Có thể xem/chỉnh trong quyền được cấp |
| T03 | User A thử mở `draft-B` bằng URL/input | Bị từ chối; không hiển thị chi tiết của B |
| T04 | User C gửi `confirm` cho bản nháp bất kỳ | Bị từ chối tại service |
| T05 | User A gửi event không thuộc state hiện tại | Không đi tới state cấm |
| T06 | User A sửa hidden field `ownerId` hoặc `price` | Binder không chấp nhận các thay đổi đặc quyền |
| T07 | User A gửi thiếu CSRF token | Request thay đổi trạng thái bị chặn |
| T08 | User A gửi form ngày hẹn không hợp lệ | Validation báo lỗi; service không commit |
| T09 | User A gửi hai POST confirm cùng dữ liệu | Không tạo hai giao dịch |
| T10 | Hai request cùng chiếm một slot | Chỉ một commit thành công hoặc kết quả phù hợp với business rule |
| T11 | User A logout, User B login rồi dùng URL execution cũ | Không thể thao tác bằng quyền/dữ liệu của A |
| T12 | Flow hết hạn trước `confirm` | Lỗi có kiểm soát, không commit, có thể bắt đầu lại |
| T13 | Subflow trả event `verified` giả/không hợp lệ | Không bypass kiểm tra nghiệp vụ cuối cùng |
| T14 | Ghi chú chứa HTML/JS rồi mở review | Nội dung được escape, không thực thi script |
| T15 | Service ném `AccessDeniedException` | Không bị chuyển thành thành công; không thay đổi dữ liệu |

### 13.3. Phân lớp kiểm thử

**Kiểm thử Spring Security/HTTP:** dùng `MockMvc` hoặc test tương đương để xác nhận filter chain, session/cookie, CSRF và route authorization. Kiểm tra request thật có chứa execution key và token đúng.

**Kiểm thử state machine:** dùng hạ tầng kiểm thử Web Flow (như `AbstractXmlFlowExecutionTests` trong những phiên bản có hỗ trợ) hoặc integration test phù hợp để xem event nào hợp lệ ở mỗi state, kiểm tra back/cancel và xử lý validation error. State test đơn lẻ không thay thế kiểm thử HTTP security.

**Kiểm thử service:** gọi service qua Spring context có method security hoặc đặt test cho policy kiểm tra owner/authority, transaction, optimistic locking và idempotency. Với `@PreAuthorize`, test phải đi qua proxy bảo mật để phản ánh runtime.

**Kiểm thử tích hợp:** chạy từ trình duyệt/HTTP qua filter → MVC → SWF → service/database trong môi trường test, thử nhiều tab, logout giữa chừng, session timeout và phục hồi sau lỗi. Đây là bước chứng minh các ranh giới hoạt động **cùng nhau**.

## 14. Tình huống phân tích: một flow có thể đúng điều hướng nhưng sai bảo mật

Giả sử flow chỉ định:

~~~xml
<view-state id="review" view="booking/review">
    <transition on="confirm" to="finished">
        <evaluate expression="bookingService.save(bookingDraft)"/>
    </transition>
</view-state>
~~~

Người dùng A mở bản nháp của B do ID được truyền vào flow. Các màn hình, state và transition đều chạy đúng; `save` vẫn có thể tác động lên dữ liệu của B nếu service không kiểm tra owner.

Hãy sửa thiết kế bằng cách phân công rõ:

1. Khi vào URL flow, **Spring Security** yêu cầu đăng nhập.
2. Khi nạp `bookingId`, **service** chỉ trả dữ liệu khi principal có quyền xem.
3. Tại `details`, **binder** chỉ nhận field khách hàng có quyền cập nhật.
4. Khi đi từ `details` sang `review`, **validation** kiểm tra dữ liệu hợp lệ để hiển thị.
5. Khi nhận event `confirm`, **service** kiểm tra lại principal, owner, version, slot, ràng buộc nghiệp vụ và thực hiện commit có kiểm soát trùng.
6. Khi hết session hoặc phát sinh lỗi, **Web Flow** trả về trạng thái/thông báo phục hồi an toàn; không tiết lộ dữ liệu và không tự bỏ qua xác thực.

Hành trình **đúng** và nghiệp vụ **được phép** là hai câu hỏi riêng. Cùng một transition có thể hợp lệ về state nhưng không được phép cho principal hiện tại.

## 15. Checklist khi review một flow có dữ liệu người dùng

- [ ] Xác định đường URL vào flow và URL tiếp tục execution; cả hai đi qua policy HTTP phù hợp.
- [ ] Spring Security xác thực principal và có cơ chế xử lý session/logout đúng.
- [ ] Mỗi action đọc/ghi bản ghi đều kiểm tra quyền **trên chính bản ghi đó**.
- [ ] Nếu dùng khai báo `<secured>`, đã xác minh integration/listener thực sự hoạt động.
- [ ] Không xem hidden field, execution key, event hoặc dữ liệu trong `flowScope` là bằng chứng cấp quyền.
- [ ] Model binder khai báo whitelist field; field nhạy cảm chỉ được server quyết định.
- [ ] Binding, field/cross-field validation và business validation có trách nhiệm riêng.
- [ ] Quy tắc nghiệp vụ được kiểm tra lại tại thời điểm commit trong transaction phù hợp.
- [ ] Request ghi được bảo vệ CSRF; GET không gây hiệu ứng nghiệp vụ.
- [ ] View escape dữ liệu người dùng; không render nội dung HTML/JS không tin cậy.
- [ ] Session, conversation scope, subflow không giữ hoặc tiết lộ dữ liệu quá rộng.
- [ ] Có chiến lược idempotency và xử lý cạnh tranh giữa các request.
- [ ] Event không hợp lệ, session timeout, quyền bị thu hồi và lỗi service đều được xử lý an toàn.
- [ ] Test HTTP, flow state, service và tích hợp đều có kịch bản bị từ chối.

## 16. Câu hỏi tự kiểm tra

**1. Xác thực thành công có chứng minh người dùng sở hữu bản nháp không?** Không. Danh tính chỉ trả lời “ai”; quyền sở hữu và quyền thao tác phải được kiểm tra riêng.

**2. Vì sao cần binding whitelist khi đã dùng `@Valid`?** `@Valid` kiểm tra tính hợp lệ của dữ liệu đã được bind; nó không tự giới hạn field nào client được phép thay đổi. Whitelist ngăn mass assignment ngay tại ranh giới nhận dữ liệu.

**3. Một event `confirm` có transition hợp lệ có được phép commit không?** Chỉ khi service đồng thời xác minh principal, authority/owner, trạng thái nghiệp vụ và điều kiện transaction.

**4. Vì sao kiểm tra quyền lúc mở flow chưa đủ?** Session, vai trò, owner và trạng thái dữ liệu có thể thay đổi trong lúc người dùng ở các bước tiếp theo; flow có thể còn mở trong nhiều tab.

**5. CSRF token có thay thế kiểm tra quyền trên `bookingId` không?** Không. Token chống request giả mạo từ origin khác trong mô hình dùng cookie; quyền đối tượng vẫn phải kiểm tra ở server.

**6. Khi người dùng nhập dữ liệu đúng tại `details`, có thể bỏ kiểm tra ở `confirm` không?** Không. Dữ liệu có thể lỗi thời hoặc quy tắc nghiệp vụ bị thay đổi do yêu cầu khác.

**7. Dữ liệu ở `flowScope` có đáng tin hơn form field không?** Scope giữ dữ liệu đã được thu thập/xử lý trong một execution, nhưng dữ liệu có thể bắt nguồn từ client, lỗi thời hoặc không còn phù hợp với principal hiện tại. Cần kiểm tra theo mục đích dùng.

**8. Vì sao cần test quyền ở cả flow và service?** Flow test chứng minh điều hướng đúng; service test chứng minh thao tác nghiệp vụ bảo vệ quyền sở hữu và transaction, kể cả qua những đường gọi khác.

## 17. Tài liệu đọc thêm

- [Spring Web Flow Reference Guide](https://docs.spring.io/spring-webflow/docs/3.0.2/reference/) — flow definition, execution, state, binding, validation, SecurityFlowExecutionListener và test.
- [Spring Security — Servlet Applications](https://docs.spring.io/spring-security/reference/servlet/) — authentication, authorization, session management và filter chain.
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html) — route authorization.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html) — bảo vệ request thay đổi trạng thái với cookie-based session.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html) — `@EnableMethodSecurity`, `@PreAuthorize` và proxy.
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) — phân quyền theo đối tượng và deny by default.
- [OWASP Mass Assignment Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html) — tránh bind field đặc quyền.
- [OWASP Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html) — encoding theo ngữ cảnh.

**Điểm cần nhớ:** **Spring Security** xác định danh tính và bảo vệ request; **Spring Web Flow** kiểm soát hành trình state/event/transition; **binder và validator** kiểm soát input; **service và database** bảo vệ quyền sở hữu, bất biến nghiệp vụ và tính nhất quán khi commit. Một flow an toàn phải thực thi đầy đủ các ranh giới đó cả khi người dùng bấm nút bình thường lẫn khi request bị chỉnh sửa, gửi lặp hoặc phục hồi từ phiên cũ.
