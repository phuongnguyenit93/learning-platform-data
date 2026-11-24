# Vị trí của Abstract Factory trong nhóm mẫu thiết kế khởi tạo

## 1. Bối cảnh: vì sao có nhóm mẫu thiết kế khởi tạo?

Trong phát triển phần mềm, việc tạo đối tượng không phải lúc nào cũng đơn giản như viết `new SomeClass()`. Khi ứng dụng phát triển, quyết định **tạo lớp nào**, **tạo bằng cách nào**, **sử dụng chung hay tạo mới** và **các đối tượng phải phối hợp ra sao** có thể trở thành những quy tắc thay đổi theo cấu hình, nền tảng hoặc yêu cầu nghiệp vụ.

Ví dụ, một ứng dụng có giao diện **Light** và **Dark**. Mỗi chế độ có nút bấm, hộp thoại và thanh điều hướng riêng. Nếu mã màn hình tự tạo từng lớp cụ thể, một màn hình có thể chọn `DarkButton` nhưng lại sử dụng `LightDialog`. Khi ứng dụng thêm chế độ mới, các điều kiện chọn lớp dễ bị lặp ở nhiều nơi.

Nhóm **Creational Design Patterns** (mẫu thiết kế khởi tạo) tập trung vào cách **tổ chức trách nhiệm tạo đối tượng** để mã sử dụng không bị gắn chặt quá mức với cơ chế khởi tạo. Trong nhóm này, **Abstract Factory** đặc biệt phù hợp khi ứng dụng phải tạo **nhiều loại đối tượng liên quan theo cùng một họ/biến thể**.

Nội dung bài học thuộc module **Abstract Factory** của mảng thiết kế phần mềm. Mục tiêu là xác định vị trí của nó trong hệ thống các mẫu khởi tạo, biết điểm khác biệt với các mẫu gần kề và chọn đúng công cụ cho từng loại bài toán.

## 2. Bức tranh tổng thể: năm mẫu khởi tạo GoF

Bộ *Gang of Four (GoF)* phân loại năm mẫu thiết kế khởi tạo kinh điển:

1. **Singleton**
2. **Factory Method**
3. **Abstract Factory**
4. **Builder**
5. **Prototype**

Chúng cùng quan tâm đến việc tạo đối tượng nhưng giải quyết những **câu hỏi thiết kế khác nhau**.

| Mẫu thiết kế | Câu hỏi trọng tâm | Trách nhiệm nổi bật | Tình huống minh họa |
| --- | --- | --- | --- |
| **Singleton** | Làm thế nào giới hạn việc tạo một lớp về một instance trong phạm vi thiết kế? | Kiểm soát số instance và cung cấp cách truy cập/thu nhận nó | Một đối tượng cấu hình dùng chung có vòng đời được quản lý |
| **Factory Method** | Làm thế nào để một lớp cha định nghĩa điểm tạo sản phẩm, còn lớp con quyết định sản phẩm cụ thể? | Cho phép lớp con thay đổi sản phẩm được khởi tạo qua phương thức tạo | Mỗi loại trình biên tập tạo loại tài liệu riêng |
| **Abstract Factory** | Làm thế nào tạo **một họ gồm nhiều loại sản phẩm liên quan** mà client không cần biết các lớp cụ thể? | Gom các phương thức tạo sản phẩm theo **họ tương thích** | Một factory tạo cả nút và hộp thoại Light; factory khác tạo bộ Dark |
| **Builder** | Làm thế nào xây dựng một đối tượng phức tạp qua các bước có kiểm soát? | Tách quá trình lắp ráp khỏi cách biểu diễn/đối tượng hoàn chỉnh | Xây dựng một yêu cầu HTTP hoặc cấu hình báo cáo nhiều tùy chọn |
| **Prototype** | Làm thế nào tạo đối tượng mới từ một đối tượng mẫu có sẵn? | Sao chép prototype thay vì cấu hình mọi instance từ đầu | Nhân bản mẫu biểu đồ hoặc thành phần đã cấu hình |

Sơ đồ vị trí của Abstract Factory:

~~~mermaid
flowchart TB
    GoF["GoF Design Patterns"] --> C["Creational / Khởi tạo"]
    GoF --> S["Structural / Cấu trúc"]
    GoF --> B["Behavioral / Hành vi"]
    C --> Single["Singleton"]
    C --> FM["Factory Method"]
    C --> AF["Abstract Factory"]
    C --> Build["Builder"]
    C --> Proto["Prototype"]
    AF --> Family["Tạo đồng bộ các họ sản phẩm liên quan"]
