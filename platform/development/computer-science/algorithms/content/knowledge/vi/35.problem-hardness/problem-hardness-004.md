# Bài toán quyết định, chứng chỉ và kiểm tra lời giải

> **Chủ đề:** Computer Science Algorithms → **Độ khó bài toán**.  
> **Mục tiêu:** Phân biệt bài toán **quyết định** (YES/NO), bài toán tìm kiếm và tối ưu; nắm định nghĩa **chứng chỉ** (*certificate/witness*) và **bộ kiểm tra lời giải** (*verifier*) chạy trong thời gian đa thức; hiểu chính xác mối quan hệ giữa **P, NP, coNP, NP-hard, NP-complete**; phân biệt *tự tìm nghiệm* với *kiểm một nghiệm được cung cấp*. Bài có **5 chương trình Java 17 độc lập** kiểm chứng chứng chỉ cho CNF-SAT, CLIQUE, SUBSET SUM, HAMILTONIAN CYCLE và GRAPH COLORING, các ví dụ hợp lệ/giả mạo, chứng minh đúng, phân tích theo kích thước đầu vào nhị phân và bài tập có đáp án.

## 1. Bài toán quyết định trả lời câu hỏi gì?

Một **bài toán quyết định** nhận một **thể hiện** (*instance*) x và trả về đúng một trong hai kết quả:

- **YES:** thể hiện có tính chất cần hỏi.
- **NO:** thể hiện không có tính chất đó.

Ví dụ:

- “Đồ thị G có **clique kích thước ít nhất k** không?”
- “Có thể chọn một số phần tử của dãy sao cho tổng **đúng bằng T** không?”
- “Công thức Boolean F có **một phép gán làm F đúng** không?”
- “Đồ thị có chu trình đi qua **mỗi đỉnh đúng một lần** rồi về đầu không?”
- “Có thể tô đồ thị bằng **không quá k màu** mà hai đầu mọi cạnh khác màu không?”

Câu trả lời YES/NO thường ngắn hơn nhiều so với việc **tìm** một nghiệm cụ thể.

### 1.1. Quyết định, tìm kiếm và tối ưu

Ba dạng câu hỏi có liên quan nhưng không đồng nhất:

| Dạng | Ví dụ CLIQUE | Đầu ra |
|---|---|---|
| **Quyết định** | Có clique ≥k không? | YES/NO |
| **Tìm kiếm** | Hãy chỉ ra một clique ≥k, nếu có | Tập đỉnh hoặc thông báo không tồn tại |
| **Tối ưu** | Clique lớn nhất có bao nhiêu đỉnh? | Giá trị tối ưu ω(G), có thể kèm đỉnh |

Tương tự, TSP tối ưu hỏi độ dài tour nhỏ nhất, còn **TSP quyết định** hỏi “Có tour có tổng chi phí ≤B không?”.

Đối với nhiều bài toán, có thể chuyển từ **tối ưu** sang nhiều truy vấn **quyết định** bằng tìm nhị phân trên giá trị mục tiêu khi có các giới hạn và biểu diễn thích hợp. Tuy nhiên phải tính cả số bit của ngưỡng, và một oracle YES/NO không tự động đưa ra **chứng chỉ đường đi** nếu không có cơ chế khôi phục.

### 1.2. Một bài toán quyết định là một tập ngôn ngữ

Trong lý thuyết độ phức tạp, ta chọn một cách mã hóa hợp lệ thể hiện x thành chuỗi nhị phân:

`enc(x)∈{0,1}*`.

Bài toán tương ứng với **ngôn ngữ YES**:

`L = { enc(x) | câu trả lời cho x là YES }`.

Một thuật toán giải bài toán quyết định phải phân biệt thành viên và không thành viên của L.

Đầu vào sai cú pháp theo quy ước thường được **từ chối**, nhưng việc validate định dạng **khác** với kết luận rằng một thể hiện hợp lệ là NO. Các demo trong bài dùng một quy ước rõ: nếu dữ liệu instance/certificate không đúng định dạng, `verify` trả `false`.

### 1.3. “Có thể kiểm nhanh” không có nghĩa “có thể tìm nhanh”

Một Sudoku đã điền đầy đủ thường dễ kiểm so với việc tự điền. Một tour TSP đã cho dễ cộng chi phí so với việc tìm tour ngắn nhất. Điều này là **trực giác hữu ích** để hiểu NP, nhưng cần định nghĩa chính thức theo **độ dài mã hóa** và giới hạn thời gian đa thức.

## 2. Kích thước đầu vào là số bit, không chỉ số đối tượng

Độ phức tạp đa thức tính theo **độ dài chuỗi mã hóa input**, ký hiệu `N=|enc(x)|`, chứ không nhất thiết theo giá trị của các số trong input.

Ví dụ số nguyên T được mã hóa nhị phân cần `Θ(log2(T+1))` bit khi T≥0. Một thuật toán có thời gian O(nT) có thể chạy rất lâu khi T lớn, và **không phải** đa thức theo `n+log T` nói chung.

### 2.1. Cấu trúc đồ thị

Một đồ thị n đỉnh:

- Ma trận kề `boolean[n][n]` chiếm Θ(n²) ô; kiểm định dạng/đối xứng có thể tốn O(n²).
- Danh sách cạnh có m cạnh chiếm khoảng O(m log n) bit cộng thông tin n và overhead mã hóa.
- Một tập k đỉnh bằng ID trong `[0,n)` cần O(k log n) bit, không phải O(k) bit trong mô hình bit chuẩn.

Nếu thuật toán phân tích bằng phép toán trên chỉ số Java `int` có giới hạn hữu hạn, ta có thể nói O(n²) **word operations**; để khẳng định đa thức lý thuyết cần tính thêm kích thước biểu diễn của các số liên quan.

### 2.2. Dữ liệu số lớn

SUBSET SUM có n số a_i và mục tiêu T. Kích thước input liên quan tới **tổng số bit các số**, không phải chỉ n. Một chứng chỉ chỉ gồm **các vị trí chọn**, nên có độ dài đa thức dù tổng có thể vượt `long`.

### 2.3. Cách mã hóa không được giấu thông tin siêu lớn

Định nghĩa của lớp độ phức tạp dùng các mã hóa “hợp lý” có thể chuyển đổi trong thời gian đa thức. Nếu tùy ý cho một trường chứa một số khổng lồ dưới dạng một ký tự đặc biệt, tuyên bố thời gian “đa thức” có thể đánh lừa. Khi phân tích thuật toán, hãy công bố cách mã hóa **nhị phân/unary** và loại dữ liệu.

## 3. Chứng chỉ (certificate/witness) là gì?

**Chứng chỉ YES** là thông tin bổ sung w, thường là một cấu trúc nghiệm cụ thể, giúp kiểm tra nhanh rằng instance x thực sự thuộc L.

Ví dụ:

| Bài toán | Chứng chỉ YES có thể là |
|---|---|
| SAT | Các giá trị true/false của biến |
| CLIQUE | Danh sách k đỉnh đôi một kề nhau |
| SUBSET SUM | Danh sách vị trí các số được chọn |
| HAMILTONIAN CYCLE | Hoán vị các đỉnh theo thứ tự đi tour |
| k-COLORING | Nhãn màu của từng đỉnh |
| TSP quyết định | Thứ tự tour có chi phí ≤B |
| VERTEX COVER | Danh sách đỉnh phủ mọi cạnh |
| INDEPENDENT SET | Danh sách đỉnh không có cạnh nối từng cặp |

Một chứng chỉ phải **gắn với thể hiện cụ thể**. Không thể dùng assignment của công thức F1 để khẳng định F2 thỏa mãn trừ khi kiểm lại trên F2.

### 3.1. Hai điều kiện logic bắt buộc

Một bộ kiểm tra `V(x,w)` phải phân biệt:

- **Tính đầy đủ (*completeness*):** Nếu x là YES, tồn tại **ít nhất một** w hợp lệ khiến `V(x,w)=true`.
- **Tính đúng đắn (*soundness*):** Nếu `V(x,w)=true` thì x **thực sự là YES**; chứng chỉ giả không được lọt qua.

Cả hai đều thiết yếu. Một hàm `verify` **luôn trả false** có soundness một cách rỗng nhưng không có completeness. Một hàm **luôn trả true** có completeness nhưng soundness sai.

### 3.2. Không chấp nhận chưa đủ để nói NO

Nếu `V(x,w)=false`, kết luận đúng là:

> “Chứng chỉ **w này** không xác nhận YES cho x.”

Nó **không** đồng nghĩa:

> “Không tồn tại chứng chỉ nào khác, nên x chắc chắn là NO.”

Ví dụ một tập 3 đỉnh không tạo clique không ngăn cản đồ thị có **một tập 3 đỉnh khác** tạo clique.

