# Viết unit test bằng JUnit cho từng ConcreteFactory và hợp đồng trả về

Trong mẫu thiết kế **Abstract Factory**, mỗi `ConcreteFactory` chịu trách nhiệm tạo **một họ sản phẩm có liên quan**. Kiểm thử từng factory không dừng ở việc xác nhận phương thức tạo có được gọi: cần chứng minh factory trả về sản phẩm **hợp lệ, thuộc đúng họ và sử dụng được qua các interface mà khách hàng phụ thuộc**.

Bài thuộc phần **Kiểm thử** của module `SOFTWARE_DESIGN_DESIGN_PATTERN_CREATIONAL_ABSTRACT_FACTORY`, với mục tiêu **học về Abstract Factory trong design pattern**. Ta sẽ xây dựng một ví dụ Java nhỏ, viết unit test bằng **JUnit Jupiter (JUnit 5)** cho từng `ConcreteFactory`, tái sử dụng các phép kiểm tra hợp đồng và phân biệt những bảo đảm thực sự cần kiểm tra với các chi tiết triển khai không nên ràng buộc cứng.

Sau bài này, bạn có thể:

- Xác định **hợp đồng trả về** của `AbstractFactory` và từng phương thức tạo sản phẩm.
- Viết test xác minh giá trị trả về khác `null`, đúng loại sản phẩm và đúng biến thể.
- Phát hiện lỗi một factory vô tình trộn sản phẩm từ các họ khác nhau.
- Tổ chức bộ kiểm thử dùng chung để mọi `ConcreteFactory` đều chịu cùng bộ tiêu chí.
- Quyết định khi nào cần kiểm tra lớp cụ thể, hành vi, vòng đời hoặc ngoại lệ.

## 1. Xác định chính xác thứ cần kiểm thử

Ví dụ ứng dụng có hai giao diện: `LIGHT` và `DARK`. Mỗi giao diện cần một `Button` và một `Dialog`. Một `UiFactory` đóng vai trò Abstract Factory; `LightUiFactory` và `DarkUiFactory` là hai Concrete Factory.

~~~mermaid
classDiagram
    class UiFactory {
      <<interface>>
      +createButton() Button
      +createDialog() Dialog
    }
    class LightUiFactory
    class DarkUiFactory
    class Button {
      <<interface>>
      +theme() Theme
      +render() String
    }
    class Dialog {
      <<interface>>
      +theme() Theme
      +render() String
    }
    UiFactory <|.. LightUiFactory
    UiFactory <|.. DarkUiFactory
    UiFactory ..> Button : creates
    UiFactory ..> Dialog : creates
~~~

Từ sơ đồ, hãy chuyển yêu cầu thiết kế thành **hợp đồng có thể kiểm chứng**:

| Hợp đồng | Cần xác minh | Lỗi điển hình |
| --- | --- | --- |
| `createButton()` trả về `Button` hợp lệ | Kết quả khác `null`, sử dụng được qua interface `Button` | Factory trả `null` |
| `createDialog()` trả về `Dialog` hợp lệ | Kết quả khác `null`, sử dụng được qua interface `Dialog` | Factory chưa xây dựng xong một sản phẩm |
| Factory tạo **đúng họ** | Với `LightUiFactory`, cả hai sản phẩm có `theme() == LIGHT`; tương tự `DARK` | `DarkUiFactory` trả về `LightDialog` |
| Các sản phẩm **nhất quán** | `button.theme() == dialog.theme()` | Hai sản phẩm không tương thích về giao diện |
| Sản phẩm vận hành theo API chung | Gọi `render()` thành công và có đầu ra hợp lệ theo quy ước ví dụ | Đối tượng được tạo nhưng không dùng được |

