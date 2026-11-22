# Sắp xếp nổi bọt và điều kiện dừng sớm

**Bubble sort (sắp xếp nổi bọt)** là thuật toán sắp xếp so sánh dựa trên việc quét dãy và **đổi chỗ hai phần tử kề nhau nếu chúng sai thứ tự**. Mỗi lượt quét đầy đủ đưa một phần tử lớn nhất của vùng chưa được cố định về phía cuối, giống như “nổi” lên đúng vị trí. Thuật toán đơn giản để học cách xây dựng **bất biến vòng lặp**, tính số phép so sánh/đổi chỗ và hiểu vì sao một điều kiện **dừng sớm khi không có lần đổi chỗ nào** có thể cải thiện thời gian trên dữ liệu gần như đã sắp xếp.

Trong thực tế, bubble sort thường **không phải thuật toán nên chọn để sắp xếp mảng lớn** vì thời gian trường hợp xấu nhất là `Θ(n²)`. Giá trị học tập của nó nằm ở lời giải có thể giải thích và kiểm chứng từng bước, tính ổn định, sắp xếp tại chỗ, cùng kỹ thuật theo dõi sự tiến triển để bỏ công việc không cần thiết.

## 1. Đặc tả bài toán và giả định

Input là mảng `a` gồm `n` phần tử, cần sắp xếp **tăng không giảm**:

```text
a[0] <= a[1] <= ... <= a[n-1]
```

Ta xét mảng `int[]` trong Java. Phần tử có thể âm, bằng nhau, đã sắp xếp hoặc đảo ngược hoàn toàn. Phương pháp mẫu **sửa trực tiếp mảng đầu vào**; nếu hợp đồng yêu cầu giữ nguyên input thì phải sao chép trước.

Định nghĩa các phép cơ bản:

- **Một lần so sánh:** kiểm tra cặp kề `a[i]` và `a[i+1]` bằng điều kiện `a[i] > a[i+1]`.
- **Một lần đổi chỗ (swap):** chỉ diễn ra khi `a[i] > a[i+1]`. Sau đổi chỗ, phần tử lớn hơn chuyển một vị trí sang **phải**.
- **Một lượt quét (pass):** đi từ trái sang phải qua các cặp kề trong vùng đang xử lý.
- **Đuôi đã cố định:** sau mỗi lượt quét cần thiết, phần tử lớn nhất của vùng chưa cố định nằm ở cuối vùng đó. Các lượt tiếp theo không cần so sánh lại phần tử đã cố định ở phía phải.

Với `n=0` hoặc `n=1`, dãy đã sắp: **không cần so sánh, không cần đổi chỗ**.

Hai ký hiệu khác nhau cần phân biệt: `O(n²)` mô tả **cận tăng trưởng thời gian**; `n(n−1)/2` là **số so sánh chính xác** của bản bubble chuẩn chạy đủ `n−1` lượt theo độ dài giảm dần, bất kể dữ liệu.

## 2. Quan sát một lượt “nổi bọt”

Cho mảng ban đầu:

```text
[5, 1, 4, 2, 8]
```

Quét từ trái sang phải và chỉ đổi chỗ khi cặp kề bị đảo thứ tự:

| Bước trong lượt 1 | Cặp kề so sánh | Kết quả |
| --- | --- | --- |
| 1 | `5 > 1` | Đổi → `[1, 5, 4, 2, 8]` |
| 2 | `5 > 4` | Đổi → `[1, 4, 5, 2, 8]` |
| 3 | `5 > 2` | Đổi → `[1, 4, 2, 5, 8]` |
| 4 | `5 > 8` sai | Không đổi → `[1, 4, 2, 5, 8]` |

Trong một lượt đầy đủ, phần tử lớn nhất của vùng chưa cố định bị đẩy dần qua các phần tử nhỏ hơn, cuối cùng ở **vị trí cuối vùng**. Ở ví dụ này `8` vốn đã ở cuối, nên vẫn đúng rằng sau lượt 1, phần tử ở cuối `8` là lớn nhất.

Các lượt tiếp theo chỉ xét phần bên trái của phần tử đã cố định:

| Lượt | Vùng so sánh | Mảng sau lượt | Số so sánh | Số đổi chỗ |
| --- | --- | --- | ---: | ---: |
| 1 | Chỉ số `0..4` | `[1, 4, 2, 5, 8]` | 4 | 3 |
| 2 | Chỉ số `0..3` | `[1, 2, 4, 5, 8]` | 3 | 1 |
| 3 | Chỉ số `0..2` | `[1, 2, 4, 5, 8]` | 2 | 0 → **dừng sớm** |

