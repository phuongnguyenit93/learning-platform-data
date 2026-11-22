# Phân hoạch ba phía khi có nhiều khóa trùng

Trong nhóm thuật toán **sắp xếp so sánh**, thao tác *phân hoạch* (*partition*) chia một đoạn dữ liệu quanh một giá trị **chốt** (*pivot*). Nếu có nhiều phần tử mang cùng khóa, **phân hoạch ba phía** (*three-way partition*, còn gọi là *Dutch National Flag partition*) thường hiệu quả hơn cách chỉ chia hai phía: sau một lần quét, nó tách rõ ba vùng **nhỏ hơn**, **bằng**, và **lớn hơn** pivot.

Điểm mấu chốt: các phần tử **bằng pivot đã nằm đúng nhóm của mình**, nên thuật toán sắp xếp kiểu quicksort **không cần đưa nhóm đó vào các lời gọi đệ quy**. Khi dữ liệu chứa rất nhiều khóa trùng, cách này tránh lặp lại vô ích việc xử lý các bản sao bằng nhau.

Bài học tập trung vào cách xác định ba vùng, bất biến vòng lặp, chứng minh kết thúc/tính đúng, áp dụng trong quicksort, phân tích chi phí và chương trình Java 17+ hoàn chỉnh.

## 1. Phân hoạch ba phía là gì?

Giả sử ta phân hoạch **đoạn chỉ số đóng [lo, hi]** của mảng `a` theo pivot `p`. Kết quả cần có hai ranh giới `lt` và `gt` thỏa:

- Vùng trái `a[lo .. lt-1]`: tất cả phần tử **< p**.
- Vùng giữa `a[lt .. gt]`: tất cả phần tử **= p**.
- Vùng phải `a[gt+1 .. hi]`: tất cả phần tử **> p**.

Ba vùng ghép lại phải chứa **đúng các phần tử ban đầu của đoạn**, kể cả số lần xuất hiện; không được làm mất hoặc tạo thêm phần tử. Các phần tử bên trong vùng < p và > p **chưa nhất thiết được sắp xếp**.

Với đoạn ví dụ:

```text
Dữ liệu: [2, 3, 2, 1, 2, 3, 1, 2, 0]
pivot = 2

Một kết quả phân hoạch hợp lệ:
[1, 0, 1 | 2, 2, 2, 2 | 3, 3]
   < 2          = 2       > 2

Số phần tử theo từng nhóm: 3 | 4 | 2
Ranh giới: lt = 3, gt = 6 (đánh chỉ số từ 0)
```

Đây chỉ là **một cách sắp thứ tự hợp lệ** sau phân hoạch. Tùy trình tự đổi chỗ, vùng trái có thể là `[1,1,0]` hay `[0,1,1]`; điều bắt buộc là **quan hệ với pivot và số lượng mỗi nhóm**, không phải thứ tự nội bộ.

### Vì sao hai phía đôi khi kém khi khóa trùng?

Một số cách phân hoạch nhị phân chia thành hai nhóm `<= pivot` và `> pivot` (hoặc `< pivot` và `>= pivot`). Khi có nhiều khóa bằng nhau, nhiều bản sao có thể vẫn bị đưa vào những bài toán con, khiến các lần so sánh lặp lại. Một cách chia quá lệch (ví dụ mỗi lần chỉ tách được một phần tử) có thể làm quicksort chạy **O(n²)**.

Không phải **mọi** thuật toán quicksort hai phía đều xử lý khóa trùng kém: các biến thể như Hoare partition có thể ứng xử khác. Lợi ích đặc trưng của phân hoạch ba phía là **cô lập cả nhóm bằng pivot trong cùng một lượt** và loại nhóm ấy khỏi đệ quy tiếp theo.

## 2. Bốn vùng trong lúc xử lý

Để tạo ra **ba vùng cuối**, trong quá trình quét ta duy trì **bốn vùng tạm thời** và ba chỉ số `lt`, `i`, `gt`:

```text
lo                                                    hi
|   < pivot   |   = pivot   |    CHƯA BIẾT    |   > pivot   |
lo          lt-1 lt        i-1 i            gt gt+1      hi
```

Cụ thể:

