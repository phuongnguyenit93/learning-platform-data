# Impersonation banner — Dải thông báo khi thao tác dưới danh tính khác

## 1. Banner bảo vệ quyết định của người thao tác

Trong chương **Impersonation**, banner là dải thông báo giúp người dùng nhận biết họ đang ở chế độ thao tác theo ngữ cảnh của một tài khoản khác. Ví dụ, nhân viên hỗ trợ mở giao diện của khách hàng để điều tra lỗi.

Nếu giao diện chỉ đổi avatar thành khách hàng, nhân viên có thể quên chế độ hiện tại và thực hiện một hành động trên sai tài khoản. Nếu banner ghi “chỉ xem” nhưng API vẫn cho sửa dữ liệu, người dùng nhận được một lời hứa sai về phạm vi tác động.

Banner cần giúp trả lời ngay:

- Ai là người thực sự đang thao tác?
- Đang xem hoặc thao tác theo tài khoản nào, thuộc tenant nào?
- Phạm vi hiện tại là chỉ xem hay cho phép những thay đổi cụ thể?
- Chế độ còn hiệu lực tới khi nào?
- Làm thế nào để kết thúc và trở về ngữ cảnh của mình?
- Giao diện có đang chắc chắn về ngữ cảnh hiện tại không?

Banner là biện pháp giảm nhầm lẫn và hỗ trợ minh bạch. Quyền được phép thực hiện phải được server kiểm tra độc lập trên từng thao tác.

## 2. Phân biệt actor, tài khoản hiệu lực và phạm vi hỗ trợ

| Khái niệm | Ý nghĩa trong bài |
|---|---|
| Actor | Nhân viên hoặc chủ thể đã xác thực thực sự sử dụng hệ thống |
| Tài khoản hiệu lực | Tài khoản đích mà chế độ hỗ trợ đang mô phỏng ngữ cảnh |
| Tenant hiệu lực | Không gian dữ liệu được server cho phép sử dụng trong chế độ đó |
| Phiên impersonation | Bản ghi có vòng đời và điều kiện cho phép chế độ hỗ trợ |
| Phạm vi hành động | Các action và tài nguyên được phép trong phiên |
| Ngữ cảnh thao tác | Tổ hợp actor, tài khoản đích, tenant, chế độ và phiên bản hiện tại |

Không làm mất actor bằng cách chỉ lưu tài khoản đích trong security context hoặc audit.

Cũng không cộng toàn bộ quyền quản trị của nhân viên với toàn bộ quyền của khách hàng. Quyền hỗ trợ phải được chính sách xác định, gắn với đối tượng và mục đích được cho phép.

OWASP khuyến nghị kiểm tra quyền trên mỗi yêu cầu và mặc định từ chối khi không có căn cứ cho phép. Banner và nút bị ẩn không thay thế các kiểm tra đó. [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)

### 2.1. Không gọi mọi trường hợp là “đăng nhập thành khách hàng”

Cách diễn đạt này có thể làm người dùng hiểu rằng họ có toàn bộ quyền của khách hàng hoặc hành động sẽ được ghi như chính khách hàng thực hiện.

Trong bài, dùng “chế độ hỗ trợ” và hiển thị riêng actor, tài khoản đích. Tổ chức có thể dùng thuật ngữ khác, nhưng cần giải thích đúng khả năng của chế độ.

Không hiển thị một nhãn phạm vi rộng hơn hoặc hẹp hơn chính sách thực tế.

## 3. Nội dung tối thiểu của banner

### 3.1. Ví dụ cho phiên chỉ xem

~~~text
CHẾ ĐỘ HỖ TRỢ ĐANG BẬT

Người thao tác: Phương — nhân viên hỗ trợ SUP-17
Tài khoản đang hỗ trợ: Lan — KH-4821
Đơn vị: Cửa hàng Minh An — TEN-204
Phạm vi: Chỉ xem đơn hàng trong yêu cầu hỗ trợ này
Hết hiệu lực: 16:30 ngày 22/11/2026, giờ Việt Nam

[Kết thúc chế độ hỗ trợ]
~~~

Các tên và mã là dữ liệu giả định. Mã ngắn giúp phân biệt tài khoản trùng tên, nhưng vẫn chỉ hiển thị dữ liệu mà người hỗ trợ được phép biết.