Tổng cho ví dụ: **9 lần so sánh, 4 lần đổi chỗ, 3 lượt quét**. Dãy đã được sắp xếp sau lượt 2, nhưng thuật toán không thể khẳng định phần còn lại có thứ tự chỉ từ việc đã có một số lần đổi chỗ; lượt 3 **không có lần đổi chỗ nào** cung cấp chứng cứ để kết thúc ngay.

Nếu cứ chạy thêm cho đủ số lượt cố định, lượt thứ tư vẫn so sánh một cặp không cần thiết. Với mảng lớn đã gần có thứ tự, tiết kiệm bằng dừng sớm có thể đáng kể.

## 3. Thuật toán bubble sort chuẩn với dừng sớm

Dưới đây là lõi xử lý dành cho `int[] a`; `end` là chỉ số **cuối cùng của phần chưa cố định**, và `swapped` cho biết trong lượt hiện tại có đổi chỗ hay không:

```java
for (int end = a.length - 1; end > 0; end--) {
    boolean swapped = false;

    for (int i = 0; i < end; i++) {
        if (a[i] > a[i + 1]) {
            int temp = a[i];
            a[i] = a[i + 1];
            a[i + 1] = temp;
            swapped = true;
        }
    }

    if (!swapped) {
        break;
    }
}
```

*Đoạn trên là phần lõi thuật toán; chương trình Java đầy đủ có `main` ở mục 9.*

Quy tắc cập nhật:

1. Khởi đầu `end=n−1` vì chưa có đuôi được bảo đảm đã ở vị trí cuối.
2. Trong lượt, so sánh tất cả cặp `(i,i+1)` với `i=0..end−1`. Chỉ đổi khi `a[i]>a[i+1]`.
3. Sau lượt, `a[end]` là phần tử lớn nhất của đoạn `a[0..end]` đã xét. Do đó lần tiếp theo chỉ cần xét đến `end−1`.
4. Nếu cả lượt **không có bất kỳ swap nào**, các cặp kề trong đoạn đang xét đều đã thỏa `a[i]≤a[i+1]`. Kết hợp với đuôi đã cố định, **toàn mảng tăng không giảm** và có thể `break`.
5. Nếu `end` giảm đến `0`, phần tử cuối cùng còn lại mặc nhiên ở vị trí đúng. Không cần một lượt quét độ dài 0.

Biến `swapped` phải được đặt về **`false` ở đầu mỗi lượt**, không phải đặt một lần trước tất cả vòng lặp. Nếu quên reset, sau khi gặp swap ở lượt đầu, điều kiện dừng sớm có thể không bao giờ kích hoạt.

Dùng `>`, không dùng `>=`, để hai phần tử **bằng nhau** không bị đổi chỗ; đây là điều kiện then chốt cho tính **ổn định** của sắp xếp.

## 4. Chứng minh bubble sort đúng bằng bất biến vòng lặp

Để chứng minh tính đúng, không cần dựa vào hình ảnh “bọt nổi” mang tính trực giác. Ta cần mệnh đề bảo toàn sau mỗi lượt quét.

**Bất biến trước lượt có `end`:** Đoạn đuôi `a[end+1..n−1]` đã tăng không giảm, và **mọi phần tử trong đuôi đó lớn hơn hoặc bằng mọi phần tử còn ở `a[0..end]`**. Vì vậy các phần tử đuôi đã ở những vị trí cuối đúng của dãy đã sắp xếp.

**Khởi tạo:** Khi `end=n−1`, đoạn đuôi rỗng, nên bất biến hiển nhiên đúng.

**Bổ đề một lượt quét:** Sau khi so sánh/đổi chỗ liên tiếp các cặp `(0,1),(1,2),...,(end−1,end)`, giá trị ở `a[end]` bằng **giá trị lớn nhất vốn có trong `a[0..end]` ở đầu lượt**. Có thể chứng minh bằng quy nạp theo vị trí: sau khi xử lý cặp tới chỉ số `i`, phần tử ở `a[i+1]` là lớn nhất trong các phần tử ban đầu của tiền tố `a[0..i+1]`; phần tử lớn hơn luôn nằm bên phải cặp vừa xử lý.

**Duy trì:** Bổ đề cho thấy `a[end]` được đưa về đúng nhóm vị trí cuối của vùng chưa cố định. Đuôi cũ vốn đã tăng không giảm và không nhỏ hơn phần đang xử lý; khi thêm `a[end]` vào đầu đuôi, đuôi mới vẫn tăng không giảm và không nhỏ hơn mọi phần tử còn bên trái. Bất biến đúng ở lượt kế tiếp với `end−1`.

