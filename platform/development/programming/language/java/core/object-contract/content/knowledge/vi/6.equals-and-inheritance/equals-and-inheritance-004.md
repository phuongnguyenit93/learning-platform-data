# Ảnh hưởng của lựa chọn kiểm tra kiểu tới quan hệ lớp cha, lớp con khi triển khai `equals()` trong Java

Khi ghi đè `equals(Object)`, kiểm tra kiểu không chỉ quyết định có ép kiểu được hay không: nó còn quyết định **những lớp nào được phép xem đối tượng của nhau là bằng nhau**. Sự khác biệt giữa `instanceof` và `getClass()` đặc biệt quan trọng trong quan hệ kế thừa, nơi lớp con có thể bổ sung trạng thái mà lớp cha không biết.

Bài học này tập trung vào ảnh hưởng của lựa chọn kiểm tra kiểu đối với **equality của lớp cha và lớp con**, các lỗi **đối xứng** và **bắc cầu**, và cách chọn thiết kế có hợp đồng `equals()`/`hashCode()` nhất quán.

## 1. Hợp đồng `equals()` cần giữ khi có kế thừa

Với các tham chiếu khác `null`, `equals()` phải đáp ứng:

1. **Phản xạ (reflexive):** `a.equals(a)` là `true`.
2. **Đối xứng (symmetric):** `a.equals(b)` và `b.equals(a)` luôn có cùng kết quả.
3. **Bắc cầu (transitive):** nếu `a.equals(b)` và `b.equals(c)` đúng, `a.equals(c)` cũng phải đúng.
4. **Nhất quán (consistent):** kết quả không đổi qua các lần gọi khi trạng thái dùng để so sánh không thay đổi.
5. **Không bằng `null`:** `a.equals(null)` luôn là `false`.

Đồng thời, **nếu `a.equals(b)` là `true`, mã băm `a.hashCode()` và `b.hashCode()` phải bằng nhau**. Ngược lại, hai mã băm bằng nhau không chứng minh hai đối tượng bằng nhau.

Trong kế thừa, khó khăn là lớp cha chỉ biết các trường của chính nó, còn lớp con có thể bổ sung trường quan trọng cho định nghĩa giá trị. Nếu lớp cha cho phép đối chiếu với lớp con nhưng lớp con áp dụng điều kiện chặt hơn, phép so sánh dễ mất tính đối xứng. Nếu cố dung hòa hai cách, phép so sánh có thể mất tính bắc cầu.

## 2. `instanceof` và `getClass()` kiểm tra hai quan hệ khác nhau

### Kiểm tra bằng `instanceof`

~~~java
if (!(other instanceof Point point)) {
    return false;
}
~~~

Đây là đoạn minh họa nằm **bên trong** phương thức `equals(Object other)`. Java 17 hỗ trợ pattern matching với `instanceof`: khi điều kiện thành công, biến `point` có kiểu `Point` để dùng ngay.

Điều kiện đúng khi object thuộc lớp `Point` **hoặc một lớp con của `Point`** (và cũng có thể áp dụng với interface được triển khai). Với `other == null`, `instanceof` trả `false`. Do đó, dùng `instanceof` trong `Point.equals` cho phép `Point` so sánh tọa độ của cả các lớp kế thừa, nếu chúng có thể ép kiểu sang `Point`.

### Kiểm tra bằng `getClass()`

~~~java
if (other == null || getClass() != other.getClass()) {
    return false;
}
~~~

Đây cũng là đoạn minh họa bên trong `equals(Object other)`. Kiểm tra `getClass()` yêu cầu **đúng cùng một lớp runtime**: một instance `Point` và một instance `ColorPoint extends Point` là hai kiểu runtime khác nhau, nên `Point.equals(colorPoint)` trả `false`, ngay cả khi tọa độ giống hệt nhau.

Việc kiểm tra `null` trước `other.getClass()` là bắt buộc để tránh `NullPointerException`. Trong phương thức instance, `getClass()` tương đương `this.getClass()`.

| Câu hỏi | `other instanceof Point` | `getClass() == other.getClass()` trong `Point.equals` |
|---|---|---|
| `other` là `Point` | `true` | `true` |
| `other` là `ColorPoint extends Point` | `true` | `false` |
| `other` không thuộc họ `Point` | `false` | `false` |
| `other == null` | `false` | Phải kiểm tra `null` trước |

