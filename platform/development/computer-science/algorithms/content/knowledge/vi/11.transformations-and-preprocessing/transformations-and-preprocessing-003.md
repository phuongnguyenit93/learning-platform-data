# Nén tọa độ và bảo toàn quan hệ thứ tự

**Nén tọa độ (coordinate compression)** là kỹ thuật thay các giá trị ban đầu có thể rất lớn, rất nhỏ, âm hoặc thưa thớt bằng **thứ hạng của chúng trong danh sách giá trị phân biệt đã sắp xếp**. Kết quả là những số nguyên nhỏ, liên tiếp, rất tiện làm chỉ số cho mảng tần suất, Fenwick Tree, Segment Tree và nhiều thuật toán xử lý thứ tự.

Mục tiêu quan trọng **không phải thu nhỏ giá trị số học mà là giữ nguyên quan hệ thứ tự**. Với nén tọa độ chuẩn, nếu `x<y` thì mã nén của `x` nhỏ hơn mã nén của `y`; nếu `x=y` thì hai mã bằng nhau. Ngược lại, **hiệu số, khoảng cách, tỉ lệ và tổng của giá trị gốc không được bảo toàn**.

Xét mảng:

```text
Giá trị gốc:       [40, -10, 40, 7, -10, 1000000000]
Giá trị phân biệt
đã sắp tăng:       [-10, 7, 40, 1000000000]
Thứ hạng 0-based:    0   1   2       3

Dãy sau nén:       [ 2,  0,  2, 1,   0,       3]
```

Số `1.000.000.000` rất lớn nhưng chỉ có **3** giá trị phân biệt đứng trước nó, nên được mã hóa thành `3`. Hai lần xuất hiện `40` cùng nhận mã `2`, hai lần xuất hiện `-10` cùng nhận mã `0`. Thứ tự **các vị trí trong mảng ban đầu vẫn giữ nguyên**; chỉ giá trị tại mỗi vị trí được thay bằng mã.

## 1. Định nghĩa chính xác

Cho dãy `a` có `n` phần tử. Gọi `U` là dãy gồm **các giá trị phân biệt của `a`**, được sắp tăng nghiêm ngặt:

\[
U[0]<U[1]<\cdots<U[m-1],\qquad 0\le m\le n.
\]

Định nghĩa hàm nén `rank(x)` cho mỗi giá trị `x` có mặt trong `U` là **chỉ số duy nhất** `r` sao cho `U[r]=x`.

Với quy ước **0-based**, các mã liên tiếp từ `0` đến `m-1`. Dãy nén là:

\[
c[i]=\operatorname{rank}(a[i]),\quad 0\le i<n.
\]

Dãy `U` chính là **bảng giải mã** (dictionary): từ mã `r` ta lấy lại giá trị gốc `U[r]`. Nếu chỉ giữ `c` mà bỏ `U`, không thể khôi phục các giá trị gốc một cách duy nhất.

### Những tính chất được bảo toàn

Với mọi giá trị `x,y` thuộc tập giá trị đã đăng ký trong `U`:

- **Bảo toàn thứ tự nghiêm ngặt:** `x<y` khi và chỉ khi `rank(x)<rank(y)`.
- **Bảo toàn bằng nhau:** `x=y` khi và chỉ khi `rank(x)=rank(y)`.
- **Bảo toàn quan hệ không giảm:** `x<=y` khi và chỉ khi `rank(x)<=rank(y)`.
- **Bảo toàn dấu so sánh của từng cặp trong dãy:** `a[i]>a[j]` khi và chỉ khi `c[i]>c[j]`.
- **Bảo toàn số lần xuất hiện:** mỗi vị trí vẫn tồn tại, các bản sao của một giá trị vẫn cùng mã.
- **Bảo toàn thứ tự vị trí:** phần tử ban đầu ở vị trí `i` vẫn nằm ở vị trí `i` của dãy nén.

Điều này làm nén tọa độ phù hợp với những bài toán chỉ cần **so sánh giá trị hoặc đếm các phần tử nhỏ hơn/lớn hơn**: nghịch thế, số thứ hạng, LIS, truy vấn tần suất theo giá trị hay thống kê thứ tự.

### Những tính chất không được bảo toàn

Nén tọa độ **không phải phép biến đổi tuyến tính**:

```text
Giá trị gốc:     [-100, 4, 1000000]
Mã nén:          [   0, 1,       2]

Khoảng cách gốc:
  4 - (-100) = 104
  1000000 - 4 = 999996

Khoảng cách mã:
  1 - 0 = 1
  2 - 1 = 1
```

Vì vậy, nếu bài toán hỏi **khoảng cách tọa độ**, **tổng giá trị**, **trung bình**, **độ rộng đoạn trên trục số**, **ngưỡng chênh lệch `x-y>=d`** hoặc một phép tính hình học phụ thuộc khoảng cách thực, không được thay trực tiếp giá trị bằng mã rồi tính trên mã như thể số học được giữ nguyên.

Nén còn có thể làm mất ý nghĩa **các vị trí nguyên không xuất hiện**: giữa `U[1]=4` và `U[2]=1000000` là rất nhiều số nguyên, nhưng trong miền chỉ số nén chỉ có hai mã liên tiếp. Nếu thuật toán cần đo độ dài khoảng giữa hai mốc, phải dùng lại `U` hoặc lưu trọng số của những khoảng đó.