### 3.3. Chứng chỉ không phải lời giải do verifier tạo

Verifier nhận w từ bên ngoài và chỉ kiểm. Nó không cần chọn biến SAT, tìm clique, tìm tour, hay duyệt hết các tập con. Chính việc **tìm w** có thể là phần khó.

## 4. Định nghĩa NP bằng bộ kiểm tra đa thức

Ngôn ngữ L thuộc NP nếu tồn tại:

- Một đa thức p(N).
- Một thuật toán **xác định** V chạy trong thời gian đa thức theo N (khi w có độ dài bị chặn bởi p(N)).

Sao cho với mọi x hợp lệ:

`x ∈ L ⇔ tồn tại w, |w|≤p(|x|) và V(x,w)=1`.

Định nghĩa có hai yếu tố độc lập:

1. **Độ dài chứng chỉ** được chặn bởi một đa thức theo kích thước input.
2. **Chi phí kiểm chứng** chứng chỉ không vượt thời gian đa thức.

Chỉ nói “đã có đáp án nên kiểm nhanh” mà không nêu cách kiểm và độ dài chứng chỉ là chưa chứng minh thuộc NP.

### 4.1. Vì sao “nondeterministic” xuất hiện trong tên NP?

NP là viết tắt của *nondeterministic polynomial time*. Trong mô hình máy Turing không đơn định, máy có thể “đoán” w theo nhánh không đơn định rồi kiểm trong thời gian đa thức.

Định nghĩa bằng chứng chỉ ở trên **tương đương** mô hình này về lớp ngôn ngữ. Không nên diễn giải “máy tính chạy ngẫu nhiên vài lần là đoán đúng” — không đơn định là **một mô hình toán học**, không phải một thuật toán randomized hiệu quả thực tế.

### 4.2. Không cần chứng chỉ ngắn cho mọi NO theo định nghĩa NP

NP mô tả **chứng chỉ YES**. Một instance NO có thể không có chứng chỉ NO ngắn dễ kiểm bằng cơ chế tương tự.

Lớp **coNP** chứa những ngôn ngữ có **phần bù nằm trong NP**. Ví dụ UNSAT (công thức không thỏa mãn) nằm trong coNP, vì phần bù của nó là SAT thuộc NP. Không được khẳng định từ đây rằng đã có chứng chỉ NO đa thức cho mọi công thức SAT.

### 4.3. Trường hợp P

P là lớp bài toán quyết định giải được trong thời gian đa thức **bằng thuật toán xác định**. Ta có:

`P ⊆ NP`.

Nếu biết một thuật toán quyết định đa thức, ta có thể làm verifier **bỏ qua w** và tự chạy thuật toán; cũng có thể coi chứng chỉ là chuỗi rỗng.

Mọi bài toán trong P cũng có ngôn ngữ phần bù trong P, do đổi YES/NO; vì thế:

`P ⊆ NP ∩ coNP`.

Điều đó không khẳng định `NP=coNP`.

## 5. NP, NP-hard và NP-complete không giống nhau

| Khái niệm | Định nghĩa cốt lõi | Hệ quả |
|---|---|---|
| **P** | Quyết định trong thời gian đa thức xác định | Có thuật toán quyết định nhanh theo lý thuyết |
| **NP** | Có chứng chỉ YES dài đa thức và kiểm đa thức | **Không nhất thiết** đã biết cách tìm w nhanh |
| **coNP** | Phần bù ngôn ngữ ở NP | Quan tâm chứng cứ về NO của bài toán gốc |
| **NP-hard** | Mọi bài trong NP quy giảm đa thức đến bài này | Ít nhất khó như mọi bài NP theo phép giảm được chọn |
| **NP-complete** | **Vừa ở NP vừa NP-hard** | Đại diện khó nhất bên trong NP |

**Kiểm nhanh chứng chỉ YES chỉ chứng minh tính thuộc NP**, **không** chứng minh NP-hard hay NP-complete.

### 5.1. Có thể NP-hard mà không nằm trong NP

Một bài toán tối ưu hoặc một bài toán ngôn ngữ ngoài NP vẫn có thể NP-hard. Do đó “NP-hard” không tự cho biết nó có chứng chỉ YES đa thức, thậm chí không nhất thiết là bài toán quyết định.

### 5.2. Những ví dụ kinh điển

- SAT và 3-SAT: NP-complete.
- CLIQUE decision: NP-complete.
- VERTEX COVER decision: NP-complete.
- HAMILTONIAN CYCLE decision (đồ thị tổng quát): NP-complete.
- SUBSET SUM decision với số nguyên dương mã hóa nhị phân: NP-complete.
- 3-COLORING: NP-complete; **2-COLORING** giải được đa thức bằng kiểm lưỡng phân.
- TSP decision trong dạng chuẩn tổng quát phù hợp: NP-complete; **TSP optimization** thường gọi NP-hard, không gọi bản tối ưu là một ngôn ngữ NP-complete nếu chưa chuyển về dạng quyết định.

### 5.3. P so với NP

Câu hỏi `P=?NP` **chưa có lời giải được chấp nhận**. Việc một verifier chạy nhanh không trả lời câu hỏi này.

Không được viết “NP là các bài toán không giải được nhanh” hoặc “NP nghĩa là non-polynomial”. Những phát biểu đó sai: P là **tập con của NP**.

## 6. Cấu trúc một verifier an toàn

Một verifier nhận:

`Instance x` và `Certificate w`.

Nó phải:

1. **Kiểm định dạng** instance: kích thước, dữ liệu, quy ước đồ thị, giá trị mục tiêu.
2. **Kiểm định dạng** certificate: độ dài, loại giá trị, miền chỉ số.
3. **Kiểm không có dữ liệu giả**: ID vượt range, phần tử trùng không hợp lệ, cạnh không tồn tại, giá trị tổng bị tràn.
4. **Kiểm trực tiếp tính chất** đề bài yêu cầu.
5. Chỉ trả true khi **mọi điều kiện đều đúng**.

Không được dùng một kết quả kiểm từng phần để chấp nhận sớm trước khi đã xác nhận toàn bộ cấu trúc đầu vào hợp lệ.

### 6.1. Verifier không phải chương trình tìm kiếm

Sai thiết kế:

```text
verify(graph, certificate):
    if certificate is invalid:
        enumerate all cliques until one succeeds
    return success
```

Đây đã biến **kiểm tra** thành **tự giải**. Muốn chứng minh NP membership, verifier nên dùng trực tiếp witness, không thử lại vô số witness khác.

### 6.2. Độ dài của w

Nếu w ngắn nhưng câu lệnh “kiểm w” thực chất chạy một hàm thời gian mũ, ta vẫn **chưa chứng minh thuộc NP**.

Ngược lại, việc thử **tất cả** w có thể tốn thời gian mũ, nhưng điều đó không ảnh hưởng đến việc **mỗi lần kiểm một w** chỉ tốn đa thức.

### 6.3. Dữ liệu không đáng tin

Trong Java, certificate có thể đến từ file/API không đáng tin. Kiểm null, ID âm, ID vượt mảng, phần tử trùng, matrix không đối xứng, cạnh tự nối hoặc dữ liệu số tràn. Một exception thay vì false có thể là lỗi chất lượng API; nhưng cả hai đều **không phải** chứng nhận YES.

## 7. CNF-SAT: chứng chỉ là phép gán Boolean

Một công thức Boolean dạng chuẩn hội (*conjunctive normal form*, CNF) là phép **AND** của các mệnh đề (*clauses*), mỗi clause là **OR** của các literal. Literal là biến x_i hoặc phủ định ¬x_i.

Ví dụ:

`F = (x1 ∨ ¬x2 ∨ x3) ∧ (¬x1 ∨ x2) ∧ (x2 ∨ ¬x3)`.

Hỏi: Có phép gán `(x1,x2,x3)` làm F đúng không?

### 7.1. Chứng chỉ

Một mảng `boolean[n]` mô tả giá trị của n biến; độ dài O(n) bit trong mô hình toán học. Một verifier duyệt từng clause và kiểm có **ít nhất một literal đúng**.

Với:

`x1=true, x2=true, x3=false`,

cả ba clause đều đúng. Do đó F là YES và mảng này là một chứng chỉ hợp lệ.

Với:

`x1=false, x2=true, x3=false`,

clause đầu `(x1 ∨ ¬x2 ∨ x3)` là false. Chứng chỉ này **không hợp lệ**, dù F vẫn có phép gán khác thỏa mãn.

### 7.2. Mã hóa signed-literal trong Java

Quy ước literal nguyên:

- `+i` đại diện x_i.
- `-i` đại diện ¬x_i.
- i trong `[1,n]`.
- `0` không phải literal hợp lệ.
- `Integer.MIN_VALUE` phải được xử lý không tràn khi lấy trị tuyệt đối; chuyển sang `long` **trước khi gọi Math.abs**.

