# Bao lồi bằng chuỗi đơn điệu (Andrew’s monotone chain)

## 1. Bao lồi là gì?

Với một tập điểm trong mặt phẳng, **bao lồi** (*convex hull*) là tập lồi nhỏ nhất chứa tất cả các điểm. Khi có ít nhất ba điểm không thẳng hàng, biên của bao lồi là một đa giác lồi. Chúng ta cần trả về các **đỉnh cực trị**, không giữ những điểm nằm ở giữa một cạnh.

Ví dụ: trong tập {(0,0),(2,0),(2,2),(0,2),(1,1),(1,0)}, điểm (1,1) nằm trong hình và (1,0) nằm giữa cạnh đáy. Bao lồi là bốn góc:

```text
[(0,0), (2,0), (2,2), (0,2)]
```

**Hợp đồng của bài:** loại tọa độ trùng; với đa giác không suy biến, các đỉnh đi **ngược chiều kim đồng hồ (CCW)**, bắt đầu tại điểm nhỏ nhất theo thứ tự từ điển (x tăng, rồi y tăng), **không lặp điểm đầu ở cuối**. Nếu mọi điểm thẳng hàng, trả hai đầu mút; nếu có một tọa độ phân biệt, trả một điểm; tập rỗng trả rỗng.

Bao lồi khác với tìm đường biên lõm của đám điểm: hình bao lồi có thể phủ nhiều khoảng trống và không mô tả các lõm giữa các cụm điểm.

## 2. Hướng quay của ba điểm: tích có hướng

Cho A=(ax,ay), B=(bx,by), C=(cx,cy), xét:

**cross(A,B,C)=(bx-ax)*(cy-ay)-(by-ay)*(cx-ax).**

| Dấu cross | Diễn giải |
|---|---|
| `>0` | A -> B -> C quay trái (CCW) |
| `<0` | quay phải (CW) |
| `=0` | ba điểm thẳng hàng |

```text
A=(0,0), B=(2,0), C=(2,2)  -> cross=4
A=(0,0), B=(2,0), C=(2,-2) -> cross=-4
A=(0,0), B=(1,1), C=(3,3)  -> cross=0
```

Đây là **predicate** trung tâm: chuỗi các đỉnh hull phải luôn giữ góc quay trái nghiêm ngặt. Dấu phải được tính đúng; một dấu cross bị tràn có thể loại nhầm một đỉnh cực trị.

### 2.1. Tại sao dùng BigInteger cho tọa độ long?

Đầu vào long có thể là Long.MIN_VALUE hoặc Long.MAX_VALUE. Khi đó hiệu bx-ax có thể gần 2^64, không chứa trong signed long; phép nhân hai hiệu có thể gần 2^128. Nếu trừ trên long rồi mới chuyển sang BigInteger thì **đã tràn trước khi chuyển**.

Phương pháp an toàn là chuyển từng tọa độ sang BigInteger, sau đó mới trừ và nhân:

```java
BigInteger dx1 = BigInteger.valueOf(b.x())
    .subtract(BigInteger.valueOf(a.x()));
BigInteger dy1 = BigInteger.valueOf(b.y())
    .subtract(BigInteger.valueOf(a.y()));
BigInteger dx2 = BigInteger.valueOf(c.x())
    .subtract(BigInteger.valueOf(a.x()));
BigInteger dy2 = BigInteger.valueOf(c.y())
    .subtract(BigInteger.valueOf(a.y()));
BigInteger cross = dx1.multiply(dy2)
    .subtract(dy1.multiply(dx2));
```

Không lấy trị tuyệt đối của cross trước khi xét dấu. Với tọa độ nguyên nhỏ và đã có cận toán học bảo đảm không tràn, long có thể nhanh hơn; còn bản Java 17 trong bài ưu tiên **đúng tuyệt đối cho mọi long**.

Với tọa độ double, biểu thức gần 0 có thể bị sai dấu do làm tròn; cần robust orientation predicate hoặc hợp đồng epsilon được xác định rõ. Không tự dùng epsilon tùy ý cho dữ liệu nguyên chính xác.

