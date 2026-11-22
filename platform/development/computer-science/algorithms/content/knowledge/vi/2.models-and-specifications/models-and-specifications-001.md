# Chuyển yêu cầu thành hợp đồng đầu vào–đầu ra

## 1. Hợp đồng đầu vào–đầu ra là gì?

Khi nhận một yêu cầu như “tìm phần tử x trong dãy”, người thiết kế thuật toán chưa có đủ thông tin để viết chương trình đúng: dãy có được sắp xếp không, có thể rỗng không, x xuất hiện nhiều lần thì lấy vị trí nào, không tìm thấy thì trả gì? **Hợp đồng đầu vào–đầu ra** (input/output contract) là đặc tả có thể kiểm chứng, mô tả điều kiện mà bên gọi phải đáp ứng và cam kết mà thuật toán phải thực hiện.

Hợp đồng trả lời ba câu hỏi: **nhận gì**, **đảm bảo gì**, **trong điều kiện nào**. Nó là ranh giới giữa yêu cầu nghiệp vụ và một cách cài đặt cụ thể. Nhiều thuật toán khác nhau có thể cùng thỏa một hợp đồng; chỉ khi hợp đồng rõ ràng mới có thể lựa chọn thuật toán, chứng minh tính đúng và thiết kế kiểm thử.

Các thành phần thường gặp:

| Thành phần | Câu hỏi cần chốt |
| --- | --- |
| Mục tiêu | Tác vụ giải quyết vấn đề nào, đối tượng nào được tính là kết quả đúng? |
| Đầu vào | Kiểu dữ liệu, cấu trúc, đơn vị, miền giá trị, kích thước, quy ước chỉ số là gì? |
| Tiền điều kiện (precondition) | Dữ liệu phải thỏa tính chất nào để thuật toán bảo đảm kết quả, chẳng hạn mảng đã tăng dần? |
| Đầu ra | Kiểu trả về và ý nghĩa từng giá trị, kể cả khi không có lời giải, là gì? |
| Hậu điều kiện (postcondition) | Quan hệ chính xác giữa đầu vào ban đầu và đầu ra là gì? |
| Lỗi và trường hợp biên | Dữ liệu null, rỗng, không hợp lệ, quá giới hạn, không có kết quả được xử lý thế nào? |
| Tác động phụ | Có sửa đầu vào, ghi trạng thái, I/O hay thay đổi thứ tự phần tử không? |
| Ràng buộc chất lượng | Thời gian, bộ nhớ, tính ổn định, tính xác định cần bảo đảm ở mức nào và trên giả định nào? |

**Tiền điều kiện khác kiểm tra hợp lệ tại runtime.** Ví dụ, “mảng đã sắp xếp tăng không giảm” có thể là trách nhiệm của bên gọi; phương thức không nhất thiết quét toàn mảng để xác nhận. Nếu API muốn tự từ chối mọi mảng chưa sắp xếp, đó là một cam kết bổ sung, có chi phí kiểm tra riêng và phải ghi trong hợp đồng.

## 2. Quy trình chuyển yêu cầu tự nhiên thành hợp đồng

### Bước 1 — Tách mục tiêu khỏi cách làm

Xác định động từ và đối tượng: *tìm vị trí*, *sắp xếp*, *đếm*, *chọn đường đi*, *tối ưu chi phí*. Ghi nhận tiêu chí thành công từ góc nhìn người dùng. Không mặc nhiên chọn tìm kiếm nhị phân, quy hoạch động hay cấu trúc dữ liệu cụ thể trước khi làm rõ ràng buộc.

Ví dụ “tìm phần tử” là yêu cầu còn mơ hồ; “trả về chỉ số nhỏ nhất của phần tử bằng x trong mảng int đã sắp xếp tăng không giảm” là mục tiêu có thể kiểm chứng.

### Bước 2 — Chuẩn hóa dữ liệu đầu vào

Mỗi tham số cần có tên, kiểu, miền giá trị và ý nghĩa:

- Kiểu: số nguyên, số thực, chuỗi, mảng, danh sách, đồ thị, tập hợp hay bản ghi.
- Kích thước: rỗng có hợp lệ không; giới hạn n và độ dài; dữ liệu có thể có phần tử trùng không.
- Thuộc tính cấu trúc: đã sắp xếp, các đỉnh hợp lệ, đồ thị có hướng, trọng số không âm, chuỗi đã chuẩn hóa hay chưa.
- Quy ước: chỉ số bắt đầu từ 0 hay 1, khoảng đóng hay nửa mở, đơn vị đo và phạm vi giá trị.
- Quyền sở hữu: đầu vào có thể bị thay đổi hay phải được giữ nguyên.

Một điều kiện “không âm” không được ngầm gán cho dữ liệu nếu yêu cầu chưa cho phép. Những điểm còn thiếu phải được làm rõ hoặc ghi thành giả định được phê duyệt; không biến giả định thành sự thật một cách âm thầm.

### Bước 3 — Xác định tiền điều kiện

Viết điều kiện đúng trước khi thực thi, chẳng hạn:

- Mảng a không phải null.
- Với mọi i từ 0 đến n−2, a[i] ≤ a[i+1] (tăng không giảm).
- Tham số k nằm trong khoảng 0 ≤ k ≤ n.
- Với bài toán đường đi ngắn dùng Dijkstra, các cạnh có trọng số không âm.

Phân biệt **đầu vào hợp lệ** (thuộc miền thuật toán cam kết giải quyết) và **đầu vào không hợp lệ** (có thể bị từ chối hoặc nằm ngoài bảo đảm). Không được tùy tiện đồng nhất “dữ liệu rỗng” với “dữ liệu lỗi”: mảng rỗng hoàn toàn hợp lệ đối với nhiều thuật toán tìm kiếm.

### Bước 4 — Định nghĩa kết quả bằng hậu điều kiện

Không dừng ở câu “trả về kết quả chính xác”. Hãy chỉ rõ kết quả chứng minh được điều gì. Ví dụ, nếu trả về chỉ số r của lần xuất hiện đầu tiên:

- Khi r ≥ 0: r là chỉ số hợp lệ, a[r] bằng x và không có chỉ số j nhỏ hơn r với a[j] bằng x.
- Khi r = −1: không tồn tại chỉ số i có a[i] bằng x.
- Mảng đầu vào sau lời gọi có cùng nội dung như trước lời gọi.

Nếu đầu ra là một tập hợp hoặc dãy, phải nói rõ thứ tự, phần tử trùng, tính ổn định và việc có được sửa dữ liệu gốc hay không. Với bài toán có nhiều đáp án đúng, cần quyết định chấp nhận mọi đáp án thỏa điều kiện hay quy định cách phá hòa (tie-breaking).

### Bước 5 — Định nghĩa nhánh đặc biệt và lỗi

Ghi thành bảng tình huống: dữ liệu rỗng, không có lời giải, nhiều lời giải, tham số bất hợp lệ, giới hạn cực trị. Phân biệt rõ **không có kết quả hợp lệ** với **không thể xử lý đầu vào**. Ví dụ, trong tìm kiếm: không thấy x trả về −1; mảng null ném ngoại lệ; mảng rỗng trả về −1.

Nếu ngoại lệ là một phần hợp đồng, ghi đúng loại ngoại lệ và điều kiện kích hoạt. Nếu một tiền điều kiện không được kiểm tra trong mã, không tuyên bố phương thức sẽ chủ động phát hiện mọi trường hợp vi phạm.

### Bước 6 — Chốt tác động phụ và ràng buộc phi chức năng

Ghi rõ thuật toán thuần túy hay có thay đổi bên ngoài, có giữ nguyên đầu vào không, có cần kết quả xác định không. Chỉ nêu độ phức tạp khi đã ghi giả định về kích thước đầu vào và mô hình chi phí. Chẳng hạn, tìm kiếm nhị phân trên mảng truy cập ngẫu nhiên đã sắp xếp có thời gian O(log n) và bộ nhớ phụ O(1); nếu phải tự kiểm tra tính sắp xếp bằng một lượt quét, thời gian tổng thể không còn O(log n).

