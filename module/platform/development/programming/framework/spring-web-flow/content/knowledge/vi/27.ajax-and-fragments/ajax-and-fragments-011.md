# Đọc ứng dụng Spring JavaScript cũ và đánh giá phương án thay thế

Trong chương **Ajax và phân mảnh**, bài này hướng dẫn cách đọc một ứng dụng đang dùng Spring JavaScript (thường được gọi là Spring.js), lần theo cách nó gắn sự kiện trình duyệt với request Ajax của Spring Web Flow, và đánh giá phương án thay thế phù hợp. Mục tiêu là hiểu hành vi hiện tại trước khi thay thư viện: nút nào gửi event, request mang flow execution key nào, server trả về toàn trang hay fragment, và dữ liệu nào được cập nhật vào DOM.

Spring Web Flow mô hình hóa hành trình nhiều bước qua state, event, transition và subflow; Spring MVC tiếp nhận request và render view. Spring JavaScript từng cung cấp lớp tiện ích phía trình duyệt để gắn hành vi Ajax, cập nhật vùng giao diện và tích hợp với các view của Spring. Khi bảo trì hệ thống cũ, cần phân biệt phần JavaScript của ứng dụng, thư viện Spring JS, toolkit giao diện đi kèm và cơ chế Ajax/fragment phía máy chủ. Chỉ thay một file script mà không hiểu hợp đồng request/response có thể làm hỏng flow đang chạy.

## 1. Spring JavaScript là gì và thường xuất hiện ở đâu?

Spring JavaScript là thư viện JavaScript thuộc hệ sinh thái Spring Web Flow đời trước, thường được phân phối cùng các tài nguyên web của Spring. Nó cung cấp API để gắn decoration vào phần tử HTML, gửi Ajax request, xử lý phản hồi và phối hợp với các tiện ích giao diện. Một số ứng dụng cũ còn dùng Dojo hoặc toolkit khác cho widget, hiệu ứng và sự kiện.

Khi đọc mã nguồn, có thể gặp các dấu hiệu sau:

| Dấu hiệu | Ý nghĩa cần kiểm tra |
| --- | --- |
| File như `spring.js`, `spring-resource.js` hoặc tài nguyên nằm dưới đường dẫn Spring resource | Có thể là thư viện Spring JavaScript hoặc resource được đóng gói cùng Spring. Xác minh nội dung và phiên bản thực tế. |
| Namespace JavaScript `Spring` | Có thể đang gọi API của Spring JS. Tìm nơi khởi tạo, nạp script và đăng ký decoration. |
| `Spring.addDecoration(...)` | Mã đang gắn hành vi cho phần tử HTML bằng một decoration. |
| `AjaxEventDecoration` hoặc `AjaxFormDecoration` | Có thể gửi event hoặc form qua Ajax thay vì submit trang thông thường. |
| Tham số như `fragments` hoặc header đánh dấu Ajax | Server có thể render một phần view thay vì toàn bộ trang. Cần kiểm tra request thực tế và cấu hình handler. |
| Tài nguyên Dojo, widget dialog hoặc popup | Giao diện có thể phụ thuộc vào toolkit cũ ngoài Spring JS. |

Tên file và API có thể khác theo phiên bản. Không kết luận một ứng dụng đang dùng Spring JS chỉ vì thấy chữ `spring` trong tên file; hãy xác nhận nội dung script, dependency và cách các trang gọi nó.

## 2. Lập bản đồ từ trang HTML đến request Ajax

Hãy bắt đầu từ một màn hình có tương tác Ajax cụ thể, chẳng hạn form tìm kiếm khung giờ. Lần theo toàn bộ đường đi:

1. HTML chứa form, nút hoặc phần tử được gắn event.
2. Script khởi tạo decoration và chỉ định event, form, tham số hoặc vùng phản hồi.
3. Trình duyệt gửi request đến URL của flow hoặc endpoint Spring MVC.
4. Request mang thông tin cần thiết như HTTP method, event ID, flow execution key, CSRF token và dấu hiệu Ajax.
5. Spring Web Flow/MVC xử lý request, thực hiện transition hoặc controller logic.
6. Server render toàn bộ view hoặc một/một số fragment.
7. JavaScript nhận response và thay nội dung vùng DOM tương ứng.

