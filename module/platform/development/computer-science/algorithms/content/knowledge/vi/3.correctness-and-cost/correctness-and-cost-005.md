# Chứng minh tối ưu bằng cận và đối chiếu lời giải

## 1. “Tối ưu” nghĩa là gì?

Một thuật toán **đúng** tạo ra kết quả thỏa đặc tả. Một thuật toán **tối ưu** còn phải đạt một tiêu chí tốt nhất đã được nêu rõ. Trong khoa học thuật toán, hai câu hỏi sau khác nhau:

1. **Thuật toán có chi phí tính toán tối ưu không?** Ví dụ: để tìm phần tử lớn nhất trong mảng chưa sắp xếp, có thể dùng ít hơn n − 1 phép so sánh trong trường hợp xấu nhất hay không?
2. **Lời giải mà thuật toán trả về có giá trị mục tiêu tối ưu không?** Ví dụ: cách đổi tiền trả về có dùng ít đồng xu nhất trong tất cả các cách đổi hợp lệ hay không?

Một thuật toán có thể tìm đúng nghiệm tối ưu nhưng chạy chậm; ngược lại, một thuật toán chạy nhanh có thể chỉ đưa ra nghiệm gần tối ưu. Phải xác định đang chứng minh tính chất nào, với **đầu vào**, **mô hình tính toán**, **hàm mục tiêu**, **giả định** và **kiểu đánh giá chi phí** nào.

Bài học này tập trung vào hai công cụ hỗ trợ nhau:

- **Chứng minh bằng cận:** đưa ra giới hạn mà mọi lời giải hoặc mọi thuật toán thuộc phạm vi xét phải tuân theo, rồi đối chiếu với phương án cụ thể.
- **Đối chiếu lời giải:** dùng một lời giải tham chiếu độc lập, cách kiểm tra khác hoặc phép liệt kê đầy đủ để phát hiện sai sót và kiểm nghiệm các điều kiện đã đặc tả.

Đối chiếu bằng kiểm thử tăng độ tin cậy; bản thân số lượng lớn các ca kiểm thử **không thay thế** chứng minh tổng quát.

## 2. Chuẩn hóa bài toán trước khi tìm cận

Một tuyên bố “tối ưu” có ý nghĩa khi trả lời đủ các câu hỏi sau.

| Câu hỏi | Ví dụ cần làm rõ |
| --- | --- |
| Đầu vào hợp lệ là gì? | Mảng có thể rỗng, trùng giá trị, sắp xếp sẵn hay không? |
| Đầu ra đúng là gì? | Trả giá trị lớn nhất, chỉ số đầu tiên của nó, hay mọi chỉ số đồng hạng? |
| Mục tiêu tối ưu là gì? | Ít phép so sánh nhất, ít thời gian nhất, ít bộ nhớ nhất, hay giá trị nghiệm nhỏ nhất? |
| Chi phí đo thế nào? | Số phép so sánh, thời gian RAM, số truy cập đĩa, số bước đệ quy? |
| Phạm vi so sánh là gì? | Mọi thuật toán so sánh, mọi thuật toán tất định, hay thuật toán đã biết? |
| Phân tích trường hợp nào? | Tốt nhất, xấu nhất, trung bình, kỳ vọng hay amortized? |
| Kích thước dữ liệu là gì? | n phần tử, số đỉnh V và cạnh E, giá trị đích T, hay độ dài bit? |
| Có cho phép tiền xử lý? | Dữ liệu đã sắp xếp từ trước hay chi phí sắp xếp phải tính vào tác vụ? |

Ví dụ, khẳng định “tìm kiếm nhị phân là tối ưu O(log n)” phải nói rằng dữ liệu **đã sắp xếp**, phép truy cập vị trí bất kỳ là O(1) và kết quả cần xác định được vị trí/biên cần tìm theo mô hình so sánh. Nếu đầu vào là mảng bất kỳ hoặc thời gian tạo cấu trúc tra cứu chưa được tính, kết luận ấy không tự áp dụng.

Cũng cần phân biệt:

- **Cận trên của chi phí thuật toán:** bảo đảm thuật toán cụ thể dùng *không quá* một mức chi phí tiệm cận, chẳng hạn O(n).
- **Cận dưới của độ khó bài toán:** chứng minh *mọi* thuật toán được phép trong mô hình phải tốn *ít nhất* một mức chi phí trên trường hợp được định lượng, chẳng hạn Ω(n).
- **Cận chặt:** khi cận trên và cận dưới trùng bậc, chi phí tối ưu trong phạm vi xét là Θ(n).

