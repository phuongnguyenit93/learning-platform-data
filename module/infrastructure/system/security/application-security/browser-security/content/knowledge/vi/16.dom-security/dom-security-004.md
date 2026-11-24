# outerHTML và ranh giới an toàn của DOM

`outerHTML` là thuộc tính của phần tử DOM dùng để đọc hoặc thay thế toàn bộ phần tử bằng một đoạn HTML. Nó rất tiện khi cần dựng lại một vùng giao diện, nhưng cũng là một điểm đưa dữ liệu vào bộ phân tích HTML của trình duyệt. Nếu chuỗi được gán có chứa dữ liệu do người dùng hoặc hệ thống bên ngoài kiểm soát, ứng dụng có thể tạo ra DOM ngoài dự kiến và mở đường cho DOM-based XSS.

Bài học này tập trung vào cách `outerHTML` hoạt động, vì sao setter của nó là một HTML injection sink, cách chọn API an toàn hơn, và cách kết hợp bộ làm sạch HTML với Trusted Types và Content Security Policy (CSP).

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt hành vi đọc và ghi của `outerHTML`.
- Giải thích vì sao gán chuỗi không tin cậy vào `outerHTML` có thể dẫn đến DOM XSS.
- Nhận diện luồng dữ liệu từ nguồn không tin cậy đến HTML sink trong mã trình duyệt.
- Chọn `textContent`, các API tạo node hoặc bộ làm sạch HTML phù hợp với nhu cầu.
- Dùng Trusted Types để kiểm soát những vị trí được phép nhận HTML.
- Kiểm thử và rà soát các luồng sử dụng `outerHTML` trong ứng dụng.

## 1. `outerHTML` làm gì?

`outerHTML` có hai hành vi khác nhau tùy cách sử dụng.

| Cách sử dụng | Hành vi |
|---|---|
| Đọc `element.outerHTML` | Trả về chuỗi HTML tuần tự hóa của chính phần tử đó, gồm biểu diễn thẻ của phần tử và markup con (nếu có). |
| Gán `element.outerHTML = value` | Phân tích `value` như một đoạn HTML trong ngữ cảnh phù hợp, sau đó thay thế phần tử đích bằng các node được tạo ra. |

Ví dụ đọc HTML:

~~~js
const card = document.querySelector("#profile-card");

console.log(card.outerHTML);
// Ví dụ: <article id="profile-card"><h2>An</h2></article>
~~~

Ví dụ thay thế phần tử:

~~~js
const card = document.querySelector("#profile-card");

card.outerHTML =
  '<article id="profile-card"><h2>Hồ sơ mới</h2></article>';
~~~

Sau phép gán, phần tử cũ được thay bằng phần tử mới. Biến `card` vẫn tham chiếu đến node cũ đã bị tách khỏi cây DOM. Nếu những dòng tiếp theo tiếp tục sửa `card`, thay đổi đó có thể không xuất hiện trên trang.

~~~js
const oldCard = document.querySelector("#profile-card");

oldCard.outerHTML =
  '<article id="profile-card"><h2>Hồ sơ mới</h2></article>';

// oldCard vẫn là node cũ, không phải article mới vừa được chèn.
console.log(oldCard.isConnected); // false
~~~

Điểm khác biệt này quan trọng khi sửa DOM trong ứng dụng có nhiều thành phần phụ thuộc vào cùng một node. Nó cũng có thể làm mất các event listener được gắn trực tiếp lên phần tử cũ, trạng thái JavaScript gắn trên node và những tham chiếu mà mã khác đang giữ. Event delegation trên một phần tử cha còn tồn tại có thể tiếp tục hoạt động, nhưng listener gắn trên node bị thay thế thì không tự chuyển sang node mới.

Setter của `outerHTML` phân tích HTML theo ngữ cảnh của phần tử cha. Vì vậy, cùng một chuỗi có thể tạo ra cây node khác nhau trong các ngữ cảnh như bảng HTML hoặc danh sách. Đừng xem thao tác này như phép thay thế chuỗi thuần túy: trình duyệt đang chạy bộ phân tích HTML và cập nhật cây DOM.

## 2. Vì sao setter là một điểm nhạy cảm về bảo mật?

Ứng dụng thường nhận dữ liệu từ nhiều nguồn:

