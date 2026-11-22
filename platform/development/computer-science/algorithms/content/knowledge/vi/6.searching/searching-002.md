# Tìm kiếm trên dữ liệu có thứ tự và không có thứ tự

Tìm kiếm là thao tác xác định xem một khóa có xuất hiện trong tập dữ liệu hay không, khóa đó nằm ở đâu hoặc bản ghi nào thỏa điều kiện. Cùng một câu hỏi, thuật toán phù hợp thay đổi khi **dữ liệu đã sắp xếp**, khi **dữ liệu chưa sắp xếp**, khi có nhiều truy vấn hoặc khi phải bảo toàn vị trí gốc.

Hai phương pháp nền tảng là **tìm kiếm tuyến tính (linear search)** và **tìm kiếm nhị phân (binary search)**. Bài học cũng giải thích các lựa chọn khi dùng chỉ mục băm, cây tìm kiếm có thứ tự, giá trị trùng lặp và truy vấn theo khoảng.

## 1. Phát biểu bài toán trước khi chọn thuật toán

Cho dãy a gồm n phần tử và một khóa x. “Tìm x” có thể mang nhiều nghĩa:

- **Tồn tại:** trả true nếu có ít nhất một phần tử bằng x, ngược lại false.
- **Tìm một vị trí:** trả một chỉ số i sao cho a[i] = x.
- **Vị trí đầu tiên/cuối cùng:** nếu có khóa trùng, cần vị trí nhỏ nhất/lớn nhất.
- **Tất cả vị trí:** trả danh sách mọi i thỏa a[i] = x.
- **Đếm:** trả số phần tử bằng x.
- **Tìm theo quan hệ thứ tự:** tìm phần tử đầu tiên không nhỏ hơn x, phần tử lớn nhất không vượt x, hoặc các phần tử thuộc đoạn [L, R].

Cần xác định **quy ước chỉ số** (0-based hay 1-based), kết quả khi **không tìm thấy** (−1, null hay vị trí chèn), cách xử lý **khóa lặp** và quan hệ dùng để so sánh.

Ví dụ, dãy chưa sắp xếp:

~~~text
index:  0  1  2  3  4  5  6
value:  7  2  9  2  5  2  1
~~~

Với khóa x = 2, ta có: tồn tại = true; vị trí đầu tiên = 1; mọi vị trí = [1, 3, 5]; số lần xuất hiện = 3. Nếu sắp xếp tăng thành **[1, 2, 2, 2, 5, 7, 9]**, các vị trí của x trong **dãy mới** là [1, 2, 3]. Không được nhầm những vị trí này với chỉ số trong dữ liệu gốc.

## 2. Tìm kiếm tuyến tính trên dữ liệu không có thứ tự

**Linear search** lần lượt kiểm tra từng phần tử. Với yêu cầu trả chỉ số đầu tiên:

~~~text
linearFirst(a, x):
    for i từ 0 đến n-1:
        if a[i] == x:
            return i
    return -1
~~~

Không cần bất kỳ giả thiết thứ tự nào. Nếu mảng rỗng, vòng lặp không thực hiện và trả −1. Nếu có nhiều khóa giống nhau, việc duyệt từ trái sang phải bảo đảm trả **chỉ số nhỏ nhất**.

**Vì sao đúng?** Khi thuật toán đang xét a[i], mọi vị trí j < i đã được kiểm tra và không bằng x. Nếu a[i] = x, i là vị trí phù hợp đầu tiên. Nếu duyệt hết mà không thấy, không có phần tử nào bằng x.

Độ phức tạp với n phần tử:

| Trường hợp | Số phép kiểm tra | Chi phí |
| --- | ---: | --- |
| Khóa xuất hiện ngay đầu | 1 | O(1) tốt nhất |
| Khóa ở cuối | n | O(n) |
| Khóa không tồn tại | n | O(n) |
| Vị trí xuất hiện phân bố rộng | Tỉ lệ với n | O(n) trung bình trong mô hình thông thường |
| Chỉ lưu chỉ số kết quả | — | O(1) bộ nhớ phụ |

Nếu đề yêu cầu **liệt kê tất cả** hoặc **đếm chính xác** các phần tử thỏa một điều kiện bất kỳ, một lần quét O(n) thường là cần thiết vì bất kỳ vị trí nào cũng có thể đóng góp đáp án. Để xuất k vị trí còn cần O(k) chỗ lưu danh sách kết quả, trừ khi xuất từng vị trí trực tiếp.

