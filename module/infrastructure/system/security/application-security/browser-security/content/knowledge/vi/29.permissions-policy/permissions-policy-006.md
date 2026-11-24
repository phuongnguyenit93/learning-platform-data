# Default allowlist

**Default allowlist** là danh sách origin mặc định mà một tính năng của browser được phép sử dụng khi tài liệu không khai báo chính sách riêng cho tính năng đó. Trong **Permissions Policy**, mỗi feature như geolocation, camera, microphone hoặc fullscreen có một default allowlist do đặc tả và tài liệu của feature quy định.

Default allowlist ảnh hưởng hai việc: tài liệu top-level có được dùng feature khi không gửi header hay không, và feature có tự động được cấp cho iframe con hay không. Ví dụ, default allowlist **self** cho phép trang top-level và iframe cùng origin, nhưng không tự cấp feature cho iframe cross-origin. Muốn cấp cho một iframe bên ngoài, trang cha cần delegate feature bằng thuộc tính **allow** và bảo đảm HTTP header không chặn origin đó.

Permissions Policy quyết định **ngữ cảnh tài liệu nào được phép sử dụng feature**. Quyền do browser lưu cho người dùng là một lớp khác. Permissions API có thể trả trạng thái hiệu lực **granted**, **denied** hoặc **prompt**; nếu Permissions Policy chặn feature, query thường trả **denied** và browser không cần hỏi người dùng. Quyền này cũng không thay thế authorization của ứng dụng hoặc kiểm tra quyền ở server.

Bài học thuộc chương **Permissions Policy** trong module **Browser Security** (SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY). Nội dung tập trung vào default allowlist, cách kết hợp response header với iframe delegation, kiểm tra trạng thái qua Permissions API và phân biệt quyền browser với ủy quyền tính năng trong ứng dụng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích default allowlist và vai trò của nó khi document không khai báo Permissions Policy tường minh.
2. Phân biệt wildcard, self, empty allowlist và src trong header hoặc thuộc tính iframe.
3. Xác định vì sao default allowlist self cho phép trang top-level nhưng không tự cấp feature cho iframe cross-origin.
4. Cấu hình Permissions-Policy response header để đặt giới hạn trên cho các origin được phép.
5. Delegate một feature cho iframe bằng thuộc tính allow và hiểu cách chính sách được kế thừa.
6. Dùng navigator.permissions.query() để đọc PermissionStatus.state.
7. Phân biệt trạng thái quyền browser, Permissions Policy và authorization nghiệp vụ của ứng dụng.
8. Nhận diện giới hạn hỗ trợ giữa browser, feature directive và Permissions API descriptor.
9. Kiểm tra default policy, delegation và policy denial bằng DevTools cùng Node.js lab.

## 2. Permissions Policy giải quyết vấn đề gì?

Browser cung cấp nhiều API có thể truy cập dữ liệu hoặc khả năng nhạy cảm của thiết bị, ví dụ:

- Geolocation đọc vị trí thiết bị.
- Camera và microphone truy cập thiết bị thu hình/âm thanh.
- Fullscreen chuyển phần tử hoặc tài liệu sang chế độ toàn màn hình.
- Autoplay điều khiển việc phát media tự động.
- Các API khác như WebUSB, WebBluetooth, WebXR hoặc Screen Wake Lock.

Một trang có thể nhúng nội dung từ nhà cung cấp khác bằng iframe. Nếu iframe được phép sử dụng mọi feature mà browser hỗ trợ, một widget bên thứ ba có thể yêu cầu quyền hoặc kích hoạt chức năng ngoài nhu cầu của sản phẩm.

**Permissions Policy** cho phép trang cha giới hạn feature nào được dùng trong document và những iframe nào được nhận feature đó. Chính sách được gửi bằng HTTP response header **Permissions-Policy**; một iframe có thể được cấp tập quyền hẹp hơn qua thuộc tính **allow**.

Permissions Policy là cơ chế kiểm soát feature của browser. Nó không phải hệ thống phân quyền người dùng của ứng dụng, không xác minh vai trò tài khoản và không thay thế kiểm tra quyền ở backend.

### 2.1. Ba lớp cần phân biệt

| Lớp | Câu hỏi | Cơ chế |
| --- | --- | --- |
| Permissions Policy | Document hoặc iframe này có được phép dùng feature không? | Permissions-Policy header và iframe allow |
| Browser permission | Người dùng/browser đã cho phép origin sử dụng feature chưa? | Cài đặt quyền của browser và Permissions API |
| Application authorization | Tài khoản này có được phép xem hoặc thay đổi dữ liệu/nghiệp vụ không? | Session, role, permission và kiểm tra ở server |

Ví dụ, một iframe bản đồ có thể được delegate geolocation bằng Permissions Policy. Người dùng vẫn có thể từ chối chia sẻ vị trí trong browser. Nếu người dùng đồng ý, ứng dụng bản đồ vẫn chỉ được truy cập dữ liệu nghiệp vụ mà server cho phép tài khoản đó.

## 3. Default allowlist là gì?

Mỗi policy-controlled feature có một **default allowlist**. Giá trị này được dùng khi document không khai báo directive tương ứng trong response header và khi xác định feature có tự động được cấp cho các browsing context con hay không.

