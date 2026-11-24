# Extension review

Đánh giá bảo mật extension là quá trình kiểm tra một tiện ích trình duyệt trước khi cài đặt, phát hành hoặc cập nhật để xác định extension có xin đúng quyền, xử lý dữ liệu an toàn và chỉ thực hiện những hành vi người dùng đã chấp thuận hay không. Một extension có thể đọc nội dung trang, quan sát tab, thay đổi giao diện, gửi dữ liệu ra mạng hoặc gọi API đặc quyền của trình duyệt. Vì vậy, review cần xem xét đồng thời manifest, mã nguồn, luồng dữ liệu, ranh giới giữa các ngữ cảnh chạy và hành vi thực tế.

Trong bài này, “review” tập trung vào đánh giá bảo mật kỹ thuật. Kết quả review nên trả lời được ba câu hỏi: extension có quyền gì, dữ liệu nào đi qua extension và những quyền đó được sử dụng ở đâu. Mỗi kết luận cần gắn với bằng chứng có thể kiểm tra lại.

## Mục tiêu và phạm vi review

Một đợt review có thể phục vụ nhiều thời điểm:

- **Trước khi cài đặt:** xác định extension có đáng tin cậy, có yêu cầu quyền phù hợp với chức năng và có hành vi thu thập dữ liệu minh bạch hay không.
- **Trước khi phát hành:** tìm lỗi trong mã nguồn, cấu hình, thư viện phụ thuộc và quy trình đóng gói.
- **Trước khi cập nhật:** kiểm tra thay đổi về quyền, host, luồng dữ liệu, endpoint mạng và hành vi mới so với phiên bản đã được duyệt.
- **Trong vận hành:** điều tra một quyền mới, một yêu cầu mạng bất thường, phản ánh về quyền riêng tư hoặc dấu hiệu extension bị chiếm quyền phát hành.

Trước khi đọc mã, cần ghi lại ít nhất tên và ID extension, phiên bản, trình duyệt và phiên bản trình duyệt mục tiêu, manifest, mã nguồn hoặc gói cài đặt, danh sách thư viện phụ thuộc, các dịch vụ máy chủ liên quan và chức năng mà sản phẩm tuyên bố cung cấp. Nếu chỉ có gói đã biên dịch, cần ghi rõ giới hạn của việc review vì khó truy nguyên mã nguồn và xác nhận tính tái lập của bản dựng.

Xác định tài sản cần bảo vệ: nội dung trang, lịch sử duyệt web, cookie, thông tin đăng nhập, dữ liệu biểu mẫu, tệp người dùng, token, cấu hình và quyền truy cập vào tài khoản bên thứ ba. Sau đó xác định tác nhân có thể gây rủi ro: trang web độc hại, nội dung do người dùng kiểm soát, script bên thứ ba, máy chủ bị xâm nhập, thư viện độc hại hoặc người có quyền phát hành extension.

## Hiểu các ranh giới tin cậy

Extension thường có nhiều ngữ cảnh chạy với quyền và dữ liệu khác nhau. Reviewer cần lập sơ đồ thành phần và kiểm tra mọi đường đi giữa chúng.

~~~mermaid
flowchart LR
    U[Người dùng] -->|Thao tác| UI[Extension page hoặc popup]
    P[Trang web] <--> DOM[Content script]
    DOM <-->|Message đã kiểm tra| SW[Background service worker]
    UI <-->|Extension messaging| SW
    SW -->|Browser APIs| B[Trình duyệt]
    SW <-->|HTTPS| API[Dịch vụ bên ngoài]
~~~

- **Extension page hoặc popup** là giao diện do extension kiểm soát và có thể gọi các API được cấp quyền.
- **Background service worker** xử lý sự kiện nền trong Manifest V3. Nó có thể gọi API đặc quyền, điều phối message và thực hiện yêu cầu mạng theo quyền đã cấp. Service worker có thể bị dừng khi không hoạt động, vì vậy không nên dựa vào biến toàn cục trong bộ nhớ để lưu trạng thái quan trọng.
- **Content script** chạy trên trang được khai báo hoặc được cấp quyền truy cập. Trong Chrome, content script mặc định chạy trong isolated world: biến JavaScript của nó được tách khỏi biến của trang, nhưng nó vẫn thao tác trên cùng DOM. Nội dung DOM, thuộc tính, sự kiện và dữ liệu do trang cung cấp đều có thể bị trang kiểm soát.
- **Trang web** là vùng không tin cậy, kể cả khi extension chỉ hoạt động trên một website quen thuộc. Trang có thể bị XSS, chứa nội dung do người dùng tạo hoặc tải script bên thứ ba.
- **Dịch vụ bên ngoài** có thể nhận dữ liệu từ extension. Cần xác định rõ dữ liệu nào được gửi, mục đích, thời điểm, thời hạn lưu trữ và bên nào có quyền truy cập.

