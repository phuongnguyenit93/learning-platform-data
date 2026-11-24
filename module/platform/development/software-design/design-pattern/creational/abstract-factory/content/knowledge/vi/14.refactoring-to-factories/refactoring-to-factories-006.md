# Di chuyển quyết định chọn họ về composition root theo từng bước nhỏ

## 1. Vấn đề cần giải quyết khi tái cấu trúc

Trong một ứng dụng đặt phòng, nhiều màn hình cần tạo nút bấm và hộp thoại theo cùng chủ đề **Light** hoặc **Dark**. Ban đầu, mỗi màn hình có thể tự kiểm tra cấu hình để khởi tạo lớp sản phẩm cụ thể:

~~~java
class BookingScreen {
    void show(boolean darkMode) {
        Button confirm = darkMode
                ? new DarkButton()
                : new LightButton();

        Dialog message = darkMode
                ? new DarkDialog()
                : new LightDialog();

        confirm.render("Xác nhận đặt phòng");
        message.show("Đặt phòng thành công");
    }
}
~~~

Trong ví dụ trên, `Button` và `Dialog` là các interface sản phẩm, còn những lớp Light/Dark là lớp triển khai. Khi nhiều màn hình lặp lại đoạn chọn sản phẩm, xuất hiện các vấn đề:

- Cùng một cấu hình nhưng mỗi màn hình có thể diễn giải khác nhau.
- Một nhánh viết sai có thể ghép `DarkButton` với `LightDialog`.
- Muốn thêm họ mới, ví dụ High Contrast, phải sửa nhiều client.
- Mã giao diện vừa có trách nhiệm **sử dụng sản phẩm**, vừa có trách nhiệm **chọn lớp triển khai**.
- Test muốn thay cả họ phải can thiệp vào các cờ hoặc các câu lệnh tạo đối tượng bên trong client.

**Mục tiêu tái cấu trúc** là đưa quyết định **chọn họ sản phẩm** ra khỏi các màn hình, tập trung tại **composition root** (điểm lắp ghép dependency), rồi truyền một `UIFactory` phù hợp vào các client. Đây là cách áp dụng mẫu **Abstract Factory** trong nhóm *Creational Design Patterns*.

Điểm quan trọng của bài học không nằm ở việc viết một factory mới càng nhanh càng tốt. Trọng tâm là **dịch chuyển trách nhiệm qua nhiều thay đổi nhỏ, có thể kiểm tra và giữ nguyên hành vi đang có**.

## 2. Composition root là gì và vì sao đặt quyết định ở đó?

**Composition root** là nơi một ứng dụng hoặc một phạm vi xử lý **tạo, lựa chọn và kết nối các dependency cụ thể** để hình thành những đối tượng cấp cao hơn. Trong ứng dụng Java đơn giản, đó có thể là `main()`. Trong ứng dụng web, nó có thể là bước cấu hình dependency injection lúc khởi động hoặc điểm tạo dependency cho một request/phạm vi sử dụng.

Composition root thường biết:

- Ứng dụng đang chạy với cấu hình, nền tảng hoặc profile nào.
- Các concrete factory và dịch vụ triển khai nào có sẵn.
- Cách cấp những dependency đó cho các lớp nghiệp vụ hoặc giao diện.

Ngược lại, `BookingScreen` chỉ cần biết: **«Tôi có một Button và một Dialog để sử dụng»**. Màn hình không cần biết tên biến môi trường, tên lớp Light/Dark hoặc câu lệnh khởi tạo concrete factory.

Sơ đồ trước và sau:

~~~mermaid
flowchart LR
    subgraph Before["Trước khi tái cấu trúc"]
        S1["BookingScreen"] --> C1["if (darkMode)"]
        S2["HelpScreen"] --> C2["if (theme)"]
        C1 --> P1["Light/Dark Products"]
        C2 --> P1
    end
    subgraph After["Sau khi tái cấu trúc"]
        Root["Composition root"] --> F["UIFactory đã chọn"]
        F --> S3["BookingScreen"]
        F --> S4["HelpScreen"]
        S3 --> AP["Button / Dialog interfaces"]
        S4 --> AP
    end
~~~

Sơ đồ là diễn giải trách nhiệm: ở mã thật, composition root **truyền factory** vào constructor của client; client **gọi phương thức tạo sản phẩm** trên factory, rồi sử dụng chúng qua interface sản phẩm.

### 2.1. Chọn factory và tạo sản phẩm là hai trách nhiệm khác nhau

**Chọn họ:** căn cứ cấu hình để quyết định `LightUIFactory` hay `DarkUIFactory`. Việc này nằm ở composition root hoặc một bộ chọn được root gọi.