## 3. Ý tưởng của Andrew’s monotone chain

Hình dung một sợi dây cao su được kéo căng quanh các điểm. Điểm ở bên trong không giữ dây; điểm nằm giữa cạnh cũng không cần làm đỉnh. Andrew xây hai đường từ các điểm đã sắp xếp:

1. **Lower chain:** quét các điểm từ trái sang phải, giữ phần biên dưới.
2. **Upper chain:** quét các điểm từ phải sang trái, giữ phần biên trên.
3. Ghép hai đường, loại hai đầu mút bị lặp.

Thuật toán dùng stack/list cho từng chuỗi. Khi điểm mới gây **quay phải hoặc thẳng hàng**, pop điểm cuối để phục hồi tính lồi. Cả hai chuỗi dùng cùng điều kiện orientation <= 0 vì chiều quét của upper đã được đảo.

## 4. Sort theo (x,y) và loại điểm trùng

Sắp xếp từ điển: x nhỏ trước, x bằng nhau thì y nhỏ trước. Ví dụ:

```text
Đầu vào:  (2,0), (0,2), (1,1), (0,0), (2,2), (0,0)
Sort:     (0,0), (0,0), (0,2), (1,1), (2,0), (2,2)
Unique:   (0,0),        (0,2), (1,1), (2,0), (2,2)
```

Loại trùng bằng cách so điểm hiện tại với điểm liền trước sau sort. Điểm lặp không làm thay đổi hull nhưng có thể gây các đoạn độ dài 0, nhiều điểm cùng tọa độ trong output và lỗi ở các thuật toán kiểm thử.

Trong Java dùng Comparator.comparingLong(Point::x).thenComparingLong(Point::y). **Không viết comparator bằng a.x-b.x** vì phép trừ có thể tràn và cho thứ tự sai. Sorting chiếm O(n log n), dedup O(n).

## 5. Dựng lower hull

Quét danh sách unique từ trái sang phải. Với mỗi điểm mới p, xem hai điểm cuối a,b trong lower:

```text
lower = []
for p in points tăng theo (x,y):
    while lower có >=2 điểm
          và cross(lower[-2], lower[-1], p) <= 0:
        bỏ lower[-1]
    thêm p vào lower
```

**Vì sao pop khi cross < 0?** Ba điểm tạo góc lõm/quay phải, nên b không thuộc biên dưới lồi cần giữ. **Vì sao pop cả khi cross = 0?** Phiên bản này chỉ trả các đỉnh cực trị: nếu a,b,p thẳng hàng theo thứ tự quét, b ở giữa cạnh a-p và không phải đỉnh.

Ví dụ lower xử lý (0,0),(1,0),(2,0): khi thêm (2,0), cross=0, nên bỏ (1,0). Kết quả còn hai đầu (0,0),(2,0).

**Bất biến:** sau khi thêm từng điểm, các điểm liên tiếp trên lower chỉ tạo những lần quay trái nghiêm ngặt. Những điểm bị pop là điểm nằm ở phía không phù hợp của cạnh nối mới, hoặc thẳng hàng giữa các đầu mút nên không thể là đỉnh cực trị của lower.

## 6. Dựng upper và ghép

Duyệt **ngược** danh sách unique, áp dụng cùng quy tắc pop:

```text
upper = []
for p in points giảm theo (x,y):
    while upper có >=2 điểm
          và cross(upper[-2], upper[-1], p) <= 0:
        bỏ upper[-1]
    thêm p vào upper
```

Lower đi từ điểm lex-min sang lex-max; upper đi ngược lại. Hai chuỗi cùng chứa hai đầu mút, nên trước khi ghép phải **bỏ phần tử cuối của mỗi chuỗi**:

```text
lower = [(0,0),(2,0),(2,2)]
upper = [(2,2),(0,2),(0,0)]

bỏ last(lower), last(upper)
ghép => [(0,0),(2,0),(2,2),(0,2)]
```

Đối với h >= 3, chuỗi ghép theo CCW. Không lặp đỉnh đầu ở cuối. Đừng ghép nguyên hai list vì sẽ lặp hai đầu mút.

