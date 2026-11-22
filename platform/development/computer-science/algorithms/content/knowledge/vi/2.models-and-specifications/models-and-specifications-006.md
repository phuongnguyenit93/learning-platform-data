# Phân biệt một lời giải bất kỳ với tất cả lời giải

## 1. Vì sao phải phân biệt ngay trong đặc tả?

Một bài toán thuật toán có thể có nhiều đáp án hợp lệ. Câu “hãy tìm một lời giải” và câu “hãy tìm tất cả lời giải” tuy dùng cùng điều kiện hợp lệ nhưng yêu cầu **đầu ra, tiêu chí đúng và chiến lược tìm kiếm khác nhau**. Nếu hiểu sai lượng từ “một” và “tất cả”, chương trình có thể trả về một đáp án đúng mà vẫn không đáp ứng đề bài.

Ký hiệu:
- \(x\): dữ liệu đầu vào; \(Y(x)\): miền các ứng viên có thể xem xét.
- \(Valid(x,y)\): mệnh đề kiểm tra ứng viên \(y\) có thỏa tất cả ràng buộc của đầu vào \(x\) hay không.
- \(S(x)=\{y\in Y(x)\mid Valid(x,y)\}\): **tập nghiệm** của bài toán.

Hai hợp đồng đầu ra cơ bản là:

**Tìm một lời giải bất kỳ:** trả về một \(y\in S(x)\), hoặc thông báo **không tồn tại nghiệm** khi \(S(x)=\varnothing\). “Bất kỳ” nghĩa là không cần chọn nghiệm tốt nhất hoặc nghiệm có thứ tự cụ thể, miễn đúng điều kiện; thuật toán vẫn phải chứng minh được thông báo “không có” nếu không tìm thấy.

**Tìm tất cả lời giải:** trả về toàn bộ \(S(x)\), không chứa ứng viên sai, không thiếu nghiệm và không lặp nghiệm theo quy tắc nhận diện nghiệm đã được đặc tả. Nếu không có nghiệm, đầu ra là một tập/danh sách rỗng.

Không nên đồng nhất hai yêu cầu này với bài toán **quyết định** (“có nghiệm hay không?”), **đếm nghiệm** (“có bao nhiêu nghiệm?”) hoặc **tối ưu hóa** (“nghiệm có chi phí nhỏ nhất/lợi ích lớn nhất?”). Một nghiệm bất kỳ chưa chắc là nghiệm tối ưu; số lượng nghiệm cũng không thay thế danh sách nghiệm.

## 2. Sự khác nhau về hợp đồng và điều kiện đúng

| Tiêu chí | Một lời giải bất kỳ | Tất cả lời giải |
|---|---|---|
| Đầu ra khi có nghiệm | Một nghiệm hợp lệ | Toàn bộ các nghiệm hợp lệ |
| Đầu ra khi vô nghiệm | Dấu hiệu rõ ràng: Optional.empty, null theo hợp đồng, hoặc kiểu kết quả riêng | Tập/danh sách rỗng |
| Tính đúng đắn | Nghiệm trả về phải hợp lệ; thông báo vô nghiệm phải đúng | Mọi nghiệm phải hợp lệ (**soundness**) và mọi nghiệm hợp lệ phải xuất hiện (**completeness**) |
| Trùng lặp | Không có vấn đề lặp trong một kết quả đơn | Phải làm rõ hai nghiệm thế nào được coi là giống nhau và tránh liệt kê trùng |
| Dừng sớm | Có thể dừng ngay khi đã tìm được một nghiệm | Thường phải khám phá hết không gian tìm kiếm liên quan, trừ khi có chứng minh đã thu đủ |
| Dung lượng kết quả | Thường là một cấu trúc kích thước theo một nghiệm | Có thể tăng theo số nghiệm, thậm chí theo hàm mũ |
| Thứ tự | Không bắt buộc nếu đề bài không quy định | Không bắt buộc nếu đề bài coi kết quả là tập; nếu yêu cầu thứ tự, phải thực hiện đúng |

Một thuật toán “tìm một” chưa hoàn chỉnh nếu chỉ thử vài khả năng rồi trả “không có” khi thất bại. Muốn kết luận vô nghiệm, nó phải duyệt đầy đủ các trường hợp cần thiết hoặc có lập luận loại trừ chắc chắn. Ngược lại, một thuật toán “tìm tất cả” mà trả về ngay khi gặp nghiệm đầu tiên là sai vì **thiếu nghiệm**, dù nghiệm đó hoàn toàn hợp lệ.

