# Tính đối xứng khi đổi vị trí hai đối tượng trong hợp đồng `equals()`

## 1. Khái niệm và yêu cầu của hợp đồng

Trong Java, `Object.equals(Object)` diễn tả việc hai đối tượng có được xem là **bằng nhau về mặt logic** hay không. Một yêu cầu bắt buộc của hợp đồng `equals` là **tính đối xứng (symmetry)**:

> Với hai tham chiếu `a` và `b` không null, `a.equals(b)` phải trả về cùng kết quả với `b.equals(a)`.

Công thức kiểm tra:

```java
a.equals(b) == b.equals(a)
```

Yêu cầu này đúng khi cả hai kết quả là `true` **hoặc** cả hai là `false`. Nếu `a.equals(b)` là `true` nhưng `b.equals(a)` là `false`, lớp đó vi phạm hợp đồng. “Đổi vị trí” tức là hoán đổi **đối tượng nhận lời gọi** và **đối số**, chứ không phải đổi thứ tự so sánh các thuộc tính trong cùng đối tượng.

Chẳng hạn, hai đối tượng cùng mô tả tọa độ (3, 4) phải thống nhất kết luận bằng nhau ở cả hai chiều. Nếu một đối tượng còn biểu diễn màu sắc mà đối tượng kia không có màu sắc, thiết kế quan hệ bằng nhau phải giải quyết rõ việc chúng có được coi là cùng một giá trị hay không.

Symmetry là một trong năm yêu cầu của hợp đồng `equals`, cùng với tính phản xạ, bắc cầu, nhất quán và so sánh với `null` luôn trả về `false`. Đạt symmetry **chưa đủ** để khẳng định `equals` hợp lệ toàn diện. Nếu ghi đè `equals`, cũng phải bảo đảm các đối tượng bằng nhau có cùng `hashCode()`.

## 2. Tại sao đổi chiều lại cho kết quả khác?

Lỗi xuất hiện rõ nhất khi lớp cha và lớp con sử dụng **hai tiêu chí bằng nhau không tương thích**:

1. Lớp cha `Point` chỉ so sánh tọa độ `x`, `y` và sử dụng `instanceof Point`, nên chấp nhận cả `ColoredPoint` là một `Point`.
2. Lớp con `ColoredPoint` bổ sung trường `color` và chỉ chấp nhận đối tượng `ColoredPoint`.
3. Khi gọi `point.equals(coloredPoint)`, lớp cha nhìn thấy cùng tọa độ và trả về `true`; khi gọi theo chiều ngược lại, lớp con nhìn thấy kiểu không tương thích và trả về `false`.

Java cho phép mã này biên dịch, vì trình biên dịch không kiểm chứng được mọi tính chất của quan hệ bằng nhau.

## 3. Ví dụ Java 17: sai ở đâu, sửa thế nào?

Lưu chương trình đầy đủ sau trong tệp **`EqualsSymmetryDemo.java`**. Ví dụ đầu cố tình vi phạm đối xứng. Ví dụ sau biểu diễn điểm có màu bằng **composition**: một đối tượng chứa tọa độ và màu, thay vì kế thừa một lớp với định nghĩa bằng nhau khác.

```java
import java.util.Objects;

public class EqualsSymmetryDemo {
    static class Point {
        private final int x;
        private final int y;

        Point(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof Point p)) return false;
            return x == p.x && y == p.y;
        }

        @Override
        public int hashCode() {
            return Objects.hash(x, y);
        }
    }

    static final class ColoredPoint extends Point {
        private final String color;

        ColoredPoint(int x, int y, String color) {
            super(x, y);
            this.color = Objects.requireNonNull(color);
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof ColoredPoint p)) return false;
            return super.equals(p) && color.equals(p.color);
        }

        // Kế thừa Point.hashCode() để tập trung minh họa
        // lỗi symmetry; trùng hash giữa hai màu khác nhau là hợp lệ.
    }

    record SafePoint(int x, int y) {}

    record SafeColoredPoint(SafePoint point, String color) {
        SafeColoredPoint {
            Objects.requireNonNull(point);
            Objects.requireNonNull(color);
        }
    }

    static void assertSymmetric(Object a, Object b) {
        boolean forward = Objects.equals(a, b);
        boolean backward = Objects.equals(b, a);
        if (forward != backward) {
            throw new AssertionError("equals is not symmetric");
        }
    }

    public static void main(String[] args) {
        Point base = new Point(3, 4);
        ColoredPoint red = new ColoredPoint(3, 4, "red");

        System.out.println("base.equals(red) = " + base.equals(red));
        System.out.println("red.equals(base) = " + red.equals(base));

        SafePoint plain = new SafePoint(3, 4);
        SafeColoredPoint colored = new SafeColoredPoint(plain, "red");
        SafeColoredPoint copy =
                new SafeColoredPoint(new SafePoint(3, 4), "red");

        System.out.println("plain.equals(colored) = " + plain.equals(colored));
        System.out.println("colored.equals(plain) = " + colored.equals(plain));
        System.out.println("colored.equals(copy) = " + colored.equals(copy));

        assertSymmetric(plain, colored);
        assertSymmetric(colored, copy);
        assertSymmetric(plain, new SafePoint(3, 4));
        assertSymmetric(plain, null);
        System.out.println("safe symmetry checks = PASS");
    }
}
```

