# Truy vết khi một bước chuyển ghép nhiều bài toán con

## 1. Ý tưởng: đáp án được dựng từ nhiều nhánh

Trong **quy hoạch động cấu trúc**, trạng thái lớn có thể được tạo bằng cách **ghép kết quả của hai hoặc nhiều bài toán con**. Nếu bài toán chỉ hỏi giá trị tối ưu, một bảng DP có thể đã đủ. Nhưng nếu đề yêu cầu **cấu trúc nghiệm** (cây, cách đặt ngoặc, phân hoạch, tập phần tử ở từng cây con), ta cần **truy vết quyết định ghép** và khôi phục **tất cả các nhánh con**.

Ví dụ:
- Nhân chuỗi ma trận: chọn k để chia chuỗi thành **đoạn trái [i,k] và đoạn phải [k+1,j]**, sau đó ghép hai cách nhân tối ưu bằng một cặp ngoặc.
- Tối ưu cây nhị phân: chọn một nút gốc, truy vết **cây trái và cây phải**.
- DP trên cây có ngân sách: chia ngân sách cho **nhiều cây con**, rồi truy vết quyết định bên trong từng cây con.
- DP trên đoạn: một bước chọn điểm tách hoặc cấu trúc ở giữa, hai đoạn còn lại đều tham gia nghiệm.

Đây là khác biệt cốt lõi với việc truy vết **một tiền nhiệm** trong một đường đi hoặc một trạng thái đơn ở mỗi bước. Một nhánh không thể tự tạo cả cấu trúc cha nếu bước chuyển của cha thực sự cần nhiều con.

**Quy tắc ghi nhớ:** khi một bước chuyển dùng kết quả của những trạng thái con nào, truy vết phải xác định đúng **quyết định tối ưu đã chọn** và khôi phục **toàn bộ những trạng thái con ấy**, không bỏ hoặc dùng lặp một nhánh.

## 2. Mô hình tổng quát cho quy hoạch động có bước ghép

Giả sử trạng thái s có nhiều quyết định hợp lệ d. Khi chọn d, bài toán tách thành các trạng thái con \(s_1,s_2,\ldots,s_t\). Nếu mục tiêu là tổng chi phí, truy hồi có dạng:

\[
DP[s]=\min_{d\in Decisions(s)}
\left(localCost(s,d)+\sum_{r=1}^{t}DP[s_r]\right).
\]

Nếu tối đa hóa, thay min bằng max. Nếu bài toán đếm hoặc dùng hàm tổng hợp khác, phép kết hợp có thể không phải phép cộng; do đó công thức trên là **một mô hình thường gặp**, không phải công thức cho mọi DP cấu trúc.

Muốn khôi phục nghiệm, có thể lưu **decision[s]** là một d đạt tối ưu khi tính DP[s]. Quyết định này phải chứa đủ dữ liệu để xác định:
1. Các trạng thái con nào được sử dụng.
2. Tham số dành cho từng con (ví dụ khoảng chỉ số, ngân sách được cấp, trạng thái cha–con).
3. Cách ghép các nghiệm con thành nghiệm tại s.

Giả mã tổng quát:

~~~text
reconstruct(state):
    if state is a base case:
        return baseSolution(state)

    decision = chosenDecision[state]
    children = childrenOf(state, decision)

    pieces = []
    for child in children:
        pieces.add(reconstruct(child))

    return combine(state, decision, pieces)
~~~

Ở đây **children có thể gồm hai, ba hoặc nhiều trạng thái**, chứ không chỉ một tiền nhiệm. Một lời giải đệ quy đúng cần điều kiện dừng và cần đảm bảo các trạng thái con **nhỏ hơn trạng thái cha** hoặc cấu trúc phụ thuộc không có chu trình.

**Giới hạn của phương pháp cộng nghiệm con:** sau khi cố định d, các bài toán con phải thực sự độc lập về những tương tác còn lại. Nếu chúng dùng chung tài nguyên hoặc có ràng buộc qua biên, các thông tin ảnh hưởng lẫn nhau phải được mã hóa trong trạng thái/quyết định. Không thể tùy tiện cộng các giá trị tối ưu riêng rẽ rồi cho rằng nghiệm ghép vẫn hợp lệ.

## 3. Bài toán mẫu: đặt ngoặc tối ưu khi nhân chuỗi ma trận

### 3.1. Đề bài

Có n ma trận \(A_1,A_2,\ldots,A_n\) cần nhân theo **đúng thứ tự đã cho**. Ma trận A_i có kích thước \(p_{i-1}\times p_i\). Tính chất kết hợp cho phép thay đổi cách **đặt ngoặc**:

\[
(A_1A_2)A_3=A_1(A_2A_3),
\]

nhưng không được hoán đổi thứ tự ma trận tùy ý. Cách đặt ngoặc ảnh hưởng rất lớn tới tổng số phép nhân vô hướng.

