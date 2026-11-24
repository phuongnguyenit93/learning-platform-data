# Window opener isolation: bảo vệ browsing context bằng noopener và COOP

## 1. Window opener là gì?

Khi một trang mở một cửa sổ hoặc tab khác bằng liên kết target="_blank" hay JavaScript window.open(), browser có thể tạo quan hệ **opener** giữa trang mở và trang mới.

Ví dụ:

~~~html
<a href="https://docs.example.test" target="_blank">
  Mở tài liệu
</a>
~~~

Hoặc:

~~~js
const popup = window.open("https://login.example.test", "_blank");
~~~

Trong trang được mở, thuộc tính window.opener có thể tham chiếu tới window của trang đã mở nó. Quan hệ này hữu ích cho các luồng tích hợp như OAuth, thanh toán hoặc popup chọn tài khoản: cửa sổ con có thể gửi kết quả về trang cha qua postMessage.

Nhưng quan hệ opener cũng tạo ra rủi ro. Trang được mở có thể dùng một số thao tác cross-origin được browser cho phép để điều hướng trang mở nó tới một địa chỉ khác. Kẻ tấn công có thể lợi dụng điều này để thay trang gốc bằng giao diện giả mạo. Kỹ thuật này thường được gọi là **reverse tabnabbing**.

**Window opener isolation** là việc kiểm soát hoặc cắt quan hệ giữa các browsing context khi không cần tin cậy lẫn nhau. Hai cơ chế quan trọng là:

- **noopener:** chủ động mở cửa sổ mới mà không tạo quan hệ opener.
- **Cross-Origin-Opener-Policy (COOP):** dùng HTTP response header để kiểm soát việc tài liệu top-level có ở chung browsing context group với opener hay không.

Bài học thuộc chương **Cross-origin isolation** của module **SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY**. Module phân tích ranh giới bảo mật giữa browser, origin, cookie và ứng dụng web; bài này tập trung vào quan hệ opener, việc tách browsing context group, tương thích với popup tích hợp và mối liên hệ giữa COOP, COEP và cross-origin isolation.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích window.opener và những quyền mà một trang được mở có thể sử dụng.
2. Mô tả reverse tabnabbing và lý do SOP không loại bỏ hoàn toàn rủi ro điều hướng opener.
3. Dùng rel=noopener, rel=noreferrer và window.open() features đúng cách.
4. Giải thích COOP và vai trò của browsing context group.
5. Phân biệt các policy phổ biến unsafe-none, same-origin và same-origin-allow-popups.
6. Nhận diện khi COOP làm mất window.opener hoặc khiến tham chiếu popup không còn hoạt động như trước.
7. Triển khai COOP Report-Only và kiểm tra báo cáo trước khi enforce.
8. Giải thích COOP kết hợp COEP để tạo cross-origin isolated environment.
9. Lập kế hoạch tương thích cho OAuth, thanh toán và popup callback.
10. Kiểm chứng hành vi bằng DevTools trên các origin thử nghiệm.

## 2. window.opener và mô hình tin cậy

Giả sử trang A mở trang B:

~~~js
// Chạy trong trang A.
const child = window.open("https://b.example.test", "_blank");
~~~

Nếu quan hệ opener được giữ, trong trang B:

~~~js
window.opener
~~~

có thể tham chiếu tới window của trang A.

Mối quan hệ này không đồng nghĩa B được tự do đọc toàn bộ DOM của A. Nếu A và B khác origin, Same-Origin Policy (SOP) vẫn giới hạn quyền đọc. Tuy nhiên, các Window reference cross-origin vẫn cung cấp một tập thao tác hạn chế; trong đó có các khả năng như focus, close, postMessage và điều hướng một số thuộc tính Location theo quy tắc browser.

Vì vậy, cần tách hai khái niệm:

- **Đọc:** trang B có thể đọc DOM, cookie hoặc state của A hay không?
- **Điều khiển điều hướng:** trang B có thể yêu cầu browser điều hướng A hay không?

SOP chủ yếu bảo vệ việc đọc dữ liệu cross-origin. Nó không có nghĩa một trang cross-origin không thể tác động tới mọi hành vi điều hướng của opener.

### 2.1. Vì sao opener có thể là rủi ro?

Nếu trang B bị xâm nhập, chứa quảng cáo độc hại hoặc thuộc domain không đáng tin, nó có thể cố gắng điều hướng A:

~~~js
if (window.opener) {
  window.opener.location = "https://login-lookalike.example.test";
}
~~~

Người dùng có thể quay lại tab A và nhìn thấy trang giả mạo thay cho ứng dụng ban đầu. Nếu họ không để ý origin trên thanh địa chỉ, họ có thể nhập thông tin đăng nhập vào trang giả.

Ví dụ này mô tả khả năng điều hướng opener trong các điều kiện browser cho phép. Nó không chứng minh trang B có thể đọc nội dung A; SOP vẫn áp dụng cho truy cập dữ liệu.