Tại thư mục chứa tệp, thực thi:

```bash
javac EqualsSymmetryDemo.java
java EqualsSymmetryDemo
```

Kết quả trên Java 17+:

```text
base.equals(red) = true
red.equals(base) = false
plain.equals(colored) = false
colored.equals(plain) = false
colored.equals(copy) = true
safe symmetry checks = PASS
```

**Diễn giải:**

- `base.equals(red)` là `true` vì `red instanceof Point` đúng và cả hai tọa độ bằng nhau. Phương thức lớp cha bỏ qua màu.
- `red.equals(base)` là `false` vì `base instanceof ColoredPoint` sai. Đây chính là vi phạm đối xứng: cùng một cặp nhưng hai chiều trái ngược.
- `plain.equals(colored)` và `colored.equals(plain)` cùng `false`. Hai kiểu `record` độc lập biểu diễn hai loại giá trị khác nhau, nên hai phía không coi nhau là bằng nhau.
- `colored.equals(copy)` là `true`: hai đối tượng `SafeColoredPoint` có điểm và màu tương ứng bằng nhau. `record` tự cung cấp `equals` và `hashCode` dựa trên các thành phần.
- `assertSymmetric` kiểm tra hai hướng kể cả trường hợp `null`; nếu gọi `assertSymmetric(base, red)`, hàm sẽ ném `AssertionError`.

Trong phần mã lỗi, `ColoredPoint` giữ `hashCode` kế thừa chỉ dựa vào tọa độ. Hai điểm khác màu có thể cùng hash dù không bằng nhau, và **va chạm hash là hợp lệ**; việc đó giúp minh họa riêng lỗi symmetry. Tuy vậy, trong thiết kế hoàn chỉnh, hãy chọn thành phần hash theo mô hình bằng nhau hợp lệ và đảm bảo hai đối tượng bằng nhau luôn có cùng hash.

## 4. Thiết kế `equals` để bảo toàn tính đối xứng

### Giải pháp A: lớp giá trị `final`, `record` và composition

Nếu đối tượng là một giá trị có tập thuộc tính xác định, lớp `final` ngăn lớp con thay đổi cách hiểu quan hệ bằng nhau. `record` phù hợp với đối tượng dữ liệu bất biến theo các thành phần: Java tự sinh `equals`/`hashCode` theo thành phần và kiểu `record`. Trong ví dụ, `SafeColoredPoint` chứa `SafePoint` nên màu sắc không bị lẫn vào hợp đồng bằng nhau của `SafePoint`.

Composition đặc biệt hữu ích khi một kiểu mới **có thêm thuộc tính quyết định danh tính**. Nếu kế thừa kiểu cũ chỉ để tái sử dụng dữ liệu mà rồi sửa cách so sánh, có thể làm hỏng đối xứng hoặc bắc cầu.

### Giải pháp B: xác nhận cùng kiểu runtime bằng `getClass()`

Nếu các đối tượng thuộc **hai lớp runtime khác nhau không được xem là bằng nhau**, có thể thay `Point.equals` trong chương trình trên bằng phương thức sau:

```java
@Override
public boolean equals(Object other) {
    if (this == other) return true;
    if (other == null || getClass() != other.getClass()) return false;
    Point p = (Point) other;
    return x == p.x && y == p.y;
}
```

Đây là **đoạn thay thế trong lớp `Point`**, không phải chương trình độc lập. Khi ấy, `Point.equals(ColoredPoint)` và `ColoredPoint.equals(Point)` cùng trả về `false`. Với hai đối tượng đều là `ColoredPoint`, lời gọi `super.equals(p)` trong lớp con vẫn có thể so sánh tọa độ rồi kiểm tra màu.