Ký hiệu O, Ω và Θ mô tả **tốc độ tăng tiệm cận**; chúng không tự khẳng định hai thuật toán có hằng số thời gian như nhau. Kết luận trong trường hợp xấu nhất cũng không tự suy ra tối ưu ở trung bình hoặc về bộ nhớ.

## 3. Khuôn chứng minh chi phí thuật toán tối ưu

Giả sử một lớp bài toán có kích thước đầu vào n và mô hình chi phí C.

**Bước 1 — Xây dựng thuật toán và cận trên.** Chỉ ra thuật toán A đúng, kết thúc và có chi phí xấu nhất U(n). Điều này chứng tỏ bài toán *có thể* giải với chi phí không vượt cận ấy.

**Bước 2 — Chứng minh cận dưới cho mọi thuật toán hợp lệ.** Thiết lập L(n) sao cho bất kỳ thuật toán nào trong mô hình cũng cần ít nhất L(n) chi phí trong trường hợp xấu nhất. Cách chứng minh phải lượng hóa trên **mọi thuật toán**, không chỉ chỉ ra một tình huống khiến thuật toán A chạy chậm.

**Bước 3 — So khớp cận.** Nếu U(n) = O(f(n)) và L(n) = Ω(f(n)), thì độ phức tạp tối ưu xấu nhất trong mô hình là Θ(f(n)). Nếu chỉ biết O(n log n) và Ω(n), chưa đủ để khẳng định thuật toán tối ưu tiệm cận: khoảng cách giữa hai cận có thể còn cải thiện được.

**Bước 4 — Nêu đúng phạm vi kết luận.** Ghi rõ giả định về phép toán, dữ liệu, thuật toán được xét và thước đo chi phí. Một cận dưới cho *thuật toán dựa trên so sánh* không tự trở thành cận dưới cho thuật toán sử dụng bảng tra hoặc cấu trúc miền khóa đặc biệt.

Những kỹ thuật phổ biến để dựng cận dưới gồm:

- **Lập luận đối kháng (adversary):** sau mỗi thao tác, chỉ ra còn bao nhiêu khả năng chưa thể loại trừ.
- **Cây quyết định / lượng thông tin:** nếu phải phân biệt K khả năng, cây có nhánh hữu hạn cần đủ độ sâu để có ít nhất K lá.
- **Quy giản (reduction):** nếu giải được bài toán B quá nhanh sẽ kéo theo cách giải bài toán A nhanh hơn cận dưới đã chứng minh của A; phải tính cả chi phí biến đổi đầu vào/đầu ra.
- **Lập luận phải khảo sát dữ liệu:** chứng minh mỗi phần tử hoặc phần thông tin có thể làm đổi kết quả; không chỉ nói “dường như phải đọc tất cả”.

## 4. Ví dụ 1: tìm phần tử lớn nhất cần n − 1 phép so sánh

### 4.1. Đặc tả

Cho mảng số nguyên không rỗng, chưa giả định đã sắp xếp, độ dài n ≥ 1. Trả về **chỉ số nhỏ nhất** của một phần tử có giá trị lớn nhất; không sửa mảng. Ta đếm phép so sánh **giữa hai phần tử dữ liệu**; phép kiểm tra điều kiện vòng lặp và xử lý null không tính vào thước đo này.

Một cách giải: giữ chỉ số best, lần lượt so sánh a[i] với a[best], cập nhật best khi gặp giá trị **lớn hơn**. Dùng dấu > thay vì >= giúp giữ chỉ số đầu tiên nếu nhiều phần tử cùng lớn nhất.

### 4.2. Cận trên và tính đúng

Ban đầu best = 0. Sau khi xét i phần tử đầu tiên, bất biến là: **best chỉ đến phần tử lớn nhất đầu tiên trong đoạn a[0..i−1]**.

- Khởi tạo: với một phần tử, best = 0 là đúng.
- Duy trì: khi xét a[i], nếu lớn hơn cực đại cũ thì cập nhật; nếu bằng hoặc nhỏ hơn thì giữ best. Do đó cực đại đầu tiên của đoạn đã xét luôn được lưu.
- Kết thúc: sau khi duyệt đủ n phần tử, best là chỉ số cực đại đầu tiên của toàn mảng.

