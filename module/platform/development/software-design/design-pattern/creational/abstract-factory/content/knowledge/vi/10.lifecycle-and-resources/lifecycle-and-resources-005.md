# Đánh giá tính an toàn luồng của factory không trạng thái và factory có cache

## 1. Bài toán: một factory được nhiều luồng sử dụng

Trong **Abstract Factory** thuộc nhóm *Creational Design Patterns*, client yêu cầu nhiều loại sản phẩm liên quan thông qua một factory chung. Ví dụ, ứng dụng giao diện Light cần một cặp `Button` và `Checkbox` có cùng phong cách hiển thị. Trong ứng dụng máy chủ, nhiều request có thể đồng thời gọi một factory được chia sẻ để tạo các sản phẩm này.

Giả sử một `LightGUIFactory` được sử dụng bởi tám luồng. Chúng cùng yêu cầu thông tin giao diện theo ngôn ngữ `vi` và sau đó tạo nút, ô chọn. Ban đầu factory có thể chỉ gọi `new`. Sau một thời gian, lập trình viên thêm cache để tránh nạp lại bộ thông số giao diện nhiều lần. **Thay đổi tưởng như chỉ nhằm tối ưu hiệu năng có thể làm thay đổi tính an toàn luồng của factory.**

Bài này tập trung trả lời bốn câu hỏi:

1. Khi nào **factory không trạng thái** có thể dùng chung an toàn giữa nhiều luồng?
2. Vì sao đưa `HashMap` làm cache vào factory có thể gây race condition dù `HashMap` được khai báo `final`?
3. Dùng `ConcurrentHashMap` và dữ liệu bất biến như thế nào để vừa chia sẻ cache vừa tránh chia sẻ trạng thái UI giữa các request?
4. Khi cache có giới hạn bộ nhớ, thời hạn sử dụng hoặc tài nguyên cần đóng, ai chịu trách nhiệm với vòng đời của chúng?

**Phạm vi mô phỏng:** Ví dụ Java bên dưới dùng chuỗi ký tự làm kết quả hiển thị để tập trung vào đồng thời và vòng đời. Nó không tạo cửa sổ Swing/JavaFX thật. Các nguyên tắc kiểm tra trạng thái dùng chung vẫn áp dụng khi concrete product là đối tượng GUI, bộ mã hóa, trình kết xuất hay adapter I/O.

## 2. Phân biệt ba đối tượng cần đánh giá

Không nên gộp câu hỏi “factory có an toàn luồng không?” với câu hỏi “mọi product do factory trả về đều an toàn luồng không?”.

| Đối tượng | Chứa hoặc chia sẻ gì? | Rủi ro điển hình |
| --- | --- | --- |
| **Factory** | Phương thức tạo `Button`, `Checkbox`; có thể có cache hoặc collaborator dùng chung. | Hai luồng cập nhật cùng trạng thái cache không đồng bộ. |
| **Dữ liệu trong cache** | Bộ thông số giao diện, tài nguyên tải sẵn, instance product. | Bị sửa đồng thời, quan sát giá trị thiếu nhất quán, bị đóng khi còn người sử dụng. |
| **Product** | Thông số hiển thị, trạng thái chọn, thông tin theo phiên hoặc request. | Product có trạng thái bị dùng chung và ghi đè giữa các luồng. |

Về vai trò mẫu thiết kế:

- `GUIFactory` là **Abstract Factory**, khai báo `createButton()` và `createCheckbox()`.
- `LightGUIFactory` là **Concrete Factory**, cung cấp cả hai product thuộc họ Light.
- `Button` và `Checkbox` là **Abstract Product**; `LightButton` và `LightCheckbox` là **Concrete Product**.
- `SettingsPanel` là **Client**, sử dụng hai product qua interface.

Trách nhiệm bảo đảm **cùng họ sản phẩm** của Abstract Factory và trách nhiệm bảo đảm **an toàn truy cập đồng thời** là hai yêu cầu song song. Một factory có thể cấp đúng Light theme nhưng vẫn bị lỗi tranh chấp cache. Ngược lại, một cache an toàn luồng cũng không tự ngăn factory trả về nút Light và checkbox Dark.

