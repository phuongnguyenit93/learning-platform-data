# Lắp ráp chương trình trong main và chạy lần lượt hai họ sản phẩm

## 1. Mục tiêu: kiểm chứng Abstract Factory bằng một chương trình chạy được

Khi học **Abstract Factory** trong nhóm **Creational Design Patterns**, các interface và concrete factory mới chỉ là một phần của thiết kế. Ta còn phải **lắp ráp các đối tượng tại điểm khởi động chương trình** và chứng minh rằng **cùng một client** hoạt động được với **nhiều họ sản phẩm**.

Giả sử ứng dụng có hai bộ giao diện:

- **Windows:** `WindowsButton` và `WindowsCheckbox`.
- **macOS:** `MacButton` và `MacCheckbox`.

Một màn hình cài đặt cần hiển thị nút **Lưu thay đổi** và checkbox **Nhận thông báo**. Màn hình đó không nên chứa câu lệnh `new WindowsButton()`, `new MacCheckbox()` hay điều kiện kiểm tra hệ điều hành để quyết định từng widget.

Thay vào đó:

1. `main()` tạo factory Windows.
2. `main()` truyền factory đó vào cùng một lớp client, rồi yêu cầu client hiển thị.
3. `main()` tạo factory macOS.
4. `main()` truyền factory macOS vào **cùng lớp client**, rồi hiển thị lần nữa.
5. Kết quả cho thấy cả nút và checkbox của mỗi lần chạy thuộc **cùng một họ**, trong khi mã client không đổi.

**Trọng tâm của bài học:** `main()` đóng vai trò **composition root** — nơi lựa chọn concrete factory và kết nối dependency. Ví dụ cố ý chạy **lần lượt cả hai họ trong một lần thực thi** để dễ quan sát sự thay thế giữa các biến thể. Ứng dụng production thường chỉ chọn một họ phù hợp với cấu hình hoặc ngữ cảnh của từng phiên.

## 2. Chuẩn bị cấu trúc: ai tạo, ai sử dụng?

### 2.1. Hai loại sản phẩm và hai họ triển khai

| Vai trò | Họ Windows | Họ macOS |
| --- | --- | --- |
| `Button` | `WindowsButton` | `MacButton` |
| `Checkbox` | `WindowsCheckbox` | `MacCheckbox` |
| Concrete Factory | `WindowsUIFactory` | `MacUIFactory` |
| Client nhận factory | `SettingsScreen` | **Cùng `SettingsScreen`** |

Có hai hướng đọc bảng:

- Theo **hàng**: những lớp cụ thể nào thực hiện cùng một interface sản phẩm?
- Theo **cột**: các sản phẩm nào phải được tạo cùng nhau để giao diện nhất quán theo một biến thể?

Abstract Factory đặc biệt hữu ích cho **hướng theo cột**: một factory tạo nhiều **loại sản phẩm** thuộc cùng một **họ**.

### 2.2. Các vai trò trong chương trình

| Thành phần | Trách nhiệm |
| --- | --- |
| `Button` và `Checkbox` | **Abstract Products**: mô tả các thao tác GUI mà client cần |
| `WindowsButton`, `MacButton`, `WindowsCheckbox`, `MacCheckbox` | **Concrete Products**: cung cấp hành vi của từng biến thể |
| `UIFactory` | **Abstract Factory**: khai báo cách yêu cầu tạo Button và Checkbox |
| `WindowsUIFactory` và `MacUIFactory` | **Concrete Factories**: chọn lớp cụ thể cho toàn bộ họ |
| `SettingsScreen` | **Client**: nhận factory và sử dụng sản phẩm qua interface |
| `AbstractFactoryMainDemo.main()` | **Composition root**: tạo factory, truyền dependency và gọi client |

Sơ đồ phụ thuộc:

~~~mermaid
flowchart TB
    Main["main() / composition root"] --> WF["WindowsUIFactory"]
    Main --> MF["MacUIFactory"]
    Main --> Client["SettingsScreen (hai lần tạo instance)"]
    Client --> AF["UIFactory"]
    Client --> B["Button"]
    Client --> C["Checkbox"]
    WF -. "implements" .-> AF
    MF -. "implements" .-> AF
    WF --> WB["WindowsButton"]
    WF --> WC["WindowsCheckbox"]
    MF --> MB["MacButton"]
    MF --> MC["MacCheckbox"]
    WB -. "implements" .-> B
    MB -. "implements" .-> B
    WC -. "implements" .-> C
    MC -. "implements" .-> C
