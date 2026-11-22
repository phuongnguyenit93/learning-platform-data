# Bài toán tồn tại, đếm, cực tiểu và cực đại trong quy hoạch động

Cùng một tập dữ liệu và cùng một hệ ràng buộc có thể dẫn đến **bốn câu hỏi khác nhau**: có lời giải hay không, có bao nhiêu lời giải, lời giải tốt nhất theo hướng nhỏ nhất là gì, và lời giải tốt nhất theo hướng lớn nhất là gì. Trong **quy hoạch động (dynamic programming, DP)**, chúng có thể dùng **cùng định nghĩa trạng thái và cùng các lựa chọn chuyển trạng thái**, nhưng khác cách **khởi tạo**, **tổng hợp các phương án** và **biểu diễn trạng thái không thể đạt**.

Ví dụ với các đồng tiền mệnh giá **1, 3, 4**, được dùng **không giới hạn**, muốn tạo tổng **6**:

- **Tồn tại:** có thể tạo 6 hay không? **Có**.
- **Đếm:** có bao nhiêu cách chọn *tổ hợp đồng tiền*, không phân biệt thứ tự? **4** cách.
- **Cực tiểu:** cần ít nhất bao nhiêu đồng? **2 đồng**, cụ thể 3+3.
- **Cực đại:** có thể dùng nhiều nhất bao nhiêu đồng? **6 đồng**, cụ thể 1+1+1+1+1+1.

Bốn câu hỏi không chỉ khác ở lệnh trả kết quả: chúng quyết định **cách DP gộp các đường đi dẫn tới cùng một trạng thái**. Bài học này trình bày tư duy chung, hai mô hình điển hình (chọn 0/1 và chọn không giới hạn), sự khác biệt giữa đếm tổ hợp và đếm chuỗi có thứ tự, chương trình Java 17+ chạy được, chứng minh đúng và các lỗi dễ nhầm.

## 1. Phân biệt bốn loại mục tiêu

Gọi **S** là tập tất cả lời giải hợp lệ của bài toán, và **score(x)** là giá trị cần tối ưu nếu đề có hàm điểm/chi phí.

| Câu hỏi | Ý nghĩa | Kết quả khi không có lời giải | Phép tổng hợp điển hình |
| --- | --- | --- | --- |
| **Tồn tại (existence/feasibility)** | Có ít nhất một x thuộc S? | false | OR |
| **Đếm (counting)** | S có bao nhiêu phần tử? | 0 | Cộng số cách |
| **Cực tiểu (minimization)** | min score(x) với x thuộc S | Không xác định / +∞ làm sentinel | min |
| **Cực đại (maximization)** | max score(x) với x thuộc S | Không xác định / −∞ làm sentinel | max |

Nếu có trạng thái **đích đạt được bằng nhiều lựa chọn khác nhau**, phép gộp quyết định ta giữ lại gì:

- Với **tồn tại**, chỉ cần **một** cách hợp lệ, nên dùng OR.
- Với **đếm**, phải tính tổng số cách từ các nhánh **không đếm trùng**.
- Với **cực tiểu**, giữ giá trị nhỏ nhất trong những cách hợp lệ.
- Với **cực đại**, giữ giá trị lớn nhất trong những cách hợp lệ.

**Bài toán con (state) và phép chuyển (transition) phải được xác định độc lập trước khi chọn phép gộp.** Cùng một state có thể dùng cho nhiều mục tiêu, nhưng không phải mọi mục tiêu đều có thể giữ nguyên số chiều trạng thái. Ví dụ khi muốn tối ưu thêm số lượng loại đã dùng, hoặc ràng buộc về thứ tự, có thể phải bổ sung chiều trạng thái.

### Giá trị đúng khi không có phương án

Không nên dùng một giá trị số chung cho tất cả mục tiêu:

- **Đếm:** 0 là số cách hợp lệ để biểu diễn “không có cách”.
- **Min:** 0 thường là một kết quả **hợp lệ** (chọn không phần tử), nên không thể tùy tiện dùng 0 làm “không đạt”.
- **Max:** tương tự, 0 có thể là kết quả hợp lệ. Có thể dùng −1 nếu score là số lượng phần tử không âm, hoặc −∞ trong mô hình tổng quát.
- **Exist:** false tự nhiên biểu thị trạng thái không thể đạt.

Với min, có thể dùng **INF** và bảo đảm **không cộng chi phí vào INF trước khi kiểm tra đạt được**; nếu INF = Integer.MAX_VALUE mà cứ cộng 1, số nguyên có thể tràn thành số âm.

## 2. Bắt đầu từ mô hình trạng thái và phép chuyển

Một công thức DP thường có cấu trúc:

**dp[state] = combine(dp[predecessor] qua các lựa chọn hợp lệ)**.

Từ trạng thái trước **u**, nếu thực hiện một lựa chọn có chi phí **c**, có thể đi đến trạng thái sau **v**. Cách cập nhật cho từng mục tiêu:

~~~text
Tồn tại:  reach[v] = reach[v] OR reach[u]

Đếm:      ways[v]  = ways[v] + ways[u]

Cực tiểu: min[v]   = min(min[v], min[u] + c)

Cực đại:  max[v]   = max(max[v], max[u] + c)
~~~

Trong hai dòng tối ưu, phép cộng **c** có thể thay bằng phép nhân, cộng phần thưởng hoặc hàm cập nhật trạng thái khác, tùy định nghĩa score. Điều kiện quan trọng là **chỉ sử dụng u nếu u đạt được**; với đếm chỉ cộng những cách hợp lệ, còn với min/max phải loại bỏ trạng thái vô nghiệm.

Đừng suy ra “đếm được bao nhiêu lời giải” chỉ bằng cách đếm số đường đi trong **mọi** đồ thị trạng thái mà không xem một lời giải có thể tạo ra nhiều đường đi không. Một mô hình chuyển trạng thái có thể **đếm trùng** khi các thứ tự ra quyết định khác nhau lại biểu diễn cùng một tổ hợp.

### Cách chọn base case

Giả sử bài xây một tổng bằng cách chọn phần tử có trọng số dương, ban đầu chưa chọn gì:

