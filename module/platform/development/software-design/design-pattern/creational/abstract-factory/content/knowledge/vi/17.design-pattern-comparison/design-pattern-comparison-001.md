# Abstract Factory và Factory Method: mục tiêu, cấu trúc và phạm vi tạo đối tượng

> **Chương:** So sánh mẫu thiết kế  
> **Học phần:** Học về Abstract Factory trong Design Pattern (mã module: `SOFTWARE_DESIGN_DESIGN_PATTERN_CREATIONAL_ABSTRACT_FACTORY`).  
> **Trọng tâm:** Phân biệt hai mẫu thiết kế khởi tạo (*creational patterns*) của GoF theo **vấn đề cần giải quyết**, **cách các thành phần cộng tác** và **phạm vi quyết định tạo đối tượng**.

## 1. Vì sao hai mẫu này thường bị nhầm?

Cả **Factory Method** và **Abstract Factory** đều giúp mã sử dụng đối tượng giảm phụ thuộc vào các lớp cụ thể. Trong cả hai mẫu, mã sử dụng có thể gọi một phương thức tên `createButton()` mà không trực tiếp gọi `new WindowsButton()` hoặc `new MacButton()`.

Tuy nhiên, **chỉ nhìn tên phương thức không đủ để xác định mẫu thiết kế**. Cần trả lời:

- **Factory Method:** *Một quy trình có bước cần tạo đối tượng; lớp con được quyền quyết định biến thể sản phẩm nào sẽ được tạo ở bước đó.* Quy trình dùng đối tượng vẫn do lớp cơ sở tổ chức.
- **Abstract Factory:** *Một hệ thống cần một bộ sản phẩm có liên quan hoặc tương thích với nhau; mã sử dụng chọn một factory đại diện cho cả họ, rồi yêu cầu factory đó tạo các loại sản phẩm cần thiết.*

Chẳng hạn, màn hình của ứng dụng desktop cần một `Button`. Nếu một lớp `Dialog` có quy trình `show()` cố định nhưng cho phép các lớp con lựa chọn Button để hiển thị, đó là tình huống điển hình của **Factory Method**. Nếu màn hình cần cả `Button`, `Checkbox` và sau này là `TextField` cùng phong cách Windows hoặc macOS, đó là tình huống điển hình của **Abstract Factory**.

## 2. Bảng so sánh theo ba khía cạnh trọng tâm

| Tiêu chí | Factory Method | Abstract Factory |
| --- | --- | --- |
| **Mục tiêu chính** | Để lớp con quyết định lớp sản phẩm cụ thể được khởi tạo tại một bước của quy trình | Tạo **cả họ** đối tượng liên quan/tương thích mà không buộc client phụ thuộc vào lớp cụ thể |
| **Đơn vị biến thiên** | Cách tạo một sản phẩm tại một *điểm mở rộng* của `Creator` | Một **họ sản phẩm** gồm nhiều loại sản phẩm |
| **Cấu trúc chủ đạo** | `Creator` khai báo factory method; `ConcreteCreator` ghi đè; `Product` là hợp đồng chung | `AbstractFactory` khai báo nhiều thao tác tạo; mỗi `ConcreteFactory` cung cấp các biến thể cùng họ của những `AbstractProduct` |
| **Cách mở rộng thường gặp** | Kế thừa và ghi đè phương thức | Truyền/thay thế một đối tượng factory qua composition (cấu thành) |
| **Mã sử dụng phụ thuộc vào** | Giao diện/lớp cơ sở `Creator` và `Product` | `AbstractFactory` và các giao diện `AbstractProduct` |
| **Phạm vi điều phối** | Quy trình của một creator cần tạo sản phẩm phù hợp ở một thời điểm | Một client hoặc phân hệ cần phối hợp nhiều loại sản phẩm thuộc cùng họ |
| **Điểm mạnh nổi bật** | Giữ ổn định quy trình dùng sản phẩm, cho phép thay cách tạo qua subclass | Giữ các sản phẩm cùng họ nhất quán và đổi cả họ ở một điểm cấu hình |
| **Đánh đổi chính** | Tăng số lớp creator khi có thêm nhiều biến thể; gắn mở rộng với kế thừa | Thêm một *loại sản phẩm* thường phải sửa giao diện factory và mọi concrete factory |

