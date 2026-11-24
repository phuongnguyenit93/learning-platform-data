# Phân biệt loại sản phẩm, biến thể sản phẩm và họ sản phẩm

Khi học **Abstract Factory**, ba khái niệm dễ bị lẫn nhất là **loại sản phẩm** (product type), **biến thể sản phẩm** (product variant) và **họ sản phẩm** (product family). Phân biệt đúng ba khái niệm này giúp xác định các interface cần thiết, thiết kế factory và tránh tạo ra những đối tượng không tương thích trong cùng một chức năng.

Trong phạm vi thiết kế phần mềm, “sản phẩm” là **đối tượng được tạo ra bởi factory**, không nhất thiết là hàng hóa bán cho người dùng. Ví dụ một nút bấm, một ô chọn, một kết nối cơ sở dữ liệu đều có thể là sản phẩm.

## 1. Mô hình hai chiều: loại sản phẩm và họ sản phẩm

Giả sử một ứng dụng desktop cần giao diện riêng cho Windows và macOS. Ở mỗi hệ điều hành, màn hình có **nút bấm** và **ô chọn**:

| Họ sản phẩm / Loại sản phẩm | Nút bấm (Button) | Ô chọn (Checkbox) |
| --- | --- | --- |
| **Windows** | WindowsButton | WindowsCheckbox |
| **macOS** | MacButton | MacCheckbox |

Hãy đọc bảng theo ba cách:

- **Đọc theo cột:** Button và Checkbox là **hai loại sản phẩm** khác nhau. Các đối tượng cùng một cột thực hiện cùng một vai trò và tuân theo cùng hợp đồng (interface), dù chúng mang phong cách của hệ điều hành khác nhau.
- **Nhìn vào từng ô:** WindowsButton, MacButton, WindowsCheckbox, MacCheckbox là **các biến thể sản phẩm cụ thể**. Chẳng hạn, WindowsButton và MacButton là hai biến thể của loại Button.
- **Đọc theo hàng:** WindowsButton đi cùng WindowsCheckbox tạo thành **họ sản phẩm Windows**; MacButton đi cùng MacCheckbox tạo thành **họ sản phẩm macOS**. Thành viên trong cùng một hàng được thiết kế để hoạt động và hiển thị nhất quán với nhau.

**Điểm mấu chốt:** loại sản phẩm trả lời câu hỏi **“Đối tượng có nhiệm vụ gì?”**; biến thể trả lời **“Nhiệm vụ đó được thực hiện theo cách nào?”**; họ sản phẩm trả lời **“Những biến thể nào thuộc cùng một ngữ cảnh và có thể sử dụng đồng bộ?”**.

## 2. Loại sản phẩm (product type)

**Loại sản phẩm** mô tả một nhóm đối tượng có cùng vai trò, hành vi hoặc hợp đồng mà mã sử dụng chúng có thể dựa vào. Trong ví dụ giao diện:

- **Button**: một thành phần nút bấm có khả năng hiển thị.
- **Checkbox**: một thành phần ô chọn có khả năng hiển thị.

Trong Java, ta thường thể hiện loại sản phẩm bằng **interface** (abstract product). Một loại có thể có nhiều hiện thực cụ thể:

~~~java
interface Button {
    void render();
}

interface Checkbox {
    void render();
}
~~~

Hai interface này diễn đạt **đối tượng làm được gì**, không buộc mã khách hàng biết nút bấm đó có giao diện Windows hay macOS. Cả WindowsButton lẫn MacButton đều thực hiện Button; còn WindowsCheckbox và MacCheckbox thực hiện Checkbox.

“Loại” trong bài học này là **vai trò thiết kế** của sản phẩm. Nó không nhất thiết trùng với một lớp cha duy nhất, cũng không có nghĩa mọi sản phẩm thuộc cùng một họ phải triển khai cùng một interface. Trái lại, một họ thường chứa **nhiều loại khác nhau**.

## 3. Biến thể sản phẩm (product variant)

**Biến thể sản phẩm** là một hiện thực cụ thể của **một loại sản phẩm** cho một nền tảng, phong cách, cấu hình hoặc môi trường nhất định.

Ví dụ:

- WindowsButton: hiện thực Button theo phong cách Windows.
- MacButton: hiện thực Button theo phong cách macOS.
- WindowsCheckbox: hiện thực Checkbox theo phong cách Windows.
- MacCheckbox: hiện thực Checkbox theo phong cách macOS.

Trong thuật ngữ của mẫu thiết kế, những lớp như WindowsButton hay MacButton thường được gọi là **concrete product**. Một đối tượng được tạo từ lớp WindowsButton là **instance của biến thể đó**; cần phân biệt lớp/kiểu hiện thực với từng instance trong bộ nhớ.

~~~java
final class WindowsButton implements Button {
    @Override
    public void render() {
        System.out.println("Windows button");
    }
}

final class MacButton implements Button {
    @Override
    public void render() {
        System.out.println("macOS button");
    }
}
~~~

Hai lớp trên khác cách thực hiện nhưng có thể thay thế cho nhau **ở những nơi chỉ cần hợp đồng Button**. Sự thay thế này không tự bảo đảm rằng chúng sẽ tương thích về giao diện hoặc hành vi với *các loại sản phẩm khác* đang có trên màn hình. Đó là lý do cần xét thêm **họ sản phẩm**.

### Biến thể không đồng nghĩa với loại sản phẩm mới

Nếu chỉ đổi cách vẽ nút bấm từ Windows sang macOS, ta đang tạo **biến thể khác của Button**, chứ không tự nhiên tạo một loại sản phẩm mới. Ngược lại, nếu cần thêm thanh trượt (Slider) có vai trò khác nút bấm và ô chọn, đó là **loại sản phẩm mới**. Mỗi họ có thể cần cung cấp một biến thể Slider tương ứng.

## 4. Họ sản phẩm (product family)

**Họ sản phẩm** là tập hợp các biến thể **thuộc những loại sản phẩm khác nhau** nhưng cùng tuân theo một bối cảnh thiết kế, nền tảng, giao thức hoặc tập quy tắc tương thích.

Với ví dụ trên:

- **Họ Windows:** WindowsButton + WindowsCheckbox.
- **Họ macOS:** MacButton + MacCheckbox.

Một họ được xác định bằng **tính nhất quán hoặc khả năng phối hợp giữa các sản phẩm**, chứ không chỉ vì tên lớp có chung tiền tố. Cùng một họ có thể chia sẻ quy tắc về màu sắc, khoảng cách, hành vi điều khiển, thư viện nền tảng hoặc phiên bản giao thức. Trong một hệ thống cụ thể, các ràng buộc tương thích phải được xác định rõ theo yêu cầu nghiệp vụ/kỹ thuật.

Ví dụ, nếu màn hình được cấu hình dùng phong cách Windows nhưng lại tạo WindowsButton cùng MacCheckbox, mỗi đối tượng vẫn có thể hoạt động riêng lẻ; tuy nhiên toàn bộ giao diện có thể thiếu nhất quán. Với các hệ thống khác, việc trộn sản phẩm khác họ còn có thể gây lỗi giao thức hoặc cấu hình. **Abstract Factory giúp thống nhất việc chọn họ khi tạo sản phẩm**.

### Tại sao “họ” không chỉ là tập các biến thể của một loại?

Tập {WindowsButton, MacButton} gồm **hai biến thể của cùng loại Button**. Đó là một tập hợp các biến thể, **không phải họ Windows**. Họ Windows cần gồm các sản phẩm Windows có *vai trò khác nhau*, ví dụ WindowsButton và WindowsCheckbox.

Sơ đồ sau diễn tả cách các factory cụ thể tạo ra các thành viên tương ứng:

~~~mermaid
flowchart TB
    Client["Màn hình dùng interface"] --> Factory["GUIFactory"]
    WindowsFactory["WindowsFactory"] -. "triển khai" .-> Factory
    MacFactory["MacFactory"] -. "triển khai" .-> Factory
    WindowsFactory --> WindowsButton["WindowsButton : Button"]
    WindowsFactory --> WindowsCheckbox["WindowsCheckbox : Checkbox"]
    MacFactory --> MacButton["MacButton : Button"]
    MacFactory --> MacCheckbox["MacCheckbox : Checkbox"]
    subgraph WindowsFamily["Họ Windows"]
        WindowsButton
        WindowsCheckbox
    end
    subgraph MacFamily["Họ macOS"]
        MacButton
        MacCheckbox
    end
