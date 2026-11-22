# Giữ trạng thái biểu mẫu, bộ lọc và lựa chọn hiện tại

Trong ứng dụng web theo kiến trúc **MODEL_VIEW_CONTROLLER (MVC)**, người dùng thường thực hiện một chuỗi thao tác thay vì chỉ mở một trang rồi rời đi. Họ có thể điền biểu mẫu qua nhiều bước, lọc danh sách, chuyển trang, mở một tab nội dung, chọn một mục hoặc quay lại màn hình trước đó. Để trải nghiệm không bị mất ngữ cảnh, ứng dụng cần quyết định trạng thái nào phải được giữ, giữ ở đâu, trong bao lâu và khôi phục như thế nào.

**Trạng thái biểu mẫu, bộ lọc và lựa chọn hiện tại** là những dạng trạng thái tương tác thường gặp. Chúng thường phục vụ một người dùng hoặc một ngữ cảnh màn hình, có vòng đời ngắn hơn dữ liệu nghiệp vụ. Ví dụ, từ khóa tìm kiếm và trang hiện tại có thể nằm trong URL; dữ liệu form đang nhập có thể nằm trong request hoặc session tạm thời; tab đang chọn có thể được khôi phục từ query parameter hoặc bộ nhớ trình duyệt.

Không có một nơi lưu phù hợp cho mọi trạng thái. Lựa chọn đúng phụ thuộc vào việc người dùng có cần chia sẻ/bookmark trạng thái đó không, dữ liệu có nhạy cảm không, có cần tồn tại qua nhiều request hay nhiều thiết bị không và trạng thái có ảnh hưởng đến nghiệp vụ hay không.

## 1. Trạng thái tương tác là gì?

Trạng thái tương tác (interaction state) mô tả ngữ cảnh hiện tại của người dùng khi làm việc với giao diện. Nó có thể bao gồm:

- Các giá trị đã nhập trong biểu mẫu nhưng chưa được lưu.
- Các lỗi validation cần hiển thị để người dùng sửa.
- Từ khóa tìm kiếm, bộ lọc, thứ tự sắp xếp và số trang.
- Tab, mục accordion hoặc vùng nội dung đang được chọn/mở.
- Mục đang được chọn trong bảng hoặc danh sách.
- Bước hiện tại của wizard nhiều bước.
- Thông báo tạm thời sau một thao tác.
- Trạng thái giao diện như đang tải, đang chỉnh sửa hoặc đang xác nhận hộp thoại.

Những dữ liệu này cùng xuất hiện với dữ liệu nghiệp vụ trên trang nhưng không nhất thiết thuộc về đối tượng nghiệp vụ. Ví dụ, một đơn hàng có trạng thái `CONFIRMED` là dữ liệu nghiệp vụ. Người dùng đang mở tab `HISTORY`, lọc theo tháng 11 và đứng ở trang 3 là trạng thái tương tác.

### Phân biệt ba nhóm trạng thái

| Nhóm | Ý nghĩa | Ví dụ | Nguồn có thẩm quyền thường gặp |
|---|---|---|---|
| Trạng thái nghiệp vụ | Sự thật và vòng đời của đối tượng trong hệ thống | Đơn hàng đã thanh toán | Domain Model và kho lưu trữ phía máy chủ |
| Trạng thái tương tác | Ngữ cảnh làm việc của người dùng | Bộ lọc, tab, bước form | URL, request, session hoặc browser state |
| Trạng thái trình bày tức thời | Trạng thái phục vụ phản hồi giao diện | Spinner, focus, dialog đang mở | Bộ nhớ UI phía client |

Ranh giới này giúp tránh lưu các lựa chọn giao diện vào entity nghiệp vụ. Nó cũng nhắc rằng dữ liệu nằm ở trình duyệt không thể được dùng làm bằng chứng về quyền truy cập, giá tiền hoặc trạng thái thật của đối tượng.

## 2. Vòng đời của trạng thái

Trước khi chọn nơi lưu, hãy xác định trạng thái cần tồn tại trong bao lâu và trong phạm vi nào.

