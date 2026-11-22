# Kiểm tra các cặp và bộ ba đối tượng ở nhiều mức kế thừa khi cài đặt `equals`

## 1. Vì sao cần thử nhiều đối tượng trong một hệ phân cấp?

Khi cài đặt `equals(Object)` cho lớp có quan hệ kế thừa, một phép thử `a.equals(b)` đơn lẻ không đủ để xác nhận hợp đồng bằng nhau. Lớp cha có thể chấp nhận lớp con, trong khi lớp con lại từ chối lớp cha vì muốn so sánh thêm trường riêng. Một cách sửa vội để làm đối xứng hai chiều còn có thể khiến **tính bắc cầu** bị vi phạm khi so sánh ba đối tượng.

Ví dụ một lớp `Point` chỉ có tọa độ và lớp con `ColoredPoint` có thêm màu sắc:

- Nếu `Point` coi mọi `ColoredPoint` cùng tọa độ là bằng mình, còn `ColoredPoint` từ chối `Point` vì thiếu màu, ta có thể gặp `a.equals(b) != b.equals(a)`: **vi phạm đối xứng**.
- Nếu `ColoredPoint` chấp nhận so với `Point` bằng tọa độ, nhưng đòi hai `ColoredPoint` phải cùng màu, thì một `Point` thường có thể trở thành cầu nối giữa hai `ColoredPoint` khác màu: **vi phạm bắc cầu**.

Vì thế, với một phân cấp như `Base → Middle → Leaf`, cần kiểm tra **cả hai hướng của mọi cặp** và **mọi thứ tự liên quan của bộ ba**. Mục tiêu là phát hiện trường hợp một triển khai có vẻ đúng khi so sánh những đối tượng cùng lớp nhưng sai khi so sánh qua các cấp kế thừa.

Đề bài tập trung vào **phương pháp kiểm tra** tính đúng đắn của `equals` qua nhiều mức kế thừa: chọn mẫu, lập ma trận cặp, kiểm tra bộ ba, nhận diện phản ví dụ và chọn chính sách bình đẳng phù hợp.

## 2. Hợp đồng cần dùng làm tiêu chuẩn kiểm tra

Với các tham chiếu đối tượng không phải `null`, `equals` phải tuân thủ:

| Thuộc tính | Biểu thức cần kiểm tra | Ý nghĩa khi kiểm thử |
| --- | --- | --- |
| Phản xạ (*reflexive*) | `x.equals(x) == true` | Từng đối tượng phải bằng chính nó. |
| Đối xứng (*symmetric*) | `x.equals(y) == y.equals(x)` | Một **cặp có thứ tự** phải được kiểm tra đủ hai chiều. |
| Bắc cầu (*transitive*) | Nếu `x.equals(y)` và `y.equals(z)` đều đúng thì `x.equals(z)` cũng đúng. | Kiểm tra **bộ ba có thứ tự**, đặc biệt qua lớp cha làm cầu nối. |
| Nhất quán (*consistent*) | Lặp lại phép so sánh khi trạng thái liên quan không đổi phải cho cùng kết quả. | Thử lặp và tránh sửa trạng thái giữa các phép thử. |
| So với `null` | `x.equals(null) == false` | Mọi đối tượng thật phải từ chối `null` mà không ném lỗi. |

Ngoài ra, quan hệ với `hashCode` bắt buộc là:

```text
Nếu a.equals(b) == true thì a.hashCode() == b.hashCode().
```

Chiều ngược lại **không bắt buộc**: hai đối tượng có thể cùng hash nhưng không bằng nhau. `equals` cần trả `false` cho đối tượng không tương thích về kiểu theo chính sách lớp, chứ không ném `ClassCastException` do ép kiểu thiếu kiểm tra.

Đây là các điều kiện **đồng thời**. Một lớp vượt qua thử nghiệm phản xạ hay đối xứng vẫn có thể thất bại ở tính bắc cầu. Những phép thử trên một tập mẫu hữu hạn giúp tìm phản ví dụ; chúng không thể chứng minh mọi trường hợp có thể có của lớp đều đúng.

## 3. Chọn cặp ở cùng cấp, khác cấp và nhánh anh em

Xét phân cấp ba mức:

```text
Point
  └── NamedPoint
        └── ColoredNamedPoint
```

