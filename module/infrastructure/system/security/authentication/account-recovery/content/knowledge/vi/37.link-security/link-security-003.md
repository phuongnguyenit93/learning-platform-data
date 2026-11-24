# Link leakage in history: Rò rỉ liên kết khôi phục qua lịch sử trình duyệt

Một liên kết khôi phục tài khoản thường mang token cho phép tiếp tục một thao tác nhạy cảm. Khi token nằm trong URL, dấu vết điều hướng có thể trở thành nơi lưu giữ bí mật. Người khác nhìn thấy lịch sử trên máy dùng chung hoặc lấy được dữ liệu trình duyệt có thể tìm thấy liên kết đó trước khi token hết hiệu lực.

Bài học này giải thích rủi ro từ lịch sử trình duyệt trong luồng khôi phục mật khẩu, MFA, passkey và thiết bị xác thực. Mục tiêu thiết kế là giảm thời gian token hiện diện trong URL, tránh tạo thêm bản sao và bảo đảm một liên kết đã sử dụng không còn cấp quyền.

## 1. Vì sao một dòng lịch sử có thể trở thành thông tin xác thực?

Xét URL minh họa:

~~~text
https://accounts.example.com/recovery/start?token=TOKEN_MINH_HOA
~~~

Nếu máy chủ chỉ cần token này để chấp nhận bước khôi phục, người giữ URL có một dạng quyền theo cơ chế bearer: quyền đến từ việc sở hữu bí mật, không nhất thiết từ việc biết mật khẩu cũ. Chuỗi trong ví dụ là ký hiệu minh họa, không phải token có thể sử dụng.

Một tình huống thường gặp:

1. Người dùng mở email khôi phục trên máy tính dùng chung.
2. Trình duyệt điều hướng tới trang có token trong URL.
3. Người dùng chưa hoàn tất thao tác, đóng tab rồi rời máy.
4. Người tiếp theo mở lại tab hoặc tìm trang khôi phục trong lịch sử.
5. Nếu token còn hiệu lực và chính sách chỉ yêu cầu token, người đó có thể tiếp tục khôi phục.

Tác động phụ thuộc vào quyền mà token cấp. Link đặt mật khẩu mới, link thay yếu tố MFA và link cho phép đăng ký passkey mới không nên được xem là tương đương. Một đường dẫn bị lộ chỉ dẫn đến chiếm tài khoản khi những điều kiện còn lại của luồng cho phép; tuy vậy, lịch sử trình duyệt không phải nơi thích hợp để lưu bất kỳ bí mật nào trong các luồng này.

HTTPS bảo vệ đường truyền giữa các đầu cuối hợp lệ. Nó không làm URL biến mất khỏi trình duyệt sau khi người dùng đã mở trang.

## 2. Phân biệt các loại dấu vết

Từ “history” có thể chỉ nhiều bề mặt khác nhau. Cần phân biệt chúng để không chọn nhầm biện pháp xử lý.

| Bề mặt | Dữ liệu có thể xuất hiện | Điều cần nhớ khi thiết kế |
| --- | --- | --- |
| Session history của tab | Các entry phục vụ Back và Forward | Việc thay entry hiện tại không sửa tất cả entry khác |
| Lịch sử duyệt web của hồ sơ | URL đã truy cập, thời điểm, tiêu đề tùy trình duyệt | Không coi API điều hướng của trang là công cụ xóa toàn bộ lịch sử |
| Khôi phục tab và phiên làm việc | Trạng thái để mở lại trang sau khi đóng hoặc khởi động lại | Hành vi lưu và phục hồi phụ thuộc trình duyệt, cấu hình |
| Đồng bộ trình duyệt | Một phần dữ liệu duyệt web được đồng bộ khi tính năng đó hoạt động | Không giả định thay URL sẽ thu hồi mọi bản sao đã đồng bộ |
| Bookmark, clipboard, ảnh chụp | Bản sao do người dùng hoặc phần mềm tạo ra | Ứng dụng không kiểm soát được toàn bộ vòng đời bản sao |

Bảng này là mô hình rủi ro cần xét, không khẳng định mọi trình duyệt luôn lưu đủ các loại dữ liệu trên.

Ngoài lịch sử còn có HTTP cache, access log và dữ liệu Referer. Chúng là những kênh lưu hoặc truyền dữ liệu riêng. Xóa query ở thanh địa chỉ không sửa access log đã ghi; đặt chính sách Referer không xóa một entry trong tab.

### Query, path và fragment