## 3. Những điều đặc tả phải nói rõ

1. **Thế nào là một nghiệm?** Xác định cấu trúc đáp án và điều kiện kiểm tra \(Valid\): ví dụ tập chỉ số, đường đi, phép gán biến, hoán vị, lịch xếp việc.
2. **Miền tìm kiếm và ràng buộc:** Đầu vào hữu hạn hay vô hạn? Phần tử có được dùng lại không? Có ràng buộc về độ dài, giá trị, tổng, tính duy nhất hay không?
3. **Phân biệt các nghiệm:** Hai đường đi khác thứ tự có được coi là cùng một lời giải không? Hai phần tử có cùng giá trị nhưng khác vị trí có phân biệt không? Nếu đề bài nói “tập con”, \(\{2,3\}\) và \(\{3,2\}\) là cùng một tập.
4. **Dạng kết quả:** Trả một nghiệm, danh sách mọi nghiệm, bộ đếm, iterator, hay phát từng nghiệm qua callback? Khi không có nghiệm, biểu diễn thế nào?
5. **Thứ tự và giới hạn:** Có cần sắp xếp từ điển hay tăng dần không? Có giới hạn thời gian/bộ nhớ hoặc chỉ lấy tối đa \(k\) nghiệm không? “Tối đa \(k\) nghiệm” là một yêu cầu riêng, không còn đồng nghĩa “tất cả”.
6. **Tiêu chí chấp nhận:** Với “một”, kiểm tra nghiệm thuộc \(S(x)\), và nếu báo không có thì \(S(x)\) phải rỗng. Với “tất cả”, so sánh đúng **toàn bộ tập nghiệm** sau khi chuẩn hóa cách biểu diễn và thứ tự nếu thứ tự không quan trọng.

Nếu \(S(x)\) là vô hạn, việc tạo xong một danh sách hữu hạn “tất cả nghiệm” nói chung là bất khả thi. Khi đó đề bài phải bổ sung miền hữu hạn, giới hạn độ dài, cách mô tả nghiệm bằng quy tắc, hoặc cơ chế sinh nghiệm dần. Không được tự tiện đổi “tất cả” thành “một số nghiệm đầu tiên”.

## 4. Ví dụ xuyên suốt: tổng tập con (Subset Sum)

**Đầu vào:** mảng các số nguyên dương **phân biệt** và mục tiêu \(T\ge 0\).

**Một nghiệm:** chọn một số phần tử, mỗi phần tử **tối đa một lần**, sao cho tổng bằng \(T\). Thứ tự chọn không tạo nghiệm mới. Trong ví dụ, ta giữ thứ tự xuất hiện trong mảng để có một cách biểu diễn thống nhất.

Với mảng [2, 3, 5, 7] và \(T=10\), tập nghiệm là:
- [2, 3, 5], vì \(2+3+5=10\).
- [3, 7], vì \(3+7=10\).

Vì vậy:
- Đề bài “tìm **một** tập con” cho phép trả **[2, 3, 5]** *hoặc* **[3, 7]**.
- Đề bài “tìm **tất cả** tập con” bắt buộc trả đủ **[[2, 3, 5], [3, 7]]**, nếu thứ tự không được chỉ định thì hai nghiệm có thể xuất hiện theo thứ tự khác.
- Với \(T=1\), không có nghiệm: kết quả tìm một là “không có”; kết quả tìm tất cả là **[]**.
- Với \(T=0\), **tập con rỗng là một nghiệm hợp lệ**: kết quả tìm một là một tập con **[]**, còn tìm tất cả là **[[]]**. Cần phân biệt rõ **[]** (không có nghiệm nào trong danh sách) với **[[]]** (danh sách có đúng một nghiệm là tập con rỗng).

Trong bài này, mỗi vị trí chỉ có hai lựa chọn: **chọn** hoặc **bỏ qua**. Hai nhánh này tạo một cây tìm kiếm nhị phân. Ta dùng cùng mô hình trạng thái cho cả hai yêu cầu nhưng khác điều kiện dừng.

## 5. Ví dụ Java 17+ chạy độc lập

