# Quicksort và các cách phân hoạch

**Quicksort** là thuật toán sắp xếp dựa trên phép so sánh và chiến lược **chia để trị**. Mỗi lượt chọn một giá trị làm **pivot (chốt)**, rồi *phân hoạch (partition)* phần mảng đang xét thành các vùng có quan hệ thứ tự đã biết với pivot. Sau đó ta tiếp tục sắp xếp những vùng còn cần xử lý. Quicksort thường có thời gian O(n log n) trong tình huống thuận lợi hoặc trung bình với giả thiết phân hoạch cân đối thích hợp, nhưng có thể giảm xuống O(n²) nếu liên tục tạo các vùng rất lệch.

Điều quan trọng nhất để hiểu và cài đặt Quicksort là: **cách phân hoạch quyết định bất biến của từng vùng, giá trị mà hàm partition trả về, và đoạn nào được đệ quy tiếp**. Không được thay thế tùy tiện các biên đệ quy của Lomuto, Hoare và phân hoạch ba phía cho nhau.

Bài này thuộc nhóm **Sắp xếp so sánh**, dùng mảng số nguyên và thứ tự tăng dần để giải thích ba cách phân hoạch phổ biến: **Lomuto**, **Hoare** và **Dutch National Flag ba phía (<, =, >)**. Chúng cùng có thể đưa mảng về thứ tự tăng dần nhưng tổ chức các phần tử quanh pivot khác nhau.

## 1. Đặc tả sắp xếp và khung thuật toán

**Đầu vào:** một mảng int không null, có thể rỗng, có phần tử âm, trùng nhau hoặc ở giới hạn của int.

**Đầu ra:** mảng đầu vào được thay đổi tại chỗ để thỏa điều kiện a[i] ≤ a[i+1] với mọi chỉ số hợp lệ. Tập giá trị và **số lần xuất hiện** của mỗi giá trị phải được bảo toàn; không được làm mất hay tự sinh phần tử.

**Vấn đề cần phân biệt:** ở đây trả về kết quả trực tiếp trong mảng thay vì trả về một mảng mới. Các biến thể bên dưới đều không bảo đảm **tính ổn định (stability)**: nếu hai bản ghi có khóa bằng nhau thì thứ tự tương đối của chúng có thể thay đổi; với int thuần túy không quan sát được sự khác biệt đó.

Khung Quicksort:

1. Nếu đoạn hiện tại chỉ có 0 hoặc 1 phần tử thì đã có thứ tự, kết thúc nhánh.
2. Chọn pivot và phân hoạch đoạn để hình thành những vùng có quan hệ đã chứng minh với pivot.
3. Chỉ đệ quy vào những vùng cần sắp xếp; vùng đã được xác định đúng vị trí hoặc toàn bộ vùng có giá trị bằng pivot không cần sắp xếp lại.
4. Khi các đoạn nhỏ đã có thứ tự, toàn bộ đoạn lớn được sắp xếp.

Quicksort khác Merge Sort ở bước trung tâm: Merge Sort chia rồi **trộn hai nửa đã sắp xếp**, còn Quicksort **phân hoạch trước**, nhờ đó các quan hệ giữa hai vùng được bảo đảm từ trước khi đệ quy.

## 2. Pivot là giá trị so sánh, không nhất thiết là vị trí cố định

Có thể chọn pivot bằng phần tử đầu, cuối, giữa, ngẫu nhiên hoặc một ước lượng như median-of-three. Chọn pivot không đổi nội dung phép so sánh, nhưng ảnh hưởng độ cân đối và số lần xử lý.

**Cần phân biệt:**

- **Giá trị pivot** dùng để quyết định phần tử nhỏ/lớn/bằng trong lượt phân hoạch.
- **Chỉ số chứa pivot ban đầu** là một vị trí trong mảng, có thể thay đổi giá trị khi hoán đổi.
- **Biên phân hoạch** chỉ là đường ranh giới giữa các vùng có quan hệ thứ tự; với Hoare, đó thường **không phải vị trí cuối cùng của pivot**.

Trong ví dụ Java, Lomuto chọn phần tử cuối làm pivot, còn Hoare và ba phía chụp **giá trị** ở vị trí giữa. Việc lưu giá trị pivot vào biến riêng giúp phép so sánh nhất quán ngay cả khi các phần tử bị hoán đổi.

