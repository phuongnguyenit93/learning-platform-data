# Hàng đợi đơn điệu và cực trị trong cửa sổ

**Hàng đợi đơn điệu** (monotonic deque) là kỹ thuật giữ lại các ứng viên có khả năng trở thành giá trị lớn nhất hoặc nhỏ nhất trong một **cửa sổ trượt** của dãy. Khi cửa sổ dịch sang phải, phần tử đã hết hạn được loại bỏ; phần tử mới có thể khiến một số ứng viên cũ không còn cần thiết. Nhờ duy trì một deque (hàng đợi hai đầu) theo thứ tự đơn điệu, ta tính min/max của **tất cả cửa sổ liên tiếp có cùng độ dài** trong thời gian tuyến tính.

Ý tưởng trung tâm là ba bất biến: **chỉ số tăng dần**, **giá trị các ứng viên đơn điệu**, và **mọi ứng viên đều còn nằm trong cửa sổ**. Chỉ số ở đầu deque cho ngay giá trị cực trị. Hiểu được vì sao xóa ứng viên không làm mất lời giải và vì sao số lần xóa có tổng chi phí nhỏ là chìa khóa để sử dụng kỹ thuật đúng.

## 1. Bài toán cửa sổ trượt

Cho mảng số nguyên a gồm n phần tử, đánh chỉ số từ 0 tới n-1, và số nguyên k thỏa mãn \(1\le k\le n\). Cửa sổ kết thúc tại vị trí r, khi r đã đủ lớn, có biên:

\[
left=r-k+1,\qquad W_r=[left,r],\qquad r\ge k-1.
\]

Cần tìm giá trị cực đại hoặc cực tiểu của các phần tử trong mỗi cửa sổ:

\[
M_r=\max\{a[i]\mid r-k+1\le i\le r\},
\quad
m_r=\min\{a[i]\mid r-k+1\le i\le r\}.
\]

Có đúng \(n-k+1\) cửa sổ đầy đủ, ứng với r chạy từ \(k-1\) tới \(n-1\).

Ví dụ với dãy \(a=[4,2,12,3,8,7,9]\), \(k=3\):

| Cửa sổ | Giá trị trong cửa sổ | Min | Max |
|---|---|---:|---:|
| Chỉ số 0..2 | [4, 2, 12] | 2 | 12 |
| Chỉ số 1..3 | [2, 12, 3] | 2 | 12 |
| Chỉ số 2..4 | [12, 3, 8] | 3 | 12 |
| Chỉ số 3..5 | [3, 8, 7] | 3 | 8 |
| Chỉ số 4..6 | [8, 7, 9] | 7 | 9 |

Kết quả max là **[12, 12, 12, 8, 9]** và kết quả min là **[2, 2, 3, 3, 7]**.

Bài toán yêu cầu **một giá trị cực trị cho mỗi cửa sổ**, không phải cực trị của toàn bộ mảng hay một giá trị tổng hợp duy nhất. Nếu muốn cả chỉ số nơi xuất hiện cực trị, cần thêm quy tắc giải quyết trường hợp nhiều phần tử bằng nhau.

## 2. Tại sao cần tối ưu?

Cách trực tiếp là xét từng biên trái l từ 0 tới n-k, rồi quét k phần tử trong đoạn [l,l+k-1]. Với đúng \(n-k+1\) cửa sổ, thời gian sẽ là:

\[
\Theta((n-k+1)k).
\]

Bộ nhớ phụ có thể \(O(1)\), chưa tính mảng lưu kết quả. Nếu k gần n/2, số phép xét là bậc \(\Theta(n^2)\), dù hai cửa sổ liền nhau chia sẻ phần lớn phần tử.

Một heap có thể quản lý các ứng viên cực trị, nhưng cần xử lý phần tử không còn thuộc cửa sổ (chẳng hạn lazy deletion) và thường có chi phí \(O(\log n)\) trên một thao tác. Cây cân bằng hoặc segment tree hữu ích trong những biến thể cần cập nhật hoặc truy vấn đoạn bất kỳ, nhưng với **một cửa sổ cố định dịch liên tục sang phải**, deque đơn điệu đạt \(O(n)\) tổng thời gian và \(O(k)\) bộ nhớ phụ.

## 3. Deque lưu chỉ số, không chỉ lưu giá trị

Deque hỗ trợ thêm/xóa ở cả đầu trước (front) và đầu sau (back). Trong thuật toán này, deque lưu **chỉ số của phần tử**. Ta cần chỉ số để nhận biết khi nào ứng viên đã ra khỏi cửa sổ, đặc biệt khi dãy chứa nhiều giá trị trùng nhau.