- Trường nhập liệu, nội dung bình luận, tên hiển thị hoặc mô tả hồ sơ.
- Tham số URL, fragment sau dấu `#`, dữ liệu từ `postMessage`.
- Phản hồi API, dữ liệu nhập từ CSV hoặc nội dung do dịch vụ bên thứ ba cung cấp.
- `localStorage`, `sessionStorage`, IndexedDB và dữ liệu được lưu từ phiên trước.
- Thuộc tính `data-*` hoặc nội dung được máy chủ đưa vào trang.

Các nguồn này không tự trở nên đáng tin chỉ vì dữ liệu đã đi qua máy chủ, đã được lưu trong cơ sở dữ liệu hoặc được đọc từ cùng origin. Dữ liệu có thể do người dùng khác tạo, bị sửa đổi trước khi lưu, hoặc đến từ một dịch vụ mà ứng dụng không kiểm soát.

Một luồng DOM XSS thường có dạng:

~~~text
Nguồn dữ liệu không tin cậy
        |
        v
Đọc dữ liệu trong JavaScript
        |
        v
Ghép chuỗi HTML hoặc xử lý không phù hợp
        |
        v
Gán vào outerHTML
        |
        v
Trình duyệt phân tích và chèn node
        |
        v
Nội dung chủ động có thể thực thi trong origin của ứng dụng
~~~

`outerHTML` setter là một HTML injection sink vì chuỗi đầu vào được diễn giải thành cấu trúc HTML. Khi dữ liệu không tin cậy có thể điều khiển cấu trúc được tạo ra, kẻ tấn công có thể đưa thuộc tính sự kiện, URL nguy hiểm hoặc phần tử HTML có hành vi chủ động vào trang.

Ví dụ sau minh họa lỗi. Không đưa đoạn thử nghiệm này lên trang thật có người dùng; chỉ chạy trong trang lab cục bộ:

~~~js
const target = document.querySelector("#preview");
const untrustedMarkup =
  "<img src=x onerror=\"alert('DOM XSS')\">";

target.outerHTML = untrustedMarkup;
~~~

Nếu trình duyệt tải ảnh thất bại và chính sách trang cho phép inline event handler, handler `onerror` có thể chạy trong ngữ cảnh trang. Một trang có CSP nghiêm ngặt có thể chặn một số cách thực thi này, nhưng CSP không biến việc chèn HTML không tin cậy thành thao tác an toàn.

Một số điểm cần nhớ:

- Thẻ `<script>` được tạo qua các thao tác phân tích HTML dạng fragment như `innerHTML` hoặc `outerHTML` thường không được thực thi như một script vừa tải trực tiếp từ tài liệu. Đây không phải lý do để tin chuỗi HTML: thuộc tính sự kiện, URL có sơ đồ nguy hiểm, phần tử nhúng và các cấu trúc khác vẫn có thể tạo hành vi không mong muốn.
- Mức độ nguy hiểm phụ thuộc vào loại node, thuộc tính, trình duyệt, ngữ cảnh phân tích và chính sách bảo mật đang áp dụng.
- Nội dung được chèn có thể kích hoạt tải tài nguyên, tạo biểu mẫu hoặc liên kết giả, thay đổi giao diện để lừa người dùng, hoặc chạy mã khi một sự kiện xảy ra.
- Khi mã chạy trong origin của ứng dụng, nó có thể thao tác DOM và thực hiện các hành động mà người dùng hiện tại được phép thực hiện. Cookie có cờ HttpOnly không thể bị đọc trực tiếp bằng JavaScript, nhưng điều đó không loại bỏ các tác động khác của XSS.

Vì vậy, cần đánh giá toàn bộ luồng dữ liệu thay vì chỉ tìm một chuỗi có vẻ nguy hiểm.

## 3. Mẫu lỗi thường gặp

### 3.1 Nội suy dữ liệu vào chuỗi HTML

~~~js
function renderProfile(user) {
  const current = document.querySelector("#profile");

  current.outerHTML =
    '<section id="profile">' +
      "<h2>" + user.displayName + "</h2>" +
      "<p>" + user.biography + "</p>" +
    "</section>";
}
~~~