**Kết thúc thông thường:** Sau tối đa `n−1` lượt, chỉ còn một phần tử chưa cố định, và đuôi đã được bảo đảm ở các vị trí cuối. Mọi phần tử theo thứ tự tăng không giảm.

**Kết thúc sớm:** Nếu lượt không swap, với mọi `i=0..end−1` đã có `a[i]≤a[i+1]` tại thời điểm so sánh. Vì không swap ở bất kỳ bước nào, không phần tử nào đổi giá trị/vị trí suốt lượt, nên **toàn tiền tố `a[0..end]` tăng không giảm**. Bất biến cho biết đuôi bên phải cũng tăng không giảm và không nhỏ hơn tiền tố. Suy ra **toàn dãy đã sắp xếp**; `break` là an toàn.

**Tính kết thúc:** `end` giảm một đơn vị mỗi lượt, còn vòng trong có tối đa `end` lần so sánh; ngoài ra có thể thoát sớm. Số lượt hữu hạn với mọi `n≥0`.

Chứng minh này không phụ thuộc vào các giá trị cụ thể, nên áp dụng được cho phần tử âm, bằng nhau hay thứ tự ban đầu bất kỳ.

## 5. Điều kiện dừng sớm cải thiện trường hợp nào?

So sánh hai phiên bản:

- **Không dừng sớm:** Luôn chạy các lượt có `end=n−1,n−2,...,1`. Có đúng `(n−1)+(n−2)+...+1=n(n−1)/2` lần so sánh, dù dữ liệu ban đầu đã có thứ tự.
- **Có dừng sớm:** Sau mỗi lượt, nếu không swap thì thoát. Với input đã tăng không giảm, chỉ cần **một lượt gồm `n−1` phép so sánh** khi `n≥2`; với `n≤1` là 0. Trường hợp xấu nhất vẫn `n(n−1)/2` so sánh, chẳng hạn mảng giảm dần toàn phần tử phân biệt.

Ví dụ `[1,2,3,4,5]`: một lượt so sánh bốn cặp, không swap, dừng ngay. Từ `Θ(n²)` của bản cố định số lượt, **trường hợp tốt nhất** của bản dừng sớm trở thành `Θ(n)` khi `n≥2`.

Ví dụ `[2,1,3,4,5]`: lượt đầu đổi cặp `(2,1)` rồi tiếp tục kiểm tra các cặp phía sau, được `[1,2,3,4,5]`. Vì đã xảy ra một swap, bản dừng sớm cơ bản **phải làm lượt thứ hai** để phát hiện không còn swap: tổng **7 so sánh, 1 swap, 2 lượt**. Đây là chỗ còn có thể cải tiến bằng cách ghi lại **vị trí swap cuối cùng**.

Dừng sớm không có nghĩa mỗi input “gần sắp xếp” đều chạy `O(n)`. Một phần tử rất nhỏ đứng gần cuối có thể cần nhiều lượt để dịch từng bước sang trái, khiến tổng phép so sánh vẫn bậc hai. Để kết luận, phải phân tích cấu trúc dữ liệu cụ thể, không chỉ đếm số vị trí sai ban đầu.

## 6. Tối ưu thêm: chỉ quét đến vị trí đổi chỗ cuối cùng

Trong một lượt từ trái sang phải, các cặp **phía sau vị trí swap cuối cùng** đều đã được so sánh mà **không cần đổi**, và chúng nằm trong vùng đã được kiểm chứng đúng thứ tự. Ta có thể thu nhỏ giới hạn quét mạnh hơn mức giảm một đơn vị.

Một cách triển khai dùng `bound` là **số phần tử của đoạn còn cần xem xét**; vòng trong so sánh cặp `a[i−1],a[i]` với `i` chạy từ `1` đến `bound−1`:

```java
int bound = a.length;
while (bound > 1) {
    int lastSwap = 1; // Nếu không swap: kết thúc ở bound = 1.

    for (int i = 1; i < bound; i++) {
        if (a[i - 1] > a[i]) {
            int temp = a[i - 1];
            a[i - 1] = a[i];
            a[i] = temp;
            lastSwap = i; // Chỉ số bên phải của cặp vừa đổi.
        }
    }

    bound = lastSwap;
}
```

*Đây là phần lõi minh họa; chương trình hoàn chỉnh bên dưới còn ghi số lượt và số phép so sánh.*

