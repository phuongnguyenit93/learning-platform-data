# Tính đúng, hiệu quả và giới hạn tài nguyên của thuật toán

Một thuật toán hữu ích phải trả lời được ba câu hỏi: **kết quả có đúng không, cần bao nhiêu công sức để tạo ra kết quả và có chạy được trong giới hạn thực tế không?** Ba câu hỏi liên quan với nhau nhưng cần được đánh giá riêng. Thuật toán rất nhanh mà trả kết quả sai vẫn vô dụng; thuật toán đúng về mặt toán học nhưng dùng quá nhiều thời gian hoặc bộ nhớ cũng có thể không đáp ứng được bài toán.

Trong bản đồ học thuật toán, đây là bộ tiêu chí để **đọc, so sánh, lựa chọn và kiểm chứng** bất kỳ cách giải nào. Ta sẽ dùng bài toán tìm một giá trị trong mảng để nhìn rõ từng tiêu chí.

## 1. Phát biểu bài toán và hợp đồng đầu vào–đầu ra

Trước khi hỏi thuật toán nhanh đến đâu, hãy xác định chính xác:

- **Đầu vào:** dữ liệu gì, kích thước bao nhiêu, có thể rỗng hoặc chứa giá trị trùng nhau không?
- **Điều kiện trước (precondition):** dữ liệu bắt buộc thỏa mãn điều gì, chẳng hạn mảng đã được sắp tăng dần?
- **Đầu ra và điều kiện sau (postcondition):** trả về kết quả nào được xem là đúng?
- **Ràng buộc:** giới hạn thời gian, bộ nhớ, độ lớn số nguyên, số lần truy vấn, cách đọc/ghi dữ liệu và môi trường chạy.

Ví dụ, với mảng `[2, 5, 9, 13, 21, 34]` và giá trị cần tìm `21`, kết quả `4` là vị trí đúng theo chỉ số bắt đầu từ 0. Nếu không tìm thấy thì trả `-1`. Nếu mảng chứa các phần tử trùng nhau, hợp đồng phải nói rõ **trả về một vị trí bất kỳ** hay **vị trí đầu tiên**; hai yêu cầu dẫn đến những cách cài đặt khác nhau.

Không nên tự ý giả định một điều kiện chưa được đề bài bảo đảm. Tìm kiếm nhị phân chỉ đúng trên dãy **đã sắp xếp theo cùng thứ tự so sánh** mà thuật toán sử dụng.

## 2. Tính đúng: đúng kết quả và chắc chắn kết thúc

Một cách giải được xem là **đúng hoàn toàn (total correctness)** khi, với mọi đầu vào thỏa điều kiện trước:

1. Nếu thuật toán kết thúc thì đầu ra thỏa điều kiện sau (**tính đúng từng phần**, partial correctness).
2. Thuật toán **thực sự kết thúc** sau hữu hạn bước.

Hai vế đều quan trọng: một vòng lặp mãi mãi không trở nên đúng chỉ vì những trạng thái trung gian của nó hợp lý.

### Cách lập luận có thể kiểm tra

Với chương trình lặp, một công cụ quan trọng là **bất biến vòng lặp (loop invariant)**: mệnh đề luôn đúng ở đầu mỗi lần lặp. Chứng minh nó bằng ba bước:

1. **Khởi tạo:** bất biến đúng trước lần lặp đầu tiên.
2. **Duy trì:** nếu đúng ở đầu một lần lặp, sau khi thực hiện thân vòng lặp nó vẫn đúng ở lần kế tiếp.
3. **Kết thúc:** khi điều kiện lặp sai, kết hợp bất biến với trạng thái kết thúc để suy ra kết quả đáp ứng yêu cầu.

Để chứng minh vòng lặp dừng, thường xác định một đại lượng không âm (chẳng hạn độ dài khoảng đang xét) **giảm nghiêm ngặt** ở mỗi lần lặp mà chưa trả kết quả.