**Tạo sản phẩm trong họ:** `LightUIFactory.createButton()` tạo `LightButton`, `DarkUIFactory.createDialog()` tạo `DarkDialog`. Việc này nằm ở concrete factory.

**Sử dụng sản phẩm:** `BookingScreen` gọi `button.render(...)` và `dialog.show(...)` qua các interface. Nó không chọn họ và không gọi constructor sản phẩm cụ thể.

Phân chia này giúp mã client áp dụng nguyên tắc **phụ thuộc vào trừu tượng**. Nó cũng tạo ra một điểm nhất quán: nhiều sản phẩm trong cùng phạm vi có thể được tạo từ **cùng một factory đã chọn**.

### 2.2. «Một nơi chọn» không nhất thiết là «một factory toàn cục»

Composition root có thể tạo một factory cho toàn ứng dụng, hoặc chọn factory riêng cho một phiên người dùng hay một request nếu yêu cầu là như vậy. Không cần biến factory thành Singleton hoặc lưu nó trong biến toàn cục.

Ví dụ, nếu mỗi người dùng có theme riêng thì factory có thể được chọn lúc tạo **phạm vi giao diện của người dùng đó**. Vẫn chỉ có một nơi có trách nhiệm chọn cho phạm vi ấy; các màn hình trong phạm vi nhận cùng lựa chọn qua dependency.

## 3. Xác định phạm vi thay đổi trước khi sửa mã

Để chuyển một hệ thống đang chạy sang Abstract Factory, nên xác định rõ:

| Câu hỏi khảo sát | Ví dụ cần tìm | Hướng xử lý |
| --- | --- | --- |
| Ai quyết định họ? | `if (darkMode)`, `switch (theme)`, đọc `APP_THEME` | Chuyển về ranh giới lắp ghép |
| Ai trực tiếp tạo sản phẩm? | `new LightButton()`, `new DarkDialog()` | Gom vào concrete factory |
| Client cần làm gì với sản phẩm? | `render()`, `show()` | Mô tả bằng product interface |
| Những sản phẩm nào phải cùng họ? | Nút và hộp thoại trong một màn hình | Tạo từ một `UIFactory` |
| Hành vi nào phải giữ nguyên? | Nội dung, thứ tự hiển thị, nhánh lỗi | Ghi nhận làm chuẩn đối chiếu |
| Factory sống trong phạm vi nào? | Một app, một session, một request | Quy định ownership và vòng đời |
| Có bao nhiêu điểm tạo client? | `main()`, controller, test setup | Di chuyển từng nơi dùng theo kế hoạch |

**Đừng thay nhiều thứ cùng một lúc.** Khi vừa đổi tên phương thức, vừa thay thư viện giao diện, vừa sửa luồng nghiệp vụ và vừa đưa vào factory, lỗi rất khó truy vết. Một lần tái cấu trúc tốt tạo ra các bước mà mỗi bước có mục tiêu có thể quan sát.

### 3.1. Đặt tiêu chí hoàn thành cụ thể

Sau khi tái cấu trúc, một thiết kế đáp ứng mục tiêu khi:

1. Client dùng `Button`, `Dialog` và `UIFactory`; không dùng `DarkButton`, `LightDialog` hoặc tự đọc cấu hình để chọn họ.
2. Những sản phẩm phải phối hợp được tạo từ cùng concrete factory theo phạm vi đã định.
3. Quyết định chọn factory nằm tại composition root hoặc một lớp selector mà root gọi.
4. Cấu hình sai có cách xử lý rõ ràng; không âm thầm chọn một họ ngoài ý muốn.
5. Hành vi quan sát được của các luồng Light và Dark vẫn tương đương trước và sau refactor.

Các tiêu chí này mô tả **hành vi và ranh giới phụ thuộc**, không yêu cầu phải dùng một framework DI cụ thể.

## 4. Lộ trình tái cấu trúc theo các bước nhỏ

Có thể chia công việc thành sáu bước. Mỗi bước tạo ra một trạng thái trung gian có thể đọc hiểu và đánh giá.

### Bước 0 — Ghi nhận hành vi và đường đi hiện tại

Trước khi chuyển trách nhiệm, ghi nhận ít nhất hai trường hợp:

~~~text
theme=light:
  [Light] Button: Xác nhận đặt phòng
  [Light] Dialog: Đặt phòng thành công

theme=dark:
  [Dark] Button: Xác nhận đặt phòng
  [Dark] Dialog: Đặt phòng thành công
~~~

Nếu có xử lý sự kiện, trạng thái hoặc thứ tự lời gọi quan trọng, phải ghi nhận cả những đặc điểm đó. Không nên chỉ kiểm tra ứng dụng «khởi động được».