~~~

**Điểm cần nhớ:** Abstract Factory là **một mẫu thuộc nhóm khởi tạo**, cùng nhóm với Factory Method, Builder, Prototype và Singleton. Nó không phải tên gọi chung cho tất cả factory hoặc mọi đoạn mã có phương thức `create()`.

### 2.1. «Khởi tạo» không chỉ là giấu toán tử new

Một mẫu khởi tạo hữu ích khi nó cô lập một **quyết định có thể thay đổi**. Chẳng hạn:

- Factory Method cô lập quyết định **một lớp con sẽ tạo sản phẩm cụ thể nào**.
- Builder cô lập **quy trình hình thành một đối tượng có nhiều phần hoặc bước**.
- Prototype cô lập **cách tạo đối tượng mới từ một đối tượng mẫu**.
- Singleton xử lý **giới hạn số instance và cách thu nhận instance**.
- Abstract Factory cô lập quyết định **một bộ gồm nhiều loại sản phẩm sẽ thuộc cùng họ nào**.

Việc đơn giản bọc `new` trong một hàm không tự động đem lại đầy đủ cấu trúc và lợi ích của các mẫu này. Cần xét **điểm biến thiên** mà thiết kế đang muốn quản lý.

## 3. Điều gì làm Abstract Factory nổi bật?

### 3.1. Hai chiều của bài toán: loại sản phẩm và họ sản phẩm

Giả sử ứng dụng có hai **loại sản phẩm**: `Button` và `Dialog`. Mỗi loại có hai **biến thể**: Light và Dark.

| Loại sản phẩm (vai trò) | Họ Light | Họ Dark |
| --- | --- | --- |
| `Button` | `LightButton` | `DarkButton` |
| `Dialog` | `LightDialog` | `DarkDialog` |
| Factory tương ứng | `LightUIFactory` | `DarkUIFactory` |

Đọc bảng theo **hàng** sẽ thấy các cách triển khai của cùng một loại sản phẩm. Đọc theo **cột** sẽ thấy **một họ** gồm nhiều loại sản phẩm được thiết kế để cùng sử dụng.

Abstract Factory chọn **cả một cột**: client nhận một `UIFactory`, sau đó yêu cầu factory tạo `Button` và `Dialog`. Concrete factory quyết định nên khởi tạo những lớp nào để các sản phẩm thuộc cùng biến thể.

### 3.2. Cấu trúc điển hình

~~~java
// Abstract Products
interface Button {
    void draw();
}

interface Dialog {
    void show();
}

// Abstract Factory
interface UIFactory {
    Button createButton();
    Dialog createDialog();
}
~~~

Các thành phần của cấu trúc gồm:

| Vai trò | Trách nhiệm |
| --- | --- |
| **Abstract Product** | Hợp đồng dùng chung của mỗi loại sản phẩm, ví dụ `Button` và `Dialog` |
| **Concrete Product** | Lớp triển khai một biến thể, ví dụ `DarkButton` và `DarkDialog` |
| **Abstract Factory** | Hợp đồng tạo nhiều loại sản phẩm, ví dụ `UIFactory` |
| **Concrete Factory** | Cài đặt việc tạo cả họ, ví dụ `DarkUIFactory` |
| **Client** | Nhận factory và sử dụng sản phẩm qua interface |

Nhờ vậy, client biết **mình cần loại sản phẩm nào**, nhưng không cần quyết định **biến thể nào được tạo ra** trong từng lời gọi.

Một lưu ý quan trọng: Java không tự bảo đảm `DarkUIFactory` luôn trả về đúng sản phẩm Dark. Một concrete factory viết sai vẫn có thể trả về `LightDialog` vì cả hai đều triển khai `Dialog`. Khả năng tạo sản phẩm cùng họ đến từ **quy ước thiết kế và việc triển khai đúng**; những quy tắc tương thích quan trọng nên được kiểm thử.

### 3.3. Lợi ích gắn trực tiếp với bài toán «cả họ»

Khi lựa chọn giao diện chuyển từ Light sang Dark, mã lắp ghép ứng dụng truyền một factory khác cho các client mới. Client vẫn gọi `createButton()` và `createDialog()` theo hợp đồng không đổi.