### 2.2. Reverse tabnabbing

Một luồng điển hình:

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant A as Trang ứng dụng A
    participant B as Trang ngoài B
    U->>A: Bấm liên kết mở tab mới
    A->>B: Mở B với quan hệ opener
    B->>B: Nhận window.opener
    B->>A: Yêu cầu điều hướng opener tới trang giả
    A-->>U: Tab gốc hiển thị trang giả mạo
~~~

Rủi ro tăng khi ứng dụng mở liên kết tới nội dung do người dùng kiểm soát, trang quảng cáo, đối tác không có cùng mức tin cậy hoặc URL redirect không được kiểm tra.

## 3. SOP không thay thế noopener

SOP hạn chế trang cross-origin đọc dữ liệu của nhau. Nhưng khi có opener, trang được mở vẫn có thể dùng một số API của Window được phép qua ranh giới origin.

Ví dụ, một trang cross-origin thường không thể đọc:

~~~js
window.opener.document.body.innerHTML
~~~

nhưng có thể có khả năng yêu cầu điều hướng:

~~~js
window.opener.location = "https://example.test";
~~~

Các chi tiết truy cập cross-origin được browser giới hạn theo mô hình Window/Location. Không dựa vào SOP như biện pháp duy nhất để ngăn reverse tabnabbing.

Dùng noopener khi không cần cửa sổ mới truy cập opener. Nếu cần trao đổi kết quả, thiết kế một giao thức có chủ đích với postMessage, origin validation và targetOrigin chính xác; cân nhắc COOP compatibility để bảo đảm quan hệ browsing context vẫn tồn tại.

## 4. rel=noopener cho liên kết mở tab mới

Cách đơn giản để ngăn trang đích nhận opener là thêm rel=noopener:

~~~html
<a
  href="https://external.example.test/article"
  target="_blank"
  rel="noopener"
>
  Mở bài viết
</a>
~~~

Với noopener, trang mới không nhận được tham chiếu window.opener tới trang mở nó. Điều này ngăn trang mới dùng opener để điều hướng tab gốc.

### 4.1. noopener không chặn việc mở tab

noopener chỉ cắt quan hệ opener. Nó không có nghĩa browser không mở URL đích. Trang mới vẫn có thể tải và hoạt động như một tab độc lập.

### 4.2. Browser hiện đại và target=_blank

Các browser hiện đại áp dụng hành vi implicit noopener cho phần lớn hyperlink target="_blank". Tuy nhiên, khai báo rel=noopener tường minh vẫn hữu ích:

- Làm rõ ý định bảo mật cho người review.
- Giảm phụ thuộc vào hành vi browser cũ.
- Giúp code dễ nhận diện khi target có thể được thay đổi động.
- Bảo vệ các luồng mở tab được tạo từ template hoặc component.

Không thêm rel=opener trừ khi ứng dụng thực sự cần quan hệ opener và đã đánh giá rủi ro.

### 4.3. noopener và named target

noopener cũng ảnh hưởng việc tái sử dụng browsing context có tên. Với target không phải các giá trị đặc biệt như _self, _parent, _top, browser xử lý như một browsing context mới thay vì cho phép liên kết mở điều hướng context đã đặt tên trong một số trường hợp theo quy tắc HTML.

Nếu ứng dụng dựa vào named target để tái sử dụng popup, cần kiểm tra hành vi khi thêm noopener và chọn thiết kế phù hợp.

## 5. rel=noreferrer và khác biệt với noopener

Một lựa chọn khác:

~~~html
<a
  href="https://external.example.test"
  target="_blank"
  rel="noreferrer"
>
  Mở trang ngoài
</a>
~~~

noreferrer yêu cầu browser không gửi thông tin Referer trong request theo chính sách tương ứng và bao hàm hành vi noopener.

| Giá trị | Cắt window.opener | Ảnh hưởng Referer |
| --- | --- | --- |
| noopener | Có | Không tự yêu cầu bỏ Referer. |
| noreferrer | Có | Không gửi Referer trong điều kiện áp dụng. |
| noopener noreferrer | Có | Không gửi Referer trong điều kiện áp dụng. |

Chỉ dùng noreferrer khi muốn giảm rò rỉ thông tin trang nguồn. Việc bỏ Referer có thể ảnh hưởng analytics, kiểm tra nguồn truy cập hoặc luồng tích hợp. Nếu chỉ cần ngăn reverse tabnabbing, noopener thường đủ.

## 6. window.open() và feature noopener

JavaScript có thể chỉ định noopener trong feature string:

~~~js
const popup = window.open(
  "https://external.example.test",
  "_blank",
  "noopener"
);
~~~

Có thể kết hợp noreferrer:

~~~js
window.open(
  "https://external.example.test",
  "_blank",
  "noopener,noreferrer"
);
~~~