~~~

Điểm cần phân biệt: lớp `SettingsScreen` **nhận factory**; `main()` **biết concrete factory**; mỗi concrete factory **biết concrete product**. Mỗi tầng chỉ giữ thông tin cần thiết cho trách nhiệm của mình.

## 3. Thiết kế interface trước khi ghép trong main

### 3.1. Interface sản phẩm

Một nút và một checkbox có chức năng khác nhau nên cần **hai hợp đồng riêng**:

~~~java
interface Button {
    void setLabel(String label);
    void render();
    void click();
}

interface Checkbox {
    void setLabel(String label);
    void setChecked(boolean checked);
    boolean isChecked();
    void render();
}
~~~

Trong ví dụ:

- `Button.setLabel()` lưu nội dung sẽ hiển thị trên nút.
- `Button.render()` mô phỏng việc vẽ nút.
- `Button.click()` mô phỏng thao tác kích hoạt nút.
- `Checkbox.setLabel()` đặt nội dung bên cạnh ô đánh dấu.
- `Checkbox.setChecked()` và `isChecked()` thao tác với trạng thái lựa chọn.
- `Checkbox.render()` hiển thị trạng thái theo phong cách tương ứng.

Các phương thức `render()` và `click()` ở đây chủ yếu phục vụ **bản demo console**. Trong Swing, JavaFX hoặc UI toolkit thật, framework thường quản lý việc hiển thị và sự kiện. Abstract Factory **không bắt buộc** tên phương thức này; các hợp đồng cần phản ánh đúng cách client sử dụng GUI thực tế.

### 3.2. Interface factory

~~~java
interface UIFactory {
    Button createButton();
    Checkbox createCheckbox();
}
~~~

Hai phương thức này tạo **hai loại sản phẩm**. Factory **không quyết định khi nào người dùng bấm nút** hoặc checkbox phải được bật hay tắt. Factory chỉ quyết định **lớp triển khai được tạo ra** cho mỗi loại sản phẩm.

Vì chữ ký trả về là `Button` và `Checkbox`, `SettingsScreen` không cần biết các instance thực tế được tạo từ `WindowsButton` hay `MacCheckbox`.

### 3.3. Vì sao không truyền trực tiếp hai lớp cụ thể vào main?

Nếu `main()` truyền riêng từng sản phẩm, client vẫn có thể dùng interface sản phẩm:

~~~java
Button button = new WindowsButton();
Checkbox checkbox = new WindowsCheckbox();
~~~

Cách này hợp lệ cho ứng dụng nhỏ. Tuy nhiên, khi có nhiều client và nhiều họ, `main()` có thể phải trực tiếp biết cách tạo **mọi sản phẩm**. Abstract Factory giúp gom quy tắc này: `main()` chỉ chọn `WindowsUIFactory` hoặc `MacUIFactory`; các factory cụ thể tự tạo sản phẩm phù hợp.

## 4. Mã Java hoàn chỉnh trong một tệp

Ví dụ sau **tự chứa**, không yêu cầu thư viện bên ngoài. Lưu thành tệp **`AbstractFactoryMainDemo.java`**. Chỉ có một lớp `public` trùng tên tệp; các interface và lớp hỗ trợ được khai báo ở cấp package trong cùng tệp để người học dễ chạy.

~~~java
// ===== Abstract Product 1: Button =====

interface Button {
    void setLabel(String label);
    void render();
    void click();
}

// ===== Abstract Product 2: Checkbox =====

interface Checkbox {
    void setLabel(String label);
    void setChecked(boolean checked);
    boolean isChecked();
    void render();
}

// ===== Abstract Factory =====

interface UIFactory {
    Button createButton();
    Checkbox createCheckbox();
}

// ===== Concrete Products: Windows =====

class WindowsButton implements Button {
    private String label = "";

    @Override
    public void setLabel(String label) {
        this.label = label;
    }

    @Override
    public void render() {
        System.out.println("[Windows] Button: " + label);
    }

    @Override
    public void click() {
        System.out.println("[Windows] Click: " + label);
    }
}

