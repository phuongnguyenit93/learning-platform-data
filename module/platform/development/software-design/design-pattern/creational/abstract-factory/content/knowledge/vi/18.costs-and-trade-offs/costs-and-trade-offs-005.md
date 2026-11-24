# Cân nhắc tính ổn định của product interface trước khi công khai API

Trong **Abstract Factory**, client phụ thuộc vào các **abstract product** (interface sản phẩm như `Button`, `Checkbox`) và **abstract factory** (interface tạo ra những sản phẩm đó). Cách thiết kế này giúp thay đổi từng **họ sản phẩm** mà ít sửa mã nghiệp vụ. Nhưng khi các interface được đưa ra ngoài một module hoặc công khai cho nhóm phát triển khác, chúng trở thành **hợp đồng mà nhiều bên dựa vào**. Một thay đổi tưởng như nhỏ có thể buộc tất cả concrete product, concrete factory và những client liên quan phải cập nhật.

Bài thuộc chương **Chi phí và đánh đổi** này tập trung vào quyết định cần đưa ra **trước khi công khai API**: nên ổn định những phần nào của product interface, dự báo chi phí thay đổi ra sao, và làm thế nào để bổ sung chức năng mà không phá vỡ các họ sản phẩm đang hoạt động.

## 1. Phân biệt API nội bộ với hợp đồng công khai

Một interface Java tồn tại trong mã nguồn chưa chắc đã là **public API** theo nghĩa hợp đồng hỗ trợ bên ngoài. Cần xác định **ai có quyền sử dụng hoặc hiện thực nó**.

| Phạm vi sử dụng | Ai phụ thuộc vào hợp đồng? | Hệ quả khi thay đổi |
| --- | --- | --- |
| **Nội bộ một module** | Nhóm sở hữu module kiểm soát cả client lẫn implementations | Có thể refactor đồng bộ và triển khai cùng một bản phát hành |
| **API dùng chung giữa nhiều module/nhóm** | Client có thể phát hành ở nhịp khác nhau | Phải quan tâm tương thích nguồn, nhị phân và hành vi |
| **SPI hoặc API cho plugin** | Bên thứ ba tự viết concrete products/factories | Thay đổi interface có thể buộc nhiều nhà cung cấp cập nhật |
| **Thư viện công khai** | Người dùng không do nhóm phát triển kiểm soát | Cần chính sách phiên bản, tài liệu nâng cấp và chu kỳ ngừng hỗ trợ |

**API** (*Application Programming Interface*) thường là hợp đồng phía **người sử dụng** gọi vào. **SPI** (*Service Provider Interface*) là hợp đồng mà **người cung cấp triển khai** phải hiện thực. Trong Abstract Factory, một interface có thể đồng thời đóng cả hai vai trò: client gọi `createButton()`, còn tác giả plugin viết `WindowsFactory implements GUIFactory`.

Vì vậy, trước khi đặt `public` cho một abstract product/factory, cần trả lời:

1. Client bên ngoài có được **gọi** interface này không?
2. Plugin bên ngoài có được **implements** interface này không?
3. Có thể cập nhật đồng thời tất cả các implementations khi phát hành phiên bản mới không?
4. Những đảm bảo nào được công bố: kiểu trả về, khả năng không null, vòng đời, trạng thái, lỗi, tương thích theo họ?

Việc interface có khai báo từ khóa `public` **không tự quyết định toàn bộ chính sách hỗ trợ**; nhưng một khi đã công bố và có người phụ thuộc, thay đổi tùy tiện sẽ trở nên tốn kém.

## 2. Hai trục thay đổi của Abstract Factory

Xét một bộ giao diện có hai loại sản phẩm:

| Họ / Loại sản phẩm | Button | Checkbox |
| --- | --- | --- |
| Light | LightButton | LightCheckbox |
| Dark | DarkButton | DarkCheckbox |

Hợp đồng công khai ban đầu có thể rất nhỏ:

~~~java
public interface Button {
    String render();
}

public interface Checkbox {
    String render();
}

public interface GUIFactory {
    Button createButton();
    Checkbox createCheckbox();
}
~~~

Đây là **ba tệp Java độc lập** nếu được viết dưới dạng `public` top-level trong một dự án thực. Hai loại sản phẩm `Button` và `Checkbox` đóng vai trò các **cột**, hai họ `Light` và `Dark` đóng vai trò các **hàng**.

### Thêm họ mới

Nếu chỉ thêm họ `HighContrast` nhưng vẫn cần đúng `Button` và `Checkbox`, ta thường viết:

