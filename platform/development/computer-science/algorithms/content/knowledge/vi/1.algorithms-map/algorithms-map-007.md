# Các họ kỹ thuật thiết kế thuật toán và cách nhận diện

> **Nhánh kiến thức:** Bản đồ thuật toán — Computer Science Algorithms.  
> **Mục tiêu:** Khi gặp một bài toán mới, nhận ra cấu trúc của nó, đề xuất vài họ kỹ thuật phù hợp, biết điều kiện để mỗi kỹ thuật đúng, và chọn phương án dựa trên chứng minh cùng độ phức tạp.

## 1. Đọc bài toán trước khi chọn thuật toán

Một **họ kỹ thuật thiết kế thuật toán** (*algorithm design paradigm*) là cách tổ chức lời giải có thể tái sử dụng trên nhiều bài toán: thử mọi khả năng, chia bài toán, ra quyết định tham lam, lưu trạng thái con, tìm kiếm có cắt tỉa... Tên một thuật toán cụ thể như merge sort, Dijkstra hay Kruskal thường chỉ là một ví dụ thuộc hoặc kết hợp nhiều kỹ thuật.

Không nên phân loại cứng theo một nhãn duy nhất. Ví dụ, Dijkstra vừa giải bài toán đường đi trên đồ thị, vừa dùng lựa chọn tham lam và hàng đợi ưu tiên; một bài quy hoạch động có thể dùng tìm kiếm nhị phân để tăng tốc chuyển trạng thái.

Trước khi chọn họ kỹ thuật, xác định rõ:

1. **Đầu vào:** kích thước `n`, miền giá trị, dữ liệu có thứ tự không, có phần tử âm/trùng không, có cạnh trọng số âm không, đầu vào có thay đổi theo thời gian không?
2. **Đầu ra:** cần tìm *một* nghiệm, *mọi* nghiệm, đếm số nghiệm, tối ưu giá trị, hay chỉ kiểm tra tính khả thi?
3. **Ràng buộc:** thời gian, bộ nhớ, cần nghiệm chính xác hay cho phép xấp xỉ, có được tiền xử lý, có truy vấn lặp lại không?
4. **Cấu trúc:** các phần có độc lập không, bài toán con có lặp lại không, có thể chứng minh một lựa chọn cục bộ luôn an toàn không, điều kiện đúng/sai có đơn điệu không?
5. **Chứng cứ đúng:** bất biến vòng lặp, quy nạp, lập luận trao đổi, quan hệ truy hồi, hoặc tính đầy đủ của phép liệt kê.

**Bản đồ nhận diện nhanh**

| Dấu hiệu nổi bật | Họ/pattern nên xét | Câu hỏi kiểm tra quyết định |
|---|---|---|
| Không gian nghiệm nhỏ; cần chuẩn đối chiếu | Vét cạn (*brute force*) | Liệt kê hết có nằm trong giới hạn không? |
| Chia thành nhiều bài toán con tương đối độc lập | Chia để trị (*divide and conquer*) | Có cách kết hợp kết quả nhanh và đúng không? |
| Mỗi bước giảm về một bài toán nhỏ hơn | Giảm để trị (*decrease and conquer*) | Phần còn lại có giữ nguyên tính chất cần tìm không? |
| Muốn chốt lựa chọn ngay, không quay lại | Tham lam (*greedy*) | Có chứng minh lựa chọn cục bộ dẫn đến nghiệm toàn cục không? |
| Tối ưu/đếm; trạng thái con lặp lại | Quy hoạch động (*dynamic programming*, DP) | Xác định được trạng thái và công thức chuyển đúng không? |
| Cần dựng nghiệm thỏa nhiều ràng buộc | Quay lui (*backtracking*) | Có thể loại sớm nhánh vi phạm ràng buộc không? |
| Tối ưu tổ hợp, có cận tốt | Nhánh cận (*branch and bound*) | Cận có bảo đảm không bỏ mất nghiệm tốt hơn không? |
| Sắp xếp/biến đổi giúp lộ cấu trúc | Biến đổi và tiền xử lý | Chi phí chuẩn bị có được bù bởi truy vấn/xử lý sau không? |
| Tính khả thi theo đáp án có tính đơn điệu | Tìm kiếm nhị phân trên đáp án | Nếu mức `x` khả thi thì mọi mức lớn hơn/nhỏ hơn tương ứng cũng khả thi chứ? |
| Dữ liệu nằm trên đỉnh/cạnh, quan hệ phụ thuộc | Thuật toán đồ thị | Bài toán thực sự là kết nối, thứ tự, đường đi, cây khung hay luồng? |
| Cần thuật toán nhanh theo kỳ vọng | Ngẫu nhiên hóa | Cam kết là đúng tuyệt đối hay đúng với xác suất cao? |
| Bài toán tối ưu quá khó để giải chính xác ở quy mô lớn | Xấp xỉ/heuristic | Cần bảo đảm chất lượng nghiệm hay chỉ một phương án thực dụng? |

