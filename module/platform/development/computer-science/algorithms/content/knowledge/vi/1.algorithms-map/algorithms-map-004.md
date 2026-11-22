# Từ ví dụ cụ thể đến quy tắc giải tổng quát

Một lời giải cho **một bộ dữ liệu** chưa chắc là một **thuật toán**. Khi học thuật toán, ta cần đi từ việc “với các số này, đáp án là gì?” đến “với mọi đầu vào hợp lệ thuộc cùng một loại bài toán, phải thực hiện những bước nào để luôn cho ra đáp án đúng?”. Quá trình này gọi là **khái quát hóa lời giải**.

Bản đồ tư duy của bài:

**Ví dụ cụ thể → Đặc tả bài toán → Trạng thái cần theo dõi → Quy tắc cập nhật → Thuật toán tổng quát → Lập luận đúng đắn → Kiểm thử.**

## 1. Phân biệt ví dụ, cách làm và quy tắc tổng quát

Giả sử cần tìm số lớn nhất trong dãy:

- Đầu vào ví dụ: **[3, 9, 2, 7]**.
- Đầu ra của ví dụ: **9**.
- Cách làm bằng tay: nhìn từng số, ghi nhớ số lớn nhất đã thấy, rồi trả lại số đó.

Con số 9 chỉ là đáp án cho **một trường hợp**. Câu “chọn số thứ hai” cũng không phải quy tắc tổng quát: nó tình cờ đúng với ví dụ này nhưng sai với [9, 3, 2, 7]. Quy tắc có khả năng áp dụng rộng hơn là:

> Ghi nhớ phần tử lớn nhất trong những phần tử đã xem. Mỗi lần gặp phần tử lớn hơn, thay giá trị đang ghi nhớ. Khi đã xem hết dãy, giá trị đang ghi nhớ là đáp án.

Quy tắc không phụ thuộc vào độ dài cố định, vị trí của phần tử lớn nhất, việc các số có dương hay không, hoặc dãy có sắp xếp hay không. Tuy nhiên, nó vẫn có **điều kiện áp dụng**: dãy phải có ít nhất một phần tử để tồn tại số lớn nhất.

## 2. Chuyển câu chuyện thành đặc tả rõ ràng

Trước khi viết mã, cần xác định điều gì được phép thay đổi giữa các ví dụ và điều gì phải luôn đúng.

| Thành phần | Đặc tả cho bài tìm giá trị lớn nhất |
| --- | --- |
| Đầu vào | Mảng số nguyên a, độ dài n ≥ 1 |
| Đầu ra | Một giá trị m là phần tử của a và m ≥ mọi phần tử trong a |
| Điều kiện ban đầu | a khác null và không rỗng |
| Trường hợp không hợp lệ | Báo lỗi rõ ràng, ví dụ IllegalArgumentException |
| Yêu cầu khác | Không cần sắp xếp, không thay đổi mảng đầu vào |
| Thước đo quy mô | n = số phần tử của mảng |

Đặc tả giúp tránh hai kiểu nhầm lẫn: coi một tính chất ngẫu nhiên của ví dụ là giả thiết chung, hoặc bỏ qua đầu vào đặc biệt khiến giải pháp chỉ chạy đúng với dữ liệu “đẹp”.

**Phân biệt ba cấp độ:** một **test case** là một đầu vào kèm đầu ra kỳ vọng; một **đặc tả** nói đúng/sai nghĩa là gì với mọi đầu vào hợp lệ; một **thuật toán** là một quy trình hữu hạn để tính đầu ra đáp ứng đặc tả đó.

## 3. Quan sát từng bước để tìm trạng thái cần lưu

Với dãy [3, 9, 2, 7], ta không cần nhớ mọi phép so sánh đã thực hiện. Chỉ cần một biến **best** đại diện cho số lớn nhất trong phần đã duyệt.

