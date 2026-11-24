# Khai báo interface Button và Checkbox bằng các thao tác phù hợp miền giao diện

## 1. Mục tiêu của bước hiện thực

Khi học **Abstract Factory** trong nhóm **Creational Design Patterns** bằng Java, một bước quan trọng là xác định **các loại sản phẩm** mà ứng dụng cần tạo ra, rồi mô tả chúng qua interface. Với miền giao diện người dùng (GUI), hai loại sản phẩm thường gặp là **Button** (nút bấm) và **Checkbox** (ô đánh dấu).

Một màn hình cài đặt có thể cần:

- Một nút **Lưu** để người dùng thực hiện hành động.
- Một checkbox **Bật thông báo** để biểu diễn và thay đổi lựa chọn bật/tắt.

Ở Windows, macOS hay một bộ giao diện tùy biến, cách vẽ và xử lý tương tác có thể khác nhau. Tuy nhiên, màn hình sử dụng các thành phần này vẫn cần cùng những **khả năng nghiệp vụ của giao diện**: đặt nhãn, hiển thị, kích hoạt nút, đọc và thay đổi trạng thái checkbox.

Trong Abstract Factory, `Button` và `Checkbox` được gọi là **Abstract Product**. Chúng mô tả những gì các thành phần GUI có thể làm, không quyết định chúng có màu gì, được vẽ bằng thư viện nào hoặc thuộc hệ điều hành nào.

Bài học này tập trung vào cách chọn **phương thức phù hợp miền giao diện**, khai báo hai interface sản phẩm, xác định hợp đồng của chúng và kết nối chúng với factory trong ví dụ Java chạy được.

## 2. Bắt đầu từ hành vi, chưa bắt đầu từ lớp cụ thể

Đặt câu hỏi từ góc nhìn **mã sử dụng** (*client*): màn hình cần làm gì với sản phẩm?

| Thành phần | Nhu cầu của client | Phương thức minh họa |
| --- | --- | --- |
| Button | Hiển thị văn bản mô tả hành động | `setLabel(String label)` |
| Button | Hiển thị nút theo biến thể giao diện đang dùng | `render()` |
| Button | Kích hoạt nút trong bản demo mô phỏng | `click()` |
| Checkbox | Đặt trạng thái được chọn hoặc bỏ chọn | `setChecked(boolean checked)` |
| Checkbox | Đọc trạng thái hiện tại | `isChecked()` |
| Checkbox | Hiển thị trạng thái theo biến thể giao diện | `render()` |

Điểm mấu chốt là **Button và Checkbox có trách nhiệm khác nhau**:

- Button biểu diễn **một hành động**. Nó có nhãn, được hiển thị và có thể được kích hoạt.
- Checkbox biểu diễn **một lựa chọn nhị phân**. Nó có trạng thái được chọn/chưa chọn và cần cho phép client đọc hoặc đặt trạng thái đó.

Không nên ép mọi thành phần dùng chung cùng một interface chứa đủ cả `click()` và `setChecked()`. Nút bấm không có ý nghĩa «đang được đánh dấu» trong mô hình này; checkbox không phải một lệnh «Lưu» của màn hình.

### 2.1. Hai interface sản phẩm cơ bản

~~~java
interface Button {
    void setLabel(String label);
    void render();
    void click();
}

interface Checkbox {
    void setChecked(boolean checked);
    boolean isChecked();
    void render();
}
~~~

Các phương thức trên diễn tả **hợp đồng hành vi**:

- `setLabel(label)` cập nhật nhãn hiển thị của nút.
- `render()` hiển thị thành phần dựa trên dữ liệu hiện tại. Cách vẽ thuộc quyền quyết định của lớp cụ thể.
- `click()` mô phỏng việc kích hoạt nút trong ví dụ console. Trong GUI thật, sự kiện click thường được chuyển tới chương trình từ hệ thống sự kiện của toolkit.
- `setChecked(checked)` đặt trạng thái checkbox; lời gọi `isChecked()` sau đó phải phản ánh trạng thái đã đặt nếu không có sự kiện khác thay đổi nó.
- `isChecked()` là **truy vấn trạng thái**, không nên tự ý thay đổi trạng thái.
  
