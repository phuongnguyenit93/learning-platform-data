# Phương thức đối tượng bổ sung cho hành vi gắn với dữ liệu trong `record` (Java hiện đại)

## 1. Vì sao `record` vẫn cần phương thức đối tượng?

`record` biểu diễn một **bộ dữ liệu có các thành phần được khai báo rõ ràng** (*record components*). Khi dữ liệu cần được diễn giải, kiểm tra, tính toán hoặc tạo ra giá trị mới dựa trên trạng thái hiện có, ta có thể khai báo **phương thức đối tượng** (*instance method*) trực tiếp trong thân `record`. Nhờ đó hành vi liên quan đến dữ liệu được đặt bên cạnh dữ liệu mà nó sử dụng.

Ví dụ đơn giản:

```java
record Rectangle(int width, int height) {
    long area() {
        return (long) width * height;
    }

    boolean isSquare() {
        return width == height;
    }
}
```

Đây là khai báo `record` hoàn chỉnh, nhưng chưa phải chương trình có `main`. Hai phương thức `area()` và `isSquare()` được gọi trên **một instance** của `Rectangle`:

```java
Rectangle shape = new Rectangle(4, 6);
System.out.println(shape.area());     // 24
System.out.println(shape.isSquare()); // false
```

Đoạn sử dụng nằm trong một phương thức Java có thể truy cập `Rectangle`.

- `width` và `height` là **thành phần lưu trữ trạng thái**; Java tự tạo trường `private final`, constructor chuẩn và các accessor `width()`/`height()` tương ứng.
- `area()` và `isSquare()` là **hành vi bổ sung**. Chúng được khai báo bởi người lập trình; Java không tự sinh các phương thức nghiệp vụ này.
- Giá trị diện tích là **dữ liệu suy ra** (*derived value*). Ta tính từ `width` và `height` khi cần, thay vì phải khai báo thêm trường lưu diện tích.
- Phương thức có thể dùng trực tiếp tên thành phần bên trong thân record; từ bên ngoài phải gọi accessor như `shape.width()`.

**Trạng thái phiên bản:** Record xuất hiện ở Java 14 dưới dạng preview, trở thành tính năng chuẩn từ Java 16 và được dùng bình thường trên JDK 17, 21 và những phiên bản mới hơn. Tất cả ví dụ trong bài dùng cú pháp ổn định; không cần `--enable-preview`.

## 2. Cấu trúc một record có thêm hành vi

Mẫu tổng quát:

```java
record RecordName(TypeA first, TypeB second) {
    // Tùy chọn: kiểm tra và chuẩn hóa đầu vào.
    RecordName {
        // validate / normalize first, second
    }

    // Phương thức đối tượng: truy cập trạng thái của instance.
    ReturnType calculate() {
        // return kết quả tính từ first và second
    }

    // Phương thức static: thao tác qua tên kiểu, không có this.
    static RecordName factory(TypeA first, TypeB second) {
        return new RecordName(first, second);
    }
}
```

Đây là **khung cú pháp minh họa**: `TypeA`, `TypeB` và `ReturnType` cần được thay bằng kiểu Java thực tế; bình luận trong constructor không thiết lập quy tắc kiểm tra cụ thể.

Một `record` có thể khai báo:

- Constructor chuẩn (*canonical constructor*) hoặc compact constructor để kiểm tra/chuẩn hóa các thành phần.
- Phương thức đối tượng thông thường, có tham số, có giá trị trả về, ném ngoại lệ, overload và dùng các modifier thích hợp như `public`, `private`.
- Phương thức `static`, hằng `static final`, lớp hoặc interface lồng nhau và việc triển khai interface.
- Phương thức override được phép như `toString()`, `equals(Object)`, `hashCode()` hoặc accessor thành phần khi có lý do rõ ràng. Với trường hợp bình thường, nên để các phương thức được sinh giữ ngữ nghĩa record.

