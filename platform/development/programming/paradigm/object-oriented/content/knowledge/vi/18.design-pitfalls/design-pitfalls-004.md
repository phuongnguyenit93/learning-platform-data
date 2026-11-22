# Kế thừa chỉ để dùng lại vài phương thức: một lỗi thiết kế OOP

> **Bài học:** Không nên tạo quan hệ `extends` giữa hai lớp chỉ vì lớp con muốn dùng lại vài phương thức của lớp cha. Hãy đánh giá quan hệ kiểu, hợp đồng hành vi và những API vô tình bị kế thừa; khi đối tượng chỉ **sử dụng** một khả năng, composition/delegation thường biểu diễn đúng hơn.

## 1. Vì sao quyết định này dễ xảy ra?

Khi học Java, ta thấy một lớp có thể dùng `extends` để kế thừa các phương thức `public` hoặc `protected` có thể truy cập của lớp cha:

~~~java
class TextFormatter {
    public String format(String value) {
        return value.trim();
    }
}

class RegistrationService extends TextFormatter {
    public String register(String username) {
        return format(username);
    }
}
~~~

Mã này có thể biên dịch, nhưng `RegistrationService` trở thành một subtype của `TextFormatter` dù chức năng của dịch vụ đăng ký chỉ **cần dùng** thao tác định dạng. Từ bên ngoài, người ta có thể đối xử với dịch vụ đăng ký như một bộ định dạng:

~~~java
TextFormatter formatter = new RegistrationService();
System.out.println(formatter.format("  An  "));
~~~

Câu lệnh hợp lệ về kiểu nhưng quan hệ nghiệp vụ rất kỳ lạ. Nếu `TextFormatter` được sửa để lưu bộ đệm, hỗ trợ `close()` hay thay đổi thuật toán, `RegistrationService` có thể chịu ảnh hưởng chỉ vì một phương thức tiện dụng.

Lợi ích tiết kiệm một ít mã ban đầu đã tạo ra **quan hệ phụ thuộc dài hạn**.

Đây là một dạng **implementation inheritance for convenience**: dùng kế thừa như đường tắt tái sử dụng code, dù đối tượng con không thực sự đại diện cho một trường hợp của abstraction cha.

## 2. Kế thừa mang ý nghĩa mạnh hơn “dùng được phương thức”

Trong OOP, `B extends A` là một quan hệ kiểu. Nếu Java cho phép coi `B` như `A`, thì code sử dụng `A` được quyền kỳ vọng những cam kết mà `A` công bố.

Ví dụ: khi `EmailNotificationSender` thực sự đáp ứng toàn bộ hợp đồng của `NotificationSender`, một caller chỉ cần biết hợp đồng chung có thể sử dụng nó. Nhưng nếu `InventoryService extends HashMap<String, Integer>` chỉ vì muốn gọi `put()` và `get()`, ta đang tuyên bố dịch vụ tồn kho có thể được sử dụng như **mọi HashMap thông thường**.

Câu hỏi thiết kế nên đặt trước khi dùng `extends`:

- **Quan hệ “là một” (is-a) có thật không?** Mọi `B` có thực sự là một `A` theo domain và hợp đồng đã định nghĩa không?
- **Caller có thể thay thế không?** Bất kỳ nơi nào cần `A` có dùng được `B` mà không phá kỳ vọng đã công bố không?
- **API kế thừa có đúng không?** Có phương thức của `A` mà `B` không nên cho phép không?
- **Có đang dùng lại implementation thay vì abstraction?** Nếu chỉ cần một khả năng nhỏ, sở hữu một collaborator có thể rõ hơn không?
- **Thay đổi sẽ lan tới đâu?** Khi lớp cha thay cấu trúc, constructor hoặc method, lớp con có bị ảnh hưởng ngoài dự kiến không?

