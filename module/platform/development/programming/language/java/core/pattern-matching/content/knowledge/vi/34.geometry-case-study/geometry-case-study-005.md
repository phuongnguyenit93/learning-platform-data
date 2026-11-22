# Xử lý null shape trong case study hình học

**Chủ đề:** Java Core Pattern Matching — Case study hình học. Bài dùng **Java 21 trở lên** để thực hành sealed interface, record patterns và pattern matching for switch (JEP 440, JEP 441). Mục tiêu là xử lý **shape null** đúng ngữ nghĩa, đồng thời phân biệt nó với một hình không null nhưng chứa dữ liệu tọa độ không hợp lệ.

## 1. Bài toán: hình vắng mặt khác hình không hợp lệ

Giả sử hệ thống nhận các hình: **Circle** (hình tròn), **Rectangle** (hình chữ nhật) và **Segment** (đoạn thẳng). Ứng dụng có hai nhu cầu khác nhau:

- **Màn hình xem trước:** Nếu chưa có hình, hiển thị “NO SHAPE”. Nếu có đối tượng hình nhưng thiếu tọa độ, hiển thị lỗi dữ liệu phù hợp thay vì làm ứng dụng dừng.
- **Bộ tính toán nghiêm ngặt:** Chỉ chấp nhận hình có dữ liệu hợp lệ để tính diện tích; đầu vào null hoặc hình thiếu tọa độ phải bị từ chối bằng ngoại lệ rõ ràng.

Hai API có thể dùng **cùng một mô hình hình học**, nhưng không nhất thiết có cùng hợp đồng đối với null. Sai lầm phổ biến là cố gắng biến **mọi null thành diện tích 0**, vì **không có hình**, **hình có diện tích bằng 0** và **hình hỏng dữ liệu** là ba trạng thái khác nhau.

Hãy bắt đầu bằng việc phân loại rõ:

| Đầu vào | Ý nghĩa | Hướng xử lý hợp lý |
| --- | --- | --- |
| **shape == null** | Không có đối tượng hình | Hiển thị trạng thái trống hoặc từ chối tại API |
| **new Circle(null, 1)** | Có Circle nhưng thiếu tâm | Phát hiện dữ liệu thiếu; không giả định tâm (0, 0) |
| **new Rectangle(null, 2, 5)** | Có Rectangle nhưng thiếu gốc tọa độ | Báo lỗi gốc tọa độ |
| **new Segment(start, null)** | Có Segment nhưng thiếu một đầu mút | Báo lỗi điểm đầu/cuối |
| **new Circle(point, 0)** | Circle hợp lệ, bán kính 0 | Diện tích 0 là kết quả có ý nghĩa |
| **new Segment(p1, p2)** | Đoạn thẳng có hai điểm | Độ dài có thể dương, diện tích hình phẳng bằng 0 |

**Nguyên tắc:** Không dùng giá trị số 0 hoặc String rỗng làm biểu diễn chung cho tất cả trường hợp null nếu caller cần phân biệt các trạng thái này.

## 2. Mô hình dữ liệu: sealed Shape, Point và ba record

Một miền hình học tương đối đóng có thể diễn đạt bằng sealed interface:

~~~java
sealed interface Shape permits Circle, Rectangle, Segment {}

record Point(double x, double y) {}

record Circle(Point center, double radius) implements Shape {}

record Rectangle(Point origin, double width, double height) implements Shape {}

record Segment(Point start, Point end) implements Shape {}
~~~

**Đây là đoạn khai báo minh họa**, bản đầy đủ có constructor kiểm tra kích thước ở mục 6.

Vì **Circle**, **Rectangle** và **Segment** đều là record (ngầm final), mỗi kiểu là một biến thể cụ thể. Trình biên dịch có thể chứng minh một switch xử lý đủ các subtype của Shape mà không cần default.

Mỗi record có ý nghĩa hình học:

- **Circle:** tâm và bán kính, diện tích bằng π × r².
- **Rectangle:** gốc tọa độ, chiều rộng, chiều cao; diện tích bằng width × height.
- **Segment:** điểm đầu, điểm cuối; độ dài bằng căn bậc hai của tổng bình phương chênh lệch tọa độ.

**Record không tự cấm null** đối với component tham chiếu như **Point**. Vì vậy **new Circle(null, 1)** vẫn tạo được nếu constructor không kiểm tra center. Component nguyên thủy kiểu double thì không thể nhận null, nhưng vẫn có thể nhận **NaN** hoặc giá trị vô cực nếu không xác thực.