Nhưng `record` **không cho phép khai báo thêm trường instance** ngoài các trường được sinh từ header; không có instance initializer; nó ngầm `final` và mở rộng từ `java.lang.Record` nên không thể kế thừa một lớp khác. Các phương thức vẫn có thể phức tạp, nhưng **không làm record trở thành một lớp có bộ nhớ trạng thái instance tùy ý**.

## 3. Dùng thành phần và accessor trong phương thức đối tượng

Xét record đại diện cho một dòng đơn hàng:

```java
record OrderLine(String sku, int quantity, long unitPriceVnd) {
    long totalVnd() {
        return Math.multiplyExact(unitPriceVnd, quantity);
    }

    String summary() {
        return sku + " / " + quantity + " / " + totalVnd();
    }
}
```

Đây là một record hoàn chỉnh về cú pháp; ví dụ chưa có kiểm tra dữ liệu nên dành cho mục đích mô tả truy cập thành phần. Khi gọi `new OrderLine("BOOK", 2, 50_000).totalVnd()`, kết quả là `100000`.

Trong thân record:

- `sku`, `quantity` và `unitPriceVnd` là các trường của instance hiện tại và có thể được đọc trực tiếp.
- Có thể viết `this.sku` hoặc `this.quantity()` để làm rõ ý định; đối với việc đọc component trong record, dùng tên trường hoặc accessor đều được.
- Từ bên ngoài, các trường instance tương ứng có quyền truy cập `private`; phải dùng `line.sku()`, `line.quantity()`, `line.unitPriceVnd()`.
- `summary()` có thể gọi `totalVnd()` như một phương thức instance khác, giúp tránh lặp công thức tính toán.

`Math.multiplyExact(long, long)` được dùng để **phát hiện tràn số**: với hai giá trị hợp lệ riêng rẽ nhưng tích vượt phạm vi `long`, Java ném `ArithmeticException`. Đây là một lựa chọn thích hợp khi kết quả tiền/đơn vị đếm không được phép âm thầm tràn số; khi ứng dụng cần số vượt phạm vi `long` hoặc tính thuế/đơn vị tiền tệ phức tạp, cần chọn kiểu và chính sách tính phù hợp, chẳng hạn `BigDecimal`.

## 4. Ví dụ hoàn chỉnh Java 17+: hành vi gắn với dữ liệu

Chương trình sau dùng một record có validation, phương thức tính toán, truy vấn điều kiện, định dạng mô tả, phương thức tạo instance mới, hằng và factory static. Record đồng thời triển khai một interface để cho phép gọi hành vi qua hợp đồng chung.

**Tệp `Main.java`:**

```java
import java.util.Objects;

public class Main {
    interface Billable {
        long totalVnd();
    }

    record OrderLine(String sku, int quantity, long unitPriceVnd)
            implements Billable {
        private static final int BULK_THRESHOLD = 10;

        OrderLine {
            sku = Objects.requireNonNull(sku, "sku").strip();
            if (sku.isEmpty()) {
                throw new IllegalArgumentException("SKU must not be blank");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException("Quantity must be positive");
            }
            if (unitPriceVnd < 0) {
                throw new IllegalArgumentException("Price must not be negative");
            }
        }

        @Override
        public long totalVnd() {
            return Math.multiplyExact(unitPriceVnd, quantity);
        }

        public boolean isBulk() {
            return quantity >= BULK_THRESHOLD;
        }

        public OrderLine withQuantity(int newQuantity) {
            return new OrderLine(sku, newQuantity, unitPriceVnd);
        }

        public String description() {
            return sku + ": " + quantity + " x " + unitPriceVnd
                    + " = " + totalVnd() + " VND";
        }

        public static OrderLine gift(String sku) {
            return new OrderLine(sku, 1, 0);
        }
    }

    public static void main(String[] args) {
        OrderLine line = new OrderLine("  JDK-21  ", 3, 120_000);
        System.out.println(line.sku());
        System.out.println(line.totalVnd());
        System.out.println(line.isBulk());
        System.out.println(line.description());

        OrderLine larger = line.withQuantity(12);
        System.out.println(line.quantity());
        System.out.println(larger.totalVnd());
        System.out.println(larger.isBulk());
        System.out.println(line.equals(larger));

        OrderLine same = new OrderLine("JDK-21", 3, 120_000);
        System.out.println(line.equals(same));

        Billable bill = larger;
        System.out.println(bill.totalVnd());

        System.out.println(OrderLine.gift("GIFT").totalVnd());
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 Main.java
java Main
```

