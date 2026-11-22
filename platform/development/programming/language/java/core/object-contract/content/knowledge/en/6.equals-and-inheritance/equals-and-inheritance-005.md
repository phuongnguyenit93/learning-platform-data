# Gọi `super.equals()` và những điều việc đó không tự bảo đảm

Khi một lớp Java kế thừa lớp khác, việc gọi `super.equals(other)` trong `equals()` của lớp con trông có vẻ là cách tái sử dụng phần so sánh chung. **Nó chỉ gọi triển khai `equals()` của lớp cha; nó không tự động bảo đảm hợp đồng `equals()` trên toàn bộ cây kế thừa.** Đặc biệt, lớp cha và lớp con có thể bất đồng về loại đối tượng nào được phép bằng nhau; điều này làm hỏng **tính đối xứng** hoặc **tính bắc cầu** dù từng phép kiểm tra trường riêng lẻ đều có vẻ hợp lý.

Bài học tập trung vào cách hoạt động của `super.equals()`, những lỗi đặc trưng khi thêm trạng thái vào lớp con và các phương án thiết kế an toàn.

## 1. `super.equals(other)` thực sự làm gì?

Trong một phương thức của lớp con, lệnh:

```java
@Override
public boolean equals(Object other) {
    return super.equals(other);
}
```

gọi triển khai `equals(Object)` được kế thừa từ lớp cha. Ý nghĩa của lệnh phụ thuộc **lớp cha đã cài đặt `equals()` như thế nào**:

- Nếu lớp cha không ghi đè `equals()`, cuối cùng lời gọi dùng `Object.equals()`: chỉ hai tham chiếu trỏ tới cùng đối tượng mới bằng nhau (`this == other`).
- Nếu lớp cha ghi đè `equals()` để so sánh một số trường, lời gọi kiểm tra đúng những điều kiện mà lớp cha đã viết, bao gồm chính sách kiểm tra kiểu (`instanceof` hay `getClass()`).
- Nếu lớp cha có phương thức phụ được override rồi gọi từ `equals()`, việc thực thi bên trong vẫn có thể chịu ảnh hưởng của đa hình. Gọi `super.equals()` không có nghĩa là toàn bộ quá trình chạy bị tách khỏi lớp con.

Ví dụ:

```java
class Parent {
    final int id;

    Parent(int id) {
        this.id = id;
    }

    @Override
    public boolean equals(Object obj) {
        return obj instanceof Parent other && id == other.id;
    }

    @Override
    public int hashCode() {
        return Integer.hashCode(id);
    }
}

class Child extends Parent {
    final String label;

    Child(int id, String label) {
        super(id);
        this.label = label;
    }

    // Không ghi đè equals/hashCode:
    // label không tham gia vào quan hệ bằng nhau.
}
```

`new Child(1, "A").equals(new Child(1, "B"))` trả `true` vì lớp con đang thừa hưởng quy tắc chỉ xét `id`. Đây có thể là chủ ý nếu `label` chỉ là thông tin phụ, nhưng sẽ sai nếu `label` cũng là một phần giá trị phải so sánh. **Kế thừa `equals()` không tự quyết định trường mới nào quan trọng.**

Ngược lại, việc lớp con viết `return super.equals(obj) && ...` chỉ bổ sung một điều kiện ở **hướng gọi từ lớp con**. Lớp cha vẫn dùng định nghĩa cũ khi tự so sánh với lớp con.

## 2. Hợp đồng `equals()` cần giữ trong kế thừa

Với các đối tượng không null `x`, `y`, `z`, quan hệ bằng nhau hợp lệ phải thỏa:

1. **Phản xạ:** `x.equals(x)` là `true`.
2. **Đối xứng:** `x.equals(y)` và `y.equals(x)` có cùng giá trị.
3. **Bắc cầu:** nếu `x.equals(y)` và `y.equals(z)`, thì `x.equals(z)`.
4. **Nhất quán:** khi trạng thái dùng để so sánh không đổi, các lần gọi phải cho cùng kết quả.
5. **So với null:** `x.equals(null)` là `false`.

Khi ghi đè `equals()`, còn phải bảo đảm hợp đồng với `hashCode()`: nếu `x.equals(y)` là `true` thì `x.hashCode() == y.hashCode()`. Chiều ngược lại không bắt buộc. Việc lớp cha có sẵn một triển khai `hashCode()` đúng cho **quy tắc bằng nhau của riêng lớp cha** không có nghĩa quy tắc đó còn đúng nếu lớp con định nghĩa lại tính bằng nhau.

