# Giữ trạng thái tối thiểu và tránh lưu dữ liệu suy ra không cần thiết trong thiết kế lớp Java

## 1. Mục tiêu học tập

Sau khi học bài này, bạn có thể:

- Phân biệt **trạng thái nguồn** (*source of truth*, *canonical state*) với **dữ liệu dẫn xuất** (*derived/computed data*), dữ liệu hiển thị và cache.
- Trả lời câu hỏi “Field này có thực sự cần lưu?” trước khi thêm một instance field vào Java class.
- Nhận diện những giá trị tính được chính xác từ fields khác, như `total = unitPrice × quantity`, `area = width × height`, `fullName = firstName + lastName` hoặc `age = ngày hiện tại - ngày sinh`.
- Hiểu vì sao lưu đồng thời cả dữ liệu nguồn và dữ liệu dẫn xuất có thể tạo ra **trạng thái mâu thuẫn**, logic đồng bộ khó bảo trì, bugs khi thêm setter/constructor hoặc thay đổi công thức.
- Biết thiết kế private fields, constructor validation và instance methods để tập trung trách nhiệm cập nhật trạng thái vào đúng class.
- Sử dụng immutable values và defensive copying để tránh object bên ngoài sửa dữ liệu đầu vào làm kết quả dẫn xuất thay đổi không kiểm soát.
- Tận dụng `record` Java 17 khi trạng thái là một bộ giá trị đơn giản; nhớ rằng record component là representation và record không cho tự thêm instance field ngoài components.
- Phân biệt **giá trị bất biến đã chốt tại thời điểm nghiệp vụ** (giá thanh toán, thuế thực thu, tỷ giá giao dịch, số dư được kiểm toán) với **giá trị thuần túy có thể tính lại**: không tự động loại bỏ mọi giá trị có vẻ dẫn xuất.
- Cân nhắc performance khi tính giá trị đắt: lazy cache, cache invalidation, versioning, external cache; hiểu cache là **state phụ trợ có chi phí correctness**, không phải truth mới.
- Tránh lỗi integer overflow, sai đơn vị, rounding/precision khi tính tiền, tổng và các giá trị dẫn xuất.
- Thiết kế public API không expose mutable backing collections và không bắt callers đồng bộ hai setters riêng.
- Phân biệt **derived value tại thời điểm hiện tại** với **snapshot lịch sử** hoặc **denormalized read model** trong persistence/analytics.
- Viết chương trình Java 17+, chạy `javac`/`java`, đối chiếu stdout và kiểm thử invariants bằng những ví dụ độc lập.

> **Phạm vi:** Bài tập trung vào nguyên tắc giữ **trạng thái đối tượng tối thiểu nhưng đủ** và tránh lưu dữ liệu có thể tính lại từ trạng thái nguồn. Không phải mọi caching hay materialized values đều sai. Ta cần phân biệt yêu cầu nghiệp vụ, tính ổn định theo thời gian, chi phí tính toán và tính nhất quán.

## 2. Khái niệm gốc: trạng thái tối thiểu là gì?

Trong Java, **trạng thái của một instance** thường được biểu diễn bằng các instance fields. Một thiết kế có trạng thái tối thiểu lưu **những facts độc lập cần thiết** để mô tả object, không lưu trùng những giá trị có thể suy ra hoàn toàn từ facts ấy.

Ví dụ một dòng đơn hàng:

~~~java
final class OrderLine {
    private final long unitPriceCents;
    private final int quantity;
}
~~~

Giá trị `totalCents` có thể được tính chính xác từ hai fields:

~~~java
long totalCents() {
    return Math.multiplyExact(unitPriceCents, quantity);
}
~~~

Nếu class còn khai `private long totalCents;` và lưu vào constructor, nó đang có **hai cách biểu diễn cùng một thông tin**:

~~~text
unitPriceCents ─┐
                ├── phép nhân ──► totalCents
quantity ───────┘

Nếu lưu cả ba:
    source fields và cached total có thể bất đồng.
~~~

**Giữ trạng thái tối thiểu** không có nghĩa “lớp nào cũng phải chỉ có một field”. Mục tiêu là mỗi field có **lý do tồn tại độc lập**: identity, input gốc, dữ liệu snapshot đã cam kết, invariant được bảo vệ, hoặc cache mà chi phí tính lại được chứng minh.

### 2.1. Dữ liệu nguồn, dẫn xuất và snapshot

| Loại thông tin | Ví dụ | Nên lưu ở object? |
| --- | --- | --- |
| Source/canonical | `quantity`, `unitPriceCents` | Có, nếu định nghĩa object |
| Derived thuần | `totalCents = price × quantity` | Thường tính khi cần |
| Presentation | `displayText = name + " / " + code` | Thường tính hoặc xử lý ở view |
| Snapshot nghiệp vụ | Giá đã chốt khi thanh toán | Có thể **phải** lưu để kiểm toán |
| Derived phụ thuộc thời gian | Tuổi “hôm nay” từ ngày sinh | Tính với ngày được truyền vào |
| Expensive derived cache | Tổng từ một tập hàng triệu records | Có thể cache có kiểm soát |
| External materialized read model | Báo cáo tổng doanh thu, bảng tra nhanh | Có thể tồn tại riêng, có refresh/versioning |
| Dữ liệu thừa do tiện tay | `isAdult` + `birthDate` + `age` | Thường bỏ hoặc định nghĩa thật rõ snapshot |

**Câu hỏi quan trọng:** nếu một field dẫn xuất và fields nguồn bất đồng, **giá trị nào được tin?** Nếu không có câu trả lời thống nhất, representation dễ sai.

## 3. Cách phát hiện một field không nên lưu

Hãy hỏi lần lượt:

1. Có thể tính field đó từ **những fields đã có** bằng một công thức xác định không?
2. Công thức có nhanh và rẻ ở quy mô sử dụng thông thường không?
3. Có một nguồn cập nhật độc lập cho field ấy không?
4. Giá trị có cần phản ánh **thời điểm trong quá khứ** thay vì hiện tại không?
5. Có side effect, I/O, service call hoặc dữ liệu bên ngoài nào trong phép tính không?
6. Nếu thay một field nguồn, có phải cập nhật nhiều fields “bóng” để tránh mismatch không?
7. Có thể tránh một setter nguy hiểm bằng việc **không lưu dữ liệu dẫn xuất** không?
8. Nếu cần cache, ai có quyền làm cache invalid, và làm sao bảo đảm mọi mutation path đều cập nhật nó?
9. Field này có làm constructor nhiều parameters khó bảo vệ invariant không?
10. Nếu serialize object, field dẫn xuất có cần nằm trong schema không, hay consumer tự tính được?

Nếu field có công thức đơn giản, rẻ, không có snapshot semantics và không có nguồn độc lập, **tính trong method** thường là lựa chọn tốt.

## 4. Anti-pattern: lưu cả dữ liệu nguồn và tổng

Một thiết kế dễ bị drift:

~~~java
class BadLine {
    int quantity;
    long unitPriceCents;
    long totalCents;

    BadLine(int quantity, long unitPriceCents) {
        this.quantity = quantity;
        this.unitPriceCents = unitPriceCents;
        this.totalCents = quantity * unitPriceCents;
    }

    void setQuantity(int quantity) {
        this.quantity = quantity;
        // Quên cập nhật totalCents!
    }
}
~~~

Đây là **snippet minh họa có chủ đích chứa lỗi**, không dùng làm design recommendation. Khi quantity đổi, total cũ tồn tại và object có một trạng thái không nhất quán.

Nếu tất cả dữ liệu source đều mutable, số lượng đường cập nhật tăng lên khiến lỗi càng dễ xảy ra: setter, bulk update, JSON deserialization, ORM hydration, reflection-based framework, future developer thêm field. Code review phải kiểm tra từng nơi có thể mutate.

**Cách sửa:** một nguồn sự thật, method `totalCents()` tính từ quantity và unitPriceCents, kèm invariant validation.

## 5. Chương trình 1: OrderLine immutable với tổng dẫn xuất

Lưu **`OrderLineDemo.java`**:

~~~java
public class OrderLineDemo {
    static final class OrderLine {
        private final String sku;
        private final long unitPriceCents;
        private final int quantity;

