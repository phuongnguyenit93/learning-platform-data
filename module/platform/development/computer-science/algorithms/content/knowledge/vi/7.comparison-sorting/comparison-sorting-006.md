# Shell sort và vai trò của dãy bước nhảy

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả **Shell sort** như một chuỗi các lượt **insertion sort có bước nhảy** (gapped insertion sort) và phân biệt nó với insertion sort thông thường.
2. Hiểu **dãy bước nhảy (gap sequence)** quyết định cách chia các nhóm vị trí, thứ tự xử lý và chi phí di chuyển phần tử.
3. Tự mô phỏng một lượt `gap = h`, kiểm tra bất biến **h-sorted**, giải thích tại sao lượt cuối `gap = 1` bảo đảm mảng được sắp xếp.
4. Cài đặt Shell sort tăng dần trong Java 17+, kiểm thử mảng rỗng, mảng trùng, số âm và giải thích đầu ra từng lượt.
5. Phân biệt các đặc tính: **in-place**, **không bảo đảm ổn định**, thời gian phụ thuộc dãy gap, bộ nhớ phụ `O(1)`.
6. So sánh các lựa chọn dãy gap phổ biến mà không nhầm hiệu quả thực nghiệm với một bảo đảm lý thuyết.

## 1. Trực giác: sửa nhược điểm của insertion sort bằng cách di chuyển xa

**Insertion sort** thông thường duyệt phần tử từ trái sang phải, đưa mỗi phần tử vào đúng chỗ trong đoạn đã có thứ tự bằng cách dịch các giá trị lớn hơn sang phải. Nó rất hiệu quả trên dữ liệu gần có thứ tự, nhưng với mảng đảo ngược, một phần tử nhỏ ở gần cuối có thể phải dịch qua gần hết mảng. Độ phức tạp tệ nhất của insertion sort là `Θ(n²)` phép so sánh/di chuyển.

**Shell sort** cải tiến ý tưởng bằng cách cho các phần tử **di chuyển qua những khoảng xa hơn một vị trí ở các lượt đầu**, rồi giảm dần khoảng cách:

```text
Insertion sort thông thường: khoảng cách giữa hai phần tử so sánh = 1.

Shell sort:
     gap = 4  -> chỉnh các vị trí cách nhau 4
     gap = 2  -> chỉnh các vị trí cách nhau 2
     gap = 1  -> insertion sort hoàn thiện mảng
```

Khi `gap` lớn, một phần tử ở phía sau có thể tiến về phía trước nhanh hơn vì mỗi lần dịch chuyển nhảy qua nhiều chỉ số. Các lượt sau với gap nhỏ hơn làm mảng ngày càng gần đúng thứ tự cuối. Lượt `gap=1` đóng vai trò hoàn thiện việc sắp xếp.

Shell sort là **thuật toán sắp xếp so sánh** trên dãy, thường được cài đặt **tại chỗ** trên mảng. Nó không dùng thêm một mảng độ dài `n`; chỉ cần một vài biến tạm. Tên “Shell” gắn với Donald Shell, người đề xuất thuật toán vào năm 1959.

Bài toán được đặc tả ở đây:

- **Input:** mảng `int[] a` không `null`, độ dài `n≥0`, có thể chứa số âm, phần tử trùng, các giá trị `int` cực trị.
- **Output:** chính mảng `a` sau khi sắp xếp **không giảm**, tức `a[0] ≤ a[1] ≤ ... ≤ a[n-1]`.
- **Bảo toàn:** không thêm/bỏ phần tử, không đổi số lần xuất hiện của mỗi giá trị.
- **Chính sách bằng nhau:** chỉ yêu cầu thứ tự theo giá trị; thuật toán **không bảo đảm giữ thứ tự tương đối của những bản ghi có khóa bằng nhau**.

Nếu cần thứ tự giảm dần hoặc sắp bản ghi theo Comparator, phải đổi phép so sánh một cách nhất quán và định nghĩa rõ quan hệ thứ tự.

## 2. Một lượt gap h làm gì?

Giả sử `h` là số nguyên dương. Các chỉ số được chia theo **phần dư khi chia cho h**. Mỗi nhóm gồm những vị trí cách nhau đúng `h`:

```text
n = 8, h = 4

Nhóm 0: chỉ số 0, 4
Nhóm 1: chỉ số 1, 5
Nhóm 2: chỉ số 2, 6
Nhóm 3: chỉ số 3, 7
```

Một lượt **h-insertion sort** sắp từng nhóm theo thứ tự tăng dần, nhưng **ghi trực tiếp về đúng những vị trí của nhóm ấy trên mảng ban đầu**. Không cần tách nhóm thành mảng phụ.

Ví dụ:

```text
Trước gap = 4:
Chỉ số:  0  1  2  3  4  5  6  7
Giá trị: 9  8  3  7  5  6  4  1

Nhóm 0: [9,5] -> [5,9]
Nhóm 1: [8,6] -> [6,8]
Nhóm 2: [3,4] -> [3,4]
Nhóm 3: [7,1] -> [1,7]

Sau gap = 4:
Giá trị: 5  6  3  1  9  8  4  7
```