- Tổng 0 **có thể đạt**: reach[0] = true.
- Có **đúng một cách chọn rỗng**: ways[0] = 1.
- Số phần tử nhỏ nhất/lớn nhất để tạo tổng 0 là **0**: min[0] = max[0] = 0.
- Các tổng dương còn lại lúc bắt đầu **chưa đạt**: reach=false, ways=0, min=INF, max=−∞.

Cơ sở **ways[0]=1** thường dễ bị nhầm thành 0. Nó không nói rằng đã chọn một đồng tiền: nó biểu diễn **một cách lựa chọn rỗng** để làm điểm xuất phát cho những cách xây tổng dương. Nếu đặt ways[0]=0, mọi phép cộng số cách phía sau có thể đều bằng 0.

## 3. Mô hình 0/1: mỗi phần tử chỉ chọn tối đa một lần

Cho n phần tử có trọng số nguyên dương **a[0],...,a[n−1]** và tổng đích **T ≥ 0**. Mỗi phần tử là **một vị trí riêng biệt**: hoặc **không chọn**, hoặc **chọn đúng một lần**.

Ví dụ **a=[2,3,3,5]**, T=5. Hai phần tử 3 nằm ở **hai chỉ số khác nhau**. Các tập chỉ số tạo tổng 5:

1. Chọn phần tử 5.
2. Chọn phần tử 2 và số 3 ở vị trí thứ nhất.
3. Chọn phần tử 2 và số 3 ở vị trí thứ hai.

Do đó:

- **Tồn tại:** true.
- **Đếm theo tập chỉ số:** 3 cách.
- **Ít phần tử nhất:** 1 (chọn 5).
- **Nhiều phần tử nhất:** 2 (chọn 2 và một trong hai số 3).

Đây là ví dụ quan trọng vì **hai giá trị bằng nhau nhưng là hai phần tử đầu vào khác nhau**. Nếu đề đếm theo **đa tập giá trị** thay vì theo chỉ số, đáp án có thể khác; phải định nghĩa “một cách” rõ ràng.

### Trạng thái hai chiều

Đặt **dp[i][s]** là kết quả dùng **i phần tử đầu tiên** để tạo tổng s, với 0 ≤ i ≤ n và 0 ≤ s ≤ T.

Phần tử mới có trọng số **w=a[i−1]**. Các cách của dp[i][s] chia thành **hai nhóm rời nhau**:

- **Bỏ qua w:** dùng kết quả từ dp[i−1][s].
- **Chọn w:** chỉ hợp lệ nếu s≥w, dùng kết quả từ dp[i−1][s−w] rồi thêm một phần tử.

Từ đó suy ra bốn công thức:

**Tồn tại:**

**E[i][s] = E[i−1][s] OR (s≥w AND E[i−1][s−w])**.

**Đếm tập chỉ số:**

**C[i][s] = C[i−1][s] + (s≥w ? C[i−1][s−w] : 0)**.

**Cực tiểu số phần tử:**

**Min[i][s] = min(Min[i−1][s], 1+Min[i−1][s−w])** nếu s≥w và trạng thái trước đạt; nếu không thì chỉ xét nhánh bỏ qua.

**Cực đại số phần tử:**

**Max[i][s] = max(Max[i−1][s], 1+Max[i−1][s−w])** với cùng điều kiện hợp lệ.

**Cực tiểu/cực đại ở đây là số phần tử được chọn**, không phải tổng trọng số: tổng đã bị cố định bằng T.

### Vì sao công thức đúng?

Mỗi tập con của i phần tử có **một trong đúng hai tình huống**: chứa phần tử thứ i hoặc không chứa nó. Hai nhóm này không giao nhau; khi bỏ phần tử thứ i ra khỏi nhóm có chứa nó, ta thu được một tập con hợp lệ từ i−1 phần tử có tổng s−w. Vì vậy:

- OR đúng vì chỉ cần ít nhất một nhóm có lời giải.
- Cộng đúng vì hai nhóm **rời nhau** và bao phủ toàn bộ lời giải.
- Min/max đúng vì ứng viên tối ưu của toàn bộ tập phải nằm trong một trong hai nhóm.

Đây là một chứng minh bằng **phân hoạch tập lời giải**. Cấu trúc phân hoạch là lý do công thức đếm không bị trùng.

## 4. Tối ưu bộ nhớ 0/1: duyệt tổng giảm dần

Bảng hai chiều có (n+1)(T+1) trạng thái, tốn **O(nT)** bộ nhớ. Nếu chỉ cần kết quả cuối cùng (không cần phục hồi cách chọn hoặc lưu bảng cho mọi tiền tố), có thể dùng **một mảng theo tổng**, tức O(T) ô cho mỗi loại đại lượng.

Với mỗi phần tử w, cập nhật:

~~~text
for each value w in a:
    for s = T downto w:
        if state[s-w] đạt được:
            đưa lựa chọn "chọn w" vào state[s]
~~~

**Phải duyệt s giảm dần** để phần tử w không được dùng quá một lần trong cùng lượt xử lý.

Vì s−w < s với w>0, khi đang xét s theo thứ tự giảm, ô state[s−w] vẫn chứa kết quả **trước khi thêm phần tử hiện tại**. Đó là kết quả đúng của nhánh “chọn w” trong mô hình 0/1.

Nếu duyệt tăng dần, state[s−w] có thể đã sử dụng w ở đầu lượt, rồi lại được sử dụng để cập nhật state[s]. Khi đó một phần tử 0/1 có thể bị dùng **nhiều lần**, biến sai bài toán thành dạng không giới hạn.

Ví dụ chỉ có **một phần tử a=[2]**, T=4:

- 0/1 đúng: không thể tạo 4 bằng một phần tử 2.
- Nếu duyệt tăng: đạt tổng 2, rồi từ tổng 2 lại cập nhật tổng 4 bằng chính phần tử 2, cho kết quả sai.

### Những trường hợp biên

- Không có phần tử, T=0: tồn tại=true, đếm=1, min=max=0 vì tập rỗng là một tập con hợp lệ.
- Không có phần tử, T>0: tồn tại=false, đếm=0, min/max không xác định.
- T=0 khi mọi trọng số đều dương: chỉ có tập rỗng, đếm=1.
- Các giá trị bằng nhau ở **vị trí khác nhau** vẫn là các lựa chọn riêng nếu đếm tập chỉ số.
- Trọng số 0 hay âm đòi hỏi mô hình và xử lý riêng. Bài học cùng chương trình minh họa **chỉ nhận số nguyên dương** để giữ chỉ số tổng và lập luận tối ưu đơn giản.