Ví dụ flow có view tìm kiếm và view kết quả:

```xml
<view-state id="searchSlots" view="booking/search">
    <transition on="search" to="showSlots" />
</view-state>

<view-state id="showSlots" view="booking/slots">
    <transition on="choose" to="reviewBooking" />
</view-state>
```

Một trang cũ có thể gắn Ajax decoration vào nút tìm kiếm. Đoạn dưới chỉ minh họa một pattern thường gặp của Spring JS; tên constructor, tham số và resource cần đối chiếu với đúng phiên bản trong ứng dụng:

```javascript
Spring.addDecoration(new Spring.AjaxEventDecoration({
    elementId: "searchButton",
    event: "onclick",
    formId: "slotSearchForm",
    params: { fragments: "slotResults" }
}));
```

Đừng chỉ đọc JavaScript để đoán response. Mở trình duyệt, bật Network, thực hiện thao tác và ghi lại URL, method, request headers, form data/query string, status code, response headers và body. Đối chiếu response với vùng DOM được cập nhật. Nếu request gửi `fragments=slotResults`, hãy tìm xem server dùng tham số đó ở đâu và fragment có tên tương ứng được render thế nào.

## 3. Nhận diện các phần phụ thuộc trong một ứng dụng cũ

Spring JavaScript thường không đứng một mình. Trước khi thay thế, lập danh sách tất cả lớp phụ thuộc:

| Lớp | Cần tìm | Câu hỏi cần trả lời |
| --- | --- | --- |
| Dependency | Maven/Gradle dependency hoặc JAR được đóng gói | Phiên bản Spring JS/Web Flow nào đang được dùng? Có dependency bắc cầu nào không? |
| Resource | Script, stylesheet, ảnh, dojo modules | Tài nguyên được phục vụ từ classpath, servlet resource handler hay thư mục static? |
| Khởi tạo | Script chung, `onload`, decorator registration | Decoration được đăng ký trực tiếp trong trang hay từ file dùng chung? |
| HTML | ID phần tử, form, class, data attribute | JavaScript phụ thuộc ID hoặc cấu trúc DOM nào? |
| Server | Flow XML, controller, view resolver, Ajax handler | Request đi vào flow state nào và server chọn fragment bằng cách nào? |
| Template | JSP, Tiles, Thymeleaf hoặc view technology khác | Fragment được định danh, lồng và render ra sao? |
| Toolkit | Dojo hoặc thư viện UI khác | Widget nào phụ thuộc toolkit và có thể thay riêng không? |
| Bảo mật | CSRF, session, execution key, authorization | Ajax request có giữ nguyên cơ chế bảo vệ của form thường không? |

Tìm kiếm trong phạm vi repository các chuỗi `Spring.addDecoration`, `AjaxEventDecoration`, `AjaxFormDecoration`, `Spring.remoting`, `Spring.onLoad`, `fragments`, `Spring-ajax` và tên file script thực tế. Sau đó lần theo từng kết quả đến view, flow/controller và cấu hình resource. Không thay thế toàn bộ thư viện chỉ vì một màn hình không còn dùng API của nó; có thể ứng dụng vẫn phụ thuộc vào một widget hoặc một trang khác.

## 4. Hiểu hợp đồng request của Spring Web Flow

Request Ajax gửi đến flow vẫn là request của một flow execution. Tùy cách triển khai, request có thể cần:

- Flow execution key để tiếp tục đúng lần thực thi.
- Event parameter như `_eventId_search` để phát event tương ứng.
- Dữ liệu form và các request parameter cần cho binding.
- CSRF token theo cấu hình Spring Security.
- Header hoặc parameter đánh dấu request Ajax để server chọn cách render response.
- Tham số chỉ định fragment cần render nếu ứng dụng sử dụng cơ chế này.