Khi dùng noopener, window.open() có thể trả về null theo hành vi API. Vì vậy không dùng giá trị trả về như một cách duy nhất để phân biệt popup bị browser chặn với popup được mở nhưng đã tách opener.

Nếu cần theo dõi trạng thái popup, hãy thiết kế flow riêng và kiểm tra behavior trên browser mục tiêu. Không bỏ noopener chỉ để lấy được Window handle nếu trang ngoài không thực sự đáng tin.

### 6.1. Khi popup cần callback

Một số tích hợp yêu cầu popup gửi kết quả về trang mở. Nếu dùng noopener, popup không có window.opener để gọi postMessage về trang đó.

Các lựa chọn thiết kế:

- Dùng redirect về một callback page cùng origin của ứng dụng.
- Dùng server-side state và polling một endpoint đã xác thực.
- Dùng một popup bridge có origin tin cậy và giữ quan hệ opener có kiểm soát.
- Dùng postMessage với targetOrigin chính xác khi opener relationship được giữ và COOP policy tương thích.

Không hy sinh opener isolation cho mọi liên kết ngoài chỉ vì một luồng popup cần callback. Tách route hoặc flow tích hợp có nhu cầu đặc biệt.

## 7. Cross-Origin-Opener-Policy (COOP) là gì?

**Cross-Origin-Opener-Policy (COOP)** là HTTP response header cho phép website kiểm soát việc tài liệu top-level có được đặt trong cùng **browsing context group** với opener hay không.

Ví dụ:

~~~http
Cross-Origin-Opener-Policy: same-origin
~~~

Khi policy yêu cầu same-origin isolation, browser có thể đặt tài liệu vào browsing context group riêng nếu opener hoặc popup không có policy tương thích. Khi tách group, quan hệ opener có thể bị cắt và tham chiếu tới cửa sổ kia không còn hoạt động như trước.

COOP tác động ở mức browsing context group, không chỉ kiểm tra xem JavaScript có được đọc DOM hay không. Nó bổ sung một ranh giới giữa các top-level browsing contexts và có thể ảnh hưởng tới popup, postMessage, window.closed và một số tích hợp.

### 7.1. Browsing context group

Một browsing context group là nhóm các browsing context có thể giữ những quan hệ đồng bộ nhất định, ví dụ opener. Browser có thể tách các context sang group khác khi COOP policy không tương thích.

Sơ đồ khái quát:

~~~mermaid
flowchart TD
    A["Tab A: portal.example.test"] --> B["Mở popup B"]
    B --> C{"COOP có tương thích?"}
    C -->| "Có" | D["Có thể giữ cùng browsing context group"]
    C -->| "Không" | E["Browser tách browsing context group"]
    D --> F["Opener relationship có thể còn"]
    E --> G["Opener relationship bị cắt"]
~~~

Browsing context group là khái niệm web platform. Không nên đồng nhất tuyệt đối nó với một OS process; browser có thể dùng nhiều process hoặc chia sẻ process theo implementation và chính sách riêng.

### 7.2. COOP là response policy

COOP được gửi qua HTTP response header của tài liệu top-level. Đặt một đoạn JavaScript kiểm tra window.opener sau khi tải không thay thế policy này.

COOP không phải thuộc tính HTML trên iframe và không được áp dụng bằng meta element. Header phải được cấu hình ở server, reverse proxy hoặc nền tảng phân phối response.

## 8. Các giá trị COOP phổ biến

Các policy thường gặp:

| Giá trị | Hành vi khái quát | Trường hợp sử dụng |
| --- | --- | --- |
| unsafe-none | Hành vi mặc định, cho phép tương tác opener theo các quy tắc khác của browser. | Ứng dụng chưa bật COOP. |
| same-origin | Tách tài liệu top-level khỏi browsing context group không tương thích về origin/policy. | Trang cần opener isolation mạnh. |
| same-origin-allow-popups | Giữ khả năng tương tác với một số popup không opt-in COOP, đồng thời áp dụng ranh giới theo quy tắc tương thích. | Tích hợp popup như OAuth hoặc thanh toán cần đánh giá. |

Chi tiết tương thích phụ thuộc policy của cả opener và opened document. Không giả định chỉ nhìn header của một phía là đủ để biết popup sẽ giữ opener hay bị tách group.

### 8.1. unsafe-none

unsafe-none là hành vi mặc định nếu response không khai báo COOP. Tài liệu có thể ở cùng browsing context group với opener cross-origin theo các quy tắc browser và SOP.

Điều này thuận tiện cho tích hợp cũ nhưng không tạo ranh giới opener isolation rõ ràng. Nếu ứng dụng mở nhiều trang ngoài, hãy dùng noopener cho các liên kết không cần opener.

### 8.2. same-origin

~~~http
Cross-Origin-Opener-Policy: same-origin
~~~