1. `a[lo .. lt-1] < pivot`: nhóm nhỏ hơn đã xử lý.
2. `a[lt .. i-1] == pivot`: nhóm bằng đã xử lý.
3. `a[i .. gt]`: nhóm **chưa phân loại**.
4. `a[gt+1 .. hi] > pivot`: nhóm lớn hơn đã xử lý.

Ở ví dụ dùng pivot là `a[lo]`, khởi tạo:

```text
pivot = a[lo]
lt = lo
i  = lo + 1
gt = hi
```

Vì `a[lo] == pivot` nên vùng bằng ban đầu gồm đúng một phần tử. Vùng trái và vùng phải đã xử lý đều rỗng; vùng chưa biết chứa các phần tử từ `lo+1` đến `hi`.

**Quy ước khoảng chỉ số:** Các vùng là **đoạn đóng**; một vùng rỗng được biểu diễn bằng điểm đầu lớn hơn điểm cuối (ví dụ `i > gt`). Thực hiện phân hoạch cho đoạn con không được làm thay đổi phần tử nằm ngoài `[lo, hi]`.

## 3. Ba tình huống khi xét a[i]

Trong khi `i <= gt`, phần tử `a[i]` chưa được phân loại. So sánh nó với pivot:

**Trường hợp A — a[i] < pivot**

Hoán đổi `a[i]` với `a[lt]`, sau đó tăng **cả lt và i**.

- Giá trị nhỏ hơn pivot đã đi về cuối vùng trái.
- Giá trị bằng pivot vốn nằm tại lt chuyển sang vị trí i cũ (trừ trường hợp các chỉ số trùng nhau, hoán đổi chính nó).
- Sau khi tăng cả hai con trỏ, vùng trái và vùng bằng đều đúng như bất biến.

**Trường hợp B — a[i] == pivot**

Chỉ tăng **i**. Phần tử này nối dài vùng bằng pivot; không cần hoán đổi.

**Trường hợp C — a[i] > pivot**

Hoán đổi `a[i]` với `a[gt]`, rồi **giảm gt nhưng không tăng i**.

- Phần tử lớn hơn đã chuyển sang vùng phải.
- Phần tử mới đến vị trí i được lấy từ vùng **chưa biết**, nên có thể nhỏ hơn/bằng/lớn hơn pivot.
- Nếu tăng i ngay, ta sẽ **bỏ qua** việc phân loại phần tử vừa được đổi vào: đây là lỗi quan trọng nhất của thuật toán.

Đoạn mã cốt lõi:

```java
int pivot = a[lo];
int lt = lo;
int i = lo + 1;
int gt = hi;

while (i <= gt) {
    if (a[i] < pivot) {
        swap(a, lt, i);
        lt++;
        i++;
    } else if (a[i] > pivot) {
        swap(a, i, gt);
        gt--;          // i giữ nguyên: phần tử mới đến chưa biết
    } else {
        i++;
    }
}
// Kết quả: a[lo..lt-1] < pivot; a[lt..gt] == pivot;
//          a[gt+1..hi] > pivot
```

Đây là **đoạn minh họa thuật toán**, cần định nghĩa phương thức `swap` và dữ liệu đầu vào; tệp Java hoàn chỉnh có ở phần 8.

### Nhìn theo “vùng chưa biết”

Mỗi vòng xử lý **chính xác một phần tử** trong vùng chưa biết:

- Nhánh nhỏ hơn: `i++`, vùng chưa biết rút từ bên trái.
- Nhánh bằng: `i++`, vùng chưa biết rút từ bên trái.
- Nhánh lớn hơn: `gt--`, vùng chưa biết rút từ bên phải, còn vị trí i cần xét lại.

Ta không cần dự đoán phần tử sẽ đến từ bên phải là gì. Thuật toán bảo đảm mọi phần tử chưa được phân loại sẽ được xem xét trước khi kết thúc.

## 4. Chứng minh tính đúng bằng bất biến vòng lặp

Giả định đoạn đầu vào hợp lệ `0 <= lo <= hi < a.length`; pivot được giữ trong biến riêng nên dù vị trí a[lo] thay đổi trong lúc hoán đổi, **giá trị pivot không thay đổi**.

