# Permissions Policy: kiểm soát quyền sử dụng tính năng trình duyệt

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích Permissions Policy và lý do website cần giới hạn các API nhạy cảm của browser.
2. Cấu hình HTTP response header Permissions-Policy để cho phép hoặc chặn tính năng theo origin.
3. Dùng thuộc tính allow trên iframe để ủy quyền tính năng cho nội dung nhúng.
4. Hiểu cách policy được kế thừa qua cây iframe và vì sao frame con không thể tự bật lại tính năng đã bị frame cha chặn.
5. Phân biệt Permissions Policy với quyền do người dùng cấp, Permissions API, CSP, CORS và iframe sandbox.
6. Áp dụng nguyên tắc least privilege cho camera, microphone, geolocation, fullscreen và các tính năng mạnh khác.
7. Kiểm tra hành vi policy bằng HTTPS, Chrome DevTools và browser matrix.

> **Bối cảnh:** Module Browser Security phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; đồng thời thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types và security headers. Permissions Policy bổ sung một lớp kiểm soát cho các tính năng mạnh của browser, đặc biệt khi website nhúng iframe từ origin khác.

## 1. Permissions Policy giải quyết vấn đề gì?

Browser cung cấp nhiều API có thể truy cập tài nguyên hoặc khả năng nhạy cảm của thiết bị:

- Camera và microphone.
- Vị trí địa lý (geolocation).
- Chia sẻ màn hình.
- Fullscreen.
- Clipboard.
- USB, serial và một số thiết bị phần cứng.
- Autoplay và các khả năng ảnh hưởng tới trải nghiệm người dùng.

Các API này hữu ích, nhưng một trang hoặc nội dung nhúng không phải lúc nào cũng cần chúng. Nếu một trang chứa nhiều iframe từ nhà cung cấp khác nhau, việc cho phép mọi frame sử dụng mọi tính năng sẽ mở rộng bề mặt tấn công và quyền riêng tư.

Permissions Policy cho phép chủ website khai báo tính năng nào được sử dụng trong document và origin nào có thể được cấp tính năng đó trong các iframe lồng bên trong.

Ví dụ website không cần camera, microphone hoặc vị trí:

    Permissions-Policy: camera=(), microphone=(), geolocation=()

Browser áp dụng policy này cho document và các browsing context con trong phạm vi tương ứng. Nếu JavaScript cố gọi API bị policy chặn, browser có thể từ chối thao tác, trả trạng thái bị từ chối hoặc không cho phép tính năng hoạt động, tùy API.

### Permissions Policy là lớp kiểm soát của website

Permissions Policy trả lời câu hỏi: website này có cho phép document hoặc iframe sử dụng tính năng browser này hay không?

Nó không tự cấp quyền camera hoặc vị trí cho người dùng. Nếu policy cho phép, browser vẫn áp dụng permission prompt, cài đặt quyền của người dùng, yêu cầu secure context và các điều kiện khác của API.

## 2. Hai cơ chế thiết lập policy

| Cơ chế | Phạm vi | Mục đích |
| --- | --- | --- |
| HTTP response header Permissions-Policy | Document nhận response và nội dung nhúng bên trong | Thiết lập ranh giới quyền ở cấp trang |
| Thuộc tính allow trên iframe | Một iframe cụ thể | Ủy quyền hoặc thu hẹp tính năng cho frame đó |

Header được phát từ server của document. Thuộc tính allow được đặt trên phần tử iframe ở trang cha.

### Header đặt giới hạn ở cấp trang

    Permissions-Policy: camera=(), microphone=(), geolocation=(), display-capture=()

Policy trên chặn các tính năng được liệt kê trong document và các frame con theo quy tắc kế thừa.

### iframe allow ủy quyền cho một frame cụ thể

    <iframe
      src="https://meet.example.test/room/123"
      title="Phòng họp"
      allow="camera; microphone; fullscreen">
    </iframe>