### Khi nào tuyến tính là lựa chọn phù hợp?

Tuyến tính đơn giản và đáng dùng khi n nhỏ, chỉ tìm một vài lần, dữ liệu thay đổi liên tục, thứ tự gốc phải được giữ nguyên hoặc điều kiện tìm kiếm không cho phép loại nhiều phần tử bằng một phép so sánh. Ví dụ “tìm sinh viên đầu tiên có cả ba điều kiện tùy ý” có thể cần kiểm tra từng bản ghi nếu chưa có chỉ mục thích hợp.

Ngay cả khi dãy đã tăng dần, việc quét vẫn đúng; có thể **dừng sớm** khi gặp a[i] > x, vì các phần tử tiếp theo không thể bằng x. Tuy nhiên, trường hợp xấu nhất vẫn là O(n).

## 3. Vì sao tìm kiếm nhị phân cần dữ liệu có thứ tự?

Giả sử mảng đã sắp xếp **tăng dần** và truy cập a[i] mất O(1). Chọn vị trí giữa mid của miền tìm kiếm:

- Nếu a[mid] < x, tất cả phần tử ở mid và bên trái đều không thể bằng x; tìm bên phải.
- Nếu a[mid] > x, tất cả phần tử ở mid và bên phải đều không thể bằng x; tìm bên trái.
- Nếu a[mid] == x, đã biết một vị trí khớp, dù chưa chắc là vị trí đầu tiên khi có khóa trùng.

Mỗi phép so sánh loại xấp xỉ nửa miền ứng viên. Sau k vòng, độ dài miền còn lại vào khoảng n/2^k, nên số vòng **O(log₂ n)**. Phiên bản lặp cần O(1) bộ nhớ phụ; phiên bản đệ quy cần thêm O(log n) ngăn xếp gọi hàm trong trường hợp thường gặp.

### Khoảng đóng và khoảng nửa mở

Có hai cách diễn đạt miền tìm kiếm, đều đúng khi dùng nhất quán:

- **[left, right]** bao gồm hai đầu; ban đầu left = 0 và right = n−1; còn ứng viên khi left ≤ right.
- **[lo, hi)** bao gồm lo nhưng loại trừ hi; ban đầu lo = 0 và hi = n; còn ứng viên khi lo < hi.

Nếu dùng khoảng đóng, sau khi loại mid cần cập nhật left = mid + 1 hoặc right = mid − 1. Nếu dùng khoảng nửa mở để tìm biên, có thể cập nhật lo = mid + 1 hoặc hi = mid.

Công thức **mid = lo + (hi − lo) / 2** với chỉ số không âm tránh nguy cơ tràn int của **(lo + hi) / 2** khi tổng hai chỉ số rất lớn.

### Phản ví dụ khi dữ liệu chưa sắp xếp

Dãy **[8, 1, 5, 3]** không tăng dần. Nếu tùy tiện chạy thuật toán tìm **chỉ số đầu tiên có phần tử ≥ 1** trên dãy này, phép loại nửa miền có thể trả 0 vì a[0] = 8; nhưng kết luận rằng mọi vị trí từ 0 trở đi đều phù hợp không có cơ sở. Với bài tìm khóa bằng 1, việc chỉ quan sát một vài phần tử giữa cũng không thể chứng minh nửa bỏ đi không có 1.

Tìm kiếm nhị phân có thể **tình cờ** trả đúng trên một số dữ liệu chưa sắp xếp, song không có bảo đảm. Trước khi áp dụng phải chứng minh thứ tự hoặc tính đơn điệu dùng để loại một nửa.

## 4. Lower bound, upper bound và khóa trùng

Trên mảng **tăng dần**, một phiên bản binary search trả vị trí khớp tùy ý không đủ khi bài yêu cầu tìm **đầu tiên, cuối cùng hoặc đếm**.

Định nghĩa:

- **lowerBound(x):** chỉ số nhỏ nhất i có a[i] ≥ x; trả n nếu không tồn tại vị trí như vậy.
- **upperBound(x):** chỉ số nhỏ nhất i có a[i] > x; trả n nếu không tồn tại.

Cả hai trả giá trị từ **0 đến n**. Giá trị n là **vị trí ngay sau cuối mảng**, hợp lệ như vị trí chèn nhưng không hợp lệ để truy cập a[n].