Giả sử lớp cha xem tọa độ là bản chất, lớp giữa xem thêm tên, lớp dưới cùng xem thêm màu. Để phát hiện sai sót, nên tạo các đối tượng có thể so sánh một cách có chủ đích:

1. **Cùng cấp, cùng dữ liệu**: hai `Point` có tọa độ bằng nhau; hai `NamedPoint` cùng tọa độ và tên; hai `ColoredNamedPoint` có mọi trường giống nhau.
2. **Cùng cấp, khác dữ liệu**: chỉ đổi một trường tham gia `equals` để chắc chắn nhận `false` nếu trường đó thực sự ảnh hưởng đến bằng nhau.
3. **Cùng tham chiếu**: `a.equals(a)` và một biến alias `b = a`; đây là kiểm tra phản xạ, không phải đối xứng đầy đủ.
4. **Khác cấp kề nhau**: `Point ↔ NamedPoint`, `NamedPoint ↔ ColoredNamedPoint`, luôn gọi cả hai chiều.
5. **Cách nhau hai mức**: `Point ↔ ColoredNamedPoint`; không được bỏ qua vì hai lớp trung gian có thể có quy tắc khác nhau.
6. **Khác nhánh cùng cha**: nếu có hai lớp con khác nhau, kiểm tra `ChildA ↔ ChildB` cũng như những cặp với cha.
7. **`null` và kiểu không liên quan**: mỗi đối tượng so với `null` và một loại ngoài phân cấp để phát hiện lỗi kiểm tra kiểu.

Một **ma trận cặp** theo danh sách mẫu `[p, n, c]` tương đương với chín phép gọi:

| Bên trái `equals` | `p` (Point) | `n` (NamedPoint) | `c` (ColoredNamedPoint) |
| --- | --- | --- | --- |
| `p` | `p.equals(p)` | `p.equals(n)` | `p.equals(c)` |
| `n` | `n.equals(p)` | `n.equals(n)` | `n.equals(c)` |
| `c` | `c.equals(p)` | `c.equals(n)` | `c.equals(c)` |

Để xác minh **đối xứng**, so sánh mỗi ô `(i, j)` với ô đối diện qua đường chéo `(j, i)`. Chẳng hạn, `p.equals(c)` phải cho kết quả giống `c.equals(p)`. Nếu chỉ gọi theo một chiều hoặc chỉ so sánh hai bản thể cùng lớp, lỗi tại ranh giới cha/con có thể bị bỏ qua.

Không nên mặc định mọi cặp cha/con **phải bằng nhau**. Tùy mô hình dữ liệu, `Point` với `ColoredNamedPoint` có thể được định nghĩa luôn khác nhau, hoặc bằng nhau theo một khóa bất biến chung. Điều bắt buộc là chính sách đó phải nhất quán ở cả hai hướng và không phá hợp đồng.

## 4. Bộ ba kiểm tra bắc cầu: phải xét thứ tự

Nếu `a.equals(b)` đúng và `b.equals(c)` đúng thì bắt buộc `a.equals(c)` đúng. Điều kiện này không chỉ áp dụng khi ba đối tượng có cùng runtime class.

Ví dụ:

```text
red   = ColoredPoint(5, "red")
plain = Point(5)
blue  = ColoredPoint(5, "blue")

red.equals(plain)  → true
plain.equals(blue) → true
red.equals(blue)   → false   // VI PHẠM BẮC CẦU
```

`plain` có cùng tọa độ với cả hai điểm màu, nhưng `red` và `blue` lại khác nhau. Không thể chấp nhận đồng thời tất cả ba quy tắc này nếu muốn `equals` là quan hệ tương đương.

Với danh sách `n` mẫu, cách kiểm tra tổng quát:

```text
for mỗi a trong mẫu:
    for mỗi b trong mẫu:
        for mỗi c trong mẫu:
            nếu a.equals(b) và b.equals(c) và !a.equals(c):
                báo VI PHẠM BẮC CẦU với bộ ba (a, b, c)
```

Ba vòng lặp duyệt **bộ ba có thứ tự**, kể cả lặp lại đối tượng. Với `n` phần tử có nhiều nhất `n³` bộ ba, rất phù hợp cho một tập kiểm thử nhỏ đã chọn kỹ. Đổi thứ tự các phần tử có thể làm điều kiện tiên đề khác đi; vì thế chỉ thử `(a, b, c)` mà không xét thứ tự còn lại là chưa đủ.