Vòng lặp chạy với i = 1, 2, …, n − 1, đúng **n − 1 lần so sánh giữa phần tử dữ liệu**. Vậy chi phí theo thước đo đã chốt là n − 1, thời gian O(n), bộ nhớ phụ O(1). Với n = 1, số so sánh bằng 0.

### 4.3. Cận dưới bằng đối kháng

Xét trước tập con đầu vào có **n giá trị đôi một khác nhau**. Ban đầu, bất kỳ phần tử nào cũng có thể là lớn nhất. Sau một phép so sánh hai phần tử, phần tử nhỏ hơn được chứng minh **không thể** là cực đại; một phép so sánh có thể loại khỏi danh sách ứng viên nhiều nhất **một** phần tử trước đó chưa bị loại. Để xác định duy nhất cực đại, phải loại ít nhất n − 1 ứng viên. Bởi vậy mọi thuật toán chỉ dựa vào so sánh cần **ít nhất n − 1 phép so sánh trong trường hợp xấu nhất**.

Lập luận trên tập con các giá trị phân biệt đủ để chứng minh cận dưới cho bài toán tổng quát có thể chứa giá trị trùng: thuật toán giải mọi đầu vào cũng phải giải đúng tập con ấy.

Ta đã có:

~~~text
Cận dưới cho bài toán (mô hình so sánh): n - 1.
Cận trên của thuật toán duyệt:           n - 1.
Kết luận: thuật toán đạt số so sánh tối ưu xấu nhất.
~~~

Cần phát biểu chính xác: thuật toán duyệt **tối ưu về số phép so sánh** trong mô hình này; nhận định không đồng nghĩa tối ưu về thời gian máy thực tế trong mọi hệ thống, về số lần truy cập bộ nhớ hoặc với đầu vào đã có cấu trúc bổ sung. Nếu mảng được bảo đảm tăng dần và chỉ cần giá trị lớn nhất, đọc phần tử cuối đã đủ; giả định bài toán đã đổi.

## 5. Ví dụ 2: sắp xếp dựa trên so sánh có cận dưới Ω(n log n)

Với n khóa **phân biệt**, có n! thứ tự đầu vào khác nhau. Một thuật toán sắp xếp chỉ xác định thứ tự qua so sánh hai khóa có thể được biểu diễn bằng **cây quyết định**; ở tập con khóa phân biệt, mỗi phép so sánh có hai kết quả (< hoặc >).

Để phân biệt đúng n! hoán vị, cây cần ít nhất n! lá. Cây nhị phân có độ sâu xấu nhất h chứa tối đa 2^h lá, vì thế:

~~~text
2^h >= n!
h >= ceil(log2(n!))
log2(n!) = Theta(n log n)
=> Số phép so sánh trong trường hợp xấu nhất là Omega(n log n).
~~~

Merge sort dựa trên so sánh chạy O(n log n), nên kết hợp cận dưới với cận trên chứng minh bậc Θ(n log n) là tối ưu **trong mô hình sắp xếp bằng so sánh**.

Điều này không phủ nhận counting sort O(n + k) khi các khóa là số nguyên thuộc miền hữu hạn có k giá trị, vì thuật toán ấy tận dụng trực tiếp **giá trị khóa và miền khóa**, không bị giới hạn vào so sánh cặp khóa. Muốn so sánh công bằng còn phải tính bộ nhớ O(k), điều kiện đầu vào và cách biểu diễn khóa.

**Lỗi suy luận hay gặp:** “Merge sort là O(n log n), nên không thuật toán nào nhanh hơn.” Cận trên của một thuật toán không chứng minh giới hạn của mọi thuật toán. Kết luận tối ưu chỉ xuất hiện sau khi chứng minh cận dưới độc lập.

## 6. Tối ưu **giá trị nghiệm** bằng cận dưới và cận trên

Với bài toán cực tiểu, đặt F là tập mọi nghiệm khả thi và f(x) là chi phí của nghiệm x:

~~~text
OPT = min { f(x) : x thuộc F }.
~~~

Để xác nhận một nghiệm ứng viên x* là tối ưu, cần:

1. **Chứng nhận khả thi:** x* ∈ F.
2. **Cận trên từ nghiệm:** U = f(x*) nên OPT ≤ U.
3. **Cận dưới hợp lệ:** chứng minh L ≤ f(x) với mọi x ∈ F, tức L ≤ OPT.
4. **Khớp cận:** nếu L = U, suy ra L ≤ OPT ≤ U và do đó OPT = f(x*).

Đối với bài toán **cực đại**, chiều cận đảo lại: nghiệm khả thi cho **cận dưới** L = f(x*) ≤ OPT, còn một lập luận trên mọi nghiệm khả thi cho **cận trên** OPT ≤ U. Khi L = U, nghiệm tối ưu.

Nếu L < U trong bài toán cực tiểu, **chưa thể kết luận** x* không tối ưu. Cận dưới có thể còn quá yếu. Đồng thời, dù nghiệm đã được chứng minh tối ưu về giá trị, thuật toán tìm ra nó vẫn có thể tốn thời gian không tối ưu.

### Ví dụ: đổi tiền với số đồng xu ít nhất

Giả sử có số lượng không giới hạn các đồng xu mệnh giá {1, 4, 6}, mỗi đồng xu có giá trị dương, và cần đổi **đúng 8 đơn vị** với **ít đồng xu nhất**.

**Cận dưới:** một đồng xu trị giá tối đa 6; dùng k đồng thì tổng giá trị nhiều nhất là 6k. Muốn đạt 8, bắt buộc k × 6 ≥ 8, nên:

~~~text
OPT >= ceil(8 / 6) = 2.
~~~

**Cận trên:** cách đổi [4, 4] có tổng bằng 8, dùng đúng 2 đồng; đó là một nghiệm khả thi, nên OPT ≤ 2.

**Kết luận:** 2 ≤ OPT ≤ 2, vậy **OPT = 2**; [4, 4] là nghiệm tối ưu toàn cục.

Nếu áp dụng tham lam chọn mệnh giá lớn nhất trước, ta nhận [6, 1, 1] với 3 đồng. Nghiệm đó vẫn khả thi nhưng **không tối ưu**. Đây là phản ví dụ cụ thể cho quy tắc tham lam trên hệ mệnh giá này.

Cận ceil(T / maxCoin) là hợp lệ cho mọi T ≥ 0 và mọi hệ mệnh giá dương nhưng **không phải lúc nào cũng chặt**. Nếu chưa tìm được nghiệm đạt cận, phải dùng chứng minh mạnh hơn hoặc phương pháp giải chính xác như duyệt đầy đủ, quy hoạch động hay branch-and-bound. Không được ép kết quả ứng viên khớp cận bằng cách bỏ qua ràng buộc “đổi đúng T”.

## 7. Đối chiếu lời giải: oracle, vét cạn và kiểm tra thuộc tính

**Oracle** là cách độc lập cho biết đáp án đúng của các trường hợp kiểm tra. Nó có thể chậm hơn thuật toán cần kiểm chứng nhưng phải dễ lý giải và có miền áp dụng rõ ràng.

Một quy trình thực tế:

1. **Xây baseline đơn giản:** ví dụ, duyệt đầy đủ tất cả nghiệm cho kích thước nhỏ; so sánh với thuật toán chính.
2. **Định nghĩa tiêu chuẩn tương đương:** nếu có nhiều nghiệm tối ưu, so sánh **tính khả thi và giá trị mục tiêu**, không bắt buộc hai phương pháp trả cùng một biểu diễn.
3. **Bao phủ biên:** n = 1, giá trị trùng, âm, tất cả bằng nhau, nghiệm không tồn tại, chi phí bằng nhau, dữ liệu tối đa trong phạm vi kiểm thử.
4. **Kiểm thử có hệ thống:** liệt kê mọi đầu vào trong miền nhỏ hoặc sinh dữ liệu ngẫu nhiên có seed cố định, giữ lại phản ví dụ nhỏ nhất khi có khác biệt.
5. **Kiểm tra tính chất:** kết quả không vi phạm tiền/hậu điều kiện, mảng không bị sửa khi hợp đồng cấm, nghiệm luôn khả thi; có thể áp dụng biến đổi bảo toàn tính chất (metamorphic test).
6. **Phân tích riêng chi phí:** đếm thao tác theo mô hình hoặc chạy benchmark có kiểm soát; không dùng thời gian một vài đầu vào làm chứng minh cận dưới cho mọi thuật toán.