Với Permissions-Policy HTTP header, các default allowlist chuẩn thường là:

- **self**: cho phép document top-level và các iframe cùng origin theo quy tắc kế thừa.
- **wildcard (*)**: cho phép document top-level và các iframe ở mọi origin theo mặc định.

Giá trị mặc định cụ thể phụ thuộc từng directive. Không được suy ra rằng mọi feature đều có cùng default allowlist. Hãy kiểm tra trang tham chiếu của directive đang dùng và browser mục tiêu.

Ví dụ, tài liệu MDN hiện ghi các directive geolocation, camera, microphone, fullscreen và autoplay có default allowlist là self.

### 3.1. Default self

Giả sử trang top-level có origin https://app.example.com và không gửi directive geolocation:

~~~text
https://app.example.com
  ├── iframe https://app.example.com/map
  └── iframe https://maps.partner.example/widget
~~~

Với default allowlist self:

- Document top-level có thể dùng geolocation nếu các điều kiện khác cũng đáp ứng.
- Iframe cùng origin có thể được cấp feature theo default.
- Iframe https://maps.partner.example không tự động được cấp feature.

Default self không có nghĩa là tắt feature cho trang chính. Origin của document top-level chính là origin của chính nó nên khớp self.

### 3.2. Default wildcard

Nếu một feature có default allowlist wildcard, feature được cho phép trong document top-level và tự động có thể được dùng trong iframe con ở mọi origin, trừ khi chính sách tường minh giới hạn nó.

Đây là lý do cần tra cứu default của từng feature. Một trang có thể không gửi Permissions-Policy header nhưng vẫn có những feature được tự động delegate rộng hơn dự kiến.

### 3.3. Empty allowlist là chính sách chặn tường minh

Dấu ngoặc rỗng trong HTTP header biểu thị empty allowlist:

~~~http
Permissions-Policy: geolocation=()
~~~

Directive này chặn geolocation trong document và các browsing context con chịu chính sách đó. Nó khác default allowlist: đây là lựa chọn do ứng dụng chủ động khai báo để tắt feature.

Nếu parent đã chặn feature, iframe không thể bật lại bằng thuộc tính allow. Việc chặn được kế thừa theo chuỗi browsing context.

## 4. Phân biệt wildcard, self, empty allowlist và src

Các từ khóa này xuất hiện ở nhiều vị trí nhưng ý nghĩa và cú pháp phụ thuộc nơi khai báo.

| Giá trị | Trong HTTP header | Trong iframe allow |
| --- | --- | --- |
| Wildcard (*) | Mọi origin | Mọi origin trong phạm vi container policy |
| self | Origin của response đang đặt header | Origin của document chứa iframe |
| Empty allowlist | Dùng () để chặn feature | Dùng 'none' để chặn feature |
| src | Không phải giá trị default allowlist của header | Origin của URL trong thuộc tính src của iframe |

src đặc biệt quan trọng: nếu iframe có allow="geolocation" mà không ghi allowlist, giá trị mặc định của thuộc tính allow là 'src'. Do đó:

~~~html
<iframe src="https://maps.example/widget" allow="geolocation"></iframe>
~~~

tương đương:

~~~html
<iframe
  src="https://maps.example/widget"
  allow="geolocation 'src'"></iframe>
~~~

src không có nghĩa là origin của trang cha. Nó trỏ tới origin của URL iframe được khai báo trong src.

Trong header, origin cụ thể được đặt trong ngoặc và dùng chuỗi có dấu nháy:

~~~http
Permissions-Policy: geolocation=(self "https://maps.example")
~~~

Trong thuộc tính iframe, origin cụ thể thường được ghi trực tiếp:

~~~html
<iframe
  src="https://maps.example/widget"
  allow="geolocation https://maps.example"></iframe>
~~~

## 5. Cấu hình default và policy tường minh bằng HTTP header

### 5.1. Ví dụ chỉ cho phép origin của ứng dụng

~~~http
Permissions-Policy: geolocation=(self), camera=(), microphone=(), fullscreen=(self)
~~~

Ý nghĩa:

- Geolocation chỉ được phép trong origin của ứng dụng và các context cùng origin theo quy tắc kế thừa.
- Camera và microphone bị tắt.
- Fullscreen chỉ được phép trong origin của ứng dụng.

Header policy tường minh giúp nhóm phát triển không phụ thuộc hoàn toàn vào default của từng feature.

Khả năng hỗ trợ của Permissions-Policy header và từng directive không đồng đều giữa các browser/version. Tên header cũ Feature-Policy đã được thay bằng Permissions-Policy; hãy dùng cú pháp mới và kiểm tra bảng tương thích cho từng feature trước khi triển khai rộng.

### 5.2. Cho phép một origin đối tác

~~~http
Permissions-Policy: geolocation=(self "https://maps.partner.example")
~~~

Header này định nghĩa tập origin tối đa có thể được cấp geolocation. Để iframe đối tác thực sự nhận feature, phần tử iframe cũng cần delegate:

~~~html
<iframe
  src="https://maps.partner.example/embed"
  allow="geolocation"
  title="Bản đồ đối tác"></iframe>
