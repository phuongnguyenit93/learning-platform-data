# Chọn ứng viên chiếm đa số bằng Boyer–Moore và bước xác minh

## 1. Bài toán: “chiếm đa số” nghĩa là gì?

Cho dãy số nguyên a có n phần tử. Một giá trị m được gọi là **phần tử chiếm đa số** (majority element) khi số lần xuất hiện của m **lớn hơn một nửa** số phần tử:

~~~text
frequency(m, a) > n / 2
~~~

Dấu **>** là nghiêm ngặt. Với n = 7, một giá trị phải xuất hiện ít nhất 4 lần; với n = 6 phải xuất hiện ít nhất 4 lần, vì đúng 3 lần chỉ bằng n/2. Nếu có phần tử chiếm đa số, nó **duy nhất**: hai giá trị khác nhau không thể đồng thời xuất hiện hơn n/2 lần.

Các ví dụ:

| Dãy | n | Kết luận |
| --- | ---: | --- |
| [2, 2, 1, 1, 1, 2, 2] | 7 | 2 xuất hiện 4 lần, chiếm đa số |
| [7, 7, 7] | 3 | 7 xuất hiện 3 lần, chiếm đa số |
| [4] | 1 | 4 xuất hiện 1 lần, chiếm đa số |
| [9, 9, 1, 1] | 4 | Không có đa số: mỗi giá trị xuất hiện 2 lần |
| [1, 2, 3, 3, 4] | 5 | Không có đa số: 3 chỉ xuất hiện 2 lần |
| [] | 0 | Không có phần tử chiếm đa số |

**Đa số không đồng nghĩa với “xuất hiện nhiều nhất”.** Trong [1, 2, 3, 3, 4], số 3 là giá trị xuất hiện nhiều nhất nhưng tần suất 2/5 không vượt 1/2. Phân biệt điều này là điều kiện quan trọng khi thiết kế thuật toán.

Boyer–Moore Majority Vote giải quyết phần chọn **ứng viên có thể chiếm đa số** bằng một biến giá trị và một biến đếm. Nhưng khi đề bài **không bảo đảm chắc chắn có đa số**, cần thêm bước **xác minh ứng viên**; nếu bỏ qua bước này, thuật toán có thể trả sai.

## 2. Hợp đồng đầu vào–đầu ra của lời giải

Ta chọn hợp đồng cho Java 17 như sau:

- Đầu vào là một mảng `int[]` không null, không đòi hỏi sắp xếp; các giá trị âm, 0, trùng nhau đều hợp lệ.
- Mảng rỗng hợp lệ và **không có đa số**.
- Khi một giá trị xuất hiện **nhiều hơn ⌊n/2⌋ lần**, trả về chính giá trị đó.
- Khi không có giá trị nào thỏa điều kiện, trả về một kết quả thể hiện **không tìm thấy**, thay vì trả một ứng viên chưa kiểm chứng.
- Phương thức không sửa mảng đầu vào; bộ nhớ phụ được giới hạn ở một số biến.
- Nếu đầu vào là null, báo lỗi theo hợp đồng; ở ví dụ Java là `NullPointerException`.

Kiểu trả về `OptionalInt` phù hợp hơn một giá trị đặc biệt như `-1`, vì **mọi giá trị int đều có thể là phần tử chiếm đa số**, kể cả `-1` và `Integer.MIN_VALUE`. Với `OptionalInt.empty()`, không có kết quả được phân biệt rõ với một kết quả bằng `-1`.

Thuật toán bao gồm **hai giai đoạn**:

1. **Bầu chọn** một ứng viên trong O(n) thời gian, O(1) bộ nhớ phụ.
2. **Đếm thật** số lần ứng viên xuất hiện và chỉ công nhận nếu vượt n/2.

Nội dung quan trọng nhất cần nhớ: **sau giai đoạn 1, `candidate` chỉ là ứng viên; `votes` không phải tần suất thật**.

