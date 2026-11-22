# Xây dựng lời giải vét cạn làm mốc đối chiếu

Khi gặp một bài toán thuật toán, ta thường muốn tìm ngay cách giải nhanh. Tuy nhiên, trước khi tối ưu, nên có một lời giải **đơn giản, dễ kiểm tra tính đúng đắn** để làm mốc đối chiếu. Lời giải vét cạn (brute force/exhaustive search) là cách phổ biến để tạo ra mốc này: liệt kê có hệ thống các khả năng thuộc miền tìm kiếm, kiểm tra từng khả năng theo đặc tả và trả về kết quả.

Điểm cốt lõi: **lời giải vét cạn làm chuẩn tham chiếu về kết quả, không nhất thiết làm chuẩn về hiệu năng**. Nó giúp ta phát hiện lời giải tối ưu hóa có trả sai đáp án hay không trên những đầu vào đủ nhỏ để chạy cả hai.

Trong nhóm kiến thức **Mô hình và đặc tả**, thứ tự làm việc nên là:

**Đặc tả đầu vào/đầu ra → Xác định toàn bộ ứng viên → Kiểm tra tính hợp lệ → Viết lời giải vét cạn → Chứng minh không bỏ sót → Dùng làm mốc kiểm thử → Tối ưu và so sánh.**

## 1. “Vét cạn” nghĩa là gì và khi nào dùng làm mốc?

Một bài toán có thể yêu cầu **tồn tại** ứng viên hợp lệ, **đếm** số ứng viên, hoặc **tìm ứng viên tốt nhất** theo tiêu chí tối ưu. Lời giải vét cạn phải bám sát đúng loại yêu cầu:

- **Bài toán tồn tại:** duyệt lần lượt các ứng viên; gặp một ứng viên hợp lệ có thể trả về true; duyệt hết mà không có thì trả về false.
- **Bài toán đếm:** duyệt từng ứng viên đúng một lần và tăng bộ đếm cho mỗi ứng viên thỏa điều kiện.
- **Bài toán tối ưu:** duyệt tất cả ứng viên khả thi, theo dõi giá trị tốt nhất; không được dừng ngay ở ứng viên hợp lệ đầu tiên nếu còn ứng viên tốt hơn.

Ví dụ điển hình: xét mọi cặp chỉ số, mọi đoạn con, mọi tập con, hoặc mọi thứ tự sắp xếp. Không phải lúc nào vét cạn cũng có dạng hai vòng lặp; số ứng viên có thể là n², 2ⁿ hoặc n! tùy bài toán.

**Mốc đối chiếu (reference implementation/oracle):** một chương trình trả về kết quả được tin cậy trên miền đầu vào thử nghiệm. Lời giải vét cạn là ứng viên tốt vì thường ngắn, dễ giải thích và gần đặc tả. Nhưng một chương trình vét cạn **vẫn có thể bị lỗi**, nên cần chứng minh phạm vi bao phủ và kiểm tra nó bằng các trường hợp có đáp án đã biết.

## 2. Ví dụ xuyên suốt: có hai phần tử khác vị trí cộng lại bằng target không?

Cho mảng số nguyên values và số nguyên target. Hãy xác định có tồn tại **hai chỉ số khác nhau** i, j sao cho values[i] + values[j] = target hay không.

| Thành phần đặc tả | Quy ước |
| --- | --- |
| Đầu vào | values là mảng int khác null; target là int |
| Đầu ra | boolean: true nếu tồn tại hai **vị trí khác nhau** có tổng đúng target, ngược lại false |
| Miền chỉ số | 0 ≤ i < j < values.length |
| Mảng rỗng hoặc một phần tử | false, vì chưa đủ hai vị trí |
| Hai giá trị bằng nhau | Được phép, miễn chúng ở **hai chỉ số khác nhau** |
| Mảng null | Ném IllegalArgumentException |
| Tác động phụ | Không thay đổi mảng đầu vào |
| So sánh tổng | Dùng kiểu long cho phép cộng để tránh tràn số int |

Lấy values = **[4, 1, 7, 3]**, target = **10**. Ta muốn trả về **true** vì cặp ở chỉ số 2 và 3 có tổng 7 + 3 = 10. Cặp chỉ số 0 và 0 không được xét, dù giá trị ở chỉ số đó có thể được dùng trong những bài toán khác.