Một case study cần phân biệt hai câu hỏi:

1. Kiểu hình gì đang được xử lý? Đây là việc của **type/record pattern**.
2. Bản thân dữ liệu hình có hợp lệ để tính toán không? Đây là việc của **constructor validation**, **guard** hoặc **logic kiểm tra trong API**.

Đừng suy luận rằng pattern khớp đồng nghĩa dữ liệu miền hợp lệ.

## 3. Null selector trong instanceof và switch khác nhau

### 3.1. instanceof không match null

~~~java
Shape shape = null;
boolean isCircle = shape instanceof Circle;  // false
~~~

Nếu chuyển sang pattern variable:

~~~java
if (shape instanceof Circle circle) {
    System.out.println(circle.radius());
} else {
    System.out.println("not a circle");
}
~~~

Với shape null, nhánh **else** chạy. Không có Circle được ràng buộc và không có NullPointerException chỉ vì toán tử instanceof.

### 3.2. Pattern switch cần chính sách null tường minh

~~~java
static String category(Shape shape) {
    return switch (shape) {
        case null -> "NO SHAPE";
        case Circle c -> "CIRCLE";
        case Rectangle r -> "RECTANGLE";
        case Segment s -> "SEGMENT";
    };
}
~~~

Với **shape == null**, case null trả “NO SHAPE”. Các case còn lại sử dụng **type patterns** để phân loại đối tượng không null.

Nếu bỏ case null, switch expression có thể vẫn exhaustive theo ba subtype, nhưng khi nhận null, nó thông thường ném **NullPointerException**. Tính exhaustive theo kiểu **không đồng nghĩa** chấp nhận null.

**default không tự thay case null.** Nếu muốn nhóm null và những kiểu khác vào cùng một nhánh trên một selector mở, Java 21 có cú pháp **case null, default**. Tuy nhiên, trên sealed Shape đã biết đủ subtype, viết **case null** riêng rõ ràng và giúp tránh default che trường hợp subtype mới.

### 3.3. Không phải mọi “null” đều là selector

Xét ba giá trị:

~~~java
Shape missing = null;
Shape circleWithoutCenter = new Circle(null, 2);
Shape segmentWithoutEnd = new Segment(new Point(0, 0), null);
~~~

- **missing** là selector null.
- **circleWithoutCenter** là một đối tượng Circle không null.
- **segmentWithoutEnd** là một đối tượng Segment không null.

Khi xử lý từng giá trị, **case null** chỉ bắt trường hợp thứ nhất. Hai trường hợp còn lại cần xét record component hoặc invariant của từng kiểu.

## 4. Record pattern lồng nhau và giá trị null

Record pattern rất thuận tiện khi cần trích xuất tọa độ:

~~~java
case Circle(Point(double x, double y), double radius) ->
        "CIRCLE area=" + fmt(Math.PI * radius * radius);
~~~

Mẫu này yêu cầu:

1. Selector thực sự là một **Circle** không null.
2. Component **center** phải là đối tượng **Point** để có thể phân rã.
3. Hai component của Point là **double x** và **double y**.
4. Bán kính được ràng buộc vào **radius**.

Nếu **center == null**, mẫu lồng **Point(...)** không thể match. Nó **không** tự sử dụng tọa độ (0,0) và không được coi là một Circle hợp lệ chỉ vì selector khác null.

Vì thế, khi constructor Circle cho phép center null, cần nhánh dự phòng:

~~~java
case Circle(Point(double x, double y), double radius) ->
        "CIRCLE area=" + fmt(Math.PI * radius * radius);
case Circle(var center, var radius) -> "INVALID: circle center";
~~~

**case Circle(var center, var radius)** không đòi hỏi center phải khác null. Nó bao phủ những Circle còn lại, gồm Circle với center null. Nhánh dự phòng không đơn thuần “sửa lỗi trình biên dịch”: nó thể hiện **quyết định nghiệp vụ rằng dữ liệu hình thiếu tâm là không hợp lệ**.

Tương tự đối với Segment:

~~~java
case Segment(Point(double x1, double y1),
             Point(double x2, double y2)) ->
        "SEGMENT length=" + fmt(Math.hypot(x2 - x1, y2 - y1));
case Segment(var start, var end) ->
        "INVALID: segment endpoint";
~~~

