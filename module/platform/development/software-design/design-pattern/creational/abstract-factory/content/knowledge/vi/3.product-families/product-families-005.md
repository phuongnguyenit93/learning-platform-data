# Xác định sản phẩm bắt buộc, tùy chọn và tổ hợp không được hỗ trợ

Khi áp dụng **Abstract Factory** trong thiết kế phần mềm, ta thường nói mỗi concrete factory tạo ra **một họ sản phẩm tương thích**. Tuy nhiên, các họ không phải lúc nào cũng hỗ trợ một tập tính năng giống hệt nhau. Có sản phẩm mà mọi họ **bắt buộc phải tạo được**, có sản phẩm chỉ cần khi một tính năng được bật, và có những **tổ hợp sản phẩm hoặc tính năng không hợp lệ**.

Bài thuộc chương **Họ sản phẩm** này hướng dẫn phân tích ba trường hợp đó, xây dựng **ma trận hỗ trợ**, thiết kế hợp đồng factory trong Java, xử lý rõ ràng các trường hợp không hỗ trợ và kiểm tra tính nhất quán của cả bộ sản phẩm. Đây là một bước quan trọng trước khi viết lớp factory: nếu phân loại sai nhu cầu, interface chung có thể buộc concrete factory tạo sản phẩm giả, trả về null hoặc làm client phát sinh nhiều điều kiện đặc thù.

## 1. Từ họ sản phẩm đến yêu cầu hỗ trợ

Giả sử một ứng dụng có màn hình **SettingsScreen** với hai chế độ tương tác:

- **Desktop**: dùng chuột, có thể hiển thị gợi ý khi rê chuột (*hover tooltip*).
- **Touch**: dùng màn hình cảm ứng; phiên bản ví dụ **không cung cấp gợi ý khi hover**.

Cả hai chế độ đều cần **Button** và **Checkbox** để màn hình hoạt động. **Tooltip** là thành phần bổ sung mà giao diện Desktop có thể dùng khi người dùng yêu cầu tính năng gợi ý.

| Họ sản phẩm | Button | Checkbox | Tooltip khi yêu cầu | Hỗ trợ hover |
| --- | --- | --- | --- | --- |
| **Desktop** | DesktopButton | DesktopCheckbox | DesktopTooltip | Có |
| **Touch** | TouchButton | TouchCheckbox | Không có biến thể tương ứng trong bài | Không |

Đọc bảng theo hai chiều:

- **Theo cột**, Button, Checkbox và Tooltip là **các loại sản phẩm** (*product types*), mỗi loại có một trách nhiệm khác nhau.
- **Theo hàng**, các biến thể như DesktopButton và DesktopCheckbox thuộc **cùng họ Desktop**; TouchButton và TouchCheckbox thuộc **cùng họ Touch**.

Không nên kết luận rằng vì Desktop có Tooltip nên mọi factory khác cũng phải tạo Tooltip thật. Cần xét **Tooltip có thực sự là sản phẩm bắt buộc của ứng dụng hay chỉ là tiện ích tùy chọn**.

### Ba khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Hành vi thiết kế phù hợp |
| --- | --- | --- |
| **Sản phẩm bắt buộc** (*required product*) | Client không thể hoàn thành chức năng cốt lõi nếu thiếu loại sản phẩm này | Factory phải trả một sản phẩm hợp lệ; thất bại là lỗi hợp đồng hoặc cấu hình |
| **Sản phẩm tùy chọn** (*optional product*) | Client có cách hoạt động hợp lệ khi sản phẩm vắng mặt | API biểu diễn được trạng thái không có sản phẩm, ví dụ Optional<T> |
| **Tổ hợp không được hỗ trợ** (*unsupported combination*) | Một yêu cầu ghép các sản phẩm hoặc năng lực không thỏa ràng buộc hệ thống | Phát hiện, từ chối có giải thích hoặc yêu cầu người dùng chọn cấu hình hợp lệ |

**Tính bắt buộc là thuộc tính của bài toán/client và hợp đồng, không phải của tên lớp.** Với màn hình cơ bản, Tooltip có thể tùy chọn. Với một chức năng huấn luyện bắt buộc hiển thị tooltip, tính năng đó sẽ không thể chạy hợp lệ trên họ Touch của ví dụ: phải thay cách tương tác hoặc từ chối cấu hình.

## 2. Xác định sản phẩm bắt buộc

Một loại sản phẩm nên được xem là **bắt buộc** nếu bỏ nó đi thì không thể đáp ứng hợp đồng cốt lõi mà client công bố.

Trong SettingsScreen, hai giả định nghiệp vụ là:

1. Người dùng luôn cần nhấn Button để lưu cài đặt.
2. Người dùng luôn cần thay đổi lựa chọn bằng Checkbox.

