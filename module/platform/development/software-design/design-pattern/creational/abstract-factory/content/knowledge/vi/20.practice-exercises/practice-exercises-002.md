# Vẽ sơ đồ UML và hiện thực ví dụ Light và Dark bằng Java

Trong phần **Bài tập thực hành** của chủ đề **Abstract Factory** (mẫu thiết kế khởi tạo), chúng ta sẽ thiết kế một ứng dụng mô phỏng giao diện có hai chủ đề **Light** (sáng) và **Dark** (tối). Mỗi chủ đề cung cấp bộ thành phần có kiểu hiển thị nhất quán. Bài này hướng dẫn xác định họ sản phẩm, vẽ **UML class diagram**, hiện thực bằng Java, chạy thử và đánh giá thiết kế.

Ví dụ chỉ in mô tả giao diện ra console để tập trung vào cấu trúc Abstract Factory, nên có thể chạy bằng JDK mà không cần JavaFX, Swing hay thư viện ngoài.

## 1. Mục tiêu và đề bài

Sau bài thực hành, người học có thể:

1. Phân biệt **loại sản phẩm**, **biến thể sản phẩm** và **họ sản phẩm** trong ví dụ Light/Dark.
2. Vẽ sơ đồ lớp UML đúng quan hệ giữa Abstract Factory, Concrete Factory, Abstract Product, Concrete Product và Client.
3. Hiện thực các interface, lớp cụ thể và mã client trong Java.
4. Thay đổi toàn bộ chủ đề giao diện bằng cách chọn một factory, không sửa mã của client.
5. Kiểm tra tính nhất quán của sản phẩm và nhận biết giới hạn của thiết kế.

### Yêu cầu chức năng

Ứng dụng có một màn hình tên **SettingsPanel**, sử dụng hai loại thành phần:

- **Button**: nút bấm, cung cấp thao tác render().
- **Checkbox**: ô chọn, cung cấp thao tác render().

Màn hình hỗ trợ hai **họ sản phẩm**:

| Họ sản phẩm | Biến thể Button | Biến thể Checkbox | Phong cách |
| --- | --- | --- | --- |
| Light | LightButton | LightCheckbox | Nền sáng, nội dung tối |
| Dark | DarkButton | DarkCheckbox | Nền tối, nội dung sáng |

Ràng buộc: khi màn hình được tạo với chủ đề Light, cả Button và Checkbox phải thuộc họ Light; với chủ đề Dark, cả hai phải thuộc họ Dark. Mã SettingsPanel **không được trực tiếp khởi tạo** LightButton, DarkButton, LightCheckbox hay DarkCheckbox.

### Yêu cầu thiết kế

- Có hai interface sản phẩm **Button** và **Checkbox**.
- Có một interface nhà máy **ThemeFactory** với hai phương thức createButton() và createCheckbox().
- Có hai concrete factory **LightThemeFactory** và **DarkThemeFactory**.
- Có bốn concrete product: LightButton, DarkButton, LightCheckbox, DarkCheckbox.
- Có client **SettingsPanel** nhận ThemeFactory từ bên ngoài qua constructor.
- Điểm vào chương trình (**Main**) chọn chủ đề theo tham số khởi chạy; mặc định Light.

## 2. Phân tích trước khi vẽ UML

Hãy xác định rõ mỗi thành phần đóng vai trò gì:

| Vai trò trong Abstract Factory | Thành phần trong bài | Ý nghĩa |
| --- | --- | --- |
| Abstract Product | Button, Checkbox | Hợp đồng chung cho từng loại điều khiển |
| Concrete Product | LightButton, DarkButton, LightCheckbox, DarkCheckbox | Cách biểu diễn cụ thể của từng điều khiển |
| Abstract Factory | ThemeFactory | Hợp đồng tạo một bộ điều khiển |
| Concrete Factory | LightThemeFactory, DarkThemeFactory | Tạo một bộ cùng chủ đề |
| Client | SettingsPanel | Chỉ sử dụng interface và đối tượng factory được truyền vào |
| Composition root | Main | Chọn concrete factory và lắp ghép đối tượng |

