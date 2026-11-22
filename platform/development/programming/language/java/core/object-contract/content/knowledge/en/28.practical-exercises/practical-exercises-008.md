# Rà soát hệ lớp kế thừa làm mất tính đối xứng của equals()

## 1. Vấn đề cần phát hiện

Hợp đồng `Object.equals()` trong Java yêu cầu **tính đối xứng**: với hai tham chiếu khác `null` là `x` và `y`, kết quả `x.equals(y)` phải bằng kết quả `y.equals(x)`.

```text
x.equals(y) == y.equals(x)
```

Lỗi thường gặp khi lớp con bổ sung thuộc tính mới: lớp cha dùng `instanceof Parent` nên vẫn chấp nhận instance lớp con, trong khi lớp con dùng `instanceof Child` nên không chấp nhận instance lớp cha. Hai lời gọi thực hiện hai triển khai `equals()` khác nhau do Java sử dụng **dynamic dispatch**.

Cần phân biệt:
- `a == b` trên hai biến tham chiếu là kiểm tra **cùng đối tượng**.
- `a.equals(b)` là so sánh **bằng nhau theo hợp đồng logic của kiểu**.
- `Object.equals()` mặc định chỉ coi cùng identity là bằng nhau; một lớp ghi đè `equals()` có thể định nghĩa phép bằng nhau theo dữ liệu.

Mục tiêu bài rà soát là tìm cặp cha/con làm mất đối xứng, lần theo nguyên nhân, kiểm tra nguy cơ vi phạm tính bắc cầu và hash, áp dụng một chính sách sửa nhất quán, sau đó viết kiểm thử hồi quy.

## 2. Ví dụ lỗi: Point và ColoredPoint

Giả sử `Point` xác định bằng nhau bằng hai tọa độ `x, y`, còn `ColoredPoint extends Point` bổ sung trường `color` được tính trong phép bằng nhau.

Đây là **trích đoạn minh họa**, không phải tệp Java độc lập:

```java
class Point {
    final int x, y;

    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) return true;
        if (!(obj instanceof Point other)) return false;
        return x == other.x && y == other.y;
    }

    @Override
    public int hashCode() {
        return java.util.Objects.hash(x, y);
    }
}

class ColoredPoint extends Point {
    final String color;

    ColoredPoint(int x, int y, String color) {
        super(x, y);
        this.color = java.util.Objects.requireNonNull(color);
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) return true;
        if (!(obj instanceof ColoredPoint other)) return false;
        return super.equals(other) && color.equals(other.color);
    }

    @Override
    public int hashCode() {
        return java.util.Objects.hash(super.hashCode(), color);
    }
}
```

Với `Point point = new Point(2, 3);` và `ColoredPoint red = new ColoredPoint(2, 3, "red");`, lần lượt kiểm tra:

| Phép gọi | Triển khai được chọn | Kiểm tra kiểu | Kết quả |
| --- | --- | --- | --- |
| `point.equals(red)` | `Point.equals` | `red instanceof Point` đúng | `true`: trùng tọa độ |
| `red.equals(point)` | `ColoredPoint.equals` | `point instanceof ColoredPoint` sai | `false` |
| `point == red` | Toán tử identity | Hai đối tượng khác nhau | `false` |

`instanceof Point` cho phép cả đối tượng thuộc lớp con của `Point`; chiều ngược lại không đúng. Vì vậy:

```text
point.equals(red) = true
red.equals(point) = false
```

**Đây là phản ví dụ trực tiếp của tính đối xứng.** Thay đổi riêng dòng `super.equals(other)` trong lớp con sẽ không giải quyết được việc hai lớp đang có hai chính sách chấp nhận đối tượng khác nhau.

## 3. Tác hại và các hợp đồng cần rà soát cùng lúc

Một `equals()` đúng phải đáp ứng toàn bộ quy tắc, khi thông tin dùng để so sánh không đổi:

| Tính chất | Yêu cầu |
| --- | --- |
| Phản xạ | `x.equals(x)` luôn `true` với `x != null` |
| Đối xứng | `x.equals(y)` và `y.equals(x)` có cùng kết quả |
| Bắc cầu | `x.equals(y)` và `y.equals(z)` đúng thì `x.equals(z)` đúng |
| Nhất quán | Kết quả ổn định qua nhiều lần gọi nếu dữ liệu liên quan không đổi |
| Khác `null` | `x.equals(null)` trả `false` |
| Hash tương ứng | `x.equals(y)` đúng thì `x.hashCode() == y.hashCode()` |