## 3. Ý tưởng triệt tiêu từng cặp phần tử khác nhau

Xét một dãy có giá trị m chiếm đa số. Nếu bỏ đi **một cặp gồm hai giá trị khác nhau**, m vẫn chiếm đa số trong phần còn lại, miễn là phần còn lại không rỗng:

- Nếu cặp bị bỏ gồm m và một giá trị khác, số phần tử m và số phần tử không phải m cùng giảm 1.
- Nếu cặp không chứa m, số phần tử m giữ nguyên còn số phần tử không phải m giảm 2.
- Vì trước khi bỏ cặp, số phần tử m lớn hơn tổng số phần tử khác, chênh lệch đó vẫn dương sau mỗi phép loại bỏ.

Ví dụ:

~~~text
Dữ liệu:       2  2  1  1  1  2  2
Số lần 2:      4
Số phần tử khác 2: 3

Có thể triệt tiêu 3 cặp (2, 1).
Cuối cùng vẫn còn ít nhất một số 2.
~~~

Ta không cần thực sự tạo danh sách rồi xóa từng cặp. Boyer–Moore biểu diễn **những phần tử chưa bị triệt tiêu** bằng hai biến:

- `candidate`: giá trị đang đại diện cho phần chưa triệt tiêu.
- `votes`: số bản sao chưa bị triệt tiêu của `candidate`, **không phải tổng số lần candidate đã xuất hiện trong dãy**.

Với mỗi phần tử x:

- Nếu `votes == 0`, đặt `candidate = x` và `votes = 1`: bắt đầu một nhóm ứng viên mới.
- Nếu x bằng `candidate`, tăng `votes`: có thêm một bản sao cùng giá trị.
- Nếu x khác `candidate`, giảm `votes`: triệt tiêu một bản sao ứng viên với x.

Khi `votes` trở thành 0, những phần tử của phần đã xử lý có thể ghép thành các cặp khác giá trị theo cách diễn giải của thuật toán. Biến `candidate` lúc ấy có thể còn chứa giá trị cũ nhưng **không có ứng viên đang được giữ lại**; phần tử kế tiếp sẽ chọn lại ứng viên.

Đây là ý tưởng “bỏ phiếu” chứ không phải “đếm phiếu” theo nghĩa tần suất từng giá trị. Phép triệt tiêu giữ được **ứng viên bắt buộc** nếu đa số thực sự tồn tại.

## 4. Giai đoạn 1: chọn ứng viên

Mã giả, áp dụng cho một dãy không rỗng:

~~~text
candidate = 0        // giá trị khởi tạo tùy ý, chưa có nghĩa
votes = 0

for each x in a:
    if votes == 0:
        candidate = x
        votes = 1
    else if x == candidate:
        votes = votes + 1
    else:
        votes = votes - 1

// candidate là ứng viên, chưa phải đáp án cuối cùng
~~~

Giá trị khởi tạo `candidate = 0` không gây nhầm lẫn với phần tử 0 thật, vì khi `votes == 0`, giá trị candidate cũ được bỏ qua và thay bằng phần tử hiện tại.

### Truy vết khi có đa số

Với a = [2, 2, 1, 1, 1, 2, 2]:

| Vị trí i | x | Thao tác | candidate sau bước | votes sau bước |
| ---: | ---: | --- | ---: | ---: |
| 0 | 2 | Đặt ứng viên mới | 2 | 1 |
| 1 | 2 | Cùng ứng viên, tăng | 2 | 2 |
| 2 | 1 | Khác ứng viên, giảm | 2 | 1 |
| 3 | 1 | Khác ứng viên, giảm | 2 | 0 |
| 4 | 1 | Đặt ứng viên mới | 1 | 1 |
| 5 | 2 | Khác ứng viên, giảm | 1 | 0 |
| 6 | 2 | Đặt ứng viên mới | 2 | 1 |

Kết thúc giai đoạn 1, `candidate = 2` và `votes = 1`. Trong toàn mảng, 2 xuất hiện **4 lần**, không phải 1 lần. Vì vậy, **không được dùng `votes` để kiểm tra có đa số**.