same-origin yêu cầu browser giữ tài liệu trong browsing context group phù hợp với các tài liệu cùng origin và policy tương thích. Nếu mở từ hoặc mở một tài liệu cross-origin không tương thích, browser có thể tách group và cắt quan hệ opener.

Đây là policy thường được dùng khi ứng dụng muốn cô lập cửa sổ khỏi nội dung cross-origin và là một điều kiện quan trọng cho cross-origin isolation khi kết hợp COEP.

Tác động cần kiểm thử:

- window.opener có thể trở thành null ở phía popup.
- Tham chiếu WindowProxy mà opener giữ có thể thể hiện như đã đóng hoặc mất liên kết.
- postMessage qua quan hệ popup có thể không còn hoạt động.
- Một số flow OAuth/payment dựa vào callback popup có thể thất bại.
- Kiểm tra window.closed có thể không phản ánh popup còn mở trên màn hình hay không theo cách ứng dụng cũ kỳ vọng.

### 8.3. same-origin-allow-popups

~~~http
Cross-Origin-Opener-Policy: same-origin-allow-popups
~~~

Policy này được thiết kế cho trường hợp ứng dụng cần giữ tương tác với một số popup không opt-in COOP, chẳng hạn trang xác thực hoặc thanh toán bên ngoài. Nó cho phép các quan hệ popup tương thích theo quy tắc COOP, trong khi vẫn có thể cô lập với những context có policy không tương thích.

Đây là một thỏa hiệp tương thích, không phải cách ly nghiêm ngặt như same-origin trong mọi tình huống. Cần đánh giá trang popup, luồng callback và dữ liệu được trao đổi trước khi chọn.

Không chọn same-origin-allow-popups chỉ vì same-origin làm hỏng popup; hãy xác định chính xác popup nào cần opener và liệu có thể thay bằng callback bridge hoặc server-side flow hay không.

### 8.4. Giá trị policy và browser support

COOP là tính năng của browser hiện đại, nhưng hỗ trợ và chi tiết hành vi có thể khác theo phiên bản. Tài liệu/spec có thể bổ sung giá trị policy; khi dùng giá trị ngoài các lựa chọn phổ biến trong bài này, kiểm tra compatibility matrix của browser mục tiêu.

Các browser không hỗ trợ COOP có thể bỏ qua header. Vì vậy vẫn cần rel=noopener cho liên kết mở tab ngoài và không dựa vào COOP làm lớp duy nhất cho mọi client.

## 9. COOP ảnh hưởng cả opener và opened document

COOP không chỉ là một header để popup “tự bảo vệ”. Nó tham gia quyết định browsing context group cho tài liệu top-level và có thể làm thay đổi quan hệ giữa hai phía.

Ví dụ:

- A mở B.
- A có COOP same-origin.
- B có policy không tương thích.
- Browser có thể đưa B vào browsing context group khác.
- Quan hệ opener giữa A và B bị cắt theo kết quả xử lý.

Tương tự, một trang có COOP same-origin được mở từ trang cross-origin có thể bị tách khỏi opener. Do đó, kiểm thử cả hai hướng:

1. Ứng dụng có mở popup cross-origin không?
2. Ứng dụng có được mở từ một trang cross-origin không?
3. Trang popup có response COOP riêng không?
4. Redirect có đưa popup qua một origin/policy khác không?

### 9.1. Không thể nới policy ở một phía để ghi đè policy phía kia

COOP compatibility phụ thuộc cả tài liệu opener và opened document. Một trang không thể đơn phương yêu cầu browser bỏ qua policy isolation nghiêm ngặt của trang còn lại.

Khi tích hợp không hoạt động, xem header thực tế của cả hai response và luồng điều hướng. Không chỉ thay đổi header trên ứng dụng chính rồi giả định popup sẽ hoạt động.

## 10. COOP và postMessage

postMessage thường được dùng để popup trả kết quả về opener:

~~~js
// Trong popup.
window.opener.postMessage(
  { type: "auth-complete", code: "temporary-code" },
  "https://app.example.test"
);
~~~

Parent nhận:

~~~js
window.addEventListener("message", (event) => {
  if (event.origin !== "https://login.example.test") return;
  if (event.source !== popupReference) return;
  if (event.data?.type !== "auth-complete") return;

  completeLogin(event.data);
});
~~~

Cách này chỉ hoạt động nếu opener relationship và browsing context communication còn tồn tại. Nếu COOP tách group hoặc popup được mở với noopener, window.opener có thể là null và callback không tới được parent qua cách này.

### 10.1. Kiểm tra origin vẫn cần thiết

Nếu popup callback hoạt động, receiver vẫn phải xác minh:

- event.origin chính xác của popup callback.
- event.source là popup dự kiến.
- Schema, kiểu và trạng thái message.
- State/nonce của giao dịch đăng nhập hoặc thanh toán.
- Code chỉ được dùng một lần và được backend xác minh.

COOP không thay event.origin, event.source hoặc kiểm tra state trong OAuth/OIDC.