Lưu mã dưới tên **AnyVsAllSolutions.java**:

~~~java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;

public final class AnyVsAllSolutions {
    private AnyVsAllSolutions() {
    }

    // Trả một tập con có tổng bằng target, hoặc Optional.empty().
    public static Optional<List<Integer>> findAny(int[] values, int target) {
        validate(values, target);
        List<Integer> path = new ArrayList<>();
        if (searchAny(values, 0, target, path)) {
            return Optional.of(List.copyOf(path));
        }
        return Optional.empty();
    }

    // Trả đầy đủ các tập con có tổng bằng target.
    public static List<List<Integer>> findAll(int[] values, int target) {
        validate(values, target);
        List<List<Integer>> answers = new ArrayList<>();
        searchAll(values, 0, target, new ArrayList<>(), answers);
        return answers;
    }

    private static boolean searchAny(
            int[] values, int index, int remaining, List<Integer> path) {
        if (remaining < 0) {
            return false;
        }
        if (index == values.length) {
            return remaining == 0;
        }

        path.add(values[index]); // Nhánh chọn.
        if (searchAny(values, index + 1, remaining - values[index], path)) {
            return true; // Có nghiệm: giữ path và dừng ngay.
        }
        path.remove(path.size() - 1); // Hoàn tác nếu nhánh chọn thất bại.

        return searchAny(values, index + 1, remaining, path); // Nhánh bỏ.
    }

    private static void searchAll(
            int[] values, int index, int remaining,
            List<Integer> path, List<List<Integer>> answers) {
        if (remaining < 0) {
            return;
        }
        if (index == values.length) {
            if (remaining == 0) {
                answers.add(List.copyOf(path)); // Chụp bản sao của nghiệm.
            }
            return;
        }

        path.add(values[index]); // Nhánh chọn.
        searchAll(values, index + 1, remaining - values[index], path, answers);
        path.remove(path.size() - 1); // Quay lui.
        searchAll(values, index + 1, remaining, path, answers); // Nhánh bỏ.
    }

    private static void validate(int[] values, int target) {
        if (values == null || target < 0) {
            throw new IllegalArgumentException("Mảng phải khác null; target >= 0");
        }
        Set<Integer> seen = new HashSet<>();
        for (int value : values) {
            if (value <= 0 || !seen.add(value)) {
                throw new IllegalArgumentException(
                        "Các phần tử phải dương và phân biệt");
            }
        }
    }

    public static void main(String[] args) {
        int[] values = {2, 3, 5, 7};
        System.out.println("Một nghiệm tổng 10: "
                + findAny(values, 10).map(Object::toString).orElse("không có"));
        System.out.println("Mọi nghiệm tổng 10: " + findAll(values, 10));
        System.out.println("Một nghiệm tổng 1: "
                + findAny(values, 1).map(Object::toString).orElse("không có"));
        System.out.println("Mọi nghiệm tổng 1: " + findAll(values, 1));
        System.out.println("Một nghiệm tổng 0: "
                + findAny(values, 0).map(Object::toString).orElse("không có"));
        System.out.println("Mọi nghiệm tổng 0: " + findAll(values, 0));
    }
}
~~~

Biên dịch và chạy từ thư mục chứa tệp:

~~~bash
javac AnyVsAllSolutions.java
java AnyVsAllSolutions
~~~

Kết quả chuẩn của chương trình:

~~~text
Một nghiệm tổng 10: [2, 3, 5]
Mọi nghiệm tổng 10: [[2, 3, 5], [3, 7]]
Một nghiệm tổng 1: không có
Mọi nghiệm tổng 1: []
Một nghiệm tổng 0: []
Mọi nghiệm tổng 0: [[]]
~~~

**Giải thích cơ chế:** Cả hai thủ tục đệ quy mang trạng thái (index, remaining, path). Trong đó, index là vị trí chưa quyết định tiếp theo, remaining là tổng còn thiếu và path chứa các phần tử đã chọn. Thử nhánh chọn trước nên chương trình tìm nghiệm [2, 3, 5] trước [3, 7]. **searchAny** dùng kiểu trả về boolean để báo đã tìm thấy: khi đúng, lời gọi bên ngoài trả ngay mà không xóa path đang chứa nghiệm. **searchAll** không được dừng ở nghiệm đầu tiên; nó sao chép path vào answers, hoàn tác lựa chọn và tiếp tục nhánh khác. Nếu chỉ thêm trực tiếp đối tượng path (không sao chép), các lần quay lui sau đó sẽ làm thay đổi cả những nghiệm đã lưu.