Trước khi viết thuật toán, cần phân biệt rõ **giá trị** và **vị trí**: [5, 5] có hai vị trí chứa 5 nên thỏa target = 10; [5] chỉ có một vị trí nên không thỏa.

## 3. Chuyển đặc tả thành phép liệt kê ứng viên

Với mảng độ dài n, tập ứng viên chính xác là **mọi cặp (i, j) thỏa 0 ≤ i < j < n**. Ta chọn i < j để tránh cặp dùng cùng một vị trí và tránh xét cặp đối xứng (i, j) với (j, i) hai lần.

Với [4, 1, 7, 3], toàn bộ ứng viên gồm:

| Cặp chỉ số | Giá trị được cộng | Tổng |
| --- | --- | ---: |
| (0, 1) | 4 + 1 | 5 |
| (0, 2) | 4 + 7 | 11 |
| (0, 3) | 4 + 3 | 7 |
| (1, 2) | 1 + 7 | 8 |
| (1, 3) | 1 + 3 | 4 |
| (2, 3) | 7 + 3 | 10 |

Có 6 cặp, bằng n(n − 1)/2 với n = 4. Vì cặp cuối có tổng bằng target, lời giải trả về true. Với một đầu vào không có cặp phù hợp, ta phải duyệt **hết** các cặp trước khi trả về false.

Mô hình tổng quát của phép vét cạn:

1. **Sinh ứng viên:** liệt kê những cặp chỉ số hợp lệ.
2. **Kiểm tra điều kiện:** tính tổng của hai giá trị và so với target.
3. **Tổng hợp kết quả:** trả true ngay khi tìm thấy; chỉ trả false sau khi duyệt hết mà không tìm thấy.

Giả mã:

~~~text
HAS_PAIR_BRUTE_FORCE(values, target):
    nếu values là null: báo lỗi đầu vào
    cho i từ 0 đến length(values) - 1:
        cho j từ i + 1 đến length(values) - 1:
            sum ← cộng values[i] và values[j] bằng số nguyên đủ rộng
            nếu sum = target:
                trả về true
    trả về false
~~~

Ở đây, “sinh hết ứng viên” không có nghĩa phải tạo và lưu cả danh sách trong bộ nhớ. Hai vòng lặp sinh từng cặp theo nhu cầu.

## 4. Chứng minh lời giải vét cạn là mốc đúng

Một thuật toán vét cạn dùng để kiểm tra thuật toán khác phải có lập luận đúng đắn của riêng nó.

**Tính hợp lệ (soundness):** nếu trả về true, thuật toán đã thực sự tìm thấy một cặp chỉ số i < j và tổng của hai giá trị bằng target. Vì i < j, cặp dùng hai vị trí khác nhau. Do đó kết quả true luôn có nhân chứng hợp lệ.

**Tính đầy đủ (completeness):** giả sử tồn tại một cặp hợp lệ (p, q) với p < q. Vòng lặp ngoài lần lượt nhận mọi i từ 0 tới n − 1. Khi i = p, vòng lặp trong duyệt mọi j từ p + 1 tới n − 1, nên chắc chắn có lúc j = q. Khi đó phép kiểm tra nhận ra cặp hợp lệ và trả về true. Vì vậy không thể bỏ sót cặp cần tìm.

**Khi trả về false:** cả hai vòng lặp đã kết thúc mà không có cặp nào thỏa điều kiện. Do mọi cặp hợp lệ đã được xét, theo tính đầy đủ, không tồn tại cặp có tổng target.

**Tính dừng:** n là độ dài hữu hạn của mảng; i và j tăng trong giới hạn của vòng lặp. Mỗi phép thử có thời gian hữu hạn, nên thuật toán dừng. Đối với n = 0 hoặc n = 1, vòng lặp trong không có lần thực hiện nào và kết quả là false, đúng đặc tả.

Số cặp cần kiểm tra trong trường hợp không tìm thấy là:

\[
\frac{n(n-1)}{2}
\]