Nếu start hoặc end null, mẫu hai Point không match; case Segment tổng quát sẽ trả thông báo lỗi. Trong Java, **Math.hypot(dx, dy)** là cách tính độ dài thường rõ ràng và ổn định số hơn việc tự tính **Math.sqrt(dx*dx + dy*dy)** ở những trị số có biên độ lớn.

**Lưu ý:** Null selector không phải nguyên nhân duy nhất khiến một record pattern không khớp. Khi đặt mẫu record lồng nhiều tầng, mỗi component tham chiếu cần được xét theo hợp đồng null riêng.

## 5. Hai chính sách API trên cùng một hierarchy

Với cùng kiểu Shape, hệ thống có thể cần hai phương thức.

### API khoan dung cho màn hình: describe(Shape)

~~~java
// Trích các nhánh tiêu biểu; hàm đầy đủ ở mục 6.
return switch (shape) {
    case null -> "NO SHAPE";
    case Circle(Point(var x, var y), var radius) ->
            "CIRCLE area=" + fmt(Math.PI * radius * radius);
    case Circle(var center, var radius) -> "INVALID: circle center";
    // Các nhánh Rectangle và Segment được khai báo đầy đủ ở ví dụ.
};
~~~

Đoạn trên **chỉ là trích dẫn minh họa, không phải switch exhaustive để chép chạy độc lập**. Ý định của API là **không ném ngoại lệ chỉ vì thiếu shape hoặc thiếu tọa độ**; thay vào đó nó tạo thông điệp có thể hiển thị. Tuy nhiên, constructor vẫn có thể ném ngoại lệ ngay từ lúc tạo shape nếu kích thước không hợp lệ.

### API nghiêm ngặt cho phép tính: areaStrict(Shape)

~~~java
static double areaStrict(Shape shape) {
    Objects.requireNonNull(shape, "shape");
    return switch (shape) {
        case Circle(Point(var x, var y), double r) -> Math.PI * r * r;
        case Circle(var center, var radius) ->
                throw new IllegalArgumentException("circle center");
        case Rectangle(Point(var x, var y), double w, double h) -> w * h;
        case Rectangle(var origin, var w, var h) ->
                throw new IllegalArgumentException("rectangle origin");
        case Segment(Point(var x1, var y1), Point(var x2, var y2)) -> 0.0;
        case Segment(var start, var end) ->
                throw new IllegalArgumentException("segment endpoint");
    };
}
~~~

Đây là code trích từ ví dụ đầy đủ, giả định đã import **java.util.Objects** và có các record Shape tương ứng.

Ở ranh giới hàm, **Objects.requireNonNull(shape, "shape")** từ chối selector null bằng **NullPointerException** trước switch. Các case còn lại chỉ xử lý subtype không null. Nếu thiếu điểm, nhánh của subtype đó ném **IllegalArgumentException**.

Vì cả ba subtype đều được bao phủ, switch expression không cần default. Các nhánh **throw** vẫn là kết thúc hợp lệ của một switch expression; không phải mọi nhánh đều phải trả về double nếu nhánh đó cố ý kết thúc bất thường.

**Quy ước quan trọng:** NullPointerException và IllegalArgumentException có ý nghĩa khác nhau ở API này. Dù không phải quy tắc duy nhất mọi tổ chức phải dùng, việc phân biệt chúng giúp tài liệu và caller nhận diện đúng điều kiện vi phạm.

## 6. Chương trình Java 21 hoàn chỉnh, chạy được

Chương trình bên dưới có cả **null selector**, **shape chứa Point null**, **record pattern lồng**, **diện tích**, **độ dài** và **constructor validation**.

Lưu toàn bộ vào file **NullShapeDemo.java**:

~~~java
import java.util.Locale;
import java.util.Objects;

public class NullShapeDemo {
    sealed interface Shape permits Circle, Rectangle, Segment {}

    record Point(double x, double y) {}

    record Circle(Point center, double radius) implements Shape {
        Circle {
            if (!Double.isFinite(radius) || radius < 0) {
                throw new IllegalArgumentException("radius");
            }
        }
    }

    record Rectangle(Point origin, double width, double height)
            implements Shape {
        Rectangle {
            if (!Double.isFinite(width) || !Double.isFinite(height)
                    || width < 0 || height < 0) {
                throw new IllegalArgumentException("size");
            }
        }
    }

    record Segment(Point start, Point end) implements Shape {}

    static String fmt(double value) {
        return String.format(Locale.ROOT, "%.2f", value);
    }

