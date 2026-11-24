# Khái niệm Abstract Factory và mục tiêu tạo các họ đối tượng liên quan

## 1. Bài toán dẫn đến Abstract Factory

Giả sử một ứng dụng đặt phòng có hai bộ giao diện: **Sáng (Light)** và **Tối (Dark)**. Mỗi bộ gồm nhiều thành phần như nút bấm, hộp thoại, thanh thông báo. Khi người dùng chọn giao diện Tối, các thành phần xuất hiện cùng nhau phải có phong cách Tối; một nút Tối nằm cạnh hộp thoại Sáng là một tổ hợp thiếu nhất quán.

Nếu mã của từng màn hình tự chọn lớp cụ thể, logic tạo đối tượng có thể bị rải rác:

~~~java
Button button = darkMode ? new DarkButton() : new LightButton();
Dialog dialog = darkMode ? new DarkDialog() : new LightDialog();
~~~

Hai dòng trên vẫn hoạt động trong ví dụ nhỏ. Nhưng khi ứng dụng có nhiều màn hình, nhiều loại thành phần và thêm chế độ tương phản cao, mỗi nơi lại phải biết về các lớp cụ thể và lặp lại quy tắc chọn biến thể. Một màn hình có thể vô tình tạo `DarkButton` cùng `LightDialog`.

**Abstract Factory** giải quyết bài toán này bằng cách đưa việc tạo **một họ các đối tượng liên quan** vào cùng một hợp đồng tạo đối tượng. Mã sử dụng chỉ chọn hoặc nhận **một factory** phù hợp, rồi yêu cầu factory đó tạo các thành phần cần thiết.

## 2. Abstract Factory là gì?

**Abstract Factory (Nhà máy trừu tượng)** là một mẫu thiết kế thuộc nhóm **Creational Design Patterns** (mẫu thiết kế khởi tạo). Mẫu này cung cấp **giao diện để tạo ra các họ đối tượng liên quan hoặc phụ thuộc lẫn nhau mà mã sử dụng không phải chỉ định trực tiếp những lớp cụ thể của chúng**.

Có ba ý chính trong định nghĩa:

1. **Tạo đối tượng qua một hợp đồng:** phía sử dụng gọi các phương thức như `createButton()` và `createDialog()` trên interface `UIFactory`, thay vì tự gọi `new LightButton()` tại mọi nơi.
2. **Tạo theo họ:** một factory cụ thể sản xuất các loại sản phẩm thuộc cùng biến thể, ví dụ `LightUIFactory` tạo `LightButton` và `LightDialog`.
3. **Ẩn lớp triển khai khỏi mã sử dụng:** màn hình làm việc với `Button`, `Dialog` và `UIFactory`; lớp cụ thể được quyết định ở phần cấu hình hoặc khởi tạo ứng dụng.

Tên gọi *abstract* đề cập đến **hợp đồng tạo sản phẩm**: lớp sử dụng biết factory **có thể tạo những loại sản phẩm nào**, nhưng không cần biết **chính xác lớp nào sẽ được khởi tạo**. Factory cụ thể vẫn chứa logic khởi tạo thật.

### 2.1. Phân biệt «loại sản phẩm» và «họ sản phẩm»

Hai khái niệm này rất dễ nhầm:

- **Loại sản phẩm (product type):** vai trò hoặc hợp đồng của một đối tượng, chẳng hạn `Button` hay `Dialog`.
- **Biến thể (variant):** cách triển khai một loại sản phẩm, chẳng hạn `LightButton` hoặc `DarkButton`.
- **Họ sản phẩm (product family):** tập hợp các biến thể của **nhiều loại sản phẩm** được thiết kế để sử dụng cùng nhau, chẳng hạn `LightButton` + `LightDialog`.

| Loại sản phẩm | Họ Light | Họ Dark |
| --- | --- | --- |
| `Button` | `LightButton` | `DarkButton` |
| `Dialog` | `LightDialog` | `DarkDialog` |
| Factory tạo cả họ | `LightUIFactory` | `DarkUIFactory` |

