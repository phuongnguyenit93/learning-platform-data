# Mục đích của `record` và mối liên hệ với lớp mang dữ liệu trong Java 17

## 1. Vì sao Java có `record`?

Trong nhiều chương trình, ta cần một kiểu chỉ để **mang một nhóm dữ liệu có tên và kiểu rõ ràng**. Ví dụ, một tọa độ gồm `x`, `y`; một dòng hóa đơn gồm mã sản phẩm, số lượng và đơn giá; hay một kết quả thống kê gồm tổng số và giá trị trung bình. Các đối tượng kiểu này thường được tạo bằng constructor, đọc dữ liệu qua các phương thức, so sánh theo nội dung và in ra để theo dõi.

Trước khi có `record`, một lớp Java mang dữ liệu thường phải viết nhiều mã lặp:

- Trường dữ liệu, thường là `private final`.
- Constructor để nhận và gán dữ liệu.
- Phương thức đọc từng trường.
- `equals(Object)` và `hashCode()` để so sánh theo nội dung, dùng làm khóa trong collection.
- `toString()` để biểu diễn đối tượng dễ đọc.

Nếu lớp thực sự chỉ biểu diễn một nhóm dữ liệu, lượng mã này có thể lớn hơn phần mô tả ý nghĩa dữ liệu. Dùng công cụ IDE sinh code giúp giảm thao tác nhập, nhưng vẫn để lại nhiều phương thức phải bảo trì khi thêm, đổi tên hoặc bỏ trường.

**`record`** được thiết kế để mô tả trực tiếp kiểu mang dữ liệu: người viết công bố **các thành phần dữ liệu** (*record components*) ngay trong phần khai báo; trình biên dịch tạo các thành viên chuẩn tương ứng. Nó giúp mã ngắn hơn và thể hiện rõ hợp đồng của kiểu: “đối tượng này được đặc trưng bởi những thành phần dữ liệu nào?”.

`record` là một dạng **class đặc biệt trong Java**, không phải một kiểu primitive hoặc cấu trúc dữ liệu nằm ngoài mô hình đối tượng. Record được chuẩn hóa từ Java 16 (JEP 395), vì vậy **Java 17 sử dụng record như tính năng ổn định, không cần bật preview**.

## 2. Từ một lớp mang dữ liệu thông thường đến `record`

Xét một giá trị đại diện cho tọa độ hai chiều. Cách viết bằng class thông thường:

```java
import java.util.Objects;

public final class Point {
    private final int x;
    private final int y;

    public Point(int x, int y) {
        this.x = x;
        this.y = y;
    }

    public int x() {
        return x;
    }

    public int y() {
        return y;
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) return true;
        if (!(obj instanceof Point other)) return false;
        return x == other.x && y == other.y;
    }

    @Override
    public int hashCode() {
        return Objects.hash(x, y);
    }

    @Override
    public String toString() {
        return "Point[x=" + x + ", y=" + y + "]";
    }
}
```

Với record, ý tưởng tương ứng được khai báo ngắn gọn:

```java
public record Point(int x, int y) {}
```

Hai đoạn là **hai cách xây dựng kiểu mang dữ liệu có hợp đồng tương tự**, không phải hai khai báo được dùng đồng thời trong cùng dự án. Ở bản record, `x` và `y` là **record components**. Từ chúng, Java cung cấp:

- Các trường lưu trữ dữ liệu tương ứng, là `private final`.
- Canonical constructor nhận các thành phần theo thứ tự `(int x, int y)`.
- Phương thức đọc `x()` và `y()`.
- `equals(Object)`, `hashCode()` và `toString()` dựa trên các thành phần đã khai báo.

Ví dụ sử dụng:

```java
Point a = new Point(3, 5);
Point b = new Point(3, 5);

System.out.println(a.x());       // 3
System.out.println(a.y());       // 5
System.out.println(a.equals(b));  // true
System.out.println(a == b);       // false
System.out.println(a);            // Point[x=3, y=5]
```

Điều quan trọng không chỉ là ít dòng code: phần khai báo `record Point(int x, int y)` đã thể hiện rõ **hai thành phần xác định dữ liệu** của `Point`.