Để phân biệt **loại** và **họ**, hãy đọc ma trận sản phẩm:

- **Theo cột:** Button và Checkbox là hai loại có trách nhiệm khác nhau.
- **Theo hàng:** Light và Dark là hai họ, mỗi họ có một biến thể cho từng loại.
- **Theo ô:** LightButton hoặc DarkCheckbox là một concrete product cụ thể.

Hai biến thể LightButton và DarkButton cùng thực hiện interface Button nhưng **không thuộc cùng một họ**. Ngược lại, LightButton và LightCheckbox thuộc **cùng họ Light** dù thực hiện hai interface khác nhau.

## 3. Vẽ sơ đồ lớp UML

### 3.1. Sơ đồ tham khảo

Sử dụng cú pháp Mermaid classDiagram sau để biểu diễn UML:

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
    class ThemeFactory {
        <<interface>>
        +createButton() Button
        +createCheckbox() Checkbox
    }

    class LightButton {
        +render() String
    }
    class DarkButton {
        +render() String
    }
    class LightCheckbox {
        +render() String
    }
    class DarkCheckbox {
        +render() String
    }
    class LightThemeFactory {
        +createButton() Button
        +createCheckbox() Checkbox
    }
    class DarkThemeFactory {
        +createButton() Button
        +createCheckbox() Checkbox
    }
    class SettingsPanel {
        -button : Button
        -checkbox : Checkbox
        +SettingsPanel(factory : ThemeFactory)
        +show() String
    }

    Button <|.. LightButton
    Button <|.. DarkButton
    Checkbox <|.. LightCheckbox
    Checkbox <|.. DarkCheckbox
    ThemeFactory <|.. LightThemeFactory
    ThemeFactory <|.. DarkThemeFactory

    ThemeFactory ..> Button : createButton
    ThemeFactory ..> Checkbox : createCheckbox
    LightThemeFactory ..> LightButton : creates
    LightThemeFactory ..> LightCheckbox : creates
    DarkThemeFactory ..> DarkButton : creates
    DarkThemeFactory ..> DarkCheckbox : creates
    SettingsPanel ..> ThemeFactory : constructor parameter
    SettingsPanel --> Button : holds
    SettingsPanel --> Checkbox : holds
~~~

### 3.2. Cách đọc sơ đồ

- Mũi tên **nét đứt, tam giác rỗng** từ LightButton đến Button (ký hiệu <|..) là quan hệ **realization**: lớp triển khai interface. Các biến thể và factory khác tương tự.
- Mũi tên **phụ thuộc** từ concrete factory đến concrete product (ký hiệu ..>) cho biết factory **tạo** loại đối tượng đó.
- SettingsPanel có quan hệ **association** với Button và Checkbox vì nó giữ tham chiếu đến hai đối tượng, đồng thời phụ thuộc vào ThemeFactory thông qua tham số constructor.
- ThemeFactory phụ thuộc vào Button và Checkbox ở **kiểu trả về** của hai phương thức tạo. Nó không cần biết tên lớp LightButton hay DarkCheckbox.

Điểm cần nhận ra: **một concrete factory triển khai đầy đủ cả hai phương thức tạo sản phẩm**; mỗi phương thức trả về một biến thể thuộc cùng họ. Đó là cơ chế giữ chủ đề nhất quán trong lúc khởi tạo màn hình.

### 3.3. Sơ đồ luồng tạo đối tượng

Sơ đồ tuần tự cho thấy quyết định Light/Dark được đưa ra **trước khi** client yêu cầu sản phẩm:

~~~mermaid
sequenceDiagram
    actor User as Người chạy chương trình
    participant Main
    participant Factory as ThemeFactory
    participant Panel as SettingsPanel
    participant Button
    participant Checkbox
    User->>Main: Chọn light hoặc dark
    Main->>Main: Khởi tạo concrete factory
    Main->>Panel: new SettingsPanel(factory)
    Panel->>Factory: createButton()
    Factory-->>Panel: Button cùng chủ đề
    Panel->>Factory: createCheckbox()
    Factory-->>Panel: Checkbox cùng chủ đề
    Main->>Panel: show()
    Panel->>Button: render()
    Button-->>Panel: Chuỗi mô tả Button
    Panel->>Checkbox: render()
    Checkbox-->>Panel: Chuỗi mô tả Checkbox
    Panel-->>Main: Kết quả