`displayName` và `biography` có thể chứa ký tự tạo thành thẻ hoặc thuộc tính HTML. Việc nối chuỗi không tự mã hóa dữ liệu. Nếu một trường chứa markup do người dùng kiểm soát, trình duyệt sẽ phân tích markup đó khi setter chạy.

Lỗi tương tự xuất hiện khi:

- Dùng template literal để tạo một đoạn HTML từ dữ liệu API.
- Đọc nội dung trong query string rồi ghép vào markup.
- Tin rằng dữ liệu lấy từ `localStorage` luôn an toàn.
- Chỉ lọc một vài chuỗi như `<script>` hoặc `javascript:`.
- Mã hóa HTML bằng một hàm không phù hợp rồi đưa kết quả vào một ngữ cảnh HTML khác.

### 3.2 Chỉ loại bỏ thẻ script

Loại bỏ chuỗi `<script>` bằng biểu thức chính quy không phải biện pháp làm sạch HTML đáng tin cậy. HTML có nhiều cách biểu diễn node và thuộc tính; parser còn chuẩn hóa markup trong quá trình phân tích. Những cấu trúc như event handler, URL, SVG hoặc phần tử nhúng không được xử lý đầy đủ bằng cách xóa một mẫu văn bản.

### 3.3 Tin rằng dữ liệu đã được mã hóa ở một nơi khác

Mã hóa đầu ra phải phù hợp với ngữ cảnh cuối cùng. Chuỗi an toàn để hiển thị như văn bản có thể không an toàn khi được diễn giải thành HTML, thuộc tính, URL hoặc JavaScript. Nếu dữ liệu đã được mã hóa cho một ngữ cảnh rồi lại được giải mã, nối chuỗi hoặc đưa vào ngữ cảnh khác, lớp bảo vệ có thể mất tác dụng.

Với `outerHTML`, câu hỏi cần trả lời là: dữ liệu có được phép trở thành markup không? Nếu không, hãy giữ nó ở dạng văn bản hoặc node DOM.

## 4. Đọc `outerHTML` cũng cần có chủ đích

Đọc `outerHTML` không tự phân tích lại chuỗi và không tự tạo ra XSS. Tuy nhiên, kết quả là một chuỗi HTML có thể trở thành nguồn dữ liệu cho một sink khác nếu được lưu, gửi đi hoặc chèn lại ở nơi khác.

Không nên coi kết quả đọc là dữ liệu đã được làm sạch:

~~~js
const serialized = document.querySelector("#comment").outerHTML;

// Không an toàn nếu serialized hoặc một phần của nó được chèn lại
// vào một HTML sink mà không có bước xử lý phù hợp.
someOtherElement.outerHTML = serialized;
~~~

Một số giới hạn của việc tuần tự hóa:

- Kết quả là biểu diễn HTML của cây DOM tại thời điểm đọc, không phải bản sao nguyên văn của HTML nguồn ban đầu.
- Các thay đổi trong thuộc tính hoặc cấu trúc DOM có thể được phản ánh trong chuỗi; trạng thái runtime như event listener đã đăng ký bằng JavaScript không được tuần tự hóa thành markup.
- Không nên dựa vào `outerHTML` để sao chép trạng thái đầy đủ của một thành phần giao diện.
- Nếu markup chứa dữ liệu nhạy cảm, ghi toàn bộ chuỗi vào log hoặc gửi đến hệ thống theo dõi có thể làm lộ dữ liệu.

Nếu mục đích là lấy nội dung chữ, dùng `textContent`. Nếu cần quan sát cấu trúc DOM để gỡ lỗi, hãy giới hạn dữ liệu được ghi và tránh đưa chuỗi đó trở lại một HTML sink.

## 5. Chọn API an toàn theo mục đích

Cách xử lý tốt nhất thường là không tạo HTML từ chuỗi. Hãy chọn API thể hiện đúng ý định của ứng dụng.

### 5.1 Chỉ cần hiển thị văn bản: dùng `textContent`

~~~js
const heading = document.createElement("h2");
heading.textContent = user.displayName;

const description = document.createElement("p");
description.textContent = user.biography;

const profile = document.createElement("section");
profile.id = "profile";
profile.append(heading, description);

document.querySelector("#profile").replaceWith(profile);
~~~