Trong ví dụ lỗi, hash của `Point` chỉ dùng tọa độ nhưng hash của `ColoredPoint` còn dùng màu. Khi `point.equals(red)` cho `true`, hệ thống phải đảm bảo hai hash bằng nhau; công thức khác nhau ở trên **có thể** tạo hash khác nhau và vi phạm thêm hợp đồng `equals()` / `hashCode()`.

`HashSet` và `HashMap` dựa vào cả hai phương thức. Với lớp vi phạm hợp đồng, thêm/xóa/tìm khóa có thể biểu hiện không nhất quán. Tránh coi một số đo `HashSet.size()` trên bộ dữ liệu bất kỳ là bằng chứng hợp đồng vẫn đúng. **Khác đối tượng không bắt buộc khác hash**: trùng hash là được phép, nhưng bằng nhau theo `equals()` bắt buộc trùng hash.

## 4. Bẫy sửa sai: đối xứng trở lại nhưng mất bắc cầu

Một bản sửa tưởng hợp lý có thể cho `ColoredPoint` bằng `Point` nếu cùng tọa độ, nhưng so thêm màu khi cả hai đều là `ColoredPoint`.

Với ba đối tượng:

```text
base = Point(2, 3)
red  = ColoredPoint(2, 3, "red")
blue = ColoredPoint(2, 3, "blue")
```

Nếu màu bị bỏ qua khi một bên là `Point`, nhưng được xét khi cả hai là `ColoredPoint`, ta nhận:

```text
red.equals(base)  = true
base.equals(blue) = true
red.equals(blue)  = false
```

Như vậy **tính bắc cầu** bị phá vỡ. Dù có sửa hash để các đối tượng trên dùng cùng hash tọa độ, điều đó cũng không cứu được tính bắc cầu. Muốn cho `Point` bằng tất cả `ColoredPoint` cùng tọa độ thì hai `ColoredPoint` khác màu tại tọa độ ấy cũng phải bằng nhau; nếu màu phân biệt giá trị logic, hãy chọn một chính sách khác cho cha/con.

## 5. Chương trình Java 17+ chạy độc lập

