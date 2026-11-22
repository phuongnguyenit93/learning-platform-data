# Tổ chức khóa ổn định và chú thích ngữ cảnh cho người dịch

## Mục tiêu bài học

Trong ứng dụng Java đa ngôn ngữ, một màn hình có thể hiển thị nội dung từ các tệp tài nguyên `.properties`, thường thông qua `ResourceBundle`. **Khóa tài nguyên (resource key)** là định danh nối mã ứng dụng với bản dịch; **giá trị** là văn bản người dùng nhìn thấy. Nếu khóa thay đổi theo lời văn, bị tái sử dụng sai ý nghĩa hoặc thiếu giải thích ngữ cảnh, người dịch rất dễ tạo câu sai dù từng từ có vẻ đúng.

Sau bài học, bạn có thể:

- Đặt tên khóa theo **ý nghĩa và vị trí sử dụng** để mã Java, bản dịch và công cụ quản lý dịch thuật cùng tham chiếu ổn định.
- Giải thích tại sao thay đổi câu chữ thường chỉ nên sửa **giá trị**, và khi nào thay đổi **ý nghĩa** đòi khóa mới.
- Ghi chú ngữ cảnh cho người dịch: vị trí hiển thị, hành động, đối tượng, giọng văn, placeholder, giới hạn chiều dài và ví dụ.
- Hiểu quy tắc comment của tệp Java `.properties`, cùng giới hạn: comment là thông tin trong nguồn, **không trở thành giá trị truy cập qua `ResourceBundle`**.
- Quản lý khóa giữa nhiều locale, phát hiện thiếu khóa/placeholder và tránh để fallback che khuất bản dịch thiếu.
- Áp dụng các nguyên tắc trên bằng ví dụ Java 17+ có thể biên dịch và chạy.

Đây là bài về **thiết kế và bảo trì tệp tài nguyên**. Nó không yêu cầu xây một hệ thống dịch thuật mới hay thay đổi cơ chế lựa chọn `Locale`.

## 1. Khóa tài nguyên là hợp đồng ổn định

Xem một dòng trong `messages_vi.properties`:

```properties
checkout.action.pay=Thanh toán
```

Ở đây:

- `checkout.action.pay` là **key**: định danh mà mã nguồn dùng để tìm tài nguyên.
- `Thanh toán` là **value**: văn bản tiếng Việt dành cho người dùng.
- `checkout` mô tả tính năng, `action` là loại nội dung, `pay` là ý định hành động.

Mã Java:

```java
ResourceBundle bundle = ResourceBundle.getBundle(
        "messages", Locale.forLanguageTag("vi-VN"));
String label = bundle.getString("checkout.action.pay");
```

Đây là đoạn minh họa đặt trong một phương thức; đã có import `java.util.ResourceBundle` và `java.util.Locale`. Tệp `messages_vi.properties` cần nằm đúng vị trí classpath mà base name `messages` tham chiếu.

Nếu nhóm nội dung đổi nhãn giao diện từ “Thanh toán” sang “Tiến hành thanh toán”, **khóa vẫn là `checkout.action.pay`**; chỉ đổi value. Điều đó giúp Java code, bài test, thống kê thiếu dịch và công cụ dịch thuật không phải đổi theo từng lần chỉnh câu chữ.

Ngược lại, nếu một nút trước đây **thanh toán ngay** nhưng được sửa thành **lưu đơn hàng để thanh toán sau**, ý nghĩa hành động đã khác: nên tạo khóa mới, ví dụ `checkout.action.saveForLater`, rồi cập nhật mã gọi. Giữ khóa `pay` cho hành động “lưu” sẽ gây hiểu nhầm cho những người đọc tệp, nhất là người dịch.

### Điều gì khiến một key được coi là ổn định?

Một key tốt mô tả **vai trò ngữ nghĩa tương đối lâu dài**, không phụ thuộc câu dịch cụ thể. Nó nên:

1. Có ý nghĩa đủ rõ để phân biệt với các key khác.
2. Được dùng nhất quán bởi mã và tài nguyên nhiều locale.
3. Không cần đổi khi cải thiện từ ngữ nhưng **có thể đổi** khi nội dung đổi ngữ nghĩa.
4. Tránh phụ thuộc thứ tự màn hình, số dòng, tên người hoặc bản dịch của một locale.
5. Có phạm vi rõ ràng: đội nào sở hữu và được dùng ở vị trí nào.

Key là một phần của hợp đồng **mã nguồn ↔ tài nguyên ↔ quy trình dịch thuật**. Vì thế đổi key tương đương đổi tên điểm truy cập: phải rà lại nơi dùng và các bản địa phương hóa.