## 2. Quy ước 0-based, 1-based và vai trò của mảng U

Hai hệ đánh số thường gặp:

| Ý nghĩa | 0-based | 1-based |
|---|---:|---:|
| Giá trị nhỏ nhất trong `U` | 0 | 1 |
| Giá trị nhỏ thứ hai **phân biệt** | 1 | 2 |
| Giá trị lớn nhất trong `U` | `m-1` | `m` |
| Chuyển từ mã 0-based | `r` | `r+1` |
| Chuyển ngược về 0-based | `r` | `r-1` |

Trong Java, mảng dùng chỉ số **0-based**. Khi chỉ cần tra bảng `U` hoặc dùng Segment Tree trên đoạn `[0,m)`, mã `0..m-1` thường tự nhiên. Với **Fenwick Tree (Binary Indexed Tree)**, cấu trúc thường được cài với chỉ số **1-based**, nên sau khi nén cần dùng `rank+1` khi cập nhật.

Ví dụ:

```text
Giá trị gốc:      [40, -10, 40, 7, -10, 1000000000]
Mã nén 0-based:   [ 2,   0,  2, 1,   0,          3]
Chỉ số Fenwick:   [ 3,   1,  3, 2,   1,          4]
```

**Không nên trộn lẫn hai hệ:** `rank=0` là mã hợp lệ của giá trị nhỏ nhất, nhưng nếu đưa trực tiếp chỉ số `0` vào một hàm cập nhật Fenwick với vòng `index += index & -index`, chỉ số có thể không tăng và gây vòng lặp vô hạn. Đổi sang `rank+1` đúng một lần ở ranh giới API.

Một cách đặt tên biến giảm sai sót là `zeroBasedRank` và `fenwickIndex`. Đừng gọi cả hai là `index` nếu không giải thích.

### Hai loại thứ hạng dễ nhầm

- **Thứ hạng của giá trị phân biệt:** nén mỗi giá trị có mặt thành một mã duy nhất. Ví dụ `[2,2,5]` nén thành `[0,0,1]`.
- **Thứ hạng của từng lần xuất hiện trong mảng sắp:** cả hai bản sao `2` có thể chiếm các vị trí thứ `1` và `2` trong danh sách ba phần tử. Đó là cách đếm order statistics **có lặp**, không phải quy tắc cấp mã nén.

Nén tọa độ **không xóa** bản sao khỏi dãy đầu vào. Ta chỉ loại bản sao khi xây **danh sách từ điển `U`**, rồi gán lại mã cho mọi phần tử gốc. Việc `m<n` là bình thường khi dữ liệu có trùng.

## 3. Quy trình nén tọa độ bằng sắp xếp và loại trùng

Với mảng đầu vào `a`, cách triển khai offline cổ điển gồm:

1. Sao chép tất cả các giá trị của `a` sang mảng `sorted`; không thay đổi `a`.
2. Sắp `sorted` tăng dần bằng `Arrays.sort`.
3. Duyệt mảng đã sắp, **giữ đúng một lần xuất hiện** cho mỗi giá trị để tạo `U`.
4. Với mỗi `a[i]` trong mảng gốc, tìm vị trí bằng `Arrays.binarySearch(U,a[i])` để có `c[i]`.
5. Giữ đồng thời `U` và `c` nếu cần giải mã hoặc truy vấn ngưỡng sau này.

Ví dụ với `a=[50,10,50,-2,10]`:

```text
Bước 1: copy                  [50, 10, 50, -2, 10]
Bước 2: sort                  [-2, 10, 10, 50, 50]
Bước 3: unique = U            [-2, 10, 50]
Bước 4: gán mã theo U         [ 2,  1,  2,  0,  1]
Bước 5: giữ U để giải mã      U[2] = 50, U[0] = -2
```

**Bất biến của bước loại trùng:** `sorted[0..write)` luôn chứa các giá trị phân biệt đã thấy theo thứ tự tăng, còn `write` là số giá trị phân biệt đã giữ. Khi giá trị mới khác giá trị cuối được giữ, ghi nó vào `sorted[write]` rồi tăng `write`. Từ dữ liệu đã sắp, các bản sao cùng giá trị nằm cạnh nhau nên so với giá trị cuối đã giữ là đủ.

**Không trừ hai số `int` để so sánh thứ tự:** nếu giá trị có thể là `Integer.MIN_VALUE` hoặc `Integer.MAX_VALUE`, biểu thức `x-y` có thể tràn số. Sử dụng toán tử `<`/`>`, `Integer.compare` hoặc tìm kiếm nhị phân của thư viện.

### Ví dụ so sánh trước và sau

| Truy vấn trên giá trị gốc | Truy vấn tương đương trên mã | Kết quả có giữ nguyên? |
|---|---|---|
| `x < y` | `rank(x) < rank(y)` | Có, với `x,y` đã có trong `U` |
| `x == y` | `rank(x) == rank(y)` | Có |
| `x <= y` | `rank(x) <= rank(y)` | Có |
| Đếm `a[i] < a[j]` | Đếm `c[i] < c[j]` | Có |
| Tìm vị trí phần tử lớn nhất | Tìm vị trí có mã lớn nhất | Có |
| `x-y` là bao nhiêu? | `rank(x)-rank(y)` | **Không** |
| `x+y` là bao nhiêu? | `rank(x)+rank(y)` | **Không** |
| Có bao nhiêu số nguyên nằm giữa `x` và `y`? | Chênh lệch hai mã | **Không**: mã chỉ đếm giá trị phân biệt có mặt trong `U` |

