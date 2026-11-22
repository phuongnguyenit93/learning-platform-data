# Các trường hợp suy biến: điểm trùng, thẳng hàng, cạnh chồng

Trong **Hình học tính toán**, nhiều thuật toán đúng trên hình vẽ “bình thường” nhưng sai với **các trường hợp suy biến** (*degenerate configurations*): hai điểm trùng tọa độ, ba điểm thẳng hàng, một đoạn có độ dài bằng 0, hai cạnh nằm trên cùng đường rồi chồng lên nhau, một đa giác có đỉnh/cạnh lặp, hoặc tất cả điểm đầu vào bao lồi nằm trên một đường. Đây là những tình huống phải giải quyết bằng **định nghĩa chính xác**, không phải dùng một câu lệnh “bỏ qua nếu lạ”.

Bài học tập trung vào ba nhóm tình huống trong tên bài: **điểm trùng**, **thẳng hàng** và **cạnh chồng**. Các ứng dụng kiểm tra giao đoạn, tính đơn của đa giác và dựng bao lồi được dùng để minh họa cách thiết kế thuật toán không bỏ sót suy biến. Có mã **Java 17+ hoàn chỉnh**, sử dụng `BigInteger` để tính chính xác dấu định hướng cho tọa độ `long`, đồng thời đối chiếu với một bộ kiểm thử độc lập.

**Quy ước dùng xuyên suốt:**

- Hệ tọa độ Cartesian, x tăng sang phải, y tăng lên trên.
- Điểm `P=(x,y)` có tọa độ nguyên kiểu `long`.
- Đoạn `[A,B]` là **đoạn đóng**, gồm hai đầu mút; `[A,A]` được coi là một **điểm**.
- Hai điểm **trùng** khi cả x và y bằng nhau; hai bản ghi input khác ID có thể trùng tọa độ.
- Giao của hai đoạn được phân thành bốn loại: `NONE`, `TOUCH`, `PROPER`, `OVERLAP` theo định nghĩa cụ thể phần 5.
- Một polygon được nhập dưới dạng danh sách các đỉnh **không lặp lại đỉnh đầu ở cuối**; chương trình tự nối cạnh cuối về đầu.
- Dấu `cross(A,B,C)` là số học nguyên chính xác, không dùng epsilon để đoán thẳng hàng.

## 1. Những suy biến cần nhận diện

| Suy biến | Ví dụ | Hậu quả nếu bỏ qua |
| --- | --- | --- |
| Điểm trùng | `P0=(2,3)`, `P2=(2,3)` | Đếm thừa đỉnh hull, cạnh độ dài 0, nhầm số vị trí phân biệt |
| Đoạn điểm | `[A,A]` | Chia cho độ dài đoạn bằng 0 |
| Ba điểm thẳng hàng | `(0,0),(2,0),(4,0)` | Không có tam giác diện tích dương; orientation bằng 0 |
| Điểm trên đường kéo dài | `A=(0,0),B=(4,0),P=(7,0)` | Cross bằng 0 nhưng P **không thuộc đoạn** |
| Đoạn chạm | `[0,4]` và `[4,7]` trên cùng trục | Có đúng một điểm chung |
| Đoạn chồng | `[0,6]` và `[3,9]` trên cùng trục | Giao là một đoạn **dài dương** |
| Cạnh đi ngược | `(0,0)→(4,0)→(2,0)` | Hai cạnh kề chồng một phần; polygon không đơn |
| Điểm hull thẳng hàng | Nhiều điểm trên `y=x` | Hull tối giản chỉ còn hai đầu mút |

**Suy biến không phải lúc nào cũng là lỗi đầu vào.** Với bài giao đoạn đóng, `[A,A]` là một đoạn hợp lệ, dù nó chỉ chứa một điểm. Với bài yêu cầu tam giác không suy biến, ba đỉnh thẳng hàng phải bị từ chối. Với bao lồi của một tập điểm, có thể trả một hoặc hai điểm thay vì ép tạo một đa giác. Vì vậy luôn xác định rõ **ý nghĩa của đầu ra** trước khi xử lý.

## 2. Điểm trùng: giá trị hình học khác chỉ số

Cho hai điểm A=(ax,ay), B=(bx,by):

```text
samePoint(A,B) <=> ax == bx AND ay == by
```

Ví dụ ba bản ghi:

```text
id0 -> (2,3)
id1 -> (5,7)
id2 -> (2,3)
```

Có **ba bản ghi**, nhưng chỉ **hai tọa độ phân biệt**. Nếu yêu cầu số lượng điểm đầu vào, đếm 3; nếu yêu cầu số điểm khác vị trí, đếm 2. Nếu một tọa độ xuất hiện k lần, nó tạo **k(k−1)/2 cặp bản ghi trùng**.

Không tự loại trùng trong mọi bài:

- **Convex hull của tập vị trí:** Có thể dùng `HashSet<Point>` loại các điểm có cùng tọa độ.
- **Đếm tần suất, cặp trùng:** Phải giữ số lần xuất hiện hoặc một bảng tần suất.
- **Danh sách đỉnh đa giác:** Trùng đỉnh có thể tạo cạnh độ dài 0 hoặc tự chạm, cần chính sách hợp lệ/không hợp lệ riêng.
- **Hai đoạn `[A,A]`:** Không loại chúng đi nếu đề cho phép đoạn suy biến thành điểm.

Trong Java, `record Point(long x,long y)` có `equals` dựa trên hai thành phần. Với tọa độ `double`, hai điểm “rất gần” không mặc nhiên là trùng; dùng epsilon để gộp điểm là chính sách dữ liệu riêng. Quan hệ “khoảng cách ≤ epsilon” có thể **không bắc cầu** (A gần B, B gần C nhưng A không gần C), nên không dùng ngây thơ như `equals` trong Set/Map.

## 3. Thẳng hàng: dấu tích có hướng chính xác

Với ba điểm có thứ tự A, B, C:

```text
AB = (bx-ax, by-ay)
AC = (cx-ax, cy-ay)

cross(A,B,C)
    = (bx-ax)*(cy-ay) - (by-ay)*(cx-ax)

orientation = sign(cross)

cross > 0: rẽ trái / counterclockwise (CCW)
cross < 0: rẽ phải / clockwise (CW)
cross = 0: thẳng hàng hoặc trường hợp suy biến
```

Nếu A≠B, `cross=0` nghĩa là C nằm trên **đường thẳng vô hạn** qua A và B. Nếu A=B, vector AB bằng 0, nên `cross=0` với **mọi C**; khi đó không có đường thẳng AB có hướng xác định duy nhất. Nếu A=C cũng có một vector bằng 0.

### 3.1. Ví dụ

```text
A=(0,0), B=(4,0)

C=(2,3):  cross = 12 >0, CCW
C=(2,-3): cross = -12<0, CW
C=(2,0):  cross = 0, nằm trên đoạn AB
C=(7,0):  cross = 0, nằm ngoài đoạn AB
```

**Cross=0 không đủ để kiểm tra P nằm trong đoạn.** Cần thêm điều kiện tọa độ nằm giữa hai đầu mút.

### 3.2. Diện tích tam giác và những phép chia nguy hiểm