## 3. Mô hình factory không trạng thái

Factory **không trạng thái** (*stateless factory*) thường không giữ biến instance có thể thay đổi sau khi khởi tạo. Trong phương thức tạo sản phẩm, nó dùng dữ liệu tham số và biến cục bộ rồi trả đối tượng mới:

```java
final class StatelessLightGUIFactory implements GUIFactory {
    @Override
    public Button createButton(String locale) {
        LightTokens tokens = LightTokensLoader.load(locale);
        return new LightButton(tokens);
    }

    @Override
    public Checkbox createCheckbox(String locale) {
        LightTokens tokens = LightTokensLoader.load(locale);
        return new LightCheckbox(tokens);
    }
}
```

Hai lời gọi đồng thời có các biến cục bộ `tokens` riêng. Factory không sửa trạng thái dùng chung nên **bản thân phần logic này không tạo ra data race**. Nhưng kết luận “stateless luôn thread-safe” là quá rộng. Vẫn phải kiểm tra:

- `LightTokensLoader.load(...)` có dùng biến static mutable, bộ đệm không đồng bộ hoặc thư viện không an toàn luồng không?
- Factory có được công bố (*safely published*) cho các luồng sau khi hoàn tất khởi tạo không, và có để `this` thoát khỏi constructor quá sớm không?
- Product mới trả về có bị client chia sẻ cho nhiều luồng hay chứa tham chiếu tới dữ liệu mutable dùng chung không?
- Nguồn dữ liệu ở ngoài, chẳng hạn cấu hình đang được thay đổi, có được đọc bằng cơ chế nhất quán phù hợp không?

**Kết luận có điều kiện:** Factory không trạng thái dễ dùng chung an toàn khi đường đi tạo product không truy cập trạng thái mutable không được bảo vệ, dữ liệu được công bố đúng cách và các product/collaborator tuân thủ hợp đồng đồng thời của chúng.

## 4. Thêm cache sẽ thay đổi bản chất việc chia sẻ

Một tối ưu hóa thường gặp là cache bộ thông số Light theo mã ngôn ngữ để khỏi dựng lại nhiều lần. Cách viết sau **không an toàn** nếu nhiều luồng dùng chung instance factory:

```java
// Ví dụ minh họa lỗi: các kiểu GUIFactory, LightTokens, LightTokensLoader
// được định nghĩa ở mục 5 bên dưới.
import java.util.HashMap;
import java.util.Map;

final class UnsafeCachedLightGUIFactory implements GUIFactory {
    private final Map<String, LightTokens> cache = new HashMap<>();

    private LightTokens tokens(String locale) {
        String key = LightTokensLoader.normalize(locale);
        return cache.computeIfAbsent(
                key, LightTokensLoader::loadNormalized);
    }

    @Override
    public Button createButton(String locale) {
        return new LightButton(tokens(locale));
    }

    @Override
    public Checkbox createCheckbox(String locale) {
        return new LightCheckbox(tokens(locale));
    }
}
```

`HashMap` và việc thực hiện `computeIfAbsent` trên `HashMap` **không có bảo đảm an toàn luồng**. Khi hai luồng cùng thấy một key chưa tồn tại, chúng có thể đồng thời tạo giá trị và thay đổi cấu trúc map. Kết quả có thể là tính toán lặp, mất cập nhật, trạng thái quan sát không nhất quán hoặc các lỗi đồng thời khác; việc chương trình đôi khi vẫn chạy bình thường không chứng minh thiết kế đúng.

Từ khóa `final` chỉ ngăn **gán lại tham chiếu** `cache` sau khi khởi tạo; nó không biến nội dung `HashMap` thành bất biến và cũng không khóa các thao tác đọc/ghi. Tương tự, đặt `volatile` lên tham chiếu map không làm cho các thao tác phức hợp trên `HashMap` trở nên atomic.

Trong ví dụ này, `LightTokens` nên là đối tượng bất biến, nhưng **giá trị bất biến không tự khiến cấu trúc cache mutable trở thành an toàn luồng**. Cả hai lớp trách nhiệm đều cần được xét riêng.

