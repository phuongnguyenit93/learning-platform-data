# Tìm kiếm trong dãy xoay có thứ tự và các giả thiết áp dụng

## 1. Bài toán và thuật ngữ

Giả sử một mảng đã được **sắp xếp tăng không giảm** rồi cắt tại một vị trí và đổi chỗ hai đoạn. Ví dụ:

~~~text
Dãy đã sắp xếp:          [0, 1, 2, 4, 5, 6, 7]
Cắt trước giá trị 4:     [0, 1, 2] | [4, 5, 6, 7]
Dãy sau khi xoay:        [4, 5, 6, 7, 0, 1, 2]
                                   ^ điểm giảm
~~~

Bài toán: cho mảng đã xoay a và giá trị cần tìm target, hãy tìm vị trí một phần tử bằng target mà không phải sắp xếp lại mảng. Đây là biến thể của tìm kiếm nhị phân; thường được gọi là **search in rotated sorted array**.

“Xoay” ở đây là **xoay vòng các phần tử**, không đảo ngược thứ tự nội bộ: nếu dãy gốc là s[0..n), ta có thể viết a = s[k..n) nối với s[0..k), với một chỉ số k hợp lệ. Xoay 0 vị trí cũng được phép. Dãy gốc tăng **không giảm** nghĩa là cho phép phần tử bằng nhau; nếu yêu cầu tất cả phần tử **phân biệt** thì đó là giả thiết mạnh hơn, ảnh hưởng trực tiếp tới độ phức tạp.

Ví dụ hợp lệ khi cho phép lặp:

~~~text
[3, 3, 0, 0, 1, 1]  // xoay từ [0, 0, 1, 1, 3, 3]
[1, 1, 1, 1]        // đã tăng không giảm, xoay thế nào cũng vậy
[1, 2, 3, 4]        // chưa xoay (xoay 0 vị trí)
[]                  // đầu vào rỗng, không tìm thấy phần tử
~~~

Dãy [2, 1, 3] **không** phải là một phép xoay của dãy tăng không giảm: dù nhìn theo chiều trái sang phải có một lần giảm, không có vị trí cắt vòng nào làm toàn bộ các phần tử trở thành dãy tăng không giảm.

Mục tiêu của bài là xác định **khi nào có thể chia đôi**, vì sao bản có phần tử phân biệt đạt O(log n), vì sao phần tử trùng có thể làm suy biến O(n), và tại sao phải nêu rõ tiền điều kiện của đầu vào.

## 2. Hợp đồng đầu vào và đầu ra

Ta xác định một hợp đồng rõ ràng cho hàm tìm kiếm:

| Thuộc tính | Quy ước |
| --- | --- |
| Đầu vào | Mảng số nguyên a (không null), giá trị nguyên target |
| Tiền điều kiện | a là một phép xoay của **một** mảng tăng không giảm |
| Phần tử trùng | Có thể xuất hiện, kể cả ở hai đầu sau khi xoay |
| Đầu ra | **Bất kỳ** chỉ số i thỏa 0 ≤ i < n và a[i] == target; trả −1 nếu không có |
| Mảng rỗng | Hợp lệ, kết quả −1 |
| Mảng null | Ném NullPointerException trong ví dụ Java |
| Tác động phụ | Không sửa nội dung hoặc thứ tự mảng |
| Độ phức tạp | O(log n) khi các phần tử phân biệt; O(n) trường hợp tệ nhất nếu có phần tử lặp |
| Tính ổn định đầu vào | Mảng không bị thay đổi bởi tác nhân khác trong lúc tìm kiếm |

**Tìm bất kỳ vị trí khác tìm vị trí đầu tiên.** Ví dụ, trong [3, 1, 1, 2, 3], target = 3 có hai đáp án chỉ số 0 và 4. Hợp đồng này chấp nhận cả hai. Nếu yêu cầu “chỉ số nhỏ nhất”, cần thay đổi hậu điều kiện và lựa chọn thuật toán hoặc thực hiện công đoạn bổ sung. Đặc biệt các phần tử bằng nhau có thể nằm ở hai đầu mảng sau xoay, nên không thể tùy ý áp dụng cách tìm lower bound trên mảng tăng bình thường.

