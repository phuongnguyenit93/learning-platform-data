# Đổi ngôn ngữ khi đang chạy và làm mới dữ liệu đã định dạng trong Java

## 1. Đổi ngôn ngữ trong ứng dụng đang hoạt động là gì?

Giả sử một ứng dụng Java đang hiển thị:

~~~text
[en-US] Orders
Welcome, Lan!
Date: March 5, 2025
Quantity: 1,234.50
~~~

Người dùng bấm **Tiếng Việt** mà không khởi động lại. Giao diện phải cập nhật nhãn, thông điệp và định dạng:

~~~text
[vi-VN] Đơn hàng
Xin chào, Lan!
Ngày: 5 tháng 3, 2025
Số lượng: 1.234,50
~~~

Đây không chỉ là thay văn bản `Orders` bằng `Đơn hàng`. Việc chọn locale mới có thể tác động:

- Nhãn, tiêu đề, menu, button, tooltip, placeholder, thông báo lỗi và trợ năng.
- Cách hiển thị số, phần trăm, đơn vị tiền, ngày giờ và tên tháng.
- Thông điệp có tham số, thứ tự tham số, plural và lựa chọn cách diễn đạt.
- Header bảng, cột số liệu, nhãn trục biểu đồ, mô tả trạng thái trống, thông báo đang mở.
- Bố cục LTR/RTL, xuống dòng, hướng của đoạn chữ và font.
- Kết quả bất đồng bộ được format trước khi người dùng đổi ngôn ngữ.
- Các trường nhập liệu chưa commit: tránh làm mất draft hoặc đọc sai dấu nhóm khi đổi locale.

**Nguyên tắc cốt lõi:** đổi locale là thay **ngữ cảnh trình bày**. Nó không làm các `String` đã format tự cập nhật, và không nên tự thay đổi dữ liệu nghiệp vụ. Hãy giữ dữ liệu ở dạng có kiểu, cập nhật trạng thái locale, chọn lại tài nguyên/formatter, rồi render lại UI.

## 2. Ba lớp không được trộn lẫn

~~~text
DOMAIN MODEL (nguồn bất biến)
  customerName: "Lan"
  orderId: 42
  quantity: BigDecimal("1234.50")
  date: LocalDate.of(2025,3,5)
  price: Money(amount, Currency.USD)
            |
            | áp dụng PresentationContext
            v
PRESENTATION CONTEXT
  uiLocale: en-US / vi-VN
  formatLocale: en-US / vi-VN (nếu ứng dụng tách)
  zone: Asia/Ho_Chi_Minh
  currency: USD (đúng loại tiền nghiệp vụ)
            |
            v
PRESENTATION
  ResourceBundle -> nhãn/thông báo
  NumberFormat -> số/tiền/phần trăm
  DateTimeFormatter -> ngày/giờ
  MessageFormat -> thông điệp có tham số
  ComponentOrientation -> LTR/RTL
            |
            v
UI/RENDERER
~~~

| Thứ cần giữ | Kiểu dữ liệu | Khi đổi locale |
| --- | --- | --- |
| Số lượng | `BigDecimal` | Gọi formatter số theo locale mới |
| Ngày không có giờ | `LocalDate` | Format lại theo locale mới |
| Thời điểm tuyệt đối | `Instant` | Format theo locale và `ZoneId` được chọn |
| Loại tiền | `Currency` cùng giá trị `BigDecimal` | Thay cách hiện ký hiệu; **không tự đổi currency** |
| Mã đơn hàng | ID, String theo schema | Thường giữ nguyên ký tự, không format như số lượng |
| Tên khách hàng | `String` gốc | Giữ đúng tên; chỉ chèn vào message mới |
| Ngôn ngữ UI | `Locale` hoặc language tag BCP 47 | Cập nhật state và thông báo presenters |
| Chuỗi đã format | `String` dẫn xuất | **Tạo lại**, không dùng làm dữ liệu nguồn |

Một `BigDecimal("1234.50")` không trở thành `BigDecimal("1.234,50")` khi đổi ngôn ngữ. `"1.234,50"` chỉ là **chuỗi hiển thị**. Tương tự, nếu đang có `Instant`, đổi locale không tự thay `ZoneId` hay thời điểm của sự kiện.

**Tại sao không lưu dữ liệu dưới dạng label?** Vì bản dịch, quy tắc dấu và dữ liệu locale của JDK có thể khác giữa người dùng hoặc giữa các lần cập nhật. Một chuỗi đã format không đủ để khôi phục ý nghĩa typed một cách an toàn.

## 3. Locale.setDefault không phải nút chuyển ngôn ngữ theo người dùng

Có cách làm tưởng đơn giản:

~~~java
Locale.setDefault(Locale.forLanguageTag("vi-VN"));
frame.repaint();
~~~

Đây chỉ là **mảnh mã minh họa** trong method, cần import `Locale` và biến `frame` đã có. Nó không bảo đảm UI đang mở tự đổi ngôn ngữ.

Ba vấn đề:

1. `Locale.setDefault` thay **default locale của toàn JVM** hoặc category toàn JVM, không phải của một request hay một cửa sổ.
2. Các `ResourceBundle`, `NumberFormat`, `MessageFormat`, `DateTimeFormatter` đã tạo trước đó **không tự đổi** nội dung khi bạn sửa default.
3. `repaint` chỉ vẽ lại các label đang lưu; nếu `JLabel.setText` chưa được gọi với bản dịch mới, văn bản cũ vẫn hiện.

### Server đa người dùng: lỗi race

~~~text
Request A: chọn vi-VN -> Locale.setDefault(vi-VN)
Request B: chọn en-US -> Locale.setDefault(en-US)
Request A: format số bằng NumberFormat.getInstance()
           -> có thể vô tình dùng default của B
~~~

Không sử dụng default locale mutable để phục vụ đồng thời các user. Thay bằng:

~~~java
Locale locale = Locale.forLanguageTag("vi-VN");
ResourceBundle b = ResourceBundle.getBundle("Messages", locale);
NumberFormat nf = NumberFormat.getNumberInstance(locale);
DateTimeFormatter df = DateTimeFormatter
        .ofLocalizedDate(FormatStyle.LONG)
        .withLocale(locale);
~~~

Đây là **mảnh mã trong method**, cần import `java.util.Locale`, `java.util.ResourceBundle`, `java.text.NumberFormat`, `java.time.format.DateTimeFormatter` và `FormatStyle`.

Một locale ứng với **phiên, màn hình hoặc request**. Không tạo một biến static `currentLocale` mutable rồi dùng chung cho tất cả client trong web server.

## 4. Quy trình chuyển locale đúng

Khi người dùng chọn ngôn ngữ mới:

1. **Nhận sự kiện** `LanguageChanged(newLocale)`.
2. **Xác thực** locale thuộc tập ngôn ngữ ứng dụng hỗ trợ; không mặc định tag hợp lệ là có bản dịch.
3. **Cập nhật state** ở phạm vi đúng (user/session/window).
4. **Chọn tài nguyên** từ `ResourceBundle` theo locale đó.
5. **Chuẩn bị formatter** theo locale mới; đảm bảo formatter mutable không bị tái sử dụng sai.
6. **Dựng lại presentation model** từ dữ liệu typed và message keys, không parse lại chuỗi cũ để lấy giá trị.
7. **Cập nhật tất cả view** phụ thuộc locale: nhãn, số, ngày, validation, tooltip, bảng, dialog, accessibility.
8. **Cập nhật layout** nếu thay đổi chiều chữ, độ dài nhãn, căn chỉnh hoặc font.
9. **Giữ user input** và lựa chọn hiện tại trừ khi chính sách sản phẩm yêu cầu chuyển có kiểm soát.
10. **Loại bỏ kết quả bất đồng bộ cũ** hoặc format lại chúng bằng locale hiện hành.
11. **Lưu lựa chọn** nếu người dùng muốn ngôn ngữ được giữ qua phiên sau.

Một ứng dụng reactive có thể tự kích hoạt các binding phụ thuộc `locale`; ứng dụng imperative có thể gọi `applyLocale(locale)` để cập nhật component. Cả hai vẫn phải kiểm kê đủ mọi nơi đã format văn bản.

## 5. Ví dụ console hoàn chỉnh: đổi en-US sang vi-VN

Ví dụ Java 17+ có thể chạy chỉ với JDK, không cần Maven hoặc framework. Tạo thư mục sau:

~~~text
locale-console/
  LanguageSwitchDemo.java
  Messages_en.properties
  Messages_vi.properties
~~~

Tạo `Messages_en.properties` bằng UTF-8:

~~~properties
title=Orders
welcome=Welcome, {0}!
date=Date
quantity=Quantity
name=Customer
language=Language
~~~

Tạo `Messages_vi.properties` bằng UTF-8:

~~~properties
title=Đơn hàng
welcome=Xin chào, {0}!
date=Ngày
quantity=Số lượng
name=Khách hàng
language=Ngôn ngữ
~~~

Tạo `LanguageSwitchDemo.java`:

~~~java
import java.math.BigDecimal;
import java.text.MessageFormat;
import java.text.NumberFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;
import java.util.ResourceBundle;

public class LanguageSwitchDemo {
    record Order(
            String customer,
            BigDecimal quantity,
            LocalDate date
    ) {}

    static final class OrderScreen {
        private final Order order; // Dữ liệu nguồn
        private Locale locale;     // Trạng thái trình bày

        OrderScreen(Order order, Locale locale) {
            this.order = order;
            this.locale = locale;
        }

        void changeLanguage(Locale next) {
            this.locale = next;
            render();
        }

        void render() {
            ResourceBundle messages =
                    ResourceBundle.getBundle("Messages", locale);

            NumberFormat numbers =
                    NumberFormat.getNumberInstance(locale);
            numbers.setMinimumFractionDigits(2);
            numbers.setMaximumFractionDigits(2);

            DateTimeFormatter dates = DateTimeFormatter
                    .ofLocalizedDate(FormatStyle.LONG)
                    .withLocale(locale);

            MessageFormat welcome = new MessageFormat(
                    messages.getString("welcome"), locale);

            System.out.println("[" + locale.toLanguageTag()
                    + "] " + messages.getString("title"));
            System.out.println(welcome.format(
                    new Object[]{order.customer()}));
            System.out.println(messages.getString("date") + ": "
                    + order.date().format(dates));
            System.out.println(messages.getString("quantity") + ": "
                    + numbers.format(order.quantity()));
        }
    }

    public static void main(String[] args) {
        Order order = new Order(
                "Lan",
                new BigDecimal("1234.50"),
                LocalDate.of(2025, 3, 5));

        OrderScreen screen = new OrderScreen(
                order, Locale.forLanguageTag("en-US"));
        screen.render();

        screen.changeLanguage(Locale.forLanguageTag("vi-VN"));
    }
}
~~~

Biên dịch và chạy trong thư mục `locale-console`:

~~~bash
javac -encoding UTF-8 LanguageSwitchDemo.java
java -cp . LanguageSwitchDemo
~~~

Đầu ra tham khảo từ JDK có dữ liệu locale thông dụng:

~~~text
[en-US] Orders
Welcome, Lan!
Date: March 5, 2025
Quantity: 1,234.50
[vi-VN] Đơn hàng
Xin chào, Lan!
Ngày: 5 tháng 3, 2025
Số lượng: 1.234,50
~~~

**Chú ý:** chi tiết dấu nhóm, khoảng trắng hoặc cách viết ngày có thể thay đổi theo provider/JDK/CLDR. Các key/nhãn cố định từ properties phải khớp; đầu ra số/ngày cần được kiểm thử với môi trường được hỗ trợ.

### Tại sao ví dụ này đúng?