Isolated world không làm cho DOM trở nên đáng tin. Một content script có thể đọc một phần tử do trang tạo, nhưng giá trị trong phần tử đó vẫn là đầu vào không tin cậy. Tương tự, một message gửi từ content script đến service worker không tự động an toàn chỉ vì cả hai thuộc cùng extension. Message có thể bắt nguồn từ dữ liệu do trang kiểm soát.

## Review manifest và quyền

Manifest là điểm bắt đầu tốt nhất vì nó cho biết extension khai báo những khả năng nào. Với Manifest V3, hãy xem cả quyền API, quyền truy cập host và các cấu hình ảnh hưởng đến bề mặt tấn công.

| Thành phần | Câu hỏi cần đặt ra | Dấu hiệu cần xem xét kỹ |
|---|---|---|
| permissions | API nào thực sự cần cho chức năng? | Quyền nhạy cảm được khai báo nhưng không có luồng sử dụng hợp lý |
| host_permissions | Extension cần truy cập những website nào? | Quyền rộng như `<all_urls>` hoặc mọi subdomain mà không có lý do cụ thể |
| optional_host_permissions | Có thể xin quyền theo nhu cầu tại thời điểm người dùng bật tính năng không? | Xin quyền cho nhiều host ngay từ lần cài đầu tiên |
| content_scripts.matches | Content script được đưa vào trang nào? | Match pattern rộng hơn phạm vi sản phẩm cần hỗ trợ |
| web_accessible_resources | Tài nguyên nào được trang web bên ngoài tải? | Công khai script, trang nội bộ hoặc dữ liệu không cần thiết |
| externally_connectable | Website hoặc extension bên ngoài nào được phép kết nối? | Cho phép origin hoặc extension ID không được kiểm soát |
| content_security_policy | Extension page giới hạn nguồn script ra sao? | Cho phép mã thực thi động hoặc nới lỏng CSP không cần thiết |

Không nên đánh giá quyền chỉ bằng tên. Cần nối từng quyền với một chức năng, vị trí gọi API và thời điểm sử dụng. Ví dụ, chức năng chỉ chạy khi người dùng bấm nút trên tab hiện tại có thể phù hợp với `activeTab` và `scripting`; nó có thể không cần quyền đọc mọi website. Nếu tính năng chỉ dùng trên một cổng nội bộ, hãy giới hạn host vào origin cần thiết hoặc xin optional host permission khi người dùng bật tính năng.

Ví dụ manifest tối giản cho một tiện ích chỉ chạy sau thao tác của người dùng:

~~~json
{
  "manifest_version": 3,
  "name": "Reading helper",
  "version": "1.0.0",
  "permissions": ["activeTab", "scripting", "storage"],
  "optional_host_permissions": ["https://portal.example.com/*"],
  "background": {
    "service_worker": "service-worker.js"
  },
  "action": {
    "default_title": "Enable reading helper"
  },
  "content_security_policy": {
    "extension_pages": "script-src 'self'; object-src 'self'"
  }
}
~~~

Đây chỉ là ví dụ để minh họa cách giới hạn quyền; manifest thực tế phải khớp chức năng và các trình duyệt mục tiêu. Với Chrome, `activeTab` cấp quyền truy cập tạm thời vào tab sau một thao tác rõ ràng của người dùng. `scripting` cho phép sử dụng API chèn script, còn `optional_host_permissions` cho phép extension yêu cầu host cụ thể khi cần. Reviewer cần kiểm tra cả mã gọi `chrome.permissions.request` và giao diện giải thích lý do xin quyền.

