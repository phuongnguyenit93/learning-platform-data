# Feature delegation

> **Chương:** Permissions Policy  
> **Học phần:** Application Security — Browser Security (SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY)

Một trang web có thể nhúng video, bản đồ, widget họp hoặc ứng dụng của đối tác trong iframe. Một số widget cần dùng browser feature như camera, microphone, geolocation, fullscreen hoặc clipboard. Việc tải được iframe không có nghĩa frame đó tự động được dùng mọi feature; browser cần biết trang cha có cho phép và có delegate quyền đó cho frame hay không.

**Feature delegation** là quá trình một tài liệu cho phép browsing context con sử dụng một browser feature trong phạm vi đã được kiểm soát. Với iframe, quyền này thường được quyết định qua nhiều lớp: Permissions Policy trên response của trang cha, thuộc tính allow trên iframe và policy của tài liệu con. Một ancestor đã từ chối feature thì frame sâu hơn không thể tự bật lại bằng cách thêm allow.

Feature delegation không phải là cấp quyền thiết bị cho người dùng. Browser vẫn áp dụng secure context, permission prompt, user activation và các điều kiện riêng của API. Mục tiêu là giới hạn frame nào có thể yêu cầu feature, sau đó để browser và người dùng quyết định quyền sử dụng thực tế.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích feature delegation giữa parent document và iframe.
2. Phân biệt Permissions Policy response header với thuộc tính allow của iframe.
3. Cấu hình allowlist chính xác cho origin được nhúng.
4. Mô tả cách policy được kế thừa qua iframe lồng nhau.
5. Hiểu vai trò của từ khóa src trong iframe allow.
6. Cấu hình iframe động trước khi tải nội dung.
7. Phân biệt feature delegation với user permission, sandbox, CSP và SOP.
8. Chẩn đoán trường hợp API bị chặn ở parent hoặc child frame.
9. Thiết kế và kiểm thử luồng delegate feature an toàn.

## 2. Vì sao cần delegate feature?

Giả sử ứng dụng tại app.example.com nhúng dịch vụ họp tại meet.example.net. Dịch vụ họp cần camera và microphone, nhưng ứng dụng còn nhúng quảng cáo, widget chat và dashboard từ nhiều nhà cung cấp khác. Nếu cấp quyền rộng cho mọi frame, nội dung không liên quan có thể yêu cầu sử dụng những tính năng nhạy cảm.

Feature delegation cho phép ứng dụng giới hạn quyền theo từng frame:

- Trang chính có thể dùng camera nếu sản phẩm cần.
- Frame họp được cấp camera và microphone.
- Widget chat chỉ được dùng các API cần thiết cho chat.
- Frame quảng cáo không được cấp camera, microphone hoặc geolocation.

Đây là cách áp dụng nguyên tắc quyền tối thiểu cho browser feature. Khi một tích hợp thay đổi nhà cung cấp hoặc origin, allowlist cũng cần được review.

## 3. Ba lớp quyết định quyền trong iframe

Với một iframe cross-origin, cần xem xét ba lớp:

| Lớp | Nơi cấu hình | Vai trò |
| --- | --- | --- |
| Policy của parent | HTTP response header Permissions-Policy của trang cha | Xác định parent có thể sử dụng feature và có thể cho phép origin con nào |
| Container policy | Thuộc tính allow trên element iframe | Delegate feature cho browsing context được nhúng cụ thể |
| Policy của child | HTTP response header Permissions-Policy của tài liệu con | Có thể tiếp tục giới hạn feature trong child và các context con do child tạo |

Các lớp này phối hợp với policy được kế thừa. Thuộc tính allow không thể mở lại feature mà policy của ancestor đã từ chối. Header của child cũng không thể tự nâng quyền vượt qua giới hạn đã được kế thừa từ parent.

Ví dụ, nếu parent response đặt camera=(), việc thêm allow='camera' trên iframe không cấp lại camera. Nếu parent cho phép meet.example.net và iframe delegate camera cho origin của src, child vẫn cần đáp ứng policy riêng, secure context và user permission.

## 4. Luồng delegate từ parent tới child

Ví dụ ứng dụng tại https://app.example.com nhúng https://meet.example.net:

~~~http
Permissions-Policy: camera=("https://meet.example.net"), microphone=("https://meet.example.net"), geolocation=()
~~~

Trên iframe:

