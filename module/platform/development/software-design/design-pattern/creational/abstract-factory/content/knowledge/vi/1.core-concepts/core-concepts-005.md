# Điều kiện áp dụng khi ứng dụng cần nhiều họ sản phẩm tương thích

## 1. Bài toán lựa chọn Abstract Factory

Giả sử một ứng dụng quản lý đặt phòng có hai giao diện **Light** và **Dark**. Mỗi giao diện gồm các thành phần như nút bấm, hộp thoại và thông báo. Màn hình xác nhận đặt phòng cần dùng nút và hộp thoại cùng một phong cách.

Nếu mỗi màn hình tự quyết định lớp cần tạo:

~~~java
Button button = isDark ? new DarkButton() : new LightButton();
Dialog dialog = isDark ? new DarkDialog() : new LightDialog();
~~~

thì điều kiện chọn biến thể sẽ xuất hiện tại nhiều nơi. Một nơi sử dụng sai điều kiện có thể tạo `DarkButton` cùng `LightDialog`, khiến bộ giao diện thiếu nhất quán.

**Abstract Factory** thuộc nhóm mẫu thiết kế khởi tạo (*Creational Design Patterns*). Mẫu này cung cấp **giao diện để tạo một họ gồm nhiều đối tượng liên quan hoặc phụ thuộc nhau**, trong khi phần sử dụng không phải chỉ định trực tiếp những lớp sản phẩm cụ thể.

Đối với bài toán trên:

- **Loại sản phẩm** là `Button`, `Dialog`, `Notification`.
- **Họ sản phẩm** là tập các loại sản phẩm cùng biến thể: Light hoặc Dark.
- **Concrete factory** là đơn vị đưa ra quyết định nhất quán cho cả họ, chẳng hạn `LightUIFactory` hoặc `DarkUIFactory`.
- **Client** nhận `UIFactory` và sử dụng kết quả qua các interface sản phẩm.

Tuy nhiên, **không phải cứ có nhiều class hoặc nhiều biến thể là nên áp dụng Abstract Factory**. Cần xem ứng dụng có thật sự cần lựa chọn *đồng bộ một họ* hay không. Bài học này tập trung vào các điều kiện và dấu hiệu giúp ra quyết định đó.

## 2. «Họ sản phẩm tương thích» thực sự nghĩa là gì?

### 2.1. Phân biệt loại sản phẩm, biến thể và họ

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Loại sản phẩm** (*product type*) | Đối tượng đóng vai trò gì? | `Button`, `Dialog` |
| **Biến thể** (*variant*) | Vai trò đó được triển khai theo cách nào? | `LightButton`, `DarkButton` |
| **Họ sản phẩm** (*product family*) | Những biến thể nào được thiết kế để dùng cùng nhau? | `LightButton` + `LightDialog` |
| **Quy tắc tương thích** | Vì sao phải chọn các biến thể cùng họ? | Thành phần GUI cần thống nhất theme, kích thước hoặc hành vi tương tác |

Có thể hình dung hệ sản phẩm như một ma trận:

| Vai trò | Họ Light | Họ Dark |
| --- | --- | --- |
| `Button` | `LightButton` | `DarkButton` |
| `Dialog` | `LightDialog` | `DarkDialog` |
| `Notification` | `LightNotification` | `DarkNotification` |
| Factory cung cấp cả họ | `LightUIFactory` | `DarkUIFactory` |

Mỗi **hàng** biểu diễn một loại sản phẩm. Mỗi **cột** là một họ gồm nhiều sản phẩm có cùng biến thể. Abstract Factory tạo sản phẩm theo **một cột**, còn client vẫn thấy các vai trò chung theo **từng hàng**.

### 2.2. «Tương thích» không nhất thiết là cùng màu hoặc cùng class cha

Tương thích có thể đến từ nhiều quy tắc:

- **Giao diện:** nút, hộp thoại và thanh thông báo dùng chung một hệ thiết kế.
- **Giao thức:** bộ mã hóa và bộ giải mã phải thống nhất định dạng dữ liệu.
- **Nền tảng:** nhiều thành phần phải sử dụng cùng bộ API của hệ điều hành.
- **Nhà cung cấp:** các đối tượng truy cập dịch vụ phụ thuộc vào một bộ cấu hình hoặc giao thức của cùng nhà cung cấp.
- **Phiên bản:** các đối tượng được xây dựng cho cùng phiên bản giao thức hoặc schema.