Bảng này là **điểm xuất phát**, không thay thế chứng minh. Một bài toán có thể cần tổ hợp: sắp xếp → hai con trỏ; tìm kiếm nhị phân đáp án → kiểm tra khả thi bằng tham lam; DP → tối ưu bằng cấu trúc dữ liệu.

## 2. Vét cạn và tìm kiếm có hệ thống

### 2.1. Vét cạn (*brute force*)

**Ý tưởng:** kiểm tra tất cả ứng viên theo một thứ tự xác định, giữ lại nghiệm hợp lệ/tốt nhất. Ưu điểm là rõ tính đầy đủ, dễ làm lời giải mẫu để kiểm chứng thuật toán tối ưu.

**Dấu hiệu:** `n` nhỏ; không có cấu trúc rõ; cần kiểm thử bằng đối chiếu. Nếu có `n` quyết định nhị phân, tìm hết có thể cần `2^n` nhánh; hoán vị `n` phần tử có thể đến `n!` trường hợp. Đừng suy từ tên “vét cạn” ra một độ phức tạp cố định: còn phụ thuộc số ứng viên và thời gian kiểm tra mỗi ứng viên.

**Khi tránh:** `n` lớn và không có cắt tỉa; không giả định máy sẽ chạy nổi chỉ vì vòng lặp ngắn. Với `n ≈ 20`, `2^n` đôi khi khả thi; với `n ≈ 100`, liệt kê toàn bộ thường bất khả thi.

### 2.2. Quay lui (*backtracking*)

**Ý tưởng:** xây nghiệm từng phần, thử một lựa chọn, đi sâu, rồi hoàn tác để thử lựa chọn khác. Khi một nghiệm bộ phận chắc chắn không thể dẫn đến nghiệm hợp lệ, **cắt ngay nhánh đó**. Ví dụ: xếp N quân hậu, tô màu đồ thị, Sudoku, sinh tổ hợp có điều kiện.

**Cách nhận diện:** yêu cầu liệt kê nghiệm, hoặc tìm một cấu hình hợp lệ dưới nhiều ràng buộc phụ thuộc lẫn nhau. Câu hỏi quan trọng là có kiểm tra được ràng buộc ngay khi thêm một phần tử không.

**Đảm bảo:** nếu chỉ cắt nhánh **không thể** dẫn đến nghiệm hợp lệ, thuật toán vẫn đầy đủ. Độ phức tạp xấu nhất thường vẫn hàm mũ. Khi cài đặt với mảng/danh sách trạng thái dùng chung, phải hoàn tác chính xác sau lời gọi đệ quy; nếu không các nhánh sẽ nhiễm trạng thái.

### 2.3. Nhánh cận (*branch and bound*)

Cũng duyệt cây nghiệm, nhưng phục vụ **tối ưu hóa**: giữ nghiệm tốt nhất đã biết (*incumbent*) và tính cận lạc quan cho mỗi nhánh. Với bài toán **tối thiểu hóa**, nếu cận dưới của nhánh đã lớn hơn hoặc bằng nghiệm tốt nhất thì có thể bỏ nhánh; với **tối đa hóa**, dùng cận trên nhỏ hơn hoặc bằng nghiệm tốt nhất.

Cận phải **hợp lệ**; cận ước lượng tùy ý có thể loại nhầm nghiệm tối ưu. Ví dụ áp dụng: bài toán người du lịch, phân công, ba lô nguyên trong các trường hợp cần nghiệm tối ưu chính xác. Nhánh cận có thể nhanh trong thực tế, nhưng không mặc nhiên biến bài toán hàm mũ thành đa thức.

**Phân biệt nhanh:** quay lui chủ yếu cắt vì *không hợp lệ*; nhánh cận còn cắt vì *không thể tốt hơn nghiệm hiện có*.

## 3. Chia để trị và giảm để trị

### 3.1. Chia để trị (*divide and conquer*)

Gồm ba bước: **chia** đầu vào thành các phần nhỏ, **giải đệ quy** các phần, **kết hợp** kết quả. Phù hợp nếu các phần tương đối độc lập và phép kết hợp hiệu quả.

- **Merge sort:** chia đôi, sắp xếp mỗi nửa, trộn hai nửa đã sắp xếp; thời gian `O(n log n)`, bộ nhớ phụ `O(n)` ở cài đặt mảng thông dụng.
- **Quicksort:** phân hoạch quanh pivot rồi xử lý các đoạn; trung bình `O(n log n)` với lựa chọn pivot phù hợp, trường hợp xấu `O(n²)`.
- **Bài toán đoạn:** tính thống kê mỗi nửa và ghép qua biên khi có công thức hợp lệ.