Mảng chưa tăng dần từ trái sang phải vì `5 > 3` và `6 > 1`. Tuy nhiên, nó thỏa thuộc tính **4-sorted**: mỗi phần tử ở chỉ số `i≥4` lớn hơn hoặc bằng phần tử ở `i-4`.

### Định nghĩa h-sorted

Với mảng `a` và `h≥1`, gọi mảng là **h-sorted** nếu:

\[
\forall i\in[h,n-1],\qquad a[i-h]\le a[i].
\]

Tương đương, tất cả các dãy con:

\[
a[r],a[r+h],a[r+2h],\ldots
\]

với `r=0,1,\ldots,h-1` (nếu chỉ số còn hợp lệ) đều không giảm.

- `h=4`: chỉ cần các nhóm cách nhau 4 có thứ tự.
- `h=2`: các vị trí chẵn tạo một dãy đã sắp xếp và các vị trí lẻ tạo một dãy đã sắp xếp.
- **`h=1`:** chính toàn bộ mảng phải không giảm. Vì vậy **một lượt insertion sort với gap 1 đủ để hoàn tất sắp xếp**, bất kể mảng ban đầu ra sao.

Đây là **bất biến sau một lượt gap**, không có nghĩa các lượt sau luôn giữ nguyên thuộc tính `h-sorted` của mọi gap đã dùng trước. Điều ta cần để chứng minh đầu ra đúng là lượt cuối `h=1` sắp toàn bộ mảng.

## 3. Cơ chế gapped insertion sort

Với một gap `h`, duyệt chỉ số `i` từ `h` đến `n-1`:

1. Lưu `temp = a[i]` để không mất phần tử đang chèn.
2. Bắt đầu `j=i`.
3. Trong khi `j≥h` và `a[j-h]>temp`, dời `a[j-h]` sang ô `a[j]`; rồi giảm `j` đi `h`.
4. Ghi `temp` vào `a[j]` sau khi đã tìm được vị trí thích hợp **trong nhóm chỉ số cùng phần dư modulo h**.
5. Chuyển sang `i` tiếp theo.

Giả mã cho một lượt:

```text
GAPPED_INSERTION(a, h):
    yêu cầu: 1 <= h < n  (với n >= 2)
    for i từ h đến n-1:
        temp <- a[i]
        j <- i

        while j >= h và a[j-h] > temp:
            a[j] <- a[j-h]
            j <- j-h

        a[j] <- temp
```

Điểm khác insertion sort thông thường là `j` giảm **h**, không phải 1. Mỗi lượt chèn chỉ so sánh/di chuyển trong một nhóm đồng dư `j mod h`.

Sự so sánh `a[j-h] > temp`, thay vì `>=`, giúp một lượt chèn không chủ động đảo thứ tự các phần tử **bằng khóa trong cùng nhóm**; tuy nhiên **toàn bộ Shell sort vẫn có thể không ổn định**, vì các nhóm giao thoa theo những gap khác nhau ở các lượt tiếp theo.

### Ví dụ chèn với h = 2

Giả sử một thời điểm của lượt gap 2 có các vị trí chẵn như sau:

```text
Chỉ số chẵn:  0    2    4    6
Giá trị:     3    5    9    4
                            ^
                          temp=4
```

Khi đưa 4 vào nhóm: dịch 9 sang vị trí 6, dịch 5 sang vị trí 4, rồi ghi 4 tại vị trí 2. Dãy vị trí chẵn trở thành `[3,4,5,9]`. Các phần tử ở vị trí lẻ không bị thay đổi bởi lần chèn này.

Vì Shell sort dùng nhiều lượt gap, một phần tử có thể tiến xa chỉ trong một lần chèn. Đó là lý do việc chọn khoảng cách ban đầu và lộ trình giảm gap có thể cải thiện đáng kể hiệu năng so với insertion sort trực tiếp trên mảng rất lộn xộn.

## 4. Dãy bước nhảy quyết định quá trình sắp xếp

**Dãy bước nhảy (gap sequence)** là một dãy số nguyên dương `h_1,h_2,...,h_t`, thường dùng theo **thứ tự giảm dần**, với **`h_t=1`** để bảo đảm sắp xếp hoàn chỉnh.

Mỗi gap xác định:

- Những cặp vị trí nào được so sánh và có thể dịch chuyển trong một lượt.
- Số **nhóm đồng dư** theo gap và độ dài mỗi nhóm.
- Khả năng đưa phần tử về gần vị trí cuối một cách nhanh chóng.
- Tổng số lượt, số so sánh, số lần dịch chuyển và đặc điểm truy cập bộ nhớ.

Một dãy gap không thể được đánh giá chỉ bằng **số lượt**. Dãy có ít lượt hơn đôi khi khiến lượt `gap=1` phải sửa rất nhiều sai lệch còn sót lại; dãy có thêm các bước trung gian hữu ích lại có thể giảm tổng công việc.

### Dãy halving (Shell gốc)

Một lựa chọn dễ hiểu và dễ cài:

\[
h_1=\lfloor n/2\rfloor,\quad
h_{k+1}=\lfloor h_k/2\rfloor
\]

