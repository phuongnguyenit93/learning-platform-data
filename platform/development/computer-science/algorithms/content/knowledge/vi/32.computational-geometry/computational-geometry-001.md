# Điểm, vectơ và các phép kiểm tra hình học cơ bản

> **Chủ đề:** Computer Science Algorithms → **Hình học tính toán**.  
> **Mục tiêu:** Học cách biểu diễn điểm/vectơ trong mặt phẳng; tính hiệu tọa độ, tích vô hướng, tích có hướng, hướng quay, thẳng hàng, diện tích, giao đường/đoạn, khoảng cách, hình chiếu, diện tích đa giác, kiểm tra điểm trong đa giác và bao lồi. Đặc biệt phân biệt **tính toán chính xác** trên tọa độ nguyên với phép đo xấp xỉ trên số thực, xử lý đầu mút/biên/trường hợp suy biến và tránh overflow Java. Các ví dụ Java 17 độc lập đều kèm lệnh biên dịch và stdout dự kiến.

## 1. Điểm và vectơ khác nhau như thế nào?

**Điểm** P=(x,y) là vị trí trong một hệ tọa độ. **Vectơ** u=(ux,uy) mô tả độ dời, không gắn cố định với một vị trí.

Cho hai điểm A=(ax,ay), B=(bx,by):

`AB = B−A = (bx−ax, by−ay)`.

Ví dụ A=(1,2), B=(4,6) thì AB=(3,4). Có thể thực hiện:

- **Điểm + vectơ → điểm:** `(ax,ay)+(ux,uy)=(ax+ux,ay+uy)`.
- **Điểm − điểm → vectơ:** `B−A`.
- **Vectơ + vectơ → vectơ:** `(ux+vx,uy+vy)`.
- **Nhân vectơ với hệ số:** `λu=(λux,λuy)`.
- **Vectơ không:** `(0,0)`, độ dài0, không có hướng xác định.

Không được nhầm phép cộng hai **vị trí** với một phép toán vectơ có ý nghĩa trong mọi ngữ cảnh. Một trung điểm M=(A+B)/2 là một tổ hợp affine: M=A+(B−A)/2.

### 1.1. Quy ước hệ tọa độ

Mặc định: trục x sang phải, trục y **hướng lên**, tức hệ Descartes chuẩn. Trong hệ này:

- Từ vectơ nằm ngang hướng phải sang hướng lên là quay **ngược chiều kim đồng hồ** (*CCW*).
- Từ vectơ hướng phải sang hướng xuống là quay **cùng chiều kim đồng hồ** (*CW*).

Trong nhiều hệ tọa độ màn hình, y **hướng xuống**, nên dấu CCW/CW theo trực giác hình vẽ sẽ **đảo**. Cần công bố quy ước trước khi viết hoặc kiểm thử `orientation`.

### 1.2. Đường thẳng và đoạn thẳng

Với A≠B, đường thẳng đi qua A,B gồm các điểm:

`P(t)=A+t·(B−A)`, t là số thực bất kỳ.

**Đoạn thẳng đóng** AB gồm các P(t) với `0≤t≤1`. Nó **bao gồm hai đầu mút A và B**. Trong bài này, giao tại đầu mút được tính là giao.

- t=0 ⇒ P=A.
- t=1 ⇒ P=B.
- 0<t<1 ⇒ P trong lòng đoạn.
- t<0 hoặc t>1 ⇒ P trên đường kéo dài nhưng không thuộc đoạn.

Nếu A=B, đoạn suy biến thành **một điểm**; không có một đường thẳng duy nhất được xác định bởi hai điểm trùng nhau.

### 1.3. Tịnh tiến bảo toàn phép kiểm hình học

Nếu cộng cùng vectơ t vào tất cả điểm, hiệu tọa độ không đổi:

`(B+t)−(A+t)=B−A`.

Vì thế **hướng quay, giao đoạn, khoảng cách, diện tích** không thay đổi dưới phép tịnh tiến. Có thể dùng đây làm một kiểm thử bất biến (*metamorphic testing*) thay vì chỉ so với vài hình vẽ minh họa.

## 2. Tích vô hướng (*dot product*)

Với u=(ux,uy), v=(vx,vy):

`dot(u,v)=ux·vx+uy·vy`.

Khi cả hai vectơ khác0:

`dot(u,v)=|u|·|v|·cosθ`.

Do đó:

- dot>0: góc θ giữa hai vectơ **nhọn**.
- dot=0: hai vectơ **vuông góc**.
- dot<0: góc **tù**.

Nếu một vectơ bằng0 thì dot=0 nhưng **góc giữa vectơ không và vectơ khác không không xác định**; đừng kết luận có góc 90°.

### 2.1. Ví dụ

u=(3,4), v=(-4,3):

`dot(u,v)=3·(-4)+4·3=−12+12=0`.

Hai vectơ khác0 nên vuông góc.

Độ dài bình phương:

`normSquared(u)=dot(u,u)=3²+4²=25`.

Vậy |u|=5. Tương tự |v|=5.

### 2.2. So độ dài mà không dùng căn

Nếu chỉ cần xem |u| nhỏ hơn |v| không, so sánh:

`dot(u,u)` với `dot(v,v)`.

Vì căn bậc hai tăng trên các số không âm, hai cách cho thứ tự giống nhau. Không tính `sqrt` nếu không cần in độ dài thực.

### 2.3. Hình chiếu lên đường thẳng

Cho A≠B, r=B−A và điểm P:

`t=dot(P−A,r)/dot(r,r)`.

Chân chiếu vuông góc lên **đường thẳng vô hạn** AB:

`H=A+t·r`.

Để tìm điểm gần P nhất trên **đoạn đóng** AB, chặn tham số:

`t_segment = max(0,min(1,t))`.

Sau đó dùng `A+t_segment·r`. Với đoạn suy biến A=B, điểm gần nhất trên đoạn đơn giản là A; tuyệt đối không chia cho `dot(r,r)=0`.

## 3. Tích có hướng 2D (*cross product*)

Với u=(ux,uy), v=(vx,vy):

`cross(u,v)=ux·vy−uy·vx`.

Đây là định thức hai chiều. Nó cho **diện tích có dấu** của hình bình hành do u,v tạo thành.

- cross>0: v nằm về bên trái u theo hệ trục y hướng lên; quay từ u sang v là CCW.
- cross<0: quay CW.
- cross=0: hai vectơ song song/thẳng hàng, kể cả khi một vectơ bằng0.

Tính chất:

`cross(u,v)=−cross(v,u)`;

`cross(u,u)=0`;

`|cross(u,v)|=|u|·|v|·|sinθ|`.

### 3.1. Ví dụ u=(3,4), v=(-4,3)

`cross(u,v)=3·3−4·(-4)=9+16=25`.

Kết hợp dot0 và cross dương, hai vectơ vuông góc, quay từ u sang v là CCW90°.

### 3.2. Tại sao dấu bị đảo dễ gây lỗi?

Nếu viết `cross(C−A,B−A)` thay vì `cross(B−A,C−A)`, kết quả sẽ **đổi dấu**, từ CCW thành CW. Mọi thuật toán như giao đoạn/bao lồi sử dụng dấu phải dùng **một thứ tự điểm nhất quán**.

### 3.3. Khi nào lấy giá trị tuyệt đối?

- Muốn kiểm hướng: **giữ dấu**.
- Muốn diện tích không âm: lấy `abs(cross)`.
- Muốn hai vectơ song song: kiểm `cross==0`, với số học chính xác nếu dữ liệu nguyên.

## 4. Phép kiểm hướng quay (*orientation*) của ba điểm

Cho A,B,C:

`orient(A,B,C) = cross(B−A,C−A)`.

| orient | Ý nghĩa với hệ trục y hướng lên |
|---|---|
| >0 | C ở bên trái đường A→B; ba điểm tạo CCW |
| <0 | C ở bên phải đường A→B; ba điểm tạo CW |
| =0 | A,B,C thẳng hàng theo định thức |

Ví dụ A=(0,0), B=(4,0), C=(2,3):

`orient = (4,0)×(2,3) = 12>0`.

Kết luận: CCW; C bên trái hướng A→B.

### 4.1. Diện tích tam giác

`twiceArea(ABC)=abs(orient(A,B,C))`.

Với A=(0,0),B=(4,0),C=(2,3), `twiceArea=12`, diện tích bằng6.

Với tọa độ nguyên, twiceArea là số nguyên, còn diện tích có thể là số nguyên hoặc một nửa số nguyên. **Giữ twiceArea dưới dạng nguyên** nếu không cần xuất diện tích thực.

### 4.2. Thẳng hàng chưa chắc thuộc đoạn

Nếu A=(0,0), B=(4,0), C=(5,0), orientation=0 nhưng C **ngoài đoạn AB**. Phải kiểm thêm phạm vi tọa độ.

### 4.3. Công thức khai triển độc lập

Có thể viết:

`orient(A,B,C) = (bx−ax)(cy−ay) − (by−ay)(cx−ax)`,

hoặc định thức mở rộng:

`ax(by−cy)+bx(cy−ay)+cx(ay−by)`.

Hai biểu thức bằng nhau trong số học chính xác. Dùng chúng làm **oracle kiểm lại dấu** trong test.

### 4.4. Tránh overflow: chuyển sang BigInteger trước khi trừ

Không được tính hiệu `long` rồi mới chuyển sang BigInteger:

```java
// SAI khi b.x() - a.x() overflow long:
BigInteger dx = BigInteger.valueOf(b.x() - a.x());
```

Cách đúng:

```java
BigInteger dx = BigInteger.valueOf(b.x())
        .subtract(BigInteger.valueOf(a.x()));
```

Tọa độ A.x=Long.MIN_VALUE, B.x=Long.MAX_VALUE cho hiệu toán học `2^64−1`, vượt `long`. Tích có hướng hai hiệu còn có thể cần hơn 64 bit. Nếu cần quyết định hướng/giao **đúng tuyệt đối** trên toàn miền long, phải dùng BigInteger (hoặc kiểu rộng đủ kèm chứng minh giới hạn).

## 5. Điểm nằm trên đoạn thẳng đóng

Với đoạn AB và điểm P, điều kiện cần và đủ:

1. `orient(A,B,P)=0`: P nằm trên đường thẳng AB (hoặc AB suy biến).
2. `min(ax,bx)≤px≤max(ax,bx)`.
3. `min(ay,by)≤py≤max(ay,by)`.

Hai điều kiện sau tạo **hộp bao** (*bounding box*) của đoạn.

### 5.1. Ví dụ

A=(0,0), B=(4,0):

- P=(2,0) ⇒ **thuộc đoạn**.
- P=(4,0) ⇒ **thuộc đoạn** vì đoạn đóng chứa đầu mút.
- P=(5,0) ⇒ **không thuộc đoạn**, tuy thẳng hàng.
- P=(2,1) ⇒ **không thuộc đoạn**, tuy x,y nằm trong bbox.

Vì vậy chỉ kiểm orientation hoặc chỉ kiểm bbox đều **không đủ**.

### 5.2. Đoạn suy biến A=B

Nếu A=B=(2,0), orient(A,A,P)=0 **với mọi P** vì vectơ AA=(0,0). Nhưng bbox thu thành một điểm duy nhất, nên công thức trên vẫn trả true **chỉ khi P=A**.

Không cần một nhánh đặc biệt trong onSegment nếu đã kết hợp **cả orientation và bbox** một cách chính xác.

## 6. Hai đoạn thẳng giao nhau — phân loại chính xác

Cho hai đoạn đóng AB và CD. Ta trả một trong bốn trạng thái:

- `NONE`: không có điểm chung.
- `PROPER`: cắt tại một điểm nằm **trong lòng cả hai đoạn**, không ở đầu mút.
- `TOUCH`: giao tại đúng **một điểm** nhưng không phải PROPER (ví dụ chạm đầu mút hoặc một đoạn suy biến).
- `OVERLAP`: hai đoạn cùng đường và có một đoạn chung **dài dương**.

Phân loại bốn mức có ích hơn boolean trong nhiều bài toán va chạm và bao lồi.

### 6.1. Phép kiểm orientation bốn phía

Đặt:

`o1=orient(A,B,C)`,
`o2=orient(A,B,D)`,
`o3=orient(C,D,A)`,
`o4=orient(C,D,B)`.

Nếu o1,o2 **trái dấu nghiêm ngặt** và o3,o4 trái dấu nghiêm ngặt:

`o1·o2<0` và `o3·o4<0`,

thì hai đoạn cắt **PROPER**.

Trên code, có thể lấy `signum()` trước rồi nhân các dấu -1/0/+1, hoặc dùng so sánh dấu; **không cần nhân hai định thức lớn** có thể overflow.

### 6.2. Chạm biên hoặc đầu mút

Nếu một orientation=0 **và** điểm tương ứng `onSegment` của đoạn còn lại, có giao ở biên. Ví dụ:

AB=(0,0)–(4,0), CD=(4,0)–(4,5) ⇒ `TOUCH` tại (4,0).

Nhớ rằng orientation=0 **không** đủ: điểm có thể nằm ngoài đoạn trên phần đường kéo dài.

### 6.3. Hai đoạn thẳng hàng

Nếu cả bốn orient=0, xét giao của **hai khoảng theo thứ tự từ điển tọa độ** `(x,y)`.

Đặt:

`lowAB = minLex(A,B)`, `highAB=maxLex(A,B)`;

`lowCD = minLex(C,D)`, `highCD=maxLex(C,D)`.

`lo=maxLex(lowAB,lowCD)`,
`hi=minLex(highAB,highCD)`.

Khi mọi điểm collinear, thứ tự từ điển đi dọc theo đường thẳng (nếu x không đổi thì dùng y):

- lo>hi ⇒ `NONE`.
- lo==hi ⇒ `TOUCH`.
- lo<hi ⇒ `OVERLAP`.

Cách này xử lý đoạn ngang, dọc, dốc âm và cả đoạn suy biến.

### 6.4. Bảng ví dụ

| AB | CD | Kết quả |
|---|---|---|
| (0,0)–(4,4) | (0,4)–(4,0) | `PROPER` tại (2,2) |
| (0,0)–(4,0) | (4,0)–(4,5) | `TOUCH` |
| (0,0)–(5,0) | (2,0)–(8,0) | `OVERLAP` |
| (0,0)–(2,0) | (3,0)–(5,0) | `NONE` |
| (0,0)–(4,0) | (0,2)–(4,2) | `NONE` song song khác đường |
| (2,0)–(2,0) | (0,0)–(4,0) | `TOUCH` điểm–đoạn |
| (2,1)–(2,1) | (0,0)–(4,0) | `NONE` điểm ngoài đoạn |
| (2,1)–(2,1) | (2,1)–(2,1) | `TOUCH` hai đoạn điểm trùng |

### 6.5. Các bất biến mạnh

Kết quả **không phụ thuộc** thứ tự liệt kê đoạn:

`classify(A,B,C,D)=classify(C,D,A,B)`.

Đảo đầu mút cũng không thay đổi loại giao:

`classify(A,B,C,D)=classify(B,A,D,C)`.

Tịnh tiến mọi điểm cùng vectơ cũng không làm thay đổi giao. Đây là những test nhanh và hữu ích để bắt lỗi dấu/biên.

## 7. Giao hai đường thẳng — phân số hữu tỉ chính xác

Hai đường thẳng vô hạn AB và CD (A≠B,C≠D) có tham số:

`L1=A+t·r`, với r=B−A;

`L2=C+u·s`, với s=D−C.

Đặt w=C−A. Từ A+t·r=C+u·s, lấy cross với s:

`t·cross(r,s)=cross(w,s)`.

Nếu mẫu `den=cross(r,s)≠0`, suy ra:

`t=cross(w,s)/den`.

Tương tự:

`u=cross(w,r)/den`.

Nếu tọa độ đầu vào nguyên, t,u và tọa độ giao điểm là **hữu tỉ**; có thể dùng `BigInteger` cho tử/mẫu và **rút gọn** bằng gcd.

### 7.1. Ví dụ giao 3/2

Đường qua (0,0),(3,3) có phương trình y=x. Đường qua (0,3),(3,0) có phương trình y=3−x.

Giao:

`x=3−x` ⇒ `x=3/2`, `y=3/2`.

Đây là giao **PROPER** của hai đoạn tương ứng.

### 7.2. Giao đoạn khác giao đường

Hai **đường vô hạn** có thể cắt nhau ngoài một trong hai đoạn. Để giao nằm trên **hai đoạn đóng**, cần:

`0≤t≤1` và `0≤u≤1`.

Nếu cả bốn bất đẳng thức nghiêm ngặt, giao PROPER. Nếu bằng0 hoặc1 tại một phía, thường là TOUCH.

So t,u bằng **tử/mẫu nguyên** sau khi đưa mẫu dương, không nhất thiết chuyển double.

### 7.3. Khi mẫu bằng0

Nếu `cross(r,s)=0`, hai phương song song:

- Hai đường khác nhau ⇒ không giao.
- Hai đường trùng nhau ⇒ vô số điểm chung.
- Một đoạn suy biến ⇒ không xác định một đường thẳng duy nhất qua hai điểm khác nhau.

Không được chia mẫu0. Nếu cần phân loại **giao hai đoạn** collinear, dùng giao khoảng như phần6.

## 8. Java 17 — các predicate nguyên và giao hữu tỉ

Chương trình hoàn chỉnh dùng `record Point(long x,long y)` và `Vector(BigInteger x,y)`. **Mọi phép trừ và nhân của định thức được thực hiện trên BigInteger**, kể cả khi tọa độ đầu vào là Long.MIN/MAX.

Lưu **ExactGeometryPredicatesDemo.java**:

```java
import java.math.BigInteger;

public class ExactGeometryPredicatesDemo {
    record Point(long x, long y) {}
    record Vector(BigInteger x, BigInteger y) {
        BigInteger dot(Vector v) {
            return x.multiply(v.x).add(y.multiply(v.y));
        }
        BigInteger cross(Vector v) {
            return x.multiply(v.y).subtract(y.multiply(v.x));
        }
        BigInteger normSquared() {
            return dot(this);
        }
    }

    enum IntersectionKind { NONE, PROPER, TOUCH, OVERLAP }

    record Rational(BigInteger num, BigInteger den) {
        Rational {
            if (den.signum() == 0) {
                throw new IllegalArgumentException("Zero denominator");
            }
            if (den.signum() < 0) {
                num = num.negate();
                den = den.negate();
            }
            BigInteger g = num.gcd(den);
            num = num.divide(g);
            den = den.divide(g);
        }
        @Override
        public String toString() {
            return den.equals(BigInteger.ONE)
                    ? num.toString() : num + "/" + den;
        }
    }

    record RationalPoint(Rational x, Rational y) {
        @Override
        public String toString() {
            return "(" + x + ", " + y + ")";
        }
    }

    static Vector difference(Point from, Point to) {
        return new Vector(
                BigInteger.valueOf(to.x())
                        .subtract(BigInteger.valueOf(from.x())),
                BigInteger.valueOf(to.y())
                        .subtract(BigInteger.valueOf(from.y())));
    }

    static BigInteger orient(Point a, Point b, Point c) {
        return difference(a, b).cross(difference(a, c));
    }

    static String direction(Point a, Point b, Point c) {
        int s = orient(a, b, c).signum();
        return s > 0 ? "CCW" : s < 0 ? "CW" : "COLLINEAR";
    }

    static boolean between(long a, long b, long p) {
        return Math.min(a, b) <= p && p <= Math.max(a, b);
    }

    static boolean onSegment(Point a, Point b, Point p) {
        return orient(a, b, p).signum() == 0
                && between(a.x(), b.x(), p.x())
                && between(a.y(), b.y(), p.y());
    }

    static int compare(Point a, Point b) {
        int x = Long.compare(a.x(), b.x());
        return x != 0 ? x : Long.compare(a.y(), b.y());
    }
    static Point lower(Point a, Point b) {
        return compare(a, b) <= 0 ? a : b;
    }
    static Point upper(Point a, Point b) {
        return compare(a, b) >= 0 ? a : b;
    }

    static IntersectionKind classify(
            Point a, Point b, Point c, Point d) {
        int o1 = orient(a, b, c).signum();
        int o2 = orient(a, b, d).signum();
        int o3 = orient(c, d, a).signum();
        int o4 = orient(c, d, b).signum();

        if (o1 == 0 && o2 == 0 && o3 == 0 && o4 == 0) {
            Point lo = upper(lower(a, b), lower(c, d));
            Point hi = lower(upper(a, b), upper(c, d));
            int cmp = compare(lo, hi);
            return cmp > 0 ? IntersectionKind.NONE
                    : cmp == 0 ? IntersectionKind.TOUCH
                    : IntersectionKind.OVERLAP;
        }

        if (o1 * o2 < 0 && o3 * o4 < 0) {
            // o1...o4 chỉ là dấu -1/0/+1, nhân an toàn.
            return IntersectionKind.PROPER;
        }

        if ((o1 == 0 && onSegment(a, b, c))
                || (o2 == 0 && onSegment(a, b, d))
                || (o3 == 0 && onSegment(c, d, a))
                || (o4 == 0 && onSegment(c, d, b))) {
            return IntersectionKind.TOUCH;
        }
        return IntersectionKind.NONE;
    }

    static RationalPoint lineIntersection(
            Point a, Point b, Point c, Point d) {
        Vector r = difference(a, b);
        Vector s = difference(c, d);
        Vector w = difference(a, c);
        BigInteger den = r.cross(s);

        if (den.signum() == 0) return null;

        BigInteger tNum = w.cross(s);
        BigInteger xNum = BigInteger.valueOf(a.x())
                .multiply(den).add(r.x().multiply(tNum));
        BigInteger yNum = BigInteger.valueOf(a.y())
                .multiply(den).add(r.y().multiply(tNum));

        return new RationalPoint(
                new Rational(xNum, den),
                new Rational(yNum, den));
    }

    static void printKind(
            String label, Point a, Point b, Point c, Point d) {
        System.out.println(label + ": " + classify(a, b, c, d));
    }

    public static void main(String[] args) {
        Point a = new Point(0, 0);
        Point b = new Point(4, 0);
        Point c = new Point(2, 3);
        Vector u = new Vector(BigInteger.valueOf(3),
                              BigInteger.valueOf(4));
        Vector v = new Vector(BigInteger.valueOf(-4),
                              BigInteger.valueOf(3));

        System.out.println("dot(u,v) = " + u.dot(v));
        System.out.println("cross(u,v) = " + u.cross(v));
        System.out.println("|u|^2 = " + u.normSquared());
        System.out.println("orientation(A,B,C) = "
                + direction(a, b, c));
        System.out.println("twice triangle area = "
                + orient(a, b, c).abs());
        System.out.println("(2,0) on AB = "
                + onSegment(a, b, new Point(2, 0)));
        System.out.println("(5,0) on AB = "
                + onSegment(a, b, new Point(5, 0)));

        printKind("Proper",
                new Point(0, 0), new Point(4, 4),
                new Point(0, 4), new Point(4, 0));
        printKind("Touch",
                new Point(0, 0), new Point(4, 0),
                new Point(4, 0), new Point(4, 5));
        printKind("Overlap",
                new Point(0, 0), new Point(5, 0),
                new Point(2, 0), new Point(8, 0));
        printKind("Disjoint",
                new Point(0, 0), new Point(2, 0),
                new Point(3, 0), new Point(5, 0));
        printKind("Point segment",
                new Point(2, 0), new Point(2, 0),
                new Point(0, 0), new Point(4, 0));

        RationalPoint intersection = lineIntersection(
                new Point(0, 0), new Point(3, 3),
                new Point(0, 3), new Point(3, 0));
        System.out.println("rational intersection = "
                + intersection);

        BigInteger extreme = orient(
                new Point(Long.MIN_VALUE, 0),
                new Point(Long.MAX_VALUE, 0),
                new Point(0, Long.MAX_VALUE));
        System.out.println("extreme cross bitLength = "
                + extreme.bitLength());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ExactGeometryPredicatesDemo.java
java ExactGeometryPredicatesDemo
```

Stdout:

```text
dot(u,v) = 0
cross(u,v) = 25
|u|^2 = 25
orientation(A,B,C) = CCW
twice triangle area = 12
(2,0) on AB = true
(5,0) on AB = false
Proper: PROPER
Touch: TOUCH
Overlap: OVERLAP
Disjoint: NONE
Point segment: TOUCH
rational intersection = (3/2, 3/2)
extreme cross bitLength = 127
```

### 8.1. Không nhầm nhân dấu với nhân định thức

`o1,o2,o3,o4` trong Java là **-1,0,+1** lấy bằng `signum()`. Do đó `o1*o2` không tràn. Nếu thay bằng tích của chính các số cross lớn dưới dạng int/long, có thể overflow và đảo kết quả.

### 8.2. Đường vô hạn và đoạn hữu hạn khác nhau

`lineIntersection` chỉ trả một giao điểm khi hai đường không song song; nó có thể nằm ngoài hai đoạn. Để biết giao của **hai đoạn**, cần gọi `classify` hoặc so 0≤t,u≤1; nếu hai đoạn `OVERLAP`, kết quả là **một đoạn**, không phải một RationalPoint.

### 8.3. Ví dụ vượt miền long

Hiệu `Long.MAX_VALUE−Long.MIN_VALUE=2^64−1` đã vượt long. Ví dụ cuối có cross lớn dương và `bitLength=127`, minh họa vì sao chuyển `BigInteger` **sau** khi long bị tràn là không đủ.

## 9. Số thực và độ chính xác

Đối với dữ liệu **nguyên**, ta có thể quyết định dấu định thức **chính xác** bằng BigInteger. Đối với tọa độ từ sensor, đồ họa, GIS hoặc mô phỏng có giá trị **double**, phép toán IEEE 754 sẽ có sai số làm tròn.

Ví dụ:

`0.1+0.2 != 0.3`

trong so sánh `==` thông thường, dù biểu diễn thập phân gợi ý hai vế bằng nhau.

### 9.1. EPS không phải quy tắc tổng quát

Một phép so xấp xỉ hữu ích:

`|x−y| ≤ absTol + relTol·max(|x|,|y|)`,

với tol phụ thuộc đơn vị và độ lớn. Nhưng `orient` là tích có hướng có **đơn vị diện tích**, nên dùng `abs(cross)<=1e-9` cho mọi thang đo không phải cách kiểm hướng hình học đáng tin cậy.

Với các quyết định tổ hợp như có giao/có thẳng hàng, dữ liệu nguyên nên dùng số học **exact**. Với dữ liệu double gần suy biến có thể cần **robust/adaptive predicates**, không đơn giản chọn EPS tuyệt đối tùy ý.

### 9.2. Tính khoảng cách tốt hơn với hypot

Với double, `Math.sqrt(dx*dx+dy*dy)` có thể overflow hoặc underflow ở cực trị. `Math.hypot(dx,dy)` thường ổn định hơn. Dù vậy, nếu hiệu tọa độ đã bị làm tròn hoặc biến thành Infinity, không có công thức nào tự khôi phục thông tin đã mất.

### 9.3. Hình học Euclid và tọa độ địa lý

Khoảng cách trong hệ tọa độ kinh độ/vĩ độ không phải khoảng cách phẳng theo đơn vị mét. Cần lựa chọn mô hình địa lý/phép chiếu thích hợp. Các công thức trong bài giả định **mặt phẳng Descartes** và đơn vị thống nhất.

### 9.4. Dữ liệu không hữu hạn

Nếu đầu vào `NaN` hoặc `Infinity`, các phép so và nhân double có thể ra kết quả vô nghĩa. Khi nhận dữ liệu từ bên ngoài, kiểm `Double.isFinite` và xử lý đầu vào không hợp lệ trước khi dùng hình học.

## 10. Khoảng cách và hình chiếu

Cho A,B,P với A≠B, r=B−A.

**Khoảng cách P tới đường AB vô hạn**:

`distanceLine = |cross(r,P−A)| / |r|`.

**Chân gần nhất trên đoạn đóng AB**:

`t = dot(P−A,r)/dot(r,r)`,

`t_segment = max(0,min(1,t))`,

`H = A+t_segment·r`.

**Khoảng cách P tới đoạn**:

`distanceSegment = |P−H|`.

