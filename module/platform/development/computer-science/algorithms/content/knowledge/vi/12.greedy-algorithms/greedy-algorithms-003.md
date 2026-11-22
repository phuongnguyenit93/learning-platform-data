# Chứng minh bằng phép trao đổi (Exchange Argument) trong thuật toán tham lam

## 1. Mục tiêu: vì sao một lựa chọn cục bộ có thể tối ưu toàn cục?

**Thuật toán tham lam (greedy algorithm)** xây dựng lời giải theo từng bước bằng cách chọn phương án được coi là tốt nhất ngay tại thời điểm đó. Ví dụ: chọn hoạt động kết thúc sớm nhất, lấy vật có giá trị trên một đơn vị khối lượng cao nhất, hoặc chọn cạnh nhẹ nhất thỏa ràng buộc trong một thuật toán cây khung.

Nhưng “có vẻ hợp lý” chưa đủ để khẳng định **tối ưu**. Phương án tốt nhất ở bước hiện tại có thể làm mất những khả năng tốt hơn về sau. Muốn chứng minh một chiến lược greedy đúng, ta cần giải thích vì sao lựa chọn đó **không làm giảm chất lượng lời giải tối ưu**.

**Chứng minh bằng phép trao đổi (exchange argument)** là một kỹ thuật quan trọng: bắt đầu từ một lời giải tối ưu bất kỳ, rồi chứng tỏ ta có thể **thay đổi** lời giải ấy để nó chứa lựa chọn tham lam, mà vẫn **hợp lệ** và **không kém tối ưu**. Lặp luận điểm này cho những bước tiếp theo, ta chứng minh thuật toán tham lam tạo được một lời giải tối ưu.

Ý tưởng không phải chỉ nói “lấy phần tử tốt hơn để thay phần tử kém hơn”. Một phép trao đổi chỉ hợp lệ khi chứng minh đồng thời:

1. **Khả thi:** lời giải sau thay đổi vẫn thỏa tất cả ràng buộc.
2. **Chất lượng:** giá trị mục tiêu không xấu đi — không giảm nếu đang tối đa hóa, không tăng nếu đang tối thiểu hóa.
3. **Tiến triển:** lời giải mới **đồng ý với ít nhất một lựa chọn tham lam nữa** mà không phá những lựa chọn đã khớp trước đó.

Nếu thiếu một trong ba phần, đây chưa phải chứng minh đầy đủ.

## 2. Mẫu chứng minh trao đổi tổng quát

Giả sử đang xét bài toán tối ưu hóa với tập lời giải khả thi F và hàm mục tiêu \(V(S)\). Thuật toán greedy đưa ra dãy lựa chọn \(g_1,g_2,\ldots\). Với bài toán **tối đa hóa**, một mẫu chứng minh thường như sau:

**Bước A — Cố định trạng thái trước bước i.** Giả sử các lựa chọn \(g_1,\ldots,g_{i-1}\) đã được giữ nguyên, và vẫn tồn tại một lời giải tối ưu mở rộng được tiền tố đó.

**Bước B — So với một lời giải tối ưu.** Chọn một lời giải tối ưu O nhất quán với tiền tố đã cố định. Nếu O đã chọn \(g_i\) thì không cần thay đổi.

**Bước C — Tạo phép trao đổi.** Nếu O chọn \(o_i\) khác \(g_i\), xây dựng một lời giải mới O' bằng cách thay \(o_i\) bằng \(g_i\), hoặc thay một nhóm phần tử phù hợp.

**Bước D — Chứng minh hai bất biến.** Chứng minh O' vẫn khả thi, và \(V(O')\ge V(O)\). Vì O đã tối ưu, O' cũng tối ưu; đồng thời O' có chung thêm một lựa chọn với greedy.

**Bước E — Lặp lại.** Áp dụng lập luận cho phần còn lại sau lựa chọn mới. Khi tất cả lựa chọn tham lam đã được khớp, thuật toán greedy là tối ưu.