Ví dụ với **a = [1, 2, 2, 2, 5, 7, 9]**:

| x | lowerBound(x) | upperBound(x) | Số lần bằng x |
| ---: | ---: | ---: | ---: |
| 0 | 0 | 0 | 0 |
| 2 | 1 | 4 | 3 |
| 4 | 4 | 4 | 0 |
| 5 | 4 | 5 | 1 |
| 9 | 6 | 7 | 1 |
| 10 | 7 | 7 | 0 |

Có thể suy ra:

1. **Tồn tại x** khi p = lowerBound(x) thỏa **p < n và a[p] == x**.
2. **Vị trí đầu tiên** là p nếu tồn tại, còn không là −1.
3. **Vị trí cuối cùng** là upperBound(x) − 1 nếu tồn tại.
4. **Số lần xuất hiện** là upperBound(x) − lowerBound(x).
5. **Chèn x trước các phần tử bằng x** tại lowerBound(x); chèn sau các phần tử bằng x tại upperBound(x).
6. **Đếm số phần tử có giá trị trong đoạn đóng [L, R]**, với L ≤ R, bằng **upperBound(R) − lowerBound(L)**.

Nếu L > R, khoảng rỗng và số phần tử bằng 0. Công thức với hai bound không yêu cầu tăng R lên 1, vì vậy tránh lỗi tràn số ở giá trị nguyên lớn nhất.

### Bất biến của lower bound

Với khoảng tìm kiếm [lo, hi), duy trì:

- Mọi vị trí trước lo có giá trị **< x**.
- Mọi vị trí từ hi đến cuối mảng có giá trị **≥ x**.

~~~text
lowerBound(a, x):
    lo = 0
    hi = length(a)
    while lo < hi:
        mid = lo + (hi - lo) / 2
        if a[mid] < x:
            lo = mid + 1
        else:
            hi = mid
    return lo
~~~

Vòng lặp thu nhỏ khoảng ứng viên cho đến khi lo == hi; đây chính là vị trí đầu tiên có thể có giá trị ≥ x. **Upper bound** dùng cùng khuôn nhưng thay so sánh bằng **a[mid] <= x** để tìm vị trí đầu tiên > x. Hai hàm khác nhau chính tại việc xử lý các phần tử **bằng** x.

## 5. Chương trình Java 17+ chạy độc lập

Ví dụ dưới đây minh họa tìm kiếm trên dãy gốc, tạo bản sao đã sắp xếp, rồi tra biên và đếm khóa lặp. Đầu ra trả **chỉ số 0-based**; hàm tìm chính xác trả −1 nếu không tìm thấy.

~~~java
import java.util.Arrays;

public class SearchOrderedVsUnorderedDemo {

    static int linearFirst(int[] a, int key) {
        for (int i = 0; i < a.length; i++) {
            if (a[i] == key) {
                return i;
            }
        }
        return -1;
    }

    // Vi tri dau tien co a[i] >= key, hoac a.length.
    static int lowerBound(int[] a, int key) {
        int lo = 0;
        int hi = a.length;
        while (lo < hi) {
            int mid = lo + (hi - lo) / 2;
            if (a[mid] < key) {
                lo = mid + 1;
            } else {
                hi = mid;
            }
        }
        return lo;
    }

    // Vi tri dau tien co a[i] > key, hoac a.length.
    static int upperBound(int[] a, int key) {
        int lo = 0;
        int hi = a.length;
        while (lo < hi) {
            int mid = lo + (hi - lo) / 2;
            if (a[mid] <= key) {
                lo = mid + 1;
            } else {
                hi = mid;
            }
        }
        return lo;
    }

    static int firstSorted(int[] a, int key) {
        int p = lowerBound(a, key);
        return p < a.length && a[p] == key ? p : -1;
    }

    static int lastSorted(int[] a, int key) {
        int p = upperBound(a, key) - 1;
        return p >= 0 && a[p] == key ? p : -1;
    }

    static int countSorted(int[] a, int key) {
        return upperBound(a, key) - lowerBound(a, key);
    }

    static int countClosedRange(int[] a, int from, int to) {
        if (from > to) {
            return 0;
        }
        return upperBound(a, to) - lowerBound(a, from);
    }