Với bài tìm cực đại, thư viện duyệt dòng dữ liệu để lấy giá trị max, sau đó tìm **lần xuất hiện đầu tiên** của giá trị ấy có thể làm oracle độc lập cho chỉ số. Với bài đổi tiền nhỏ, vét cạn mọi lựa chọn đồng xu là oracle cho số lượng tối thiểu. Vét cạn có thể tốn thời gian rất lớn khi mục tiêu T tăng, nên chỉ dùng làm đối chứng nhỏ hoặc thay bằng một phương pháp chính xác đã được chứng minh.

### 7.1. Ví dụ Java 17: đối chiếu cả hai dạng tối ưu

Chương trình dưới đây thực hiện bốn việc: duyệt tìm chỉ số cực đại đầu tiên và đếm phép so sánh; đối chiếu với oracle từ thư viện; kiểm tra **toàn bộ** mảng độ dài 1..5 trên miền giá trị {−1, 0, 1}; và dùng vét cạn để đối chiếu nghiệm đổi tiền cùng cận chứng nhận.

~~~java
import java.util.Arrays;

public final class BoundsAndOracleDemo {
    private BoundsAndOracleDemo() {}

    public record MaxResult(int index, int comparisons) {}

    // Contract: a is non-null and non-empty; return the first max index.
    // Count only comparisons between array elements. Do not modify a.
    public static MaxResult firstMax(int[] a) {
        if (a == null || a.length == 0) {
            throw new IllegalArgumentException("a must be non-empty");
        }

        int best = 0;
        int comparisons = 0;

        for (int i = 1; i < a.length; i++) {
            comparisons++;
            if (a[i] > a[best]) {
                best = i;
            }
        }

        return new MaxResult(best, comparisons);
    }

    // Independent result oracle; intended for test comparisons.
    private static int oracleFirstMax(int[] a) {
        int maxValue = Arrays.stream(a).max().orElseThrow();

        for (int i = 0; i < a.length; i++) {
            if (a[i] == maxValue) {
                return i;
            }
        }

        throw new AssertionError("Unreachable for a non-empty array");
    }

    // Exhaust every array of length 1..5 over {-1, 0, 1}.
    private static int verifySmallArrays() {
        int tested = 0;

        for (int n = 1; n <= 5; n++) {
            int possibilities = 1;
            for (int j = 0; j < n; j++) {
                possibilities *= 3;
            }

            for (int code = 0; code < possibilities; code++) {
                int[] a = new int[n];
                int remaining = code;

                for (int i = 0; i < n; i++) {
                    a[i] = remaining % 3 - 1;
                    remaining /= 3;
                }

                int[] before = a.clone();
                MaxResult actual = firstMax(a);

                if (actual.index() != oracleFirstMax(a)
                        || actual.comparisons() != n - 1
                        || !Arrays.equals(a, before)) {
                    throw new AssertionError(Arrays.toString(a));
                }

                tested++;
            }
        }

        return tested;
    }

    // Exhaustive exact oracle for SMALL targets and positive coins.
    // Returns Integer.MAX_VALUE if no exact combination exists.
    private static int exactMinCoins(int[] coins, int remaining) {
        if (remaining == 0) {
            return 0;
        }

        int best = Integer.MAX_VALUE;
        for (int coin : coins) {
            if (coin > 0 && coin <= remaining) {
                int sub = exactMinCoins(coins, remaining - coin);
                if (sub != Integer.MAX_VALUE) {
                    best = Math.min(best, sub + 1);
                }
            }
        }

        return best;
    }