cho đến khi nhận được `1`, sau đó kết thúc. Ví dụ:

| Kích thước `n` | Dãy gap thực hiện |
| ---: | --- |
| 0 hoặc 1 | Không cần lượt nào |
| 5 | `2,1` |
| 8 | `4,2,1` |
| 10 | `5,2,1` |
| 16 | `8,4,2,1` |
| 25 | `12,6,3,1` |

Ưu điểm: rất dễ tạo, không cần lưu danh sách gap, số lượt `O(log n)` với `n≥2`. Nhược điểm: hiệu năng trường hợp xấu có thể tới bậc hai; các gap là bội/chia đôi liên tiếp nên ở nhiều lượt, các vị trí được ghép theo những cấu trúc tương đối giống nhau.

**Không nên kết luận halving “luôn kém” hoặc một dãy khác “luôn tốt nhất”** chỉ dựa trên một mảng ngắn hay một phép đo.

### Một số dãy gap thường gặp

Các dãy dưới đây thường được **liệt kê tăng dần trong tài liệu** nhưng phải **lấy các giá trị nhỏ hơn `n` và chạy theo thứ tự giảm dần** trong Shell sort:

| Tên dãy | Các giá trị tăng dần ban đầu | Ý tưởng / lưu ý |
| --- | --- | --- |
| **Hibbard** | `1,3,7,15,31,...` với `2^k-1`, `k≥1` | Tạo gap không chỉ là những lần chia đôi liên tiếp; dùng `gap<n`. |
| **Knuth** | `1,4,13,40,121,...` theo `h_{k+1}=3h_k+1` từ `h_1=1` | Đơn giản và thông dụng; với `n=20`, thực hiện `13,4,1`. |
| **Ciura** | `1,4,10,23,57,132,301,701,1750` | Các gap thực nghiệm thường dùng cho cỡ dữ liệu phù hợp; muốn mở rộng lên kích thước lớn phải công bố rõ quy tắc sinh thêm. |
| **Halving** | Sinh từ `⌊n/2⌋` rồi chia đôi dần | Phụ thuộc trực tiếp vào `n`; ví dụ `n=20` có `10,5,2,1`. |

Một phần mềm có thể dùng dãy khác nếu đáp ứng hợp đồng đúng đắn. Không có bảo đảm rằng dãy Ciura, Knuth hay Hibbard sẽ chạy nhanh nhất trên **mọi** loại đầu vào, kích thước, phần cứng và chi phí so sánh.

### Quy tắc chọn gap hợp lệ

Với `n≥2`, một lịch trình dễ kiểm soát nên:

1. Chỉ dùng gap nguyên dương; thường bỏ gap `h≥n` vì lượt đó không thực hiện lần chèn nào.
2. Chạy từ gap lớn đến gap nhỏ, thường **giảm nghiêm ngặt** để không xử lý lặp một gap không cần thiết.
3. **Kết thúc bằng gap 1**; nếu chỉ chạy đến gap 2, các nhóm chẵn/lẻ có thể đã sắp nhưng mảng vẫn chưa tăng dần.
4. Được xác định rõ khi `n` nhỏ, khi một gap trùng nhau hoặc khi sinh gap có nguy cơ tràn kiểu nguyên.
5. Được đo/kiểm thử trên dạng dữ liệu cần xử lý thật, đồng thời phân biệt thực nghiệm với giới hạn toán học.

Tính đúng không đòi hỏi các gap phải là bội số của nhau. Đó là một trong những lý do tồn tại nhiều dãy gap được nghiên cứu: **thứ tự và cấu trúc gap thay đổi cách các phần tử gặp nhau** trong những lượt sắp xếp trước lượt cuối.

## 5. Mô phỏng đầy đủ: gap 4 → 2 → 1

Xét đầu vào:

```text
a = [9, 8, 3, 7, 5, 6, 4, 1]
n = 8
gap = floor(n/2) = 4
```

### Lượt 1 — gap = 4

Các nhóm có hai phần tử:

- Chỉ số `0,4`: `[9,5]` → `[5,9]`.
- Chỉ số `1,5`: `[8,6]` → `[6,8]`.
- Chỉ số `2,6`: `[3,4]` → giữ nguyên.
- Chỉ số `3,7`: `[7,1]` → `[1,7]`.

Kết quả:

```text
[5, 6, 3, 1, 9, 8, 4, 7]
```

Mọi phần tử ở chỉ số `i≥4` đều không nhỏ hơn phần tử ở chỉ số `i-4`. Mảng đã **4-sorted**, nhưng chưa sắp xếp toàn bộ.

### Lượt 2 — gap = 2

Chia hai nhóm theo chỉ số:

- **Vị trí chẵn** `0,2,4,6`: `[5,3,9,4]` → `[3,4,5,9]`.
- **Vị trí lẻ** `1,3,5,7`: `[6,1,8,7]` → `[1,6,7,8]`.

Ghép về đúng chỉ số:

```text
[3, 1, 4, 6, 5, 7, 9, 8]
```

Mảng hiện **2-sorted**: những chỉ số chẵn và những chỉ số lẻ riêng rẽ đều có giá trị không giảm. Vẫn còn cặp kề nhau đảo thứ tự, như `3>1` hay `6>5`.

