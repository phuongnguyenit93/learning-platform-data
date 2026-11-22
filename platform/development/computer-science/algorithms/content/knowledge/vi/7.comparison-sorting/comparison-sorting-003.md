# Sắp xếp chọn (Selection Sort)

**Sắp xếp chọn** (*selection sort*) là một thuật toán sắp xếp dựa trên so sánh. Thay vì cố sắp xếp tất cả phần tử cùng lúc, thuật toán lần lượt **tìm phần tử nhỏ nhất trong phần chưa sắp xếp**, rồi đưa nó về đúng vị trí tiếp theo ở đầu mảng. Sau mỗi lượt, phần đầu mảng trở thành một đoạn đã sắp xếp dài hơn một phần tử.

Selection sort dễ mô phỏng bằng tay, dễ chứng minh tính đúng và có số lần **hoán đổi** tương đối ít. Đổi lại, nó luôn thực hiện số lượng so sánh bậc hai, kể cả khi mảng đầu vào đã có thứ tự. Vì vậy đây là thuật toán quan trọng để hiểu tư duy chọn phần tử, bất biến vòng lặp và phân tích độ phức tạp, nhưng hiếm khi là phương án tối ưu cho mảng lớn trong thực tế.

## 1. Đặc tả bài toán và ý tưởng cốt lõi

**Đầu vào:** một mảng a gồm n số nguyên, có thể rỗng; các giá trị có thể âm, dương, bằng nhau và nằm ở hai cực trị của kiểu int.

**Đầu ra:** chính mảng a được sắp xếp **không giảm**:

~~~text
a[0] <= a[1] <= ... <= a[n-1]
~~~

Kết quả còn phải là **một hoán vị của mảng gốc**: không được thêm, làm mất hoặc thay đổi số lần xuất hiện của bất kỳ giá trị nào. Ví dụ [3, 1, 3, 2] phải thành [1, 2, 3, 3], chứ không phải [1, 2, 3] vì bản sau đã làm mất một số 3.

Trong bài học, phiên bản chuẩn của selection sort:
- Đánh chỉ số từ **0**.
- Sắp xếp **tăng dần/không giảm**.
- Thao tác **ngay trên mảng được truyền vào** (*in-place*); không tạo thêm mảng kết quả.
- Chọn vị trí của phần tử nhỏ nhất bằng so sánh **<**, không ưu tiên phần tử bằng nhau đến sau.
- Chỉ hoán đổi nếu chỉ số phần tử nhỏ nhất khác vị trí đang xét.

Phần chưa sắp xếp ban đầu là toàn bộ [0, n). Ở lượt i, tìm phần tử nhỏ nhất trong **đoạn [i, n)** rồi đưa về a[i]. Như vậy [0, i] trở thành đoạn đã xếp đúng sau lượt i.

**Phân biệt quan trọng:** “chọn phần tử nhỏ nhất mỗi lượt” trong selection sort là một chiến lược cụ thể để **sắp xếp toàn bộ mảng**. Nó không đồng nghĩa với bài toán tìm phần tử nhỏ thứ k (*selection problem*) hoặc thuật toán quickselect, nơi mục tiêu thường chỉ là xác định một vị trí thứ tự.

## 2. Quy trình từng lượt và giả mã

Thuật toán sử dụng hai vòng lặp lồng nhau:

1. Với i chạy từ 0 đến n − 2, coi i là vị trí tiếp theo cần cố định.
2. Đặt minIndex = i, giả định a[i] đang nhỏ nhất ở phần chưa sắp.
3. Duyệt j từ i + 1 đến n − 1. Nếu a[j] < a[minIndex], cập nhật minIndex = j.
4. Sau khi duyệt xong, a[minIndex] thực sự là giá trị nhỏ nhất trong đoạn [i, n).
5. Nếu minIndex khác i, đổi chỗ a[i] và a[minIndex].
6. Tiếp tục sang i + 1. Không cần một lượt riêng cho phần tử cuối: khi n − 1 phần tử đầu đã đúng, phần còn lại cũng phải đúng.

Giả mã:

~~~text
selectionSort(a):
    n = length(a)

    for i = 0 .. n - 2:
        minIndex = i

        for j = i + 1 .. n - 1:
            if a[j] < a[minIndex]:
                minIndex = j

        if minIndex != i:
            temp = a[i]
            a[i] = a[minIndex]
            a[minIndex] = temp
~~~