### Truy vết khi không có đa số

Với a = [1, 2, 3, 3, 4]:

| Vị trí i | x | candidate sau bước | votes sau bước |
| ---: | ---: | ---: | ---: |
| 0 | 1 | 1 | 1 |
| 1 | 2 | 1 | 0 |
| 2 | 3 | 3 | 1 |
| 3 | 3 | 3 | 2 |
| 4 | 4 | 3 | 1 |

Thuật toán trả ứng viên 3 với `votes = 1`, nhưng trong dãy gốc số 3 chỉ xuất hiện 2 lần. Điều kiện đa số cho n = 5 yêu cầu xuất hiện **ít nhất 3 lần**. Nếu trả ngay candidate, kết quả sẽ sai.

## 5. Giai đoạn 2: xác minh ứng viên

Sau khi đã chọn `candidate`, duyệt lại chính mảng đầu vào để tính **số lần xuất hiện thật** của giá trị ấy:

~~~text
count = 0

for each x in a:
    if x == candidate:
        count = count + 1

if count > floor(n / 2):
    return candidate
else:
    return "không có đa số"
~~~

Với n nguyên không âm, phép chia nguyên `n / 2` trong Java có giá trị ⌊n/2⌋; vì thế `count > n / 2` biểu diễn chính xác điều kiện đa số. Cách này còn tránh phép nhân `2 * count`, vốn có thể tràn kiểu int khi dữ liệu cực lớn.

**Không kiểm tra `votes > 0` thay cho xác minh.** Dãy [1, 2, 3, 3, 4] đã cho thấy `votes > 0` dù không có đa số. Cũng không được kiểm tra `count >= n / 2`: với [9, 9, 1, 1], count của 9 bằng 2, n/2 bằng 2, nhưng không có đa số.

Nếu n = 0, không có ứng viên có nghĩa; có thể trả “không có đa số” ngay trước vòng bầu chọn. Nếu n > 0 nhưng không có đa số, bước 2 sẽ loại ứng viên bất kể nó là giá trị nào.

Hai giai đoạn giải quyết hai bài toán logic khác nhau:

| Giai đoạn | Đầu ra | Điều đã chứng minh |
| --- | --- | --- |
| Bầu chọn | Một giá trị ứng viên | **Nếu** tồn tại đa số, giá trị đa số phải là ứng viên |
| Xác minh | Đa số hoặc không có đa số | Ứng viên có thực sự xuất hiện hơn n/2 lần trong dữ liệu gốc hay không |

Mệnh đề “nếu có đa số thì ứng viên đúng” **không kéo theo** “ứng viên luôn là đa số”. Bước xác minh là điều kiện không thể bỏ qua khi đầu vào không được bảo đảm có đa số.

## 6. Chứng minh tính đúng bằng bất biến triệt tiêu

Ta chứng minh riêng hai phần.

### 6.1. Bất biến của lượt bầu chọn

Sau khi đọc xong một tiền tố bất kỳ của mảng, có thể chia toàn bộ các phần tử đã đọc thành:

1. Một tập các **cặp gồm hai giá trị khác nhau** đã triệt tiêu.
2. Một nhóm gồm đúng `votes` phần tử chưa triệt tiêu, tất cả đều bằng `candidate` nếu `votes > 0`; nhóm này rỗng khi `votes == 0`.

Ban đầu chưa đọc phần tử nào, nhóm chưa triệt tiêu rỗng và bất biến đúng.

Giả sử bất biến đúng trước khi đọc x:

- Nếu nhóm rỗng, thêm x vào nhóm mới, ứng viên trở thành x, `votes = 1`.
- Nếu x bằng ứng viên, tăng kích thước nhóm thêm một, bất biến vẫn đúng.
- Nếu x khác ứng viên, ghép x với một phần tử ứng viên trong nhóm thành một cặp khác giá trị, rồi giảm `votes` đi một. Phần nhóm còn lại vẫn toàn ứng viên.