### Lượt 3 — gap = 1

Tất cả vị trí thuộc một nhóm. Insertion sort theo từng phần tử sẽ hoàn thiện thứ tự:

```text
[1, 3, 4, 5, 6, 7, 8, 9]
```

Chỉ cần nhớ **mỗi lượt gap làm các nhóm tương ứng có thứ tự**; lượt gap 1 mới là điều kiện trực tiếp xác nhận toàn mảng có thứ tự. Đừng nhầm “sau gap 4 nhìn gần đúng hơn” với “đã hoàn tất sắp xếp”.

| Lượt | Gap | Mảng sau lượt | Bất biến vừa thiết lập |
| ---: | ---: | --- | --- |
| Trước | — | `[9,8,3,7,5,6,4,1]` | Chưa có yêu cầu |
| 1 | 4 | `[5,6,3,1,9,8,4,7]` | 4-sorted |
| 2 | 2 | `[3,1,4,6,5,7,9,8]` | 2-sorted |
| 3 | 1 | `[1,3,4,5,6,7,8,9]` | 1-sorted = đã sắp xếp |

## 6. Java 17+: Shell sort với dãy gap halving

Ví dụ này là chương trình đầy đủ lưu dưới tên **`ShellSortDemo.java`**. Nó sắp xếp mảng `int[]` **tại chỗ**, in mảng sau từng lượt gap và kiểm tra hậu điều kiện. Hàm yêu cầu đầu vào không `null`.

```java
import java.util.Arrays;
import java.util.Objects;

public class ShellSortDemo {
    public static void shellSort(int[] a) {
        Objects.requireNonNull(a, "a");

        for (int gap = a.length / 2; gap > 0; gap /= 2) {
            for (int i = gap; i < a.length; i++) {
                int value = a[i];
                int j = i;

                while (j >= gap && a[j - gap] > value) {
                    a[j] = a[j - gap];
                    j -= gap;
                }

                a[j] = value;
            }

            System.out.println(
                    "gap=" + gap + ": " + Arrays.toString(a));
        }
    }

    public static boolean isSorted(int[] a) {
        Objects.requireNonNull(a, "a");

        for (int i = 1; i < a.length; i++) {
            if (a[i - 1] > a[i]) {
                return false;
            }
        }

        return true;
    }

    public static void main(String[] args) {
        int[] a = {9, 8, 3, 7, 5, 6, 4, 1};
        System.out.println("before: " + Arrays.toString(a));

        shellSort(a);

        System.out.println("after: " + Arrays.toString(a));
        System.out.println("sorted: " + isSorted(a));
    }
}
```

Biên dịch và chạy với JDK 17 hoặc mới hơn:

```bash
javac ShellSortDemo.java
java ShellSortDemo
```

Đầu ra chuẩn chính xác:

```text
before: [9, 8, 3, 7, 5, 6, 4, 1]
gap=4: [5, 6, 3, 1, 9, 8, 4, 7]
gap=2: [3, 1, 4, 6, 5, 7, 9, 8]
gap=1: [1, 3, 4, 5, 6, 7, 8, 9]
after: [1, 3, 4, 5, 6, 7, 8, 9]
sorted: true
```

**Giải thích từng phần của code:**

- `for (gap = n/2; gap > 0; gap /= 2)` sinh dãy gap halving và kết thúc sau gap 1. Với `n=0` hoặc `n=1`, vòng không chạy; mảng đã có thứ tự.
- `i` chạy từ `gap`, vì chỉ các phần tử có vị trí đứng sau ít nhất một phần tử cùng nhóm mới cần chèn.
- `value=a[i]` giữ phần tử cần đưa vào vị trí đúng, trong khi các phần tử lớn hơn bị dịch về bên phải theo khoảng `gap`.
- `j>=gap` bảo đảm `j-gap` luôn là chỉ số hợp lệ.
- `a[j-gap]>value` sắp xếp **tăng dần**. Không dùng phép trừ `a[j-gap]-value` làm điều kiện so sánh vì phép trừ hai `int` có thể tràn số.
- `a[j]=value` ghi phần tử đã lưu vào đúng chỗ sau khi dịch; nếu đã đúng chỗ, đó chỉ là phép gán lại cùng giá trị.
- `shellSort` thay đổi **chính mảng đầu vào**, không trả mảng mới. Dòng in từng gap là để học tập; trong thư viện thực tế có thể bỏ thao tác in.
- `isSorted` chỉ kiểm tra quan hệ thứ tự, chưa tự chứng minh tính **bảo toàn đa tập phần tử**. Để kiểm thử đầy đủ có thể so với bản sao đã gọi `Arrays.sort`.

Đây là Java 17+ thuần túy, dùng các API chuẩn `Arrays` và `Objects`. Với phần tử số âm, phần tử trùng hoặc giá trị `Integer.MIN_VALUE` và `Integer.MAX_VALUE`, phép so sánh `>` vẫn hợp lệ. Nếu mảng `null`, chương trình ném `NullPointerException` theo `Objects.requireNonNull`; đây là một phần của hợp đồng hàm ví dụ.