Với **cực đại**, deque Dmax có các bất biến sau khi xử lý vị trí r:

1. **Thứ tự chỉ số:** các chỉ số trong deque tăng dần từ front tới back; chỉ số mới luôn được thêm vào cuối.
2. **Tính hợp lệ:** mỗi chỉ số đều thuộc cửa sổ hiện tại, tức không nhỏ hơn left = r-k+1; trong giai đoạn cửa sổ chưa đủ k phần tử, các chỉ số đã đọc đều còn được giữ nếu chưa bị thống trị.
3. **Giá trị đơn điệu:** nếu loại phần tử cũ khi có giá trị bằng phần tử mới, các giá trị ứng với chỉ số trong deque giảm **nghiêm ngặt** từ front tới back.
4. **Đầu deque cho cực đại:** giá trị a[Dmax.front] chính là max của cửa sổ, khi cửa sổ đã đầy đủ.

Với **cực tiểu**, deque Dmin giữ giá trị **tăng nghiêm ngặt** và đầu deque cho min.

Deque không cần giữ mọi phần tử của cửa sổ: những chỉ số bị phần tử đến sau thống trị được loại đi. Đây là điểm làm thuật toán tiết kiệm công việc.

## 4. Ba thao tác cập nhật khi cửa sổ dịch

Giả sử đang đưa phần tử mới tại chỉ số r vào cửa sổ. Biên trái của cửa sổ là left = r-k+1.

**A. Xóa phần tử hết hạn ở front.** Chừng nào chỉ số ở front **nhỏ hơn left**, ta xóa nó khỏi deque. Vì các chỉ số tăng dần, chỉ có đầu trước mới chứa phần tử hết hạn. Điều kiện đúng là index < left, tương đương index <= r-k; không được xóa index = left vì nó vẫn hợp lệ.

**B. Xóa ứng viên bị thống trị ở back.**

- Nếu cần max: liên tục xóa ứng viên cuối có giá trị **nhỏ hơn hoặc bằng** a[r].
- Nếu cần min: liên tục xóa ứng viên cuối có giá trị **lớn hơn hoặc bằng** a[r].

**C. Thêm r vào back.** Sau đó, khi r >= k-1, trả giá trị tại front.

Mã giả cho **max**:

~~~text
D = deque rỗng
for r = 0 .. n - 1:
    left = r - k + 1

    while D không rỗng và D.front < left:
        xóa đầu trước

    while D không rỗng và a[D.back] <= a[r]:
        xóa đầu sau

    thêm r vào đầu sau

    if r >= k - 1:
        xuất a[D.front]
~~~

Để tìm **min**, thay dấu so sánh ở vòng xóa đầu sau từ <= thành >=. Nếu cần cả hai, duy trì hai deque và cập nhật trong cùng một lần duyệt.

**Vì sao có thể xóa ở back?** Giả sử j < r và a[j] <= a[r] khi tìm max. Mọi cửa sổ trượt sang phải về sau còn chứa vị trí j đều cũng chứa r, vì r nằm sau j. Phần tử tại r không nhỏ hơn phần tử tại j, đồng thời **hết hạn muộn hơn**. Do đó j không thể là ứng viên tốt hơn r trong một cửa sổ tương lai: xóa j là an toàn. Với min, lập luận đối xứng khi a[j] >= a[r].

Chú ý: bước A giải quyết **hết hạn theo vị trí**; bước B giải quyết **bị thống trị theo giá trị**. Thiếu một trong hai bước có thể khiến thuật toán trả kết quả sai.

## 5. Mô phỏng hàng đợi max từng bước

Với a = [4, 2, 12, 3, 8, 7, 9], k = 3, biểu diễn deque dưới dạng các cặp chỉ số:giá trị. Ví dụ 2:12 nghĩa là a[2] = 12.

| r | a[r] | left | Deque max sau khi cập nhật | Max xuất ra |
|---:|---:|---:|---|---:|
| 0 | 4 | -2 | [0:4] | Chưa đủ k |
| 1 | 2 | -1 | [0:4, 1:2] | Chưa đủ k |
| 2 | 12 | 0 | [2:12] | **12** |
| 3 | 3 | 1 | [2:12, 3:3] | **12** |
| 4 | 8 | 2 | [2:12, 4:8] | **12** |
| 5 | 7 | 3 | [4:8, 5:7] | **8** |
| 6 | 9 | 4 | [6:9] | **9** |