Như vậy, bất biến được duy trì qua từng phần tử.

### 6.2. Nếu đa số tồn tại, nó phải là ứng viên

Giả sử m xuất hiện M lần trong n phần tử với M > n/2, hay M > n − M. Trước khi triệt tiêu, số bản sao m **lớn hơn** tổng số phần tử khác m.

Trong mỗi cặp bị loại, có nhiều nhất một m. Nếu cặp chứa m thì nó cũng phải chứa một phần tử khác m, nên khoảng chênh lệch giữa số m và số không phải m không giảm. Nếu cặp không chứa m, khoảng chênh lệch tăng. Do đó, sau khi triệt tiêu các cặp khác giá trị, ít nhất một phần tử m còn lại.

Theo bất biến, toàn bộ các phần tử còn lại phải bằng nhau và bằng `candidate`. Vì có phần tử m còn lại, suy ra `candidate = m`. Vậy nếu dữ liệu có đa số thì lượt bầu chọn không thể loại mất giá trị đó.

Lập luận trên **không** chứng minh ứng viên là đa số khi không có đa số. Trong trường hợp ấy, các phần tử khác nhau cũng có thể bị triệt tiêu để lại một giá trị bất kỳ. Bước 2 kiểm tra đúng điều kiện gốc và loại tất cả ứng viên không đạt ngưỡng.

### 6.3. Tính đúng của thuật toán hoàn chỉnh

- **Nếu thuật toán trả giá trị m:** lượt xác minh đã đếm đủ các vị trí và xác nhận số lần m xuất hiện > n/2. Do đó m thực sự là đa số.
- **Nếu dữ liệu có đa số m:** chứng minh bầu chọn bảo đảm candidate = m; lượt xác minh sẽ đếm được hơn n/2 và trả m.
- **Nếu dữ liệu không có đa số:** mọi giá trị đều xuất hiện không quá n/2 lần, nên ứng viên không qua được lượt xác minh; thuật toán báo không có đa số.

Vòng bầu chọn và vòng đếm đều duyệt hữu hạn n phần tử, nên thuật toán kết thúc. Ba mệnh đề trên chứng minh tính đúng cho mọi đầu vào hợp lệ, kể cả khi không có đa số.

## 7. Chương trình Java 17+ độc lập

Chương trình dưới đây dùng `OptionalInt` để phân biệt một giá trị đa số với trường hợp không có kết quả. Nó xử lý mảng rỗng, không sửa mảng, và không dùng giá trị sentinel xung đột với dữ liệu.

Lưu tệp tên **MajorityVoteExample.java**:

~~~java
import java.util.Arrays;
import java.util.Objects;
import java.util.OptionalInt;

public final class MajorityVoteExample {
    private MajorityVoteExample() {}

    /**
     * Returns the value occurring more than floor(n / 2) times.
     * Returns OptionalInt.empty() when no majority exists, including
     * for an empty array. Null input throws NullPointerException.
     * The input array is not modified.
     */
    public static OptionalInt majority(int[] values) {
        Objects.requireNonNull(values, "values");

        if (values.length == 0) {
            return OptionalInt.empty();
        }

        // Phase 1: select a candidate by cancelling unequal pairs.
        int candidate = 0;
        int votes = 0;

        for (int value : values) {
            if (votes == 0) {
                candidate = value;
                votes = 1;
            } else if (value == candidate) {
                votes++;
            } else {
                votes--;
            }
        }

        // Phase 2: verify the candidate's actual frequency.
        int actualCount = 0;
        for (int value : values) {
            if (value == candidate) {
                actualCount++;
            }
        }

        if (actualCount > values.length / 2) {
            return OptionalInt.of(candidate);
        }
        return OptionalInt.empty();
    }

    private static void show(int[] values) {
        OptionalInt result = majority(values);
        String answer = result.isPresent()
                ? Integer.toString(result.getAsInt())
                : "none";
        System.out.println(Arrays.toString(values)
                + " -> majority=" + answer);
    }

