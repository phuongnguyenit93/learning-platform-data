# Dùng composition khi mở rộng giá trị qua kế thừa làm hợp đồng khó giữ

## 1. Vấn đề: thêm “giá trị” vào subclass có thể phá hợp đồng equals

Trong Java, kế thừa (`extends`) phù hợp khi một đối tượng con thực sự có thể thay thế đối tượng cha theo những cam kết của kiểu cha. Nhưng **kế thừa một lớp giá trị chỉ để bổ sung thành phần dùng cho so sánh bằng nhau** thường tạo ra mâu thuẫn.

Xét `Point(x, y)` định nghĩa hai điểm bằng nhau nếu tọa độ giống nhau. Sau đó ta muốn `ColorPoint(x, y, color)` bổ sung màu và định nghĩa hai điểm có màu bằng nhau khi **cả tọa độ lẫn màu** giống nhau. Nếu `ColorPoint extends Point`, cách lớp cha nhìn equality và cách lớp con nhìn equality không còn cùng tiêu chí.

Hợp đồng `Object.equals(Object)` yêu cầu, với các đối tượng khác `null`:

- **Phản xạ:** `x.equals(x)` là `true`.
- **Đối xứng:** `x.equals(y)` và `y.equals(x)` có cùng kết quả.
- **Bắc cầu:** nếu `x.equals(y)` và `y.equals(z)` đều `true`, thì `x.equals(z)` cũng phải `true`.
- **Nhất quán:** kết quả ổn định khi trạng thái tham gia so sánh không đổi.
- **So sánh với null:** `x.equals(null)` là `false`.

Ngoài ra, hai đối tượng bằng nhau phải có cùng `hashCode()`. Việc cài đặt `equals(Object)` và `hashCode()` ở hai lớp phải tương thích, không chỉ đúng riêng rẽ ở từng lớp.

Điểm khó không nằm ở cách viết `instanceof` hay cú pháp Java, mà ở **hai định nghĩa giá trị khác nhau cùng xuất hiện trong một hệ phân cấp**: `Point` bỏ qua màu, còn `ColorPoint` muốn tính cả màu.

## 2. Bẫy đối xứng khi ghi đè equals trong lớp con

Giả sử lớp cha cài:

```java
@Override
public boolean equals(Object obj) {
    return obj instanceof Point other
            && x == other.x && y == other.y;
}
```

Đây là **đoạn trích minh họa**, giả sử `x`, `y` là các trường của `Point` và có `hashCode()` phù hợp. Vì dùng `instanceof Point`, lớp cha chấp nhận cả các subclass có cùng tọa độ.

Nếu subclass chỉ chấp nhận đối tượng `ColorPoint` rồi so thêm `color`, ta nhận được:

- `point.equals(redPoint)` → `true`: lớp cha chỉ xét tọa độ.
- `redPoint.equals(point)` → `false`: lớp con đòi đối tượng còn phải có màu.

Hai chiều khác nhau, nên **phá tính đối xứng**. Đổi `instanceof Point` thành `getClass() == obj.getClass()` ở lớp cha có thể thay đổi ngữ nghĩa để `Point` và `ColorPoint` không bằng nhau, nhưng không phải lúc nào cũng sửa được API lớp cha đã phát hành, và có thể đi ngược kỳ vọng mà người dùng đang dựa vào.

## 3. Bẫy bắc cầu khi cố “vá” đối xứng

Một cách vá hấp dẫn là: nếu `ColorPoint` được so với `Point` thường, hãy để `Point` quyết định; nếu so với `ColorPoint`, hãy xét cả màu. Cách này khiến mỗi cặp `Point`–`ColorPoint` có thể đối xứng, nhưng lại làm hỏng **tính bắc cầu**.

Tạo tệp đầy đủ `InheritanceTrapDemo.java`:

```java
import java.util.Objects;

public class InheritanceTrapDemo {
    static class Point {
        private final int x;
        private final int y;

        Point(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof Point other)) {
                return false;
            }
            return x == other.x && y == other.y;
        }

        @Override
        public int hashCode() {
            return Objects.hash(x, y);
        }
    }

    static final class ColorPoint extends Point {
        private final String color;

        ColorPoint(int x, int y, String color) {
            super(x, y);
            this.color = Objects.requireNonNull(color);
        }

        @Override
        public boolean equals(Object obj) {
            if (!(obj instanceof Point)) {
                return false;
            }
            if (!(obj instanceof ColorPoint other)) {
                // Chấp nhận Point thường theo định nghĩa của lớp cha.
                return obj.equals(this);
            }
            return super.equals(other) && color.equals(other.color);
        }

        @Override
        public int hashCode() {
            // Phải khớp cả Point thường nếu equals cho rằng chúng bằng nhau.
            return super.hashCode();
        }
    }

    public static void main(String[] args) {
        Point plain = new Point(1, 2);
        ColorPoint red = new ColorPoint(1, 2, "red");
        ColorPoint blue = new ColorPoint(1, 2, "blue");

        System.out.println(red.equals(plain));
        System.out.println(plain.equals(blue));
        System.out.println(red.equals(blue));
    }
}
```