Ở dự án thật, có thể dùng test hành vi sẵn có hoặc phép kiểm tra thủ công đã thống nhất. Đối với bài viết này, các đầu ra console chỉ là **mô phỏng hành vi** để dễ theo dõi.

### Bước 1 — Bảo đảm có interface cho từng loại sản phẩm

Trích phần hành vi chung mà client cần:

~~~java
interface Button {
    void render(String label);
}

interface Dialog {
    void show(String message);
}
~~~

Giữ nguyên các lớp hiện tại rồi cho chúng triển khai interface. Nếu chúng đã implements interface, bước này chỉ cần xác minh hợp đồng đủ phù hợp.

~~~java
class LightButton implements Button {
    @Override
    public void render(String label) {
        System.out.println("[Light] Button: " + label);
    }
}

// DarkButton cũng implements Button với cùng hợp đồng.
~~~

**Vì sao làm trước?** Chỉ khi client phụ thuộc vào product interface thì việc đổi factory mới không làm client buộc phải biết kiểu sản phẩm cụ thể. Không nên mang các phương thức riêng Light/Dark vào hợp đồng chung chỉ để tiện di chuyển mã.

### Bước 2 — Tạo abstract factory và concrete factory

Khai báo một phương thức cho mỗi loại sản phẩm cần đồng bộ:

~~~java
interface UIFactory {
    Button createButton();
    Dialog createDialog();
}
~~~

Hiện thực mỗi họ ở một factory:

~~~java
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
~~~

Lúc này, mã tạo sản phẩm của từng họ đã được **gom và đặt tên rõ ràng**. Có thể xác minh riêng rằng `LightUIFactory` trả về sản phẩm Light cho cả Button và Dialog, tương tự với Dark.

Chưa cần sửa đồng loạt mọi màn hình. Các concrete factory mới có thể tồn tại song song với mã client cũ trong một giai đoạn chuyển đổi ngắn.

### Bước 3 — Chuyển một client sang nhận factory qua constructor

Chọn một màn hình đơn giản trước. Thay vì để màn hình tự tạo lớp cụ thể, truyền `UIFactory` vào:

~~~java
class BookingScreen {
    private final Button confirmButton;
    private final Dialog confirmationDialog;

    BookingScreen(UIFactory factory) {
        this.confirmButton = factory.createButton();
        this.confirmationDialog = factory.createDialog();
    }

    void show() {
        confirmButton.render("Xác nhận đặt phòng");
        confirmationDialog.show("Đặt phòng thành công");
    }
}
~~~

Trong giai đoạn này, **điểm gọi màn hình** có thể khởi tạo factory ngay cạnh nơi gọi:

~~~java
// Điểm gọi tạm thời trong quá trình chuyển đổi.
UIFactory factory = darkMode
        ? new DarkUIFactory()
        : new LightUIFactory();

BookingScreen screen = new BookingScreen(factory);
screen.show();
~~~

Cách làm này đã loại bỏ quyết định Light/Dark **bên trong `BookingScreen`**, nhưng quyết định có thể vẫn đang nằm rải rác ở nhiều điểm gọi. Đây là **trạng thái trung gian**, chưa phải đích cuối cùng.

Điểm mạnh của bước này: có thể chuyển từng màn hình mà không buộc mọi màn hình đồng thời thay đổi constructor. Cần giữ phần mã tạm thời trong phạm vi được quản lý và có kế hoạch loại bỏ.

### Bước 4 — Tập trung quyết định chọn họ ở composition root

Khi các client đã nhận `UIFactory`, gom việc đọc cấu hình và chọn concrete factory ở nơi lắp ghép ứng dụng:

~~~java
final Theme theme = Theme.parse(rawTheme);
final UIFactory factory = chooseFactory(theme);

BookingScreen bookingScreen = new BookingScreen(factory);
HelpScreen helpScreen = new HelpScreen(factory);
~~~

Lưu ý những vai trò:

- `Theme.parse(rawTheme)` kiểm tra và chuyển cấu hình thành giá trị có kiểu rõ ràng.
- `chooseFactory(theme)` ánh xạ một theme hợp lệ thành concrete factory.
- Composition root cấp **cùng factory** cho hai màn hình thuộc cùng phạm vi.
- `BookingScreen` và `HelpScreen` không nhận cờ `darkMode` và không biết tên theme.

Không nhất thiết gộp phân tích cấu hình và tạo factory vào một hàm lớn. Có thể tách `ThemeResolver` hoặc `UIFactorySelector` để dễ kiểm tra, miễn **composition root vẫn là nơi điều phối lựa chọn và lắp ghép**.

### Bước 5 — Di chuyển các client còn lại và dọn nhánh cũ

