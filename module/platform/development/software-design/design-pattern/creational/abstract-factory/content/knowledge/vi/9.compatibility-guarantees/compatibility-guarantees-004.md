# Dùng generic hoặc family token khi kiểm tra kiểu thông thường chưa đủ

Trong mẫu thiết kế **Abstract Factory**, một factory tạo ra **một họ sản phẩm có liên quan**. Chẳng hạn, factory giao diện Light tạo LightButton và LightCheckbox, còn factory Dark tạo DarkButton và DarkCheckbox. Các interface **Button** và **Checkbox** giúp mã khách hàng ít phụ thuộc vào lớp cụ thể, nhưng chỉ kiểm tra interface riêng lẻ **chưa khẳng định hai đối tượng thuộc cùng một họ**.

Bài thuộc chương **Bảo đảm tương thích** này giải thích khi nào cần bổ sung **Java generic** để liên kết họ sản phẩm ở thời điểm biên dịch, khi nào cần **family token** để kiểm tra ở thời điểm chạy, cách kết hợp hai cơ chế và giới hạn của từng cách. Mục tiêu là bảo vệ một **bất biến thiết kế**: các sản phẩm được ghép với nhau phải tương thích theo quy tắc đã công bố của hệ thống.

## 1. Vì sao interface thông thường chưa đủ?

Giả sử màn hình có hai loại sản phẩm:

| Họ / Loại sản phẩm | Button | Checkbox |
| --- | --- | --- |
| Light | LightButton | LightCheckbox |
| Dark | DarkButton | DarkCheckbox |

Các lớp cụ thể đều triển khai đúng interface tương ứng:

~~~java
interface Button {
    String render();
}

interface Checkbox {
    String render();
}

// Các lớp LightButton, DarkButton đều implements Button.
// Các lớp LightCheckbox, DarkCheckbox đều implements Checkbox.
~~~

Nhưng chữ ký của một hàm ghép sản phẩm như sau vẫn cho phép trộn họ:

~~~java
void showScreen(Button button, Checkbox checkbox) {
    System.out.println(button.render());
    System.out.println(checkbox.render());
}

// Hợp lệ về kiểu Java nếu các lớp cụ thể đã được định nghĩa:
showScreen(new LightButton(), new DarkCheckbox());
~~~

Trình biên dịch chỉ xác minh **LightButton là Button** và **DarkCheckbox là Checkbox**; nó không biết quy tắc nghiệp vụ **“Button và Checkbox phải cùng Light hoặc cùng Dark”**. Đây là hai mức tương thích khác nhau:

1. **Tương thích theo loại (product type):** đối tượng thực hiện đúng hợp đồng Button hay Checkbox.
2. **Tương thích theo họ (product family):** những đối tượng được phối hợp thuộc cùng bộ biến thể hoặc đáp ứng cùng một quy tắc liên kết.

Abstract Factory tạo **một điểm chọn họ thống nhất**, nhưng các kiểu trả về Button và Checkbox đơn thuần không buộc Java chứng minh mọi factory luôn tạo đúng họ. Một concrete factory viết sai vẫn có thể trả LightButton và DarkCheckbox. Nếu phải kiểm tra chặt chẽ hơn, có thể đưa **danh tính họ** vào kiểu generic hoặc một **token kiểm tra lúc chạy**.

## 2. Cách thứ nhất: generic liên kết họ sản phẩm tại thời điểm biên dịch

### 2.1. Dùng marker type cho từng họ

Ta tạo một interface đánh dấu và các kiểu đại diện cho họ:

~~~java
interface Family {
}

final class Light implements Family {
}

final class Dark implements Family {
}
~~~

**Light** và **Dark** ở đây là *kiểu đánh dấu* (marker types), không phải nút bấm hoặc ô chọn và cũng không bắt buộc tạo instance. Chúng được sử dụng như tham số kiểu để diễn tả **đối tượng thuộc họ nào**.

Tiếp đó, khai báo các hợp đồng generic:

~~~java
interface Button<F extends Family> {
    String render();
}

interface Checkbox<F extends Family> {
    String render();
}

interface ThemeFactory<F extends Family> {
    Button<F> createButton();
    Checkbox<F> createCheckbox();
}
~~~

