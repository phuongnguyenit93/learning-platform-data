# Các bài toán con độc lập và các bài toán con chồng lặp

## 1. Vì sao cần phân biệt hai kiểu bài toán con?

Khi giải một bài toán bằng đệ quy, ta thường gọi cùng một kiểu hàm trên các đầu vào nhỏ hơn. Mỗi lời gọi đó tương ứng với một **bài toán con (subproblem)**. Điều quan trọng là hai lời gọi ở các nhánh khác nhau có đang xử lý **hai trạng thái thật sự khác nhau**, hay đang yêu cầu tính lại **cùng một kết quả**.

- **Bài toán con độc lập theo phân rã:** các nhánh xử lý những phạm vi hoặc trạng thái khác nhau; trong cùng một lần thực hiện không giải lại cùng một bài toán con. Ví dụ điển hình là hai nửa chỉ số rời nhau của Merge sort.
- **Bài toán con chồng lặp (overlapping subproblems):** nhiều nhánh trong cây gọi dẫn tới cùng một trạng thái toán học. Nếu mỗi nhánh giải từ đầu, công việc sẽ lặp lại. Ví dụ điển hình là tính Fibonacci bằng đệ quy thuần túy.

Sự phân biệt này giúp lựa chọn cách tổ chức:

1. **Divide and conquer (chia để trị):** chia thành các phần, giải các phần và kết hợp. Khi các phần không trùng trạng thái, tính nhớ kết quả thường không giúp gì.
2. **Memoization (ghi nhớ):** giải từ trên xuống, lưu kết quả của từng trạng thái, tránh tính lại khi gặp trạng thái đó lần nữa.
3. **Tabulation (lập bảng):** giải các trạng thái theo thứ tự phụ thuộc từ nhỏ tới lớn.
4. **Rolling state (trạng thái cuốn chiếu):** chỉ giữ một vài kết quả gần đây khi công thức truy hồi cho phép, thay vì lưu cả bảng.

Các tên gọi này không phải ranh giới tuyệt đối. Một công thức có thể có bước **chia** đồng thời dẫn tới **chồng lặp** trên toàn cây tìm kiếm; lúc đó quy hoạch động có thể cải thiện đáng kể. Ngược lại, đệ quy có hai nhánh không có nghĩa là phải dùng memoization.

## 2. “Cùng bài toán con” nghĩa là cùng trạng thái nào?

Để nhận diện sự trùng lặp, trước hết xác định **bộ tham số đủ để quyết định kết quả**. Hai lời gọi chỉ được xem là cùng bài toán con khi chúng thực sự cần cùng một kết quả dưới cùng điều kiện dữ liệu.

| Bài toán | Trạng thái phù hợp | Khi nào hai lời gọi trùng nhau? |
| --- | --- | --- |
| Merge sort | Khoảng chỉ số [left, right) trên một mảng cố định | Cùng phạm vi cần sắp xếp trong cùng ngữ cảnh |
| Fibonacci | Số nguyên n | Cùng F(n) |
| Đếm đường đi trên lưới | Tọa độ (row, column), cùng bản đồ và đích | Cùng ô và cùng dữ liệu lưới |
| Knapsack 0/1 | (index, remainingCapacity), cùng danh sách vật phẩm | Cùng chỉ số vật phẩm tiếp theo và dung lượng còn lại |
| Bài toán trên đoạn | Cặp biên (l, r) và các điều kiện bổ sung | Cùng đoạn, cùng điều kiện và dữ liệu |
| Đếm cách đổi tiền | (coinIndex, remainingAmount) với tập tiền cố định | Cùng loại tiền được phép dùng và số tiền còn lại |

**Trùng giá trị chưa chắc là trùng trạng thái.** Hai đoạn [0, 3) và [5, 8) có thể cùng chứa dãy [2, 1, 3] nhưng chúng nằm ở hai vùng khác nhau. Khi sắp xếp trực tiếp trên mảng, hai phạm vi đó là hai nhiệm vụ khác nhau. Ngược lại, F(4) luôn có cùng kết quả trong cùng định nghĩa Fibonacci, bất kể nó được gọi từ F(5) hay F(6).

**Hai phép tính đọc dữ liệu giao nhau cũng chưa chắc là cùng bài toán con.** Tổng đoạn [0, 4) và tổng đoạn [2, 6) đọc chung một số phần tử nhưng trả về hai câu hỏi khác nhau. Có thể khai thác phần tính toán chia sẻ qua tổng tiền tố, song không thể lưu cả hai dưới một khóa chỉ vì chúng giao nhau.

Khi lưu cache, khóa phải chứa mọi thứ ảnh hưởng tới kết quả: chỉ số, dung lượng, target, giới hạn, phiên bản dữ liệu, trạng thái lựa chọn... Lưu sai khóa có thể cho đáp án sai dù chương trình chạy nhanh.

