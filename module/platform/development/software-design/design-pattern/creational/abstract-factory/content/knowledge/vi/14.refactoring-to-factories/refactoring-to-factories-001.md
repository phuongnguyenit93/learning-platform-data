# Nhận diện điểm khởi tạo trùng lặp và điều kiện chọn biến thể trong mã Java hiện hữu

Trong quá trình **tái cấu trúc** một ứng dụng Java, việc phát hiện đúng nơi mã đang tạo đối tượng thường quan trọng hơn việc vội vàng thêm một lớp có tên `Factory`. Với mẫu thiết kế **Abstract Factory**, điều cần nhận ra là **nhiều nơi đang chọn và khởi tạo những nhóm đối tượng có liên quan, theo cùng một biến thể**. Khi những lựa chọn này nằm rải rác trong mã nghiệp vụ, việc thêm biến thể mới dễ khiến hàng loạt lớp phải sửa theo.

Bài học thuộc mạch **Học về abstract factory trong design pattern** của module `SOFTWARE_DESIGN_DESIGN_PATTERN_CREATIONAL_ABSTRACT_FACTORY`. Mục tiêu ở đây là **đọc và chẩn đoán mã Java hiện hữu**: xác định điểm khởi tạo lặp lại, truy vết điều kiện chọn biến thể, nhận diện nhóm sản phẩm cần tương thích và quyết định khi nào Abstract Factory là một hướng tái cấu trúc hợp lý.

Sau bài này, bạn cần có khả năng trả lời ba câu hỏi khi xem một đoạn mã: **đối tượng được tạo ở đâu?**, **biến thể được quyết định ở đâu?**, và **những đối tượng nào phải được tạo theo cùng một lựa chọn?**

## 1. Quan sát từ một ví dụ Java hiện hữu

Giả sử ứng dụng có hai giao diện: trang tổng quan (`DashboardPage`) và trang thiết lập (`SettingsPage`). Mỗi trang cần một nút bấm (`Button`) và một hộp thoại (`Dialog`). Ứng dụng hỗ trợ hai bộ giao diện `LIGHT` và `DARK`; các lớp `LightButton`, `LightDialog`, `DarkButton`, `DarkDialog` đã tồn tại và hiện thực các interface tương ứng.

Đoạn mã rút gọn dưới đây thể hiện cách hai trang đang tự chọn sản phẩm cụ thể:

~~~java
enum Theme {
    LIGHT, DARK
}

interface Button {
    void render();
}

interface Dialog {
    void open();
}

// Các lớp LightButton, DarkButton thực hiện Button;
// LightDialog, DarkDialog thực hiện Dialog.

final class DashboardPage {
    void show(Theme theme) {
        Button button;
        Dialog dialog;

        if (theme == Theme.LIGHT) {
            button = new LightButton();
            dialog = new LightDialog();
        } else {
            button = new DarkButton();
            dialog = new DarkDialog();
        }

        button.render();
        dialog.open();
    }
}

final class SettingsPage {
    void show(Theme theme) {
        Button button;
        Dialog dialog;

        if (theme == Theme.LIGHT) {
            button = new LightButton();
            dialog = new LightDialog();
        } else {
            button = new DarkButton();
            dialog = new DarkDialog();
        }

        dialog.open();
        button.render();
    }
}
~~~

Mã trên vẫn có thể chạy đúng. Vấn đề bộc lộ khi cần thêm `HIGH_CONTRAST`, đổi constructor của `DarkDialog`, hoặc bảo đảm mọi màn hình dùng cùng một bộ giao diện.

Hãy quan sát riêng ba dấu hiệu:

1. **Khởi tạo bị lặp:** cả hai trang đều gọi `new LightButton()`, `new LightDialog()`, `new DarkButton()` và `new DarkDialog()`.
2. **Cùng một điều kiện chọn biến thể:** cả hai trang đều hỏi `theme == Theme.LIGHT` để quyết định các lớp cụ thể.
3. **Các sản phẩm đi theo một họ:** nếu chọn `LIGHT`, cả nút và hộp thoại phải thuộc họ `LIGHT`; nếu chọn `DARK`, cả hai phải thuộc họ `DARK`.

Dấu hiệu thứ ba là điểm quyết định: bài toán có **một họ sản phẩm liên quan**. Chỉ nhìn thấy `new` hoặc `if` chưa đủ để kết luận cần Abstract Factory.

## 2. Điểm khởi tạo trùng lặp không chỉ là những dòng giống hệt nhau