Hợp đồng dùng −1 an toàn vì **chỉ số hợp lệ luôn không âm**. Không dùng chính giá trị phần tử làm mã “không tìm thấy”: target có thể là −1 hoặc bất kỳ số nguyên nào.

Phương thức tìm kiếm ở ví dụ cuối bài **tin vào tiền điều kiện đã công bố**. Nó không quét trước toàn mảng để kiểm tra mảng thực sự là phép xoay; nếu làm vậy, ngay cả với phần tử phân biệt, tổng thời gian sẽ bao gồm một lượt O(n) và không còn bảo đảm O(log n) end-to-end.

## 3. Vì sao vẫn dùng được tìm kiếm nhị phân?

Trong mảng tăng thuần túy, so sánh target với a[mid] cho phép bỏ một nửa vì các phần tử hai phía đã có thứ tự. Trong mảng đã xoay, **toàn bộ** khoảng đang xét có thể không tăng, nhưng với các phần tử **phân biệt**, ít nhất một trong hai nửa [left, mid] hoặc [mid, right] vẫn tăng.

Ví dụ:

~~~text
[4, 5, 6, 7, 0, 1, 2]
 L        M        R

[left, mid] = [4, 5, 6, 7] tăng
[mid, right] = [7, 0, 1, 2] không tăng
~~~

Nếu target = 0, nó không nằm trong khoảng giá trị [4, 7], nên ta bỏ nửa trái và xét phần bên phải. Khi khoảng thu nhỏ, ta lại kiểm tra nửa nào chắc chắn có thứ tự để quyết định.

Với các phần tử phân biệt, tại một vòng lặp khi a[mid] chưa bằng target:

- Nếu **a[left] ≤ a[mid]**, nửa trái [left, mid] tăng. Nếu **a[left] ≤ target < a[mid]**, target (nếu tồn tại) thuộc phần trái nên đặt right = mid − 1. Ngược lại đặt left = mid + 1.
- Nếu **a[left] > a[mid]**, nửa phải [mid, right] tăng. Nếu **a[mid] < target ≤ a[right]**, đặt left = mid + 1. Ngược lại đặt right = mid − 1.

Các điều kiện ranh giới không đối xứng hoàn toàn vì đã kiểm tra **a[mid] == target** trước: trong nửa trái, bỏ mid nên dùng target < a[mid]; trong nửa phải, bỏ mid nên dùng a[mid] < target.

### Ví dụ truy vết với phần tử phân biệt

Tìm 0 trong [4, 5, 6, 7, 0, 1, 2], chỉ số 0-based:

| Bước | left | mid | right | a[mid] | Nhận xét và cập nhật |
| ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 0 | 3 | 6 | 7 | Nửa trái [4,5,6,7] tăng, 0 không thuộc [4,7]; left=4 |
| 2 | 4 | 5 | 6 | 1 | Nửa trái [0,1] tăng, 0 nằm trong [0,1); right=4 |
| 3 | 4 | 4 | 4 | 0 | Bằng target; trả chỉ số 4 |

Chỉ cần ba lần chọn mid. Đây là kết quả cho **bộ dữ liệu cụ thể** chứ không phải số bước cố định cho mọi n.

## 4. Mã giả khi mọi phần tử phân biệt

~~~text
searchDistinct(a, target):
    left  = 0
    right = a.length - 1

    while left <= right:
        mid = left + (right - left) / 2

        if a[mid] == target:
            return mid

        if a[left] <= a[mid]:          // nửa trái có thứ tự
            if a[left] <= target < a[mid]:
                right = mid - 1
            else:
                left = mid + 1
        else:                          // nửa phải có thứ tự
            if a[mid] < target <= a[right]:
                left = mid + 1
            else:
                right = mid - 1

    return -1
~~~

Công thức mid = left + (right − left) / 2 tránh nguy cơ tràn số nguyên nếu viết (left + right) / 2 với chỉ số lớn. Với Java, đây là phép chia nguyên khi left và right là số nguyên; left ≤ right bảo đảm hiệu không âm.