Dòng cuối là một nhầm lẫn quan trọng: `rank(y)-rank(x)-1` (nếu `x<y` và cả hai có mặt) đếm **bao nhiêu giá trị phân biệt của từ điển nằm nghiêm ngặt giữa chúng**, không đếm mọi số nguyên nằm giữa hai tọa độ gốc.

## 4. Tra cứu khi giá trị truy vấn không thuộc từ điển

Một từ điển được xây **chỉ từ dữ liệu đã biết**. Nếu có truy vấn `x` **không xuất hiện trong `U`**, phải phân biệt ba thao tác:

1. **Tra mã chính xác `rankOfKnown(x)`:** chỉ hợp lệ khi `x` thuộc `U`. Nếu không, trả dấu hiệu không tồn tại hoặc ném lỗi có chủ đích.
2. **`lowerBound(x)`:** số phần tử của `U` **nhỏ hơn nghiêm ngặt `x`**, đồng thời là vị trí chèn đầu tiên để vẫn giữ thứ tự.
3. **`upperBound(x)`:** số phần tử của `U` **nhỏ hơn hoặc bằng `x`**, tức vị trí chèn sau tất cả phần tử bằng `x`.

Ví dụ với `U=[-10,7,40,1000000000]`:

```text
rankOfKnown(7)   = 1
rankOfKnown(39)  = KHÔNG TỒN TẠI (39 không có trong U)

lowerBound(39)   = 2   (có 2 giá trị: -10 và 7 < 39)
upperBound(40)   = 3   (có 3 giá trị: -10, 7, 40 <= 40)
lowerBound(-11)  = 0
upperBound(1000000000) = 4
```

Các kết quả `lowerBound`/`upperBound` nằm trong khoảng **`0..m`**, nên `m` có thể là kết quả hợp lệ để chỉ vị trí sau cuối. Đó **không phải mã nén của một giá trị thuộc `U`** (mã hợp lệ chỉ là `0..m-1`).

Khi cần đếm số **lần xuất hiện trong dãy gốc** có giá trị dưới ngưỡng `x`, `lowerBound(x)` chỉ cho biết **ranh giới theo giá trị phân biệt**. Cần thêm mảng tần suất, prefix sums hoặc Fenwick Tree trên các mã để đếm **số bản sao**. Không được lấy trực tiếp `lowerBound(x)` làm số phần tử gốc thỏa điều kiện khi có giá trị trùng.

### Thêm một giá trị mới sau khi nén

Ví dụ `U=[10,50]` tạo `10→0`, `50→1`. Nếu sau đó bổ sung `30`, từ điển đúng sẽ là `[10,30,50]` và `50` đổi mã từ `1` sang `2`.

Vì vậy, nén tọa độ chuẩn chủ yếu là **tiền xử lý offline**: phải biết trước các giá trị cần đưa vào thứ tự chung. Nếu có các **truy vấn/cập nhật với giá trị mới**, có thể gom toàn bộ giá trị từ dữ liệu và thao tác dự kiến trước khi nén. Nếu không thể biết trước, cân nhắc cây tìm kiếm cân bằng có thống kê thứ tự, cấu trúc có thể mở rộng động, hoặc cách tiếp cận khác. Không được âm thầm gán mã mới ở cuối cho `30`, vì như vậy phá quan hệ `10<30<50`.

## 5. Chương trình Java 17+ hoàn chỉnh

Chương trình sau tự xây từ điển và các mã nén, không phụ thuộc thư viện ngoài JDK. Nó minh họa:

- Nén thành các mã **0-based** theo thứ tự tăng, không thay đổi đầu vào.
- Chuyển sang chỉ số **1-based** khi cần tích hợp Fenwick Tree.
- Giải mã bằng `U[rank]`, tra mã chính xác và tìm `lowerBound/upperBound`.
- Ứng dụng bảo toàn quan hệ thứ tự để **đếm nghịch thế** với Fenwick Tree, tính cả các bản sao đúng cách.

Định nghĩa nghịch thế chuẩn: cặp chỉ số `i<j` sao cho `a[i]>a[j]`. Một phép nén đúng giữ nguyên kết quả đếm vì điều kiện so sánh trước/sau tương đương.

Lưu tệp **`CoordinateCompressionDemo.java`**:

```java
import java.util.Arrays;

public final class CoordinateCompressionDemo {
    private CoordinateCompressionDemo() {
    }

    static final class Compression {
        private final int[] unique;
        private final int[] ranks;

        private Compression(int[] unique, int[] ranks) {
            this.unique = unique;
            this.ranks = ranks;
        }

        int distinctCount() {
            return unique.length;
        }

        // Trả về bản sao, không để người gọi chỉnh dữ liệu nội bộ.
        int[] uniqueValues() {
            return Arrays.copyOf(unique, unique.length);
        }

        int[] zeroBasedRanks() {
            return Arrays.copyOf(ranks, ranks.length);
        }

        int[] oneBasedRanks() {
            int[] oneBased = new int[ranks.length];
            for (int i = 0; i < ranks.length; i++) {
                oneBased[i] = ranks[i] + 1;
            }
            return oneBased;
        }

        // Chỉ nhận giá trị đã có trong từ điển.
        int rankOfKnown(int value) {
            int index = Arrays.binarySearch(unique, value);
            if (index < 0) {
                throw new IllegalArgumentException(
                    "value is not in dictionary"
                );
            }
            return index;
        }

        int decode(int zeroBasedRank) {
            if (zeroBasedRank < 0 || zeroBasedRank >= unique.length) {
                throw new IllegalArgumentException(
                    "rank out of range"
                );
            }
            return unique[zeroBasedRank];
        }

        // Số giá trị PHÂN BIỆT nhỏ hơn x, có thể bằng m.
        int lowerBound(int x) {
            int lo = 0;
            int hi = unique.length;
            while (lo < hi) {
                int mid = lo + (hi - lo) / 2;
                if (unique[mid] < x) {
                    lo = mid + 1;
                } else {
                    hi = mid;
                }
            }
            return lo;
        }

        // Số giá trị PHÂN BIỆT nhỏ hơn hoặc bằng x.
        int upperBound(int x) {
            int lo = 0;
            int hi = unique.length;
            while (lo < hi) {
                int mid = lo + (hi - lo) / 2;
                if (unique[mid] <= x) {
                    lo = mid + 1;
                } else {
                    hi = mid;
                }
            }
            return lo;
        }
    }

    // Đầu vào khác null; tạo từ điển tăng nghiêm ngặt
    // và mã 0-based, không làm thay đổi mảng input.
    static Compression compress(int[] input) {
        if (input == null) {
            throw new IllegalArgumentException(
                "input must not be null"
            );
        }

        int[] sorted = Arrays.copyOf(input, input.length);
        Arrays.sort(sorted);

        int write = 0;
        for (int value : sorted) {
            if (write == 0 || sorted[write - 1] != value) {
                sorted[write] = value;
                write++;
            }
        }

        int[] unique = Arrays.copyOf(sorted, write);
        int[] ranks = new int[input.length];

        for (int i = 0; i < input.length; i++) {
            // Giá trị input[i] chắc chắn có trong unique.
            ranks[i] = Arrays.binarySearch(unique, input[i]);
        }
        return new Compression(unique, ranks);
    }

    // Fenwick Tree lưu số lần xuất hiện, chỉ số 1-based.
    static final class Fenwick {
        private final long[] tree;

        private Fenwick(int size) {
            tree = new long[size + 1];
        }

        void add(int oneBasedIndex, long delta) {
            for (int i = oneBasedIndex; i < tree.length; ) {
                tree[i] += delta;
                int step = i & -i;
                // Không để phép cộng chỉ số tràn int.
                if (step > tree.length - 1 - i) {
                    break;
                }
                i += step;
            }
        }

        long prefixSum(int oneBasedIndex) {
            long sum = 0L;
            for (int i = oneBasedIndex; i > 0; i -= i & -i) {
                sum += tree[i];
            }
            return sum;
        }
    }

    // Đếm cặp (i,j), i<j và a[i]>a[j].
    static long inversionCount(int[] input) {
        Compression compressed = compress(input);
        Fenwick fenwick = new Fenwick(compressed.distinctCount());
        long inversions = 0L;

        // Khi duyệt từ phải sang trái, Fenwick chỉ lưu
        // những phần tử nằm ở phía PHẢI vị trí i.
        for (int i = input.length - 1; i >= 0; i--) {
            int zeroBasedRank = compressed.ranks[i];

            // Các giá trị nhỏ hơn nghiêm ngặt có mã
            // 0..rank-1, tương ứng prefix Fenwick (rank).
            inversions += fenwick.prefixSum(zeroBasedRank);

            // Chỉ số Fenwick bắt đầu từ 1.
            fenwick.add(zeroBasedRank + 1, 1L);
        }
        return inversions;
    }

    public static void main(String[] args) {
        int[] data = {
            40, -10, 40, 7, -10, 1_000_000_000
        };
        Compression result = compress(data);

        System.out.println("Original: "
            + Arrays.toString(data));
        System.out.println("Unique: "
            + Arrays.toString(result.uniqueValues()));
        System.out.println("Ranks 0-based: "
            + Arrays.toString(result.zeroBasedRanks()));
        System.out.println("Ranks 1-based: "
            + Arrays.toString(result.oneBasedRanks()));

        System.out.println("Rank of 7: "
            + result.rankOfKnown(7));
        System.out.println("Decode rank 2: "
            + result.decode(2));
        System.out.println("Lower bound 39: "
            + result.lowerBound(39));
        System.out.println("Upper bound 40: "
            + result.upperBound(40));

        try {
            result.rankOfKnown(39);
        } catch (IllegalArgumentException expected) {
            System.out.println("Unknown 39: rejected");
        }

        System.out.println("Inversions sample: "
            + inversionCount(data));
        System.out.println("Inversions duplicates: "
            + inversionCount(new int[] {5, -2, 5, 3, -2}));

        System.out.println("All equal ranks: "
            + Arrays.toString(
                compress(new int[] {8, 8, 8}).zeroBasedRanks()));
        System.out.println("Empty ranks: "
            + Arrays.toString(
                compress(new int[0]).zeroBasedRanks()));
        System.out.println("Extreme ranks: "
            + Arrays.toString(compress(new int[] {
                Integer.MAX_VALUE, Integer.MIN_VALUE,
                0, Integer.MIN_VALUE
            }).zeroBasedRanks()));
    }
}
```

