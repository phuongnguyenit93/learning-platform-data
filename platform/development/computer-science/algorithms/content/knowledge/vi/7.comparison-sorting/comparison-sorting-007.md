# Sắp xếp trộn (Merge Sort)

**Merge sort (sắp xếp trộn)** là thuật toán sắp xếp dựa trên **chia để trị (divide and conquer)**: chia dãy thành các phần nhỏ, sắp xếp từng phần rồi **trộn hai phần đã sắp xếp** thành một dãy có thứ tự. Một cách cài đặt chuẩn dùng thêm vùng nhớ tạm, chạy **O(n log n)** trong trường hợp xấu nhất và có thể **ổn định (stable)**, nghĩa là các phần tử có khóa bằng nhau giữ nguyên thứ tự tương đối ban đầu.

Bài học thuộc nhóm **sắp xếp so sánh**. Điểm cốt lõi cần hiểu không chỉ là chia mảng làm đôi, mà còn là **bất biến của bước merge**, lý do chi phí toàn thuật toán là O(n log n), cách bảo đảm tính ổn định và những đánh đổi về bộ nhớ.

## 1. Bài toán và ý tưởng chia để trị

Cho mảng a gồm n phần tử và một quan hệ so sánh, cần hoán vị các phần tử sao cho:

**a[0] ≤ a[1] ≤ ... ≤ a[n−1]** theo quan hệ thứ tự đã chọn.

Giả sử quan hệ so sánh tạo ra một thứ tự phù hợp: có tính nhất quán và không thay đổi giữa chừng. Với dữ liệu đối tượng Java, quan hệ này có thể đến từ **Comparator**.

Merge sort thực hiện ba bước:

1. **Divide — chia:** nếu dãy có hơn một phần tử, tách dãy thành nửa trái và nửa phải.
2. **Conquer — giải:** đệ quy sắp xếp từng nửa theo cùng thuật toán. Dãy có 0 hoặc 1 phần tử đã được sắp xếp.
3. **Combine — kết hợp:** trộn hai nửa **đã sắp xếp** thành một dãy hoàn chỉnh cũng đã sắp xếp.

Ví dụ sắp xếp tăng dần dãy **[8, 3, 5, 2, 7, 4, 6, 1]**:

~~~text
                      [8,3,5,2,7,4,6,1]
                       /             \
                 [8,3,5,2]         [7,4,6,1]
                  /    \             /    \
               [8,3]  [5,2]       [7,4]  [6,1]
               /  \    /  \       /  \    /  \
              [8] [3] [5] [2]   [7] [4] [6] [1]

Trộn từ dưới lên:
[3,8]  [2,5]  [4,7]  [1,6]
       [2,3,5,8]          [1,4,6,7]
              [1,2,3,4,5,6,7,8]
~~~

**Lưu ý:** “Chia” chỉ xác định các đoạn con; việc **trộn theo thứ tự** mới tạo ra kết quả đã sắp xếp. Không thể đơn giản ghép hai nửa đã sắp theo vị trí nếu các giá trị của hai nửa xen kẽ nhau.

## 2. Bước merge: trộn hai dãy đã có thứ tự

Xét hai dãy tăng dần:

- Trái: **L = [2, 5, 9]**
- Phải: **R = [1, 3, 7, 10]**

Giữ hai con trỏ i và j ở đầu mỗi dãy. So sánh phần tử hiện tại, đưa phần tử nhỏ hơn vào dãy kết quả và tăng con trỏ tương ứng.

| Lần | Đầu trái còn lại | Đầu phải còn lại | Lấy | Kết quả tạm |
| ---: | ---: | ---: | --- | --- |
| 1 | 2 | 1 | 1 từ phải | [1] |
| 2 | 2 | 3 | 2 từ trái | [1,2] |
| 3 | 5 | 3 | 3 từ phải | [1,2,3] |
| 4 | 5 | 7 | 5 từ trái | [1,2,3,5] |
| 5 | 9 | 7 | 7 từ phải | [1,2,3,5,7] |
| 6 | 9 | 10 | 9 từ trái | [1,2,3,5,7,9] |
| 7 | Hết | 10 | Chép phần còn lại | [1,2,3,5,7,9,10] |