`textContent` tạo nội dung văn bản. Các ký tự như dấu ngoặc nhọn hoặc chuỗi giống thẻ HTML được hiển thị như chữ, không được parser diễn giải thành node. Đây là lựa chọn phù hợp cho tên, tiêu đề, mô tả thuần văn bản, thông báo lỗi và nội dung người dùng không cần định dạng HTML.

Có thể dùng `insertAdjacentText` hoặc `replaceChildren` với node và chuỗi văn bản tùy cấu trúc cần tạo. Khi truyền chuỗi vào các API nhận `Node` hoặc chuỗi văn bản như `append` và `replaceChildren`, chuỗi được chuyển thành text node thay vì HTML.

### 5.2 Cần cấu trúc giao diện: tạo node và gán thuộc tính riêng

~~~js
function buildProfile(user) {
  const profile = document.createElement("section");
  profile.id = "profile";

  const heading = document.createElement("h2");
  heading.textContent = user.displayName;

  const biography = document.createElement("p");
  biography.textContent = user.biography;

  profile.append(heading, biography);
  return profile;
}

const oldProfile = document.querySelector("#profile");
oldProfile.replaceWith(buildProfile(user));
~~~

Cách này tách cấu trúc khỏi dữ liệu. Dữ liệu văn bản được gán qua `textContent`; thuộc tính được đặt qua các API DOM tương ứng. Hãy dùng danh sách thuộc tính cho phép thay vì nhận tên thuộc tính tùy ý từ dữ liệu đầu vào.

### 5.3 Cần tạo liên kết: kiểm tra URL theo chính sách ứng dụng

Không gán URL không tin cậy vào `href` hoặc `src` mà không kiểm tra. Việc kiểm tra phải xét giao thức và đích đến theo nhu cầu sản phẩm. Ví dụ sau chỉ chấp nhận liên kết HTTPS đến cùng origin:

~~~js
function buildProfileLink(label, rawHref) {
  const link = document.createElement("a");
  link.textContent = label;

  try {
    const url = new URL(rawHref, window.location.origin);

    if (
      url.protocol === "https:" &&
      url.origin === window.location.origin
    ) {
      link.href = url.href;
    }
  } catch {
    // URL không hợp lệ: giữ nội dung dưới dạng văn bản, không tạo href.
  }

  return link;
}
~~~

Nếu sản phẩm cần liên kết đến các domain bên ngoài, hãy xác định allowlist hostname rõ ràng, chỉ chấp nhận các giao thức cần thiết và cân nhắc chính sách cho liên kết mở tab mới. Không dùng kiểm tra chuỗi sơ sài để quyết định một URL có an toàn hay không.

### 5.4 Cần thay thế phần tử: dùng node với `replaceWith`

`replaceWith` nhận các node hoặc chuỗi văn bản. Khi cần thay toàn bộ phần tử, có thể tạo node mới rồi thay phần tử cũ. Điều này giữ cho dữ liệu không tin cậy ở dạng văn bản và tránh đưa chuỗi vào HTML parser.

~~~js
const oldElement = document.querySelector("#status");
const message = document.createElement("p");

message.id = "status";
message.className = "status-message";
message.textContent = serverMessage;

oldElement.replaceWith(message);
~~~

## 6. Khi sản phẩm thật sự cần HTML do người dùng cung cấp

Một số tính năng cần định dạng phong phú, chẳng hạn trình soạn thảo bài viết, bình luận có danh sách hoặc nội dung mô tả hỗ trợ liên kết. Khi đó, ứng dụng phải quyết định rõ HTML nào được phép tồn tại và dùng một bộ làm sạch HTML đã được duy trì, có hiểu biết về parser.

DOMPurify là một lựa chọn phổ biến để làm sạch HTML trong trình duyệt. Cấu hình phải phù hợp với tính năng, và nên giới hạn tag cùng thuộc tính ở mức tối thiểu.

Ví dụ một tính năng chỉ cho phép đoạn văn, nhấn mạnh, danh sách và liên kết:

~~~js
const cleanHtml = DOMPurify.sanitize(untrustedHtml, {
  ALLOWED_TAGS: [
    "p", "strong", "em", "ul", "ol", "li", "a", "br"
  ],
  ALLOWED_ATTR: ["href", "title"]
});

target.outerHTML = cleanHtml;
~~~