Không cần đưa token, session ID bí mật, email đầy đủ hoặc thông tin cá nhân không liên quan vào banner.

### 3.2. Bảng nội dung và mục đích

| Thành phần | Mục đích |
|---|---|
| Nhãn chế độ rõ ràng | Phân biệt với sử dụng tài khoản bình thường |
| Người thao tác | Giữ nhận thức về actor thực |
| Tài khoản đích và dấu hiệu nhận diện | Tránh nhầm giữa khách hàng trùng tên |
| Tenant hoặc đơn vị | Tránh thao tác nhầm không gian dữ liệu |
| Phạm vi ngắn gọn | Cho biết có thể tạo tác động gì |
| Thời điểm kết thúc | Tránh kỳ vọng chế độ tồn tại vô hạn |
| Nút kết thúc | Cung cấp đường trở về rõ ràng |
| Trạng thái đang xác minh hoặc đang kết thúc | Không trình bày sự chắc chắn khi chưa có xác nhận |

Không chỉ ghi “Bạn đang mạo danh người dùng”. Thông báo đó không cho biết người dùng nào hoặc có thể làm gì.

Nếu cho phép một số thay đổi, có thể ghi:

~~~text
Phạm vi: Xem đơn hàng và cập nhật ghi chú hỗ trợ.
Không bao gồm hoàn tiền, đổi tài khoản nhận hoặc thay quyền truy cập.
~~~

Danh sách này phải đến từ hợp đồng chính sách của sản phẩm, không phải một đoạn chữ cố định được giữ nguyên khi quyền đã thay đổi.

### 3.3. Nội dung không được phụ thuộc dữ liệu tự khai

Không dựng danh tính đích từ query string như `?impersonateUser=...` rồi coi đó là trạng thái hiện hành.

Server phải xác định phiên có thật, actor nào được phép sử dụng, tài khoản đích và tenant nào liên quan. Banner dùng bản mô tả được server trả về từ ngữ cảnh đã xác thực.

Tên hiển thị có thể do người dùng sửa. Dùng cách render an toàn và kết hợp mã nhận diện ổn định phù hợp, thay vì để một tên như “Quản trị viên — chế độ bình thường” đánh tráo nhãn do hệ thống cung cấp.

## 4. Banner phải có mặt trong suốt ngữ cảnh thao tác

### 4.1. Hiển thị bền vững, không chỉ là thông báo thoáng qua

Một toast biến mất sau vài giây không đủ để nhắc người dùng về chế độ còn kéo dài nhiều phút.

Đặt banner ở lớp giao diện chung để nó được giữ khi:

- Chuyển route hoặc mở trang con.
- Cuộn trang dài.
- Mở biểu mẫu, bảng chi tiết hoặc một vùng làm việc khác.
- Dùng kích thước màn hình nhỏ hoặc phóng to chữ.
- Quay lại từ trang trước hoặc khôi phục một tab.

Không cung cấp nút đóng chỉ làm ẩn banner trong khi phiên hỗ trợ vẫn hoạt động. Nút kết thúc phải kết thúc ngữ cảnh phía server theo hợp đồng.

Một bản hiển thị gọn trên thiết bị nhỏ vẫn cần giữ nhận diện chế độ, tài khoản/tenant đủ phân biệt và đường kết thúc. Không cắt mất tên đích rồi chỉ còn một màu nền.

### 4.2. Modal và thao tác quan trọng phải giữ được nhận thức ngữ cảnh

Banner có thể bị che bởi modal hoặc không nằm trong phần mà trình đọc màn hình đang tương tác. Với hộp thoại quan trọng, nhắc lại tài khoản đích, tenant và phạm vi có liên quan ở nội dung xác nhận.

Ví dụ:

~~~text
Bạn đang hỗ trợ KH-4821 tại TEN-204.
Thao tác này cập nhật ghi chú đơn hàng của tài khoản đó.
~~~

Lời nhắc không cấp thêm quyền. Nếu chính sách chỉ cho xem, endpoint ghi chú phải từ chối dù người dùng gọi trực tiếp.

Không yêu cầu người dùng xác nhận lại mọi lần đọc dữ liệu. Mức nhắc cần phù hợp với tác động và không làm thông báo mất giá trị vì xuất hiện liên tục.

