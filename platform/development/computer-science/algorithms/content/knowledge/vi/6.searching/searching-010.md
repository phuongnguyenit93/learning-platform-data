# Tìm miền tìm kiếm bằng tăng gấp đôi (Exponential Search)

Khi muốn tìm một giá trị hoặc ngưỡng bằng **tìm kiếm nhị phân (binary search)**, ta thường cần biết trước **khoảng chỉ số hoặc khoảng giá trị có thể chứa đáp án**. Nếu cận trên chưa rõ, một cách xác định khoảng hiệu quả là **tăng gấp đôi cận thử**: kiểm tra các mốc `1, 2, 4, 8, 16, ...` cho đến khi vượt qua hoặc chạm đáp án, rồi mới tìm kiếm nhị phân trong khoảng vừa thu hẹp được.

Kỹ thuật này thường được gọi là **exponential search**, **doubling search** hoặc **tìm cận bằng tăng gấp đôi**. Đây là kỹ thuật *xác định miền tìm kiếm*, không phải phương pháp thử lần lượt mọi phần tử. Hai giai đoạn có vai trò khác nhau:

1. **Mở rộng (galloping/doubling):** tăng cận theo cấp số nhân để nhanh chóng bao được vị trí hoặc ngưỡng cần tìm.
2. **Thu hẹp (binary search):** dùng điều kiện thứ tự hoặc tính đơn điệu để xác định chính xác kết quả trong miền đã bao.

Ví dụ, cần tìm `46` trong dãy đã sắp:

```text
Chỉ số:  0   1   2   3   4   5   6   7   8    9    10
Giá trị: 2   5   9  14  21  31  46  64  85  110   143

Thử tăng gấp đôi chỉ số:
            1: a[1] = 5  < 46
            2: a[2] = 9  < 46
            4: a[4] = 21 < 46
            8: a[8] = 85 >= 46

Miền ứng viên sau pha mở rộng: [5, 8]
Tìm nhị phân trong [5, 8] → tìm được 46 tại chỉ số 6.
```

Ta không dò từng chỉ số `0,1,2,3,...`. Mỗi bước mở rộng nhân đôi tầm với, nên sau `k` lần mở rộng đã kiểm tra tới mốc khoảng `2^k`.

## 1. Vì sao cần tìm miền trước khi tìm chính xác?

Tìm kiếm nhị phân thông thường bắt đầu với một khoảng có sẵn, ví dụ `[0, n-1]` trên mảng dài `n`. Mỗi bước chia đôi khoảng nhờ biết dữ liệu đã có thứ tự. Nhưng có những tình huống ta **không biết cận trên gần đáp án**:

- Mảng đã sắp nhưng đáp án dự kiến ở gần đầu và ta muốn xác định một khoảng nhỏ trước khi tìm nhị phân.
- Kho chỉ mục hỗ trợ truy cập ngẫu nhiên mà độ dài hữu ích chưa biết ngay; cần kiểm tra giới hạn truy cập trước khi dùng chỉ số tăng gấp đôi.
- Bài toán tìm **ngưỡng nhỏ nhất** thỏa một điều kiện đơn điệu, như số đơn vị tài nguyên tối thiểu để đáp ứng yêu cầu, nhưng không có sẵn cận trên chặt.
- Một hàm kiểm tra `P(x)` chuyển từ **sai sang đúng** khi `x` tăng; ta có thể tăng `x` gấp đôi cho tới lúc lần đầu gặp một mốc đúng.

**Điều kiện quyết định là tính có thứ tự/đơn điệu.** Nếu không có cơ sở nào cho biết một kết quả kiểm tra cho phép loại toàn bộ phần nhỏ hơn hoặc lớn hơn, việc tăng gấp đôi rồi tìm nhị phân có thể trả sai.

Đặc biệt, **mảng đã sắp** và **hàm điều kiện đơn điệu** là hai biến thể liên quan nhưng có hợp đồng khác nhau: trong mảng ta đang tìm **một giá trị cụ thể**, còn trong bài toán ngưỡng ta thường tìm **vị trí đầu tiên làm điều kiện đúng**.