**F** biểu thị cùng một họ trong một factory. Vì thế:

- **ThemeFactory<Light>** phải có createButton() trả **Button<Light>** và createCheckbox() trả **Checkbox<Light>**.
- **ThemeFactory<Dark>** trả về cặp tương ứng với **Dark**.
- **Button<Light>** và **Button<Dark>** là các kiểu generic khác nhau; Java generic thông thường là **bất biến** (*invariant*) theo tham số kiểu.

Một concrete factory như sau sẽ bị trình biên dịch từ chối nếu cố trả sai họ:

~~~java
// Minh họa lỗi biên dịch; không ghép vào chương trình hoàn chỉnh.
final class WrongLightFactory implements ThemeFactory<Light> {
    public Button<Light> createButton() {
        return new LightButton();
    }

    public Checkbox<Light> createCheckbox() {
        return new DarkCheckbox(); // SAI: Checkbox<Dark> không là Checkbox<Light>.
    }
}
~~~

Đoạn mã giả định LightButton triển khai Button<Light> và DarkCheckbox triển khai Checkbox<Dark>. Khi sử dụng kiểu generic đầy đủ, lỗi trộn họ được phát hiện sớm ở **thời điểm biên dịch**, thay vì chờ người dùng nhìn thấy giao diện sai.

### 2.2. Ràng buộc cả client với cùng một tham số kiểu

Client cũng có thể mang tham số **F**:

~~~java
final class Panel<F extends Family> {
    private final Button<F> button;
    private final Checkbox<F> checkbox;

    Panel(ThemeFactory<F> factory) {
        button = factory.createButton();
        checkbox = factory.createCheckbox();
    }
}
~~~

Constructor nhận **một ThemeFactory<F>**, vì vậy Button<F> và Checkbox<F> được sinh ra cùng một đường tạo. Khi biết **F = Light**, Java chỉ chấp nhận ThemeFactory<Light> cho Panel<Light>:

~~~java
// Minh họa: hai dòng đầu hợp lệ; dòng cuối là lỗi biên dịch.
Panel<Light> lightPanel = new Panel<>(new LightThemeFactory());
Panel<Dark> darkPanel = new Panel<>(new DarkThemeFactory());

Panel<Light> wrongPanel = new Panel<>(new DarkThemeFactory()); // SAI.
~~~

Đây là cách biến **quy tắc chọn họ** thành ràng buộc của API. Lớp Panel không cần biết cụ thể LightButton hay DarkCheckbox, nhưng compiler vẫn có thể kiểm tra quan hệ giữa các loại sản phẩm.

### 2.3. Không dùng wildcard để thay thế một ràng buộc cùng họ

Trong Java, **Button<? extends Family>** nghĩa là Button thuộc *một họ nào đó*, chứ không xác định đó là Light hay Dark. Hai biến kiểu Button<? extends Family> và Checkbox<? extends Family> có thể chứa **hai họ khác nhau**.

Nếu một hàm nhận **hai wildcard riêng biệt**, nó không bảo đảm hai wildcard trỏ đến cùng một họ:

~~~java
// Hàm này KHÔNG thể hiện quy tắc cùng họ.
void displayAny(Button<? extends Family> button,
                Checkbox<? extends Family> checkbox) {
    System.out.println(button.render() + " " + checkbox.render());
}
~~~

Khi cần biểu diễn **cùng một họ**, hãy dùng **một tham số kiểu chung F** trong chữ ký hàm:

~~~java
// Hai tham số phải cùng một F.
static <F extends Family> void displaySameFamily(
        Button<F> button, Checkbox<F> checkbox) {
    System.out.println(button.render() + " " + checkbox.render());
}
~~~

Với Button<Light> và Checkbox<Dark>, Java không thể chọn cùng một **F** hợp lệ cho hai tham số bất biến đó. Tuy vậy, cần lưu ý các đường đi có **raw type, ép kiểu không an toàn hoặc reflection** vẫn có thể vượt qua cơ chế kiểm tra generic. Phần sau sẽ dùng token để phát hiện một số lỗi tại ranh giới này.

## 3. Cách thứ hai: family token kiểm tra họ khi chương trình chạy

