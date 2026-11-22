# Mẫu `canEqual()` trong kế thừa: mục đích, điều kiện phối hợp và giới hạn

## 1. Vì sao cần `canEqual()` khi ghi đè `equals()`?

Trong Java, `Object.equals(Object)` phải tuân thủ các tính chất **phản xạ**, **đối xứng**, **bắc cầu**, **nhất quán**, và `x.equals(null)` luôn là `false` với `x` khác `null`. Khi hai đối tượng được xem là bằng nhau, chúng còn phải có cùng `hashCode()`.

Kế thừa làm việc xây dựng quan hệ bằng nhau khó hơn vì lớp cha và lớp con có thể **khác nhau về các trường quyết định danh tính logic**. Một lớp `Point` chỉ có tọa độ (`x`, `y`); lớp `ColoredPoint` kế thừa `Point` nhưng bổ sung `color`. Nếu lớp cha dùng `instanceof Point` để so sánh tọa độ, còn lớp con chỉ nhận `ColoredPoint` và kiểm tra thêm màu, cùng một cặp đối tượng có thể cho hai câu trả lời trái ngược:

| Phép so sánh | Kết quả theo cách triển khai sai | Nguyên nhân |
| --- | --- | --- |
| `point.equals(coloredPoint)` | `true` | Lớp cha nhìn thấy đối tượng con là một `Point` và chỉ xét tọa độ |
| `coloredPoint.equals(point)` | `false` | Lớp con từ chối đối tượng không phải `ColoredPoint` |

Đó là vi phạm **tính đối xứng**: với hai tham chiếu không null `a` và `b`, `a.equals(b)` phải bằng `b.equals(a)`. Chỉ sửa ở lớp con chưa đủ nếu phương thức `equals` của lớp cha vẫn tự ý chấp nhận đối tượng lớp con.

**`canEqual()` là một mẫu thiết kế bổ trợ**, do người lập trình tự định nghĩa, cho phép đối tượng bên phải trả lời câu hỏi: *“Tôi có chấp nhận được so sánh bằng nhau theo kiểu của đối tượng bên trái không?”* Đây **không phải** phương thức có sẵn của `java.lang.Object` và Java **không** tự sinh nó cho các lớp thường.

## 2. Cơ chế: hai đối tượng phải đồng thuận

Trong một phiên bản đơn giản của mẫu, lớp cha triển khai:

```java
protected boolean canEqual(Object other) {
    return other instanceof Point;
}

@Override
public boolean equals(Object other) {
    if (this == other) return true;
    if (!(other instanceof Point that)) return false;
    return that.canEqual(this) && x == that.x && y == that.y;
}
```

Đây là **đoạn minh họa nằm trong lớp `Point`**, giả sử lớp đã khai báo trường `x`, `y` và phương thức `canEqual` như trên; chưa phải một tệp Java độc lập.

Điểm then chốt là lời gọi **`that.canEqual(this)`**:

1. `this` là đối tượng đang được gọi `equals` (bên trái).
2. `that` là đối tượng bên phải đã được xác nhận là một `Point` hoặc lớp con.
3. Lời gọi `that.canEqual(this)` dùng **dynamic dispatch**: JVM chọn cách triển khai `canEqual` của **kiểu runtime của `that`**, không nhất thiết là cách triển khai tại `Point`.
4. Nếu `that` là `ColoredPoint`, nó có thể từ chối `this` chỉ thuộc `Point`. Lớp cha lúc này trả về `false` trước khi so sánh tọa độ.

Mẫu này cho phép một lớp con có thêm tiêu chí bằng nhau ngăn lớp cha xem nó là cùng giá trị với lớp cha. Đổi lại, **mọi lớp tham gia phải cùng tuân thủ quy ước**. Nếu lớp con bổ sung trạng thái vào `equals` nhưng không điều chỉnh `canEqual`, lớp cha vẫn có thể chấp nhận nó theo một chiều và làm hỏng đối xứng.

## 3. Chương trình Java 17+ hoàn chỉnh

