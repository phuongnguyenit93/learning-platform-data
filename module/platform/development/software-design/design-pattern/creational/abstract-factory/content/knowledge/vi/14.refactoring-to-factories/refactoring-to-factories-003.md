# Trích xuất product interface từ các lớp cụ thể đang được sử dụng

## 1. Bối cảnh và mục tiêu tái cấu trúc

Trong một ứng dụng Java đang phát triển, mã giao diện đôi khi tạo và sử dụng trực tiếp các lớp cụ thể như `LightButton` và `LightCheckbox`. Cách làm này có thể đủ đơn giản ở giai đoạn đầu. Vấn đề xuất hiện khi ứng dụng cần hỗ trợ thêm giao diện **Dark**: mỗi màn hình lại phải biết tên các lớp mới và tự lựa chọn chúng.

Để tiến tới **Abstract Factory** — mẫu thiết kế khởi tạo giúp tạo **các họ sản phẩm liên quan** qua một hợp đồng chung — cần xác định trước các **product interface** (*Abstract Product*). Chúng mô tả **những hành vi client thật sự cần**, không gắn với cách triển khai của một biến thể.

Bài học này tập trung vào một bước **tái cấu trúc** cụ thể:

> Từ những lớp sản phẩm đã được ứng dụng sử dụng trực tiếp, trích xuất các interface sản phẩm phù hợp rồi chuyển client sang phụ thuộc vào các interface đó.

Mục tiêu là giữ nguyên hành vi đang hoạt động trong khi mở ra khả năng thay thế lớp cụ thể bằng các biến thể khác. Việc xây dựng một `GUIFactory` có thể diễn ra **sau** khi ranh giới product interface đã rõ ràng.

Sau bài này, người học có thể:

- Nhận diện chỗ client phụ thuộc vào lớp sản phẩm cụ thể.
- Chọn phương thức đưa vào interface từ nhu cầu sử dụng thực tế.
- Cho lớp cũ `implements` interface mới mà vẫn giữ hành vi.
- Chuyển trường, tham số, kiểu trả về của client sang interface một cách có kiểm soát.
- Đưa việc khởi tạo lớp cụ thể ra khỏi client để chuẩn bị cho Abstract Factory.
- Nhận biết nguy cơ khi trích interface quá lớn, đổi hợp đồng hoặc ép kiểu ngược về lớp cụ thể.

## 2. Hiện trạng: client phụ thuộc trực tiếp vào product cụ thể

Giả sử có một màn hình cài đặt, đang chạy với hai thành phần giao diện Light:

- `LightButton`: nút **Lưu**.
- `LightCheckbox`: lựa chọn **Bật thông báo**.

Mã hiện tại có thể được tổ chức như sau:

~~~java
// Minh họa hiện trạng: các class đã có trong dự án.
class LightButton {
    private String text = "";

    public void setText(String text) {
        this.text = text;
    }

    public void render() {
        System.out.println("[Light] Button: " + text);
    }

    // Phương thức dành riêng cho hiệu ứng Light.
    public void setLightShadow(int depth) {
        // Cấu hình hiệu ứng hiển thị.
    }
}

class LightCheckbox {
    private boolean checked;

    public void setChecked(boolean checked) {
        this.checked = checked;
    }

    public boolean isChecked() {
        return checked;
    }

    public void render() {
        System.out.println("[Light] Checkbox: " + checked);
    }
}

class SettingsScreen {
    private final LightButton saveButton = new LightButton();
    private final LightCheckbox notifications = new LightCheckbox();

    void show() {
        saveButton.setText("Lưu");
        notifications.setChecked(true);

        saveButton.render();
        notifications.render();
        System.out.println(
            "Thông báo được bật: " + notifications.isChecked()
        );
    }
}
~~~

Ở đây, `SettingsScreen` gắn chặt với hai lớp cụ thể theo **hai cách**:

1. Các trường có kiểu `LightButton` và `LightCheckbox`.
2. Chính màn hình gọi `new LightButton()` và `new LightCheckbox()` để tạo đối tượng.

Nếu muốn đổi sang giao diện Dark, màn hình phải sửa cả kiểu và cách tạo sản phẩm, hoặc chứa điều kiện chọn lớp. Khi nhiều màn hình làm giống vậy, quy tắc chọn biến thể bị lặp lại.