Điểm cần nhớ: so sánh trực tiếp a[mid] với target rồi tăng hay giảm left/right **như trên mảng tăng thuần** là sai, bởi mảng đã xoay có một đoạn giá trị lớn rồi quay về đoạn giá trị nhỏ.

## 5. Phần tử trùng làm mất thông tin như thế nào?

Khi cho phép các giá trị lặp, phép so sánh ở biên có thể **không tiết lộ nửa nào tăng**. Xem:

~~~text
a = [1, 1, 1, 1, 0, 1]
     L     M     R
target = 0

a[left] = a[mid] = a[right] = 1
~~~

Ba giá trị biên bằng nhau, nhưng một giá trị khác (0) vẫn có thể nằm sâu trong khoảng. Chỉ nhìn a[left], a[mid], a[right] không đủ biết đoạn xoay nằm bên trái hay bên phải. Nếu tự nhận nửa trái hoặc nửa phải là hoàn toàn tăng và loại một nửa mà không có bằng chứng, có nguy cơ bỏ mất target.

Vì đã kiểm tra a[mid] != target, trong trường hợp **a[left] == a[mid] == a[right]**, ta biết chắc a[left] và a[right] đều **không** bằng target. Do đó có thể loại **chính hai đầu mút này**:

~~~text
if a[left] == a[mid] && a[mid] == a[right]:
    left = left + 1
    right = right - 1
    continue
~~~

Quy tắc này luôn an toàn: nếu target tồn tại, nó không nằm ở hai đầu vừa bỏ. Sau khi thu hẹp, tiếp tục dùng cùng cách chia đôi với phần còn lại.

Chỉ được bỏ cả hai đầu sau khi đã kiểm tra mid không phải target và cả ba giá trị bằng nhau. Không được tùy ý bỏ một đoạn lớn chỉ vì “nhiều phần tử giống nhau”.

### Truy vết trường hợp mơ hồ

Với a = [1, 1, 1, 1, 0, 1], target = 0:

| Bước | [left, right] | mid, a[mid] | Quyết định |
| ---: | --- | --- | --- |
| 1 | [0, 5] | 2, 1 | a[left] = a[mid] = a[right] = 1 khác target; bỏ hai biên → [1, 4] |
| 2 | [1, 4] | 2, 1 | Nửa trái [1,1] tăng nhưng target không ở đó; còn [3,4] |
| 3 | [3, 4] | 3, 1 | Nửa trái chỉ có 1, target không ở đó; còn [4,4] |
| 4 | [4, 4] | 4, 0 | Tìm thấy, trả 4 |

Việc bỏ từng đầu có thể kéo dài. Ví dụ [1,1,1,1,1,1] tìm target = 2: rất nhiều vòng chỉ có thể loại 2 phần tử, dẫn tới số vòng tỷ lệ với n. Vì vậy **có trùng lặp thì thời gian tệ nhất là O(n)**, mặc dù nhiều đầu vào có trùng vẫn xử lý nhanh.

## 6. Mã giả tổng quát có phần tử trùng

~~~text
searchRotated(a, target):
    left  = 0
    right = a.length - 1

    while left <= right:
        mid = left + (right - left) / 2

        if a[mid] == target:
            return mid

        if a[left] == a[mid] && a[mid] == a[right]:
            left  = left + 1
            right = right - 1
            continue

        if a[left] <= a[mid]:
            if a[left] <= target < a[mid]:
                right = mid - 1
            else:
                left = mid + 1
        else:
            if a[mid] < target <= a[right]:
                left = mid + 1
            else:
                right = mid - 1

    return -1
~~~

Đây là một cách triển khai thống nhất, chạy được cả khi các phần tử phân biệt lẫn khi có giá trị trùng, dưới tiền điều kiện dãy là phép xoay của dãy tăng không giảm. Nhánh xử lý trùng xuất hiện **sau** kiểm tra bằng target, nên nó không vô tình bỏ đáp án ở mid.

Không bắt buộc phải tìm “điểm xoay” trước. Nếu tách bài thành tìm pivot rồi tìm nhị phân trên nửa tương ứng, vẫn cần xử lý đúng sự mơ hồ của giá trị trùng khi xác định pivot. Một thuật toán tìm pivot giả định giá trị phân biệt có thể thất bại khi chuyển sang đầu vào cho phép lặp.

