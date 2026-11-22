# Thuật toán là gì và quan hệ với bài toán, chương trình, dữ liệu

## Mục tiêu học tập

Sau bài này, bạn có thể: (1) phân biệt **bài toán**, **một trường hợp đầu vào**, **thuật toán**, **chương trình** và **dữ liệu**; (2) mô tả bài toán bằng đầu vào, ràng buộc và đầu ra mong muốn; (3) chuyển một ý tưởng giải thành các bước rõ ràng rồi triển khai bằng Java; (4) giải thích vì sao cách tổ chức dữ liệu ảnh hưởng đến lựa chọn và hiệu năng thuật toán; (5) bước đầu kiểm tra tính đúng, tính dừng và chi phí của thuật toán.

## 1. Năm khái niệm liên hệ với nhau

| Khái niệm | Trả lời câu hỏi | Ví dụ với việc tìm số lớn nhất |
| --- | --- | --- |
| **Bài toán (problem)** | Ta cần giải quyết điều gì, với đầu vào hợp lệ nào và kết quả phải thỏa điều kiện gì? | Cho dãy có ít nhất một số nguyên; trả về giá trị lớn nhất trong dãy. |
| **Trường hợp bài toán (problem instance)** | Lần giải cụ thể nhận dữ liệu nào? | Dãy `[4, 9, 2, 9]`. |
| **Thuật toán (algorithm)** | Quy trình hữu hạn, đủ rõ để biến đầu vào hợp lệ thành kết quả đúng là gì? | Giữ giá trị lớn nhất đã thấy, duyệt các phần tử còn lại và cập nhật nếu gặp số lớn hơn. |
| **Chương trình (program)** | Quy trình đó được biểu diễn và thực thi bằng công cụ nào? | Phương thức `max(int[])` viết bằng Java và được JVM thực thi. |
| **Dữ liệu (data)** | Những giá trị và cách biểu diễn nào được dùng làm đầu vào, trạng thái trung gian và đầu ra? | Mảng `int[]` đầu vào, biến `best` và giá trị nguyên trả về. |

Mối quan hệ điển hình:

```text
BÀI TOÁN (đặc tả đầu vào + kết quả cần đạt)
      ↓ lựa chọn cách giải
THUẬT TOÁN (các bước xử lý + lý do đúng)
      ↓ triển khai bằng ngôn ngữ và cấu trúc dữ liệu
CHƯƠNG TRÌNH (mã nguồn, thư viện, môi trường thực thi)
      ↓ chạy trên một trường hợp dữ liệu
ĐẦU RA + HÀNH VI THỰC TẾ
      ↓ đối chiếu với đặc tả
KẾT QUẢ ĐÚNG / SAI, TỐC ĐỘ, BỘ NHỚ
```

Một **bài toán** có thể có nhiều thuật toán khác nhau; một **thuật toán** có thể được cài bằng nhiều ngôn ngữ và nhiều chương trình; một **chương trình** có thể chạy trên vô số trường hợp dữ liệu. Vì vậy, “thuật toán” không đồng nghĩa với “đoạn code”, còn một lần chạy có đầu ra đúng chưa chứng minh chương trình đúng với mọi đầu vào hợp lệ.

## 2. Bài toán phải được đặc tả trước khi giải

Hãy viết đủ ba thành phần:

1. **Đầu vào:** nhận gì, kiểu dữ liệu gì, kích thước hoặc miền giá trị nào?
2. **Tiền điều kiện/ràng buộc:** trường hợp nào được phép; dữ liệu đã sắp xếp chưa; có thể rỗng, trùng, âm, `null` không?
3. **Đầu ra/hậu điều kiện:** chính xác kết quả nào được coi là đúng; khi có nhiều kết quả hợp lệ thì chấp nhận kết quả nào?

Ví dụ đặc tả bài toán `MAX`:

- **Input:** dãy `A` gồm `n ≥ 1` phần tử nguyên.
- **Output:** một số nguyên `m` thuộc `A` sao cho mọi phần tử `x` trong `A` đều thỏa `x ≤ m`.
- **Trường hợp:** `A = [4, 9, 2, 9]` thì `m = 9`; `A = [-8, -3, -10]` thì `m = -3`.
- **Ngoài phạm vi input:** dãy rỗng. Ta phải xác định cách xử lý rõ ràng trong giao diện chương trình (ví dụ ném ngoại lệ), không tự ý trả về `0`.

Điểm dễ nhầm: “tìm **giá trị** lớn nhất” khác “tìm **vị trí** của phần tử lớn nhất”. Với `[4, 9, 2, 9]`, giá trị lớn nhất duy nhất là `9` nhưng có hai vị trí cùng đạt cực đại (chỉ số `1` và `3` nếu đếm từ 0). Nếu đầu ra là chỉ số, đặc tả còn phải cho biết lấy vị trí đầu tiên, cuối cùng hay bất kỳ vị trí nào. Thay đổi đặc tả tức là thay đổi bài toán cần giải.

Thuật toán chỉ được đánh giá “đúng” khi đối chiếu với **đặc tả đã thống nhất**, không dựa trên cảm giác rằng kết quả “có vẻ hợp lý”.

## 3. Thuật toán có những đặc điểm gì?

Một thuật toán được mô tả ở mức độc lập với ngôn ngữ lập trình bằng lời, sơ đồ hoặc giả mã. Một mô tả hữu ích cần có:

- **Bước rõ ràng và thực hiện được:** mỗi thao tác có ý nghĩa xác định và có thể hoàn thành trong mô hình tính toán đang dùng.
- **Đầu vào, đầu ra được xác định:** biết dữ liệu nào cần thiết và điều kiện kết quả đúng.
- **Tính dừng đối với đầu vào hợp lệ:** quy trình phải kết thúc sau hữu hạn bước (đối với thuật toán thông thường được yêu cầu cho bài toán này).
- **Tính đúng:** khi dừng, kết quả thỏa hậu điều kiện của bài toán với mọi đầu vào hợp lệ.
- **Tính tổng quát:** mô tả giải cả một lớp trường hợp đầu vào, không chỉ một ví dụ được viết sẵn.

Một số thuật toán có yếu tố ngẫu nhiên hoặc cho phép nhiều đường thực thi; vì vậy **không nên coi tính xác định theo nghĩa “luôn cùng một chuỗi bước” là điều bắt buộc của mọi thuật toán**. Điều thiết yếu là phải phát biểu được quy tắc thực hiện và tiêu chí đúng thích hợp.

Giả mã cho `MAX`:

```text
MAX(A):
    yêu cầu: A có ít nhất 1 phần tử
    best ← A[0]
    với i từ 1 đến độ_dài(A) - 1:
        nếu A[i] > best:
            best ← A[i]
    trả về best
```

Chữ `best` chỉ là trạng thái tạm. Nó không phải đáp án ngay từ đầu; nó trở thành đáp án sau khi đã xử lý toàn bộ dãy. Các phép gán, so sánh và duyệt chính là những thao tác thuật toán yêu cầu từ cách biểu diễn dữ liệu.

## 4. Từ thuật toán thành chương trình Java 17+

Dưới đây là một **chương trình hoàn chỉnh**, có thể biên dịch độc lập. Tên tệp bắt buộc là `AlgorithmDemo.java` vì lớp công khai có tên `AlgorithmDemo`.

```java
public class AlgorithmDemo {
    public static int max(int[] values) {
        if (values == null || values.length == 0) {
            throw new IllegalArgumentException(
                    "Mang phai co it nhat mot phan tu");
        }

        int best = values[0];
        for (int i = 1; i < values.length; i++) {
            if (values[i] > best) {
                best = values[i];
            }
        }
        return best;
    }

    public static void main(String[] args) {
        int[] numbers = {4, 9, 2, 9};
        System.out.println("Gia tri lon nhat: " + max(numbers));
        System.out.println(
                "Tat ca am: " + max(new int[]{-8, -3, -10}));
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac AlgorithmDemo.java
java AlgorithmDemo
```

