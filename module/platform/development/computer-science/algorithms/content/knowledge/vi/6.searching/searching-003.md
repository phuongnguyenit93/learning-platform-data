# Tìm kiếm nhị phân với bất biến khoảng

Tìm kiếm nhị phân (binary search) là cách liên tục thu hẹp miền ứng viên nhờ **thứ tự đã biết**. Khi dữ liệu được sắp xếp, một phép so sánh tại vị trí giữa có thể loại bỏ nguyên một nửa miền cần xét. Tuy nhiên, phần khó không phải cú pháp vòng lặp mà là chứng minh **mỗi lần loại bỏ đều an toàn**: đáp án cần tìm vẫn được giữ trong khoảng còn lại.

Bài này dùng một mô hình khoảng nhất quán là **nửa mở [lo, hi)**: bao gồm vị trí lo nhưng không bao gồm hi. Ta xây dựng bất biến rõ ràng, lần theo từng vòng lặp, chứng minh đúng và dừng, xử lý mảng rỗng, phần tử trùng và trường hợp không tìm thấy, rồi hiện thực bằng Java 17+.

## 1. Điều kiện để dùng tìm kiếm nhị phân

Giả sử có mảng số nguyên a dài n, được sắp xếp **không giảm**: a[0] ≤ a[1] ≤ ... ≤ a[n−1]. Dữ liệu có thể có giá trị bằng nhau. Ví dụ:

~~~text
Chỉ số:  0  1  2  3  4  5
Giá trị: 1  2  2  2  5  9
~~~

Ta muốn tìm target = 2. Mọi giá trị nhỏ hơn 2 nằm trước các giá trị bằng hoặc lớn hơn 2. Vì vậy có thể bỏ nguyên một đoạn dựa trên so sánh với giá trị ở giữa.

**Tiền điều kiện bắt buộc:** mảng đã được sắp xếp không giảm theo đúng phép so sánh được dùng. Các phương thức Java trong bài kiểm tra đầu vào khác null, nhưng **không quét lại để xác minh thứ tự**. Nếu phải kiểm tra thứ tự mỗi lần bằng một lượt quét O(n), toàn bộ lời gọi sẽ không còn thời gian O(log n). Khi mảng chưa sắp xếp, kết quả tìm nhị phân không được bảo đảm; hãy sắp xếp trước nếu hợp đồng ứng dụng cho phép thay đổi thứ tự, hoặc sử dụng phương pháp tìm khác.

Mỗi biến thể tìm kiếm nhị phân phải trả lời chính xác câu hỏi của nó: tìm **một** vị trí có giá trị target, tìm **vị trí đầu tiên**, tìm **vị trí chèn**, hay đếm số lần xuất hiện? Việc xác định đầu ra trước khi viết điều kiện so sánh là yếu tố quyết định.

## 2. Tìm cận dưới: dạng tổng quát nhất khi có phần tử trùng

Định nghĩa **lowerBound(a, target)** là vị trí nhỏ nhất i trong phạm vi **0 đến n** sao cho:

- Nếu i < n thì a[i] ≥ target.
- Mọi chỉ số j < i đều thỏa a[j] < target.
- Nếu mọi phần tử đều nhỏ hơn target thì trả về n, nghĩa là vị trí chèn ở cuối.

Không cần có phần tử nào bằng target. Ví dụ với [1, 2, 2, 2, 5, 9]:

| target | lowerBound | Ý nghĩa |
| ---: | ---: | --- |
| 0 | 0 | Chèn trước 1 |
| 2 | 1 | Giá trị đầu tiên không nhỏ hơn 2 |
| 3 | 4 | Chèn trước 5, dù 3 không có trong mảng |
| 9 | 5 | Giá trị 9 ở chỉ số 5 |
| 10 | 6 | Chèn cuối mảng |

Nếu mảng rỗng, n = 0 và lowerBound luôn trả về 0. Giá trị trả về là **vị trí biên** trong [0, n], không phải lúc nào cũng là chỉ số có thể truy cập trực tiếp: chỉ số n là ngoài mảng.

## 3. Bất biến khoảng nửa mở [lo, hi)

Đây là trung tâm của thuật toán. Khởi tạo **lo = 0**, **hi = n**, nghĩa là khoảng chưa phân loại là [lo, hi).