~~~

Trong Java, biến Factory của sơ đồ có kiểu khai báo ThemeFactory nhưng thực tế trỏ đến **LightThemeFactory** hoặc **DarkThemeFactory**. Chính **đa hình** quyết định phương thức tạo cụ thể được gọi.

## 4. Hiện thực Java hoàn chỉnh

Tạo tệp **Main.java** và đặt toàn bộ đoạn mã dưới đây vào tệp. Ví dụ dùng các lớp lồng nhau để người mới học có thể chạy ngay trong một tệp; với dự án lớn, nên tách từng interface/lớp thành tệp tương ứng.

~~~java
public class Main {
    // Abstract Products: hai loại điều khiển giao diện.
    interface Button {
        String render();
    }

    interface Checkbox {
        String render();
    }

    // Abstract Factory: cách tạo một bộ sản phẩm cùng chủ đề.
    interface ThemeFactory {
        Button createButton();
        Checkbox createCheckbox();
    }

    // Concrete Products của họ Light.
    static final class LightButton implements Button {
        @Override
        public String render() {
            return "[Light] Button: nền trắng, chữ đen";
        }
    }

    static final class LightCheckbox implements Checkbox {
        @Override
        public String render() {
            return "[Light] Checkbox: viền xám, dấu chọn đen";
        }
    }

    // Concrete Products của họ Dark.
    static final class DarkButton implements Button {
        @Override
        public String render() {
            return "[Dark] Button: nền đen, chữ trắng";
        }
    }

    static final class DarkCheckbox implements Checkbox {
        @Override
        public String render() {
            return "[Dark] Checkbox: viền sáng, dấu chọn trắng";
        }
    }

    // Concrete Factory của họ Light.
    static final class LightThemeFactory implements ThemeFactory {
        @Override
        public Button createButton() {
            return new LightButton();
        }

        @Override
        public Checkbox createCheckbox() {
            return new LightCheckbox();
        }
    }

    // Concrete Factory của họ Dark.
    static final class DarkThemeFactory implements ThemeFactory {
        @Override
        public Button createButton() {
            return new DarkButton();
        }

        @Override
        public Checkbox createCheckbox() {
            return new DarkCheckbox();
        }
    }

    // Client: chỉ biết các abstract products và abstract factory.
    static final class SettingsPanel {
        private final Button button;
        private final Checkbox checkbox;

        SettingsPanel(ThemeFactory factory) {
            this.button = factory.createButton();
            this.checkbox = factory.createCheckbox();
        }

        String show() {
            return button.render() + System.lineSeparator()
                    + checkbox.render();
        }
    }

    // Composition root: chỉ ở đây cần biết concrete factories.
    private static ThemeFactory chooseFactory(String theme) {
        if ("light".equalsIgnoreCase(theme)) {
            return new LightThemeFactory();
        }
        if ("dark".equalsIgnoreCase(theme)) {
            return new DarkThemeFactory();
        }
        throw new IllegalArgumentException(
                "Chủ đề không hợp lệ: " + theme
                + ". Chỉ hỗ trợ light hoặc dark.");
    }

    public static void main(String[] args) {
        String theme = args.length == 0 ? "light" : args[0];
        ThemeFactory factory = chooseFactory(theme);
        SettingsPanel settingsPanel = new SettingsPanel(factory);
        System.out.println(settingsPanel.show());
    }
}
~~~

### 4.1. Phân tích các bước hiện thực

**Bước 1 — Khai báo abstract products.** Button và Checkbox chỉ quy định hành vi render(), chưa có thông tin Light/Dark. Client dùng được chúng mà không biết chi tiết từng biến thể.

**Bước 2 — Viết concrete products.** Mỗi lớp mô phỏng cách hiển thị của một loại điều khiển trong một chủ đề. Ví dụ LightButton và DarkButton cùng triển khai Button nhưng trả về chuỗi mô tả khác nhau.

