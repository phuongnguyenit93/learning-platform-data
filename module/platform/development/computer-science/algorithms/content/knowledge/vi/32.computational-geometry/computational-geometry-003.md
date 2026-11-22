# Kiểm tra thẳng hàng, nằm giữa và trên đoạn

## 1. Bài toán và ba khái niệm cần phân biệt

Trong **hình học tính toán**, cần phân biệt rõ ba câu hỏi về điểm A, B, P trên mặt phẳng:

1. **Thẳng hàng:** A, B, P có cùng thuộc một đường thẳng không?
2. **Nằm giữa:** P có ở giữa A và B dọc theo đường thẳng đó không?
3. **Nằm trên đoạn:** P có thuộc đoạn hữu hạn AB, bao gồm hoặc không bao gồm hai đầu mút không?

Ví dụ:

~~~text
A=(1,1)     B=(5,5)     P=(3,3)
Q=(7,7)     R=(3,4)

Tren duong thang cheo co A,B:
A ------- P ------- B ------- Q

R nam lech khoi duong thang.
~~~

- P thẳng hàng và nằm **nghiêm ngặt giữa** A,B.
- Q thẳng hàng nhưng **nằm ngoài** đoạn AB.
- R không thẳng hàng.
- A,B thuộc **đoạn đóng [A,B]**, nhưng không thuộc **phần trong (A,B)**.
- Nếu A=B, đoạn suy biến chỉ chứa một điểm A và phần trong đoạn là rỗng.

Đây không phải các câu hỏi tương đương. Kiểm tra **thẳng hàng** là điều kiện cần để nằm trên đoạn AB, nhưng **không đủ**.

Bài sử dụng hệ tọa độ Descartes với trục x tăng sang phải, trục y tăng lên trên. Các ví dụ chính dùng tọa độ nguyên `long` và số học `BigInteger` chính xác nhằm tránh tràn khi tính định thức.

### Quy ước

- Đoạn đóng [A,B] gồm cả hai đầu mút.
- Đoạn mở (A,B) loại hai đầu mút; nếu A=B, là tập rỗng.
- Đường thẳng AB là vô hạn, nhưng chỉ xác định duy nhất nếu A≠B.
- Tia A→B là tập A+t(B−A) với t≥0 và A≠B.
- Điểm P được xem là nằm giữa theo nghĩa **strict** khi P thuộc đoạn đóng và P khác A,B.

Trong đề thi lập trình, phải đọc rõ từ ngữ “thuộc đoạn”, “nằm giữa”, “strictly between” và “including endpoints” để chọn predicate đúng.

## 2. Vectơ và tích có hướng trong mặt phẳng

Đặt:

~~~text
A=(ax,ay), B=(bx,by), P=(px,py)
u = B-A = (bx-ax, by-ay)
v = P-A = (px-ax, py-ay)
~~~

**Tích có hướng trong 2D** là số vô hướng:

~~~text
cross(u,v) = u.x*v.y - u.y*v.x

orient(A,B,P)
    = (bx-ax)*(py-ay) - (by-ay)*(px-ax)
~~~

Dấu của định thức cho biết vị trí P so với **đường thẳng có hướng A→B**:

| Dấu orient | Ý nghĩa trong hệ trục y tăng lên |
| --- | --- |
| Dương (>0) | P ở phía trái AB (hướng quay ngược chiều kim đồng hồ) |
| Âm (<0) | P ở phía phải AB (hướng quay theo chiều kim đồng hồ) |
| Bằng 0 | Hai vectơ AB,AP phụ thuộc tuyến tính; ba điểm thẳng hàng theo phép kiểm đại số |

Ví dụ:

~~~text
A=(1,1), B=(5,5), P=(3,3)
B-A=(4,4), P-A=(2,2)
cross=4*2-4*2=0
~~~

Với R=(3,4), ta có:

~~~text
R-A=(2,3)
cross(A,B,R)=4*3-4*2=4>0
~~~

Vậy R ở phía trái hướng A→B.

**Cẩn thận với hệ tọa độ màn hình:** nhiều ứng dụng vẽ trục y hướng xuống. Giá trị định thức không đổi theo công thức tọa độ đã nhập, nhưng cách nhìn “trái/phải” trên màn hình có thể ngược với hệ Descartes.

### Vì sao không dùng hệ số góc?

So hai hệ số góc thường phải chia `(by-ay)/(bx-ax)`, gặp vấn đề khi bx=ax (đường thẳng đứng) và sai số số thực. Định thức không cần chia, căn bậc hai hay lượng giác; trên tọa độ nguyên, phép kiểm có thể chính xác tuyệt đối nếu dùng kiểu số đủ rộng.

## 3. Thẳng hàng: điều kiện cần và đủ khi A≠B

Nếu A và B phân biệt, chúng xác định một đường thẳng duy nhất. Khi đó:

~~~text
P thuoc duong thang vo han AB
<=> orient(A,B,P) == 0
~~~

**Chứng minh:** P trên đường thẳng AB khi tồn tại một số thực t sao cho `P=A+t(B−A)`. Khi ấy AP=t·AB, nên `cross(AB,AP)=t·cross(AB,AB)=0`.

Ngược lại, AB là vectơ khác 0 và `cross(AB,AP)=0` làm AB,AP phụ thuộc tuyến tính, tức AP=t·AB; P nằm trên đường thẳng đi qua A và B.

### Đoạn suy biến A=B

Nếu A=B, AB=(0,0) nên:

~~~text
cross(A,A,P)=0 voi moi P
~~~

Đây là lý do một hàm chỉ kiểm `cross==0` không thể tự khẳng định P nằm trên **đường thẳng duy nhất qua A,B** khi A=B: hai đầu mút trùng nhau không xác định đường thẳng duy nhất.

Một API có thể quy ước `areCollinearByCross` trả true theo định nghĩa đại số dù A=B, nhưng hàm “P thuộc đường thẳng qua A,B” nên yêu cầu A≠B hoặc xử lý suy biến rõ ràng. Còn **đoạn đóng AA** là tập chỉ chứa A, nên membership đòi P==A.

## 4. Điểm thẳng hàng vẫn có thể nằm ngoài đoạn

Với A=(1,1), B=(5,5):