Đây là một **API minh họa có chủ đích** để làm rõ Abstract Factory. Những UI toolkit thực tế có thể dùng tên phương thức khác, cơ chế sự kiện thay cho `click()` hoặc không để client gọi trực tiếp `render()`. Điều quan trọng là các phương thức được chọn biểu diễn hành vi **chung cho mọi biến thể** của cùng loại sản phẩm.

### 2.2. Vì sao cần cả interface Button và interface Checkbox?

Giả sử chỉ dùng một interface tối giản:

~~~java
interface Widget {
    void render();
}
~~~

Client có thể hiển thị widget, nhưng không có cách **an toàn về kiểu** để hỏi checkbox đã được chọn hay để đặt nhãn nút. Nếu viết:

~~~java
Widget widget = factory.createCheckbox();
// Không có widget.isChecked() trong hợp đồng Widget.
~~~

client sẽ phải ép kiểu về một loại cụ thể hoặc dùng cơ chế riêng để truy cập hành vi. Điều đó làm suy yếu mục tiêu giúp client chỉ phụ thuộc vào trừu tượng.

Thiết kế phù hợp hơn là mỗi **loại sản phẩm** có interface thể hiện đúng trách nhiệm của nó. Có thể có thêm interface nền `Widget` khi nhiều sản phẩm thật sự có hành vi chung, nhưng không nên vì vậy mà làm mất các hợp đồng `Button` và `Checkbox`.

## 3. Vai trò của hai interface trong Abstract Factory

Abstract Factory không chỉ là tập các interface GUI. Mẫu thiết kế này còn có **interface factory** với một phương thức tạo cho từng loại sản phẩm:

~~~java
interface GUIFactory {
    Button createButton();
    Checkbox createCheckbox();
}
~~~

Ở đây có **hai tầng hợp đồng**:

1. `GUIFactory` quy định client có thể **yêu cầu tạo những loại sản phẩm nào**.
2. `Button` và `Checkbox` quy định client có thể **làm gì với sản phẩm đã nhận**.

Mỗi factory cụ thể tạo hai sản phẩm thuộc cùng một **họ biến thể**. Ví dụ:

| Interface sản phẩm | Họ Windows | Họ macOS |
| --- | --- | --- |
| `Button` | `WindowsButton` | `MacButton` |
| `Checkbox` | `WindowsCheckbox` | `MacCheckbox` |
| Concrete Factory | `WindowsGUIFactory` | `MacGUIFactory` |

Sơ đồ quan hệ:

~~~mermaid
flowchart TB
    Client["SettingsScreen"] --> AF["GUIFactory"]
    Client --> B["Button"]
    Client --> C["Checkbox"]
    WFactory["WindowsGUIFactory"] -. "implements" .-> AF
    MFactory["MacGUIFactory"] -. "implements" .-> AF
    WFactory --> WB["WindowsButton"]
    WFactory --> WC["WindowsCheckbox"]
    MFactory --> MB["MacButton"]
    MFactory --> MC["MacCheckbox"]
    WB -. "implements" .-> B
    MB -. "implements" .-> B
    WC -. "implements" .-> C
    MC -. "implements" .-> C
~~~

`SettingsScreen` chỉ cần biết các interface. Factory Windows tạo một **WindowsButton** và một **WindowsCheckbox**; factory macOS tạo sản phẩm tương ứng của họ macOS.

Trong Java, những lớp cụ thể có thể `implements Button` hoặc `implements Checkbox`. Factory trả về các interface này, vì vậy client không cần biết class nào đang được khởi tạo.

## 4. Ví dụ Java hoàn chỉnh

Ví dụ sau không dùng thư viện GUI thật; `render()` in ra console để thấy mỗi họ hiển thị khác nhau, còn `click()` mô phỏng việc nút được kích hoạt. Mục đích là quan sát **hợp đồng Abstract Product** và **cách factory tạo sản phẩm đúng họ**.