Theo thuật toán nhân ma trận cơ bản, nhân ma trận kích thước a×b với ma trận b×c tốn **a·b·c phép nhân vô hướng**. Ta cần tìm cách đặt ngoặc có **tổng chi phí nhỏ nhất**; bài toán này không yêu cầu thực sự nhân các ma trận.

Ví dụ:

| Ma trận | Kích thước |
|---|---|
| A1 | 10 × 30 |
| A2 | 30 × 5 |
| A3 | 5 × 60 |

- Cách \((A_1A_2)A_3\): nhân A1 với A2 tốn 10·30·5=**1.500**; nhân tích 10×5 với A3 tốn 10·5·60=**3.000**; tổng **4.500**.
- Cách \(A_1(A_2A_3)\): nhân A2 với A3 tốn 30·5·60=**9.000**; nhân A1 với tích 30×60 tốn 10·30·60=**18.000**; tổng **27.000**.

Hai kết quả toán học giống nhau và cùng kích thước 10×60, nhưng tổng phép tính khác nhau. Nếu chỉ trả số 4.500, ta mới giải được phần **giá trị tối ưu**; muốn lập kế hoạch nhân thì phải trả **cây đặt ngoặc**.

### 3.2. Quy ước chỉ số và trạng thái

Dùng **chỉ số 0-based trong DP**:
- Mảng dimensions/p có n+1 số nguyên dương, p[0],...,p[n].
- A1 có kích thước p[0]×p[1], A2 là p[1]×p[2], v.v.
- Trạng thái [i,j], với \(0\le i\le j<n\), đại diện chuỗi **A(i+1) ... A(j+1)**.
- Tích của cả đoạn [i,j] luôn có kích thước \(p[i]\times p[j+1]\), không phụ thuộc cách đặt ngoặc.

Định nghĩa:

\[
cost[i][j]=\text{số phép nhân vô hướng tối thiểu để tính tích đoạn [i,j]}.
\]

Nếu i=j thì chỉ có một ma trận, không cần nhân:

\[
cost[i][i]=0.
\]

### 3.3. Chọn điểm chia k và ghép cả hai phía

Với i<j, mọi cách đặt ngoặc của đoạn [i,j] đều có một **phép nhân cuối cùng**. Phép ấy phải tách tại một vị trí k:

\[
i\le k<j.
\]

Hai tích dùng để thực hiện phép nhân cuối:
- **Trái:** đoạn [i,k], kích thước \(p[i]\times p[k+1]\).
- **Phải:** đoạn [k+1,j], kích thước \(p[k+1]\times p[j+1]\).

Chi phí phép nhân cuối là \(p[i]\cdot p[k+1]\cdot p[j+1]\). Vì hai đoạn con đều phải được tính, chi phí của lựa chọn k:

\[
candidate(i,k,j)=cost[i][k]+cost[k+1][j]
+p[i]p[k+1]p[j+1].
\]

Lấy nhỏ nhất trên mọi điểm chia:

\[
\boxed{
cost[i][j]=\min_{i\le k<j}
\left(cost[i][k]+cost[k+1][j]+p[i]p[k+1]p[j+1]\right).
}
\]

**Không được chỉ lấy min của hai con.** Điểm k không chọn một trong hai nhánh để bỏ nhánh còn lại: nó xác định **hai nhánh đều phải được giải**, cộng thêm chi phí ghép cuối.

### 3.4. Lưu quyết định split[i][j]

Trong khi tìm cost[i][j], lưu thêm:

\[
split[i][j]=k^*
\]

là vị trí k cho chi phí nhỏ nhất. Tại trạng thái lá i=j, không cần đọc split[i][i].

Nếu nhiều k cùng đạt chi phí tối ưu, có thể chọn một k theo tie-break rõ ràng. Ví dụ **duyệt k tăng dần, chỉ cập nhật khi chi phí giảm nghiêm ngặt**, thì khi hòa giữ **k nhỏ nhất**. Lưu một quyết định là đủ để khôi phục **một** cách đặt ngoặc tối ưu.

**Ý nghĩa của split:** split[i][j] là **ranh giới giữa hai nhóm ma trận**, không phải chỉ số ma trận được bỏ ra khỏi phép nhân. Sau khi chọn k, vẫn cần mọi ma trận trong đoạn [i,j].

## 4. Chứng minh tính đúng của công thức và quyết định lưu

Chứng minh bằng quy nạp theo độ dài đoạn L=j−i+1.

**Cơ sở L=1:** một ma trận không cần phép nhân ma trận, nên cost[i][i]=0 chính xác.

**Giả thuyết:** mọi đoạn ngắn hơn L đã có chi phí tối thiểu đúng.