**Điểm cốt lõi:** `equals()` là quan hệ giữa **hai đối tượng**, nên phải xét cả hướng lớp cha → lớp con lẫn lớp con → lớp cha, và cả chuỗi gồm **ba đối tượng** khi đánh giá tính bắc cầu.

## 3. Lỗi đối xứng: lớp cha nhận lớp con, lớp con từ chối lớp cha

Giả sử `Point` chỉ có tọa độ `(x, y)` và dùng `instanceof Point` trong `equals()`. `ColoredPoint` bổ sung màu sắc. Lớp con chỉ cho phép so sánh với `ColoredPoint`, sau đó gọi `super.equals(other)` và so thêm màu.

- `point.equals(coloredPoint)` có thể là `true` vì một `ColoredPoint` **cũng là** `Point` và có cùng tọa độ.
- `coloredPoint.equals(point)` là `false` vì đối tượng `point` không phải `ColoredPoint`.

Cả hai phương thức đều đọc đúng các trường mà chúng quan tâm, nhưng **vi phạm tính đối xứng**. `super.equals()` trả `true` cho hai lớp con cùng tọa độ không thể làm cho lớp cha tự biết về điều kiện màu sắc mới.

## 4. Lỗi bắc cầu: cố cho lớp con so bằng lớp cha khi phù hợp

Một cách vá hấp dẫn là để lớp con so sánh như `Point` nếu đối tượng kia chỉ là `Point`, nhưng so thêm màu nếu cả hai là `ColoredPoint`. Khi đó:

- `đỏ.equals(point)` là `true`, vì cùng tọa độ.
- `point.equals(xanh)` là `true`, vì cùng tọa độ.
- `đỏ.equals(xanh)` là `false`, vì khác màu.

Tính đối xứng cho ba phép so sánh này có thể được giữ, nhưng **tính bắc cầu bị phá**: từ `đỏ == point` và `point == xanh` đáng lẽ phải suy ra `đỏ == xanh`.

### 4.1. Chạy cả hai lỗi bằng Java 17+

Lưu thành file **`EqualsInheritancePitfall.java`**:

```java
import java.util.Objects;

class Point {
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
        return obj instanceof Point other
                && x == other.x
                && y == other.y;
    }

    @Override
    public int hashCode() {
        return Objects.hash(x, y);
    }
}

// Phiên bản 1: chỉ nhận đúng nhóm lớp con.
// Sai tính đối xứng khi Point vẫn nhận mọi instanceof Point.
class StrictColorPoint extends Point {
    private final String color;

    StrictColorPoint(int x, int y, String color) {
        super(x, y);
        this.color = Objects.requireNonNull(color);
    }

    @Override
    public boolean equals(Object obj) {
        if (!(obj instanceof StrictColorPoint other)) {
            return false;
        }
        return super.equals(obj) && color.equals(other.color);
    }

    // Cố ý giữ hashCode theo tọa độ để cô lập lỗi đối xứng.
    // Hash trùng vẫn hợp lệ; nó không cứu được equals sai.
}

// Phiên bản 2: so như Point khi gặp Point thông thường.
// Sai tính bắc cầu khi hai lớp con khác màu.
class FlexibleColorPoint extends Point {
    private final String color;

    FlexibleColorPoint(int x, int y, String color) {
        super(x, y);
        this.color = Objects.requireNonNull(color);
    }

    @Override
    public boolean equals(Object obj) {
        if (!(obj instanceof Point)) {
            return false;
        }
        if (!(obj instanceof FlexibleColorPoint other)) {
            return super.equals(obj);
        }
        return super.equals(obj) && color.equals(other.color);
    }

    // Cũng dùng hashCode theo tọa độ, đủ để minh họa
    // rằng hashCode hợp lệ không kéo theo equals hợp lệ.
}

public class EqualsInheritancePitfall {
    public static void main(String[] args) {
        Point point = new Point(2, 3);
        StrictColorPoint redStrict =
                new StrictColorPoint(2, 3, "red");

        System.out.println("point -> strict: "
                + point.equals(redStrict));
        System.out.println("strict -> point: "
                + redStrict.equals(point));

        FlexibleColorPoint red =
                new FlexibleColorPoint(2, 3, "red");
        FlexibleColorPoint blue =
                new FlexibleColorPoint(2, 3, "blue");

        System.out.println("red -> point: "
                + red.equals(point));
        System.out.println("point -> blue: "
                + point.equals(blue));
        System.out.println("red -> blue: "
                + red.equals(blue));
    }
}
```

