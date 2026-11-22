# Cặp điểm gần nhất bằng chia để trị

## Mục tiêu

Trong phần **Hình học tính toán**, bài toán **cặp điểm gần nhất** (*closest pair of points*) yêu cầu chọn hai điểm khác nhau trong một tập điểm 2D để **khoảng cách Euclid giữa chúng nhỏ nhất**.

Nếu kiểm tra tất cả các cặp, thuật toán mất **O(n²)**. Với kỹ thuật **chia để trị** và duy trì đúng hai thứ tự theo trục X, Y, ta có thể giải trong **O(n log n)** thời gian và **O(n)** bộ nhớ phụ. Điểm cốt lõi không chỉ là chia đôi: cần xử lý những cặp nằm qua đường chia mà không thử mọi cặp chéo.

Sau bài học, bạn sẽ có thể:

- Phát biểu bài toán chính xác, hiểu trường hợp n<2, điểm trùng tọa độ và cặp đồng hạng.
- So sánh **bình phương khoảng cách** để tránh căn bậc hai và lỗi số thực khi chọn min.
- Viết lời giải vét cạn làm oracle kiểm thử.
- Giải thích đường chia, nửa trái/nửa phải và dải **strip** quanh đường chia.
- Chứng minh vì sao mỗi điểm chỉ cần đối chiếu tối đa **7 điểm tiếp theo theo Y** trong mô hình Euclid 2D.
- Duy trì mảng điểm sorted Y bằng **merge**, tránh sắp xếp lại ở mọi nút.
- Chứng minh truy hồi `T(n)=2T(n/2)+O(n)=O(n log n)`.
- Cài đặt Java 17+ với tọa độ `long` và phép đo khoảng cách `BigInteger` chính xác, kể cả hai cực trị long.
- Kiểm tra điểm trùng, nhiều hoành độ/tung độ bằng nhau, tọa độ âm, trường hợp cặp chéo tối ưu và dữ liệu hòa.
- Phân biệt cách chia để trị O(n log n) với những triển khai có thể thành O(n log² n), cũng như với sweep line và vét cạn.

---

## 1. Phát biểu bài toán và đầu ra

Cho n điểm:

\[
P=\{p_0,p_1,\ldots,p_{n-1}\},\qquad
p_i=(x_i,y_i),
\]

với `n≥2`.

Cần tìm hai chỉ số `i\ne j` để:

\[
d(p_i,p_j)=
\sqrt{(x_i-x_j)^2+(y_i-y_j)^2}
\]

nhỏ nhất.

Khoảng cách dùng trong bài là **Euclid** trong **mặt phẳng hai chiều**. Nếu đề dùng Manhattan, Chebyshev hoặc không gian ba chiều, kỹ thuật và cận số láng giềng phải phân tích lại.

### 1.1. Một điểm đầu vào là một phần tử, không chỉ là tọa độ

Ví dụ:

```text
id=0 -> (7,7)
id=1 -> (1,3)
id=2 -> (7,7)
```

Hai điểm id 0 và 2 là **hai phần tử khác chỉ số**, dù tọa độ giống nhau. Chúng tạo cặp hợp lệ và có khoảng cách bằng **0**.

Không được xóa điểm trùng nếu bài toán yêu cầu tìm cặp giữa các phần tử đầu vào, vì xóa có thể làm biến mất kết quả tối ưu 0.

### 1.2. Cặp đồng hạng

Có thể có nhiều cặp có cùng khoảng cách nhỏ nhất, chẳng hạn các cạnh của hình vuông. Bài này chỉ cần trả **một cặp tối ưu bất kỳ**, không bắt buộc chọn cặp có id từ điển nhỏ nhất.

Quy ước này quan trọng: mã Java chỉ cập nhật khi tìm được **khoảng cách nhỏ hơn nghiêm ngặt**. Những cặp bằng nhau không bắt buộc được liệt kê. Nếu đề yêu cầu toàn bộ cặp đồng hạng hoặc tie-break canonical, phải thiết kế xử lý bổ sung.

### 1.3. Dữ liệu n<2

Khi không có ít nhất hai phần tử, bài toán không có cặp hợp lệ. Chương trình mẫu ném `IllegalArgumentException` với n<2. Một đề cụ thể có thể yêu cầu định dạng đầu ra khác; khi thi, ưu tiên đặc tả đề.

---

## 2. Tại sao dùng bình phương khoảng cách?

Bình phương khoảng cách Euclid giữa hai điểm:

\[
\boxed{D(p,q)=(x_p-x_q)^2+(y_p-y_q)^2.}
\]

Vì căn bậc hai tăng nghiêm ngặt trên miền không âm:

\[
D(p,q)<D(u,v)
\iff
\sqrt{D(p,q)}<\sqrt{D(u,v)}.
\]

Do đó, việc so sánh hai cặp theo khoảng cách **không cần sqrt**.

### Lợi ích

1. Không phải tính căn bậc hai tại mỗi cặp.
2. Với tọa độ nguyên và phép số học chính xác, giá trị D là một **số nguyên** có thể so sánh không có sai số làm tròn.
3. Bước lọc strip cũng có thể thực hiện bằng bình phương:
   \[
   (x-splitX)^2<D_{\mathrm{best}}.
   \]
4. Bước loại theo Y dùng:
   \[
   (y_j-y_i)^2\ge D_{\mathrm{best}}
   \]
   để kết luận cặp không thể cải thiện.

Chỉ khi **cần hiển thị khoảng cách thực**, ta mới lấy căn bậc hai của D. Mã Java trả D chính xác và cung cấp thêm một phương thức trả khoảng cách `double` gần đúng để hiển thị.

### 2.1. Vấn đề overflow

Không nên viết:

```java
long dx = p.x() - q.x();
long squared = dx * dx;
```

nếu tọa độ có thể gần `Long.MIN_VALUE` hoặc `Long.MAX_VALUE`. Hiệu đã có thể vượt giới hạn long **trước khi bình phương**; phép bình phương lại có thể tràn tiếp.

Chương trình sử dụng:

```java
BigInteger dx = BigInteger.valueOf(p.x())
        .subtract(BigInteger.valueOf(q.x()));

BigInteger dxSquared = dx.multiply(dx);
```

Tức là chuyển từng toán hạng sang `BigInteger` **trước phép trừ**. Cách này giữ kết quả chính xác trong mọi trường hợp tọa độ long 64-bit.

---

## 3. Lời giải vét cạn O(n²)

Có:

\[
\binom n2=\frac{n(n-1)}2
\]

cặp chỉ số `i<j`.

Giả mã:

```text
BRUTE_FORCE(points):
    require n>=2

    best = distanceSquared(points[0], points[1])
    pair = (0,1)

    for i = 0..n-1:
        for j = i+1..n-1:
            candidate = distanceSquared(points[i],points[j])
            if candidate < best:
                best = candidate
                pair = (i,j)

    return (pair,best)
```

**Tính đúng:** mọi cặp hợp lệ được kiểm tra một lần, và best là nhỏ nhất trong các cặp đã kiểm tra. Sau khi duyệt hết, best là tối ưu toàn cục.