Một cách đánh giá thường gặp là truy hồi `T(n) = aT(n/b) + f(n)`, với `f(n)` là chi phí chia/ghép. Không áp dụng công thức này máy móc nếu kích thước các nhánh không cân bằng hoặc nhánh có chồng lặp lớn.

### 3.2. Giảm để trị (*decrease and conquer*)

Mỗi bước chỉ tiếp tục với **một** bài toán nhỏ hơn, như binary search trên một mảng đã sắp xếp. Khác biệt cốt lõi với merge sort: không giải cả hai nửa.

**Tìm kiếm nhị phân trên dữ liệu có thứ tự:** sau mỗi phép so sánh, loại bỏ chắc chắn một nửa miền tìm kiếm; `O(log n)` phép so sánh. Điều kiện then chốt là thứ tự và phép so sánh phù hợp.

**Tìm kiếm nhị phân trên đáp án:** không cần mảng đã sắp xếp; cần một mệnh đề khả thi **đơn điệu**. Chẳng hạn, nếu chở hàng được với sức chứa `C` thì mọi sức chứa lớn hơn cũng chở được. Ta tìm sức chứa nhỏ nhất khả thi bằng một hàm kiểm tra.

Dù dùng kiểu nào, phải nói rõ bất biến của `low/high`, giới hạn biên, xử lý khi không có đáp án và cách tính `mid = low + (high - low) / 2` để tránh tràn số ở dạng số nguyên thông thường.

## 4. Tham lam và quy hoạch động: cặp dễ nhầm nhất

### 4.1. Tham lam (*greedy*)

Từng bước chọn phương án tốt nhất theo tiêu chí cục bộ, **không xét lại**. Ưu thế thường là đơn giản, nhanh và ít bộ nhớ. Nhưng câu “chọn tốt nhất lúc này” chỉ là **trực giác**, không phải bằng chứng đúng.

**Dấu hiệu khả quan:** có thể sắp xếp các đối tượng theo một khóa và chứng minh chọn đối tượng đầu tiên luôn không làm mất nghiệm tối ưu. Hai dạng chứng minh phổ biến:

- **Lập luận trao đổi (*exchange argument*):** từ một nghiệm tối ưu bất kỳ, thay lựa chọn đầu bằng lựa chọn tham lam mà không làm xấu kết quả; lặp lại trên phần còn lại.
- **Bất biến/đi trước (*stays ahead*):** sau mỗi bước, nghiệm tham lam không thua một nghiệm khác theo một đại lượng đã xác định.

**Ví dụ đúng:** chọn nhiều khoảng thời gian **không giao nhau** nhất, mỗi lần chọn khoảng có thời điểm kết thúc sớm nhất trong các khoảng còn khả dụng. Sắp xếp `O(n log n)`, duyệt `O(n)`. Nếu mỗi khoảng có **trọng số/lợi ích riêng** và mục tiêu là tổng lợi ích tối đa, quy tắc này không còn bảo đảm đúng: thường dùng *weighted interval scheduling DP*.

**Ví dụ sai:** đổi ít đồng nhất với mệnh giá `{1, 3, 4}`, tổng `6`. Lấy đồng lớn nhất mỗi lần cho `4 + 1 + 1` (3 đồng), trong khi `3 + 3` chỉ cần 2 đồng. Tham lam không được suy ra từ việc có thể chọn đồng lớn nhất.

### 4.2. Quy hoạch động (*dynamic programming*, DP)

DP dùng khi có thể mô tả lời giải bằng **bài toán con và quan hệ chuyển trạng thái**; đặc biệt hữu ích khi các bài toán con **chồng lặp**. Lưu kết quả để không tính lại, bằng:

- **Memoization (top-down):** đệ quy + bộ nhớ đệm, chỉ tính trạng thái được thăm.
- **Tabulation (bottom-up):** tính trạng thái theo thứ tự phụ thuộc; dễ tối ưu bộ nhớ khi chỉ cần vài lớp trước.

Quy trình thiết kế DP:

1. Định nghĩa `dp[state]` bằng một câu chính xác, gồm ý nghĩa của các chỉ số.
2. Xác định **trạng thái cơ sở**.
3. Liệt kê **mọi quyết định hợp lệ** ở một trạng thái và tạo quan hệ chuyển.
4. Chỉ rõ thứ tự tính không dùng giá trị chưa xác định; nếu dùng đệ quy, phải có điều kiện dừng.
5. Lập luận rằng mọi nghiệm tối ưu thuộc một nhánh đã xét và lời giải con tối ưu được sử dụng đúng.
6. Đếm số trạng thái × chi phí mỗi chuyển; xét khả năng nén bộ nhớ.