Một request submit form truyền thống có thể trông như sau:

```html
<form method="post" action="/booking">
    <input type="hidden" name="_flowExecutionKey" value="EXAMPLE-KEY" />
    <input type="hidden" name="_csrf" value="EXAMPLE-CSRF-TOKEN" />
    <input name="date" value="2026-12-10" />
    <button type="submit" name="_eventId_search" value="true">Tìm</button>
</form>
```

Các giá trị key/token ở trên chỉ minh họa cấu trúc; ứng dụng phải render giá trị thật từ Web Flow và Spring Security. Khi chuyển sang `fetch`, htmx hoặc thư viện khác, cần giữ đúng URL, method, execution key, event parameter, CSRF token và dữ liệu binding. Không hard-code execution key hoặc sao chép token của một request sang flow execution khác.

Nếu Ajax request không gửi execution key hoặc gửi key cũ, server có thể không tìm được execution, trả lỗi hết hạn hoặc xử lý sai flow. Nếu request thiếu event parameter, server có thể không thực hiện transition mà client đang mong đợi. Đây là lý do cần lưu request thực tế trước khi viết lại JavaScript.

## 5. Hiểu fragment response và cập nhật DOM

Một request Ajax có thể nhận một fragment HTML thay vì toàn bộ trang. Ví dụ server render vùng kết quả tìm kiếm, còn client thay nội dung `#slotResults`. Cần xác định rõ:

- Fragment nào được yêu cầu và fragment name được truyền ở đâu?
- View resolver hoặc Ajax handler nào chọn phần view cần render?
- Response là HTML thuần, JSON chứa HTML hay một định dạng riêng?
- Client cập nhật element nào, thay toàn bộ element hay chỉ nội dung con?
- Script khởi tạo widget có chạy lại sau khi thay fragment không?
- Form errors, validation messages và flow execution key mới có được đưa vào fragment không?

Ví dụ JSP tách vùng kết quả:

```jsp
<%-- booking/search.jsp --%>
<form id="slotSearchForm" method="post">
    <!-- Các field tìm kiếm và flow execution key được render tại đây. -->
</form>

<section id="slotResults" aria-live="polite">
    <jsp:include page="/WEB-INF/views/booking/slot-results.jsp" />
</section>
```

View fragment có thể được render lại với danh sách mới. Nhưng cần xem response thực tế: một số ứng dụng dùng Tiles hoặc cơ chế Ajax handler để chọn fragment; một số ứng dụng chỉ trả toàn bộ JSP rồi client tự trích phần tử. Hai cách có hợp đồng khác nhau.

Nếu thay DOM bằng `innerHTML`, các event listener gắn trực tiếp vào node cũ có thể mất. Cần gắn listener lại sau khi cập nhật, dùng event delegation hoặc chọn cơ chế component có lifecycle rõ ràng. Cũng phải tránh khởi tạo widget trùng lặp khi fragment được render nhiều lần.

## 6. Đánh giá các phương án thay thế

Không có một thư viện mới phù hợp cho mọi ứng dụng. Chọn theo độ phức tạp giao diện, khả năng giữ server-rendered views, nhu cầu tương tác và kỹ năng đội ngũ.

| Phương án | Phù hợp khi | Ưu điểm | Chi phí/rủi ro |
| --- | --- | --- | --- |
| HTML form và navigation thông thường | Tương tác ít, mỗi bước có thể tải trang mới | Đơn giản, dễ kiểm thử, progressive enhancement tốt | Có full page reload; trải nghiệm ít tức thời hơn. |
| `fetch` hoặc XMLHttpRequest gốc | Chỉ có một vài tương tác Ajax và muốn ít dependency | API trình duyệt chuẩn, kiểm soát request/response rõ | Phải tự xử lý loading, lỗi, DOM update, CSRF và lifecycle. |
| htmx | Giao diện chủ yếu server-rendered và cần thay fragment theo request | Khai báo tương tác ngay trong HTML, phù hợp HTML response | Cần thống nhất header, target, swap strategy, history và tích hợp flow key. |
| Framework UI như React/Vue | Giao diện có state client phức tạp, component tương tác sâu | Component model và ecosystem phong phú | Tăng công sức build, state synchronization, API contract và accessibility. |
| Giữ Spring JS trong ngắn hạn | Ứng dụng lớn, rủi ro thay đổi cao hoặc còn phụ thuộc sâu | Tránh migration diện rộng ngay lập tức | Tiếp tục gánh dependency cũ, khó nâng cấp và khó tuyển người bảo trì. |