## 2. Exponential Search trên mảng đã sắp

**Bài toán.** Cho một mảng `a` được sắp **không giảm** (các giá trị bằng nhau được phép xuất hiện) và một giá trị `target`. Trả **một chỉ số bất kỳ** có `a[i] == target`; nếu không có thì trả `-1`. Các chỉ số bắt đầu từ `0`.

Giả sử `n=a.length`. Ta xử lý:

1. Nếu `n=0`, trả `-1`.
2. Nếu `a[0]==target`, trả `0` ngay. Nếu `a[0]>target`, trả `-1` vì dãy đã sắp và mọi phần tử còn lại không nhỏ hơn `a[0]`.
3. Bắt đầu với `probe=1` và `left=1`. Trong khi `probe<n` và `a[probe]<target`, ta biết chắc **mọi phần tử tới `probe` đều nhỏ hơn mục tiêu**. Vì vậy cập nhật `left=probe+1` rồi tăng `probe` gấp đôi.
4. Khi dừng, đặt `right=min(probe,n-1)`. Nếu `left>right` thì không còn ứng viên. Ngược lại, tìm nhị phân trong **khoảng chỉ số đóng** `[left,right]` và trả chỉ số tìm thấy hoặc `-1`.

### Vì sao mảng phải được sắp?

Nếu tại `probe=4` thấy `a[4]<target`, chỉ khi mảng không giảm mới suy được mọi giá trị ở chỉ số `0..4` cũng nhỏ hơn `target`. Chính suy luận này cho phép bỏ toàn bộ tiền tố thay vì kiểm tra từng phần tử.

Trong mảng chưa sắp, một giá trị ở chỉ số `4` nhỏ hơn `target` **không nói gì** về giá trị ở các vị trí trước đó. Khi ấy việc bỏ cả tiền tố là không hợp lệ. Nếu đầu vào chưa sắp, có thể sắp trước (và tính cả chi phí) hoặc chọn kỹ thuật phù hợp khác.

### Bất biến của giai đoạn mở rộng

Sau mỗi lần kiểm tra `a[probe]<target` và tăng `left=probe+1`, ta duy trì:

> Mọi chỉ số **nhỏ hơn `left`** đều không thể chứa `target`.

Ban đầu, sau khi đã xử lý phần tử `a[0]` và biết nó nhỏ hơn mục tiêu, `left=1` nên bất biến đúng. Khi gặp `a[probe]<target`, tính không giảm bảo đảm mọi vị trí tới `probe` nhỏ hơn mục tiêu; do đó cập nhật `left` không bỏ sót nghiệm.

Khi quá trình mở rộng dừng, có hai khả năng:

- **`probe<n` và `a[probe]>=target`:** nếu giá trị cần tìm tồn tại thì nó nằm trong `[left,probe]`. Bên trái `left` đã bị loại; bên phải `probe` không thể chứa một giá trị nhỏ hơn `a[probe]`. Nếu `a[probe]==target` thì chính mốc này đã là một nghiệm.
- **`probe>=n`:** đã vượt độ dài mảng; bên phải chỉ số `n-1` không tồn tại. Mọi nghiệm còn lại, nếu có, phải nằm trong `[left,n-1]`.

Sau đó, tìm nhị phân thông thường giữ bất biến rằng **nếu còn nghiệm, một nghiệm nằm trong đoạn đang xét**, và giảm độ dài đoạn đến khi tìm thấy hoặc rỗng.

### Trường hợp giá trị trùng nhau

Với `[1,3,3,3,5,8]` và `target=3`, thuật toán có thể trả chỉ số `1`, `2` hoặc `3` tùy cách nhị phân được cài đặt. Hợp đồng ở đây chỉ yêu cầu **một vị trí đúng**. Nếu đề yêu cầu **vị trí đầu tiên**, cần dùng biến thể **lower bound** trong miền chứa vị trí đầu tiên; không được mặc định hàm tìm một vị trí bất kỳ đáp ứng yêu cầu đó.