Ví dụ: đổi ít đồng nhất với mệnh giá không giới hạn, `dp[x]` là số đồng ít nhất để tạo tổng `x`:

`dp[0] = 0`; với `x > 0`, `dp[x] = 1 + min(dp[x - c])` trên mọi mệnh giá `c ≤ x` có trạng thái trước đó khả thi. Trạng thái không tạo được biểu diễn bằng vô cực. Nếu có `k` mệnh giá và tổng `W`, thời gian `O(kW)`, bộ nhớ `O(W)`. Đây là **giả đa thức** theo trị số `W`, không nhất thiết đa thức theo số bit biểu diễn `W`.

**Đừng gắn nhãn DP chỉ vì có đệ quy.** Đệ quy cây không lưu trạng thái có thể tính lặp; một bài có cấu trúc con tối ưu nhưng không chồng lặp đôi khi chia để trị là đủ. Ngược lại, DP có thể dùng trên DAG, chuỗi, đoạn, tập con hoặc chữ số — hình dạng bảng không quyết định bản chất.

### 4.3. Ví dụ Java 17: phản ví dụ tham lam, lời giải DP

Lưu tệp `CoinChangeFamilies.java`:

```java
import java.util.Arrays;

public class CoinChangeFamilies {
    // Tiền đề: coins tăng dần, mọi mệnh giá dương; ví dụ có đồng 1.
    static int greedyCount(int[] coins, int amount) {
        int count = 0;
        for (int i = coins.length - 1; i >= 0; i--) {
            count += amount / coins[i];
            amount %= coins[i];
        }
        return amount == 0 ? count : -1;
    }

    // Mỗi mệnh giá được sử dụng không giới hạn số lần.
    static int dpCount(int[] coins, int amount) {
        int inf = amount + 1;
        int[] dp = new int[amount + 1];
        Arrays.fill(dp, inf);
        dp[0] = 0;

        for (int x = 1; x <= amount; x++) {
            for (int coin : coins) {
                if (coin <= x && dp[x - coin] != inf) {
                    dp[x] = Math.min(dp[x], dp[x - coin] + 1);
                }
            }
        }
        return dp[amount] == inf ? -1 : dp[amount];
    }

    public static void main(String[] args) {
        int[] coins = {1, 3, 4};
        int amount = 6;
        System.out.println("Greedy: " + greedyCount(coins, amount));
        System.out.println("DP: " + dpCount(coins, amount));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 CoinChangeFamilies.java
java CoinChangeFamilies
```

Kết quả chuẩn:

```text
Greedy: 3
DP: 2
```

Với `coins` đã sắp xếp, phép tham lam ở đây tốn `O(k)`, nhưng **sai mục tiêu tối ưu** trên bộ mệnh giá này; DP tốn `O(kW)` và trả số đồng ít nhất nếu mô hình “dùng vô hạn đồng” đúng. Nếu bài toán giới hạn số lượng từng đồng, trạng thái/chuyển cần thay đổi: không dùng công thức này mà không kiểm tra điều kiện.

## 5. Biến đổi, tiền xử lý và giảm bài toán

**Transform and conquer** tìm một biểu diễn làm lời giải trở nên dễ hơn, thường thông qua sắp xếp, băm, nén tọa độ, tổng tiền tố, cấu trúc dữ liệu, hoặc chuyển bài toán về một bài toán đã biết.

- **Sắp xếp:** làm lộ thứ tự để dùng hai con trỏ, greedy theo mốc thời gian, quét sự kiện; phải tính thêm `O(n log n)` và xem có cần giữ chỉ số gốc không.
- **Hash map / hash set:** tra cứu trung bình gần `O(1)` mỗi thao tác; thích hợp cho đếm tần suất và bài toán bù. Phải xử lý trùng, khóa và bộ nhớ; độ phức tạp trung bình không đồng nghĩa chặn xấu nhất tuyệt đối.
- **Prefix sum:** sau chuẩn bị `O(n)`, tổng đoạn `[l, r)` là `prefix[r] - prefix[l]` trong `O(1)`; với số âm, có thể kết hợp hash map để đếm đoạn có tổng cho trước.
- **Nén tọa độ:** thay giá trị lớn/rời rạc bằng thứ hạng sau sắp xếp, giữ **thứ tự so sánh**; không giữ khoảng cách số học, nên không dùng các thứ hạng đó để thay thế phép trừ khoảng cách.
- **Giảm về đồ thị/matching/flow:** hữu ích khi cấu trúc quan hệ khớp một mô hình chuẩn, nhưng phải chứng minh ánh xạ hai chiều: nghiệm bài gốc ↔ nghiệm bài biến đổi.