## 7. Chứng minh tính đúng và tính dừng

### Bất biến trong một lượt gap h

Với `h>0` cố định, khi xử lý `i` theo thứ tự tăng dần, ta chỉ chèn `a[i]` vào nhóm vị trí:

\[
i\bmod h,\; i\bmod h+h,\; i\bmod h+2h,\ldots,i.
\]

**Bất biến:** trước khi chèn phần tử tại `i`, những phần tử đã xử lý trước đó của cùng nhóm tạo thành một dãy không giảm; sau khi chèn bằng cách dịch các phần tử lớn hơn sang phải, nhóm ấy vẫn không giảm.

- **Khởi tạo:** phần tử đầu tiên của mỗi nhóm (một phần tử) hiển nhiên đã có thứ tự.
- **Duy trì:** `value` được đưa về vị trí sau các phần tử `≤value` và trước các phần tử `>value` trong tiền tố cùng nhóm. Các phần tử khác chỉ bị dịch một vị trí nhóm, nên thứ tự tiền tố được giữ.
- **Kết thúc lượt:** mọi phần tử mỗi nhóm đã được đưa vào đúng vị trí trong nhóm; do đó toàn mảng là **h-sorted**.

### Vì sao toàn bộ Shell sort sắp đúng?

Tại **lượt cuối `h=1`**, chỉ có một nhóm chứa mọi chỉ số `0,1,...,n-1`. Bất biến của gapped insertion sort với `h=1` kết luận cả nhóm được sắp xếp không giảm, tức hậu điều kiện sắp xếp đúng.

Ngoài ra, mỗi bước chỉ **dịch và chèn lại những phần tử đã có**, không tạo giá trị mới và không bỏ phần tử, nên đa tập giá trị được bảo toàn.

Vì thế, **bất kỳ dãy gap hữu hạn gồm các số nguyên dương, được xử lý hợp lệ và có lượt cuối `gap=1`, đều cho kết quả sắp xếp đúng** nếu từng lượt gapped insertion sort được cài đúng. Hiệu năng có thể khác rất nhiều, nhưng điều kiện đúng đắn cơ bản này không phụ thuộc vào việc chọn halving, Knuth hay Ciura.

### Tính dừng

- Số gap trong dãy halving là hữu hạn: `gap` bắt đầu từ `⌊n/2⌋`, mỗi lần chia nguyên cho 2 và cuối cùng về 0.
- Ở mỗi lượt gap, `i` tăng từ `gap` đến `n-1` nên chỉ có hữu hạn bước.
- Trong vòng `while`, `j` giảm đúng `gap>0`, luôn giữ không âm; không thể lặp vô hạn.

Thuật toán vì vậy dừng với mọi mảng `int[]` hữu hạn hợp lệ.

## 8. Độ phức tạp: điều gì chắc chắn, điều gì phụ thuộc gap?

### Chi phí một lượt gap

Với một gap `h`, dãy được chia thành `h` nhóm (một số nhóm có thể rỗng nếu `h>n`). Mỗi nhóm có khoảng `n/h` phần tử. Insertion sort trên nhóm độ dài `m` có chi phí tệ nhất `O(m²)` phép so sánh/dịch chuyển.

Cộng chi phí của các nhóm cho một lượt:

\[
O\!\left(\sum_{r=0}^{h-1}m_r^2\right)
=O\!\left(n+\frac{n^2}{h}\right)
\quad (1\le h<n).
\]

Với `h` lớn, mỗi nhóm ngắn hơn, nên lượt ấy có thể xử lý tương đối nhanh. Với `h=1`, chặn trên của một lượt chính là `O(n²)` của insertion sort thông thường. Nhưng các lượt gap lớn trước đó **có thể làm lượt 1 nhẹ hơn đáng kể** trên dữ liệu thực tế.

### Trường hợp dãy halving

- Có `O(log n)` lượt gap khi `n≥2`.
- Cộng các chặn theo từng lượt gap của dãy chia đôi cho chặn trên tệ nhất **`O(n²)`**.
- Với mảng đã sắp xếp, mỗi lượt vẫn cần quét các vị trí, còn vòng dịch hầu như không chạy; tổng công việc theo cách cài này là **`O(n log n)`**.
- **Bộ nhớ phụ `O(1)`**: biến `gap`, `i`, `j`, `value`; mảng đầu vào được sửa tại chỗ.
- Với các dãy gap khác, số lượt và giới hạn chi phí thay đổi; không được tự nhận “mọi Shell sort là `O(n log n)` trong worst-case”.

**Chú ý cách phát biểu:** `O(n²)` ở đây là một **chặn trên** an toàn của bản halving. Để phát biểu một cận chặt `Θ(...)` cho một họ gap khác cần phân tích cụ thể, không suy từ vài kết quả benchmark.

### Vì sao dãy bước nhảy có thể ảnh hưởng mạnh?