Thuộc tính allow yêu cầu browser cấp các tính năng được liệt kê cho nội dung của iframe, trong giới hạn policy của trang cha. Nó không tự vượt qua giới hạn mà header của parent đã đặt.

### Hai cơ chế phối hợp

    Response của trang host
    Permissions-Policy:
      camera=(self "https://meet.example.test")
      microphone=(self "https://meet.example.test")
                     |
                     v
    Trang host tạo iframe
    allow="camera; microphone"
                     |
                     v
    Browser tính policy hiệu lực cho iframe
                     |
                     v
    Frame chỉ được dùng tính năng nếu mọi lớp đều cho phép

Header định nghĩa tập origin tối đa được phép. Thuộc tính allow của iframe giới hạn việc cấp quyền cho frame cụ thể. Cách làm này giúp trang host kiểm soát tập nguồn tin cậy ở cấp response và chỉ cấp đúng quyền cần thiết cho từng iframe.

## 3. Cú pháp HTTP header Permissions-Policy

Cú pháp tổng quát:

    Permissions-Policy: <feature>=<allowlist>

Header dùng cú pháp Structured Fields. Nhiều directive có thể được khai báo trong cùng header, phân tách bằng dấu phẩy:

    Permissions-Policy: camera=(), microphone=(), geolocation=(), fullscreen=(self)

Tên gọi cũ của cơ chế này là Feature Policy. Tên HTTP header và cú pháp header đã được đổi sang Permissions-Policy; cú pháp thuộc tính allow trên iframe vẫn giữ dạng riêng tương thích với cú pháp cũ. Với ứng dụng mới, dùng Permissions-Policy và không dựa vào header Feature-Policy cũ.

Permissions-Policy được gửi qua HTTP response header. Không đặt policy này trong meta http-equiv rồi kỳ vọng browser áp dụng như header.

Các giá trị allowlist thường gặp:

| Giá trị | Ý nghĩa |
| --- | --- |
| () | Không cho phép origin nào sử dụng tính năng |
| * | Cho phép mọi origin, bao gồm các browsing context lồng nhau |
| (self) | Cho phép document cùng origin và các frame cùng origin theo quy tắc policy |
| ("https://meet.example.test") | Chỉ cho phép origin được nêu |
| (self "https://meet.example.test") | Cho phép origin hiện tại và origin đối tác |

Ví dụ chặn hoàn toàn:

    Permissions-Policy: camera=(), microphone=(), geolocation=()

Ví dụ chỉ cho phép trang hiện tại và một origin họp video:

    Permissions-Policy: camera=(self "https://meet.example.test"), microphone=(self "https://meet.example.test"), geolocation=()

### Ý nghĩa của self

Trong HTTP header, self là token biểu thị origin của document đang áp dụng policy. Nó không có nghĩa là mọi subdomain cùng domain registrable đều được phép.

Ví dụ:

    https://app.example.test
    https://admin.example.test
    https://meet.example.test

Ba origin trên khác nhau vì host khác nhau. Policy (self) ở app.example.test không tự cho phép admin.example.test hoặc meet.example.test.

### Ý nghĩa của wildcard và allowlist rỗng

Wildcard * cho phép mọi origin trong phạm vi directive:

    Permissions-Policy: geolocation=*

Đây thường là lựa chọn quá rộng đối với camera, microphone, geolocation hoặc các tính năng nhạy cảm. Chỉ dùng wildcard khi có yêu cầu rõ ràng và đã đánh giá mọi iframe trong phạm vi.

Allowlist rỗng chặn mọi origin:

    Permissions-Policy: microphone=()

Đây là lựa chọn rõ ràng khi ứng dụng không cần tính năng đó.

## 4. Default allowlist: không phải tính năng nào cũng có mặc định giống nhau