class WindowsCheckbox implements Checkbox {
    private String label = "";
    private boolean checked;

    @Override
    public void setLabel(String label) {
        this.label = label;
    }

    @Override
    public void setChecked(boolean checked) {
        this.checked = checked;
    }

    @Override
    public boolean isChecked() {
        return checked;
    }

    @Override
    public void render() {
        String mark = checked ? "[x]" : "[ ]";
        System.out.println(
            "[Windows] Checkbox: " + mark + " " + label
        );
    }
}

// ===== Concrete Products: macOS =====

class MacButton implements Button {
    private String label = "";

    @Override
    public void setLabel(String label) {
        this.label = label;
    }

    @Override
    public void render() {
        System.out.println("(macOS) Button: " + label);
    }

    @Override
    public void click() {
        System.out.println("(macOS) Click: " + label);
    }
}

class MacCheckbox implements Checkbox {
    private String label = "";
    private boolean checked;

    @Override
    public void setLabel(String label) {
        this.label = label;
    }

    @Override
    public void setChecked(boolean checked) {
        this.checked = checked;
    }

    @Override
    public boolean isChecked() {
        return checked;
    }

    @Override
    public void render() {
        String mark = checked ? "ON" : "OFF";
        System.out.println(
            "(macOS) Checkbox: " + mark + " - " + label
        );
    }
}

// ===== Concrete Factory: Windows =====

class WindowsUIFactory implements UIFactory {
    @Override
    public Button createButton() {
        return new WindowsButton();
    }

    @Override
    public Checkbox createCheckbox() {
        return new WindowsCheckbox();
    }
}

// ===== Concrete Factory: macOS =====

class MacUIFactory implements UIFactory {
    @Override
    public Button createButton() {
        return new MacButton();
    }

    @Override
    public Checkbox createCheckbox() {
        return new MacCheckbox();
    }
}

// ===== Client: chỉ phụ thuộc vào các interface =====

class SettingsScreen {
    private final Button saveButton;
    private final Checkbox notificationCheckbox;

    SettingsScreen(UIFactory factory) {
        // Cả hai sản phẩm đến từ cùng một factory.
        saveButton = factory.createButton();
        notificationCheckbox = factory.createCheckbox();
    }

    void show() {
        saveButton.setLabel("Lưu thay đổi");
        notificationCheckbox.setLabel("Nhận thông báo");
        notificationCheckbox.setChecked(true);

        saveButton.render();
        notificationCheckbox.render();

        System.out.println(
            "Trạng thái nhận thông báo: "
                + notificationCheckbox.isChecked()
        );

        // Mô phỏng hành động của người dùng trong console.
        saveButton.click();
    }
}

// ===== Composition root: chạy lần lượt hai họ =====

public class AbstractFactoryMainDemo {
    private static void runFamily(
            String familyName,
            UIFactory factory) {

        System.out.println("=== " + familyName + " ===");

        // Cùng một lớp client, chỉ khác factory được cấp.
        SettingsScreen screen = new SettingsScreen(factory);
        screen.show();
    }

    public static void main(String[] args) {
        // Lần 1: chọn toàn bộ họ Windows.
        UIFactory windowsFactory = new WindowsUIFactory();
        runFamily("Windows", windowsFactory);

        System.out.println();

        // Lần 2: chọn toàn bộ họ macOS.
        UIFactory macFactory = new MacUIFactory();
        runFamily("macOS", macFactory);
    }
}
~~~

### 4.1. Biên dịch và chạy

Mở terminal trong thư mục đã lưu tệp rồi thực hiện:

~~~bash
javac -encoding UTF-8 AbstractFactoryMainDemo.java
java AbstractFactoryMainDemo
~~~

Ví dụ chỉ sử dụng cú pháp Java cơ bản, có thể chạy với **JDK 8 trở lên**. Không cần phụ thuộc Swing, JavaFX, Maven, Gradle hay SDK hệ điều hành.

Kết quả mong đợi trong **một lần chạy**:

~~~text
=== Windows ===
[Windows] Button: Lưu thay đổi
[Windows] Checkbox: [x] Nhận thông báo
Trạng thái nhận thông báo: true
[Windows] Click: Lưu thay đổi

=== macOS ===
(macOS) Button: Lưu thay đổi
(macOS) Checkbox: ON - Nhận thông báo
Trạng thái nhận thông báo: true
(macOS) Click: Lưu thay đổi
~~~