    public static void main(String[] args) {
        int[] original = {7, 2, 9, 2, 5, 2, 1};
        System.out.println("Goc: " + Arrays.toString(original));
        System.out.println("Tuyen tinh 2: " + linearFirst(original, 2));
        System.out.println("Tuyen tinh 4: " + linearFirst(original, 4));

        int[] sorted = original.clone();
        Arrays.sort(sorted);
        System.out.println("Tang dan: " + Arrays.toString(sorted));
        System.out.println("Lower 2: " + lowerBound(sorted, 2));
        System.out.println("Upper 2: " + upperBound(sorted, 2));
        System.out.println("Dau tien 2: " + firstSorted(sorted, 2));
        System.out.println("Cuoi cung 2: " + lastSorted(sorted, 2));
        System.out.println("Dem 2: " + countSorted(sorted, 2));
        System.out.println("Dem [2,7]: " + countClosedRange(sorted, 2, 7));
        System.out.println("Tim 4: " + firstSorted(sorted, 4));
        System.out.println("Vi tri chen 4: " + lowerBound(sorted, 4));
        System.out.println("Tim 9: " + firstSorted(sorted, 9));
    }
}
~~~

Lưu thành **SearchOrderedVsUnorderedDemo.java**. Chạy với JDK 17 trở lên:

~~~bash
javac SearchOrderedVsUnorderedDemo.java
java SearchOrderedVsUnorderedDemo
~~~

Đầu ra:

~~~text
Goc: [7, 2, 9, 2, 5, 2, 1]
Tuyen tinh 2: 1
Tuyen tinh 4: -1
Tang dan: [1, 2, 2, 2, 5, 7, 9]
Lower 2: 1
Upper 2: 4
Dau tien 2: 1
Cuoi cung 2: 3
Dem 2: 3
Dem [2,7]: 5
Tim 4: -1
Vi tri chen 4: 4
Tim 9: 6
~~~

Giải thích:

- Trên dữ liệu gốc, số 2 xuất hiện đầu tiên ở chỉ số 1 và số 4 không xuất hiện.
- Sau khi sắp xếp, ba số 2 chiếm [1,4), tức chỉ số 1, 2, 3. Chúng có **lower bound = 1** và **upper bound = 4**.
- Đoạn giá trị **[2,7]** gồm **2, 2, 2, 5, 7** nên có 5 phần tử.
- Số 4 không có trong dãy, nhưng vị trí chèn để giữ thứ tự là **4**, đứng trước giá trị 5.
- **original.clone()** bảo toàn dãy ban đầu. Nếu thay bằng **Arrays.sort(original)**, các vị trí trả về sẽ chỉ còn mang ý nghĩa trong mảng đã sắp xếp.
- Hàm firstSorted phải kiểm tra **p < a.length** trước khi truy cập a[p], vì lowerBound có thể trả n.

Chương trình sử dụng số nguyên để làm rõ ý tưởng. Với dữ liệu đối tượng, cần định nghĩa quan hệ so sánh và tính bằng nhau phù hợp; không thể máy móc dùng toán tử == để so sánh nội dung đối tượng.

## 6. Phân tích thời gian cả quá trình: một lần hay nhiều lần tìm?

Giả sử có n phần tử và cần thực hiện q truy vấn tìm chính xác trên cùng tập dữ liệu.

| Chiến lược | Chuẩn bị | Mỗi truy vấn | Bộ nhớ phụ và lưu ý |
| --- | --- | --- | --- |
| Quét tuần tự | O(1) | O(n) trường hợp xấu nhất | O(1) nếu chỉ trả vị trí |
| Mảng đã tăng dần + binary search | Không cần sắp xếp lại | O(log n) | O(1) cho truy vấn |
| Sắp xếp rồi binary search | Thông thường khoảng O(n log n), tùy thuật toán sắp xếp | O(log n) | Có thể cần bản sao để giữ dữ liệu gốc |
| HashSet/HashMap | O(n) kỳ vọng để tạo chỉ mục | O(1) kỳ vọng, không bảo đảm mọi trường hợp | O(n), không duy trì thứ tự |
| TreeSet/TreeMap tự cân bằng | O(n log n) khi chèn n khóa lần lượt | O(log n) | O(n), thuận lợi cho cập nhật và truy vấn cận |

Nếu quét q lần, tổng chi phí xấu nhất là **O(qn)**. Nếu sắp xếp một lần rồi tìm q lần, tổng chi phí thông thường vào khoảng **O(n log n + q log n)**. Với một truy vấn duy nhất trên dữ liệu chưa sắp xếp, quét O(n) thường hợp lý hơn việc sắp xếp trước.

