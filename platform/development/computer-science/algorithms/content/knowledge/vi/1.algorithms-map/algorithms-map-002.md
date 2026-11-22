# Đầu vào, đầu ra, bước xử lý và điều kiện kết thúc

Một thuật toán là một dãy chỉ dẫn xác định nhằm giải một bài toán. Để hiểu hoặc thiết kế thuật toán, trước tiên cần trả lời bốn câu hỏi: **thuật toán nhận gì, phải tạo ra gì, biến đổi dữ liệu như thế nào và khi nào chắc chắn dừng**. Bốn thành phần này là khung cơ bản để đọc giả mã, vẽ lưu đồ, viết chương trình và kiểm tra tính đúng đắn.

## 1. Bản đồ bốn thành phần

| Thành phần | Câu hỏi phải trả lời | Ví dụ: tìm một số trong mảng |
| --- | --- | --- |
| **Đầu vào (input)** | Dữ liệu ban đầu là gì, kiểu và điều kiện hợp lệ ra sao? | Mảng số nguyên `values` và số cần tìm `target`. |
| **Đầu ra (output)** | Kết quả nào được coi là đúng; xử lý trường hợp không có kết quả thế nào? | Vị trí xuất hiện đầu tiên của `target`, hoặc `-1` nếu không thấy. |
| **Bước xử lý (processing steps)** | Những thao tác nào được thực hiện, theo thứ tự và điều kiện nào? | Kiểm tra lần lượt các phần tử từ trái sang phải. |
| **Điều kiện kết thúc (termination)** | Sự kiện nào làm thuật toán dừng, và vì sao nó không lặp vô hạn? | Tìm thấy phần tử hoặc đã kiểm tra hết mảng. |

Bốn thành phần phải khớp nhau. Chẳng hạn, nếu đầu ra yêu cầu **vị trí đầu tiên**, một thuật toán trả về vị trí xuất hiện cuối cùng dù vẫn tìm đúng giá trị là **sai đặc tả**. Nếu các bước có thể lặp mãi, chưa thể khẳng định thuật toán hoàn tất trên mọi đầu vào hợp lệ.

## 2. Đầu vào: xác định rõ dữ liệu và miền hợp lệ

Đầu vào là thông tin thuật toán cần để bắt đầu. Nó có thể được truyền qua tham số hàm, đọc từ tệp, lấy từ bộ nhớ hoặc cảm biến; **không nhất thiết** phải được nhập bằng bàn phím.

Khi mô tả đầu vào, hãy nêu:

- **Kiểu và cấu trúc:** số nguyên, chuỗi, mảng, đồ thị, danh sách, v.v.
- **Ràng buộc hợp lệ (tiền điều kiện):** ví dụ, mảng không phải `null`, kích thước không âm, dữ liệu đã sắp xếp nếu dùng tìm kiếm nhị phân.
- **Trường hợp biên:** đầu vào rỗng, một phần tử, trùng lặp, giá trị âm, dữ liệu rất lớn.
- **Khả năng thay đổi:** thuật toán có được sửa trực tiếp đầu vào hay phải giữ nguyên?

Với bài toán `firstIndexOf(values, target)`, ta quy định `values` là mảng `int` **khác `null`**, có thể rỗng; `target` là một số `int` bất kỳ. Mảng không cần sắp xếp. Việc truyền `null` là vi phạm tiền điều kiện và chương trình minh họa sẽ báo lỗi rõ ràng.

Một đặc tả thiếu ràng buộc dễ dẫn đến cách cài đặt sai: tìm kiếm nhị phân chỉ đúng khi dữ liệu tuân thủ điều kiện sắp xếp, còn tìm kiếm tuần tự không cần điều kiện ấy.

## 3. Đầu ra: xác định chính xác ý nghĩa của kết quả

Đầu ra là kết quả thuật toán cam kết cung cấp. Nó có thể là một giá trị, một tập dữ liệu, một trạng thái được cập nhật hoặc một hành động có thể quan sát. **In ra màn hình chỉ là một cách trình bày đầu ra**, không phải định nghĩa duy nhất của nó.

