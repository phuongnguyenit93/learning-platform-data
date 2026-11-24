# Phát hiện cấu hình sai và quyết định báo lỗi hoặc dùng biến thể mặc định

## 1. Vì sao lựa chọn biến thể cần kiểm tra cấu hình?

Trong **Abstract Factory**, ứng dụng thường chọn một **concrete factory** dựa trên cấu hình, sau đó dùng factory đó để tạo các sản phẩm cùng họ. Ví dụ, cấu hình giao diện `APP_THEME=dark` có thể dẫn tới `DarkUIFactory`, tạo cả `DarkButton` và `DarkDialog`.

Quá trình này có vẻ đơn giản:

~~~java
UIFactory factory = darkMode
        ? new DarkUIFactory()
        : new LightUIFactory();
~~~

Nhưng nếu `darkMode` đến từ chuỗi cấu hình bên ngoài thì câu hỏi quan trọng là: **chuỗi đó có thực sự hợp lệ không?**

Xem cách viết sau:

~~~java
String raw = System.getenv("APP_THEME");
UIFactory factory = "dark".equalsIgnoreCase(raw)
        ? new DarkUIFactory()
        : new LightUIFactory();
~~~

Khi `APP_THEME=drak` (gõ nhầm), chương trình âm thầm chọn giao diện Light. Người vận hành tưởng đã triển khai Dark, trong khi ứng dụng chạy khác cấu hình dự kiến. Với một lựa chọn quan trọng hơn như nhà cung cấp thanh toán hoặc định dạng lưu trữ, việc âm thầm chọn sai biến thể có thể gây lỗi nghiêm trọng.

**Nhiệm vụ của bước lựa chọn biến thể** không chỉ là ánh xạ `dark → DarkUIFactory`. Nó còn phải:

1. Đọc đúng nguồn cấu hình và xác định giá trị được cung cấp hay chưa.
2. Phân biệt **thiếu cấu hình**, **cấu hình rỗng**, **cấu hình không được hỗ trợ** và **cấu hình hợp lệ**.
3. Quyết định theo chính sách rõ ràng: **báo lỗi sớm** (*fail fast*) hay **dùng biến thể mặc định** (*fallback*).
4. Chọn **một factory nhất quán cho cả họ sản phẩm**, sau khi cấu hình đã được xử lý.
5. Để lại thông tin chẩn đoán phù hợp nếu có sai cấu hình.

Bài này thuộc chương **Lựa chọn biến thể** trong nội dung học **Abstract Factory** của nhóm mẫu thiết kế khởi tạo (*Creational Design Patterns*). Trọng tâm là phát hiện cấu hình sai và xây dựng quyết định xử lý có chủ đích trong Java.

## 2. Nhận diện đúng các trạng thái cấu hình

Giả sử ứng dụng hỗ trợ hai họ giao diện `light` và `dark`, với `light` là mặc định khi người dùng **không chỉ định** chủ đề.

| Đầu vào `APP_THEME` | Phân loại | Cách hiểu hợp lý |
| --- | --- | --- |
| Không tồn tại (`null` khi đọc biến môi trường) | **Thiếu** | Người dùng chưa chọn; nếu tùy chọn không bắt buộc, có thể áp dụng mặc định |
| `"light"` | **Hợp lệ** | Chọn Light |
| `"dark"` | **Hợp lệ** | Chọn Dark |
| `" DARK "` | **Hợp lệ sau chuẩn hóa** | Loại khoảng trắng đầu/cuối và chuẩn hóa chữ hoa/thường |
| `""` hoặc `"   "` | **Rỗng** | Đã cung cấp giá trị nhưng không chỉ rõ biến thể; trong thiết kế bài này coi là cấu hình sai |
| `"drak"` | **Không được hỗ trợ** | Có khả năng gõ nhầm; cần báo lỗi hoặc fallback có cảnh báo |
| `"blue"` | **Không được hỗ trợ** | Không có factory tương ứng trong phiên bản ứng dụng |
| `"light,dark"` | **Sai định dạng** | Một cấu hình chỉ được chọn một họ, không phải danh sách |

**Thiếu** và **rỗng** có thể mang ý nghĩa khác nhau. Nếu `APP_THEME` là tùy chọn, không thiết lập giá trị có thể được hiểu là «sử dụng mặc định». Nhưng thiết lập giá trị thành chuỗi rỗng có thể là lỗi trong script triển khai, vì thế nên nhận diện thay vì ngầm coi mọi chuỗi lạ là Light.

Đây là **quy tắc của ví dụ**, không phải bắt buộc của Abstract Factory. Nếu nghiệp vụ xác định giá trị trống cũng tương đương «chưa chọn», điều đó cần được ghi thành hợp đồng cấu hình và áp dụng thống nhất. Nếu `APP_THEME` là trường bắt buộc, ngay cả `null` cũng phải được xem là sai.