Một **điểm khởi tạo** là vị trí chịu trách nhiệm quyết định và tạo ra một đối tượng, chẳng hạn gọi constructor, gọi phương thức tạo tĩnh hoặc yêu cầu một thành phần khác cấp đối tượng.

Trong mã Java, hãy chú ý các dạng sau:

| Dạng xuất hiện | Ví dụ | Điều cần hỏi |
| --- | --- | --- |
| Gọi constructor trực tiếp | `new LightButton()` | Có bao nhiêu nơi phụ thuộc vào lớp cụ thể này? |
| Tạo theo nhánh điều kiện | `theme == LIGHT ? new LightButton() : new DarkButton()` | Điều kiện tương tự có lặp ở nơi khác không? |
| Dùng `switch` để chọn lớp | `switch (theme) { ... }` | Có nhiều sản phẩm cùng phụ thuộc vào `theme` không? |
| Hàm tạo tĩnh hoặc hàm trợ giúp | `Widgets.newButton(theme)` | Logic chọn biến thể đã được gom hết hay vẫn rải rác? |
| Cấu hình hoặc ánh xạ | `creators.get(theme).get()` | Bộ ánh xạ có tạo một họ sản phẩm nhất quán không? |
| Khởi tạo gián tiếp qua DI | `provider.get()` | Có nơi nào vẫn tự chọn các implementation không? |

**Trùng lặp cú pháp** dễ nhận thấy khi cùng một khối `if/else` được sao chép. **Trùng lặp về quyết định** tinh vi hơn: hai đoạn mã có thể khác cách viết nhưng cùng mã hóa quy tắc *“chọn LIGHT thì tạo LightButton và LightDialog”*.

Ví dụ, hai đoạn dưới đây có cùng trách nhiệm lựa chọn biến thể, dù không trùng từng dòng:

~~~java
// Nơi A: if/else
Button button = theme == Theme.LIGHT
        ? new LightButton()
        : new DarkButton();

// Nơi B: switch
Dialog dialog = switch (theme) {
    case LIGHT -> new LightDialog();
    case DARK -> new DarkDialog();
};
~~~

Nếu cả hai đều thuộc cùng một luồng tạo giao diện, quy tắc chọn họ sản phẩm vẫn bị chia đôi. Đổi tên lớp, thêm biến thể hoặc thay quy ước tương thích sẽ tác động đến nhiều điểm.

Ngược lại, hai lệnh `new ArrayList<>()` ở hai phương thức độc lập **không tự động** tạo nên vấn đề Abstract Factory. Việc tạo đối tượng thường xuyên là bình thường; điều cần tìm là **sự phụ thuộc lặp vào các loại sản phẩm cụ thể và quy tắc chọn biến thể**.

## 3. Lần theo điều kiện chọn biến thể

**Biến thể** là một lựa chọn làm thay đổi implementation được tạo ra: hệ điều hành, chủ đề giao diện, nhà cung cấp dịch vụ, định dạng tích hợp hoặc một nhóm sản phẩm tương thích khác.

Trong mã cũ, biến thể có thể xuất hiện dưới nhiều hình thức:

- Một `enum`: `Theme.LIGHT`, `Platform.WINDOWS`, `Provider.A`.
- Một chuỗi cấu hình: `"dark"`, `"windows"`; chú ý cả trường hợp so sánh trực tiếp với chuỗi.
- Điều kiện môi trường: hệ điều hành, feature flag, cấu hình triển khai.
- Một kiểm tra kiểu: `instanceof`, phân nhánh theo tên class hoặc loại dependency.
- Một chuỗi lựa chọn được truyền sâu qua nhiều lớp: `Controller → Service → View`.

Cần phân biệt **nơi thu thập biến thể** với **nơi thực sự chọn implementation**. Ví dụ, cấu hình `theme` được đọc ở lúc khởi động là hợp lý; vấn đề là mỗi màn hình lại dùng `theme` để tự quyết định những constructor cụ thể.

Khi kiểm tra một nhánh điều kiện, hỏi theo thứ tự:

1. Nhánh này chỉ thay đổi **hành vi** hay thực sự chọn **lớp đối tượng cần tạo**?
2. Có bao nhiêu loại sản phẩm được lựa chọn dựa trên cùng một giá trị?
3. Các sản phẩm được chọn có yêu cầu đồng bộ biến thể hoặc tương thích với nhau không?
4. Quy tắc tương tự xuất hiện ở những lớp nào khác?
5. Nếu thêm một biến thể mới, phải sửa bao nhiêu vị trí?