## 7. Trường hợp suy biến

| Số tọa độ khác nhau | Kết quả |
|---|---|
| 0 | [] |
| 1 | [P] |
| 2 | [A,B] theo thứ tự từ điển |
| >=3, tất cả thẳng hàng | [đầu mút nhỏ nhất, đầu mút lớn nhất] |
| >=3, không thẳng hàng | các đỉnh cực trị CCW |

Ví dụ `(-2,-2),(0,0),(2,2),(4,4),(4,4)` cho hull `[(-2,-2),(4,4)]`. Tập thẳng đứng cùng x xử lý đúng nhờ tie-break theo y. Không nên tạo đa giác ba đỉnh cho một tập hoàn toàn thẳng hàng.

**Điểm nằm trên cạnh:** với các điểm (0,0),(1,0),(2,0) trong hình chữ nhật, (1,0) không được giữ. Nếu đề yêu cầu **mọi điểm trên biên**, đó là hợp đồng khác. Chỉ thay <=0 bằng <0 trong cả hai lần quét có thể giữ điểm lặp, sai thứ tự khi tất cả thẳng hàng; phải thiết kế riêng biến thể giữ biên.

## 8. Chứng minh tính đúng

### 8.1. Lower là chuỗi dưới lồi

Sort bảo đảm đường quét tiến theo x tăng, đồng thời xử lý thứ tự y khi x bằng nhau. Mỗi khi thêm p tạo góc quay phải hoặc thẳng hàng với hai điểm cuối, b bị loại vì không thể làm đỉnh cực trị của biên dưới của các điểm đã xét. Việc pop lặp lại đến khi góc cuối quay trái đảm bảo chuỗi giữ dạng lồi.

### 8.2. Upper đối xứng

Quét ngược tương ứng xây phần biên trên. Cùng với lower, nó bao hết các đỉnh cực trị; mỗi điểm còn lại ở bên trong hoặc trên đoạn nối giữa các đỉnh. Hai đầu mút chung được giữ đúng một lần sau ghép.

### 8.3. Kết quả là hull

Chuỗi ghép là đường bao khép kín không lõm, với phần trong ở bên trái mỗi cạnh khi đi CCW. Toàn bộ các điểm gốc nằm trong hoặc trên các nửa mặt phẳng tạo bởi cạnh; đường bao là đa giác lồi bao chứa tập, và không giữ đỉnh không cần thiết. Vì mọi đỉnh cực trị đã được lower/upper giữ lại, đây là bao lồi nhỏ nhất. Với tập thẳng hàng, bao lồi suy biến thành đoạn nối hai đầu mút.

### 8.4. Vì sao chỉ O(n) thao tác stack?

Mỗi điểm được push tối đa một lần và pop tối đa một lần **trong mỗi chuỗi**. Các vòng while lồng trong for không khiến tổng số pop thành O(n²); tổng push+pop sau sorting là O(n).

## 9. Độ phức tạp và độ chính xác

Với n điểm đầu vào: sort O(n log n), dedup O(n), hai lượt quét O(n), kết quả tổng **O(n log n) thời gian và O(n) bộ nhớ phụ**. Số phép orientation là O(n). Với tọa độ long cố định 64 bit, BigInteger trung gian có số bit bị chặn, nên tính một orientation được xem là chi phí hằng số theo n; với tọa độ BigInteger không giới hạn độ dài bit, cần cộng thêm chi phí phép toán nhiều bit.

**Độ chính xác:** cùng một thuật toán hình học nhưng phép cross tràn có thể đổi dấu, cho hull sai mà không báo lỗi. Dùng BigInteger ở phần tính dấu để an toàn. Java record Point hỗ trợ equals/hashCode theo hai tọa độ, tiện loại trùng và so kết quả.

## 10. Diện tích hull theo công thức shoelace

Với h>=3 đỉnh quanh biên, đặt:

**signedArea2 = tổng (x[i]*y[i+1] - y[i]*x[i+1])**, chỉ số i+1 được lấy modulo h.

