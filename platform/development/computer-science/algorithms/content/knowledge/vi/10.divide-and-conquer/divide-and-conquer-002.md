# Điều kiện cơ sở và bảo đảm kích thước giảm

Trong **chia để trị (divide and conquer)**, một bài toán lớn được chia thành các bài toán con, giải chúng rồi kết hợp kết quả. Để cách làm này là một thuật toán hữu hạn và đúng, hai câu hỏi cần được trả lời trước khi viết lời gọi đệ quy:

1. **Khi nào dừng?** Đây là **điều kiện cơ sở (base case)** và hành động trả kết quả trực tiếp.
2. **Vì sao mỗi lời gọi tiếp theo tiến gần tới điều kiện cơ sở?** Đây là **bảo đảm kích thước giảm** theo một thước đo rõ ràng.

Nếu chỉ có base case nhưng một nhánh vẫn nhận lại đúng bài toán ban đầu, chương trình có thể đệ quy vô hạn và gây StackOverflowError. Nếu kích thước giảm nhưng không có cách xử lý trường hợp nhỏ nhất hoặc biên rỗng, chương trình vẫn có thể truy cập sai chỉ số hoặc tính sai kết quả.

Bài học thuộc nhóm **Chia để trị** của Computer Science Algorithms. Ta sẽ dùng đoạn mảng **nửa mở [lo, hi)**, merge sort và phép tìm giá trị lớn nhất làm ví dụ, rồi mở rộng lập luận sang tìm kiếm nhị phân, Quicksort và các bài toán chia để trị khác.

## 1. Phân biệt dừng, đúng đắn và hiệu năng

Ba thuộc tính thường bị nhầm lẫn:

- **Dừng (termination):** lời gọi cuối cùng sẽ trả về, không gọi đệ quy mãi.
- **Đúng đắn (correctness):** giá trị trả về hoặc mảng sau khi sửa thỏa đặc tả, kể cả khi đầu vào rỗng hoặc có phần tử trùng.
- **Hiệu năng (complexity):** tổng số phép toán và lượng bộ nhớ/stack được dùng.

Một thuật toán giảm kích thước đi 1 mỗi lần **có thể dừng** nhưng vẫn có độ sâu O(n). Một thuật toán giảm kích thước còn khoảng một nửa thường có độ sâu O(log n), nhưng thời gian tổng cộng còn phụ thuộc **số bài toán con** và chi phí kết hợp. Do đó chứng minh “có giảm kích thước” mới đủ cho một phần của lập luận, không tự chứng minh thời gian O(log n).

Khuôn suy nghĩ đúng là: **đặc tả miền đầu vào → base case → thước đo tiến độ → phép chia → chứng minh giảm nghiêm ngặt → bước kết hợp → chứng minh bằng quy nạp → kiểm thử**.

## 2. Chọn một thước đo không âm để chứng minh tiến độ

Giả sử hàm làm việc trên một đoạn mảng **[lo, hi)**, gồm những vị trí i thỏa lo ≤ i < hi. Ta yêu cầu **0 ≤ lo ≤ hi ≤ a.length**, đặt:

~~~text
m = hi - lo
~~~

Vì các biên hợp lệ, m là số nguyên **không âm**. Thước đo m gọi là *variant* hoặc *ranking function* khi dùng để chứng minh dừng.

Để chứng minh quá trình đệ quy hữu hạn, mỗi lời gọi trên bài toán chưa chạm base case phải chỉ gọi các bài toán con có thước đo **nhỏ hơn nghiêm ngặt** so với m của cha, và các phép tính tại mỗi nút cũng phải hữu hạn.

Cụ thể, nếu m ≥ 2, chọn:

~~~text
mid = lo + (hi - lo) / 2
trái  = [lo, mid)
phải  = [mid, hi)
~~~

Phép chia số nguyên làm tròn xuống. Ta có **lo < mid < hi** với m ≥ 2, nên:

- Độ dài trái = mid − lo = floor(m/2), thuộc [1, m−1].
- Độ dài phải = hi − mid = ceil(m/2), thuộc [1, m−1].
- Hai đoạn không chồng lặp và hợp lại đúng đoạn cha.