Ở đây, `theme()` là **một phần của hợp đồng công khai trong ví dụ** để quan sát họ sản phẩm. Trong hệ thống thực, có thể kiểm tra họ sản phẩm bằng thuộc tính có sẵn, hành vi mà người dùng nhìn thấy, cấu hình được công bố hoặc bằng kiểm thử tích hợp. Không cần bổ sung một getter chỉ phục vụ test nếu API vốn không đòi hỏi nó.

Chú ý: các interface đã quy định kiểu trả về của phương thức tại thời điểm biên dịch; unit test nhằm xác minh **kết quả runtime** và những bất biến mà hệ thống kiểu Java chưa bảo đảm, đặc biệt là khác `null` và cùng họ.

## 2. Mã Java để làm đối tượng kiểm thử

Để ví dụ có thể theo dõi độc lập, phần dưới sử dụng một file `src/main/java/example/abstractfactory/UiModel.java`. Tất cả các kiểu đều là *package-private* để có thể đặt cùng một file Java; trong dự án thật có thể tách interface và lớp triển khai thành những file riêng.

~~~java
package example.abstractfactory;

enum Theme {
    LIGHT, DARK
}

interface Button {
    Theme theme();
    String render();
}

interface Dialog {
    Theme theme();
    String render();
}

final class LightButton implements Button {
    @Override
    public Theme theme() {
        return Theme.LIGHT;
    }

    @Override
    public String render() {
        return "<button class=\"light\">OK</button>";
    }
}

final class LightDialog implements Dialog {
    @Override
    public Theme theme() {
        return Theme.LIGHT;
    }

    @Override
    public String render() {
        return "<dialog class=\"light\">Notice</dialog>";
    }
}

final class DarkButton implements Button {
    @Override
    public Theme theme() {
        return Theme.DARK;
    }

    @Override
    public String render() {
        return "<button class=\"dark\">OK</button>";
    }
}

final class DarkDialog implements Dialog {
    @Override
    public Theme theme() {
        return Theme.DARK;
    }

    @Override
    public String render() {
        return "<dialog class=\"dark\">Notice</dialog>";
    }
}

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
~~~

Điểm thiết kế cần nhớ: `UiFactory` chỉ hứa cung cấp `Button` và `Dialog`; **mỗi concrete factory** quyết định bộ implementation tương ứng. Vì vậy test vừa cần xác minh hợp đồng chung của `UiFactory`, vừa cần xác minh factory cụ thể được nối với đúng họ sản phẩm.

Trong ví dụ, `render()` trả về chuỗi để minh họa một hành vi có thể quan sát mà không cần thư viện giao diện. Các ứng dụng Android, Swing, JavaFX hoặc ứng dụng web server-side sẽ có cách quan sát hành vi khác.

## 3. Viết test trực tiếp cho `LightUiFactory`

JUnit Jupiter dùng annotation `@Test` để nhận diện phương thức kiểm thử và cung cấp các assertion như `assertNotNull`, `assertEquals`, `assertInstanceOf`. Ví dụ sau đặt tại `src/test/java/example/abstractfactory/LightUiFactoryTest.java`, cùng package với mã sản phẩm:

~~~java
package example.abstractfactory;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class LightUiFactoryTest {

    @Test
    void createsNonNullProductsOfLightFamily() {
        UiFactory factory = new LightUiFactory();

        Button button = factory.createButton();
        Dialog dialog = factory.createDialog();

        assertNotNull(button, "Button must not be null");
        assertNotNull(dialog, "Dialog must not be null");

        assertAll("LIGHT family",
                () -> assertEquals(Theme.LIGHT, button.theme()),
                () -> assertEquals(Theme.LIGHT, dialog.theme()),
                () -> assertEquals(button.theme(), dialog.theme())
        );
    }

    @Test
    void returnsExpectedLightImplementations() {
        UiFactory factory = new LightUiFactory();

        assertInstanceOf(LightButton.class, factory.createButton());
        assertInstanceOf(LightDialog.class, factory.createDialog());
    }

    @Test
    void productsCanRenderThroughTheirInterfaces() {
        UiFactory factory = new LightUiFactory();

        Button button = factory.createButton();
        Dialog dialog = factory.createDialog();

        String buttonMarkup = assertDoesNotThrow(button::render);
        String dialogMarkup = assertDoesNotThrow(dialog::render);

        assertFalse(buttonMarkup.trim().isEmpty());
        assertFalse(dialogMarkup.trim().isEmpty());
    }
}
~~~

