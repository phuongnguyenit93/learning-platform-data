# Localized phone formatting trong luồng khôi phục tài khoản

## 1. Mục tiêu: dễ nhận ra số điện thoại và giữ đúng đích khôi phục

Trong luồng khôi phục tài khoản, số điện thoại có thể xuất hiện ở bước nhập định danh, chọn kênh nhận mã, xác nhận thông tin liên hệ hoặc xử lý tình huống mất thiết bị MFA. Người dùng thường nhớ số theo cách viết quen thuộc tại nơi cấp số, trong khi hệ thống gửi mã cần một đích nhất quán.

**Localized phone formatting** là cách tiếp nhận và trình bày số điện thoại phù hợp với ngữ cảnh vùng đánh số, đồng thời bản địa hóa nhãn, hướng dẫn và thông báo. Mục tiêu là giúp người dùng hiểu mình đang sử dụng số nào mà không làm thay đổi số đích.

Ví dụ, người dùng đang đọc giao diện tiếng Việt nhưng số khôi phục được cấp tại Hoa Kỳ. Chuyển ngôn ngữ giao diện sang tiếng Việt không cho phép ứng dụng thêm `+84`, đổi nhóm chữ số theo số Việt Nam hoặc diễn giải lại số đã lưu.

Trong bài này, cần tách ba vấn đề: **nhập số**, **chuẩn hóa để xử lý** và **định dạng để hiển thị**. Quyết định số nào đủ điều kiện khôi phục tài khoản là một ràng buộc an toàn riêng của phía máy chủ.

## 2. Locale, vùng đánh số và mã gọi không phải cùng một dữ liệu

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| Locale giao diện | Chọn ngôn ngữ và cách viết thông điệp | `vi-VN`, `en-US` |
| Vùng dùng để phân tích số nội địa | Cung cấp ngữ cảnh khi số chưa có mã gọi quốc tế | `VN`, `US`, `GB` |
| Mã gọi quốc tế | Thành phần đầu của số quốc tế | `+84`, `+1`, `+44` |
| Quốc gia đang cư trú hoặc địa chỉ IP | Ngữ cảnh môi trường của người dùng | Người dùng đi du lịch ở nước khác |
| Định danh liên hệ đã xác minh | Chọn bản ghi liên hệ được phép dùng trong giao dịch | Một ID nội bộ do server quản lý |

Không suy ra vùng của số điện thoại chỉ từ ngôn ngữ hoặc địa chỉ IP. Một người có thể dùng số nước ngoài, đi du lịch hoặc sử dụng giao diện bằng ngôn ngữ khác nơi cấp số. Một mã gọi cũng có thể được nhiều vùng dùng chung, như `+1`.

Tên vùng trong bộ chọn nên được dịch, còn giá trị kỹ thuật giữ ổn định. Chẳng hạn, nhãn có thể là “Hoa Kỳ (+1)” nhưng giá trị gửi về là `US`; không dùng chuỗi nhãn đã dịch làm khóa nghiệp vụ.