Ở **đầu mỗi vòng lặp**, ta duy trì đồng thời ba điều kiện:

1. **0 ≤ lo ≤ hi ≤ n**.
2. Mọi vị trí i < lo đã biết có **a[i] < target**.
3. Mọi vị trí i ≥ hi đã biết có **a[i] ≥ target**.

Như vậy đáp án lowerBound luôn nằm trong đoạn biên **[lo, hi]**; chỉ các phần tử trong [lo, hi) còn chưa được phân loại. Khi khoảng chưa phân loại rỗng, **lo = hi** và chính biên đó là đáp án.

Trạng thái khởi tạo đúng vì:

- Không có vị trí nào trước lo = 0.
- Không có vị trí nào từ hi = n tới n−1.
- Mọi phần tử của mảng ban đầu nằm trong [0, n).

Mọi khẳng định về phần đã loại bỏ đều đúng một cách hiển nhiên tại thời điểm đầu, kể cả với mảng rỗng.

## 4. Cách cập nhật hai biên

Trong khi **lo < hi**, chọn:

~~~text
mid = lo + (hi - lo) / 2
~~~

Ở đây phép chia số nguyên làm tròn xuống. Bởi lo < hi, ta có **lo ≤ mid < hi**; vì thế truy cập a[mid] an toàn.

Nếu **a[mid] < target**, nhờ tính sắp xếp, mọi phần tử từ lo đến mid đều nhỏ hơn target. Không phần tử nào trong đoạn đó có thể là vị trí lowerBound. Vì vậy:

~~~text
lo = mid + 1
~~~

Nếu **a[mid] ≥ target**, toàn bộ các phần tử từ mid về phía phải đều không nhỏ hơn target. Vị trí biên có thể là mid hoặc nằm bên trái mid. Vì vậy:

~~~text
hi = mid
~~~

**Vì sao không dùng hi = mid - 1?** Trong cách viết nửa mở này, mid vẫn có thể chính là đáp án cận dưới; loại nó sẽ làm sai khi target xuất hiện lần đầu tại mid. Việc dùng hi = mid đi kèm vòng lặp **while (lo < hi)**, nên không bị lặp vô hạn: mid luôn nhỏ hơn hi trong vòng lặp, do đó độ rộng hi−lo giảm.

**Vì sao viết mid = lo + (hi−lo)/2?** Cách tính trực tiếp (lo+hi)/2 có thể gây tràn số nguyên ở một số ngôn ngữ hoặc với hai biên lớn. Dạng hiệu số an toàn với biên chỉ số không âm của mảng Java.

## 5. Lần theo dữ liệu cụ thể và giữ bất biến

Với a = [1, 2, 2, 2, 5, 9], target = 2:

| Lần | lo trước | hi trước | mid | a[mid] | Quyết định |
| --- | ---: | ---: | ---: | ---: | --- |
| 1 | 0 | 6 | 3 | 2 | a[3] ≥ 2 nên hi = 3 |
| 2 | 0 | 3 | 1 | 2 | a[1] ≥ 2 nên hi = 1 |
| 3 | 0 | 1 | 0 | 1 | a[0] < 2 nên lo = 1 |
| Kết thúc | 1 | 1 | — | — | lowerBound = 1 |

Nếu chỉ tìm *một* phần tử bằng 2 rồi dừng ngay ở mid = 3, kết quả 3 là một vị trí hợp lệ nhưng **không phải lần xuất hiện đầu tiên**. Thuật toán cận dưới tiếp tục thu hẹp về bên trái để bảo đảm kết quả là 1.

Với target = 3, các bước là:

~~~text
[lo, hi) = [0, 6), mid = 3, a[3] = 2 < 3  -> lo = 4
[lo, hi) = [4, 6), mid = 5, a[5] = 9 >= 3 -> hi = 5
[lo, hi) = [4, 5), mid = 4, a[4] = 5 >= 3 -> hi = 4
Dừng tại lo = hi = 4: vị trí chèn 3, không có số 3 trong mảng.
~~~

Điểm quan trọng là bất biến phân định điều ta **đã chứng minh về phần bị loại**, không chỉ ghi lại hai con số lo và hi.

## 6. Chứng minh tính đúng đắn và tính dừng