**Chi phí:** O(n²) phép tính khoảng cách, O(1) bộ nhớ phụ ngoài input và kết quả.

Với n nhỏ, đây là lựa chọn tuyệt vời vì ít bug. Với n lớn, đây còn là **oracle tham chiếu** để kiểm thử thuật toán chia để trị trên các tập điểm nhỏ sinh ngẫu nhiên.

---

## 4. Cấu trúc chia để trị

Ý tưởng:

1. Sort các điểm theo trục X.
2. Chia dãy theo **chỉ số giữa**, tạo nửa trái và nửa phải có kích thước gần bằng nhau.
3. Đệ quy giải nửa trái, nhận cặp gần nhất có khoảng cách `d_L`.
4. Đệ quy giải nửa phải, nhận cặp gần nhất có khoảng cách `d_R`.
5. Đặt:
   \[
   \delta=\min(d_L,d_R).
   \]
6. Kiểm tra xem có **cặp chéo** (một điểm mỗi nửa) có khoảng cách nhỏ hơn δ hay không.
7. Trả cặp có khoảng cách nhỏ nhất.

Mọi cặp điểm thuộc một trong ba loại: trái–trái, phải–phải, trái–phải. Hai lời gọi đệ quy xử lý hai loại đầu, còn bước gộp xử lý trường hợp cuối.

### 4.1. Chia theo chỉ số, không phải điều kiện x<splitX

Sau sort theo X, với phân đoạn `[lo,hi)`:

```text
mid = lo + (hi-lo)/2

left  = [lo,mid)
right = [mid,hi)

splitX = byX[mid].x
```

Mỗi bên gần một nửa số điểm.

Nếu rất nhiều điểm có cùng hoành độ X, việc chia cứng bằng `x<splitX` và `x≥splitX` có thể làm một bên rỗng. Chia **theo index của mảng đã sorted X** giữ cân bằng dù mọi X đều bằng nhau.

### 4.2. Trường hợp cơ sở

Khi phân đoạn có **2 hoặc 3 điểm**:

- Dùng vét cạn các cặp bên trong.
- Sort chính phân đoạn tương ứng của mảng làm việc theo Y.
- Trả cặp tốt nhất.

Với n≥2 và việc chia đôi các phân đoạn có hơn 3 điểm, không phát sinh nhánh chỉ một điểm.

### 4.3. Bước gộp mới là phần khó

Nếu chỉ trả `min(d_L,d_R)`, có thể bỏ sót một cặp gần nhất có một điểm ở trái và một điểm ở phải.

Nếu thử mọi cặp chéo, bước gộp có thể tốn Θ(n²), làm mất lợi ích chia đôi. Cần một cách tìm cặp chéo nhanh: **strip theo X, sắp Y, kiểm tra vài láng giềng**.

---

## 5. Dải strip quanh đường chia

Giả sử khoảng cách gần nhất tìm được ở hai nửa là:

\[
\delta=\min(d_L,d_R)>0.
\]

Xét một cặp chéo p,q có khoảng cách tốt hơn:

\[
d(p,q)<\delta.
\]

Khoảng cách theo phương X thỏa:

\[
|x_p-x_q|\le d(p,q)<\delta.
\]

Vì hai điểm thuộc hai nửa theo thứ tự X, mỗi điểm phải cách đường chia x=splitX **dưới δ**. Vậy cả hai nằm trong:

\[
\boxed{|x-splitX|<\delta}.
\]

Vùng này gọi là **strip**, rộng 2δ.

### 5.1. Lọc không cần sqrt

Đặt `D=\delta^2`. Điều kiện một điểm p thuộc strip:

\[
\boxed{(x_p-splitX)^2<D.}
\]

Vì chương trình chỉ tìm **cải thiện nghiêm ngặt**, những điểm cách đường chia đúng δ theo phương X cũng không thể tham gia cặp tốt hơn.

### 5.2. Khi δ=0

Khoảng cách không âm, nên đã đạt 0 thì không cặp nào tốt hơn. Chương trình có thể bỏ qua kiểm tra strip.

Tuy nhiên, phải **giữ bất biến thứ tự Y** trước khi trả về cho nút cha. Mã Java gộp theo Y rồi mới kiểm tra `D=0` và trả sớm.

### 5.3. Không chỉ cần các điểm ở gần đường chia

Đúng là chỉ các điểm thuộc strip mới có khả năng tạo cặp chéo tốt hơn. Nhưng nếu strip chứa nhiều điểm, thử mọi cặp trong strip vẫn có thể là O(n²). Phải kết hợp thêm **thứ tự Y** và định lý hình học để đạt tuyến tính ở bước gộp.

---

## 6. Vì sao tối đa 7 điểm kế tiếp theo Y là đủ?

Đây là tính chất đặc trưng của bài **closest pair trong 2D với khoảng cách Euclid**.

Đặt δ>0 là khoảng cách nhỏ nhất trong hai nửa. Bất kỳ hai điểm thuộc **cùng một nửa** đều có khoảng cách ít nhất δ.

Xét một điểm p trong strip. Để có cặp tốt hơn, điểm q xuất hiện **sau p theo thứ tự Y** phải thỏa:

\[
0\le y_q-y_p<\delta.
\]

Do đó các điểm cần xét nằm trong một hình chữ nhật:

- Rộng tối đa 2δ quanh đường chia.
- Cao δ, bắt đầu từ tung độ của p.

### 6.1. Chia hình chữ nhật thành ô

Xét riêng phần thuộc nửa trái và phần thuộc nửa phải. Mỗi phần có chiều rộng không quá δ, chiều cao δ.

Chia mỗi phần thành **4 hình vuông nhỏ**, mỗi hình vuông có cạnh δ/2.

Đường chéo ô nhỏ:

\[
\sqrt{(\delta/2)^2+(\delta/2)^2}
=\frac{\delta}{\sqrt2}<\delta.
\]

Vì trong một nửa không tồn tại hai điểm cách nhau **nhỏ hơn δ**, không thể có hai điểm **cùng nửa trong cùng ô nhỏ**.

Mỗi nửa tối đa 4 điểm trong vùng đó, nên hai nửa cộng lại tối đa:

\[
4+4=8
\]

điểm, **tính cả p**.

Bởi vậy, sau p có tối đa **7 điểm liên tiếp theo Y** cần xét để tìm một cặp có khoảng cách <δ.

### 6.2. Vòng lặp strip

Nếu strip đã sorted theo Y:

```text
for i from 0 to stripCount-1:
    for j from i+1 to min(i+7,stripCount-1):
        if (y[j]-y[i])^2 >= bestSquared:
            break

        candidate = squaredDistance(strip[i],strip[j])

        if candidate < bestSquared:
            update best
```

Chỉ có hằng số tối đa 7 lần so sánh hình học cho mỗi điểm, nên bước quét strip là **O(n)**.

### 6.3. Vì sao có thể dừng khi dy²≥D?

Nếu:

\[
(y_q-y_p)^2\ge D,
\]

thì:

\[
d^2(p,q)=(x_q-x_p)^2+(y_q-y_p)^2
\ge D.
\]

Cặp này không cải thiện best. Vì các điểm tiếp theo sorted Y còn có chênh lệch Y lớn hơn hoặc bằng, ta có thể **break** vòng lặp trong.

