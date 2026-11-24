# Recovery page script policy: Chính sách script cho trang khôi phục tài khoản

Trang khôi phục tài khoản là nơi người dùng có thể nhập mật khẩu mới, mã dự phòng hoặc bằng chứng để thay MFA và đăng ký lại passkey. JavaScript chạy trong trang có thể đọc nhiều dữ liệu mà giao diện đang xử lý. Vì vậy, quyết định cho một script xuất hiện trên trang này cũng là quyết định giao cho mã đó một phần quyền tiếp cận quá trình khôi phục.

Chính sách script cần trả lời ba câu hỏi: mã nào thật sự cần chạy, bằng cách nào trình duyệt nhận diện mã được phép, và ứng dụng vẫn phải bảo vệ điều gì khi mã đã được cho phép chạy. Content Security Policy (CSP) hỗ trợ câu hỏi thứ hai; một kiến trúc ít script giúp giải quyết câu hỏi thứ nhất.

## 1. Rủi ro đặc thù của trang khôi phục

Hãy xét một trang đặt lại mật khẩu đang tải bộ giao diện chung của website. Bộ giao diện này kéo theo tag manager, công cụ ghi lại phiên và widget hỗ trợ. Người dùng nhập mật khẩu mới vào form trước khi gửi.

Nếu một script bên thứ ba bị thay đổi ngoài ý muốn hoặc cấu hình thu thập dữ liệu quá rộng, mã đó có thể quan sát trường nhập. Dữ liệu chưa cần rời trình duyệt qua form chính thức vẫn có thể bị một script đọc.

Các tài sản cần bảo vệ bao gồm:

| Dữ liệu hoặc khả năng | Vì sao nhạy cảm |
| --- | --- |
| Token khôi phục đang được xử lý | Có thể cho phép tiếp tục một giao dịch khôi phục |
| Mật khẩu mới và trường xác nhận | Là bí mật xác thực người dùng sắp sử dụng |
| Mã dự phòng, mã xác minh | Có thể là bằng chứng dùng một lần để thay yếu tố xác thực |
| Kết quả kiểm tra quyền khôi phục | Có thể tiết lộ trạng thái tài khoản hoặc quá trình xác minh |
| Form và đích gửi dữ liệu | Script có thể sửa giao diện để hướng người dùng sang hành động khác |
| Phiên khôi phục còn hiệu lực | Mã chạy trong trang có thể gửi yêu cầu sử dụng phiên trong phạm vi được phép |

Cookie HttpOnly hạn chế việc JavaScript đọc trực tiếp giá trị cookie, nhưng không ngăn toàn bộ hành động của script độc hại. Mã chạy trong cùng trang vẫn có thể đọc trường nhập hoặc gửi yêu cầu mà trình duyệt đính kèm cookie.

Vì thế, không nên xem trang khôi phục là một trang nội dung thông thường chỉ cần thêm form. Nó cần một tập phụ thuộc và ranh giới tin cậy được lựa chọn riêng.

## 2. Bắt đầu từ nhu cầu chức năng

Trước khi viết CSP, xác định phần nào của hành trình thật sự cần JavaScript. Một form HTML gửi POST và được máy chủ xử lý có thể đáp ứng nhiều trường hợp đặt lại mật khẩu mà không cần chạy script.

Ngược lại, đăng ký passkey thường cần gọi API của trình duyệt, và một số giao diện cần hiển thị tiến độ hoặc trao đổi dữ liệu mà không tải lại trang. Khi đó, nên giới hạn script vào chức năng cụ thể.

Một lựa chọn kiến trúc cho trang khôi phục:

| Thành phần | Lựa chọn đề xuất | Lý do |
| --- | --- | --- |
| Gửi form mật khẩu mới | Ưu tiên form HTML hoặc một đoạn mã nội bộ nhỏ | Giảm số thành phần tiếp xúc với mật khẩu |
| Đăng ký passkey thay thế | Mã nội bộ gọi API cần thiết | Phải gắn với challenge và quyền do máy chủ xác nhận |
| Analytics hành vi chi tiết | Loại khỏi trang chứa bí mật | Không cần thiết để thực hiện khôi phục |
| Session replay | Loại khỏi hành trình nhạy cảm | Tránh phụ thuộc vào quy tắc che từng trường |
| Tag manager dùng chung | Không đưa vào template khôi phục | Tránh tạo đường tải thêm mã ngoài danh sách đã chọn |
| Widget hỗ trợ | Dẫn người dùng sang trang trợ giúp riêng khi phù hợp | Hạn chế mã ngoài tham gia vào form |
| Thư viện giao diện | Chỉ giữ phần thật sự dùng | Giảm phụ thuộc và mã không cần thiết |