Định dạng số cần dựa trên kế hoạch đánh số liên quan, thay vì áp dụng mẫu nhóm số của ngôn ngữ đang xem. Đây cũng là sự phân biệt được nêu trong [FAQ của libphonenumber](https://github.com/google/libphonenumber/blob/master/FAQ.md).

## 3. Tách số chuẩn, số hiển thị và số đã che

Một mô hình hữu ích có ba dạng biểu diễn:

| Dạng | Mục đích | Ví dụ |
| --- | --- | --- |
| Số chuẩn phục vụ xử lý | So sánh và chuyển cho thành phần gửi tin theo hợp đồng của hệ thống | `+12025550123` |
| Số hiển thị đầy đủ | Giúp người dùng đọc và kiểm tra khi được phép xem | `+1 202-555-0123` hoặc `(202) 555-0123` |
| Gợi ý đã che | Giúp chọn liên hệ mà hạn chế tiết lộ | `+1 ••• ••• 0123` |

Số ví dụ dùng phần `555-0123`, thuộc dải `555-0100` đến `555-0199` được NANPA giữ cho số hư cấu, không hoạt động. Đây là dữ liệu minh họa, không phải đích gửi OTP. Xem [NANPA — 555 Line Numbers](https://www.nanpa.com/numbering/555-line-numbers).

Với số quốc tế E.164 cho vùng địa lý, độ dài tối đa là 15 chữ số, gồm mã quốc gia. Dấu `+` trong chuỗi ứng dụng không được tính là một chữ số. Xem [ITU-T E.164, bản 02/2026](https://www.itu.int/rec/T-REC-E.164-202602-I).

Trong phạm vi số điện thoại khôi phục thông thường của bài này, có thể chọn hợp đồng lưu trữ là dấu `+` theo sau bởi chữ số ASCII, không chứa dấu cách hay dấu phân nhóm. Đây là **chuỗi**, không phải một đại lượng để cộng trừ hoặc lưu bằng kiểu số nguyên.

Chuỗi hiển thị là dữ liệu dẫn xuất. Không dùng nó làm khóa so sánh, đích gửi mã hoặc đầu vào để ghi đè ngược số chuẩn. Dấu ngoặc, dấu cách và dấu gạch nối phục vụ việc đọc; chúng không tạo ra một liên hệ mới.

## 4. Thiết kế trường nhập không ép một mẫu số toàn cầu

Nếu cho phép nhập số chưa có mã gọi quốc tế, cần một bộ chọn vùng rõ ràng. Nếu người dùng nhập số bắt đầu bằng `+`, ứng dụng phải hiểu đó là dạng quốc tế và không ghép thêm mã gọi từ bộ chọn.

```html
<form method="post" action="/account-recovery/phone">
  <label for="phone-region">Vùng của số điện thoại</label>
  <select id="phone-region" name="phoneRegion">
    <option value="">Chọn vùng nếu nhập số nội địa</option>
    <option value="VN">Việt Nam (+84)</option>
    <option value="US">Hoa Kỳ (+1)</option>
    <option value="GB">Vương quốc Anh (+44)</option>
  </select>

  <label for="recovery-phone">Số điện thoại khôi phục</label>
  <p id="recovery-phone-hint">
    Chọn vùng của số hoặc nhập đầy đủ số với dấu + và mã gọi quốc tế.
    Bạn có thể dán số có khoảng trắng, dấu ngoặc hoặc dấu gạch nối.
  </p>
  <input
    id="recovery-phone"
    name="phoneInput"
    type="tel"
    inputmode="tel"
    autocomplete="tel"
    aria-describedby="recovery-phone-hint"
    maxlength="256"
    required
  >

  <button type="submit">Tiếp tục</button>
</form>
```

`type="tel"` hỗ trợ nhập số điện thoại và có thể cung cấp bàn phím phù hợp trên thiết bị di động; nó không tự xác nhận mọi quy tắc số điện thoại quốc tế. Xem [MDN — input type tel](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/input/tel).

`autocomplete="tel"` gợi ý tự điền số đầy đủ. Nếu thiết kế tách phần mã gọi và phần số nội địa, cần chọn token autocomplete phù hợp với đúng thành phần; `tel-national` không có cùng nghĩa với `tel`. Xem [MDN — autocomplete](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Attributes/autocomplete).

Giới hạn `256` ở ví dụ là ngân sách chiều dài cho chuỗi nhập có định dạng, không phải độ dài số theo E.164. Server vẫn phải tự giới hạn đầu vào. Không đặt `maxlength="15"` cho chuỗi thô rồi vô tình chặn dấu `+`, khoảng trắng hoặc dấu ngoặc hợp lệ về mặt trình bày.

Ba lựa chọn vùng trong HTML chỉ minh họa cấu trúc. Danh sách thực tế phải thể hiện các vùng sản phẩm hỗ trợ, có thể tìm kiếm và có tên bằng văn bản; một lá cờ đơn lẻ không đủ để giải thích mã gọi hoặc phạm vi hỗ trợ.

## 5. Phân tích số cần ngữ cảnh, không chỉ xóa ký tự

Hai tình huống đầu vào phải được phân biệt:

1. **Có dấu `+` và mã gọi quốc tế:** phân tích như số quốc tế. Bộ chọn vùng không được âm thầm thay thế phần mã gọi đã nhập.
2. **Không có mã gọi quốc tế:** sử dụng vùng người dùng đã chọn. Nếu thiếu ngữ cảnh cần thiết, yêu cầu bổ sung thay vì đoán từ locale.

Không dùng công thức chung “bỏ mọi số 0 đầu rồi thêm mã gọi”. Một số 0 có thể có ý nghĩa trong chính số quốc tế, như trường hợp Italy. Cũng không đổi mọi tiền tố `00` thành `+`, vì cách quay số quốc tế phụ thuộc vùng. Xem [FAQ về parsing của libphonenumber](https://github.com/google/libphonenumber/blob/master/FAQ.md).

Tương tự, không chỉ xóa mọi ký tự không phải chữ số. Thao tác đó làm mất dấu `+`, có thể nhập nhằng mã gọi với phần số nội địa và có thể ghép cả số máy lẻ vào đích gửi tin.

Ứng dụng nên xác định chính sách ký tự đầu vào trước khi gọi parser:

- Khoảng trắng và dấu phân nhóm được chấp nhận là phần trình bày.
- Nếu hỗ trợ chữ số thập phân của hệ chữ khác, ánh xạ từng chữ số sang giá trị ASCII tương ứng theo chính sách rõ ràng.
- Ký tự điều khiển, nhiều số trong cùng ô, nội dung mô tả tự do và ký hiệu máy lẻ cần được xử lý riêng hoặc từ chối có giải thích.
- Không âm thầm bỏ một ký tự chưa hiểu để tạo ra một số khác trông có vẻ hợp lệ.

Ví dụ, `٢٠٢٥٥٥٠١٢٣` là một cách viết cùng chuỗi giá trị chữ số với `2025550123`; nó vẫn cần ngữ cảnh vùng khi chưa có mã gọi. Việc hỗ trợ hệ chữ không cho phép tự suy ra vùng từ loại chữ số.

Một parser có thể có hành vi khá dung thứ với văn bản để phục vụ nhiều ứng dụng khác nhau. Trường nhập đích khôi phục cần hợp đồng hẹp hơn: người dùng nhập một số điện thoại, không phải một câu chứa số điện thoại.

## 6. Luồng xử lý từ đầu vào đến liên hệ được phép dùng

Một luồng xử lý rõ ràng có thể được mô tả như sau:

```text
Chuỗi nhập + vùng được chọn khi cần
    ↓
Giới hạn chiều dài, xử lý ký tự theo chính sách
    ↓
Phân tích theo metadata đánh số
    ↓
Kiểm tra cấu trúc số và loại đầu vào được hỗ trợ
    ↓
Tạo số chuẩn dùng trong hệ thống
    ↓
Đối chiếu liên hệ đã xác minh trong ngữ cảnh khôi phục
    ↓
Áp dụng điều kiện khôi phục và giới hạn gửi mã
    ↓
Gửi tới liên hệ được server cho phép
```

Cần phân biệt các câu hỏi ở mỗi tầng:

| Câu hỏi | Điều có thể kết luận |
| --- | --- |
| Chuỗi có thể phân tích được không? | Parser tìm được cấu trúc theo đầu vào và ngữ cảnh |
| Số có độ dài hoặc mẫu phù hợp metadata không? | Có mức độ phù hợp với kế hoạch đánh số được biết |
| Kênh SMS có được sản phẩm hỗ trợ không? | Chính sách và hạ tầng cho phép thử kênh tương ứng |
| Số có thuộc liên hệ khôi phục đủ điều kiện không? | Cần đối chiếu trạng thái tài khoản và liên hệ phía server |
| Người đang thao tác có đáp ứng yêu cầu khôi phục không? | Cần bằng chứng xác minh và quyết định rủi ro của giao dịch |

Một số được thư viện đánh giá hợp lệ không chứng minh rằng nó đang được cấp cho người dùng cụ thể hoặc có thể nhận tin ngay lúc này. [libphonenumber FAQ](https://github.com/google/libphonenumber/blob/master/FAQ.md) nêu rõ giới hạn này.

Phân loại số, khả năng chuyển phát và việc kiểm soát số là các thông tin khác nhau. Không cấp quyền đổi mật khẩu, thay MFA hoặc đăng ký passkey chỉ vì số đã được chuẩn hóa thành công.

## 7. Ví dụ Java: chỉ tạo bản hiển thị từ số chuẩn đã có

Đoạn mã sau nhận **số chuẩn đã được lưu theo hợp đồng của hệ thống**, rồi tạo cách trình bày. Nó minh họa tầng formatting; việc tiếp nhận đầu vào tùy ý và xác định quyền khôi phục nằm ở các tầng trước.

```java
import com.google.i18n.phonenumbers.NumberParseException;
import com.google.i18n.phonenumbers.PhoneNumberUtil;
import com.google.i18n.phonenumbers.PhoneNumberUtil.PhoneNumberFormat;
import com.google.i18n.phonenumbers.Phonenumber.PhoneNumber;

public final class RecoveryPhoneDisplay {
    public enum Style {
        INTERNATIONAL,
        NATIONAL
    }

    private static final PhoneNumberUtil PHONES =
            PhoneNumberUtil.getInstance();

    private RecoveryPhoneDisplay() {
    }

    public static String formatStoredNumber(String e164, Style style)
            throws NumberParseException {
        if (e164 == null || !e164.matches("\\+[1-9][0-9]{1,14}")) {
            throw new IllegalArgumentException("Expected canonical phone");
        }
        if (style == null) {
            throw new IllegalArgumentException("Display style is required");
        }

        PhoneNumber phone = PHONES.parse(e164, "ZZ");
        PhoneNumberFormat format = style == Style.NATIONAL
                ? PhoneNumberFormat.NATIONAL
                : PhoneNumberFormat.INTERNATIONAL;

        return PHONES.format(phone, format);
    }
}
```

Các chế độ `NATIONAL`, `INTERNATIONAL` và `E164` phục vụ những cách biểu diễn khác nhau trong [ví dụ chính thức của libphonenumber](https://github.com/google/libphonenumber#quick-examples).

Biểu thức chính quy trong mã chỉ bảo vệ hình dạng của hợp đồng chuỗi chuẩn. Nó không thay thế metadata đánh số hoặc xác minh quyền kiểm soát số. `ZZ` biểu thị ngữ cảnh vùng không xác định; chuỗi đã có `+` và mã gọi nên không cần suy vùng từ ngôn ngữ giao diện.

Việc chọn `NATIONAL` phải là một quyết định trình bày có ngữ cảnh rõ ràng. Nếu người dùng có thể nhầm vùng, ưu tiên hiển thị cả mã gọi hoặc tên vùng. Không chọn định dạng nội địa chỉ vì locale hiện tại có một hậu tố vùng giống hoặc khác số đã lưu.

Nếu formatting thất bại với một bản ghi cũ, không tự sửa số chuẩn hay đánh dấu liên hệ chưa xác minh. Hệ thống cần một cách hiển thị dự phòng phù hợp quyền xem và một đường xử lý dữ liệu riêng. Không ghi số đầy đủ hoặc nội dung exception chứa đầu vào vào log công khai.

## 8. Định dạng trong lúc nhập và sau khi nhập

Định dạng trong lúc gõ có thể giúp người dùng đọc các nhóm số, nhưng cũng có thể làm con trỏ nhảy, xóa nhầm ký tự hoặc phá thao tác dán. Trong luồng khôi phục, sự ổn định của thao tác nhập thường quan trọng hơn việc mọi phím gõ đều tạo ra chuỗi đẹp ngay lập tức.

Có thể giữ nguyên bản người dùng đang sửa, rồi hiển thị một bản xem trước sau khi số đã có đủ ngữ cảnh. Nếu dùng formatter trong lúc nhập, cần bảo toàn vị trí con trỏ, thao tác chọn vùng, xóa, dán và quá trình nhập của bộ gõ.

Không chặn phím theo cách chỉ cho điền từ trái sang phải. Người dùng phải sửa được một chữ số ở giữa chuỗi. Không tự gửi yêu cầu nhận OTP khi parser vừa nhận ra một số có vẻ hoàn chỉnh.

Khi đổi vùng trong bộ chọn, nếu đầu vào là số nội địa thì cách hiểu có thể thay đổi. Giao diện cần cho thấy kết quả và yêu cầu thao tác xác nhận phù hợp trước khi tiếp tục. Nếu đầu vào là số quốc tế có `+`, không âm thầm viết lại mã gọi để khớp bộ chọn.

Khi chỉ đổi ngôn ngữ giao diện, giữ nguyên giá trị số chuẩn và liên hệ đang được chọn. Nhãn “Số điện thoại” có thể đổi sang “Phone number”; đích nhận mã không được đổi theo.

## 9. Số đã che, khả năng truy cập và văn bản phải sang trái

Ở bước chọn kênh khôi phục, người dùng có thể chỉ cần thấy gợi ý như “Số điện thoại kết thúc bằng 0123”. Số lượng chữ số được lộ và việc hiển thị mã gọi phải theo chính sách tiết lộ thông tin của bước đó.

Masking cần thực hiện từ dữ liệu có cấu trúc hoặc số chuẩn, rồi tạo riêng gợi ý hiển thị. Không dùng công thức “giữ bốn ký tự cuối chuỗi đã format”, vì dấu cách, máy lẻ hoặc dấu phân nhóm có thể làm sai kết quả.

Nếu hai liên hệ có cùng các chữ số cuối, phải dùng ID liên hệ ổn định để phân biệt. Không coi gợi ý đã che là định danh duy nhất hoặc bằng chứng đủ để gửi mã.

Không giấu số đầy đủ chỉ bằng CSS rồi để nó trong `aria-label`, thuộc tính `data-*`, tooltip hoặc mã HTML được trả cho người chưa có quyền xem. Nhãn truy cập cũng phải tuân thủ cùng mức che thông tin.

Với giao diện dùng hướng viết phải sang trái, có thể cô lập gợi ý số theo hướng trái sang phải:

```html
<p dir="rtl">
  <span>رقم الهاتف:</span>
  <bdi dir="ltr">+1 ••• ••• 0123</bdi>
</p>
```

`bdi` giúp nội dung bên trong được xử lý tách biệt với văn bản xung quanh theo thuật toán hai chiều. Xem [MDN — bdi](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/bdi).

Nếu trình đọc màn hình cần một mô tả dễ hiểu hơn chuỗi ký hiệu che, có thể cung cấp câu đã dịch như “Số điện thoại kết thúc bằng 0123”. Phần mô tả đó không được chứa số đầy đủ. Với một số đầy đủ mà người dùng được phép sao chép, thao tác sao chép nên dùng dữ liệu số được xác định rõ, tránh mang theo ký tự định hướng vô hình từ lớp trình bày.

## 10. Ràng buộc an toàn khi dùng số cho khôi phục

**Định dạng không được đổi người nhận.** Sau khi server chọn liên hệ khôi phục đủ điều kiện, thao tác gửi lại mã phải bám vào liên hệ và giao dịch đó. Không tin một trường ẩn phía client chứa số mới chỉ vì giao diện đang hiển thị số đã che giống nhau.

Một thiết kế an toàn nên giữ các ràng buộc sau:

- So sánh bằng số chuẩn ở nơi cần đối chiếu, không so sánh bằng chuỗi hiển thị hoặc vài chữ số cuối.
- Gắn thử thách với giao dịch khôi phục và liên hệ được phép dùng; việc đổi liên hệ cần đi qua nhánh chính sách tương ứng.
- Chuẩn hóa nhất quán trước khi áp dụng hạn mức theo đích, để khác biệt dấu cách hay dấu ngoặc không tạo ra nhiều khóa độc lập.
- Bổ sung hạn mức theo tài khoản, giao dịch và tín hiệu lạm dụng phù hợp; một khóa theo số điện thoại không bao phủ mọi tình huống.
- Không để thông báo, dữ liệu trả về hoặc gợi ý masking tiết lộ liên hệ đã đăng ký ở bước mà người yêu cầu chưa được phép biết.
- Xử lý thay số, mất SIM hoặc không còn kiểm soát số như một tình huống khôi phục cần đánh giá riêng, thay vì chỉ sửa formatter.

Ngay cả khi một người nhận được OTP, quyền khôi phục vẫn phải xét theo chính sách của hệ thống. Một số điện thoại có thể được chuyển chủ hoặc thay đổi tình trạng sử dụng theo thời gian; không coi nó là định danh danh tính bất biến.

Máy lẻ, số ngắn và các đích ngoài phạm vi SMS thông thường cần hợp đồng riêng nếu sản phẩm muốn hỗ trợ. Không tự ghép chúng vào số chuẩn rồi giả định rằng nhà cung cấp gửi tin sẽ hiểu giống giao diện.

## 11. Những lỗi thiết kế dễ gặp

| Lỗi | Hệ quả trong luồng khôi phục | Cách thiết kế phù hợp hơn |
| --- | --- | --- |
| Dùng locale để thêm mã gọi | Gửi tới số khác khi người dùng đổi ngôn ngữ | Dùng số chuẩn đã có hoặc vùng nhập được chọn rõ ràng |
| Ép mọi số thành đúng 10 chữ số | Từ chối người dùng ngoài mẫu nội địa được giả định | Phân tích theo kế hoạch đánh số và phạm vi hỗ trợ |
| Lưu số bằng kiểu số nguyên | Mất dấu `+` và ý nghĩa biểu diễn | Lưu chuỗi chuẩn theo hợp đồng rõ ràng |
| Tự bỏ mọi số 0 đầu | Có thể đổi ý nghĩa số | Để parser có metadata xử lý đúng ngữ cảnh |
| Dùng chuỗi đã che làm đích gửi | Không xác định được chính xác liên hệ | Server chọn bản ghi liên hệ đủ điều kiện |
| Tin số đã normalize do client gửi | Client có thể thay đích | Server tự kiểm tra và ràng buộc với giao dịch |
| Cắt chuỗi thô ở mốc 15 ký tự | Làm mất chữ số vì có dấu phân nhóm | Tách giới hạn đầu vào và giới hạn số chuẩn |
| Hiển thị lỗi “số này không thuộc tài khoản” quá sớm | Có thể hỗ trợ dò liên hệ tài khoản | Dùng thông điệp phù hợp quyền tiết lộ của bước |

Thông báo lỗi về cú pháp có thể hướng dẫn trực tiếp: “Chọn vùng của số hoặc nhập mã gọi quốc tế bắt đầu bằng +”. Thông báo liên quan đến sự tồn tại của tài khoản hay liên hệ cần tuân thủ chính sách chống dò tài khoản; không gộp hai loại lỗi thành một quy tắc tiết lộ duy nhất cho mọi bước.

Khi metadata thư viện thay đổi, đó là thay đổi cách diễn giải hoặc trình bày dữ liệu, không phải bằng chứng người dùng đã xác minh lại số. Tránh tự động xóa liên hệ, đổi quyền khôi phục hoặc sửa hàng loạt số đã lưu chỉ từ một kết quả formatting khác trước.

## 12. Tình huống vận dụng

Một người dùng nói tiếng Việt có số khôi phục tại Hoa Kỳ và vừa mất thiết bị chứa ứng dụng MFA. Họ mở giao diện tiếng Việt, chọn phương án nhận mã qua số đã đăng ký rồi đổi giao diện sang tiếng Anh để làm theo hướng dẫn của bộ phận hỗ trợ.

Trong thiết kế phù hợp:

1. Tên phương thức và hướng dẫn thay đổi theo ngôn ngữ, còn ID liên hệ và số chuẩn giữ nguyên.
2. Giao diện dùng gợi ý đã che đủ để nhận ra liên hệ theo mức thông tin được phép lộ.
3. Việc hiển thị quốc tế hay nội địa chỉ thay cách đọc, không tạo lại đích gửi từ locale mới.
4. Nút gửi lại sử dụng giao dịch và liên hệ do server đã ràng buộc, không đọc ngược số từ chuỗi đã che.
5. Nếu người dùng không còn kiểm soát số, họ chuyển sang phương án khôi phục khác theo chính sách; formatter không cho phép thay số để nhận mã ngay.

Khi thiết kế localized phone formatting, hãy xác định rõ **ngữ cảnh dùng để hiểu số nhập, số chuẩn dùng để xử lý và thông tin được phép trình bày ở từng bước**. Giữ ba phần này nhất quán giúp bản địa hóa trải nghiệm mà vẫn bảo toàn đích khôi phục tài khoản.
