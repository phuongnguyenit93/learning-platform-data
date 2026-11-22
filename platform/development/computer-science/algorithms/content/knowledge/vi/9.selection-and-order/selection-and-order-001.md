# Tìm nhỏ nhất, lớn nhất và đồng thời cả hai

Trong nhóm thuật toán **chọn và thứ tự**, ba yêu cầu cơ bản là tìm phần tử **nhỏ nhất** (minimum), tìm phần tử **lớn nhất** (maximum), hoặc tìm **đồng thời cả hai** trên cùng một tập dữ liệu. Chúng thường xuất hiện khi tìm giá thấp nhất và cao nhất, điểm thấp nhất và cao nhất, thời gian sớm nhất và muộn nhất hoặc các mốc biên của dữ liệu.

Một cách trực giác là sắp xếp toàn bộ dữ liệu rồi lấy hai đầu. Tuy nhiên, nếu chỉ cần min/max, việc sắp xếp là không cần thiết: **một lượt quét O(n)** đủ để tìm một cực trị; còn **so sánh các phần tử theo cặp** giúp tìm cả hai với ít phép so sánh hơn so với hai lượt quét độc lập, dù độ phức tạp tiệm cận vẫn là O(n).

## 1. Định nghĩa bài toán và hợp đồng đầu ra

Cho dãy **a[0..n−1]** gồm n phần tử có thể so sánh theo một quan hệ thứ tự.

- **Minimum:** tìm m sao cho m ≤ a[i] với mọi i hợp lệ.
- **Maximum:** tìm M sao cho M ≥ a[i] với mọi i hợp lệ.
- **Min–max đồng thời:** trả cặp (m, M) sau khi xét dữ liệu.
- **Argmin/argmax:** thay vì chỉ trả giá trị, trả **vị trí** mà cực trị xuất hiện.
- **Tập vị trí đạt cực trị:** nếu giá trị cực trị xuất hiện nhiều lần, trả tất cả vị trí thỏa điều kiện.

Ví dụ với **[8, 3, 5, 2, 7, 4, 6, 1]**:

- Giá trị nhỏ nhất: **1**, tại chỉ số **7**.
- Giá trị lớn nhất: **8**, tại chỉ số **0**.
- Nếu cần cả hai, kết quả: **(1, 8)**.

**“Nhỏ nhất” và “lớn nhất” phải dựa trên cùng quy tắc so sánh**. Với số nguyên, thứ tự tự nhiên là thứ tự số học; với bản ghi, có thể phải so theo giá, điểm, thời gian hoặc khóa do bài toán quy định.

### Dãy rỗng, một phần tử và giá trị trùng lặp

- Nếu **n = 0**, min và max **không xác định** nếu chưa có giá trị mặc định hoặc quy ước đặc biệt. API có thể ném ngoại lệ hoặc trả Optional rỗng; không được mặc định truy cập a[0].
- Nếu **n = 1**, phần tử duy nhất đồng thời là min và max, **không cần phép so sánh giữa các phần tử**.
- Nếu có **nhiều phần tử bằng cực trị**, bài toán phải quy định lấy vị trí **đầu tiên**, **cuối cùng** hay tất cả vị trí. Giá trị min/max vẫn không đổi.
- Nếu dãy toàn phần tử bằng nhau, **min = max**; đây không phải hai bản ghi nhất thiết khác nhau.

Trong ví dụ Java bên dưới, chỉ số bắt đầu từ **0** và khi có nhiều giá trị bằng nhau, ta ưu tiên **chỉ số nhỏ nhất** cho cả argmin và argmax.

## 2. Tìm nhỏ nhất bằng một lượt quét

Khởi tạo ứng viên min bằng phần tử đầu tiên. Với mỗi phần tử tiếp theo, so sánh với min hiện tại và cập nhật nếu nhỏ hơn:

~~~text
minIndex = 0
for i = 1 .. n-1:
    if a[i] < a[minIndex]:
        minIndex = i
return minIndex
~~~

**Bất biến vòng lặp:** trước khi xét a[i], a[minIndex] là giá trị nhỏ nhất trong đoạn đã xét **a[0..i−1]**. Sau khi so a[i] với giá trị đó, minIndex là vị trí nhỏ nhất trong đoạn **a[0..i]**. Khi xét hết, đây chính là min của toàn dãy.

Với n ≥ 1, nếu kiểm tra từng phần tử còn lại đúng một lần:

- Số phép so sánh giá trị: **n − 1**.
- Thời gian: **Θ(n)**.
- Bộ nhớ phụ: **O(1)** nếu chỉ giữ giá trị hoặc chỉ số cực trị.

Khi dùng điều kiện **a[i] < a[minIndex]** (không có dấu bằng), lần xuất hiện đầu tiên của cực tiểu được giữ lại. Nếu dùng **≤**, việc cập nhật ở các phần tử bằng nhau sẽ đưa chỉ số về **lần xuất hiện cuối cùng**.

### Vì sao không thể bảo đảm tìm min với ít hơn n−1 phép so sánh?

Trong mô hình chỉ được suy luận quan hệ thứ tự từ **phép so sánh cặp phần tử**, để khẳng định một ứng viên là nhỏ nhất, mỗi phần tử khác nó phải từng bị chứng minh **không thể nhỏ nhất**, tức phải “thua” ít nhất một so sánh. Một phép so sánh giữa hai phần tử chỉ trực tiếp loại được tối đa một ứng viên min. Vì vậy cần ít nhất **n−1** phép so sánh trong trường hợp xấu nhất. Một lượt quét đạt đúng mức này, nên tối ưu về số phép so sánh trong mô hình đó.

## 3. Tìm lớn nhất bằng một lượt quét

Đổi chiều so sánh:

~~~text
maxIndex = 0
for i = 1 .. n-1:
    if a[i] > a[maxIndex]:
        maxIndex = i
return maxIndex
~~~

Bất biến: sau khi xét i, a[maxIndex] là lớn nhất trong toàn bộ đoạn đã đọc. Tương tự min, tìm max cần **n−1** phép so sánh trong trường hợp xấu nhất và dùng **O(1)** bộ nhớ phụ.

Điều kiện **>** giữ vị trí xuất hiện đầu tiên của max nếu có phần tử bằng nhau; điều kiện **≥** sẽ chọn phần tử bằng nhau xuất hiện về sau.

### Hai lượt quét độc lập để lấy cả min và max

Một cách đơn giản là:

1. Quét để tìm min: **n−1** phép so sánh.
2. Quét lại để tìm max: **n−1** phép so sánh.

Tổng cộng với n ≥ 1 là:

**C₂scan(n) = 2(n−1) = 2n−2** phép so sánh giá trị.

Cả hai vẫn chạy **Θ(n)** thời gian, bộ nhớ phụ **O(1)**, nhưng khi n lớn ta có thể tiết kiệm thêm phép so sánh bằng cách **xử lý hai phần tử một lần**.

Cũng có thể viết một vòng lặp duy nhất, nhưng nếu mỗi phần tử đều được so với cả min lẫn max thì tổng số phép so sánh vẫn là **2n−2**. Điểm cải tiến của phương pháp theo cặp nằm ở **giảm số lần so sánh**, không chỉ ở giảm số vòng for.

## 4. Tìm min và max đồng thời theo từng cặp

**Ý tưởng:** lấy hai phần tử chưa xử lý, so sánh chúng với **nhau trước**. Sau đó:

- Phần tử nhỏ hơn (hoặc bằng) của cặp chỉ cần so với **min toàn cục**.
- Phần tử lớn hơn (hoặc bằng) của cặp chỉ cần so với **max toàn cục**.

Do đã biết thứ tự trong cặp, **không cần** đem cả hai phần tử so với cả min và max.

Với mỗi cặp đầy đủ, ta dùng **3 phép so sánh giá trị**:

1. So hai phần tử trong cặp: xác định ứng viên min cục bộ và max cục bộ.
2. So ứng viên min cục bộ với min toàn cục.
3. So ứng viên max cục bộ với max toàn cục.

Nếu xử lý độc lập từng phần tử, mỗi cặp sẽ cần tới **4 phép so sánh** (mỗi phần tử so với cả min và max). Nhờ phân vai trong cặp, tiết kiệm một phép so sánh cho mỗi cặp sau bước khởi tạo.

### Khởi tạo khi n chẵn

Nếu n = 2k:

1. So **a[0]** và **a[1]** đúng **một lần** để khởi tạo min và max.
2. Còn n−2 phần tử, tức **(n−2)/2** cặp.
3. Mỗi cặp thêm 3 phép so sánh.

Vậy:

**Cpair(n) = 1 + 3(n−2)/2 = 3n/2 − 2** khi n chẵn và n ≥ 2.