Thành phần `int[][]` chứa mảng các clause. Verifier kiểm **tất cả literal** thuộc miền trước khi đánh giá, tránh một clause đúng sớm che mất dữ liệu malformed phía sau.

### 7.3. Trường hợp rỗng quan trọng

- **CNF không có clause**: một AND rỗng được quy ước là true, **mọi phép gán** thỏa.
- **Một clause rỗng**: OR rỗng là false, **không phép gán nào** thỏa.
- Biến không xuất hiện trong F: có thể nhận bất kỳ giá trị nào; verifier vẫn kiểm mảng có đúng n biến theo schema.

### 7.4. Độ phức tạp

Đặt `L` là tổng số literal xuất hiện. Kiểm chứng cần O(n+L) lần truy cập/đánh giá logic khi input đã được biểu diễn phù hợp; nếu tính bit complexity, cần cộng chi phí đọc/giải mã literal và chỉ số. Chứng chỉ n bit là đa thức theo input đã mã hóa n biến và formula.

Không gian có thể O(1) bổ sung ngoài input/certificate cho cách cài đặt hai vòng, nếu chỉ dùng biến đếm.

## 8. Java 17 — verifier CNF-SAT không tự giải SAT

Lưu **SatCertificateDemo.java**:

```java
public class SatCertificateDemo {
    record Cnf(int variables, int[][] clauses) {}

    static boolean verify(Cnf instance, boolean[] assignment) {
        if (instance == null || instance.variables() < 0
                || instance.clauses() == null
                || assignment == null
                || assignment.length != instance.variables()) {
            return false;
        }

        // Validate the entire formula before accepting any assignment.
        for (int[] clause : instance.clauses()) {
            if (clause == null) return false;
            for (int literal : clause) {
                long variable = Math.abs((long) literal);
                if (variable < 1 || variable > instance.variables()) {
                    return false;
                }
            }
        }

        for (int[] clause : instance.clauses()) {
            boolean satisfied = false;
            for (int literal : clause) {
                int index = (int) Math.abs((long) literal) - 1;
                boolean value = assignment[index];
                if (literal < 0) value = !value;
                if (value) {
                    satisfied = true;
                    break;
                }
            }
            if (!satisfied) return false;
        }
        return true;
    }

    public static void main(String[] args) {
        Cnf instance = new Cnf(3, new int[][] {
                {1, -2, 3}, {-1, 2}, {2, -3}
        });

        System.out.println("valid assignment: "
                + verify(instance, new boolean[] {true, true, false}));
        System.out.println("invalid assignment: "
                + verify(instance, new boolean[] {false, true, false}));
        System.out.println("another valid assignment: "
                + verify(instance, new boolean[] {false, false, false}));
        System.out.println("short certificate: "
                + verify(instance, new boolean[] {true, false}));

        System.out.println("empty conjunction: "
                + verify(new Cnf(2, new int[0][]),
                         new boolean[] {false, false}));
        System.out.println("empty clause: "
                + verify(new Cnf(1, new int[][] {{}}),
                         new boolean[] {false}));
        System.out.println("out-of-range literal: "
                + verify(new Cnf(1, new int[][] {{2}}),
                         new boolean[] {true}));
        System.out.println("zero literal: "
                + verify(new Cnf(1, new int[][] {{0}}),
                         new boolean[] {true}));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 SatCertificateDemo.java
java SatCertificateDemo
```

Stdout:

```text
valid assignment: true
invalid assignment: false
another valid assignment: true
short certificate: false
empty conjunction: true
empty clause: false
out-of-range literal: false
zero literal: false
```

**Diễn giải:** Dòng `invalid assignment: false` **không** chứng minh F là UNSAT; các dòng true đã cho thấy ít nhất một assignment làm F đúng. Việc xác nhận một assignment không đồng nghĩa một thuật toán đã **tìm ra** assignment ấy.

## 9. CLIQUE: kiểm một tập đỉnh đôi một kề nhau

Cho đồ thị vô hướng đơn G=(V,E) và số nguyên k≥0.

Bài toán quyết định:

> Có tập S⊆V với `|S|≥k` mà mọi cặp hai đỉnh khác nhau trong S được nối bởi cạnh không?

Ta chỉ cần đưa một chứng chỉ có **đúng k đỉnh**, vì nếu có clique lớn hơn k thì chọn bất kỳ k đỉnh của nó cũng tạo clique.

### 9.1. Chứng chỉ

Danh sách `S=[v1,...,vk]` với:

1. Đúng k phần tử.
2. Từng ID thuộc `[0,n)`.
3. Các đỉnh **phân biệt**.
4. Với mọi i<j, cạnh `(vi,vj)` tồn tại.

Ví dụ đồ thị có tam giác `(0,1),(1,2),(0,2)`, tập `[0,1,2]` là chứng chỉ YES cho k=3.

Tập `[0,1,4]` có thể thất bại nhưng **không chứng minh** đồ thị không có clique3.

### 9.2. Độ phức tạp và tính đúng

Sau kiểm tra dữ liệu đồ thị là đơn/vô hướng, verifier kiểm O(k²) cặp đỉnh. Nếu dùng matrix `boolean[n][n]` và validate toàn đồ thị, tổng O(n²+k²)=O(n²) vì k≤n.

- Nếu trả true, mọi cặp trong S kề nhau ⇒ S là clique k ⇒ instance YES (**soundness**).
- Nếu G có clique ít nhất k, lấy k đỉnh của clique đó làm chứng chỉ ⇒ verifier trả true (**completeness**).

### 9.3. k=0 và trường hợp đặc biệt

Tập rỗng được coi là clique kích thước0. Do đó **mọi đồ thị hợp lệ** trả YES với k=0. Nếu k>n thì chắc chắn NO. Những quy ước này giúp API xử lý biên một cách nhất quán.

## 10. Java 17 — verifier CLIQUE

Lưu **CliqueCertificateDemo.java**:

```java
public class CliqueCertificateDemo {
    static void edge(boolean[][] graph, int a, int b) {
        graph[a][b] = true;
        graph[b][a] = true;
    }

    static boolean validGraph(boolean[][] g) {
        if (g == null) return false;
        int n = g.length;
        for (int i = 0; i < n; i++) {
            if (g[i] == null || g[i].length != n) return false;
        }
        for (int i = 0; i < n; i++) {
            if (g[i][i]) return false;
            for (int j = i + 1; j < n; j++) {
                if (g[i][j] != g[j][i]) return false;
            }
        }
        return true;
    }

    static boolean verify(boolean[][] g, int k, int[] vertices) {
        if (!validGraph(g) || k < 0 || k > g.length
                || vertices == null || vertices.length != k) {
            return false;
        }

        boolean[] seen = new boolean[g.length];
        for (int v : vertices) {
            if (v < 0 || v >= g.length || seen[v]) return false;
            seen[v] = true;
        }

        for (int i = 0; i < vertices.length; i++) {
            for (int j = i + 1; j < vertices.length; j++) {
                if (!g[vertices[i]][vertices[j]]) return false;
            }
        }
        return true;
    }

    public static void main(String[] args) {
        boolean[][] g = new boolean[5][5];
        edge(g, 0, 1);
        edge(g, 0, 2);
        edge(g, 1, 2);
        edge(g, 1, 3);
        edge(g, 2, 3);
        edge(g, 3, 4);

        System.out.println("triangle certificate: "
                + verify(g, 3, new int[] {0, 1, 2}));
        System.out.println("missing edge: "
                + verify(g, 3, new int[] {0, 1, 4}));
        System.out.println("duplicate vertex: "
                + verify(g, 3, new int[] {0, 1, 1}));
        System.out.println("wrong certificate size: "
                + verify(g, 3, new int[] {0, 1}));
        System.out.println("empty clique k=0: "
                + verify(g, 0, new int[] {}));
        System.out.println("four-vertex certificate: "
                + verify(g, 4, new int[] {0, 1, 2, 3}));

        boolean[][] asymmetric = new boolean[3][3];
        asymmetric[0][1] = true;
        System.out.println("malformed graph: "
                + verify(asymmetric, 2, new int[] {0, 1}));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 CliqueCertificateDemo.java
java CliqueCertificateDemo
```

Stdout:

```text
triangle certificate: true
missing edge: false
duplicate vertex: false
wrong certificate size: false
empty clique k=0: true
four-vertex certificate: false
malformed graph: false
```

**Điểm dễ nhầm:** `missing edge: false` hoặc `four-vertex certificate: false` chỉ nói danh sách hiện tại không chứng minh YES. Muốn kết luận G không có clique4 phải có thuật toán quyết định/chứng minh bổ sung, không được suy từ việc một danh sách bị từ chối.

## 11. VERTEX COVER và INDEPENDENT SET: hai chứng chỉ đồ thị khác