Nếu A=B, đoạn chỉ chứa A và khoảng cách là |P−A|. Đường thẳng qua hai điểm trùng nhau không xác định duy nhất; API khoảng cách **tới đường** nên ném lỗi thay vì chia cho 0.

### 10.1. Hai ví dụ

A=(0,0), B=(4,0), P=(2,3):

`t=0.5`, H=(2,0), cả khoảng cách tới đoạn và tới đường đều là **3**.

Q=(6,3):

`t=1.5`, chân chiếu trên đường là (6,0), **ngoài đoạn**. Chân gần nhất trên đoạn là B=(4,0):

`distanceSegment(Q,AB)=√13≈3.605551`, nhưng `distanceLine(Q,AB)=3`.

Đây là lỗi thường gặp nhất khi tính khoảng cách tới đoạn: quên **clamp** tham số.

### 10.2. Đoạn suy biến

A=B=(1,2), P=(4,6):

`distanceSegment=√(3²+4²)=5`.

Không tính t bằng mẫu `|AB|²=0`. Chân gần nhất luôn bằng A.

## 11. Java 17 — khoảng cách, chân chiếu và số thực

Lưu **MetricGeometryDemo.java**:

```java
import java.util.Locale;

public class MetricGeometryDemo {
    record Point(double x, double y) {}

    static double dot(double ax, double ay,
                      double bx, double by) {
        return ax * bx + ay * by;
    }

    static Point nearestOnSegment(Point p, Point a, Point b) {
        double dx = b.x() - a.x();
        double dy = b.y() - a.y();
        double lengthSquared = dot(dx, dy, dx, dy);

        if (lengthSquared == 0.0) return a;

        double t = dot(p.x() - a.x(), p.y() - a.y(),
                       dx, dy) / lengthSquared;
        t = Math.max(0.0, Math.min(1.0, t));
        return new Point(a.x() + t * dx, a.y() + t * dy);
    }

    static double distanceSegment(Point p, Point a, Point b) {
        Point foot = nearestOnSegment(p, a, b);
        return Math.hypot(p.x() - foot.x(), p.y() - foot.y());
    }

    static double distanceLine(Point p, Point a, Point b) {
        double dx = b.x() - a.x();
        double dy = b.y() - a.y();
        double length = Math.hypot(dx, dy);
        if (length == 0.0) {
            throw new IllegalArgumentException(
                    "Line requires distinct points");
        }

        double cross = dx * (p.y() - a.y())
                - dy * (p.x() - a.x());
        return Math.abs(cross) / length;
    }

    static boolean approximatelyEqual(double x, double y) {
        final double absTol = 1e-12;
        final double relTol = 1e-12;
        return Math.abs(x - y) <= absTol
                + relTol * Math.max(Math.abs(x), Math.abs(y));
    }

    public static void main(String[] args) {
        Point a = new Point(0, 0), b = new Point(4, 0);
        Point p = new Point(2, 3), q = new Point(6, 3);
        Point footP = nearestOnSegment(p, a, b);

        System.out.printf(Locale.ROOT,
                "P foot=(%.1f,%.1f), segment=%.6f, line=%.6f%n",
                footP.x(), footP.y(),
                distanceSegment(p, a, b),
                distanceLine(p, a, b));

        Point footQ = nearestOnSegment(q, a, b);
        System.out.printf(Locale.ROOT,
                "Q foot=(%.1f,%.1f), segment=%.6f, line=%.6f%n",
                footQ.x(), footQ.y(),
                distanceSegment(q, a, b),
                distanceLine(q, a, b));

        Point same = new Point(1, 2);
        Point outside = new Point(4, 6);
        System.out.printf(Locale.ROOT,
                "Degenerate segment distance=%.6f%n",
                distanceSegment(outside, same, same));

        try {
            distanceLine(outside, same, same);
        } catch (IllegalArgumentException e) {
            System.out.println("Degenerate line rejected: true");
        }

        double sum = 0.1 + 0.2;
        System.out.println("0.1+0.2==0.3: " + (sum == 0.3));
        System.out.println("approximatelyEqual: "
                + approximatelyEqual(sum, 0.3));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 MetricGeometryDemo.java
java MetricGeometryDemo
```

Stdout:

```text
P foot=(2.0,0.0), segment=3.000000, line=3.000000
Q foot=(4.0,0.0), segment=3.605551, line=3.000000
Degenerate segment distance=5.000000
Degenerate line rejected: true
0.1+0.2==0.3: false
approximatelyEqual: true
```

**Giới hạn:** Đây là ví dụ double dùng tọa độ vừa phải. `lengthSquared` có thể overflow/underflow với trị rất lớn/nhỏ; code sản xuất phải validate đầu vào hoặc dùng công thức có kiểm soát số học. **Đừng dùng** chính epsilon của metric demo làm quyết định chắc chắn cho orient/giao đoạn nguyên.

## 12. Diện tích đa giác: công thức dây giày

Cho đa giác đơn gồm các đỉnh tuần tự:

`P0=(x0,y0),...,P(n−1)=(x(n−1),y(n−1))`.

Tổng định thức:

`S = Σ_i [xi·y(i+1) − yi·x(i+1)]`

với chỉ số `i+1` lấy modulo n, tức có cả cạnh **cuối về đầu**.

Diện tích không âm:

`Area=|S|/2`.

`S` chính là **hai lần diện tích có dấu**:

- Đỉnh CCW ⇒ S>0 khi đa giác không suy biến.
- Đỉnh CW ⇒ S<0.
- Đảo chiều vòng đỉnh ⇒ S đổi dấu nhưng |S|/2 giữ nguyên.

### 12.1. Ví dụ hình vuông

`(0,0),(2,0),(2,2),(0,2)` cho:

`S=0+4+4+0=8`.

Vậy diện tích bằng4. Nếu đảo thứ tự đỉnh, S=-8 và diện tích vẫn4.

### 12.2. Ví dụ đa giác lõm

`(0,0),(6,0),(6,6),(3,3),(0,6)` cho S=54, diện tích **27**. Công thức shoelace vẫn đúng với **đa giác đơn lõm**.

Nếu đa giác **tự cắt**, công thức cho diện tích **đại số có dấu** theo đường biên, không nhất thiết là diện tích phần hợp hình mà người dùng tưởng tượng. Cần định nghĩa mô hình vùng riêng.

## 13. Điểm trong đa giác: INSIDE / OUTSIDE / BOUNDARY

Với **đa giác đơn không tự cắt**, điểm Q có ba trạng thái:

- `BOUNDARY`: trùng đỉnh hoặc nằm trên cạnh.
- `INSIDE`: trong miền được khép bởi đa giác.
- `OUTSIDE`: ngoài.

Một cách kiểm tra phổ biến là **ray casting / even–odd rule**: bắn tia ngang từ Q sang phải; nếu số lần cắt cạnh lẻ thì INSIDE, nếu chẵn thì OUTSIDE.

### 13.1. Kiểm BOUNDARY trước

Trước khi đếm giao tia, duyệt các cạnh AB và dùng `onSegment(A,B,Q)`. Nếu đúng, trả BOUNDARY ngay.

Nếu không làm bước này, trường hợp Q trùng đỉnh hoặc nằm ngang trên một cạnh có thể bị phân loại tùy chi tiết đếm giao của tia.

### 13.2. Quy tắc nửa mở ở y

Một cạnh AB cắt mức ngang `y=qy` khi:

`(A.y>Q.y) != (B.y>Q.y)`.

Đây là phép thử **nửa mở**, tránh đếm đôi một đỉnh chung giữa hai cạnh. Cạnh nằm ngang sẽ không được đếm như giao tia, vì trường hợp Q nằm trên cạnh đã được xử lý BOUNDARY.

Để kiểm giao này có nằm **bên phải Q** không, không cần chia số thực:

- Cạnh đi lên (`B.y>A.y`) thì `orient(A,B,Q)>0` nghĩa giao tia nằm ở bên phải Q.
- Cạnh đi xuống (`B.y<A.y`) thì `orient(A,B,Q)<0` nghĩa giao tia nằm bên phải Q.

Vậy có thể chỉ dùng **dấu cross BigInteger** để toggle parity.

### 13.3. Ví dụ hình chữ nhật

Đa giác `(0,0),(6,0),(6,4),(0,4)`:

| Q | Kết quả |
|---|---|
| (3,2) | INSIDE |
| (6,2) | BOUNDARY |
| (7,2) | OUTSIDE |
| (0,0) | BOUNDARY |

Đảo chiều danh sách đỉnh **không** đổi loại điểm.

### 13.4. Ví dụ đa giác lõm

Đa giác `(0,0),(6,0),(6,6),(3,3),(0,6)`:

- Q=(3,2) ⇒ INSIDE.
- Q=(3,5) ⇒ OUTSIDE (trong khe lõm, dù nằm trong bbox).
- Q=(4,4) ⇒ BOUNDARY trên cạnh chéo.

Vì vậy **bbox không đủ** để kết luận điểm trong đa giác lõm.

### 13.5. Giới hạn mô hình

- Code giả định **đa giác đơn** có ít nhất ba đỉnh.
- Đa giác tự cắt có nhiều định nghĩa tô vùng, như even–odd và nonzero winding; kết quả có thể khác.
- Đa giác có **lỗ** cần mô tả nhiều vòng biên và quy tắc tương ứng.
- Nếu input nhiều cạnh trùng hoặc polygon suy biến, cần validate trước thay vì mặc định đây là vùng đơn hợp lệ.

## 14. Bao lồi (*convex hull*) bằng Andrew monotone chain

