# Tích có hướng và hướng quay của ba điểm

**Tích có hướng** (*cross product*) là một phép tính nền tảng trong **Hình học tính toán**. Với ba điểm có thứ tự A, B, C, dấu của biểu thức `cross(AB, AC)` cho biết đường gấp khúc A→B→C rẽ trái, rẽ phải hay thẳng hàng. Cùng một phép tính còn giúp tìm diện tích tam giác, phân loại điểm theo nửa mặt phẳng, kiểm tra điểm thuộc đoạn, giao hai đoạn và dựng bao lồi (*convex hull*).

**Phạm vi bài:** Tập trung hiểu chính xác công thức, ý nghĩa dấu và các trường hợp suy biến của hướng quay **ba điểm**. Giao đoạn, diện tích đa giác và bao lồi là những ứng dụng thiết thực để thấy cách dùng predicate này; không cần hiểu chúng trước để học định nghĩa tích có hướng.

**Quy ước xuyên suốt:** Hệ tọa độ Cartesian x tăng sang phải, y tăng lên trên; ba điểm xét **theo thứ tự A,B,C**. Tọa độ trong Java là số nguyên `long`, nhưng mọi phép trừ và nhân phục vụ cross được thực hiện bằng `BigInteger` để tránh tràn. Đoạn thẳng được coi là **đoạn đóng**, bao gồm hai đầu mút; A=B là một đoạn suy biến thành điểm. Nếu đề dùng tọa độ màn hình y hướng xuống hoặc đoạn mở, cần đổi quy ước diễn giải tương ứng.

## 1. Định nghĩa: vector và định thức

Với hai vector trong mặt phẳng:

```text
u = (ux, uy)
v = (vx, vy)

cross(u,v) = ux * vy - uy * vx
```

Phép toán này được gọi là tích có hướng 2D nhưng **trả về một số có dấu**, không phải vector 2D. Nếu nhúng u,v thành vector 3D có tọa độ z bằng0, tích có hướng 3D là vector (0,0,cross(u,v)). Giá trị số 2D chính là thành phần z.

Với ba điểm:

```text
A = (ax, ay)
B = (bx, by)
C = (cx, cy)

AB = (bx-ax, by-ay)
AC = (cx-ax, cy-ay)

cross(A,B,C)
    = cross(AB, AC)
    = (bx-ax)*(cy-ay)
      - (by-ay)*(cx-ax)
```

Hai vector **cùng xuất phát tại A**. Phải nhất quán thứ tự: `cross(AB, AC)` là **đối dấu** với `cross(AC, AB)`. Có thể thay AC bằng BC trong tích `cross(AB,BC)` nhờ AC=AB+BC và cross(AB,AB)=0, nhưng định nghĩa AB,AC rõ nghĩa hơn cho việc xác định hướng quay.

## 2. Quy tắc dấu và vị trí trái/phải

| Giá trị tích có hướng | Hướng quay A→B→C | Vị trí C so với đường thẳng có hướng A→B |
| --- | --- | --- |
| `cross>0` | Rẽ **trái**, ngược chiều kim đồng hồ (CCW) | Bên trái |
| `cross<0` | Rẽ **phải**, cùng chiều kim đồng hồ (CW) | Bên phải |
| `cross=0` | **Thẳng hàng** hoặc suy biến | Trên đường AB nếu A≠B |

Nhận diện “trái/phải” phụ thuộc **chiều A→B**, không phụ thuộc chỉ riêng y của C. Đi từ B về A sẽ đảo phía. Tích có hướng cho dấu của diện tích, **không** cho góc quay tính bằng độ.

### 2.1. Tính tay ba trường hợp

```text
A = (0,0), B = (4,0)

C1 = (2, 3):
cross = 4*3-0*2 = 12 > 0
=> CCW, trái.

C2 = (2,-3):
cross = 4*(-3)-0*2 = -12 < 0
=> CW, phải.

C3 = (8,0):
cross = 4*0-0*8 = 0
=> thẳng hàng.
```

**Lưu ý:** C3=(8,0) nằm ngoài đoạn A(0,0)→B(4,0) dù cross=0. Tích có hướng bằng0 không đủ để xác định điểm thuộc **đoạn hữu hạn**.

### 2.2. Hệ tọa độ màn hình y tăng xuống

Trong nhiều UI/ảnh bitmap, y lớn hơn nghĩa là điểm nằm **thấp hơn**. Khi lật trục y từ hệ Cartesian lên sang hệ màn hình xuống, **dấu định thức đổi** nếu ta chuyển đổi tọa độ hình học tương ứng. Cùng biểu thức đại số vẫn tính đúng, nhưng diễn giải trực quan CCW/CW khi nhìn trên màn hình phải phù hợp quy ước trục.

Không nên thêm dấu âm tùy tiện; cần ghi rõ hệ tọa độ của bài toán. Với hình học Cartesian x phải/y lên, dương=trái là quy ước của chương trình dưới đây.

## 3. Tích có hướng bằng hai lần diện tích có hướng

Hai vector AB,AC tạo hình bình hành diện tích bằng `|cross(A,B,C)|`. Tam giác ABC là một nửa hình ấy:

```text
signedTwiceTriangleArea = cross(A,B,C)

triangleArea = abs(cross(A,B,C)) / 2
```

Với tọa độ nguyên, cross luôn nguyên nhưng diện tích có thể là số nguyên **hoặc phần lẻ .5**. Ví dụ:

```text
A=(0,0), B=(1,0), C=(0,1)
cross=1
triangleArea=0.5
```

Nếu chỉ so sánh diện tích hay kiểm tra thẳng hàng, giữ **hai lần diện tích** dưới dạng số nguyên để tránh số thực. Nếu cần in diện tích chính xác với tọa độ nguyên, chia BigInteger cho2 và in đuôi `.0` hoặc `.5`; không dùng chia số nguyên rồi làm mất phần .5.

## 4. Tính chất đại số quan trọng

**Đổi thứ tự hai vector đổi dấu:**

```text
cross(u,v) = -cross(v,u)
cross(A,B,C) = -cross(A,C,B)
```

