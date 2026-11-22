# Thuật toán Las Vegas và thuật toán Monte Carlo

**Chủ đề:** Computer Science Algorithms · Ngẫu nhiên hóa

## 1. Giới thiệu

Thuật toán ngẫu nhiên hóa (randomized algorithm) sử dụng những lựa chọn ngẫu nhiên trong quá trình chạy: chọn pivot, lấy mẫu hoặc kiểm tra bằng một vector sinh ngẫu nhiên. Cùng một đầu vào có thể dẫn tới đường chạy và thời gian khác nhau, đôi khi cả kết quả khác nhau.

Có hai mô hình quan trọng:

- **Las Vegas:** nếu thuật toán trả một đáp án, đáp án **luôn đúng** bất kể các bit ngẫu nhiên. Số bước, thời gian hoặc số lần phải thử có thể phụ thuộc ngẫu nhiên.
- **Monte Carlo:** thuật toán có một ngân sách tính toán đã xác định theo kích thước đầu vào và số lượt lấy mẫu, nhưng có **xác suất trả đáp án sai**. Xác suất đó phải được phát biểu và chứng minh rõ ràng.

Ví dụ Las Vegas: randomized Quicksort, dùng pivot ngẫu nhiên nhưng **luôn sắp xếp đúng**. Ví dụ Monte Carlo: Freivalds kiểm tra AB=C bằng vector ngẫu nhiên. Nếu AB≠C, một lần kiểm tra **có thể chấp nhận nhầm**, nhưng xác suất sai có cận lý thuyết.

Điểm khác biệt cốt lõi là **bảo đảm tính đúng của kết quả**, không phải việc có hay không gọi Random. Một số thuật toán Las Vegas như randomized Quicksort có cả cận thời gian xấu nhất hữu hạn; không nên mô tả Las Vegas là “luôn chạy không giới hạn”.

## 2. Bảng đối chiếu

| Khía cạnh | Las Vegas | Monte Carlo |
|---|---|---|
| Tính đúng khi trả đáp án | Bảo đảm đúng | Có thể sai với xác suất được chặn |
| Đại lượng phân tích | Thời gian/số lần thử kỳ vọng và đuôi phân phối | Xác suất lỗi và chi phí theo số lần thử |
| Random ảnh hưởng | Đường chạy, số bước; đôi khi chọn một trong nhiều đáp án đều đúng | Có thể ảnh hưởng chính đáp án đúng/sai |
| Nếu bốc trúng lựa chọn xấu | Chậm hơn hoặc thử lại, không trả kết quả sai | Có thể trả đáp án sai |
| Ví dụ | Quicksort ngẫu nhiên, Quickselect ngẫu nhiên | Freivalds, kiểm tra đồng nhất đa thức, lấy mẫu xấp xỉ |
| Cách tăng độ tin cậy | Dựa vào chứng minh và bộ kiểm chứng kết quả | Lặp độc lập, gộp kết quả theo quy tắc được chứng minh |

**Bảo đảm Las Vegas:** với đầu vào cố định x và bất cứ chuỗi random hợp lệ R nào, nếu A(x;R) trả đáp án thì đáp án đúng.

**Bảo đảm Monte Carlo:** với mỗi x, xác suất theo việc chọn R để A(x;R) sai không vượt một cận \(\delta\):

\[
\forall x:\quad \Pr_R[A(x;R)\text{ sai}]\le\delta.
\]

Đây là cận **trên mỗi đầu vào cố định**, không phải “99% dữ liệu trong một tập test cho kết quả đúng”. Thống kê thực nghiệm hữu ích nhưng không thay cho chứng minh cận lỗi.

## 3. Zero-error, one-sided và two-sided error

**Zero-error:** không có câu trả lời sai. Thuật toán có thể cần lâu mới trả lời. Nếu có deadline, trạng thái UNKNOWN/TIMEOUT phải phân biệt với YES/NO; trả “không biết” không phải trả đáp án sai.

**One-sided error:** chỉ một loại câu trả lời có thể sai. Freivalds có tính chất:
- AB=C đúng ⇒ mọi vector ngẫu nhiên đều thỏa A(Br)=Cr ⇒ luôn trả true.
- AB≠C ⇒ có thể không tìm được sai khác sau số lượt hữu hạn ⇒ đôi khi trả true nhầm.
- Nếu đã có một vector khiến A(Br)≠Cr ⇒ chắc chắn AB≠C, nên trả false không sai.

Vậy lỗi của Freivalds là **false positive**, không phải false negative, trong mô hình số học chính xác.

**Two-sided error:** cả YES và NO đều có thể sai trên những đầu vào khác nhau. Muốn giảm lỗi thường dùng lấy mẫu/lặp lại và một quy tắc đa số phiếu phù hợp với chứng minh. Không tự áp dụng cách đa số phiếu của thuật toán two-sided cho Freivalds.

## 4. Las Vegas: randomized Quicksort