Đây là các quyết định thiết kế cho tình huống trong bài học, không phải quy tắc rằng mọi giao diện phải có cùng cấu trúc. Nếu buộc dùng dịch vụ ngoài, cần xác định rõ dữ liệu nó được tiếp cận, người chịu trách nhiệm và phương án thay thế khi dịch vụ không hoạt động.

Một file tải từ đường dẫn cùng origin cũng cần có nguồn gốc rõ ràng. Sao chép SDK bên thứ ba vào thư mục assets không tự làm mã đó đáng tin hơn.

## 3. CSP là cổng cho phép thực thi mã

CSP được máy chủ gửi cho trình duyệt để giới hạn những hoạt động của tài liệu, trong đó có việc tải và chạy script. Nó là lớp bảo vệ bổ sung; vẫn phải xử lý đúng dữ liệu không tin cậy và ngăn chèn HTML hoặc JavaScript. Xem [OWASP: Content Security Policy](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html).

Chính sách nên được gửi bằng HTTP response header ngay khi phục vụ tài liệu khôi phục. Không đợi JavaScript khởi động rồi mới cố áp đặt chính sách cho chính trang đó.

### Trang không cần JavaScript

Nếu form do máy chủ kết xuất và không cần script:

~~~http
Content-Security-Policy: default-src 'none'; script-src 'none'; style-src 'self'; img-src 'self'; form-action 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'
~~~

Chính sách này là ví dụ cho một trang đơn giản, dùng stylesheet và ảnh nội bộ, gửi form về cùng origin. Nhu cầu tài nguyên khác phải được xác định cụ thể thay vì mở rộng toàn bộ policy.

### Trang cần một script nội bộ

Với một bundle JavaScript thông thường, không tải thêm script động, có thể dùng nonce:

~~~http
Content-Security-Policy: default-src 'none'; script-src 'nonce-{{NONCE}}'; script-src-attr 'none'; style-src 'self'; img-src 'self'; connect-src 'self'; form-action 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; worker-src 'none'
~~~

`{{NONCE}}` là placeholder mà máy chủ phải thay bằng giá trị ngẫu nhiên mới cho mỗi phản hồi HTML. Không gửi nguyên placeholder này và không dùng một chuỗi cố định cho tất cả người dùng.

HTML tương ứng:

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <title>Khôi phục tài khoản</title>
  <link rel="stylesheet" href="/assets/recovery-v1.css">
  <script nonce="{{NONCE}}" src="/assets/recovery-v1.js" defer></script>
</head>
<body>
  <main>
    <h1>Tiếp tục khôi phục tài khoản</h1>
    <p id="recovery-message" role="status"></p>
    <button id="show-help" type="button">Xem hướng dẫn</button>
  </main>
</body>
</html>
~~~

Header và thuộc tính nonce phải dùng cùng giá trị của một phản hồi. Template chỉ thêm nonce vào thẻ script do ứng dụng chủ động tạo; không quét toàn bộ HTML rồi gắn nonce cho mọi thẻ script tìm thấy, vì mã bị chèn cũng có thể được cấp quyền.