Đa giác CCW không suy biến có signedArea2 > 0, CW có < 0. Diện tích hình học = abs(signedArea2)/2. Với 0,1,2 điểm, diện tích theo quy ước bằng 0.

Vì tọa độ nguyên nên diện tích chính xác là số nguyên hoặc số có phần thập phân `.5`. Mã mẫu tính signedArea2 bằng BigInteger, sau đó chia 2 và thêm `.5` khi số dư bằng 1, tránh sai số làm tròn.

```text
Square: [(0,0),(2,0),(2,2),(0,2)]
signedArea2 = 8; area = 4

Triangle: [(0,0),(1,0),(0,1)]
signedArea2 = 1; area = 0.5
```

**Chu vi:** với polygon không suy biến, cộng độ dài các đoạn giữa đỉnh liên tiếp và đoạn khép kín. Đây là độ dài thực nên thường tính gần đúng; với hull 1 hoặc 2 điểm phải xác định rõ quy ước 'chu vi' của hình suy biến trước khi trả kết quả.

## 11. Đối chiếu bằng thuật toán khác

**Jarvis march (gift wrapping)** bắt đầu ở điểm cực trái rồi tại mỗi bước chọn điểm kế tiếp sao cho các điểm khác nằm bên trái hoặc trên cạnh hướng hiện tại. Nếu có nhiều điểm cùng phương, chọn điểm xa nhất để chỉ giữ đầu mút. Đi quanh cho tới khi trở về điểm ban đầu.

Jarvis mất O(n*h) với h đỉnh hull, khác hoàn toàn hai lần quét stack của Andrew; phù hợp làm **oracle thuật toán khác** cho đầu vào nhỏ. Với h gần n, Jarvis có thể chậm hơn Andrew.

**Graham scan** cũng O(n log n) nhưng thường phải sort theo góc quanh pivot và xử lý tie-break cho các điểm thẳng hàng. Andrew đơn giản hơn vì chỉ cần sort tọa độ từ điển.

Kiểm tra bổ sung: với hull có ít nhất 3 đỉnh, signedArea2 phải dương, cross của mọi ba đỉnh liên tiếp phải dương, và mọi điểm gốc phải nằm trên hoặc bên trái mọi cạnh hull. Với hull là đoạn thẳng, mọi điểm gốc phải nằm trên **đoạn** nối hai đầu, không chỉ trên đường thẳng vô hạn.


## 12. Java 17+ hoàn chỉnh

Lưu dưới tên `MonotoneChainHullDemo.java`. Chương trình tự cài Andrew và Jarvis oracle, xử lý số nguyên long bằng BigInteger để cross/diện tích không tràn.