## 2. Quy tắc đặt tên có cấu trúc

Không có quy tắc đặt tên key duy nhất bắt buộc bởi `ResourceBundle`. Tuy nhiên, dự án nên định nghĩa một convention và tuân theo nhất quán.

Một kiểu phổ biến:

```text
<feature>.<element-or-content-kind>.<semantic-intent>
```

Ví dụ:

| Key đề xuất | Ý định |
| --- | --- |
| `checkout.action.pay` | Nhãn nút thực hiện thanh toán |
| `checkout.action.cancel` | Nhãn nút hủy bước thanh toán |
| `checkout.summary.itemCount` | Thông điệp số lượng sản phẩm trong tóm tắt đơn hàng |
| `checkout.error.paymentDeclined` | Thông báo giao dịch bị từ chối |
| `account.error.sessionExpired` | Thông báo phiên đăng nhập hết hạn |
| `profile.field.displayName.label` | Nhãn trường tên hiển thị |
| `profile.field.displayName.hint` | Hướng dẫn dưới trường tên hiển thị |
| `navigation.menu.orders` | Nhãn mục điều hướng tới đơn hàng |

Điều quan trọng không nằm ở số dấu chấm mà ở tính **ổn định, dễ tìm và mô tả đúng ý định**. Một nhóm có thể chọn `feature.component.purpose` hoặc một convention khác. Không cần cố ép mọi key vào ba cấp nếu việc đó tạo từ dài, mơ hồ hoặc khó dùng.

Các key nên dễ tìm bằng tìm kiếm văn bản trong codebase, dễ nhóm trong công cụ dịch thuật và dễ suy ra trách nhiệm của tính năng.

### Đối chiếu cách đặt tên

| Khóa yếu | Vấn đề | Hướng cải thiện |
| --- | --- | --- |
| `button1` | Phụ thuộc vị trí, không biết nút làm gì | `checkout.action.pay` |
| `label_12` | Số thứ tự không mang ngữ nghĩa | `profile.field.email.label` |
| `click_here` | Lấy lời văn tiếng Anh làm định danh | `account.action.verifyEmail` |
| `error` | Quá chung, các loại lỗi có ngữ cảnh khác nhau | `checkout.error.paymentDeclined` |
| `hello_text_new_v2` | Chứa trạng thái chỉnh sửa, không bền | `home.welcome.greeting` |
| `confirm` dùng cho mọi nút | Chữ “confirm” có thể là xác nhận hủy, xóa, thanh toán | Tách khóa theo hành động thực |
| `checkout.title.2026` | Gắn key vào năm khi ngữ nghĩa không phụ thuộc năm | `checkout.page.title` |

Có thể cố ý **dùng chung key** khi cùng một thông điệp thực sự có cùng ý nghĩa và cùng hợp đồng hiển thị. Nhưng hai chỗ cùng dùng chữ “Mở”, “Lưu”, “Tiếp tục” ở ngữ cảnh khác nhau chưa đủ để kết luận chúng nên dùng chung key: cách dịch phụ thuộc đối tượng, giống/ngôi, dạng động từ, độ dài nút, văn phong hoặc vị trí trong câu.

**Không dùng chính chuỗi tiếng Anh làm key chỉ vì bản gốc đang là tiếng Anh.** Khi copy thay đổi, tên key kiểu `Pay now` rất dễ trở nên sai lệch và có thể khó quản lý trong mã.

## 3. Một giá trị có thể có nhiều nghĩa — vì sao người dịch cần ngữ cảnh?

Xét chuỗi tiếng Anh `"Open"`:

- Trong file manager, có thể là **mở tệp**.
- Trong trạng thái đơn hàng, có thể là **đang mở/chưa đóng**.
- Trên bảng giờ hoạt động, có thể là **đang mở cửa**.

Nếu chỉ nhận:

```properties
common.open=Open
```

người dịch thiếu thông tin để chọn từ chính xác. Đặc biệt, một từ tiếng Anh có thể có nhiều dạng dịch tùy loại từ, số lượng, giống và cấu trúc ngữ pháp ở ngôn ngữ khác.

Tách key theo ngữ nghĩa:

```properties
file.action.open=Open
order.status.open=Open
store.status.open=Open
```

Các value tiếng Anh giống nhau nhưng ý nghĩa khác nhau. Những ngôn ngữ khác có thể cần ba bản dịch khác nhau.

### Chú thích gì là đủ?

Mỗi key dễ gây hiểu nhầm nên có các thông tin thực sự ảnh hưởng đến bản dịch:

- **Nơi xuất hiện:** màn hình, dialog, email, tiêu đề, aria-label, thông báo lỗi, tooltip.
- **Chức năng:** người dùng bấm để làm gì hoặc trạng thái nào đang được mô tả.
- **Đối tượng:** “Open” áp dụng cho tệp, đơn hàng, cửa hàng hay tài khoản.
- **Giọng văn:** thân thiện, trang trọng, cảnh báo nghiêm túc; tránh thay đổi giọng văn ngẫu nhiên giữa màn hình.
- **Độ dài và ràng buộc bố cục:** nhãn nút có không gian nhỏ hay mô tả có thể nhiều câu; chỉ nêu giới hạn ký tự nếu giao diện thật sự có giới hạn.
- **Tham số:** `{0}` là số lượng gì, `{1}` là tên người hay thời gian; đơn vị và định dạng do đâu quyết định.
- **Ví dụ:** câu có thể được hiển thị với dữ liệu thật đã ẩn danh.
- **Điều cần giữ nguyên:** tên sản phẩm, biến mẫu, URL/markup được cho phép, dấu câu hoặc quy định pháp lý đặc biệt nếu có.

Ghi chú nên ngắn và chính xác, viết từ góc nhìn **đối tượng đọc là người dịch**. Một comment kiểu “Translation here” không mang thông tin. Một comment như “Nhãn nút ở màn hình thanh toán; người dùng bấm để thực hiện giao dịch ngay” hữu ích hơn nhiều.

## 4. Comment trong Java .properties

Java `.properties` cho phép dòng comment bắt đầu bằng `#` hoặc `!` (sau phần whitespace đầu dòng được bỏ qua theo cú pháp properties). Ví dụ:

```properties
# TRANSLATORS: Label on the primary checkout button.
# Action: starts payment immediately; not "save for later".
checkout.action.pay=Pay now

# TRANSLATORS: Shown above the cart items.
# {0} = total number of line items, already calculated by the app.
checkout.summary.itemCount=Items: {0}
```

Tệp trong ví dụ có hai key; các dòng comment giúp người dịch hiểu ngữ cảnh.

**Điểm quan trọng:** `PropertyResourceBundle` không biến các comment đó thành tài nguyên có thể đọc bằng key. Nếu Java gọi `getString("TRANSLATORS")` sẽ không nhận một metadata riêng cho comment; thông tin dành cho người dịch nằm trong file nguồn và công cụ quản lý bản dịch.

Một số công cụ xuất/nhập bản dịch có thể làm mất comment hoặc di chuyển comment, nên pipeline dịch thuật cần kiểm tra việc bảo toàn chú thích. Nếu nhóm dùng nền tảng dịch thuật, hãy map các trường mô tả/context của nền tảng sang source comment hoặc metadata ổn định, thay vì chỉ hy vọng comment luôn đi theo các lần chuyển đổi.

### Comment khác với giá trị hiển thị

```properties
# This is a translator note; users never see it.
account.error.sessionExpired=Your session has expired
```

Giá trị được hiển thị chỉ là `Your session has expired`. Dòng comment không được đưa vào output và không thay đổi cách `ResourceBundle` tra key.

Đừng giấu thông tin nghiệp vụ cần runtime xử lý trong comment vì Java không tự đọc comment sau khi `PropertyResourceBundle` đã parse. Metadata dùng ở runtime phải có thiết kế riêng, thay vì dựa vào dòng `#`.

## 5. Mã nguồn, bản gốc và bản dịch nên cùng một hợp đồng khóa

Một cấu trúc tài nguyên quen thuộc trong ứng dụng Java:

```text
src/main/resources/
  messages.properties
  messages_vi.properties
  messages_fr.properties
  messages_ja.properties
```

- `messages.properties` có thể đóng vai trò **root/default bundle** và là tập key tham chiếu của dự án.
- `messages_vi.properties` chứa bản dịch tiếng Việt.
- `messages_fr.properties` chứa bản dịch tiếng Pháp.
- `messages_ja.properties` chứa bản dịch tiếng Nhật.

Trong ứng dụng có package, có thể dùng base name `com.example.i18n.messages` và đặt resource tại `com/example/i18n/messages*.properties`. Tên tệp ResourceBundle truyền thống dùng `_` để ghép phần locale candidate như `messages_vi_VN.properties`; còn language tag truyền qua API `Locale.forLanguageTag("vi-VN")` dùng dấu `-`.

Cùng một key nên mang **cùng ý nghĩa** ở mọi locale:

```properties
# messages.properties
account.error.sessionExpired=Your session has expired.
```

```properties
# messages_vi.properties
account.error.sessionExpired=Phiên đăng nhập của bạn đã hết hạn.
```