Mỗi bước tiêu thụ một phần tử, không bao giờ quay con trỏ về trước. Nếu tổng độ dài hai dãy là m, thời gian merge là **O(m)**; trong cài đặt dùng mảng đệm, bộ nhớ tạm là **O(m)** cho lần merge đó.

### Bất biến giải thích tính đúng đắn

Ngay trước khi ghi phần tử tiếp theo vào kết quả:

- Phần đã ghi của kết quả là **tăng dần**.
- Phần đã ghi chứa đúng các phần tử nhỏ nhất đã lấy từ hai dãy nguồn.
- Hai phần chưa lấy ở L và R đều vẫn tăng dần.
- **Phần tử nhỏ nhất chưa được ghi** bắt buộc là một trong hai phần tử đầu chưa dùng của L hoặc R.

Bởi vậy chọn phần tử nhỏ hơn trong hai đầu chưa dùng luôn đúng. Khi một bên hết, toàn bộ phần còn lại của bên kia đã có thứ tự và có thể sao chép nguyên thứ tự. Sau đúng m lần đưa phần tử vào kết quả, thu được dãy đã sắp và bảo toàn đầy đủ các phần tử.

Quan hệ so sánh phải nhất quán. Nếu Comparator đưa ra kết quả mâu thuẫn cho cùng cặp khóa giữa các lần gọi, giả định “hai nửa đã sắp xếp theo cùng thứ tự” không còn đáng tin cậy.

## 3. Tính ổn định: xử lý các phần tử bằng nhau

Một thuật toán sắp xếp là **ổn định** khi với hai phần tử p và q có **khóa so sánh bằng nhau**, nếu p đứng trước q trong đầu vào thì p vẫn đứng trước q ở đầu ra.

Ví dụ dữ liệu (điểm, mã học viên):

~~~text
Trước khi sắp:
(90,A) (70,B) (90,C) (70,D) (90,E)

Sắp tăng dần theo điểm, ổn định:
(70,B) (70,D) (90,A) (90,C) (90,E)
~~~

Thứ tự của B trước D ở nhóm 70 và A trước C trước E ở nhóm 90 phải được giữ nguyên.

**Quy tắc quan trọng trong merge:** khi khóa của hai đầu bằng nhau, **lấy phần tử từ nửa trái trước**. Trong Java, nếu so sánh comparator.compare(left, right), điều kiện nên là **≤ 0** để chọn trái. Nếu tùy tiện dùng **< 0** rồi lấy phải khi bằng nhau, cặp phần tử bằng khóa nằm ở hai nửa có thể bị đảo thứ tự, làm mất tính ổn định.

Tính ổn định được chứng minh bằng quy nạp:

1. Dãy có 0 hoặc 1 phần tử luôn ổn định.
2. Hai nửa được đệ quy sắp ổn định, nên thứ tự nội bộ của các phần tử bằng khóa trong cùng nửa được giữ.
3. Nếu hai phần tử bằng khóa nằm ở hai nửa, phần tử của nửa trái vốn xuất hiện trước trong dãy gốc; quy tắc **chọn trái khi bằng nhau** giữ đúng thứ tự này trong bước merge.
4. Do đó toàn bộ kết quả vẫn ổn định.

**Ổn định không có nghĩa là các phần tử khác nhau đều giữ vị trí cũ.** Nó chỉ bảo toàn thứ tự *tương đối giữa các phần tử có khóa bằng nhau*.

## 4. Cài đặt top-down: đoạn nửa mở [from, to)

Một thiết kế an toàn là dùng đoạn **[from, to)**, tức bao gồm from và loại trừ to:

- Độ dài đoạn là **to − from**.
- Nửa trái **[from, mid)**.
- Nửa phải **[mid, to)**.
- Vùng sau merge vẫn là **[from, to)**.