**Khác biệt cốt lõi:** `instanceof` coi *khả năng thuộc một hệ kiểu* là điều kiện để bước vào so sánh; `getClass()` yêu cầu *cùng lớp runtime*. Cả hai chỉ là **bước kiểm tra kiểu**, chưa đủ để `equals()` đúng: phần so sánh trường, `hashCode()` và cách ghi đè trong lớp con vẫn phải tuân theo hợp đồng.

## 3. Lỗi đối xứng khi lớp cha dùng `instanceof` nhưng lớp con thêm trường

Giả sử `Point` có `x`, `y`; lớp con `ColorPoint` bổ sung `color`. Lớp cha muốn xem hai điểm cùng tọa độ là bằng nhau, trong khi lớp con muốn màu cũng phải khớp.

- `Point.equals` dùng `instanceof Point` nên chấp nhận object `ColorPoint` chỉ dựa trên `x`, `y`.
- `ColorPoint.equals` chỉ chấp nhận `ColorPoint` và yêu cầu màu giống nhau.
- Với `p = Point(1, 2)` và `red = ColorPoint(1, 2, "red")`, ta nhận được `p.equals(red) == true` nhưng `red.equals(p) == false`.

Đây là **vi phạm đối xứng**: cùng hai object nhưng kết quả phụ thuộc thứ tự gọi. Việc lớp con thêm trường có ý nghĩa là nguyên nhân sâu hơn; `instanceof` cho phép lớp cha so với lớp con nhưng không cho lớp cha biết điều kiện mà lớp con cần.

Lỗi này còn gây khó cho `hashCode()`. Nếu `Point.hashCode()` dùng tọa độ còn `ColorPoint.hashCode()` thêm màu, ta có thể có cặp mà `Point.equals(ColorPoint)` trả `true` nhưng hash khác nhau, vi phạm thêm hợp đồng hash. **Thêm `hashCode()` vào lớp con không sửa được lỗi `equals()` thiếu đối xứng**; hai phương thức phải được thiết kế cùng nhau.

## 4. Cố sửa đối xứng có thể phá tính bắc cầu

Một cách vá thường gặp là bảo lớp con: nếu đối tượng cần so sánh chỉ là lớp cha, hãy so tọa độ; nếu là lớp con cùng loại, hãy so cả màu.

Khi đó với cùng tọa độ:

- `red = ColorPoint(1, 2, "red")` bằng `plain = Point(1, 2)`.
- `plain = Point(1, 2)` bằng `blue = ColorPoint(1, 2, "blue")`.
- Nhưng `red` **không bằng** `blue` vì màu khác nhau.

Kết quả: `red.equals(plain)` đúng **và** `plain.equals(blue)` đúng nhưng `red.equals(blue)` sai. Phép so sánh đã **mất tính bắc cầu**. Có thể làm đối xứng và hash nhất quán ở ví dụ này, nhưng vẫn không có một quan hệ equality hợp lệ. Việc "so theo lớp cha nếu không cùng lớp con" không phải giải pháp tổng quát.

Bài toán căn bản nằm ở định nghĩa: muốn cả `Point` không màu bằng hai `ColorPoint` khác màu thì theo tính bắc cầu, hai điểm có màu kia cũng phải bằng nhau; điều đó mâu thuẫn với yêu cầu màu là một phần giá trị. Không thể giải quyết mâu thuẫn định nghĩa này bằng đổi cú pháp `instanceof`.

## 5. Ví dụ Java 17 chạy được: lỗi đối xứng, lỗi bắc cầu và cách sửa

Lưu toàn bộ chương trình sau thành file **`EqualsInheritanceDemo.java`**. Các lớp lồng nhau dùng tên khác nhau để ba tình huống không ảnh hưởng lẫn nhau.

~~~java
import java.util.HashSet;
import java.util.List;
import java.util.Objects;

public class EqualsInheritanceDemo {

    // 1) Lớp cha dùng instanceof: cho phép lớp con đi qua.
    static class NaivePoint {
        final int x, y;