### 4.3. Màu sắc không phải thông tin duy nhất

Dùng nhãn chữ rõ ràng, kết cấu và ký hiệu khi phù hợp. Không dựa riêng vào nền vàng/đỏ để thể hiện chế độ.

WCAG giải thích rằng màu không được là phương tiện thị giác duy nhất để truyền đạt thông tin hoặc phân biệt hành động. [W3C — Use of Color](https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html)

Kiểm tra độ tương phản, khả năng xuống dòng và focus bàn phím trong giao diện thực tế. Chỉ đặt một màu cảnh báo chưa chứng minh thành phần có thể sử dụng được.

## 5. Hợp đồng ngữ cảnh từ server

### 5.1. Mẫu phản hồi để dựng banner

~~~json
{
  "mode": "IMPERSONATING",
  "contextRef": "acting-context-example",
  "revision": 18,
  "actor": {
    "reference": "SUP-17",
    "displayName": "Phương"
  },
  "effectiveUser": {
    "reference": "KH-4821",
    "displayName": "Lan"
  },
  "tenant": {
    "reference": "TEN-204",
    "displayName": "Cửa hàng Minh An"
  },
  "accessLabel": "Chỉ xem đơn hàng trong yêu cầu hỗ trợ này",
  "expiresAt": "2026-11-22T09:30:00Z",
  "policyVersion": "support-read-orders-v3"
}
~~~

Đây là hợp đồng minh họa, không phải schema bắt buộc của một chuẩn impersonation.

`contextRef` là tham chiếu không phải bí mật, dùng nhận diện ngữ cảnh mà giao diện đang hiển thị. Nó không phải access token và không tự cấp quyền.

`revision` thay đổi theo quy tắc phía server khi ngữ cảnh hoặc điều kiện cần đồng bộ thay đổi. Tham chiếu và phiên bản phải được ràng buộc với phiên đã xác thực.

Phản hồi riêng theo phiên cần chính sách cache phù hợp; ví dụ dùng `Cache-Control: no-store` và kiểm tra proxy/CDN không chia sẻ dữ liệu giữa các phiên.

### 5.2. Chưa xác minh không được hiển thị như chế độ bình thường

Khi ứng dụng khởi động hoặc tải lại:

~~~text
Đang xác minh ngữ cảnh
    -> server xác nhận NORMAL: mở vùng làm việc bình thường
    -> server xác nhận IMPERSONATING: dựng banner và đúng vùng làm việc
    -> không xác minh được: giữ trạng thái chưa rõ và khóa thao tác cần ngữ cảnh
~~~

Không dùng lỗi fetch hoặc trường bị thiếu làm lý do mặc định `mode=NORMAL`. Server có thể vẫn đang cho phiên hoạt động theo tài khoản đích.

Trong lúc chưa rõ, có thể hiện:

~~~text
Chưa xác minh được tài khoản đang thao tác.
Các thao tác trên dữ liệu đang tạm dừng. Hãy thử tải lại trạng thái.
~~~

Không tiếp tục tải dữ liệu nhạy cảm theo một giả định cũ. Giữ đường tải lại, kết thúc chế độ hoặc đăng nhập lại phù hợp với trạng thái xác thực thực tế.

### 5.3. Nhãn UI và quyền server dùng cùng một căn cứ

Nếu banner ghi “chỉ xem”, chính sách server phải chặn các action thay đổi tương ứng. Không chỉ vô hiệu hóa nút hoặc chặn mọi HTTP POST một cách máy móc: GraphQL có thể dùng POST cho truy vấn đọc, còn một endpoint GET thiết kế sai vẫn có thể gây tác dụng phụ.

Phân loại theo action nghiệp vụ. Kiểm tra cả API phụ, batch, import, WebSocket và các đường gọi khác.

Nếu không ánh xạ được chính sách thành nhãn đúng, đừng hiển thị một nhãn “chỉ xem” mặc định trong khi cho thao tác tiếp tục.

## 6. Nhiều tab và việc chuyển tài khoản

### 6.1. Một tình huống thao tác nhầm

~~~text
Tab A đang mở tài khoản KH-4821.
Tab B chuyển phiên hỗ trợ sang KH-9072.
Cookie dùng chung khiến server chuyển ngữ cảnh toàn phiên.
Tab A vẫn hiển thị banner KH-4821.
Người dùng gửi biểu mẫu từ tab A.
~~~