Bao lồi là tập lồi nhỏ nhất chứa mọi điểm. Với tập hữu hạn điểm 2D, có thể trả các đỉnh biên lồi theo thứ tự CCW.

**Andrew monotone chain**:

1. Sắp các điểm theo `(x,y)` tăng, loại điểm trùng.
2. Duyệt trái sang phải xây **lower hull**.
3. Duyệt phải sang trái xây **upper hull**.
4. Khi thêm điểm mới, nếu ba đỉnh cuối không tạo **rẽ trái nghiêm ngặt** (`orient≤0`), bỏ đỉnh giữa rồi thử lại.
5. Ghép hai nửa, không lặp các đầu mút.

### 14.1. Vì sao dùng orient≤0?

`orient<0` là quay phải khiến chuỗi đang xây không còn lồi đúng chiều. `orient=0` nghĩa ba điểm collinear: nếu chỉ muốn **đỉnh cực trị**, điểm giữa trên cùng cạnh không cần giữ.

Với convention này:

- Các điểm nằm trong một cạnh hull bị loại.
- Nếu mọi điểm collinear, hull chứa **hai đầu mút**.
- Nếu cần liệt kê **mọi điểm trên biên**, thuật toán và việc loại trùng phải điều chỉnh, không đổi dấu một cách tùy tiện.

### 14.2. Ví dụ có điểm trùng và điểm nội bộ

Input:

`(0,0),(2,0),(2,2),(0,2),(1,1),(2,0),(1,0),(1,2)`.

Hull CCW:

`(0,0),(2,0),(2,2),(0,2)`.

Điểm (1,1) nằm trong, (1,0)/(1,2) trên cạnh, (2,0) bị lặp: chúng không là đỉnh cực trị mới.

### 14.3. Trường hợp suy biến

- n=0 ⇒ hull rỗng.
- Chỉ một tọa độ phân biệt ⇒ hull một điểm.
- Hai tọa độ phân biệt ⇒ hull hai điểm.
- Tất cả collinear ⇒ hai đầu mút cực trị.
- Duplicate points ⇒ loại trùng trước khi xây.

### 14.4. Độ phức tạp

Sort n điểm: O(n log n).

Mỗi điểm được thêm và xóa khỏi mỗi chuỗi hull tối đa hằng số lần: O(n) sau sort.

Tổng **O(n log n)** so sánh, O(n) bộ nhớ điểm/hull. Với tọa độ rất lớn, mỗi phép orientation BigInteger có thêm chi phí số học theo số bit.

## 15. Java 17 — bao lồi, shoelace và ray casting exact

Chương trình này sử dụng **một predicate orient BigInteger** nhất quán cho ba phép: dựng bao lồi, tính diện tích, kiểm điểm trong/ngoài/trên biên đa giác.

Lưu **HullAndPolygonGeometryDemo.java**:

```java
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.TreeSet;
import java.util.StringJoiner;

public class HullAndPolygonGeometryDemo {
    record Point(long x, long y) {}
    enum Location { INSIDE, OUTSIDE, BOUNDARY }

    static final Comparator<Point> LEX =
            Comparator.comparingLong(Point::x)
                    .thenComparingLong(Point::y);

    static BigInteger bi(long n) {
        return BigInteger.valueOf(n);
    }

    static BigInteger orient(Point a, Point b, Point c) {
        BigInteger abx = bi(b.x()).subtract(bi(a.x()));
        BigInteger aby = bi(b.y()).subtract(bi(a.y()));
        BigInteger acx = bi(c.x()).subtract(bi(a.x()));
        BigInteger acy = bi(c.y()).subtract(bi(a.y()));
        return abx.multiply(acy).subtract(aby.multiply(acx));
    }

    static boolean between(long a, long b, long p) {
        return Math.min(a, b) <= p && p <= Math.max(a, b);
    }

    static boolean onSegment(Point a, Point b, Point p) {
        return orient(a, b, p).signum() == 0
                && between(a.x(), b.x(), p.x())
                && between(a.y(), b.y(), p.y());
    }

    static List<Point> convexHull(List<Point> points) {
        TreeSet<Point> unique = new TreeSet<>(LEX);
        unique.addAll(points);
        List<Point> sorted = new ArrayList<>(unique);
        if (sorted.size() <= 1) return sorted;

        List<Point> lower = new ArrayList<>();
        for (Point p : sorted) {
            while (lower.size() >= 2
                    && orient(lower.get(lower.size() - 2),
                              lower.get(lower.size() - 1), p)
                              .signum() <= 0) {
                lower.remove(lower.size() - 1);
            }
            lower.add(p);
        }

        List<Point> upper = new ArrayList<>();
        for (int i = sorted.size() - 1; i >= 0; i--) {
            Point p = sorted.get(i);
            while (upper.size() >= 2
                    && orient(upper.get(upper.size() - 2),
                              upper.get(upper.size() - 1), p)
                              .signum() <= 0) {
                upper.remove(upper.size() - 1);
            }
            upper.add(p);
        }

        lower.remove(lower.size() - 1);
        upper.remove(upper.size() - 1);
        lower.addAll(upper);
        return lower;
    }

    static BigInteger signedTwiceArea(List<Point> polygon) {
        BigInteger sum = BigInteger.ZERO;
        if (polygon.size() < 3) return sum;
        for (int i = 0; i < polygon.size(); i++) {
            Point a = polygon.get(i);
            Point b = polygon.get((i + 1) % polygon.size());
            sum = sum.add(bi(a.x()).multiply(bi(b.y()))
                    .subtract(bi(a.y()).multiply(bi(b.x()))));
        }
        return sum;
    }

    static Location locate(List<Point> polygon, Point p) {
        if (polygon.size() < 3) {
            throw new IllegalArgumentException(
                    "A polygon needs at least 3 vertices");
        }
        boolean inside = false;
        for (int i = 0; i < polygon.size(); i++) {
            Point a = polygon.get(i);
            Point b = polygon.get((i + 1) % polygon.size());

            if (onSegment(a, b, p)) return Location.BOUNDARY;

            boolean crosses = (a.y() > p.y()) != (b.y() > p.y());
            if (crosses) {
                int sign = orient(a, b, p).signum();
                boolean right = b.y() > a.y()
                        ? sign > 0 : sign < 0;
                if (right) inside = !inside;
            }
        }
        return inside ? Location.INSIDE : Location.OUTSIDE;
    }

    static String display(List<Point> points) {
        StringJoiner out = new StringJoiner(" ");
        for (Point p : points) {
            out.add("(" + p.x() + "," + p.y() + ")");
        }
        return out.toString();
    }

    public static void main(String[] args) {
        List<Point> cloud = List.of(
                new Point(0, 0), new Point(2, 0),
                new Point(2, 2), new Point(0, 2),
                new Point(1, 1), new Point(2, 0),
                new Point(1, 0), new Point(1, 2));
        List<Point> hull = convexHull(cloud);
        System.out.println("Hull: " + display(hull));
        System.out.println("Hull signed twice area: "
                + signedTwiceArea(hull));

        List<Point> rectangle = List.of(
                new Point(0, 0), new Point(6, 0),
                new Point(6, 4), new Point(0, 4));
        System.out.println("Rectangle twice area: "
                + signedTwiceArea(rectangle));
        System.out.println("Rectangle (3,2): "
                + locate(rectangle, new Point(3, 2)));
        System.out.println("Rectangle (6,2): "
                + locate(rectangle, new Point(6, 2)));
        System.out.println("Rectangle (7,2): "
                + locate(rectangle, new Point(7, 2)));
        System.out.println("Rectangle (0,0): "
                + locate(rectangle, new Point(0, 0)));

        List<Point> reversed = new ArrayList<>(rectangle);
        Collections.reverse(reversed);
        System.out.println("Reversed rectangle twice area: "
                + signedTwiceArea(reversed));
        System.out.println("Reversed rectangle (3,2): "
                + locate(reversed, new Point(3, 2)));

        List<Point> concave = List.of(
                new Point(0, 0), new Point(6, 0),
                new Point(6, 6), new Point(3, 3),
                new Point(0, 6));
        System.out.println("Concave twice area: "
                + signedTwiceArea(concave));
        System.out.println("Concave (3,2): "
                + locate(concave, new Point(3, 2)));
        System.out.println("Concave (3,5): "
                + locate(concave, new Point(3, 5)));
        System.out.println("Concave (4,4): "
                + locate(concave, new Point(4, 4)));

        List<Point> collinear = List.of(
                new Point(0, 0), new Point(1, 1),
                new Point(2, 2), new Point(1, 1));
        System.out.println("Collinear hull: "
                + display(convexHull(collinear)));
        System.out.println("Empty hull size: "
                + convexHull(List.of()).size());
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 HullAndPolygonGeometryDemo.java
java HullAndPolygonGeometryDemo
```

Stdout:

```text
Hull: (0,0) (2,0) (2,2) (0,2)
Hull signed twice area: 8
Rectangle twice area: 48
Rectangle (3,2): INSIDE
Rectangle (6,2): BOUNDARY
Rectangle (7,2): OUTSIDE
Rectangle (0,0): BOUNDARY
Reversed rectangle twice area: -48
Reversed rectangle (3,2): INSIDE
Concave twice area: 54
Concave (3,2): INSIDE
Concave (3,5): OUTSIDE
Concave (4,4): BOUNDARY
Collinear hull: (0,0) (2,2)
Empty hull size: 0
```

### 15.1. Vì sao hull có thứ tự CCW?