Vị trí chia giữa nên tính **mid = from + (to − from) / 2**, tránh cộng from + to có thể tràn số nguyên khi chỉ số lớn.

Điều kiện dừng: **to − from ≤ 1**. Với n = 0, không truy cập phần tử nào; với n = 1, không cần làm gì. Mọi đoạn dài hơn 1 đều được chia thành hai đoạn ngắn hơn, nên đệ quy kết thúc.

### Giả mã cơ bản

~~~text
mergeSort(a, from, to):
    if to - from <= 1:
        return

    mid = from + (to - from) / 2

    mergeSort(a, from, mid)
    mergeSort(a, mid, to)
    mergeTwoSortedHalves(a, from, mid, to)
~~~

Bước merge chỉ hợp lệ khi **cả hai đoạn con đã được sắp xếp**. Nếu gọi merge trên hai đoạn chưa được sắp hoặc ranh giới mid sai, kết quả có thể không có thứ tự.

### Dùng một mảng phụ chung

Một cách cài đặt đơn giản là tạo một mảng đệm (auxiliary array) có độ dài n **một lần** ở lời gọi ngoài cùng, sau đó tái sử dụng nó trong toàn bộ các bước merge. Tạo mảng đệm mới ở mỗi lời gọi vừa sinh nhiều đối tượng không cần thiết vừa tăng chi phí cấp phát.

Với giải thuật đệ quy tuần tự, các lời gọi merge không chạy đồng thời nên có thể tái sử dụng chung một mảng đệm. Nếu song song hóa các nhánh, cần bảo đảm mỗi nhánh chỉ ghi vào vùng đệm riêng hoặc có cơ chế phân chia vùng nhớ an toàn.

## 5. Java 17+: chương trình chạy được và giữ tính ổn định

Ví dụ sau là chương trình Java độc lập, sắp xếp một mảng Integer và một mảng record Entry. Bản generic áp dụng cho **mảng đối tượng** với Comparator; trong mỗi bước merge, khi hai khóa bằng nhau, luôn ưu tiên phần tử ở nửa trái.

Chương trình có một tối ưu nhỏ: sau khi sắp hai nửa, nếu **phần tử cuối nửa trái ≤ phần tử đầu nửa phải**, hai nửa đã ở đúng thứ tự toàn cục nên có thể bỏ qua bước sao chép/trộn. Tối ưu này vẫn giữ tính ổn định.

~~~java
import java.util.Arrays;
import java.util.Comparator;

public class MergeSortDemo {

    record Entry(int score, String label) {}

    public static <T> void mergeSort(T[] array,
                                     Comparator<? super T> comparator) {
        if (array == null || comparator == null) {
            throw new IllegalArgumentException("array/comparator must not be null");
        }

        T[] aux = array.clone();
        sortRange(array, aux, 0, array.length, comparator);
    }

    private static <T> void sortRange(T[] array, T[] aux,
                                      int from, int to,
                                      Comparator<? super T> comparator) {
        if (to - from <= 1) {
            return;
        }

        int mid = from + (to - from) / 2;
        sortRange(array, aux, from, mid, comparator);
        sortRange(array, aux, mid, to, comparator);

        // Hai nửa đã tăng dần và không cần trộn thêm.
        if (comparator.compare(array[mid - 1], array[mid]) <= 0) {
            return;
        }

        merge(array, aux, from, mid, to, comparator);
    }

    private static <T> void merge(T[] array, T[] aux,
                                  int from, int mid, int to,
                                  Comparator<? super T> comparator) {
        int i = from;
        int j = mid;

        for (int k = from; k < to; k++) {
            if (i == mid) {
                aux[k] = array[j++];
            } else if (j == to) {
                aux[k] = array[i++];
            } else if (comparator.compare(array[i], array[j]) <= 0) {
                // Chọn bên trái khi bằng nhau để giữ tính ổn định.
                aux[k] = array[i++];
            } else {
                aux[k] = array[j++];
            }
        }

        System.arraycopy(aux, from, array, from, to - from);
    }

