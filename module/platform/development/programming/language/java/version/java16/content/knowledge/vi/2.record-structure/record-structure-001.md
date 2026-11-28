# Record và mô hình lớp mang dữ liệu minh bạch

## 1. Vì sao Java cần `record`?

Trong ứng dụng Java, nhiều đối tượng chỉ có nhiệm vụ **mang một tập dữ liệu xác định**: thông tin trả về từ một API, kết quả truy vấn, thông số cấu hình đã kiểm tra, hoặc một giá trị dùng để truyền giữa các tầng. Với lớp thông thường, lập trình viên thường phải viết lặp lại field, constructor, phương thức đọc dữ liệu, `equals()`, `hashCode()` và `toString()`.

Từ **Java 16**, `record` là một tính năng chính thức của ngôn ngữ (JEP 395), tiếp tục được hỗ trợ trong Java hiện đại và **không cần bật preview**. `record` khai báo một lớp mà *hình dạng dữ liệu* được thể hiện ngay trong phần đầu khai báo:

```java
record Point(int x, int y) {}
```

`Point` mang đúng hai thành phần (`record components`) là `x` và `y`. Việc công khai cấu trúc dữ liệu này là một cam kết về mô hình: người dùng kiểu `Point` biết rằng ý nghĩa của giá trị được quyết định bởi hai thành phần đó. Đây là nội dung của cụm từ **lớp mang dữ liệu minh bạch** (*transparent data carrier*).

Mục tiêu của bài học:

- Hiểu `record` diễn đạt điều gì về thiết kế, ngoài việc giúp viết ít mã.
- Biết các thành phần và phương thức mà trình biên dịch cung cấp.
- Phân biệt tính bất biến của field với bất biến của toàn bộ dữ liệu tham chiếu.
- Biết khi nào nên chọn `record` và khi nào vẫn cần một lớp thông thường.

## 2. Từ lớp mang dữ liệu thủ công đến `record`

Xét kiểu dữ liệu chỉ lưu tọa độ. Một cách viết với lớp thông thường là:

```java
import java.util.Objects;

final class PointValue {
    private final int x;
    private final int y;

    PointValue(int x, int y) {
        this.x = x;
        this.y = y;
    }

    public int x() { return x; }
    public int y() { return y; }

    @Override
    public boolean equals(Object other) {
        if (!(other instanceof PointValue p)) {
            return false;
        }
        return x == p.x && y == p.y;
    }

    @Override
    public int hashCode() {
        return Objects.hash(x, y);
    }

    @Override
    public String toString() {
        return "PointValue[x=" + x + ", y=" + y + "]";
    }
}
```

Khi dùng `record`, cách mô tả tương ứng gọn hơn:

```java
record Point(int x, int y) {}
```

Trình biên dịch tạo các thành phần thiết yếu dựa trên danh sách `int x, int y`. Cả hai kiểu đều có thể đại diện cho giá trị tọa độ; `record` giúp ý định này trở nên rõ ràng và tránh việc quên cập nhật `equals()` hoặc `hashCode()` khi thêm thành phần mới.

### Những gì trình biên dịch cung cấp

| Thành phần | Với `record Point(int x, int y)` |
| --- | --- |
| Dữ liệu lưu trữ | Hai field `private final` tương ứng với `x` và `y`. |
| Constructor chuẩn (*canonical constructor*) | Constructor nhận đủ `x` và `y` theo đúng thứ tự khai báo. |
| Phương thức đọc (*accessor*) | `public int x()` và `public int y()`, **không phải** `getX()`/`getY()`. |
| `equals(Object)` | So sánh các đối tượng record cùng kiểu dựa trên giá trị các component. |
| `hashCode()` | Tính từ các component, nhất quán với `equals()`. |
| `toString()` | Biểu diễn kiểu cùng tên và giá trị các component, hữu ích khi xem log/debug. |

Ví dụ sử dụng:

```java
Point first = new Point(3, 7);
Point second = new Point(3, 7);

System.out.println(first.x());             // 3
System.out.println(first.equals(second));  // true
System.out.println(first == second);       // false: đây là hai object
System.out.println(first);                  // Point[x=3, y=7]
```

Điểm cần hiểu: `record` vẫn là **lớp kiểu tham chiếu**; tạo đối tượng bằng `new`, và toán tử `==` vẫn so sánh tham chiếu. `equals()` do compiler cung cấp mới thể hiện *ngữ nghĩa giá trị* của record. Đừng dựa vào định dạng chính xác của `toString()` để lưu trữ hay trao đổi dữ liệu, vì đó không phải giao thức serialization.