Vì vậy, độ phức tạp thời gian tệ nhất là **O(n²)**, bộ nhớ phụ là **O(1)**. Trường hợp may mắn tìm thấy sớm có thể nhanh hơn, nhưng mốc đánh giá thông thường vẫn cần xét trường hợp tệ nhất.

## 5. Java 17+: một chương trình gồm lời giải mốc và lời giải nhanh

Chương trình sau chứa hai cách giải cùng đặc tả:

- **hasPairBruteForce:** dùng hai vòng lặp độc lập với cấu trúc dữ liệu tối ưu.
- **hasPairOptimized:** dùng HashSet để hỏi xem giá trị bù trừ đã xuất hiện **ở một vị trí trước đó** hay chưa. Trung bình, cách này có thời gian O(n) và bộ nhớ phụ O(n).

Đặc biệt, phép cộng và phép trừ liên quan tới target đều chuyển sang **long** trước khi tính, vì biểu thức cộng hai int có thể tràn số và dẫn tới kết quả sai.

Lưu mã dưới đây thành tệp **PairSumOracle.java**:

~~~java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

public final class PairSumOracle {
    private PairSumOracle() {
    }

    public static boolean hasPairBruteForce(int[] values, int target) {
        if (values == null) {
            throw new IllegalArgumentException("values must not be null");
        }

        for (int i = 0; i < values.length; i++) {
            for (int j = i + 1; j < values.length; j++) {
                long sum = (long) values[i] + values[j];
                if (sum == (long) target) {
                    return true;
                }
            }
        }
        return false;
    }

    public static boolean hasPairOptimized(int[] values, int target) {
        if (values == null) {
            throw new IllegalArgumentException("values must not be null");
        }

        Set<Long> seen = new HashSet<>();
        for (int value : values) {
            long complement = (long) target - value;
            if (seen.contains(complement)) {
                return true;
            }
            seen.add((long) value);
        }
        return false;
    }

    private static void checkAllSmallCases() {
        int[] alphabet = {-2, -1, 0, 1, 2};
        long checked = 0L;

        for (int length = 0; length <= 5; length++) {
            int arrangements = 1;
            for (int k = 0; k < length; k++) {
                arrangements *= alphabet.length;
            }

            for (int encoded = 0; encoded < arrangements; encoded++) {
                int[] values = new int[length];
                int remainder = encoded;
                for (int i = 0; i < length; i++) {
                    values[i] = alphabet[remainder % alphabet.length];
                    remainder /= alphabet.length;
                }

                for (int target = -4; target <= 4; target++) {
                    boolean expected = hasPairBruteForce(values, target);
                    boolean actual = hasPairOptimized(values, target);
                    if (actual != expected) {
                        throw new AssertionError(
                            "Mismatch: values=" + Arrays.toString(values)
                            + ", target=" + target
                            + ", bruteForce=" + expected
                            + ", optimized=" + actual
                        );
                    }
                    checked++;
                }
            }
        }
        System.out.println("Checked " + checked + " cases: PASS");
    }

    public static void main(String[] args) {
        System.out.println(hasPairBruteForce(new int[] {4, 1, 7, 3}, 10));
        System.out.println(hasPairBruteForce(new int[] {5, 5}, 10));
        System.out.println(hasPairBruteForce(new int[] {5}, 10));
        System.out.println(hasPairBruteForce(
            new int[] {Integer.MAX_VALUE, Integer.MAX_VALUE}, -2
        ));
        checkAllSmallCases();
    }
}
~~~

Tại thư mục chứa tệp, chạy:

~~~bash
javac PairSumOracle.java
java PairSumOracle
~~~

Đầu ra kỳ vọng:

~~~text
true
true
false
false
Checked 35154 cases: PASS
~~~

Bốn dòng boolean minh họa: có cặp thường; có hai phần tử 5 ở hai vị trí; mảng chỉ có một phần tử; và phản ví dụ tràn số. Cụ thể, Integer.MAX_VALUE + Integer.MAX_VALUE nếu tính bằng int sẽ bị tràn thành -2, nhưng tổng toán học của hai số này **không phải -2**. Hai cách giải dùng long để kết luận false cho target = -2.