## 3. Phân hoạch Lomuto: chốt về đúng một vị trí

Dùng đoạn chỉ số **[lo, hi]** (hai đầu đều bao gồm), chọn pivot = a[hi]. Trong vòng lặp j từ lo tới hi − 1, duy trì biến i làm ranh giới:

- Đoạn **[lo, i)** chứa toàn bộ phần tử đã gặp nhỏ hơn pivot.
- Đoạn **[i, j)** chứa toàn bộ phần tử đã gặp lớn hơn hoặc bằng pivot.
- Đoạn **[j, hi)** chưa được kiểm tra.
- a[hi] vẫn giữ giá trị pivot cho đến thao tác cuối.

Khi a[j] < pivot, đổi a[i] với a[j] và tăng i. Khi a[j] ≥ pivot, chỉ tăng j. Sau vòng lặp, đổi a[i] với a[hi]. Kết quả:

**a[lo..i−1] < pivot; a[i] = pivot; a[i+1..hi] ≥ pivot.**

Hàm partition **trả về i**, chính là vị trí cuối cùng của một bản sao pivot. Vì pivot ở i đã đúng trong mảng kết quả, đệ quy vào **[lo, i−1]** và **[i+1, hi]**.

Giả mã:

~~~text
LOMUTO(a, lo, hi):
    pivot = a[hi]
    i = lo
    cho j chạy từ lo tới hi - 1:
        nếu a[j] < pivot:
            đổi a[i], a[j]
            i = i + 1
    đổi a[i], a[hi]
    trả về i
~~~

Với mảng **[4, 1, 4, 2, 4]**, pivot cuối là 4. Sau khi duyệt j, hai giá trị 1 và 2 được đưa sang đầu. Đổi pivot về i = 2 thu được **[1, 2, 4, 4, 4]**. Vị trí 2 của pivot được cố định, còn hai nửa có thể tiếp tục sắp xếp.

**Nhược điểm quan trọng:** nếu mảng đã tăng dần và pivot luôn là phần tử cuối, mỗi lượt phân hoạch đưa pivot lớn nhất về cuối rồi chỉ rút đi một phần tử. Nếu mọi phần tử bằng nhau, điều kiện < pivot không bao giờ đúng; mỗi lượt cũng chỉ cố định một vị trí. Cả hai là tình huống dễ dẫn đến O(n²) và độ sâu đệ quy O(n).

## 4. Phân hoạch Hoare: đổi phần tử sai phía rồi trả về biên

Hoare dùng hai con trỏ đi từ hai đầu của **[lo, hi]**. Ví dụ có thể chọn pivot bằng giá trị a[lo + (hi − lo)/2]. Hai con trỏ di chuyển cho đến khi:

- i dừng tại một phần tử **≥ pivot** ở phía trái;
- j dừng tại một phần tử **≤ pivot** ở phía phải.

Nếu i < j, hai phần tử đang ở phía chưa phù hợp được hoán đổi. Nếu i ≥ j, phân hoạch hoàn tất và **trả về j**.

Tại điểm trả về j, hai đoạn được xác lập:

- **[lo, j]** chỉ chứa các giá trị **≤ pivot**;
- **[j+1, hi]** chỉ chứa các giá trị **≥ pivot**.

Các giá trị bằng pivot có thể xuất hiện ở **cả hai phía**. Chúng không nhất thiết nằm tập trung ở trung tâm. Với việc chọn pivot từ một phần tử trong đoạn và dùng các vòng quét nghiêm ngặt như chương trình bên dưới, các lời gọi không rỗng sẽ rút ngắn kích thước đoạn.

**Khác Lomuto:** giá trị trả về j là **biên**, không khẳng định a[j] bằng pivot hoặc đã ở vị trí cuối. Đệ quy phải là **[lo, j]** và **[j+1, hi]**. Nếu vô tình dùng công thức [lo, j−1] và [j+1, hi], ta có thể bỏ sót a[j] chưa được sắp xếp.

Giả mã:

~~~text
HOARE(a, lo, hi):
    pivot = a[lo + (hi - lo) / 2]
    i = lo - 1
    j = hi + 1
    lặp:
        tăng i cho đến khi a[i] >= pivot
        giảm j cho đến khi a[j] <= pivot
        nếu i >= j: trả về j
        đổi a[i], a[j]