Chương trình chạy **Windows trước, macOS sau**, theo đúng thứ tự lệnh trong `main()`. Đây là hai lần dựng **hai instance khác nhau của `SettingsScreen`**; chúng không phải một màn hình tự đổi nền tảng trong khi đang hiển thị.

### 4.2. Quan sát kết quả để nhận diện họ sản phẩm

Ở phần Windows, cả nút và checkbox đều có tiền tố `[Windows]`. Ở phần macOS, cả hai đều có tiền tố `(macOS)`. Việc hiển thị khác nhau do **Concrete Product** quyết định.

Cùng lúc, hai phần vẫn có nội dung và hành vi chung:

- Nút mang nhãn **Lưu thay đổi**.
- Checkbox mang nhãn **Nhận thông báo**.
- Trạng thái checkbox sau khi gọi `setChecked(true)` đều là `true`.
- Nút có thể được kích hoạt qua `click()`.

Đây là biểu hiện của **đa hình**: client gọi cùng một phương thức của interface; cách thực thi phụ thuộc vào instance thực tế được factory tạo ra.

## 5. Phân tích main theo từng câu lệnh

Đoạn quan trọng nhất trong bài học:

~~~java
public static void main(String[] args) {
    UIFactory windowsFactory = new WindowsUIFactory();
    runFamily("Windows", windowsFactory);

    System.out.println();

    UIFactory macFactory = new MacUIFactory();
    runFamily("macOS", macFactory);
}
~~~

### 5.1. Tạo factory Windows

~~~java
UIFactory windowsFactory = new WindowsUIFactory();
~~~

**Kiểu khai báo** của biến là `UIFactory`, còn **kiểu instance thật** là `WindowsUIFactory`. Sau khi có biến này, những nơi dùng `windowsFactory` chỉ cần biết hai phương thức `createButton()` và `createCheckbox()`.

Việc xuất hiện `new WindowsUIFactory()` ở `main()` là chủ đích: composition root là ranh giới được phép biết các lớp triển khai để **lắp ghép hệ thống**. Abstract Factory không đòi hỏi loại bỏ mọi toán tử `new`.

### 5.2. Cấp factory cho client

~~~java
runFamily("Windows", windowsFactory);
~~~

`runFamily()` nhận `UIFactory`. Nó chỉ khởi tạo `SettingsScreen(factory)` và gọi `show()`. Hàm hỗ trợ này không cần biết factory được truyền vào thuộc Windows hay macOS.

Mã trong `SettingsScreen`:

~~~java
SettingsScreen(UIFactory factory) {
    saveButton = factory.createButton();
    notificationCheckbox = factory.createCheckbox();
}
~~~

định nghĩa **cách dùng factory qua hợp đồng**. Khi nhận `WindowsUIFactory`, Java thực thi các phương thức tạo sản phẩm của factory Windows và trả về `WindowsButton`, `WindowsCheckbox`.

### 5.3. Tạo factory macOS rồi dùng lại chính client

~~~java
UIFactory macFactory = new MacUIFactory();
runFamily("macOS", macFactory);
~~~

Từ đây, `SettingsScreen` hoàn toàn không thay đổi. Hai lời gọi `factory.createButton()` và `factory.createCheckbox()` giờ được đáp ứng bởi `MacUIFactory`.

Nếu muốn thay đổi thứ tự chạy, chỉ cần đổi thứ tự các lời gọi `runFamily()` ở `main()`. Không cần sửa bất kỳ concrete product nào.

### 5.4. Ý nghĩa của việc có hai lần dựng SettingsScreen

Hai biến thể được chạy nối tiếp để **minh họa** thiết kế. Khi tạo:

~~~java
new SettingsScreen(windowsFactory);
new SettingsScreen(macFactory);
~~~

mỗi lần gọi tạo một màn hình mới cùng các sản phẩm tương ứng. Các biến `label` và `checked` nằm trong từng instance, nên việc thiết lập trạng thái trên màn hình Windows **không khiến checkbox macOS thừa hưởng trạng thái đó từ màn hình trước**. Trong ví dụ, cả hai đều hiển thị `true` vì phương thức `show()` đặt `setChecked(true)` cho mỗi màn hình.