## 3. “Minh bạch” là một quyết định thiết kế

Với một lớp thông thường, tác giả có thể chọn chi tiết nào là trạng thái nội bộ, che giấu hoặc thay đổi cách biểu diễn bên trong. Ngược lại, danh sách component của record định nghĩa một phần quan trọng trong **API công khai của kiểu**.

```java
public record CustomerSummary(long id, String name, String tier) {}
```

Người dùng có thể gọi `id()`, `name()`, `tier()` và mong đợi hai `CustomerSummary` có cùng giá trị ba component sẽ bằng nhau. Việc thêm, bớt, đổi tên hoặc đổi kiểu component có thể làm thay đổi constructor, accessor và ngữ nghĩa so sánh, nên cần được xem là **thay đổi hợp đồng API**. Nếu dữ liệu là DTO đã được các hệ thống khác sử dụng, hãy quản lý quá trình thay đổi phiên bản một cách có chủ đích.

`record` **không có nghĩa là lớp không được chứa hành vi**. Ta vẫn có thể thêm phương thức nghiệp vụ chỉ dựa trên các component:

```java
public record Rectangle(double width, double height) {
    public double area() {
        return width * height;
    }
}
```

`area()` là hành vi phù hợp vì được suy ra từ dữ liệu đã khai báo, không cần một trạng thái ẩn có thể thay đổi độc lập.

## 4. Ranh giới cấu trúc của một `record`

Các ràng buộc của record giúp giữ lời hứa rằng trạng thái của nó được mô tả bởi các component:

- Record **ngầm là `final`**, không thể dùng làm lớp cha và không có mệnh đề `extends` tùy ý; lớp cha trực tiếp là `java.lang.Record`.
- Record **có thể `implements` interface**, khai báo phương thức riêng, hằng số và thành viên `static`.
- Không thể khai báo thêm **instance field** nằm ngoài các component hoặc instance initializer; vì vậy không thể lén thêm một trạng thái instance độc lập.
- Các field component là `private final`: không gán lại được sau khi đối tượng hoàn tất khởi tạo; không có setter do trình biên dịch tạo.
- Có thể khai báo record generic, record lồng trong lớp, và record cục bộ khi chúng diễn đạt dữ liệu rõ ràng hơn.

Ví dụ record hiện thực một interface:

```java
interface HasCode {
    String code();
}

record CourseId(String code) implements HasCode {
    public boolean isJavaCourse() {
        return code.startsWith("JAVA-");
    }
}
```

Constructor thông thường vẫn tồn tại nếu bạn cần thêm quy tắc khởi tạo. Tuy nhiên, record nên giữ vai trò đối tượng giá trị, không biến thành thực thể có vòng đời và trạng thái biến đổi phức tạp.

## 5. Dữ liệu hợp lệ ngay từ khi khởi tạo

Record phù hợp cho dữ liệu đi qua ranh giới hệ thống nếu ta buộc dữ liệu tuân thủ bất biến (*invariant*) tại lúc tạo. Java hỗ trợ **compact canonical constructor**: viết phần thân constructor mà không lặp lại danh sách tham số.

```java
import java.math.BigDecimal;
import java.util.Objects;

public record ProductPrice(String sku, BigDecimal amount) {
    public ProductPrice {
        sku = Objects.requireNonNull(sku, "sku").strip();
        Objects.requireNonNull(amount, "amount");

        if (sku.isEmpty()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        if (amount.signum() < 0) {
            throw new IllegalArgumentException("amount must be non-negative");
        }
    }

    public boolean isFree() {
        return amount.signum() == 0;
    }
}
```

Khi chạy `new ProductPrice("  SKU-01  ", new BigDecimal("12.50"))`, giá trị `sku()` được chuẩn hóa thành `"SKU-01"`. Trong compact constructor, các tên `sku`, `amount` là **tham số constructor**; sau phần thân, Java tự gán giá trị cuối cùng của chúng cho các field tương ứng. Không tự viết `this.sku = sku` trong compact constructor.

Khi cần kiểm soát từng phép gán, có thể viết canonical constructor đầy đủ (`ProductPrice(String sku, BigDecimal amount)`), nhưng khi đó phải tự khởi tạo tất cả các field component. Các constructor phụ, nếu có, phải ủy quyền đến constructor khác trong chính record bằng `this(...)` để cuối cùng đi qua canonical constructor.