**Hoán vị vòng ba điểm giữ dấu:**

```text
cross(A,B,C) = cross(B,C,A) = cross(C,A,B)
```

**Tịnh tiến tất cả điểm cùng một vector không đổi giá trị:**

```text
cross(A+t, B+t, C+t) = cross(A,B,C)
```

Vì cả hai vector hiệu B−A và C−A không đổi.

**Nhân cả hai trục với hệ số λ:**

```text
cross(λA, λB, λC) = λ² * cross(A,B,C)
```

Nếu λ≠0, dấu giữ nguyên. Nhưng **phản xạ một trục** là phép biến đổi có định thức âm, nên đảo hướng quay.

**Khi cross bằng0:** AB,AC phụ thuộc tuyến tính. Nếu A≠B, C nằm trên đường thẳng AB. Nếu A=B, AB là vector không, cross=0 **với mọi C**; đó là trường hợp suy biến, không có hướng AB thực sự để bàn chuyện trái/phải.

Các tính chất đổi dấu và hoán vị vòng rất hữu ích làm kiểm thử tự động.

## 5. Điểm thuộc đoạn thẳng

Cho đoạn **đóng** [A,B]. P thuộc đoạn khi và chỉ khi:

1. `cross(A,B,P)=0`: P thẳng hàng.
2. P nằm trong hộp tọa độ của hai đầu mút, tính cả biên:

```text
min(ax,bx) <= px <= max(ax,bx)
min(ay,by) <= py <= max(ay,by)
```

Tóm lại:

```text
onSegment(A,B,P) =
    cross(A,B,P) == 0
    AND px nằm trong khoảng ax,bx
    AND py nằm trong khoảng ay,by
```

Ví dụ A=(0,0), B=(4,0):

| P | Cross | Thuộc đoạn? |
| --- | ---: | --- |
| (0,0) | 0 | Có, đầu mút |
| (2,0) | 0 | Có, điểm giữa |
| (4,0) | 0 | Có, đầu mút |
| (5,0) | 0 | **Không**, ngoài hộp |
| (2,1) | 4 | **Không**, khác đường |
| (−1,0) | 0 | **Không**, nằm trên tia kéo dài |

**Đoạn suy biến:** Nếu A=B, cross(A,B,P)=0 cho mọi P; bounding box chỉ chứa đúng điểm A. Vậy onSegment(A,A,P) đúng khi và chỉ khi P=A. Không cần chia cho độ dài đoạn hay tạo hệ số t có thể chia cho0.

**Đường thẳng vô hạn khác đoạn hữu hạn:** Nếu bài hỏi P nằm trên **đường** AB, với A≠B chỉ cross=0 là đủ. Nếu hỏi P nằm trên **đoạn**, bắt buộc kiểm tra thêm hộp tọa độ.

## 6. Kiểm tra hai đoạn thẳng giao nhau

Xét hai đoạn đóng [A,B] và [C,D]. Tính:

```text
o1 = orientation(A,B,C)
o2 = orientation(A,B,D)
o3 = orientation(C,D,A)
o4 = orientation(C,D,B)
```

Mỗi oi chỉ có −1,0,+1.

### 6.1. Cắt nhau ở nội điểm hai đoạn

Trong trường hợp không có các đầu mút thẳng hàng với đường tương ứng, hai đoạn cắt nhau ở **phần trong** khi:

```text
o1*o2 < 0 AND o3*o4 < 0.
```

Ý nghĩa: C,D nằm hai phía trái/ngược nhau của đường AB, và A,B nằm hai phía khác nhau của đường CD.

### 6.2. Chạm đầu mút và chồng lấp

Điều kiện cắt nghiêm ngặt **không bao gồm** chạm đầu mút hoặc chồng lấp thẳng hàng. Kiểm tra bốn trường hợp đặc biệt trước:

```text
if o1 == 0 AND onSegment(A,B,C): true
if o2 == 0 AND onSegment(A,B,D): true
if o3 == 0 AND onSegment(C,D,A): true
if o4 == 0 AND onSegment(C,D,B): true

otherwise:
    o1*o2 < 0 AND o3*o4 < 0
```

Lời giải này hỗ trợ cả đoạn suy biến (một điểm). **Không** chỉ viết `o1!=o2 && o3!=o4` khi có số0: một đầu mút có thể thẳng hàng với **đường kéo dài** nhưng nằm ngoài đoạn.

Các ví dụ:

| Đoạn AB | Đoạn CD | Giao? |
| --- | --- | --- |
| (0,0)–(4,4) | (0,4)–(4,0) | true: cắt ở (2,2) |
| (0,0)–(4,0) | (4,0)–(6,3) | true: chạm đầu mút |
| (0,0)–(6,0) | (3,0)–(10,0) | true: chồng lấp |
| (0,0)–(2,0) | (3,0)–(5,0) | false: cùng đường nhưng rời |
| (0,0)–(4,0) | (0,1)–(4,1) | false: song song rời |
| (1,1)–(1,1) | (0,0)–(2,2) | true: một đoạn là điểm thuộc đoạn kia |

Các hàm trả **boolean giao hay không**, không trả tọa độ giao điểm. Tính giao điểm chính xác là một bài riêng thường cần phân số/giải phương trình tham số.

## 7. Ứng dụng: bao lồi Andrew's monotone chain

Bao lồi là đa giác lồi nhỏ nhất chứa một tập điểm. Một thuật toán phổ biến có độ phức tạp O(n log n):

1. Loại điểm trùng và sắp điểm theo x tăng, nếu hòa thì y tăng.
2. Duyệt trái→phải để xây **lower hull**.
3. Duyệt phải→trái để xây **upper hull**.
4. Mỗi khi ba điểm cuối tạo rẽ phải hoặc **thẳng hàng** (cross≤0), bỏ điểm ở giữa.
5. Nối hai nửa và bỏ đầu mút bị lặp.

Giả mã:

```text
for each p in points sorted by (x,y):
    while lower has at least two points and
          cross(lower[-2],lower[-1],p) <= 0:
        remove the last point in lower
    append p to lower
```