| Vòng đời | Ví dụ | Câu hỏi cần trả lời |
|---|---|---|
| Trong một lần render | Spinner, hover, focus | Có cần lưu qua lần cập nhật DOM không? |
| Trong một lần tương tác | Tab đang mở, dialog | Khi đóng hoặc điều hướng thì có khôi phục không? |
| Trong một request | Dữ liệu POST vừa nhận | Nếu validation lỗi, dữ liệu nào cần trả lại? |
| Qua một lần redirect | Thông báo thành công hoặc lỗi | Có cần flash message cho GET tiếp theo không? |
| Trong một tab trình duyệt | Wizard đang điền dở | Refresh có cần giữ tiến độ không? |
| Qua nhiều tab trong cùng trình duyệt | Bộ lọc hoặc lựa chọn gần đây | Các tab có cần độc lập không? |
| Qua nhiều phiên đăng nhập | Tùy chọn giao diện | Có cần lưu trong hồ sơ người dùng không? |
| Qua nhiều người dùng/thiết bị | Trạng thái nghiệp vụ được chia sẻ | Có phải dữ liệu nghiệp vụ trong backend không? |

Một trạng thái có thể thay đổi vòng đời khi yêu cầu sản phẩm thay đổi. Ví dụ, bộ lọc danh sách ban đầu chỉ tồn tại trong component; sau đó sản phẩm yêu cầu người dùng chia sẻ URL để đồng nghiệp mở đúng danh sách. Khi ấy, query parameter trở thành lựa chọn phù hợp hơn.

## 3. Chọn nơi lưu trạng thái

Các nơi lưu phổ biến trong ứng dụng web có đặc tính khác nhau.

| Nơi lưu | Phạm vi và vòng đời | Phù hợp với | Hạn chế cần lưu ý |
|---|---|---|---|
| URL path/query | Có thể bookmark, chia sẻ và dùng Back/Forward | Bộ lọc, tìm kiếm, phân trang, tab có thể chia sẻ | Không đưa dữ liệu nhạy cảm; URL có thể vào history/log/referrer |
| Request parameters/body | Một request | Dữ liệu form vừa gửi, tiêu chí truy vấn | Không tự tồn tại qua request tiếp theo |
| Flash attributes | Thường qua một lần redirect | Thông báo sau POST | Không phù hợp với dữ liệu lớn hoặc nhiều bước kéo dài |
| Session phía server | Nhiều request trong một phiên | Wizard ngắn, dữ liệu tạm cần giữ giữa các bước | Có thể xung đột giữa nhiều tab, hết hạn và tăng bộ nhớ |
| Cookie | Gửi theo request đến phạm vi domain/path | Một số tùy chọn nhỏ hoặc định danh session | Giới hạn kích thước, gửi kèm request, cần thuộc tính bảo mật |
| `sessionStorage` | Theo tab và origin, đến khi tab/window đóng | Bản nháp tạm của một tab, trạng thái wizard | Không chia sẻ giữa tab; có thể mất khi đóng tab |
| `localStorage` | Theo origin, tồn tại qua lần mở trình duyệt | Tùy chọn không nhạy cảm như chế độ hiển thị | JavaScript cùng origin đọc được; không có expiry tự động |
| IndexedDB | Kho dữ liệu phía client, có thể lưu lượng lớn hơn | Bản nháp/offline data theo yêu cầu | Phức tạp hơn, vẫn nằm trong vùng client không đáng tin cậy |
| Database/hồ sơ người dùng | Bền vững phía server | Tùy chọn hoặc bản nháp cần đồng bộ nhiều thiết bị | Cần quyền truy cập, cleanup và chính sách lưu trữ |

Không chọn nơi lưu chỉ vì API dễ dùng. Hãy xét ý nghĩa, độ nhạy cảm, khả năng chia sẻ, yêu cầu khôi phục và rủi ro đồng bộ.

## 4. Giữ bộ lọc, tìm kiếm và phân trang trong URL

Bộ lọc và phân trang thường là trạng thái mà người dùng muốn chia sẻ hoặc quay lại. URL query parameter phù hợp vì nó cho phép:

- Bookmark danh sách theo đúng điều kiện lọc.
- Copy URL gửi cho đồng nghiệp.
- Refresh mà không mất bộ lọc.
- Dùng Back/Forward để quay lại điều kiện xem trước đó.
- Mở trực tiếp một trang kết quả mà không cần khôi phục session riêng.

Ví dụ:

```text
/orders?status=PAID&from=2026-11-01&to=2026-11-30&sort=createdAt,desc&page=2&size=25
```

Controller nhận query parameter, kiểm tra và chuyển thành đối tượng tiêu chí tìm kiếm:

```java
public record OrderSearchCriteria(
        OrderStatus status,
        LocalDate from,
        LocalDate to,
        String sort,
        int page,
        int size
) {}
```

Một query service có thể nhận criteria, kiểm tra giới hạn và truy vấn dữ liệu. ViewModel trả về danh sách, tổng số trang và các giá trị bộ lọc hiện tại để View render lại form.

### Kiểm tra và chuẩn hóa query parameter

Không tin query parameter chỉ vì nó nằm trong URL. Người dùng có thể sửa `page=-100`, `size=1000000`, `sort=unknown` hoặc ngày bắt đầu sau ngày kết thúc.

Server nên:

- Chuyển đổi kiểu và xử lý giá trị không parse được.
- Áp dụng giá trị mặc định rõ ràng.
- Giới hạn page và size trong khoảng hợp lý.
- Allowlist trường và chiều sắp xếp được phép.
- Kiểm tra quan hệ giữa các điều kiện, ví dụ `from` không sau `to`.
- Áp dụng authorization vào dữ liệu truy vấn; bộ lọc không được mở rộng phạm vi người dùng được xem.

Ví dụ, chỉ cho phép sắp xếp theo `createdAt`, `total` hoặc `orderNumber`; không nối trực tiếp chuỗi `sort` từ URL vào SQL. Dùng mapping sang thuộc tính/query expression đã định nghĩa.

### Giữ bộ lọc khi chuyển trang

Khi người dùng chuyển từ trang 2 sang trang 3, URL mới cần giữ lại các filter và sort hiện tại. View có thể tạo link dựa trên criteria đã được chuẩn hóa. Nếu filter thay đổi, thường đặt page về 0 hoặc 1 để tránh trang hiện tại vượt khỏi số trang còn lại.

```text
/orders?status=PAID&sort=createdAt,desc&page=3&size=25
```

Khi người dùng xóa bộ lọc, hãy xóa query parameter tương ứng và khôi phục giá trị mặc định. Tránh tạo URL có nhiều tham số trùng lặp hoặc giữ lại filter cũ không còn áp dụng.

## 5. Giữ tab và lựa chọn hiện tại

Không phải mọi trạng thái giao diện đều cần lưu. Hãy chọn cách phù hợp với ý nghĩa của lựa chọn:

- **Tab có thể chia sẻ hoặc bookmark:** dùng query parameter như `?tab=history`.
- **Tab chỉ phục vụ tạm thời trong component:** giữ trong state phía client.
- **Tab cần khôi phục sau refresh trong cùng tab:** có thể dùng `sessionStorage`.
- **Tab mặc định của người dùng qua nhiều phiên:** có thể lưu trong profile nếu đó là tùy chọn sản phẩm.

Ví dụ URL:

```text
/orders/42?tab=history
```

Server cần kiểm tra tab nằm trong danh sách cho phép, sau đó ViewModel chứa tab đang chọn. Nếu tab không hợp lệ, có thể dùng tab mặc định hoặc trả lỗi điều hướng phù hợp.

### Lựa chọn trong danh sách

Trạng thái một hàng đang được chọn có thể chỉ tồn tại trong bộ nhớ giao diện. Nhưng nếu người dùng muốn chia sẻ một lựa chọn hoặc mở lại cùng đối tượng, URL như `/orders/42` thường có ý nghĩa hơn.

Không lưu một danh sách ID được chọn trong `localStorage` rồi xem nó là bằng chứng người dùng có quyền truy cập. Khi cần tải các mục đã chọn, server phải kiểm tra quyền trên từng ID. Nếu một số mục đã bị xóa hoặc quyền đã thay đổi, giao diện cần xử lý kết quả không còn hợp lệ.

## 6. Giữ dữ liệu biểu mẫu khi validation thất bại

Với form server-rendered, cách đơn giản nhất là trả lại cùng View trong response POST khi binding hoặc validation thất bại. Controller giữ Form Object và BindingResult để template hiển thị giá trị cùng lỗi.

```java
@PostMapping("/profile")
String updateProfile(
        @Valid @ModelAttribute("form") UpdateProfileForm form,
        BindingResult errors,
        Model model) {

    if (errors.hasErrors()) {
        model.addAttribute("formOptions", queryService.getFormOptions());
        return "profile/edit";
    }

    profileService.update(form);
    return "redirect:/profile";
}
```