**Biên dịch và chạy** bằng JDK 17 trở lên:

```bash
javac CoordinateCompressionDemo.java
java CoordinateCompressionDemo
```

**Kết quả chuẩn:**

```text
Original: [40, -10, 40, 7, -10, 1000000000]
Unique: [-10, 7, 40, 1000000000]
Ranks 0-based: [2, 0, 2, 1, 0, 3]
Ranks 1-based: [3, 1, 3, 2, 1, 4]
Rank of 7: 1
Decode rank 2: 40
Lower bound 39: 2
Upper bound 40: 3
Unknown 39: rejected
Inversions sample: 6
Inversions duplicates: 6
All equal ranks: [0, 0, 0]
Empty ranks: []
Extreme ranks: [2, 0, 1, 0]
```

### Giải thích những dòng quan trọng

- `unique` là từ điển tăng **nghiêm ngặt**, không có bản sao. `ranks` có **cùng chiều dài và cùng thứ tự vị trí** với mảng gốc.
- Giá trị `40` có mã `2` vì đúng hai giá trị phân biệt `-10`, `7` đứng trước nó; giá trị `-10` có mã `0` tại cả hai lần xuất hiện.
- Mã 1-based là các mã 0-based cộng `1`, dùng làm chỉ số cho Fenwick Tree.
- `rankOfKnown(39)` bị từ chối vì `39` không được đưa vào `unique`. Nhưng `lowerBound(39)=2` vẫn hợp lệ vì hai giá trị phân biệt nhỏ hơn `39`.
- Với `data`, có `6` nghịch thế theo vị trí ban đầu. `inversionCount` đếm bằng quan hệ mã `rank(a[i])>rank(a[j])`, không bằng khoảng cách số học giữa mã.
- `[5,-2,5,3,-2]` có `6` nghịch thế; hai lần xuất hiện `5` cùng một mã nhưng được Fenwick ghi nhận là **hai lần cập nhật tần suất** khi duyệt.
- Mọi giá trị bằng `8` nhận mã `0`, nhưng **ba phần tử gốc vẫn còn đủ ba vị trí**.
- Với dãy rỗng, từ điển và mã đều rỗng. Với các giá trị `Integer.MIN_VALUE` và `Integer.MAX_VALUE`, thuật toán không dùng phép trừ để so sánh nên tránh tràn số.

### Vì sao Fenwick dùng `prefixSum(rank)` chứ không phải `prefixSum(rank+1)`?

Trong bản Fenwick này, mã nén 0-based của giá trị `x` là `r`; nó được cập nhật ở **chỉ số 1-based `r+1`**. Khi đang ở vị trí `i` và đã xử lý các phần tử **bên phải**, ta muốn đếm **chỉ những phần tử nhỏ hơn nghiêm ngặt `a[i]`**.

Các phần tử ấy có mã `0..r-1`, tức ở các chỉ số Fenwick `1..r`. Vì thế truy vấn `prefixSum(r)` mới đúng; truy vấn `prefixSum(r+1)` còn bao gồm những phần tử **bằng `a[i]`**, khiến nghịch thế bị đếm thừa khi có bản sao.

Ví dụ `[5,5]` có `0` nghịch thế. Nếu dùng tiền tố tới chỉ số của `5` thay vì tiền tố đứng trước nó, phần tử `5` ở bên trái sẽ bị tính nhầm với bản sao bên phải.

## 6. Chứng minh nén tọa độ bảo toàn thứ tự

Ta chứng minh tính chất chính thức của hàm `rank`.

Vì `U` chứa **mỗi giá trị phân biệt đúng một lần** theo **thứ tự tăng nghiêm ngặt**, mỗi giá trị gốc có đúng một chỉ số tương ứng.

**Nếu `x<y`:** do `U` sắp tăng, `x` phải xuất hiện trước `y`; vậy `rank(x)<rank(y)`.

**Nếu `rank(x)<rank(y)`:** chỉ số nhỏ hơn trong một dãy tăng nghiêm ngặt có giá trị nhỏ hơn, nên `U[rank(x)]<U[rank(y)]`, tức `x<y`.

**Nếu `x=y`:** vì chỉ có một vị trí cho mỗi giá trị phân biệt, hai giá trị nhận cùng một mã. Ngược lại, nếu mã bằng nhau thì cùng truy về một phần tử của `U`, nên giá trị gốc cũng bằng nhau.

Ba mệnh đề trên bao phủ mọi kiểu so sánh `<`, `==`, `>` và từ đó suy ra `<=`, `>=`. Đặc biệt, với mọi vị trí `i,j`:

\[
a[i]>a[j]\iff c[i]>c[j].
\]

**Hệ quả:** số nghịch thế, số cặp tăng/giảm theo so sánh, kết quả tìm thứ hạng phân biệt và vị trí của giá trị cực tiểu/cực đại được bảo toàn. Nếu thuật toán dựa **chỉ** vào kết quả các phép so sánh và số lần xuất hiện, việc thay bằng mã không đổi đáp án logic của nó.

**Giới hạn:** phép nén không phải **đẳng cự**, cũng không bảo toàn cộng/trừ. Chẳng hạn `x=7` và `y=40` có `y-x=33` nhưng mã của chúng chỉ khác `1`. Dùng `rank(y)-rank(x)` để suy ra `33` là lỗi về bản chất, không chỉ lỗi triển khai.

