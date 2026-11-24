# Permission inheritance: kế thừa Permissions Policy qua nested iframe

## 1. Vì sao cần hiểu permission inheritance?

Một ứng dụng có thể nhúng nhiều lớp nội dung: trang chính nhúng widget đối tác, widget lại nhúng bản đồ hoặc trình phát media của nhà cung cấp khác. Các frame này có thể cần dùng một số tính năng của browser như Geolocation, Camera, Microphone, Fullscreen hoặc Payment Request.

**Permissions Policy** cho phép trang kiểm soát những tính năng nào được sử dụng trong document hiện tại và các browsing context được nhúng. Chính sách được cấu hình bằng HTTP response header `Permissions-Policy`; từng phần tử `iframe` có thể dùng thuộc tính `allow` để cấp hoặc giới hạn tính năng cho frame cụ thể.

Khi có nhiều lớp iframe, quyền được đánh giá qua từng ranh giới cha-con. Một frame chỉ có thể truyền tiếp tính năng nếu chính nó đang được phép sử dụng tính năng đó. Nếu một cấp đã vô hiệu hóa tính năng, frame con không thể tự bật lại bằng cách đặt `allow` rộng hơn.

Ví dụ, trang `shop.example` nhúng `checkout.example`, rồi checkout nhúng `identity.example`. Nếu camera được cấp cho checkout nhưng checkout không được phép chuyển tiếp camera cho identity, frame identity không thể dùng camera dù thẻ iframe cuối có khai báo `allow="camera"`.

Bài học này tập trung vào kiểm thử nested iframe và cách allowlist được kế thừa qua nhiều cấp. Mục tiêu là hiểu đúng vai trò của response header, iframe container policy, default allowlist và policy riêng của từng document.

Sau bài học, bạn có thể:

- Phân biệt declared policy, inherited policy và container policy.
- Đọc đúng cú pháp `Permissions-Policy` header và iframe `allow`.
- Giải thích vì sao phải cấp quyền ở từng ranh giới cha-con.
- Phân biệt quyền của frame hiện tại với quyền frame đó có thể delegate tiếp.
- Kiểm thử chuỗi top-level → middle iframe → nested iframe.
- Chẩn đoán trường hợp một cấp từ chối tính năng và các cấp sau không thể bật lại.
- Phân biệt Permissions Policy với quyền người dùng, secure context, sandbox và Same-Origin Policy.

## 2. Các khái niệm cần phân biệt

Permissions Policy có nhiều lớp chính sách. Dùng đúng tên giúp tránh nhầm rằng một iframe `allow` có thể ghi đè mọi cấu hình ở cấp trên.

| Khái niệm | Ý nghĩa |
| --- | --- |
| Policy-controlled feature | Tính năng/API mà browser cho phép policy kiểm soát, ví dụ `geolocation`, `camera`, `microphone`, `fullscreen`. |
| Declared policy | Chính sách document khai báo qua response header `Permissions-Policy`. |
| Inherited policy | Trạng thái Enabled/Disabled document nhận từ parent document và container iframe của nó. |
| Container policy | Chính sách trên ranh giới iframe, được tạo từ thuộc tính `allow` (và một số thuộc tính legacy). |
| Allowlist | Tập origin được phép dùng một feature trong policy tương ứng. |
| Default allowlist | Quy tắc mặc định của từng feature khi header hoặc iframe `allow` không khai báo feature đó. |

### 2.1 Response header thuộc về document

`Permissions-Policy` là HTTP response header. Server gửi header cùng response HTML của document. Browser dùng policy đó cho document và việc delegate tính năng tới các browsing context con.

Ví dụ:

```http
Permissions-Policy: geolocation=(self "https://maps.example")
```

Header trên giới hạn Geolocation trong document và các frame được xét theo allowlist của document. `self` là origin của document nhận response; origin bên ngoài được ghi thành chuỗi có dấu ngoặc kép theo cú pháp Structured Fields.

Không đặt `Permissions-Policy` trong thẻ `<meta>` để thay thế response header. Policy này được giao qua HTTP response.

### 2.2 iframe allow là container policy

Thuộc tính `allow` được đặt trên phần tử `<iframe>` ở document cha:

```html
<iframe
  src="https://maps.example/embed"
  allow="geolocation">
</iframe>
```

Nó tạo container policy cho browsing context mà iframe chứa. Policy này được xét khi browser tạo document con và quyết định feature có được kế thừa qua ranh giới đó hay không.

`allow` không phải một quyền toàn cục cho toàn bộ cây frame. Mỗi iframe có container policy riêng.

### 2.3 Inherited policy là trạng thái bật/tắt được truyền xuống

Document con nhận inherited policy từ policy của document cha và container policy của iframe chứa nó. Nếu feature bị Disabled ở bước kế thừa, response header của document con không thể bật lại feature đó.

Khi feature được kế thừa ở trạng thái Enabled, document con có thể tiếp tục giới hạn việc sử dụng và delegate cho iframe con theo policy do chính document con khai báo cùng `allow` trên iframe con.