Bộ ba nên bao gồm: ba đối tượng cùng lớp; một lớp cha ở giữa hai lớp con; lớp giữa ở giữa cha và cháu; ba cấp liên tiếp; hai nhánh con với cha chung; những đối tượng khác giá trị nhưng cùng phần dữ liệu của lớp cha.

## 5. Java 17+: chương trình kiểm tra tự động cặp và bộ ba

Ví dụ sau cố ý tạo **hai kiểu triển khai sai**, sau đó so với một mô hình hợp lệ. Tất cả đều nằm trong một tệp độc lập `HierarchyEqualsAudit.java`, không cần thư viện kiểm thử bên ngoài.

```java
import java.util.List;

public class HierarchyEqualsAudit {
    record Sample(String label, Object value) { }

    // Cấp cha: coi mọi Point có x bằng nhau là bằng nhau.
    static class Point {
        final int x;

        Point(int x) {
            this.x = x;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (!(obj instanceof Point other)) return false;
            return x == other.x;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(x);
        }
    }

    // Cấp giữa: đòi phía bên kia ít nhất là NamedPoint.
    static class NamedPoint extends Point {
        final String name;

        NamedPoint(int x, String name) {
            super(x);
            this.name = name;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (!(obj instanceof NamedPoint other)) return false;
            return super.equals(other) && name.equals(other.name);
        }
    }

    // Cấp lá: đòi phía bên kia là ColoredNamedPoint.
    static final class ColoredNamedPoint extends NamedPoint {
        final String color;

        ColoredNamedPoint(int x, String name, String color) {
            super(x, name);
            this.color = color;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (!(obj instanceof ColoredNamedPoint other)) return false;
            return super.equals(other) && color.equals(other.color);
        }
    }

    // Cố sửa đối xứng khi so với Point thường, nhưng phá bắc cầu.
    static final class LenientColorPoint extends Point {
        final String color;

        LenientColorPoint(int x, String color) {
            super(x);
            this.color = color;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (!(obj instanceof Point other)) return false;

            if (!(obj instanceof LenientColorPoint colored)) {
                return super.equals(other);
            }
            return super.equals(colored)
                    && color.equals(colored.color);
        }
    }

    // Phương án hợp lệ: mọi cấp cùng so sánh theo ID bất biến.
    static class Entity {
        private final int id;

        Entity(int id) {
            this.id = id;
        }

        @Override
        public final boolean equals(Object obj) {
            if (this == obj) return true;
            if (!(obj instanceof Entity other)) return false;
            return id == other.id;
        }

        @Override
        public final int hashCode() {
            return Integer.hashCode(id);
        }
    }

    static class DetailedEntity extends Entity {
        final String description;

        DetailedEntity(int id, String description) {
            super(id);
            this.description = description;
        }
    }

    static final class ColoredEntity extends DetailedEntity {
        final String color;

        ColoredEntity(int id, String description, String color) {
            super(id, description);
            this.color = color;
        }
    }

    static void audit(String name, List<Sample> samples) {
        boolean reflexive = true;
        boolean nullRule = true;
        boolean symmetric = true;
        boolean transitive = true;
        boolean hashAgreement = true;

        for (Sample a : samples) {
            Object left = a.value();

            if (!left.equals(left)) reflexive = false;
            if (left.equals(null)) nullRule = false;

            for (Sample b : samples) {
                Object right = b.value();
                boolean ab = left.equals(right);
                boolean ba = right.equals(left);

                if (ab != ba) symmetric = false;
                if (ab && left.hashCode() != right.hashCode()) {
                    hashAgreement = false;
                }

                for (Sample c : samples) {
                    Object third = c.value();
                    if (ab && right.equals(third)
                            && !left.equals(third)) {
                        transitive = false;
                    }
                }
            }
        }

        System.out.printf(
                "%s: reflexive=%s, nullRule=%s, symmetry=%s, "
                        + "transitivity=%s, hashAgreement=%s%n",
                name, reflexive, nullRule, symmetric,
                transitive, hashAgreement);
    }

    public static void main(String[] args) {
        Point base = new Point(5);
        NamedPoint middle = new NamedPoint(5, "oak");
        ColoredNamedPoint leaf =
                new ColoredNamedPoint(5, "oak", "red");

        System.out.println("base.equals(middle): "
                + base.equals(middle));
        System.out.println("middle.equals(base): "
                + middle.equals(base));
        audit("Strict subclasses", List.of(
                new Sample("base", base),
                new Sample("middle", middle),
                new Sample("leaf", leaf)));

        Point bridge = new Point(9);
        LenientColorPoint red = new LenientColorPoint(9, "red");
        LenientColorPoint blue = new LenientColorPoint(9, "blue");

        System.out.println("red.equals(bridge): "
                + red.equals(bridge));
        System.out.println("bridge.equals(blue): "
                + bridge.equals(blue));
        System.out.println("red.equals(blue): "
                + red.equals(blue));
        audit("Lenient subclasses", List.of(
                new Sample("red", red),
                new Sample("bridge", bridge),
                new Sample("blue", blue)));

        audit("Final inherited ID", List.of(
                new Sample("root", new Entity(7)),
                new Sample("middle", new DetailedEntity(7, "A")),
                new Sample("leaf", new ColoredEntity(7, "A", "red")),
                new Sample("other", new ColoredEntity(8, "B", "blue"))));
    }
}
```

