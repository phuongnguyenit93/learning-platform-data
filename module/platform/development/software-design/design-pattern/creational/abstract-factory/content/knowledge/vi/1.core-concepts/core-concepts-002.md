# Ý nghĩa của việc tạo đối tượng qua interface thay vì phụ thuộc lớp triển khai

## 1. Vì sao đây là ý tưởng quan trọng của Abstract Factory?

Trong một ứng dụng có nhiều cách hiển thị giao diện, lớp màn hình cần một nút bấm và một hộp thoại. Có thể viết mã tạo trực tiếp:

~~~java
Button button = new DesktopButton();
Dialog dialog = new DesktopDialog();
~~~

Giả sử sau đó sản phẩm phải chạy trên thiết bị di động. Nếu mỗi màn hình đều tự gọi `new DesktopButton()` và `new DesktopDialog()`, các màn hình ấy phải được sửa để chọn lớp tương ứng với môi trường mới. Khi thêm nhiều thành phần, số vị trí cần sửa và nguy cơ phối hợp nhầm biến thể càng tăng.

**Ý tưởng cốt lõi của Abstract Factory:** mã sử dụng yêu cầu sản phẩm **thông qua một interface của factory**, nhận kết quả **dưới dạng interface sản phẩm**, còn factory cụ thể chịu trách nhiệm chọn và khởi tạo các lớp triển khai.

~~~java
Button button = factory.createButton();
Dialog dialog = factory.createDialog();
~~~

Lớp màn hình không phải biết `DesktopButton`, `MobileButton` hay constructor của chúng. Nó chỉ cần biết có thể gọi `createButton()`, `createDialog()` và làm việc với kết quả theo hợp đồng `Button`, `Dialog`.

Trong bài học về **Abstract Factory** thuộc nhóm **Creational Design Patterns**, đây là cơ chế giúp cùng một mã sử dụng làm việc với **nhiều họ sản phẩm liên quan** (ví dụ bộ giao diện Desktop và bộ giao diện Mobile) mà không gắn chặt với từng lớp cụ thể.

## 2. Phân biệt interface, lớp triển khai và đối tượng thực

Một số thuật ngữ cần tách bạch:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Interface sản phẩm** (*Abstract Product*) | Cam kết về những thao tác mà client được sử dụng | `Button` có `draw()`; `Dialog` có `open()` |
| **Lớp triển khai sản phẩm** (*Concrete Product*) | Cài đặt hành vi của một biến thể | `DesktopButton`, `MobileDialog` |
| **Interface factory** (*Abstract Factory*) | Hợp đồng về các loại sản phẩm có thể tạo | `WidgetFactory` với `createButton()`, `createDialog()` |
| **Lớp triển khai factory** (*Concrete Factory*) | Tạo những lớp sản phẩm cụ thể thuộc cùng họ | `DesktopWidgetFactory`, `MobileWidgetFactory` |
| **Đối tượng runtime** | Instance thật nhận được từ factory; luôn có một lớp triển khai cụ thể | Một instance `MobileButton` được giữ trong biến kiểu `Button` |

Ví dụ:

~~~java
interface Button {
    void draw();
}

class MobileButton implements Button {
    @Override
    public void draw() {
        System.out.println("Vẽ nút cho điện thoại");
    }
}

Button button = new MobileButton();
button.draw();
~~~

Biến `button` có **kiểu khai báo** là `Button`, nhưng đối tượng được tạo có **kiểu runtime** là `MobileButton`. Khi gọi `draw()`, Java thực thi phương thức tương ứng với đối tượng thật (*đa hình*).

**Interface không trực tiếp khởi tạo đối tượng.** Ví dụ, không thể viết `new Button()` để tạo instance của một interface theo cách thông thường. Đâu đó trong chương trình vẫn phải có mã tạo đối tượng cụ thể (chẳng hạn `new MobileButton()`). Abstract Factory **chuyển trách nhiệm đó sang concrete factory**, để phần lớn mã sử dụng không phải biết những constructor này.

### 2.1. Có hai lớp trừu tượng cùng tham gia

Abstract Factory thường dùng **hai tầng interface**, mỗi tầng giải quyết một câu hỏi riêng:

1. **Interface factory:** *Làm thế nào tôi yêu cầu một bộ sản phẩm?* Ví dụ `WidgetFactory.createButton()`.
2. **Interface sản phẩm:** *Sau khi nhận sản phẩm, tôi được làm gì với nó?* Ví dụ `Button.draw()`.

Chỉ có interface sản phẩm chưa đủ để che giấu khâu khởi tạo nếu client vẫn viết `new DesktopButton()`. Ngược lại, chỉ có interface factory cũng chưa giải phóng client khỏi lớp cụ thể nếu phương thức factory trả về trực tiếp `DesktopButton` và client phụ thuộc vào các API riêng của lớp đó.

## 3. So sánh hai cách thiết kế phụ thuộc

### 3.1. Client phụ thuộc trực tiếp vào lớp triển khai

~~~java
class CheckoutPage {
    void render() {
        DesktopButton button = new DesktopButton();
        DesktopDialog dialog = new DesktopDialog();

        button.draw();
        dialog.open();
    }
}
~~~

*Đoạn mã trên minh họa thiết kế phụ thuộc trực tiếp; giả sử `DesktopButton` và `DesktopDialog` đã được định nghĩa.*

`CheckoutPage` vừa quyết định **tạo lớp nào**, vừa quyết định **sử dụng sản phẩm thế nào**. Nó phải sửa khi lựa chọn lớp thay đổi; khó dùng lại nguyên vẹn cho nền tảng khác. Nếu một lớp cụ thể đòi hỏi thêm tham số khởi tạo, constructor đó cũng có thể kéo thay đổi vào nhiều màn hình.

### 3.2. Client phụ thuộc vào hợp đồng

~~~java
class CheckoutPage {
    private final WidgetFactory factory;

    CheckoutPage(WidgetFactory factory) {
        this.factory = factory;
    }

    void render() {
        Button button = factory.createButton();
        Dialog dialog = factory.createDialog();

        button.draw();
        dialog.open();
    }
}
~~~

Client không gọi constructor của concrete product. Một đối tượng `WidgetFactory` được **truyền từ bên ngoài** qua constructor (*constructor injection*), cho phép cùng một `CheckoutPage` sử dụng bất kỳ factory nào tuân thủ hợp đồng.

Điểm thay đổi then chốt là **hướng phụ thuộc trong mã nguồn**:

~~~mermaid
flowchart TB
    Client["CheckoutPage"] --> AF["WidgetFactory (interface)"]
    Client --> BP["Button (interface)"]
    Client --> DP["Dialog (interface)"]
    DesktopFactory["DesktopWidgetFactory"] -. "implements" .-> AF
    MobileFactory["MobileWidgetFactory"] -. "implements" .-> AF
    DesktopFactory --> DesktopProducts["DesktopButton + DesktopDialog"]
    MobileFactory --> MobileProducts["MobileButton + MobileDialog"]
~~~

`CheckoutPage` chỉ biết các interface; lớp factory cụ thể và các lớp sản phẩm cụ thể nằm ở phía triển khai. Một phần khác của ứng dụng chịu trách nhiệm **chọn và cung cấp** concrete factory cho `CheckoutPage`.

## 4. Ví dụ Java tự chạy: một client, hai họ sản phẩm

Ứng dụng minh họa có hai loại widget (`Button`, `Dialog`) và hai họ triển khai:

- **Desktop:** `DesktopButton`, `DesktopDialog`.
- **Mobile:** `MobileButton`, `MobileDialog`.

Mọi phương thức tạo sản phẩm nằm trong interface `WidgetFactory`. Mỗi concrete factory triển khai đầy đủ phương thức đó cho **cùng một họ**.

Lưu toàn bộ mã sau trong tệp `InterfaceFactoryDemo.java`:

~~~java
// Hai giao diện sản phẩm: hành vi client cần dùng.
interface Button {
    void draw();
}

interface Dialog {
    void open();
}

// Interface factory: client không cần biết class nào được new.
interface WidgetFactory {
    Button createButton();
    Dialog createDialog();
}

// Họ sản phẩm Desktop.
class DesktopButton implements Button {
    @Override
    public void draw() {
        System.out.println("Nút dành cho Desktop");
    }
}