## 3. Tại sao phải kiểm tra giới hạn chỉ số và tràn số?

Các mốc `1,2,4,8,...` tăng rất nhanh. Nếu mảng có kích thước hữu hạn, không được truy cập `a[probe]` khi `probe>=n`. Trong Java, điều kiện:

```java
while (probe < a.length && a[(int) probe] < target) {
    // ...
}
```

có ý nghĩa vì toán tử `&&` đánh giá từ trái sang phải và **dừng sớm**: nếu `probe<a.length` sai, biểu thức truy cập mảng không được thực hiện.

Ta sử dụng `long probe` để phép nhân đôi không tràn `int` trước khi đối chiếu với chiều dài mảng. Trong lúc `probe<a.length` đúng, `probe` có giá trị nằm trong miền chỉ số `int` nên ép kiểu `(int)probe` là hợp lệ. Sau khi vượt độ dài, chỉ dùng `Math.min(probe, (long)n-1)` để kẹp về chỉ số cuối; không ép `probe` lớn hơn miền mảng thành chỉ số truy cập.

**Không dùng một chỉ số tăng mãi không giới hạn.** Nếu bài toán trên một miền số mà điều kiện có thể *không bao giờ đúng*, vòng nhân đôi vô hạn có thể không dừng; cần biết một cận tối đa hoặc có chứng minh rằng ngưỡng đúng chắc chắn tồn tại. Khi dùng kiểu số hữu hạn, cũng phải bảo vệ phép nhân đôi khỏi tràn số.

## 4. Ví dụ Java 17+: tìm giá trị và tìm ngưỡng

Chương trình dưới đây cho thấy hai ứng dụng độc lập của ý tưởng tăng gấp đôi:

- `exponentialSearch` tìm **một chỉ số** có giá trị bằng `target` trong mảng đã sắp không giảm.
- `firstTrueUpTo` tìm **số nguyên không âm nhỏ nhất `x`** thỏa `condition.test(x)` trên miền `[0,maxX]`, với điều kiện `condition` có dạng **sai...sai, đúng...đúng**.

`firstTrueUpTo` trả `-1` khi điều kiện không đúng ở bất kỳ số nào trong miền; tham số `maxX` là cận tối đa có thật, không phải lời hứa về một không gian vô hạn. Hai hàm đều không yêu cầu cấp thêm mảng.

Lưu chương trình đúng tên **`DoublingSearchDemo.java`**:

```java
import java.util.function.LongPredicate;

public final class DoublingSearchDemo {
    // Tiền điều kiện: a != null và đã sắp xếp không giảm.
    // Trả một chỉ số i có a[i] == target, hoặc -1.
    static int exponentialSearch(int[] a, int target) {
        if (a.length == 0) {
            return -1;
        }
        if (a[0] == target) {
            return 0;
        }
        if (a[0] > target) {
            return -1;
        }

        int left = 1;
        long probe = 1;

        // probe dùng long; chỉ ép về int sau khi biết probe < n.
        while (probe < a.length && a[(int) probe] < target) {
            left = (int) probe + 1;
            probe *= 2;
        }

        int right = (int) Math.min(probe, (long) a.length - 1);

        // Tìm nhị phân trong đoạn chỉ số đóng [left, right].
        while (left <= right) {
            int mid = left + (right - left) / 2;

            if (a[mid] == target) {
                return mid;
            }
            if (a[mid] < target) {
                left = mid + 1;
            } else {
                right = mid - 1;
            }
        }
        return -1;
    }

    // Tiền điều kiện: maxX >= 0; condition thuần (không tác dụng phụ)
    // và đơn điệu từ false sang true trên miền [0, maxX].
    // Trả ngưỡng đầu tiên thỏa điều kiện; -1 nếu không tồn tại.
    static long firstTrueUpTo(long maxX, LongPredicate condition) {
        if (maxX < 0) {
            throw new IllegalArgumentException("maxX must be >= 0");
        }
        if (condition.test(0)) {
            return 0;
        }
        if (maxX == 0) {
            return -1;
        }

        long lastFalse = 0;
        long high = 1;

        // Tăng cận nhanh nhưng không vượt maxX hoặc tràn long.
        while (high < maxX && !condition.test(high)) {
            lastFalse = high;
            high = high > maxX / 2 ? maxX : high * 2;
        }

        // Nếu điều kiện vẫn sai tại cận tối đa đã đạt,
        // thì không tồn tại ngưỡng đúng trong [0, maxX].
        if (!condition.test(high)) {
            return -1;
        }

        long low = lastFalse + 1;
        // Nhị phân để tìm vị trí đầu tiên đúng.
        while (low < high) {
            long mid = low + (high - low) / 2;
            if (condition.test(mid)) {
                high = mid;
            } else {
                low = mid + 1;
            }
        }
        return low;
    }

    public static void main(String[] args) {
        int[] values = {2, 5, 9, 14, 21, 31, 46, 64, 85, 110, 143};

        System.out.println("Tim 2: "
            + exponentialSearch(values, 2));
        System.out.println("Tim 46: "
            + exponentialSearch(values, 46));
        System.out.println("Tim 143: "
            + exponentialSearch(values, 143));
        System.out.println("Tim 32: "
            + exponentialSearch(values, 32));
        System.out.println("Tim 1: "
            + exponentialSearch(values, 1));
        System.out.println("Mang rong: "
            + exponentialSearch(new int[0], 10));

        System.out.println("Nguong dau tien >= 37: "
            + firstTrueUpTo(100, x -> x >= 37));
        System.out.println("Khong co trong [0,20]: "
            + firstTrueUpTo(20, x -> x >= 37));
        System.out.println("Dung ngay tai 0: "
            + firstTrueUpTo(100, x -> x >= 0));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac DoublingSearchDemo.java
java DoublingSearchDemo
```

Kết quả chuẩn:

```text
Tim 2: 0
Tim 46: 6
Tim 143: 10
Tim 32: -1
Tim 1: -1
Mang rong: -1
Nguong dau tien >= 37: 37
Khong co trong [0,20]: -1
Dung ngay tai 0: 0
```

### Giải thích đầu ra

- `2` là phần tử đầu tiên nên được trả về ngay ở chỉ số `0`.
- `46` nằm tại chỉ số `6` và được tìm trong miền `[5,8]` sau pha nhân đôi.
- `143` là phần tử cuối ở chỉ số `10`. Sau khi thử tới chỉ số `8` có giá trị `85` nhỏ hơn mục tiêu, `probe` tăng lên `16`, vượt `n=11`; miền còn lại là `[9,10]`.
- `32` nằm giữa `31` và `46` nhưng không tồn tại trong mảng; tìm nhị phân trong miền được bao trả `-1`. `1` nhỏ hơn phần tử đầu tiên nên cũng không tìm thấy.
- Với điều kiện `x>=37` trong `[0,100]`, các cận thử `1,2,4,8,16,32` đều sai, còn `64` đúng. Miền chắc chắn chứa ngưỡng đầu tiên là `[33,64]`; tìm nhị phân trả `37`.
- Nếu chỉ cho phép `x` tới `20` thì không tồn tại ngưỡng `37` trong miền, nên trả `-1`. Nếu điều kiện đúng ngay tại `0` thì trả `0`, không phải `1`.

**Lưu ý về hợp đồng:** mã giả định mảng khác `null` và được sắp không giảm; `firstTrueUpTo` giả định `condition` khác `null`, không có tác dụng phụ và đơn điệu. Nếu các điều kiện này không được bảo đảm thì phải kiểm tra/chuẩn hóa đầu vào hoặc thay thuật toán. Hai hàm dùng cận và phép so sánh chứ không tự xác minh mảng đã sắp hay điều kiện thật sự đơn điệu.

## 5. Tìm ngưỡng đầu tiên bằng tăng gấp đôi trên miền số