Lợi ích chính là:

- **Cô lập lớp cụ thể:** màn hình không cần gọi `new DarkButton()` hoặc `new LightDialog()`.
- **Tăng tính nhất quán giữa sản phẩm:** một factory chịu trách nhiệm chọn đúng các biến thể liên quan.
- **Thay cả họ thuận tiện:** thêm factory và sản phẩm mới cho một biến thể thường không đòi hỏi sửa logic client hiện có.
- **Hỗ trợ kiểm thử:** có thể truyền fake factory hoặc implementation khác thông qua cùng interface.

Các lợi ích trên đều phục vụ một mục tiêu cụ thể: **quản lý sự đa dạng của những bộ sản phẩm cùng vai trò nhưng khác biến thể**.

## 4. Phân biệt Abstract Factory với Factory Method

Hai mẫu này dễ nhầm vì đều có phương thức tạo đối tượng. Trong cách trình bày GoF kinh điển, khác biệt đáng chú ý nằm ở **cấu trúc mở rộng** và **phạm vi sản phẩm**.

### 4.1. Factory Method: lớp con quyết định sản phẩm được tạo

Factory Method định nghĩa một phương thức tạo sản phẩm tại lớp cơ sở (*Creator*). Lớp con triển khai hoặc ghi đè phương thức đó để quyết định concrete product. Mã trong lớp cơ sở sử dụng kết quả thông qua interface sản phẩm.

Ví dụ khái niệm:

~~~java
interface Document {
    void open();
}

abstract class Editor {
    // Đây là factory method.
    protected abstract Document createDocument();

    public void openNewDocument() {
        Document document = createDocument();
        document.open();
    }
}

// Một lớp con của Editor chọn loại Document cụ thể.
~~~

Ở đây, lớp cơ sở quy định **khi nào cần tài liệu**, còn lớp con quyết định **tạo loại tài liệu nào**. Đây là cơ chế dựa trên **kế thừa và ghi đè phương thức**.

Đừng đồng nhất mọi hàm có tên `createSomething()` với **Factory Method pattern**. Một phương thức tạo trong Abstract Factory có thể đồng thời sử dụng cách triển khai dựa trên Factory Method, nhưng chỉ có tên `create` không đủ để kết luận về mẫu.

### 4.2. Abstract Factory: một đối tượng factory tạo cả bộ sản phẩm

Trong Abstract Factory, client thường **nhận một đối tượng factory** rồi gọi nhiều phương thức trên đó:

~~~java
UIFactory factory = /* factory đã được chọn ở nơi cấu hình */;
Button button = factory.createButton();
Dialog dialog = factory.createDialog();
~~~

Ví dụ này cho thấy cơ chế **composition**: client nắm giữ một factory qua interface. Concrete factory có nhiệm vụ tạo **một họ gồm nhiều loại sản phẩm**.

| Góc nhìn | Factory Method | Abstract Factory |
| --- | --- | --- |
| Câu hỏi chính | Một lớp con tạo sản phẩm cụ thể nào? | Cần tạo họ sản phẩm nào cho nhiều loại sản phẩm liên quan? |
| Cơ chế điển hình | Kế thừa Creator và ghi đè phương thức tạo | Cung cấp concrete factory như một dependency |
| Hợp đồng chính | Điểm tạo sản phẩm trong lớp cơ sở | Interface gồm các phương thức tạo từng loại sản phẩm |
| Phạm vi thường gặp | Một vai trò sản phẩm tại một điểm mở rộng | Nhiều vai trò sản phẩm trong cùng họ |
| Điểm mạnh | Tùy biến việc tạo thông qua lớp con | Chuyển đổi đồng bộ nhiều sản phẩm theo biến thể |

**Không có quy tắc hai mẫu loại trừ nhau.** Một concrete factory của Abstract Factory có thể dùng Factory Method bên trong để tạo từng sản phẩm; hoặc dùng Prototype để nhân bản một đối tượng đã cấu hình.

## 5. Phân biệt với Builder, Prototype và Singleton

### 5.1. Builder: tập trung vào cách lắp ráp một đối tượng

Khi một yêu cầu báo cáo có hàng chục thuộc tính tùy chọn, client có thể cần tạo nó qua nhiều bước:

~~~java
ReportRequest request = new ReportRequestBuilder()
        .withTitle("Doanh thu quý")
        .includeCharts(true)
        .withFormat("PDF")
        .build();
~~~

*Đoạn mã trên mang tính minh họa API; `ReportRequestBuilder` không thuộc ví dụ Java tự chạy ở phần sau.*

Builder phù hợp vì trọng tâm là **xây dựng một đối tượng có cấu hình phức tạp**. Trong khi đó, Abstract Factory phù hợp nếu hệ thống cần tạo **cả một bộ đối tượng khác loại** theo biến thể, ví dụ `PdfFormatter` + `PdfExporter` hoặc `HtmlFormatter` + `HtmlExporter`.

Hai mẫu có thể kết hợp: một Abstract Factory có thể tạo builder theo từng họ; builder tiếp tục lắp ráp sản phẩm phức tạp.

### 5.2. Prototype: tập trung vào việc tạo từ mẫu có sẵn

Prototype phù hợp khi đã có một đối tượng được cấu hình làm mẫu và muốn tạo ra một đối tượng mới với trạng thái tương ứng:

~~~java
// Pseudocode: prototype tự định nghĩa cơ chế copy phù hợp.
Shape copy = template.copy();
~~~

Khác biệt quan trọng:

- Prototype hỏi: **«Có thể tạo đối tượng mới bằng cách sao chép đối tượng mẫu không?»**
- Abstract Factory hỏi: **«Nhiều loại đối tượng cần được tạo thuộc cùng họ nào?»**

Cơ chế sao chép cần có quy tắc rõ ràng về **deep copy** và **shallow copy**. Prototype không mặc nhiên bảo đảm mọi thành phần lồng nhau được sao chép độc lập.

Một concrete factory trong Abstract Factory thậm chí có thể lưu các prototype và sao chép chúng khi tạo sản phẩm. Đây là ví dụ hai mẫu hỗ trợ nhau.

### 5.3. Singleton: tập trung vào số instance, không phải họ sản phẩm

Singleton tổ chức để một lớp có một instance trong phạm vi được thiết kế và cung cấp cách lấy instance đó. Đây là mối quan tâm về **số lượng/vòng đời đối tượng**, khác với cách chọn nhiều sản phẩm cùng biến thể.

Một factory có thể được cài đặt dưới dạng Singleton nếu chính factory cần dùng chung và không giữ trạng thái thay đổi theo request; tuy nhiên **Abstract Factory không đòi hỏi Singleton**. Hoàn toàn có thể có nhiều instance `LightUIFactory` và các instance này vẫn tạo đúng họ Light.

Không nên dùng Singleton chỉ vì muốn truy cập factory ở mọi nơi. Đối tượng dùng chung toàn cục có thể làm phụ thuộc khó nhìn thấy và khó cô lập trong kiểm thử. Việc truyền factory tường minh hoặc dùng dependency injection thường dễ kiểm soát hơn.

## 6. Ví dụ Java: cùng một client, nhiều họ sản phẩm

Để thấy vì sao Abstract Factory nằm đúng vị trí của nó trong nhóm khởi tạo, hãy xét trường hợp tạo **hai loại thành phần GUI** theo chế độ Light/Dark. Các lớp triển khai chỉ in mô phỏng lên console để tránh phụ thuộc framework giao diện.

Lưu mã trong tệp `CreationalPositionDemo.java`:

~~~java
// Abstract Product 1
interface Button {
    String display();
}

// Abstract Product 2
interface Dialog {
    String display();
}

// Abstract Factory: khai báo các loại sản phẩm cần tạo.
interface UIFactory {
    Button createButton();
    Dialog createDialog();
}

// Họ Light
class LightButton implements Button {
    @Override
    public String display() {
        return "Button Light";
    }
}

class LightDialog implements Dialog {
    @Override
    public String display() {
        return "Dialog Light";
    }
}

// Họ Dark
class DarkButton implements Button {
    @Override
    public String display() {
        return "Button Dark";
    }
}

class DarkDialog implements Dialog {
    @Override
    public String display() {
        return "Dialog Dark";
    }
}

// Mỗi factory triển khai việc tạo cả họ sản phẩm.
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

// Client chỉ phụ thuộc vào các interface.
class SettingsPage {
    private final UIFactory factory;

