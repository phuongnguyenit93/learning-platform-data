# Kiểm tra redirect với yêu cầu thông thường và yêu cầu Ajax

Trong chương **URL và điều hướng**, bài này hướng dẫn kiểm tra cách Spring Web Flow chuyển hướng sau khi nhận một request thông thường và một request Ajax. Cả hai loại request đều có thể gửi event để tiếp tục flow, nhưng cách trình duyệt xử lý phản hồi khác nhau. Nếu dùng cùng một kiểu redirect cho cả hai mà không xét cơ chế Ajax, ứng dụng có thể cập nhật nhầm một vùng HTML, không đổi URL trên thanh địa chỉ hoặc điều hướng không đúng flow execution.

Module **SPRING_WEB_FLOW** mô hình hóa hành trình web nhiều bước bằng state, event, transition và subflow; đồng thời tích hợp flow execution với Spring MVC. Vì vậy, cần kiểm tra cả phản hồi HTTP, URL đích, flow execution key và hành vi phía trình duyệt.

## 1. Redirect giải quyết vấn đề gì?

Redirect yêu cầu trình duyệt thực hiện một request mới đến URL khác. Trong ứng dụng web, cách dùng phổ biến là Post/Redirect/Get (PRG): trình duyệt gửi POST để xử lý form, server trả redirect, rồi trình duyệt gửi GET đến URL hiển thị kết quả. Khi người dùng refresh trang kết quả, trình duyệt không gửi lại POST vừa tạo dữ liệu.

Với Spring Web Flow, redirect còn giúp trình duyệt tiếp tục đúng flow execution sau khi một event làm thay đổi trạng thái. URL thực thi flow thường mang execution key do SWF quản lý. Luôn dùng URL do flow cung cấp để gửi event tiếp theo, tránh tự tạo hoặc ghép key bằng chuỗi cố định.

Redirect khác với render view:

| Hành vi | Điều xảy ra | Khi phù hợp |
|---|---|---|
| Render view | Server trả nội dung HTML hoặc fragment trong response hiện tại. | Hiển thị state hiện tại hoặc cập nhật một phần trang. |
| Redirect | Server yêu cầu client tạo request mới đến URL đích. | PRG, rời flow, hoặc chuyển sang URL khác. |
| Forward nội bộ | Server chuyển xử lý trong cùng request theo cơ chế web container/MVC. | Điều phối nội bộ khi không cần browser đổi URL. |

Trong flow, một transition sang state khác không nhất thiết có nghĩa ứng dụng phải điều hướng ra một URL ngoài. SWF quản lý state và execution URL. Chỉ dùng external redirect khi thực sự muốn trình duyệt rời flow hoặc mở một URL bên ngoài.

## 2. Phân biệt điều hướng bên trong flow và external redirect

Có hai tình huống dễ bị nhầm:

**Chuyển state trong cùng flow:** transition chuyển từ `edit` sang `review`, hoặc từ `review` sang `completed`. Flow execution vẫn thuộc cùng flow; SWF tiếp tục quản lý state và execution key. Trình duyệt có thể nhận redirect nội bộ theo cơ chế PRG của adapter để tải lại URL thực thi flow.

**Rời flow bằng external redirect:** end-state hoặc view selection yêu cầu chuyển trình duyệt đến một URL khác, ví dụ trang cảm ơn của ứng dụng hoặc trang thanh toán do nhà cung cấp lưu trữ. URL đích có thể nằm trong ứng dụng hoặc ở domain khác.

Ví dụ một flow xác nhận đơn hàng rồi chuyển ra trang kết quả trong cùng ứng dụng:

```xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="http://www.springframework.org/schema/webflow
                          http://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <view-state id="review" view="order/review">
        <transition on="back" to="edit"/>
        <transition on="confirm" to="completed">
            <evaluate expression="orderService.confirm(flowScope.orderId)"/>
        </transition>
    </view-state>

    <end-state id="completed"
               view="externalRedirect:contextRelative:/orders/complete"/>
</flow>
```

`externalRedirect:contextRelative:` yêu cầu chuyển hướng đến đường dẫn tương đối với context của ứng dụng. Nếu cần redirect đến domain khác, hãy dùng URL đích được cấu hình và kiểm soát ở server. Không lấy tùy ý tham số `returnUrl` từ người dùng rồi đưa thẳng vào redirect vì có thể tạo open redirect.