~~~

Với **[4, 1, 4, 2, 4]**, chọn pivot từ giữa nên giá trị pivot = 4. Một trạng thái sau phân hoạch hợp lệ là **[4, 1, 2 | 4, 4]**, biên j = 2. Nửa trái chưa có thứ tự, dù mọi phần tử bên trái ≤ 4 và mọi phần tử bên phải ≥ 4. Chính hai lời gọi đệ quy tiếp theo đưa cả mảng về thứ tự.

**Ưu điểm thường gặp:** cách quét từ hai đầu có thể giảm một số thao tác đổi chỗ so với các cách cài đặt Lomuto, và xử lý nhiều phần tử bằng nhau cân đối hơn trong ví dụ này. Tuy nhiên, không có bảo đảm rằng Hoare luôn nhanh hơn trên mọi dữ liệu; kết quả còn tùy pivot, phân bố giá trị, cách cài đặt và chi phí bộ nhớ/cache.

## 5. Phân hoạch ba phía: tách rõ vùng bằng pivot

Khi có nhiều phần tử trùng nhau, phân hoạch nhị phân thường làm công việc dư thừa: các phần tử bằng pivot vẫn bị chia vào hai vùng rồi tiếp tục tham gia những lần đệ quy. Phân hoạch ba phía (Dutch National Flag) duy trì bốn miền trong đoạn [lo, hi]:

| Miền | Ý nghĩa |
| --- | --- |
| **[lo, lt)** | Các phần tử nhỏ hơn pivot |
| **[lt, i)** | Các phần tử bằng pivot |
| **[i, gt]** | Các phần tử chưa phân loại |
| **(gt, hi]** | Các phần tử lớn hơn pivot |

Khởi tạo lt = lo, i = lo, gt = hi. Khi i ≤ gt, xét a[i]:

1. Nếu **a[i] < pivot**, đổi a[i] với a[lt], tăng cả lt và i.
2. Nếu **a[i] = pivot**, chỉ tăng i để mở rộng vùng bằng nhau.
3. Nếu **a[i] > pivot**, đổi a[i] với a[gt] rồi **giảm gt nhưng giữ i**, vì phần tử vừa chuyển từ cuối sang i chưa được kiểm tra.

Khi dừng, i = gt + 1; mọi phần tử đã thuộc một trong ba nhóm. Kết quả:

**[lo, lt−1] < pivot; [lt, gt] = pivot; [gt+1, hi] > pivot.**

Chỉ cần đệ quy vào **[lo, lt−1]** và **[gt+1, hi]**. Toàn bộ đoạn bằng pivot ở giữa không cần phân hoạch lại.

Giả mã:

~~~text
THREE_WAY(a, lo, hi):
    pivot = a[lo + (hi - lo) / 2]
    lt = lo, i = lo, gt = hi
    trong khi i <= gt:
        nếu a[i] < pivot:
            đổi a[lt], a[i]; tăng lt và i
        ngược lại nếu a[i] > pivot:
            đổi a[i], a[gt]; giảm gt
        ngược lại:
            tăng i
    đệ quy [lo, lt - 1] và [gt + 1, hi]
~~~

Với **[4, 1, 4, 2, 4]** và pivot 4, ta có vùng nhỏ hơn là **[1, 2]**, vùng bằng là **[4, 4, 4]**, vùng lớn hơn rỗng. Với mảng **[7, 7, 7, 7]**, một lượt O(n) gom mọi phần tử vào vùng bằng, rồi cả hai nhánh đệ quy đều rỗng: trường hợp nhiều giá trị trùng trở nên rất thuận lợi.

## 6. Ba bất biến dẫn đến ba quy tắc đệ quy khác nhau

| Phân hoạch | Bất biến / hậu điều kiện chính | Trả về hoặc biên sau bước | Đoạn đệ quy tiếp |
| --- | --- | --- | --- |
| **Lomuto** | Trái < pivot, vị trí i = pivot, phải ≥ pivot | Trả **chỉ số i** của pivot cố định | **[lo, i−1]** và **[i+1, hi]** |
| **Hoare** | Trái ≤ pivot, phải ≥ pivot, giá trị bằng có thể ở hai bên | Trả **biên j**, chưa chắc a[j] là pivot | **[lo, j]** và **[j+1, hi]** |
| **Ba phía** | Trái < pivot, giữa = pivot, phải > pivot | Hai biên **lt, gt** quanh vùng bằng | **[lo, lt−1]** và **[gt+1, hi]** |