Nếu server âm thầm áp request đó cho KH-9072, giao diện và quyết định đã lệch nhau.

Cần chọn mô hình quản lý ngữ cảnh rõ ràng:

| Mô hình | Yêu cầu chính |
|---|---|
| Ngữ cảnh dùng chung toàn phiên trình duyệt | Mọi tab phải phát hiện thay đổi; request mang dấu hiệu ngữ cảnh đã được hiển thị |
| Ngữ cảnh riêng cho vùng làm việc hoặc tab | Server ràng buộc tham chiếu đúng phiên và actor; không tin tab ID tùy ý |
| Ngữ cảnh chỉ đọc tách biệt | Vẫn cần xác thực, giới hạn tài nguyên và xử lý hết hạn/thu hồi |

Không mặc định dùng `localStorage` để lưu token hoặc cờ chế độ chung rồi coi các tab đã đồng bộ an toàn.

### 6.2. Request phải gắn với ngữ cảnh người dùng đã thấy

Một cách bảo vệ sự nhất quán là gửi:

~~~http
X-Expected-Acting-Context: acting-context-example
X-Expected-Context-Revision: 18
~~~

Server lấy ngữ cảnh có thẩm quyền từ phiên đã xác thực và so sánh với giá trị mong đợi. Nếu không khớp, từ chối trước khi tạo tác động và yêu cầu tải lại ngữ cảnh.

Hai header trên là hợp đồng ứng dụng minh họa. Chúng không thay thế xác thực, kiểm tra quyền, CSRF hoặc kiểm tra đối tượng.

Việc so sánh hữu ích cả với request đọc dữ liệu: một tab cũ không nên nhận dữ liệu của tài khoản mới chỉ vì cookie đã thay đổi.

Không âm thầm bỏ kiểm tra khi header bị thiếu trên đường gọi cần ràng buộc ngữ cảnh. Cũng không cho client dùng header để tự chọn một tài khoản chưa được server cấp quyền.

### 6.3. Không tự gửi lại thao tác sang tài khoản mới

Khi phát hiện mismatch:

1. Dừng thao tác đang chuẩn bị.
2. Tải lại ngữ cảnh có thẩm quyền.
3. Loại dữ liệu/form cũ khỏi vùng có thể gửi nhầm.
4. Hiển thị rõ tài khoản và tenant hiện tại.
5. Yêu cầu người dùng bắt đầu lại ý định nếu nội dung vẫn phù hợp.

Không thay header bằng revision mới rồi tự retry một lệnh thay đổi. Người dùng đã nhập lệnh cho ngữ cảnh cũ.

Idempotency key cũng cần phạm vi nghiệp vụ rõ ràng. Không cho cùng key của tài khoản A trả nhầm kết quả của tài khoản B hoặc dùng việc đổi target để tạo thêm một tác dụng phụ cho cùng ý định đã cam kết.

## 7. Minh họa Java: chặn request có ngữ cảnh đã cũ

Đoạn mã Java 17+ chỉ minh họa kiểm tra tính khớp ngữ cảnh. `VerifiedContext` phải được tạo từ cơ chế xác thực và dữ liệu server, không bind từ body.

~~~java
import java.time.Instant;

final class ActingContextGuard {
    enum Mode { NORMAL, IMPERSONATING }

    record VerifiedContext(
            String contextRef,
            long revision,
            Mode mode,
            String actorId,
            String effectiveUserId,
            String tenantId,
            Instant impersonationExpiresAt) {}

    record ExpectedContext(String contextRef, long revision) {}

    static void requireExpectedContext(
            VerifiedContext actual,
            ExpectedContext expected,
            Instant decisionAt) {

        if (expected == null
                || !actual.contextRef().equals(expected.contextRef())
                || actual.revision() != expected.revision()) {
            throw new IllegalStateException("ACTING_CONTEXT_CHANGED");
        }

        if (actual.mode() == Mode.IMPERSONATING
                && !decisionAt.isBefore(
                        actual.impersonationExpiresAt())) {
            throw new IllegalStateException("IMPERSONATION_EXPIRED");
        }
    }
}
~~~

Các giới hạn của ví dụ:

- Các trường bắt buộc và tính hợp lệ của record phải được kiểm tra ở đường tạo dữ liệu nội bộ.
- Hàm chưa kiểm tra quyền actor được impersonate ai, trạng thái thu hồi hoặc quyền trên đối tượng.
- Context khớp không chứng minh action được phép.
- Kiểm tra và ghi nghiệp vụ phải có ranh giới nhất quán khi context có thể đổi đồng thời.
- Cần ánh xạ lỗi thành hợp đồng HTTP phù hợp, ví dụ xung đột ngữ cảnh có thể dùng 409 trong API này.
- Hết hạn không làm request tự rơi về tài khoản actor và tiếp tục cùng lệnh.

Một pipeline tham chiếu:

~~~text
Xác thực phiên
-> lấy context đang có hiệu lực
-> so khớp expected context
-> kiểm tra phiên impersonation và action được phép
-> kiểm tra đối tượng thuộc đúng target/tenant
-> kiểm tra trạng thái và bất biến nghiệp vụ
-> ghi thay đổi, idempotency và audit
~~~

Với thao tác nhạy cảm, server cần xác định mốc tiếp nhận được bảo vệ trước chuyển context, kết thúc hoặc thu hồi. Một lần đọc context ở đầu request rồi xử lý rất lâu không tự bảo vệ quyết định cuối.

## 8. Minh họa HTML và cách thông báo có thể tiếp cận

### 8.1. Cấu trúc banner

~~~html
<aside id="impersonation-banner"
       aria-labelledby="impersonation-heading"
       hidden>
  <h2 id="impersonation-heading">Chế độ hỗ trợ đang bật</h2>

  <p>Người thao tác: <bdi id="acting-employee"></bdi></p>
  <p>Tài khoản đang hỗ trợ: <bdi id="acting-customer"></bdi></p>
  <p>Đơn vị: <bdi id="acting-tenant"></bdi></p>
  <p>Phạm vi: <span id="acting-scope"></span></p>

  <p>Hết hiệu lực:
    <time id="acting-expiry"></time>
  </p>

  <button id="end-impersonation" type="button">
    Kết thúc chế độ hỗ trợ
  </button>
</aside>

<p id="acting-context-announcement"
   role="status"
   aria-live="polite"
   aria-atomic="true"></p>
~~~

Đoạn HTML bắt đầu với banner ẩn, nhưng vùng làm việc chưa được phép hoạt động cho tới khi context được xác minh. Banner ẩn lúc khởi tạo không phải kết luận đang ở chế độ bình thường.

Dải hiển thị cần có bố cục không bị mất khi điều hướng. Nếu dùng sticky hoặc fixed, kiểm tra nội dung và focus không bị che, đặc biệt khi phóng to hoặc màn hình nhỏ.

### 8.2. Render dữ liệu bằng text

~~~javascript
function renderConfirmedImpersonation(view, formattedExpiry) {
  if (view.mode !== "IMPERSONATING") {
    throw new Error("Unexpected acting context");
  }

  document.getElementById("acting-employee").textContent =
    view.actor.displayName + " (" + view.actor.reference + ")";

  document.getElementById("acting-customer").textContent =
    view.effectiveUser.displayName +
    " (" + view.effectiveUser.reference + ")";

  document.getElementById("acting-tenant").textContent =
    view.tenant.displayName + " (" + view.tenant.reference + ")";

  document.getElementById("acting-scope").textContent =
    view.accessLabel;

  const expiry = document.getElementById("acting-expiry");
  expiry.dateTime = view.expiresAt;
  expiry.textContent = formattedExpiry;

  document.getElementById("impersonation-banner").hidden = false;

  document.getElementById("acting-context-announcement").textContent =
    "Đã bật chế độ hỗ trợ cho tài khoản " +
    view.effectiveUser.reference + ". " + view.accessLabel;
}
~~~

`view` là dữ liệu từ endpoint ngữ cảnh, đã được kiểm tra cấu trúc theo hợp đồng ứng dụng. `formattedExpiry` cần thể hiện ngày, giờ và vùng giờ đủ rõ.

Dùng `textContent` thay vì đưa tên tài khoản vào `innerHTML`. Tên hiển thị không được biến thành HTML thực thi hoặc ghi đè nhãn chế độ.