Chính sách **≤0** có nghĩa thuật toán loại các điểm thẳng hàng **ở giữa cạnh bao**. Nếu bài yêu cầu giữ mọi điểm trên biên, cần thay chính sách và xử lý riêng trường hợp tất cả điểm thẳng hàng; không được chỉ đổi dấu rồi giả định mọi trường hợp đều đúng.

Ví dụ tập [(0,0),(2,0),(2,2),(0,2),(1,1),(1,0),(0,0)] có hull tối giản:

```text
[(0,0),(2,0),(2,2),(0,2)]
```

Điểm giữa (1,1) nằm trong, (1,0) nằm trên cạnh, (0,0) trùng — tất cả đều không tạo thêm đỉnh. Hull có thứ tự **CCW**, bắt đầu từ điểm trái nhất (nếu x hòa chọn y nhỏ nhất).

Với các điểm **tất cả thẳng hàng**, hull theo chính sách này là **hai đầu mút cực trị**; nếu có một điểm phân biệt thì hull có1 phần tử, tập rỗng có0 phần tử.

## 8. Ứng dụng: diện tích đa giác theo shoelace

Cho các đỉnh của **đa giác đơn** (không tự cắt) theo đúng thứ tự quanh biên `P0,...,P(k−1)`:

```text
signedTwiceArea =
    SUM (xi*y(i+1) - yi*x(i+1))
    for i=0..k-1
    with P(k)=P0.

area = |signedTwiceArea|/2.
```

Nếu đỉnh theo CCW và y hướng lên, signedTwiceArea dương; đảo chiều thì âm.

Với hình vuông [(0,0),(2,0),(2,2),(0,2)], tổng định thức bằng8, diện tích bằng4. Hàm `signedTwicePolygonArea` trong chương trình dùng BigInteger và có thể áp dụng cho hull.

**Không** gọi |shoelace|/2 là diện tích hình học của vùng tự cắt nếu các cạnh giao nhau; lúc đó tổng là diện tích **đại số có hướng**, có thể có các vùng triệt tiêu. Trước tiên cần định nghĩa thế nào là diện tích của hình tự cắt.

## 9. Vấn đề tràn số và sai số

### 9.1. Tràn có thể xảy ra ngay ở bước trừ

Cách viết phổ biến:

```java
long cross = (bx-ax)*(cy-ay) - (by-ay)*(cx-ax);
```

**không an toàn** cho mọi tọa độ long. Không chỉ phép nhân, mà `bx−ax` cũng có thể vượt miền signed 64-bit. Sau khi đã tràn, việc đưa kết quả sang BigInteger không cứu được:

```java
// Sai khi phép trừ long đã tràn:
BigInteger.valueOf(bx - ax)
```

Cách đúng:

```java
BigInteger dx = BigInteger.valueOf(bx)
        .subtract(BigInteger.valueOf(ax));
```

Từ đó tính mọi phép nhân/trừ bằng BigInteger. Hàm `orientation` lấy `cross.signum()`, luôn trả −1,0,+1, không cần ép BigInteger về long.

Với ba điểm có tọa độ ở biên Long.MIN_VALUE/Long.MAX_VALUE, hiệu có thể bằng `2^64−1`, vượt long. Tích có thể có **39 chữ số**. Chương trình kiểm thử trường hợp này.

### 9.2. Sai số số thực khi gần thẳng hàng

Với `X=10^16`:

```text
A=(0,0)
B=(X,X-1)
C=(X+1,X)

cross(A,B,C)
    = X*X-(X-1)*(X+1)
    = 1 > 0
```

Dấu toán học chính xác là **dương** dù hai tích đều khoảng 10³². Trong `double`, các số nguyên liên tiếp quanh 10¹⁶ có thể không còn phân biệt được và hiệu hai tích lớn bị triệt tiêu, nên kết quả có thể bị làm tròn thành0. Nếu đó là predicate xác định hull hoặc giao đoạn, sai số này có thể làm sai nhánh thuật toán.

Với dữ liệu **nguyên**, sử dụng số học nguyên chính xác. Không tùy tiện so `Math.abs(cross)<epsilon` rồi coi thẳng hàng: điều ấy thay đổi định nghĩa của bài toán. Với dữ liệu **thực**, cần robust orientation predicate và quản lý sai số dựa trên miền dữ liệu.

### 9.3. Khi nào dùng long vẫn được?

Nếu đề giới hạn tọa độ nhỏ, có thể chứng minh cận cho mọi phép trừ, nhân và lấy hiệu rồi dùng long. Tọa độ đầu vào dạng int **không bảo đảm** phép nhân hai hiệu vừa int. Mã dùng BigInteger để không cần suy đoán cận, đổi lại tăng chi phí tạo đối tượng số học.

## 10. Chứng minh tính đúng của ba phép kiểm tra

**Hướng quay:** Định thức `D=ux*vy−uy*vx` là diện tích có hướng của hình bình hành. Với vector không suy biến, D có dấu như sin góc có hướng từ AB đến AC. Dương ứng với CCW trên hệ tọa độ chuẩn, âm với CW; D=0 khi các vector phụ thuộc tuyến tính.

**Điểm thuộc đoạn:** Nếu P=A+t(B−A), 0≤t≤1, rõ ràng cross=0 và P nằm trong hộp tọa độ. Ngược lại, nếu A≠B, cross=0 buộc AP=tAB cho một t; điều kiện hộp ở trục có AB khác0 buộc 0≤t≤1. Nếu A=B, hộp chỉ chứa đúng A. Vậy kết hợp cross=0 và hộp là **cần và đủ**.

**Giao hai đoạn:** Khi hai đường chứa đoạn không song song, nếu cắt tại nội điểm của cả hai, mỗi cặp đầu mút nằm khác phía của đường bên kia, nên các cặp dấu đối nhau. Ngược lại, nếu hai cặp khác phía nghiêm ngặt, các đoạn liên tục phải cắt bên trong. Nếu giao tại đầu mút hoặc chồng lấp thẳng hàng, ít nhất một đầu mút nằm trên đoạn kia; các kiểm tra onSegment nhận diện đúng. Kết hợp hai nhóm là điều kiện cần và đủ cho giao **đoạn đóng**.