### Bước 7 — Viết ví dụ đối chứng và truy vết

Với mỗi mệnh đề quan trọng trong hợp đồng, tạo ít nhất một ví dụ hoặc phép kiểm thử có thể bác bỏ một cài đặt sai. Đặc biệt kiểm tra giá trị nhỏ nhất, lớn nhất, không tìm thấy, phần tử trùng và trạng thái rỗng. Cuối cùng đối chiếu từng câu trong yêu cầu với một điều khoản của hợp đồng hoặc một điểm cần hỏi lại.

## 3. Mẫu hợp đồng có thể tái sử dụng

~~~text
Tên tác vụ:
Mục tiêu quan sát được:
Đầu vào:
  - tên, kiểu, miền giá trị, cấu trúc, giới hạn, quy ước
Tiền điều kiện:
  - những tính chất bên gọi phải bảo đảm
Đầu ra:
  - kiểu và ý nghĩa của từng dạng giá trị
Hậu điều kiện:
  - quan hệ có thể kiểm chứng giữa input trước gọi và output
Trường hợp đặc biệt:
  - rỗng, trùng, không có lời giải, cực trị
Đầu vào không hợp lệ:
  - xử lý bằng ngoại lệ, mã lỗi hay ngoài phạm vi cam kết
Tác động phụ:
  - những thay đổi được phép và những thứ phải giữ nguyên
Ràng buộc:
  - thời gian/bộ nhớ/tính ổn định/tính xác định, cùng giả định
Ví dụ và kiểm thử chấp nhận:
  - các input, kết quả dự kiến và tính chất cần kiểm chứng
~~~

Mẫu này độc lập với ngôn ngữ lập trình. Khi chuyển sang Java, kiểu dữ liệu, giá trị trả về và ngoại lệ nên khớp với chữ ký phương thức và tài liệu API; hợp đồng không được phụ thuộc vào tên biến vòng lặp hoặc chiến lược cài đặt.

## 4. Ví dụ đầy đủ: tìm vị trí đầu tiên trong mảng đã sắp xếp

### 4.1. Từ câu yêu cầu mơ hồ đến đặc tả chính xác

Yêu cầu ban đầu: “Cho một mảng và một số nguyên x, tìm vị trí của x.”

Các câu hỏi bắt buộc phải giải quyết: mảng có được sắp xếp không; chỉ số tính từ 0 hay 1; giá trị trùng xử lý thế nào; không thấy thì trả gì; mảng rỗng có hợp lệ không; có được sửa mảng không?

Hợp đồng được chốt cho ví dụ này:

| Thuộc tính | Cam kết |
| --- | --- |
| API | firstIndexOf(int[] a, int target) trả về int |
| Đầu vào hợp lệ | a khác null, có thể rỗng, được sắp xếp tăng không giảm |
| Quy ước | Chỉ số bắt đầu từ 0; các phần tử có thể trùng nhau |
| Kết quả khi tìm thấy | Chỉ số nhỏ nhất i sao cho a[i] == target |
| Kết quả khi không thấy | −1 |
| a == null | Ném IllegalArgumentException |
| a chưa sắp xếp | Vi phạm tiền điều kiện; không bảo đảm kết quả và không hứa phát hiện |
| Tác động phụ | Không sửa a |
| Độ phức tạp | O(log n) thời gian, O(1) bộ nhớ phụ, với n = a.length và a đã sắp xếp |

Viết dạng logic cho đầu vào hợp lệ:

- **P (tiền điều kiện):** a ≠ null và với mọi i thuộc [0, n−2], a[i] ≤ a[i+1].
- **Q (hậu điều kiện):** nếu kết quả r = −1 thì không có phần tử nào bằng target; nếu r ≥ 0 thì 0 ≤ r < n, a[r] = target và với mọi j < r, a[j] ≠ target. Trong cả hai trường hợp, a giữ nguyên.
- **Nhánh lỗi bổ sung:** a == null được kiểm tra và gây IllegalArgumentException.