Đoạn mã chỉ minh họa render. Nó chưa thực hiện fetch, đồng bộ phiên bản, kết thúc phiên, xử lý lỗi hoặc ràng buộc request.

### 8.3. Thông báo thay đổi, không đọc lại liên tục

Khi bật, đổi target, hết hiệu lực hoặc kết thúc chế độ, ứng dụng nên thông báo thay đổi theo cách công nghệ hỗ trợ có thể nhận biết.

WCAG về status messages giải thích việc biểu diễn trạng thái bằng role hoặc thuộc tính phù hợp để người dùng được thông báo mà không cần luôn chuyển focus. [W3C — Status Messages](https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html)

Không đưa cả banner vào live region rồi cập nhật countdown mỗi giây. Điều đó có thể làm trình đọc màn hình đọc lại liên tục.

Nếu có đồng hồ đếm ngược, thông báo các mốc có ý nghĩa theo thiết kế, còn server quyết định hết hạn. Không dùng thời gian thiết bị để tự gia hạn phiên.

Nút kết thúc phải dùng được bằng bàn phím, có tên rõ và trạng thái đang xử lý có thể nhận biết. Không tạo focus trap chỉ để giữ người dùng nhìn banner.

## 9. Kết thúc chế độ là một thay đổi phía server

### 9.1. Không chỉ xóa banner hoặc cờ frontend

Luồng tham chiếu:

~~~text
Người dùng chọn kết thúc
-> tạm dừng thao tác theo context hiện tại
-> gửi yêu cầu kết thúc có xác thực và bảo vệ phù hợp
-> server chấm dứt context impersonation theo chính sách
-> server xác nhận hoặc client tải lại context hiện hành
-> loại dữ liệu/form/cache cũ
-> dựng lại vùng làm việc của actor nếu phiên actor còn hợp lệ
~~~

Một endpoint thay đổi trạng thái cần dùng phương thức và biện pháp chống request giả mạo phù hợp. Không dùng một liên kết GET gây kết thúc hoặc chuyển danh tính ngoài ý định.

Nếu phiên actor đã hết hạn, có thể cần đăng nhập lại. Không giữ token ban đầu trong JavaScript rồi tự phục hồi đặc quyền bằng cách gán lại token đó.

OWASP mô tả quản lý vòng đời phiên, đổi định danh phiên khi thay đổi mức quyền và vô hiệu hóa phía server. Cơ chế impersonation cần tích hợp với mô hình phiên thay vì chỉ thay trạng thái giao diện. [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)

### 9.2. Khi yêu cầu kết thúc bị timeout

Server có thể đã kết thúc nhưng phản hồi bị mất, hoặc chưa nhận được yêu cầu. Giao diện chưa biết kết quả.

Hiển thị trạng thái tương tự:

~~~text
Chưa xác nhận được việc kết thúc chế độ hỗ trợ.
Các thao tác đang tạm dừng. Đang kiểm tra lại trạng thái.
~~~

Không ẩn banner rồi hiển thị tài khoản actor như thể đã kết thúc thành công. Tải lại context hoặc retry thao tác kết thúc theo hợp đồng an toàn trước khi mở lại vùng làm việc.

Không cần giữ một lời khẳng định “chế độ vẫn đang hoạt động” khi chưa biết. Phải thể hiện đúng sự không chắc chắn.

### 9.3. Đóng tab, back và dữ liệu cũ

Đóng tab không tự bảo đảm phiên server đã hết. Nút back hoặc bộ nhớ khôi phục trang có thể đưa giao diện cũ trở lại.

Khi khôi phục hoặc tab hoạt động trở lại, cần xác minh context trước khi thao tác tiếp. Các thông báo giữa tab có thể giúp cập nhật sớm, nhưng không thay kiểm tra server.

Không lưu kết luận quyền trong một cờ frontend tồn tại lâu dài. Dữ liệu cache cần được phân tách theo context phù hợp và loại bỏ khi đổi target; một key chỉ theo URL có thể trả nhầm dữ liệu của khách hàng trước.

## 10. Request đang chạy và công việc bất đồng bộ

### 10.1. Không để phản hồi cũ ghi lên giao diện mới

Ví dụ:

~~~text
Bắt đầu tải đơn hàng của KH-4821.
Người dùng kết thúc chế độ hoặc chuyển sang KH-9072.
Phản hồi cũ quay về muộn.
~~~