Ví dụ trên minh họa việc làm sạch trước khi gán. Trong ứng dụng có bật Trusted Types enforcement, setter yêu cầu một giá trị `TrustedHTML`; chuỗi `cleanHtml` thông thường sẽ bị từ chối. Phần tiếp theo trình bày cách kết hợp hai cơ chế.

Khi dùng bộ làm sạch HTML, cần giữ các nguyên tắc sau:

1. Dùng thư viện có parser, được cập nhật thường xuyên và có quy trình theo dõi lỗ hổng.
2. Xác định rõ tập tag, thuộc tính và giao thức được phép cho tính năng. Đừng bật toàn bộ HTML nếu sản phẩm chỉ cần một tập nhỏ.
3. Làm sạch ở ranh giới trước khi đưa dữ liệu vào HTML sink. Không nối thêm chuỗi hoặc thay đổi markup sau bước làm sạch theo cách có thể đưa nội dung nguy hiểm trở lại.
4. Không dùng bộ làm sạch HTML để thay thế kiểm tra URL, kiểm tra quyền hoặc xác thực dữ liệu nghiệp vụ.
5. Không tái sử dụng kết quả đã làm sạch trong ngữ cảnh khác như JavaScript, CSS hoặc thuộc tính HTML tùy ý. Mỗi ngữ cảnh cần cách xử lý phù hợp.
6. Kiểm thử cấu hình với các trường hợp tag, thuộc tính, URL và markup lồng nhau mà tính năng thực tế có thể nhận.

Bộ làm sạch không nên được viết bằng cách tự xóa các chuỗi đáng ngờ bằng regex. HTML là một ngôn ngữ có quy tắc phân tích phức tạp; một bộ làm sạch cần hiểu cấu trúc mà trình duyệt sẽ tạo ra.

## 7. Dùng Trusted Types để kiểm soát HTML sink

Trusted Types là cơ chế của trình duyệt giúp ứng dụng kiểm soát những API nhạy cảm có thể nhận chuỗi và tạo DOM. Khi được bật bằng CSP, các sink thuộc nhóm được bảo vệ sẽ yêu cầu giá trị có kiểu tin cậy như `TrustedHTML`, thay vì chấp nhận chuỗi thông thường.

Trusted Types không tự làm sạch dữ liệu. Ứng dụng phải tạo policy có trách nhiệm, và policy phải áp dụng bộ làm sạch phù hợp. Một policy chỉ trả lại nguyên đầu vào sẽ vô hiệu hóa mục đích bảo vệ.

Ví dụ kết hợp DOMPurify với policy:

~~~js
const htmlPolicy = trustedTypes.createPolicy("app-html", {
  createHTML(input) {
    return DOMPurify.sanitize(input, {
      ALLOWED_TAGS: [
        "p", "strong", "em", "ul", "ol", "li", "a", "br"
      ],
      ALLOWED_ATTR: ["href", "title"],
      RETURN_TRUSTED_TYPE: false
    });
  }
});

const trustedMarkup = htmlPolicy.createHTML(untrustedHtml);
target.outerHTML = trustedMarkup;
~~~

Trong callback `createHTML`, DOMPurify trả về chuỗi đã làm sạch bằng `RETURN_TRUSTED_TYPE: false`. Chính policy bọc kết quả đó thành `TrustedHTML`. Cách dùng cụ thể cần khớp với phiên bản DOMPurify và môi trường triển khai của ứng dụng.

Có thể yêu cầu trình duyệt thực thi Trusted Types bằng CSP:

~~~http
Content-Security-Policy: require-trusted-types-for 'script'; trusted-types app-html
~~~

Khi chính sách này được hỗ trợ và thực thi, các sink được bảo vệ sẽ từ chối chuỗi thông thường. Chỉ policy có tên được cho phép mới được tạo. Tùy trình duyệt và môi trường, mức hỗ trợ có thể khác nhau; cần kiểm tra ma trận trình duyệt của sản phẩm và theo dõi lỗi enforcement trong console.

Một số nguyên tắc khi thiết kế policy:

- Tạo policy ở một nơi có kiểm soát, không tạo policy tùy tiện tại từng thành phần.
- Đặt tên policy theo chức năng và giới hạn tên được phép trong CSP.
- Dùng bộ làm sạch đã được kiểm thử trong callback.
- Không cung cấp policy kiểu pass-through nhận chuỗi rồi trả nguyên chuỗi.
- Không biến mọi chuỗi thành `TrustedHTML` chỉ để làm lỗi biến mất.
- Theo dõi các sink còn nhận chuỗi và xử lý chúng theo từng luồng dữ liệu.