Khái niệm **Liskov Substitution Principle (LSP)** liên quan chặt chẽ: subtype phải duy trì những bảo đảm hành vi mà client của supertype có quyền trông đợi. Việc code biên dịch được chưa chứng minh tuân thủ LSP.

Cần phân biệt: kế thừa để chia sẻ implementation **không tự động sai**. Một abstraction nền được thiết kế để kế thừa, có hợp đồng ổn định và các subtype đúng nghĩa có thể dùng chung code rất tốt. Vấn đề là chọn `extends` **chỉ vì vài method có sẵn**, không xem xét toàn bộ hợp đồng.

## 3. Tình huống nguy hiểm: Inventory kế thừa HashMap

Giả sử ta muốn quản lý số lượng hàng tồn, luôn thỏa các bất biến:

1. SKU không rỗng.
2. Số lượng của mỗi SKU không âm.
3. Chỉ tăng kho qua `restock` và giảm kho qua `reserve` sau khi kiểm tra.
4. Khi `reserve` bị từ chối, tồn kho không đổi.

Một cách làm sai là kế thừa một collection mutable chỉ để có các hàm truy cập:

~~~java
import java.util.HashMap;

class UnsafeInventory extends HashMap<String, Integer> {
    public void restock(String sku, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity phải dương");
        }
        merge(sku, quantity, Integer::sum);
    }
}
~~~

Cách gọi này phá được bất biến mà không cần sửa `restock()`:

~~~java
UnsafeInventory inventory = new UnsafeInventory();
inventory.restock("BOOK", 5);

// Các API được kế thừa công khai từ HashMap:
inventory.put("BOOK", -100);
inventory.put(null, null);
inventory.clear();

System.out.println(inventory.get("BOOK")); // null
~~~

`UnsafeInventory` không chỉ kế thừa `get` và `put`; nó còn kế thừa hàng loạt khả năng sửa dữ liệu như `remove`, `replace`, `compute`, `merge`, `putAll`, `clear`, cùng các view collection có thể sửa. Người dùng API có thể đi vòng qua validation và quy tắc nghiệp vụ.

Sơ đồ sự cố:

~~~mermaid
flowchart TD
    Client["Client"] -->|restock hợp lệ| Inventory["UnsafeInventory extends HashMap"]
    Client -->|put / clear / compute| MapMethods["API mutable của HashMap"]
    MapMethods --> Inventory
    Inventory --> Broken["Bất biến tồn kho có thể bị phá"]
~~~

Vấn đề nằm ở **ranh giới cho phép sửa trạng thái**. Ngay cả khi ta override `put()` để kiểm tra, vẫn phải xem xét mọi đường cập nhật khác, cả hành vi kế thừa và các API thêm mới trong tương lai. Đó là chi phí lớn chỉ vì muốn dùng lại vài phương thức của collection.

## 4. Sửa bằng composition: Inventory sở hữu Map

Một đối tượng tồn kho **có một cấu trúc lưu trữ** chứ không cần **là một HashMap**. Dùng một field `private` để giữ Map, rồi công khai những thao tác có ý nghĩa nghiệp vụ.

