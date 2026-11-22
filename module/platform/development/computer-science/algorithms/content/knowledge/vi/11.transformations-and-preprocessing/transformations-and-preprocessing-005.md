# Tiền xử lý một lần cho nhiều truy vấn

Một bài toán có thể chứa **một bộ dữ liệu lớn và hàng nghìn, hàng triệu câu hỏi** về chính bộ dữ liệu đó. Nếu mỗi truy vấn đều duyệt lại toàn bộ đầu vào, tổng thời gian dễ vượt giới hạn dù thuật toán trả lời *một câu hỏi* có vẻ đơn giản.

**Tiền xử lý một lần cho nhiều truy vấn (preprocess once, query many times)** là chiến lược dành một lượng công việc ban đầu để xây **thông tin phụ trợ** — ví dụ tổng tiền tố, mảng đã sắp, bảng tra cứu, chỉ mục băm, sparse table hoặc cây truy vấn — sau đó dùng thông tin này trả lời các câu hỏi nhanh hơn.

Điều cần tối ưu không phải riêng thời gian của một truy vấn, mà là **tổng chi phí xây cấu trúc + trả lời mọi truy vấn + bảo trì khi dữ liệu thay đổi**, trong giới hạn bộ nhớ cho phép.

## 1. Mô hình hóa bài toán trước khi tiền xử lý

Giả sử có:

- **n** phần tử dữ liệu gốc.
- **q** truy vấn được gửi đến cùng dữ liệu.
- **U** lần cập nhật dữ liệu, nếu có.
- **B(n)** là thời gian xây cấu trúc tiền xử lý.
- **Q(n)** là thời gian trả lời một truy vấn từ cấu trúc.
- **A(n)** là thời gian cho một lần cập nhật cấu trúc, nếu hỗ trợ.

Tổng chi phí xấp xỉ:

**Tổng = B(n) + q × Q(n) + U × A(n)**

Nếu không tiền xử lý, giả sử mỗi truy vấn mất **D(n)**, tổng thời gian là **q × D(n)**. Tiền xử lý có lợi về mặt thời gian khi:

**B(n) + q × Q(n) + U × A(n) < q × D(n)**,

đồng thời bộ nhớ phụ và chi phí xây cấu trúc phải chấp nhận được. Đây là công thức phân tích theo mô hình trừu tượng, không phải cách dự báo chính xác thời gian mili-giây.

Các câu hỏi cần xác định ngay từ đầu:

1. Dữ liệu **tĩnh** (không thay đổi giữa các truy vấn) hay **động** (có cập nhật)?
2. Truy vấn hỏi **tổng, đếm, min/max, tồn tại, thứ tự, khoảng giá trị, khoảng vị trí** hay điều kiện phức tạp hơn?
3. q là 1, vài chục hay hàng triệu? Có biết trước toàn bộ truy vấn để xử lý **offline** không?
4. Có thể dùng **O(n)**, **O(n log n)**, **O(n²)** hay chỉ O(1) bộ nhớ phụ?
5. Cần trả **giá trị**, **chỉ số gốc**, **tập phần tử** hay chỉ true/false?
6. Phép toán gộp có tính chất đặc biệt như **kết hợp, có nghịch đảo, idempotent** không?

Không có một cấu trúc tiền xử lý tối ưu cho mọi loại truy vấn. Một mảng tổng tiền tố không tự giải nhanh bài toán min đoạn; sparse table min không tự trả tổng đoạn; chỉ mục băm thường không hỗ trợ truy vấn thứ tự.

## 2. Ví dụ mở đầu: tổng nhiều đoạn liên tiếp

Cho mảng số nguyên:

~~~text
index:  0  1  2  3  4  5
a:      5  1  4  1  7  3
~~~

Giả sử nhiều lần hỏi tổng **a[l] + a[l+1] + ... + a[r−1]** trên đoạn nửa mở **[l,r)**.

### Cách trực tiếp: cộng lại trên từng truy vấn

~~~text
rangeSum(a, l, r):
    answer = 0
    for i = l..r-1:
        answer += a[i]
    return answer
~~~

Với đoạn dài k = r−l, chi phí là **O(k)**. Nếu nhiều truy vấn đều dài gần n, tổng chi phí xấu nhất có thể là **O(qn)**.

### Tiền xử lý: tổng tiền tố (prefix sum)

Xây mảng P dài n+1:

**P[0] = 0**

**P[i+1] = P[i] + a[i]**, với 0 ≤ i < n.

Với dữ liệu trên:

~~~text
a:        [5, 1, 4, 1, 7, 3]
P:     [0, 5, 6, 10, 11, 18, 21]
index:   0  1  2   3   4   5   6
~~~

Định nghĩa **P[i] = tổng của a[0..i)**. Khi đó:

**sum(l,r) = P[r] − P[l]**.

Ví dụ:

- **[1,5)**: P[5] − P[1] = 18 − 5 = **13**, tức 1+4+1+7.
- **[0,6)**: P[6] − P[0] = 21 − 0 = **21**.
- **[2,2)**: P[2] − P[2] = **0** — đoạn rỗng có tổng bằng 0.

Chi phí:

| Công việc | Không tiền xử lý | Prefix sum |
| --- | --- | --- |
| Xây dữ liệu phụ | Không cần | O(n) |
| Một truy vấn [l,r) | O(r−l) | **O(1)** |
| q truy vấn dài tùy ý | Có thể O(qn) | **O(n+q)** tính cả xây |
| Bộ nhớ phụ | O(1) | **O(n)** |

### Chứng minh công thức