**Vì sao cập nhật `bound=lastSwap` là an toàn?** Tại cuối lượt, các vị trí ở **từ `lastSwap` trở về sau** đã nằm trong phần đuôi đúng thứ tự: từ swap cuối trở đi không còn cặp nào đảo thứ tự; giá trị di chuyển sang vị trí `lastSwap` là giá trị lớn nhất đã gặp trong tiền tố tới đó, và bất biến của phần đuôi cũ vẫn được giữ. Các cặp cần kiểm tra ở lượt sau chỉ có chỉ số bên phải `i<lastSwap`. Nếu không có swap nào, toàn vùng hiện tại đã tăng không giảm và đặt `bound=1` để kết thúc.

**Đặc biệt:** Không dùng `bound=lastSwap−1` trong đúng mẫu vòng này vì `bound` là **cận trên loại trừ** của chỉ số phải `i`. Giảm thêm một có thể bỏ cặp ở chỉ số phải `lastSwap−1` đang cần xử lý. Đừng trộn quy ước `i=0..end−1` của mẫu trước với `i=1..bound−1` của mẫu này.

Với `[2,1,3,4,5]`, swap cuối cùng (và duy nhất) xảy ra khi `i=1`. Sau lượt đầu, `lastSwap=1`, `bound=1`, vòng lặp dừng ngay: **4 so sánh, 1 swap, 1 lượt**. Bản chỉ dùng cờ `swapped` cần **7 so sánh**. Hai phiên bản đều sắp xếp đúng, đều ổn định, đều dùng `O(1)` bộ nhớ phụ. Tối ưu này không thay đổi mức **`Θ(n²)` trường hợp xấu nhất**.

## 7. Số phép so sánh, số swap và độ phức tạp

Gọi `n` là số phần tử:

| Thuộc tính | Bubble cố định số lượt | Bubble có dừng sớm | Bubble có vị trí swap cuối |
| --- | --- | --- | --- |
| Thời gian tốt nhất khi đã sắp | `Θ(n²)` nếu cố chạy đủ lượt | `Θ(n)` với `n≥2` | `Θ(n)` với `n≥2` |
| Thời gian xấu nhất | `Θ(n²)` | `Θ(n²)` | `Θ(n²)` |
| Số so sánh xấu nhất | `n(n−1)/2` | Không vượt `n(n−1)/2` | Không vượt `n(n−1)/2` |
| Bộ nhớ phụ cho mảng nguyên thủy tại chỗ | `O(1)` | `O(1)` | `O(1)` |
| Stable nếu chỉ swap khi `>` | Có | Có | Có |
| Có thay đổi thứ tự input | Có thể | Có thể | Có thể |

Với bản dừng sớm, **trường hợp tốt nhất** là một lượt `n−1` so sánh (khi `n≥2`). **Trường hợp xấu nhất** với input đảo ngược có `n(n−1)/2` so sánh và cũng có thể có đúng số swap đó. Dù có dừng sớm, mảng đảo ngược `[5,4,3,2,1]` vẫn cần `10` so sánh, `10` swap, `4` lượt.

### Mối liên hệ với số nghịch thế (inversions)

Một **nghịch thế** là cặp chỉ số `(i,j)` với `i<j` nhưng `a[i]>a[j]`. Dãy tăng không giảm có **0 nghịch thế**; dãy giảm dần gồm `n` giá trị phân biệt có tối đa `n(n−1)/2` nghịch thế.

Mỗi lần bubble đổi **một cặp kề đang nghịch thế**, số nghịch thế giảm **đúng 1**: thứ tự tương đối của đúng hai phần tử kề đó đổi, còn quan hệ vị trí giữa chúng với mọi phần tử khác không đổi. Vì thuật toán chỉ kết thúc khi hết nghịch thế, nên:

**Số swap thực hiện bằng đúng số nghịch thế của input ban đầu** (với điều kiện so sánh `>` và swap kề như trên), bất kể có dừng sớm hay thu hẹp theo swap cuối.

Ví dụ `[5,1,4,2,8]` có bốn nghịch thế: `(5,1)`, `(5,4)`, `(5,2)`, `(4,2)`, nên cần đúng **4 swap**; nó không phụ thuộc vào cách đếm số lượt quét. Đây là một cách kiểm tra triển khai: nếu code chỉ swap cặp kề bị đảo mà số swap khác số nghịch thế ban đầu, nhiều khả năng logic có lỗi.

Lưu ý **số so sánh** không đơn giản bằng số nghịch thế: phần tử cần được kiểm tra ngay cả khi không swap. Dãy đã sắp xếp có số nghịch thế 0 nhưng bản có dừng sớm vẫn cần `n−1` phép so sánh để xác nhận.

### Không nhầm “ít swap” với “ít thời gian”