Phép cắt nhánh remaining < 0 ở đây **chỉ đúng vì mọi phần tử đều dương**: các lựa chọn tiếp theo không thể làm tổng giảm. Nếu cho phép số âm hoặc cơ chế dùng lại phần tử, phải xem xét lại miền nghiệm, điều kiện dừng, cách tránh vòng lặp và tính hợp lệ của phép cắt nhánh. Mã minh họa chủ động từ chối số 0, số âm và giá trị lặp để giữ đúng hợp đồng đã nêu.

## 6. Vì sao hai thuật toán đúng?

**Bất biến trạng thái:** Trước mỗi lời gọi tại index = i, path là tập con của i phần tử đầu tiên, mỗi phần tử được chọn tối đa một lần; remaining = target − tổng(path).

- **Tính hợp lệ:** Chỉ ghi nhận nghiệm khi đã xét đủ phần tử và remaining = 0. Vì bất biến đúng, tổng(path) bằng target. Do mỗi vị trí được xét một lần, không phần tử nào bị chọn hai lần.
- **Tính đầy đủ của findAll:** Mọi tập con tương ứng duy nhất với một chuỗi chọn/bỏ qua trên n vị trí. searchAll xét cả hai nhánh của mỗi vị trí, trừ các nhánh remaining < 0 vốn chắc chắn không thể thành nghiệm với số dương. Do đó mọi nghiệm đều tới một lá được ghi nhận.
- **Không lặp:** Với các giá trị đầu vào phân biệt và mỗi vị trí chỉ quyết định một lần, hai chuỗi chọn/bỏ qua khác nhau không tạo ra cùng một tập giá trị.
- **Đúng của findAny:** Nó chỉ trả một nghiệm khi đi đến lá hợp lệ. Nếu trả Optional.empty(), cả hai nhánh cần thiết đã thất bại, nên không có nghiệm. Việc dừng ngay khi gặp nghiệm đầu tiên phù hợp đúng yêu cầu “một lời giải bất kỳ”.
- **Kết thúc:** Mỗi lời gọi đệ quy tăng index một đơn vị; độ sâu tối đa là n và không có nhánh vô hạn.

Chú ý: Tính đầy đủ là yêu cầu của **tìm tất cả**, nhưng **tìm một** cũng cần duyệt đủ khi kết luận *vô nghiệm*. Hai khái niệm chỉ khác nhau ở thời điểm được phép dừng sau khi đã tìm ra ít nhất một nghiệm.

## 7. Chi phí thời gian, bộ nhớ và quy mô đầu ra

Gọi n là số phần tử, k là số nghiệm được tìm thấy. Cây chọn/bỏ qua có tối đa \(2^n\) lá và \(O(2^n)\) nút.

- **findAny:** Trường hợp tốt có thể dừng sau một nhánh thành công; nhưng trường hợp xấu hoặc vô nghiệm vẫn cần \(O(2^n)\) thời gian. Ngăn xếp đệ quy và path cần \(O(n)\) bộ nhớ phụ, chưa kể bản sao một nghiệm kích thước tối đa n.
- **findAll:** Thời gian \(O(2^n + k\cdot n)\), gồm duyệt cây và sao chép từng nghiệm; bộ nhớ \(O(n+k\cdot n)\) khi giữ toàn bộ nghiệm trong danh sách. Nếu mỗi phần tử là số dương phân biệt, k vẫn có thể rất lớn. Không thể kỳ vọng luôn có thuật toán chạy nhanh hơn kích thước của chính kết quả phải xuất ra.
- **Sinh nghiệm tuần tự:** Nếu không cần giữ mọi nghiệm cùng lúc, có thể dùng callback/iterator để phát từng nghiệm rồi giải phóng bộ nhớ lưu kết quả. Điều này giảm bộ nhớ giữ đầu ra nhưng **không làm biến mất chi phí thời gian liệt kê**; mọi nghiệm vẫn phải được sinh ra.