```java
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.Random;

public final class MonotoneChainHullDemo {
    private MonotoneChainHullDemo() {}

    public record Point(long x, long y) {
        @Override
        public String toString() {
            return "(" + x + "," + y + ")";
        }
    }

    private static final Comparator<Point> ORDER =
        Comparator.comparingLong(Point::x)
            .thenComparingLong(Point::y);

    private static BigInteger bi(long x) {
        return BigInteger.valueOf(x);
    }

    // No long subtraction/multiplication before BigInteger.
    public static BigInteger cross(
            Point a, Point b, Point c) {
        BigInteger dx1 = bi(b.x()).subtract(bi(a.x()));
        BigInteger dy1 = bi(b.y()).subtract(bi(a.y()));
        BigInteger dx2 = bi(c.x()).subtract(bi(a.x()));
        BigInteger dy2 = bi(c.y()).subtract(bi(a.y()));

        return dx1.multiply(dy2).subtract(dy1.multiply(dx2));
    }

    private static List<Point> sortedUnique(
            Collection<Point> input) {
        Objects.requireNonNull(input, "input");
        ArrayList<Point> sorted = new ArrayList<>(input);

        for (Point p : sorted) Objects.requireNonNull(p);
        sorted.sort(ORDER);

        ArrayList<Point> unique = new ArrayList<>();
        for (Point p : sorted) {
            if (unique.isEmpty()
                || !unique.get(unique.size() - 1).equals(p)) {
                unique.add(p);
            }
        }
        return unique;
    }

    // CCW, starting at lexicographically minimum;
    // keeps only extreme vertices, no repeated first point.
    public static List<Point> hull(Collection<Point> input) {
        List<Point> sorted = sortedUnique(input);
        int n = sorted.size();
        if (n <= 2) return List.copyOf(sorted);

        ArrayList<Point> lower = new ArrayList<>();
        for (Point p : sorted) {
            while (lower.size() >= 2 &&
                    cross(
                        lower.get(lower.size() - 2),
                        lower.get(lower.size() - 1), p
                    ).signum() <= 0) {
                lower.remove(lower.size() - 1);
            }
            lower.add(p);
        }

        ArrayList<Point> upper = new ArrayList<>();
        for (int i = n - 1; i >= 0; i--) {
            Point p = sorted.get(i);
            while (upper.size() >= 2 &&
                    cross(
                        upper.get(upper.size() - 2),
                        upper.get(upper.size() - 1), p
                    ).signum() <= 0) {
                upper.remove(upper.size() - 1);
            }
            upper.add(p);
        }

        // Each end point occurs in both chains.
        lower.remove(lower.size() - 1);
        upper.remove(upper.size() - 1);
        lower.addAll(upper);
        return List.copyOf(lower);
    }

    public static BigInteger signedTwiceArea(List<Point> h) {
        if (h.size() < 3) return BigInteger.ZERO;
        BigInteger result = BigInteger.ZERO;

        for (int i = 0; i < h.size(); i++) {
            Point a = h.get(i);
            Point b = h.get((i + 1) % h.size());
            result = result.add(
                bi(a.x()).multiply(bi(b.y()))
                    .subtract(bi(a.y()).multiply(bi(b.x())))
            );
        }
        return result;
    }

    // Exact because coordinates are integral: area is k or k.5.
    public static String exactArea(List<Point> h) {
        BigInteger a2 = signedTwiceArea(h).abs();
        BigInteger[] dr = a2.divideAndRemainder(
            BigInteger.valueOf(2)
        );
        return dr[0] + (dr[1].signum() == 0 ? "" : ".5");
    }

    private static BigInteger distSquared(Point a, Point b) {
        BigInteger dx = bi(b.x()).subtract(bi(a.x()));
        BigInteger dy = bi(b.y()).subtract(bi(a.y()));
        return dx.multiply(dx).add(dy.multiply(dy));
    }

    // Gift wrapping: independent control flow from Andrew.
    private static List<Point> jarvisOracle(
            Collection<Point> input) {
        List<Point> points = sortedUnique(input);
        if (points.size() <= 2) return List.copyOf(points);

        Point start = points.get(0);
        Point current = start;
        ArrayList<Point> answer = new ArrayList<>();

        do {
            answer.add(current);
            Point next = null;

            for (Point candidate : points) {
                if (candidate.equals(current)) continue;
                if (next == null) {
                    next = candidate;
                    continue;
                }

                int turn = cross(
                    current, next, candidate
                ).signum();

                if (turn < 0 ||
                    (turn == 0 && distSquared(
                        current, candidate
                    ).compareTo(distSquared(current, next)) > 0)) {
                    next = candidate;
                }
            }
            current = next;
            if (answer.size() > points.size()) {
                throw new AssertionError("Jarvis did not close");
            }
        } while (!current.equals(start));

        return List.copyOf(answer);
    }

    private static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    // Geometry-level invariants beyond exact oracle equality.
    private static void verify(
            List<Point> input, List<Point> h) {
        if (h.isEmpty()) {
            check(input.isEmpty(), "empty hull for nonempty data");
            return;
        }

        if (h.size() == 1) {
            for (Point p : input) {
                check(p.equals(h.get(0)), "singleton mismatch");
            }
            return;
        }

        if (h.size() == 2) {
            Point a = h.get(0), b = h.get(1);
            for (Point p : input) {
                check(cross(a, b, p).signum() == 0,
                    "point not on line");
                check(
                    Math.min(a.x(), b.x()) <= p.x()
                    && p.x() <= Math.max(a.x(), b.x())
                    && Math.min(a.y(), b.y()) <= p.y()
                    && p.y() <= Math.max(a.y(), b.y()),
                    "point not on segment"
                );
            }
            return;
        }

        check(signedTwiceArea(h).signum() > 0,
            "hull orientation is not CCW");

        for (int i = 0; i < h.size(); i++) {
            Point a = h.get(i);
            Point b = h.get((i + 1) % h.size());
            Point c = h.get((i + 2) % h.size());

            check(cross(a, b, c).signum() > 0,
                "non-strict vertex turn");

            for (Point p : input) {
                check(cross(a, b, p).signum() >= 0,
                    "input lies outside hull edge");
            }
        }
    }

    public static void main(String[] args) {
        List<Point> square = List.of(
            new Point(0, 0), new Point(2, 0),
            new Point(2, 2), new Point(0, 2),
            new Point(1, 1), new Point(1, 0),
            new Point(0, 0), new Point(2, 2)
        );
        List<Point> sq = hull(square);

        System.out.println("Square hull: " + sq);
        System.out.println(
            "Square twiceArea: " + signedTwiceArea(sq)
        );
        System.out.println("Square area: " + exactArea(sq));

        List<Point> line = List.of(
            new Point(0, 0), new Point(4, 4),
            new Point(-2, -2), new Point(2, 2),
            new Point(-2, -2)
        );
        System.out.println("Collinear: " + hull(line));
        System.out.println(
            "Singleton: " + hull(List.of(
                new Point(5, -7), new Point(5, -7)
            ))
        );
        System.out.println("Empty: " + hull(List.of()));
        System.out.println(
            "Triangle area: " + exactArea(hull(List.of(
                new Point(0, 0), new Point(1, 0),
                new Point(0, 1)
            )))
        );

        BigInteger extreme = cross(
            new Point(Long.MIN_VALUE, Long.MIN_VALUE),
            new Point(Long.MAX_VALUE, Long.MIN_VALUE),
            new Point(Long.MAX_VALUE, Long.MAX_VALUE)
        );
        System.out.println(
            "Extreme cross sign: " + extreme.signum()
        );

        check(sq.equals(jarvisOracle(square)),
            "sample oracle mismatch");
        verify(square, sq);

        Random random = new Random(425L);

        for (int t = 0; t < 2_100; t++) {
            int n = random.nextInt(17);
            ArrayList<Point> input = new ArrayList<>();

            for (int i = 0; i < n; i++) {
                input.add(new Point(
                    random.nextInt(15) - 7,
                    random.nextInt(15) - 7
                ));
            }

            List<Point> actual = hull(input);
            check(actual.equals(jarvisOracle(input)),
                "Jarvis mismatch trial=" + t);
            verify(input, actual);
        }

        for (int t = 0; t < 400; t++) {
            long x0 = random.nextInt(19) - 9;
            long y0 = random.nextInt(19) - 9;
            long dx = random.nextInt(7) - 3;
            long dy = random.nextInt(7) - 3;
            if (dx == 0 && dy == 0) dx = 1;

            ArrayList<Point> input = new ArrayList<>();
            int n = random.nextInt(15);

            for (int i = 0; i < n; i++) {
                long k = random.nextInt(19) - 9;
                input.add(new Point(
                    x0 + k * dx, y0 + k * dy
                ));
            }

            List<Point> actual = hull(input);
            check(actual.equals(jarvisOracle(input)),
                "collinear mismatch trial=" + t);
            check(actual.size() <= 2,
                "too many collinear hull vertices");
            verify(input, actual);
        }

        System.out.println("Random Jarvis: 2100 PASS");
        System.out.println("Collinear oracle: 400 PASS");
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 MonotoneChainHullDemo.java
java MonotoneChainHullDemo
```