Ví dụ n = 8: quét hai lần cần **14** so sánh; theo cặp cần **10**.

### Khởi tạo khi n lẻ

Nếu n = 2k + 1:

1. Cho **a[0]** đồng thời là min và max, không cần so sánh.
2. Còn n−1 phần tử, tức **(n−1)/2** cặp.
3. Mỗi cặp dùng 3 phép so sánh.

Vậy:

**Cpair(n) = 3(n−1)/2** khi n lẻ.

Ví dụ n = 7: quét hai lần cần **12** so sánh; theo cặp cần **9**. Khi n = 1, công thức cho ra **0**.

Gộp cho mọi n ≥ 1, số phép so sánh của phương pháp theo cặp là:

**Cpair(n) = ⌈3n/2⌉ − 2.**

Giá trị này nhỏ hơn **2n−2** khi dữ liệu đủ lớn và tiết kiệm khoảng **25% số phép so sánh giá trị** khi n tăng. Cả hai vẫn thuộc **Θ(n)** thời gian.

## 5. Truy vết phương pháp theo cặp

Dãy ban đầu:

~~~text
a = [8, 3, 5, 2, 7, 4, 6, 1]
index 0  1  2  3  4  5  6  7
~~~

Có n = 8 chẵn nên so a[0] = 8 với a[1] = 3 để khởi tạo:

**min = 3**, **max = 8**, đã dùng **1 so sánh**.

| Cặp đang xét | So trong cặp | So với min hiện tại | So với max hiện tại | Min mới | Max mới | Tổng so sánh |
| --- | --- | --- | --- | ---: | ---: | ---: |
| (5, 2) | 2 nhỏ hơn 5 | 2 < 3 | 5 > 8 là sai | 2 | 8 | 4 |
| (7, 4) | 4 nhỏ hơn 7 | 4 < 2 là sai | 7 > 8 là sai | 2 | 8 | 7 |
| (6, 1) | 1 nhỏ hơn 6 | 1 < 2 | 6 > 8 là sai | 1 | 8 | 10 |

Kết quả min = 1 tại chỉ số 7, max = 8 tại chỉ số 0, tổng **10 phép so sánh giá trị**.

### Bất biến và chứng minh đúng

Sau khi xử lý một số cặp đầu tiên, giữ:

- **minIndex** chỉ phần tử nhỏ nhất trong tất cả phần tử đã xử lý.
- **maxIndex** chỉ phần tử lớn nhất trong tất cả phần tử đã xử lý.
- Các phần tử chưa xử lý không ảnh hưởng đến tính đúng đắn của cực trị trên phần đã xét.

Khi thêm cặp (x, y), gọi small là phần tử nhỏ hơn và large là phần tử lớn hơn:

- Vì **small ≤ large**, nếu phần tử nào trong cặp có thể làm giảm min thì **small** đã đủ là ứng viên; chỉ cần so small với min hiện có.
- Vì **large ≥ small**, nếu phần tử nào trong cặp có thể làm tăng max thì **large** đã đủ là ứng viên; chỉ cần so large với max hiện có.

Sau hai lần cập nhật, bất biến tiếp tục đúng cho toàn bộ các phần tử vừa xét. Đến cuối mảng, min/max toàn cục là chính xác.

Với giá trị trùng nhau, cặp vẫn có một small và một large **theo vai trò**, chúng có thể chính là cùng một vị trí được chọn làm đại diện. Nếu yêu cầu giữ vị trí đầu tiên, phải xử lý cả trường hợp **bằng nhau** cho đúng.

## 6. Java 17+: chương trình đầy đủ, đếm phép so sánh

Chương trình dưới đây triển khai cả **hai lượt quét** và **phương pháp theo cặp**. Cả hai đều trả giá trị min/max, chỉ số xuất hiện **đầu tiên** và số phép so sánh **giữa giá trị dữ liệu**. Việc so sánh **chỉ số** để phân xử hòa không được tính là so sánh khóa dữ liệu.

~~~java
import java.util.Arrays;

public class MinMaxSelectionDemo {

    record Result(int min, int minIndex, int max, int maxIndex,
                  int comparisons) {}

    private static void requireNonEmpty(int[] a) {
        if (a == null || a.length == 0) {
            throw new IllegalArgumentException("array must be nonempty");
        }
    }