Vì không tồn tại dãy giảm vô hạn của số nguyên không âm, mọi đường đi đệ quy cuối cùng phải tới một đoạn có m bằng 0 hoặc 1. Lập luận này gọi là **tính có thứ tự tốt (well-foundedness)** của thước đo đệ quy.

**Cần chú ý:** “trung bình kích thước giảm” không đủ cho chứng minh dừng. Ta phải biết **từng lời gọi đệ quy thực sự** giảm thước đo. Khi một thuật toán dùng nhiều thông số, có thể phải dùng thước đo phức hợp hoặc một cặp thứ tự từ điển, nhưng nguyên tắc vẫn là tiến độ nghiêm ngặt.

## 3. Base case phải bám sát đặc tả, không chỉ là một dòng if

Với đoạn [lo, hi), m = hi − lo có ba tình huống cần phân biệt:

| Trường hợp | Số phần tử | Ý nghĩa đối với từng bài toán |
| --- | ---: | --- |
| **m = 0** | 0 | Sắp xếp đoạn rỗng: đã xong; tính tổng: thường trả 0; lấy max: thường không có kết quả hợp lệ |
| **m = 1** | 1 | Sắp xếp: đã xong; tổng: trả phần tử; max: trả chính phần tử đó |
| **m ≥ 2** | Ít nhất 2 | Có thể chia thành hai đoạn con không rỗng và đều nhỏ hơn đoạn cha |

Vì vậy base case **không giống nhau cho mọi bài toán**:

- Với merge sort, đoạn rỗng và đoạn một phần tử đều đã sắp xếp: dùng **if (m <= 1) return**.
- Với tổng đoạn, 0 là phần tử đơn vị của phép cộng, nên trường hợp rỗng có thể trả 0 nếu đặc tả cho phép.
- Với giá trị lớn nhất của đoạn, không thể trả 0 cho mảng rỗng: chẳng hạn [-5, -2] có max = -2, không phải 0. Cần từ chối mảng rỗng hoặc định nghĩa một kiểu kết quả đặc biệt.
- Với hàm đệ quy tìm max trong ví dụ Java, hàm công khai **chặn n = 0** bằng IllegalArgumentException; do đó hàm nội bộ chỉ nhận m ≥ 1 và base case hợp lệ là **m = 1**.

Điều kiện cơ sở còn phải **trả về đúng kiểu và đúng giá trị**, không chỉ tránh lỗi stack. Dừng sớm bằng một giá trị sai vẫn làm thuật toán sai.

## 4. Quy tắc chia đoạn nửa mở không bỏ sót, không xử lý hai lần

Khi dùng [lo, hi), các điểm chia phải tuân theo một quy ước nhất quán:

~~~text
solve(lo, hi):
    m = hi - lo
    nếu m <= 1:
        trả kết quả cơ sở phù hợp
    mid = lo + m / 2
    leftResult  = solve(lo, mid)
    rightResult = solve(mid, hi)
    trả combine(leftResult, rightResult)
~~~

Đoạn trái gồm lo..mid−1, đoạn phải gồm mid..hi−1. Hai đoạn **kề nhau, không giao nhau** và phủ đủ m phần tử của đoạn cha.

Công thức mid = lo + (hi − lo)/2 còn tránh tính tổng lo + hi quá lớn trong những tình huống chỉ số có giới hạn kiểu int. Trong Java, các chỉ số hợp lệ của mảng không âm và hi ≥ lo, nên phép trừ hi − lo có ý nghĩa trực tiếp.

**Ví dụ m = 5:** [0, 5) chia thành [0, 2) có 2 phần tử và [2, 5) có 3 phần tử; tiếp tục [0, 2) thành [0, 1), [1, 2), còn [2, 5) thành [2, 3), [3, 5). Nhánh [3, 5) chia thành [3, 4), [4, 5). Mọi lá đều có một phần tử, và mỗi vị trí 0..4 thuộc đúng một lá.