    public static void main(String[] args) {
        Integer[] numbers = {8, 3, 5, 2, 7, 4, 6, 1};
        mergeSort(numbers, Comparator.naturalOrder());
        System.out.println("Numbers: " + Arrays.toString(numbers));

        Entry[] records = {
                new Entry(90, "A"),
                new Entry(70, "B"),
                new Entry(90, "C"),
                new Entry(70, "D"),
                new Entry(90, "E")
        };
        mergeSort(records, Comparator.comparingInt(Entry::score));
        System.out.println("Stable: " + Arrays.toString(records));

        Integer[] empty = {};
        mergeSort(empty, Comparator.naturalOrder());
        System.out.println("Empty: " + Arrays.toString(empty));
    }
}
~~~

Lưu đúng tên tệp **MergeSortDemo.java**, biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac MergeSortDemo.java
java MergeSortDemo
~~~

Đầu ra:

~~~text
Numbers: [1, 2, 3, 4, 5, 6, 7, 8]
Stable: [Entry[score=70, label=B], Entry[score=70, label=D], Entry[score=90, label=A], Entry[score=90, label=C], Entry[score=90, label=E]]
Empty: []
~~~

**Giải thích mã:**

- **mergeSort** tạo một bản sao làm vùng đệm, rồi xử lý toàn bộ đoạn [0, array.length).
- **sortRange** chia đoạn, sắp hai nửa trước, rồi hợp nhất. Hai phần được xử lý tuần tự nên không đè dữ liệu của nhau.
- **comparator.compare(array[mid − 1], array[mid]) ≤ 0** cho biết giá trị lớn nhất của nửa trái không lớn hơn giá trị nhỏ nhất của nửa phải. Vì mỗi nửa đã tăng dần, nối hai nửa sẽ vẫn đúng thứ tự; không cần merge.
- **merge** dùng hai con trỏ i và j. Khi một nửa hết, lấy tiếp từ nửa còn lại. Khi cả hai còn phần tử, dùng **≤ 0** để bảo đảm ổn định.
- **System.arraycopy** chép chính xác đoạn [from, to) từ aux về array. Các phần tử ngoài đoạn không bị thay đổi bởi bước merge.
- Hai học viên B và D cùng điểm 70, nên kết quả giữ **B trước D**; ba học viên A, C, E cùng điểm 90 và vẫn giữ **A trước C trước E**.
- Mảng rỗng được xử lý trực tiếp, không gọi comparator hoặc truy cập chỉ số ngoài mảng.

Mảng đầu vào bị **thay đổi thành thứ tự đã sắp xếp**. Đây là thao tác sửa mảng tại chỗ về mặt giao diện API, nhưng **không phải thuật toán in-place theo nghĩa dùng O(1) bộ nhớ phụ**, vì vẫn cần vùng đệm O(n).

## 6. Phân tích độ phức tạp thời gian

Ở một cấp đệ quy, các đoạn con có tổng độ dài n. Nếu mỗi đoạn được merge theo hai con trỏ, tổng chi phí merge trên một cấp là **O(n)**.

Mỗi lần chia làm đôi, độ sâu cây đệ quy là **O(log n)**. Có khoảng log₂ n cấp trộn, do đó tổng thời gian trường hợp xấu nhất:

**O(n log n).**

Khi chia thành hai nửa gần bằng nhau, có thể mô tả bằng hệ thức truy hồi:

**T(n) = T(⌊n/2⌋) + T(⌈n/2⌉) + Θ(n)** khi phải thực hiện merge toàn bộ đoạn, với T(0), T(1) = Θ(1).

Với n là lũy thừa của 2, cách viết quen thuộc là **T(n) = 2T(n/2) + Θ(n)**. Giải ra **Θ(n log n)**.

### Tốt nhất, trung bình và xấu nhất