Trước khi gắn dữ liệu lên màn hình, kiểm tra phản hồi còn thuộc context và thế hệ tải hiện tại. Nếu không, loại phản hồi đó.

Có thể hủy request ở frontend để giảm công việc thừa. Việc abort không chứng minh server chưa xử lý hoặc đã rollback thao tác.

Với dữ liệu nhạy cảm, thiết kế cả việc ngắt subscription, thay context WebSocket và lọc sự kiện đến muộn. Không chỉ xử lý HTTP fetch.

### 10.2. Kết thúc phiên không tự hủy mọi lệnh đã commit

Nếu một lệnh được tiếp nhận hợp lệ trước khi kết thúc, nó có thể đã được ghi vào hàng đợi. Cần chính sách xác định:

- Lệnh đã cam kết được tiếp tục hay cần hủy?
- Worker kiểm tra quyền ở lúc tiếp nhận, trước thực thi hay cả hai?
- Có thể hủy tới mốc nào?
- Kết quả không rõ được tra cứu hoặc đối soát ra sao?

Banner mất đi không phải bằng chứng không còn công việc nền. Nếu còn lệnh liên quan, giao diện có thể cung cấp trạng thái và đường quản lý phù hợp.

Worker phải giữ actor khởi tạo, target, tenant, nguồn impersonation và nội dung đã chốt. Không dùng quyền hệ thống để mở rộng phạm vi vì người dùng không còn nhìn thấy banner.

### 10.3. Bất biến vẫn được kiểm tra độc lập

Một chế độ hỗ trợ có banner rõ vẫn không được:

- Bỏ qua phê duyệt bắt buộc.
- Đổi giá hoặc người hưởng ngoài quyền.
- Hoàn tiền vượt tổng tiền đủ điều kiện.
- Tạo giao dịch trùng khi retry.
- Truy cập đối tượng của tenant khác.

Nếu có action được cho phép trong impersonation, action đó vẫn đi qua kiểm tra miền, transaction, hạn mức và idempotency tương ứng.

## 11. Vòng đời giao diện và audit

### 11.1. Mô hình trạng thái tham chiếu

~~~mermaid
stateDiagram-v2
    [*] --> Verifying
    Verifying --> Normal: server xác nhận ngữ cảnh thường
    Verifying --> Active: server xác nhận impersonation
    Verifying --> Unverified: không xác minh được
    Normal --> Starting: yêu cầu bật hỗ trợ
    Starting --> Active: server cấp context
    Starting --> Unverified: chưa rõ kết quả
    Active --> Ending: yêu cầu kết thúc
    Active --> Verifying: context đổi hoặc cần kiểm tra lại
    Ending --> Normal: xác nhận kết thúc và actor còn hợp lệ
    Ending --> Unverified: chưa rõ kết quả
    Unverified --> Verifying: tải lại trạng thái
~~~

Nếu xác thực không còn hợp lệ, ứng dụng còn cần nhánh đăng nhập lại. Không tự đi từ `Unverified` sang `Normal` chỉ vì đã chờ đủ lâu.

Các trạng thái xác minh hoặc chuyển chế độ phải có điều kiện khóa thao tác trên đối tượng, thay vì chỉ đổi một dòng chữ.

### 11.2. Audit giữ đúng ý nghĩa

Nên có dấu vết phù hợp cho:

- Yêu cầu bắt đầu và việc cấp context thành công.
- Target, tenant, actor, phạm vi, lý do hoặc hồ sơ hỗ trợ theo chính sách.
- Kết thúc, hết hạn và thu hồi.
- Request bị chặn vì context không khớp.
- Các thao tác nghiệp vụ đã commit trong chế độ.
- Lệnh nền và kết quả liên quan.

Phân biệt “người dùng chọn kết thúc” với “server đã chấm dứt context”.

Nếu ghi một event “banner đã render”, nó chỉ phản ánh thông tin phía client; không chứng minh người dùng đã nhìn thấy, hiểu hoặc đồng ý. Không dùng event đó thay bằng chứng phân quyền và commit.

Tránh ghi event cho mỗi lần countdown thay đổi hoặc mỗi lần component render lại. Audit cần giữ ý nghĩa, không bị lấp bởi nhiễu.