    // Quét độc lập để tìm min và max.
    static Result twoScans(int[] a) {
        requireNonEmpty(a);
        int minIndex = 0;
        int maxIndex = 0;
        int comparisons = 0;

        for (int i = 1; i < a.length; i++) {
            comparisons++;
            if (Integer.compare(a[i], a[minIndex]) < 0) {
                minIndex = i;
            }
        }

        for (int i = 1; i < a.length; i++) {
            comparisons++;
            if (Integer.compare(a[i], a[maxIndex]) > 0) {
                maxIndex = i;
            }
        }

        return new Result(a[minIndex], minIndex, a[maxIndex],
                          maxIndex, comparisons);
    }

    // Min + max đồng thời: 3 so sánh cho mỗi cặp còn lại.
    static Result pairwiseMinMax(int[] a) {
        requireNonEmpty(a);
        int minIndex;
        int maxIndex;
        int next;
        int comparisons = 0;

        if (a.length % 2 == 0) {
            // n chẵn: khởi tạo từ cặp đầu bằng đúng 1 so sánh.
            int c = Integer.compare(a[0], a[1]);
            comparisons++;
            minIndex = (c <= 0) ? 0 : 1;
            maxIndex = (c >= 0) ? 0 : 1;
            next = 2;
        } else {
            // n lẻ: phần tử đầu tiên vừa là min vừa là max.
            minIndex = 0;
            maxIndex = 0;
            next = 1;
        }

        for (int i = next; i + 1 < a.length; i += 2) {
            // 1) Chọn ứng viên nhỏ/lớn của cặp.
            int c = Integer.compare(a[i], a[i + 1]);
            comparisons++;
            int smallIndex = (c <= 0) ? i : i + 1;
            int largeIndex = (c >= 0) ? i : i + 1;

            // 2) Cập nhật min; nếu cùng giá trị, ưu tiên chỉ số sớm.
            int minCmp = Integer.compare(a[smallIndex], a[minIndex]);
            comparisons++;
            if (minCmp < 0
                    || (minCmp == 0 && smallIndex < minIndex)) {
                minIndex = smallIndex;
            }

            // 3) Cập nhật max; nếu cùng giá trị, ưu tiên chỉ số sớm.
            int maxCmp = Integer.compare(a[largeIndex], a[maxIndex]);
            comparisons++;
            if (maxCmp > 0
                    || (maxCmp == 0 && largeIndex < maxIndex)) {
                maxIndex = largeIndex;
            }
        }

        return new Result(a[minIndex], minIndex, a[maxIndex],
                          maxIndex, comparisons);
    }

    static void show(int[] a) {
        Result slow = twoScans(a);
        Result pair = pairwiseMinMax(a);

        System.out.println("Array: " + Arrays.toString(a));
        System.out.printf(
                "Two scans: min=%d@%d, max=%d@%d, comparisons=%d%n",
                slow.min(), slow.minIndex(),
                slow.max(), slow.maxIndex(), slow.comparisons());
        System.out.printf(
                "Pairwise: min=%d@%d, max=%d@%d, comparisons=%d%n",
                pair.min(), pair.minIndex(),
                pair.max(), pair.maxIndex(), pair.comparisons());
    }

    public static void main(String[] args) {
        show(new int[] {8, 3, 5, 2, 7, 4, 6, 1});
        show(new int[] {4, 2, 9, 2, 9, 7, 1});
        show(new int[] {5, 5, 5, 5, 5});
        show(new int[] {42});
    }
}
~~~

Lưu thành **MinMaxSelectionDemo.java** và chạy bằng JDK 17 trở lên:

~~~bash
javac MinMaxSelectionDemo.java
java MinMaxSelectionDemo
~~~

**Đầu ra chính xác:**

~~~text
Array: [8, 3, 5, 2, 7, 4, 6, 1]
Two scans: min=1@7, max=8@0, comparisons=14
Pairwise: min=1@7, max=8@0, comparisons=10
Array: [4, 2, 9, 2, 9, 7, 1]
Two scans: min=1@6, max=9@2, comparisons=12
Pairwise: min=1@6, max=9@2, comparisons=9
Array: [5, 5, 5, 5, 5]
Two scans: min=5@0, max=5@0, comparisons=8
Pairwise: min=5@0, max=5@0, comparisons=6
Array: [42]
Two scans: min=42@0, max=42@0, comparisons=0
Pairwise: min=42@0, max=42@0, comparisons=0
~~~