Đầu ra chuẩn chính xác:

```text
Gia tri lon nhat: 9
Tat ca am: -3
```

Giải thích sự tương ứng:

| Ý tưởng thuật toán | Cấu trúc chương trình |
| --- | --- |
| Dãy đầu vào | Tham số `int[] values` |
| Tiền điều kiện có ít nhất một phần tử | Kiểm tra `null`/rỗng và ném `IllegalArgumentException` |
| Giá trị tốt nhất đã thấy | Biến cục bộ `int best` |
| Duyệt các phần tử chưa xét | Vòng lặp `for` với chỉ số `i` |
| Thay kết quả tạm khi thấy số lớn hơn | Câu lệnh `if` và phép gán |
| Đầu ra | `return best` |

Lựa chọn **ném ngoại lệ** cho `null`/rỗng là hành vi của giao diện chương trình khi bị gọi ngoài tiền điều kiện đã nêu; có thể thiết kế API khác, nhưng phải ghi rõ hợp đồng. Thuật toán này không cộng hoặc nhân các số nguyên nên không có nguy cơ tràn số do phép tính tổng/tích; mọi giá trị `int`, kể cả số âm, đều so sánh được. Khởi tạo `best = 0` là lỗi vì sẽ trả kết quả sai khi tất cả phần tử âm.

## 5. Vì sao thuật toán trên đúng và dừng?

Ta dùng **bất biến vòng lặp** để lý giải tính đúng, thay vì chỉ thử vài ví dụ:

- **Khởi tạo:** trước lần lặp đầu tiên, `best = A[0]` là giá trị lớn nhất của phần tử đã xét duy nhất.
- **Duy trì:** giả sử sau khi xét các phần tử từ `A[0]` đến `A[i-1]`, `best` là giá trị lớn nhất trong đoạn đó. Khi xét `A[i]`, nếu `A[i] > best` ta gán `best = A[i]`; nếu không thì giữ nguyên. Trong cả hai trường hợp, `best` lại là giá trị lớn nhất của các phần tử đã xét.
- **Kết thúc:** khi vòng lặp kết thúc, toàn bộ `n` phần tử đều đã được xét; theo bất biến, `best` là giá trị lớn nhất toàn dãy, đúng với hậu điều kiện.

Vòng lặp bắt đầu từ `i = 1`, tăng mỗi lần một đơn vị và dừng khi `i = n`; do `n` hữu hạn, nó thực hiện đúng `n - 1` lượt. Trường hợp `n = 1` không vào vòng lặp và trả chính phần tử duy nhất. Tính dừng và tính đúng là hai câu hỏi riêng: một chương trình có thể dừng nhanh nhưng trả sai, hoặc thao tác đúng ở một số bước nhưng không bao giờ kết thúc.

## 6. Dữ liệu ảnh hưởng đến thuật toán như thế nào?

**Dữ liệu là đối tượng được xử lý, nhưng cách biểu diễn dữ liệu cũng quyết định các thao tác thuận tiện và chi phí thực hiện.**

- **Giá trị:** phần tử âm, trùng nhau, kích thước lớn hoặc dữ liệu rỗng tạo ra các trường hợp cần xử lý cụ thể.
- **Kiểu và biểu diễn:** `int`, `long`, chuỗi, đối tượng hay số thực có miền giá trị và quy tắc so sánh khác nhau. Chẳng hạn số thực `NaN` không tuân theo so sánh thứ tự thông thường, nên không thể mặc nhiên áp dụng hợp đồng bài toán số nguyên cho mọi kiểu.
- **Cấu trúc dữ liệu:** mảng cho truy cập theo chỉ số thường có chi phí `O(1)`; với danh sách liên kết, việc tìm phần tử ở một chỉ số bất kỳ thường phải đi qua các nút. Một ý tưởng thuật toán có thể có chi phí khác hẳn khi thay cấu trúc dữ liệu.
- **Trạng thái trung gian:** biến `best` lưu đủ thông tin để giải bài toán tìm cực đại mà không phải tạo bản sao cả dãy.
- **Ràng buộc dữ liệu:** nếu biết trước dãy đã sắp xếp, ta có thể khai thác điều kiện đó; nếu dữ liệu không thỏa, thuật toán dựa trên điều kiện ấy có thể sai.