Một biến đổi có thể **thay đổi điều kiện áp dụng kỹ thuật khác**: sắp xếp giúp hai con trỏ, nhưng làm mất thứ tự thời gian ban đầu; chỉ nên làm khi việc đổi thứ tự không phá yêu cầu.

## 6. Những pattern cần nhận diện sớm

Các pattern sau thường *kết hợp* với họ kỹ thuật ở trên, thay vì là các họ hoàn toàn tách biệt.

| Cấu trúc dữ liệu/yêu cầu | Pattern hiệu quả thường gặp | Điều kiện và cạm bẫy |
|---|---|---|
| Cặp phần tử trên mảng đã sắp xếp thỏa tổng | Hai con trỏ từ hai đầu | Dựa vào tính đơn điệu khi dịch con trỏ; cần xử lý trùng |
| Đoạn liên tiếp, cần duy trì tính chất đơn điệu khi mở rộng/thu hẹp | Cửa sổ trượt (*sliding window*) | Với tổng đoạn và số âm, quy tắc co khi tổng quá lớn thường sai |
| Đếm/tìm đoạn có tổng mục tiêu, có số âm | Prefix sum + hash map | Duy trì tần suất tổng tiền tố; xử lý tiền tố rỗng |
| Tổng min/max trên nhiều cửa sổ cố định | Deque đơn điệu | Cần loại phần tử hết hạn và phần tử kém hữu ích |
| Phần tử lớn hơn gần nhất, ngoặc, histogram | Stack đơn điệu | Mỗi phần tử vào/ra stack tối đa một lần trong pattern điển hình |
| Các sự kiện theo thời gian/tọa độ; đoạn giao nhau | Sắp xếp + sweep line | Quy tắc xử lý sự kiện cùng tọa độ ảnh hưởng đáp án |
| Nhiều truy vấn về tổng đoạn, mảng tĩnh | Prefix sum | Có cập nhật điểm thường xuyên thì cân nhắc Fenwick/segment tree |
| Truy vấn/cập nhật theo đoạn | Fenwick tree / segment tree | Xác định phép gộp và thao tác cập nhật, `O(log n)` điển hình |
| Truy vấn gộp nhóm kết nối khi thêm cạnh | Disjoint Set Union (DSU) | Tối ưu union-by-size/rank và path compression |
| Tối ưu đáp án số nguyên, kiểm tra khả thi đơn điệu | Binary search on answer | Hàm feasibility phải đúng, biên có đáp án, tránh overflow |
| Top-`k`, lấy phần tử ưu tiên liên tục | Heap / priority queue | `O(log n)` mỗi thêm/xóa đỉnh điển hình |

**Ví dụ phân biệt sliding window và prefix sum.** Với các số **không âm**, khi mở rộng cửa sổ, tổng không giảm; với mục tiêu tổng không vượt `K`, có thể co cửa sổ khi tổng vượt giới hạn. Nếu có số âm, mở rộng có thể làm tổng giảm, nên lập luận đó sụp đổ. Đếm số đoạn có tổng bằng `K` trong mảng chứa số âm thường dùng prefix sum + hash map.

### Java 17: đếm đoạn tổng cho trước dù có số âm

Lưu tệp `SubarrayTechniqueDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;

public class SubarrayTechniqueDemo {
    static long countSubarrays(int[] values, long target) {
        Map<Long, Long> frequency = new HashMap<>();
        frequency.put(0L, 1L); // Tiền tố rỗng.
        long prefix = 0L;
        long answer = 0L;

        for (int value : values) {
            prefix += value;
            answer += frequency.getOrDefault(prefix - target, 0L);
            frequency.merge(prefix, 1L, Long::sum);
        }
        return answer;
    }

    public static void main(String[] args) {
        int[] values = {1, -1, 1};
        System.out.println("Subarrays: " + countSubarrays(values, 1));
    }
}
```

```bash
javac -encoding UTF-8 SubarrayTechniqueDemo.java
java SubarrayTechniqueDemo
```

```text
Subarrays: 3
```

Ba đoạn thỏa mãn (chỉ số 0-based, biên phải loại trừ) là `[0,1)`, `[0,3)`, `[2,3)`. Vì tổng đoạn `[l,r) = prefix[r] - prefix[l]`, tại mỗi `r` ta đếm các tổng tiền tố trước đó bằng `prefix[r] - target`. **Phải cộng đáp án trước khi thêm tiền tố hiện tại** để chỉ đếm các đoạn không rỗng theo đúng thứ tự. Độ phức tạp kỳ vọng `O(n)`, bộ nhớ `O(n)`.

## 7. Nhận diện bài toán đồ thị