Điểm quan trọng: trạng thái kế thừa và allowlist do document hiện tại khai báo là hai phần khác nhau. Không nên coi allowlist của response header ở top-level như một danh sách nguyên văn phải lặp lại trong mọi iframe sâu hơn; mỗi cấp được đánh giá theo policy hiệu lực của document cha trực tiếp.

## 3. Browser kết hợp các lớp policy như thế nào?

Khi tạo một document trong iframe, browser xét các điều kiện theo ranh giới cha-con:

1. Feature có đang được bật trong policy của document cha không?
2. Policy của document cha có cho phép origin của document con không?
3. Container policy từ thuộc tính `allow` của iframe có khớp origin document con không?
4. Nếu iframe không khai báo feature trong `allow`, default allowlist của feature có cho phép kế thừa tự động không?
5. Khi document con tải response, header `Permissions-Policy` của chính nó có tiếp tục giới hạn feature cho document đó và các frame mà nó nhúng không?

Nếu một trong các bước kế thừa cần thiết trả về Disabled, frame con không thể khôi phục quyền chỉ bằng cách thêm một allowlist rộng hơn ở cấp dưới.

### 3.1 Feature phải được bật trong document cha

Một document không thể delegate feature mà chính nó đã bị policy vô hiệu hóa. Ví dụ, nếu top-level response trả:

```http
Permissions-Policy: geolocation=()
```

thì Geolocation bị tắt trong top-level và các document con. Dù iframe có `allow="geolocation"` và document con trả header cho phép mọi origin, trạng thái inherited Disabled vẫn chặn feature.

### 3.2 Origin của child phải được cho phép ở ranh giới hiện tại

Giả sử parent có header:

```http
Permissions-Policy: geolocation=(self "https://middle.example")
```

Parent chỉ cho phép document cùng origin và `https://middle.example` nhận feature theo header này. Một iframe tới `https://untrusted.example` không được nhận Geolocation chỉ vì nó có `allow="geolocation"`.

Với cross-origin iframe, cần có cả quyền từ policy của parent và sự delegate phù hợp trên iframe. Chỉ liệt kê origin trong header không tự động cấp feature cho iframe cross-origin.

### 3.3 iframe allow phải cấp cho document được nhúng

Ví dụ:

```html
<iframe
  src="https://middle.example"
  allow="geolocation">
</iframe>
```

`allow="geolocation"` là dạng rút gọn của `allow="geolocation 'src'"`. Token `'src'` đại diện cho origin của URL trong thuộc tính `src` tại thời điểm khai báo container policy.

Nếu header của parent đã cho phép `middle.example`, iframe `allow` này cho phép document được tải từ origin đó nhận feature qua ranh giới iframe.

### 3.4 Policy riêng của document con có thể giới hạn cấp tiếp theo

Sau khi document middle được phép dùng Geolocation, response của nó có thể khai báo:

```http
Permissions-Policy: geolocation=(self "https://leaf.example")
```

Khi middle nhúng leaf, policy của middle được xét cho origin leaf và iframe `allow` của middle cũng phải delegate feature. Nếu middle khai báo `geolocation=()`, leaf không thể bật lại.

Nếu middle không khai báo directive `geolocation`, inherited feature vẫn có thể được delegate tiếp bằng `allow` trên iframe con, theo default allowlist và các điều kiện ở ranh giới đó. Hãy phân biệt trường hợp không khai báo directive với trường hợp khai báo allowlist chỉ gồm `self`.

## 4. Cú pháp HTTP Permissions-Policy

Header dùng cú pháp Structured Fields. Mỗi feature là một dictionary member; nhiều feature phân cách bằng dấu phẩy.

Ví dụ:

```http
Permissions-Policy: geolocation=(self "https://maps.example"), camera=(), microphone=()
```

Một số dạng allowlist:

| Giá trị header | Ý nghĩa |
| --- | --- |
| `geolocation=*` | Cho phép feature ở mọi origin theo policy này. |
| `geolocation=()` | Không cho phép origin nào dùng feature. |
| `geolocation=(self)` | Chỉ cho phép origin của document nhận header. |
| `geolocation=(self "https://maps.example")` | Cho phép document hiện tại và origin được liệt kê. |
| `geolocation=("https://maps.example")` | Chỉ cho phép origin được liệt kê; document hiện tại cũng có thể bị chặn nếu không nằm trong allowlist. |

Origin trong header được đặt trong dấu ngoặc kép. `self` là token không đặt trong dấu ngoặc kép.

### 4.1 Allowlist hẹp hơn thường an toàn hơn

Không dùng `*` cho camera, microphone, geolocation hoặc các tính năng nhạy cảm nếu không có yêu cầu rõ ràng. Liệt kê origin đối tác cụ thể giúp giới hạn nơi được nhận feature.

Subdomain khác nhau là cross-origin dù có thể cùng site. Port khác nhau cũng tạo origin khác nhau. Ví dụ `https://app.example` và `https://widget.example` cần được xét riêng; `http://localhost:3000` và `http://localhost:3001` cũng là hai origin khác nhau.

### 4.2 Header không khai báo một feature