Đây là hai mẫu có **trọng tâm khác nhau**, chứ không phải hai cách đặt tên cho cùng một phương thức. Một hệ thống có thể sử dụng cả hai.

## 3. Factory Method: lớp con chọn sản phẩm cho một quy trình

### 3.1. Vấn đề và mục tiêu

Giả sử ứng dụng có lớp `Dialog` với quy trình hiển thị chung: tạo Button, đặt Button lên giao diện, rồi xử lý tương tác. Quy trình này áp dụng cho nhiều hệ điều hành, nhưng Button cụ thể khác nhau theo nền tảng.

Nếu `Dialog.show()` tự viết `new WindowsButton()` thì quy trình bị gắn với Windows. Nếu viết `if` cho mọi nền tảng ngay trong `show()`, lớp cơ sở cần sửa mỗi khi có biến thể mới.

Factory Method giải quyết bằng cách chuyển **quyết định tạo Button** sang một phương thức mà các lớp con có thể ghi đè. `Dialog` điều khiển *khi nào và vì sao* cần Button; `WindowsDialog` và `MacDialog` quyết định *Button nào* được tạo.

### 3.2. Các vai trò trong cấu trúc

| Vai trò | Ví dụ |
| --- | --- |
| `Product` | Giao diện `Button` |
| `ConcreteProduct` | `WindowsButton`, `MacButton` |
| `Creator` | Lớp cơ sở `Dialog` khai báo `createButton()` và chứa `show()` |
| `ConcreteCreator` | `WindowsDialog`, `MacDialog` ghi đè `createButton()` |

~~~mermaid
flowchart TB
    Caller["Mã gọi"] --> Creator["Dialog: show()"]
    Creator --> Method["createButton(): Button"]
    WinCreator["WindowsDialog"] -. "ghi đè" .-> Method
    MacCreator["MacDialog"] -. "ghi đè" .-> Method
    WinCreator --> WinButton["WindowsButton"]
    MacCreator --> MacButton["MacButton"]
~~~

Mũi tên đứt nét biểu diễn việc lớp con cung cấp cách triển khai cho factory method. Khi `show()` gọi `createButton()` trên đối tượng `WindowsDialog`, cơ chế đa hình sẽ dùng phương thức được ghi đè của `WindowsDialog`.

### 3.3. Ví dụ Java có thể chạy độc lập

Lưu đoạn sau thành `FactoryMethodDemo.java`:

~~~java
public class FactoryMethodDemo {
    interface Button {
        String render();
    }

    static final class WindowsButton implements Button {
        @Override
        public String render() {
            return "Windows Button";
        }
    }

    static final class MacButton implements Button {
        @Override
        public String render() {
            return "macOS Button";
        }
    }

    // Creator: tổ chức quy trình; không biết lớp Button cụ thể.
    static abstract class Dialog {
        public final void show() {
            Button button = createButton();  // Factory Method
            System.out.println("Dialog shows " + button.render());
        }

        protected abstract Button createButton();
    }

    // ConcreteCreator của Windows.
    static final class WindowsDialog extends Dialog {
        @Override
        protected Button createButton() {
            return new WindowsButton();
        }
    }

    // ConcreteCreator của macOS.
    static final class MacDialog extends Dialog {
        @Override
        protected Button createButton() {
            return new MacButton();
        }
    }

    public static void main(String[] args) {
        Dialog dialog = args.length > 0
                && "mac".equalsIgnoreCase(args[0])
                ? new MacDialog()
                : new WindowsDialog();

        dialog.show();
    }
}
~~~

Chạy:

~~~bash
javac FactoryMethodDemo.java
java FactoryMethodDemo
# Dialog shows Windows Button