P[r] là tổng của a[0],...,a[r−1]. P[l] là tổng của a[0],...,a[l−1]. Trừ hai đại lượng loại bỏ toàn bộ phần trước l, chỉ giữ a[l],...,a[r−1]. Công thức không phụ thuộc dấu của các phần tử: số âm, số dương và số 0 đều hợp lệ.

**Lưu ý quan trọng:** P có n+1 phần tử và dùng đoạn **[l,r)**. Truy cập P[r] hợp lệ khi **r = n**, nhưng truy cập a[n] không hợp lệ. Nếu đề dùng đoạn đóng **[L,R]**, chuyển sang **P[R+1] − P[L]**; chỉ thực hiện khi 0 ≤ L ≤ R < n.

### Prefix sum có trả lời truy vấn min/max không?

Không trực tiếp. Phép cộng có phép trừ để **loại bỏ** tiền tố phía trước, nhưng từ “minimum của cả tiền tố” và “minimum của tiền tố ngắn hơn” không thể suy ra minimum của phần còn lại bằng một phép trừ. Ví dụ hai mảng có cùng các cực trị tiền tố đến một thời điểm vẫn có thể có min hoàn toàn khác nhau ở đoạn cần hỏi.

Hãy chọn cấu trúc dựa trên **phép toán mà truy vấn thật sự yêu cầu**, thay vì nghĩ có một loại “prefix” chung dùng cho mọi câu hỏi.

## 3. Điều kiện nền tảng: dữ liệu tĩnh và dữ liệu động

**Static queries (truy vấn trên dữ liệu tĩnh):** xây cấu trúc từ một phiên bản dữ liệu, rồi hỏi nhiều lần mà không sửa phiên bản đó. Prefix sum, sorted array và sparse table rất hiệu quả trong bối cảnh này.

**Dynamic queries (truy vấn có cập nhật):** dữ liệu thay đổi giữa các câu hỏi. Nếu sửa a[i], mọi P[j] với j > i có thể thay đổi. Việc sửa lại prefix sum thông thường mất O(n) trường hợp xấu nhất; tổng tiền tố đã xây **không còn đúng** sau cập nhật nếu chưa đồng bộ.

Ví dụ ban đầu a = [5,1,4,1,7,3] và P[5]=18. Nếu cập nhật a[1] từ 1 thành 10, truy vấn [1,5) đáng ra là **22**, không phải 13. Dùng P cũ sẽ trả sai.

Cấu trúc phù hợp phụ thuộc kiểu thay đổi:

- **Không cập nhật:** prefix sum O(1) truy vấn là rất mạnh.
- **Cập nhật một điểm, hỏi tổng đoạn:** Fenwick tree (Binary Indexed Tree) hoặc segment tree hỗ trợ cập nhật và truy vấn O(log n).
- **Cập nhật cả đoạn, rồi hỏi:** cần thiết kế lazy propagation, difference array hoặc cấu trúc khác tùy việc có truy vấn xen kẽ không.
- **Dữ liệu thay đổi theo từng phiên bản:** có thể tính lại chỉ mục, giữ chỉ mục riêng theo phiên bản hoặc dùng cấu trúc persistent nếu yêu cầu.

Không được dùng bảng tiền xử lý của **phiên bản cũ** để âm thầm trả lời trên **phiên bản mới**.

## 4. Tiền xử lý bằng sắp xếp: tìm kiếm và đếm theo giá trị

Giả sử dữ liệu ban đầu chưa có thứ tự. Nếu q rất lớn và câu hỏi liên tục hỏi “bao nhiêu giá trị bằng x?” hoặc “bao nhiêu giá trị trong đoạn [L,R]?”, có thể **sắp xếp một lần**, rồi dùng **tìm kiếm nhị phân** cho mỗi truy vấn.

Với a = [5,1,4,1,7,3], mảng đã sắp là:

~~~text
sorted = [1, 1, 3, 4, 5, 7]
index      0  1  2  3  4  5
~~~

Định nghĩa:

- **lowerBound(x):** chỉ số đầu tiên i mà sorted[i] ≥ x; không có thì trả n.
- **upperBound(x):** chỉ số đầu tiên i mà sorted[i] > x; không có thì trả n.

Các công thức:

**countEqual(x) = upperBound(x) − lowerBound(x)**

**countInClosedValueRange(L,R) = upperBound(R) − lowerBound(L)** khi L ≤ R.

Ví dụ:

- countEqual(1) = 2 vì hai phần tử 1 nằm tại chỉ số 0 và 1.
- countInClosedValueRange(1,4) = 4 vì các giá trị 1,1,3,4 thỏa điều kiện.
- countInClosedValueRange(2,6) = 3 vì có 3,4,5.
- Nếu L > R thì đoạn giá trị rỗng, trả 0.

**Thời gian:** sắp xếp thường O(n log n) với thuật toán so sánh thích hợp; mỗi lower/upper bound O(log n), nên q truy vấn có tổng chi phí **O(n log n + q log n)**.

**Giữ vị trí gốc:** sắp xếp làm thay đổi thứ tự. Nếu cần trả chỉ số trong đầu vào ban đầu, phải lưu **(giá trị, chỉ số gốc)** khi sắp hoặc xây chỉ mục giá trị → danh sách vị trí gốc. Mã Java bên dưới **clone** dữ liệu trước khi sắp nên không làm thay đổi mảng nguồn.

### Khi nào dùng HashMap thay vì sort?

Với truy vấn chỉ hỏi **tồn tại hoặc đếm chính xác một khóa**:

- Duyệt một lần xây **HashMap<giá trị, tần suất>**: trung bình O(n).
- Mỗi lần tra tần suất: trung bình O(1), nhưng hash không bảo đảm thời gian O(1) trong mọi trường hợp và phải cấp thêm bộ nhớ.
- Nếu hỏi **giá trị nằm trong một khoảng**, HashMap không có thứ tự sẵn để xác định nhanh [L,R]; sorted array + two bounds hoặc cấu trúc có thứ tự phù hợp hơn.

Cấu trúc băm lưu theo khóa nên không tự giữ thứ tự ban đầu; nếu cần tất cả chỉ số gốc, value phải là danh sách các chỉ số, không chỉ một tần suất.

## 5. Tiền xử lý min/max trên đoạn tĩnh: sparse table

Với n phần tử **không thay đổi**, cần trả lời nhiều truy vấn:

**min(a[l], ..., a[r−1])** trên đoạn **không rỗng [l,r)**.

Quét trực tiếp mất O(r−l) cho mỗi truy vấn. Prefix sum không hỗ trợ min, nhưng có thể xây **sparse table**:

**st[k][i] = min của đoạn [i, i+2^k)** nếu đoạn nằm trong mảng.

Cơ sở: **st[0][i] = a[i]**.

Khi k > 0:

**st[k][i] = min(st[k−1][i], st[k−1][i+2^(k−1)])**.

Vì một đoạn độ dài 2^k gồm hai nửa liên tiếp độ dài 2^(k−1), công thức đúng theo phép min.

### Trả lời một truy vấn O(1)

Cho độ dài len = r−l > 0; chọn **k = floor(log₂ len)**. Hai đoạn:

- [l, l+2^k)
- [r−2^k, r)

cùng nằm trong [l,r) và **phủ toàn bộ** [l,r). Chúng có thể **chồng lặp** nếu len không phải lũy thừa của 2.

Do **min(x,x)=x** (phép min có tính *idempotent*), phần tử bị tính hai lần không gây vấn đề:

**rangeMin(l,r) = min(st[k][l], st[k][r−2^k])**.

Với a = [5,1,4,1,7,3]:

- min[1,5) = min(1,4,1,7) = **1**.
- min[4,6) = min(7,3) = **3**.
- min[0,6) = **1**.

Chi phí sparse table:

- Xây: **O(n log n)** thời gian.
- Bộ nhớ: **O(n log n)**.
- Truy vấn min/max tĩnh: **O(1)** sau khi có bảng log₂.

**Cảnh báo:** không áp dụng công thức **hai đoạn chồng lặp** để tính **tổng** vì phần giao sẽ bị cộng hai lần. Với tổng đoạn, prefix sum phù hợp hơn. Sparse table cũng không thuận tiện với cập nhật điểm: khi một phần tử thay đổi, nhiều ô bảng phụ thuộc có thể phải xây lại.

## 6. Prefix sum hai chiều: tổng hình chữ nhật

Với ma trận gồm R hàng, C cột, nhiều truy vấn hỏi tổng các ô trong hình chữ nhật. Quét từng hình chữ nhật có thể tốn O(chiều cao × chiều rộng) mỗi lần.

Định nghĩa prefix sum 2D **P** kích thước (R+1) × (C+1):

**P[r+1][c+1] = A[r][c] + P[r][c+1] + P[r+1][c] − P[r][c]**.

P[r][c] là tổng các ô trong **[0,r) × [0,c)**.

Với hình chữ nhật nửa mở **[r1,r2) × [c1,c2)**:

**sumRect = P[r2][c2] − P[r1][c2] − P[r2][c1] + P[r1][c1]**.

Giải thích bao hàm–loại trừ:

1. Lấy tổng góc trên-trái đến (r2,c2).
2. Trừ các hàng trước r1.
3. Trừ các cột trước c1.
4. Cộng lại phần giao đã bị trừ hai lần.

Ví dụ:

~~~text
A =
1 2 3
4 5 6
7 8 9
~~~

- Hàng [0,2), cột [1,3): 2+3+5+6 = **16**.
- Hàng [1,3), cột [0,2): 4+5+7+8 = **24**.
- Toàn ma trận: **45**.

Xây bảng tốn O(RC) thời gian và O(RC) bộ nhớ; mỗi truy vấn hình chữ nhật O(1). Phải dùng **quy ước biên nhất quán**. Nếu đề cho tọa độ đóng [r1,r2] × [c1,c2], cần đổi thành [r1,r2+1) × [c1,c2+1) sau khi kiểm tra giới hạn.

## 7. Chương trình Java 17+ chạy độc lập

Chương trình minh họa **bốn kiểu tiền xử lý** trên dữ liệu tĩnh:

1. **PrefixSum**: tổng nhiều đoạn theo **vị trí**, O(1) mỗi truy vấn.
2. **SortedCounter**: sắp xếp bản sao và đếm theo **giá trị**, O(log n) mỗi truy vấn.
3. **SparseMin**: min trên đoạn vị trí không rỗng, O(1) mỗi truy vấn sau O(n log n) tiền xử lý.
4. **Prefix2D**: tổng hình chữ nhật trên ma trận, O(1) mỗi truy vấn.

Toàn bộ chỉ số dùng **0-based** và đoạn **nửa mở**. Để dễ kiểm tra, các lớp có xác minh biên đầu vào thay vì âm thầm trả một kết quả sai.

~~~java
import java.util.Arrays;
import java.util.Objects;

public class PreprocessManyQueriesDemo {

    static void checkRange(int from, int to, int n) {
        if (from < 0 || to < from || to > n) {
            throw new IndexOutOfBoundsException(
                    "Invalid range [" + from + "," + to + ") for n=" + n);
        }
    }