### 10.2. Tránh gửi token dài hạn qua opener

Nếu cần callback, ưu tiên gửi một authorization code ngắn hạn, dùng một lần và ràng buộc với state/PKCE theo flow tương ứng. Backend cần đổi code và xác minh giao dịch. Không gửi access token hoặc refresh token dài hạn qua postMessage chỉ vì opener relationship còn tồn tại.

## 11. Thiết kế OAuth và thanh toán khi bật COOP

Một số flow popup truyền thống dựa vào:

1. Ứng dụng mở trang nhà cung cấp bằng window.open().
2. Người dùng đăng nhập hoặc xác nhận.
3. Nhà cung cấp redirect popup về callback URL của ứng dụng.
4. Callback gọi window.opener.postMessage().
5. Trang chính hoàn tất flow.

COOP same-origin hoặc noopener có thể làm bước 4 không còn khả dụng.

Các phương án thiết kế:

| Phương án | Đặc điểm | Khi phù hợp |
| --- | --- | --- |
| Giữ popup opener có kiểm soát | Chọn COOP tương thích, giới hạn popup tin cậy, validate message nghiêm ngặt. | Tích hợp legacy chưa thể thay đổi. |
| Same-origin callback bridge | Popup redirect về route callback cùng origin, gửi kết quả sau khi kiểm tra state. | Có thể duy trì một callback page thuộc ứng dụng. |
| Server-side completion | Backend nhận callback, cập nhật transaction; trang chính poll trạng thái đã xác thực. | Flow cần độ tin cậy cao, không phụ thuộc opener. |
| Top-level redirect | Điều hướng toàn trang qua nhà cung cấp rồi quay lại. | Không cần giữ trạng thái popup. |
| MessageChannel có bootstrap an toàn | Dùng channel riêng sau khi xác thực origin và context ban đầu. | Hai ứng dụng có giao thức tích hợp được kiểm soát. |

Nếu dùng popup opener, giới hạn nó cho route tích hợp cần thiết. Các liên kết ngoài thông thường vẫn nên dùng noopener.

## 12. COOP và window.closed

Ứng dụng thường kiểm tra popup:

~~~js
if (popup.closed) {
  // Người dùng đóng popup?
}
~~~

Khi COOP tách browsing context group, tham chiếu tới popup có thể bị browser xử lý như đã đóng đối với opener, dù cửa sổ popup vẫn còn hiển thị. Điều này có thể làm code polling cũ hiểu sai rằng người dùng đã đóng popup.

Không dùng window.closed như nguồn duy nhất xác định flow hoàn tất. Hãy dựa vào callback đã xác thực, server-side transaction status hoặc một trạng thái giao thức rõ ràng.

## 13. COOP Report-Only và báo cáo

Trước khi enforce COOP, có thể dùng chế độ Report-Only để quan sát tác động dự kiến:

~~~http
Cross-Origin-Opener-Policy-Report-Only: same-origin; report-to="coop"
Reporting-Endpoints: coop="https://app.example.test/reports/coop"
~~~

Header Report-Only cho phép browser ghi nhận các tình huống policy dự kiến sẽ gây browsing context group switch hoặc ảnh hưởng opener mà chưa áp dụng policy đó như chế độ enforce.

Cần kiểm tra browser mục tiêu và cấu hình Reporting API thực tế. Một số hệ thống cũ dùng cơ chế báo cáo khác; không giả định mọi browser gửi report cùng định dạng hoặc mọi report đều có đầy đủ URL.

### 13.1. Report-Only không bảo vệ người dùng

Report-Only chỉ giúp quan sát. Nếu response chưa có COOP enforce hoặc noopener, quan hệ opener vẫn có thể tồn tại. Không xem việc nhận report là đã ngăn reverse tabnabbing.

### 13.2. Quy trình rollout

1. Kiểm kê tất cả popup, window.open và liên kết target=_blank.
2. Xác định flow cần window.opener hoặc popup callback.
3. Thêm COOP Report-Only ở staging.
4. Mở các luồng OAuth, thanh toán, đăng nhập, dashboard và tích hợp đối tác.
5. Thu thập report, console message và lỗi callback.
6. Sửa flow không cần opener; dùng noopener cho liên kết ngoài.
7. Chọn policy enforce phù hợp với các popup thực sự cần giữ quan hệ.
8. Triển khai từng bước và theo dõi transaction failure, window.closed và postMessage.

Không tự động nới policy chỉ vì một report xuất hiện. Xác định popup có phải tích hợp hợp lệ và có thể thay bằng callback bridge hay không.

## 14. COOP và Cross-Origin-Embedder-Policy (COEP)

COOP thường được nhắc cùng **Cross-Origin-Embedder-Policy (COEP)** khi ứng dụng cần cross-origin isolation cho một số API web.

Một cấu hình thường dùng:

~~~http
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
~~~

