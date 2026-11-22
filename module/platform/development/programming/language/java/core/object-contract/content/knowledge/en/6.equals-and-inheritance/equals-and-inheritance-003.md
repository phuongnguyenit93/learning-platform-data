# Kiểm tra kiểu bằng `instanceof` hoặc `getClass()` khi cài đặt `equals()` trong Java

## 1. Vì sao việc kiểm tra kiểu ảnh hưởng đến `equals()`?

Trong Java, `equals(Object other)` quyết định khi nào hai **đối tượng** được coi là bằng nhau theo ý nghĩa của lớp. Trước khi so sánh các trường dữ liệu, phương thức thường kiểm tra xem đối tượng bên phải có thuộc **miền đối tượng được phép so sánh bằng nhau** với đối tượng bên trái hay không.

Khi một lớp có thể được kế thừa, hai cách kiểm tra thường dẫn đến chính sách khác nhau:

- `other instanceof Point`: chấp nhận đối tượng của `Point` **và mọi lớp con** của `Point` (nếu không `null`). Đây là kiểm tra **cùng kiểu hoặc kiểu con**.
- `getClass() == other.getClass()`: chỉ chấp nhận hai đối tượng có **chính xác cùng lớp lúc chạy**. Đây là kiểm tra **lớp thực tế giống hệt nhau**.

Sự khác biệt quan trọng nhất xuất hiện khi lớp con bổ sung trường dữ liệu hoặc ghi đè `equals()`. Một lớp cha có thể xem lớp con là bằng nhau theo các trường của cha, trong khi lớp con lại cần so sánh thêm trường riêng. Nếu triển khai thiếu nhất quán, `equals()` có thể vi phạm tính **đối xứng** hoặc **bắc cầu**.

Chủ đề này nói về **chọn miền so sánh kiểu trong `equals()`**. Toán tử `==` giữa hai biến tham chiếu vẫn kiểm tra **danh tính đối tượng**, không phải tiêu chí bằng nhau do `equals()` định nghĩa.

## 2. Phân biệt chính xác `instanceof` và `getClass()`

### `instanceof`: chấp nhận quan hệ kế thừa hoặc triển khai interface

Với biểu thức `obj instanceof T`, kết quả là `true` nếu đối tượng lúc chạy là thể hiện của `T`, lớp con của `T`, hoặc lớp triển khai interface `T` (theo quan hệ kiểu phù hợp); nếu `obj == null`, kết quả luôn `false`.

Java 17 hỗ trợ **pattern matching cho `instanceof`**:

```java
if (other instanceof Point point) {
    // point đã có kiểu Point, không cần ép kiểu thủ công.
}
```

Pattern chỉ khai báo biến `point` ở nơi trình biên dịch xác định phép kiểm tra đã thành công. Ví dụ `if (!(other instanceof Point point)) return false;` cho phép dùng `point` sau câu `if` vì nhánh thất bại đã thoát.

### `getClass()`: yêu cầu lớp lúc chạy trùng khớp hoàn toàn

`Object.getClass()` trả về đối tượng `Class<?>` đại diện cho **lớp thực tế lúc chạy**, không phải kiểu khai báo của biến. So sánh hai đối tượng `Class` bằng `==` là phù hợp vì cùng lớp trong cùng ngữ cảnh nạp lớp được đại diện bởi cùng đối tượng `Class`.

```java
if (other == null || getClass() != other.getClass()) {
    return false;
}
```

Phải kiểm tra `other == null` trước khi gọi `other.getClass()`: nếu không sẽ có `NullPointerException`. Trái lại, `null instanceof Point` đơn giản trả về `false`.

### Ví dụ chạy được: kiểu khai báo không quyết định `getClass()`

Tạo tệp `TypeCheckDemo.java`:

```java
public class TypeCheckDemo {
    interface Identified {}

    static class Parent implements Identified {}

    static final class Child extends Parent {}

    public static void main(String[] args) {
        Parent polymorphic = new Child();
        Parent parent = new Parent();
        Object nothing = null;

        System.out.println("is Parent: " + (polymorphic instanceof Parent));
        System.out.println("is Child: " + (polymorphic instanceof Child));
        System.out.println("is Identified: " + (polymorphic instanceof Identified));
        System.out.println("exact Parent: " + (polymorphic.getClass() == Parent.class));
        System.out.println("exact Child: " + (polymorphic.getClass() == Child.class));
        System.out.println("parent exact Parent: " + (parent.getClass() == Parent.class));
        System.out.println("null instanceof Parent: " + (nothing instanceof Parent));
    }
}
```