| Bước | Phần tử xét | best sau bước | Giải thích |
| --- | ---: | ---: | --- |
| Khởi tạo | 3 | 3 | Dãy con đã xét chỉ có phần tử đầu |
| Xét vị trí 1 | 9 | 9 | 9 lớn hơn 3 |
| Xét vị trí 2 | 2 | 9 | 2 không lớn hơn 9 |
| Xét vị trí 3 | 7 | 9 | 7 không lớn hơn 9 |
| Kết thúc | — | 9 | Đã xét mọi phần tử |

Điểm quan trọng không phải các số 3, 9, 2, 7; đó là **ý nghĩa của best** sau mỗi bước. Ta có thể phát biểu một thuộc tính đúng xuyên suốt vòng lặp:

**Bất biến vòng lặp:** sau khi đã xử lý các phần tử từ vị trí 0 đến i, best bằng giá trị lớn nhất trong chính đoạn đó.

Từ bất biến, suy ra cách cập nhật:

1. Khởi tạo best = a[0], vì đây là phần tử duy nhất đã xét.
2. Với từng vị trí i từ 1 đến n − 1, so sánh a[i] với best.
3. Nếu a[i] lớn hơn best, gán best = a[i]; nếu không, giữ nguyên.
4. Khi duyệt hết dãy, trả về best.

Đây là một **khuôn mẫu duyệt tuyến tính và duy trì trạng thái**. Nó mô tả cách xử lý một lớp đầu vào, thay vì ghi nhớ một vài đáp án riêng lẻ.

## 4. Diễn đạt quy tắc thành giả mã

~~~text
MAXIMUM(a):
    yêu cầu a khác null và độ dài a ít nhất là 1
    best <- a[0]
    với i từ 1 đến độ dài a - 1:
        nếu a[i] > best:
            best <- a[i]
    trả về best
~~~

Giả mã tập trung vào quy tắc xử lý. Khi chuyển sang ngôn ngữ lập trình, điều phải giữ nguyên là đặc tả, thứ tự duyệt và ý nghĩa của best; tên biến hay cú pháp có thể khác.

## 5. Hiện thực hoàn chỉnh bằng Java 17+

Lưu đoạn mã dưới đây vào tệp **GeneralizeMaximum.java**:

~~~java
public final class GeneralizeMaximum {
    private GeneralizeMaximum() {
    }

    public static int maximum(int[] numbers) {
        if (numbers == null || numbers.length == 0) {
            throw new IllegalArgumentException(
                "numbers must not be null or empty"
            );
        }

        int best = numbers[0];
        for (int i = 1; i < numbers.length; i++) {
            if (numbers[i] > best) {
                best = numbers[i];
            }
        }
        return best;
    }

    public static void main(String[] args) {
        System.out.println(maximum(new int[] {3, 9, 2, 7}));
        System.out.println(maximum(new int[] {-7, -2, -11}));
        System.out.println(maximum(new int[] {42}));
        System.out.println(maximum(new int[] {9, 9, 3}));
    }
}
~~~

Biên dịch và chạy tại thư mục chứa tệp:

~~~bash
javac GeneralizeMaximum.java
java GeneralizeMaximum
~~~

Kết quả chuẩn trên đầu ra:

~~~text
9
-2
42
9
~~~

Giải thích các trường hợp: dãy đầu minh họa đường đi thông thường; dãy toàn số âm chứng minh không được mặc định số lớn nhất là 0; dãy một phần tử kiểm tra khởi tạo; dãy trùng giá trị chứng minh quy tắc vẫn hợp lệ khi có nhiều phần tử cùng lớn nhất. Phương thức maximum từ chối mảng null hoặc rỗng bằng ngoại lệ, vì đặc tả không định nghĩa giá trị lớn nhất cho hai đầu vào đó. Nó không sửa các phần tử của mảng.

## 6. Vì sao thuật toán đúng với mọi đầu vào hợp lệ?

Một vài kết quả đúng trên ví dụ **không phải chứng minh**. Ta chứng minh bằng bất biến ở phần 3.

**Khởi tạo:** trước lần lặp đầu tiên, best = a[0]. Do đó best là giá trị lớn nhất trong đoạn chỉ chứa a[0]. Bất biến đúng.

**Duy trì:** giả sử trước khi xét a[i], best là giá trị lớn nhất trong đoạn a[0…i−1]. Có hai khả năng:

- Nếu a[i] > best, phần tử mới lớn hơn mọi phần tử trước đó. Gán best = a[i] bảo toàn bất biến.
- Nếu a[i] ≤ best, không có phần tử mới nào vượt best. Giữ best cũng bảo toàn bất biến.

**Kết thúc:** chỉ số i tăng sau mỗi vòng lặp và bị chặn bởi độ dài hữu hạn n, nên vòng lặp dừng. Khi dừng, mọi phần tử a[0…n−1] đều đã được xét. Theo bất biến, best là giá trị lớn nhất của toàn bộ dãy, đúng với đặc tả.

Đây là ba câu hỏi kiểm chứng có thể dùng lại cho nhiều thuật toán: **bất biến có đúng lúc bắt đầu không; mỗi bước có giữ nó đúng không; khi dừng, bất biến có suy ra kết quả cần tìm không?**

## 7. Đánh giá hiệu quả sau khi đã có quy tắc đúng

Với n phần tử, chương trình thực hiện **n − 1 phép so sánh** giữa phần tử mới và best; vì vậy thời gian là **O(n)**. Chỉ dùng một biến best và một biến chỉ số vòng lặp, nên bộ nhớ phụ là **O(1)**, không tính mảng đầu vào do người gọi cung cấp.

Trong mô hình so sánh với dữ liệu chưa sắp xếp, muốn chắc chắn biết phần tử lớn nhất phải xét ảnh hưởng của mọi phần tử; việc duyệt tuyến tính là hợp lý và đạt số phép so sánh tối ưu n − 1. Không nên mặc định “tổng quát” đồng nghĩa với “nhanh nhất”: trước hết phải **đúng cho miền đầu vào**, sau đó mới so sánh các cách triển khai dựa trên chi phí và ràng buộc.

## 8. Kiểm thử để phát hiện quy tắc chỉ đúng tình cờ

| Nhóm trường hợp | Đầu vào | Kết quả kỳ vọng | Điều muốn kiểm tra |
| --- | --- | --- | --- |
| Thông thường | [3, 9, 2, 7] | 9 | Duyệt hết và cập nhật |
| Lớn nhất ở đầu | [9, 3, 2, 7] | 9 | Không phụ thuộc vị trí |
| Lớn nhất ở cuối | [2, 3, 7, 9] | 9 | Không bỏ sót phần tử cuối |
| Toàn số âm | [-7, -2, -11] | -2 | Không khởi tạo best = 0 |
| Một phần tử | [42] | 42 | Vòng lặp có thể chạy 0 lần |
| Trùng giá trị | [9, 9, 3] | 9 | Không yêu cầu các giá trị khác nhau |
| Giá trị biên int | [Integer.MIN_VALUE, Integer.MAX_VALUE] | Integer.MAX_VALUE | So sánh đúng ở biên |
| Mảng rỗng hoặc null | [] hoặc null | IllegalArgumentException | Hợp đồng đầu vào rõ ràng |

Ngoài test case, có thể dùng **tính chất** để kiểm tra nhiều dữ liệu tự tạo: kết quả phải là một phần tử có trong mảng; không phần tử nào lớn hơn kết quả; hoán vị thứ tự các phần tử không làm thay đổi giá trị lớn nhất; thêm một bản sao của phần tử đã có cũng không thay đổi kết quả. Các tính chất này giúp kiểm tra quy tắc tổng quát mà không dựa vào một ví dụ cố định.

## 9. Những lối khái quát hóa sai thường gặp

**Ghi nhớ vị trí của đáp án:** “Ở ví dụ trên phần tử thứ hai lớn nhất nên cứ lấy phần tử thứ hai”. Đây là học thuộc một mẫu dữ liệu, không phải thuật toán.

**Đưa giả thiết chưa được cho:** “Dãy đã tăng dần, vậy lấy phần tử cuối”. Chỉ đúng nếu tính tăng dần là điều kiện chính thức của đề; nó sai với mảng chưa sắp xếp.