Trong browser hỗ trợ, trên secure context và khi các điều kiện liên quan được đáp ứng, kết hợp COOP same-origin với COEP phù hợp có thể làm:

~~~js
window.crossOriginIsolated === true
~~~

Cross-origin isolation có thể cần cho những tính năng như SharedArrayBuffer trong browser hiện đại và một số khả năng hiệu năng/timing có độ phân giải cao.

### 14.1. COOP một mình không đủ

Chỉ đặt:

~~~http
Cross-Origin-Opener-Policy: same-origin
~~~

không tự đảm bảo crossOriginIsolated là true. Ứng dụng còn cần COEP tương thích, secure context, hỗ trợ browser và không bị policy cấp cao hơn hạn chế.

### 14.2. COEP require-corp

Với:

~~~http
Cross-Origin-Embedder-Policy: require-corp
~~~

các tài nguyên cross-origin được nhúng cần đáp ứng quy tắc CORS hoặc Cross-Origin-Resource-Policy (CORP) tương ứng. Điều này có thể làm ảnh, font, script, worker hoặc tài nguyên từ CDN bị chặn nếu server nguồn chưa opt in.

Một lựa chọn khác là credentialless trong browser hỗ trợ; nó thay đổi cách xử lý credential cho một số request cross-origin no-CORS. Không chọn chỉ để làm lỗi biến mất nếu chưa hiểu tác động cookie và cache.

### 14.3. Kiểm tra crossOriginIsolated

Trong Console:

~~~js
console.log(window.crossOriginIsolated);
~~~

Nếu false, kiểm tra COOP, COEP, secure context, browser support và lỗi resource bị chặn. Đây là tín hiệu runtime hữu ích, không phải phép kiểm tra toàn diện cho mọi yêu cầu bảo mật của ứng dụng.

## 15. COOP không phải CSP và không thay SOP

Ba cơ chế có vai trò khác nhau:

| Cơ chế | Ranh giới chính | Câu hỏi |
| --- | --- | --- |
| SOP | Truy cập dữ liệu cross-origin | Script origin này có được đọc dữ liệu origin kia không? |
| COOP | Quan hệ giữa top-level browsing contexts | Trang có ở chung browsing context group với opener cross-origin không? |
| CSP | Nguồn tài nguyên và một số hành vi document | Trang được tải script/frame/image từ đâu và thực thi theo policy nào? |
| COEP | Tài nguyên cross-origin được nhúng | Tài nguyên cross-origin có opt in theo yêu cầu embedding không? |

COOP không tự sanitize HTML, không ngăn XSS, không kiểm tra CSRF và không xác thực message. Nó giảm một số quan hệ cross-origin ở cấp browsing context.

Nếu XSS đã chạy trong cùng origin của ứng dụng, COOP không ngăn script đó thao tác DOM hoặc gọi API mà trang có quyền. Vẫn cần output encoding, safe DOM APIs, CSP, Trusted Types và backend authorization.

## 16. COOP áp dụng ở đâu?

COOP là policy cho tài liệu top-level. Không dùng header COOP trên một iframe như cách kiểm soát opener của iframe hoặc giới hạn ai được nhúng iframe đó.

Với iframe, các cơ chế khác có vai trò riêng:

- frame-src ở parent giới hạn URL frame được tải.
- frame-ancestors ở child giới hạn ancestor được phép nhúng child.
- sandbox giới hạn khả năng của nội dung frame.
- postMessage dùng để trao đổi dữ liệu có kiểm tra origin/source.

Nếu một trang trong iframe mở popup hoặc top-level window, cần xem xét browsing context, opener relationship và các policy của tài liệu top-level liên quan. Không giả định COOP trên iframe response tạo cùng tác động như COOP trên top-level response.

## 17. Các lỗi triển khai thường gặp

1. **Chỉ dựa vào SOP để ngăn reverse tabnabbing:** SOP hạn chế đọc nhưng không loại bỏ mọi thao tác điều hướng opener.
2. **Quên rel=noopener:** liên kết ngoài mở tab mới có thể giữ opener theo hành vi browser cũ hoặc cấu hình cụ thể.
3. **Dùng noreferrer mà không hiểu tác động:** Referer bị loại bỏ, có thể ảnh hưởng analytics và tích hợp.
4. **Cho rằng noopener không mở tab:** nó cắt quan hệ opener, không chặn việc mở URL.
5. **Dùng window.open noopener nhưng vẫn trông chờ handle:** API có thể trả null.
6. **Bật COOP same-origin mà không kiểm tra popup:** OAuth/payment callback có thể bị cắt.
7. **Nghĩ COOP chỉ ảnh hưởng popup do trang mở:** trang cũng có thể bị tách khỏi opener đã mở nó.
8. **Chỉ kiểm tra window.opener:** tham chiếu WindowProxy và trạng thái browsing context có thể thay đổi sau navigation/COOP.
9. **Dựa vào window.closed để biết popup đã đóng:** COOP separation có thể khiến tham chiếu trông như đã đóng.
10. **Cho rằng same-origin-allow-popups tương đương same-origin:** policy này giữ một số popup relationship tương thích và có trade-off khác.
11. **Cho rằng COOP một mình bật cross-origin isolation:** cần COEP và điều kiện browser/runtime.
12. **Bật COEP mà không kiểm tra CDN:** tài nguyên cross-origin có thể bị chặn do thiếu CORS/CORP.
13. **Đặt COOP trong meta tag:** COOP cần HTTP response header.
14. **Chỉ cấu hình một phía của popup:** compatibility phụ thuộc policy của cả opener và opened document.
15. **Dùng COOP thay postMessage validation:** COOP không xác thực event.origin, event.source hay payload.
16. **Coi COOP là phòng vệ XSS toàn diện:** script độc cùng origin vẫn có quyền của document.
17. **Không kiểm thử browser cũ:** browser bỏ qua COOP vẫn cần noopener và các biện pháp SOP-safe.
18. **Bỏ qua redirect cuối:** policy của document cuối cùng và luồng redirect có thể ảnh hưởng kết quả tích hợp.