1. **Gap lớn giúp phần tử đi xa:** ví dụ phần tử nhỏ nằm sát cuối dãy có thể được chuyển lên rất nhiều vị trí chỉ sau ít lần dịch.
2. **Gap trung gian giúp trộn các nhóm:** một lịch trình toàn những gap có liên hệ chia hết mạnh có thể để lại mẫu đảo thứ tự khó sửa ở lượt 1; những khoảng khác nhau tạo nhiều cặp vị trí cần so sánh hơn.
3. **Gap quá nhỏ quá sớm:** gần giống insertion sort trên dãy còn rất lộn xộn, làm nhiều phép dịch.
4. **Gap quá lớn hoặc lặp lại:** nếu `h≥n`, không có lần chèn nào; nếu lặp h, mảng đã h-sorted nên lượt sau thường ít tác dụng.
5. **Đặc tính truy cập bộ nhớ và CPU:** gap lớn dẫn tới truy cập cách xa nhau; số lượt, lượng dịch và tính cục bộ bộ nhớ cùng ảnh hưởng thời gian thật.
6. **Phân phối dữ liệu và kích thước:** mảng gần sắp, mảng đảo, mảng ngẫu nhiên, nhiều khóa trùng hay gần như không trùng có thể cho những kết quả đo khác nhau.

Tổng thời gian thực nghiệm cần đo **cả quá trình**. Một dãy có ít phép so sánh chưa chắc luôn thắng khi phải đánh đổi bằng truy cập bộ nhớ bất lợi; cũng không thể đánh giá bằng cách chỉ nhìn số gap.

## 9. Shell sort có ổn định không?

**Không bảo đảm ổn định (not stable).** Sắp xếp ổn định nghĩa là nếu hai bản ghi có **khóa bằng nhau**, thứ tự tương đối của chúng trong đầu ra phải giống thứ tự đầu vào.

Phản ví dụ với `n=4`, gap halving `2,1`. Ký hiệu `2A` và `2B` là hai bản ghi khác nhau nhưng cùng khóa số `2`:

```text
Đầu vào:          [2A, 3, 1, 2B]
                         gap=2
Nhóm chỉ số 0,2:  [2A,1] -> [1,2A]
Nhóm chỉ số 1,3:  [3,2B] -> [2B,3]

Sau gap=2:        [1, 2B, 2A, 3]
Sau gap=1:        [1, 2B, 2A, 3]
```

Ở đầu vào, `2A` đứng trước `2B`; ở đầu ra, `2B` đứng trước `2A`, dù khóa của hai bản ghi bằng nhau. Lượt gap 1 có thể dùng phép so sánh nghiêm `>` và không hoán đổi trực tiếp các khóa bằng nhau, nhưng **sự đảo thứ tự đã xảy ra ở lượt gap 2**. Do đó dùng `>` thay `>=` không thể biến toàn bộ Shell sort thành ổn định.

- Với **số nguyên thuần túy**, hai giá trị 2 không mang danh tính nên đầu ra vẫn là một dãy giá trị đúng.
- Với **bản ghi**, nếu nghiệp vụ bắt buộc bảo toàn thứ tự giữa các khóa bằng nhau, phải chọn thuật toán ổn định hoặc áp dụng chiến lược thêm chỉ số đầu vào vào khóa so sánh (khi chấp nhận chi phí/đặc tả mới).

Một thuật toán có thể đúng về **thứ tự giá trị** nhưng sai với hợp đồng nghiệp vụ yêu cầu **ổn định**. Vì vậy tính ổn định cần được công bố ngay trong đặc tả.

## 10. So sánh Shell sort với một số thuật toán cùng nhóm

| Thuật toán | Ý tưởng | Đặc điểm nổi bật |
| --- | --- | --- |
| **Insertion sort** | Chèn từng phần tử vào tiền tố đã có thứ tự, bước nhảy 1 | Đơn giản, ổn định nếu dùng phép so sánh nghiêm và cài đúng; tệ nhất `Θ(n²)` |
| **Shell sort** | Nhiều lượt insertion sort với gap giảm dần và kết thúc ở 1 | In-place `O(1)` bộ nhớ phụ, không ổn định; thời gian phụ thuộc dãy gap |
| **Merge sort** | Chia nhỏ rồi trộn các đoạn có thứ tự | Có thể ổn định; thời gian `O(n log n)` với thiết kế chuẩn; bản cài đặt mảng thường cần `O(n)` bộ nhớ phụ |
| **Heap sort** | Xây heap rồi lần lượt lấy phần tử cực trị | Thời gian tệ nhất `O(n log n)` và có cài đặt `O(1)` bộ nhớ phụ; thông thường không ổn định |

**Khi cân nhắc Shell sort:** thích hợp để nghiên cứu mối quan hệ giữa các lượt tiền xử lý và chi phí sắp xếp, hoặc trong bối cảnh cần code nhỏ, in-place và dữ liệu kích thước vừa phải. Không nên mặc định chọn nó cho mọi tập dữ liệu lớn hoặc hệ thống cần worst-case `O(n log n)`/độ ổn định; hãy đối chiếu yêu cầu thực và thuật toán thư viện sẵn có.

Một lựa chọn thực tế trong Java để sắp `int[]` là `Arrays.sort(a)`; đó là một API thư viện chứ **không phải Shell sort**. Có thể dùng nó làm đối chứng đúng đắn trong các bài test, nhưng không gán đặc tính nội bộ của một thuật toán cụ thể cho mọi phiên bản thư viện mà không kiểm tra hợp đồng tương ứng.