Dưới đây là file **InheritanceReuseDemo.java**, chạy độc lập trên Java 17 trở lên:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class InheritanceReuseDemo {

    // Inventory không extends HashMap.
    public static final class Inventory {
        private final Map<String, Integer> quantities = new HashMap<>();

        public void restock(String sku, int added) {
            sku = validSku(sku);
            if (added <= 0) {
                throw new IllegalArgumentException(
                        "Số lượng bổ sung phải dương");
            }

            // Từ chối overflow thay vì cho phép số âm do tràn int.
            quantities.merge(sku, added, Math::addExact);
        }

        public boolean reserve(String sku, int requested) {
            sku = validSku(sku);
            if (requested <= 0) {
                throw new IllegalArgumentException(
                        "Số lượng đặt giữ phải dương");
            }

            int available = quantities.getOrDefault(sku, 0);
            if (requested > available) {
                return false; // Không thay đổi state.
            }

            quantities.put(sku, available - requested);
            return true;
        }

        public int available(String sku) {
            return quantities.getOrDefault(validSku(sku), 0);
        }

        // Cho phép đọc một snapshot, không trả Map mutable nội bộ.
        public Map<String, Integer> snapshot() {
            return Map.copyOf(quantities);
        }

        private static String validSku(String sku) {
            if (sku == null || sku.isBlank()) {
                throw new IllegalArgumentException(
                        "SKU không được rỗng");
            }
            return sku.trim();
        }
    }

    public static final class CheckoutService {
        private final Inventory inventory;

        public CheckoutService(Inventory inventory) {
            this.inventory =
                    Objects.requireNonNull(inventory, "inventory");
        }

        public String placeOrder(String sku, int quantity) {
            if (inventory.reserve(sku, quantity)) {
                return "RESERVED " + sku + " x" + quantity;
            }
            return "REJECTED: insufficient stock";
        }
    }

    public static void main(String[] args) {
        Inventory inventory = new Inventory();
        inventory.restock("BOOK", 5);

        CheckoutService checkout = new CheckoutService(inventory);
        System.out.println(checkout.placeOrder("BOOK", 3));
        System.out.println(inventory.available("BOOK"));
        System.out.println(checkout.placeOrder("BOOK", 3));
        System.out.println(inventory.available("BOOK"));

        // Không thể gọi:
        // inventory.put("BOOK", -100);
        // inventory.clear();
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac InheritanceReuseDemo.java
java InheritanceReuseDemo
~~~

Kết quả:

~~~text
RESERVED BOOK x3
2
REJECTED: insufficient stock
2
~~~

**Cơ chế bảo vệ:**

- `Inventory` giữ `Map` dưới dạng `private final`; client không gọi được `put()`, `clear()` hoặc `compute()` trên đối tượng Inventory.
- Các phương thức công khai diễn đạt nghiệp vụ: `restock`, `reserve`, `available`.
- `reserve` kiểm tra trước khi giảm số lượng. Khi thiếu hàng, nó trả `false` và không cập nhật state.
- `Math.addExact` phát hiện overflow trong phép cộng số lượng, tránh một kết quả âm ngoài chủ đích.
- `snapshot()` trả một Map không sửa được qua reference trả về. Vì key và value của ví dụ là `String` và `Integer`, không có phần tử mutable bên trong.
- `CheckoutService` **sử dụng** `Inventory` thông qua dependency đưa vào constructor; không trở thành subtype của Inventory hay Map.

Ví dụ chạy trong **một luồng** để giải thích ranh giới và bất biến. `HashMap` và các thao tác kiểm tra–cập nhật trên không thread-safe nếu có nhiều thread cùng sửa. Với dữ liệu thực ở database, cần kiểm soát transaction, locking hoặc cập nhật có điều kiện để tránh tranh chấp. Composition giải quyết quan hệ kiểu và kiểm soát API, không tự động cung cấp đồng bộ.

### Sơ đồ thiết kế sau khi sửa

~~~mermaid
classDiagram
    class CheckoutService {
        -inventory: Inventory
        +placeOrder(sku, quantity) String
    }
    class Inventory {
        -quantities: Map~String, Integer~
        +restock(sku, added) void
        +reserve(sku, requested) boolean
        +available(sku) int
        +snapshot() Map
    }
    class Map {
        <<interface>>
        +get(key)
        +put(key, value)
        +clear()
    }
    CheckoutService --> Inventory : sử dụng
    Inventory *-- Map : sở hữu nội bộ
~~~

Mã giả theo sơ đồ: một đối tượng CheckoutService có tham chiếu tới Inventory; Inventory giữ một Map ở bên trong. **Interface Map không trở thành API nghiệp vụ công khai của Inventory**.

## 5. Cái giá ẩn của việc kế thừa chỉ để tái sử dụng code

| Rủi ro | Hậu quả cụ thể | Dấu hiệu |
| --- | --- | --- |
| **API bị phình ra** | Subclass công khai những phương thức nó không thực sự muốn cung cấp | Class nghiệp vụ thừa hưởng `clear()`, `putAll()` từ collection |
| **Phá bất biến** | Caller thay đổi state qua một đường không kiểm tra | `put("BOOK", -1)` bỏ qua `restock()` |
| **Sai quan hệ is-a / LSP** | Một dịch vụ bị đối xử như một bộ tiện ích hay container tổng quát | `SomeService extends Formatter` chỉ để lấy `format()` |
| **Phụ thuộc chặt vào lớp cha** | Sửa tên, kiểu trả về, constructor hoặc chi tiết `protected` có thể làm nhiều subclass lỗi | Một thay đổi nhỏ trong base class lan nhiều lớp |
| **Fragile base class** | Thêm phương thức hoặc thay cách base class gọi nội bộ có thể thay đổi hành vi của subclass | Override phụ thuộc vào thứ tự gọi implementation |
| **Khó thay implementation** | Muốn đổi `HashMap` sang cache/database buộc thay cả quan hệ kiểu | Mã nghiệp vụ bị gắn với collection concrete |
| **Hierarchy explosion** | Tổ hợp nhiều khả năng sinh ra nhiều biến thể lớp con | `CachedLoggedValidatedService`… |
| **Test khó cô lập** | Test subtype phải dựng state/cấu hình không liên quan của cha | Subclass chỉ cần hai hàm nhưng phụ thuộc resource cha |
| **Tính truy cập bị hiểu sai** | `protected` bị lạm dụng làm API cho mọi subclass | Field nội bộ bị các subclass sửa tùy ý |

Những điều này là **rủi ro**, không phải tất yếu cho mọi quan hệ kế thừa. Nhưng nếu lợi ích chỉ là “khỏi viết 5 dòng ủy quyền”, lợi ích thường không đủ để bù chi phí ràng buộc.

### Một lỗi còn tinh vi hơn: base class tự gọi phương thức có thể override

Ví dụ:

~~~java
class BaseProcessor {
    public BaseProcessor() {
        initialize(); // Gọi phương thức có thể override.
    }

    protected void initialize() {
        // Mặc định.
    }
}

class CsvProcessor extends BaseProcessor {
    private final String delimiter = ";";

    @Override
    protected void initialize() {
        // Có thể chạy khi field delimiter còn null.
        System.out.println(delimiter.length());
    }
}
~~~

Khi tạo `new CsvProcessor()`, constructor của base class chạy **trước khi các field initializer của subclass hoàn tất**. Lời gọi `initialize()` là virtual dispatch và có thể gọi override ở subclass; ở thời điểm đó `delimiter` vẫn là giá trị mặc định `null`, dẫn đến `NullPointerException`.

Đây là lý do tránh gọi phương thức có thể override từ constructor của superclass. Khi buộc dùng inheritance, cần hiểu rõ lifecycle của object và hợp đồng dành cho subclass; thường dùng phương thức `final`, factory hoặc bước khởi tạo tường minh thay vì gọi hook quá sớm.

## 6. Composition và delegation khác nhau thế nào?

- **Composition:** một object quản lý hoặc sử dụng các đối tượng thành phần để hoàn thành trách nhiệm. Trong ví dụ, `Inventory` sở hữu cấu trúc dữ liệu.
- **Delegation:** một object chuyển một phần công việc cho collaborator. `CheckoutService` gọi `inventory.reserve(...)` thay vì tự sửa kho.

Hai khái niệm thường đi cùng nhau, nhưng không phải từ đồng nghĩa. Một object có thể chứa một dependency mà không ủy quyền nguyên vẹn mọi lời gọi; nó có thể phối hợp nhiều collaborator và thêm điều kiện nghiệp vụ.

Ví dụ nhỏ, một dịch vụ cần chuẩn hóa mã:

~~~java
final class SkuNormalizer {
    String normalize(String sku) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU rỗng");
        }
        return sku.trim().toUpperCase(java.util.Locale.ROOT);
    }
}