Không nên để cùng key có nghĩa “hết hạn phiên” ở tiếng Anh nhưng “sai mật khẩu” ở một ngôn ngữ khác. Đó là lỗi tương thích ngữ nghĩa, dù các tệp không hề sai cú pháp.

### Có cần mọi tệp đều có tất cả key?

Về mặt runtime, `ResourceBundle` có cơ chế tìm key trong parent/fallback; một bản dịch thiếu key vẫn có thể được lấy từ bundle cha. Nhưng về **chất lượng bản địa hóa**, không nên coi “không ném exception” là bằng chứng mọi bản dịch đầy đủ.

Cần phân biệt:

1. **Khóa được định nghĩa trong chính locale đó.**
2. **Khóa lấy từ root/parent bundle khi locale thiếu.**
3. **Khóa không tìm được ở bất kỳ mức fallback nào.**

Trường hợp 2 có thể làm UI pha lẫn tiếng Anh và tiếng Việt. Nếu sản phẩm yêu cầu dịch hoàn chỉnh, pipeline QA phải so sánh **tập khóa có thật của từng tệp nguồn** với tập khóa tham chiếu, thay vì chỉ gọi `ResourceBundle.getBundle(...).getString(key)` và thấy có giá trị.

Một số tổ chức cho phép vài key fallback có chủ đích (tên riêng hoặc nội dung chưa dịch); các ngoại lệ nên được theo dõi minh bạch, không ngầm xem là thành công.

## 6. Giữ key ổn định trong vòng đời thay đổi sản phẩm

### Thay lời văn nhưng giữ ý nghĩa

Giả sử key:

```properties
checkout.action.pay=Pay now
```

Nhóm nội dung muốn đổi thành:

```properties
checkout.action.pay=Complete payment
```

Nếu chức năng của nút vẫn là thực hiện thanh toán, **giữ khóa**. Sửa bản gốc, đánh dấu bản dịch cần rà soát, cập nhật comment nếu ngữ cảnh hiển thị thay đổi. Không có lý do kỹ thuật để đổi thành `checkout.action.completePayment` chỉ vì câu tiếng Anh được viết lại.

### Thay ý nghĩa: tạo key mới

Nếu nút đổi thành “Đặt lịch thanh toán”, nó không còn biểu thị thực hiện thanh toán ngay. Tạo một key mới như `checkout.action.schedulePayment`, cung cấp mô tả mới và cập nhật tham chiếu Java. Giữ khóa cũ khi nó còn được dùng; chỉ xóa sau khi kiểm tra không còn nơi sử dụng và quy trình dịch đã chuyển đổi đầy đủ.

### Đổi tên hoặc di chuyển chức năng

Khi module được đổi tên nhưng chức năng vẫn như cũ, không cần đổi toàn bộ key ngay chỉ để làm đẹp namespace. Cân nhắc:

- Có phải hợp đồng public của resource đã được thành phần khác tham chiếu?
- Thay đổi tên key có khiến bản dịch bị coi như nội dung mới không?
- Có thể giữ alias/migration trong một phiên phát hành không?
- Có người dịch và công cụ thống kê phụ thuộc ID cũ hay không?

Đừng tái sử dụng một key đã nghỉ cho ý nghĩa mới: dữ liệu translation memory hoặc bản dịch còn tồn tại có thể được áp vào ngữ cảnh không liên quan.

### Quy trình review một thay đổi key

1. Xác định ý nghĩa mới và vị trí hiển thị.
2. Kiểm tra tất cả call site của key hiện tại.
3. Chọn sửa value, thêm key mới hoặc migration rõ ràng.
4. Cập nhật nguồn tham chiếu, tất cả bản dịch liên quan và comment.
5. Kiểm tra key thừa/mất, placeholder, định dạng, giao diện.
6. Chỉ loại bỏ key cũ khi không còn người dùng của nó; không “dọn khóa” bằng cách xóa hàng loạt không được kiểm chứng.

## 7. Placeholder là một phần của hợp đồng dịch thuật

Chuỗi dịch thường chứa chỗ trống cho dữ liệu runtime. Với `java.text.MessageFormat`, các placeholder có cú pháp như `{0}`, `{1}` và có thể có định dạng phụ.

Ví dụ:

```properties
# TRANSLATORS: Summary line below the shopping cart.
# {0} = the number of products in the cart.
checkout.summary.itemCount=Items: {0}
```

Bản tiếng Việt:

```properties
# TRANSLATORS: Dòng tóm tắt ngay dưới giỏ hàng.
# {0} = số sản phẩm trong giỏ, do ứng dụng tính.
checkout.summary.itemCount=Số sản phẩm: {0}
```