- `HighContrastButton implements Button`.
- `HighContrastCheckbox implements Checkbox`.
- `HighContrastFactory implements GUIFactory`.

Các interface công khai có thể **giữ nguyên**. Đây là hướng mở rộng mà Abstract Factory xử lý tương đối thuận tiện, với điều kiện họ mới đáp ứng cùng hợp đồng và mọi quy tắc tương thích.

### Thêm loại hoặc hành vi mới

Nếu muốn **tất cả Button** có thêm phương thức `setIcon(...)`, hoặc muốn **mọi GUIFactory** tạo được một loại `Tooltip` mới, bài toán khác hẳn:

- Thêm một phương thức trừu tượng vào `Button` ảnh hưởng đến **mọi lớp triển khai Button**.
- Thêm `Tooltip createTooltip()` vào `GUIFactory` ảnh hưởng đến **mọi concrete factory**.
- Client có thể phải quyết định cách xử lý chức năng mới ở các họ chưa hỗ trợ.

Giả sử có `F` họ và mỗi họ có một lớp hiện thực cho `Button`. Khi bổ sung một **phương thức bắt buộc** cho `Button`, ít nhất `F` lớp hiện thực có khả năng cần thay đổi. Nếu số concrete implementations lớn hơn số họ hoặc nhiều plugin bên ngoài hiện thực sản phẩm, phạm vi ảnh hưởng còn rộng hơn.

Đây là lý do **độ ổn định của product interface** quyết định phần lớn chi phí mở rộng và bảo trì của Abstract Factory.

## 3. Điều gì thực sự nằm trong hợp đồng product interface?

Hợp đồng không chỉ là danh sách phương thức. Trước khi công khai, cần xác định cả **ý nghĩa hành vi**.

| Thành phần của hợp đồng | Câu hỏi cần làm rõ |
| --- | --- |
| **Tên, tham số, kiểu trả về** | Các họ có thể thực hiện hợp đồng này lâu dài không? |
| **Tiền điều kiện** | Client được truyền `null`, chuỗi rỗng, giá trị ngoài phạm vi không? |
| **Hậu điều kiện** | `render()` bảo đảm trả chuỗi không null hay có thể thất bại? |
| **Trạng thái và vòng đời** | Đối tượng có thể dùng lại không; khi nào phải giải phóng tài nguyên? |
| **Thread safety** | Có thể gọi từ nhiều thread hay chỉ từ UI thread? |
| **Lỗi** | Lỗi không hỗ trợ, cấu hình sai và lỗi runtime được báo bằng cách nào? |
| **Tính tương thích** | Những sản phẩm nào phải cùng họ hoặc cùng phiên bản giao thức? |
| **Khả năng mở rộng** | Tính năng nào có thể bổ sung như capability độc lập? |

Ví dụ, `Button.render()` trả về `String`. Việc đổi **ý nghĩa** của chuỗi trả về từ “mô tả có thể hiển thị” sang “mã cấu hình JSON” có thể khiến client hoạt động sai **dù chữ ký Java không đổi**. Tương tự, việc một implementation bất ngờ bắt đầu ném exception ở trường hợp trước đây hợp lệ là một thay đổi ngữ nghĩa.

Khi thiết kế abstract product, hãy đưa vào interface **hành vi tối thiểu mà tất cả các họ có thể cung cấp đúng nghĩa**, thay vì sao chép đầy đủ API của một nền tảng cụ thể.

## 4. Ba lớp tương thích cần đánh giá

Không nên chỉ hỏi “chương trình có biên dịch không?”. Một thay đổi của public interface có thể tác động ở ba lớp khác nhau:

1. **Source compatibility (tương thích mã nguồn):** mã client và implementation cũ có biên dịch lại với API mới mà không sửa không?
2. **Binary compatibility (tương thích nhị phân):** các file `.class` đã biên dịch với API cũ có tiếp tục liên kết và chạy với thư viện mới không?
3. **Behavioral compatibility (tương thích hành vi):** các giả định hợp lệ của client về kết quả, trạng thái, lỗi và ý nghĩa phương thức có còn đúng không?

Một thay đổi có thể **qua lớp này nhưng thất bại ở lớp khác**. Đặc biệt, Java không đảm bảo rằng “thay đổi không gây lỗi liên kết nhị phân” đồng nghĩa với “mọi lệnh gọi chạy an toàn”.

### 4.1. Một số thay đổi thường gặp