class DesktopDialog implements Dialog {
    @Override
    public void open() {
        System.out.println("Hộp thoại dành cho Desktop");
    }
}

// Họ sản phẩm Mobile.
class MobileButton implements Button {
    @Override
    public void draw() {
        System.out.println("Nút dành cho Mobile");
    }
}

class MobileDialog implements Dialog {
    @Override
    public void open() {
        System.out.println("Hộp thoại dành cho Mobile");
    }
}

// Mỗi factory chịu trách nhiệm tạo trọn họ tương ứng.
class DesktopWidgetFactory implements WidgetFactory {
    @Override
    public Button createButton() {
        return new DesktopButton();
    }

    @Override
    public Dialog createDialog() {
        return new DesktopDialog();
    }
}

class MobileWidgetFactory implements WidgetFactory {
    @Override
    public Button createButton() {
        return new MobileButton();
    }

    @Override
    public Dialog createDialog() {
        return new MobileDialog();
    }
}

// Client chỉ biết WidgetFactory, Button và Dialog.
class CheckoutPage {
    private final WidgetFactory factory;

    CheckoutPage(WidgetFactory factory) {
        this.factory = factory;
    }

    void render() {
        Button button = factory.createButton();
        Dialog dialog = factory.createDialog();

        button.draw();
        dialog.open();
    }
}