Đây cũng là điểm khác biệt giữa **thay họ bằng factory khi tạo đối tượng** và **thay đổi trạng thái trực tiếp trên đối tượng đã tồn tại**. Abstract Factory không tự động biến `WindowsCheckbox` đang có thành `MacCheckbox`.

## 6. Phân biệt composition root với concrete factory

Cả hai đều liên quan khởi tạo nên dễ bị gộp thành một trách nhiệm.

| Câu hỏi | Nơi chịu trách nhiệm |
| --- | --- |
| Chương trình cần chạy họ Windows hay macOS? | `main()` / composition root |
| `WindowsUIFactory` phải tạo loại Button cụ thể nào? | `WindowsUIFactory.createButton()` |
| Checkbox có trạng thái bật/tắt thế nào? | `SettingsScreen` đặt trạng thái, `Checkbox` lưu và trả về |
| Nút được in theo phong cách nào? | `WindowsButton` hoặc `MacButton` |
| Khi nào một màn hình mới được tạo? | Hàm lắp ghép hoặc tầng quản lý vòng đời |
| Một màn hình sử dụng Button và Checkbox ra sao? | `SettingsScreen` qua interface |

Có thể tách hàm chọn factory khỏi `main()` khi logic cấu hình phức tạp:

~~~java
static UIFactory selectFactory(String platform) {
    if ("windows".equalsIgnoreCase(platform)) {
        return new WindowsUIFactory();
    }
    if ("macos".equalsIgnoreCase(platform)) {
        return new MacUIFactory();
    }
    throw new IllegalArgumentException(
        "Nền tảng không được hỗ trợ: " + platform
    );
}
~~~

Đây là **đoạn mã bổ sung để thảo luận**, có thể đặt trong lớp main ở một phiên bản mở rộng. Chương trình tự chạy ở phần 4 không cần selector vì nó **cố ý chạy cả hai họ theo thứ tự cố định**.

Nếu triển khai thực tế chỉ chọn một họ từ cấu hình, hãy phân giải cấu hình rồi tạo factory **một lần tại ranh giới lắp ghép**, sau đó cấp factory ấy cho các client liên quan. Không để từng màn hình tự đọc cấu hình và tự tạo factory.

## 7. Vì sao phải dùng một factory cho cả Button và Checkbox?

Giả sử client tự tạo từng sản phẩm:

~~~java
// Sai quy tắc phối hợp nếu muốn giao diện Windows nhất quán.
Button button = new WindowsButton();
Checkbox checkbox = new MacCheckbox();
~~~

Mã trên **có thể biên dịch**, vì cả hai đều triển khai các interface tương ứng. Tuy nhiên, kết quả tạo ra một cặp sản phẩm không cùng họ.

Với Abstract Factory:

~~~java
UIFactory factory = new WindowsUIFactory();

Button button = factory.createButton();
Checkbox checkbox = factory.createCheckbox();
~~~

cả hai sản phẩm được tạo bởi **cùng một concrete factory**. Thiết kế này biểu đạt quy tắc: một màn hình thuộc họ Windows sẽ sử dụng cả Button và Checkbox Windows.

Cần hiểu giới hạn: **interface không bảo đảm tự động tính nhất quán theo họ**. Người triển khai vẫn có thể viết sai:

~~~java
class WrongWindowsFactory implements UIFactory {
    @Override
    public Button createButton() {
        return new WindowsButton();
    }

    @Override
    public Checkbox createCheckbox() {
        return new MacCheckbox(); // Sai về họ nhưng đúng kiểu Checkbox.
    }
}
~~~

Vì thế, ngoài việc tổ chức code đúng, dự án thật nên kiểm tra từng concrete factory tạo các sản phẩm phù hợp. Với GUI, có thể kiểm tra hành vi hiển thị, theme hoặc phối hợp các widget; với những họ sản phẩm khác như encoder/decoder, cần kiểm tra **khả năng tương thích thực tế**.

## 8. Những bước kiểm tra khi ghép chương trình trong main

Không nên chỉ thấy chương trình in ra một vài dòng rồi kết luận toàn bộ thiết kế đã đúng. Có thể kiểm tra các điều kiện sau:

| Nội dung kiểm tra | Kết quả mong đợi |
| --- | --- |
| `main()` tạo `WindowsUIFactory` rồi `MacUIFactory` | Hai họ được chạy đúng thứ tự |
| `SettingsScreen` chỉ nhận `UIFactory` | Client không phụ thuộc tên concrete factory |
| `WindowsUIFactory.createButton()` | Tạo `WindowsButton` |
| `WindowsUIFactory.createCheckbox()` | Tạo `WindowsCheckbox` |
| `MacUIFactory.createButton()` | Tạo `MacButton` |
| `MacUIFactory.createCheckbox()` | Tạo `MacCheckbox` |
| `setChecked(true)` rồi `isChecked()` | Cả hai họ đều trả `true` |
| Kết quả Windows | Button và Checkbox cùng phong cách Windows |
| Kết quả macOS | Button và Checkbox cùng phong cách macOS |
| `show()` của client | Không cần điều kiện kiểm tra platform/theme |

### 8.1. Kiểm tra rằng client thật sự không biết class cụ thể

Đọc lớp `SettingsScreen` trong ví dụ:

~~~java
class SettingsScreen {
    private final Button saveButton;
    private final Checkbox notificationCheckbox;

    SettingsScreen(UIFactory factory) {
        saveButton = factory.createButton();
        notificationCheckbox = factory.createCheckbox();
    }
    // ...
}
~~~

Client chỉ giữ ba tên trừu tượng: `UIFactory`, `Button` và `Checkbox`. Không có `Windows...` hay `Mac...` trong phần này. Đây là **bằng chứng về ranh giới phụ thuộc** chứ không chỉ là khác biệt đầu ra khi chạy.

### 8.2. Có thể thử với fake factory

Khi client nhận factory qua constructor, kiểm thử có thể cấp một factory giả:

~~~java
// Ví dụ riêng minh họa hướng kiểm thử;
// không ghép trực tiếp vào tệp demo ở phần 4.
class CountingFactory implements UIFactory {
    int buttonCreates;
    int checkboxCreates;

    @Override
    public Button createButton() {
        buttonCreates++;
        return new FakeButton();
    }

    @Override
    public Checkbox createCheckbox() {
        checkboxCreates++;
        return new FakeCheckbox();
    }
}
~~~

`FakeButton` và `FakeCheckbox` là các lớp giả cần được định nghĩa trong bộ kiểm thử, có cùng interface và không tạo giao diện thật. Sau khi tạo `SettingsScreen(fake)`, có thể kiểm tra factory đã được gọi đúng một lần cho mỗi loại sản phẩm.

Bài này chỉ tập trung vào **lắp ghép và chạy hai họ thật của ví dụ console**; kiểm thử bằng fake là khả năng mở rộng dựa trên việc client phụ thuộc vào interface.

## 9. Những lỗi thường gặp khi hoàn thiện main

### 9.1. Chọn một họ trong main nhưng client lại tạo họ khác

~~~java
// main đã chọn Windows...
UIFactory factory = new WindowsUIFactory();

// ...nhưng client vẫn tự new các lớp macOS bên trong.
~~~

Đây là dấu hiệu **chưa tách trách nhiệm triệt để**. Sau khi truyền factory, các client phải lấy những sản phẩm liên quan từ factory đã nhận.

### 9.2. Khởi tạo factory khác cho từng sản phẩm

~~~java
Button button =
        new WindowsUIFactory().createButton();

Checkbox checkbox =
        new MacUIFactory().createCheckbox();
~~~

Nếu mục tiêu là phối hợp cùng họ, cách này tạo ra cặp sai. Trong `SettingsScreen`, ta truyền một factory và gọi cả hai phương thức của factory đó.

### 9.3. Viết logic lựa chọn platform trong SettingsScreen

~~~java
class SettingsScreen {
    SettingsScreen(String platform) {
        // if ("windows") ...
        // if ("macos") ...
    }
}
~~~

Khi client tự lựa chọn implementation, thêm họ mới sẽ buộc sửa client. Hãy chuyển lựa chọn tới composition root và truyền `UIFactory` thay vì chuỗi platform.

### 9.4. Nhầm «chạy lần lượt» với «đổi theme trên một instance»

Trong ví dụ, mỗi lần `runFamily()` đều tạo **một `SettingsScreen` mới**. Nếu ứng dụng yêu cầu một màn hình đang mở đổi theme ngay lập tức, cần thiết kế thêm cơ chế tạo lại hoặc cập nhật component, bảo toàn trạng thái và xử lý tài nguyên GUI.