Ví dụ dùng Spring MVC. Khi render lại form, cần nạp lại các lựa chọn phụ trợ như danh sách quốc gia, tỉnh/thành hoặc loại tài khoản; nếu thiếu, template có thể không hiển thị đầy đủ. Dữ liệu nhập hợp lệ nên được giữ để người dùng chỉ sửa trường lỗi.

Không giữ lại mật khẩu, mã OTP, token bí mật hoặc dữ liệu nhạy cảm trong response lỗi. Các trường đó cần được để trống sau khi trả form.

### Form nhiều bước (wizard)

Với form nhiều bước, dữ liệu có thể chưa đủ để tạo Domain Object hoàn chỉnh. Có thể dùng một form state hoặc draft tạm thời:

```java
public record RegistrationDraft(
        String displayName,
        String email,
        String selectedPlan,
        int currentStep
) {}
```

Ở mỗi bước, server kiểm tra những điều kiện phù hợp với bước đó. Chỉ khi người dùng hoàn tất quy trình và server xác nhận toàn bộ dữ liệu, ứng dụng mới tạo đối tượng nghiệp vụ cuối cùng.

Nếu lưu draft trong session, cần xác định khóa riêng cho mỗi quy trình hoặc mỗi tab. Nếu chỉ lưu một biến `registrationDraft` trong session, mở hai wizard ở hai tab có thể khiến dữ liệu tab này ghi đè tab kia.

Với wizard dài hoặc cần tiếp tục trên thiết bị khác, một bản nháp phía server có định danh riêng và quyền truy cập rõ ràng có thể phù hợp hơn session. Bản nháp cần expiry và quy tắc xóa dữ liệu chưa hoàn tất.

## 7. Flash state sau redirect

Sau thao tác POST thành công, ứng dụng thường dùng Post/Redirect/Get để tránh refresh gửi lại POST. Một thông báo như “Đã lưu thay đổi” có thể được giữ qua một lần redirect bằng flash attribute.

```java
redirectAttributes.addFlashAttribute(
        "notice", "Hồ sơ đã được cập nhật.");
return "redirect:/profile";
```

Flash attribute phù hợp với thông báo ngắn cần hiển thị ở request GET kế tiếp. Nó không phải nơi lưu bản nháp lâu dài, dữ liệu form lớn hoặc trạng thái nghiệp vụ. GET đích vẫn phải truy vấn dữ liệu mới nhất từ server.

Thông báo flash thường chỉ được tiêu thụ một lần. Khi người dùng mở nhiều tab hoặc nhiều redirect xảy ra gần nhau, hãy kiểm tra thông báo được gắn với đúng URL đích và không chứa dữ liệu nhạy cảm.

## 8. Session phía máy chủ

Session phù hợp khi trạng thái cần đi qua nhiều request nhưng không cần xuất hiện trong URL. Ví dụ, một wizard ngắn có thể giữ dữ liệu tạm ở session cho đến khi hoàn tất.

Tuy nhiên, session có một số giới hạn:

- Nhiều tab cùng dùng một session và có thể ghi đè cùng một key.
- Session có thể hết hạn hoặc bị xóa khi người dùng đăng xuất.
- Dữ liệu session làm tăng bộ nhớ và có thể cần replication trong hệ thống nhiều instance.
- Nếu lưu entity hoặc dữ liệu lớn, session dễ trở nên nặng và lỗi thời.
- Nếu session được serialize để lưu ngoài process, thay đổi class có thể ảnh hưởng tương thích dữ liệu.

### Phân biệt session ID và dữ liệu session

Trình duyệt thường giữ session identifier trong cookie; dữ liệu session có thể nằm phía server. Cookie session cần các thuộc tính bảo mật phù hợp như `HttpOnly`, `Secure` và `SameSite` theo cách ứng dụng xác thực và triển khai. Không đưa toàn bộ dữ liệu form hoặc thông tin bí mật vào cookie tự tạo chỉ vì muốn tránh session store.

Session không phải nguồn sự thật cho đơn hàng, quyền sở hữu hoặc số dư tài khoản. Những dữ liệu đó phải được quản lý bởi tầng nghiệp vụ và kho lưu trữ có thẩm quyền.

## 9. Browser storage: sessionStorage, localStorage và IndexedDB

### sessionStorage