Diện tích có hướng gấp đôi của tam giác ABC là `cross(A,B,C)`. Diện tích hình học là `abs(cross)/2`. Khi cross=0, tam giác có diện tích bằng 0, không có nội thất hai chiều. Các công thức barycentric coordinates, tâm ngoại tiếp hoặc biến đổi tọa độ phải chia cho định thức cần **kiểm tra mẫu số khác 0 trước**.

Tọa độ nguyên có thể tạo diện tích `.5`; giữ **hai lần diện tích dưới dạng số nguyên** khi so sánh để tránh làm tròn không cần thiết.

### 3.3. Nguy cơ tràn số

Đoạn Java:

```java
long area2 = (bx-ax)*(cy-ay) - (by-ay)*(cx-ax);
```

**không an toàn** trên toàn miền `long`. Ngay bước trừ `bx-ax` có thể tràn trước khi nhân. Cả cách viết `BigInteger.valueOf(bx-ax)` cũng sai nếu phép trừ long đã tràn.

Đúng là chuyển **từng tọa độ** sang BigInteger trước khi trừ:

```java
BigInteger dx = BigInteger.valueOf(bx)
        .subtract(BigInteger.valueOf(ax));
```

Với Long.MIN_VALUE và Long.MAX_VALUE, hiệu có thể vượt signed 64-bit, tích có thể có 39 chữ số. Mã ở phần 10 dùng BigInteger cho tất cả hiệu và định thức; `signum()` trả -1/0/+1 chính xác.

Nếu đầu vào là số thực gần thẳng hàng, `double` cũng có thể đổi dấu vì phép trừ hai tích lớn gần bằng nhau. Không thêm epsilon tùy ý cho bài số nguyên chính xác; với dữ liệu thực, nên dùng **robust orientation predicate** theo miền và yêu cầu sai số.

## 4. Đoạn độ dài 0 và điểm thuộc đoạn

Đoạn đóng `[A,A]` là **tập một điểm** `{A}`. Nó không có độ dài dương, nên không áp dụng công thức tham số chia cho độ dài AB hoặc độ dài bình phương AB mà không kiểm tra A≠B.

```text
[A,A] giao [C,D]
    <=> A nằm trên đoạn đóng [C,D]

[A,A] giao [C,C]
    <=> A == C
```

Nếu giao, phần giao là **một điểm**, nên phân loại là `TOUCH`, không phải `PROPER` hay `OVERLAP`.

### 4.1. Kiểm tra thuộc đoạn đúng cả khi A=B

P thuộc `[A,B]` khi và chỉ khi:

```text
cross(A,B,P) == 0

AND min(ax,bx) <= px <= max(ax,bx)
AND min(ay,by) <= py <= max(ay,by)
```

Cross=0 xác nhận P cùng đường với AB nếu A≠B; điều kiện **bounding box** bảo đảm P không nằm trên tia kéo dài. Với A=B, bounding box co thành đúng A, nên P chỉ thuộc đoạn khi P=A.

| Đoạn AB | P | Kết quả |
| --- | --- | --- |
| (0,0)–(4,0) | (2,0) | true |
| (0,0)–(4,0) | (7,0) | false dù cross=0 |
| (0,0)–(4,0) | (2,1) | false |
| (3,3)–(3,3) | (3,3) | true |
| (3,3)–(3,3) | (3,4) | false dù cross=0 |

Đừng kiểm tra hộp chỉ theo x mà bỏ y, hoặc ngược lại. Dùng `Math.min/Math.max` trực tiếp trên hai giá trị long để tránh tính hiệu có thể tràn.

## 5. Phân loại giao đoạn: NONE, TOUCH, PROPER, OVERLAP

Với **hai đoạn đóng** `[A,B]` và `[C,D]`, ta định nghĩa bốn kết quả:

| Loại | Ý nghĩa hình học |
| --- | --- |
| `NONE` | Hai đoạn không có điểm chung |
| `TOUCH` | Phần giao **chính xác một điểm** nhưng không phải giao tại nội điểm của **cả hai đoạn có độ dài dương** |
| `PROPER` | Hai đoạn có độ dài dương, không cùng đường, cắt nhau tại nội điểm của **cả hai** |
| `OVERLAP` | Phần giao là một **đoạn có độ dài dương**; phải nằm trên cùng đường |

Với quy ước này, hai **đoạn điểm trùng** nhau cho `TOUCH`, không phải `OVERLAP`. Một đoạn điểm nằm giữa đoạn khác cũng là `TOUCH`, vì đoạn điểm không có nội thất một chiều.

### 5.1. Trường hợp cùng đường thẳng

Hai đoạn không suy biến nằm trên cùng một đường có thể:

```text
[0,6] và [8,10] -> NONE
[0,6] và [6,10] -> TOUCH tại một điểm
[0,6] và [3,9]  -> OVERLAP trên [3,6]
[0,6] và [1,4]  -> OVERLAP, một đoạn nằm trong đoạn kia
[0,6] và [0,6]  -> OVERLAP, hai đoạn trùng hoàn toàn
```

Một cách kiểm tra chính xác là so khoảng trên đường bằng **thứ tự từ điển** `(x,y)`:

```text
lo1=minLex(A,B), hi1=maxLex(A,B)
lo2=minLex(C,D), hi2=maxLex(C,D)

left=maxLex(lo1,lo2)
right=minLex(hi1,hi2)

left>right -> NONE
left=right -> TOUCH
left<right -> OVERLAP
```

**Điều kiện tiên quyết:** Hai đoạn phải **không suy biến** và **đã được xác nhận cùng một đường thẳng**. Khi đó thứ tự từ điển là thứ tự một chiều nhất quán: nếu đường không dọc, x thay đổi đơn điệu; nếu đường dọc, x bằng nhau và y thay đổi đơn điệu. Tuyệt đối không chỉ so “khoảng x chồng nhau” khi chưa xác nhận collinear.

So điểm bằng `Long.compare`, không dùng phép trừ `a.x-b.x` (có thể tràn).

### 5.2. Thứ tự kiểm tra các nhánh

1. Nếu A=B, kiểm tra A có nằm trên `[C,D]`; trả `TOUCH/NONE`.
2. Nếu C=D, kiểm tra C có nằm trên `[A,B]`; trả `TOUCH/NONE`.
3. Tính bốn dấu `o1=orient(A,B,C)`, `o2=orient(A,B,D)`, `o3=orient(C,D,A)`, `o4=orient(C,D,B)`.
4. Nếu **tất cả bằng 0**, hai đoạn có độ dài dương cùng đường; so hai khoảng để trả `NONE/TOUCH/OVERLAP`.
5. Nếu chưa cùng đường, kiểm tra bất kỳ đầu mút nào có orientation bằng 0 **và thực sự nằm trên đoạn kia**, trả `TOUCH`.
6. Nếu `o1*o2<0 && o3*o4<0`, trả `PROPER`.
7. Còn lại `NONE`.

**Phải kiểm tra đồng tuyến trước khi trả TOUCH chỉ vì một đầu mút nằm trên đoạn.** Hai đoạn chồng dài dương có thể chứa đầu mút của nhau; nếu dừng ngay sẽ phân loại thiếu `OVERLAP`.