**Khởi tạo từ một giá trị tiện tay:** best = 0 sai với [-7, -2, -11]. Khởi tạo bằng a[0] biến việc “đã xét một phần tử” thành một bất biến đúng ngay từ đầu.

**Bỏ qua ranh giới vòng lặp:** duyệt đến n − 2 có thể bỏ sót cực đại ở cuối; duyệt tới n sẽ truy cập ngoài mảng. Với Java, các chỉ số hợp lệ là 0 đến n − 1.

**Chỉ thử trường hợp thuận lợi:** ví dụ có số dương và nhiều phần tử không kiểm chứng được trường hợp toàn âm, một phần tử, trùng giá trị hoặc đầu vào không hợp lệ.

**Quên phát biểu rõ đầu ra:** “tìm số lớn nhất” trả về **giá trị**; “tìm vị trí xuất hiện đầu tiên của số lớn nhất” trả về **chỉ số**. Hai đặc tả gần nhau nhưng khác nhau và đòi hỏi trạng thái khác nhau.

## 10. Dùng cùng tư duy cho bài toán khác

Không phải thuật toán nào cũng là một vòng lặp tuyến tính, nhưng **cách đi từ ví dụ đến đặc tả và bất biến** áp dụng rất rộng. Với bài **đếm số chẵn trong mảng**, ta thay trạng thái best bằng count, khởi tạo count = 0, tăng count khi phần tử đang xét là số chẵn. Bất biến lúc này là: *count bằng số phần tử chẵn trong đoạn đã duyệt*. Cách tìm bất biến tương tự; quy tắc cập nhật thay đổi theo mục tiêu.

Ngay cả trong bài tìm cực đại, chỉ cần đổi yêu cầu thành **vị trí xuất hiện đầu tiên của giá trị lớn nhất**, ta phải lưu cả bestValue và bestIndex. Khi phần tử mới **lớn hơn nghiêm ngặt** bestValue, cập nhật cả hai; khi bằng nhau, giữ chỉ số cũ để bảo toàn yêu cầu “đầu tiên”. Ví dụ [5, 9, 9, 3] trả về chỉ số 1 nếu đếm từ 0. Việc đổi điều kiện từ > sang ≥ sẽ cho chỉ số 2, tức là giải một bài toán khác. Đây là ví dụ vì sao quy tắc phải được rút ra từ **đặc tả**, không chỉ từ hình dạng các ví dụ.

## 11. Quy trình thực hành trên một đề thuật toán mới

1. **Diễn đạt lại yêu cầu:** đầu vào là gì, đầu ra đúng nghĩa là gì, có bao nhiêu đối tượng, có điều kiện hay giới hạn nào?
2. **Tự giải một ví dụ nhỏ:** mô tả thao tác thật sự cần thực hiện, tránh coi giá trị hoặc vị trí ngẫu nhiên là quy luật.
3. **Tìm thông tin tối thiểu cần ghi nhớ:** sau mỗi bước, điều gì phải đúng về phần đã xử lý (bất biến/trạng thái)?
4. **Rút ra quy tắc cập nhật:** khi thêm một phần tử hoặc thực hiện một thao tác, trạng thái phải thay đổi thế nào để bất biến vẫn đúng?
5. **Xác định điều kiện dừng và đặc tả lỗi:** quy trình có kết thúc với mọi đầu vào hợp lệ không; đầu vào không hợp lệ xử lý ra sao?
6. **Viết giả mã rồi mới viết code:** đối chiếu mỗi dòng với quy tắc đã rút ra; không trộn vào các giả định chỉ đúng trong ví dụ đầu.
7. **Chứng minh và kiểm thử:** kiểm tra khởi tạo–duy trì–kết thúc, phản ví dụ, dữ liệu biên, độ phức tạp và các tính chất độc lập với dữ liệu mẫu.

**Tự kiểm tra:** Nếu thay [3, 9, 2, 7] bằng một mảng khác có độ dài bất kỳ ≥ 1, mọi bước trong giải pháp có còn được xác định rõ không? Nếu có, và bất biến chứng minh được đầu ra đáp ứng đặc tả, ta đã tiến từ một ví dụ riêng lẻ đến một **quy tắc giải tổng quát**.