Chương trình dưới đây minh họa cả ba trạng thái: lỗi đối xứng, bản vá sai phá bắc cầu và một chính sách sửa nhất quán. Lưu **nguyên vẹn** vào `EqualityInheritanceReview.java`.

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class EqualityInheritanceReview {
    static class LoosePoint {
        private final int x;
        private final int y;

        LoosePoint(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (!(obj instanceof LoosePoint other)) return false;
            return x == other.x && y == other.y;
        }

        @Override
        public int hashCode() {
            return Objects.hash(x, y);
        }
    }

    static final class RestrictedColoredPoint extends LoosePoint {
        private final String color;

        RestrictedColoredPoint(int x, int y, String color) {
            super(x, y);
            this.color = Objects.requireNonNull(color);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (!(obj instanceof RestrictedColoredPoint other)) {
                return false;
            }
            return super.equals(other) && color.equals(other.color);
        }

        @Override
        public int hashCode() {
            return Objects.hash(super.hashCode(), color);
        }
    }

    static final class BridgeColoredPoint extends LoosePoint {
        private final String color;

        BridgeColoredPoint(int x, int y, String color) {
            super(x, y);
            this.color = Objects.requireNonNull(color);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (!(obj instanceof LoosePoint)) return false;
            if (!(obj instanceof BridgeColoredPoint other)) {
                return super.equals(obj);
            }
            return super.equals(other) && color.equals(other.color);
        }

        @Override
        public int hashCode() {
            // Phù hợp với LoosePoint khi coi chúng bằng nhau.
            return super.hashCode();
        }
    }

    static class ExactPoint {
        private final int x;
        private final int y;

        ExactPoint(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (obj == null || getClass() != obj.getClass()) {
                return false;
            }
            ExactPoint other = (ExactPoint) obj;
            return x == other.x && y == other.y;
        }

        @Override
        public int hashCode() {
            return Objects.hash(x, y);
        }
    }

    static final class ExactColoredPoint extends ExactPoint {
        private final String color;

        ExactColoredPoint(int x, int y, String color) {
            super(x, y);
            this.color = Objects.requireNonNull(color);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (obj == null || getClass() != obj.getClass()) {
                return false;
            }
            ExactColoredPoint other = (ExactColoredPoint) obj;
            return super.equals(other) && color.equals(other.color);
        }

        @Override
        public int hashCode() {
            return Objects.hash(super.hashCode(), color);
        }
    }

    public static void main(String[] args) {
        LoosePoint point = new LoosePoint(2, 3);
        RestrictedColoredPoint restricted =
                new RestrictedColoredPoint(2, 3, "red");

        System.out.println("=== Broken symmetry ===");
        System.out.println("parent -> child: " + point.equals(restricted));
        System.out.println("child -> parent: " + restricted.equals(point));

        BridgeColoredPoint red = new BridgeColoredPoint(2, 3, "red");
        BridgeColoredPoint blue = new BridgeColoredPoint(2, 3, "blue");

        System.out.println("=== Broken transitivity ===");
        System.out.println("red -> parent: " + red.equals(point));
        System.out.println("parent -> blue: " + point.equals(blue));
        System.out.println("red -> blue: " + red.equals(blue));

        ExactPoint exact = new ExactPoint(2, 3);
        ExactColoredPoint exactRed = new ExactColoredPoint(2, 3, "red");
        ExactColoredPoint sameRed = new ExactColoredPoint(2, 3, "red");
        ExactColoredPoint exactBlue = new ExactColoredPoint(2, 3, "blue");

        System.out.println("=== Corrected policy ===");
        System.out.println("parent -> child: " + exact.equals(exactRed));
        System.out.println("child -> parent: " + exactRed.equals(exact));
        System.out.println("equal colored points: " + exactRed.equals(sameRed));
        System.out.println("different colors: " + exactRed.equals(exactBlue));
        System.out.println("equal hash: " +
                (exactRed.hashCode() == sameRed.hashCode()));

        Set<ExactPoint> set = new HashSet<>();
        set.add(exact);
        set.add(exactRed);
        set.add(sameRed);
        set.add(exactBlue);
        System.out.println("HashSet size: " + set.size());
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac EqualityInheritanceReview.java
java EqualityInheritanceReview
```

Kết quả xác định:

```text
=== Broken symmetry ===
parent -> child: true
child -> parent: false
=== Broken transitivity ===
red -> parent: true
parent -> blue: true
red -> blue: false
=== Corrected policy ===
parent -> child: false
child -> parent: false
equal colored points: true
different colors: false
equal hash: true
HashSet size: 3
```

**Giải thích mã:**

- `LoosePoint.equals()` dùng `instanceof LoosePoint` nên coi mọi đối tượng con trùng tọa độ là bằng nhau.
- `RestrictedColoredPoint.equals()` chỉ nhận cùng lớp con nên hai phép gọi cha/con đưa ra kết quả trái ngược.
- `BridgeColoredPoint` chấp nhận cha bằng tọa độ và chấp nhận cùng lớp con theo tọa độ + màu: cặp `red` với `point` và `point` với `blue` bằng nhau, trong khi `red` với `blue` không bằng nhau.
- `ExactPoint` dùng `getClass()` yêu cầu cùng lớp thực tế. `ExactColoredPoint` áp dụng cùng quy tắc rồi so thêm `color`. Do đó `exact.equals(exactRed)` và chiều ngược lại **đều `false`**.
- Trong `ExactColoredPoint.equals()`, `super.equals(other)` vẫn hoạt động: cả hai đối tượng được so sánh đều có lớp thực tế `ExactColoredPoint`, vượt qua điều kiện `getClass()` trong `ExactPoint`.
- `sameRed` có nội dung bằng `exactRed` và cùng hash; `HashSet` vì vậy chứa đúng ba giá trị logic: điểm thường, điểm đỏ và điểm xanh.

Chương trình cố tình **in các vi phạm**, thay vì ném lỗi ở lần vi phạm đầu tiên, để quan sát đủ ba phần trong cùng một lượt chạy.

## 6. Ba chiến lược thiết kế hợp lệ theo nghiệp vụ

### A. Chỉ bằng nhau khi cùng lớp thực tế

Sử dụng `getClass()` ở các lớp tham gia, như cặp `ExactPoint`/`ExactColoredPoint`. Cách này hợp lý khi `Point(2,3)` là **kiểu giá trị khác** `ColoredPoint(2,3,"red")`. Tất cả trường tạo nên tính bằng nhau trong từng lớp phải được đưa vào `equals()` và `hashCode()`.

Nhược điểm cần cân nhắc: những đối tượng là subclass/proxy được framework tạo ra có thể có lớp thực tế khác đối tượng gốc. Ví dụ trong một số cơ chế ORM, phải có chính sách riêng phù hợp với proxy và identity của thực thể. Không thay tất cả `instanceof` thành `getClass()` một cách máy móc.

### B. Dùng composition hoặc final value type

Nếu màu không phải một kiểu con cần thay thế điểm thường theo hợp đồng lớp, dùng **composition**:

```java
record PointValue(int x, int y) {}

record ColoredPointValue(PointValue point, String color) {
    ColoredPointValue {
        java.util.Objects.requireNonNull(point);
        java.util.Objects.requireNonNull(color);
    }
}
```

Đây là **đoạn định nghĩa kiểu minh họa** (không phải chương trình độc lập). Trong Java 17, `record` sinh `equals()` và `hashCode()` dựa vào các component và không thể bị subclass. Hai `PointValue(2,3)` bằng nhau; hai `ColoredPointValue` bằng nhau khi cả `point` và `color` bằng nhau. `PointValue` không phải cha của `ColoredPointValue`, nên xung đột đối xứng cha/con bị loại khỏi thiết kế.

Record không bảo đảm **bất biến sâu** nếu component chứa object mutable; ở đây dùng `int`, `String`, `PointValue` nên dữ liệu phục vụ phép bằng nhau ổn định.

### C. Tất cả các lớp so sánh đúng cùng một bộ dữ liệu

Nếu yêu cầu nghiệp vụ thực sự chỉ quan tâm tọa độ, lớp con có thể không đưa `color` vào logic bằng nhau, và `hashCode()` của nó cũng phải theo tọa độ. Khi đó **hai điểm màu khác nhau cùng tọa độ vẫn bằng nhau**. Đây có thể là lựa chọn hợp lệ, nhưng phải chấp nhận hệ quả đó.

Những hệ kế thừa phức tạp đôi khi dùng một cơ chế xác nhận tương thích hai chiều như `canEqual`. Đây không phải cách sửa tự động; cần thiết kế chính sách nhất quán cho toàn hệ và kiểm thử symmetry, transitivity, hash sau khi áp dụng.

## 7. Quy trình rà soát một hệ lớp thật

1. **Lập bản đồ kế thừa.** Tìm tất cả lớp cha/con liên quan và các phương thức `equals(Object)`/`hashCode()` ghi đè. Ghi rõ trường nào lớp con mới bổ sung, có tham gia định nghĩa bằng nhau hay không.
2. **Chốt chính sách bình đẳng.** Một điểm thường và một điểm màu cùng tọa độ có cần được coi là bằng nhau không? Nếu có, màu có còn được dùng để phân biệt các điểm màu không? Câu trả lời phải tuân thủ quan hệ tương đương.
3. **Tạo ba nhóm đối tượng:** cùng tham chiếu; hai instance riêng nhưng cùng giá trị; hai instance riêng khác giá trị. Sau đó tạo cặp cha/con cùng tọa độ, các lớp con cùng/different `color`, và bộ ba điểm thường/đỏ/xanh để kiểm tra quan hệ.
4. **Kiểm tra cả hai chiều.** Với từng cặp `a, b`, tính `a.equals(b)` và `b.equals(a)`. Không chỉ thử `child.equals(parent)` rồi kết luận.
5. **Kiểm tra bộ ba.** Với mọi `a, b, c` mà `a.equals(b)` và `b.equals(c)` đúng, yêu cầu `a.equals(c)` đúng.
6. **Kiểm tra hash và collection.** Mọi cặp bằng nhau phải có hash bằng nhau; thử `HashSet`, `HashMap` và các caller phụ thuộc vào việc gộp đối tượng theo giá trị.
7. **Kiểm tra trạng thái có thể thay đổi.** Nếu key của hash collection bị thay trường dùng trong `equals()`/`hashCode()`, việc tìm lại phần tử có thể sai lệch. Ưu tiên immutable key.
8. **Bổ sung kiểm thử hồi quy.** Phủ cả các lớp cháu hoặc proxy nếu hệ thống thực tế có dùng chúng.

Bảng dữ liệu gợi ý:

| Cặp hoặc bộ ba | Điều cần kiểm tra |
| --- | --- |
| `p` và `alias = p` | Cùng identity, phản xạ |
| `new Point(2,3)`, `new Point(2,3)` | Hai instance cha bằng giá trị |
| Hai `ColoredPoint(2,3,"red")` | Hai instance con bằng giá trị và hash |
| `Point(2,3)`, `ColoredPoint(2,3,"red")` | Hai chiều cha/con |
| Điểm đỏ và điểm xanh cùng tọa độ | Thuộc tính `color` |
| Điểm đỏ, điểm thường, điểm xanh | Bắc cầu |
| Bất kỳ instance và `null` | Kết quả `equals(null)` là `false` |

## 8. Kiểm thử tự động ma trận đối xứng và bắc cầu

Thêm phần sau **vào trong `main`** của chương trình Java 17 bên trên (không phải tệp độc lập). Các đối tượng `ExactPoint` và `ExactColoredPoint` đã có sẵn ở ví dụ:

```java
Object[] samples = {
        new ExactPoint(2, 3),
        new ExactPoint(2, 3),
        new ExactColoredPoint(2, 3, "red"),
        new ExactColoredPoint(2, 3, "red"),
        new ExactColoredPoint(2, 3, "blue")
};

for (Object a : samples) {
    for (Object b : samples) {
        if (a.equals(b) != b.equals(a)) {
            throw new AssertionError("Symmetry violated");
        }
        if (a.equals(b) && a.hashCode() != b.hashCode()) {
            throw new AssertionError("Hash contract violated");
        }
    }
}

for (Object a : samples) {
    for (Object b : samples) {
        for (Object c : samples) {
            if (a.equals(b) && b.equals(c) && !a.equals(c)) {
                throw new AssertionError("Transitivity violated");
            }
        }
    }
}
```

Với mẫu **đã sửa**, không có ngoại lệ phát sinh. Khi đưa các đối tượng lỗi vào ma trận, các điều kiện tương ứng có thể tìm ra phản ví dụ. Với dự án thật, đưa phép kiểm tra này vào test JUnit 5 và tăng mẫu theo ranh giới lớp/giá trị. Đây là kiểm thử trên **bộ mẫu đã chọn**, không chứng minh tự động mọi trạng thái của mọi đối tượng.

## 9. Sai lầm phổ biến

- **Chỉ kiểm tra một chiều:** `child.equals(parent)` đúng/sai chưa nói lên `parent.equals(child)` có giống hay không.
- **Chỉ xem `instanceof` như so sánh lớp chính xác:** thực chất toán tử chấp nhận kiểu con, nên dễ làm lớp cha định nghĩa equality rộng hơn lớp con.
- **Chữa symmetry nhưng không kiểm tra transitivity:** mẫu điểm đỏ/điểm thường/điểm xanh cho thấy bản vá “bỏ qua màu khi so với cha” có thể sai.
- **Ghi đè `equals()` nhưng quên `hashCode()`:** collection dựa trên hash cần hợp đồng giữa hai phương thức.
- **Đòi hai đối tượng khác nhau phải có hash khác nhau:** collision vẫn hợp lệ.
- **Thay đổi key đang nằm trong `HashMap`/`HashSet`:** nếu trường dùng để tính hash thay đổi, tra cứu có thể không còn đúng.
- **Áp dụng một kiểu sửa cho mọi hệ:** chính sách equality phải phản ánh nghiệp vụ và có thể chịu tác động từ ORM proxy, subclass động hoặc kiểu value cụ thể.

## 10. Tự kiểm tra

**Hỏi:** Vì sao `Point.equals(ColoredPoint)` có thể đúng, nhưng `ColoredPoint.equals(Point)` sai?  
**Đáp:** Lớp cha chấp nhận mọi `instanceof Point`, còn lớp con chỉ chấp nhận `instanceof ColoredPoint`.

**Hỏi:** Nếu `red.equals(base)` và `base.equals(blue)` đúng nhưng `red.equals(blue)` sai, vi phạm điều gì?  
**Đáp:** Tính bắc cầu.

**Hỏi:** Vì sao bản sửa `getClass()` làm `ExactPoint` và `ExactColoredPoint` cùng tọa độ không bằng nhau?  
**Đáp:** Chính sách bình đẳng yêu cầu **cùng lớp thực tế** trước khi so thuộc tính.

**Hỏi:** Nếu `x.equals(y)` đúng thì hash hai đối tượng cần thế nào?  
**Đáp:** Bắt buộc bằng nhau; chiều ngược lại không bắt buộc.

**Ghi nhớ:** Khi lớp con bổ sung trạng thái tham gia `equals()`, phải rà soát **toàn bộ hệ lớp**, thử cả hai chiều so sánh lẫn bộ ba bắc cầu, chọn chính sách equality nhất quán rồi đồng bộ `hashCode()` và kiểm thử collection. Một bản sửa chỉ làm cho một cặp đối tượng có kết quả đối xứng chưa đủ để bảo đảm hợp đồng `Object`.