Các dạng dưới đây đều đặt bí mật vào URL mà người dùng có thể nhìn thấy hoặc sao chép:

~~~text
/recovery/start?token=TOKEN_MINH_HOA
/recovery/start/TOKEN_MINH_HOA
/recovery/start#token=TOKEN_MINH_HOA
~~~

Đưa token từ query sang path không loại bỏ rủi ro lịch sử. Fragment thường được xử lý phía trình duyệt và không đi trong HTTP request target gửi tới máy chủ, nhưng vẫn thuộc URL phía client và có thể bị JavaScript đọc. Vì thế, fragment không tự giải quyết bài toán lưu bí mật trong lịch sử. Xem [MDN: URI fragment](https://developer.mozilla.org/en-US/docs/Web/URI/Reference/Fragment).

Đánh giá này cũng áp dụng cho URL đã mã hóa hoặc được ký. Một chuỗi khó đọc vẫn là bí mật có thể tái sử dụng nếu bên nhận chỉ cần gửi nguyên chuỗi đó.

## 3. Các biện pháp dễ tạo cảm giác an toàn sai

### Chỉ thêm Cache-Control

~~~http
Cache-Control: no-store
~~~

Header này yêu cầu cache không lưu phản hồi. Nó hữu ích cho trang khôi phục nhưng không phải lệnh xóa lịch sử điều hướng. `no-cache` có ý nghĩa khác: phản hồi có thể được lưu nhưng phải xác thực lại trước khi tái sử dụng theo quy tắc cache. Không dùng việc cấu hình cache làm bằng chứng rằng URL không còn trong lịch sử. Xem [MDN: Cache-Control](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control).

### Tạo một entry sạch bằng pushState

~~~javascript
history.pushState(null, "", "/recovery/continue");
~~~

Thao tác thêm entry mới có thể để entry chứa token ở phía trước trong chuỗi Back. Người dùng nhìn thấy URL sạch ở hiện tại chưa có nghĩa entry trước đã được thay thế.

Theo mô hình History của HTML, `pushState` và `replaceState` có mục đích khác nhau: một bên thêm entry, bên còn lại thay entry hiện tại. Đây là khác biệt quyết định khi xử lý URL chứa token. Xem [WHATWG: History interface](https://html.spec.whatwg.org/multipage/nav-history-apis.html#the-history-interface).

### Chuyển trang rồi coi token đã biến mất

Một redirect có thể đưa người dùng tới địa chỉ sạch. Tuy nhiên, không nên từ đó suy ra mọi dấu vết của URL đầu vào đã được xóa trên mọi trình duyệt hoặc mọi nơi lưu dữ liệu. URL ban đầu đã được sử dụng để điều hướng trước khi máy chủ phản hồi.

Tương tự, `location.replace()` có thể hữu ích khi cần điều hướng thay thế entry hiện tại, nhưng không phải cơ chế thu hồi token hay xóa dữ liệu bên ngoài entry chịu tác động.

### Yêu cầu người dùng dùng chế độ riêng tư

Đây có thể là hướng dẫn sử dụng bổ sung cho thiết bị dùng chung, nhưng hệ thống không nên phụ thuộc vào nó để bảo vệ token. Người dùng có thể mở nhầm hồ sơ, sao chép URL hoặc để phiên khôi phục đang hoạt động trên máy. Mức bảo vệ cốt lõi vẫn phải do ứng dụng và máy chủ thực hiện.

## 4. Thiết kế luồng tách bí mật khỏi URL sớm

Một phương án kiến trúc là dùng trang tiếp nhận tối giản để lấy token khỏi URL, rồi chuyển sang một phiên khôi phục có phạm vi hẹp. Đây là đề xuất thiết kế cho bài học, cần được điều chỉnh theo yêu cầu xác minh của từng hệ thống.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Trình duyệt
    participant S as Máy chủ khôi phục

    U->>B: Mở liên kết nhận qua kênh khôi phục
    B->>S: GET trang tiếp nhận
    S-->>B: HTML tối giản và chính sách bảo vệ
    B->>B: Giữ token tạm trong bộ nhớ, thay URL hiện tại
    U->>B: Chọn tiếp tục
    B->>S: POST token và bằng chứng chống CSRF
    S->>S: Kiểm tra token, tiêu thụ nguyên tử, tạo phiên giới hạn
    S-->>B: Cookie phiên khôi phục và kết quả không chứa token
    B->>S: Tiếp tục tại đường dẫn sạch
~~~

### Bước 1: Tiếp nhận trên trang tối giản

Trang này chỉ có thành phần cần thiết cho khôi phục. Tránh tải analytics, session replay, widget hỗ trợ hoặc script không cần thiết trước khi xử lý URL. Nếu script khác đã đọc URL, việc làm sạch sau đó không thu hồi được bản sao nó đã tạo.

Không đưa token vào tiêu đề trang, thông báo lỗi hoặc thuộc tính DOM để tiện gỡ lỗi. Tránh để router thông thường tự động ghi nhận toàn bộ URL đầu vào trước mã tiếp nhận.

Việc người dùng mở trang bằng GET không nên tự đặt mật khẩu, xóa MFA hay đăng ký passkey. Trong phương án ở đây, GET cũng chưa tiêu thụ token; bước POST có chủ đích mới trao đổi nó. Điều này giúp tránh việc chỉ truy cập link đã làm hỏng hành trình, nhưng không phải bằng chứng chắc chắn phân biệt con người với mọi loại trình quét link.

### Bước 2: Thay entry hiện tại

Ứng dụng đọc token, giữ tạm trong bộ nhớ rồi thay URL bằng một đường dẫn cùng origin đã xác định sẵn:

~~~javascript
history.replaceState(null, "", "/recovery/continue");
~~~

Không lưu token vào đối số `state`. Đối số đó cũng là dữ liệu gắn với entry lịch sử.

`replaceState` thay URL và state của entry hiện tại, không tải tài liệu mới. URL thay thế phải cùng origin. Vì vậy, sau lệnh trên trình duyệt vẫn đang hiển thị tài liệu tiếp nhận; máy chủ cũng cần xử lý được `/recovery/continue` khi người dùng thực sự tải lại địa chỉ ấy. Xem [MDN: History.replaceState](https://developer.mozilla.org/en-US/docs/Web/API/History/replaceState).

### Bước 3: Đổi token lấy phiên khôi phục giới hạn

Máy chủ nhận token qua POST body, xác thực và quyết định có tạo phiên hay không. Đừng đưa token trở lại query của endpoint tiếp theo, response JSON hoặc header Location.

Phiên mới chỉ phục vụ mục đích được cho phép, chẳng hạn tiếp tục đặt lại mật khẩu. Nó không phải phiên đăng nhập toàn quyền. Với khôi phục MFA hoặc đăng ký passkey thay thế, chính sách có thể yêu cầu thêm bằng chứng độc lập trước khi cho phép thay đổi yếu tố xác thực.

Chuyển token vào POST body giúp tách nó khỏi URL điều hướng, nhưng body vẫn có thể bị ghi bởi công cụ quan sát nếu cấu hình sai. Đây là thay đổi vị trí truyền dữ liệu, không phải quyền ghi lại bí mật trong log.

### Bước 4: Kết thúc quyền khôi phục

Khi thao tác thành công, phiên khôi phục phải hết quyền sử dụng. Link đã trao đổi cũng không được tạo thêm phiên mới. Nếu chỉ xóa URL mà máy chủ vẫn chấp nhận token cũ, người giữ bản sao vẫn có thể cạnh tranh với người dùng.

## 5. Ví dụ tiếp nhận token phía trình duyệt

Đoạn dưới minh họa phần xử lý URL và POST trao đổi token. Nó giả định HTML có các phần tử `continue-recovery`, `recovery-message` và meta `csrf-token` do máy chủ phát hành.

~~~javascript
(() => {
  const button = document.getElementById("continue-recovery");
  const message = document.getElementById("recovery-message");
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content;
  button.disabled = true;

  let recoveryToken = null;

  try {
    const incoming = new URL(window.location.href);
    const candidates = incoming.searchParams.getAll("token");
    recoveryToken =
      candidates.length === 1 && candidates[0].length > 0
        ? candidates[0]
        : null;

    // Không chép token vào history.state; bỏ cả query và fragment.
    window.history.replaceState(null, "", "/recovery/continue");
  } catch {
    recoveryToken = null;
    message.textContent = "Không thể tiếp tục. Hãy yêu cầu liên kết mới.";
    return;
  }

  if (!recoveryToken || !csrf) {
    recoveryToken = null;
    message.textContent = "Không thể tiếp tục. Hãy mở liên kết hợp lệ.";
    return;
  }

  button.disabled = false;

  button.addEventListener("click", async () => {
    button.disabled = true;

    try {
      const response = await fetch("/recovery/exchange", {
        method: "POST",
        mode: "same-origin",
        credentials: "same-origin",
        cache: "no-store",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrf
        },
        body: JSON.stringify({ token: recoveryToken })
      });

      if (!response.ok) {
        throw new Error("RECOVERY_EXCHANGE_FAILED");
      }

      // Máy chủ đã cấp cookie phiên khôi phục giới hạn.
      recoveryToken = null;
      window.location.replace("/recovery/continue");
    } catch {
      recoveryToken = null;
      message.textContent =
        "Không thể tiếp tục. Hãy yêu cầu liên kết mới nếu cần.";
    }
  }, { once: true });
})();
~~~

Những quyết định đáng chú ý trong ví dụ:

- Dùng đường dẫn sạch cố định cùng origin, không lấy đích điều hướng tùy ý từ tham số của link.
- Từ chối trường hợp tham số token bị lặp, tránh cách diễn giải không thống nhất giữa các thành phần.
- Không dùng localStorage, sessionStorage hoặc `history.state` để bảo đảm token còn sau khi tải lại.
- Chỉ bắt đầu POST khi người dùng chọn tiếp tục; không coi thao tác click là biện pháp chống bot đầy đủ.
- Không ghi URL, token, request body hay nội dung lỗi máy chủ vào console.
- Khi kết quả trao đổi không chắc chắn, không tự đưa token trở lại URL để thử lại.

Việc gán `null` chỉ bỏ tham chiếu của biến trong ứng dụng; JavaScript không cung cấp ở đây một cam kết xóa sạch mọi bản sao bí mật khỏi bộ nhớ.

Ví dụ chưa triển khai máy chủ, hệ thống CSRF, cookie hay chính sách xác minh danh tính. Máy chủ vẫn phải xác thực dữ liệu đầu vào; việc kiểm tra phía client không tạo ra quyền khôi phục.

### Tải lại trang giữa chừng

Có hai trường hợp cần xử lý rõ:

| Thời điểm tải lại | Dữ liệu máy chủ có | Hành vi nên thiết kế |
| --- | --- | --- |
| Trước khi trao đổi token thành công | Có thể chưa có phiên khôi phục | Hiển thị hướng dẫn mở lại email hoặc yêu cầu link mới; không phục hồi token từ web storage |
| Sau khi phiên giới hạn đã được cấp | Có cookie phiên khôi phục hợp lệ | Tiếp tục bằng phiên sau khi máy chủ kiểm tra quyền và thời hạn |
| Sau khi phiên đã kết thúc | Phiên không còn quyền | Không cho form cũ tiếp tục thực hiện thao tác nhạy cảm |

Nếu mất mạng sau khi máy chủ đã trao đổi token nhưng trước khi client nhận phản hồi, kết quả có thể không rõ đối với client. Có thể đưa người dùng về đường dẫn sạch để kiểm tra phiên; nếu không có phiên dùng được, hướng dẫn bắt đầu lại. Không tự cho token đã dùng hoạt động trở lại chỉ để khắc phục trải nghiệm này.

## 6. Phần bảo vệ bắt buộc nằm ở máy chủ

### Tiêu thụ token phải nguyên tử

Đừng tách “kiểm tra chưa dùng” và “đánh dấu đã dùng” thành hai thao tác độc lập không có kiểm soát đồng thời. Hai trình duyệt có cùng URL có thể cùng vượt qua bước kiểm tra.

Một giao dịch minh họa:

~~~text
BEGIN
  Tìm bản ghi bằng giá trị băm của token và khóa bản ghi phù hợp.
  Kiểm tra đúng mục đích, đúng tài khoản, chưa hết hạn, chưa sử dụng.
  Kiểm tra các điều kiện xác minh bổ sung theo chính sách.
  Đánh dấu token đã trao đổi.
  Tạo phiên khôi phục có phạm vi và thời hạn giới hạn.
COMMIT
Chỉ gửi cookie phiên khi giao dịch đã thành công.
~~~

Có thể dùng cập nhật có điều kiện thay cho khóa bản ghi nếu cơ sở dữ liệu hỗ trợ và kiểm tra được số bản ghi thực sự thay đổi. Điều cần giữ là chỉ một lần trao đổi thành công cho cùng quyền một lần.

Token cần được tạo bằng nguồn ngẫu nhiên mật mã, đủ khó đoán, lưu an toàn, giới hạn thời gian và vô hiệu sau sử dụng. OWASP nêu các nguyên tắc này cho luồng quên mật khẩu; chúng giúp giảm tác hại nếu một bản sao link bị lộ. Xem [OWASP: Forgot Password](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).

### Phiên sạch URL vẫn là một bí mật

Ví dụ cookie cho một kiến trúc HTTPS:

~~~http
Set-Cookie: __Host-recovery=OPAQUE_SESSION_ID; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Tên có tiền tố `__Host-` đòi hỏi các điều kiện tương ứng của trình duyệt, gồm Secure, Path=/ và không có Domain. Xem [MDN: Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie#cookie_prefixes). Path=/ không giới hạn quyền nghiệp vụ: máy chủ phải bảo đảm cookie này chỉ được chấp nhận cho chức năng khôi phục được cấp.

Chọn thời hạn phiên theo rủi ro, thực hiện chống CSRF và kiểm tra origin phù hợp cho các thao tác thay đổi trạng thái. Thuộc tính SameSite là một lớp hỗ trợ, không thay thế toàn bộ thiết kế chống CSRF.

Một người dùng khác ngồi vào đúng hồ sơ trình duyệt có phiên khôi phục còn hiệu lực có thể tiếp tục thao tác dù lịch sử đã sạch token. Vì vậy, bài toán có hai phần: không lưu bí mật vào URL và kiểm soát quyền còn tồn tại trong phiên.

### Khôi phục có mức bảo đảm khác nhau

Ví dụ, hệ thống có thể cho phép link email tiếp tục đặt mật khẩu nhưng yêu cầu thêm mã dự phòng hoặc quy trình xác minh riêng khi người dùng muốn thay MFA. Không tự cho một link đặt lại mật khẩu khả năng xóa mọi yếu tố xác thực.

Các ví dụ này là lựa chọn chính sách cần được thiết kế theo tài khoản và hậu quả của việc mất quyền kiểm soát; chúng không phải bảo đảm rằng email luôn đủ mạnh cho khôi phục.

## 7. Giới hạn của việc làm sạch lịch sử

`replaceState` có phạm vi tác động là entry hiện tại. Thiết kế phải giả định có thể tồn tại bản sao trước thời điểm ứng dụng xử lý URL.

Các giới hạn cần tính đến:

- URL có thể đã được người dùng sao chép hoặc chụp ảnh trước khi mã chạy.
- Extension có quyền phù hợp hoặc thiết bị đã bị xâm nhập có thể quan sát dữ liệu ngoài phạm vi bảo vệ của trang.
- Trình duyệt hoặc dịch vụ đồng bộ có thể có hành vi lưu dữ liệu riêng; trang không thể hứa thu hồi tất cả.
- Một entry khác do ứng dụng tạo trước đó có thể còn chứa token.
- Trang được phục hồi từ trạng thái cũ có thể hiển thị giao diện đã lỗi thời; máy chủ vẫn phải từ chối quyền hết hạn hoặc đã tiêu thụ.

Do đó, tiêu chí an toàn không phải “không ai có thể tìm thấy bất kỳ dấu vết nào”. Tiêu chí thực dụng là ứng dụng chủ động hạn chế tạo dấu vết, rút ngắn thời gian lộ và không cho dấu vết cũ khôi phục quyền đã chấm dứt.

Nếu nghi một link còn hiệu lực đã bị lộ, xóa lịch sử phía người dùng không đủ. Hệ thống cần vô hiệu quyền khôi phục liên quan và xử lý phiên phát sinh theo bằng chứng, đồng thời tránh để báo cáo sự cố chứa lại token.

## 8. Những đánh đổi cần giải thích cho người dùng

Làm sạch URL sớm có thể khiến người dùng không tiếp tục được sau khi tải lại trước khi tạo phiên. Thông báo nên nói rõ cách trở lại hành trình, chẳng hạn mở lại email hoặc yêu cầu liên kết mới. Không nhúng lại bí mật vào URL để giữ tiện ích tải lại.

Với thiết bị dùng chung, giao diện nên nhắc người dùng hoàn tất hoặc thoát luồng khôi phục trước khi rời máy. Nút thoát cần chấm dứt phiên ở máy chủ, không chỉ chuyển sang một trang khác.

Nếu hệ thống cần tránh đưa bí mật vào URL ngay từ đầu, có thể cân nhắc link chỉ mở trang nhập mã và gửi mã qua kênh phù hợp. Phương án này thay đổi trải nghiệm và mô hình chống đoán mã; mã vẫn là bí mật, vẫn cần thời hạn, giới hạn lần thử và ràng buộc đúng giao dịch.

Kết quả mong muốn của thiết kế là: người dùng đi qua các trang khôi phục bằng địa chỉ sạch; token chỉ phục vụ bước trao đổi có kiểm soát; và lịch sử cũ không thể cấp lại quyền sau khi luồng đã kết thúc.