## 3. Merge sort: chia các phần không giao nhau

Merge sort sắp xếp một đoạn [left, right) bằng ba bước:

1. Tách tại mid = left + (right − left)/2, thành [left, mid) và [mid, right).
2. Gọi đệ quy sắp xếp từng nửa.
3. Trộn hai nửa đã có thứ tự để tạo đoạn tăng không giảm.

Với a = [8, 3, 5, 3, 9, 1]:

~~~text
                         [8, 3, 5, 3, 9, 1]
                         /               \
                    [8, 3, 5]           [3, 9, 1]
                    /      \            /      \
                  [8]     [3, 5]       [3]    [9, 1]
                          /   \                /   \
                        [3]   [5]            [9]   [1]

Trộn: [3, 5] và [1, 9]
      [3, 5, 8] và [1, 3, 9]
      [1, 3, 3, 5, 8, 9]
~~~

Nếu xét bằng chỉ số:

~~~text
[0, 6)
├─ [0, 3)
│  ├─ [0, 1)
│  └─ [1, 3)
│     ├─ [1, 2)
│     └─ [2, 3)
└─ [3, 6)
   ├─ [3, 4)
   └─ [4, 6)
      ├─ [4, 5)
      └─ [5, 6)
~~~

Các nửa con của mỗi nút rời nhau về chỉ số và phủ toàn bộ đoạn cha. Trong lần thực hiện Merge sort chuẩn, một khoảng con cụ thể không bị giải lại theo hai đường đệ quy khác nhau. **Không có trạng thái trùng cần memoize** chỉ vì cây có nhiều lời gọi.

Với n≥1, cây chia đôi tới đoạn một phần tử có n lá và mỗi nút trong có hai con, nên số nút/lời gọi là 2n−1. Ví dụ n=6 cho 11 lời gọi, tất cả các nút tương ứng các khoảng khác nhau. Nhưng số lời gọi Θ(n) **không phải** thời gian toàn thuật toán: mỗi nút còn phải trộn các phần tử.

### Độc lập không đồng nghĩa không cần phối hợp

Hai nửa có thể được giải độc lập về **kết quả con**, nhưng cần kết hợp bằng phép merge. Nếu triển khai song song, còn phải bảo đảm các nhánh không ghi cùng vùng bộ nhớ; tính độc lập về trạng thái toán học không tự chứng minh một chương trình đa luồng là an toàn.

Một triển khai đúng có thể dùng cùng mảng tạm nếu chỉ chạy tuần tự hoặc phân chia rõ các vùng ghi. Cần tách câu hỏi “có cùng trạng thái lặp lại không?” khỏi câu hỏi “hai nhánh có thể chạy đồng thời không?”.

## 4. Phân tích thời gian Merge sort: chi phí kết hợp

Với việc chia thành hai nửa gần bằng nhau và trộn n phần tử ở mỗi nút cha:

~~~text
T(n) = T(floor(n/2)) + T(ceil(n/2)) + Θ(n)
T(0) = T(1) = Θ(1)
~~~

Khi n là lũy thừa của 2:

~~~text
T(n) = 2T(n/2) + Θ(n)
     = Θ(n log n)
~~~

Cây đệ quy cao Θ(log n); ở mỗi tầng, tổng kích thước các đoạn cần trộn là O(n). Vì có nhiều tầng trộn, tổng chi phí Θ(n log n).

Phiên bản Java bên dưới tạo một bản sao của đầu vào và một mảng tạm dài n, nên bộ nhớ phụ **Θ(n)**, chưa kể stack đệ quy O(log n). Không được chỉ tính stack rồi kết luận thuật toán dùng O(log n) bộ nhớ.

Đây là ví dụ điển hình cho thấy **các bài toán con không chồng lặp vẫn có tổng chi phí lớn hơn O(n)** vì bước kết hợp ở mỗi tầng. Cách phân tích đúng là chi phí từng nhánh **cộng** chi phí kết hợp, chứ không chỉ đếm số nhánh.

## 5. Fibonacci: cùng trạng thái xuất hiện trên nhiều nhánh

Định nghĩa dãy Fibonacci:

~~~text
F(0) = 0
F(1) = 1
F(n) = F(n - 1) + F(n - 2), n >= 2
~~~

Đệ quy trực tiếp có dạng:

~~~java
static long naive(int n) {
    if (n < 2) {
        return n;
    }
    return naive(n - 1) + naive(n - 2);
}
~~~

Đây chỉ là phần lõi minh họa, **chưa tự xử lý n âm hoặc tràn long**. Phần chương trình hoàn chỉnh bên dưới sẽ có các ràng buộc này.