Vì thế **Button** và **Checkbox** phải có trong **mọi họ mà SettingsScreen chấp nhận**. Từ đó, interface của Abstract Factory nên có các phương thức tạo trả về loại sản phẩm tương ứng:

~~~java
interface Button {
    String render();
}

interface Checkbox {
    String render();
}

interface ScreenFactory {
    Button createButton();
    Checkbox createCheckbox();
}
~~~

Hai phương thức trên có nghĩa: một ScreenFactory hợp lệ **phải tạo được** Button và Checkbox. Không có quy tắc Java nào tự ngăn một triển khai trả về null; đây là **hợp đồng thiết kế** cần được ghi rõ và kiểm tra.

### Không dùng null để lách sản phẩm bắt buộc

~~~java
// Phản ví dụ: một factory không đáp ứng hợp đồng SettingsScreen.
class BrokenTouchFactory implements ScreenFactory {
    public Button createButton() {
        return new TouchButton();
    }

    public Checkbox createCheckbox() {
        return null; // SAI: Checkbox là yêu cầu bắt buộc.
    }
}
~~~

Đoạn này chỉ minh họa lỗi; giả sử TouchButton và các interface đã được khai báo ở nơi khác. Nó có thể biên dịch nhưng sẽ dẫn đến lỗi hoặc trạng thái màn hình thiếu chức năng. **Không nên coi một sản phẩm bắt buộc đang thiếu là sản phẩm tùy chọn chỉ vì một concrete factory chưa triển khai được.**

Nếu một họ không thể đáp ứng yêu cầu cốt lõi, cần lựa chọn rõ ràng: không cho họ đó tham gia màn hình này, thay đổi yêu cầu sản phẩm ở cấp nghiệp vụ hoặc thiết kế một màn hình khác với hợp đồng phù hợp.

### Câu hỏi giúp xác định tính bắt buộc

- Client có thể hoàn thành chức năng chính khi không có sản phẩm đó không?
- Tất cả các họ được hỗ trợ có thể cung cấp một biến thể đúng nghĩa không?
- Việc trả sản phẩm giả để giữ chữ ký có làm sai hành vi hay gây hiểu nhầm không?
- Khi khởi tạo thất bại, hệ thống cần báo **lỗi cấu hình** hay có một **phương án hoạt động thay thế** thực sự?

Không nên quyết định rằng một loại là bắt buộc chỉ vì “factory hiện tại đã có phương thức đó”. Hãy xuất phát từ **yêu cầu sử dụng của client**.

## 3. Xác định sản phẩm tùy chọn

**Sản phẩm tùy chọn** chỉ có ý nghĩa khi ứng dụng đã định nghĩa được **hành vi đúng trong trường hợp sản phẩm không hiện diện**.

Trong ví dụ, SettingsScreen vẫn hoạt động với Button và Checkbox khi không có Tooltip. Khi cấu hình muốn hiển thị tooltip, chỉ họ Desktop đáp ứng được; họ Touch không có sản phẩm đó trong phiên bản đang xét.

Một API Java có thể biểu diễn sự vắng mặt bằng **Optional<Tooltip>**:

~~~java
import java.util.Optional;

interface Tooltip {
    String render();
}

interface ScreenFactory {
    Button createButton();       // Bắt buộc.
    Checkbox createCheckbox();   // Bắt buộc.
    Optional<Tooltip> createTooltip(); // Có thể không có.
}
~~~

Với hợp đồng này:

- **DesktopFactory.createTooltip()** có thể trả **Optional.of(new DesktopTooltip())**.
- **TouchFactory.createTooltip()** trả **Optional.empty()**.
- Client kiểm tra **isPresent()** hoặc dùng các thao tác Optional thích hợp trước khi dùng Tooltip.

**Optional.empty() không đồng nghĩa với lỗi.** Nó là kết quả hợp lệ nếu Tooltip không cần thiết cho chức năng được yêu cầu. Nếu người dùng **đã yêu cầu tooltip**, nhưng factory trả Optional.empty(), lúc đó **cấu hình đang yêu cầu một tổ hợp không được hỗ trợ** và ứng dụng phải xử lý rõ ràng.

### Không dùng Optional làm cớ bỏ qua yêu cầu cốt lõi

Một thiết kế như sau thường làm yếu hợp đồng khi cả hai loại đều bắt buộc:

~~~java
// Phản ví dụ nếu Button và Checkbox luôn bắt buộc:
interface TooWeakScreenFactory {
    Optional<Button> createButton();
    Optional<Checkbox> createCheckbox();
}
~~~

Client sẽ phải xử lý trường hợp **không có Button hoặc Checkbox** ở nhiều chỗ, dù nghiệp vụ không có màn hình hợp lệ nào như vậy. Khi phần tử bắt buộc bị thiếu, hãy phát hiện và báo lỗi thay vì biến mọi sản phẩm thành tùy chọn.