### 5.3. Bảng ví dụ

| Đoạn 1 | Đoạn 2 | Loại |
| --- | --- | --- |
| (0,0)–(4,4) | (0,4)–(4,0) | `PROPER` |
| (0,0)–(4,0) | (4,0)–(4,3) | `TOUCH` |
| (0,0)–(6,0) | (3,0)–(9,0) | `OVERLAP` |
| (0,0)–(3,0) | (3,0)–(7,0) | `TOUCH` |
| (0,0)–(2,0) | (3,0)–(7,0) | `NONE` |
| (0,0)–(4,0) | (0,2)–(4,2) | `NONE` |
| (0,0)–(0,0) | (0,0)–(0,0) | `TOUCH` |
| (2,0)–(2,0) | (0,0)–(4,0) | `TOUCH` |

Công thức đơn giản `o1!=o2 && o3!=o4` không đủ cho mọi ca biên, vì dấu 0 có thể xuất hiện khi một điểm nằm trên **đường kéo dài** nhưng ngoài đoạn. Hãy kiểm tra bounding box cùng orientation.

## 6. Cạnh chồng trong đa giác khác góc 180 độ

Đa giác là một **danh sách đỉnh theo thứ tự chu trình**, không phải một tập tọa độ vô thứ tự. Hai cạnh kề có thể cùng đường theo hai cách rất khác nhau:

```text
(0,0) -> (2,0) -> (4,0)
```

Hai cạnh đi **tiếp một hướng**, chung đúng đầu mút (2,0). Đỉnh giữa có góc 180°, nhưng hai cạnh **không chồng**. Một đa giác đơn có thể chứa đỉnh như vậy.

```text
(0,0) -> (4,0) -> (2,0)
```

Cạnh thứ hai **đi ngược** trên một phần cạnh thứ nhất, tạo phần chồng từ (2,0) tới (4,0). Đây là cạnh chồng, không phải chỉ “thẳng hàng”, và khiến biên polygon không đơn theo hợp đồng của bài.

### 6.1. Đỉnh cuối lặp lại đỉnh đầu

Nhiều định dạng có:

```text
(0,0),(4,0),(4,4),(0,4),(0,0)
```

Hàm kiểm tra ở bài yêu cầu danh sách **không lặp đỉnh đầu tại phần tử cuối** vì nó tự đóng chu trình bằng cạnh từ đỉnh cuối về đầu. Nếu giữ phần tử cuối trùng đầu, dữ liệu có một đỉnh lặp và một cạnh độ dài 0, nên hàm trả false. Điều đó **không có nghĩa hình vuông hình học thực sự không đơn**; hãy chuẩn hóa kiểu biểu diễn trước khi gọi.

### 6.2. Hợp đồng kiểm tra đa giác đơn

Hàm `isSimpleNonzeroPolygon` trong chương trình yêu cầu:

- Ít nhất 3 đỉnh, **tất cả đỉnh khác tọa độ**, không có phần tử cuối trùng đầu.
- Diện tích có hướng gấp đôi khác 0.
- Mọi cặp **cạnh kề** chỉ giao tại **một đầu mút chung** (`TOUCH`), không `OVERLAP`.
- Mọi cặp **cạnh không kề** không giao (`NONE`).

Nó **cho phép đỉnh thẳng hàng 180°** nếu các cạnh chỉ chạm tại đỉnh, không chồng. Đây là kiểm tra polygon **đơn, diện tích khác 0**, không phải kiểm tra **lồi nghiêm ngặt**. Độ phức tạp O(n²) vì so từng cặp cạnh; với n rất lớn, có thể dùng kỹ thuật quét đường phức tạp hơn nhưng vẫn phải quy định rõ các ca biên.

## 7. Bao lồi với điểm trùng hoặc tất cả thẳng hàng

Thuật toán Andrew's monotone chain thường được dùng để xây **convex hull tối giản**:

1. Loại các tọa độ trùng bằng tập hợp.
2. Sắp xếp x tăng, nếu bằng x thì y tăng, bằng `Long.compare`.
3. Dựng lower/upper hull, bỏ điểm giữa nếu `orientation<=0`.
4. Ghép hai nửa và bỏ đỉnh lặp ở chỗ nối.

Chính sách `<=0` **loại các điểm thẳng hàng nằm giữa trên biên hull**. Nếu đề yêu cầu giữ **mọi điểm trên cạnh biên**, cần thay chính sách và kiểm tra riêng trường hợp tất cả điểm thẳng hàng.

```text
[(0,0),(0,0),(1,1),(2,2),(3,3),(2,2)]
    -> hull [(0,0),(3,3)]

[] -> hull []
[(0,0),(0,0)] -> hull [(0,0)]
```

Không mặc định hull phải có ≥3 đỉnh. Tập rỗng cho hull rỗng, một tọa độ phân biệt cho một điểm, mọi điểm cùng đường cho **hai đầu mút cực trị**.

## 8. Tạo test riêng cho ca suy biến

Các điểm ngẫu nhiên độc lập trên một miền rộng **hiếm khi** tình cờ tạo bốn điểm cùng đường và chồng nhau. Muốn kiểm thử có ý nghĩa, hãy tạo **những cấu hình có chủ đích**:

| Nhóm test | Mục tiêu |
| --- | --- |
| Hai đoạn điểm trùng/khác | `TOUCH`, `NONE` |
| Đoạn điểm nằm trên đoạn dài | `TOUCH` |
| Các đoạn trên cùng một đường với tham số t | `NONE`, `TOUCH`, `OVERLAP` |
| Hai đoạn qua một tâm theo hai hướng cắt nhau | `PROPER` |
| Hai đoạn chung một đầu mút | `TOUCH`, đôi khi `OVERLAP` nếu cùng đường ngược hướng |
| Tọa độ Long.MIN/MAX | Phát hiện overflow |
| Hull rỗng, một điểm, tất cả thẳng hàng | Chống giả định luôn có đa giác |
| Polygon lặp đầu-cuối, hình nơ, cạnh đi ngược | Kiểm tra biên không đơn |

Một **oracle độc lập** càng hữu ích: chương trình dưới đây dùng cách giải giao hai đường theo **tham số hữu tỉ** để đối chiếu phân loại đoạn không song song, và công thức định thức 3×3 khai triển riêng để kiểm tra giá trị cross.

## 9. Chương trình Java 17+ hoàn chỉnh

Tên tệp: **DegenerateGeometryDemo.java**. Chương trình xử lý cả đoạn độ dài 0, đoạn trùng/chồng, các đầu mút, hull suy biến và polygon tự cắt/cạnh chồng. Mã còn kiểm tra tính đối xứng của phép giao khi hoán đổi hai đoạn hoặc đảo thứ tự đầu mút.