~~~text
P=(3,3)  -> orient=0, on segment
Q=(7,7)  -> orient=0, outside segment
T=(-1,-1)-> orient=0, outside segment
R=(3,4)  -> orient=4, off line
~~~

Định nghĩa toán học của đoạn đóng:

~~~text
[A,B] = { A+t*(B-A) | 0<=t<=1 }
~~~

Định nghĩa phần trong:

~~~text
(A,B) = { A+t*(B-A) | 0<t<1 }, A!=B
~~~

Đường thẳng vô hạn cho phép **mọi** t∈R. Điểm Q có t=1,5, nằm sau B; T có t=−0,5, nằm trước A. Vì thế điều kiện “thẳng hàng” cần thêm **ràng buộc giới hạn t**.

Hai kỹ thuật thực hành phổ biến tương đương nhau: giới hạn theo tọa độ (**bounding box**) và giới hạn theo **hình chiếu/tích vô hướng**.

## 5. Kiểm đoạn đóng bằng cross + bounding box

Điều kiện **cần và đủ** để P thuộc đoạn đóng AB là:

~~~text
orient(A,B,P)==0

AND

min(ax,bx) <= px <= max(ax,bx)

AND

min(ay,by) <= py <= max(ay,by)
~~~

Ví dụ P=(3,3) nằm trong [A=(1,1),B=(5,5)] vì cross=0, x nằm trong [1,5], y nằm trong [1,5]. Nhưng Q=(7,7) cross=0 mà x,y ngoài [1,5], nên bị loại.

### Vì sao phải kiểm cả x và y?

Xét đoạn đứng:

~~~text
A=(2,-2), B=(2,4), P=(2,1)
~~~

P thẳng hàng và có x=2, y trong [−2,4], nên thuộc đoạn. Tuy nhiên điểm (2,100) có cùng x và thẳng hàng nhưng nằm **ngoài** đoạn; điểm (3,1) có y nằm trong khoảng nhưng không thẳng hàng.

Công thức kiểm cả cross lẫn hai khoảng giúp xử lý mọi hướng, kể cả đoạn đứng, ngang hoặc chéo.

### Không phụ thuộc thứ tự đầu mút

[A,B] là cùng đoạn với [B,A]. Dùng `min/max` làm điều kiện đúng cả khi ax>bx hoặc ay>by. Đừng mặc định A ở trái/dưới B.

### Khi A=B

Bounding box thu về một tọa độ duy nhất (ax,ay). Cross bằng 0 với mọi P, nhưng hai khoảng buộc P=A. Vì thế công thức cũng xử lý **đúng đoạn suy biến** theo quy ước bài.

## 6. Kiểm đoạn bằng tích vô hướng và hình chiếu

Đặt u=B−A, v=P−A. **Tích vô hướng** là:

~~~text
dot(u,v)=u.x*v.x+u.y*v.y
lengthSquared(u)=dot(u,u)
~~~

Khi A≠B và P thẳng hàng, P=A+t(B−A) với:

~~~text
t = dot(P-A,B-A) / dot(B-A,B-A)
~~~

Vì mẫu là bình phương độ dài AB, nó dương khi A≠B. Vậy membership đoạn đóng tương đương:

~~~text
orient(A,B,P)==0
AND 0 <= dot(P-A,B-A) <= ||B-A||^2
~~~

Với phần trong đoạn, thay hai dấu ≤ bằng <, đồng thời yêu cầu A≠B.

**Không được bỏ điều kiện thẳng hàng.** Một điểm lệch khỏi đường thẳng có thể có hình chiếu nằm trong [A,B], tức dot nằm trong khoảng hợp lệ, nhưng chính P vẫn không nằm trên đoạn.

### Ví dụ số học

Với A=(1,1), B=(5,5), ta có:

~~~text
AB=(4,4)
lengthSquared = 4*4+4*4=32

P=(3,3), AP=(2,2)
dot(AP,AB)=2*4+2*4=16
0 < 16 < 32 -> BETWEEN

Q=(7,7), AQ=(6,6)
dot(AQ,AB)=6*4+6*4=48 > 32 -> AFTER_B

T=(-1,-1), AT=(-2,-2)
dot(AT,AB)=-2*4-2*4=-16 < 0 -> BEFORE_A
~~~

### Cách kiểm dot khác

Nếu P thẳng hàng với A,B và A≠B:

~~~text
(P-A) dot (P-B) <= 0   <=> P thuoc doan dong
(P-A) dot (P-B) <  0   <=> P thuoc phan trong doan
~~~

Vì `P=A+t(B−A)`, tích này là `t(t−1)||B−A||²`, không dương đúng khi t∈[0,1].

## 7. Phân loại vị trí theo đoạn có hướng

Nếu A≠B, ta có thể phân loại chính xác P theo hai bước:

1. Nếu cross khác 0: `OFF_LINE`.
2. Nếu cross=0, tính `along=dot(P-A,B-A)` và `len2=||B-A||²`.

~~~text
along < 0        -> BEFORE_A
along = 0        -> AT_A
0 < along < len2 -> BETWEEN
along = len2     -> AT_B
along > len2     -> AFTER_B
~~~

Cần kiểm cross trước vì một điểm không thẳng hàng vẫn có thể có along nằm trong khoảng. Với A=B, thay vì chia cho len2=0, bài dùng hai trạng thái:

~~~text
DEGENERATE_POINT: P=A=B
DEGENERATE_OTHER: P khac A=B
~~~

### Đoạn đóng và đoạn mở

~~~text
onClosedSegment(A,B,P):
    cross==0 AND boundingBoxContains(P)

onOpenSegment(A,B,P):
    A!=B
    AND onClosedSegment(A,B,P)
    AND P!=A AND P!=B
~~~

| P với A=(1,1),B=(5,5) | Cross | Đoạn đóng | Đoạn mở | Phân loại |
| --- | ---: | --- | --- | --- |
| (3,3) | 0 | true | true | BETWEEN |
| (1,1) | 0 | true | false | AT_A |
| (5,5) | 0 | true | false | AT_B |
| (7,7) | 0 | false | false | AFTER_B |
| (−1,−1) | 0 | false | false | BEFORE_A |
| (3,4) | 4 | false | false | OFF_LINE |

Nếu đảo A,B, các giá trị membership không thay đổi, nhưng “trước A” và “sau B” mang ý nghĩa theo hướng mới.