Một input có rất ít nghịch thế có thể dẫn đến ít swap nhưng vẫn cần nhiều so sánh. Tối ưu `lastSwap` giúp cắt bớt vùng đã chắc chắn có thứ tự, nhưng bubble sort vẫn không có bảo đảm `O(n log n)` trên dữ liệu tổng quát.

Trong thực tế, với mảng đủ lớn nên cân nhắc `Arrays.sort` hoặc thuật toán khác được thiết kế phù hợp với kiểu dữ liệu, điều kiện stable, số phần tử và bộ nhớ. Bubble sort là lựa chọn tốt để **học bất biến và phân tích hoạt động**, hoặc cho các bộ dữ liệu rất nhỏ trong tình huống phù hợp.

## 8. Tính ổn định (stability) và quyền sửa input

Thuật toán sắp xếp **ổn định** nếu các phần tử có **khóa so sánh bằng nhau** giữ nguyên thứ tự tương đối. Điều này có ý nghĩa khi mỗi bản ghi có thêm thông tin khác ngoài khóa.

Ví dụ:

```text
Trước:  [(2,A), (1,X), (2,B), (1,Y)]
Sau:    [(1,X), (1,Y), (2,A), (2,B)]
```

Trong kết quả ổn định, hai bản ghi khóa `1` giữ thứ tự `X` trước `Y`; hai bản ghi khóa `2` giữ `A` trước `B`. Bubble sort dùng điều kiện **`left.key > right.key`** sẽ không bao giờ đổi trực tiếp hai khóa bằng nhau. Vì chỉ swap **kề nhau**, hai bản ghi có cùng khóa không thể vượt qua nhau mà không trực tiếp đổi chỗ; do đó thuật toán **ổn định**.

Nếu đổi điều kiện thành `>=`, phần tử có khóa bằng nhau cũng bị swap. Khi đó tính ổn định bị phá, số swap vô ích tăng và điều kiện “không swap thì dừng” có thể không xuất hiện dù dãy đã tăng không giảm.

**In-place:** Các ví dụ đầu tiên sửa trực tiếp `int[] a`: `O(1)` bộ nhớ phụ cho các biến chỉ số và biến tạm. Nếu caller cần giữ nguyên input, có thể làm:

```java
int[] copy = original.clone();
bubbleEarly(copy); // Hàm xử lý trên bản sao.
```

Bản sao mảng `int[]` một chiều cần `O(n)` thời gian và `O(n)` bộ nhớ; việc sort `copy` không đổi các phần tử của `original`. Mảng đối tượng chứa các đối tượng **mutable** đòi hỏi chú ý aliasing: `clone()` chỉ sao chép mảng chứa các tham chiếu, không sao chép sâu từng đối tượng.

## 9. Java 17+ — chương trình hoàn chỉnh có số đo và kiểm chứng

Chương trình **BubbleSortDemo.java** triển khai hai phiên bản dừng sớm, ví dụ stable trên bản ghi có nhãn và một phép kiểm tra với tất cả mảng độ dài từ 0 đến 6 tạo từ ba giá trị `−1,0,1`. Mỗi input được đối chiếu với `Arrays.sort` và được kiểm thêm rằng **số swap bằng số nghịch thế ban đầu**.