**Bất biến I:** Trước mỗi vòng, bốn vùng có tính chất:

1. Mọi giá trị trong `[lo, lt)` đều nhỏ hơn pivot.
2. Mọi giá trị trong `[lt, i)` đều bằng pivot.
3. Các phần tử trong `[i, gt]` chưa có ràng buộc so sánh.
4. Mọi giá trị trong `(gt, hi]` đều lớn hơn pivot.
5. Các phần tử bên ngoài `[lo, hi]` giữ nguyên; trong đoạn đang phân hoạch, mọi thao tác là hoán đổi, nên giữ nguyên **đa tập** các giá trị.

**Khởi tạo:** `lt=lo` nên vùng nhỏ hơn rỗng. `i=lo+1` nên vùng bằng chứa đúng a[lo]=pivot. `gt=hi` nên vùng lớn hơn rỗng. Mọi điều kiện đều đúng.

**Duy trì:** Xét lần lượt ba nhánh trong phần 3:

- Nhỏ hơn: chuyển đúng giá trị nhỏ hơn vào vị trí lt; vị trí i nhận một phần tử bằng pivot từ vùng bằng, nên khi lt/i cùng tăng, hai vùng đã xử lý vẫn đúng.
- Bằng: tăng i để nhập thêm phần tử bằng vào vùng bằng.
- Lớn hơn: chuyển đúng phần tử lớn vào vị trí gt; giảm gt khiến nó nằm trong vùng lớn hơn, còn phần tử chuyển vào i vẫn ở vùng chưa biết.

Vì vậy bất biến vẫn đúng sau mọi vòng.

**Kết thúc:** Vòng lặp dừng khi `i > gt`, tức vùng chưa biết rỗng. Từ bất biến suy ra **toàn bộ đoạn [lo,hi] đã được chia thành ba nhóm đúng quan hệ với pivot**. Tính chất bảo toàn đa tập bảo đảm không mất và không nhân đôi phần tử. Hai ranh giới `lt` và `gt` chỉ ra chính xác vùng bằng pivot.

### Chứng minh vòng lặp dừng

Chọn đại lượng nguyên không âm `V = gt - i + 1` khi `i <= gt`, là **số phần tử chưa phân loại**.

- Trong nhánh nhỏ hơn/bằng, i tăng 1 nên V giảm 1.
- Trong nhánh lớn hơn, gt giảm 1 nên V cũng giảm 1.
- V không âm trong lúc điều kiện vòng lặp đúng và cuối cùng trở về 0.

Vì V giảm nghiêm ngặt mỗi lượt, vòng lặp kết thúc. Có đúng `hi - lo` lượt phân loại sau khi chọn a[lo] làm pivot, do vị trí lo đã thuộc vùng bằng từ đầu. Mỗi lượt làm số hữu hạn phép so sánh/hoán đổi, nên **thời gian phân hoạch một đoạn dài m = hi−lo+1 là Θ(m)**, dùng **O(1)** bộ nhớ phụ.

## 5. Tại sao phân hoạch ba phía hữu ích cho quicksort?

Quicksort dựa trên quy tắc:

1. Chọn một pivot trong đoạn cần sắp xếp.
2. Phân hoạch theo pivot.
3. Sắp xếp đệ quy những phần tử **nhỏ hơn** và **lớn hơn** pivot.
4. **Không cần sắp xếp lại vùng bằng** vì mọi phần tử ở đó có cùng khóa, và chúng đều nằm sau mọi phần tử nhỏ hơn, trước mọi phần tử lớn hơn.

Sau phân hoạch trả `lt, gt`:

```text
quicksort(a, lo, lt-1)  // vùng < pivot
     a[lt..gt]          // vùng = pivot: bỏ qua
quicksort(a, gt+1, hi)  // vùng > pivot
```

Nếu cả đoạn có cùng một khóa, **toàn bộ đoạn trở thành vùng bằng sau một lượt**, không còn bài toán con cần xử lý. Đó là lợi thế lớn khi dữ liệu chứa nhiều bản sao.

Ví dụ:

```text
a = [7, 7, 7, 7, 7, 7, 7]
pivot = 7

< 7: rỗng       = 7: toàn bộ 7 phần tử       > 7: rỗng
Không còn lời gọi đệ quy trên phần tử nào.
```

Một lớp ứng dụng khác là **quickselect**: sau phân hoạch, nếu vị trí thứ k rơi trong vùng bằng, đã tìm được khóa cần chọn; nếu không, chỉ tiếp tục xét **một phía** chứa k. Tuy nhiên việc trả về một phần tử theo thứ hạng, quản lý chỉ số và độ phức tạp của quickselect là một bài toán riêng, không phải mặc nhiên suy ra mảng đã được sắp xếp.

## 6. Phức tạp thời gian và không gian

Gọi n là tổng số phần tử; m là kích thước một đoạn được phân hoạch.

| Công việc hoặc tình huống | Thời gian | Bộ nhớ phụ |
| --- | --- | --- |
| Phân hoạch ba phía một đoạn dài m | **Θ(m)** | **O(1)** |
| Quicksort ba phía, pivot chọn ngẫu nhiên, trung bình/kỳ vọng | **O(n log n)** | Phụ thuộc triển khai đệ quy |
| Tất cả n phần tử bằng nhau | **Θ(n)** cho cả sắp xếp ba phía | O(1) cho phân hoạch, cộng stack |
| Trường hợp xấu của quicksort (pivot liên tục lệch) | **O(n²)** | Phụ thuộc cách giới hạn độ sâu stack |
| Duyệt một vùng bằng pivot sau phân hoạch | **O(1)** để có hai biên | Không cần duyệt lại phần tử bằng |

**Giải thích thời gian:**

- Một lần phân hoạch có **O(m)** thao tác vì mỗi vòng giảm số phần tử chưa phân loại đúng một.
- Nếu pivot chia các bài toán con tương đối cân bằng, phương trình kiểu `T(n) = T(n₁) + T(n₂) + Θ(n)` với `n₁+n₂ <= n−1` cho tổng gần O(n log n).
- Khi **mọi phần tử bằng nhau**, `n₁=n₂=0` sau phân hoạch đầu, nên toàn bộ sắp xếp hoàn tất trong O(n).
- Nếu dữ liệu chủ yếu chứa các khóa phân biệt và pivot bị chọn lệch liên tục (ví dụ nhóm nhỏ hơn rỗng, nhóm lớn hơn gần n), tổng công việc vẫn có thể là O(n²). **Phân hoạch ba phía không tự loại bỏ trường hợp xấu của quicksort**.
- Chọn pivot **ngẫu nhiên** làm giảm nguy cơ lặp lại phân hoạch lệch có hệ thống trên một kiểu đầu vào cụ thể và cho phân tích **kỳ vọng** O(n log n). Không phải bảo đảm mọi lần chạy đều O(n log n).

**Giải thích bộ nhớ:** Phân hoạch tại chỗ cần ba chỉ số và một pivot, nên O(1). Nếu viết quicksort với hai lời gọi đệ quy trực tiếp, độ sâu stack có thể là O(n) ở trường hợp xấu. Trong chương trình ở phần 8, ta **chỉ đệ quy trên phía nhỏ hơn** và dùng một vòng lặp để xử lý phía lớn hơn; điều này giữ **O(log n) độ sâu lời gọi trong trường hợp xấu**, dù thời gian xấu nhất vẫn là O(n²). Không nên gọi cả thuật toán quicksort là “O(1) bộ nhớ” chỉ vì bước phân hoạch là tại chỗ.

### “Khóa trùng nhiều” là bao nhiêu?

Không có một tỷ lệ cố định mà sau đó ba phía luôn thắng mọi cách khác: kết quả còn phụ thuộc cách chọn pivot, mức độ trùng, việc đổi chỗ, chi phí so sánh, bộ nhớ và hiện thực hai phía.

Với dữ liệu có **rất ít khóa phân biệt nhưng rất nhiều bản sao**, vùng bằng lớn có thể cắt giảm đáng kể các bài toán con. Với hầu hết khóa phân biệt, vùng bằng thường chỉ dài 1 và hành vi tổng thể gần quicksort thông thường; vẫn cần đo hiệu năng thực tế nếu chọn thuật toán cho hệ thống lớn.

