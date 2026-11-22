# Bài toán quyết định, tìm kiếm, liệt kê, đếm và tối ưu

Trong bản đồ thuật toán, một vấn đề thực tế có thể được đặt thành nhiều **dạng bài toán** tùy câu hỏi cần trả lời. Cùng một dữ liệu đầu vào, yêu cầu “có tồn tại không?”, “hãy tìm một”, “hãy đưa ra tất cả”, “có bao nhiêu?” và “cái nào tốt nhất?” dẫn đến các loại đầu ra, chiến lược giải và chi phí tính toán khác nhau.

## 1. Mô hình chung: thể hiện, nghiệm và ràng buộc

Gọi **x** là một thể hiện (instance) của bài toán, chẳng hạn một tập vật phẩm và một mức tổng mong muốn. Gọi **y** là một phương án ứng viên. Một quan hệ **hợp lệ(x, y)** cho biết phương án y có thỏa yêu cầu của x hay không. Khi đó:

- **S(x) = { y | hợp lệ(x, y) }** là tập nghiệm của thể hiện x.
- **S(x) = ∅** nghĩa là thể hiện không có nghiệm.
- Nếu phải so sánh các nghiệm, bổ sung **hàm mục tiêu f(x, y)** (chi phí, thời gian, lợi nhuận, tổng trọng lượng...) và xác định **tối thiểu hóa** hay **tối đa hóa**.
- Phải mô tả rõ nghiệm nào được coi là khác nhau. Ví dụ, nếu các vật phẩm ở các vị trí khác nhau dù có cùng giá trị, hai cách chọn theo vị trí vẫn có thể là hai nghiệm khác nhau.

Đây là một khung mô hình hóa tiện dụng; không phải mọi bài toán quyết định đều buộc phải viết theo quan hệ tồn tại nghiệm. Tuy nhiên, với bài toán “có nghiệm thỏa điều kiện hay không?”, khung này thể hiện rất rõ sự liên hệ giữa năm dạng.

## 2. Năm dạng bài toán khác nhau ở đầu ra

| Dạng | Câu hỏi đặc trưng | Kết quả cần trả | Trường hợp không có nghiệm |
| --- | --- | --- | --- |
| **Quyết định (decision)** | Có tồn tại nghiệm hợp lệ không? | Một giá trị **Có/Không**, true/false | false |
| **Tìm kiếm (search)** | Hãy tìm một nghiệm hợp lệ. | Một nghiệm y thuộc S(x) | Thông báo không có nghiệm |
| **Liệt kê (enumeration)** | Hãy tìm tất cả nghiệm hợp lệ. | Toàn bộ các nghiệm phân biệt, không bỏ sót và không trùng lặp theo quy ước | Danh sách rỗng |
| **Đếm (counting)** | Có chính xác bao nhiêu nghiệm? | Số nguyên **|S(x)|** | 0 |
| **Tối ưu (optimization)** | Nghiệm hợp lệ nào làm f nhỏ nhất/lớn nhất? | Giá trị tối ưu, nghiệm tối ưu hoặc cả hai, tùy đặc tả | Thông báo vô nghiệm nếu miền khả thi rỗng |

Cần phân biệt **kiểm tra một nghiệm** với **tìm ra nghiệm**. Nếu đã được cho y, việc kiểm tra hợp lệ(x, y) có thể rất nhanh; điều đó chưa có nghĩa là tìm được một y hoặc đếm tất cả y sẽ nhanh.

Tương tự, **giá trị tối ưu** và **nghiệm đạt giá trị ấy** là hai loại kết quả. Với bài toán lập lịch, biết thời gian hoàn thành nhỏ nhất là 12 giờ chưa đồng nghĩa với việc đã tạo ra lịch cụ thể.

## 3. Một ví dụ xuyên suốt: chọn tập con

Có bốn vật phẩm phân biệt theo vị trí với trọng lượng **[2, 3, 5, 7]**. Mỗi vật phẩm được chọn **tối đa một lần** (mô hình 0/1); thứ tự chọn không tạo ra nghiệm mới.