### Có phải sản phẩm tùy chọn luôn cần một phương thức trong factory chính?

Không nhất thiết. Có vài cách biểu diễn:

| Thiết kế | Khi phù hợp | Điểm đánh đổi |
| --- | --- | --- |
| **Optional<Tooltip> trong ScreenFactory** | Số ít loại tùy chọn, hầu hết client hiểu khái niệm Tooltip | Mỗi concrete factory phải thực hiện phương thức và biểu diễn sự vắng mặt |
| **Factory tùy chọn riêng** (ví dụ TooltipFactory) | Tooltip là nhóm chức năng độc lập | Cần quản lý mối quan hệ giữa factory phụ và họ chính |
| **Capability interface** (ví dụ HoverTooltipSupport) | Chỉ một số họ có năng lực đặc thù và không muốn mở rộng factory cơ bản | Client cần kiểm tra năng lực hoặc nhận capability qua composition root |
| **Null Object** có ngữ nghĩa rõ | Hành vi “không làm gì” thực sự đáp ứng yêu cầu sử dụng | Có thể che giấu tính năng không được hỗ trợ nếu dùng tùy tiện |

Trong bài này chọn **Optional<Tooltip>** để người học nhìn thấy sự khác nhau giữa **sản phẩm cần có** và **sản phẩm có thể vắng mặt** ngay trong hợp đồng.

## 4. Xác định tổ hợp không được hỗ trợ

Một tổ hợp bị từ chối khi **các điều kiện phối hợp không thể cùng thỏa mãn**, dù từng sản phẩm có thể hợp lệ khi dùng độc lập.

### 4.1. Tổ hợp trộn hai họ

Ví dụ:

~~~java
// Phản ví dụ: các kiểu riêng lẻ đúng, nhưng hai đối tượng khác họ.
Button button = new DesktopButton();
Checkbox checkbox = new TouchCheckbox();
~~~

Button là Button, Checkbox là Checkbox; tuy nhiên tổ hợp này phá quy tắc **“một màn hình dùng một họ tương tác”**. Abstract Factory hỗ trợ duy trì tính nhất quán bằng cách tạo cả bộ từ **một concrete factory**. Khi đối tượng đến từ plugin hoặc mã cũ, có thể kiểm tra **family token** tại runtime.

### 4.2. Yêu cầu tính năng mà họ không có

Ví dụ người dùng yêu cầu:

~~~text
family = touch
showHoverTooltip = true
~~~

Họ Touch vẫn tạo đầy đủ Button và Checkbox, nhưng không có Tooltip dựa trên hover. Đây không phải lỗi của Button hoặc Checkbox; đó là **tổ hợp family × capability không được hỗ trợ**. Nếu vẫn âm thầm bỏ tooltip khi người dùng đã yêu cầu, chương trình có thể vi phạm yêu cầu thực tế.

### 4.3. Hai sản phẩm cùng họ vẫn có thể xung đột

Danh tính họ là một điều kiện quan trọng nhưng **chưa đủ** để chứng minh mọi tổ hợp hợp lệ. Ví dụ trong một họ thiết bị, hai sản phẩm cùng báo **FamilyId.DESKTOP** nhưng một sản phẩm cần API v2 còn sản phẩm kia chỉ hỗ trợ API v1. Khi có thêm ràng buộc về phiên bản, giao thức, kích thước, quyền hoặc năng lực, phải kiểm tra các ràng buộc đó riêng.

Vì vậy nên chia quy tắc thành:

1. **Loại bắt buộc:** loại sản phẩm nào phải có?
2. **Họ:** các sản phẩm ghép cùng nhau thuộc một họ tương thích không?
3. **Năng lực/tính năng:** họ đó có đáp ứng hành vi được bật không?
4. **Ràng buộc liên sản phẩm:** hai biến thể có tương thích về giao thức, phiên bản hoặc cấu hình không?

Không nên coi việc so sánh một chuỗi familyId là **bằng chứng tuyệt đối** về tương thích hành vi.

## 5. Tạo ma trận hỗ trợ trước khi viết factory

Đối với một màn hình cụ thể, lập ma trận gồm các **họ** theo hàng và **loại sản phẩm** theo cột. Có thể dùng ba ký hiệu:

- **R** (*required*): phải cung cấp sản phẩm hợp lệ.
- **O** (*optional, available*): họ có thể cung cấp, chỉ tạo/dùng khi cần.
- **N** (*not supported*): không có biến thể hợp lệ của loại này trong họ đang xét.

| Họ / Loại | Button | Checkbox | Tooltip dạng hover |
| --- | --- | --- | --- |
| Desktop | R | R | O |
| Touch | R | R | N |