- `Order` là `record` bất biến: cùng dữ liệu gốc được render hai lần.
- `changeLanguage` cập nhật `Locale` của **screen**, không gọi `Locale.setDefault`.
- `render` chọn lại `ResourceBundle`, `NumberFormat`, `DateTimeFormatter` và `MessageFormat` cho locale hiện tại.
- Ngày và số được **format lại từ typed values**, không parse `"March 5, 2025"` hay `"1,234.50"` rồi đoán ngược.
- Mỗi ngôn ngữ có **toàn câu** `welcome` với placeholder `{0}`; người dịch có thể đổi thứ tự tham số nếu cần.
- Toàn bộ file `.properties` và Java literal được lưu UTF-8; `javac -encoding UTF-8` giúp tránh khác biệt khi biên dịch trên môi trường cũ.

**Giới hạn:** ví dụ console chỉ mô phỏng sự kiện. Trong GUI, `render` sẽ cập nhật component hoặc observable state; dữ liệu nguyên tắc không đổi.

## 6. ResourceBundle: đổi locale khác với reload file

`ResourceBundle.getBundle("Messages", locale)` chọn bundle tương ứng. Nếu đã có `ResourceBundle english`, nó **không trở thành tiếng Việt** khi state đổi.

~~~java
ResourceBundle english = ResourceBundle.getBundle(
        "Messages", Locale.ENGLISH);
ResourceBundle vietnamese = ResourceBundle.getBundle(
        "Messages", Locale.forLanguageTag("vi-VN"));
~~~

Đây là mảnh mã trong method, cần import `java.util.ResourceBundle` và `java.util.Locale`.

### Cache có phải vấn đề?

`ResourceBundle` có cache để tránh nạp lại cùng file. Khi đổi `en-US` → `vi-VN`, bạn đang **yêu cầu một locale khác**; không phải đang sửa file nguồn. Vì vậy bình thường **không gọi `ResourceBundle.clearCache()` mỗi lần switch**.

Chỉ cân nhắc invalidation khi **nội dung file bundle thay đổi tại runtime**. Với tài nguyên đóng gói cùng JAR, thường chỉ thay trong release mới. Với nguồn live, cần policy TTL/needsReload hoặc cơ chế provider. Không nhầm việc lấy bundle khác với làm mới bản ghi trong cache.

### Fallback và missing key

`ResourceBundle` tìm các locale ứng viên và kế thừa khóa qua parent. Nếu `Messages_vi_VN.properties` không có nhưng `Messages_vi.properties` có, ứng dụng có thể dùng bản `vi`. Tuy vậy, nếu không có tài nguyên theo locale yêu cầu, thuật toán fallback mặc định còn có thể xét default locale JVM.

Để không rò ngôn ngữ server vào giao diện:

- Chỉ cho chọn **supported locales**; kiểm tra tài nguyên sẵn có.
- Có **fallback business** có chủ đích, chẳng hạn tiếng Anh cho key thiếu.
- Với classpath/unnamed module, có thể dùng `ResourceBundle.Control.getNoFallbackControl` nếu muốn chặn fallback sang default JVM, nhưng vẫn giữ candidate/parent root.
- Với **named modules** (JPMS), overload `ResourceBundle.getBundle(..., Control)` không được hỗ trợ; phải dùng cơ chế module/provider.

`MissingResourceException` có thể xuất hiện khi thiếu bundle hoặc key; nên kiểm tra key đầy đủ tại build/QA và có lỗi/fallback rõ ràng, không âm thầm trả chuỗi trống.

## 7. NumberFormat: tạo lại theo locale, giữ số gốc

Ví dụ:

~~~java
BigDecimal value = new BigDecimal("1234.50");
Locale us = Locale.forLanguageTag("en-US");
Locale vi = Locale.forLanguageTag("vi-VN");

NumberFormat en = NumberFormat.getNumberInstance(us);
NumberFormat vn = NumberFormat.getNumberInstance(vi);
en.setMinimumFractionDigits(2);
en.setMaximumFractionDigits(2);
vn.setMinimumFractionDigits(2);
vn.setMaximumFractionDigits(2);

System.out.println(en.format(value));
System.out.println(vn.format(value));
~~~

Đây là mảnh mã trong method, cần import `BigDecimal`, `Locale`, `NumberFormat`. Dữ liệu locale JDK thường cho:

~~~text
1,234.50
1.234,50
~~~

`NumberFormat` và `DecimalFormat` là các đối tượng **mutable**, không được coi là thread-safe khi dùng chung không đồng bộ. Một formatter tạo với `Locale.US` không tự đổi cấu hình khi default locale thay đổi. Khi render nhiều user, tạo formatter theo request hoặc clone/cấu hình riêng cho từng tác vụ.

### Ngôn ngữ không tự đổi đơn vị tiền

Nếu một đơn hàng là **USD**, đổi UI sang tiếng Việt không làm nó thành VND. Để hiển thị:

~~~java
Currency usd = Currency.getInstance("USD");
NumberFormat money = NumberFormat.getCurrencyInstance(locale);
money.setCurrency(usd);
String shown = money.format(amount);
~~~

Đây là mảnh mã trong method; cần import `java.util.Currency`, `java.text.NumberFormat` và có biến `locale`, `amount`. `setCurrency` thay currency được hiển thị nhưng **không thực hiện chuyển đổi tỷ giá**. Nó cũng không luôn tự điều chỉnh fraction digits đã cấu hình; đối với tiền, cần thiết kế chính sách precision/rounding và currency identity.

## 8. DateTimeFormatter: có thể dùng chung theo cấu hình rõ ràng

`DateTimeFormatter` trong `java.time` **bất biến và thread-safe**. `withLocale` tạo formatter mới:

~~~java
DateTimeFormatter base =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG);

DateTimeFormatter english = base.withLocale(Locale.US);
DateTimeFormatter vietnamese = base.withLocale(
        Locale.forLanguageTag("vi-VN"));
~~~

Đây là mảnh mã trong method, cần import `DateTimeFormatter`, `FormatStyle`, `Locale`. `base` không thay đổi.

