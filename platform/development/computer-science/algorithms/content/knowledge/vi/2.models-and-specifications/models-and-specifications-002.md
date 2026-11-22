# Tiền điều kiện, hậu điều kiện và các trường hợp không hợp lệ

## 1. Vì sao thuật toán cần được đặc tả?

Một thuật toán không chỉ là các bước tính toán. Để người khác sử dụng, chứng minh và kiểm thử đúng, ta cần nói rõ **đầu vào nào được chấp nhận**, **kết quả nào được bảo đảm** và **điều gì xảy ra khi đầu vào không hợp lệ**. Ba phần này tạo thành hợp đồng (contract) giữa người gọi và thuật toán.

Ví dụ, yêu cầu “tìm phần tử lớn nhất của mảng” vẫn thiếu thông tin: mảng có được rỗng không, có được null không, tất cả số đều âm thì sao, hàm có sửa mảng hay không? Đặc tả làm rõ những điểm đó trước khi viết mã.

- **Tiền điều kiện (precondition):** điều phải đúng tại thời điểm bắt đầu thực hiện để thuật toán có nghĩa vụ bảo đảm kết quả bình thường.
- **Hậu điều kiện (postcondition):** điều phải đúng khi thuật toán hoàn tất bình thường, giả sử tiền điều kiện được thỏa mãn.
- **Trường hợp không hợp lệ (invalid case):** đầu vào hoặc trạng thái vi phạm hợp đồng đã công bố; cần quy định cách phát hiện và phản hồi phù hợp.

Trong ngữ cảnh mô hình và đặc tả, thường ký hiệu tiền điều kiện là P, thuật toán là A và hậu điều kiện là Q. Bộ ba Hoare viết là **{P} A {Q}**: nếu P đúng khi bắt đầu và A kết thúc bình thường thì Q phải đúng. Đây là cách diễn đạt tính đúng đắn bộ phận (partial correctness); muốn có tính đúng đắn toàn phần (total correctness) còn phải chứng minh A dừng với mọi đầu vào thỏa P.

## 2. Viết tiền điều kiện đúng và đủ

Tiền điều kiện xác định **miền đầu vào hợp lệ**. Nó có thể đề cập đến kiểu dữ liệu, miền giá trị, cấu trúc, thứ tự dữ liệu, quan hệ giữa nhiều tham số và trạng thái hệ thống.

Ví dụ cho các bài toán khác nhau:

| Thuật toán | Tiền điều kiện có ý nghĩa |
| --- | --- |
| Tìm giá trị lớn nhất của mảng số nguyên | Mảng khác null và có ít nhất một phần tử |
| Tìm kiếm nhị phân trên mảng | Mảng khác null và đã được sắp tăng dần (không giảm); mảng rỗng có thể vẫn hợp lệ |
| Chia hai số nguyên | Số chia khác 0; cần quy định riêng khả năng tràn số |
| Truy cập phần tử ở vị trí i | Mảng khác null, 0 ≤ i < độ dài mảng |

Một tiền điều kiện tốt phải **cụ thể, kiểm tra được hoặc có thể được người gọi bảo đảm**, đồng thời không mạnh hơn mức thuật toán thật sự cần. Chẳng hạn, hàm tìm giá trị lớn nhất không cần yêu cầu mảng đã sắp xếp; thêm yêu cầu đó sẽ hạn chế người dùng vô ích.

Cần phân biệt hai cách thực thi hợp đồng:

1. **Kiểm tra tại ranh giới hàm:** như kiểm tra null hoặc mảng rỗng với chi phí O(1), rồi ném ngoại lệ rõ nghĩa.
2. **Yêu cầu người gọi bảo đảm:** như mảng đã sắp xếp cho tìm kiếm nhị phân. Việc quét để xác nhận thứ tự mất O(n); nếu quét mỗi lần tìm, tổng thời gian mỗi lần gọi không còn O(log n). Có thể chọn API kiểm tra đầu vào ở bước chuẩn bị dữ liệu, hoặc ghi rõ điều kiện mà API lõi dựa vào.

Không phải điều kiện nào cũng cần kiểm tra trong mọi lần gọi. Nhưng nếu không kiểm tra, tài liệu phải nói rõ trách nhiệm của người gọi và **không hứa một kết quả cụ thể** khi điều kiện bị vi phạm.

## 3. Viết hậu điều kiện có thể kiểm chứng

Hậu điều kiện mô tả kết quả đủ chính xác để phân biệt một lời giải đúng với lời giải sai. Nó thường bao gồm:

- **Giá trị trả về:** đúng theo tính chất toán học của bài toán, kể cả khi có nhiều đáp án hợp lệ.
- **Trạng thái sau khi chạy:** dữ liệu đầu vào có bị sửa hay không, cấu trúc nào được giữ nguyên.
- **Quan hệ giữa đầu vào và đầu ra:** kết quả có thuộc tập dữ liệu ban đầu, có thỏa miền chỉ số, có giữ thứ tự hay không.
- **Trường hợp không tìm thấy:** trả về giá trị quy ước, kiểu tùy chọn, hoặc ném ngoại lệ theo hợp đồng cụ thể.

Ví dụ, với hàm max nhận mảng số nguyên hợp lệ, có thể phát biểu:

- Giá trị trả về r bằng **một phần tử trong mảng đầu vào**.
- Với mọi phần tử x trong mảng, **r ≥ x**.
- Nội dung và thứ tự các phần tử của mảng **không thay đổi**.

Các điều kiện này mạnh hơn phát biểu mơ hồ “trả về một số lớn”. Với dữ liệu âm hoàn toàn, kết quả vẫn là số lớn nhất trong các số âm; không được tùy tiện trả 0.

Hậu điều kiện của đường chạy bình thường khác với **hợp đồng ngoại lệ**. Nếu đầu vào không hợp lệ, hàm có thể ném ngoại lệ đã quy định; khi đó không được đánh giá nó theo một giá trị trả về bình thường vốn không tồn tại.

## 4. Ví dụ Java 17+: đặc tả và cài đặt hàm max

**Hợp đồng của max(values):**

- Tiền điều kiện để có kết quả bình thường: values khác null và values.length > 0.
- Hậu điều kiện bình thường: trả về phần tử lớn nhất của values; mảng không bị thay đổi.
- Đầu vào không hợp lệ: values là null hoặc có độ dài 0; ném IllegalArgumentException với thông báo riêng cho từng trường hợp.
- Độ phức tạp: thời gian O(n), bộ nhớ phụ O(1) với n là số phần tử.

Lưu chương trình sau thành tệp **MaxContractDemo.java**:

~~~java
import java.util.Arrays;

