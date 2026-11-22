# Mở rộng lớp có `equals()` và nguy cơ mất đối xứng

## Mục tiêu

Bài này tập trung vào một tình huống dễ mắc lỗi khi thiết kế **quan hệ bằng nhau của đối tượng** trong Java: lớp cha đã ghi đè `equals(Object)`, còn lớp con kế thừa hoặc thay đổi định nghĩa bằng nhau, đặc biệt khi lớp con bổ sung thuộc tính cần so sánh. Bạn sẽ hiểu vì sao một cách triển khai có vẻ hợp lý lại vi phạm **tính đối xứng** (symmetry), vì sao cách vá ngây thơ có thể làm hỏng **tính bắc cầu** (transitivity), và cách lựa chọn thiết kế an toàn.

Trong ví dụ, một điểm có tọa độ `(x, y)` và một điểm có thêm màu sắc sẽ giúp nhìn thấy mâu thuẫn giữa “bằng nhau theo tọa độ” và “bằng nhau theo tọa độ lẫn màu”.

## 1. Hợp đồng của `equals(Object)`

`equals(Object)` là phương thức của `java.lang.Object`. Nếu ghi đè nó để định nghĩa **bằng nhau về giá trị/ý nghĩa**, chương trình phải duy trì những tính chất sau đối với các tham chiếu không `null`:

| Tính chất | Phát biểu | Ví dụ |
| --- | --- | --- |
| **Phản xạ** (reflexive) | `x.equals(x)` phải là `true` | Một đối tượng bằng chính nó |
| **Đối xứng** (symmetric) | `x.equals(y)` và `y.equals(x)` phải cùng kết quả | Không thể chỉ một phía công nhận “bằng nhau” |
| **Bắc cầu** (transitive) | Nếu `x.equals(y)` và `y.equals(z)` đều đúng thì `x.equals(z)` phải đúng | Quan hệ bằng nhau không tự mâu thuẫn qua đối tượng trung gian |
| **Nhất quán** (consistent) | Khi thông tin dùng để so sánh không thay đổi, gọi lại cho cùng kết quả | Không thay đổi kết quả tùy ý giữa hai lần gọi |
| **So với `null`** | `x.equals(null)` phải là `false` | Không một đối tượng nào bằng `null` |

**Ràng buộc gắn với `hashCode()`:** Nếu `a.equals(b)` trả về `true` thì `a.hashCode() == b.hashCode()` **bắt buộc** đúng. Chiều đảo lại **không bắt buộc**: hai đối tượng khác nhau vẫn có thể trùng hash. Nếu ghi đè `equals`, thường phải ghi đè `hashCode` đồng bộ; nếu không, việc tra cứu trong `HashMap`, `HashSet` có thể sai về mặt hành vi mong đợi.

Hợp đồng này áp dụng **xuyên các lớp** khi một lời gọi `equals` được cho phép so sánh đối tượng lớp cha với lớp con. Hợp đồng không biến mất chỉ vì các lớp nằm trong quan hệ kế thừa.

## 2. Gốc rễ của bài toán: lớp cha và lớp con muốn so sánh khác nhau

Giả sử có hai kiểu:

```text
Point(x, y)
   ▲
   │ extends
   │
ColoredPoint(x, y, color)
```

Với `Point`, hai điểm có cùng `x` và `y` được xem là bằng nhau. Với `ColoredPoint`, người thiết kế có thể muốn màu sắc cũng tham gia quyết định bằng nhau.

Hãy xét:

```text
p = Point(1, 2)
r = ColoredPoint(1, 2, "red")
```

- Nếu gọi `p.equals(r)`, lớp cha có thể chỉ xem `r` như một `Point`, rồi kết luận **bằng nhau** dựa trên tọa độ.
- Nếu gọi `r.equals(p)`, lớp con có thể yêu cầu đối phương **cũng phải có màu**, rồi kết luận **khác nhau**.
- Cùng một cặp đối tượng nhưng hai chiều so sánh trả kết quả khác nhau: **vi phạm đối xứng**.

Điều này bắt nguồn từ **chênh lệch thông tin**: `Point` không có thuộc tính `color` để so sánh, trong khi `ColoredPoint` lại coi `color` là một phần của danh tính theo giá trị. Việc `ColoredPoint` kế thừa từ `Point` không tự giải quyết được sự khác biệt về định nghĩa bằng nhau.

## 3. Ví dụ chạy được: vỡ đối xứng và cách vá làm vỡ bắc cầu