final class ImportService {
    private final SkuNormalizer normalizer;

    ImportService(SkuNormalizer normalizer) {
        this.normalizer = java.util.Objects.requireNonNull(normalizer);
    }

    String importSku(String rawSku) {
        String sku = normalizer.normalize(rawSku);
        // Tiếp tục nghiệp vụ import...
        return sku;
    }
}
~~~

`ImportService` **cần** chuẩn hóa mã; nó không cần `extends SkuNormalizer`. Bằng composition, `SkuNormalizer` có thể được tái sử dụng ở nhiều nơi mà không ép các client trở thành subtype của bộ chuẩn hóa.

Tuy vậy, đừng tạo một lớp helper cho mọi dòng code đơn giản. Nếu một thuật toán ngắn chỉ thuộc một class, `private static method` hoặc một phương thức private là đủ. Tách collaborator khi có trách nhiệm dùng chung, có thuật toán độc lập, có nhu cầu test/thay thế hoặc một ranh giới rõ ràng.

## 7. Khi nào kế thừa vẫn là lựa chọn hợp lý?

Một thiết kế có thể chọn kế thừa khi cả **ngữ nghĩa subtype** và **hợp đồng** đều phù hợp. Chẳng hạn framework cung cấp base class với extension points được thiết kế rõ ràng, hoặc mô hình có phân loại chuyên biệt thật sự.