## 7. Bất biến và chứng minh tính đúng

Chứng minh cần tách phần “không bỏ đáp án” khỏi phần “vòng lặp kết thúc”.

### 7.1. Bất biến của khoảng tìm kiếm

Tại đầu mỗi lượt, nếu target tồn tại trong toàn bộ mảng và chưa được trả về, thì **tồn tại một vị trí chứa target trong khoảng [left, right]**. Các vị trí bị loại ở những vòng trước không chứa lời giải mà thuật toán cần giữ lại.

Cơ sở: ban đầu [left, right] = [0, n−1], bao trùm tất cả chỉ số. Nếu n=0 thì left=0, right=−1 và vòng lặp không chạy, đúng vì không có phần tử.

Bước duy trì:

1. Nếu a[mid] bằng target, trả ngay một chỉ số hợp lệ.
2. Nếu a[left] = a[mid] = a[right] nhưng khác target, hai đầu đều không chứa target, nên thu hẹp [left+1, right−1] vẫn giữ mọi vị trí có thể là đáp án.
3. Ở nhánh còn lại, tính chất “mảng là phép xoay của một dãy tăng không giảm” và phép so sánh giá trị biên cho phép xác định phần đã được chứng minh có thứ tự. Nếu target nằm trong khoảng giá trị của nửa ấy, chỉ phần ấy còn khả năng chứa target; nếu không, bỏ nửa ấy và tiếp tục ở phần kia. Tính chất này áp dụng cả với mảng có trùng sau khi đã loại trường hợp ba giá trị biên bằng nhau gây mơ hồ.

Vì mỗi lần loại một phần ta chỉ bỏ những vị trí chắc chắn không cần thiết, bất biến tiếp tục đúng. Nếu hết vòng lặp mà không tìm thấy, left > right và khoảng rỗng. Bất biến khi ấy cho biết target không có trong mảng, nên trả −1 là đúng.

### 7.2. Vòng lặp luôn kết thúc

Khi chưa trả kết quả, mỗi nhánh đều **thu nhỏ nghiêm ngặt** số chỉ số trong [left, right]:

- left = mid + 1 bỏ ít nhất một vị trí;
- right = mid − 1 bỏ ít nhất một vị trí;
- left++ và right-- bỏ ít nhất một đầu, có thể cả hai.

Do số vị trí còn lại hữu hạn và không thể âm, vòng lặp kết thúc. Kết hợp với bất biến, đây là lý do hàm đáp ứng hậu điều kiện với mọi đầu vào đúng tiền điều kiện.

**Lưu ý về điều kiện tiên quyết:** nếu a không phải là phép xoay của dãy tăng không giảm, cơ sở lập luận “một phần có thứ tự nên loại được phần kia” không còn bảo đảm. Chương trình vẫn có thể chạy và trả một chỉ số tình cờ đúng hoặc −1, nhưng **không có bảo đảm tìm thấy mọi phần tử hiện diện**. Đó là lý do kiểm tra đầu vào và thực hiện tìm kiếm là hai nhiệm vụ cần phân biệt.

## 8. Độ phức tạp: O(log n) có điều kiện

Gọi n là số phần tử của mảng, giả định việc truy cập một phần tử và so sánh hai số nguyên là O(1).

| Tình huống | Best case | Worst case | Bộ nhớ phụ |
| --- | --- | --- | --- |
| Mảng xoay hợp lệ, **mọi giá trị phân biệt** | Θ(1) nếu gặp ngay ở mid | Θ(log n) với n đủ lớn | Θ(1) |
| Mảng xoay hợp lệ, **cho phép trùng lặp** | Θ(1) | O(n), thực tế có họ ví dụ Θ(n) | Θ(1) |
| Quét xác minh đầu vào rồi tìm kiếm | Không còn chỉ là chi phí tìm kiếm | O(n) cho cả trường hợp phân biệt | Θ(1) nếu kiểm tra trực tiếp bằng biến đếm |