### Vì sao không nén bằng một phép băm tùy ý?

Một `HashMap` gán mã theo **thứ tự gặp** có thể cho:

```text
Dữ liệu:             [40, -10, 7]
Mã theo thứ tự gặp:  [ 0,   1, 2]
```

Ở đây `40 > -10` nhưng `0 < 1`, làm **đảo quan hệ thứ tự**. Việc mỗi giá trị có mã riêng không đủ; nén tọa độ cần **thứ hạng theo giá trị đã sắp**. Có thể dùng `HashMap<Integer,Integer>` để **tra nhanh** từ giá trị sang mã **sau khi đã sắp và cấp mã đúng**; không được lấy thứ tự duyệt HashMap hoặc thứ tự đầu vào làm thứ tự của các mã.

## 7. Độ phức tạp và lựa chọn triển khai

Giả sử mảng có `n` phần tử và `m` giá trị phân biệt (`0<=m<=n`).

| Bước | Thời gian | Bộ nhớ |
|---|---|---|
| Sao chép dãy và sắp tăng | `O(n log n)` với sắp so sánh thông dụng | `O(n)` cho bản sao, thêm chi phí nội bộ tùy thuật toán sắp |
| Loại trùng từ dãy đã sắp | `O(n)` | `O(m)` nếu tạo mảng `U` riêng |
| Tìm mã cho `n` phần tử bằng tìm kiếm nhị phân trên `U` | `O(n log m)` nếu `m>=2` | `O(n)` cho mảng mã |
| **Toàn bộ nén offline như ví dụ** | **`O(n log n)`** | **`O(n)`** |
| Tra mã chính xác, giải mã | `O(log m)` / `O(1)` | `O(1)` |
| `lowerBound/upperBound` trên `U` | `O(log m)` nếu `m>=2` | `O(1)` |
| Fenwick duyệt một lần sau nén | `O(n log m)` | `O(m)` |

Với `m=0` hoặc `m=1`, số bước của những phép tra là hằng số; không nên lấy `log 0` làm một chi phí có ý nghĩa.

Nếu cần tra rất nhiều lần, có thể tạo thêm `HashMap<Integer,Integer>` từ từng giá trị `U[r]` tới mã `r`, giúp tra chính xác ở thời gian **kỳ vọng `O(1)`** cho mỗi giá trị đã có. Tuy nhiên `lowerBound` và `upperBound` vẫn cần một cấu trúc duy trì **thứ tự giá trị**, như mảng `U` đã sắp. Bản dùng tìm kiếm nhị phân có ưu điểm đơn giản, không cần bảng băm và có giới hạn tra cứu `O(log m)`.

### Khi nào nén có lợi về bộ nhớ?

Giả sử giá trị là mã khách hàng từ `-2.000.000.000` đến `+2.000.000.000` nhưng dãy chỉ có vài nghìn giá trị phân biệt. Cấp phát mảng tần suất theo **giá trị gốc** vừa không thực tế vừa có vấn đề với chỉ số âm. Nén thành `0..m-1` cho phép cấp phát mảng dài khoảng `m` thay vì phụ thuộc miền giá trị số học khổng lồ.

Với các bài toán truy vấn hàng chục triệu lần, chi phí **tiền xử lý ban đầu** có thể được bù lại bởi việc các thao tác sau đó dùng một miền chỉ số gọn, thích hợp cho Fenwick, Segment Tree hoặc mảng đếm. Tuy nhiên, nén tự nó **không làm mất `O(n log n)` tiền xử lý** và không khiến mọi truy vấn tự động thành `O(1)`; chi phí phụ thuộc cấu trúc dữ liệu dùng sau nén.

## 8. Ứng dụng và cách chọn mốc nén

### 8.1. Đếm nghịch thế

Muốn đếm cặp `i<j` và `a[i]>a[j]`, nén bảo toàn chính xác phép so sánh `>`. Fenwick Tree quản lý số lần xuất hiện theo mã; duyệt phải sang trái, truy vấn số phần tử có mã nhỏ hơn rồi cập nhật mã hiện tại. Thời gian `O(n log n)` kể cả tiền xử lý, bộ nhớ `O(n)`.

### 8.2. Đếm số phần tử nhỏ hơn một ngưỡng

Với từ điển `U` và mảng tần suất `freq[r]`, muốn đếm số lần xuất hiện của giá trị **nhỏ hơn `x`**, lấy:

\[
b=\operatorname{lowerBound}(x),\qquad
\text{answer}=\sum_{r=0}^{b-1}freq[r].
\]

Với dấu **nhỏ hơn hoặc bằng `x`**, thay `b` bằng `upperBound(x)`. Hai công thức đúng cả khi `x` **không xuất hiện** trong `U`.

Lưu ý: `b` là số **giá trị phân biệt** dưới ngưỡng; tổng `freq` mới là số **phần tử gốc tính cả bản sao**.

### 8.3. Dãy con tăng dài nhất (LIS) và thống kê thứ hạng

Khi xử lý điều kiện **tăng nghiêm ngặt `a[j]<a[i]`**, có thể thay bằng `rank(a[j])<rank(a[i])`. Khi xử lý **không giảm `a[j]<=a[i]`**, thay bằng `rank(a[j])<=rank(a[i])`. Hai trường hợp khác nhau khi giá trị trùng; nén không xóa sự khác biệt đó. Với Segment Tree hoặc Fenwick lưu DP, việc truy vấn `<` hay `<=` quyết định ranh giới chỉ số được lấy.