Cần lưu ý: `getClass()` coi lớp runtime là một phần của danh tính logic. Nếu bài toán thật sự yêu cầu đối tượng thuộc các lớp khác nhau có thể bằng nhau, kiểm tra chặt kiểu có thể không phù hợp. Không có một lệnh thay thế máy móc cho mọi mô hình phân cấp.

### Giải pháp C: một quy tắc bằng nhau thống nhất trong toàn hệ phân cấp

Nếu cần cho phép so sánh bằng nhau xuyên lớp, toàn bộ hệ phân cấp phải chia sẻ cách xác định danh tính và duy trì **cả tính đối xứng lẫn tính bắc cầu**. Không thể để lớp cha coi tọa độ là đủ, còn lớp con vừa yêu cầu thêm màu, vừa kỳ vọng so sánh qua lớp cha vẫn giữ hợp đồng trong mọi trường hợp.

Một lựa chọn là đặt mọi thuộc tính quyết định bình đẳng vào cùng một mô hình giá trị thống nhất; lựa chọn khác là định nghĩa các kiểu giá trị độc lập và chuyển dữ liệu theo một chuẩn chung trước khi so sánh. Khi không có lý do nghiệp vụ rõ ràng để bằng nhau xuyên kiểu, `final`/`record` và composition thường dễ duy trì hơn.

## 5. Cách kiểm thử và các lỗi thường gặp

Kiểm thử theo cặp phải quan sát **hai lời gọi riêng biệt**:

```java
boolean leftToRight = Objects.equals(a, b);
boolean rightToLeft = Objects.equals(b, a);
if (leftToRight != rightToLeft) {
    throw new AssertionError("Broken symmetry");
}
```

Đoạn trên sử dụng `a`, `b` có sẵn; hàm `assertSymmetric` trong chương trình đầy đủ là phiên bản chạy được. `Objects.equals(a, b)` chỉ xử lý null an toàn rồi dựa vào `a.equals(b)`; **nó không tự sửa quan hệ bằng nhau thiếu đối xứng**. Vì thế cần so với `Objects.equals(b, a)`.

Nên lập bộ cặp gồm: cùng lớp/cùng giá trị; cùng lớp/khác giá trị; đối tượng cha–con ở cả hai hướng; hai lớp con khác nhau; đối tượng với `null`; và hai đối tượng trỏ cùng tham chiếu. Cặp cha–con rất quan trọng vì nó làm lộ tiêu chí kiểm tra kiểu không thống nhất. Ngoài symmetry, hãy kiểm tra phản xạ, bắc cầu, nhất quán và điều kiện hash của các đối tượng bằng nhau.

| Lỗi | Vì sao nguy hiểm | Cách xử lý |
| --- | --- | --- |
| Cha dùng `instanceof` rộng, con chỉ nhận đúng lớp con | Một chiều `true`, chiều kia `false` | Thống nhất phạm vi kiểu được coi là bằng nhau |
| Chỉ kiểm tra `a.equals(b)` | Bỏ sót kết quả trái chiều | Kiểm tra cả `b.equals(a)` |
| Viết `equals(Point)` thay vì `equals(Object)` | Đây là overload, không ghi đè phương thức của `Object` | Dùng đúng chữ ký và `@Override` |
| Ghi đè `equals` nhưng quên `hashCode` | Hai đối tượng bằng nhau có thể cho hash khác nhau | Xây dựng cả hai theo cùng quan hệ bằng nhau |
| Dùng `==` để so đối tượng cần bằng nhau theo giá trị | So sánh cùng tham chiếu thay vì cùng giá trị | Xác định rõ so identity hay logical equality |
| Dùng thuộc tính thay đổi được trong equality/hash của khóa `HashMap` | Có thể không tìm lại khóa sau khi thay đổi | Ưu tiên khóa giá trị bất biến |

**Bài tự kiểm tra:** `A.equals` chỉ xét `id` và chấp nhận `instanceof A`; lớp con `B.equals` chỉ chấp nhận `B`, xét cả `id` và `role`. Với `new A(7)` và `new B(7, "admin")`, chiều `A → B` sẽ là `true`, còn chiều `B → A` sẽ là `false`. Cách sửa phải làm cho cả hai chiều thống nhất và vẫn giữ các yêu cầu còn lại của `equals`.

Trước khi triển khai `equals`, hãy xác định rõ **hai kiểu nào được phép bằng nhau và dựa trên các thuộc tính nào**, sau đó kiểm tra mỗi cặp theo cả hai hướng.