~~~html
<iframe
  src="https://meet.example.net/room/123"
  allow="camera 'src'; microphone 'src'; fullscreen 'src'"
  title="Phòng họp với đối tác"></iframe>
~~~

Parent response cho phép origin cuộc họp sử dụng camera và microphone. Thuộc tính allow trên iframe delegate hai feature đó cho frame có origin từ src; fullscreen cũng được delegate trong ví dụ. Geolocation bị từ chối ở parent.

Nếu parent không cần tự sử dụng camera/microphone, không cần thêm self vào allowlist. Nếu ứng dụng chính cũng cần dùng camera, có thể thêm self:

~~~http
Permissions-Policy: camera=(self "https://meet.example.net"), microphone=(self "https://meet.example.net")
~~~

Hãy dùng origin chính xác gồm scheme, host và port. http://meet.example.net, https://meet.example.net và https://meet.example.net:8443 là các origin khác nhau.

## 5. Cú pháp header và cú pháp iframe allow khác nhau

Đây là nguồn gây lỗi cấu hình phổ biến. HTTP response header dùng cú pháp Permissions Policy dạng Structured Fields:

~~~http
Permissions-Policy: camera=(self "https://meet.example.net"), microphone=(), fullscreen=(self)
~~~

Thuộc tính allow của iframe dùng cú pháp riêng:

~~~html
<iframe
  src="https://meet.example.net/room"
  allow="camera 'src'; microphone 'none'; fullscreen 'src'"
  title="Phòng họp"></iframe>
~~~

| Ý nghĩa | HTTP header | iframe allow |
| --- | --- | --- |
| Cùng origin của tài liệu áp dụng policy | self | 'self' |
| Origin của URL src của iframe | Không có từ khóa tương đương | 'src' |
| Không cho phép origin nào | () | 'none' |
| Mọi origin | * | * |
| Origin cụ thể | "https://meet.example.net" | https://meet.example.net |

Trong header, self là token không có dấu nháy đơn và origin được đặt trong dấu nháy kép. Trong iframe allow, các từ khóa đặc biệt như 'self', 'src' và 'none' được đặt trong dấu nháy đơn. Không sao chép nguyên cú pháp từ header sang HTML attribute.

## 6. Từ khóa src trong iframe allow

Từ khóa src ràng buộc allowlist với origin của URL được chỉ định trong thuộc tính src của iframe. Đây thường là lựa chọn dễ quản lý khi iframe luôn tải widget từ một origin đã biết.

~~~html
<iframe
  src="https://meet.example.net/room"
  allow="camera 'src'; microphone 'src'"
  title="Widget họp"></iframe>
~~~

Khi dùng src, không phải lặp lại origin đầy đủ trong từng directive của attribute. Tuy nhiên, response header của parent vẫn cần cho phép origin con tương ứng. src trong iframe allow không thể vượt qua allowlist của parent.

Nếu iframe có thể điều hướng hoặc redirect tới origin khác, hãy kiểm tra origin thực tế của tài liệu sau navigation và kiểm thử hành vi trong browser mục tiêu. Không để một URL do người dùng kiểm soát quyết định frame nào được nhận feature.

## 7. Delegate cho origin cụ thể

Có thể khai báo origin cụ thể trong iframe allow:

~~~html
<iframe
  src="https://meet.example.net/room"
  allow="camera https://meet.example.net; microphone https://meet.example.net"
  title="Widget họp"></iframe>
~~~

Cách này hữu ích khi cần thể hiện rõ origin được cấp quyền. Nó cũng đòi hỏi cập nhật attribute nếu origin dịch vụ thay đổi.

Không dùng wildcard nếu chỉ có một đối tác cần quyền. Một wildcard rộng có thể khiến những frame không liên quan cũng được phép sử dụng feature, tùy policy và default allowlist của feature đó. Ưu tiên origin cụ thể, có chủ sở hữu và lý do nghiệp vụ.

## 8. Policy của parent là giới hạn tối đa

Giả sử parent response gửi:

~~~http
Permissions-Policy: camera=(self), microphone=()
~~~

Sau đó HTML nhúng:

~~~html
<iframe
  src="https://meet.example.net/room"
  allow="camera 'src'; microphone 'src'"
  title="Widget họp"></iframe>
~~~