**Bước 3 — Khai báo abstract factory.** ThemeFactory có cả createButton() và createCheckbox(). Mỗi phương thức trả về **interface**, không trả về trực tiếp kiểu LightButton hay DarkCheckbox.

**Bước 4 — Viết concrete factories.** LightThemeFactory luôn trả về LightButton và LightCheckbox; DarkThemeFactory luôn trả về DarkButton và DarkCheckbox. Đây là chỗ chứa quyết định biến thể.

**Bước 5 — Viết client.** SettingsPanel nhận factory qua constructor, gọi cả hai phương thức tạo và chỉ lưu tham chiếu kiểu Button, Checkbox. Mã client vì thế không chứa lệnh kiểm tra chủ đề hoặc tên của các concrete product.

**Bước 6 — Chọn họ tại composition root.** Main đọc tham số dòng lệnh, chọn concrete factory phù hợp rồi cung cấp cho SettingsPanel. Việc thêm cách chọn theo cấu hình, môi trường hoặc dependency injection có thể được triển khai ở đây mà không phải sửa thuật toán hiển thị của SettingsPanel.

## 5. Biên dịch, chạy và đối chiếu kết quả

Với JDK đã cài và lệnh javac/java có trong PATH, mở terminal tại thư mục chứa Main.java rồi thực hiện:

~~~text
javac -encoding UTF-8 Main.java
java Main light
~~~

Kết quả:

~~~text
[Light] Button: nền trắng, chữ đen
[Light] Checkbox: viền xám, dấu chọn đen
~~~

Đổi sang Dark mà **không sửa SettingsPanel**:

~~~text
java Main dark
~~~

Kết quả:

~~~text
[Dark] Button: nền đen, chữ trắng
[Dark] Checkbox: viền sáng, dấu chọn trắng
~~~

Không truyền tham số thì chương trình mặc định Light:

~~~text
java Main
~~~

Nếu truyền một chủ đề không được hỗ trợ, ví dụ java Main blue, chương trình ném IllegalArgumentException với thông báo chủ đề không hợp lệ. Hành vi này giúp tránh âm thầm sử dụng sai bộ sản phẩm.

**Lưu ý:** trong bài tập, render() chỉ trả về chuỗi mô tả, không tạo nút bấm hay ô chọn đồ họa thực sự. Khi tích hợp thư viện UI, cùng ý tưởng vẫn áp dụng: concrete product chuyển sang thực hiện lời gọi UI tương ứng.

## 6. Kiểm chứng thiết kế với các trường hợp cụ thể

Thay vì chỉ kiểm tra xem chương trình có in ra màn hình hay không, hãy kiểm tra tính đúng đắn của mô hình Abstract Factory.

| Trường hợp | Cách thực hiện | Kết quả mong đợi |
| --- | --- | --- |
| Chạy chủ đề Light | java Main light | Cả hai dòng đều bắt đầu bằng [Light] |
| Chạy chủ đề Dark | java Main dark | Cả hai dòng đều bắt đầu bằng [Dark] |
| Không truyền tham số | java Main | Dùng họ Light mặc định |
| Thử chữ hoa/chữ thường | java Main DARK | Vẫn dùng họ Dark |
| Truyền chủ đề lạ | java Main blue | Thông báo lỗi đầu vào, không tạo màn hình |
| Rà soát SettingsPanel | Đọc constructor và show() | Không có new LightButton, new DarkCheckbox hay điều kiện light/dark |

Có thể bổ sung một phép kiểm tra nhỏ trong phương thức main, ngay sau khi chọn factory và trước khi tạo SettingsPanel, để kiểm tra một factory có cung cấp đúng họ:

~~~java
// Đoạn bổ sung tùy chọn trong main, không phải một chương trình độc lập.
String expected = "dark".equalsIgnoreCase(theme) ? "[Dark]" : "[Light]";
String buttonText = factory.createButton().render();
String checkboxText = factory.createCheckbox().render();

if (!buttonText.startsWith(expected)
        || !checkboxText.startsWith(expected)) {
    throw new AssertionError("Factory đã trộn hai họ sản phẩm");
}
~~~