Khi hiển thị `Instant`, cần thêm `ZoneId`:

~~~java
Instant moment = Instant.parse("2025-03-05T10:15:30Z");
ZoneId userZone = ZoneId.of("Asia/Ho_Chi_Minh");

DateTimeFormatter f = DateTimeFormatter
        .ofLocalizedDateTime(FormatStyle.MEDIUM)
        .withLocale(locale)
        .withZone(userZone);

String displayed = f.format(moment);
~~~

Đây là mảnh mã trong method, cần import `java.time.Instant`, `ZoneId`, `DateTimeFormatter`, `FormatStyle` và biến `locale`.

**Đổi `Locale` khác với đổi `ZoneId`.** Người dùng có thể muốn UI tiếng Anh tại Việt Nam, hoặc UI tiếng Việt trong múi giờ Berlin. Giữ các lựa chọn tách biệt nếu nghiệp vụ yêu cầu.

## 9. MessageFormat: setLocale không cập nhật mọi subformat cũ

`MessageFormat` hỗ trợ câu có tham số theo ngôn ngữ. Tuy nhiên, Javadoc nêu rõ **`setLocale` không tự cập nhật các đối tượng `Format` đã tạo trước đó do `applyPattern`**. Một code cũ giữ `MessageFormat` chứa `{0,number}` và chỉ gọi `setLocale` có thể vẫn in số kiểu locale cũ.

### Ví dụ Java 17+ đầy đủ

Tạo `MessageFormatSwitchDemo.java`:

~~~java
import java.text.MessageFormat;
import java.util.Locale;