~~~

Các đường nối từ factory tới sản phẩm thể hiện **trách nhiệm khởi tạo**; các nhóm thể hiện **họ**. Một factory Windows không nên trả về MacCheckbox khi ứng dụng đang cần một bộ sản phẩm Windows nhất quán.

## 5. Kết nối ba khái niệm trong Abstract Factory

**Abstract Factory** cung cấp một interface để tạo ra **các sản phẩm có liên quan hoặc phụ thuộc lẫn nhau**, mà mã khách hàng không cần phụ thuộc trực tiếp vào các lớp sản phẩm cụ thể.

Các vai trò ánh xạ như sau:

| Thành phần của mẫu | Trong ví dụ | Trách nhiệm |
| --- | --- | --- |
| Abstract product | Button, Checkbox | Định nghĩa hợp đồng cho **từng loại sản phẩm** |
| Concrete product | WindowsButton, MacButton, WindowsCheckbox, MacCheckbox | Cài đặt **biến thể** của một loại |
| Abstract factory | GUIFactory | Định nghĩa cách tạo **tất cả loại sản phẩm** được hỗ trợ |
| Concrete factory | WindowsFactory, MacFactory | Tạo các biến thể thuộc **một họ sản phẩm** |
| Client | SettingsScreen | Sử dụng Button, Checkbox thông qua interface, nhận sản phẩm từ factory được cung cấp |

### Ví dụ Java hoàn chỉnh

Ví dụ dưới đây chạy độc lập với một tệp **Main.java**. Phần chọn nền tảng được đặt ở đầu chương trình; màn hình chỉ biết đến các interface:

~~~java
public class Main {
    // Hai loại sản phẩm (abstract products).
    interface Button {
        void render();
    }

    interface Checkbox {
        void render();
    }

    // Hai biến thể thuộc họ Windows.
    static final class WindowsButton implements Button {
        @Override
        public void render() {
            System.out.println("[Windows] Button");
        }
    }

    static final class WindowsCheckbox implements Checkbox {
        @Override
        public void render() {
            System.out.println("[Windows] Checkbox");
        }
    }

    // Hai biến thể thuộc họ macOS.
    static final class MacButton implements Button {
        @Override
        public void render() {
            System.out.println("[macOS] Button");
        }
    }

    static final class MacCheckbox implements Checkbox {
        @Override
        public void render() {
            System.out.println("[macOS] Checkbox");
        }
    }

    // Abstract Factory: một hợp đồng tạo cả hai loại sản phẩm.
    interface GUIFactory {
        Button createButton();
        Checkbox createCheckbox();
    }

    // Concrete Factory: chỉ tạo các biến thể thuộc họ Windows.
    static final class WindowsFactory implements GUIFactory {
        @Override
        public Button createButton() {
            return new WindowsButton();
        }

        @Override
        public Checkbox createCheckbox() {
            return new WindowsCheckbox();
        }
    }

    // Concrete Factory: chỉ tạo các biến thể thuộc họ macOS.
    static final class MacFactory implements GUIFactory {
        @Override
        public Button createButton() {
            return new MacButton();
        }

        @Override
        public Checkbox createCheckbox() {
            return new MacCheckbox();
        }
    }

    // Client không biết các lớp WindowsButton, MacButton, ...
    static final class SettingsScreen {
        private final Button button;
        private final Checkbox checkbox;

        SettingsScreen(GUIFactory factory) {
            this.button = factory.createButton();
            this.checkbox = factory.createCheckbox();
        }

        void render() {
            button.render();
            checkbox.render();
        }
    }

    public static void main(String[] args) {
        // Đây là nơi chọn họ sản phẩm cho toàn bộ màn hình.
        GUIFactory factory = args.length > 0
                && "mac".equalsIgnoreCase(args[0])
                ? new MacFactory()
                : new WindowsFactory();

        SettingsScreen screen = new SettingsScreen(factory);
        screen.render();
    }
}
~~~

Biên dịch và chạy:

~~~text
javac Main.java
java Main
[Windows] Button
[Windows] Checkbox

java Main mac
[macOS] Button
[macOS] Checkbox
~~~