| Phiên bản | Tốt nhất | Trung bình | Xấu nhất |
| --- | --- | --- | --- |
| Top-down **luôn trộn** hai nửa đã sắp | Θ(n log n) | Θ(n log n) | Θ(n log n) |
| Top-down **có kiểm tra biên để bỏ merge** như mã Java | Θ(n) trên dãy đã tăng sẵn | Thông thường O(n log n) | Θ(n log n) |

Vì sao phiên bản có kiểm tra biên đạt **Θ(n)** khi dãy đã tăng? Tại mỗi nút trong cây đệ quy, hai nửa đã có đúng thứ tự nên chỉ cần một phép so sánh **array[mid−1] ≤ array[mid]** để không phải merge. Cây chia có O(n) nút, vì vậy tổng chi phí là Θ(n), dù vẫn có O(log n) tầng gọi hàm.

Đây là **tối ưu của cài đặt cụ thể**, không phải đặc tính bắt buộc của mọi phiên bản merge sort. Với đầu vào bất kỳ, không có bảo đảm các bước merge đều được bỏ qua.

### Bộ nhớ

Ở phiên bản dùng đệm aux chung:

- **Mảng phụ** có n vị trí tham chiếu: **O(n)**.
- **Ngăn xếp đệ quy** có độ sâu **O(log n)**.
- Tổng bộ nhớ phụ vẫn là **O(n)** với n lớn.

Nếu đầu vào gồm đối tượng nặng, clone() trong ví dụ chỉ tạo **bản sao mảng tham chiếu**, không sao chép sâu từng đối tượng. Phần tử trong hai mảng có thể trỏ đến cùng đối tượng; merge chỉ đổi thứ tự tham chiếu.

Không nên nói merge sort luôn dùng O(n) bộ nhớ trong mọi mô hình: có những thuật toán trộn tại chỗ phức tạp hơn, những phiên bản làm việc trên linked list và những biến thể phục vụ bộ nhớ ngoài. Tuy nhiên, **cách cài đặt mảng với aux** là phiên bản chuẩn dễ hiểu và dùng O(n) vùng đệm.

## 7. Bottom-up merge sort: phiên bản lặp

Merge sort không bắt buộc dùng đệ quy. Trong phiên bản **bottom-up**, ta bắt đầu với những đoạn đã sắp có độ dài 1, rồi lần lượt trộn các cặp đoạn độ dài 1 → 2 → 4 → 8 → ...

Với mỗi kích thước run = 1, 2, 4, ...:

1. Xét các cặp đoạn liên tiếp có chiều dài tối đa run.
2. Trộn đoạn [start, mid) với [mid, end), trong đó **mid = min(start + run, n)** và **end = min(start + 2×run, n)**.
3. Sau một lượt, các đoạn đã sắp có độ dài tối đa **2×run**.
4. Lặp cho đến khi run ≥ n.

Giả mã khái niệm:

~~~text
run = 1
while run < n:
    start = 0
    while start < n:
        mid = min(start + run, n)
        end = min(start + 2*run, n)
        merge hai đoạn đã sắp [start,mid), [mid,end)
        start = end
    run = 2*run
~~~

**Lưu ý khi cài với int rất lớn:** nhân đôi run hoặc tính start + 2*run có thể tràn số; nên dùng cách tính biên có kiểm tra giới hạn, hoặc kiểu số rộng hơn. Trường hợp [mid, end) rỗng thì không cần trộn.

Bottom-up có thời gian **O(n log n)** và bộ nhớ phụ thường **O(n)** với mảng đệm, nhưng không dùng ngăn xếp đệ quy. Nó dễ mở rộng để trộn các **run đã sắp xếp sẵn** hoặc áp dụng trong xử lý dữ liệu theo từng khối.

## 8. Ứng dụng: đếm nghịch thế trong O(n log n)

Một **nghịch thế (inversion)** của dãy a là một cặp chỉ số (i, j) sao cho **i < j nhưng a[i] > a[j]**. Đây là cách đo mức độ “ngược thứ tự” so với dãy tăng.