**Giải thích chi tiết:**

- **Result** là một record Java, lưu min, minIndex, max, maxIndex và comparisons; Java tự sinh các accessor như **min()**, **maxIndex()**.
- **requireNonEmpty** quy định rõ trường hợp null hoặc mảng rỗng: ném **IllegalArgumentException**, thay vì truy cập a[0] và gặp lỗi ngoài ý muốn.
- **twoScans** mỗi vòng so đúng n−1 lần, nên đếm được **2n−2** so sánh.
- **pairwiseMinMax** xét n chẵn/lẻ để không bỏ sót phần tử. Mỗi cặp sau khởi tạo dùng đúng **3 lần gọi Integer.compare**.
- Khi hai phần tử trong một cặp bằng nhau, các biểu thức **c <= 0** và **c >= 0** đều chọn phần tử đầu cặp cho hai vai trò; do đó không ưu tiên phần tử thứ hai chỉ vì bằng khóa.
- Khi ứng viên cực trị mới có cùng giá trị với cực trị cũ, điều kiện **smallIndex < minIndex** hoặc **largeIndex < maxIndex** bảo đảm trả **chỉ số xuất hiện đầu tiên toàn dãy**.
- Trong dãy toàn 5, min và max đều là 5 và chỉ số được chọn đều là 0.
- **Integer.compare** an toàn hơn trừ hai số để so sánh, vì phép trừ có thể tràn với giá trị int rất lớn trái dấu.

Chương trình **không sắp xếp hoặc thay đổi mảng đầu vào**. Hai thuật toán đều giữ một số lượng hằng các biến, vì vậy bộ nhớ phụ **O(1)**, không tính dữ liệu đầu vào hay đối tượng kết quả nhỏ.

## 7. So sánh về hiệu năng

| Bài toán / phương pháp | So sánh trong trường hợp xấu nhất | Thời gian | Bộ nhớ phụ |
| --- | --- | --- | --- |
| Chỉ tìm min, quét | n−1 | Θ(n) | O(1) |
| Chỉ tìm max, quét | n−1 | Θ(n) | O(1) |
| Min và max, hai quét độc lập | 2n−2 | Θ(n) | O(1) |
| Min và max, xử lý theo cặp | ⌈3n/2⌉−2 | Θ(n) | O(1) |
| Sắp xếp rồi lấy hai đầu bằng thuật toán so sánh thông thường | Thường Θ(n log n) để sắp toàn bộ | Thường O(n log n) | Tùy thuật toán |

Các công thức tính phép so sánh trong bảng giả sử **n ≥ 1**, phần tử có thứ tự và áp dụng chính xác khuôn cài đặt tương ứng.

**Nhiều ít phép so sánh không đồng nghĩa với khác bậc Big-O.** Cả quét độc lập và theo cặp đều Θ(n), nhưng phương pháp theo cặp tiết kiệm một phần chi phí hằng số. Trong các hệ thống thực tế, chi phí truy cập bộ nhớ, nhánh rẽ, gọi comparator và tối ưu của trình biên dịch cũng có thể ảnh hưởng; nên đo benchmark khi hiệu năng tuyệt đối quan trọng.

### Phương pháp theo cặp có tối ưu về số phép so sánh không?

Trong **mô hình so sánh tổng quát** và xét trường hợp xấu nhất với các phần tử có thể phân biệt, việc tìm đồng thời min và max cần ít nhất **⌈3n/2⌉−2** phép so sánh khi n ≥ 2; với n = 1 cần 0. Phương pháp theo cặp đạt đúng mức này nên là **tối ưu theo số phép so sánh trường hợp xấu nhất**, chứ không chỉ nhanh hơn hai quét một chút.

Trực giác của cận dưới: so sánh ban đầu giúp phân loại ứng viên “có thể lớn nhất” và “có thể nhỏ nhất”; muốn xác nhận min phải loại tất cả đối thủ min, muốn xác nhận max phải loại tất cả đối thủ max. Một so sánh giữa hai phần tử chưa từng được đối chiếu có thể cùng góp phần phân loại cả hai, nên ta nên ghép chúng thành cặp ngay từ đầu. Sau đó vẫn cần đủ các phép so sánh để tìm phần tử tốt nhất trong từng nhóm ứng viên. Một lập luận đối kháng trong mô hình so sánh cho cận dưới nêu trên.