    /**
     * Trả mô tả để hiển thị; chấp nhận selector null.
     *
     * @param shape có thể null; null nghĩa là chưa có hình
     * @return mô tả không null; hình thiếu tọa độ được ghi INVALID
     */
    static String describe(Shape shape) {
        return switch (shape) {
            case null -> "NO SHAPE";

            case Circle(Point(double cx, double cy), double radius) ->
                    "CIRCLE area=" + fmt(Math.PI * radius * radius);
            case Circle(var center, var radius) ->
                    "INVALID: circle center";

            case Rectangle(Point(double ox, double oy),
                           double width, double height) ->
                    "RECTANGLE area=" + fmt(width * height);
            case Rectangle(var origin, var width, var height) ->
                    "INVALID: rectangle origin";

            case Segment(Point(double x1, double y1),
                         Point(double x2, double y2)) ->
                    "SEGMENT length="
                            + fmt(Math.hypot(x2 - x1, y2 - y1));
            case Segment(var start, var end) ->
                    "INVALID: segment endpoint";
        };
    }

    /**
     * Tính diện tích của một Shape có đủ tọa độ.
     *
     * @param shape bắt buộc khác null
     * @return diện tích; đoạn thẳng hợp lệ có diện tích 0
     * @throws NullPointerException nếu shape null
     * @throws IllegalArgumentException nếu shape thiếu
     *         tâm/gốc tọa độ/đầu mút cần thiết
     */
    static double areaStrict(Shape shape) {
        Objects.requireNonNull(shape, "shape");
        return switch (shape) {
            case Circle(Point(var x, var y), double radius) ->
                    Math.PI * radius * radius;
            case Circle(var center, var radius) ->
                    throw new IllegalArgumentException("circle center");

            case Rectangle(Point(var x, var y),
                           double width, double height) ->
                    width * height;
            case Rectangle(var origin, var width, var height) ->
                    throw new IllegalArgumentException("rectangle origin");

            case Segment(Point(var x1, var y1),
                         Point(var x2, var y2)) -> 0.0;
            case Segment(var start, var end) ->
                    throw new IllegalArgumentException("segment endpoint");
        };
    }

    public static void main(String[] args) {
        Shape[] samples = {
            null,
            new Circle(new Point(0, 0), 2),
            new Circle(null, 1),
            new Rectangle(new Point(1, 1), 3, 4),
            new Rectangle(null, 2, 5),
            new Segment(new Point(0, 0), new Point(3, 4)),
            new Segment(new Point(0, 0), null)
        };

        for (Shape shape : samples) {
            System.out.println(describe(shape));
        }

        System.out.println("AREA: " + fmt(areaStrict(
                new Circle(new Point(1, 2), 2))));

        try {
            areaStrict(null);
        } catch (NullPointerException ex) {
            System.out.println("REJECTED: " + ex.getMessage());
        }

        try {
            areaStrict(new Circle(null, 1));
        } catch (IllegalArgumentException ex) {
            System.out.println("REJECTED: " + ex.getMessage());
        }

        try {
            new Circle(new Point(0, 0), -1);
        } catch (IllegalArgumentException ex) {
            System.out.println("REJECTED: " + ex.getMessage());
        }
    }
}
~~~

### Biên dịch và chạy

Dùng JDK 21 hoặc mới hơn, tại thư mục chứa **NullShapeDemo.java**:

~~~bash
javac NullShapeDemo.java
java NullShapeDemo
~~~

**Đầu ra chính xác:**

~~~text
NO SHAPE
CIRCLE area=12.57
INVALID: circle center
RECTANGLE area=12.00
INVALID: rectangle origin
SEGMENT length=5.00
INVALID: segment endpoint
AREA: 12.57
REJECTED: shape
REJECTED: circle center
REJECTED: radius
~~~

**Giải thích kết quả:**

1. **null:** describe chọn case null và in NO SHAPE, thay vì để NullPointerException xảy ra.
2. **Circle((0,0), 2):** center là Point không null, mẫu lồng khớp; diện tích π × 2² xấp xỉ **12.57**.
3. **Circle(null, 1):** selector là Circle nhưng mẫu chứa Point không khớp; case Circle tổng quát trả INVALID: circle center.
4. **Rectangle((1,1), 3,4):** diện tích 3 × 4 = **12.00**.
5. **Rectangle(null, 2,5):** không có Point origin, nhánh dự phòng trả INVALID: rectangle origin.
6. **Segment((0,0),(3,4)):** chênh lệch hai trục 3 và 4, nên độ dài bằng **5.00**.
7. **Segment((0,0),null):** thiếu một đầu mút, nhánh dự phòng trả INVALID: segment endpoint.
8. **areaStrict** trên Circle hợp lệ trả diện tích và được in dạng hai chữ số thập phân.
9. **areaStrict(null):** Objects.requireNonNull từ chối bằng NullPointerException với thông điệp shape.
10. **areaStrict(Circle(null,1)):** thiếu tâm nên ném IllegalArgumentException với thông điệp circle center.
11. **Circle có bán kính -1:** compact constructor ném IllegalArgumentException ngay khi tạo đối tượng; phép tính areaStrict chưa được gọi.