Camera vẫn không được delegate cho meet.example.net vì parent header chỉ cho phép self. Microphone bị từ chối với mọi origin. Attribute allow có thể giới hạn thêm hoặc chọn frame nhận feature trong phạm vi policy của parent; nó không thể mở rộng một allowlist đã bị parent giới hạn.

Khi cần delegate camera cho đối tác, parent phải khai báo origin đó:

~~~http
Permissions-Policy: camera=(self "https://meet.example.net"), microphone=()
~~~

và iframe phải delegate camera:

~~~html
<iframe
  src="https://meet.example.net/room"
  allow="camera 'src'"
  title="Widget họp"></iframe>
~~~

## 9. Policy của child có thể tiếp tục giới hạn

Tài liệu con có thể gửi Permissions-Policy response header cho chính nó. Header đó có thể thu hẹp feature được phép sử dụng trong child và các context con mà child tạo.

Ví dụ response của meet.example.net:

~~~http
Permissions-Policy: camera=(self), microphone=(self), geolocation=(), usb=()
~~~

Trong trường hợp này, tài liệu cuộc họp được phép dùng camera/microphone cho chính origin của nó, còn geolocation và USB bị từ chối. Nếu child không cần delegate camera cho frame cháu, không cấp thêm trong iframe bên trong.

Header của child không thể khôi phục feature đã bị parent từ chối. Nếu parent không delegate camera, child response không thể tự bật lại camera bằng cách khai báo camera=(self).

## 10. Delegation qua iframe lồng nhau

Một ứng dụng có thể có chuỗi parent → widget → sub-widget. Mỗi ranh giới nhúng cần được xem xét riêng:

~~~text
app.example.com
  |
  | parent policy cho phép meet.example.net
  | iframe allow delegate camera
  v
meet.example.net
  |
  | policy của meet cho phép camera trong context cần thiết
  | iframe allow delegate tiếp cho media.example.org
  v
media.example.org
~~~

Frame con chỉ có thể tiếp tục delegate feature nếu feature còn được phép trong policy hiệu lực của chính nó. Parent trực tiếp phải cấu hình allow trên iframe cháu, và policy của tài liệu cha trung gian phải cho phép việc delegate đó. Nếu một ancestor đã chặn feature, các frame sâu hơn không thể tự bật lại.

Đừng suy luận rằng cấp camera cho frame họp đồng nghĩa mọi frame mà nhà cung cấp nhúng tiếp đều được dùng camera. Kiểm thử toàn bộ cây frame, nhất là khi widget tải iframe từ domain khác.

## 11. Default allowlist và delegation

Mỗi Permissions Policy feature có default allowlist riêng. Tùy feature, mặc định có thể giới hạn ở self, cho phép rộng hơn hoặc từ chối. Khi không khai báo một feature, browser dùng default allowlist được định nghĩa cho feature đó.

Điều này ảnh hưởng tới delegation:

- Nếu default allowlist không cho cross-origin frame, chỉ thêm iframe allow có thể chưa đủ.
- Parent header có thể cần khai báo origin đối tác cụ thể.
- Nếu parent đã từ chối feature, iframe allow không thể mở lại.
- Feature không được browser hỗ trợ sẽ không trở nên khả dụng chỉ vì header có tên feature đó.

Không dựa vào giả định mọi feature đều có cùng default. Hãy kiểm tra default allowlist của feature trên browser mục tiêu và khai báo rõ quyền nhạy cảm.

## 12. Feature delegation không phải user permission

Để camera hoạt động trong iframe, thường cần đồng thời:

1. Parent policy cho phép origin của frame.
2. iframe allow delegate camera cho frame.
3. Policy của child không từ chối camera.
4. Tài liệu đáp ứng secure context và điều kiện của API.
5. Browser cho phép người dùng cấp quyền và người dùng chấp thuận.

Nếu một điều kiện không đạt, API có thể thất bại. Header không tự bật camera và không thay thế permission prompt. Một user permission đã được cấp trước đó cũng không thể vượt qua Permissions Policy đang chặn feature.

Ví dụ trong child:

~~~js
async function startCamera() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: true,
      audio: false
    });

    document.querySelector('video').srcObject = stream;
  } catch (error) {
    console.error('Không thể mở camera:', error.name);
  }
}
~~~

Ứng dụng cần hiển thị trạng thái phù hợp nếu feature bị chặn, thiết bị không có, người dùng từ chối hoặc browser không hỗ trợ. Không lặp prompt liên tục hoặc làm người dùng hiểu rằng policy đã cấp quyền đồng nghĩa họ đã đồng ý.