Đây là biến thể tổng quát rất hữu ích cho **tìm kiếm nhị phân trên đáp án (binary search on answer)**. Giả sử có hàm kiểm tra `P(x)` trên các số nguyên không âm, và khi tăng `x`, kết quả chuyển nhiều nhất một lần từ **false** sang **true**:

```text
x:     0  1  2  3 ... 35 36 | 37 38 39 ... maxX
P(x):  F  F  F  F ...  F  F |  T  T  T ...  T
                              ^
                          ngưỡng cần tìm
```

Ta cần giá trị **nhỏ nhất** `x` sao cho `P(x)` đúng, không chỉ là một giá trị đúng bất kỳ. Tăng `x` gấp đôi cho tới khi gặp một mốc có `P(x)=true`:

```text
Kiểm tra 0: false
Kiểm tra 1: false
Kiểm tra 2: false
Kiểm tra 4: false
Kiểm tra 8: false
Kiểm tra 16: false
Kiểm tra 32: false
Kiểm tra 64: true

Biết chắc: mọi x <= 32 đều sai; 64 đã đúng.
Tìm nhị phân "first true" trong [33, 64] → 37.
```

### Bất biến và chứng minh cho biến thể tìm ngưỡng

Khi đã xác nhận `P(0)=false`, đặt `lastFalse=0`. Mỗi lần kiểm tra `P(high)=false`, tính đơn điệu bảo đảm **mọi `x<=high` đều sai**, nên có thể gán `lastFalse=high` rồi tăng cận.

Khi gặp `P(high)=true`, ta biết:

- Mọi giá trị `x<=lastFalse` đều sai.
- `high` là một vị trí đã đúng.
- Vậy **ngưỡng đúng đầu tiên (nếu có) nằm trong `[lastFalse+1,high]`**.

Trong vòng nhị phân, đặt `low=lastFalse+1`, giữ `high` là một cận đúng. Với `mid`:

- Nếu `P(mid)=true`, ngưỡng không thể lớn hơn `mid`; đặt `high=mid`.
- Nếu `P(mid)=false`, ngưỡng phải lớn hơn `mid`; đặt `low=mid+1`.

Khi `low==high`, đó là **giá trị đúng đầu tiên**. Đây chính là mẫu **lower bound trên điều kiện đơn điệu**, không phải tìm một giá trị bằng nhau trong mảng.

### Khi ngưỡng không tồn tại

Nếu `P(maxX)=false` và `P` đơn điệu false→true, mọi giá trị nhỏ hơn cũng sai; không có đáp án trong miền. Hàm trả `-1`. Nếu không có cận trên `maxX` và điều kiện có thể sai mãi mãi, việc cứ nhân đôi `high` sẽ không kết thúc. Vì vậy, với không gian vô hạn, phải có **giả thiết toán học bảo đảm sớm muộn tồn tại giá trị đúng**, hoặc phải đặt giới hạn tìm kiếm thực tế.

Trong ví dụ Java, `high = high > maxX/2 ? maxX : high*2` tránh tràn `long` và bảo đảm không vượt miền. Sau đó, phép tìm trung điểm `low+(high-low)/2` cũng tránh cộng trực tiếp `low+high` khi hai cận rất lớn.

### Điều kiện đơn điệu phải được chứng minh, không được đoán

Ví dụ, nếu `P(x)` là “với `x` nhân viên, có thể hoàn thành tất cả công việc trước thời hạn” và tăng số nhân viên không làm mất năng lực làm việc, `P` có thể đơn điệu từ sai sang đúng. Nhưng nếu `P(x)` là “số chi phí chính xác bằng ngân sách”, điều kiện có thể đúng ở vài giá trị rời rạc rồi lại sai; tìm `firstTrue` kiểu trên không hợp lệ.

Hơn nữa, mỗi lần `P(x)` có thể là một phép tính tốn kém. Nếu một lần kiểm tra `P` cần `T(n)` thời gian, tổng thời gian phải tính thêm chi phí đó, không thể gọi cả thuật toán là `O(log x)` bất kể hàm kiểm tra làm gì.