### So sánh nhanh

| Khía cạnh | Class mang dữ liệu thông thường | Record |
|---|---|---|
| Công bố dữ liệu | Tự khai báo field và API | Record header công bố components |
| Constructor | Tự viết | Có canonical constructor, có thể tùy chỉnh |
| Truy cập dữ liệu | Tự định nghĩa, thường `getX()` hoặc `x()` | Accessor mặc định cùng tên component: `x()` |
| So sánh nội dung | Tự viết `equals()`, `hashCode()` nếu cần | Được cung cấp mặc định theo components |
| Biểu diễn chuỗi | Tự viết `toString()` nếu cần | Có `toString()` mặc định |
| Thay đổi trường sau khi tạo | Do tác giả thiết kế; có thể mutable | Không thể gán lại các component fields |
| Kế thừa class khác | Có thể `extends` một class phù hợp | Không được `extends` class tùy ý; ngầm kế thừa `java.lang.Record` |
| Cho class khác kế thừa | Phụ thuộc `final` và thiết kế khác | Bản thân record là `final` |
| Trách nhiệm và hành vi | Linh hoạt, có thể giữ nhiều trạng thái nội bộ | Dùng cho mô hình dữ liệu công khai qua components; vẫn khai báo được phương thức nghiệp vụ |

**Không phải mọi class ít code đều nên trở thành record.** Việc chọn record là một quyết định mô hình dữ liệu và hợp đồng API, không chỉ là thao tác rút ngắn cú pháp.

## 3. Record là class với hợp đồng dữ liệu rõ ràng

Khai báo:

```java
record Book(String isbn, String title, int pages) {}
```

đưa ra ba thành phần theo thứ tự: `isbn`, `title`, `pages`. Các thành phần là một phần công khai của hình dạng record. Đổi tên, đổi thứ tự hoặc đổi kiểu component có thể ảnh hưởng đến constructor, accessor, cách biểu diễn đối tượng và mã gọi từ nơi khác.

### 3.1. Record components và accessor

Mỗi component sinh ra phương thức đọc có **đúng tên component**, không thêm tiền tố `get`:

```java
Book book = new Book("978-1", "Learning Java", 320);
String id = book.isbn();
int length = book.pages();
```

Đây là một khác biệt cần biết nếu chuyển từ JavaBean thông thường sang record. Các thư viện, công cụ serialization hoặc framework có thể dựa vào getter dạng `getIsbn()`, setter hoặc constructor rỗng; khả năng nhận diện record phụ thuộc phiên bản và cách tích hợp cụ thể. Không nên mặc định rằng mọi class mang dữ liệu dùng trong framework đều có thể đổi thành record mà không tác động tới API.

### 3.2. Constructor, `equals`, `hashCode`, `toString`

Với record không khai báo phần thân đặc biệt, trình biên dịch cung cấp canonical constructor nhận toàn bộ components. Java cũng cung cấp `equals`/`hashCode` theo nội dung các components và một dạng `toString` phản ánh tên kiểu, tên thành phần và giá trị.

```java
Book a = new Book("A-1", "Java", 200);
Book b = new Book("A-1", "Java", 200);

System.out.println(a.equals(b));              // true
System.out.println(a.hashCode() == b.hashCode()); // true
System.out.println(a); // Ví dụ: Book[isbn=A-1, title=Java, pages=200]
```

Hai record `a` và `b` có thể là **hai đối tượng khác nhau** nhưng bằng nhau theo nội dung. Vì vậy:

- `equals()` diễn tả quan hệ tương đương theo components.
- `hashCode()` nhất quán với `equals()`; hai record bằng nhau phải có hash code bằng nhau.
- `==` với hai biến tham chiếu đến record vẫn kiểm tra **cùng một đối tượng** hay không.

Record vẫn là object, vẫn có object identity và có thể được sử dụng trong collection hoặc truyền qua phương thức như class khác. Nó **không biến Java thành ngôn ngữ truyền đối tượng theo giá trị**, và cũng không bảo đảm cách lưu trữ trong bộ nhớ khác với class thường.

### 3.3. Record có thể có hành vi