**Đầu ra xác định:**

```text
Square hull: [(0,0), (2,0), (2,2), (0,2)]
Square twiceArea: 8
Square area: 4
Collinear: [(-2,-2), (4,4)]
Singleton: [(5,-7)]
Empty: []
Triangle area: 0.5
Extreme cross sign: 1
Random Jarvis: 2100 PASS
Collinear oracle: 400 PASS
```


## 13. Phân tích từng phần của mã

**Point/ORDER:** record lưu chính xác hai tọa độ long; comparator x rồi y dùng so sánh không tràn. Việc khử trùng dựa vào Point.equals.

**cross:** dùng BigInteger từ từng tọa độ trước khi tính hiệu, tích; chỉ xét signum để xác định quay trái, phải hoặc thẳng hàng.

**hull:** xử lý 0,1,2 điểm sau dedup; lower và upper đều pop khi cross<=0; bỏ điểm cuối của mỗi chuỗi trước khi ghép. Các đoạn thẳng all-collinear chỉ còn hai đầu mút.

**signedTwiceArea/exactArea:** công thức dây giày tính số nguyên chính xác; sau đó chia 2 và thêm .5 nếu cần. Không làm tròn double.

**jarvisOracle:** xuất phát ở điểm lex-min; mỗi bước chọn cạnh hỗ trợ tiếp theo theo một thuật toán khác và ưu tiên điểm xa nhất khi thẳng hàng. Độ phức tạp O(n*h), dùng để kiểm tra dữ liệu nhỏ chứ không thay thế thuật toán chính.