Biên dịch và chạy (Java 17+):

```bash
javac -encoding UTF-8 TypeCheckDemo.java
java TypeCheckDemo
```

Stdout:

```text
is Parent: true
is Child: true
is Identified: true
exact Parent: false
exact Child: true
parent exact Parent: true
null instanceof Parent: false
```

Biến `polymorphic` khai báo là `Parent` nhưng chứa đối tượng `Child`. Vì thế `instanceof Parent` là `true`, còn `polymorphic.getClass() == Parent.class` là `false`. Trong trường hợp này, `getClass()` có kết quả `Child.class`.

## 3. Nhắc lại hợp đồng `equals()` trước khi chọn cách kiểm tra kiểu

Với các tham chiếu đối tượng không `null`, một cách triển khai `equals()` đúng phải thỏa mãn:

1. **Phản xạ (reflexive):** `x.equals(x)` luôn `true`.
2. **Đối xứng (symmetric):** `x.equals(y)` và `y.equals(x)` luôn có cùng giá trị.
3. **Bắc cầu (transitive):** nếu `x.equals(y)` và `y.equals(z)` đều `true`, thì `x.equals(z)` cũng phải `true`.
4. **Nhất quán (consistent):** nhiều lần so sánh cho cùng kết quả khi trạng thái có liên quan không thay đổi.
5. **Với `null`:** `x.equals(null)` là `false`.

Hợp đồng đi kèm của `hashCode()`: **nếu `x.equals(y)` là `true`, thì `x.hashCode() == y.hashCode()` phải đúng**. Điều ngược lại không bắt buộc: hai đối tượng khác nhau vẫn có thể trùng mã băm.

Các collection như `HashSet` và `HashMap` cần cả `equals()` và `hashCode()` vận hành nhất quán. Chọn `instanceof` hay `getClass()` chưa đủ để bảo đảm toàn bộ hợp đồng: còn phải xem trường nào tham gia so sánh, tính bất biến của dữ liệu và cách lớp con ghi đè phương thức.

## 4. Rủi ro khi lớp cha dùng `instanceof`, lớp con bổ sung tiêu chí bằng nhau

Giả sử lớp `Point` chỉ quan tâm tọa độ `x, y`. Lớp con `ColoredPoint` có thêm `color` và muốn màu sắc cũng tham gia định nghĩa bằng nhau.

Tạo tệp `BadInstanceofDemo.java`:

```java
import java.util.Objects;

public class BadInstanceofDemo {
    static class Point {
        final int x;
        final int y;

        Point(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public boolean equals(Object obj) {
            if (!(obj instanceof Point other)) return false;
            return x == other.x && y == other.y;
        }

        @Override
        public int hashCode() {
            return Objects.hash(x, y);
        }
    }

    static final class ColoredPoint extends Point {
        final String color;

        ColoredPoint(int x, int y, String color) {
            super(x, y);
            this.color = Objects.requireNonNull(color);
        }

        @Override
        public boolean equals(Object obj) {
            if (!(obj instanceof ColoredPoint other)) return false;
            return super.equals(other) && color.equals(other.color);
        }

        @Override
        public int hashCode() {
            return 31 * super.hashCode() + color.hashCode();
        }
    }

    public static void main(String[] args) {
        Point plain = new Point(1, 2);
        ColoredPoint red = new ColoredPoint(1, 2, "red");

        System.out.println("plain.equals(red): " + plain.equals(red));
        System.out.println("red.equals(plain): " + red.equals(plain));
    }
}
```

```bash
javac -encoding UTF-8 BadInstanceofDemo.java
java BadInstanceofDemo
```

Stdout:

```text
plain.equals(red): true
red.equals(plain): false
```

Đây là **ví dụ CỐ Ý SAI** để nhìn thấy lỗi:

- `plain.equals(red)` kiểm tra `red instanceof Point`, điều kiện đúng, rồi chỉ so `x, y`: kết quả `true`.
- `red.equals(plain)` kiểm tra `plain instanceof ColoredPoint`, điều kiện sai: kết quả `false`.
- Hợp đồng **đối xứng** bị phá vỡ. Hai `hashCode()` còn có thể khác nhau dù phép so sánh từ phía `plain` trả `true`, làm thiết kế càng không phù hợp với collection dựa trên hash.

Không nên “vá” lỗi đơn thuần bằng cách cho lớp con bỏ qua màu khi gặp `Point`. Nếu `Point(1,2)` được coi bằng cả điểm đỏ và điểm xanh, nhưng hai điểm có màu khác nhau lại không bằng nhau, tính **bắc cầu** cũng có thể bị phá vỡ. Cần chọn một chính sách bằng nhau nhất quán cho toàn bộ phân cấp lớp.

## 5. Giải pháp dùng `getClass()`: chỉ bằng nhau khi cùng lớp thực tế

Khi `Point` và `ColoredPoint` đại diện cho **hai kiểu giá trị khác nhau**, không cho chúng bằng nhau qua ranh giới lớp là một lựa chọn rõ ràng. Mỗi lớp trước tiên so `getClass()`, rồi mới so những trường xác định giá trị của lớp đó.

Tạo tệp `ExactClassEqualityDemo.java`:

```java
import java.util.Objects;

public class ExactClassEqualityDemo {
    static class Point {
        final int x;
        final int y;

        Point(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (obj == null || getClass() != obj.getClass()) return false;
            Point other = (Point) obj;
            return x == other.x && y == other.y;
        }

        @Override
        public int hashCode() {
            return Objects.hash(x, y);
        }
    }

    static final class ColoredPoint extends Point {
        final String color;

        ColoredPoint(int x, int y, String color) {
            super(x, y);
            this.color = Objects.requireNonNull(color);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (obj == null || getClass() != obj.getClass()) return false;
            ColoredPoint other = (ColoredPoint) obj;
            return super.equals(other) && color.equals(other.color);
        }

        @Override
        public int hashCode() {
            return 31 * super.hashCode() + color.hashCode();
        }
    }

    public static void main(String[] args) {
        Point plain = new Point(1, 2);
        ColoredPoint red = new ColoredPoint(1, 2, "red");
        ColoredPoint redCopy = new ColoredPoint(1, 2, "red");
        ColoredPoint blue = new ColoredPoint(1, 2, "blue");

        System.out.println("plain.equals(red): " + plain.equals(red));
        System.out.println("red.equals(plain): " + red.equals(plain));
        System.out.println("red.equals(redCopy): " + red.equals(redCopy));
        System.out.println("red.equals(blue): " + red.equals(blue));
        System.out.println("equal hash: " + (red.hashCode() == redCopy.hashCode()));
    }
}
```

```bash
javac -encoding UTF-8 ExactClassEqualityDemo.java
java ExactClassEqualityDemo
```

Stdout:

```text
plain.equals(red): false
red.equals(plain): false
red.equals(redCopy): true
red.equals(blue): false
equal hash: true
```

Ở đây:

- `Point` và `ColoredPoint` **không bao giờ bằng nhau** dù tọa độ giống nhau. Hai chiều so sánh đều `false`, nên tránh được lỗi đối xứng trong ví dụ trước.
- Hai `ColoredPoint` được so theo cả `x, y` (thông qua `super.equals(other)`) và `color`.
- `hashCode()` của `ColoredPoint` kết hợp cùng những phần dữ liệu mà `equals()` dùng. Hai điểm màu bằng nhau chắc chắn có mã băm bằng nhau.
- Việc `super.equals(other)` vẫn đúng trong ví dụ này vì cả `this` và `other` đều là `ColoredPoint` tại thời điểm gọi phương thức của `Point`; kiểm tra `getClass()` ở lớp cha vì thế thành công.

**Lưu ý về thiết kế:** `getClass()` không tự động làm `equals()` đúng. Nếu một lớp con có trạng thái ảnh hưởng đến danh tính giá trị mà lại kế thừa nguyên `equals()` của lớp cha, hai thể hiện cùng lớp con vẫn có thể bị xem là bằng nhau dù trạng thái bổ sung khác nhau. Lớp con phải định nghĩa lại chính sách so sánh và `hashCode()` một cách nhất quán, hoặc phân cấp cần được thiết kế để không cho lớp con thêm dữ liệu ảnh hưởng đến equality.