    public static void main(String[] args) {
        int[] data = {4, 9, 2, 9, 6};
        MaxResult found = firstMax(data);
        System.out.println(
                "maximum: index=" + found.index()
                + ", value=" + data[found.index()]
                + ", comparisons=" + found.comparisons()
        );

        System.out.println("verifiedArrays=" + verifySmallArrays());

        int[] coins = {1, 4, 6};
        int target = 8;

        // ceil(target / 6), calculated without floating-point rounding.
        int lowerBound = target / 6 + (target % 6 == 0 ? 0 : 1);
        int[] witness = {4, 4};
        int witnessSum = 0;
        for (int coin : witness) {
            if (Arrays.stream(coins).noneMatch(v -> v == coin)) {
                throw new AssertionError("Invalid denomination");
            }
            witnessSum += coin;
        }
        if (witnessSum != target) {
            throw new AssertionError("Infeasible witness");
        }

        int oracle = exactMinCoins(coins, target);

        int left = target;
        int greedyCount = 0;
        for (int coin : new int[]{6, 4, 1}) {
            greedyCount += left / coin;
            left %= coin;
        }
        if (left != 0) {
            throw new AssertionError("Greedy did not reach target");
        }

        System.out.println(
                "coins: lowerBound=" + lowerBound
                + ", feasible=" + witness.length
                + ", oracle=" + oracle
                + ", greedy=" + greedyCount
        );
    }
}
~~~

Lưu dưới tên **BoundsAndOracleDemo.java**, sau đó biên dịch và chạy:

~~~bash
javac BoundsAndOracleDemo.java
java BoundsAndOracleDemo
~~~

Stdout chính xác:

~~~text
maximum: index=1, value=9, comparisons=4
verifiedArrays=363
coins: lowerBound=2, feasible=2, oracle=2, greedy=3
~~~

Vì 3¹ + 3² + 3³ + 3⁴ + 3⁵ = 363, chương trình đã kiểm tra đủ 363 mảng trong miền đã chọn. Mỗi trường hợp xác minh chỉ số, số phép so sánh và việc không sửa mảng. Kết quả ấy **không chứng minh** phương thức đúng trên mọi mảng int dài tùy ý; chứng minh tổng quát đến từ bất biến và lập luận cận ở mục 4.

Oracle đổi tiền vét cạn các khả năng chọn đồng xu đầu tiên, sau đó xét phần còn lại. Vì mọi mệnh giá dương nên mỗi lời gọi giảm remaining; quy nạp theo remaining cho thấy cách duyệt này tìm được số đồng xu ít nhất nếu có lời giải. Với remaining nhỏ như 8, dùng oracle này hợp lý; không dùng không kiểm soát cho mục tiêu lớn vì số nhánh đệ quy có thể tăng theo cấp số mũ.

Trong ví dụ này, **chứng nhận hai cận L = U = 2 mới là lý do toán học xác nhận nghiệm tối ưu**. Giá trị oracle = 2 đóng vai trò đối chiếu bổ sung và phát hiện sai sót trong chương trình.

## 8. Các cách dựng cận cho bài toán tối ưu tổ hợp

Không phải bài toán nào cũng có cận đơn giản như số đồng xu. Có thể dùng các hướng sau, luôn chỉ rõ chiều cận:

| Kỹ thuật | Cách sử dụng | Điểm cần chứng minh |
| --- | --- | --- |
| Thư giãn ràng buộc (relaxation) | Cho phép nhiều nghiệm hơn; với bài **cực tiểu**, giá trị tối ưu thư giãn là **cận dưới**; với bài **cực đại**, là **cận trên** | Mọi nghiệm gốc vẫn khả thi trong bài thư giãn; hàm mục tiêu giữ tương ứng |
| Nghiệm khả thi | Bất kỳ nghiệm hợp lệ cho **cận trên** của cực tiểu hoặc **cận dưới** của cực đại | Kiểm tra mọi ràng buộc và tính đúng giá trị mục tiêu |
| Phân nhánh và cận (branch-and-bound) | Ước lượng giá trị tốt nhất có thể đạt ở một nhánh, loại nhánh nếu không thể thắng nghiệm hiện tại | Cận phải đúng cho **toàn bộ** nghiệm trong nhánh |
| Đối ngẫu / bất đẳng thức | Suy ra giới hạn mục tiêu từ các ràng buộc; ví dụ cận đối ngẫu yếu trong quy hoạch tuyến tính | Điều kiện áp dụng và chiều bất đẳng thức |
| Lập luận trao đổi (exchange argument) | Chứng minh một lựa chọn tham lam có thể xuất hiện trong nghiệm tối ưu, rồi quy nạp cho phần còn lại | Phép trao đổi không phá tính khả thi hoặc làm xấu mục tiêu |
| Quy hoạch động | Dựa trên cấu trúc con tối ưu để tính giá trị tốt nhất qua các trạng thái | Trạng thái đủ thông tin, chuyển trạng thái đầy đủ, cơ sở và thứ tự tính đúng |