## 13. Ví dụ delegate geolocation cho một iframe

Giả sử một ứng dụng bản đồ cần vị trí người dùng trong frame maps.example.net. Parent response:

~~~http
Permissions-Policy: geolocation=("https://maps.example.net"), camera=(), microphone=()
~~~

HTML:

~~~html
<iframe
  src="https://maps.example.net/nearby"
  allow="geolocation 'src'"
  title="Bản đồ quanh bạn"></iframe>
~~~

Child gọi API geolocation sau khi người dùng chủ động chọn chức năng tìm vị trí:

~~~js
navigator.geolocation.getCurrentPosition(
  ({ coords }) => showNearbyPlaces(coords.latitude, coords.longitude),
  (error) => showLocationError(error.code)
);
~~~

Parent chỉ delegate geolocation cho maps.example.net. Các iframe khác không nhận quyền đó qua policy này. Browser vẫn áp dụng permission của người dùng và các yêu cầu secure context.

## 14. Ví dụ delegate fullscreen

Video player hoặc công cụ trình chiếu có thể cần fullscreen:

~~~http
Permissions-Policy: fullscreen=(self "https://video.example.net")
~~~

~~~html
<iframe
  src="https://video.example.net/player"
  allow="fullscreen 'src'"
  title="Video"></iframe>
~~~

Fullscreen thường còn phụ thuộc user activation và quy tắc API/browser. Việc delegate chỉ cho phép frame yêu cầu tính năng trong policy; nó không tự đưa nội dung vào fullscreen khi trang tải.

Nếu chỉ cần fullscreen cho video player, không cấp cùng quyền đó cho mọi iframe trên trang.

## 15. Tạo iframe động an toàn

Một số ứng dụng tạo iframe sau khi người dùng mở widget. Hãy chọn origin từ cấu hình đáng tin cậy, thiết lập allow trước khi tải nội dung và không nhận URL tùy ý từ query string hoặc form.

~~~js
const widgetConfig = {
  origin: 'https://meet.example.net',
  path: '/room/demo',
  allow: "camera 'src'; microphone 'src'; fullscreen 'src'"
};

const frame = document.createElement('iframe');
frame.title = 'Widget họp';
frame.allow = widgetConfig.allow;
frame.referrerPolicy = 'strict-origin-when-cross-origin';
frame.src = new URL(widgetConfig.path, widgetConfig.origin).href;

document.querySelector('#widget-container').append(frame);
~~~

Trong ví dụ, origin và path đến từ cấu hình do ứng dụng quản lý. Trong production, cần kiểm tra host/path bằng allowlist và không cho người dùng tự đưa một URL bất kỳ vào frame có quyền camera/microphone.

Thiết lập attribute trước khi append giúp cấu hình container policy rõ ràng trước khi frame bắt đầu tải. Nếu thay đổi src hoặc allow sau đó, hãy kiểm tra navigation mới và policy hiệu lực trong browser.

## 16. Redirect và thay đổi origin

Feature delegation gắn với browsing context và origin của tài liệu được tải. Một iframe có thể bắt đầu từ URL được tin cậy rồi redirect sang origin khác. Không giả định origin cuối cùng vẫn là origin ban đầu.

Khi frame điều hướng:

- Browser áp dụng lại các quy tắc policy cho tài liệu mới.
- Origin mới phải nằm trong phạm vi cho phép của parent/container policy.
- Policy response của tài liệu mới có thể tiếp tục hạn chế feature.
- Không gửi dữ liệu nhạy cảm cho frame chỉ vì URL khởi đầu đã được allowlist.

Hạn chế redirect không cần thiết qua origin không liên quan. Nếu nhà cung cấp dùng nhiều origin cho login, media hoặc processing, xác định rõ origin nào cần feature nào và chỉ cấp quyền ở đúng frame.

## 17. Iframe srcdoc và about:blank

Iframe dùng srcdoc hoặc about:blank có thể có quan hệ origin đặc biệt với tài liệu tạo ra nó. Không dùng các URL này như cách né allowlist hoặc để nhúng HTML không tin cậy với quyền rộng.