| Thay đổi trên API công khai | Tác động đáng chú ý |
| --- | --- |
| **Thêm phương thức abstract vào Button** | Các lớp implements cũ cần bổ sung phương thức khi biên dịch lại. Lớp cũ có thể vẫn liên kết, nhưng gọi phương thức mới trên lớp chưa hiện thực có thể gây `AbstractMethodError`. |
| **Thêm phương thức abstract vào GUIFactory** | Tất cả concrete factory triển khai hợp đồng cần cập nhật khi biên dịch lại; các factory cũ có nguy cơ lỗi khi client gọi phương thức mới. |
| **Thêm phương thức default vào interface** | Implementation không nhất thiết phải viết lại phương thức, nhưng có thể phát sinh xung đột với các default method/interface khác; hành vi mặc định phải thực sự hợp lệ cho mọi họ. |
| **Đổi tên, bỏ phương thức, đổi kiểu tham số/kiểu trả về** | Có thể làm mã nguồn không biên dịch hoặc làm client nhị phân cũ gặp lỗi liên kết như `NoSuchMethodError`; mức độ tùy dạng thay đổi và cách Java biên dịch nó. |
| **Thêm overload** | Thường là mở rộng, nhưng có thể làm lời gọi với `null`, lambda hoặc các kiểu chuyển đổi trở nên mơ hồ khi biên dịch lại. |
| **Thêm checked exception vào hợp đồng** | Mã nguồn client biên dịch lại có thể phải xử lý hoặc khai báo exception; checked exception không tự làm thay đổi JVM method descriptor. |
| **Thay đổi ngữ nghĩa, nullability hoặc thread-safety** | Có thể phá vỡ client tại runtime dù chữ ký phương thức hoàn toàn giống trước. |

Bảng trên mô tả **các nguy cơ thực tế**, không phải quy tắc “mọi thay đổi kiểu X luôn phá mọi binary”. Với một API Java đã công khai rộng rãi, cần kiểm tra tương thích theo **ngữ cảnh chữ ký và phiên bản cụ thể**, thay vì suy luận chỉ từ tên thao tác sửa.

### 4.2. Vì sao thêm abstract method là thay đổi nhiều rủi ro?

Giả sử thư viện v1 công bố:

~~~java
public interface Button {
    String render();
}
~~~

Plugin bên ngoài có thể đã biên dịch lớp:

~~~java
public final class LegacyButton implements Button {
    @Override
    public String render() {
        return "Legacy button";
    }
}
~~~

Nếu thư viện v2 thay interface thành:

~~~java
public interface Button {
    String render();
    String iconName(); // Phương thức abstract mới.
}
~~~

Khi biên dịch lại `LegacyButton` theo v2, lớp thiếu `iconName()` nên không đáp ứng hợp đồng. Trong các tình huống triển khai cũ đã biên dịch, JVM có thể chỉ báo `AbstractMethodError` **khi thực sự gọi** phương thức mới trên đối tượng đó. Điều này rất khó chịu với plugin được cập nhật độc lập vì lỗi có thể không xuất hiện ở lúc khởi động.

Nếu icon chỉ phục vụ một nhóm Button, bắt **mọi** Button phải công bố `iconName()` là dấu hiệu interface quá rộng. Trước khi công khai API, nên dự đoán những năng lực nào thực sự **bắt buộc cho tất cả các họ**.

## 5. Ba câu hỏi trước khi đưa một phương thức vào product interface

Khi có đề xuất thêm `iconName()`, `setNativeHandle()` hoặc `enableAnimation()`, hãy đặt ba câu hỏi:

**Câu hỏi 1 — Có phải yêu cầu cốt lõi của mọi họ?** Nếu một họ dùng console, một họ dùng desktop và một họ dùng thiết bị không có icon, hành vi icon có thể không có ý nghĩa chung.

**Câu hỏi 2 — Có định nghĩa được ngữ nghĩa nhất quán?** `render()` có thể tương đối chung; nhưng `getWindowsHandle()` thì không. Trả `null` hoặc ném `UnsupportedOperationException` ở hầu hết các họ không tạo ra một abstraction tốt.

**Câu hỏi 3 — Có dự đoán được phiên bản và vòng đời của hành vi?** API công khai thường tồn tại lâu hơn một implementation. Nếu một hành vi có khả năng thay đổi liên tục, có thể đặt nó trong một **capability interface** tách biệt thay vì buộc mọi product biết đến nó.