Ký pháp Hoare **{P} A {Q}** biểu thị: nếu P đúng và thuật toán A kết thúc bình thường, Q phải đúng. Đây là phát biểu về *tính đúng bộ phận*; để có tính đúng toàn phần còn phải chứng minh A kết thúc. Ngoại lệ được đặc tả ở nhánh lỗi riêng.

### 4.2. Cài đặt Java 17+

~~~java
import java.util.Arrays;

public final class FirstOccurrenceContract {
    private FirstOccurrenceContract() {}

    /**
     * Precondition: a is non-null and sorted in nondecreasing order.
     * Returns the smallest index containing target, or -1 if absent.
     * Does not modify a. An unsorted array violates the precondition.
     */
    public static int firstIndexOf(int[] a, int target) {
        if (a == null) {
            throw new IllegalArgumentException("a must not be null");
        }

        int left = 0;
        int right = a.length; // Search interval [left, right).

        while (left < right) {
            int mid = left + (right - left) / 2;
            if (a[mid] < target) {
                left = mid + 1;
            } else {
                right = mid;
            }
        }

        return left < a.length && a[left] == target ? left : -1;
    }

    public static void main(String[] args) {
        int[] data = {1, 2, 2, 2, 5};

        System.out.println(firstIndexOf(data, 2));
        System.out.println(firstIndexOf(data, 4));
        System.out.println(firstIndexOf(new int[0], 7));
        System.out.println(Arrays.toString(data));
    }
}
~~~

Lưu dưới tên **FirstOccurrenceContract.java**, rồi chạy:

~~~bash
javac FirstOccurrenceContract.java
java FirstOccurrenceContract
~~~

Kết quả chuẩn trên stdout:

~~~text
1
-1
-1
[1, 2, 2, 2, 5]
~~~

Giải thích: chỉ số đầu tiên của số 2 là 1; số 4 không xuất hiện; mảng rỗng không chứa số 7; in lại mảng xác nhận ví dụ này không thay đổi dữ liệu. Kiểm tra một lần bằng in mảng chưa phải là bằng chứng tổng quát rằng hàm không sửa mọi đầu vào; thuộc tính ấy còn cần được kiểm tra hoặc suy luận từ thân hàm.

**Vì sao dùng khoảng nửa mở [left, right)?** Thuật toán tìm vị trí đầu tiên mà giá trị không nhỏ hơn target (lower bound). Khởi đầu left = 0 và right = n; với mỗi bước, nếu a[mid] < target thì đáp án phải ở bên phải mid, ngược lại đáp án có thể là mid hoặc bên trái. Khi left = right, chỉ số này là vị trí lower bound; ta kiểm tra thêm xem có bằng target hay không.

Bất biến vòng lặp:

1. 0 ≤ left ≤ right ≤ n.
2. Mọi chỉ số i < left đều có a[i] < target.
3. Mọi chỉ số i ≥ right đều có a[i] ≥ target.

Ban đầu các miền bị loại đều rỗng nên bất biến đúng. Tính sắp xếp của a bảo đảm mỗi nhánh cập nhật vẫn giữ bất biến. Khi dừng, left = right nên mọi vị trí trước left nhỏ hơn target, mọi vị trí từ left trở đi lớn hơn hoặc bằng target. Vì vậy, nếu a[left] bằng target thì left là chỉ số nhỏ nhất thỏa yêu cầu; nếu không thì target không xuất hiện. Mỗi vòng lặp làm ngắn khoảng tìm kiếm, nên thuật toán kết thúc. Biểu thức **left + (right − left) / 2** tránh rủi ro cộng trực tiếp left + right làm tràn số nguyên.

### 4.3. Bộ kiểm thử từ hợp đồng

| Dữ liệu đầu vào | target | Kết quả dự kiến | Điều khoản được kiểm tra |
| --- | ---: | ---: | --- |
| [] | 7 | −1 | Mảng rỗng là hợp lệ |
| [4] | 4 | 0 | Một phần tử, tìm thấy |
| [4] | 3 | −1 | Một phần tử, không thấy |
| [1, 2, 2, 2, 5] | 2 | 1 | Nhiều phần tử trùng, lấy vị trí đầu tiên |
| [1, 3, 5] | 4 | −1 | Giá trị nằm giữa hai phần tử |
| [−2147483648, 0, 2147483647] | 2147483647 | 2 | Biên kiểu int |
| null | 2 | IllegalArgumentException | Nhánh dữ liệu không hợp lệ |