Trong một số lớp bài toán, ràng buộc và thuật toán chuyên dụng giúp cắt nhánh tốt hơn hoặc trả một nghiệm nhanh hơn. Không được vì thế suy ra rằng mọi bài “tìm một” đều dễ; độ phức tạp phụ thuộc bài toán, đầu vào và thuật toán cụ thể. Khi bài toán đòi hỏi “tất cả” mà số nghiệm khổng lồ, cần công khai giới hạn tài nguyên hoặc thống nhất lại giao diện đầu ra; không âm thầm trả một phần và gọi là đầy đủ.

## 8. Kiểm thử đúng yêu cầu, không phụ thuộc ngẫu nhiên vào thứ tự

| Đầu vào | Yêu cầu một nghiệm | Yêu cầu mọi nghiệm |
|---|---|---|
| [2,3,5,7], T=10 | [2,3,5] **hoặc** [3,7] | Đủ hai nghiệm đó, không lặp |
| [2,3,5,7], T=1 | Không có | [] |
| [2,3,5,7], T=0 | [] là một nghiệm hợp lệ | [[]] |
| Mảng rỗng, T=0 | [] là một nghiệm hợp lệ | [[]] |
| Mảng rỗng, T=5 | Không có | [] |

Khi kiểm thử hàm **findAny**, đừng buộc kết quả luôn bằng một đáp án cụ thể nếu hợp đồng cho phép nhiều nghiệm: hãy xác minh tổng, ràng buộc, khả năng không có nghiệm và tính duy nhất của phần tử được chọn. Khi kiểm thử **findAll**, chuẩn hóa nghiệm theo quy tắc tương đương của bài toán rồi so sánh **tập nghiệm kỳ vọng**, không chỉ kiểm tra rằng các nghiệm đã xuất ra đều đúng. Ví dụ chỉ trả [2,3,5] khi T=10 vẫn vượt qua phép thử “mọi kết quả đều hợp lệ” nhưng **thất bại tính đầy đủ**.

## 9. Sai lầm thường gặp và cách sửa

1. **Trả về khi gặp nghiệm đầu tiên trong bài “tất cả”:** Bỏ mất các nghiệm còn lại. Sửa bằng cách ghi nhận rồi quay lui, duyệt tiếp các nhánh còn khả năng tạo nghiệm.
2. **Nhầm “không có nghiệm” với “nghiệm rỗng”:** Với tổng mục tiêu 0, [] có thể là một nghiệm thật. Dùng biểu diễn phân biệt như Optional.empty() và Optional.of([]), hoặc [] và [[]] cho danh sách mọi nghiệm.
3. **Đếm các hoán vị thành nghiệm khác nhau:** Nếu lời giải là một tập con, [2,3] và [3,2] không phải hai nghiệm. Chốt quy tắc tương đương và dùng thứ tự chỉ số tăng dần hoặc chuẩn hóa.
4. **Không sao chép trạng thái khi lưu mọi nghiệm:** Cùng một danh sách path bị sửa bởi quay lui sẽ làm hỏng kết quả. Dùng List.copyOf(path) hoặc new ArrayList<>(path).
5. **Cắt nhánh bằng giả định không có trong đề:** Kiểm tra remaining < 0 chỉ hợp lệ trong ví dụ số dương. Với dữ liệu khác, phải chứng minh lại điều kiện cắt.
6. **Nói “không có” sau khi tìm kiếm chưa đủ:** Thất bại của một nhánh, một heuristic hoặc một giới hạn thời gian không chứng minh bài toán vô nghiệm. Nếu phải dừng vì tài nguyên, dùng trạng thái riêng như “chưa xác định/không hoàn tất”.
7. **Nhầm mọi nghiệm với nghiệm tối ưu hoặc k nghiệm đầu tiên:** Mỗi yêu cầu có hợp đồng riêng, tiêu chí dừng riêng và kiểm thử riêng.

**Câu hỏi tự kiểm tra:** Với một bài xếp lịch có ba lịch hợp lệ, hàm trả duy nhất lịch đầu tiên có đúng khi đề yêu cầu “một lịch bất kỳ” không? **Có**, nếu lịch đó thỏa mọi ràng buộc. Hàm đó có đúng khi đề yêu cầu “tất cả lịch hợp lệ” không? **Không**, vì còn hai lịch bị bỏ sót. Đây là khác biệt cần chuyển thành điều kiện kiểm chứng cụ thể ngay trong đặc tả trước khi chọn thuật toán.