Nếu ứng dụng cần một default policy để hỗ trợ giai đoạn chuyển đổi, policy đó phải có logic làm sạch thực sự và được giám sát. Không dùng default policy như cách bỏ qua lỗi ở mọi nơi.

## 8. CSP là lớp phòng vệ bổ sung

Content Security Policy giới hạn những nguồn và loại nội dung mà trình duyệt được phép tải hoặc thực thi. CSP có thể giảm tác động của một số lỗi chèn HTML, ví dụ bằng cách hạn chế inline script và nguồn script. Kết hợp `require-trusted-types-for 'script'` có thể giúp chặn chuỗi đi vào các HTML sink được Trusted Types bảo vệ.

CSP vẫn là lớp phòng vệ bổ sung:

- CSP không chứng minh chuỗi HTML đầu vào đã an toàn.
- CSP không thay thế việc dùng `textContent`, DOM API hoặc bộ làm sạch phù hợp.
- Một chính sách quá rộng có thể làm giảm hiệu quả bảo vệ.
- Cần triển khai, kiểm thử và theo dõi chính sách trong bối cảnh ứng dụng thực tế.

Hãy bắt đầu từ chính sách phù hợp với ứng dụng, dùng chế độ báo cáo nếu quy trình triển khai yêu cầu quan sát trước, rồi mới thực thi sau khi đã xử lý các vi phạm hợp lệ. Không thêm ngoại lệ rộng chỉ để một sink không an toàn tiếp tục hoạt động.

## 9. Framework và mã DOM trực tiếp

Các framework giao diện thường cung cấp cơ chế escape dữ liệu khi render văn bản. Nhưng cơ chế đó chỉ áp dụng trong phạm vi API mà framework quản lý.

Ví dụ, React có `dangerouslySetInnerHTML`, Vue có `v-html`, và các framework khác cũng có API tương tự để chèn HTML. Những API này cần được xem như HTML sink và chỉ nhận nội dung đã được xử lý theo chính sách của ứng dụng.

Gọi `outerHTML` trực tiếp trên node do framework quản lý có thể phá vỡ giả định về quyền sở hữu DOM của framework. Virtual DOM hoặc hệ thống cập nhật của framework có thể tiếp tục nghĩ rằng node cũ vẫn tồn tại, dẫn đến giao diện không nhất quán hoặc lỗi ở lần render tiếp theo.

Nên để framework quản lý vòng đời node của nó. Nếu cần tích hợp thư viện thao tác DOM, hãy dùng điểm tích hợp chính thức như ref hoặc lifecycle hook, và giới hạn vùng DOM mà thư viện được phép quản lý. Dù dùng framework nào, dữ liệu không tin cậy vẫn phải được xử lý đúng trước khi đi vào HTML sink.

## 10. Kiểm thử việc sử dụng `outerHTML`

Kiểm thử cần xác nhận cả hành vi mong muốn và việc dữ liệu không thể biến thành markup ngoài dự kiến.

### 10.1 Kiểm tra hiển thị văn bản

Dùng một chuỗi thử nghiệm có ký tự đặc biệt:

~~~js
const sample = '<img src=x onerror="alert(1)">';

const output = document.createElement("p");
output.textContent = sample;

document.querySelector("#result").replaceChildren(output);
~~~

Kết quả mong đợi: trang hiển thị nguyên chuỗi như văn bản; không tạo phần tử ảnh và không có event handler mới trong DOM.

### 10.2 Kiểm tra HTML được làm sạch

Với tính năng rich text, tạo bộ ca kiểm thử gồm:

- Tag hợp lệ mà tính năng cho phép.
- Tag không nằm trong allowlist.
- Thuộc tính sự kiện như `onerror` và `onclick`.
- URL có giao thức không được phép.
- HTML lồng nhau, markup sai cấu trúc và thuộc tính trùng.
- Các trường hợp có SVG hoặc phần tử nhúng nếu ứng dụng có xử lý những loại nội dung đó.