**Khởi tạo:** các điều kiện ở mục 3 đúng với [lo, hi) = [0, n).

**Duy trì:** giả sử các điều kiện đúng ở đầu một vòng lặp.

- Nếu a[mid] < target, do mảng không giảm, mọi phần tử có chỉ số ≤ mid đều < target. Gán lo = mid + 1 làm rộng đoạn đã xác nhận nhỏ hơn target, không phá điều kiện của phần bên phải.
- Nếu a[mid] ≥ target, do mảng không giảm, mọi phần tử có chỉ số ≥ mid đều ≥ target. Gán hi = mid làm rộng đoạn đã xác nhận không nhỏ hơn target, không phá điều kiện của phần bên trái.

Trong cả hai trường hợp, thứ tự **0 ≤ lo ≤ hi ≤ n** vẫn đúng. Do đó bất biến được bảo toàn.

**Tính dừng:** độ rộng **hi − lo** là số nguyên không âm. Mỗi vòng đều giảm nghiêm ngặt độ rộng vì hoặc lo tăng đến ít nhất mid + 1, hoặc hi giảm xuống mid < hi cũ. Không thể giảm mãi một số nguyên không âm, nên vòng lặp kết thúc.

**Tại thời điểm kết thúc**, lo = hi. Mọi chỉ số nhỏ hơn lo đều có giá trị < target; mọi chỉ số từ lo đến hết đều có giá trị ≥ target. Vì vậy lo là vị trí nhỏ nhất thỏa điều kiện cận dưới, hoặc n nếu không có phần tử thỏa.

Lập luận này không phụ thuộc vào target có xuất hiện hay không, số phần tử trùng hay độ dài của mảng. Đó là lý do mô hình bất biến có sức mạnh hơn việc thử một vài ví dụ.

## 7. Tìm cận trên và lần xuất hiện đầu tiên

**upperBound(a, target)** là vị trí nhỏ nhất i trong [0, n] sao cho a[i] **> target**; nếu không có phần tử lớn hơn thì trả về n.

Bất biến của upperBound tương tự, nhưng ranh giới đổi từ **< / ≥** sang **≤ / >**:

- Mọi i < lo đều có a[i] ≤ target.
- Mọi i ≥ hi đều có a[i] > target.
- Khoảng [lo, hi) chưa được phân loại.

Khi **a[mid] ≤ target** thì gán **lo = mid + 1**; ngược lại gán **hi = mid**. Trên a = [1, 2, 2, 2, 5, 9] và target = 2:

- lowerBound = 1 (đầu dải bằng 2).
- upperBound = 4 (vị trí ngay sau dải bằng 2).
- Số phần tử bằng 2 là **upperBound − lowerBound = 3**.
- Khoảng các vị trí có giá trị đúng bằng 2 là **[1, 4)**.

Muốn tìm **chỉ số xuất hiện đầu tiên của target**, hãy tính i = lowerBound(a, target), sau đó kiểm tra **i < n và a[i] == target**. Nếu đúng, trả về i; nếu không, trả về −1. Không được truy cập a[i] trước khi kiểm tra i < n, vì i có thể bằng n.

Nếu muốn **chỉ số xuất hiện cuối cùng**, khi upperBound > lowerBound thì nó bằng upperBound − 1; nếu không có phần tử nào bằng target thì trả về −1. Cách định nghĩa cận dưới và cận trên cũng hỗ trợ đếm, tìm vị trí chèn, và truy vấn khoảng trong dữ liệu đã sắp xếp.

## 8. Chương trình Java 17+ có thể chạy độc lập

Lưu nguyên mã dưới đây vào tệp **BinarySearchIntervals.java**. Đầu vào của các hàm phải là mảng int không giảm; chúng ném IllegalArgumentException khi mảng null. Chương trình không sửa mảng do người gọi cung cấp. Hàm **verifySmallArrays** sinh mảng từ bộ giá trị {-1, 0, 1}, sắp xếp từng mảng rồi đối chiếu kết quả nhị phân với cách duyệt tuyến tính; đây là kiểm thử phụ trợ, không nằm trong độ phức tạp của riêng các hàm tìm kiếm.

~~~java
import java.util.Arrays;

public final class BinarySearchIntervals {
    private BinarySearchIntervals() {
    }