**Bao lồi:** Sau khi sort, vòng lặp monotone chain bỏ những đỉnh tạo rẽ phải hoặc nằm giữa cạnh thẳng hàng, vì chúng không thể là đỉnh cực trị cần thiết của biên lồi theo chính sách tối giản. Hai nửa hull xây theo chiều đối nhau nối lại tạo biên CCW chứa mọi điểm. Mỗi điểm chỉ bị thêm/bỏ số lần hữu hạn, nên vòng quét tuyến tính sau sort.

## 11. Cài đặt Java 17 đầy đủ

Tệp mã có tên **`CrossProductOrientationDemo.java`**. Các phép tính cross, orientation, diện tích, bounding box và thuật toán hull dùng cùng quy ước. Kiểm thử có **một oracle định thức khác công thức vector** và **một oracle tham số hữu tỉ cho giao đoạn**, nên không chỉ kiểm tra hàm bằng chính logic mà hàm ấy đang dùng. Đoạn đóng và điểm suy biến đều được hỗ trợ.


```java
import java.math.BigInteger;
import java.util.*;

public class CrossProductOrientationDemo {
    record Point(long x, long y) {}
    record Vector(BigInteger x, BigInteger y) {}

    static BigInteger bi(long value) {
        return BigInteger.valueOf(value);
    }

    static Vector vector(Point from, Point to) {
        Objects.requireNonNull(from, "from");
        Objects.requireNonNull(to, "to");
        return new Vector(
                bi(to.x()).subtract(bi(from.x())),
                bi(to.y()).subtract(bi(from.y())));
    }

    static BigInteger determinant(Vector u, Vector v) {
        return u.x().multiply(v.y())
                .subtract(u.y().multiply(v.x()));
    }

    // Exact signed twice-area of triangle (a,b,c).
    static BigInteger cross(Point a, Point b, Point c) {
        return determinant(vector(a, b), vector(a, c));
    }

    // +1 = CCW/left, -1 = CW/right, 0 = collinear.
    static int orientation(Point a, Point b, Point c) {
        return cross(a, b, c).signum();
    }

    static String turnName(Point a, Point b, Point c) {
        return switch (orientation(a, b, c)) {
            case 1 -> "COUNTERCLOCKWISE";
            case -1 -> "CLOCKWISE";
            default -> "COLLINEAR";
        };
    }

    static boolean withinBox(Point a, Point b, Point p) {
        return Math.min(a.x(), b.x()) <= p.x()
                && p.x() <= Math.max(a.x(), b.x())
                && Math.min(a.y(), b.y()) <= p.y()
                && p.y() <= Math.max(a.y(), b.y());
    }

    // CLOSED segment membership (including endpoints).
    static boolean onSegment(Point a, Point b, Point p) {
        return orientation(a, b, p) == 0
                && withinBox(a, b, p);
    }

    static boolean intersects(
            Point a, Point b, Point c, Point d) {
        int o1 = orientation(a, b, c);
        int o2 = orientation(a, b, d);
        int o3 = orientation(c, d, a);
        int o4 = orientation(c, d, b);

        if (o1 == 0 && onSegment(a, b, c)) return true;
        if (o2 == 0 && onSegment(a, b, d)) return true;
        if (o3 == 0 && onSegment(c, d, a)) return true;
        if (o4 == 0 && onSegment(c, d, b)) return true;
        return o1 * o2 < 0 && o3 * o4 < 0;
    }

    static BigInteger signedTwicePolygonArea(
            List<Point> polygon) {
        Objects.requireNonNull(polygon, "polygon");
        if (polygon.size() < 3) return BigInteger.ZERO;
        BigInteger sum = BigInteger.ZERO;
        for (int i = 0; i < polygon.size(); i++) {
            Point a = Objects.requireNonNull(
                    polygon.get(i), "polygon vertex");
            Point b = Objects.requireNonNull(
                    polygon.get((i + 1) % polygon.size()),
                    "polygon vertex");
            sum = sum.add(
                    bi(a.x()).multiply(bi(b.y()))
                            .subtract(
                                    bi(a.y()).multiply(bi(b.x()))));
        }
        return sum;
    }

    static String halfIntegerArea(BigInteger twiceArea) {
        BigInteger[] pair = twiceArea.abs()
                .divideAndRemainder(BigInteger.TWO);
        return pair[0] + (pair[1].signum() == 0 ? ".0" : ".5");
    }

    // Strict hull: exclude intermediate collinear boundary points.
    static List<Point> convexHull(List<Point> input) {
        Objects.requireNonNull(input, "points");
        Set<Point> unique = new HashSet<>();
        for (Point p : input) {
            unique.add(Objects.requireNonNull(p, "point"));
        }
        List<Point> sorted = new ArrayList<>(unique);
        sorted.sort(
                Comparator.comparingLong(Point::x)
                        .thenComparingLong(Point::y));
        if (sorted.size() <= 1) return List.copyOf(sorted);

        List<Point> lower = new ArrayList<>();
        for (Point p : sorted) {
            while (lower.size() >= 2
                    && orientation(
                            lower.get(lower.size() - 2),
                            lower.get(lower.size() - 1), p) <= 0) {
                lower.remove(lower.size() - 1);
            }
            lower.add(p);
        }

        List<Point> upper = new ArrayList<>();
        for (int i = sorted.size() - 1; i >= 0; i--) {
            Point p = sorted.get(i);
            while (upper.size() >= 2
                    && orientation(
                            upper.get(upper.size() - 2),
                            upper.get(upper.size() - 1), p) <= 0) {
                upper.remove(upper.size() - 1);
            }
            upper.add(p);
        }

        lower.remove(lower.size() - 1);
        upper.remove(upper.size() - 1);
        lower.addAll(upper);
        return List.copyOf(lower);
    }

    // Independent 3x3 determinant expansion.
    static BigInteger triangleDeterminantOracle(
            Point a, Point b, Point c) {
        return bi(a.x()).multiply(
                        bi(b.y()).subtract(bi(c.y())))
                .add(bi(b.x()).multiply(
                        bi(c.y()).subtract(bi(a.y()))))
                .add(bi(c.x()).multiply(
                        bi(a.y()).subtract(bi(b.y()))));
    }

    static boolean oracleContains(Point a, Point b, Point p) {
        return triangleDeterminantOracle(a, b, p).signum() == 0
                && withinBox(a, b, p);
    }

    // Oracle uses rational segment parameters t and u.
    static boolean segmentOracle(
            Point a, Point b, Point c, Point d) {
        if (a.equals(b)) {
            return oracleContains(c, d, a);
        }
        if (c.equals(d)) {
            return oracleContains(a, b, c);
        }

        Vector r = vector(a, b);
        Vector s = vector(c, d);
        Vector w = vector(a, c);
        BigInteger denominator = determinant(r, s);

        if (denominator.signum() == 0) {
            if (triangleDeterminantOracle(a, b, c)
                    .signum() != 0) {
                return false;
            }
            return Math.max(Math.min(a.x(), b.x()),
                            Math.min(c.x(), d.x()))
                            <= Math.min(Math.max(a.x(), b.x()),
                                    Math.max(c.x(), d.x()))
                    && Math.max(Math.min(a.y(), b.y()),
                            Math.min(c.y(), d.y()))
                            <= Math.min(Math.max(a.y(), b.y()),
                                    Math.max(c.y(), d.y()));
        }

        BigInteger t = determinant(w, s);
        BigInteger u = determinant(w, r);
        if (denominator.signum() < 0) {
            denominator = denominator.negate();
            t = t.negate();
            u = u.negate();
        }
        return t.signum() >= 0 && t.compareTo(denominator) <= 0
                && u.signum() >= 0
                && u.compareTo(denominator) <= 0;
    }

    static long randomCoordinate(Random rng) {
        return switch (rng.nextInt(12)) {
            case 0 -> Long.MIN_VALUE;
            case 1 -> Long.MAX_VALUE;
            case 2 -> Long.MIN_VALUE + 1;
            case 3 -> Long.MAX_VALUE - 1;
            default -> rng.nextInt(41) - 20;
        };
    }

    static Point randomPoint(Random rng) {
        return new Point(
                randomCoordinate(rng),
                randomCoordinate(rng));
    }

    static void randomizedCrossCheck() {
        Random rng = new Random(20261110L);

        for (int trial = 0; trial < 2000; trial++) {
            Point a = randomPoint(rng);
            Point b = randomPoint(rng);
            Point c = randomPoint(rng);
            BigInteger actual = cross(a, b, c);
            BigInteger expected =
                    triangleDeterminantOracle(a, b, c);
            if (!actual.equals(expected)
                    || !actual.equals(cross(b, c, a))
                    || !actual.equals(cross(a, c, b).negate())) {
                throw new AssertionError(
                        "cross identity mismatch: " + trial);
            }
        }

        for (int trial = 0; trial < 2000; trial++) {
            Point a = randomPoint(rng);
            Point b = randomPoint(rng);
            Point c = randomPoint(rng);
            Point d = randomPoint(rng);
            boolean actual = intersects(a, b, c, d);
            boolean expected = segmentOracle(a, b, c, d);
            if (actual != expected) {
                throw new AssertionError(
                        "segment mismatch: " + trial
                        + " a=" + a + " b=" + b
                        + " c=" + c + " d=" + d);
            }
        }

        for (int trial = 0; trial < 500; trial++) {
            int count = rng.nextInt(17);
            List<Point> points = new ArrayList<>();
            for (int i = 0; i < count; i++) {
                points.add(new Point(
                        rng.nextInt(17) - 8,
                        rng.nextInt(17) - 8));
            }
            List<Point> hull = convexHull(points);
            if (new HashSet<>(hull).size() != hull.size()
                    || !points.containsAll(hull)) {
                throw new AssertionError("invalid hull vertices");
            }
            if (hull.size() >= 3) {
                if (signedTwicePolygonArea(hull).signum() <= 0) {
                    throw new AssertionError("non-CCW hull");
                }
                for (int i = 0; i < hull.size(); i++) {
                    Point a = hull.get(i);
                    Point b = hull.get((i + 1) % hull.size());
                    for (Point p : points) {
                        if (triangleDeterminantOracle(a, b, p)
                                .signum() < 0) {
                            throw new AssertionError(
                                    "point outside convex hull");
                        }
                    }
                }
            } else if (hull.size() == 2) {
                for (Point p : points) {
                    if (!oracleContains(
                            hull.get(0), hull.get(1), p)) {
                        throw new AssertionError(
                                "two-point hull not collinear");
                    }
                }
            } else if (!points.isEmpty()
                    && hull.size() != 1) {
                throw new AssertionError("empty hull with points");
            }
        }
        System.out.println(
                "Random cross-check: PASS "
                + "(2000 triples, 2000 segment pairs, 500 hulls)");
    }

    public static void main(String[] args) {
        Point a = new Point(0, 0);
        Point b = new Point(4, 0);
        Point left = new Point(2, 3);
        Point right = new Point(2, -3);
        Point far = new Point(8, 0);

        System.out.println(
                "Left turn: cross=" + cross(a, b, left)
                + ", orientation=" + turnName(a, b, left)
                + ", triangleArea="
                + halfIntegerArea(cross(a, b, left)));

        System.out.println(
                "Right turn: cross=" + cross(a, b, right)
                + ", orientation=" + turnName(a, b, right));

        System.out.println(
                "Far collinear: cross=" + cross(a, b, far)
                + ", onSegment=" + onSegment(a, b, far));

        System.out.println(
                "Boundary points: inside="
                + onSegment(a, b, new Point(2, 0))
                + ", outside="
                + onSegment(a, b, new Point(5, 0)));

        System.out.println(
                "Half-integer area: "
                + halfIntegerArea(cross(
                        a, new Point(1, 0), new Point(0, 1))));

        System.out.println(
                "Proper crossing: "
                + intersects(new Point(0, 0), new Point(4, 4),
                        new Point(0, 4), new Point(4, 0)));

        System.out.println(
                "Touching endpoint: "
                + intersects(new Point(0, 0), new Point(4, 0),
                        new Point(4, 0), new Point(6, 3)));

        System.out.println(
                "Overlapping collinear: "
                + intersects(new Point(0, 0), new Point(6, 0),
                        new Point(3, 0), new Point(10, 0)));

        System.out.println(
                "Parallel disjoint: "
                + intersects(new Point(0, 0), new Point(4, 0),
                        new Point(0, 1), new Point(4, 1)));

        System.out.println(
                "Collinear disjoint: "
                + intersects(new Point(0, 0), new Point(2, 0),
                        new Point(3, 0), new Point(5, 0)));

        System.out.println(
                "Point segment: "
                + intersects(new Point(1, 1), new Point(1, 1),
                        new Point(0, 0), new Point(2, 2)));

        List<Point> square = List.of(
                new Point(0, 0), new Point(2, 0),
                new Point(2, 2), new Point(0, 2),
                new Point(1, 1), new Point(1, 0),
                new Point(0, 0));
        List<Point> squareHull = convexHull(square);
        System.out.println(
                "Square hull: " + squareHull
                + ", area="
                + halfIntegerArea(signedTwicePolygonArea(
                        squareHull)));

        List<Point> collinear = List.of(
                new Point(0, 0), new Point(1, 1),
                new Point(2, 2), new Point(3, 3),
                new Point(3, 3));
        System.out.println(
                "Collinear hull: " + convexHull(collinear));

        Point e1 = new Point(Long.MIN_VALUE, Long.MIN_VALUE);
        Point e2 = new Point(Long.MAX_VALUE, Long.MIN_VALUE);
        Point e3 = new Point(Long.MIN_VALUE, Long.MAX_VALUE);
        BigInteger extremeCross = cross(e1, e2, e3);
        System.out.println(
                "Long extremes: sign=" + extremeCross.signum()
                + ", decimalDigits="
                + extremeCross.abs().toString().length());

        System.out.println(
                "Zero vector: " + turnName(
                        new Point(1, 1),
                        new Point(1, 1),
                        new Point(100, -100)));

        randomizedCrossCheck();
    }
}
```