public class InterfaceFactoryDemo {
    public static void main(String[] args) {
        // Nơi lắp ghép ứng dụng: chọn lớp cụ thể một lần.
        boolean useMobile =
                args.length > 0 && "mobile".equalsIgnoreCase(args[0]);

        WidgetFactory factory = useMobile
                ? new MobileWidgetFactory()
                : new DesktopWidgetFactory();

        CheckoutPage page = new CheckoutPage(factory);
        page.render();
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 InterfaceFactoryDemo.java
java InterfaceFactoryDemo
java InterfaceFactoryDemo mobile
~~~

Kết quả của hai lệnh chạy, theo thứ tự:

~~~text
Nút dành cho Desktop
Hộp thoại dành cho Desktop

Nút dành cho Mobile
Hộp thoại dành cho Mobile
~~~

### 4.1. Chính xác điều gì diễn ra lúc chạy?

1. `main()` xem tham số để chọn `DesktopWidgetFactory` hoặc `MobileWidgetFactory`.
2. Biến `factory` có kiểu khai báo là `WidgetFactory`, dù instance thật thuộc một trong hai lớp triển khai.
3. `CheckoutPage` nhận factory qua constructor. Phần này không kiểm tra `if (mobile)` và không tham chiếu tới `DesktopButton` hay `MobileDialog`.
4. Lệnh `factory.createButton()` được thực thi bởi **concrete factory thực tế** và trả về một instance cụ thể.
5. `CheckoutPage` giữ sản phẩm dưới kiểu interface `Button` rồi gọi `draw()`; Java chọn cách thực thi tương ứng với concrete product.
6. `createDialog()` hoạt động tương tự. Vì cả hai sản phẩm được lấy qua **cùng một factory** đúng quy ước, chúng thuộc cùng họ.

Lưu ý: `new MobileWidgetFactory()` và `new DesktopWidgetFactory()` vẫn xuất hiện trong `main()`. Đó là điều bình thường. **Việc chọn implementation phải diễn ra ở một ranh giới nào đó**, thường là nơi lắp ghép ứng dụng (*composition root*) hoặc cấu hình dependency injection.

### 4.2. Vì sao interface của factory nên trả về interface sản phẩm?

Hãy so sánh hai chữ ký:

~~~java
// Phụ thuộc vào implementation trong API.
MobileButton createButton();

// Che giấu implementation trong API.
Button createButton();
~~~

Nếu API công khai trả về `MobileButton`, phần gọi có thể bắt đầu sử dụng những tính năng chỉ có trên lớp Mobile. Khi đổi sang Desktop, mã đó sẽ gặp vấn đề. Trả về `Button` giúp client chỉ sử dụng hành vi **chung, ổn định và cần thiết**. Phương thức trong concrete factory vẫn có thể trả về `new MobileButton()` vì `MobileButton` triển khai `Button`.

## 5. Những lợi ích thực tế của việc phụ thuộc vào interface

### 5.1. Đổi họ sản phẩm mà không viết lại client

Khi chuyển Desktop sang Mobile, sự thay đổi nằm ở nơi chọn concrete factory. Miễn là `CheckoutPage` dùng đúng các phương thức trong hợp đồng, mã màn hình không cần biết chọn biến thể nào.

Đây là cách áp dụng ý tưởng **lập trình hướng tới interface, không hướng tới implementation**: phần sử dụng mô tả *cần những khả năng gì*, phần triển khai quyết định *thực hiện khả năng ấy bằng cách nào*.

### 5.2. Giảm lan truyền thay đổi và tập trung quy tắc khởi tạo

Giả sử `MobileButton` có constructor mới cần các thông số về màu sắc hoặc kích thước. Với factory, có thể điều chỉnh `MobileWidgetFactory.createButton()` để cung cấp tham số phù hợp. Client không phải biết chi tiết khởi tạo đó, miễn là giao diện công khai giữ nguyên.

Nếu client gọi constructor trực tiếp ở nhiều nơi, cùng một thay đổi có thể phải sửa nhiều màn hình. Factory giúp **cô lập thay đổi trong cách tạo đối tượng**.

### 5.3. Phối hợp sản phẩm liên quan nhất quán hơn

Đôi khi một nút Desktop cần đi cùng hộp thoại Desktop, hoặc hai client của cùng một dịch vụ phải dùng chung cấu hình. Một concrete factory có thể tập trung quy tắc **tạo đúng những biến thể thuộc cùng họ**.

Tuy nhiên, đây là tính nhất quán **do thiết kế và cách sử dụng factory bảo đảm**, không phải do interface tự chứng minh. Nếu ai đó cài đặt `MobileWidgetFactory.createDialog()` bằng `new DesktopDialog()`, Java vẫn có thể biên dịch vì kiểu trả về vẫn là `Dialog`. Do đó, các ràng buộc tương thích quan trọng nên được kiểm tra bằng test hoặc bằng các cấu trúc kiểu chặt chẽ hơn khi cần.

### 5.4. Dễ thay thế dependency khi kiểm thử

Vì `CheckoutPage` nhận một `WidgetFactory`, có thể truyền một fake factory để quan sát xem nó yêu cầu những sản phẩm nào. Ví dụ, cùng với các interface ở trên, có thể thêm:

~~~java
class CountingWidgetFactory implements WidgetFactory {
    int buttonsCreated;
    int dialogsCreated;

    @Override
    public Button createButton() {
        buttonsCreated++;
        return () -> {}; // Button giả: không vẽ thật.
    }

    @Override
    public Dialog createDialog() {
        dialogsCreated++;
        return () -> {}; // Dialog giả: không mở thật.
    }
}
~~~

Một tình huống kiểm thử minh họa:

~~~java
CountingWidgetFactory fake = new CountingWidgetFactory();
new CheckoutPage(fake).render();

if (fake.buttonsCreated != 1 || fake.dialogsCreated != 1) {
    throw new AssertionError("CheckoutPage phải tạo đủ hai widget");
}
~~~

Ở đây có thể xác minh **hành vi tương tác của client với factory** mà không cần tạo widget Desktop/Mobile thật. Cách làm này hữu ích khi concrete product có phụ thuộc phức tạp như hệ điều hành, cơ sở dữ liệu hoặc kết nối mạng. Trong dự án thực, test vẫn phải chọn các khẳng định phù hợp với hành vi cần bảo đảm; chỉ đếm số lượt tạo không thay thế kiểm thử tích hợp.

### 5.5. Hỗ trợ Dependency Inversion

Theo **Dependency Inversion Principle (DIP)**, phần logic cấp cao nên phụ thuộc vào các trừu tượng phù hợp thay vì vào chi tiết triển khai cấp thấp. Trong ví dụ:

- `CheckoutPage` là client cần vẽ widget.
- `WidgetFactory`, `Button` và `Dialog` là các hợp đồng client cần.
- `DesktopWidgetFactory`, `MobileWidgetFactory` và sản phẩm cụ thể là phần chi tiết có thể thay thế.

Cả client và các concrete factory cùng tuân theo các hợp đồng. Việc **truyền factory qua constructor** là một kỹ thuật *dependency injection* giúp nối chúng lại; còn DIP là **nguyên tắc thiết kế quan hệ phụ thuộc**. Hai khái niệm liên quan nhưng không đồng nghĩa, và Abstract Factory không bắt buộc phải dùng framework dependency injection.

## 6. Những thay đổi nào dễ, những thay đổi nào vẫn khó?

| Tình huống thay đổi | Ảnh hưởng khi dùng Abstract Factory qua interface |
| --- | --- |
| Đổi Desktop thành Mobile | Thay factory được cung cấp cho client; client giữ nguyên nếu hợp đồng giữ nguyên |
| Thêm một họ Tablet | Thêm `TabletButton`, `TabletDialog`, `TabletWidgetFactory` và cách chọn factory; client thường giữ nguyên |
| Đổi constructor của `MobileButton` | Thường chỉ cần sửa logic tạo trong `MobileWidgetFactory` |
| Thêm một loại sản phẩm `Checkbox` | Cần thêm interface `Checkbox`, phương thức `createCheckbox()` vào factory interface và triển khai ở các concrete factory |
| Client cần tính năng đặc thù chỉ có trên Mobile | Có thể phải thay đổi thiết kế hợp đồng, tách chức năng, hoặc chấp nhận sự phụ thuộc riêng ở phạm vi hợp lý |
| Muốn widget đã tạo tự đổi giao diện khi đổi factory | Factory không tự cập nhật instance cũ; cần tạo lại widget hoặc thiết kế cơ chế cập nhật riêng |

**Điểm đánh đổi:** Abstract Factory thường hỗ trợ **mở rộng theo họ sản phẩm** tốt hơn **mở rộng theo loại sản phẩm**. Khi thêm `createCheckbox()` vào interface, tất cả concrete factory đang triển khai interface đó phải cung cấp phương thức mới.

Interface tạo ra một **ranh giới thay đổi hữu ích**, nhưng không biến mọi thay đổi thành miễn phí.

## 7. Khi nào tạo qua interface đem lại giá trị?

Cách tiếp cận này đặc biệt phù hợp khi có các đặc điểm sau:

- Cùng một logic cần hoạt động với **nhiều biến thể triển khai** theo môi trường, cấu hình hoặc nền tảng.
- Có **nhiều loại đối tượng liên quan** và yêu cầu sử dụng các biến thể tương thích như một bộ.
- Chi tiết khởi tạo phức tạp, thay đổi tương đối độc lập với hành vi mà client cần.
- Cần cung cấp triển khai giả hoặc thay thế dependency trong kiểm thử.
- Muốn một interface ổn định đóng vai trò ranh giới giữa logic nghiệp vụ và hệ thống bên ngoài.

Ví dụ ứng dụng khác: một dịch vụ báo cáo có thể chọn bộ `ReportWriter` và `ReportReader` cùng dùng định dạng JSON hoặc XML; một ứng dụng đa nền tảng có thể chọn bộ nút bấm, hộp thoại và thanh điều hướng của Windows hoặc macOS. Quan trọng là nhu cầu **thay trọn một họ có cùng tập vai trò**.

Nếu chương trình nhỏ, chỉ có một lớp đơn giản và không cần biến thể, việc tạo interface cùng nhiều factory có thể làm tăng số lượng mã và khó đọc hơn. **Không có quy tắc rằng mọi câu lệnh `new` đều phải được thay bằng factory.**

## 8. Những nhầm lẫn dễ gặp

**Nhầm lẫn 1 — «Dùng interface nghĩa là không còn lớp cụ thể».** Sai. Runtime luôn cần instance của lớp triển khai. Interface chỉ giới hạn điều client cần biết và cách client tương tác.

**Nhầm lẫn 2 — «Có interface sản phẩm là đã dùng Abstract Factory».** Chưa đủ. Nếu client vẫn tự quyết định `new DesktopButton()`, nó vẫn phụ thuộc vào chi tiết khởi tạo. Cấu trúc Abstract Factory cần thêm hợp đồng tạo **các loại sản phẩm trong một họ** và những concrete factory triển khai hợp đồng đó.

**Nhầm lẫn 3 — «Interface bảo đảm các sản phẩm chắc chắn tương thích».** Không tự động. `Button` và `Dialog` chỉ mô tả hành vi. Factory cần được triển khai nhất quán; các quy tắc mạnh hơn về khả năng kết hợp đôi khi cần kiểm tra bổ sung.

**Nhầm lẫn 4 — «Mọi nơi trong ứng dụng đều tuyệt đối không được thấy class cụ thể».** Không cần thiết. Nơi lắp ghép ứng dụng phải biết chọn implementation nào hoặc phải ủy quyền việc này cho cấu hình/DI container. Trọng tâm là **giới hạn phạm vi phần mã phụ thuộc vào implementation**.

**Nhầm lẫn 5 — «Interface giúp thay đổi implementation ngay trên object đang tồn tại».** Không. Đổi concrete factory chỉ ảnh hưởng các lần tạo sản phẩm tiếp theo, trừ khi ứng dụng chủ động thay thế các instance cũ hoặc xây dựng cơ chế cập nhật riêng.

**Nhầm lẫn 6 — «Interface luôn tốt hơn abstract class».** Không phải trong mọi trường hợp. Interface phù hợp khi cần cam kết khả năng và nhiều implementation độc lập; abstract class có thể hữu ích khi các triển khai cần chia sẻ trạng thái hoặc hành vi. Java cho phép một factory contract dùng interface hoặc abstract class tùy yêu cầu cụ thể.

## 9. Tự kiểm tra mức hiểu

**Câu hỏi 1:** Nếu `WidgetFactory.createButton()` trả về kiểu `Button`, liệu factory có thể tạo `new DesktopButton()` không?

**Trả lời:** Có, vì `DesktopButton implements Button`. Kiểu công khai cho client là `Button`, còn kiểu đối tượng thực là `DesktopButton`.

**Câu hỏi 2:** Khi muốn chạy `CheckoutPage` trên Mobile, có bắt buộc sửa class `CheckoutPage` không?

**Trả lời:** Không, miễn là nó chỉ sử dụng hợp đồng `WidgetFactory`/`Button`/`Dialog`. Phần khởi tạo ứng dụng chỉ cần truyền `MobileWidgetFactory` thay cho `DesktopWidgetFactory`.

**Câu hỏi 3:** Vì sao không để `CheckoutPage` tự chọn `MobileWidgetFactory` bằng câu lệnh `if`?

**Trả lời:** Làm vậy vẫn có thể chạy nhưng sẽ đưa chi tiết lựa chọn implementation trở lại client. Nếu nhiều client cùng cần lựa chọn này, logic cấu hình dễ bị lặp và khó thay đổi. Truyền factory từ ngoài giúp giữ trách nhiệm lắp ghép tại một vị trí phù hợp.

**Câu hỏi 4:** Thêm phương thức `createCheckbox()` vào `WidgetFactory` có hoàn toàn không ảnh hưởng mã cũ không?

**Trả lời:** Không. Các concrete factory triển khai `WidgetFactory` sẽ phải bổ sung phương thức mới. Những client không dùng checkbox thường không cần sửa, nhưng hợp đồng tạo sản phẩm đã thay đổi.

## 10. Ghi nhớ

Tạo đối tượng **qua interface trong Abstract Factory** có nghĩa là client **yêu cầu sản phẩm bằng các phương thức trừu tượng** và **sử dụng sản phẩm thông qua hợp đồng chung**. Concrete factory vẫn trực tiếp tạo các instance cụ thể, nhưng giữ quyết định khởi tạo đó khỏi mã client.

Giá trị thực tế nằm ở ba mối quan hệ: **client phụ thuộc vào hợp đồng**, **concrete factory quyết định cách tạo**, và **một factory lựa chọn các sản phẩm thuộc cùng họ**. Cách tổ chức này cho phép thay đổi biến thể có kiểm soát, hạn chế lan truyền chi tiết triển khai và hỗ trợ kiểm thử, với chi phí là thêm tầng trừu tượng và phải cập nhật các factory khi mở rộng tập loại sản phẩm.