**Tệp `BrokenEqualsDemo.java`**, chạy bằng Java 17+:

```java
import java.util.Objects;

public class BrokenEqualsDemo {
    static class Point {
        final int x;
        final int y;

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

    // Cố tình SAI để minh họa mất đối xứng.
    static final class ColoredPoint extends Point {
        final String color;

        ColoredPoint(int x, int y, String color) {
            super(x, y);
            this.color = Objects.requireNonNull(color);
        }

        @Override
        public boolean equals(Object obj) {
            if (!(obj instanceof ColoredPoint other)) {
                return false;
            }
            return super.equals(other) && color.equals(other.color);
        }

        @Override
        public int hashCode() {
            return Objects.hash(super.hashCode(), color);
        }
    }

    // Cố tình SAI: cố cho lớp con bằng Point thường.
    static final class LenientColoredPoint extends Point {
        final String color;

        LenientColoredPoint(int x, int y, String color) {
            super(x, y);
            this.color = Objects.requireNonNull(color);
        }

        @Override
        public boolean equals(Object obj) {
            if (obj instanceof LenientColoredPoint other) {
                return super.equals(other) && color.equals(other.color);
            }
            return obj instanceof Point && super.equals(obj);
        }

        @Override
        public int hashCode() {
            return Objects.hash(super.hashCode(), color);
        }
    }

    public static void main(String[] args) {
        Point plain = new Point(1, 2);
        ColoredPoint red = new ColoredPoint(1, 2, "red");

        System.out.println("plain.equals(red): " + plain.equals(red));
        System.out.println("red.equals(plain): " + red.equals(plain));

        LenientColoredPoint lenientRed =
                new LenientColoredPoint(1, 2, "red");
        LenientColoredPoint lenientBlue =
                new LenientColoredPoint(1, 2, "blue");

        System.out.println(
                "plain.equals(lenientRed): " + plain.equals(lenientRed));
        System.out.println(
                "lenientRed.equals(plain): " + lenientRed.equals(plain));
        System.out.println(
                "plain.equals(lenientBlue): " + plain.equals(lenientBlue));
        System.out.println(
                "lenientRed.equals(lenientBlue): "
                        + lenientRed.equals(lenientBlue));
    }
}
```

Biên dịch và chạy:

```bash
javac BrokenEqualsDemo.java
java BrokenEqualsDemo
```

**Đầu ra chính xác:**

```text
plain.equals(red): true
red.equals(plain): false
plain.equals(lenientRed): true
lenientRed.equals(plain): true
plain.equals(lenientBlue): true
lenientRed.equals(lenientBlue): false
```

### 3.1. Vì sao `plain.equals(red)` là `true`?

Phương thức được gọi là `Point.equals` vì biến nhận lời gọi `plain` đang trỏ tới đối tượng có lớp thực tế `Point`. Biểu thức:

```java
obj instanceof Point other
```

trả về `true` khi `obj` là `Point` **hoặc đối tượng của lớp con `Point`**. Vì `ColoredPoint` là một `Point`, phép so sánh chỉ xét `x`, `y` và trả `true`. Màu không được kiểm tra.

Khi đảo chiều `red.equals(plain)`, JVM gọi phương thức ghi đè trong `ColoredPoint`. Kiểm tra `obj instanceof ColoredPoint` trả về `false` vì `plain` là `Point` thuần. Kết quả thành `false`. Đây là vi phạm **đối xứng**, không phải hành vi Java ngẫu nhiên.

### 3.2. Vì sao “cho phép so sánh với Point thường” chưa giải quyết được?

Lớp `LenientColoredPoint` cố xử lý trường hợp so với `Point` bằng cách chỉ kiểm tra tọa độ. Nhờ đó:

```text
lenientRed.equals(plain)   = true
plain.equals(lenientRed)   = true
```

Nhưng `lenientRed` và `lenientBlue` có màu khác nhau, nên khi so hai đối tượng cùng lớp con, `equals` trả về `false`. Ta có:

```text
lenientRed  ==(equals)==  plain
plain       ==(equals)==  lenientBlue
lenientRed  !=(equals)!=  lenientBlue
```

Từ `lenientRed.equals(plain) == true` và `plain.equals(lenientBlue) == true`, tính **bắc cầu** yêu cầu `lenientRed.equals(lenientBlue) == true`. Chương trình lại trả `false`: phương án “vá đối xứng” này làm hỏng **bắc cầu**.