        NaivePoint(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof NaivePoint p)) return false;
            return x == p.x && y == p.y;
        }

        @Override
        public int hashCode() {
            return Objects.hash(x, y);
        }
    }

    // Lớp con siết chặt điều kiện: gây lỗi đối xứng.
    static class NaiveColorPoint extends NaivePoint {
        final String color;

        NaiveColorPoint(int x, int y, String color) {
            super(x, y);
            this.color = color;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof NaiveColorPoint p)) return false;
            return super.equals(other)
                    && Objects.equals(color, p.color);
        }

        @Override
        public int hashCode() {
            return Objects.hash(super.hashCode(), color);
        }
    }

    // 2) Phiên bản thử dung hòa lớp cha và lớp con.
    static class FlexiblePoint {
        final int x, y;

        FlexiblePoint(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof FlexiblePoint p)) return false;
            return x == p.x && y == p.y;
        }

        @Override
        public int hashCode() {
            return Objects.hash(x, y);
        }
    }

    static class FlexibleColorPoint extends FlexiblePoint {
        final String color;

        FlexibleColorPoint(int x, int y, String color) {
            super(x, y);
            this.color = color;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof FlexiblePoint)) return false;
            if (!(other instanceof FlexibleColorPoint p)) {
                return super.equals(other); // Chỉ so tọa độ với lớp cha.
            }
            return super.equals(other)
                    && Objects.equals(color, p.color);
        }

        // Cố ý kế thừa hashCode theo tọa độ để các cặp
        // bằng nhau giữa lớp cha/con có cùng mã băm.
        // Việc này KHÔNG thể sửa lỗi bắc cầu.
    }

    // 3) Giải pháp cùng lớp runtime: getClass().
    static class StrictPoint {
        final int x, y;

        StrictPoint(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (other == null || getClass() != other.getClass()) {
                return false;
            }
            StrictPoint p = (StrictPoint) other;
            return x == p.x && y == p.y;
        }

        @Override
        public int hashCode() {
            return Objects.hash(x, y);
        }
    }

    static class StrictColorPoint extends StrictPoint {
        final String color;

        StrictColorPoint(int x, int y, String color) {
            super(x, y);
            this.color = color;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (other == null || getClass() != other.getClass()) {
                return false;
            }
            StrictColorPoint p = (StrictColorPoint) other;
            return super.equals(other)
                    && Objects.equals(color, p.color);
        }

        @Override
        public int hashCode() {
            return Objects.hash(super.hashCode(), color);
        }
    }

    // 4) Composition/value type: không có kế thừa giá trị.
    record ColoredPoint(int x, int y, String color) {}

    public static void main(String[] args) {
        NaivePoint p = new NaivePoint(1, 2);
        NaiveColorPoint red = new NaiveColorPoint(1, 2, "red");
        System.out.println("naive parent -> child: " + p.equals(red));
        System.out.println("naive child -> parent: " + red.equals(p));

        FlexiblePoint plain = new FlexiblePoint(1, 2);
        FlexibleColorPoint flexibleRed =
                new FlexibleColorPoint(1, 2, "red");
        FlexibleColorPoint flexibleBlue =
                new FlexibleColorPoint(1, 2, "blue");
        System.out.println("flexible red -> plain: "
                + flexibleRed.equals(plain));
        System.out.println("flexible plain -> blue: "
                + plain.equals(flexibleBlue));
        System.out.println("flexible red -> blue: "
                + flexibleRed.equals(flexibleBlue));

        StrictPoint strictPlain = new StrictPoint(1, 2);
        StrictColorPoint strictRed = new StrictColorPoint(1, 2, "red");
        StrictColorPoint sameRed = new StrictColorPoint(1, 2, "red");
        StrictColorPoint strictBlue = new StrictColorPoint(1, 2, "blue");
        System.out.println("strict parent -> child: "
                + strictPlain.equals(strictRed));
        System.out.println("strict child -> parent: "
                + strictRed.equals(strictPlain));
        System.out.println("strict red -> red copy: "
                + strictRed.equals(sameRed));
        System.out.println("strict red -> blue: "
                + strictRed.equals(strictBlue));
        System.out.println("strict set size: "
                + new HashSet<>(List.of(
                        strictPlain, strictRed, sameRed, strictBlue)).size());

        ColoredPoint valueA = new ColoredPoint(1, 2, "red");
        ColoredPoint valueB = new ColoredPoint(1, 2, "red");
        System.out.println("record value equality: "
                + valueA.equals(valueB));
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac EqualsInheritanceDemo.java
java EqualsInheritanceDemo
~~~

Đầu ra kỳ vọng:

~~~text
naive parent -> child: true
naive child -> parent: false
flexible red -> plain: true
flexible plain -> blue: true
flexible red -> blue: false
strict parent -> child: false
strict child -> parent: false
strict red -> red copy: true
strict red -> blue: false
strict set size: 3
record value equality: true
~~~

**Đọc kết quả theo ba lớp vấn đề:**

- **Naive:** `NaivePoint` chấp nhận `NaiveColorPoint`; chiều ngược lại bị từ chối. Một chiều `true`, một chiều `false`: **đối xứng thất bại**.
- **Flexible:** cả `red` và `blue` đều bằng `plain` nhưng không bằng nhau: **bắc cầu thất bại**. Không nên áp dụng chiến lược này.
- **Strict:** so sánh chéo kiểu trả `false` ở cả hai chiều; hai `StrictColorPoint` cùng tọa độ và màu bằng nhau. `HashSet` chứa 3 giá trị phân biệt: điểm gốc, điểm đỏ, điểm xanh.
- **Record:** `ColoredPoint` là kiểu giá trị bất biến và mặc nhiên là `final`; Java sinh `equals()`/`hashCode()` từ các component. Không tồn tại lớp con `ColoredPoint` có thể âm thầm thay đổi nghĩa của equality.

Lưu ý quan trọng trong ví dụ **Strict**: lớp con có gọi `super.equals(other)`, nhưng cả lớp cha và lớp con đều kiểm tra chính xác lớp runtime trước khi so trường. Nếu bỏ kiểm tra `getClass()` ở lớp cha, hoặc ghi đè không đồng bộ giữa các lớp, kết quả có thể khác.

## 6. Khi nào dùng `getClass()`?

Dùng `getClass()` khi **hai object chỉ được bằng nhau nếu có cùng kiểu runtime chính xác**. Đây thường là lựa chọn rõ ràng khi một lớp cơ sở **có thể được kế thừa**, và các lớp con được phép bổ sung trường có ý nghĩa đối với equality.

Mẫu cho lớp cha:

~~~java
@Override
public boolean equals(Object other) {
    if (this == other) return true;
    if (other == null || getClass() != other.getClass()) {
        return false;
    }
    Point p = (Point) other;
    return x == p.x && y == p.y;
}
~~~

Đây là snippet đặt trong lớp `Point` có sẵn trường `x`, `y`; không phải chương trình độc lập. Một lớp con thêm dữ liệu bình đẳng có thể kiểm tra `getClass()` lần nữa, gọi `super.equals(other)`, rồi so các trường riêng và ghi đè `hashCode()` tương ứng.

**Ưu điểm:** ranh giới equality giữa các lớp rõ ràng; lớp cha và lớp con không bị tự động xem là cùng giá trị chỉ vì chia sẻ trường.

**Đánh đổi:** hai thực thể có cùng dữ liệu nghiệp vụ nhưng có **hai kiểu runtime khác nhau** sẽ không bằng nhau. Điều này có thể gây bất ngờ khi dùng **proxy subclass** do thư viện tạo động (chẳng hạn một số cơ chế ORM). Nếu ứng dụng sử dụng proxy, cần tìm hiểu quy tắc identity/equality của framework và thiết kế riêng cho mô hình entity đó; không thể sửa an toàn chỉ bằng thay `getClass()` thành `instanceof`.

`getClass()` cũng **không tự bảo đảm** hợp đồng: vẫn phải tránh trường mutable trong hash key, viết hash tương thích và duy trì equality khi lớp con bổ sung trạng thái.

## 7. Khi nào dùng `instanceof`?

`instanceof` hợp lý khi có **một khái niệm giá trị chung trên cả hệ phân cấp**, và các lớp con không được thay đổi tiêu chí bằng nhau, hoặc khi lớp **không cho phép kế thừa**.

Ví dụ đối với lớp bất biến và `final`:

~~~java
final class Point {
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
        return java.util.Objects.hash(x, y);
    }
}
~~~