Phép kiểm tra trên đủ minh họa quy tắc của ví dụ console; trong dự án thật, **chuỗi hiển thị không phải bằng chứng tin cậy về kiểu hay khả năng tương thích**. Nên kiểm thử factory theo những thuộc tính và ràng buộc thực sự của sản phẩm, ví dụ theme token, giao thức hoặc hành vi được công bố trong hợp đồng.

### Điều gì xảy ra khi không dùng cùng một factory?

Nếu client tự ghép như sau, chương trình vẫn có thể biên dịch nhưng giao diện bị trộn chủ đề:

~~~java
// Đoạn mã phản ví dụ: KHÔNG đưa vào SettingsPanel.
Button button = new LightButton();
Checkbox checkbox = new DarkCheckbox();
~~~

Việc interface Button và Checkbox hợp lệ **không tự bảo đảm** chúng thuộc cùng một họ. Abstract Factory tạo ra một **điểm khởi tạo thống nhất** giúp giữ quy ước này, nhưng mỗi concrete factory vẫn phải được triển khai đúng.

## 7. Bài tập tự luyện

Sau khi chạy ví dụ gốc, hãy tự giải các bài sau. Mỗi bài yêu cầu cập nhật UML trước khi sửa Java; như vậy sơ đồ luôn phản ánh thiết kế.

### Bài A — Thêm loại sản phẩm mới: TextField

**Yêu cầu:**

1. Thêm interface TextField với phương thức render() trả về String.
2. Viết LightTextField và DarkTextField.
3. Bổ sung createTextField() vào ThemeFactory và hiện thực ở **cả hai** concrete factory.
4. Mở rộng SettingsPanel để hiển thị Button, Checkbox và TextField.

**Tiêu chí đạt:** mỗi lần chạy Light hoặc Dark có ba dòng kết quả thuộc cùng chủ đề; UML bổ sung quan hệ interface/realization và phụ thuộc tạo sản phẩm tương ứng. Không cần thêm điều kiện rẽ nhánh chủ đề vào SettingsPanel.

**Điểm cần nhận ra:** thêm một **loại sản phẩm** buộc sửa interface factory và **mọi concrete factory**. Đây là đánh đổi thường gặp của Abstract Factory.

### Bài B — Thêm họ sản phẩm mới: HighContrast

**Yêu cầu:**

1. Viết HighContrastButton và HighContrastCheckbox, có mô tả tương phản cao.
2. Viết HighContrastThemeFactory triển khai ThemeFactory.
3. Cập nhật chooseFactory() để hỗ trợ tham số high-contrast.
4. Cập nhật sơ đồ UML với factory và sản phẩm mới.

**Tiêu chí đạt:** chạy java Main high-contrast tạo cả Button lẫn Checkbox thuộc họ HighContrast, không cần sửa SettingsPanel hoặc các interface sản phẩm hiện hữu.

**Điểm cần nhận ra:** thêm **họ mới** thường thuận tiện hơn thêm **loại mới**, miễn là các loại sản phẩm hiện có đủ đáp ứng yêu cầu.

### Bài C — Cô lập phụ thuộc và thử nghiệm client

**Yêu cầu:** tạo một FakeThemeFactory trả về Button và Checkbox giả, chỉ ghi lại việc render() được gọi. Dùng factory đó để kiểm tra SettingsPanel **không phụ thuộc** vào LightButton hoặc DarkButton.

Gợi ý: vì Button và Checkbox chỉ có một phương thức trừu tượng, có thể dùng lambda như sau:

~~~java
// Ví dụ dùng bên trong một lớp implement ThemeFactory.
public Button createButton() {
    return () -> "[Fake] Button";
}

public Checkbox createCheckbox() {
    return () -> "[Fake] Checkbox";
}
~~~

**Tiêu chí đạt:** SettingsPanel hiển thị kết quả của hai fake products và không cần biết các lớp Light/Dark. Trong dự án thật, dùng assertion của bộ kiểm thử để kiểm tra hành vi thay vì chỉ quan sát console.

### Bài D — Phân tích một thay đổi thiết kế