Khi chỉ chuyển từ state này sang state khác, giữ điều hướng trong flow và dùng `${flowExecutionUrl}` của view. Không chuyển sang URL bắt đầu flow mới nếu mục tiêu chỉ là tiếp tục execution hiện tại.

## 3. Request thông thường: PRG và Location header

Request thông thường thường được trình duyệt gửi bằng form HTML. Ví dụ, người dùng xác nhận đơn từ màn hình review:

```html
<form method="post" action="${flowExecutionUrl}">
    <!-- Các trường và CSRF token do ứng dụng cung cấp -->
    <button type="submit" name="_eventId_confirm">Xác nhận</button>
</form>
```

`_eventId_confirm` khớp với transition `on="confirm"`. Sau khi xử lý event, server có thể trả redirect để trình duyệt tải URL tiếp theo. Với PRG, phản hồi redirect thường là 302 hoặc 303 tùy cấu hình và phiên bản framework; hãy kiểm tra status thực tế của ứng dụng thay vì mặc định rằng mọi redirect đều dùng cùng một mã.

Khi kiểm tra request thường, cần xác minh:

1. POST được gửi đến đúng `flowExecutionUrl` và chứa event ID đúng.
2. Server trả status redirect phù hợp và có header `Location` hợp lệ.
3. Trình duyệt gửi request GET tiếp theo đến URL trong `Location`.
4. URL trên thanh địa chỉ được cập nhật và hiển thị state/view mong đợi.
5. Flow execution tiếp tục đúng execution; không khởi tạo một flow mới ngoài ý muốn.
6. Dữ liệu cần chuyển qua redirect được đặt trong flash scope hoặc cơ chế output tương ứng, không dựa vào request scope đã kết thúc.

Có thể dùng flash scope để hiển thị thông báo một lần sau redirect. Không lưu object lớn hoặc dữ liệu nhạy cảm vào flash scope; chỉ chuyển thông tin cần cho lần hiển thị tiếp theo.

## 4. Request Ajax: redirect không đồng nghĩa với điều hướng toàn trang

A request Ajax thường được gửi bằng `XMLHttpRequest` hoặc `fetch`. Trình duyệt nhận response trong JavaScript thay vì điều hướng tài liệu hiện tại. Nếu server trả HTTP 302 cho một request XHR, trình duyệt có thể tự theo redirect ở tầng XHR, nhưng URL trên thanh địa chỉ và tài liệu đang mở không nhất thiết thay đổi. JavaScript thường chỉ nhận nội dung response cuối cùng.

Vì vậy, không thể suy luận rằng “server đã trả 302” thì người dùng đã được điều hướng. Cần phân biệt hai mục tiêu:

- **Cập nhật một phần giao diện:** server trả fragment hoặc response Ajax phù hợp; JavaScript thay vùng giao diện cần thiết. URL trang có thể giữ nguyên.
- **Điều hướng trình duyệt đến URL khác:** server và Ajax client phải có giao thức redirect dành cho Ajax. Client nhận tín hiệu redirect rồi thực hiện điều hướng cấp trang, ví dụ cập nhật `window.location` theo cơ chế thư viện đang dùng.

Spring Web Flow tích hợp cơ chế `AjaxHandler` để nhận diện request Ajax và gửi phản hồi phù hợp. Khi dùng Spring JavaScript, `SpringJavascriptAjaxHandler` phối hợp với client để xử lý redirect và lỗi Ajax. Hãy dùng handler và client tương thích với phiên bản SWF/Spring đang chạy; không tự đoán một response header hay format JSON rồi kỳ vọng thư viện hiểu được.

## 5. Cấu hình AjaxHandler với FlowHandlerAdapter

Trong cấu hình Spring MVC, `FlowHandlerAdapter` kết nối request với `FlowExecutor`. Với ứng dụng sử dụng Spring JavaScript, có thể cấu hình Ajax handler tương ứng:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.webflow.execution.FlowExecutor;
import org.springframework.webflow.mvc.servlet.FlowHandlerAdapter;
import org.springframework.webflow.mvc.servlet.SpringJavascriptAjaxHandler;

@Configuration
public class FlowMvcConfiguration {