Lưu toàn bộ mã trong tệp **`ButtonCheckboxDemo.java`**:

~~~java
// Abstract Product 1: hành vi chung của mọi nút.
interface Button {
    void setLabel(String label);
    void render();

    // Chỉ dùng để mô phỏng một lần kích hoạt trong bản console.
    void click();
}

// Abstract Product 2: hành vi chung của mọi ô đánh dấu.
interface Checkbox {
    void setChecked(boolean checked);
    boolean isChecked();
    void render();
}

// Abstract Factory: tạo hai loại sản phẩm của cùng một họ.
interface GUIFactory {
    Button createButton();
    Checkbox createCheckbox();
}

// ===== Họ Windows =====

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
        System.out.println(
            "[Windows] Checkbox: " + (checked ? "[x]" : "[ ]")
        );
    }
}

class WindowsGUIFactory implements GUIFactory {
    @Override
    public Button createButton() {
        return new WindowsButton();
    }

    @Override
    public Checkbox createCheckbox() {
        return new WindowsCheckbox();
    }
}

// ===== Họ macOS =====

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
        System.out.println(
            "(macOS) Checkbox: " + (checked ? "ON" : "OFF")
        );
    }
}

class MacGUIFactory implements GUIFactory {
    @Override
    public Button createButton() {
        return new MacButton();
    }

    @Override
    public Checkbox createCheckbox() {
        return new MacCheckbox();
    }
}

// Client không tham chiếu tới WindowsButton hoặc MacCheckbox.
class SettingsScreen {
    private final Button saveButton;
    private final Checkbox notificationCheckbox;

    SettingsScreen(GUIFactory factory) {
        saveButton = factory.createButton();
        notificationCheckbox = factory.createCheckbox();
    }

    void show() {
        saveButton.setLabel("Lưu");
        notificationCheckbox.setChecked(true);

        saveButton.render();
        notificationCheckbox.render();

        System.out.println(
            "Bật thông báo: " + notificationCheckbox.isChecked()
        );

        // Mô phỏng người dùng nhấn nút trong bản console.
        saveButton.click();
    }
}

public class ButtonCheckboxDemo {
    public static void main(String[] args) {
        boolean mac = args.length > 0
                && "mac".equalsIgnoreCase(args[0]);

        // Composition root chọn một concrete factory.
        GUIFactory factory = mac
                ? new MacGUIFactory()
                : new WindowsGUIFactory();

        SettingsScreen screen = new SettingsScreen(factory);
        screen.show();
    }
}
~~~

Biên dịch bằng JDK có sẵn, không cần thư viện ngoài:

~~~bash
javac -encoding UTF-8 ButtonCheckboxDemo.java
java ButtonCheckboxDemo
java ButtonCheckboxDemo mac
~~~

Kết quả khi chạy với factory Windows:

~~~text
[Windows] Button: Lưu
[Windows] Checkbox: [x]
Bật thông báo: true
[Windows] Click: Lưu
~~~

Kết quả khi chạy với factory macOS:

~~~text
(macOS) Button: Lưu
(macOS) Checkbox: ON
Bật thông báo: true
(macOS) Click: Lưu
~~~

**Điểm cần quan sát:** hai lần chạy dùng **chung** mã `SettingsScreen`. Màn hình không kiểm tra `if (mac)`, không cần ép kiểu và không gọi `new WindowsButton()`. Toàn bộ khác biệt của bản demo được quyết định bởi **factory cụ thể** và **lớp triển khai của sản phẩm**.

### 4.1. Diễn giải luồng thực thi

1. `main()` chọn `WindowsGUIFactory` hoặc `MacGUIFactory` từ tham số dòng lệnh.
2. `SettingsScreen` nhận một đối tượng kiểu `GUIFactory` qua constructor.
3. Factory tạo một nút và một checkbox thuộc cùng họ.
4. `SettingsScreen` chỉ dùng các phương thức trên `Button` và `Checkbox`.
5. Lệnh `render()` được điều phối tới cách hiển thị Windows hoặc macOS tùy đối tượng thực tại runtime.
6. Lệnh `isChecked()` trả về trạng thái checkbox qua hợp đồng chung, dù mỗi biến thể hiển thị trạng thái theo cách riêng.