Ngoài bảng ví dụ, kiểm tra thuộc tính tổng quát: với mọi mảng đã sắp xếp hợp lệ, kết quả luôn là −1 hoặc chỉ số hợp lệ; nếu kết quả là chỉ số, phần tử tại đó bằng target và không có phần tử bằng target ở bên trái; đầu vào không bị thay đổi. Có thể so với một thuật toán quét tuyến tính đơn giản làm *oracle* cho các bộ dữ liệu ngẫu nhiên nhỏ. Mảng [2, 1] vi phạm tiền điều kiện nên không thể dùng để yêu cầu phương thức trả một kết quả xác định theo hợp đồng này.

## 5. Khi hợp đồng thay đổi, thuật toán hoặc kiểm thử cũng đổi

Cùng một phát biểu “tìm x” nhưng các hợp đồng khác nhau dẫn tới cách giải khác nhau:

| Yêu cầu được chốt | Hệ quả thiết kế |
| --- | --- |
| Mảng bất kỳ, chỉ cần một vị trí xuất hiện | Có thể quét tuyến tính, không đòi hỏi sắp xếp |
| Mảng tăng không giảm, lấy lần xuất hiện đầu tiên | Có thể dùng lower bound như ví dụ |
| Mảng tăng không giảm, lấy lần xuất hiện cuối cùng | Cần tìm biên phải của nhóm phần tử bằng x |
| Mảng chưa sắp xếp, phải trả chỉ số trong mảng gốc | Không thể sắp xếp làm mất thông tin vị trí mà không lưu ánh xạ |
| Bắt buộc phát hiện mảng chưa sắp xếp | Cần định nghĩa cách báo lỗi và tính thêm chi phí kiểm tra |

Ví dụ thứ hai: “trả bản sao đã sắp xếp tăng dần của dãy số nguyên”. Hợp đồng nên nêu đầu vào có được null hay rỗng không; đầu ra là **mảng mới**, tăng không giảm, có cùng số lượng xuất hiện của từng giá trị như đầu vào; mảng gốc không đổi. Không đủ khi chỉ yêu cầu “mảng kết quả tăng dần”: một thuật toán trả mảng rỗng cho mọi đầu vào vẫn tăng dần nhưng làm mất toàn bộ phần tử! Phải có cả điều kiện **thứ tự** và **bảo toàn đa tập phần tử**. Nếu sắp xếp các bản ghi theo khóa, cần nói thêm có yêu cầu *stable sort* (giữ thứ tự tương đối của các bản ghi cùng khóa) hay không.

Với các yêu cầu tối ưu hóa, hậu điều kiện thường phải có hai vế: **đầu ra khả thi** (thỏa mọi ràng buộc) và **giá trị tối ưu** (không tồn tại đầu ra khả thi tốt hơn theo hàm mục tiêu). Một lời giải có chi phí thấp nhưng vi phạm ràng buộc không thỏa hợp đồng.

## 6. Từ hợp đồng đến đặc tả kiểm chứng được

Có ba lớp nên giữ tách bạch:

- **Điều kiện đầu vào:** bên gọi có trách nhiệm cung cấp dữ liệu trong miền cam kết; nếu API tự kiểm tra một phần thì ghi rõ phần đó.
- **Tính chất kết quả:** kiểm thử với ví dụ cụ thể, kiểm thử thuộc tính, so sánh với lời giải đơn giản hoặc chứng minh bằng bất biến.
- **Chi phí và tác động phụ:** đo trên dữ liệu có kích thước đại diện, phân tích độ phức tạp và xác minh những trạng thái phải giữ nguyên.

Cần phân biệt rõ: **ví dụ** giúp hiểu ý nghĩa, **kiểm thử** phát hiện nhiều sai sót, còn **chứng minh** giải thích tại sao kết quả luôn đúng khi các giả định được đáp ứng. Không một ví dụ đơn lẻ nào thay cho hậu điều kiện tổng quát.

