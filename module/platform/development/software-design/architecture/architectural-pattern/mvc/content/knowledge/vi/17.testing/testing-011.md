# Kiểm thử khả năng tiếp cận và bản địa hóa giao diện

Trong module **MODEL_VIEW_CONTROLLER**, View là nơi người dùng tiếp nhận thông tin và gửi tương tác đến Controller. Một giao diện có thể hoạt động đúng với chuột và một ngôn ngữ mặc định nhưng vẫn gây khó khăn cho người dùng bàn phím, trình đọc màn hình, người có thị lực kém hoặc người dùng ở locale khác. Vì vậy, kiểm thử giao diện cần xác nhận cả khả năng tiếp cận (accessibility) lẫn bản địa hóa (localization), từ nội dung HTML do server render đến trạng thái được cập nhật sau mỗi request.

Bài học thuộc chương **Kiểm thử**. Trọng tâm là xây dựng chiến lược kiểm thử cho giao diện MVC theo hai hướng: **khả năng tiếp cận** và **bản địa hóa**. Ta sẽ kiểm tra ngữ nghĩa HTML, điều hướng bàn phím, focus, tương phản, thông báo động và khả năng tương thích với công nghệ hỗ trợ; đồng thời kiểm tra locale, thông điệp, định dạng ngày giờ/số/tiền tệ, số nhiều, ngôn ngữ viết từ phải sang trái, fallback và dữ liệu đầu vào. Các ví dụ sử dụng Java Spring MVC, ResourceBundle và công cụ kiểm thử web.

## 1. Accessibility và localization trong kiểm thử MVC

**Accessibility (a11y)** là khả năng để người dùng có thể nhận biết, hiểu, điều hướng và thao tác với giao diện bằng nhiều cách khác nhau, kể cả khi họ dùng bàn phím, trình đọc màn hình, phóng to nội dung hoặc thiết lập hỗ trợ riêng của hệ điều hành.

**Localization (l10n)** là điều chỉnh giao diện và hành vi cho một ngôn ngữ và vùng văn hóa cụ thể. Công việc này không chỉ dịch câu chữ; nó còn liên quan đến định dạng ngày, số, tiền tệ, múi giờ, cách hiển thị tên, thứ tự sắp xếp, quy tắc số nhiều và hướng chữ.

Hai lĩnh vực có liên hệ chặt chẽ:

- Trình đọc màn hình cần biết ngôn ngữ của trang và những đoạn nội dung đổi ngôn ngữ.
- Thông báo lỗi cần được dịch và gắn đúng với trường nhập để người dùng hiểu được.
- Giao diện RTL có thể làm thay đổi thứ tự thị giác, vị trí biểu tượng và cách điều hướng.
- Nội dung dài hơn sau dịch có thể làm vỡ bố cục, che nút hoặc cắt mất nhãn.
- Ngày giờ và số liệu được định dạng sai có thể khiến người dùng nhập nhầm hoặc đưa ra quyết định sai.

Kiểm thử cả hai giúp giao diện phục vụ được nhiều nhóm người dùng và giảm lỗi khi triển khai ở nhiều thị trường.

### 1.1. Mục tiêu kiểm thử

Một chiến lược tốt cần trả lời các câu hỏi:

1. Người dùng có thể hoàn thành tác vụ chính bằng bàn phím mà không cần chuột không?
2. Trình đọc màn hình có đọc đúng tên, vai trò, trạng thái và thứ tự nội dung không?
3. Lỗi, trạng thái loading và kết quả cập nhật động có được thông báo phù hợp không?
4. Nội dung có đủ tương phản, phóng to và reflow mà không mất chức năng không?
5. Mọi chuỗi hiển thị có được lấy từ nguồn thông điệp đã bản địa hóa không?
6. Ngày, số, tiền tệ và thời gian có được định dạng theo locale và timezone đúng không?
7. Nội dung dài, chữ RTL và ký tự Unicode có làm hỏng bố cục hoặc dữ liệu không?
8. Khi thiếu bản dịch, ứng dụng có fallback rõ ràng và có thể phát hiện không?

## 2. Dùng WCAG làm cơ sở kiểm thử

WCAG tổ chức yêu cầu accessibility theo bốn nguyên tắc **POUR**:

| Nguyên tắc | Ý nghĩa | Ví dụ kiểm thử |
|---|---|---|
| Perceivable – Có thể nhận biết | Thông tin phải được trình bày theo cách người dùng có thể cảm nhận | Alt text, caption, contrast, cấu trúc heading |
| Operable – Có thể thao tác | Thành phần và điều hướng có thể sử dụng | Bàn phím, focus, không keyboard trap |
| Understandable – Có thể hiểu | Nội dung và hành vi dễ dự đoán | Nhãn rõ, thông báo lỗi hữu ích, ngôn ngữ đúng |
| Robust – Tương thích | Nội dung hoạt động với trình duyệt và công nghệ hỗ trợ | HTML ngữ nghĩa, ARIA đúng, tên và vai trò được công bố |

WCAG 2.2 là một phiên bản tiêu chuẩn thường được dùng làm cơ sở thiết kế và kiểm thử. Nhiều sản phẩm chọn mức AA làm mục tiêu. Việc đạt một số kiểm tra tự động không đồng nghĩa toàn bộ giao diện đã phù hợp WCAG; cần kết hợp kiểm tra tự động, kiểm tra thủ công và đánh giá bằng công nghệ hỗ trợ.

### 2.1. Chuyển yêu cầu thành tiêu chí có thể kiểm tra

Không nên ghi test case chung chung như “trang phải accessible”. Hãy chuyển thành hành vi quan sát được:

- Mọi input có label được liên kết bằng for và id, hoặc có accessible name tương đương.
- Khi mở dialog, focus chuyển vào dialog; khi đóng, focus trở lại phần tử đã mở dialog.
- Người dùng có thể tới và kích hoạt mọi chức năng bằng bàn phím.
- Focus đang hoạt động luôn nhìn thấy được và không bị sticky header che khuất.
- Lỗi của trường được liên kết với input và được thông báo khi phù hợp.
- Nội dung có thể reflow ở viewport hẹp hoặc khi zoom mà không mất chức năng.
- Trang khai báo đúng ngôn ngữ mặc định và đánh dấu đoạn văn bản đổi ngôn ngữ.
- Không có chuỗi giao diện chưa dịch trong locale được hỗ trợ.

Mỗi tiêu chí cần xác định phạm vi trang, trạng thái, dữ liệu và cách kiểm chứng.

## 3. Kiểm thử cấu trúc và ngữ nghĩa HTML

HTML ngữ nghĩa giúp trình duyệt và công nghệ hỗ trợ hiểu cấu trúc trang. Ưu tiên phần tử HTML có sẵn trước khi thêm ARIA.

### 3.1. Heading và landmark

Kiểm tra:

- Trang có một heading chính mô tả nội dung, thường là h1.
- Các heading tiếp theo phản ánh cấu trúc phân cấp, không chọn cấp heading chỉ vì kích thước chữ.
- Vùng điều hướng dùng nav với accessible name nếu có nhiều vùng điều hướng.
- Nội dung chính dùng main.
- Vùng header/footer dùng landmark phù hợp.
- Có liên kết bỏ qua điều hướng lặp lại (skip link) để đến nội dung chính.
- Các landmark không bị lồng hoặc đặt tên mơ hồ.

Ví dụ:

~~~html
<a class="skip-link" href="#main-content">Bỏ qua điều hướng</a>

<header>
  <nav aria-label="Điều hướng chính">
    <!-- Các liên kết chính -->
  </nav>
</header>

<main id="main-content">
  <h1>Danh sách sách</h1>
  <section aria-labelledby="filter-title">
    <h2 id="filter-title">Bộ lọc</h2>
    <!-- Form lọc -->
  </section>
</main>
~~~

Trong kiểm thử, không chỉ xác nhận các thẻ tồn tại. Hãy kiểm tra tên landmark có phân biệt được khi trang có nhiều vùng nav hoặc nhiều vùng section được đặt tên.

### 3.2. Link và button phải đúng vai trò

- Dùng a cho điều hướng đến URL hoặc tài nguyên khác.
- Dùng button cho hành động tại trang như mở dialog, gửi form hoặc tải lại.
- Link có tên mô tả đích đến; tránh nhiều link “Xem thêm” không có ngữ cảnh.
- Button có accessible name và trạng thái disabled phù hợp.
- Không dùng div hoặc span làm button giả nếu không tái tạo đầy đủ bàn phím, focus và vai trò.

Ví dụ:

~~~html
<a href="/books/42">Xem chi tiết sách Thiết kế hệ thống</a>
<button type="button">Mở bộ lọc nâng cao</button>
~~~

Tên link có thể được rút gọn trực quan nhưng vẫn cần ngữ cảnh rõ với công nghệ hỗ trợ. Không dùng icon đơn lẻ làm nút nếu thiếu accessible name.

### 3.3. Ảnh và nội dung phi văn bản

Kiểm tra:

- Ảnh mang thông tin có alt text mô tả mục đích hoặc nội dung cần thiết.
- Ảnh trang trí có alt rỗng để trình đọc màn hình bỏ qua.
- Ảnh biểu đồ có phần mô tả dữ liệu tương đương.
- CAPTCHA hoặc nội dung đa phương tiện có phương án thay thế phù hợp.
- Alt text không lặp nguyên văn caption nếu điều đó tạo nội dung đọc trùng không cần thiết.

Ví dụ:

~~~html
<img src="/images/book-cover.jpg" alt="Bìa sách Thiết kế hệ thống, nền xanh" />
<img src="/images/divider.svg" alt="" />
~~~

Alt text không nên nhồi từ khóa hoặc mô tả mọi chi tiết thị giác nếu chúng không có ý nghĩa với tác vụ.

### 3.4. Bảng dữ liệu

Bảng cần có quan hệ tiêu đề và dữ liệu rõ ràng:

~~~html
<table>
  <caption>Danh sách sách đang được mượn</caption>
  <thead>
    <tr>
      <th scope="col">Tên sách</th>
      <th scope="col">Người mượn</th>
      <th scope="col">Ngày trả</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th scope="row">Thiết kế hệ thống</th>
      <td>Nguyễn An</td>
      <td>25/11/2026</td>
    </tr>
  </tbody>
</table>
~~~

Kiểm thử bằng trình đọc màn hình để xác nhận người dùng biết đang ở cột hoặc hàng nào. Với bảng phức tạp có nhiều nhóm tiêu đề, cần cấu trúc header tương ứng thay vì chỉ dựa vào CSS.

## 4. Kiểm thử form và thông báo lỗi có thể tiếp cận

Form là điểm tương tác quan trọng trong MVC. Controller binding và validation tạo ra lỗi; View phải trình bày lỗi sao cho người dùng nhận biết và sửa được.

### 4.1. Label và hướng dẫn

Mỗi input cần nhãn rõ ràng. Placeholder không thay thế label vì nó biến mất khi nhập và thường có tương phản thấp.

~~~html
<label for="email">Địa chỉ email</label>
<input
  id="email"
  name="email"
  type="email"
  autocomplete="email"
  aria-describedby="email-help"
/>
<p id="email-help">Dùng địa chỉ bạn có thể truy cập.</p>
~~~

Kiểm tra:

- Nhãn được liên kết với đúng input.
- Trường bắt buộc được thông báo bằng văn bản và thuộc tính phù hợp.
- Hướng dẫn định dạng xuất hiện trước hoặc gắn với trường.
- autocomplete dùng token đúng khi phù hợp.
- Nhóm radio/checkbox có fieldset và legend khi chúng tạo thành một nhóm.

### 4.2. Gắn lỗi vào đúng trường