Chẳng hạn:

~~~java
if (theme == Theme.LIGHT) {
    button = new LightButton();
    dialog = new LightDialog();
}
~~~

Nhánh này đồng thời chọn **hai sản phẩm** của họ `LIGHT`. Đó là ứng viên mạnh cho Abstract Factory. Nhưng nhánh:

~~~java
if (order.isExpress()) {
    shippingFee += 20_000;
}
~~~

chỉ thể hiện quy tắc tính phí; không có bằng chứng về một họ đối tượng cần tạo. Không nên đưa nó vào Abstract Factory chỉ vì có `if`.

## 4. Lập bản đồ các điểm khởi tạo trước khi sửa

Để tránh thay đổi thiếu sót, lập một bảng kiểm kê từ các đoạn mã tìm được:

| Vị trí | Giá trị chọn | Sản phẩm được tạo | Quy tắc cần giữ |
| --- | --- | --- | --- |
| `DashboardPage.show()` | `LIGHT` | `LightButton`, `LightDialog` | Cùng họ `LIGHT` |
| `DashboardPage.show()` | `DARK` | `DarkButton`, `DarkDialog` | Cùng họ `DARK` |
| `SettingsPage.show()` | `LIGHT` | `LightButton`, `LightDialog` | Cùng họ `LIGHT` |
| `SettingsPage.show()` | `DARK` | `DarkButton`, `DarkDialog` | Cùng họ `DARK` |

Bảng cho thấy **hai trục**: loại sản phẩm (`Button`, `Dialog`) và biến thể (`LIGHT`, `DARK`). Mỗi ô tương ứng một lớp cụ thể. Hai nơi gọi cùng biết cả bốn lớp, vì vậy thay đổi một họ sản phẩm có nguy cơ lan sang cả hai nơi.

Cách khảo sát một codebase Java:

1. **Tìm điểm tạo đối tượng:** dùng tìm kiếm trong IDE cho constructor của các lớp cụ thể hoặc mẫu `new ...`. Có thể dùng `rg` để thu hẹp danh sách ban đầu, nhưng cần đọc ngữ cảnh của từng kết quả.
2. **Nhóm theo trách nhiệm:** phân loại các vị trí theo chức năng thực tế (màn hình, bộ xuất dữ liệu, bộ tích hợp...), tránh gom những `new` không liên quan.
3. **Truy ngược nguồn lựa chọn:** xác định `theme` hoặc `provider` đến từ cấu hình, tham số, request hay trạng thái chạy; ghi rõ nơi quyết định hợp lệ.
4. **Lập ma trận sản phẩm × biến thể:** kiểm tra mỗi biến thể tạo đủ bộ sản phẩm nào, có ngoại lệ hoặc thiếu ô nào không.
5. **Đánh giá mức lan truyền:** thử trả lời “thêm biến thể C” hoặc “đổi constructor của một sản phẩm” phải cập nhật bao nhiêu lớp.
6. **Ghi nhận ràng buộc:** tham số constructor, vòng đời, caching, tài nguyên cần đóng, xử lý lỗi và yêu cầu tương thích trước khi đề xuất tái cấu trúc.

Ví dụ lệnh tìm kiếm dùng để **khám phá**, không thể thay thế việc phân tích bằng mắt:

~~~bash
rg -n 'new (Light|Dark)(Button|Dialog)' src/main/java
rg -n 'Theme\.LIGHT|Theme\.DARK|switch \(theme\)' src/main/java
~~~

Đường dẫn `src/main/java` chỉ là ví dụ của cấu trúc Maven/Gradle thông dụng. Trong dự án thực tế, có thể cần tìm cả mã test, module khác hoặc nơi tạo đối tượng qua API gián tiếp. Công cụ tìm kiếm chỉ gợi ý vị trí; nó không tự kết luận cần dùng design pattern nào.

## 5. Phân biệt tín hiệu mạnh và dấu hiệu dễ gây nhầm lẫn