~~~

Nếu iframe điều hướng sang một origin khác không có trong allowlist của header, origin mới không được hưởng quyền chỉ vì element vẫn có allow="geolocation".

### 5.3. Chặn feature không cần thiết

~~~http
Permissions-Policy: camera=(), microphone=(), geolocation=(), usb=()
~~~

Đây là cách giảm bề mặt feature cho các trang không cần truy cập thiết bị hoặc vị trí. Chỉ đưa directive mà browser hỗ trợ và ứng dụng đã kiểm thử vào cấu hình. Một số directive có thể không được triển khai đồng đều giữa các browser.

### 5.4. Header có directive tường minh sẽ giới hạn khả năng delegate

Giả sử header:

~~~http
Permissions-Policy: geolocation=(self "https://maps.partner.example")
~~~

Một iframe khác origin có:

~~~html
<iframe
  src="https://untrusted.example/widget"
  allow="geolocation *"></iframe>
~~~

Iframe không thể mở rộng quyền vượt qua allowlist của parent header. Thuộc tính allow chỉ delegate feature cho origin nằm trong tập origin mà parent policy cho phép.

## 6. Iframe allow và cách policy được kế thừa

Response header đặt giới hạn trên cho document và các context con. Thuộc tính allow trên iframe cấp một tập quyền cụ thể cho iframe đó.

### 6.1. Header và iframe allow phối hợp

~~~mermaid
flowchart TD
    A["Parent response: Permissions-Policy"] --> B["Tập origin tối đa được phép"]
    B --> C["Iframe element: allow"]
    C --> D{"Origin của iframe có nằm trong parent allowlist?"}
    D -->|Không| E["Feature bị chặn"]
    D -->|Có| F{"Iframe allow có cấp feature?"}
    F -->|Có| G["Feature được delegate"]
    F -->|Không| H["Áp dụng default allowlist của feature"]
    H --> I["Kiểm tra các điều kiện browser permission khác"]
    G --> I
    I --> J["Feature có thể sử dụng nếu các điều kiện khác đều đạt"]
~~~

### 6.2. Chỉ cấp feature cần thiết

Ví dụ iframe video cần autoplay và fullscreen:

~~~html
<iframe
  src="https://video.partner.example/player"
  allow="autoplay; fullscreen"
  title="Video player"></iframe>
~~~

Không dùng allow="*" hoặc cấp camera, microphone, geolocation nếu widget không cần chúng.

### 6.3. Nhiều feature trong một iframe

Thuộc tính allow dùng dấu chấm phẩy để phân tách directive:

~~~html
<iframe
  src="https://meeting.partner.example/room"
  allow="camera 'src'; microphone 'src'; fullscreen 'src'"
  title="Phòng họp"></iframe>
~~~

Trong HTTP header, các directive được phân tách theo cú pháp Structured Fields, thường dùng dấu phẩy:

~~~http
Permissions-Policy: camera=(self "https://meeting.partner.example"), microphone=(self "https://meeting.partner.example"), fullscreen=(self "https://meeting.partner.example")
~~~

Đừng sao chép dấu phân tách của iframe attribute sang HTTP header hoặc ngược lại.

### 6.4. Policy không thể được bật lại ở frame con

Nếu một parent đã đặt geolocation=(), iframe con không thể khôi phục feature bằng:

~~~html
<iframe
  src="https://maps.partner.example"
  allow="geolocation *"></iframe>
~~~

Tương tự, một frame trung gian không thể bật lại feature mà ancestor trước đó đã chặn. Quy tắc này ngăn một widget được nhúng tự mở rộng quyền vượt qua quyết định của trang chủ.

## 7. Default allowlist áp dụng cho iframe thế nào?

Đây là phần dễ nhầm nhất: **default allowlist của feature trong Permissions Policy khác default value của thuộc tính iframe allow.**

| Tình huống | Kết quả với feature có default self |
| --- | --- |
| Trang top-level không có header directive | Feature được phép trong trang top-level nếu các điều kiện khác đạt |
| Iframe cùng origin, không ghi directive trong allow | Feature có thể được cấp theo default self |
| Iframe cross-origin, không ghi directive trong allow | Feature không tự động được cấp |
| Iframe cross-origin có allow="geolocation" và parent không đặt header hạn chế | allow delegate feature cho origin trong src |
| Parent header có geolocation=(self) và iframe cross-origin có allow="geolocation" | Bị chặn vì origin iframe nằm ngoài allowlist của parent |
| Parent header có geolocation=() và iframe có allow="geolocation" | Bị chặn |
| Parent header có geolocation=(self "https://maps.partner.example") và iframe tương ứng có allow="geolocation" | Feature được delegate, còn phụ thuộc browser permission và điều kiện API |

Khi parent không khai báo directive cho một feature, iframe allow vẫn có thể delegate feature cho origin được nêu. Nếu iframe không nêu feature đó, default allowlist của feature quyết định việc cấp tự động.

### 7.1. Ví dụ theo origin

Giả sử:

- Parent: https://app.example.com
- Iframe A: https://app.example.com/map
- Iframe B: https://maps.partner.example/embed