Sau khi một màn hình đã hoạt động đúng, lần lượt chuyển các màn hình khác sang cùng cơ chế constructor injection. Mỗi nơi chuyển xong cần loại bỏ các nhánh chọn Light/Dark và các constructor cụ thể không còn sử dụng ở **client đó**.

Những dấu hiệu đã hoàn tất:

~~~text
Client: không còn if (darkMode), new LightButton(), new DarkDialog().
Factory: giữ các câu lệnh new ... sản phẩm cụ thể.
Composition root: giữ việc chọn LightUIFactory hoặc DarkUIFactory.
~~~

Không nên giữ **hai đường lựa chọn song song** quá lâu — một đường ở root và một đường cũ ở client — vì có thể có những màn hình chọn sai họ khi cập nhật cấu hình.

### Bước 6 — Kiểm tra hành vi và phạm vi dependency

Xác minh lại các luồng Light/Dark đã ghi nhận ở bước 0. Đồng thời kiểm tra **quan hệ phụ thuộc**:

- Một client có còn tự đọc `APP_THEME` hay gọi `new DarkButton()` không?
- Có nơi nào tạo Button từ một factory và Dialog từ một factory khác không?
- Khi thêm một họ mới, có cần sửa mã xử lý trong client không?
- Một fake factory có thể cấp cho client trong test không?
- Nếu đầu vào cấu hình không hợp lệ, ứng dụng có xử lý đúng chính sách không?

Bản refactor hoàn chỉnh có thể thay đổi **cấu trúc mã và nơi phụ thuộc**, nhưng không nên tự ý thay đổi nội dung hiển thị, cách điều khiển nghiệp vụ hoặc kết quả xử lý của người dùng.

## 5. Java hoàn chỉnh: chọn một factory tại composition root

Chương trình sau thể hiện **trạng thái sau tái cấu trúc**. Có hai họ sản phẩm (`Light` và `Dark`), hai loại sản phẩm (`Button` và `Dialog`), cùng hai màn hình dùng chung lựa chọn.

Để ví dụ tự chứa, `main()` đóng vai trò composition root. Trường hợp không có đối số được đặc tả là mặc định Light; nếu truyền đối số nhưng tên chủ đề không hợp lệ, chương trình **báo lỗi**, tránh âm thầm thay ý định cấu hình.

Lưu toàn bộ mã dưới tên **`CompositionRootDemo.java`**:

~~~java
import java.util.Locale;

// 1. Abstract Products
interface Button {
    void render(String label);
}

interface Dialog {
    void show(String message);
}

// 2. Abstract Factory
interface UIFactory {
    Button createButton();
    Dialog createDialog();
}

// 3. Concrete Products: Light
class LightButton implements Button {
    @Override
    public void render(String label) {
        System.out.println("[Light] Button: " + label);
    }
}

class LightDialog implements Dialog {
    @Override
    public void show(String message) {
        System.out.println("[Light] Dialog: " + message);
    }
}

// 4. Concrete Products: Dark
class DarkButton implements Button {
    @Override
    public void render(String label) {
        System.out.println("[Dark] Button: " + label);
    }
}

class DarkDialog implements Dialog {
    @Override
    public void show(String message) {
        System.out.println("[Dark] Dialog: " + message);
    }
}

// 5. Concrete Factories
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

// 6. Client 1: sử dụng cả Button và Dialog
class BookingScreen {
    private final Button button;
    private final Dialog dialog;

    BookingScreen(UIFactory factory) {
        this.button = factory.createButton();
        this.dialog = factory.createDialog();
    }

    void show() {
        button.render("Xác nhận đặt phòng");
        dialog.show("Đặt phòng thành công");
    }
}

// 7. Client 2: sử dụng Dialog, không chọn theme
class HelpScreen {
    private final Dialog dialog;

    HelpScreen(UIFactory factory) {
        this.dialog = factory.createDialog();
    }

    void show() {
        dialog.show("Hướng dẫn đặt phòng");
    }
}

// 8. Giá trị cấu hình đã được xác thực
enum Theme {
    LIGHT, DARK;

    static Theme parse(String raw) {
        if (raw == null) {
            // Ví dụ quy định không có lựa chọn nghĩa là dùng Light.
            return LIGHT;
        }

        String value = raw.trim()
                .toLowerCase(Locale.ROOT);

        switch (value) {
            case "light":
                return LIGHT;
            case "dark":
                return DARK;
            default:
                throw new IllegalArgumentException(
                    "Theme không hợp lệ: hãy chọn 'light' hoặc 'dark'."
                );
        }
    }
}

// 9. Composition root
public class CompositionRootDemo {
    private static UIFactory chooseFactory(Theme theme) {
        switch (theme) {
            case LIGHT:
                return new LightUIFactory();
            case DARK:
                return new DarkUIFactory();
            default:
                throw new IllegalStateException(
                    "Chưa có factory cho theme " + theme
                );
        }
    }