Ví dụ, nếu bộ mã hóa sinh JSON nhưng bộ giải mã chỉ đọc XML, hai đối tượng đều có thể hoạt động **riêng lẻ** mà vẫn không tương thích **khi phối hợp**. Một factory theo họ JSON và một factory theo họ XML có thể biểu đạt rõ quy tắc chọn đồng bộ đó.

**Không cần các sản phẩm trong cùng họ có cùng interface.** `Button` và `Dialog` thực hiện hai vai trò khác nhau. Chỉ những biến thể của **cùng một loại** thường cần tuân theo cùng hợp đồng, ví dụ `LightButton` và `DarkButton` đều triển khai `Button`.

Cũng không có bảo đảm tự động rằng mọi đối tượng do một concrete factory trả về đều tương thích. Nếu `DarkUIFactory` vô tình trả về `LightDialog`, Java vẫn có thể chấp nhận vì cả hai cùng triển khai `Dialog`. Quy tắc tương thích phải được thể hiện bằng thiết kế, cách triển khai và kiểm tra phù hợp.

## 3. Các điều kiện nên có trước khi chọn Abstract Factory

### 3.1. Điều kiện 1 — Có từ hai loại sản phẩm liên quan cần phối hợp

Dấu hiệu mạnh nhất là cùng một luồng nghiệp vụ sử dụng **nhiều loại đối tượng** và các loại đó có quan hệ rõ ràng.

Ví dụ: màn hình xác nhận dùng cả `Button` và `Dialog`. Người dùng chọn Dark thì **cả hai** cần là phiên bản Dark. Client không nên quyết định từng thành phần một cách độc lập.

Nếu ứng dụng chỉ cần tạo một loại `Button` theo Light hoặc Dark, một factory đơn giản, Factory Method hoặc truyền dependency trực tiếp có thể là đủ. Theo cấu trúc phổ biến của Abstract Factory, **nhiều loại sản phẩm** mới làm nổi bật lợi ích tạo **một họ**.

Điều này là **tiêu chí thiết kế thực tiễn**, không phải yêu cầu của trình biên dịch rằng factory bắt buộc có ít nhất hai phương thức.

### 3.2. Điều kiện 2 — Có nhiều họ biến thể thực sự cần hỗ trợ

Ứng dụng nên có ít nhất hai họ đang tồn tại hoặc yêu cầu mở rộng đủ rõ để việc tách biến thể mang lại giá trị.

Ví dụ:

- Light: `LightButton`, `LightDialog`.
- Dark: `DarkButton`, `DarkDialog`.
- Trong tương lai có kế hoạch High Contrast, với cùng bộ vai trò sản phẩm.

Nếu sản phẩm chỉ dùng một giao diện, không có yêu cầu thay thế cụ thể và vẫn rất đơn giản, tạo một hệ thống nhiều interface/factory từ sớm có thể là **trừu tượng hóa quá mức** (*overengineering*).

Nói cách khác, cần có một **điểm biến thiên thực tế**: lựa chọn họ sản phẩm có thể thay đổi theo môi trường, cấu hình, nền tảng hoặc yêu cầu sản phẩm.

### 3.3. Điều kiện 3 — Tồn tại quy tắc tương thích ở cấp họ

Phải xác định được **vì sao các sản phẩm nên được chọn cùng nhau**.

Một quy tắc rõ ràng có thể là:

> Nếu dùng giao diện Dark, mọi Button và Dialog của màn hình đó phải thuộc họ Dark.

Hoặc:

> Nếu dùng định dạng JSON, bộ mã hóa và giải mã được cấp cho cùng phiên xử lý phải tương thích với định dạng JSON.

Nếu sản phẩm A và B có thể thay đổi hoàn toàn độc lập, việc gộp chúng vào cùng factory có thể tạo ra **phụ thuộc giả**. Chẳng hạn, nếu ứng dụng cho phép người dùng tự chọn màu nút và kiểu hộp thoại độc lập theo yêu cầu nghiệp vụ, một factory ép cả hai theo một theme duy nhất có thể hạn chế khả năng cần thiết.

**Câu hỏi quyết định:** khi thay đổi một lựa chọn cấu hình, có bắt buộc thay đổi **nhiều loại sản phẩm cùng lúc** để hệ thống hoạt động đúng hoặc nhất quán hay không?

### 3.4. Điều kiện 4 — Client có thể làm việc qua các hợp đồng chung