### Giữ HTML form và submit truyền thống

Đây thường là phương án an toàn cho wizard nhiều bước nếu Ajax chỉ được dùng để tránh tải lại trang. Form POST event đến flow, server thực hiện transition rồi trả view kế tiếp. Cách này tận dụng binding, validation và flow execution sẵn có, giảm code phía trình duyệt. Có thể dùng redirect sau khi kết thúc hoặc khi cần pattern POST/Redirect/GET.

### Dùng fetch cho tương tác nhỏ

`fetch` phù hợp khi cần tải gợi ý, kiểm tra một field hoặc refresh một vùng kết quả. Client cần gửi đúng method, content type, CSRF token và flow execution key nếu request tiếp tục flow. Phải kiểm tra `response.ok`, xử lý status như 401/403/409/410 và không giả định mọi response đều là HTML thành công.

Ví dụ tổng quát khi gửi form:

```javascript
const form = document.querySelector("#slotSearchForm");

form.addEventListener("submit", async (event) => {
    event.preventDefault();

    const response = await fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        headers: { "Accept": "text/html", "X-Requested-With": "XMLHttpRequest" }
    });

    if (!response.ok) {
        // Hiển thị lỗi phù hợp; không thay DOM bằng một trang lỗi tùy tiện.
        return;
    }

    const html = await response.text();
    document.querySelector("#slotResults").innerHTML = html;
});
```

Đây chỉ là khung minh họa. Ứng dụng phải bổ sung CSRF header/parameter theo cấu hình thực tế, đảm bảo `form.action` trỏ đúng flow execution URL, và xác định response thực sự là fragment `slotResults`. Không dùng `X-Requested-With` làm cơ chế xác thực hoặc bằng chứng bảo mật; đó chỉ là dấu hiệu request nếu server có quy ước sử dụng.

### Dùng htmx cho server-rendered fragments

htmx có thể phù hợp khi server đã render HTML và client chỉ cần yêu cầu một phần view. Các thuộc tính như `hx-post`, `hx-target` và `hx-swap` mô tả request và vùng cập nhật. Trước khi dùng với Web Flow, hãy xác định cách truyền execution key và CSRF token, cách server nhận diện Ajax request, cách trả fragment và cách xử lý redirect/flow expiration. Không giả định response redirect của flow sẽ tự hoạt động giống một request điều hướng toàn trang trong mọi cấu hình htmx.

Ví dụ ý tưởng:

```html
<form hx-post="/booking/execution-url"
      hx-target="#slotResults"
      hx-swap="innerHTML">
    <!-- Form fields, execution key và CSRF token được render từ server. -->
    <button type="submit">Tìm khung giờ</button>
</form>
<div id="slotResults" aria-live="polite"></div>
```

URL trong ví dụ là placeholder. Khi triển khai, dùng execution URL do Web Flow tạo và kiểm tra response fragment tương ứng. Nếu event làm flow chuyển sang state khác, cần quyết định server trả fragment của state mới hay yêu cầu trình duyệt điều hướng toàn trang.

### Dùng React hoặc Vue khi client thực sự sở hữu giao diện

Framework UI phù hợp khi màn hình có nhiều tương tác cục bộ, state phức tạp, cập nhật lạc quan hoặc component phong phú. Tuy nhiên, khi kết hợp với Spring Web Flow, cần xác định rõ ai sở hữu state quy trình. Một hướng là Web Flow tiếp tục quản lý quy trình máy chủ và client chỉ render dữ liệu/submit event; hướng khác là chuyển hẳn điều phối quy trình sang API và client router. Tránh để cùng một quy trình có hai state machine độc lập không đồng bộ.