Mỗi directive có default allowlist riêng. Tùy feature, mặc định có thể là self, * hoặc none. Khi một feature không được khai báo trong header, browser áp dụng default allowlist của feature đó.

Vì vậy:

- Không suy luận rằng mọi API nhạy cảm mặc định chỉ dành cho same-origin.
- Không suy luận rằng mọi feature mặc định mở cho mọi origin.
- Tra cứu default allowlist của từng directive trong tài liệu browser/spec đang hỗ trợ.
- Với tính năng nhạy cảm, khai báo policy tường minh để ý định bảo mật dễ kiểm tra.

Một baseline có thể bắt đầu bằng việc chặn các tính năng ứng dụng không dùng:

    Permissions-Policy: camera=(), microphone=(), geolocation=(), display-capture=(), usb=()

Danh sách feature và mức hỗ trợ khác nhau giữa browser. Nếu browser không nhận diện một directive, directive đó có thể bị bỏ qua; do đó cần kiểm tra compatibility thay vì giả định header đã được thực thi đồng nhất.

## 5. Ủy quyền tính năng cho iframe

Giả sử host ở origin https://shop.example.test và nhúng bản đồ ở origin https://maps.example.test. Host muốn cho bản đồ dùng geolocation, nhưng không muốn các frame khác có quyền này.

### Bước 1 — Khai báo tập origin tối đa ở header

Response của host:

    Permissions-Policy: geolocation=(self "https://maps.example.test")

Header cho phép origin host và maps.example.test nằm trong tập origin có thể được cấp geolocation.

### Bước 2 — Cấp quyền cho iframe cụ thể

    <iframe
      src="https://maps.example.test/embed"
      title="Bản đồ"
      allow="geolocation">
    </iframe>

Khi một feature được liệt kê trong allow nhưng không ghi allowlist tường minh, giá trị mặc định của iframe là src. Điều đó có nghĩa feature được cấp cho document có cùng origin với URL src của iframe.

### Bước 3 — Kiểm tra permission của người dùng

Ngay cả khi Permissions Policy cho phép geolocation, browser vẫn có thể hỏi người dùng cấp quyền vị trí. Nếu người dùng từ chối, API vẫn không cung cấp vị trí.

    Feature được browser hỗ trợ?
              |
              v
    Secure context hợp lệ?
              |
              v
    Permissions Policy cho phép?
              |
              v
    Iframe được parent delegate?
              |
              v
    Người dùng/browser cho phép?
              |
              v
    API còn đáp ứng điều kiện riêng?
              |
              v
    Tính năng hoạt động

### Không thể mở lại feature đã bị parent chặn

Nếu parent trả:

    Permissions-Policy: geolocation=()

thì iframe không thể tự bật geolocation bằng:

    <iframe
      src="https://maps.example.test/embed"
      allow="geolocation">
    </iframe>

Policy bị chặn ở ancestor là giới hạn một chiều. Frame con và các descendant của nó không thể nới rộng quyền đã bị parent loại bỏ.

## 6. Cú pháp allow trên iframe khác cú pháp HTTP header

Đây là điểm dễ nhầm khi chuyển cấu hình từ header sang HTML.

HTTP header:

    Permissions-Policy: geolocation=(self "https://maps.example.test")

Iframe allow:

    <iframe
      src="https://maps.example.test/embed"
      allow="geolocation 'src'; fullscreen 'none'">
    </iframe>

Khác biệt cú pháp:

| Ý nghĩa | HTTP header | iframe allow |
| --- | --- | --- |
| Cho phép same-origin | self | 'self' |
| Cho phép mọi origin | * | * |
| Chặn mọi origin | () | 'none' |
| Cho phép origin của src iframe | Không có token src trong header | 'src' |
| Origin cụ thể | "https://maps.example.test" trong allowlist | https://maps.example.test, không đặt trong dấu nháy |

### Giá trị src