        OrderLine(String sku, long unitPriceCents, int quantity) {
            if (sku == null || sku.isBlank()) {
                throw new IllegalArgumentException("sku");
            }
            if (unitPriceCents < 0 || quantity < 0) {
                throw new IllegalArgumentException("negative");
            }
            this.sku = sku;
            this.unitPriceCents = unitPriceCents;
            this.quantity = quantity;
        }

        long totalCents() {
            return Math.multiplyExact(unitPriceCents, quantity);
        }

        OrderLine withQuantity(int next) {
            return new OrderLine(sku, unitPriceCents, next);
        }

        int quantity() {
            return quantity;
        }
    }

    public static void main(String[] args) {
        OrderLine original = new OrderLine("PEN", 125, 3);
        OrderLine updated = original.withQuantity(4);

        System.out.println("quantity=" + original.quantity());
        System.out.println("original total=" + original.totalCents());
        System.out.println("updated total=" + updated.totalCents());
        System.out.println("original unchanged=" +
                (original.quantity() == 3));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 OrderLineDemo.java
java OrderLineDemo
~~~

**Stdout:**

~~~text
quantity=3
original total=375
updated total=500
original unchanged=true
~~~

**Giải thích:**

- `sku`, `unitPriceCents`, `quantity` là nguồn dữ liệu.
- Không có field `totalCents`. Method tính lại bằng `Math.multiplyExact` để không âm thầm overflow của `long`.
- Constructor bảo vệ null/blank sku và số lượng/giá âm.
- `withQuantity` tạo một object mới, không thêm setter và không cần “đồng bộ total”.
- Old and new objects có invariant riêng.
- Dùng đơn vị **cents** trong ví dụ để tránh sai số floating-point cho tiền; trong hệ thống tài chính thật còn cần currency, limits và rounding policies phù hợp.

## 6. Đoạn code trước/sau khi dữ liệu dẫn xuất dễ bị lệch

**Trước (rủi ro):**

~~~java
class Profile {
    String firstName;
    String lastName;
    String fullName;

    void changeLastName(String last) {
        lastName = last;
        // Quên cập nhật fullName.
    }
}
~~~

**Sau (source duy nhất):**

~~~java
class Profile {
    private final String firstName;
    private final String lastName;

    Profile(String firstName, String lastName) {
        this.firstName = firstName;
        this.lastName = lastName;
    }

    String fullName() {
        return firstName + " " + lastName;
    }
}
~~~

Snippets trên để so sánh ý tưởng, không có `main`. Nếu cần cập nhật họ tên, có thể cung cấp constructor/`withLastName(...)` hoặc một controlled mutation method. Không lưu thêm fullName trong cùng object nếu chỉ là nối hai chuỗi và không có snapshot/standardized-name requirement độc lập.

### 6.1. Biết phân biệt dữ liệu cần normalize với dữ liệu dẫn xuất

Ví dụ email được normalized (strip/lowercase theo **policy xác định**) trong constructor: **giá trị normalized** có thể chính là canonical source, không cần lưu cả `rawEmail` và `normalizedEmail` trừ khi business cần raw original input như một record có ý nghĩa độc lập.

## 7. Chương trình 2: Tên đầy đủ là một method, không phải field

Lưu **`FullNameDemo.java`**:

~~~java
import java.util.Objects;

public class FullNameDemo {
    record Person(String firstName, String lastName) {
        Person {
            firstName = Objects.requireNonNull(firstName).strip();
            lastName = Objects.requireNonNull(lastName).strip();

            if (firstName.isEmpty() || lastName.isEmpty()) {
                throw new IllegalArgumentException("name");
            }
        }

        String fullName() {
            return firstName + " " + lastName;
        }

        Person withLastName(String next) {
            return new Person(firstName, next);
        }
    }

    public static void main(String[] args) {
        Person first = new Person("  Lan ", " Nguyen  ");
        Person second = first.withLastName("Tran");

        System.out.println("first=" + first.fullName());
        System.out.println("second=" + second.fullName());
        System.out.println("same first name=" +
                first.firstName().equals(second.firstName()));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 FullNameDemo.java
java FullNameDemo
~~~

Stdout:

~~~text
first=Lan Nguyen
second=Lan Tran
same first name=true
~~~

Record components là canonical representation. `fullName()` là giá trị dẫn xuất, không cần thêm một component thứ ba chỉ để chứa phép nối.

## 8. Hình học: lưu chiều rộng/chiều cao, tính diện tích

Một hình chữ nhật:

~~~java
record Rectangle(int width, int height) {
    Rectangle {
        if (width < 0 || height < 0) {
            throw new IllegalArgumentException("size");
        }
    }

    long area() {
        return (long) width * height;
    }
}
~~~

Nếu lưu `area` như một component ngoài width/height, caller có thể khai `new Rectangle(4, 5, 99)` trừ khi thêm validation. Nếu area chỉ là phép nhân, việc đưa vào representation làm constructor/API phức tạp và dẫn đến “redundant state”.

### 8.1. Chương trình 3: area/perimeter tính khi cần

Lưu **`RectangleDerivedDemo.java`**:

~~~java
public class RectangleDerivedDemo {
    record Rectangle(int width, int height) {
        Rectangle {
            if (width < 0 || height < 0) {
                throw new IllegalArgumentException("size");
            }
        }

        long area() {
            return (long) width * height;
        }

        long perimeter() {
            return 2L * (width + (long) height);
        }

        boolean isSquare() {
            return width == height;
        }
    }

    public static void main(String[] args) {
        Rectangle a = new Rectangle(4, 5);
        Rectangle b = new Rectangle(6, 6);

        System.out.println("a area=" + a.area());
        System.out.println("a perimeter=" + a.perimeter());
        System.out.println("a square=" + a.isSquare());
        System.out.println("b area=" + b.area());
        System.out.println("b square=" + b.isSquare());
    }
}
~~~

Chạy:

~~~bash
javac --release 17 RectangleDerivedDemo.java
java RectangleDerivedDemo
~~~

Stdout:

~~~text
a area=20
a perimeter=18
a square=false
b area=36
b square=true
~~~

**Giải thích:** `isSquare`, `area` và `perimeter` đều là facts suy ra từ width/height. `(long)` làm phép tính ở dạng long nhằm tránh overflow int trong các trường hợp tương ứng; production code còn cần xem xét giới hạn tối đa của long.

## 9. Dữ liệu dẫn xuất phụ thuộc vào “bây giờ”: đừng lưu age như state cố định

Nếu class lưu `birthDate` và `age` cùng lúc, tuổi sẽ tự thay đổi theo ngày, nhưng field age **không tự tăng lúc nửa đêm**. Đây là lỗi nghiệp vụ phổ biến.

Tốt hơn:

~~~java
record Person(java.time.LocalDate birthDate) {
    int ageOn(java.time.LocalDate date) {
        return java.time.Period.between(birthDate, date).getYears();
    }
}
~~~

Một phép tính “tuổi hiện tại” phụ thuộc clock/time zone hoặc một `LocalDate` được truyền vào. **Đưa ngày đánh giá vào method** giúp test deterministic, không cần lưu “age hôm nay” như source data.

Cẩn trọng: nếu domain thật cần lưu tuổi đã khai báo tại thời điểm đăng ký bảo hiểm, đó là **snapshot nghiệp vụ** có thể cần giữ. Không được mất lịch sử chỉ vì hôm nay có thể tính tuổi mới.

## 10. Chương trình 4: ngày sinh là nguồn, tuổi là derived value

Lưu **`AgeDerivedDemo.java`**:

~~~java
import java.time.LocalDate;
import java.time.Period;

public class AgeDerivedDemo {
    record Person(LocalDate birthDate) {
        Person {
            if (birthDate == null) {
                throw new IllegalArgumentException("birthDate");
            }
        }

        int ageOn(LocalDate date) {
            if (date.isBefore(birthDate)) {
                throw new IllegalArgumentException("date before birth");
            }
            return Period.between(birthDate, date).getYears();
        }
    }

    public static void main(String[] args) {
        Person p = new Person(LocalDate.of(2000, 10, 18));

        System.out.println("age 2025=" +
                p.ageOn(LocalDate.of(2025, 10, 18)));
        System.out.println("age 2026=" +
                p.ageOn(LocalDate.of(2026, 10, 18)));
        System.out.println("birth=" + p.birthDate());
    }
}
~~~

Chạy:

~~~bash
javac --release 17 AgeDerivedDemo.java
java AgeDerivedDemo
~~~

Stdout:

~~~text
age 2025=25
age 2026=26
birth=2000-10-18
~~~

Bản thân Person không cần setter “updateAgeOnBirthday”. Người gọi quyết định ngày đánh giá, nên tính toán nhất quán và dễ kiểm thử.

**Không suy giá trị tuổi từ ngày hệ thống trong unit test** nếu muốn stdout giống nhau ở mọi ngày. Với UI cần `LocalDate.now(zone)`, hãy cung cấp `Clock` hoặc ngày hiện tại từ application boundary.

## 11. Derived collection: tổng giỏ hàng nên lấy từ các dòng gốc

Giả sử Cart chứa List<OrderLine> và field `subtotalCents`. Nếu list bị thêm/bớt hàng mà code quên cập nhật subtotal, invariant `subtotal = sum(lines)` bị phá vỡ.

Thiết kế nhỏ:

~~~java
final class Cart {
    private final java.util.List<Line> lines;

    long subtotalCents() {
        long sum = 0;
        for (Line line : lines) {
            sum = Math.addExact(sum, line.totalCents());
        }
        return sum;
    }
}
~~~

Không cần một field tổng nếu giỏ nhỏ và phép cộng rẻ. Nếu Cart immutable, mỗi thay đổi tạo Cart mới, giúp code không phải quản lý invalidation.

### 11.1. Defensive copy và element immutability

Nếu constructor chỉ ghi `this.lines = input` với `input` là mutable ArrayList, caller có thể thay contents sau construction, làm Cart “immutable” trên giấy nhưng derived subtotal biến động bất ngờ.

Dùng `List.copyOf(input)` (Java 10+) để tạo một unmodifiable snapshot về **cấu trúc collection**. Tuy nhiên nó là shallow copy: nếu elements mutable, vẫn có thể thay đổi nội dung từng element qua aliases. Lựa chọn tốt là elements cũng immutable records/value objects.

## 12. Chương trình 5: giỏ hàng immutable, không lưu subtotal

Lưu **`ImmutableCartDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ImmutableCartDemo {
    record Line(String sku, long unitPriceCents, int quantity) {
        Line {
            if (sku == null || sku.isBlank()
                    || unitPriceCents < 0 || quantity < 0) {
                throw new IllegalArgumentException("line");
            }
        }

        long totalCents() {
            return Math.multiplyExact(unitPriceCents, quantity);
        }
    }

    static final class Cart {
        private final List<Line> lines;

        Cart(List<Line> input) {
            this.lines = List.copyOf(input);
        }

        long subtotalCents() {
            long sum = 0;
            for (Line line : lines) {
                sum = Math.addExact(sum, line.totalCents());
            }
            return sum;
        }

        Cart plus(Line line) {
            List<Line> next = new ArrayList<>(lines);
            next.add(line);
            return new Cart(next);
        }

        int size() {
            return lines.size();
        }
    }

    public static void main(String[] args) {
        Cart original = new Cart(List.of(
                new Line("PEN", 100, 2),
                new Line("BOOK", 500, 1)));
        Cart updated = original.plus(new Line("ERASER", 100, 1));

        System.out.println("original size=" + original.size());
        System.out.println("original subtotal=" +
                original.subtotalCents());
        System.out.println("updated size=" + updated.size());
        System.out.println("updated subtotal=" +
                updated.subtotalCents());
        System.out.println("original still=" +
                original.subtotalCents());
    }
}
~~~

Chạy:

~~~bash
javac --release 17 ImmutableCartDemo.java
java ImmutableCartDemo
~~~

Stdout:

~~~text
original size=2
original subtotal=700
updated size=3
updated subtotal=800
original still=700
~~~

List.copyOf reject null elements và không cho caller sửa returned collection structure. Immutable `Line` records giữ source values; Cart không lưu `subtotalCents`, nên không có nguy cơ subtotal quên cập nhật sau `plus`.

**Hiệu năng:** mỗi call `subtotalCents()` chạy O(n). Với carts thông thường, đây thường là trade-off đơn giản hơn việc giữ mutable cache; với millions of items và high-frequency queries, hãy đo thực tế trước khi thay đổi thiết kế.

## 13. Chương trình 6: bug khi cache dẫn xuất mà quên invalidation

Bài này cố tình biểu diễn **thiết kế sai nhưng code vẫn compile/run** để quan sát drift.

Lưu **`StaleTotalDemo.java`**:

~~~java
public class StaleTotalDemo {
    static class Line {
        int quantity;
        final long unitPriceCents;
        final long cachedTotalCents;

        Line(int quantity, long unitPriceCents) {
            this.quantity = quantity;
            this.unitPriceCents = unitPriceCents;
            this.cachedTotalCents = quantity * unitPriceCents;
        }

        void changeQuantity(int next) {
            quantity = next; // BUG: cachedTotalCents không đổi.
        }

        long recomputedTotalCents() {
            return (long) quantity * unitPriceCents;
        }
    }

    public static void main(String[] args) {
        Line line = new Line(2, 100);
        System.out.println("before cached=" + line.cachedTotalCents);

        line.changeQuantity(3);

        System.out.println("after cached=" + line.cachedTotalCents);
        System.out.println("correct now=" +
                line.recomputedTotalCents());
        System.out.println("consistent=" +
                (line.cachedTotalCents ==
                        line.recomputedTotalCents()));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 StaleTotalDemo.java
java StaleTotalDemo
~~~

Stdout:

~~~text
before cached=200
after cached=200
correct now=300
consistent=false
~~~

Vấn đề không phải phép nhân sai; vấn đề là **dữ liệu dẫn xuất thành một field độc lập** mà update path không bảo vệ invariant. Một setter mới, ORM hydration hoặc partial update có thể lặp lại lỗi này.

**Cách sửa gọn:** bỏ field `cachedTotalCents` và tính `(long) quantity * unitPriceCents` trong getter, hoặc thay toàn bộ object bằng value mới.

## 14. Encapsulation giúp bảo vệ source of truth

Dùng `private` fields và **controlled methods**:

~~~java
final class Item {
    private long unitPriceCents;
    private int quantity;

    void changeQuantity(int next) {
        if (next < 0) {
            throw new IllegalArgumentException("quantity");
        }
        quantity = next;
    }

    long totalCents() {
        return Math.multiplyExact(unitPriceCents, quantity);
    }
}
~~~

Snippet trên thiếu constructor/other API nhưng minh họa điều cốt lõi: mỗi mutation chỉ đổi **source field**, derived methods đọc state hiện hành.

Một class public có fields như `public int quantity` và `public int total` làm invariant dựa vào kỷ luật của mọi caller, khó duy trì. `private` không tự tạo correctness; bạn vẫn cần validation và policies trong methods.

### 14.1. Đừng để caller cập nhật hai field bằng hai setters

API kiểu `setQuantity(3); setTotal(300);` có thể tạm thời mâu thuẫn, throw giữa hai calls hoặc concurrency race. Tốt hơn là một command mang domain semantics (changeQuantity), và derived getter tính total.

## 15. Chương trình 7: mutable source, getter luôn nhất quán

Lưu **`ControlledMutationDemo.java`**:

~~~java
public class ControlledMutationDemo {
    static final class Line {
        private final long unitPriceCents;
        private int quantity;

        Line(long unitPriceCents, int quantity) {
            if (unitPriceCents < 0) {
                throw new IllegalArgumentException("price");
            }
            this.unitPriceCents = unitPriceCents;
            changeQuantity(quantity);
        }

        void changeQuantity(int next) {
            if (next < 0) {
                throw new IllegalArgumentException("quantity");
            }
            quantity = next;
        }

        long totalCents() {
            return Math.multiplyExact(unitPriceCents, quantity);
        }
    }

    public static void main(String[] args) {
        Line line = new Line(120, 2);
        System.out.println("before=" + line.totalCents());

        line.changeQuantity(3);
        System.out.println("after=" + line.totalCents());

        try {
            line.changeQuantity(-1);
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid rejected");
        }

        System.out.println("after rejection=" +
                line.totalCents());
    }
}
~~~

Chạy:

~~~bash
javac --release 17 ControlledMutationDemo.java
java ControlledMutationDemo
~~~

Stdout:

~~~text
before=240
after=360
invalid rejected
after rejection=360
~~~

Không có duplicated total field. Mutation validation fail để lại source state cũ; getter phản ánh đúng.

**Concurrency:** class mutable ví dụ không tự thread-safe. Dù bỏ derived field, nếu multiple threads đọc/ghi quantity cần synchronization hoặc immutable snapshots/atomic designs để có visibility và consistency thích hợp.

## 16. Không phải “càng ít field càng tốt”

Tối thiểu phải **đủ giữ những facts không thể tái tạo**. Đừng loại bỏ:

- Transaction timestamp thực tế.
- External identifier hoặc idempotency key.
- Giá/tỷ giá/thuế đã chốt ở giao dịch.
- Audit actor và audit reason.
- Provider response hoặc approval code có ý nghĩa lịch sử.
- Các status có nguồn quyết định độc lập, chẳng hạn “paymentApproved” từ payment gateway (không thể suy từ subtotal).
- Snapshot cũ cần phục vụ kiểm toán hoặc hệ thống ngoại bộ.
- Version của dữ liệu được tính toán theo business rule cũ.

Một giá trị “có thể tính được với dữ liệu hiện tại” chưa chắc tái tạo **sự kiện trong quá khứ**. Ví dụ ngày hôm nay tính được tuổi hôm nay, nhưng tuổi khai tại thời điểm ký hợp đồng có thể có nghĩa pháp lý riêng.

### 16.1. Nguyên tắc xác định canonical representation

Một field nên lưu nếu có một **nguồn thay đổi độc lập** hoặc mang **ngữ nghĩa thời điểm** không thể suy lại đúng khi context thay đổi. Tối giản trạng thái là giảm duplication, không làm mất chứng cứ và information lineage.

## 17. Giá tiền, BigDecimal, rounding và trạng thái tối thiểu

Không chỉ vấn đề field duplication; phép tính dẫn xuất phải đúng domain. Với tiền:

- Dùng integer minor units như cents nếu currency/domain cho phép và giới hạn rõ.
- Hoặc dùng `BigDecimal` với currency, scale/rounding policy.
- Tránh `double` làm source authoritative của số tiền cần chính xác.
- Dùng `BigDecimal(String)` hoặc `BigDecimal.valueOf` phù hợp, tránh `new BigDecimal(0.1)` nếu kỳ vọng chính xác 0.1 thập phân.
- Dùng `Math.addExact`/`multiplyExact` khi integer overflow sẽ là lỗi cần phát hiện.
- Nếu snapshot “amount charged” là dữ liệu thực đã settlement, **giá trị thanh toán thực tế** có thể cần lưu độc lập dù có thể tính amount dự kiến từ line items.

### 17.1. Chương trình 8: BigDecimal total tính từ nguồn

Lưu **`BigDecimalLineDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.util.Objects;

public class BigDecimalLineDemo {
    static final class Line {
        private final BigDecimal unitPrice;
        private final int quantity;

        Line(BigDecimal unitPrice, int quantity) {
            Objects.requireNonNull(unitPrice, "unitPrice");
            if (unitPrice.signum() < 0 || quantity < 0) {
                throw new IllegalArgumentException("negative");
            }
            this.unitPrice = unitPrice;
            this.quantity = quantity;
        }

        BigDecimal total() {
            return unitPrice.multiply(BigDecimal.valueOf(quantity));
        }
    }

    public static void main(String[] args) {
        Line line = new Line(new BigDecimal("2.50"), 3);
        System.out.println("unit price=" + "2.50");
        System.out.println("total=" + line.total().toPlainString());
    }
}
~~~

Chạy:

~~~bash
javac --release 17 BigDecimalLineDemo.java
java BigDecimalLineDemo
~~~

Stdout:

~~~text
unit price=2.50
total=7.50
~~~

`BigDecimal.multiply` tính total đúng với scale trong trường hợp này. Demo dùng values không cần rounding; ứng dụng thực phải quy định currency/scale/exchange rate/discount/rounding ở đúng nơi, không ngầm giả định mọi currency đều có 2 decimal digits.

## 18. Nguyên tắc audit: “giá trị suy ra” có thể trở thành snapshot bắt buộc

Đặt hai câu hỏi khác nhau:

1. **Giỏ hàng hiện tại trị giá bao nhiêu?** Có thể tính từ Cart.lines, số lượng và đơn giá hiện hành.
2. **Đơn hàng ngày 01/01 đã được tính phí thực tế bao nhiêu?** Có thể là một transaction fact đã chốt; không nên tính lại từ catalog price mới.

Đây là lý do **OrderDraft** và **ConfirmedOrder** có thể có representations khác nhau:

~~~text
OrderDraft:
    lines hiện tại
    subtotal() tính từ lines

ConfirmedOrder:
    line snapshots
    amountCharged
    confirmedAt
    paymentReference
~~~

`amountCharged` trong ConfirmedOrder không nhất thiết “duplicate vô ích”: nó có thể là kết quả settlement, bao gồm rounding, promotion, tax, delivery fees và external payment behavior. Nó là một **fact lịch sử** mà business cần giữ.

Cẩn thận khi dùng cùng tên `total` cho “computed cart subtotal” và “actual settled amount”. Đặt tên API thể hiện ý nghĩa.

## 19. Chương trình 9: phân biệt total dự kiến với settled amount

Lưu **`OrderSnapshotDemo.java`**:

~~~java
import java.time.LocalDate;

public class OrderSnapshotDemo {
    record Draft(long unitPriceCents, int quantity) {
        long expectedTotal() {
            return Math.multiplyExact(unitPriceCents, quantity);
        }
    }

    record Confirmed(long expectedTotalCents,
                     long chargedCents,
                     LocalDate date) {
        Confirmed {
            if (expectedTotalCents < 0 || chargedCents < 0
                    || date == null) {
                throw new IllegalArgumentException("confirmation");
            }
        }

        long adjustmentCents() {
            return chargedCents - expectedTotalCents;
        }
    }

    public static void main(String[] args) {
        Draft draft = new Draft(100, 3);
        Confirmed confirmed =
                new Confirmed(draft.expectedTotal(), 280,
                        LocalDate.of(2026, 1, 1));

        System.out.println("expected=" + draft.expectedTotal());
        System.out.println("charged=" + confirmed.chargedCents());
        System.out.println("adjustment=" +
                confirmed.adjustmentCents());
        System.out.println("date=" + confirmed.date());
    }
}
~~~

Chạy:

~~~bash
javac --release 17 OrderSnapshotDemo.java
java OrderSnapshotDemo
~~~

Stdout:

~~~text
expected=300
charged=280
adjustment=-20
date=2026-01-01
~~~

`chargedCents` là kết quả đã chốt có thể khác expectedTotal (ví dụ adjustment do chính sách), không nhất thiết là duplicated calculated state. `adjustmentCents()` mới là derived value từ hai facts trong Confirmed.

Đây là model đơn giản: production code cần lưu chính sách điều chỉnh và xác nhận settlement từ hệ thống thanh toán.

## 20. Một lịch sử giao dịch có thể là nguồn để tính số dư

Nếu yêu cầu domain đặt **ledger/history** làm source of truth, balance hiện tại có thể được tính từ opening balance cộng các movements.

~~~text
openingBalance + Σ movements = currentBalance
~~~

Giữ **cả ledger và mutable balance** trong cùng object làm xuất hiện invariant đồng bộ giữa hai dạng state. Nhưng một hệ thống kế toán nhiều giao dịch thường dùng **materialized balance** vì performance/transactional consistency. Đây là một trường hợp cache/view được chấp nhận khi có reconciliation và atomic updates.

Ở ví dụ nhỏ, ta ưu tiên đơn giản: chỉ lưu opening amount và list movements có kiểm soát.

### 20.1. Chương trình 10: balance dẫn xuất từ transactions

Lưu **`LedgerBalanceDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class LedgerBalanceDemo {
    static final class Ledger {
        private final long openingBalance;
        private final List<Long> movements = new ArrayList<>();

        Ledger(long openingBalance) {
            if (openingBalance < 0) {
                throw new IllegalArgumentException("opening");
            }
            this.openingBalance = openingBalance;
        }

        long balance() {
            long value = openingBalance;
            for (long movement : movements) {
                value = Math.addExact(value, movement);
            }
            return value;
        }

        void deposit(long amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("deposit");
            }
            Math.addExact(balance(), amount);
            movements.add(amount);
        }

        void withdraw(long amount) {
            if (amount <= 0 || amount > balance()) {
                throw new IllegalArgumentException("withdraw");
            }
            movements.add(-amount);
        }

        List<Long> history() {
            return List.copyOf(movements);
        }
    }

    public static void main(String[] args) {
        Ledger ledger = new Ledger(100);
        ledger.deposit(50);
        ledger.withdraw(20);

        System.out.println("balance=" + ledger.balance());
        System.out.println("movements=" + ledger.history().size());

        try {
            ledger.withdraw(200);
        } catch (IllegalArgumentException expected) {
            System.out.println("overdraft rejected");
        }

        System.out.println("still balance=" + ledger.balance());
    }
}
~~~

Chạy:

~~~bash
javac --release 17 LedgerBalanceDemo.java
java LedgerBalanceDemo
~~~

Stdout:

~~~text
balance=130
movements=2
overdraft rejected
still balance=130
~~~

**Giải thích:**

- Ledger lưu source events, không thêm mutable `balance` field.
- `balance()` tính từ openingBalance + movements.
- `deposit` kiểm tra overflow trước khi ghi.
- `withdraw` bảo đảm sufficient funds.
- `history()` trả snapshot không sửa được về cấu trúc.
- Demo single-thread, in-memory; không có concurrency, idempotency hoặc durable transactions.

**Ngoại lệ thực tiễn:** với millions of movements, tính lại O(n) mỗi lần có thể đắt. Trong hệ thống thực, materialized balance + atomic ledger transaction + periodic reconciliation là thiết kế hợp lệ; trọng tâm không phải “bằng mọi giá không có balance cache”.

## 21. Immutable vs mutable objects trong tối giản trạng thái

### 21.1. Immutable value object

Nếu tất cả canonical fields `private final` và nested values immutable, giá trị dẫn xuất có thể tính bất kỳ lúc nào mà không lo concurrent mutation trong object.

~~~java
record Point(int x, int y) {
    long distanceSquared() {
        return (long) x * x + (long) y * y;
    }
}
~~~

Record `Point` chỉ có x/y components; `distanceSquared()` là method. Không nên thêm `distanceSquared` thành record component chỉ vì tính được.

### 21.2. Mutable object

Nếu class cho đổi source fields, getter dẫn xuất phải đọc trạng thái nhất quán theo concurrency model. Không thêm cached fields tùy ý nếu mọi mutations không có invalidation contract. Nếu multiple threads truy cập, cần thread-safety policy.

### 21.3. Record không tự deep-immutable

Một record có `List<String> items` chỉ giữ một **final List reference**. Nếu List ban đầu mutable, người khác có thể sửa contents làm derived count/totals thay đổi. Defensive copying hoặc chọn immutable component types là phần quan trọng của một representation đáng tin.

## 22. Chương trình 11: defensive copy để bảo vệ source data

Lưu **`DefensiveCopyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class DefensiveCopyDemo {
    record Basket(List<String> items) {
        Basket {
            items = List.copyOf(items);
        }

        int count() {
            return items.size();
        }

        String summary() {
            return String.join(",", items);
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A"));
        Basket basket = new Basket(source);

        source.add("B");

        System.out.println("source=" + source);
        System.out.println("basket=" + basket.summary());
        System.out.println("count=" + basket.count());

        try {
            basket.items().add("C");
        } catch (UnsupportedOperationException expected) {
            System.out.println("basket unmodifiable");
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 DefensiveCopyDemo.java
java DefensiveCopyDemo
~~~

Stdout:

~~~text
source=[A, B]
basket=A
count=1
basket unmodifiable
~~~

`List.copyOf` trả unmodifiable snapshot về elements/reference sequence tại thời điểm tạo. Với elements là String immutable, derived count/summary của Basket không bị caller thay đổi qua original list.

Nếu elements là mutable `Item`, `List.copyOf` **không deep-copy Item objects**. Phải bảo vệ cả element state nếu immutable snapshot thực sự là business contract.

## 23. Tối giản state giúp constructor và API gọn, invariant rõ

Constructor nhận hai source fields:

~~~java
new Rectangle(3, 5);
~~~

Dễ hiểu hơn:

~~~java
new Rectangle(3, 5, 15, 16, false);
~~~

nếu ba arguments cuối chỉ là area/perimeter/isSquare có thể suy từ hai số đầu. API dài cho phép contradictory input hoặc đòi validation phức tạp.

Một public constructor nhận `amount, quantity, total` đặt câu hỏi: giá trị nào thắng nếu total ≠ amount × quantity? Nếu total không là độc lập business fact, hãy loại bỏ parameter và tính qua method.

### 23.1. Derived getter không được có side effects bất ngờ

Một method `total()` tốt thường **pure** theo state: cùng canonical inputs cho cùng output, không tự sửa fields, không gọi network, không đổi transaction.

Nếu method thực hiện I/O hay thay state, tên `getTotal()` dễ gây hiểu nhầm. Hãy tách query/computation và command/side effect rõ ràng.

## 24. Cache khi phép tính đắt: trade-off có điều kiện

Một field cache có thể hợp lý nếu:

1. Derived calculation thực sự đắt (đo bằng profiler/benchmark).
2. Kết quả được đọc nhiều lần giữa các mutations.
3. Inputs có **mutation boundary rõ** và cập nhật tập trung.
4. Có strategy invalidation đầy đủ.
5. Memory cache chấp nhận được.
6. Concurrency/visibility rules được thiết kế.
7. Khi cache invalid/missing, có khả năng tính lại đúng từ source.
8. Không dùng cache như một fact nghiệp vụ độc lập nếu nó chỉ là derived value.

**Điểm then chốt:** cache **không thay thế nguồn sự thật**. Khi inputs đổi, cache phải bị vô hiệu hóa hoặc có versioning.

### 24.1. Các chiến lược

| Strategy | Ưu điểm | Rủi ro |
| --- | --- | --- |
| Compute on demand | Ít fields, luôn theo source | O(n) mỗi lần đọc |
| Eager recompute on mutation | Getter O(1) | Mọi mutation phải update cache; transaction consistency |
| Lazy + dirty flag | Tính lại khi cần | Dirty flag/invalidation phải chính xác |
| Versioned cache | Có thể so sourceVersion/cacheVersion | Version drift, concurrency |
| External cache/materialized view | Tách read optimization khỏi domain source | Đồng bộ/cập nhật trễ, eviction, failures |
| Immutable object memoization | Inputs không đổi sau construction | Thread-safety/publication nếu lazy; thêm memory |

Không dùng cache chỉ vì “có vẻ getter nên O(1)”; chọn sau khi đo ở workload thực.

## 25. Chương trình 12: cached derived total có invalidation rõ

Lưu **`ValidatedCacheDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ValidatedCacheDemo {
    static final class Report {
        private final List<Long> amounts = new ArrayList<>();
        private boolean dirty = true;
        private long cachedTotal;
        private int calculations;

        void add(long amount) {
            if (amount < 0) {
                throw new IllegalArgumentException("amount");
            }
            amounts.add(amount);
            dirty = true;
        }

        long total() {
            if (dirty) {
                long sum = 0;
                for (long amount : amounts) {
                    sum = Math.addExact(sum, amount);
                }
                cachedTotal = sum;
                dirty = false;
                calculations++;
            }
            return cachedTotal;
        }

        int calculations() {
            return calculations;
        }
    }

    public static void main(String[] args) {
        Report report = new Report();

        report.add(10);
        report.add(20);

        System.out.println("first=" + report.total());
        System.out.println("second=" + report.total());
        System.out.println("calcs=" + report.calculations());

        report.add(5);

        System.out.println("after change=" + report.total());
        System.out.println("calcs after change=" +
                report.calculations());
    }
}
~~~

Chạy:

~~~bash
javac --release 17 ValidatedCacheDemo.java
java ValidatedCacheDemo
~~~

Stdout:

~~~text
first=30
second=30
calcs=1
after change=35
calcs after change=2
~~~

Đây là **minh họa khi cache thực sự được chọn**; việc nó cần `dirty`, `cachedTotal` và `calculations` cho thấy chi phí state bổ sung. `calculations` chỉ là metric để giải thích demo, không thuộc domain state. Lớp không expose `amounts` mutable list và mọi mutation đều gọi `add` để đặt dirty.

**Cảnh báo:** đây là single-thread sample. Nếu nhiều threads đọc/ghi Report, `dirty` và `cachedTotal` cần synchronization/atomic snapshots/immutable approach; `volatile` đơn giản trên một field không tự tạo một snapshot nhất quán của toàn object. Với số rất lớn, tính tổng có thể overflow; `Math.addExact` phát hiện thay vì silent wrap.

## 26. Cache làm tăng state và số invariant phải kiểm thử

Khi chỉ có list `amounts`:

~~~text
total() = sum(amounts)
~~~

Một invariant nguồn dữ liệu đơn giản là amounts chỉ chứa số không âm (theo domain).

Khi có cache:

~~~text
dirty=false ⇒ cachedTotal == sum(amounts)
dirty=true  ⇒ cachedTotal không dùng làm query result
~~~

Phải bảo đảm điều này qua:
- mọi path thêm/sửa/xóa;
- rollback khi mutation fail;
- deserialize/rehydrate;
- concurrency memory visibility;
- copy/clone object;
- version changes;
- exceptions trong quá trình compute.

Vì vậy mỗi redundant field có một **correctness cost**. Đừng chỉ đánh giá số byte cho field đó.

## 27. Trạng thái dẫn xuất cho collection: `size`, `isEmpty`, `contains`

Với một private List source:

~~~java
private final List<String> items = new ArrayList<>();

int count() {
    return items.size();
}

boolean empty() {
    return items.isEmpty();
}
~~~

Không cần thêm `itemCount`, `emptyFlag` để sao chép List size/status: List vốn đã giữ size phù hợp với own implementation.

Một `contains("A")` là derived query từ items; nếu chạy quá đắt, cân nhắc data structure phù hợp như Set thay vì tự duy trì count flags hay indexes thủ công. Chọn cấu trúc lưu source data phù hợp với access patterns thường tốt hơn thêm redundant cache.

### 27.1. Khi cần nhiều representations để tối ưu

Một service có thể giữ `Map<Id,Item>` và một index `Map<Category,List<Id>>` để truy vấn nhanh. Đó là **deliberate denormalization**, không phải thiết kế trạng thái tối thiểu theo nghĩa đơn giản. Nó cần ownership/atomic update/rebuild/reconciliation. Hãy để domain object đơn giản nếu indexing thuộc infrastructure/read layer.

## 28. Invariant bảo vệ bằng method, không phải bằng lời hứa của caller

Có thể đặt các nguyên tắc:

- Field nguồn `quantity >= 0`.
- `unitPriceCents >= 0`.
- `totalCents() = exactMultiply(quantity, unitPriceCents)`.
- `lines` không có null.
- `birthDate` không null; method ageOn kiểm tra evaluation date.
- `openingBalance >= 0` và withdrawal rules.
- `cacheValid ⇒ cachedTotal đúng với sourceVersion` nếu có cache.

Chỉ dùng comment `// Always keep total synced` không đủ. Đưa invariants vào constructor/controlled APIs/tests.

### 28.1. Atomicity của nhiều nguồn

Khi cần cập nhật hai canonical source fields **cùng lúc**, một method `changePriceAndQuantity` hoặc immutable replacement có thể bảo vệ invariant. Tối giản fields không thay synchronization/transaction requirements. Nếu two fields là một logically atomic state, chúng vẫn cần cập nhật nhất quán.

## 29. Equality và hashCode khi giữ redundant fields

Nếu một class tự khai `equals`/`hashCode`, cần quyết định identity/value semantics đúng với **canonical state**. Không đưa transient derived cache vào equality/hash nếu cache không phải business identity: hai objects cùng inputs mà cache warm/cold khác nhau không nên bất ngờ unequal.

Với `record Rectangle(int width,int height)`, generated equals/hashCode phản ánh components; derived method area không góp thêm một field.

Ngược lại, nếu đưa `area` như một component vào record, nó thành một phần representation/equality dù chỉ tính từ width/height. Điều đó làm API/invariant phức tạp và có thể ảnh hưởng serialization.

### 29.1. Bảo vệ mutable keys

Nếu object làm HashMap/HashSet key, các fields ảnh hưởng equals/hash không nên bị mutate khi object đang làm key. Derived getter có vẻ innocuous nhưng equality dựa trên mutable source có thể gây lỗi lookup. Immutable value objects thường dễ dùng an toàn hơn.

## 30. Chương trình 13: record value equality dựa trên source components

Lưu **`MinimalRecordEqualityDemo.java`**:

~~~java
public class MinimalRecordEqualityDemo {
    record Rectangle(int width, int height) {
        long area() {
            return (long) width * height;
        }
    }

    public static void main(String[] args) {
        Rectangle a = new Rectangle(2, 6);
        Rectangle b = new Rectangle(2, 6);
        Rectangle c = new Rectangle(3, 4);

        System.out.println("a area=" + a.area());
        System.out.println("c area=" + c.area());
        System.out.println("a equals b=" + a.equals(b));
        System.out.println("a equals c=" + a.equals(c));
        System.out.println("same area=" + (a.area() == c.area()));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 MinimalRecordEqualityDemo.java
java MinimalRecordEqualityDemo
~~~

Stdout:

~~~text
a area=12
c area=12
a equals b=true
a equals c=false
same area=true
~~~

Hai hình có cùng derived area chưa chắc có cùng canonical width/height, vì vậy không nên dùng area như shortcut thay representation trong equality.

## 31. Normalize input một lần, không giữ cả bản gốc và bản chuẩn hóa khi không cần

Nếu policy của domain định nghĩa email canonical là trimmed lowercase ASCII domain-friendly string, hãy validate rồi lưu **một representation canonical**:

~~~java
record Email(String value) {
    Email {
        value = value.strip().toLowerCase(
                java.util.Locale.ROOT);
    }
}
~~~

Đây là **snippet** minh họa policy giản lược, không phải email internationalization/canonicalization toàn diện: địa chỉ email có quy tắc local-part phức tạp và application phải chọn policy đúng. Trong domain ID thông thường với quy tắc case-insensitive do chính ứng dụng định nghĩa, normalization có thể thực hiện có kiểm soát.

Không lưu đồng thời raw input và canonical value nếu raw không có independent audit purpose. Nếu phải hiển thị tên đúng cách người dùng nhập hoặc phục vụ compliance, raw snapshot có thể là dữ liệu thật cần giữ.

## 32. Chương trình 14: canonical code một field

Lưu **`NormalizedCodeDemo.java`**:

~~~java
import java.util.Locale;
import java.util.Objects;

public class NormalizedCodeDemo {
    record ProductCode(String value) {
        ProductCode {
            value = Objects.requireNonNull(value, "value")
                    .strip()
                    .toUpperCase(Locale.ROOT);

            if (value.isEmpty()) {
                throw new IllegalArgumentException("blank");
            }
        }

        String display() {
            return "SKU-" + value;
        }
    }

    public static void main(String[] args) {
        ProductCode a = new ProductCode("  pen ");
        ProductCode b = new ProductCode("PEN");

        System.out.println("canonical=" + a.value());
        System.out.println("same value=" + a.equals(b));
        System.out.println("display=" + a.display());
    }
}
~~~

Chạy:

~~~bash
javac --release 17 NormalizedCodeDemo.java
java NormalizedCodeDemo
~~~

Stdout:

~~~text
canonical=PEN
same value=true
display=SKU-PEN
~~~

Object giữ một canonical value. `display` là derived presentation; không cần `displayCode` field. Chính sách `strip/upper` thuộc ProductCode domain trong demo.

## 33. Thiết kế API: source queries và derived queries rõ tên

Một lớp domain có thể cung cấp:

~~~java
long unitPriceCents();
int quantity();
long expectedTotalCents();
~~~

Tên method nói rõ ý nghĩa:
- Giá đơn vị là source.
- Quantity là source.
- Expected total là computed.

Không trộn:
- `getTotal()` vừa cập nhật database, vừa thay cache, vừa gọi payment provider.
- `setTotal()` trong khi giá trị total được suy từ source.
- `getAge()` dựa vào implicit system time khiến tests nondeterministic.
- `getChargedAmount()` nhưng thực tế chỉ tính expected amount từ current catalog.

Đặt tên theo nghiệp vụ để tránh lưu nhầm snapshot và derived view.

## 34. DTO, persistence và JSON: tránh gửi “hai nguồn sự thật”

Khi serialize object ra DTO, đôi khi nên trả cả source và derived fields để consumer tiện hiển thị:

~~~text
{
  "unitPriceCents": 125,
  "quantity": 3,
  "totalCents": 375
}
~~~

Đây là **JSON schema minh họa**, không phải Java code. Vấn đề là xác định **ai sở hữu total**:

- Server có thể đưa total như **derived response field** (computed mỗi lần).
- Client không nên gửi total lên để override business validation nếu nó chỉ là derived.
- Nếu client gửi cả source/total, server phải có rule rõ: recompute/validate hoặc reject mismatch.
- Khi persistence một completed transaction, settled amount là independent snapshot có thể cần lưu.
- Trong read models/materialized views, lưu total vì performance là chấp nhận được nếu có refresh/versioning/reconciliation và nguồn đúng.

Đừng coi “trạng thái tối thiểu” là bắt buộc xóa derived value khỏi **mọi API response**; nó chủ yếu nói về **authoritative internal state**, không cấm presentation projection.

## 35. Chi phí tính toán và heuristic đánh giá

Một heuristic:

1. **O(1) và pure** như fullName, area, quantity×price: hầu như luôn nên tính.
2. **O(n) với n nhỏ** như subtotal của giỏ vài chục dòng: thường tính.
3. **O(n) với n lớn và query thường xuyên**: đo benchmark và cân nhắc cache/materialized view.
4. **I/O/cross-service**: không gọi “simple derived getter”; đây là một query boundary/service concern.
5. **Time-varying** như age, exchange rate: truyền clock/context và định nghĩa snapshot semantics.
6. **Must retain history**: snapshot riêng dù nhìn có vẻ dẫn xuất.
7. **Thread-safety/invalidation quá phức tạp**: cân nhắc immutable snapshot/external cache thay internal fields.
8. **Derived output lớn**: có thể streaming/lazy iterator thay field lưu toàn bộ list sao chép.

Một field giảm CPU nhưng thêm synchronization, invalidation và memory không mặc nhiên là tối ưu. Chi phí tổng mới quyết định.

## 36. Mẫu checklist đánh giá field

| Câu hỏi | Nếu trả lời “có” | Hướng hành động |
| --- | --- | --- |
| Có công thức từ fields nguồn? | Derived candidate | Viết method, không lưu vội |
| Công thức rẻ/pure? | Dễ tính lại | Giữ minimal state |
| Inputs thay đổi độc lập? | Dễ drift | Càng tránh duplicate field |
| Là sự kiện lịch sử đã chốt? | Snapshot có ý nghĩa | Lưu rõ immutable fact |
| Phụ thuộc ngày/clock/external rate? | Context thay đổi | Truyền context, phân biệt snapshot |
| Tính lại rất tốn CPU/I/O? | Performance concern | Đo và thiết kế caching có contract |
| Có nhiều mutation paths? | Cache invalidation khó | Encapsulation/immutable thay thế |
| Có cần equality/serialization? | Representation API concern | Tránh derived field gây coupling |
| Có mutable nested collections? | Source có thể bị đổi ngầm | Defensive copy/immutable elements |
| Có concurrent readers/writers? | Consistency/visibility concern | Snapshot hoặc synchronization |
| Dữ liệu xuất hiện trong API response? | Có thể chỉ là projection | Tính từ source lúc serialize |
| Data migrations làm rule thay? | Historical divergence | Version rule/snapshot/reconciliation |

## 37. Unit tests cần kiểm tra gì?

- Given source values, computed getter đúng.
- Thay đổi source qua method hợp lệ khiến computed values đúng ngay.
- Invalid mutations throw và **không phá source state**.
- Old immutable object không đổi khi tạo new object.
- Caller sửa input list sau constructor không làm internal state đổi.
- Nếu cache có invalidation, compute count và value after change đúng.
- Source equal thì derived outputs theo same formula equal.
- Different source có thể cùng derived output nhưng objects không nhất thiết equal.
- Money calculation không overflow âm thầm.
- Time-derived values dùng input date/clock cố định.
- Snapshot lịch sử không thay khi price list hiện tại đổi.
- Serialize/deserialize DTO phải tuân quy tắc source of truth.
- Tests concurrency khi shared mutable source/cache thực sự đa luồng.

### 37.1. Chương trình 15: kiểm thử hợp đồng minimal state

Lưu **`MinimalStateContractTest.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class MinimalStateContractTest {
    record Line(long priceCents, int quantity) {
        Line {
            if (priceCents < 0 || quantity < 0) {
                throw new IllegalArgumentException("line");
            }
        }

        long total() {
            return Math.multiplyExact(priceCents, quantity);
        }
    }

    record Cart(List<Line> lines) {
        Cart {
            lines = List.copyOf(lines);
        }

        long subtotal() {
            long sum = 0;
            for (Line line : lines) {
                sum = Math.addExact(sum, line.total());
            }
            return sum;
        }
    }

    static void check(boolean ok, String description) {
        if (!ok) {
            throw new AssertionError(description);
        }
    }

    public static void main(String[] args) {
        List<Line> input = new ArrayList<>();
        input.add(new Line(125, 2));
        Cart cart = new Cart(input);

        check(cart.subtotal() == 250, "initial total");
        input.add(new Line(500, 1));
        check(cart.lines().size() == 1, "defensive copy");
        check(cart.subtotal() == 250, "subtotal unchanged");

        try {
            cart.lines().add(new Line(1, 1));
            throw new AssertionError("mutation accepted");
        } catch (UnsupportedOperationException expected) {
            // List copy không cho cấu trúc bị sửa.
        }

        try {
            new Line(-1, 1);
            throw new AssertionError("negative accepted");
        } catch (IllegalArgumentException expected) {
            // Constructor bảo vệ source invariant.
        }

        check(new Line(125, 2).total() == cart.subtotal(),
                "same formula");

        System.out.println("minimal state checks passed");
    }
}
~~~

Chạy:

~~~bash
javac --release 17 MinimalStateContractTest.java
java MinimalStateContractTest
~~~

Stdout:

~~~text
minimal state checks passed
~~~

Tests chạy chủ động bằng `check`, không phụ thuộc `assert` (bị tắt mặc định nếu không thêm `-ea`). Đặc biệt, Cart không có extra total field mà vẫn đáp ứng đầy đủ các checks.

## 38. Những lỗi thường gặp

| Thiết kế/vấn đề | Vì sao nguy hiểm? | Cách sửa |
| --- | --- | --- |
| `price, qty, total` là 3 mutable fields | Total có thể stale | Lưu price/qty, tính total |
| `firstName, lastName, fullName` | Duplicate string, đổi họ tên bị lệch | `fullName()` method |
| `width, height, area, perimeter` | Constructor setters phức tạp | Derived geometry methods |
| `birthDate, age` | Age thay theo thời gian | `ageOn(date)` |
| `items, itemCount, emptyFlag` | List đã giữ size | `size()`/`isEmpty()` |
| Expose `ArrayList` rồi giữ cached sum | External mutations bỏ qua invalidation | Private list, defensive copy/query |
| Giữ cached sum không dirty/version | Stale result | Compute or invalidation/versioning |
| Coi mọi snapshot là duplicate thừa | Mất giá/thuế lịch sử | Phân loại authoritative event facts |
| Dùng `double` cho monetary authoritative totals | Precision issues | Cents/BigDecimal + policy |
| Dùng `quantity*price` không kiểm overflow | Silent wraparound | Exact operations/validation |
| Getter có network I/O | Side effect/latency bất ngờ | Query service rõ ràng |
| Derived cache trong equals/hashCode | Warm/cold objects unequal | Canonical identity/value semantics |
| Mutable object làm key rồi update fields | Hash-based lookup break | Immutable keys |
| Hai setters `setQty/setTotal` | Non-atomic consistency | Một source, derived query |
| Coi `List.copyOf` là deep copy | Elements mutable vẫn đổi | Immutable elements/deep snapshot nếu cần |
| Derived flag `isExpired` lưu mãi | Time changes state | `isExpiredAt(now)` |
| Recompute nặng trong getter gọi cực thường | Performance cost | Benchmark + deliberate cache |
| Cache mutable shared thiếu synchronization | Races/stale visibility | Immutable snapshots/locking |
| DTO cho client gửi total override | Client có thể đưa giá trị sai | Recompute/validate server-side |
| Xóa actual settlement amount vì “recompute được” | Mất audit history | Giữ independent snapshot fact |

## 39. Bài tập áp dụng

### Bài 1. Thiết kế lại Student

Cho fields `birthDate`, `age`, `displayAge`. Hỏi nên giữ gì?

**Gợi ý đáp án:** nếu chỉ cần tuổi hiện tại, giữ `birthDate`; dùng `ageOn(LocalDate)` và display method. Nếu age khai tại thời điểm xét tuyển là fact cố định, mô hình riêng snapshot để không đánh mất ý nghĩa lịch sử.

### Bài 2. Giỏ hàng có 3 dòng

Có `List<Line> lines`, `int count`, `long subtotal`. Hỏi count/subtotal có thể bỏ không?

**Đáp án:** `count() = lines.size()` và `subtotal() = sum(lines.total())`. Nếu list nhỏ, bỏ fields thừa. Nếu subtotal là snapshot đã chốt hoặc tính rất tốn, phân loại lại và thiết kế có contract.

### Bài 3. Công thức diện tích

~~~java
record Rectangle(int width, int height, long area) {}
~~~

**Đáp án:** nếu area chỉ là width×height, record nên chỉ giữ width,height rồi method area. Nếu area được đo thực địa và có ý nghĩa khác, không được tự suy bằng công thức.

### Bài 4. Giá trị đã settlement

Cart dự kiến 10000 cents, gateway charge 9800 cents. Có nên bỏ `chargedCents` vì “total = items sum”?

**Đáp án:** Không. Charged amount là fact của external settlement có thể khác expected total; giữ snapshot và reference/adjustment context.

### Bài 5. Cần cache

Tính tổng 1 triệu events, getter gọi 1000 lần/giây, mutations mỗi giờ. Làm gì?

**Đáp án:** đo chi phí; có thể snapshot/cache hoặc materialized read model. Đặt rõ cache invalidation và concurrency; không vô tình biến cache thành authoritative fact.

### Bài 6. External mutation

Constructor nhận ArrayList rồi gán trực tiếp vào private final List, subtotal computed. Có an toàn không?

**Đáp án:** Không nếu caller vẫn giữ ArrayList và có thể sửa. Dùng `List.copyOf`/immutable element values hoặc explicit live-view contract.

### Bài 7. Field private là đủ chưa?

Quantity/Price private nhưng một method vẫn sửa quantity và không cập nhật cachedTotal. Invariant có được bảo vệ chưa?

**Đáp án:** Chưa. Private chỉ thu hẹp mutation paths; vẫn cần remove derived state hoặc correct invalidation.

### Bài 8. Currency

`double total = 0.1 + 0.2` có nên là authoritative monetary amount?

**Đáp án:** Không nên, vì binary floating-point không biểu diễn chính xác mọi decimal fractions. Chọn cents/BigDecimal với scale/rounding policy phù hợp.

### Bài 9. Record chứa List

`record Cart(List<Line> lines)` có tự immutable không?

**Đáp án:** Record field final nhưng List elements/structure có thể mutable qua alias; cần defensive copy hoặc immutable data model.

### Bài 10. Getter có service call

`getCurrentExchangeRate()` cần gọi network. Có nên lưu một field rate và xem nó derived từ currency pair không?

**Đáp án:** Không tự coi đó là pure formula. Rate có timestamp, provider, version và caching/consistency contract; mô hình query/snapshot rõ.

### Bài 11. Full name có cần localization?

Tên người có quy tắc hiển thị theo locale/policy. Điều này có làm fullName thành source state không?

**Đáp án:** Chưa chắc. Có thể truyền formatting strategy/locale vào display method. Chỉ lưu original display name khi nó là user-authored independent fact cần giữ.

### Bài 12. Cache làm equality thay đổi?

Hai objects có same inputs, một object cache đã warm, một chưa. Chúng có nên unequal không?

**Đáp án:** Thường không nếu cache chỉ là performance detail; equals/hashCode nên theo canonical identity/value semantics.

## 40. Checklist thiết kế lớp

- [ ] Từng field có nguồn dữ liệu độc lập hoặc lý do lưu rõ?
- [ ] Có field nào có thể tính rẻ và chính xác từ fields khác?
- [ ] Đã chọn source of truth khi có thể mismatch?
- [ ] Fields nguồn được private và validation đầy đủ?
- [ ] Có setter nào đòi caller tự update derived fields?
- [ ] Derived getters có pure behavior và tên phù hợp?
- [ ] Có tránh duplicate state trong constructor/record components?
- [ ] Có xét integer overflow, currency/scale/rounding?
- [ ] Có data thay theo clock/context và được tính với explicit input?
- [ ] Có snapshot/audit facts không nên xóa?
- [ ] Có defensive copy mutable collection inputs?
- [ ] Elements nested có thật sự immutable?
- [ ] Nếu cache, đã đo performance và lập invalidation policy?
- [ ] Có concurrency policy cho cache/mutable canonical fields?
- [ ] Cache có thể rebuild/reconcile từ authoritative state?
- [ ] Derived fields có vô tình tham gia equals/hashCode?
- [ ] DTO/persistence có phân biệt input truth với output projection?
- [ ] Unit tests kiểm update, rejection, copy, snapshot và overflow?
- [ ] Khi thay business formula, có cần versioning historical amounts?
- [ ] Thiết kế đọc được và ít invariant hơn trước?

## 41. Tài liệu tham khảo

- [Java Language Specification Java SE 17 `8.3 — Field Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3): instance fields, static fields, field modifiers.
- [JLS Java SE 17 `8.3.1.2 — final Fields](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3.1.2): final fields và definite assignment.
- [JLS Java SE 17 `8.8 — Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8): constructor và initialization.
- [JLS Java SE 17 `8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): component-based representation, derived methods.
- [Java SE 17 `java.util.List.copyOf`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): unmodifiable snapshot, null restrictions, shallow elements.
- [Java SE 17 `java.math.BigDecimal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): arbitrary-precision decimal calculations, multiply, scale/rounding.
- [Java SE 17 `java.lang.Math.addExact`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#addExact(long,long)) và [`multiplyExact`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#multiplyExact(long,long)): kiểm tra overflow.
- [Java SE 17 `java.time.LocalDate`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html): ngày và temporal computations.
- [Java SE 17 `java.time.Period`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Period.html): date-based amount và age computation.
- [Oracle Java 17 — Creating Unmodifiable Lists, Sets, and Maps](https://docs.oracle.com/en/java/javase/17/core/creating-immutable-lists-sets-and-maps.html): unmodifiable factory/copy APIs và trade-offs.

## Kết luận

Thiết kế lớp tốt không cố giảm số fields bằng mọi giá; nó giữ **tập trạng thái nguồn đủ, rõ và nhất quán**. Những kết quả như `area`, `fullName`, `lineTotal`, `cartSubtotal`, `isEmpty` hoặc `ageOn(date)` thường nên được **tính từ source fields**, không lưu thành duplicated mutable fields.

Giảm redundant state giúp giảm số invariants, setters, constructor parameters, synchronization paths và lỗi khi công thức thay đổi. Encapsulation, validation, immutable values và defensive copies giúp source of truth ổn định.

Khi performance thực sự yêu cầu, **cache có kiểm soát** là một optimization hợp lệ — nhưng phải có invalidation, concurrency policy và khả năng tính lại từ nguồn. Khi business cần **actual historical/snapshot facts**, hãy lưu chúng với ý nghĩa riêng thay vì xóa vì trông giống dữ liệu dẫn xuất.

**Nguyên tắc ghi nhớ:** *Lưu facts thực sự cần nhớ; tính lại những điều chắc chắn suy được; chỉ cache khi chi phí tính lại đã được chứng minh; bảo toàn những snapshots có ý nghĩa nghiệp vụ.*