Điểm cân bằng là: interface **đủ nhỏ để ổn định**, nhưng **đủ ý nghĩa để client dựa vào**. Không phải cứ ít phương thức là tốt; một interface thiếu các hành vi thật sự bất biến sẽ buộc client dùng ép kiểu hoặc biết quá nhiều chi tiết.

## 6. Mở rộng bằng capability interface mà không sửa hợp đồng cũ

Giả sử v1 chỉ yêu cầu Button và Checkbox cơ bản. Sau khi phát hành, ứng dụng bổ sung nút có icon cho một số chủ đề. Có thể công bố **interface mới**:

~~~java
interface IconButton extends Button {
    String iconName();
}
~~~

Với hướng này:

- `Button` **không đổi**; các implementation cũ vẫn đáp ứng hợp đồng ban đầu.
- Các implementation muốn hỗ trợ icon có thể triển khai `IconButton`.
- Chức năng cần icon phụ thuộc vào `IconButton`, còn màn hình cơ bản tiếp tục chỉ phụ thuộc vào `Button`.

Tương tự, không nhất thiết bổ sung `createIconButton()` vào `GUIFactory` nếu chỉ một số họ có năng lực đó. Có thể khai báo **factory mở rộng**:

~~~java
interface IconGUIFactory extends GUIFactory {
    IconButton createIconButton(String iconName);
}
~~~

**IconGUIFactory** là một hợp đồng bổ sung. Những concrete factory cũ chỉ triển khai `GUIFactory` vẫn hợp lệ; các họ muốn cung cấp icon triển khai thêm hợp đồng mở rộng.

### 6.1. Sơ đồ lớp

~~~mermaid
classDiagram
    direction TB
    class Button {
        <<interface>>
        +render() String
    }
    class Checkbox {
        <<interface>>
        +render() String
    }
    class GUIFactory {
        <<interface>>
        +createButton() Button
        +createCheckbox() Checkbox
    }
    class IconButton {
        <<interface>>
        +iconName() String
    }
    class IconGUIFactory {
        <<interface>>
        +createIconButton(iconName) IconButton
    }
    class LightFactory
    class DarkFactory
    class SettingsPanel
    Button <|-- IconButton
    GUIFactory <|-- IconGUIFactory
    GUIFactory <|.. LightFactory
    IconGUIFactory <|.. DarkFactory
    SettingsPanel ..> GUIFactory : receives
    GUIFactory ..> Button : creates
    GUIFactory ..> Checkbox : creates
    IconGUIFactory ..> IconButton : creates
~~~

Ở sơ đồ Mermaid, mũi tên tam giác rỗng từ interface con đến interface cha biểu diễn **kế thừa hợp đồng**; mũi tên nét đứt từ concrete factory đến interface biểu diễn **realization**. Phần code dưới đây triển khai cấu trúc này.

### 6.2. Ví dụ Java hoàn chỉnh

Ví dụ chạy độc lập trong **Main.java**, với Java 8 trở lên. Họ **Light** chỉ hỗ trợ API cơ bản; họ **Dark** hỗ trợ API cơ bản và khả năng tạo IconButton. Mã SettingsPanel **không đổi** dù factory nhận vào khác nhau.

~~~java
import java.util.Objects;

public class Main {
    // Hợp đồng sản phẩm v1: giữ ổn định cho tất cả các họ.
    interface Button {
        String render();
    }

    interface Checkbox {
        String render();
    }

    interface GUIFactory {
        Button createButton();
        Checkbox createCheckbox();
    }

    // Hợp đồng mở rộng dành riêng cho năng lực icon.
    interface IconButton extends Button {
        String iconName();
    }

    interface IconGUIFactory extends GUIFactory {
        IconButton createIconButton(String iconName);
    }

    // Họ Light: hiện thực các sản phẩm v1.
    static final class LightButton implements Button {
        @Override
        public String render() {
            return "[Light] Button";
        }
    }

    static final class LightCheckbox implements Checkbox {
        @Override
        public String render() {
            return "[Light] Checkbox";
        }
    }

    static final class LightFactory implements GUIFactory {
        @Override
        public Button createButton() {
            return new LightButton();
        }

        @Override
        public Checkbox createCheckbox() {
            return new LightCheckbox();
        }
    }

    // Họ Dark: hiện thực các sản phẩm v1 và năng lực icon.
    static final class DarkButton implements Button {
        @Override
        public String render() {
            return "[Dark] Button";
        }
    }

    static final class DarkCheckbox implements Checkbox {
        @Override
        public String render() {
            return "[Dark] Checkbox";
        }
    }