Lưu mã sau vào **`CanEqualDemo.java`**. `Point` có tọa độ; `ColoredPoint` thêm màu sắc và ghi đè đồng bộ `canEqual`, `equals`, `hashCode`. Chương trình kiểm tra các cặp theo cả hai chiều.

```java
import java.util.Objects;

public class CanEqualDemo {
    static class Point {
        private final int x;
        private final int y;

        Point(int x, int y) {
            this.x = x;
            this.y = y;
        }

        protected boolean canEqual(Object other) {
            return other instanceof Point;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof Point that)) return false;
            return that.canEqual(this)
                    && x == that.x
                    && y == that.y;
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
        protected boolean canEqual(Object other) {
            return other instanceof ColoredPoint;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof ColoredPoint that)) return false;
            return that.canEqual(this)
                    && super.equals(that)
                    && color.equals(that.color);
        }

        @Override
        public int hashCode() {
            return 31 * super.hashCode() + color.hashCode();
        }
    }

    static void check(String label, Object a, Object b) {
        boolean forward = Objects.equals(a, b);
        boolean reverse = Objects.equals(b, a);

        System.out.printf("%s: forward=%s, reverse=%s%n",
                label, forward, reverse);

        if (forward != reverse) {
            throw new AssertionError("Broken symmetry: " + label);
        }
    }

    public static void main(String[] args) {
        Point base = new Point(2, 5);
        Point baseCopy = new Point(2, 5);
        ColoredPoint red = new ColoredPoint(2, 5, "red");
        ColoredPoint redCopy = new ColoredPoint(2, 5, "red");
        ColoredPoint blue = new ColoredPoint(2, 5, "blue");

        check("Point vs ColoredPoint", base, red);
        check("ColoredPoint copies", red, redCopy);
        check("Different colors", red, blue);
        check("Point copies", base, baseCopy);
        check("Point vs null", base, null);

        System.out.println("equal red objects share hash: "
                + (red.hashCode() == redCopy.hashCode()));
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

```bash
javac CanEqualDemo.java
java CanEqualDemo
```

Kết quả chuẩn:

```text
Point vs ColoredPoint: forward=false, reverse=false
ColoredPoint copies: forward=true, reverse=true
Different colors: forward=false, reverse=false
Point copies: forward=true, reverse=true
Point vs null: forward=false, reverse=false
equal red objects share hash: true
```

**Vì sao các dòng đó xuất hiện?**

- **`base.equals(red)`**: `red` thỏa `instanceof Point`, nhưng `red.canEqual(base)` gọi bản ghi đè tại `ColoredPoint`. Vì `base` không phải `ColoredPoint`, lời gọi trả `false`. Lớp cha từ chối so sánh chéo kiểu dù tọa độ trùng.
- **`red.equals(base)`**: điều kiện `base instanceof ColoredPoint` là `false`, nên lớp con cũng trả `false`. Hai chiều thống nhất.
- **`red.equals(redCopy)`**: cả hai đều là `ColoredPoint`; `that.canEqual(this)` chấp nhận, `super.equals(that)` xác nhận tọa độ, và `color.equals(that.color)` xác nhận màu giống nhau. Chiều đảo cũng `true`.
- **`red.equals(blue)`**: tọa độ giống nhưng màu khác, hai chiều đều `false`.
- **`base.equals(baseCopy)`**: cả hai đều là `Point` cùng tọa độ, hai chiều `true`.
- `Objects.equals(base, null)` và `Objects.equals(null, base)` đều `false`, giúp kiểm thử hướng đảo an toàn với `null`.
- Hai `ColoredPoint` bằng nhau phải cùng `hashCode`; ví dụ kiểm chứng điều đó. Hai đối tượng **không** bằng nhau vẫn được phép trùng hash.

Trong `ColoredPoint.equals`, điều kiện `that.canEqual(this)` thể hiện rõ sự đồng thuận của đối tượng bên phải. Lời gọi `super.equals(that)` còn kiểm tra `that.canEqual(this)` tại lớp cha, sau đó kiểm tra các tọa độ; ở ví dụ một cấp này, việc hỏi lại là thừa về mặt tính toán nhưng giúp lớp cha luôn tự duy trì hợp đồng của mình.

## 4. Những điều kiện cần phối hợp giữa lớp cha và lớp con

### 4.1. Lớp cha phải hỏi ý kiến đối tượng bên phải

`Point.equals` cần kiểm tra `other.canEqual(this)` **trước khi kết luận** bằng nhau theo các trường của lớp cha. Nếu lớp cha chỉ viết `other instanceof Point` rồi so sánh tọa độ, phương thức `canEqual` ở lớp con sẽ không được dùng và mẫu không giải quyết được tình huống ban đầu.

### 4.2. Lớp con có thêm trạng thái bình đẳng phải ghi đè `canEqual`

Nếu màu sắc tham gia quyết định `equals`, `ColoredPoint.canEqual` nên chấp nhận đúng nhóm đối tượng mà nó sẵn sàng so sánh theo định nghĩa ấy. Trong ví dụ, nó chỉ chấp nhận `ColoredPoint`.

Nếu lớp con chỉ thêm dữ liệu trình bày, **không** thêm trường tham gia vào định nghĩa bằng nhau, có thể không cần mở rộng quy tắc của lớp cha; tuy nhiên quyết định này phải được ghi nhận rõ trong mô hình. Không có nguyên tắc “mọi lớp con đều phải khác lớp cha” áp dụng cho mọi bài toán.

### 4.3. Lớp con phải phối hợp `equals` với phần bằng nhau được kế thừa

Lớp con cần kết hợp các phép kiểm tra: kiểu đối tượng phù hợp, đối tượng bên phải chấp nhận, phần dữ liệu của lớp cha bằng nhau (ví dụ `super.equals(that)`), và phần dữ liệu mới bằng nhau. Nếu bỏ `super.equals`, hai điểm khác tọa độ có thể bị coi là bằng nhau chỉ vì cùng màu.

Không đủ nếu chỉ ghi đè `canEqual`: **chính `equals` vẫn phải thực hiện đầy đủ so sánh thuộc tính**. Ngược lại, chỉ ghi đè `equals` mà không ghi đè `canEqual` trong lớp con có thêm trạng thái bình đẳng dễ tái tạo lỗi đối xứng.

### 4.4. `hashCode` phải theo cùng quan hệ bằng nhau

Khi `a.equals(b)` là `true` thì bắt buộc `a.hashCode() == b.hashCode()`. Trong ví dụ, `Point` dùng tọa độ, `ColoredPoint` kết hợp hash của phần cha với màu. Cả hai đối tượng `ColoredPoint` bằng nhau có hash bằng nhau.

Không suy luận chiều ngược: hai hash bằng nhau **không** kéo theo hai đối tượng bằng nhau. Nếu cho phép các kiểu khác nhau bằng nhau, cần bảo đảm cách tính hash của **mọi kiểu tương thích** thống nhất, không chỉ tính hash hợp lệ trong từng lớp.

### 4.5. Quy ước cần áp dụng xuyên suốt hệ phân cấp

Đối với hệ phân cấp nhiều tầng (`Point → ColoredPoint → LabeledColoredPoint`), mỗi tầng bổ sung thuộc tính tham gia bình đẳng phải cân nhắc cập nhật `canEqual`, `equals` và `hashCode`. Lớp ở tầng giữa cũng phải duy trì phép kiểm tra đồng thuận; nếu một lớp bỏ qua, bất đối xứng có thể trở lại.

Trong ví dụ, `ColoredPoint` được đánh dấu `final` để không phát sinh một tầng kế thừa mới tự ý thay đổi quy tắc. Đó là biện pháp thiết kế hữu ích, không phải điều kiện bắt buộc của mọi cách dùng `canEqual`.

## 5. `canEqual()` giải quyết được gì và **không** giải quyết được gì?

| Nội dung | Vai trò thực tế của `canEqual` |
| --- | --- |
| Đối xứng khi cha/con khác quy tắc giá trị | **Có thể hỗ trợ**: lớp con từ chối quan hệ với lớp cha; lớp cha tôn trọng quyết định đó |
| Phản xạ | Không tự bảo đảm; `equals` vẫn phải trả `true` khi cùng đối tượng |
| Bắc cầu | Không tự bảo đảm; nếu `a=b` và `b=c` thì thiết kế phải làm cho `a=c` |
| Nhất quán | Không tự bảo đảm nếu các trường tham gia so sánh thay đổi mà không có quy tắc rõ |
| So sánh với `null` | Không tự bảo đảm; `equals(null)` phải là `false` |
| Hợp đồng `hashCode` | Không tự bảo đảm; phải triển khai và kiểm tra riêng |
| Tính đúng đắn của mô hình miền | Không thay thế quyết định nghiệp vụ: đối tượng nào có thể đại diện cho cùng giá trị |

**Giới hạn lớn nhất:** `canEqual` là một *quy ước hợp tác*. Nó không có quyền ép mọi lớp con thực hiện đúng, không chứng minh được quan hệ bằng nhau là bắc cầu, và không ngăn mã khác ghi đè `equals` một cách không phù hợp. Nếu bên trái kết luận bằng nhau theo bộ trường A, bên phải dựa trên bộ trường B không tương thích, chỉ có một phương thức kiểm tra ý định không thể tự hòa giải hai định nghĩa.

**Đối tượng có thể thay đổi:** Nếu `x`, `y` hoặc `color` có thể bị sửa sau khi đưa đối tượng vào `HashSet` hay dùng làm khóa `HashMap`, giá trị hash có thể thay đổi và làm việc tìm kiếm sai mong đợi. Ví dụ dùng trường `final` nhằm loại trừ rủi ro này trong chính chương trình, nhưng thiết kế bất biến cũng cần áp dụng cho các đối tượng thành phần khi liên quan.

**Các kiểu lạ hoặc proxy:** Kiểm tra bằng `instanceof`, `getClass()` và `canEqual` biểu thị các chính sách tương thích kiểu khác nhau. Nếu framework tạo lớp con ở runtime, chính sách bằng nhau cần tính đến kiểu runtime và dữ liệu đại diện; không có một lựa chọn đúng cho mọi loại proxy hoặc entity.

## 6. So sánh với các phương án thiết kế khác

| Cách tiếp cận | Khi nào phù hợp | Đánh đổi |
| --- | --- | --- |
| `getClass() == other.getClass()` | Chỉ các đối tượng **cùng lớp runtime** mới có thể bằng nhau | Dễ hiểu, nhưng luôn bác bỏ bình đẳng giữa cha/con dù cùng tiêu chí |
| `instanceof` đơn thuần | Hệ phân cấp có định nghĩa bình đẳng thống nhất, lớp con không tự thêm trạng thái quyết định bình đẳng | Dễ bị vi phạm đối xứng/bắc cầu khi lớp con bổ sung tiêu chí |
| `instanceof` kết hợp `canEqual` | Cần cho phép từng kiểu kiểm soát khả năng bình đẳng xuyên hệ phân cấp | Linh hoạt hơn, nhưng mọi lớp liên quan phải hợp tác và kiểm thử cẩn thận |
| `final class` hoặc `record` | Đối tượng giá trị có danh tính logic rõ và không cần biến thể qua kế thừa | Ít rủi ro hợp đồng hơn; `record` tự sinh `equals`/`hashCode` theo thành phần |
| Composition | Kiểu mới **chứa** giá trị cũ và bổ sung thành phần như màu | Tách được các miền bình đẳng, tránh phải điều phối quan hệ cha–con |

Ví dụ, thay vì thiết kế `ColoredPoint extends Point`, có thể tạo hai `record` riêng:

```java
record PointValue(int x, int y) {}
record ColoredPointValue(PointValue point, String color) {}
```

Đây là **đoạn khai báo kiểu độc lập**, không phải toàn bộ chương trình chạy. Kiểu có màu chứa kiểu tọa độ và Java sinh phép so sánh theo thành phần. Một `PointValue` không bằng một `ColoredPointValue` theo mặc định ở cả hai chiều; trong trường hợp không cần bình đẳng xuyên kiểu, đó thường là thiết kế đơn giản hơn.

`canEqual` hữu ích khi kế thừa thật sự là yêu cầu của mô hình và không muốn áp dụng chính sách cứng “chỉ đúng cùng lớp”. Nó không phải một nghi thức buộc mọi lớp Java đều phải dùng.

## 7. Kiểm thử đầy đủ và các lỗi thường gặp

Khi có kế thừa, đừng chỉ viết assertion cho `a.equals(b)`. Kiểm tra **đảo chiều** và so sánh tất cả nhóm lớp có khả năng liên quan:

- Cùng tham chiếu; hai đối tượng khác tham chiếu nhưng cùng giá trị; cùng kiểu khác giá trị.
- Cha–con theo cả hai hướng; hai lớp con cùng kiểu; hai lớp con khác kiểu.
- `null` và đối tượng không liên quan; thứ tự gọi đảo.
- Ba đối tượng để kiểm tra tính **bắc cầu**; lặp phép so sánh khi không đổi trạng thái để kiểm tra **nhất quán**.
- Hai đối tượng được xác định bằng nhau phải có cùng `hashCode()`; thử dùng làm khóa trong `HashMap`/`HashSet` nếu đó là trường hợp sử dụng thật.

Những sai sót đáng chú ý:

1. **Quên `other.canEqual(this)` trong lớp cha:** lớp con có ghi đè `canEqual` vẫn không thể từ chối khi lớp cha chủ động so sánh.
2. **Lớp con thêm trường vào `equals` nhưng không ghi đè `canEqual`:** có thể khôi phục tình trạng lớp cha chấp nhận lớp con theo một chiều, lớp con từ chối lớp cha theo chiều kia.
3. **Không gọi `super.equals` khi cần so sánh trường kế thừa:** hai đối tượng có phần dữ liệu cha khác nhau vẫn có thể được đánh giá bằng nhau.
4. **Không đồng bộ `hashCode`:** các đối tượng bằng nhau có thể rơi vào những bucket khác nhau trong cấu trúc hash, vi phạm hợp đồng.
5. **Tưởng rằng `canEqual` tự kiểm tra mọi tính chất của `equals`:** nó chỉ hỗ trợ kiểm soát kiểu tương thích; cần kiểm thử cả bắc cầu, phản xạ và nhất quán.
6. **Viết `equals(Point)` thay vì `equals(Object)`:** đó là overload, không ghi đè đúng hợp đồng `Object.equals`. Dùng `@Override` giúp phát hiện nhầm chữ ký khi biên dịch.

**Bài tự kiểm tra:** Giả sử `Point.equals` chỉ so tọa độ và có gọi `other.canEqual(this)`, nhưng `ColoredPoint` ghi đè `equals` để so thêm màu mà **quên ghi đè `canEqual`**. Khi `point` và `coloredPoint` có cùng tọa độ, hãy tính hai chiều: `point.equals(coloredPoint)` có thể là `true` vì `ColoredPoint` kế thừa `Point.canEqual`; `coloredPoint.equals(point)` là `false` vì đối tượng cha không phải `ColoredPoint`. Đây là lý do **lớp cha và lớp con phải cùng phối hợp** thì mẫu mới giúp bảo toàn đối xứng.

Tóm lại, `canEqual()` là cách đưa quyền chấp nhận quan hệ bằng nhau về phía đối tượng được so sánh. Hãy dùng nó khi cần quản lý bình đẳng trong hệ phân cấp mở; bảo đảm mỗi tầng kết hợp `canEqual`, `equals` và `hashCode` nhất quán, rồi kiểm thử toàn bộ hợp đồng. Nếu không thật sự cần bình đẳng xuyên kiểu, các lớp giá trị `final`, `record` và composition thường giúp đơn giản hóa thiết kế.