Chạy trong thư mục chứa tệp:

```bash
javac HierarchyEqualsAudit.java
java HierarchyEqualsAudit
```

Stdout:

```text
base.equals(middle): true
middle.equals(base): false
Strict subclasses: reflexive=true, nullRule=true, symmetry=false, transitivity=true, hashAgreement=true
red.equals(bridge): true
bridge.equals(blue): true
red.equals(blue): false
Lenient subclasses: reflexive=true, nullRule=true, symmetry=true, transitivity=false, hashAgreement=true
Final inherited ID: reflexive=true, nullRule=true, symmetry=true, transitivity=true, hashAgreement=true
```

**Cách đọc:**

- **`Strict subclasses`:** `Point.equals` dùng `instanceof Point`, nên nhận một `NamedPoint` cùng `x`. Nhưng `NamedPoint.equals` đòi đối số là `NamedPoint`, nên loại `Point`. Ma trận cặp phát hiện **đối xứng sai**. Với bộ ba mẫu cụ thể này, bắc cầu vẫn đúng; không thể kết luận phương thức hợp lệ chỉ vì cột bắc cầu là `true`.
- **`Lenient subclasses`:** `LenientColorPoint` bỏ qua màu khi đối số là `Point` thuần và so màu khi đối số cũng là `LenientColorPoint`. Mỗi cặp trong tập mẫu đối xứng, nhưng bộ ba `(red, bridge, blue)` làm **bắc cầu sai**.
- **`Final inherited ID`:** các cấp `Entity → DetailedEntity → ColoredEntity` kế thừa cùng một `equals/hashCode` dạng `final`, so sánh duy nhất theo `id`. Với chính sách đã chọn, lớp con không thể bổ sung điều kiện làm hai chiều hoặc bộ ba mâu thuẫn. Các trường mô tả/màu **cố ý không tham gia** quan hệ bằng nhau.

Trong ví dụ, các lớp sai `NamedPoint`, `ColoredNamedPoint` và `LenientColorPoint` kế thừa `Point.hashCode` dựa trên `x`. Đây là chủ ý để minh họa **đối xứng và bắc cầu độc lập** với lỗi hash: việc hai đối tượng không bằng nhau vẫn có thể trùng hash là hợp lệ. Trong hệ thống thật, cách chọn trường hash phải phù hợp với toàn bộ chính sách `equals`.

## 6. Mở rộng kiểm thử để bắt phản ví dụ tốt hơn

### Tạo mẫu khác biệt đúng một trường

Với mỗi mức, bổ sung các biến thể đổi một trường để phát hiện việc bỏ quên trường:

```text
Point(5), Point(6)
NamedPoint(5,"oak"), NamedPoint(5,"pine")
ColoredNamedPoint(5,"oak","red"),
ColoredNamedPoint(5,"oak","blue")
```

Nếu chính sách của lớp quy định trường màu phải tham gia bằng nhau, hai đối tượng khác màu không được tự nhiên bị gộp chung. Ngược lại, nếu toàn phân cấp cùng định nghĩa bằng nhau chỉ qua `id`, thay đổi các trường mô tả **không nên** thay đổi kết quả. Kết quả kỳ vọng phải xuất phát từ hợp đồng nghiệp vụ được chọn, không từ tên trường.