Đây là chỗ dễ nhầm nhất. Người học thường nhớ “sau partition thì bỏ pivot và đệ quy hai bên”; phát biểu này **chỉ đúng trực tiếp cho Lomuto** khi pivot thật sự đã về một vị trí cuối. Với Hoare phải giữ cả hai phần theo biên, còn với ba phía phải bỏ cả vùng bằng pivot.

## 7. Chứng minh vì sao phân hoạch và Quicksort đúng

**Lomuto:**

- Ban đầu [lo, i) và [i, j) đều rỗng, nên bất biến đúng.
- Mỗi bước j chuyển một phần tử vào vùng < pivot hoặc mở rộng vùng ≥ pivot. Hoán đổi không làm thay đổi đa tập giá trị.
- Sau khi duyệt hết, đổi pivot a[hi] về i bảo đảm mọi giá trị bên trái < a[i] và bên phải ≥ a[i]. Nếu hai đoạn con được sắp xếp, toàn bộ đoạn cũng được sắp xếp.

**Hoare:**

- Hai con trỏ tiến vào trong tới các phần tử có thể đang ở phía sai: phần tử bên trái ≥ pivot và phần tử bên phải ≤ pivot.
- Nếu chưa giao nhau, hoán đổi giúp củng cố điều kiện ≤ pivot ở phía trái và ≥ pivot ở phía phải. Những vùng đã quét qua không cần xét lại.
- Khi giao nhau, ranh giới j tách hai miền có quan hệ với pivot. Vì mỗi đoạn con ngắn hơn đoạn ban đầu, quy nạp trên độ dài cho thấy sau hai lời gọi đệ quy, từng miền đã có thứ tự. Mọi giá trị miền trái ≤ pivot ≤ mọi giá trị miền phải, nên ghép hai miền vẫn có thứ tự.

**Ba phía:**

- Bốn miền trong bảng ở mục 5 là bất biến trước mỗi lượt kiểm tra. Mỗi nhánh cập nhật đúng một miền đã phân loại; trường hợp > pivot giữ nguyên i để không bỏ qua phần tử mới chuyển vào.
- Số phần tử chưa xét, **gt−i+1**, giảm một đơn vị mỗi lượt, nên vòng phân hoạch dừng.
- Sau khi dừng, ba miền <, =, > đã hình thành. Chỉ cần sắp xếp hai miền không bằng pivot rồi ghép theo thứ tự.

**Tính dừng của Quicksort:** đoạn có 0 hoặc 1 phần tử dừng ngay. Mỗi cách partition bên dưới được sử dụng với các biên đệ quy tương ứng sao cho các đoạn được gọi tiếp có độ dài **nhỏ hơn nghiêm ngặt** đoạn cha. Quy nạp theo độ dài chứng minh toàn bộ thuật toán dừng và trả về mảng không giảm, đồng thời chỉ hoán đổi nên bảo toàn đa tập phần tử.

## 8. Java 17+ hoàn chỉnh: chạy cả ba chiến lược

Chương trình sau triển khai cả ba kiểu bằng phương thức riêng, không dùng thư viện sắp xếp để tạo ra kết quả của các thuật toán đang học. **Arrays.sort chỉ dùng trong phần kiểm thử** làm chuẩn kết quả. Mảng đầu vào được sửa trực tiếp; các hàm công khai ném IllegalArgumentException nếu mảng null.

Lưu nguyên chương trình trong tệp **QuicksortPartitions.java**:

~~~java
import java.util.Arrays;

public final class QuicksortPartitions {
    private QuicksortPartitions() {
    }

    private static void swap(int[] a, int i, int j) {
        int temp = a[i];
        a[i] = a[j];
        a[j] = temp;
    }

    private static void requireArray(int[] a) {
        if (a == null) {
            throw new IllegalArgumentException("array must not be null");
        }
    }

    public static void sortLomuto(int[] a) {
        requireArray(a);
        quickLomuto(a, 0, a.length - 1);
    }