Nếu response không khai báo directive cho một feature, document không tự động bị từ chối chỉ vì thiếu directive. Việc kế thừa và delegate tiếp phụ thuộc default allowlist của feature, policy kế thừa và container policy của iframe.

Default allowlist không giống nhau cho mọi feature. Một số feature có default `self`, một số có default `*`. Hãy tra default allowlist của đúng feature thay vì suy luận từ một ví dụ khác.

## 5. Cú pháp iframe allow

Giá trị `allow` dùng cú pháp HTML attribute serialization, không phải cú pháp Structured Fields của HTTP header.

Ví dụ:

```html
<iframe
  src="https://maps.example/embed"
  allow="geolocation 'src'; camera 'none'; fullscreen 'self'">
</iframe>
```

| Giá trị iframe | Ý nghĩa |
| --- | --- |
| `geolocation 'src'` | Cho phép origin được khai báo bởi URL `src` của iframe. |
| `geolocation 'self'` | Cho phép origin của document chứa phần tử iframe. |
| `geolocation https://maps.example` | Cho phép origin được chỉ định. Origin trong attribute không đặt trong dấu ngoặc kép. |
| `geolocation 'none'` | Không cho phép origin nào dùng feature trong frame này. |
| `geolocation *` | Cho phép mọi origin trong container policy này. |

`'src'`, `'self'` và `'none'` là các keyword có dấu nháy đơn trong attribute. Origin thông thường được ghi trực tiếp, không có dấu nháy.

### 5.1 Feature không được liệt kê trong allow

Nếu `allow` không liệt kê một feature, browser dùng default allowlist của feature để quyết định container policy. Vì thế, thiếu `allow` không có nghĩa mọi feature đều bị chặn hoặc đều được bật.

Với các feature như Geolocation có default allowlist `self`, cross-origin iframe thường cần được delegate rõ ràng. Cách rõ ràng nhất là khai báo feature và allowlist mong muốn trên iframe.

### 5.2 Không dùng cú pháp header trong attribute

Ví dụ đúng:

```html
<iframe
  src="https://maps.example"
  allow="geolocation 'src'">
</iframe>
```

Header tương ứng có cú pháp khác:

```http
Permissions-Policy: geolocation=(self "https://maps.example")
```

Không sao chép nguyên văn chuỗi `geolocation=(self "...")` của header vào thuộc tính `allow`.

## 6. Mô hình ba cấp: top-level, middle và leaf

Dùng ba origin để quan sát quá trình kế thừa:

| Vai trò | Origin | Trách nhiệm |
| --- | --- | --- |
| A — top-level | `http://localhost:3000` | Quyết định có cấp Geolocation cho middle hay không. |
| B — middle iframe | `http://localhost:3001` | Nhận quyền từ A và quyết định có delegate cho leaf hay không. |
| C — leaf iframe | `http://localhost:3002` | Chỉ dùng Geolocation nếu được cấp qua cả ranh giới A→B và B→C. |

Các port khác nhau tạo các origin khác nhau, dù cùng hostname `localhost`.

### 6.1 Cấu hình response của A

Server A trả header:

```http
Permissions-Policy: geolocation=(self "http://localhost:3001")
```

HTML của A:

```html
<iframe
  id="middle"
  src="http://localhost:3001/middle.html"
  allow="geolocation">
</iframe>
```

Header cho phép origin A và B. Thuộc tính `allow` delegate Geolocation qua iframe A→B.

### 6.2 Cấu hình response của B

Server B trả header:

```http
Permissions-Policy: geolocation=(self "http://localhost:3002")
```

HTML của B:

```html
<iframe
  id="leaf"
  src="http://localhost:3002/leaf.html"
  allow="geolocation">
</iframe>
```

Header của B cho phép B và C. Thuộc tính `allow` trên iframe của B delegate Geolocation qua ranh giới B→C.

### 6.3 Document C kiểm tra tính năng

Trang leaf có thể kiểm tra policy và gọi API:

```javascript
const policy = document.permissionsPolicy || document.featurePolicy;

console.log(
  "Geolocation allowed by document policy:",
  policy?.allowsFeature?.("geolocation")
);

function requestLocation() {
  navigator.geolocation.getCurrentPosition(
    position => {
      console.log("Location available:", position.coords.latitude);
    },
    error => {
      console.error("Geolocation failed:", error.code, error.message);
    }
  );
}
```

`allowsFeature()` là API introspection có mức hỗ trợ khác nhau giữa browser. Nếu API không có, kiểm tra Console và kết quả gọi feature trong browser mục tiêu.

## 7. Vì sao quyền không tự truyền qua mọi cấp?

Permissions Policy không hoạt động như một cờ toàn cục bật ở top-level rồi tự động cho phép mọi frame sâu hơn. Mỗi document con phải được tạo với inherited policy phù hợp, và từng document có thể áp dụng declared policy của riêng nó.

Một cách đọc hữu ích:

- A phải được phép dùng feature và phải delegate qua iframe A→B.
- B phải nhận feature ở trạng thái Enabled.
- Policy response của B có thể tiếp tục giới hạn những origin được phép nhận feature từ B.
- B phải delegate qua iframe B→C.
- C chỉ được dùng feature nếu mọi điều kiện cần thiết tại hai ranh giới đều đạt.