Biên dịch và chạy trên JDK 17+:

```bash
javac InheritanceTrapDemo.java
java InheritanceTrapDemo
```

Kết quả:

```text
true
true
false
```

Ta có:

```text
red == plain   (true)
plain == blue  (true)
red == blue    (false)  <-- mâu thuẫn với tính bắc cầu
```

Vì `Point` xem hai đối tượng cùng tọa độ là bằng nhau, nó trở thành cầu nối giữa hai `ColorPoint` khác màu. Hai `ColorPoint` kia lại không bằng nhau theo định nghĩa mới. Đây là mâu thuẫn logic của cách tổ chức giá trị, không đơn thuần là lỗi điều kiện `if`.

Trong ví dụ, `hashCode()` của `ColorPoint` cố tình dùng `super.hashCode()` để không tạo thêm vi phạm quy tắc “bằng nhau ⇒ cùng mã băm” cho các cặp có `equals` trả `true`. Điều đó **không cứu được tính bắc cầu**, cũng không có nghĩa đây là implementation nên dùng trong sản phẩm. Lưu ý đoạn gọi `obj.equals(this)` chỉ minh họa trường hợp `Point` đơn giản này; nếu có thêm subclass với quy tắc so sánh riêng, cách chuyển quyền qua lại còn có thể phát sinh vấn đề khác.

## 4. Giải pháp: composition thay cho extends

**Composition (kết hợp đối tượng)** nghĩa là `ColorPoint` **chứa một `Point` làm thành phần** thay vì tự nhận mình là một subtype của `Point`.

```text
Kế thừa:                 Composition:

ColorPoint               ColorPoint
    extends Point            has-a Point
    + color                   + color
```

Khi đó có hai miền giá trị rõ ràng:

- `Point` so sánh tọa độ với các `Point` khác.
- `ColorPoint` so sánh tọa độ **và màu** với các `ColorPoint` khác.
- `Point` và `ColorPoint` không bị buộc phải coi nhau là bằng nhau chỉ vì có chung tọa độ.
- Nếu một API chỉ cần tọa độ, `ColorPoint` có thể **cung cấp thành phần `Point`** qua `position()` hoặc một phương thức chuyển đổi rõ ràng.