Những điểm cần quan sát:

1. **SettingsScreen** cần hai loại sản phẩm, Button và Checkbox, nên không tạo trực tiếp một lớp Windows hay Mac nào.
2. **GUIFactory** khai báo **hai phương thức tạo sản phẩm** tương ứng với hai loại. Đây là hợp đồng chung cho việc tạo các thành viên trong một họ.
3. **WindowsFactory** cung cấp cả WindowsButton và WindowsCheckbox; **MacFactory** cung cấp cả MacButton và MacCheckbox. Chọn một concrete factory đồng nghĩa chọn một họ.
4. Đoạn quyết định dùng Windows hay macOS nằm tại **composition root** (vị trí ghép các phụ thuộc ở đầu chương trình). Mã màn hình không cần rải các điều kiện kiểm tra hệ điều hành.
5. Ví dụ dùng thao tác in ra console để thấy kết quả; trong ứng dụng thật, phương thức render có thể gọi API giao diện tương ứng.

**Lưu ý về bảo đảm tương thích:** interface GUIFactory quy định có thể tạo Button và Checkbox nhưng bản thân Java type system không chứng minh mọi concrete factory luôn trả đúng họ. Tính nhất quán của mỗi họ là **bất biến thiết kế** cần được bảo vệ bằng cách triển khai factory đúng và kiểm thử phù hợp.

## 6. Nhận diện nhanh bằng cách đổi từng chiều

Giữ nguyên ví dụ giao diện:

| Yêu cầu thay đổi | Thứ thay đổi | Ảnh hưởng thiết kế |
| --- | --- | --- |
| Dùng nút bấm macOS thay nút bấm Windows | **Biến thể** của loại Button | Chọn hiện thực MacButton thay cho WindowsButton |
| Thêm ô chọn vào màn hình chỉ có nút bấm | **Loại sản phẩm** | Cần hợp đồng Checkbox và phương thức tạo tương ứng |
| Chuyển toàn bộ màn hình từ Windows sang macOS | **Họ sản phẩm** | Cung cấp MacFactory thay cho WindowsFactory |
| Hỗ trợ thêm giao diện Linux gồm nút bấm và ô chọn | **Họ sản phẩm mới** | Thêm LinuxButton, LinuxCheckbox, LinuxFactory |
| Thêm thanh trượt cho tất cả nền tảng | **Loại sản phẩm mới** | Bổ sung Slider, các biến thể Slider và phương thức createSlider() ở các factory |

Ma trận hai chiều cho thấy hai hướng mở rộng của Abstract Factory **không cân xứng**:

- **Thêm họ sản phẩm mới** thường thuận tiện: tạo các concrete product mới và một concrete factory mới. Các client hiện có vẫn dùng các interface cũ; phần cấu hình cần biết cách chọn factory mới.
- **Thêm loại sản phẩm mới** thường tốn công hơn: phải mở rộng abstract factory và cập nhật **mọi concrete factory** để cung cấp sản phẩm mới. Đây là điểm đánh đổi quan trọng của mẫu.

Vì thế Abstract Factory phù hợp nhất khi **tập loại sản phẩm tương đối ổn định**, còn hệ thống cần hỗ trợ **nhiều họ sản phẩm có thể thay thế nhau**.

## 7. Những nhầm lẫn thường gặp

### Nhầm 1: “Button là một họ sản phẩm”

**Button là một loại sản phẩm**. WindowsButton và MacButton là các biến thể của Button. Một họ Windows gồm nhiều loại, chẳng hạn WindowsButton **và** WindowsCheckbox.

### Nhầm 2: “WindowsButton và WindowsCheckbox là cùng một loại vì cùng họ”

Chúng thuộc **cùng họ** nhưng **khác loại**: một đối tượng phục vụ vai trò nút bấm, đối tượng kia phục vụ vai trò ô chọn. Việc thuộc cùng họ không yêu cầu chúng dùng cùng interface.

### Nhầm 3: “Đã dùng interface thì tự động bảo đảm cùng họ”

Hai đối tượng cùng tuân theo interface riêng của chúng chưa chắc đồng bộ với nhau. Ví dụ mã bên dưới tạo lẫn hai họ:

~~~java
Button button = new WindowsButton();
Checkbox checkbox = new MacCheckbox(); // Khác họ với button
~~~

Mã có thể biên dịch nếu các lớp khả dụng trong phạm vi đó, nhưng quy tắc “một màn hình dùng một họ giao diện” đã bị vi phạm. Dùng **một concrete factory** để tạo toàn bộ các thành phần liên quan sẽ giúp duy trì quy tắc này.

### Nhầm 4: “Mỗi lớp con là một loại sản phẩm”

Tên lớp cụ thể không quyết định đó là **loại** hay **biến thể**. Nếu hai lớp cùng thực hiện một hợp đồng Button và chỉ khác nền tảng, chúng là hai biến thể của **một loại**.

### Nhầm 5: “Cứ có nhiều lớp tương tự nhau là cần Abstract Factory”

Mẫu này có giá trị khi ứng dụng cần **tạo đồng bộ nhiều loại sản phẩm liên quan theo từng họ**. Nếu chỉ tạo một loại đối tượng, một factory đơn giản hoặc Factory Method có thể đủ. Nếu các sản phẩm không có yêu cầu nhất quán hay tương thích theo nhóm, việc thêm nhiều interface và factory có thể làm thiết kế phức tạp không cần thiết.

## 8. Cách xác định loại, biến thể và họ trước khi thiết kế

Khi phân tích một hệ thống, có thể làm lần lượt:

1. **Liệt kê các vai trò mà client thực sự sử dụng.** Ví dụ: Button, Checkbox, Slider. Đó là những ứng viên cho **loại sản phẩm**.
2. **Xác định các bối cảnh cần một bộ sản phẩm nhất quán.** Ví dụ: Windows, macOS, Linux hoặc các bộ giao diện sáng/tối. Đó là những ứng viên cho **họ sản phẩm**. Chỉ tách thành họ khi có quy tắc chung thực sự.
3. **Lập ma trận loại × họ.** Với mỗi ô, xác định biến thể cụ thể. Nếu một số ô không tồn tại hoặc có ràng buộc đặc biệt, phải giải quyết yêu cầu đó thay vì tự giả định mọi kết hợp đều hợp lệ.
4. **Định nghĩa abstract product cho từng loại.** Chỉ đặt vào interface những hành vi client cần; tránh đưa chi tiết đặc thù của một họ vào hợp đồng chung nếu các họ khác không thể thực hiện hợp lý.
5. **Định nghĩa abstract factory và concrete factory.** Mỗi concrete factory tạo ra bộ biến thể của một họ; client nhận factory qua tham số hoặc dependency injection.
6. **Kiểm thử tính nhất quán theo họ.** Xác minh factory cung cấp đủ các loại sản phẩm và chúng tuân theo quy tắc tương thích, giao diện hoặc giao thức đã đặt ra.

Một ví dụ ngoài giao diện là phần mềm tạo **bộ tài liệu** theo định dạng. Các loại sản phẩm có thể là DocumentWriter và DocumentReader; các họ có thể là JSON và XML; biến thể là JsonWriter, JsonReader, XmlWriter, XmlReader. Chỉ nên coi đây là các họ theo Abstract Factory khi hệ thống thật sự yêu cầu reader và writer được lựa chọn thành một bộ tương thích. Nếu chúng hoàn toàn độc lập, thiết kế factory riêng có thể rõ ràng hơn.

## 9. Ghi nhớ

- **Loại sản phẩm = vai trò/hợp đồng** mà client sử dụng (**Button**, **Checkbox**).
- **Biến thể sản phẩm = cách hiện thực cụ thể của một loại** (**WindowsButton**, **MacButton**).
- **Họ sản phẩm = bộ biến thể thuộc các loại khác nhau nhưng cùng bối cảnh tương thích** (**WindowsButton + WindowsCheckbox**).
- **Abstract Factory = hợp đồng tạo một bộ sản phẩm**, còn **concrete factory = nơi lựa chọn và tạo các biến thể thuộc cùng một họ**.

Khi chưa chắc một thực thể là loại, biến thể hay họ, hãy đặt nó vào **ma trận “họ theo hàng, loại theo cột”**. Vị trí trong ma trận thường làm rõ ngay vai trò thiết kế của thực thể đó.