Với F(5), các lời gọi tạo ra cây:

~~~text
                          F(5)
                        /      \
                     F(4)      F(3)
                    /   \      /   \
                 F(3)  F(2)  F(2)  F(1)
                /   \  / \   / \
              F(2) F(1) F(1) F(0) F(1) F(0)
              / \
            F(1) F(0)
~~~

F(3) được tính hai lần; F(2) được tính ba lần. Lời gọi F(2) ở bất kỳ nhánh nào vẫn cần cùng kết quả F(2)=1. Khi tăng n, các bản sao của trạng thái F(k) xuất hiện ở nhiều vị trí trong cây gọi.

Đặt C(n) là số lần vào hàm đệ quy trực tiếp, **kể cả lời gọi ban đầu**:

~~~text
C(0) = C(1) = 1
C(n) = 1 + C(n-1) + C(n-2) khi n >= 2
~~~

Suy ra C(2)=3, C(3)=5, C(4)=9, C(5)=15, C(10)=177. Thời gian phát triển theo **Θ(φ^n)**, với φ=(1+√5)/2, trong khi số giá trị trạng thái khác nhau chỉ là n+1: F(0)...F(n). Độ sâu stack lớn nhất O(n).

Với F(10), **177 lời gọi** cùng tính toán các trạng thái từ một tập chỉ có **11 giá trị khác nhau**. Đây chính là lợi ích có thể thu được khi ghi nhớ kết quả: giảm số lần tính lại cùng một F(k), chứ không thay đổi công thức toán học của Fibonacci.

## 6. Từ cây lời gọi thành DAG trạng thái

Một cây đệ quy thường có **một nút cho mỗi lần gọi**, kể cả khi cùng tham số xuất hiện nhiều lần. Trong khi đó, **đồ thị phụ thuộc trạng thái (DAG)** có thể chỉ giữ **một đỉnh cho mỗi trạng thái duy nhất** và cạnh chỉ quan hệ phụ thuộc.

Ví dụ, F(5) cần F(4),F(3); F(4) cần F(3),F(2); F(3) cần F(2),F(1). Hai lần “cần F(3)” có thể trỏ đến **cùng một đỉnh F(3)**. Nếu đã biết giá trị, dùng lại thay vì giải một cây mới từ F(3).

Đối với Fibonacci, mọi cạnh đi từ n tới n−1 hoặc n−2, tức chỉ số giảm, nên đồ thị phụ thuộc **không có chu trình** và cuối cùng chạm trạng thái cơ sở 0 hoặc 1. Đây là cơ sở để memoization hoặc tabulation tính mỗi trạng thái một lần.

Không phải mọi bài toán đệ quy đều tự cho một DAG hữu hạn. Nếu trạng thái có thể phụ thuộc ngược tới chính nó mà chưa có cách xử lý chu trình, chỉ gắn một Map vào hàm đệ quy không đủ để bảo đảm chương trình kết thúc hay cho đáp án đúng.

Trong Merge sort, mỗi khoảng [l,r) trong một lần phân rã xuất hiện một lần; “gộp các nút trùng trạng thái” không làm cây nhỏ đi. Trong Fibonacci, nhiều nút của cây được gộp vào cùng đỉnh, giảm khối lượng công việc đáng kể.

## 7. Memoization: quy hoạch động từ trên xuống

**Memoization** giải theo nhu cầu:

1. Nhận yêu cầu tính trạng thái S.
2. Nếu có kết quả S trong cache, trả ngay.
3. Nếu chưa có, giải các trạng thái mà S phụ thuộc, tính kết quả, lưu rồi trả.

Với Fibonacci, cache có thể là mảng memo[n] vì trạng thái chỉ cần số nguyên n:

~~~text
solve(n):
    if n == 0: return 0
    if n == 1: return 1
    if memo[n] đã có: return memo[n]

    memo[n] = solve(n - 1) + solve(n - 2)
    return memo[n]
~~~

Bất biến quan trọng: khi memo[k] đánh dấu “đã tính”, nó phải lưu **đúng** F(k); mọi lần dùng lại trả đúng giá trị đó. Kết quả phải **xác định** theo khóa k. Nếu thay đổi dữ liệu đầu vào giữa các lượt hoặc hàm có hiệu ứng phụ, phải thiết kế lại khóa và chính sách hết hạn cache.

Với n≥2, mỗi F(k) được tính mới tối đa một lần. Có n+1 trạng thái khả dĩ, mỗi lần tính mới chỉ cộng hai giá trị, nên thời gian **Θ(n)**. Bảng nhớ dài n+1 dùng Θ(n) bộ nhớ; stack đệ quy sâu O(n); tổng bộ nhớ phụ Θ(n).