`sessionStorage` được phân vùng theo origin và browsing context/tab. Nó phù hợp với trạng thái tạm thời cần tồn tại qua refresh trong cùng tab, ví dụ tab đang chọn hoặc một bản nháp không nhạy cảm.

```javascript
const key = "orders:list-state";

function saveListState(state) {
  sessionStorage.setItem(key, JSON.stringify(state));
}

function loadListState() {
  const raw = sessionStorage.getItem(key);
  return raw ? JSON.parse(raw) : null;
}
```

Ví dụ cần thêm `try/catch` cho dữ liệu parse lỗi hoặc storage bị chặn, đồng thời kiểm tra schema trước khi sử dụng. Không giả định dữ liệu trong storage luôn đúng phiên bản hoặc có đủ trường.

### localStorage

`localStorage` tồn tại qua nhiều lần mở trình duyệt trong cùng origin cho đến khi bị xóa hoặc bị giới hạn bởi trình duyệt. Nó có thể dùng cho tùy chọn không nhạy cảm như chế độ hiển thị hoặc số dòng mặc định.

```javascript
localStorage.setItem("ui:theme", "dark");
const theme = localStorage.getItem("ui:theme") ?? "light";
```

Không lưu mật khẩu, access token, session secret hoặc dữ liệu nhạy cảm vào localStorage. JavaScript cùng origin có thể đọc nội dung; nếu ứng dụng bị XSS, dữ liệu này có thể bị truy cập. Storage cũng có thể bị người dùng sửa hoặc xóa.

### IndexedDB

IndexedDB phù hợp với dữ liệu phía client có cấu trúc và dung lượng lớn hơn, chẳng hạn bản nháp offline hoặc cache. Tuy nhiên, dữ liệu vẫn thuộc vùng kiểm soát của client. Khi đồng bộ lên server, backend phải kiểm tra lại quyền, tính hợp lệ và xung đột.

### Khi storage không dùng được

Trình duyệt có thể chặn storage trong một số chế độ riêng tư hoặc khi vượt quota. Hãy xử lý ngoại lệ và có fallback hợp lý. Đừng để ứng dụng mất khả năng hoạt động cơ bản chỉ vì không ghi được localStorage.

## 10. Dữ liệu nhạy cảm và bảo mật trạng thái

Trạng thái tương tác có thể chứa dữ liệu do người dùng nhập, vì vậy nơi lưu và cách khôi phục cần được xem xét về bảo mật.

- Không đưa mật khẩu, OTP, token bí mật, số thẻ hoặc dữ liệu nhạy cảm vào URL.
- Không coi hidden input, query parameter, cookie tùy chỉnh hoặc browser storage là dữ liệu đáng tin cậy.
- Khi khôi phục draft phía server, kiểm tra người dùng hiện tại có quyền đọc và tiếp tục draft đó không.
- Áp dụng CSRF protection cho request thay đổi dữ liệu khi dùng cookie/session authentication.
- Escape dữ liệu người dùng khi render lại form để tránh XSS.
- Giới hạn kích thước và thời gian tồn tại của dữ liệu tạm.
- Xóa dữ liệu nhạy cảm khi hoàn tất, hủy quy trình hoặc đăng xuất theo chính sách sản phẩm.
- Không đưa dữ liệu riêng tư vào analytics hoặc log URL không cần thiết.

### Hidden field không phải nơi lưu bí mật

Hidden input chỉ ẩn trường khỏi cách nhìn thông thường của giao diện. Người dùng vẫn có thể xem và sửa giá trị bằng developer tools hoặc tạo request trực tiếp.

Ví dụ không nên tin:

```html
<input type="hidden" name="ownerId" value="user-42">
<input type="hidden" name="total" value="100000">
```

Server cần xác định chủ sở hữu từ danh tính đã xác thực và tính tổng tiền từ dữ liệu có thẩm quyền. Hidden field có thể giữ một giá trị điều hướng hoặc version để hỗ trợ trải nghiệm, nhưng server vẫn phải xác minh.

## 11. Nhiều tab và xung đột trạng thái

Một người dùng có thể mở cùng một form trong hai tab. Nếu ứng dụng lưu tất cả dữ liệu wizard vào một key session duy nhất, tab thứ hai có thể ghi đè dữ liệu tab thứ nhất. Tương tự, hai tab có thể cùng chỉnh sửa một đối tượng và lưu các giá trị khác nhau.