**Lưu ý:** R/O/N là cách ghi **quy tắc cho một bài toán**, không phải các giá trị bắt buộc trong ngôn ngữ Java. Một sản phẩm có thể được xem là tùy chọn trong ứng dụng A nhưng là bắt buộc trong ứng dụng B.

Tiếp theo, lập ma trận **yêu cầu tính năng × họ**:

| Cấu hình màn hình | Desktop | Touch | Giải thích |
| --- | --- | --- | --- |
| Button + Checkbox | Hỗ trợ | Hỗ trợ | Cả hai họ đáp ứng sản phẩm bắt buộc |
| Button + Checkbox + tooltip hover | Hỗ trợ | **Không hỗ trợ** | Touch không cung cấp năng lực hover tooltip |
| DesktopButton + TouchCheckbox | **Không hợp lệ** | **Không hợp lệ** | Ghép hai họ, không thể xem là một bộ nhất quán |
| Không có Checkbox | **Không hợp lệ** | **Không hợp lệ** | Thiếu loại sản phẩm bắt buộc của SettingsScreen |

Hai ma trận giải quyết hai câu hỏi khác nhau: **factory có tạo được một loại sản phẩm không** và **cấu hình cụ thể có được phép hoạt động không**. Nếu chỉ lập ma trận thứ nhất, hệ thống vẫn có thể bỏ sót các xung đột khi phối hợp.

### Một quy tắc quyết định dễ thực hiện

~~~mermaid
flowchart TD
    A["Yêu cầu tạo SettingsScreen"] --> B{"Có đủ Button và Checkbox?"}
    B -->|Không| X["Từ chối: thiếu sản phẩm bắt buộc"]
    B -->|Có| C{"Các sản phẩm cùng họ?"}
    C -->|Không| Y["Từ chối: trộn họ sản phẩm"]
    C -->|Có| D{"Người dùng yêu cầu tooltip?"}
    D -->|Không| G["Hiển thị màn hình cơ bản"]
    D -->|Có| E{"Factory tạo được Tooltip?"}
    E -->|Không| Z["Từ chối tổ hợp không hỗ trợ"]
    E -->|Có| F{"Tooltip có tương thích không?"}
    F -->|Không| Z
    F -->|Có| H["Hiển thị màn hình có tooltip"]
~~~

Sơ đồ minh họa một **chính sách fail-fast**: khi chức năng được yêu cầu nhưng không thể thực hiện, thông báo lỗi ở thời điểm ghép các sản phẩm thay vì âm thầm hiển thị giao diện thiếu chức năng.

## 6. Ví dụ Java hoàn chỉnh: bắt buộc, tùy chọn và từ chối tổ hợp sai

Ví dụ chạy độc lập trong một tệp **Main.java**, sử dụng Java 8 trở lên và không cần thư viện ngoài. Các lớp được đặt lồng nhau để dễ đọc; dự án thực tế có thể tách chúng thành interface và lớp theo package.

~~~java
import java.util.Objects;
import java.util.Optional;

public class Main {
    enum FamilyId {
        DESKTOP, TOUCH
    }

    // Mỗi sản phẩm có thể công bố họ để kiểm tra lúc ghép.
    interface Product {
        FamilyId family();
        String render();
    }

    interface Button extends Product {
    }

    interface Checkbox extends Product {
    }

    interface Tooltip extends Product {
    }

    // Hợp đồng chung: Button và Checkbox luôn bắt buộc.
    // Tooltip có thể vắng mặt, nhưng không được trả null Optional.
    interface ScreenFactory {
        FamilyId family();
        Button createButton();
        Checkbox createCheckbox();
        Optional<Tooltip> createTooltip();
    }

    // ===== Họ Desktop =====
    static final class DesktopButton implements Button {
        public FamilyId family() {
            return FamilyId.DESKTOP;
        }

        public String render() {
            return "[DESKTOP] Button (chuột)";
        }
    }

    static final class DesktopCheckbox implements Checkbox {
        public FamilyId family() {
            return FamilyId.DESKTOP;
        }

        public String render() {
            return "[DESKTOP] Checkbox (chuột)";
        }
    }

    static final class DesktopTooltip implements Tooltip {
        public FamilyId family() {
            return FamilyId.DESKTOP;
        }

        public String render() {
            return "[DESKTOP] Tooltip (hover)";
        }
    }

    static final class DesktopFactory implements ScreenFactory {
        public FamilyId family() {
            return FamilyId.DESKTOP;
        }

        public Button createButton() {
            return new DesktopButton();
        }

        public Checkbox createCheckbox() {
            return new DesktopCheckbox();
        }

        public Optional<Tooltip> createTooltip() {
            return Optional.of(new DesktopTooltip());
        }
    }