### 2.1. Chuẩn hóa vừa đủ, không đoán hộ người cấu hình

Với một tên chủ đề thông thường, có thể chuẩn hóa:

~~~java
String normalized = raw.trim().toLowerCase(java.util.Locale.ROOT);
~~~

`trim()` bỏ các ký tự khoảng trắng ASCII ở đầu/cuối, còn `toLowerCase(Locale.ROOT)` làm việc theo quy tắc ổn định, không phụ thuộc locale mặc định của máy chạy.

Sau đó so sánh **chính xác** với `"light"` và `"dark"`. Không nên sử dụng quy tắc như `contains("dark")` hoặc `startsWith("dark")` để «sửa» cấu hình: chúng có thể nhận những giá trị chưa từng được hỗ trợ.

Nếu ứng dụng chủ động hỗ trợ alias, ví dụ `"night"` là tên khác của `"dark"`, hãy ghi alias vào tập giá trị được chấp nhận một cách tường minh và kiểm thử nó. Alias là **quy ước API cấu hình**, không phải lý do để chấp nhận mọi chuỗi gần giống.

### 2.2. Cấu hình hợp lệ về chữ nhưng không khả dụng ở runtime

Không phải lỗi nào cũng là giá trị lạ. Ví dụ `APP_THEME=dark` có trong danh sách hợp lệ, nhưng phiên bản ứng dụng đang triển khai **không đóng gói `DarkUIFactory`**. Khi đó cấu hình **cú pháp hợp lệ nhưng không được runtime hỗ trợ**.

Quy trình chọn factory cần kiểm tra cả hai:

- **Hợp lệ về cấu hình:** giá trị tương ứng với một biến thể đã định nghĩa.
- **Khả dụng về triển khai:** có concrete factory đáp ứng biến thể đó và các dependency cần thiết.

Nếu không thể tạo factory do lỗi chương trình, lỗi dependency hoặc thiếu triển khai, không nên tự động xử lý như lỗi gõ sai tên chủ đề. Đây có thể là lỗi triển khai cần báo riêng.

## 3. Hai chính sách xử lý sai cấu hình

Khi đầu vào sai, hai cách xử lý thường gặp là **báo lỗi sớm** và **fallback sang biến thể mặc định**.

### 3.1. Fail fast: ngừng khởi tạo và báo cấu hình sai

Với chế độ nghiêm ngặt (*strict / fail fast*), giá trị không hợp lệ khiến bước khởi tạo thất bại trước khi tạo các thành phần phụ thuộc.

~~~text
APP_THEME=drak
→ Kiểm tra: không nằm trong {light, dark}
→ Báo lỗi: APP_THEME phải là 'light' hoặc 'dark'
→ Không tạo GUIFactory, không khởi chạy màn hình
~~~

Lợi ích:

- Phát hiện sai cấu hình tại nguồn, tránh việc ứng dụng âm thầm chạy với biến thể khác mong muốn.
- Giúp triển khai tự động nhận biết lỗi qua thông báo và **mã thoát khác 0**.
- Thích hợp với cấu hình cần chính xác để bảo đảm hành vi, khả năng tương thích hoặc ràng buộc hệ thống.

Chi phí: ứng dụng có thể không khởi chạy dù có một biến thể mặc định đang hoạt động. Đây là chủ đích nếu chạy sai cấu hình nguy hiểm hơn dừng để sửa.

### 3.2. Fallback: dùng mặc định nhưng phải có chính sách và dấu vết

Trong chế độ fallback, ứng dụng có thể tiếp tục bằng một biến thể mặc định đã công bố:

~~~text
APP_THEME=drak
→ Kiểm tra: không hợp lệ
→ [WARN] APP_THEME không hợp lệ; dùng biến thể mặc định 'light'
→ Chọn LightUIFactory
→ Tạo tất cả sản phẩm GUI của họ Light
~~~

Fallback phù hợp khi:

- Biến thể là **tùy chọn về trải nghiệm**, chẳng hạn chủ đề hiển thị.
- Có mặc định **an toàn và được người dùng chấp nhận**.
- Việc chạy với mặc định ít gây hại hơn không khởi động ứng dụng.
- Cảnh báo có thể được theo dõi và cấu hình sai có thể được sửa.

Fallback **không đồng nghĩa với nuốt lỗi**. Nếu chọn mặc định cho giá trị không hợp lệ, cần log hoặc tín hiệu chẩn đoán để đội vận hành không bỏ sót cấu hình sai.

Không nên fallback tùy tiện với cấu hình phân vùng dữ liệu, thông số bảo mật, nhà cung cấp thanh toán hoặc giao thức có yêu cầu tương thích chặt. Chọn sai họ sản phẩm trong những miền đó có thể nguy hiểm hơn việc từ chối khởi chạy.