## 7. Chọn pivot và tính ổn định

### Chọn pivot

Trong ví dụ phân hoạch độc lập, ta dùng **a[lo]** làm pivot vì dễ kiểm chứng bất biến. Khi áp dụng trong quicksort, luôn chọn phần tử đầu trên dữ liệu đã có cấu trúc có thể khiến phân hoạch lệch nghiêm trọng. Một cách cải thiện phổ biến là:

1. Chọn chỉ số pivot ngẫu nhiên trong **[lo, hi]**.
2. Hoán đổi phần tử đó về vị trí lo.
3. Gọi thuật toán phân hoạch ba phía dùng a[lo] làm pivot.

Ta cũng có thể chọn pivot kiểu “trung vị của ba” hoặc kết hợp các chiến lược khác; điều đó không tự tạo bảo đảm tuyệt đối về trường hợp xấu.

### Phân hoạch ba phía thường **không ổn định**

**Ổn định (stable sort)** nghĩa là hai bản ghi có khóa bằng nhau vẫn giữ nguyên thứ tự xuất hiện ban đầu. Phân hoạch tại chỗ kiểu Dutch National Flag dùng **hoán đổi xa**, nên **không bảo đảm ổn định**. Với mảng int, các bản sao bằng nhau trông giống hệt, nhưng với đối tượng có khóa trùng và dữ liệu phụ (ví dụ ID), thứ tự ID có thể bị đảo.

Nếu bài toán yêu cầu giữ thứ tự các bản ghi có cùng khóa, nên chọn thuật toán/cấu trúc có cam kết ổn định (hoặc dùng bộ đệm bổ sung cho phân hoạch ổn định). Việc một đoạn bằng pivot liên tục **không đồng nghĩa** thứ tự nội bộ của các phần tử bằng pivot được giữ nguyên.

### Số học và so sánh

Với khóa kiểu `int`, dùng `a[i] < pivot` và `a[i] > pivot`. Không nên so sánh bằng phép trừ `a[i] - pivot` vì có thể tràn số khi gặp `Integer.MIN_VALUE` và `Integer.MAX_VALUE`.

Với đối tượng, sử dụng một `Comparator` có quy tắc nhất quán; ba nhóm được xác định bởi dấu của `compare(element, pivot)`. Nếu comparator không nhất quán hoặc thay đổi trong lúc sắp xếp, bất biến phân hoạch có thể mất hiệu lực.

## 8. Chương trình Java 17+ chạy được

Chương trình dưới đây triển khai:

- `partition3`: phân hoạch một đoạn theo phần tử đầu, trả hai biên `lt` và `gt`.
- `quickSort3`: quicksort ba phía, **chọn pivot ngẫu nhiên** rồi hoán đổi về đầu đoạn.
- **Giới hạn độ sâu stack:** dùng đệ quy cho phía nhỏ hơn và tiếp tục lặp trên phía lớn hơn.
- Hàm `isValidPartition` để kiểm tra ba nhóm trong ví dụ toàn mảng.
- Các kiểm tra: nhiều khóa trùng, tất cả khóa bằng nhau, mảng rỗng, một phần tử và số âm.