## 11. Các lỗi cài đặt và hiểu sai thường gặp

1. **Quên gap cuối bằng 1.** Với gap cuối là 2, các phần tử chẵn/lẻ có thứ tự riêng nhưng toàn mảng có thể vẫn lộn xộn.
2. **Giảm `j` đi 1 thay vì `gap`.** Như vậy vòng chèn không còn chỉ xử lý các phần tử trong cùng nhóm, sai ý nghĩa h-sorted.
3. **Dùng `i=0` ở mọi lượt rồi truy cập `a[i-gap]` mà không chặn chỉ số.** Đúng hơn là bắt đầu từ `i=gap` và kiểm tra `j>=gap`.
4. **Dùng `j>gap` thay cho `j>=gap`.** Khi `j=gap`, phần tử `a[0]` vẫn cần có cơ hội được so sánh; bỏ nó có thể làm nhóm không được sắp xếp.
5. **Quên lưu `value` trước khi dịch.** Việc dịch phần tử có thể ghi đè giá trị đang cần chèn.
6. **Chia gap bằng cách không bảo đảm tiến tới 1.** Một dãy custom có gap 0, gap âm, gap lặp hoặc không có gap 1 có thể làm lặp sai, không xử lý gì hoặc không sắp hoàn chỉnh.
7. **Kết luận thuật toán ổn định vì vòng while dùng `>`.** Các lượt gap khác có thể đổi thứ tự các bản ghi bằng khóa, như phản ví dụ ở mục 9.
8. **Khẳng định worst-case `O(n log n)` cho mọi dãy gap.** Chưa được chứng minh; tính toán phụ thuộc gap cụ thể.
9. **Đếm một vòng `while` có thể chạy dài rồi lập tức kết luận mọi lượt đều bậc hai.** Cần xét chiều dài từng nhóm `n/h` và toàn bộ chuỗi gap.
10. **Chạy benchmark cùng phần in ra console.** In mảng sau mỗi lượt làm méo kết quả đo; nên bỏ `println` khi benchmark.
11. **Thay đổi input giữa các phép thử thuật toán.** Muốn so sánh hiệu năng công bằng, dùng bản sao các mảng có cùng nội dung và cùng cấu hình JVM/môi trường đo.
12. **Không kiểm thử dữ liệu trùng, âm, rỗng hay đảo ngược.** Các ca đó giúp phát hiện lỗi chỉ số, phép so sánh và hợp đồng.

## 12. Kiểm thử kết quả và lựa chọn dãy gap

Để kiểm tra tính đúng, dùng các nhóm đầu vào sau:

| Trường hợp | Input ví dụ | Output kỳ vọng |
| --- | --- | --- |
| Rỗng | `[]` | `[]` |
| Một phần tử | `[5]` | `[5]` |
| Đã tăng dần | `[1,2,3,4]` | `[1,2,3,4]` |
| Đảo ngược | `[5,4,3,2,1]` | `[1,2,3,4,5]` |
| Có số âm | `[0,-4,2,-1]` | `[-4,-1,0,2]` |
| Nhiều phần tử trùng | `[4,2,4,2,4]` | `[2,2,4,4,4]` |
| Tất cả trùng | `[7,7,7]` | `[7,7,7]` |
| Cực trị nguyên | `[2147483647,-2147483648,0]` | `[-2147483648,0,2147483647]` |

Ngoài so sánh toàn bộ mảng với bản sao được `Arrays.sort`, nên xác minh:

- **Có thứ tự:** `a[i-1]<=a[i]` với mọi `i` từ 1 đến `n-1`.
- **Bảo toàn dữ liệu:** số lần xuất hiện mỗi giá trị trong kết quả bằng trong đầu vào.
- **Kết quả độc lập với lựa chọn dãy gap hợp lệ:** các dãy gap hợp lệ có thể cho chi phí và trạng thái trung gian khác nhau, nhưng với `int[]`, kết quả sắp tăng dần phải cùng một dãy giá trị.
- **Đặc tính không ổn định:** nếu bài toán sử dụng bản ghi có khóa bằng nhau, test phải kiểm tra yêu cầu về thứ tự tương đối riêng; `Arrays.toString` trên mảng số nguyên không cho thấy danh tính.

Để đo ảnh hưởng của gap:

1. Cố định kích thước `n` và bộ dữ liệu đầu vào.
2. Chạy halving, Knuth hoặc Ciura trên **những bản sao giống nhau**; loại bỏ in console khi đo.
3. Lặp đủ lần và cân nhắc hiệu ứng JIT, khởi động JVM, GC và nhiễu hệ thống.
4. Ghi số so sánh và số dịch chuyển (nếu muốn hiểu thuật toán), đồng thời đo thời gian thực tế một cách nhất quán.
5. Thử nhiều kiểu dữ liệu: ngẫu nhiên, gần tăng dần, đảo ngược, nhiều khóa trùng, kích thước nhỏ/lớn.
6. Báo kết quả **theo bộ dữ liệu và môi trường đã đo**, không suy ra chứng minh worst-case từ vài benchmark.