Các bước đáng chú ý:

- Khi r=2, phần tử 12 lớn hơn 2 và 4 nên cả hai ứng viên cũ bị xóa ở back. Đầu deque là 2:12.
- Khi r=4, 8 xóa ứng viên 3:3 ở back, nhưng không xóa 2:12 vì 12 > 8.
- Khi r=5, cửa sổ là [3,5], chỉ số 2 đã hết hạn nên bị xóa ở front; đầu mới 4:8 cho giá trị 8.
- Khi r=6, giá trị 9 thống trị 7 và 8; deque chỉ còn 6:9.

Tại mọi thời điểm cửa sổ đã đủ k phần tử, front luôn chỉ đến vị trí cực đại hợp lệ. Không cần nhìn lại các phần tử đã bị xóa.

## 6. Trường hợp có nhiều giá trị bằng nhau

Điều kiện xóa ở back ảnh hưởng đến **vị trí** được chọn khi có nhiều phần tử cùng đạt min/max.

Với max:

- Dùng so sánh **<=**: khi phần tử mới bằng phần tử cũ, xóa bản sao cũ. Deque có giá trị **giảm nghiêm ngặt**; vị trí cực đại được ưu tiên là bản sao **mới nhất** còn hợp lệ.
- Dùng so sánh **<**: giữ lại các bản sao cùng giá trị. Deque có giá trị **không tăng**; khi cần chỉ số của cực đại, front ưu tiên **vị trí cũ nhất** còn hợp lệ.

Với min: dùng >= để ưu tiên bản sao mới nhất, hoặc > để ưu tiên bản sao cũ nhất.

Ví dụ a = [5, 5, 4, 5], k=2. Mọi cửa sổ đều có max bằng 5, nhưng chỉ số cực đại được chọn có thể khác nhau theo quy tắc hòa. Nếu đề bài chỉ cần **giá trị cực trị**, cả hai quy tắc đều đúng và có độ phức tạp như nhau. Nếu đề bài yêu cầu vị trí trái nhất hoặc phải nhất của cực trị, phải ghi rõ quy tắc trong đặc tả và áp dụng dấu so sánh tương ứng.

Không nên nói “front luôn là vị trí đầu tiên có giá trị max” nếu đang dùng dấu <=: front chỉ bảo đảm là **một vị trí có giá trị max**.

## 7. Chứng minh tính đúng

Chứng minh cho Dmax; Dmin hoàn toàn tương tự với chiều so sánh ngược lại.

**Cơ sở quy nạp.** Trước khi đọc phần tử nào, deque rỗng. Sau phần tử đầu tiên, chỉ số hợp lệ được thêm vào; chỉ số tăng dần, giá trị đơn điệu và front là cực đại của phần đã xét.

**Bước quy nạp.** Giả sử sau khi xử lý r-1, deque giữ đúng những ứng viên cần thiết.

1. Khi biên trái dịch tới left, việc xóa các chỉ số < left ở front loại toàn bộ ứng viên hết hạn. Thứ tự chỉ số tăng dần bảo đảm không có phần tử hết hạn nằm ẩn ở phía sau một phần tử hợp lệ.
2. Với phần tử mới a[r], mọi chỉ số bị xóa ở back đều có giá trị <= a[r]. Phần tử mới xuất hiện muộn hơn, tồn tại trong mọi cửa sổ tương lai còn chứa chỉ số cũ, và có giá trị không nhỏ hơn. Vì thế những chỉ số bị xóa không cần thiết để xác định max tương lai.
3. Thêm r ở back duy trì chỉ số tăng dần. Những ứng viên còn lại ở back trước khi thêm đều có giá trị > a[r], nên dãy giá trị trong deque giảm nghiêm ngặt.
4. Mọi phần tử còn trong cửa sổ hoặc nằm trong deque, hoặc đã bị một phần tử về sau có giá trị lớn hơn hoặc bằng thống trị. Trong các ứng viên chưa bị loại, giá trị tại front lớn nhất. Vì các phần tử bị loại không thể đánh bại ứng viên thống trị chúng, front là cực đại thật của cửa sổ.

Theo quy nạp, ở mỗi r >= k-1, giá trị a[Dmax.front] là max chính xác của cửa sổ [r-k+1,r]. Cơ chế đối xứng chứng minh a[Dmin.front] là min chính xác. Thuật toán trả một giá trị cho mỗi r từ k-1 tới n-1, nên không thiếu hoặc lặp cửa sổ.