    SettingsPage(UIFactory factory) {
        this.factory = factory;
    }

    void render() {
        Button button = factory.createButton();
        Dialog dialog = factory.createDialog();

        System.out.println(button.display());
        System.out.println(dialog.display());
    }
}

public class CreationalPositionDemo {
    public static void main(String[] args) {
        boolean darkMode = args.length > 0
                && "dark".equalsIgnoreCase(args[0]);

        // Chọn họ sản phẩm tại nơi lắp ghép ứng dụng.
        UIFactory factory = darkMode
                ? new DarkUIFactory()
                : new LightUIFactory();

        new SettingsPage(factory).render();
    }
}
~~~

Biên dịch và chạy bằng JDK:

~~~bash
javac -encoding UTF-8 CreationalPositionDemo.java
java CreationalPositionDemo
java CreationalPositionDemo dark
~~~

Kết quả hai lần chạy:

~~~text
Button Light
Dialog Light

Button Dark
Dialog Dark
~~~

### 6.1. Vì sao ví dụ này là Abstract Factory?

Có thể chỉ ra trực tiếp năm dấu hiệu:

1. **Hai loại sản phẩm khác nhau:** `Button` và `Dialog`.
2. **Hai họ sản phẩm:** Light và Dark.
3. **Một hợp đồng tạo cả hai loại:** `UIFactory`.
4. **Hai concrete factory:** mỗi factory trả về sản phẩm của cùng một họ.
5. **Client chỉ biết abstraction:** `SettingsPage` không tham chiếu đến `LightButton` hoặc `DarkDialog`.

Nếu client chỉ cần tạo **một** loại `Button` và không có nhu cầu phối hợp nhiều loại sản phẩm, một factory đơn giản hoặc Factory Method có thể đủ. Việc thêm Abstract Factory lúc đó chưa chắc đem lại giá trị tương xứng.

### 6.2. Phần nào vẫn phải biết lớp cụ thể?

`main()` vẫn có `new LightUIFactory()` hoặc `new DarkUIFactory()`. Điều này là hợp lý: **nơi lắp ghép ứng dụng** (*composition root*) cần biết quyết định cấu hình để cấp đúng factory.

Abstract Factory không xóa bỏ hoàn toàn việc tạo lớp cụ thể. Nó **đưa quyết định đó ra khỏi phần lớn client**, giúp các client làm việc với cùng các interface sản phẩm.

Một giới hạn khác: khi `SettingsPage` đã tạo sản phẩm, đổi factory ở nơi khác **không biến các instance cũ** thành phiên bản Dark. Chuyển chế độ ngay trên giao diện đang chạy đòi hỏi cập nhật/tạo lại các thành phần hoặc một cơ chế trạng thái bổ sung.

## 7. Dùng mẫu nào cho từng yêu cầu?

Sử dụng các câu hỏi sau để tìm đúng trọng tâm; các câu trả lời có thể dẫn tới **nhiều mẫu kết hợp**.

| Yêu cầu nổi bật | Hướng cân nhắc | Vì sao? |
| --- | --- | --- |
| Cùng logic nhưng có nhiều **bộ sản phẩm khác loại, tương thích** theo biến thể | **Abstract Factory** | Một factory đại diện cho cả họ sản phẩm |
| Lớp cơ sở định nghĩa quy trình, lớp con quyết định đối tượng được tạo tại một điểm mở rộng | **Factory Method** | Tận dụng đa hình và phương thức được ghi đè |
| Một đối tượng cần lắp ráp qua nhiều bước hoặc tùy chọn cấu hình | **Builder** | Làm rõ quy trình dựng đối tượng |
| Có mẫu được cấu hình sẵn, tạo mới bằng cách sao chép là phù hợp | **Prototype** | Tái sử dụng trạng thái mẫu |
| Phải kiểm soát một instance duy nhất trong phạm vi cụ thể | **Singleton** | Kiểm soát số lượng và cách truy cập instance |
| Chỉ cần `new` một lớp đơn giản ở một nơi, ít khả năng thay đổi | **Tạo trực tiếp** | Tránh tăng tầng trừu tượng khi chưa có yêu cầu thực tế |

Một cách đặt câu hỏi dễ nhớ là: **điều gì thay đổi nhiều nhất?**