    private static void requireArray(int[] values) {
        if (values == null) {
            throw new IllegalArgumentException("values must not be null");
        }
    }

    public static int lowerBound(int[] values, int target) {
        requireArray(values);
        int lo = 0;
        int hi = values.length;

        while (lo < hi) {
            int mid = lo + (hi - lo) / 2;
            if (values[mid] < target) {
                lo = mid + 1;
            } else {
                hi = mid;
            }
        }
        return lo;
    }

    public static int upperBound(int[] values, int target) {
        requireArray(values);
        int lo = 0;
        int hi = values.length;

        while (lo < hi) {
            int mid = lo + (hi - lo) / 2;
            if (values[mid] <= target) {
                lo = mid + 1;
            } else {
                hi = mid;
            }
        }
        return lo;
    }

    public static int firstIndex(int[] values, int target) {
        int index = lowerBound(values, target);
        if (index < values.length && values[index] == target) {
            return index;
        }
        return -1;
    }

    public static int count(int[] values, int target) {
        return upperBound(values, target) - lowerBound(values, target);
    }

    private static void verifySmallArrays() {
        int checked = 0;
        for (int length = 0; length <= 5; length++) {
            int combinations = 1;
            for (int i = 0; i < length; i++) {
                combinations *= 3;
            }

            for (int encoded = 0; encoded < combinations; encoded++) {
                int[] sample = new int[length];
                int remaining = encoded;
                for (int i = 0; i < length; i++) {
                    sample[i] = remaining % 3 - 1;
                    remaining /= 3;
                }
                Arrays.sort(sample);

                for (int target = -2; target <= 2; target++) {
                    int expectedLower = 0;
                    while (expectedLower < sample.length
                            && sample[expectedLower] < target) {
                        expectedLower++;
                    }

                    int expectedUpper = expectedLower;
                    while (expectedUpper < sample.length
                            && sample[expectedUpper] <= target) {
                        expectedUpper++;
                    }

                    int expectedFirst = expectedLower < expectedUpper
                            ? expectedLower : -1;

                    if (lowerBound(sample, target) != expectedLower
                            || upperBound(sample, target) != expectedUpper
                            || firstIndex(sample, target) != expectedFirst
                            || count(sample, target)
                                != expectedUpper - expectedLower) {
                        throw new AssertionError(
                            "Mismatch: " + Arrays.toString(sample)
                            + ", target=" + target
                        );
                    }
                    checked++;
                }
            }
        }
        System.out.println("Verified " + checked + " cases: PASS");
    }

    public static void main(String[] args) {
        int[] data = {1, 2, 2, 2, 5, 9};
        System.out.println("lowerBound(2) = " + lowerBound(data, 2));
        System.out.println("upperBound(2) = " + upperBound(data, 2));
        System.out.println("firstIndex(2) = " + firstIndex(data, 2));
        System.out.println("count(2) = " + count(data, 2));
        System.out.println("lowerBound(3) = " + lowerBound(data, 3));
        System.out.println("firstIndex(3) = " + firstIndex(data, 3));
        System.out.println("lowerBound(0) = " + lowerBound(data, 0));
        System.out.println("lowerBound(10) = " + lowerBound(data, 10));
        System.out.println("firstIndex(empty) = "
                + firstIndex(new int[0], 7));
        int[] extremes = {Integer.MIN_VALUE, Integer.MAX_VALUE};
        System.out.println("firstIndex(MAX) = "
                + firstIndex(extremes, Integer.MAX_VALUE));
        verifySmallArrays();
    }
}
~~~

Lệnh biên dịch và chạy tại thư mục chứa tệp:

~~~bash
javac BinarySearchIntervals.java
java BinarySearchIntervals
~~~

Kết quả chuẩn:

~~~text
lowerBound(2) = 1
upperBound(2) = 4
firstIndex(2) = 1
count(2) = 3
lowerBound(3) = 4
firstIndex(3) = -1
lowerBound(0) = 0
lowerBound(10) = 6
firstIndex(empty) = -1
firstIndex(MAX) = 1
Verified 1820 cases: PASS
~~~