### 11.1. Independent Set

Một tập độc lập S có **không cặp đỉnh nào** của S nối bằng cạnh.

Bài toán quyết định: Có independent set kích thước **ít nhất k** không?

Chứng chỉ: k ID đỉnh phân biệt và không cạnh nối giữa bất kỳ hai ID ấy. Verifier tương tự CLIQUE nhưng điều kiện cạnh đảo lại.

### 11.2. Vertex Cover

Một tập C⊆V là **vertex cover** nếu mỗi cạnh có **ít nhất một đầu mút** thuộc C.

Bài toán quyết định: Có vertex cover kích thước **không quá k** không?

Chứng chỉ: danh sách đỉnh C, có thể ngắn hơn k, và kiểm **mọi cạnh** đều được phủ. Nếu dữ liệu dùng danh sách cạnh có m cạnh, kiểm O(n+m+|C|) thao tác trên chỉ số trong cách cài đặt phù hợp. Kích thước chứng chỉ tối đa n ID.

### 11.3. Quan hệ phần bù cực kỳ hữu ích

Với cùng đồ thị G:

`C là vertex cover ⇔ V\C là independent set`.

Chứng minh:

- Nếu phần bù V\C chứa một cạnh có cả hai đầu mút nằm ngoài C, cạnh đó **không được phủ**, mâu thuẫn.
- Nếu V\C độc lập, không cạnh nào có hai đầu ở ngoài C, nên **mọi cạnh** có ít nhất một đầu trong C.

Do đó:

`G có independent set kích thước ≥k ⇔ G có vertex cover kích thước ≤n−k`.

Với đồ thị bù \u0305G (các cạnh giữa hai đỉnh khác nhau là những cặp **không có cạnh** trong G):

`G có clique kích thước ≥k ⇔ \u0305G có independent set kích thước ≥k`.

Kết hợp:

`G có clique ≥k ⇔ \u0305G có vertex cover ≤n−k`.

Đây là cơ sở của một **phép giảm đa thức**, không phải chỉ là sự giống nhau ngẫu nhiên của code verifier.

## 12. SUBSET SUM: kiểm tập chỉ số và tránh overflow

Input:

- Dãy số nguyên `a0,a1,...,a(n−1)`.
- Mục tiêu T.

Hỏi có tập chỉ số S⊆{0,...,n−1} sao cho:

`Σ(i∈S) a_i = T`

không?

### 12.1. Vì sao chứng chỉ là vị trí, không chỉ giá trị?

Nếu dãy có hai phần tử **bằng giá trị** ở hai vị trí khác nhau, ta vẫn có quyền chọn chúng riêng biệt. Đưa **chỉ số** giúp định nghĩa rõ mỗi phần tử được dùng tối đa một lần trong phiên bản SUBSET SUM 0/1.

Chứng chỉ là danh sách chỉ số phân biệt. Verifier:

1. Xác nhận mọi chỉ số thuộc `[0,n)`.
2. Không có chỉ số trùng.
3. Cộng đúng các giá trị tương ứng.
4. So tổng với T.

### 12.2. Dùng BigInteger khi cần chính xác

Trong Java, tổng các `long` có thể **tràn long** dù mỗi số hợp lệ. Nếu đã tràn rồi mới gọi `BigInteger.valueOf(sum)`, không thể khôi phục kết quả.

Cách đúng là chuyển từng phần tử sang BigInteger **trước phép cộng**:

`sum=sum.add(BigInteger.valueOf(a[index]))`.

Ví dụ:

`Long.MAX_VALUE+Long.MAX_VALUE=18446744073709551614`

trong số học nguyên chính xác, vượt giới hạn long.

### 12.3. Độ phức tạp

Chứng chỉ tối đa n chỉ số, mỗi chỉ số có O(log n) bit. Với các số có độ dài tối đa B bit và tổng s phần tử, cộng bằng BigInteger đòi O(s·(B+log n)) bit operations theo mô hình cộng tuyến tính thông thường, cộng chi phí kiểm chỉ số O(n+s). Toàn bộ vẫn **đa thức theo độ dài input**.

Không được nói “cộng n số là O(n) thời gian bit” nếu các số có độ dài tùy ý. Trong mô hình word-RAM với long cố định, thời gian mỗi phép cộng là O(1) nhưng rủi ro overflow phải được quản lý.

### 12.4. Pseudo-polynomial khác polynomial

Với SUBSET SUM có số không âm và T≥0, một giải thuật quy hoạch động thường có thời gian O(nT). Điều đó gọi **giả đa thức** (*pseudo-polynomial*): T có thể lớn theo hàm mũ của số bit `log T` trong input.

Việc tồn tại DP này không mâu thuẫn với SUBSET SUM mã hóa nhị phân là NP-complete. Phiên bản có số âm cần sửa mô hình DP/phạm vi giá trị; demo verifier chấp nhận cả số âm để nhấn mạnh việc kiểm tổng vẫn dễ.

## 13. Java 17 — SUBSET SUM verifier bằng BigInteger

Lưu **SubsetSumCertificateDemo.java**:

```java
import java.math.BigInteger;

public class SubsetSumCertificateDemo {
    static boolean verify(long[] values, BigInteger target,
                          int[] selectedIndices) {
        if (values == null || target == null
                || selectedIndices == null) {
            return false;
        }

        boolean[] seen = new boolean[values.length];
        BigInteger sum = BigInteger.ZERO;
        for (int index : selectedIndices) {
            if (index < 0 || index >= values.length || seen[index]) {
                return false;
            }
            seen[index] = true;
            sum = sum.add(BigInteger.valueOf(values[index]));
        }
        return sum.equals(target);
    }

    public static void main(String[] args) {
        long[] values = {6, 10, 15, 21};
        BigInteger target = BigInteger.valueOf(31);

        System.out.println("valid subset: "
                + verify(values, target, new int[] {1, 3}));
        System.out.println("wrong sum: "
                + verify(values, target, new int[] {0, 2}));
        System.out.println("duplicate index: "
                + verify(values, target, new int[] {1, 1}));
        System.out.println("index out of range: "
                + verify(values, target, new int[] {8}));
        System.out.println("empty subset target zero: "
                + verify(values, BigInteger.ZERO, new int[] {}));

        long[] large = {Long.MAX_VALUE, Long.MAX_VALUE};
        BigInteger exact = BigInteger.valueOf(Long.MAX_VALUE)
                .multiply(BigInteger.TWO);
        System.out.println("beyond long sum: " + exact);
        System.out.println("beyond long verified: "
                + verify(large, exact, new int[] {0, 1}));

        long[] signed = {-3, 5, 8};
        System.out.println("signed subset: "
                + verify(signed, BigInteger.valueOf(2),
                         new int[] {0, 1}));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 SubsetSumCertificateDemo.java
java SubsetSumCertificateDemo
```

Stdout:

```text
valid subset: true
wrong sum: false
duplicate index: false
index out of range: false
empty subset target zero: true
beyond long sum: 18446744073709551614
beyond long verified: true
signed subset: true
```

**Quan trọng:** Chứng chỉ sai `wrong sum` không phủ định việc tồn tại tập `{10,21}` đạt31. Verifier chỉ kiểm **chứng chỉ đã được cung cấp**, không tự tìm tập mới.

## 14. HAMILTONIAN CYCLE: chứng chỉ là một hoán vị đỉnh

Một **chu trình Hamilton** đi qua **mỗi đỉnh đúng một lần** và quay lại đỉnh đầu bằng một cạnh. Với đồ thị vô hướng đơn và quy ước chu trình có ít nhất **3 đỉnh**, instance YES nếu có một chu trình như vậy.

### 14.1. Chứng chỉ

Mảng `order` gồm n ID đỉnh, mô tả:

`order[0] → order[1] → ... → order[n−1] → order[0]`.

Verifier kiểm:

1. Đúng **n** ID.
2. Tất cả trong `[0,n)` và **không trùng**.
3. Mỗi cạnh liên tiếp tồn tại.
4. Cạnh **cuối về đầu** tồn tại.
5. Đồ thị đáp ứng quy ước simple, undirected.
6. `n≥3`.

Nếu bỏ bước4, code chỉ đang kiểm **đường đi Hamilton**, không phải **chu trình Hamilton**.

### 14.2. Phân biệt Hamilton và Euler

- **Hamilton:** đi qua mỗi **đỉnh** đúng một lần trong chu trình.
- **Euler:** đi qua mỗi **cạnh** đúng một lần trong một đường đi/chu trình.

Kiểm một tour Hamilton rất đơn giản khi thứ tự đỉnh đã được cho, nhưng việc tìm nó trong đồ thị tổng quát là một bài NP-complete ở dạng quyết định. Trái lại, có thuật toán đa thức quyết định tồn tại chu trình Euler trong đồ thị vô hướng bằng bậc đỉnh và liên thông thích hợp.