| Quan sát | Đánh giá | Lý do |
| --- | --- | --- |
| Nhiều lớp tự tạo cùng **bộ** `Button` và `Dialog` theo `Theme` | **Mạnh** | Có họ sản phẩm, quy tắc tương thích và lựa chọn trùng lặp |
| Một nơi duy nhất tạo ba sản phẩm theo `Platform`, dự kiến thêm platform mới | **Có thể phù hợp** | Trách nhiệm tạo họ sản phẩm đã rõ; cân nhắc độ phức tạp hiện tại |
| Nhiều nơi chỉ tạo một loại `PaymentClient` theo `Provider` | **Chưa đủ** | Có thể chỉ cần một factory đơn giản hoặc tiêm dependency |
| Các `new User()` xuất hiện nhiều lần, không có biến thể | **Không phải tín hiệu** | Chỉ là khởi tạo dữ liệu bình thường |
| Có nhiều `if` chọn cách tính toán, không tạo đối tượng | **Không phải tín hiệu** | Bài toán có thể thuộc Strategy hoặc quy tắc nghiệp vụ thông thường |
| Đã có dependency injection chọn implementation ở một nơi | **Cần kiểm tra thêm** | Quy tắc lựa chọn có thể đã được tập trung đủ |

Một dấu hiệu quan trọng khác là **nguy cơ trộn sai biến thể**:

~~~java
Button button = new LightButton();
Dialog dialog = new DarkDialog(); // Vô tình ghép hai họ khác nhau
~~~

Các interface riêng lẻ vẫn có thể làm đoạn mã biên dịch thành công, nhưng trải nghiệm giao diện có thể thiếu nhất quán. Abstract Factory giúp một khách hàng lấy các sản phẩm từ **cùng một factory đã chọn**, giảm các điểm có thể phát sinh sai lệch đó.

## 6. Đối chiếu cấu trúc trước và sau khi gom trách nhiệm tạo đối tượng

Sơ đồ sau mô tả luồng phụ thuộc trước khi tái cấu trúc:

~~~mermaid
flowchart TD
    T["Theme: LIGHT / DARK"] --> A["DashboardPage"]
    T --> B["SettingsPage"]
    A --> C{"Tự chọn biến thể"}
    B --> D{"Tự chọn biến thể"}
    C --> L["LightButton + LightDialog"]
    C --> K["DarkButton + DarkDialog"]
    D --> L
    D --> K
~~~

`DashboardPage` và `SettingsPage` đều biết cấu trúc của cả hai họ sản phẩm. Nếu đã xác nhận các tín hiệu ở trên, có thể **đề xuất** một `UiFactory` cung cấp cả `Button` và `Dialog`:

~~~java
interface UiFactory {
    Button createButton();
    Dialog createDialog();
}

final class LightUiFactory implements UiFactory {
    @Override
    public Button createButton() {
        return new LightButton();
    }

    @Override
    public Dialog createDialog() {
        return new LightDialog();
    }
}

final class DarkUiFactory implements UiFactory {
    @Override
    public Button createButton() {
        return new DarkButton();
    }

    @Override
    public Dialog createDialog() {
        return new DarkDialog();
    }
}

final class UiFactorySelector {
    static UiFactory forTheme(Theme theme) {
        return switch (theme) {
            case LIGHT -> new LightUiFactory();
            case DARK -> new DarkUiFactory();
        };
    }
}
~~~

Đây là ví dụ cấu trúc sử dụng `switch` expression của Java 14+ (ổn định từ Java 14); với dự án Java cũ hơn có thể dùng `switch` statement hoặc `if/else`. `Theme`, `Button`, `Dialog` và các lớp sản phẩm cụ thể vẫn mang ý nghĩa như phần ví dụ ban đầu.

Khi đó, mã khách hàng chỉ yêu cầu sản phẩm qua `UiFactory`:

~~~java
final class DashboardPage {
    private final UiFactory factory;

    DashboardPage(UiFactory factory) {
        this.factory = factory;
    }

    void show() {
        Button button = factory.createButton();
        Dialog dialog = factory.createDialog();
        button.render();
        dialog.open();
    }
}

final class SettingsPage {
    private final UiFactory factory;

    SettingsPage(UiFactory factory) {
        this.factory = factory;
    }

    void show() {
        Button button = factory.createButton();
        Dialog dialog = factory.createDialog();
        dialog.open();
        button.render();
    }
}

// Tại nơi cấu hình/khởi tạo ứng dụng (composition root):
UiFactory factory = UiFactorySelector.forTheme(theme);
new DashboardPage(factory).show();
new SettingsPage(factory).show();
~~~

Khối cuối minh họa các lệnh trong một phương thức khởi tạo ứng dụng đã có biến `theme`; đó không phải những lệnh Java đặt trực tiếp ở cấp file.

~~~mermaid
flowchart TD
    T["Theme"] --> S["UiFactorySelector"]
    S --> F["UiFactory đã chọn"]
    F --> A["DashboardPage"]
    F --> B["SettingsPage"]
    F --> P["createButton / createDialog"]
    P --> Q["Các sản phẩm cùng một họ"]