Một record không chỉ là “túi chứa dữ liệu” không có phương thức. Nó có thể cài đặt logic gắn trực tiếp với dữ liệu và triển khai interface:

```java
public record Rectangle(double width, double height) {
    public Rectangle {
        if (!Double.isFinite(width) || !Double.isFinite(height)
                || width < 0 || height < 0) {
            throw new IllegalArgumentException("Invalid dimensions");
        }
    }

    public double area() {
        return width * height;
    }

    public boolean isSquare() {
        return Double.compare(width, height) == 0;
    }
}
```

`area()` và `isSquare()` là **hành vi suy ra từ chính các components**. Đưa những thao tác như vậy vào record thường hợp lý hơn so với việc lưu kết quả như một trạng thái có thể mất đồng bộ.

## 4. “Bất biến” của record: đúng đến đâu?

Record có các trường lưu component là `private final`, nên **không thể gán lại tham chiếu hoặc giá trị component sau khi đối tượng được tạo**. Tuy nhiên, đây là **bất biến nông** (*shallow immutability*), không phải bảo đảm mọi đối tượng nằm bên trong record đều bất biến.

### 4.1. Component là primitive hoặc immutable object

```java
record Temperature(String city, int celsius) {}

Temperature t = new Temperature("Ha Noi", 28);
// t.celsius = 30; // Lỗi: không có field công khai để gán.
// t.celsius(30);   // Lỗi: accessor không phải setter.
```

`String` là kiểu bất biến; `int` là primitive. Với dạng dữ liệu này, record mang lại mô hình giá trị đơn giản, dễ suy luận.

Nếu cần “cập nhật” bản ghi, ta thường tạo một record mới:

```java
Temperature next = new Temperature(t.city(), 30);
```

### 4.2. Component tham chiếu đến đối tượng mutable

Ví dụ sau **không thật sự bất biến sâu**:

```java
import java.util.List;

record Team(String name, List<String> members) {}

List<String> names = new java.util.ArrayList<>();
names.add("An");
Team team = new Team("Core", names);
names.add("Binh");

System.out.println(team.members()); // [An, Binh]
```

Danh sách có thể bị sửa qua biến `names`; record chỉ giữ một tham chiếu `final` đến danh sách đó.

Khi muốn giữ bất biến ở cấp danh sách, tạo bản sao trong constructor:

```java
import java.util.List;
import java.util.Objects;

public record Team(String name, List<String> members) {
    public Team {
        name = Objects.requireNonNull(name, "name").strip();
        if (name.isBlank()) {
            throw new IllegalArgumentException("Name must not be blank");
        }
        members = List.copyOf(Objects.requireNonNull(members, "members"));
    }
}
```

`List.copyOf` tạo danh sách không sửa được qua các phương thức của nó và tách khỏi các thay đổi sau này của danh sách nguồn. Nhưng nếu **phần tử bên trong** là đối tượng mutable, bản sao danh sách vẫn không tự biến các phần tử đó thành bất biến. Cần cân nhắc bản sao phòng vệ thích hợp cho từng loại dữ liệu.

### 4.3. Mảng là một trường hợp dễ nhầm

```java
record Bytes(byte[] data) {}
```

Với record này, người gọi vẫn có thể thay đổi `data` qua mảng nhận về từ accessor, và cách so sánh mặc định của component mảng dựa trên **bằng nhau của tham chiếu mảng**, không phải bằng nhau từng byte. Hai mảng khác nhau có nội dung giống hệt nhau chưa chắc làm hai `Bytes` record bằng nhau.

Trong một API cần bất biến và so sánh theo nội dung mảng, có thể dùng bản sao phòng vệ cho cả constructor và accessor, đồng thời thiết kế `equals`/`hashCode` phù hợp với nội dung, hoặc chọn một kiểu dữ liệu đại diện khác có hợp đồng tương đương rõ ràng.

Đây là ví dụ cho thấy **record không tự giải quyết mọi vấn đề về bất biến và so sánh sâu**. Cần kiểm tra đặc điểm của từng component.

## 5. Kiểm tra dữ liệu ngay khi tạo record