**Nguyên tắc:** Kiểm tra `null`, chuẩn hóa giá trị và kiểm tra quy tắc nghiệp vụ ngay khi tạo record. Việc đặt các quy tắc này ở constructor giúp mọi đối tượng mới đều đi qua một điểm xác thực thống nhất.

## 6. `final` không đồng nghĩa bất biến sâu

Đây là giới hạn quan trọng nhất khi áp dụng record trong thực tế. Record **bất biến ở mức field** (*shallowly immutable*): ta không thể gán một tham chiếu mới vào field component, nhưng đối tượng mà field đó trỏ đến vẫn có thể thay đổi.

```java
import java.util.List;

record UnsafeOrder(String id, List<String> items) {}
```

Nếu `items` là một `ArrayList` có thể sửa được, mã bên ngoài vẫn có thể thêm phần tử qua danh sách ban đầu hoặc qua `unsafeOrder.items()`. Trạng thái mà record biểu diễn sẽ thay đổi dù field `items` là `final`.

Với danh sách gồm phần tử bất biến như `String`, có thể sao chép phòng vệ ngay trong compact constructor:

```java
import java.util.List;
import java.util.Objects;

public record OrderSnapshot(String orderId, List<String> items) {
    public OrderSnapshot {
        orderId = Objects.requireNonNull(orderId, "orderId").strip();
        if (orderId.isEmpty()) {
            throw new IllegalArgumentException("orderId must not be blank");
        }
        items = List.copyOf(Objects.requireNonNull(items, "items"));
    }
}
```

`List.copyOf()` tạo hoặc tái sử dụng một danh sách không cho phép sửa cấu trúc, ngăn thay đổi danh sách nguồn ảnh hưởng đến snapshot; nó cũng từ chối phần tử `null`. Tuy nhiên, đây **không phải deep copy**: nếu phần tử là đối tượng mutable, việc sửa chính phần tử ấy vẫn có thể quan sát được. Khi cần bất biến sâu, hãy dùng component có kiểu bất biến hoặc sao chép phòng vệ đối tượng lồng nhau.

Một bẫy khác là **mảng**:

```java
record Payload(byte[] bytes) {}

Payload a = new Payload(new byte[] {1, 2});
Payload b = new Payload(new byte[] {1, 2});
System.out.println(a.equals(b)); // false
```

Mảng vừa có thể thay đổi nội dung, vừa có `equals()` mặc định theo tham chiếu. `equals()` sinh tự động cho record không biến so sánh mảng thành so sánh từng phần tử. Nếu muốn bình đẳng theo nội dung, ưu tiên một kiểu giá trị bất biến phù hợp (ví dụ danh sách phần tử bất biến với bản sao phòng vệ), hoặc tự thiết kế cơ chế so sánh và sao chép nhất quán.

## 7. Ví dụ hoàn chỉnh: DTO khóa học bất biến ở biên ứng dụng

Giả sử ứng dụng trả về một thẻ giới thiệu khóa học. Bản ghi cần mã khóa học, tiêu đề, danh sách nhãn; dữ liệu phải được chuẩn hóa và không bị thay đổi khi người gọi tiếp tục sửa danh sách ban đầu.