Generic hỗ trợ kiểm tra tại thời điểm biên dịch, nhưng sau khi Java **type erasure** (xóa thông tin tham số kiểu khi biên dịch), không thể chỉ hỏi một instance rằng nó là **Button<Light>** hay **Button<Dark>** bằng phép **instanceof**.

Ví dụ, đoạn kiểm tra sau **không hợp lệ trong Java**:

~~~java
// Không biên dịch được:
if (button instanceof Button<Light>) {
    // ...
}
~~~

Vì vậy, khi sản phẩm đến từ **plugin**, dữ liệu cấu hình động, hệ thống cũ, reflection hoặc code ép kiểu không an toàn, có thể cần thêm một **family token** tồn tại ở runtime.

### 3.1. Family token là gì?

Family token là **giá trị nhận diện họ** mà chương trình có thể so sánh khi chạy. Hai lựa chọn phổ biến:

| Token | Ví dụ | Khi nào dùng |
| --- | --- | --- |
| **Class token** | Light.class, Dark.class | Họ được mô hình hóa bằng kiểu Java, muốn kết hợp với generic F |
| **Enum hoặc ID ổn định** | FamilyId.LIGHT, FamilyId.DARK | Họ là danh mục nghiệp vụ hoặc được ghi ra cấu hình/dữ liệu |

Với Class token, các hợp đồng có thể khai báo:

~~~java
interface Button<F extends Family> {
    Class<F> familyType();
    String render();
}

interface Checkbox<F extends Family> {
    Class<F> familyType();
    String render();
}

interface ThemeFactory<F extends Family> {
    Class<F> familyType();
    Button<F> createButton();
    Checkbox<F> createCheckbox();
}
~~~

Khi tạo một màn hình, mã kiểm tra **token của factory và các sản phẩm có trùng nhau không**. Nếu một adapter cũ hoặc plugin khai báo sai loại sản phẩm, hệ thống có thể phát hiện trước khi hiển thị.

### 3.2. Generic và token bổ sung cho nhau

~~~mermaid
flowchart TB
    API["API generic: ThemeFactory<F>"] --> Compile["Kiểm tra lúc biên dịch"]
    Compile --> Family["Button<F> + Checkbox<F>"]
    Family --> Runtime["Kiểm tra token khi khởi tạo"]
    Runtime --> Check{"Token factory = Button = Checkbox?"}
    Check -->|Có| Screen["Tạo màn hình"]
    Check -->|Không| Error["Từ chối cấu hình / factory sai"]
~~~

Kiểm tra bằng generic diễn ra **trước lúc chạy** và chặn việc trộn các họ trong mã Java an toàn về kiểu. Kiểm tra token diễn ra **lúc chạy** và hữu ích khi mã vượt ranh giới mà generic không còn đủ thông tin hoặc không được tuân thủ.

Hai cơ chế không thay thế hoàn toàn cho nhau. Token chỉ xác nhận **danh tính họ được công bố**; nếu một sản phẩm báo Light nhưng thực tế vẽ như Dark, phép so sánh token có thể vẫn qua. Chất lượng, ngữ nghĩa và khả năng phối hợp của các sản phẩm còn cần **kiểm thử hành vi**.

## 4. Ví dụ Java đầy đủ: vừa generic vừa family token

Ví dụ sau có thể đặt nguyên trong một tệp **Main.java** và chạy với Java 8 trở lên. Chúng ta vẫn dùng hai họ **Light**, **Dark** và hai loại sản phẩm **Button**, **Checkbox**. Trong lớp Panel, cả factory, button và checkbox phải khai báo cùng kiểu **F**, đồng thời token được kiểm tra ở runtime.

~~~java
import java.util.Locale;
import java.util.Objects;

public class Main {
    // Marker types để định danh họ trong hệ thống kiểu Java.
    interface Family {
    }

    static final class Light implements Family {
    }

    static final class Dark implements Family {
    }

    // Abstract products có tham số F và family token.
    interface Button<F extends Family> {
        Class<F> familyType();
        String render();
    }

    interface Checkbox<F extends Family> {
        Class<F> familyType();
        String render();
    }

    // Abstract Factory có trách nhiệm tạo cùng một F.
    interface ThemeFactory<F extends Family> {
        Class<F> familyType();
        Button<F> createButton();
        Checkbox<F> createCheckbox();
    }