    private static void quickLomuto(int[] a, int lo, int hi) {
        if (lo >= hi) {
            return;
        }
        int pivotIndex = partitionLomuto(a, lo, hi);
        quickLomuto(a, lo, pivotIndex - 1);
        quickLomuto(a, pivotIndex + 1, hi);
    }

    private static int partitionLomuto(int[] a, int lo, int hi) {
        int pivot = a[hi];
        int i = lo;
        for (int j = lo; j < hi; j++) {
            if (a[j] < pivot) {
                swap(a, i, j);
                i++;
            }
        }
        swap(a, i, hi);
        return i;
    }

    public static void sortHoare(int[] a) {
        requireArray(a);
        quickHoare(a, 0, a.length - 1);
    }

    private static void quickHoare(int[] a, int lo, int hi) {
        if (lo >= hi) {
            return;
        }
        int boundary = partitionHoare(a, lo, hi);
        quickHoare(a, lo, boundary);
        quickHoare(a, boundary + 1, hi);
    }

    private static int partitionHoare(int[] a, int lo, int hi) {
        int pivot = a[lo + (hi - lo) / 2];
        int i = lo - 1;
        int j = hi + 1;

        while (true) {
            do {
                i++;
            } while (a[i] < pivot);
            do {
                j--;
            } while (a[j] > pivot);

            if (i >= j) {
                return j;
            }
            swap(a, i, j);
        }
    }

    public static void sortThreeWay(int[] a) {
        requireArray(a);
        quickThreeWay(a, 0, a.length - 1);
    }

    private static void quickThreeWay(int[] a, int lo, int hi) {
        if (lo >= hi) {
            return;
        }

        int pivot = a[lo + (hi - lo) / 2];
        int lt = lo;
        int i = lo;
        int gt = hi;

        while (i <= gt) {
            if (a[i] < pivot) {
                swap(a, lt, i);
                lt++;
                i++;
            } else if (a[i] > pivot) {
                swap(a, i, gt);
                gt--;
            } else {
                i++;
            }
        }

        quickThreeWay(a, lo, lt - 1);
        quickThreeWay(a, gt + 1, hi);
    }

    private static void checkOne(int[] input) {
        int[] expected = input.clone();
        Arrays.sort(expected);

        int[] lomuto = input.clone();
        int[] hoare = input.clone();
        int[] threeWay = input.clone();
        sortLomuto(lomuto);
        sortHoare(hoare);
        sortThreeWay(threeWay);

        if (!Arrays.equals(expected, lomuto)
                || !Arrays.equals(expected, hoare)
                || !Arrays.equals(expected, threeWay)) {
            throw new AssertionError(
                "Input=" + Arrays.toString(input)
                + ", expected=" + Arrays.toString(expected)
                + ", lomuto=" + Arrays.toString(lomuto)
                + ", hoare=" + Arrays.toString(hoare)
                + ", threeWay=" + Arrays.toString(threeWay)
            );
        }
    }

    private static void verifySmallArrays() {
        int[] alphabet = {-2, -1, 0, 1, 2};
        int checked = 0;

        for (int length = 0; length <= 6; length++) {
            int combinations = 1;
            for (int i = 0; i < length; i++) {
                combinations *= alphabet.length;
            }

            for (int encoded = 0; encoded < combinations; encoded++) {
                int[] input = new int[length];
                int remaining = encoded;
                for (int i = 0; i < length; i++) {
                    input[i] = alphabet[remaining % alphabet.length];
                    remaining /= alphabet.length;
                }
                checkOne(input);
                checked++;
            }
        }

        checkOne(new int[] {
            Integer.MAX_VALUE, Integer.MIN_VALUE, 0, -1,
            Integer.MAX_VALUE
        });
        checkOne(new int[] {9, 8, 7, 6, 5, 4, 3, 2, 1});
        checkOne(new int[] {1, 2, 3, 4, 5, 6, 7, 8, 9});
        checkOne(new int[] {4, 4, 4, 4, 4, 4});

        System.out.println("Verified " + checked + " generated arrays: PASS");
        System.out.println("Additional boundary arrays: PASS");
    }