### 11.2. Biên dịch và chạy

Dùng JDK 17 hoặc mới hơn. Lưu mã vào tệp `CrossProductOrientationDemo.java`:

```bash
javac CrossProductOrientationDemo.java
java CrossProductOrientationDemo
```

**Stdout chính xác:**

```text
Left turn: cross=12, orientation=COUNTERCLOCKWISE, triangleArea=6.0
Right turn: cross=-12, orientation=CLOCKWISE
Far collinear: cross=0, onSegment=false
Boundary points: inside=true, outside=false
Half-integer area: 0.5
Proper crossing: true
Touching endpoint: true
Overlapping collinear: true
Parallel disjoint: false
Collinear disjoint: false
Point segment: true
Square hull: [Point[x=0, y=0], Point[x=2, y=0], Point[x=2, y=2], Point[x=0, y=2]], area=4.0
Collinear hull: [Point[x=0, y=0], Point[x=3, y=3]]
Long extremes: sign=1, decimalDigits=39
Zero vector: COLLINEAR
Random cross-check: PASS (2000 triples, 2000 segment pairs, 500 hulls)
```

### 11.3. Ý nghĩa kết quả và kiểm thử

- **Left/Right:** Các bộ ba với cross=12 và −12 cho hai hướng quay trái/phải, diện tích tam giác đều là6.
- **Far collinear:** cross=0 nhưng C nằm ngoài đoạn AB; minh họa việc bắt buộc kiểm tra bounding box.
- **Boundary points:** Đoạn đóng chứa điểm giữa và hai đầu mút, không chứa điểm nằm trên đường kéo dài.
- **Half-integer:** Tam giác đơn vị có diện tích0.5; không bị làm tròn xuống0.
- **Proper crossing / touching / overlap:** Ba kiểu giao đều được nhận ra; **parallel disjoint** và **collinear disjoint** trả false.
- **Point segment:** Đoạn suy biến thành điểm (1,1) vẫn giao với đoạn xiên chứa điểm đó.
- **Square hull:** Loại điểm trùng, điểm nằm trong và điểm nằm giữa cạnh; chu trình CCW có diện tích4.
- **Collinear hull:** Giữ đúng hai đầu mút cực trị.
- **Long extremes:** Dấu tính chính xác với kết quả 39 chữ số, dù hiệu tọa độ vượt long.
- **Zero vector:** Nhãn COLLINEAR ở đây là **dấu định thức bằng0 của bộ ba suy biến** chứ không có đường AB có hướng thật sự.