Đặc biệt chú ý các quyền có thể mở rộng đáng kể khả năng quan sát hoặc thay đổi trình duyệt, chẳng hạn `cookies`, `history`, `tabs`, `webRequest`, `downloads` và quyền truy cập host rộng. Một quyền có thể hợp lệ về mặt kỹ thuật nhưng vẫn không phù hợp với mục đích sản phẩm. Nếu extension cần quyền rộng, hồ sơ review phải nêu rõ chức năng không thể thực hiện bằng quyền hẹp hơn và rủi ro người dùng chấp nhận.

## Kiểm tra content script và thao tác DOM

Content script thường là nơi dữ liệu từ website đi vào extension. Hãy tìm mọi chỗ đọc `location`, URL, DOM, thuộc tính, form, selection, event, `window.postMessage` và dữ liệu do trang đưa vào. Với mỗi giá trị, xác định nguồn, định dạng mong đợi, giới hạn kích thước và cách sử dụng.

Tránh đưa chuỗi không tin cậy trực tiếp vào HTML. Ví dụ sau có thể biến tiêu đề do trang kiểm soát thành HTML thực thi:

~~~javascript
// Không an toàn: pageTitle có thể chứa markup do trang kiểm soát.
container.innerHTML = pageTitle;
~~~

Nếu chỉ cần hiển thị văn bản, tạo node và gán `textContent`:

~~~javascript
const label = document.createElement("span");
label.textContent = pageTitle;
container.replaceChildren(label);
~~~

Review cả `insertAdjacentHTML`, `outerHTML`, `document.write`, thuộc tính sự kiện, URL điều hướng và các thư viện dựng giao diện. Nếu thực sự cần render HTML, phải dùng bộ phân tích hoặc sanitizer phù hợp với ngữ cảnh và kiểm tra cấu hình của nó; không tự viết một hàm lọc chuỗi bằng vài phép thay thế đơn giản.

Khi content script trao đổi với script của trang qua `window.postMessage`, hãy kiểm tra `event.source`, `event.origin`, kiểu message và cấu trúc payload. Kiểm tra origin chỉ xác nhận nơi message đến; nó không chứng minh nội dung là an toàn, bởi trang cùng origin cũng có thể bị khai thác. Không để message từ trang trực tiếp kích hoạt API đặc quyền như đọc cookie, tải URL tùy ý hoặc truy cập tệp.

## Kiểm tra messaging và quyền của service worker

Service worker thường là nơi tập trung quyền. Vì vậy, mọi message yêu cầu hành động đặc quyền phải được xác thực và kiểm tra schema. Không nên viết một handler tổng quát nhận `{ action, url, data }` rồi thực hiện hành động dựa trên các giá trị đó mà không có allowlist.

Ví dụ dưới đây minh họa handler chỉ chấp nhận một loại yêu cầu từ content script trên origin được cho phép, ở frame chính:

~~~javascript
const APPROVED_ORIGIN = "https://portal.example.com";

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (sender.id !== chrome.runtime.id || sender.frameId !== 0) {
    return;
  }

  let sourceUrl;
  try {
    sourceUrl = new URL(sender.url || "");
  } catch {
    return;
  }

  if (sourceUrl.origin !== APPROVED_ORIGIN) {
    return;
  }

  if (!message || message.type !== "GET_READING_STATE") {
    return;
  }

  chrome.storage.local.get(["readingState"])
    .then(({ readingState }) => {
      sendResponse({ ok: true, readingState: readingState ?? null });
    })
    .catch(() => sendResponse({ ok: false }));

  return true;
});
~~~

Handler này chỉ là khung minh họa. Trong sản phẩm, cần kiểm tra thêm schema của mọi trường được nhận, giới hạn độ dài, trạng thái quyền hiện tại và điều kiện nghiệp vụ. Nếu cần hỗ trợ nhiều frame hoặc nhiều origin, hãy khai báo rõ từng trường hợp. Nếu extension nhận message từ extension hoặc website bên ngoài, review riêng `onMessageExternal` và `externally_connectable`, sau đó allowlist đúng ID hoặc origin dự kiến.

Các dấu hiệu rủi ro cao trong messaging gồm: nhận URL tùy ý rồi fetch bằng quyền của extension; nhận tên API hoặc tên hàm rồi gọi động; chuyển dữ liệu trang thành lệnh; trả token hoặc dữ liệu nhạy cảm cho content script; tin vào `tabId`, `frameId` hoặc URL do payload tự khai báo thay vì metadata của sender. Service worker phải tự xác định ngữ cảnh gửi từ `sender` và kiểm tra quyền trước khi thực hiện hành động.