Sơ đồ phụ thuộc ban đầu:

~~~mermaid
flowchart LR
    Screen["SettingsScreen"] --> LB["LightButton"]
    Screen --> LC["LightCheckbox"]
~~~

Bản chất vấn đề **không phải** toán tử `new` luôn xấu. Vấn đề là **một client vốn chỉ cần thao tác chung của Button và Checkbox lại bị buộc phải biết chính xác lớp Light**. Đây là điểm nên trích xuất interface.

## 3. Bước 1: khảo sát hành vi client đang thực sự dùng

Trước khi tạo interface, hãy lập danh sách những thao tác mà client cần. Có thể tìm các chỗ sử dụng lớp cụ thể trong trường dữ liệu, tham số, kiểu trả về, chỗ gọi constructor, chỗ dùng `instanceof` hoặc ép kiểu và các lời gọi phương thức.

Với ví dụ, `SettingsScreen` đang sử dụng:

| Lớp cụ thể | Thao tác client cần | Đưa vào product interface? | Lý do |
| --- | --- | --- | --- |
| `LightButton` | `setText(String)` | **Có** | Mọi biến thể Button đều cần đặt nhãn |
| `LightButton` | `render()` | **Có** trong ví dụ | Client yêu cầu hiển thị nút mà không quan tâm cách vẽ |
| `LightButton` | `setLightShadow(int)` | **Không** | Chỉ mang ý nghĩa với cách hiển thị Light |
| `LightCheckbox` | `setChecked(boolean)` | **Có** | Mọi biến thể Checkbox đều biểu diễn trạng thái chọn |
| `LightCheckbox` | `isChecked()` | **Có** | Client cần đọc lựa chọn hiện tại |
| `LightCheckbox` | `render()` | **Có** trong ví dụ | Hành vi hiển thị chung của loại Checkbox |
| Cả hai | Constructor, trường `text`/`checked` | **Không** | Chi tiết tạo và lưu trạng thái thuộc lớp triển khai |

**Quy tắc trích xuất:** bắt đầu từ **nhu cầu của client**, không sao chép toàn bộ phương thức public của lớp cụ thể. Nếu client không cần thao tác `setLightShadow()`, hoặc thao tác đó không có ý nghĩa với Dark Button, không nên đưa nó vào hợp đồng chung.

### 3.1. Xác định «loại sản phẩm» trước khi trích interface

Hai loại sản phẩm trong bài này có trách nhiệm khác nhau:

- **Button** biểu diễn một hành động, có nội dung để hiển thị.
- **Checkbox** biểu diễn một lựa chọn nhị phân, có trạng thái để đặt và đọc.

Vì thế cần hai interface độc lập: `Button` và `Checkbox`. Không nên vì cả hai đều có `render()` mà ép chúng thành một interface duy nhất chỉ gồm `render()`: client sẽ mất khả năng gọi `setText()` hoặc `isChecked()` theo kiểu an toàn.

Tương tự, không nên tạo một interface khổng lồ có đủ các phương thức của cả hai loại. Một `Button` thông thường không cần triển khai `isChecked()`, và interface như vậy dễ vi phạm **Interface Segregation Principle**.

### 3.2. Xác định hợp đồng, không chỉ chữ ký

Một phương thức trong interface phải có **ý nghĩa nhất quán** giữa các lớp triển khai.

| Phương thức | Ngữ nghĩa cần thống nhất |
| --- | --- |
| `Button.setText(String)` | Cập nhật nhãn sẽ được sử dụng khi hiển thị nút |
| `Button.render()` | Hiển thị nút theo dữ liệu hiện tại của nó |
| `Checkbox.setChecked(boolean)` | Đặt trạng thái lựa chọn thành giá trị truyền vào |
| `Checkbox.isChecked()` | Trả về trạng thái hiện tại; bản thân việc đọc không đổi trạng thái |
| `Checkbox.render()` | Hiển thị checkbox theo trạng thái hiện tại |

Ví dụ, nếu `setChecked(true)` đã thực thi thành công và không có thao tác khác xen vào, `isChecked()` cần trả về `true`. Nếu biến thể Dark trả về ngược giá trị chỉ để phục vụ cách vẽ, nó đã vi phạm hợp đồng logic mà client dựa vào.