~~~

Điều kiện chọn biến thể **vẫn tồn tại**, nhưng được đặt tại một ranh giới khởi tạo có chủ đích. Các trang không phải biết `LightButton`, `DarkButton` hay nhánh `if` của `Theme`. Một factory cụ thể chịu trách nhiệm cung cấp cả hai loại sản phẩm thuộc một họ.

Ví dụ chỉ thể hiện **hướng refactor** để nhìn rõ vị trí trách nhiệm. Trong hệ thống thật, cần kiểm chứng phạm vi sống của factory và sản phẩm, giá trị cấu hình thay đổi động, tham số cần truyền lúc khởi tạo, cùng tác dụng phụ của constructor trước khi thay mã cũ.

## 7. Khi nào chọn Abstract Factory, khi nào chọn giải pháp gọn hơn?

| Tình huống | Hướng cân nhắc |
| --- | --- |
| Một họ gồm nhiều loại sản phẩm liên quan; các khách hàng cần chọn cùng một biến thể | **Abstract Factory** |
| Chỉ có một loại sản phẩm thay đổi theo tham số | Factory đơn giản, Factory Method hoặc DI có thể đủ |
| Một thuật toán thay đổi theo điều kiện, không phải cách tạo cả họ đối tượng | **Strategy** hoặc tổ chức lại điều kiện nghiệp vụ |
| Chỉ cần tạo một đối tượng phụ thuộc nhiều tham số tùy chọn | Builder có thể phù hợp hơn |
| Framework DI đã lắp ráp đúng bộ implementation cho mỗi cấu hình | Tiếp tục dùng cơ chế DI; chỉ thêm interface factory khi có nhu cầu tạo họ sản phẩm tại runtime |
| Hai lớp cùng khởi tạo đối tượng giá trị đơn giản, không có quy tắc tương thích | Giữ cách tạo trực tiếp nếu mã rõ ràng |

**Abstract Factory** biểu diễn một giao diện tạo **nhiều loại sản phẩm thuộc cùng họ**; mỗi concrete factory đại diện cho một biến thể. **Factory Method** thường trao quyền cho lớp con quyết định một đối tượng cụ thể cần tạo. Cả hai đều xử lý khởi tạo, nhưng áp dụng vào những cấu trúc và nhu cầu mở rộng khác nhau.

Đừng chọn mẫu chỉ vì dự án có nhiều `new` hoặc nhiều `switch`. Nếu mới có một implementation và không có ràng buộc giữa các sản phẩm, một tầng factory mới có thể khiến việc đọc và kiểm tra mã phức tạp hơn mà chưa đem lại lợi ích.

## 8. Kiểm tra rủi ro khi đọc mã cũ

Việc gom các lệnh khởi tạo cần bảo toàn **ngữ nghĩa**, không chỉ rút ngắn số dòng:

- **Tham số constructor:** `new DarkDialog(locale, metrics)` có thể phụ thuộc thông tin chỉ có tại màn hình. Phải xác định dữ liệu này nên đi qua factory, qua phương thức `createDialog(...)` hay qua dependency được tiêm sẵn.
- **Vòng đời:** đối tượng có thể phải tạo mới mỗi lần, dùng chung có kiểm soát hoặc được đóng sau khi dùng. Không tự biến factory thành cache hoặc singleton nếu chưa chứng minh an toàn.
- **Tác dụng phụ:** constructor có thể đọc file, mở kết nối, đăng ký listener hoặc ném ngoại lệ. Dời vị trí tạo đối tượng có thể thay đổi thời điểm xảy ra tác dụng phụ.
- **Thay đổi cấu hình lúc chạy:** nếu theme có thể đổi trong một phiên, factory được chọn một lần khi khởi động có thể không phản ánh theme mới. Cần xác định điểm tái chọn factory và tái tạo sản phẩm.
- **Khả năng tương thích:** cùng là `Button` và `Dialog` chưa chứng minh chúng thuộc một họ hợp lệ. Quy ước “sản phẩm cùng bộ” cần được ghi rõ và kiểm thử.
- **Thứ tự và xử lý lỗi:** nếu ứng dụng trước đây tạo `Button` rồi `Dialog`, việc tạo sớm, tạo muộn hoặc xử lý ngoại lệ khác đi có thể làm thay đổi hành vi.
- **Giá trị `null` hoặc không hợp lệ:** trong ví dụ ban đầu, `theme == Theme.LIGHT` trả về `false` khi `theme` là `null`, nên nhánh `else` chọn `DARK`; `switch (theme)` trong ví dụ sau sẽ ném `NullPointerException`. Cần kiểm tra hợp đồng đầu vào và quyết định rõ cách xử lý trước khi đổi cấu trúc.