Kết quả mong đợi phải được định nghĩa theo cấu hình sản phẩm. Không chỉ kiểm tra rằng chuỗi đầu ra khác chuỗi đầu vào; hãy kiểm tra cây DOM cuối cùng và hành vi của nó.

### 10.3 Kiểm tra Trusted Types

Trong trình duyệt hỗ trợ enforcement, bật CSP thử nghiệm và xác nhận:

- Gán một chuỗi thông thường vào `outerHTML` bị từ chối.
- Giá trị do policy đã được phê duyệt tạo ra được chấp nhận.
- Policy không làm sạch hoặc policy không được cho phép không thể được tạo.
- Console và báo cáo CSP ghi nhận đúng sink còn vi phạm.

Khi kiểm thử tự động, có thể kiểm tra node cuối cùng, thuộc tính và trạng thái kết nối của node. Tránh dựa vào việc gọi `alert` làm tín hiệu duy nhất; hành vi này phụ thuộc CSP, môi trường kiểm thử và cách trình duyệt xử lý sự kiện.

### 10.4 Rà soát mã nguồn

Tìm các điểm có khả năng phân tích HTML, sau đó lần ngược nguồn dữ liệu:

~~~text
outerHTML
innerHTML
insertAdjacentHTML
document.write
Range.createContextualFragment
DOMParser.parseFromString
~~~

Với mỗi điểm tìm thấy, ghi nhận:

1. Dữ liệu đến từ đâu?
2. Ai có thể kiểm soát dữ liệu đó?
3. Dữ liệu có được dùng như văn bản hay markup?
4. Có bộ làm sạch hoặc Trusted Types policy nào đứng trước sink?
5. Có thao tác nào sửa chuỗi sau khi làm sạch?
6. Node được tạo có nằm trong vùng DOM do framework quản lý không?
7. Có kiểm thử hồi quy cho trường hợp dữ liệu độc hại không?

Không phải mọi lần dùng `outerHTML` đều là lỗ hổng. Markup tĩnh do ứng dụng kiểm soát và không chứa dữ liệu không tin cậy có thể là trường hợp hợp lệ. Tuy nhiên, vẫn cần hiểu rõ sink, nguồn dữ liệu và cách bảo trì đoạn mã đó.

## 11. Bài thực hành

Thực hiện trong một trang lab cục bộ, không dùng dữ liệu thật hoặc tài khoản thật.

### Bài 1: Quan sát getter và setter

Tạo một phần tử có id `demo` và một nút bấm. Khi bấm nút, đọc `outerHTML` rồi hiển thị kết quả bằng `textContent` trong một vùng log.

Sau đó thay phần tử `demo` bằng một node mới. Kiểm tra `isConnected` của tham chiếu cũ và tìm node mới bằng `document.querySelector`. Ghi lại sự khác nhau giữa tham chiếu JavaScript và cây DOM đang hiển thị.

### Bài 2: So sánh HTML sink và text API

Lấy cùng một chuỗi thử nghiệm có dấu ngoặc nhọn và một thuộc tính sự kiện. Đưa chuỗi vào một phần tử bằng `textContent`; trong một vùng lab riêng, thử gán nó qua `outerHTML`.

Quan sát cây DOM trong DevTools. Ghi nhận chuỗi nào tạo text node, chuỗi nào được parser diễn giải thành element hoặc attribute. Chỉ sử dụng payload vô hại trong môi trường lab.

### Bài 3: Tạo thành phần hồ sơ an toàn

Viết hàm dựng hồ sơ gồm tiêu đề, mô tả và liên kết. Dùng `createElement`, `textContent` và kiểm tra URL theo allowlist. Không nối dữ liệu người dùng vào chuỗi HTML.

Kiểm thử với tên có dấu ngoặc nhọn, mô tả có chuỗi giống thẻ HTML, URL sai định dạng và URL có giao thức không được phép. Xác nhận nội dung vẫn hiển thị như dự kiến và không tạo node ngoài ý muốn.

### Bài 4: Thêm hỗ trợ rich text

Nếu lab có nhu cầu hiển thị rich text, tích hợp DOMPurify với allowlist nhỏ. Tạo các ca kiểm thử cho tag, thuộc tính và URL không được phép. Sau đó bật Trusted Types enforcement trên trình duyệt hỗ trợ và sửa từng sink để chỉ nhận `TrustedHTML` do policy đã phê duyệt tạo ra.