Việc B được phép dùng Geolocation không có nghĩa mọi iframe mà B tạo ra đều tự động được phép. Việc C có `allow="geolocation"` cũng không thể sửa một lần từ chối đã xảy ra ở A→B hoặc trong policy của B.

### 7.1 Tách biệt inherited state và allowlist của từng document

Giả sử A chỉ khai báo `geolocation=(self "http://localhost:3001")`. Header này cho B quyền kế thừa tại ranh giới A→B. Sau khi B đã được phép, B có thể khai báo policy riêng để giới hạn các frame con, ví dụ chỉ `self` và `http://localhost:3002`.

Nếu B không khai báo directive `geolocation`, B vẫn có thể delegate cho C bằng iframe `allow` phù hợp, miễn là feature còn Enabled trong B và default/container policy cho phép. Nếu B khai báo `geolocation=(self)`, B giữ quyền cho chính nó nhưng không cho origin C kế thừa qua B.

Đây là lý do cần kiểm tra header của từng document, thay vì chỉ đọc header top-level và suy ra trạng thái mọi hậu duệ.

## 8. Default allowlist và quyền delegate tự động

Mỗi feature có default allowlist riêng. Hai dạng phổ biến:

- `self`: feature mặc định được kế thừa bởi document cùng origin với parent; cross-origin child cần được delegate rõ ràng.
- `*`: feature mặc định có thể được kế thừa bởi mọi origin, trừ khi policy hoặc container policy giới hạn lại.

Ví dụ Geolocation thường có default allowlist là `self`. Vì vậy, iframe cross-origin cần được cấp rõ ràng. Không suy ra default của Camera, Microphone, Fullscreen hoặc feature khác từ Geolocation; kiểm tra danh sách feature và default allowlist mà browser hỗ trợ.

### 8.1 Không khai báo header khác với khai báo empty allowlist

Hai trường hợp sau có ý nghĩa khác nhau:

```http
# Không có directive geolocation trong response
```

và:

```http
Permissions-Policy: geolocation=()
```

Trường hợp đầu không tạo declared restriction cho feature đó; default allowlist và container policy quyết định việc kế thừa. Trường hợp thứ hai chủ động vô hiệu hóa Geolocation cho mọi origin trong phạm vi policy của document, bao gồm nested browsing contexts.

### 8.2 iframe allow không khai báo feature

Nếu iframe không liệt kê Geolocation trong `allow`, browser áp dụng default allowlist của Geolocation cho container policy. Với default `self`, cùng-origin child có thể được tự động cho phép khi parent đã có feature; cross-origin child sẽ không tự được cấp.

Nếu iframe có khai báo `allow="geolocation"`, container policy dùng `'src'` làm allowlist mặc định cho feature được nêu. Đây là một cơ chế delegate rõ ràng cho origin được khai báo trong `src`.

## 9. Điều hướng iframe sang origin khác

Một iframe có thể điều hướng sau khi tải lần đầu. Policy được cấp cho origin ban đầu không tự động áp dụng cho mọi origin mà frame có thể chuyển tới.

Ví dụ:

```html
<iframe
  src="https://trusted.example/start"
  allow="geolocation">
</iframe>
```

`allow="geolocation"` tương đương `'src'`, tức origin của URL `src` được khai báo. Nếu document trong iframe điều hướng sang `https://next.example`, origin mới không được tự động nhận policy dành cho origin ban đầu.

Nếu luồng điều hướng là chủ đích và origin đích đã được tin cậy, có thể liệt kê rõ các origin được phép:

```html
<iframe
  src="https://trusted.example/start"
  allow="geolocation https://trusted.example https://next.example">
</iframe>
```

Response header của parent cũng phải cho phép origin phù hợp. Đừng thêm origin đích vào `allow` nếu không kiểm soát hoặc không tin cậy nội dung có thể được tải tại đó.

### 9.1 Test navigation

1. Tạo iframe tới origin B với `allow="geolocation"` và xác nhận B được cấp feature.
2. Cho B điều hướng sang origin C.
3. Quan sát C không nhận quyền chỉ dựa trên `'src'` của origin B.
4. Thêm origin C vào allowlist iframe và policy response của parent theo nhu cầu.
5. Reload, lặp lại test và xác nhận origin ngoài allowlist vẫn bị chặn.

## 10. Permissions Policy không thay thế quyền người dùng

Permissions Policy là giới hạn do website/embedding document đặt ra. Nó không tự cấp quyền truy cập thiết bị hoặc dữ liệu cho người dùng.

Để Geolocation hoạt động, còn cần:

- Browser hỗ trợ feature và API tương ứng.
- Document chạy trong secure context theo yêu cầu của API.
- Permissions Policy cho phép feature ở document hiện tại.
- Người dùng chưa từ chối quyền Geolocation cho website/browser.
- Hệ điều hành và thiết bị cho phép truy cập vị trí.