Bộ kiểm thử có **2.000 bộ ba điểm**, so cross với công thức định thức triển khai độc lập và tính chất hoán vị vòng/đổi dấu. Tiếp theo, **2.000 cặp đoạn thẳng** được so với phép giải giao theo tham số hữu tỉ (t,u∈[0,1]), kể cả trường hợp song song và suy biến. Cuối cùng, **500 bộ điểm bao lồi** được kiểm tra đỉnh không trùng, thuộc input, thứ tự CCW và mọi điểm đầu vào nằm trên hoặc phía trong mọi cạnh bao. Nếu bất kỳ điều kiện nào sai, chương trình ném `AssertionError`; chỉ in PASS khi tất cả phép kiểm tra đều vượt qua.

## 12. Độ phức tạp

Gọi n là số điểm đầu vào, h là số điểm trên bao lồi.

| Tác vụ | Thời gian | Bộ nhớ phụ |
| --- | --- | --- |
| Cross/Orientation của ba điểm long | O(1) phép BigInteger kích thước bị chặn bởi long | O(1) |
| Điểm thuộc đoạn | O(1) | O(1) |
| Giao hai đoạn | O(1), số hữu hạn orientation | O(1) |
| Bao lồi Andrew | O(n log n) do sort; hai vòng stack O(n) | O(n) |
| Shoelace của đa giác h đỉnh | O(h) | O(1) ngoài biến cộng dồn |