### 8.4. Các khoảng tọa độ và quét đường thẳng

Trong bài hình học hoặc quét sự kiện, ta thường chỉ cần xử lý những **mốc tọa độ xuất hiện**. Nén giúp mảng/Segment Tree dùng chỉ số gọn. Nhưng nếu tính **độ dài phủ**, phải dùng hiệu `U[r+1]-U[r]` (trong kiểu số đủ lớn), **không** dùng `(r+1)-r=1`.

Một số bài yêu cầu biểu diễn **đoạn trống giữa các mốc**, ví dụ thao tác đóng/mở ô trên trục nguyên. Khi đó có thể phải nén thêm các mốc ranh giới, giá trị lân cận hoặc **đoạn giữa các mốc** tùy định nghĩa khoảng đóng/nửa mở. Việc thêm `x+1` phải được kiểm tra tràn số nếu `x` có thể đạt giới hạn của kiểu số.

### 8.5. Truy vấn offline có cập nhật

Nếu đề cho trước toàn bộ thao tác, có thể thu thập cả giá trị xuất hiện ở các lần cập nhật và ngưỡng truy vấn cần tham chiếu trước khi nén. Với ngưỡng chỉ dùng trong điều kiện `<`/`<=`, đôi khi không cần thêm ngưỡng vào `U` vì có `lowerBound/upperBound`. Nhưng **giá trị được chèn vào cấu trúc tần suất** phải có mã chính xác; cần có trong từ điển ngay từ đầu hoặc có cơ chế bổ sung lại cấu trúc.

## 9. Lỗi phổ biến

| Lỗi | Vì sao sai | Cách khắc phục |
|---|---|---|
| Gán mã theo thứ tự xuất hiện | Mã có thể không tăng theo giá trị | Sắp các **giá trị phân biệt** trước khi gán mã |
| Không loại trùng khi xây từ điển | Một giá trị có thể có nhiều chỉ số, làm rối định nghĩa rank | Duyệt mảng đã sắp và giữ một lần mỗi giá trị |
| Loại trùng ngay trong **dãy gốc** | Mất vị trí, mất số lần xuất hiện cần cho bài toán | Chỉ loại trùng khi tạo từ điển `U` |
| Dùng mã làm giá trị số học để tính hiệu/tổng | Không bảo toàn khoảng cách và độ lớn | Tính trên giá trị gốc hoặc giải mã qua `U` |
| Trộn rank 0-based với Fenwick 1-based | Có thể sai kết quả hoặc vòng lặp tại chỉ số 0 | `fenwickIndex=rank+1`, thống nhất ở API |
| Truy vấn Fenwick `prefixSum(rank+1)` để đếm giá trị **nhỏ hơn nghiêm ngặt** | Đếm cả các phần tử bằng nhau | Dùng `prefixSum(rank)` |
| Gọi `Arrays.binarySearch` rồi dùng kết quả âm như mã | Không có giá trị đó trong từ điển | Kiểm tra trả về; với ngưỡng dùng lower/upper bound |
| Lấy `lowerBound(x)` làm số bản sao nhỏ hơn `x` | Chỉ đếm giá trị phân biệt, không đếm số lần xuất hiện | Cộng tần suất của các mã trước ranh giới |
| Thêm giá trị mới mà không cập nhật thứ hạng cũ | Phá tính bảo toàn thứ tự khi giá trị chen vào giữa | Gom giá trị offline hoặc dùng cấu trúc động |
| Dùng `a-b` làm comparator | Tràn `int` ở giá trị cực trị | Dùng `Integer.compare(a,b)` |
| Quên lưu `U` khi cần giải mã | Mã không cho biết giá trị ban đầu | Lưu mảng giá trị phân biệt đã sắp |
| Dùng `x+1` trên `Integer.MAX_VALUE` khi thêm mốc ranh giới | Tràn về số âm | Nâng kiểu trước phép cộng, kiểm tra miền |
| Nhầm giá trị thứ hạng phân biệt với phần tử nhỏ thứ `k` tính cả lặp | Sai khi dãy có bản sao | Xác nhận quy ước rank và dùng tần suất phù hợp |

## 10. Kiểm thử các bất biến

Nên kiểm tra không chỉ đầu ra một ví dụ, mà cả những tính chất bắt buộc:

1. **Từ điển:** `U` tăng nghiêm ngặt, mọi giá trị gốc xuất hiện đúng một lần trong `U`.
2. **Giải mã:** với mọi `i`, `U[c[i]]==a[i]`.
3. **Bảo toàn quan hệ:** với mọi cặp `i,j` trên bộ dữ liệu nhỏ, dấu của phép so sánh giữa `a[i]` và `a[j]` phải bằng dấu so sánh giữa `c[i]` và `c[j]`.
4. **Bảo toàn bản sao:** `a[i]==a[j]` khi và chỉ khi `c[i]==c[j]`.
5. **Ranh giới:** mảng rỗng, một phần tử, toàn bộ phần tử bằng nhau, âm/dương xen kẽ, đã tăng, đã giảm.
6. **Giá trị cực trị:** `Integer.MIN_VALUE`, `Integer.MAX_VALUE`, `0` và các giá trị sát nhau.
7. **Ngưỡng không có trong `U`:** kiểm tra `lowerBound/upperBound` ở trước nhỏ nhất, giữa hai giá trị và sau lớn nhất.
8. **Ứng dụng Fenwick:** so số nghịch thế đếm bằng nén với một phương pháp brute-force `O(n²)` trên mảng nhỏ, bao gồm trường hợp nhiều giá trị bằng nhau.