```java
import java.util.Arrays;

public class BubbleSortDemo {
    record Metrics(long comparisons, long swaps, int passes) {}

    // Sắp xếp trực tiếp mảng, dừng khi trọn một lượt không swap.
    static Metrics bubbleEarly(int[] a) {
        long comparisons = 0;
        long swaps = 0;
        int passes = 0;

        for (int end = a.length - 1; end > 0; end--) {
            boolean swapped = false;
            for (int i = 0; i < end; i++) {
                comparisons++;
                if (a[i] > a[i + 1]) {
                    int temp = a[i];
                    a[i] = a[i + 1];
                    a[i + 1] = temp;
                    swaps++;
                    swapped = true;
                }
            }
            passes++;
            if (!swapped) {
                break;
            }
        }

        return new Metrics(comparisons, swaps, passes);
    }

    // Tối ưu ranh giới theo chỉ số phải của swap cuối.
    static Metrics bubbleLastSwap(int[] a) {
        long comparisons = 0;
        long swaps = 0;
        int passes = 0;
        int bound = a.length;

        while (bound > 1) {
            int lastSwap = 1;
            for (int i = 1; i < bound; i++) {
                comparisons++;
                if (a[i - 1] > a[i]) {
                    int temp = a[i - 1];
                    a[i - 1] = a[i];
                    a[i] = temp;
                    swaps++;
                    lastSwap = i;
                }
            }
            passes++;
            bound = lastSwap;
        }

        return new Metrics(comparisons, swaps, passes);
    }

    record Tagged(int key, String tag) {
        @Override
        public String toString() {
            return key + ":" + tag;
        }
    }

    // Cố ý chỉ đổi khi key trái LỚN HƠN key phải.
    static void stableBubble(Tagged[] a) {
        for (int end = a.length - 1; end > 0; end--) {
            boolean swapped = false;
            for (int i = 0; i < end; i++) {
                if (a[i].key() > a[i + 1].key()) {
                    Tagged temp = a[i];
                    a[i] = a[i + 1];
                    a[i + 1] = temp;
                    swapped = true;
                }
            }
            if (!swapped) {
                break;
            }
        }
    }

    // Đếm số nghịch thế bằng cách trực tiếp, chỉ dùng trong test nhỏ.
    static long inversions(int[] a) {
        long result = 0;
        for (int i = 0; i < a.length; i++) {
            for (int j = i + 1; j < a.length; j++) {
                if (a[i] > a[j]) {
                    result++;
                }
            }
        }
        return result;
    }

    // Tổng 1+3+9+27+81+243+729 = 1093 mảng.
    static int checkSmallCases() {
        int variants = 1;
        int checked = 0;
        for (int n = 0; n <= 6; n++) {
            for (int encoded = 0; encoded < variants; encoded++) {
                int[] input = new int[n];
                int code = encoded;
                for (int i = 0; i < n; i++) {
                    input[i] = code % 3 - 1;
                    code /= 3;
                }

                int[] expected = input.clone();
                Arrays.sort(expected);
                long initialInversions = inversions(input);

                int[] a = input.clone();
                int[] b = input.clone();
                Metrics first = bubbleEarly(a);
                Metrics second = bubbleLastSwap(b);

                if (!Arrays.equals(a, expected)
                        || !Arrays.equals(b, expected)
                        || first.swaps() != initialInversions
                        || second.swaps() != initialInversions) {
                    throw new AssertionError(
                        "Failed for " + Arrays.toString(input));
                }
                checked++;
            }
            variants *= 3;
        }
        return checked;
    }

    public static void main(String[] args) {
        int[] sample = {5, 1, 4, 2, 8};
        Metrics sampleMetrics = bubbleEarly(sample);
        System.out.println("Sample: " + Arrays.toString(sample));
        System.out.println("Sample metrics: " + sampleMetrics);

        int[] sorted = {1, 2, 3, 4, 5};
        System.out.println("Already sorted: " + bubbleEarly(sorted));

        int[] reversed = {5, 4, 3, 2, 1};
        System.out.println("Reversed: " + bubbleEarly(reversed));

        int[] near = {2, 1, 3, 4, 5};
        int[] nearCopy = near.clone();
        Metrics basic = bubbleEarly(near);
        Metrics byLastSwap = bubbleLastSwap(nearCopy);
        System.out.println("Near, early stop: " + basic);
        System.out.println("Near, last swap: " + byLastSwap);

        Tagged[] tagged = {
            new Tagged(2, "A"),
            new Tagged(1, "X"),
            new Tagged(2, "B"),
            new Tagged(1, "Y")
        };
        stableBubble(tagged);
        System.out.println("Stable tagged: " + Arrays.toString(tagged));

        int[] original = {3, 1, 2};
        int[] copy = original.clone();
        bubbleEarly(copy);
        System.out.println("Original: " + Arrays.toString(original));
        System.out.println("Sorted copy: " + Arrays.toString(copy));

        System.out.println("Empty: " + bubbleEarly(new int[0]));
        System.out.println("Singleton: " + bubbleLastSwap(new int[]{42}));
        System.out.println("Small exhaustive check: OK ("
                           + checkSmallCases() + " arrays)");
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 BubbleSortDemo.java
java BubbleSortDemo
```

Stdout dự kiến:

```text
Sample: [1, 2, 4, 5, 8]
Sample metrics: Metrics[comparisons=9, swaps=4, passes=3]
Already sorted: Metrics[comparisons=4, swaps=0, passes=1]
Reversed: Metrics[comparisons=10, swaps=10, passes=4]
Near, early stop: Metrics[comparisons=7, swaps=1, passes=2]
Near, last swap: Metrics[comparisons=4, swaps=1, passes=1]
Stable tagged: [1:X, 1:Y, 2:A, 2:B]
Original: [3, 1, 2]
Sorted copy: [1, 2, 3]
Empty: Metrics[comparisons=0, swaps=0, passes=0]
Singleton: Metrics[comparisons=0, swaps=0, passes=0]
Small exhaustive check: OK (1093 arrays)
```