Ví dụ về kế thừa hướng tới hợp đồng:

~~~java
abstract class Shape {
    abstract double area();
}

final class Circle extends Shape {
    private final double radius;

    Circle(double radius) {
        if (!Double.isFinite(radius) || radius < 0.0) {
            throw new IllegalArgumentException("Bán kính không hợp lệ");
        }
        this.radius = radius;
    }

    @Override
    double area() {
        return Math.PI * radius * radius;
    }
}

static double areaOf(Shape shape) {
    return shape.area();
}
~~~

Ở đây `Circle` thực sự là một `Shape` theo abstraction đang được sử dụng; caller nhận `Shape` có thể lấy diện tích từ `Circle` mà không cần biết loại hình cụ thể. Đoạn `areaOf` minh họa phương thức static có thể đặt trong một lớp tiện ích; nếu đặt tất cả snippet vào một file Java để thử, cần thêm lớp bao ngoài cho method đó.

Có thể chọn **interface** thay vì abstract class khi chỉ muốn định nghĩa năng lực:

~~~java
interface Drawable {
    void draw();
}

final class SvgCircle implements Drawable {
    @Override
    public void draw() {
        System.out.println("<circle />");
    }
}
~~~

Một class có thể triển khai nhiều interface, nhưng Java chỉ cho kế thừa trực tiếp một class. Interface có `default method` đôi khi chia sẻ một hành vi mặc định gắn chặt với hợp đồng, **không nên bị lạm dụng thành kho các tiện ích không liên quan**.

### Khi dùng inheritance để tái sử dụng implementation là hợp lệ

Có những abstraction được xây dựng riêng cho việc mở rộng:

- Một base class có invariant và vòng đời được tài liệu hóa đầy đủ.
- Subclass đáp ứng mọi hành vi công khai của base class.
- Các điểm mở rộng `protected` và quy tắc override được thiết kế ổn định.
- Thay đổi implementation cha có test hợp đồng bảo vệ các subtype quan trọng.
- Quan hệ phân cấp giúp đơn giản mô hình so với việc tạo thêm nhiều wrapper.