Ví dụ **a = [4, 1, 3, 2]** có **4 nghịch thế**:

- (4,1)
- (4,3)
- (4,2)
- (3,2)

Thay vì kiểm tra tất cả O(n²) cặp, có thể bổ sung bộ đếm trong merge sort:

- Đếm nghịch thế hoàn toàn trong nửa trái bằng đệ quy.
- Đếm nghịch thế hoàn toàn trong nửa phải bằng đệ quy.
- Khi trộn, nếu **a[i] ≤ a[j]**, lấy phần tử trái, không tạo nghịch thế chéo.
- Nếu **a[i] > a[j]**, lấy phần tử phải a[j]. Vì nửa trái đã sắp tăng, tất cả **mid − i** phần tử trái còn lại đều lớn hơn a[j], nên tạo thêm **mid − i** nghịch thế chéo.

Cộng ba nguồn đếm cho ra kết quả chính xác trong **O(n log n)**. Nếu số phần tử lớn, số cặp tối đa là n(n−1)/2 và có thể vượt **int**; nên dùng **long** hoặc kiểu số đủ rộng theo giới hạn đề.

Đây là một ứng dụng quan trọng của ý tưởng merge: **tính toán thông tin khi hai nửa được hợp nhất** thay vì chỉ tạo mảng đã sắp.

## 9. Khi nào merge sort có lợi?

| Tiêu chí | Merge sort (mảng + aux) | Quicksort thông thường | Heapsort | Insertion sort |
| --- | --- | --- | --- | --- |
| Xấu nhất | O(n log n) | O(n²) nếu chọn pivot bất lợi và không có bảo vệ bổ sung | O(n log n) | O(n²) |
| Trung bình phổ biến | O(n log n) | O(n log n) | O(n log n) | O(n²) |
| Ổn định theo phiên bản chuẩn | **Có**, nếu chọn trái khi bằng nhau | Thường **không** | Thường **không** | **Có** khi chỉ dịch chuyển phần tử lớn hơn strict |
| Bộ nhớ phụ điển hình | O(n) | O(log n) trung bình cho ngăn xếp (tùy cài đặt) | O(1) | O(1) |
| Đặc điểm nổi bật | Hiệu năng xấu nhất tốt, dễ trộn run, ổn định | Thường hiệu quả trên mảng với locality tốt | Không cần aux O(n), bảo đảm thời gian | Tốt cho đoạn nhỏ hoặc gần có thứ tự |

Bảng mô tả các **phiên bản điển hình**. Thuật toán thực tế có thể dùng hybrid, chọn pivot ngẫu nhiên, introsort, tối ưu cho run hoặc thuật toán thư viện khác nên cần xét đúng cài đặt.

Merge sort đặc biệt hữu ích khi:

- **Yêu cầu ổn định:** sau khi sắp theo nhiều khóa, muốn giữ thứ tự trước đó của bản ghi có khóa mới bằng nhau.
- **Cần giới hạn thời gian xấu nhất O(n log n)** trên dữ liệu tổng quát.
- **Dữ liệu lớn xử lý ngoài bộ nhớ (external merge sort):** chia file thành các khối vừa RAM, sắp từng khối, ghi các run ra đĩa, rồi trộn nhiều run theo thứ tự bằng luồng/heap. Khi đó chi phí I/O và số lần đọc ghi khối là yếu tố quan trọng.
- **Dữ liệu nằm trong linked list:** có thể tách danh sách và trộn các nút bằng thay đổi con trỏ; không nhất thiết cần mảng aux O(n) như cách làm cho mảng.
- **Bài toán chia để trị có bước kết hợp theo thứ tự:** đếm nghịch thế, một số truy vấn thống kê hoặc trộn nhiều luồng đã sắp.

Nếu chỉ có một dãy rất nhỏ, insertion sort có thể đơn giản và nhanh hơn vì chi phí gọi hàm/cấp phát của merge sort. Nếu giới hạn bộ nhớ phụ rất chặt, O(n) aux có thể là trở ngại.