    static final class PrefixSum {
        private final long[] prefix;

        PrefixSum(int[] a) {
            Objects.requireNonNull(a, "array");
            prefix = new long[a.length + 1];
            for (int i = 0; i < a.length; i++) {
                prefix[i + 1] = prefix[i] + a[i];
            }
        }

        long sum(int from, int to) {
            checkRange(from, to, prefix.length - 1);
            return prefix[to] - prefix[from];
        }
    }

    static final class SortedCounter {
        private final int[] sorted;

        SortedCounter(int[] a) {
            Objects.requireNonNull(a, "array");
            sorted = a.clone();
            Arrays.sort(sorted);
        }

        int[] snapshot() {
            return sorted.clone();
        }

        int lowerBound(int x) {
            int lo = 0;
            int hi = sorted.length;
            while (lo < hi) {
                int mid = lo + (hi - lo) / 2;
                if (sorted[mid] < x) {
                    lo = mid + 1;
                } else {
                    hi = mid;
                }
            }
            return lo;
        }

        int upperBound(int x) {
            int lo = 0;
            int hi = sorted.length;
            while (lo < hi) {
                int mid = lo + (hi - lo) / 2;
                if (sorted[mid] <= x) {
                    lo = mid + 1;
                } else {
                    hi = mid;
                }
            }
            return lo;
        }

        int countEqual(int x) {
            return upperBound(x) - lowerBound(x);
        }

        int countClosedValueRange(int left, int right) {
            if (left > right) {
                return 0;
            }
            return upperBound(right) - lowerBound(left);
        }
    }

    static final class SparseMin {
        private final int n;
        private final int[] log2;
        private final int[][] st;

        SparseMin(int[] a) {
            Objects.requireNonNull(a, "array");
            if (a.length == 0) {
                throw new IllegalArgumentException(
                        "SparseMin requires a non-empty array");
            }
            n = a.length;

            log2 = new int[n + 1];
            for (int i = 2; i <= n; i++) {
                log2[i] = log2[i / 2] + 1;
            }

            st = new int[log2[n] + 1][n];
            System.arraycopy(a, 0, st[0], 0, n);

            for (int k = 1; k < st.length; k++) {
                int len = 1 << k;
                int half = len >> 1;
                for (int i = 0; i + len <= n; i++) {
                    st[k][i] = Math.min(
                            st[k - 1][i],
                            st[k - 1][i + half]);
                }
            }
        }

        int min(int from, int to) {
            checkRange(from, to, n);
            if (from == to) {
                throw new IllegalArgumentException(
                        "Minimum of an empty range is undefined");
            }
            int k = log2[to - from];
            int len = 1 << k;
            return Math.min(st[k][from], st[k][to - len]);
        }
    }

    static final class Prefix2D {
        private final int rows;
        private final int cols;
        private final long[][] prefix;

        Prefix2D(int[][] a) {
            Objects.requireNonNull(a, "matrix");
            rows = a.length;
            cols = (rows == 0) ? 0
                    : Objects.requireNonNull(a[0], "matrix row").length;

            for (int r = 0; r < rows; r++) {
                Objects.requireNonNull(a[r], "matrix row");
                if (a[r].length != cols) {
                    throw new IllegalArgumentException(
                            "Matrix must be rectangular");
                }
            }

            prefix = new long[rows + 1][cols + 1];
            for (int r = 0; r < rows; r++) {
                for (int c = 0; c < cols; c++) {
                    prefix[r + 1][c + 1] = a[r][c]
                            + prefix[r][c + 1]
                            + prefix[r + 1][c]
                            - prefix[r][c];
                }
            }
        }

        long sum(int r1, int r2, int c1, int c2) {
            checkRange(r1, r2, rows);
            checkRange(c1, c2, cols);
            return prefix[r2][c2] - prefix[r1][c2]
                    - prefix[r2][c1] + prefix[r1][c1];
        }
    }

    public static void main(String[] args) {
        int[] data = {5, 1, 4, 1, 7, 3};

        PrefixSum sums = new PrefixSum(data);
        SortedCounter counter = new SortedCounter(data);
        SparseMin mins = new SparseMin(data);

        System.out.println("Original: " + Arrays.toString(data));
        System.out.println("Sum [1,5): " + sums.sum(1, 5));
        System.out.println("Sum [0,6): " + sums.sum(0, 6));

        System.out.println("Sorted: "
                + Arrays.toString(counter.snapshot()));
        System.out.println("Count value 1: " + counter.countEqual(1));
        System.out.println("Count values [1,4]: "
                + counter.countClosedValueRange(1, 4));
        System.out.println("Count values [2,6]: "
                + counter.countClosedValueRange(2, 6));

        System.out.println("Min [1,5): " + mins.min(1, 5));
        System.out.println("Min [4,6): " + mins.min(4, 6));

        int[][] grid = {
                {1, 2, 3},
                {4, 5, 6},
                {7, 8, 9}
        };
        Prefix2D matrixSums = new Prefix2D(grid);

        System.out.println("Rect [0,2)x[1,3): "
                + matrixSums.sum(0, 2, 1, 3));
        System.out.println("Rect [1,3)x[0,2): "
                + matrixSums.sum(1, 3, 0, 2));
        System.out.println("Rect all: "
                + matrixSums.sum(0, 3, 0, 3));
    }
}
~~~

Lưu mã vào tệp **PreprocessManyQueriesDemo.java**. Biên dịch và chạy với **JDK 17+**:

~~~bash
javac PreprocessManyQueriesDemo.java
java PreprocessManyQueriesDemo
~~~

Đầu ra dự kiến chính xác:

~~~text
Original: [5, 1, 4, 1, 7, 3]
Sum [1,5): 13
Sum [0,6): 21
Sorted: [1, 1, 3, 4, 5, 7]
Count value 1: 2
Count values [1,4]: 4
Count values [2,6]: 3
Min [1,5): 1
Min [4,6): 3
Rect [0,2)x[1,3): 16
Rect [1,3)x[0,2): 24
Rect all: 45
~~~

### Phân tích cụ thể từng lớp

**PrefixSum:** tạo mảng long dài n+1. Hàm sum chỉ trừ hai số, không duyệt lại dữ liệu. Dùng long vì tổng của nhiều số int có thể vượt giới hạn int; nếu tổng thật vượt miền long, vẫn cần kiểu rộng hơn.

**SortedCounter:** dùng a.clone() và Arrays.sort để giữ nguyên dữ liệu gốc. Mỗi truy vấn đếm dùng hai binary search. upperBound(x) tìm phần tử đầu tiên > x; lowerBound(x) tìm phần tử đầu tiên ≥ x. Chúng trả vị trí chèn khi không có phần tử tương ứng, nên không được truy cập sorted[n] khi bound = n.

**SparseMin:** lưu kết quả min các đoạn có độ dài lũy thừa của 2; bảng log2 giúp chọn k trong O(1). Truy vấn yêu cầu **from < to**, vì minimum của đoạn rỗng không được định nghĩa trong ví dụ này. Nó chỉ phù hợp khi dữ liệu gốc không đổi sau tiền xử lý.

**Prefix2D:** tiền xử lý O(RC), chỉ dùng bốn phần tử của bảng prefix cho mỗi hình chữ nhật. Chương trình kiểm tra ma trận **hình chữ nhật** (các hàng cùng số cột), kể cả trường hợp có 0 hàng/0 cột. Cấu trúc trả tổng 0 cho hình chữ nhật rỗng hợp lệ.

**Tính tĩnh:** cả bốn lớp đều lưu **ảnh chụp trạng thái lúc xây**. Thay đổi mảng data hoặc grid sau đó **không cập nhật** prefix, bản sao sorted, sparse table hoặc prefix 2D. Muốn truy vấn giá trị mới, phải xây lại hoặc chuyển sang cấu trúc có hỗ trợ cập nhật.

## 8. Chọn cấu trúc theo loại truy vấn

| Loại truy vấn trên dữ liệu tĩnh | Tiền xử lý thường dùng | Xây | Mỗi truy vấn | Bộ nhớ phụ |
| --- | --- | --- | --- | --- |
| Tổng đoạn [l,r) | Prefix sum | O(n) | **O(1)** | O(n) |
| XOR đoạn | Prefix XOR | O(n) | **O(1)** | O(n) |
| Đếm số phần tử thỏa điều kiện cố định trong đoạn | Prefix count | O(n) | **O(1)** | O(n) |
| Đếm số phần tử bằng x bất kỳ | HashMap tần suất | O(n) kỳ vọng | **O(1)** kỳ vọng | O(n) |
| Tồn tại khóa chính xác | HashSet | O(n) kỳ vọng | **O(1)** kỳ vọng | O(n) |
| Đếm giá trị thuộc [L,R] | Sắp xếp + lower/upper bound | O(n log n) | **O(log n)** | O(n) nếu giữ bản sao |
| Min/max trên đoạn | Sparse table | O(n log n) | **O(1)** | O(n log n) |
| Tổng hình chữ nhật R×C | Prefix sum 2D | O(RC) | **O(1)** | O(RC) |
| Nhiều truy vấn theo hạng, có trùng | Mảng sắp xếp + binary search | O(n log n) | O(log n) | Theo cách lưu |
| Nhiều truy vấn trên cây tĩnh | DFS + bảng depth/tin/tout, LCA nếu cần | Tùy kỹ thuật | Tùy kỹ thuật | Tùy kỹ thuật |

Đối với **prefix XOR**, sử dụng P[i+1] = P[i] XOR a[i] rồi trả P[r] XOR P[l] vì phép XOR tự triệt tiêu: x XOR x = 0. Với **prefix count** của điều kiện cố định (ví dụ a[i] là số chẵn), đặt P[i+1] = P[i] + (a[i] chẵn ? 1 : 0), sau đó đếm chẵn trong [l,r) bằng P[r]−P[l].

Các bảng trên mô tả trường hợp điển hình; phải đọc rõ điều kiện truy vấn trước khi chọn. Nếu cần đếm số **giá trị phân biệt** trên nhiều đoạn [l,r), chỉ có tổng tiền tố, mảng đã sắp hoặc HashMap toàn cục **không đủ** để trả lời O(1); bài toán này có các kỹ thuật riêng như Mo's algorithm (offline), persistent segment tree hoặc cấu trúc khác tùy ràng buộc.

## 9. Khi truy vấn xen kẽ cập nhật: chọn cấu trúc động

Một lỗi rất phổ biến là thấy prefix sum O(1) rồi dùng nó cho bài có lệnh UPDATE giữa các lệnh QUERY mà không xét cách sửa cấu trúc.