## Review lưu trữ, mạng và quyền riêng tư

Vẽ luồng dữ liệu từ lúc thu thập đến lúc xóa. Với mỗi loại dữ liệu, ghi rõ nguồn, mục đích, nơi lưu, nơi truyền, thời gian lưu và thành phần có thể đọc. Dữ liệu cần xem xét gồm URL, tiêu đề trang, nội dung trang, lịch sử duyệt, cookie, thông tin tài khoản, token, dữ liệu biểu mẫu và định danh thiết bị.

- **Lưu trữ:** chỉ lưu dữ liệu cần thiết. `chrome.storage.local` và `chrome.storage.sync` là nơi lưu tiện ích, không phải kho bí mật chuyên dụng. Không lưu mật khẩu hoặc khóa bí mật dài hạn ở dạng có thể đọc được. Kiểm tra ngữ cảnh nào có thể truy cập storage; khi phù hợp, giới hạn access level của storage để content script không đọc được dữ liệu chỉ dành cho trusted contexts.
- **Token:** hạn chế thời gian sống và phạm vi token; tránh đưa token vào DOM, URL, log hoặc message không cần thiết. Dùng cơ chế xác thực phù hợp của nền tảng thay vì tự xây dựng quy trình lưu mật khẩu.
- **Kết nối mạng:** kiểm tra mọi `fetch`, WebSocket, beacon và thư viện gửi telemetry. Chỉ gửi đến endpoint được xác định, dùng HTTPS, xác thực dữ liệu phản hồi và không gửi toàn bộ nội dung trang nếu chức năng chỉ cần một vài trường.
- **Quyền riêng tư:** đối chiếu hành vi thực tế với thông báo cho người dùng. Nếu thu thập hoặc chia sẻ dữ liệu, cần có mục đích cụ thể, lựa chọn phù hợp và cơ chế xóa dữ liệu theo cam kết của sản phẩm.
- **Log và lỗi:** không ghi token, cookie, nội dung trang hoặc dữ liệu cá nhân vào console, báo cáo lỗi hay hệ thống analytics. Kiểm tra cả log trong bản production.

Một review tốt không chỉ tìm nơi gọi API mạng. Hãy theo dõi dữ liệu qua nhiều bước: content script đọc DOM, gửi message, service worker biến đổi dữ liệu, thư viện analytics nhận dữ liệu và máy chủ lưu lại. Một trường có vẻ vô hại ở từng bước có thể trở thành dữ liệu nhạy cảm khi được kết hợp với URL hoặc định danh người dùng.

## Kiểm tra mã thực thi, thư viện và chuỗi cung ứng

Với Manifest V3 trên Chrome, extension page phải tuân theo chính sách hạn chế mã thực thi. Mã JavaScript thực thi cần nằm trong gói extension và được kiểm soát qua quy trình phát hành. Không tải mã JavaScript từ máy chủ hoặc CDN để thực thi, không dùng `eval` hay cơ chế tương đương để biến dữ liệu từ xa thành mã. Dữ liệu cấu hình hoặc nội dung từ xa vẫn cần được kiểm tra schema và không được diễn giải như chương trình.

Kiểm tra các điểm sau:

- Danh sách package trực tiếp và gián tiếp, phiên bản khóa trong lockfile, nguồn tải và lịch sử thay đổi của thư viện.
- Script cài đặt, bước build, plugin bundler và mã được sinh trong quá trình đóng gói.
- Mã bị làm rối khó giải thích, đoạn mã không có nguồn gốc, file thực thi bất ngờ hoặc dependency không phục vụ chức năng.
- Quyền của tài khoản và quy trình có thể phát hành extension, bảo vệ khóa ký, tài khoản store và pipeline CI/CD.
- Khả năng tái tạo bản dựng từ source đã review và đối chiếu hash của gói chuẩn bị phát hành.