Với default self, A được cấp theo mặc định; B không được cấp tự động. Nếu sản phẩm cần B sử dụng geolocation, parent phải delegate rõ ràng và kiểm tra policy ở mọi ancestor.

## 8. Permissions API kiểm tra trạng thái quyền ra sao?

**Permissions API** cung cấp cách truy vấn trạng thái quyền của một feature trong context hiện tại. Ví dụ với Geolocation:

~~~js
const status = await navigator.permissions.query({
  name: 'geolocation',
});

console.log(status.state);
~~~

PermissionStatus.state có ba giá trị:

| State | Ý nghĩa |
| --- | --- |
| granted | Các điều kiện quyền hiện tại cho phép sử dụng feature; browser không cần hỏi lại người dùng tại thời điểm đó |
| prompt | Chưa có quyết định cấp quyền; khi gọi API sử dụng feature, browser có thể hỏi người dùng |
| denied | Feature hiện không được phép trong context này; nguyên nhân có thể là user/browser setting hoặc policy restriction |

Permissions API không tự mở prompt. Prompt được kích hoạt bởi API cụ thể, ví dụ gọi navigator.geolocation.getCurrentPosition() khi state là prompt.

### 8.1. Permissions API có tính đến Permissions Policy

Trạng thái được query là trạng thái hiệu lực trong context, không chỉ là lựa chọn mà người dùng đã lưu trong browser. Các điều kiện có thể bao gồm:

- Secure context requirement.
- Permissions Policy áp dụng cho document và iframe.
- Quyết định permission của người dùng hoặc browser.
- Yêu cầu user activation hoặc điều kiện riêng của API.

Nếu Permissions Policy chặn feature, Permissions API thường trả denied; browser không cần hỏi người dùng để cấp một feature mà document không được phép dùng.

### 8.2. denied không nói rõ nguyên nhân

denied có thể đến từ:

- Người dùng đã chặn vị trí/camera/microphone cho origin.
- Browser hoặc hệ điều hành chặn truy cập thiết bị.
- Permissions Policy chặn feature trong document hoặc iframe.
- Document không đáp ứng điều kiện bảo mật cần thiết.

Vì vậy, không nên kết luận rằng người dùng đã nhấn nút Block chỉ từ state === 'denied'. Hãy kiểm tra response header, iframe allow, secure context và cài đặt quyền browser.

### 8.3. Permissions API không phải Permissions Policy API

Hai API có mục đích khác nhau:

| API | Trả lời câu hỏi |
| --- | --- |
| navigator.permissions.query() | Context hiện tại có trạng thái quyền hiệu lực là granted, denied hay prompt? |
| document.permissionsPolicy nếu browser hỗ trợ | Feature có được Permissions Policy cho phép trong document này không? |

Permissions API không trả danh sách origin trong allowlist và không cho biết directive nào đã chặn. Để xác định policy, kiểm tra response header, thuộc tính iframe và API introspection nếu browser hỗ trợ.

### 8.4. Theo dõi thay đổi trạng thái

PermissionStatus phát sự kiện change khi state thay đổi:

~~~js
const status = await navigator.permissions.query({
  name: 'geolocation',
});

console.log('Initial state:', status.state);

status.addEventListener('change', () => {
  console.log('Permission changed:', status.state);
});
~~~

Đây là cách cập nhật giao diện khi người dùng thay đổi quyền trong browser settings hoặc khi trạng thái quyền của context thay đổi.

## 9. Kiểm tra feature policy và gọi API thực tế

### 9.1. Query permission có xử lý lỗi

Không phải mọi browser đều hỗ trợ mọi permission descriptor. Ví dụ geolocation thường được hỗ trợ rộng, nhưng descriptor của một API mới có thể gây TypeError.

~~~js
async function inspectGeolocationPermission() {
  if (!navigator.permissions?.query) {
    return {
      supported: false,
      reason: 'Permissions API không khả dụng',
    };
  }

  try {
    const status = await navigator.permissions.query({
      name: 'geolocation',
    });

    return {
      supported: true,
      state: status.state,
    };
  } catch (error) {
    return {
      supported: false,
      reason: error.message,
    };
  }
}

inspectGeolocationPermission().then(console.log);
~~~

Không giả định mọi permission name đều được hỗ trợ chỉ vì navigator.permissions tồn tại.

### 9.2. Kiểm tra Permissions Policy nếu có API introspection

Đặc tả hiện mô tả document.permissionsPolicy, với các phương thức như allowsFeature() và getAllowlistForFeature(). Mức hỗ trợ browser còn hạn chế, vì vậy cần feature detection:

~~~js
function inspectGeolocationPolicy() {
  const policy = document.permissionsPolicy;

  if (!policy || typeof policy.allowsFeature !== 'function') {
    return {
      supported: false,
      allowed: null,
      reason: 'Browser không cung cấp PermissionsPolicy introspection API',
    };
  }

  return {
    supported: true,
    allowed: policy.allowsFeature('geolocation'),
    allowlist:
      typeof policy.getAllowlistForFeature === 'function'
        ? policy.getAllowlistForFeature('geolocation')
        : null,
  };
}

console.log(inspectGeolocationPolicy());
~~~