### Merge nhiều run và external sorting

Khi trộn **hai run** đã sắp, dùng hai con trỏ là đủ. Khi trộn **k run** đã sắp, có thể dùng **min-heap** chứa phần tử đầu hiện tại của mỗi run; mỗi lần lấy phần tử nhỏ nhất, rồi đưa phần tử kế tiếp từ run tương ứng vào heap. Với tổng N phần tử, chi phí so sánh thường **O(N log k)**.

Nếu cần ổn định trên nhiều run, phải xác định quy tắc hòa khi khóa bằng nhau, ví dụ ưu tiên chỉ số run gốc rồi vị trí trong run; nếu không, tính ổn định có thể bị phá giữa các run dù từng run đã ổn định.

## 10. Java có sẵn thuật toán sắp xếp: có cần tự viết không?

Java có API tiện lợi như **Arrays.sort** và **List.sort**. Trong phần mềm thông thường, nên ưu tiên API thư viện khi đáp ứng yêu cầu; tự viết merge sort chủ yếu để học cơ chế, áp dụng biến thể đặc biệt hoặc cần kiểm soát bước merge.

Đặc biệt:

- **Arrays.sort(Object[])** và **List.sort** có hợp đồng **ổn định** cho các phần tử đối tượng theo bộ so sánh tương ứng.
- Với **mảng nguyên thủy** như int[], không có bản ghi mang định danh khác nhau cùng khóa để quan sát ý nghĩa ổn định theo cách thông thường; không nên dựa vào giả định rằng cài đặt sắp xếp nguyên thủy của thư viện là stable.
- Một cài đặt thư viện có thể dùng thuật toán lai như TimSort hoặc các kỹ thuật tối ưu nội bộ, nên **không khẳng định mọi lời gọi Arrays.sort đều chạy đúng mã merge sort ở trên**.
- Khi so sánh đối tượng, Comparator nên có tính nhất quán, bắc cầu và không phụ thuộc vào trạng thái thay đổi trong lúc sắp xếp.

Với bài thực hành, chương trình tự cài ở mục 5 minh họa được rõ tính ổn định thông qua khóa **score** và nhãn **label**.

## 11. Những lỗi phổ biến và cách kiểm tra

1. **Merge khi hai nửa chưa sắp.** Hai con trỏ chỉ đúng khi mỗi nửa đã tăng dần theo cùng Comparator.
2. **Nhầm biên [from,mid) và [mid,to).** Ghi thiếu phần tử mid hoặc vượt to sẽ gây mất/sai phần tử.
3. **Khi bằng nhau chọn nửa phải.** Kết quả có thể vẫn tăng nhưng không còn **ổn định**.
4. **Chỉ sao chép đến khi một nửa hết.** Phải lấy toàn bộ phần dư của nửa còn lại.
5. **Quên chép aux về array** hoặc chép sai vùng. Cấp đệ quy phía trên sẽ thấy dữ liệu cũ chưa sắp.
6. **Tạo mảng aux mới ở mỗi lời gọi mà không cần thiết.** Tăng công việc cấp phát, làm kém hiệu quả.
7. **Nhầm “mảng được sửa trực tiếp” với thuật toán dùng O(1) bộ nhớ phụ.** Bản chuẩn có aux O(n).
8. **Tuyên bố tốt nhất luôn Θ(n log n).** Đúng với phiên bản luôn merge, nhưng phiên bản có kiểm tra hai biên có thể đạt Θ(n) trên dữ liệu đã sắp.
9. **Tính mid bằng (from + to)/2.** Có nguy cơ tràn khi chỉ số lớn; dùng from + (to−from)/2.
10. **Comparator sai hoặc không nhất quán.** Có thể làm hỏng giả định thứ tự của hai nửa.
11. **Quên dữ liệu trùng hoặc dãy rỗng.** Kiểm thử n = 0, n = 1, toàn khóa bằng nhau để kiểm tra base case và ổn định.
12. **Tính số nghịch thế bằng int khi n lớn.** Tổng nghịch thế có thể lên đến n(n−1)/2.
13. **Không xét chi phí I/O khi dữ liệu nằm ngoài RAM.** External merge sort cần tối ưu kích thước run, bộ đệm và số lượt merge.
14. **Song song hóa dùng chung aux không phân vùng ghi.** Khi hai task cùng ghi vùng đệm có thể phát sinh race; phải thiết kế vùng độc lập.