**Stdout chính xác:**

```text
JDK-21
360000
false
JDK-21: 3 x 120000 = 360000 VND
3
1440000
true
false
true
1440000
0
```

Chương trình được viết để chạy độc lập. `OrderLine` và `Billable` là các kiểu lồng trong `Main`; dùng `record` lồng như vậy vẫn hoàn toàn hợp lệ.

### Phân tích các phương thức

**`totalVnd()` — tính giá trị từ các component**

`3 × 120000 = 360000`. Phương thức có thể gọi nhiều lần mà không cần trường `total` lưu sẵn. Vì `unitPriceVnd` và `quantity` là các trường final của record, kết quả này không thay đổi với cùng một instance khi các component là kiểu nguyên thủy. Lựa chọn `Math.multiplyExact` giúp phát hiện phép tính không biểu diễn được bằng `long`.

**`isBulk()` — diễn đạt điều kiện nghiệp vụ**

Điều kiện số lượng từ `10` trở lên được đặt trong một phương thức có tên rõ nghĩa. `line.isBulk()` là `false` khi `quantity = 3`, còn `larger.isBulk()` là `true` khi `quantity = 12`. Hằng `BULK_THRESHOLD` là `static final`, dùng chung cho kiểu record, không trở thành component, không xuất hiện trong constructor và không tham gia equality của record.

**`description()` — trình bày dữ liệu**

Phương thức sử dụng các component và tái sử dụng `totalVnd()` để tạo một mô tả đọc được. Đây là định dạng dành cho ví dụ; trong ứng dụng lớn, nếu trình bày phụ thuộc locale/ngôn ngữ hoặc cách xuất JSON, nên đặt nhiệm vụ định dạng phức tạp ở lớp phù hợp thay vì nhồi mọi việc vào record.

**`withQuantity(int)` — tạo giá trị mới, giữ bản gốc**

`line.withQuantity(12)` tạo **một `OrderLine` mới**. Constructor được chạy lại nên các invariant được kiểm tra. Instance `line` vẫn có `quantity = 3`, còn `larger` có `quantity = 12` và tổng tiền mới `1440000`. Hai record không bằng nhau vì component `quantity` khác nhau.

**`gift(String)` — factory `static`**

Đây là phương thức gọi trên **tên kiểu** `OrderLine.gift("GIFT")`, tạo một dòng hàng có số lượng `1` và đơn giá `0`. Vì là `static`, nó không dùng `this` và không đọc trực tiếp trạng thái của một instance cụ thể. Giá trị trả về vẫn phải qua constructor và validation như những cách tạo khác.

**`implements Billable` — thực thi interface**

`totalVnd()` có quyền truy cập `public` vì phương thức interface cũng là `public`. Sau khi gán `Billable bill = larger`, có thể gọi `bill.totalVnd()` mà không cần biết lớp triển khai cụ thể. Record được ngầm `final` nhưng **vẫn triển khai interface bình thường**.

## 5. Khác biệt quan trọng: hành vi tính toán và trạng thái lưu trữ

Có thể bổ sung bao nhiêu phương thức hợp lý tùy mục đích, nhưng **không thể bổ sung một trường instance mới** để ghi nhớ kết quả tính:

```java
// Cố ý sai: record không cho phép trường instance khai báo thêm.
record InvalidRectangle(int width, int height) {
    private long cachedArea; // Lỗi biên dịch.
}
```