Dòng cuối cho biết chương trình đã so sánh hai cách giải trên **35.154 trường hợp nhỏ** và không phát hiện sai khác. Đây là kết quả kiểm thử có hệ thống, không thay thế cho chứng minh đúng đắn.

## 6. Vì sao cách so sánh hàng chục nghìn trường hợp hoạt động?

Trong phương thức checkAllSmallCases, bộ giá trị thử là {-2, -1, 0, 1, 2}. Mọi mảng độ dài từ 0 tới 5 được tạo từ bộ này, bao gồm mảng rỗng, phần tử trùng nhau, số âm và số 0. Mỗi mảng được thử với từng target nguyên từ -4 tới 4.

Số mảng khác nhau theo độ dài (có tính thứ tự) là:

\[
5^0 + 5^1 + 5^2 + 5^3 + 5^4 + 5^5
= 1 + 5 + 25 + 125 + 625 + 3125
= 3906.
\]

Có 9 giá trị target nên tổng số phép so sánh đầu ra là **3906 × 9 = 35.154**. Mỗi lần thử đều tính:

- expected = hasPairBruteForce(values, target);
- actual = hasPairOptimized(values, target);
- nếu expected khác actual thì ném AssertionError kèm mảng, target và hai kết quả, giúp tái hiện trường hợp sai.

Đây là **kiểm thử đối chiếu (differential testing)**: cùng một đầu vào, hai cách hiện thực khác nhau phải cho kết quả giống nhau theo cùng một đặc tả. Với bài toán trả về boolean, có thể so sánh trực tiếp. Nếu bài toán trả về **một cặp chỉ số bất kỳ**, hai lời giải có thể trả về hai cặp khác nhau nhưng đều đúng; khi đó phải kiểm tra điều kiện hợp lệ hoặc chuẩn hóa đầu ra trước khi so sánh, không đòi các chỉ số giống hệt nhau.

Cách tạo dữ liệu trong chương trình là **vét cạn miền thử nhỏ**, chứ không vét cạn toàn bộ miền int hay mọi mảng có độ dài tùy ý. Bằng chứng kiểm thử chỉ bao phủ giới hạn cụ thể đó.

## 7. Cách lập mốc đối chiếu đáng tin cậy

**Bước 1 — Chốt hợp đồng chung.** Định nghĩa đầu vào, đầu ra, kết quả của trường hợp không có lời giải, tính hợp lệ của ứng viên và cách xử lý null. Nếu mốc và bản tối ưu có các hợp đồng khác nhau, kết quả đối chiếu sẽ gây hiểu nhầm.

**Bước 2 — Ưu tiên cách viết rõ ràng.** Trong mốc vét cạn, hai vòng lặp theo chỉ số bám sát phát biểu “có hai vị trí khác nhau”. Tránh thêm cắt tỉa hoặc tối ưu khó chứng minh khiến cả mốc cũng trở nên phức tạp.

**Bước 3 — Chứng minh không bỏ sót.** Nêu được một ánh xạ từ **mọi ứng viên hợp lệ** tới **một lượt kiểm tra cụ thể** trong chương trình. Với ví dụ này, mọi cặp (p, q) với p < q đều được kiểm tra tại i = p, j = q.

**Bước 4 — Thử các trường hợp có đáp án hiển nhiên.** Đối với mảng rỗng, một phần tử, cặp trùng giá trị và tổng âm, ta có thể suy luận trực tiếp mà không cần tin vào bất kỳ cách hiện thực nào.

**Bước 5 — Chạy đối chiếu trên đầu vào nhỏ.** Trước tiên kiểm thử cố định và các trường hợp biên, sau đó sinh có hệ thống các trường hợp nhỏ hoặc tạo dữ liệu ngẫu nhiên với seed cố định để có thể tái hiện.

**Bước 6 — Thu nhỏ phản ví dụ.** Nếu hai cách khác nhau, tìm một mảng ngắn hơn hoặc giá trị đơn giản hơn vẫn giữ được lỗi. Lưu trường hợp đó làm regression test, tìm lỗi trong cả mốc lẫn bản tối ưu và kiểm tra lại đặc tả.