Java thực hiện **dynamic dispatch**: khi một phương thức interface được gọi trên biến `Button`, phương thức của lớp instance thực (`WindowsButton` hoặc `MacButton`) được chạy.

### 4.2. Vì sao không khai báo kiểu trả về là lớp cụ thể?

So sánh:

~~~java
// Client bị lộ chi tiết Windows ngay trong API.
WindowsButton createButton();

// Client chỉ biết loại sản phẩm chung.
Button createButton();
~~~

Khi `GUIFactory` trả về `Button`, mã gọi không phụ thuộc vào các phương thức riêng của `WindowsButton`. Nhờ đó cùng một client tiếp tục hoạt động khi factory khác trả về `MacButton`.

Điều này **không có nghĩa runtime tạo ra «đối tượng interface»**: `new WindowsButton()` vẫn diễn ra trong `WindowsGUIFactory`. Interface chỉ là **kiểu hợp đồng** ở ranh giới giữa code sử dụng và code triển khai.

## 5. Thiết kế hợp đồng phương thức cho đúng miền giao diện

Chọn phương thức cho interface cần cân bằng hai mục tiêu: **đủ cho client sử dụng** và **không buộc client phụ thuộc chi tiết từng nền tảng**.

### 5.1. Chọn tên diễn tả ý nghĩa, tránh lộ nền tảng

Những phương thức như `setLabel(String)` và `isChecked()` nói về hành vi của thành phần. Tránh đưa vào interface chung các phương thức như:

~~~java
// Các tên dưới đây KHÔNG nên đặt trong interface chung
// nếu chỉ một nền tảng hiểu các khả năng này.
void applyWindowsNativeStyle();
void setMacSpecificAppearance();
~~~

Chúng khiến client phụ thuộc vào chi tiết cụ thể. Nếu ứng dụng thật sự yêu cầu tính năng đặc thù nền tảng, hãy cân nhắc một abstraction riêng, một adapter hoặc xử lý ở lớp triển khai. Không phải mọi khả năng của concrete product đều phải được công khai trong interface chung.

### 5.2. Giữ mỗi interface gắn với trách nhiệm của thành phần

`Button` không nhất thiết có `isChecked()`; `Checkbox` không nhất thiết có `setLabel()` nếu mô hình bài toán xem nhãn checkbox là một đối tượng khác. Cũng không nên vì muốn tái sử dụng mà nhét mọi API vào một interface `UIComponent` rất lớn rồi để một số lớp ném `UnsupportedOperationException`.

Ví dụ không phù hợp:

~~~java
interface EverythingWidget {
    void click();
    void setChecked(boolean checked);
    boolean isChecked();
    void setLabel(String label);
}
~~~

Một nút thông thường có thể không hỗ trợ `setChecked()`, trong khi một checkbox có thể không thực hiện hành vi nút như mong đợi. Interface quá rộng làm client khó hiểu các khả năng được bảo đảm và dễ vi phạm **Interface Segregation Principle**.

### 5.3. Làm rõ trạng thái của Checkbox

Hai phương thức:

~~~java
void setChecked(boolean checked);
boolean isChecked();
~~~

mang một hợp đồng đơn giản nhưng thiết thực:

- Giá trị `true` nghĩa là checkbox đang được chọn; `false` nghĩa là chưa được chọn.
- `setChecked(value)` đặt trạng thái về `value`.
- `isChecked()` đọc trạng thái hiện tại.
- Trong ví dụ console, gọi `setChecked(true)` rồi `isChecked()` sẽ nhận `true`.

Nếu sau này ứng dụng cần trạng thái thứ ba (*indeterminate*) như «chỉ chọn một phần», boolean không còn biểu diễn đủ. Khi đó cần thiết kế lại hợp đồng có chủ đích, ví dụ một enum `UNCHECKED`, `CHECKED`, `INDETERMINATE`. **Không nên lén dùng `null` hoặc số nguyên tùy tiện** để mang trạng thái mới.