**Mục tiêu quan trọng nhất:** khi một màn hình lấy cả `Button` và `Dialog` từ cùng một factory đã chọn, chúng thuộc cùng một họ. Mẫu này giúp **tổ chức và duy trì tính tương thích/nhất quán giữa các đối tượng liên quan**, chứ không đơn thuần là thay `new` bằng một hàm khác.

«Liên quan» có thể nghĩa là cùng giao diện, cùng hệ điều hành, cùng nhà cung cấp hoặc cùng bộ giao thức. «Phụ thuộc lẫn nhau» có thể nghĩa là các sản phẩm phải tương thích về định dạng, cấu hình hoặc cách phối hợp. Các sản phẩm **không bắt buộc** phải tham chiếu trực tiếp đến nhau trong mã nguồn.

## 3. Các vai trò trong cấu trúc Abstract Factory

| Vai trò | Nhiệm vụ | Ví dụ |
| --- | --- | --- |
| **Abstract Factory** | Khai báo phương thức tạo từng *loại* sản phẩm trong họ | `UIFactory` với `createButton()`, `createDialog()` |
| **Concrete Factory** | Quyết định biến thể cụ thể cho **mọi** loại sản phẩm mà factory hỗ trợ | `LightUIFactory`, `DarkUIFactory` |
| **Abstract Product** | Giao diện mà mã sử dụng nhìn thấy | `Button`, `Dialog` |
| **Concrete Product** | Cài đặt hành vi của từng biến thể | `LightButton`, `DarkDialog`, ... |
| **Client** | Nhận factory và sử dụng sản phẩm qua các giao diện | `Screen` |
| **Composition root** | Chọn factory cụ thể một lần dựa trên cấu hình/ngữ cảnh | Hàm `main`, nơi cấu hình dependency injection |

Sơ đồ mô tả quan hệ chính:

~~~mermaid
flowchart TB
    Client["Screen (client)"] --> AbstractFactory["UIFactory"]
    AbstractFactory -. "hiện thực bởi" .-> LightFactory["LightUIFactory"]
    AbstractFactory -. "hiện thực bởi" .-> DarkFactory["DarkUIFactory"]
    LightFactory --> LightButton["LightButton : Button"]
    LightFactory --> LightDialog["LightDialog : Dialog"]
    DarkFactory --> DarkButton["DarkButton : Button"]
    DarkFactory --> DarkDialog["DarkDialog : Dialog"]
~~~

Sơ đồ cho thấy mỗi concrete factory biết phải tạo những sản phẩm nào. Mã `Screen` chỉ phụ thuộc vào hợp đồng `UIFactory`; nó không cần phân nhánh theo Light/Dark.

## 4. Ví dụ Java hoàn chỉnh: tạo giao diện đồng bộ theo chủ đề

Ví dụ sau dùng một tệp duy nhất `AbstractFactoryDemo.java`, có thể biên dịch với Java thông thường. Để tập trung vào mẫu thiết kế, phương thức `render()` chỉ in văn bản mô phỏng thay vì hiển thị GUI thật.

~~~java
// Abstract Product 1
interface Button {
    void render();
}

// Abstract Product 2
interface Dialog {
    void render();
}

// Abstract Factory: khai báo các loại sản phẩm trong một họ
interface UIFactory {
    Button createButton();
    Dialog createDialog();
}

// Các sản phẩm thuộc họ Light
class LightButton implements Button {
    @Override
    public void render() {
        System.out.println("Nút: giao diện SÁNG");
    }
}

class LightDialog implements Dialog {
    @Override
    public void render() {
        System.out.println("Hộp thoại: giao diện SÁNG");
    }
}

// Các sản phẩm thuộc họ Dark
class DarkButton implements Button {
    @Override
    public void render() {
        System.out.println("Nút: giao diện TỐI");
    }
}

class DarkDialog implements Dialog {
    @Override
    public void render() {
        System.out.println("Hộp thoại: giao diện TỐI");
    }
}

// Concrete Factory 1: luôn tạo các sản phẩm họ Light
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

// Concrete Factory 2: luôn tạo các sản phẩm họ Dark
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

// Client: không tham chiếu đến LightButton, DarkButton, ...
class Screen {
    private final Button button;
    private final Dialog dialog;