## 6. Độ phức tạp: tìm được miền nhanh đến đâu?

Giả sử vị trí đầu tiên có thể đạt mục tiêu (hoặc vị trí chèn của `target` trong mảng đã sắp) là `p`, đánh số từ `0`. Pha tăng gấp đôi thử các cận `1,2,4,...` và chỉ cần khoảng `O(log(p+1))` phép kiểm tra để tiến tới hoặc vượt `p`.

Khi dừng, miền còn lại có kích thước cùng bậc với `p+1`, nên tìm nhị phân thêm `O(log(p+1))` bước. Hai giai đoạn cộng lại vẫn là **`O(log(p+1))` phép kiểm tra**, ngoại trừ các trường hợp đầu vào quá nhỏ được xử lý hằng số.

Với mảng hữu hạn dài `n`, trường hợp xấu nhất là **`O(log n)`** nếu `n>=2`, giống bậc của tìm nhị phân thông thường. Nếu `target` có mặt rất gần đầu, số phép kiểm tra có thể gắn với `p` hơn là `n`, dù **không bảo đảm luôn nhanh hơn** tìm nhị phân trên toàn mảng do hệ số hằng và số lần đọc thực tế.

| Công việc | Số bước xét ở mức tiệm cận | Bộ nhớ phụ |
|---|---|---|
| Mở rộng cận bằng nhân đôi | `O(log(p+1))` nếu vị trí/ranh giới cần vượt là `p` | `O(1)` |
| Tìm nhị phân trong miền vừa xác định | `O(log(p+1))` | `O(1)` với bản lặp |
| Toàn bộ tìm kiếm trên mảng đã sắp dài `n` | `O(log n)` ở trường hợp xấu nhất | `O(1)` |
| Tìm ngưỡng đầu tiên với `P(x)` có giá thành `T` mỗi lần | `O(log(q+1))` lần kiểm tra nếu ngưỡng ở `q` | `O(1)` ngoài bộ nhớ mà `P` sử dụng |

Nếu không có đáp án, số lần kiểm tra tối đa phụ thuộc **cận hữu hạn thực tế**: với mảng dài `n` là `O(log n)`; với miền `[0,maxX]` là `O(log(maxX+1))`. Cần lưu ý rằng số lượt gọi điều kiện và **thời gian chạy thực** khác nhau khi kiểm tra `P` tốn kém.

### Vì sao không phải `O(p)` hay `O(n)`?

Cách quét tuần tự đến `p` phải thử gần `p` vị trí. Tăng gấp đôi đi qua `1,2,4,...,2^k`, nên số mốc là khoảng `k` với `2^k≈p`, tức `k≈log₂p`. Sau đó, tìm nhị phân chia đôi miền mỗi bước. Tổng hai số logarit vẫn cùng bậc logarit.

Tuy nhiên, điều này dựa trên **khả năng truy cập ngẫu nhiên tới mốc `2^k` với chi phí phù hợp**. Nếu dữ liệu là luồng chỉ được duyệt tuần tự từ đầu, muốn chạm mốc lớn hơn có thể phải đọc mọi phần tử trung gian; tổng chi phí có thể khác phân tích trên. Đừng giả định “dãy vô hạn” đồng nghĩa có thể truy cập `a[2^k]` trong `O(1)`.

## 7. Khi nào dùng và khi nào không?

**Phù hợp:**

- Có thứ tự hoặc một hàm kiểm tra đơn điệu và cần tìm **ngưỡng/cận** trước khi thu hẹp bằng nhị phân.
- Có thể kiểm tra các mốc `1,2,4,...` mà không duyệt tuần tự toàn bộ khoảng đã nhảy qua.
- Chưa biết cận trên chặt, hoặc muốn tìm một khoảng gần nơi đáp án xuất hiện.
- Bài toán có nhiều lần kiểm tra và vị trí ngưỡng thường gần đầu, trong khi miền tối đa có thể rất lớn.