Lưu file **`ThreeWayPartitionDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;
import java.util.Random;

public class ThreeWayPartitionDemo {
    record Bounds(int lt, int gt) {}

    static void swap(int[] a, int i, int j) {
        int temp = a[i];
        a[i] = a[j];
        a[j] = temp;
    }

    // Phân hoạch đoạn đóng [lo, hi]; pivot là a[lo].
    static Bounds partition3(int[] a, int lo, int hi) {
        Objects.requireNonNull(a, "array must not be null");
        if (lo < 0 || lo > hi || hi >= a.length) {
            throw new IllegalArgumentException("invalid nonempty range");
        }

        int pivot = a[lo];
        int lt = lo;
        int i = lo + 1;
        int gt = hi;

        while (i <= gt) {
            if (a[i] < pivot) {
                swap(a, lt, i);
                lt++;
                i++;
            } else if (a[i] > pivot) {
                swap(a, i, gt);
                gt--; // Khong tang i: phan tu moi chua duoc xet
            } else {
                i++;
            }
        }
        return new Bounds(lt, gt);
    }

    // Sap xep tai cho; xu ly mang rong va mang 1 phan tu.
    static void quickSort3(int[] a) {
        Objects.requireNonNull(a, "array must not be null");
        Random random = new Random();
        quickSort3(a, 0, a.length - 1, random);
    }

    // Chi de quy phia nho hon, lap tren phia lon hon.
    private static void quickSort3(
            int[] a, int lo, int hi, Random random) {
        while (lo < hi) {
            int pivotIndex = lo + random.nextInt(hi - lo + 1);
            swap(a, lo, pivotIndex);
            Bounds bounds = partition3(a, lo, hi);

            int leftLength = bounds.lt() - lo;
            int rightLength = hi - bounds.gt();

            if (leftLength < rightLength) {
                quickSort3(a, lo, bounds.lt() - 1, random);
                lo = bounds.gt() + 1;
            } else {
                quickSort3(a, bounds.gt() + 1, hi, random);
                hi = bounds.lt() - 1;
            }
        }
    }

    // Chi dung cho vi du phan hoach toan mang.
    static boolean isValidPartition(
            int[] a, int pivot, Bounds bounds) {
        for (int i = 0; i < bounds.lt(); i++) {
            if (a[i] >= pivot) return false;
        }
        for (int i = bounds.lt(); i <= bounds.gt(); i++) {
            if (a[i] != pivot) return false;
        }
        for (int i = bounds.gt() + 1; i < a.length; i++) {
            if (a[i] <= pivot) return false;
        }
        return true;
    }

    public static void main(String[] args) {
        int[] demo = {2, 3, 2, 1, 2, 3, 1, 2, 0};
        int pivot = demo[0];
        Bounds bounds = partition3(demo, 0, demo.length - 1);

        int lessCount = bounds.lt();
        int equalCount = bounds.gt() - bounds.lt() + 1;
        int greaterCount = demo.length - bounds.gt() - 1;

        System.out.println("Group counts (<,=,>): "
                + lessCount + ", " + equalCount + ", "
                + greaterCount);
        System.out.println("Equal block: "
                + Arrays.toString(Arrays.copyOfRange(
                        demo, bounds.lt(), bounds.gt() + 1)));
        System.out.println("Partition valid: "
                + isValidPartition(demo, pivot, bounds));

        int[] values = {5, 1, 5, 3, 2, 5, 1, 4, 3, 5, 0};
        quickSort3(values);
        System.out.println("Sorted: " + Arrays.toString(values));

        int[] allEqual = {7, 7, 7, 7, 7};
        quickSort3(allEqual);
        System.out.println("All equal: "
                + Arrays.toString(allEqual));

        int[] negative = {0, -3, 2, -3, 0, -1};
        quickSort3(negative);
        System.out.println("Negatives: "
                + Arrays.toString(negative));

        int[] empty = {};
        quickSort3(empty);
        System.out.println("Empty: " + Arrays.toString(empty));

        int[] one = {42};
        quickSort3(one);
        System.out.println("Single: " + Arrays.toString(one));
    }
}
```

Lệnh biên dịch và chạy (JDK 17 trở lên):

```bash
javac ThreeWayPartitionDemo.java
java ThreeWayPartitionDemo
```

**Stdout** (không phụ thuộc vị trí pivot ngẫu nhiên trong các lượt sắp xếp vì kết quả cuối đã được sắp tăng):

```text
Group counts (<,=,>): 3, 4, 2
Equal block: [2, 2, 2, 2]
Partition valid: true
Sorted: [0, 1, 1, 2, 3, 3, 4, 5, 5, 5, 5]
All equal: [7, 7, 7, 7, 7]
Negatives: [-3, -3, -1, 0, 0, 2]
Empty: []
Single: [42]
```

**Giải thích:**