API cũ document.featurePolicy thuộc Feature Policy, đã bị đánh dấu deprecated/non-standard. Không nên dùng nó làm nền tảng cho code mới. Nếu cần hỗ trợ browser cũ, hãy xem đó là công cụ chẩn đoán có giới hạn và vẫn kiểm tra header/iframe trong DevTools.

### 9.3. Gọi feature chỉ sau hành động của người dùng

Ví dụ Geolocation:

~~~js
const button = document.querySelector('#get-location');
const output = document.querySelector('#location-status');

button.addEventListener('click', () => {
  if (!navigator.geolocation) {
    output.textContent = 'Browser không hỗ trợ Geolocation API.';
    return;
  }

  navigator.geolocation.getCurrentPosition(
    (position) => {
      output.textContent =
        'Đã nhận vị trí với độ chính xác ' +
        position.coords.accuracy +
        ' mét.';
    },
    (error) => {
      output.textContent =
        'Không thể lấy vị trí: ' + error.message;
    },
    {
      enableHighAccuracy: false,
      timeout: 10000,
      maximumAge: 30000,
    },
  );
});
~~~

Không tự động gọi API nhạy cảm khi vừa tải trang. Hãy giải thích vì sao cần feature và để người dùng chủ động kích hoạt. Với geolocation, chỉ hiển thị tọa độ hoặc gửi chúng lên server khi ứng dụng thực sự cần và có cơ sở xử lý phù hợp.

## 10. Browser permission khác authorization của ứng dụng

Một trạng thái granted không có nghĩa người dùng được quyền truy cập mọi dữ liệu mà feature có thể thu thập.

Ví dụ:

1. Browser cho phép trang đọc vị trí thiết bị.
2. Ứng dụng nhận tọa độ hiện tại.
3. Backend vẫn phải kiểm tra tài khoản có quyền xem cửa hàng, đơn hàng hoặc dữ liệu theo vùng đó hay không.

Tương tự:

- Camera được browser cho phép không có nghĩa user được quyền tham gia mọi cuộc họp.
- Microphone được browser cho phép không có nghĩa user được quyền ghi âm phiên làm việc.
- Geolocation được browser cho phép không có nghĩa client được quyền thay đổi địa chỉ giao hàng trong database.

Authorization phải được thực hiện ở server dựa trên danh tính, quyền và tài nguyên cụ thể. Không tin giá trị JavaScript, trạng thái permission hoặc dữ liệu từ client như bằng chứng phân quyền.

## 11. Ví dụ triển khai theo default allowlist

### 11.1. Trang không cần geolocation

~~~http
Permissions-Policy: geolocation=()
~~~

Đây là lựa chọn rõ ràng cho trang không cần vị trí. Iframe con cũng không thể tự bật geolocation lại.

### 11.2. Trang chỉ dùng geolocation trên origin của mình

~~~http
Permissions-Policy: geolocation=(self)
~~~

Trang top-level và iframe cùng origin được phép theo policy. Iframe cross-origin không được cấp feature.

### 11.3. Trang cấp geolocation cho một bản đồ đối tác

Response header:

~~~http
Permissions-Policy: geolocation=(self "https://maps.partner.example")
~~~

HTML:

~~~html
<iframe
  src="https://maps.partner.example/embed"
  allow="geolocation"
  title="Bản đồ đối tác"></iframe>
~~~

Người dùng vẫn cần cấp browser permission cho origin phù hợp. Nếu permission đang là prompt, browser có thể hỏi khi iframe gọi Geolocation API. Nếu user/browser từ chối, policy allow không thể ép browser cho phép.

### 11.4. Widget không cần feature nhạy cảm

~~~http
Permissions-Policy: camera=(), microphone=(), geolocation=(), usb=()
~~~

Với iframe widget:

~~~html
<iframe
  src="https://widget.partner.example/embed"
  title="Widget công khai"></iframe>
~~~

Không thêm allow cho các feature không cần. Hãy chỉ delegate theo yêu cầu chức năng đã xác nhận.

## 12. Thực hành: kiểm tra default allowlist và delegation

Bài lab dùng **Node.js 18 trở lên**, không cần package ngoài. Hai server chạy trên cùng hostname localhost nhưng khác port:

- http://localhost:3000: trang cha.
- http://localhost:3001: trang con trong iframe.

Hai URL khác port nên khác origin. localhost được browser xem là secure context trong môi trường phát triển, nên có thể thử Geolocation API. Lab không cần đọc vị trí thật để quan sát policy; thao tác lấy vị trí chỉ chạy khi người học nhấn nút trong iframe.

Lab có bốn chế độ:

| Route | Header của parent | Iframe allow | Mục đích |
| --- | --- | --- | --- |
| /default | Không khai báo geolocation | Không có | Quan sát default allowlist self |
| /iframe-only | Không khai báo geolocation | geolocation | Quan sát explicit delegation bằng container |
| /header-allow | geolocation=(self "http://localhost:3001") | geolocation | Header và iframe cùng cho phép |
| /header-deny | geolocation=() | geolocation | Chứng minh iframe không thể bật lại feature bị parent chặn |

### 12.1. Tạo file permissions-policy-lab.mjs