Các khoảng của vòng for ở đây bao gồm cả hai cận khi còn hợp lệ; với n = 0 hoặc n = 1, vòng ngoài không chạy. Không được đổi chỗ ngay khi vừa tìm thấy một phần tử nhỏ hơn: phải **quét xong toàn bộ đoạn chưa sắp** rồi mới biết đâu là phần tử nhỏ nhất.

### Tại sao chỉ cần một lần đổi chỗ mỗi lượt?

Sau khi đã biết minIndex, một lần đổi chỗ đặt giá trị nhỏ nhất ở đúng vị trí i. Phần tử cũ tại i chuyển đến minIndex, vẫn nằm trong phần chưa sắp; nó sẽ được xử lý ở các lượt tiếp theo. Không cần liên tục dịch chuyển các phần tử như một số cách cài insertion sort.

Khi minIndex = i, a[i] đã là phần tử nhỏ nhất của đoạn còn lại. Nếu không yêu cầu một thao tác “swap với chính mình” cho mục đích trình diễn, nên bỏ qua hoán đổi không cần thiết.

## 3. Ví dụ chi tiết: theo dõi toàn bộ mảng

Xét mảng:

~~~text
[64, 25, 12, 22, 11]
~~~

Mục tiêu là sắp xếp tăng dần. Mỗi lượt tìm min trong đoạn chưa sắp rồi đưa về đầu đoạn đó.

| Lượt i | Phần đã cố định trước lượt | Đoạn tìm min | minIndex, min | Mảng sau lượt |
| --- | --- | --- | --- | --- |
| 0 | Rỗng | [64,25,12,22,11] | 4, 11 | [11,25,12,22,64] |
| 1 | [11] | [25,12,22,64] | 2, 12 | [11,12,25,22,64] |
| 2 | [11,12] | [25,22,64] | 3, 22 | [11,12,22,25,64] |
| 3 | [11,12,22] | [25,64] | 3, 25 | [11,12,22,25,64] |

**Lượt 0:** trong cả mảng, số nhỏ nhất là 11 ở chỉ số 4. Đổi a[0] = 64 và a[4] = 11. Kết quả [11, 25, 12, 22, 64]. Giá trị 11 từ đây không bị đụng đến nữa.

**Lượt 1:** chỉ xét các chỉ số 1..4; số nhỏ nhất là 12 ở chỉ số 2. Đổi 25 và 12. Mảng thành [11, 12, 25, 22, 64].

**Lượt 2:** trong [25, 22, 64], nhỏ nhất là 22 ở chỉ số 3. Đổi 25 và 22. Mảng thành [11, 12, 22, 25, 64].

**Lượt 3:** đoạn còn lại [25, 64] đã có nhỏ nhất ở vị trí đầu. Không cần swap. Phần tử cuối 64 cũng đã ở đúng vị trí.

Kết quả cuối cùng:

~~~text
[11, 12, 22, 25, 64]
~~~

Có **4 lượt của vòng ngoài**, **10 lần so sánh a[j] < a[minIndex]** và **3 lần hoán đổi thực sự**. Số so sánh là 4 + 3 + 2 + 1 = 10. Con số này không phụ thuộc vào thứ tự giá trị ban đầu, miễn ta dùng đúng hai vòng lặp của thuật toán trên.

### Cách tự mô phỏng không bị nhầm

Ở đầu mỗi lượt, kẻ một vạch sau phần đã cố định. Khi tìm min, **chỉ duyệt phía bên phải vạch**. Ghi minIndex sau khi quét hết, rồi mới thực hiện tối đa một hoán đổi. Nếu cứ nhìn thấy số nhỏ hơn rồi đổi ngay, chương trình có thể vẫn sắp được mảng theo cách khác, nhưng không còn là quy trình selection sort chuẩn đang phân tích ở đây.

## 4. Bất biến vòng lặp: vì sao selection sort đúng?

Một thuật toán không thể được coi là đúng chỉ vì chạy đúng vài ví dụ. Ta chứng minh bằng **bất biến vòng lặp** (*loop invariant*).

**Bất biến trước lượt i của vòng ngoài:**
1. Đoạn a[0 .. i−1] được sắp xếp không giảm.
2. Các phần tử trong đoạn đó là **i phần tử nhỏ nhất của toàn bộ mảng**, tính cả số lần xuất hiện; do đó mọi phần tử trong đoạn đã cố định không lớn hơn bất kỳ phần tử nào ở phần chưa sắp.
3. Toàn bộ mảng vẫn có cùng đa tập giá trị với mảng ban đầu.