Chạy:

```bash
javac EqualsInheritancePitfall.java
java EqualsInheritancePitfall
```

Kết quả:

```text
point -> strict: true
strict -> point: false
red -> point: true
point -> blue: true
red -> blue: false
```

Hai ví dụ là **phản ví dụ có chủ ý**, không phải mẫu `equals()` nên dùng trong dự án. Trong cả hai, các lớp con kế thừa hash theo tọa độ để tránh tạo thêm sự khác biệt về hash; **ngay cả khi mã băm như nhau, các lỗi đối xứng/bắc cầu vẫn tồn tại**. Đừng cho rằng cập nhật `hashCode()` có thể sửa các lỗi logic này.

## 5. `getClass()` có giúp không?

Một phương án đơn giản là lớp cha chỉ cho phép bằng nhau khi **chính xác cùng lớp runtime**:

```java
if (obj == null || getClass() != obj.getClass()) {
    return false;
}
```

Khi cả lớp cha và lớp con đều tôn trọng chính sách đó, `Point` sẽ **không bằng** `ColoredPoint` dù trùng tọa độ. Nhờ vậy không có tình trạng lớp cha chấp nhận một lớp con mà lớp con từ chối lớp cha.

Nếu lớp cha dùng `getClass()` và lớp con ghi đè `equals()`, lớp con **vẫn có thể gọi `super.equals()`** để tái sử dụng so sánh tọa độ. Đối với hai đối tượng cùng lớp con, `getClass()` trong phương thức lớp cha vẫn là lớp runtime của hai đối tượng, nên kiểm tra cùng lớp có thể thành công.

### 5.1. Mẫu an toàn: chính sách cùng lớp, trạng thái bất biến

Tạo file **`SafeSuperEqualsDemo.java`**:

```java
import java.util.Objects;

class Coordinate {
    private final int x;
    private final int y;

    Coordinate(int x, int y) {
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
        Coordinate other = (Coordinate) obj;
        return x == other.x && y == other.y;
    }

    @Override
    public int hashCode() {
        return Objects.hash(x, y);
    }
}

final class ColorCoordinate extends Coordinate {
    private final String color;

    ColorCoordinate(int x, int y, String color) {
        super(x, y);
        this.color = Objects.requireNonNull(color);
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) {
            return true;
        }
        if (!super.equals(obj)) {
            return false;
        }
        ColorCoordinate other = (ColorCoordinate) obj;
        return color.equals(other.color);
    }

    @Override
    public int hashCode() {
        return 31 * super.hashCode() + color.hashCode();
    }
}

public class SafeSuperEqualsDemo {
    public static void main(String[] args) {
        Coordinate point = new Coordinate(2, 3);
        ColorCoordinate red =
                new ColorCoordinate(2, 3, "red");
        ColorCoordinate redCopy =
                new ColorCoordinate(2, 3, "red");
        ColorCoordinate blue =
                new ColorCoordinate(2, 3, "blue");

        System.out.println("point -> red: "
                + point.equals(red));
        System.out.println("red -> point: "
                + red.equals(point));
        System.out.println("red -> redCopy: "
                + red.equals(redCopy));
        System.out.println("red -> blue: "
                + red.equals(blue));
        System.out.println("equal hashes: "
                + (red.hashCode() == redCopy.hashCode()));
    }
}
```

Chạy:

```bash
javac SafeSuperEqualsDemo.java
java SafeSuperEqualsDemo
```

Kết quả:

```text
point -> red: false
red -> point: false
red -> redCopy: true
red -> blue: false
equal hashes: true
```

**Vì sao ví dụ này nhất quán?**

1. `Coordinate.equals()` so sánh `getClass()` trước, nên không chấp nhận đối tượng thuộc lớp khác. Lời gọi từ hai phía đều trả `false` giữa `Coordinate` và `ColorCoordinate`.
2. Với hai `ColorCoordinate`, `super.equals()` so tọa độ (và chính sách cùng lớp); sau đó `ColorCoordinate.equals()` so tiếp `color`.
3. `ColorCoordinate.hashCode()` kết hợp mã băm phần cha và `color`, phù hợp các thuộc tính mà `equals()` của lớp con xét.
4. Trường dữ liệu đều `final`; lớp `ColorCoordinate` cũng `final`, nên không có lớp con mới tiếp tục mở rộng cách so sánh của nó.