### 6.4. Khi best giảm giữa lúc quét strip

Strip có thể được tạo bằng khoảng cách D ban đầu, sau đó bestSquared giảm khi tìm được cặp tốt hơn. Các điểm trong strip lúc này có thể **nhiều hơn cần thiết**, nhưng không thiếu ứng viên quan trọng.

Điều kiện dừng dy² có thể dùng giá trị bestSquared mới để bỏ qua thêm cặp không cải thiện. Cận bảy láng giềng từ lập luận hình học với D ban đầu vẫn đủ để tìm khoảng cách nhỏ nhất.

### 6.5. Giới hạn của con số 7

Con số 7 được chứng minh cho bài toán:

- Điểm trong **mặt phẳng 2D**.
- Khoảng cách **Euclid**.
- Hai nửa đã được giải chính xác.
- Tìm **một giá trị nhỏ nhất**, không phải liệt kê mọi cặp hòa.
- Strip sorted theo **Y**.
- Chỉ cần các cặp có khoảng cách **nhỏ hơn nghiêm ngặt** ứng viên.

Không được dùng 7 một cách máy móc cho 3D, khoảng cách Manhattan, Chebyshev, tìm k cặp gần nhất hoặc liệt kê tất cả cặp đồng hạng.

---

## 7. Duy trì thứ tự Y để đạt O(n log n)

Một phiên bản dễ viết có thể sort tất cả điểm theo X, đệ quy rồi **sort strip theo Y tại mỗi nút**.

Nếu ở một nút k điểm, sort strip mất O(k log k), tổng truy hồi có thể là:

\[
T(n)=2T(n/2)+O(n\log n)
=\boxed{O(n\log^2 n)}.
\]

Muốn đạt O(n log n), cần làm bước gộp trong O(k) bằng cách giữ một mảng **byY**.

### 7.1. Hai mảng có vai trò khác nhau

- `byX`: điểm đã được sort theo `(x,y,id)` **một lần**, không đổi sau đó.
- `byY`: mảng làm việc, ban đầu `byY=byX.clone()`, được sắp dần theo Y trong các lời gọi đệ quy.

**Bất biến:** khi `solveRange(lo,hi)` trả về, đoạn `byY[lo..hi)` chứa đúng các điểm của `byX[lo..hi)` và sorted theo `(y,x,id)`.

### 7.2. Tại sao không sort byY toàn cục trước rồi chia bằng mid của byX?

Nếu byY đã sort toàn cục theo Y, `byY[lo..mid)` sẽ **không nhất thiết chứa các điểm của nửa trái theo X**. Vùng chia đôi bị sai, làm lời giải không còn hợp lệ.

Trong mã mẫu, byY **khởi tạo bằng bản sao byX**, nên lúc bắt đầu mỗi lời gọi con, các phân đoạn vẫn tương ứng với hai nửa theo X. Mỗi nhánh chỉ sắp xếp **bên trong phân đoạn của mình**.

### 7.3. Merge theo Y

Sau khi đệ quy trái và phải, ta có hai đoạn:

```text
byY[lo..mid)  sorted Y
byY[mid..hi)  sorted Y
```

Giống merge sort, dùng hai con trỏ để **merge trong O(hi-lo)** vào mergeBuffer rồi sao chép về byY.

Nhờ đó, `byY[lo..hi)` sorted Y và ta lọc điểm vào stripBuffer theo thứ tự y đã có sẵn; **không cần gọi sort strip**.

### 7.4. Vì sao buffer dùng chung an toàn?

Trong đệ quy tuần tự, nút cha chỉ dùng buffer **sau khi cả hai nhánh con đã trả kết quả**. Không có hai lời gọi đang dùng buffer cùng lúc.

Hai mảng mergeBuffer và stripBuffer dài n được tái sử dụng ở mọi nút, nên tổng bộ nhớ phụ vẫn O(n), không phải O(n log n).

---

## 8. Mô phỏng cặp gần nhất đi qua đường chia

Input:

```text
id    tọa độ
0     (0,0)
1     (0,10)
2     (1,2)
3     (1,20)
```

Sau sort X và chia:

- Trái: id 0,1. Bình phương khoảng cách tốt nhất là `100`.
- Phải: id 2,3. Bình phương khoảng cách tốt nhất là `324`.

Bước gộp bắt đầu với:

\[
D=\min(100,324)=100,\quad
\delta=10.
\]

Đường chia có `splitX=1`.

Các điểm đều thỏa `(x-1)^2<100`, nên vào strip. Theo thứ tự Y:

```text
(0,0), (1,2), (0,10), (1,20)
```

Cặp đầu:

\[
d^2((0,0),(1,2))
=(0-1)^2+(0-2)^2
=1+4
=\boxed5.
\]

Đây là cặp **chéo đường chia**, tốt hơn cả hai nửa.

Khoảng cách nhỏ nhất toàn cục:

\[
d=\sqrt5\approx2.236068.
\]

Nếu chỉ trả min kết quả trái/phải, thuật toán sẽ trả sai `sqrt100=10`. Bước gộp strip là bắt buộc.

### 8.1. Ví dụ sáu điểm

```text
id  tọa độ
0   (0,0)
1   (5,4)
2   (3,1)
3   (9,8)
4   (3,2)
5   (4,3)
```

Cặp gần nhất duy nhất: **id 2 và id 4**.

\[
D=((3-3)^2+(1-2)^2)=1,
\]

nên khoảng cách bằng 1.

### 8.2. Điểm trùng tọa độ

```text
id  tọa độ
0   (7,7)
1   (1,3)
2   (7,7)
3   (9,10)
```

Id 0 và id 2 tạo cặp có D=0. Kết quả này là tối ưu và được code nhận ra dù hai điểm có cùng tọa độ.

### 8.3. Hai điểm theo tam giác 3–4–5

`(0,0)` và `(3,4)` có:

\[
D=3^2+4^2=25,\quad d=5.
\]

Đây là test cơ bản cho phép tính bình phương khoảng cách và căn bậc hai khi hiển thị.

---

## 9. Java 17+ hoàn chỉnh

Mã sau đáp ứng cận O(n log n) theo số điểm với tọa độ `long` cố định:

- Sort byX đúng một lần theo `x,y,id`.
- byY ban đầu là bản sao byX, duy trì từng phân đoạn theo Y bằng merge.
- Base case 2–3 điểm vét cạn.
- Mỗi nút chỉ lọc strip rồi xét tối đa 7 phần tử tiếp theo theo Y.
- Sử dụng `BigInteger` để so sánh bình phương khoảng cách **chính xác** ngay cả khi hiệu của hai tọa độ không vừa long.
- Giữ id để phân biệt điểm trùng tọa độ.
- Trả một cặp tối ưu, **không cam kết tie-break** nếu nhiều cặp hòa.

Tệp: **`ClosestPairDivideConquerDemo.java`**.