**Lưu ý:** Hai lớp con trong ví dụ được cố tình viết sai để chứng minh lỗi; **không sao chép hai cách triển khai đó vào mã sản phẩm**.

### 3.3. `hashCode` cũng có thể mất hợp đồng

Trong ví dụ trên, `Point` băm theo tọa độ, còn lớp con băm thêm màu. Nhưng một số chiều `equals` lại coi `Point` và lớp con là bằng nhau. Khi bằng nhau mà mã băm khác nhau, hợp đồng `equals/hashCode` bị vi phạm. Không cần so sánh hoặc đoán các con số hash cụ thể để nhận ra vấn đề: **tập trường tham gia bình đẳng và tập trường tham gia băm phải tương thích cho mọi cặp được coi là bằng nhau**.

Điều này có thể tạo lỗi khó tái hiện khi dùng làm khóa `HashMap` hoặc phần tử `HashSet`: cấu trúc băm dựa vào `hashCode` để tìm vùng ứng viên trước khi gọi `equals`. Hơn nữa, do `equals` không đối xứng, ngay cả thao tác dùng `equals` trực tiếp cũng không có nghĩa ổn định theo thứ tự đối tượng.

## 4. Vì sao chỉ đổi `instanceof` thành `getClass()` vẫn cần quyết định thiết kế?

Có hai kiểu kiểm tra lớp thường gặp:

```java
// Nhận cả đối tượng lớp con nếu nó là một Point:
obj instanceof Point

// Chỉ nhận đối tượng có đúng lớp runtime của bên nhận:
obj != null && getClass() == obj.getClass()
```

- `instanceof` cho phép **bao gồm các lớp con**. Có thể phù hợp nếu mọi lớp con phải có **cùng một định nghĩa bằng nhau** và không thêm trường có ý nghĩa trong `equals`.
- `getClass()` yêu cầu **đúng cùng lớp runtime**. Có thể giúp tách quan hệ bằng nhau giữa các kiểu, miễn là **mọi lớp liên quan** triển khai nhất quán.
- Với `getClass()`, một `Point` và một `ColoredPoint` luôn không bằng nhau, kể cả tọa độ trùng nhau. Đây là **quyết định ngữ nghĩa** của API, không chỉ là mẹo đổi cú pháp.
- Khi dùng các lớp proxy do framework sinh ra, kiểm tra chính xác lớp runtime có thể chặt hơn mong muốn. Cần xác định rõ chính sách bằng nhau theo kiểu nghiệp vụ, tránh mặc định `getClass()` là đáp án cho mọi trường hợp.

Nếu lớp con được phép thay đổi ngữ nghĩa `equals`, người thiết kế phải phối hợp **toàn bộ phân cấp**, gồm `equals` và `hashCode`. Vá duy nhất một nhánh thường không đủ.

## 5. Cách an toàn A: ưu tiên composition khi lớp con thêm trạng thái bình đẳng

Khi màu thực sự là một phần định nghĩa bằng nhau, giải pháp rõ ràng thường là **không kế thừa một lớp đã có chính sách `equals` không tương thích**. Cho kiểu điểm có tọa độ bất biến, rồi tạo kiểu điểm màu **chứa** điểm tọa độ qua composition.

**Tệp `CompositionEqualityDemo.java`:**

```java
import java.util.Objects;

public class CompositionEqualityDemo {
    static final class Position {
        private final int x;
        private final int y;

        Position(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof Position other)) {
                return false;
            }
            return x == other.x && y == other.y;
        }

        @Override
        public int hashCode() {
            return Objects.hash(x, y);
        }
    }

    static final class ColoredPoint {
        private final Position position;
        private final String color;

        ColoredPoint(Position position, String color) {
            this.position = Objects.requireNonNull(position);
            this.color = Objects.requireNonNull(color);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof ColoredPoint other)) {
                return false;
            }
            return position.equals(other.position)
                    && color.equals(other.color);
        }

        @Override
        public int hashCode() {
            return Objects.hash(position, color);
        }
    }

    public static void main(String[] args) {
        Position p1 = new Position(1, 2);
        Position p2 = new Position(1, 2);
        ColoredPoint red1 = new ColoredPoint(p1, "red");
        ColoredPoint red2 = new ColoredPoint(p2, "red");
        ColoredPoint blue = new ColoredPoint(p1, "blue");

        System.out.println("p1.equals(p2): " + p1.equals(p2));
        System.out.println("red1.equals(red2): " + red1.equals(red2));
        System.out.println(
                "red1.hashCode() == red2.hashCode(): "
                        + (red1.hashCode() == red2.hashCode()));
        System.out.println("red1.equals(blue): " + red1.equals(blue));
        System.out.println("red1.equals(p1): " + red1.equals(p1));
    }
}
```