Khi server trả validation error, View nên:

- Đánh dấu trường lỗi bằng aria-invalid="true".
- Liên kết thông báo bằng aria-describedby.
- Hiển thị thông báo bằng văn bản, không chỉ đổi màu viền.
- Có bản tóm tắt lỗi ở đầu form nếu form có nhiều trường.
- Cho phép người dùng di chuyển từ bản tóm tắt đến trường tương ứng.
- Giữ lại dữ liệu hợp lệ đã nhập.

Ví dụ:

~~~html
<label for="email">Địa chỉ email</label>
<input
  id="email"
  name="email"
  type="email"
  aria-invalid="true"
  aria-describedby="email-error"
/>
<p id="email-error" class="field-error">
  Vui lòng nhập địa chỉ email hợp lệ.
</p>
~~~

Kiểm thử cả trường hợp nhiều lỗi và lỗi cross-field. Không gắn một thông báo vào một trường không liên quan chỉ vì template dễ triển khai hơn.

### 4.3. Focus sau khi submit lỗi

Với form dài, khi submit thất bại, người dùng bàn phím hoặc screen reader cần biết có lỗi. Có thể:

- Đưa focus đến heading của error summary.
- Dùng liên kết từ summary đến trường lỗi.
- Đưa focus trực tiếp đến trường lỗi đầu tiên nếu đó là hành vi đã được thiết kế.
- Không tự động đưa focus đến từng lỗi liên tiếp.

Kiểm thử xác nhận focus không bị mất về đầu document hoặc rơi vào phần tử không còn tồn tại sau khi server render lại.

### 4.4. Kiểm thử validation theo locale

Thông báo lỗi cần đúng ngôn ngữ và đúng định dạng. Ví dụ, cùng một trường ngày có thể được nhập theo thứ tự ngày/tháng/năm ở locale này và tháng/ngày/năm ở locale khác. Không chỉ đổi cách hiển thị; server cần parse theo hợp đồng đã định nghĩa và trả lỗi nhất quán.

Không nên dùng chuỗi hiển thị đã dịch để xác định logic. Hãy dùng error code ổn định như EMAIL_INVALID, rồi ánh xạ sang message theo locale.

## 5. Kiểm thử bàn phím và quản lý focus

Mọi chức năng quan trọng phải có thể thao tác bằng bàn phím. Một vòng kiểm thử cơ bản:

1. Reload trang và không dùng chuột.
2. Nhấn Tab để đi qua các phần tử tương tác.
3. Dùng Shift+Tab để đi ngược.
4. Dùng Enter để kích hoạt link và button theo đúng vai trò.
5. Dùng Space cho button và checkbox theo hành vi chuẩn.
6. Dùng phím mũi tên trong nhóm điều khiển có hỗ trợ như radio group hoặc menu đúng chuẩn.
7. Mở và đóng dialog, menu, popover.
8. Kiểm tra focus sau khi submit, điều hướng và cập nhật nội dung.
9. Xác nhận không có keyboard trap.

### 5.1. Focus phải nhìn thấy

Focus indicator cần rõ ràng trên mọi nền. Không xóa outline mặc định nếu không thay bằng chỉ báo đủ rõ. Kiểm tra:

- Focus không bị che bởi header hoặc footer cố định.
- Focus không bị cắt bởi container có overflow hidden.
- Thứ tự focus theo logic đọc và thao tác.
- Phần tử disabled không nhận focus theo hành vi thiết kế.
- Nội dung ẩn không còn nằm trong thứ tự focus.
- Focus không nhảy bất ngờ khi nội dung cập nhật.

### 5.2. Dialog và modal

Một dialog cần:

- Có accessible name, thường thông qua aria-labelledby.
- Có mô tả bổ sung nếu cần.
- Chuyển focus vào vùng dialog khi mở.
- Giữ focus trong dialog nếu modal thực sự khóa tương tác nền.
- Hỗ trợ đóng bằng Escape khi phù hợp.
- Khôi phục focus về phần tử kích hoạt khi đóng.
- Không để nội dung nền tiếp tục nhận tương tác nếu dialog là modal.

Ví dụ:

~~~html
<section
  role="dialog"
  aria-modal="true"
  aria-labelledby="confirm-title"
>
  <h2 id="confirm-title">Xác nhận xóa sách</h2>
  <p>Thao tác này không thể hoàn tác.</p>
  <button type="button">Hủy</button>
  <button type="button">Xóa sách</button>
</section>
~~~

HTML trên chỉ minh họa tên và vai trò. Để tạo modal hoàn chỉnh cần quản lý focus, inert background, phím Escape và khôi phục focus bằng cơ chế UI phù hợp.

### 5.3. Thứ tự focus và thứ tự đọc

Thứ tự Tab cần theo luồng tác vụ. Không dùng tabindex dương để ép thứ tự vì nó tạo thứ tự khó dự đoán. Thông thường chỉ dùng tabindex="0" để đưa một phần tử tùy chỉnh vào thứ tự focus và tabindex="-1" để focus bằng script mà không thêm vào thứ tự Tab.

Kiểm thử thứ tự đọc bằng screen reader vì thứ tự DOM và thứ tự CSS có thể khác nhau. Không dùng CSS order để tạo một trình tự thị giác trái ngược hoàn toàn với luồng nội dung nếu điều đó làm người dùng công nghệ hỗ trợ khó hiểu.

## 6. Tương phản, zoom và reflow

### 6.1. Tương phản màu

Một số ngưỡng WCAG thường được dùng ở mức AA:

| Thành phần | Tỷ lệ tương phản tối thiểu thường áp dụng |
|---|---:|
| Văn bản thông thường | 4.5:1 |
| Văn bản lớn | 3:1 |
| Thành phần giao diện và đồ họa cần thiết để nhận biết | 3:1 so với màu liền kề |