| Yêu cầu | Cấu trúc cân nhắc | Xây | Truy vấn | Cập nhật |
| --- | --- | --- | --- | --- |
| Tổng đoạn, không có cập nhật | Prefix sum | O(n) | O(1) | Không hỗ trợ hiệu quả |
| Tổng đoạn, sửa một giá trị | Fenwick tree | O(n) nếu xây tuyến tính; cũng có cách O(n log n) | O(log n) | O(log n) |
| Tổng/min/max đoạn, sửa một giá trị | Segment tree | O(n) | O(log n) | O(log n) |
| Cộng giá trị trên đoạn, hỏi tổng đoạn | Segment tree với lazy propagation | O(n) | O(log n) | O(log n) |
| Cộng giá trị trên nhiều đoạn rồi mới hỏi các điểm (offline) | Difference array | O(n) hoặc O(1) để chuẩn bị phần cần thiết | Khôi phục O(n) rồi lấy điểm O(1) | O(1) mỗi lần đánh dấu đoạn |

**Fenwick tree** đặc biệt gọn cho tổng tiền tố với cập nhật điểm; một truy vấn tổng [l,r) có thể lấy prefix(r) − prefix(l). Các phép trên Fenwick thường dùng chỉ số **1-based** bên trong, dù giao diện có thể 0-based.

**Segment tree** tổng quát hơn cho những phép gộp kết hợp như sum/min/max hoặc trạng thái nhiều trường; đổi lại cài đặt phức tạp hơn và cần thêm bộ nhớ O(n).

**Difference array** xử lý cập nhật cộng đoạn khi các update được thu thập **trước** khi cần kết quả cuối cùng. Nếu giữa các update lại liên tục hỏi tổng đoạn hoặc giá trị hiện thời, chỉ giữ difference array chưa khôi phục không trực tiếp đáp ứng mọi truy vấn O(1).

Một nguyên tắc dễ nhớ: **càng nhiều cập nhật xen kẽ, càng phải coi chi phí bảo trì là một phần của bài toán**, không chỉ xét thời gian trả lời sau tiền xử lý.

## 10. Tiền xử lý cho truy vấn trên đồ thị và cây

Chiến lược “xử lý trước, trả lời nhanh sau” không giới hạn ở mảng.

### Cây: depth, parent và LCA

Với **cây tĩnh**, một lượt DFS/BFS có thể tính:

- **depth[v]**: độ sâu nút v.
- **parent[v]**: cha trực tiếp.
- **tin/tout**: thời điểm vào/ra khi duyệt DFS để kiểm tra quan hệ tổ tiên theo một quy ước nhất quán.

Nếu có rất nhiều truy vấn hỏi **tổ tiên chung gần nhất (LCA)**, có thể xây bảng **binary lifting** up[k][v] biểu thị tổ tiên 2^k bước của v. Xây thường O(n log n), mỗi truy vấn LCA O(log n) sau tiền xử lý. Cấu trúc này dựa trên cây và gốc đã cố định; thay đổi cạnh hoặc đổi gốc có thể làm bảng cũ không còn phù hợp.

Với hai nút u,v trong cây không trọng số, khi biết LCA w, số cạnh trên đường đi giữa chúng là:

**dist(u,v) = depth[u] + depth[v] − 2×depth[w]**.

Đây là một dạng “biến đổi dữ liệu trước” để tránh duyệt đường đi cho mỗi truy vấn.

### Đồ thị: đường đi ngắn nhất

Nếu có nhiều truy vấn từ **cùng một nguồn s** đến nhiều đích:

- Đồ thị không trọng số: chạy **BFS từ s một lần**, lưu dist[v], mỗi truy vấn khoảng cách từ s đến v chỉ cần đọc dist[v] trong O(1).
- Đồ thị có trọng số **không âm**: có thể chạy Dijkstra một lần từ nguồn s (với cấu trúc phù hợp) rồi trả nhiều truy vấn về cùng nguồn bằng tra bảng.
- Nếu **nguồn thay đổi tùy truy vấn**, một BFS/Dijkstra từ s không giải được mọi nguồn. Có thể chạy riêng từng nguồn, tiền xử lý nhiều nguồn hoặc xét all-pairs shortest paths theo giới hạn n, số truy vấn và trọng số.

Không áp dụng Dijkstra chuẩn cho cạnh trọng số âm và không giả định mọi cấu trúc tiền xử lý khoảng cách phù hợp khi đồ thị cập nhật liên tục.

Ví dụ này cho thấy **mẫu truy vấn** quan trọng không kém số lượng truy vấn: nhiều đích **chung một nguồn** khác với nhiều cặp nguồn–đích bất kỳ.

## 11. Memoization, cache và tiền xử lý toàn bộ

Ba khái niệm gần nhau nhưng không giống hệt:

**Precomputation (tính sẵn):** chủ động tính một bảng kết quả hoặc tóm tắt cho các trường hợp đã biết sẽ hữu ích, trước khi nhận truy vấn.

**Memoization (ghi nhớ theo yêu cầu):** chỉ tính kết quả của một trạng thái khi lần đầu được hỏi, rồi lưu lại; lần tiếp theo cùng trạng thái tra từ cache.

**Caching (lưu kết quả truy cập):** có thể lưu kết quả của truy vấn đầy đủ hoặc một phần trung gian, thường cần chính sách hết hạn, giới hạn dung lượng và quy tắc vô hiệu hóa khi dữ liệu thay đổi.

Ví dụ ứng dụng có hàng triệu khóa có thể truy vấn nhưng thực tế chỉ một tập nhỏ được hỏi lặp đi lặp lại. Tính trước kết quả cho **mọi** khóa có thể tốn quá nhiều thời gian và bộ nhớ; memoization theo các khóa thực sự xuất hiện hợp lý hơn.