Độ phức tạp O(n log n) nói về **kiểu sắp xếp so sánh hiệu quả phổ biến**; không phải lời hứa rằng mọi thuật toán sắp xếp và mọi cài đặt đều có giới hạn xấu nhất như nhau. Trong Java, cần xem cụ thể loại mảng, bộ so sánh và API dùng để sắp xếp.

Nếu dãy được **cập nhật thường xuyên**, mảng giữ thứ tự có thể cần dịch chuyển O(n) phần tử khi chèn/xóa dù bước định vị chỉ O(log n). Cây tìm kiếm tự cân bằng có thể thích hợp hơn với các thao tác theo khóa trong O(log n), nhưng thường cần thêm bộ nhớ cho các nút và liên kết.

### Hash index có thay thế binary search không?

HashSet phù hợp với câu hỏi **có tồn tại khóa x?**, HashMap phù hợp với ánh xạ **key → value**. Tuy nhiên, hash thông thường không cung cấp thứ tự để trả lời tự nhiên các câu hỏi như:

- Khóa nhỏ nhất ≥ x hoặc khóa lớn nhất ≤ x là gì?
- Có bao nhiêu giá trị trong khoảng [L,R]?
- Xuất các giá trị trong [L,R] theo thứ tự tăng dần.

Nếu cần danh sách **mọi chỉ số gốc** của khóa trùng, HashMap phải lưu **key → danh sách chỉ số**; chỉ gán key → một chỉ số sẽ bỏ sót những lần xuất hiện khác.

Đối với tập dữ liệu động cần thứ tự, TreeMap/TreeSet cung cấp các thao tác như **floor, ceiling, lower, higher**; nếu cần truy vấn hạng và đếm khoảng thường xuyên với O(log n), có thể cần cấu trúc tăng cường thêm số lượng trong cây con.

## 7. Tìm kiếm và vấn đề truy cập ngẫu nhiên

Binary search O(log n) **theo thời gian** dựa trên giả định đọc a[mid] tốn O(1). Mảng và ArrayList thông thường đáp ứng giả định này. Với LinkedList, truy cập phần tử giữa theo chỉ số có thể phải đi qua nhiều nút; số lần **so sánh** vẫn ít nhưng tổng chi phí lấy các phần tử giữa có thể lớn.

Bởi vậy, không thể chỉ dựa vào tên “tìm kiếm nhị phân” để khẳng định O(log n) trên mọi cấu trúc. Cần xét cả **cách lưu dữ liệu**.

Với **danh sách liên kết có thứ tự**, đôi khi quét tuần tự là lựa chọn đơn giản và cạnh tranh hơn. Với **mảng rất lớn được lưu trên đĩa** và truy cập ngẫu nhiên tốn I/O, các chỉ mục kiểu B-tree/B+ tree hoặc lưu trữ theo khối thường phù hợp hơn việc thực hiện nhiều thao tác đọc rời rạc.

## 8. Dữ liệu giảm dần, đối tượng và quan hệ so sánh

### Dãy giảm dần

Dãy giảm dần vẫn có thứ tự nhưng các nhánh phải đổi chiều. Ví dụ để tìm vị trí đầu tiên có a[i] ≤ x trên dãy giảm dần, nếu a[mid] > x thì phải di chuyển sang **phải**; các phần tử bên trái còn lớn hơn. Không dùng nguyên xi điều kiện lowerBound tăng dần trên dữ liệu giảm dần.

### Dữ liệu là đối tượng

Trong Java, toán tử **==** trên tham chiếu đối tượng thường kiểm tra có cùng đối tượng hay không, khác với **equals** về nội dung. Sắp xếp và binary search trên đối tượng dùng **Comparable** hoặc **Comparator**. Nếu Comparator trả 0 cho hai khóa, chúng được xem là bằng nhau theo thứ tự so sánh; điều này có thể khác với equals nếu thiết kế không nhất quán.

Ví dụ, nếu sắp tên người dùng theo thứ tự không phân biệt hoa/thường nhưng lại dò bằng so sánh có phân biệt hoa/thường, kết quả có thể không đáp ứng ý nghĩa nghiệp vụ. Hãy chọn **một định nghĩa khóa và quan hệ so sánh thống nhất** từ khâu sắp xếp đến khâu tìm.

### API tiêu chuẩn