## 8. Phân tích thời gian khấu hao và bộ nhớ

Hai vòng xóa ở mỗi bước có thể chạy nhiều lần. Trong trường hợp xấu nhất của **một bước**, phần tử rất lớn có thể xóa tới k ứng viên khỏi deque max, nên không thể tuyên bố mọi lần xử lý phần tử đều tốn O(1) trong trường hợp xấu nhất.

Tuy nhiên, xét **toàn bộ n bước**:

- Mỗi chỉ số được thêm **đúng một lần** vào mỗi deque.
- Khi một chỉ số đã bị xóa khỏi deque, nó **không bao giờ được thêm lại**.
- Vì vậy mỗi chỉ số bị xóa **tối đa một lần** (ở front hoặc back) trên mỗi deque.

Tổng số lần thêm là n và tổng số lần xóa không vượt n trên mỗi deque. Tổng phép kiểm tra và truy cập đầu deque có bậc O(n); đó là **phân tích khấu hao** (amortized analysis). Duy trì hai deque vẫn là O(n) thời gian, chỉ khác hệ số hằng.

Mỗi deque chỉ giữ các chỉ số còn trong cửa sổ hiện hành, nên chứa tối đa k phần tử: bộ nhớ phụ **O(k)**. Nếu trả hai mảng kết quả, mỗi mảng có n-k+1 phần tử, nên **bộ nhớ đầu ra** là \(\Theta(n-k+1)\) cho mỗi mảng. Tổng bộ nhớ ngoài đầu vào là \(O(k+n-k+1)=O(n)\), còn **bộ nhớ phụ riêng của thuật toán** là \(O(k)\).

Nếu xử lý trực tuyến, đưa từng kết quả cho một consumer và không lưu tất cả vào danh sách, thuật toán có thể giữ O(k) bộ nhớ làm việc (chưa kể nơi nhận và bộ đệm I/O). Đổi lại, toàn bộ n-k+1 giá trị cực trị vẫn phải được phát nếu đặc tả đòi đầy đủ.

## 9. Java 17+: chương trình tìm đồng thời min và max

Sử dụng **ArrayDeque<Integer>** của Java để lưu chỉ số. Hai deque được cập nhật ở mỗi vị trí r. Mảng kết quả có độ dài n-k+1 và chỉ ghi sau khi cửa sổ có đủ k phần tử.

Lưu mã sau thành tệp **SlidingWindowExtrema.java**:

~~~java
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.Objects;

public class SlidingWindowExtrema {
    record Result(int[] minimums, int[] maximums) {}

    static Result findExtrema(int[] a, int k) {
        Objects.requireNonNull(a, "array");
        if (k < 1 || k > a.length) {
            throw new IllegalArgumentException("k must be in [1, n]");
        }

        int n = a.length;
        int outputSize = n - k + 1;
        int[] minimums = new int[outputSize];
        int[] maximums = new int[outputSize];

        ArrayDeque<Integer> minDeque = new ArrayDeque<>();
        ArrayDeque<Integer> maxDeque = new ArrayDeque<>();

        for (int r = 0; r < n; r++) {
            int left = r - k + 1;

            // Remove indices outside this window.
            while (!minDeque.isEmpty() && minDeque.peekFirst() < left) {
                minDeque.removeFirst();
            }
            while (!maxDeque.isEmpty() && maxDeque.peekFirst() < left) {
                maxDeque.removeFirst();
            }

            // Increasing values for minimum.
            while (!minDeque.isEmpty() && a[minDeque.peekLast()] >= a[r]) {
                minDeque.removeLast();
            }

            // Decreasing values for maximum.
            while (!maxDeque.isEmpty() && a[maxDeque.peekLast()] <= a[r]) {
                maxDeque.removeLast();
            }

            minDeque.addLast(r);
            maxDeque.addLast(r);

            if (r >= k - 1) {
                int outputIndex = r - k + 1;
                minimums[outputIndex] = a[minDeque.peekFirst()];
                maximums[outputIndex] = a[maxDeque.peekFirst()];
            }
        }
        return new Result(minimums, maximums);
    }