Ví dụ `AbstractList<E>` trong JDK là một *skeletal implementation*: nó được thiết kế cho việc triển khai các kiểu List phù hợp hợp đồng. Đó là chuyện khác với việc cho `Inventory` kế thừa `HashMap` chỉ để lấy `get/put`. Nếu một subtype cố ý tuân thủ mọi semantics của Map/List thì sử dụng base collection phù hợp có thể hợp lý.

## 8. So sánh các lựa chọn tái sử dụng

| Lựa chọn | Nên chọn khi | Điều phải chú ý |
| --- | --- | --- |
| `private method` | Logic nhỏ chỉ dùng trong một lớp | Không trừu tượng hóa quá sớm |
| `static utility method` | Thuật toán thuần, không cần trạng thái | Giữ API có tên rõ, đừng tạo “God Utils” |
| **Composition** | Một đối tượng **có/sử dụng** collaborator | Chọn ownership và lifecycle rõ ràng |
| **Delegation** | Muốn chuyển một nhiệm vụ cụ thể sang cộng tác viên | Không phơi bày toàn bộ API nội bộ |
| **Interface + implementation** | Cần nhiều cách đáp ứng cùng hợp đồng, dependency boundary rõ | Mỗi implementation phải giữ đúng contract |
| **Abstract class** | Có họ subtype thật sự, chung invariant hoặc template được thiết kế để mở rộng | `protected`, constructor, override và LSP |
| **Decorator** | Cần chồng lớp hành vi quanh một hợp đồng | Thứ tự các wrapper và side effect |
| **Inheritance từ class concrete** | Chỉ khi class cha có thiết kế mở rộng và subtype đáp ứng đúng contract | Rủi ro phụ thuộc vào chi tiết implementation |

**Composition over inheritance** là một nguyên tắc ưu tiên có điều kiện, không phải luật cấm kế thừa. Nên chọn cách diễn đạt đúng domain và giảm coupling lâu dài.

## 9. Refactor từ inheritance sang composition

Giả sử codebase đang có:

~~~java
class PricingService extends SharedStringUtil {
    // Gọi formatCurrency(...) của SharedStringUtil.
}
~~~

Đừng sửa thành một hệ thống interface/factory phức tạp nếu thực tế chỉ cần một helper nhỏ. Quy trình refactor an toàn:

1. **Đọc toàn bộ API công khai của lớp cha** và nơi sử dụng subtype. Đặc biệt kiểm tra nơi truyền `PricingService` dưới kiểu `SharedStringUtil`.
2. **Xác định phương thức thực sự cần dùng** và hợp đồng của nó. Nếu logic nhỏ, cân nhắc helper; nếu là thành phần có trách nhiệm riêng, tạo collaborator.
3. **Đưa dependency vào constructor** hoặc giữ một thành phần private phù hợp. Thay `super.someMethod()` bằng `collaborator.someMethod()` ở chỗ cần.
4. **Gỡ `extends`**, chỉ sau khi caller không còn dựa vào quan hệ kiểu cũ. Nếu đây là public API, thay đổi có thể phá tính tương thích và cần kế hoạch migration.
5. **Giữ test hành vi** của nghiệp vụ và bổ sung test xác nhận invariant hoặc đường truy cập trước đây gây lỗi.
6. **Dọn những phương thức dư thừa** chỉ dùng để “giả làm” subtype, giữ một API nhỏ có ý nghĩa.

Trước và sau:

~~~mermaid
flowchart LR
    subgraph Before["Trước: is-a giả tạo"]
        A["PricingService"] -->|extends| B["SharedStringUtil"]
    end
    subgraph After["Sau: sử dụng collaborator"]
        C["PricingService"] -->|has-a / delegates| D["CurrencyFormatter"]
    end
~~~

**Không thực hiện refactor một cách cơ học** nếu base class chứa hook lifecycle, template method, protected state hoặc caller phụ thuộc mạnh vào polymorphism. Khi đó cần thiết kế lại ranh giới, không chỉ chuyển `extends` thành một field.

## 10. Kiểm thử để chứng minh việc đổi thiết kế có ích