Không sử dụng cận dưới này như lời khẳng định trong mọi mô hình tính toán: nếu dữ liệu có miền giá trị và thông tin đặc biệt, có phép toán mạnh hơn phép so sánh cặp hoặc biết trước các giới hạn, có thể tận dụng giả thiết riêng.

## 8. Nếu cần chỉ số đầu/cuối hoặc tất cả cực trị

**Giá trị min/max** và **vị trí argmin/argmax** là hai kiểu kết quả khác nhau.

Với **[4, 2, 9, 2, 9, 7, 1]**:

- min = 1 tại chỉ số **6**;
- max = 9 tại các chỉ số **2 và 4**;
- theo quy tắc vị trí đầu tiên, argmax = **2**.

Để trả **vị trí cuối cùng**, khi hai giá trị bằng nhau hãy chọn chỉ số **lớn hơn** theo quy tắc nhất quán, kể cả khi phân vai phần tử trong cặp. Không chỉ đổi dấu cập nhật toàn cục mà quên xử lý hai phần tử bằng nhau trong cùng cặp.

Để trả **mọi vị trí cực trị**, một cách đơn giản và đáng tin là:

1. Tìm giá trị min và max bằng một trong các phương pháp trên.
2. Quét dãy thêm một lần để thu thập tất cả i sao cho a[i] bằng min hoặc max.

Chi phí vẫn **O(n + k)** với k vị trí thực sự được xuất, thường viết O(n) khi chỉ đếm các phần tử đầu vào; bộ nhớ đầu ra phụ thuộc k. Nếu min = max, phải xác định xem mỗi vị trí được liệt kê trong cả hai tập hay chỉ một lần trong kết quả gộp.

### Min/max trên đoạn con

Nếu chỉ hỏi cực trị trên một đoạn **[L,R]** của mảng một lần, có thể quét đoạn đó trong O(R−L+1). Nếu có **rất nhiều truy vấn** trên nhiều đoạn, việc quét từng đoạn lại nhiều lần có thể không tối ưu:

- **Sparse table** hỗ trợ truy vấn min/max trên đoạn tĩnh sau tiền xử lý, thường O(1) mỗi truy vấn cho các phép toán idempotent như min/max, nhưng cập nhật không thuận tiện.
- **Segment tree** hỗ trợ truy vấn min/max theo đoạn và cập nhật điểm thường O(log n) sau khi xây cây.
- **Monotonic deque** hỗ trợ min/max của mọi cửa sổ trượt độ dài k trong O(n) tổng thời gian.

Các cấu trúc này giải **bài toán truy vấn cực trị theo đoạn**, khác với yêu cầu duy nhất “tìm min và max của toàn bộ mảng một lần”.

## 9. Dữ liệu đến theo luồng và xử lý song song

### Luồng dữ liệu (streaming)

Khi các phần tử đến liên tiếp và không cần lưu lại toàn bộ, có thể duy trì:

- **currentMin**: min của tất cả dữ liệu đã nhận.
- **currentMax**: max của tất cả dữ liệu đã nhận.
- **count** hoặc chỉ số thứ tự để xác định vị trí đầu/cuối khi cần.

Mỗi phần tử mới được so với min và max hiện tại, chi phí cập nhật **O(1)** và bộ nhớ **O(1)** nếu chỉ giữ hai cực trị. Với luồng dài không biết trước n, phương pháp này đơn giản hơn việc đợi đủ cặp; việc giữ chờ một phần tử để so theo cặp cũng khả thi nhưng phải xử lý phần tử cuối nếu luồng dừng ở số lượng lẻ.

### Xử lý song song và phân tán

Chia dữ liệu thành các khối. Mỗi worker tính **localMin, localMax** của khối mình; sau đó gộp các cặp kết quả:

**merge((m₁, M₁), (m₂, M₂)) = (min(m₁,m₂), max(M₁,M₂)).**

Phép gộp có tính **kết hợp** theo giá trị, nên phù hợp với reduce song song. Nếu cần chỉ số đầu tiên khi có nhiều phần tử bằng nhau, phải gộp theo quy tắc “giá trị nhỏ/lớn hơn thắng; nếu bằng thì **chỉ số toàn cục nhỏ hơn thắng**”. Các khối phải mang theo chỉ số gốc hoặc một định danh vị trí thống nhất.