### 14.3. Chi phí kiểm

Với adjacency matrix, kiểm tính hợp lệ đồ thị O(n²), chứng chỉ O(n), kiểm mỗi cạnh O(n). Tổng O(n²) thao tác trên ma trận; độ dài chứng chỉ O(n log n) bit.

## 15. Java 17 — verifier HAMILTONIAN CYCLE

Lưu **HamiltonianCycleCertificateDemo.java**:

```java
public class HamiltonianCycleCertificateDemo {
    static void edge(boolean[][] g, int a, int b) {
        g[a][b] = true;
        g[b][a] = true;
    }

    static boolean validGraph(boolean[][] g) {
        if (g == null) return false;
        int n = g.length;
        for (int i = 0; i < n; i++) {
            if (g[i] == null || g[i].length != n) return false;
        }
        for (int i = 0; i < n; i++) {
            if (g[i][i]) return false;
            for (int j = i + 1; j < n; j++) {
                if (g[i][j] != g[j][i]) return false;
            }
        }
        return true;
    }

    static boolean verify(boolean[][] g, int[] order) {
        if (!validGraph(g) || g.length < 3 || order == null
                || order.length != g.length) {
            return false;
        }
        int n = g.length;
        boolean[] seen = new boolean[n];
        for (int v : order) {
            if (v < 0 || v >= n || seen[v]) return false;
            seen[v] = true;
        }

        for (int i = 0; i < n; i++) {
            int a = order[i];
            int b = order[(i + 1) % n];
            if (!g[a][b]) return false;
        }
        return true;
    }

    public static void main(String[] args) {
        boolean[][] square = new boolean[4][4];
        edge(square, 0, 1);
        edge(square, 1, 2);
        edge(square, 2, 3);
        edge(square, 3, 0);

        System.out.println("square cycle: "
                + verify(square, new int[] {0, 1, 2, 3}));
        System.out.println("missing consecutive edge: "
                + verify(square, new int[] {0, 2, 1, 3}));
        System.out.println("repeated vertex: "
                + verify(square, new int[] {0, 1, 1, 3}));

        boolean[][] path = new boolean[4][4];
        edge(path, 0, 1);
        edge(path, 1, 2);
        edge(path, 2, 3);
        System.out.println("path without closing edge: "
                + verify(path, new int[] {0, 1, 2, 3}));

        System.out.println("short certificate: "
                + verify(square, new int[] {0, 1, 2}));

        boolean[][] two = new boolean[2][2];
        edge(two, 0, 1);
        System.out.println("two-vertex convention: "
                + verify(two, new int[] {0, 1}));

        boolean[][] asymmetric = new boolean[3][3];
        asymmetric[0][1] = true;
        System.out.println("malformed graph: "
                + verify(asymmetric, new int[] {0, 1, 2}));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 HamiltonianCycleCertificateDemo.java
java HamiltonianCycleCertificateDemo
```

Stdout:

```text
square cycle: true
missing consecutive edge: false
repeated vertex: false
path without closing edge: false
short certificate: false
two-vertex convention: false
malformed graph: false
```

Dòng `two-vertex convention` minh họa quy ước **đồ thị vô hướng đơn**: một cặp đỉnh không tạo chu trình đơn dài2. Với multigraph hoặc đồ thị có hướng, cần công bố định nghĩa khác nếu muốn nhận chu trình dài2.

## 16. GRAPH COLORING: chứng chỉ là màu cho từng đỉnh

Bài toán k-COLORING quyết định:

> Có thể gán cho mỗi đỉnh một trong k màu sao cho hai đầu mỗi cạnh có màu khác nhau không?

Một chứng chỉ là mảng `colors[v]` gồm n nhãn màu thuộc `[0,k)`.

Verifier:

1. Kiểm đồ thị hợp lệ theo quy ước simple, undirected.
2. Kiểm đúng n nhãn màu.
3. Kiểm `0≤colors[v]<k`.
4. Với mọi cạnh `(u,v)`, kiểm `colors[u] != colors[v]`.

### 16.1. Không dùng màu thừa cũng hợp lệ

“Dùng không quá k màu” cho phép một chứng chỉ chỉ sử dụng 2 màu dù k=3; không bắt buộc xuất hiện đủ cả k nhãn.

### 16.2. Một đồ thị có thể 3-colorable nhưng không 2-colorable

Tam giác gồm ba cạnh giữa ba đỉnh. Phải dùng ba màu khác nhau, nên có chứng chỉ 3 màu; không có phép tô chỉ2 màu.

Nhưng nếu một **chứng chỉ 2 màu cụ thể** bị từ chối, điều đó tự nó **chưa chứng minh** tam giác không thể tô bằng2 màu. Sự bất khả thi ở đây được suy ra từ lập luận về **chu trình lẻ**; tổng quát, 2-COLORING có thuật toán BFS/DFS kiểm bipartite chạy đa thức.

### 16.3. Độ phức tạp

Với ma trận kề n×n, kiểm format và mọi cạnh O(n²); độ dài chứng chỉ khoảng O(n log(k+1)) bit theo mã hóa nhãn cố định. Dùng k là số nguyên nhị phân vẫn đa thức theo input nếu verifier kiểm dữ liệu đúng.

### 16.4. Trường hợp rỗng

Trong demo, đồ thị không có đỉnh với k=0 được nhận là tô màu hợp lệ một cách rỗng. Với n>0 và k=0, không có nhãn màu hợp lệ nên trả false. Một bài toán chính thức khác có thể quy định chỉ k≥1; hãy nêu domain trong đề.

## 17. Java 17 — verifier GRAPH COLORING

Lưu **GraphColoringCertificateDemo.java**:

```java
public class GraphColoringCertificateDemo {
    static void edge(boolean[][] g, int a, int b) {
        g[a][b] = true;
        g[b][a] = true;
    }

    static boolean validGraph(boolean[][] g) {
        if (g == null) return false;
        int n = g.length;
        for (int i = 0; i < n; i++) {
            if (g[i] == null || g[i].length != n) return false;
        }
        for (int i = 0; i < n; i++) {
            if (g[i][i]) return false;
            for (int j = i + 1; j < n; j++) {
                if (g[i][j] != g[j][i]) return false;
            }
        }
        return true;
    }

    static boolean verify(boolean[][] g, int k, int[] colors) {
        if (!validGraph(g) || k < 0 || colors == null
                || colors.length != g.length) {
            return false;
        }
        for (int color : colors) {
            if (color < 0 || color >= k) return false;
        }
        for (int u = 0; u < g.length; u++) {
            for (int v = u + 1; v < g.length; v++) {
                if (g[u][v] && colors[u] == colors[v]) return false;
            }
        }
        return true;
    }

    public static void main(String[] args) {
        boolean[][] triangle = new boolean[3][3];
        edge(triangle, 0, 1);
        edge(triangle, 1, 2);
        edge(triangle, 0, 2);

        System.out.println("triangle valid 3-coloring: "
                + verify(triangle, 3, new int[] {0, 1, 2}));
        System.out.println("triangle invalid 2-coloring: "
                + verify(triangle, 2, new int[] {0, 1, 0}));
        System.out.println("invalid color index: "
                + verify(triangle, 2, new int[] {0, 1, 2}));

        boolean[][] path = new boolean[4][4];
        edge(path, 0, 1);
        edge(path, 1, 2);
        edge(path, 2, 3);
        System.out.println("path valid 2-coloring: "
                + verify(path, 2, new int[] {0, 1, 0, 1}));

        System.out.println("empty graph k=0: "
                + verify(new boolean[0][0], 0, new int[] {}));
        System.out.println("triangle one-coloring: "
                + verify(triangle, 1, new int[] {0, 0, 0}));

        boolean[][] loop = new boolean[2][2];
        loop[0][0] = true;
        System.out.println("malformed loop graph: "
                + verify(loop, 2, new int[] {0, 1}));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 GraphColoringCertificateDemo.java
java GraphColoringCertificateDemo
```

Stdout:

```text
triangle valid 3-coloring: true
triangle invalid 2-coloring: false
invalid color index: false
path valid 2-coloring: true
empty graph k=0: true
triangle one-coloring: false
malformed loop graph: false
```

## 18. TSP quyết định và các chứng chỉ hữu ích khác

**Travelling Salesperson Problem** ở dạng quyết định:

- Input: n thành phố, ma trận chi phí/tập cạnh, ngân sách B.
- Hỏi: Có tour qua mỗi thành phố một lần, quay về điểm xuất phát, có **tổng chi phí ≤B** không?

Chứng chỉ YES là một **hoán vị n thành phố**. Verifier kiểm:

1. Mỗi ID hợp lệ, không trùng.
2. Mọi chặng giữa hai đỉnh liên tiếp và chặng cuối→đầu hợp lệ.
3. Cộng chi phí **kể cả chặng đóng tour**.
4. Tổng ≤B.