**Bước 7 — Đo hiệu năng riêng.** Khi kiểm thử kết quả đã ổn, mới benchmark với dữ liệu đủ lớn, tách thời gian tạo đầu vào khỏi thời gian đo và không dùng vét cạn ở kích thước gây tăng chi phí quá mức.

## 8. Những trường hợp biên cần có ngoài phép kiểm thử đối chiếu

| Trường hợp | Ví dụ | Kỳ vọng | Lỗi dễ gặp |
| --- | --- | --- | --- |
| Mảng rỗng | [], target = 0 | false | Truy cập values[0] |
| Một phần tử | [5], target = 10 | false | Dùng lại cùng vị trí |
| Giá trị trùng | [5, 5], target = 10 | true | Loại bỏ bản sao theo giá trị |
| Có số âm | [-4, 7, 1], target = 3 | true | Giả thiết dữ liệu chỉ dương |
| Có số 0 | [0, 0], target = 0 | true | Bỏ qua số 0 hoặc vị trí thứ hai |
| Không có cặp | [1, 2, 4], target = 8 | false | Trả true không có nhân chứng |
| Biên int | [MAX_VALUE, MAX_VALUE], target = -2 | false | Tổng int tràn thành -2 |
| Tổng âm hợp lệ | [MIN_VALUE, MAX_VALUE], target = -1 | true | Sai ở giá trị biên |
| Thứ tự thay đổi | [3, 7, 4, 1], target = 10 | true | Phụ thuộc thứ tự ngẫu nhiên |
| Null | null | IllegalArgumentException | Hợp đồng lỗi không nhất quán |

Có thể kiểm tra một số **thuộc tính độc lập**: hoán vị mảng không làm thay đổi kết quả boolean; nếu tìm thấy cặp thì hai vị trí phải khác nhau; nếu mảng có hai phần tử thì phép thử chỉ phụ thuộc tổng của chính hai phần tử đó. Thuộc tính độc lập rất hữu ích để phát hiện trường hợp **cả mốc và bản tối ưu cùng mắc một lỗi**.

## 9. Phản ví dụ cho các “tối ưu” sai

Một phiên bản HashSet sai thường thực hiện theo thứ tự **thêm value vào seen trước, rồi mới hỏi seen có target − value hay không**. Với mảng [5] và target = 10, cách đó tìm ra chính 5 vừa thêm và trả true, trong khi không có hai chỉ số khác nhau. Bản đúng phải **kiểm tra trước, thêm sau** như trong chương trình.

Một phiên bản khác dùng HashSet<Integer> và tính complement = target - value bằng int. Với target và value ở biên của int, phép trừ có thể tràn số; phép tính sai vẫn có thể tình cờ khớp một phần tử nào đó. Dùng long tránh lỗi này.

Một bản vét cạn cũng có thể sai nếu vòng lặp trong bắt đầu từ j = i, vì nó cho phép dùng cùng một phần tử hai lần. Nếu j bắt đầu từ i + 2, nó bỏ sót những cặp liền kề. Các lỗi này giải thích vì sao cần **đánh giá đúng đắn của oracle** bằng đặc tả và phản ví dụ trước khi tin kết quả đối chiếu.

## 10. Áp dụng ý tưởng mốc vét cạn cho những lớp bài toán khác

| Bài toán | Miền ứng viên vét cạn | Ý tưởng mốc | Chi phí tham khảo |
| --- | --- | --- | --- |
| Tìm hai phần tử có tổng target | Mọi cặp chỉ số i < j | Kiểm tra từng tổng | O(n²) |
| Tìm đoạn con có tổng lớn nhất | Mọi cặp biên đoạn (l, r) | Cộng các phần tử trong từng đoạn, lấy max | O(n³) nếu tính tổng lại từ đầu cho mỗi đoạn |
| Chọn tập con thỏa ràng buộc | Mọi tập con của n phần tử | Sinh tập con, kiểm tra điều kiện | Có 2ⁿ tập con; thời gian còn phụ thuộc chi phí kiểm tra từng tập |
| Bài toán thứ tự | Mọi hoán vị của n phần tử | Kiểm tra/tính điểm từng hoán vị | Có n! hoán vị; thời gian còn phụ thuộc chi phí tính điểm |
| Tìm một đường đi đơn trong đồ thị nhỏ | Mọi đường đi không lặp đỉnh thỏa giới hạn | Sinh và kiểm tra đường đi | Có thể tăng theo hàm mũ; phải ràng buộc tránh vòng lặp vô hạn |