## 5. Mô hình không giới hạn: mỗi mệnh giá dùng nhiều lần

Đổi đặc tả: có các **mệnh giá nguyên dương phân biệt** c₁,...,cₖ; mỗi loại được dùng bao nhiêu lần cũng được. Hỏi tổng T và **đếm tổ hợp đồng tiền**, nghĩa là **thứ tự các đồng được chọn không tạo ra cách mới**.

Với c=[1,3,4], T=6:

| Tổ hợp (không xét thứ tự) | Số đồng |
| --- | ---: |
| 1+1+1+1+1+1 | 6 |
| 3+1+1+1 | 4 |
| 3+3 | 2 |
| 4+1+1 | 3 |

Vậy **4 tổ hợp**, min số đồng **2**, max số đồng **6**.

Điểm khác 0/1: một loại tiền có thể được dùng nhiều lần, nên trạng thái tổng **s−c** được phép đã sử dụng loại tiền đang xét.

### Hai chiều: bỏ qua loại tiền hoặc dùng thêm một đồng loại đó

Đặt **D[i][s]** là kết quả khi chỉ có **i mệnh giá đầu tiên** và mỗi mệnh giá được dùng không giới hạn.

Nếu mệnh giá mới là cᵢ:

- **Không dùng cᵢ:** lấy từ D[i−1][s].
- **Dùng ít nhất một cᵢ:** bỏ đi một đồng cᵢ, phần còn lại là một tổ hợp tạo s−cᵢ **vẫn được phép dùng cᵢ**, nên lấy từ **D[i][s−cᵢ]** chứ không phải D[i−1][s−cᵢ].

Với số cách:

**C[i][s] = C[i−1][s] + (s≥cᵢ ? C[i][s−cᵢ] : 0)**.

Với min/max số đồng, dùng tương tự hai nhánh và cộng **1** khi lấy thêm cᵢ. Tồn tại dùng OR.

Bằng việc xét mệnh giá theo thứ tự cố định, ta mô tả mỗi tổ hợp bằng **số lần dùng từng loại tiền**. Mỗi tổ hợp xuất hiện đúng một lần, nên phép cộng đếm không bị lặp theo thứ tự đồng tiền.

### Một chiều: duyệt tổng tăng dần

~~~text
for each coin c in coins:             // duyệt từng loại tiền
    for s = c .. T:                   // s tăng dần
        nếu state[s-c] đạt được:
            cập nhật state[s] từ state[s-c] và thêm một đồng c
~~~

Vì s−c < s, khi duyệt tăng ta có thể tái sử dụng kết quả vừa tạo từ cùng mệnh giá, nên phù hợp với **không giới hạn**. Vòng **loại tiền bên ngoài, tổng bên trong** là một phần của định nghĩa bài **đếm tổ hợp không xét thứ tự**.

Đối với min/max và tồn tại, cùng cơ chế này tính được mục tiêu đúng. Nhưng khi **đếm**, chỉ đổi thứ tự vòng lặp có thể làm thay đổi chính **đối tượng được đếm**.

## 6. Đếm tổ hợp khác đếm chuỗi có thứ tự

Một điểm dễ sai nhất của DP đếm là không nói rõ **hai lời giải được xem là khác nhau khi nào**.

Với các bước có độ dài 1,3,4 để đạt tổng 6:

- Nếu thứ tự **không quan trọng**, tổ hợp **3+1+1+1** chỉ là **một cách**, bất kể vị trí của đồng 3.
- Nếu thứ tự **quan trọng**, các chuỗi **3+1+1+1**, **1+3+1+1**, **1+1+3+1**, **1+1+1+3** là **bốn cách khác nhau**.

Đếm chuỗi có thứ tự có công thức khác:

**ordered[0]=1**,

**ordered[s] = tổng ordered[s−c] qua các loại c≤s**, với s từ 1 đến T.

Giả mã:

~~~text
ordered[0] = 1
for s = 1 .. T:                      // tổng bên ngoài
    for each coin c:
        if c <= s:
            ordered[s] += ordered[s-c]
~~~

Với c={1,3,4}, T=6:

- **Đếm tổ hợp:** 4.
- **Đếm chuỗi có thứ tự:** **9**.

Cụ thể, 9 chuỗi là một chuỗi sáu số 1, bốn vị trí có thể đặt một số 3 trong chuỗi gồm 3,1,1,1, ba vị trí có thể đặt số 4 trong chuỗi gồm 4,1,1, và một chuỗi 3,3.

**Tại sao tổng bên ngoài làm đếm chuỗi?** Mỗi lời giải có một **đồng cuối cùng** với mệnh giá c. Bỏ đồng cuối đi tạo một chuỗi có thứ tự tổng s−c. Các trường hợp c khác nhau phân hoạch lời giải theo đồng cuối cùng, nên có thể cộng số chuỗi. Đây là đếm **đường đi có thứ tự**, không phải đếm đa tập mệnh giá.

Trong một bài lập trình, nếu chỉ thấy từ “cách” mà không có quy ước, cần đọc lại mô tả hoặc ví dụ trước khi chọn công thức. Không thể dùng một biến ways và đổi tùy tiện thứ tự hai vòng for.

## 7. Java 17+: bốn mục tiêu trên cùng mô hình chuyển

Chương trình sau triển khai:

- Chọn 0/1: mỗi **vị trí** đầu vào chỉ dùng tối đa một lần; các vị trí bằng giá trị vẫn là phần tử khác nhau.
- Chọn không giới hạn: mỗi **mệnh giá** dùng nhiều lần; chương trình yêu cầu các mệnh giá phân biệt để không đếm lặp cùng một loại tiền.
- Trả đồng thời **exists**, **ways**, **minItems** và **maxItems** cho tổng T.
- Đếm **chính xác** bằng **BigInteger**, không tràn int/long khi số cách quá lớn.
- Khi không thể đạt tổng, minItems và maxItems được trả dưới dạng **−1** (sentinel ở giao diện), trong khi kết quả nội bộ có giá trị khởi tạo riêng.
- Có thêm hàm đếm **chuỗi có thứ tự** để minh họa sự khác biệt với tổ hợp.