    static final class DarkIconButton implements IconButton {
        private final String icon;

        DarkIconButton(String icon) {
            this.icon = Objects.requireNonNull(icon, "icon");
        }

        @Override
        public String iconName() {
            return icon;
        }

        @Override
        public String render() {
            return "[Dark] IconButton (" + icon + ")";
        }
    }

    static final class DarkFactory implements IconGUIFactory {
        @Override
        public Button createButton() {
            return new DarkButton();
        }

        @Override
        public Checkbox createCheckbox() {
            return new DarkCheckbox();
        }

        @Override
        public IconButton createIconButton(String iconName) {
            return new DarkIconButton(iconName);
        }
    }

    // Client cũ: chỉ cần hợp đồng cơ bản.
    static final class SettingsPanel {
        private final Button button;
        private final Checkbox checkbox;

        SettingsPanel(GUIFactory factory) {
            Objects.requireNonNull(factory, "factory");
            button = Objects.requireNonNull(
                    factory.createButton(), "button");
            checkbox = Objects.requireNonNull(
                    factory.createCheckbox(), "checkbox");
        }

        String render() {
            return button.render() + System.lineSeparator()
                    + checkbox.render();
        }
    }

    public static void main(String[] args) {
        if (args.length > 2) {
            throw new IllegalArgumentException(
                    "Cách dùng: java Main [light|dark] [icon]");
        }

        String theme = args.length == 0 ? "light" : args[0];
        GUIFactory factory;
        if ("light".equalsIgnoreCase(theme)) {
            factory = new LightFactory();
        } else if ("dark".equalsIgnoreCase(theme)) {
            factory = new DarkFactory();
        } else {
            throw new IllegalArgumentException(
                    "Chủ đề không hợp lệ: " + theme);
        }

        boolean needIcon = args.length == 2;
        if (needIcon && !"icon".equalsIgnoreCase(args[1])) {
            throw new IllegalArgumentException(
                    "Tùy chọn không hợp lệ: " + args[1]);
        }

        // Dùng hợp đồng công khai ban đầu.
        System.out.println(new SettingsPanel(factory).render());

        if (needIcon) {
            // Kiểm tra một khả năng mở rộng được yêu cầu.
            if (!(factory instanceof IconGUIFactory)) {
                throw new UnsupportedOperationException(
                        "Họ " + theme + " không hỗ trợ IconButton");
            }

            IconGUIFactory iconFactory = (IconGUIFactory) factory;
            IconButton iconButton = iconFactory.createIconButton("save");
            System.out.println(iconButton.render()
                    + ", icon=" + iconButton.iconName());
        }
    }
}
~~~

Biên dịch và chạy:

~~~text
javac -encoding UTF-8 Main.java

java Main light
[Light] Button
[Light] Checkbox

java Main dark
[Dark] Button
[Dark] Checkbox

java Main dark icon
[Dark] Button
[Dark] Checkbox
[Dark] IconButton (save), icon=save
~~~

Nếu chạy `java Main light icon`, chương trình in hai thành phần cơ bản rồi ném `UnsupportedOperationException` với thông báo họ Light không hỗ trợ IconButton. Đây là một **chính sách từ chối yêu cầu không được hỗ trợ**, không phải bằng chứng API cũ bị lỗi.

### 6.3. Đọc kết quả theo góc nhìn tương thích API

1. **Client cũ vẫn giữ nguyên.** SettingsPanel chỉ biết Button, Checkbox và GUIFactory.
2. **Factory cũ không cần sửa.** LightFactory không buộc phải hiện thực phương thức `createIconButton()`.
3. **Chức năng mới có hợp đồng riêng.** Những nơi bắt buộc phải có icon có thể yêu cầu `IconGUIFactory` ngay từ constructor, thay vì tự làm `instanceof` ở nhiều client.
4. **Điểm chọn cấu hình phải xử lý năng lực.** Nếu cho phép người dùng chọn Light rồi yêu cầu icon, composition root cần báo lỗi sớm hoặc có chính sách thay thế hợp lệ.

Cách phân nhánh trong `main()` chỉ để minh họa. Trong ứng dụng lớn, nên đưa việc **kiểm tra capability** vào bước lựa chọn/cấu hình và truyền đúng loại factory cho từng client, tránh rải điều kiện `instanceof` khắp mã nghiệp vụ.

## 7. Phương án dùng default method: khi nào phù hợp?

Java 8 cho phép thêm **default method** vào interface. Với một hành vi có **giá trị mặc định đúng cho tất cả các implementation**, đây có thể là cách mở rộng hợp đồng mà không buộc từng lớp cũ viết lại.