- Thay **họ** của nhiều sản phẩm → ưu tiên xem xét Abstract Factory.
- Thay **loại sản phẩm do lớp con lựa chọn** → xem Factory Method.
- Thay **các bước và tùy chọn xây dựng** → xem Builder.
- Thay **mẫu để sao chép** → xem Prototype.
- Kiểm soát **số instance** → xem Singleton.

### 7.1. Vì sao Abstract Factory không thay thế tất cả mẫu còn lại?

Với bài toán giao diện, Abstract Factory giải quyết câu hỏi «tạo họ Light hay Dark?». Nó không quy định:

- Cách một đối tượng phức tạp được tạo qua nhiều bước.
- Cách sao chép an toàn một instance đang tồn tại.
- Số lượng instance của factory hoặc sản phẩm cần tồn tại trong ứng dụng.
- Khi nào một sự kiện GUI được phát ra hay xử lý.

Những trách nhiệm khác thuộc về thiết kế vòng đời, xử lý sự kiện hoặc các mẫu phù hợp khác. Một ứng dụng có thể dùng Abstract Factory để chọn họ sản phẩm và Builder để cấu hình một sản phẩm phức tạp trong họ đó.

## 8. Đánh đổi của Abstract Factory trong bức tranh chung

Vì hợp đồng factory thường khai báo **một phương thức cho từng loại sản phẩm**, hai hướng mở rộng có chi phí khác nhau.

### 8.1. Thêm họ mới thường ít đụng đến client

Nếu thêm chế độ **High Contrast**, ta có thể viết:

- `HighContrastButton implements Button`
- `HighContrastDialog implements Dialog`
- `HighContrastUIFactory implements UIFactory`

Sau đó cập nhật nơi chọn factory. `SettingsPage` vẫn sử dụng `UIFactory`, `Button` và `Dialog`.

Đây là ưu điểm nổi bật khi hệ thống dự kiến **nhiều họ có cùng bộ vai trò sản phẩm**.

### 8.2. Thêm loại sản phẩm mới sẽ tác động tới nhiều factory

Giả sử mọi họ đều cần `Checkbox`. Khi đó cần:

1. Định nghĩa `Checkbox` và các concrete product tương ứng cho Light, Dark, High Contrast.
2. Thêm `Checkbox createCheckbox()` vào `UIFactory`.
3. Cài đặt phương thức mới trong **tất cả** concrete factory hiện có.

Vì vậy, Abstract Factory phù hợp nhất khi **tập các loại sản phẩm tương đối ổn định**, còn **các họ/biến thể có thể thay đổi hoặc mở rộng**.

Nếu các loại sản phẩm mới được thêm liên tục, cần xem lại ranh giới factory: có thể tách thành những factory nhỏ theo nhóm trách nhiệm, hoặc chọn cấu trúc khác để tránh interface quá lớn.

### 8.3. Lợi ích và chi phí

| Lợi ích | Chi phí hoặc giới hạn |
| --- | --- |
| Client ít phụ thuộc lớp triển khai | Cần thêm interface và concrete factory |
| Đổi bộ sản phẩm theo cấu hình | Vẫn cần một nơi lựa chọn factory cụ thể |
| Dễ giữ sản phẩm trong cùng họ | Factory triển khai sai vẫn có thể tạo bộ không tương thích |
| Thuận tiện thêm biến thể mới | Thêm **loại sản phẩm** phải cập nhật toàn bộ họ |
| Dễ thay fake factory trong test | Trừu tượng hóa có thể quá mức nếu bài toán chỉ có một lớp |

Abstract Factory không phải một «quy tắc luôn phải dùng». Nó là công cụ để **giảm sự lan truyền của quyết định chọn họ sản phẩm** khi quyết định đó thật sự quan trọng.

## 9. Những nhầm lẫn thường gặp về vị trí của mẫu

**«Abstract Factory chính là Factory Method với nhiều hàm hơn.»** Chưa chính xác. Abstract Factory thể hiện **gia đình các sản phẩm liên quan** bằng một hợp đồng tạo đối tượng; Factory Method nhấn mạnh **điểm mở rộng bằng ghi đè phương thức tạo**. Chúng có thể phối hợp, nhưng điểm biến thiên chính không giống nhau.

**«Abstract Factory bắt buộc tạo tất cả sản phẩm cùng lúc.»** Không. Interface có nhiều phương thức tạo, nhưng client có thể gọi những phương thức cần thiết vào thời điểm phù hợp. Factory cung cấp khả năng tạo đúng họ, không ép mọi sản phẩm phải ra đời cùng nhau.