Đây là một khai báo lớp hoàn chỉnh, nhưng không có `main`; có thể dùng cùng các lớp khác trong dự án. Vì `Point` là `final`, không có `ColorPoint extends Point`, nên điểm yếu về lớp con bổ sung trường không phát sinh. Kiểu `record Point(int x, int y) {}` cũng là lựa chọn gọn khi đúng với thiết kế dữ liệu.

Nếu lớp vẫn cho kế thừa và dùng `instanceof`, phải trả lời câu hỏi: **lớp con có được thêm trường ảnh hưởng equality không?** Nếu không được, cần quy ước và ràng buộc thiết kế nhất quán, ví dụ dùng các lớp con chỉ bổ sung hành vi, không thay đổi danh tính giá trị. Chỉ dựa vào lời hứa "lớp con không override equals" không bảo vệ trước những thay đổi ngoài ý muốn về sau.

## 8. Mẫu `canEqual` cho hệ phân cấp cần mở rộng

Một kỹ thuật khác là cho cả hai vế **chấp thuận khả năng so sánh**. Lớp cha hỏi object bên kia có muốn được xem là cùng miền equality hay không qua `canEqual`. Lớp con bổ sung trạng thái có thể từ chối equality với lớp cha để bảo toàn đối xứng.

Minh họa phần thiết yếu (hai lớp dùng trong hệ phân cấp, không có `main`):