Với ví dụ `InheritanceReuseDemo.java` ở trên, JUnit 5 có thể xác nhận chính các bất biến mà inheritance từ HashMap làm khó kiểm soát:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class InheritanceReuseDemoTest {

    @Test
    void thieuHangKhongLamKhoThayDoi() {
        var inventory = new InheritanceReuseDemo.Inventory();
        inventory.restock("BOOK", 2);

        assertFalse(inventory.reserve("BOOK", 3));
        assertEquals(2, inventory.available("BOOK"));
    }

    @Test
    void giuHangThanhCongKhongDeTonKhoAm() {
        var inventory = new InheritanceReuseDemo.Inventory();
        inventory.restock("BOOK", 5);

        assertTrue(inventory.reserve("BOOK", 3));
        assertEquals(2, inventory.available("BOOK"));
    }

    @Test
    void chanSoLuongAmVaTranhOverflow() {
        var inventory = new InheritanceReuseDemo.Inventory();

        assertThrows(IllegalArgumentException.class,
                () -> inventory.restock("BOOK", -1));

        inventory.restock("BOOK", Integer.MAX_VALUE);
        assertThrows(ArithmeticException.class,
                () -> inventory.restock("BOOK", 1));
        assertEquals(Integer.MAX_VALUE, inventory.available("BOOK"));
    }

    @Test
    void snapshotKhongChoSuaKhoQuaReferenceTraVe() {
        var inventory = new InheritanceReuseDemo.Inventory();
        inventory.restock("BOOK", 2);

        var snapshot = inventory.snapshot();

        assertThrows(UnsupportedOperationException.class,
                () -> snapshot.put("BOOK", -10));
        assertEquals(2, inventory.available("BOOK"));
    }
}
~~~

Các test này cần JUnit Jupiter trong classpath. Phần `InheritanceReuseDemo.java` không cần JUnit và chạy trực tiếp bằng JDK 17.

Phần quan trọng hơn test riêng từng hàm là **contract của Inventory**: sau mọi lệnh hợp lệ, giá trị tồn kho không âm; lỗi đầu vào không phá state; client không thể sửa dữ liệu mà bỏ qua phương thức nghiệp vụ. Nếu logic chuyển sang DB, các test tích hợp cần kiểm chứng tranh chấp đồng thời và transaction.

## 11. Những ngộ nhận dễ gặp

**“Cứ có mã giống nhau thì đưa vào superclass.”** Hai đoạn mã có thể giống nhau tạm thời nhưng có lý do thay đổi khác nhau. Kéo chúng vào cha chung có thể ép hai module thay đổi cùng nhau. Ưu tiên chia sẻ *tri thức và trách nhiệm thực sự chung*, không chỉ những dòng giống cú pháp.

**“Dùng `protected` là đã đóng gói.”** `protected` mở một bề mặt mở rộng cho subclass; nó tạo cam kết khó đổi trong hệ thống có kế thừa. Một field mutable `protected` có thể cho lớp con phá invariant mà lớp cha dự định bảo vệ.

**“Composition luôn cần interface.”** Không. Nếu chỉ có một collaborator cụ thể với API rõ và không có lý do thay thế, một field `private final SomeHelper` là đủ. Tạo interface trùng khít class chỉ để có DI có thể thêm boilerplate.

**“Đổi inheritance sang composition là xong mọi vấn đề.”** Cấu trúc dependency chỉ là một phần. Một collaborator chứa mutable state dùng chung sai cách vẫn có thể phá bất biến hoặc gây race. Phải thiết kế ownership, dữ liệu và transaction độc lập.

**“Mọi quan hệ is-a đều phải là inheritance từ class.”** Không. Nhiều hợp đồng thích hợp với interface, `sealed interface` hoặc các kiểu dữ liệu khác. Việc có chung một khả năng có thể diễn đạt bằng `implements` mà không ép dùng chung implementation.