**verify:** kiểm CCW, góc quay trái nghiêm ngặt và mọi điểm đầu vào nằm bên trái hoặc trên mỗi cạnh của polygon. Với hull là đoạn, kiểm tất cả điểm nằm đúng trong đoạn (không chỉ trên đường thẳng).

**Random:** 2.100 ca tổng quát có 0..16 điểm tọa độ -7..7, và 400 ca thẳng hàng ngẫu nhiên gồm giá trị trùng/lặp. Việc kiểm thử xác suất hữu hạn không thay thế chứng minh bất biến.

## 14. Lỗi thường gặp

| Lỗi | Hệ quả | Khắc phục |
|---|---|---|
| Quên sort theo x rồi y | Dựng chuỗi sai thứ tự | Sort lex `(x,y)` |
| Comparator bằng hiệu tọa độ | Tràn và thứ tự sai | `Long.compare` hoặc comparator long chuẩn |
| Không dedup | Lặp điểm, cạnh dài 0 | Bỏ trùng sau sort |
| Cross bằng long cho tọa độ long bất kỳ | Tràn, có thể đổi dấu | BigInteger trước khi trừ và nhân |
| Chỉ pop khi cross<0 | Giữ điểm giữa cạnh | `<=0` nếu chỉ cần đỉnh cực trị |
| Pop khi cross>=0 | Nhầm trái/phải | Xác định sign orientation đúng |
| Upper quét cùng chiều lower | Không tạo đúng biên trên | Quét ngược |
| Ghép mà không bỏ hai đầu mút chung | Lặp góc | Pop cuối mỗi chuỗi trước ghép |
| Lặp đỉnh đầu cuối khi đề chỉ muốn h điểm | Sai số đỉnh | Trả chuỗi mở, polygon hiểu ngầm khép |
| All-collinear coi là polygon | Sai diện tích/hình dạng | Trả hai đầu mút |
| Bỏ qua n=0/1/2 | Lỗi truy cập list | Xử lý sớm |
| Tính shoelace bằng long không có bound | Tràn | BigInteger |
| Nhầm area2 với area | Sai gấp hai | area=abs(area2)/2 |
| Tọa độ double gần thẳng hàng dùng epsilon tùy tiện | Phán đoán sai | Robust predicate hoặc sai số quy định |
| Chỉ test một hình vuông | Bỏ lỗi điểm trùng, thẳng hàng, giới hạn | Oracle Jarvis và test suy biến |

## 15. Bài tập có đáp án

**Bài 1.** Bao lồi của (0,0),(2,0),(2,2),(0,2),(1,1)? *Đáp án:* bốn góc theo CCW.

**Bài 2.** Cross((0,0),(2,0),(2,2))? *Đáp án:* +4, quay trái.

**Bài 3.** Cross((0,0),(2,0),(2,-2))? *Đáp án:* -4, quay phải.

**Bài 4.** Cross((0,0),(1,1),(3,3))? *Đáp án:* 0, thẳng hàng.