**Không nên áp dụng máy móc:**

- Mảng chưa sắp nhưng vẫn dùng lập luận “mốc này nhỏ, mọi vị trí trước cũng nhỏ”.
- Điều kiện `P(x)` không đơn điệu, ví dụ đúng–sai–đúng xen kẽ.
- Phép thử `P(x)` có tác dụng phụ làm lần kiểm tra sau phụ thuộc lần trước; chứng minh tìm kiếm có thể mất hiệu lực.
- Không có cận tối đa, cũng không có bảo đảm về sự tồn tại của một vị trí đúng; vòng mở rộng có thể không dừng.
- Dữ liệu chỉ có thể đọc tuần tự, nên các bước “nhảy cóc” thật ra vẫn phải duyệt mọi phần tử.
- Bài toán cần **toàn bộ các chỉ số** hay **vị trí đầu tiên trong số nhiều giá trị trùng**; hàm tìm một chỉ số bất kỳ chỉ đáp ứng hợp đồng hẹp hơn.

Nếu đã biết `n` và chỉ cần tìm một phần tử bất kỳ trong mảng đã sắp, tìm nhị phân trực tiếp thường là cách ngắn gọn và dễ duy trì. Tăng gấp đôi hữu ích khi việc **tự xác định cận** là một phần thực chất của bài toán.

## 8. Các lỗi phổ biến và cách tránh

| Lỗi | Vì sao sai | Cách xử lý |
|---|---|---|
| Bắt đầu với cận `0` rồi liên tục nhân đôi | `0*2=0`, không mở rộng được | Kiểm tra vị trí `0` riêng, bắt đầu `probe=1` |
| Đọc `a[probe]` trước khi kiểm tra `probe<n` | Có thể ném `ArrayIndexOutOfBoundsException` | Kiểm tra giới hạn trước khi truy cập, dùng đánh giá ngắn mạch của `&&` |
| Dùng `int probe` và cứ `probe*=2` không kiểm soát | Có thể tràn số nguyên và tạo chỉ số âm | Dùng `long` hoặc kẹp cận trước nhân đôi |
| Nhầm khoảng đóng và nửa mở | Lệch cận, bỏ sót phần tử đầu/cuối | Viết rõ `[left,right]` và điều kiện `left<=right` |
| Không nhớ mốc cuối đã xác nhận “quá nhỏ” | Mở rộng xong nhưng thu hẹp sai miền | Lưu `left` hoặc `lastFalse` sau mỗi lần loại tiền tố |
| Gọi tìm nhị phân trên mảng chưa sắp | Loại ứng viên sai | Xác nhận thứ tự trước, hoặc dùng phương pháp khác |
| Tìm một phần tử bất kỳ nhưng công bố “vị trí đầu tiên” | Có thể sai khi tồn tại bản sao | Đổi pha nhị phân sang lower bound rồi kiểm tra bằng nhau |
| Điều kiện ngưỡng không đơn điệu | Không có bất biến bảo toàn cận đầu tiên | Chứng minh tính đơn điệu từ hợp đồng bài toán |
| Không có cận hay tiêu chí dừng | Có thể lặp mãi nếu điều kiện không bao giờ đúng | Đặt `maxX` hoặc chứng minh tồn tại ngưỡng |
| Thực hiện phép toán bên trong `P(x)` có thể tràn số | Kiểm tra trả sai dù logic tìm kiếm đúng | Phân tích miền số trung gian, dùng kiểu đủ lớn hoặc biến đổi so sánh an toàn |

### Kiểm thử trường hợp biên

Với biến thể mảng đã sắp, nên kiểm tra: mảng rỗng, một phần tử, tìm phần tử đầu/cuối, số nhỏ hơn phần tử đầu, số lớn hơn phần tử cuối, số nằm giữa nhưng không tồn tại, dãy có số âm, dãy toàn giá trị trùng và phần tử ở gần mốc `2^k`.