Trong bài toán tìm vị trí đầu tiên:

- Nếu `target` có trong mảng, trả về chỉ số nhỏ nhất `k` sao cho `values[k] == target`. Chỉ số bắt đầu từ `0`.
- Nếu không có phần tử phù hợp, trả về `-1`. Quy ước này không mơ hồ vì chỉ số mảng hợp lệ không âm.
- Thuật toán không thay đổi các phần tử của `values`.

Đây là **hậu điều kiện**: với kết quả `k >= 0`, phải có `values[k] == target` và mọi vị trí trước `k` đều khác `target`; với kết quả `-1`, không có phần tử nào bằng `target`.

Viết được hậu điều kiện giúp phân biệt kết quả “có vẻ hợp lý” với kết quả thật sự đúng yêu cầu. Nếu miền kết quả hợp lệ cũng chứa `-1`, cần một cơ chế báo “không tìm thấy” khác (ví dụ kiểu kết quả có cờ trạng thái).

## 4. Bước xử lý: diễn đạt thành chuỗi thao tác có thể thực hiện

Một bước xử lý nên **rõ ràng, hữu hạn và xác định**: đọc dữ liệu nào, kiểm tra điều kiện gì, cập nhật trạng thái ra sao và chuyển sang bước nào. Các cấu trúc cơ bản là **tuần tự**, **rẽ nhánh** và **lặp**.

Với tìm kiếm tuần tự, các bước là:

1. Đặt chỉ số `i = 0`: bắt đầu ở phần tử đầu tiên.
2. Nếu `i < values.length`, so sánh `values[i]` với `target`.
3. Nếu bằng nhau, trả về `i` ngay; do đã quét từ trái sang phải, đó là vị trí đầu tiên.
4. Nếu khác nhau, tăng `i` lên `1` và quay lại bước 2.
5. Nếu `i == values.length`, nghĩa là đã xét hết mảng mà chưa thấy, trả về `-1`.

Có thể mô tả độc lập với ngôn ngữ lập trình bằng giả mã:

```text
firstIndexOf(values, target):
    yêu cầu values là mảng hợp lệ, khác null
    i <- 0
    while i < length(values):
        if values[i] == target:
            return i
        i <- i + 1
    return -1
```

Giả mã làm rõ logic; nó không phải chương trình Java để biên dịch trực tiếp. Trạng thái `i` liên kết các bước với nhau: mỗi lần chưa tìm thấy, nó ghi nhận thêm một vị trí đã kiểm tra.

### Theo dõi một lần chạy

Cho `values = [4, 9, 2, 9]` và `target = 2`:

| Lần kiểm tra | `i` | `values[i]` | Kết quả |
| --- | ---: | ---: | --- |
| 1 | 0 | 4 | Khác 2; tăng `i` thành 1. |
| 2 | 1 | 9 | Khác 2; tăng `i` thành 2. |
| 3 | 2 | 2 | Bằng 2; trả về `2` và dừng. |

Nếu đổi `target = 7`, vòng lặp duyệt đủ bốn phần tử, sau đó `i = 4`; điều kiện `i < 4` sai và hàm trả `-1`.

## 5. Điều kiện kết thúc: có điểm dừng và có tiến triển

**Điều kiện tiếp tục lặp** khác với **điều kiện kết thúc cả thuật toán**. Trong ví dụ, `i < values.length` cho biết khi nào còn phần tử để xét. Hàm có hai đường kết thúc hợp lệ:

1. **Tìm thấy:** `return i` kết thúc hàm ngay, kể cả khi mảng còn phần tử chưa xét.
2. **Duyệt hết:** `i` đạt `values.length`; vòng lặp kết thúc rồi `return -1`.

Nêu được một điều kiện dừng chưa đủ; phải giải thích vì sao sẽ đến được điều kiện đó. Với mảng hữu hạn có độ dài `n`, ở đầu mỗi vòng lặp `0 <= i < n`. Nếu chưa trả về, lệnh `i++` làm `i` tăng đúng một đơn vị. Đại lượng `n - i` là số nguyên không âm và giảm sau mỗi lần lặp chưa kết thúc, nên không thể giảm vô hạn. Vì thế hàm dừng sau tối đa `n` lần so sánh trên mọi mảng hợp lệ.