### 5.4. Đừng nhầm thao tác mô phỏng với cơ chế GUI thật

`render()` và `click()` trong ví dụ console giúp nhìn thấy hành vi; chúng **không phải yêu cầu bắt buộc của Abstract Factory**.

Một UI toolkit thật thường dùng cơ chế sự kiện. Hợp đồng cho nút có thể giống như:

~~~java
interface Button {
    void setLabel(String label);
    void setOnClick(Runnable handler);
}
~~~

Checkbox có thể đăng ký callback khi người dùng thay đổi lựa chọn:

~~~java
import java.util.function.Consumer;

interface Checkbox {
    void setChecked(boolean checked);
    boolean isChecked();
    void setOnCheckedChange(Consumer<Boolean> handler);
}
~~~

Đây là **biến thể API để thảo luận**, không ghép trực tiếp vào tệp demo phía trên. Với API có callback, phải định nghĩa rõ khi nào callback được gọi: chỉ khi người dùng thao tác, hay cả khi code gọi `setChecked()`? Có gọi khi đặt lại cùng giá trị không? Hàm callback chạy trên luồng nào? Các quyết định ấy phụ thuộc vào UI toolkit và yêu cầu ứng dụng, không do Abstract Factory quy định.

Trong Swing hoặc JavaFX thật, framework thường quản lý sự kiện và luồng giao diện; không nên lấy bản demo console làm mẫu để tự gọi `render()` hoặc xử lý click ngoài event loop của framework.

## 6. Chọn interface theo nhu cầu thực tế của client

Trước khi thêm một phương thức vào `Button` hoặc `Checkbox`, có thể dùng bốn câu hỏi sau:

1. **Client thực sự cần khả năng này không?** Ví dụ màn hình cần biết người dùng bật thông báo nên `isChecked()` có giá trị rõ ràng.
2. **Mọi biến thể của sản phẩm có thể cung cấp ngữ nghĩa tương đương không?** Nếu macOS và Windows đều có thể đặt trạng thái checkbox, `setChecked(boolean)` phù hợp để trừu tượng hóa.
3. **Tên phương thức nói về miền giao diện hay chi tiết kỹ thuật?** `setLabel()` mô tả hành vi; `paintWithGDI()` lộ thư viện đồ họa của một nền tảng.
4. **Hợp đồng có đủ cụ thể để client tin cậy không?** Ví dụ `isChecked()` phải trả về trạng thái hiện tại; không nên trả dữ liệu không liên quan tùy từng biến thể.

Lưu ý về khả năng mở rộng: việc thêm một **họ GUI** mới, chẳng hạn Linux, thường chỉ cần những concrete product và concrete factory mới. Nhưng nếu thêm một **loại sản phẩm** mới, chẳng hạn `Slider`, cần khai báo interface `Slider`, thêm `createSlider()` vào `GUIFactory` và triển khai phương thức trong mọi concrete factory.

## 7. Một số lỗi thường gặp khi khai báo Abstract Product

| Lỗi | Vì sao gây vấn đề | Cách điều chỉnh |
| --- | --- | --- |
| Interface chỉ có `render()` dù client cần đọc trạng thái checkbox | Client phải ép kiểu hoặc kiểm tra class để truy cập chức năng | Khai báo `Checkbox.isChecked()` và `setChecked()` trong loại sản phẩm phù hợp |
| `GUIFactory.createButton()` trả về `WindowsButton` | Hợp đồng factory bị buộc chặt vào một biến thể | Trả về `Button` |
| Client dùng `instanceof WindowsCheckbox` | Client biết và phân nhánh theo lớp triển khai | Biểu diễn nhu cầu dùng chung thành phương thức interface, nếu hợp lý |
| Đặt API riêng Windows/macOS vào interface chung | Các biến thể khác khó triển khai với ngữ nghĩa tương đương | Giữ API chung tập trung vào hành vi miền GUI |
| Gộp Button và Checkbox thành một interface có mọi phương thức | Một số phương thức vô nghĩa trên một số widget | Chia interface theo từng loại sản phẩm và trách nhiệm |
| Gọi `setChecked()` nhưng `isChecked()` trả về trạng thái không nhất quán | Phá vỡ hợp đồng client dựa vào | Xác định ngữ nghĩa trạng thái và triển khai nhất quán |
| Giả định gọi `setChecked()` luôn kích hoạt callback | Dẫn tới xử lý sự kiện trùng hoặc không mong muốn | Xác định chính xác ngữ nghĩa sự kiện theo API đang dùng |