Việc một thư viện phổ biến hoặc có nhiều lượt tải không chứng minh phiên bản đang dùng an toàn. Review cần kiểm tra phiên bản cụ thể, dependency bắc cầu và thay đổi trong bản cập nhật. Khi phát hiện dependency có rủi ro, xác định đường gọi thực tế và khả năng dữ liệu không tin cậy đi vào thành phần đó.

## Kiểm thử hành vi thực tế

Static review giúp tìm cấu hình và đường đi dữ liệu đáng ngờ, nhưng không thể thay thế kiểm thử trong trình duyệt. Dùng profile thử nghiệm sạch, cài đúng gói sẽ phát hành và ghi lại hành vi trước, trong và sau khi cấp quyền.

Các phép thử nên bao gồm:

1. **Cài đặt lần đầu:** ghi lại cảnh báo quyền, màn hình onboarding và các kết nối mạng tự phát sinh trước khi người dùng bật chức năng.
2. **Cấp và thu hồi quyền:** xác minh extension chỉ hoạt động trong phạm vi đã cấp, xử lý đúng khi quyền bị từ chối hoặc thu hồi và không liên tục gây áp lực để người dùng cấp quyền rộng.
3. **Trang đầu vào độc hại:** thử tiêu đề chứa HTML, URL có ký tự đặc biệt, form bất thường, nội dung rất dài, sự kiện giả và message sai schema.
4. **Ngữ cảnh trình duyệt:** thử tab khác origin, iframe, tab đã điều hướng, tab đóng, nhiều cửa sổ và service worker bị dừng rồi khởi động lại.
5. **Mạng:** quan sát endpoint, method, header, payload, redirect, lỗi TLS và hành vi khi máy chủ trả dữ liệu sai định dạng hoặc không phản hồi.
6. **Lưu trữ:** kiểm tra dữ liệu sau khi đăng xuất, xóa dữ liệu extension, thu hồi quyền, cài lại và cập nhật phiên bản.
7. **Cập nhật:** so sánh manifest, quyền, script, dependency và endpoint giữa hai bản. Kiểm tra thay đổi quyền có được giải thích và có yêu cầu người dùng chấp thuận phù hợp hay không.

Khi kiểm thử, ghi lại phiên bản trình duyệt, phiên bản extension, cấu hình, thao tác tái hiện, log liên quan và kết quả quan sát. Không dùng tài khoản hoặc dữ liệu sản xuất nếu không có phê duyệt và biện pháp bảo vệ phù hợp.

## Phân loại và ghi nhận phát hiện

Một phát hiện cần đủ thông tin để người khác tái hiện và sửa. Mẫu ghi nhận nên có:

| Trường | Nội dung |
|---|---|
| Tiêu đề | Mô tả ngắn hành vi hoặc điểm yếu |
| Mức độ | Critical, High, Medium hoặc Low, kèm lý do đánh giá |
| Phiên bản và vị trí | ID, phiên bản extension, file, hàm hoặc cấu hình liên quan |
| Điều kiện | Quyền, thao tác người dùng và trạng thái cần có để lỗi xảy ra |
| Bằng chứng | Đoạn mã, log mạng, ảnh chụp hoặc kết quả kiểm thử |
| Tác động | Dữ liệu hoặc chức năng có thể bị ảnh hưởng và ai có thể khai thác |
| Tái hiện | Các bước ngắn, có thể lặp lại trong profile thử nghiệm |
| Khuyến nghị | Thay đổi cụ thể và cách xác minh sau khi sửa |

Mức độ phải phản ánh tác động và khả năng khai thác trong bối cảnh extension. Ví dụ, một message có thể yêu cầu service worker fetch URL tùy ý sẽ nghiêm trọng hơn nếu kẻ tấn công chỉ có thể gửi message từ một trang không thể truy cập. Ngược lại, nếu content script chạy trên mọi website và message đó có thể kích hoạt yêu cầu bằng quyền của extension, phạm vi ảnh hưởng có thể rất lớn. Không gán mức độ chỉ dựa vào tên quyền hoặc một công cụ quét tự động.

Nên tách phát hiện đã xác nhận khỏi nghi vấn cần thêm bằng chứng. Nếu chưa tái hiện được, ghi rõ giả định, dữ liệu còn thiếu và bước kiểm tra tiếp theo. Điều này giúp nhóm phát triển ưu tiên sửa đúng nguyên nhân và giúp người duyệt hiểu giới hạn của kết luận.

