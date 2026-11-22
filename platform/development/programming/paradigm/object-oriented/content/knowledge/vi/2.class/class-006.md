# Thành viên chỉ đọc và thành viên có thể thay đổi trong lớp Java

Khi thiết kế một lớp (class), không phải dữ liệu nào của đối tượng cũng được phép sửa sau khi khởi tạo. Mã định danh sản phẩm thường cần giữ nguyên, còn tên hiển thị hoặc giá bán có thể thay đổi theo quy tắc nghiệp vụ. Java cho phép thiết kế hai nhóm thuộc tính này bằng cách kết hợp **đóng gói (encapsulation)**, từ khóa `final`, phương thức đọc (getter) và phương thức cập nhật (setter hoặc phương thức nghiệp vụ).

> **Ý chính:** “Chỉ đọc” có thể có nghĩa là *người dùng lớp chỉ được xem*, hoặc *giá trị không được gán lại sau khi khởi tạo*. Hai ý này liên quan nhưng không đồng nhất. Cần xác định rõ ta muốn bảo vệ **tham chiếu**, **trạng thái đối tượng** hay **quyền cập nhật từ bên ngoài**.

## 1. Phân biệt các kiểu thành viên

Trong Java, “thành viên của lớp” bao gồm trường dữ liệu (field), phương thức (method), lớp lồng nhau… Khi nói về thành viên “chỉ đọc/có thể thay đổi”, ta thường đang bàn về **thuộc tính/trạng thái** và API truy cập chúng.

| Cách khai báo hoặc cung cấp API | Bên ngoài đọc? | Bên ngoài sửa trực tiếp? | Bên trong lớp có thể thay đổi? |
| --- | --- | --- | --- |
| `private final String id` + `getId()` | Có | Không | Không thể gán lại `id` sau khi khởi tạo |
| `private String name` + `getName()`, `setName()` | Có | Qua setter | Có, theo kiểm tra của setter |
| `private int stock` + `getStock()`, `reserve()` | Có | Chỉ qua hành vi `reserve()` | Có, theo quy tắc nghiệp vụ |
| `public String name` | Có | Có, gán trực tiếp | Có, khó kiểm soát |
| `private final List<String> tags` + `getTags()` | Có | Tùy cách trả về danh sách | Tham chiếu không gán lại, phần tử có thể vẫn bị sửa nếu danh sách mutable |

**Đóng gói** thường bắt đầu từ khai báo field `private`, sau đó chỉ công khai những phương thức thật sự cần thiết. Getter và setter là lựa chọn thiết kế, không phải quy định rằng thuộc tính nào cũng cần cả hai.

## 2. Ví dụ thực tế: sản phẩm có thuộc tính chỉ đọc và thuộc tính được cập nhật

Giả sử hệ thống quản lý sản phẩm yêu cầu:

- **SKU**: mã sản phẩm, không được đổi sau khi tạo.
- **createdAt**: thời điểm tạo, không được đổi.
- **name**: tên hiển thị, được sửa nhưng không được rỗng.
- **price**: giá bán, được sửa nhưng không được âm.

`Product.java` (Java 11+):

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;

public class Product {
    // Chỉ được gán trong quá trình khởi tạo đối tượng.
    private final String sku;
    private final Instant createdAt;

    // Có thể được gán lại thông qua các phương thức được kiểm soát.
    private String name;
    private BigDecimal price;

    public Product(String sku, String name, BigDecimal price) {
        this.sku = Objects.requireNonNull(sku, "sku").trim();
        if (this.sku.isEmpty()) {
            throw new IllegalArgumentException("SKU không được rỗng");
        }

        this.createdAt = Instant.now();
        setName(name);
        setPrice(price);
    }