## 8. Các ca biên cần phân biệt

### Đoạn ngang, đứng và chéo

Đoạn ngang có ay=by; đoạn đứng có ax=bx. Cả hai đều dùng được cross+bounding box, không cần công thức hệ số góc.

### Đoạn suy biến

~~~text
A=B=(9,-4)
P=(9,-4): closed=true, strict=false
Q=(9,-3): closed=false, strict=false
~~~

Dù cross(A,A,Q)=0, bounding box loại Q. Nếu đề yêu cầu đoạn có độ dài dương, có thể từ chối A=B; còn ví dụ Java xem đoạn suy biến như tập {A}.

### Điểm nằm trên phần kéo dài

P có cross=0 nhưng có along<0 hoặc along>len². Đây là trường hợp thường xuyên gây sai nếu chỉ dựa vào định thức.

### Đầu mút

P=A hoặc P=B thuộc đoạn đóng, không thuộc phần trong. So điểm bằng nhau bằng **cả x và y**, không phải chỉ x.

### Tọa độ âm, thứ tự đầu mút ngược

Không được so khoảng bằng cách mặc định ax<=bx. `min/max` đúng cho tọa độ âm và mọi hướng.

### Độ lớn cực trị

~~~text
A=(Long.MIN_VALUE, Long.MIN_VALUE)
B=(Long.MAX_VALUE, Long.MAX_VALUE)
P=(0,0)
~~~

P nằm trên đoạn AB. Nhưng `B.x-A.x` không biểu diễn được bằng `long`. Nếu không xử lý overflow, một predicate sai có thể gây lỗi dây chuyền ở giao đoạn, bao lồi và kiểm biên đa giác.

## 9. Overflow: chuyển sang BigInteger trước phép trừ

Một biểu thức thường thấy nhưng **không an toàn trong miền tọa độ long đầy đủ**:

~~~java
long dx = b.x() - a.x();
long dy = b.y() - a.y();
long cross = dx * (p.y() - a.y())
        - dy * (p.x() - a.x());
~~~

Có ba nguồn overflow:

- Hiệu của hai long có thể vượt miền long.
- Tích hai hiệu có thể vượt long dù từng hiệu vừa long.
- Phép trừ hai tích có thể lại vượt long.

**Sai:**

~~~java
BigInteger dx = BigInteger.valueOf(b.x() - a.x());
~~~

Bởi vì phép trừ chạy bằng `long` trước khi chuyển, BigInteger có thể nhận kết quả đã tràn.

**Đúng:**

~~~java
BigInteger dx = BigInteger.valueOf(b.x())
        .subtract(BigInteger.valueOf(a.x()));
~~~

Từ đó tính cross, dot, len² bằng BigInteger.

### Khi nào có thể dùng long?

Nếu đề có giới hạn tọa độ nhỏ, ví dụ |x|,|y|≤10^6, thì mỗi hiệu không vượt 2·10^6, mỗi tích không vượt 4·10^12, độ lớn cross không vượt 8·10^12, vừa long. Khi ấy dùng long có thể nhanh hơn.

Nhưng nếu giới hạn tọa độ là 10^12, 10^18 hoặc không biết, **không được ngầm giả định phép nhân vẫn an toàn**. `Math.subtractExact`, `Math.multiplyExact` giúp phát hiện overflow nhưng chỉ ném lỗi; BigInteger mới cho kết quả lớn chính xác.

### Bounding box riêng lẻ không overflow

`Math.min(ax,bx)<=px && px<=Math.max(ax,bx)` chỉ so long, không cộng/trừ, nên không tràn. Tuy nhiên để membership chính xác, **cross phải được tính đúng**.

## 10. Java 17: chương trình chạy độc lập

Mã gồm:

- `record Point(long x,long y)` đại diện điểm.
- `cross(A,B,P)` exact bằng BigInteger.
- `orientation` trả −1/0/+1 theo dấu.
- `areCollinearByCross` kiểm định thức, có ngữ nghĩa đại số khi A=B.
- `onClosedSegment`, `onOpenSegment` theo quy ước rõ.
- `classifyOnDirectedLine` phân loại BEFORE_A, AT_A, BETWEEN, AT_B, AFTER_B, OFF_LINE và suy biến.
- `segmentsIntersect` kiểm hai đoạn **đóng** giao nhau, gồm chạm và chồng lấn.
- `oracleOnSegmentUsingProjection` dùng dot để kiểm độc lập so với bounding box.
- `verifySmallGrid` đối chiếu trên **15.625 bộ ba điểm** từ lưới [−2,2]².

Toàn bộ phương thức số học hình học chuyển tọa độ sang BigInteger **trước khi trừ**.

Lưu vào **CollinearitySegmentDemo.java**:

~~~java
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class CollinearitySegmentDemo {

    public record Point(long x, long y) {}

    public enum Position {
        BEFORE_A,
        AT_A,
        BETWEEN,
        AT_B,
        AFTER_B,
        OFF_LINE,
        DEGENERATE_POINT,
        DEGENERATE_OTHER
    }

    // Convert before subtracting; long subtraction can overflow.
    private static BigInteger delta(long end, long start) {
        return BigInteger.valueOf(end)
                .subtract(BigInteger.valueOf(start));
    }

    // Cross product (B-A) x (P-A), exact for long inputs.
    public static BigInteger cross(Point a, Point b, Point p) {
        Objects.requireNonNull(a, "a");
        Objects.requireNonNull(b, "b");
        Objects.requireNonNull(p, "p");

        BigInteger ux = delta(b.x(), a.x());
        BigInteger uy = delta(b.y(), a.y());
        BigInteger vx = delta(p.x(), a.x());
        BigInteger vy = delta(p.y(), a.y());

        return ux.multiply(vy).subtract(uy.multiply(vx));
    }

    public static int orientation(Point a, Point b, Point p) {
        return cross(a, b, p).signum();
    }

    // Algebraic collinearity: true for any P if A=B.
    public static boolean areCollinearByCross(
            Point a, Point b, Point p) {
        return orientation(a, b, p) == 0;
    }

    private static boolean betweenInclusive(
            long value, long first, long second) {
        return Math.min(first, second) <= value
                && value <= Math.max(first, second);
    }

    // Closed segment [A,B], including endpoints.
    public static boolean onClosedSegment(
            Point a, Point b, Point p) {
        return areCollinearByCross(a, b, p)
                && betweenInclusive(p.x(), a.x(), b.x())
                && betweenInclusive(p.y(), a.y(), b.y());
    }

    // Open segment (A,B), excluding endpoints.
    public static boolean onOpenSegment(
            Point a, Point b, Point p) {
        return !a.equals(b)
                && onClosedSegment(a, b, p)
                && !p.equals(a)
                && !p.equals(b);
    }

    // Dot of (P-A) and (B-A), exact.
    private static BigInteger projectionNumerator(
            Point a, Point b, Point p) {
        BigInteger ux = delta(b.x(), a.x());
        BigInteger uy = delta(b.y(), a.y());
        BigInteger vx = delta(p.x(), a.x());
        BigInteger vy = delta(p.y(), a.y());
        return vx.multiply(ux).add(vy.multiply(uy));
    }

    private static BigInteger squaredLength(Point a, Point b) {
        BigInteger ux = delta(b.x(), a.x());
        BigInteger uy = delta(b.y(), a.y());
        return ux.multiply(ux).add(uy.multiply(uy));
    }

    public static Position classifyOnDirectedLine(
            Point a, Point b, Point p) {
        Objects.requireNonNull(a, "a");
        Objects.requireNonNull(b, "b");
        Objects.requireNonNull(p, "p");

        if (a.equals(b)) {
            return p.equals(a)
                    ? Position.DEGENERATE_POINT
                    : Position.DEGENERATE_OTHER;
        }
        if (orientation(a, b, p) != 0) {
            return Position.OFF_LINE;
        }

        BigInteger along = projectionNumerator(a, b, p);
        BigInteger length2 = squaredLength(a, b);

        if (along.signum() < 0) {
            return Position.BEFORE_A;
        }
        if (along.signum() == 0) {
            return Position.AT_A;
        }
        if (along.compareTo(length2) < 0) {
            return Position.BETWEEN;
        }
        if (along.compareTo(length2) == 0) {
            return Position.AT_B;
        }
        return Position.AFTER_B;
    }

    // Closed segment intersection, including touch and overlap.
    public static boolean segmentsIntersect(
            Point a, Point b, Point c, Point d) {
        int o1 = orientation(a, b, c);
        int o2 = orientation(a, b, d);
        int o3 = orientation(c, d, a);
        int o4 = orientation(c, d, b);

        if (o1 == 0 && onClosedSegment(a, b, c)) {
            return true;
        }
        if (o2 == 0 && onClosedSegment(a, b, d)) {
            return true;
        }
        if (o3 == 0 && onClosedSegment(c, d, a)) {
            return true;
        }
        if (o4 == 0 && onClosedSegment(c, d, b)) {
            return true;
        }

        // Proper crossing has opposite nonzero orientations.
        return o1 * o2 < 0 && o3 * o4 < 0;
    }

    // Independent bounding condition using dot/projection.
    private static boolean oracleOnSegmentUsingProjection(
            Point a, Point b, Point p) {
        if (a.equals(b)) {
            return p.equals(a);
        }
        if (orientation(a, b, p) != 0) {
            return false;
        }

        BigInteger along = projectionNumerator(a, b, p);
        BigInteger len2 = squaredLength(a, b);

        return along.signum() >= 0
                && along.compareTo(len2) <= 0;
    }

    private static int verifySmallGrid() {
        List<Point> points = new ArrayList<>();
        for (long x = -2; x <= 2; x++) {
            for (long y = -2; y <= 2; y++) {
                points.add(new Point(x, y));
            }
        }

        int checked = 0;
        for (Point a : points) {
            for (Point b : points) {
                for (Point p : points) {
                    boolean actual = onClosedSegment(a, b, p);
                    boolean expected =
                            oracleOnSegmentUsingProjection(a, b, p);

                    if (actual != expected) {
                        throw new AssertionError(
                                "Projection mismatch at "
                                + a + ", " + b + ", " + p);
                    }
                    if (actual != onClosedSegment(b, a, p)) {
                        throw new AssertionError(
                                "Endpoint order mismatch");
                    }

                    boolean strictExpected =
                            expected && !a.equals(b)
                            && !p.equals(a) && !p.equals(b);
                    if (onOpenSegment(a, b, p)
                            != strictExpected) {
                        throw new AssertionError(
                                "Strict membership mismatch");
                    }
                    checked++;
                }
            }
        }
        return checked;
    }

    public static void main(String[] args) {
        Point a = new Point(1, 1);
        Point b = new Point(5, 5);
        Point p = new Point(3, 3);
        Point q = new Point(7, 7);
        Point r = new Point(3, 4);

        System.out.println("P: cross=" + cross(a, b, p)
                + ", orientation=" + orientation(a, b, p)
                + ", closed=" + onClosedSegment(a, b, p)
                + ", strict=" + onOpenSegment(a, b, p)
                + ", position=" + classifyOnDirectedLine(a, b, p));

        System.out.println("Q: cross=" + cross(a, b, q)
                + ", closed=" + onClosedSegment(a, b, q)
                + ", position=" + classifyOnDirectedLine(a, b, q));

        System.out.println("R: cross=" + cross(a, b, r)
                + ", orientation=" + orientation(a, b, r)
                + ", closed=" + onClosedSegment(a, b, r)
                + ", position=" + classifyOnDirectedLine(a, b, r));

        System.out.println("before: position="
                + classifyOnDirectedLine(a, b, new Point(-1, -1)));
        System.out.println("endpoint A: closed="
                + onClosedSegment(a, b, a)
                + ", strict=" + onOpenSegment(a, b, a)
                + ", position=" + classifyOnDirectedLine(a, b, a));

        System.out.println("reversed endpoints: closed="
                + onClosedSegment(b, a, p)
                + ", strict=" + onOpenSegment(b, a, p));

        Point va = new Point(2, -2);
        Point vb = new Point(2, 4);
        Point vp = new Point(2, 1);
        System.out.println("vertical: closed="
                + onClosedSegment(va, vb, vp)
                + ", strict=" + onOpenSegment(va, vb, vp));

        Point single = new Point(9, -4);
        Point other = new Point(9, -3);
        System.out.println("degenerate same: closed="
                + onClosedSegment(single, single, single)
                + ", strict=" + onOpenSegment(single, single, single)
                + ", position="
                + classifyOnDirectedLine(single, single, single));
        System.out.println("degenerate other: closed="
                + onClosedSegment(single, single, other)
                + ", strict=" + onOpenSegment(single, single, other)
                + ", position="
                + classifyOnDirectedLine(single, single, other));

        Point lo = new Point(Long.MIN_VALUE, Long.MIN_VALUE);
        Point hi = new Point(Long.MAX_VALUE, Long.MAX_VALUE);
        Point middle = new Point(0, 0);
        Point right = new Point(Long.MAX_VALUE, Long.MIN_VALUE);
        System.out.println("extreme middle: closed="
                + onClosedSegment(lo, hi, middle)
                + ", strict=" + onOpenSegment(lo, hi, middle));
        System.out.println("extreme right orientation="
                + orientation(lo, hi, right));

        System.out.println("segments crossing="
                + segmentsIntersect(
                        new Point(0, 0), new Point(4, 4),
                        new Point(0, 4), new Point(4, 0)));
        System.out.println("segments disjoint="
                + segmentsIntersect(
                        new Point(0, 0), new Point(1, 1),
                        new Point(2, 2), new Point(3, 3)));
        System.out.println("segments overlap="
                + segmentsIntersect(
                        new Point(0, 0), new Point(4, 0),
                        new Point(2, 0), new Point(6, 0)));
        System.out.println("segments touching="
                + segmentsIntersect(
                        new Point(0, 0), new Point(2, 0),
                        new Point(2, 0), new Point(4, 0)));
        System.out.println("point-segment intersection="
                + segmentsIntersect(
                        new Point(2, 2), new Point(2, 2),
                        new Point(0, 0), new Point(4, 4)));

        System.out.println("exhaustive triples="
                + verifySmallGrid());
    }
}
~~~