- Trong ví dụ phân hoạch, pivot=2; có ba giá trị nhỏ hơn (1,1,0), bốn giá trị bằng và hai giá trị lớn hơn (3,3). Hai biên của vùng bằng là **lt=3, gt=6**.
- `Arrays.copyOfRange(demo, lt, gt+1)` chỉ sao chép **vùng bằng** để hiển thị; thuật toán `partition3` bản thân **không cấp phát mảng con**.
- `isValidPartition` kiểm tra quan hệ ba vùng cho ví dụ **phân hoạch toàn mảng**. Việc kiểm tra này là công cụ minh họa, không nằm trong các vòng phân hoạch của quicksort.
- `quickSort3` thay đổi mảng được truyền vào **tại chỗ**. Với mảng rỗng và một phần tử, `lo >= hi` nên vòng xử lý không chạy.
- Kết quả sắp xếp cuối cùng luôn tăng không giảm, dù trình tự hoán đổi trung gian phụ thuộc pivot được chọn.

### Vì sao phiên bản này có stack O(log n) ngay cả khi phân hoạch lệch?

Giả sử mỗi đoạn có m phần tử. Sau phân hoạch, hai vùng cần sắp tiếp có kích thước l và r với `l + r <= m - 1`. Ta **gọi đệ quy vùng nhỏ hơn**, có kích thước không quá `(m-1)/2`; vùng lớn hơn được xử lý bởi vòng `while` trong **cùng khung gọi hàm**. Vì kích thước bài toán ở mỗi mức đệ quy thực sự giảm ít nhất khoảng một nửa, độ sâu ngăn xếp tối đa O(log n) ngay cả khi một phía rất lớn. Điều này **không** biến thời gian trường hợp xấu O(n²) thành O(n log n); nó chỉ giảm nhu cầu stack.

Trong mã, nhánh xử lý vùng nhỏ hơn có thể được gọi với `lo > hi` (vùng rỗng). Vì vòng `while(lo < hi)` trả về ngay, việc đó là hợp lệ.

## 9. Những sai lầm thường gặp

1. **Tăng i sau khi đổi a[i] với a[gt].** Phần tử vừa vào vị trí i chưa được phân loại; phải giữ i, chỉ giảm gt.
2. **Quên tăng lt sau nhánh nhỏ hơn.** Khi đó vùng nhỏ hơn không mở rộng, bất biến bốn vùng bị phá.
3. **Dùng pivot = a[lo] xuyên suốt mà không lưu riêng.** Sau các hoán đổi, giá trị tại a[lo] có thể thay đổi; cần lưu `int pivot = a[lo]` trước vòng.
4. **Cho rằng mọi phần tử trong ba vùng đã sắp thứ tự nội bộ.** Phân hoạch chỉ đảm bảo quan hệ với pivot, không phải toàn bộ thứ tự tăng.
5. **Gọi đệ quy cả vùng bằng.** Mục tiêu của ba phía là bỏ qua toàn bộ các phần tử bằng pivot ở bước tiếp theo; gọi lại vùng này sẽ tạo việc làm dư thừa.
6. **Nhầm mảng con với toàn mảng.** Khi xử lý đoạn [lo,hi], chỉ đổi phần tử trong đoạn ấy; ranh giới lt,gt là **chỉ số tuyệt đối trên mảng**.
7. **Đồng nhất độ phức tạp phân hoạch với độ phức tạp sắp xếp.** Một lần phân hoạch O(m) không đồng nghĩa toàn bộ quicksort O(n), vì có nhiều mức phân hoạch.
8. **Gọi thuật toán ổn định vì có vùng bằng liên tiếp.** Các phép swap không giữ thứ tự ban đầu của những bản ghi có khóa bằng nhau.
9. **So sánh khóa bằng phép trừ.** Với int, phép trừ có thể tràn; so sánh trực tiếp hoặc dùng comparator.
10. **Chọn pivot đầu rồi khẳng định quicksort luôn O(n log n).** Quicksort vẫn có trường hợp xấu O(n²); pivot ngẫu nhiên chỉ cho cận kỳ vọng.
11. **Sai điều kiện dừng.** Khi `i > gt` mới hết vùng chưa biết. Nếu dừng khi `i == gt`, còn một phần tử chưa được phân loại.
12. **Giả định mọi bản sao bằng nhau là cùng một bản ghi.** Với đối tượng mang khóa và ID, các bản sao cùng khóa vẫn có thể khác ID; nếu cần giữ thứ tự ID, phải dùng chiến lược ổn định.