Một số cách giảm xung đột:

- Đưa trạng thái có thể chia sẻ vào URL để mỗi tab có ngữ cảnh độc lập.
- Dùng draft ID riêng cho mỗi phiên quy trình thay vì một session key toàn cục.
- Với state phía client, dùng key theo resource/tab và schema version phù hợp.
- Với cập nhật dữ liệu nghiệp vụ, dùng optimistic locking hoặc version để phát hiện ghi đè.
- Khi dữ liệu đã cũ, thông báo cho người dùng và yêu cầu tải lại hoặc hợp nhất thay đổi.
- Không tự động áp dụng draft cũ lên một entity đã thay đổi nếu chưa có quy tắc merge rõ ràng.

Ví dụ, form sửa hồ sơ có thể chứa version `7`. Nếu người dùng mở hai tab, tab A lưu và tạo version `8`; tab B gửi version `7`. Server phát hiện xung đột và trả thông báo phù hợp thay vì âm thầm ghi đè thay đổi của tab A.

## 12. Vòng đời và dọn dẹp trạng thái tạm

Trạng thái tạm nếu không có quy tắc dọn dẹp có thể tích lũy hoặc làm người dùng thấy dữ liệu cũ bất ngờ.

Hãy xác định các sự kiện kết thúc vòng đời:

- Người dùng submit thành công.
- Người dùng hủy form hoặc wizard.
- Draft hết hạn sau một khoảng thời gian.
- Người dùng đăng xuất hoặc phiên hết hạn.
- Tài nguyên gốc bị xóa hoặc quyền truy cập bị thu hồi.
- Người dùng bắt đầu một quy trình mới thay thế quy trình cũ.
- Schema ứng dụng thay đổi khiến dữ liệu lưu cũ không còn tương thích.

Với session, xóa key hoặc draft khi hoàn tất. Với localStorage/sessionStorage, dùng namespace và version để có thể migrate hoặc xóa dữ liệu cũ. Với draft lưu database, đặt `expiresAt`, tạo job cleanup và bảo đảm chỉ chủ thể được phép mới đọc/xóa draft.

Không xóa trạng thái người dùng đang cần chỉ vì component unmount nếu sản phẩm yêu cầu khôi phục khi quay lại. Ngược lại, không giữ dữ liệu vô thời hạn khi nó chứa thông tin cá nhân hoặc quy trình đã kết thúc.

## 13. Ví dụ Spring MVC: giữ filter và trang hiện tại

Giả sử trang danh sách đơn hàng nhận các query parameter `status`, `page` và `size`. Controller có thể chuyển chúng thành criteria đã chuẩn hóa:

```java
@GetMapping("/orders")
String list(
        @RequestParam(required = false) OrderStatus status,
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size,
        Principal principal,
        Model model) {

    int safePage = Math.max(0, page);
    int safeSize = Math.min(Math.max(size, 1), 100);

    OrderSearchCriteria criteria = new OrderSearchCriteria(
            status, safePage, safeSize);

    OrderPageViewModel result =
            orderQueryService.search(criteria, principal.getName());

    model.addAttribute("result", result);
    model.addAttribute("criteria", criteria);
    return "orders/list";
}
```

Ví dụ rút gọn; ứng dụng thực tế cần xử lý giá trị enum không parse được, ngày tháng, sort allowlist và lỗi binding phù hợp. Service/query phải giới hạn dữ liệu theo quyền của người dùng. Không dựa vào `status` trong URL để cấp quyền xem đơn hàng.

View render lại filter và link phân trang từ criteria hiện tại. Khi người dùng chuyển trang, giữ status và size trong URL. Khi thay filter, reset page để tránh trang không còn tồn tại.

## 14. Ví dụ JavaScript: khôi phục trạng thái filter trong một tab

Nếu yêu cầu chỉ là khôi phục lựa chọn hiển thị trong cùng tab sau refresh, có thể dùng `sessionStorage`:

```javascript
const storageKey = "orders-filter:v1";
const form = document.querySelector("#orders-filter");

function readSavedFilter() {
  try {
    const raw = sessionStorage.getItem(storageKey);
    if (!raw) return null;

    const value = JSON.parse(raw);
    if (typeof value.status !== "string") return null;
    if (!Number.isInteger(value.page) || value.page < 0) return null;

    return value;
  } catch {
    return null;
  }
}

function saveFilter() {
  const data = new FormData(form);
  const state = {
    status: String(data.get("status") ?? ""),
    page: Number(data.get("page") ?? 0)
  };

  try {
    sessionStorage.setItem(storageKey, JSON.stringify(state));
  } catch {
    // Storage có thể bị chặn hoặc hết quota; giao diện vẫn tiếp tục hoạt động.
  }
}

form.addEventListener("change", saveFilter);
```

Ví dụ minh họa cách lưu state phía client, chưa bao gồm logic đồng bộ query string hoặc submit form. Nếu filter có thể chia sẻ, URL thường là nguồn khôi phục tốt hơn; không nên vừa để URL vừa để storage cùng điều khiển một giá trị mà không định nghĩa thứ tự ưu tiên.

## 15. Xác định nguồn ưu tiên khi khôi phục

Khi một trạng thái có thể xuất hiện ở nhiều nơi, ứng dụng cần quy định nguồn nào có ưu tiên. Ví dụ, bộ lọc có thể tồn tại trong URL và sessionStorage. Nếu URL có `status=PAID` nhưng storage giữ `status=OPEN`, ứng dụng phải có quy tắc rõ ràng.

Một chính sách thường hợp lý:

1. **URL được ưu tiên** cho trạng thái có thể chia sẻ/bookmark như filter, sort, page và tab.
2. **Request/form submission** là nguồn cho dữ liệu người dùng vừa gửi trong request hiện tại; server xác minh trước khi dùng.
3. **Flash/session tạm thời** chỉ khôi phục dữ liệu ngắn hạn theo luồng đã xác định, ví dụ lỗi qua redirect hoặc wizard draft.
4. **Browser storage** dùng cho tùy chọn hoặc state cục bộ không được định nghĩa trong URL.
5. **Backend** là nguồn có thẩm quyền cho dữ liệu nghiệp vụ và quyền truy cập.

Đây là thứ tự tham khảo, không phải quy tắc bắt buộc cho mọi sản phẩm. Điều quan trọng là không có hai nguồn cùng ghi đè lẫn nhau một cách không xác định.

## 16. Kiểm thử khả năng giữ và khôi phục trạng thái

Kiểm thử nên bao phủ cả trạng thái bình thường, dữ liệu lỗi thời và các ranh giới lưu trữ.

| Cấp kiểm thử | Nội dung cần xác minh | Ví dụ |
|---|---|---|
| Unit test | Chuẩn hóa criteria và giá trị mặc định | Page âm thành page mặc định; size không vượt giới hạn |
| Controller test | Query parameter được chuyển đúng vào query service | Filter, sort, page giữ đúng giá trị |
| View test | Form phản ánh trạng thái hiện tại | Dropdown chọn đúng status; trang hiện tại được đánh dấu |
| Browser test | Refresh và Back/Forward giữ ngữ cảnh | URL filter được khôi phục sau refresh |
| Session test | Wizard state có khóa riêng và expiry | Hai tab không ghi đè draft nhau |
| Security test | State phía client không cấp quyền | Sửa hidden `ownerId` không thay đổi chủ sở hữu |
| Concurrency test | Draft hoặc form cũ không ghi đè dữ liệu mới | Version cũ bị từ chối |
| Cleanup test | State tạm được xóa đúng lúc | Draft hết hạn không còn truy cập được |

Các tình huống nên thử:

1. Mở URL có filter, refresh và xác minh filter vẫn được áp dụng.
2. Chuyển trang rồi nhấn Back; bộ lọc và trang trước được khôi phục.
3. Thay filter khi đang ở trang cuối; ứng dụng reset page hợp lý.
4. Gửi form thiếu dữ liệu; giá trị không nhạy cảm được giữ lại và lỗi gắn đúng trường.
5. Mở hai wizard ở hai tab; dữ liệu của chúng không ghi đè nhau.
6. Đóng tab rồi mở lại; `sessionStorage` có vòng đời đúng với yêu cầu.
7. Đăng xuất rồi đăng nhập lại; dữ liệu session cũ không rò sang người dùng khác.
8. Sửa localStorage hoặc hidden field; backend vẫn xác minh dữ liệu và quyền.
9. Draft hết hạn hoặc tài nguyên bị xóa; giao diện hiển thị trạng thái phù hợp.
10. Hai tab sửa cùng một đối tượng; xung đột version được phát hiện.