**Khởi tạo:** trước lượt i = 0, đoạn đầu là rỗng, đã sắp xếp một cách hiển nhiên và chứa đúng 0 phần tử nhỏ nhất. Chưa có thay đổi dữ liệu nên đa tập được bảo toàn.

**Duy trì:** ở lượt i, vòng trong xét tất cả vị trí từ i đến n−1 và giữ chỉ số của giá trị nhỏ nhất. Sau khi kết thúc vòng trong, việc đổi chỗ đưa giá trị nhỏ nhất còn lại vào a[i]. Giá trị này không nhỏ hơn các giá trị đã cố định trước đó (vì những giá trị ấy đã là các giá trị nhỏ nhất của toàn bộ mảng), nên đoạn a[0 .. i] vẫn có thứ tự không giảm và chứa i+1 giá trị nhỏ nhất. Đổi chỗ chỉ hoán vị các giá trị, không làm thay đổi đa tập. Bất biến được giữ cho lượt tiếp theo.

**Kết thúc:** vòng ngoài hoàn thành sau khi cố định n−1 vị trí đầu (nếu n≥2). Theo bất biến, những vị trí này chứa n−1 giá trị nhỏ nhất theo đúng thứ tự; phần tử còn lại ở cuối là giá trị lớn nhất còn lại, nên cả mảng không giảm. Với n = 0 hoặc n = 1, mảng đã được sắp xếp ngay từ đầu.

**Tính kết thúc:** vòng ngoài tăng i một đơn vị ở mỗi lượt, còn vòng trong tăng j từ i+1 tới n−1. Cả hai đều chạy trên tập chỉ số hữu hạn; không có nhánh làm lùi các biến lặp. Thuật toán kết thúc với mọi mảng hữu hạn hợp lệ.

Cấu trúc chứng minh gồm **khởi tạo → duy trì → kết thúc**, áp dụng được cho nhiều thuật toán khác như insertion sort, tìm kiếm nhị phân, thuật toán tham lam và các vòng xử lý dãy.

## 5. Phân tích thời gian và số phép hoán đổi

### 5.1. Số lần so sánh chính xác

Ở lượt i, vòng trong so sánh n−i−1 lần. Tổng số so sánh:

\[
C(n)=(n-1)+(n-2)+\cdots+1+0=\frac{n(n-1)}{2}.
\]

Trong ký hiệu Big-O và Theta, số lần so sánh là **Θ(n²)** khi n tăng. Không có lợi thế về số lần so sánh khi đầu vào đã sắp xếp, vì thuật toán vẫn duyệt toàn bộ phần chưa sắp để chứng nhận phần tử nhỏ nhất.

| Số phần tử n | Số so sánh n(n−1)/2 | Số lượt vòng ngoài (nếu n≥1) |
| ---: | ---: | ---: |
| 0 | 0 | 0 |
| 1 | 0 | 0 |
| 2 | 1 | 1 |
| 5 | 10 | 4 |
| 10 | 45 | 9 |
| 100 | 4.950 | 99 |
| 1.000 | 499.500 | 999 |
| 10.000 | 49.995.000 | 9.999 |

Độ phức tạp thời gian trong cả **best case, average case và worst case** của phiên bản chuẩn là **Θ(n²)**: dù có thể bỏ qua một số swap, việc so sánh vẫn không thay đổi.

### 5.2. Số lần swap

Mỗi lượt i có **tối đa một lần hoán đổi**. Có n−1 lượt nếu n≥1, nên:

~~~text
0 <= số lần swap <= max(0, n - 1)
~~~

- Mảng đã sắp xếp: nếu bỏ qua self-swap, **0 swap**.
- Mảng [64,25,12,22,11]: **3 swap**.
- Mảng [2,3,4,5,1]: **4 swap** với n=5 — đạt giới hạn n−1.
- Mảng đảo ngược không bắt buộc đạt n−1 swap; ví dụ [5,4,3,2,1] chỉ cần 2 swap cho phiên bản này.

Điểm đáng chú ý là selection sort có số lần **ghi đổi chỗ** O(n), trong khi số so sánh Θ(n²). Một swap thông thường cần vài phép gán. Vì vậy nếu chi phí ghi dữ liệu đáng kể nhưng so sánh tương đối rẻ, đặc điểm ít swap có thể có ích trong những tình huống đặc thù. Tuy nhiên **ít swap không đồng nghĩa chạy nhanh hơn tổng thể**: bộ nhớ đệm CPU, chi phí so sánh, kích thước dữ liệu và lựa chọn thuật toán cũng quan trọng.