Ba test giải quyết ba câu hỏi khác nhau:

1. **Factory có trả về một bộ sản phẩm đầy đủ, cùng họ không?** Kiểm tra `null` trước khi gọi `theme()` để khi có lỗi, thông báo dễ hiểu và không biến việc thiếu sản phẩm thành `NullPointerException` khó đọc.
2. **Factory cụ thể này có trả về đúng các lớp đã định không?** `assertInstanceOf` phát hiện trường hợp ánh xạ sai `LightButton` hoặc `LightDialog`. Chỉ giữ phép kiểm tra này khi mapping tới lớp cụ thể thực sự là yêu cầu được bảo đảm.
3. **Sản phẩm có sử dụng được qua abstraction không?** `assertDoesNotThrow` và kiểm tra chuỗi không rỗng chứng minh luồng gọi cơ bản hoạt động. Trong sản phẩm thật, cần kiểm chứng hành vi có ý nghĩa hơn nếu `render()` có quy ước chặt chẽ.

`assertAll` gom các assertion cùng nhóm để báo nhiều sai lệch trong một lần chạy. Tuy nhiên, `assertAll` không thay thế kiểm tra `null` trước khi truy cập phương thức của kết quả.

## 4. Viết test tương ứng cho `DarkUiFactory`

File `src/test/java/example/abstractfactory/DarkUiFactoryTest.java`:

~~~java
package example.abstractfactory;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class DarkUiFactoryTest {

    @Test
    void createsNonNullProductsOfDarkFamily() {
        UiFactory factory = new DarkUiFactory();

        Button button = factory.createButton();
        Dialog dialog = factory.createDialog();

        assertNotNull(button, "Button must not be null");
        assertNotNull(dialog, "Dialog must not be null");

        assertAll("DARK family",
                () -> assertEquals(Theme.DARK, button.theme()),
                () -> assertEquals(Theme.DARK, dialog.theme()),
                () -> assertEquals(button.theme(), dialog.theme())
        );
    }

    @Test
    void returnsExpectedDarkImplementations() {
        UiFactory factory = new DarkUiFactory();

        assertInstanceOf(DarkButton.class, factory.createButton());
        assertInstanceOf(DarkDialog.class, factory.createDialog());
    }

    @Test
    void productsCanRenderThroughTheirInterfaces() {
        UiFactory factory = new DarkUiFactory();

        Button button = factory.createButton();
        Dialog dialog = factory.createDialog();

        String buttonMarkup = assertDoesNotThrow(button::render);
        String dialogMarkup = assertDoesNotThrow(dialog::render);

        assertFalse(buttonMarkup.trim().isEmpty());
        assertFalse(dialogMarkup.trim().isEmpty());
    }
}
~~~

Mặc dù test này gần giống test của `LightUiFactory`, việc gọi trực tiếp `new DarkUiFactory()` là cần thiết: không thể lấy kết quả kiểm thử của factory sáng làm bằng chứng cho factory tối. Nếu `DarkUiFactory.createDialog()` vô tình trả `new LightDialog()`, test này sẽ báo lỗi ngay.

Khi số biến thể tăng, sao chép nhiều test giống nhau dễ dẫn đến bỏ quên một tiêu chí ở một factory. Phần tiếp theo tổ chức chúng thành một **bộ kiểm thử hợp đồng dùng chung**.

## 5. Tái sử dụng cùng bộ kiểm thử hợp đồng cho mọi ConcreteFactory