Quicksort chia dãy quanh một pivot, rồi đệ quy hai phía. Nếu pivot luôn là phần tử đầu, các đầu vào tăng dần có thể gây phân hoạch lệch liên tục. Chọn pivot **ngẫu nhiên đều trong vùng đang xử lý** giúp có thời gian kỳ vọng tốt.

Để xử lý nhiều phần tử trùng, dùng **three-way partition** theo kiểu Dutch National Flag, chia:
- miền các phần tử **nhỏ hơn** pivot;
- miền các phần tử **bằng** pivot;
- miền các phần tử **lớn hơn** pivot.

Với con trỏ low,lt,i,gt,high, duy trì:

~~~text
[low .. lt-1]   < pivot
[lt .. i-1]     = pivot
[i .. gt]       chưa phân loại
[gt+1 .. high]  > pivot
~~~

Nếu a[i] nhỏ hơn pivot: đổi với a[lt], tăng lt và i. Nếu lớn hơn pivot: đổi với a[gt], giảm gt và **không tăng i** vì phần tử mới đổi tới chưa được kiểm tra. Nếu bằng: tăng i.

Sau mỗi vòng, số phần tử chưa phân loại giảm. Khi i>gt, mọi phần tử bằng pivot đã nằm đúng miền; hai miền ngoài được sắp xếp đệ quy. Chứng minh này đúng với **mọi pivot là một phần tử của đoạn hiện tại**, nên random không ảnh hưởng tính đúng.

### 4.1. Thời gian

Với pivot chọn đều và các khóa phân biệt, độ phức tạp kỳ vọng là:

\[
\mathbb E[T(n)]=O(n\log n).
\]

Với các khóa trùng nhau, three-way partition gom toàn bộ khóa bằng pivot ở một lượt, tránh worst-case do một dãy toàn phần tử giống nhau. Tuy vậy, trên các khóa phân biệt vẫn có chuỗi pivot rất lệch cho **worst-case O(n²)**.

Đây là cận **kỳ vọng theo random choices** cho một đầu vào đã cố định, không có nghĩa mỗi lần chạy đều O(n log n).

Bản Java luôn đệ quy phía nhỏ hơn và xử lý phía lớn hơn bằng while, giữ độ sâu stack **O(log(n+1))** trong trường hợp xấu nhất, ngoài chính mảng đầu vào. Mỗi lần phân hoạch loại ít nhất một phần tử bằng pivot, nên thuật toán luôn kết thúc.

### 4.2. Ví dụ

~~~text
Input: [9, 1, 7, 3, 3, -2, 0, 9]
Seed 17: [-2, 0, 1, 3, 3, 7, 9, 9]
Seed 29: [-2, 0, 1, 3, 3, 7, 9, 9]
~~~

Hai đường chạy có thể khác, nhưng đáp án giống nhau. Với dãy [5,5,5,5], three-way partition gom cả bốn giá trị bằng pivot; với dãy rỗng, kết quả vẫn rỗng.

**Randomized Quickselect** cũng là Las Vegas: pivot ngẫu nhiên giúp thời gian tìm phần tử thứ k có kỳ vọng O(n), nhưng phần tử trả về vẫn phải đúng và worst-case vẫn có thể O(n²).

## 5. Monte Carlo: thuật toán Freivalds

Cho ma trận nguyên vuông A,B,C kích thước n×n. Ta muốn kiểm tra:

\[
AB=C\;?
\]

Nhân ma trận trực tiếp mất O(n³) phép toán số học. Freivalds chọn vector nhị phân ngẫu nhiên \(r\in\{0,1\}^n\) và so:

\[
\boxed{A(Br)\stackrel{?}{=}Cr}.
\]

Một lượt làm:
1. Chọn mỗi r[j] độc lập, bằng 0 hoặc 1 với xác suất 1/2.
2. Tính u=Br.
3. Tính v=Au.
4. Tính w=Cr.
5. Nếu v khác w: trả **false** ngay, chứng minh AB≠C.
6. Nếu v bằng w: lượt này **chưa phát hiện** lỗi. Nếu còn lượt, lấy vector mới; chỉ trả true khi mọi lượt đều qua.

Ba phép nhân ma trận-vector cần **O(n²)** phép toán mỗi lượt; t lượt cần **O(tn²)**. Có thể kết thúc sớm khi phát hiện sai khác.

### 5.1. Tại sao đúng một phía?

Nếu AB=C, tính kết hợp cho:

\[
A(Br)=(AB)r=Cr
\]

với **mọi** r, nên không có false negative.

Nếu AB≠C, đặt D=AB−C≠0. Khi đó một lượt chấp nhận nhầm khi Dr=0.

Chọn một hàng i của D có ít nhất một hệ số khác 0, và cột j sao cho D[i][j]≠0. Giữ cố định tất cả bit r[k] với k≠j. Phương trình:

\[
D[i][j]r[j]+\sum_{k\ne j}D[i][k]r[k]=0
\]