    public static void main(String[] args) {
        int[] input = {4, 1, 4, 2, 4};
        int[] a = input.clone();
        int[] b = input.clone();
        int[] c = input.clone();

        sortLomuto(a);
        sortHoare(b);
        sortThreeWay(c);

        System.out.println("Lomuto: " + Arrays.toString(a));
        System.out.println("Hoare: " + Arrays.toString(b));
        System.out.println("Three-way: " + Arrays.toString(c));

        int[] extremes = {
            Integer.MAX_VALUE, 0, Integer.MIN_VALUE, -1,
            Integer.MAX_VALUE
        };
        sortThreeWay(extremes);
        System.out.println("Extremes: " + Arrays.toString(extremes));

        verifySmallArrays();
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac QuicksortPartitions.java
java QuicksortPartitions
~~~

Đầu ra chính xác:

~~~text
Lomuto: [1, 2, 4, 4, 4]
Hoare: [1, 2, 4, 4, 4]
Three-way: [1, 2, 4, 4, 4]
Extremes: [-2147483648, -1, 0, 2147483647, 2147483647]
Verified 19531 generated arrays: PASS
Additional boundary arrays: PASS
~~~

Phần kiểm thử tự sinh **19.531** mảng độ dài 0 đến 6 từ 5 giá trị {-2, -1, 0, 1, 2}, với số lượng 1 + 5 + 25 + 125 + 625 + 3.125 + 15.625 = 19.531. Mỗi mảng được sắp xếp ba lần bằng ba chiến lược và so sánh với Arrays.sort trên bản sao độc lập. Nếu khác nhau, chương trình ném AssertionError và in dữ liệu đầu vào cùng tất cả kết quả. Sau đó nó còn kiểm tra bốn mảng biên: int cực trị, tăng dần, giảm dần và toàn giá trị bằng nhau. Dòng PASS chỉ xác nhận các ca kiểm thử đã chạy thành công, **không tự thay thế chứng minh đúng cho mọi đầu vào**.

## 9. Độ phức tạp và bộ nhớ

Một phép partition duyệt hoặc quét mỗi phần tử của đoạn hiện tại một số lần hữu hạn, có thời gian **O(m)** với m là độ dài đoạn. Quicksort có biểu thức gần đúng **T(n) = T(k) + T(n−k−1) + O(n)** cho Lomuto, với k là số phần tử rơi vào bên trái pivot.

- **Phân hoạch cân đối:** k xấp xỉ n/2, độ sâu khoảng log n, tổng thời gian O(n log n).
- **Phân hoạch lệch liên tục:** một nhánh dài n−1, nhánh kia rỗng, tổng thời gian O(n²).
- **Chọn pivot ngẫu nhiên:** giúp đạt kỳ vọng O(n log n) trong mô hình các pivot được chọn ngẫu nhiên phù hợp, song vẫn có khả năng gặp trường hợp rất xấu.
- **Hoare và ba phía:** phương trình đệ quy phụ thuộc kích thước các vùng chúng trả về; nếu phần bằng pivot nhiều, ba phía có thể giảm đáng kể công việc vì bỏ qua cả miền bằng nhau sau một lần phân hoạch.

Với cách cài đặt đệ quy trực tiếp bên dưới, các phép hoán đổi và một lượt partition dùng **O(1) bộ nhớ phụ tại chỗ**, không cấp thêm mảng có kích thước tỉ lệ n. Tuy nhiên, **ngăn xếp đệ quy** cần O(log n) trong trường hợp cân đối và có thể tăng đến O(n) trong trường hợp phân hoạch cực lệch. Vì vậy nếu gọi “Quicksort có O(1) bộ nhớ” mà bỏ qua stack thì không đầy đủ.

Không thể khẳng định mọi chuỗi dữ liệu đều được sắp xếp trong O(n log n) chỉ từ việc chọn pivot ở giữa **vị trí chỉ số**; một đầu vào có chủ đích vẫn có thể làm các giá trị pivot dẫn đến phân hoạch xấu. Trong hệ thống cần bảo đảm thời gian xấu nhất, có thể áp dụng **introsort** (chuyển sang heapsort khi đệ quy quá sâu), hoặc giới hạn độ sâu rồi dùng thuật toán dự phòng. Nếu cần bảo đảm ổn định, phải chọn thuật toán/cài đặt khác hoặc bổ sung cơ chế giữ thứ tự.

## 10. Chọn chiến lược theo đặc trưng dữ liệu

| Đặc điểm | Lomuto | Hoare | Ba phía |
| --- | --- | --- | --- |
| Dễ giải thích pivot ở vị trí cuối | Rõ ràng, trả đúng chỉ số pivot | Trả biên, pivot chưa chắc cố định | Cố định cả một vùng bằng pivot |
| Nhiều phần tử trùng nhau | Có thể phân hoạch rất lệch khi dùng so sánh < | Hai con trỏ có thể chia giá trị bằng ra hai nhánh | Thường tốt, bỏ vùng bằng ngay |
| Dữ liệu đã tăng hoặc giảm | Pivot cuối dễ làm lệch n−1 : 0 | Pivot giữa theo chỉ số thường cân đối với dữ liệu đã sắp | Pivot giữa theo chỉ số thường hợp lý trong trường hợp này |
| Bộ nhớ partition | O(1) | O(1) | O(1) |
| Điều kiện cần nhớ | Phân biệt < và ≥ | Trả biên j, giữ [lo, j] | Giữ nguyên i sau khi đổi với gt |

**Lomuto** phù hợp để bắt đầu học bất biến và vị trí pivot. **Hoare** minh họa phân hoạch bằng hai con trỏ với ranh giới đệ quy khác. **Ba phía** là lựa chọn có ích khi dữ liệu trùng nhiều. Với hệ thống thực tế, cần benchmark theo phân bố dữ liệu, yêu cầu ổn định, giới hạn stack và kiểu dữ liệu; không thể chọn chiến lược chỉ bằng tên.

## 11. Các lỗi thường gặp

1. **Trộn công thức đệ quy:** partition Hoare trả j, nhưng lại gọi [lo, j−1], bỏ sót phần tử ở j. Hoặc partition Lomuto trả vị trí pivot nhưng tiếp tục đệ quy bao gồm vị trí đó.
2. **Không làm giảm đoạn:** khi dùng Hoare mà chọn pivot/điều kiện không đồng bộ, có thể trả biên bằng hi và lặp lại nguyên đoạn. Phải kiểm tra cả quy tắc chọn pivot, điều kiện quét và đoạn đệ quy.
3. **Dùng <= thay vì < mà không xét lại bất biến:** trong Lomuto, thay đổi điều kiện có thể vẫn tạo một partition hợp lệ kiểu khác, nhưng cách xử lý giá trị bằng pivot và hiệu năng thay đổi; phải chứng minh lại các vùng.
4. **Tăng i ngay sau khi đổi với gt ở ba phía:** phần tử chuyển từ a[gt] sang a[i] chưa được phân loại; tăng i có thể bỏ sót nó.
5. **Coi pivot Hoare đã nằm đúng vị trí:** j chỉ là biên chia; a[j] không nhất thiết bằng pivot.
6. **Sai biên rỗng/một phần tử:** quên điều kiện lo >= hi làm các đoạn vô nghĩa vẫn truy cập phần tử.
7. **Coi O(n log n) là bảo đảm mọi trường hợp:** độ sâu phân hoạch xấu vẫn làm n² phép toán và có nguy cơ StackOverflowError trong Java.
8. **Quên tính ổn định:** hoán đổi xa có thể đảo thứ tự các bản ghi có khóa trùng nhau.
9. **Quên bảo toàn dữ liệu:** sắp xếp phải bảo toàn số lần xuất hiện của từng giá trị; so mỗi đầu ra với mảng đã sắp bằng thư viện là cách kiểm thử cả tính bảo toàn.
10. **Tính pivot bằng (lo + hi)/2:** có thể tràn int trong những bối cảnh chỉ số lớn; công thức lo + (hi−lo)/2 an toàn hơn với biên hợp lệ.

## 12. Kiểm thử và cách giải thích phản ví dụ

| Trường hợp | Đầu vào | Kết quả tăng dần |
| --- | --- | --- |
| Rỗng | [] | [] |
| Một phần tử | [8] | [8] |
| Đã tăng | [1, 2, 3, 4] | [1, 2, 3, 4] |
| Giảm hoàn toàn | [4, 3, 2, 1] | [1, 2, 3, 4] |
| Mọi giá trị bằng nhau | [7, 7, 7] | [7, 7, 7] |
| Trùng xen kẽ | [4, 1, 4, 2, 4] | [1, 2, 4, 4, 4] |
| Chứa số âm | [0, -3, 2, -1] | [-3, -1, 0, 2] |
| Biên int | [MAX_VALUE, MIN_VALUE, 0] | [MIN_VALUE, 0, MAX_VALUE] |
| Mảng null | null | IllegalArgumentException |

Khi một hiện thực trả kết quả khác Arrays.sort, trước tiên ghi lại mảng gốc và pivot tại lượt phân hoạch gây sai khác. Kiểm tra hậu điều kiện partition và việc đoạn đệ quy có bỏ sót hay chồng lặp vị trí nào không. Với dữ liệu ngẫu nhiên, dùng seed cố định để tái hiện; nếu có thể, thu nhỏ mảng cho tới khi còn phản ví dụ ngắn nhất. Ví dụ **[2, 1]** đã đủ để phát hiện nhiều lỗi điều kiện dừng hoặc đổi chỗ.

**Kiểm thử hiệu năng riêng với kiểm thử đúng đắn:** dùng kích thước lớn và đo nhiều lần sau giai đoạn warm-up, so sánh kiểu phân phối dữ liệu (đã sắp xếp, gần sắp xếp, toàn giá trị giống nhau, ngẫu nhiên). Đừng lấy riêng số mili giây của một trường hợp nhỏ làm bằng chứng chiến lược nào luôn nhanh nhất.

## 13. Mở rộng: từ Quicksort đến Quickselect

Partition là thao tác dùng chung cho nhiều thuật toán. Nếu mục tiêu là tìm phần tử ở thứ hạng k, **Quickselect** dùng partition để biết k nằm ở vùng nào, rồi chỉ tiếp tục xử lý vùng có thể chứa đáp án; không nhất thiết sắp xếp toàn bộ mảng. Với phân hoạch ba phía, nếu k nằm trong đoạn bằng pivot thì có thể trả lời ngay mà không cần đệ quy.

Tuy nhiên, đừng nhầm Quicksort và Quickselect: Quicksort phải xử lý các vùng còn cần sắp xếp để bảo đảm **toàn bộ mảng có thứ tự**, còn Quickselect chỉ cần tìm **một thứ hạng**. Chúng cùng tận dụng bất biến partition nhưng điều kiện dừng và đầu ra khác nhau.

## 14. Checklist tự cài đặt đúng

Trước khi viết Quicksort cho một đề mới:

1. **Chọn hợp đồng:** sắp xếp tăng hay giảm, có yêu cầu stable, có được sửa mảng đầu vào không?
2. **Chọn partition:** Lomuto, Hoare hay ba phía; định nghĩa chính xác giá trị trả về và các miền sau lượt phân hoạch.
3. **Viết bất biến vòng lặp:** mỗi miền đã chứa những phần tử so với pivot; miền nào còn chưa kiểm tra?
4. **Chứng minh giảm tiến độ:** mỗi lượt quét thu hẹp miền chưa xét, mỗi lời gọi đệ quy giảm chiều dài đoạn.
5. **Ghép partition với đúng các đoạn đệ quy:** không dùng một công thức cho mọi cách phân hoạch.
6. **Kiểm thử:** mảng rỗng, một phần tử, đã tăng/giảm, nhiều phần tử bằng nhau, trùng xen kẽ, số âm và giá trị biên.
7. **Đánh giá hiệu quả:** chọn pivot, số phép so sánh và đổi chỗ, độ sâu stack, tính ổn định, phân phối dữ liệu và phương án dự phòng nếu cần.

**Câu hỏi tự kiểm tra:** tại sao Lomuto trả về vị trí cuối của pivot, nhưng Hoare chỉ trả về một ranh giới? Vì sao ba phía phải giữ nguyên i sau khi đổi với gt? Nếu mọi giá trị đều bằng nhau, tại sao Lomuto với pivot cuối suy biến còn ba phía có thể xử lý gần như một lượt duy nhất?

Nắm được các **bất biến phân hoạch** là chìa khóa để vừa hiện thực Quicksort đúng, vừa nhận biết khi nào một biến thể có ưu hoặc nhược điểm. Một khi điều kiện các miền và biên đệ quy đã rõ, thuật toán không còn là một công thức đổi chỗ cần học thuộc mà trở thành một quy trình có thể chứng minh và kiểm thử.