**Phân biệt số lượt vào hàm và số lần tính mới:** chương trình Java bên dưới đếm cả lượt gặp cache hit. Khi tính F(10), helper vẫn được gọi **19 lần**, nhưng chỉ **9 trạng thái không phải cơ sở**, F(2)...F(10), được tính mới. Hai trường hợp cơ sở F(0) và F(1) trả trực tiếp.

Nếu một kết quả hợp lệ có thể là −1, không được dùng −1 làm “chưa tính” mà không có biến đánh dấu riêng. Trong ví dụ Fibonacci, kết quả hợp lệ luôn không âm, nên mảng long điền −1 an toàn trong miền n được hỗ trợ.

### Khi cache không mang lại lợi ích

Nếu các trạng thái đều duy nhất trong lần thực thi, như các khoảng riêng của một lần Merge sort, cache không giảm số phép tính. Nó còn tạo chi phí phụ cho ghi/tra cứu và dùng bộ nhớ. Cũng không nên suy luận rằng **mọi thuật toán có trạng thái trùng đều thành O(n)**: cần đếm số trạng thái phân biệt và chi phí xử lý từng trạng thái.

## 8. Tabulation: quy hoạch động từ dưới lên

**Tabulation** xác định một thứ tự tính mà tại thời điểm tính S, mọi trạng thái S phụ thuộc đã có kết quả.

Với Fibonacci:

~~~text
dp[0] = 0
dp[1] = 1
for i = 2 .. n:
    dp[i] = dp[i-1] + dp[i-2]
return dp[n]
~~~

Có n+1 phần tử bảng, mỗi phần tử tính O(1), nên thời gian Θ(n), bộ nhớ Θ(n).

Nếu chỉ cần F(n), không cần lưu toàn bộ bảng: từ công thức, mỗi F(i) chỉ phụ thuộc F(i−1) và F(i−2). Ta có thể dùng hai biến:

~~~text
previous = 0
current  = 1

for i = 2 .. n:
    next = previous + current
    previous = current
    current = next

return current
~~~

Cách **rolling state** này giữ thời gian Θ(n) và giảm bộ nhớ phụ xuống **Θ(1)**. Đây là tối ưu hóa cách lưu trữ, **không có nghĩa công thức Fibonacci không còn chồng lặp**.

| Tiêu chí | Memoization (top-down) | Tabulation (bottom-up) |
| --- | --- | --- |
| Cách duyệt | Từ yêu cầu cuối, đi xuống các phụ thuộc | Từ trường hợp cơ sở tới trạng thái cần |
| Trạng thái được tính | Thường chỉ trạng thái thực sự được thăm | Thường tính một miền trạng thái theo thứ tự |
| Ngăn xếp | Có thể sâu, ví dụ O(n) ở Fibonacci | Thường không cần đệ quy |
| Tổ chức bộ nhớ | Cache theo khóa trạng thái | Bảng/rolling array theo thứ tự phụ thuộc |
| Điểm dễ sai | Khóa thiếu tham số, nhầm “chưa tính” | Sai thứ tự, ghi đè trạng thái còn cần |
| Độ phù hợp | Hình thức đệ quy tự nhiên, trạng thái thưa | Phụ thuộc rõ, miền dễ liệt kê |

Không có cách nào mặc định tốt hơn trong mọi bài toán. Khi nhiều trạng thái không bao giờ được thăm từ mục tiêu, top-down có thể tiết kiệm tính toán; khi cần hạn chế stack hoặc phụ thuộc theo lớp, bottom-up có thể thuận lợi hơn.

## 9. Ví dụ Java 17+ hoàn chỉnh

Chương trình độc lập sau gồm:

- Merge sort tạo **mảng mới**, hai lời gọi trên các đoạn **không giao nhau**, trộn từng đoạn bằng một mảng tạm chung trong thực thi tuần tự.
- Fibonacci đệ quy trực tiếp, đếm số lượt gọi.
- Fibonacci có memoization, đếm số lượt gọi helper và số trạng thái thực sự tính mới.
- Fibonacci bottom-up với **hai biến**.
- Giới hạn giá trị n để không tràn long; đầu vào âm gây IllegalArgumentException.