có **nhiều nhất một** nghiệm r[j] trong {0,1}. Vì r[j] được rút đồng xác suất, khả năng hàng i bằng 0 không quá 1/2; việc Dr=0 còn đòi các hàng khác bằng 0 nên càng không thể có xác suất lớn hơn.

Do đó:

\[
\boxed{\Pr[\text{một lượt chấp nhận nhầm}\mid AB\ne C]\le1/2}.
\]

Đây là bảo đảm toán học cho mọi ma trận sai cố định dưới giả thiết bit r độc lập và đều; không phải một tỷ lệ được ước lượng bằng vài lần chạy test.

## 6. Một false positive thực sự ở ma trận 2×2

Xét:

\[
A=\begin{pmatrix}1&2\\3&4\end{pmatrix},
\quad B=\begin{pmatrix}5&6\\7&8\end{pmatrix}.
\]

Tích đúng:

\[
AB=\begin{pmatrix}19&22\\43&50\end{pmatrix}.
\]

Cho ứng viên đúng C=AB và ứng viên sai:

\[
C_{\mathrm{bad}}=\begin{pmatrix}20&22\\43&50\end{pmatrix}.
\]

Hiệu:

\[
D=AB-C_{\mathrm{bad}}=\begin{pmatrix}-1&0\\0&0\end{pmatrix}.
\]

Với r=(r0,r1), ta có Dr=(−r0,0). Lượt kiểm tra **chấp nhận nhầm** đúng khi r0=0:
- r=(0,0) hoặc (0,1): chấp nhận nhầm.
- r=(1,0) hoặc (1,1): phát hiện sai khác.

Tỷ lệ là **2/4=1/2**, đạt đúng cận trên của định lý.

Với r=(1,0):

~~~text
B*r        = (5,7)
A*(B*r)    = (19,43)
Cbad*r     = (20,43)
=> phát hiện tích sai
~~~

Nhưng với r=(0,0), cả hai vế đều bằng vector 0, nên Freivalds **trả true sai**. Vector toàn 0 là một kết quả rút thăm hợp lệ, không phải ngoại lệ mà code được phép xóa bỏ sau khi đã dùng chứng minh xác suất trên không gian vector ban đầu.

Trong chương trình Java 17:
- Random(4472026L) sinh r=(0,0) ở lượt đầu. Với t=1, Cbad được chấp nhận nhầm.
- Nếu tiếp tục **16 lượt** trên cùng một luồng random, có lượt r0=1 nên Cbad bị phát hiện.
- Random(7L) phát hiện Cbad ngay lượt đầu.

Seed cố định cho ví dụ giúp tái lập đường chạy; nó **không** phải nền tảng của chứng minh xác suất.

## 7. Giảm xác suất lỗi bằng lặp độc lập

Với ma trận sai, mỗi lượt Freivalds có xác suất chấp nhận nhầm không quá 1/2. Nếu t vector được sinh **độc lập**, và chỉ chấp nhận khi **tất cả** lượt qua, thì:

\[
\boxed{\Pr[\text{false positive sau t lượt}]\le(1/2)^t=2^{-t}}.
\]

| t | Cận lỗi |
|---:|---:|
| 1 | 1/2 |
| 2 | 1/4 |
| 5 | 1/32 |
| 10 | 1/1024 |
| 16 | 1/65536 |
| 20 | 1/1048576 |
| 30 | 1/1073741824 |

Muốn cận lỗi nhỏ hơn hay bằng \(\delta\), chọn t≥ceil(log₂(1/δ)). Khi tăng t, thời gian kiểm tra tăng theo O(tn²) nhưng cận lỗi giảm theo lũy thừa.

**Không sinh lại đúng cùng một vector t lần.** Nếu r đầu không phát hiện lỗi, mọi bản sao cũng không phát hiện. Lặp như vậy **không** tạo ra cận 2^-t.

**Không đổi sang quy tắc đa số phiếu** rồi dùng nguyên cận Freivalds: chứng minh 2^-t phụ thuộc quy tắc “mọi lượt đều phải qua”.

### 7.1. Nhiều truy vấn và union bound

Nếu có N bài kiểm chứng riêng, mỗi bài sai có cận lỗi 2^-t, xác suất **ít nhất một lỗi trong cả lô** được chặn bởi:

\[
\Pr[\text{có lỗi trong lô}]\le N2^{-t}.
\]

Đây là union bound, không đòi các truy vấn độc lập để cộng cận. Vì vậy số lượt t cần được chọn theo **độ tin cậy của toàn hệ thống**, không chỉ theo một phép thử riêng lẻ.

### 7.2. Giả ngẫu nhiên trong Java

Java util.Random là bộ sinh **giả ngẫu nhiên theo seed**: nếu seed đã biết, toàn bộ chuỗi nextBoolean xác định. Nó tốt để minh họa và kiểm thử tái lập; không phải nguồn ngẫu nhiên mật mã và không tự bảo đảm phân phối lý tưởng đối với một đối thủ nhìn thấy/điều khiển seed.