## 5. Cây lời gọi và bằng chứng kích thước giảm

Với năm phần tử, cây phân chia có thể biểu diễn:

~~~text
[0, 5)  m=5
├── [0, 2)  m=2
│   ├── [0, 1)  m=1  -> base
│   └── [1, 2)  m=1  -> base
└── [2, 5)  m=3
    ├── [2, 3)  m=1  -> base
    └── [3, 5)  m=2
        ├── [3, 4)  m=1  -> base
        └── [4, 5)  m=1  -> base
~~~

Ở từng cạnh cha → con, giá trị m giảm: từ 5 xuống 2 hoặc 3; từ 3 xuống 1 hoặc 2; từ 2 xuống 1. Không có con nào nhận lại đoạn bằng kích thước cha.

Ta cần chứng minh điều này **với mọi m ≥ 2**, không chỉ m = 5. Đó là lý do công thức floor(m/2) và ceil(m/2) quan trọng hơn một hình vẽ cụ thể.

Dù hai lời gọi con đều được thực hiện, chương trình thực thi chúng lần lượt; trên một stack tại một thời điểm chỉ tồn tại **một chuỗi tổ tiên**. Điều này giải thích vì sao bộ nhớ call stack thường tỉ lệ với **độ sâu cây**, không phải tổng số nút.

## 6. Merge sort: base case và bước kết hợp

Merge sort chia đoạn [lo, hi) thành hai nửa, sắp xếp mỗi nửa rồi **trộn** hai nửa đã có thứ tự thành một đoạn có thứ tự.

**Hợp đồng:** với mảng int bất kỳ không null, kết quả cuối cùng nằm ngay trong mảng đầu vào, được sắp xếp không giảm và bảo toàn số lần xuất hiện của từng giá trị. Đoạn rỗng và đoạn một phần tử đã thỏa hợp đồng.

**Cấu trúc:**

1. Nếu hi − lo ≤ 1, return.
2. Tính mid nằm trong đoạn và bảo đảm **lo < mid < hi**.
3. Sắp xếp [lo, mid) và [mid, hi) bằng đệ quy.
4. Trộn hai đoạn đã sắp vào buffer, sao chép kết quả về [lo, hi).

Bất biến khi trộn: các phần tử đã ghi trong buffer từ lo tới write−1 là những phần tử nhỏ nhất đã lấy ra từ hai nửa theo thứ tự không giảm; hai con trỏ left và right chỉ tiến về phía trước. Khi một nửa hết, phần còn lại của nửa kia vốn đã được sắp xếp nên chỉ cần chép tiếp.

Trong đoạn mã, khi hai giá trị bằng nhau, phép so sánh **a[left] <= a[right]** ưu tiên phần tử của nửa trái. Nếu mở rộng mẫu này sang bản ghi có khóa và giữ nguyên thao tác sao chép bản ghi, đó là nguyên tắc giúp **merge ổn định**. Với int thuần túy, hai giá trị bằng nhau không mang danh tính riêng để quan sát tính ổn định.

## 7. Tìm maximum bằng chia để trị: cùng phép chia nhưng khác base case

Bài toán tìm max minh họa rằng cách chia có thể giống merge sort, còn đặc tả và trường hợp cơ sở khác hẳn.

- **Tiền điều kiện:** mảng khác null và không rỗng.
- **Base case:** m = 1, trả a[lo].
- **Bước chia:** với m ≥ 2, chia [lo, hi) thành hai đoạn con không rỗng.
- **Bước kết hợp:** trả Math.max(leftMax, rightMax).
- **Tác động phụ:** không thay đổi mảng.

Với a = [7, −2, 7, 3, 0], max của nửa trái là 7, max của nửa phải cũng là 7, nên kết quả là 7. Đối với đoạn rỗng, không có phần tử làm chứng cho giá trị lớn nhất, vì vậy API minh họa **ném IllegalArgumentException** thay vì tự giả định max = 0.