Ví dụ bài toán **tìm một giá trị `x` trong mảng** (đầu ra là một vị trí chứa `x` hoặc `-1` nếu không thấy):

| Cách giải | Điều kiện chính | Chi phí tìm một lần | Đánh đổi |
| --- | --- | --- | --- |
| Duyệt tuần tự | Mảng không cần sắp xếp | `O(n)` trong trường hợp xấu nhất | Đơn giản, không cần chuẩn bị dữ liệu |
| Tìm kiếm nhị phân | Mảng **đã sắp xếp** theo cùng thứ tự so sánh và có truy cập chỉ số hiệu quả | `O(log n)` trong trường hợp xấu nhất | Không thể dùng trực tiếp trên mảng chưa sắp xếp |
| Tạo chỉ mục băm | Xây thêm cấu trúc tra cứu và xác định cách xử lý khóa trùng | Trung bình thường kỳ vọng gần `O(1)` mỗi truy vấn, tùy giả định về băm | Tốn thời gian xây chỉ mục và bộ nhớ phụ; tình huống xấu có thể chậm |

Nếu chỉ tìm một lần trên mảng chưa sắp xếp, chi phí **sắp xếp trước** (ví dụ `O(n log n)` với một thuật toán sắp xếp phù hợp) có thể lớn hơn duyệt tuần tự `O(n)`. Nhưng khi cần rất nhiều truy vấn trên cùng một tập dữ liệu, chi phí chuẩn bị có thể được bù lại. Với yêu cầu “tìm chỉ số trong mảng gốc”, việc sắp xếp còn làm thay đổi vị trí: chương trình phải bảo toàn chỉ số gốc hoặc điều chỉnh đặc tả.

Điều này cho thấy **đầu vào, giả định, tần suất sử dụng và dạng đầu ra** quyết định nên chọn thuật toán nào. Không thể tuyên bố một thuật toán “tốt nhất” mà bỏ qua bối cảnh bài toán.

## 7. Đánh giá thuật toán và đánh giá chương trình

Tính đúng là điều kiện đầu tiên; tiếp theo mới xem chi phí tài nguyên.

Với thuật toán `MAX` và mảng `n` phần tử:

- Có đúng `n - 1` lần so sánh `A[i] > best` khi `n ≥ 1`.
- **Thời gian:** `O(n)` vì số thao tác tỉ lệ tuyến tính với `n`; để tìm cực đại trong dãy bất kỳ bằng mô hình so sánh, phải xem xét mọi phần tử.
- **Bộ nhớ phụ:** `O(1)` vì chỉ cần `best` và `i`, không tính bộ nhớ lưu mảng đầu vào.
- **Thời gian chạy thực đo:** còn phụ thuộc kích thước dữ liệu, JVM, phần cứng, JIT và môi trường; ký hiệu `O(n)` mô tả tốc độ tăng theo `n`, không phải số mili giây chính xác.

Hai chương trình khác nhau có thể cài **cùng một thuật toán** và cùng độ phức tạp tiệm cận nhưng tốc độ thực đo khác nhau do cách lưu dữ liệu, cấp phát, thư viện hoặc tối ưu hóa. Ngược lại, hai chương trình cùng giải một bài toán có thể dùng **hai thuật toán khác nhau** với độ phức tạp khác nhau. Khi thử hiệu năng, cần kiểm tra kết quả đúng, dùng dữ liệu đại diện, nêu rõ kích thước và đo trên môi trường so sánh được.

Đừng lẫn lộn: `O(n)` không có nghĩa là luôn nhanh hơn `O(n log n)` với mọi `n` và mọi máy; nó chỉ cho biết đặc điểm tăng trưởng tiệm cận trong điều kiện phân tích tương ứng.

## 8. Quy trình chọn và hiện thực một thuật toán