Để chương trình ngắn và công thức đúng rõ ràng, các trọng số/mệnh giá trong ví dụ phải là **số nguyên dương**, và T không âm.

~~~java
import java.math.BigInteger;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class FourDpObjectivesDemo {

    enum Mode { ZERO_ONE, UNBOUNDED }

    record Result(boolean exists, BigInteger ways,
                  int minItems, int maxItems) {}

    private static void checkInput(int[] values, int target,
                                   boolean requireDistinct) {
        Objects.requireNonNull(values, "values");
        if (target < 0 || target == Integer.MAX_VALUE) {
            throw new IllegalArgumentException("Invalid target");
        }

        Set<Integer> seen = new HashSet<>();
        for (int value : values) {
            if (value <= 0) {
                throw new IllegalArgumentException(
                        "All values must be positive");
            }
            if (requireDistinct && !seen.add(value)) {
                throw new IllegalArgumentException(
                        "Unbounded coin denominations must be distinct");
            }
        }
    }

    // Trang thai: tong s co the dat duoc hay khong; bao nhieu cach;
    // it nhat / nhieu nhat bao nhieu phan tu de tao dung tong s.
    static Result solve(int[] values, int target, Mode mode) {
        Objects.requireNonNull(mode, "mode");
        checkInput(values, target, mode == Mode.UNBOUNDED);

        boolean[] exists = new boolean[target + 1];
        BigInteger[] ways = new BigInteger[target + 1];
        int[] min = new int[target + 1];
        int[] max = new int[target + 1];

        Arrays.fill(ways, BigInteger.ZERO);
        Arrays.fill(min, Integer.MAX_VALUE);
        Arrays.fill(max, -1);

        exists[0] = true;
        ways[0] = BigInteger.ONE;
        min[0] = 0;
        max[0] = 0;

        for (int value : values) {
            if (mode == Mode.ZERO_ONE) {
                // Duyet giam: khong tai su dung phan tu hien tai.
                for (int s = target; s >= value; s--) {
                    relax(s, value, exists, ways, min, max);
                }
            } else {
                // Duyet tang: duoc tai su dung cung menh gia.
                for (int s = value; s <= target; s++) {
                    relax(s, value, exists, ways, min, max);
                }
            }
        }

        return new Result(
                exists[target],
                ways[target],
                exists[target] ? min[target] : -1,
                exists[target] ? max[target] : -1);
    }

    private static void relax(int s, int value,
                              boolean[] exists, BigInteger[] ways,
                              int[] min, int[] max) {
        int previous = s - value;

        // Bo qua nhanh khong co loi giai.
        if (!exists[previous]) {
            return;
        }

        exists[s] = true;
        ways[s] = ways[s].add(ways[previous]);
        min[s] = Math.min(min[s], min[previous] + 1);
        max[s] = Math.max(max[s], max[previous] + 1);
    }

    // Dem CHUOI tien co thu tu; khac voi so to hop.
    static BigInteger countOrdered(int[] coins, int target) {
        checkInput(coins, target, true);

        BigInteger[] ways = new BigInteger[target + 1];
        Arrays.fill(ways, BigInteger.ZERO);
        ways[0] = BigInteger.ONE;

        for (int s = 1; s <= target; s++) {
            for (int coin : coins) {
                if (coin <= s) {
                    ways[s] = ways[s].add(ways[s - coin]);
                }
            }
        }

        return ways[target];
    }

    public static void main(String[] args) {
        int[] items = {2, 3, 3, 5};
        int[] coins = {1, 3, 4};

        System.out.println("0/1 [2,3,3,5], target 5: "
                + solve(items, 5, Mode.ZERO_ONE));
        System.out.println("0/1 [2,3,3,5], target 6: "
                + solve(items, 6, Mode.ZERO_ONE));

        System.out.println("Unlimited [1,3,4], target 6: "
                + solve(coins, 6, Mode.UNBOUNDED));
        System.out.println("Ordered [1,3,4], target 6: "
                + countOrdered(coins, 6));

        System.out.println("Unlimited [3,4], target 2: "
                + solve(new int[] {3, 4}, 2, Mode.UNBOUNDED));
        System.out.println("Unlimited [], target 0: "
                + solve(new int[] {}, 0, Mode.UNBOUNDED));
    }
}
~~~

Lưu vào tệp **FourDpObjectivesDemo.java** rồi biên dịch/chạy với **JDK 17 trở lên**:

~~~bash
javac FourDpObjectivesDemo.java
java FourDpObjectivesDemo
~~~

Đầu ra chính xác theo quy tắc của record trong Java:

~~~text
0/1 [2,3,3,5], target 5: Result[exists=true, ways=3, minItems=1, maxItems=2]
0/1 [2,3,3,5], target 6: Result[exists=true, ways=1, minItems=2, maxItems=2]
Unlimited [1,3,4], target 6: Result[exists=true, ways=4, minItems=2, maxItems=6]
Ordered [1,3,4], target 6: 9
Unlimited [3,4], target 2: Result[exists=false, ways=0, minItems=-1, maxItems=-1]
Unlimited [], target 0: Result[exists=true, ways=1, minItems=0, maxItems=0]
~~~

### Phân tích các điểm quan trọng của chương trình

**checkInput:** từ chối trọng số không dương. Ở chế độ không giới hạn, nếu có hai mệnh giá cùng giá trị, chúng thực chất là **một loại tiền**; để tránh việc đếm cùng một tổ hợp nhiều lần, chương trình yêu cầu chúng phân biệt. Chế độ 0/1 **cho phép các giá trị trùng**, bởi hai phần tử ở hai vị trí là hai lựa chọn khác nhau.

**solve:** tạo bốn mảng trạng thái cho cùng không gian tổng **0..T**. Khởi tạo tổng 0 làm trạng thái gốc hợp lệ. Những ô còn lại bắt đầu chưa thể đạt.