    public static void main(String[] args) {
        if (args.length > 1) {
            System.err.println(
                "Cách dùng: java CompositionRootDemo [light|dark]"
            );
            System.exit(2);
            return;
        }

        try {
            String rawTheme = args.length == 0
                    ? null
                    : args[0];

            // Đọc/kiểm tra cấu hình một lần.
            Theme theme = Theme.parse(rawTheme);

            // Chọn đúng một concrete factory cho phạm vi app.
            UIFactory factory = chooseFactory(theme);

            // Cấp cùng factory cho các client liên quan.
            BookingScreen booking = new BookingScreen(factory);
            HelpScreen help = new HelpScreen(factory);

            booking.show();
            help.show();
        } catch (IllegalArgumentException ex) {
            System.err.println("[ERROR] " + ex.getMessage());
            System.exit(2);
        }
    }
}
~~~

### 5.1. Chạy ví dụ

Biên dịch và chạy bằng JDK:

~~~bash
javac -encoding UTF-8 CompositionRootDemo.java
java CompositionRootDemo
java CompositionRootDemo dark
java CompositionRootDemo drak
~~~

Không truyền đối số, chương trình hiển thị:

~~~text
[Light] Button: Xác nhận đặt phòng
[Light] Dialog: Đặt phòng thành công
[Light] Dialog: Hướng dẫn đặt phòng
~~~

Truyền `dark`, chương trình hiển thị:

~~~text
[Dark] Button: Xác nhận đặt phòng
[Dark] Dialog: Đặt phòng thành công
[Dark] Dialog: Hướng dẫn đặt phòng
~~~

Truyền `drak`, chương trình báo:

~~~text
[ERROR] Theme không hợp lệ: hãy chọn 'light' hoặc 'dark'.
~~~

Ở trường hợp sai, chương trình dùng mã thoát khác 0 (`2`). Không một màn hình nào phải quyết định nên dùng Light hay Dark.

### 5.2. Điểm nào trong mã là composition root?

Trong `main()`, đoạn:

~~~java
Theme theme = Theme.parse(rawTheme);
UIFactory factory = chooseFactory(theme);

BookingScreen booking = new BookingScreen(factory);
HelpScreen help = new HelpScreen(factory);
~~~

là nơi **kết nối các đối tượng cụ thể thành cấu trúc ứng dụng**. `chooseFactory()` chỉ là một phương thức hỗ trợ; chính `main()` điều phối nguồn cấu hình, lựa chọn factory và cấp dependency.

Chú ý rằng `chooseFactory()` biết `LightUIFactory` và `DarkUIFactory`, nhưng các màn hình **không biết hai lớp này**. Việc còn một `switch` tại ranh giới lắp ghép là điều bình thường. Abstract Factory không yêu cầu loại bỏ mọi điều kiện trong chương trình; nó yêu cầu **không phát tán quyết định chọn họ vào mã sử dụng sản phẩm**.

### 5.3. Điều gì thay đổi và điều gì được giữ nguyên?

| Thành phần | Trước khi refactor | Sau khi refactor |
| --- | --- | --- |
| `BookingScreen` | Nhận cờ và tự quyết định lớp sản phẩm | Nhận `UIFactory` và dùng product interface |
| `HelpScreen` | Tự chọn `LightDialog`/`DarkDialog` | Nhận cùng `UIFactory` |
| Cấu hình theme | Có thể bị đọc/diễn giải nhiều lần | Đọc và phân giải một lần tại root |
| Chọn lớp cụ thể | Lặp trong client | Tập trung trong concrete factory |
| Kết quả Light/Dark | Nút và hộp thoại tương ứng với theme | Giữ nguyên hành vi theo theme |
| Mở rộng họ | Phải cập nhật nhiều client | Chủ yếu thêm concrete products/factory và cập nhật selector |

Đây là tác dụng của việc **di chuyển trách nhiệm**; bản thân thuật toán xử lý màn hình vẫn là lời gọi `render()` và `show()`.

## 6. Đảm bảo mỗi bước nhỏ có thể kiểm chứng

Việc tái cấu trúc nên được thực hiện với một nhịp rõ ràng: **thay một ranh giới phụ thuộc, kiểm tra hành vi, rồi chuyển phần tiếp theo**.