Với **mục tiêu T = 10**, nghiệm hợp lệ cho bốn dạng đầu là một tập con có tổng đúng bằng 10.

- **Quyết định:** “Có tập con tổng bằng 10 không?” → **Có**.
- **Tìm kiếm:** Trả một nghiệm, chẳng hạn **[2, 3, 5]**.
- **Liệt kê:** Có đúng hai nghiệm: **[2, 3, 5]** và **[3, 7]**.
- **Đếm:** Kết quả là **2**, không cần xuất hai tập con.

Với **bài toán tối ưu**, ta đặt thêm ràng buộc sức chứa **C = 10** và câu hỏi: “Chọn tập con có tổng **không vượt quá 10** sao cho tổng lớn nhất.” Giá trị tối ưu là **10**; cả **[2, 3, 5]** và **[3, 7]** đều đạt tối ưu. Nếu đề yêu cầu một nghiệm tối ưu, chỉ cần trả một trong hai; nếu đề yêu cầu mọi nghiệm tối ưu, đó lại là một yêu cầu liệt kê.

**Chú ý về mô hình:** Bốn dạng đầu dùng ràng buộc **tổng = 10**. Bài toán tối ưu dùng miền khả thi **tổng ≤ 10** và mục tiêu **tổng lớn nhất**. Muốn so sánh độ khó hoặc chuyển đổi giữa các dạng, phải nói rõ ràng buộc, hàm mục tiêu và kiểu đầu ra; không chỉ dựa vào tên dạng bài toán.

Nếu thay T bằng một giá trị không thể tạo ra, quyết định trả false, tìm kiếm báo vô nghiệm, liệt kê trả [], đếm trả 0. Với tập con rỗng được phép chọn, tổng bằng 0 luôn có ít nhất một nghiệm: **tập rỗng**.

## 4. Cách thuật toán thay đổi theo yêu cầu

Xét cây lựa chọn nhị phân của n vật phẩm: tại mỗi bước, **chọn** hoặc **bỏ qua** vật phẩm hiện tại. Mọi lá tương ứng với một tập con theo vị trí; có tối đa **2^n** lá.

- **Quyết định:** Dừng ngay khi gặp nghiệm đầu tiên và trả true; nếu đã duyệt hết mà không có thì false.
- **Tìm kiếm:** Dừng khi có nghiệm đầu tiên nhưng đồng thời lưu các lựa chọn để dựng lại nghiệm.
- **Liệt kê:** Không dừng ở nghiệm đầu tiên; ghi nhận từng nghiệm và tiếp tục cho đến khi duyệt đủ không gian tìm kiếm.
- **Đếm:** Không cần lưu từng nghiệm; mỗi nhánh trả số nghiệm của nó, sau đó **cộng** hai kết quả. Nếu số nghiệm lớn, sử dụng kiểu số nguyên đủ rộng.
- **Tối ưu:** Chỉ xét phương án khả thi, so sánh giá trị hàm mục tiêu với kết quả tốt nhất đã biết và cập nhật nghiệm tương ứng.

Các dạng này có thể cùng dùng quay lui (backtracking), quy hoạch động (dynamic programming), chia để trị, nhánh và cận hoặc kỹ thuật chuyên biệt. **Dạng bài toán quy định cần trả gì; kỹ thuật thuật toán quy định giải bằng cách nào.**

### Ví dụ Java 17+: năm cách trả lời trên cùng dữ liệu

Chương trình dưới đây dùng quay lui để bộc lộ rõ sự khác biệt về hành vi. Đây là chương trình Java độc lập, không cần thư viện ngoài JDK. Vật phẩm đều không âm; vì vậy ở bài tối ưu, một nhánh có tổng đã vượt sức chứa có thể bị cắt bỏ an toàn.

~~~java
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.List;

public class ProblemFormsDemo {
    private static final int[] ITEMS = {2, 3, 5, 7};
    private static final int TARGET = 10;
    private static final int CAPACITY = 10;