Cần phân biệt **tổng công việc** (work) với **thời gian chạy song song** (span). Chia khối không làm bài toán ngừng phải đọc tất cả phần tử; nó chỉ cho phép nhiều phần được kiểm tra đồng thời khi có tài nguyên phù hợp.

## 10. So sánh đối tượng và những trường hợp dễ lỗi

### Giá trị số nguyên cực trị

Đừng viết **a − b** để so hai số int, vì có thể tràn số. Ví dụ một số gần Integer.MIN_VALUE và một số gần Integer.MAX_VALUE có thể cho hiệu không biểu diễn được bằng int. Dùng **Integer.compare(a,b)**, **Long.compare** hoặc Comparator phù hợp.

Không khởi tạo min bằng 0 hoặc max bằng 0 nếu chưa có bảo đảm về miền dữ liệu:

- Với toàn số dương, min khởi tạo 0 sẽ sai.
- Với toàn số âm, max khởi tạo 0 sẽ sai.

Hãy khởi tạo từ **phần tử đầu tiên có thật** hoặc dùng một sentinel được chứng minh phù hợp và được xử lý đúng.

### So sánh số thực và NaN

Với float/double, cần đặc tả cách xử lý **NaN**, **+0.0/−0.0**, **+∞/−∞**. Phép so sánh số học bằng toán tử < hoặc > với NaN thường trả false, nên không thể mặc định một vòng quét đơn giản sẽ có thứ tự tổng quát nhất quán. Nếu yêu cầu thứ tự của Java, hãy dùng **Double.compare** hoặc **Comparator.comparingDouble** và hiểu quy ước sắp xếp của kiểu dữ liệu đó.

### Bản ghi nhiều trường

Giả sử muốn tìm người có **điểm thấp nhất**, nếu bằng điểm chọn mã ID nhỏ nhất: tiêu chí so sánh phải là (score ASC, id ASC). Muốn người có điểm cao nhất nhưng cùng điểm chọn ID nhỏ nhất thì tiêu chí max **không nhất thiết là phép đảo hoàn toàn** tiêu chí min, vì chiều của tie-breaker ID có thể giữ nguyên. Cần định nghĩa rõ hai quan hệ thứ tự hoặc chọn một quy tắc thống nhất theo yêu cầu.

### Không cần sắp xếp

Nếu đề chỉ hỏi min/max, **sorting** thêm chi phí mà không cung cấp kết quả cần thiết khác. Thuật toán sắp xếp so sánh thường mất Θ(n log n) với các phương pháp tối ưu phổ biến, trong khi min/max được chọn trực tiếp bằng Θ(n). Tuy nhiên, nếu dãy **đã sắp xếp sẵn** theo thứ tự tăng và có truy cập ngẫu nhiên, min = phần tử đầu, max = phần tử cuối, chỉ mất O(1) để đọc hai giá trị; đây là việc tận dụng **thứ tự đã biết**, không phải tìm cực trị từ dữ liệu chưa biết.

## 11. Lỗi thường gặp và kiểm thử biên

1. **Quên kiểm tra mảng rỗng.** Truy cập a[0] trên n = 0 gây lỗi; phải có hợp đồng trả kết quả rõ ràng.
2. **Khởi tạo min/max bằng 0.** Sai khi mọi phần tử cùng dấu hoặc miền dữ liệu không chứa 0.
3. **Tìm cả hai bằng cách sắp xếp.** Không cần O(n log n) nếu chỉ muốn hai cực trị.
4. **Nhầm số lượt duyệt với số phép so sánh.** Một vòng for so với cả min và max vẫn có thể dùng 2n−2 so sánh.
5. **Với n chẵn, quên khởi tạo từ hai phần tử đầu.** Sẽ làm thiếu một phần tử hoặc đếm sai phép so sánh.
6. **Với n lẻ, xử lý cặp từ chỉ số 0 mà không giải quyết phần tử dư.** Có thể vượt biên hoặc bỏ sót phần tử.
7. **Dùng ≤ / ≥ mà không xác định quy ước hòa.** Chỉ số xuất hiện đầu/cuối có thể bị đảo khi có giá trị trùng.
8. **Chỉ cập nhật một cực trị cho mỗi cặp.** Cần cập nhật cả min và max từ hai ứng viên đã phân vai.
9. **Đếm nhầm số phép so sánh vì xét thêm chỉ số.** Khi phân tích mô hình so sánh khóa, các điều kiện kiểm tra chỉ số/tie khác với phép so sánh giá trị.
10. **Dùng phép trừ để so int.** Có thể tràn số; dùng Integer.compare.
11. **Lẫn thuật toán min/max của toàn mảng với truy vấn range min/max.** Nhiều truy vấn đoạn cần cấu trúc hỗ trợ riêng.
12. **Khẳng định mọi cách tìm min/max đều sử dụng đúng ⌈3n/2⌉−2 phép so sánh.** Đó là phương pháp theo cặp phù hợp và cận tối ưu trong mô hình so sánh, không phải công thức cho mọi cài đặt.