public class MessageFormatSwitchDemo {
    public static void main(String[] args) {
        Locale en = Locale.forLanguageTag("en-US");
        Locale vi = Locale.forLanguageTag("vi-VN");

        MessageFormat formatter =
                new MessageFormat("{0,number}", en);

        System.out.println("Before: "
                + formatter.format(new Object[]{1234.5}));

        formatter.setLocale(vi);
        System.out.println("Only setLocale: "
                + formatter.format(new Object[]{1234.5}));

        formatter.applyPattern("{0,number}");
        System.out.println("Re-apply pattern: "
                + formatter.format(new Object[]{1234.5}));

        MessageFormat fresh =
                new MessageFormat("{0,number}", vi);
        System.out.println("Fresh formatter: "
                + fresh.format(new Object[]{1234.5}));
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 MessageFormatSwitchDemo.java
java MessageFormatSwitchDemo
~~~

Đầu ra đã kiểm tra trong JDK:

~~~text
Before: 1,234.5
Only setLocale: 1,234.5
Re-apply pattern: 1.234,5
Fresh formatter: 1.234,5
~~~

**Khuyến nghị:** ở UI đổi locale, tạo `MessageFormat` mới với **pattern đã dịch của locale mới**. Nếu tái sử dụng, phải hiểu trạng thái mutable, `applyPattern` và các định dạng số/ngày đã được cấu hình thủ công. Không chia sẻ `MessageFormat` mutable giữa nhiều luồng không đồng bộ.

### Câu thông điệp cần được dịch nguyên vẹn

Tránh nối:

~~~java
String s = bundle.getString("prefix")
        + " " + customer + " " + bundle.getString("suffix");
~~~

Đây là mảnh mã trong method, có `bundle` và `customer` đã có. Cấu trúc câu giữa các ngôn ngữ có thể khác. Dùng `welcome=Welcome, {0}!` và `welcome=Xin chào, {0}!` để người dịch điều chỉnh trật tự tham số. Cần kiểm tra cách escape dấu nháy đơn trong `MessageFormat` và cân nhắc thư viện plural theo ngôn ngữ cho những thông điệp phức tạp.

## 10. GUI Swing: làm mới component khi đổi ngôn ngữ

Một app Swing cần cập nhật **`JLabel`, title, các giá trị đã format và component orientation**, chứ không chỉ đổi một biến. Ví dụ sau dùng lại hai file `Messages_en.properties`, `Messages_vi.properties` của ví dụ 1, có đủ các key `title`, `welcome`, `date`, `quantity`, `name`, `language`.

Tạo `SwingLanguageSwitchDemo.java` trong cùng thư mục:

~~~java
import java.awt.ComponentOrientation;
import java.awt.GridLayout;
import java.math.BigDecimal;
import java.text.MessageFormat;
import java.text.NumberFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;
import java.util.ResourceBundle;
import javax.swing.JComboBox;
import javax.swing.JFrame;
import javax.swing.JLabel;
import javax.swing.JPanel;
import javax.swing.JTextField;
import javax.swing.SwingUtilities;

public class SwingLanguageSwitchDemo {
    private final JFrame frame = new JFrame();
    private final JPanel panel = new JPanel(
            new GridLayout(5, 2, 8, 8));

    private final JComboBox<String> language =
            new JComboBox<>(new String[]{"English", "Tiếng Việt"});
    private final JLabel languageLabel = new JLabel();
    private final JLabel customerLabel = new JLabel();
    private final JTextField customerField = new JTextField("Lan", 12);
    private final JLabel dateLabel = new JLabel();
    private final JLabel dateValue = new JLabel();
    private final JLabel quantityLabel = new JLabel();
    private final JLabel quantityValue = new JLabel();
    private final JLabel greetingLabel = new JLabel();

    private final LocalDate date = LocalDate.of(2025, 3, 5);
    private final BigDecimal quantity = new BigDecimal("1234.50");

    SwingLanguageSwitchDemo() {
        frame.setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);

        panel.add(languageLabel);
        panel.add(language);
        panel.add(customerLabel);
        panel.add(customerField);
        panel.add(dateLabel);
        panel.add(dateValue);
        panel.add(quantityLabel);
        panel.add(quantityValue);
        panel.add(greetingLabel);
        panel.add(new JLabel());
        frame.setContentPane(panel);

        language.addActionListener(e -> {
            Locale locale = language.getSelectedIndex() == 0
                    ? Locale.forLanguageTag("en-US")
                    : Locale.forLanguageTag("vi-VN");
            applyLocale(locale);
        });

        applyLocale(Locale.forLanguageTag("en-US"));
        frame.setLocationRelativeTo(null);
        frame.setVisible(true);
    }

    private void applyLocale(Locale locale) {
        ResourceBundle b = ResourceBundle.getBundle(
                "Messages", locale);
        NumberFormat number = NumberFormat.getNumberInstance(locale);
        number.setMinimumFractionDigits(2);
        number.setMaximumFractionDigits(2);

        DateTimeFormatter dates =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
                        .withLocale(locale);
        MessageFormat greeting =
                new MessageFormat(b.getString("welcome"), locale);

        frame.setTitle(b.getString("title"));
        languageLabel.setText(b.getString("language"));
        customerLabel.setText(b.getString("name"));
        dateLabel.setText(b.getString("date"));
        dateValue.setText(date.format(dates));
        quantityLabel.setText(b.getString("quantity"));
        quantityValue.setText(number.format(quantity));
        greetingLabel.setText(greeting.format(
                new Object[]{customerField.getText()}));

        ComponentOrientation orientation =
                ComponentOrientation.getOrientation(locale);
        frame.applyComponentOrientation(orientation);
        panel.applyComponentOrientation(orientation);
        panel.revalidate();
        panel.repaint();
        frame.pack();
    }

    public static void main(String[] args) {
        SwingUtilities.invokeLater(SwingLanguageSwitchDemo::new);
    }
}
~~~

Biên dịch và chạy trong môi trường **có desktop/GUI**, không phải CI headless:

~~~bash
javac -encoding UTF-8 SwingLanguageSwitchDemo.java
java -cp . SwingLanguageSwitchDemo
~~~

### Những điều Swing demo đã xử lý

- Cửa sổ mở một lần; người dùng chọn dropdown để đổi locale **ngay khi đang chạy**.
- Event listener và cập nhật Swing được thực hiện trên **Event Dispatch Thread (EDT)** vì constructor được gọi qua `SwingUtilities.invokeLater`.
- Cả label, tiêu đề frame, ngày, số và lời chào đều được **tính lại**.
- `JTextField` của khách hàng được giữ nguyên; đổi ngôn ngữ **không xóa nội dung vừa nhập**.
- `ComponentOrientation` cho phép layout nhận hướng gợi ý từ locale; với app RTL phức tạp cần kiểm tra từng widget và khả năng hỗ trợ của layout.
- `revalidate`/`repaint`/`pack` giúp UI thích ứng khi bản dịch dài hơn.
- Đối tượng `LocalDate` và `BigDecimal` của màn hình được giữ nguyên.

**Giới hạn để triển khai production:** demo không cập nhật lời chào trong lúc gõ tên; nếu cần live update, dùng `DocumentListener` phù hợp. Menu, tooltip, validation, accessible descriptions, table headers và các cửa sổ con phải có logic refresh tương tự. Một số component cần xử lý focus/selection hoặc layout riêng, không chỉ `applyComponentOrientation`.

## 11. Reactivity: locale là state, chuỗi được tính lại là derived data

Trong GUI lớn, gán trực tiếp bằng hàng trăm `label.setText(...)` có thể dễ bỏ sót. Kiến trúc MVVM/reactive cho phép định nghĩa:

~~~text
localeState = vi-VN
   |
   +--> titleText      = bundle(localeState).getString("title")
   +--> amountText     = formatNumber(amount, localeState)
   +--> dateText       = formatDate(date, localeState)
   +--> welcomeText    = formatMessage(name, localeState)
   +--> orientation    = direction(localeState)
   |
   v
View theo dõi derived values và re-render
~~~

Với JavaFX, có thể dùng observable property/binding; với web front-end, có thể dùng state management. Dù framework nào, **mọi derived value phải khai báo phụ thuộc locale**. Nếu date text được tính một lần trong constructor rồi cache mà không có invalidation, đổi language state không làm nó tự đổi.

Phân biệt hai mô hình:

- **Imperative:** method `applyLocale(locale)` cập nhật từng component. Phù hợp app nhỏ, yêu cầu checklist kỹ.
- **Reactive:** locale là state và nhãn/số/ngày là derived values. Phù hợp nhiều màn hình; framework hỗ trợ invalidation nhưng vẫn phải quản lý cache và asynchronous updates.

Không tạo một số locale copy riêng ở từng dialog mà không thông báo nhau, nếu sản phẩm yêu cầu mọi cửa sổ cùng đổi ngôn ngữ.

## 12. Chuyển locale khi field đang được chỉnh sửa

Giả sử form đang nhập số theo en-US:

~~~text
1,234.50
~~~

Trước khi người dùng submit, họ đổi sang vi-VN. Nếu code lấy chuỗi đó rồi parse bằng parser vi-VN, dấu `,` có thể được hiểu theo quy tắc **thập phân**, còn dấu `.` có thể là dấu nhóm. Điều đó có thể tạo giá trị sai hoặc parse chỉ phần đầu.

Chọn một chính sách rõ:

**Chính sách A — Giữ draft.** Nếu input chưa commit, giữ nguyên `JTextField.getText()` và lưu `localeAtEditStart`; chỉ đổi nhãn/hint cho tới khi người dùng hoàn tất edit. Khi commit, parse theo locale đã gắn với input hoặc yêu cầu xác nhận.

**Chính sách B — Chuyển có kiểm soát.** Trước khi đổi, parse/validate input bằng **locale cũ** thành `BigDecimal`. Nếu hợp lệ và người dùng chấp nhận, format từ typed value sang locale mới, đồng thời xử lý focus/caret/selection.

**Không nên làm:**

~~~java
NumberFormat parser =
        NumberFormat.getNumberInstance(currentLocale);
Number value = parser.parse(uncommittedText);
~~~

Đây là mảnh mã **minh họa cách sai**, cần xử lý `ParseException`. `currentLocale` có thể đã đổi khác locale người dùng đang dùng khi gõ chuỗi.

`NumberFormat.parse` còn có thể chỉ đọc **tiền tố** hợp lệ; nếu cần validation chặt, dùng `ParsePosition` xác nhận toàn bộ chuỗi được tiêu thụ và kiểm tra đúng vị trí dấu nhóm, scale/range theo nghiệp vụ.

## 13. Bất đồng bộ: không để kết quả ngôn ngữ cũ ghi đè UI mới

Ví dụ:

~~~text
t0: màn hình en-US; bắt đầu fetch
t1: người dùng đổi sang vi-VN
t2: response tiếng Anh quay lại sau khi đổi
t3: nếu áp trực tiếp -> UI trộn English và Tiếng Việt
~~~

Hai biện pháp quan trọng:

1. **Fetch dữ liệu nghiệp vụ trung tính** nếu có thể, rồi format theo locale **ngay tại lúc commit/render**.
2. Với tác vụ trả về nội dung đã dịch hoặc đã format, kèm **locale/version/generation**; khi hoàn tất, chỉ áp kết quả nếu vẫn thuộc trạng thái hiện tại.

### Mẫu generation guard (mảnh code kiến trúc)

~~~java
final AtomicLong generation = new AtomicLong();
volatile Locale current = Locale.forLanguageTag("en-US");

void changeLanguage(Locale next) {
    current = next;
    generation.incrementAndGet();
    renderAll(next);
}

void startLoad() {
    long version = generation.get();
    Locale requested = current;

    fetchAsync().thenAccept(data -> {
        runOnUiThread(() -> {
            // Kiểm tra bên trong UI callback, không chỉ trước enqueue.
            if (version != generation.get()) {
                return;
            }
            renderData(data, requested);
        });
    });
}
~~~

Đây là **mảnh code không độc lập**, cần `AtomicLong` từ `java.util.concurrent.atomic`. Các method `fetchAsync`, `runOnUiThread`, `renderAll`, `renderData` do framework định nghĩa.

**Vì sao kiểm tra bên trong UI callback?** Nếu chỉ kiểm tra generation trước khi enqueue vào EDT, người dùng có thể đổi locale giữa lúc kiểm tra và lúc callback thực sự chạy. Tốt hơn là kiểm tra lần cuối ở điểm commit.

Với một app nhiều người dùng, generation phải có phạm vi theo **user/session/window**, không phải một số đếm toàn server khiến các user vô tình huỷ job của nhau.

## 14. Tách uiLocale, formatLocale, zone và currency khi cần

Một số ứng dụng cho phép dùng ngôn ngữ English nhưng số theo quy tắc Đức, múi giờ Việt Nam và tiền USD. Không nhất thiết gom các lựa chọn thành một locale:

~~~java
record UserPreferences(
        Locale uiLocale,
        Locale formatLocale,
        ZoneId zone,
        Currency currency
) {}
~~~

Đây là mảnh khai báo trong class, cần import `java.util.Locale`, `java.time.ZoneId` và `java.util.Currency`.

Các tầng dùng đúng thuộc tính:

| Thuộc tính | Nhiệm vụ |
| --- | --- |
| `uiLocale` | Chọn `ResourceBundle`, tên nút, trợ giúp, message |
| `formatLocale` | Format số, ngày theo quy ước được chọn |
| `zone` | Đổi `Instant` thành giờ địa phương |
| `currency` | Đơn vị tiền của giá trị, không phải tỷ giá |
| `measurementSystem` (nếu có) | Chính sách đơn vị, ví dụ km/mi |

Với ứng dụng nhỏ, dùng một locale chung có thể đủ. Nhưng nếu nghiệp vụ đã yêu cầu những lựa chọn độc lập thì không tự đổi zone/currency khi người dùng chỉ chọn ngôn ngữ.

## 15. Đổi ngôn ngữ còn liên quan chiều chữ, trợ năng và layout

Tiếng Việt và tiếng Anh thường LTR. Ứng dụng mở rộng sang tiếng Ả Rập hoặc Hebrew có thể cần:

- Cập nhật hướng nền của container/paragraph theo locale phù hợp.
- Căn chỉnh nhãn, thứ tự icon/text, vị trí button và định hướng bảng.
- Cô lập URL/email/mã sản phẩm LTR nằm trong một câu RTL.
- Cập nhật accessible name/description cho screen reader.
- Cập nhật tooltip, alt text và những chuỗi đã cache trong menu/dialog.
- Kiểm tra font fallback, dấu kết hợp và sự thay đổi chiều dài bản dịch.
- Đảm bảo thứ tự logic của dữ liệu và ID **không bị đảo** theo thứ tự hiển thị.

Trong Swing, `ComponentOrientation.getOrientation(locale)` là điểm bắt đầu; trong HTML có `dir` và phần tử `bdi`. Không dùng `new StringBuilder(text).reverse()` để “đổi sang RTL”: đảo chuỗi có thể làm hỏng số, dấu câu, emoji và ngữ pháp.

Đối với một ngày đã format, dùng `DateTimeFormatter.ofLocalizedDate` thường tốt hơn việc ép một pattern ngày/tháng/năm cố định cho mọi locale. Với tên tháng đứng độc lập trong tiêu đề lịch, có thể dùng `LLLL` thay `MMMM` ở các ngôn ngữ có hai dạng tên tháng.

## 16. Các vùng UI cần refresh và tiêu chí hoàn tất

| Vùng cần xem | Ví dụ | Cần làm gì |
| --- | --- | --- |
| Header | Tiêu đề cửa sổ, thanh điều hướng | Lấy text theo locale mới |
| Điều khiển | Button, menu, tab | Lấy label/shortcut/tooltip phù hợp |
| Form | Label, hint, placeholder | Đổi text nhưng giữ draft người dùng |
| Validation | Error, warning, inline help | Dịch lại lỗi đang hiện, không bỏ mất trạng thái lỗi |
| Thông báo | Snackbar, toast, dialog | Chọn update/đóng/để lịch sử theo policy |
| Bảng | Header, cells số/ngày | Gọi lại renderer với locale mới |
| Biểu đồ | Axis ticks, legends | Format lại nhãn từ số liệu nguồn |
| Calendar | Tên tháng, thứ trong tuần | Chọn format theo locale |
| Tài liệu | Preview, email, export | Dùng locale của recipient/job |
| Accessibility | Accessible names, descriptions | Cập nhật văn bản trợ năng |
| Hướng chữ | LTR/RTL | Cập nhật orientation/isolation |
| Async | Dữ liệu đến sau | Guard version hoặc re-render với locale hiện tại |

**Không chỉ gọi `repaint()`:** UI cần **được gán các chuỗi mới** trước khi vẽ. `repaint` chỉ dùng text đã có.

## 17. Ví dụ 3 — Tự kiểm thử lựa chọn tài nguyên và bảo toàn dữ liệu

Bài kiểm thử dưới đây không cần framework JUnit. Dùng lại `Messages_en.properties` và `Messages_vi.properties` từ ví dụ 1.

Tạo `LocaleSwitchSelfTest.java`:

~~~java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;
import java.util.ResourceBundle;

public class LocaleSwitchSelfTest {
    static void require(boolean ok, String detail) {
        if (!ok) {
            throw new AssertionError(detail);
        }
    }