    public static void main(String[] args) {
        System.out.println("Quyet dinh: " + exists(0, 0));

        List<Integer> one = new ArrayList<>();
        boolean found = findOne(0, 0, one);
        System.out.println("Tim kiem: " + (found ? one : "khong co"));

        List<List<Integer>> all = new ArrayList<>();
        enumerate(0, 0, new ArrayList<>(), all);
        System.out.println("Liet ke: " + all);

        System.out.println("Dem: " + count(0, 0));

        Best best = new Best();
        maximize(0, 0, new ArrayList<>(), best);
        System.out.println("Toi uu: " + best.sum + " " + best.chosen);
    }

    // Có ít nhất một tập con có tổng đúng TARGET?
    private static boolean exists(int index, int sum) {
        if (index == ITEMS.length) {
            return sum == TARGET;
        }
        return exists(index + 1, sum + ITEMS[index])
                || exists(index + 1, sum);
    }

    // Tìm một nghiệm, giữ các vật phẩm đã chọn trong chosen.
    private static boolean findOne(int index, int sum, List<Integer> chosen) {
        if (index == ITEMS.length) {
            return sum == TARGET;
        }

        chosen.add(ITEMS[index]);
        if (findOne(index + 1, sum + ITEMS[index], chosen)) {
            return true;
        }
        chosen.remove(chosen.size() - 1);

        return findOne(index + 1, sum, chosen);
    }

    // Liệt kê mọi tập con có tổng đúng TARGET.
    private static void enumerate(int index, int sum,
                                  List<Integer> chosen,
                                  List<List<Integer>> result) {
        if (index == ITEMS.length) {
            if (sum == TARGET) {
                result.add(new ArrayList<>(chosen));
            }
            return;
        }

        chosen.add(ITEMS[index]);
        enumerate(index + 1, sum + ITEMS[index], chosen, result);
        chosen.remove(chosen.size() - 1);

        enumerate(index + 1, sum, chosen, result);
    }

    // Đếm nghiệm mà không dựng danh sách nghiệm.
    private static BigInteger count(int index, int sum) {
        if (index == ITEMS.length) {
            return sum == TARGET ? BigInteger.ONE : BigInteger.ZERO;
        }

        return count(index + 1, sum + ITEMS[index])
                .add(count(index + 1, sum));
    }

    private static final class Best {
        int sum = -1;
        List<Integer> chosen = List.of();
    }

    // Tối đa hóa tổng, với điều kiện tổng <= CAPACITY.
    private static void maximize(int index, int sum,
                                 List<Integer> chosen, Best best) {
        if (sum > CAPACITY) {
            return;
        }

        if (index == ITEMS.length) {
            if (sum > best.sum) {
                best.sum = sum;
                best.chosen = new ArrayList<>(chosen);
            }
            return;
        }

        chosen.add(ITEMS[index]);
        maximize(index + 1, sum + ITEMS[index], chosen, best);
        chosen.remove(chosen.size() - 1);

        maximize(index + 1, sum, chosen, best);
    }
}
~~~

Lưu thành **ProblemFormsDemo.java**, rồi biên dịch/chạy:

~~~bash
javac ProblemFormsDemo.java
java ProblemFormsDemo
~~~

Đầu ra:

~~~text
Quyet dinh: true
Tim kiem: [2, 3, 5]
Liet ke: [[2, 3, 5], [3, 7]]
Dem: 2
Toi uu: 10 [2, 3, 5]
~~~

**Giải thích kết quả:** Nhánh “chọn” được thử trước nhánh “bỏ”, nên tìm kiếm gặp [2, 3, 5] đầu tiên và liệt kê theo thứ tự thể hiện. Bài đếm dùng **BigInteger** để tránh giới hạn của int/long đối với số nghiệm rất lớn. Bài tối ưu chỉ cập nhật khi tìm thấy tổng **lớn hơn** giá trị đang giữ, vì vậy khi có nhiều nghiệm cùng tối ưu, nó giữ nghiệm tối ưu đầu tiên gặp được.