Với đệ quy, cách nhìn tương tự là: có **trường hợp cơ sở**, lời gọi tiếp theo tiến gần hơn đến trường hợp đó, và phép kết hợp kết quả của các bài toán con vẫn đúng. Quy nạp toán học thường được dùng để chứng minh tính đúng của thuật toán đệ quy.

### Ví dụ chạy được bằng Java 17+

Chương trình sau có hai phương pháp tìm kiếm. `linearSearch` không cần mảng sắp xếp; `binarySearch` yêu cầu mảng tăng dần hoặc không giảm. Cả hai trả về chỉ số khớp bất kỳ, hoặc `-1` khi không tìm thấy.

```java
public final class SearchQuality {
    static int linearSearch(int[] a, int target) {
        for (int i = 0; i < a.length; i++) {
            if (a[i] == target) {
                return i;
            }
        }
        return -1;
    }

    // Điều kiện trước: a != null và a đã sắp xếp không giảm.
    static int binarySearch(int[] a, int target) {
        int left = 0;
        int right = a.length; // Khoảng đang xét là [left, right).

        while (left < right) {
            int mid = left + (right - left) / 2;

            if (a[mid] < target) {
                left = mid + 1;
            } else if (a[mid] > target) {
                right = mid;
            } else {
                return mid;
            }
        }
        return -1;
    }

    public static void main(String[] args) {
        int[] sorted = {2, 5, 9, 13, 21, 34};

        System.out.println("Linear 21: " + linearSearch(sorted, 21));
        System.out.println("Binary 21: " + binarySearch(sorted, 21));
        System.out.println("Binary 8: " + binarySearch(sorted, 8));
        System.out.println("Empty: " + binarySearch(new int[0], 2));

        long pairs = (long) 100_000 * 99_999 / 2;
        System.out.println("Pairs: " + pairs);
    }
}
```

Lưu thành `SearchQuality.java`, rồi chạy:

```bash
javac SearchQuality.java
java SearchQuality
```

Kết quả chuẩn:

```text
Linear 21: 4
Binary 21: 4
Binary 8: -1
Empty: -1
Pairs: 4999950000
```

Dòng `Pairs` minh họa một giới hạn khác: số cặp khác nhau của 100.000 phần tử vượt giá trị lớn nhất của `int`. Ép kiểu `(long)` **trước phép nhân** giúp phép tính diễn ra trên `long`. Tính số cặp bằng công thức là `O(1)`; thực sự duyệt từng cặp vẫn cần số bước bậc `O(n²)`.

### Vì sao tìm kiếm nhị phân trên đây đúng?

Xét khoảng chỉ số **nửa mở** `[left, right)`: lấy `left`, không lấy `right`. Bất biến là: **nếu `target` có trong mảng và chưa được tìm thấy thì vẫn còn ít nhất một vị trí chứa nó trong khoảng đang xét**.

- **Ban đầu:** `[0, a.length)` bao trùm toàn mảng nên bất biến đúng.
- **Nếu `a[mid] < target`:** vì mảng không giảm, mọi phần tử từ `left` đến `mid` đều nhỏ hơn `target`. Loại chúng bằng `left = mid + 1` không bỏ sót đáp án.
- **Nếu `a[mid] > target`:** mọi phần tử từ `mid` đến trước `right` đều lớn hơn `target`. Đặt `right = mid` giữ lại toàn bộ vị trí còn có thể khớp.
- **Nếu bằng nhau:** chỉ số `mid` là kết quả hợp lệ, nên trả về ngay.
- **Khi khoảng rỗng:** nếu chưa trả kết quả thì không còn vị trí có thể chứa `target`; trả `-1` là đúng.

Độ dài `right - left` là số nguyên không âm. Khi vòng lặp còn chạy, `mid` luôn nằm trong khoảng và mỗi nhánh không trả kết quả đều **làm khoảng ngắn đi ít nhất một phần tử**; vì vậy chương trình chắc chắn dừng. Biểu thức `left + (right - left) / 2` còn tránh nguy cơ tràn `int` của phép tính giữa bằng `(left + right) / 2`.