### 3.3. Ma trận ra quyết định

| Tình huống | Chính sách thường phù hợp | Lý do |
| --- | --- | --- |
| Chủ đề Light/Dark là tùy chọn, không được cung cấp | Mặc định Light theo đặc tả | Đây không nhất thiết là lỗi |
| Chủ đề được cung cấp nhưng gõ nhầm, môi trường phát triển | Fail fast | Phát hiện lỗi cấu hình ngay |
| Chủ đề gõ nhầm trong ứng dụng cần tiếp tục phục vụ người dùng | Fallback kèm cảnh báo, nếu đã được cho phép | Duy trì trải nghiệm tối thiểu |
| Chọn sai nhà cung cấp thanh toán | Thường fail fast | Tránh vận hành theo đường xử lý không mong muốn |
| Thiếu secret hoặc chứng chỉ bắt buộc | Fail fast | Không tồn tại mặc định an toàn |
| Factory đã chọn bị lỗi khởi tạo do bug hoặc dependency | Báo lỗi kỹ thuật phù hợp | Không nhầm lỗi triển khai với lỗi nhập tên biến thể |
| Chính bản thân chính sách `strict/fallback` bị viết sai | Fail fast | Không được âm thầm đổi chính sách xử lý lỗi |

**Nguyên tắc:** quyết định fallback dựa trên **rủi ro nghiệp vụ và cam kết vận hành**, không dựa vào việc viết `if/else` nào tiện hơn.

## 4. Đặt bước kiểm tra ở đâu trong kiến trúc Abstract Factory?

Một cách phân chia trách nhiệm rõ ràng là:

~~~mermaid
flowchart TD
    Source["Đọc CLI / ENV / file cấu hình"] --> Parse["Chuẩn hóa và kiểm tra biến thể"]
    Parse --> Valid{"Giá trị hợp lệ?"}
    Valid -->|Có| Theme["Theme: LIGHT hoặc DARK"]
    Valid -->|Không| Policy{"Chính sách lỗi?"}
    Policy -->|Fail fast| Error["Báo lỗi và dừng khởi tạo"]
    Policy -->|Fallback| Warning["Cảnh báo, dùng Theme mặc định"]
    Warning --> Theme
    Theme --> Selector["Chọn một concrete GUIFactory"]
    Selector --> Client["Client nhận GUIFactory"]
    Client --> Products["Tạo Button + Dialog cùng họ"]
~~~

Có thể chia thành bốn ranh giới:

1. **Nguồn cấu hình:** đọc chuỗi từ tham số dòng lệnh, biến môi trường hoặc hệ thống cấu hình.
2. **Bộ phân giải cấu hình (*resolver*):** chuyển chuỗi thành một giá trị **kiểu an toàn**, ví dụ enum `Theme.LIGHT` / `Theme.DARK`, hoặc trả lỗi theo chính sách.
3. **Bộ chọn factory:** ánh xạ một `Theme` hợp lệ sang `LightUIFactory` hay `DarkUIFactory`.
4. **Client:** chỉ nhận `GUIFactory` và gọi các phương thức tạo sản phẩm qua interface.

Phân chia này giúp tránh đưa logic kiểm tra cấu hình vào từng màn hình:

~~~java
// Mùi thiết kế: client tự đọc cấu hình và tự chọn biến thể.
class Screen {
    void render() {
        String theme = System.getenv("APP_THEME");
        // ... mỗi màn hình lại tự if/switch và tạo lớp cụ thể
    }
}
~~~

Thay vào đó, quyết định cấu hình nên được xử lý ở **composition root**, tức nơi lắp ghép các dependency lúc ứng dụng khởi động (hoặc lúc một phạm vi UI mới được tạo).

**Điểm đặc biệt của Abstract Factory:** sau khi đã chọn factory, hãy lấy **toàn bộ sản phẩm cùng họ** qua factory đó. Không để mỗi sản phẩm đọc lại cấu hình độc lập vì có thể tạo ra nút Light và hộp thoại Dark khi giá trị cấu hình thay đổi giữa hai lần đọc.

## 5. Ví dụ Java đầy đủ: strict và fallback

Ví dụ sử dụng **hai loại sản phẩm** là `Button` và `Dialog`, cùng **hai họ** là Light và Dark. Mã có thể đặt trong một tệp `VariantSelectionDemo.java` và chạy bằng JDK thông thường; hành vi hiển thị được mô phỏng qua console.

Quy ước của ví dụ:

- `APP_THEME` là **tùy chọn**. Nếu không có tham số chủ đề và biến môi trường cũng không được thiết lập, dùng `light`.
- Khi có giá trị, chỉ chấp nhận `light` và `dark` (không phân biệt chữ hoa/thường, bỏ khoảng trắng đầu/cuối).
- Giá trị rỗng hoặc không được hỗ trợ là **cấu hình sai**.
- Chính sách mặc định là `strict`, tức **fail fast** cho giá trị sai.
- Có thể bật `fallback` **một cách tường minh**, với cảnh báo và họ mặc định Light.
- Nếu chính tên chính sách bị viết sai, chương trình luôn báo lỗi.
- Đối số thứ nhất (nếu có) có ưu tiên so với `APP_THEME`; đối số thứ hai là `strict` hoặc `fallback`.

~~~java
import java.util.Locale;

// ==== Abstract Products ====
interface Button {
    void render();
}

interface Dialog {
    void render();
}

// ==== Abstract Factory ====
interface GUIFactory {
    Button createButton();
    Dialog createDialog();
}

// ==== Concrete Products ====
class LightButton implements Button {
    @Override
    public void render() {
        System.out.println("Light Button");
    }
}

class LightDialog implements Dialog {
    @Override
    public void render() {
        System.out.println("Light Dialog");
    }
}

class DarkButton implements Button {
    @Override
    public void render() {
        System.out.println("Dark Button");
    }
}

class DarkDialog implements Dialog {
    @Override
    public void render() {
        System.out.println("Dark Dialog");
    }
}

// ==== Concrete Factories ====
class LightGUIFactory implements GUIFactory {
    @Override
    public Button createButton() {
        return new LightButton();
    }

    @Override
    public Dialog createDialog() {
        return new LightDialog();
    }
}

class DarkGUIFactory implements GUIFactory {
    @Override
    public Button createButton() {
        return new DarkButton();
    }

    @Override
    public Dialog createDialog() {
        return new DarkDialog();
    }
}

// ==== Typed configuration ====
enum Theme {
    LIGHT, DARK
}

enum InvalidThemePolicy {
    FAIL_FAST, FALLBACK_TO_DEFAULT
}

class ThemeConfigException extends RuntimeException {
    ThemeConfigException(String message) {
        super(message);
    }
}

// Chỉ giải quyết việc phân tích/kiểm tra cấu hình.
class ThemeResolver {
    private static final Theme DEFAULT_THEME = Theme.LIGHT;

    static InvalidThemePolicy parsePolicy(String rawPolicy) {
        if (rawPolicy == null) {
            return InvalidThemePolicy.FAIL_FAST;
        }

        String value = rawPolicy.trim()
                .toLowerCase(Locale.ROOT);

        switch (value) {
            case "strict":
                return InvalidThemePolicy.FAIL_FAST;
            case "fallback":
                return InvalidThemePolicy.FALLBACK_TO_DEFAULT;
            default:
                // Chính sách sai không được âm thầm chuyển về fallback.
                throw new ThemeConfigException(
                    "Chính sách không hợp lệ; chọn 'strict' hoặc 'fallback'."
                );
        }
    }

    static Theme resolve(String rawTheme, InvalidThemePolicy policy) {
        // APP_THEME là tùy chọn: thiếu cấu hình -> mặc định.
        if (rawTheme == null) {
            return DEFAULT_THEME;
        }

        String value = rawTheme.trim()
                .toLowerCase(Locale.ROOT);

        switch (value) {
            case "light":
                return Theme.LIGHT;
            case "dark":
                return Theme.DARK;
            default:
                // Bao gồm cả chuỗi rỗng và tên biến thể không hỗ trợ.
                if (policy == InvalidThemePolicy.FAIL_FAST) {
                    throw new ThemeConfigException(
                        "APP_THEME không hợp lệ; giá trị cho phép: "
                        + "'light', 'dark'."
                    );
                }

                if (policy == InvalidThemePolicy.FALLBACK_TO_DEFAULT) {
                    // Không ghi lại nguyên văn đầu vào không tin cậy.
                    System.err.println(
                        "[WARN] APP_THEME không hợp lệ; "
                        + "sử dụng mặc định 'light'."
                    );
                    return DEFAULT_THEME;
                }

                throw new ThemeConfigException(
                    "Chính sách xử lý APP_THEME không được hỗ trợ."
                );
        }
    }
}

// Factory selector chỉ nhận giá trị đã được phân giải.
class GUIFactorySelector {
    static GUIFactory create(Theme theme) {
        if (theme == null) {
            throw new IllegalArgumentException(
                "Theme đã phân giải không được null."
            );
        }

        switch (theme) {
            case LIGHT:
                return new LightGUIFactory();
            case DARK:
                return new DarkGUIFactory();
            default:
                // Trường hợp thêm enum mới nhưng quên thêm factory.
                throw new IllegalStateException(
                    "Chưa có GUIFactory cho theme: " + theme
                );
        }
    }
}

// Client sử dụng một factory đã được chọn.
class SettingsScreen {
    private final GUIFactory factory;

    SettingsScreen(GUIFactory factory) {
        this.factory = factory;
    }