**relax:** duy nhất một hàm cập nhật làm rõ sự khác biệt giữa bốn mục tiêu: **OR gián tiếp qua exists**, **cộng số cách**, **min**, **max**. Hàm chỉ thêm một phần tử vào trạng thái đã tồn tại, nên không cộng vào vô cùng hoặc dùng −1 sai nghĩa.

**Duyệt tổng giảm ở ZERO_ONE:** bảo đảm khi xét trạng thái s−value, phần tử hiện tại vẫn chưa được dùng. Kết quả đếm là số **tập con chỉ số**, không phải số chuỗi chọn phần tử.

**Duyệt tổng tăng ở UNBOUNDED:** cho phép dùng mệnh giá hiện tại nhiều lần. Vì vòng ngoài đi theo từng loại mệnh giá, mọi tổ hợp không phân biệt thứ tự được đếm một lần.

**countOrdered:** đổi cấu trúc vòng lặp thành **tổng ngoài, đồng tiền trong**. Mỗi lần thêm một đồng vào **cuối chuỗi**, nên cách đổi thứ tự được tính là một cách khác.

**Result:** khi không có lời giải, ways=0 và exists=false, còn minItems/maxItems=−1. Tại target=0, lựa chọn rỗng là một lời giải: exists=true, ways=1, min=max=0.

Chương trình này **không phục hồi danh sách phần tử đã chọn**, chỉ trả các đại lượng mà bốn câu hỏi yêu cầu. Nếu cần in một cách tối ưu, phải lưu quyết định truy vết hoặc suy ngược trên một bảng trạng thái đủ thông tin; không nên coi việc có một giá trị min/max là đã có sẵn đường đi cụ thể.

## 8. Phân tích độ phức tạp và kích thước số cách

Với n giá trị/loại tiền và tổng đích T:

- Có n lượt xử lý.
- Mỗi lượt duyệt tối đa T+1 trạng thái tổng.
- Số lần kiểm tra/chuyển trạng thái là **O(nT)**.
- Bốn mảng trạng thái trong chương trình đều có độ dài T+1, nên số **ô DP** là **O(T)**.

Tuy nhiên, **BigInteger là số nguyên độ dài tùy ý**. Phép cộng hai BigInteger không nhất thiết có chi phí O(1) theo bit. Khi số cách rất lớn, thời gian và bộ nhớ thực còn phụ thuộc **độ dài biểu diễn nhị phân** của ways. Vì vậy phát biểu **O(nT)** là số lượng **bước chuyển và phép cộng số cách** trong mô hình coi phép toán số học là một đơn vị, chứ không phải cận bit-complexity chặt cho mọi đầu vào.

Nếu chỉ cần **tồn tại**, có thể dùng boolean[] hoặc bitset; không cần BigInteger. Nếu chỉ cần **min**, có thể bỏ hai mảng count/max. Lưu cả bốn kết quả chỉ phù hợp khi yêu cầu nhiều mục tiêu hoặc muốn minh họa chúng cùng lúc.

### Khi nào dùng số nguyên modulo?

Nhiều bài đếm có đáp án rất lớn và yêu cầu in **ways modulo M**, chẳng hạn một số nguyên tố lớn. Khi đó:

**ways[s] = (ways[s] + ways[predecessor]) mod M**.

Phải đặc biệt chú ý: **ways[s] mod M = 0 không có nghĩa là không tồn tại lời giải**. Số cách thật có thể là M hoặc bội số của M. Nếu vừa muốn **tồn tại** vừa đếm modulo, cần **biến exists riêng**; không dùng biểu thức waysModulo[s] > 0 làm kiểm tra khả thi.

Khi mô hình có số cách cực lớn nhưng chỉ cần biết có tồn tại, bài toán boolean thường rẻ hơn đáng kể so với đếm chính xác.

## 9. Tối ưu chi phí hoặc phần thưởng: không chỉ đếm số phần tử

Trong ví dụ đồng tiền, mỗi lựa chọn có chi phí **1** vì mục tiêu là số đồng. Nhưng min/max của DP có thể tối ưu đại lượng khác:

- **Min chi phí** đạt một trạng thái: cộng chi phí cạnh/lựa chọn rồi lấy min.
- **Max lợi nhuận** với ràng buộc ngân sách: cộng lợi nhuận rồi lấy max.
- **Min số bước** để đi từ trạng thái ban đầu đến đích.
- **Max số điểm** thu được khi chọn những phần tử không xung đột.
- **Min thời gian hoàn thành** với điều kiện chuyển trạng thái hợp lệ.

Ví dụ bài **0/1 knapsack**: vật i có trọng lượng wᵢ và lợi nhuận vᵢ; giới hạn khối lượng B. Nếu dp[i][b] là **lợi nhuận lớn nhất với khối lượng không vượt b**, công thức thường là:

**dp[i][b] = max(dp[i−1][b], vᵢ + dp[i−1][b−wᵢ])** khi b≥wᵢ.

Cơ sở thường là dp[0][b]=0 cho mọi b≥0 vì chọn rỗng hợp lệ dưới ràng buộc **không vượt b**. Nhưng nếu đổi định nghĩa thành “khối lượng **đúng bằng b**”, cơ sở phải là dp[0][0]=0 và các b>0 không đạt. **Chỉ thay chữ “≤ B” thành “= B” đã làm thay đổi base case**.

Đối với **tối thiểu hóa**, cũng cần phân biệt “đúng bằng mục tiêu” với “ít nhất mục tiêu”. Một trạng thái được định nghĩa mơ hồ là nguyên nhân thường gặp nhất dẫn đến phép min/max áp dụng đúng cú pháp nhưng sai bài toán.

## 10. Cực đại có thể vô hạn và đếm có thể vô hạn

Trong mô hình các mệnh giá **nguyên dương**, để đạt tổng T, số đồng tối đa không vượt **T / minCoin**. Bởi vậy cực đại số đồng là **hữu hạn**. Giả thiết dương cũng khiến các chuyển trạng thái tăng tổng, tạo một hướng duyệt không có chu trình.

Nếu cho phép lựa chọn có **trọng số 0**, ta có thể thêm một đồng 0 vô hạn lần mà vẫn giữ tổng T. Khi đó:

- Nếu đếm số **dãy lựa chọn** không giới hạn, số lời giải có thể **vô hạn**.
- Nếu tối đa hóa **số phần tử chọn**, đáp án có thể **không bị chặn trên**.
- Duyệt tăng s không còn bảo đảm đọc một trạng thái có tổng nhỏ hơn, vì s−0=s; công thức có thể tự phụ thuộc vào chính nó.

Nếu có cả trọng số âm và dương, chu trình tổng bằng 0 cũng có thể gây hiện tượng tương tự tùy ràng buộc. Vì vậy không thể mở rộng mã coin DP sang trọng số 0/âm chỉ bằng cách sửa giới hạn vòng for.

Trong đồ thị trạng thái tổng quát, đặc biệt đồ thị có chu trình, muốn đếm đường đi hoặc tìm cực đại cần hỏi:

1. Có giới hạn số bước/lần sử dụng cạnh không?
2. Có chu trình cho phép đi mãi mà vẫn về trạng thái tương đương không?
3. Nếu tối ưu theo trọng số, chu trình có làm giá trị tốt dần không?
4. Nếu đếm, hai đường đi khác nhau được tính là hai lời giải hay không?

Không phải mọi bài có state và recurrence đều áp dụng được một lượt DP theo chỉ số tăng; cần có **thứ tự phụ thuộc hợp lệ** hoặc một thuật toán phù hợp với chu trình.

## 11. DP trên lưới và đồ thị không chu trình: một mô hình, bốn kết quả

Xét một **đồ thị có hướng không chu trình (DAG)**, với đỉnh bắt đầu s và đỉnh đích t. Mỗi cạnh u→v có chi phí c(u,v). Xử lý các đỉnh theo **thứ tự tô-pô**.

Có thể dùng cùng tập cạnh nhưng thay cách tổng hợp:

- **Có đường đi s→t?** exists[s]=true; với mỗi cạnh u→v, exists[v] |= exists[u].
- **Có bao nhiêu đường đi s→t?** ways[s]=1; với mỗi cạnh u→v, ways[v] += ways[u]. Ở đây hai đường đi phân biệt bằng chuỗi cạnh/đỉnh theo đặc tả, và đồ thị cần có cách biểu diễn cạnh nhất quán.
- **Đường đi chi phí nhỏ nhất?** distMin[s]=0; cập nhật distMin[v]=min(distMin[v], distMin[u]+c).
- **Đường đi chi phí lớn nhất?** distMax[s]=0; cập nhật distMax[v]=max(distMax[v],distMax[u]+c).

Các cập nhật chỉ xảy ra nếu u **đạt được**. Với DAG, số cạnh trên mọi đường đi hữu hạn nên cả min và max trên tập đường đi đều có nghĩa (nếu có đường đi), ngay cả khi có cạnh trọng số âm. Điều này **không đúng nguyên xi cho đồ thị có chu trình**.

### Đường đi trên lưới

Trong lưới R×C, giả sử từ ô (r,c) chỉ được đi **xuống** hoặc **sang phải**. Với r,c hợp lệ:

- Tồn tại đường đến ô: **E[r][c] = E[r−1][c] OR E[r][c−1]**, bỏ các hướng ngoài biên và các ô bị chặn.
- Đếm đường: **C[r][c] = C[r−1][c] + C[r][c−1]**, với gốc start có một đường rỗng.
- Min tổng chi phí: lấy **min** từ hai ô trước cộng chi phí của ô hiện tại.
- Max tổng phần thưởng: lấy **max** từ hai ô trước cộng phần thưởng của ô hiện tại.

Với lưới 2×3 không có vật cản, đi từ góc trên trái đến góc dưới phải cần 1 bước xuống và 2 bước phải. Số thứ tự đường đi là **3**: DRR, RDR, RRD. Nếu mỗi ô có trọng số, công thức min/max thay đổi theo trọng số nhưng **không thay đổi đồ thị phụ thuộc**.

**Điểm đáng chú ý:** tổng hợp OR, +, min hay max là một dạng chọn đại lượng cần giữ lại. Những phép này giống ý tưởng của các cấu trúc đại số (boolean, cộng, min-plus, max-plus), nhưng cách áp dụng vẫn cần đúng base case, đúng cạnh chuyển và giả thiết không đếm trùng.

## 12. Phục hồi lời giải và xử lý nhiều kết quả tối ưu

DP tối ưu thường chỉ trả **giá trị**. Nếu đề yêu cầu **một cách chọn cụ thể**, cần thêm thông tin để truy vết.

Đối với 0/1 với bảng hai chiều:

1. Bắt đầu từ state (n,T).
2. So giá trị hiện tại với nhánh **không chọn phần tử thứ i**.
3. Nếu quyết định chọn hợp lệ và đạt giá trị tối ưu, ghi lại i, giảm tổng đi a[i−1], rồi chuyển về i−1.
4. Lặp đến trạng thái cơ sở.

Khi có **nhiều cách đạt cùng cực trị**, quy tắc phá hòa phải rõ: ưu tiên không chọn/chọn, chỉ số nhỏ hơn, từ điển nhỏ hơn, hoặc một tiêu chí khác. Chỉ lưu min/max không đủ nếu cần tất cả phương án tối ưu hoặc thứ tự xác định giữa các phương án.

### Đếm số lời giải đạt tối ưu

“Giá trị tối ưu bằng 7” và “có 7 lời giải tối ưu” là hai câu hỏi hoàn toàn khác nhau. Nếu đề yêu cầu **cả giá trị min/max lẫn số cách đạt giá trị ấy**, mỗi state có thể trả một cặp **(bestValue, countBest)**:

- Nếu ứng viên tốt hơn bestValue hiện tại: thay bestValue và đặt countBest bằng số cách của ứng viên.
- Nếu ứng viên bằng bestValue: **cộng số cách** của ứng viên, với điều kiện các nhánh đếm được phân hoạch không trùng.
- Nếu ứng viên kém hơn: bỏ qua.

Ví dụ với các vật 0/1 [2,3,3,5] và T=5, min số vật là 1 do vật 5, số cách đạt min là **1**. Tổng số cách đạt T lại là **3**. Nếu chỉ hỏi “đếm số cách” thì 3; nếu hỏi “đếm số cách tối ưu min” thì 1.