~~~java
interface Button {
    String render();

    // Chỉ phù hợp nếu mô tả mặc định có ngữ nghĩa đúng cho mọi Button.
    default String description() {
        return render();
    }
}
~~~

Tuy nhiên, default method không phải “nút bấm cứu tương thích” cho mọi tình huống:

- Nếu phương thức mới mặc định là **không làm gì**, nhưng client cần một hành vi bắt buộc, API có thể **che giấu việc một họ không hỗ trợ**.
- Hai interface khác nhau có thể cùng cung cấp một default method gây **xung đột kế thừa**, buộc lớp triển khai xử lý khi biên dịch lại hoặc gây vấn đề tương thích khi kết hợp các bản thư viện.
- Một phương thức mặc định mới có thể thay đổi cách phân giải method hoặc tương tác với các lớp có phương thức trùng tên.
- Hành vi mặc định chưa chắc phù hợp với các concrete products tồn tại nhiều năm trước đó.

Ví dụ sau có vẻ tiện nhưng nguy hiểm nếu icon là yêu cầu thật:

~~~java
// Phản ví dụ về ngữ nghĩa; không đặt cùng interface Button của ví dụ chính.
interface ButtonWithQuestionableDefault {
    String render();

    default String renderWithIcon(String iconName) {
        return render(); // Âm thầm bỏ qua icon được yêu cầu.
    }
}
~~~

Kết luận khi xét default method là: **có giá trị mặc định đúng đắn không?** Nếu không có, hãy cân nhắc **capability interface**, factory mở rộng hoặc phiên bản API mới.

## 8. Khi thay đổi là bắt buộc: lập kế hoạch phiên bản và di trú

Không phải yêu cầu nào cũng có thể mở rộng bằng một interface phụ. Nếu mọi Button từ nay bắt buộc có **accessibility name** theo hợp đồng mới, đội phát triển cần lập kế hoạch để các implementation thực sự đáp ứng quy tắc. Không nên coi một giá trị mặc định thiếu ý nghĩa là tương đương với việc triển khai đầy đủ.

Một quy trình nâng cấp có thể gồm:

1. **Định nghĩa hợp đồng mới:** làm rõ nội dung, tiền/hậu điều kiện, nullability và test tương thích.
2. **Khảo sát người dùng hợp đồng:** liệt kê các nhóm/team/plugin đang `implements Button` và những client đang gọi nó.
3. **Chuẩn bị đường di trú:** cung cấp interface mở rộng tạm thời, adapter hoặc một API phiên bản mới nếu cần.
4. **Thông báo phạm vi thay đổi:** tài liệu phiên bản phải chỉ rõ mã nào cần sửa, điểm thay thế và hành vi mới.
5. **Kiểm thử phiên bản kết hợp:** chạy client/implementation cũ với thư viện mới ở những tổ hợp có cam kết hỗ trợ.
6. **Loại bỏ hợp đồng cũ theo chính sách đã công bố:** chỉ sau khi có lộ trình và mốc ngừng hỗ trợ phù hợp.

### 8.1. Versioned interface có thể giúp tách thời điểm nâng cấp

Nếu một hợp đồng mới thực sự khác về ngữ nghĩa:

~~~java
interface ButtonV1 {
    String render();
}

interface ButtonV2 extends ButtonV1 {
    String accessibleName();
}
~~~

ButtonV2 diễn tả **khả năng bổ sung**; lớp chỉ triển khai ButtonV1 không tự động trở thành ButtonV2. Client cần tính năng mới phụ thuộc vào ButtonV2 và hệ thống phải cung cấp implementation tương ứng. Nếu sự khác biệt đến mức không thể kế thừa hợp lý, hai API riêng và một **adapter** có thể phù hợp hơn.

Đặt hậu tố V2 chỉ là một **ví dụ biểu diễn phiên bản**, không phải yêu cầu mọi dự án phải giữ V1/V2 mãi mãi. Cần quyết định dựa trên chính sách phát hành, số người phụ thuộc và chi phí duy trì song song.

### 8.2. Semantic versioning không thay thế kiểm thử

Với thư viện áp dụng **Semantic Versioning**, thay đổi API không tương thích thông thường phải được công bố ở **major version** theo chính sách dự án. Tuy nhiên, việc tăng phiên bản không tự làm cho client và plugin tương thích. Hãy tài liệu hóa rõ:

- API nào thay đổi (abstract products, abstract factory, factory registry, SPI).
- Mã cũ nào còn được hỗ trợ và trong thời gian bao lâu.
- Đâu là bản thay thế, hướng dẫn biên dịch lại và các hành vi cần sửa.
- Cần kiểm thử trên **classpath/module path** và các phiên bản plugin nào.

Một hệ thống có nhiều nhà cung cấp factory thường cần **ma trận hỗ trợ phiên bản** để tránh chạy một plugin cũ với host không phù hợp.

## 9. Kiểm tra API trước khi công khai

Việc “đóng băng” một interface không có nghĩa là không bao giờ được thay đổi. Nghĩa thực tế là **chỉ công bố những bảo đảm có thể duy trì**, còn phần chưa ổn định được đặt ở ranh giới mở rộng rõ ràng.

### 9.1. Checklist quyết định

- [ ] Đã xác định **client** và **người triển khai** từng interface, gồm plugin bên ngoài nếu có.
- [ ] Từng phương thức của abstract product là hành vi **cốt lõi có ý nghĩa với mọi họ**.
- [ ] Kiểu tham số và kiểu trả về không lộ chi tiết một nền tảng cụ thể mà các họ khác khó hỗ trợ.
- [ ] Hợp đồng mô tả nullability, exception, vòng đời, thread-safety và ngữ nghĩa kết quả.
- [ ] Abstract Factory chỉ yêu cầu tạo **những loại sản phẩm cốt lõi** phù hợp với mọi họ đã cam kết hỗ trợ.
- [ ] Những tính năng có khả năng thay đổi được xem xét dưới dạng capability interface hoặc factory mở rộng.
- [ ] Đã thử mô phỏng **thêm một họ mới** và **thêm một khả năng mới** để kiểm tra phạm vi sửa đổi.
- [ ] Có chính sách versioning/deprecation, tài liệu nâng cấp và cách phát hiện lỗi ở runtime.
- [ ] Có kiểm thử hợp đồng cho mọi concrete factory và các implementation mà nhóm phát triển kiểm soát.
- [ ] Nếu hỗ trợ plugin, đã xem xét ma trận **host version × plugin version** ở thời điểm triển khai.

### 9.2. Đo chi phí thay đổi trên một ví dụ thật

Lập một danh sách các bên chịu ảnh hưởng cho hai kịch bản:

| Kịch bản | Phần có thể cần sửa | Dấu hiệu API ổn định |
| --- | --- | --- |
| Thêm họ `HighContrast` | Các concrete products/factory mới, đăng ký hoặc cơ chế khám phá, cấu hình và kiểm thử | Client và abstract products cũ giữ nguyên |
| Bổ sung chức năng IconButton cho một số họ | Interface năng lực mới, implementation hỗ trợ, kiểm tra capability | Không ép các họ khác triển khai icon giả |
| Bắt buộc thêm một phương thức cho mọi Button | Tất cả implementations liên quan, tài liệu, client, kiểm thử, quy trình nâng cấp | Có lý do nghiệp vụ rõ và kế hoạch di trú |
| Thêm loại sản phẩm cốt lõi `Tooltip` | Abstract factory và tất cả concrete factories, cùng hợp đồng Tooltip | Chấp nhận chi phí vì mọi họ thực sự có thể đáp ứng |

**Nguyên tắc đánh giá:** nếu một đề xuất thường xuyên buộc sửa **tất cả** các implementation ở những nhóm độc lập, có thể ranh giới interface đang quá rộng hoặc chưa phản ánh đúng phần ổn định của miền nghiệp vụ.

## 10. Những lỗi thường gặp

### Lỗi 1 — Công khai toàn bộ API của một concrete product

Ví dụ lấy mọi phương thức riêng của WindowsButton đưa vào interface Button rồi yêu cầu MacButton thực hiện. Hợp đồng chung sẽ trở thành tập hợp các tính năng không phù hợp với một số họ. Nên chỉ giữ **hành vi thực sự dùng chung**, còn phần đặc thù đặt sau capability hoặc adapter.

### Lỗi 2 — Thêm phương thức vào GUIFactory cho mọi yêu cầu mới

Mỗi loại sản phẩm mới là một phương thức mà **mọi concrete factory** phải đáp ứng. Nếu đó là tính năng chỉ tồn tại ở một họ, nên xem xét factory mở rộng hoặc một nhóm sản phẩm độc lập.

### Lỗi 3 — Nhầm không lỗi biên dịch với không lỗi runtime