**Bước quy nạp:** xét một cách đặt ngoặc bất kỳ của chuỗi A(i+1)...A(j+1). Phép nhân cuối cùng của cách đặt ngoặc đó chia chuỗi thành hai đoạn liên tiếp [i,k] và [k+1,j] với một k hợp lệ.

Nếu cấu trúc của đoạn trái chưa tối ưu cho [i,k], ta thay nó bằng cấu trúc tốt nhất của đoạn ấy. **Kích thước tích trái không đổi** vì thứ tự và tập ma trận không đổi, nên phép nhân với đoạn phải vẫn hợp lệ; tổng chi phí sẽ giảm. Điều này mâu thuẫn với giả thiết cấu trúc gốc tối ưu. Lập luận tương tự cho đoạn phải.

Vì vậy, khi cố định k, nghiệm tối ưu phải dùng **hai nghiệm con tối ưu** cộng chi phí nhân cuối. Xét mọi k là xét mọi loại phép nhân cuối có thể xảy ra; lấy min cho đúng giá trị tối ưu của đoạn [i,j].

Khi tính min, split[i][j] lưu một k đạt min; truy vết theo split ghép những cấu trúc con tối ưu nên cũng trả **một cấu trúc tối ưu toàn đoạn**.

**Điều kiện ghép hợp lệ:** việc thay cấu trúc con không làm đổi kích thước ma trận trung gian. Trong các bài toán cấu trúc khác, muốn dùng phép thay thế tối ưu tương tự phải chứng minh rằng nghiệm con mới còn **tương thích với phần ngoài**; đây không phải điều tự động đúng với mọi trạng thái được đặt ra.

## 5. Điền bảng đúng thứ tự

Tại [i,j], tất cả [i,k] và [k+1,j] đều **ngắn hơn [i,j]**. Vì thế tính các đoạn theo **độ dài tăng dần**:

~~~text
for length = 2 .. n:
    for i = 0 .. n - length:
        j = i + length - 1
        best = infinity

        for k = i .. j - 1:
            candidate = cost[i][k] + cost[k + 1][j]
                      + p[i] * p[k + 1] * p[j + 1]

            if candidate is better than best:
                best = candidate
                split[i][j] = k

        cost[i][j] = best
~~~

Trước các vòng lặp, đặt cost[i][i]=0. Khi đang tính một đoạn dài L, mọi đoạn con được tham chiếu có độ dài nhỏ hơn L và đã được tính. Đây là **bất biến** đảm bảo bảng không dùng giá trị chưa khởi tạo.

Số đoạn (i,j) là O(n²). Mỗi đoạn xét tới O(n) điểm chia k; vì vậy tổng thời gian tính bảng là **O(n³)**, bộ nhớ cho cost và split là **O(n²)**.

Không thể chỉ “duyệt ngược từ hàng cuối” khi chưa có split: trước hết phải xây bảng theo đúng quan hệ phụ thuộc, sau đó mới tiến hành truy vết.

## 6. Ví dụ tính ba ma trận và dựng cây nghiệm

Với \(p=[10,30,5,60]\), có n=3 ma trận.

Chi phí đoạn dài 2:
- cost[0][1]=10·30·5=**1.500**, split[0][1]=0.
- cost[1][2]=30·5·60=**9.000**, split[1][2]=1.

Đoạn [0,2]:
- k=0: cost[0][0]+cost[1][2]+10·30·60 =0+9000+18000=**27000**.
- k=1: cost[0][1]+cost[2][2]+10·5·60 =1500+0+3000=**4500**.

Chọn split[0][2]=**1**, cost[0][2]=**4500**.

| Đoạn | cost | split |
|---|---:|---:|
| [0,0], [1,1], [2,2] | 0 | Không có |
| [0,1] | 1500 | 0 |
| [1,2] | 9000 | 1 |
| [0,2] | **4500** | **1** |

Bắt đầu truy vết tại [0,2]:
1. split[0][2]=1, nên tạo **hai** nhánh: trái [0,1] và phải [2,2].
2. Nhánh trái [0,1] có split=0, tách thành [0,0] và [1,1].
3. Ba lá [0,0], [1,1], [2,2] tương ứng A1, A2, A3.
4. Ghép [0,0] với [1,1] thành (A1 * A2); sau đó ghép cấu trúc ấy với A3.

~~~text
[0,2], split=1
├── [0,1], split=0
│   ├── [0,0] -> A1
│   └── [1,1] -> A2
└── [2,2] -> A3

Cây đặt ngoặc: ((A1 * A2) * A3)
Chi phí tối thiểu: 4500
~~~

Nếu chỉ truy vết nhánh [0,1] và bỏ [2,2], đầu ra sẽ thiếu A3. Nếu đi cả hai nhánh nhưng đảo thứ tự ghép thành A3 * (A1*A2), ta đã **đổi thứ tự ma trận**, không hợp lệ với bài toán đã cho.