    public static void main(String[] args) {
        show(new int[] {2, 2, 1, 1, 1, 2, 2});
        show(new int[] {1, 2, 3, 3, 4});
        show(new int[] {9, 9, 1, 1});
        show(new int[] {-3, -3, 1, -3});
        show(new int[] {7});
        show(new int[] {});

        try {
            majority(null);
        } catch (NullPointerException ex) {
            System.out.println("null -> NullPointerException");
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac MajorityVoteExample.java
java MajorityVoteExample
~~~

Stdout chính xác:

~~~text
[2, 2, 1, 1, 1, 2, 2] -> majority=2
[1, 2, 3, 3, 4] -> majority=none
[9, 9, 1, 1] -> majority=none
[-3, -3, 1, -3] -> majority=-3
[7] -> majority=7
[] -> majority=none
null -> NullPointerException
~~~

**Diễn giải:** dãy đầu có 4 số 2 trên 7 phần tử; hai dãy kế tiếp không có giá trị nào vượt n/2; số âm vẫn là ứng viên hợp lệ; mảng một phần tử luôn có đa số; mảng rỗng trả OptionalInt rỗng; null bị `Objects.requireNonNull` từ chối.

Hai vòng for đều là một lượt tuyến tính. Phần `main` còn dùng `Arrays.toString` để **in toàn bộ mảng** phục vụ minh họa; chi phí tạo chuỗi và in console không nằm trong phép phân tích chi phí riêng của phương thức `majority`.

## 8. Phân tích độ phức tạp và khả năng xử lý luồng

Với n phần tử:

| Công đoạn | Thời gian | Bộ nhớ phụ |
| --- | --- | --- |
| Chọn ứng viên | Θ(n) | Θ(1) |
| Xác minh bằng cách đếm | Θ(n) | Θ(1) |
| Toàn bộ phương thức | Θ(n) | Θ(1) |

Hai lượt n + n có tổng chi phí Θ(n), không phải Θ(n²). Đếm số biến `candidate`, `votes`, `actualCount` không phụ thuộc n, nên bộ nhớ phụ là hằng số. Phương thức đọc mảng đã cung cấp, không sao chép hoặc sắp xếp dữ liệu.

**Tuyên bố O(1) bộ nhớ phụ không có nghĩa chỉ đọc dữ liệu một lần.** Bản cài đặt phải duyệt lại mảng để xác minh. Nếu nguồn dữ liệu chỉ là luồng một chiều không cho đọc lại, cần có cơ chế **phát lại**, lưu dữ liệu ở nơi khác, hoặc thay đổi bài toán/giả định. Chỉ giữ hai biến candidate và votes trong một luồng tùy ý không đủ để bảo đảm báo đúng việc có hay không có đa số sau một lần đọc.

Nếu đề bài **bảo đảm từ trước rằng có phần tử đa số**, có thể trả ứng viên ngay sau lượt 1. Đó là hợp đồng khác, và người dùng phải thật sự tin được giả định. Nếu không có bảo đảm, bỏ bước xác minh biến kết quả thành một phỏng đoán.

### So sánh với các cách khác

| Cách tiếp cận | Thời gian điển hình | Bộ nhớ phụ | Điểm cần lưu ý |
| --- | --- | --- | --- |
| Đếm tần suất bằng HashMap | O(n) kỳ vọng | O(k) với k giá trị phân biệt | Cho biết tần suất thật, cần không gian cho các khóa |
| Sắp xếp và kiểm tra phần tử giữa | O(n log n) với sort so sánh | Phụ thuộc cách sắp xếp | Có thể làm đổi thứ tự; phải xác minh ứng viên giữa |
| Boyer–Moore + xác minh | Θ(n) | Θ(1) | Không cần sắp xếp, hai lượt, đúng với giá trị nguyên bất kỳ |

Ở cách sắp xếp, nếu có đa số thì giá trị đó chắc chắn chiếm phần tử ở vị trí giữa của dãy đã sắp xếp; tuy nhiên giá trị ở giữa **không mặc nhiên là đa số**, nên cũng phải xác minh. Muốn bảo toàn mảng ban đầu phải tạo bản sao hoặc dùng cách khác và tính thêm chi phí bản sao.

## 9. Trường hợp biên, rủi ro và lỗi phổ biến

1. **Quên lượt xác minh.** Với [1, 2, 3, 3, 4], candidate bằng 3 nhưng tần suất chỉ là 2/5; trả 3 ngay sẽ sai.
2. **Dùng `votes` làm `actualCount`.** Vote phản ánh phần chưa triệt tiêu, không đếm mọi lần xuất hiện; ví dụ [2, 2, 1, 1, 1, 2, 2] cho votes=1 dù frequency(2)=4.
3. **Dùng điều kiện `>= n/2`.** “Chiếm đa số” phải **lớn hơn** n/2, không phải bằng. Với n chẵn, chính xác n/2 lần không đủ.
4. **Nhầm phần tử phổ biến nhất với đa số.** Một giá trị có tần suất cao nhất vẫn có thể không vượt ngưỡng 50%.
5. **Không xử lý mảng rỗng.** Không có một phần tử nào để làm candidate có nghĩa. Chọn trả rỗng hoặc báo lỗi theo hợp đồng; ví dụ chọn `OptionalInt.empty()`.
6. **Chọn `-1` làm dấu “không có kết quả”.** `-1` có thể là đa số hợp lệ; dùng `OptionalInt` để không nhầm lẫn.
7. **Không phân biệt null với rỗng.** null là tham chiếu không có mảng, còn [] là mảng hợp lệ có 0 phần tử; hai trường hợp có chính sách khác nhau trong ví dụ.
8. **Khởi tạo `candidate = 0` rồi bỏ qua `votes == 0`.** Khi chưa có ứng viên, phải lấy phần tử thực làm candidate. 0 ban đầu chỉ là giá trị placeholder nội bộ.
9. **Cho rằng dữ liệu phải sắp xếp.** Boyer–Moore Majority Vote không cần thứ tự, có thể xử lý các giá trị âm và trùng lặp.
10. **Tuyên bố “một lượt” cho thuật toán có xác minh.** Lượt bầu chọn là một lượt; lời giải hoàn chỉnh cho đầu vào bất kỳ ở đây có **hai lượt**, dù vẫn Θ(n).
11. **Sửa mảng trong lúc kiểm tra.** Lượt đếm phải kiểm tra chính tập giá trị được dùng để bầu chọn; nếu dữ liệu bị thay đổi giữa hai lượt, kết quả không còn bảo đảm theo hợp đồng. Bên gọi phải bảo đảm mảng ổn định trong suốt lời gọi.
12. **Lẫn thuật toán Majority Vote với Boyer–Moore tìm chuỗi.** Hai kỹ thuật cùng mang tên Boyer và Moore nhưng giải bài toán khác nhau: bài này chọn phần tử đa số, còn thuật toán tìm chuỗi xử lý so khớp mẫu trong văn bản.

Một cách đơn giản để tự kiểm tra logic: nếu không biết chắc dãy có đa số hay không, mọi giải pháp chỉ trả một giá trị từ dữ liệu mà **không có bước hoặc thông tin xác minh tần suất**, đều cần được xem xét lại.

## 10. Bộ kiểm thử theo hợp đồng

Các trường hợp nên kiểm thử gồm:

| Đầu vào | Đầu ra dự kiến | Mục tiêu kiểm thử |
| --- | --- | --- |
| [] | empty | Dãy rỗng |
| [5] | 5 | Một phần tử |
| [3, 3, 3, 3] | 3 | Tất cả bằng nhau |
| [2, 2, 1, 1, 1, 2, 2] | 2 | Đa số chỉ hơn n/2 một lần |
| [1, 2, 3, 3, 4] | empty | Candidate có thể tồn tại nhưng không phải đa số |
| [9, 9, 1, 1] | empty | Bằng đúng n/2 là không đủ |
| [-3, -3, 1, -3] | -3 | Giá trị âm là đa số |
| [-1, -1, 8] | -1 | Không nhầm -1 với “không có kết quả” |
| [Integer.MIN_VALUE, 0, Integer.MIN_VALUE] | Integer.MIN_VALUE | Giá trị biên kiểu int |
| null | NullPointerException | Đầu vào không hợp lệ |

Ngoài các ví dụ cố định, có thể tạo nhiều mảng ngắn và dùng một lời giải chậm nhưng dễ kiểm chứng làm **oracle**:

~~~text
oracle(a):
    if a rỗng:
        return "không có đa số"
    với mỗi giá trị x khác nhau trong a:
        đếm số lần x xuất hiện trong toàn a
        nếu count(x) > floor(n / 2):
            return x
    return "không có đa số"
~~~

Trên các mảng ngắn, oracle có thể dùng hai vòng lặp lồng nhau với O(n²) thời gian để tránh phụ thuộc vào cùng một cách giải. So sánh đầu ra oracle với Boyer–Moore trên các mảng sinh ngẫu nhiên nhỏ. Vì phần tử đa số là duy nhất nếu tồn tại, hai lời giải phải khớp giá trị và cùng báo không có kết quả trong mọi trường hợp còn lại.

Các **tính chất** cũng cần giữ:

- Khi kết quả có mặt, tần suất thật của giá trị trả về luôn **> n/2**.
- Khi không có kết quả, mọi giá trị xuất hiện **≤ n/2** lần.
- Hoán vị các phần tử trong dãy không làm thay đổi kết quả cuối cùng (giá trị đa số hoặc không có đa số), dù candidate và votes trung gian có thể thay đổi.
- Hai lượt không thay đổi nội dung mảng.
- Kết quả đúng với mọi số nguyên 32-bit; không cần giá trị sentinel.

Lưu ý: chạy được vài test không phải là chứng minh tính đúng với mọi n. Bất biến triệt tiêu ở mục 6 giải thích tính đúng tổng quát; bộ kiểm thử giúp phát hiện lỗi cài đặt hoặc sai khác giữa code và hợp đồng.

## 11. Cách áp dụng và checklist

Khi gặp bài toán “tìm phần tử xuất hiện quá nửa” hoặc “majority element”, có thể làm theo quy trình:

1. Xác định ngưỡng chính xác là **> n/2** và kiểm tra đề bài có **bảo đảm tồn tại** đa số hay không.
2. Chốt chính sách mảng rỗng, null, các giá trị có thể xuất hiện và kiểu kết quả khi không tìm thấy.
3. Bầu chọn bằng `candidate` và `votes` theo quy tắc triệt tiêu một cặp khác nhau khi gặp giá trị trái ứng viên.
4. Khi lượt đầu kết thúc, chỉ gọi giá trị nhận được là **ứng viên**.
5. Nếu không có bảo đảm tồn tại đa số, đếm chính xác số lần xuất hiện của ứng viên trong **cùng dữ liệu** và chỉ trả ứng viên khi `count > n / 2`.
6. Kiểm thử cả trường hợp có đa số, không có đa số, đúng bằng một nửa, giá trị âm và mảng rỗng.
7. Ghi rõ chi phí thực tế: **hai lượt Θ(n), bộ nhớ phụ Θ(1)** cho lời giải hoàn chỉnh khi dữ liệu là mảng có thể đọc lại.

**Điểm mấu chốt:** Boyer–Moore Majority Vote dùng triệt tiêu các cặp giá trị khác nhau để tìm ra ứng viên bắt buộc nếu đa số tồn tại. **Lượt xác minh biến ứng viên đó thành kết luận đúng**, kể cả khi dãy không có phần tử nào chiếm đa số.