```java
import java.math.BigInteger;
import java.util.*;

public class DegenerateGeometryDemo {
    record Point(long x, long y) {}
    enum Intersection { NONE, TOUCH, PROPER, OVERLAP }

    static BigInteger bi(long x) {
        return BigInteger.valueOf(x);
    }

    static BigInteger cross(Point a, Point b, Point c) {
        BigInteger ux = bi(b.x()).subtract(bi(a.x()));
        BigInteger uy = bi(b.y()).subtract(bi(a.y()));
        BigInteger vx = bi(c.x()).subtract(bi(a.x()));
        BigInteger vy = bi(c.y()).subtract(bi(a.y()));
        return ux.multiply(vy).subtract(uy.multiply(vx));
    }

    static int orientation(Point a, Point b, Point c) {
        return cross(a, b, c).signum();
    }

    static int compare(Point a, Point b) {
        int cx = Long.compare(a.x(), b.x());
        return cx != 0 ? cx : Long.compare(a.y(), b.y());
    }

    static boolean between(long first, long second, long value) {
        return Math.min(first, second) <= value
                && value <= Math.max(first, second);
    }

    static boolean onSegment(Point a, Point b, Point p) {
        return orientation(a, b, p) == 0
                && between(a.x(), b.x(), p.x())
                && between(a.y(), b.y(), p.y());
    }

    static Point minPoint(Point a, Point b) {
        return compare(a, b) <= 0 ? a : b;
    }

    static Point maxPoint(Point a, Point b) {
        return compare(a, b) >= 0 ? a : b;
    }

    // Intersection classification of CLOSED segments [a,b],[c,d].
    static Intersection classify(
            Point a, Point b, Point c, Point d) {
        Objects.requireNonNull(a, "a");
        Objects.requireNonNull(b, "b");
        Objects.requireNonNull(c, "c");
        Objects.requireNonNull(d, "d");

        // Zero-length segments are points.
        if (a.equals(b)) {
            return onSegment(c, d, a)
                    ? Intersection.TOUCH : Intersection.NONE;
        }
        if (c.equals(d)) {
            return onSegment(a, b, c)
                    ? Intersection.TOUCH : Intersection.NONE;
        }

        int o1 = orientation(a, b, c);
        int o2 = orientation(a, b, d);
        int o3 = orientation(c, d, a);
        int o4 = orientation(c, d, b);

        if (o1 == 0 && o2 == 0 && o3 == 0 && o4 == 0) {
            // Both nondegenerate segments lie on the same line.
            // Lexicographic point order is monotone along a line.
            Point left = maxPoint(minPoint(a, b), minPoint(c, d));
            Point right = minPoint(maxPoint(a, b), maxPoint(c, d));
            int relation = compare(left, right);
            if (relation > 0) return Intersection.NONE;
            if (relation == 0) return Intersection.TOUCH;
            return Intersection.OVERLAP;
        }

        if ((o1 == 0 && onSegment(a, b, c))
                || (o2 == 0 && onSegment(a, b, d))
                || (o3 == 0 && onSegment(c, d, a))
                || (o4 == 0 && onSegment(c, d, b))) {
            return Intersection.TOUCH;
        }
        if (o1 * o2 < 0 && o3 * o4 < 0) {
            return Intersection.PROPER;
        }
        return Intersection.NONE;
    }

    // Minimal hull: remove duplicate input points and intermediate
    // collinear points on each boundary edge.
    static List<Point> convexHull(List<Point> input) {
        Objects.requireNonNull(input, "input");
        Set<Point> distinct = new HashSet<>();
        for (Point p : input) {
            distinct.add(Objects.requireNonNull(p, "point"));
        }
        List<Point> points = new ArrayList<>(distinct);
        points.sort(DegenerateGeometryDemo::compare);
        if (points.size() <= 1) return List.copyOf(points);

        List<Point> lower = new ArrayList<>();
        for (Point p : points) {
            while (lower.size() >= 2
                    && orientation(
                            lower.get(lower.size() - 2),
                            lower.get(lower.size() - 1), p) <= 0) {
                lower.remove(lower.size() - 1);
            }
            lower.add(p);
        }

        List<Point> upper = new ArrayList<>();
        for (int i = points.size() - 1; i >= 0; i--) {
            Point p = points.get(i);
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

    static BigInteger signedTwiceArea(List<Point> polygon) {
        if (polygon.size() < 3) return BigInteger.ZERO;
        BigInteger area2 = BigInteger.ZERO;
        for (int i = 0; i < polygon.size(); i++) {
            Point a = polygon.get(i);
            Point b = polygon.get((i + 1) % polygon.size());
            area2 = area2.add(
                    bi(a.x()).multiply(bi(b.y()))
                            .subtract(
                                    bi(a.y()).multiply(bi(b.x()))));
        }
        return area2;
    }

    // A simple polygon with nonzero area, distinct vertices,
    // no repeated closing vertex, and no edge overlap.
    // Straight (180-degree) consecutive vertices are allowed.
    static boolean isSimpleNonzeroPolygon(List<Point> polygon) {
        Objects.requireNonNull(polygon, "polygon");
        int n = polygon.size();
        if (n < 3) return false;
        Set<Point> unique = new HashSet<>();
        for (Point p : polygon) {
            if (!unique.add(Objects.requireNonNull(p, "point"))) {
                return false;
            }
        }
        if (signedTwiceArea(polygon).signum() == 0) {
            return false;
        }

        for (int i = 0; i < n; i++) {
            Point a = polygon.get(i);
            Point b = polygon.get((i + 1) % n);
            for (int j = i + 1; j < n; j++) {
                Point c = polygon.get(j);
                Point d = polygon.get((j + 1) % n);
                Intersection kind = classify(a, b, c, d);
                boolean adjacent = j == i + 1
                        || (i == 0 && j == n - 1);
                if (adjacent) {
                    if (kind != Intersection.TOUCH) return false;
                } else if (kind != Intersection.NONE) {
                    return false;
                }
            }
        }
        return true;
    }

    // Independent orientation oracle via expanded 3x3 determinant.
    static BigInteger oracleCross(Point a, Point b, Point c) {
        return bi(a.x()).multiply(
                        bi(b.y()).subtract(bi(c.y())))
                .add(bi(b.x()).multiply(
                        bi(c.y()).subtract(bi(a.y()))))
                .add(bi(c.x()).multiply(
                        bi(a.y()).subtract(bi(b.y()))));
    }

    static boolean oracleContains(Point a, Point b, Point p) {
        return oracleCross(a, b, p).signum() == 0
                && between(a.x(), b.x(), p.x())
                && between(a.y(), b.y(), p.y());
    }

    record Vector(BigInteger x, BigInteger y) {}

    static Vector difference(Point a, Point b) {
        return new Vector(
                bi(b.x()).subtract(bi(a.x())),
                bi(b.y()).subtract(bi(a.y())));
    }

    static BigInteger det(Vector a, Vector b) {
        return a.x().multiply(b.y())
                .subtract(a.y().multiply(b.x()));
    }

    // Independent oracle:
    // solve [a,b] and [c,d] by rational parameters t,u in [0,1].
    static Intersection rationalOracle(
            Point a, Point b, Point c, Point d) {
        if (a.equals(b)) {
            return oracleContains(c, d, a)
                    ? Intersection.TOUCH : Intersection.NONE;
        }
        if (c.equals(d)) {
            return oracleContains(a, b, c)
                    ? Intersection.TOUCH : Intersection.NONE;
        }

        Vector r = difference(a, b);
        Vector s = difference(c, d);
        Vector w = difference(a, c);
        BigInteger den = det(r, s);

        if (den.signum() == 0) {
            if (oracleCross(a, b, c).signum() != 0) {
                return Intersection.NONE;
            }
            Point low = maxPoint(minPoint(a, b), minPoint(c, d));
            Point high = minPoint(maxPoint(a, b), maxPoint(c, d));
            int cmp = compare(low, high);
            return cmp > 0 ? Intersection.NONE
                    : cmp == 0 ? Intersection.TOUCH
                    : Intersection.OVERLAP;
        }

        BigInteger tn = det(w, s);
        BigInteger un = det(w, r);
        if (den.signum() < 0) {
            den = den.negate();
            tn = tn.negate();
            un = un.negate();
        }

        if (tn.signum() < 0 || un.signum() < 0
                || tn.compareTo(den) > 0
                || un.compareTo(den) > 0) {
            return Intersection.NONE;
        }
        boolean strict = tn.signum() > 0 && un.signum() > 0
                && tn.compareTo(den) < 0
                && un.compareTo(den) < 0;
        return strict ? Intersection.PROPER : Intersection.TOUCH;
    }

    static Point smallPoint(Random rng) {
        return new Point(rng.nextInt(31) - 15,
                rng.nextInt(31) - 15);
    }

    static long coordinate(Random rng) {
        return switch (rng.nextInt(12)) {
            case 0 -> Long.MIN_VALUE;
            case 1 -> Long.MAX_VALUE;
            case 2 -> Long.MIN_VALUE + 1;
            case 3 -> Long.MAX_VALUE - 1;
            default -> rng.nextInt(41) - 20;
        };
    }

    static Point extremePoint(Random rng) {
        return new Point(coordinate(rng), coordinate(rng));
    }

    static int[] observed = new int[Intersection.values().length];

    static void checkSegments(
            Point a, Point b, Point c, Point d) {
        Intersection actual = classify(a, b, c, d);
        Intersection oracle = rationalOracle(a, b, c, d);
        if (actual != oracle
                || classify(c, d, a, b) != actual
                || classify(b, a, d, c) != actual) {
            throw new AssertionError(
                    "segment mismatch: "
                    + List.of(a, b, c, d)
                    + " actual=" + actual + " oracle=" + oracle);
        }
        observed[actual.ordinal()]++;
    }

    static void randomizedCrossCheck() {
        Random rng = new Random(20261110L);

        for (int i = 0; i < 3000; i++) {
            Point a = extremePoint(rng);
            Point b = extremePoint(rng);
            Point c = extremePoint(rng);
            BigInteger exact = cross(a, b, c);
            if (!exact.equals(oracleCross(a, b, c))
                    || !exact.equals(cross(b, c, a))
                    || !exact.equals(cross(a, c, b).negate())) {
                throw new AssertionError("orientation mismatch");
            }
        }

        for (int i = 0; i < 2000; i++) {
            checkSegments(extremePoint(rng), extremePoint(rng),
                    extremePoint(rng), extremePoint(rng));
        }

        // Collinear groups, including overlaps, touches and points.
        for (int i = 0; i < 2000; i++) {
            Point origin = smallPoint(rng);
            long dx = rng.nextInt(7) - 3;
            long dy = rng.nextInt(7) - 3;
            if (dx == 0 && dy == 0) dx = 1;
            long t1 = rng.nextInt(15) - 7;
            long t2 = rng.nextInt(15) - 7;
            long t3 = rng.nextInt(15) - 7;
            long t4 = rng.nextInt(15) - 7;
            Point a = new Point(origin.x() + dx * t1,
                    origin.y() + dy * t1);
            Point b = new Point(origin.x() + dx * t2,
                    origin.y() + dy * t2);
            Point c = new Point(origin.x() + dx * t3,
                    origin.y() + dy * t3);
            Point d = new Point(origin.x() + dx * t4,
                    origin.y() + dy * t4);
            checkSegments(a, b, c, d);
        }

        // Guaranteed proper crossing: two transverse centered edges.
        for (int i = 0; i < 1000; i++) {
            Point center = smallPoint(rng);
            long dx = rng.nextInt(9) - 4;
            long dy = rng.nextInt(9) - 4;
            if (dx == 0 && dy == 0) dx = 1;
            checkSegments(
                    new Point(center.x() - dx, center.y() - dy),
                    new Point(center.x() + dx, center.y() + dy),
                    new Point(center.x() - dy, center.y() + dx),
                    new Point(center.x() + dy, center.y() - dx));
        }

        // A common endpoint; sometimes also collinear.
        for (int i = 0; i < 1000; i++) {
            Point a = smallPoint(rng);
            Point b = smallPoint(rng);
            Point d = smallPoint(rng);
            checkSegments(a, b, b, d);
        }

        // Point-like segments, both equal and distinct.
        for (int i = 0; i < 1000; i++) {
            Point a = smallPoint(rng);
            Point c = i % 2 == 0 ? a : smallPoint(rng);
            Point d = i % 3 == 0 ? c : smallPoint(rng);
            checkSegments(a, a, c, d);
        }

        for (int i = 0; i < observed.length; i++) {
            if (observed[i] == 0) {
                throw new AssertionError(
                        "intersection class not covered: " + i);
            }
        }

        for (int i = 0; i < 600; i++) {
            int n = rng.nextInt(18);
            List<Point> input = new ArrayList<>();
            for (int j = 0; j < n; j++) {
                input.add(new Point(
                        rng.nextInt(21) - 10,
                        rng.nextInt(21) - 10));
            }
            List<Point> hull = convexHull(input);
            if (new HashSet<>(hull).size() != hull.size()
                    || !input.containsAll(hull)) {
                throw new AssertionError("duplicate or invented hull");
            }
            if (hull.size() >= 3) {
                if (signedTwiceArea(hull).signum() <= 0) {
                    throw new AssertionError("non-CCW hull");
                }
                for (int j = 0; j < hull.size(); j++) {
                    Point a = hull.get(j);
                    Point b = hull.get((j + 1) % hull.size());
                    for (Point p : input) {
                        if (oracleCross(a, b, p).signum() < 0) {
                            throw new AssertionError(
                                    "input point outside hull");
                        }
                    }
                }
            } else if (hull.size() == 2) {
                for (Point p : input) {
                    if (!oracleContains(
                            hull.get(0), hull.get(1), p)) {
                        throw new AssertionError("incorrect line hull");
                    }
                }
            } else if (input.size() > 0 && hull.size() != 1) {
                throw new AssertionError("missing point hull");
            }
        }

        System.out.println(
                "Random cross-check: PASS "
                + "(3000 triples, 7000 segment pairs, 600 hulls)");
        System.out.println(
                "Observed classes [NONE, TOUCH, PROPER, OVERLAP]: "
                + Arrays.toString(observed));
    }

    public static void main(String[] args) {
        Point o = new Point(0, 0);
        Point x = new Point(4, 0);
        Point top = new Point(2, 3);

        System.out.println(
                "Turn: " + orientation(o, x, top)
                + ", collinearOutside="
                + onSegment(o, x, new Point(7, 0)));

        System.out.println(
                "Duplicate points: " + classify(
                        o, o, o, o));

        System.out.println(
                "Point on segment: " + classify(
                        new Point(2, 0), new Point(2, 0),
                        o, x));

        System.out.println(
                "Distinct points: " + classify(
                        o, o, x, x));

        System.out.println(
                "Proper crossing: " + classify(
                        new Point(0, 0), new Point(4, 4),
                        new Point(0, 4), new Point(4, 0)));

        System.out.println(
                "Endpoint touch: " + classify(
                        o, x, x, new Point(4, 3)));

        System.out.println(
                "Collinear overlap: " + classify(
                        new Point(0, 0), new Point(6, 0),
                        new Point(3, 0), new Point(9, 0)));

        System.out.println(
                "Collinear touch: " + classify(
                        o, new Point(3, 0),
                        new Point(3, 0), new Point(7, 0)));

        System.out.println(
                "Collinear disjoint: " + classify(
                        o, new Point(2, 0),
                        new Point(3, 0), new Point(7, 0)));

        System.out.println(
                "Parallel disjoint: " + classify(
                        o, x,
                        new Point(0, 2), new Point(4, 2)));

        List<Point> candidates = List.of(
                new Point(0, 0), new Point(0, 0),
                new Point(1, 1), new Point(2, 2),
                new Point(3, 3), new Point(2, 2));
        System.out.println(
                "All-collinear hull: " + convexHull(candidates));

        System.out.println(
                "Empty hull: " + convexHull(List.of()));
        System.out.println(
                "Single-point hull: " + convexHull(
                        List.of(o, o)));

        List<Point> square = List.of(
                o, new Point(4, 0),
                new Point(4, 4), new Point(0, 4));
        List<Point> closedSquare = List.of(
                o, new Point(4, 0),
                new Point(4, 4), new Point(0, 4), o);
        List<Point> bowtie = List.of(
                o, new Point(4, 4),
                new Point(0, 4), new Point(4, 0));
        List<Point> overlappingEdge = List.of(
                o, new Point(4, 0),
                new Point(2, 0), new Point(2, 2),
                new Point(0, 2));
        List<Point> straightVertex = List.of(
                o, new Point(2, 0),
                new Point(4, 0), new Point(4, 4),
                new Point(0, 4));

        System.out.println(
                "Simple square: "
                + isSimpleNonzeroPolygon(square));
        System.out.println(
                "Repeated closing vertex accepted: "
                + isSimpleNonzeroPolygon(closedSquare));
        System.out.println(
                "Bowtie simple: "
                + isSimpleNonzeroPolygon(bowtie));
        System.out.println(
                "Overlapping-edge polygon simple: "
                + isSimpleNonzeroPolygon(overlappingEdge));
        System.out.println(
                "Straight boundary vertex simple: "
                + isSimpleNonzeroPolygon(straightVertex));

        Point min = new Point(Long.MIN_VALUE, Long.MIN_VALUE);
        Point maxX = new Point(Long.MAX_VALUE, Long.MIN_VALUE);
        Point maxY = new Point(Long.MIN_VALUE, Long.MAX_VALUE);
        BigInteger hugeCross = cross(min, maxX, maxY);
        System.out.println(
                "Long extremes: sign=" + hugeCross.signum()
                + ", decimalDigits="
                + hugeCross.toString().length());

        randomizedCrossCheck();
    }
}
```