Đây là mã cố ý sai để minh họa quy tắc. Record chỉ có các trường instance tương ứng với component được liệt kê ở header. Nếu cần `area`, hãy tính trong một phương thức:

```java
record Rectangle(int width, int height) {
    Rectangle {
        if (width < 0 || height < 0) {
            throw new IllegalArgumentException("Negative dimension");
        }
    }

    long area() {
        return (long) width * height;
    }
}
```

Nếu kết quả suy ra đắt đỏ và phải cache theo từng instance, cần xem lại mô hình: một lớp thông thường hoặc cache ngoài với chính sách rõ ràng có thể phù hợp hơn. Không cố lách bằng trường `static`, vì `static` được chia sẻ ở cấp kiểu, không giữ giá trị riêng cho mỗi đối tượng.

### Phương thức có thể trả đối tượng mới

Để thể hiện một phép biến đổi giá trị:

```java
record Point(int x, int y) {
    Point moveBy(int dx, int dy) {
        return new Point(
                Math.addExact(x, dx),
                Math.addExact(y, dy)
        );
    }
}
```

Ví dụ:

```java
Point oldPoint = new Point(2, 5);
Point newPoint = oldPoint.moveBy(3, -2);

System.out.println(oldPoint); // Point[x=2, y=5]
System.out.println(newPoint); // Point[x=5, y=3]
```

Đây là các đoạn mã riêng đặt trong ngữ cảnh thích hợp, không thay thế chương trình `Main.java` ở trên. `moveBy` trả **một record mới**, không sửa `oldPoint`. Các thành phần `x`, `y` của record có trường `final` và không có setter tự sinh.

### Không hiểu "record bất biến" là "mọi hành vi đều thuần túy"

Các component của record có trường `final`, nhưng Java **không cấm phương thức của record thực hiện I/O, thay đổi trạng thái tĩnh, hay gọi phương thức trên một đối tượng mutable mà component trỏ tới**. Chẳng hạn:

```java
record CounterView(StringBuilder builder) {
    void append(String suffix) {
        builder.append(suffix);
    }
}
```

Đây là mã Java hợp lệ, nhưng `StringBuilder` **mutable**: gọi `append` làm nội dung builder thay đổi dù tham chiếu component là final. Vì vậy record chỉ cung cấp **bất biến nông** (*shallow immutability*). Nếu thiết kế record cần thực sự mang ngữ nghĩa giá trị ổn định, nên chọn các component bất biến hoặc sao chép phòng vệ đúng cách.

## 6. Phương thức và invariant trong compact constructor

Phương thức đối tượng có thể giả định rằng các invariant đã được constructor kiểm tra trước khi instance được dùng bình thường:

```java
record Distance(int kilometers) {
    Distance {
        if (kilometers < 0) {
            throw new IllegalArgumentException("Distance cannot be negative");
        }
    }

    boolean isLongTrip() {
        return kilometers >= 100;
    }

    Distance plus(Distance other) {
        java.util.Objects.requireNonNull(other, "other");
        return new Distance(Math.addExact(kilometers, other.kilometers));
    }
}
```

Đây là một khai báo record độc lập. Vì constructor không cho tạo `Distance` âm, `isLongTrip()` chỉ cần xử lý dữ liệu hợp lệ. `plus` tạo một giá trị mới, gọi constructor để bảo toàn invariant, và dùng `Math.addExact` để không âm thầm tràn số.

**Lưu ý đặc thù compact constructor:** trong khối `Distance { ... }`, các trường component chưa được Java gán từ tham số constructor cho đến khi khối kết thúc thành công. Khi kiểm tra/chuẩn hóa, sử dụng trực tiếp các **tham số** `kilometers`; không gọi một instance method dựa trên component đang chờ gán rồi giả định nó đã có giá trị đầu vào. Sau khi construction hoàn tất, phương thức đối tượng đọc trạng thái đã được xác lập.

Khi cần chuẩn hóa chuỗi:

```java
record Code(String value) {
    Code {
        value = java.util.Objects.requireNonNull(value, "value").strip();
        if (value.isEmpty()) {
            throw new IllegalArgumentException("Blank code");
        }
    }

    boolean startsWithJ() {
        return value.startsWith("J");
    }
}
```

`new Code("  J17  ").startsWithJ()` cho kết quả `true` và accessor `value()` trả `"J17"`. Việc gán lại tham số `value` trong compact constructor làm giá trị **được lưu** là bản đã chuẩn hóa.

## 7. Phương thức record và `equals`/`hashCode`/`toString`

Bên cạnh constructor và accessor, Java tự cung cấp `equals(Object)`, `hashCode()` và `toString()` dựa trên các record component (nếu người lập trình không override).

```java
record Product(String code, long priceVnd) {
    boolean isFree() {
        return priceVnd == 0;
    }
}
```

`new Product("A", 0)` và một instance `new Product("A", 0)` khác **bằng nhau theo `equals`**, vì các component bằng nhau. Phương thức `isFree()` **không phải component** nên không trực tiếp tham gia phép so sánh. Trường hợp này hợp lý vì `isFree()` là kết quả suy ra hoàn toàn từ `priceVnd`.

Nếu thay đổi code của `isFree()`, cách record được tạo và các thành phần dùng để so sánh **không tự thay đổi**. Nếu thêm một component mới vào header, ngược lại, constructor, accessor và equality mặc định có thể bị ảnh hưởng; đây là thay đổi hợp đồng dữ liệu cần xem xét.

Đôi khi có lý do override `toString()` để kiểm soát dữ liệu được trình bày, hoặc override `equals` và `hashCode` theo quy tắc miền đặc biệt. Nhưng khi đó phải duy trì hợp đồng equality, tính nhất quán với component và các yêu cầu của record. Với đối tượng chỉ biểu diễn một bộ dữ liệu, **giữ mặc định thường rõ ràng và ít lỗi hơn**.

## 8. Phương thức instance so với phương thức `static`

| Câu hỏi | Phương thức đối tượng | Phương thức `static` |
| --- | --- | --- |
| Gọi như thế nào? | `line.totalVnd()` | `OrderLine.gift("GIFT")` |
| Có `this` không? | Có | Không |
| Có thể đọc component của instance hiện tại trực tiếp không? | Có | Không, trừ khi nhận instance làm tham số |
| Dùng cho việc gì? | Tính toán, kiểm tra, biến đổi dựa trên trạng thái của đối tượng | Factory, tiện ích độc lập, logic áp dụng chung cho kiểu |
| Có tự trở thành record component không? | Không | Không |

Ví dụ về helper tĩnh hoạt động với dữ liệu được truyền vào:

```java
record Pair(int left, int right) {
    int sum() {
        return Math.addExact(left, right);
    }

    static Pair zeros() {
        return new Pair(0, 0);
    }
}
```

`new Pair(1, 2).sum()` trả `3`; `Pair.zeros().sum()` trả `0`. Không thể viết `static int sum() { return left + right; }` mà không có đối tượng cụ thể, vì `left` và `right` là trạng thái instance.

**Chọn phương thức đối tượng** khi logic có ý nghĩa trực tiếp trên trạng thái record và việc gọi `object.method()` truyền đạt rõ ý định. Chọn static khi tạo instance hoặc tính toán không gắn với một đối tượng hiện có.

## 9. Áp dụng interface và kiểm soát mức truy cập

Record có thể implement interface, bao gồm interface khai báo phương thức hành vi:

```java
interface HasArea {
    long area();
}

record Box(int width, int height) implements HasArea {
    Box {
        if (width < 0 || height < 0) {
            throw new IllegalArgumentException("Dimensions must be non-negative");
        }
    }

    @Override
    public long area() {
        return (long) width * height;
    }
}
```

Đây là hai khai báo kiểu; để chạy cần đặt ở nơi hợp lệ trong tệp Java hoặc trong lớp chứa.