### 5.3. Bộ nhớ và tính thích ứng

Phiên bản sắp xếp tại chỗ chỉ cần các biến i, j, minIndex, temp và vài bộ đếm: **O(1) bộ nhớ phụ** (không tính mảng đầu vào). Nó là thuật toán **in-place**; không yêu cầu cấp một mảng O(n) để lưu kết quả.

Selection sort chuẩn **không thích ứng** (*non-adaptive*) theo mức độ đã có thứ tự của mảng: cả mảng đã sắp và mảng đảo đều tốn cùng số lần so sánh. Thuật toán cũng không yêu cầu đệ quy.

## 6. Tính ổn định: một nhược điểm dễ bỏ qua

Một thuật toán sắp xếp là **ổn định** (*stable*) nếu các phần tử có **khóa so sánh bằng nhau** vẫn giữ nguyên thứ tự tương đối từ đầu vào.

Đối với các số nguyên đơn thuần, ta thường không thấy vấn đề vì hai số 2 trông giống nhau. Nhưng khi sắp xếp bản ghi (tên, điểm), hai người cùng điểm có thể mang danh tính khác nhau; thứ tự của họ có thể quan trọng.

**Selection sort kiểu đổi chỗ trực tiếp thường không ổn định.** Phản ví dụ:

~~~text
Đầu vào:   [(2,A), (2,B), (1,C)]
            khóa=2 khóa=2 khóa=1

Chọn min là (1,C), đổi với (2,A):

Sau lượt 0: [(1,C), (2,B), (2,A)]
Kết thúc:  [(1,C), (2,B), (2,A)]
~~~

Hai bản ghi có khóa 2 ban đầu theo thứ tự **A rồi B**, nhưng kết quả lại thành **B rồi A**. Đây là một phản ví dụ hợp lệ cho tính ổn định.

Điều đáng chú ý: dù vòng trong dùng so sánh **<** (chọn phần tử nhỏ nhất xuất hiện đầu tiên khi có hòa), phép swap vẫn có thể khiến một bản ghi bằng khóa bị đẩy qua bản ghi cùng khóa khác. Vì vậy đổi dấu so sánh hoặc cố chọn phần tử hòa đầu tiên **không tự biến selection sort trao đổi trực tiếp thành ổn định**.

### Có thể làm selection sort ổn định không?

Có. Một biến thể **stable selection sort** làm như sau:
1. Tìm vị trí minIndex của phần tử nhỏ nhất trong [i, n).
2. Lưu riêng phần tử đó vào biến temp.
3. **Dịch phải** từng phần tử ở [i, minIndex−1] một vị trí.
4. Đặt temp vào a[i], thay vì swap hai vị trí xa nhau.

Nhờ dịch chuyển bảo toàn thứ tự tương đối của các phần tử bị dời, và chọn **lần xuất hiện đầu tiên** của khóa nhỏ nhất, biến thể có thể ổn định. Nó vẫn tốn **Θ(n²) so sánh**, **O(1) bộ nhớ phụ** với phép dịch in-place, nhưng số lần dịch/ghi có thể tới **Θ(n²)**, đánh đổi ưu điểm ít swap của bản chuẩn.

Một lựa chọn khác là sắp xếp theo khóa kép (khóa chính, vị trí gốc), nhưng khi đó tiêu chí so sánh đã được thay đổi để bảo toàn thứ tự, và có thể cần lưu vị trí gốc của từng bản ghi. Không được mặc nhiên tuyên bố selection sort chuẩn ổn định.

## 7. Java 17 chạy được: thuật toán, theo dõi các lượt và kiểm thử