Nonce là dấu hiệu cho phép thực thi trong tài liệu, không phải token xác minh người dùng, bí mật chống CSRF hay bằng chứng rằng nội dung file đã được kiểm tra toàn vẹn. Hướng dẫn triển khai CSP của MDN giải thích cách dùng nonce và hash để nhận diện script được phép. Xem [MDN: CSP implementation](https://developer.mozilla.org/en-US/docs/Web/Security/Practical_implementation_guides/CSP).

### Vai trò của các chỉ thị trong ví dụ

| Chỉ thị | Vai trò trong trang minh họa |
| --- | --- |
| default-src 'none' | Từ chối mặc định đối với các loại tải tài nguyên sử dụng fallback này |
| script-src 'nonce-...' | Cho phép script có nonce phù hợp |
| script-src-attr 'none' | Chặn mã trong thuộc tính sự kiện như onclick |
| connect-src 'self' | Giới hạn các kết nối do chỉ thị này quản lý về cùng origin |
| form-action 'self' | Giới hạn đích gửi form |
| base-uri 'none' | Chặn việc dùng phần tử base để thay cách phân giải URL tương đối |
| object-src 'none' | Chặn nội dung kiểu object và embed |
| frame-ancestors 'none' | Không cho tài liệu bị nhúng bởi trang cha |
| worker-src 'none' | Chặn việc tạo worker mới qua các cơ chế thuộc phạm vi chỉ thị |

Không phải mọi chỉ thị đều kế thừa từ default-src. Đặc biệt, cần khai báo rõ form-action và frame-ancestors khi muốn áp dụng các hạn chế đó. Tài liệu [MDN: Content-Security-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy) mô tả các nhóm chỉ thị và fallback.

Các hạn chế tải tài nguyên không đồng nghĩa phân quyền nghiệp vụ. `connect-src 'self'` không phân biệt một endpoint khôi phục với một endpoint quản trị trên cùng origin; máy chủ vẫn phải kiểm tra quyền ở từng yêu cầu.

## 4. Quản lý nonce và chuỗi tin cậy

### Sinh nonce ở máy chủ

Ví dụ Java tạo giá trị ngẫu nhiên 128 bit rồi biểu diễn bằng Base64:

~~~java
import java.security.SecureRandom;
import java.util.Base64;

public final class RecoveryNonce {
    private static final SecureRandom RANDOM = new SecureRandom();

    private RecoveryNonce() {
    }

    public static String create() {
        byte[] bytes = new byte[16];
        RANDOM.nextBytes(bytes);
        return Base64.getEncoder().encodeToString(bytes);
    }
}
~~~

Ứng dụng gọi hàm một lần cho mỗi phản hồi HTML, giữ giá trị trong phạm vi phản hồi để đưa vào cả CSP và template. Không tạo hai nonce độc lập cho header và thẻ script.

Không lấy nonce từ thời gian, ID tài khoản, tham số query hoặc giá trị do trình duyệt tự khai báo. Cũng không dùng nonce của CSP làm mã khôi phục.

HTML chứa nonce cần được phục vụ sao cho lớp cache không phát lại cùng tài liệu có nonce cho nhiều phản hồi ngoài thiết kế. Trang khôi phục thường còn cần chính sách không lưu phản hồi nhạy cảm; cache của các file tĩnh có phiên bản là một quyết định riêng.

### Không bật strict-dynamic theo thói quen

`'strict-dynamic'` cho phép sự tin cậy từ một script gốc có nonce hoặc hash truyền sang script mà nó tải theo cơ chế được CSP quy định. Trên trình duyệt hỗ trợ, các biểu thức nguồn như 'self' và host allowlist trong script-src bị bỏ qua khi áp dụng cơ chế này. Xem [MDN: script-src và strict-dynamic](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/script-src#strict-dynamic).

Điều này hữu ích với ứng dụng có bộ nạp mã được kiểm soát, nhưng làm việc chọn script gốc trở nên đặc biệt quan trọng. Cấp nonce cho tag manager rồi để nó tải tùy ý không đạt mục tiêu giới hạn mã của trang khôi phục.

Ví dụ trong bài chủ động dùng một bundle thông thường và không thêm strict-dynamic. Nếu kiến trúc cần dynamic loader, phải xác định cả nguồn URL mà loader sử dụng và những mã có thể được tải tiếp. Không cho tham số từ URL hoặc nội dung người dùng quyết định đường dẫn script.

### Hash và SRI giải quyết phần nào?

Hash trong CSP là một cách khác để cho phép những đoạn script có nội dung khớp giá trị đã khai báo. Khi nội dung thay đổi, giá trị tương ứng cũng phải thay đổi. Cần chọn cơ chế phù hợp với cách sinh HTML và đóng gói mã, không tự thay nonce bằng một hash tượng trưng.

Subresource Integrity (SRI) cho trình duyệt so sánh nội dung tài nguyên với giá trị integrity được chỉ định; tài nguyên từ origin khác còn cần đáp ứng điều kiện CORS liên quan. SRI không giới hạn quyền của mã sau khi nó được chấp nhận chạy. Xem [MDN: Subresource Integrity](https://developer.mozilla.org/en-US/docs/Web/Security/Defenses/Subresource_Integrity).

Một file độc hại nhưng có đúng hash được cấu hình vẫn là file được cho phép. Do đó, CSP và SRI không thay thế việc chọn phụ thuộc, quản lý phiên bản và bảo vệ quá trình phát hành.

## 5. Viết JavaScript để dữ liệu không trở thành mã

Trang có CSP vẫn cần tránh các điểm chuyển dữ liệu không tin cậy thành HTML hoặc JavaScript.

Ví dụ, ứng dụng muốn hiển thị hướng dẫn lấy từ cấu hình:

~~~javascript
(() => {
  const button = document.getElementById("show-help");
  const message = document.getElementById("recovery-message");

  if (!button || !message) {
    return;
  }

  button.addEventListener("click", () => {
    message.textContent =
      "Chỉ tiếp tục khi bạn là người yêu cầu khôi phục tài khoản.";
  });
})();
~~~

Đoạn này dùng addEventListener thay cho thuộc tính onclick, và textContent thay cho việc ghép chuỗi vào innerHTML. Nó không cần bật unsafe-inline để hoạt động với policy đã minh họa.

Các lựa chọn thực hành cho mã khôi phục:

- Xử lý trạng thái bằng cấu trúc dữ liệu và nhánh điều kiện rõ ràng; không dùng eval hoặc Function để diễn giải dữ liệu.
- Không ghép token, tên tài khoản hoặc thông báo lỗi vào một đoạn JavaScript trong template.
- Nếu cần dữ liệu JSON từ máy chủ, dùng cơ chế tuần tự hóa và nhúng an toàn theo đúng ngữ cảnh của framework.
- Dùng thông báo giao diện đã xác định thay vì đưa nguyên HTML lỗi từ API vào DOM.
- Không lấy URL tải script từ query, fragment hoặc giá trị do người dùng kiểm soát.
- Không lưu token khôi phục vào biến toàn cục để nhiều SDK có thể dùng chung.
- Không đưa mật khẩu, mã dự phòng hoặc token khôi phục vào sự kiện analytics và log phía client.

Đưa token vào một closure giúp giảm việc vô tình truy cập qua biến toàn cục, nhưng không tạo một vùng cách ly trước script độc hại đã chạy trong cùng trang. Script đó vẫn có thể quan sát DOM hoặc tác động hành vi giao diện.

### Trusted Types là lớp bổ sung

Trên trình duyệt hỗ trợ, `require-trusted-types-for 'script'` yêu cầu một số điểm nhận dữ liệu nhạy cảm với chèn mã phải nhận đối tượng Trusted Types thay vì chuỗi thông thường. Chỉ thị `trusted-types` kiểm soát các tên policy được phép tạo. Xem [MDN: require-trusted-types-for](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/require-trusted-types-for) và [MDN: trusted-types](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/trusted-types).

Không tạo một policy mặc định chỉ trả nguyên mọi chuỗi đầu vào để làm lỗi biến mất. Một policy như vậy có thể hợp thức hóa dữ liệu chưa được xử lý an toàn. Việc áp dụng còn cần phù hợp với thư viện và các trình duyệt mà sản phẩm hỗ trợ; CSP nền tảng và xử lý DOM an toàn vẫn cần thiết.

## 6. Quan sát vi phạm mà không phát tán dữ liệu khôi phục

Có thể dùng Content-Security-Policy-Report-Only để quan sát một chính sách đề xuất trước khi thực thi. Header này không chặn vi phạm theo policy đang được quan sát. Nếu có đồng thời một CSP thực thi, CSP đó vẫn có tác dụng riêng. Xem [MDN: Content-Security-Policy-Report-Only](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy-Report-Only).

Ví dụ cấu hình kênh báo cáo cho policy quan sát:

~~~http
Reporting-Endpoints: recovery-csp="https://accounts.example.com/security/csp-report"
Content-Security-Policy-Report-Only: default-src 'none'; script-src 'nonce-{{NONCE}}'; object-src 'none'; base-uri 'none'; report-to recovery-csp
~~~

Đây chỉ là ví dụ policy quan sát rút gọn. Nó không thay thế toàn bộ policy thực thi ở phần trước, và việc nhận báo cáo phụ thuộc vào hỗ trợ của trình duyệt.

Báo cáo vi phạm cũng là dữ liệu cần kiểm soát. Nó có thể chứa URL của tài liệu, nguồn bị chặn hoặc thông tin khác có liên quan tới hành trình khôi phục. Khi URL còn mang token, chuyển nguyên báo cáo tới nhà cung cấp ngoài có thể tạo thêm một đường lộ dữ liệu.

Thiết kế tiếp nhận nên:

1. Ưu tiên endpoint do hệ thống kiểm soát cho hành trình nhạy cảm.
2. Loại bỏ bí mật khỏi URL và dữ liệu trước khi lưu hoặc chuyển tiếp.
3. Không tự bật thu thập trích đoạn mã nếu có khả năng chứa dữ liệu nhạy cảm.
4. Giới hạn dung lượng, tần suất, thời gian lưu và người được đọc.
5. Xem báo cáo là dữ liệu không tin cậy, không phải lệnh để tự động sửa CSP.

Nếu thấy báo cáo cho một miền lạ, trước hết cần hiểu vì sao có yêu cầu đó. Không tự thêm miền vào allowlist chỉ để làm bảng cảnh báo sạch hơn.

## 7. Xử lý khi script bị chặn hoặc không tải được

Trang khôi phục phải có hành vi rõ ràng khi JavaScript không chạy. Đây có thể là lỗi mạng, chặn tài nguyên bởi CSP hoặc không tương thích với môi trường người dùng.

Đối với thao tác không bắt buộc JavaScript, có thể giữ một form do máy chủ xử lý. Đối với thao tác bắt buộc API trình duyệt, như đăng ký passkey, giao diện nên giải thích rằng chưa thể tiếp tục và chỉ dẫn sang phương án khôi phục đã được hệ thống cho phép.

Không xử lý sự cố bằng cách tự nới script-src thành '*' hoặc thêm unsafe-inline, unsafe-eval cho toàn bộ hành trình. Cũng không tự hạ yêu cầu xác minh MFA chỉ vì mã giao diện bị chặn.

Một thông báo phù hợp có thể là:

> Không thể tải thành phần cần thiết để tiếp tục. Bạn có thể thử lại hoặc chọn phương án khôi phục khác đang được cung cấp.

Thông báo không nên kèm token, URL đầy đủ, stack trace hoặc dữ liệu bí mật mà trình duyệt đang giữ.

Nếu trang dùng nonce, lỗi phối hợp giữa header và HTML cần được xử lý ở máy chủ hoặc lớp phân phối. Người dùng không nên được hướng dẫn tắt cơ chế bảo vệ của trình duyệt để tiếp tục.

## 8. Những giới hạn phải giữ trong mô hình bảo vệ

CSP giảm khả năng mã không được cấp phép chạy, nhưng không chứng minh rằng mã được cấp phép là an toàn.

| Giả định dễ mắc | Giới hạn thực tế |
| --- | --- |
| Chỉ tải script cùng origin là đủ | Một script cùng origin có thể có lỗi, bị thay thế hoặc chứa phụ thuộc không phù hợp |
| Có nonce thì script chỉ được tải từ đường dẫn nội bộ | Nonce là cơ chế cấp quyền; template vẫn phải cố định src đúng thiết kế |
| connect-src ngăn mọi cách đưa dữ liệu ra ngoài | Chỉ thị quản lý một nhóm kết nối, không phải mọi hành vi điều hướng hoặc mọi kênh rò rỉ |
| Cookie HttpOnly làm script độc hại vô hại | Script vẫn có thể đọc trường nhập và gửi yêu cầu trong ngữ cảnh trang |
| worker-src 'none' xóa mọi worker đã tồn tại | Nó không phải lệnh thu hồi một service worker đã kiểm soát trang |
| Trình duyệt chấp nhận CSP thì API không cần phân quyền | Mọi thay đổi tài khoản vẫn phải được máy chủ kiểm tra độc lập |
| Report-Only đã bảo vệ người dùng | Policy ở chế độ quan sát không thực thi việc chặn |

Nếu ứng dụng chính có tập script lớn hoặc service worker có phạm vi rộng, một origin khôi phục chuyên biệt có thể giúp tách bề mặt tin cậy. Việc tách cần được thiết kế cùng cookie, CORS, CSRF và chuyển giao giao dịch; một subdomain mới tự nó không hoàn thành các yêu cầu đó.

Ở phía máy chủ, vẫn phải kiểm tra token dùng một lần, thời hạn, đúng mục đích, đúng giao dịch và bằng chứng xác minh cần thiết. Không chấp nhận việc thay mật khẩu, xóa MFA hay thêm passkey chỉ vì client gửi trạng thái “đã xác minh”.

Một chính sách script tốt cho trang khôi phục bắt đầu bằng việc giảm mã cần chạy, cấp quyền rõ cho phần còn lại và bảo đảm máy chủ không phụ thuộc vào sự trung thực của JavaScript để quyết định quyền tài khoản.