Biên dịch và chạy trên JDK 17:

~~~bash
javac CollinearitySegmentDemo.java
java CollinearitySegmentDemo
~~~

**Stdout chính xác:**

~~~text
P: cross=0, orientation=0, closed=true, strict=true, position=BETWEEN
Q: cross=0, closed=false, position=AFTER_B
R: cross=4, orientation=1, closed=false, position=OFF_LINE
before: position=BEFORE_A
endpoint A: closed=true, strict=false, position=AT_A
reversed endpoints: closed=true, strict=true
vertical: closed=true, strict=true
degenerate same: closed=true, strict=false, position=DEGENERATE_POINT
degenerate other: closed=false, strict=false, position=DEGENERATE_OTHER
extreme middle: closed=true, strict=true
extreme right orientation=-1
segments crossing=true
segments disjoint=false
segments overlap=true
segments touching=true
point-segment intersection=true
exhaustive triples=15625
~~~

### Phân tích kết quả

P thẳng hàng và nằm trong đoạn mở. Q thẳng hàng nhưng ngoài đoạn. R có cross=4 nên không nằm trên đường thẳng AB. Đổi thứ tự A,B không thay membership. Đoạn suy biến xử lý được cả điểm trùng và điểm khác. Với hiệu tọa độ vượt miền long, BigInteger vẫn giữ đúng dấu cross. Các ví dụ giao đoạn kiểm cắt thật, rời, chồng lấn, chạm và một đoạn chỉ là một điểm.

Trong lưới nhỏ x,y∈[−2,2], có 25 điểm. Chương trình thử **25³=15.625 bộ ba** (A,B,P) và so hai predicate độc lập về giới hạn, đồng thời kiểm đối xứng [A,B]=[B,A] và strict membership.

## 11. Chứng minh điều kiện cross + bounding box

Hàm `onClosedSegment` dùng cross bằng 0 và hai khoảng tọa độ. Chứng minh cả hai chiều.

**Chiều thuận.** Nếu P nằm trên đoạn AB, tồn tại t∈[0,1] sao cho:

~~~text
P=A+t*(B-A)
~~~

Khi đó cross(AB,AP)=t cross(AB,AB)=0. Từng tọa độ của P là `(1−t)*aCoord+t*bCoord`, luôn nằm giữa hai đầu mút. Do vậy cả ba điều kiện đều thỏa.

**Chiều đảo.** Nếu A=B, bounding box buộc P=A, đúng với đoạn suy biến. Nếu A≠B và cross=0 thì AP=t·AB. Ít nhất một thành phần của AB khác 0; điều kiện tọa độ đó nằm giữa A và B buộc 0≤t≤1. Vậy P thuộc đoạn AB.

**Đoạn mở.** Với A≠B, P=A tương đương t=0 và P=B tương đương t=1. Thêm điều kiện P≠A,B sẽ cho 0<t<1.

**Đối xứng.** Khi đổi A và B, dấu cross có thể đổi, nhưng điều kiện bằng 0 không đổi. Min/max cũng giữ nguyên, nên membership đoạn không phụ thuộc chiều liệt kê đầu mút.

## 12. Độ phức tạp và an toàn kiểu số

Một lần kiểm đoạn đóng cần một số hằng phép trừ, nhân, cộng, so sánh và min/max. Với tọa độ được giới hạn số bit cố định, độ phức tạp theo số điểm là **O(1) thời gian, O(1) bộ nhớ phụ**.

Bản Java sử dụng `BigInteger` cho vài biến trung gian. Chi phí số học BigInteger phụ thuộc số bit, nhưng với các tọa độ đầu vào luôn thuộc `long` 64-bit, số bit của cross có cận cố định và số đối tượng mỗi lần kiểm cũng hữu hạn.

Nếu bài dùng **tọa độ số nguyên có độ dài tùy ý**, chi phí BigInteger cần phân tích theo độ dài bit của các toán hạng; O(1) chỉ đúng trong mô hình số học độ lớn bị chặn.

| Loại phép tính | Ưu điểm | Hạn chế |
| --- | --- | --- |
| int | Nhanh, ngắn | Tràn rất dễ |
| long | Nhanh khi cận tọa độ nhỏ | Không an toàn cho mọi tọa độ long |
| `Math.*Exact` | Phát hiện overflow | Ném lỗi chứ không tính kết quả ngoài miền |
| BigInteger | Chính xác cho hiệu và tích lớn | Cấp phát và tính toán đắt hơn |
| double + tolerance | Hữu ích cho dữ liệu đo gần đúng | Không thay thế predicate nguyên exact |