    static final class LightButton implements Button<Light> {
        @Override
        public Class<Light> familyType() {
            return Light.class;
        }

        @Override
        public String render() {
            return "[Light] Button";
        }
    }

    static final class LightCheckbox implements Checkbox<Light> {
        @Override
        public Class<Light> familyType() {
            return Light.class;
        }

        @Override
        public String render() {
            return "[Light] Checkbox";
        }
    }

    static final class DarkButton implements Button<Dark> {
        @Override
        public Class<Dark> familyType() {
            return Dark.class;
        }

        @Override
        public String render() {
            return "[Dark] Button";
        }
    }

    static final class DarkCheckbox implements Checkbox<Dark> {
        @Override
        public Class<Dark> familyType() {
            return Dark.class;
        }

        @Override
        public String render() {
            return "[Dark] Checkbox";
        }
    }

    static final class LightThemeFactory implements ThemeFactory<Light> {
        @Override
        public Class<Light> familyType() {
            return Light.class;
        }

        @Override
        public Button<Light> createButton() {
            return new LightButton();
        }

        @Override
        public Checkbox<Light> createCheckbox() {
            return new LightCheckbox();
        }
    }

    static final class DarkThemeFactory implements ThemeFactory<Dark> {
        @Override
        public Class<Dark> familyType() {
            return Dark.class;
        }

        @Override
        public Button<Dark> createButton() {
            return new DarkButton();
        }

        @Override
        public Checkbox<Dark> createCheckbox() {
            return new DarkCheckbox();
        }
    }

    // Client nhận một factory thuộc một họ F.
    static final class Panel<F extends Family> {
        private final Button<F> button;
        private final Checkbox<F> checkbox;

        Panel(ThemeFactory<F> factory) {
            Objects.requireNonNull(factory, "factory");

            Class<F> expected = Objects.requireNonNull(
                    factory.familyType(), "factory.familyType()");
            button = Objects.requireNonNull(
                    factory.createButton(), "button");
            checkbox = Objects.requireNonNull(
                    factory.createCheckbox(), "checkbox");

            ensureSameFamily(expected, button.familyType(), "Button");
            ensureSameFamily(expected, checkbox.familyType(), "Checkbox");
        }

        private static void ensureSameFamily(
                Class<?> expected, Class<?> actual, String kind) {
            if (!expected.equals(actual)) {
                throw new IllegalArgumentException(
                        kind + " sai họ: mong đợi "
                                + expected.getSimpleName()
                                + ", nhận "
                                + (actual == null
                                        ? "null" : actual.getSimpleName()));
            }
        }

        String render() {
            return button.render() + System.lineSeparator()
                    + checkbox.render();
        }
    }

    // Giữ cùng tham số F xuyên suốt thao tác tạo Panel.
    static <F extends Family> Panel<F> createPanel(
            ThemeFactory<F> factory) {
        return new Panel<>(factory);
    }

    static ThemeFactory<? extends Family> selectFactory(String theme) {
        if ("light".equals(theme)) {
            return new LightThemeFactory();
        }
        if ("dark".equals(theme)) {
            return new DarkThemeFactory();
        }
        throw new IllegalArgumentException("Chủ đề không hợp lệ: " + theme);
    }

    public static void main(String[] args) {
        String theme = args.length == 0
                ? "light" : args[0].toLowerCase(Locale.ROOT);

        // Factory được chọn động: kiểu họ cụ thể chưa biết lúc biên dịch.
        ThemeFactory<? extends Family> factory = selectFactory(theme);

        // Wildcard được capture cho MỘT lời gọi, tạo Panel cùng họ.
        Panel<?> panel = createPanel(factory);
        System.out.println(panel.render());
    }
}
~~~

Biên dịch và chạy:

~~~text
javac -encoding UTF-8 Main.java
java Main
[Light] Button
[Light] Checkbox

java Main dark
[Dark] Button
[Dark] Checkbox
~~~

Hãy chú ý ba chi tiết:

1. **ThemeFactory<Light>** chỉ trả về **Button<Light>** và **Checkbox<Light>** trong một chương trình Java sử dụng generic đúng cách.
2. **Panel<F>** nhận **một** ThemeFactory<F> và so sánh token của mỗi sản phẩm với token factory. Việc kiểm tra xảy ra **trước** khi render().
3. Phần cấu hình có thể trả về **ThemeFactory<? extends Family>** vì chưa biết Light hay Dark tại thời điểm biên dịch. Phương thức generic **createPanel** sử dụng *wildcard capture* để giữ một tham số F nhất quán cho factory và panel trong cùng lời gọi. Kết quả được lưu ở kiểu **Panel<?>** vì bên ngoài lời gọi không cần biết F cụ thể.

Không nên cố ép **ThemeFactory<? extends Family>** thành **ThemeFactory<Light>** chỉ vì chuỗi cấu hình ghi light; generic không thể suy ra sự thật đó từ một chuỗi runtime. Chọn factory là một thao tác ở ranh giới cấu hình, còn tính nhất quán khi tạo sản phẩm được bảo vệ bên trong createPanel và Panel.

## 5. Khi nào generic có thể bị vượt qua và token giúp phát hiện?

Java cho phép code cũ hoặc code dùng raw type thực hiện ép kiểu không an toàn. Đoạn sau minh họa **lỗi cố tình tạo**, không phải cách triển khai được khuyến nghị:

~~~java
// Ví dụ giả lập một adapter/plugin cũ vi phạm hợp đồng generic.
// Các lớp ở đây dùng cùng kiểu như ví dụ Main.java.
@SuppressWarnings({"rawtypes", "unchecked"})
static Checkbox<Light> unsafeLegacyCheckbox() {
    Checkbox raw = new DarkCheckbox();
    return (Checkbox<Light>) raw;
}
~~~

Nếu một **ThemeFactory<Light>** dùng unsafeLegacyCheckbox() để trả về Checkbox<Light>, generic check có thể bị qua mặt sau ép kiểu. Khi Panel gọi **checkbox.familyType()**, sản phẩm thực sự trả về **Dark.class**, khác **Light.class** của factory. Việc so sánh token sẽ ném **IllegalArgumentException** trước khi hiển thị.

Trong thực tế, các điểm dễ xuất hiện sai lệch tương tự là:

- **Thành phần legacy:** API dùng Object, raw collection hoặc ép kiểu generic.
- **Reflection và dependency injection theo tên:** lớp được xác định từ cấu hình tại runtime.
- **Plugin hoặc SPI:** nhà cung cấp bên ngoài triển khai hợp đồng nhưng có thể cấu hình sai.
- **Dữ liệu được giải mã:** đối tượng chứa tên họ/ID họ từ JSON, cơ sở dữ liệu hoặc thông điệp, không tự có tham số generic chính xác.

**Cần phân biệt:** ví dụ runtime trên chỉ phát hiện **sản phẩm tự khai báo token khác** với factory. Nếu provider gian lận hoặc sai sót khiến cả sản phẩm lẫn factory **cùng báo Light** dù hành vi không thuộc Light, token sẽ không phát hiện được. Đây là cơ chế kiểm soát **metadata về họ**, không phải phương án xác minh đầy đủ mọi hành vi hoặc ranh giới bảo mật đối với mã không đáng tin cậy.

## 6. Family token bằng enum hoặc ID khi không dùng marker type

Một số hệ thống không cần tham số generic ở mọi lớp, chẳng hạn khi họ sản phẩm đến từ **tệp cấu hình**, bảng dữ liệu hoặc dịch vụ ngoài. Có thể dùng token runtime đơn giản hơn:

~~~java
enum FamilyId {
    LIGHT, DARK
}

interface FamilyTagged {
    FamilyId familyId();
}

interface SimpleButton extends FamilyTagged {
    String render();
}

interface SimpleCheckbox extends FamilyTagged {
    String render();
}

static void checkFamily(
        FamilyId selected, SimpleButton button, SimpleCheckbox checkbox) {
    if (selected != button.familyId()
            || selected != checkbox.familyId()) {
        throw new IllegalArgumentException("Trộn họ giao diện");
    }
}
~~~

Đây là đoạn mã minh họa các khai báo và phương thức hỗ trợ; để đưa vào chương trình Java hoàn chỉnh, đặt **checkFamily** trong một lớp và cung cấp các hiện thực của SimpleButton, SimpleCheckbox.