Văn bản lớn thường được hiểu theo tiêu chí WCAG như cỡ ít nhất 18 pt thông thường hoặc 14 pt đậm. Cần dùng công cụ đo contrast trên màu thực tế sau khi CSS, opacity và trạng thái hover/focus được áp dụng.

Không chỉ kiểm tra màu chữ trên nền mặc định. Hãy kiểm tra placeholder, disabled state, error state, link, icon có ý nghĩa, focus ring và các thành phần trong dark mode.

### 6.2. Không dùng màu làm tín hiệu duy nhất

Một trường lỗi không nên chỉ có viền đỏ. Cần thêm thông báo văn bản hoặc biểu tượng có nhãn. Biểu đồ không nên chỉ phân biệt series bằng màu; có thể thêm nhãn, kiểu đường hoặc pattern.

Kiểm thử trong grayscale hoặc chế độ tương phản cao giúp phát hiện tín hiệu chỉ dựa vào màu.

### 6.3. Zoom và reflow

Kiểm tra:

- Zoom trình duyệt đến 200% mà không mất nội dung hoặc chức năng.
- Với nội dung thông thường, reflow ở viewport tương đương 320 CSS px không buộc người dùng cuộn ngang hai chiều, ngoại trừ nội dung cần bố cục hai chiều như bảng dữ liệu hoặc bản đồ.
- Text không bị cắt bởi fixed height.
- Button, dialog và menu vẫn sử dụng được khi chữ phóng to.
- Nội dung không chồng lấn khi font người dùng lớn hơn.
- Không khóa zoom bằng viewport meta.

WCAG có tiêu chí riêng cho reflow và text resize; cần kiểm tra theo loại nội dung thay vì áp dụng máy móc cho mọi bảng hoặc sơ đồ.

### 6.4. Motion và animation

Tôn trọng thiết lập prefers-reduced-motion cho chuyển động không thiết yếu. Không dùng animation nhấp nháy có thể gây khó chịu hoặc nguy cơ cho người nhạy cảm với chuyển động. Kiểm thử cả trạng thái bật và tắt reduced motion.

## 7. Kiểm thử screen reader và công nghệ hỗ trợ

Automated scan không thể thay thế việc dùng screen reader. Nên chọn một số tổ hợp trình duyệt và công nghệ hỗ trợ phù hợp với người dùng mục tiêu.

Ví dụ ma trận kiểm tra:

| Nền tảng | Công nghệ hỗ trợ gợi ý |
|---|---|
| Windows | NVDA với Firefox hoặc Chrome |
| Windows | JAWS với trình duyệt được tổ chức hỗ trợ |
| macOS/iOS | VoiceOver với Safari |
| Android | TalkBack với Chrome |
| Windows/macOS | Phóng đại màn hình và zoom trình duyệt |

Không nhất thiết mọi lần release đều phải kiểm thử mọi tổ hợp. Hãy xác định tổ hợp đại diện, kiểm tra sâu các luồng trọng yếu và mở rộng ma trận theo mức rủi ro.

### 7.1. Những gì cần nghe và xác nhận

- Tên, vai trò và trạng thái của button, link, checkbox, tab và dialog.
- Heading và landmark có thể điều hướng.
- Form label và mô tả được đọc cùng input.
- Lỗi được thông báo sau submit.
- Trạng thái loading và kết quả bất đồng bộ được thông báo.
- Nội dung ẩn không bị đọc như nội dung đang hiển thị.
- Icon-only control có accessible name.
- Ngôn ngữ được chuyển đúng khi nội dung đổi locale.

### 7.2. Nội dung cập nhật động

Khi danh sách được tải bằng AJAX/fetch, người dùng screen reader cần được thông báo phù hợp. Có thể dùng role="status" hoặc aria-live="polite" cho cập nhật không khẩn cấp; role="alert" phù hợp với lỗi khẩn cần thông báo ngay.

~~~html
<p id="search-status" role="status" aria-live="polite">
  Đang tìm kiếm...
</p>
~~~

Khi request hoàn tất, cập nhật vùng live bằng nội dung như “Tìm thấy 12 kết quả”. Cần tránh cập nhật liên tục khiến screen reader đọc quá nhiều thông báo. Live region nên tồn tại trước khi nội dung được đưa vào để công nghệ hỗ trợ nhận ra thay đổi ổn định hơn.

## 8. Kiểm thử tự động accessibility

Có thể dùng các công cụ sau:

- **axe-core:** phát hiện nhiều lỗi về tên accessible, ARIA, label, contrast và cấu trúc.
- **Lighthouse:** đưa ra một số kiểm tra accessibility trong báo cáo trình duyệt.
- **Pa11y:** chạy kiểm tra tự động trên URL hoặc luồng đã cấu hình.
- **Playwright/Cypress:** điều khiển trình duyệt, kiểm tra DOM, keyboard và tích hợp axe.
- **HTML validator:** phát hiện markup không hợp lệ có thể ảnh hưởng ngữ nghĩa.

Ví dụ Playwright kết hợp axe-core:

~~~typescript
import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("trang danh sách sách không có lỗi accessibility đã phát hiện", async ({ page }) => {
  await page.goto("/books");

  const results = await new AxeBuilder({ page }).analyze();

  expect(results.violations).toEqual([]);
});
~~~

Ví dụ là điểm khởi đầu. Trong ứng dụng thật, cần cấu hình context phù hợp, đăng nhập, dữ liệu test và loại trừ có giải thích nếu có false positive. Không nên thêm exclusion chỉ để pipeline xanh.

### 8.1. Automated test có giới hạn

Công cụ tự động không thể đánh giá đầy đủ:

- Nội dung alt có thực sự hữu ích không.
- Luồng bàn phím có hợp lý với tác vụ không.
- Thông báo screen reader có dễ hiểu không.
- Thứ tự focus có gây mất định hướng không.
- Ngôn ngữ bản dịch có tự nhiên và chính xác không.
- Một dialog có thực sự dễ sử dụng với người dùng công nghệ hỗ trợ không.