Hai câu có thể khác trật tự từ nhưng đều giữ `{0}` để chương trình thay đúng số lượng. Nếu một bản dịch xóa hoặc đổi nhầm thành `{1}`, dữ liệu runtime có thể bị mất hoặc hiển thị sai.

### Khi có nhiều tham số

```properties
# {0} = buyer display name; {1} = order identifier.
order.notification.created=Hello {0}, order {1} is ready.
```

Người dịch cần biết **vai trò của từng chỉ số**, đặc biệt khi thứ tự từ trong ngôn ngữ đích khác tiếng Anh. Có thể đảo vị trí `{0}` và `{1}` trong bản dịch nếu phù hợp ngữ pháp, nhưng không được đổi ý nghĩa của chúng.

Đừng yêu cầu người dịch tự sửa số placeholder hoặc biến template nếu chưa có thay đổi hợp đồng trong mã. Nếu nội dung gốc thay đổi danh sách tham số, đó là thay đổi cần QA tương ứng ở các locale.

### MessageFormat không phải printf, và dấu nháy có ý nghĩa

`MessageFormat` dùng cú pháp khác `String.format`. `{0}` không giống `%s`. `MessageFormat` còn có quy tắc đặc biệt cho dấu nháy đơn `'` và ngoặc nhọn. Ví dụ, muốn một dấu nháy đơn hiển thị đúng ở một pattern MessageFormat có thể cần viết thành `''`.

Nếu bản dịch có dấu nháy đơn, dấu ngoặc nhọn hoặc mẫu số/ngày có định dạng, nên chạy test bằng **chính formatter được dùng trong runtime**. Không nên kiểm thử bằng thay chuỗi thủ công như `replace("{0}", value)` rồi cho rằng tương đương MessageFormat.

Đối với số lượng số ít/số nhiều, chỉ thay một placeholder không luôn đủ cho mọi ngôn ngữ. Có thể cần quy tắc plural theo thư viện i18n phù hợp hoặc pattern được thiết kế riêng; không suy từ cấu trúc tiếng Anh sang mọi locale.

### Đừng đưa văn bản người dùng vào key

Key là định danh ổn định, vì vậy không tạo key kiểu:

```text
order.error.paymentDeclinedForJohn
cart.items.3
welcome.Alice
```

Thay vào đó dùng một key với placeholder để dữ liệu runtime tách khỏi nội dung dịch. Điều này tránh bùng nổ key, dễ giữ cấu trúc ngôn ngữ và tránh chèn dữ liệu cá nhân vào ID tài nguyên.

## 8. Ví dụ hoàn chỉnh Java 17+: comment, khóa ổn định và MessageFormat

Ta xây dựng một họ bundle `messages` gồm root bundle, bản tiếng Việt và chương trình Java. Ví dụ chạy được trên Java 17+; các message được lấy theo key, và comment trong properties giúp người dịch hiểu ngữ cảnh nhưng không trở thành key.

Tạo **ba tệp trong cùng một thư mục**, lưu các file `.properties` bằng UTF-8.

### Tệp messages.properties

```properties
# TRANSLATORS: Primary button on the checkout screen.
# Action: immediately proceeds to payment, not saving for later.
checkout.action.pay=Pay now

# TRANSLATORS: Summary line shown below the cart.
# {0} = number of products currently in the cart.
checkout.summary.itemCount=Items: {0}

# TRANSLATORS: Displayed when a logged-in session expires.
account.error.sessionExpired=Your session has expired.

# TRANSLATORS: Link text opening the refund policy.
checkout.link.refundPolicy=Refund policy
```

### Tệp messages_vi.properties

```properties
# TRANSLATORS: Nút chính ở màn hình thanh toán, thực hiện thanh toán ngay.
checkout.action.pay=Thanh toán ngay

# TRANSLATORS: Dòng tóm tắt dưới giỏ hàng.
# {0} = số sản phẩm trong giỏ.
checkout.summary.itemCount=Số sản phẩm: {0}

# TRANSLATORS: Hiển thị khi phiên đăng nhập hết hạn.
account.error.sessionExpired=Phiên đăng nhập đã hết hạn.
```

Cố ý chưa dịch `checkout.link.refundPolicy` ở bản tiếng Việt để minh họa hành vi fallback từ root bundle. Trong sản phẩm thực tế, đây là một key cần được phát hiện trong báo cáo thiếu dịch.

### Tệp ResourceKeyDemo.java