## 18. Thực hành A — Quan sát window.opener và noopener

Tạo hai trang local/test trên hai origin khác nhau, ví dụ app.example.test và external.example.test.

Ở trang A, tạo liên kết:

~~~html
<a href="https://external.example.test/popup" target="_blank">
  Mở popup không noopener
</a>
~~~

Trong trang B, mở DevTools Console và kiểm tra:

~~~js
console.log(window.opener);
~~~

Sau đó thêm rel=noopener vào liên kết và thử lại. Quan sát window.opener ở B.

**Mục tiêu:** xác nhận noopener cắt quan hệ opener mà vẫn cho phép mở trang mới.

## 19. Thực hành B — Quan sát COOP same-origin

Trên response HTML của trang A, gửi:

~~~http
Cross-Origin-Opener-Policy: same-origin
~~~

Dùng A mở B ở origin khác. Kiểm tra:

- window.opener trong B.
- Giá trị popup.closed mà A quan sát.
- Khả năng trao đổi postMessage.
- Console message và response headers của cả A/B.

Thử đổi policy của B và ghi lại khác biệt. Chỉ dùng origin thử nghiệm, không dùng flow đăng nhập thật.

## 20. Thực hành C — Report-Only trước khi enforce

Trên staging, gửi:

~~~http
Cross-Origin-Opener-Policy-Report-Only: same-origin; report-to="coop"
Reporting-Endpoints: coop="https://app.example.test/reports/coop"
~~~

Chạy các flow:

- Mở popup đăng nhập.
- Mở cổng thanh toán thử nghiệm.
- Quay lại callback route.
- Gửi postMessage.
- Đóng popup và kiểm tra trạng thái.

Ghi nhận report, Console và lỗi giao diện. Sau khi hiểu tác động, triển khai COOP enforce trên staging rồi mới cân nhắc production.

## 21. Thực hành D — Kiểm tra cross-origin isolation

Trên môi trường HTTPS test, cấu hình:

~~~http
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
~~~

Mở Console:

~~~js
console.log({
  isolated: window.crossOriginIsolated,
  sharedArrayBuffer: typeof SharedArrayBuffer
});
~~~

Nếu crossOriginIsolated là false, kiểm tra:

1. COOP có nằm trên response top-level không?
2. COEP có được gửi trên response cuối không?
3. Browser có hỗ trợ tính năng không?
4. Trang có phải secure context không?
5. Tài nguyên cross-origin có CORS/CORP phù hợp không?
6. Console có báo tài nguyên bị COEP chặn không?

Không thêm allowlist rộng chỉ để vượt qua lỗi. Sửa response policy ở nguồn tài nguyên hoặc thay nguồn CDN bằng endpoint phù hợp.

## 22. Checklist review Window opener isolation

- [ ] Kiểm kê target=_blank, window.open và các popup được mở bởi ứng dụng.
- [ ] Dùng rel=noopener cho liên kết ngoài không cần callback.
- [ ] Dùng noreferrer chỉ khi cần bỏ Referer và hiểu ảnh hưởng.
- [ ] Không tin trang đích chỉ vì nó mở từ ứng dụng.
- [ ] Xác định mọi flow thực sự cần window.opener hoặc popup handle.
- [ ] Chọn COOP theo nhu cầu: unsafe-none, same-origin hoặc same-origin-allow-popups.
- [ ] Đánh giá policy của cả opener và opened document.
- [ ] Kiểm tra redirect và response header cuối cùng.
- [ ] Kiểm tra window.opener, popup.closed và postMessage sau khi bật COOP.
- [ ] Không dựa vào window.closed làm tín hiệu duy nhất của popup lifecycle.
- [ ] Với OAuth/OIDC, xác minh state, PKCE và callback theo flow chuẩn.
- [ ] Không gửi access/refresh token dài hạn qua postMessage.
- [ ] Dùng exact targetOrigin và xác minh event.origin/event.source khi giữ popup callback.
- [ ] Có phương án callback bridge hoặc server-side completion nếu opener bị cắt.
- [ ] Dùng COOP Report-Only trước khi enforce.
- [ ] Gửi COOP bằng HTTP response header trên tài liệu top-level.
- [ ] Không nhầm COOP với frame-ancestors hoặc frame-src.
- [ ] Nếu cần cross-origin isolation, kết hợp COOP với COEP phù hợp.
- [ ] Kiểm tra CORS/CORP cho tài nguyên khi bật COEP.
- [ ] Xác minh window.crossOriginIsolated trong browser mục tiêu.
- [ ] Giữ noopener như fallback cho browser không hỗ trợ COOP.
- [ ] Theo dõi báo cáo, lỗi popup và lỗi tích hợp sau rollout.