**Ưu điểm:** dễ biểu diễn token trong cấu hình, log và cơ sở dữ liệu; có thể xác thực trước khi ghép sản phẩm. **Giới hạn:** vì các interface SimpleButton và SimpleCheckbox không chứa F, compiler vẫn cho phép truyền LightButton và DarkCheckbox cùng lúc, rồi lỗi chỉ xuất hiện **tại runtime**.

Nếu hệ thống mở rộng họ qua plugin mà danh sách họ không cố định, một enum trung tâm có thể khó bảo trì vì thêm mỗi họ buộc sửa enum. Khi đó có thể dùng **ID được chuẩn hóa** hoặc một kiểu FamilyKey bất biến và kiểm soát **tính duy nhất của ID** trong registry. Với Class token, chú ý hai lớp có cùng tên nhưng được nạp bởi **class loader khác nhau** là hai đối tượng Class khác nhau; cần thống nhất cách nạp API nếu ứng dụng có kiến trúc plugin phức tạp.

## 7. Lựa chọn cơ chế theo ranh giới tin cậy

| Tình huống | Cơ chế phù hợp | Lý do |
| --- | --- | --- |
| Tất cả concrete products và factory do cùng dự án kiểm soát | **Generic theo F** | Phát hiện nhiều lỗi trộn họ ngay khi biên dịch |
| Client dùng một factory cho cả nhóm sản phẩm | **ThemeFactory<F> + Panel<F>** | Biểu diễn quan hệ giữa các loại sản phẩm qua một tham số chung |
| Factory/sản phẩm đến từ plugin, reflection, mã legacy | **Generic + token runtime** | Có thêm kiểm tra khi thông tin generic bị xóa hoặc bị vượt qua |
| Danh tính họ đọc từ dữ liệu hoặc cấu hình | **Enum, ID hoặc FamilyKey** | Dễ chuyển đổi, lưu trữ và thông báo lỗi |
| Hành vi sản phẩm phải tương thích về protocol, version, tính năng | **Token + kiểm tra năng lực và kiểm thử tích hợp** | Cùng ID họ chưa khẳng định mọi khả năng phối hợp |
| Nhiều họ được dùng đồng thời ở những màn hình khác nhau | **Factory riêng cho từng phạm vi** | Duy trì nhất quán trong từng nhóm mà không ép toàn ứng dụng cùng một họ |

**Không nên mặc định thêm token vào mọi loại sản phẩm.** Khi toàn bộ quá trình khởi tạo nằm trong mã Java có kiểm soát, giao diện generic đã bảo đảm ràng buộc cần thiết, việc lặp token có thể làm API dài và tăng công bảo trì. Token có ích khi tồn tại **đường đi thực tế** mà compiler không thể chứng minh cùng họ.

### Token họ khác với kiểm tra năng lực và phiên bản

Hai sản phẩm đều báo **FamilyId.DARK** chưa chắc tương thích khi một bên hỗ trợ giao thức v2 còn bên kia chỉ hỗ trợ v1. Nếu có yêu cầu về **protocol version**, cấu hình khu vực, quyền truy cập hoặc feature set, hãy biểu diễn chúng bằng hợp đồng riêng và kiểm chứng thực tế. Có thể bổ sung đối tượng mô tả capability hoặc sử dụng các kiểm tra tương thích cụ thể; chỉ so sánh familyId không đủ.

Tương tự, một factory trả đúng **Button<Light>** và **Checkbox<Light>** về generic vẫn có thể tạo đối tượng lỗi, thiếu tài nguyên hoặc render sai. Generic cung cấp **bảo đảm về kiểu**, còn tính đúng đắn của hành vi cần unit test và integration test phù hợp.

## 8. Những lỗi thiết kế thường gặp

### 8.1. Coi abstract interface là bằng chứng cùng họ

Chỉ vì hai đối tượng triển khai Button và Checkbox thì chưa thể kết luận chúng tương thích. Để bảo vệ cùng họ, sử dụng một factory cho bộ sản phẩm và, nếu cần, gắn **F** hoặc token cho các hợp đồng.

### 8.2. Khai báo generic ở factory nhưng bỏ ở client