Mã cũ biên dịch trước khi nâng cấp thư viện có thể vẫn nạp được nhưng gặp `AbstractMethodError` khi gọi phương thức mới trên implementation cũ. Cần kiểm tra cả kết hợp **binary cũ + API mới** nếu dự án cam kết hỗ trợ.

### Lỗi 4 — Dùng default method làm giải pháp cho mọi incompatibility

Nếu default âm thầm bỏ qua hành vi bắt buộc, code vẫn chạy nhưng có thể sai nghiệp vụ. Giá trị mặc định phải có **ý nghĩa hợp lệ**, không chỉ giúp tránh sửa lớp cũ.

### Lỗi 5 — Quên hợp đồng hành vi khi đổi kiểu

Giữ nguyên `String render()` không chứng minh API ổn định nếu kết quả, lỗi hoặc điều kiện gọi thay đổi. Cần tài liệu và kiểm thử hành vi, không chỉ so sánh chữ ký.

### Lỗi 6 — Đưa interface thử nghiệm vào public API quá sớm

Khi chưa biết mọi họ có thể hỗ trợ hay không, công khai hợp đồng khiến việc sửa lại về sau tốn công cho cả client lẫn plugin. Nên thử trong phạm vi nội bộ hoặc dưới API mở rộng có chính sách thay đổi rõ ràng trước khi cam kết hỗ trợ rộng.

## 11. Bài tập vận dụng

**Bài A — Xem xét một thay đổi API:** có đề xuất thêm `void setIcon(String icon)` vào Button. Hãy liệt kê ít nhất ba loại implementation không có khái niệm icon; đề xuất giữ Button ổn định bằng capability hoặc adapter; giải thích tình huống nào cần một interface mới thay vì default method.

**Bài B — Phân tích ba lớp tương thích:** v1 công bố `String render()`; v2 đổi thành `CharSequence render()`. Hãy xác định các nhóm bị ảnh hưởng (client source, implementation source, binary cũ) và lập kế hoạch kiểm tra, không tự kết luận rằng “kiểu trả về rộng hơn thì chắc chắn tương thích”.

**Bài C — Thêm loại sản phẩm mới:** giao diện cũ có Button và Checkbox, nay yêu cầu Tooltip bắt buộc cho tất cả các họ. Hãy liệt kê các tệp API, concrete products, concrete factories và kiểm thử cần bổ sung. Nếu một họ không thể tạo Tooltip đúng nghĩa, giải thích vì sao không nên trả null chỉ để tránh thay đổi thiết kế.

**Bài D — Thiết kế plugin:** ứng dụng cho đối tác viết `PartnerButton implements Button`. Hãy lập ma trận kiểm thử khi nâng cấp Button từ v1 sang v2: build lại mã đối tác, chạy class đối tác cũ, gọi phương thức mới và kiểm thử hành vi cũ.

**Bài E — Review trước công bố:** đọc lại các interface Button, Checkbox, GUIFactory và IconGUIFactory trong ví dụ. Viết một tài liệu hợp đồng ngắn mô tả: tính không null, ý nghĩa render(), cách thông báo không hỗ trợ icon, phạm vi họ sản phẩm, và những phần **chưa** cam kết ổn định.

## 12. Ghi nhớ

- Trong Abstract Factory, **product interface** là hợp đồng mà client và các concrete products cùng phụ thuộc; khi công khai, việc thay đổi có thể ảnh hưởng nhiều nhóm và nhiều phiên bản.
- **Thêm họ sản phẩm** thường dễ hơn **thay đổi loại sản phẩm hoặc thêm phương thức bắt buộc** vào interface chung.
- Tương thích API cần xét cả **mã nguồn**, **nhị phân** và **hành vi**; ba điều này không đồng nhất.
- **Default method** chỉ phù hợp khi có hành vi mặc định hợp lệ và đã kiểm tra các xung đột tiềm ẩn.
- **Capability interface**, factory mở rộng, adapter và API theo phiên bản là những lựa chọn để phát triển chức năng mà vẫn kiểm soát tác động lên hợp đồng cũ.

**Trước khi công khai API**, hãy làm rõ phần nào thực sự bất biến với mọi họ, ai sẽ triển khai hợp đồng và cách hệ thống nâng cấp khi yêu cầu thay đổi. Một product interface ổn định giúp Abstract Factory phát huy lợi ích về khả năng thay thế và cô lập phụ thuộc; một interface công khai quá sớm có thể chuyển chi phí thay đổi từ một module sang toàn bộ hệ sinh thái sử dụng nó.