    // ===== Họ Touch =====
    static final class TouchButton implements Button {
        public FamilyId family() {
            return FamilyId.TOUCH;
        }

        public String render() {
            return "[TOUCH] Button (chạm)";
        }
    }

    static final class TouchCheckbox implements Checkbox {
        public FamilyId family() {
            return FamilyId.TOUCH;
        }

        public String render() {
            return "[TOUCH] Checkbox (chạm)";
        }
    }

    static final class TouchFactory implements ScreenFactory {
        public FamilyId family() {
            return FamilyId.TOUCH;
        }

        public Button createButton() {
            return new TouchButton();
        }

        public Checkbox createCheckbox() {
            return new TouchCheckbox();
        }

        public Optional<Tooltip> createTooltip() {
            // Không hỗ trợ tooltip dựa trên hover trong họ Touch.
            return Optional.empty();
        }
    }

    // ===== Client chỉ dùng các hợp đồng trừu tượng =====
    static final class SettingsScreen {
        private final Button button;
        private final Checkbox checkbox;
        private final Optional<Tooltip> tooltip;

        SettingsScreen(ScreenFactory factory, boolean requestTooltip) {
            Objects.requireNonNull(factory, "factory");
            FamilyId expected = Objects.requireNonNull(
                    factory.family(), "factory.family()");

            // Hai sản phẩm bắt buộc không được null và phải cùng họ.
            Button b = Objects.requireNonNull(
                    factory.createButton(), "Factory thiếu Button");
            Checkbox c = Objects.requireNonNull(
                    factory.createCheckbox(), "Factory thiếu Checkbox");
            checkFamily(expected, b, "Button");
            checkFamily(expected, c, "Checkbox");

            Optional<Tooltip> selectedTooltip = Optional.empty();
            if (requestTooltip) {
                Optional<Tooltip> available = Objects.requireNonNull(
                        factory.createTooltip(), "Factory trả null Optional");
                if (!available.isPresent()) {
                    throw new UnsupportedOperationException(
                            "Họ " + expected + " không hỗ trợ hover tooltip");
                }
                checkFamily(expected, available.get(), "Tooltip");
                selectedTooltip = available;
            }

            this.button = b;
            this.checkbox = c;
            this.tooltip = selectedTooltip;
        }

        private static void checkFamily(
                FamilyId expected, Product product, String kind) {
            if (product.family() != expected) {
                throw new IllegalArgumentException(
                        kind + " không cùng họ với factory: " + expected);
            }
        }

        String render() {
            String result = button.render()
                    + System.lineSeparator() + checkbox.render();
            if (tooltip.isPresent()) {
                result += System.lineSeparator() + tooltip.get().render();
            }
            return result;
        }
    }

    public static void main(String[] args) {
        if (args.length > 2) {
            throw new IllegalArgumentException(
                    "Cách dùng: java Main [desktop|touch] [tooltip]");
        }

        String familyName = args.length == 0 ? "desktop" : args[0];
        ScreenFactory factory;
        if ("desktop".equalsIgnoreCase(familyName)) {
            factory = new DesktopFactory();
        } else if ("touch".equalsIgnoreCase(familyName)) {
            factory = new TouchFactory();
        } else {
            throw new IllegalArgumentException(
                    "Họ không được hỗ trợ: " + familyName);
        }

        if (args.length == 2 && !"tooltip".equalsIgnoreCase(args[1])) {
            throw new IllegalArgumentException(
                    "Tùy chọn không hợp lệ: " + args[1]);
        }
        boolean requestTooltip = args.length == 2;

        SettingsScreen screen = new SettingsScreen(
                factory, requestTooltip);
        System.out.println(screen.render());
    }
}
~~~

### 6.1. Chạy các tổ hợp hợp lệ

Lưu mã vào **Main.java** ở thư mục làm việc rồi biên dịch:

~~~text
javac -encoding UTF-8 Main.java
~~~

Chạy màn hình Desktop chỉ với hai sản phẩm bắt buộc:

~~~text
java Main desktop
[DESKTOP] Button (chuột)
[DESKTOP] Checkbox (chuột)
~~~

Yêu cầu thêm Tooltip cho họ Desktop:

~~~text
java Main desktop tooltip
[DESKTOP] Button (chuột)
[DESKTOP] Checkbox (chuột)
[DESKTOP] Tooltip (hover)
~~~

Chạy màn hình Touch:

~~~text
java Main touch
[TOUCH] Button (chạm)
[TOUCH] Checkbox (chạm)
~~~

Nếu không truyền tham số, chương trình chọn Desktop mặc định và không hiển thị Tooltip.

### 6.2. Thử tổ hợp không được hỗ trợ

~~~text
java Main touch tooltip
~~~