~~~js
import { createServer } from 'node:http';

function childPage() {
  return [
    '<!doctype html>',
    '<html lang="vi"><head><meta charset="utf-8">',
    '<title>Child permissions probe</title>',
    '<style>body{font:15px sans-serif;padding:16px}code{overflow-wrap:anywhere}</style>',
    '</head><body>',
    '<h2>Iframe origin: localhost:3001</h2>',
    '<p>Permissions Policy: <strong id="policy-state">Đang kiểm tra...</strong></p>',
    '<p>Permissions API: <strong id="permission-state">Đang kiểm tra...</strong></p>',
    '<button id="get-location">Thử lấy vị trí</button>',
    '<p id="result">Chưa gọi Geolocation API.</p>',
    '<script>',
    'async function inspect() {',
    "  const policy = document.permissionsPolicy;",
    "  const policyOutput = document.querySelector('#policy-state');",
    "  if (policy && typeof policy.allowsFeature === 'function') {",
    "    policyOutput.textContent = String(policy.allowsFeature('geolocation'));",
    '  } else {',
    "    policyOutput.textContent = 'Introspection API không hỗ trợ trong browser này';",
    '  }',
    "  const permissionOutput = document.querySelector('#permission-state');",
    '  if (!navigator.permissions || !navigator.permissions.query) {',
    "    permissionOutput.textContent = 'Permissions API không khả dụng';",
    '    return;',
    '  }',
    '  try {',
    "    const status = await navigator.permissions.query({ name: 'geolocation' });",
    '    permissionOutput.textContent = status.state;',
    "    status.addEventListener('change', () => {",
    '      permissionOutput.textContent = status.state;',
    '    });',
    '  } catch (error) {',
    "    permissionOutput.textContent = 'Không query được: ' + error.message;",
    '  }',
    '}',
    "document.querySelector('#get-location').addEventListener('click', () => {",
    "  const result = document.querySelector('#result');",
    '  if (!navigator.geolocation) {',
    "    result.textContent = 'Geolocation API không khả dụng.';",
    '    return;',
    '  }',
    '  navigator.geolocation.getCurrentPosition(',
    '    (position) => {',
    "      result.textContent = 'Được phép. Độ chính xác: ' + position.coords.accuracy + ' mét.';",
    '    },',
    '    (error) => {',
    "      result.textContent = 'Không lấy được vị trí (code ' + error.code + '): ' + error.message;",
    '    },',
    '    { timeout: 10000, maximumAge: 30000 }',
    '  );',
    '});',
    'inspect();',
    '</script>',
    '</body></html>',
  ].join('\n');
}

function parentPage(mode) {
  const withAllow = mode !== 'default';
  const allowAttribute = withAllow ? ' allow="geolocation"' : '';

  return [
    '<!doctype html>',
    '<html lang="vi"><head><meta charset="utf-8">',
    '<title>Permissions Policy lab</title></head><body>',
    '<h1>Permissions Policy default allowlist</h1>',
    '<p>Chế độ hiện tại: <strong>' + mode + '</strong></p>',
    '<ul>',
    '<li><a href="/default">Default allowlist</a></li>',
    '<li><a href="/iframe-only">Iframe allow only</a></li>',
    '<li><a href="/header-allow">Header allow + iframe allow</a></li>',
    '<li><a href="/header-deny">Header deny + iframe allow</a></li>',
    '</ul>',
    '<p>Iframe bên dưới có origin localhost:3001.</p>',
    '<iframe src="http://localhost:3001/child"' + allowAttribute +
      ' title="Permissions test child" width="100%" height="340"></iframe>',
    '</body></html>',
  ].join('\n');
}

createServer((req, res) => {
  const path = new URL(req.url, 'http://localhost:3001').pathname;

  if (path !== '/child') {
    res.writeHead(404);
    res.end('Not found');
    return;
  }

  res.writeHead(200, {
    'Content-Type': 'text/html; charset=utf-8',
    'Cache-Control': 'no-store',
  });
  res.end(childPage());
}).listen(3001, () => {
  console.log('Child: http://localhost:3001/child');
});

createServer((req, res) => {
  const path = new URL(req.url, 'http://localhost:3000').pathname;
  const mode = path.slice(1) || 'default';
  const modes = new Set([
    'default',
    'iframe-only',
    'header-allow',
    'header-deny',
  ]);

  if (!modes.has(mode)) {
    res.writeHead(404);
    res.end('Not found');
    return;
  }

  const headers = {
    'Content-Type': 'text/html; charset=utf-8',
    'Cache-Control': 'no-store',
  };

  if (mode === 'header-allow') {
    headers['Permissions-Policy'] =
      'geolocation=(self "http://localhost:3001")';
  }

  if (mode === 'header-deny') {
    headers['Permissions-Policy'] = 'geolocation=()';
  }

  res.writeHead(200, headers);
  res.end(parentPage(mode));
}).listen(3000, () => {
  console.log('Parent: http://localhost:3000');
});
~~~

### 12.2. Chạy lab

~~~bash
node permissions-policy-lab.mjs
~~~

Mở http://localhost:3000/default.

### 12.3. Quan sát default allowlist

Ở route /default:

- Parent không gửi directive geolocation.
- Iframe khác origin không có thuộc tính allow.
- Vì geolocation có default allowlist self, iframe cross-origin không tự động được cấp feature.
- Trong browser hỗ trợ đầy đủ, Permissions API trong child thường trả denied do policy.

Đây là ví dụ cho thấy default allowlist quyết định delegation tự động khi iframe không khai báo feature.

### 12.4. Thử iframe allow

Mở /iframe-only:

- Parent vẫn không khai báo directive geolocation.
- Iframe có allow="geolocation".
- Giá trị mặc định của feature trong iframe allow là src, tức origin http://localhost:3001.
- Nếu browser hỗ trợ, policy có thể cho phép feature trong child. Permissions API lúc này có thể trả prompt, granted hoặc denied tùy browser permission của origin.

Nhấn **Thử lấy vị trí** để browser xử lý yêu cầu thực tế. Chỉ cấp quyền nếu bạn muốn kiểm tra chức năng này.

### 12.5. Thử header allow

Mở /header-allow:

~~~http
Permissions-Policy: geolocation=(self "http://localhost:3001")
~~~

Parent header cho phép origin ứng dụng và origin iframe. Iframe cũng có allow="geolocation", vì vậy hai lớp policy đều cho phép delegation. Người dùng vẫn cần browser permission nếu state là prompt.

### 12.6. Thử header deny

Mở /header-deny:

~~~http
Permissions-Policy: geolocation=()
~~~

Iframe vẫn có allow="geolocation", nhưng header của parent đã chặn feature. Child không thể tự cấp lại. Permissions API thường trả denied, và thao tác lấy vị trí thất bại mà không cần browser hỏi người dùng.

### 12.7. Kiểm tra trong DevTools

- Mở Network và chọn response của trang parent; kiểm tra Permissions-Policy header.
- Chọn iframe trong Elements và kiểm tra thuộc tính allow.
- Chuyển execution context của Console sang frame con.
- Kiểm tra navigator.permissions.query({ name: 'geolocation' }).
- Nếu có, kiểm tra document.permissionsPolicy?.allowsFeature('geolocation').
- Nhấn nút trong iframe để quan sát kết quả Geolocation API và thông báo Console.

### 12.8. Giới hạn lab

- Lab cần browser hỗ trợ directive geolocation và Permissions Policy cho iframe; mức hỗ trợ có thể khác nhau giữa browser/version.
- document.permissionsPolicy chưa được hỗ trợ đồng đều. Nếu API introspection không có, kiểm tra header và iframe allow trực tiếp.
- Geolocation chỉ hoạt động trong secure context. Browser thường coi localhost là secure context cho phát triển local.
- Trạng thái browser permission phụ thuộc cài đặt của origin và có thể đã được cấp/từ chối từ trước.
- Lab không gửi tọa độ tới server và không dùng dữ liệu vị trí cho nghiệp vụ thật.

## 13. Lỗi cấu hình thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Nghĩ mọi feature có default self | Một feature có default wildcard có thể được delegate rộng hơn dự kiến | Tra cứu default allowlist riêng của từng directive |
| Nghĩ self là origin của iframe | Cho phép nhầm origin hoặc chặn nhầm iframe | Trong header, self là origin gửi header; trong iframe allow, self là origin của document cha |
| Nhầm src với self | Delegate sai origin | src là origin từ URL iframe; chỉ dùng trong iframe allow |
| Dùng () trong iframe attribute | Sai cú pháp cho empty allowlist | Dùng none trong iframe allow; dùng () trong HTTP header |
| Chỉ đặt iframe allow, không xem header parent | Iframe vẫn bị chặn bởi allowlist của ancestor | Kiểm tra cả response header và từng iframe |
| Parent chặn rồi mong child bật lại | Feature vẫn bị chặn | Chỉ cấp ở parent khi thực sự cần |
| Query denied rồi kết luận user đã bấm Block | Chẩn đoán sai nguyên nhân | Kiểm tra Permissions Policy, secure context và browser settings |
| Thấy granted rồi bỏ kiểm tra backend | Client có thể truy cập feature nhưng không có quyền nghiệp vụ | Authorization luôn phải được kiểm tra ở server |
| Dùng document.featurePolicy trong code mới | Phụ thuộc API cũ, non-standard | Ưu tiên document.permissionsPolicy nếu được hỗ trợ; nếu không, kiểm tra header/iframe |
| Tin rằng mọi browser hỗ trợ cùng directive | Feature có thể bị bỏ qua hoặc không có hiệu lực ở browser khác | Kiểm tra browser support cho từng directive và test thực tế |

## 14. Checklist triển khai Permissions Policy