**Giới hạn:** chính sách `getClass()` định nghĩa *khác lớp runtime thì không bằng nhau*. Điều này có thể không phù hợp nếu ứng dụng chủ ý cần bình đẳng đa hình hoặc có proxy/subclass do framework tạo. Ngoài ra, `Coordinate` ở ví dụ vẫn cho phép được kế thừa; mỗi lớp con mới có trạng thái tham gia giá trị phải tiếp tục tôn trọng chính sách `equals()`/`hashCode()`. `super.equals()` không thể ép các lớp con tương lai tự làm điều đó.

## 6. Những cách tổ chức thiết kế khác

### 6.1. Ưu tiên bất biến, lớp `final`, `record` hoặc composition

Nếu lớp con chỉ khác về dữ liệu giá trị, thường dễ bảo toàn hợp đồng hơn khi **không dùng kế thừa để mở rộng danh tính giá trị**. Dùng hai record độc lập:

```java
record PointValue(int x, int y) {}

record ColoredPointValue(int x, int y, String color) {}
```

Java tự sinh `equals()` và `hashCode()` cho mỗi record dựa trên thành phần của **chính record đó**, với quy tắc so sánh theo loại record tương ứng. Hai `ColoredPointValue` có cùng `x`, `y`, `color` sẽ bằng nhau; `PointValue` và `ColoredPointValue` là hai kiểu độc lập.

Nếu cần tái sử dụng thông tin chung mà không muốn kế thừa quan hệ bằng nhau, dùng **composition**:

```java
record ColoredPointValue(PointValue point, String color) {}
```

Cách này làm rõ rằng màu sắc và tọa độ cùng góp phần xác định giá trị. Tuy nhiên, nếu nghiệp vụ coi màu chỉ là thông tin phụ và bình đẳng chỉ dựa trên tọa độ, cần chọn một định nghĩa khác có chủ ý; không nên máy móc so tất cả trường.

### 6.2. `final equals()` ở lớp cha

Nếu mọi lớp con **thật sự có chung một định nghĩa bằng nhau** (ví dụ tất cả chỉ được nhận dạng bằng một ID bất biến), lớp cha có thể quy định `equals()`/`hashCode()` là `final`, không cho lớp con thay đổi:

```java
@Override
public final boolean equals(Object obj) {
    // So sánh đúng theo một quy tắc chung đã chọn.
}
```

Điều này chỉ phù hợp nếu không lớp con nào cần bổ sung thuộc tính vào tính bằng nhau; nếu một lớp con cần phân biệt thêm màu, làm `equals()` của lớp cha thành `final` sẽ khiến màu không tham gia quan hệ bằng nhau. `final` ngăn ghi đè, **không tự chứng minh quy tắc trong lớp cha là đúng**.

### 6.3. Mẫu `canEqual` cho hệ phân cấp đa hình

Một số thiết kế dùng phương thức như `canEqual(Object)` để hai phía thỏa thuận có được phép bằng nhau hay không trước khi kiểm tra trường:

1. Lớp cha kiểm tra đối tượng kia là kiểu phù hợp, rồi yêu cầu `other.canEqual(this)` đồng ý.
2. Lớp con có thêm trạng thái thay đổi `canEqual()` để từ chối bằng nhau với lớp cha không mang trạng thái đó.
3. Lớp con kiểm tra thêm trường mới sau khi gọi `super.equals(other)`; mọi lớp trong hệ phân cấp phải triển khai cùng quy ước.

Mẫu này giúp xây dựng một số hệ phân cấp có thể mở rộng mà vẫn giữ đối xứng, nhưng khó bảo trì hơn: một lớp con bỏ qua quy ước có thể làm hỏng hợp đồng. Không có chuyện chỉ thêm một lệnh `canEqual()` là tự động bảo đảm mọi quan hệ bắc cầu hoặc chính sách hash. Khi không có yêu cầu kế thừa đa hình rõ ràng, composition/lớp bất biến thường dễ hiểu hơn.

## 7. Những điều `super.equals()` không tự bảo đảm