Cận Freivalds \(2^{-t}\) là định lý trong mô hình vector được rút đều và độc lập. Với ứng dụng có đối thủ chủ động, cần xem lại **mô hình đe dọa, cách giữ bí mật hoặc chọn random và quyền kiểm soát seed**. Một nguồn như SecureRandom có thể thích hợp hơn cho mục đích chống dự đoán, dù vẫn phải thiết kế đúng các lượt lấy mẫu.

Không được khởi tạo new Random cùng seed **bên trong mỗi vòng**, vì sẽ lặp vector đầu tiên thay vì tiếp tục chuỗi.

## 8. Khi áp dụng giới hạn thời gian hoặc bộ kiểm chứng

Một Las Vegas có thể chạy lại cho đến khi có lời giải thỏa một **bộ kiểm chứng chính xác**. Nếu hết ngân sách:
- Trả UNKNOWN/TIMEOUT: không đưa ra đáp án sai, nhưng chưa giải xong.
- Trả lời giải đã được chứng nhận đúng: giữ zero-error.
- Đoán một đáp án để kịp deadline: **mất bảo đảm zero-error**; phải phân tích xác suất sai của cách đoán.

Với thời gian T không âm và kỳ vọng hữu hạn, bất đẳng thức Markov:

\[
\Pr[T\ge k\mathbb E T]\le 1/k
\]

(với k>1) cho cận thô về xác suất vượt ngân sách, **không** trực tiếp là xác suất sai nếu thuật toán trả TIMEOUT thay vì đoán.

Có thể chuyển một kiểu “đề xuất ngẫu nhiên + kiểm chứng tất định” thành Las Vegas bằng cách chỉ xuất lời giải sau khi bộ kiểm chứng chứng nhận. Ngược lại, một phép thử Monte Carlo chỉ cho “có vẻ đúng” chưa đủ để chứng nhận tuyệt đối khi chứng minh vẫn cho xác suất false positive khác 0.

## 9. Monte Carlo quyết định và Monte Carlo ước lượng

Freivalds là **thuật toán quyết định** có one-sided error: nó trả boolean. Không phải mọi Monte Carlo đều trả boolean.

Trong **ước lượng theo mẫu**, ta có thể ước lượng một xác suất p bằng \(\hat p=(X_1+\dots+X_t)/t\), với các biến Bernoulli độc lập có kỳ vọng p. Khi đó cần định nghĩa thành công bằng **sai số tối đa \(\epsilon\)**, chứ không yêu cầu \(\hat p\) trùng chính xác một số thực.

Ví dụ bất đẳng thức Hoeffding:

\[
\Pr[|\hat p-p|\ge\epsilon]\le2e^{-2t\epsilon^2}.
\]

Công thức phụ thuộc giả thiết độc lập/miền giá trị của mẫu. Không được áp dụng nguyên xi cho mẫu tương quan hoặc bị chọn thiên lệch.

Việc chọn số lượt luôn cần gắn với: loại bài toán, mô hình lỗi, phân phối ngẫu nhiên và ngân sách tính toán.

## 10. Java 17 hoàn chỉnh

Lưu file **RandomizedAlgorithmsDemo.java**. Code gồm:
- Randomized Quicksort three-way: luôn đúng, thời gian chịu ảnh hưởng random pivot.
- Freivalds trên ma trận vuông long với phép toán trung gian **BigInteger** để tránh overflow.
- Oracle nhân ma trận chính xác O(n³) để kiểm chứng ví dụ nhỏ.
- Kiểm tra lỗi ma trận rỗng, ma trận không vuông và số lượt t≤0.
- Seed minh họa một lần Monte Carlo false positive và cách nhiều lượt phát hiện.

~~~java
import java.math.BigInteger;
import java.util.Arrays;
import java.util.Objects;
import java.util.Random;

public final class RandomizedAlgorithmsDemo {
    private RandomizedAlgorithmsDemo() {
    }

    // LAS VEGAS: randomized 3-way Quicksort

    private static void swap(int[] a, int i, int j) {
        int temp = a[i];
        a[i] = a[j];
        a[j] = temp;
    }

    public static void randomizedQuickSort(int[] a, Random rng) {
        Objects.requireNonNull(a, "array");
        Objects.requireNonNull(rng, "rng");
        quickSort(a, 0, a.length - 1, rng);
    }

    private static void quickSort(
            int[] a, int low, int high, Random rng) {
        while (low < high) {
            int pivot = a[low + rng.nextInt(high - low + 1)];
            int lt = low;
            int i = low;
            int gt = high;

            // [low,lt) < pivot, [lt,i) = pivot,
            // [i,gt] unknown, (gt,high] > pivot.
            while (i <= gt) {
                if (a[i] < pivot) {
                    swap(a, lt, i);
                    lt++;
                    i++;
                } else if (a[i] > pivot) {
                    swap(a, i, gt);
                    gt--;
                } else {
                    i++;
                }
            }

            // De quy nhanh nho; xu ly nhanh lon qua while.
            if (lt - low < high - gt) {
                quickSort(a, low, lt - 1, rng);
                low = gt + 1;
            } else {
                quickSort(a, gt + 1, high, rng);
                high = lt - 1;
            }
        }
    }