1. **Kiểm kê feature:** xác định ứng dụng và từng iframe thực sự cần camera, microphone, geolocation, fullscreen, autoplay hoặc API nào khác.
2. **Tra default allowlist:** kiểm tra tài liệu của từng directive; không suy luận từ feature khác.
3. **Đặt policy tường minh:** dùng response header để xác định origin tối đa được phép.
4. **Dùng allowlist hẹp:** ưu tiên self hoặc origin cụ thể; tránh wildcard nếu không có nhu cầu rõ ràng.
5. **Delegate theo iframe:** chỉ thêm allow cho widget cần feature.
6. **Kiểm tra ancestor chain:** một ancestor chặn feature thì descendants không thể bật lại.
7. **Kiểm tra user permission:** dùng Permissions API để hiển thị granted, denied hoặc prompt khi descriptor được hỗ trợ.
8. **Không suy luận nguyên nhân từ state:** denied không chứng minh người dùng đã bấm Block.
9. **Kiểm tra secure context:** camera, microphone và geolocation thường yêu cầu HTTPS hoặc secure context tương đương.
10. **Giữ authorization ở server:** browser permission không phải quyền truy cập dữ liệu/nghiệp vụ.
11. **Feature detect:** kiểm tra API và directive hỗ trợ ở các browser mục tiêu.
12. **Kiểm thử iframe:** thử same-origin, cross-origin, nested iframe, redirect và navigation sang origin khác.
13. **Quan sát runtime:** kiểm tra Network header, Console violation, Permissions API và kết quả gọi feature.
14. **Rà soát định kỳ:** khi thêm iframe hoặc vendor mới, xem lại feature mà nội dung đó được delegate.

## 15. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Default allowlist là quyền mà người dùng đã cấp.” | Đây là chính sách origin được phép dùng feature, không phải user permission. |
| “Default self chặn cả trang top-level.” | Origin của top-level document khớp chính self, nên feature vẫn có thể được dùng. |
| “Không có Permissions-Policy header nghĩa là mọi feature được cấp cho mọi iframe.” | Default allowlist của từng feature vẫn quyết định delegation tự động. |
| “Iframe allow có thể vượt parent header.” | Header của ancestor đặt giới hạn trên; iframe chỉ delegate trong phạm vi được phép. |
| “allow geolocation có nghĩa là browser không hỏi người dùng.” | Nó chỉ delegate feature; user/browser permission vẫn có thể yêu cầu prompt. |
| “Permissions API query là API xin quyền.” | query chỉ đọc trạng thái; API sử dụng feature mới có thể kích hoạt prompt. |
| “denied luôn do người dùng từ chối.” | Policy, secure context hoặc browser setting cũng có thể tạo trạng thái denied. |
| “granted đồng nghĩa tài khoản được phép dùng dữ liệu.” | Application authorization là lớp riêng và phải kiểm tra ở server. |
| “Permissions Policy thay CSP.” | Permissions Policy kiểm soát feature; CSP kiểm soát nguồn và hành vi tài nguyên. |
| “document.featurePolicy là API hiện đại.” | Đây là API cũ, non-standard/deprecated; support của API introspection mới vẫn cần kiểm tra. |

## 16. Câu hỏi tự đánh giá

**Câu 1.** Default allowlist quyết định điều gì?

**Gợi ý trả lời:** Nó quyết định feature được phép trong document không khai báo policy tường minh và có tự động được delegate cho iframe con hay không.

**Câu 2.** Default self có chặn feature trong trang top-level không?

**Gợi ý trả lời:** Không. Origin của trang top-level khớp self; iframe cross-origin mới không được cấp tự động.

**Câu 3.** allow="geolocation" tương đương giá trị nào?

**Gợi ý trả lời:** allow="geolocation 'src'"; src là origin của URL iframe.

**Câu 4.** Vì sao iframe không thể bật lại feature đã bị parent header chặn?

**Gợi ý trả lời:** Policy được kế thừa theo chuỗi browsing context; container policy của child không thể mở rộng vượt qua giới hạn của ancestor.

**Câu 5.** Permissions API trả những state nào?

**Gợi ý trả lời:** granted, denied và prompt.

**Câu 6.** Vì sao query trả denied chưa chứng minh người dùng đã từ chối?

**Gợi ý trả lời:** Trạng thái hiệu lực còn tính đến Permissions Policy, secure context và các giới hạn browser khác.

**Câu 7.** Browser permission khác authorization của ứng dụng như thế nào?

**Gợi ý trả lời:** Browser permission cho phép origin sử dụng một khả năng của thiết bị/API; authorization quyết định tài khoản được truy cập tài nguyên hoặc thao tác nghiệp vụ nào và phải được server kiểm tra.

## Tài liệu tham khảo

- W3C — [Permissions Policy](https://www.w3.org/TR/permissions-policy/), phần Default Allowlists và Policy Introspection.
- W3C — [Permissions](https://www.w3.org/TR/permissions/).
- MDN — [Permissions Policy guide](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Permissions_Policy).
- MDN — [Permissions-Policy header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Permissions-Policy).
- MDN — [Geolocation directive](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Permissions-Policy/geolocation), [Camera directive](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Permissions-Policy/camera), [Microphone directive](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Permissions-Policy/microphone), [Fullscreen directive](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Permissions-Policy/fullscreen).
- MDN — [Permissions API](https://developer.mozilla.org/en-US/docs/Web/API/Permissions_API), [PermissionStatus.state](https://developer.mozilla.org/en-US/docs/Web/API/PermissionStatus/state).
- MDN — [Geolocation API](https://developer.mozilla.org/en-US/docs/Web/API/Geolocation_API).