java FactoryMethodDemo mac
# Dialog shows macOS Button
~~~

**Điểm cần quan sát:** `Dialog.show()` là quy trình chung; `createButton()` là điểm có thể thay đổi. Lớp con quyết định loại Button mà quy trình sẽ sử dụng. Việc `main()` lựa chọn một `ConcreteCreator` không làm mất ý nghĩa của Factory Method: quyết định lớp sản phẩm cụ thể vẫn được ủy quyền cho phương thức ghi đè trong creator.

Đoạn mã dùng `render()` trả về chuỗi để minh họa; một thư viện UI thực tế có thể vẽ nút lên màn hình hoặc trả về một đối tượng widget.

## 4. Abstract Factory: chọn một họ sản phẩm tương thích

### 4.1. Vấn đề và mục tiêu

Giờ giả sử `LoginScreen` luôn cần **hai loại sản phẩm**: Button để đăng nhập và Checkbox để ghi nhớ tài khoản. Nếu đang dùng giao diện Windows, cả hai phải là bản Windows; nếu đang dùng giao diện macOS, cả hai phải là bản macOS.

Các tổ hợp kỳ vọng:

| Họ được chọn | Button | Checkbox |
| --- | --- | --- |
| Windows | `WindowsButton` | `WindowsCheckbox` |
| macOS | `MacButton` | `MacCheckbox` |

Mục tiêu không còn giới hạn ở điểm tạo Button trong một quy trình. Ta cần một **hợp đồng cung cấp đồng bộ các sản phẩm** của một họ, để client không tự quyết định lớp cụ thể cho từng thành phần.

### 4.2. Các vai trò trong cấu trúc

| Vai trò | Ví dụ |
| --- | --- |
| `AbstractProductA`, `AbstractProductB` | `Button`, `Checkbox` |
| `ConcreteProduct` | `WindowsButton`, `WindowsCheckbox`, `MacButton`, `MacCheckbox` |
| `AbstractFactory` | `WidgetFactory` khai báo `createButton()` và `createCheckbox()` |
| `ConcreteFactory` | `WindowsWidgetFactory`, `MacWidgetFactory` |
| Client | `LoginScreen` được cấp một `WidgetFactory` |

~~~mermaid
flowchart TB
    Client["LoginScreen"] --> AF["WidgetFactory"]
    AF --> TypeA["createButton(): Button"]
    AF --> TypeB["createCheckbox(): Checkbox"]
    W["WindowsWidgetFactory"] -. "triển khai" .-> AF
    M["MacWidgetFactory"] -. "triển khai" .-> AF
    W --> WB["WindowsButton"]
    W --> WC["WindowsCheckbox"]
    M --> MB["MacButton"]
    M --> MC["MacCheckbox"]
~~~

**Mỗi concrete factory đại diện cho một hàng trong ma trận họ sản phẩm.** Client chỉ nhận một đối tượng `WidgetFactory`. Hai thao tác `createButton()` và `createCheckbox()` trên factory đó trả về các biến thể thuộc cùng họ.

### 4.3. Ví dụ Java có thể chạy độc lập

Lưu đoạn sau thành `AbstractFactoryDemo.java`:

~~~java
public class AbstractFactoryDemo {
    interface Button {
        String render();
    }

    interface Checkbox {
        String render();
    }

    static final class WindowsButton implements Button {
        @Override
        public String render() {
            return "Windows Button";
        }
    }

    static final class MacButton implements Button {
        @Override
        public String render() {
            return "macOS Button";
        }
    }

    static final class WindowsCheckbox implements Checkbox {
        @Override
        public String render() {
            return "Windows Checkbox";
        }
    }

    static final class MacCheckbox implements Checkbox {
        @Override
        public String render() {
            return "macOS Checkbox";
        }
    }

    // AbstractFactory: mô tả các loại sản phẩm trong một họ.
    interface WidgetFactory {
        Button createButton();
        Checkbox createCheckbox();
    }

    static final class WindowsWidgetFactory implements WidgetFactory {
        @Override
        public Button createButton() {
            return new WindowsButton();
        }