Chương trình ném **UnsupportedOperationException** với nội dung **“Họ TOUCH không hỗ trợ hover tooltip”**. Phần stack trace và mã thoát phụ thuộc môi trường chạy.

Sự thất bại này là **hành vi có chủ đích**: Button và Checkbox của Touch vẫn hợp lệ, nhưng yêu cầu thêm Tooltip trái với ma trận hỗ trợ.

### 6.3. Ba lớp kiểm tra trong SettingsScreen

1. **Objects.requireNonNull** bảo vệ sản phẩm **bắt buộc** và ngăn factory trả null thay cho Optional.
2. **checkFamily** đối chiếu token của mỗi sản phẩm với token của factory để phát hiện một số trường hợp **trộn họ**.
3. **Optional.isPresent()** phân biệt **không có Tooltip** với **có Tooltip**, và chỉ báo lỗi thiếu năng lực khi **requestTooltip=true**.

Nếu requestTooltip=false, SettingsScreen **không gọi** createTooltip(). Điều này tránh tạo một sản phẩm tùy chọn khi client không dùng đến nó, đặc biệt hữu ích nếu việc tạo sản phẩm thực tế đắt đỏ.

**Giới hạn:** family token chỉ kiểm tra **danh tính họ do đối tượng công bố**. Nó không chứng minh hành vi render() thật sự tương thích. Trong hệ thống thực, cần kiểm thử quy tắc giao thức, phiên bản và những hành vi quan trọng khác.

## 7. Các lựa chọn API khi một họ không có biến thể

Giả sử công ty muốn phát triển thêm họ **Voice**. Họ mới có cách tương tác bằng giọng nói và **không có Checkbox đồ họa**. Có nên viết VoiceFactory trả null từ createCheckbox() để tham gia ScreenFactory không?

**Không nên.** Bởi ScreenFactory hiện định nghĩa Button và Checkbox là bắt buộc. Có ba hướng thiết kế hợp lý hơn tùy yêu cầu thật:

1. **Không đưa VoiceFactory vào nhóm factory của SettingsScreen** nếu màn hình này cần điều khiển đồ họa. Voice có thể thuộc một abstraction khác.
2. **Thiết kế giao diện cấp cao hơn**, ví dụ SelectableOption hoặc ConfirmAction, nếu các họ thực sự có thể thực hiện chung một hành vi theo các phương thức khác nhau.
3. **Tách contract theo năng lực** nếu bài toán có một lõi dùng chung và các nhóm chức năng hoàn toàn độc lập, nhưng tránh tạo interface chỉ để bỏ qua mọi phương thức không hỗ trợ.

Việc chọn hướng nào phụ thuộc vào **hợp đồng mà client cần**, chứ không có quy tắc rằng mọi họ phải cố triển khai mọi loại sản phẩm.

### Vì sao không lạm dụng Null Object?

Null Object hữu ích khi “không thực hiện hành động” là một hành vi **được chấp nhận rõ ràng**. Nhưng thay Checkbox bắt buộc bằng một đối tượng không làm gì sẽ khiến thao tác lựa chọn của người dùng không có hiệu lực. Khi đó hệ thống đang che giấu một yêu cầu không thể đáp ứng.

Tương tự, nếu người dùng đã yêu cầu tooltip, âm thầm trả Optional.empty() rồi bỏ qua mà không thông báo có thể gây mất chức năng. Chính sách xử lý phải phản ánh ý nghĩa nghiệp vụ: **bỏ qua hợp lệ**, **dùng phương án thay thế được chấp nhận**, hoặc **từ chối cấu hình**.

### Có nên dùng phương thức mặc định trong interface?

Java 8 cho phép một interface định nghĩa phương thức mặc định:

~~~java
interface ScreenFactory {
    Button createButton();
    Checkbox createCheckbox();

    default Optional<Tooltip> createTooltip() {
        return Optional.empty();
    }
}
~~~

Cách này có thể giảm công cập nhật các concrete factory hiện hữu khi bổ sung **một loại sản phẩm tùy chọn**, nhưng phải ghi rõ Optional.empty() có nghĩa là **không hỗ trợ**. Nó cũng không miễn việc cập nhật client/kiểm thử theo quy tắc mới. Nếu Tooltip trở thành **bắt buộc** cho mọi họ, default Optional.empty() không còn phù hợp với hợp đồng đó.

## 8. Khi mở rộng họ hoặc loại sản phẩm

Trong Abstract Factory, **thêm họ** và **thêm loại** có chi phí khác nhau.

### Thêm họ mới vào một hợp đồng ổn định

Ví dụ tạo **GamepadFactory** cho một thiết bị chơi game:

- Kiểm tra ScreenFactory có thật sự phù hợp với trường hợp dùng gamepad hay không.
- Nếu phù hợp, cung cấp **GamepadButton** và **GamepadCheckbox** để đáp ứng hai loại bắt buộc theo đúng ngữ nghĩa.
- Quyết định xem có hỗ trợ Tooltip hay không, rồi trả Optional thích hợp.
- Kiểm tra mọi tổ hợp liên sản phẩm trước khi đăng ký GamepadFactory để client sử dụng.

Không nên khai báo một họ là **được hỗ trợ hoàn toàn** chỉ vì class đã triển khai interface; việc đáp ứng **bất biến của màn hình** mới là tiêu chí.

### Thêm loại sản phẩm mới vào các họ đang có

Nếu ứng dụng cần **TextField bắt buộc**:

- Thêm interface TextField và createTextField() vào ScreenFactory.
- Cung cấp DesktopTextField **và** TouchTextField phù hợp.
- Cập nhật mọi concrete factory và kiểm thử màn hình.

Nếu TextField **chỉ tùy chọn**:

- Thỏa thuận hành vi của màn hình khi không có TextField.
- Có thể dùng Optional<TextField> hoặc một capability riêng.
- Cập nhật **ma trận hỗ trợ** và các trường hợp yêu cầu tính năng tương ứng.

**Nhận định thiết kế:** Abstract Factory đặc biệt phù hợp khi danh sách **loại sản phẩm chủ đạo tương đối ổn định**, còn số họ cần hỗ trợ có thể tăng. Nếu loại mới thường xuyên xuất hiện và không có mặt ở đa số họ, hãy xem xét chia các nhóm factory theo trách nhiệm hoặc khả năng riêng.

## 9. Kiểm thử các trường hợp quan trọng

Một ma trận có nhiều ô “hỗ trợ/không hỗ trợ” nên được kiểm chứng bằng các ca tương ứng, thay vì chỉ kiểm thử một concrete factory.

| Trường hợp | Cách kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| Desktop cơ bản | Chọn Desktop, không yêu cầu Tooltip | Tạo đủ Button và Checkbox cùng họ |
| Desktop có Tooltip | Chọn Desktop, bật Tooltip | Tạo đủ ba sản phẩm cùng họ |
| Touch cơ bản | Chọn Touch, không yêu cầu Tooltip | Tạo đủ Button và Checkbox; màn hình hợp lệ |
| Touch + Tooltip | Chọn Touch, yêu cầu Tooltip | Từ chối với lỗi năng lực rõ ràng |
| Factory thiếu Checkbox | Factory trả null cho loại bắt buộc | Fail-fast ngay khi khởi tạo màn hình |
| Factory trộn DesktopButton với TouchCheckbox | Factory trả hai họ khác nhau | Kiểm tra family token từ chối |
| Factory trả null Optional | createTooltip() trả null khi được gọi | Phát hiện vi phạm hợp đồng Optional |
| Họ không có tên hợp lệ | Chọn một family chưa đăng ký | Từ chối lựa chọn thay vì âm thầm đổi họ |

Trong dự án Java thật, có thể dùng **JUnit** hoặc bộ kiểm thử phù hợp để viết assertion cho từng trường hợp. Mã minh họa ở trên cho phép thử thủ công ba tổ hợp hợp lệ và tổ hợp Touch + Tooltip; các lỗi factory cần một implementation giả hoặc kiểm thử riêng để tạo tình huống.

### Giới hạn của các phép kiểm tra

- **Kiểm tra kiểu** cho biết đối tượng triển khai đúng Button/Checkbox/Tooltip; nó không tự chứng minh **cùng họ**.
- **Kiểm tra family token** phát hiện một số trường hợp sai họ, nhưng dựa vào token do đối tượng công bố.
- **Kiểm tra Optional** xác nhận có/không có một sản phẩm tùy chọn trong ngữ cảnh khởi tạo.
- **Kiểm thử tích hợp** kiểm tra các ràng buộc ngoài kiểu và token, ví dụ thứ tự khởi tạo, phiên bản giao thức, vòng đời tài nguyên và hành vi thực tế.

Những lớp bảo vệ này bổ sung cho nhau. Không nên tuyên bố một tổ hợp “được bảo đảm tương thích” nếu chỉ mới xác nhận nó biên dịch hoặc cùng familyId.

## 10. Các lỗi thường gặp khi thiết kế ma trận hỗ trợ

**Lỗi 1 — Xem mọi sản phẩm là bắt buộc.** Concrete factory bị ép viết các lớp vô nghĩa hoặc ném UnsupportedOperationException từ những phương thức mà client tưởng luôn thành công. Hãy chỉ giữ yêu cầu bắt buộc ở nơi nghiệp vụ thật sự cần.

**Lỗi 2 — Xem mọi sản phẩm là tùy chọn.** API tràn ngập Optional và client phải xử lý trạng thái thiếu những thành phần cốt lõi. Hãy giữ hợp đồng mạnh cho sản phẩm bắt buộc.