Vì vậy, kết quả scan không phải chứng nhận accessibility. Cần manual testing và người dùng thực tế khi sản phẩm có yêu cầu cao.

## 9. Bản địa hóa: locale, language và region

**Language** là ngôn ngữ nội dung; **region** là biến thể theo vùng; **locale** kết hợp quy tắc ngôn ngữ và vùng để định dạng và lựa chọn tài nguyên.

Ví dụ tag locale theo BCP 47:

- vi-VN: tiếng Việt tại Việt Nam.
- en-US: tiếng Anh tại Hoa Kỳ.
- en-GB: tiếng Anh tại Vương quốc Anh.
- fr-FR: tiếng Pháp tại Pháp.
- ar-EG: tiếng Ả Rập tại Ai Cập.

Không suy ra locale chỉ từ địa chỉ IP. IP có thể phản ánh VPN, mạng công ty hoặc vị trí không trùng với ngôn ngữ người dùng muốn dùng. Nên có lựa chọn ngôn ngữ rõ ràng và ghi nhớ preference theo chính sách sản phẩm.

### 9.1. Chọn locale theo thứ tự có chủ đích

Một ứng dụng có thể áp dụng thứ tự:

1. Locale người dùng đã chọn và lưu trong hồ sơ.
2. Locale được chọn rõ ràng trong cookie hoặc session.
3. Accept-Language của trình duyệt cho lần truy cập đầu.
4. Locale mặc định của sản phẩm.

Thứ tự thực tế tùy hợp đồng sản phẩm. Nếu người dùng chủ động chọn tiếng Việt, không nên để header trình duyệt tự đổi lại tiếng Anh ở mỗi request.

### 9.2. Đặt ngôn ngữ cho tài liệu và đoạn nội dung

HTML nên khai báo ngôn ngữ mặc định:

~~~html
<html lang="vi-VN">
~~~

Nếu một đoạn trích dẫn dùng ngôn ngữ khác, đánh dấu riêng:

~~~html
<p lang="en">Please sign in to continue.</p>
~~~

lang giúp trình đọc màn hình chọn cách phát âm phù hợp. Nếu locale thay đổi, View cần render đúng thuộc tính lang, không chỉ đổi nội dung text.

## 10. Externalize thông điệp và tránh ghép chuỗi

Không viết cứng nội dung người dùng nhìn thấy trong Controller hoặc template. Đưa thông điệp vào resource bundle với key có ý nghĩa.

Ví dụ:

~~~properties
# messages_vi.properties
book.list.title=Danh sách sách
book.empty=Chưa có sách phù hợp.
validation.email.invalid=Vui lòng nhập địa chỉ email hợp lệ.
search.result.count=Tìm thấy {0} kết quả.
~~~

~~~properties
# messages_en.properties
book.list.title=Book list
book.empty=No matching books found.
validation.email.invalid=Enter a valid email address.
search.result.count=Found {0} results.
~~~

Tránh ghép câu từ nhiều mảnh:

~~~java
String message = "Tìm thấy " + count + " kết quả";
~~~

Thứ tự từ và cấu trúc câu có thể khác giữa ngôn ngữ. Dùng message format để bản dịch quyết định vị trí tham số.

### 10.1. Key nên ổn định và có ngữ cảnh

Tên key như book.list.title hoặc validation.email.invalid dễ tìm và tái sử dụng. Tránh dùng nguyên câu tiếng Việt làm key vì khi sửa câu chữ sẽ khó theo dõi tham chiếu và bản dịch.

Không dùng một key chung cho các câu giống nhau về chữ nhưng khác ngữ cảnh. Ví dụ “Open” có thể là động từ mở tài liệu hoặc tính từ chỉ trạng thái đang mở; bản dịch có thể khác.

### 10.2. Fallback khi thiếu bản dịch

Xác định rõ locale fallback, ví dụ vi-VN có thể fallback về vi, rồi về locale mặc định của sản phẩm. Thiếu key trong locale chính cần được phát hiện trong CI hoặc test resource completeness.

Không nên để key kỹ thuật như book.list.title xuất hiện trên giao diện production. Fallback có thể giúp hệ thống vẫn hiển thị, nhưng không được che giấu lỗi thiếu bản dịch trong quá trình phát triển.

## 11. Định dạng số, ngày giờ và tiền tệ

Định dạng phải dựa trên locale và loại dữ liệu. Không tự ghép dấu chấm, dấu phẩy hoặc ký hiệu tiền tệ.

### 11.1. Số và phần trăm

Cùng một giá trị có thể được hiển thị khác nhau:

| Locale | Ví dụ số |
|---|---|
| vi-VN | 1.234.567,89 |
| en-US | 1,234,567.89 |
| de-DE | 1.234.567,89 |
| fr-FR | 1 234 567,89 |

Các ví dụ có thể khác theo quy tắc làm tròn và môi trường ICU. Test nên kiểm tra kết quả theo locale đã xác định, không tự giả định dấu phân cách giống nhau.

### 11.2. Ngày và thời gian

Một thời điểm có thể hiển thị theo định dạng ngày khác nhau. Ngoài locale, timezone cũng ảnh hưởng ngày giờ hiển thị.

- Lưu thời điểm tuyệt đối theo chuẩn như Instant khi biểu diễn một thời điểm trên timeline.
- Dùng LocalDate cho ngày lịch không gắn múi giờ, ví dụ ngày sinh hoặc ngày hẹn theo lịch.
- Chuyển sang timezone người dùng khi hiển thị thời điểm.
- Không parse ngày nhập bằng format mặc định của máy chủ.
- Kiểm thử ranh giới ngày khi timezone khác nhau và các thời điểm chuyển DST.

### 11.3. Tiền tệ

Tiền tệ cần cả giá trị và currency code. Không giả định mọi loại tiền có hai chữ số thập phân. Một số currency có số chữ số thập phân khác nhau.