        @Override
        public Checkbox createCheckbox() {
            return new WindowsCheckbox();
        }
    }

    static final class MacWidgetFactory implements WidgetFactory {
        @Override
        public Button createButton() {
            return new MacButton();
        }

        @Override
        public Checkbox createCheckbox() {
            return new MacCheckbox();
        }
    }

    // Client biết các giao diện chung, không biết lớp widget cụ thể.
    static final class LoginScreen {
        private final Button loginButton;
        private final Checkbox rememberMe;

        LoginScreen(WidgetFactory factory) {
            loginButton = factory.createButton();
            rememberMe = factory.createCheckbox();
        }

        void render() {
            System.out.println(loginButton.render());
            System.out.println(rememberMe.render());
        }
    }

    public static void main(String[] args) {
        WidgetFactory factory = args.length > 0
                && "mac".equalsIgnoreCase(args[0])
                ? new MacWidgetFactory()
                : new WindowsWidgetFactory();

        new LoginScreen(factory).render();
    }
}
~~~

Chạy:

~~~bash
javac AbstractFactoryDemo.java
java AbstractFactoryDemo
# Windows Button
# Windows Checkbox

java AbstractFactoryDemo mac
# macOS Button
# macOS Checkbox
~~~

**Điểm cần quan sát:** `LoginScreen` được truyền **một factory** rồi yêu cầu cả Button và Checkbox từ factory đó. Khi đổi từ `WindowsWidgetFactory` sang `MacWidgetFactory`, toàn bộ họ thành phần thay đổi cùng nhau mà không cần sửa code `LoginScreen`.

Abstract Factory **giúp duy trì** tính tương thích theo họ nhưng không tự động ngăn mọi cách dùng sai. Nếu client cố tình lấy Button từ factory Windows và Checkbox từ factory macOS, nó vẫn có thể trộn họ. Cách thiết kế thông thường là chọn một factory ở điểm khởi tạo ứng dụng (*composition root*) rồi cấp chính factory ấy cho toàn bộ màn hình hoặc phân hệ tương ứng.

## 5. So sánh cấu trúc: kế thừa creator và cấu thành với factory

### Factory Method: thuật toán của creator chứa điểm mở rộng

~~~text
WindowsDialog ──kế thừa──> Dialog
                            ├─ show()                 [quy trình dùng Button]
                            └─ createButton(): Button [điểm mở rộng]

WindowsDialog.createButton() ──> WindowsButton
MacDialog.createButton()     ──> MacButton
~~~

Quan hệ kế thừa quan trọng vì **creator có thể gọi một factory method được lớp con ghi đè**. Quy trình ở lớp cơ sở không phải biết chi tiết cách khởi tạo sản phẩm.

### Abstract Factory: client nhận đối tượng factory

~~~text
LoginScreen ──được cấp──> WidgetFactory
                            ├─ createButton(): Button
                            └─ createCheckbox(): Checkbox

WindowsWidgetFactory ──> WindowsButton  + WindowsCheckbox
MacWidgetFactory     ──> MacButton      + MacCheckbox
~~~

Quan hệ quan trọng ở phía client là **cấu thành/cộng tác với một factory trừu tượng**. Bản thân các factory cụ thể có thể triển khai một interface, kế thừa lớp trừu tượng hoặc được cấu hình bằng cơ chế khác. Bởi vậy, không nên kết luận rằng Abstract Factory “không dùng kế thừa”; điểm phân biệt là **nhiệm vụ cung cấp một họ sản phẩm**.

### Cùng tên phương thức nhưng vai trò khác nhau

Trong cả hai ví dụ đều có `createButton()`:

- Ở **Factory Method**, đó là bước có thể ghi đè nằm trong cấu trúc `Dialog`; `show()` của creator gọi phương thức để hoàn thành quy trình.
- Ở **Abstract Factory**, đó là **một trong nhiều thao tác tạo sản phẩm** được gom trong `WidgetFactory`; client gọi những thao tác trên cùng factory để lấy các sản phẩm tương thích.