Nếu dùng kiểu đối tượng mà so sánh phức tạp (ví dụ chuỗi dài), **chi phí mỗi phép so sánh có thể không phải `O(1)`**; phân tích theo số lần so sánh cần được kết hợp với chi phí so sánh khóa thật.

## 13. Bài tập tự kiểm tra

**Bài 1 — Nhóm theo gap.** Với `a=[9,8,3,7,5,6,4,1]` và `h=4`, liệt kê các nhóm chỉ số cùng phần dư modulo 4, và trạng thái mảng sau khi tất cả nhóm được sắp.

**Bài 2 — Vì sao bắt buộc gap 1?** Cho `a=[2,1,4,3]`. Nếu chỉ thực hiện lượt gap 2 rồi dừng, mảng đã sắp xếp toàn bộ chưa? Vì sao?

**Bài 3 — Dãy gap.** Với `n=20`, ghi dãy gap halving và dãy gap Knuth được dùng khi bỏ mọi gap `h≥n`, chạy các gap còn lại theo thứ tự giảm dần.

**Bài 4 — Mô phỏng.** Với `a=[9,8,3,7,5,6,4,1]`, hãy mô phỏng gap 2 sau gap 4; kiểm tra mọi cặp `a[i-2]<=a[i]` với `i≥2`.

**Bài 5 — Bất biến.** Tại sao chỉ cần chứng minh mỗi lượt tạo ra mảng h-sorted là đủ để chứng minh tính đúng của Shell sort có gap cuối bằng 1? Cần thêm lập luận nào về bảo toàn phần tử?

**Bài 6 — Không ổn định.** Với các bản ghi `[2A,3,1,2B]` và gap `2,1`, hãy tìm thứ tự cuối cùng. Bản ghi A có còn đứng trước B khi cả hai cùng khóa 2 không?

**Bài 7 — Chi phí.** Vì sao một lượt gap h có thể xem như h lượt insertion sort trên các nhóm độ dài xấp xỉ n/h? Điều đó nói gì về chi phí của gap rất lớn và gap 1?

**Bài 8 — Chọn thuật toán.** Một ứng dụng bắt buộc giữ thứ tự nhập của các bản ghi có cùng điểm và cần chặn worst-case `O(n log n)` cho mảng rất lớn. Có nên chọn Shell sort halving làm phương án mặc định không? Giải thích dựa trên yêu cầu, không dựa vào sở thích cá nhân.

### Đáp án gợi ý

1. Nhóm `(0,4):[9,5]`, `(1,5):[8,6]`, `(2,6):[3,4]`, `(3,7):[7,1]`. Sau lượt: `[5,6,3,1,9,8,4,7]`.
2. Chưa. Hai nhóm `(0,2):[2,4]` và `(1,3):[1,3]` đã có thứ tự; mảng `[2,1,4,3]` vẫn có `2>1`. Cần lượt gap 1.
3. Halving: `10,5,2,1`. Knuth: `13,4,1` (dãy tăng `1,4,13,40,...`, bỏ 40 vì `40≥20`).
4. Sau gap 2: `[3,1,4,6,5,7,9,8]`. Các vị trí chẵn `[3,4,5,9]` và lẻ `[1,6,7,8]` đều tăng.
5. Với gap 1, h-sorted đồng nghĩa `a[i-1]<=a[i]` cho mọi `i≥1`. Mỗi lần chèn chỉ dịch/gán lại giá trị có sẵn nên đa tập được bảo toàn.
6. Sau gap 2 và gap 1: `[1,2B,2A,3]`. `2B` đã đứng trước `2A` nên không ổn định.
7. Mỗi nhóm có độ dài khoảng `n/h` và insertion sort trên nhóm tốn tối đa bậc hai theo chiều dài nhóm. Cộng lại có chặn `O(n+n²/h)` cho một lượt; gap 1 là insertion sort toàn mảng.
8. Không nên chọn làm mặc định khi hai yêu cầu ấy là bắt buộc: Shell sort không bảo đảm ổn định, còn halving không cung cấp bảo đảm worst-case `O(n log n)`. Cần chọn thuật toán/cách cài phù hợp cả tính ổn định lẫn giới hạn thời gian.

## Ghi nhớ

Shell sort thực hiện **gapped insertion sort** ở nhiều bước nhảy, thường từ lớn về nhỏ và **kết thúc bằng 1**. Sau mỗi lượt gap h, các dãy con gồm vị trí cách nhau h được sắp xếp; lượt **gap 1** hoàn thiện thứ tự của toàn mảng. **Dãy bước nhảy là lựa chọn quan trọng nhất chi phối số lượt, mẫu so sánh và chi phí thực tế**. Thuật toán dùng `O(1)` bộ nhớ phụ và cài tại chỗ, nhưng **không bảo đảm ổn định** và không có một độ phức tạp thời gian chung cho mọi lựa chọn gap. Hãy chứng minh tính đúng riêng với hiệu năng, rồi đánh giá dãy gap trên dữ liệu và yêu cầu cụ thể.