Chương trình sau có một hàm \`selectionSort\` nhận mảng \`int[]\`, thay đổi trực tiếp mảng, và trả thống kê số lần so sánh/hoán đổi. Chế độ \`trace\` in trạng thái sau từng lượt. Phần kiểm thử lấy nhiều mẫu nhỏ, so kết quả với \`Arrays.sort\` để phát hiện sai khác.

~~~java
import java.util.Arrays;

public class SelectionSortDemo {
    record Stats(long comparisons, int swaps) {}

    static Stats selectionSort(int[] a, boolean trace) {
        long comparisons = 0;
        int swaps = 0;

        for (int i = 0; i < a.length - 1; i++) {
            int minIndex = i;

            for (int j = i + 1; j < a.length; j++) {
                comparisons++;
                if (a[j] < a[minIndex]) {
                    minIndex = j;
                }
            }

            boolean moved = (minIndex != i);
            if (moved) {
                int temp = a[i];
                a[i] = a[minIndex];
                a[minIndex] = temp;
                swaps++;
            }

            if (trace) {
                System.out.println("pass " + (i + 1)
                        + ": " + Arrays.toString(a)
                        + " min=" + a[i]
                        + " swap=" + moved);
            }
        }

        return new Stats(comparisons, swaps);
    }

    static void verify(int[] input) {
        int[] expected = input.clone();
        int[] actual = input.clone();

        Arrays.sort(expected);
        selectionSort(actual, false);

        if (!Arrays.equals(expected, actual)) {
            throw new AssertionError(
                    "input=" + Arrays.toString(input)
                    + ", expected=" + Arrays.toString(expected)
                    + ", actual=" + Arrays.toString(actual));
        }
    }

    public static void main(String[] args) {
        int[] values = {64, 25, 12, 22, 11};

        System.out.println("initial=" + Arrays.toString(values));
        Stats stats = selectionSort(values, true);
        System.out.println("sorted=" + Arrays.toString(values));
        System.out.println("comparisons=" + stats.comparisons()
                + " swaps=" + stats.swaps());

        int[][] cases = {
            {},
            {5},
            {2, 2, 1},
            {0, -2, 3, -2},
            {Integer.MAX_VALUE, -1, Integer.MIN_VALUE}
        };

        for (int[] testCase : cases) {
            verify(testCase);
        }
        System.out.println("verified=" + cases.length);
    }
}
~~~

Lưu thành **SelectionSortDemo.java**. Với **JDK 17 trở lên**, chạy:

~~~bash
javac SelectionSortDemo.java
java SelectionSortDemo
~~~

Đầu ra chính xác:

~~~text
initial=[64, 25, 12, 22, 11]
pass 1: [11, 25, 12, 22, 64] min=11 swap=true
pass 2: [11, 12, 25, 22, 64] min=12 swap=true
pass 3: [11, 12, 22, 25, 64] min=22 swap=true
pass 4: [11, 12, 22, 25, 64] min=25 swap=false
sorted=[11, 12, 22, 25, 64]
comparisons=10 swaps=3
verified=5
~~~

**Giải thích các quyết định trong mã:**

- Vòng ngoài dùng \`i < a.length - 1\` nên không lặp trên mảng rỗng hoặc một phần tử.
- \`minIndex = i\` giữ vị trí nhỏ nhất đã tìm thấy; vòng trong chỉ cập nhật khi gặp giá trị **nhỏ hơn**, không đổi vì bằng nhau.
- \`moved\` lưu trước việc có cần hoán đổi hay không, để trace đúng cả lượt không swap.
- \`Stats\` là **record** của Java 17 chứa \`long comparisons\` và \`int swaps\`; dùng \`long\` cho bộ đếm so sánh để tránh tràn kiểu int nếu n lớn.
- \`verify\` làm việc trên hai bản sao, vì hàm sort chủ ý thay đổi trực tiếp tham số đầu vào. Dùng \`Arrays.sort\` làm một oracle thử nghiệm chứ không thay thế chứng minh đúng ở phần 4.
- Các ca kiểm thử bao phủ mảng rỗng, một phần tử, phần tử trùng, số âm và cực trị \`Integer.MIN_VALUE\`/\`Integer.MAX_VALUE\`.
- So sánh số nguyên bằng \`<\` trực tiếp, không dùng phép trừ kiểu \`a[j] - a[minIndex]\`; phép trừ như vậy có thể tràn int và làm sai thứ tự khi triển khai comparator.

Chương trình không tự xử lý tham số null: hợp đồng ở đây nhận một **mảng int không null**, có thể dài 0. Nếu API thực tế cần hỗ trợ null, phải bổ sung tiền điều kiện hoặc quy định hành vi riêng.

## 8. Trường hợp biên và ca kiểm thử cần có

Một bộ kiểm thử chất lượng không chỉ chứa mảng “lộn xộn” nhiều phần tử. Cần kiểm tra các kích thước tối thiểu và các cấu hình dễ làm lộ lỗi chỉ số, so sánh hoặc hoán đổi.

| Đầu vào | Kết quả đúng | Trọng tâm kiểm tra |
| --- | --- | --- |
| \`[]\` | \`[]\` | Vòng ngoài không truy cập dữ liệu khi n = 0 |
| \`[5]\` | \`[5]\` | n = 1, không cần quét hay swap |
| \`[1, 2, 3]\` | \`[1, 2, 3]\` | Đã có thứ tự, không nên self-swap |
| \`[3, 2, 1]\` | \`[1, 2, 3]\` | Đảo ngược, cần chọn min ở cuối |
| \`[2, 2, 2]\` | \`[2, 2, 2]\` | Toàn bộ bằng nhau, không swap nếu dùng < |
| \`[3, 1, 3, 2]\` | \`[1, 2, 3, 3]\` | Giữ nguyên bội số phần tử |
| \`[-2, 0, -2, 3]\` | \`[-2, -2, 0, 3]\` | Số âm và phần tử trùng |
| \`[Integer.MAX_VALUE, Integer.MIN_VALUE]\` | \`[Integer.MIN_VALUE, Integer.MAX_VALUE]\` | Giá trị cực trị, không so sánh bằng phép trừ |
| \`[2, 3, 4, 5, 1]\` | \`[1, 2, 3, 4, 5]\` | Có thể đạt n−1 swap |

### Lỗi thường gặp

**1. Không đặt lại minIndex = i ở đầu mỗi lượt.** Khi bước trước kết thúc, minIndex thuộc đoạn cũ. Nếu tái sử dụng nó, thuật toán có thể lấy phần tử trong đoạn đã cố định hoặc bỏ qua đầu đoạn mới.

**2. Duyệt nhầm qua phần đã sắp xếp.** Ở lượt i chỉ được tìm min trong \`[i, n)\`. Quét lại toàn bộ mảng có thể kéo phần tử đã cố định ra khỏi vị trí đúng.

**3. Quên bao gồm phần tử cuối.** Vòng trong phải xét tới \`j = n - 1\`, tức điều kiện \`j < n\`. Dùng \`j < n - 1\` sẽ bỏ qua ứng viên cuối, ví dụ phần tử 11 trong [64,25,12,22,11] ở lượt đầu.

**4. Nhầm chỉ số và giá trị nhỏ nhất.** \`minIndex\` là vị trí, không phải giá trị. Gán \`a[i] = minIndex\` sẽ tạo ra dữ liệu mới và làm mất tính hoán vị.

**5. Hoán đổi giữa lúc chưa quét xong.** Selection sort chuẩn chỉ swap sau khi xác định min của toàn bộ phần chưa sắp. Đổi liên tục trong vòng trong khiến số phép ghi tăng và phân tích thuật toán khác đi.

**6. Quên điều kiện minIndex != i.** Swap với chính mình thường không đổi kết quả nhưng tạo thao tác ghi thừa. Nếu đang đo số lần swap thực sự, cần quy ước rõ có tính self-swap hay không; trong bài này **không tính**.

**7. Cho rằng thuật toán ổn định chỉ vì dùng <.** Phản ví dụ bản ghi [(2,A),(2,B),(1,C)] cho thấy đổi chỗ xa vẫn có thể đảo thứ tự các khóa bằng nhau.

**8. Chỉ kiểm tra mảng kết quả tăng dần.** Ví dụ hàm vô tình làm mất bớt phần tử trùng vẫn tạo ra dãy không giảm. Phải kiểm tra cả **bảo toàn đa tập**; với mẫu nhỏ có thể so với \`Arrays.sort\` trên bản sao.

**9. Kết luận mảng đã gần sắp thì chạy O(n).** Selection sort vẫn so sánh Θ(n²) trong phiên bản chuẩn; số swap thấp hơn không làm giảm số lần quét.

**10. Không phân biệt tăng dần và giảm dần.** Muốn giảm dần, mỗi lượt cần chọn **giá trị lớn nhất** trong phần chưa sắp, thay vì nhỏ nhất; bất biến và hậu điều kiện phải đổi tương ứng. Không nên đổi ngẫu nhiên một dấu so sánh mà bỏ qua đặc tả.

## 9. So sánh với các thuật toán sắp xếp khác

| Thuật toán | Thời gian điển hình của phiên bản phổ biến | Bộ nhớ phụ | Ổn định? | Khi nào có thể cân nhắc |
| --- | --- | --- | --- | --- |
| Selection sort đổi chỗ | Θ(n²) cả tốt và xấu | O(1) | Không | Học bất biến; n nhỏ; giảm số swap |
| Insertion sort | Tốt nhất Θ(n) khi đã sắp, xấu nhất Θ(n²) | O(1) | Có nếu cài đúng | Dữ liệu nhỏ/gần sắp |
| Bubble sort có cờ dừng | Tốt nhất Θ(n), xấu nhất Θ(n²) | O(1) | Có nếu chỉ đổi khi > | Minh họa hoán đổi kề |
| Merge sort trên mảng | Θ(n log n) | O(n) thường gặp | Có nếu ghép đúng | Cần hiệu năng ổn định theo n lớn |
| Heap sort | Θ(n log n) | O(1) với heap tại chỗ | Không trong bản phổ biến | Cần cận xấu nhất tốt, ít bộ nhớ phụ |
| Quick sort | Trung bình Θ(n log n), xấu nhất Θ(n²) | O(log n) stack kỳ vọng trong một số cài đặt | Thường không | Sắp xếp in-place hiệu quả trong nhiều tình huống |

Đây là bảng so sánh các **phiên bản thuật toán phổ biến**, không phải cam kết cho mọi cách triển khai. Ví dụ insertion sort chỉ ổn định khi không dời vượt qua những phần tử bằng khóa; merge sort chỉ ổn định nếu khi hai phần tử bằng khóa thì chọn phần tử từ nửa trái trước.

Trong Java thực tế, nên cân nhắc \`Arrays.sort\` hoặc các API sắp xếp chuẩn khi không có yêu cầu học thuật đặc biệt. Các API thư viện đã được tối ưu và kiểm thử rộng; việc tự chọn selection sort cho dữ liệu lớn thường làm giảm hiệu năng đáng kể.

### Khi selection sort có ý nghĩa

- **Giảng dạy:** cực dễ quan sát đoạn đã đúng tăng dần sau mỗi lượt.
- **Mảng rất nhỏ:** chi phí bậc hai có thể vẫn chấp nhận được; tuy nhiên việc tối ưu cần đo đạc thay vì giả định.
- **Môi trường tốn chi phí ghi:** số swap tối đa n−1 là một đặc tính có thể quan tâm nếu ghi đắt hơn so sánh.
- **Bài cần chứng minh thuật toán:** bất biến “prefix là i phần tử nhỏ nhất” rất rõ.

Ngược lại, nếu n lên tới 100.000, số lần so sánh là 100.000×99.999/2 = **4.999.950.000** — thường không phù hợp với giới hạn thời gian của bài lập trình. Với n lớn, hãy xem xét các thuật toán O(n log n) và ràng buộc tính ổn định.

## 10. Biến thể và các mở rộng liên quan

### 10.1. Selection sort giảm dần

Thay bước “tìm nhỏ nhất” bằng “tìm lớn nhất” trong phần chưa sắp. Sau mỗi lượt, đoạn đầu là i+1 phần tử **lớn nhất** theo thứ tự không tăng. Số so sánh và giới hạn swap không đổi. Đây vẫn là selection sort với tiêu chí ngược lại.

### 10.2. Chọn giá trị cuối cùng trước

Có thể chọn **giá trị lớn nhất** trong phần chưa sắp rồi đặt vào **cuối** phần ấy, thu hẹp khoảng chưa sắp từ phải qua trái. Bất biến đổi thành “hậu tố đã sắp chứa những phần tử lớn nhất”. Cần thiết kế vòng lặp cho nhất quán với cận trái/phải; không chỉ đảo thứ tự vòng i mà giữ nguyên phép tìm min phía phải.

### 10.3. Stable selection sort

Như phần 6: tìm min còn lại, rồi **dịch các phần tử nằm trước min sang phải** thay vì hoán đổi hai vị trí xa. Với khóa bằng nhau, chọn phần tử đầu tiên trong phần chưa sắp để bảo toàn thứ tự xuất hiện. Đổi lại có thể phải thực hiện Θ(n²) phép dịch.

### 10.4. Chọn đồng thời hai cực trị

Một biến thể tìm **cả min và max** trong đoạn còn lại, cố định một giá trị ở đầu và một ở cuối mỗi lượt. Do có hai lần đặt phần tử, phải đặc biệt chú ý khi vị trí max bị thay đổi bởi swap min hoặc khi min/max trùng nhau. Biến thể này không mặc nhiên giữ nguyên số so sánh hay độ ổn định của bản chuẩn; cần phân tích riêng.

### 10.5. So sánh với tìm kiếm phần tử nhỏ thứ k

Nếu chỉ muốn lấy phần tử nhỏ thứ k, sắp xếp cả mảng bằng selection sort là một cách làm nhưng chi phí Θ(n²). Có những thuật toán chọn thứ tự như quickselect thường giải quyết nhu cầu này nhanh hơn về kỳ vọng mà không sắp xếp toàn bộ. Việc “selection” xuất hiện trong tên cả hai không có nghĩa chúng là cùng một thuật toán.

## 11. Câu hỏi tự luyện

**Bài 1 — theo dõi bằng tay.** Cho a = [9, 4, 6, 2], hãy ghi mảng sau mỗi lượt selection sort tăng dần.

*Đáp án tham khảo:* lượt 0 chọn 2 ở cuối → [2,4,6,9]; lượt 1 đã có 4 nhỏ nhất → [2,4,6,9]; lượt 2 đã có 6 nhỏ nhất → [2,4,6,9]. Tổng 6 so sánh và 1 swap.

**Bài 2 — số phép so sánh.** Với n = 8, thuật toán chuẩn thực hiện bao nhiêu lần so sánh? Kết quả có khác nếu mảng đã sắp xếp không?

*Đáp án:* 8×7/2 = **28**; không đổi, vì vòng trong vẫn xét mọi phần tử còn lại.

**Bài 3 — chứng minh.** Phát biểu bất biến của vòng ngoài và giải thích vì sao sau lượt i, vị trí i không cần được chỉnh sửa nữa.

*Định hướng:* trước lượt i, prefix có i phần tử nhỏ nhất và đã sắp. Lấy min của suffix đem về vị trí i, nên sau lượt này prefix có i+1 phần tử nhỏ nhất theo đúng thứ tự. Các lượt sau chỉ thao tác trong phần còn lại, không chạm prefix.

**Bài 4 — ổn định.** Có ba bản ghi [(2,A), (2,B), (1,C)]. Selection sort trực tiếp có bảo toàn thứ tự A trước B không?

*Đáp án:* Không: đổi (1,C) với (2,A) tạo [(1,C), (2,B), (2,A)], đảo B và A. Muốn ổn định, cân nhắc biến thể dịch chuyển thay cho swap xa.

**Bài 5 — cận số swap.** Với 5 phần tử, tối đa có bao nhiêu lượt swap thực sự? Hãy cho một đầu vào đạt mức tối đa.

*Đáp án:* Tối đa **4**, vì chỉ có 4 lượt ngoài. Mảng [2,3,4,5,1] cần đúng 4 swap trong bản selection sort có bỏ self-swap.

**Bài 6 — chọn thuật toán.** Nếu cần sắp xếp 100.000 số nguyên trong thời gian ngắn, selection sort có phù hợp không?

*Đáp án:* Thường không. Nó phải thực hiện khoảng **4.999.950.000 lần so sánh**. Nên chọn thuật toán O(n log n) hoặc hàm sắp xếp thư viện phù hợp với loại dữ liệu và yêu cầu ổn định.

## 12. Tóm tắt cần nhớ

1. **Selection sort** lặp qua các vị trí i và **chọn phần tử nhỏ nhất** từ đoạn chưa sắp [i, n) để đưa về a[i].
2. **Bất biến chính:** trước lượt i, prefix [0, i) đã sắp và chứa đúng i phần tử nhỏ nhất của mảng.
3. **Thời gian:** số so sánh luôn là **n(n−1)/2**, nên Θ(n²) ở best/average/worst case.
4. **Bộ nhớ phụ:** O(1) với phiên bản đổi chỗ trực tiếp. **Swap:** tối đa n−1 lần (bỏ qua self-swap).
5. **Ổn định:** phiên bản swap thông thường **không ổn định**; có thể làm ổn định bằng cách chọn min rồi dịch chuyển, nhưng số phép ghi tăng.
6. **Ứng dụng:** tốt để học thuật toán và khi n nhỏ/chi phí swap quan trọng; không phù hợp mặc định cho dữ liệu lớn.
7. **Kiểm tra kết quả:** ngoài thứ tự không giảm còn phải giữ nguyên kích thước và đa tập giá trị, thử ca rỗng, một phần tử, trùng, âm, cực trị và mảng đã sắp.