~~~java
import java.util.Objects;

class CanPoint {
    private final int x, y;

    CanPoint(int x, int y) {
        this.x = x;
        this.y = y;
    }

    protected boolean canEqual(Object other) {
        return other instanceof CanPoint;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof CanPoint p)) return false;
        return p.canEqual(this) && x == p.x && y == p.y;
    }

    @Override
    public int hashCode() {
        return Objects.hash(x, y);
    }
}

class CanColorPoint extends CanPoint {
    private final String color;

    CanColorPoint(int x, int y, String color) {
        super(x, y);
        this.color = color;
    }

    @Override
    protected boolean canEqual(Object other) {
        return other instanceof CanColorPoint;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof CanColorPoint p)) return false;
        return p.canEqual(this)
                && super.equals(other)
                && Objects.equals(color, p.color);
    }

    @Override
    public int hashCode() {
        return Objects.hash(super.hashCode(), color);
    }
}
~~~

Ở đây `new CanPoint(1,2).equals(new CanColorPoint(1,2,"red"))` trả `false`: đối tượng lớp con không `canEqual` với lớp cha. Chiều ngược lại cũng `false` vì kiểm tra `instanceof CanColorPoint` thất bại. Hai `CanColorPoint` cùng dữ liệu thì bằng nhau và có cùng hash.

`canEqual` hữu ích khi thực sự cần một **hệ phân cấp mở** với hợp đồng equality được kiểm soát, nhưng **không tự động giải quyết mọi nhánh kế thừa**. Các lớp con khác nếu bổ sung trạng thái có ý nghĩa vẫn phải phối hợp `canEqual`, `equals`, `hashCode` và bảo toàn quan hệ bắc cầu giữa các kiểu. Nếu không có yêu cầu cụ thể cho kế thừa, `final`, `record` hoặc **composition** thường giảm rủi ro hơn.

## 9. Thiết kế thay thế: composition và phân biệt entity với value object

Kế thừa dữ liệu không luôn là quan hệ phù hợp. Nếu `ColorPoint` thực chất là "một giá trị gồm một điểm và một màu", có thể dùng composition:

~~~java
record Point(int x, int y) {}
record ColoredPoint(Point point, String color) {}
~~~

Đây là hai kiểu record độc lập. `ColoredPoint` **chứa** `Point` thay vì **là một lớp con của** `Point`. Không có yêu cầu `Point.equals(ColoredPoint)` vì hai kiểu đại diện cho hai miền giá trị khác nhau. Equality do record sinh dựa trên các component; bất biến và không có lớp con làm hợp đồng dễ dự đoán.

Đối với **entity**, cần xem kỹ định danh nghiệp vụ có ổn định hay không. Hai lớp con đại diện cho cùng một thực thể lưu trữ có thể cần một chính sách khác so với value object, đặc biệt khi có ORM/proxy. Nếu equality theo ID, phải quyết định hành vi với ID chưa cấp, lớp runtime khác nhau và cách tính hash không đổi trong vòng đời entity. Không sử dụng `instanceof` như một cách vá chung cho mọi entity.

## 10. Ảnh hưởng trực tiếp đến collection

Một sai sót khi viết `equals()` không dừng lại ở phép `if`:

- `HashSet.add`/`contains` và `HashMap.put`/`get` cần `equals()` **và** `hashCode()` đúng hợp đồng. Nếu kết quả `a.equals(b)` phụ thuộc chiều gọi, việc nhận diện khóa có thể phụ thuộc thứ tự tra cứu và chi tiết triển khai; nếu hash cũng không nhất quán, object logic "bằng nhau" có thể bị lưu ở những bucket khác nhau.
- `List.contains` sử dụng equality để tìm phần tử; kết quả với quan hệ không đối xứng có thể không khớp trực giác khi đổi đối tượng tìm kiếm và phần tử chứa trong list.
- `TreeSet`/`TreeMap` dùng `compareTo` hoặc `Comparator` để xét khóa tương đương; `compare == 0` chưa chắc đồng nghĩa `equals == true`. Khi phối hợp equality và ordering, cần thiết kế cả hai hợp đồng, nhưng **đổi `getClass`/`instanceof` không tự sửa comparator**.