### Duyệt ma trận sau mỗi cấp mới

Khi thêm một lớp cháu, chạy lại không chỉ kiểm thử của lớp cháu mà cả các cặp với **mọi lớp tổ tiên** và những lớp con khác cùng cha. Lớp cha cũng có thể bắt đầu vi phạm hợp đồng khi một kiểu con mới xuất hiện, dù mã nguồn `equals` của lớp cha chưa hề thay đổi.

Có thể bổ sung danh sách mẫu qua bảng dữ liệu hoặc tham số hóa kiểm thử JUnit 5; phần quan trọng là cùng một bộ kiểm tra được áp dụng lên **tất cả các runtime type** trong phạm vi. Ví dụ `List<Sample>` của chương trình trên lưu chung các đối tượng kiểu `Object`, nên phép gọi `left.equals(right)` sử dụng **dynamic dispatch** tới phương thức thực tế của đối tượng bên trái. Đây chính là lý do đổi chiều phép gọi có thể cho kết quả khác nhau khi override sai.

### Xác minh hash, null, nhất quán và ngoại lệ

- Với mọi cặp mà `a.equals(b)` là `true`, kiểm tra hash bằng nhau. Không yêu cầu hai mã băm khác nhau khi `equals` là `false`.
- Với mọi đối tượng mẫu, thử `a.equals(null)` và `a.equals(new Object())`; kết quả kỳ vọng thông thường là `false`.
- Chạy lại các phép kiểm tra khi không thay đổi trạng thái liên quan để xem kết quả có ổn định.
- Nếu các trường tham gia `equals/hashCode` có thể thay đổi, thiết kế thêm thử nghiệm có kiểm soát. Tránh sửa các trường đó khi đối tượng đang làm khóa của `HashMap` hoặc nằm trong `HashSet`, vì có thể khiến thao tác tra cứu bị sai.
- Khi kiểm thử những cài đặt có khả năng ném ngoại lệ, bao rõ lỗi theo cặp/bộ ba để xác định phương thức nào bị hỏng. Ví dụ chương trình trên giả định `equals` trả boolean hợp lệ, nên không bao ngoại lệ trong vòng lặp.

Một tập thử nhỏ có thể chứa nhiều đối tượng **có cùng giá trị logic** nhưng khác tham chiếu, nhiều đối tượng khác nhau ở một trường, một đối tượng cha và nhiều lớp con. Chỉ sử dụng `a.equals(a)` hay hai instance cùng lớp không thể kiểm tra được nguy cơ do kế thừa.

## 7. Chọn chính sách bình đẳng phù hợp để kiểm thử có ý nghĩa

Có ba hướng thường gặp:

| Chính sách | Cách áp dụng | Điều phải chú ý |
| --- | --- | --- |
| **Bằng nhau theo kiểu runtime chính xác** | Dùng `getClass()` để yêu cầu cùng lớp trước khi so sánh trường. | Cha và con không bằng nhau, kể cả trùng dữ liệu cha; phải áp dụng nhất quán qua các override. |
| **Bằng nhau theo khóa chung bất biến** | Lớp cha định nghĩa `final equals/hashCode` dựa trên khóa đại diện cho cùng thực thể ở mọi cấp. | Trường bổ sung ở lớp con không được âm thầm thay đổi ý nghĩa của `equals`. |
| **Loại bỏ kế thừa khỏi lớp giá trị** | Dùng lớp `final` hoặc `record` cho kiểu giá trị; so sánh các thành phần được xác định rõ. | Các kiểu giá trị mới không tham gia bình đẳng qua một phân cấp có thể mở rộng. |

Nếu chọn kiểu runtime chính xác, một lớp cha có thể dùng:

```java
@Override
public boolean equals(Object obj) {
    if (this == obj) return true;
    if (obj == null || getClass() != obj.getClass()) return false;
    Point other = (Point) obj;
    return x == other.x;
}
```

Đoạn này là **minh họa bên trong lớp `Point` có trường `x`**, không phải tệp chạy riêng. Nếu có lớp con override `equals`, chính sách kiểm tra kiểu và cách gọi `super.equals` vẫn phải được thiết kế đồng bộ. Chỉ thay `instanceof` thành `getClass` ở một vị trí, rồi giữ những so sánh lỏng lẻo khác, **không tự động** chứng minh cả phân cấp đúng.