Với chi phí nguyên có độ dài bit hữu hạn, tổng bằng số học chính xác như BigInteger để không bị tràn; kiểm chi phí trong thời gian đa thức theo độ dài input.

Ví dụ một tour có chi phí11 và B=12 là chứng chỉ YES. Với B=10, **chính tour ấy** thất bại nhưng chưa chứng minh không có tour khác giá≤10.

### 18.1. Giá trị tối ưu khác witness YES

Để chứng minh một tour là **tối ưu**, không đủ chỉ kiểm nó là một tour hợp lệ. Muốn kết luận không tồn tại tour tốt hơn, phải có lập luận/chứng cứ cho mệnh đề kiểu NO ở ngưỡng thấp hơn, hoặc một **lower bound** khớp với chi phí tour.

Tương tự, một clique k đỉnh chỉ chứng minh tồn tại clique≥k, **không chứng minh k là kích thước lớn nhất**.

### 18.2. Các bài khác

- **PATH ≤k:** Đường đi s→t có không quá k cạnh; chứng chỉ là danh sách đỉnh; kiểm cạnh nối và hai đầu. Nhiều biến thể đường đi ngắn nhất giải được đa thức và **không** NP-complete chỉ vì có witness.
- **PARTITION:** Chứng chỉ chia tập thành hai phần có tổng bằng nhau, nếu phiên bản input quy định như vậy.
- **MAX-CUT decision:** Chứng chỉ mỗi đỉnh thuộc một trong hai phía; cộng trọng số cạnh cắt và so với ngưỡng.
- **VERTEX COVER:** Danh sách đỉnh; quét mọi cạnh kiểm có đầu thuộc tập.
- **INDEPENDENT SET:** Danh sách đỉnh phân biệt không có cặp kề nhau.

Điểm chung là **kiểm một cấu trúc được cung cấp** khác với **tự sinh cấu trúc ấy**.

## 19. Chứng minh verifier đúng: đừng chỉ đưa code

Một chứng minh thuộc NP thường có ba phần:

1. **Định nghĩa chứng chỉ:** ví dụ SAT có assignment n biến; CLIQUE có k ID; HAMILTON có hoán vị n ID.
2. **Phân tích kích thước:** assignment O(n), danh sách ID O(k log n), hoán vị O(n log n); số bit đều đa thức theo instance.
3. **Thuật toán kiểm và soundness/completeness:** kiểm toàn bộ điều kiện định nghĩa trong thời gian đa thức.

### 19.1. CNF-SAT

Nếu verifier nhận, mọi clause có literal đúng ⇒ toàn CNF đúng ⇒ YES. Nếu CNF thỏa được, đưa assignment thỏa làm w ⇒ verifier nhận.

### 19.2. CLIQUE

Nếu verifier nhận, k ID phân biệt và mọi cặp có cạnh ⇒ S là clique k. Nếu clique≥k tồn tại, lấy k đỉnh của nó ⇒ verifier nhận.

### 19.3. SUBSET SUM

Nếu verifier nhận, các chỉ số hợp lệ/phân biệt và tổng chính xác T ⇒ một tập con đạt T. Nếu có tập con đạt T, liệt kê các chỉ số được chọn ⇒ verifier nhận.

### 19.4. HAMILTONIAN CYCLE

Nếu verifier nhận, hoán vị liệt kê mọi đỉnh đúng một lần và mọi cạnh kể cả chặng đóng tồn tại ⇒ một chu trình Hamilton. Nếu có chu trình, ghi các đỉnh theo thứ tự đi ⇒ verifier nhận.

### 19.5. k-COLORING

Nếu verifier nhận, mỗi nhãn thuộc `[0,k)`, mọi cạnh nối hai màu khác nhau ⇒ tô màu hợp lệ. Nếu tồn tại phép tô như thế, cung cấp nhãn màu của từng đỉnh ⇒ verifier nhận.

**Kết luận đúng:** cả năm bài quyết định có verifier chứng chỉ đa thức nên thuộc **NP**. Kết luận ấy **không tự chứng minh** một bài là NP-hard; cần bước phép giảm.

## 20. Phép giảm đa thức: chứng minh bài toán khó

Một **phép giảm Karp đa thức** từ A tới B, viết:

`A ≤p B`,

là phép biến đổi tính được trong thời gian đa thức `f` từ instance x của A sang instance f(x) của B sao cho:

`x là YES của A ⇔ f(x) là YES của B`.

Nếu đã có solver đa thức cho B, ta có solver đa thức cho A: tính f(x), chạy solver B.

### 20.1. Chiều giảm rất quan trọng

Để chứng minh **B NP-hard**, chọn một bài **A đã biết NP-hard/NP-complete**, xây dựng:

`A ≤p B`.

Nếu chỉ xây được `B ≤p A`, ta **không** chứng minh B khó bằng A. Đây là lỗi suy luận phổ biến.

### 20.2. Muốn chứng minh B NP-complete

Hai nghĩa vụ độc lập:

1. **B ∈ NP:** đưa chứng chỉ, verifier, bound độ dài/thời gian.
2. **B NP-hard:** đưa phép giảm đa thức từ một bài đã biết NP-hard và chứng minh **hai chiều YES tương đương**.

Không bỏ qua chứng minh độ dài output của phép giảm là đa thức theo input.

## 21. Ví dụ giảm CNF-SAT → CLIQUE

Giả sử CNF có m clause `C1, C2, ..., Cm`, mỗi clause là một OR của các literal.

Xây dựng đồ thị H:

1. Tạo **một đỉnh cho mỗi lần xuất hiện literal** trong một clause. Một biến xuất hiện nhiều lần tạo **các đỉnh khác nhau theo occurrence**.
2. **Không nối** hai đỉnh cùng clause.
3. Với hai đỉnh ở **hai clause khác nhau**, nối cạnh nếu hai literal **không đối nghịch nhau** (không phải x_i và ¬x_i của cùng một biến).
4. Đặt tham số CLIQUE `k=m`.

Phép tạo có số đỉnh bằng tổng số occurrences L, số cạnh tối đa O(L²). Có thể xây trong thời gian đa thức theo kích thước CNF.

### 21.1. Nếu CNF thỏa được ⇒ H có clique m

Cho một assignment thỏa mãn công thức. Trong mỗi clause chọn **một literal đang true**. Vì cùng một assignment, không thể có cả x_i và ¬x_i đều true, nên các literal được chọn ở những clause khác nhau **không đối nghịch**.

Đồ thị có cạnh giữa mọi cặp đỉnh được chọn; lấy đúng một từ mỗi clause tạo **clique m**.

### 21.2. Nếu H có clique m ⇒ CNF thỏa được

Do không có cạnh giữa hai đỉnh cùng clause, clique m bắt buộc chọn **đúng một đỉnh ở mỗi trong m clause**.

Các literal được chọn đôi một không đối nghịch, nên có thể gán biến để **tất cả literal đã chọn đều true**. Các biến chưa bị ràng buộc gán tùy ý. Mỗi clause có một literal đúng ⇒ cả CNF đúng.

### 21.3. Trường hợp biên

- Nếu một clause rỗng, nó không tạo đỉnh, nên không thể có clique m khi m>0; CNF cũng UNSAT.
- Nếu công thức không có clause (m=0), CNF true; một tập đỉnh rỗng là clique kích thước0, phù hợp quy ước.
- Hai occurrences cùng biến **cùng dấu** ở các clause khác nhau không mâu thuẫn và có thể nối cạnh.
- Hai literal x_i và ¬x_i ở hai clause khác nhau **không nối**, vì không thể cùng true dưới một assignment.

Từ SAT thuộc NP-complete và phép giảm trên, CLIQUE là NP-hard. Kết hợp với verifier CLIQUE ở phần9 ⇒ **CLIQUE NP-complete**.

### 21.4. Giảm CLIQUE → VERTEX COVER

Dùng đồ thị bù \u0305G với cùng tập đỉnh:

`G có clique ≥k`
`⇔ \u0305G có independent set ≥k`
`⇔ \u0305G có vertex cover ≤n−k`.

Biến đổi đồ thị bù và đổi ngưỡng n−k thực hiện trong thời gian đa thức. Đây là cách suy ra VERTEX COVER NP-hard từ CLIQUE; để gọi NP-complete phải thêm verifier vertex cover đa thức.

## 22. Sai lầm trong chứng minh NP membership

### Lỗi 1 — Bỏ qua định nghĩa của một instance hợp lệ

Đồ thị có hướng hay vô hướng? Có cạnh tự nối không? Nghiệm HAMILTON yêu cầu chu trình dài ít nhất3 không? Một verifier và một định nghĩa khác nhau sẽ kiểm sai bài.