## 10. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** Với `a=[2,3,2,1,2,3,1,2,0]` và pivot=2, ba vùng cuối có bao nhiêu phần tử?

**Đáp án:** Nhỏ hơn 2 có 3 phần tử (1,1,0), bằng 2 có 4 phần tử, lớn hơn 2 có 2 phần tử (3,3). Ranh giới vùng bằng là lt=3, gt=6 khi phân hoạch toàn mảng.

**Câu 2.** Tại sao sau nhánh `a[i] > pivot` phải giữ nguyên i?

**Đáp án:** Vì a[gt] thuộc vùng chưa phân loại. Swap đưa giá trị chưa biết từ gt sang i; nếu i tăng ngay thì giá trị này chưa được kiểm tra và có thể ở sai vùng.

**Câu 3.** Bất biến nào quan trọng nhất để chứng minh kết thúc?

**Đáp án:** Độ dài vùng chưa biết `gt-i+1` là số nguyên không âm khi vòng còn chạy và giảm đúng 1 ở mỗi lượt: nhánh nhỏ hơn/bằng tăng i; nhánh lớn hơn giảm gt. Không thể có chuỗi giảm nghiêm ngặt vô hạn trong số nguyên không âm.

**Câu 4.** Một mảng có 1.000 phần tử đều bằng 7. Quicksort ba phía xử lý bao nhiêu bài toán con không rỗng sau phân hoạch đầu?

**Đáp án:** **0.** Tất cả nằm trong vùng bằng; phân hoạch đầu O(n) đã đủ để có mảng đúng thứ tự.

**Câu 5.** Ba phía có bảo đảm quicksort O(n log n) trường hợp xấu không?

**Đáp án:** **Không.** Nếu các khóa phần lớn phân biệt và pivot liên tục tạo phân hoạch lệch, vẫn có O(n²). Ngẫu nhiên hóa pivot giúp có kỳ vọng O(n log n), không phải bảo đảm cho mọi lần chạy.

**Câu 6.** Sau phân hoạch pivot=4, một đoạn có các nhóm `[1,3,2] | [4,4] | [7,5]`. Đã được sắp xếp hoàn toàn chưa?

**Đáp án:** **Chưa.** Các nhóm đã đúng tương quan với pivot, nhưng nhóm <4 đang có 3 trước 2, nhóm >4 có 7 trước 5. Cần tiếp tục sắp xếp hai nhóm ngoài.

**Câu 7.** Phân hoạch ba phía có giữ thứ tự của các bản ghi cùng khóa không?

**Đáp án:** Không có bảo đảm. Thuật toán hoán đổi tại chỗ làm thay đổi thứ tự tương đối; muốn ổn định phải dùng thuật toán/cách phân hoạch có cam kết giữ thứ tự.

**Câu 8.** Vì sao “đệ quy phía nhỏ hơn, lặp phía lớn hơn” giúp giảm stack?

**Đáp án:** Phía nhỏ hơn có kích thước không quá một nửa đoạn hiện tại, nên mỗi mức đệ quy thực sự giảm nhanh kích thước còn xử lý. Phía lớn hơn dùng lại cùng khung gọi hàm, làm độ sâu stack O(log n) ngay cả trong trường hợp phân hoạch lệch.

## Ghi nhớ

Phân hoạch ba phía chia đoạn quanh pivot thành **< pivot | = pivot | > pivot** bằng cách duy trì bốn vùng trong lúc quét: đã nhỏ, đã bằng, chưa biết, đã lớn. Dùng ba chỉ số `lt, i, gt`; **chỉ tăng i khi phần tử tại i đã được phân loại**, giữ i khi đổi với gt. Vòng lặp chạy **Θ(m)** trên đoạn m phần tử, dùng **O(1)** bộ nhớ phụ và trả về hai biên của nhóm bằng. Trong quicksort, **bỏ qua nhóm bằng pivot** giúp tránh xử lý lặp lại nhiều khóa trùng; thời gian kỳ vọng O(n log n), với trường hợp tất cả khóa bằng nhau có thể xuống Θ(n), nhưng thời gian trường hợp xấu vẫn O(n²).