```java
import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

public class ResourceKeyDemo {
    public static void main(String[] args) {
        Locale locale = Locale.forLanguageTag("vi-VN");
        ResourceBundle bundle = ResourceBundle.getBundle("messages", locale);

        String button = bundle.getString("checkout.action.pay");
        String pattern = bundle.getString("checkout.summary.itemCount");
        String summary = new MessageFormat(pattern, locale)
                .format(new Object[] {3});

        System.out.println(button);
        System.out.println(summary);
        System.out.println(
                bundle.getString("account.error.sessionExpired"));
        System.out.println(
                bundle.getString("checkout.link.refundPolicy"));

        System.out.println(bundle.containsKey("TRANSLATORS"));
    }
}
```

Biên dịch và chạy từ thư mục chứa cả ba tệp:

```bash
javac -encoding UTF-8 ResourceKeyDemo.java
java -cp . ResourceKeyDemo
```

Stdout:

```text
Thanh toán ngay
Số sản phẩm: 3
Phiên đăng nhập đã hết hạn.
Refund policy
false
```

**Giải thích từng dòng:**

1. `checkout.action.pay` lấy giá trị từ `messages_vi.properties`; key trong Java không chứa chữ tiếng Việt hay văn bản nút.
2. `checkout.summary.itemCount` giữ tham số `{0}`, còn `MessageFormat` thay bằng số `3`.
3. `account.error.sessionExpired` lấy câu tiếng Việt theo cùng key ngữ nghĩa ở hai locale.
4. `checkout.link.refundPolicy` không có trong file tiếng Việt; `ResourceBundle` tìm được giá trị ở bundle cha/root. Ví dụ có thể chạy nhưng **bản dịch chưa hoàn thiện**.
5. `containsKey("TRANSLATORS")` trả `false` vì các comment `# TRANSLATORS: ...` là metadata nguồn, không tạo key `TRANSLATORS`.

Ví dụ dùng locale tường minh nên không cần thay đổi `Locale.setDefault` của JVM. Java 17+ đọc tệp `.properties` trong `ResourceBundle` bằng cơ chế hỗ trợ UTF-8; tránh soạn file dưới encoding khác mà không kiểm soát.

### Khi đặt trong dự án thật

Với dự án dùng Maven hoặc Gradle, thường lưu các tệp tại `src/main/resources/messages.properties` và `src/main/resources/messages_vi.properties`, còn lớp Java ở thư mục source tương ứng. Nếu chọn đặt bundle trong package, dùng đúng đường dẫn resource và base name đầy đủ. Các tệp phải xuất hiện trong classpath runtime; chỉ lưu chúng ở thư mục làm việc nhưng không đóng gói có thể gây `MissingResourceException`.

Trong môi trường có module system, class loader riêng hoặc `ResourceBundle.Control` tùy biến, cần kiểm tra thêm cơ chế tải tài nguyên tương ứng. Ví dụ ở đây dựa trên classpath mặc định.

## 9. Giữ chú thích đồng bộ với thay đổi

Comment sai đôi khi còn nguy hiểm hơn comment thiếu. Giả sử:

```properties
# Button opens the refund details, no payment is performed.
checkout.action.pay=Pay now
```

Tên key, value và comment không thống nhất về hành động. Người dịch có thể chọn bản dịch về “xem chính sách hoàn tiền”, trong khi mã Java vẫn gọi key cho nút thanh toán.

Khi cập nhật:

- **Nội dung hiển thị:** rà soát xem comment còn mô tả đúng ngữ cảnh không.
- **Chức năng sản phẩm:** xác định có phải tạo key mới và viết comment mới không.
- **Placeholder:** cập nhật mô tả vị trí và ý nghĩa tham số, kiểm thử số lượng/thứ tự tham số.
- **Giới hạn giao diện:** chỉ cập nhật khi ràng buộc UI thực sự thay đổi; tránh gán giới hạn cứng không có cơ sở.
- **Ảnh chụp màn hình hoặc liên kết tham khảo:** nếu công cụ dịch thuật hỗ trợ, gắn đúng màn hình và duy trì liên kết sống qua việc thiết kế lại UI.

Trong review, người dịch nên nhận được **ngữ cảnh đủ để quyết định cách diễn đạt** mà không phải tìm toàn bộ Java source. Chú thích tốt giúp giảm số vòng hỏi đáp và bản dịch sai ý, nhưng không thay thế việc kiểm tra giao diện thật.

## 10. Kiểm tra chất lượng và tự động hóa

### A. So sánh tập khóa của từng locale

Tập khóa trong `messages.properties` là mốc tham chiếu nếu dự án chọn root bundle làm nguồn chính. Với mỗi file ngôn ngữ:

- **Missing keys:** có ở root nhưng không được định nghĩa trong file đó.
- **Extra keys:** có trong file ngôn ngữ nhưng không còn trong root hoặc không được cho phép.
- **Duplicate keys:** xuất hiện lặp trong cùng file, khiến một giá trị có thể che giá trị khác.
- **Empty values:** có key nhưng value rỗng; có thể hợp lệ trong vài ngữ cảnh, cần chính sách.
- **Stale comments:** mô tả sai hành động hoặc placeholder.
- **Orphan keys:** key tồn tại trong resource nhưng không còn call site thực tế; không xóa máy móc khi có truy cập động.

Để kiểm tra thiếu dịch, công cụ nên đọc **key được khai báo trong từng file** thay vì chỉ hỏi `ResourceBundle.containsKey(key)`. Lý do: `containsKey` có thể xem xét parent chain, nên một key thiếu trong file tiếng Việt vẫn hiện là tồn tại qua fallback root.

Các thư viện đọc properties cũng có thể ghi đè key trùng và làm mất thông tin “đã khai báo hai lần”. Muốn phát hiện duplicate chính xác, công cụ lint nên phân tích **nguồn file thô** (bao gồm escape và continuation theo đúng cú pháp) thay vì chỉ xét map kết quả cuối cùng.

### B. Kiểm tra placeholder, kiểu dữ liệu và dấu nháy

Nếu mã gọi `new MessageFormat(pattern, locale)`, việc kiểm thử nên:

1. Parse pattern của **từng locale được hỗ trợ** bằng `MessageFormat` tương ứng.
2. Xác định các placeholder mong đợi từ hợp đồng mã và source.
3. Phát hiện thiếu/thừa/sai chỉ số tham số, kiểm tra kiểu dữ liệu cho number/date/time khi cần.
4. Xác nhận một vài kết quả với input mẫu, bao gồm ký tự đặc biệt và giá trị biên.
5. Kiểm tra các pattern sử dụng dấu nháy đơn và ngoặc nhọn vì dễ tạo lỗi dịch thuật.

Không thể áp quy tắc “placeholder phải có thứ tự giống hệt bản gốc” cho mọi ngôn ngữ: bản dịch có thể đảo chỗ `{0}` và `{1}` để đúng ngữ pháp. Điều cần giữ là **cùng ý nghĩa và tập tham số hợp lệ**.

### C. Kiểm tra văn bản trong giao diện thật

Một bản dịch có thể đúng trong file nhưng vẫn gây:

- Cắt chữ ở nút, tab, thanh điều hướng.
- Câu thiếu mạo từ/hậu tố vì không biết ngữ cảnh.
- Tên người hoặc số bị ghép sai trật tự.
- Lỗi hiển thị dấu, font, direction hoặc ký tự đặc biệt.
- Câu không nhất quán giọng văn giữa màn hình và email.

Vì vậy, QA tệp tài nguyên và QA UI bổ sung cho nhau. Nếu có kiểm tra hình ảnh/screenshot, hãy cung cấp cho người dịch đúng màn hình và trạng thái, đặc biệt ở các key dễ hiểu nhầm.

### D. Quy ước CI có thể áp dụng

Một pipeline tối thiểu có thể yêu cầu:

1. Không có lỗi cú pháp properties hoặc lỗi mã hóa UTF-8.
2. Không có duplicate key ngoài danh sách ngoại lệ được phê duyệt.
3. Không có placeholder hỏng theo formatter đang dùng.
4. Mọi key được dùng trong mã đều có source key hợp lệ, trừ khi truy cập động được khai báo riêng.
5. Mọi key mới có ngữ cảnh đầy đủ ở nơi cần thiết.
6. Tỷ lệ hoàn thành bản dịch được báo cáo từ **key thật trong từng locale**, không tính fallback như đã dịch.
7. Các thay đổi ý nghĩa có migration key minh bạch.

Không nhất thiết mọi lỗi đều phải chặn release giống nhau. Có thể phân cấp thiếu bản dịch, key không còn dùng, lỗi placeholder và lỗi cú pháp theo mức độ ảnh hưởng. Nhưng **sự khác nhau giữa bản dịch thật và fallback** phải luôn nhìn thấy trong báo cáo.

## 11. Những lỗi phổ biến