| Mốc | Thay đổi chính | Bằng chứng cần có |
| --- | --- | --- |
| 0 | Ghi nhận Light/Dark hiện tại | Có kết quả chuẩn của các màn hình |
| 1 | Trích product interface | Lớp cũ implements và client cũ còn hoạt động |
| 2 | Thêm concrete factories | Mỗi factory tạo đúng các sản phẩm cùng họ |
| 3 | Chuyển một màn hình sang constructor injection | Màn hình dùng được cả Light và Dark mà không sửa logic |
| 4 | Chọn factory tại composition root | Nhiều màn hình nhận cùng lựa chọn theo phạm vi |
| 5 | Chuyển các màn hình còn lại, bỏ nhánh cũ | Client không còn điều kiện theo theme |
| 6 | Đối chiếu và kiểm tra phụ thuộc | Các hành vi cũ giữ nguyên; chỉ root biết lựa chọn họ |

### 6.1. Kiểm thử client bằng fake factory

Khi client đã nhận `UIFactory` qua constructor, có thể đưa một factory giả vào test:

~~~java
// Ví dụ bổ sung; dùng cùng Button, Dialog, UIFactory ở phần 5.
class RecordingFactory implements UIFactory {
    int buttonsCreated;
    int dialogsCreated;

    @Override
    public Button createButton() {
        buttonsCreated++;
        return label -> {};
    }

    @Override
    public Dialog createDialog() {
        dialogsCreated++;
        return message -> {};
    }
}
~~~

Vì `Button` và `Dialog` trong ví dụ đều là functional interface, các lambda trên hợp lệ.

Một phép kiểm tra nhỏ:

~~~java
RecordingFactory fake = new RecordingFactory();
new BookingScreen(fake).show();

if (fake.buttonsCreated != 1 || fake.dialogsCreated != 1) {
    throw new AssertionError("BookingScreen phải yêu cầu đủ sản phẩm");
}
~~~

Kiểm tra này xác nhận **client lấy các dependency qua factory**. Nó không đủ để chứng minh Light/Dark được vẽ đúng hoặc các sự kiện GUI vận hành chính xác. Các hành vi ấy cần kiểm tra ở mức phù hợp với ứng dụng.

### 6.2. Kiểm tra cụ thể việc tạo cùng họ

Các interface `Button` và `Dialog` không tự cấm một factory viết sai như:

~~~java
class IncorrectDarkFactory implements UIFactory {
    @Override
    public Button createButton() {
        return new DarkButton();
    }

    @Override
    public Dialog createDialog() {
        return new LightDialog(); // Sai họ.
    }
}
~~~

Mã trên vẫn có thể biên dịch vì `LightDialog` thực hiện interface `Dialog`. Vì thế cần kiểm thử **concrete factory tạo đúng bộ sản phẩm**, qua kiểu lớp trong test nội bộ hoặc tốt hơn là hành vi tương thích quan sát được theo yêu cầu thực tế.

**Không nên** thêm phương thức `getThemeName()` vào mọi Abstract Product chỉ để đáp ứng một bài test, nếu đó không phải nhu cầu của client. Chọn bằng chứng kiểm thử theo hợp đồng và quy tắc nghiệp vụ.

## 7. Những điểm dễ vướng khi di chuyển quyết định

### 7.1. Chọn factory ở mọi client thay vì ở composition root

~~~java
class BookingScreen {
    BookingScreen(String theme) {
        UIFactory factory = "dark".equals(theme)
                ? new DarkUIFactory()
                : new LightUIFactory();
        // ...
    }
}
~~~

Màn hình đã dùng factory nhưng vẫn tự lựa chọn họ. Khi thêm biến thể thứ ba, mã này vẫn phải sửa và điều kiện lại có thể bị lặp.

**Cách điều chỉnh:** thay tham số `String theme` bằng `UIFactory factory`; quyết định chọn concrete factory nằm ở nơi lắp ghép bên ngoài màn hình.

### 7.2. Đưa cấu hình môi trường vào interface sản phẩm

~~~java
interface Button {
    void render(String label);
    boolean isDarkMode();
}
~~~

Nếu `isDarkMode()` chỉ phục vụ việc client phân nhánh để quyết định tạo `Dialog` nào, thì quyết định họ vẫn chưa được di chuyển đúng chỗ.

Sản phẩm nên mô tả **khả năng nghiệp vụ của chính nó**. Factory đại diện cho họ sản phẩm, còn composition root đại diện cho việc chọn họ theo ngữ cảnh.

### 7.3. Tạo hai factory riêng cho cùng một màn hình

~~~java
Button button =
        new LightUIFactory().createButton();

Dialog dialog =
        new DarkUIFactory().createDialog();
~~~

Cách này làm mất quy tắc đồng bộ. Nếu một màn hình cần cùng theme, nó phải nhận **một lựa chọn factory nhất quán**. Có thể các sản phẩm được tạo ở nhiều thời điểm khác nhau, nhưng nguồn lựa chọn họ phải thống nhất trong phạm vi đó.