### Lỗi 2 — Nhầm “tìm nhanh” với “kiểm nhanh”

Verifier SAT chỉ kiểm assignment; nó không chứng minh có thuật toán tìm assignment đa thức.

### Lỗi 3 — Coi một chứng chỉ false là chứng minh NO

Một clique candidate thiếu cạnh không loại trừ clique khác.

### Lỗi 4 — Bỏ sót chứng minh kích thước witness

Một chứng chỉ dài theo giá trị số T, dù kiểm từng phần dễ, có thể **không** dài đa thức theo số bit input.

### Lỗi 5 — Dùng tìm kiếm mũ bên trong verifier

Nếu verifier chạy brute force mọi assignment khi w sai, đó không còn là kiểm một chứng chỉ đa thức.

### Lỗi 6 — Gọi mọi bài trong NP là NP-complete

Membership chỉ là nửa yêu cầu; phải chứng minh NP-hard.

### Lỗi 7 — Giảm sai hướng

Muốn B khó, cần A đã biết khó **giảm tới B**, không chỉ B giảm tới A.

### Lỗi 8 — Chỉ chứng minh một chiều của phép giảm

Cần `YES(A) ⇔ YES(B)` để quyết định được bảo toàn; chỉ `⇒` có thể tạo false positive.

### Lỗi 9 — Không xét thời gian biến đổi

Một phép tạo đồ thị có số đỉnh theo hàm mũ của input không phải reduction đa thức.

### Lỗi 10 — Nhầm NP với “non-polynomial”

NP là nondeterministic polynomial time; P⊆NP.

### Lỗi 11 — Khẳng định P≠NP như đã chứng minh

Câu hỏi này chưa được giải quyết bằng chứng minh được công nhận.

### Lỗi 12 — Nói mọi NO đều không có chứng chỉ ngắn

Định nghĩa NP **không yêu cầu** chứng chỉ NO, nhưng một số bài toán/instance vẫn có thể có chứng cứ NO dễ kiểm; phải phân biệt NP với coNP.

### Lỗi 13 — Gọi tối ưu trực tiếp là NP-complete

NP-complete gắn với **ngôn ngữ quyết định**; dạng tối ưu thường gọi NP-hard.

### Lỗi 14 — Không phân biệt 2-COLORING và 3-COLORING

2-COLORING giải được đa thức, 3-COLORING tổng quát NP-complete.

### Lỗi 15 — Quên k=0 trong CLIQUE

Tập rỗng là clique0; nếu input hợp lệ, đây là YES.

### Lỗi 16 — Cho phép ID đỉnh trùng

Danh sách [0,1,1] không là tập ba đỉnh.

### Lỗi 17 — Không kiểm mọi cặp CLIQUE

Chỉ kiểm các đỉnh nối theo một đường đi không đủ; clique cần **mọi cặp**.

### Lỗi 18 — Không kiểm cạnh cuối→đầu trong HAMILTONIAN CYCLE

Khi đó chỉ là Hamiltonian path.

### Lỗi 19 — Nhầm HAMILTON và EULER

Một bài kiểm đỉnh, một bài kiểm cạnh; độ khó quyết định khác nhau.

### Lỗi 20 — Kiểm tô màu nhưng bỏ sót range màu

Một nhãn `-1` hoặc `k` không thuộc bảng màu `[0,k)`.

### Lỗi 21 — Từ chối tô màu vì không dùng đủ k màu

k-COLORING là “**không quá** k màu”; dùng ít màu hơn vẫn hợp lệ.

### Lỗi 22 — SUBSET SUM dùng lại một index

Dãy 0/1 cho phép chọn mỗi **vị trí** tối đa một lần.

### Lỗi 23 — Tràn long khi cộng tổng

Cần BigInteger nếu tổng có thể vượt long; chuyển từng phần tử trước phép cộng.

### Lỗi 24 — Coi O(nT) là luôn polynomial

T mã hóa nhị phân có số bit O(log T); O(nT) có thể mũ theo kích thước input.

### Lỗi 25 — Bỏ qua malformed literal

Lấy `Math.abs(Integer.MIN_VALUE)` dưới dạng int có thể vẫn âm; cần long trước khi abs và kiểm phạm vi.

### Lỗi 26 — Kiểm SAT dừng sớm trước validate toàn formula

Có thể bỏ lọt literal malformed trong clause sau. Nên validate instance trước khi chấp nhận certificate.

### Lỗi 27 — Nhầm AND rỗng với OR rỗng

CNF không clause là true; một clause rỗng là false.

### Lỗi 28 — TSP quên chặng cuối về đầu

Tổng tour không hợp lệ nếu bỏ chi phí đóng chu trình.

### Lỗi 29 — TSP cộng cost kiểu int/long rồi overflow

Kiểm tổng số lớn bằng số học chính xác theo số bit input.

### Lỗi 30 — Chứng chỉ tối ưu chỉ cần một lời giải khả thi

Một tour khả thi không chứng minh là tour ngắn nhất.

### Lỗi 31 — Không kiểm đồ thị vô hướng đối xứng

Ma trận chỉ có g[u][v] mà thiếu g[v][u] là một instance khác theo định nghĩa.

### Lỗi 32 — Mặc nhiên coi Java int là số nguyên toán học vô hạn

Phân tích bit complexity và kiểm overflow khi nhận dữ liệu ngoài.

### Lỗi 33 — Nhầm 0-based và 1-based

SAT signed literal thường dùng 1-based, graph vertices thường 0-based. Phải công bố quy ước.

### Lỗi 34 — “Không tìm được” ⇒ “không tồn tại”

Hết thời gian, thử vài witness hoặc một heuristic thất bại **không** chứng minh NO.

### Lỗi 35 — Chỉ kiểm ví dụ thành công

Cần test chứng chỉ giả, trùng, ngoài range, thiếu cạnh, tổng sai, input rỗng và instance malformed.

### Lỗi 36 — Bỏ qua soundness/completeness

Verifier chỉ true-when-correct chưa đủ nếu luôn từ chối tất cả YES.

## 23. Bảng tổng hợp chứng chỉ và thời gian kiểm

| Bài toán YES | Chứng chỉ | Kiểm chính | Thời gian demo |
|---|---|---|---|
| CNF-SAT | n giá trị Boolean | Mỗi clause có literal true | O(n+L) truy cập |
| CLIQUE ≥k | k ID đỉnh phân biệt | Mọi cặp kề nhau | O(n²+k²) |
| SUBSET SUM=T | Vị trí các phần tử | Không trùng, tổng đúng bằng T | Đa thức theo tổng bit input |
| HAMILTONIAN CYCLE | Hoán vị n đỉnh | Mọi cạnh và chặng cuối→đầu | O(n²) |
| k-COLORING | n màu | Range màu, hai đầu cạnh khác màu | O(n²) |
| TSP tour≤B | Hoán vị thành phố | Tổng tour và chặng đóng ≤B | Đa thức theo input bits |
| VERTEX COVER≤k | Tập đỉnh | Mọi cạnh có đầu được chọn | O(n+m) với danh sách cạnh |
| INDEPENDENT SET≥k | Tập đỉnh | Không có cạnh trong tập | O(n²) nếu matrix |

**Điều kiện chung:** Các chi phí trong bảng giả định input đã được mã hóa/tổ chức phù hợp và **không dùng brute-force tìm chứng chỉ**. Với ma trận kề, O(n²) bao gồm validate đồ thị. Với các số lớn, bit operations khác word operations.

## 24. Bài tập có đáp án

### Bài 1 — Quyết định và tìm kiếm

“Đồ thị có clique size≥4 không?” khác gì “Hãy liệt kê clique4”?

**Đáp án:** câu đầu trả YES/NO; câu sau phải xuất một tập đỉnh (hoặc cho biết không tồn tại).

### Bài 2 — Tối ưu

“Clique lớn nhất có bao nhiêu đỉnh?” có phải trực tiếp là một bài toán YES/NO không?

**Đáp án:** không; nó yêu cầu giá trị tối ưu.

### Bài 3 — Định nghĩa NP

Cần những gì cho chứng chỉ YES?

**Đáp án:** chứng chỉ độ dài đa thức theo input bits và verifier xác định chạy đa thức, thỏa soundness/completeness.

### Bài 4 — Từ chối chứng chỉ

`verify(F,w)=false` có chứng minh F là UNSAT không?

**Đáp án:** không; có thể tồn tại w khác.

### Bài 5 — Chứng chỉ SAT

Với F=(x1∨x2)∧(¬x1∨x2), assignment x1=false,x2=true có hợp lệ không?

**Đáp án:** có; mỗi clause có x2=true.

### Bài 6 — Một clause rỗng

CNF chứa clause `()` có thỏa được không?

**Đáp án:** không; OR rỗng là false.

### Bài 7 — Không có clause

CNF với không clause có thỏa được không?