Vì vậy, **một phương thức tên `create...` không mặc nhiên là mẫu Factory Method**. Mẫu thiết kế được nhận diện bằng các vai trò và quan hệ trong toàn bộ giải pháp, không phải bằng tên API.

## 6. So sánh phạm vi tạo đối tượng và khả năng mở rộng

Hãy xem ma trận biến thể của UI:

| Họ / loại sản phẩm | Button | Checkbox | TextField (nếu bổ sung) |
| --- | --- | --- | --- |
| Windows | WindowsButton | WindowsCheckbox | WindowsTextField |
| macOS | MacButton | MacCheckbox | MacTextField |
| Linux (nếu bổ sung) | LinuxButton | LinuxCheckbox | LinuxTextField |

Trong **Abstract Factory**, mỗi factory thường đại diện cho **một hàng** (họ Windows/macOS/Linux); các phương thức của factory đại diện cho **các cột** (loại Button/Checkbox/TextField). Trong ví dụ **Factory Method**, điểm mở rộng `Dialog.createButton()` chỉ quyết định một ô trong cột Button của quy trình `Dialog`. Đây là phép hình dung hữu ích, không phải giới hạn bắt buộc rằng một creator tuyệt đối chỉ được khai báo một factory method.

| Tác động của yêu cầu thay đổi | Factory Method | Abstract Factory |
| --- | --- | --- |
| Thêm một biến thể Button cho `Dialog` | Có thể thêm `ConcreteProduct` và `ConcreteCreator` tương ứng; quy trình `Dialog.show()` không đổi | Nếu có họ UI mới, thêm factory cụ thể và các sản phẩm tương ứng trong họ |
| Thêm cả họ Linux (Button + Checkbox) | Nếu nhiều creator độc lập, phải tổ chức các quy tắc lựa chọn của chúng để bảo đảm cùng Linux | Thêm `LinuxWidgetFactory` với các phương thức trả về sản phẩm Linux; cấu hình chọn factory cần hỗ trợ Linux |
| Thêm loại sản phẩm mới `TextField` | Nếu cần một quy trình tạo TextField, có thể phải bổ sung factory method hoặc một hệ creator riêng; không có sẵn hợp đồng cho cả họ | Thêm `createTextField()` vào `WidgetFactory` và triển khai trong **mọi** concrete factory |
| Thay cách dựng một sản phẩm | Ghi đè/cập nhật factory method tại creator tương ứng | Cập nhật thao tác tạo sản phẩm của concrete factory liên quan |
| Thay toàn bộ phong cách UI trong một phân hệ | Cần cơ chế chọn các creator phù hợp nếu có nhiều loại sản phẩm | Cấp factory của họ mới cho client hoặc phân hệ |

Hai nhận xét quan trọng:

1. **Factory Method không bị giới hạn cứng ở “một lớp sản phẩm duy nhất”.** Một creator có thể khai báo nhiều factory methods, và nhiều creator có thể phối hợp. Điểm cốt lõi vẫn là lớp con quyết định việc tạo sản phẩm tại những điểm mở rộng của creator.
2. **Abstract Factory không khiến việc mở rộng mọi chiều đều dễ.** Nó thuận tiện khi thêm *họ sản phẩm* mới tuân theo hợp đồng đã có, nhưng có chi phí cao hơn khi thêm một *loại sản phẩm* mới vào hợp đồng chung vì mọi concrete factory đều phải cập nhật.

## 7. Hai mẫu có thể kết hợp như thế nào?

Trong thiết kế kinh điển, **Abstract Factory thường có thể được triển khai bằng Factory Methods**: một lớp factory trừu tượng khai báo các thao tác tạo sản phẩm và các factory con ghi đè chúng.

~~~java
abstract class WidgetFactory {
    abstract Button createButton();
    abstract Checkbox createCheckbox();
}

final class WindowsWidgetFactory extends WidgetFactory {
    @Override
    Button createButton() {
        return new WindowsButton();
    }