Trong iframe allow, src là keyword chỉ origin của URL trong thuộc tính src. Nếu iframe điều hướng sang origin khác, policy được gắn với src ban đầu không tự động áp dụng cho origin mới trừ khi origin đó cũng được cho phép trong allowlist.

Ví dụ:

    <iframe
      src="https://maps.example.test/embed"
      allow="geolocation">
    </iframe>

tương đương với:

    <iframe
      src="https://maps.example.test/embed"
      allow="geolocation 'src'">
    </iframe>

### Chặn tính năng ở một iframe

    <iframe
      src="https://comments.example.test"
      allow="camera 'none'; microphone 'none'; geolocation 'none'">
    </iframe>

Đây là giới hạn thêm cho iframe cụ thể. Nó không thay thế policy header ở cấp trang.

## 7. Policy kế thừa qua nhiều tầng iframe

Một trang có thể nhúng frame nhiều tầng:

    Top-level: https://app.example.test
           |
           v
    Frame A: https://portal.partner.test
           |
           v
    Frame B: https://video.partner.test
           |
           v
    Frame C: https://widget.vendor.test

Để Frame C dùng camera, quyền phải được phép xuyên suốt các lớp policy liên quan:

1. Header của top-level phải cho phép origin cần thiết nằm trong phạm vi.
2. Iframe A phải delegate camera cho origin của frame con.
3. Header của Frame A không được chặn camera đối với descendant.
4. Iframe B phải tiếp tục delegate camera cho Frame C nếu Frame C cần sử dụng.
5. Header của Frame B cũng không được chặn feature.
6. Browser permission và các điều kiện API vẫn phải cho phép.

Nếu một ancestor đặt allowlist rỗng cho camera, frame sâu hơn không thể mở lại.

### Ví dụ policy bị chặn ở giữa cây

Top-level:

    Permissions-Policy: camera=(self "https://portal.partner.test" "https://video.partner.test" "https://widget.vendor.test")

Frame A cho phép camera:

    <iframe
      src="https://portal.partner.test"
      allow="camera">
    </iframe>

Nhưng response của Frame A:

    Permissions-Policy: camera=()

Frame A đã chặn camera cho chính nó và các frame con. Frame B hoặc C không thể tự bật lại camera, dù top-level đã cho phép origin của chúng.

### Nguyên tắc thiết kế

- Xác định feature cần thiết ở từng iframe.
- Header top-level chỉ liệt kê những origin có thể được cấp quyền.
- Mỗi iframe chỉ nhận feature cần thiết qua allow.
- Nếu có nhiều tầng embed, xác minh delegation ở từng cạnh trong cây.
- Không cấp quyền rộng ở frame cha chỉ để một frame con có thể hoạt động.

## 8. Permissions Policy không phải permission prompt

Permissions Policy và quyền do người dùng cấp là hai lớp khác nhau:

| Lớp | Chủ thể quyết định | Ví dụ |
| --- | --- | --- |
| Permissions Policy | Website qua response header và iframe allow | Host không cho iframe dùng camera |
| User permission | Người dùng qua browser prompt/cài đặt | Người dùng từ chối camera |
| Secure context | Browser đánh giá môi trường | API chỉ hoạt động trên HTTPS hoặc localhost được coi là secure |
| API-specific requirement | Browser và API | Cần user gesture, thiết bị khả dụng hoặc điều kiện trạng thái |

Policy cho phép không có nghĩa browser sẽ bỏ qua prompt. Policy chặn thì user không thể dùng prompt để mở lại tính năng mà document đã bị cấm.

### Permissions API không thay Permissions Policy

JavaScript có thể hỏi trạng thái một số quyền qua navigator.permissions.query(). Ví dụ:

    const result = await navigator.permissions.query({
      name: "geolocation"
    });

    console.log(result.state);

Giá trị có thể là granted, denied hoặc prompt tùy quyền và browser. API này mô tả trạng thái permission mà browser cung cấp; nó không thay thế việc cấu hình Permissions Policy.