**Cách đọc chương trình:**

- `Metrics` được trả về sau khi sort, ghi lại **so sánh thực sự**, **swap thực sự** và **số lượt thực sự**; không suy ra các số này từ Big-O.
- Input `sample` có 4 nghịch thế, đúng bằng 4 swap, dù số so sánh là 9.
- Mảng đã tăng không giảm cần một lượt không swap; mảng đảo hoàn toàn cần đủ bốn lượt.
- Cả hai phiên bản đều trả mảng `[1,2,3,4,5]` cho input gần sắp xếp, nhưng phiên bản `lastSwap` bỏ được lượt kiểm tra cuối không cần thiết.
- Thứ tự nhãn `X` trước `Y` và `A` trước `B` cho thấy sort theo `key` là stable.
- Hàm `checkSmallCases` sinh `1+3+9+27+81+243+729=1.093` mảng khác nhau **theo dãy đầu vào** (có thể trùng sau khi sort), với độ dài 0 đến 6. So với `Arrays.sort` và phép đếm nghịch thế giúp phát hiện lỗi thuật toán hoặc lỗi thống kê.
- Dù kiểm thử nhiều trường hợp nhỏ, **chứng minh bằng bất biến** ở mục 4 vẫn là lý do tổng quát để tin tưởng tính đúng.

## 10. Những lỗi triển khai thường gặp

**Lỗi 1 — So sánh nhầm vùng đuôi.** Khi mảng dài `n`, lượt đầu có `end=n−1` và `i<end`; cặp cuối cần kiểm tra là `a[n−2]` với `a[n−1]`. Nếu dùng `i<=end` sẽ truy cập `a[end+1]` ngoài vùng; nếu dừng `i<end−1` ở lượt đầu sẽ bỏ sót cặp cuối.

**Lỗi 2 — Quên reset cờ `swapped`.** Cờ phải trở về `false` đầu **mỗi lượt**. Nếu chỉ khởi tạo một lần, sau swap đầu tiên sẽ không bao giờ thấy lượt sạch, mất tối ưu dừng sớm.

**Lỗi 3 — Đặt `break` sai vị trí.** Không được dừng ngay khi **một cặp không cần swap**, vì những cặp phía sau vẫn có thể sai thứ tự. Chỉ được dừng khi **cả lượt quét** không có swap.

**Lỗi 4 — Dùng `>=` để swap.** Hai phần tử có khóa bằng nhau bị đổi vô ích; với dữ liệu có nhãn, mất tính stable. Bản có dừng sớm còn có thể tiếp tục swap trên dãy chỉ gồm các giá trị giống nhau.

**Lỗi 5 — Hiểu nhầm “mỗi lượt cố định một phần tử”.** Điều này cho phép **giảm biên so sánh ở phía phải**; không cho phép tự ý bỏ các phần tử giữa mảng. Nếu đổi hướng quét, phần tử được cố định có thể ở phía **trái** và cần chứng minh bất biến lại.

**Lỗi 6 — Trộn hai quy ước chỉ số.** `end` trong bản đầu là chỉ số phải **bao gồm**; `bound` trong bản `lastSwap` là giới hạn **loại trừ** của chỉ số phải `i`. Copy công thức `bound=lastSwap−1` từ một mã khác có thể gây bỏ cặp cần xét.

**Lỗi 7 — Đếm sai số swap và so sánh.** So sánh được tính cả khi điều kiện `>` sai. Swap chỉ tính khi đổi chỗ thực sự. Với bubble chỉ swap cặp kề sai thứ tự, số swap đúng bằng số nghịch thế ban đầu, không bằng số lượt quét.

**Lỗi 8 — Quên hợp đồng sửa input.** `bubbleEarly(a)` trực tiếp thay đổi `a`. Nếu yêu cầu giữ input, truyền `a.clone()`, rồi tính cả chi phí sao chép. Nếu đối tượng có các trường mutable bên trong, một bản sao nông cần được xem xét thêm.

**Lỗi 9 — Đánh giá hiệu năng chỉ bằng ví dụ đã sắp.** Dừng sớm cho `Θ(n)` ở trường hợp tốt nhất nhưng **không đổi** trường hợp xấu nhất `Θ(n²)`. Phải thử cả dãy đảo ngược và các trường hợp cần nhiều lượt đưa phần tử nhỏ sang trái.

**Lỗi 10 — Dùng bubble sort cho mọi bài sort.** Nếu không có yêu cầu học thuật hoặc ràng buộc đặc biệt, nên chọn thuật toán/thư viện có hiệu quả tốt hơn ở quy mô lớn. Việc có tối ưu dừng sớm không biến bubble sort thành sắp xếp `O(n log n)`.