Trong hệ thống thật, một kiểu mang dữ liệu vẫn cần **bảo vệ bất biến nghiệp vụ** (*invariant*): số lượng không âm, mã không rỗng, tiền không âm, ngày kết thúc không trước ngày bắt đầu...

Record hỗ trợ **compact canonical constructor**: cú pháp chỉ có tên record và phần thân, không phải viết lại toàn bộ danh sách tham số. Ta kiểm tra hoặc chuẩn hóa tham số trong thân constructor, rồi Java tự gán những tham số cuối cùng vào các trường tương ứng.

```java
import java.math.BigDecimal;
import java.util.Objects;

public record OrderLine(String sku, int quantity, BigDecimal unitPrice) {
    public OrderLine {
        sku = Objects.requireNonNull(sku, "sku").strip();
        Objects.requireNonNull(unitPrice, "unitPrice");

        if (sku.isEmpty()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        if (unitPrice.signum() < 0) {
            throw new IllegalArgumentException("unitPrice must be non-negative");
        }
    }

    public BigDecimal total() {
        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }
}
```

Ở đây:

1. `OrderLine` công bố ba component `sku`, `quantity`, `unitPrice`.
2. `public OrderLine { ... }` kiểm tra và chuẩn hóa đầu vào. Việc gán lại **tham số** `sku` trước khi constructor kết thúc là hợp lệ; đây không phải thay đổi trường của record sau khi tạo.
3. Java hoàn tất việc gán các tham số vào component fields ở cuối compact constructor.
4. `total()` trả kết quả suy ra từ dữ liệu, không giữ thêm một bản sao của tổng tiền.
5. `BigDecimal` được sử dụng thay cho số thực nhị phân cho giá trị tiền đòi hỏi phép tính thập phân chính xác theo quy tắc miền nghiệp vụ.

Ví dụ:

```java
OrderLine line = new OrderLine("  P-10  ", 3, new BigDecimal("12.50"));
System.out.println(line.sku());   // P-10
System.out.println(line.total()); // 37.50
```

Ngoài compact constructor, record cũng cho phép khai báo canonical constructor tường minh với danh sách tham số đầy đủ. Constructor phụ (nhận bộ tham số khác) phải ủy quyền đến một constructor khác của cùng record bằng `this(...)`, để cuối cùng việc tạo đối tượng đi qua canonical constructor và nhất quán dữ liệu.

```java
record Size(int width, int height) {
    Size(int side) {
        this(side, side);
    }
}
```

## 6. Record được phép và không được phép khai báo gì?

| Đặc điểm | Quy tắc của Java 17 | Ý nghĩa khi thiết kế |
|---|---|---|
| Record là class | Kế thừa ngầm `java.lang.Record` | Dùng được như một object và một kiểu Java thông thường |
| Kế thừa | Record ngầm `final`, không thể `extends` class khác | Không dùng cho hierarchy class cần mở rộng theo kế thừa |
| Interface | Có thể `implements` một hoặc nhiều interface | Phù hợp cho mô hình dữ liệu tham gia vào hợp đồng chung |
| Trường instance | Không được tự khai báo field instance bổ sung ngoài fields của components | Toàn bộ trạng thái instance nằm trong record header |
| Trường `static` | Có thể khai báo trường `static` phù hợp | Dùng hằng số hoặc dữ liệu mức lớp khi có lý do |
| Phương thức | Có thể khai báo instance/static method, override phương thức hợp lệ | Đưa quy tắc gắn chặt với components vào record |
| Constructor | Có canonical/compact constructor và constructor phụ hợp lệ | Xác thực và chuẩn hóa dữ liệu lúc tạo |
| Component fields | Là `private final`; không có setter được sinh | Không gán lại dữ liệu sau khi tạo |
| Record lồng nhau | Nested record ngầm mang tính `static` | Không giữ tham chiếu ngầm tới instance lớp bao ngoài |
| Generic | Có thể khai báo tham số kiểu như `record Pair<A,B>(A first, B second)` | Dùng cho kết quả có kiểu rõ ràng |

Ví dụ record triển khai interface:

```java
interface Priced {
    long priceInCents();
}

record Item(String code, long priceInCents) implements Priced {
    Item {
        if (priceInCents < 0) {
            throw new IllegalArgumentException("price must be non-negative");
        }
    }
}
```