## 10. Biên dịch, chạy và kiểm tra kết quả

Lưu mã vào **DegenerateGeometryDemo.java** rồi dùng JDK 17 trở lên:

```bash
javac DegenerateGeometryDemo.java
java DegenerateGeometryDemo
```

**Stdout chính xác của chương trình:**

```text
Turn: 1, collinearOutside=false
Duplicate points: TOUCH
Point on segment: TOUCH
Distinct points: NONE
Proper crossing: PROPER
Endpoint touch: TOUCH
Collinear overlap: OVERLAP
Collinear touch: TOUCH
Collinear disjoint: NONE
Parallel disjoint: NONE
All-collinear hull: [Point[x=0, y=0], Point[x=3, y=3]]
Empty hull: []
Single-point hull: [Point[x=0, y=0]]
Simple square: true
Repeated closing vertex accepted: false
Bowtie simple: false
Overlapping-edge polygon simple: false
Straight boundary vertex simple: true
Long extremes: sign=1, decimalDigits=39
Random cross-check: PASS (3000 triples, 7000 segment pairs, 600 hulls)
Observed classes [NONE, TOUCH, PROPER, OVERLAP]: [2600, 1763, 1427, 1210]
```

### 10.1. Diễn giải các dòng output

**Turn:** Bộ ba (0,0)→(4,0)→(2,3) có dấu +1 (rẽ trái). Điểm (7,0) tuy thẳng hàng nhưng ngoài đoạn, nên `collinearOutside=false`.