Nếu các trường tham gia equality/hash có thể thay đổi sau khi đưa vào hash collection, ngay cả triển khai `equals` vốn đúng cũng có thể làm tra cứu thất bại. Trường hợp value object nên ưu tiên bất biến.

## 11. Checklist trước khi quyết định kiểm tra kiểu

| Câu hỏi thiết kế | Hướng chọn |
|---|---|
| Lớp có thể được kế thừa không? | Nếu không cần: cân nhắc `final` hoặc `record` |
| Lớp con có thêm trường quyết định equality không? | Tránh để `instanceof` ở cha chấp nhận con theo một định nghĩa rộng hơn |
| Equality giữa các lớp runtime khác nhau có phải yêu cầu nghiệp vụ không? | Chỉ cho phép khi định nghĩa tương đương xuyên lớp thống nhất và bảo toàn mọi hợp đồng |
| Cần mọi lớp con có equality riêng theo đầy đủ trạng thái? | Cân nhắc `getClass()` và override đồng bộ tại từng lớp |
| Có proxy class do framework sinh ra không? | Xác minh quy tắc định danh của framework trước khi chọn runtime-class equality |
| Có thật sự cần kế thừa dữ liệu không? | Cân nhắc composition cho value object |
| Hash code có lấy từ đúng các trường dùng để so sánh không? | Kiểm thử các object bằng nhau có cùng hash |
| Có dùng làm khóa `HashMap`/`HashSet` không? | Ưu tiên trạng thái bất biến và hợp đồng equality rõ ràng |

**Kiểm thử quan hệ**, không chỉ vài cặp riêng lẻ: kiểm tra `a.equals(a)`, `a.equals(b) == b.equals(a)`, tam giác `a → b → c`, trường hợp `null`, object khác tọa độ/khác trường con, và mã băm của cặp bằng nhau. Khi hệ phân cấp sâu hoặc có nhiều nhánh, hãy thử cả đối tượng thuộc các lớp sibling, chứ không chỉ một lớp cha và một lớp con.

## 12. Tự kiểm tra

**Câu 1.** Lớp cha `Shape` dùng `other instanceof Shape` và chỉ so `id`. Lớp con `ColoredShape` bổ sung màu vào `equals`. Rủi ro nào xuất hiện?  
**Đáp án:** Đối xứng có thể vỡ: lớp cha cho hai object bằng nhau theo ID, lớp con từ chối đối tượng cha. Nếu hash ở lớp con cũng xét màu, còn có nguy cơ vi phạm hợp đồng hash.

**Câu 2.** Đổi lớp cha sang `getClass()` có tự động làm mọi `equals()` trong hệ phân cấp đúng không?  
**Đáp án:** Không. Nó chỉ từ chối equality giữa các lớp runtime khác nhau. So sánh trường, hash, tính bất biến và các override trong lớp con vẫn phải đúng.

**Câu 3.** Vì sao không nên cho `ColorPoint(red)` bằng `Point` và `Point` bằng `ColorPoint(blue)` nhưng lại nói `red` khác `blue`?  
**Đáp án:** Vì phá tính bắc cầu của `equals()`. Nếu A bằng B, B bằng C thì A phải bằng C.

**Câu 4.** Khi lớp giá trị không cần kế thừa và mọi trường đều phải tham gia equality, lựa chọn nào đơn giản?  
**Đáp án:** Một `record` hoặc lớp `final` bất biến, với `equals`/`hashCode` dựa trên toàn bộ trạng thái có ý nghĩa.

**Kết luận:** Chọn `instanceof` nghĩa là cho phép so sánh trong **họ kiểu**; chọn `getClass()` nghĩa là yêu cầu **chính xác cùng lớp runtime**. Với kế thừa, câu hỏi quan trọng nhất là **lớp con có thêm trạng thái làm thay đổi nghĩa của "bằng nhau" không?** Nếu có, cần đặt ranh giới equality rõ ràng hoặc thay đổi mô hình dữ liệu để tránh vi phạm đối xứng, bắc cầu và hash.