Bộ tự kiểm tra sinh tất cả **1 + 3 + 9 + 27 + 81 + 243 = 364** cách chọn dãy độ dài 0 đến 5 từ ba giá trị, rồi sắp xếp từng dãy và thử 5 target từ −2 đến 2. Tổng cộng có **364 × 5 = 1.820** lượt đối chiếu. Có thể có những dãy sắp xếp trùng nhau do nhiều hoán vị ban đầu, nhưng điều đó không làm sai số lượt kiểm tra. Phép so sánh độc lập được thực hiện bằng cách duyệt tuyến tính, có thể phát hiện cả lỗi cận dưới, cận trên, kết quả −1 và số lần xuất hiện.

## 9. Các trường hợp biên quan trọng

| Tình huống | Dữ liệu | Kết quả cần có | Lỗi có thể phát hiện |
| --- | --- | --- | --- |
| Mảng rỗng | [], target = 2 | lowerBound = 0; firstIndex = −1 | Đọc a[0] hoặc xử lý vòng lặp sai |
| Mảng một phần tử, có target | [5], target = 5 | lowerBound = 0; upperBound = 1 | Sai biên khi chỉ có một ứng viên |
| Mảng một phần tử, thiếu target | [5], target = 4 | lowerBound = 0; firstIndex = −1 | Nhầm vị trí chèn là vị trí tìm thấy |
| Toàn phần tử trùng | [2, 2, 2], target = 2 | lowerBound = 0; upperBound = 3 | Dừng ở phần tử bằng bất kỳ |
| Target nhỏ nhất | [1, 2, 5], target = 0 | lowerBound = 0 | Thiếu biên đầu |
| Target lớn hơn tất cả | [1, 2, 5], target = 6 | lowerBound = 3 | Truy cập a[n] |
| Target nằm giữa hai giá trị | [1, 2, 5], target = 3 | lowerBound = 2; firstIndex = −1 | Không phân biệt tồn tại và vị trí chèn |
| Có số âm | [−5, −2, 0, 4], target = −2 | firstIndex = 1 | Giả định giá trị phải dương |
| Sát biên int | [MIN_VALUE, MAX_VALUE], target = MAX_VALUE | firstIndex = 1 | Tính mid hoặc so sánh sai |
| Mảng không sắp xếp | [5, 1, 3] | Ngoài tiền điều kiện | Không thể dùng kết quả để kết luận đúng/sai thuật toán |
| Mảng null | null | IllegalArgumentException | Thiếu hợp đồng đầu vào |

Đừng chỉ kiểm tra trường hợp có target. Nhánh trả về n và trường hợp mảng rỗng thường là nguồn lỗi vượt chỉ số. Với các giá trị đặc biệt, có thể dùng Integer.MIN_VALUE và Integer.MAX_VALUE trong Java để kiểm tra cách tính mid và so sánh.

## 10. Phân biệt hai quy ước khoảng để tránh lỗi

Một cách viết khác dùng khoảng **đóng [lo, hi]** và khởi tạo lo = 0, hi = n − 1. Với bài tìm **một** giá trị, vòng lặp thường là **while (lo <= hi)**, rồi khi a[mid] lớn hơn target gán hi = mid − 1. Quy ước này có thể đúng, nhưng bất biến và giá trị trả về phải được thiết kế riêng.

Bảng đối chiếu:

| Yếu tố | Nửa mở [lo, hi) của bài | Đóng [lo, hi] trong tìm kiếm vị trí bất kỳ |
| --- | --- | --- |
| Khởi tạo | lo = 0, hi = n | lo = 0, hi = n − 1 |
| Khi tiếp tục | lo < hi | lo <= hi |
| Nhánh loại nửa trái | lo = mid + 1 | lo = mid + 1 |
| Nhánh loại nửa phải | hi = mid | hi = mid − 1 |
| Điều kiện dừng | lo = hi | lo > hi |
| Đầu ra điển hình | Vị trí biên chèn/cận dưới | Một chỉ số có giá trị bằng target hoặc −1 |

**Không trộn các dòng trong bảng**. Ví dụ thay hi = mid bằng hi = mid − 1 nhưng vẫn áp dụng lập luận cận dưới sẽ loại mất mid, dù mid có thể là đáp án. Ngược lại, trong khoảng đóng mà cập nhật hi = mid và dùng vòng lặp lo <= hi, trạng thái lo = hi = mid có thể lặp mãi.