Một bộ kiểm thử ngẫu nhiên có thể tạo mảng dài `0..50` với các giá trị trong miền nhỏ để tạo nhiều bản sao; đối chiếu `compress` và `inversionCount` với cách làm chậm dễ hiểu. **Chứng minh tính bảo toàn thứ tự** vẫn là cơ sở tổng quát, còn kiểm thử giúp phát hiện lỗi triển khai, chỉ số và tràn số.

## 11. Bài tập thực hành

**Bài 1 — Nén cơ bản.** Cho dãy `[100,-7,100,0,-7,8]`. Viết từ điển `U` và dãy nén 0-based.

*Đáp án đối chiếu:* `U=[-7,0,8,100]`; dãy nén là `[3,0,3,1,0,2]`. Các vị trí vẫn giữ nguyên.

**Bài 2 — Phân biệt hai hệ chỉ số.** Với `U=[-7,0,8,100]`, giá trị `8` có mã 0-based bao nhiêu và dùng chỉ số Fenwick bao nhiêu?

*Đáp án:* mã `2`, chỉ số Fenwick `3`.

**Bài 3 — Truy vấn giá trị chưa có.** Với `U=[-10,7,40,1000000000]`, tính `lowerBound(39)`, `upperBound(7)` và giải thích tại sao không được trả `rankOfKnown(39)=2`.

*Đáp án:* `lowerBound(39)=2`, `upperBound(7)=2`. Giá trị `39` không thuộc từ điển; số `2` là **vị trí chèn**, không phải mã hiện có của `39`.

**Bài 4 — Bảo toàn so sánh, không bảo toàn độ dài.** Cho `x=-100`, `y=4`, `z=1000000`. Tại sao `rank(z)-rank(y)=1` nhưng `z-y` lại rất lớn?

*Gợi ý:* rank chỉ đếm **bao nhiêu mốc phân biệt đứng trước**, không đo khoảng cách số học.

**Bài 5 — Đếm nghịch thế.** Cho `a=[5,-2,5,3,-2]`. Tìm dãy nén 0-based và đếm các cặp `i<j` với `a[i]>a[j]`.

*Đáp án:* `U=[-2,3,5]`, dãy nén `[2,0,2,1,0]`, số nghịch thế **`6`**. Nếu đếm theo mã vẫn phải được `6`.

**Bài 6 — Ngưỡng tính cả bản sao.** Có dãy `[2,2,5,9,9,9]`, từ điển `U=[2,5,9]`. Có bao nhiêu phần tử gốc `<=5`? Có bao nhiêu **giá trị phân biệt** `<=5`?

*Đáp án:* có **3** lần xuất hiện (`2,2,5`) nhưng chỉ **2** giá trị phân biệt (`2,5`). `upperBound(5)=2` chỉ trả đáp án loại thứ hai; muốn đếm bản sao phải cộng `freq[0]+freq[1]=2+1=3`.

**Bài 7 — Dữ liệu thay đổi.** Từ điển ban đầu `U=[10,50]`, sau đó xuất hiện `30`. Nêu vì sao không thể tùy tiện cấp `30→2` và vẫn khẳng định nén bảo toàn thứ tự.

*Đáp án:* vì `10<30<50` nhưng mã mới `0<2` lại lớn hơn mã `1` của `50`; cần xây lại `U=[10,30,50]` hoặc có thiết kế thứ tự động phù hợp.

**Bài 8 — Đoạn hình học.** Hai mốc `x=10`, `y=1.000.010` được nén thành `0` và `1`. Nếu một thuật toán cần chiều dài thật của đoạn `[x,y)`, phải trả bao nhiêu?

*Đáp án:* chiều dài thật là `1.000.000` đơn vị, không phải `1`; cần hiệu giá trị từ điển `U[1]-U[0]` với kiểu số phù hợp.

## Ghi nhớ

**Nén tọa độ = sắp các giá trị phân biệt, gán thứ hạng liên tiếp, rồi thay mỗi phần tử gốc bằng thứ hạng tương ứng.** Nó bảo toàn hoàn toàn **`<`, `>`, `==`, `<=` và `>=`** giữa các giá trị thuộc từ điển, nhưng **không bảo toàn khoảng cách và phép cộng/trừ**. Mảng mã vẫn giữ độ dài, vị trí và số lần xuất hiện của dãy gốc.

Trước khi nén, hãy xác nhận bài toán chỉ cần **thứ tự hay cần độ dài số học**, có xử lý **giá trị trùng** không, dùng rank **0-based hay 1-based**, và có **giá trị mới phát sinh sau tiền xử lý** không. Khi kết hợp Fenwick/Segment Tree, ranh giới `lowerBound/upperBound` và phép cộng `1` ở chỉ số phải được định nghĩa nhất quán. Đó là điều giúp kỹ thuật biến một miền giá trị khổng lồ thành miền chỉ số nhỏ mà vẫn **không làm sai quan hệ thứ tự**.