## 5. Hiện thực hoàn chỉnh: stateless và cached factory

Đoạn dưới đây có thể lưu thành **`Main.java`** và chạy bằng **JDK 17+**. Nó so sánh:

1. `StatelessLightGUIFactory`: tạo một bộ `LightTokens` mỗi lần client yêu cầu product.
2. `CachedLightGUIFactory`: chia sẻ các `LightTokens` bất biến qua `ConcurrentHashMap`.

Cả hai đều thực hiện cùng hợp đồng `GUIFactory` và **tạo product mới** mỗi lần gọi. Cache chỉ chứa thông số giao diện dùng chung, không chứa trạng thái chọn checkbox của người dùng.

```java
// Main.java — Java 17+
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

// Abstract Products.
interface Button {
    String render(String caption);
}

interface Checkbox {
    String render(String caption, boolean checked);
}

// Abstract Factory: cung cấp một bộ GUI cùng Light theme, theo locale.
interface GUIFactory {
    Button createButton(String locale);
    Checkbox createCheckbox(String locale);
}

// Dữ liệu immutable: các thành phần chỉ giữ tham chiếu đến tokens.
record LightTokens(String locale, String background, String foreground) {
    LightTokens {
        Objects.requireNonNull(locale, "locale");
        Objects.requireNonNull(background, "background");
        Objects.requireNonNull(foreground, "foreground");
    }
}

// Nguồn tạo tokens thuần, không truy cập biến mutable dùng chung.
final class LightTokensLoader {
    private LightTokensLoader() {}

    static String normalize(String locale) {
        String key = Objects.requireNonNull(locale, "locale")
                .trim().toLowerCase(Locale.ROOT);
        if (!key.equals("vi") && !key.equals("en")) {
            throw new IllegalArgumentException("Unsupported locale: " + locale);
        }
        return key;
    }

    static LightTokens loadNormalized(String key) {
        // Trong ứng dụng thật có thể là đọc cấu hình hoặc dựng bảng style.
        return new LightTokens(key, "white", "black");
    }

    static LightTokens load(String locale) {
        return loadNormalized(normalize(locale));
    }
}

// Concrete Products: không có trạng thái mutable.
final class LightButton implements Button {
    private final LightTokens tokens;

    LightButton(LightTokens tokens) {
        this.tokens = Objects.requireNonNull(tokens, "tokens");
    }

    @Override
    public String render(String caption) {
        return "[Light/" + tokens.locale() + " bg=" + tokens.background()
                + "] Button [" + caption + "]";
    }
}

final class LightCheckbox implements Checkbox {
    private final LightTokens tokens;

    LightCheckbox(LightTokens tokens) {
        this.tokens = Objects.requireNonNull(tokens, "tokens");
    }

    @Override
    public String render(String caption, boolean checked) {
        String mark = checked ? "x" : " ";
        return "[Light/" + tokens.locale() + " bg=" + tokens.background()
                + "] Checkbox [" + mark + "] " + caption;
    }
}

// Concrete Factory không trạng thái.
final class StatelessLightGUIFactory implements GUIFactory {
    @Override
    public Button createButton(String locale) {
        return new LightButton(LightTokensLoader.load(locale));
    }

    @Override
    public Checkbox createCheckbox(String locale) {
        return new LightCheckbox(LightTokensLoader.load(locale));
    }
}

// Concrete Factory có cache dùng chung an toàn luồng.
final class CachedLightGUIFactory implements GUIFactory {
    private final ConcurrentMap<String, LightTokens> cache =
            new ConcurrentHashMap<>();

    private LightTokens tokens(String locale) {
        String key = LightTokensLoader.normalize(locale);
        return cache.computeIfAbsent(
                key, LightTokensLoader::loadNormalized);
    }

    @Override
    public Button createButton(String locale) {
        return new LightButton(tokens(locale));
    }

    @Override
    public Checkbox createCheckbox(String locale) {
        return new LightCheckbox(tokens(locale));
    }

    int cacheEntries() {
        return cache.size();
    }
}

// Client: giữ hai product được cấp từ cùng factory và cùng locale.
final class SettingsPanel {
    private final Button button;
    private final Checkbox checkbox;

    SettingsPanel(GUIFactory factory, String locale) {
        Objects.requireNonNull(factory, "factory");
        button = factory.createButton(locale);
        checkbox = factory.createCheckbox(locale);
    }

    String preview() {
        return button.render("Save") + "\n"
                + checkbox.render("Auto-save", true);
    }
}

public class Main {
    private static final String EXPECTED =
            "[Light/vi bg=white] Button [Save]\n"
            + "[Light/vi bg=white] Checkbox [x] Auto-save";

    public static void main(String[] args) throws Exception {
        GUIFactory stateless = new StatelessLightGUIFactory();
        CachedLightGUIFactory cached = new CachedLightGUIFactory();

        System.out.println(new SettingsPanel(stateless, "vi").preview());
        checkConcurrentCalls(stateless);
        checkConcurrentCalls(cached);

        if (cached.cacheEntries() != 1) {
            throw new AssertionError("Expected exactly one cached locale");
        }
        System.out.println("Concurrent checks: PASS");
        System.out.println("Cached locales: " + cached.cacheEntries());
    }

    // Một phép thử đồng thời nhỏ, không thay thế kiểm thử stress chuyên sâu.
    private static void checkConcurrentCalls(GUIFactory factory)
            throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(8);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<String>> results = new ArrayList<>();

        try {
            for (int i = 0; i < 24; i++) {
                results.add(pool.submit(() -> {
                    start.await();
                    return new SettingsPanel(factory, "VI").preview();
                }));
            }

            start.countDown();
            for (Future<String> result : results) {
                String actual = result.get();
                if (!EXPECTED.equals(actual)) {
                    throw new AssertionError("Unexpected output: " + actual);
                }
            }
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }
}
```

