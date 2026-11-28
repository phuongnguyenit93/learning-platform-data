# Permissions-Policy

## 1. Mục tiêu và phạm vi

Permissions Policy là cơ chế để một website giới hạn những tính năng trình duyệt mà tài liệu và nội dung nhúng được phép sử dụng. Chính sách thường được chuyển bằng HTTP response header `Permissions-Policy`, kết hợp với thuộc tính `allow` của iframe khi cần ủy quyền tính năng cho nội dung nhúng. [W3C: Permissions Policy](https://www.w3.org/TR/permissions-policy/)

Ví dụ, một cổng quản lý yêu cầu bảo mật không cần camera, microphone hay vị trí địa lý trên các trang xem tài liệu. Việc chặn các khả năng đó giúp biến nguyên tắc “chỉ có quyền cần thiết” thành điều kiện mà trình duyệt có thể thực thi trong phạm vi tính năng được hỗ trợ.

Trong thiết kế yêu cầu bảo mật, mục tiêu không phải thêm càng nhiều tên directive càng tốt. Cần xác định tính năng nào thực sự cần, tài liệu nào được phép dùng, origin nào được ủy quyền và cách chứng minh chính sách có hiệu lực trên các trình duyệt thuộc phạm vi hỗ trợ.

Sau bài này, người học có thể:

- Phân biệt Permissions Policy với quyền do người dùng cấp và quyền truy cập API phía máy chủ.
- Viết đúng cú pháp header và phân biệt nó với cú pháp `iframe allow`.
- Đặc tả ranh giới giữa trang cha, iframe cùng origin và iframe khác origin.
- Thiết kế profile cho trang thông thường và trang cần một khả năng nhạy cảm.
- Xác định bằng chứng từ response cuối cùng, cấu trúc frame và hành vi của tính năng.

Bài sử dụng camera, microphone và geolocation để minh họa. Đây là một tập tính năng có chủ ý của ví dụ, không phải danh sách đầy đủ mọi khả năng mà trình duyệt hoặc mọi phiên bản của cơ chế này kiểm soát.

## 2. Mục tiêu bảo vệ và giới hạn của cơ chế

### 2.1. Giới hạn khả năng của tài liệu

Giả sử trang quản lý yêu cầu có một iframe hỗ trợ và một widget thống kê. Không có nhu cầu nghiệp vụ nào yêu cầu chúng sử dụng microphone. Một chính sách chặn microphone tạo ranh giới rõ hơn so với việc chỉ kỳ vọng mã hiện tại sẽ không gọi API đó.

Điều kiện cần đặc tả là “tài liệu này không được sử dụng khả năng microphone trong các trình duyệt được hỗ trợ”, không chỉ “giao diện không có nút ghi âm”. Việc ẩn nút không ngăn một đoạn mã khác thử gọi API.

### 2.2. Được policy cho phép không đồng nghĩa đã có quyền của người dùng

Camera và microphone còn chịu các điều kiện của API, quyền người dùng, quyền hệ điều hành và tình trạng thiết bị. Một allowlist cho phép origin chỉ mở khả năng được xét theo policy; nó không tự cấp quyền ghi hình hoặc ghi âm thay người dùng. [W3C: Media Capture and Streams, tích hợp Permissions Policy](https://www.w3.org/TR/mediacapture-streams/#permissions-policy-integration)

Cần tách hai câu hỏi:

```text
Tài liệu có được policy cho phép sử dụng tính năng không?

Nếu có, các điều kiện khác để sử dụng tính năng đã được đáp ứng chưa?
```

Ví dụ, một widget được ủy quyền camera vẫn cần xử lý tình huống người dùng từ chối hoặc không có thiết bị phù hợp. Ngược lại, việc người dùng từng cho phép camera không có nghĩa tài liệu hiện tại được vượt qua một policy đang chặn.

### 2.3. Không phải authorization của API

Permissions Policy được trình duyệt thực thi đối với khả năng của tài liệu. Nó không thay kiểm tra đăng nhập, tenant, quyền đối tượng hoặc quyền tải dữ liệu ở máy chủ.

Một client HTTP tự viết không phải tuân theo các giới hạn giao diện theo cách trình duyệt thực thi. Máy chủ vẫn phải tự bảo vệ API. Header chặn camera cũng không ngăn việc tải lên một tệp hình ảnh có sẵn nếu chức năng upload cho phép hành vi đó.

### 2.4. Không phải bộ lọc toàn bộ mã độc hoặc dữ liệu

Chặn một tính năng không loại bỏ mọi rủi ro từ script, không sửa XSS và không thu hồi dữ liệu đã được chia sẻ bằng một luồng khác. Nó chỉ đặt giới hạn cho những khả năng thuộc chính sách có hiệu lực.

Vì vậy, cần mô tả mục tiêu đủ hẹp để kiểm chứng, đồng thời kết hợp các yêu cầu độc lập về nội dung, sandbox, quyền máy chủ và quản lý dữ liệu khi kiến trúc cần chúng.

## 3. Cú pháp header và allowlist

### 3.1. Các dạng thường dùng

Header có dạng directive gắn với allowlist. Nhiều directive được phân cách bằng dấu phẩy; origin cụ thể trong danh sách được đặt trong dấu nháy kép. [MDN: Permissions-Policy header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Permissions-Policy)

```http
Permissions-Policy: camera=(), microphone=(), geolocation=()
```

Các ví dụ minh họa:

| Giá trị | Ý nghĩa chính sách mong muốn |
| --- | --- |
| `camera=()` | Không cấp khả năng camera cho tài liệu và các frame bị ràng buộc bởi chính sách này |
| `camera=(self)` | Giới hạn allowlist của camera vào origin của tài liệu khai báo |
| `camera=(self "https://capture.example.test")` | Cho phép xét camera trong phạm vi origin hiện tại và origin được liệt kê, cùng các điều kiện ủy quyền liên quan |
| `camera=*` | Allowlist rộng, không phải lựa chọn tối thiểu quyền của ví dụ này |

Các dòng trong bảng là ví dụ chính sách, không phải các header cần gửi đồng thời. Một profile phải chọn giá trị có chủ ý cho từng tính năng thuộc phạm vi của nó.

### 3.2. Origin không phải đường dẫn

Origin được xác định bởi scheme, host và port theo mô hình origin của web. Quyết định cho một origin không phải là quyết định riêng cho một đường dẫn như `/capture` trên origin đó.

```text
https://capture.example.test
https://capture.example.test:8443
https://other.example.test
```

Không nên coi các giá trị trên là cùng một đích chỉ vì tên miền có phần giống nhau. Ngược lại, hai đường dẫn trên cùng origin không tạo một ranh giới origin mới.

Nếu chỉ một widget nên có khả năng nhạy cảm, việc đặt widget trên một origin riêng có thể giúp diễn đạt ranh giới rõ hơn. Thiết kế này vẫn cần kiểm soát nội dung và các script chạy trong origin đó.

### 3.3. Không sao chép cú pháp iframe vào header

Cú pháp của `iframe allow` khác header. Ví dụ chặn camera cho một iframe có thể dùng:

```html
<iframe
  src="https://help.example.test/widget"
  title="Trợ giúp"
  allow="camera 'none'; microphone 'none'; geolocation 'none'">
</iframe>
```

Ở thuộc tính `allow`, các nhóm tính năng được ngăn bằng dấu chấm phẩy và có các token như `'none'`. Không chuyển nguyên chuỗi này thành giá trị header. [MDN: hướng dẫn Permissions Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Permissions_Policy)

Ví dụ sau không phải cách viết header được dùng trong bài:

```text
Permissions-Policy: camera 'none'; microphone 'none'
```

Một cấu hình có tên header đúng nhưng giá trị sai không tạo bằng chứng rằng trình duyệt đã áp dụng điều kiện bảo vệ mong muốn.

### 3.4. Không khai báo không đồng nghĩa từ chối

Mỗi tính năng có mặc định riêng. Không nên suy ra các tính năng bị bỏ khỏi header đều tự động bị chặn. Camera và microphone có default allowlist là `self` theo đặc tả tương ứng. [W3C: Media Capture and Streams, mục 14](https://www.w3.org/TR/mediacapture-streams/#permissions-policy-integration)

Yêu cầu nên liệt kê những tính năng đã được đánh giá là không cần thiết và cần chặn. Khi bổ sung một khả năng mới vào sản phẩm, cần đánh giá lại profile thay vì dựa vào một danh sách cũ không có phạm vi rõ.

## 4. Trang cha, iframe và chính sách kế thừa

### 4.1. Header và allow phối hợp với nhau

Đối với một iframe khác origin cần camera, thiết kế phải phối hợp allowlist của trang cha với việc ủy quyền ở iframe. Ví dụ của Chrome nêu rõ việc thêm origin khác vào header không tự thay cho thuộc tính `allow` cần thiết trên iframe khác origin. [Chrome for Developers: Permissions Policy](https://developer.chrome.com/docs/privacy-security/permissions-policy)

Trang cha tại `https://portal.example.test` có thể trả:

```http
Permissions-Policy: camera=(self "https://capture.example.test"), microphone=(), geolocation=()
```

Và nhúng widget bằng:

```html
<iframe
  src="https://capture.example.test/widget"
  title="Chụp ảnh minh chứng"
  allow="camera https://capture.example.test; microphone 'none'; geolocation 'none'">
</iframe>
```

Các origin trong ví dụ là địa chỉ minh họa. Origin thực tế phải được phê duyệt từ danh mục tích hợp của hệ thống, không lấy nguyên giá trị do caller tùy ý cung cấp để ghép vào header.

### 4.2. Frame con không tự mở lại quyền cha đã chặn

Nếu camera bị chặn trong chính sách kế thừa từ cha, thêm `allow` ở frame con hoặc một header rộng hơn tại con không tự gỡ được giới hạn đó. Thuộc tính `allow` bổ sung ràng buộc trong phạm vi chính sách cha, không phải một lệnh bỏ qua cha. [W3C: Permissions Policy, inherited policies](https://www.w3.org/TR/permissions-policy/), [MDN: HTMLIFrameElement.allow](https://developer.mozilla.org/en-US/docs/Web/API/HTMLIFrameElement/allow)

Do đó, không thể vừa đặt `camera=()` ở shell cha rồi kỳ vọng một iframe bên trong sẽ dùng camera bằng cách thêm `allow="camera"`. Nếu nghiệp vụ cần widget đó, phải có profile cha cho phép đường ủy quyền cần thiết và kiểm soát giới hạn còn lại.

### 4.3. Frame con vẫn có thể thu hẹp chính nó

Một widget có thể trả policy riêng để chặn microphone và geolocation, hoặc chặn thêm camera nếu nó không cần dùng trong một trang cụ thể. Kết quả hiệu lực phụ thuộc toàn bộ đường kế thừa và cấu hình của tài liệu đích, không chỉ một thẻ iframe ở trang trên cùng.

Với chuỗi frame nhiều cấp, cần xác định từng cạnh nhúng. Quyền được thiết kế cho một widget không nên vô tình trở thành quyền cho mọi nội dung mà widget có thể nhúng tiếp.

### 4.4. Điều hướng iframe là một tình huống cần kiểm chứng

Iframe có thể tải một origin rồi điều hướng sang origin khác. Hồ sơ ủy quyền cần xác định origin nào được phép ở tài liệu thực tế, không chỉ chuỗi `src` ban đầu.

Trong profile mẫu, origin ngoài allowlist không được nhận camera chỉ vì frame trước đó từng tải widget được phép. Tiêu chí nghiệm thu cần bao gồm điều hướng và các frame lồng nhau nếu chức năng có những hành vi này.

## 5. Script và những ranh giới không nên hiểu nhầm

### 5.1. Script ngoài được nạp vào trang vẫn chạy trong ngữ cảnh trang

Một script được tải từ origin bên ngoài nhưng thực thi trực tiếp trong tài liệu sẽ chịu policy của tài liệu đang chứa nó; policy không tách quyền theo nơi lưu tệp JavaScript. [MDN: kế thừa policy cho nội dung nhúng](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Permissions_Policy#inheritance_of_policies_for_embedded_content)

Vì vậy, `camera=(self)` không có nghĩa chỉ mã do tổ chức tự viết mới có khả năng camera. Mã bên thứ ba chạy trong trang cũng cần được xem xét theo mức tin cậy của trang đó.

Trong profile shell dùng để ủy quyền camera, `self` được giữ trong allowlist để đường ủy quyền không bị chặn ở cha. Điều này cũng có nghĩa shell cần được bảo vệ tương xứng; không nên mô tả nó là một trang đã bị cấm camera nhưng vẫn ủy quyền được camera xuống con.

### 5.2. Các cơ chế liên quan có mục tiêu khác nhau

| Cơ chế | Mục tiêu cần phân biệt |
| --- | --- |
| Permissions Policy | Giới hạn một số khả năng trình duyệt của tài liệu và frame |
| Quyền của người dùng/hệ điều hành | Quyết định quyền truy cập thiết bị hoặc khả năng theo cơ chế của nền tảng |
| CSP | Kiểm soát các nguồn và hành vi nội dung theo directive tương ứng |
| `iframe sandbox` | Áp dụng các giới hạn cho ngữ cảnh nhúng theo cấu hình sandbox |
| CORS | Điều khiển việc chia sẻ response giữa origin theo cơ chế trình duyệt |
| Authorization phía máy chủ | Quyết định caller có được thực hiện hành động hoặc truy cập dữ liệu không |

Không dùng một header thay cho tất cả các mục tiêu này. Khi một iframe không hoạt động, nguyên nhân cũng có thể nằm ở sandbox, quyền thiết bị hoặc cấu hình nội dung, thay vì Permissions Policy.

## 6. Chuyển nhu cầu nghiệp vụ thành profile

### 6.1. Kiểm kê trước khi chặn

Giả sử cổng yêu cầu bảo mật có hai nhóm trang:

- Trang thông thường chỉ đọc, tìm kiếm và soạn nội dung văn bản.
- Trang đính kèm ảnh minh chứng nhúng một widget chụp ảnh từ origin được kiểm soát.

Ma trận thiết kế có thể là:

| Khả năng | Trang thông thường | Shell chụp ảnh | Widget được phê duyệt |
| --- | --- | --- | --- |
| Camera | Chặn | Cho phép trong đường ủy quyền đã xác định | Được xét sử dụng khi cả policy và các điều kiện khác cho phép |
| Microphone | Chặn | Chặn | Chặn |
| Geolocation | Chặn | Chặn | Chặn |

Việc chụp ảnh không tự tạo nhu cầu ghi âm hoặc lấy vị trí. Mỗi khả năng phải có căn cứ riêng; không mở rộng mọi directive chỉ để một chức năng thử nghiệm hoạt động.

### 6.2. Profile có thể ánh xạ sang header

```text
STANDARD_DOCUMENT
  camera=(), microphone=(), geolocation=()

CAPTURE_SHELL
  camera=(self "https://capture.example.test"), microphone=(), geolocation=()

CAPTURE_WIDGET
  camera=(self), microphone=(), geolocation=()
```

Profile widget không tự tạo quyền nếu một tổ tiên đã chặn. Nó chỉ mô tả phần chính sách mà tài liệu widget mong muốn trong phạm vi được kế thừa.

Các profile trên là lựa chọn của hệ thống mẫu. Nếu sản phẩm cần microphone hoặc geolocation, phải bổ sung điều kiện nghiệp vụ và bằng chứng cho chính khả năng đó.

### 6.3. Chọn profile từ cấu hình được kiểm soát

Không để query parameter như `?camera=true` hoặc một role tự khai trong request quyết định mở policy. Việc chọn profile cần gắn với route tài liệu và cấu hình chức năng do hệ thống kiểm soát.

Nếu một chức năng cần phân quyền người dùng, máy chủ vẫn phải kiểm tra quyền truy cập chức năng và API liên quan. Profile trình duyệt không phải bằng chứng caller được phép tải hoặc ghi minh chứng của một tài nguyên cụ thể.

## 7. Đặc tả yêu cầu bảo mật có thể nghiệm thu

### 7.1. Yêu cầu còn thiếu

```text
Ứng dụng phải có Permissions-Policy để an toàn.
```

Câu này không xác định tài liệu nào, tính năng nào, trình duyệt nào, có iframe được ủy quyền hay không và phải quan sát kết quả gì. Chỉ kiểm tra có tên header sẽ bỏ qua phần lớn điều kiện cần thực thi.

### 7.2. Yêu cầu nền tảng cho trang thông thường

```text
REQ-PP-01 — Giới hạn khả năng của tài liệu thông thường

Mọi response tạo tài liệu HTML thuộc profile STANDARD_DOCUMENT phải có
policy hiệu lực chặn camera, microphone và geolocation trên tài liệu đó
và các nội dung nhúng bị ràng buộc bởi đường kế thừa tương ứng.

Trên tập trình duyệt và directive được hệ thống hỗ trợ, việc thử sử dụng
những khả năng này không được vượt qua giới hạn do policy đặt ra, kể cả
khi môi trường người dùng đã cho phép khả năng đó ở mức khác.

Bằng chứng phải bao gồm response cuối cùng tới trình duyệt, cấu trúc frame
và hành vi thực thi của từng khả năng trong điều kiện kiểm chứng hợp lệ.
```

### 7.3. Các yêu cầu bổ sung

| Mã | Nội dung | Bằng chứng nghiệm thu |
| --- | --- | --- |
| REQ-PP-02 | Mỗi khả năng được mở phải có tài liệu, origin và nhu cầu nghiệp vụ được phê duyệt | Ma trận khả năng và danh mục origin |
| REQ-PP-03 | Cross-origin iframe được ủy quyền phải đáp ứng đồng thời policy cha, cấu hình container và policy con | Response và DOM của toàn chuỗi frame |
| REQ-PP-04 | Origin ngoài allowlist và frame không được ủy quyền không được nhận khả năng ngoài profile | Các tình huống frame không tin cậy và điều hướng |
| REQ-PP-05 | Hệ thống phải kiểm soát cú pháp và giá trị policy có hiệu lực sau các lớp gateway, CDN và ứng dụng | Response thực tế trên các đường phục vụ |
| REQ-PP-06 | Profile không được mở rộng từ dữ liệu do caller tùy ý cung cấp | Luồng chọn profile và request thay dữ liệu tự khai |
| REQ-PP-07 | Tập trình duyệt được hỗ trợ phải được đối chiếu theo từng directive và tình huống frame cần dùng | Ma trận tương thích và kết quả hành vi |
| REQ-PP-08 | Lỗi hoặc thiếu hỗ trợ của cơ chế này không được dùng làm lý do bỏ quyền máy chủ hoặc tự mở mọi khả năng | Luồng xử lý lỗi và yêu cầu authorization độc lập |

Một ngoại lệ cần camera phải nêu đúng phạm vi, không chỉ ghi “trang đặc biệt bỏ header”. Bỏ toàn bộ policy có thể mở thêm những khả năng không liên quan tới nhu cầu chụp ảnh.

## 8. Ví dụ Java: profile được chọn từ một tập hữu hạn

Ví dụ sau chỉ tạo giá trị header từ những profile đã định nghĩa. Nó không phụ thuộc một framework web cụ thể và không cấu hình trực tiếp response của ứng dụng:

```java
import java.util.Objects;

public final class PermissionsPolicyProfiles {

    public enum PageProfile {
        STANDARD_DOCUMENT,
        CAPTURE_SHELL,
        CAPTURE_WIDGET
    }

    private PermissionsPolicyProfiles() {
    }

    public static String headerValue(PageProfile profile) {
        Objects.requireNonNull(profile, "profile");

        switch (profile) {
            case STANDARD_DOCUMENT:
                return "camera=(), microphone=(), geolocation=()";

            case CAPTURE_SHELL:
                return "camera=(self \"https://capture.example.test\"), "
                        + "microphone=(), geolocation=()";

            case CAPTURE_WIDGET:
                return "camera=(self), microphone=(), geolocation=()";

            default:
                throw new IllegalArgumentException("Unknown page profile");
        }
    }
}
```

Giá trị trả về cần được lớp web gắn vào HTTP response header `Permissions-Policy` trước khi response tạo tài liệu được gửi. Route và chức năng đã được hệ thống xác định sẽ chọn profile, không phải một chuỗi tùy ý từ request.

Những điểm cần giữ khi tích hợp:

- Không tạo allowlist bằng cách nối trực tiếp origin chưa được phê duyệt.
- Không chuyển sang một chuỗi rỗng hoặc policy mở khi việc chọn profile gặp lỗi.
- Không mặc định header do ứng dụng tạo sẽ được giữ nguyên qua CDN hoặc gateway.
- Không chỉ áp dụng ở controller thành công rồi bỏ sót các trang HTML do lớp khác tạo.
- Không coi các profile trên là quyền được cấp cho một tài khoản; quyền chức năng vẫn do máy chủ kiểm tra.

Một lớp thuần tạo chuỗi giúp quản lý cấu hình tập trung, nhưng kiểm tra chuỗi đó không đủ để nghiệm thu. Vẫn cần chứng minh response thực tế và hành vi trình duyệt phù hợp.

## 9. Đặt policy ở đúng response và đúng tài liệu

### 9.1. Header thuộc response tạo tài liệu

Nếu frontend được phát từ CDN còn backend Java chỉ trả JSON, thêm header vào response JSON không tự cấu hình policy của trang HTML đã được tải trước đó. Cần xác định thành phần nào tạo tài liệu và gắn profile tại đúng ranh giới đó.

Tương tự, một trang lỗi do gateway tạo không nhất thiết đi qua bộ lọc header của ứng dụng. Nếu trang đó thuộc phạm vi yêu cầu, phải có profile được áp dụng ở thành phần thực sự phát response.

### 9.2. Không giả định mọi lớp xử lý header giống nhau

Ứng dụng, reverse proxy và CDN có thể thêm, thay hoặc loại header. Yêu cầu tích hợp nên chỉ rõ thành phần sở hữu giá trị có hiệu lực và cách tránh các khai báo trùng hoặc mâu thuẫn.

Không nghiệm thu bằng một file cấu hình ở backend nếu người dùng nhận một giá trị khác. Cần quan sát response cuối cùng trên các đường phục vụ có liên quan, bao gồm trường hợp cache được dùng hoặc trang được tạo bởi một đường xử lý riêng.

### 9.3. Chính sách thay đổi theo tài liệu, không theo tên màn hình trong SPA

Một ứng dụng một trang có thể đổi màn hình mà không tải tài liệu HTML mới. Việc đổi route phía client hoặc tải một JSON mới không đồng nghĩa browser đã nhận một policy mới cho tài liệu hiện tại.

Nếu thiết kế cần một vùng có quyền camera khác với vùng thông thường, phải chọn mô hình tài liệu hoặc frame phù hợp rồi kiểm chứng vòng đời của nó. Không nên dựa vào việc UI đã điều hướng sang màn hình khác để kết luận quyền của tài liệu cũ tự biến mất.

Khi máy chủ thay profile, cũng cần xác định hành vi đối với trang đang mở. Không tuyên bố thay cấu hình HTTP đã ngay lập tức cập nhật mọi tài liệu đã tải ở trình duyệt.

### 9.4. Cache phải giữ đúng biến thể tài liệu

Nếu response HTML có nhiều profile, cơ chế cache cần phân biệt đúng những biến thể đã được thiết kế. Không để một shell có khả năng camera bị phục vụ nhầm cho trang đáng lẽ dùng profile chặn camera.

Ngược lại, một bản cache của profile chặn có thể làm chức năng được phê duyệt không hoạt động. Tiêu chí cần kiểm tra cả tính bảo vệ và tính đúng đắn của việc phân phối profile, không chỉ một lần tải không qua cache.

## 10. Kiểm chứng hành vi của khả năng

### 10.1. Header có mặt chưa chứng minh đã được thực thi

Mức hỗ trợ của header và từng directive không đồng nhất giữa các trình duyệt. Tài liệu tham chiếu của MDN đánh dấu những giới hạn tương thích cần được kiểm tra trước khi áp dụng. Do đó, yêu cầu phải có tập browser/version mục tiêu và bằng chứng theo từng tính năng, thay vì suy ra một header bảo đảm hành vi trên mọi client. [MDN: Permissions-Policy, tương thích trình duyệt](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Permissions-Policy#browser_compatibility)

Nếu directive không được thực thi trong một browser, kết quả cần được báo đúng là thiếu bảo đảm của lớp này. Không coi việc máy chủ đã gửi chuỗi cấu hình là bằng chứng browser đã chặn.

### 10.2. Thiết lập điều kiện để kết quả có ý nghĩa

Đối với camera, môi trường phải có secure context phù hợp và cơ chế thiết bị/quyền kiểm thử được xác định. `getUserMedia()` có thể thất bại vì người dùng từ chối, không có thiết bị hoặc các điều kiện khác, nên một lần thất bại đơn lẻ chưa chỉ ra nguyên nhân policy. [MDN: MediaDevices.getUserMedia](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia)

Một thiết kế kiểm chứng đáng tin có thể dùng hai trường hợp đối chứng:

```text
Đối chứng cho phép:
  Môi trường và quyền thiết bị đã được chuẩn bị.
  Profile cho phép đúng khả năng trong đúng tài liệu.
  Thao tác có thể thành công trong điều kiện kiểm thử.

Trường hợp chặn:
  Giữ các điều kiện môi trường thích hợp.
  Tải tài liệu với profile chặn khả năng đó.
  Thao tác không sử dụng được khả năng do ràng buộc cần kiểm chứng.
```

Với môi trường tự động, có thể dùng thiết bị kiểm thử hoặc mô phỏng do công cụ hỗ trợ theo chính sách của nhóm. Không cần ghi hoặc lưu media của người thật để chứng minh một profile chặn camera.

### 10.3. Đoạn kiểm chứng camera minh họa

Đoạn JavaScript sau chỉ dành cho một trang kiểm thử được phép. Nó trả trạng thái quan sát và dừng các track ngay nếu có được stream:

```javascript
async function probeCameraForAuthorizedTest() {
  if (!window.isSecureContext) {
    return { outcome: "invalid-test-context" };
  }

  if (!navigator.mediaDevices ||
      typeof navigator.mediaDevices.getUserMedia !== "function") {
    return { outcome: "api-unavailable" };
  }

  let stream;

  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: true,
      audio: false
    });

    return { outcome: "obtained" };
  } catch (error) {
    return {
      outcome: "rejected",
      errorName: error.name
    };
  } finally {
    if (stream) {
      for (const track of stream.getTracks()) {
        track.stop();
      }
    }
  }
}
```

Trên browser có hỗ trợ directive camera, policy chặn có thể khiến lời gọi bị từ chối với `NotAllowedError`. Tên lỗi này là một phần bằng chứng, không phải bằng chứng độc lập duy nhất về nguyên nhân. [MDN: Permissions-Policy camera](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Permissions-Policy/camera)

Đoạn code không tự kết luận PASS cho yêu cầu bảo mật. Người kiểm chứng vẫn phải biết profile đã nhận, vị trí trong frame tree, khả năng hỗ trợ của browser và trạng thái quyền của môi trường. Nếu người dùng không phản hồi prompt, harness cần phân loại kết quả chờ theo thiết kế thay vì tự coi đó là đã chặn thành công.

Camera và microphone cần được kiểm tra riêng nếu yêu cầu chặn cả hai. Một lời gọi yêu cầu đồng thời audio và video rồi thất bại không tự chứng minh cả hai khả năng đều bị chặn đúng.

### 10.4. Ma trận tình huống cho hệ thống mẫu

| Tình huống | Kỳ vọng theo profile | Bằng chứng chính |
| --- | --- | --- |
| Trang STANDARD thử camera | Không sử dụng được camera do policy hiệu lực | Header, ngữ cảnh tài liệu và kết quả API có đối chứng |
| Trang STANDARD thử microphone | Không sử dụng được microphone do policy hiệu lực | Kiểm tra riêng khả năng audio |
| Trang STANDARD thử geolocation | Không lấy được vị trí qua khả năng bị chặn | Điều kiện và hành vi của API tương ứng |
| Shell chụp ảnh nhúng đúng widget, có `allow` phù hợp | Widget có thể tiếp tục bước xin quyền hoặc dùng camera khi các điều kiện khác đạt | Header cha/con, DOM iframe và kết quả đối chứng |
| Iframe khác origin không được ủy quyền | Không nhận được khả năng camera ngoài profile | Tình huống không có hoặc không khớp ủy quyền |
| Frame con cố mở camera sau khi cha đã chặn | Không vượt được giới hạn cha | Toàn bộ chuỗi policy và hành vi của con |
| Widget điều hướng sang origin ngoài allowlist | Không mang theo quyền camera ngoài phạm vi đã cấp | Origin tài liệu sau điều hướng và kết quả API |
| Frame lồng thêm một nội dung khác | Chỉ có khả năng nếu toàn đường ủy quyền cho phép theo thiết kế | Chính sách ở từng cạnh nhúng |
| Browser không thực thi directive thuộc yêu cầu | Ghi nhận thiếu bảo đảm hoặc ngoài phạm vi hỗ trợ đã chốt | Phiên bản browser, directive và kết quả quan sát |

Các kỳ vọng về khả năng đều nằm trong tập browser và điều kiện đã được xác định. Không biến hàng “có thể dùng camera” thành yêu cầu bỏ qua sự từ chối của người dùng hoặc bỏ các kiểm tra quyền khác.

## 11. Vòng đời policy và quan sát vận hành

### 11.1. Giữ ma trận khả năng cùng với thiết kế tính năng

Khi thêm cuộc gọi âm thanh, bản đồ hoặc một widget mới, cần cập nhật ma trận nhu cầu. Không chỉ sửa header để loại bỏ lỗi console mà không biết khả năng đó có thực sự được sản phẩm phê duyệt hay chưa.

Một thay đổi origin của nhà cung cấp cũng cần được xem như thay đổi ranh giới tin cậy. Nhu cầu cho phép một host cụ thể không tự tạo nhu cầu cho phép mọi subdomain hoặc mọi origin.

### 11.2. Không coi thiếu báo cáo là bằng chứng không có vi phạm

Console, công cụ đọc policy hoặc cơ chế báo cáo có thể hỗ trợ điều tra khi môi trường triển khai hỗ trợ chúng. Tập bằng chứng vẫn phải dựa trên khả năng thực tế của browser và luồng kiểm chứng được kiểm soát.

Không có cảnh báo không chứng minh tính năng bị chặn, và không có sự kiện telemetry không chứng minh không ai thử dùng tính năng. Hệ thống quan sát có thể không được hỗ trợ, bị tắt hoặc không thu thập đường đi đang xét.

### 11.3. Phân công trách nhiệm

| Thành phần | Trách nhiệm điển hình |
| --- | --- |
| Nhóm sản phẩm và bảo mật | Xác định khả năng cần thiết, profile và ngoại lệ |
| Nhóm web hoặc ứng dụng | Chọn profile đúng cho tài liệu và cấu hình iframe |
| Nhóm hạ tầng/CDN | Bảo toàn policy trên response cuối và các trang họ tạo |
| Nhóm tích hợp widget | Xác nhận origin, frame tree và nhu cầu của nội dung nhúng |
| Nhóm kiểm chứng | Kiểm tra cú pháp, biến thể response và hành vi trên browser mục tiêu |

Nếu hai nhóm cùng thêm header, cần thống nhất nơi sở hữu cấu hình thay vì để kết quả phụ thuộc thứ tự proxy. Nếu widget nằm trên một hệ thống riêng, bên đó cần biết policy con của họ là một phần của hợp đồng tích hợp.

### 11.4. Quản lý ngoại lệ có thời hạn

Ngoại lệ nên ghi rõ tài liệu nào, khả năng nào, origin nào, chủ sở hữu và lý do. Nếu có thời hạn hoặc sự kiện kết thúc, phải xác định cách bỏ ủy quyền và kiểm chứng lại profile sau đó.

Một cấu hình mở cho giai đoạn phát triển không nên trở thành mặc định production chỉ vì chức năng đã chạy được. Cần nghiệm thu chính sách cần đạt, không chỉ nghiệm thu việc widget xuất hiện trên màn hình.

## 12. Các sai lầm thường gặp

### 12.1. Chặn tất cả ở cha rồi mở ở con

Đây là hiểu sai đường kế thừa. Cần thiết kế lại profile của đường ủy quyền; frame con không có quyền tự đảo một giới hạn mà nó đã kế thừa từ cha.

### 12.2. Mở wildcard để chữa mọi lỗi tương thích

Cho phép mọi origin làm mất ranh giới cần bảo vệ. Cần xác định tính năng, origin và cạnh nhúng nào đang thiếu cấu hình hoặc browser nào chưa hỗ trợ, rồi sửa đúng phần đó.

### 12.3. Dùng cú pháp Feature-Policy cũ cho header mới

Việc cơ chế từng có tên Feature Policy không có nghĩa chỉ cần đổi tên header và giữ nguyên cú pháp. Cần dùng grammar tương ứng với header thực tế và kiểm chứng trên tập browser hỗ trợ.

### 12.4. Cho rằng allowlist origin là allowlist script

Policy áp dụng theo tài liệu và đường nhúng, không phân biệt từng tệp JavaScript được tải vào cùng ngữ cảnh. Mức tin cậy của script chạy trong trang cần được kiểm soát bằng thiết kế phù hợp.

### 12.5. Chỉ kiểm tra tên header

Header có thể sai cú pháp, bị thay ở proxy, nằm trên response không tạo tài liệu hoặc không được browser thực thi. Nghiệm thu cần quan sát cả cấu hình cuối cùng lẫn hành vi trong điều kiện có ý nghĩa.

### 12.6. Dùng lỗi thiết bị làm bằng chứng policy

Không có camera, người dùng từ chối hoặc môi trường không đủ điều kiện đều có thể khiến lời gọi thất bại. Cần đối chứng để xác định giới hạn do policy thực sự là nguyên nhân cần kiểm chứng.

## 13. Hồ sơ yêu cầu mẫu

Một hồ sơ gọn cho cổng tài liệu có thể viết:

```text
Tài sản và mục tiêu:
  Giới hạn khả năng trình duyệt không cần thiết của các tài liệu thuộc cổng.

Profile mặc định:
  STANDARD_DOCUMENT chặn camera, microphone và geolocation.

Ngoại lệ nghiệp vụ:
  CAPTURE_SHELL chỉ mở đường camera cho widget tại origin đã phê duyệt.
  Microphone và geolocation vẫn bị chặn.
  Shell được xem là ngữ cảnh có khả năng camera và phải được bảo vệ tương ứng.

Thực thi:
  Header trên response tạo tài liệu, allow trên iframe và policy con phù hợp.
  Origin được chọn từ cấu hình được kiểm soát.
  Quyền chức năng và quyền dữ liệu phía máy chủ vẫn có hiệu lực độc lập.

Nghiệm thu:
  Kiểm tra response cuối, frame tree, điều hướng và các biến thể cache.
  Dùng đối chứng về môi trường, quyền và thiết bị cho từng khả năng.
  Ghi rõ browser/version và directive đã được chứng minh có hiệu lực.

Vòng đời:
  Tính năng hoặc origin mới phải cập nhật ma trận và bằng chứng.
  Ngoại lệ có chủ sở hữu; thay đổi profile phải xét tài liệu đang tồn tại.
```

Permissions-Policy đạt mục tiêu khi khả năng của mỗi tài liệu và nội dung nhúng không vượt phạm vi nghiệp vụ được phê duyệt trên tập browser hỗ trợ. Yêu cầu bảo mật cần nối được tính năng, origin, đường kế thừa, response thực tế và bằng chứng hành vi, đồng thời giữ độc lập các kiểm tra quyền người dùng và quyền máy chủ.