| Dãy đầu vào | Min | Max | Hai quét | Theo cặp |
| --- | ---: | ---: | ---: | ---: |
| [42] | 42 | 42 | 0 | 0 |
| [2,1] | 1 | 2 | 2 | 1 |
| [3,1,2] | 1 | 3 | 4 | 3 |
| [5,5,5,5,5] | 5 | 5 | 8 | 6 |
| [-3,-8,-1,-5] | −8 | −1 | 6 | 4 |
| [8,3,5,2,7,4,6,1] | 1 | 8 | 14 | 10 |

Hãy kiểm thử cả: mảng rỗng, n = 1, n = 2, n chẵn/lẻ, đã tăng, đã giảm, toàn phần tử bằng nhau, cực trị ở đầu/cuối, số âm, Integer.MIN_VALUE, Integer.MAX_VALUE và nhiều vị trí cùng cực trị. Đồng thời so kết quả của phương pháp theo cặp với phương pháp quét độc lập trên nhiều dãy nhỏ để phát hiện lỗi biên.

## 12. Bài tập tự kiểm tra

**Câu 1.** Với n = 10, hai lượt quét và phương pháp theo cặp lần lượt dùng bao nhiêu phép so sánh?  
**Đáp án:** Hai quét dùng 2(10−1) = **18**; theo cặp dùng 3×10/2−2 = **13**.

**Câu 2.** Với n = 9, phương pháp theo cặp dùng bao nhiêu phép so sánh?  
**Đáp án:** 3(9−1)/2 = **12**.

**Câu 3.** Vì sao xử lý một cặp cần ba thay vì bốn phép so sánh?  
**Đáp án:** So hai phần tử trong cặp trước để biết phần tử nào có khả năng giảm min và phần tử nào có khả năng tăng max; sau đó chỉ so mỗi ứng viên với cực trị tương ứng.

**Câu 4.** Với a = [5,1,5,1], nếu yêu cầu chỉ số đầu tiên của min và max thì kết quả là gì?  
**Đáp án:** min = 1 tại chỉ số **1**, max = 5 tại chỉ số **0**.

**Câu 5.** Vì sao cả hai cách tìm min/max đều có độ phức tạp Θ(n)?  
**Đáp án:** Đều phải xem tất cả n phần tử trong trường hợp tổng quát; phương pháp theo cặp chỉ giảm **hệ số của số phép so sánh**, không đổi bậc tuyến tính.

**Câu 6.** Nếu dữ liệu đã được sắp tăng và được bảo đảm không thay đổi, min/max của toàn mảng nằm ở đâu?  
**Đáp án:** Min ở phần tử đầu, max ở phần tử cuối; đọc hai phần tử mất O(1) với mảng có truy cập ngẫu nhiên.

## 13. Ghi nhớ

- **Một cực trị:** quét một lần, **n−1 phép so sánh**, Θ(n) thời gian, O(1) bộ nhớ phụ.
- **Hai cực trị, làm độc lập:** **2n−2 phép so sánh**.
- **Hai cực trị, theo cặp:** **⌈3n/2⌉−2 phép so sánh** với n ≥ 1; đạt cận tối ưu trường hợp xấu nhất trong mô hình so sánh.
- **Bản chất tiết kiệm:** mỗi cặp cần một phép so nội bộ, sau đó chỉ đưa **ứng viên min** so với min và **ứng viên max** so với max.
- **Chọn chỉ số đúng:** thống nhất cách xử lý phần tử bằng nhau, trường hợp rỗng và quan hệ so sánh của bài toán.

Không cần sắp xếp khi chỉ chọn min/max. Hãy ưu tiên một lượt quét khi muốn cài đặt đơn giản; dùng phương pháp theo cặp khi cần giảm số phép so sánh và vẫn giữ O(1) bộ nhớ phụ.