    public static void main(String[] args) {
        int[] a = {4, 2, 12, 3, 8, 7, 9};
        int k = 3;
        Result result = findExtrema(a, k);

        System.out.println("Input: " + Arrays.toString(a));
        System.out.println("Window size: " + k);
        System.out.println("Minimums: " + Arrays.toString(result.minimums()));
        System.out.println("Maximums: " + Arrays.toString(result.maximums()));
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac SlidingWindowExtrema.java
java SlidingWindowExtrema
~~~

Kết quả chuẩn trên stdout:

~~~text
Input: [4, 2, 12, 3, 8, 7, 9]
Window size: 3
Minimums: [2, 2, 3, 3, 7]
Maximums: [12, 12, 12, 8, 9]
~~~

**Giải thích triển khai:**

- **peekFirst()** xem chỉ số ứng viên cực trị; lấy **a[index]** để đọc giá trị.
- **removeFirst()** loại chỉ số hết hạn, còn **removeLast()** loại ứng viên bị thống trị. Hai thao tác này có vai trò khác nhau.
- Deque min dùng điều kiện >=, deque max dùng <=. Vì vậy các giá trị còn lại trong từng deque lần lượt tăng hoặc giảm nghiêm ngặt.
- Khi r=k-1, cửa sổ đầu tiên vừa đủ k phần tử và vị trí đầu ra là 0. Khi r=n-1, vị trí đầu ra là n-k.
- Đoạn mã dùng **Objects.requireNonNull** để từ chối mảng null bằng NullPointerException; nếu k<1 hoặc k>n, ném IllegalArgumentException. Việc từ chối đầu vào không hợp lệ là lựa chọn hợp đồng của ví dụ.
- Vì dùng Integer để bao chỉ số kiểu int, ArrayDeque<Integer> có overhead đóng hộp và đối tượng. Nếu rất nhạy về RAM/GC, có thể cài deque bằng mảng int[] với hai con trỏ; độ phức tạp không đổi.

Phương thức **findExtrema** mất \(\Theta(n)\) thời gian và \(O(k)\) bộ nhớ phụ cho hai deque, cộng bộ nhớ kết quả \(\Theta(n-k+1)\) trên mỗi mảng. Với mỗi phần tử mới, chương trình xử lý cả min và max trong cùng một vòng duyệt.

## 10. Trường hợp biên phải kiểm tra

| Trường hợp | Kết quả hoặc quy tắc |
|---|---|
| k = 1 | Mỗi cửa sổ chỉ có một phần tử, nên min = max = phần tử đó; kết quả bằng dãy gốc |
| k = n | Chỉ có một cửa sổ; trả min và max của cả mảng |
| Toàn giá trị âm | Thuật toán vẫn chính xác vì dùng so sánh phần tử, không mặc định max khởi tạo bằng 0 |
| Nhiều phần tử bằng nhau | Giá trị cực trị không đổi; quy tắc < hay <= ảnh hưởng chỉ số được ưu tiên khi hòa |
| Dãy tăng | Deque max thường chỉ còn ứng viên mới nhất; deque min giữ các ứng viên còn hạn |
| Dãy giảm | Deque min thường chỉ còn ứng viên mới nhất; deque max giữ các ứng viên còn hạn |
| k = 0 hoặc k > n | Phải quy định xử lý; ví dụ Java ném IllegalArgumentException |
| Mảng rỗng | Không tồn tại k hợp lệ theo hợp đồng 1 <= k <= n ở ví dụ Java |
| Mảng null | Ví dụ Java phát sinh NullPointerException |
| Cửa sổ chưa đủ k phần tử | Chưa trả giá trị; nếu yêu cầu trả max/min của tiền tố ngắn hơn thì phải sửa đặc tả và điểm phát kết quả |

Một số bài toán yêu cầu trả **vị trí cực trị** chứ không chỉ giá trị. Deque đã có sẵn chỉ số; chỉ cần trả chỉ số ở front thay vì a[front] và áp dụng đúng quy tắc hòa ở phần 6.

Cửa sổ trong bài này trượt đều sang phải và không lấy lại những vị trí đã loại. Nếu cửa sổ có thể **mở rộng ngược về trái**, ứng viên đã xóa không thể tự khôi phục, vì thế không được áp dụng trực tiếp thuật toán này cho mọi loại truy vấn đoạn tùy ý.

Với cửa sổ theo **timestamp** thay vì số phần tử cố định, cách xác định phần tử hết hạn phải dựa vào thời gian. Nếu sự kiện tới không theo thứ tự thời gian, việc đơn giản thay chỉ số bằng timestamp có thể vi phạm giả thiết về thứ tự xử lý; cần thiết kế thêm cơ chế sắp xếp/buffer hoặc cấu trúc khác.

## 11. Khi nào nên dùng kỹ thuật khác?

| Yêu cầu | Gợi ý cấu trúc | Lý do |
|---|---|---|
| Max/min cho mọi cửa sổ cố định, dịch một chiều | **Monotonic deque** | O(n) toàn bộ, O(k) bộ nhớ phụ |
| Chỉ một cửa sổ có k phần tử | Quét trực tiếp | O(k), ngắn gọn hơn |
| Nhiều truy vấn min/max đoạn bất kỳ trên dãy bất biến | Sparse table/RMQ tĩnh | Tiền xử lý để truy vấn nhanh |
| Nhiều truy vấn và cập nhật giá trị | Segment tree | Cập nhật và truy vấn đoạn thường O(log n) |
| Trung vị hoặc phân vị trong cửa sổ | Heap có cân bằng, multiset, cấu trúc theo thứ tự | Min/max deque không duy trì thứ hạng giữa các phần tử |
| Muốn cực trị cùng một lúc ở luồng trực tuyến | Hai monotonic deque | Mỗi lần nhận phần tử cập nhật cả hai cực trị |

Không phải mọi bài toán “cửa sổ” đều giải bằng deque đơn điệu. Kỹ thuật này đặc biệt thích hợp cho **min/max** khi biên cửa sổ tiến theo một chiều. Với tổng cửa sổ, prefix sum hoặc cập nhật tổng trượt thường đơn giản hơn; với trung vị phải dùng cấu trúc quản lý thứ hạng.

## 12. Lỗi cài đặt hay gặp

1. **Chỉ lưu giá trị** mà không lưu chỉ số, nên khi có nhiều bản sao cùng giá trị không biết bản sao nào hết hạn.
2. **Sai dấu hết hạn:** xóa khi chỉ số < left; không xóa khi chỉ số = left vì nó vẫn nằm trong cửa sổ.
3. **Đảo dấu so sánh:** max loại các giá trị cuối <= giá trị mới; min loại các giá trị cuối >= giá trị mới.
4. **Chỉ xóa đầu trước mà không xóa đầu sau**, khiến deque không còn đơn điệu.
5. **Chỉ xóa đầu sau mà bỏ bước hết hạn**, khiến front có thể chỉ tới một phần tử đã ra khỏi cửa sổ.
6. **Phát kết quả trước r=k-1**, tạo các cửa sổ thiếu phần tử ngoài đặc tả.
7. **Nhầm O(k) thời gian của một lần xóa nhiều phần tử thành O(nk) tổng thời gian**, dù mỗi chỉ số chỉ bị xóa tối đa một lần.
8. **Báo O(k) là tổng RAM** dù chương trình còn trả hai mảng đầu ra dài n-k+1.
9. **Khẳng định front là vị trí trái nhất của max** khi dùng <= và các giá trị bằng nhau đã bị xóa.
10. **Bỏ qua tính hợp lệ của k**, có thể truy cập front của deque rỗng hoặc cấp phát kết quả sai kích thước.

## 13. Bài tập tự kiểm tra

**Bài 1.** Cho a = [-4, -2, -7, -1], k=2. Max của ba cửa sổ là gì?

**Đáp án:** [-2, -2, -1]. Cách khởi tạo cực đại bằng 0 sẽ cho kết quả sai với toàn số âm.

**Bài 2.** Với a = [5, 5, 4, 5], k=2, nếu cần **chỉ số trái nhất** của max, dùng dấu < hay <= khi loại phần tử ở đuôi deque max?

**Đáp án:** Dùng dấu **<** để giữ những phần tử có giá trị bằng nhau, nhờ đó front ưu tiên bản sao cũ nhất còn hợp lệ.

**Bài 3.** Một bước có thể xóa 100 chỉ số ở back. Vì sao tổng thời gian vẫn O(n)?

**Đáp án:** Mỗi chỉ số được thêm đúng một lần và chỉ có thể bị xóa một lần. Tổng số thao tác thêm/xóa trên n chỉ số vẫn tuyến tính.

**Bài 4.** Với k=n, deque có thể giữ bao nhiêu phần tử và mảng kết quả có bao nhiêu mục?

**Đáp án:** Deque tối đa n chỉ số, còn mỗi mảng kết quả chỉ có một mục vì n-k+1=1.

**Ghi nhớ:** Lưu **chỉ số** theo thứ tự tăng, xóa **front khi hết hạn**, xóa **back khi bị ứng viên mới thống trị**, rồi lấy min/max tại **front**. Ba bất biến đúng giúp mọi cửa sổ được xử lý trong **O(n) tổng thời gian, O(k) bộ nhớ phụ**.