Accessor `priceInCents()` do record tạo ra có thể đáp ứng trực tiếp hợp đồng phương thức của interface. Không cần tự viết lại phương thức chỉ để trả về component.

Record cũng có thể là kiểu con trực tiếp của một **sealed interface** khi kiểu record được phép. Record vốn ngầm `final`, nên nhánh đó được đóng. Đây là sự kết hợp hữu ích khi cần mô hình hóa một nhóm kết quả xác định, nhưng không cần học sealed trước mới hiểu mục đích cơ bản của record.

## 7. Khi nào record là lựa chọn phù hợp?

### 7.1. Những trường hợp thường phù hợp

**Dữ liệu trao đổi giữa các lớp hoặc tầng ứng dụng (DTO):**

```java
record SearchResult(String title, String url, int score) {}
```

Một kết quả tìm kiếm được biểu diễn bằng bộ thành phần rõ ràng, rất thuận tiện để trả về từ hàm hoặc chuyển giữa các lớp. Việc dùng record cho DTO còn tùy thuộc công cụ tuần tự hóa và hợp đồng API đang sử dụng.

**Giá trị gắn với miền nghiệp vụ:**

```java
record DateRange(java.time.LocalDate from, java.time.LocalDate to) {
    DateRange {
        if (from == null || to == null || to.isBefore(from)) {
            throw new IllegalArgumentException("Invalid date range");
        }
    }
}
```

Những thành phần được kiểm tra ngay từ đầu, giúp tránh tạo một khoảng ngày không hợp lệ.

**Giá trị trả về có nhiều phần:**

```java
record CountAndTotal(long count, long total) {}
```

Thay vì dùng mảng với ý nghĩa khó đoán của chỉ số 0 và 1, kết quả có tên component minh bạch.

**Dữ liệu đầu vào cho một thao tác:**

```java
record CreateUserCommand(String email, String displayName) {}
```

Record truyền dữ liệu của một yêu cầu rõ ràng, sau đó tầng nghiệp vụ xử lý và trả kết quả. Dùng record không loại bỏ nhu cầu kiểm tra tính hợp lệ hoặc phân quyền ở tầng thích hợp.

### 7.2. Những trường hợp class thông thường thường hợp lý hơn

**Đối tượng có vòng đời và trạng thái thay đổi:** tài khoản có số dư liên tục biến đổi, giỏ hàng thêm/bớt phần tử, tiến trình có trạng thái thay đổi theo hành động. Một class bao đóng state và các phép chuyển trạng thái có thể truyền đạt thiết kế tốt hơn.

**Đối tượng có danh tính độc lập với toàn bộ thuộc tính:** hai thực thể có cùng tên và ngày sinh chưa chắc là cùng một người dùng; hai đơn hàng có cùng các trường hiển thị chưa chắc là cùng đơn hàng. Khi bình đẳng theo ID hoặc danh tính là phần cốt lõi, không nên áp dụng máy móc `equals()` dựa trên tất cả components của record.

**Framework yêu cầu hình dạng lớp khác:** một số cơ chế ORM/entity, proxy, lazy loading hoặc công cụ binding có thể cần class có thể kế thừa, constructor đặc biệt hoặc các trường mutable. Ví dụ, entity JPA thường có vòng đời, định danh và yêu cầu framework không phù hợp với giới hạn `final`/constructor/components của record. Record có thể phù hợp hơn cho projection hoặc DTO, tùy framework và phiên bản.

**Mô hình cần kế thừa từ class khác hoặc giữ state ẩn bổ sung:** record không được extends một lớp tùy ý và không có field instance ngoài components. Nếu kiểu phải chứa cache per-instance, state nội bộ không công bố hoặc tham gia vào class hierarchy cụ thể, class thường có thể chính xác hơn.

Một quy tắc thiết kế hữu ích: nếu người dùng kiểu cần quan tâm **bộ dữ liệu được công bố** hơn là **danh tính và vòng đời của một đối tượng**, hãy cân nhắc record. Nếu đối tượng cần duy trì trạng thái qua chuỗi hành động, class thường là lựa chọn tự nhiên hơn.