Để một client sử dụng nhiều họ mà không sửa mã riêng cho từng họ, cần xác định được các **Abstract Product**:

~~~java
interface Button {
    void render();
}

interface Dialog {
    void show();
}
~~~

Các lớp `LightButton`, `DarkButton` cùng thực hiện `Button`; `LightDialog` và `DarkDialog` cùng thực hiện `Dialog`. Client chỉ dùng `render()` và `show()` theo hợp đồng.

Nếu client liên tục phải gọi `instanceof DarkButton` hoặc ép kiểu để truy cập phương thức đặc thù, cần xem lại **ranh giới trừu tượng**. Có thể hợp đồng chung chưa đủ, có thể trách nhiệm đang đặt sai chỗ, hoặc có thể sản phẩm không thực sự có khả năng thay thế lẫn nhau.

Hợp đồng nên phản ánh **hành vi client thật sự cần**, không sao chép toàn bộ API của một biến thể để ép các biến thể khác triển khai.

### 3.5. Điều kiện 5 — Bộ loại sản phẩm tương đối ổn định

Một abstract factory thường có phương thức tạo cho mỗi loại sản phẩm:

~~~java
interface UIFactory {
    Button createButton();
    Dialog createDialog();
}
~~~

Nếu thêm họ **High Contrast**, có thể bổ sung `HighContrastUIFactory` và các concrete product tương ứng. Client dùng `UIFactory` thường không cần thay đổi.

Nhưng nếu thêm **một loại sản phẩm mới** như `Checkbox`, phải thêm `createCheckbox()` vào `UIFactory` và triển khai trong **tất cả** concrete factory hiện có. Vì vậy:

- **Nhiều họ biến thể, cùng tập loại sản phẩm:** Abstract Factory thường phát huy điểm mạnh.
- **Tập loại sản phẩm liên tục thay đổi:** chi phí cập nhật interface và các factory tăng lên; cân nhắc chia ranh giới factory hoặc thiết kế khác.

Tập sản phẩm không cần «đóng băng» tuyệt đối. Điều cần đánh giá là **hướng thay đổi thường xuyên nhất** trong hệ thống.

### 3.6. Điều kiện 6 — Có ranh giới phù hợp để chọn và cấp factory

Việc chọn họ nên diễn ra tại nơi ứng dụng biết cấu hình hoặc môi trường:

~~~java
UIFactory factory = useDark
        ? new DarkUIFactory()
        : new LightUIFactory();

ConfirmationScreen screen = new ConfirmationScreen(factory);
~~~

`ConfirmationScreen` chỉ giữ một `UIFactory` hoặc giữ các sản phẩm đã tạo từ factory đó. Nó không cần tự đọc biến môi trường hay tự chọn từng class.

Trong ứng dụng lớn, vị trí này thường là **composition root**, tầng lắp ghép dependency hoặc một phạm vi tạo giao diện mới. Nếu cấu hình thay đổi trong lúc chạy, cần quyết định rõ **khi nào factory được thay thế** và có phải tạo lại những sản phẩm đã tồn tại hay không.

Một factory chọn đúng họ sẽ có ích khi ứng dụng có cơ chế **cấp cùng factory cho các client thuộc cùng phạm vi nhất quán**.

## 4. Kiểm tra nhanh qua luồng quyết định

~~~mermaid
flowchart TD
    A["Ứng dụng cần tạo sản phẩm"] --> B{"Có nhiều loại sản phẩm liên quan?"}
    B -->|Không| X["Cân nhắc tạo trực tiếp hoặc factory đơn giản"]
    B -->|Có| C{"Có nhiều họ biến thể cần hỗ trợ?"}
    C -->|Không| Y["Giữ thiết kế đơn giản cho tới khi có nhu cầu"]
    C -->|Có| D{"Các sản phẩm phải phối hợp theo cùng họ?"}
    D -->|Không| Z["Cân nhắc factory riêng cho mỗi nhu cầu"]
    D -->|Có| E{"Client dùng được hợp đồng chung?"}
    E -->|Không| F["Thiết kế lại ranh giới Abstract Product"]
    E -->|Có| G{"Tập loại sản phẩm khá ổn định?"}
    G -->|Không| H["Cân nhắc tách factory hoặc thiết kế linh hoạt khác"]
    G -->|Có| I["Abstract Factory là lựa chọn đáng cân nhắc"]
~~~