## 6. Khi nào `instanceof` lại là lựa chọn hợp lệ?

`instanceof` **không sai về bản chất**. Nó hữu ích khi chính sách nghiệp vụ muốn coi các đối tượng trong cùng một phân cấp là bằng nhau theo **một tập thuộc tính chung**, bất kể lớp con cụ thể. Nhưng không thể cho lớp con tùy ý thay đổi tiêu chí equality.

Một cách đảm bảo điều đó là để lớp cha định nghĩa `equals()` và `hashCode()` là `final`, đồng thời quy định rõ các trường bổ sung của lớp con **không góp phần vào equality**.

Tạo tệp `HierarchyEqualityDemo.java`:

```java
public class HierarchyEqualityDemo {
    static class Coordinate {
        final int x;
        final int y;

        Coordinate(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public final boolean equals(Object obj) {
            if (this == obj) return true;
            if (!(obj instanceof Coordinate other)) return false;
            return x == other.x && y == other.y;
        }

        @Override
        public final int hashCode() {
            return 31 * x + y;
        }
    }

    static final class LabeledCoordinate extends Coordinate {
        final String label;

        LabeledCoordinate(int x, int y, String label) {
            super(x, y);
            this.label = label;
        }
    }

    public static void main(String[] args) {
        Coordinate plain = new Coordinate(1, 2);
        LabeledCoordinate a = new LabeledCoordinate(1, 2, "A");
        LabeledCoordinate b = new LabeledCoordinate(1, 2, "B");

        System.out.println("plain.equals(a): " + plain.equals(a));
        System.out.println("a.equals(plain): " + a.equals(plain));
        System.out.println("a.equals(b): " + a.equals(b));
        System.out.println("same hash: " + (plain.hashCode() == a.hashCode()));
    }
}
```

```bash
javac -encoding UTF-8 HierarchyEqualityDemo.java
java HierarchyEqualityDemo
```

Stdout:

```text
plain.equals(a): true
a.equals(plain): true
a.equals(b): true
same hash: true
```

Ở đây hai tọa độ bằng nhau khi cùng `x, y`, **nhãn chỉ là thông tin hiển thị**. Do equality ở lớp cha là `final`, lớp con không thể ghi đè với quy tắc riêng và phá đối xứng. Điều này chỉ phù hợp khi yêu cầu thực sự cho phép bỏ qua `label`; nếu nhãn phân biệt giá trị, cần chính sách equality khác.

Với một **lớp `final` không có lớp con**, hai cách kiểm tra kiểu thường có miền chấp nhận tương đương khi so với chính lớp ấy: `other instanceof MyFinalType` và `other != null && other.getClass() == MyFinalType.class`. Trong trường hợp này, `instanceof` thường ngắn gọn hơn; quyết định chủ yếu cần cân nhắc khi lớp có thể được kế thừa.

## 7. Những tình huống cần xét trước khi quyết định

### Kiểu runtime, proxy và framework

Một số framework có thể tạo **lớp con proxy** của entity hay domain class. `getClass()` đối chiếu lớp runtime một cách nghiêm ngặt, nên một đối tượng proxy và đối tượng thật của lớp gốc có thể bị đánh giá khác lớp dù cùng dữ liệu. Tuy nhiên, thay ngay bằng `instanceof` cũng không tự giải quyết toàn bộ bài toán equality của entity (ví dụ định danh khi chưa lưu, proxy, trạng thái có thể thay đổi). Nếu dùng framework như ORM, hãy theo chính sách equality phù hợp với cơ chế proxy/identity của framework và kiểm tra hai chiều so sánh.

### So sánh với interface hoặc nhiều nhánh kế thừa

`instanceof` có thể chấp nhận đối tượng thuộc các lớp runtime khác nhau cùng triển khai một interface. Điều này hữu ích để **kiểm tra khả năng sử dụng** của đối tượng, nhưng không mặc định có nghĩa mọi hiện thực của interface đều có cùng **ngữ nghĩa bằng nhau**. Trước khi dùng trong `equals()`, phải xác định trường/thuộc tính nào được so sánh và bảo đảm tất cả nhánh tuân cùng tiêu chí.