Không dùng một kết quả query duy nhất làm bằng chứng rằng header đã được áp dụng đúng. Hãy kiểm tra response header, iframe delegation và thử gọi API trong browser mục tiêu.

## 9. Phân biệt Permissions Policy với CSP, CORS và sandbox

| Cơ chế | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| Permissions Policy | Document/iframe được dùng API browser nào? | Chặn camera hoặc geolocation |
| Content Security Policy | Trang được tải tài nguyên và thực thi script theo quy tắc nào? | script-src, frame-src |
| CORS | JavaScript có được đọc response cross-origin không? | Access-Control-Allow-Origin |
| iframe sandbox | Frame bị giới hạn khả năng thực thi và tương tác nào? | Chặn script, form, popup theo token |
| Same-Origin Policy | Script được đọc DOM/dữ liệu origin nào? | Ngăn đọc DOM cross-origin tùy ý |

### Permissions Policy và CSP

CSP frame-src kiểm soát nguồn iframe mà trang được phép tải. Permissions Policy kiểm soát tính năng browser mà document hoặc iframe được phép dùng.

    Content-Security-Policy: default-src 'self'; frame-src https://maps.example.test
    Permissions-Policy: geolocation=(self "https://maps.example.test")

Hai header bổ sung cho nhau: CSP cho phép tải map frame; Permissions Policy cho phép origin map được sử dụng geolocation nếu iframe cũng được delegate.

### Permissions Policy và CORS

CORS không cấp quyền camera hoặc vị trí. Nó điều khiển việc đọc response cross-origin qua các API mạng. Một iframe có thể được delegate geolocation nhưng vẫn không được phép đọc response của API cross-origin nếu CORS không cho phép.

### Permissions Policy và iframe sandbox

Sandbox hạn chế một số hành vi của frame, còn Permissions Policy giới hạn các feature được dùng. Nếu iframe có cả sandbox và allow, browser phải thỏa cả hai nhóm quy tắc.

Không bỏ sandbox chỉ vì cần camera; hãy cấu hình token sandbox và delegation theo nhu cầu thực tế.

## 10. Chọn feature và allowlist theo nguyên tắc least privilege

| Feature | Rủi ro nếu cấp quá rộng | Baseline gợi ý |
| --- | --- | --- |
| camera | Thu hình ảnh/môi trường xung quanh | Chặn nếu không cần; chỉ cấp cho ứng dụng gọi video |
| microphone | Thu âm thanh | Chặn nếu không cần; chỉ cấp cho phòng họp |
| geolocation | Tiết lộ vị trí người dùng | Chỉ cấp cho bản đồ/dịch vụ có chức năng vị trí |
| display-capture | Chia sẻ nội dung màn hình | Chỉ cấp cho dịch vụ họp hoặc hỗ trợ có yêu cầu |
| fullscreen | Chiếm toàn màn hình và gây nhầm lẫn giao diện | Chỉ cấp cho trình phát/game cần thiết |
| usb | Truy cập thiết bị USB được hỗ trợ | Chặn nếu không có nghiệp vụ phần cứng |
| autoplay | Tự phát media gây ảnh hưởng trải nghiệm | Chỉ cấp nếu sản phẩm cần và browser hỗ trợ |

Tên directive và hỗ trợ thay đổi theo browser. Hãy đối chiếu danh sách feature trong MDN và compatibility table trước khi dùng trong production.

### Baseline cho ứng dụng không cần tính năng nhạy cảm

    Permissions-Policy: camera=(), microphone=(), geolocation=(), display-capture=(), usb=()

### Baseline cho ứng dụng có video call đối tác

    Permissions-Policy: camera=(self "https://meet.example.test"), microphone=(self "https://meet.example.test"), geolocation=(), display-capture=()

Iframe:

    <iframe
      src="https://meet.example.test/room"
      title="Video meeting"
      allow="camera; microphone">
    </iframe>