Trước khi thực sự refactor, nên có phép kiểm tra ở mức hành vi phù hợp:

~~~java
// Minh họa một kiểm thử đặc tính của từng họ sản phẩm.
// Sử dụng assertTrue của JUnit 5.
@Test
void lightFactoryCreatesMatchingProducts() {
    UiFactory factory = new LightUiFactory();

    assertTrue(factory.createButton() instanceof LightButton);
    assertTrue(factory.createDialog() instanceof LightDialog);
}
~~~

`@Test` và `assertTrue` cần import từ JUnit 5 trong lớp test thực tế. Kiểm tra lớp cụ thể ở đây nhằm minh họa quy tắc tạo đúng họ; với kiểm thử tích hợp, nên ưu tiên quan sát thuộc tính hiển thị hoặc hành vi từ bên ngoài khi có thể. Ngoài tính nhất quán của sản phẩm, nên kiểm tra luồng chọn `LIGHT`/`DARK`, xử lý giá trị đầu vào không hợp lệ và hành vi của trang trước/sau refactor.

## 9. Bài tập phân tích mã

### Tình huống A — Nhiều bộ đối tượng

~~~java
if (platform == Platform.WEB) {
    menu = new WebMenu();
    toolbar = new WebToolbar();
} else {
    menu = new DesktopMenu();
    toolbar = new DesktopToolbar();
}
~~~

Khối này xuất hiện trong ba lớp màn hình. Đây là **ứng viên mạnh** cho Abstract Factory nếu `Menu` và `Toolbar` phải theo cùng một nền tảng. Hãy xác định ma trận hai loại sản phẩm × hai biến thể, rồi tìm nơi có thể chọn một `UiFactory` chung.

### Tình huống B — Một đối tượng

~~~java
Notifier notifier = channel == Channel.EMAIL
        ? new EmailNotifier()
        : new SmsNotifier();
~~~

Dù cấu trúc chọn implementation rõ ràng, đoạn mã mới tạo **một loại sản phẩm**. Chưa có bằng chứng về họ sản phẩm; một factory nhỏ hoặc cơ chế DI có thể đáp ứng tốt hơn.

### Tình huống C — Điều kiện hành vi

~~~java
if (customer.isVip()) {
    discount = 0.15;
} else {
    discount = 0.05;
}
~~~

Đây không phải điểm tạo đối tượng. Nếu quy tắc chiết khấu ngày càng phức tạp, nên xem xét chính sách tính giá hoặc Strategy, không áp dụng Abstract Factory theo phản xạ.

## 10. Checklist kết luận sau khi khảo sát một module Java

Trước khi đề xuất Abstract Factory, hãy tự kiểm tra:

- [ ] Đã chỉ ra các vị trí gọi constructor, static factory hoặc provider có trách nhiệm tạo sản phẩm cụ thể.
- [ ] Đã tìm được những điều kiện `if`, `switch`, ánh xạ hoặc cấu hình quyết định biến thể.
- [ ] Đã phân biệt việc lặp **quy tắc lựa chọn** với những lệnh `new` tình cờ giống nhau.
- [ ] Đã lập ma trận **loại sản phẩm × biến thể**, xác định những đối tượng bắt buộc tương thích.
- [ ] Đã xác nhận có lý do thực tế để gom trách nhiệm tạo **cả họ sản phẩm**.
- [ ] Đã xác định điểm cấu hình/khởi tạo phù hợp để chọn factory một lần hoặc theo vòng đời thích hợp.
- [ ] Đã ghi nhận constructor arguments, tài nguyên, lỗi, thứ tự khởi tạo và việc thay đổi biến thể lúc chạy.
- [ ] Đã cân nhắc giải pháp đơn giản hơn khi chỉ có một loại sản phẩm hoặc một điều kiện nghiệp vụ.

**Điểm mấu chốt:** Trong bài toán refactoring hướng tới Abstract Factory, đối tượng cần tìm không phải bản thân từ khóa `new`; đó là **quyết định chọn một họ implementation đang bị lặp hoặc phân tán**. Khi nhận diện đúng quyết định ấy, bạn mới có cơ sở đặt ranh giới factory hợp lý và dự đoán chính xác tác động của việc thêm biến thể trong tương lai.