Nếu nội dung srcdoc cần dùng feature, hãy xác định rõ origin/context và policy thực tế của frame. Với HTML không tin cậy, ưu tiên sandbox chặt và không delegate browser feature nhạy cảm. Nếu cần một widget có quyền camera hoặc geolocation, dùng origin riêng được vận hành và kiểm soát thay vì nhúng HTML tùy ý vào srcdoc.

## 18. Permissions Policy và iframe sandbox

Sandbox và feature delegation kiểm soát hai nhóm năng lực khác nhau:

| Cơ chế | Kiểm soát |
| --- | --- |
| iframe sandbox | Script, form, popup, download, điều hướng top-level và origin behavior |
| Permissions Policy/iframe allow | Browser feature như camera, microphone, geolocation, fullscreen và clipboard |

Ví dụ:

~~~html
<iframe
  src="https://widget.example.net/embed"
  sandbox="allow-scripts"
  allow="fullscreen 'src'"
  title="Widget xem nội dung"></iframe>
~~~

Frame được phép chạy script và có thể yêu cầu fullscreen theo policy, nhưng vẫn chịu các hạn chế sandbox khác. Việc allow fullscreen không tự cấp allow-scripts; việc allow-scripts cũng không tự cấp camera.

Không thêm allow-same-origin hoặc các sandbox token khác chỉ để khắc phục một feature bị chặn. Xác định lớp policy nào đang từ chối và chỉ thay đổi lớp đó khi có lý do rõ ràng.

## 19. Permissions Policy và CSP

CSP có các directive liên quan tới framing:

| Directive | Câu hỏi |
| --- | --- |
| frame-src | Trang cha được tải iframe từ nguồn nào? |
| frame-ancestors | Trang hiện tại được origin nào nhúng? |
| Permissions-Policy | Frame được phép sử dụng browser feature nào? |

Ví dụ parent chỉ tải widget từ origin đối tác và delegate camera:

~~~http
Content-Security-Policy: default-src 'self'; frame-src https://meet.example.net
Permissions-Policy: camera=("https://meet.example.net"), microphone=()
~~~

~~~html
<iframe
  src="https://meet.example.net/room"
  allow="camera 'src'"
  title="Cuộc họp"></iframe>
~~~

frame-src không cấp camera; Permissions Policy không giới hạn nguồn iframe được tải. Cần dùng đúng directive cho đúng câu hỏi bảo mật.

## 20. Permissions Policy không thay thế SOP và CORS

SOP giới hạn truy cập DOM và dữ liệu giữa các origin. CORS cho phép server công bố origin nào được đọc response cross-origin. Permissions Policy quyết định một browsing context có được dùng browser feature hay không.

Một iframe cross-origin có thể được delegate camera mà vẫn không thể đọc DOM parent. Ngược lại, CORS cho phép JavaScript đọc response API không đồng nghĩa API camera được cấp cho frame đó.

Không dùng Access-Control-Allow-Origin để cấp quyền camera/geolocation. Không dùng Permissions Policy để mở quyền đọc API response. Các cơ chế này giải quyết những ranh giới khác nhau.

## 21. Quản lý danh sách origin được delegate

Danh sách origin có quyền sử dụng feature là một phần của cấu hình bảo mật. Với mỗi origin, ghi nhận:

- Chủ sở hữu kỹ thuật và đầu mối vận hành.
- Tính năng cần dùng và lý do nghiệp vụ.
- Các route/frame cụ thể cần nhận feature.
- Scheme, host và port chính xác.
- Môi trường production, staging và test.
- Cách xử lý redirect và subdomain.
- Ngày review, thời hạn tích hợp và quy trình thu hồi.

Không tạo allowlist từ dữ liệu người dùng hoặc phản chiếu Origin header mà không xác minh. Khi đối tác thay domain, không tự động cấp quyền cho mọi subdomain mới. Hãy review origin mới và kiểm thử trên môi trường staging.

Nếu nhiều ứng dụng dùng chung cấu hình, quản lý policy tập trung nhưng vẫn cho phép từng route có quyền khác nhau. Một trang admin không nhất thiết phải delegate camera như trang họp trực tuyến.

## 22. Kiểm tra feature delegation trong browser

Khi API trong iframe thất bại, kiểm tra theo thứ tự:

1. Xác nhận URL và origin cuối cùng của iframe.
2. Kiểm tra Permissions-Policy response header của parent.
3. Kiểm tra attribute allow trên đúng element iframe.
4. Kiểm tra response header Permissions-Policy của child.
5. Kiểm tra policy và attribute của các ancestor nếu frame lồng nhau.
6. Kiểm tra secure context, user activation và permission của browser.
7. Xem Console để tìm thông báo feature bị chặn.
8. Xử lý lỗi API và phân biệt policy denial với user denial hoặc thiết bị không sẵn sàng.