| Sai lầm | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Dùng `button1` hoặc `label42` | Không thể suy ra ý nghĩa của key | Đặt tên theo feature và chức năng |
| Dùng câu tiếng Anh nguyên văn làm key | Copy thay đổi khiến định danh sai lệch | Tách key ổn định khỏi value hiển thị |
| Đổi key mỗi khi chỉnh văn bản | Mất lịch sử dịch thuật, tăng công di chuyển | Giữ key khi ngữ nghĩa không đổi |
| Dùng lại key cũ cho chức năng mới | Bản dịch cũ áp dụng sai ngữ cảnh | Tạo key mới, cập nhật call site |
| Gộp mọi `common.ok`, `common.open`, `common.save` | Mất ngữ cảnh của hành động và loại từ | Chỉ tái sử dụng khi thật sự cùng ý nghĩa |
| Không mô tả placeholder `{0}` | Người dịch có thể bỏ, đảo sai hoặc sửa cú pháp | Ghi ý nghĩa và ví dụ tham số |
| Coi comment `#` là runtime metadata | Code không thể truy xuất comment qua `ResourceBundle` | Dùng comment cho quy trình dịch, schema riêng nếu runtime cần |
| Chỉ test `bundle.getString(key)` | Root fallback che key dịch bị thiếu | So sánh tập key khai báo trong file của locale |
| Đổi `.properties` nhưng không kiểm tra encoding | Ký tự tiếng Việt bị sai khi đóng gói hoặc đọc | Dùng UTF-8 và test Unicode trên runtime |
| Tưởng đổi chính tả nguồn là key mới | Phát sinh duplicate và thiếu dịch không cần thiết | Giữ key, đánh dấu giá trị cần re-translate |
| Tự ghép chuỗi dịch để tạo câu hoàn chỉnh | Ngữ pháp, thứ tự và plural khó dịch | Thiết kế thông điệp đầy đủ có placeholder rõ nghĩa |
| Bỏ kiểm tra sau khi nhập từ công cụ dịch | Comment hoặc placeholder có thể bị mất | Lint và kiểm thử output sau import |

## 12. Bài tập thực hành

**Bài 1 — Tách key theo ý nghĩa.** Một ứng dụng có ba màn hình: mở file, xem trạng thái “Open” của đơn hàng và xem cửa hàng đang mở cửa. Hãy đề xuất ba key có ngữ nghĩa riêng và viết comment giúp người dịch không nhầm chúng.

**Bài 2 — Giữ key hay đổi key?** Nút `checkout.action.pay` đổi value từ “Pay now” sang “Complete payment” nhưng vẫn thanh toán ngay. Bạn nên giữ key hay tạo key mới? Sau đó sản phẩm đổi hành động thành “Schedule payment for next week”; quyết định có đổi không và giải thích lý do.

**Bài 3 — Placeholder.** Thông báo có `order.status.ready=Order {0} is ready for {1}`, trong đó `{0}` là mã đơn và `{1}` là tên người nhận. Viết hai dòng comment mô tả rõ tham số và giải thích vì sao người dịch có thể thay đổi thứ tự placeholder khi ngôn ngữ yêu cầu.

**Bài 4 — Phát hiện thiếu dịch.** Trong ví dụ `ResourceKeyDemo`, tại sao `getString("checkout.link.refundPolicy")` vẫn chạy và trả “Refund policy”? Nêu cách phát hiện key này **chưa có bản dịch tiếng Việt** ngay cả khi lời gọi không phát sinh exception.

**Bài 5 — Đánh giá comment.** So sánh hai comment `# label text` và `# Button at checkout; pressing it starts payment immediately.`. Comment nào hữu ích hơn và còn thiếu thông tin gì nếu nút có giới hạn chiều rộng?

## 13. Ghi nhớ

**Khóa tài nguyên là một định danh hợp đồng ổn định; value là câu chữ có thể thay đổi theo locale và theo chỉnh sửa nội dung.** Thiết kế key theo ý nghĩa, không theo thứ tự hiển thị hoặc nguyên văn tiếng Anh. Hai chuỗi nhìn giống nhau vẫn có thể cần hai key nếu ngữ cảnh khác; key cũ không nên được tái sử dụng cho hành động mới.

**Chú thích dành cho người dịch giải thích ý nghĩa trong ngữ cảnh**, đặc biệt là nơi hiển thị, chức năng, đối tượng và placeholder. Trong `.properties`, comment `#`/`!` hỗ trợ quy trình biên dịch bản dịch nhưng không thể đọc như key/value qua `ResourceBundle`.

Cuối cùng, hãy kiểm soát tính đồng bộ giữa source và các bản dịch bằng so sánh tập khóa, kiểm tra placeholder và QA giao diện. `ResourceBundle` có thể fallback thành công ngay cả khi locale được yêu cầu đang thiếu bản dịch; hệ thống kiểm thử phải nhìn thấy điều đó để sản phẩm không vô tình hiển thị nội dung lẫn ngôn ngữ.