    // API chỉ đọc.
    public String getSku() {
        return sku;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    // API đọc/ghi có kiểm soát.
    public String getName() {
        return name;
    }

    public void setName(String name) {
        String value = Objects.requireNonNull(name, "name").trim();
        if (value.isEmpty()) {
            throw new IllegalArgumentException("Tên không được rỗng");
        }
        this.name = value;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public void setPrice(BigDecimal price) {
        Objects.requireNonNull(price, "price");
        if (price.signum() < 0) {
            throw new IllegalArgumentException("Giá không được âm");
        }
        this.price = price;
    }
}
~~~

Cách sử dụng:

~~~java
import java.math.BigDecimal;

public class Main {
    public static void main(String[] args) {
        Product product = new Product(
                "BOOK-001", "Java căn bản", new BigDecimal("150000")
        );

        System.out.println(product.getSku());       // BOOK-001
        System.out.println(product.getCreatedAt()); // Thời điểm tạo
        System.out.println(product.getPrice());     // 150000

        product.setName("Java nâng cao"); // Hợp lệ
        product.setPrice(new BigDecimal("180000")); // Hợp lệ

        // product.setSku("BOOK-002"); // Lỗi biên dịch: không có setSku
        // product.sku = "BOOK-002";  // Lỗi biên dịch: sku là private

        // Ném IllegalArgumentException:
        // product.setPrice(new BigDecimal("-1000"));
    }
}
~~~

Điểm quan trọng là **quyền sửa thuộc tính là quyết định của lớp**. Người dùng `Product` có thể đọc `sku` nhưng không có đường cập nhật công khai; với `price`, người dùng chỉ thay đổi được thông qua kiểm tra giá hợp lệ. Cách này giúp các đối tượng không dễ rơi vào trạng thái sai nghiệp vụ.

## 3. `final` bảo vệ điều gì?

Một field `final` chỉ được **gán giá trị đúng một lần** trong quá trình khởi tạo: ngay tại chỗ khai báo, trong khối khởi tạo hoặc trong constructor phù hợp. Sau khi gán, không thể gán lại field đó.

~~~java
public class Customer {
    private final long id;
    private String email;

    public Customer(long id, String email) {
        this.id = id;
        this.email = email;
    }

    public long getId() { return id; }
    public String getEmail() { return email; }

    public void changeEmail(String email) {
        this.email = email;
    }

    // public void changeId(long newId) {
    //     this.id = newId; // LỖI: không thể gán lại final field
    // }
}
~~~

Tuy nhiên, **`final` trên biến tham chiếu không làm cho đối tượng được trỏ tới trở nên bất biến**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class Basket {
    private final List<String> items = new ArrayList<>();

    public void add(String item) {
        items.add(item); // Hợp lệ: thay đổi nội dung List
    }

    public List<String> getItems() {
        return items; // Nguy hiểm: làm lộ List mutable
    }
}
~~~

Đoạn gọi sau có thể sửa dữ liệu nội bộ mà không thông qua `add`:

~~~java
Basket basket = new Basket();
basket.add("Sách");
basket.getItems().clear(); // Xóa dữ liệu nội bộ!
~~~

`items` không thể trỏ sang danh sách khác vì `final`, nhưng danh sách hiện tại vẫn có thể thay đổi. Tương tự, getter không có setter **chưa đủ** để đảm bảo đối tượng là bất biến.

## 4. Tạo API chỉ đọc an toàn với collection

Nếu trạng thái cần là danh sách chỉ đọc, có thể tạo **bản sao không thể chỉnh sửa** ngay khi khởi tạo:

~~~java
import java.util.List;
import java.util.Objects;

public class Course {
    private final String code;
    private final List<String> topics;

    public Course(String code, List<String> topics) {
        this.code = Objects.requireNonNull(code, "code");
        this.topics = List.copyOf(
                Objects.requireNonNull(topics, "topics")
        );
    }

    public String getCode() {
        return code;
    }

    public List<String> getTopics() {
        return topics;
    }
}
~~~

Kiểm chứng:

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> input = new ArrayList<>(List.of("OOP", "Exception"));
Course course = new Course("JAVA-01", input);

input.add("Thread"); // Không ảnh hưởng topics của course

System.out.println(course.getTopics()); // [OOP, Exception]

// Ném UnsupportedOperationException:
course.getTopics().add("Spring");
~~~

`List.copyOf` (Java 10+) tạo danh sách không sửa được và không phụ thuộc vào các thay đổi tiếp theo trên danh sách đầu vào. Lưu ý: đây là **bất biến nông (shallow)**. Nếu các phần tử là đối tượng mutable, bản thân phần tử vẫn có thể bị sửa qua tham chiếu; ví dụ trên an toàn vì `String` là immutable. `List.copyOf` cũng không chấp nhận phần tử `null`.

So sánh nhanh:

| Cách trả về | Đặc điểm |
| --- | --- |
| `return internalList;` | Người gọi có thể thay đổi trực tiếp nếu là List mutable |
| `return Collections.unmodifiableList(internalList);` | Không sửa qua view được, nhưng vẫn nhìn thấy thay đổi do danh sách gốc tạo ra |
| `return List.copyOf(internalList);` | Danh sách kết quả không sửa được; tạo snapshot logic của các phần tử |
| `return new ArrayList<>(internalList);` | Người gọi sửa bản sao được nhưng không ảnh hưởng danh sách bên trong (nếu phần tử không bị chia sẻ trạng thái mutable) |

Nếu lớp **cần tiếp tục quản lý một danh sách mutable bên trong**, có thể trả về `List.copyOf(items)` từ getter để cung cấp snapshot chỉ đọc mỗi lần gọi, trong khi vẫn dùng phương thức nghiệp vụ để cập nhật nội bộ.

## 5. Chỉ đọc từ bên ngoài vẫn có thể thay đổi ở bên trong

Đôi khi giá trị được phép thay đổi nhưng **không nên có setter công khai**. Ví dụ lượng tồn kho chỉ giảm khi đặt hàng hợp lệ; nếu tạo `setStock(int)`, người gọi có thể bỏ qua quy trình đặt hàng.

~~~java
public class Inventory {
    private int available;

    public Inventory(int initialQuantity) {
        if (initialQuantity < 0) {
            throw new IllegalArgumentException("Tồn kho không được âm");
        }
        this.available = initialQuantity;
    }

    public int getAvailable() {
        return available; // Người ngoài chỉ đọc được con số
    }

    public void reserve(int quantity) {
        if (quantity <= 0 || quantity > available) {
            throw new IllegalArgumentException("Số lượng đặt không hợp lệ");
        }
        available -= quantity;
    }

    public void restock(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Số lượng nhập phải dương");
        }
        available = Math.addExact(available, quantity);
    }
}
~~~

~~~java
Inventory inventory = new Inventory(10);
inventory.reserve(3);
System.out.println(inventory.getAvailable()); // 7

// inventory.setAvailable(999); // Không có API này
~~~

Ở đây `available` **không phải field final**, vì số lượng thay đổi sau mỗi giao dịch. Nhưng đối với mã nguồn gọi từ bên ngoài, đây vẫn là thuộc tính **chỉ có quyền đọc trực tiếp qua getter**; mọi thay đổi phải đi qua `reserve` hoặc `restock`.

Luồng trách nhiệm có thể hình dung như sau:

~~~mermaid
flowchart TD
    A["Code sử dụng Inventory"] --> B["getAvailable(): đọc tồn kho"]
    A --> C["reserve(quantity): yêu cầu đặt"]
    C --> D{"Số lượng hợp lệ?"}
    D -->|Có| E["Cập nhật available"]
    D -->|Không| F["Ném ngoại lệ"]
~~~

**Lưu ý về đồng thời:** ví dụ `Inventory` trên phù hợp để minh họa đóng gói trong môi trường đơn luồng. Nếu nhiều luồng hoặc nhiều request cùng đặt hàng, kiểm tra và trừ tồn kho phải được bảo vệ bằng cơ chế đồng bộ/giao dịch/locking thích hợp; `private`, getter hay `final` tự chúng không ngăn được race condition.

## 6. Thuộc tính chỉ đọc, hằng số và immutable object có giống nhau không?

| Khái niệm | Ý nghĩa chính | Ví dụ |
| --- | --- | --- |
| Read-only API | Bên ngoài chỉ quan sát trạng thái, không được gán tùy ý | `getAvailable()` mà không có `setAvailable()` |
| Final field | Không gán lại field sau khi khởi tạo | `private final String sku` |
| Constant | Hằng số thường dùng chung trên lớp, phổ biến với `static final` | `public static final int MAX_ITEMS = 100;` |
| Immutable object | Toàn bộ trạng thái quan sát được không thay đổi sau khi tạo | `String`, `BigDecimal`, lớp value object thiết kế đúng |
| Mutable object | Một phần trạng thái có thể thay đổi theo thời gian | `Product` với `setPrice()` |

Ví dụ hằng số:

~~~java
public final class CartRules {
    private CartRules() {
        // Không cho tạo instance của lớp tiện ích.
    }