**Ví dụ thư giãn:** bài ba lô 0/1 tối đa hóa giá trị dưới giới hạn trọng lượng. Nếu tạm cho phép lấy **phân số** vật phẩm, tập nghiệm rộng hơn; giá trị tối ưu của bài thư giãn là một **cận trên** cho tối ưu 0/1. Nếu một nghiệm 0/1 khả thi có giá trị đúng bằng cận trên ấy, nó tối ưu. Nếu không khớp, kết quả thư giãn chỉ là giới hạn, chưa phải chứng minh nghiệm ứng viên tối ưu.

Khi branch-and-bound tìm ra nghiệm khả thi U cho bài cực tiểu và mọi nhánh chưa thăm đều có cận dưới L_branch ≥ U, ta có thể loại hết các nhánh đó, từ đó chứng minh U tối ưu. Nếu cận bị tính sai hoặc có nhánh khả thi chưa được xem xét, chứng nhận tối ưu không còn hợp lệ.

## 9. Đối chiếu đúng cách khi có nhiều đáp án tối ưu

Ví dụ bài đường đi ngắn nhất có hai đường khác nhau nhưng cùng tổng trọng số tối thiểu. Nếu thuật toán chính trả đường A còn oracle trả đường B, phép so sánh chuỗi đỉnh trực tiếp sẽ báo “khác” dù cả hai đều đúng.

Phải tách hai lớp:

1. **Tính khả thi:** đường bắt đầu/kết thúc đúng, từng cạnh tồn tại, không vi phạm ràng buộc; nghiệm đổi tiền cộng đúng T; lịch chọn không chồng lấn.
2. **Giá trị mục tiêu:** tổng trọng số, số đồng xu, số công việc hoặc chi phí có bằng giá trị tối ưu oracle không.

Chỉ bắt buộc so sánh **cùng biểu diễn** khi hợp đồng quy định thêm tiêu chí phá hòa, chẳng hạn “trả đường đi có thứ tự từ điển nhỏ nhất trong số các đường tối ưu”.

Một số phép biến đổi hữu ích để kiểm tra tính chất:

- Với bài tìm cực đại, hoán vị mảng không làm đổi **giá trị** cực đại, dù chỉ số có thể đổi.
- Thêm một phần tử nhỏ hơn cực đại hiện tại không làm đổi **giá trị** cực đại; vị trí cực đại đầu tiên có thể thay đổi nếu chèn trước nó.
- Với bài đổi tiền có mệnh giá dương, thay đổi **thứ tự liệt kê** các mệnh giá không được thay đổi số đồng tối ưu.
- Với bài tìm đường ngắn nhất, đổi tên các đỉnh theo song ánh bảo toàn cạnh/trọng số không được làm đổi độ dài tối ưu giữa các đỉnh tương ứng.

Các phép thử này giúp phát hiện lỗi nhưng vẫn phải đi cùng tiền điều kiện và chứng minh cần thiết.

## 10. Sai lầm phổ biến

1. **Nhầm “đầu ra đúng” với “đầu ra tối ưu”.** Một nghiệm khả thi không chắc đạt giá trị mục tiêu tốt nhất; cần cận, chứng minh trao đổi, quy hoạch động hoặc phương pháp chính xác.
2. **Nhầm thuật toán nhanh với thuật toán trả nghiệm tốt.** Tham lam có thể chạy nhanh nhưng không tối ưu về nghiệm, như đổi tiền {1, 4, 6}.
3. **Dùng cận trên của một thuật toán làm cận dưới của mọi thuật toán.** Việc A chạy O(n²) không loại trừ một thuật toán khác O(n log n).
4. **Không nêu mô hình tính toán.** Cận dưới so sánh cho sắp xếp không áp dụng nguyên xi cho counting sort hoặc các phép toán khai thác miền khóa.
5. **Gộp các thước đo không tương đương.** Ít phép so sánh không bảo đảm ít thời gian thực tế nếu tốn cấp phát, I/O hoặc truy cập bộ nhớ; tối ưu worst-case không đồng nghĩa tối ưu average-case.
6. **Đánh giá thiếu tiền xử lý.** Tìm kiếm nhanh trong cấu trúc đã xây có thể không tối ưu nếu nhiệm vụ thực tế chỉ có một truy vấn và chi phí xây dựng chưa được tính.
7. **Dùng cận không hợp lệ.** Cận phải đúng cho *mọi* nghiệm khả thi trong phạm vi xét; một ước lượng dựa trên trực giác hoặc chỉ một mẫu kiểm thử không đủ.
8. **Suy ra nghiệm không tối ưu chỉ vì cận chưa khớp.** Khi L < U, có thể nghiệm đã tối ưu nhưng cận còn lỏng.
9. **Đối chiếu nhầm các nghiệm đồng hạng.** So sánh biểu diễn thay vì khả thi và giá trị mục tiêu sẽ gây báo lỗi giả.
10. **Dùng oracle cũng chưa được kiểm chứng.** Hai phương thức cùng mắc lỗi hoặc cùng dựa trên một giả định sai có thể đồng ý trên nhiều ca; hãy xây oracle đơn giản, có lý giải độc lập và kiểm thử biên.
11. **Đánh đồng vét cạn miền nhỏ với chứng minh tổng quát.** Kiểm tra 363 ca chỉ bao phủ đúng 363 ca; bất biến, quy nạp hoặc lập luận cận mới giúp tổng quát hóa.
12. **Quên trường hợp không có nghiệm.** Khi F rỗng, “nghiệm tối ưu” có thể không tồn tại; hợp đồng phải định nghĩa rõ cách báo không khả thi thay vì tự gán một giá trị mục tiêu hữu hạn.