    // MONTE CARLO: Freivalds test of A*B == C.

    private static int squareSize(long[][] matrix, String name) {
        if (matrix == null || matrix.length == 0) {
            throw new IllegalArgumentException(
                    name + " must be nonempty");
        }
        int n = matrix.length;
        for (long[] row : matrix) {
            if (row == null || row.length != n) {
                throw new IllegalArgumentException(
                        name + " must be square");
            }
        }
        return n;
    }

    private static int sameSize(
            long[][] a, long[][] b, long[][] c) {
        int n = squareSize(a, "A");
        if (squareSize(b, "B") != n
                || squareSize(c, "C") != n) {
            throw new IllegalArgumentException(
                    "Matrices must have the same size");
        }
        return n;
    }

    private static BigInteger[] matrixVector(
            long[][] matrix, BigInteger[] vector) {
        int n = matrix.length;
        BigInteger[] result = new BigInteger[n];

        for (int i = 0; i < n; i++) {
            BigInteger sum = BigInteger.ZERO;
            for (int j = 0; j < n; j++) {
                sum = sum.add(
                        BigInteger.valueOf(matrix[i][j])
                                .multiply(vector[j]));
            }
            result[i] = sum;
        }
        return result;
    }

    // True can be a false positive; false proves A*B != C.
    public static boolean freivalds(
            long[][] a, long[][] b, long[][] c,
            int rounds, Random rng) {
        int n = sameSize(a, b, c);
        if (rounds <= 0) {
            throw new IllegalArgumentException(
                    "rounds must be positive");
        }
        Objects.requireNonNull(rng, "rng");

        for (int trial = 0; trial < rounds; trial++) {
            BigInteger[] r = new BigInteger[n];
            for (int j = 0; j < n; j++) {
                r[j] = rng.nextBoolean()
                        ? BigInteger.ONE : BigInteger.ZERO;
            }
            BigInteger[] br = matrixVector(b, r);
            BigInteger[] left = matrixVector(a, br);
            BigInteger[] right = matrixVector(c, r);
            if (!Arrays.equals(left, right)) {
                return false;
            }
        }
        return true;
    }

    // Exact O(n^3) oracle, never called by freivalds.
    public static BigInteger[][] exactProduct(
            long[][] a, long[][] b) {
        int n = squareSize(a, "A");
        if (squareSize(b, "B") != n) {
            throw new IllegalArgumentException(
                    "Matrices must have the same size");
        }
        BigInteger[][] result = new BigInteger[n][n];
        for (int i = 0; i < n; i++) {
            for (int j = 0; j < n; j++) {
                BigInteger sum = BigInteger.ZERO;
                for (int k = 0; k < n; k++) {
                    sum = sum.add(
                            BigInteger.valueOf(a[i][k])
                                    .multiply(BigInteger.valueOf(
                                            b[k][j])));
                }
                result[i][j] = sum;
            }
        }
        return result;
    }

    public static boolean exactProductEquals(
            long[][] a, long[][] b, long[][] c) {
        int n = sameSize(a, b, c);
        BigInteger[][] expected = exactProduct(a, b);
        for (int i = 0; i < n; i++) {
            for (int j = 0; j < n; j++) {
                if (!expected[i][j].equals(
                        BigInteger.valueOf(c[i][j]))) {
                    return false;
                }
            }
        }
        return true;
    }