Điều đáng học không nằm ở việc “thêm một base case”, mà là **chọn base case phù hợp với phép kết hợp**. Tổng có giá trị đơn vị 0 cho đoạn rỗng; max trên các số nguyên không có giá trị đơn vị hữu hạn trong kiểu int nếu muốn mọi đầu vào hợp lệ và không dùng một kết quả đặc biệt.

## 8. Java 17+: hai ví dụ có thể chạy độc lập

Chương trình sau bao gồm **mergeSort** và **maxDivideConquer**, cùng một chuẩn đoạn nửa mở, nhưng có base case khác nhau. Các phương thức công khai bảo vệ đầu vào null; max còn bảo vệ mảng rỗng. Merge sort cấp một buffer chung với kích thước n rồi tái sử dụng trong tất cả lời gọi, tránh cấp một mảng mới ở từng mức đệ quy.

Lưu đầy đủ đoạn mã sau thành **DivideConquerTermination.java**:

~~~java
import java.util.Arrays;

public final class DivideConquerTermination {
    private DivideConquerTermination() {
    }

    private static void requireArray(int[] a) {
        if (a == null) {
            throw new IllegalArgumentException("array must not be null");
        }
    }

    public static void mergeSort(int[] a) {
        requireArray(a);
        int[] temp = new int[a.length];
        sort(a, temp, 0, a.length);
    }

    private static void sort(int[] a, int[] temp, int lo, int hi) {
        int length = hi - lo;
        if (length <= 1) {
            return;
        }

        int mid = lo + (hi - lo) / 2;
        sort(a, temp, lo, mid);
        sort(a, temp, mid, hi);
        merge(a, temp, lo, mid, hi);
    }

    private static void merge(int[] a, int[] temp,
                              int lo, int mid, int hi) {
        int left = lo;
        int right = mid;
        int write = lo;

        while (left < mid && right < hi) {
            if (a[left] <= a[right]) {
                temp[write++] = a[left++];
            } else {
                temp[write++] = a[right++];
            }
        }
        while (left < mid) {
            temp[write++] = a[left++];
        }
        while (right < hi) {
            temp[write++] = a[right++];
        }
        System.arraycopy(temp, lo, a, lo, hi - lo);
    }

    public static int maxDivideConquer(int[] a) {
        requireArray(a);
        if (a.length == 0) {
            throw new IllegalArgumentException("maximum of empty array");
        }
        return max(a, 0, a.length);
    }

    private static int max(int[] a, int lo, int hi) {
        int length = hi - lo;
        if (length == 1) {
            return a[lo];
        }

        int mid = lo + (hi - lo) / 2;
        int leftMax = max(a, lo, mid);
        int rightMax = max(a, mid, hi);
        return Math.max(leftMax, rightMax);
    }

    private static void checkOne(int[] original) {
        int[] expected = original.clone();
        Arrays.sort(expected);
        int[] actual = original.clone();
        mergeSort(actual);
        if (!Arrays.equals(expected, actual)) {
            throw new AssertionError(
                "Sort mismatch: " + Arrays.toString(original)
            );
        }

        if (original.length > 0) {
            int expectedMax = original[0];
            for (int value : original) {
                expectedMax = Math.max(expectedMax, value);
            }
            if (maxDivideConquer(original) != expectedMax) {
                throw new AssertionError(
                    "Max mismatch: " + Arrays.toString(original)
                );
            }
        }
    }

    private static void verifySmallArrays() {
        int[] alphabet = {-2, 0, 2};
        int checked = 0;

        for (int length = 0; length <= 6; length++) {
            int combinations = 1;
            for (int i = 0; i < length; i++) {
                combinations *= alphabet.length;
            }

            for (int code = 0; code < combinations; code++) {
                int[] values = new int[length];
                int rest = code;
                for (int i = 0; i < length; i++) {
                    values[i] = alphabet[rest % alphabet.length];
                    rest /= alphabet.length;
                }
                checkOne(values);
                checked++;
            }
        }

        checkOne(new int[] {
            Integer.MAX_VALUE, Integer.MIN_VALUE, 0,
            Integer.MAX_VALUE
        });
        checkOne(new int[] {8, 7, 6, 5, 4, 3, 2, 1});
        checkOne(new int[] {1, 2, 3, 4, 5, 6, 7, 8});

        System.out.println("Verified " + checked + " generated arrays: PASS");
        System.out.println("Additional edge cases: PASS");
    }