JUnit Jupiter hỗ trợ thừa kế các phương thức `@Test` từ một lớp cha trừu tượng. Ta tạo một lớp test chuẩn có hai thông tin tùy biến: **factory cần kiểm tra** và **biến thể kỳ vọng**.

File `src/test/java/example/abstractfactory/UiFactoryContractTest.java`:

~~~java
package example.abstractfactory;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

abstract class UiFactoryContractTest {

    protected abstract UiFactory createFactory();

    protected abstract Theme expectedTheme();

    @Test
    void createsCompleteAndConsistentFamily() {
        UiFactory factory = createFactory();
        assertNotNull(factory);

        Button button = factory.createButton();
        Dialog dialog = factory.createDialog();
        assertNotNull(button, "createButton() must not return null");
        assertNotNull(dialog, "createDialog() must not return null");

        assertAll("family contract",
                () -> assertEquals(expectedTheme(), button.theme()),
                () -> assertEquals(expectedTheme(), dialog.theme()),
                () -> assertEquals(button.theme(), dialog.theme())
        );
    }

    @Test
    void createdProductsSupportTheirPublicOperations() {
        UiFactory factory = createFactory();

        Button button = factory.createButton();
        Dialog dialog = factory.createDialog();
        assertNotNull(button);
        assertNotNull(dialog);

        String buttonMarkup = assertDoesNotThrow(button::render);
        String dialogMarkup = assertDoesNotThrow(dialog::render);

        assertNotNull(buttonMarkup);
        assertNotNull(dialogMarkup);
        assertFalse(buttonMarkup.trim().isEmpty());
        assertFalse(dialogMarkup.trim().isEmpty());
    }
}
~~~

Kế thừa bộ test chuẩn cho từng concrete factory, chỉ khai báo các đặc điểm riêng.

File `LightUiFactoryTest.java` trong phương án **dùng lại hợp đồng**:

~~~java
package example.abstractfactory;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;

class LightUiFactoryTest extends UiFactoryContractTest {

    @Override
    protected UiFactory createFactory() {
        return new LightUiFactory();
    }

    @Override
    protected Theme expectedTheme() {
        return Theme.LIGHT;
    }

    @Test
    void mapsToTheExpectedImplementations() {
        UiFactory factory = createFactory();
        assertInstanceOf(LightButton.class, factory.createButton());
        assertInstanceOf(LightDialog.class, factory.createDialog());
    }
}
~~~

File `DarkUiFactoryTest.java` trong phương án **dùng lại hợp đồng**:

~~~java
package example.abstractfactory;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;

class DarkUiFactoryTest extends UiFactoryContractTest {

    @Override
    protected UiFactory createFactory() {
        return new DarkUiFactory();
    }

    @Override
    protected Theme expectedTheme() {
        return Theme.DARK;
    }

    @Test
    void mapsToTheExpectedImplementations() {
        UiFactory factory = createFactory();
        assertInstanceOf(DarkButton.class, factory.createButton());
        assertInstanceOf(DarkDialog.class, factory.createDialog());
    }
}
~~~

**Chọn một trong hai cách tổ chức:** dùng các lớp test trực tiếp ở mục 3–4 **hoặc thay chúng bằng** hai lớp test kế thừa ở mục này. Không đặt hai phiên bản trùng tên `LightUiFactoryTest` hay `DarkUiFactoryTest` trong cùng package.

Với phương án kế thừa, JUnit chạy **hai test hợp đồng thừa kế và một test mapping riêng** cho mỗi lớp concrete, tổng cộng sáu test từ hai lớp con; lớp `UiFactoryContractTest` là abstract nên không được chạy độc lập. Nếu sau này thêm `HighContrastUiFactory`, chỉ cần tạo lớp test con với `expectedTheme()` tương ứng và phép kiểm tra mapping thích hợp. Việc viết lớp test cho mỗi factory là một phần trách nhiệm khi bổ sung biến thể mới.