    public static void main(String[] args) {
        int[] source = {9, 1, 7, 3, 3, -2, 0, 9};
        int[] first = source.clone();
        int[] second = source.clone();
        randomizedQuickSort(first, new Random(17));
        randomizedQuickSort(second, new Random(29));

        System.out.println("Las Vegas seed 17: "
                + Arrays.toString(first));
        System.out.println("Las Vegas seed 29: "
                + Arrays.toString(second));
        System.out.println("Las Vegas outputs agree: "
                + Arrays.equals(first, second));

        int[] duplicates = {5, 5, 5, 5};
        randomizedQuickSort(duplicates, new Random(19));
        System.out.println("Las Vegas duplicates: "
                + Arrays.toString(duplicates));

        int[] empty = {};
        randomizedQuickSort(empty, new Random(23));
        System.out.println("Las Vegas empty: "
                + Arrays.toString(empty));

        long[][] a = {{1, 2}, {3, 4}};
        long[][] b = {{5, 6}, {7, 8}};
        long[][] good = {{19, 22}, {43, 50}};
        long[][] bad = {{20, 22}, {43, 50}};

        System.out.println("Exact product: "
                + Arrays.deepToString(exactProduct(a, b)));
        System.out.println("Exact correct: "
                + exactProductEquals(a, b, good));
        System.out.println("Exact incorrect: "
                + exactProductEquals(a, b, bad));

        System.out.println("Freivalds correct (16): "
                + freivalds(a, b, good,
                        16, new Random(4472026L)));
        System.out.println("Freivalds bad (1): "
                + freivalds(a, b, bad,
                        1, new Random(4472026L)));
        System.out.println("Freivalds bad (16): "
                + freivalds(a, b, bad,
                        16, new Random(4472026L)));
        System.out.println("Freivalds bad (seed 7): "
                + freivalds(a, b, bad,
                        16, new Random(7L)));

        boolean wrong = !exactProductEquals(a, b, bad);
        boolean accepted = freivalds(
                a, b, bad, 1, new Random(4472026L));
        System.out.println("False positive demonstrated: "
                + (wrong && accepted));
        System.out.println(
                "Error bound after 16 rounds: 1/65536");

        try {
            freivalds(a, b, good, 0, new Random(1));
            System.out.println("Reject zero rounds: false");
        } catch (IllegalArgumentException expected) {
            System.out.println("Reject zero rounds: true");
        }

        try {
            long[][] ragged = {{1, 2}, {3}};
            freivalds(ragged, b, good, 1, new Random(1));
            System.out.println("Reject ragged matrix: false");
        } catch (IllegalArgumentException expected) {
            System.out.println("Reject ragged matrix: true");
        }

        try {
            long[][] none = new long[0][0];
            freivalds(none, none, none, 1, new Random(1));
            System.out.println("Reject empty matrix: false");
        } catch (IllegalArgumentException expected) {
            System.out.println("Reject empty matrix: true");
        }
    }
}
~~~

### 10.1. Biên dịch và chạy

Với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 RandomizedAlgorithmsDemo.java
java RandomizedAlgorithmsDemo
~~~

**Stdout dự kiến với seed cố định trong mã:**

~~~text
Las Vegas seed 17: [-2, 0, 1, 3, 3, 7, 9, 9]
Las Vegas seed 29: [-2, 0, 1, 3, 3, 7, 9, 9]
Las Vegas outputs agree: true
Las Vegas duplicates: [5, 5, 5, 5]
Las Vegas empty: []
Exact product: [[19, 22], [43, 50]]
Exact correct: true
Exact incorrect: false
Freivalds correct (16): true
Freivalds bad (1): true
Freivalds bad (16): false
Freivalds bad (seed 7): false
False positive demonstrated: true
Error bound after 16 rounds: 1/65536
Reject zero rounds: true
Reject ragged matrix: true
Reject empty matrix: true
~~~

### 10.2. Giải thích điểm cốt yếu trong Java

**randomizedQuickSort:** chọn pivot bằng rng.nextInt trên số chỉ số hợp lệ, phân hoạch ba miền rồi đệ quy phía nhỏ. Nó luôn sắp mảng đúng; seed chỉ thay đổi quá trình. Không cần so kết quả với một chứng chỉ xác suất để tin mảng đã sort.

**freivalds:** chỉ gọi matrixVector với B*r, A*(B*r), C*r. Không nhân ma trận A*B đầy đủ. Trả false ngay nếu phát hiện sai khác, và true chỉ khi mọi lượt đều chấp nhận. Bảo đảm false không sai đòi phép toán số nguyên chính xác.

**exactProduct:** tính ma trận thật O(n³), tách riêng làm oracle cho ví dụ nhỏ; nếu dùng nó bên trong Freivalds thì đánh mất lợi thế O(tn²).

**BigInteger:** số hạng nhân/cộng có thể vượt long, dù từng phần tử đầu vào là long. Code dùng BigInteger cho các tích và tổng, nên không bị false negative do overflow số nguyên.

**Random và seed:** Random(4472026L) được tạo mới **ở các lần gọi minh họa riêng**, nhưng bên trong một lần gọi freivalds, các vector được rút **liên tiếp từ cùng một rng**. Việc đó khác lỗi tạo mới Random cùng seed bên trong từng trial.

**Điều kiện đầu vào:** ma trận phải vuông, không rỗng, cùng kích thước; rounds phải dương. Cần thỏa các điều kiện này trước khi công bố một kết quả có cận xác suất.

## 11. Kiểm thử độc lập

### 11.1. Oracle cho Las Vegas

Sinh mảng gồm số âm, dương, 0, phần tử lặp, mảng đã tăng dần, giảm dần, mảng rỗng và các giá trị nguyên cực trị. Với mỗi seed:
1. Sao chép mảng đầu vào.
2. Dùng Arrays.sort làm oracle.
3. Chạy randomizedQuickSort.
4. So mảng kết quả với oracle theo từng phần tử.
5. Kiểm tra độ dài và multiset phần tử không đổi.