```bash
javac CompositionEqualityDemo.java
java CompositionEqualityDemo
```

**Đầu ra chính xác:**

```text
p1.equals(p2): true
red1.equals(red2): true
red1.hashCode() == red2.hashCode(): true
red1.equals(blue): false
red1.equals(p1): false
```

Đặc điểm của thiết kế:

1. `Position` và `ColoredPoint` là hai lớp `final`, không có lớp con bất ngờ kế thừa và thay đổi chính sách so sánh.
2. Hai `Position` bằng nhau khi tọa độ giống nhau, hai `ColoredPoint` bằng nhau khi **cả position và color** bằng nhau.
3. Một `ColoredPoint` không tự nhận là `Position`: không tồn tại tình huống cha đồng ý, con từ chối.
4. Cả hai kiểu bất biến trong ví dụ: các trường `final` và những thành phần được giữ (`Position`, `String`) đều bất biến; nhờ vậy giá trị băm không thay đổi sau khi đưa vào tập hợp băm.
5. `hashCode` của `ColoredPoint` dùng đúng các thành phần tham gia `equals`; hai đối tượng bằng nhau chắc chắn có cùng mã băm.

Nếu mục tiêu là các kiểu dữ liệu giá trị ngắn gọn trên Java 17+, có thể dùng `record`; các thành phần record tham gia `equals` và `hashCode` mặc định:

```java
record Position(int x, int y) {}
record ColoredPoint(Position position, String color) {}
```

Đoạn record này minh họa cách khai báo độc lập (có thể đặt ở phạm vi tệp/package phù hợp). Mỗi record mặc định là `final` nên không thể được kế thừa để lén đổi chính sách so sánh. Nếu thành phần record là đối tượng mutable thì bản thân record **không tự sao chép sâu hay làm bất biến thành phần đó**.

## 6. Cách an toàn B: giữ kế thừa nhưng chủ động cấm bằng nhau xuyên lớp

Trong những hệ thống đã có kế thừa và muốn `Point` **không bằng** bất kỳ lớp con nào, có thể áp dụng kiểm tra lớp runtime chính xác ngay ở lớp cha; lớp con thêm trường thì ghi đè `equals` và `hashCode` nhất quán.

**Tệp `StrictClassEqualityDemo.java`:**

```java
import java.util.Objects;

public class StrictClassEqualityDemo {
    static class Point {
        final int x;
        final int y;

        Point(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (obj == null || getClass() != obj.getClass()) {
                return false;
            }
            Point other = (Point) obj;
            return x == other.x && y == other.y;
        }

        @Override
        public int hashCode() {
            return Objects.hash(getClass(), x, y);
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
            if (!super.equals(obj)) {
                return false;
            }
            ColoredPoint other = (ColoredPoint) obj;
            return color.equals(other.color);
        }

        @Override
        public int hashCode() {
            return Objects.hash(super.hashCode(), color);
        }
    }

    public static void main(String[] args) {
        Point plain = new Point(1, 2);
        Point red1 = new ColoredPoint(1, 2, "red");
        Point red2 = new ColoredPoint(1, 2, "red");
        Point blue = new ColoredPoint(1, 2, "blue");

        System.out.println("plain.equals(red1): " + plain.equals(red1));
        System.out.println("red1.equals(plain): " + red1.equals(plain));
        System.out.println("red1.equals(red2): " + red1.equals(red2));
        System.out.println("red1.equals(blue): " + red1.equals(blue));
        System.out.println(
                "equal red points have equal hashes: "
                        + (red1.hashCode() == red2.hashCode()));
    }
}
```

```bash
javac StrictClassEqualityDemo.java
java StrictClassEqualityDemo
```

**Đầu ra chính xác:**

```text
plain.equals(red1): false
red1.equals(plain): false
red1.equals(red2): true
red1.equals(blue): false
equal red points have equal hashes: true
```

Giải thích:

- Trong `Point.equals`, `getClass()` trả lớp thực tế của đối tượng đang nhận lời gọi. Một `Point` thuần và một `ColoredPoint` luôn bị coi là khác lớp, **từ cả hai chiều**.
- Trong `ColoredPoint.equals`, lời gọi `super.equals(obj)` kiểm tra cùng lớp runtime và tọa độ trước. Vì kiểm tra đó thành công chỉ khi cả hai là `ColoredPoint`, ép kiểu `(ColoredPoint) obj` là an toàn.
- Lớp con kiểm tra thêm `color` và bổ sung `color` vào `hashCode`. Các đối tượng được xem là bằng nhau theo cùng chính sách.
- `Point.hashCode` đưa cả lớp runtime vào công thức băm. Điều này phù hợp với quyết định rằng các lớp khác nhau không được coi là bằng nhau. Hai đối tượng khác lớp vẫn có thể tình cờ trùng hash; không sao.

**Giới hạn thiết kế:** Cách này chấp nhận việc kiểu cha và kiểu con **không bằng nhau về giá trị** dù cùng tọa độ. Có thể không phù hợp nếu người gọi mong quan hệ đa hình “mọi Point có tọa độ giống nhau đều bằng nhau”. Không nên chọn cách này mà chưa thống nhất ngữ nghĩa API. Ví dụ sử dụng lớp con `final` để không có lớp cháu tiếp tục bổ sung trạng thái bình đẳng.

## 7. Nếu bắt buộc phải có bằng nhau đa hình giữa cha và con thì sao?

Có những trường hợp quan hệ “là một” (`is-a`) đi cùng một định nghĩa bằng nhau có chủ ý: mọi đối tượng trong một phân cấp đều được so sánh theo **cùng tập thuộc tính** do lớp cha xác định. Khi đó lớp con **không được tự ý thêm điều kiện** làm thay đổi quy tắc cho chỉ một hướng so sánh.

Ví dụ: nếu chỉ tọa độ xác định bằng nhau cho **toàn bộ phân cấp**, màu chỉ là thuộc tính hiển thị thì có thể chấp nhận:

```text
Point(1, 2) bằng ColoredPoint(1, 2, "red")
ColoredPoint(1, 2, "red") bằng ColoredPoint(1, 2, "blue")
```

Nhưng nếu người dùng thực sự kỳ vọng hai màu khác nhau là hai giá trị khác nhau, chính sách này **không đáp ứng yêu cầu miền nghiệp vụ**; hãy thiết kế composition hoặc tách kiểu thay vì giả vờ màu không quan trọng.

Một số phân cấp phức tạp dùng mô thức `canEqual` để phối hợp sự đồng ý giữa hai phía. Mô thức đó đòi hỏi thiết kế và kiểm thử xuyên toàn bộ lớp cha/lớp con, không phải chỉ thêm một phương thức là tự động bảo đảm cả đối xứng lẫn bắc cầu. Trong bài toán điểm có thêm màu, composition hoặc chính sách tách lớp rõ ràng thường dễ kiểm chứng hơn.

## 8. Quy trình rà soát `equals` khi có kế thừa

Khi đọc hoặc viết một lớp kế thừa lớp đã ghi đè `equals`, hãy kiểm tra tuần tự:

1. **Xác định ý nghĩa của bằng nhau:** Đây là đối tượng giá trị (value object) hay đối tượng có danh tính nghiệp vụ (entity)? Thuộc tính nào thực sự tham gia so sánh?
2. **Xác định phạm vi so sánh:** Lớp cha có dùng `instanceof` cho phép con, hay dùng `getClass` yêu cầu cùng lớp thực tế?
3. **Xem mọi lớp con có trạng thái mới không:** Trạng thái ấy có thuộc định nghĩa bằng nhau hay chỉ là metadata/trình bày?
4. **Thử đủ hai chiều:** `a.equals(b)` và `b.equals(a)`, với `a` là cha, `b` là con. Không chỉ thử hai thể hiện cùng một lớp.
5. **Thử bộ ba:** Với các đối tượng ở cha/con và hai lớp con khác nhau, kiểm tra quy tắc bắc cầu; chính các bộ ba là nơi cách vá ngây thơ thường thất bại.
6. **Rà soát `hashCode` và tính bất biến:** Mọi cặp `equals == true` phải có hash bằng nhau. Tránh thay đổi trường dùng băm khi đối tượng đang làm phần tử `HashSet` hoặc khóa `HashMap`.
7. **Kiểm tra `null`, chính mình và các giá trị biên:** `a.equals(a)`, `a.equals(null)`, và trường hợp thuộc tính thành phần có thể `null`.

Một bảng kiểm thử ý nghĩa cho ví dụ gồm `Point p`, `ColoredPoint red` và `ColoredPoint blue`:

| Phép thử | Triển khai sai ở mục 3 | Chính sách tách lớp mục 6 |
| --- | --- | --- |
| `p.equals(red)` | `true` | `false` |
| `red.equals(p)` | `false` (vi phạm đối xứng) | `false` |
| `red.equals(blue)` khi màu khác | `false` | `false` |
| Hai ColoredPoint cùng tọa độ và cùng màu | `true` | `true` |
| Hai đối tượng `equals == true` có cùng `hashCode`? | Không được bảo đảm cho mọi cặp | Được bảo đảm theo triển khai đã cho |

*Bảng dùng `ColoredPoint` (bản giới hạn loại), không dùng `LenientColoredPoint`, ở mục 3.*

## 9. Những lỗi suy luận phổ biến

- **“Dùng `instanceof` là luôn tốt vì hỗ trợ đa hình.”** Không hẳn: `instanceof` trong lớp cha cho phép so với lớp con, nhưng lớp con có thể có quy tắc giá trị chặt hơn. Tính đa hình của kiểu không đồng nghĩa mọi đối tượng của các kiểu đó phải bằng nhau.
- **“Thêm `color` vào `ColoredPoint.equals` là đủ.”** Không đủ: lớp cha còn có thể trả `true` ở chiều ngược lại, phá đối xứng.
- **“Cho lớp con bằng lớp cha khi tọa độ trùng nhau thì đã sửa xong.”** Chưa chắc: hai lớp con khác màu có thể cùng bằng một đối tượng cha nhưng lại không bằng nhau, phá bắc cầu.
- **“`hashCode` độc lập với `equals`.”** Sai: các đối tượng bằng nhau phải có cùng hash. Hash khác nhau cho một cặp bằng nhau làm cấu trúc băm hoạt động không đáng tin cậy.
- **“Đổi toàn bộ sang `getClass()` luôn là chuẩn.”** Không đúng với mọi mô hình, đặc biệt khi API cần bình đẳng đa hình hoặc xử lý proxy. Đây là lựa chọn thiết kế có hậu quả cụ thể.
- **“Đặt `final` cho trường `color` là đủ.”** `final` giữ nguyên tham chiếu/trường, nhưng không khắc phục mâu thuẫn bình đẳng giữa lớp cha với lớp con.

## Tự kiểm tra

**Câu 1.** Lớp cha `Vehicle` kiểm tra `obj instanceof Vehicle` và so sánh `id`; lớp con `ElectricVehicle` đòi đối phương là `ElectricVehicle` rồi so thêm `batteryModel`. Có nguy cơ nào?  
**Trả lời:** Một `Vehicle` và một `ElectricVehicle` cùng `id` có thể được lớp cha coi là bằng nhau trong khi lớp con từ chối, làm mất đối xứng.

**Câu 2.** Nếu lớp con sửa `equals` để trả `true` khi so với lớp cha cùng `id`, và lại so thêm `batteryModel` khi gặp lớp con khác, vấn đề gì có thể xảy ra?  
**Trả lời:** Hai lớp con có `batteryModel` khác nhau có thể đều bằng một đối tượng cha nhưng không bằng nhau với nhau, vi phạm bắc cầu.

**Câu 3.** Vì sao không thể chỉ thêm `color` vào `hashCode` và bỏ qua `equals`?  
**Trả lời:** Nếu `equals` của lớp cha còn công nhận hai đối tượng bằng nhau dựa trên tọa độ, hash của lớp con có thể khác hash của lớp cha, vi phạm yêu cầu “bằng nhau thì cùng hash”.

**Câu 4.** Khi nào composition phù hợp hơn inheritance?  
**Trả lời:** Khi đối tượng mở rộng có định nghĩa bình đẳng mới gồm trạng thái bổ sung, mà định nghĩa ấy không thể đồng thời giữ tính đối xứng/bắc cầu với chính sách của lớp cha.

## Kết luận

**Hợp đồng `equals` có hiệu lực trên mọi đối tượng được so sánh, kể cả khi chúng thuộc các lớp trong cùng phân cấp kế thừa.** Lớp cha so bằng `instanceof` và lớp con thêm điều kiện bình đẳng rất dễ gây **mất đối xứng**; việc cố nới điều kiện so với lớp cha có thể chuyển thành **mất bắc cầu**. Hãy quyết định trước ngữ nghĩa bằng nhau, dùng composition và lớp `final` cho value object khi phù hợp, hoặc thống nhất chính sách cùng lớp runtime trong toàn phân cấp. Luôn kiểm tra đồng thời `equals`, `hashCode` và cả hai chiều so sánh.