Nếu có nhiều truy vấn P trên cùng đoạn AB, có thể tiền tính AB, bình phương độ dài, min/max để giảm việc lặp; vẫn phải dùng kiểu số phù hợp.

## 13. Tọa độ số thực và epsilon

Với số thực `double`, kiểm:

~~~java
cross == 0.0
~~~

có thể không phù hợp với dữ liệu đo vì làm tròn. Tuy nhiên thay thành `Math.abs(cross)<1e-9` cho **mọi bài toán** cũng không đúng về mặt ngữ nghĩa: cross có đơn vị **diện tích** và tăng theo bình phương tỷ lệ tọa độ.

### Khoảng cách tới đường thẳng

Nếu A≠B, khoảng cách Euclid từ P tới đường thẳng vô hạn AB là:

~~~text
distanceToLine = abs(cross(B-A,P-A)) / length(B-A)
~~~

Đại lượng này có đơn vị độ dài. Nếu ứng dụng chấp nhận sai số vị trí `epsDistance` theo đơn vị tọa độ, có thể xét:

~~~text
distanceToLine <= epsDistance
~~~

Ngoài ra kiểm hình chiếu dọc AB:

~~~text
along = dot(P-A, unit(B-A))

-epsDistance <= along <= length(B-A)+epsDistance
~~~

Đây là một **định nghĩa gần đoạn do ứng dụng chọn**, không phải phép kiểm chính xác “thuộc đoạn” trong toán học.

### Các cảnh báo khi dùng double

- Cần xác định đơn vị dữ liệu và ngưỡng thực tế trước khi chọn epsilon.
- Xử lý NaN/Infinity thay vì để chúng đi qua so sánh.
- Phép trừ tọa độ cực lớn có thể overflow; giá trị cực nhỏ có thể underflow.
- Đoạn suy biến hoặc gần suy biến cần xử lý riêng để tránh chia cho độ dài gần 0.
- Với orientation robust cho dữ liệu double, có thể cần **adaptive precision geometric predicates**.
- Nếu đầu vào là tọa độ nguyên, nên ưu tiên **số học chính xác**, không chuyển tùy tiện sang double để lấy epsilon.

## 14. Ứng dụng: giao hai đoạn thẳng

Để xác định hai đoạn đóng AB và CD có giao, tính bốn dấu:

~~~text
o1 = sign(cross(A,B,C))
o2 = sign(cross(A,B,D))
o3 = sign(cross(C,D,A))
o4 = sign(cross(C,D,B))
~~~

**Giao cắt thực sự trong phần trong** xảy ra nếu:

~~~text
o1*o2<0 AND o3*o4<0
~~~

Tức C,D ở hai phía khác nhau của đường thẳng AB và A,B ở hai phía khác nhau của đường thẳng CD.

**Chạm đầu mút/chồng lấn** cần kiểm thêm:

~~~text
o1==0 AND C on [A,B]
o2==0 AND D on [A,B]
o3==0 AND A on [C,D]
o4==0 AND B on [C,D]
~~~

Chỉ cần một trong bốn trường hợp đúng là hai đoạn đóng có giao.

Không chỉ dùng `o1!=o2 && o3!=o4` khi có giá trị 0: một điểm nằm trên **phần kéo dài** của đường thẳng nhưng ở ngoài đoạn có thể gây kết luận sai. Mã Java kiểm các trường hợp on-segment trước rồi mới nhận giao cắt với **hai tích dấu âm**.

Bảng ví dụ:

| Hai đoạn | Có giao không? | Lý do |
| --- | --- | --- |
| (0,0)-(4,4) và (0,4)-(4,0) | Có | Cắt thật sự |
| (0,0)-(1,1) và (2,2)-(3,3) | Không | Thẳng hàng nhưng rời |
| (0,0)-(4,0) và (2,0)-(6,0) | Có | Chồng lấn |
| (0,0)-(2,0) và (2,0)-(4,0) | Có | Chạm đầu mút |
| (2,2)-(2,2) và (0,0)-(4,4) | Có | Đoạn suy biến là điểm nằm trên đoạn khác |

## 15. Ứng dụng mở rộng trong hình học

### Kiểm điểm thuộc cạnh đa giác

Khi xét một điểm nằm trên **biên đa giác**, có thể duyệt từng cạnh AB và kiểm `onClosedSegment(A,B,P)`. Nếu true ở một cạnh, P thuộc biên. Đây chỉ là **một bước**, không tự giải đầy đủ bài toán điểm nằm **trong** đa giác (cần ray casting hoặc winding number).

### Bao lồi (convex hull)

Thuật toán Graham scan hoặc monotone chain thường dùng dấu cross để quyết định hướng rẽ khi kiểm một điểm có nằm trên phía lồi của cạnh đang xét hay không. Quy tắc giữ hay loại điểm **thẳng hàng trên cạnh bao lồi** tùy yêu cầu đầu ra; không được nhầm “thẳng hàng” với “nằm giữa”.

### Đếm điểm nguyên trên đoạn

Với hai điểm nguyên phân biệt:

~~~text
dx = abs(bx-ax)
dy = abs(by-ay)
g  = gcd(dx,dy)

so diem nguyen tren doan dong = g+1
so diem nguyen nam giua chat  = g-1
~~~

Ví dụ A=(0,0), B=(6,4), gcd(6,4)=2, các điểm nguyên trên đoạn là (0,0), (3,2), (6,4): có 3 điểm đóng và 1 điểm trong.

Nếu A=B, đoạn suy biến chỉ có đúng một điểm; công thức g−1 cho số điểm trong không áp dụng theo nghĩa thông thường. Với tọa độ long cực trị, hiệu và abs cũng có thể tràn (chẳng hạn `Math.abs(Long.MIN_VALUE)`), nên cần BigInteger cho bài đếm tổng quát.

### Kiểm tia (ray)

Tia A→B với A≠B gồm `P=A+t(B-A)` và t≥0. Predicate là:

~~~text
cross(A,B,P)==0
AND dot(P-A,B-A)>=0
~~~