Bảo đảm Las Vegas là kết quả luôn đúng, nên **chỉ một phản ví dụ sort sai** đủ bác bỏ tính đúng của cài đặt, không thể biện hộ là “xác suất hiếm”.

### 11.2. Oracle cho Monte Carlo

Với n nhỏ:
1. Sinh A,B nguyên nhỏ.
2. Tính AB bằng exactProduct BigInteger.
3. Tạo C=AB và một Cbad bằng cách sửa ít nhất một phần tử.
4. C đúng: freivalds phải **luôn trả true** với mọi seed và số lượt dương.
5. Cbad: một số lần freivalds trả true vẫn là false positive được cho phép; nhưng mỗi false phải tương ứng một sai khác thật.

Có thể **liệt kê hết 2^n vector** để đo chính xác tỉ lệ chấp nhận nhầm của một lượt đối với Cbad. Với n nhỏ, tỷ lệ không được vượt 1/2. Ví dụ D=[[-1,0],[0,0]] có hai vector được chấp nhận trong bốn vector nhị phân độ dài 2.

### 11.3. Phân biệt kiểm thử và chứng minh

Test ngẫu nhiên có seed chỉ kiểm chứng những đường chạy cụ thể. Cận sai số \(2^{-t}\) cần chứng minh từ cơ chế phân phối bit, không suy ra từ việc 16 lần thử trong một mẫu đều qua.

Khi thấy lỗi:
- Lưu đầu vào, seed, số vòng, vector liên quan.
- Rút gọn phản ví dụ nếu có thể.
- Thêm regression test không ngẫu nhiên.
- Kiểm tra overflow, điều kiện dừng và việc reset RNG.

## 12. Chọn chiến lược theo yêu cầu

| Nhu cầu | Hướng phù hợp |
|---|---|
| Tuyệt đối không trả đáp án sai | Tất định hoặc Las Vegas có bộ chứng nhận |
| Cần kết quả nhanh, chấp nhận xác suất lỗi nhỏ | Monte Carlo với cận lỗi và số lượt cụ thể |
| Sort mảng, muốn tránh đầu vào xấu cho pivot cố định | Randomized three-way Quicksort |
| Kiểm nhanh ma trận AB=C | Freivalds: O(tn²), one-sided error |
| Phải chứng minh chắc chắn AB=C | Nhân/kiểm chứng tất định chính xác |
| Nhiều truy vấn Monte Carlo | Tăng t theo union bound N2^-t |
| Có đối thủ chủ động xem seed | Xét nguồn random và mô hình đe dọa |
| Cần debug thuật toán ngẫu nhiên | Seed cố định, oracle nhỏ và regression tests |
| Hết thời gian nhưng không được sai | Trả TIMEOUT/UNKNOWN, không đoán |
| Ước lượng xác suất/giá trị liên tục | Phát biểu sai số epsilon và cận xác suất tương ứng |

## 13. Sai lầm phổ biến

1. Cho rằng hễ dùng Random thì là Monte Carlo.
2. Cho rằng Las Vegas luôn nhanh trong mọi lần chạy.
3. Nhầm O(n log n) kỳ vọng với worst-case O(n log n) của Quicksort.
4. Cho rằng random pivot có thể làm quicksort trả mảng sai một cách “hợp lệ”.
5. Không gom khóa bằng pivot, khiến dãy trùng lặp xử lý chậm.
6. Sau khi đổi với gt trong three-way partition lại tăng i, bỏ phần tử chưa xét.
7. Không giảm kích thước miền bài toán, tạo vòng lặp/đệ quy vô hạn.
8. Gọi mọi Monte Carlo là two-sided error, bỏ tính one-sided của Freivalds.
9. Nghĩ Freivalds true chứng minh AB=C tuyệt đối.
10. Nghĩ Freivalds false có thể sai khi AB=C trong số học chính xác.
11. Tính trực tiếp AB trong Freivalds rồi vẫn tuyên bố O(tn²).
12. So B(Ar) hoặc rA thay cho A(Br), Cr.
13. Nhân/cộng bằng long làm overflow rồi mới so vector.
14. Dùng rounds=0 và coi true là kết quả có độ tin cậy.
15. Quên kiểm tra ma trận vuông, cùng kích thước và không rỗng.
16. Lặp lại một vector t lần nhưng vẫn sử dụng cận lỗi 2^-t.
17. Reset Random cùng seed trong mỗi trial, khiến vector lặp.
18. Dùng majority vote mà không chứng minh lại xác suất lỗi.
19. Dùng Java Random cho ứng dụng đối kháng mà không phân tích seed.
20. Thấy một false positive rồi kết luận thuật toán Monte Carlo bị lỗi, dù được phép.
21. Lấy tỷ lệ đúng trên bộ test làm xác suất lỗi tối đa với mọi đầu vào.
22. Chạy nhiều lần cùng seed và coi đó là các lần thử thống kê độc lập.
23. Không dùng oracle độc lập khi kiểm thử.
24. Cho rằng sai số 1/65536 là 0 tuyệt đối.
25. Bỏ cận lỗi tổng cộng khi có hàng triệu phép kiểm.
26. Trả lời phỏng đoán sau TIMEOUT nhưng vẫn tuyên bố Las Vegas zero-error.
27. Không phân biệt fixed-seed reproducibility và chứng minh xác suất.
28. Áp dụng Hoeffding cho mẫu phụ thuộc mà không đủ giả thiết.
29. Không lưu seed/đầu vào khi phát hiện lỗi.
30. Không tính chi phí thực tế của phép nhân BigInteger khi phân tích hiệu năng.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Las Vegas khác Monte Carlo ở đâu?