    public static void main(String[] args) {
        int[] numbers = {7, -2, 7, 3, 0};
        System.out.println("max = " + maxDivideConquer(numbers));
        mergeSort(numbers);
        System.out.println("sorted = " + Arrays.toString(numbers));

        int[] empty = {};
        mergeSort(empty);
        System.out.println("empty sorted = " + Arrays.toString(empty));

        try {
            maxDivideConquer(empty);
            throw new AssertionError("Empty max should be rejected");
        } catch (IllegalArgumentException expected) {
            System.out.println("empty max rejected = true");
        }

        System.out.println(
            "single max = " + maxDivideConquer(new int[] {-8})
        );
        verifySmallArrays();
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~bash
javac DivideConquerTermination.java
java DivideConquerTermination
~~~

Đầu ra chính xác của chương trình:

~~~text
max = 7
sorted = [-2, 0, 3, 7, 7]
empty sorted = []
empty max rejected = true
single max = -8
Verified 1093 generated arrays: PASS
Additional edge cases: PASS
~~~

Dòng **Verified 1093 generated arrays: PASS** được tạo bởi bộ kiểm thử sinh mọi dãy độ dài từ 0 tới 6 trên tập giá trị {-2, 0, 2}. Số dãy được thử là:

~~~text
3^0 + 3^1 + 3^2 + 3^3 + 3^4 + 3^5 + 3^6
= 1 + 3 + 9 + 27 + 81 + 243 + 729
= 1093.
~~~

Ở mỗi dãy, merge sort được đối chiếu với Arrays.sort trên bản sao; khi dãy không rỗng, max chia để trị được đối chiếu với phép tìm max tuyến tính. Sau đó chương trình còn thử các mảng tăng dần, giảm dần và chứa Integer.MIN_VALUE/Integer.MAX_VALUE. Kết quả PASS thể hiện phạm vi kiểm thử cụ thể, **không thay thế chứng minh đúng đắn cho mọi mảng**.

## 9. Chứng minh thuật toán dừng bằng thước đo m

Với merge sort, bất biến miền đầu vào là 0 ≤ lo ≤ hi ≤ n. Thước đo **m = hi − lo** là số nguyên không âm.

- **m = 0 hoặc m = 1:** chương trình trả ngay, không gọi đệ quy.
- **m ≥ 2:** mid = lo + floor(m/2), hai lời gọi có kích thước floor(m/2) và ceil(m/2), đều thuộc khoảng [1, m−1].
- Lời gọi thực hiện một số hữu hạn thao tác để chia, gọi con và trộn; hai vòng while của merge đều tăng con trỏ hoặc write trong phạm vi hữu hạn.

Do mỗi đường đi đệ quy mang một dãy m giảm nghiêm ngặt tới 1, các lời gọi kết thúc. Không có chu trình nào có thể trở lại cùng đoạn cha.

Với maxDivideConquer, phương thức công khai chỉ chuyển vào hàm nội bộ khi n ≥ 1. Do đó **m = 1** là base case đạt được và đủ; khi m ≥ 2, hai con đều có m nhỏ hơn và ít nhất là 1. Toàn bộ đệ quy dừng.

**Chứng minh dừng chỉ là một phần:** vẫn cần chứng minh các đoạn con phủ đúng dữ liệu, phép kết hợp đúng, và mảng/ràng buộc đầu vào được xử lý theo đặc tả.

## 10. Chứng minh kết quả đúng bằng quy nạp theo kích thước

**Merge sort:** giả sử mọi đoạn ngắn hơn m đều được sắp xếp đúng và giữ nguyên đa tập phần tử.

- Nếu m ≤ 1 thì đoạn đã không giảm và đa tập được giữ nguyên.
- Nếu m ≥ 2, hai đoạn con đều ngắn hơn m nên theo giả thiết quy nạp chúng được sắp xếp và bảo toàn dữ liệu.
- Thao tác merge luôn chọn phần tử nhỏ hơn (hoặc phần tử nửa trái khi bằng nhau) trong hai phần tử đầu chưa lấy, do đó mảng kết quả không giảm; mỗi phần tử của hai nửa được lấy đúng một lần. Kết quả của đoạn cha vừa có thứ tự vừa bảo toàn đa tập.

**Max chia để trị:** với m = 1, kết quả a[lo] chính là max của đoạn. Với m ≥ 2, max của hợp hai đoạn rời nhau bằng **max(max của nửa trái, max của nửa phải)**; nhờ giả thiết quy nạp, hai lời gọi con trả đúng max của từng nửa, nên Math.max kết hợp cho kết quả đúng của toàn đoạn.

Ở cả hai bài toán, phép chia thỏa điều kiện giảm kích thước đóng **hai vai trò**: bảo đảm đệ quy dừng và cho phép dùng giả thiết quy nạp đối với từng bài toán con.

## 11. Độ phức tạp: giảm kích thước không đồng nghĩa O(log n) thời gian

Trong mỗi mức của merge sort, tổng số phần tử tham gia các lượt merge là O(n). Vì khoảng được chia gần nửa và có O(log n) mức, ta có:

~~~text
T(n) = T(floor(n/2)) + T(ceil(n/2)) + O(n), n >= 2
T(0) = O(1), T(1) = O(1)
=> T(n) = O(n log n) cho n >= 2.
~~~

- **Thời gian merge sort:** O(n log n) khi n ≥ 2.
- **Bộ nhớ phụ merge sort:** O(n) cho buffer; thêm O(log n) call stack với phép chia cân đối, nên tổng vẫn là O(n).
- **Thời gian tìm max chia để trị:** O(n), vì mỗi phần tử là một lá và phép kết hợp max trên từng nút tốn O(1).
- **Bộ nhớ phụ tìm max:** O(log n) stack với chia gần đôi, không cần buffer cỡ n.

Nếu một thuật toán chỉ gọi **một** nhánh cỡ n/2 ở mỗi bước và mỗi bước dùng O(1) công việc, thời gian có thể O(log n) như tìm nhị phân. Nếu gọi **hai** nhánh cỡ n/2 với công việc kết hợp O(n), thời gian là O(n log n) như merge sort. Nếu giảm mỗi lần từ n xuống n−1 rồi làm O(n) công việc, thời gian có thể là O(n²), dù vẫn dừng.

Khi mô tả độ phức tạp phải phân biệt rõ **độ sâu đệ quy**, **tổng số nút** và **công việc mỗi nút**. Một cây chia đôi không biến mọi thuật toán trên cây đó thành thuật toán O(log n).

## 12. Các lỗi phổ biến làm đệ quy không dừng hoặc cho kết quả sai

| Lỗi | Ví dụ / nguyên nhân | Sửa bằng lập luận gì? |
| --- | --- | --- |
| Base case chỉ xét m = 1 | Gọi sort trên đoạn rỗng có m = 0, mid = lo; một nhánh lại là đoạn rỗng | Với sort, dùng m ≤ 1 |
| Chia đoạn nhưng con không nhỏ hơn cha | Với m = 2 và mid = lo+1, gọi lại [lo, mid+1) tức chính [lo, hi) | Chứng minh m(con) < m(cha) cho mọi nhánh |
| Trộn quy ước khoảng | Một hàm dùng [lo, hi), hàm con dùng [lo, hi] | Ghi rõ biên bao gồm và biên loại trừ |
| Bỏ sót hoặc xử lý trùng vị trí | Dùng [lo, mid) và [mid+1, hi) làm mất phần tử tại mid | Chứng minh hai đoạn con rời nhau và hợp lại đúng đoạn cha |
| Base case sai giá trị | Trả 0 cho max trên đoạn rỗng hoặc mọi đoạn đơn | Lấy điều kiện cơ sở từ đặc tả và phép kết hợp |
| Không có giới hạn biên | Truy cập a[mid] khi m = 0 | Kiểm tra m và chỉ số trước khi truy cập |
| Chỉ kiểm tra một nhánh giảm | Một lời gọi nhỏ hơn nhưng lời gọi kia nhận lại đoạn gốc | Xét **tất cả** lời gọi con |
| Thuật toán dừng nhưng quá sâu | Giảm n thành n−1 tới hàng triệu lần | Ước lượng stack, cân bằng chia hoặc dùng vòng lặp |
| Sai bước kết hợp | Hai nửa đã sort nhưng nối thẳng thay vì merge | Chứng minh hậu điều kiện của combine |
| Tràn chỉ số | Tính mid từ lo+hi khi giới hạn kiểu số nguyên | Dùng lo + (hi−lo)/2 |

**Phản ví dụ nhỏ rất có giá trị:** với m = 2, nếu chia sai thành [lo, mid+1) và [mid, hi), nhánh trái dài 2 bằng chính cha. Chỉ một trường hợp hai phần tử đã đủ lộ lỗi dừng; không cần mảng rất lớn.

## 13. Áp dụng sang tìm kiếm nhị phân và Quicksort

**Tìm kiếm nhị phân:** sau khi kiểm tra phần tử giữa, ta chỉ tiếp tục xét một nửa không thể loại bỏ. Tùy biến thể, khoảng có thể là [lo, mid) hoặc [mid+1, hi); nhưng khoảng mới phải nhỏ hơn khoảng cũ. Base case và đầu ra khác nhau giữa “tìm một phần tử bằng target” và “tìm vị trí cận dưới”. Không thể chép nguyên các phép cập nhật mà không xác định bất biến.

**Quicksort với Lomuto:** partition đưa pivot tới một chỉ số cố định p, sau đó xử lý hai đoạn không chứa p: [lo, p−1] và [p+1, hi] nếu dùng khoảng đóng. Với n ≥ 2, hai đoạn có ít hơn n phần tử.

**Quicksort với Hoare:** partition thường trả về **biên j**, không phải vị trí cuối của pivot. Phải dùng hai đoạn phù hợp với quy ước Hoare, chẳng hạn [lo, j] và [j+1, hi] khi dùng khoảng đóng, đồng thời bảo đảm partition không trả về một biên làm nhánh nào giữ nguyên cả đoạn. Không được máy móc thay Hoare bằng quy tắc đệ quy Lomuto.

**Lũy thừa nhanh:** nếu số mũ không âm e, base case e = 0 trả 1, còn bước đệ quy trên floor(e/2) làm giảm số mũ với mọi e ≥ 1. Chi phí kết hợp cần xử lý e chẵn/lẻ. Đây là ví dụ chia để trị trên **một số nguyên**, không phải đoạn mảng, nhưng thước đo giảm là e vẫn chứng minh được tính dừng.

**Quy tắc chung:** mỗi biến thể phải có **thước đo tiến độ và điều kiện cơ sở tương thích** với cấu trúc bài toán của chính nó.

## 14. Bộ trường hợp biên nên kiểm thử

| Đầu vào / tình huống | Merge sort | Tìm max chia để trị |
| --- | --- | --- |
| Mảng rỗng [] | Trả mảng rỗng | IllegalArgumentException |
| Một phần tử [−8] | Giữ [−8] | −8 |
| Hai phần tử [3, 1] | [1, 3] | 3 |
| Độ dài lẻ [7, −2, 7, 3, 0] | [−2, 0, 3, 7, 7] | 7 |
| Giá trị bằng nhau [2, 2, 2] | Giữ ba phần tử 2 | 2 |
| Đã tăng [1, 2, 3] | Giữ thứ tự | 3 |
| Đã giảm [3, 2, 1] | [1, 2, 3] | 3 |
| Có số âm [−5, −2, −7] | [−7, −5, −2] | −2 |
| Biên int [MIN_VALUE, MAX_VALUE] | [MIN_VALUE, MAX_VALUE] | MAX_VALUE |
| null | IllegalArgumentException | IllegalArgumentException |

Kiểm thử cần quan sát **cả kết quả lẫn tình trạng dừng**. Dù lời gọi nhỏ có thể khiến lỗi stack xảy ra ngay, với một số lỗi giảm kích thước quá chậm, bộ kiểm thử nhỏ vẫn qua. Vì vậy cần bổ sung chứng minh kích thước giảm và kiểm tra ranh giới theo công thức, không chỉ chạy vài mảng.

Khi gặp StackOverflowError, đừng mặc nhiên tăng giới hạn stack hoặc thêm một if tùy ý. Hãy hỏi: thước đo có giảm theo **mọi nhánh** không; base case có thể đạt đến không; chương trình có vô tình gọi lại đúng đoạn ban đầu không?

## 15. Checklist thiết kế và bài tập vận dụng

Trước khi viết một hàm chia để trị:

1. **Chốt hợp đồng:** dữ liệu nào hợp lệ, kết quả là gì, xử lý rỗng và null thế nào?
2. **Định nghĩa bài toán con:** ví dụ solve(a, lo, hi) tác động trên [lo, hi), không phải một khoảng chưa được mô tả.
3. **Chọn thước đo tiến độ:** độ dài hi−lo, số đỉnh chưa xử lý, kích thước cây, số mũ hoặc biến không âm tương ứng.
4. **Viết điều kiện cơ sở:** xác định chính xác miền nhỏ nhất và giá trị trả về đúng đặc tả.
5. **Chứng minh chia:** mỗi con thuộc miền hợp lệ; không mất phần tử hay tính phần tử hai lần nếu bài toán đòi phân hoạch.
6. **Chứng minh giảm nghiêm ngặt:** với từng con, thước đo phải nhỏ hơn cha; đừng chỉ xét ví dụ chung chung.
7. **Chứng minh combine:** nếu mọi con đúng thì kết quả cha đúng.
8. **Phân tích chi phí:** số nhánh, kích thước từng nhánh, công việc kết hợp, độ sâu và bộ nhớ tạm.
9. **Kiểm thử:** rỗng, đơn, hai phần tử, độ dài chẵn/lẻ, số âm, trùng, biên kiểu và các trường hợp tiền điều kiện sai.

**Bài tập 1 — Tổng đoạn:** hiện thực sum(a, lo, hi) trên [lo, hi). Đặt base case m = 0 trả 0 và m = 1 trả a[lo]; chia tại mid khi m ≥ 2, lấy tổng hai kết quả. Chứng minh tổng các đoạn con bằng tổng đoạn cha và thước đo giảm.

**Bài tập 2 — Sửa lỗi đệ quy:** giả sử hàm sort trên [lo, hi) khi m ≥ 2 gọi sort(lo, mid+1) và sort(mid, hi). Với m = 2, hãy lập cây lời gọi và chứng minh nhánh nào có thể không giảm kích thước. Sửa bằng hai đoạn [lo, mid), [mid, hi).

**Bài tập 3 — Đếm độ sâu:** với mảng n = 17, ghi độ dài lớn nhất của từng mức đệ quy khi chia gần đôi cho tới m = 1. Dựa trên dãy này, giải thích vì sao độ sâu tăng theo log n dù tổng số lời gọi có thể tăng theo n.

**Câu hỏi tổng kết:** Khi nào base case m ≤ 1 là đúng nhưng base case m = 1 là không đủ? Tại sao việc chia thành hai phần luôn **có tên gọi “chia đôi”** vẫn không bảo đảm hai con nhỏ hơn cha? Vì sao chứng minh dừng không đồng nghĩa với chứng minh hiệu năng tốt?

**Kết luận:** trong chia để trị, một lời gọi đệ quy chỉ hợp lệ khi có lý do rõ ràng để tin rằng nó sẽ tiến gần trường hợp cơ sở. **Điều kiện cơ sở đúng + thước đo giảm nghiêm ngặt trên mọi nhánh + phép kết hợp đúng** là nền tảng để thiết kế thuật toán hữu hạn, kiểm chứng được và có thể phân tích chi phí.