Không áp đặt t≤1. Do đó Q=(7,7) nằm trên tia từ (1,1) qua (5,5), nhưng ngoài đoạn giữa hai điểm ấy.

## 16. Những lỗi thường gặp

| Lỗi | Hậu quả | Khắc phục |
| --- | --- | --- |
| Chỉ kiểm cross==0 để nhận trên đoạn | Nhận điểm ngoài phần kéo dài | Thêm bounding box |
| Chỉ kiểm bounding box | Nhận điểm lệch khỏi đường | Thêm cross |
| Chỉ kiểm hình chiếu/dot | Nhận điểm không thẳng hàng | Thêm cross |
| Dùng hệ số góc bằng chia | Chia cho 0 ở đoạn đứng | Dùng định thức |
| Nhầm hệ trục y xuống | Đọc sai dấu trái/phải | Ghi rõ hệ trục |
| Nhầm đoạn đóng với đoạn mở | Sai ở đầu mút | Chọn strict/inclusive |
| Không xử lý A=B | Cross=0 với mọi P | Đoạn suy biến chỉ chứa A |
| Chỉ kiểm x hoặc y | Sai ở đoạn đứng/ngang | Kiểm cả x và y |
| Giả định ax≤bx | Sai khi đảo đầu mút | Dùng min/max |
| Tính cross bằng int | Overflow | Long với cận hoặc BigInteger |
| Tính cross bằng long tùy tiện | Tràn ở hiệu/tích | Chứng minh cận hoặc BigInteger |
| Tạo BigInteger từ phép trừ long | Đã tràn trước khi chuyển | Chuyển trước khi trừ |
| Dùng `Math.abs(Long.MIN_VALUE)` | Không trả trị tuyệt đối mong muốn | Dùng BigInteger |
| Dùng EPS cố định trên cross | Sai thang đo | Khoảng cách/tolerance có đơn vị |
| Không xử lý NaN/Infinity | So sánh sai | Validate double |
| Đổi A,B nhưng giữ nghĩa BEFORE/AFTER cũ | Phân loại hướng sai | Phân biệt hướng và membership |
| Giao đoạn chỉ kiểm signs khác nhau có 0 | Có false positive | Kiểm on-segment và tích dấu âm |
| Không test suy biến | Sai trường hợp A=B | Test riêng |
| Đếm điểm nguyên g−1 khi A=B | Kết quả không hợp lệ | Xử lý riêng |
| Dùng đường thẳng vô hạn thay đoạn | Nhận sai điểm kéo dài | Kiểm miền t∈[0,1] |
| Chỉ test tọa độ dương | Bỏ lỗi min/max và dấu | Thử âm, đảo đầu mút |

## 17. Kiểm thử bằng oracle độc lập

### Các ca mẫu

| A | B | P | Cross | Đoạn đóng | Đoạn mở |
| --- | --- | --- | ---: | --- | --- |
| (1,1) | (5,5) | (3,3) | 0 | true | true |
| (1,1) | (5,5) | (1,1) | 0 | true | false |
| (1,1) | (5,5) | (5,5) | 0 | true | false |
| (1,1) | (5,5) | (7,7) | 0 | false | false |
| (1,1) | (5,5) | (3,4) | 4 | false | false |
| (2,-2) | (2,4) | (2,1) | 0 | true | true |
| (2,-2) | (2,4) | (3,1) | -6 | false | false |
| (9,-4) | (9,-4) | (9,-4) | 0 | true | false |
| (9,-4) | (9,-4) | (9,-3) | 0 | false | false |

### Lưới 15.625 bộ ba

Chọn các điểm nguyên x,y trong [−2,2], có 5×5=25 điểm. Duyệt mọi bộ ba có thứ tự A,B,P:

~~~text
25 * 25 * 25 = 15625
~~~

Với mỗi bộ ba:

1. So kết quả **cross + bounding box** với **cross + projection/dot**.
2. Đảo A,B, membership đoạn đóng phải giữ nguyên.
3. Strict membership bằng closed && A!=B && P!=A && P!=B.
4. Không xảy ra truy cập ngoài miền, chia cho 0 hoặc lỗi số học.

Oracle không lặp lại phép so min/max mà dùng tích vô hướng, nhằm tăng khả năng phát hiện lỗi điều kiện segment. Cả hai cùng sử dụng định thức exact để kiểm thẳng hàng.

### Ranh giới 64-bit

Thử A=(Long.MIN_VALUE,Long.MIN_VALUE), B=(Long.MAX_VALUE,Long.MAX_VALUE), P=(0,0): membership đóng và mở đều true. Điểm R=(Long.MAX_VALUE,Long.MIN_VALUE) cho orientation âm rất lớn; `cross` BigInteger không overflow.

### Kiểm giao đoạn

Kiểm riêng: cắt trong phần trong, thẳng hàng rời, thẳng hàng chồng, chạm đầu mút, một hoặc hai đoạn suy biến, đoạn thẳng đứng và ngang, đường thẳng trùng nhưng không giao đoạn.

### Property-based tests

- `onOpenSegment => onClosedSegment` luôn đúng.
- `onClosedSegment(A,B,A)` và `onClosedSegment(A,B,B)` luôn true.
- `onOpenSegment(A,B,A)` và `onOpenSegment(A,B,B)` luôn false.
- Đổi thứ tự A,B không đổi membership.
- Nếu A=B thì onClosed đúng khi và chỉ khi P=A.
- Nếu onClosed thì `orientation==0`.
- Nếu P có orientation khác 0 thì onClosed và onOpen đều false.
- Với A≠B và cross=0, classification dọc AB nhất quán với dấu của dot và length².
- Kết quả giao đoạn đối xứng khi đổi thứ tự hai đoạn và khi đảo đầu mút mỗi đoạn.

## 18. Chọn predicate đúng với câu hỏi

| Câu hỏi | Predicate |
| --- | --- |
| “Ba điểm A,B,P thẳng hàng?” | `cross==0`, ghi rõ khi có điểm trùng |
| “P ở trái hướng A→B?” | `cross>0` với hệ Descartes và A≠B |
| “P trên đường thẳng vô hạn AB?” | A≠B và `cross==0` |
| “P trên tia A→B?” | A≠B, cross==0, dot(P−A,B−A)≥0 |
| “P trên đoạn đóng AB?” | cross==0 + bounding x/y |
| “P nằm nghiêm ngặt giữa A,B?” | onClosed, A≠B, P≠A và P≠B |
| “P trước A hoặc sau B?” | A≠B, cross==0, so projection với 0 và len² |
| “Hai đoạn đóng có giao?” | orientation + onClosedSegment ở trường hợp cross=0 |
| “P cách đoạn AB dưới ngưỡng sai số?” | Khoảng cách/project và tolerance theo ứng dụng |