### 7.4. Dùng global mutable factory như một đường tắt

~~~java
// Ví dụ nguy hiểm trong ứng dụng nhiều phiên người dùng.
class GlobalTheme {
    static UIFactory currentFactory;
}
~~~

Một người dùng đổi theme có thể ảnh hưởng tới người dùng khác nếu mọi client đọc cùng biến static đang thay đổi. Điều này cũng làm test phụ thuộc vào thứ tự chạy.

**Cách điều chỉnh:** truyền dependency theo phạm vi phù hợp qua constructor hoặc cơ chế DI; nếu theme theo session, mỗi session nhận factory tương ứng. Một factory không nhất thiết là Singleton.

### 7.5. Mặc định cho mọi cấu hình sai

~~~java
UIFactory factory = "dark".equalsIgnoreCase(raw)
        ? new DarkUIFactory()
        : new LightUIFactory();
~~~

Nếu `raw = "drak"`, ứng dụng âm thầm chọn Light. Với cấu hình quan trọng, đây là lỗi vận hành.

Trong ví dụ tự chạy, **không cung cấp theme** được coi là mặc định Light theo hợp đồng, còn **giá trị đã cung cấp nhưng sai** dẫn tới báo lỗi. Chính sách fallback khác có thể được dùng nếu thực sự được phép, nhưng phải công bố và có cảnh báo.

### 7.6. Trộn việc tái cấu trúc với thay đổi hành vi

Chuyển `new DarkDialog()` về factory không phải lúc đổi nội dung thông báo, thay thứ tự gọi nghiệp vụ hoặc sửa toàn bộ vòng đời sản phẩm. Những thay đổi ấy nên được tách nếu không bắt buộc.

Một cách dễ đánh giá là giữ tên API và đầu ra cũ trong bước chuyển dependency, sau đó mở riêng công việc cải tiến chức năng. Nếu cần thêm phương thức vào interface, cân nhắc phạm vi ảnh hưởng của **mọi concrete factory**.

### 7.7. Đổi constructor công khai quá nhanh

Trong thư viện đang được module khác dùng, sửa:

~~~java
BookingScreen(boolean darkMode)
~~~

thành:

~~~java
BookingScreen(UIFactory factory)
~~~

có thể làm hỏng mã nguồn của các caller ngoài phạm vi refactor. Cần đánh giá **khả năng tương thích API**, chuyển những điểm gọi đã biết và nếu cần thì có giai đoạn adapter/constructor tương thích cũ với kế hoạch loại bỏ rõ ràng.

Constructor cũ có thể tạm ủy quyền cho cơ chế chọn factory, nhưng **không nên giữ mã chọn biến thể ở client lâu dài** vì đây là đích cần loại bỏ. Với ứng dụng nội bộ không có người dùng API bên ngoài, đôi khi sửa trực tiếp caller trong cùng một thay đổi nhỏ sẽ đơn giản hơn.

## 8. Nếu theme thay đổi khi ứng dụng đang chạy?

Composition root ở lúc khởi động chỉ là **một trường hợp**. Một ứng dụng cho phép người dùng đổi giao diện ngay lập tức cần một ranh giới lắp ghép phù hợp với phạm vi cập nhật.

Giả sử `BookingScreen` tạo `LightButton` trong constructor. Khi cấu hình đổi sang Dark, việc thay biến factory ở nơi khác **không tự biến `LightButton` thành `DarkButton`**. Abstract Factory kiểm soát **những lần khởi tạo**, không tự thay đổi các instance đã tồn tại.

Một quy trình cập nhật có thể là:

~~~text
Người dùng chọn Dark
→ Kiểm tra giá trị theme
→ Lấy factory Dark cho phạm vi giao diện
→ Tạo lại bộ thành phần liên quan hoặc cập nhật chúng theo thiết kế UI
→ Thay thế màn hình/thành phần cũ có kiểm soát
~~~

Nếu cần giữ form đang nhập, con trỏ, trạng thái checkbox hoặc tài nguyên GUI, cần quyết định cách **chuyển trạng thái** và **giải phóng tài nguyên**. Những việc đó thuộc quản lý vòng đời và giao diện, không tự động có được khi dùng Abstract Factory.

Trong các hệ thống nhiều tenant hoặc nhiều request, hãy bảo đảm các sản phẩm cùng request sử dụng **cùng snapshot cấu hình**. Đừng đọc lại cấu hình ở giữa mỗi lời gọi `createButton()` và `createDialog()`, vì lúc đó hai sản phẩm có thể được chọn từ hai họ khác nhau.

## 9. Khi nào nên và không nên đưa ra composition root?