public class MaxContractDemo {
    public static int max(int[] values) {
        if (values == null) {
            throw new IllegalArgumentException("values must not be null");
        }
        if (values.length == 0) {
            throw new IllegalArgumentException("values must not be empty");
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
        int[] a = {-3, 7, 2, 7};
        System.out.println("max = " + max(a));
        System.out.println("unchanged = " + Arrays.equals(a, new int[]{-3, 7, 2, 7}));

        try {
            max(new int[0]);
        } catch (IllegalArgumentException ex) {
            System.out.println("empty: " + ex.getMessage());
        }

        try {
            max(null);
        } catch (IllegalArgumentException ex) {
            System.out.println("null: " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy từ thư mục chứa tệp:

~~~bash
javac MaxContractDemo.java
java MaxContractDemo
~~~

Kết quả chuẩn:

~~~text
max = 7
unchanged = true
empty: values must not be empty
null: values must not be null
~~~

**Giải thích tính đúng:** sau khi nhận dữ liệu hợp lệ, biến best khởi tạo bằng phần tử đầu tiên. Tại đầu mỗi vòng lặp có chỉ số i (1 ≤ i < n), **bất biến vòng lặp (loop invariant)** là “best bằng giá trị lớn nhất của đoạn values[0..i-1]”. Mỗi bước so sánh thêm values[i] và cập nhật best nếu cần, nên bất biến được duy trì. Khi vòng lặp kết thúc, best là giá trị lớn nhất của toàn mảng. Chỉ đọc phần tử, không gán vào values, nên tính bất biến của dữ liệu cũng được bảo toàn.

Vòng lặp duyệt hữu hạn từ i = 1 đến n - 1 nên sẽ dừng; cùng với bất biến, đó là cơ sở giải thích tính đúng đắn toàn phần của ví dụ. Việc kiểm tra null phải đứng **trước** thao tác lấy values.length, nếu không sẽ phát sinh NullPointerException ngoài hợp đồng đã chủ định.

## 5. Phân biệt đầu vào không hợp lệ với trường hợp biên hợp lệ

**Trường hợp biên (edge/boundary case)** nằm ở rìa miền hợp lệ; **trường hợp không hợp lệ** nằm ngoài miền đó. Không được đánh đồng kết quả “không tìm thấy” với dữ liệu sai.

| Lời gọi hoặc tình huống | Phân loại | Hành vi theo hợp đồng |
| --- | --- | --- |
| max([5]) | Hợp lệ, nhỏ nhất về kích thước | Trả 5 |
| max([-8, -2, -11]) | Hợp lệ, tất cả số âm | Trả -2 |
| max([7, 7, 7]) | Hợp lệ, có phần tử trùng | Trả 7 |
| max(null) | Không hợp lệ | IllegalArgumentException |
| max([]) | Không hợp lệ | IllegalArgumentException |
| Tìm kiếm nhị phân trong mảng đã sắp xếp nhưng không có khóa | Hợp lệ | Trả dấu hiệu “không tìm thấy” đã quy định |
| Tìm kiếm nhị phân trên mảng chưa sắp xếp | Vi phạm tiền điều kiện | Phải từ chối hoặc không bảo đảm kết quả, tùy API |

Đặc tả có thể khác nhau theo bài toán: mảng rỗng **không hợp lệ** với max vì không có phần tử lớn nhất, nhưng **có thể hợp lệ** với tìm kiếm nhị phân vì chắc chắn không có phần tử phù hợp. Không suy ra quy tắc chung từ tên kiểu dữ liệu.

Với các phép tính số học, cần nêu rõ miền giá trị và xử lý tràn số. Ví dụ, phép cộng int trong Java có thể tràn theo ngữ nghĩa số nguyên 32-bit; nếu hậu điều kiện đòi tổng toán học chính xác, có thể dùng long khi đủ miền hoặc Math.addExact để phát hiện tràn, thay vì ngầm coi kết quả tràn là đúng.

## 6. Ví dụ đặc tả tìm kiếm nhị phân

Giả sử binarySearch(a, target) tìm trong mảng int tăng dần, không giảm:

**P (tiền điều kiện):** a khác null; với mọi i từ 1 đến a.length - 1, a[i - 1] ≤ a[i]. Không bắt buộc mảng có phần tử.

**Q (hậu điều kiện khi trả về r):**

- Hoặc r = -1 và **không tồn tại** chỉ số j hợp lệ sao cho a[j] = target.
- Hoặc 0 ≤ r < a.length và a[r] = target.
- Mảng a giữ nguyên.
- Nếu có phần tử trùng, bất kỳ chỉ số khớp nào đều được chấp nhận, trừ khi đề bài yêu cầu rõ “vị trí đầu tiên/cuối cùng”.

Đối với mảng rỗng hợp lệ, r = -1. Đối với mảng chưa sắp xếp, một cài đặt tìm kiếm nhị phân thông thường có thể bỏ lỡ phần tử dù nó tồn tại; vì vậy không thể khẳng định Q nếu không thỏa P. Khi cài đặt tìm kiếm nhị phân bằng chỉ số int, cách tính mid = low + (high - low) / 2 giúp tránh rủi ro tràn của phép cộng low + high.

Điểm cốt lõi là **tiền điều kiện định nghĩa khi nào hậu điều kiện được bảo đảm**; biểu diễn -1 là một phần của hậu điều kiện cho đầu vào hợp lệ không có kết quả, không phải bằng chứng lỗi đầu vào.

## 7. Chọn chính sách xử lý trường hợp không hợp lệ

Có một số chính sách thông dụng; cần chọn nhất quán và công bố rõ trong API:

1. **Ném ngoại lệ:** phù hợp khi không thể tiếp tục với đầu vào đó. Với dữ liệu đối số không hợp lệ trong Java, IllegalArgumentException thường thích hợp; null cũng có thể dùng NullPointerException qua Objects.requireNonNull nếu hợp đồng quy định như vậy.
2. **Trả về kiểu thể hiện sự vắng mặt:** chẳng hạn OptionalInt cho một phép tìm có thể không ra kết quả; cách này nên dành cho **không tìm thấy dù đầu vào hợp lệ**, không dùng để che lỗi gọi sai.
3. **Trả mã trạng thái/kiểu kết quả có cấu trúc:** hữu ích khi lỗi là một nhánh nghiệp vụ thường gặp và người gọi cần phân biệt nhiều loại lỗi.
4. **Yêu cầu tiền điều kiện nhưng không kiểm tra tại runtime:** hữu ích khi kiểm tra tốn kém; phải nêu rõ rằng đầu vào vi phạm nằm ngoài bảo đảm kết quả của thuật toán. Java vẫn có hành vi chạy cụ thể tùy mã, nhưng hành vi đó không tự trở thành lời hứa của API.

Không nên dùng assert của Java làm biện pháp kiểm tra duy nhất cho đầu vào công khai: assertion thường bị tắt khi chạy bình thường. Cũng không nên bắt mọi ngoại lệ rồi trả một giá trị mặc định dễ bị hiểu nhầm là kết quả hợp lệ.

## 8. Từ đặc tả đến kiểm thử và chứng minh

Có thể đi theo trình tự sau:

1. **Xác định miền dữ liệu:** đầu vào, kích thước, thứ tự, giới hạn giá trị và khả năng null.
2. **Viết P trước mã:** điều kiện phải thỏa để bài toán có đáp án được định nghĩa.
3. **Viết Q đủ mạnh:** ràng buộc giá trị trả về, tính đầy đủ của kết quả và trạng thái sau chạy.
4. **Quy định lỗi:** những gì bị từ chối, bằng ngoại lệ hoặc kết quả có kiểu rõ ràng; tách chúng khỏi trường hợp không tìm thấy hợp lệ.
5. **Lập luận tính đúng:** tìm bất biến vòng lặp/quan hệ quy nạp và điều kiện dừng; kiểm tra trường hợp có nhiều đáp án.
6. **Sinh kiểm thử từ P và Q:** ít nhất một trường hợp bình thường, các biên hợp lệ, các lớp đầu vào không hợp lệ và tính chất hậu điều kiện.

Bảng kiểm thử gợi ý cho max:

| Nhóm | Dữ liệu | Mong đợi |
| --- | --- | --- |
| Một phần tử | [42] | 42 |
| Số âm | [-5, -2, -9] | -2 |
| Trùng cực đại | [4, 9, 9, 1] | 9 |
| Biên kiểu int | [Integer.MIN_VALUE, Integer.MAX_VALUE] | Integer.MAX_VALUE |
| Mảng rỗng | [] | IllegalArgumentException |
| Tham chiếu null | null | IllegalArgumentException |
| Bảo toàn dữ liệu | Bất kỳ mảng hợp lệ | Nội dung mảng sau khi gọi bằng trước khi gọi |

Có thể kiểm tra thuộc tính thay vì chỉ so sánh một vài ví dụ: với mọi mảng hợp lệ, kết quả phải là một phần tử đã có, không nhỏ hơn phần tử nào và mảng không đổi. Kiểm thử tự động giúp phát hiện lỗi nhưng không thay thế chứng minh khi yêu cầu độ tin cậy cao.

## 9. Các lỗi thường gặp

- **Đặc tả thiếu tiền điều kiện ẩn:** dùng tìm kiếm nhị phân nhưng quên ghi “đã sắp xếp”.
- **Hậu điều kiện mơ hồ:** chỉ ghi “trả vị trí đúng” mà không định nghĩa không tìm thấy, chỉ số hợp lệ hay phần tử trùng.
- **Đánh đồng dữ liệu lỗi và kết quả hợp lệ:** dùng -1 cho cả “không tìm thấy” lẫn “đầu vào sai” khiến người gọi khó xác định nguyên nhân.
- **Bỏ sót ảnh hưởng trạng thái:** hàm làm thay đổi mảng nhưng tài liệu lại ngầm cho rằng đầu vào được giữ nguyên.
- **Kiểm tra gây đổi độ phức tạp:** quét toàn mảng để xác nhận đã sắp xếp trong mỗi lần tìm kiếm nhưng vẫn công bố O(log n) cho cả API.
- **Không kiểm tra giá trị biên:** số âm hoàn toàn, mảng một phần tử, lặp phần tử, giá trị int cực đại/cực tiểu và phép tính có thể tràn.
- **Nhầm bất biến với hậu điều kiện:** bất biến phải đúng ở các vị trí xác định trong suốt vòng lặp; hậu điều kiện nói về trạng thái khi kết thúc.

**Tự luyện:** hãy đặc tả một hàm trả chỉ số xuất hiện **đầu tiên** của target trong mảng tăng dần. Ngoài điều kiện a khác null và đã sắp xếp, hậu điều kiện cần thêm: nếu trả r ≥ 0 thì a[r] = target và **mọi j < r đều khác target**; nếu trả -1 thì target không tồn tại. Chính điều kiện “đầu tiên” này khiến một cài đặt tìm kiếm nhị phân trả bất kỳ chỉ số trùng nào chưa đủ đúng đặc tả.

**Ghi nhớ:** phát biểu rõ **P (được phép gọi khi nào), Q (bảo đảm điều gì), và chính sách cho đầu vào vi phạm P** trước khi chọn cấu trúc dữ liệu hay tối ưu thuật toán. Một thuật toán chạy được với vài ví dụ chưa chắc đúng với hợp đồng của nó.