## 7. Thuật toán truy vết cây nhị phân

Một hàm build(i,j) tái tạo **toàn bộ tích đoạn [i,j]**:

~~~text
build(i, j):
    if i == j:
        return "A" + (i + 1)

    k = split[i][j]
    left  = build(i, k)
    right = build(k + 1, j)
    return "(" + left + " * " + right + ")"
~~~

Điểm khác nhau so với truy vết một tiền nhiệm là dòng gọi **cả build(i,k) và build(k+1,j)**. Hàm không chỉ “đi theo split”; nó dùng split để xác định **hai đoạn con**.

**Bất biến truy vết:** build(i,j) phải xuất chính xác các ma trận A(i+1),...,A(j+1), mỗi ma trận **đúng một lần và đúng thứ tự**, với chi phí bằng cost[i][j]. Cơ sở i=j xuất một lá; trường hợp i<j ghép hai đoạn liên tiếp, không giao nhau và bao trùm toàn đoạn, nên giữ được bất biến.

Mọi split hợp lệ thỏa i≤k<j, hai con ngắn hơn cha, do đó truy vết kết thúc. Cây tạo ra có n lá và n−1 nút trong; vì vậy có **2n−1 lời gọi build**. Số nút truy vết là O(n); chi phí sinh văn bản còn phụ thuộc số chữ số trong các nhãn A1,..,An. Độ sâu ngăn xếp phụ thuộc hình dạng cây, có thể là O(n) khi cây lệch.

Nếu chỉ cần một nghiệm, lưu một split tại mỗi đoạn là đủ. Nếu phải liệt kê **tất cả** cách đặt ngoặc tối ưu, một split duy nhất không đủ khi nhiều k có cùng chi phí.

## 8. Chương trình Java 17+ đầy đủ

Chương trình sau:
- Tính bảng chi phí tối thiểu và bảng split.
- Khôi phục cách đặt ngoặc bằng **đệ quy trên cả hai nhánh**.
- Ghi **trace theo thứ tự preorder**: cha trước, sau đó con trái, sau đó con phải.
- Xử lý một ma trận, các trường hợp hòa và hai bộ dữ liệu mẫu.
- Dùng Math.addExact, Math.multiplyExact để báo tràn long khi chi phí vượt kiểu số.