## 7. Đánh giá tương thích với Spring MVC và Spring Web Flow

Trước khi chọn công nghệ, kiểm tra từng yêu cầu kỹ thuật:

| Yêu cầu | Câu hỏi đánh giá |
| --- | --- |
| Flow execution | Request mới có tiếp tục đúng execution không? Execution key được cập nhật sau response như thế nào? |
| Event | Event name được gửi theo quy ước nào? Có hỗ trợ event từ form và nút riêng không? |
| Binding | Server có nhận đúng form fields, nested properties và multi-value parameters không? |
| Validation | Binding errors và validation messages có thể render lại trong fragment không? |
| Redirect | Khi flow kết thúc hoặc chuyển flow, client có điều hướng toàn trang đúng không? |
| Session | Request Ajax có gửi session cookie và xử lý timeout/expired execution không? |
| CSRF | Token được gửi đúng cách với POST, PUT, PATCH hoặc DELETE? |
| Accessibility | Loading, lỗi và nội dung mới có được thông báo cho screen reader không? |
| History | Back/Forward có đưa flow và giao diện về trạng thái nhất quán không? |
| Testing | Có thể kiểm thử request, response, fragment và hành vi browser ổn định không? |

Đặc biệt chú ý response sau transition. Nếu server render một view state mới nhưng client chỉ thay một vùng nhỏ, các thành phần ngoài vùng đó có thể vẫn hiển thị dữ liệu cũ hoặc execution key cũ. Nếu response là redirect, client cần tuân theo semantics của redirect và cập nhật URL/history phù hợp. Hãy quyết định rõ khi nào nên swap fragment và khi nào phải điều hướng toàn trang.

## 8. Lộ trình migration theo từng màn hình

Thay thế thư viện cũ nên diễn ra theo lát cắt nhỏ, bắt đầu từ màn hình ít rủi ro:

1. **Kiểm kê:** tìm dependency, script, decoration, widget, flow, controller và fragment liên quan.
2. **Ghi nhận hành vi:** lưu request/response của các thao tác chính, gồm thành công, validation error, timeout và redirect.
3. **Phân loại tương tác:** quyết định thao tác nào cần Ajax, thao tác nào có thể dùng form submit thông thường.
4. **Chọn phương án:** native form, fetch, htmx hoặc framework UI dựa trên yêu cầu của màn hình.
5. **Giữ hợp đồng máy chủ:** bảo toàn flow ID, execution key, event, binding, validation, CSRF và quyền truy cập.
6. **Thay một tương tác:** chuyển một form hoặc một vùng fragment, không thay toàn bộ ứng dụng trong một lần.
7. **Kiểm thử hồi quy:** so sánh URL, method, payload, response, DOM, history và trạng thái flow trước/sau.
8. **Loại bỏ dependency cũ:** chỉ gỡ resource và thư viện khi tìm kiếm xác nhận không còn trang nào dùng đến.

Trong giai đoạn chuyển tiếp, có thể để các màn hình cũ và mới cùng tồn tại. Đặt ranh giới rõ theo view hoặc route, tránh nạp hai framework cùng xử lý một form. Theo dõi lỗi JavaScript, response 4xx/5xx và tỷ lệ flow execution hết hạn sau khi triển khai từng lát cắt.

## 9. Các lỗi migration thường gặp