Ngược lại, nếu đầu vào là một mảng n phần tử và có q truy vấn tổng đoạn bất kỳ, prefix sum cần **O(n)** để bao phủ mọi đoạn bằng một cấu trúc gọn, thay vì cache riêng từng cặp (l,r), có thể lên đến **O(n²)** khóa.

Không đánh đồng “đã cache một vài kết quả” với “mọi truy vấn đều O(1)”. Truy vấn **chưa có trong cache** vẫn phải tính; cache cũng có chi phí tìm kiếm, cấp phát, eviction và invalidation.

## 12. Phân tích điểm hòa vốn và lựa chọn thực tế

Giả sử cần trả q truy vấn trên n phần tử. Nếu trực tiếp mỗi truy vấn có thể mất O(n), còn phương pháp tiền xử lý chi phí O(n) và trả O(1), tổng lần lượt là:

- Trực tiếp: **O(qn)**.
- Prefix sum: **O(n+q)**.

Với q lớn, ưu thế tiệm cận rất rõ. Nhưng với **q=1 và đoạn chỉ dài 2**, cộng trực tiếp hai giá trị mất một lượng công việc nhỏ, còn xây cả prefix sum phải duyệt n phần tử — tiền xử lý không có lợi.

### Ví dụ định lượng khái quát

Nếu n = 100.000 và có 20.000 truy vấn tổng đoạn dài trung bình 50.000 phần tử:

- Quét trực tiếp phải đọc cỡ **1.000.000.000 phần tử** qua các truy vấn, bỏ qua các tối ưu bộ nhớ đệm hay compiler.
- Prefix sum xây khoảng **100.000 tổng tích lũy** rồi mỗi truy vấn chỉ thực hiện hai lần đọc và một phép trừ.

Ví dụ này minh họa **số lượng phép xử lý trong mô hình**, không phải benchmark về thời gian máy thực. Kết quả chạy thực tế còn phụ thuộc cách tổ chức dữ liệu, CPU, GC, băng thông và môi trường.

Nếu lựa chọn là sắp xếp O(n log n) rồi tra cứu O(log n), số truy vấn phải đủ nhiều để bù chi phí sort. Với truy vấn tồn tại khóa chính xác, HashMap/HashSet có thể nhanh hơn trung bình; với truy vấn khoảng giá trị hoặc truy vấn thứ tự, sắp xếp có lợi thế về khả năng trả kết quả theo biên.

### Checklist trước khi tiền xử lý

1. **Truy vấn có lặp trên cùng phiên bản dữ liệu không?** Nếu mỗi truy vấn dùng dữ liệu khác, không thể dùng một chỉ mục chung.
2. **Truy vấn thật sự hỏi gì?** Tổng, XOR, min, số lần xuất hiện, phần tử thứ k, khoảng giá trị hay đường đi?
3. **Dữ liệu tĩnh hay có cập nhật?** Nếu động, cần tính cả chi phí sửa hoặc xây lại.
4. **n, q, U và dung lượng bộ nhớ?** Không chọn sparse table O(n log n) nếu RAM không đủ.
5. **Giữ chỉ số gốc không?** Sort thay đổi thứ tự; clone hoặc lưu ánh xạ khi cần.
6. **Quy ước đoạn và đầu ra?** [l,r) hay [l,r], có cho phép đoạn rỗng, giá trị trùng và chỉ số bắt đầu?
7. **Có tràn số không?** Tổng của nhiều phần tử int thường nên lưu bằng long.
8. **Dùng lại một cấu trúc hay nhiều chỉ mục?** Nếu workload hỗn hợp, có thể xây cả prefix sum và sparse table, nhưng phải tính tổng chi phí.
9. **Có kiểm thử đối chiếu với cách trực tiếp không?** Với n nhỏ, brute force là chuẩn tham chiếu tốt để phát hiện lỗi biên.
10. **Khi nào cấu trúc hết hiệu lực?** Phải có quy tắc xây lại hoặc cập nhật rõ ràng.

## 13. Những lỗi thường gặp

- **Chỉ nhìn thời gian O(1) của truy vấn mà bỏ qua thời gian O(n) hoặc O(n log n) để xây.**
- **Dùng prefix sum cũ sau khi sửa dữ liệu.** Câu trả lời có thể sai mà chương trình không báo lỗi.
- **Nhầm [l,r) với [l,r].** Sai một phần tử ở r hoặc đọc vượt a[n].
- **Khởi tạo prefix có n phần tử thay vì n+1.** Khó biểu diễn đoạn bắt đầu từ 0 và đoạn rỗng một cách nhất quán.
- **Dùng int để chứa tổng có thể lớn.** Tổng của nhiều số int có thể vượt miền int.
- **Áp dụng hai khối sparse table chồng lặp cho phép cộng.** Phần giao bị cộng hai lần, vì sum không idempotent.
- **Dùng sorted array để trả chỉ số gốc mà không lưu ánh xạ.** Chỉ số sau sort không còn là chỉ số nguồn.
- **Quên khóa trùng.** countEqual phải dùng đúng upperBound−lowerBound, không phải boolean tồn tại.
- **Sử dụng HashSet khi cần số lần xuất hiện.** HashSet chỉ lưu khóa phân biệt, không lưu tần suất.
- **Tuyên bố HashMap luôn O(1) trong trường hợp xấu nhất.** Độ phức tạp kỳ vọng phụ thuộc đặc tính hash và cài đặt.
- **Cập nhật điểm trong prefix sum bằng cách sửa một ô P[i].** Thực tế nhiều giá trị prefix phía sau cũng thay đổi.
- **Không xét giới hạn O(n log n) bộ nhớ của sparse table.** Với n rất lớn, bộ nhớ có thể vượt giới hạn.
- **Nhầm số hàng/cột trong 2D prefix sum.** Dùng [r1,r2)×[c1,c2) và công thức bao hàm–loại trừ đồng nhất.
- **Không xử lý hình chữ nhật rỗng, ma trận có hàng không cùng độ dài hoặc chỉ số ngoài biên.**
- **Cache không có chiến lược invalidation.** Kết quả cũ tiếp tục được sử dụng sau khi dữ liệu hoặc quy tắc truy vấn đổi.
- **Tính sẵn quá nhiều trạng thái chưa chắc được hỏi.** Một chiến lược lazy/memoized có thể tiết kiệm hơn.
- **Dùng một BFS cho mọi cặp nguồn–đích.** Bảng khoảng cách từ một nguồn chỉ trả câu hỏi bắt đầu từ chính nguồn đó.