Feature detection chỉ cho biết API có tồn tại; nó không chứng minh feature được policy cho phép. Tương tự, user permission đang ở trạng thái granted không thể vượt qua policy chặn.

## 23. Ví dụ ma trận quyền

Giả sử trang cha là app.example.com và có ba frame:

| Frame | Origin | Feature cần dùng | Quyết định |
| --- | --- | --- | --- |
| Ứng dụng chính | app.example.com | Geolocation | Cho phép self nếu sản phẩm cần |
| Widget họp | meet.example.net | Camera, microphone, fullscreen | Delegate ba feature cho origin này |
| Widget chat | chat.example.org | Không cần feature thiết bị | Từ chối camera, microphone và geolocation |

Header parent có thể là:

~~~http
Permissions-Policy: geolocation=(self), camera=("https://meet.example.net"), microphone=("https://meet.example.net"), fullscreen=("https://meet.example.net")
~~~

Widget họp:

~~~html
<iframe
  src="https://meet.example.net/room"
  allow="camera 'src'; microphone 'src'; fullscreen 'src'"
  title="Họp trực tuyến"></iframe>
~~~

Widget chat:

~~~html
<iframe
  src="https://chat.example.org/widget"
  allow="camera 'none'; microphone 'none'; geolocation 'none'"
  title="Hỗ trợ khách hàng"></iframe>
~~~

Ma trận này giúp reviewer thấy rõ frame nào nhận quyền nào. Hãy giữ policy ở mức tối thiểu; không cấp feature cho frame chỉ vì nó đang được nhúng trên cùng trang.

## 24. Thực hành kiểm chứng trong môi trường lab

Chỉ sử dụng các origin lab do bạn kiểm soát, thiết bị thử nghiệm và dữ liệu giả. Không yêu cầu camera, microphone hoặc vị trí của người khác.

### Bài thử A — Delegate camera cho iframe cross-origin

1. Chạy parent trên https://app.lab.example.test và child trên https://meet.lab.example.test.
2. Trên response parent, cấu hình camera allowlist cho origin child.
3. Thêm allow="camera 'src'" vào iframe.
4. Trong child, gọi getUserMedia với camera lab.
5. Bỏ attribute allow và thử lại.

**Kỳ vọng:** Khi parent policy và container policy cùng cho phép, browser có thể hiển thị permission prompt và API hoạt động sau khi người dùng chấp thuận. Khi thiếu một lớp policy, browser từ chối feature.

### Bài thử B — Parent policy không cho phép

Đặt camera=() trên response parent nhưng giữ allow="camera 'src'" trên iframe.

**Kỳ vọng:** iframe allow không thể mở lại camera đã bị parent policy từ chối.

### Bài thử C — Child response policy thu hẹp quyền

Cho parent delegate camera cho child. Sau đó đặt response child là camera=().

**Kỳ vọng:** Child tự giới hạn camera trong tài liệu của nó; header child không thể nới quyền mà parent đã từ chối và cũng có thể thu hẹp quyền đã được delegate.

### Bài thử D — Nested iframe

Tạo parent → child → grandchild. Delegate feature tới child, sau đó thử delegate tiếp tới grandchild bằng allow trên iframe bên trong. Thử bỏ allow ở một tầng.

**Kỳ vọng:** Mỗi tầng phải có policy hiệu lực cho phép. Một ancestor chặn feature thì frame sâu hơn không thể tự bật lại.

### Bài thử E — So sánh header và iframe allow

Thử cùng feature với các cấu hình: header parent chỉ self; header parent có origin child; iframe allow không có directive; iframe allow dùng 'src'; iframe allow dùng 'none'.

**Kỳ vọng:** Phân biệt được allowlist ở response với container policy của iframe. Ghi lại Console, response header và kết quả API ở từng frame.