Sắp theo x rồi xây lower và upper bằng phép bỏ các lượt rẽ không trái. Nếu có ba đỉnh không collinear, output hull theo thứ tự CCW, nên `signedTwiceArea(hull)` dương.

### 15.2. Vì sao PIP không cần tính tọa độ giao tia bằng double?

Chỉ cần biết một cạnh đang cắt ngang mức y của điểm, và giao cắt nằm bên phải điểm hay không. Với tọa độ nguyên, **dấu orientation BigInteger** đủ để quyết định, loại bỏ sai số từ phép chia x giao tia.

### 15.3. Đa giác suy biến và tự cắt

Nếu danh sách đỉnh không mô tả một đa giác đơn, kết quả INSIDE/OUTSIDE có thể phụ thuộc định nghĩa. Code demo kiểm `n>=3` nhưng không tự chứng minh biên là đơn; trong hệ thống sản xuất nên validate polygon trước.

## 16. Oracle độc lập cho giao đoạn bằng tham số hữu tỉ

Để kiểm một hàm `classify` dựa vào bốn orientation, ta có thể so với một **cài đặt khác** dựa trên giao điểm hai đường.

Cho r=B−A, s=D−C, w=C−A, `den=cross(r,s)`.

### 16.1. Nếu den khác0

Đặt:

`tNum=cross(w,s)`, `uNum=cross(w,r)`.

Chuẩn hóa nếu den âm thì đổi dấu cả den,tNum,uNum để den>0.

- Nếu tNum<0, tNum>den, uNum<0 hoặc uNum>den ⇒ `NONE`.
- Nếu `0<tNum<den` và `0<uNum<den` ⇒ `PROPER`.
- Nếu trong hai khoảng đóng [0,den] nhưng có chạm biên ⇒ `TOUCH`.

Không hề có `double` hoặc phép chia có sai số: chỉ so **BigInteger**.

### 16.2. Nếu den=0

Hai vectơ hướng song song:

- Nếu `cross(r,w)≠0`: hai đường khác nhau ⇒ `NONE`.
- Nếu cùng đường: dùng giao khoảng đầu mút như phần6.

Nếu một đoạn là **một điểm** (A=B hoặc C=D), phải xử lý bằng so điểm hoặc `onSegment` trước vì r=0 làm denominator0 cho mọi s.

### 16.3. Vì sao đây là oracle hữu ích?

Hàm chính phân tích **dấu của bốn orient**. Oracle này dùng **giải tham số t,u của hai đường**. Hai suy luận khác nhau, nên có thể bắt lỗi ở điều kiện biên của nhau.

Đừng chỉ so boolean “có giao” vì các kết quả `PROPER`, `TOUCH`, `OVERLAP` đều true nhưng mang ý nghĩa khác. So **chính xác từng enum**.

## 17. Java 17 — differential test 2.000 cặp đoạn

Chương trình sau có hai cài đặt:

- `byOrientation`: bốn orient, điểm trên đoạn, giao khoảng collinear.
- `byRationalParameters`: giải tham số BigInteger; xử lý riêng đoạn điểm.

Nó đối chiếu **mọi loại giao**, kiểm đổi vai đoạn và đảo đầu mút, trên 7 case cố định và 2.000 case ngẫu nhiên tái lập.

Lưu **SegmentIntersectionOracleDemo.java**:

```java
import java.math.BigInteger;
import java.util.Random;

public class SegmentIntersectionOracleDemo {
    record Point(long x, long y) {}
    record Vector(BigInteger x, BigInteger y) {
        BigInteger cross(Vector b) {
            return x.multiply(b.y).subtract(y.multiply(b.x));
        }
    }
    enum Kind { NONE, PROPER, TOUCH, OVERLAP }

    static Vector delta(Point a, Point b) {
        return new Vector(
                BigInteger.valueOf(b.x()).subtract(
                        BigInteger.valueOf(a.x())),
                BigInteger.valueOf(b.y()).subtract(
                        BigInteger.valueOf(a.y())));
    }

    static BigInteger orient(Point a, Point b, Point c) {
        return delta(a, b).cross(delta(a, c));
    }

    static int cmp(Point a, Point b) {
        int x = Long.compare(a.x(), b.x());
        return x != 0 ? x : Long.compare(a.y(), b.y());
    }

    static Point min(Point a, Point b) {
        return cmp(a, b) <= 0 ? a : b;
    }
    static Point max(Point a, Point b) {
        return cmp(a, b) >= 0 ? a : b;
    }
    static boolean between(long a, long b, long p) {
        return Math.min(a, b) <= p && p <= Math.max(a, b);
    }
    static boolean onSegment(Point a, Point b, Point p) {
        return orient(a, b, p).signum() == 0
                && between(a.x(), b.x(), p.x())
                && between(a.y(), b.y(), p.y());
    }

    static Kind collinearOverlap(
            Point a, Point b, Point c, Point d) {
        Point lo = max(min(a, b), min(c, d));
        Point hi = min(max(a, b), max(c, d));
        int rel = cmp(lo, hi);
        return rel > 0 ? Kind.NONE
                : rel == 0 ? Kind.TOUCH : Kind.OVERLAP;
    }

    static Kind byOrientation(
            Point a, Point b, Point c, Point d) {
        int o1 = orient(a, b, c).signum();
        int o2 = orient(a, b, d).signum();
        int o3 = orient(c, d, a).signum();
        int o4 = orient(c, d, b).signum();

        if (o1 == 0 && o2 == 0 && o3 == 0 && o4 == 0) {
            return collinearOverlap(a, b, c, d);
        }
        if (o1 * o2 < 0 && o3 * o4 < 0) return Kind.PROPER;

        if ((o1 == 0 && onSegment(a, b, c))
                || (o2 == 0 && onSegment(a, b, d))
                || (o3 == 0 && onSegment(c, d, a))
                || (o4 == 0 && onSegment(c, d, b))) {
            return Kind.TOUCH;
        }
        return Kind.NONE;
    }

    static Kind byRationalParameters(
            Point a, Point b, Point c, Point d) {
        if (a.equals(b) && c.equals(d)) {
            return a.equals(c) ? Kind.TOUCH : Kind.NONE;
        }
        if (a.equals(b)) {
            return onSegment(c, d, a) ? Kind.TOUCH : Kind.NONE;
        }
        if (c.equals(d)) {
            return onSegment(a, b, c) ? Kind.TOUCH : Kind.NONE;
        }

        Vector r = delta(a, b);
        Vector s = delta(c, d);
        Vector w = delta(a, c);
        BigInteger den = r.cross(s);

        if (den.signum() == 0) {
            return r.cross(w).signum() == 0
                    ? collinearOverlap(a, b, c, d) : Kind.NONE;
        }

        BigInteger t = w.cross(s);
        BigInteger u = w.cross(r);
        if (den.signum() < 0) {
            den = den.negate();
            t = t.negate();
            u = u.negate();
        }

        BigInteger zero = BigInteger.ZERO;
        if (t.compareTo(zero) < 0 || t.compareTo(den) > 0
                || u.compareTo(zero) < 0 || u.compareTo(den) > 0) {
            return Kind.NONE;
        }

        boolean strictT = t.signum() > 0 && t.compareTo(den) < 0;
        boolean strictU = u.signum() > 0 && u.compareTo(den) < 0;
        return strictT && strictU ? Kind.PROPER : Kind.TOUCH;
    }

    static void check(Point a, Point b, Point c, Point d) {
        Kind first = byOrientation(a, b, c, d);
        Kind second = byRationalParameters(a, b, c, d);
        Kind swapped = byOrientation(c, d, a, b);
        Kind reversed = byOrientation(b, a, d, c);
        if (first != second || first != swapped
                || first != reversed) {
            throw new IllegalStateException(
                    "Mismatch " + a + b + c + d
                    + ": orient=" + first + " rational=" + second);
        }
    }

    static Point randomPoint(Random rng) {
        return new Point(rng.nextInt(21) - 10,
                         rng.nextInt(21) - 10);
    }

    public static void main(String[] args) {
        Point p00 = new Point(0, 0);
        Point p40 = new Point(4, 0);
        check(p00, new Point(4, 4),
                new Point(0, 4), new Point(4, 0));
        check(p00, p40, p40, new Point(4, 5));
        check(p00, new Point(5, 0),
                new Point(2, 0), new Point(8, 0));
        check(p00, new Point(2, 0),
                new Point(3, 0), new Point(5, 0));
        check(new Point(2, 0), new Point(2, 0),
                p00, p40);
        check(new Point(2, 1), new Point(2, 1),
                p00, p40);
        check(new Point(2, 1), new Point(2, 1),
                new Point(2, 1), new Point(2, 1));

        System.out.println("Fixed segment cases: 7");

        Random random = new Random(4182026L);
        int cases = 2000;
        for (int i = 0; i < cases; i++) {
            Point a = randomPoint(random);
            Point b = randomPoint(random);
            Point c = randomPoint(random);
            Point d = randomPoint(random);
            check(a, b, c, d);
        }

        System.out.println("Random segment cases: " + cases);
        System.out.println("All exact classifications agree: true");
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 SegmentIntersectionOracleDemo.java
java SegmentIntersectionOracleDemo
```

Stdout:

```text
Fixed segment cases: 7
Random segment cases: 2000
All exact classifications agree: true
```

### 17.1. Vì sao riêng xử lý đoạn suy biến?

Nếu A=B thì r=0, làm `den=cross(r,s)=0` cho mọi s. Hai điểm trùng nhau không xác định một đường thẳng riêng; phải so điểm trực tiếp hoặc kiểm `onSegment` trên đoạn còn lại.