Hàm **fmt** dùng **Locale.ROOT** để dấu phân cách thập phân trong đầu ra ví dụ là **dấu chấm**, độc lập với locale mặc định của máy chạy.

**Lưu ý về độ chính xác:** Java double là số thực dấu phẩy động; ví dụ in hai chữ số để dễ kiểm tra. Khi xây dựng ứng dụng hình học chính xác cao, cần quy định sai số, NaN, Infinity, độ lớn tọa độ và vấn đề tràn khi tính diện tích. Kiểm tra bán kính hữu hạn không tự bảo đảm π × radius² luôn hữu hạn nếu bán kính cực lớn.

## 7. Vì sao dùng nhánh tổng quát theo từng subtype?

Trong chương trình, hai case liên tiếp của Circle là:

~~~java
case Circle(Point(double cx, double cy), double radius) ->
        "CIRCLE area=" + fmt(Math.PI * radius * radius);
case Circle(var center, var radius) ->
        "INVALID: circle center";
~~~

**Nhánh đầu:** mô tả một Circle có center thực sự là Point.  
**Nhánh sau:** được thử nếu nhánh đầu không khớp, và bao phủ mọi Circle còn lại (ở đây là center null).

Nhánh thứ hai có vai trò **bảo toàn tính đầy đủ** của switch và **nêu rõ lỗi dữ liệu**. Cùng quy tắc áp dụng cho Rectangle và Segment.

Nếu chỉ viết một mẫu lồng Point cho từng subtype rồi không có nhánh dự phòng, trình biên dịch có thể xem switch expression là **chưa exhaustive**, vì những object record vẫn có thể chứa component null. Không nên giải quyết thiếu nhánh bằng một **default -> 0**: nó vừa có thể che lỗi dữ liệu, vừa làm nhánh xử lý subtype mới trong tương lai bị bỏ qua.

### Thứ tự các case

Đặt pattern **hẹp trước**, pattern **rộng sau**. Nếu đặt **case Circle(var center, var radius)** trước mẫu **Circle(Point(...), ...)**, mẫu rộng có thể che tất cả Circle và làm case sau bị dominated (không thể tới được).

Với switch có guard, cũng cần nhớ:

~~~java
case Circle(Point(var x, var y), double r) when r > 0 ->
        "positive circle";
case Circle(var center, var radius) -> "another circle";
~~~

Guard **r > 0** thu hẹp nhánh đầu; nhánh sau xử lý các trường hợp còn lại. Nếu guard ném exception thay vì trả false, ngoại lệ sẽ lan ra; switch không tự coi đó là không match.

## 8. Một lựa chọn khác: cấm Point null ngay trong constructor

Trong hệ thống domain hoàn chỉnh, Circle thiếu tâm hoặc Segment thiếu đầu mút thường **không phải trạng thái hợp lệ**. Có thể bảo vệ invariant ngay tại lúc tạo đối tượng:

~~~java
// Mô hình thay thế, không ghép cùng khai báo Circle của chương trình chính.
record StrictCircle(Point center, double radius) {
    StrictCircle {
        Objects.requireNonNull(center, "center");
        if (!Double.isFinite(radius) || radius < 0) {
            throw new IllegalArgumentException("radius");
        }
    }
}
~~~

Nếu dùng model như trên, **new StrictCircle(null, 1)** bị từ chối ở constructor, nên code xử lý StrictCircle được tạo hợp lệ không cần cùng mức phòng thủ cho center null. Tuy nhiên, **selector của API nhận StrictCircle** vẫn có thể là null; phải quy định hợp đồng riêng.

Đối với Segment:

~~~java
// Mô hình thay thế, yêu cầu có đủ hai đầu mút.
record StrictSegment(Point start, Point end) {
    StrictSegment {
        Objects.requireNonNull(start, "start");
        Objects.requireNonNull(end, "end");
    }
}
~~~