## Ví dụ review: tiện ích lưu bài đọc

Giả sử một extension có chức năng lưu tiêu đề và URL của trang hiện tại vào danh sách đọc. Manifest yêu cầu `tabs`, `cookies` và host permission `<all_urls>`. Service worker gửi tiêu đề, URL và cookie đến một API từ xa mỗi khi người dùng mở tab.

Review cần đối chiếu từng quyền và dữ liệu với chức năng:

1. Để lưu tab hiện tại sau khi người dùng bấm nút, có thể dùng `activeTab` và chỉ đọc tab được người dùng chọn. Quyền `tabs` rộng có thể không cần thiết nếu extension không phải quan sát mọi tab.
2. Chức năng không cần cookie để lưu tiêu đề và URL, nên quyền `cookies` cần được loại bỏ.
3. Nếu extension chỉ hỗ trợ một website, giới hạn host vào website đó. Nếu hỗ trợ nhiều website, cân nhắc xin quyền theo từng website hoặc theo hành động người dùng.
4. Chỉ gửi dữ liệu khi người dùng bấm lưu và giải thích rõ dữ liệu được gửi đến dịch vụ nào. Không gửi cookie hoặc nội dung trang nếu không có yêu cầu chức năng và cơ sở rõ ràng.
5. Service worker chỉ nhận message lưu bài với schema hẹp, kiểm tra sender và không nhận URL đích tùy ý để thực hiện fetch.
6. Kiểm thử với trang có tiêu đề chứa HTML, tab ngoài phạm vi, quyền bị thu hồi và máy chủ không phản hồi. Xác minh không có request nền thu thập dữ liệu trước thao tác lưu.

Ví dụ này cho thấy review không dừng ở việc quyền có hợp lệ hay không. Reviewer cần kiểm tra xem quyền có cần thiết, dữ liệu có tương xứng với chức năng và thời điểm thu thập có đúng với kỳ vọng của người dùng hay không.

## Checklist trước khi chấp thuận

- [ ] Đã ghi nhận ID, phiên bản, trình duyệt mục tiêu và nguồn gói cài đặt.
- [ ] Mỗi permission, host permission và content script match đều có lý do gắn với chức năng.
- [ ] Đã kiểm tra `web_accessible_resources`, `externally_connectable` và CSP.
- [ ] Content script xử lý DOM và dữ liệu trang như đầu vào không tin cậy.
- [ ] Message handler kiểm tra sender, schema, quyền và allowlist hành động.
- [ ] Service worker không cung cấp API đặc quyền tổng quát cho nội dung trang.
- [ ] Dữ liệu lưu trữ, token, log và payload mạng đã được rà soát.
- [ ] Không có mã thực thi từ xa hoặc cơ chế biến dữ liệu từ xa thành mã.
- [ ] Dependency, build pipeline và quyền phát hành đã được kiểm tra.
- [ ] Đã kiểm thử quyền, trang độc hại, lỗi mạng, iframe, service worker restart và cập nhật.
- [ ] Mọi phát hiện có bằng chứng, mức độ, tác động, bước tái hiện và khuyến nghị.

Chỉ chấp thuận khi các phát hiện nghiêm trọng đã được xử lý hoặc có quyết định chấp nhận rủi ro được ghi nhận bởi đúng người có thẩm quyền. Sau khi phát hành, lưu lại phiên bản và kết quả review để lần cập nhật tiếp theo có thể so sánh chính xác.

## Câu hỏi tự kiểm tra

1. Vì sao content script chạy trong isolated world vẫn phải coi DOM là dữ liệu không tin cậy?
2. Một extension chỉ thao tác trên tab hiện tại sau khi người dùng bấm nút có thể giảm quyền bằng cách nào?
3. Vì sao service worker phải xác thực sender và schema của message dù message đến từ extension?
4. Khi review một request mạng, cần lần theo những bước nào để xác định dữ liệu người dùng bị gửi đi?
5. Một bản cập nhật chỉ thay đổi host permission vẫn cần review lại vì những lý do gì?

Nếu trả lời được các câu hỏi này bằng cách chỉ ra vị trí trong manifest, mã nguồn và bằng chứng runtime, bạn đã có nền tảng để thực hiện một đợt extension review có thể kiểm chứng và lặp lại.