**Duplicate points:** Hai đoạn điểm cùng tại (0,0) giao đúng một điểm → `TOUCH`.

**Point on segment:** Đoạn điểm tại (2,0) thuộc đoạn ngang (0,0)–(4,0) → `TOUCH`.

**Distinct points:** Hai đoạn điểm khác nhau (0,0) và (4,0) → `NONE`.

**Proper crossing:** Hai đường chéo cắt trong nội điểm của cả hai đoạn → `PROPER`.

**Endpoint touch:** Hai đoạn chỉ có chung đầu mút (4,0) → `TOUCH`.

**Collinear overlap:** Giao trên đoạn [(3,0),(6,0)] có độ dài dương → `OVERLAP`.

**Collinear touch:** Hai đoạn ngang chỉ có chung x=3 → `TOUCH`.

**Collinear disjoint:** Hai đoạn cùng đường nhưng hai khoảng tách rời → `NONE`.

**Parallel disjoint:** Hai đoạn thuộc hai đường y=0 và y=2 → `NONE`.

**All-collinear hull:** Điểm input trùng và thẳng hàng được rút thành hai điểm cực trị (0,0) và (3,3).

**Empty hull / Single-point hull:** Kết quả là [] hoặc một điểm, không sinh đa giác giả.

**Simple square:** Danh sách bốn góc hình vuông là một đa giác đơn có diện tích khác 0.

**Repeated closing vertex accepted=false:** API tự tạo cạnh đóng nên phải bỏ đỉnh cuối trùng đầu trước khi gọi. Đây là **ràng buộc định dạng input**, không phải kết luận rằng hình vuông về mặt hình học không đơn.

**Bowtie simple=false:** Hình nơ có các cạnh không kề tự cắt, nên không đơn.

**Overlapping-edge polygon simple=false:** Cạnh đáy đi từ (0,0) đến (4,0) rồi quay về (2,0), nên hai cạnh kề chồng đoạn dài dương.

**Straight boundary vertex simple=true:** Hai cạnh đáy đi liên tiếp qua (0,0)→(2,0)→(4,0), chỉ chung đỉnh giữa, không chồng.

**Long extremes:** Số cross tính bằng BigInteger vẫn chính xác, có 39 chữ số thập phân; kết quả `sign=1`.