Trong hệ thống thật, còn cần xác định chính sách xử lý `null`, ngoại lệ, luồng UI và sự kiện. **Tái cấu trúc nên giữ nguyên những quy ước đang được client trông đợi**, hoặc chỉ thay đổi chúng trong một công việc riêng có kiểm thử phù hợp.

## 4. Bước 2: trích xuất Abstract Product từ các lớp cũ

Sau khi đã biết client cần gì, khai báo hai interface:

~~~java
// Product interface cho loại sản phẩm Button.
interface Button {
    void setText(String text);
    void render();
}

// Product interface cho loại sản phẩm Checkbox.
interface Checkbox {
    void setChecked(boolean checked);
    boolean isChecked();
    void render();
}
~~~

Chỉ những khả năng chung, hữu ích với client mới có mặt trong hợp đồng. Các chi tiết như màu Light, bóng đổ hoặc thư viện vẽ cụ thể tiếp tục nằm trong lớp triển khai.

Có thể hình dung ý nghĩa của tên gọi:

- **Abstract Product**: `Button`, `Checkbox`.
- **Concrete Product**: `LightButton`, `LightCheckbox`; về sau có thể thêm `DarkButton` và `DarkCheckbox`.

**Java interface không tạo ra đối tượng trực tiếp.** Khi một biến có kiểu `Button`, đối tượng thực tế vẫn là instance của một lớp `implements Button`. Interface chỉ quy định những thao tác client được phép dựa vào.

### 4.1. Cho các lớp đang tồn tại implements interface mới

Bước thay đổi đầu tiên đối với lớp cũ nên thật nhỏ:

~~~java
class LightButton implements Button {
    // Giữ nguyên trạng thái và cài đặt đang có.

    @Override
    public void setText(String text) {
        // Giữ nguyên xử lý cũ.
    }

    @Override
    public void render() {
        // Giữ nguyên cách hiển thị Light.
    }

    // Phương thức riêng vẫn được phép tồn tại.
    public void setLightShadow(int depth) {
        // Chỉ dành cho LightButton.
    }
}
~~~

Tương tự:

~~~java
class LightCheckbox implements Checkbox {
    private boolean checked;

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
        System.out.println("[Light] Checkbox: " + checked);
    }
}
~~~

Hai đoạn trên minh họa **bước chỉnh sửa tại chỗ** của lớp cũ; chúng không phải toàn bộ chương trình để chạy riêng. Ví dụ tự chạy ở phần 7 sẽ chứa đầy đủ các lớp.

Nếu chữ ký ban đầu đã trùng với interface, thường chỉ cần thêm `implements Button` hoặc `implements Checkbox` và `@Override`. Phần triển khai phương thức không cần thay đổi.

Nếu phương thức cũ có tên hoặc tham số khác, hãy đánh giá cách thích ứng thay vì sửa đồng loạt toàn bộ ứng dụng. Ví dụ, lớp cũ có `setCaption(String)`, còn interface thống nhất dùng `setText(String)`, có thể tạo cầu nối:

~~~java
@Override
public void setText(String text) {
    setCaption(text); // Tái sử dụng hành vi cũ.
}
~~~

**Lưu ý Java:** phương thức triển khai phương thức của interface phải có mức truy cập `public`; `@Override` giúp trình biên dịch phát hiện lỗi sai tên hoặc sai chữ ký.

## 5. Bước 3: chuyển client từ concrete type sang interface

Sau khi lớp cũ triển khai interface, có thể thay kiểu phụ thuộc trong `SettingsScreen`.

### 5.1. Thay kiểu trường và tham số

Trước:

~~~java
class SettingsScreen {
    private final LightButton saveButton;
    private final LightCheckbox notifications;

    SettingsScreen(LightButton saveButton,
                   LightCheckbox notifications) {
        this.saveButton = saveButton;
        this.notifications = notifications;
    }
}
~~~

Sau:

~~~java
class SettingsScreen {
    private final Button saveButton;
    private final Checkbox notifications;

    SettingsScreen(Button saveButton,
                   Checkbox notifications) {
        this.saveButton = saveButton;
        this.notifications = notifications;
    }
}
~~~