| Điều dễ ngộ nhận | Sự thật |
| --- | --- |
| “Lớp cha đã so đúng nên lớp con chắc chắn đúng.” | Lớp con có thể thêm trạng thái làm thay đổi quan hệ bằng nhau, gây bất đồng với lớp cha. |
| “Gọi `super.equals()` là đủ bảo đảm đối xứng.” | Chỉ kiểm tra một chiều; lớp cha có thể nhận lớp con trong khi lớp con không nhận lớp cha. |
| “Nếu đối xứng thì bắc cầu cũng đúng.” | Phiên bản so sánh linh hoạt theo kiểu ở ví dụ 4 vẫn có thể phá bắc cầu. |
| “Đã gọi `super.equals()` thì khỏi cần `hashCode()`.” | Nếu lớp con bổ sung trường vào tính bằng nhau, phải thiết kế hash nhất quán với định nghĩa cuối cùng. |
| “Có thêm `instanceof` trong lớp con là sửa được.” | Thường chỉ làm lớp con từ chối lớp cha, chưa xử lý cách lớp cha nhìn lớp con. |
| “Dùng `getClass()` luôn tốt hơn `instanceof`.” | Phù hợp với bình đẳng chính xác theo lớp, nhưng có thể bất tiện với proxy và ý nghĩa đa hình. |
| “Lớp cha `equals()` dùng tham chiếu thì lớp con tự so được dữ liệu.” | Nếu `super.equals()` cuối cùng là `Object.equals()`, hai đối tượng riêng biệt bị từ chối ngay cả khi trường giống nhau. |
| “Hai hash giống nhau chứng minh thiết kế equals đúng.” | Hash va chạm được phép; mã băm không chứng minh đối xứng hoặc bắc cầu. |

`super.equals()` cũng không tự động giải quyết so sánh null, tránh vòng lặp giữa các tham chiếu đối tượng, tính nhất quán khi dữ liệu thay đổi, hay những vấn đề khi lớp cha/lớp con thay đổi hợp đồng qua các phiên bản. Đây đều là trách nhiệm của mô hình giá trị và triển khai cụ thể.

## 8. Checklist khi review `equals()` có kế thừa

1. **Xác định lớp cha thực sự gọi triển khai nào:** `Object.equals()`, một `equals()` dựa trên `instanceof`, hay dựa trên `getClass()`? Các lớp trung gian có ghi đè không?
2. **Định nghĩa rõ bằng nhau:** cùng ID, cùng mọi thuộc tính giá trị, hay chỉ cùng loại cụ thể? Thuộc tính mới của lớp con có tham gia không?
3. **Thử hai chiều:** `parent.equals(child)` và `child.equals(parent)` phải giống nhau. Kiểm tra cả hai trường hợp tọa độ/ID giống và khác.
4. **Thử ba đối tượng:** một lớp cha và hai lớp con giống phần chung nhưng khác trường thêm vào; kiểm tra tính bắc cầu.
5. **Soát cặp hash:** nếu `equals()` của lớp con mở rộng điều kiện, `hashCode()` của lớp con phải bảo đảm hai đối tượng bằng nhau có cùng hash; không dựa vào sự trùng hash để chữa lỗi `equals()`.
6. **Kiểm tra `null`, chính đối tượng đó, nhiều lần gọi và trạng thái thay đổi.** Dùng các trường bất biến nếu đối tượng được đưa vào `HashSet` hoặc dùng làm khóa `HashMap`.
7. **Xem xét hệ quả lên collection:** khi `equals()` không đối xứng/bắc cầu, việc `HashSet.contains()`, `HashMap.get()` hoặc khử trùng theo khóa có thể trở nên khó dự đoán. `TreeSet`/`TreeMap` còn có hợp đồng thứ tự riêng qua `compareTo()`/`Comparator`.
8. **Quyết định chính sách kế thừa:** `final`/record/composition, `getClass()`, hoặc hợp đồng hợp tác như `canEqual`; đừng trộn các quy tắc không tương thích giữa các lớp.

**Kết luận kiến thức:** `super.equals(other)` là một lời gọi tái sử dụng phép so sánh phần cha. Để thiết kế `equals()` đúng trong kế thừa, phải xác định *cả hai đối tượng có cùng đồng ý về quan hệ bằng nhau hay không*, kiểm tra đối xứng và bắc cầu trên các tổ hợp lớp, đồng thời giữ `hashCode()` nhất quán. Nếu việc thêm trạng thái ở lớp con làm quy tắc bằng nhau khó diễn đạt, cân nhắc tách các giá trị thành kiểu bất biến hoặc dùng composition.