**Không cần tạo interface cho mọi class đơn lẻ.** Interface phát huy giá trị khi có **hợp đồng được client cần đến** và các cách triển khai khác nhau cần dùng chung hợp đồng ấy. Trong Abstract Factory, những loại sản phẩm thuộc nhiều họ là lý do tự nhiên để có interface.

## 8. Kiểm tra hiểu bài

**Câu hỏi 1.** `Button` và `Checkbox` là hai interface sản phẩm khác nhau, vậy vì sao `GUIFactory` lại khai báo cả `createButton()` lẫn `createCheckbox()`?

**Trả lời:** Vì factory đại diện cho **một họ sản phẩm** gồm nhiều **loại sản phẩm**. Mỗi phương thức tạo một loại; cùng factory quyết định biến thể nhất quán cho cả bộ.

**Câu hỏi 2.** Nếu `WindowsButton` có thêm phương thức `setWindowsAccentColor()`, client giữ biến kiểu `Button` có gọi trực tiếp được không?

**Trả lời:** Không. Client chỉ thấy phương thức đã khai báo trên `Button`. Đây là giới hạn có chủ đích để giảm phụ thuộc vào nền tảng; nếu tính năng cần thật, phải cân nhắc lại thiết kế API.

**Câu hỏi 3.** Vì sao `Checkbox` cần `isChecked()` thay vì chỉ có `render()`?

**Trả lời:** Màn hình cài đặt phải đọc được trạng thái lựa chọn để sử dụng trong logic của nó. Hành vi «đọc trạng thái checkbox» thuộc hợp đồng của sản phẩm, không chỉ thuộc cách hiển thị.

**Câu hỏi 4.** Đổi `GUIFactory` từ `WindowsGUIFactory` sang `MacGUIFactory` có tự đổi mọi widget đã tạo trước đó không?

**Trả lời:** Không. Factory quyết định sản phẩm được tạo trong những lần gọi mới. Widget đã tạo là instance riêng; nếu muốn thay giao diện đang hiển thị, ứng dụng cần tạo lại widget hoặc cung cấp cơ chế cập nhật riêng.

**Câu hỏi 5.** Nếu thêm `Slider`, có cần thay đổi hai interface `Button` và `Checkbox` không?

**Trả lời:** Thường không. `Slider` là **loại sản phẩm riêng**; cần tạo interface `Slider` cùng phương thức tạo tương ứng ở factory. Hai interface hiện tại chỉ thay đổi nếu nhu cầu hành vi thực sự của chúng thay đổi.

## 9. Ghi nhớ khi viết Java

Trong Abstract Factory, **`Button` và `Checkbox` là những hợp đồng sản phẩm có trách nhiệm riêng**. `Button` thể hiện hành vi của nút; `Checkbox` thể hiện trạng thái và thao tác của một lựa chọn. Concrete product như `WindowsButton` hay `MacCheckbox` chịu trách nhiệm triển khai hành vi theo từng họ GUI.

Khi `GUIFactory` trả về kiểu `Button` và `Checkbox`, mã sử dụng có thể gọi **cùng những phương thức có ý nghĩa trong miền giao diện** mà không cần biết lớp triển khai. Đây là cơ sở để thay đổi toàn bộ họ sản phẩm bằng cách thay factory, giữ client gọn và tránh gắn chặt logic màn hình với từng nền tảng.