### Tại sao tách hợp đồng chung khỏi mapping cụ thể?

Hai mức kiểm tra trả lời hai loại câu hỏi khác nhau:

- **Hợp đồng chung (ổn định):** mọi `UiFactory` phải trả về `Button`, `Dialog` hợp lệ và cùng biến thể; khách hàng dùng chúng qua interface.
- **Mapping cụ thể (tùy yêu cầu):** `LightUiFactory` hiện tạo `LightButton`, `LightDialog`. Nếu kiến trúc cho phép thay bằng adapter hoặc decorator nhưng vẫn giữ hành vi và biến thể đúng, test ép kiểu lớp cụ thể có thể quá chặt.

Vì vậy, không nhất thiết luôn cần `assertInstanceOf`. Nếu chỉ có cam kết qua interface và hành vi, kiểm tra hợp đồng và kết quả quan sát được có thể phù hợp hơn.

## 6. Đọc lỗi kiểm thử để tìm sai hợp đồng

Giả sử một lập trình viên vô tình sửa factory tối:

~~~java
final class DarkUiFactory implements UiFactory {
    @Override
    public Button createButton() {
        return new DarkButton();
    }

    @Override
    public Dialog createDialog() {
        return new LightDialog(); // Sai họ sản phẩm
    }
}
~~~

Mã vẫn **biên dịch thành công** vì `LightDialog` thực hiện `Dialog`. Nhưng test hợp đồng của `DarkUiFactoryTest` sẽ phát hiện `dialog.theme()` là `LIGHT` thay vì `DARK`; test mapping riêng cũng phát hiện trả về sai lớp.

| Đột biến lỗi được đưa vào factory | Phép kiểm tra kỳ vọng phát hiện |
| --- | --- |
| `createButton()` trả `null` | `assertNotNull(button)` |
| `DarkUiFactory.createDialog()` trả `LightDialog` | `assertEquals(DARK, dialog.theme())` và có thể `assertInstanceOf(DarkDialog.class, ...)` |
| Hai sản phẩm thuộc hai họ khác nhau | `assertEquals(button.theme(), dialog.theme())` |
| Sản phẩm `render()` ném ngoại lệ | `assertDoesNotThrow` |
| `render()` trả chuỗi rỗng | `assertFalse(markup.trim().isEmpty())` |
| `render()` trả `null` | `assertNotNull(markup)` trước khi gọi `trim()` |

Chú ý một lỗi tinh tế trong cách viết test: nếu chỉ khẳng định `button.theme() == dialog.theme()`, factory có thể trả **cả hai sản phẩm sai nhưng cùng một họ** và test vẫn qua. Vì vậy phải kiểm tra **cả biến thể kỳ vọng của từng sản phẩm** lẫn quan hệ nhất quán giữa chúng.

## 7. Những hợp đồng bổ sung cần cân nhắc theo thiết kế thực tế

### 7.1. Vòng đời: tạo mới hay dùng chung?

Mẫu Abstract Factory tự nó **không quy định** mỗi lần gọi phương thức tạo phải trả về một instance mới. Nếu API của ứng dụng **cam kết** tạo mới, bạn có thể thêm:

~~~java
@Test
void createsDifferentButtonsOnSeparateCalls() {
    UiFactory factory = new LightUiFactory();

    Button first = factory.createButton();
    Button second = factory.createButton();

    assertNotSame(first, second);
}
~~~

Test này đúng với implementation minh họa ở trên, vì mỗi lần gọi đều sử dụng `new LightButton()`. Tuy nhiên, nếu yêu cầu cho phép cache hoặc chia sẻ instance bất biến, `assertNotSame` sẽ khóa một quyết định không thuộc hợp đồng và có thể làm test thất bại khi refactor hợp lệ. Tương tự, **không tự động kiểm tra `assertSame`** nếu thiết kế không cam kết singleton.

### 7.2. Tham số không hợp lệ và xử lý ngoại lệ