Ví dụ, nếu đang kiểm tra một thuật toán O(n) tìm tổng đoạn con lớn nhất, có thể dùng lời giải O(n³) làm oracle với mảng rất ngắn. Nếu đang kiểm tra một thuật toán quy hoạch động cho tập con, có thể liệt kê tất cả 2ⁿ tập con cho n nhỏ để so sánh. Mốc vét cạn thường dễ nghĩ ra, còn thuật toán tối ưu có thể dùng tham lam, chia để trị, quy hoạch động, cấu trúc dữ liệu hoặc biến đổi toán học.

**Giới hạn thực dụng:** với bài tăng theo 2ⁿ hoặc n!, tuyệt đối không mở rộng kích thước thử một cách máy móc. Mục tiêu của oracle là chạy **đủ nhiều dữ liệu nhỏ để phát hiện sai**, không phải dùng oracle xử lý dữ liệu sản xuất.

## 11. Phân biệt các kiểu “đúng” trước khi tin phép so sánh

Có ba vấn đề khác nhau:

1. **Đặc tả đúng:** chương trình có thực sự giải bài toán cần giải không? Ví dụ “hai phần tử” có cho phép cùng chỉ số hay không?
2. **Oracle đúng:** nó có sinh đủ ứng viên và kiểm tra điều kiện không? Vòng lặp có bỏ cặp nào hay tính sai số học không?
3. **Bản tối ưu đúng:** nó có giữ nguyên ý nghĩa của đầu ra không? Khi tiết kiệm thời gian, có vô tình loại mất phương án hợp lệ không?

Việc bản tối ưu khớp oracle trên 35.154 trường hợp **không tự chứng minh** đúng với mọi int[]; vẫn cần suy luận logic và các test biên không nằm trong bảng thử nhỏ, như Integer.MIN_VALUE và Integer.MAX_VALUE. Đồng thời, nếu oracle và bản tối ưu giống nhau trong một lỗi chung, chỉ so sánh chéo sẽ không phát hiện được. Vì vậy nên kết hợp **chứng minh + test có đáp án độc lập + differential testing**.

## 12. Bài tập tự áp dụng và checklist

**Bài tập:** Cho mảng số nguyên a, tìm **độ dài đoạn con liên tiếp dài nhất có tổng bằng k**. Hãy tự viết đặc tả cho trường hợp không tồn tại đoạn thỏa, sau đó viết oracle: chọn mọi l từ 0 tới n − 1, mọi r từ l tới n − 1, cộng a[l..r] rồi cập nhật độ dài lớn nhất nếu tổng bằng k. Với mảng rỗng, có thể quy ước kết quả là 0 nếu đề xác nhận không tính đoạn rỗng là ứng viên. Đừng dùng kết quả của thuật toán tối ưu để định nghĩa đáp án của oracle.

Tự kiểm tra một oracle trước khi dùng làm mốc:

- Đầu vào và đầu ra có được đặc tả rõ, kể cả trường hợp vô nghiệm và biên không?
- Có thể chỉ ra **mọi ứng viên hợp lệ** đều được một lượt lặp xét đến không?
- Khi chương trình chấp nhận một ứng viên, có chắc ứng viên thỏa toàn bộ điều kiện không?
- Số học, chỉ số và xử lý phần tử trùng đã tuân theo đặc tả chưa?
- Mốc có đủ đơn giản để kiểm tra độc lập và chạy được trên kích thước thử nhỏ không?
- Bản tối ưu có dùng **cùng hợp đồng đầu ra**; các kết quả được so sánh theo ngữ nghĩa đúng không?
- Khi phát hiện sai khác, có lưu đầu vào tối giản thành regression test để tránh tái phát không?

Năng lực quan trọng nhất ở đây là biến một đặc tả thành **một thủ tục tham chiếu có thể kiểm chứng**. Khi đã có thủ tục đó, mọi thay đổi để làm thuật toán nhanh hơn đều có một mốc kết quả cụ thể để thử lại.