```java
import java.math.BigInteger;
import java.util.Arrays;
import java.util.Comparator;
import java.util.Objects;

public final class ClosestPairDivideConquerDemo {

    public record Point(long x, long y, int id) {
    }

    public record Result(
            Point first,
            Point second,
            BigInteger distanceSquared) {

        // For display only; pair selection uses exact d^2.
        public double approximateDistance() {
            return Math.sqrt(distanceSquared.doubleValue());
        }
    }

    private static final Comparator<Point> BY_X =
            Comparator.comparingLong(Point::x)
                    .thenComparingLong(Point::y)
                    .thenComparingInt(Point::id);

    private static final Comparator<Point> BY_Y =
            Comparator.comparingLong(Point::y)
                    .thenComparingLong(Point::x)
                    .thenComparingInt(Point::id);

    // Exact even for Long.MIN_VALUE and Long.MAX_VALUE.
    private static BigInteger squareDifference(
            long a, long b) {

        BigInteger delta = BigInteger.valueOf(a)
                .subtract(BigInteger.valueOf(b));

        return delta.multiply(delta);
    }

    private static BigInteger squaredDistance(
            Point a, Point b) {

        return squareDifference(a.x(), b.x())
                .add(squareDifference(a.y(), b.y()));
    }

    private static Result candidate(Point a, Point b) {
        return new Result(a, b, squaredDistance(a, b));
    }

    private static Result chooseSmaller(
            Result a, Result b) {

        return a.distanceSquared()
                .compareTo(b.distanceSquared()) <= 0
                ? a : b;
    }

    private static final class Solver {

        private final Point[] byX;
        private final Point[] byY;
        private final Point[] mergeBuffer;
        private final Point[] stripBuffer;

        private Solver(Point[] points) {
            byX = points.clone();
            Arrays.sort(byX, BY_X);

            // Initially, each interval matches byX.
            byY = byX.clone();

            mergeBuffer = new Point[points.length];
            stripBuffer = new Point[points.length];
        }

        private Result solve() {
            return solveRange(0, byX.length);
        }

        // Both halves are already Y-sorted.
        private void mergeByY(int lo, int mid, int hi) {
            int i = lo;
            int j = mid;
            int out = lo;

            while (i < mid && j < hi) {
                if (BY_Y.compare(byY[i], byY[j]) <= 0) {
                    mergeBuffer[out++] = byY[i++];
                } else {
                    mergeBuffer[out++] = byY[j++];
                }
            }

            while (i < mid) {
                mergeBuffer[out++] = byY[i++];
            }

            while (j < hi) {
                mergeBuffer[out++] = byY[j++];
            }

            System.arraycopy(
                    mergeBuffer, lo, byY, lo, hi - lo);
        }

        // On return, byY[lo..hi) is sorted by Y.
        private Result solveRange(int lo, int hi) {
            int count = hi - lo;

            if (count <= 3) {
                Result best = null;

                for (int i = lo; i < hi; i++) {
                    for (int j = i + 1; j < hi; j++) {
                        Result current =
                                candidate(byX[i], byX[j]);

                        if (best == null
                                || current.distanceSquared()
                                        .compareTo(
                                          best.distanceSquared()) < 0) {
                            best = current;
                        }
                    }
                }

                Arrays.sort(byY, lo, hi, BY_Y);
                return best;
            }

            int mid = lo + (hi - lo) / 2;
            long splitX = byX[mid].x();

            Result leftBest = solveRange(lo, mid);
            Result rightBest = solveRange(mid, hi);

            Result best = chooseSmaller(leftBest, rightBest);

            // Keep the Y-order invariant before returning.
            mergeByY(lo, mid, hi);

            // Distance 0 cannot be improved.
            if (best.distanceSquared().signum() == 0) {
                return best;
            }

            int stripCount = 0;

            for (int i = lo; i < hi; i++) {
                Point p = byY[i];

                if (squareDifference(p.x(), splitX)
                        .compareTo(best.distanceSquared()) < 0) {
                    stripBuffer[stripCount++] = p;
                }
            }

            // Strip is already sorted by Y.
            for (int i = 0; i < stripCount; i++) {
                for (int j = i + 1;
                        j < stripCount && j <= i + 7;
                        j++) {

                    BigInteger dySquared = squareDifference(
                            stripBuffer[j].y(),
                            stripBuffer[i].y());

                    if (dySquared.compareTo(
                            best.distanceSquared()) >= 0) {
                        break;
                    }

                    Result current = candidate(
                            stripBuffer[i], stripBuffer[j]);

                    if (current.distanceSquared()
                            .compareTo(
                              best.distanceSquared()) < 0) {
                        best = current;
                    }
                }
            }

            return best;
        }
    }

    public static Result closestPair(long[][] coordinates) {
        Objects.requireNonNull(
                coordinates, "coordinates");

        if (coordinates.length < 2) {
            throw new IllegalArgumentException(
                    "At least two points are required");
        }

        Point[] points = new Point[coordinates.length];

        for (int i = 0; i < coordinates.length; i++) {
            if (coordinates[i] == null
                    || coordinates[i].length != 2) {
                throw new IllegalArgumentException(
                        "Each point must have exactly x and y");
            }

            points[i] = new Point(
                    coordinates[i][0],
                    coordinates[i][1],
                    i);
        }

        return new Solver(points).solve();
    }

    private static String pairIds(Result result) {
        return result.first().id()
                + ", " + result.second().id();
    }

    public static void main(String[] args) {
        Result basic = closestPair(new long[][] {
                {0, 0},
                {5, 4},
                {3, 1},
                {9, 8},
                {3, 2},
                {4, 3}
        });

        System.out.println(
                "Basic ids: " + pairIds(basic));
        System.out.println(
                "Basic squared: "
                        + basic.distanceSquared());
        System.out.println(
                "Basic distance: "
                        + basic.approximateDistance());

        Result cross = closestPair(new long[][] {
                {0, 0},
                {0, 10},
                {1, 2},
                {1, 20}
        });

        System.out.println(
                "Cross ids: " + pairIds(cross));
        System.out.println(
                "Cross squared: "
                        + cross.distanceSquared());

        Result duplicates = closestPair(new long[][] {
                {7, 7},
                {1, 3},
                {7, 7},
                {9, 10}
        });

        System.out.println(
                "Duplicate ids: " + pairIds(duplicates));
        System.out.println(
                "Duplicate squared: "
                        + duplicates.distanceSquared());

        Result two = closestPair(new long[][] {
                {0, 0},
                {3, 4}
        });

        System.out.println(
                "Two-point squared: "
                        + two.distanceSquared());
        System.out.println(
                "Two-point distance: "
                        + two.approximateDistance());

        Result sameX = closestPair(new long[][] {
                {2, 4},
                {2, 3},
                {2, 0},
                {2, 10},
                {2, 8}
        });

        System.out.println(
                "Same-X squared: "
                        + sameX.distanceSquared());

        Result extreme = closestPair(new long[][] {
                {Long.MIN_VALUE, 0},
                {Long.MAX_VALUE, 0}
        });

        System.out.println(
                "Extreme squared: "
                        + extreme.distanceSquared());

        boolean tooFewRejected = false;

        try {
            closestPair(new long[][] { {1, 2} });
        } catch (IllegalArgumentException ex) {
            tooFewRejected = true;
        }

        System.out.println(
                "Too few rejected: "
                        + tooFewRejected);

        boolean invalidShapeRejected = false;

        try {
            closestPair(new long[][] {
                    {1, 2},
                    {3}
            });
        } catch (IllegalArgumentException ex) {
            invalidShapeRejected = true;
        }

        System.out.println(
                "Invalid shape rejected: "
                        + invalidShapeRejected);

        boolean nullRejected = false;

        try {
            closestPair(null);
        } catch (NullPointerException ex) {
            nullRejected = true;
        }

        System.out.println(
                "Null rejected: " + nullRejected);
    }
}
```