    public static final int MAX_ITEMS = 100;
}

// Dùng: CartRules.MAX_ITEMS
~~~

Một `static final` tham chiếu tới đối tượng mutable vẫn **không tự biến đối tượng đó thành immutable**. Hằng số đối với kiểu nguyên thủy hoặc `String` là những trường hợp trực quan và an toàn hơn.

Java 16+ còn có **record**, giúp biểu diễn dữ liệu chỉ đọc đơn giản:

~~~java
import java.math.BigDecimal;
import java.util.Objects;

public record ProductSummary(String sku, BigDecimal price) {
    public ProductSummary {
        Objects.requireNonNull(sku, "sku");
        Objects.requireNonNull(price, "price");
        if (price.signum() < 0) {
            throw new IllegalArgumentException("Giá không được âm");
        }
    }
}
~~~

~~~java
ProductSummary summary =
        new ProductSummary("BOOK-001", new BigDecimal("200000"));

System.out.println(summary.sku());
System.out.println(summary.price());

// summary.price = ...; // Không thể gán: component thuộc record là final
// summary.setPrice(...); // Record không tự tạo setter
~~~

Với `String` và `BigDecimal` đều bất biến, `ProductSummary` là value object bất biến theo các thành phần này. **Record chỉ bảo đảm bất biến nông**: nếu thành phần là `List` hoặc một đối tượng mutable thì cần defensive copy, kiểm soát getter/accessor hoặc thiết kế thành phần bất biến phù hợp.

## 7. Chọn cách thiết kế theo nghiệp vụ

Trước khi khai báo field, hãy xác định **ai được phép thay đổi**, **thời điểm thay đổi** và **điều kiện hợp lệ**:

| Thuộc tính | Thiết kế thường phù hợp | Lý do |
| --- | --- | --- |
| Mã hóa đơn, mã sản phẩm | `private final` + getter | Danh tính ổn định sau khởi tạo |
| Tên hiển thị | `private` + getter + setter kiểm tra đầu vào | Được phép sửa nhưng phải hợp lệ |
| Số dư tài khoản | `private` + getter + `deposit()/withdraw()` | Tránh setter tùy ý làm mất quy tắc |
| Ngày tạo | `private final Instant` + getter | Là mốc lịch sử không cần sửa |
| Danh sách vai trò | Bản sao không sửa được hoặc API cập nhật có kiểm soát | Tránh người gọi can thiệp trực tiếp |
| Tổng tiền tính từ chi tiết | Getter tính toán, không lưu field nếu không cần | Tránh dữ liệu dẫn xuất bị lệch |

**Những lỗi hay gặp khi mới học:**

1. Mặc định sinh setter cho mọi field, kể cả mã định danh hoặc trạng thái nghiệp vụ quan trọng.
2. Cho rằng `private` đồng nghĩa với immutable. Thực tế `private` chỉ giới hạn quyền truy cập trực tiếp.
3. Cho rằng `final List<T>` khiến toàn bộ list và phần tử không thể sửa.
4. Trả về array, collection hoặc `Date` mutable nội bộ mà không tạo bản sao khi cần.
5. Chỉ kiểm tra giá trị trong constructor nhưng để setter ghi giá trị không hợp lệ.
6. Dùng getter/setter cho thao tác mang ý nghĩa nghiệp vụ rõ ràng, thay vì đặt tên `reserve`, `cancel`, `activate`…

## 8. Tự kiểm tra

**Câu 1.** Field `private final String id` có getter nhưng không có setter là chỉ đọc theo nghĩa nào?

Field `id` không được gán lại sau lúc khởi tạo; bên ngoài chỉ có thể xem giá trị thông qua getter. `String` cũng immutable nên không phát sinh vấn đề sửa trạng thái nội bộ của chuỗi.

**Câu 2.** Field `private int stock` có getter và `reserve(int)` nhưng không có setter có phải “chỉ đọc” không?

Chỉ đọc **đối với API truy cập trực tiếp từ bên ngoài**; trạng thái thật vẫn mutable và được cập nhật thông qua `reserve`. Đây là cách thường được ưu tiên khi thao tác phải tuân thủ quy tắc nghiệp vụ.

**Câu 3.** Vì sao getter trả về `List` có thể phá vỡ ý định chỉ đọc dù field là `final`?

Vì `final` khóa **việc gán lại tham chiếu**, không khóa **nội dung đối tượng**. Nếu getter lộ danh sách mutable, người gọi có thể sửa trực tiếp. Hãy dùng immutable collection, defensive copy hoặc API truy cập được kiểm soát.

**Câu 4.** Khi nào nên chọn một object bất biến hoàn toàn?

Khi dữ liệu mô tả một giá trị/snapshot cần ổn định (ví dụ thông tin tổng hợp dùng để truyền dữ liệu), ít có nhu cầu cập nhật từng field và có thể tạo object mới khi giá trị thay đổi. Với đối tượng có vòng đời và chuyển trạng thái nghiệp vụ, có thể chọn mutable có kiểm soát.

**Ghi nhớ:** Quyền đọc/ghi nên xuất phát từ quy tắc của đối tượng. `final` giúp cố định một phép gán; `private` và getter/setter giúp kiểm soát API; defensive copy giúp bảo vệ dữ liệu tham chiếu; immutable object giúp trạng thái không đổi. Kết hợp đúng các công cụ đó mới tạo nên một lớp dễ sử dụng và khó bị cập nhật sai.