### Chạy và quan sát

Từ thư mục chứa `Main.java`:

```bash
javac Main.java
java Main
```

Kết quả mong đợi:

```text
[Light/vi bg=white] Button [Save]
[Light/vi bg=white] Checkbox [x] Auto-save
Concurrent checks: PASS
Cached locales: 1
```

Kiểm tra chạy 24 tác vụ trên pool tám luồng đối với mỗi factory. Tất cả tác vụ đều tạo cặp product Light cho ngôn ngữ `vi` (dữ liệu đầu vào `VI` được chuẩn hóa thành `vi`). Với factory có cache, chỉ có **một key** `vi` tồn tại sau các lời gọi nên `cacheEntries() == 1`.

**Giới hạn của phép thử:** Test đồng thời có thể phát hiện lỗi nhưng **không chứng minh** một implementation an toàn trong mọi lịch xen kẽ luồng. Cơ sở để đánh giá an toàn nằm ở cấu trúc dữ liệu, thao tác truy cập, tính bất biến của giá trị và các quy tắc *happens-before* trong Java; chạy thử chỉ bổ sung bằng chứng thực nghiệm. Không nên dùng kết quả “PASS” để hợp thức hóa một `HashMap` bị chia sẻ mà không đồng bộ.

## 6. Vì sao bản cached factory an toàn hơn?

Trong `CachedLightGUIFactory`, cache dùng:

```java
private final ConcurrentMap<String, LightTokens> cache =
        new ConcurrentHashMap<>();

private LightTokens tokens(String locale) {
    String key = LightTokensLoader.normalize(locale);
    return cache.computeIfAbsent(
            key, LightTokensLoader::loadNormalized);
}
```

Có bốn điểm cần đánh giá:

1. **Cấu trúc dữ liệu:** `ConcurrentHashMap` hỗ trợ truy cập đồng thời; `computeIfAbsent` thực hiện thao tác xác định hoặc thêm ánh xạ theo key một cách atomic theo hợp đồng của nó. Các thread không tự cập nhật một `HashMap` thông thường.
2. **Giá trị được chia sẻ:** `LightTokens` là `record` chỉ chứa `String` bất biến, không giữ một `List` mutable hoặc tham chiếu có thể bị sửa qua nơi khác. Các product chỉ đọc tokens.
3. **Product mới cho mỗi lời gọi:** Factory có thể chia sẻ tokens nhưng vẫn tạo `new LightButton(...)` và `new LightCheckbox(...)`. Trạng thái dành riêng cho từng màn hình, nếu được bổ sung về sau, không bị dùng chung chỉ vì có cache.
4. **Công bố đối tượng:** Factory và cache được tạo xong trước khi các tác vụ dùng chung; trong ví dụ, việc gửi công việc cho `ExecutorService` và các primitive đồng bộ bảo đảm chuyển giao tham chiếu theo cơ chế đồng thời của Java. Không công bố một factory chưa khởi tạo xong.

Với một key đang vắng mặt, `ConcurrentHashMap.computeIfAbsent` phối hợp phép tính theo key để các lời gọi cạnh tranh không tự ghi đè cache không an toàn. Tuy nhiên, **không nên suy rộng thành “loader chắc chắn chỉ được gọi đúng một lần trong mọi hoàn cảnh”**: key có thể bị xóa hoặc bị hủy cache; hàm tạo có thể ném exception hay trả `null`; các yêu cầu sau đó có thể phải tính lại. `ConcurrentHashMap` không lưu giá trị `null`.

Hàm dùng trong `computeIfAbsent` nên ngắn, rõ ràng, không sửa lại chính map theo cách đệ quy. Nếu quá trình dựng giá trị cần I/O chậm, tải nhiều tài nguyên hoặc có thể thất bại, hãy đánh giá việc chờ của các luồng cùng key, chính sách retry, timeout và có nên dùng một cấu trúc cache chuyên dụng.

### Khi chỉ cần khóa thay cho concurrent map

Có thể giữ `HashMap` nếu **mọi đường truy cập** được bảo vệ bằng cùng một cơ chế đồng bộ:

```java
private final Map<String, LightTokens> cache = new HashMap<>();

private synchronized LightTokens tokens(String locale) {
    String key = LightTokensLoader.normalize(locale);
    return cache.computeIfAbsent(
            key, LightTokensLoader::loadNormalized);
}
```

Đây là **phương án thay thế** cho phần cache, không phải đoạn cần ghép đồng thời với `ConcurrentHashMap` ở ví dụ đầy đủ. Vì khóa `this` bảo vệ toàn bộ phương thức, hai luồng không cùng thao tác trên `HashMap` qua phương thức đó. Tuy nhiên, tính an toàn chỉ còn đúng nếu **không có đường đọc/ghi cache khác bỏ qua khóa**; khóa toàn bộ phương thức cũng làm các key độc lập phải chờ nhau và có thể thành nút thắt hiệu năng.

## 7. Cache product mutable: lỗi dù map đã an toàn

Một hiểu nhầm khác là: “Chỉ cần chuyển `HashMap` sang `ConcurrentHashMap` thì sản phẩm trả về cũng an toàn luồng”. Concurrent map bảo vệ **thao tác trên map**, không tự bảo vệ trạng thái của **object value**.

Ví dụ product có trạng thái checkbox dùng chung:

```java
// Ví dụ phản diện: mutable product, không dùng trong chương trình mục 5.
final class MutableCheckbox {
    private boolean checked;

    String render(boolean nextChecked) {
        checked = nextChecked;
        return checked ? "[x]" : "[ ]";
    }
}

// Nguy hiểm nếu client A và B cùng nhận một instance từ cache:
// Thread A: checkbox.render(true)
// Thread B: checkbox.render(false)
```

Hai lời gọi có thể xen kẽ giữa bước gán `checked` và bước đọc lại trường. Thread A yêu cầu `true` nhưng có thể nhận `[ ]` sau khi thread B ghi `false`. Đặt object này làm **value trong `ConcurrentHashMap`** không loại bỏ data race bên trong `MutableCheckbox`.