Đây là **sơ đồ đánh giá**, không phải một bộ luật cứng. Có những thiết kế hợp lý dùng Abstract Factory dù hiện tại chỉ mới có một họ, vì hợp đồng đa nền tảng đã được yêu cầu rõ trong lộ trình. Ngược lại, có nhiều họ nhưng phạm vi rất nhỏ vẫn có thể giải quyết gọn bằng một cơ chế đơn giản hơn.

### 4.1. Bảng chấm dấu hiệu áp dụng

| Câu hỏi | Nếu trả lời «Có» | Nếu trả lời «Không» |
| --- | --- | --- |
| Có nhiều loại sản phẩm được tạo trong cùng một ngữ cảnh không? | Có nền tảng để tạo một họ | Ít lợi ích từ việc gom phương thức |
| Các loại sản phẩm có quy tắc tương thích chung không? | Có lý do để chọn theo họ | Dễ tạo quan hệ phụ thuộc không cần thiết |
| Có từ hai họ/biến thể cần hỗ trợ không? | Có điểm thay thế thực tế | Có thể chưa cần hệ factory đầy đủ |
| Các biến thể của cùng loại có hợp đồng chung không? | Client có thể tách khỏi class cụ thể | Cần làm rõ abstraction trước |
| Việc thêm họ mới có khả năng thường xuyên hơn thêm loại sản phẩm mới không? | Đánh đổi của Abstract Factory thuận lợi | Cần cân nhắc chi phí sửa nhiều factory |
| Có thể chọn factory một lần theo cấu hình/ngữ cảnh không? | Giữ được tính nhất quán trong phạm vi sử dụng | Dễ lặp quy tắc chọn trong từng client |

Nếu phần lớn câu hỏi ở cột «Có», Abstract Factory là ứng viên mạnh. Tuy nhiên, trước khi áp dụng vẫn cần đánh giá mức độ phức tạp của bài toán, số client và chi phí bảo trì.

## 5. Ví dụ Java hoàn chỉnh: chọn một họ GUI tương thích

Ví dụ dưới đây thể hiện **hai vai trò sản phẩm** (`Button` và `Dialog`), **hai họ** (Light và Dark) và **một client** không phụ thuộc lớp sản phẩm cụ thể. Phần hiển thị chỉ in ra console để tập trung vào mẫu thiết kế.

Lưu toàn bộ mã trong tệp `CompatibleFamilyDemo.java`:

~~~java
// ==== Abstract Products ====
interface Button {
    void render();
}

interface Dialog {
    void show();
}

// ==== Abstract Factory ====
interface UIFactory {
    Button createButton();
    Dialog createDialog();
}

// ==== Concrete Products: Light ====
class LightButton implements Button {
    @Override
    public void render() {
        System.out.println("[Light] Button: Xác nhận");
    }
}

class LightDialog implements Dialog {
    @Override
    public void show() {
        System.out.println("[Light] Dialog: Đặt phòng thành công");
    }
}

// ==== Concrete Products: Dark ====
class DarkButton implements Button {
    @Override
    public void render() {
        System.out.println("[Dark] Button: Xác nhận");
    }
}

class DarkDialog implements Dialog {
    @Override
    public void show() {
        System.out.println("[Dark] Dialog: Đặt phòng thành công");
    }
}

// ==== Concrete Factories ====
class LightUIFactory implements UIFactory {
    @Override
    public Button createButton() {
        return new LightButton();
    }

    @Override
    public Dialog createDialog() {
        return new LightDialog();
    }
}

class DarkUIFactory implements UIFactory {
    @Override
    public Button createButton() {
        return new DarkButton();
    }

    @Override
    public Dialog createDialog() {
        return new DarkDialog();
    }
}

// ==== Client chỉ làm việc với interface ====
class ConfirmationScreen {
    private final Button button;
    private final Dialog dialog;

    ConfirmationScreen(UIFactory factory) {
        this.button = factory.createButton();
        this.dialog = factory.createDialog();
    }

    void display() {
        button.render();
        dialog.show();
    }
}

public class CompatibleFamilyDemo {
    public static void main(String[] args) {
        // Quyết định chọn biến thể được thực hiện một lần.
        boolean useDark =
                args.length > 0 && "dark".equalsIgnoreCase(args[0]);

        UIFactory factory = useDark
                ? new DarkUIFactory()
                : new LightUIFactory();

        ConfirmationScreen screen = new ConfirmationScreen(factory);
        screen.display();
    }
}
~~~

Biên dịch và chạy bằng JDK:

~~~bash
javac -encoding UTF-8 CompatibleFamilyDemo.java
java CompatibleFamilyDemo
java CompatibleFamilyDemo dark
~~~

Hai lần chạy lần lượt in:

~~~text
[Light] Button: Xác nhận
[Light] Dialog: Đặt phòng thành công

[Dark] Button: Xác nhận
[Dark] Dialog: Đặt phòng thành công
~~~

### 5.1. Vì sao ví dụ đáp ứng các điều kiện?

1. **Có nhiều vai trò sản phẩm:** màn hình cần cả `Button` và `Dialog`.
2. **Có hai họ:** mỗi vai trò có phiên bản Light và Dark.
3. **Có quy tắc phối hợp:** nút và hộp thoại của một màn hình cùng dùng một theme.
4. **Có hợp đồng chung:** `Button` và `Dialog` mô tả hành vi client cần.
5. **Có điểm lựa chọn tập trung:** `main()` chọn một `UIFactory` rồi cấp cho màn hình.
6. **Có thể thêm họ mới:** ví dụ thêm `HighContrastUIFactory` mà không phải sửa logic `ConfirmationScreen` nếu các interface không đổi.

Client không có điều kiện `if (useDark)`, cũng không cần biết `DarkButton` hoặc `LightDialog` là những lớp nào. Quyết định chọn family nằm ở phần khởi tạo ứng dụng.

### 5.2. Một factory, nhiều lần tạo sản phẩm

Điểm quan trọng không phải factory tạo **mọi sản phẩm cùng thời điểm**. Một client có thể gọi `factory.createButton()` ngay khi tạo màn hình, rồi gọi `factory.createDialog()` sau một sự kiện. Chừng nào client dùng **cùng factory đại diện cho cùng họ**, các sản phẩm mới vẫn thuộc họ được chọn.

Ví dụ này lưu hai sản phẩm trong constructor để dễ quan sát. Nếu muốn thay Light thành Dark cho **màn hình đã tồn tại**, chỉ đổi biến `factory` ở `main()` là không đủ: những instance cũ vẫn là Light. Ứng dụng phải tạo lại chúng hoặc hỗ trợ cơ chế thay giao diện riêng.

### 5.3. Tính nhất quán được bảo đảm ở đâu?

Các interface chỉ diễn tả khả năng của từng loại sản phẩm. Bản thân Java không ngăn `DarkUIFactory.createDialog()` trả về `LightDialog` vì lớp này cũng triển khai `Dialog`.

Do đó, khi quy tắc phối hợp quan trọng, nên kiểm thử **mỗi concrete factory** tạo đúng họ. Các thử nghiệm có thể kiểm tra bộ thành phần Light, Dark tương ứng và kết quả sử dụng chung; đối với giao thức dữ liệu còn cần kiểm thử khả năng tương thích thực tế.

Không nên thêm một phương thức `getThemeName()` vào mọi product **chỉ để test**, nếu client không có nhu cầu đó. Trong test có thể dùng metadata của fixture, assertion cụ thể hoặc kiểm thử hành vi tích hợp, miễn sao không làm méo mó interface sản phẩm vì yêu cầu nội bộ của kiểm thử.

## 6. Những trường hợp Abstract Factory chưa phải lựa chọn phù hợp

### 6.1. Chỉ có một loại sản phẩm cần thay thế

Nếu ứng dụng chỉ có nhiều cách tạo `Logger`, nhưng không có bộ sản phẩm liên quan phải chọn đồng bộ, **truyền `Logger` qua interface** hoặc một factory đơn giản thường dễ hiểu hơn.

~~~java
interface Logger {
    void log(String message);
}

// Nơi lắp ghép ứng dụng chọn implementation phù hợp,
// sau đó cung cấp Logger cho client.
~~~

Không cần tạo `LoggingFamilyFactory` với hàng loạt phương thức nếu thực tế chỉ có một loại sản phẩm.

### 6.2. Các biến thể có thể kết hợp tùy ý

Giả sử phần mềm cho người dùng tự chọn một `Button` Light và một `Dialog` Dark, và đây là **yêu cầu hợp lệ** của sản phẩm. Một factory chỉ tạo cả bộ Light hoặc cả bộ Dark sẽ trở thành ràng buộc không phù hợp.

Khi các lựa chọn **độc lập**, nên xem xét cấp từng dependency hoặc factory cho từng trách nhiệm. Chỉ gom những thứ thực sự cần đồng bộ.