### Tính ổn định của dữ liệu tham gia equality

Dù chọn cách kiểm tra kiểu nào, dùng các trường **mutable** làm cơ sở cho cả `equals()` và `hashCode()` có thể gây vấn đề sau khi đưa đối tượng vào `HashSet` hoặc làm khóa `HashMap`: sửa trường có thể khiến mã băm hoặc vị trí logic thay đổi. Với value object, nên ưu tiên dữ liệu bất biến và equality nhất quán. Với entity, xác định chính sách riêng theo vòng đời định danh.

### `equals()` không thay thế `==`

`this == other` ở đầu `equals()` là tối ưu hợp lệ: cùng một đối tượng luôn bằng chính nó nếu tuân đúng hợp đồng. Nó không thay thế phần kiểm tra kiểu và so trường đối với **hai đối tượng khác nhau**. Ngược lại, `getClass() == other.getClass()` so sánh **đại diện lớp runtime**, không so xem hai đối tượng dữ liệu có cùng danh tính.

## 8. Bảng chọn nhanh `instanceof` và `getClass()`

| Câu hỏi thiết kế | Hướng lựa chọn |
| --- | --- |
| Hai lớp khác nhau trong phân cấp có được coi bằng nhau không? | Nếu **không**, kiểm tra lớp chính xác bằng `getClass()` là chính sách dễ diễn đạt. |
| Mọi lớp con chỉ là những cách trình bày của cùng một giá trị cơ sở? | Có thể dùng `instanceof` với equality chung ở lớp cha; cân nhắc `final equals()` và `final hashCode()`. |
| Lớp con cần bổ sung trường tham gia equality? | Tránh để lớp cha dùng `instanceof` chấp nhận lớp con trong khi lớp con lại thu hẹp so sánh; cần chính sách toàn phân cấp bảo toàn hợp đồng. |
| Lớp là `final`, không thể kế thừa? | `instanceof` thường đơn giản; `getClass()` cũng có thể đúng nhưng không mang thêm lợi ích rõ rệt. |
| Có proxy/runtime subclass do framework tạo? | Xác minh cách lấy lớp/định danh phù hợp framework trước khi dùng `getClass()` trực tiếp. |
| Đối tượng bên phải có thể là `null`? | `instanceof` tự trả `false`; với `getClass()` phải kiểm tra `null` trước. |

## 9. Checklist kiểm thử `equals()` trong phân cấp kế thừa

Với các lớp `Base`, `ChildA`, `ChildB`, kiểm thử ít nhất:

1. **Cùng đối tượng:** `a.equals(a)` là `true`.
2. **Null:** `a.equals(null)` là `false`.
3. **Cùng lớp:** các đối tượng khác nhau nhưng có cùng trường được coi là giá trị có kết quả equality phù hợp.
4. **Khác lớp:** so cả `base.equals(child)` **và** `child.equals(base)`; chúng phải nhất quán.
5. **Hai lớp con:** so hai thể hiện cùng lớp con và các thể hiện thuộc hai lớp con khác nhau theo chính sách đã chọn.
6. **Bắc cầu:** lập bộ ba `x, y, z` ở những kiểu runtime khác nhau; nếu hai quan hệ đầu là `true`, quan hệ thứ ba phải là `true`.
7. **Hash:** với mọi cặp `x.equals(y)` đúng, kiểm tra `x.hashCode() == y.hashCode()`; thử thêm thao tác với `HashSet`/`HashMap` khi phù hợp.
8. **Trạng thái:** kiểm tra cách đối tượng ứng xử khi dữ liệu tham gia equality có thể bị thay đổi, đặc biệt sau khi dùng làm khóa hash.
9. **Proxy (nếu có):** kiểm tra các cặp đối tượng thật/proxy theo chính sách thực tế của framework.

**Ghi nhớ:** `instanceof` trả lời “đối tượng này thuộc kiểu được yêu cầu hoặc một kiểu con/triển khai phù hợp không?”, còn `getClass()` trả lời “lớp runtime chính xác là gì?”. Khi viết `equals()`, điều quyết định là **ngữ nghĩa bằng nhau trên cả phân cấp lớp**. Phương án đúng phải giữ được đối xứng, bắc cầu và hợp đồng với `hashCode()`, kể cả khi lớp con được bổ sung sau này.