Một số factory có chữ ký như `createDialog(Locale locale)` hoặc `createButton(ButtonConfig config)`. Nếu hợp đồng quy định rõ điều gì xảy ra với `null`, thêm test cho trường hợp đó:

~~~java
// Ví dụ giả định cho một interface khác có tham số cấu hình.
@Test
void rejectsNullConfig() {
    ConfigurableUiFactory factory = new ConfigurableLightUiFactory();

    assertThrows(
            IllegalArgumentException.class,
            () -> factory.createButton(null)
    );
}
~~~

`ConfigurableUiFactory` và `ConfigurableLightUiFactory` chỉ là **tên giả định để minh họa một hợp đồng khác**, không thuộc `UiModel.java`. Test trên chỉ thích hợp **nếu yêu cầu đã quy định** factory ném `IllegalArgumentException` với cấu hình `null`. Không nên tự đặt quy tắc ngoại lệ rồi biến nó thành yêu cầu bằng test.

### 7.3. Đối tượng phụ thuộc tài nguyên ngoài

Một factory sản xuất connection, client mạng, adapter cơ sở dữ liệu hoặc wrapper file có thể cần dependency bên ngoài. Khi viết **unit test cho chính factory**, hãy tiêm dependency giả hoặc stub ở ranh giới có thể kiểm soát để kiểm tra việc lắp ráp đúng; tránh buộc một unit test mở kết nối thật. Nếu mục tiêu là xác minh factory làm việc đúng với driver hoặc dịch vụ thật, đó là **kiểm thử tích hợp**, cần môi trường và vòng đời tài nguyên riêng.

### 7.4. Bảo đảm tương thích vượt qua một thuộc tính

`theme()` chỉ là một bất biến đơn giản. Trong hệ thống thật, một họ sản phẩm có thể phải đồng bộ phiên bản giao thức, mã hóa dữ liệu, chuẩn truy cập, transaction hoặc ngữ cảnh bảo mật. Hãy mô tả bất biến ở mức **hành vi có thể quan sát** và kiểm tra cặp sản phẩm cùng nhau khi chúng tương tác, thay vì chỉ so tên lớp.

Ví dụ: factory cho một kho dữ liệu tạo `Encoder` và `Decoder` cùng định dạng. Test tốt phải chứng minh dữ liệu được encoder tạo ra có thể được decoder cùng họ đọc lại; kiểm tra cả hai có nhãn `"JSON"` là chưa đủ để chứng minh khả năng tương tác.

## 8. Chạy JUnit và tổ chức file

Các đoạn mã minh họa ở trên giả định JUnit **Jupiter 5.8 hoặc mới hơn** (vì dùng `assertInstanceOf`), chạy trên Java hỗ trợ phiên bản JUnit được chọn. Tối thiểu cần runtime JUnit Platform và cấu hình build tool để phát hiện test Jupiter. Nếu dùng Gradle Groovy DSL, cấu hình thường có dạng:

~~~groovy
dependencies {
    testImplementation platform('org.junit:junit-bom:5.11.4')
    testImplementation 'org.junit.jupiter:junit-jupiter'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Phiên bản `5.11.4` là **ví dụ cố định để minh họa cấu hình JUnit 5**, không phải khẳng định phiên bản mới nhất; với dự án thật hãy dùng phiên bản hoặc BOM phù hợp đang được quản lý. Sau khi đặt file vào đúng package và cấu hình phụ thuộc, có thể chạy bằng Gradle:

~~~bash
./gradlew test --tests "example.abstractfactory.LightUiFactoryTest"
./gradlew test --tests "example.abstractfactory.DarkUiFactoryTest"
./gradlew test
~~~

Trên Windows có thể dùng `gradlew.bat` thay cho `./gradlew`. Các lệnh là hướng dẫn thực hành, **không phải kết quả đã thực thi trong bài học**.

Cấu trúc nguồn tham khảo cho **phương án kiểm thử hợp đồng dùng chung**:

~~~text
src/
  main/java/example/abstractfactory/
    UiModel.java
  test/java/example/abstractfactory/
    UiFactoryContractTest.java
    LightUiFactoryTest.java
    DarkUiFactoryTest.java
~~~

Khi kiểm tra kết quả, hãy xem từng lớp `ConcreteFactory` đều thực sự xuất hiện trong test report. Tổng số test chạy không tự bảo đảm độ bao phủ từng factory nếu một biến thể bị bỏ sót hoặc test vô tình khởi tạo cùng một factory ở nhiều lớp test.

## 9. Bài tập tự luyện

**Bài tập 1 — Tìm sai hợp đồng.** Một `WindowsWidgetFactory` phải tạo `WindowsButton` và `WindowsMenu`, nhưng test chỉ viết:

~~~java
assertNotNull(factory.createButton());
assertNotNull(factory.createMenu());
~~~

Hai assertion này bỏ sót điều gì? Hãy bổ sung kiểm tra Windows family cho cả hai sản phẩm và một assertion xác minh hai sản phẩm cùng thuộc Windows.

**Bài tập 2 — Thêm ConcreteFactory.** Thêm `HighContrastUiFactory` với `HighContrastButton` và `HighContrastDialog` vào ví dụ. Viết lớp `HighContrastUiFactoryTest` thừa kế `UiFactoryContractTest`, triển khai `createFactory()` và `expectedTheme()`, rồi thêm test riêng khi mapping tới các lớp cụ thể là một yêu cầu.

**Bài tập 3 — Phát hiện test quá chặt.** Một nhóm thay `LightButton` bằng `InstrumentedLightButton` vẫn thực hiện `Button`, giữ `Theme.LIGHT` và hành vi đúng. Test nào có thể thất bại dù hợp đồng công khai không đổi? Khi nào nên bỏ hoặc điều chỉnh test mapping lớp cụ thể?

**Bài tập 4 — Lỗi trộn họ.** Cố tình sửa `DarkUiFactory.createDialog()` để trả `LightDialog`, dự đoán chính xác những assertion nào thất bại trước khi chạy test. Sau đó trả mã về cấu trúc đúng.

## 10. Checklist khi đánh giá unit test của một ConcreteFactory

- [ ] Mỗi `ConcreteFactory` đều có lớp test hoặc một ca kiểm thử được gọi trực tiếp với chính factory đó.
- [ ] Mọi phương thức tạo sản phẩm trong `AbstractFactory` đều được thực thi.
- [ ] Kết quả được kiểm tra khác `null` trước khi truy cập phương thức.
- [ ] Đã kiểm tra loại sản phẩm hoặc hành vi theo **hợp đồng công khai**.
- [ ] Đã xác minh **biến thể kỳ vọng** cho từng sản phẩm và tính nhất quán trong cùng một họ.
- [ ] Test không khóa cứng lớp implementation, vòng đời hoặc thứ tự khởi tạo nếu API không cam kết điều đó.
- [ ] Nếu có tham số, lỗi hoặc tài nguyên, đã xác định hợp đồng tương ứng trước khi viết assertion.
- [ ] Các test có khả năng làm lộ lỗi `ConcreteFactory` tạo nhầm sản phẩm của họ khác.
- [ ] Đã phân biệt unit test của factory với kiểm thử tích hợp của các thành phần phụ thuộc.

**Kết luận:** Unit test có giá trị nhất cho Abstract Factory là phép kiểm tra rằng **mỗi ConcreteFactory thực hiện đầy đủ cùng một hợp đồng và luôn tạo một họ sản phẩm đúng, nhất quán**. Test riêng bảo vệ mapping của từng biến thể; test hợp đồng dùng chung giúp giữ tiêu chuẩn kiểm tra đồng nhất khi hệ thống có thêm factory mới.