`@Override` giúp trình biên dịch kiểm tra đúng chữ ký; phương thức thực hiện phương thức interface phải là `public`. Record có thể triển khai **nhiều interface**, nhưng vẫn không thể `extends` một class tự chọn hoặc tạo subclass của chính record (vì record `final`).

Các phương thức bổ trợ không nằm trong API công khai có thể khai báo `private`:

```java
record EmailLabel(String value) {
    String masked() {
        return value.length() <= 3 ? "***" : firstThree() + "***";
    }

    private String firstThree() {
        return value.substring(0, 3);
    }
}
```

`masked()` là phương thức instance dùng helper `private firstThree()`. Đây là ví dụ minh họa về cách tổ chức, chưa có validation cho `value` và không nên dùng quy tắc che dữ liệu ví dụ làm biện pháp bảo mật thật. Nếu ứng dụng cần ẩn dữ liệu nhạy cảm, hãy áp dụng chính sách bảo mật và kiểm tra riêng.

## 10. Tình huống cần đặc biệt chú ý

### 10.1 Không cố viết setter như lớp dữ liệu mutable

Mã sau **cố ý sai**:

```java
record Counter(int value) {
    void setValue(int value) {
        this.value = value; // Lỗi: trường component là final.
    }
}
```

Muốn cập nhật kiểu giá trị, trả về record mới:

```java
record Counter(int value) {
    Counter increment() {
        return new Counter(Math.addExact(value, 1));
    }
}
```

`increment()` tạo giá trị mới; instance cũ vẫn giữ `value` ban đầu.

### 10.2 Không thêm trường cache cấp instance

`record Item(int price) { private int cachedTax; }` **không hợp lệ** vì record không cho khai báo trường instance bổ sung. Nếu bài toán thực sự yêu cầu trạng thái cache, xem xét mô hình khác hoặc cache ngoài với quy tắc rõ ràng. Không thêm một thành phần vào header chỉ để lách vấn đề mà không muốn nó trở thành phần dữ liệu công khai và equality.

### 10.3 Đừng nhầm accessor với JavaBean getter

Record `record User(String name) {}` sinh phương thức `name()`. Nó **không tự sinh** `getName()`. Nếu framework cụ thể dựa vào quy ước JavaBean cũ, cần kiểm tra phiên bản và hỗ trợ record/constructor binding thực tế. Có thể viết phương thức `getName()` bổ sung khi thật sự cần:

```java
record User(String name) {
    String getName() {
        return name;
    }
}
```

Nhưng thêm getter dự phòng cho mọi record không phải quy tắc bắt buộc; với API hiện đại đã hỗ trợ record, accessor `name()` thường là đủ.

### 10.4 Validation và tràn số

Phương thức có thể ném ngoại lệ trong khi constructor vẫn tạo thành công record. Trong `Main.java`, `totalVnd()` dùng `Math.multiplyExact`; nếu tích của đơn giá và số lượng vượt `Long.MAX_VALUE`, nó ném `ArithmeticException`. Tùy yêu cầu, có thể kiểm tra tích ngay lúc xây dựng record hoặc chấp nhận phát hiện tại thời điểm tính, nhưng phải mô tả rõ hợp đồng và có test.

### 10.5 Không coi "record có phương thức" là entity mutable

Record phù hợp với **giá trị** và ảnh chụp dữ liệu, dù có nhiều phương thức. Nếu đối tượng cần danh tính ổn định, vòng đời dài, thay đổi trạng thái liên tục, framework yêu cầu constructor không tham số hoặc có các thuộc tính mutable, lớp thường có thể hợp lý hơn. Việc thêm một phương thức `rename()` vào record không làm nó trở thành một thực thể mutable: cách rõ ràng cho thiết kế dạng giá trị là trả một record mới.

## 11. Kiểm thử phương thức của record

Khi kiểm tra các phương thức bổ sung, cần bao phủ cả kết quả và hợp đồng bảo toàn giá trị:

1. **Tính toán đúng:** `new OrderLine("A", 2, 50_000).totalVnd()` phải là `100000`.
2. **Biên điều kiện:** `isBulk()` phải `false` ở `9` và `true` ở `10`.
3. **Không sửa instance cũ:** sau `withQuantity(10)`, `original.quantity()` vẫn giữ giá trị ban đầu.
4. **Bảo toàn invariant:** `withQuantity(0)` phải bị từ chối bởi constructor như `new OrderLine(..., 0, ...)`.
5. **Equality vẫn theo component:** hai record có cùng component bằng nhau, bất kể chúng có bao nhiêu phương thức tính toán.
6. **Số học không tràn âm thầm:** nếu tổng tiền vượt phạm vi `long`, kỳ vọng `ArithmeticException` từ `Math.multiplyExact`.

Ví dụ kiểm tra ngay trong một phương thức `main` hoặc test Java có thể truy cập `OrderLine`:

```java
OrderLine one = new OrderLine("A", 9, 100);
OrderLine two = one.withQuantity(10);

System.out.println(one.isBulk());        // false
System.out.println(two.isBulk());        // true
System.out.println(one.quantity());      // 9
System.out.println(two.totalVnd());      // 1000
```

Trong ví dụ test riêng này, `OrderLine` phải nằm trong phạm vi truy cập; nếu giữ kiểu lồng trong `Main`, có thể dùng `Main.OrderLine` từ lớp khác cùng package khi mức truy cập cho phép.

Để kiểm thử lỗi số học, có thể dùng JUnit Jupiter nếu dự án đã có dependency, ví dụ:

```java
// Đoạn bên trong phương thức @Test, với JUnit Jupiter:
org.junit.jupiter.api.Assertions.assertThrows(
        ArithmeticException.class,
        () -> new OrderLine("A", 2, Long.MAX_VALUE).totalVnd()
);
```

`new OrderLine("A", 2, Long.MAX_VALUE)` được phép bởi validation hiện tại; `totalVnd()` mới ném lỗi khi nhân. Đây là **đoạn test cần có JUnit Jupiter**, không chạy độc lập bằng `javac` nếu chưa thêm thư viện.

## 12. Khi nào nên đưa hành vi vào record?

Nên đưa phương thức instance vào record nếu:

- Phương thức tính một kết quả **suy ra trực tiếp và ổn định** từ các component, ví dụ `area()`, `totalVnd()`, `isBulk()`.
- Phương thức diễn đạt một quy tắc nhỏ của giá trị, giúp code gọi ngắn và tránh lặp điều kiện.
- Phương thức tạo **một giá trị mới** từ giá trị cũ, chẳng hạn `withQuantity(...)`, đồng thời tái sử dụng validation.
- Phương thức là nghĩa vụ của một interface có ý nghĩa với giá trị record.

Nên cân nhắc đặt logic ở nơi khác nếu thao tác cần kết nối mạng/cơ sở dữ liệu, phụ thuộc nhiều dịch vụ bên ngoài, giữ trạng thái mutable qua thời gian, hoặc là quy trình nghiệp vụ lớn không còn thuộc riêng dữ liệu của record. Việc đặt phương thức gần dữ liệu cần đem lại **tính rõ ràng về trách nhiệm**, không chỉ giảm số lớp.

**Ghi nhớ:** `record` cho phép định nghĩa các **instance method** thông thường để tính toán, kiểm tra, diễn giải và tạo giá trị mới dựa trên component. Các phương thức này **không tạo thêm trường instance**, không thay đổi mặc định equality theo component và không biến record thành đối tượng mutable. Kết hợp compact constructor để bảo vệ invariant, phương thức đối tượng cho hành vi gắn với dữ liệu và static factory/interface khi thực sự cần.

### Tham khảo chính thức

- [JEP 395 — Records (chuẩn từ Java 16)](https://openjdk.org/jeps/395)
- [Java Language Specification — `8.10 Record Classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10)
- [Java SE API — Math.multiplyExact](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html#multiplyExact(long,long))