    @Override
    Checkbox createCheckbox() {
        return new WindowsCheckbox();
    }
}
~~~

*Giả sử* các giao diện `Button`, `Checkbox` và các lớp sản phẩm cụ thể đã được khai báo như ở ví dụ trước. Ở đây, các phương thức tạo được triển khai bằng cách ghi đè trong lớp con; đồng thời, toàn bộ lớp `WidgetFactory` đại diện cho **hợp đồng tạo một họ sản phẩm**.

Điều này không có nghĩa hai mẫu là một:

- **Abstract Factory** mô tả *bộ khả năng tạo nhiều sản phẩm liên quan* mà client cần.
- **Factory Method** mô tả *một kỹ thuật phân quyền quyết định khởi tạo cho lớp con*.

Một Abstract Factory khác cũng có thể dùng **composition**, registry, prototype hoặc các constructor được ủy quyền để tạo sản phẩm. Kế thừa và ghi đè factory method là một cách triển khai phổ biến, nhưng không phải là điều kiện duy nhất để có Abstract Factory.

## 8. Hướng dẫn lựa chọn mẫu theo tình huống

### Chọn Factory Method khi

- Có **một quy trình hoặc hành vi chung** cần tạo đối tượng ở một bước nhất định.
- Cần cho phép các lớp con lựa chọn biến thể sản phẩm được tạo tại bước đó.
- Việc thay đổi sản phẩm không nhất thiết đòi hỏi đồng bộ nhiều loại sản phẩm thuộc cùng một họ.

**Ví dụ:** `Dialog.show()` luôn thực hiện cùng một quy trình, còn `WindowsDialog` và `MacDialog` quyết định Button cụ thể.

### Chọn Abstract Factory khi

- Có **từ hai loại sản phẩm trở lên** cần cung cấp theo **những họ nhất quán**.
- Mã client cần đổi cả họ sản phẩm khi cấu hình môi trường, nền tảng hoặc chủ đề thay đổi.
- Việc trộn các sản phẩm từ các họ khác nhau gây lỗi thiết kế, hành vi hoặc trải nghiệm.

**Ví dụ:** `LoginScreen` cần đồng thời `WindowsButton` + `WindowsCheckbox` hoặc `MacButton` + `MacCheckbox`, và trong tương lai thêm TextField.

### Khi chưa cần cả hai

Nếu ứng dụng chỉ tạo một đối tượng đơn giản và không có điểm mở rộng theo kế thừa hay ràng buộc họ sản phẩm, gọi constructor trực tiếp có thể rõ ràng hơn. Nếu chỉ muốn tập trung một câu lệnh `switch` hoặc `if` để chọn một lớp cụ thể, một **simple factory** (hàm/lớp tạo đơn giản) có thể đủ; simple factory tự nó không đồng nghĩa với Factory Method theo cấu trúc GoF.

Nếu Button và Checkbox chỉ khác màu sắc/kiểu chữ và có thể thay bằng một theme hoặc stylesheet, cần đánh giá giải pháp theme trước khi tạo các lớp sản phẩm theo họ.

## 9. Những ngộ nhận dễ gặp khi học và thiết kế

| Ngộ nhận | Cách hiểu chính xác |
| --- | --- |
| “Có phương thức `createButton()` thì chắc chắn là Factory Method.” | Tên phương thức không xác định mẫu; Factory Method có quan hệ creator–subclass và một bước khởi tạo có thể ghi đè |
| “Abstract Factory chỉ là Factory Method với nhiều hàm `create`.” | Abstract Factory đặt trọng tâm vào **một họ sản phẩm liên quan**, cách chọn họ và tính nhất quán của client |
| “Factory Method luôn chỉ tạo đúng một đối tượng.” | Một factory method có thể được gọi nhiều lần; một creator cũng có thể khai báo nhiều factory methods |
| “Abstract Factory tự động cấm trộn họ ở thời điểm biên dịch.” | Thường không. Client cần được cấp đúng factory và sử dụng nhất quán; kiểu thông thường chưa tự mã hóa mọi ràng buộc họ |
| “Thêm TextField vào Abstract Factory không ảnh hưởng code cũ.” | Nếu mở rộng interface factory, các concrete factory hiện hữu đều cần hỗ trợ `createTextField()` |
| “Hai mẫu loại trừ nhau.” | Chúng có thể cộng tác: Abstract Factory cung cấp hợp đồng họ, Factory Methods có thể là cơ chế triển khai các thao tác tạo |
| “Một factory có `switch(platform)` luôn là Abstract Factory.” | Cần xét liệu nó cung cấp **các loại sản phẩm có quan hệ theo họ** hay chỉ là một hàm tạo sản phẩm đơn lẻ |