### 6.3. Mới có một cấu hình đơn giản và chưa có nhu cầu thay đổi

Nếu một màn hình nhỏ chỉ được sử dụng một lần và chỉ có một bộ widget, thêm hai interface, một abstract factory và nhiều concrete factory có thể tăng độ phức tạp mà chưa tạo lợi ích đáng kể.

Không nên dùng Abstract Factory chỉ vì có một câu lệnh `new`. **Dấu hiệu áp dụng là nhu cầu thay nhiều sản phẩm theo cùng một quyết định**, không phải số dòng khởi tạo.

### 6.4. Loại sản phẩm thay đổi liên tục

Khi hệ thống thêm một vai trò mới mỗi tuần, ví dụ `Slider`, `Menu`, `Toast`, `Tooltip`, mọi concrete factory sẽ phải cập nhật theo interface chung. Nếu mỗi nhóm tính năng do đội khác quản lý, một interface quá lớn có thể trở thành nút thắt.

Lúc đó nên đánh giá cách chia thành factory theo phạm vi thành phần, hoặc dùng cơ chế đăng ký plugin khi miền bài toán thực sự cần. Mỗi lựa chọn có đánh đổi; không có một thiết kế thay thế duy nhất cho mọi tình huống.

### 6.5. Không có trừu tượng hành vi đủ ổn định

Nếu hai biến thể chỉ giống nhau ở tên gọi nhưng khác hẳn vòng đời và hành vi, cố ép chúng triển khai một interface có thể khiến client liên tục ép kiểu, dùng `instanceof` hoặc nhận `UnsupportedOperationException`.

Khi đó cần làm rõ **hợp đồng nghiệp vụ chung** hoặc tách vai trò phù hợp. Abstract Factory không tự biến hai sản phẩm khác bản chất thành những đối tượng có thể thay thế lẫn nhau.

## 7. Đánh đổi cần tính khi thiết kế nhiều họ

### 7.1. Dễ thêm họ mới, khó thêm loại sản phẩm mới

| Kiểu thay đổi | Việc cần làm | Ảnh hưởng lên client |
| --- | --- | --- |
| Thêm họ **High Contrast** | Tạo các concrete product và một concrete factory cho họ mới | Client hiện tại thường không đổi |
| Thêm loại sản phẩm **Checkbox** | Thêm `Checkbox`, `createCheckbox()` và cài đặt cho **tất cả** concrete factory | Client cũ có thể không đổi, nhưng toàn bộ factory phải sửa |
| Thay constructor của `DarkButton` | Sửa trong `DarkUIFactory.createButton()` | Client không cần biết constructor |
| Đổi quy tắc phối hợp sản phẩm | Điều chỉnh factory, quy tắc cấu hình và kiểm thử tương thích | Có thể ảnh hưởng cách cấp factory hoặc phạm vi sử dụng |
| Thay theme trong lúc chạy | Chọn factory mới và quản lý việc tạo lại/cập nhật widget | Có thể phải thay đổi quản lý vòng đời UI |

Từ bảng này, một dấu hiệu rất quan trọng là **tốc độ thay đổi theo hai chiều**:

- Nếu các **họ** tăng thường xuyên, còn tập **loại sản phẩm** khá ổn định, Abstract Factory có xu hướng thuận lợi.
- Nếu các **loại sản phẩm** mở rộng thường xuyên, còn số họ ít, chi phí sửa tất cả factory dễ trở nên lớn.

### 7.2. Kiểm soát vòng đời và trạng thái

Abstract Factory quy định **cách lựa chọn loại sản phẩm cụ thể**, nhưng không tự quyết định mỗi lần gọi phải tạo một instance mới hay trả về instance dùng chung. Điều đó thuộc về hợp đồng cụ thể và thiết kế vòng đời.

Ví dụ, một `Dialog` có thể cần tạo mới cho mỗi lần hiển thị, còn một đối tượng cấu hình không thay đổi có thể được tái sử dụng. Khi chuyển từ tạo trực tiếp sang factory, cần giữ nguyên những giả định hợp lệ về:

- Thời điểm khởi tạo và giải phóng tài nguyên.
- Trạng thái có được chia sẻ giữa các client hay không.
- Khả năng sử dụng đồng thời ở nhiều luồng.
- Cách xử lý lỗi khi một sản phẩm trong họ không thể khởi tạo.