Một lời giải hình học tốt bắt đầu bằng việc **chốt ngữ nghĩa**. Hai chương trình cùng dùng cross có thể trả khác nhau nếu một chương trình xét đường thẳng vô hạn, một chương trình xét tia, và một chương trình xét đoạn.

Khi đề mơ hồ về từ “between”, dùng ví dụ và điều kiện đầu mút để xác định có tính A,B hay không; tránh diễn giải theo tên hàm chung chung.

## 19. Bài tập thực hành

1. Tính cross(A,B,P) với A=(1,1),B=(5,5),P=(3,3).
2. Tính cross(A,B,R) với R=(3,4); giải thích dấu dương.
3. Với Q=(7,7), giải thích vì sao cross=0 nhưng không thuộc AB.
4. Viết công thức onClosedSegment không cần phép chia.
5. Viết onOpenSegment và xử lý A=B.
6. Tính projection/length² cho P nằm giữa A=(1,1),B=(5,5).
7. Chứng minh dot/length² tương đương tham số t khi đã thẳng hàng.
8. Phân loại BEFORE_A,AT_A,BETWEEN,AT_B,AFTER_B bằng dot.
9. Kiểm đoạn đứng (2,−2)→(2,4) với (2,1), (2,100), (3,1).
10. Kiểm đoạn ngang (−3,5)→(4,5) với (0,5), (0,6).
11. Thử đảo A,B; chứng minh membership không đổi.
12. Phân biệt đường thẳng AB, tia A→B và đoạn AB.
13. Cài kiểm tia A→B, thử Q=(7,7).
14. Giải thích vì sao cross(A,A,P)=0 với mọi P.
15. Tính cross của (0,0),(4,0),(2,1).
16. Chứng minh dot(P−A,P−B)≤0 cho P thẳng hàng thuộc đoạn.
17. Tìm P có hình chiếu trong AB nhưng P không nằm trên đường thẳng.
18. Tạo một ca hệ số góc bị chia cho 0 nhưng cross vẫn đúng.
19. Chứng minh cross + bounding box cần và đủ bằng tham số t.
20. Tính dấu orientation khi đổi A↔B.
21. Viết BigInteger cross chuyển từng tọa độ trước khi trừ.
22. Tìm tọa độ làm phép trừ long overflow.
23. Tìm tọa độ làm phép nhân hai hiệu long overflow.
24. So `Math.multiplyExact` với BigInteger về fail-fast.
25. Viết test toàn bộ 15.625 bộ ba trên lưới [−2,2].
26. Viết kiểm thử đối xứng của onClosed khi đảo đầu mút.
27. Kiểm A=B với P=A và P≠A.
28. Cài segmentsIntersect có xử lý chạm và chồng.
29. Tạo hai đoạn thẳng hàng nhưng không giao.
30. Tạo hai đoạn cắt hình chữ X và tính bốn dấu.
31. Tìm điểm thuộc cạnh đa giác, phân biệt với điểm nằm trong đa giác.
32. Liệt kê điểm nguyên trên đoạn (0,0)→(6,4).
33. Chứng minh số điểm nguyên trên đoạn không suy biến bằng gcd(|dx|,|dy|)+1.
34. Giải thích vì sao EPS trên cross không phù hợp mọi tỷ lệ hình.
35. Thiết kế tiêu chí khoảng cách tới đoạn với epsDistance.
36. Viết kiểm tra NaN/Infinity cho dữ liệu double.
37. Phân biệt chiều dấu cross trong hệ trục y hướng xuống.
38. Test property onOpen=>onClosed và một phản ví dụ cho chiều ngược.
39. Thiết kế bộ test cho Long.MIN_VALUE và Long.MAX_VALUE.
40. Giải thích vì sao đoạn suy biến không có phần trong.

## 20. Checklist và tổng kết

Trước khi dùng một predicate hình học, kiểm tra:

- Hệ tọa độ dùng trục y hướng lên hay xuống?
- Bài hỏi thẳng hàng, trên đường thẳng, trên tia, đoạn đóng hay nằm giữa chặt?
- Đã xử lý A=B, P=A hoặc P=B chưa?
- Có đủ **cross==0 và hai khoảng tọa độ** khi kiểm đoạn không?
- Nếu dùng dot, đã xác nhận thẳng hàng chưa?
- Có dùng min/max khi A,B có thể bị đảo không?
- Kiểu số có chịu được hiệu và tích các hiệu tọa độ không?
- Nếu dùng BigInteger, đã chuyển **trước** khi trừ chưa?
- Nếu dùng double, ngưỡng tolerance có thang đo và đơn vị rõ chưa?
- Có test đoạn ngang, đứng, âm, suy biến, ngoài phần kéo dài và tọa độ cực trị không?
- Có oracle độc lập và test property đối xứng/strict không?
- Khi kiểm giao đoạn, có xử lý orientation=0 bằng on-segment thay vì chỉ so dấu không?

**Kết luận:** Ba điểm A,B,P thẳng hàng theo định thức khi `cross(B−A,P−A)=0`. Để kiểm P nằm trên **đoạn đóng**, phải kết hợp thêm:

~~~text
min(ax,bx) <= px <= max(ax,bx)
min(ay,by) <= py <= max(ay,by)
~~~

Muốn **nằm giữa chặt**, yêu cầu A≠B và P không trùng hai đầu mút. Có thể thay bounding box bằng kiểm projection/dot khi đã biết thẳng hàng. Với tọa độ nguyên long không có cận nhỏ, dùng BigInteger cho hiệu và tích nhằm tránh overflow. Phân biệt **đường thẳng vô hạn, tia, đoạn đóng, đoạn mở** cùng các trường hợp suy biến là cơ sở quan trọng để xây những thuật toán lớn hơn như giao đoạn, bao lồi và kiểm biên đa giác.