Mục tiêu phụ như “số cách tối ưu” có thể làm kiểu giá trị DP khác đi: thay vì một số, cần trả một **record nhiều trường** để combine đủ thông tin.

## 13. So sánh với backtracking, memoization và greedy

**Backtracking/vét cạn** liệt kê mọi lựa chọn có/không hoặc mọi chuỗi đi đến đích. Nó phù hợp khi n nhỏ, khi phải xuất mọi lời giải hoặc khi cắt nhánh hiệu quả; nhưng số lựa chọn thường tăng theo hàm mũ.

**Memoization (top-down DP)** vẫn dùng công thức trạng thái, nhưng chỉ tính một state lần đầu được gọi rồi lưu kết quả. Tốt khi không phải mọi tổng 0..T đều liên quan; cần tránh chu trình trong hệ phụ thuộc và kiểm soát độ sâu đệ quy.

**Tabulation (bottom-up DP)** đi theo thứ tự phụ thuộc hợp lệ và thường dễ kiểm soát bộ nhớ. Với 0/1 dùng duyệt tổng giảm; không giới hạn dùng duyệt tổng tăng theo từng loại tiền.

**Greedy** chỉ giữ một lựa chọn tại mỗi bước theo quy tắc cục bộ; không thể mặc định thay DP bằng greedy khi bài hỏi min/max. Với mệnh giá {1,3,4}, tạo tổng 6 bằng ít đồng nhất: greedy chọn 4+1+1 = 3 đồng, nhưng DP tìm 3+3 = **2** đồng. Đây là phản ví dụ cụ thể cho quy tắc “luôn chọn mệnh giá lớn nhất còn dùng được”.

DP đúng dựa trên **trạng thái chứa đủ thông tin cho phần còn lại** và công thức tổng hợp mọi lựa chọn hợp lệ, không dựa vào sự hấp dẫn cục bộ của một lựa chọn.

## 14. Những lỗi phổ biến cần tránh

1. **Không định nghĩa “một cách” là gì.** Đếm tập chỉ số, đa tập giá trị hay chuỗi có thứ tự có thể cho ba đáp án khác nhau.
2. **Đặt ways[0]=0.** Làm mất cách chọn rỗng và có thể khiến mọi số cách về 0.
3. **Dùng 0 làm sentinel cho min hoặc max khi 0 có thể hợp lệ.** Phải tách vô nghiệm khỏi kết quả thực.
4. **Cộng 1 vào INF mà không kiểm tra.** Với int có thể tràn, cho ra một “min” âm vô lý.
5. **Duyệt tổng tăng trong 0/1.** Có thể dùng một phần tử nhiều lần.
6. **Duyệt tổng giảm cho unbounded coin rồi chờ tái sử dụng cùng loại tiền.** Cách này chặn việc dùng lại trong cùng lượt.
7. **Đổi thứ tự vòng lặp khi đếm mà không kiểm tra ý nghĩa.** Đếm tổ hợp và đếm chuỗi khác nhau.
8. **Có các mệnh giá trùng nhưng coi là các loại tiền độc lập trong bài đếm theo giá trị.** Dễ đếm cùng tổ hợp nhiều lần.
9. **Nhầm số cách modulo bằng 0 với trạng thái không thể đạt.** Số cách thật có thể khác 0.
10. **Chỉ tối ưu theo tổng s nhưng bỏ quên một ràng buộc khác.** Ví dụ giới hạn số lần dùng một loại tiền, giới hạn ngân sách, vị trí liên tiếp hoặc các lựa chọn xung đột có thể đòi hỏi thêm chiều state.
11. **Dùng công thức knapsack “không vượt B” cho bài “đúng bằng B”.** Base case và trạng thái vô nghiệm khác nhau.
12. **Bỏ qua trường hợp T=0.** Một lựa chọn rỗng là hợp lệ theo mô hình ví dụ; tồn tại=true và ways=1.
13. **Dùng int/long cho số cách khổng lồ mà không xét tràn.** Có thể cần BigInteger hoặc modulo được đề quy định.
14. **Áp dụng DP acyclic khi có trọng số 0/âm và chu trình chuyển trạng thái.** Có thể có số cách vô hạn hoặc giá trị cực đại không bị chặn.
15. **Không kiểm tra trạng thái trước khi min/max update.** Kết quả vô nghiệm có thể len vào các trạng thái đạt được.
16. **Tưởng có giá trị min/max là đã có danh sách chọn.** Muốn phục hồi lời giải phải lưu/duy trì thêm đường đi hoặc thông tin truy vết.
17. **Đếm tất cả lời giải và đếm lời giải tối ưu như nhau.** Cần state (best,countBest) nếu câu hỏi yêu cầu số phương án đạt optimum.
18. **Không thử giá trị trùng và dữ liệu không có lời giải.** Đây là hai ca thường làm lộ lỗi logic trong DP đếm.
19. **Đánh giá O(nT) mà quên chi phí BigInteger.** Với đếm chính xác, mỗi phép cộng có độ dài số thay đổi.
20. **Truy vấn nhiều giá trị T nhưng xây bảng chỉ đến T nhỏ hơn.** Cần xác định phạm vi tổng tối đa được hỗ trợ khi xây.

## 15. Bộ kiểm thử cần có

| Input và mô hình | Mục tiêu | Tồn tại | Số cách | Min số phần tử | Max số phần tử |
| --- | ---: | --- | ---: | ---: | ---: |
| 0/1 [2,3,3,5] | 5 | true | 3 | 1 | 2 |
| 0/1 [2,3,3,5] | 6 | true | 1 | 2 | 2 |
| 0/1 [2,3,3,5] | 1 | false | 0 | — | — |
| 0/1 [] | 0 | true | 1 | 0 | 0 |
| 0/1 [] | 2 | false | 0 | — | — |
| Không giới hạn [1,3,4] | 6 | true | 4 | 2 | 6 |
| Không giới hạn [3,4] | 2 | false | 0 | — | — |
| Không giới hạn [3,4] | 6 | true | 1 | 2 | 2 |
| Không giới hạn [] | 0 | true | 1 | 0 | 0 |
| Không giới hạn [] | 2 | false | 0 | — | — |