Chỉ cấp camera/microphone cho origin họp đã xác minh. Không cấp geolocation nếu chức năng họp không cần vị trí.

## 11. Triển khai Permissions-Policy trên server

### Nginx

Ví dụ chặn các feature không dùng:

    server {
        listen 443 ssl;
        server_name app.example.test;

        add_header Permissions-Policy "camera=(), microphone=(), geolocation=(), display-capture=(), usb=()" always;

        location / {
            proxy_pass http://application;
        }
    }

Ví dụ cho phép một dịch vụ họp:

    add_header Permissions-Policy "camera=(self \"https://meet.example.test\"), microphone=(self \"https://meet.example.test\"), geolocation=()" always;

Kiểm tra quy tắc kế thừa add_header giữa server và location. Tránh để CDN, reverse proxy và ứng dụng cùng phát policy mâu thuẫn.

### Node.js / Express

    import express from "express";

    const app = express();

    app.use((req, res, next) => {
      res.setHeader(
        "Permissions-Policy",
        [
          "camera=()",
          "microphone=()",
          "geolocation=()",
          "display-capture=()",
          "usb=()"
        ].join(", ")
      );
      next();
    });

Nếu một route cần camera/microphone, hãy phát policy riêng cho response của route đó và kiểm tra mọi iframe được nhúng. Không bật feature toàn cục chỉ vì một trang duy nhất cần dùng.

### Java / Spring Security

Có thể thêm header qua StaticHeadersWriter:

    import org.springframework.context.annotation.Bean;
    import org.springframework.security.config.annotation.web.builders.HttpSecurity;
    import org.springframework.security.web.SecurityFilterChain;
    import org.springframework.security.web.header.writers.StaticHeadersWriter;

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.headers(headers -> headers.addHeaderWriter(
            new StaticHeadersWriter(
                "Permissions-Policy",
                "camera=(), microphone=(), geolocation=(), display-capture=(), usb=()"
            )
        ));

        return http.build();
    }

Đây là ví dụ cấu hình header tĩnh. API Spring Security có thể khác theo phiên bản; hãy xác minh dependency và response thực tế của ứng dụng.

## 12. Kiểm thử bằng Chrome DevTools

Thực hiện trên HTTPS staging hoặc localhost. Camera, microphone và geolocation thường yêu cầu secure context; không kết luận policy sai chỉ vì trang thử nghiệm chạy trên HTTP không bảo mật.

### Bước 1 — Xác minh response header

1. Mở trang trong browser.
2. DevTools → Network.
3. Chọn document chính.
4. Xem Response Headers.
5. Xác nhận Permissions-Policy đúng với cấu hình server.
6. Kiểm tra response của iframe nếu iframe có policy riêng.

### Bước 2 — Thử chặn camera và microphone

Phát header trong staging:

    Permissions-Policy: camera=(), microphone=()

Thử gọi API:

    try {
      await navigator.mediaDevices.getUserMedia({
        video: true,
        audio: true
      });
    } catch (error) {
      console.log(error.name, error.message);
    }

Quan sát Console và lỗi API. Khi policy chặn, browser không nên cho document sử dụng feature dù người dùng đã từng cấp quyền ở cài đặt.

### Bước 3 — Thử geolocation

Header:

    Permissions-Policy: geolocation=()

Thử:

    navigator.geolocation.getCurrentPosition(
      (position) => console.log(position.coords.latitude),
      (error) => console.log(error.code, error.message)
    );

Không ghi tọa độ thật của người dùng vào log hoặc gửi lên hệ thống test.

### Bước 4 — Thử iframe delegation

Parent response:

    Permissions-Policy: geolocation=(self "https://maps.example.test")

HTML:

    <iframe
      src="https://maps.example.test/embed"
      title="Map"
      allow="geolocation">
    </iframe>

Kiểm tra:

1. Frame đúng origin được khai báo trong header.
2. iframe có allow phù hợp.
3. Browser chạy trên secure context.
4. Người dùng đã cấp quyền vị trí nếu browser yêu cầu.
5. Thử bỏ allow hoặc bỏ origin khỏi header và xác nhận tính năng bị chặn.

### Bước 5 — Kiểm tra nested iframe

Tạo parent → child → grandchild. Delegate feature ở từng iframe cần thiết. Sau đó đặt policy chặn ở child và xác nhận grandchild không thể tự bật lại.

### Ma trận kiểm thử

| Ca kiểm thử | Thiết lập | Kết quả mong đợi |
| --- | --- | --- |
| Feature bị chặn ở header | camera=() | Document và frame con không dùng camera |
| Feature same-origin | geolocation=(self) | Document cùng origin được phép theo policy |
| Cross-origin không được liệt kê | geolocation=(self) | Frame khác origin không được cấp |
| Cross-origin được liệt kê và delegate | Header có origin + iframe allow | Frame có thể dùng API nếu các điều kiện khác cho phép |
| Header cho phép nhưng iframe thiếu allow | Không delegate feature cho frame | Frame không nhận quyền ngoài default policy áp dụng |
| Parent chặn, child cho phép | Parent geolocation=() | Child vẫn bị chặn |
| User từ chối permission | Policy cho phép | API vẫn không được cấp dữ liệu |
| HTTP không secure | Feature yêu cầu secure context | API có thể không khả dụng dù policy cho phép |
| Browser không hỗ trợ directive | Header có feature không được hỗ trợ | Không được giả định policy đã được enforce |

## 13. Reporting và quan sát vi phạm

Một số browser hỗ trợ báo cáo vi phạm Permissions Policy qua Reporting API hoặc quan sát trong trang. Khả năng hỗ trợ và cú pháp reporting có thể khác nhau theo browser và phiên bản.

Nếu triển khai reporting:

- Định nghĩa Reporting-Endpoints theo cơ chế browser hỗ trợ.
- Kiểm tra directive report-to trong tài liệu hiện hành.
- Không gửi dữ liệu vị trí, camera, microphone hoặc payload nhạy cảm vào report.
- Coi report là tín hiệu chẩn đoán, không phải bằng chứng đầy đủ rằng mọi browser đều enforce.

DevTools Console và kiểm thử API thực tế vẫn cần thiết. Không dựa duy nhất vào việc không thấy report để kết luận policy không có vi phạm.

## 14. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nghĩ header cho phép đồng nghĩa user đã cấp quyền | API vẫn có thể hiện permission prompt hoặc bị từ chối | Kiểm tra cả policy và user permission |
| Dùng wildcard cho camera/microphone | Mọi iframe có thể được cấp feature | Allowlist origin cụ thể |
| Nghĩ iframe allow ghi đè header parent | Frame con không thể mở lại feature đã bị ancestor chặn | Kiểm tra policy ở mọi ancestor |
| Sao chép cú pháp header vào allow | Sai cú pháp do hai cơ chế khác nhau | Dùng syntax riêng của iframe allow |
| Nghĩ self bao gồm mọi subdomain | Cho phép nhầm origin hoặc hiểu sai phạm vi | So khớp exact origin |
| Không khai báo feature nhạy cảm | Default allowlist khác nhau theo directive | Đặt policy tường minh cho feature cần hạn chế |
| Chỉ kiểm tra top-level document | Bỏ sót quyền được delegate cho iframe | Kiểm tra cả cây frame |
| Nghĩ Permissions API thay header | Không kiểm soát được quyền của frame | Dùng Permissions-Policy và test thực tế |
| Nhầm CSP frame-src với Permissions Policy | Tải được iframe nhưng API vẫn bị chặn hoặc ngược lại | Dùng đúng cơ chế cho đúng câu hỏi |
| Tin browser nào cũng hỗ trợ mọi directive | Policy có thể bị bỏ qua ở browser cũ | Kiểm tra compatibility và fallback |
| Bật feature toàn cục vì một trang cần | Mở quyền không cần thiết cho các trang khác | Phát header theo route và delegate đúng iframe |