Lưu đúng tệp **IndependentVsOverlapping.java**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public final class IndependentVsOverlapping {
    private IndependentVsOverlapping() {}

    static final class Counter {
        long calls;
        long computed;
    }

    public static int[] mergeSort(int[] input) {
        Objects.requireNonNull(input, "input");
        int[] result = Arrays.copyOf(input, input.length);
        int[] scratch = new int[result.length];
        mergeSortRange(result, scratch, 0, result.length);
        return result;
    }

    // Sort the half-open range [left, right).
    private static void mergeSortRange(
            int[] data, int[] scratch, int left, int right) {
        if (right - left <= 1) {
            return;
        }

        int mid = left + (right - left) / 2;
        mergeSortRange(data, scratch, left, mid);
        mergeSortRange(data, scratch, mid, right);

        int i = left;
        int j = mid;
        int out = left;

        while (i < mid && j < right) {
            if (data[i] <= data[j]) {
                scratch[out++] = data[i++];
            } else {
                scratch[out++] = data[j++];
            }
        }
        while (i < mid) {
            scratch[out++] = data[i++];
        }
        while (j < right) {
            scratch[out++] = data[j++];
        }

        System.arraycopy(scratch, left, data, left, right - left);
    }

    // Intentionally naive. Do not use for large n.
    public static long fibNaive(int n, Counter stats) {
        Objects.requireNonNull(stats, "stats");
        if (n < 0 || n > 40) {
            throw new IllegalArgumentException("n outside [0, 40]");
        }

        stats.calls++;
        if (n < 2) {
            return n;
        }
        return fibNaive(n - 1, stats) + fibNaive(n - 2, stats);
    }

    // Top-down DP with a cache of non-base values.
    public static long fibMemo(int n, Counter stats) {
        Objects.requireNonNull(stats, "stats");
        if (n < 0 || n > 92) {
            throw new IllegalArgumentException("n outside [0, 92]");
        }

        long[] memo = new long[n + 1];
        Arrays.fill(memo, -1L);
        return fibMemoRecursive(n, memo, stats);
    }

    private static long fibMemoRecursive(
            int n, long[] memo, Counter stats) {
        stats.calls++;
        if (n < 2) {
            return n;
        }
        if (memo[n] != -1L) {
            return memo[n];
        }

        stats.computed++;
        memo[n] = fibMemoRecursive(n - 1, memo, stats)
                + fibMemoRecursive(n - 2, memo, stats);
        return memo[n];
    }

    // Bottom-up DP; no recursion and no DP array.
    public static long fibRolling(int n) {
        if (n < 0 || n > 92) {
            throw new IllegalArgumentException("n outside [0, 92]");
        }
        if (n < 2) {
            return n;
        }

        long previous = 0L;
        long current = 1L;
        for (int i = 2; i <= n; i++) {
            long next = previous + current;
            previous = current;
            current = next;
        }
        return current;
    }

    public static void main(String[] args) {
        int[] input = {8, 3, 5, 3, 9, 1};
        System.out.println("Input: " + Arrays.toString(input));
        System.out.println("Merge sort: " + Arrays.toString(mergeSort(input)));
        System.out.println("Input unchanged: " + Arrays.toString(input));

        Counter naive = new Counter();
        long n10 = fibNaive(10, naive);
        System.out.println("Naive F(10)=" + n10
                + ", calls=" + naive.calls);

        Counter memo = new Counter();
        long m10 = fibMemo(10, memo);
        System.out.println("Memo F(10)=" + m10
                + ", calls=" + memo.calls
                + ", computed=" + memo.computed);

        System.out.println("Rolling F(50)=" + fibRolling(50));
        System.out.println("Empty merge: "
                + Arrays.toString(mergeSort(new int[0])));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac IndependentVsOverlapping.java
java IndependentVsOverlapping
~~~

Stdout dự kiến chính xác:

~~~text
Input: [8, 3, 5, 3, 9, 1]
Merge sort: [1, 3, 3, 5, 8, 9]
Input unchanged: [8, 3, 5, 3, 9, 1]
Naive F(10)=55, calls=177
Memo F(10)=55, calls=19, computed=9
Rolling F(50)=12586269025
Empty merge: []
~~~

Các số đếm là **theo đúng cách cài đặt này**: phiên bản memo gọi F(0)/F(1) trực tiếp mà không điền cache cho hai trạng thái cơ sở; `computed` đếm các trạng thái F(2) tới F(10). Đừng đọc “19 lời gọi” thành “19 trạng thái phân biệt”: trạng thái riêng chỉ có 11 giá trị F(0)..F(10).

F(92)=7.540.113.804.746.346.429 vẫn chứa vừa kiểu long có dấu, còn F(93) thì không. Bản memo/rolling giới hạn n≤92. Bản đệ quy ngây thơ giới hạn n≤40 để tránh vô tình chạy công việc cấp số mũ rất lâu. Muốn tính số Fibonacci lớn hơn có thể dùng BigInteger nhưng phải phân tích thêm chi phí cộng các số ngày càng dài.

## 10. Chứng minh tính đúng của các thuật toán

### 10.1. Merge sort

**Cơ sở:** một đoạn 0 hoặc 1 phần tử đã có thứ tự.

**Bước quy nạp:** giả sử mọi lời gọi trên đoạn ngắn hơn đều sắp xếp đúng. Khi đoạn dài ít nhất 2 được chia tại mid, hai nửa có độ dài nhỏ hơn và rời nhau. Theo giả thiết quy nạp, sau hai lời gọi, mỗi nửa đã tăng không giảm. Khi trộn, chọn giá trị nhỏ hơn ở đầu hai nửa còn lại, nên mỗi phần tử ghi vào vùng output là nhỏ nhất trong các phần tử chưa trộn. Khi một nửa hết, chép phần còn lại của nửa kia. Kết quả tăng không giảm và giữ đủ các phần tử ban đầu.

Mỗi lần tách giảm độ dài, và phép trộn đưa các con trỏ tiến về phía phải, nên thuật toán kết thúc. Khi hai giá trị ở đầu bằng nhau, bản ví dụ chọn bên trái trước (dấu `<=`), phù hợp với nguyên tắc trộn ổn định khi dữ liệu là bản ghi có nhãn; với int đơn thuần, tính ổn định không quan sát được bằng giá trị.

### 10.2. Fibonacci có memoization

**Cơ sở:** F(0)=0, F(1)=1.

**Bước quy nạp:** giả sử lời gọi với số nhỏ hơn n đều đúng. Nếu F(n) chưa được lưu, chương trình tính đúng F(n−1) và F(n−2), cộng ra F(n), lưu vào memo[n]. Nếu F(n) đã được lưu, giá trị ấy từng được tính đúng nên dùng lại vẫn đúng. Mọi lời gọi chưa có kết quả giảm n và cuối cùng chạm cơ sở.

Chứng minh dựa vào tính xác định của F(n) theo **chỉ n**. Nếu hàm cần thêm tham số, dữ liệu thay đổi hoặc hiệu ứng bên ngoài, cache chỉ theo n không còn được bảo đảm đúng.

### 10.3. Fibonacci rolling

Trước vòng lặp, previous=F(0), current=F(1). Sau bước i≥2, next=F(i−2)+F(i−1)=F(i); gán previous=current và current=next khôi phục bất biến previous=F(i−1), current=F(i). Khi i=n hoàn thành, current là F(n). Vòng lặp hữu hạn nên kết thúc.

## 11. Bảng so sánh chi phí

| Cách làm | Số trạng thái hoặc lời gọi | Thời gian | Bộ nhớ phụ | Giải thích |
| --- | --- | --- | --- | --- |
| Merge sort n≥2 | 2n−1 lời gọi với n≥1; khoảng riêng | Θ(n log n) | Θ(n) cho bản sao và scratch | Có bước merge ở mỗi tầng |
| Fibonacci đệ quy thuần | Θ(φ^n) lời gọi | Θ(φ^n) | O(n) stack | Tính trùng nhiều F(k) |
| Fibonacci memo | O(n) trạng thái phân biệt | Θ(n) | Θ(n) bảng và stack | Tính mới mỗi F(k) một lần |
| Fibonacci tabulation mảng | n+1 ô trạng thái | Θ(n) | Θ(n) | Duyệt trạng thái theo phụ thuộc |
| Fibonacci rolling | Không lưu cả bảng | Θ(n) | Θ(1) | Chỉ cần hai giá trị trước |

Bảng dùng mô hình **phép cộng số nguyên có chi phí O(1)** trong giới hạn không tràn. Nếu dùng số nguyên độ chính xác tùy ý với n rất lớn, chi phí các phép cộng phụ thuộc độ dài bit và cần phân tích lại.

Số trạng thái ≠ số lời gọi ≠ tổng thời gian. Merge sort có số lời gọi tuyến tính nhưng mỗi cấp phải trộn; Fibonacci ngây thơ có số lời gọi cấp số mũ nhưng mỗi lời gọi chỉ làm một vài phép cộng. Memoization giảm số lần tính mới, không tự làm mọi bài toán thành O(n).

## 12. Ví dụ khác về chồng lặp

### 12.1. Đếm đường đi trong lưới

Cho lưới R×C, chỉ đi sang phải hoặc xuống. Gọi ways(r,c) là số đường từ ô (r,c) tới đích với lưới và đích giữ nguyên:

~~~text
ways(r,c) = ways(r+1,c) + ways(r,c+1)
~~~

Một ô có thể được đi tới từ nhiều nhánh của cây đệ quy. Số cách đi tiếp từ **cùng ô** là cùng trạng thái, nên có thể cache bằng cặp (r,c). Với mỗi ô tính một lần và xử lý O(1) chuyển tiếp, thời gian O(RC), bộ nhớ bảng O(RC). Phải định nghĩa đúng trường hợp cơ sở, biên ngoài lưới, vật cản và các hạn chế đường đi; nếu ô đích hoặc vật cản thay đổi, cache cũ có thể không còn đúng.

### 12.2. Knapsack 0/1

Gọi best(i, capacity) là giá trị tối ưu khi chỉ còn các vật phẩm từ i trở đi, với dung lượng còn lại capacity. Một nhánh chọn vật phẩm và một nhánh bỏ vật phẩm có thể **gặp lại đúng cặp (i, capacity)** theo các con đường khác nhau. Khi có n vật phẩm, W là dung lượng nguyên và mỗi trạng thái có số chuyển tiếp hằng số, DP chuẩn có O(nW) trạng thái/thời gian giả đa thức, bộ nhớ O(nW) nếu lưu toàn bộ bảng.

Cache chỉ theo i là **sai** vì cùng i nhưng dung lượng khác nhau có thể có kết quả khác nhau. Không phải mọi bộ dữ liệu đều khiến các nhánh chồng lặp đáng kể; điều đó phụ thuộc các trạng thái thực tế được thăm.

### 12.3. Matrix-chain multiplication

Bài toán tìm cách đặt ngoặc nhân n ma trận với ít phép nhân vô hướng nhất thường dùng trạng thái m(i,j): chi phí tối ưu để nhân các ma trận từ i tới j. Khi thử các điểm tách k, nhiều phương án phụ thuộc các **đoạn (i,j) giống nhau**. Chia để trị thuần túy sẽ tính lại nhiều đoạn; DP giải mỗi trạng thái đoạn một lần.

Với n ma trận, có O(n²) đoạn và mỗi đoạn có thể thử O(n) điểm tách, nên thời gian chuẩn O(n³), bộ nhớ O(n²). Đây là ví dụ công thức *chia bài toán* nhưng các trạng thái *chồng lặp qua nhiều phương án*, cần phân biệt với Merge sort có một cách tách cố định cho mỗi đoạn.

## 13. Cách chọn lời giải và các lỗi thường gặp

Quy trình thực hành:

1. **Viết định nghĩa trạng thái chính xác.** Những tham số nào quyết định kết quả? Có dữ liệu ngoài nào phải cố định?
2. **Vẽ cây lời gọi cho n nhỏ.** Ghi trạng thái trên từng nút, không chỉ giá trị của phần tử.
3. **Nhận ra trạng thái lặp.** Hai nhánh có gọi lại đúng bài toán S hay chỉ xử lý hai vùng khác nhau?
4. **Viết truy hồi và trường hợp cơ sở.** Mọi cạnh phụ thuộc có tiến tới trạng thái nhỏ hơn hoặc một thứ tự tính hợp lệ không?
5. **Đếm trạng thái và chuyển tiếp.** Tổng thời gian DP thường là tổng công việc của các trạng thái được xử lý, không chỉ “bao nhiêu tầng đệ quy”.
6. **Chọn memoization hay tabulation.** Cân nhắc số trạng thái được thăm, khả năng liệt kê bảng, stack và bộ nhớ.
7. **Tối ưu nếu có thể.** Từ một bảng n ô xuống hai biến chỉ hợp lệ khi công thức không còn cần các trạng thái cũ hơn.
8. **Kiểm thử tính đúng trước khi đo tốc độ.** Các thuật toán so sánh phải trả kết quả tương đương trên cùng miền đầu vào.

Những lỗi hay xảy ra:

- **Có hai lời gọi đệ quy → mặc định chồng lặp.** Sai với Merge sort: hai nửa là phạm vi khác nhau.
- **Hai đoạn có giá trị giống nhau → dùng cùng khóa cache.** Sai nếu trạng thái thực tế bao gồm vị trí hoặc ngữ cảnh khác.
- **Memoization luôn thành O(n).** Sai: số trạng thái có thể là O(n²), O(nW), thậm chí quá lớn để lưu.
- **Lưu cache theo khóa thiếu tham số.** Ví dụ knapsack không được bỏ remainingCapacity.
- **Cho rằng bài toán con độc lập không cần kết hợp.** Merge sort vẫn trả chi phí Θ(n) cho từng bước trộn ở cấp cha.
- **Bỏ qua tính hợp lệ của cache.** Dữ liệu sửa giữa chừng hoặc hàm có tác động phụ có thể làm kết quả lưu sai.
- **Quên ngăn xếp và mảng phụ.** Memo Fibonacci cần cả bảng và stack; Merge sort cần scratch.
- **Cho rằng chia để trị luôn O(log n) độ sâu.** Phân chia mất cân bằng có thể tạo độ sâu O(n).
- **Đo Fibonacci ngây thơ với n quá lớn.** Số lời gọi tăng nhanh; cần giới hạn n và dùng DP khi phù hợp.
- **Nhầm số lần vào helper với số lần tính mới.** Cache hit vẫn là một lần gọi nhưng không giải lại cả cây.
- **Không phân biệt bài toán tối ưu với đếm cách.** Khái niệm “cấu trúc con tối ưu” quan trọng cho DP tối ưu; với bài toán đếm, cần truy hồi đếm đúng mà không nhất thiết dùng thuật ngữ tối ưu.
- **Để đệ quy có chu trình không xử lý.** Memoization thuần không tự sửa công thức không có điều kiện dừng.

## 14. Kế hoạch kiểm thử và bài tập

### Kiểm thử bắt buộc

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Merge sort [8,3,5,3,9,1] | [1,3,3,5,8,9] |
| Merge sort [] | [] |
| Merge sort [5] | [5] |
| Merge sort [-3,2,0,-3] | [-3,-3,0,2] |
| Merge sort input null | NullPointerException |
| Merge sort | Không sửa đầu vào |
| Fibonacci F(0), F(1) | 0 và 1 |
| Fibonacci F(10) | 55 với cả ba cách |
| Fibonacci F(50) | 12586269025 với memo/rolling |
| Fibonacci F(92) | 7540113804746346429 với long |
| Fibonacci n âm | IllegalArgumentException |
| Fibonacci n>40 ở bản naive | IllegalArgumentException |
| Fibonacci n>92 ở bản memo/rolling | IllegalArgumentException |
| Thống kê F(10) ở ví dụ | naive 177 calls; memo 19 calls và computed 9 |

Với Merge sort, sinh các mảng nhỏ chứa số âm/dương/trùng và so sánh với `Arrays.sort` trên một bản sao; đối chiếu mảng gốc không thay đổi. Với Fibonacci, kiểm tra memo và rolling cho n=0..92; chỉ kiểm tra naive cho n nhỏ để tránh công việc cấp số mũ.

### Câu hỏi tự luyện

1. Với n=8, Merge sort tạo bao nhiêu nút/lời gọi khi mỗi đoạn dài ít nhất 2 đều chia hai? Các nửa ở mỗi nút có giao nhau không?
2. Vẽ cây F(6); đánh dấu những trạng thái F(k) xuất hiện nhiều lần. Có bao nhiêu **giá trị trạng thái khác nhau**, so với tổng số lời gọi?
3. Nếu Fibonacci memo chỉ lưu n chẵn, còn n lẻ luôn tính lại, điều gì xảy ra với tổng công việc?
4. Khi chỉ cần F(n), vì sao có thể giảm bảng DP xuống hai biến? Trường hợp nào muốn truy vết toàn bộ dãy F(0)..F(n) thì không thể chỉ trả hai biến như vậy?
5. Với knapsack, vì sao cache best(i) là không đủ? Hãy cho hai lời gọi có cùng i nhưng dung lượng khác nhau.
6. Với Matrix-chain multiplication, vì sao công thức trông giống chia để trị nhưng vẫn cần lưu các trạng thái m(i,j) để tránh trùng lặp?

## 15. Checklist tổng kết

- [ ] Đã định nghĩa **trạng thái bài toán con** bằng đủ tham số?
- [ ] Đã phân biệt **các đoạn rời nhau** với **trạng thái thực sự chồng lặp**?
- [ ] Có nhiều nhánh cần tính lại cùng một kết quả không?
- [ ] Đã viết công thức truy hồi, cơ sở và chứng minh tính kết thúc?
- [ ] Với chia để trị, đã tính cả chi phí **kết hợp** ở cấp cha?
- [ ] Nếu memoize, khóa cache đủ thông tin và kết quả ổn định theo khóa?
- [ ] Nếu tabulate, thứ tự tính tuân theo quan hệ phụ thuộc?
- [ ] Đã đếm số trạng thái và công việc mỗi trạng thái?
- [ ] Đã tính đầy đủ bộ nhớ phụ gồm cache, scratch và stack?
- [ ] Đã bảo vệ chương trình trước input không hợp lệ và tràn số?
- [ ] Đã kiểm thử tính đúng trên đầu vào nhỏ trước khi đo hiệu năng?

**Kết luận:** bài toán con độc lập thường nên giải trực tiếp rồi kết hợp, như hai đoạn rời nhau của Merge sort. Bài toán con chồng lặp cần nhận diện theo **cùng trạng thái toán học**, như F(k) trong nhiều nhánh Fibonacci; khi ấy memoization hoặc tabulation có thể tránh tính lại. Điều quyết định lựa chọn không phải số lời gọi con tại mỗi nút, mà là **số trạng thái duy nhất, quan hệ phụ thuộc, chi phí xử lý từng trạng thái và bộ nhớ cần dùng**.