**Random cross-check:** Với seed 20261110, chương trình kiểm tra 3.000 bộ ba điểm có cả tọa độ cực trị, 7.000 cặp đoạn gồm các nhóm ngẫu nhiên/đồng tuyến/giao chéo/chung đầu mút/đoạn điểm, và 600 bộ điểm hull. Oracle không chỉ dùng lại điều kiện bốn dấu: nó giải hai đường theo **tham số hữu tỉ** để đối chiếu giao không song song, và dùng định thức 3×3 khai triển để đối chiếu cross. Mọi lớp giao đều được gặp ít nhất một lần; nếu có sai lệch, ném `AssertionError`. Với seed cố định, số ca `[NONE,TOUCH,PROPER,OVERLAP]` là `[2600,1763,1427,1210]`, tổng đúng 7.000.

## 11. Chứng minh tính đúng

### 11.1. Điểm thuộc đoạn, kể cả đoạn suy biến

Nếu P thuộc đoạn đóng [A,B], tồn tại t∈[0,1] sao cho P=A+t(B−A). Vì AP=tAB, cross(AB,AP)=0; tọa độ P cũng nằm trong hộp đầu mút. Ngược lại, khi A≠B, cross=0 buộc AP cùng phương AB; điều kiện hộp trên một trục có AB khác 0 buộc hệ số t nằm trong [0,1]. Khi A=B, hộp chỉ chứa A. Vì vậy hai điều kiện là cần và đủ.

### 11.2. Đoạn điểm

Nếu A=B thì [A,B]={A}. Giao với [C,D] không rỗng khi và chỉ khi `onSegment(C,D,A)` đúng. Khi đó giao chỉ có **một điểm**. Vì thế phân loại `TOUCH` là đúng; nếu không, `NONE`.

### 11.3. Giao hai đoạn cùng đường

Hai đoạn không suy biến cùng đường tương ứng hai khoảng đóng theo thứ tự từ điển. Giao hai khoảng là rỗng, một điểm hoặc một khoảng có độ dài dương tùy max(lower) so với min(upper). Ba nhánh của thuật toán chính xác là `NONE`, `TOUCH` và `OVERLAP`.

### 11.4. Giao không đồng tuyến

Nếu giao tại đầu mút, ít nhất một điểm biên nằm trên đoạn kia và kiểm tra `onSegment` phát hiện, trả `TOUCH`. Nếu giao ở nội điểm hai đoạn, cặp đầu mút của mỗi đoạn nằm hai phía nghiêm ngặt của đường chứa đoạn kia; do đó `o1*o2<0 && o3*o4<0`. Ngược lại, hai cặp dấu đối nhau nghiêm ngặt bảo đảm giao duy nhất bên trong hai đoạn, trả `PROPER`. Nếu cả điều kiện biên và điều kiện nghiêm ngặt sai, chúng không giao. Vì các đoạn điểm và cặp đồng tuyến được xét riêng trước, không có trường hợp bị bỏ sót.

### 11.5. Tính đơn của đa giác

Trong danh sách đỉnh phân biệt theo chu trình, hai cạnh kề vốn có chung một đầu mút; để không đi trùng biên, chúng chỉ được giao ở đúng một điểm ấy. Hai cạnh không kề phải không giao để tránh tự cắt hay tự chạm. Diện tích khác 0 loại trường hợp chu trình suy biến về hình một chiều. Đó là hợp đồng kiểm tra của hàm `isSimpleNonzeroPolygon`, không phải một kiểm tra tính lồi.

## 12. Phân tích độ phức tạp

Với tọa độ kiểu `long` 64-bit cố định, mỗi phép tính BigInteger định hướng có số bit toán hạng bị chặn; phân tích dưới đây tính theo số lượng điểm.

| Tác vụ | Thời gian | Bộ nhớ phụ |
| --- | --- | --- |
| So tọa độ, tính hướng quay | O(1) | O(1) |
| Kiểm tra thuộc đoạn | O(1) | O(1) |
| Phân loại hai đoạn | O(1) | O(1) |
| Bao lồi Andrew monotone chain | O(n log n), do sort; stack O(n) | O(n) |
| Kiểm tra đa giác đơn với k đỉnh | O(k²), so tất cả cặp cạnh | O(k) Set đỉnh |
| Shoelace trên k đỉnh | O(k) | O(1) biến tổng |

**Không khẳng định BigInteger luôn O(1)** khi tọa độ có độ dài bit không giới hạn: chi phí cộng/trừ/nhân tăng theo số bit. Với `long` đầu vào, kích thước trung gian bị chặn, nên O(1) theo n là phù hợp.

## 13. Những lỗi thường gặp

1. Coi hai bản ghi khác ID luôn có tọa độ khác nhau.
2. Loại trùng trước khi đếm số bản ghi hay tần suất.
3. So tham chiếu thay vì so tọa độ khi cần equality hình học.
4. Dùng epsilon không bắc cầu làm tiêu chí Set/Map.
5. Coi A=B vẫn tạo đường thẳng AB có hướng thông thường.
6. Chỉ dùng cross=0 để kết luận điểm thuộc đoạn.
7. Chỉ kiểm tra hộp tọa độ mà không kiểm tra cross=0.
8. Chỉ xét khoảng x mà bỏ khoảng y.
9. Dùng công thức chia cho độ dài đoạn khi A=B.
10. Phân loại hai đoạn điểm trùng nhau thành OVERLAP.
11. Coi một đoạn điểm nằm trên đoạn dài là PROPER.
12. Coi mọi cặp đoạn cùng đường đều có giao.
13. Coi mọi giao cùng đường là chồng đoạn dài dương.
14. Trả TOUCH sớm trước khi kiểm tra OVERLAP đồng tuyến.
15. So hai khoảng từ điển khi chưa xác nhận hai đoạn cùng đường.
16. So tọa độ long bằng phép trừ, gây nguy cơ overflow.
17. Trừ hai long rồi mới bọc BigInteger.
18. Nhân long rồi mới bọc BigInteger.
19. Dùng double gần suy biến mà không xét lỗi dấu.
20. Dùng epsilon tùy ý cho bài tọa độ nguyên chính xác.
21. Nhầm đỉnh 180° đi tiếp với cạnh đi ngược chồng nhau.
22. Quên chuẩn hóa polygon có đỉnh cuối trùng đầu theo API.
23. Không kiểm tra cặp cạnh kề nên bỏ cạnh chồng.
24. Chỉ nhìn diện tích khác 0 rồi kết luận polygon đơn.
25. Coi ba đỉnh thẳng hàng là tam giác diện tích dương.
26. Quên hull rỗng/hull một điểm/hull hai điểm.
27. Không loại trùng khi cần bao lồi tối giản.
28. Không xác định giữ hay bỏ các điểm thẳng hàng trên biên hull.
29. Không bỏ đầu mút lặp khi ghép hai nửa hull.
30. Dùng `o1!=o2 && o3!=o4` mà bỏ trường hợp orientation=0.
31. Không xác minh tính đối xứng khi đổi thứ tự hai đoạn.
32. Không xác minh bất biến khi đảo đầu mút một đoạn.
33. Chỉ sinh test ngẫu nhiên độc lập, hiếm khi phủ cạnh chồng.
34. Không thử đoạn trùng hoàn toàn và hai đoạn chạm đúng một điểm.
35. Không thử tọa độ cực trị signed long.
36. Cho rằng validator trả false với đỉnh cuối trùng đầu nghĩa là hình vuông hình học không đơn.
37. Áp thuật toán đoạn đóng cho bài dùng đoạn mở.
38. Không có oracle độc lập để đối chiếu các nhánh suy biến.