Đối với bài toán **tối thiểu hóa**, điều kiện mục tiêu đảo thành \(V(O')\le V(O)\). Với các bài toán có trọng số, phép đổi có thể là **trao đổi một lượng liên tục** thay vì đổi nguyên một phần tử.

**Phân biệt ba thuật ngữ:**
- **Greedy-choice property:** luôn tồn tại một lời giải tối ưu chứa lựa chọn tham lam hiện tại.
- **Optimal substructure:** sau khi cố định lựa chọn đầu, phần còn lại cũng là một bài toán con mà lời giải tối ưu của nó giúp tạo lời giải tối ưu toàn cục.
- **Exchange argument:** một cách chứng minh greedy-choice property bằng cách **biến đổi lời giải tối ưu**.

Chúng liên quan nhưng không đồng nghĩa. Một bài toán có cấu trúc con tối ưu chưa chắc có quy tắc tham lam đúng; quy hoạch động cũng khai thác cấu trúc con tối ưu nhưng thường so nhiều phương án thay vì cố định ngay một lựa chọn.

## 3. Ví dụ kinh điển: chọn nhiều hoạt động không chồng lấn nhất

### 3.1. Phát biểu bài toán

Có n hoạt động, mỗi hoạt động i chiếm khoảng thời gian **nửa mở** \([s_i,f_i)\), với \(s_i<f_i\). Hai hoạt động tương thích nếu chúng không chồng lấn; đặc biệt, một hoạt động kết thúc tại t và hoạt động kế tiếp bắt đầu đúng tại t **được phép** chọn cùng nhau.

**Mục tiêu:** chọn được **số lượng hoạt động lớn nhất**, không quan tâm độ dài hay trọng số riêng của từng hoạt động.

Ta có các hoạt động sau:

| Mã | Bắt đầu | Kết thúc | Khoảng |
|---|---:|---:|---|
| A | 1 | 4 | [1,4) |
| B | 3 | 5 | [3,5) |
| C | 0 | 6 | [0,6) |
| D | 5 | 7 | [5,7) |
| E | 3 | 9 | [3,9) |
| F | 5 | 9 | [5,9) |
| G | 6 | 10 | [6,10) |
| H | 8 | 11 | [8,11) |
| I | 8 | 12 | [8,12) |
| J | 2 | 14 | [2,14) |
| K | 12 | 16 | [12,16) |

Một lời giải hợp lệ là [A,D,H,K], có **4 hoạt động**. Hãy chứng minh nó có số lượng tối đa, thay vì chỉ nhìn bằng trực giác.

### 3.2. Quy tắc tham lam: kết thúc sớm nhất

**Chọn hoạt động có thời gian kết thúc sớm nhất trong số những hoạt động còn tương thích với tiền tố đã chọn.** Sau đó bỏ qua hoạt động xung đột và lặp lại.

Quy trình:
1. Sắp xếp hoạt động theo thời điểm kết thúc tăng dần.
2. Ghi nhận thời điểm kết thúc của hoạt động được chọn gần nhất.
3. Duyệt các hoạt động theo thứ tự đó; nếu hoạt động hiện tại có \(start\ge lastFinish\), chọn nó và cập nhật lastFinish.
4. Trả danh sách đã chọn.

**Lý do trực quan:** kết thúc sớm để dành nhiều thời gian nhất cho những hoạt động tương lai. Nhưng ta phải dùng phép trao đổi mới chứng minh được từ trực giác này tới tối ưu.

Các bước trên bộ dữ liệu:

~~~text
Ban đầu: chưa chọn hoạt động nào.
Xét A=[1,4): chọn A; lastFinish=4.
Xét B=[3,5), C=[0,6): bỏ vì start<4.
Xét D=[5,7): chọn D; lastFinish=7.
Xét E=[3,9), F=[5,9), G=[6,10): bỏ vì start<7.
Xét H=[8,11): chọn H; lastFinish=11.
Xét I=[8,12), J=[2,14): bỏ vì start<11.
Xét K=[12,16): chọn K.
Kết quả: [A, D, H, K] — 4 hoạt động.
~~~

Thứ tự xử lý các hoạt động cùng thời điểm kết thúc có thể được cố định bằng khóa phụ để dễ kiểm thử; điều đó **không cần thiết** cho chứng minh số lượng tối ưu.

## 4. Chứng minh tối ưu của quy tắc kết thúc sớm nhất

### 4.1. Bổ đề trao đổi cho lựa chọn đầu tiên

Gọi g là hoạt động có thời điểm kết thúc sớm nhất trong tất cả hoạt động khả thi. Xét một lời giải tối ưu bất kỳ:

\[
O=(o_1,o_2,\ldots,o_m),
\]

các hoạt động trong O được xếp theo thứ tự thời gian và không chồng lấn. Vì g kết thúc sớm nhất:

\[
f_g\le f_{o_1}.
\]

Nếu \(g=o_1\), lời giải tối ưu đã chứa lựa chọn greedy. Nếu không, thay \(o_1\) bằng g để được:

\[
O'=(g,o_2,\ldots,o_m).
\]

**Chứng minh khả thi:** với mọi hoạt động tiếp sau \(o_1\), ta có \(s_{o_j}\ge f_{o_1}\). Mặt khác \(f_g\le f_{o_1}\), nên:

\[
s_{o_j}\ge f_{o_1}\ge f_g.
\]

Do đó g không xung đột với bất kỳ hoạt động nào phía sau. Không có xung đột với phần trước vì đây là lựa chọn đầu. Tập O' vẫn khả thi.

**Chứng minh không kém tối ưu:** O' có đúng **m** hoạt động như O. Vì O đã có số lượng tối đa, O' cũng tối ưu. Và O' chứa g ở vị trí đầu.

Kết luận bổ đề: **luôn tồn tại một lời giải tối ưu bắt đầu bằng hoạt động kết thúc sớm nhất**.

Không cần g là hoạt động duy nhất có kết thúc sớm nhất. Nếu nhiều hoạt động có cùng thời điểm kết thúc, thay một hoạt động đầu bằng bất kỳ g nào trong nhóm ấy vẫn giữ tính khả thi.

### 4.2. Mở rộng cho mọi bước bằng quy nạp

Giả sử greedy đã chọn tiền tố tương thích \(G=(g_1,\ldots,g_{i-1})\), kết thúc tại thời điểm t, và vẫn tồn tại một lời giải tối ưu chứa tiền tố ấy. Phần còn lại của bài toán gồm các hoạt động có \(s\ge t\).

Greedy chọn g có thời điểm kết thúc nhỏ nhất trong phần còn lại. Xét phần đuôi của một lời giải tối ưu đang khớp với G; nếu phần đuôi có hoạt động đầu o, ta biết \(f_g\le f_o\). Thay o bằng g:

- g bắt đầu sau hoặc đúng t, nên tương thích với **tiền tố**.
- Mọi hoạt động sau o bắt đầu không sớm hơn \(f_o\), mà \(f_g\le f_o\), nên tương thích với **g**.
- Số hoạt động không thay đổi, nên lời giải mới vẫn tối ưu.

Lặp quy nạp cho tới khi không còn hoạt động nào tương thích. Nếu phần đuôi của một lời giải được cho là tối ưu lại rỗng trong khi vẫn còn một hoạt động g khả thi, ta có thể thêm g và làm tăng số lượng — mâu thuẫn với tối ưu. Vì vậy phép quy nạp không mắc trường hợp bỏ sót hoạt động.

Kết luận:

\[
\boxed{\text{Chọn lần lượt hoạt động kết thúc sớm nhất tạo số lượng tối đa.}}
\]

**Điểm mấu chốt của phép trao đổi:** không phải vì g ngắn nhất hay bắt đầu sớm nhất, mà vì **thay hoạt động đầu tiên bằng g không khiến bất kỳ hoạt động tương lai nào mất tính khả thi**.

### 4.3. Vì sao không chọn hoạt động bắt đầu sớm nhất?

Xét ba khoảng:

~~~text
Long   [0,10)
Short1 [1,2)
Short2 [2,3)
~~~

Quy tắc “bắt đầu sớm nhất” chọn Long và chỉ lấy được **1 hoạt động**. Quy tắc “kết thúc sớm nhất” chọn Short1 rồi Short2, được **2 hoạt động**. Nếu cố trao đổi Long bằng Short1 trong lời giải [Long], ta cải thiện số lượng sau khi thêm Short2; điều này cho thấy một lựa chọn bắt đầu sớm không có bổ đề giữ được tối ưu như lựa chọn kết thúc sớm.

Quy tắc “thời lượng ngắn nhất” cũng không luôn đúng. Ví dụ [0,3), [3,6), [2,4): chọn [2,4) vì độ dài 2 làm mất cả hai khoảng độ dài 3; kết quả 1, trong khi có thể chọn [0,3) và [3,6) được 2.

**Không dùng các phản ví dụ chỉ để kiểm thử mã:** chúng chỉ ra chính xác vị trí một chứng minh trao đổi của quy tắc sai sẽ không thể bảo đảm rằng lựa chọn tham lam không phá phần còn lại.

## 5. Ví dụ trao đổi thứ hai: fractional knapsack

### 5.1. Bài toán

Cho các món hàng i có **khối lượng** \(w_i>0\), **giá trị** \(v_i\ge0\), và ba lô dung lượng W. Có thể lấy **một phần** của mỗi món: chọn \(x_i\in[0,w_i]\) đơn vị khối lượng từ món i. Mục tiêu:

\[
\max \sum_i x_i\frac{v_i}{w_i}
\quad\text{với}\quad \sum_i x_i\le W.
\]

Đặt \(\rho_i=v_i/w_i\) là **mật độ giá trị**. Thuật toán tham lam sắp \(\rho_i\) giảm dần, lấy nhiều nhất có thể từ món đang xét rồi mới sang món có mật độ thấp hơn.

### 5.2. Phép trao đổi khối lượng

Giả sử một lời giải khả thi đang lấy \(\delta>0\) khối lượng từ món j có \(\rho_j<\rho_i\), trong khi món i có mật độ cao hơn vẫn chưa được lấy hết. Có thể chọn một \(\delta\) đủ nhỏ để vừa giảm lượng lấy từ j vừa tăng lượng lấy từ i, giữ nguyên tổng khối lượng:

\[
x_i'=x_i+\delta,\qquad
x_j'=x_j-\delta.
\]

Thay đổi mục tiêu:

\[
V'-V=\delta\rho_i-\delta\rho_j
=\delta(\rho_i-\rho_j)>0.
\]

Nếu lời giải ban đầu được tuyên bố tối ưu, điều này là mâu thuẫn. Với \(\rho_i=\rho_j\), phép đổi giữ nguyên mục tiêu, nên có thể chọn thứ tự bất kỳ trong nhóm cùng mật độ.

Bằng cách lặp trao đổi cho đến khi không còn món mật độ cao nào chưa lấy hết trong khi món mật độ thấp đang được lấy, ta thu được lời giải lấy hàng theo **mật độ giảm dần**, đúng với tham lam.

Đây là ví dụ **trao đổi một lượng liên tục**, khác với đổi nguyên một hoạt động trong bài toán lịch.

### 5.3. Vì sao không dùng ngay cho 0/1 knapsack?

Trong **0/1 knapsack**, mỗi món chỉ được lấy nguyên hoặc bỏ; việc chuyển \(\delta\) khối lượng từ món j sang món i có thể không tạo được phương án hợp lệ.

Ví dụ dung lượng W=50:
- A: khối lượng 10, giá trị 60, mật độ 6.
- B: khối lượng 20, giá trị 100, mật độ 5.
- C: khối lượng 30, giá trị 120, mật độ 4.

Greedy theo mật độ lấy A rồi B, tổng giá trị **160**, còn dung lượng 20 không đủ lấy C. Nhưng chọn B+C có tổng khối lượng 50 và giá trị **220**. Chính điều kiện **được lấy một phần** đã cho phép phép trao đổi của fractional knapsack; khi điều kiện này biến mất, chứng minh không còn hợp lệ.

**Bài học chung:** khi một phép đổi được đề xuất, phải kiểm tra lại **miền lời giải khả thi của đúng bài toán**; kết luận của một biến thể không tự chuyển sang biến thể khác.

## 6. Mẫu phản biện: nhận diện “chứng minh trao đổi” chưa đủ

Một số lập luận thường nghe có vẻ hợp lý nhưng thiếu cơ sở:

| Phát biểu | Điểm thiếu | Cần bổ sung |
|---|---|---|
| “Chọn phần tử tốt nhất trước nên kết quả tối ưu” | Chưa xét ảnh hưởng tới phần còn lại | Xây dựng lời giải tối ưu sau trao đổi mà vẫn khả thi |
| “Có thể thay o bằng g” | Chưa chứng minh không phá ràng buộc | Bất đẳng thức hoặc cấu trúc cụ thể đảm bảo khả thi |
| “g tốt hơn o” | “Tốt hơn” ở một tiêu chí không nhất thiết tốt hơn mục tiêu | Chứng minh tổng giá trị sau đổi không xấu |
| “Đổi lần đầu được thì mọi lần đều được” | Chưa bảo toàn tiền tố đã chốt | Dùng quy nạp hoặc bất biến của trạng thái còn lại |
| “Đổi được trong bài tương tự” | Ràng buộc có thể khác | Kiểm tra lại điều kiện riêng như có được chia nhỏ món hàng hay không |
| “Chương trình chạy đúng vài test” | Thử nghiệm hữu hạn không chứng minh mọi đầu vào | Chứng minh tổng quát, sau đó dùng test để hỗ trợ triển khai |

Ngoài exchange argument, có hai kỹ thuật họ hàng:
- **Stays-ahead:** chứng minh sau mỗi bước greedy không thua một lời giải khác theo một đại lượng tiên đoán tương lai, chẳng hạn thời điểm kết thúc thứ i.
- **Cut-and-paste / cấu trúc con tối ưu:** chứng minh thay phần lời giải sau một tiền tố bằng một lời giải tốt hơn sẽ cải thiện toàn cục, từ đó suy ra phần đuôi phải tối ưu.

Có bài toán áp dụng được nhiều kỹ thuật; không bắt buộc mọi bài tham lam phải dùng phép trao đổi. Nhưng khi dùng phép trao đổi, phần **khả thi và giá trị mục tiêu** không được bỏ qua.

## 7. Java 17+ hoàn chỉnh: greedy và kiểm chứng bằng brute force

Ví dụ Java sau thực hiện hai việc:
1. Tính lịch có số lượng hoạt động tối đa bằng **greedy kết thúc sớm nhất**.
2. Với một bộ dữ liệu nhỏ, dùng **liệt kê mọi tập con** để xác nhận số lượng tối ưu. Đây là công cụ kiểm thử độc lập, **không phải** là một phần cần thiết của thuật toán greedy và không thay thế chứng minh.

Mỗi hoạt động có tên, thời điểm bắt đầu và kết thúc. Chương trình dùng các khoảng \([start,end)\), yêu cầu **start < end**, và cho phép hoạt động kế tiếp bắt đầu đúng lúc hoạt động trước kết thúc.

Lưu tệp **ExchangeArgumentGreedyDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public final class ExchangeArgumentGreedyDemo {
    private ExchangeArgumentGreedyDemo() {
    }

    record Interval(String name, int start, int end) {
        Interval {
            if (name == null || name.isBlank() || start >= end) {
                throw new IllegalArgumentException("Invalid interval");
            }
        }
    }

    private static final Comparator<Interval> BY_FINISH =
            Comparator.comparingInt(Interval::end)
                    .thenComparingInt(Interval::start)
                    .thenComparing(Interval::name);

    public static List<Interval> earliestFinish(List<Interval> input) {
        if (input == null || input.contains(null)) {
            throw new IllegalArgumentException("Invalid list");
        }

        List<Interval> sorted = new ArrayList<>(input);
        sorted.sort(BY_FINISH);

        List<Interval> answer = new ArrayList<>();
        long lastFinish = Long.MIN_VALUE;

        for (Interval current : sorted) {
            if (current.start() >= lastFinish) {
                answer.add(current);
                lastFinish = current.end();
            }
        }
        return answer;
    }

    // Một chiến lược sai, chỉ dùng để minh họa phản ví dụ.
    private static List<Interval> earliestStart(List<Interval> input) {
        List<Interval> sorted = new ArrayList<>(input);
        sorted.sort(Comparator.comparingInt(Interval::start)
                .thenComparingInt(Interval::end)
                .thenComparing(Interval::name));

        List<Interval> answer = new ArrayList<>();
        long lastFinish = Long.MIN_VALUE;
        for (Interval current : sorted) {
            if (current.start() >= lastFinish) {
                answer.add(current);
                lastFinish = current.end();
            }
        }
        return answer;
    }

    private static List<String> names(List<Interval> selected) {
        List<String> result = new ArrayList<>();
        for (Interval item : selected) {
            result.add(item.name());
        }
        return result;
    }

    // Chỉ dùng cho n nhỏ: thử tất cả 2^n tập con.
    private static int bruteForceOptimum(List<Interval> input) {
        int n = input.size();
        if (n > 20) {
            throw new IllegalArgumentException("Too many intervals");
        }

        int best = 0;
        for (int mask = 0; mask < (1 << n); mask++) {
            int count = Integer.bitCount(mask);
            if (count <= best) {
                continue;
            }

            boolean feasible = true;
            for (int i = 0; i < n && feasible; i++) {
                if ((mask & (1 << i)) == 0) {
                    continue;
                }
                for (int j = i + 1; j < n; j++) {
                    if ((mask & (1 << j)) == 0) {
                        continue;
                    }

                    Interval a = input.get(i);
                    Interval b = input.get(j);
                    boolean overlaps =
                            a.start() < b.end() && b.start() < a.end();
                    if (overlaps) {
                        feasible = false;
                        break;
                    }
                }
            }

            if (feasible) {
                best = count;
            }
        }
        return best;
    }

    public static void main(String[] args) {
        List<Interval> activities = List.of(
                new Interval("A", 1, 4),
                new Interval("B", 3, 5),
                new Interval("C", 0, 6),
                new Interval("D", 5, 7),
                new Interval("E", 3, 9),
                new Interval("F", 5, 9),
                new Interval("G", 6, 10),
                new Interval("H", 8, 11),
                new Interval("I", 8, 12),
                new Interval("J", 2, 14),
                new Interval("K", 12, 16)
        );

        List<Interval> greedy = earliestFinish(activities);
        System.out.println("Greedy: " + names(greedy));
        System.out.println("Selected: " + greedy.size());
        System.out.println("Brute-force optimum: "
                + bruteForceOptimum(activities));

        List<Interval> counterexample = List.of(
                new Interval("Long", 0, 10),
                new Interval("Short1", 1, 2),
                new Interval("Short2", 2, 3)
        );
        System.out.println("Earliest start: "
                + names(earliestStart(counterexample)));
        System.out.println("Earliest finish: "
                + names(earliestFinish(counterexample)));

        List<Interval> touching = List.of(
                new Interval("X", 0, 2),
                new Interval("Y", 2, 4)
        );
        System.out.println("Touching: " + names(earliestFinish(touching)));
        System.out.println("Empty: " + names(earliestFinish(List.of())));
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac ExchangeArgumentGreedyDemo.java
java ExchangeArgumentGreedyDemo
~~~

Stdout dự kiến chính xác:

~~~text
Greedy: [A, D, H, K]
Selected: 4
Brute-force optimum: 4
Earliest start: [Long]
Earliest finish: [Short1, Short2]
Touching: [X, Y]
Empty: []
~~~

### Giải thích chương trình

- **BY_FINISH** sắp theo end tăng dần. Các khóa phụ start, name chỉ làm thứ tự của những hoạt động cùng thời gian kết thúc mang tính xác định; không ảnh hưởng chứng minh tối ưu số lượng.
- **lastFinish** dùng long với giá trị ban đầu Long.MIN_VALUE để mọi thời điểm bắt đầu kiểu int đều được xem xét, kể cả số âm. Sau mỗi hoạt động được nhận, nó đổi thành end của hoạt động ấy.
- **earliestFinish** sao chép danh sách trước khi sắp, không sửa thứ tự danh sách nguồn. Điều kiện start ≥ lastFinish cho phép hai khoảng chạm đầu–cuối mà không chồng lấn.
- **bruteForceOptimum** xét mọi mask của tập con, chỉ nhận một tập nếu **mọi cặp khoảng** trong tập không giao nhau. Điều kiện hai khoảng nửa mở A và B giao nhau là \(A.start<B.end\) và \(B.start<A.end\). Vòng thử chỉ dùng cho n≤20 vì tốn công việc theo cấp số mũ, không phải phương án sản xuất.
- Mẫu phản ví dụ phân biệt đúng quy tắc earliest start sai với earliest finish đúng; mẫu touching xác nhận điều kiện tương thích ở thời điểm biên.

**Độ phức tạp của thuật toán tham lam:** sắp xếp n hoạt động theo end bằng sort có thời gian O(n log n) trong mô hình so sánh; duyệt và chọn O(n), nên toàn bộ **O(n log n)**. Bộ nhớ chứa bản sao danh sách, danh sách kết quả và bộ nhớ nội bộ sort là O(n) theo bậc lớn. Nếu hoạt động đã được sắp theo end, riêng bước chọn chỉ cần **O(n) thời gian** và O(1) trạng thái ngoài kết quả; có thể xuất kết quả trực tiếp nếu không muốn giữ một List.

**Brute force chỉ để thử nghiệm:** mã liệt kê tối đa \(2^n\) tập con và so cặp phần tử trong mỗi tập, có chặn trên O(\(2^n n^2\)) thời gian, nên tuyệt đối không dùng nó thay greedy khi n lớn. Việc test trả cùng giá trị 4 không tự chứng minh greedy đúng cho mọi đầu vào; chứng minh trao đổi ở mục 4 làm nhiệm vụ đó.

## 8. Trường hợp mà phép trao đổi thất bại

### 8.1. Bài toán chọn khoảng có trọng số

Nếu mỗi hoạt động có trọng số (giá trị) khác nhau và mục tiêu là **tối đa tổng trọng số**, quy tắc kết thúc sớm nhất không còn bảo đảm tối ưu.

Ví dụ:
- A: [0,2), trọng số 1.
- B: [0,3), trọng số 100.

Greedy kết thúc sớm nhất chọn A và được 1, còn chọn B cho 100. Phép trao đổi “thay hoạt động đầu bằng A” giữ **số hoạt động**, nhưng **không giữ tổng trọng số**. Chính bước so sánh mục tiêu đã thất bại. Với weighted interval scheduling tổng quát, thường cần quy hoạch động hoặc phương pháp khác.

### 8.2. Trao đổi phá tính khả thi

Với bài toán chỉ được lấy nguyên món hàng, phép đổi một phần khối lượng không tồn tại trong miền phương án hợp lệ. Với bài toán có thứ tự phụ thuộc, đổi vị trí hai công việc có thể vi phạm quan hệ trước–sau. Với đường đi trên đồ thị, thay một cạnh có trọng số nhỏ hơn có thể làm đường đi không còn nối đúng các đỉnh cần thiết.

Không được tuyên bố “ta luôn đổi được” chỉ bằng việc so trọng số hoặc thời điểm. Phải chứng minh **cấu trúc ràng buộc** vẫn giữ sau đổi.

### 8.3. Mục tiêu và trạng thái không trùng nhau

Trong interval scheduling tối đa số lượng, đổi o thành g bảo toàn số lượng và không làm kết thúc muộn hơn, nên phần đuôi vẫn khả thi. Nếu mục tiêu là **tối thiểu tổng thời gian chờ**, **tối thiểu trễ hạn tối đa** hoặc **tối đa lợi nhuận**, cần lập phép trao đổi và bất đẳng thức theo chính mục tiêu ấy. Một lập luận đúng cho chỉ tiêu A chưa chắc đúng cho chỉ tiêu B.

## 9. Cách viết chứng minh trao đổi trong bài thi/phỏng vấn

Một bài giải tốt nên viết thành những câu kiểm chứng được:

1. **Định nghĩa lời giải khả thi và mục tiêu.** Ví dụ, các khoảng [start,end) không giao nhau và tối đa hóa số lượng.
2. **Định nghĩa lựa chọn greedy chính xác.** “Hoạt động khả thi kết thúc sớm nhất” khác “hoạt động ngắn nhất”.
3. **Chọn lời giải tối ưu O để so sánh.** Nói rõ phần tử nào của O được thay và nó đang ở vị trí nào.
4. **Nêu quan hệ giúp trao đổi.** Trong interval scheduling: \(f_g\le f_{o_1}\).
5. **Kiểm tra khả thi sau đổi.** Mọi hoạt động sau o1 vẫn có start ≥ f_g; các phần trước không xung đột.
6. **Kiểm tra giá trị mục tiêu.** Thay một hoạt động bằng một hoạt động nên không giảm số lượng.
7. **Lặp lại có căn cứ.** Sử dụng quy nạp trên số lựa chọn đã khớp hoặc chứng minh quy tắc cũng đúng trên bài toán còn lại.
8. **Kết luận độ phức tạp riêng.** Chứng minh đúng đắn không đồng nghĩa phân tích thời gian/bộ nhớ.

Một cách thử sức cho chứng minh: **đổi mục tiêu hoặc thêm ràng buộc** rồi hỏi mệnh đề nào hỏng đầu tiên. Với weighted interval scheduling, chính điều “không kém mục tiêu” hỏng; với 0/1 knapsack, phép đổi một phần không còn khả thi.

### Những lỗi ngôn ngữ nên tránh

- “Greedy đúng vì luôn chọn tốt nhất”: thiếu lý do toàn cục.
- “Không mất tính tổng quát, nghiệm tối ưu chọn g”: đây chính là điều cần chứng minh.
- “O' tối ưu vì g tốt hơn o”: cần xác minh **O' khả thi** và **giá trị mục tiêu không xấu**.
- “Thay phần tử đầu xong là đủ”: phải chứng minh cho **mọi bước tiếp theo** hoặc bài toán con.
- “Các phần tử sau không bị ảnh hưởng”: cần một bất đẳng thức hoặc cấu trúc cụ thể để hỗ trợ, ví dụ \(f_g\le f_o\).
- “Chọn kết thúc sớm nhất là tốt nhất trong mọi lịch”: sai nếu các hoạt động có lợi nhuận khác nhau hoặc có ràng buộc bổ sung.

## 10. Kiểm thử tính đúng của cài đặt

Ngoài chứng minh toán học, chương trình cần được kiểm thử để tránh lỗi cài đặt:

| Trường hợp | Điều kiện cần xác minh |
|---|---|
| Không có hoạt động | Trả danh sách rỗng |
| Chỉ một hoạt động hợp lệ | Chọn đúng hoạt động đó |
| Hai hoạt động có end=start ở biên | Có thể chọn cả hai theo khoảng nửa mở |
| Mọi hoạt động chồng nhau | Chọn tối đa một |
| Nhiều hoạt động không chồng nhau | Có thể chọn tất cả |
| Nhiều hoạt động cùng thời điểm kết thúc | Chọn theo quy tắc tie ổn định hoặc xác định, vẫn tối ưu số lượng |
| Thời điểm âm hoặc giới hạn int | So sánh đúng, không tràn do phép trừ |
| Dữ liệu đầu vào chưa sắp | Kết quả giống dữ liệu đã sắp theo end |
| start ≥ end | Từ chối theo hợp đồng của ví dụ |
| Nhiều dữ liệu ngẫu nhiên nhỏ | Số lượng greedy bằng brute-force optimum |

Với n nhỏ, có thể sinh tất cả bộ khoảng có start<end trong một miền thời gian hạn chế, chạy greedy và liệt kê tập con như chương trình trên để so kết quả. Điều này là **kiểm thử thuộc tính (property-based testing)** hữu ích nhưng vẫn không thay thế chứng minh cho toàn bộ miền đầu vào.

Khi tie có nhiều khoảng cùng thời điểm kết thúc, các lời giải tối ưu khác nhau có thể chọn các tập khác nhau. Kiểm thử nên đối chiếu **mục tiêu và tính hợp lệ** trước, không bắt mọi bộ dữ liệu có cùng một thứ tự tên nếu bài toán không quy định tie-break.

## 11. Bài tập tự kiểm tra

**Câu 1.** Trong bài chọn tối đa số hoạt động, tại sao có thể thay hoạt động đầu của một lịch tối ưu bằng hoạt động kết thúc sớm nhất?

**Đáp án:** Vì hoạt động greedy có end không muộn hơn end của hoạt động đầu tối ưu. Mọi hoạt động sau trong lịch tối ưu bắt đầu sau end của hoạt động đầu, nên cũng bắt đầu sau end của greedy. Lời giải thay thế vẫn tương thích và có cùng số hoạt động.

**Câu 2.** Tại sao phép trao đổi của fractional knapsack không chứng minh được tham lam cho 0/1 knapsack?

**Đáp án:** Vì 0/1 knapsack không cho lấy lượng \(\delta\) bất kỳ từ món hàng. Phép chuyển khối lượng có thể tạo phương án không hợp lệ; do đó không được dùng bất đẳng thức cải thiện giá trị cho một phép đổi không khả thi.

**Câu 3.** Cho A=[0,2) trọng số 1 và B=[0,3) trọng số 100. Tại sao quy tắc kết thúc sớm nhất thất bại nếu mục tiêu là tối đa tổng trọng số?

**Đáp án:** Nó chọn A được 1, trong khi chọn B được 100. Trao đổi hai hoạt động bảo toàn **số lượng** nhưng giảm **tổng trọng số**, nên bước bảo toàn mục tiêu trong chứng minh ban đầu không còn đúng.

**Câu 4.** Nếu hai hoạt động cùng thời điểm kết thúc nhưng bắt đầu khác nhau, chọn hoạt động nào trước có ảnh hưởng tới số lượng tối ưu không?

**Đáp án:** Không, với bài toán tối đa số hoạt động không trọng số và khoảng hợp lệ, vì hoạt động nào kết thúc cùng thời điểm cũng để lại cùng ngưỡng bắt đầu cho phần còn lại. Tie-break có thể dùng để tạo đầu ra xác định.

**Câu 5.** Nếu chứng minh được lời giải sau trao đổi có cùng giá trị nhưng chưa chứng minh nó khả thi thì đã đủ chưa?

**Đáp án:** Chưa. Giá trị của một phương án không hợp lệ không cho biết gì về tối ưu trên **tập phương án hợp lệ**. Luôn chứng minh ràng buộc còn đúng sau phép đổi.

**Câu 6.** Điểm khác nhau giữa “lựa chọn greedy tồn tại trong một lời giải tối ưu” và “thuật toán greedy cho lời giải tối ưu” là gì?

**Đáp án:** Mệnh đề đầu chỉ bảo đảm **một bước có thể được cố định** trong lời giải tối ưu. Muốn chứng minh cả thuật toán, cần tiếp tục lập luận trên bài toán con sau mỗi lựa chọn, bảo toàn tiền tố đã chọn cho tới khi kết thúc.

**Ghi nhớ:** Chứng minh bằng phép trao đổi là phép biến đổi **một lời giải tối ưu** để nó tuân theo **một lựa chọn greedy**, đồng thời bảo toàn **tính khả thi** và **giá trị tối ưu**. Khi có thể lặp quy trình ấy cho mọi bước, ta mới có chứng minh tham lam đúng.