### 9.1. Lệnh chạy

Dùng JDK 17 hoặc mới hơn:

```bash
javac ClosestPairDivideConquerDemo.java
java ClosestPairDivideConquerDemo
```

**Stdout kỳ vọng:**

```text
Basic ids: 2, 4
Basic squared: 1
Basic distance: 1.0
Cross ids: 0, 2
Cross squared: 5
Duplicate ids: 0, 2
Duplicate squared: 0
Two-point squared: 25
Two-point distance: 5.0
Same-X squared: 1
Extreme squared: 340282366920938463426481119284349108225
Too few rejected: true
Invalid shape rejected: true
Null rejected: true
```

### 9.2. Giải thích các thành phần

**Point:** record giữ x,y và id đầu vào. Id giúp phân biệt hai phần tử có cùng tọa độ.

**Result:** trả cặp và bình phương khoảng cách dưới dạng BigInteger. `approximateDistance()` dùng `Math.sqrt` để hiển thị số thực gần đúng; quyết định cặp min **không dựa vào số thực**.

**BY_X / BY_Y:** hai comparator sử dụng `Comparator.comparingLong` và id làm khóa cuối. Không có phép trừ hai long trong comparator.

**squareDifference:** chuyển từng tọa độ sang BigInteger trước phép trừ, rồi nhân kết quả với chính nó. Nhờ vậy không tràn dù hai tọa độ ở hai cực trị.

**Solver:** các mảng byX,byY,mergeBuffer,stripBuffer có kích thước n. byX sắp X một lần; byY ban đầu copy theo cùng index rồi được merge Y khi đi lên cây đệ quy.

**Base case:** vét cạn 2 hoặc 3 điểm, sorted byY đoạn tương ứng, trả cặp tối ưu.

**Recursive case:** chia theo mid, chọn min từ hai nửa, merge Y, bỏ qua strip nếu D=0, còn lại lọc điểm gần splitX và xét tối đa 7 phần tử kế tiếp.

### 9.3. Kết quả chính xác ở cực trị long

Với:

```text
(Long.MIN_VALUE, 0)
(Long.MAX_VALUE, 0)
```

hiệu hoành độ theo toán học:

\[
2^{64}-1
=18\,446\,744\,073\,709\,551\,615.
\]

Bình phương khoảng cách:

\[
(2^{64}-1)^2
=\boxed{340282366920938463426481119284349108225}.
\]

Không thể dùng `long` để biểu diễn hiệu hay bình phương ấy. `BigInteger` trả chính xác.

### 9.4. BigInteger và độ phức tạp theo n

Các tọa độ trong code là **long 64-bit cố định**. Hiệu của hai tọa độ cần tối đa khoảng 65 bit dấu, tổng bình phương có dưới 130 bit.

Số bit của các đối tượng BigInteger trung gian vì thế **bị chặn bởi hằng số độc lập với n**. Theo mô hình RAM với đầu vào tọa độ cố định độ rộng, mỗi phép khoảng cách có chi phí bị chặn, và toàn bộ thuật toán vẫn là O(n log n) theo n. Trong thực tế BigInteger có overhead lớn hơn long.

Nếu tọa độ là BigInteger **không giới hạn bit**, cần thêm phân tích chi phí số học nhiều bit; O(n log n) khi ấy chỉ là số bước hình học trừu tượng.

### 9.5. Vì sao không cần sort strip?

Sau lời gọi trái/phải, `mergeByY` tạo byY sorted Y cho cả đoạn. Lọc điểm vào stripBuffer theo thứ tự ấy tự động giữ Y tăng dần.

Điều này quan trọng cả cho **tính đúng** của giới hạn 7 láng giềng lẫn **O(n log n)**. Nếu lọc từ byX thì strip có thứ tự X và giới hạn 7 theo thứ tự mảng sẽ không còn được chứng minh.

---

## 10. Chứng minh tính đúng bằng quy nạp

Ta chứng minh cùng lúc hai bất biến của lời gọi `solveRange(lo,hi)`:

1. Kết quả là cặp điểm có **bình phương khoảng cách nhỏ nhất** trong vùng `byX[lo..hi)`.
2. Đoạn `byY[lo..hi)` khi trả về chứa đúng điểm của vùng đó và được **sorted theo Y**.

### 10.1. Cơ sở: hai hoặc ba điểm

Hàm kiểm tra mọi cặp; do đó tìm được min. Nó sort chính đoạn byY tương ứng theo Y trước khi trả. Hai bất biến đúng.

### 10.2. Giả thiết quy nạp

Với k>3 điểm, chia thành hai nửa. Giả sử các lời gọi con trả cặp tối ưu nội bộ và hai đoạn byY của chúng đều sorted Y, chứa đúng tập điểm của các nửa.

### 10.3. Merge bảo toàn bất biến thứ hai

Hai đoạn sorted Y được merge tuyến tính thành đoạn lớn sorted Y, không trộn điểm ngoài vùng, không làm mất hay nhân bản điểm. Bất biến byY vẫn đúng.

### 10.4. Cặp nội bộ đã được xét

Mọi cặp trái–trái được giải ở nhánh trái, mọi cặp phải–phải ở nhánh phải. Lấy best nội bộ là min của hai kết quả.

### 10.5. Cặp chéo tốt hơn không bị loại

Giả sử tồn tại cặp chéo (p,q) có khoảng cách nhỏ hơn δ nội bộ. Theo bất đẳng thức khoảng cách Euclid, mỗi điểm cách splitX dưới δ nên cả p,q nằm trong strip.

Giả sử p đứng trước q theo Y. Ta có `0≤y_q-y_p<δ`. Lập luận chia ô trong hình chữ nhật 2δ×δ chứng minh q nằm trong tối đa bảy vị trí tiếp theo theo thứ tự Y (hoặc thuật toán đã tìm được một cải thiện đủ tốt trước đó). Do đó vòng lặp strip kiểm tra các ứng viên cần thiết và không bỏ cặp tốt hơn.

### 10.6. Cặp hòa không ảnh hưởng min

Nếu một cặp chéo có khoảng cách **bằng** δ, không cần cập nhật vì giá trị min đã đúng. Chương trình chỉ phải phát hiện các cặp có khoảng cách **nhỏ hơn** best hiện tại.

### 10.7. Kết luận

Thuật toán trả min trong ba loại cặp và giữ thứ tự Y đúng. Bằng quy nạp, lời gọi đầu tiên trên toàn bộ n điểm trả một cặp gần nhất chính xác.

---

## 11. Phân tích thời gian và bộ nhớ

### 11.1. Tiền xử lý

Sắp n điểm theo X:

\[
O(n\log n).
\]