## 14. Bài tập và câu hỏi tự kiểm tra

**Câu 1.** Với a = [5,1,4,1,7,3], tổng [2,5) bằng bao nhiêu?  
**Đáp án:** 4+1+7 = **12**. Với prefix P=[0,5,6,10,11,18,21], tính P[5]−P[2]=18−6=12.

**Câu 2.** Với cùng dãy, sau khi sắp tăng thành [1,1,3,4,5,7], bao nhiêu giá trị thuộc [2,6]?  
**Đáp án:** Có **3** giá trị: 3,4,5. Tính upperBound(6)−lowerBound(2) = 5−2 = 3.

**Câu 3.** Muốn trả nhiều truy vấn minimum trên mảng không thay đổi trong O(1) sau tiền xử lý, cấu trúc nào phù hợp?  
**Đáp án:** **Sparse table** với phép min, xây O(n log n) và lưu O(n log n).

**Câu 4.** Có được dùng hai đoạn sparse table chồng lặp để tính tổng không?  
**Đáp án:** Không; phần tử thuộc giao hai đoạn sẽ bị cộng hai lần. Tổng đoạn tĩnh nên dùng **prefix sum**, hoặc cơ chế phân hoạch đoạn không chồng lặp nếu cần.

**Câu 5.** Nếu một phần tử đổi giá trị sau khi đã xây prefix sum, các truy vấn có còn đúng không?  
**Đáp án:** Không chắc. Phải cập nhật đầy đủ bảng tiền tố, xây lại hoặc dùng Fenwick/segment tree hỗ trợ cập nhật.

**Câu 6.** Ma trận [[1,2,3],[4,5,6],[7,8,9]], tổng hàng [0,2) và cột [1,3) là gì?  
**Đáp án:** **16** = 2+3+5+6.

**Câu 7.** Vì sao không nên xây prefix sum cho một truy vấn duy nhất có độ dài 2 trên một mảng rất lớn?  
**Đáp án:** Truy vấn trực tiếp chỉ cần cộng 2 phần tử, trong khi tiền xử lý duyệt cả n phần tử và chiếm thêm O(n) bộ nhớ.

**Câu 8.** Có 10.000 truy vấn khoảng cách từ cùng nút s trong đồ thị không trọng số. Cách nào hợp lý?  
**Đáp án:** Chạy **BFS từ s một lần** rồi lưu dist[]; các truy vấn s→v chỉ cần đọc dist[v]. Nếu đồ thị thay đổi hoặc nguồn truy vấn thay đổi, phải đánh giá lại.

**Câu 9.** Muốn tìm số phần tử thỏa một điều kiện cố định trong nhiều đoạn [l,r) thì cấu trúc đơn giản là gì?  
**Đáp án:** Tạo mảng **prefix count** đếm số phần tử thỏa điều kiện đến mỗi vị trí; trả P[r]−P[l] trong O(1).

**Câu 10.** Một bảng hash lưu số lần xuất hiện của từng giá trị có trả lời O(1) kỳ vọng câu hỏi “bao nhiêu số thuộc [L,R]” với L,R tùy ý không?  
**Đáp án:** Không trực tiếp; hash không duy trì thứ tự để cộng nhanh theo khoảng giá trị. Có thể cân nhắc sorted array + two bounds hoặc cấu trúc có thứ tự phù hợp.

## 15. Ghi nhớ

**Tiền xử lý một lần cho nhiều truy vấn** đổi **thời gian và bộ nhớ chuẩn bị** lấy **thời gian trả lời truy vấn thấp hơn**. Thành công phụ thuộc vào việc nhận ra **dạng câu hỏi lặp lại**:

- Tổng đoạn tĩnh → **prefix sum**, O(n) xây, O(1) truy vấn.
- Đếm khóa/đếm trong khoảng giá trị → **hash tần suất** hoặc **sort + binary search**, tùy cần thứ tự.
- Min/max đoạn tĩnh → **sparse table**, O(n log n) xây, O(1) truy vấn.
- Tổng hình chữ nhật → **prefix sum 2D**, O(RC) xây, O(1) truy vấn.
- Truy vấn xen kẽ cập nhật → **Fenwick tree, segment tree** hoặc cấu trúc động thích hợp.
- Cùng nguồn trong đồ thị hoặc nhiều truy vấn trên cây tĩnh → **BFS/DFS và bảng tổ tiên/khoảng cách** một lần theo đúng phạm vi truy vấn.

**Điểm quyết định:** đánh giá **B(n)+qQ(n)+UA(n)** trên toàn workload, không chỉ nhìn Big-O của một truy vấn; đồng thời phải giữ đúng quy ước đoạn, bản gốc dữ liệu và tính hợp lệ của cấu trúc khi có cập nhật.