- **Mất flow execution key:** request Ajax không còn tiếp tục được flow hiện tại. Hãy kiểm tra form data và URL được render từ execution hiện tại.
- **Sai event name:** nút gửi `submit` nhưng transition chờ `search`; request đến server nhưng flow không đi đúng state.
- **Server trả toàn trang nhưng client chèn vào fragment:** DOM bị lồng trang, duplicate ID hoặc script chạy sai. Xác định rõ response contract.
- **Server trả fragment nhưng client điều hướng toàn trang:** có thể hiện nội dung thiếu layout hoặc thiếu tài nguyên. Chọn đúng kiểu response cho từng request.
- **Mất CSRF token:** POST Ajax bị từ chối dù form thường hoạt động. Truyền token theo cấu hình Spring Security.
- **Validation errors biến mất:** client chỉ cập nhật vùng kết quả mà không cập nhật vùng chứa thông báo lỗi. Đảm bảo fragment có cả field errors cần thiết.
- **Widget không hoạt động sau swap:** listener gắn vào node cũ đã bị thay. Dùng event delegation hoặc khởi tạo lại theo lifecycle.
- **Back/Forward không đồng bộ:** URL thay đổi nhưng flow execution hoặc nội dung trang không tương ứng. Xác định chính sách history rõ ràng.
- **Gỡ script quá sớm:** một view khác vẫn phụ thuộc vào Spring JS hoặc Dojo. Kiểm kê toàn bộ nơi sử dụng trước khi xóa dependency.
- **Chỉ kiểm thử happy path:** lỗi timeout, session expiry, redirect và request lặp bị bỏ sót. Bổ sung kịch bản lỗi và thao tác liên tiếp.

## 10. Bộ kiểm thử tối thiểu trước khi bỏ Spring JS

| Kịch bản | Điều cần xác nhận |
| --- | --- |
| Mở flow mới | URL, view và execution key được tạo đúng. |
| Gửi event Ajax hợp lệ | Flow chuyển đúng state và response có đúng fragment. |
| Submit dữ liệu không hợp lệ | Flow giữ đúng view, lỗi binding/validation hiển thị đúng field. |
| Submit hai lần nhanh | Không tạo giao dịch hoặc bản ghi trùng; UI thể hiện trạng thái đang xử lý. |
| Session hết hạn | Người dùng được hướng dẫn khởi chạy lại; không chèn trang đăng nhập vào vùng fragment sai cách. |
| Execution key hết hạn/sai | Server từ chối an toàn và client có cách phục hồi rõ ràng. |
| CSRF token thiếu/sai | Request thay đổi trạng thái bị từ chối theo cấu hình. |
| Flow kết thúc | Client điều hướng đến URL đích đúng, không chỉ thay fragment cũ. |
| Back/Forward | URL, view và flow state không mâu thuẫn. |
| Fragment chứa dữ liệu người dùng | Nội dung được encode, không gây XSS. |
| Màn hình còn dùng widget cũ | Widget tiếp tục hoạt động cho đến khi được thay thế riêng. |

Kiểm thử server-side nên bao gồm flow execution test và MVC integration test. Kiểm thử trình duyệt cần xác nhận Network request, DOM update, focus, thông báo accessibility và history. Sau khi thay thế, tìm lại các API/resource cũ trong phạm vi repository để chắc chắn không còn nơi sử dụng trước khi gỡ dependency.

## 11. Cách đưa ra quyết định cuối cùng

Hãy đánh giá theo ba câu hỏi:

1. **Tương tác có thực sự cần Ajax không?** Nếu một lần tải trang mới không ảnh hưởng đáng kể đến trải nghiệm, form POST thông thường thường đơn giản và đáng tin cậy hơn.
2. **Server đã sở hữu HTML và flow state chưa?** Nếu có, fetch hoặc htmx có thể thay Spring JS với thay đổi nhỏ, miễn là giữ hợp đồng request/fragment và execution key.
3. **Client có cần sở hữu state giao diện phức tạp không?** Nếu có, React/Vue có thể phù hợp, nhưng cần một API và ranh giới state rõ ràng để không tạo hai bộ điều phối quy trình.

Không cần thay toàn bộ Spring JavaScript chỉ vì thư viện cũ. Hãy ưu tiên thay những tương tác có nhu cầu rõ, kiểm thử được và có ranh giới request/response ổn định. Khi hiểu được decoration, flow execution, fragment rendering và dependency của từng màn hình, đội ngũ có thể chọn phương án thay thế theo giá trị thực tế và giữ cho Spring Web Flow tiếp tục quản lý hành trình nhiều bước một cách nhất quán.