## 8. Record và các cách mang dữ liệu khác

| Cách biểu diễn | Ưu điểm | Giới hạn hoặc điểm cần cân nhắc |
|---|---|---|
| `record UserId(long value)` | Diễn đạt một giá trị có tên kiểu rõ ràng; có so sánh theo component | Cần validation khi giá trị có điều kiện nghiệp vụ |
| `final class UserId` với trường và API thủ công | Toàn quyền quyết định trạng thái, equality và API | Phải viết/bảo trì code lặp nếu chỉ mang dữ liệu |
| `Map<String, Object>` | Linh hoạt với cấu trúc động | Dễ sai khóa, mất kiểm tra kiểu ở compile time, khó mô tả contract |
| `Object[]` hoặc mảng nhiều vị trí | Cú pháp đơn giản cho dữ liệu rất ngắn | Ý nghĩa từng vị trí mơ hồ; ép kiểu và phát hiện lỗi khó hơn |
| `enum` | Đại diện tập hằng số hữu hạn với logic liên quan | Không tạo một tập giá trị mang dữ liệu tùy ý như record |

Ví dụ nhận diện:

```java
record UserId(long value) {
    UserId {
        if (value <= 0) throw new IllegalArgumentException("Invalid user ID");
    }
}
```

`UserId` cung cấp một kiểu dữ liệu có nghĩa riêng thay vì truyền `long` không rõ vai trò khắp chương trình. Tuy nhiên, việc có record **không tự đảm bảo thiết kế miền đúng**; người viết vẫn phải quy định giá trị hợp lệ, cách xử lý null và ý nghĩa equality.

## 9. Chuyển class cũ sang record: cần xem gì?

Giả sử dự án có lớp:

```java
public final class CustomerData {
    private final String name;
    private final int tier;

    public CustomerData(String name, int tier) {
        this.name = name;
        this.tier = tier;
    }

    public String getName() {
        return name;
    }

    public int getTier() {
        return tier;
    }
}
```

Cách viết ngắn bằng record:

```java
public record CustomerData(String name, int tier) {}
```

Nhưng thay thế trực tiếp có thể làm thay đổi hành vi hợp đồng:

1. **Tên accessor:** `getName()`/`getTier()` trong class trở thành `name()`/`tier()` theo mặc định. Nếu cần duy trì API, record có thể khai báo thêm phương thức tương thích, hoặc giữ class cũ.
2. **Equality:** class ở trên mặc định dùng `Object.equals()` theo danh tính; record mới so sánh theo các components. Điều này có thể ảnh hưởng `HashSet`, `HashMap`, test và logic nghiệp vụ.
3. **Chuỗi hiển thị:** `toString()` của record khác `Object.toString()` hoặc format đã tự định nghĩa ở class.
4. **Dạng constructor và reflection:** canonical constructor và record components là phần của cấu trúc record. Framework dựa vào constructor rỗng, setter hoặc JavaBean property có thể phải điều chỉnh.
5. **Yêu cầu trạng thái:** nếu class có những field không xuất hiện trong record header, record mới không còn giữ được state giống cũ.
6. **Tương thích API lâu dài:** thêm, đổi tên hoặc đổi thứ tự record component có thể ảnh hưởng đến lời gọi constructor và cách bên ngoài đọc dữ liệu. Hãy coi record header là hợp đồng được công khai.

Vì vậy, hãy chuyển sang record khi **ngữ nghĩa của kiểu** thực sự phù hợp, đồng thời đã xác định những API nào cần giữ nguyên.

## 10. Ví dụ tích hợp chạy trên Java 17

Ví dụ sau giữ một danh sách sản phẩm nhỏ và dùng record để biểu diễn dữ liệu sản phẩm. Dữ liệu được chuẩn hóa và kiểm tra ở constructor; khi muốn đổi số lượng, chương trình tạo record mới.

Lưu thành `Main.java`:

```java
import java.util.List;
import java.util.Objects;

public class Main {
    record Product(String sku, int stock) {
        Product {
            sku = Objects.requireNonNull(sku, "sku").strip();
            if (sku.isEmpty()) {
                throw new IllegalArgumentException("sku must not be blank");
            }
            if (stock < 0) {
                throw new IllegalArgumentException("stock must be non-negative");
            }
        }

        boolean inStock() {
            return stock > 0;
        }

        Product withStock(int newStock) {
            return new Product(sku, newStock);
        }
    }

    public static void main(String[] args) {
        Product first = new Product("  SKU-01  ", 5);
        Product same = new Product("SKU-01", 5);
        Product updated = first.withStock(3);

        System.out.println(first.sku());
        System.out.println(first.equals(same));
        System.out.println(first);
        System.out.println(updated);

        List<Product> products = List.of(first, new Product("SKU-02", 0));
        long available = products.stream()
                .filter(Product::inStock)
                .count();
        System.out.println("Available: " + available);
    }
}
```

Biên dịch/chạy bằng JDK 17:

```bash
javac --release 17 -encoding UTF-8 Main.java
java Main
```

Kết quả minh họa:

```text
SKU-01
true
Product[sku=SKU-01, stock=5]
Product[sku=SKU-01, stock=3]
Available: 1
```

Ví dụ biểu diễn những ý chính:

- `Product` là một **nested record** trong `Main`, nên không cần tạo file `Product.java` riêng cho ví dụ.
- `sku` được chuẩn hóa trong compact constructor, các giá trị không hợp lệ bị từ chối.
- `first.equals(same)` trả về `true` vì hai record có cùng components, dù là hai object khác nhau.
- `withStock` tạo `Product` mới; không sửa đối tượng `first`.
- `Product::inStock` dùng phương thức nghiệp vụ của record để lọc một `List<Product>`.

Đối với dự án nhiều lớp, có thể tách `Product` thành record top-level `public record Product(...)` trong file `Product.java` của package phù hợp.

## 11. Những hiểu lầm cần tránh

### “Record chỉ là cách viết ngắn của class; không khác về thiết kế”

Record có **cam kết về dữ liệu công bố** qua components và những phương thức sinh tự động, đồng thời có giới hạn về state và kế thừa. Nó gợi ý rằng ý nghĩa của đối tượng nằm ở bộ thành phần dữ liệu. Class thông thường có thể che giấu chi tiết triển khai và thay đổi state theo nhiều cách khác.

### “Record luôn bất biến sâu”

Các component fields là `final`, nhưng `List`, mảng và object mutable bên trong vẫn có thể thay đổi. Nếu cần bất biến sâu, phải thiết kế và sao chép phòng vệ tương ứng.

### “Record không thể có method hoặc constructor”

Record có thể khai báo phương thức, static member, compact/canonical constructor và constructor phụ hợp lệ. Điều bị giới hạn là **mô hình trạng thái instance** và **quan hệ kế thừa class**, không phải khả năng viết mọi logic.

### “`equals` của record giúp so sánh sâu mọi loại dữ liệu”

Record so sánh components theo quy tắc của từng kiểu. Với component mảng, bình đẳng mặc định là tham chiếu mảng; đối tượng mutable bên trong cũng có thể khiến kết quả hash/equality thay đổi theo thời gian. Cần chọn components có ngữ nghĩa bình đẳng ổn định.

### “Record là entity mặc định tốt nhất trong mọi dự án”

Entity thường cần identity, trạng thái thay đổi và các yêu cầu từ persistence framework. Record thường thuận tiện cho **DTO, kết quả tính toán, giá trị mang ý nghĩa rõ ràng hoặc snapshot**; lựa chọn cụ thể tùy kiến trúc và công cụ.

### “Record là tính năng preview của Java 17”

Không đúng. Record đã là tính năng ổn định trong Java 16, có sẵn trong Java 17. Các ví dụ trong bài chỉ dùng những tính năng ổn định của Java 17.

## 12. Bài luyện tập tự áp dụng

### Bài 1: Chọn class hay record

Đọc bốn nhu cầu:

1. Dữ liệu biểu diễn tọa độ `(latitude, longitude)`, được tạo rồi truyền qua nhiều phương thức.
2. Đối tượng giỏ hàng có thể thêm, xóa món và tính lại khuyến mại theo từng sự kiện.
3. Kết quả thống kê `(count, average)` trả về từ một hàm.
4. Đối tượng người dùng có ID và nhiều thuộc tính hồ sơ có thể thay đổi; identity quyết định cùng một người dùng.