1. **Diễn đạt bài toán:** viết input, output, tiền/hậu điều kiện; làm rõ rỗng, trùng, âm, thứ tự và cách tính chỉ số.
2. **Đặt ví dụ kiểm tra:** có trường hợp thông thường, biên và phản ví dụ đối với ý tưởng sai.
3. **Đề xuất thuật toán:** viết các bước độc lập với ngôn ngữ; liệt kê giả định như “mảng đã sắp xếp”.
4. **Giải thích tính đúng và tính dừng:** dùng bất biến, lập luận phân hoạch, quy nạp hoặc cách khác phù hợp.
5. **Chọn cách lưu dữ liệu:** cân nhắc thao tác cần thực hiện, giới hạn bộ nhớ, chi phí truy cập và chuyển đổi.
6. **Cài thành chương trình:** xác định kiểu dữ liệu, API, kiểm tra input, lỗi và kết quả trả về.
7. **Kiểm thử và đo:** so kết quả với đặc tả trên dữ liệu đại diện; sau đó đánh giá thời gian/bộ nhớ và cải tiến nếu cần.

Bốn lỗi tư duy phổ biến:

- **“Có code chạy được tức là có thuật toán đúng.”** Biên dịch thành công chỉ nói mã hợp lệ; tính đúng phụ thuộc đặc tả và mọi đầu vào hợp lệ.
- **“Ví dụ chạy đúng chứng minh được bài toán.”** Một vài ca thử không thay thế chứng minh/lập luận; test giúp phát hiện lỗi và tăng độ tin cậy triển khai.
- **“Đổi cấu trúc dữ liệu không ảnh hưởng cách giải.”** Một thuật toán dựa trên truy cập ngẫu nhiên có thể không còn hiệu quả khi dùng cấu trúc chỉ truy cập tuần tự.
- **“Độ phức tạp quyết định toàn bộ.”** Cần xét cả điều kiện đầu vào, tính đúng, chi phí tiền xử lý, bộ nhớ và yêu cầu hệ thống thực tế.

## 9. Tự kiểm tra

**Câu 1.** Với `A = [-8, -3, -10]`, chương trình `max` trả về gì? Vì sao khởi tạo `best = 0` sai?

**Câu 2.** Bài toán “trả **giá trị** lớn nhất” và “trả **vị trí đầu tiên** của giá trị lớn nhất” có cùng hậu điều kiện không? Xét `[4, 9, 2, 9]`.

**Câu 3.** Mảng `[8, 1, 5]` chưa sắp xếp. Có thể áp dụng trực tiếp tìm kiếm nhị phân thông thường không?

**Câu 4.** Hai phương thức Java và Python cùng duyệt tuyến tính để tìm cực đại có nhất thiết là hai thuật toán khác nhau không?

**Câu 5.** Một chương trình tìm cực đại có thể vừa đúng vừa dùng bộ nhớ phụ `O(1)` không? Chỉ ra dữ liệu nào vẫn cần được lưu ở bên ngoài bộ nhớ phụ.

**Đáp án gợi ý:** (1) `-3`; khởi tạo bằng `0` sai khi tất cả phần tử đều âm. (2) Không: kết quả tương ứng là `9` và chỉ số `1` (đếm từ 0). (3) Không, vì giả định đã sắp xếp bị vi phạm. (4) Không; chúng có thể là hai cách cài cùng thuật toán. (5) Có, như chương trình ở mục 4; mảng đầu vào vẫn chiếm bộ nhớ của dữ liệu đầu vào nhưng không được tính vào bộ nhớ **phụ** của thuật toán.

## Ghi nhớ

**Bài toán** xác định điều phải đạt; **thuật toán** mô tả các bước đạt điều đó; **chương trình** hiện thực thuật toán để máy chạy; **dữ liệu** vừa là đối tượng xử lý vừa ảnh hưởng đến cách giải và chi phí. Muốn đánh giá một lời giải, hãy bắt đầu từ hợp đồng đầu vào/đầu ra, chứng minh các bước đúng và dừng, rồi mới bàn về hiệu năng của cách cài cụ thể.