Tạo tệp đầy đủ `CompositionDemo.java`:

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class CompositionDemo {
    static final class Point {
        private final int x;
        private final int y;

        Point(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof Point other)) {
                return false;
            }
            return x == other.x && y == other.y;
        }

        @Override
        public int hashCode() {
            return Objects.hash(x, y);
        }
    }

    static final class ColorPoint {
        private final Point point;
        private final String color;

        ColorPoint(Point point, String color) {
            this.point = Objects.requireNonNull(point);
            this.color = Objects.requireNonNull(color);
        }

        Point position() {
            return point;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof ColorPoint other)) {
                return false;
            }
            return point.equals(other.point)
                    && color.equals(other.color);
        }

        @Override
        public int hashCode() {
            return Objects.hash(point, color);
        }
    }

    public static void main(String[] args) {
        Point plain = new Point(1, 2);
        ColorPoint red = new ColorPoint(new Point(1, 2), "red");
        ColorPoint redCopy = new ColorPoint(new Point(1, 2), "red");
        ColorPoint blue = new ColorPoint(new Point(1, 2), "blue");

        System.out.println(plain.equals(red));
        System.out.println(red.equals(plain));
        System.out.println(red.equals(redCopy));
        System.out.println(red.equals(blue));
        System.out.println(red.position().equals(plain));

        Set<Object> unique = new HashSet<>();
        unique.add(plain);
        unique.add(red);
        unique.add(redCopy);
        unique.add(blue);
        System.out.println(unique.size());
    }
}
```

Biên dịch và chạy:

```bash
javac CompositionDemo.java
java CompositionDemo
```

Kết quả:

```text
false
false
true
false
true
3
```

**Giải thích:**

1. `plain.equals(red)` và `red.equals(plain)` cùng `false` bởi hai kiểu giá trị khác nhau; không xảy ra bất đối xứng.
2. `red.equals(redCopy)` là `true`: hai vị trí bằng nhau và hai màu bằng nhau. `hashCode()` của cả hai được tính từ cùng bộ thành phần `point` + `color`.
3. `red.equals(blue)` là `false` vì màu khác nhau. Không có một `Point` trung gian nào đồng thời bằng cả hai `ColorPoint`; loại bỏ bẫy bắc cầu đã nêu.
4. `red.position().equals(plain)` là `true`: người gọi vẫn lấy được *giá trị tọa độ* khi chỉ cần so sánh vị trí, mà không lẫn nó với equality của toàn bộ điểm có màu.
5. `HashSet` chứa đúng ba giá trị khác nhau: `plain`, `red`, `blue`; `redCopy` không tạo mục mới do bằng `red`.

Ở đây `Point` và `ColorPoint` đều `final`; dữ liệu gồm hai số nguyên và chuỗi `String` bất biến, nên mã băm không bị thay đổi sau khi đưa đối tượng vào tập hợp. Việc trả về trực tiếp `point` là an toàn **trong ví dụ vì `Point` bất biến**. Nếu thành phần bên trong có thể thay đổi, cần cân nhắc bản sao phòng vệ hoặc một giao diện chỉ đọc để bảo vệ bất biến và tính nhất quán của equality.

## 5. Vì sao composition giúp giữ hợp đồng tốt hơn?

| Tiêu chí | Kế thừa lớp giá trị rồi thêm trường vào equality | Composition |
| --- | --- | --- |
| Quan hệ kiểu | `ColorPoint` cũng là một `Point` | `ColorPoint` có một `Point` |
| Định nghĩa bình đẳng | Lớp cha và lớp con có nguy cơ xung đột | Hai loại giá trị xác định equality độc lập |
| Đối xứng, bắc cầu | Dễ vi phạm nếu lớp cha cho phép subclass bằng nhau | Dễ chứng minh hơn với các kiểu `final` và thành phần ổn định |
| `hashCode` | Phải giải quyết các đối tượng “bằng nhau” chéo lớp | Tính theo đúng thành phần của từng kiểu |
| Thay thế ở API nhận `Point` | Có thể truyền `ColorPoint` trực tiếp | Cần lấy `position()` hoặc chuyển đổi tường minh |
| Ý nghĩa thiết kế | Cam kết “is-a” / thay thế được | Diễn đạt quan hệ “has-a” và quyền sở hữu thành phần |

Composition có đánh đổi thực tế: `ColorPoint` không còn được truyền trực tiếp vào phương thức có tham số `Point`. Đây là thay đổi API có chủ ý. Nếu một API chỉ cần vị trí, ta có thể gọi `render(colorPoint.position())`; nếu API thực sự cần cả vị trí và màu, hãy dùng abstraction hoặc tham số phù hợp, thay vì giả vờ rằng hai kiểu có cùng identity.

**Composition không tự động làm equality đúng.** Bạn vẫn phải cài `equals(Object)` và `hashCode()` cùng một định nghĩa, xử lý `null`, trạng thái có thể thay đổi và lớp con. Nó chỉ loại bỏ sự xung đột không cần thiết giữa equality của hai lớp trong quan hệ kế thừa.

## 6. Java record là một lựa chọn ngắn gọn cho giá trị bất biến

Khi mục tiêu là mô hình hóa dữ liệu bất biến theo các thành phần, Java 17 có `record`. Sau đây là **đoạn khai báo minh họa** có thể đặt trong một tệp nguồn Java cùng cấp hoặc làm các kiểu lồng nhau:

```java
record Point(int x, int y) {}