Với Camera/Microphone, còn phụ thuộc thiết bị có phần cứng, quyền hệ điều hành và trạng thái permission của browser. Một iframe được policy cho phép vẫn có thể nhận lỗi khi người dùng từ chối quyền.

### 10.1 Policy cho phép nhưng người dùng từ chối

Nếu `allowsFeature("geolocation")` trả về `true`, điều đó chỉ nói policy không chặn feature cho document đang kiểm tra. Nó không chứng minh người dùng đã cấp quyền hoặc vị trí hiện có thể truy xuất.

### 10.2 Policy chặn dù người dùng đã cấp quyền

Ngược lại, người dùng có thể đã cấp quyền Geolocation cho site nhưng Permissions Policy của một iframe vẫn chặn feature. Quyền người dùng và policy là hai lớp kiểm soát độc lập; cả hai phải cho phép thì API mới có thể hoạt động.

## 11. Phân biệt Permissions Policy với sandbox, SOP và CSP

| Cơ chế | Kiểm soát chính | Không thay thế |
| --- | --- | --- |
| Permissions Policy | Feature/API mà document được phép sử dụng. | User permission, sandbox, SOP hoặc CSP. |
| iframe `sandbox` | Khả năng của nội dung nhúng như scripts, forms, origin và một số hành vi khác. | Allowlist feature của Permissions Policy. |
| Same-Origin Policy (SOP) | Quyền truy cập dữ liệu/DOM giữa các origin. | Việc một API như Geolocation được bật hay tắt. |
| Content Security Policy (CSP) | Nguồn script, style, frame, kết nối và các loại tài nguyên khác. | Việc cấp quyền Camera, Microphone hoặc Geolocation. |

Các cơ chế có thể cùng áp dụng. Ví dụ, iframe có thể được Permissions Policy cấp Geolocation nhưng `sandbox` làm origin của nó trở thành opaque; khi đó origin không khớp allowlist như một origin thông thường. Một iframe cũng có thể được policy cho phép Camera nhưng CSP hoặc sandbox vẫn hạn chế các hành vi khác.

Không dùng `allow` như một cách bỏ sandbox, bỏ SOP hoặc bỏ CSP. Mỗi cơ chế giải quyết một lớp bảo vệ khác nhau.

## 12. Kiểm tra policy trong JavaScript

Một số browser triển khai API introspection để kiểm tra policy hiệu lực:

```javascript
const policy =
  document.permissionsPolicy ||
  document.featurePolicy;

if (policy && typeof policy.allowsFeature === "function") {
  console.log("geolocation:", policy.allowsFeature("geolocation"));
  console.log("camera:", policy.allowsFeature("camera"));
} else {
  console.warn("Permissions Policy introspection is unavailable");
}
```

`document.permissionsPolicy` là tên API theo specification hiện hành. `document.featurePolicy` là tên cũ còn xuất hiện ở một số browser. Cả API introspection và danh sách feature hỗ trợ đều có thể khác nhau theo browser.

### 12.1 Kiểm tra iframe element

Specification cũng định nghĩa `iframe.permissionsPolicy` để quan sát policy của container:

```javascript
const frame = document.querySelector("#middle");
const framePolicy =
  frame.permissionsPolicy ||
  frame.featurePolicy;

console.log(
  framePolicy?.allowsFeature?.("geolocation")
);
```

Kết quả trên iframe element chỉ phản ánh policy có thể quan sát từ document cha và thuộc tính iframe. Nó không chứng minh document cross-origin bên trong đã nhận feature, vì response header của document con hoặc navigation sau đó có thể tiếp tục giới hạn quyền.

### 12.2 API introspection không thay thế kiểm thử thực tế

Nếu API introspection không có hoặc không thống nhất, dùng ba nguồn:

1. Response header của từng document trong Network.
2. Console message khi browser chặn feature do Permissions Policy.
3. Kết quả gọi API thật trong từng frame, sau khi đã xử lý user permission.

Đừng chỉ kiểm tra ở top-level rồi suy ra kết quả ở leaf iframe.

## 13. Lab: kiểm thử kế thừa qua ba origin

Lab sử dụng:

- A: `http://localhost:3000`
- B: `http://localhost:3001`
- C: `http://localhost:3002`

Mỗi port là một origin khác nhau. `localhost` thường được browser xem là potentially trustworthy để thử API yêu cầu secure context, nhưng cần xác nhận trên browser mục tiêu.

### 13.1 Phát response header trên A

Nếu dùng Express, middleware của server A:

```javascript
app.use((req, res, next) => {
  res.setHeader(
    "Permissions-Policy",
    'geolocation=(self "http://localhost:3001")'
  );
  next();
});
```

Trang A:

```html
<!doctype html>
<html lang="vi">
<body>
  <h1>Top-level A</h1>
  <iframe
    id="middle"
    src="http://localhost:3001/middle.html"
    allow="geolocation"
    title="Middle frame">
  </iframe>
</body>
</html>
```

### 13.2 Phát response header trên B

Server B:

```javascript
app.use((req, res, next) => {
  res.setHeader(
    "Permissions-Policy",
    'geolocation=(self "http://localhost:3002")'
  );
  next();
});
```