Đây là ví dụ quy mô nhỏ nhằm làm rõ dạng đầu ra. Không nên dùng thuật toán vét cạn này cho n lớn mà không phân tích giới hạn dữ liệu. Với vật phẩm âm, việc cắt nhánh ngay khi tổng tạm thời vượt CAPACITY không còn đúng vì các vật phẩm âm về sau có thể kéo tổng xuống.

## 5. Độ phức tạp: không chỉ đếm số phép kiểm tra

Với n vật phẩm, thuật toán quay lui cơ bản xét O(2^n) nút/lá trong trường hợp xấu nhất, dùng O(n) ngăn xếp đệ quy. Dạng quyết định và tìm kiếm **có thể dừng sớm**, nhưng trường hợp xấu nhất vẫn phải xét rất nhiều tập con. Bài đếm trong ví dụ cũng duyệt cây, nhưng không cần lưu các nghiệm đã tìm thấy.

Nếu có **k nghiệm**, riêng việc in/liệt kê k nghiệm có độ dài tối đa n đã có thể tốn **Ω(k·n)** ký hiệu đầu ra. Khi k tăng theo hàm mũ của n, không thể đòi thuật toán in toàn bộ nghiệm chạy trong thời gian đa thức theo n mà bỏ qua kích thước đầu ra. Đối với liệt kê, vì vậy cần quan tâm cả **tổng thời gian**, **thời gian trước nghiệm đầu tiên**, **độ trễ giữa các nghiệm** và **bộ nhớ**.

Đếm chỉ xuất một con số, nhưng **đầu ra ngắn không đảm bảo cách tính dễ**: xác định tổng số cấu hình có thể khó hơn nhiều so với kiểm tra một cấu hình. Với nhiều quan hệ nghiệm có thể xác minh trong thời gian đa thức, lý thuyết độ phức tạp nghiên cứu bài đếm qua lớp **#P**. Không phải mọi bài đếm đều khó như nhau, và không nên đồng nhất #P với NP chỉ vì cả hai cùng liên quan đến nghiệm.

### Khi quy hoạch động thay thế quay lui

Với bài tập con **0/1 có trọng lượng nguyên không âm** và mục tiêu/sức chứa T vừa phải, có thể dùng trạng thái theo tổng:

- **Quyết định:** reachable[s] cho biết có tạo được tổng s không. Khởi tạo reachable[0] = true; với từng vật phẩm w, cập nhật các s từ T xuống w bằng **reachable[s] = reachable[s] OR reachable[s-w]**. Kết quả là reachable[T].
- **Tìm kiếm:** Bổ sung thông tin truy vết hoặc giữ bảng theo số vật phẩm và tổng để khôi phục một tập con tạo ra T; một giá trị true đơn lẻ không cho biết chọn vật phẩm nào.
- **Đếm:** ways[s] là số cách chọn theo vị trí để được tổng s. Khởi tạo ways[0] = 1, các vị trí khác bằng 0; lần lượt xử lý mỗi vật phẩm w theo s giảm dần và cập nhật **ways[s] = ways[s] + ways[s-w]**. Nên dùng BigInteger nếu số cách có thể vượt giới hạn số nguyên.
- **Tối ưu:** Với sức chứa C, sau khi đánh dấu các tổng khả đạt từ 0 đến C, tìm **s lớn nhất** sao cho reachable[s] là true. Truy vết thêm để lấy tập con; cách này chỉ tương ứng với mục tiêu **tối đa hóa tổng trọng lượng không vượt C**, không tự động giải mọi bài toán tối ưu.
- **Liệt kê:** Bảng reachable chỉ ghi nhận khả năng tồn tại. Muốn xuất **mọi** nghiệm cần truy ngược qua tất cả lựa chọn hợp lệ hoặc dùng một thuật toán liệt kê khác, chứ không thể chỉ giữ một đường truy vết.