Đồ thị là **mô hình dữ liệu**, không phải một họ chứng minh duy nhất. Sau khi mô hình hóa đỉnh/cạnh, chọn mục tiêu chính xác:

| Bài toán thực chất | Thuật toán cần xét | Giả thiết/giới hạn cốt lõi |
|---|---|---|
| Duyệt thành phần liên thông, tìm đường đi bất kỳ | DFS hoặc BFS | `O(V + E)` trên biểu diễn danh sách kề |
| Đường đi **ít cạnh nhất** | BFS | Đồ thị không trọng số, hoặc mọi cạnh có cùng chi phí |
| Thứ tự thực hiện các công việc có quan hệ trước–sau | Topological sort | Phải là DAG; có chu trình thì không tồn tại thứ tự topo đầy đủ |
| Đường đi ngắn nhất từ một nguồn, trọng số không âm | Dijkstra + priority queue | Cạnh âm làm hỏng bảo đảm của Dijkstra chuẩn |
| Đường đi ngắn nhất có cạnh âm | Bellman–Ford | Không có chu trình âm *tới được từ nguồn* khiến khoảng cách nhỏ nhất không xác định hữu hạn |
| Đường đi trên DAG có trọng số bất kỳ | DP theo thứ tự topo | Đúng nhờ không có chu trình, kể cả trọng số âm |
| Kết nối tất cả đỉnh với tổng chi phí cạnh nhỏ nhất | Kruskal/Prim (MST) | Bài toán cây khung vô hướng; khác đường đi ngắn nhất |
| Chia nhóm kết nối khi thêm cạnh, xử lý offline | DSU | DSU cơ bản không trực tiếp hỗ trợ xóa cạnh động tổng quát |
| Luồng tối đa qua mạng có sức chứa | Max-flow | Cần mô hình đúng bảo toàn luồng, năng lực cạnh và nguồn/đích |

**Dấu hiệu “đi từ A đến B” chưa đủ để chọn BFS/Dijkstra.** Cần hỏi tối ưu **số cạnh**, **tổng trọng số**, **số bước theo trạng thái**, **chi phí nhỏ nhất với ràng buộc bổ sung**, hay chỉ cần **tồn tại đường đi**. Khi thêm điều kiện (ví dụ số lần được giảm giá), có thể cần mở rộng trạng thái đồ thị hoặc dùng DP.

## 8. Tìm kiếm nhị phân trên đáp án: ví dụ đầy đủ

Bài toán: có các kiện hàng có trọng lượng dương theo đúng thứ tự. Mỗi ngày chở một đoạn liên tiếp và tổng khối lượng không vượt sức chứa `C`. Tìm `C` nhỏ nhất để chở hết trong **không quá** `D` ngày.

Nhận diện: với `C` càng lớn, càng dễ hoàn thành trong `D` ngày. Điều kiện khả thi đơn điệu từ **false → true**. Với một `C` cố định, đi từ trái sang phải và xếp nhiều kiện nhất có thể vào mỗi ngày là đủ để kiểm tra số ngày ít nhất trong ràng buộc giữ nguyên thứ tự.

Lưu tệp `ShipCapacitySearch.java`:

```java
public class ShipCapacitySearch {
    static boolean canShip(int[] weights, int days, long capacity) {
        int usedDays = 1;
        long currentLoad = 0;

        for (int weight : weights) {
            if (weight > capacity) return false;
            if (currentLoad + weight > capacity) {
                usedDays++;
                currentLoad = 0;
            }
            currentLoad += weight;
            if (usedDays > days) return false;
        }
        return true;
    }

    static long minCapacity(int[] weights, int days) {
        if (weights.length == 0 || days < 1) {
            throw new IllegalArgumentException("Nonempty weights and days >= 1 required");
        }
        long low = 0, high = 0;
        for (int weight : weights) {
            if (weight <= 0) {
                throw new IllegalArgumentException("Weights must be positive");
            }
            low = Math.max(low, weight);
            high += weight;
        }

        while (low < high) {
            long mid = low + (high - low) / 2;
            if (canShip(weights, days, mid)) {
                high = mid;
            } else {
                low = mid + 1;
            }
        }
        return low;
    }

    public static void main(String[] args) {
        int[] weights = {1, 2, 3, 4, 5};
        System.out.println("Capacity: " + minCapacity(weights, 3));
    }
}
```

```bash
javac -encoding UTF-8 ShipCapacitySearch.java
java ShipCapacitySearch
```

```text
Capacity: 6
```

Với sức chứa 6 có thể chia thành `[1,2,3] | [4] | [5]` trong 3 ngày; sức chứa 5 cần 4 ngày. Cận dưới là trọng lượng kiện lớn nhất, cận trên là tổng trọng lượng. Mỗi kiểm tra tốn `O(n)`, tìm kiếm tốn `O(log S)` phép kiểm tra với `S` là khoảng độ lớn cần tìm, tổng `O(n log S)`, bộ nhớ phụ `O(1)`. Dùng `long` cho tổng và sức chứa để giảm nguy cơ tràn `int`.