    @Bean
    public FlowHandlerAdapter flowHandlerAdapter(FlowExecutor flowExecutor) {
        FlowHandlerAdapter adapter = new FlowHandlerAdapter();
        adapter.setFlowExecutor(flowExecutor);
        adapter.setAjaxHandler(new SpringJavascriptAjaxHandler());
        adapter.setSaveOutputToFlashScopeOnRedirect(true);
        return adapter;
    }
}
```

Đây là ví dụ cấu hình khi ứng dụng chủ động dùng Spring JavaScript Ajax handler. Nếu ứng dụng đã có bean `FlowHandlerAdapter` do cấu hình khác tạo ra, hãy chỉnh bean hiện hữu thay vì đăng ký adapter thứ hai. API và cách auto-configure có thể khác theo phiên bản; đối chiếu Javadoc của đúng phiên bản Spring Web Flow đang dùng trước khi sao chép cấu hình.

`setSaveOutputToFlashScopeOnRedirect(true)` hỗ trợ giữ output của flow qua redirect theo cơ chế adapter. Chỉ bật khi ứng dụng cần chuyển output như thông báo hoặc dữ liệu kết quả đến request tiếp theo; tránh xem flash scope là kho lưu trạng thái dài hạn.

## 6. Gửi event Ajax và render fragment

Khi mục tiêu là cập nhật một phần màn hình, client gửi request Ajax đến execution URL và yêu cầu render phần view cần thay đổi. View-state có thể khai báo nội dung phù hợp với cơ chế Ajax của giao diện; ví dụ dưới đây minh họa form có vùng kết quả được cập nhật bởi JavaScript:

```html
<form id="searchForm" method="post" action="${flowExecutionUrl}">
    <input name="keyword" type="search">
    <button type="submit" name="_eventId_search">Tìm kiếm</button>
</form>

<div id="searchResults">
    <!-- Kết quả tìm kiếm được render bởi view -->
</div>
```

JavaScript gửi form theo cơ chế Ajax của thư viện đang dùng, rồi thay nội dung `searchResults` bằng fragment response. Khi response là fragment, không được thay cả document hoặc cố đưa fragment vào thanh địa chỉ.

Nếu event làm flow kết thúc hoặc cần chuyển sang một URL ngoài, response Ajax phải được xử lý như redirect điều hướng. Không cố chèn HTML của trang đích vào `searchResults`, vì trang đích có thể chứa layout đầy đủ, script và tài nguyên không phù hợp để nhúng.

## 7. Chọn đúng hành vi cho từng loại request

| Tình huống | Request thường | Request Ajax |
|---|---|---|
| Validation lỗi ở cùng view-state | Render lại view với lỗi và dữ liệu người dùng đã nhập. | Trả fragment/thông báo lỗi để cập nhật vùng form. |
| Chuyển sang state tiếp theo trong flow | Theo redirect/PRG hoặc cơ chế execution URL của SWF. | Cập nhật fragment nếu vẫn ở trong trải nghiệm Ajax; nếu cần đổi trang, dùng Ajax redirect signal. |
| Kết thúc flow và về trang cảm ơn | Redirect trình duyệt đến URL đích. | Phát tín hiệu redirect cho client để điều hướng toàn trang. |
| Lỗi quyền hoặc lỗi nghiệp vụ | Trả view lỗi hoặc redirect theo chính sách. | Trả lỗi Ajax có status/format phù hợp hoặc tín hiệu điều hướng lỗi được client hỗ trợ. |
| Cập nhật danh sách trong cùng màn hình | Render lại view đầy đủ nếu phù hợp. | Render fragment và thay vùng danh sách. |

Không dùng redirect chỉ để cập nhật một phần giao diện nếu fragment response giải quyết được yêu cầu. Ngược lại, không trả fragment khi flow đã kết thúc và người dùng cần rời khỏi trang hiện tại.

## 8. Kiểm tra response trong trình duyệt

DevTools Network là nơi nhanh nhất để xác định redirect đã xảy ra ở tầng HTTP hay đã điều hướng tài liệu:

1. Bật Preserve log để giữ lại chuỗi request trước và sau redirect.
2. Gửi form bằng request thường; kiểm tra request method, status, `Location` và request GET tiếp theo.
3. Gửi cùng event bằng Ajax; kiểm tra request có dấu hiệu Ajax, response status, headers và body.
4. Xác nhận JavaScript có nhận diện redirect signal và thực hiện điều hướng cấp trang khi cần.
5. Kiểm tra URL trên thanh địa chỉ, DOM được cập nhật và state của flow sau phản hồi.
6. Kiểm tra cookie/session, CSRF token và flow execution key có được gửi cùng request tiếp theo.

Các dấu hiệu thường gặp:

| Quan sát | Khả năng cần kiểm tra |
|---|---|
| Request thường trả 302/303 nhưng không có GET tiếp theo | Trình duyệt bị chặn, Location không hợp lệ hoặc request bị hủy. |
| Ajax trả 302 nhưng URL thanh địa chỉ không đổi | XHR đã theo redirect ở tầng request; client chưa thực hiện top-level navigation. |
| Ajax trả fragment nhưng toàn trang bị thay thế | JavaScript đang xử lý response như redirect hoặc nhắm sai vùng DOM. |
| Redirect quay về URL flow cũ | Event không được nhận, flow key sai hoặc transition chưa chạy như dự kiến. |
| Redirect lặp liên tục | URL đích lại kích hoạt điều kiện redirect, session/authentication hoặc mapping sai. |
| Sau redirect mất thông báo | Output chưa được lưu qua flash scope hoặc thông báo được đọc sai thời điểm. |

## 9. Kiểm thử request thường và Ajax

Viết test riêng cho hai loại request vì cùng một transition có thể tạo phản hồi khác nhau tùy cách request được gửi.

### 9.1. Kiểm thử request thông thường

Với MockMvc hoặc kiểm thử tích hợp tương đương, gửi POST đến execution URL cùng event parameter và xác nhận redirect:

```java
mvc.perform(post(flowExecutionUrl)
        .param("_eventId_confirm", "")
        .with(csrf()))
    .andExpect(status().is3xxRedirection())
    .andExpect(header().exists("Location"));