## 23. Những ngộ nhận thường gặp

| Nhận định | Đánh giá | Giải thích |
| --- | --- | --- |
| “SOP ngăn trang ngoài điều hướng opener.” | **Sai** | SOP giới hạn đọc dữ liệu; một số thao tác điều hướng vẫn được phép. |
| “noopener chặn mở tab mới.” | **Sai** | Tab vẫn mở; quan hệ opener bị cắt. |
| “noreferrer và noopener giống hệt nhau.” | **Sai** | noreferrer còn ngăn gửi Referer trong điều kiện áp dụng. |
| “target=_blank luôn có noopener ở mọi browser.” | **Sai** | Browser hiện đại thường mặc định; vẫn nên khai báo rõ cho tương thích. |
| “COOP là một CSP directive.” | **Sai** | COOP là HTTP response header riêng. |
| “COOP same-origin chỉ tác động document popup.” | **Sai** | Policy có thể tách tài liệu khỏi opener cross-origin theo cả hai hướng. |
| “same-origin-allow-popups là isolation mạnh nhất.” | **Sai** | Nó giữ một số popup relationship tương thích và có trade-off. |
| “COOP same-origin luôn tương thích với OAuth popup.” | **Sai** | Có thể cắt opener và làm callback cũ thất bại. |
| “window.opener null chứng minh popup đã đóng.” | **Sai** | opener có thể null do noopener hoặc COOP separation. |
| “popup.closed luôn phản ánh cửa sổ còn hiển thị.” | **Sai** | COOP có thể làm tham chiếu bị tách và trông như đã đóng. |
| “COOP tự bật crossOriginIsolated.” | **Sai** | Cần COEP và các điều kiện runtime/browser. |
| “COEP chỉ ảnh hưởng script.” | **Sai** | Nhiều loại tài nguyên cross-origin có thể cần CORS/CORP. |
| “COOP thay thế event.origin validation.” | **Sai** | COOP không xác thực message sender hoặc payload. |
| “COOP chặn XSS.” | **Sai** | XSS cùng origin vẫn có thể thao tác DOM và API. |
| “COOP trong iframe có tác dụng như top-level.” | **Sai** | COOP áp dụng cho tài liệu top-level, không phải cơ chế kiểm soát iframe. |

## 24. Tổng kết

Window opener tạo một quan hệ giữa trang mở và trang mới. Quan hệ này hữu ích cho popup tích hợp nhưng có thể cho phép trang đích tác động tới opener, dẫn đến reverse tabnabbing. rel=noopener là cách đơn giản để cắt quan hệ đó khi không cần callback.

COOP kiểm soát việc tài liệu top-level chia sẻ browsing context group với opener. Policy same-origin có thể tách các context không tương thích và làm mất opener relationship; same-origin-allow-popups giữ một số tích hợp popup theo quy tắc tương thích. Cần kiểm thử cả hai phía trước khi enforce.

Ba nguyên tắc cần nhớ:

1. **Cắt opener khi không cần:** dùng noopener cho liên kết ngoài và chỉ giữ callback popup trong flow đã xác minh.
2. **Rollout COOP có kiểm soát:** hiểu same-origin và same-origin-allow-popups, dùng Report-Only, kiểm tra OAuth/payment, postMessage, window.closed và redirect.
3. **Phân biệt opener isolation với cross-origin isolation:** COOP quản lý browsing context group; COEP cùng COOP có thể bật cross-origin isolation trong browser phù hợp. Chúng không thay SOP, CSP, CORS, Trusted Types hay authorization.

Khi review một popup, hãy hỏi: **trang mới có cần window.opener không, nếu bị điều hướng thì có thể tác động tab gốc thế nào, COOP policy của hai response có tương thích, callback có phụ thuộc postMessage, và ứng dụng đã có phương án khi opener bị cắt chưa?** Trả lời rõ những câu hỏi này giúp cô lập cửa sổ ngoài mà vẫn giữ các tích hợp cần thiết.