    void show() {
        Button button = factory.createButton();
        Dialog dialog = factory.createDialog();

        button.render();
        dialog.render();
    }
}

public class VariantSelectionDemo {
    public static void main(String[] args) {
        try {
            if (args.length > 2) {
                throw new ThemeConfigException(
                    "Cú pháp: java VariantSelectionDemo "
                    + "[light|dark] [strict|fallback]"
                );
            }

            // CLI có ưu tiên; nếu không truyền mới đọc APP_THEME.
            String rawTheme = args.length >= 1
                    ? args[0]
                    : System.getenv("APP_THEME");

            String rawPolicy = args.length == 2
                    ? args[1]
                    : null;

            InvalidThemePolicy policy =
                    ThemeResolver.parsePolicy(rawPolicy);

            Theme theme = ThemeResolver.resolve(rawTheme, policy);

            // Chỉ sau khi cấu hình hợp lệ mới chọn factory.
            GUIFactory factory = GUIFactorySelector.create(theme);
            new SettingsScreen(factory).show();

        } catch (ThemeConfigException ex) {
            System.err.println("[ERROR] " + ex.getMessage());
            System.exit(2); // Báo lỗi cấu hình cho hệ thống gọi.
        }
    }
}
~~~

### 5.1. Cách biên dịch và chạy

Lưu thành `VariantSelectionDemo.java` rồi chạy:

~~~bash
javac -encoding UTF-8 VariantSelectionDemo.java

# Chọn Dark hợp lệ
java VariantSelectionDemo dark

# Nhập sai và dùng chính sách nghiêm ngặt
java VariantSelectionDemo drak strict

# Nhập sai nhưng cho phép fallback
java VariantSelectionDemo drak fallback

# Tên chính sách sai: vẫn phải báo lỗi
java VariantSelectionDemo drak fallbak
~~~

**Trường hợp 1 — `dark` hợp lệ:**

~~~text
Dark Button
Dark Dialog
~~~

**Trường hợp 2 — `drak strict`:**

~~~text
[ERROR] APP_THEME không hợp lệ; giá trị cho phép: 'light', 'dark'.
~~~

Chương trình kết thúc với mã thoát **2** theo quy ước của demo; không tạo màn hình.

**Trường hợp 3 — `drak fallback`:**

~~~text
[WARN] APP_THEME không hợp lệ; sử dụng mặc định 'light'.
Light Button
Light Dialog
~~~

Dòng cảnh báo được ghi lên `stderr`, còn hai dòng hiển thị lên `stdout`. Khi công cụ chạy gộp hai luồng này, cách hiển thị các dòng có thể phụ thuộc môi trường; nội dung và quyết định dùng Light vẫn như trên.

**Trường hợp 4 — `drak fallbak`:**

~~~text
[ERROR] Chính sách không hợp lệ; chọn 'strict' hoặc 'fallback'.
~~~

Trường hợp này vẫn kết thúc với mã thoát **2**, vì không thể chọn cách xử lý lỗi dựa trên một chính sách cũng đã bị cấu hình sai.

### 5.2. Bảng kiểm tra hành vi của bộ phân giải

Giả sử biến môi trường `APP_THEME` không được thiết lập khi chạy các lệnh có tham số:

| Lệnh hoặc đầu vào | Chính sách | Kết quả mong đợi |
| --- | --- | --- |
| `java VariantSelectionDemo light` | Strict (mặc định) | Light Button + Light Dialog |
| `java VariantSelectionDemo DARK` | Strict (mặc định) | Dark Button + Dark Dialog |
| `java VariantSelectionDemo drak` | Strict (mặc định) | Báo lỗi; mã thoát 2 |
| `java VariantSelectionDemo drak fallback` | Fallback | Cảnh báo; dùng họ Light |
| `java VariantSelectionDemo drak strict` | Strict | Báo lỗi; mã thoát 2 |
| `java VariantSelectionDemo drak fallbak` | Chính sách sai | Báo lỗi; mã thoát 2 |
| Không có đối số và không có `APP_THEME` | Strict (mặc định) | Họ Light theo quy tắc «thiếu tùy chọn» |
| `APP_THEME=dark`, không có đối số | Strict (mặc định) | Họ Dark |
| Đối số chủ đề rỗng nhưng `APP_THEME=dark` | Strict (mặc định) | Báo lỗi: đối số có mặt được ưu tiên, không tự bỏ qua để đọc ENV |

Bảng này là **kết quả thiết kế cần kiểm tra**, không thay thế việc chạy kiểm thử tự động trong dự án thật.

### 5.3. Vì sao ví dụ tách ThemeResolver và GUIFactorySelector?

`ThemeResolver` xử lý **chuỗi đầu vào và chính sách**. Nó trả về một `Theme` có kiểu rõ ràng hoặc báo lỗi. `GUIFactorySelector` nhận **Theme hợp lệ** và tạo concrete factory tương ứng.