Nếu factory dùng ThemeFactory<F> nhưng client lập tức gán kết quả vào raw Button và raw Checkbox, lợi ích kiểm tra cùng F bị đánh mất ở chỗ ghép đối tượng. Nên giữ **F** tại các API cần kiểm tra mối quan hệ, chỉ dùng wildcard ở ranh giới mà họ cụ thể chưa được biết.

### 8.3. Dùng ép kiểu để làm trình biên dịch im lặng

Các phép ép kiểu không kiểm tra được trong lúc chạy có thể che sai lệch giữa Light và Dark. Chỉ dùng ở ranh giới thực sự không tránh được, thu hẹp phạm vi, kiểm tra token trước khi sử dụng và ghi rõ giả định của adapter.

### 8.4. Tin rằng instanceof kiểm tra được generic F

Không thể viết **instanceof Button<Light>** do type erasure. Nếu cần nhận diện họ tại runtime, cung cấp một token riêng và so sánh các token theo quy tắc rõ ràng.

### 8.5. Dùng một chuỗi ID nhưng không quy định nguồn và vòng đời

Nếu hai plugin cùng đăng ký ID dark, hoặc ID được ghi khác chữ hoa/chữ thường, hệ thống có thể chọn sai factory. Chuẩn hóa khóa, từ chối trùng trong registry và kiểm tra token trước khi ghép sản phẩm. Với plugin, xác định rõ token nào thuộc API dùng chung.

## 9. Bài tập kiểm chứng

**Bài A — Kiểm tra tĩnh:** dùng mã generic ở mục 4, thử sửa **LightThemeFactory.createCheckbox()** thành **return new DarkCheckbox();**. Giải thích vì sao compiler từ chối, kể cả khi DarkCheckbox thực hiện cùng loại Checkbox.

**Bài B — Kiểm tra động:** tạo một adapter cố tình dùng raw type để trả một **DarkCheckbox** từ một **ThemeFactory<Light>**. Dự đoán điều xảy ra khi Panel kiểm tra token và giải thích vì sao generic không chặn được đoạn mã đã ép kiểu.

**Bài C — Cấu hình động:** thử chọn ThemeFactory<? extends Family> dựa trên tham số Light/Dark. Dùng một phương thức generic như createPanel trong ví dụ để tạo Panel<?> mà không cần ép về ThemeFactory<Light> hay ThemeFactory<Dark>.

**Bài D — Nâng cấp từ enum sang plugin:** giả sử một plugin thêm họ HighContrast và ứng dụng không được sửa enum FamilyId. Đề xuất FamilyKey dùng ID bất biến, quy tắc chống trùng và vị trí xác thực token trong luồng khám phá provider.

**Bài E — Định nghĩa giới hạn bảo đảm:** nếu Button và Checkbox có cùng token Light nhưng Button dùng schema v1 còn Checkbox dùng schema v2, hãy đề xuất thêm kiểm tra version hoặc capability. Chỉ ra phần nào do generic, phần nào do token và phần nào do kiểm thử hành vi đảm trách.

## 10. Ghi nhớ

- **Interface thông thường** xác nhận từng đối tượng thuộc **loại sản phẩm** nào; chưa ràng buộc các loại khác nhau vào **cùng họ**.
- **Generic F** cho phép biểu diễn **ThemeFactory<F> → Button<F> + Checkbox<F>** và phát hiện nhiều lỗi trộn họ ở thời điểm biên dịch.
- **Family token** như **Light.class**, **Dark.class** hoặc **FamilyId** cho phép so sánh danh tính họ tại runtime, hữu ích ở ranh giới plugin, cấu hình động hoặc code legacy.
- **Type erasure** khiến **instanceof Button<Light>** không hợp lệ; dùng token rõ ràng nếu cần kiểm tra runtime.
- **Generic và token không thay thế kiểm thử hành vi**: cùng kiểu hoặc cùng ID họ vẫn chưa chứng minh sản phẩm hoạt động đúng, tương thích về version hay đáp ứng mọi yêu cầu kỹ thuật.

Khi cần bảo đảm tương thích trong Abstract Factory, hãy bắt đầu bằng **một factory tạo trọn họ**. Nếu yêu cầu đúng đắn đòi hỏi ràng buộc mạnh hơn, dùng **generic để liên kết các sản phẩm trong mã Java** và bổ sung **family token ở đúng ranh giới cần xác minh tại runtime**.