Nếu bỏ bước tăng `i`, khi phần tử đầu tiên khác `target`, thuật toán sẽ cứ kiểm tra lại cùng một vị trí: đây là lỗi **lặp vô hạn**. Nếu dùng điều kiện `i <= values.length`, chương trình có thể truy cập vượt chỉ số ở `i == values.length`.

Trong những bài toán khác, cách chứng minh tiến triển có thể dựa trên đoạn tìm kiếm thu hẹp dần, số việc chưa xử lý giảm dần hoặc giá trị đếm tiến đến một cận. Với thuật toán đệ quy, cần tương tự một **trường hợp cơ sở** và lời gọi đệ quy làm bài toán nhỏ đi.

## 6. Cài đặt Java 17+ có thể chạy

Tạo tệp `FirstIndexDemo.java`:

```java
public class FirstIndexDemo {
    public static int firstIndexOf(int[] values, int target) {
        if (values == null) {
            throw new IllegalArgumentException("values must not be null");
        }

        int i = 0;
        while (i < values.length) {
            if (values[i] == target) {
                return i;
            }
            i++;
        }
        return -1;
    }

    public static void main(String[] args) {
        int[] values = {4, 9, 2, 9};

        System.out.println(firstIndexOf(values, 2));
        System.out.println(firstIndexOf(values, 9));
        System.out.println(firstIndexOf(values, 7));
        System.out.println(firstIndexOf(new int[0], 7));
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac FirstIndexDemo.java
java FirstIndexDemo
```

Kết quả chuẩn:

```text
2
1
-1
-1
```

Giải thích lần lượt: số `2` ở chỉ số `2`; số `9` xuất hiện đầu tiên ở chỉ số `1`; số `7` không có trong mảng; mảng rỗng không có phần tử để tìm. Với mảng rỗng, vòng `while` không chạy lần nào và hàm vẫn trả kết quả hợp lệ. Với `values == null`, hàm chủ động ném `IllegalArgumentException`, vì đầu vào không đáp ứng tiền điều kiện.

Trong mã trên, `return` trả **kết quả của thuật toán** cho nơi gọi; `System.out.println` trong `main` chỉ giúp người học quan sát các kết quả đó.

## 7. Kiểm tra tính đúng đắn, trường hợp biên và chi phí

Có hai câu hỏi tách biệt:

- **Đúng kết quả:** nếu hàm trả `k`, `k` có thực sự là chỉ số đầu tiên hoặc `-1` đúng quy ước?
- **Chắc chắn kết thúc:** hàm có dừng với mọi đầu vào thỏa tiền điều kiện?

Một lập luận ngắn cho tính đúng của kết quả: trước mỗi lần kiểm tra `values[i]`, tất cả vị trí từ `0` đến `i - 1` đã được xác nhận **khác** `target`. Khi gặp phần tử bằng `target`, `i` vì thế là vị trí đầu tiên. Nếu vòng lặp kết thúc bình thường, mọi vị trí đã được kiểm tra và đều khác `target`, nên `-1` là đúng. Kết hợp với lập luận giảm `n - i` ở mục 5, thuật toán vừa cho kết quả đúng vừa kết thúc.

| Trường hợp | Đầu vào | Kết quả mong đợi |
| --- | --- | --- |
| Tìm thấy ngay | `[5, 8]`, tìm `5` | `0` |
| Có phần tử trùng | `[9, 2, 9]`, tìm `9` | `0` (vị trí đầu tiên) |
| Chỉ thấy ở cuối | `[3, 6, 4]`, tìm `4` | `2` |
| Không tìm thấy | `[3, 6]`, tìm `1` | `-1` |
| Mảng rỗng | `[]`, tìm `1` | `-1` |