Ghi lại lỗi console trước và sau khi xử lý. Giải thích vì sao Trusted Types không thay thế bộ làm sạch HTML.

## 12. Checklist khi review mã

Trước khi chấp nhận một thay đổi có dùng `outerHTML`, hãy xác nhận:

- [ ] Có lý do rõ ràng để tạo HTML thay vì tạo node DOM hoặc văn bản.
- [ ] Mọi dữ liệu đưa vào markup đều có nguồn gốc và mức độ tin cậy đã được xác định.
- [ ] Dữ liệu thuần văn bản được đưa qua `textContent` hoặc API text tương ứng.
- [ ] HTML rich text được làm sạch bằng thư viện phù hợp và cấu hình allowlist cụ thể.
- [ ] URL và thuộc tính nhạy cảm được kiểm tra theo chính sách riêng.
- [ ] Không có thao tác nối chuỗi hoặc chỉnh sửa nguy hiểm sau bước làm sạch.
- [ ] Trusted Types được bật khi môi trường hỗ trợ, với policy có trách nhiệm.
- [ ] CSP được cấu hình như một lớp phòng vệ bổ sung.
- [ ] Việc thay node không làm hỏng listener, tham chiếu hoặc vòng đời của framework.
- [ ] Có kiểm thử xác nhận cây DOM cuối cùng và hành vi mong muốn.

## 13. Câu hỏi tự kiểm tra

**1. Đọc `outerHTML` và gán `outerHTML` khác nhau thế nào?**

Đọc thuộc tính trả về chuỗi tuần tự hóa của phần tử. Gán thuộc tính yêu cầu trình duyệt phân tích chuỗi HTML và thay thế phần tử đích bằng các node được tạo ra.

**2. Vì sao `outerHTML` setter được gọi là HTML injection sink?**

Vì chuỗi đầu vào được diễn giải thành markup. Nếu dữ liệu không tin cậy điều khiển chuỗi đó, nó có thể tạo node hoặc thuộc tính ngoài dự kiến và dẫn đến DOM XSS.

**3. Vì sao xóa thẻ `<script>` không đủ để làm sạch HTML?**

HTML có nhiều cấu trúc chủ động khác, chẳng hạn thuộc tính sự kiện, URL nguy hiểm và phần tử nhúng. Cách xóa chuỗi không hiểu đầy đủ cách parser tạo DOM.

**4. Khi chỉ cần hiển thị bình luận dạng chữ, nên dùng API nào?**

Dùng `textContent` hoặc API tạo text node. Không cần đưa nội dung qua HTML parser.

**5. DOMPurify và Trusted Types giải quyết hai việc gì?**

DOMPurify làm sạch cấu trúc HTML theo chính sách được cấu hình. Trusted Types kiểm soát việc dữ liệu đi vào các sink được bảo vệ và yêu cầu giá trị được tạo qua policy được tin cậy.

**6. Vì sao policy Trusted Types kiểu pass-through nguy hiểm?**

Vì nó đánh dấu mọi chuỗi là đáng tin mà không kiểm tra hay làm sạch. Điều này loại bỏ hàng rào mà Trusted Types được bật để cung cấp.

**7. Điều gì xảy ra với biến đang tham chiếu đến phần tử sau khi gán `outerHTML`?**

Biến vẫn trỏ đến node cũ đã bị thay khỏi cây DOM. Muốn thao tác node mới, cần lấy lại tham chiếu từ DOM hoặc giữ tham chiếu đến node được tạo.

**8. CSP có thay thế việc làm sạch HTML không?**

Không. CSP có thể giảm khả năng thực thi một số nội dung và Trusted Types có thể chặn chuỗi tại sink được bảo vệ, nhưng ứng dụng vẫn phải chọn API phù hợp và làm sạch HTML khi tính năng thực sự cần markup.

## Ghi nhớ

`outerHTML` là API thao tác DOM hữu ích nhưng setter của nó đưa chuỗi vào bộ phân tích HTML. Hãy ưu tiên văn bản và node DOM được tạo rõ ràng. Chỉ nhận HTML khi sản phẩm thực sự cần định dạng phong phú, và khi đó phải có bộ làm sạch phù hợp, policy Trusted Types có trách nhiệm và kiểm thử trên cây DOM cuối cùng.