**Gợi ý:** (1) và (3) thường phù hợp record; (2) và (4) thường hợp lý hơn với class có mô hình nghiệp vụ/identity rõ ràng. Khi chọn, cần trình bày tại sao dữ liệu là **giá trị** hay **thực thể có vòng đời**.

### Bài 2: Bảo vệ bất biến nông

Hãy thiết kế `record Course(String code, List<String> tags)` sao cho:

- `code` không được null hoặc chỉ toàn khoảng trắng.
- `tags` không được null và sau khi tạo không thể sửa thông qua danh sách gốc hoặc accessor.
- Có phương thức `hasTag(String tag)` kiểm tra một tag có tồn tại không.

Gợi ý dùng compact constructor, `Objects.requireNonNull`, `String.strip()` và `List.copyOf`. Tự giải thích vì sao các tag ở đây nên là `String` (một kiểu bất biến) nếu muốn tránh thay đổi trạng thái qua phần tử.

### Bài 3: Dự đoán equality

```java
record Id(long value) {}
record Bag(int[] values) {}

Id a = new Id(10);
Id b = new Id(10);
Bag x = new Bag(new int[] {1, 2});
Bag y = new Bag(new int[] {1, 2});
```

Hãy xác định kết quả của `a.equals(b)`, `a == b`, `x.equals(y)`; lý giải bằng **record components**, **object identity** và đặc điểm **array equality**.

Đáp án: `true`, `false`, `false`. Hai `Id` có cùng component primitive; `a` và `b` là tham chiếu đến hai object khác nhau; hai `Bag` chứa hai mảng khác tham chiếu.

### Bài 4: Thêm một quy tắc vào record

Tạo `record Money(String currency, long minorUnits)`, kiểm tra currency không trắng và minorUnits không âm; thêm phương thức `add(Money other)` trả về bản ghi mới nếu cùng currency. Nếu khác currency, báo `IllegalArgumentException`. Đặt ví dụ cho số tiền bằng 0, lỗi currency và trường hợp cộng có thể tràn `long` (gợi ý `Math.addExact`).

Bài này giúp thực hành **data contract**, validation, hành vi nghiệp vụ và tạo giá trị mới mà không cần setter.

## 13. Tiêu chí nắm vững bài

Người học hiểu được vai trò của record khi có thể:

1. Giải thích vì sao Java cung cấp record cho các kiểu mang dữ liệu và vì sao record vẫn là class.
2. Viết được record với nhiều components, khởi tạo bằng canonical constructor, gọi accessor và giải thích `equals`/`hashCode`/`toString` mặc định.
3. Chuyển một class dữ liệu đơn giản thành record và nêu các khác biệt có thể ảnh hưởng API.
4. Viết compact constructor để xác thực, chuẩn hóa dữ liệu trước khi đối tượng được tạo.
5. Phân biệt **final component field** với **bất biến sâu**, xử lý được ví dụ collection/mảng mutable.
6. Chọn record cho DTO/giá trị phù hợp và chọn class khi cần lifecycle, identity hoặc trạng thái ẩn.
7. Viết và chạy được ví dụ bằng JDK 17 mà không cần bật preview.

### Tài liệu chính thức để tham khảo

- [Java Language Specification, Java SE 17 — Record Classes (JLS §8.10)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): cú pháp và các quy tắc của record.
- [Java SE 17 API — `java.lang.Record`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html): lớp cha chung của các record.
- [OpenJDK JEP 395 — Records](https://openjdk.org/jeps/395): mục tiêu thiết kế và trạng thái chuẩn hóa của tính năng.

Record giúp ngôn ngữ Java diễn đạt một nhóm dữ liệu cố định một cách rõ ràng. Chọn record khi **bản thân dữ liệu công khai là hợp đồng của kiểu**; chọn class thường khi hệ thống cần một mô hình đối tượng có trạng thái, danh tính hoặc kế thừa không phù hợp với giới hạn của record.