**Đáp án:** Las Vegas trả đáp án luôn đúng; Monte Carlo có xác suất lỗi được phân tích, đổi lại có thể tiết kiệm tính toán.

**Câu 2.** Vì sao randomized Quicksort vẫn là Las Vegas khi pivot lựa chọn ngẫu nhiên?

**Đáp án:** Bất biến phân hoạch đúng với mọi pivot được chọn; random chỉ ảnh hưởng thời gian.

**Câu 3.** Thời gian kỳ vọng và worst-case của randomized Quicksort?

**Đáp án:** Kỳ vọng O(n log n), worst-case O(n²) trên khóa phân biệt.

**Câu 4.** Freivalds tính những vector nào?

**Đáp án:** Br, A(Br) và Cr.

**Câu 5.** Vì sao Freivalds không bác nhầm một tích đúng?

**Đáp án:** AB=C suy ra A(Br)=Cr với mọi r.

**Câu 6.** Freivalds có thể sai loại nào?

**Đáp án:** False positive: AB≠C nhưng kiểm tra không phát hiện.

**Câu 7.** Vì sao cận lỗi một lượt không quá 1/2?

**Đáp án:** Với D=AB−C khác 0, một hệ số D[i][j] khác 0 làm phương trình hàng i có nhiều nhất một lựa chọn bit r[j] phù hợp khi các bit khác cố định.

**Câu 8.** Cận lỗi sau t lượt độc lập?

**Đáp án:** 2^-t.

**Câu 9.** Với 16 lượt, cận lỗi là bao nhiêu?

**Đáp án:** 1/65536 cho một ma trận sai cố định trong mô hình bit rút độc lập đều.

**Câu 10.** Vì sao vector r toàn 0 dễ làm Freivalds chấp nhận nhầm?

**Đáp án:** Vì mọi ma trận nhân vector 0 đều được vector 0.

**Câu 11.** Có thể reset cùng seed giữa các lượt không?

**Đáp án:** Không nếu muốn các vector mới; reset sẽ lặp lại vector đầu tiên.

**Câu 12.** BigInteger cần để làm gì?

**Đáp án:** Tránh overflow khi nhân/cộng ma trận-vector trong số học nguyên.

**Câu 13.** Kết quả false của Freivalds có chứng minh AB≠C không?

**Đáp án:** Có, nếu các phép toán chính xác và dữ liệu không bị thay đổi trong lúc kiểm tra.

**Câu 14.** Hết thời gian trong Las Vegas nên làm gì nếu không được phép trả sai?

**Đáp án:** Trả UNKNOWN/TIMEOUT riêng hoặc chỉ trả lời giải đã kiểm chứng.

**Câu 15.** Nếu có N phép kiểm, cận có ít nhất một false positive là gì?

**Đáp án:** Không quá N2^-t theo union bound.

**Câu 16.** Có thể dùng tỷ lệ đúng của một seed để chứng minh bound 2^-t?

**Đáp án:** Không. Cần chứng minh phân phối và tính độc lập các bit.

**Câu 17.** Monte Carlo ước lượng khác Monte Carlo boolean ra sao?

**Đáp án:** Nó trả giá trị gần đúng; bảo đảm thường nói về xác suất vượt sai số epsilon, không phải độ bằng nhau tuyệt đối.

**Câu 18.** Làm sao kiểm thử hai thuật toán trong bài?

**Đáp án:** So Quicksort với Arrays.sort, so Freivalds với ma trận nhân chính xác BigInteger trên ví dụ nhỏ và liệt kê toàn bộ vector n nhỏ.

**Tóm tắt:** **Las Vegas** bảo đảm đáp án đúng dù thời gian phụ thuộc ngẫu nhiên; **Monte Carlo** có xác suất sai được chứng minh và giảm nhờ lặp độc lập. Randomized Quicksort đúng với mọi pivot, kỳ vọng O(n log n). Freivalds kiểm tra AB=C bằng A(Br)=Cr với O(tn²) phép toán và cận false positive \(2^{-t}\), nhưng **true không phải chứng nhận tuyệt đối**. Luôn phân biệt ngẫu nhiên lý tưởng với seed cố định, kết quả kiểm thử với định lý và số học chính xác với overflow.