Cập nhật **s giảm dần** là điều kiện quan trọng của DP 0/1 dùng mảng một chiều: nếu duyệt tăng, một vật phẩm có thể vô tình được dùng nhiều lần trong cùng lượt. Với n vật phẩm và các tổng 0..T, DP quyết định có khoảng **O(nT)** phép cập nhật và **O(T)** ô nhớ; DP đếm còn chịu chi phí số học trên các số nguyên lớn. Vì T được mã hóa bằng số bit, O(nT) thường là **giả đa thức (pseudo-polynomial)**, không đồng nghĩa đa thức theo độ dài đầu vào nhị phân.

## 6. Những phép chuyển đổi cần hiểu đúng

### Từ nghiệm sang quyết định

Nếu đã có một nghiệm và kiểm tra được tính hợp lệ của nó, ta chứng minh câu trả lời quyết định là **Có**. Thuật toán tìm kiếm trả “không có nghiệm” một cách chính xác cũng giải được bài quyết định. Thuật toán liệt kê đầy đủ trả danh sách rỗng hay không rỗng cũng quyết định được; bộ đếm chính xác trả **0 hay lớn hơn 0** cũng vậy.

Tuy nhiên, khả năng **kiểm tra** một nghiệm cho trước không tự suy ra khả năng **tìm** nghiệm trong thời gian tương tự. Cũng không nên mặc định một chương trình trả true/false tùy ý đủ để dựng ra chứng cứ: việc chuyển **quyết định → tìm kiếm** cần cấu trúc bổ sung, chẳng hạn khả năng cố định một phần nghiệm rồi hỏi tiếp bài toán quyết định tương ứng (self-reduction).

### Từ tối ưu sang quyết định và ngược lại

Giả sử mục tiêu cần **tối đa hóa f(x, y)** trên các nghiệm hợp lệ. Với một ngưỡng t, ta đặt bài quyết định:

**“Có nghiệm hợp lệ y nào mà f(x, y) ≥ t không?”**

Nếu biết giá trị tối ưu f*, câu trả lời là **Có khi và chỉ khi f* ≥ t**, miễn là miền khả thi không rỗng. Ngược lại, nếu hàm mục tiêu là số nguyên trong một khoảng hữu hạn đã biết và giải được chính xác các câu hỏi ngưỡng, ta có thể **tìm giá trị tối ưu bằng tìm kiếm nhị phân trên ngưỡng**; muốn lấy nghiệm tối ưu cụ thể vẫn cần cách dựng/truy vết nghiệm. Với tối thiểu hóa, đổi chiều ngưỡng thành **f(x, y) ≤ t**.

Phải phân biệt câu hỏi ngưỡng **“giá trị ít nhất t”** với câu hỏi chính xác **“giá trị bằng t”**. Điều kiện bằng t **không nhất thiết đơn điệu** theo t; vì vậy không thể tùy tiện tìm kiếm nhị phân trên các câu trả lời “có tổng đúng bằng t hay không”.

### Liệt kê, đếm và tối ưu không hoán đổi máy móc

- Liệt kê đầy đủ cho phép đếm bằng số phần tử và tính tối ưu bằng cách so sánh mục tiêu, nhưng có thể phải tạo lượng đầu ra khổng lồ.
- Biết **số lượng nghiệm** không cho biết chúng là những nghiệm nào hoặc nghiệm nào tối ưu.
- Biết **một nghiệm tối ưu** không cho biết có bao nhiêu nghiệm tối ưu hay liệt kê được tất cả chúng.
- Cùng một đề bài thực tế, thay đổi định nghĩa “nghiệm” hoặc “phương án phân biệt” làm thay đổi kết quả đếm và liệt kê.

Những mối liên hệ này giúp thiết kế thuật toán và phép giảm bài toán, nhưng **không chứng minh rằng năm dạng luôn có cùng độ khó tính toán**.

## 7. Nhận diện dạng bài và tránh sai lầm

Khi đọc đề, trước tiên xác định **dữ liệu vào**, **điều kiện của nghiệm**, **đầu ra chính xác cần trả**, **cách xử lý vô nghiệm** và **giới hạn n, T, C**. Sau đó mới chọn cấu trúc dữ liệu và thuật toán.