Sao chép byY và cấp phát các buffer:

\[
O(n).
\]

### 11.2. Bước gộp một nút k điểm

- Merge hai đoạn sorted Y: **O(k)**.
- Duyệt byY và lọc strip: **O(k)**.
- Với mỗi điểm strip, kiểm tra tối đa 7 cặp: **O(k)**.

Vì vậy:

\[
Merge(k)=O(k).
\]

### 11.3. Truy hồi

\[
T(n)=2T(n/2)+O(n).
\]

Có O(log n) tầng và tổng số phần tử xử lý trên mỗi tầng là O(n), nên:

\[
\boxed{T(n)=O(n\log n)}.
\]

Cộng tiền xử lý cũng là O(n log n).

### 11.4. Vì sao sort lại tại mỗi tầng có thể chậm hơn?

Nếu sort strip ở nút k bằng O(k log k), truy hồi:

\[
T(n)=2T(n/2)+O(n\log n)
=\boxed{O(n\log^2 n)}.
\]

Do đó việc nói “cứ chia đôi là O(n log n)” là sai. Cần nhìn **chi phí bước gộp**.

### 11.5. Bộ nhớ

`byX`, `byY`, `mergeBuffer`, `stripBuffer` đều là các mảng O(n). Đệ quy sâu O(log n).

Tổng bộ nhớ phụ:

\[
\boxed{S(n)=O(n)}.
\]

Không phải O(1) và cũng không tự thành O(n log n), vì mảng buffer được tái sử dụng, không cấp phát theo từng tầng.

---

## 12. Trường hợp biên phải làm đúng

### 12.1. Một hoặc không có điểm

Không có cặp hợp lệ. Java ném `IllegalArgumentException`.

### 12.2. Hai hoặc ba điểm

Vét cạn là đủ; cần sort byY trước khi trở về để không phá bất biến đệ quy.

### 12.3. Điểm trùng

Hai id khác nhau có tọa độ bằng nhau tạo D=0. Code không loại bỏ chúng. Nếu một nửa đã có D=0, có thể bỏ strip **sau merge Y**.

### 12.4. Mọi X giống nhau

Ví dụ:

```text
(2,4),(2,3),(2,0),(2,10),(2,8)
```

Cặp gần nhất: `(2,3),(2,4)` với D=1. Vẫn chia được theo chỉ số, không cần X phân biệt.

### 12.5. Mọi Y giống nhau

Khi Y trùng, các điểm strip có chênh lệch Y=0, rất đáng xét. Không được bỏ các điểm ấy. Nếu toàn bộ điểm trên một đường ngang, cặp gần nhất là hai hoành độ kề nhau gần nhất sau sort X.

### 12.6. Tọa độ âm

Không ảnh hưởng tính đúng vì hiệu tọa độ được bình phương chính xác. Không cần lấy giá trị tuyệt đối trước khi trừ nếu dùng BigInteger.

### 12.7. Tọa độ rất lớn

Trừ hai long có thể tràn. Dùng BigInteger trước phép trừ, không dùng `Math.abs` trên một hiệu long đã tràn.

### 12.8. Nhiều cặp tối ưu

Mã trả một cặp tối ưu bất kỳ. Khi kiểm thử đối chiếu vét cạn, nên so **giá trị D** chứ không nhất thiết so thứ tự hai id nếu có hòa.

### 12.9. Hình dạng đầu vào

Hàm `closestPair` nhận `long[][]`; mỗi hàng phải là đúng `[x,y]`. Nếu một hàng null hoặc dài khác 2, chương trình chủ động báo `IllegalArgumentException` thay vì bỏ qua hoặc tính thiếu tọa độ.

---

## 13. Những lỗi thường gặp

1. **Quên xét cặp đi qua hai nửa**, chỉ trả min(dL,dR).
2. **Thử mọi cặp chéo**, khiến bước gộp trở lại O(n²).
3. **Sắp xếp strip theo Y tại mỗi nút** nhưng báo O(n log n), trong khi có thể O(n log² n).
4. **Không giữ bất biến byY sorted theo Y khi trả về**, làm bước gộp của cha sai.
5. **Trả sớm khi D=0 trước khi merge Y**, phá bất biến cha.
6. **Sort toàn bộ byY ngay từ đầu rồi chia theo index X**, chia sai tập điểm.
7. **Dùng x<splitX để chia số điểm**, mất cân bằng khi nhiều X bằng nhau.
8. **Dùng comparator `(int)(a.x-b.x)`**, tràn long và có thể đảo thứ tự.
9. **Trừ long rồi mới đổi sang BigInteger**, giá trị đã tràn.
10. **Bình phương long rồi mới ép BigInteger**, không sửa được kết quả đã tràn.
11. **Dùng sqrt cho từng cặp**, tăng chi phí và có thể giảm độ chính xác.
12. **Quên strip cần sorted theo Y**, dùng 7 phần tử tiếp theo theo X.
13. **Bỏ cặp có cùng Y** dù dy=0, có thể là cặp tối ưu.
14. **Không xử lý điểm trùng**, bỏ khoảng cách 0.
15. **Xóa bản sao điểm cùng tọa độ**, làm thay đổi bài toán khi id khác nhau.
16. **Lẫn khoảng cách D với căn δ**, viết `dx²<δ` thay vì `dx²<D`.
17. **Dùng “7” cho 3D hoặc metric khác** mà không chứng minh lại.
18. **Đổi dấu < thành <= một cách không nhất quán** khi muốn tie-break, sai hợp đồng.
19. **Báo O(log n) bộ nhớ** chỉ vì stack O(log n), quên buffer O(n).
20. **Tưởng BigInteger có chi phí O(1) với tọa độ số bit tùy ý**, không đúng trong mô hình bit.
21. **Không test cặp chéo có khoảng cách nhỏ hơn hai nửa**, một lỗi logic phổ biến.
22. **Không test tất cả X giống nhau hoặc Y giống nhau**, bỏ lỗi chia/sort.
23. **Không test tọa độ âm và hai cực trị long**, bỏ overflow.
24. **Không test n=2,n=3**, bỏ lỗi base và sort đoạn nhỏ.
25. **So id cặp với oracle khi có tie**, gây báo lỗi giả dù khoảng cách đúng.
26. **Không kiểm tra cặp trả thực sự có D bằng best đã báo**, bỏ lỗi dựng Result.
27. **Nhầm khoảng cách Euclid với Manhattan**, sai cả thuật toán và đáp án.
28. **Cho rằng chia để trị tự động O(n log n)** mà không phân tích chi phí mỗi tầng.

---

## 14. Kiểm thử bằng oracle độc lập

### 14.1. Oracle vét cạn

Với input nhỏ, duyệt tất cả `i<j` và tìm D nhỏ nhất:

```text
BRUTE_FORCE_SQUARED(points):
    best = +infinity

    for i=0..n-1:
        for j=i+1..n-1:
            best = min(
                best,
                exactSquaredDistance(points[i],points[j]))

    return best
```

Bắt buộc:

```text
fast.distanceSquared == brute.distanceSquared
```

Không bắt buộc hai cách trả **cùng id** khi có cặp hòa.

### 14.2. Bộ test định hướng