**Đáp án:** có, bằng mọi assignment hợp lệ; AND rỗng là true.

### Bài 8 — Clique đơn giản

G có tam giác 0,1,2; w=[0,1,2] với k3?

**Đáp án:** hợp lệ.

### Bài 9 — Clique giả

w=[0,1,1] với k3 có phải clique size3 không?

**Đáp án:** không; chỉ hai đỉnh phân biệt.

### Bài 10 — Clique k0

Một đồ thị hợp lệ có clique size0 không?

**Đáp án:** có, tập rỗng.

### Bài 11 — Independent set và cover

C là vertex cover khi và chỉ khi tập nào độc lập?

**Đáp án:** V\C.

### Bài 12 — Complement graph

G có clique size≥k tương đương đồ thị bù có gì?

**Đáp án:** independent set size≥k, hoặc vertex cover size≤n−k.

### Bài 13 — Subset sum

Dãy [6,10,15,21], T=31, chứng chỉ vị trí nào?

**Đáp án:** [1,3] (0-based), vì 10+21=31.

### Bài 14 — Index duplicate

Chứng chỉ [1,1] cho dãy trên có hợp lệ không?

**Đáp án:** không, chọn cùng vị trí hai lần.

### Bài 15 — Overflow

Hai số Long.MAX_VALUE có tổng toán học bao nhiêu?

**Đáp án:** 18446744073709551614; vượt long.

### Bài 16 — Pseudo-polynomial

Vì sao O(nT) chưa chắc đa thức theo kích thước input?

**Đáp án:** T mã hóa nhị phân chỉ cần Θ(log T) bit.

### Bài 17 — Hamilton cycle

Order [0,1,2,3] có đủ chưa nếu đồ thị chỉ có cạnh 0-1,1-2,2-3?

**Đáp án:** không; thiếu cạnh3-0.

### Bài 18 — Hamilton vs Euler

Hamilton ràng buộc đỉnh hay cạnh?

**Đáp án:** mỗi đỉnh đúng một lần; Euler ràng buộc mỗi cạnh đúng một lần.

### Bài 19 — Graph coloring

Tam giác có tô bằng2 màu được không?

**Đáp án:** không; chu trình lẻ, ba đỉnh đôi một kề nhau cần ba màu khác nhau.

### Bài 20 — Màu thừa

Input k=4, chứng chỉ chỉ dùng màu0,1,2 có hợp lệ không nếu mọi cạnh khác màu?

**Đáp án:** có; “không quá k màu”.

### Bài 21 — TSP tour

Verifier cần kiểm cạnh cuối về đầu không?

**Đáp án:** có, nếu đó là tour đóng.

### Bài 22 — TSP tối ưu

Một tour chi phí10 với budget12 chứng minh tối ưu10 không?

**Đáp án:** không; chỉ chứng minh có tour≤12.

### Bài 23 — NP-complete

Một bài có verifier đa thức, vậy nó NP-complete chưa?

**Đáp án:** chưa; mới chứng minh thuộc NP, cần NP-hard.

### Bài 24 — Reduction direction

Để chứng minh B NP-hard từ A đã NP-complete, giảm theo chiều nào?

**Đáp án:** A≤pB.

### Bài 25 — Độ dài chứng chỉ Hamilton

N đỉnh, liệt kê các ID có độ dài bit khoảng bao nhiêu?

**Đáp án:** O(n log n), dưới mã hóa ID nhị phân phù hợp.

### Bài 26 — SAT→CLIQUE

CNF có m clause, graph reduction cần clique size bao nhiêu?

**Đáp án:** m.

### Bài 27 — SAT→CLIQUE soundness

Vì sao clique m không chứa hai literal đối nghịch?

**Đáp án:** construction không nối cạnh giữa những occurrences đối nghịch.

### Bài 28 — SAT→CLIQUE completeness

Vì sao assignment thỏa CNF tạo được clique m?

**Đáp án:** chọn một literal đúng mỗi clause; các literal đều cùng true nên không đối nghịch.

### Bài 29 — P nằm trong NP

Tại sao P⊆NP?

**Đáp án:** verifier có thể bỏ qua certificate và chạy thuật toán quyết định đa thức.

### Bài 30 — coNP

UNSAT nằm trong lớp nào theo định nghĩa phần bù SAT?

**Đáp án:** coNP.

### Bài 31 — Kết luận NO

Một thuật toán thử1000 witness mà không tìm được cái đúng có chứng minh NO?

**Đáp án:** không, trừ khi đã chứng minh phạm vi thử bao phủ toàn bộ và quyết định được instance.

### Bài 32 — Khi nào kiểm một chứng chỉ dễ mà tìm có thể khó?

**Đáp án:** SAT, CLIQUE, SUBSET SUM, HAMILTONIAN CYCLE trong phiên bản tổng quát là ví dụ kinh điển; verifier polynomial không cho biết có cách tìm polynomial.

### Bài 33 — 2-coloring

Có cần xem 2-COLORING tổng quát là NP-complete không?

**Đáp án:** không; kiểm bipartite bằng BFS/DFS đa thức.

### Bài 34 — Validations

Nếu ma trận vô hướng bị bất đối xứng, verifier của demo xử lý thế nào?

**Đáp án:** từ chối instance theo quy ước đồ thị đơn vô hướng.

### Bài 35 — Một witness sai vẫn có YES

SAT demo có `invalid assignment=false` và `valid assignment=true`. Kết luận instance?

**Đáp án:** YES, vì **tồn tại** một assignment hợp lệ; witness sai khác không thay đổi sự tồn tại đó.

## 25. Checklist xây dựng một chứng minh NP membership

1. Đề bài đã được viết thành **câu hỏi quyết định YES/NO**?
2. Có công bố mã hóa input và kích thước bit?
3. Có phân biệt bài toán tìm kiếm và tối ưu?
4. Có quy định chính xác thế nào là instance hợp lệ?
5. Có nêu chứng chỉ YES là cấu trúc gì?
6. Có chặn **độ dài bit chứng chỉ** bằng đa thức theo input?
7. Verifier có nhận **cả x và w**?
8. Verifier có kiểm dữ liệu không hợp lệ trước khi chấp nhận?
9. Có kiểm đủ mọi điều kiện của định nghĩa nghiệm?
10. Có loại ID out-of-range, duplicate, null?
11. Có xét graph directed/undirected, loop, cạnh trùng?
12. Có kiểm ID biến SAT 1-based và vertex 0-based?
13. Có tránh overflow tổng/giá trị ngưỡng?
14. Có kiểm trường hợp đầu vào/chứng chỉ rỗng?
15. Có chứng minh **soundness**?
16. Có chứng minh **completeness**?
17. Có phân tích thời gian kiểm theo input bit length?
18. Verifier có tránh **tự tìm w bằng brute force**?
19. Có phân biệt `verify=false` với “instance NO”?
20. Có tránh nhầm NP với NP-hard/NP-complete?
21. Nếu nói NP-complete, có chứng minh B∈NP?
22. Nếu nói NP-hard, có phép giảm đúng hướng từ A đã khó?
23. Phép giảm có thời gian và kích thước output đa thức?
24. Phép giảm có chứng minh **YES iff YES** cả hai chiều?
25. Có kiểm k=0, k>n và trường hợp graph rỗng?
26. Có kiểm clause rỗng và CNF rỗng?
27. Có kiểm SUBSET SUM index trùng?
28. Có kiểm Hamilton **cạnh cuối→đầu**?
29. Có kiểm màu trong `[0,k)` và trên mọi cạnh?
30. Có kiểm TSP **tổng tour đầy đủ** kể cả cạnh đóng?
31. Có phân biệt O(nT) giả đa thức với đa thức theo input bits?
32. Có hiểu P⊆NP, coNP và P=?NP chưa được giải quyết?
33. Có test witness đúng **và** witness sai trên cùng instance YES?
34. Có test malformed input/certificate mà không crash?
35. Có thể trình bày ít nhất một ví dụ reduction và lý do đúng?
36. Có kiểm bài toán đang thuộc đúng phiên bản chuẩn trước khi viện dẫn NP-complete?

**Tổng kết:** Bài toán quyết định hỏi **có/không**, còn chứng chỉ cung cấp một **ví dụ YES cụ thể**. Bản chất NP là có **chứng chỉ YES dài đa thức** và **verifier xác định chạy đa thức**. Kiểm một lời giải được cho **không đồng nghĩa tự tìm được lời giải**, và việc một witness bị từ chối **không chứng minh NO**. Từ verifier chỉ suy ra **thuộc NP**; muốn kết luận **NP-complete** phải thêm một **phép giảm đa thức đúng chiều với hai phía tương đương**. Dù cài đặt Java dùng mảng/long/BigInteger, phân tích lý thuyết phải bám theo **số bit mã hóa input và certificate**.