## 11. Bài tập tự luyện và hướng suy luận

**Bài 1 — Theo dõi trạng thái.** Với `[4,3,1,2]`, hãy ghi chính xác mảng sau từng lần swap, sau từng lượt và tổng số so sánh/swap ở bản dừng sớm. Chỉ rõ lượt nào chứng minh có thể dừng.

*Gợi ý:* Lượt đầu đưa `4` về cuối; lượt sau tiếp tục đưa phần tử lớn nhất còn lại về vị trí đúng. Khi đã sort xong, hãy xem có cần thêm lượt không swap hay vòng ngoài tự kết thúc.

**Bài 2 — Chứng minh bất biến.** Phát biểu bằng ký hiệu rằng đuôi `a[end+1..n−1]` đã tăng không giảm và chứa các giá trị cuối lớn nhất. Chứng minh sau một lượt quét, `a[end]` trở thành phần tử lớn nhất của đoạn chưa cố định.

**Bài 3 — Dừng sớm.** Giải thích vì sao “không swap trong **một phép so sánh**” chưa cho phép dừng, trong khi “không swap trong **cả lượt**” là đủ. Dùng một phản ví dụ nếu cần.

**Bài 4 — Swap cuối.** Với `[2,1,3,4,5,6]`, dự đoán số so sánh của bản `swapped` và bản `lastSwap`. Giải thích vì sao giới hạn vòng tiếp theo được tính theo **chỉ số bên phải** của swap cuối.

*Gợi ý:* Bản cơ bản làm `5+4=9` so sánh; bản tối ưu chỉ `5`.

**Bài 5 — Inversions.** Đếm nghịch thế của `[3,1,2,1]`, rồi dự đoán số swap của bubble sort dùng điều kiện `>`. Kiểm tra trực tiếp bằng mã và giải thích vì sao mỗi swap giảm đúng một nghịch thế.

**Bài 6 — Stability.** Dữ liệu `[(2,A),(1,X),(2,B),(1,Y)]` phải sắp theo khóa số và giữ thứ tự nhãn bằng khóa. Vì sao `>` bảo đảm kết quả stable còn `>=` không?

**Bài 7 — Chọn thuật toán.** Với mảng dài `1.000.000` có thể bị đảo ngược, vì sao thêm `swapped` chưa đủ để bubble sort thành lựa chọn phù hợp? Hãy so sánh trường hợp xấu `Θ(n²)` với hướng thuật toán `O(n log n)`.

## 12. Checklist để áp dụng và chứng minh đúng

Trước khi kết luận “bubble sort với dừng sớm đã đúng và đủ nhanh”, cần kiểm tra:

1. **Đặc tả:** Sắp tăng hay giảm; được phép sửa input không; cần stable nếu các phần tử có khóa bằng nhau không?
2. **Điều kiện swap:** Chỉ đổi khi cặp kề sai thứ tự (`>` với tăng dần); không đổi các khóa bằng nhau.
3. **Ranh giới:** Lượt quét xét đúng cặp kề trong vùng chưa cố định, không truy cập ngoài `a[n−1]`.
4. **Bất biến:** Sau mỗi lượt cần thiết, một phần tử lớn nhất của vùng chưa cố định nằm ở cuối và phần đuôi đã đúng vị trí.
5. **Dừng sớm:** Reset cờ mỗi lượt; chỉ `break` khi **cả lượt** không swap, hoặc thu nhỏ bằng **swap cuối** theo đúng quy ước chỉ số.
6. **Tính kết thúc:** Biên giảm, các vòng lặp hữu hạn, xử lý `n=0` và `n=1` không cần so sánh.
7. **Độ phức tạp:** Best `Θ(n)` với dừng sớm (`n≥2`), worst `Θ(n²)`, bộ nhớ phụ tại chỗ `O(1)`; tính thêm clone và output khi cần.
8. **Kiểm thử:** Mảng rỗng, một phần tử, đã tăng, đảo ngược, tất cả bằng nhau, có số âm, nhiều khóa bằng nhau có nhãn; đối chiếu với `Arrays.sort` và số nghịch thế.

**Tiêu chí hoàn thành:** Bạn có thể viết lại bubble sort có dừng sớm từ nguyên lý swap cặp kề, truy vết mảng và thống kê số so sánh/swap, giải thích **bằng bất biến** tại sao sau lượt không swap đã sắp xếp, chứng minh thuật toán stable khi chỉ swap với dấu `>` và hiểu giới hạn của việc tối ưu dừng sớm trước khi chọn thuật toán cho dữ liệu thật.