| Input | Kết quả |
| --- | --- |
| `(0,0),(3,4)` | D=25 |
| `(0,0),(5,4),(3,1),(9,8),(3,2),(4,3)` | D=1, id 2 và 4 |
| `(0,0),(0,10),(1,2),(1,20)` | D=5, id 0 và 2 |
| `(7,7),(1,3),(7,7),(9,10)` | D=0, id 0 và 2 |
| `(2,4),(2,3),(2,0),(2,10),(2,8)` | D=1 |
| `(0,5),(6,5)` | D=36 |
| X lần lượt `Long.MIN_VALUE`, `Long.MAX_VALUE`; Y=0 | D=`(2^64-1)^2` |
| Chỉ một điểm | Ném `IllegalArgumentException` |
| Một hàng input chỉ có x | Ném `IllegalArgumentException` |
| Input null | Ném `NullPointerException` |

### 14.3. Kiểm tra ngẫu nhiên

Dùng n từ 2 tới khoảng 25 để vẫn có thể vét cạn:

1. Sinh tọa độ nguyên ngẫu nhiên trong −20..20.
2. Cho phép sinh điểm trùng để kiểm tra khoảng cách 0.
3. Chạy thuật toán chia để trị.
4. Chạy oracle vét cạn.
5. So D của hai thuật toán chính xác.
6. Xác minh hai id trong Result khác nhau, thuộc input và cặp thật có D như đã trả.
7. Lặp hàng nghìn lần với seed cố định để tái hiện lỗi.
8. Thử thêm dữ liệu đã sorted theo X, sorted ngược, toàn X bằng nhau hoặc toàn Y bằng nhau.

Mô hình thuật toán Java đã được đối chiếu độc lập với vét cạn trên nhiều chuỗi dữ liệu điểm ngắn, bao gồm các cặp chéo tối ưu và điểm trùng; **chứng minh vẫn là cơ sở của tính đúng**, còn random test kiểm tra lỗi cài đặt.

### 14.4. Test bất biến merge

Trong bản debug có thể assert ở đầu và cuối mỗi đệ quy:

- Phân đoạn byY chứa **đúng các id** của phân đoạn byX tương ứng.
- Khi trả về, byY tăng dần theo `(y,x,id)`.
- Result chứa hai id trong phân đoạn và có D đúng.
- Nếu best nội bộ bằng 0, return chỉ xảy ra **sau khi merge**.
- Strip được lọc theo Y nên vẫn tăng dần theo Y.

Sai bất biến byY có thể làm phép quét 7 láng giềng bỏ sót cặp tốt hơn dù mọi công thức khoảng cách đều đúng.

---

## 15. So sánh với các cách tiếp cận khác

| Thuật toán | Thời gian | Bộ nhớ phụ | Đặc điểm |
| --- | --- | --- | --- |
| Vét cạn | O(n²) | O(1) | Dễ cài, exact, oracle tốt |
| Chia để trị + sort strip mỗi nút | Có thể O(n log² n) | Tùy cách cài | Dễ viết nhưng mất cận tối ưu |
| **Chia để trị + merge Y** | **O(n log n)** | **O(n)** | Exact và có cận xấu nhất tốt trong 2D |
| Sweep line + tập cân bằng | O(n log n) nếu cài đúng | O(n) | Duyệt theo X, giữ tập hoạt động theo Y |
| KD-tree và nearest neighbor | Phụ thuộc cấu trúc/dữ liệu | Tùy | Phù hợp các truy vấn lân cận, không đồng nhất bài closest pair toàn cục |
| Kỹ thuật ngẫu nhiên/lưới | Tùy giả thiết | Tùy | Có thể tốt kỳ vọng nhưng cần nêu mô hình xác suất |

### 15.1. Sweep line

Một lời giải exact khác là sắp theo X rồi duy trì tập các điểm gần biên đang quét. Khi có khoảng cách ứng viên δ, loại các điểm cách xa theo X và chỉ truy vấn những điểm có Y trong một khoảng liên quan.

Trong Java, khi dùng `TreeSet`, comparator phải phân biệt id ngay cả khi hai điểm có cùng tọa độ, nếu không TreeSet có thể coi chúng là cùng khóa và loại mất điểm.

### 15.2. Truy vấn nearest-neighbor khác closest pair toàn cục

Nếu bài hỏi “với mỗi điểm truy vấn q, tìm điểm gần q nhất”, đó là mô hình **nearest neighbor search**. Kd-tree hữu ích ở một số trường hợp nhưng có cận phụ thuộc kích thước và dữ liệu.

Bài này chỉ cần **một cặp gần nhất trong toàn tập**, không phải cấu trúc trả nhiều truy vấn online.

### 15.3. Mở rộng sang nhiều chiều

Trong không gian d chiều cố định có các thuật toán chia để trị và cấu trúc hình học tổng quát, nhưng số điểm cần so trong vùng gộp phụ thuộc d. Con số 7 là tính chất của hình học 2D Euclid ở trên, không được giữ nguyên khi đổi chiều.

---

## 16. Câu hỏi thường nhầm

### “Tại sao không thể chỉ lấy min của hai nửa?”

Vì cặp tốt nhất toàn cục có thể gồm **một điểm ở mỗi nửa**, ví dụ bốn điểm `(0,0),(0,10),(1,2),(1,20)` cho cặp chéo D=5, trong khi D tốt nhất nội bộ là 100.

### “Strip cần những điểm nào?”

Chỉ những điểm thỏa `(x-splitX)^2<D`, với D là bình phương khoảng cách tốt nhất từ hai nửa. Nếu D=0, không cần tìm cải thiện.

### “Strip có cần sorted Y?”

**Có.** Giới hạn 7 nói về những điểm **tiếp theo theo tung độ**, không phải tiếp theo theo mảng ngẫu nhiên hoặc theo X.

### “Có cần gọi sqrt trong thuật toán?”

**Không.** So bình phương khoảng cách và chênh lệch X/Y bình phương là đủ. sqrt chỉ dùng để hiển thị khoảng cách thực gần đúng.

### “Nhiều điểm cùng X có gây đệ quy vô hạn?”

Không nếu chia **theo index**. Mỗi nửa có số phần tử giảm tới 2 hoặc 3, bất kể tọa độ.

### “Tại sao phải giữ byY sorted khi best=0?”

Vì nút cha còn cần merge hai phân đoạn sorted Y. Return trước merge có thể phá bất biến, khiến bước strip của cha sai.

### “Double có tiện hơn BigInteger không?”

Nếu đề dùng tọa độ thực, double có thể phù hợp. Nhưng với tọa độ nguyên long lớn và yêu cầu **exact**, double có sai số biểu diễn, còn phép trừ/bình phương long có thể tràn. BigInteger giữ D chính xác.

### “Có cần chọn cặp id nhỏ nhất khi hòa?”

Chỉ nếu đề quy định. Bài này trả một cặp tối ưu bất kỳ; việc duy trì tie-break canonical đòi đặc tả và xử lý kỹ các cặp bằng nhau.

---

## 17. Bài tập tự kiểm tra

### Bài 1
Phát biểu bài toán closest pair và điều kiện đầu vào tối thiểu.