## 25. Các lỗi delegation thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chỉ thêm allow trên iframe | Parent policy có thể không cho phép origin con | Thêm origin cần thiết vào response header parent |
| Chỉ thêm origin vào header parent | Frame chưa được delegate qua container policy | Cấu hình allow trên iframe cụ thể |
| Dùng sai cú pháp self/src | Browser không áp dụng allowlist như dự kiến | Dùng cú pháp header và attribute đúng ngữ cảnh |
| Dùng wildcard cho mọi frame | Cấp quyền rộng hơn nhu cầu | Dùng origin cụ thể và feature tối thiểu |
| Child header cố bật lại feature | Không vượt qua giới hạn được kế thừa | Sửa policy ở ancestor có thẩm quyền nếu nhu cầu hợp lệ |
| Quên iframe lồng nhau | Frame cháu không nhận feature | Kiểm tra và delegate ở từng tầng |
| Nghĩ policy cho phép là user đã đồng ý | API vẫn có thể bị user/browser từ chối | Xử lý permission prompt và API error |
| Không kiểm tra redirect | Frame có thể tải origin khác dự kiến | Kiểm tra URL cuối và giới hạn origin |
| Lấy URL iframe từ input người dùng | Attacker có thể chọn origin được cấp quyền | Dùng cấu hình/manifest origin đáng tin |
| Dùng Permissions Policy thay CSP | Vẫn có thể tải frame từ nguồn không mong muốn | Dùng frame-src và frame-ancestors đúng vai trò |
| Dùng CORS để cấp camera | CORS không điều khiển browser feature | Dùng Permissions Policy và iframe allow |

## 26. Checklist review feature delegation

- [ ] Đã liệt kê feature cần thiết cho từng iframe.
- [ ] Parent response header cho phép đúng origin cần delegate.
- [ ] iframe allow chỉ cấp feature cần thiết cho frame cụ thể.
- [ ] Dùng exact origin với scheme, host và port chính xác.
- [ ] Hiểu rõ khác biệt cú pháp header và iframe allow.
- [ ] Dùng src khi muốn ràng buộc với origin của URL iframe.
- [ ] Child response policy không vô tình thu hẹp tính năng cần thiết.
- [ ] Đã kiểm tra tất cả ancestor và nested iframe.
- [ ] Không dựa vào wildcard hoặc origin do người dùng cung cấp.
- [ ] Secure context, user activation và permission prompt được xử lý riêng.
- [ ] Redirect/navigation không đưa frame sang origin ngoài dự kiến.
- [ ] CSP frame-src giới hạn nguồn iframe được tải.
- [ ] frame-ancestors bảo vệ trang con khỏi bị nhúng ngoài ý muốn.
- [ ] Sandbox được cấu hình độc lập theo mức độ tin cậy.
- [ ] Có test cho trường hợp được phép, bị chặn ở parent và bị chặn ở child.
- [ ] Có owner và quy trình review/thu hồi origin được delegate.

## 27. Câu hỏi tự kiểm tra

1. Feature delegation giải quyết vấn đề gì khi ứng dụng nhúng iframe bên thứ ba?
2. Ba lớp policy nào quyết định feature có khả dụng trong iframe?
3. Vì sao iframe allow không thể mở lại feature bị parent policy từ chối?
4. Cú pháp self trong header khác src trong iframe allow như thế nào?
5. Khi nào nên dùng origin cụ thể thay vì wildcard?
6. Child response header có thể thu hẹp quyền được delegate ra sao?
7. Feature delegation qua nested iframe cần kiểm tra những ranh giới nào?
8. Vì sao policy cho phép không đồng nghĩa người dùng đã cấp permission?
9. Permissions Policy khác CSP frame-src, frame-ancestors, sandbox, SOP và CORS như thế nào?
10. Cần kiểm tra gì khi API hoạt động trong top-level page nhưng thất bại trong iframe?

## 28. Ghi nhớ

Feature delegation cho phép parent cấp một browser feature cho iframe cụ thể. Hãy kiểm tra policy của parent, container policy qua thuộc tính allow và policy của child. Header parent cần cho phép origin được delegate; iframe allow chọn feature cho frame; response của child có thể tiếp tục giới hạn quyền. Một ancestor đã chặn feature thì frame sâu hơn không thể tự bật lại.

Dùng origin chính xác, ưu tiên src hoặc allowlist cụ thể, kiểm tra từng tầng iframe và không cấp wildcard nếu không cần. Secure context, user activation và permission của người dùng vẫn được áp dụng. **Permissions Policy quyết định frame có đủ điều kiện yêu cầu feature hay không; browser và người dùng vẫn quyết định việc sử dụng thực tế.**