## 12. Kiểm thử nhầm ngữ cảnh và lạm dụng logic

Bảng này là các kịch bản cần kiểm tra cho một triển khai, không phải kết quả đã chạy kiểm thử hệ thống cụ thể.

| Tình huống | Điều cần xác minh |
|---|---|
| Bật impersonation thành công | Banner có actor, target, tenant, phạm vi và đường kết thúc |
| Fetch context lỗi lúc khởi tạo | Không tự hiển thị như chế độ bình thường hoặc mở thao tác theo giả định |
| Điều hướng, cuộn, modal, màn hình nhỏ | Người dùng vẫn nhận biết ngữ cảnh tại nơi quyết định hành động |
| Chỉ phân biệt chế độ bằng màu | Có thông tin chữ rõ và dùng được khi không phân biệt màu |
| Bàn phím và trình đọc màn hình | Có thể tìm nội dung, biết thay đổi và dùng nút kết thúc |
| Countdown cập nhật | Không làm live region đọc lặp liên tục |
| Tên tài khoản chứa HTML hoặc nhãn gây nhầm | Không thực thi HTML; nhãn hệ thống và mã nhận diện vẫn rõ |
| Banner ghi chỉ xem | Mọi action thay đổi tương ứng bị chặn ở server |
| Gọi trực tiếp API, GraphQL, batch hoặc WebSocket | Không vượt chính sách chỉ vì không qua UI |
| Tab B đổi target khi tab A còn form cũ | Tab A không gửi thành công vào target mới |
| Tự sửa expected context hoặc bỏ header | Không tự cấp quyền hoặc lách đường kiểm tra bắt buộc |
| Context thay đổi giữa kiểm tra và ghi | Quyết định theo ranh giới nhất quán đã thiết kế |
| Quay lại tab hoặc khôi phục trang cũ | Xác minh lại trước khi tiếp tục |
| Phản hồi KH-4821 về sau khi đổi sang KH-9072 | Không ghi dữ liệu cũ lên ngữ cảnh mới |
| Cache có dữ liệu từ target trước | Không dùng lại cho target mới |
| Nút kết thúc nhận lỗi hoặc timeout | Hiển thị chưa rõ, không giả thành công |
| Phiên actor hết hạn sau khi kết thúc | Không tự phục hồi quyền từ token lưu ở client |
| Đúng thời điểm phiên hỗ trợ hết hạn | Server từ chối theo chính sách, không phụ thuộc đồng hồ giao diện |
| Lệnh nền đã commit trước khi kết thúc | Xử lý theo hợp đồng, không suy ra đã hủy khi banner biến mất |
| Retry cùng ý định sau đổi context | Không trả nhầm kết quả hoặc tạo thêm tác dụng phụ |
| Người hỗ trợ sửa DOM để bỏ banner | Không mở rộng quyền backend |

Kiểm thử cần quan sát cả UI cuối cùng, request gửi đi, dữ liệu server và tác dụng phụ đã commit. Chỉ có ảnh chụp banner đúng chưa chứng minh ngữ cảnh an toàn.

Với kiểm thử khả năng tiếp cận, cần thao tác thực trên kích thước màn hình và công nghệ hỗ trợ phù hợp. Việc có một thuộc tính ARIA không tự bảo đảm trải nghiệm đúng.

## 13. Các bất biến cần giữ

Một impersonation banner có ích khi:

- Người dùng luôn nhận biết actor thực, tài khoản đích và tenant có liên quan.
- Nội dung được dựng từ context server, không từ cờ hoặc tên tài khoản tự khai.
- Phạm vi hiển thị khớp quyền thực thi.
- Ngữ cảnh chưa xác minh không bị trình bày như đã kết thúc hoặc đang bình thường.
- Nhiều tab, cache, phản hồi trễ và retry không làm yêu cầu đi vào sai target.
- Kết thúc chế độ có tác động phía server và được xác nhận trước khi đổi vùng làm việc.
- Mọi hành động vẫn giữ phân quyền đối tượng, state machine, transaction và idempotency.

Banner giúp con người chọn đúng hành động trong đúng ngữ cảnh. Server phải bảo đảm rằng dù giao diện bị sửa, cũ hoặc không xuất hiện, hành động vẫn không thể vượt phạm vi hỗ trợ đã được cấp.