Dù lựa chọn quy ước nào, hãy viết bất biến và xác định nghĩa của từng biên trước khi chuyển giả mã sang chương trình.

## 11. Độ phức tạp và điều kiện để có O(log n)

Mỗi vòng lặp chỉ làm vài thao tác chỉ số và một phép so sánh với a[mid], đồng thời giảm kích thước miền chưa phân loại xuống khoảng một nửa. Vì vậy:

- **Thời gian:** O(log(n + 1)) cho mọi n ≥ 0, thường viết là **O(log n)** khi n ≥ 1.
- **Bộ nhớ phụ:** O(1), vì mã tìm kiếm lặp chỉ lưu vài biến số nguyên.
- **lowerBound, upperBound, firstIndex và count:** mỗi phương thức dùng nhiều nhất một số hằng định các lần tìm nhị phân, nên đều thuộc O(log(n + 1)).

Chi phí sẽ khác nếu phải **sắp xếp dữ liệu trước**: sắp xếp bằng một thuật toán O(n log n) rồi chỉ tìm một lần thường không có lợi so với quét tuyến tính O(n). Tìm nhị phân phát huy hiệu quả khi dữ liệu **đã có thứ tự** hoặc cần nhiều truy vấn trên cùng một bộ dữ liệu có thứ tự. Với danh sách liên kết không hỗ trợ truy cập theo chỉ số O(1), thao tác lấy phần tử giữa có thể tốn thêm thời gian; lập luận O(log n) ở đây giả định mảng truy cập ngẫu nhiên O(1).

**Tìm nhị phân trên đáp án (binary search on answer):** ý tưởng thu hẹp khoảng còn mở rộng sang các bài toán khác khi có một điều kiện **đơn điệu** theo ứng viên. Ví dụ, một mốc tài nguyên đủ lớn thì các mốc lớn hơn cũng đủ; khi có phép kiểm tra khả thi, ta có thể tìm mốc nhỏ nhất thỏa điều kiện. Lúc đó phải xác định lại bất biến và chi phí của hàm kiểm tra; không nhất thiết so sánh trực tiếp a[mid] như ví dụ mảng.

## 12. Quy trình tự kiểm tra khi tự viết tìm nhị phân

1. **Chốt đầu ra:** cần một vị trí bằng target, vị trí đầu tiên, cận trên hay vị trí chèn?
2. **Nêu tiền điều kiện:** dữ liệu có được sắp xếp theo đúng thứ tự so sánh không; có phần tử trùng không?
3. **Chọn một quy ước khoảng:** [lo, hi) hoặc [lo, hi]; ghi rõ đầu nào được bao gồm.
4. **Viết bất biến ở đầu vòng lặp:** các phần tử bên trái/bên phải đã có thuộc tính gì?
5. **Chứng minh từng nhánh loại bỏ:** từ tính đơn điệu, vì sao không thể có đáp án trong phần bị bỏ?
6. **Chứng minh giảm khoảng:** vòng lặp có thể rơi vào trạng thái lo = mid mà không thu hẹp nữa không?
7. **Chốt trạng thái khi dừng:** lo/hi đại diện cho chỉ số tìm được hay biên chèn? Có cần kiểm tra tồn tại?
8. **Kiểm thử tự động:** rỗng, một phần tử, trùng, không tìm thấy, đầu/cuối, biên int; đối chiếu với quét tuyến tính trên nhiều mảng nhỏ đã sắp xếp.

**Bài tập:** hãy cài đặt hàm lastIndex dựa trên upperBound và lowerBound, trả về −1 nếu target không tồn tại. Sau đó viết kiểm thử với [2, 2, 2], [1, 3, 5], mảng rỗng và một phần tử. Hãy giải thích bằng bất biến vì sao chỉ số upperBound − 1 phải được kiểm tra để tránh trả một vị trí không hợp lệ khi target không có trong mảng.

Điểm mấu chốt của tìm kiếm nhị phân là **bất biến khoảng giải thích được mọi quyết định loại bỏ**. Khi bất biến được phát biểu chính xác, các phép cập nhật biên, xử lý phần tử trùng và điều kiện dừng đều trở thành hệ quả logic có thể chứng minh, thay vì những công thức phải học thuộc.