    Screen(UIFactory factory) {
        this.button = factory.createButton();
        this.dialog = factory.createDialog();
    }

    void render() {
        button.render();
        dialog.render();
    }
}

public class AbstractFactoryDemo {
    public static void main(String[] args) {
        // Composition root: chọn một họ sản phẩm cho màn hình.
        boolean darkMode =
                args.length > 0 && "dark".equalsIgnoreCase(args[0]);

        UIFactory factory = darkMode
                ? new DarkUIFactory()
                : new LightUIFactory();

        Screen screen = new Screen(factory);
        screen.render();
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 AbstractFactoryDemo.java
java AbstractFactoryDemo
java AbstractFactoryDemo dark
~~~

Hai lần chạy lần lượt in:

~~~text
Nút: giao diện SÁNG
Hộp thoại: giao diện SÁNG

Nút: giao diện TỐI
Hộp thoại: giao diện TỐI
~~~

### 4.1. Luồng hoạt động từng bước

1. `main` đọc tham số và tạo một trong hai factory cụ thể. **Đây là nơi biết đến Light/Dark.**
2. `Screen` chỉ nhận `UIFactory`; nó không biết factory đó là `LightUIFactory` hay `DarkUIFactory`.
3. `Screen` gọi `factory.createButton()` và `factory.createDialog()`.
4. Factory cụ thể trả về hai đối tượng cùng họ, nhưng kiểu mà `Screen` sử dụng vẫn chỉ là `Button` và `Dialog`.
5. `Screen` gọi `render()` thông qua các interface sản phẩm. Cách hoạt động thực tế do từng concrete product định nghĩa.

**Quan sát điểm tách biệt:** quyền **lựa chọn họ** thuộc về phần lắp ghép ứng dụng; quyền **lựa chọn lớp trong họ** thuộc về concrete factory; quyền **sử dụng sản phẩm** thuộc về client. Sự phân chia này làm giảm việc mã nghiệp vụ bị gắn chặt vào các lớp khởi tạo cụ thể.

### 4.2. Vì sao không để `Screen` tự gọi `new`?

Khi màn hình tự tạo `LightButton` hay `DarkDialog`, nó phải biết cả *quy tắc chọn họ* và *các lớp triển khai*. Nếu có hàng chục màn hình, quy tắc đó bị lặp lại và dễ không đồng bộ. Với Abstract Factory, chỉ cần truyền đúng factory vào mỗi màn hình; việc thêm hoặc thay thế một họ không đòi hỏi sửa logic sử dụng trong `Screen`.

Về mặt thiết kế, `Screen` phụ thuộc vào **trừu tượng** (`UIFactory`, `Button`, `Dialog`), phù hợp với nguyên tắc Dependency Inversion. Việc truyền factory qua constructor cũng giúp kiểm thử dễ hơn, vì có thể cung cấp factory giả để quan sát cách client tương tác với sản phẩm.

## 5. Những mục tiêu thiết kế mà Abstract Factory hướng tới

### 5.1. Đảm bảo sự nhất quán khi tạo nhiều sản phẩm liên quan

Một hệ thống thường có quy tắc kiểu: **các thành phần cùng xuất hiện phải thuộc cùng một nền tảng hoặc bộ cấu hình**. Gom phương thức tạo các thành phần đó vào một factory giúp biểu đạt quy tắc này rõ ràng trong API.

Tuy nhiên, Abstract Factory **không tự động ngăn tuyệt đối** việc tạo sai họ: mã ở nơi khác vẫn có thể gọi trực tiếp constructor nếu quyền truy cập cho phép, và một concrete factory viết sai vẫn có thể trả về sản phẩm khác họ. Tính nhất quán có được từ việc **client dùng chung một factory** và từ cách triển khai factory đúng hợp đồng.

### 5.2. Giảm phụ thuộc vào lớp cụ thể

Client sử dụng các giao diện sản phẩm, nên không cần sửa mỗi khi thay `LightButton` bằng một triển khai khác vẫn tuân thủ `Button`. Việc lựa chọn lớp cụ thể được dồn về nơi khởi tạo hoặc cấu hình.

### 5.3. Thay trọn bộ hành vi bằng cách đổi factory

Để thay từ Light sang Dark, ở ví dụ trên chỉ cần thay đối tượng `UIFactory` được cấp cho **màn hình mới tạo**. `Screen` vẫn dùng đúng hai phương thức và các kiểu dữ liệu cũ.

Lưu ý: khi đã tạo `Screen` và lưu sản phẩm vào các trường, đổi biến `factory` ở nơi khác **không làm các đối tượng cũ tự biến đổi**. Muốn đổi chủ đề cho giao diện đang hiển thị, ứng dụng cần tái tạo sản phẩm/màn hình hoặc thiết kế thêm cơ chế cập nhật trạng thái. Abstract Factory chỉ kiểm soát **việc khởi tạo**, không tự quản lý vòng đời hay cập nhật giao diện.

### 5.4. Gom quy tắc khởi tạo vào một vị trí

Ngoài gọi constructor, factory cụ thể có thể đảm nhiệm cấu hình mặc định hoặc truyền dependency cần thiết để các sản phẩm tương thích. Nhờ vậy việc cập nhật quy tắc cho cả một họ diễn ra tập trung, miễn là factory không bị biến thành lớp ôm quá nhiều trách nhiệm khác.

## 6. Khi nào nên dùng và khi nào không?

**Nên cân nhắc Abstract Factory khi:**

- Có **ít nhất hai loại sản phẩm liên quan** thường được tạo và dùng cùng nhau, ví dụ `Button` và `Dialog`.
- Có **nhiều họ/biến thể** của những loại sản phẩm đó, ví dụ Light/Dark, Windows/macOS, hoặc bộ thành phần theo từng nhà cung cấp.
- Cần đổi toàn bộ họ theo cấu hình, môi trường chạy, khách hàng hoặc nền tảng.
- Muốn mã sử dụng ổn định dù thay đổi các lớp triển khai cụ thể.

**Chưa cần Abstract Factory khi:**

- Chỉ có một loại đối tượng đơn giản, hoặc chưa có khái niệm «họ» thực sự.
- Số lượng biến thể rất ít và việc khởi tạo được quản lý rõ ràng tại một vị trí nhỏ.
- Việc tạo nhiều interface và factory khiến cấu trúc phức tạp hơn lợi ích nhận được.

Không nên áp dụng chỉ vì hệ thống có nhiều lớp. Dấu hiệu cốt lõi là **một quyết định cấu hình cần chi phối việc tạo ra một bộ sản phẩm có liên quan**.

## 7. Hai hướng mở rộng và đánh đổi quan trọng

### 7.1. Thêm một họ mới thường thuận lợi

Nếu bổ sung chủ đề **High Contrast**, ta có thể thêm `HighContrastButton`, `HighContrastDialog` và `HighContrastUIFactory`, rồi cập nhật nơi chọn factory. Các class client như `Screen` không cần thay đổi nếu chúng tiếp tục chỉ sử dụng `Button` và `Dialog`.

Đây là lợi ích nổi bật: **dễ mở rộng theo chiều thêm biến thể/họ sản phẩm**.

### 7.2. Thêm một *loại sản phẩm* mới thường tốn công

Giả sử mọi họ cần thêm `Checkbox`. Ta phải:

1. Định nghĩa interface `Checkbox`.
2. Thêm `createCheckbox()` vào `UIFactory`.
3. Viết `LightCheckbox`, `DarkCheckbox` và cài đặt phương thức mới trong **từng** concrete factory đang có.

Như vậy, Abstract Factory **khó mở rộng theo chiều thêm loại sản phẩm** vì hợp đồng của abstract factory và mọi factory cụ thể phải thay đổi. Đây là đánh đổi tự nhiên của cách gom nhiều phương thức tạo đối tượng vào một interface chung.

Nếu tập loại sản phẩm thay đổi liên tục, cần cân nhắc thiết kế khác hoặc chia thành các factory nhỏ theo nhóm trách nhiệm rõ ràng.

## 8. Phân biệt với những cách khởi tạo gần giống

| Cách tiếp cận | Trọng tâm | Khác biệt đáng nhớ |
| --- | --- | --- |
| **Constructor trực tiếp** | Tạo một instance cụ thể | Client thường biết tên lớp cụ thể và có thể tự phối hợp sai các biến thể |
| **Simple Factory** (cách tổ chức phổ biến, không thuộc danh sách GoF chính thức) | Chọn lớp triển khai dựa trên tham số | Thường trả về một loại sản phẩm; có thể phải chứa nhiều nhánh chọn loại và biến thể |
| **Factory Method** | Định nghĩa một phương thức tạo sản phẩm và cho lớp con quyết định cách tạo | Thường xoay quanh **một phương thức tạo**, trong khi Abstract Factory đóng gói **nhiều phương thức tạo cho một họ sản phẩm** |
| **Abstract Factory** | Tạo trọn bộ các loại sản phẩm tương thích qua một hợp đồng chung | Client chọn/nhận factory cụ thể rồi dùng tất cả sản phẩm qua trừu tượng |
| **Builder** | Lắp ráp một đối tượng phức tạp theo bước/cấu hình | Chủ yếu xử lý **quy trình xây dựng một đối tượng**, không nhất thiết tạo ra nhiều loại sản phẩm cùng họ |

Factory Method và Abstract Factory **có thể kết hợp**: các phương thức `createButton()`, `createDialog()` trong một concrete factory có thể được triển khai qua những factory method. Chúng không phải hai lựa chọn loại trừ nhau.

## 9. Những hiểu nhầm thường gặp

**«Abstract Factory phải tạo mọi đối tượng ngay lập tức.»** Không. Factory chỉ định nghĩa những phương thức có thể tạo; client gọi phương thức nào khi cần. Trong ví dụ, `Screen` chủ động tạo cả hai sản phẩm trong constructor, nhưng đó là lựa chọn của `Screen`, không phải quy tắc bắt buộc của pattern.

**«Sản phẩm trong cùng họ phải có cùng interface.»** Không. `Button` và `Dialog` là **hai loại sản phẩm khác nhau**. Các *biến thể của cùng một loại* mới tuân theo cùng interface: `LightButton` và `DarkButton` đều là `Button`.

**«Chỉ cần có một factory là đã dùng Abstract Factory.»** Chưa chắc. Nếu factory chỉ tạo một loại sản phẩm, thường chưa có lợi ích thiết kế theo họ. Giá trị của pattern xuất hiện rõ khi một factory phải điều phối **nhiều loại sản phẩm tương thích**.

**«Abstract Factory loại bỏ tất cả điều kiện Light/Dark.»** Không. Điều kiện chọn họ vẫn tồn tại tại **ranh giới lắp ghép**, ví dụ `main`, cấu hình môi trường hoặc dependency injection container. Điểm cải thiện là điều kiện đó không bị lặp trong từng client.

**«Factory tự bảo đảm hai sản phẩm hợp nhau.»** Pattern thể hiện quy tắc ấy ở cấu trúc thiết kế; lập trình viên vẫn cần cài đặt các concrete factory nhất quán và có thể bổ sung kiểm thử cho quy tắc phối hợp.

## 10. Tổng kết kiến thức cốt lõi

Abstract Factory trả lời câu hỏi: **«Làm thế nào để tạo ra nhiều loại đối tượng thuộc cùng một họ, trong khi mã sử dụng không cần biết các lớp triển khai cụ thể?»**

Trong ví dụ, `UIFactory` là hợp đồng tạo `Button` và `Dialog`; `LightUIFactory` và `DarkUIFactory` là hai cách tạo **cùng tập loại sản phẩm**, nhưng với những biến thể tương ứng. Khi truyền một factory vào `Screen`, ứng dụng chọn được cả họ mà không làm `Screen` phụ thuộc vào Light hay Dark.

Hãy nhớ hai điểm quyết định: **thay cả họ dễ dàng bằng cách đổi factory**, còn **thêm một loại sản phẩm mới cần cập nhật mọi factory**. Khi yêu cầu nghiệp vụ thật sự đặt nặng tính tương thích giữa nhiều sản phẩm, đánh đổi này thường mang lại cấu trúc dễ hiểu và dễ bảo trì hơn.