### Bộ kiểm thử tối thiểu

| Dữ liệu đầu vào | Kết quả sắp tăng mong đợi | Mục tiêu kiểm thử |
| --- | --- | --- |
| [] | [] | Dãy rỗng |
| [5] | [5] | Một phần tử |
| [1,2,3,4] | [1,2,3,4] | Đã sắp, có thể bỏ merge |
| [4,3,2,1] | [1,2,3,4] | Ngược thứ tự |
| [3,1,3,1] | [1,1,3,3] | Khóa trùng |
| [-5,0,-2,8] | [-5,-2,0,8] | Số âm và dương |
| [(2,A),(1,B),(2,C)] | [(1,B),(2,A),(2,C)] | Ổn định với khóa bằng nhau |
| [Integer.MAX_VALUE,Integer.MIN_VALUE] | [Integer.MIN_VALUE,Integer.MAX_VALUE] | Giá trị biên |

Ngoài việc kiểm tra tăng dần, cần xác minh **đa tập đầu vào và đầu ra giống hệt nhau**, tránh trường hợp mất hoặc nhân đôi phần tử trong bước merge.

## 12. Tự kiểm tra

**Câu 1.** Khi trộn [1,4,7] và [2,3,8], kết quả là gì?  
**Đáp án:** [1,2,3,4,7,8].

**Câu 2.** Vì sao merge sort dùng O(n log n) thời gian trong trường hợp xấu nhất?  
**Đáp án:** Có O(log n) tầng chia đôi; mỗi tầng có tổng số phần tử tham gia merge là O(n), nên tổng là O(n log n).

**Câu 3.** Với hai bản ghi (2,A) ở nửa trái và (2,B) ở nửa phải, cần lấy bên nào trước khi khóa bằng nhau để giữ tính ổn định?  
**Đáp án:** Lấy **(2,A)** từ trái trước.

**Câu 4.** Mảng ban đầu đã tăng dần có khiến mọi merge sort đạt Θ(n) không?  
**Đáp án:** Không. Chỉ những phiên bản có cơ chế nhận ra hai nửa đã đúng thứ tự và bỏ bước merge, như mã Java ở trên, mới đạt Θ(n) trong trường hợp này; phiên bản luôn merge vẫn Θ(n log n).

**Câu 5.** Với [4,1,3,2], có bao nhiêu nghịch thế?  
**Đáp án:** 4: (4,1), (4,3), (4,2), (3,2).

**Câu 6.** Dữ liệu không vừa RAM, có thể áp dụng ý tưởng merge sort ra sao?  
**Đáp án:** Sắp các khối vừa bộ nhớ thành các run, sau đó trộn tuần tự hoặc k-way merge chúng thành file đầu ra có thứ tự.

## 13. Ghi nhớ

**Merge sort = chia đôi + sắp từng nửa + trộn hai nửa đã sắp.** Bước merge tuyến tính đúng nhờ hai nửa cùng có thứ tự. Chia để trị tạo **O(log n)** tầng, mỗi tầng tổng **O(n)** thao tác, nên xấu nhất **O(n log n)**. Để giữ tính **ổn định**, ưu tiên phần tử **bên trái khi hai khóa bằng nhau**. Bản cài đặt dễ hiểu cho mảng dùng **O(n)** vùng nhớ phụ; với một số ràng buộc đặc biệt có thể cân nhắc bottom-up, linked-list merge, external merge hoặc thuật toán thư viện phù hợp.