Đây là phân tích **theo số điểm**, vì kiểu đầu vào long có 64 bit cố định nên toán hạng BigInteger trung gian trong cross được chặn số bit. Với tọa độ BigInteger **không giới hạn**, phép nhân/trừ có chi phí phụ thuộc số bit và phải tính **bit complexity** riêng.

## 13. Những lỗi thường gặp

1. Đổi chỗ B,C nhưng giữ nguyên cách diễn giải dấu; cross sẽ đổi dấu.
2. Dùng `cross(AC,AB)` rồi gọi là `cross(AB,AC)`.
3. Tưởng cross là một góc quay tính theo độ; nó là diện tích có hướng.
4. Lấy |cross| trước khi xác định CCW/CW, làm mất dấu.
5. Coi cross=0 là P thuộc đoạn AB; P có thể nằm trên phần kéo dài.
6. Chỉ kiểm tra tọa độ nằm trong hộp mà bỏ điều kiện cross=0.
7. Chỉ kiểm tra x mà không kiểm tra y của P khi xét đoạn xiên/dọc.
8. Không xử lý đoạn A=B; cross=0 với mọi P nhưng chỉ P=A thuộc đoạn.
9. Xem A=B là một đường thẳng có hướng xác định được.
10. Quên hệ trục y tăng xuống trong ứng dụng đồ họa.
11. Dùng int cho tích các hiệu, dẫn tới tràn khi tọa độ không quá lớn.
12. Trừ hai long rồi mới bọc BigInteger; phép trừ có thể tràn trước.
13. Nhân hai long rồi mới bọc BigInteger; kết quả đã tràn.
14. Dùng double gần thẳng hàng mà không xét mất độ chính xác.
15. Tự đặt epsilon cho dữ liệu nguyên mà không có lý do toán học.
16. Quên chia |cross| cho2 khi tính diện tích tam giác.
17. Chia số nguyên cho2 và mất phần .5 của diện tích.
18. Cho rằng hai **đường thẳng** cắt nhau thì hai **đoạn** hữu hạn cũng cắt.
19. Chỉ kiểm tra o1≠o2 và o3≠o4 mà bỏ trường hợp0 ngoài đoạn.
20. Bỏ các trường hợp hai đoạn chỉ chạm đầu mút.
21. Bỏ trường hợp hai đoạn thẳng hàng và chồng lấp.
22. Coi hai đoạn trên cùng đường thẳng luôn giao dù khoảng vị trí rời nhau.
23. Coi hai đoạn có một đầu mút trùng là không giao vì “chỉ chạm”.
24. Đếm chạm đầu mút là giao khi đề yêu cầu đoạn **mở** mà không đổi điều kiện.
25. Dựng hull mà không loại điểm trùng; dễ sinh đỉnh lặp.
26. Dùng điều kiện hull `cross<0` hay `<=0` nhưng không ghi rõ giữ/bỏ điểm thẳng hàng.
27. Không xử lý hull rỗng, một điểm, hai điểm hoặc mọi điểm thẳng hàng.
28. Quên bỏ hai đầu mút chung trước khi ghép lower và upper.
29. Tính shoelace cho danh sách điểm chưa được xếp theo chu trình biên.
30. Coi |shoelace|/2 của đa giác tự cắt là diện tích hợp các miền.
31. Dùng phép trừ tọa độ long trong comparator sắp xếp; có thể tràn và sai thứ tự.
32. Cho rằng cross dương luôn tương đương C có y lớn hơn B; còn phụ thuộc hướng AB.
33. Phản xạ một trục nhưng cho rằng hướng quay không đổi.
34. Dùng dấu cross đơn độc để sort tất cả góc trên vòng 360°; comparator có thể không bắc cầu.
35. Không thử các bộ ba thẳng hàng và trùng điểm.
36. Không thử giao chạm đầu mút, chồng lấp, song song rời, đoạn suy biến.
37. Không thử Long.MIN_VALUE/Long.MAX_VALUE dù thuật toán dùng long.
38. Cho rằng BigInteger O(1) với tọa độ độ dài bit không giới hạn; cần phân tích bit.
39. Không có oracle độc lập để phát hiện nhầm dấu hoặc điều kiện đoạn giao.
40. Nhầm điểm nằm trong tam giác không suy biến với bài toán ba đỉnh thẳng hàng: trường hợp suy biến cần quy ước riêng.

## 14. Bài tập tự luyện có đáp án

**Bài 1.** Công thức cross của u=(ux,uy), v=(vx,vy)?

**Đáp án:** `ux*vy−uy*vx`.

**Bài 2.** Công thức hướng quay bộ ba A,B,C?

**Đáp án:** `(bx−ax)(cy−ay)−(by−ay)(cx−ax)`.

**Bài 3.** A=(0,0),B=(4,0),C=(2,3): cross, hướng và diện tích?

**Đáp án:** Cross=12, CCW, diện tích=6.

**Bài 4.** Thay C=(2,−3)?

**Đáp án:** Cross=−12, CW, diện tích vẫn6.

**Bài 5.** A=(0,0),B=(4,0),C=(8,0): có thuộc đoạn AB?

**Đáp án:** Không; cross=0 nhưng C ngoài bounding box.

**Bài 6.** Đổi chỗ B và C đổi cross thế nào?

**Đáp án:** Đổi dấu.

**Bài 7.** Hoán vị vòng A,B,C đổi dấu không?

**Đáp án:** Không, `cross(A,B,C)=cross(B,C,A)`.

**Bài 8.** Tịnh tiến cả ba điểm cùng một vector có đổi cross không?

**Đáp án:** Không.

**Bài 9.** Phóng to cùng hệ số λ≠0 trên cả hai trục thì cross?

**Đáp án:** Nhân λ², dấu giữ nguyên.

**Bài 10.** A=(0,0),B=(1,0),C=(0,1): diện tích?

**Đáp án:** 0.5.

**Bài 11.** Muốn kiểm tra P thuộc đoạn đóng AB cần gì ngoài cross=0?