Chứng minh trên **không** khẳng định trả về vị trí đầu tiên nếu có giá trị trùng nhau, và **không** áp dụng cho mảng chưa sắp xếp. Với `a == null`, chương trình ném `NullPointerException`; điều kiện khác `null` đã được nêu trong hợp đồng.

## 3. Hiệu quả: phân tích thời gian và bộ nhớ

**Độ phức tạp thời gian** mô tả số thao tác cơ bản tăng như thế nào khi kích thước đầu vào `n` tăng, dưới một mô hình chi phí xác định. Nó không trực tiếp là số giây. **Độ phức tạp không gian** mô tả mức bộ nhớ sử dụng theo kích thước đầu vào; cần phân biệt **bộ nhớ phụ** do thuật toán cấp thêm với bộ nhớ để chứa chính dữ liệu đầu vào.

Ký hiệu thường gặp:

| Ký hiệu | Ý nghĩa |
|---|---|
| `O(g(n))` | Chặn trên tiệm cận: tốc độ tăng không vượt quá một bội số của `g(n)` khi `n` đủ lớn. |
| `Ω(g(n))` | Chặn dưới tiệm cận. |
| `Θ(g(n))` | Chặn chặt: vừa có chặn trên vừa có chặn dưới cùng bậc. |

Ví dụ, nếu số phép so sánh ở trường hợp xấu nhất tăng tuyến tính theo `n` thì có thể viết `Θ(n)`, và cũng đúng nhưng kém cụ thể hơn nếu chỉ viết `O(n²)`. Khi nói “thuật toán có độ phức tạp `O(n)`”, nên nêu **đang xét thời gian hay bộ nhớ** và **trường hợp nào**.

| Thuật toán tìm kiếm | Điều kiện dữ liệu | Thời gian tốt nhất | Thời gian xấu nhất | Bộ nhớ phụ |
|---|---|---|---|---|
| Tuyến tính | Không cần sắp xếp | `Θ(1)` nếu gặp ngay | `Θ(n)` | `Θ(1)` |
| Nhị phân | Đã sắp xếp không giảm | `Θ(1)` nếu trúng giữa | `Θ(log n)` với `n ≥ 2` | `Θ(1)` (bản lặp) |

Lý do tìm kiếm nhị phân có bậc logarit: mỗi vòng lặp loại đi khoảng một nửa ứng viên; sau `k` lần, số vị trí còn lại cỡ `n / 2^k`, nên chỉ cần khoảng `log₂(n)` bước cho đến khi còn tối đa một vị trí. Cơ số của logarit không thay đổi bậc `O`.

Phân tích cần chỉ rõ tình huống:

- **Trường hợp tốt nhất:** đầu vào thuận lợi nhất, chẳng hạn giá trị ở vị trí đầu tiên.
- **Trường hợp xấu nhất:** số bước lớn nhất trong số đầu vào hợp lệ cùng kích thước, hữu ích để đặt giới hạn.
- **Trung bình:** chỉ có ý nghĩa khi nêu giả định về phân phối đầu vào; không mặc nhiên là “nằm giữa tốt nhất và xấu nhất”.
- **Khấu hao (amortized):** đánh giá chi phí trung bình trên **một chuỗi thao tác** dù một thao tác riêng lẻ đôi khi đắt; ví dụ thêm phần tử vào mảng động thường có chi phí khấu hao `O(1)` dù lúc tăng dung lượng có thể phải sao chép `O(n)` phần tử.

Với cùng một bài toán, phân tích bộ nhớ cũng có nhiều phạm vi. Cả hai hàm tìm kiếm ở trên chỉ dùng vài biến số nguyên nên **bộ nhớ phụ `O(1)`**; nếu tính cả mảng đầu vào đã cho thì tổng dung lượng lưu trữ vẫn phụ thuộc `n`. Một phiên bản tìm kiếm nhị phân đệ quy thường tốn thêm ngăn xếp lời gọi `O(log n)`.