Đây là ví dụ **kết hợp**: bài toán tối ưu + tính đơn điệu → tìm kiếm nhị phân; phép kiểm tra khả thi → chiến lược tham lam có thể chứng minh. Không phải mọi phép kiểm tra “tham lam trông hợp lý” đều dùng được.

## 9. Ngẫu nhiên hóa, xấp xỉ và heuristic

**Randomized algorithms** dùng quyết định ngẫu nhiên để cải thiện hành vi trung bình hoặc giảm phụ thuộc đầu vào. Cần phân biệt:

- **Las Vegas:** kết quả luôn đúng (theo giả thiết thuật toán), thời gian chạy là biến ngẫu nhiên; ví dụ quicksort chọn pivot ngẫu nhiên vẫn sắp xếp đúng và có thời gian kỳ vọng `O(n log n)`.
- **Monte Carlo:** thời gian chạy thường bị khống chế, nhưng có xác suất trả lời sai hoặc không đạt mức chất lượng mong muốn; cần nêu xác suất lỗi và cách giảm lỗi.

**Approximation algorithms** cho lời giải gần tối ưu với một **bảo đảm định lượng** (ví dụ tỷ lệ xấp xỉ) theo mô hình/giả thiết xác định. **Heuristic** là quy tắc thực nghiệm có thể cho kết quả tốt nhưng không có bảo đảm tổng quát tương ứng. Cả hai có giá trị khi tìm tối ưu chính xác quá tốn kém, nhưng không được báo nghiệm heuristic là “tối ưu” nếu chưa chứng minh.

**Online/streaming algorithms** xử lý dữ liệu khi nó đến, có thể không giữ toàn bộ đầu vào; cần xem giới hạn bộ nhớ, số lượt quét và khả năng phải ra quyết định trước khi thấy tương lai. Chúng có thể kết hợp với greedy, heap, ngẫu nhiên hoặc cấu trúc dữ liệu khác.

## 10. Quy trình lựa chọn và kiểm chứng

Khi nhận đề, có thể đi theo chuỗi câu hỏi sau:

1. **Chuẩn hóa yêu cầu:** đầu ra đúng nghĩa gì? Phân biệt tìm một nghiệm, đếm, kiểm tra tồn tại, tối thiểu/tối đa.
2. **Ước lượng giới hạn:** nếu `n` lớn, tránh mặc định duyệt `2^n`; nếu có `n` và `W`, kiểm tra cả hai trước khi dùng `O(nW)`. Cũng xét số test và bộ nhớ.
3. **Tìm cấu trúc mạnh nhất:** có thứ tự/đơn điệu, đoạn liên tiếp, đồ thị, các lựa chọn độc lập, trạng thái lặp lại, ràng buộc để cắt tỉa?
4. **Đề xuất ít nhất hai hướng khi chưa chắc:** lời giải đúng đơn giản để kiểm chứng và lời giải có độ phức tạp tốt hơn.
5. **Chứng minh điều kiện:** greedy cần lập luận trao đổi/bất biến; binary search cần đơn điệu; DP cần quan hệ truy hồi bao phủ mọi lựa chọn; pruning cần cận an toàn.
6. **Đếm chi phí thực tế:** tiền xử lý + thao tác chính + số truy vấn; phân biệt worst-case, trung bình/kỳ vọng và giả đa thức. Với `n` lớn, khoảng `O(n log n)` thường đáng xem xét, nhưng còn phụ thuộc hằng số và giới hạn cụ thể.
7. **Kiểm thử phản ví dụ:** đầu vào rỗng/nếu hợp lệ, một phần tử, tất cả bằng nhau, âm/0, trùng, biên lớn, đồ thị không liên thông, không có nghiệm, và các tình huống vi phạm giả thiết.

**Mẫu chứng minh tương ứng với họ kỹ thuật**

| Họ kỹ thuật | Bằng chứng nên trình bày |
|---|---|
| Vét cạn/quay lui | Mỗi nghiệm hợp lệ có thể được sinh; các nhánh bị cắt chắc chắn không chứa nghiệm cần tìm |
| Chia để trị | Bài toán con bao phủ các trường hợp; bước ghép bảo toàn tính đúng |
| Tham lam | Lựa chọn đầu an toàn (trao đổi hoặc bất biến), rồi quy nạp cho phần còn lại |
| DP | Định nghĩa trạng thái, cơ sở, chuyển trạng thái và quy nạp theo thứ tự phụ thuộc |
| Nhánh cận | Cận luôn hợp lệ; loại nhánh không thể cải thiện nghiệm tốt nhất |
| Binary search | Điều kiện đơn điệu, bất biến biên và điều kiện dừng |
| Ngẫu nhiên/xấp xỉ | Mô hình xác suất hoặc tỷ lệ bảo đảm được nêu rõ |