Khi dữ liệu đến từ JSON, cơ sở dữ liệu hoặc API bên ngoài, có thể dùng một kiểu **raw input** cho phép trường thiếu, sau đó chuyển sang **validated domain shape** với constructor bảo vệ invariant. Nhờ thế các thuật toán hình học không phải kiểm tra cùng một điều kiện null tại nhiều điểm.

**Không phải cứ dùng record là dữ liệu tự hợp lệ.** Compact constructor là lựa chọn bảo vệ invariant, nhưng cần xét thêm tọa độ NaN/Infinity, giới hạn độ lớn, chiều rộng, chiều cao và các quy tắc miền đặc thù.

## 9. Chọn giữa case null, kiểm tra sớm và kiểu biểu diễn “không có hình”

Có ba cách thiết kế khác nhau, không nên trộn lẫn:

| Chính sách | Cách viết | Ưu điểm và trách nhiệm |
| --- | --- | --- |
| **Hiển thị trạng thái vắng mặt** | **case null -> "NO SHAPE"** | Thuận tiện cho UI, caller biết rõ chuỗi kết quả |
| **Từ chối đầu vào thiếu** | **Objects.requireNonNull(shape, "shape")** | Fail fast ở ranh giới tính toán; Javadoc cần @throws |
| **Biểu diễn vắng mặt bằng kiểu riêng** | **Optional<Shape>**, hoặc subtype NoShape có ý nghĩa domain | Tránh dùng null làm sentinel tùy tiện; cần mô tả ý nghĩa kết quả |

Nếu ứng dụng sử dụng Optional, **Optional.empty()** biểu diễn không có hình, còn **Optional.of(shape)** yêu cầu shape khác null. **Optional.ofNullable(shape)** chuyển null thành Optional.empty(). Tuy nhiên, việc chuyển giữa nullable Shape và Optional không giải quyết tự động component null bên trong Circle hoặc Segment; constructor hay validation vẫn cần thiết.

Nếu dùng một subtype domain như **NoShape**, phải xác định nó có thật sự là một **loại Shape hợp lý** không. Thêm NoShape vào sealed hierarchy làm các switch exhaustive hiện có phải xem lại trường hợp mới khi biên dịch lại. Không nên thêm một subtype chỉ để né việc mô tả null mà không có ý nghĩa domain.

### Quyết định ở đâu?

- **UI/presentation boundary:** có thể chọn NO SHAPE cho đối tượng chưa được chọn.
- **Domain calculation:** có thể từ chối selector null và hình thiếu dữ liệu.
- **Importer/parser:** có thể trả validation result thay vì tạo Shape không hợp lệ.
- **Persistence/API transport:** cần phân biệt trường không tồn tại, trường JSON null và object hình có trường con null theo hợp đồng dữ liệu.

Không phải mọi ranh giới đều dùng cùng một giá trị fallback; thiết kế nhất quán là **mỗi API công bố rõ chính sách của mình**.

## 10. Javadoc cho null shape

Khi một phương thức public nhận Shape, không chỉ viết “handles null”. Hãy mô tả **khi nào null hợp lệ và hậu quả cụ thể**.

Ví dụ cách tài liệu hóa hai API của chương trình:

~~~java
/**
 * Trả mô tả để hiển thị, chấp nhận Shape null.
 *
 * @param shape có thể null; null nghĩa là chưa có hình
 * @return String không null; null cho "NO SHAPE",
 *         hình thiếu Point cho thông điệp bắt đầu bằng "INVALID:"
 */
static String describe(Shape shape) { /* body ở mục 6 */ }

/**
 * Tính diện tích cho Shape không null và đủ điểm cần thiết.
 *
 * @param shape không được null
 * @return diện tích dưới dạng double; Segment hợp lệ trả 0.0
 * @throws NullPointerException nếu shape null
 * @throws IllegalArgumentException nếu hình thiếu Point cần thiết
 */
static double areaStrict(Shape shape) { /* body ở mục 6 */ }
~~~

Đây là **Javadoc minh họa**, không phải phương thức độc lập để sao chép nguyên vào Java. Nếu muốn khai báo code hợp lệ, dùng implementation đầy đủ ở mục 6.

Cần lưu ý:

1. **@param:** selector nullable hay nonnull.
2. **@return:** giá trị trả về khi null và khi đối tượng hình thiếu component.
3. **@throws:** loại exception và điều kiện ném; không nhầm với ngoại lệ từ constructor hình xảy ra **trước khi gọi API**.
4. **Tên kết quả:** NO SHAPE, INVALID, 0.0 có ý nghĩa khác nhau; nếu thay đổi chính sách, cập nhật tài liệu và test.

Nếu dự án dùng annotation như **@Nullable** hoặc **@NonNull**, hãy dùng hệ annotation phù hợp toolchain của dự án; Java SE không có một annotation @Nullable trong java.lang được mọi trình phân tích hiểu thống nhất. Annotation không tự sinh ra nhánh case null hoặc kiểm tra runtime.

## 11. Ma trận kiểm thử cần có

Bảng sau dựa trên hai API của ví dụ:

| Đầu vào | describe | areaStrict |
| --- | --- | --- |
| **null** | NO SHAPE | NPE: shape |
| **Circle(Point(0,0),2)** | CIRCLE area=12.57 | Diện tích gần 12.56637 |
| **Circle(null,1)** | INVALID: circle center | IAE: circle center |
| **Rectangle(Point(1,1),3,4)** | RECTANGLE area=12.00 | 12.0 |
| **Rectangle(null,2,5)** | INVALID: rectangle origin | IAE: rectangle origin |
| **Segment(Point(0,0),Point(3,4))** | SEGMENT length=5.00 | 0.0 |
| **Segment(Point(0,0),null)** | INVALID: segment endpoint | IAE: segment endpoint |
| **Circle(Point(0,0),0)** | CIRCLE area=0.00 | 0.0 |
| **Circle(Point(0,0),-1)** | Constructor từ chối | Không có đối tượng hợp lệ để truyền |

Trong bảng, **NPE** = NullPointerException và **IAE** = IllegalArgumentException.

Một bộ test nên khẳng định **kết quả hoặc loại ngoại lệ**, không chỉ chạy method mà không assert. Với double, so sánh kết quả có sai số thích hợp thay vì so bằng một chuỗi định dạng trong toàn bộ domain logic.

### Test bổ sung không cần framework

Đoạn sau đặt **trong class NullShapeDemo** để có thể truy cập các kiểu lồng và phương thức static:

~~~java
// Mã bổ sung minh họa, không chép nguyên ngoài class.
if (!"NO SHAPE".equals(describe(null))) {
    throw new AssertionError("null selector");
}
if (!"INVALID: circle center".equals(describe(new Circle(null, 1)))) {
    throw new AssertionError("null component");
}
if (Math.abs(areaStrict(new Rectangle(new Point(0, 0), 3, 4)) - 12)
        > 1.0e-9) {
    throw new AssertionError("rectangle area");
}
try {
    areaStrict(null);
    throw new AssertionError("expected exception");
} catch (NullPointerException expected) {
    // API từ chối null theo hợp đồng.
}
~~~

Nếu dùng JUnit, có thể thay bằng **assertEquals**, **assertThrows**, và kiểm tra sai số số thực theo phiên bản framework. Nên test bổ sung **nested null**, **bán kính/chiều rộng bằng 0**, **kích thước âm**, **NaN/Infinity** và **tọa độ rất lớn** nếu ứng dụng cho phép.

## 12. Tái cấu trúc if-else cũ: giữ nguyên null behavior

Một đoạn cũ thường có dạng:

~~~java
static String oldTypeName(Shape shape) {
    if (shape instanceof Circle) return "circle";
    if (shape instanceof Rectangle) return "rectangle";
    if (shape instanceof Segment) return "segment";
    return "missing";
}
~~~

**oldTypeName(null)** trả “missing”. Khi đổi sang switch:

~~~java
static String newTypeName(Shape shape) {
    return switch (shape) {
        case Circle c -> "circle";
        case Rectangle r -> "rectangle";
        case Segment s -> "segment";
        case null -> "missing";
    };
}
~~~

Đây là cách bảo toàn null behavior. Nếu bỏ case null, bạn có thể làm thay đổi đường đi runtime thành NullPointerException, dù switch vẫn exhaustive theo subtype.

Với **record pattern lồng**, còn phải kiểm tra **component null** đã được code cũ xử lý thế nào. Ví dụ code cũ đọc **circle.center()** mà không kiểm tra null thì có thể từng ném NPE ở thời điểm khác; chuyển sang case dự phòng trả INVALID là **thay đổi hành vi có chủ đích**, cần được test và ghi nhận, không được ngụy trang thành refactor cú pháp thuần túy.

Nguyên tắc khi chuyển đổi:

1. Ghi lại đầu vào null và giá trị/exception cũ.
2. Viết test cho selector null, center/origin/endpoint null.
3. Chuyển logic bằng type/record patterns.
4. Đặt nhánh null và fallback đúng hợp đồng.
5. Kiểm tra khả năng exhaustive và không có case bị dominated.
6. Xác nhận kết quả, thứ tự side effect và loại exception không đổi, trừ phần thay đổi nghiệp vụ đã được phê duyệt.

## 13. Những sai lầm thường gặp

**Sai 1 — Tưởng default bắt null.** Trong pattern switch Java 21, default thông thường không thay thế case null; cần kiểm tra chính sách selector null rõ ràng.

**Sai 2 — Tưởng record pattern bảo đảm mọi component khác null.** Một case như Circle(var center, var radius) có thể nhận center null; không được lập tức gọi center.x() nếu chưa có invariant hoặc kiểm tra.

**Sai 3 — Chỉ viết pattern Point lồng mà quên fallback.** Có thể bỏ sót Circle(null,1), Rectangle(null,...) hoặc Segment có endpoint null. Compiler có thể chỉ ra switch expression không exhaustive.

**Sai 4 — Dùng 0 làm fallback cho mọi lỗi.** Shape null, Circle(radius=0), Segment có diện tích 0 và hình hỏng dữ liệu là các trường hợp khác nghĩa; gộp có thể làm mất tín hiệu lỗi.

**Sai 5 — Chỉ kiểm tra radius nhưng quên Point.** Constructor có thể từ chối bán kính âm mà vẫn cho phép center null. Khi đó phép tính diện tích từ radius tuy trả số nhưng chưa chứng minh hình có vị trí hợp lệ.

**Sai 6 — Dùng String.format mà không cố định locale trong ví dụ.** Máy dùng locale có dấu phẩy thập phân có thể làm output ví dụ khác. Dùng Locale.ROOT hoặc ghi rõ locale là cách kiểm thử ổn định.

**Sai 7 — Catch mọi NullPointerException và coi là “không có hình”.** NPE cũng có thể đến từ bug trong case body hoặc accessor. Bắt rộng sẽ che nguồn lỗi; xử lý tại ranh giới biết nguyên nhân.

**Sai 8 — Không ghi hợp đồng ở API boundary.** Người gọi không biết null được chấp nhận hay bị từ chối. Sửa implementation mà quên Javadoc/test làm mất tính tương thích ngầm.

**Sai 9 — Nhầm tính exhaustive với tính hợp lệ hình học.** Compiler bảo đảm có nhánh theo kiểu/pattern, không chứng minh bán kính hữu hạn, tọa độ hợp lệ hoặc thuật toán đo diện tích không overflow.

## 14. Checklist thiết kế shape API

- [ ] Đã phân biệt **shape null** với **hình tồn tại nhưng có component null**?
- [ ] API cần hiển thị trạng thái trống hay phải từ chối dữ liệu không hợp lệ?
- [ ] Circle.center, Rectangle.origin, Segment.start/end có invariant nonnull hay policy fallback rõ?
- [ ] Có case null (nếu chấp nhận) hoặc Objects.requireNonNull (nếu từ chối)?
- [ ] Record patterns lồng có case dự phòng cho component null?
- [ ] Case hẹp đứng trước case rộng để tránh dominance?
- [ ] Switch exhaustive theo sealed Shape mà không che subtype mới bằng default không cần thiết?
- [ ] Diện tích bằng 0 được phân biệt với không có shape và lỗi dữ liệu?
- [ ] Constructor xác thực radius, width/height; tọa độ và độ chính xác số thực đã được cân nhắc?
- [ ] @param, @return, @throws ghi đúng hành vi null?
- [ ] Có test selector null, component null, zero dimensions, invalid dimensions và subtype mới?

**Kết luận:** Với case study hình học, **null shape là quyết định của API**, không phải chỉ là một nhãn case. Java 21 giúp diễn đạt rõ thông qua **case null**, sealed hierarchy và record patterns lồng. Khi shape không null nhưng Point bên trong null, cần invariant hoặc nhánh dự phòng theo từng subtype. Chọn chính sách **hiển thị trạng thái thiếu** hay **từ chối bằng ngoại lệ** dựa trên ngữ nghĩa ứng dụng, ghi rõ bằng Javadoc và kiểm chứng bằng test; không biến mọi trường hợp thiếu dữ liệu thành diện tích 0.