Thiết kế này có ba ưu điểm:

- Không cần lặp việc so sánh chuỗi ở nhiều nơi.
- Có thể kiểm thử riêng các trường hợp giá trị thiếu, rỗng, sai, hợp lệ.
- Client chỉ phụ thuộc vào `GUIFactory`, `Button` và `Dialog`; nó không cần biết cấu hình đến từ CLI hay biến môi trường.

Lưu ý: `GUIFactorySelector` có thể có một `switch`. Abstract Factory **không bắt buộc loại bỏ mọi `switch` khỏi chương trình**. Điều quan trọng là quy tắc chọn họ được tập trung tại một ranh giới rõ ràng.

## 6. Những lỗi xử lý cấu hình thường gặp

### 6.1. Nhầm «khác Dark» thành «chắc chắn Light»

~~~java
// Sai trong trường hợp cấu hình có thể không hợp lệ:
if ("dark".equalsIgnoreCase(raw)) {
    return new DarkGUIFactory();
}
return new LightGUIFactory();
~~~

Mã này không phân biệt `"light"`, `"drak"` và `null`. Nếu `null` được phép dùng mặc định, đó cũng phải là **một nhánh có chủ đích**, còn giá trị không hợp lệ phải đi qua chính sách lỗi.

Cách rõ nghĩa hơn:

~~~java
Theme theme = ThemeResolver.resolve(raw, policy);
GUIFactory factory = GUIFactorySelector.create(theme);
~~~

### 6.2. Tạo sản phẩm trước rồi mới phát hiện cấu hình sai

Ví dụ sau trộn quyết định biến thể vào từng lần tạo:

~~~java
Button button = "dark".equals(raw)
        ? new DarkButton()
        : new LightButton();

// Một nơi khác lại chuẩn hóa hoặc đọc lại cấu hình.
Dialog dialog = "DARK".equals(raw)
        ? new DarkDialog()
        : new LightDialog();
~~~

Với `raw = "dark"`, hai điều kiện cho kết quả **khác nhau**: nút Dark nhưng hộp thoại Light. Đây là vi phạm mục tiêu tạo các sản phẩm cùng họ.

**Cách xử lý:** phân giải cấu hình **một lần**, chọn **một `GUIFactory`**, rồi tạo mọi loại sản phẩm liên quan thông qua factory đó.

### 6.3. Bắt mọi ngoại lệ rồi fallback

~~~java
// Không nên làm:
try {
    return new DarkGUIFactory();
} catch (Exception ex) {
    return new LightGUIFactory();
}
~~~

Đoạn này biến cả lỗi lập trình, lỗi tạo dependency và các sai hỏng bất ngờ thành một lần chuyển sang Light. Ứng dụng có thể tiếp tục trong trạng thái mà người vận hành không hiểu nguyên nhân.

**Cách xử lý:** chỉ áp dụng fallback với **nhóm lỗi cấu hình đã định nghĩa rõ**, ở thời điểm phân giải biến thể. Những lỗi khởi tạo factory hay lỗi thực thi khác nên được báo và xử lý theo cơ chế tương ứng, không tự động coi là lỗi gõ tên chủ đề.

### 6.4. Fallback nhưng không ghi nhận sự kiện

~~~java
// Gây khó điều tra vì cấu hình sai bị che giấu.
return DEFAULT_THEME;
~~~

Nếu có giá trị sai và hệ thống đã đồng ý fallback, nên phát cảnh báo có ích: tên khóa cấu hình, loại lỗi, mặc định được chọn và cách sửa. Ở ứng dụng sản xuất có hệ thống giám sát, có thể thêm **metric** đếm lần fallback theo nguyên nhân (nhưng không gắn nhãn bằng giá trị cấu hình tùy ý gây cardinality cao).

Không nên log mật khẩu, token hay giá trị nhạy cảm nguyên văn chỉ để chẩn đoán. Ví dụ Java ghi tên khóa và các giá trị hợp lệ, tránh in trực tiếp chuỗi đầu vào không tin cậy.

### 6.5. Không công bố thứ tự ưu tiên nguồn cấu hình

Giả sử cả tham số lệnh và biến môi trường đều có giá trị. Ứng dụng cần quy định rõ nguồn nào ưu tiên.

Ví dụ hiện tại áp dụng:

~~~text
Đối số thứ nhất (nếu có) → APP_THEME → Light mặc định (nếu cả hai đều thiếu)
~~~

**Đối số rỗng vẫn là «đã được cung cấp»**, do đó phải kiểm tra giá trị rỗng, không tự chuyển sang đọc `APP_THEME`. Nếu hệ thống muốn bỏ qua giá trị rỗng và dùng nguồn thấp hơn, đó phải là một chính sách riêng được công bố và kiểm tra.