Trang B:

```html
<!doctype html>
<html lang="vi">
<body>
  <h2>Middle B</h2>
  <iframe
    id="leaf"
    src="http://localhost:3002/leaf.html"
    allow="geolocation"
    title="Leaf frame">
  </iframe>
</body>
</html>
```

### 13.3 Trang C gọi Geolocation

Trang C:

```html
<!doctype html>
<html lang="vi">
<body>
  <h3>Leaf C</h3>
  <button id="locate">Request location</button>
  <pre id="result"></pre>
  <script>
    const output = document.querySelector("#result");
    const policy =
      document.permissionsPolicy ||
      document.featurePolicy;

    output.textContent =
      "Policy allows geolocation: " +
      (policy?.allowsFeature?.("geolocation") ?? "unknown");

    document.querySelector("#locate").addEventListener("click", () => {
      if (!navigator.geolocation) {
        output.textContent += "\nGeolocation API unavailable";
        return;
      }

      navigator.geolocation.getCurrentPosition(
        position => {
          output.textContent +=
            "\nSuccess: " + position.coords.latitude;
        },
        error => {
          output.textContent +=
            "\nError " + error.code + ": " + error.message;
        }
      );
    });
  </script>
</body>
</html>
```

Trong browser, cho phép Geolocation cho các origin lab nếu browser yêu cầu. Nhấn nút trong frame C và quan sát Console, kết quả API cùng policy introspection.

### 13.4 Kết quả mong đợi của cấu hình cơ sở

Với header A cho phép B, header B cho phép C và cả hai iframe đều có `allow="geolocation"`:

- A có thể dùng Geolocation nếu người dùng và browser cho phép.
- B nhận Geolocation qua ranh giới A→B.
- C nhận Geolocation qua ranh giới B→C.
- C vẫn cần secure context và user permission phù hợp.

## 14. Ma trận kiểm thử nested iframe

Thay đổi từng cấu hình một để xác định chính xác ranh giới gây chặn.

| Ca kiểm thử | Header A | iframe A→B | Header B | iframe B→C | Kết quả mong đợi tại C |
| --- | --- | --- | --- | --- | --- |
| T1 — Cấp đủ hai cấp | Cho phép A và B | `allow="geolocation"` | Cho phép B và C | `allow="geolocation"` | Được policy cho phép. |
| T2 — A không delegate | Cho phép A và B | Bỏ `allow` | Cho phép B và C | `allow="geolocation"` | B bị chặn; C cũng bị chặn. |
| T3 — A tắt feature | `geolocation=()` | `allow="geolocation"` | Cho phép B và C | `allow="geolocation"` | B và C bị chặn. |
| T4 — B tắt feature | Cho phép A và B | `allow="geolocation"` | `geolocation=()` | `allow="geolocation"` | B và C bị chặn. |
| T5 — B chỉ cho self | Cho phép A và B | `allow="geolocation"` | `geolocation=(self)` | `allow="geolocation"` | B được policy cho phép; C bị chặn. |
| T6 — B không khai báo directive | Cho phép A và B | `allow="geolocation"` | Không có directive geolocation | `allow="geolocation"` | B có thể delegate tiếp cho C. |
| T7 — B cho phép C nhưng iframe thiếu allow | Cho phép A và B | `allow="geolocation"` | Cho phép B và C | Bỏ `allow` | C bị chặn nếu default allowlist không tự cấp cross-origin. |
| T8 — Origin C ngoài allowlist B | Cho phép A và B | `allow="geolocation"` | Chỉ cho B và origin khác | `allow="geolocation"` | C bị chặn. |

Ở T6, B không khai báo directive cho Geolocation nên không thêm giới hạn allowlist riêng cho feature đó. B vẫn phải nhận inherited feature từ A và phải delegate qua iframe B→C.

Ở T7, `allow` không liệt kê Geolocation nên browser dùng default allowlist. Với Geolocation mặc định `self`, cross-origin C không được tự động cấp.

## 15. Quy trình thực hiện lab

Thực hiện theo thứ tự để tránh thay nhiều policy cùng lúc:

1. Khởi chạy ba ứng dụng tại port 3000, 3001 và 3002.
2. Xác nhận A trả header cho phép origin B.
3. Xác nhận iframe A→B có `allow="geolocation"`.
4. Xác nhận B trả header cho phép chính B và origin C.
5. Xác nhận iframe B→C có `allow="geolocation"`.
6. Mở A, kiểm tra response header của cả A và B trong Network.
7. Kiểm tra Console tại từng frame; gọi API từ B và C.
8. Cấp quyền Geolocation cho các origin lab khi browser hỏi.
9. Chạy từng ca T1–T8 trong ma trận, mỗi lần chỉ đổi một điều kiện.
10. Ghi lại origin, header, thuộc tính iframe, policy introspection và kết quả API.

### 15.1 Kiểm tra đúng response của từng document

Trong DevTools → Network:

- Chọn request document A và xem Response Headers.
- Chọn request `middle.html` và xem header do server B trả.
- Chọn request `leaf.html` và xác nhận response cuối của C.
- Kiểm tra redirect nếu URL ban đầu không phải URL cuối cùng.
- Đảm bảo header được phát trên HTML response thực tế, không chỉ nằm trong cấu hình server hoặc response nội bộ phía sau reverse proxy.

### 15.2 Kiểm tra từng frame

Mở Console execution context selector và chọn lần lượt A, B, C. Chạy:

```javascript
({
  origin: location.origin,
  secureContext: isSecureContext,
  geolocationApi: typeof navigator.geolocation,
  policyAllowsGeolocation:
    (document.permissionsPolicy || document.featurePolicy)
      ?.allowsFeature?.("geolocation")
});
```

Nếu browser không có API introspection, giá trị policy sẽ là `undefined`; tiếp tục kiểm tra bằng Console message và thao tác Geolocation thật.

## 16. Kiểm thử origin và navigation

Nested iframe thường phức tạp hơn khi có redirect, đổi `src` hoặc điều hướng bằng script. Hãy kiểm tra các tình huống sau.

### 16.1 Cùng site nhưng khác origin

Ví dụ:

- `https://app.example.com`
- `https://widget.example.com`

Hai hostname có thể cùng site nhưng là hai origin khác nhau. Allowlist `self` không tự bao gồm subdomain khác. Tương tự, hai URL `http://localhost:3000` và `http://localhost:3001` khác origin vì port khác nhau.

### 16.2 Cùng origin nhưng khác path

`https://app.example.com` và `https://app.example.com/embed` cùng origin. Không cần liệt kê riêng path trong allowlist; policy đánh giá origin, không đánh giá path.

### 16.3 Origin đích sau redirect

Nếu iframe ban đầu khai báo origin B nhưng response redirect tới C, đừng mặc định rằng quyền dành cho B cũng áp dụng cho C. Kiểm tra origin cuối cùng, header của response và allowlist trên container. Khi cần cho phép điều hướng có chủ đích, liệt kê origin đích cụ thể trong iframe `allow` và trong policy của parent.

### 16.4 Sandbox và opaque origin

Iframe dùng `sandbox` mà không có `allow-same-origin` có thể nhận opaque origin. Opaque origin không khớp một origin cụ thể trong allowlist. Không mở rộng allowlist thành `*` chỉ để làm một iframe sandbox hoạt động; trước hết xác định vì sao frame cần feature và có thể thiết kế capability an toàn hơn hay không.

## 17. Các lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| B không dùng được Geolocation dù A header liệt kê B | Thiếu `allow` trên iframe A→B hoặc origin B không khớp chính xác. | Kiểm tra container policy, `src`, scheme, host và port. |
| C không dùng được dù B được phép | B không delegate qua iframe B→C, hoặc header B giới hạn allowlist chỉ còn `self`. | Kiểm tra response header của B và thuộc tính `allow` trên iframe C. |
| `allow` rộng nhưng feature vẫn bị chặn | Parent hoặc một document tổ tiên đã disable feature. | Kiểm tra header và Console tại từng cấp từ top-level xuống. |
| Same-site iframe bị chặn | Same-site không đồng nghĩa same-origin. | So sánh scheme, hostname và port. |
| Feature hoạt động trong B nhưng không ở C | B có quyền dùng nhưng policy của B không cho C kế thừa. | Kiểm tra declared policy của B và container policy B→C. |
| API trả permission denied dù policy introspection true | Người dùng, OS hoặc browser chưa cấp quyền; secure context hoặc thiết bị có thể không đáp ứng. | Kiểm tra permission UI, `isSecureContext`, Console và trạng thái thiết bị. |
| Chỉ lỗi sau redirect/navigation | Origin cuối không nằm trong allowlist được áp dụng. | Theo dõi redirect chain và kiểm tra `src`/origin cuối. |
| Header có trong cấu hình nhưng không có ở Network | Reverse proxy, CDN hoặc route đã bỏ/ghi đè header. | Kiểm tra response cuối mà browser nhận. |
| Feature không bị giới hạn như dự kiến | Tên directive sai hoặc browser không hỗ trợ feature. | Kiểm tra feature token và browser support. |

### 17.1 Không suy luận chỉ từ lỗi API

Geolocation có thể trả lỗi permission denied vì policy, user permission hoặc cấu hình thiết bị. Một lỗi API riêng lẻ không chỉ ra chính xác cấp iframe gây chặn. Đối chiếu response headers, Console, policy introspection và kiểm thử control ở top-level.

### 17.2 Không nhầm allow với user permission

Thêm `allow="camera"` chỉ delegate feature qua iframe. Nó không tự bấm nút cấp quyền của browser, không mở quyền camera trong hệ điều hành và không bảo đảm người dùng chấp thuận.

## 18. Hướng dẫn thiết kế policy cho ứng dụng nhiều cấp

Khi xây dựng widget hoặc micro-frontend nhiều lớp:

1. Liệt kê feature thật sự cần dùng ở mỗi document.
2. Ghi lại origin của top-level, từng iframe và mọi origin có thể được điều hướng tới.
3. Ở mỗi document, dùng `Permissions-Policy` để đặt giới hạn tối đa mà document đó được phép delegate.
4. Trên từng iframe, dùng `allow` để cấp đúng feature cho đúng origin.
5. Tránh `*` với feature nhạy cảm; chỉ dùng khi mọi origin trong phạm vi thực sự được tin cậy.
6. Không khai báo directive nếu muốn giữ default behavior chỉ sau khi đã hiểu default allowlist của feature.
7. Kiểm thử cả nhánh thành công và nhánh bị từ chối trước khi phát hành.
8. Kiểm tra lại policy khi thêm đối tác, thay subdomain, đổi CDN hoặc thêm redirect.
9. Ghi nhận policy trong tài liệu triển khai để nhóm vận hành có thể kiểm tra response thật.

### 18.1 Quyền tối thiểu theo từng frame

Ví dụ, trang chính chỉ cần Geolocation cho widget bản đồ, còn widget quảng cáo không cần bất kỳ quyền thiết bị nào. Hãy đặt policy cho phép origin bản đồ, sau đó chỉ thêm `allow="geolocation"` vào iframe bản đồ. Các iframe khác không được delegate feature.

### 18.2 Giới hạn ở document con

Nếu một widget được phép dùng Geolocation nhưng không cần chuyển quyền đó cho nội dung do người dùng tạo, response của widget có thể khai báo `geolocation=(self)` hoặc `geolocation=()` tùy yêu cầu. Sau đó, các iframe con sẽ không thể tự mở rộng quyền đã bị giới hạn.

## 19. Checklist kiểm thử nested iframe

- [ ] Đã liệt kê chính xác origin của top-level, middle và leaf.
- [ ] Đã xác định default allowlist của feature đang kiểm thử.
- [ ] Đã kiểm tra `Permissions-Policy` trên response của từng document.
- [ ] Đã kiểm tra `allow` trên từng iframe container.
- [ ] Đã xác nhận parent được phép dùng feature trước khi delegate.
- [ ] Đã kiểm tra trường hợp thiếu `allow` ở mỗi ranh giới.
- [ ] Đã kiểm tra trường hợp parent header dùng empty allowlist.
- [ ] Đã kiểm tra child header chỉ cho `self`.
- [ ] Đã kiểm tra child không khai báo directive và delegate tiếp.
- [ ] Đã thử same-site nhưng cross-origin và khác port.
- [ ] Đã thử iframe redirect/navigation sang origin khác.
- [ ] Đã thử sandbox/opaque origin nếu ứng dụng có dùng.
- [ ] Đã phân biệt policy denial với user permission denial.
- [ ] Đã xác nhận header trên response cuối qua reverse proxy/CDN.
- [ ] Đã kiểm tra trên các browser mục tiêu.

## 20. Câu hỏi tự kiểm tra

1. Declared policy khác inherited policy ở điểm nào?
2. Thuộc tính iframe `allow` tạo ra loại policy nào?
3. Vì sao một child không thể bật lại feature đã bị parent vô hiệu hóa?
4. `allow="geolocation"` tương đương allowlist nào?
5. Vì sao header của parent liệt kê origin chưa đủ để cấp feature cho cross-origin iframe?
6. Nếu middle không khai báo directive Geolocation, middle có thể delegate cho leaf trong điều kiện nào?
7. Nếu middle khai báo `geolocation=(self)`, leaf cross-origin sẽ nhận kết quả gì?
8. Vì sao `self` không bao gồm subdomain khác hoặc port khác?
9. Điều gì xảy ra khi iframe điều hướng sang origin không nằm trong allowlist?
10. Permissions Policy khác user permission như thế nào?
11. Vì sao `allowsFeature()` trả về true chưa chứng minh API chắc chắn hoạt động?
12. Cần kiểm tra những response và iframe attribute nào khi leaf frame bị chặn?

## 21. Tổng kết

Permissions Policy kiểm soát việc document sử dụng và delegate các browser features qua response header `Permissions-Policy` và container policy từ iframe `allow`. Khi browser tạo một nested document, inherited policy được xác định từ policy của document cha cùng container policy của iframe. Nếu feature bị Disabled tại một ranh giới, document con và các hậu duệ không thể bật lại bằng allowlist rộng hơn.

Mỗi document có thể khai báo policy riêng để giới hạn feature cho chính nó và các frame mà nó nhúng. Vì vậy, cần phân biệt inherited Enabled/Disabled với declared allowlist của từng document. Với chuỗi A→B→C, A phải cấp feature cho B; sau khi B nhận feature, policy của B và iframe B→C quyết định C có được nhận tiếp hay không. Header của A không phải một danh sách origin cần sao chép nguyên văn vào mọi cấp.

Khi kiểm thử, xác nhận response header của từng document, thuộc tính `allow` trên từng iframe, origin cuối sau redirect/navigation và default allowlist của feature. Cuối cùng, nhớ rằng policy chỉ là một lớp kiểm soát: secure context, user permission, sandbox, SOP và CSP vẫn có thể ảnh hưởng tới kết quả sử dụng API.