Giả sử ứng dụng cần chuyển từ Light sang Dark **ngay khi người dùng nhấn nút**, không tạo lại toàn bộ chương trình. Hãy trả lời:

- Chỉ đổi biến factory trong Main có đủ làm thay đổi Button/Checkbox đã được tạo trước đó không?
- Nên tạo lại SettingsPanel, hay cho SettingsPanel hỗ trợ thay thế bộ sản phẩm và xử lý trạng thái?
- Nếu có dữ liệu nhập liệu hoặc sự kiện đang chờ, hệ thống cần giữ lại trạng thái nào khi thay chủ đề?

**Gợi ý:** factory quyết định *đối tượng được tạo*, không tự cập nhật những đối tượng đã tồn tại. Nếu cần thay đổi chủ đề khi chạy, hãy thiết kế vòng đời và việc chuyển trạng thái riêng.

## 8. Các lỗi phổ biến khi thực hiện bài

### 8.1. Concrete Factory chỉ tạo một loại sản phẩm

Nếu LightThemeFactory chỉ có createButton() còn Checkbox được tạo rải rác trong client, factory không chịu trách nhiệm đầy đủ với họ sản phẩm. Sửa bằng cách đưa thao tác tạo Checkbox vào ThemeFactory và hiện thực đồng bộ ở các concrete factory.

### 8.2. Phương thức factory trả về kiểu cụ thể

Ví dụ khai báo ThemeFactory.createButton() trả về LightButton làm hợp đồng bị gắn cứng với họ Light. Hợp đồng chung cần trả về **Button**; concrete factory vẫn được phép tạo LightButton bên trong.

### 8.3. Client tự kiểm tra chủ đề

Nếu SettingsPanel có điều kiện kiểm tra Light/Dark để gọi new tương ứng, mã client bị phụ thuộc vào các biến thể. Hãy đưa việc chọn factory ra Main hoặc nơi lắp ghép đối tượng, còn SettingsPanel chỉ nhận ThemeFactory.

### 8.4. Đồng nhất “thay đổi factory” với “đổi chủ đề trực tiếp”

SettingsPanel trong ví dụ lưu Button và Checkbox ngay khi khởi tạo. Thay biến trỏ đến factory sau thời điểm đó không làm hai sản phẩm đã tạo tự đổi chủ đề. Muốn đổi trực tiếp, cần xác định cách tạo lại hoặc cập nhật chúng.

### 8.5. Dùng Abstract Factory khi không có họ sản phẩm

Với bài toán chỉ có một Button và không cần bộ sản phẩm liên quan, cấu trúc gồm nhiều factory và interface có thể quá mức cần thiết. Abstract Factory phát huy giá trị khi các **loại sản phẩm khác nhau cần được tạo đồng bộ** theo Light, Dark hoặc các họ khác.

## 9. Checklist tự đánh giá

Trước khi kết thúc, hãy tự kiểm tra:

- [ ] UML thể hiện đầy đủ hai abstract products và một abstract factory.
- [ ] LightThemeFactory và DarkThemeFactory đều triển khai ThemeFactory.
- [ ] Mỗi concrete product triển khai đúng interface sản phẩm tương ứng.
- [ ] Từng concrete factory trả về **cả Button và Checkbox thuộc cùng họ**.
- [ ] SettingsPanel chỉ tham chiếu Button, Checkbox và ThemeFactory.
- [ ] Chạy được cả hai chủ đề bằng cùng một mã client.
- [ ] Đã giải thích được vì sao thêm họ mới và thêm loại mới có chi phí thay đổi khác nhau.
- [ ] Phân biệt được cơ chế tạo sản phẩm với việc chuyển giao diện khi ứng dụng đang chạy.

**Kết quả mong đợi của bài thực hành:** bạn có thể đọc sơ đồ UML để xác định chính xác từng vai trò trong Abstract Factory, triển khai Java theo sơ đồ và chứng minh rằng thay **LightThemeFactory** bằng **DarkThemeFactory** sẽ tạo một bộ sản phẩm cùng chủ đề mà không làm SettingsPanel phụ thuộc vào các lớp giao diện cụ thể.