### 17.2. Vì sao không thể chỉ vét các điểm lưới nguyên?

Giao hai đoạn với đầu mút nguyên có thể có tọa độ **phân số** như (3/2,3/2). Một oracle thử duy nhất các điểm có x,y nguyên có thể **bỏ sót giao thực sự**. Phương pháp tham số hữu tỉ tránh lỗi này.

### 17.3. Kiểm bất biến

Giao của AB và CD không phụ thuộc thứ tự hai đoạn hoặc chiều kê đầu mút. Nếu hai hàm trả khác nhau sau hoán đổi, thường đã sai dấu định thức hoặc xử lý endpoint.

## 18. Kiểm thử đa giác và hull bằng phương pháp khác

Ngoài hai cách xác định giao đoạn, có những phép kiểm độc lập hữu ích:

### 18.1. Orient bằng định thức khai triển

So:

`(bx−ax)(cy−ay)−(by−ay)(cx−ax)`

với:

`ax(by−cy)+bx(cy−ay)+cx(ay−by)`.

Thử cả tọa độ cực trị, và bất biến `orient(A,B,C)=−orient(A,C,B)`.

### 18.2. Hull bằng Jarvis march

Với tập điểm nhỏ, dùng một thuật toán **gift wrapping/Jarvis march** độc lập để so đỉnh hull với Andrew monotone chain:

- Chọn điểm nhỏ nhất theo từ điển.
- Chọn điểm tiếp theo để mọi điểm còn lại ở **cùng phía trái** của cạnh; nếu collinear, chọn điểm xa nhất.
- Lặp đến khi về điểm đầu.

Cần cùng convention **bỏ điểm collinear trung gian**. Hai thuật toán nên trả cùng đỉnh hull CCW (hoặc ít nhất cùng tập đỉnh sau chuẩn hóa).

### 18.3. Point-in-polygon bằng winding number

Với đa giác **đơn**, phương pháp ray casting parity và **winding number** nên đồng ý về inside/outside nếu đã xử lý boundary riêng. Trên đa giác tự cắt, hai quy tắc có thể khác; không nên dùng test đó khi giả định đa giác đơn bị vi phạm.

### 18.4. Đảo thứ tự đỉnh

Đảo thứ tự đỉnh của một đa giác đơn:

- `signedTwiceArea` đổi dấu.
- Diện tích không dấu giữ nguyên.
- Point-in-polygon cho cùng INSIDE/OUTSIDE/BOUNDARY.

### 18.5. Dịch chuyển đồng loạt

Thêm t vào tất cả điểm không đổi orientation, giao, diện tích và khoảng cách Euclid. Có thể sinh hàng nghìn test từ một hình bằng phép dịch chuyển.

## 19. Các lỗi triển khai thường gặp

### Lỗi 1 — Nhầm điểm và vectơ

Điểm là vị trí, vectơ là độ dời. Phép B−A phải cho vectơ, không phải một điểm có gốc tùy ý.

### Lỗi 2 — Dùng sai quy ước trục y

Toán học chuẩn y hướng lên, màn hình thường y hướng xuống; CCW/CW có thể đảo so với hình vẽ.

### Lỗi 3 — Đảo toán hạng cross

`cross(B−A,C−A)` và `cross(C−A,B−A)` trái dấu.

### Lỗi 4 — Lấy abs(cross) trước khi kiểm hướng

Abs làm mất dấu phân biệt bên trái/bên phải.

### Lỗi 5 — Dùng long nhân định thức lớn

Sản phẩm hai hiệu tọa độ có thể overflow; BigInteger hoặc chặn miền an toàn.

### Lỗi 6 — Chuyển BigInteger sau khi trừ long

Trừ đã overflow trước khi chuyển; chuyển từng tọa độ trước khi trừ.

### Lỗi 7 — Nhân hai orientation lớn để tìm trái dấu

Có thể overflow; dùng `signum()` trước.

### Lỗi 8 — Kết luận dot0 luôn có góc90°

Vectơ không có dot0 với mọi vectơ nhưng góc không xác định.

### Lỗi 9 — Dùng sqrt khi chỉ cần so độ dài

So normSquared thay vì sqrt, miễn tính bình phương chính xác/đủ rộng.

### Lỗi 10 — Kiểm onSegment chỉ bằng orient0

Điểm có thể nằm ngoài đoạn trên đường kéo dài.

### Lỗi 11 — Kiểm onSegment chỉ bằng bbox

Điểm có thể trong bbox nhưng không thẳng hàng.

### Lỗi 12 — Loại đầu mút đoạn đóng

`TOUCH` tại đầu mút vẫn là giao.

### Lỗi 13 — Chỉ kiểm giao PROPER

Hai đoạn có thể TOUCH hoặc OVERLAP mà không có hai cặp dấu trái ngược nghiêm ngặt.

### Lỗi 14 — Coi mọi orient0 là giao

Phải kiểm bbox/khoảng. Thẳng hàng nhưng xa nhau là NONE.

### Lỗi 15 — Không phân biệt OVERLAP và TOUCH

OVERLAP có một đoạn chung dương; TOUCH chỉ một điểm.

### Lỗi 16 — Dùng giao đường vô hạn làm giao đoạn

Giao điểm hai đường có thể ở ngoài đoạn. Phải kiểm tham số t,u thuộc [0,1].

### Lỗi 17 — Chia cho cross r×s bằng0

Song song/trùng/đoạn suy biến không có một nghiệm giao đường duy nhất theo công thức phân số.

### Lỗi 18 — Ép giao phân số thành số nguyên

Giao có thể là 3/2; không dùng chia nguyên làm tròn nếu cần kết quả chính xác.

### Lỗi 19 — Dùng một EPS cho mọi trường hợp double

Đơn vị, thang đo và tính điều kiện khác nhau. Quyết định topology gần biên cần robust predicate.

### Lỗi 20 — So `double ==` cho kết quả đo

`0.1+0.2` và0.3 có thể không bằng đúng bit.

### Lỗi 21 — Quên kiểm NaN/Infinity

Phép so và đại số với các giá trị ấy có thể đánh lừa logic.

### Lỗi 22 — Trộn kinh độ/vĩ độ với tọa độ phẳng

Khoảng cách Euclid không trực tiếp cho mét trên địa cầu khi dùng kinh độ/vĩ độ thô.

### Lỗi 23 — Quên clamp hình chiếu khi tính khoảng cách tới đoạn

Chân chiếu trên đường vô hạn có thể ngoài đoạn; phải clamp t.

### Lỗi 24 — Chia cho normSquared0 khi A=B

Đoạn suy biến là một điểm; xử lý riêng.

### Lỗi 25 — Quên cạnh cuối→đầu trong shoelace

Công thức dùng chỉ số `(i+1)%n`, kể cả cạnh khép vòng.

### Lỗi 26 — Nhầm hai lần diện tích với diện tích

`S=2*areaSigned`; diện tích không âm là `abs(S)/2`.

### Lỗi 27 — Dùng bbox để kiểm điểm trong polygon lõm

Bbox là điều kiện cần nhưng không đủ.

### Lỗi 28 — PIP không kiểm boundary trước

Điểm nằm trên cạnh/đỉnh cần BOUNDARY, không phải inside/outside tùy giao tia.

### Lỗi 29 — Ray casting đếm đôi đỉnh

Dùng quy tắc nửa mở `(a.y>qy)!=(b.y>qy)`.

### Lỗi 30 — PIP đa giác tự cắt nhưng không quy định vùng

Even–odd và winding number có thể khác; phải định nghĩa theo đề.

### Lỗi 31 — Hull không loại trùng

Điểm trùng tạo cạnh suy biến và đỉnh lặp.

### Lỗi 32 — Hull collinear giữ sai quy ước

Nếu chỉ muốn các đỉnh cực trị, dùng `orient≤0`; nếu giữ mọi điểm trên biên, thay thuật toán có ý thức.

### Lỗi 33 — Hull n=0/1 bị truy cập sai chỉ số

Xử lý riêng trước khi bỏ điểm cuối ở hai nửa.

### Lỗi 34 — Quên all-collinear

Hull với nhiều điểm thẳng hàng thường chỉ cần hai đầu mút.

### Lỗi 35 — So boolean giao thay vì enum

PROPER, TOUCH, OVERLAP đều true về “có giao” nhưng mang thông tin khác.

### Lỗi 36 — Không kiểm đối xứng đoạn

Hoán đổi AB/CD hoặc đảo endpoints không được làm đổi loại giao.

### Lỗi 37 — Không kiểm tọa độ Long.MIN/MAX

Hiệu tọa độ có thể vượt long dù cả hai tọa độ hợp lệ.

### Lỗi 38 — Dùng exact và approximate lẫn lộn

Dot/khoảng cách đo có thể dùng double; orient/giao nguyên yêu cầu dấu chính xác. Tách hai lớp chức năng.

## 20. Bảng tình huống biên