Lưu tệp **MultiSubproblemTraceDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public final class MultiSubproblemTraceDemo {
    private MultiSubproblemTraceDemo() {
    }

    public record Result(long minCost, String order, List<String> trace) {
    }

    private static void build(int i, int j, int[][] split,
                              StringBuilder order, List<String> trace) {
        if (i == j) {
            order.append("A").append(i + 1);
            trace.add("[" + i + "," + j + "] -> A" + (i + 1));
            return;
        }

        int k = split[i][j];
        trace.add("[" + i + "," + j + "] -> split " + k);

        order.append("(");
        build(i, k, split, order, trace);
        order.append(" * ");
        build(k + 1, j, split, order, trace);
        order.append(")");
    }

    public static Result optimize(int[] dimensions) {
        if (dimensions == null || dimensions.length < 2) {
            throw new IllegalArgumentException(
                    "Need dimensions for at least one matrix");
        }
        for (int x : dimensions) {
            if (x <= 0) {
                throw new IllegalArgumentException(
                        "Matrix dimensions must be positive");
            }
        }

        int n = dimensions.length - 1;
        long[][] cost = new long[n][n];
        int[][] split = new int[n][n];

        for (int length = 2; length <= n; length++) {
            for (int i = 0; i + length <= n; i++) {
                int j = i + length - 1;
                long best = Long.MAX_VALUE;
                int bestK = -1;

                for (int k = i; k < j; k++) {
                    long multiply = Math.multiplyExact(
                            Math.multiplyExact(
                                    (long) dimensions[i],
                                    (long) dimensions[k + 1]),
                            (long) dimensions[j + 1]);

                    long candidate = Math.addExact(
                            Math.addExact(cost[i][k], cost[k + 1][j]),
                            multiply);

                    // Duyệt k tăng; nếu hòa giữ k nhỏ hơn.
                    if (bestK == -1 || candidate < best) {
                        best = candidate;
                        bestK = k;
                    }
                }

                cost[i][j] = best;
                split[i][j] = bestK;
            }
        }

        StringBuilder order = new StringBuilder();
        List<String> trace = new ArrayList<>();
        build(0, n - 1, split, order, trace);

        return new Result(cost[0][n - 1],
                order.toString(), List.copyOf(trace));
    }

    public static void main(String[] args) {
        int[] dimensions = {10, 30, 5, 60};
        Result first = optimize(dimensions);

        System.out.println("Input: " + Arrays.toString(dimensions));
        System.out.println("Minimum multiplications: "
                + first.minCost());
        System.out.println("Optimal order: " + first.order());
        System.out.println("Preorder trace:");
        for (String step : first.trace()) {
            System.out.println(step);
        }

        Result classic = optimize(
                new int[] {30, 35, 15, 5, 10, 20, 25});
        System.out.println("Six matrices: cost="
                + classic.minCost() + " order=" + classic.order());

        Result tie = optimize(new int[] {2, 2, 2, 2});
        System.out.println("Tie: cost=" + tie.minCost()
                + " order=" + tie.order());

        Result single = optimize(new int[] {12, 18});
        System.out.println("One matrix: cost=" + single.minCost()
                + " order=" + single.order());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 MultiSubproblemTraceDemo.java
java MultiSubproblemTraceDemo
~~~

Stdout:

~~~text
Input: [10, 30, 5, 60]
Minimum multiplications: 4500
Optimal order: ((A1 * A2) * A3)
Preorder trace:
[0,2] -> split 1
[0,1] -> split 0
[0,0] -> A1
[1,1] -> A2
[2,2] -> A3
Six matrices: cost=15125 order=((A1 * (A2 * A3)) * ((A4 * A5) * A6))
Tie: cost=16 order=(A1 * (A2 * A3))
One matrix: cost=0 order=A1
~~~

### Giải thích kết quả

**Ví dụ ba ma trận:** split[0][2]=1, nên hai nhánh [0,1] và [2,2] đều được truy vết. Kết quả \(((A1 * A2) * A3)\), chi phí **4500**.

**Ví dụ sáu ma trận:** mảng dimensions=[30,35,15,5,10,20,25] biểu diễn sáu ma trận, chi phí tối ưu là **15125**. Cách đặt ngoặc in ra là \(((A1 * (A2 * A3)) * ((A4 * A5) * A6))\).

**Tie:** dimensions=[2,2,2,2] cho ba ma trận 2×2; cả hai cách đặt ngoặc có chi phí 16. Vì duyệt k tăng, giữ lựa chọn đầu khi hòa, nên chọn k=0 ở đoạn gốc và xuất **(A1 * (A2 * A3))**.

**One matrix:** dimensions=[12,18] biểu diễn chỉ một ma trận A1, không cần phép nhân, nên minCost=0 và order=A1.

**Giới hạn và an toàn:**
- Hàm từ chối null, mảng có ít hơn hai kích thước hoặc kích thước không dương.
- Mã **không thực sự nhân ma trận**, chỉ tìm kế hoạch và số phép nhân vô hướng.
- Math.multiplyExact và Math.addExact báo tràn long thay vì tạo chi phí âm/sai; ở đầu vào cực lớn, một **ứng viên** có thể tràn dù một phương án khác còn biểu diễn được, nên ứng dụng muốn hỗ trợ miền rất lớn cần dùng BigInteger hoặc xử lý giới hạn đặc biệt.
- Kích thước bảng n×n có thể gây thiếu RAM nếu n quá lớn. Dùng StringBuilder để ghép văn bản theo cây, tránh tạo quá nhiều chuỗi trung gian.
- Các khoảng [i,j] và split k trong trace là **0-based**, nhưng nhãn A1,...,An là **1-based**.

## 9. Truy vết tree DP khi có nhiều hơn hai con

Bài toán nhân ma trận có hai con tại mỗi nút trong. Với **DP trên cây**, một nút u có thể có nhiều con \(c_1,c_2,\ldots,c_d\), và nghiệm ở u cần kết hợp **mọi cây con liên quan**.

Xét bài đơn giản: nút gốc R có hai cây con X,Y; có ngân sách B=2 phải chia giữa chúng. Khi đã cố định lựa chọn tại R, các cây con độc lập. Giả sử thưởng tốt nhất khi cấp **không quá b** đơn vị ngân sách là:

| Ngân sách tối đa b | X | Y |
|---:|---:|---:|
| 0 | 0 | 0 |
| 1 | 6 | 5 |
| 2 | 7 | 9 |

Để dùng ngân sách tổng 2:
- Cấp X=0, Y=2 → 0+9=9.
- Cấp X=1, Y=1 → 6+5=**11**.
- Cấp X=2, Y=0 → 7+0=7.

Phương án tốt nhất là **11**, với quyết định phân bổ \((b_X,b_Y)=(1,1)\). Truy vết ở R phải:
1. Đọc phân bổ X=1, Y=1.
2. Truy vết nghiệm của **X với ngân sách 1**.
3. Truy vết nghiệm của **Y với ngân sách 1**.
4. Ghép hai nghiệm ấy thành nghiệm ở R.

**Sai lầm 1:** cấp toàn bộ B=2 cho **mỗi** con, làm tổng ngân sách vượt 2.

**Sai lầm 2:** chọn X=1 và quên truy vết Y=1, làm kết quả chỉ có một nửa đóng góp.

### Ghép lần lượt các con và lưu quyết định trung gian

Với d con, ta có thể ghép từng con vào DP tiền tố:

\[
merge[t][b]=\text{thưởng lớn nhất khi dùng t con đầu, tổng ngân sách không quá b}.
\]

Cơ sở merge[0][b]=0. Với con thứ t (1-based):

\[
merge[t][b]=\max_{0\le x\le b}
\left(merge[t-1][b-x]+child_t[x]\right).
\]

Ở bước t, **x** là ngân sách cấp cho con thứ t. Khi cập nhật merge[t][b], lưu thêm:

\[
allocation[t][b]=x^*
\]

là một lựa chọn đạt tối ưu.

Truy vết sau khi đã ghép d con:

~~~text
remaining = B
for t = d down to 1:
    x = allocation[t][remaining]
    reconstruct(child[t], x)
    remaining = remaining - x
~~~

Nếu cần xuất các cây con theo thứ tự 1..d, có thể lưu nghiệm rồi đảo các phần hoặc sắp theo chỉ số con; nội dung trả về phải đầy đủ và nhất quán.

**Vì sao lưu allocation theo từng bước t?** Biết merge[d][B] và allocation[d][B] chỉ giải thích phần ngân sách của **con cuối**. Ta còn phải biết cách phân bổ phần dư cho d−1 con trước, nên cần thông tin ở trạng thái merge[d−1][remaining], rồi tiếp tục tới merge[1].

Một phiên bản đơn giản thử x=0..b cho mỗi con mất O(B²) cho mỗi phép ghép; tổng trên n nút cây có thể được chặn thô bởi O(nB²) thời gian. Bộ nhớ còn tùy số bảng trung gian và các quyết định được lưu để truy vết, thường có thể là O(nB) trong mô hình mỗi cạnh ghép một lần.

### Khi lựa chọn tại cha ảnh hưởng đến con

Không phải mọi cây con đều độc lập ngay từ đầu. Ví dụ: “chỉ được chọn con nếu đã chọn cha” hoặc “không được chọn hai đỉnh kề nhau”. Khi đó, trạng thái DP của con phải ghi đúng **tình trạng cha** hoặc những thông tin biên cần thiết.

Truy vết phải truyền đúng trạng thái con đã được chọn trong công thức, không chỉ truyền ngân sách. Ghép các lời giải con tối ưu trong **những trạng thái không tương thích** có thể tạo nghiệm vi phạm ràng buộc.

## 10. Cần lưu quyết định hay có thể tính lại?

**Lưu quyết định ngay khi tính DP** là cách dễ hiểu:
- Cập nhật giá trị tốt nhất.
- Đồng thời lưu **k, gốc cây, phân bổ ngân sách hoặc bộ lựa chọn con** dẫn tới giá trị đó.
- Truy vết sau cùng chỉ đọc quyết định và đi vào các trạng thái con tương ứng.

Với matrix-chain, split có O(n²) ô bổ sung; phần truy vết duyệt O(n) nút trong/lá, ngoài chi phí xuất văn bản.

**Không lưu decision mà tái tìm:** nếu còn bảng cost và dữ liệu đầu vào, có thể thử lại mọi k ở trạng thái [i,j] để tìm k có tổng chi phí bằng cost[i][j]. Cách này vẫn đúng khi dùng đúng công thức, nhưng tốn thêm thời gian; có n−1 trạng thái trong được truy vết, mỗi trạng thái có thể phải thử O(n) k, nên có thể phát sinh **O(n²)** phép thử trong trường hợp xấu nhất.

Không được tái tính bằng cách chỉ chọn nhánh trái rẻ hơn hoặc nhánh phải rẻ hơn. Phải so **tổng hai nhánh cộng chi phí ghép**.

### Khi nhiều quyết định đạt tối ưu

Nếu chỉ cần **một nghiệm**, lưu một quyết định là đủ. Nếu cần **tất cả nghiệm tối ưu**, phải xét các quyết định đồng tối ưu, rồi ghép tất cả nghiệm phù hợp của các trạng thái con.

Số nghiệm cấu trúc có thể tăng rất nhanh, vì mỗi điểm chia tạo các tổ hợp nghiệm của hai phía. Do vậy, thời gian **liệt kê tất cả nghiệm** không còn được bảo đảm chỉ bằng độ phức tạp tính bảng DP; ít nhất phải phụ thuộc số lượng đầu ra.

Các quy tắc tie-break như chọn k nhỏ nhất làm đầu ra có tính xác định. Nếu bài toán yêu cầu nghiệm nhỏ nhất theo tiêu chí khác, phải chứng minh tie-break thực sự đáp ứng tiêu chí ấy; không mặc nhiên lấy k nhỏ nhất là biểu thức ngắn nhất hay cân bằng nhất.

## 11. Chứng minh truy vết trả đúng một nghiệm tối ưu

Tính đúng giá trị DP và tính đúng **nghiệm khôi phục** là hai phần riêng.

**Cơ sở:** ở một trạng thái lá, reconstruct trả đúng cấu trúc cơ sở, chẳng hạn A(i+1) với cost=0.

**Giả thuyết quy nạp:** reconstruct của mọi trạng thái con nhỏ hơn tạo nghiệm hợp lệ đạt đúng giá trị DP của chính con ấy.

**Bước quy nạp:** tại trạng thái cha s, decision[s] là một quyết định đã đạt tối ưu lúc tính DP[s]. Nó xác định các con \(s_1,\ldots,s_t\). Theo giả thuyết quy nạp, mỗi con được truy vết chính xác. Do cách ghép và các điều kiện tương thích được xác định bởi decision[s], combine tạo một nghiệm cha hợp lệ; chi phí của nó bằng đúng biểu thức đạt DP[s]. Vì decision[s] tối ưu, kết quả cha cũng tối ưu.

Với matrix-chain, việc ghép hai đoạn **không giao nhau**, **liền nhau** bảo đảm mỗi ma trận được dùng đúng một lần và đúng thứ tự. Với tree DP chia ngân sách, tổng ngân sách phân bổ **không vượt B** và mỗi con được truy vết dưới chính ngân sách đã được cấp.

**Điều kiện kết thúc:** mọi con phải nhỏ hơn cha theo độ dài đoạn hoặc theo cấu trúc cây. Nếu một decision dẫn về chính trạng thái đang truy vết mà không tiến triển, giải pháp có thể lặp vô hạn; đó là lỗi thiết kế truy hồi/quyết định.

## 12. Kiểm thử đầy đủ: cả giá trị lẫn cấu trúc

Đối với nhân chuỗi ma trận, nên xác nhận:
- Độ dài dimensions là n+1, mọi kích thước dương.
- Mỗi A1..An xuất hiện **đúng một lần**, theo thứ tự chỉ số tăng khi đọc lá từ trái sang phải.
- Mỗi phép ghép có hai phần tử con là hai đoạn ma trận liên tiếp.
- Tổng số nút trong bằng n−1.
- Chi phí cộng từ các nút trong bằng cost[0][n−1].
- Giá trị cost tối ưu khớp với brute force khi n đủ nhỏ (liệt kê mọi cách đặt ngoặc).
- Với ví dụ n=3, hai chi phí 4500 và 27000 đều được tính đúng; min là 4500.
- Với dữ liệu cổ điển sáu ma trận, đáp án chi phí 15125.
- Với ba ma trận 2×2, hai thứ tự đều có chi phí 16, và tie-break trả cách dự kiến.
- Với n=1, không có phép nhân, cost=0 và chỉ một lá A1.

Đối với tree DP, ngoài giá trị tối ưu cần kiểm tra:
- Ngân sách các con cộng lại không vượt ngân sách cha.
- Mọi con được truy vết đúng trạng thái/điều kiện cha–con.
- Không có cây con nào bị bỏ quên hoặc được dùng nhiều lần nếu công thức không cho phép.
- Tổng phần thưởng/chi phí sau khi ghép bằng giá trị DP của trạng thái cha.

**Kiểm thử ngẫu nhiên nhỏ:** sinh các kích thước ma trận nhỏ và so DP với liệt kê toàn bộ cách đặt ngoặc; không chỉ so giá trị mà còn kiểm tra cây được khôi phục. Brute force chỉ để kiểm thử khi n nhỏ vì số cách đặt ngoặc tăng rất nhanh.

## 13. Lỗi thường gặp

1. **Chỉ truy vết một nhánh:** nếu quyết định chia thành [i,k] và [k+1,j], phải tái tạo **cả hai**.
2. **Lưu cost mà không lưu quyết định:** nếu cần cấu trúc nghiệm phải lưu split hoặc đủ thông tin để tính lại k.
3. **Nhầm k với phần tử bị loại:** k là ranh giới tách; không xóa ma trận A(k+1) hay A(k+2).
4. **Sai công thức kích thước:** với chỉ số 0-based, chi phí ghép matrix-chain là p[i]·p[k+1]·p[j+1].
5. **Để k=j hoặc k<i:** tạo đoạn rỗng hoặc không giảm kích thước; truy vết có thể sai.
6. **Hoán đổi trái và phải:** phép nhân ma trận nói chung không giao hoán; chỉ thay ngoặc, không đổi thứ tự.
7. **Lưu split không khớp cost:** khi cập nhật best phải cập nhật k cùng lúc.
8. **Đọc split[i][i] ở lá:** trạng thái một ma trận không có điểm chia.
9. **Nhầm giá trị chưa tính với một quyết định hợp lệ:** k=0 là hợp lệ; sentinel chưa có lựa chọn phải khác và cần dùng đúng điều kiện cơ sở.
10. **Giữ ngân sách B cho từng con:** có thể chi quá B vì không dùng phân bổ đã lưu.
11. **Quên quyết định ghép trung gian của nhiều con:** biết phân bổ con cuối không cho biết phân bổ của tất cả con trước.
12. **Không đưa ràng buộc cha–con vào trạng thái:** các nghiệm con riêng lẻ có thể không ghép hợp lệ.
13. **Tin rằng cây truy vết luôn sâu log n:** cây lệch có thể sâu O(n).
14. **Đồng nhất thời gian tính DP và thời gian khôi phục:** matrix-chain tính bảng O(n³) nhưng truy vết cây chỉ O(n) nút.
15. **Liệt kê mọi nghiệm bằng một split duy nhất:** một quyết định chỉ xác định một cấu trúc tối ưu.
16. **Không xử lý overflow:** chi phí có thể vượt int và long; cần giới hạn dữ liệu hoặc kiểu số phù hợp.
17. **Đưa quyết định khác mục tiêu vào lúc truy vết:** phải theo đúng lựa chọn đạt cost đã chốt, hoặc chứng minh quyết định mới đồng tối ưu.
18. **Không đối chiếu tính hợp lệ cấu trúc:** một số chi phí đúng không bảo đảm biểu thức hoặc phân bổ được khôi phục đúng.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao truy vết matrix-chain khác với truy vết một tiền nhiệm trong LCS?

**Đáp án:** Một điểm chia k sinh **hai** đoạn cần giải [i,k] và [k+1,j]. Một nghiệm của cha gồm **cả hai** nghiệm con và phép ghép; đi theo một tiền nhiệm duy nhất sẽ thiếu phần còn lại.

**Câu 2.** Với p=[10,30,5,60], cách đặt ngoặc và chi phí tối ưu là gì?

**Đáp án:** \(((A1*A2)*A3)\), chi phí 1500+3000=4500. Cách đối chứng A1*(A2*A3) tốn 9000+18000=27000.

**Câu 3.** split[0][2]=1 nói gì?

**Đáp án:** Ở phép nhân cuối, ghép tích đoạn [0,1] với tích đoạn [2,2]; chính là (A1*A2) với A3. Nó không loại một ma trận nào.

**Câu 4.** Tại sao điền bảng theo độ dài đoạn tăng dần?

**Đáp án:** Mọi cost[i][j] đều dùng chi phí của các đoạn con ngắn hơn. Tính theo độ dài bảo đảm các giá trị ấy đã sẵn sàng.

**Câu 5.** Khi có hai k đồng tối ưu, lưu một k đã đủ chưa?

**Đáp án:** Đủ để khôi phục **một** cây tối ưu. Không đủ để liệt kê mọi cây tối ưu; cần giữ hoặc tìm các lựa chọn đồng tối ưu.

**Câu 6.** Với X=[0,6,7], Y=[0,5,9], B=2, nên phân ngân sách như thế nào?

**Đáp án:** Cho X một đơn vị và Y một đơn vị, thưởng 6+5=**11** lớn hơn phương án cấp 0:2 (9) hoặc 2:0 (7). Truy vết phải đi vào cả hai cây con với phần ngân sách đã phân.

**Câu 7.** Vì sao allocation[t][b] thường phải lưu cho nhiều bước t?

**Đáp án:** Sau khi biết con thứ t nhận x, còn phải khôi phục phân bổ b−x cho t−1 con trước. Nếu không lưu hoặc tính lại các quyết định trung gian, không biết phân chia phần còn lại.

**Câu 8.** Matrix-chain có n ma trận cần bao nhiêu thời gian và bộ nhớ để tính bảng?

**Đáp án:** O(n³) thời gian và O(n²) bộ nhớ cost/split. Truy vết có O(n) nút trong/lá, cộng thời gian tạo chuỗi đầu ra.

**Câu 9.** Khi nào không thể cộng hai lời giải con tối ưu riêng lẻ?

**Đáp án:** Khi hai con còn phụ thuộc nhau qua tài nguyên dùng chung hoặc ràng buộc không biểu diễn trong trạng thái. Phải lưu đủ thông tin tương tác và chứng minh phép ghép hợp lệ.

**Ghi nhớ:** Với bước chuyển DP **ghép nhiều bài toán con**, giá trị tối ưu chỉ là một nửa kết quả. Cần lưu **lựa chọn tối ưu** và **truy vết mọi trạng thái con** tạo nên lựa chọn ấy, sau đó **ghép đúng cấu trúc, thứ tự và ràng buộc** để khôi phục một nghiệm đầy đủ.