Trong bài toán UI, trạng thái “đang được chọn” thường thuộc từng thành phần hoặc từng phiên, không nên cache và chia sẻ toàn cục một instance mutable như vậy. Hướng xử lý thường là:

- **Cache dữ liệu bất biến** dùng chung, chẳng hạn `LightTokens`, bộ định dạng không trạng thái hoặc metadata đã chuẩn hóa.
- **Tạo product mới** cho client có trạng thái riêng; truyền tokens bất biến vào constructor.
- Nếu thật sự phải chia sẻ một product có trạng thái, thiết kế rõ quyền sở hữu, đồng bộ hóa thao tác trên product hoặc dùng cấu trúc đồng thời phù hợp; kiểm tra lại việc chia sẻ đó có đúng yêu cầu nghiệp vụ không.

Không nên áp dụng `synchronized` một cách máy móc lên toàn bộ product nếu bản chất mỗi client cần trạng thái riêng: khóa giúp tránh race ở một số thao tác nhưng **không sửa được lỗi nhiều client vô tình dùng chung trạng thái**.

## 8. Tính nhất quán của cặp product khi cấu hình thay đổi

Trong `SettingsPanel`, cả `Button` và `Checkbox` được tạo bằng cùng một `GUIFactory` và mã ngôn ngữ. Khi cache chỉ thêm giá trị và tokens là bất biến, hai product dùng bộ thông số Light tương ứng với key đó.

Nhưng nếu hệ thống có tính năng **reload theme theo thời gian thực**, cần xét tình huống:

1. Thread A lấy tokens phiên bản 1 để tạo `Button`.
2. Thread B cập nhật hoặc thay cache bằng tokens phiên bản 2.
3. Thread A lấy tokens phiên bản 2 để tạo `Checkbox`.

Cả hai product có thể vẫn là Light, nhưng chúng dùng hai **phiên bản cấu hình** khác nhau. Cache an toàn luồng ở cấp map **không đủ để bảo đảm tính nhất quán nhiều phép đọc qua thời gian**.

Nếu nghiệp vụ cần hai thành phần sử dụng **chính xác cùng một snapshot**, có thể:

- Lấy một `LightTokens` **duy nhất** trước khi tạo cả hai product và truyền nó tới cả hai.
- Hoặc cung cấp một phương thức tạo **bộ sản phẩm** `createFamily(locale)` trả một object bất biến giữ cả `Button` lẫn `Checkbox` từ cùng một phiên bản tokens.
- Khi reload, thay **nguyên snapshot bất biến** bằng cơ chế công bố an toàn, thay vì sửa từng thuộc tính bên trong object dùng chung.

Ví dụ ý tưởng:

```java
// Trích đoạn thiết kế thay thế; không thuộc Main.java ở mục 5.
record GuiPair(Button button, Checkbox checkbox) {}

// Một phương thức trong factory có thể giữ cùng một snapshot:
GuiPair createPair(String locale) {
    LightTokens snapshot = tokens(locale);
    return new GuiPair(
            new LightButton(snapshot),
            new LightCheckbox(snapshot));
}
```

Hợp đồng tạo cả cặp không phải yêu cầu bắt buộc của mọi Abstract Factory; nó là một lựa chọn bổ sung khi **tính nhất quán theo thời điểm** thực sự quan trọng. Phải phân biệt quy tắc “cùng họ Light” với quy tắc mạnh hơn “cùng phiên bản cấu hình Light”.

## 9. Chi phí hiệu năng, bộ nhớ và vòng đời cache

Thêm cache có thể giảm công việc lặp lại nhưng cũng tạo **trạng thái tồn tại lâu hơn mỗi lời gọi**. Trước khi cache product hoặc metadata, cần cân nhắc:

| Yếu tố | Factory không trạng thái | Factory có cache |
| --- | --- | --- |
| Tạo đối tượng | Có thể tính/dựng lại thông số mỗi lần gọi. | Tái sử dụng giá trị đã có theo key. |
| Bộ nhớ dài hạn | Ít giữ dữ liệu giữa các lời gọi. | Giữ tham chiếu theo số key, có thể tăng không giới hạn nếu key không giới hạn. |
| Tranh chấp luồng | Không có lock nội bộ nếu logic thuần. | Cần concurrent map, lock hoặc cơ chế bất biến/snapshot phù hợp. |
| Dữ liệu cũ | Mỗi lần đọc có thể thấy cấu hình mới tùy nguồn dữ liệu. | Cần chính sách refresh/invalidate khi nguồn cấu hình thay đổi. |
| Kiểm thử | Chủ yếu kiểm tra hợp đồng tạo sản phẩm. | Kiểm tra thêm hit/miss, concurrency, key, refresh và tài nguyên. |
| Vòng đời | Product có thể tồn tại theo client, factory không cần giữ. | Giá trị cache sống theo factory/cache; phải có quy tắc giới hạn và giải phóng khi cần. |

### 9.1. Kích thước và khóa cache

Mẫu trong mục 5 chỉ chấp nhận hai locale `vi` và `en` nên số key có giới hạn nhỏ. Trong ứng dụng thực tế, khóa có thể là mã khách hàng, URL, kích thước ảnh hoặc bộ tham số tùy ý. Lúc đó `ConcurrentHashMap` **không tự đuổi các entry cũ** và cache có thể tăng bộ nhớ lâu dài.

Nên xem xét giới hạn dung lượng, thời gian hết hạn (TTL), chính sách loại bỏ entry hoặc cache library có eviction phù hợp. Một cache có đồng bộ hóa tốt nhưng không có giới hạn vẫn có thể gây thiếu bộ nhớ.

Cũng cần xác định rõ cache key bao gồm đủ những dữ liệu quyết định kết quả. Nếu style thay đổi theo theme, locale và phiên bản cấu hình thì chỉ dùng mỗi locale làm key có thể khiến cache trả lại **giá trị sai ngữ cảnh**.

### 9.2. Cache giữ tài nguyên cần đóng

Với `LightTokens` bất biến chỉ chứa chuỗi, việc loại bỏ khỏi map không có công việc đóng tài nguyên riêng. Nhưng nếu giá trị là kết nối, file handle, font native hay đối tượng chứa `AutoCloseable`, cache hoặc một thành phần sở hữu rõ ràng phải quyết định:

- Ai **tạo** và ai **đóng** tài nguyên?
- Khi entry bị thay thế hoặc xóa, có client nào còn đang dùng tài nguyên cũ không?
- Khi ứng dụng dừng, ai đóng các entry còn sống?
- Khi một thread đang dùng tài nguyên, việc eviction có thể khiến thread khác đóng nó giữa chừng không?

**Không đóng một tài nguyên chỉ vì vừa xóa entry khỏi map nếu vẫn có người dùng giữ tham chiếu tới nó.** Các cơ chế có thể cần đến bao gồm reference counting, lease, lifecycle coordinator hoặc thiết kế product mở/đóng tài nguyên trong phạm vi tác vụ. Việc chọn cơ chế phụ thuộc vào mức độ chia sẻ và hợp đồng sử dụng tài nguyên.

Nếu factory được quản lý bởi DI container, container thường có thể gọi callback hủy của **factory bean** khi đóng context, nhưng nó **không tự suy ra** cách đóng tất cả sản phẩm tạo thủ công bằng `new` và lưu trong map của factory. Cần bổ sung logic cleanup tại chủ sở hữu cache hoặc dùng tài nguyên được container quản lý với vòng đời phù hợp.

## 10. Những dấu hiệu cần xem lại trong code review