Chính sách khóa chung `final` của ví dụ chỉ phù hợp khi các thực thể có cùng `id` thực sự được xem là cùng giá trị **bất kể kiểu con**. Không nên áp dụng máy móc cho các loại khác nhau mà `id` có thể trùng nhưng ý nghĩa nghiệp vụ khác nhau. Với loại dữ liệu không cần thay đổi cấu trúc bằng kế thừa, lớp `final` hoặc `record` thường giảm đáng kể số tình huống phải kiểm thử.

Một lựa chọn mở rộng khác là mẫu `canEqual` để phối hợp bình đẳng trong phân cấp có override. Mẫu đó chỉ hữu ích khi được thiết kế và dùng nhất quán ở mọi cấp; vẫn cần ma trận cặp và bộ ba như trên để xác nhận hợp đồng thực tế.

## 8. Chiến lược kiểm thử và cách đọc kết quả thất bại

Dùng một vòng lặp chung như `audit` giúp phát hiện **tính chất của quan hệ bằng nhau** mà không phải viết riêng một câu lệnh `assert` cho từng cặp. Tuy nhiên, để một bộ kiểm thử có giá trị lâu dài:

1. **Nêu rõ quy tắc bằng nhau dự kiến** cho các cặp cùng lớp và khác lớp; các tiên đề chỉ nói quan hệ phải nhất quán, không quyết định giúp bạn cặp nào phải bằng nhau.
2. **Chọn mẫu phủ ít nhất ba mức** và các nhánh con liên quan, không chỉ những đối tượng cùng lớp. Sử dụng nhiều giá trị và ít nhất một cặp khác instance nhưng được kỳ vọng bằng nhau.
3. **Kiểm tra phản xạ/null** trước; sau đó **ma trận cặp có hướng** để bắt đối xứng.
4. **Kiểm tra mọi bộ ba có thứ tự** để bắt bắc cầu, in ra tên `(a,b,c)` gây thất bại để dễ sửa.
5. **Kiểm tra hash khi bằng nhau** và chạy lại sau khi thay đổi mẫu/thiết kế.
6. **Sửa quy tắc so sánh ở cấp phù hợp**, rồi chạy lại toàn bộ bộ kiểm thử của hệ phân cấp thay vì chỉ test trường hợp vừa hỏng.

Với `n` mẫu, cặp là `O(n²)`, bộ ba là `O(n³)`; thường nên dùng tập mẫu có chủ ý trong unit test, kết hợp kiểm thử sinh dữ liệu (*property-based testing*) khi mô hình có nhiều biến thể. Nếu kiểm tra kết quả thay đổi theo trạng thái, cần đảm bảo không có luồng khác đồng thời sửa các trường trong lúc kiểm thử; các tiên đề của `equals` giả định trạng thái dùng để so sánh vẫn ổn định.

### Câu hỏi tự kiểm tra

1. Nếu `Base.equals(Child)` là `true` nhưng `Child.equals(Base)` là `false`, hợp đồng nào bị vi phạm?
2. Vì sao chỉ thử `a.equals(b)` mà không thử `b.equals(a)` có thể bỏ sót lỗi?
3. Với `red.equals(plain) == true`, `plain.equals(blue) == true`, nhưng `red.equals(blue) == false`, lỗi gì xảy ra? Thứ tự của ba đối tượng có ý nghĩa thế nào?
4. Nếu cả hai phía đều dùng mã băm bằng nhau nhưng không bằng nhau theo `equals`, đó có phải vi phạm không?
5. Khi thêm lớp cháu, vì sao phải chạy lại các kiểm thử của **lớp cha và lớp giữa**?
6. Khi nào được chủ động bỏ qua các trường mới của lớp con trong `equals`?

**Ghi nhớ:** Với `equals` và kế thừa, cần kiểm tra **mọi cặp theo hai chiều** để xác minh đối xứng và **mọi bộ ba có thứ tự** để xác minh bắc cầu. Hãy lập mẫu ở các cấp cha, con, cháu và nhánh khác nhau, đồng thời xác định rõ chính sách bình đẳng trước khi kết luận triển khai đúng.