Để truy vết yêu cầu, có thể lập bảng nhỏ:

| Phát biểu trong yêu cầu | Điều khoản hợp đồng | Kiểm tra |
| --- | --- | --- |
| “Tìm vị trí” | Kết quả là chỉ số 0-based hoặc −1 | Một phần tử; không tìm thấy |
| “Nếu xuất hiện nhiều lần” | Chỉ số nhỏ nhất | Mảng có phần tử trùng |
| “Không làm mất dữ liệu” | Mảng đầu vào không đổi | So sánh trước/sau |
| “Tìm kiếm nhanh trên dữ liệu đã sắp xếp” | P: mảng tăng không giảm; O(log n) | Bất biến, phân tích chia đôi |

## 7. Lỗi thường gặp và cách sửa

1. **Viết thuật toán trước khi chốt hợp đồng.** Dễ chọn nhầm cách làm khi thiếu thông tin về thứ tự, phần tử trùng hoặc dữ liệu rỗng. Hãy làm rõ miền đầu vào và kết quả trước.
2. **Hậu điều kiện quá yếu.** “Trả mảng tăng dần” thiếu yêu cầu bảo toàn phần tử; “trả một vị trí của x” không giải quyết trường hợp cần vị trí đầu tiên. Bổ sung những tính chất có thể kiểm chứng.
3. **Đánh đồng không có đáp án với đầu vào sai.** Mảng hợp lệ nhưng không chứa target là kết quả −1; mảng null được xử lý theo nhánh ngoại lệ đã công bố.
4. **Giấu giả định trong cài đặt.** Tìm kiếm nhị phân cần dữ liệu có thứ tự; nếu tiền điều kiện không được công bố, người gọi có thể sử dụng sai dù mã biên dịch được.
5. **Ghi lời hứa mà mã không thực hiện.** Nếu không kiểm tra tính sắp xếp, đừng mô tả API luôn ném ngoại lệ khi mảng lộn xộn. Nếu mã sửa mảng, đừng mô tả nó là bất biến.
6. **Bỏ qua chi phí của bước tiền xử lý.** Xác minh hoặc sắp xếp dữ liệu trước tìm kiếm làm thay đổi độ phức tạp tổng; cần tính trên cả quy trình thực tế.
7. **Chỉ thử trường hợp điển hình.** Thiếu mảng rỗng, một phần tử, cực trị, trùng lặp và không tìm thấy sẽ che giấu những lỗi biên.
8. **Nhầm tính đúng bộ phận với kết thúc.** Bất biến giải thích tính đúng của kết quả tại điểm dừng; vẫn cần chỉ ra tiến độ làm vòng lặp chấm dứt.

## 8. Danh sách tự kiểm trước khi triển khai

- Mỗi đầu vào đã có kiểu, miền, kích thước, quy ước và điều kiện hợp lệ rõ ràng?
- Mỗi giá trị đầu ra có ý nghĩa duy nhất, bao gồm không có lời giải và nhiều đáp án?
- Hậu điều kiện có thể bác bỏ một đáp án sai, hay chỉ lặp lại lời yêu cầu bằng từ ngữ chung chung?
- Trường hợp rỗng, null, trùng, cực trị và vi phạm tiền điều kiện đã được định nghĩa?
- Tác động phụ và phần dữ liệu phải giữ nguyên đã được chốt?
- Ràng buộc thời gian/bộ nhớ có ghi đầy đủ giả định và chi phí tiền xử lý?
- Có ít nhất một ví dụ đối chứng cho từng nhánh chính, và có cách kiểm tra thuộc tính tổng quát?
- Chữ ký, mã, thông báo lỗi, kiểm thử và tài liệu API có tuân thủ cùng một hợp đồng?

Một hợp đồng tốt là **đủ cụ thể để phát hiện kết quả sai**, **đủ rõ để bên gọi sử dụng đúng**, và **đủ độc lập với cài đặt để có thể thay thuật toán mà vẫn giữ nguyên hành vi đã hứa**.