| Dấu hiệu | Cần kiểm tra |
| --- | --- |
| `private final HashMap<...> cache` trong một singleton factory | `final` chỉ bảo vệ tham chiếu; mọi access có được đồng bộ không? |
| `cache.computeIfAbsent(...)` trên map thông thường | Có nhiều luồng gọi đồng thời và làm thay đổi map không? |
| `ConcurrentHashMap<K, MutableProduct>` | Product có mutable state bị nhiều client chia sẻ không? |
| `static` mutable field trong loader | Factory tưởng stateless nhưng đường đi tạo product vẫn có state dùng chung không? |
| `ThreadLocal` thay cho cache đồng bộ | Có thật cần dữ liệu riêng từng luồng? Với thread pool, dữ liệu có được dọn dẹp và tránh rò giữa request không? |
| Dùng `volatile Map` để “sửa race” | Các thao tác trên nội dung map vẫn thiếu đồng bộ không? |
| Product giữ kết nối/file handle từ cache | Có chính sách sở hữu, đóng và tránh đóng khi còn đang dùng không? |
| Cache key là một chuỗi tùy ý | Đã chuẩn hóa key và giới hạn số lượng entry chưa? |
| Nút và checkbox lấy tokens bằng hai lần đọc | Có cần **một snapshot** khi cấu hình reload giữa hai lần đọc không? |
| Kiểm thử đồng thời đôi lần đều PASS | Có chứng minh được dựa trên hợp đồng cấu trúc đồng thời và safe publication không? |

## 11. Bài tập tự đánh giá

**Câu 1.** `StatelessLightGUIFactory` có một biến `static HashMap` dùng trong `LightTokensLoader.load()` nhưng không đồng bộ. Có thể gọi factory này là an toàn luồng chỉ vì nó không có trường instance không?

**Gợi ý:** Không. Cần kiểm tra toàn bộ đường đi tạo product, bao gồm trạng thái static và collaborator dùng chung. “Không trạng thái” ở vỏ factory không bảo đảm các thành phần được gọi đều an toàn.

**Câu 2.** Chuyển `HashMap` sang `ConcurrentHashMap`, nhưng cache lưu cùng một `MutableCheckbox` cho mọi request. Đã đủ an toàn chưa?

**Gợi ý:** Chưa. Map an toàn ở cấp truy cập key/value, nhưng dữ liệu mutable bên trong cùng một object có thể bị dùng chéo giữa các luồng. Nên tách cache metadata bất biến khỏi product có trạng thái theo client.

**Câu 3.** Vì sao `private final Map<K,V> cache` không đủ để biến các thao tác `put` và `computeIfAbsent` thành atomic?

**Gợi ý:** `final` ngăn đổi tham chiếu tới map, không thay đổi hợp đồng đồng thời của các thao tác bên trong map. Cần bảo vệ mọi truy cập bằng lock hoặc dùng cấu trúc concurrent phù hợp.

**Câu 4.** Nếu `LightTokensLoader.loadNormalized()` cần truy cập API chậm và có thể ném exception, nên cân nhắc thêm những vấn đề nào?

**Gợi ý:** Thread chờ cùng key, thất bại và retry, timeout, có cần cache kết quả lỗi hay không, giới hạn tải đồng thời, và liệu việc dựng giá trị có nên tách khỏi thao tác atomic ngắn của cache.

**Câu 5.** Khi người dùng chuyển theme trong lúc màn hình đang được dựng, cần bảo đảm điều gì để cặp `Button` và `Checkbox` không dùng hai phiên bản cấu hình?

**Gợi ý:** Một snapshot cấu hình được lấy và chia sẻ cho cả cặp product, hoặc factory cung cấp một thao tác tạo trọn bộ từ cùng snapshot, với cơ chế công bố/cập nhật snapshot an toàn.

### Tổng kết kiến thức cần nắm

Một **factory không trạng thái** thường dễ chia sẻ giữa các luồng nếu toàn bộ đường đi tạo product không chứa trạng thái mutable không được bảo vệ. Một **factory có cache** cần bảo đảm an toàn ở **cả cấu trúc cache, dữ liệu cache và product được trả về**; `ConcurrentHashMap` chỉ giải quyết một phần của bài toán. Quyết định cache còn phải xét tính nhất quán theo phiên bản, chi phí tạo đối tượng, giới hạn bộ nhớ và quyền sở hữu tài nguyên.

Trong Abstract Factory, hãy luôn đánh giá hai yêu cầu độc lập nhưng cùng cần thiết: **factory cung cấp đúng họ sản phẩm** và **factory thực hiện việc cấp sản phẩm an toàn theo mô hình đồng thời/vòng đời của ứng dụng**.