Một factory đúng tên họ nhưng tạo sản phẩm sai vòng đời vẫn có thể làm hỏng hành vi ứng dụng.

### 7.3. Không dùng «fallback» để che giấu họ sản phẩm không tương thích

Nếu cấu hình yêu cầu họ **Dark** nhưng factory tương ứng không tồn tại, trả về `LightUIFactory` không phải lúc nào cũng an toàn. Đặc biệt với nhà cung cấp dịch vụ hay giao thức dữ liệu, đổi sang họ khác có thể sai nghiệp vụ.

Cần phân biệt lỗi cấu hình với lỗi triển khai factory, và xác định chính sách báo lỗi hoặc fallback theo yêu cầu hệ thống. **Một họ mặc định chỉ phù hợp nếu thay thế như vậy được phép và an toàn.**

### 7.4. Cần kiểm tra đúng mức độ tương thích

Đối với GUI, việc so sánh giao diện có thể giúp phát hiện pha trộn theme. Với giao thức, việc kiểm tra các sản phẩm hoạt động cùng nhau thường quan trọng hơn việc chỉ so sánh tên lớp.

Ví dụ, một bộ serializer và deserializer cùng được đặt tên `Json...` nhưng có schema khác phiên bản vẫn có thể không tương thích. **Tên họ là lời hứa thiết kế, không phải bằng chứng đầy đủ về tương thích.**

## 8. Một số tình huống thực tế và quyết định áp dụng

| Tình huống | Có nên cân nhắc Abstract Factory? | Giải thích |
| --- | --- | --- |
| Ứng dụng nhiều theme, mỗi theme có Button/Dialog/Notification | **Có** | Nhiều loại sản phẩm phải cùng biến thể |
| Ứng dụng đa nền tảng, mỗi nền tảng có bộ widget riêng | **Có** | Một lựa chọn nền tảng chi phối cả bộ widget |
| Hệ thống hỗ trợ nhiều định dạng, encoder/decoder phải tương thích | **Có** | Quy tắc đồng bộ theo định dạng rõ ràng |
| Chỉ chọn một lớp `EmailSender` theo môi trường | **Chưa nhất thiết** | Một dependency có thể đủ, không có họ nhiều loại sản phẩm |
| Mỗi widget cho phép người dùng chọn style riêng | **Không nhất thiết** | Các lựa chọn có thể độc lập |
| Chỉ có một giao diện cố định, ít thay đổi | **Thường chưa cần** | Chi phí trừu tượng hóa có thể vượt lợi ích |
| Liên tục thêm nhiều loại widget mới vào một factory lớn | **Cần cân nhắc lại** | Mỗi loại mới gây thay đổi trên mọi họ |
| Bộ SDK của các nhà cung cấp có nhiều thành phần phải dùng đồng bộ | **Có, nếu hợp đồng chung đủ rõ** | Factory có thể cô lập cách tạo bộ adapter tương thích |

Trong nhiều hệ thống thực tế, có thể dùng Abstract Factory **kết hợp** với Dependency Injection, Adapter hoặc Factory Method. Abstract Factory quy định **họ sản phẩm cần tạo**; các cơ chế khác có thể hỗ trợ cách chọn factory, chuyển đổi API hoặc cài đặt phương thức tạo.

## 9. Bài tập tư duy: nhận diện điều kiện áp dụng

**Tình huống A — Giao diện Light/Dark**

Ứng dụng cần tạo `Button`, `Dialog` và `Menu`; người dùng chỉ chọn **một theme cho toàn màn hình**.

*Phân tích:* Có nhiều loại sản phẩm, nhiều họ và một quy tắc đồng bộ rõ. Abstract Factory là ứng viên phù hợp; mỗi concrete factory tạo cả bộ sản phẩm theo theme.

**Tình huống B — Hai loại bộ mã hóa độc lập**

Ứng dụng tạo `ImageEncoder` theo PNG/JPEG và `AudioEncoder` theo MP3/AAC; người dùng có thể chọn mỗi định dạng độc lập.

*Phân tích:* Dù có nhiều loại sản phẩm và biến thể, chưa có lý do để gộp tất cả thành **một họ cố định**. Các factory riêng hoặc cơ chế chọn độc lập có thể hợp lý hơn.

**Tình huống C — Nhiều nhà cung cấp có bộ SDK tương thích**

Mỗi nhà cung cấp cung cấp `StorageClient` và `MetadataClient`. Hai client phải dùng cùng thông tin phiên bản hoặc cấu hình nhà cung cấp để thực hiện một nghiệp vụ.