Việc đổi biến factory ở nơi khác **không tự thay đổi** các sản phẩm cũ đã tạo.

### 9.5. Gắn kết quả vào tên họ truyền dạng String

Hàm `runFamily("Windows", windowsFactory)` nhận nhãn để **in tiêu đề minh họa**. Chuỗi tên họ không được dùng bên trong `SettingsScreen` để tự chọn sản phẩm. Nếu các label hiển thị được sử dụng cho mục đích quan trọng hơn, nên tránh truyền label và factory không khớp, ví dụ gom cấu hình vào một kiểu dữ liệu có kiểm tra.

Trong demo này, nhãn được viết trực tiếp trong `main()` và chỉ dùng để giúp người đọc phân biệt hai lần chạy.

### 9.6. Chấp nhận mọi cấu hình không hợp lệ thành họ mặc định

Ứng dụng thực thường không chạy cả hai họ như demo. Nếu đổi sang cách đọc cấu hình, không nên dùng:

~~~java
// Có thể âm thầm chọn macOS khi nhập sai "windows".
return "windows".equals(platform)
        ? new WindowsUIFactory()
        : new MacUIFactory();
~~~

Nếu cấu hình đã được cung cấp nhưng sai, cần báo lỗi hoặc áp dụng fallback **có chủ đích** theo chính sách nghiệp vụ, không mặc nhiên coi mọi chuỗi lạ là macOS.

### 9.7. Để tất cả sản phẩm dùng chung trạng thái tĩnh

Các lớp concrete product trong ví dụ lưu `label` và `checked` ở **trường instance**. Nếu thay bằng trường `static`, trạng thái có thể bị chia sẻ giữa những màn hình hoặc lần chạy độc lập, tạo kết quả khó hiểu.

Vòng đời sản phẩm nên được quy định phù hợp: có sản phẩm phải tạo mới mỗi lần, có sản phẩm có thể dùng chung nếu an toàn. Abstract Factory không bắt buộc một vòng đời duy nhất.

## 10. Mở rộng ví dụ sau khi đã chạy cả hai họ

### 10.1. Thêm một họ sản phẩm mới

Giả sử ứng dụng cần thêm Linux. Ta có thể khai báo:

~~~java
class LinuxButton implements Button {
    // Cài đặt setLabel(), render(), click().
}

class LinuxCheckbox implements Checkbox {
    // Cài đặt setLabel(), setChecked(), isChecked(), render().
}

class LinuxUIFactory implements UIFactory {
    @Override
    public Button createButton() {
        return new LinuxButton();
    }

    @Override
    public Checkbox createCheckbox() {
        return new LinuxCheckbox();
    }
}
~~~

Đây là **phác thảo**, không phải các class hoàn chỉnh để chép vào chương trình. Khi triển khai đầy đủ, `main()` chỉ cần thêm:

~~~java
UIFactory linuxFactory = new LinuxUIFactory();
runFamily("Linux", linuxFactory);
~~~

`SettingsScreen` vẫn có thể giữ nguyên nếu hợp đồng không đổi. Đây là ưu điểm nổi bật của Abstract Factory: **thêm họ mới thường chủ yếu cần thêm concrete product và concrete factory, không sửa client**.

### 10.2. Thêm một loại sản phẩm mới

Nếu muốn có thêm `Dialog`, phải:

1. Khai báo product interface `Dialog`.
2. Thêm `Dialog createDialog()` vào `UIFactory`.
3. Cài đặt `createDialog()` trong **WindowsUIFactory**, **MacUIFactory** và các concrete factory khác.
4. Thêm concrete product như `WindowsDialog` và `MacDialog`.
5. Chỉ thay đổi client nào thực sự cần dùng Dialog.

Việc thêm **loại sản phẩm mới** tốn công hơn vì mọi concrete factory phải tuân theo hợp đồng factory được mở rộng. Đây là đánh đổi tự nhiên của Abstract Factory so với việc thêm họ mới.

### 10.3. Chọn một họ cho môi trường production

Trong ứng dụng production, `main()` có thể đọc tham số và chọn đúng một factory thay vì chạy tuần tự cả hai:

~~~java
// Minh họa biến thể main khác, không phải code thay thế trực tiếp
// vào chương trình đang chạy hai họ.
static UIFactory selectFactory(String platform) {
    if ("windows".equalsIgnoreCase(platform)) {
        return new WindowsUIFactory();
    }
    if ("macos".equalsIgnoreCase(platform)) {
        return new MacUIFactory();
    }
    throw new IllegalArgumentException("Platform không được hỗ trợ");
}
~~~

Sau đó dùng một `SettingsScreen(factory)`. Nhưng đây là **mục tiêu ứng dụng khác**: chương trình thử nghiệm của bài này **cố ý gọi cả hai factory nối tiếp** để chứng minh client độc lập với biến thể.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `main()` được phép gọi `new WindowsUIFactory()`, còn `SettingsScreen` không nên gọi `new WindowsButton()`?

**Trả lời:** `main()` là nơi lắp ghép và lựa chọn các dependency cụ thể. `SettingsScreen` chỉ cần sử dụng sản phẩm qua hợp đồng chung; nếu tự tạo WindowsButton, client lại bị gắn với một biến thể.

**Câu 2.** Khi `runFamily("macOS", new MacUIFactory())` chạy, có cần sửa `SettingsScreen` để hiển thị macOS không?

**Trả lời:** Không. `SettingsScreen` nhận `UIFactory`, gọi cùng hai phương thức tạo sản phẩm và dùng các interface `Button`/`Checkbox`. Concrete factory quyết định lớp được tạo.

**Câu 3.** Vì sao hai lần chạy đều có `Trạng thái nhận thông báo: true` nhưng hình thức checkbox khác nhau?

**Trả lời:** Màn hình gọi cùng `setChecked(true)` cho từng checkbox. Cả hai concrete product tuân thủ cùng hợp đồng trạng thái, còn `render()` hiển thị theo từng họ.

**Câu 4.** Khi thay `windowsFactory` bằng `macFactory`, có cần thay một đối tượng `SettingsScreen` đã tạo trước đó không?

**Trả lời:** Muốn thấy sản phẩm mới, cần tạo màn hình hoặc các widget mới từ factory được chọn. Đổi factory không làm instance Windows hiện có biến thành macOS.

**Câu 5.** Điều gì xảy ra nếu `WindowsUIFactory.createCheckbox()` trả về `new MacCheckbox()`?

**Trả lời:** Chương trình có thể vẫn biên dịch vì `MacCheckbox` là `Checkbox`, nhưng phá quy tắc cùng họ. Cần sửa factory và kiểm tra hành vi hoặc kiểu sản phẩm theo yêu cầu tương thích.

**Câu 6.** Thêm một họ Linux và thêm một loại Dialog, hướng nào thường dễ hơn?

**Trả lời:** Thêm một **họ** thường dễ vì các interface giữ nguyên. Thêm **loại sản phẩm** đòi hỏi cập nhật interface factory và mọi concrete factory hiện có.

**Câu 7.** Chạy Windows rồi macOS trong một lần `main()` có đồng nghĩa sản phẩm macOS kế thừa trạng thái instance Windows không?

**Trả lời:** Không. Hai `SettingsScreen` mới sử dụng những sản phẩm mới do hai factory khác nhau tạo. Trạng thái checkbox giống nhau do client tự đặt `true` ở mỗi lần chạy.

## 12. Tổng kết

Khi hoàn thiện một chương trình **Abstract Factory** trong Java, phần `main()` có vai trò quan trọng: **chọn và cấp concrete factory cho client**. Một ví dụ rõ ràng là chạy lần lượt **WindowsUIFactory** rồi **MacUIFactory** với cùng `SettingsScreen`. Kết quả cho thấy mỗi họ cung cấp cả Button và Checkbox theo biến thể tương ứng, còn mã client chỉ sử dụng `UIFactory`, `Button` và `Checkbox`.

Điểm cần nhớ là **composition root quyết định họ, concrete factory quyết định lớp sản phẩm trong họ, client quyết định cách dùng sản phẩm**. Phân chia này giúp ứng dụng thay cả bộ đối tượng liên quan mà ít phải sửa logic sử dụng, đồng thời tạo nền tảng cho việc cấu hình biến thể, kiểm thử và mở rộng các họ sản phẩm sau này.