Với mảng có `n` phần tử, thời gian tệ nhất là **O(n)** vì có thể phải kiểm tra đủ `n` phần tử; khi phần tử đầu khớp thì chỉ cần một phép so sánh. Bộ nhớ phụ là **O(1)** vì chỉ cần biến chỉ số `i`. Độ phức tạp cho biết mức tài nguyên tăng như thế nào, nhưng **không thay thế** việc chứng minh đúng kết quả và kết thúc.

## 8. Quy trình dùng bốn thành phần khi gặp bài toán mới

1. **Viết đầu vào:** tên, kiểu, miền hợp lệ, dữ liệu rỗng và điều kiện đặc biệt; xác định dữ liệu có thể thay đổi hay không.
2. **Viết đầu ra:** giá trị chính xác, các trường hợp thành công/thất bại và quy ước trả kết quả; thử mô tả bằng tiền điều kiện/hậu điều kiện.
3. **Viết bước xử lý:** bắt đầu từ trạng thái nào, thực hiện thao tác gì, kiểm tra điều kiện và cập nhật gì; đi thử từng bước trên một ví dụ nhỏ.
4. **Viết điều kiện kết thúc:** liệt kê mọi đường dừng; với vòng lặp/đệ quy, chỉ ra đại lượng tiến triển hoặc phạm vi thu hẹp đến điểm dừng.
5. **Kiểm tra lại:** dùng các trường hợp thường gặp, rỗng, một phần tử, trùng lặp và không có lời giải; sau đó mới phân tích thời gian và bộ nhớ.

Một mẫu mô tả ngắn dùng được cho nhiều bài là: “Với **đầu vào** X thỏa điều kiện A, thực hiện các **bước** B để tạo **đầu ra** Y thỏa điều kiện C; quá trình **kết thúc** vì mỗi vòng làm đại lượng D tiến gần một giới hạn hữu hạn.”

## 9. Những nhầm lẫn thường gặp

- **Đầu bài mơ hồ:** “tìm một phần tử” không nói tìm vị trí nào khi có trùng lặp. Cần làm rõ đầu ra trước khi chọn bước xử lý.
- **Thiếu tiền điều kiện:** áp dụng thuật toán cần dữ liệu sắp xếp cho dữ liệu tùy ý hoặc bỏ qua `null`/mảng rỗng.
- **Đồng nhất kết quả với in màn hình:** hàm cần trả giá trị để thành phần khác dùng tiếp; in ra chỉ phục vụ trình bày.
- **Quên cập nhật biến lặp:** điều kiện tiếp tục luôn đúng, khiến chương trình lặp vô hạn.
- **Sai ranh giới:** dùng `<=` thay cho `<` khi truy cập mảng, dẫn đến lỗi vượt chỉ số.
- **Chỉ nghĩ đến nhánh thành công:** không xác định kết quả khi duyệt hết mà vẫn chưa tìm thấy.
- **Nhầm `break` với `return`:** `break` chỉ thoát vòng lặp gần nhất, còn `return` kết thúc phương thức và cung cấp giá trị trả về (nếu có).

## 10. Tự kiểm tra

**Câu 1.** Với `[6, 6, 1]` và `target = 6`, hàm trả bao nhiêu? **Đáp án:** `0`, vì yêu cầu vị trí xuất hiện đầu tiên.

**Câu 2.** Với mảng rỗng, có phải vòng lặp không kết thúc vì không tìm thấy phần tử? **Đáp án:** Không. Điều kiện `0 < 0` sai ngay từ đầu; hàm trả `-1`.

**Câu 3.** Vì sao `i++` quan trọng, và nó có bảo đảm dừng khi không tìm thấy không? **Đáp án:** Nó làm số phần tử chưa xét `n - i` giảm một sau mỗi lần lặp; do `n` hữu hạn, cuối cùng `i == n` và hàm kết thúc.

**Câu 4.** Muốn đổi yêu cầu thành “trả về vị trí cuối cùng”, phần nào phải đổi? **Đáp án:** Trước hết phải đổi **đặc tả đầu ra**; sau đó điều chỉnh bước xử lý để không trả ngay ở lần khớp đầu tiên (hoặc quét từ cuối lên đầu), đồng thời kiểm tra lại điều kiện kết thúc và tính đúng đắn.