    public static void main(String[] args) {
        Locale en = Locale.forLanguageTag("en-US");
        Locale vi = Locale.forLanguageTag("vi-VN");

        BigDecimal quantity = new BigDecimal("1234.50");
        LocalDate date = LocalDate.of(2025, 3, 5);

        ResourceBundle english =
                ResourceBundle.getBundle("Messages", en);
        ResourceBundle vietnamese =
                ResourceBundle.getBundle("Messages", vi);

        require(english.getString("date").equals("Date"),
                "Wrong en resource");
        require(vietnamese.getString("date").equals("Ngày"),
                "Wrong vi resource");

        NumberFormat enNumbers =
                NumberFormat.getNumberInstance(en);
        NumberFormat viNumbers =
                NumberFormat.getNumberInstance(vi);

        String enText = enNumbers.format(quantity);
        String viText = viNumbers.format(quantity);
        require(!enText.isEmpty() && !viText.isEmpty(),
                "Number rendering failed");

        DateTimeFormatter enDate = DateTimeFormatter
                .ofLocalizedDate(FormatStyle.LONG).withLocale(en);
        DateTimeFormatter viDate = DateTimeFormatter
                .ofLocalizedDate(FormatStyle.LONG).withLocale(vi);

        require(!date.format(enDate).isEmpty(),
                "English date missing");
        require(!date.format(viDate).isEmpty(),
                "Vietnamese date missing");

        require(quantity.equals(new BigDecimal("1234.50")),
                "Quantity unexpectedly changed");
        require(date.equals(LocalDate.of(2025, 3, 5)),
                "Date unexpectedly changed");

        System.out.println("PASS: translations selected by locale");
        System.out.println("PASS: locale-specific formatting performed");
        System.out.println("PASS: typed domain data unchanged");
    }
}
~~~

Biên dịch/chạy trong thư mục resources:

~~~bash
javac -encoding UTF-8 LocaleSwitchSelfTest.java
java -cp . LocaleSwitchSelfTest
~~~

Kết quả:

~~~text
PASS: translations selected by locale
PASS: locale-specific formatting performed
PASS: typed domain data unchanged
~~~

Test tập trung vào **hợp đồng**: đúng catalog, format theo locale được yêu cầu, domain data không đổi. Nó không buộc chuỗi date/number phải có từng dấu câu giống nhau ở mọi JDK/provider. Nếu sản phẩm cần exact output, hãy ràng buộc phiên bản JDK/CLDR hoặc kiểm tra môi trường triển khai thật.

## 18. Ma trận kiểm thử end-to-end

| Kịch bản | Cách thử | Kết quả mong muốn |
| --- | --- | --- |
| Đổi en → vi → en | Chuyển nhiều lần trên cùng màn hình | Không còn nhãn lạc locale |
| Định dạng | Một `BigDecimal` và `LocalDate` | Chuỗi đổi, giá trị gốc không đổi |
| Thiếu key | Bỏ một resource key trong bản test | Fallback hoặc thông báo rõ theo policy |
| Locale chưa hỗ trợ | Chọn `fr-CA` khi chỉ có en,vi | Không âm thầm lấy ngôn ngữ server |
| User input | Nhập số en rồi đổi vi | Không parse nhầm, không reset field |
| Async race | Đổi locale trước response | Không nhận stale text |
| Multi-user | Hai request vi/en chạy song song | Không rò locale |
| Currency | Order lưu USD | Vẫn USD sau đổi UI |
| Zone | Instant + timezone cố định | Không lệch giờ chỉ do đổi language |
| RTL | Chuyển sang ngôn ngữ RTL | Layout/markup không làm hỏng URL/số |
| Swing EDT | Đổi dropdown trong UI | Không cập nhật component ngoài EDT |
| Build resources | Đóng gói .properties vào JAR | ResourceBundle tìm được tệp |
| Java upgrade | Chạy trên các JDK được hỗ trợ | Những khác biệt CLDR được đánh giá |

### Những lỗi thường gặp

- **`Locale.setDefault` trong request:** tạo cuộc đua giữa nhiều user; truyền locale tường minh.
- **Chỉ đổi trạng thái mà không render:** label/tooltip vẫn cũ; invalidate derived presentation.
- **Cache chuỗi số/ngày cho mọi user:** hiển thị sai dấu; cache typed data hoặc key có locale.
- **Giữ `MessageFormat` rồi chỉ `setLocale`:** subformat cũ tồn tại; tạo lại hoặc `applyPattern` đúng.
- **Tái sử dụng `NumberFormat` mutable giữa request:** có thể race; tạo theo request.
- **Đổi locale thì gọi `ResourceBundle.clearCache`:** không cần thiết nếu file không đổi.
- **Đổi language đồng thời đổi currency/zone:** sửa nghĩa giao dịch; tách những quyết định đó.
- **Format lại draft chưa commit:** mất dữ liệu/nhầm dấu; lưu locale của input ban đầu.
- **Quên thông báo async:** English cũ ghi đè Vietnamese mới; generation guard ở điểm commit.
- **Không cập nhật accessibility text và layout:** UI mới chỉ được dịch bề mặt.
- **Dịch message bằng nối nhiều mảnh:** sai trật tự ngữ pháp; dịch cả pattern.
- **Chỉ test English:** khó phát hiện lỗi dấu, RTL, tên tháng biến cách hoặc plural.

## 19. Lưu ngôn ngữ người dùng cho lần mở tiếp theo

Dùng **BCP 47 language tag** thay vì lưu một chuỗi tùy ý:

~~~java
Locale selected = Locale.forLanguageTag("vi-VN");
String stored = selected.toLanguageTag(); // vi-VN
Locale restored = Locale.forLanguageTag(stored);
~~~

Đây là mảnh mã trong method, cần import `java.util.Locale`.

Nguồn có thể là cài đặt tài khoản, cookie/session, cấu hình trên máy, lựa chọn tạm thời của cửa sổ hoặc `Accept-Language` của request đầu tiên. Cần xác định **thứ tự ưu tiên**: lựa chọn tường minh của người dùng thường nên mạnh hơn gợi ý từ browser, trong khi cấu hình mặc định của server chỉ là fallback được định nghĩa.

`Locale.forLanguageTag` không đảm bảo ứng dụng có đầy đủ resource cho locale đó. Luôn map sang **supported locales** đã được test; cần chính sách fallback hoặc lựa chọn gần nhất nếu bản dịch không có.

## 20. Bài tập thực hành

1. Thêm `Messages_de.properties` vào console demo và cho người dùng đổi `en-US → de-DE → vi-VN`; xác nhận không sửa `Order`.
2. Thêm một cột percentage và một giá tiền USD; phân biệt chọn locale hiển thị với loại tiền và tỷ giá.
3. Dùng `MessageFormatSwitchDemo` giải thích tại sao `setLocale` không đủ để cập nhật subformat đã tạo.
4. Với Swing demo, thêm một menu, tooltip và thông báo lỗi; đảm bảo các nội dung đang hiện được cập nhật khi đổi ngôn ngữ.
5. Tạo form nhập `1,234.50` khi en-US rồi đổi vi-VN trong lúc đang gõ; thiết kế chính sách không làm mất ý nghĩa.
6. Viết test cho hai user chạy song song, một dùng vi-VN và một dùng en-US, không có lệnh `Locale.setDefault` nào.
7. Tạo tác vụ HTTP trả chuỗi đã format en-US sau khi UI đổi sang vi-VN; dùng generation guard để tránh stale result.
8. Thử locale `ar-EG` để kiểm tra hướng RTL, hiển thị URL/email và layout.
9. Tách `uiLocale` và `formatLocale`: UI English, số định dạng Đức; giải thích cách định nghĩa resource/formatter.
10. Đặt một key thiếu trong bundle tiếng Việt; xác định chính sách fallback và cách thông báo lỗi trong QA.
11. Giải thích khác nhau giữa đổi locale selection và cập nhật file resource đang cache.
12. Khi ngày hoặc số hiển thị thay đổi sau nâng JDK, xác định nguyên nhân nằm ở dữ liệu CLDR, locale hay model nghiệp vụ.

## 21. Checklist triển khai

1. Đặt **locale trong state của đúng phiên/cửa sổ/request**, không đổi default locale toàn JVM.
2. Lưu dữ liệu typed như `BigDecimal`, `LocalDate`, `Instant`, `Currency`; coi chuỗi format là derived.
3. Chọn `ResourceBundle` theo locale mới; định nghĩa supported locales và fallback.
4. Chọn formatter theo locale mới; chú ý tính mutable của `NumberFormat`/`MessageFormat`.
5. Re-render **toàn bộ** component phụ thuộc locale, không chỉ label chính.
6. Xử lý form chưa commit, giữ draft và kiểm soát locale dùng để parse.
7. Tách locale khỏi timezone, currency, exchange rate và đơn vị đo.
8. Refresh accessibility, orientation và bố cục khi cần RTL.
9. Chặn async result cũ hoặc format lúc commit theo locale hiện hành.
10. Kiểm thử luân phiên locale, nhiều người dùng, resource thiếu, CI/headless và phiên bản JDK.
11. Chỉ invalidate cache bundle khi **nguồn bản dịch thay đổi**, không phải mọi lần switch.
12. Ghi nhận language tag BCP 47 để khôi phục lựa chọn của người dùng.

**Ghi nhớ:** Đổi ngôn ngữ đang chạy là **thay đổi trạng thái trình bày**, không phải phép biến đổi dữ liệu nguồn. Một `Locale` mới không tự đổi `String` hay formatter đã tạo. Hãy **giữ dữ liệu typed → đổi locale context → chọn lại bundle/formatter → làm mới UI → kiểm tra async và input đang sửa**. Đó là cơ sở để xây dựng ứng dụng Java đa ngôn ngữ hoạt động nhất quán mà không cần khởi động lại.

### Tài liệu tham khảo

- [Java SE 17 — Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html) — BCP 47, default locale và phạm vi locale.
- [Java SE 17 — ResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html) — tìm tài nguyên, fallback và cache.
- [Java SE 17 — MessageFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/MessageFormat.html) — tham số thông điệp, locale, applyPattern.
- [Java SE 17 — NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html) — số và tiền tệ.
- [Java SE 17 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html) — ngày giờ và formatter bất biến.
- [Java SE 17 — ComponentOrientation](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/awt/ComponentOrientation.html) — hướng hiển thị component.
- [Java SE 17 — SwingUtilities](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/javax/swing/SwingUtilities.html) — cập nhật Swing trên EDT.