## 4. Đặt độ phức tạp vào giới hạn tài nguyên

Ký hiệu tiệm cận giúp loại những cách giải khó mở rộng, nhưng việc chọn thuật toán phải dựa trên **giới hạn thật** của đề bài và môi trường chạy.

### Thời gian xử lý

Bảng sau chỉ minh họa **bậc tăng của số thao tác** khi `n = 100.000`; đây không phải số mili giây dự báo cho một máy cụ thể.

| Mức tăng giả định | Số thao tác xấp xỉ với `n = 100.000` | Nhận xét |
|---|---:|---|
| `log₂ n` | 17 | Thường rất nhỏ |
| `n` | 100.000 | Thường có thể xử lý nếu mỗi bước đơn giản |
| `n log₂ n` | 1.700.000 | Thường hợp lý với nhiều bài toán trong bộ nhớ |
| `n²` | 10.000.000.000 | Dễ vượt giới hạn thời gian |

Không thể biến con số này thành thời gian chạy chắc chắn bằng một hằng số chung: phép so sánh số nguyên, truy cập đĩa, phân bổ đối tượng, truy vấn mạng và thao tác với chuỗi có chi phí rất khác nhau. Hệ số hằng, khả năng tận dụng bộ nhớ đệm, cách tổ chức dữ liệu và JVM cũng ảnh hưởng lớn. Với đầu vào nhỏ, thuật toán có bậc tăng cao hơn đôi khi vẫn chạy nhanh hơn vì chi phí thiết lập thấp.

### Bộ nhớ và ngăn xếp

- Một `int[]` có `n = 10.000.000` phần tử cần **khoảng 40 MB chỉ cho dữ liệu phần tử** (mỗi `int` 4 byte); còn có phần đầu đối tượng, căn chỉnh, dữ liệu khác và bộ nhớ JVM. Đây là ước tính dung lượng, không phải cam kết bộ nhớ thực tế.
- `int[]` lưu giá trị nguyên trực tiếp; `Integer[]` và nhiều tập hợp chứa đối tượng có thêm chi phí tham chiếu, boxing và quản lý bộ nhớ. Không nên dùng `O(n)` như bằng chứng hai cấu trúc cần số byte gần bằng nhau.
- Đệ quy sâu tiêu thụ ngăn xếp theo độ sâu lời gọi, có thể gây `StackOverflowError` dù heap vẫn còn. Với bài toán có độ sâu rất lớn, cân nhắc bản lặp hoặc một ngăn xếp dữ liệu được kiểm soát rõ.
- Mảng, bảng quy hoạch động, đồ thị và bộ nhớ đệm có thể tăng theo nhiều tham số: chẳng hạn một bảng `n × m` cần `Θ(nm)` ô. Cần tính cả bộ nhớ của cấu trúc dữ liệu, không chỉ bộ nhớ trong hàm chính.

### Giới hạn giá trị số và dữ liệu ngoài bộ nhớ

Một thuật toán có thể đúng về logic nhưng **sai trên kiểu dữ liệu được chọn**. Các phép tính đếm, tổng, tích, chỉ số và kích thước có thể tràn `int`; hãy xác định miền giá trị trung gian và dùng `long` hoặc `BigInteger` khi phù hợp. Đổi sang `long` cũng không bảo đảm mọi phép tính vô hạn an toàn.

Khi dữ liệu vượt RAM, chi phí đọc/ghi và số lần truy cập ổ đĩa có thể quan trọng hơn số phép tính CPU. Khi dữ liệu đến qua mạng, cần xem thêm băng thông, độ trễ, kích thước đầu ra và khả năng xử lý theo luồng. Vì thế “đúng và `O(n)`” chưa đủ để kết luận một phương án chạy được trong ngân sách tài nguyên.