Điểm quan trọng là **logic client vẫn gọi cùng các thao tác** như `setText()`, `render()`, `setChecked()` và `isChecked()`. Chỉ ranh giới kiểu dữ liệu thay đổi.

Mã lắp ghép vẫn có thể truyền các đối tượng Light hiện tại:

~~~java
SettingsScreen screen = new SettingsScreen(
    new LightButton(),
    new LightCheckbox()
);
~~~

Cách này cho phép thực hiện một bước tái cấu trúc **có thể kiểm tra độc lập**: client đã phụ thuộc vào interface sản phẩm, nhưng chưa cần thêm một factory mới ngay lập tức. Việc tạo concrete product vẫn diễn ra ở nơi lắp ghép.

Trong ứng dụng có nhiều lớp gọi `new`, hãy chuyển từng khu vực về nơi khởi tạo thích hợp một cách có kiểm soát. Đừng thay cùng lúc tất cả màn hình và tất cả đường dẫn tạo đối tượng nếu chưa có khả năng kiểm tra hành vi sau mỗi bước.

### 5.2. Đổi kiểu trả về ở ranh giới phù hợp

Một phương thức client chỉ cần trả sản phẩm qua hợp đồng nên khai báo:

~~~java
Button createSaveButton() {
    return new LightButton();
}
~~~

Để ý đây vẫn là một phương thức trả về **sản phẩm theo interface**, nhưng chưa chắc đã là **Abstract Factory pattern**. Abstract Factory cần một giao diện tạo **nhiều loại sản phẩm thuộc cùng họ**.

Trong thư viện Java đang có người dùng bên ngoài, việc thay đổi kiểu trả về hoặc chữ ký của **API public** có thể làm hỏng tương thích mã nguồn hoặc nhị phân. Cần đánh giá phạm vi người gọi và cân nhắc overload, adapter hoặc giai đoạn chuyển tiếp, thay vì thay đổi API công khai một cách máy móc.

### 5.3. Chuyển tập hợp sản phẩm

Một lỗi thường gặp là giả định `List<LightButton>` có thể gán trực tiếp cho `List<Button>`. Java generics **không hiệp biến** đối với `List`:

~~~java
// Không hợp lệ:
// List<Button> buttons = new ArrayList<LightButton>();
~~~

Có thể khai báo tập hợp theo kiểu interface ngay từ nơi tạo:

~~~java
java.util.List<Button> buttons = new java.util.ArrayList<>();
buttons.add(new LightButton());
~~~

Hoặc nếu API chỉ cần **đọc** các phần tử như `Button`, cân nhắc `List<? extends Button>`. Không nên dùng ép kiểu thô để «lách» lỗi vì có thể tạo ra lỗi kiểu dữ liệu ở runtime.

## 6. Bước 4: chuẩn bị thêm họ mới và trích xuất factory

Khi client chỉ sử dụng `Button` và `Checkbox`, việc thêm các sản phẩm Dark sẽ không còn đòi hỏi sửa các thao tác màn hình đang dùng.

~~~java
class DarkButton implements Button {
    // Triển khai setText/render theo cách của Dark.
}

class DarkCheckbox implements Checkbox {
    // Triển khai setChecked/isChecked/render theo cách của Dark.
}
~~~

*Đây là phác thảo vai trò; bản triển khai đầy đủ có ở phần tiếp theo.*

Bây giờ việc khởi tạo các sản phẩm có thể chuyển vào một **Abstract Factory**:

~~~java
interface GUIFactory {
    Button createButton();
    Checkbox createCheckbox();
}
~~~

Các concrete factory chọn sản phẩm tương ứng với mỗi họ:

~~~java
class LightGUIFactory implements GUIFactory {
    @Override
    public Button createButton() {
        return new LightButton();
    }

    @Override
    public Checkbox createCheckbox() {
        return new LightCheckbox();
    }
}

class DarkGUIFactory implements GUIFactory {
    @Override
    public Button createButton() {
        return new DarkButton();
    }

    @Override
    public Checkbox createCheckbox() {
        return new DarkCheckbox();
    }
}
~~~

Từ đây, thay vì nhận hai product riêng lẻ, client có thể nhận một `GUIFactory` và yêu cầu cả hai qua interface:

~~~java
class SettingsScreen {
    private final Button saveButton;
    private final Checkbox notifications;

    SettingsScreen(GUIFactory factory) {
        saveButton = factory.createButton();
        notifications = factory.createCheckbox();
    }
}
~~~

Điểm khác với bước trước: **một factory đại diện cho cả họ**. Việc tạo Button và Checkbox được phối hợp ở một nơi, giảm nguy cơ màn hình vô tình dùng `DarkButton` cùng `LightCheckbox`.

Sơ đồ phụ thuộc sau khi tái cấu trúc:

~~~mermaid
flowchart TB
    Client["SettingsScreen"] --> Factory["GUIFactory"]
    Client --> Button["Button"]
    Client --> Checkbox["Checkbox"]
    LF["LightGUIFactory"] -. "implements" .-> Factory
    DF["DarkGUIFactory"] -. "implements" .-> Factory
    LF --> LB["LightButton"]
    LF --> LC["LightCheckbox"]
    DF --> DB["DarkButton"]
    DF --> DC["DarkCheckbox"]
    LB -. "implements" .-> Button
    DB -. "implements" .-> Button
    LC -. "implements" .-> Checkbox
    DC -. "implements" .-> Checkbox
~~~

Tách rõ **hai ranh giới**:

1. `GUIFactory` (Abstract Factory): client yêu cầu **tạo loại sản phẩm nào**.
2. `Button` và `Checkbox` (Abstract Product): client được **làm gì với sản phẩm đã tạo**.

Trong quá trình refactor, trích xuất product interface trước thường giúp mỗi thay đổi nhỏ, dễ kiểm soát và dễ đối chiếu hành vi.

## 7. Ví dụ Java hoàn chỉnh sau khi tái cấu trúc

Ví dụ dưới đây là **một tệp Java độc lập**. Nó kết hợp hai product interface, hai họ sản phẩm và hai concrete factory. Các phương thức `render()` chỉ in kết quả để minh họa; chúng không thay thế cơ chế vẽ và xử lý sự kiện của UI toolkit thực tế.

Lưu nội dung sau thành `ExtractProductInterfaceDemo.java`:

~~~java
// ==== Abstract Products ====
interface Button {
    void setText(String text);
    void render();
}

interface Checkbox {
    void setChecked(boolean checked);
    boolean isChecked();
    void render();
}

// ==== Concrete Products: Light ====
class LightButton implements Button {
    private String text = "";

    @Override
    public void setText(String text) {
        this.text = text;
    }

    @Override
    public void render() {
        System.out.println("[Light] Button: " + text);
    }

    // API riêng, không có trong product interface.
    public void setLightShadow(int depth) {
        // Cấu hình hiệu ứng Light nếu cần.
    }
}

class LightCheckbox implements Checkbox {
    private boolean checked;

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
        System.out.println("[Light] Checkbox: " + checked);
    }
}

// ==== Concrete Products: Dark ====
class DarkButton implements Button {
    private String text = "";

    @Override
    public void setText(String text) {
        this.text = text;
    }

    @Override
    public void render() {
        System.out.println("[Dark] Button: " + text);
    }
}

class DarkCheckbox implements Checkbox {
    private boolean checked;

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
        System.out.println("[Dark] Checkbox: " + checked);
    }
}

// ==== Abstract Factory ====
interface GUIFactory {
    Button createButton();
    Checkbox createCheckbox();
}

// ==== Concrete Factories ====
class LightGUIFactory implements GUIFactory {
    @Override
    public Button createButton() {
        return new LightButton();
    }

    @Override
    public Checkbox createCheckbox() {
        return new LightCheckbox();
    }
}

class DarkGUIFactory implements GUIFactory {
    @Override
    public Button createButton() {
        return new DarkButton();
    }

    @Override
    public Checkbox createCheckbox() {
        return new DarkCheckbox();
    }
}

// ==== Client ====
class SettingsScreen {
    private final Button saveButton;
    private final Checkbox notifications;

    SettingsScreen(GUIFactory factory) {
        this.saveButton = factory.createButton();
        this.notifications = factory.createCheckbox();
    }

    void show() {
        saveButton.setText("Lưu");
        notifications.setChecked(true);

        saveButton.render();
        notifications.render();
        System.out.println(
            "Thông báo được bật: " + notifications.isChecked()
        );
    }
}