Với biến thể ngưỡng, nên kiểm tra: `maxX=0`, điều kiện đúng ngay ở `0`, đúng đầu tiên tại `1` hoặc tại `maxX`, đúng đầu tiên tại một mốc `2^k`, và **không có bất cứ giá trị nào đúng**. Có thể đối chiếu trên miền nhỏ bằng một vòng lặp tuần tự để tìm ngưỡng nhỏ nhất, sau đó so với kết quả nhân đôi + nhị phân.

Kiểm thử ngẫu nhiên là công cụ phát hiện lỗi trong cài đặt; **chứng minh bất biến và tính đơn điệu** mới là cơ sở đảm bảo đúng cho mọi đầu vào hợp lệ.

## 9. Bài tập tự luyện

**Bài 1 — Xác định miền.** Cho mảng đã sắp `[1,4,7,10,13,16,20,25,31]` và `target=20`. Hãy liệt kê các chỉ số thử theo lũy thừa của `2`, miền nhị phân cuối cùng và kết quả.

*Đáp án đối chiếu:* thử `1` (giá trị 4), `2` (7), `4` (13), `8` (31); cả ba mốc đầu nhỏ hơn 20, nên miền còn lại `[5,8]`. Tìm nhị phân trả chỉ số `6`.

**Bài 2 — Ngưỡng đầu tiên.** Điều kiện `P(x)=(x>=37)` trên `[0,100]`. Sau khi thử các cận `1,2,4,8,16,32,64`, miền chứa ngưỡng đầu tiên là gì? Vì sao không cần xét `0..32`?

*Đáp án:* `[33,64]`; vì `P(32)=false` và điều kiện đơn điệu, mọi số nhỏ hơn `32` cũng sai.

**Bài 3 — Không có đáp án.** Mảng đã sắp `[2,5,8,11,14]`, tìm `99`. Mốc nhân đôi đầu tiên vượt chiều dài là bao nhiêu; miền nào còn phải kiểm tra?

*Đáp án:* thử `1`, `2`, `4` rồi nhân đôi thành `8>=5`; sau lần thử chỉ số `4` với giá trị `14<99`, ta có `left=5`, `right=4` nên miền rỗng và trả `-1`.

**Bài 4 — Phản ví dụ.** Tại sao mảng `[1,100,2,3,50]` không thể dùng quy tắc “mốc có giá trị nhỏ hơn mục tiêu thì loại mọi vị trí trước đó” khi tìm `100`?

*Gợi ý:* mảng không được sắp; một giá trị nhỏ ở mốc muộn không bảo đảm các giá trị trước cũng nhỏ. Lập luận loại tiền tố bị phá vỡ.

**Bài 5 — Thiết kế điều kiện.** Một quy trình cho phép cấp tối đa `maxX` đơn vị tài nguyên. Hãy định nghĩa `P(x)` là “với `x` đơn vị, công việc hoàn thành trước hạn”. Điều kiện nào về bài toán thực tế cần đúng để tìm lượng tài nguyên tối thiểu bằng phương pháp nhân đôi + nhị phân?

*Gợi ý:* thêm tài nguyên không được khiến một phương án trước đó khả thi trở thành bất khả thi; kiểm tra `P(x)` phải đáng tin, không phụ thuộc lịch sử kiểm tra, và phải có cận trên hữu hạn hoặc bảo đảm tồn tại nghiệm.

## Ghi nhớ

**Tìm miền bằng tăng gấp đôi = tìm một cận đủ xa bằng `1,2,4,8,...` rồi dùng tìm kiếm nhị phân để xác định đáp án.** Trên mảng đã sắp, cần chắc chắn mọi vị trí đã loại không thể chứa `target`. Trên miền số, cần chứng minh điều kiện chuyển đơn điệu từ **sai sang đúng** và giữ một cận sai cùng một cận đúng. Đừng quên giới hạn mảng, tràn số, trường hợp không có nghiệm và chi phí thực của mỗi lần kiểm tra. Khi các điều kiện được đáp ứng, kỹ thuật có thể tìm đáp án sau số phép kiểm tra bậc **logarit**.