record ColorPoint(Point position, String color) {
    ColorPoint {
        Objects.requireNonNull(position);
        Objects.requireNonNull(color);
    }
}
```

Đoạn trích cần `import java.util.Objects;`. Java tự sinh `equals(Object)` và `hashCode()` cho record dựa trên các thành phần đã khai báo, cùng cách kiểm tra kiểu phù hợp với record. `Point(1,2)` là một giá trị vị trí, còn `ColorPoint(new Point(1,2),"red")` là giá trị vị trí có màu: chúng không bị nhập nhằng thành cùng một kiểu bởi kế thừa.

Record không phải lời giải cho mọi trường hợp. Nếu một thành phần tham chiếu tới đối tượng có thể thay đổi, record chỉ giữ **tham chiếu** đó ở trường `final`, chứ không tự sao chép hay làm bất biến sâu. Nếu equality nghiệp vụ không tương ứng với tất cả thành phần của record, cần thiết kế khác.

## 7. Khi nào nên chọn composition và khi nào cân nhắc kế thừa?

**Ưu tiên composition** khi:

- Subclass định **thêm trường tham gia vào khái niệm bằng nhau theo giá trị** so với lớp cha, như thêm `color`, `currency` hay `unit`.
- Lớp cha đã có hợp đồng `equals` nhận các subclass là bằng nhau theo dữ liệu riêng của nó.
- Bạn không kiểm soát được cách lớp cha triển khai `equals` và `hashCode` (ví dụ lớp từ thư viện).
- Bạn muốn giữ rõ ràng ranh giới giữa một giá trị nền (`Point`) và giá trị mở rộng (`ColorPoint`).

**Kế thừa vẫn có thể phù hợp** khi subtype thực sự thay thế được supertype và không làm sai cam kết giá trị. Ví dụ một hierarchy của hành vi có thể sử dụng polymorphism mà không cần equality theo dữ liệu ở mỗi subclass; hoặc toàn bộ hierarchy được thiết kế và kiểm soát từ đầu bằng quy tắc equality thống nhất. Không có quy tắc rằng mọi trường hợp `extends` đều sai.

Có thể cân nhắc `getClass()` để chỉ coi các đối tượng cùng lớp là bằng nhau, hoặc một giao thức tương tác giữa lớp cha/con được thiết kế cẩn thận. Nhưng những cách đó thay đổi ý nghĩa equality và đòi hỏi hợp đồng toàn hierarchy nhất quán; thêm một phương thức kiểm tra kiểu đơn lẻ không tự chữa mọi vấn đề. Nếu muốn nhiều kiểu hỗ trợ cùng hành vi, interface mô tả hành vi có thể phù hợp hơn so với dùng chung kế thừa từ một lớp giá trị.

## 8. Checklist để thiết kế và kiểm thử

1. **Định nghĩa “bằng nhau” trước khi viết code:** yếu tố nào quyết định hai giá trị là một? Các kiểu có khác nhau về identity không?
2. **Kiểm tra quan hệ is-a:** có thể thay `Point` bằng `ColorPoint` ở mọi nơi mà hợp đồng vẫn đúng không? Nếu không, chọn quan hệ chứa đối tượng.
3. **Dùng đúng chữ ký:** `public boolean equals(Object obj)` kèm `@Override`; viết `hashCode()` từ cùng các trường tham gia equality.
4. **Kiểm thử đối xứng theo hai chiều:** `a.equals(b)` và `b.equals(a)` với cả cùng lớp và khác lớp.
5. **Kiểm thử bắc cầu trên ba đối tượng:** đặc biệt thử `red`, `plain`, `blue` có cùng vị trí nhưng màu khác nhau.
6. **Kiểm tra tính nhất quán và trạng thái:** nếu đối tượng được dùng làm khóa `HashMap` hoặc phần tử `HashSet`, tránh thay đổi trường tham gia `equals/hashCode` trong thời gian nó nằm trong bộ sưu tập.
7. **Kiểm thử qua API chung:** so sánh dưới kiểu `Object`, qua `Objects.equals`, và đưa giá trị vào `HashSet` để phát hiện lỗi hợp đồng mà cách gọi trực tiếp có thể bỏ sót.
8. **Giữ trách nhiệm rõ ràng:** API nào chỉ cần tọa độ thì nhận `Point`; API nào cần thông tin màu thì nhận `ColorPoint` hoặc abstraction thể hiện đủ dữ liệu.

**Tự kiểm tra:** Nếu `Point(1,2)` bằng cả `ColorPoint(1,2,"red")` và `ColorPoint(1,2,"blue")`, còn hai điểm có màu này không bằng nhau, hợp đồng nào bị vi phạm? **Tính bắc cầu.** Nếu `Point` nói “bằng” và `ColorPoint` nói “không bằng” cho cùng một cặp thì bị vi phạm **tính đối xứng**. Composition giúp định nghĩa các miền giá trị riêng và cung cấp tọa độ tường minh khi cần.

**Ghi nhớ:** Kế thừa là một cam kết thay thế được, trong khi equality là hợp đồng logic áp dụng xuyên suốt các lời gọi và collection. Khi subclass thêm thành phần giá trị làm tiêu chí equality của lớp cha không còn đủ, composition thường là thiết kế rõ ràng và ổn định hơn.