Nếu việc hai nguồn cấu hình mâu thuẫn được xem là lỗi trong sản phẩm cụ thể, cần thêm bước phát hiện xung đột trước khi chọn factory; quy tắc đó phụ thuộc vào yêu cầu vận hành.

## 7. Cách quyết định fail fast hay fallback trong hệ thống thật

Không có một chính sách phù hợp với mọi biến thể. Có thể đánh giá theo các tiêu chí:

| Tiêu chí | Nghiêng về fail fast | Nghiêng về fallback có cảnh báo |
| --- | --- | --- |
| **Mức độ quan trọng** | Liên quan tiền, dữ liệu, bảo mật, giao thức | Chủ yếu tác động cách hiển thị |
| **An toàn của mặc định** | Không có mặc định được bảo đảm | Có một biến thể mặc định đã được xác nhận |
| **Hậu quả chọn sai họ** | Có thể sinh dữ liệu không tương thích hoặc hành vi sai | Giao diện vẫn dùng được, chỉ khác sở thích |
| **Khả năng khôi phục** | Cần người vận hành sửa cấu hình | Có thể tiếp tục hoạt động rồi sửa sau |
| **Nhu cầu quan sát** | Cần lỗi rõ ràng và mã thoát khác 0 | Cần cảnh báo/metric để không che giấu sai cấu hình |
| **Hợp đồng triển khai** | Bắt buộc đúng biến thể đã khai báo | Cho phép sử dụng biến thể thay thế khi cần |

Có thể phân chính sách theo từng loại đầu vào thay vì dùng một quy tắc duy nhất cho mọi lỗi:

- **Thiếu tùy chọn:** dùng default khi tài liệu cấu hình quy định như vậy.
- **Rỗng/sai định dạng/không hỗ trợ:** fail fast hoặc fallback có chủ đích.
- **Thiếu trường bắt buộc:** fail fast.
- **Thiếu triển khai factory hoặc lỗi dependency:** báo lỗi khởi tạo; không được tự động đánh đồng với tên biến thể sai.
- **Chính sách fallback sai:** fail fast để tránh việc hệ thống tự quyết định một chế độ không được yêu cầu.

Một số hệ thống có thể thay đổi chính sách theo môi trường triển khai, ví dụ nghiêm ngặt trong CI và fallback ở một ứng dụng desktop. Nhưng cấu hình quyết định chính sách cũng cần **được kiểm tra nghiêm ngặt**; nếu không, hệ thống sẽ không biết mình đang hoạt động theo quy tắc nào.

## 8. Khi cấu hình có thể thay đổi trong lúc ứng dụng chạy

Ví dụ trên đọc cấu hình tại lúc khởi động. Nhiều hệ thống cho phép đổi theme khi ứng dụng đang chạy; điều đó đặt ra hai vấn đề bổ sung:

1. **Đọc snapshot nhất quán:** chọn biến thể từ một bộ dữ liệu cấu hình nhất quán, tránh mỗi thành phần đọc một giá trị ở thời điểm khác nhau.
2. **Vòng đời sản phẩm:** thay factory chỉ ảnh hưởng **các lần tạo sản phẩm mới**. Những nút và hộp thoại đã tồn tại không tự biến từ Light sang Dark.

Một luồng cập nhật an toàn về mặt thiết kế có thể là:

~~~text
Cấu hình mới đến
→ Kiểm tra tính hợp lệ / áp dụng chính sách
→ Tạo factory mới nếu hợp lệ
→ Tạo lại bộ thành phần liên quan hoặc áp dụng cơ chế đổi theme đã thiết kế
→ Chuyển giao diện sang bộ mới
~~~

Nếu cấu hình mới không hợp lệ, ứng dụng có thể **giữ nguyên theme đang chạy** thay vì dùng mặc định, nếu đó là chính sách chuyển đổi runtime đã công bố. Đây là một lựa chọn khác với fallback ở thời điểm khởi động: việc **giữ trạng thái cũ** đôi khi an toàn hơn đột ngột đổi sang Light.

Đối với giao diện thực như Swing/JavaFX, việc cập nhật thành phần phải tuân theo mô hình sự kiện và luồng GUI của framework. Abstract Factory chỉ tổ chức cách tạo họ sản phẩm, không tự thực hiện việc chuyển giao diện.

## 9. Kịch bản kiểm tra nên có

Trước khi đưa bộ chọn biến thể vào ứng dụng, nên kiểm tra các nhánh quyết định chính thay vì chỉ thử hai tên hợp lệ.