**Đáp án:** Hai điều kiện tọa độ P nằm giữa hai đầu mút theo cả x và y.

**Bài 12.** Nếu A=B=(3,4), P=(3,5), cross và onSegment?

**Đáp án:** Cross=0, onSegment=false vì P khác A.

**Bài 13.** Bốn dấu dùng để kiểm tra giao đoạn AB và CD?

**Đáp án:** `orientation(A,B,C)`, `orientation(A,B,D)`, `orientation(C,D,A)`, `orientation(C,D,B)`.

**Bài 14.** Điều kiện cắt nhau nghiêm ngặt tại hai nội điểm khi không thẳng hàng?

**Đáp án:** `o1*o2<0 && o3*o4<0`.

**Bài 15.** Hai đoạn (0,0)–(4,0) và (4,0)–(6,3) có giao nếu là đoạn đóng?

**Đáp án:** Có, chung đầu mút (4,0).

**Bài 16.** Hai đoạn (0,0)–(6,0) và (3,0)–(10,0)?

**Đáp án:** Có, chồng lấp khoảng x∈[3,6].

**Bài 17.** Hai đoạn (0,0)–(2,0) và (3,0)–(5,0)?

**Đáp án:** Không, thẳng hàng nhưng rời nhau.

**Bài 18.** Bao lồi của bốn góc hình vuông và điểm giữa là gì?

**Đáp án:** Bốn góc theo CCW; điểm giữa không là đỉnh.

**Bài 19.** Monotone chain bỏ điểm giữa khi ba điểm cuối có cross<=0 nghĩa gì?

**Đáp án:** Bỏ rẽ phải và điểm thẳng hàng giữa cạnh, giữ đỉnh lồi tối giản.

**Bài 20.** Toàn bộ điểm nằm trên một đường thẳng, có ít nhất hai điểm khác nhau: hull bao nhiêu đỉnh?

**Đáp án:** Hai đầu mút cực trị theo chính sách loại điểm giữa.

**Bài 21.** Thời gian dựng hull từ n điểm?

**Đáp án:** O(n log n) do sắp xếp; phần quét O(n).

**Bài 22.** Shoelace tính gì?

**Đáp án:** Tổng định thức cạnh liên tiếp là **hai lần diện tích có hướng**; diện tích hình học của đa giác đơn bằng trị tuyệt đối chia2.

**Bài 23.** Đảo thứ tự đỉnh hình vuông có diện tích4 thì signedTwiceArea đổi thế nào?

**Đáp án:** Từ +8 thành −8 hoặc ngược lại; diện tích vẫn4.

**Bài 24.** Vì sao BigInteger.valueOf(bx−ax) chưa đủ an toàn?

**Đáp án:** Phép trừ long có thể tràn trước; cần bọc bx và ax riêng rồi gọi subtract.

**Bài 25.** Với X=10^16, A=(0,0), B=(X,X−1), C=(X+1,X), cross chính xác?

**Đáp án:** 1; double có thể đánh mất phần khác biệt nhỏ.

**Bài 26.** Cross dương có luôn nghĩa C nằm trên B theo y?

**Đáp án:** Không, vì dấu đo bên trái đường **có hướng A→B**, không so y trực tiếp.

**Bài 27.** Tại sao chỉ dùng cross(u,v)>0 cho comparator góc cả vòng tròn là sai?

**Đáp án:** Quan hệ không tạo thứ tự toàn phần bắc cầu; phải chia nửa mặt phẳng/quadrant trước.

**Bài 28.** Giao đoạn bằng bốn hướng quay có cần điều kiện biên không?

**Đáp án:** Có, phải xử lý orientation0 qua onSegment trước khi xét dấu đối nghịch nghiêm ngặt.

**Bài 29.** Hai đoạn song song không thẳng hàng có giao không?

**Đáp án:** Không.

**Bài 30.** Đoạn suy biến thành một điểm có thể giao đoạn khác không?

**Đáp án:** Có, khi điểm ấy thuộc đoạn kia.

## 15. Checklist trước khi áp dụng

- [ ] Xác nhận hệ trục x/y và thứ tự A→B→C.
- [ ] Dùng công thức cross(AB,AC) đúng, không đổi dấu ngoài ý muốn.
- [ ] Quy ước rõ dấu +1/−1/0, và cách xử lý vector không.
- [ ] Nếu hỏi thuộc đoạn, thêm hộp tọa độ; nếu hỏi đường thẳng vô hạn, không cần.
- [ ] Nếu hỏi giao đoạn, xét cả chạm và chồng lấp tùy đoạn đóng/mở.
- [ ] Nếu làm hull, định nghĩa giữ hay bỏ các điểm thẳng hàng trên cạnh.
- [ ] Nếu tính diện tích, chia |cross| cho2 và không mất phần .5.
- [ ] Chứng minh kiểu số không tràn hoặc dùng BigInteger trước khi trừ.
- [ ] Test bộ ba CCW, CW, thẳng hàng, các điểm trùng, điểm ngoài đoạn.
- [ ] Test hai đoạn giao chéo, chạm, chồng lấp, song song và đoạn suy biến.
- [ ] Test tọa độ rất lớn và đối chiếu bằng một công thức độc lập.

## Kết luận

**Hướng quay của ba điểm** được quyết định bởi một định thức:

```text
cross(A,B,C)
    = (bx-ax)*(cy-ay) - (by-ay)*(cx-ax)

>0: rẽ trái / CCW
<0: rẽ phải / CW
=0: thẳng hàng hoặc suy biến
```

Chỉ một phép kiểm dấu này đã hỗ trợ nhiều kỹ thuật hình học tính toán. Tuy nhiên, hãy nhớ bốn ranh giới: **thẳng hàng khác nằm trong đoạn**, **giao đoạn phải xử lý các ca biên**, **hướng quay phụ thuộc thứ tự điểm/hệ trục**, và **sai số hoặc tràn số có thể đảo dấu**. Với tọa độ long và Java 17, dùng BigInteger cho hiệu tọa độ và định thức là một cách bảo toàn kết quả toán học chính xác.