## 10. Bài tập nhận diện và đáp án giải thích

**Tình huống 1 — Xuất báo cáo.** Lớp cơ sở `ReportGenerator` có quy trình `generate()` bất biến, nhưng lớp con `PdfReportGenerator` tạo một `PdfDocument`, còn `HtmlReportGenerator` tạo một `HtmlDocument` tại bước khởi tạo tài liệu.

**Nhận định:** Phù hợp **Factory Method**, vì `generate()` là quy trình của creator và lớp con quyết định sản phẩm được tạo tại một bước trong quy trình.

**Tình huống 2 — Bộ giao diện chủ đề.** Ứng dụng bán hàng hỗ trợ giao diện “Classic” và “Modern”. Mỗi màn hình phải nhận đồng bộ `Button`, `Checkbox` và `TextField` của cùng một chủ đề.

**Nhận định:** Phù hợp **Abstract Factory**, vì cần chọn một họ rồi cung cấp nhiều loại đối tượng cùng thuộc họ đó.

**Tình huống 3 — Tạo một kết nối.** Hàm `openConnection(config)` kiểm tra giá trị cấu hình và trả về một `Connection` thích hợp. Không có phân cấp creator và không có họ sản phẩm liên quan.

**Nhận định:** Chỉ riêng mô tả này phù hợp với một **simple factory** hơn; chưa đủ chứng cứ để nhận diện Factory Method hoặc Abstract Factory theo cấu trúc GoF.

**Tình huống 4 — Giao diện nhiều nền tảng kết hợp quy trình.** `LoginScreen` dùng một factory được cấp từ đầu để tạo Button/Checkbox cùng nền tảng. Sau đó, một lớp cơ sở `Dialog` dùng `createButton()` được lớp con ghi đè trong quy trình `show()`.

**Nhận định:** Cùng ứng dụng có thể có **Abstract Factory** (cấp họ widget cho `LoginScreen`) và **Factory Method** (điểm mở rộng trong quy trình của `Dialog`); không cần ép mọi công đoạn về một mẫu.

### Câu hỏi tự kiểm tra

1. Trong ví dụ `Dialog`, phương thức nào là điểm mở rộng và phương thức nào chứa quy trình chung?
2. Vì sao cấp **cùng một** `WidgetFactory` cho `LoginScreen` giúp giảm nguy cơ trộn WindowsButton với MacCheckbox?
3. Nếu thêm Linux nhưng không thêm loại widget mới, thay đổi thường tập trung ở đâu trong Abstract Factory?
4. Nếu thêm `Slider` vào mọi họ, interface factory và các concrete factory chịu ảnh hưởng như thế nào?
5. Việc có hai phương thức `create...` đã đủ chứng minh một thiết kế là Abstract Factory chưa? Hãy giải thích theo quan hệ giữa các sản phẩm.

Khi phân biệt hai mẫu, hãy bắt đầu từ **ranh giới trách nhiệm tạo đối tượng**. Nếu câu hỏi là “*Lớp con nào quyết định sản phẩm cho bước này của quy trình?*”, nghĩ tới **Factory Method**. Nếu câu hỏi là “*Factory nào cung cấp toàn bộ các sản phẩm tương thích của họ đã chọn?*”, nghĩ tới **Abstract Factory**.