## 14. Bài tập tự luyện có đáp án

**Bài 1.** Hai điểm nguyên trùng nhau khi nào?

**Đáp án:** Khi cả x lẫn y tương ứng bằng nhau.

**Bài 2.** Ba bản ghi [(2,3),(5,7),(2,3)] có bao nhiêu tọa độ phân biệt?

**Đáp án:** 2.

**Bài 3.** Một tọa độ xuất hiện k lần tạo bao nhiêu cặp bản ghi trùng?

**Đáp án:** k(k−1)/2.

**Bài 4.** Nếu A=B, cross(A,B,C) bằng mấy?

**Đáp án:** 0 với mọi C, vì AB là vector không.

**Bài 5.** Với A=(0,0),B=(4,0),P=(7,0), onSegment?

**Đáp án:** false dù ba điểm thẳng hàng.

**Bài 6.** Với A=B=(3,4), P=(3,4), onSegment?

**Đáp án:** true.

**Bài 7.** Với A=B=(3,4), P=(3,5), onSegment?

**Đáp án:** false.

**Bài 8.** Hai đoạn điểm tại cùng (0,0) thuộc loại gì?

**Đáp án:** TOUCH.

**Bài 9.** Hai đoạn điểm khác nhau tại (0,0) và (1,1)?

**Đáp án:** NONE.

**Bài 10.** Đoạn điểm tại (2,0) và đoạn [(0,0),(4,0)]?

**Đáp án:** TOUCH.

**Bài 11.** Hai đường chéo (0,0)–(4,4) và (0,4)–(4,0)?

**Đáp án:** PROPER.

**Bài 12.** [(0,0),(6,0)] và [(3,0),(9,0)]?

**Đáp án:** OVERLAP trên [(3,0),(6,0)].

**Bài 13.** [(0,0),(3,0)] và [(3,0),(7,0)]?

**Đáp án:** TOUCH.

**Bài 14.** [(0,0),(2,0)] và [(3,0),(7,0)]?

**Đáp án:** NONE.

**Bài 15.** Hai đoạn không suy biến trùng hoàn toàn?

**Đáp án:** OVERLAP, không phải TOUCH.

**Bài 16.** Hai đoạn điểm trùng hoàn toàn?

**Đáp án:** TOUCH vì phần giao không có độ dài dương.

**Bài 17.** Điều kiện proper crossing khi không đồng tuyến?

**Đáp án:** `o1*o2<0 && o3*o4<0`.

**Bài 18.** Vì sao phải xét đồng tuyến trước kiểm tra chạm?

**Đáp án:** Vì đoạn chồng có thể chứa đầu mút; trả TOUCH quá sớm sẽ bỏ OVERLAP.

**Bài 19.** Khi nào so khoảng theo thứ tự từ điển đủ để xác định giao đoạn?

**Đáp án:** Sau khi đã xác nhận cả hai đoạn không suy biến nằm trên cùng một đường.

**Bài 20.** `(0,0)→(2,0)→(4,0)` có cạnh chồng không?

**Đáp án:** Không; hai cạnh chỉ chung một đầu mút.

**Bài 21.** `(0,0)→(4,0)→(2,0)` có cạnh chồng không?

**Đáp án:** Có; chúng chồng từ (2,0) đến (4,0).

**Bài 22.** Bao lồi của [(0,0),(0,0),(1,1),(2,2),(3,3)]?

**Đáp án:** Hai đầu mút [(0,0),(3,3)].

**Bài 23.** Nếu chỉ một tọa độ phân biệt, hull có bao nhiêu điểm?

**Đáp án:** 1.

**Bài 24.** Vì sao `BigInteger.valueOf(bx-ax)` chưa an toàn?

**Đáp án:** Hiệu long có thể tràn trước khi chuyển; phải chuyển hai tọa độ riêng rồi trừ bằng BigInteger.

**Bài 25.** Chi phí validator so tất cả cặp cạnh của polygon n đỉnh?

**Đáp án:** O(n²).

**Bài 26.** Một polygon có diện tích khác 0 chắc chắn đơn không?

**Đáp án:** Không; cạnh không kề vẫn có thể cắt nhau hoặc chồng nhau.

**Bài 27.** Đỉnh thẳng hàng 180° có nhất thiết làm polygon không đơn không?

**Đáp án:** Không, nếu hai cạnh kề chỉ chạm tại đầu mút, không chồng.

**Bài 28.** Vì sao cần test cấu hình đồng tuyến có chủ đích?

**Đáp án:** Các test random độc lập thường hiếm tạo ra cạnh chồng chính xác; phải dựng riêng các đoạn cùng đường để phủ nhánh.

**Bài 29.** Nếu đề dùng đoạn mở, có tính chạm đầu mút là giao không?

**Đáp án:** Không theo định nghĩa đoạn mở; cần sửa chính sách so với mã đoạn đóng ở bài.

**Bài 30.** Những kiểm tra đối xứng nào giúp phát hiện lỗi giao đoạn?

**Đáp án:** Đổi thứ tự hai đoạn và đảo chiều các đầu mút không được thay đổi tập giao hay phân loại.

## 15. Checklist trước khi áp dụng

- [ ] Xác định điểm trùng theo tọa độ hay theo ID bản ghi.
- [ ] Chốt quy ước đoạn đóng/mở và xử lý đoạn độ dài 0.
- [ ] Tính orientation chính xác và không bỏ trường hợp 0.
- [ ] Phân biệt thẳng hàng với thuộc đoạn bằng bounding box.
- [ ] Tách đoạn điểm trước khi xử lý giao hai đoạn dài.
- [ ] Khi cùng đường, phân biệt giao rỗng, một điểm và đoạn dương.
- [ ] Khi khác đường, kiểm tra chạm biên rồi mới dùng điều kiện proper crossing.
- [ ] Khi làm polygon, xét cả cạnh kề có thể chồng nhau.
- [ ] Chuẩn hóa danh sách đỉnh polygon lặp đầu/cuối theo hợp đồng.
- [ ] Khi làm hull, xử lý 0/1/2 đỉnh và chính sách điểm biên thẳng hàng.
- [ ] Dùng Long.compare và chuyển tọa độ sang BigInteger trước phép trừ/nhân.
- [ ] Sinh test suy biến có chủ đích và đối chiếu oracle độc lập.

## Kết luận

Điểm trùng, thẳng hàng và cạnh chồng là các cấu hình buộc thuật toán hình học phải **định nghĩa và xử lý có chủ đích**. Tích có hướng bằng 0 không có nghĩa điểm nằm trong đoạn; hai đoạn cùng đường không có nghĩa giao thành một cạnh chồng; và hai cạnh kề thẳng hàng không nhất thiết khiến đa giác không đơn.

Một cài đặt đáng tin cậy phải xác định rõ **đoạn điểm**, **giao một điểm** và **giao đoạn dương**, đồng thời bảo toàn tính chính xác số học khi tính định hướng. Mã Java 17 trong bài làm rõ các ranh giới ấy bằng các nhánh tường minh và kiểm thử đối chiếu độc lập trên hàng nghìn tình huống.