*Phân tích:* Có nhiều loại sản phẩm cần phối hợp theo cùng provider. Nếu mã nghiệp vụ có thể làm việc qua interface chung, một Abstract Factory cho mỗi provider có thể kiểm soát việc tạo bộ client tương thích. Cần kiểm tra thêm quy tắc xác thực, vòng đời và phiên bản API.

**Tình huống D — Một logger duy nhất**

Ứng dụng chỉ cần một `Logger` được truyền từ bên ngoài; không có sản phẩm phụ thuộc đi kèm.

*Phân tích:* Chỉ cần interface và một nơi cấu hình implementation. Abstract Factory thường chưa đem lại lợi ích đáng kể.

**Tình huống E — Màn hình đổi theme tức thời**

Ứng dụng có Abstract Factory Light/Dark, nhưng cần đổi giao diện khi người dùng bấm nút chuyển theme.

*Phân tích:* Abstract Factory hữu ích trong việc tạo đúng họ **mới**, nhưng không tự thay đổi các đối tượng đã tạo. Cần quản lý thêm việc tái tạo hoặc cập nhật component theo vòng đời UI.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Ứng dụng có `LightButton` và `DarkButton`. Chỉ từ đó có thể khẳng định cần Abstract Factory không?

**Trả lời:** Chưa. Cần xem có **nhiều loại sản phẩm liên quan** và quy tắc chọn đồng bộ một họ hay không. Nếu chỉ thay một Button, factory đơn giản hoặc dependency injection có thể đủ.

**Câu 2.** Trong một hệ thống, `Button` và `Dialog` có phải cùng triển khai một interface duy nhất để thuộc cùng họ không?

**Trả lời:** Không. Chúng là hai loại sản phẩm khác nhau với hợp đồng riêng. Các biến thể của **cùng một loại** mới thường triển khai cùng interface sản phẩm.

**Câu 3.** Có thể nhận `LightButton` và `DarkDialog` trong cùng một màn hình dù dùng Abstract Factory không?

**Trả lời:** Vẫn có thể xảy ra nếu client tạo sản phẩm ngoài factory hoặc một concrete factory viết sai. Pattern tổ chức cách lựa chọn cùng họ; cần triển khai và kiểm thử quy tắc tương thích.

**Câu 4.** Thêm họ High Contrast hay thêm loại sản phẩm Checkbox thường dễ hơn với Abstract Factory?

**Trả lời:** Thêm **họ mới** thường ít ảnh hưởng client hơn. Thêm **loại sản phẩm mới** đòi hỏi thay đổi abstract factory và các concrete factory hiện có.

**Câu 5.** Nếu ứng dụng phải chọn Button và Dialog độc lập, việc gom vào cùng factory có còn hợp lý không?

**Trả lời:** Chỉ hợp lý nếu có quy tắc nghiệp vụ khác buộc chúng đi cùng nhau. Nếu hai lựa chọn thật sự độc lập, gộp thành một họ có thể tạo ràng buộc không cần thiết.

**Câu 6.** Vì sao nên chọn factory tại composition root thay vì đọc cấu hình trong từng sản phẩm?

**Trả lời:** Quy tắc lựa chọn được tập trung và cùng một factory có thể cung cấp bộ sản phẩm theo một cấu hình nhất quán. Client không phải lặp logic chọn class hoặc tự quản lý khả năng tương thích.

## 11. Kết luận

**Abstract Factory phù hợp khi ứng dụng cần nhiều loại sản phẩm liên quan, có nhiều họ biến thể và phải lựa chọn các sản phẩm tương thích theo cùng một quyết định cấu hình hoặc ngữ cảnh.** Sự tồn tại của interface sản phẩm ổn định và khả năng cấp một factory cho nhiều client giúp cô lập chi tiết triển khai.

Khi quyết định áp dụng, hãy ưu tiên xác định **quy tắc tương thích giữa các sản phẩm**, **hướng thay đổi của số họ và số loại sản phẩm**, cùng **ranh giới chọn factory**. Khi các sản phẩm độc lập, chỉ có một loại hoặc chưa có nhu cầu thay đổi rõ ràng, một thiết kế đơn giản hơn có thể dễ bảo trì. Khi các điều kiện thực sự phù hợp, Abstract Factory giúp hệ thống thay trọn một họ sản phẩm mà vẫn giữ phần logic sử dụng ổn định.