## 15. Câu hỏi củng cố

**Câu 1.** Permissions Policy kiểm soát điều gì?

**Giải đáp:** Nó giới hạn document và các iframe được phép sử dụng những tính năng browser cụ thể, chẳng hạn camera, microphone hoặc geolocation.

**Câu 2.** Header cho phép camera có nghĩa người dùng không cần cấp quyền nữa phải không?

**Giải đáp:** Không. Policy chỉ cho phép website sử dụng feature; browser vẫn có thể yêu cầu người dùng cấp quyền và áp dụng secure context cùng các điều kiện API.

**Câu 3.** Header camera=() có thể bị iframe allow="camera" mở lại không?

**Giải đáp:** Không. Policy của ancestor đã chặn feature; iframe con không thể nới rộng quyền đó.

**Câu 4.** HTTP header và iframe allow dùng cùng cú pháp không?

**Giải đáp:** Không. Header dùng allowlist trong ngoặc, ví dụ geolocation=(self "https://maps.example.test"); iframe allow dùng cú pháp riêng, ví dụ allow="geolocation 'src'".

**Câu 5.** Vì sao cần kiểm tra nested iframe?

**Giải đáp:** Mỗi ancestor có thể giới hạn hoặc delegate feature. Một frame bị chặn ở giữa cây sẽ không thể tự bật lại cho các descendant.

**Câu 6.** Permissions Policy có thay CSP hoặc CORS không?

**Giải đáp:** Không. Permissions Policy kiểm soát browser feature; CSP kiểm soát tài nguyên và thực thi; CORS kiểm soát quyền đọc response cross-origin.

**Câu 7.** Một iframe đã được delegate geolocation có luôn nhận được vị trí không?

**Giải đáp:** Không. Browser vẫn có thể yêu cầu user permission, secure context và điều kiện API khác.

## 16. Tổng kết

**Permissions Policy** cho phép website giới hạn các tính năng mạnh của browser ở cấp document và delegate có chọn lọc cho iframe. Dùng HTTP response header để đặt ranh giới tối đa theo origin; dùng thuộc tính allow trên từng iframe để cấp đúng feature cần thiết.

Policy được kế thừa qua cây browsing context và frame con không thể bật lại feature mà ancestor đã chặn. Cú pháp HTTP header khác cú pháp iframe allow, default allowlist thay đổi theo feature và browser, vì vậy cần khai báo tường minh cho quyền nhạy cảm và kiểm thử trên browser mục tiêu.

Permissions Policy không thay quyền do người dùng cấp, secure context, CSP, CORS hoặc iframe sandbox. Hãy áp dụng least privilege, giảm wildcard, kiểm tra mọi frame lồng nhau và xác minh hành vi API thực tế trước khi phát hành.

## Tài liệu tham khảo

1. [W3C — Permissions Policy](https://www.w3.org/TR/permissions-policy/): đặc tả policy, HTTP header, iframe allow và kế thừa.
2. [MDN — Permissions Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Permissions_Policy): khái niệm, cú pháp allowlist, default allowlist và ví dụ iframe.
3. [MDN — Permissions-Policy header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Permissions-Policy): cấu hình response header và ví dụ chặn feature.
4. [MDN — HTMLIFrameElement.allow](https://developer.mozilla.org/en-US/docs/Web/API/HTMLIFrameElement/allow): thuộc tính allow và cách nó thu hẹp policy header.
5. [Chrome for Developers — Control browser features with Permissions Policy](https://developer.chrome.com/docs/privacy-security/permissions-policy): ví dụ delegation và kiểm soát feature trong iframe.