```

`flowExecutionUrl` phải được lấy từ response hoặc fixture của lần khởi tạo flow trong test, không hardcode execution key. Nếu cần kiểm tra PRG đầy đủ, tiếp tục GET URL trong `Location` và xác nhận view/state đích.

### 9.2. Kiểm thử request Ajax

Gửi request có dấu hiệu Ajax theo cơ chế mà `AjaxHandler` đang nhận diện. Với cấu hình phổ biến dựa trên XMLHttpRequest, có thể bắt đầu bằng header `X-Requested-With: XMLHttpRequest`; kiểm tra cấu hình thực tế vì client hoặc handler tùy phiên bản có thể dùng thêm quy ước riêng.

```java
mvc.perform(post(flowExecutionUrl)
        .header("X-Requested-With", "XMLHttpRequest")
        .param("_eventId_confirm", "")
        .with(csrf()))
    .andReturn();
```

Không nên chỉ assert rằng response Ajax có status 302. Hãy xác minh Ajax handler trả đúng tín hiệu mà client đang dùng hiểu được, rồi dùng kiểm thử trình duyệt hoặc JavaScript integration test để chứng minh URL tài liệu thực sự thay đổi khi cần điều hướng.

### 9.3. Ma trận test tối thiểu

| Test case | Kiểm tra chính |
|---|---|
| POST thường với event hợp lệ | Redirect có Location và GET tiếp theo hiển thị state đúng. |
| POST Ajax với event hợp lệ nhưng vẫn ở flow | Fragment response cập nhật đúng vùng giao diện. |
| POST Ajax làm kết thúc flow | Client nhận redirect signal và điều hướng trang. |
| Ajax validation lỗi | Lỗi được hiển thị tại form; không điều hướng ngoài ý muốn. |
| Ajax bị từ chối quyền | Response lỗi phù hợp; không trả fragment chứa dữ liệu nhạy cảm. |
| Request thiếu CSRF token | Bị từ chối theo chính sách bảo mật. |
| Session hết hạn | Client xử lý authentication/session expiry rõ ràng; không lặp redirect vô hạn. |
| Flow execution key không hợp lệ | Trả lỗi phù hợp và không chuyển nhầm sang execution khác. |

## 10. Bảo mật URL redirect

Redirect URL có thể đến từ cấu hình server, kết quả flow hoặc input người dùng. Không dùng URL tùy ý do client gửi lên làm đích redirect. Nếu nghiệp vụ cần tham số quay lại, hãy:

- Chỉ cho phép đường dẫn tương đối trong ứng dụng hoặc domain nằm trong allow-list.
- Chuẩn hóa và kiểm tra URL trước khi dùng; từ chối scheme nguy hiểm hoặc URL có host ngoài danh sách.
- Không đưa token, session ID hoặc dữ liệu nhạy cảm vào query string.
- Giữ CSRF protection cho các request thay đổi trạng thái, kể cả Ajax.
- Không coi flow execution key là cơ chế xác thực hoặc phân quyền.

Khi redirect đến hệ thống ngoài như cổng thanh toán, dùng URL callback/return URL đã cấu hình ở server và xác minh chữ ký/trạng thái giao dịch qua kênh server-to-server theo thiết kế tích hợp. Không tin một redirect về trình duyệt như bằng chứng thanh toán thành công.

## 11. Xử lý lỗi và session trong redirect

Redirect có thể xảy ra khi flow kết thúc, người dùng cần đăng nhập lại hoặc session đã hết hạn. Cần phân biệt lỗi nghiệp vụ, lỗi xác thực và lỗi flow execution:

- **Lỗi nghiệp vụ:** có thể hiển thị view lỗi hoặc quay về state cho phép sửa dữ liệu.
- **Chưa đăng nhập hoặc hết phiên:** Spring Security có thể redirect đến trang đăng nhập với request thường; Ajax client cần nhận biết session hết hạn và điều hướng theo giao thức Ajax đã cấu hình.
- **Không có quyền:** trả phản hồi từ chối phù hợp; không redirect đến trang thành công.
- **Flow key không hợp lệ hoặc execution đã kết thúc:** hướng dẫn bắt đầu flow mới nếu nghiệp vụ cho phép; không tự đoán execution key khác.
- **Lỗi server:** trả lỗi 5xx hoặc view lỗi chung theo cấu hình; không giả mạo response thành redirect thành công.

Không lưu toàn bộ flow execution vào URL. SWF sử dụng execution key để định vị execution, còn trạng thái được quản lý qua repository/session theo cấu hình. Khi triển khai nhiều instance, cần bảo đảm session hoặc execution repository được chia sẻ/định tuyến phù hợp.

## 12. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Request thường POST lại khi refresh | Không có PRG sau xử lý event hoặc form action không đúng execution URL. | Kiểm tra redirect và GET tiếp theo. |
| Ajax nhận HTML trang đích nhưng không điều hướng | Client chỉ đọc body của XHR; không xử lý redirect signal. | Cấu hình AjaxHandler và client tương thích. |
| Ajax redirect làm mất trạng thái flow | Request tiếp theo thiếu execution URL/key hoặc session cookie. | Dùng URL do SWF tạo và giữ cookie/session. |
| Fragment response hiển thị cả layout | View trả toàn bộ template thay vì fragment phù hợp. | Tách fragment và render đúng vùng. |
| Redirect đến host lạ | Đích lấy từ input không được kiểm soát. | Dùng URL allow-list và kiểm tra server-side. |
| Thông báo biến mất sau redirect | Flash output không được lưu hoặc bị tiêu thụ quá sớm. | Kiểm tra flash scope và adapter configuration. |
| Ajax không được nhận diện | Header hoặc cấu hình AjaxHandler không khớp client. | Kiểm tra request headers và handler thực tế. |

## 13. Checklist triển khai

- [ ] Form thường POST đến `${flowExecutionUrl}` và gửi đúng `_eventId_...`.
- [ ] Request thay đổi dữ liệu có PRG/redirect phù hợp.
- [ ] Internal transition tiếp tục đúng flow execution; external redirect chỉ dùng khi cần rời flow.
- [ ] `Location` của request thường trỏ đến URL hợp lệ trong ứng dụng hoặc đích được cho phép.
- [ ] Ajax request được nhận diện bởi AjaxHandler tương thích với client.
- [ ] Ajax fragment response chỉ cập nhật vùng giao diện dự kiến.
- [ ] Ajax redirect signal được client xử lý thành điều hướng cấp trang.
- [ ] Flash scope chỉ chứa dữ liệu ngắn hạn cần qua redirect.
- [ ] CSRF, session, authentication và authorization vẫn được áp dụng cho Ajax.
- [ ] Không tin redirect từ cổng thanh toán là xác nhận giao dịch.
- [ ] Có test riêng cho request thường, Ajax, lỗi validation, hết phiên và flow key không hợp lệ.

## 14. Kết luận

Với request thông thường, redirect thường tạo chuỗi POST-Redirect-GET và cập nhật URL trên thanh địa chỉ. Với Ajax, response được JavaScript xử lý nên HTTP redirect không tự động đồng nghĩa với điều hướng toàn trang; ứng dụng cần dùng AjaxHandler và client tương thích để phân biệt fragment update với redirect signal. Khi kiểm tra, hãy theo dõi status, Location, response body, execution key, session và hành vi thực tế của trình duyệt. Thiết kế rõ hai đường đi này giúp Spring Web Flow vừa giữ được PRG cho form thông thường vừa cập nhật giao diện Ajax đúng cách.