**Bài 5.** Vì sao phải sort? *Đáp án:* để xây chuỗi x-monotone với thứ tự rõ ràng.

**Bài 6.** Vì sao phải dedup? *Đáp án:* một tọa độ lặp không tạo đỉnh mới.

**Bài 7.** Pop khi nào? *Đáp án:* cross của hai đỉnh cuối và điểm mới <=0.

**Bài 8.** Vì sao cross=0 cũng pop? *Đáp án:* không giữ điểm ở giữa một cạnh.

**Bài 9.** Upper quét chiều nào? *Đáp án:* từ phải sang trái.

**Bài 10.** Tại sao bỏ phần tử cuối mỗi chuỗi khi ghép? *Đáp án:* tránh trùng hai đầu mút.

**Bài 11.** Bao lồi của (0,0),(1,0),(2,0)? *Đáp án:* [(0,0),(2,0)].

**Bài 12.** Bao lồi của một tọa độ lặp 5 lần? *Đáp án:* một điểm.

**Bài 13.** Bao lồi tập rỗng? *Đáp án:* danh sách rỗng.

**Bài 14.** Tổng thao tác pop ở một chuỗi là O(n) vì sao? *Đáp án:* mỗi điểm được push một lần và pop tối đa một lần.

**Bài 15.** Độ phức tạp toàn bộ Andrew? *Đáp án:* O(n log n) thời gian, O(n) bộ nhớ.

**Bài 16.** Bao lồi hình vuông cạnh 2 có area2/area? *Đáp án:* 8/4.

**Bài 17.** Tam giác (0,0),(1,0),(0,1) có diện tích? *Đáp án:* 0.5.

**Bài 18.** area2 âm nghĩa là thứ tự gì? *Đáp án:* CW với polygon đơn không suy biến.

**Bài 19.** Long đủ tính cross mọi bộ tọa độ long? *Đáp án:* không, hiệu và tích có thể vượt signed long.

**Bài 20.** Điểm nằm giữa cạnh hull có được trả về? *Đáp án:* không trong phiên bản này.

**Bài 21.** Thay `<=0` thành `<0` có luôn cho tất cả điểm biên đúng không? *Đáp án:* không; phải xử lý trùng, thứ tự và all-collinear riêng.

**Bài 22.** Mọi điểm đầu vào ở phía nào của cạnh hull CCW? *Đáp án:* bên trái hoặc ngay trên cạnh.

**Bài 23.** Tại sao dùng Jarvis để đối chiếu? *Đáp án:* khác về điều khiển (chọn cạnh hỗ trợ, không dùng hai stack).

**Bài 24.** Tọa độ kinh/vĩ độ có được coi mặc định là mặt phẳng Euclid? *Đáp án:* không; cần hệ quy chiếu/phép chiếu phù hợp.

## 16. Checklist và ghi nhớ

1. Xác định đề hỏi đỉnh cực trị hay toàn bộ điểm trên biên.
2. Loại các tọa độ trùng sau sort `(x,y)`.
3. Không dùng phép trừ tọa độ có thể tràn trong comparator/cross.
4. Cross dương là quay trái; âm quay phải; 0 thẳng hàng.
5. Lower duyệt trái-phải, upper phải-trái; cùng pop khi `cross<=0`.
6. Bỏ phần tử cuối mỗi chuỗi trước khi ghép.
7. Đảm bảo hull CCW, bắt đầu lex-min, không lặp điểm đầu.
8. Xử lý 0,1,2 điểm và all-collinear.
9. Nếu tính diện tích, dùng shoelace chính xác và chia hai.
10. Kiểm containment, tính lồi nghiêm ngặt và oracle độc lập.

**Tóm tắt:** Andrew sort các điểm, dùng tích có hướng để giữ hai chuỗi chỉ quay trái, ghép thành bao lồi. Tổng thời gian O(n log n), bộ nhớ O(n). Tính đúng bắt nguồn từ việc các điểm bị pop không thể là đỉnh cực trị; tính ổn định của dấu cross phụ thuộc **số học không tràn**.