public class ExtractProductInterfaceDemo {
    public static void main(String[] args) {
        // Kiểm tra hợp đồng trạng thái cho cả hai họ.
        checkCheckboxContract(new LightGUIFactory());
        checkCheckboxContract(new DarkGUIFactory());

        // Nơi lắp ghép ứng dụng quyết định họ sản phẩm.
        boolean useDark = args.length > 0
                && "dark".equalsIgnoreCase(args[0]);

        GUIFactory factory = useDark
                ? new DarkGUIFactory()
                : new LightGUIFactory();

        SettingsScreen screen = new SettingsScreen(factory);
        screen.show();
    }

    private static void checkCheckboxContract(GUIFactory factory) {
        Checkbox checkbox = factory.createCheckbox();

        checkbox.setChecked(true);
        if (!checkbox.isChecked()) {
            throw new AssertionError(
                "isChecked() phải là true sau setChecked(true)"
            );
        }

        checkbox.setChecked(false);
        if (checkbox.isChecked()) {
            throw new AssertionError(
                "isChecked() phải là false sau setChecked(false)"
            );
        }
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp, với JDK có sẵn:

~~~bash
javac -encoding UTF-8 ExtractProductInterfaceDemo.java
java ExtractProductInterfaceDemo
java ExtractProductInterfaceDemo dark
~~~

Lần chạy không có tham số hiển thị:

~~~text
[Light] Button: Lưu
[Light] Checkbox: true
Thông báo được bật: true
~~~

Lần chạy với tham số `dark` hiển thị:

~~~text
[Dark] Button: Lưu
[Dark] Checkbox: true
Thông báo được bật: true
~~~

Quan sát: `SettingsScreen` **không tham chiếu bất kỳ lớp cụ thể nào**. Kết quả có tiền tố Light hoặc Dark do phương thức `render()` của concrete product quyết định. Tính nhất quán về họ do concrete factory chịu trách nhiệm.

Hàm `checkCheckboxContract()` minh họa một phép kiểm tra đơn giản cho **hợp đồng trạng thái của interface**: cả hai biến thể phải phản ánh đúng giá trị đặt qua `setChecked()`. Phép kiểm tra này không bao phủ mọi hành vi của UI, nhưng cho thấy lý do cần xác định **ngữ nghĩa hợp đồng** khi trích interface.

### 7.1. Vì sao đây là tái cấu trúc, không chỉ viết lại mã?

Nhìn vào các phần sau khi đổi:

- `LightButton`, `LightCheckbox` **vẫn tồn tại**, vẫn có trách nhiệm và hành vi cơ bản như trước.
- Hai interface mới chỉ diễn tả **những phương thức client đã dùng**.
- Client không còn phụ thuộc trực tiếp vào các lớp Light.
- Quyết định chọn Light/Dark được tập trung tại nơi tạo `GUIFactory`.
- Các lớp Dark được thêm vào mà không phải sửa logic `SettingsScreen.show()`.

Phần chuyển từ mã ban đầu sang các ranh giới mới nên được thực hiện theo những **bước nhỏ, có đối chiếu hành vi**; việc thêm họ Dark là một bước mở rộng tiếp theo. Với một dự án đang hoạt động, nên giữ quá trình «trích interface» và quá trình «thêm biến thể mới» thành những thay đổi dễ đánh giá riêng biệt.

## 8. Cách giữ hành vi ổn định trong lúc refactor

Tái cấu trúc có mục đích thay đổi **cấu trúc mã** trong khi duy trì hành vi được quan sát từ bên ngoài, trừ khi có yêu cầu thay đổi chức năng rõ ràng.

Một quy trình thực tế:

1. **Ghi nhận hành vi hiện tại:** quan sát trạng thái checkbox, nhãn nút, kết quả hiển thị và các lỗi đang được xử lý.
2. **Lập bảng API client đang dùng:** phân biệt thao tác chung và thao tác đặc thù Light.
3. **Trích interface sản phẩm nhỏ nhất có ích:** ghi rõ hợp đồng, các kiểu tham số, kiểu trả về và chính sách ngoại lệ.
4. **Cho lớp cũ implements interface:** ưu tiên giữ nguyên logic cũ trong các phương thức.
5. **Chuyển các điểm phụ thuộc từng nơi:** đổi kiểu tham số/trường/kiểu trả về cần thiết sang interface và đưa constructor ra ranh giới lắp ghép.
6. **Đối chiếu hành vi ở từng điểm:** kiểm tra client cũ có vẫn cho kết quả như trước; tránh đưa thay đổi chức năng vào cùng lúc.
7. **Khi ranh giới ổn định, thêm factory và họ mới:** kiểm tra các biến thể cùng tuân thủ hợp đồng sản phẩm.

### 8.1. Những điều cần kiểm chứng

| Tình huống | Kết quả mong đợi |
| --- | --- |
| `setChecked(true)` rồi `isChecked()` | Trả về `true` |
| `setChecked(false)` rồi `isChecked()` | Trả về `false` |
| `setText("Lưu")` rồi `render()` | Nhãn hiển thị được cập nhật đúng |
| Client nhận `LightGUIFactory` | Sử dụng được cả Button lẫn Checkbox qua interface |
| Client nhận `DarkGUIFactory` | Không sửa mã client, cùng thao tác vẫn hoạt động |
| Factory của một họ tạo cả hai sản phẩm | Các sản phẩm có biến thể phù hợp nhau |
| API Light riêng `setLightShadow()` | Không bị đưa nhầm vào interface chung |

**Giới hạn của compiler:** nếu cả `LightCheckbox` và `DarkCheckbox` đều triển khai `Checkbox`, một factory Dark viết sai vẫn có thể trả về `new LightCheckbox()` mà Java không báo lỗi kiểu. **Tính tương thích theo họ** phải được bảo đảm bằng cách triển khai và kiểm thử phù hợp, chứ interface không tự mã hóa toàn bộ quy tắc đó.

### 8.2. Các khác biệt hành vi cần chú ý

Khi chuyển client sang interface, hãy xem xét đặc biệt nếu mã cũ có:

- **Ép kiểu hoặc `instanceof`:** ví dụ client dùng `((LightButton) button).setLightShadow(...)`. Đây là dấu hiệu client còn cần chi tiết của biến thể; cần điều chỉnh trách nhiệm hoặc tạo abstraction phù hợp, thay vì ép kiểu trong mọi màn hình.
- **Trạng thái và vòng đời:** mỗi lời gọi tạo product có cần instance mới, hay phải dùng chung một đối tượng? Factory tạo sai vòng đời có thể làm mất trạng thái dù interface đúng.
- **Tham số và ngoại lệ:** các concrete product phải giữ ngữ nghĩa tương thích về `null`, giá trị không hợp lệ và thông báo lỗi nếu client có phụ thuộc vào chúng.
- **API công khai:** thay kiểu trả về/chữ ký ở thư viện dùng chung có thể gây lỗi tương thích nguồn hoặc nhị phân cho các module khác.
- **Thao tác đặc thù nền tảng:** không phải mọi khác biệt đều nên được ép vào hợp đồng chung; một số tính năng nên tách sau thành interface năng lực riêng.

## 9. Sai lầm thường gặp khi trích product interface

### 9.1. Sao chép toàn bộ API của concrete class

Một lớp Light có thể chứa `setLightShadow()`, `applyLightGradient()` hoặc phương thức lấy đối tượng UI native. Đưa tất cả vào interface `Button` sẽ buộc các biến thể Dark triển khai những thao tác không có ý nghĩa.

**Cách xử lý:** xác định client cần gì theo vai trò Button. Giữ API riêng trong concrete product hoặc tách thành một interface năng lực riêng khi thật sự có nhiều client cần.

### 9.2. Đổi kiểu biến nhưng vẫn tạo concrete product ở mọi client

~~~java
// Client vẫn biết lớp cụ thể nên lợi ích tách phụ thuộc còn hạn chế.
Button button = new LightButton();
~~~

Khai báo biến kiểu `Button` là bước tốt, nhưng nếu tất cả màn hình vẫn `new LightButton()`, quyết định chọn biến thể vẫn rải rác. **Bước tiếp theo** là truyền sản phẩm/factory từ ngoài hoặc chuyển lệnh khởi tạo về một nơi lắp ghép.

### 9.3. Trích interface quá trừu tượng

~~~java
interface Widget {
    void render();
}
~~~

Nếu client cần `Checkbox.isChecked()`, chỉ có `Widget.render()` là chưa đủ. Không nên buộc client ép kiểu về concrete class để đọc trạng thái. Hãy thiết kế **interface theo loại sản phẩm** và những thao tác thực sự cần.

### 9.4. Viết lại toàn bộ triển khai khi mới thêm interface

Mục tiêu của bước này là **tách hợp đồng**. Nếu đồng thời thay đổi cách vẽ, cấu trúc trạng thái, tên sự kiện và xử lý ngoại lệ, sẽ khó xác định nguồn gốc lỗi.

**Cách xử lý:** thêm `implements`, giữ nguyên logic sẵn có, đổi từng điểm phụ thuộc, rồi mới mở rộng các biến thể.

### 9.5. Nhầm product interface với factory interface

`Button` mô tả **một Button có thể làm gì**. `GUIFactory` mô tả **cách yêu cầu tạo ra một Button hoặc Checkbox**. Đây là hai vai trò khác nhau; không nên cho `Button` tự quản lý việc tạo cả họ sản phẩm.

### 9.6. Giả định thay factory là mọi sản phẩm cũ tự đổi họ

Factory quyết định các **lần khởi tạo tiếp theo**. Nếu màn hình đang giữ instance `LightButton`, đổi biến factory ở nơi khác không biến instance đó thành `DarkButton`. Ứng dụng cần tạo lại thành phần hoặc có cơ chế cập nhật trạng thái/giao diện riêng.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao không trích `setLightShadow()` vào interface `Button`?

**Trả lời:** Vì đó là hành vi đặc thù của lớp Light, không phải hợp đồng mà mọi biến thể Button cần bảo đảm. Đưa nó vào interface chung sẽ làm các biến thể khác phải hỗ trợ thao tác không phù hợp.

**Câu 2.** Khi nào client thực sự thôi phụ thuộc trực tiếp vào `LightButton`?

**Trả lời:** Khi những trường, tham số và thao tác mà client dựa vào sử dụng `Button`, đồng thời quyết định gọi `new LightButton()` đã được chuyển ra ngoài client hoặc vào một factory phù hợp.

**Câu 3.** Nếu muốn thêm `DarkCheckbox` nhưng client vẫn dùng `Checkbox.isChecked()`, cần sửa client không?

**Trả lời:** Thường không, miễn là `DarkCheckbox` triển khai đúng hợp đồng `Checkbox` và được cung cấp qua factory hoặc cơ chế truyền dependency phù hợp.

**Câu 4.** Vì sao việc chuyển `List<LightButton>` thành `List<Button>` không thể chỉ gán trực tiếp?

**Trả lời:** Vì generic `List` trong Java là bất biến theo tham số kiểu. Cần khai báo tập hợp mới theo interface hoặc sử dụng wildcard thích hợp theo yêu cầu truy cập.

**Câu 5.** Đã có hai product interface, liệu hệ thống đã tự động áp dụng Abstract Factory chưa?

**Trả lời:** Chưa. Product interface là điều kiện thuận lợi để thiết kế factory, nhưng Abstract Factory cần thêm **hợp đồng tạo những loại sản phẩm liên quan** và các concrete factory đại diện cho từng họ.

## 11. Tổng kết

**Trích xuất product interface** là bước quan trọng khi tái cấu trúc mã Java từ phụ thuộc lớp cụ thể sang **Abstract Factory**. Quy trình đúng bắt đầu ở **những hành vi client đang dùng**, hình thành interface sản phẩm nhỏ và có ngữ nghĩa rõ ràng, cho lớp hiện có triển khai interface, rồi chuyển client sang phụ thuộc vào hợp đồng.

Sau khi `SettingsScreen` chỉ biết `Button` và `Checkbox`, ứng dụng mới dễ đưa việc tạo cả hai vào `GUIFactory` và thay các họ Light/Dark mà không viết lại thao tác của màn hình. Cần giữ nguyên hành vi trong quá trình chuyển đổi, giới hạn việc thay đổi API public và kiểm tra tính tương thích giữa các sản phẩm của mỗi họ.