**Lỗi 3 — Dùng null thay Optional.empty().** Người gọi không thể phân biệt lỗi implementation với “không có sản phẩm” và dễ gặp NullPointerException ở vị trí khó chẩn đoán.

**Lỗi 4 — Tự động thay sản phẩm khác họ.** Nếu Touch không hỗ trợ hover tooltip, đưa DesktopTooltip vào màn hình Touch để tránh lỗi có thể phá quy tắc tương thích. Chỉ dùng phương án thay thế khi sản phẩm **thực sự tương thích** và đã được chấp nhận trong yêu cầu.

**Lỗi 5 — Âm thầm bỏ yêu cầu người dùng.** Khi Tooltip được yêu cầu nhưng không hỗ trợ, bỏ qua mà không thông báo làm giao diện thể hiện sai cấu hình. Cần xác định rõ chính sách lỗi hoặc thương lượng giảm tính năng.

**Lỗi 6 — Coi ma trận loại sản phẩm là đầy đủ.** Ma trận đó chưa thể hiện mọi tổ hợp về giao thức, phiên bản hay tính năng. Hãy bổ sung quy tắc liên sản phẩm khi nghiệp vụ đòi hỏi.

## 11. Bài tập vận dụng

### Bài A — Xây dựng ma trận ba họ

Thêm họ **TVRemote** vào ứng dụng. TVRemote có Button, Checkbox, nhưng không có hover tooltip. Hãy viết ma trận R/O/N, phân loại tổ hợp nào hợp lệ và giải thích vì sao **không nên dùng DesktopTooltip** để lấp ô còn thiếu.

### Bài B — Thêm loại sản phẩm tùy chọn

Thêm interface **HelpIcon** chỉ được cung cấp ở họ Desktop. Hãy sửa hợp đồng factory để trả **Optional<HelpIcon>** và cập nhật SettingsScreen theo quy tắc: nếu không yêu cầu biểu tượng trợ giúp thì không tạo; nếu đã yêu cầu mà không được hỗ trợ, trả lỗi rõ ràng.

### Bài C — Thêm loại sản phẩm bắt buộc

Giả sử SettingsScreen yêu cầu **TextField** cho mọi cấu hình. Hãy thêm TextField vào ma trận, cập nhật abstract factory và hai concrete factory. Viết một kiểm thử cho trường hợp một factory trả null hoặc trả TextField khác họ.

### Bài D — Thiết kế quy tắc xung đột

Trong một họ màn hình, **Tooltip** và **ModalOverlay** đều có thể tồn tại nhưng không được hoạt động **cùng lúc** vì che khuất nội dung. Hãy bổ sung ma trận tổ hợp tính năng và đề xuất điểm kiểm tra trước khi hiển thị. Lưu ý: hai sản phẩm có thể thuộc **cùng họ** mà vẫn xung đột.

### Bài E — Phân tích lựa chọn khác

Hệ thống cần hỗ trợ Voice, nhưng Voice không thể cung cấp Checkbox theo ngữ nghĩa hiện tại. Hãy so sánh ba phương án: loại Voice khỏi SettingsScreen, thiết kế một hợp đồng cấp cao hơn, hoặc tách client/factory theo năng lực. Giải thích vì sao **trả null từ createCheckbox()** không phải cách sửa đúng.

## 12. Ghi nhớ

- **Sản phẩm bắt buộc** là thành phần client cần để hoạt động đúng; factory hợp lệ phải cung cấp và không được âm thầm bỏ qua.
- **Sản phẩm tùy chọn** có thể vắng mặt khi chức năng không được yêu cầu; cần biểu diễn sự vắng mặt rõ ràng và chỉ tạo khi cần.
- **Tổ hợp không hỗ trợ** có thể do thiếu năng lực của một họ, do trộn họ, hoặc do ràng buộc tương thích giữa các sản phẩm dù chúng cùng họ.
- **Ma trận hỗ trợ** là công cụ thiết kế trước khi lập trình: phân biệt sản phẩm nào có sẵn và yêu cầu tổ hợp nào hợp lệ.
- **Abstract Factory giúp chọn và tạo một họ nhất quán**, nhưng không tự bảo đảm mọi triển khai đúng hợp đồng hoặc mọi kết hợp thành phần đều tương thích.

Một thiết kế tốt sẽ làm rõ ranh giới giữa **thiếu sản phẩm bắt buộc**, **sản phẩm tùy chọn không hiện diện** và **yêu cầu cấu hình không được hỗ trợ**. Nhờ đó, client có thể sử dụng Abstract Factory mà vẫn dự đoán được hành vi khi mở rộng sang các họ sản phẩm mới.