Một nguyên tắc có ích là phân biệt **«client phải dùng đối tượng như thế nào»** với **«ứng dụng tạo và cấp implementation nào»**.

| Quyết định | Vị trí thường phù hợp | Lý do |
| --- | --- | --- |
| Có dùng giao diện Light hay Dark? | Composition root hoặc bộ chọn do root gọi | Đó là quyết định cấu hình chọn họ |
| `DarkUIFactory` tạo lớp `DarkButton` nào? | `DarkUIFactory` | Factory biết cụ thể sản phẩm trong họ |
| Nút hiển thị nội dung gì? | Màn hình hoặc logic sử dụng | Đây là nội dung/hành vi của client |
| Khi nào hiển thị Dialog? | Client hoặc logic nghiệp vụ | Đây là luồng sử dụng sản phẩm |
| Có tạo lại màn hình khi theme đổi không? | Tầng điều phối giao diện/vòng đời | Cần quản lý instance và trạng thái |
| Khi cấu hình sai thì dừng hay fallback? | Cơ chế cấu hình ở ranh giới lắp ghép | Phụ thuộc yêu cầu vận hành |
| `createDialog()` có luôn tạo instance mới không? | Hợp đồng factory và concrete factory | Phụ thuộc quy tắc vòng đời sản phẩm |

**Không nên gom mọi logic vào `main()`.** Composition root có thể gọi `ThemeResolver` và `FactorySelector` chuyên trách. Điểm cốt lõi là những phần còn lại của ứng dụng **nhận dependency đã chọn**, thay vì tự tái diễn quyết định.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** `BookingScreen` đã gọi `factory.createButton()` nhưng constructor vẫn nhận `boolean darkMode` và tự tạo `DarkUIFactory`. Đã đạt mục tiêu chưa?

**Trả lời:** Chưa hoàn toàn. Quyết định chọn họ vẫn ở client. Cần truyền `UIFactory` đã được chọn từ composition root vào màn hình.

**Câu 2.** Vì sao nên chuyển một màn hình trước khi chuyển toàn bộ hệ thống?

**Trả lời:** Để có một thay đổi nhỏ, dễ đối chiếu với hành vi cũ. Khi cách nhận factory và dùng product interface đã ổn định, có thể áp dụng cho các client khác mà dễ xác định nguồn lỗi.

**Câu 3.** Một factory có tạo `DarkButton` và `LightDialog` mà Java vẫn biên dịch được không?

**Trả lời:** Có thể, vì hai dialog đều thực hiện interface `Dialog`. Tính tương thích của họ phải được bảo đảm bằng quy tắc triển khai và kiểm tra phù hợp.

**Câu 4.** Nếu mỗi người dùng có theme khác nhau, factory có nên là biến static toàn cục không?

**Trả lời:** Thường không. Cần cấp factory theo phạm vi người dùng hoặc phiên để tránh một lựa chọn ảnh hưởng không mong muốn tới người khác.

**Câu 5.** Có thể giữ `switch (theme)` tại `main()` không?

**Trả lời:** Có. Chọn factory là trách nhiệm của composition root; Abstract Factory không cấm mọi `switch`. Điều cần tránh là `switch` bị lặp trong các client đang sử dụng sản phẩm.

**Câu 6.** Khi người dùng đổi từ Light sang Dark, vì sao thay factory chưa làm giao diện cũ tự cập nhật?

**Trả lời:** Các đối tượng Light đã được tạo và có vòng đời riêng. Cần tạo lại hoặc cập nhật chúng thông qua cơ chế giao diện phù hợp.

**Câu 7.** Thêm họ High Contrast cần chỉnh sửa mã ở đâu?

**Trả lời:** Thêm concrete product, concrete factory và cập nhật nơi chọn factory. Các client dùng interface chung thường không cần sửa, miễn hợp đồng sản phẩm không thay đổi.

## 11. Kết luận

Khi tái cấu trúc sang **Abstract Factory**, di chuyển quyết định chọn họ về **composition root** giúp những client như `BookingScreen` chỉ còn phụ thuộc vào `UIFactory`, `Button` và `Dialog`. Concrete factory đảm nhiệm tạo các sản phẩm tương thích trong cùng họ, còn root quyết định họ nào được dùng theo cấu hình và phạm vi sử dụng.

Thực hiện theo các bước nhỏ — ghi nhận hành vi, trích product interface, thêm factory, chuyển từng client qua constructor injection, tập trung lựa chọn ở root và dọn nhánh cũ — giúp thay đổi dễ kiểm tra và hạn chế lỗi. Đích cuối là **một quyết định chọn họ nhất quán ở ranh giới lắp ghép**, trong khi logic sử dụng sản phẩm tiếp tục ổn định khi đổi giữa các biến thể.