- **Arrays.sort(array)** sắp xếp ngay trên mảng truyền vào. Dùng **clone()** hoặc cách sao chép phù hợp nếu phải bảo toàn thứ tự ban đầu.
- **Arrays.binarySearch(sortedArray, key)** yêu cầu dữ liệu đã được sắp xếp theo đúng quy ước tương ứng. Khi có phần tử trùng, API **không bảo đảm** trả vị trí đầu tiên hay cuối cùng.
- Khi **Arrays.binarySearch** không tìm thấy, kết quả là **−(insertionPoint) − 1**, không nhất thiết bằng −1. Vị trí chèn được giải mã bằng **−result − 1** khi result âm.
- **Collections.binarySearch(list, key)** áp dụng trên danh sách đã sắp, nhưng tổng thời gian còn phụ thuộc kiểu danh sách và chi phí truy cập.
- **HashMap/HashSet** dựa trên hash và bình đẳng khóa, còn **TreeMap/TreeSet** dựa trên thứ tự khóa.

Nếu đề bắt buộc trả **vị trí đầu tiên, cuối cùng hoặc số lần xuất hiện**, hãy dùng lowerBound/upperBound thay vì mặc định kết quả tùy ý của Arrays.binarySearch là vị trí đầu.

## 9. Những biến thể tìm kiếm từ tính đơn điệu

Binary search không chỉ dành cho tìm **giá trị bằng x** trong mảng tăng. Điều cốt lõi là phải có **một ranh giới** phân chia hai vùng có thể chứng minh bằng so sánh hoặc điều kiện đơn điệu.

- **Tìm vị trí đầu tiên thỏa predicate:** nếu dãy giá trị boolean theo thứ tự chỉ có dạng false...false, true...true, có thể dùng binary search để tìm true đầu tiên.
- **Tìm đáp án nhỏ nhất thỏa yêu cầu:** ví dụ một lượng tài nguyên k đủ thì mọi lượng lớn hơn cũng đủ. Cần chứng minh tính đơn điệu rồi tìm ngưỡng nhỏ nhất thỏa.
- **Exponential search trên dãy có thứ tự nhưng chưa biết giới hạn:** mở rộng biên 1, 2, 4, 8... để tìm đoạn chứa x rồi dùng binary search trong đoạn đó; phải có cơ chế kiểm tra chỉ số vượt quá phạm vi.
- **Tìm phần tử gần x nhất theo giá trị:** trên dãy tăng, có thể dùng lowerBound(x) để lấy một vài ứng viên lân cận rồi so sánh khoảng cách; cần xử lý tie và biên.

Không áp dụng binary search khi predicate có dạng true, false, true thất thường hoặc dữ liệu có nhiều đoạn tăng giảm mà chưa chứng minh được quy tắc tìm đặc biệt. Một phép so sánh chỉ giúp loại nửa miền khi tính chất đơn điệu thật sự bảo đảm điều đó.

## 10. Chọn giải pháp cho từng tình huống

| Tình huống | Cách làm cân nhắc đầu tiên | Lý do |
| --- | --- | --- |
| Một vài lần tìm trên dãy chưa sắp xếp | Linear search | Không mất chi phí tiền xử lý |
| Dãy đã tăng và cần tìm/đếm khóa | Binary search, lower/upper bound | Tìm biên trong O(log n) |
| Dãy chưa sắp xếp nhưng có rất nhiều lần tìm tồn tại | HashSet hoặc HashMap | Xây chỉ mục một lần, tra cứu trung bình nhanh |
| Cần xuất mọi vị trí gốc khi khóa có thể trùng | Quét hoặc chỉ mục key → danh sách vị trí | Giữ đủ thông tin của các lần xuất hiện |
| Nhiều truy vấn đoạn giá trị trên dữ liệu tĩnh | Mảng sắp xếp + hai bound | Xác định biên O(log n), rồi đọc kết quả |
| Nhiều cập nhật và tìm khóa lân cận | TreeMap/TreeSet hoặc cây cân bằng | Duy trì thứ tự khi chèn/xóa |
| Điều kiện tìm không đơn điệu | Quét hoặc cấu trúc chỉ mục chuyên dụng | Không đủ điều kiện để loại nửa miền |
| Cần tìm ngưỡng nhỏ nhất thỏa điều kiện đơn điệu | Binary search trên predicate | Tận dụng ranh giới false/true |