| Đầu vào | Kết quả mong đợi |
|---|---|
| Ba điểm không thẳng hàng | orient dấu đúng |
| Ba điểm thẳng hàng | orient=0 |
| A=B | Đoạn điểm; onSegment chỉ đúng với P=A |
| C cùng đường kéo dài ngoài AB | onSegment=false |
| C trong bbox nhưng lệch đường AB | onSegment=false |
| Hai đoạn cắt trong lòng | PROPER |
| Hai đoạn gặp đầu mút | TOUCH |
| Hai đoạn chồng collinear dài dương | OVERLAP |
| Hai đoạn collinear tách nhau | NONE |
| Hai đoạn song song khác đường | NONE |
| Hai đoạn điểm ở cùng tọa độ | TOUCH |
| Hai đoạn điểm khác nhau | NONE |
| Giao hai đường tại (3/2,3/2) | Rational exact |
| Hai đường song song | Không có giao duy nhất |
| Long.MIN/MAX | BigInteger giữ dấu đúng |
| A=B khi tính khoảng cách đoạn | Khoảng cách tới A |
| Hình chiếu ngoài đoạn | Clamp t=0 hoặc1 |
| Polygon đảo chiều | PIP không đổi; diện tích có dấu đổi |
| Điểm trùng polygon vertex | BOUNDARY |
| Điểm trong bbox polygon lõm nhưng ngoài miền | OUTSIDE |
| Hull điểm trùng | Một đỉnh duy nhất |
| Hull all-collinear | Hai đầu mút cực trị |
| Hull có điểm nội bộ hoặc trên cạnh | Không thêm đỉnh thừa |
| Tọa độ double NaN/Infinity | Validate trước |

## 21. Bài tập có đáp án

### Bài 1 — Hiệu điểm

A=(1,2),B=(4,6), tìm AB.

**Đáp án:** (3,4).

### Bài 2 — Dot

u=(3,4),v=(-4,3), tính dot.

**Đáp án:** 0.

### Bài 3 — Cross

Với cùng u,v, tính cross.

**Đáp án:** 25, dương.

### Bài 4 — Norm

|u| với u=(3,4)?

**Đáp án:** 5; normSquared25.

### Bài 5 — Orientation

A=(0,0),B=(4,0),C=(2,3)?

**Đáp án:** orient12>0, CCW.

### Bài 6 — Diện tích tam giác

Tam giác ở bài5 có diện tích?

**Đáp án:** 6.

### Bài 7 — Point ngoài đoạn

P=(5,0) thuộc đoạn (0,0)–(4,0)?

**Đáp án:** không, dù thẳng hàng.

### Bài 8 — Bbox không đủ

P=(1,3) thuộc đoạn (0,0)–(4,4)?

**Đáp án:** không, vì không thẳng hàng.

### Bài 9 — Đầu mút đoạn đóng

P=(4,0) thuộc đoạn (0,0)–(4,0)?

**Đáp án:** có.

### Bài 10 — Đoạn suy biến

[A,A] với A=(2,0) chứa P=(2,0)?

**Đáp án:** có; P khác A thì không.

### Bài 11 — Proper intersection

(0,0)–(4,4) và (0,4)–(4,0)?

**Đáp án:** PROPER ở (2,2).

### Bài 12 — Touch intersection

(0,0)–(4,0) và (4,0)–(4,5)?

**Đáp án:** TOUCH ở (4,0).

### Bài 13 — Overlap

(0,0)–(5,0) và (2,0)–(8,0)?

**Đáp án:** OVERLAP trên (2,0)–(5,0).

### Bài 14 — Disjoint collinear

(0,0)–(2,0) và (3,0)–(5,0)?

**Đáp án:** NONE.

### Bài 15 — Giao hữu tỉ

y=x và y=3−x?

**Đáp án:** (3/2,3/2).

### Bài 16 — Mẫu cross0

Có thể dùng công thức chia để lấy một giao điểm đường duy nhất khi r×s=0?

**Đáp án:** không.

### Bài 17 — BigInteger

Vì sao `BigInteger.valueOf(bx-ax)` có thể sai?

**Đáp án:** long trừ bị overflow trước khi chuyển.

### Bài 18 — Đổi thứ tự cross

`cross(v,u)` bằng gì so với `cross(u,v)`?

**Đáp án:** đối dấu.

### Bài 19 — Hình chiếu

P=(2,3) tới đoạn (0,0)–(4,0) có chân?

**Đáp án:** (2,0), khoảng cách3.

### Bài 20 — Hình chiếu ngoài đoạn

Q=(6,3) tới cùng đoạn có khoảng cách?

**Đáp án:** √13≈3.605551, không phải3.

### Bài 21 — Degenerate distance

P=(4,6) tới đoạn [(1,2),(1,2)]?

**Đáp án:** 5.

### Bài 22 — Shoelace

Hình vuông (0,0),(2,0),(2,2),(0,2) có S và diện tích?

**Đáp án:** S=8, diện tích4.

### Bài 23 — Đảo chiều polygon

Đảo thứ tự đỉnh có đổi diện tích không dấu?

**Đáp án:** không; chỉ đảo dấu S.

### Bài 24 — Polygon lõm

Q=(3,5) trong bbox đa giác (0,0),(6,0),(6,6),(3,3),(0,6) có INSIDE không?

**Đáp án:** OUTSIDE vì nằm trong khe lõm.

### Bài 25 — Boundary

Q=(6,2) trên cạnh phải hình chữ nhật x∈[0,6], y∈[0,4]?

**Đáp án:** BOUNDARY.

### Bài 26 — Half-open ray casting

Vì sao dùng `(a.y>qy)!=(b.y>qy)`?

**Đáp án:** để không đếm đôi một đỉnh chung khi tia đi qua đỉnh.

### Bài 27 — Hull có điểm nội bộ

Các góc hình vuông và điểm giữa tạo bao lồi nào?

**Đáp án:** chỉ bốn góc.

### Bài 28 — Hull collinear

Bao lồi của (0,0),(1,1),(2,2) với convention bỏ điểm giữa?

**Đáp án:** (0,0),(2,2).

### Bài 29 — Phức tạp hull

Andrew monotone chain?

**Đáp án:** O(n log n) thời gian, O(n) bộ nhớ.

### Bài 30 — Oracle lưới

Vì sao duyệt điểm nguyên trên hai đoạn không đủ để tìm mọi giao?

**Đáp án:** giao có thể có tọa độ phân số như (3/2,3/2).

### Bài 31 — EPS

Có một EPS cố định đúng cho mọi bài hình học double?

**Đáp án:** không; cần cân nhắc thang đo và robust predicates.

### Bài 32 — Trùng điểm hull

Nên làm gì trước khi dựng hull?

**Đáp án:** sort/unique để loại điểm trùng.

### Bài 33 — Hệ tọa độ màn hình

Nếu y hướng xuống, cảm nhận CCW/CW thay đổi thế nào?

**Đáp án:** dấu theo phép orient chuẩn có thể ngược với chiều quay nhìn trên màn hình.

### Bài 34 — So độ dài

Khi không cần in độ dài, có nên tính sqrt?

**Đáp án:** không cần, so bình phương độ dài với số học đủ rộng.

## 22. Checklist triển khai

1. Có phân biệt điểm và vectơ?
2. Đã thống nhất hệ tọa độ và chiều trục y?
3. Đoạn được hiểu là **đóng** hay mở?
4. Có xử lý đoạn suy biến A=B?
5. Với tọa độ nguyên, có chuyển sang BigInteger trước khi trừ/nhân?
6. Có dùng đúng `dot(u,v)=ux·vx+uy·vy`?
7. Có dùng đúng `cross(u,v)=ux·vy−uy·vx`?
8. Orient có lấy `(B−A)×(C−A)`?
9. Có giữ dấu cross cho hướng quay?
10. Diện tích tam giác có lấy abs(orient)/2?
11. Điểm trên đoạn có cả orient0 và bbox?
12. Có kiểm đúng hai đầu mút thuộc đoạn đóng?
13. Giao đoạn có phân loại PROPER/TOUCH/OVERLAP/NONE?
14. Có xử lý hai đoạn collinear bằng giao khoảng?
15. Có xử lý hai đoạn điểm?
16. Có kiểm các đoạn song song khác đường?
17. Có kiểm denominator0 ở giao đường?
18. Có giữ tọa độ giao hữu tỉ khi cần chính xác?
19. Có kiểm t,u thuộc [0,1] khi cần giao đoạn?
20. Hình chiếu tới đoạn có clamp t?
21. Có tránh chia normSquared0 khi A=B?
22. Với double, có validate NaN/Infinity?
23. Có hiểu EPS không thay thế predicate exact?
24. Có dùng Math.hypot phù hợp khi đo khoảng cách?
25. Shoelace có đóng cạnh cuối về đầu?
26. Có phân biệt hai lần diện tích với diện tích?
27. Point-in-polygon có kiểm BOUNDARY trước?
28. Ray casting có xử lý half-open theo y?
29. Đa giác có thỏa giả định đơn không tự cắt?
30. Hull có sort/unique?
31. Hull có quy tắc collinear rõ ràng?
32. Hull có xử lý n=0/1/2?
33. Có test tọa độ Long.MIN/MAX?
34. Có đối chiếu giao đoạn bằng tham số hữu tỉ độc lập?
35. Có kiểm giao đoạn đổi vai/đảo đầu mút?
36. Có kiểm hull bằng Jarvis march và PIP bằng winding?
37. Có kiểm invariant tịnh tiến và đảo chiều polygon?
38. Có phân biệt quyết định topo **exact** và đo metric **approximate**?

**Tổng kết:** Điểm là vị trí, vectơ là độ dời. `dot` phục vụ góc/hình chiếu/khoảng cách; `cross` phục vụ hướng quay/diện tích. `orient(A,B,C)=cross(B−A,C−A)` là predicate trung tâm để kiểm thẳng hàng, điểm trên đoạn, giao đoạn, bao lồi và point-in-polygon. Với tọa độ nguyên, hãy tính đúng dấu bằng **BigInteger** (chuyển trước khi trừ) thay vì dùng EPS tùy ý; với số thực, kiểm ràng buộc, sai số, trường hợp suy biến và phân biệt đường vô hạn với đoạn đóng.