**“Không bao giờ được dùng kế thừa.”** Đó cũng là một quy tắc quá cực đoan. Kế thừa có ích khi quan hệ subtype thật, các cam kết có thể được thực hiện, và extension points được thiết kế có chủ ý.

## 12. Checklist trước khi viết `extends`

Trả lời các câu hỏi này trong code review:

| Câu hỏi | Nếu câu trả lời là “không” |
| --- | --- |
| Có thể nói “mọi B đều là A” theo nghĩa hợp đồng, không chỉ tên gọi? | Xem lại composition hoặc interface |
| B có cần **toàn bộ** hành vi public kế thừa từ A không? | Tránh API phình và khả năng sửa state trái ý |
| B có thể được truyền cho một caller chỉ biết A mà giữ nguyên hậu điều kiện không? | Có nguy cơ vi phạm LSP |
| A đã được thiết kế hoặc tài liệu hóa để subclass mở rộng chưa? | Cẩn thận fragile base class và lifecycle |
| Có test hợp đồng cho các subtype chính không? | Khó phát hiện thay đổi phá polymorphism |
| Nếu A thay đổi implementation, B có vẫn đúng không? | Coupling vào chi tiết `protected`/override |
| Có cách đơn giản hơn như helper private hoặc collaborator không? | Ưu tiên mô hình dễ hiểu và có ít cam kết hơn |

Một dấu hiệu cảnh báo rất mạnh: **subclass chỉ dùng một hoặc hai phương thức của superclass và phần còn lại không có ý nghĩa với nó**. Khi gặp trường hợp này, trước hết hãy thử biểu diễn quan hệ **“B sử dụng A”** thay vì **“B là A”**.

## 13. Bài tập: lỗi tái sử dụng trong hệ thống khuyến mãi

Một lập trình viên thiết kế:

~~~java
class DiscountRule extends java.util.ArrayList<Integer> {
    int totalDiscount() {
        int sum = 0;
        for (int item : this) {
            sum += item;
        }
        return sum;
    }
}
~~~

Yêu cầu nghiệp vụ lại là: mỗi khoản giảm giá phải không âm, tổng giảm không được vượt giá trị đơn hàng, và chỉ application service hợp lệ mới được thêm hoặc xóa khoản giảm.

Hãy thực hiện:

1. Liệt kê ít nhất **ba đường đi từ API được kế thừa** khiến dữ liệu sai mà không qua kiểm tra.
2. Tách `DiscountRule` thành một lớp sở hữu `List<Integer>` private, cung cấp các phương thức có ý nghĩa nghiệp vụ (ví dụ `addDiscount`, `totalDiscount`) và kiểm tra hạn mức.
3. Phân biệt quy tắc thuộc đối tượng (một khoản giảm không âm) với quy tắc cần dữ liệu đơn hàng (tổng giảm không vượt giá trị đơn) để đặt validation ở đúng nơi.
4. Viết unit test chứng minh đối tượng không cho sửa danh sách từ bên ngoài và không bị overflow âm thầm.
5. Nếu cần nhiều thuật toán giảm giá độc lập, cân nhắc một `DiscountPolicy` interface; giải thích tại sao đây là một quan hệ hợp đồng có ý nghĩa, khác với `DiscountRule extends ArrayList`.

**Tự đánh giá:** class sau refactor có còn vô tình bị dùng như một `List<Integer>` không? Có phương thức công khai nào cho phép bỏ qua invariant không? Nếu đổi cấu trúc lưu trữ từ list sang một loại khác, client có phải sửa không?

**Điều cần ghi nhớ:** `extends` tạo ra **một cam kết quan hệ kiểu và hành vi**, không chỉ “mượn code”. Khi nhu cầu là sử dụng vài phương thức của đối tượng khác, hãy xem xét helper, composition và delegation. Chọn kế thừa khi subtype thực sự thay thế được supertype và toàn bộ hợp đồng kế thừa đều có ý nghĩa.