## 11. Bài tập nhận diện nhanh có đáp án

1. **Tối đa số cuộc họp không giao nhau, mỗi cuộc họp giá trị như nhau.** Sắp xếp theo thời gian kết thúc và chọn tham lam; cần chứng minh bằng trao đổi.
2. **Tối đa tổng lợi ích các cuộc họp không giao nhau, lợi ích khác nhau.** Sắp xếp theo thời gian kết thúc + DP với chỉ số cuộc họp tương thích trước đó (có thể dùng binary search).
3. **Tìm đường ít cạnh nhất trong mê cung ô vuông, mỗi bước cùng chi phí.** BFS trên đồ thị ô; nếu có khóa/cửa, trạng thái có thể gồm vị trí và tập khóa.
4. **Tìm đường ngắn nhất trong đồ thị có trọng số âm.** Không dùng Dijkstra chuẩn; xét Bellman–Ford hoặc DP trên DAG nếu không có chu trình. Kiểm tra chu trình âm khi mục tiêu yêu cầu khoảng cách hữu hạn.
5. **Chia dãy theo thứ tự thành ít ngày nhất với sức chứa giới hạn, rồi tìm sức chứa nhỏ nhất cho trước số ngày.** Tìm kiếm nhị phân đáp án + kiểm tra khả thi.
6. **Đếm đoạn con có tổng `K` khi mảng có phần tử âm.** Prefix sum + map tần suất; sliding window cộng/trừ đơn giản không có tính đơn điệu cần thiết.
7. **Xếp N quân hậu không ăn nhau.** Quay lui, cắt ngay khi trùng cột/đường chéo; worst-case vẫn có thể rất lớn.
8. **Nhiều thao tác thêm cạnh và hỏi hai đỉnh có liên thông không.** DSU nếu chỉ thêm cạnh; nếu có xóa cạnh cần kỹ thuật động/offline khác.
9. **Bài ba lô 0/1, mỗi món chỉ chọn một lần, sức chứa nguyên `W` vừa phải.** DP theo món và sức chứa; đừng nhầm với ba lô phân số, nơi greedy theo tỷ lệ giá trị/trọng lượng có thể đúng.
10. **Tìm phương án nhanh cho bài tối ưu NP-khó với dữ liệu rất lớn.** Cân nhắc xấp xỉ có bảo đảm hoặc heuristic, và công bố rõ chất lượng nghiệm được bảo đảm đến đâu.

## 12. Những lỗi lựa chọn thường gặp

- **Dùng greedy vì “có vẻ hợp lý”:** luôn chủ động tìm phản ví dụ nhỏ, nhất là khi lợi ích cục bộ ảnh hưởng các quyết định sau.
- **Dùng DP thiếu định nghĩa trạng thái:** nếu hai lịch sử cho cùng chỉ số nhưng kết quả tương lai khác nhau, trạng thái còn thiếu thông tin.
- **Dùng binary search mà predicate không đơn điệu:** đáp án kiểm tra bị lẫn nhiều tiêu chí có thể tạo chuỗi true/false xen kẽ.
- **Dùng sliding window trên tổng có số âm:** mở rộng không còn bảo đảm tổng tăng; chuyển sang prefix sum/map hoặc cấu trúc phù hợp.
- **Nhầm bài toán đồ thị:** MST không giải đường đi ngắn nhất; DFS không tự cho đường ít cạnh nhất; Dijkstra chuẩn không chịu cạnh âm.
- **Không tính chi phí tiền xử lý:** sắp xếp `O(n log n)` rồi hai con trỏ `O(n)` vẫn là `O(n log n)` cho cả lượt.
- **Cắt nhánh thiếu an toàn:** một “ước lượng có vẻ tệ” không đủ để loại nhánh trong bài cần tối ưu chính xác.
- **Đánh đồng trung bình với xấu nhất:** hash, quicksort, randomized algorithms có các bảo đảm khác nhau.
- **Tràn số và lỗi biên:** tổng lớn nên dùng `long`; kiểm tra `<`, `≤`, chỉ số 0/1-based, đoạn đóng/mở và trường hợp không có nghiệm.

**Ghi nhớ:** nhận diện kỹ thuật là phát hiện *cấu trúc và điều kiện đúng* của bài toán. Một lời giải tốt phải trả lời được đồng thời ba câu: **vì sao chọn kỹ thuật này, vì sao nó đúng, và vì sao nó đủ nhanh trong ràng buộc thực tế?**