| Dấu hiệu trong đề | Dạng thường gặp | Điều phải làm rõ |
| --- | --- | --- |
| “Có thể...?”, “tồn tại...?” | Quyết định | Chỉ cần true/false, có cần chứng minh/chứng cứ không? |
| “Tìm một cách...”, “đưa ra một đường đi...” | Tìm kiếm | Chấp nhận nghiệm bất kỳ hay có ràng buộc thêm? |
| “Tìm tất cả...”, “in mọi cấu hình...” | Liệt kê | Nghiệm phân biệt thế nào, có thứ tự xuất không? |
| “Có bao nhiêu cách...?” | Đếm | Đếm chính xác, lấy modulo hay chỉ ước lượng? |
| “Ngắn nhất”, “rẻ nhất”, “lớn nhất” | Tối ưu | Hàm mục tiêu, miền khả thi, trả giá trị hay cả phương án? |

Các lỗi phổ biến:

1. **Trả một nghiệm khi đề yêu cầu tất cả.** Tìm được nghiệm đầu tiên không đủ cho liệt kê và đếm.
2. **Đếm trùng do không xác định đồng nhất nghiệm.** Chọn vật phẩm theo vị trí khác chọn theo giá trị; hoán vị khác tổ hợp. Cần thống nhất cách biểu diễn.
3. **Nhầm tối ưu với tìm kiếm bất kỳ.** Một phương án hợp lệ chưa chắc tốt nhất; muốn khẳng định tối ưu phải có thuật toán hoặc chứng minh hỗ trợ.
4. **Quên trường hợp vô nghiệm và tập rỗng.** Với bài tập con, tập rỗng có tổng 0. Tối ưu trên miền rỗng không được tự động gán giá trị 0 nếu đặc tả không cho phép.
5. **Tràn số khi đếm.** Số nghiệm có thể tới 2^n; nếu đề cần kết quả chính xác, chọn kiểu số phù hợp. Nếu đề yêu cầu modulo m, phải nói rõ kết quả chỉ là số dư.
6. **Dùng cắt nhánh hoặc DP ngoài điều kiện áp dụng.** Cắt tổng > T chỉ an toàn khi các số tiếp theo không âm; DP theo tổng cần xem xét miền số và giới hạn giá trị.
7. **Nhầm giả đa thức với đa thức.** Sức chứa cực lớn có thể làm DP O(nC) không khả thi dù n nhỏ.
8. **Cho rằng bài đếm rẻ vì chỉ xuất một số.** Số ký tự đầu ra và công sức tính toán là hai khái niệm khác nhau.

## 8. Tự kiểm tra hiểu bài

**Câu 1.** Một đề yêu cầu “hãy cho biết có thể chia tập công việc thành hai nhóm có tổng thời gian bằng nhau hay không”. Đây là dạng gì?  
**Đáp án:** Quyết định; nếu đề yêu cầu nêu cách chia khi có thể, thêm yêu cầu tìm kiếm.

**Câu 2.** Một đề yêu cầu “in tất cả đường đi đơn từ đỉnh s đến t”. Có thể dừng ngay khi tìm thấy đường đi đầu tiên không?  
**Đáp án:** Không. Đây là liệt kê; cần phát sinh đủ các đường đi đơn, và số đường đi có thể rất lớn.

**Câu 3.** Với [2, 3, 5, 7], nếu chỉ hỏi “có bao nhiêu tập con tổng 10?”, đầu ra là gì?  
**Đáp án:** Số **2**. In ra hai tập con là giải thêm bài liệt kê, không phải đầu ra bắt buộc của bài đếm.

**Ghi nhớ:** Hãy viết rõ một câu về **đầu ra cần có** trước khi lập trình. Câu hỏi đầu ra quyết định bạn đang giải bài quyết định, tìm kiếm, liệt kê, đếm hay tối ưu; sau đó mới đến việc lựa chọn quay lui, quy hoạch động hoặc kỹ thuật khác.