### Bài 2
Vì sao có thể so d² mà không cần tính sqrt?

### Bài 3
Với n điểm có bao nhiêu cặp chỉ số i<j?

### Bài 4
Tính D và d của `(0,0)`, `(3,4)`.

### Bài 5
Cho nửa trái `(0,0),(0,10)`, phải `(1,2),(1,20)`. Tính D nội bộ và D toàn cục.

### Bài 6
Chứng minh cặp chéo cải thiện phải có mỗi điểm cách splitX dưới δ.

### Bài 7
Viết điều kiện lọc strip bằng bình phương mà không dùng sqrt.

### Bài 8
Vì sao chỉ xét 7 điểm kế tiếp trong strip theo Y?

### Bài 9
Tại sao không áp số 7 cho 3D?

### Bài 10
Nếu đã có D=0, có cần kiểm tra thêm cặp chéo không?

### Bài 11
Khi D=0, tại sao vẫn phải merge Y trước khi return?

### Bài 12
Vì sao chia theo index mid tốt hơn chia bằng `x<splitX` khi X trùng?

### Bài 13
Phân biệt `byX` và `byY` trong cài đặt.

### Bài 14
Nếu sort strip theo Y tại mỗi nút O(k log k), truy hồi là gì?

### Bài 15
Nếu merge theo Y tuyến tính, truy hồi và kết quả là gì?

### Bài 16
Bộ nhớ phụ O(n) đến từ những cấu trúc nào?

### Bài 17
Hai điểm khác id có cùng tọa độ tạo khoảng cách bao nhiêu?

### Bài 18
Với `(2,4),(2,3),(2,0),(2,10),(2,8)`, tìm D min.

### Bài 19
Giải thích vì sao comparator kiểu `a.x-b.x` nguy hiểm với long.

### Bài 20
Hiệu chính xác giữa Long.MAX_VALUE và Long.MIN_VALUE bằng bao nhiêu?

### Bài 21
Vì sao phải chuyển từng tọa độ sang BigInteger trước phép trừ?

### Bài 22
Vì sao khi có nhiều cặp hòa, kiểm thử nên so D thay vì so cặp id?

### Bài 23
Nêu cách xây oracle vét cạn cho các test n≤25.

### Bài 24
Liệt kê các bộ test biên cần có.

### Bài 25
Khi đổi khoảng cách Euclid sang Manhattan, điều gì cần chứng minh lại?

### Bài 26
Vì sao O(n log n) là bậc số thao tác hình học nếu tọa độ dùng BigInteger không giới hạn số bit?

### Bài 27
Đối chiếu chi phí của vét cạn và chia để trị ở n lớn.

### Bài 28
Nêu hai bất biến cần giữ khi `solveRange(lo,hi)` trả về.

### Bài 29
Giải thích tại sao `dy²≥D` cho phép break vòng lặp trên strip sorted Y.

### Bài 30
Tính D giữa hai điểm `(Long.MIN_VALUE,0)` và `(Long.MAX_VALUE,0)`.

### Đáp án gợi ý

1. Chọn hai điểm **khác chỉ số** có khoảng cách Euclid nhỏ nhất; cần n≥2.
2. Vì sqrt tăng trên số không âm, d² và d cho cùng thứ tự.
3. `n(n-1)/2` cặp.
4. `D=9+16=25`; d=5.
5. Trái D=100, phải D=324; cặp chéo `(0,0),(1,2)` cho D=5 tối ưu.
6. Khoảng cách ngang của cặp nhỏ hơn δ, mà hai điểm nằm hai phía đường chia nên mỗi điểm cách đường chia dưới δ.
7. `(x-splitX)^2<bestSquared`.
8. Hình chữ nhật 2δ×δ chia thành hai nửa, mỗi nửa 4 ô δ/2×δ/2; không có hai điểm cùng nửa trong một ô, nên nhiều nhất 8 điểm kể cả điểm đang xét ⇒ 7 điểm tiếp theo.
9. Số ô và cận hình học phụ thuộc chiều d và metric.
10. Không, khoảng cách không âm nên 0 đã tối ưu.
11. Để bảo toàn byY sorted cho cha merge.
12. Chia index bảo đảm gần cân bằng dù tất cả X bằng nhau.
13. byX sorted X một lần; byY ban đầu copy byX, cuối mỗi lời gọi phân đoạn tương ứng sorted Y.
14. `T(n)=2T(n/2)+O(n log n)=O(n log² n)`.
15. `T(n)=2T(n/2)+O(n)=O(n log n)`.
16. Mảng byX,byY,mergeBuffer,stripBuffer đều O(n), cộng stack O(log n).
17. D=0.
18. D=1 giữa `(2,3)` và `(2,4)`.
19. Phép trừ long có thể overflow và đảo thứ tự comparator; nên dùng `Long.compare`.
20. `2^64-1=18446744073709551615`, vượt long có dấu.
21. Nếu trừ long trước, kết quả đã tràn; BigInteger ép sau không phục hồi giá trị.
22. Có thể tồn tại nhiều cặp tối ưu; hợp đồng chỉ đòi một cặp nên cần so D exact.
23. Duyệt tất cả i<j, tính D exact bằng BigInteger và lấy min.
24. n=2,3; điểm trùng; cùng X/Y; tọa độ âm; extreme long; cặp chéo tối ưu; input sai hình dạng/null.
25. Cận strip và số láng giềng phải rút từ metric mới, không áp nguyên cận 7 Euclid.
26. Khi tọa độ có số bit không giới hạn, mỗi phép nhân/trừ BigInteger không O(1), nên phải cộng chi phí bit.
27. Vét cạn O(n²), chia để trị có merge Y O(n log n), phù hợp n lớn.
28. Result tối ưu trong vùng và byY cùng tập điểm vùng, sorted theo Y.
29. Khoảng cách bình phương luôn ≥ dy²; các điểm sau Y tăng nên không thể cải thiện.
30. `(2^64-1)^2=340282366920938463426481119284349108225`.

---

## Ghi nhớ

**Cặp điểm gần nhất bằng chia để trị** trong mặt phẳng 2D Euclid đạt:

\[
\boxed{O(n\log n)\text{ thời gian, }O(n)\text{ bộ nhớ phụ}.}
\]

Các bước cốt lõi:

1. Sort X một lần, chia theo index mid.
2. Đệ quy tìm best của từng nửa.
3. Merge các phân đoạn byY đã sorted trong O(n).
4. Với bestSquared=D>0, tạo strip từ những điểm có `(x-splitX)^2<D`.
5. Strip đã sorted Y; với mỗi điểm, xét tối đa **7 điểm tiếp theo** theo Y, dừng nếu `dy²≥D`.
6. Cập nhật chỉ khi D mới nhỏ hơn, rồi trả một cặp tối ưu.

**Không** sort strip lại ở mọi nút nếu muốn giữ O(n log n). **Không** dùng trừ/bình phương long trực tiếp khi tọa độ có thể cực lớn; `BigInteger` bảo đảm so sánh D chính xác. Luôn kiểm tra bằng oracle vét cạn, nhất là điểm trùng, X/Y trùng nhau và cặp tối ưu **đi qua đường chia**.