Dấu “—” ở cột min/max biểu thị **không có nghiệm**, khác với giá trị 0. Trong API minh họa, trạng thái vô nghiệm được biểu diễn bằng **−1** cho hai trường này.

### Kiểm thử đối chiếu với vét cạn

Với n nhỏ và mô hình 0/1, có thể duyệt **2ⁿ tập con theo mặt nạ bit**, tính tổng và số phần tử của từng tập; từ đó đối chiếu bốn kết quả với DP. Với coin unbounded có tất cả trọng số dương, có thể đệ quy duyệt số lượng từng mệnh giá từ 0 đến phần nguyên của số tiền còn lại chia cho mệnh giá. Các cách vét cạn này là **chuẩn tham chiếu để kiểm thử**, không phải khuyến nghị hiệu năng cho dữ liệu lớn.

Ngoài ví dụ cố định, nên thử ngẫu nhiên nhiều bộ nhỏ với:

- T bằng 0, nhỏ hơn mọi trọng số, hoặc đạt chính xác bởi nhiều lựa chọn.
- Hai phần tử cùng giá trị trong 0/1.
- Hai loại tiền khác giá trị nhưng đều chia được T.
- Tồn tại nhiều lời giải có số lượng phần tử khác nhau.
- Không có nghiệm dù T > 0.
- Giá trị T khá lớn để kiểm tra hiệu năng và việc chọn BigInteger/modulo.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Với tập phần tử 0/1 [2,3,3,5], T=5, có bao nhiêu tập **chỉ số** tạo được tổng 5?  
**Đáp án:** 3: một tập chọn 5 và hai tập chọn 2 với một trong hai phần tử 3. Min=1, max=2.

**Câu 2.** Vì sao đếm số cách thường khởi tạo ways[0]=1?  
**Đáp án:** Vì có đúng **một lựa chọn rỗng** tạo tổng 0; nó là điểm xuất phát để xây các cách không rỗng. Đây không phải một đồng tiền đã chọn.

**Câu 3.** Với một phần tử 0/1 trọng số 2 và T=4, vì sao không được duyệt tổng tăng?  
**Đáp án:** Sau khi tạo tổng 2, thuật toán có thể lại dùng chính phần tử đó để tạo tổng 4; trái quy định dùng mỗi phần tử tối đa một lần.

**Câu 4.** Với mệnh giá {1,3,4} không giới hạn và T=6, số tổ hợp và số chuỗi có thứ tự lần lượt là bao nhiêu?  
**Đáp án:** **4 tổ hợp** và **9 chuỗi có thứ tự**.

**Câu 5.** Tại sao min và max của trạng thái không thể đạt không nên khởi tạo bằng 0?  
**Đáp án:** 0 có thể là một đáp án thật. Cần sentinel hoặc cờ đạt được để không nhầm vô nghiệm với lời giải hợp lệ.

**Câu 6.** Nếu đếm theo modulo 5 và số cách thật là 10, waysModulo bằng bao nhiêu và có thể kết luận không tồn tại không?  
**Đáp án:** waysModulo=0 nhưng vẫn có **10 cách**; không được kết luận vô nghiệm.

**Câu 7.** Khi muốn đếm **số lời giải đạt min**, có thể dùng nguyên cách tính ways của tất cả lời giải không?  
**Đáp án:** Không. Cần đếm riêng những nhánh đạt cùng giá trị min tối ưu, bỏ nhánh kém tối ưu.

**Câu 8.** Trong bài lưới 2×3 chỉ đi xuống hoặc phải, có bao nhiêu đường đi từ góc trên trái đến góc dưới phải nếu không có vật cản?  
**Đáp án:** **3** đường: DRR, RDR, RRD.

**Câu 9.** Vì sao greedy đổi 6 bằng {1,3,4} không tối ưu về ít đồng nhất?  
**Đáp án:** Greedy chọn 4+1+1 cần 3 đồng, nhưng 3+3 chỉ cần **2** đồng.

**Câu 10.** Nếu muốn tìm max số đồng khi có đồng mệnh giá 0 được chọn vô hạn, có luôn một cực đại hữu hạn không?  
**Đáp án:** Không. Có thể thêm vô hạn đồng 0 mà tổng không đổi; bài toán có thể **không bị chặn**.

## 17. Tổng kết

Để giải đúng bốn kiểu bài **tồn tại, đếm, cực tiểu và cực đại** bằng quy hoạch động, hãy thực hiện theo thứ tự:

1. **Xác định chính xác một lời giải và một trạng thái:** đếm theo chỉ số, theo giá trị hay theo thứ tự; tổng đúng bằng T hay không vượt T?
2. **Liệt kê đầy đủ các lựa chọn chuyển:** với 0/1 là bỏ/chọn từng phần tử; với unbounded coin là bỏ loại tiền hoặc dùng thêm một đồng cùng loại.
3. **Chọn phép tổng hợp:** **OR** cho tồn tại, **cộng** cho đếm, **min** cho cực tiểu, **max** cho cực đại.
4. **Đặt base case và vô nghiệm đúng nghĩa:** exists[0]=true, ways[0]=1, min/max tại 0 bằng 0; các tổng chưa đạt cần được đánh dấu riêng.
5. **Duyệt theo đúng mô hình dùng lại:** tổng **giảm** cho 0/1, tổng **tăng** theo từng loại cho không giới hạn; với đếm chuỗi có thứ tự, tổng ở vòng ngoài.
6. **Chứng minh không thiếu, không đếm trùng:** mỗi lời giải phải được tạo bởi đúng tập chuyển đã định nghĩa, với cách phân hoạch phù hợp.
7. **Đánh giá chi phí và kiểm thử:** O(nT) chuyển trạng thái, O(T) ô khi tối ưu một chiều; chú ý BigInteger, dữ liệu không hợp lệ, chu trình và nhu cầu phục hồi lời giải.

**Thông điệp chính:** cùng một hệ trạng thái có thể trả lời nhiều câu hỏi, nhưng **ý nghĩa của phép gộp và điều kiện cơ sở** quyết định DP giải đúng mục tiêu nào. Đặc biệt, với bài **đếm**, việc xác định “hai lời giải khác nhau khi nào” quan trọng không kém công thức tính toán.