## 17. Những lỗi thiết kế thường gặp

### Lưu mọi trạng thái vào session

Session trở thành nơi chứa đủ loại dữ liệu, dễ tăng bộ nhớ và gây xung đột giữa nhiều tab. Hãy chọn URL cho trạng thái có thể chia sẻ, browser state cho UI tạm và backend cho dữ liệu nghiệp vụ.

### Đưa toàn bộ form vào URL

Query string có thể bị lưu trong history, log và referrer. Chỉ đưa filter hoặc lựa chọn không nhạy cảm cần bookmark; không đưa mật khẩu, OTP hoặc nội dung riêng tư vào URL.

### Dùng hidden field làm nguồn sự thật

Người dùng có thể sửa hidden input. Server phải xác định owner, giá, trạng thái và quyền từ dữ liệu có thẩm quyền.

### Dùng một session key cho nhiều tab

Wizard hoặc draft của tab này có thể ghi đè tab khác. Dùng draft ID hoặc key riêng cho mỗi quy trình và kiểm tra quyền khi khôi phục.

### Lưu state ở URL và storage nhưng không quy định ưu tiên

Giao diện có thể khôi phục filter cũ từ storage rồi ghi đè URL người dùng vừa chia sẻ. Hãy xác định nguồn ưu tiên và đồng bộ một chiều rõ ràng.

### Không có expiry hoặc cleanup

Draft cũ có thể tồn tại lâu hơn nhu cầu và chứa dữ liệu cá nhân. Hãy xác định thời hạn, sự kiện kết thúc và cách xóa.

### Tin state phía client khi cập nhật nghiệp vụ

Client có thể gửi version cũ hoặc lựa chọn đã lỗi thời. Server phải kiểm tra trạng thái mới nhất, quyền và concurrency trước khi ghi.

## 18. Quy trình thiết kế trạng thái biểu mẫu và lựa chọn

Khi thêm một trạng thái tương tác, hãy trả lời các câu hỏi sau:

1. **Trạng thái mô tả điều gì?** Dữ liệu nghiệp vụ, ngữ cảnh điều hướng hay trạng thái hiển thị tức thời?
2. **Ai cần dùng nó?** Một component, một tab, một phiên, một người dùng hay nhiều người?
3. **Cần tồn tại bao lâu?** Qua render, request, redirect, refresh, tab, session hay nhiều thiết bị?
4. **Có cần chia sẻ/bookmark không?** Nếu có, cân nhắc URL path/query.
5. **Có nhạy cảm không?** Nếu có, tránh URL và browser storage không phù hợp; xác định quyền truy cập phía server.
6. **Nguồn nào có ưu tiên?** URL, form submission, session, storage hay backend?
7. **Khôi phục và xác thực thế nào?** Kiểm tra kiểu, phạm vi, version và quyền trước khi dùng.
8. **Khi nào xóa?** Submit thành công, hủy, logout, hết hạn hay schema thay đổi?
9. **Có xung đột nhiều tab hoặc nhiều người dùng không?** Dùng draft ID, version hoặc cơ chế hợp nhất phù hợp.
10. **Kiểm thử ra sao?** Refresh, Back/Forward, tab mới, hết hạn, dữ liệu giả mạo và cập nhật đồng thời.

## Kết luận

Giữ trạng thái biểu mẫu, bộ lọc và lựa chọn hiện tại giúp người dùng tiếp tục công việc mà không mất ngữ cảnh. URL phù hợp với filter, sort, pagination và tab cần chia sẻ; request và form object phù hợp với dữ liệu vừa gửi; flash/session hỗ trợ các luồng tạm thời; browser storage phục vụ state cục bộ; database phía server dành cho draft hoặc tùy chọn cần bền vững và đồng bộ.

Trong MVC, View trình bày trạng thái và thu nhận tương tác; Controller khôi phục, kiểm tra và điều phối request; application service cùng Domain Model bảo vệ quy tắc và quyền; backend là nguồn có thẩm quyền cho dữ liệu nghiệp vụ. Khi xác định rõ vòng đời, phạm vi, nguồn ưu tiên và thời điểm dọn dẹp, ứng dụng có thể giữ trải nghiệm liền mạch mà vẫn tránh rò rỉ dữ liệu, xung đột nhiều tab và sử dụng trạng thái lỗi thời.