| Nhóm kiểm tra | Ví dụ | Điều cần xác minh |
| --- | --- | --- |
| Giá trị hợp lệ | `light`, `dark` | Chọn đúng factory và đúng cả họ sản phẩm |
| Chuẩn hóa | `" DARK "` | Chọn Dark; không coi là lỗi |
| Không có cấu hình tùy chọn | `null` | Dùng Light mặc định theo hợp đồng |
| Giá trị rỗng | `""`, `"   "` | Được nhận là sai, xử lý đúng policy |
| Sai chính tả | `drak` | Strict báo lỗi; fallback cảnh báo rồi dùng Light |
| Giá trị lạ | `blue` | Không tự đoán thành Dark/Light |
| Policy sai | `fallbak` | Luôn báo lỗi, không âm thầm dùng policy khác |
| Factory chưa được đăng ký | Enum có giá trị mới nhưng selector chưa xử lý | Báo lỗi thiếu factory, không tự đổi họ |
| Đồng bộ sản phẩm | Cùng một `GUIFactory` tạo Button và Dialog | Cả hai thuộc cùng biến thể |
| Cảnh báo | Fallback xảy ra | Cảnh báo mô tả nguyên nhân, có giá trị sửa lỗi |
| Nhiều nguồn cấu hình | CLI khác ENV | Tôn trọng thứ tự ưu tiên đã công bố |

Với test tự động, có thể kiểm thử `ThemeResolver.resolve()` bằng các ca đầu vào độc lập và kiểm thử `GUIFactorySelector.create()` theo enum. Với test tích hợp, cần kiểm tra mã thoát khi lỗi, cơ chế log và **toàn bộ họ sản phẩm** được tạo đúng. Nếu sản phẩm giao tiếp với hệ thống bên ngoài, cần thêm kiểm tra thực tế về khả năng tương thích chứ không chỉ so sánh tên lớp.

## 10. Những câu hỏi tự kiểm tra

**Câu 1.** Vì sao cách viết `"dark".equalsIgnoreCase(raw) ? darkFactory : lightFactory` có thể nguy hiểm?

**Trả lời:** Mọi giá trị không bằng `dark`, kể cả `drak` hay giá trị sai định dạng, đều âm thầm chọn Light. Nó không phân biệt cấu hình hợp lệ với lỗi cần được xử lý.

**Câu 2.** Cấu hình `APP_THEME` hoàn toàn không tồn tại và cấu hình `APP_THEME=""` có bắt buộc được xử lý giống nhau không?

**Trả lời:** Không. Trong ví dụ, `null` là «không chọn» nên dùng mặc định; chuỗi rỗng là một giá trị đã được cung cấp nhưng sai. Sản phẩm có thể quy định khác, song cần nhất quán và rõ ràng.

**Câu 3.** Khi nào fallback sang Light là hợp lý?

**Trả lời:** Khi Light là biến thể thay thế an toàn, rủi ro khi chọn Light được chấp nhận và chính sách có cảnh báo/giám sát. Không nên tự động fallback cho cấu hình nghiệp vụ hoặc bảo mật quan trọng.

**Câu 4.** Vì sao không để từng `Button` và `Dialog` tự đọc `APP_THEME`?

**Trả lời:** Chúng có thể đọc giá trị khác nhau hoặc triển khai cách kiểm tra khác nhau, dẫn đến sản phẩm khác họ. Cần phân giải cấu hình một lần và tạo các sản phẩm thông qua một factory được chọn thống nhất.

**Câu 5.** Nếu `GUIFactorySelector.create()` gặp enum mới chưa có factory, có nên bắt mọi ngoại lệ rồi trả `LightGUIFactory` không?

**Trả lời:** Không. Đây là lỗi đăng ký/triển khai factory, khác với người dùng nhập sai tên theme. Nó cần được phát hiện và xử lý rõ ràng, tránh che giấu bug.

**Câu 6.** Khi người dùng đổi giao diện đang chạy từ Light sang Dark, chỉ đổi biến `factory` là đủ chưa?

**Trả lời:** Chưa. Factory mới quyết định các instance được tạo tiếp theo. Giao diện đang có cần được tái tạo hoặc cập nhật theo một cơ chế riêng; cấu hình mới cũng phải được kiểm tra trước khi áp dụng.

## 11. Ghi nhớ

Trong **Abstract Factory**, chọn biến thể là quyết định có ảnh hưởng tới **cả họ sản phẩm**. Vì vậy, cần **kiểm tra cấu hình trước, tạo factory sau**, rồi để client lấy các sản phẩm liên quan từ factory ấy.

Hãy phân biệt **thiếu giá trị**, **giá trị rỗng**, **giá trị không được hỗ trợ** và **factory không khả dụng**. Với cấu hình sai, **fail fast** giúp lỗi được phát hiện rõ; **fallback có cảnh báo** phù hợp khi tồn tại mặc định an toàn và ứng dụng được phép tiếp tục. Điều quan trọng là chính sách được xác định tường minh và có thể kiểm chứng, để ứng dụng không âm thầm chạy với một họ sản phẩm khác ý định cấu hình.