Nếu phải **in k phần tử**, ngay cả khi xác định vùng đáp án bằng hai bound trong O(log n), thời gian xuất kết quả vẫn cần ít nhất **O(k)**. Thời gian O(log n) chỉ áp dụng cho thao tác **định vị biên**, không phải in vô hạn dữ liệu.

## 11. Lỗi phổ biến và kiểm thử biên

1. **Dùng binary search cho dữ liệu chưa có thứ tự.** Không thể bỏ một nửa dãy một cách có cơ sở.
2. **Sắp xếp trực tiếp dữ liệu cần giữ vị trí gốc.** Chỉ số sau sắp xếp không còn đồng nhất với chỉ số trước sắp xếp.
3. **Nhầm [left,right] với [lo,hi).** Sai điều kiện vòng lặp hoặc cập nhật mid dễ gây bỏ sót và lặp vô hạn.
4. **Đọc a[n] từ lowerBound trả về n.** Vị trí chèn n nằm ngoài phạm vi truy cập.
5. **Quên khóa trùng.** Một vị trí đúng chưa phải vị trí đầu tiên, cuối cùng hoặc số lần xuất hiện.
6. **Cho rằng Arrays.binarySearch không tìm thấy luôn trả −1.** Kết quả âm mã hóa vị trí chèn.
7. **Dùng Comparator không phù hợp định nghĩa khóa.** Thứ tự khi sắp xếp và điều kiện tìm phải thống nhất.
8. **Cho rằng chi phí binary search luôn O(log n) trên LinkedList.** Chi phí lấy phần tử giữa ảnh hưởng thời gian thực.
9. **Tính mid bằng left + right rồi chia 2.** Có thể tràn với chỉ số lớn.
10. **Sắp xếp trước mọi truy vấn mà không xét lợi ích.** Với một lần tìm, quét tuyến tính thường tiết kiệm hơn.

Các ca kiểm thử nên có: **dãy rỗng**, **một phần tử**, **khóa đầu/cuối**, **khóa không tồn tại nhỏ hơn min hoặc lớn hơn max**, **nhiều khóa trùng**, **toàn bộ phần tử bằng nhau**, **số âm**, **giá trị rất lớn**, **dữ liệu giảm dần** và **đoạn L > R**. Đối với hàm trả chỉ số, phân biệt rõ −1 với vị trí chèn 0..n.

## 12. Tự kiểm tra và ghi nhớ

**Câu 1.** Trên dãy chưa sắp xếp [5, 1, 5, 9], tìm vị trí đầu tiên của 5 bằng tuyến tính trả gì?  
**Đáp án:** **0**.

**Câu 2.** Trên dãy đã tăng [1, 2, 2, 4, 6], lowerBound(2) và upperBound(2) là gì?  
**Đáp án:** **1 và 3**; có hai phần tử bằng 2.

**Câu 3.** Trên dãy tăng [1, 2, 2, 4, 6], lowerBound(3) là bao nhiêu khi không có 3?  
**Đáp án:** **3**, vị trí chèn 3 ngay trước giá trị 4.

**Câu 4.** Vì sao tìm kiếm nhị phân có thể không đúng trên [8, 1, 5, 3]?  
**Đáp án:** Không có tính thứ tự để loại trừ cả một nửa ứng viên sau phép so sánh ở giữa.

**Câu 5.** Với dãy tăng [1, 2, 2, 2, 5, 7, 9], bao nhiêu phần tử thuộc [2,5]?  
**Đáp án:** **upperBound(5) − lowerBound(2) = 5 − 1 = 4**.

**Câu 6.** Nếu có n bản ghi chưa sắp và chỉ một truy vấn tìm chính xác, nên ưu tiên gì?  
**Đáp án:** Thường ưu tiên **linear search O(n)**; không cần trả thêm chi phí sắp xếp.

**Ghi nhớ:** Tìm kiếm tuyến tính hoạt động trên **dữ liệu không có thứ tự** với O(n) thời gian xấu nhất. Tìm kiếm nhị phân dùng **thứ tự cùng khả năng truy cập ngẫu nhiên** để đạt O(log n) và có thể mở rộng thành lower/upper bound, đếm khóa trùng, xác định vị trí chèn hoặc tìm giá trị trong khoảng. Trước khi viết code, luôn chốt **đầu ra cần trả**, **dữ liệu đã có thứ tự hay chưa**, **cách xử lý trùng lặp**, **chi phí tiền xử lý** và **các điều kiện để loại nửa miền tìm kiếm**.