Với giá trị phân biệt, mỗi vòng loại khoảng một nửa số phần tử, nên số vòng tăng theo log₂ n. Với giá trị trùng, nhánh a[left] = a[mid] = a[right] có thể chỉ giảm kích thước khoảng đi 2, dẫn đến hệ thức gần T(n) = T(n−2) + O(1), tức Θ(n) ở trường hợp tệ nhất. Vì thế lời khẳng định “tìm trong mọi mảng xoay bằng O(log n) kể cả có trùng” là **không đúng** cho thuật toán này.

Dù tệ nhất là O(n) với phần tử lặp, bộ nhớ phụ vẫn Θ(1): chỉ dùng left, right, mid và một vài biến; không cấp phát mảng phụ. Thời gian thực đo còn phụ thuộc kích thước, phân phối dữ liệu, CPU, cache, JVM và các lần so sánh. Big-O là cận tăng trưởng dưới mô hình chi phí, không phải số milli giây của một lần chạy.

### Khi nào phải đổi giải pháp?

Nếu yêu cầu luôn O(log n) trong trường hợp tệ nhất, cần một giả thiết hoặc cấu trúc dữ liệu mạnh hơn, chẳng hạn **các giá trị phân biệt**, thông tin pivot đáng tin cậy được lưu sẵn, hoặc chỉ mục được duy trì ngoài mảng. Với mảng xoay bất kỳ chứa nhiều bản sao và chỉ có quyền truy cập các giá trị bằng phép so sánh, các trường hợp mơ hồ có thể buộc phải kiểm tra tuyến tính.

Nếu có nhiều truy vấn trên cùng dữ liệu, có thể cân nhắc chi phí tiền xử lý và chỉ mục. Nếu chỉ có một truy vấn hoặc dãy ngắn, quét tuyến tính O(n) đôi khi đơn giản và phù hợp hơn. Lựa chọn phụ thuộc yêu cầu đúng, dữ liệu thực tế và tổng chi phí của toàn quy trình.

## 9. Kiểm tra xem mảng có thật sự là “dãy xoay có thứ tự”

Có hai tình huống khác nhau:

1. **Hợp đồng đã bảo đảm đầu vào hợp lệ:** phương thức tìm kiếm có thể chạy trực tiếp, giữ được cận O(log n) khi các giá trị phân biệt.
2. **Đầu vào không đáng tin:** có thể chủ động xác minh cấu trúc trước khi tìm, nhưng phải tính thêm chi phí O(n).

Một đặc điểm hữu ích của dãy xoay từ dãy tăng không giảm là: khi đi theo **vòng tròn** từ a[0] tới a[n−1] rồi trở về a[0], số cặp kề nhau có **giảm nghiêm ngặt** a[i] > a[(i+1) mod n] không quá 1. Với mảng không rỗng, điều kiện ấy cũng đủ để tồn tại một vị trí bắt đầu sao cho vòng đọc từ đó là dãy tăng không giảm. Nếu không có lần giảm nghiêm ngặt nào trên vòng tròn thì mọi phần tử bằng nhau.

Ví dụ:

~~~text
a = [4, 5, 6, 7, 0, 1, 2]
Có đúng một lần giảm 7 -> 0: hợp lệ.

a = [3, 3, 0, 0, 1, 1]
Có đúng một lần giảm 3 -> 0: hợp lệ.

a = [2, 1, 3]
Có hai lần giảm theo vòng: 2 -> 1 và 3 -> 2: không hợp lệ.
~~~

Chỉ đếm giảm trong **n−1 cặp kề tuyến tính** là chưa đủ: [2,1,3] chỉ có một lần giảm nội bộ nhưng không phải xoay của dãy tăng không giảm. Phải tính cả cặp nối **cuối → đầu**. Đối với dãy rỗng hoặc một phần tử, coi là hợp lệ theo quy ước hợp đồng.

Bài kiểm tra có O(n) thời gian và O(1) bộ nhớ phụ. Nó chỉ dùng khi thật sự cần xác thực dữ liệu; thêm nó vào mỗi lượt tìm kiếm khiến chi phí chung trở thành O(n) ngay cả trong trường hợp mảng có các phần tử phân biệt.

## 10. Cài đặt Java 17+ đầy đủ, chạy độc lập

Ví dụ sau chứa hai phương thức tách biệt:

- search: tìm **một** chỉ số bằng target hoặc −1, giả định mảng xoay tăng không giảm hợp lệ; hỗ trợ cả trùng lặp.
- isRotationOfNondecreasing: kiểm tra cấu trúc xoay khi cần, mất O(n). Không tự động gọi phương thức này trong search.

Lưu chương trình tên **RotatedSortedSearch.java**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public final class RotatedSortedSearch {
    private RotatedSortedSearch() {}

    /**
     * Precondition: a is a rotation of a nondecreasing int array.
     * Returns any matching index, or -1 when target is absent.
     * Does not modify a. Null input throws NullPointerException.
     *
     * O(log n) worst-case for distinct elements.
     * O(n) worst-case when duplicate elements are allowed.
     * O(1) extra space.
     */
    public static int search(int[] a, int target) {
        Objects.requireNonNull(a, "a");

        int left = 0;
        int right = a.length - 1;

        while (left <= right) {
            int mid = left + (right - left) / 2;

            if (a[mid] == target) {
                return mid;
            }

            // Equal boundaries cannot identify the sorted half.
            if (a[left] == a[mid] && a[mid] == a[right]) {
                left++;
                right--;
                continue;
            }

            if (a[left] <= a[mid]) { // Left half is sorted.
                if (a[left] <= target && target < a[mid]) {
                    right = mid - 1;
                } else {
                    left = mid + 1;
                }
            } else { // Right half is sorted.
                if (a[mid] < target && target <= a[right]) {
                    left = mid + 1;
                } else {
                    right = mid - 1;
                }
            }
        }

        return -1;
    }

    /**
     * Checks whether a is a rotation of a nondecreasing array.
     * An empty array is considered valid.
     * O(n) time, O(1) extra space.
     */
    public static boolean isRotationOfNondecreasing(int[] a) {
        Objects.requireNonNull(a, "a");
        int n = a.length;
        if (n < 2) {
            return true;
        }

        int decreases = 0;
        for (int i = 0; i < n; i++) {
            int next = (i + 1) % n;
            if (a[i] > a[next]) {
                decreases++;
                if (decreases > 1) {
                    return false;
                }
            }
        }
        return true;
    }

    private static void show(String label, int[] a, int target) {
        System.out.println(label + ": " + Arrays.toString(a)
                + ", target=" + target
                + ", index=" + search(a, target));
    }

    public static void main(String[] args) {
        show("Distinct", new int[] {4, 5, 6, 7, 0, 1, 2}, 0);
        show("Duplicates", new int[] {1, 1, 1, 1, 0, 1}, 0);
        show("Wrapped", new int[] {3, 1, 1, 2, 3}, 3);
        show("Missing", new int[] {2, 2, 2, 2}, 3);
        show("Empty", new int[] {}, 9);
        show("Unrotated", new int[] {1, 2, 3, 4}, 3);
        show("Negative", new int[] {-1, 0, 2, -5, -3}, -5);

        System.out.println("Valid [2, 1, 3]: "
                + isRotationOfNondecreasing(new int[] {2, 1, 3}));

        try {
            search(null, 1);
        } catch (NullPointerException ex) {
            System.out.println("Null: NullPointerException");
        }
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac RotatedSortedSearch.java
java RotatedSortedSearch
~~~

Stdout dự kiến chính xác:

~~~text
Distinct: [4, 5, 6, 7, 0, 1, 2], target=0, index=4
Duplicates: [1, 1, 1, 1, 0, 1], target=0, index=4
Wrapped: [3, 1, 1, 2, 3], target=3, index=4
Missing: [2, 2, 2, 2], target=3, index=-1
Empty: [], target=9, index=-1
Unrotated: [1, 2, 3, 4], target=3, index=2
Negative: [-1, 0, 2, -5, -3], target=-5, index=3
Valid [2, 1, 3]: false
Null: NullPointerException
~~~

Trong ví dụ Wrapped, a[0] và a[4] đều bằng 3, nhưng thuật toán trả **4**. Đó là kết quả đúng vì hợp đồng chỉ yêu cầu **bất kỳ** chỉ số hợp lệ, không yêu cầu chỉ số đầu tiên. Nếu thay đổi cách xử lý các trường hợp hòa, một cài đặt khác cũng có thể trả 0.

**Ghi chú triển khai:** có thể dùng long hoặc kiểm tra riêng nếu bài toán thao tác trên chỉ số hoặc phép tính ngoài phạm vi int; riêng việc lấy mid ở đây an toàn nhờ left + (right−left)/2. Các phép so sánh trực tiếp a[i] với target không thực hiện trừ hai giá trị int, nên tránh được lỗi tràn do so sánh bằng phép trừ.

## 11. Kiểm thử theo hợp đồng

Không đủ nếu chỉ thử một mảng xoay không có phần tử trùng. Nên có ít nhất các nhóm sau:

| Dãy a | target | Kết quả hợp lệ | Điều kiểm tra |
| --- | ---: | --- | --- |
| [] | 9 | −1 | Mảng rỗng |
| [7] | 7 | 0 | Một phần tử, tìm thấy |
| [7] | 8 | −1 | Một phần tử, không thấy |
| [1, 2, 3, 4] | 3 | 2 | Không xoay |
| [4, 5, 6, 7, 0, 1, 2] | 0 | 4 | Xoay, không trùng |
| [4, 5, 6, 7, 0, 1, 2] | 3 | −1 | Không tìm thấy trong mảng xoay |
| [1, 1, 1, 1, 0, 1] | 0 | 4 | Ba biên bằng nhau, phải loại dần |
| [3, 1, 1, 2, 3] | 3 | 0 hoặc 4 | Nhiều vị trí, không bắt buộc vị trí đầu |
| [2, 2, 2, 2] | 3 | −1 | Mọi giá trị giống nhau, không tìm thấy |
| [2, 2, 2, 2] | 2 | Một chỉ số từ 0 đến 3 | Mọi giá trị giống nhau, tìm thấy |
| [-1, 0, 2, -5, -3] | -5 | 3 | Số âm và xoay |
| [Integer.MIN_VALUE, Integer.MAX_VALUE] | Integer.MAX_VALUE | 1 | Cực trị kiểu int |
| null | 1 | NullPointerException | Đầu vào không hợp lệ |

Để kiểm thử tổng quát, sinh nhiều mảng **đã sắp xếp tăng không giảm**, chọn ngẫu nhiên điểm cắt k và xoay để tạo mảng hợp lệ. Với mỗi target, dùng một lần quét tuyến tính làm **oracle**:

~~~text
expectedExists = có tồn tại i mà a[i] == target?
result = search(a, target)

Nếu expectedExists:
    kiểm tra 0 <= result < a.length
    kiểm tra a[result] == target
Nếu không:
    kiểm tra result == -1
~~~

Không nên đòi result phải bằng chỉ số mà oracle tìm được nếu phần tử xuất hiện nhiều lần, vì hai thuật toán có thể chọn các chỉ số khác nhau mà đều đúng.

Cũng kiểm tra **tính bất biến theo xoay**: đối với cùng một đa tập phần tử, xoay ở những điểm cắt khác nhau không làm thay đổi sự tồn tại của target, dù vị trí tìm thấy có thể đổi. Trước và sau lời gọi, nội dung mảng phải trùng nhau.

Khi kiểm tra riêng phương thức isRotationOfNondecreasing, nên có:

- Dãy tăng bình thường → true.
- Dãy tăng đã xoay đúng → true.
- Dãy toàn phần tử bằng nhau → true.
- [2, 1, 3] → false (hai lần giảm trên vòng).
- [] và [5] → true theo quy ước.

Ví dụ về **kiểm thử theo thuộc tính** hữu ích hơn việc đo thời gian một lần: trước hết phải chứng minh hàm trả đúng kết quả trên miền đầu vào, sau đó mới so sánh hiệu năng với quét tuyến tính hoặc các cách tìm khác.

## 12. Các lỗi thường gặp

1. **Quên tiền điều kiện mảng xoay có thứ tự.** Không thể tự áp dụng thuật toán này cho dãy bất kỳ. Nếu không chắc đầu vào hợp lệ, cần xác minh hoặc chọn phương pháp khác.
2. **Dùng tìm kiếm nhị phân thông thường trên mảng đã xoay.** Không phải mọi phần tử phía trái mid đều nhỏ hơn mid; quy tắc bỏ nửa sẽ sai.
3. **Khẳng định O(log n) dù có trùng lặp.** Ba giá trị biên bằng nhau có thể buộc thu hẹp từng đầu, làm worst case thành O(n).
4. **Loại nửa mảng khi không xác định được nửa tăng.** Với a[left] == a[mid] == a[right] nhưng khác target, chỉ được chắc chắn loại các đầu mút đã kiểm tra; không suy đoán pivot ở phía nào.
5. **Dùng dấu < và ≤ sai.** Sau khi đã kiểm tra a[mid] == target, các điều kiện giữ nửa có dạng a[left] ≤ target < a[mid] hoặc a[mid] < target ≤ a[right].
6. **Dùng (left + right) / 2 trong ngữ cảnh chỉ số lớn.** Tổng hai chỉ số int có thể tràn; dùng left + (right−left)/2.
7. **Nhầm bất kỳ vị trí với vị trí đầu tiên.** Mảng có phần tử trùng sau xoay có thể đặt cùng một giá trị ở hai đầu.
8. **Tìm pivot bằng giả thiết giá trị phân biệt rồi áp dụng cho dữ liệu có trùng.** Quy tắc chọn nửa khi nhiều giá trị bằng nhau cần phân tích lại.
9. **Đánh giá hợp lệ chỉ bằng số lần giảm trên các cặp kề tuyến tính.** Phải xét vòng nối phần tử cuối với phần tử đầu; [2,1,3] là phản ví dụ.
10. **Bỏ qua chi phí xác minh hoặc chuẩn bị dữ liệu.** Nếu quét kiểm tra mảng O(n) trước mỗi truy vấn, toàn bộ quy trình không còn O(log n) khi xét thời gian tổng thể.
11. **Đổi thứ tự phần tử để tiện tìm nhưng vẫn trả chỉ số cũ.** Sắp xếp làm thay đổi chỉ số; nếu cần trả chỉ số trong mảng gốc thì phải bảo toàn ánh xạ.
12. **Không kiểm thử mảng rỗng, một phần tử, toàn phần tử trùng và target vắng mặt.** Những trường hợp này dễ làm lộ lỗi điều kiện dừng hoặc xử lý biên.

## 13. Khi nào nên áp dụng?

Thuật toán thích hợp khi dữ liệu là **một phép xoay của dãy tăng không giảm**, cần tìm một giá trị trong mảng, và không muốn sắp xếp lại để giữ các chỉ số ban đầu. Nếu mọi phần tử phân biệt, phương pháp có cận O(log n) thời gian và O(1) bộ nhớ phụ. Nếu có trùng, giải pháp vẫn đúng nhưng phải chấp nhận O(n) trường hợp tệ nhất.

Trước khi dùng trong một hệ thống thực tế, xác nhận:

- [ ] Dãy thực sự là phép xoay của **một dãy tăng không giảm**, không phải mảng bất kỳ có một đoạn giảm.
- [ ] Có cho phép phần tử trùng không, và có cần bảo đảm O(log n) trong worst case không?
- [ ] Kết quả yêu cầu chỉ số bất kỳ, đầu tiên, cuối cùng hay tất cả vị trí?
- [ ] Mảng rỗng, null và target không xuất hiện được xử lý đúng hợp đồng?
- [ ] So sánh giá trị và ranh giới dùng dấu <, ≤ đúng?
- [ ] Đã tính chi phí xác minh, tiền xử lý, xây chỉ mục nếu có?
- [ ] Kết quả kiểm thử được so với sự tồn tại của target, không ép trùng một chỉ số khi dữ liệu có lặp?
- [ ] Mảng giữ nguyên nội dung trong lúc chạy và sau lời gọi?

**Nguyên tắc kết luận:** trên dãy xoay có thứ tự, ta vẫn tìm nhị phân được bằng cách xác định một nửa còn tăng. Khi các biên trùng nhau làm mất thông tin, thu hẹp an toàn từng đầu là cần thiết; đổi lại, cận thời gian tệ nhất có thể trở thành tuyến tính. Mọi tuyên bố về tính đúng và tốc độ đều phải gắn với **giả thiết đầu vào** đã nêu.