## 5. Chọn cách giải theo toàn bộ chi phí

Giả sử phải tìm một giá trị trong **mảng chưa sắp xếp**:

- **Chỉ tìm một lần:** quét tuyến tính `O(n)` thường hợp lý. Sắp xếp trước rồi tìm nhị phân có thêm chi phí sắp xếp, nên khó đem lại lợi ích.
- **Tìm nhiều lần trên dữ liệu ít thay đổi:** chi phí chuẩn bị cấu trúc tra cứu có thể được bù lại sau nhiều truy vấn. Có thể sắp xếp rồi tìm nhị phân, dùng cấu trúc ánh xạ khi bài toán cho phép, hoặc lựa chọn khác theo nhu cầu bộ nhớ và thứ tự phần tử.
- **Dữ liệu thay đổi thường xuyên:** ngoài thời gian tra cứu, phải tính chi phí chèn, xóa, cập nhật và duy trì bất biến sắp xếp hoặc cấu trúc chỉ mục.
- **Bộ nhớ bị giới hạn:** một cấu trúc tra cứu phụ nhanh hơn có thể không khả thi; đôi khi chấp nhận thêm thời gian để dùng ít bộ nhớ hơn.

Vì vậy, khi so sánh hai phương án, hãy xem **tổng chi phí của toàn quy trình**, bao gồm chuẩn bị dữ liệu, số lần gọi, cập nhật, bộ nhớ, nhập/xuất và yêu cầu chính xác. Không chọn chỉ bằng một ký hiệu `O` riêng lẻ.

### Quy trình đánh giá một thuật toán

1. **Viết hợp đồng:** đầu vào hợp lệ, đầu ra chính xác, các trường hợp biên, điều kiện về thứ tự/dữ liệu trùng.
2. **Chứng minh đúng:** dùng bất biến hoặc quy nạp; chỉ rõ vì sao không bỏ sót đáp án và vì sao thuật toán dừng.
3. **Đếm chi phí:** xác định `n` (hoặc `V`, `E`, `m`...), số vòng lặp/lời gọi, cấp phát và cấu trúc phụ; phân biệt các trường hợp tốt/xấu/trung bình khi cần.
4. **Đối chiếu giới hạn:** thay kích thước tối đa để ước lượng số thao tác và số byte, đồng thời kiểm tra tràn số, đệ quy và đầu vào/đầu ra.
5. **Kiểm thử và đo:** so với một lời giải đối chứng đơn giản trên dữ liệu nhỏ; thử trường hợp biên và dữ liệu lớn có chủ đích; đo trên môi trường gần thực tế nếu hiệu năng là yêu cầu quan trọng.

Kiểm thử giúp phát hiện lỗi nhưng **không thay thế chứng minh** cho mọi đầu vào. Khi kiểm thử hiệu năng trên JVM, cần tránh kết luận từ một lần gọi `System.nanoTime()`: thời gian biên dịch JIT, làm nóng, GC và tối ưu hóa có thể làm lệch số đo; với phép đo vi mô nên dùng công cụ chuyên dụng như JMH. Luôn tách thời gian chuẩn bị dữ liệu khỏi thời gian của thao tác đang so sánh nếu mục tiêu đo yêu cầu như vậy.