**«Một Singleton factory chính là Abstract Factory.»** Không. Singleton nói về số instance; Abstract Factory nói về việc tạo các sản phẩm cùng họ. Một factory có thể là Singleton, nhưng đó là lựa chọn bổ sung.

**«Builder tạo đối tượng nên dùng nó thay Abstract Factory được.»** Chỉ khi vấn đề thực sự là **quá trình lắp ráp một đối tượng phức tạp**. Nếu yêu cầu là tạo nhiều loại sản phẩm tương thích theo biến thể, Builder tự nó không diễn tả đầy đủ lựa chọn theo họ.

**«Đã dùng interface thì chắc chắn là Abstract Factory.»** Không. Interface chỉ là cơ chế trừu tượng của ngôn ngữ. Cần xem có **hợp đồng factory** và **nhiều loại sản phẩm thuộc các họ tương ứng** hay không.

**«Abstract Factory luôn bảo đảm mọi sản phẩm cùng họ ở thời điểm biên dịch.»** Không mặc nhiên. Các method trả về interface, nên một concrete factory viết sai vẫn có thể trả về nhầm biến thể. Giữ tính nhất quán cần cách triển khai và kiểm tra phù hợp.

## 10. Câu hỏi tự đánh giá

**Câu 1.** Một hệ thống chỉ tạo các `PaymentGateway` thay thế nhau, không cần bộ sản phẩm đi kèm. Có nhất thiết phải dùng Abstract Factory không?

**Gợi ý trả lời:** Không. Có thể dùng Factory Method, factory đơn giản hoặc dependency injection tùy cách tạo và cấp dependency. Abstract Factory đem lại giá trị rõ hơn khi có **nhiều loại sản phẩm phải cùng biến thể**.

**Câu 2.** Một trình tạo báo cáo có hơn 20 tùy chọn, cần cấu hình từng bước trước khi nhận đối tượng hoàn chỉnh. Mẫu nào nổi bật?

**Gợi ý trả lời:** Builder, vì bài toán là **quy trình lắp ráp một đối tượng phức tạp**. Nếu còn phải chọn bộ thành phần PDF/HTML phù hợp, có thể kết hợp thêm Abstract Factory.

**Câu 3.** Nếu thêm họ Solarized vào giao diện hiện tại, những phần nào thường cần sửa?

**Gợi ý trả lời:** Bổ sung các concrete product của họ mới, concrete factory mới và cập nhật nơi chọn factory. Client dùng các interface cũ thường không cần sửa.

**Câu 4.** Nếu thêm loại `Menu` vào mọi họ, tại sao thay đổi lại rộng hơn?

**Gợi ý trả lời:** Phải bổ sung một phương thức tạo `Menu` trong abstract factory và cài đặt ở từng concrete factory. Đây là đánh đổi đặc trưng của Abstract Factory.

**Câu 5.** Factory có dùng phương thức `createButton()` thì có chắc là Factory Method pattern không?

**Gợi ý trả lời:** Không. Cần xem cách tổ chức Creator, điểm mở rộng qua kế thừa/ghi đè và bối cảnh tổng thể. Một phương thức có tên `createButton()` trong Abstract Factory chỉ cho biết đó là một thao tác tạo sản phẩm; tên gọi không tự quyết định mẫu thiết kế.

## 11. Kết luận

Trong năm mẫu khởi tạo GoF, **Abstract Factory giữ vị trí riêng vì giải quyết việc tạo *một họ gồm nhiều loại sản phẩm liên quan***. Factory Method thiên về việc lớp con quyết định sản phẩm cụ thể tại một điểm tạo; Builder tập trung vào quy trình dựng đối tượng; Prototype tạo từ một mẫu có sẵn; Singleton kiểm soát số instance.

Khi cần thay bộ sản phẩm Light/Dark, Windows/macOS hoặc các biến thể tương đương bằng một quyết định cấu hình, Abstract Factory cho phép **client phụ thuộc vào interface, concrete factory chọn các lớp thuộc cùng họ**. Hiểu đúng ranh giới này giúp chọn mẫu thiết kế theo yêu cầu thực tế, tránh áp dụng máy móc chỉ vì mã có nhiều lệnh `new`.