## 11. Quy trình thực hành và bảng kiểm

Khi cần khẳng định một thuật toán hoặc lời giải tối ưu:

1. Viết đặc tả đầu vào, đầu ra và các trường hợp lỗi; xác định biến kích thước.
2. Chốt tiêu chí tối ưu: chi phí tính toán hay giá trị nghiệm; cực tiểu hay cực đại.
3. Với **chi phí tính toán**, chứng minh thuật toán đúng và đạt cận trên; riêng biệt chứng minh cận dưới trên mọi thuật toán cùng mô hình và cùng loại trường hợp; đối chiếu bậc cận.
4. Với **giá trị nghiệm**, kiểm tra nghiệm khả thi, xác định giá trị ứng viên và cận đúng chiều trên toàn bộ miền nghiệm; nếu hai cận bằng nhau, ghi chứng nhận tối ưu.
5. Tạo oracle độc lập cho bộ dữ liệu nhỏ; kiểm tra ca biên, ca cố ý đánh lừa trực giác và các thuộc tính bất biến.
6. Nếu có sai khác, thu nhỏ phản ví dụ và kiểm tra hợp đồng, cách phá hòa, hướng cận, điều kiện đầu vào.
7. Viết kết luận đủ phạm vi: **tối ưu về đại lượng nào, trong mô hình nào, ở trường hợp nào, nhờ chứng minh nào**.

| Câu tự kiểm | Dấu hiệu đã đáp ứng |
| --- | --- |
| Đã xác định rõ đối tượng tối ưu? | Nêu được thời gian/so sánh/bộ nhớ hoặc hàm mục tiêu f |
| Cận dưới có thực sự áp dụng cho mọi phương án đang so sánh? | Có giả định, lượng hóa và lập luận độc lập |
| Cận trên có được chứng minh? | Có thuật toán đúng hoặc nghiệm khả thi đã kiểm tra |
| Hai cận có khớp? | Nếu có, kết luận tối ưu; nếu chưa, chỉ báo khoảng cách còn lại |
| Oracle có độc lập và có giới hạn sử dụng rõ? | Có vét cạn hoặc tham chiếu dễ chứng minh cho trường hợp nhỏ |
| Đối chiếu có xử lý nhiều đáp án đồng hạng? | Kiểm tra tính khả thi và giá trị mục tiêu, xét tie-breaking nếu có |
| Có phân biệt kiểm thử với chứng minh? | Nêu rõ kiểm thử bao phủ miền nào và chứng minh bao phủ miền nào |

Điểm cốt lõi của tư duy chứng minh tối ưu là **không chỉ trình bày một phương án tốt**, mà còn xác lập điều gì là giới hạn tốt nhất *có thể đạt*. Cận hợp lệ tạo nên chứng nhận toán học; lời giải tham chiếu và kiểm thử độc lập giúp tìm phản ví dụ, xác nhận cài đặt tuân thủ đặc tả và phát hiện chỗ chứng minh còn thiếu.