## 6. Sai lầm thường gặp và cách tự kiểm tra

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Dùng tìm kiếm nhị phân trên mảng chưa sắp xếp | Có thể trả `-1` dù phần tử có tồn tại | Kiểm tra điều kiện trước; nếu cần, sắp xếp và tính cả chi phí này |
| Chỉ kiểm thử vài ví dụ “đẹp” | Bỏ sót lỗi khi mảng rỗng, 1 phần tử, trùng nhau, vị trí biên | Dùng tập trường hợp biên và so sánh với thuật toán đối chứng |
| Chỉ báo `O(n)` mà không nói đại lượng nào | Dễ nhầm thời gian với bộ nhớ hoặc nhầm trường hợp xấu nhất với trung bình | Ghi rõ kích thước đầu vào, loại tài nguyên và trường hợp |
| Coi `O(log n)` luôn nhanh hơn `O(n)` | Bỏ qua tiền xử lý, dữ liệu chưa sắp và chi phí cố định | Tính toàn bộ quy trình, xét kích thước thực tế |
| Dùng `int` cho số phép kết hợp lớn | Tràn số, kết quả âm hoặc sai âm thầm | Ước lượng giá trị lớn nhất, nâng kiểu trước phép nhân |
| Đệ quy không tiến về trường hợp cơ sở | Lặp vô hạn hoặc tràn ngăn xếp | Chứng minh mỗi bước làm giảm một đại lượng hữu hạn |
| Quên chi phí bộ nhớ của cấu trúc phụ | Vượt heap hoặc bị áp lực GC | Ước lượng byte và đo bộ nhớ thực tế |

Với chương trình tìm kiếm ở trên, một bộ kiểm thử tối thiểu nên gồm: mảng rỗng; một phần tử khớp/không khớp; phần tử đầu/cuối/ở giữa; giá trị không tồn tại; mảng có số âm và có phần tử trùng. Khi kiểm thử ngẫu nhiên trên **mảng đã sắp**, có thể so kết quả tìm thấy/không tìm thấy của `binarySearch` với `linearSearch`; nếu có phần tử trùng, đừng bắt buộc hai hàm trả cùng chỉ số, chỉ cần chỉ số trả về thật sự chứa giá trị cần tìm.

## 7. Tự luyện để kiểm tra cách tư duy

**Bài 1.** Với `n = 100.000`, một vòng lặp xét mọi cặp phần tử khác nhau có khoảng bao nhiêu lượt? Liệu có nên xem nó là giải pháp nhẹ chỉ vì mỗi lượt so sánh mất `O(1)`?

**Gợi ý:** số cặp không thứ tự là `n(n - 1)/2 = 4.999.950.000`; phép tính đếm là hằng số bước nhưng **liệt kê tất cả cặp** vẫn bậc `Θ(n²)`.

**Bài 2.** Vì sao tìm kiếm nhị phân không cần thử lần lượt từng vị trí? Chỉ ra bất biến của khoảng `[left, right)`, đại lượng luôn giảm và điều kiện đầu vào khiến lập luận hợp lệ.

**Gợi ý:** thứ tự không giảm cho phép loại bỏ cả một nửa khoảng sau mỗi so sánh; độ dài khoảng giảm đến 0.

**Bài 3.** Cần tìm 1 giá trị trong mảng chưa sắp xếp, sau đó không dùng mảng nữa. Có nên sắp xếp toàn bộ trước khi tìm nhị phân?

**Gợi ý:** thường không; quét tuyến tính có chi phí `O(n)` mà không cần tiền xử lý. Quyết định có thể đổi khi có rất nhiều truy vấn hoặc dữ liệu đã được sắp sẵn.

**Bài 4.** Một thuật toán duyệt đồ thị có thời gian `O(V + E)`, trong đó `V` là số đỉnh và `E` là số cạnh. Vì sao chỉ ghi `O(n)` mà không nói `n` là gì dễ gây hiểu lầm?

**Gợi ý:** kích thước đồ thị gồm ít nhất hai tham số độc lập; một đồ thị dày đặc có thể có số cạnh lớn hơn nhiều so với số đỉnh.

## Ghi nhớ

**Tính đúng** trả lời “thuật toán có luôn cho đáp án hợp lệ và dừng với mọi đầu vào đúng điều kiện không?”. **Hiệu quả** trả lời “số bước và dung lượng cần thiết tăng thế nào khi bài toán lớn hơn?”. **Giới hạn tài nguyên** trả lời “với kích thước, thời gian, RAM, kiểu số và môi trường cụ thể, phương án có khả thi không?”. Luôn đánh giá cả ba trước khi chọn cách giải.