Dùng BigDecimal hoặc kiểu Money có currency; định dạng bằng NumberFormat/Currency hoặc API tương đương. Không dùng double cho số tiền vì sai số nhị phân có thể làm tròn ngoài ý muốn.

### 11.4. Ví dụ Java với NumberFormat

~~~java
NumberFormat numberFormat =
    NumberFormat.getNumberInstance(Locale.forLanguageTag("vi-VN"));

NumberFormat currencyFormat =
    NumberFormat.getCurrencyInstance(Locale.forLanguageTag("vi-VN"));

String number = numberFormat.format(1234567.89);
String amount = currencyFormat.format(new BigDecimal("1250000"));
~~~

Trong code thực tế, truyền Locale từ ngữ cảnh request hoặc user preference thay vì hardcode. Khi định dạng tiền, currency cần được đặt rõ nếu locale mặc định không đủ để xác định currency nghiệp vụ.

## 12. Số nhiều, lựa chọn và thông điệp có tham số

Không phải ngôn ngữ nào cũng dùng số nhiều theo quy tắc tiếng Anh. Câu “1 books” hoặc “2 book” là dấu hiệu đang ghép chuỗi theo mẫu không phù hợp.

Dùng ICU MessageFormat hoặc thư viện message format có hỗ trợ plural/select:

~~~text
{count, plural,
  =0 {Chưa có kết quả}
  one {Có # kết quả}
  other {Có # kết quả}
}
~~~

Các category plural phụ thuộc quy tắc ngôn ngữ; không tự viết một logic chung count == 1 cho mọi locale. Một số ngôn ngữ có nhiều dạng số nhiều hơn singular/plural.

Thông điệp cũng có thể phụ thuộc giới tính ngữ pháp hoặc lựa chọn nội dung. Nếu cần, dùng cơ chế select hoặc message catalog phù hợp thay vì nối các từ trong Controller.

## 13. RTL, Unicode và bố cục theo ngôn ngữ

Một số ngôn ngữ viết từ phải sang trái như tiếng Ả Rập và tiếng Hebrew. Bố cục cần hỗ trợ hướng đọc, thứ tự biểu tượng và đoạn văn có cả chữ RTL lẫn số/chữ Latin.

### 13.1. Hướng văn bản và CSS logical properties

Dùng dir="rtl" ở cấp tài liệu hoặc vùng phù hợp khi locale yêu cầu. Ưu tiên CSS logical properties:

~~~css
.card {
  padding-inline-start: 1rem;
  margin-inline-end: 0.5rem;
  border-inline-start: 2px solid currentColor;
}
~~~

Logical properties thích nghi với hướng viết tốt hơn padding-left/padding-right. Không lật mọi icon một cách máy móc; biểu tượng mũi tên điều hướng có thể cần đảo hướng, còn logo hoặc biểu tượng vật thể có thể giữ nguyên.

### 13.2. Chuỗi hỗn hợp và bidi isolation

Nội dung RTL có thể chứa mã đơn hàng, URL hoặc số điện thoại viết theo hướng LTR. Dùng bdi hoặc dir="auto" ở vùng phù hợp để cô lập hướng hiển thị:

~~~html
<p>
  Mã đơn hàng:
  <bdi>ORD-2026-00125</bdi>
</p>
~~~

Kiểm thử chuỗi trộn chữ Ả Rập, chữ Latin, dấu câu và chữ số để phát hiện dấu câu bị đảo vị trí.

### 13.3. Unicode và độ dài chuỗi

Một ký tự nhìn thấy có thể được tạo từ nhiều code point. Không giả định String.length() luôn bằng số ký tự người dùng cảm nhận. Khi giới hạn tên hoặc nội dung, cần xác định quy tắc theo code point, grapheme cluster hoặc byte tùy yêu cầu.

Kiểm thử:

- Dấu tiếng Việt ở dạng Unicode kết hợp và dựng sẵn.
- Emoji hoặc ký tự ngoài Basic Multilingual Plane.
- Chữ CJK.
- Ký tự có dấu kết hợp.
- Tên rất dài hoặc không có khoảng trắng.
- Văn bản RTL trộn với số và mã định danh.

Không cắt chuỗi theo số UTF-16 code unit nếu có thể làm tách surrogate pair hoặc ký tự kết hợp.

## 14. Cấu hình localization trong Spring MVC

Spring MVC có thể sử dụng MessageSource để phân giải thông điệp theo locale. Một cấu hình đơn giản với ResourceBundle:

~~~java
@Configuration
public class I18nConfig {
    @Bean
    public MessageSource messageSource() {
        var source = new ReloadableResourceBundleMessageSource();
        source.setBasename("classpath:messages");
        source.setDefaultEncoding("UTF-8");
        source.setFallbackToSystemLocale(false);
        return source;
    }
}
~~~

Resource files có thể đặt trong classpath:

~~~text
src/main/resources/
  messages.properties
  messages_vi.properties
  messages_en.properties
  messages_fr.properties
~~~

messages.properties là bundle mặc định. Nếu cần fallback theo chính sách riêng, hãy cấu hình rõ và kiểm thử. Không phụ thuộc locale của máy chạy server vì môi trường production có thể khác máy phát triển.

### 14.1. Lựa chọn locale từ request

Với ứng dụng dùng header Accept-Language, có thể dùng AcceptHeaderLocaleResolver. Cơ chế này phù hợp khi client quyết định locale theo header; resolver này không phải lựa chọn để ghi preference lâu dài từ một nút đổi ngôn ngữ.

Nếu người dùng có thể chọn và lưu locale, dùng cookie/session hoặc hồ sơ người dùng theo chính sách. Ví dụ với cookie:

~~~java
@Bean
public LocaleResolver localeResolver() {
    var resolver = new CookieLocaleResolver();
    resolver.setDefaultLocale(Locale.forLanguageTag("vi-VN"));
    resolver.setCookieName("APP_LOCALE");
    resolver.setCookieMaxAge(Duration.ofDays(365));
    resolver.setCookieHttpOnly(true);
    resolver.setCookieSecure(true);
    resolver.setCookieSameSite("Lax");
    return resolver;
}
~~~

Thuộc tính cấu hình cụ thể có thể khác theo phiên bản Spring Framework. Hãy kiểm tra API của phiên bản dự án trước khi dùng. Cookie locale chỉ là preference; không dùng nó cho xác thực hoặc phân quyền.

### 14.2. MessageSource trong Controller

~~~java
@Controller
@RequestMapping("/books")
public class BookController {
    private final MessageSource messages;

    public BookController(MessageSource messages) {
        this.messages = messages;
    }

    @GetMapping
    public String list(
        Locale locale,
        Model model
    ) {
        String title = messages.getMessage(
            "book.list.title",
            null,
            locale
        );

        model.addAttribute("pageTitle", title);
        return "books/list";
    }
}
~~~

Trong nhiều template engine, message có thể được phân giải trực tiếp trong View. Dù chọn cách nào, giữ logic nghiệp vụ trong service và để message resolution phục vụ phần trình bày.

### 14.3. Test locale trong Spring MVC

Có thể kiểm thử Controller bằng MockMvc và locale cụ thể:

~~~java
@Test
void rendersVietnameseTitle() throws Exception {
    mockMvc.perform(get("/books").locale(Locale.forLanguageTag("vi-VN")))
        .andExpect(status().isOk())
        .andExpect(model().attribute("pageTitle", "Danh sách sách"));
}
~~~

Test này giả định message bundle có key book.list.title với giá trị tiếng Việt. Cần thêm test cho locale khác, fallback, thiếu key và locale được chọn qua cookie/session nếu ứng dụng hỗ trợ.

## 15. Kiểm thử locale và bản dịch ở nhiều lớp

Localization cần kiểm tra ở nhiều điểm của MVC:

| Lớp | Điều cần kiểm thử |
|---|---|
| View | Chuỗi đã dịch, thuộc tính lang/dir, định dạng và bố cục |
| Controller | Locale được nhận đúng và truyền đến View/response |
| Application Service | Không ghép câu hiển thị hoặc phụ thuộc locale nếu nghiệp vụ không cần |
| MessageSource | Key có đủ ở locale hỗ trợ và fallback đúng |
| API | Hợp đồng locale, message code và Content-Language nếu có |
| Persistence | Lưu dữ liệu trung lập locale; không lưu chuỗi đã format thay cho giá trị chuẩn |

### 15.1. Kiểm thử completeness của resource bundle

Tạo test hoặc script kiểm tra:

- Mọi key trong bundle mặc định có ở các locale bắt buộc.
- Không có key bị dùng nhưng không tồn tại.
- Không có placeholder bị thiếu hoặc sai tên.
- Message format parse được.
- Không có chuỗi mặc định vô tình để lộ key nội bộ.
- Không có bản dịch rỗng cho thông điệp quan trọng.

Có thể cho phép một số locale fallback có chủ đích, nhưng danh sách đó phải rõ ràng. Không để thiếu bản dịch chỉ được phát hiện sau khi người dùng thấy key trên giao diện.

### 15.2. Pseudo-localization

Pseudo-localization thay chuỗi bằng phiên bản giả lập có ký tự mở rộng, dấu ngoặc hoặc độ dài tăng lên. Ví dụ:

~~~text
Danh sách sách
→ [!! Đåñh šáçh šáçh ——— !!]
~~~

Mục tiêu là phát hiện:

- Text bị cắt.
- Nút không đủ rộng.
- Layout không hỗ trợ chuỗi dài.
- Chuỗi hardcode chưa được externalize.
- Ký tự Unicode không hiển thị đúng.
- Bố cục RTL chưa được xử lý.

Pseudo-localization hữu ích trong CI hoặc môi trường QA, nhưng không thay thế review ngôn ngữ của người dịch.

### 15.3. Kiểm thử định dạng theo locale

Dùng bộ dữ liệu đại diện:

- Số nguyên, số thập phân, số âm và giá trị lớn.
- Phần trăm và tiền tệ có số chữ số thập phân khác nhau.
- Ngày đầu/cuối tháng, năm nhuận.
- Thời điểm gần nửa đêm khi đổi timezone.
- Thời điểm chuyển DST ở vùng có áp dụng.
- Ngày không hợp lệ và chuỗi nhập sai locale.
- Plural count: 0, 1, 2 và các giá trị đặc biệt theo locale.

Không chỉ so sánh screenshot. Hãy kiểm tra giá trị format, timezone, locale và hành vi parse có chủ đích.

## 16. Ma trận kiểm thử đề xuất

Không phải mọi trang cần toàn bộ tổ hợp locale, trình duyệt và công nghệ hỗ trợ. Có thể xây dựng ma trận theo mức rủi ro.

| Nhóm | Kiểm tra cơ bản | Kiểm tra chuyên sâu |
|---|---|---|
| Tất cả trang | Heading, landmark, title, lang, keyboard | Screen reader và focus order |
| Form quan trọng | Label, required, lỗi, giữ dữ liệu | Keyboard-only, screen reader, locale validation |
| Dashboard | Contrast, chart text alternative, empty/error | Zoom, high contrast, live update |
| Trang nhiều nội dung | Reflow, heading structure, link names | 200–400% zoom, long translated strings |
| Locale mặc định | Message bundle, date/number format | Pseudo-localization và screenshot |
| Locale RTL | dir, logical CSS, text direction | Mixed bidi content, focus and icon direction |
| Luồng xác thực | Label, error, timeout message | Screen reader, keyboard, localization |
| Luồng thanh toán | Currency, confirmation, error | Locale/currency/timezone và accessibility end-to-end |

### 16.1. Phân tầng kiểm thử

- **Unit test:** message formatting, date/number formatter, locale selection policy, validator.
- **Controller test:** locale request, model attribute, error message, response header.
- **Template/integration test:** lang/dir, label association, error summary, rendered message.
- **Automated browser test:** axe scan, keyboard sequence, responsive/reflow, locale switch.
- **Manual accessibility test:** screen reader, keyboard-only, zoom, high contrast.
- **Localization review:** người thông thạo ngôn ngữ kiểm tra ngữ nghĩa, văn phong và thuật ngữ.
- **Visual regression:** so sánh bố cục ở locale có chuỗi dài và RTL, nhưng phải review sai khác có ngữ cảnh.

### 16.2. Chọn luồng end-to-end trọng yếu

Ví dụ luồng đăng ký thành viên:

1. Mở form bằng locale tiếng Việt.
2. Dùng bàn phím đi qua các trường.
3. Submit với email sai để kiểm tra lỗi và focus.
4. Đổi sang tiếng Anh và xác nhận label/error đã đổi.
5. Nhập ngày theo format được công bố.
6. Submit thành công và kiểm tra thông báo kết quả.
7. Dùng screen reader xác nhận heading, label, trạng thái và thông báo.
8. Reload và xác nhận locale preference được giữ theo thiết kế.

Luồng này kiểm tra cùng lúc View, Controller binding, validation, message resolution và trạng thái sau submit.

## 17. Các lỗi thường gặp khi kiểm thử accessibility và localization

| Dấu hiệu | Hệ quả | Cách cải thiện |
|---|---|---|
| Chỉ chạy Lighthouse rồi kết luận đạt accessibility | Bỏ sót lỗi bàn phím, nội dung và screen reader | Kết hợp automated scan và manual test |
| Dùng placeholder thay label | Người dùng mất ngữ cảnh khi nhập | Dùng label liên kết với input |
| Xóa outline focus | Người dùng bàn phím không biết vị trí hiện tại | Thiết kế focus indicator rõ |
| Dùng div làm button | Thiếu keyboard và semantics | Dùng button/link đúng vai trò |
| Chỉ báo lỗi bằng màu đỏ | Không đủ thông tin với nhiều người dùng | Thêm text và liên kết lỗi |
| Không quản lý focus trong modal | Người dùng bị lạc khỏi dialog | Focus trap hợp lý và restore focus |
| Ghép câu từ các mảnh chuỗi | Câu sai trật tự ở locale khác | Dùng message format đầy đủ |
| Hardcode ngày và tiền tệ | Hiển thị sai theo vùng | Dùng locale-aware formatter |
| Chỉ test tiếng Việt | Bỏ sót lỗi khi chuỗi dài hoặc RTL | Test nhiều locale và pseudo-localization |
| Dùng locale máy chủ làm locale người dùng | Môi trường khác nhau cho kết quả khác | Truyền locale rõ ràng theo request/user |
| Thiếu fallback hoặc key dịch | Lộ key nội bộ trên giao diện | Kiểm tra resource completeness trong CI |
| Không khai báo lang | Screen reader phát âm sai | Đặt lang ở html và đoạn đổi ngôn ngữ |
| Dùng left/right cố định cho layout RTL | Bố cục bị đảo sai | Dùng CSS logical properties |
| Cắt chuỗi theo độ dài UTF-16 | Hỏng emoji hoặc ký tự kết hợp | Xác định giới hạn theo grapheme/code point |
| Chỉ kiểm tra screenshot | Không xác nhận semantics và hành vi | Bổ sung DOM, keyboard và screen reader test |

## 18. Checklist kiểm thử trước khi phát hành

### Accessibility

- [ ] Heading, landmark, label và cấu trúc bảng có ngữ nghĩa.
- [ ] Link và button dùng đúng vai trò và có accessible name.
- [ ] Ảnh thông tin có alt phù hợp; ảnh trang trí được bỏ qua.
- [ ] Mọi tác vụ quan trọng thực hiện được bằng bàn phím.
- [ ] Focus nhìn thấy, theo thứ tự hợp lý và không bị che.
- [ ] Dialog quản lý focus và khôi phục focus đúng.
- [ ] Form error được liên kết với trường và có summary khi cần.
- [ ] Loading, kết quả và lỗi động được thông báo phù hợp.
- [ ] Contrast, zoom, reflow và reduced motion được kiểm tra.
- [ ] Có kiểm tra thủ công bằng screen reader trên tổ hợp hỗ trợ đại diện.

### Localization

- [ ] Chuỗi giao diện được externalize vào resource bundle.
- [ ] Mọi locale được hỗ trợ có đủ key và placeholder.
- [ ] Locale được chọn theo chính sách rõ ràng và có thể ghi nhớ.
- [ ] HTML khai báo lang và dir phù hợp.
- [ ] Ngày, giờ, số, phần trăm và tiền tệ dùng formatter theo locale.
- [ ] Timezone và DST được xử lý đúng với dữ liệu thời điểm.
- [ ] Plural/select dùng quy tắc của ngôn ngữ.
- [ ] Nội dung RTL và chuỗi bidi hỗn hợp hiển thị đúng.
- [ ] Chuỗi dài, Unicode, emoji và ký tự kết hợp được kiểm thử.
- [ ] Fallback locale hoạt động và thiếu key được phát hiện trong CI.
- [ ] Pseudo-localization và review ngôn ngữ được thực hiện.

Kiểm thử accessibility và localization không phải một bước trang trí sau khi giao diện đã hoàn tất. Chúng xác nhận rằng View thực sự có thể được nhận biết, điều hướng và hiểu trong những điều kiện sử dụng khác nhau; Controller và tầng ứng dụng truyền đúng locale, lỗi và dữ liệu; còn nội dung hiển thị phù hợp với ngôn ngữ và vùng của người dùng. Khi được đưa vào tiêu chí chấp nhận và pipeline kiểm thử từ sớm, các vấn đề về ngữ nghĩa, focus, bản dịch, định dạng và bố cục sẽ được phát hiện trước khi đến tay người dùng.