Lưu đoạn mã sau vào **`Demo.java`**; chạy được với Java 16 trở lên:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class Demo {
    record CourseCard(String code, String title, List<String> tags) {
        CourseCard {
            code = Objects.requireNonNull(code, "code").strip();
            title = Objects.requireNonNull(title, "title").strip();
            tags = List.copyOf(Objects.requireNonNull(tags, "tags"));

            if (code.isEmpty() || title.isEmpty()) {
                throw new IllegalArgumentException("code and title are required");
            }
        }

        boolean hasTag(String tag) {
            return tags.contains(tag);
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("java", "backend"));
        CourseCard first = new CourseCard(" JAVA-16 ", " Records ", source);

        source.add("changed-outside");
        CourseCard same = new CourseCard(
            "JAVA-16", "Records", List.of("java", "backend")
        );

        System.out.println(first.code());             // JAVA-16
        System.out.println(first.title());            // Records
        System.out.println(first.tags());             // [java, backend]
        System.out.println(first.equals(same));       // true
        System.out.println(first.hasTag("java"));     // true
    }
}
```

```bash
javac --release 16 Demo.java
java Demo
```

Trong ví dụ này, `CourseCard` là record lồng trong lớp `Demo` (record lồng có tính chất `static`). `List.copyOf()` bảo vệ danh sách tag khỏi tác động từ biến `source`. Phương thức `hasTag()` cho thấy record vẫn có thể có hành vi hữu ích, miễn là hành vi gắn với các component của nó.

## 8. Khi nào nên chọn `record`?

| Nhu cầu thiết kế | Gợi ý |
| --- | --- |
| DTO truyền dữ liệu giữa tầng service và controller, response model, kết quả truy vấn | Thường phù hợp: cấu trúc dữ liệu tường minh, so sánh theo giá trị, ít mã lặp. |
| Đối tượng giá trị như tọa độ, khoảng thời gian, cặp khóa/giá trị, trạng thái snapshot | Phù hợp nếu mọi component có ngữ nghĩa giá trị ổn định và được bảo vệ khỏi sửa đổi ngoài ý muốn. |
| Đối tượng cần kiểm tra/chuẩn hóa tại thời điểm tạo | Phù hợp: dùng canonical constructor để đảm bảo invariant. |
| Thực thể cần đổi trạng thái qua setter, kế thừa lớp cơ sở, hoặc có danh tính độc lập với giá trị field | Chọn lớp thông thường; các ràng buộc của record có thể mâu thuẫn với mô hình. |
| Entity ORM/JPA phụ thuộc proxy, constructor không tham số và quản lý trạng thái | Không mặc định thay bằng record; cân nhắc dùng record ở tầng projection/DTO, tùy hỗ trợ thực tế của framework. |
| Dữ liệu chứa danh sách, mảng hoặc đối tượng mutable | Chỉ dùng khi đã chủ động thiết kế sao chép phòng vệ và ngữ nghĩa `equals()`/`hashCode()`. |

### Các lỗi dễ gặp

1. **Nhầm `record` với deep immutable:** field `final` không tự bảo vệ đối tượng mutable bên trong.
2. **Mong đợi getter kiểu JavaBean:** `customer.name()` là accessor mặc định, không phải `customer.getName()`; thư viện cụ thể cần được kiểm tra khả năng hỗ trợ record.
3. **Dùng component như chi tiết cài đặt có thể đổi tùy ý:** component là phần quan trọng của API và ngữ nghĩa so sánh.
4. **Cho dữ liệu nhạy cảm vào component rồi ghi log cả record:** `toString()` mặc định làm lộ biểu diễn component; chỉ log các trường được phép xuất hiện.
5. **Dùng record cho đối tượng có danh tính và vòng đời:** nếu hai đối tượng có cùng dữ liệu nhưng vẫn phải được xem là hai thực thể khác nhau, `equals()` theo component có thể không đúng ý nghĩa nghiệp vụ.

## 9. Tự thực hành

1. Chuyển một lớp `BookSummary` gồm `isbn`, `title`, `author` thành record. Gọi accessor và so sánh hai bản ghi có cùng dữ liệu bằng `equals()`.
2. Bổ sung compact constructor để loại khoảng trắng đầu/cuối của `isbn`, từ chối ISBN rỗng và từ chối `null` cho tên sách.
3. Thêm `List<String> categories` vào record; chứng minh rằng thay đổi `ArrayList` nguồn không thể thay đổi danh sách bên trong sau khi dùng `List.copyOf()`.
4. Giải thích vì sao việc thêm `lastViewedAt` vào header của record có thể ảnh hưởng đến hành vi `equals()` dù trường này chỉ phục vụ giao diện.

## Ghi nhớ

`record` thể hiện **hợp đồng mang dữ liệu minh bạch**: kiểu dữ liệu, API truy cập và phép so sánh theo giá trị gắn chặt với các component được khai báo. Dùng record khi cấu trúc và giá trị của dữ liệu là trung tâm thiết kế; dùng canonical constructor để đảm bảo dữ liệu hợp lệ; và tự xử lý các component mutable nếu cần bảo đảm bất biến thực sự. Đây là kiến thức chính thức từ Java 16, vẫn là lựa chọn phổ biến trong Java hiện đại.

**Tài liệu tham khảo chính thức:**

- [OpenJDK JEP 395 – Records](https://openjdk.org/jeps/395)
- [Oracle Java – Record Classes](https://docs.oracle.com/en/java/javase/25/language/records.html)
- [Javadoc `java.lang.Record`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Record.html)
