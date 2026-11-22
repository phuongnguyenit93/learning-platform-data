# Phân biệt liệt kê đầy đủ với dừng sau lời giải đầu tiên

## 1. Hai mục tiêu khác nhau của quay lui

**Quay lui (backtracking)** là phương pháp xây dựng lời giải từng bước, kiểm tra ràng buộc, đi sâu vào một nhánh hợp lệ, rồi **hoàn tác lựa chọn** để thử nhánh tiếp theo. Thông thường, ta tổ chức các lựa chọn thành **cây tìm kiếm** và dùng duyệt theo chiều sâu (DFS).

Cùng một cây tìm kiếm, hai yêu cầu đầu ra sau có ý nghĩa rất khác nhau:

1. **Liệt kê đầy đủ (enumerate all):** tìm **mọi lời giải phân biệt** thỏa ràng buộc; chỉ hoàn thành khi đã xét hết các nhánh có thể chứa lời giải hoặc đã được chứng minh không cần xét nhờ cắt tỉa hợp lệ.
2. **Dừng sau lời giải đầu tiên (find first):** tìm **một lời giải bất kỳ** theo thứ tự duyệt đã định, rồi dừng toàn bộ cuộc tìm kiếm ngay khi đã tìm thấy.

Một nhu cầu liên quan là **kiểm tra sự tồn tại (exists)**: chỉ cần biết có ít nhất một lời giải hay không. Nếu không cần nội dung nghiệm, có thể dùng kiểu trả về boolean; nếu cần một nghiệm cụ thể, dùng Optional hoặc một kiểu kết quả phân biệt rõ **có nghiệm/không có nghiệm**.

**Không được nhầm:** “lời giải đầu tiên” chỉ là nghiệm đầu tiên **theo thứ tự duyệt**. Nó **không tự động là lời giải tốt nhất**, ngắn nhất, có chi phí nhỏ nhất hoặc nhỏ nhất theo từ điển; các tính chất này cần điều kiện riêng hoặc chứng minh thứ tự duyệt phù hợp.

### Cùng một bài toán, hai đặc tả

| Tiêu chí | Dừng ở nghiệm đầu tiên | Liệt kê mọi nghiệm |
|---|---|---|
| Câu hỏi cần trả lời | Có nghiệm không? Một nghiệm là gì? | Tất cả nghiệm hợp lệ là gì? |
| Khi gặp nghiệm | Ghi hoặc trả nghiệm rồi phát tín hiệu **dừng toàn cục** | Ghi nghiệm rồi **quay lui tiếp** |
| Khi nhánh hiện tại hết cách | Quay về cha để thử nhánh khác, nếu chưa tìm được nghiệm | Quay về cha để thử nhánh khác |
| Khi tìm được nghiệm thứ nhất | Không xét nhánh còn lại | Tiếp tục xét nhánh còn lại |
| Khi không có nghiệm | Optional.empty/false | Danh sách rỗng hoặc số lượng 0 |
| Bộ nhớ đầu ra | Một nghiệm, thường O(độ dài nghiệm) | Phụ thuộc **số lượng và kích thước mọi nghiệm** |
| Thời gian xấu nhất | Vẫn có thể phải duyệt gần hết cây | Phải bao phủ mọi nhánh có khả năng chứa nghiệm |
| Tính đầy đủ | Bảo đảm có một nghiệm hợp lệ nếu có nghiệm | Bảo đảm không bỏ sót **bất kỳ nghiệm** nào |

**Đích của thuật toán phải rõ ràng ngay từ giao diện hàm**, bởi quyết định trả về sớm có thể là đúng trong chế độ find-first nhưng sai hoàn toàn trong chế độ enumerate-all.

## 2. Cây tìm kiếm, nghiệm, trạng thái và tín hiệu dừng

Một nút trong cây DFS là một **trạng thái tìm kiếm**: những lựa chọn đã thực hiện và thông tin cần thiết để biết lựa chọn nào còn hợp lệ. Một nút lá hoàn chỉnh thỏa toàn bộ ràng buộc là **một nghiệm**.

Duyệt DFS có ba hành động:
1. **Chọn (choose):** đưa một lựa chọn vào trạng thái hiện tại.
2. **Đi sâu (explore):** gọi đệ quy hoặc xử lý trạng thái con.
3. **Hoàn tác (unchoose):** khôi phục trạng thái như trước khi chọn để thử nhánh anh em.

Giả sử một lời gọi dfs đang xét nhiều lựa chọn:

~~~text
dfs(state):
    for choice in legalChoices(state):
        apply(choice)
        dfs(nextState)
        undo(choice)
~~~

Nếu chỉ tìm nghiệm đầu tiên, ta phải biết **một lời gọi con đã tìm thấy nghiệm hay chưa**, và **truyền tín hiệu dừng trở lại mọi lời gọi tổ tiên**. Nếu không truyền tín hiệu này, một lời gọi con có thể trả về sau khi tìm nghiệm, nhưng lời gọi cha vẫn tiếp tục với lựa chọn khác.

Với enumerate-all, việc một nhánh hoàn thành một nghiệm **không kết thúc toàn cây**. Ta ghi bản sao nghiệm, quay lui và tiếp tục các nhánh chưa được duyệt.

### Đặt tên đúng cho giá trị trả về

- Trong hàm **dfsFirst**, boolean true thường mang nghĩa: **đã tìm được nghiệm, cần ngừng tìm ở các mức cha**.
- Trong hàm **dfsAll**, thường dùng kiểu void hoặc một bộ thu kết quả; nhánh kết thúc sau khi ghi nghiệm, nhưng các nhánh khác tiếp tục.
- Trong một bộ máy DFS dùng chung, boolean có thể được định nghĩa là **shouldStop**. Khi đó true nghĩa **yêu cầu dừng**, không nhất thiết tương đương “có nghiệm” ở mọi chế độ. Cần đọc đúng hợp đồng.

Tín hiệu dừng nên tách khỏi nội dung nghiệm: một nghiệm có thể là **cấu trúc rỗng hợp lệ**, nên không được dùng “danh sách rỗng” để biểu thị đồng thời “không có nghiệm”.

## 3. Giả mã: tìm một nghiệm

Một mẫu đơn giản dùng boolean lan ngược từ nhánh thành công:

~~~text
dfsFirst(state):
    if state is a complete valid solution:
        saveCopy(state.solution)
        return true

    for choice in legalChoices(state):
        apply(choice)

        found = dfsFirst(nextState)

        undo(choice)
        if found:
            return true       // TRUYỀN dừng lên cha

    return false               // Không nhánh nào thành công
~~~

**Thứ tự hoàn tác và return:** ở ví dụ này, ta luôn undo trước khi truyền true, nên trạng thái dùng chung trở lại như trước. Nội dung nghiệm phải được **sao chép** khi tới trạng thái hoàn chỉnh, vì sau đó path có thể bị thay đổi bởi các lệnh undo.

Có biến thể return true trước khi undo nếu toàn bộ trạng thái chỉ là dữ liệu cục bộ rồi bị hủy ngay, nhưng cách đó gây rủi ro khi trạng thái tiếp tục được tái sử dụng hoặc kiểm tra. Với bộ máy tổng quát, **hoàn tác đối xứng ở cả nhánh thành công lẫn thất bại** dễ duy trì bất biến hơn.

**Phân biệt thất bại ở một nhánh với không có nghiệm:** dfsFirst trả false tại một lời gọi con chỉ có nghĩa *nhánh con đó không tìm được nghiệm*. Cha vẫn phải thử các nhánh anh em. Chỉ khi lời gọi **gốc** kết thúc false mới biết toàn bộ cây tìm kiếm (sau cắt tỉa an toàn) không có nghiệm.

## 4. Giả mã: liệt kê toàn bộ lời giải

Mẫu enumerate-all chỉ ghi nghiệm ở lá, rồi tiếp tục:

~~~text
dfsAll(state, answer):
    if state is a complete valid solution:
        answer.add(copy(state.solution))
        return                  // Chỉ kết thúc lời gọi LÁ

    for choice in legalChoices(state):
        apply(choice)
        dfsAll(nextState, answer)
        undo(choice)
~~~

Ở đây, lệnh return sau khi ghi nghiệm **không phải dừng toàn cục**. Nó chỉ kết thúc **lời gọi đang ở lá**. Các lời gọi cha sau đó tiếp tục các vòng for còn lựa chọn chưa thử.

Một nhầm lẫn phổ biến là cho rằng “có return trong hàm đệ quy” đồng nghĩa “thuật toán đã kết thúc”. Điều đó không đúng nếu cha còn vòng lặp; chỉ việc **truyền tín hiệu** hoặc dùng một cơ chế hủy toàn cục có kiểm soát mới dừng được toàn bộ cây.

### Phản ví dụ về return thiếu lan truyền

~~~text
dfsWrong(state):
    if complete(state):
        print(state)
        return

    for choice in choices:
        apply(choice)
        dfsWrong(nextState)
        undo(choice)
        // Cha vẫn tiếp tục mọi choice ở đây!
~~~

Hàm trên là một mẫu **liệt kê** (nếu các nhánh đều được duyệt đúng); nó **không** bảo đảm dừng sau nghiệm đầu tiên. Thêm một lệnh break ở **vòng lặp con** cũng chỉ dừng vòng lặp ấy, chưa chắc đã dừng các vòng lặp nằm ở tổ tiên.

## 5. Ví dụ xuyên suốt: bài toán N quân hậu

Cho bàn cờ n×n, đặt **n quân hậu** sao cho không có hai quân hậu nào tấn công nhau theo hàng, cột hoặc đường chéo.

Ta đặt **một quân hậu ở mỗi hàng**, từ hàng 0 đến hàng n−1. Trạng thái là một mảng:

\[
queenCol[r]=c,
\]

nghĩa là quân hậu tại hàng r nằm ở cột c. Một lời giải là mảng có n số nguyên, mỗi số trong [0,n−1], với các cột và đường chéo không xung đột.

Ví dụ n=4 có **hai** lời giải dưới dạng danh sách cột 0-based:

~~~text
Lời giải 1: [1, 3, 0, 2]
.Q..
...Q
Q...
..Q.

Lời giải 2: [2, 0, 3, 1]
..Q.
Q...
...Q
.Q..
~~~

Dấu Q biểu diễn quân hậu, dấu chấm là ô trống. Hai cách đặt này đều hợp lệ và khác nhau về tọa độ. Trong bài toán đang xét, đối xứng phản chiếu bàn cờ **không** làm chúng trở thành “cùng nghiệm”; nếu một đề coi các phép đối xứng là tương đương, phải đặt thêm quy tắc chuẩn hóa hoặc khử trùng.

### Kết quả theo chế độ

Nếu duyệt hàng tăng từ 0 và trong mỗi hàng thử cột tăng từ 0:
- **Find first (n=4):** gặp [1,3,0,2] trước, sau đó dừng. Không duyệt tiếp để sinh [2,0,3,1].
- **Enumerate all (n=4):** sinh cả [1,3,0,2] và [2,0,3,1].
- **Exists (n=4):** true, có thể dừng ngay khi thấy nghiệm đầu tiên.
- **Count all (n=4):** 2. Muốn đếm **chính xác**, không được dừng sau nghiệm thứ nhất.

Với n=2 và n=3, không có cách đặt n quân hậu hợp lệ. Cả find-first lẫn enumerate-all **vẫn có thể phải xét toàn bộ cây hợp lệ đến mức cần thiết** trước khi kết luận không có nghiệm.

Với n=1 có một lời giải [0]. Với n=0, theo quy ước tổ hợp thường dùng, tồn tại **một cách đặt rỗng hợp lệ**: không có hàng nào cần đặt hậu. Vì vậy enumerate-all(0) trả **[[]]**, không phải danh sách không có kết quả. Find-first(0) trả **một Optional có chứa danh sách rỗng**.

## 6. Kiểm tra tính hợp lệ nhanh bằng cột và đường chéo

Khi đang đặt tại hàng r và thử cột c:
- Hai hậu khác hàng là chắc chắn vì mỗi lời gọi xử lý một hàng mới.
- Dùng usedColumn[c] để biết cột c đã có hậu chưa.
- Một đường chéo có cùng hiệu hàng−cột. Với n>0, chỉ số hóa bằng \(d_1=r-c+(n-1)\), nằm trong [0,2n−2].
- Đường chéo hướng còn lại có cùng tổng hàng+cột, chỉ số \(d_2=r+c\), cũng nằm trong [0,2n−2].

Điều kiện đặt hợp lệ:

\[
\neg usedColumn[c]\land \neg diagDiff[d_1]\land \neg diagSum[d_2].
\]

Khi chọn (r,c), đánh dấu ba mảng boolean tương ứng; khi quay lui, trả ba vị trí ấy về false. Với các mảng đánh dấu, kiểm tra một lựa chọn tốn **O(1)** thay vì duyệt lại mọi quân hậu đã đặt.

**Bất biến:** trước khi xử lý một hàng r, những quân hậu ở hàng 0..r−1 không tấn công nhau; các mảng used/diag ghi chính xác cột và đường chéo chúng chiếm. Chỉ đi sâu khi kiểm tra hợp lệ, nên mọi trạng thái được truy cập giữ bất biến.

Sắp xếp thứ tự cột từ nhỏ tới lớn làm thứ tự DFS **xác định**. Nếu đổi thứ tự duyệt, nghiệm đầu tiên có thể thay đổi dù tập nghiệm đầy đủ vẫn không đổi.

## 7. Java 17+ độc lập: cùng một DFS, hai chế độ dừng

Chương trình minh họa có hai API:
- **findFirst(n): Optional<List<Integer>>** — trả một nghiệm nếu có, hoặc Optional.empty nếu không có.
- **enumerateAll(n): List<List<Integer>>** — trả danh sách toàn bộ nghiệm theo thứ tự DFS.

Cả hai dùng chung hàm search, nhưng tham số **stopAfterFirst** quyết định việc có truyền true sau khi ghi nghiệm hay không. Bộ máy DFS trả boolean với ý nghĩa **shouldStop**, không phải “có ít nhất một nghiệm” trong mọi chế độ.

Code dùng một State chứa mảng cột theo hàng và ba mảng đánh dấu cột/đường chéo. Các lựa chọn được **hoàn tác kể cả khi nhánh con yêu cầu dừng**, nhờ đó trạng thái nội bộ sạch sau mỗi lần gọi. Nghiệm được lưu bằng **List.copyOf**, không tham chiếu tới mảng còn đang bị thay đổi.

Để ví dụ không vô tình cấp phát khối lượng đầu ra rất lớn, API giới hạn **0≤n≤12**. Đây là giới hạn của **chương trình minh họa**, không phải định nghĩa toán học của bài toán N quân hậu.

Lưu thành tệp **BacktrackingSearchModesDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Optional;

public final class BacktrackingSearchModesDemo {
    private BacktrackingSearchModesDemo() {
    }

    private static final int MAX_N = 12;

    private static final class State {
        final int[] queenCol;
        final boolean[] usedColumn;
        final boolean[] diagDiff;
        final boolean[] diagSum;

        State(int n) {
            queenCol = new int[n];
            Arrays.fill(queenCol, -1);
            usedColumn = new boolean[n];

            // Hai vị trí dư để n=0 vẫn cấp phát an toàn.
            diagDiff = new boolean[2 * n + 1];
            diagSum = new boolean[2 * n + 1];
        }
    }

    private static void checkN(int n) {
        if (n < 0 || n > MAX_N) {
            throw new IllegalArgumentException("n must be 0..12");
        }
    }

    private static List<Integer> snapshot(int[] positions) {
        List<Integer> result = new ArrayList<>(positions.length);
        for (int col : positions) {
            result.add(col);
        }
        return List.copyOf(result);
    }

    // true: phải dừng toàn bộ DFS. false: tiếp tục duyệt.
    private static boolean search(
            int row, State state, List<List<Integer>> solutions,
            boolean stopAfterFirst) {
        int n = state.queenCol.length;

        if (row == n) {
            solutions.add(snapshot(state.queenCol));
            return stopAfterFirst;
        }

        for (int col = 0; col < n; col++) {
            int d1 = row - col + n - 1;
            int d2 = row + col;

            if (state.usedColumn[col]
                    || state.diagDiff[d1]
                    || state.diagSum[d2]) {
                continue;
            }

            // CHỌN.
            state.queenCol[row] = col;
            state.usedColumn[col] = true;
            state.diagDiff[d1] = true;
            state.diagSum[d2] = true;

            // ĐI SÂU.
            boolean shouldStop = search(
                    row + 1, state, solutions, stopAfterFirst);

            // HOÀN TÁC cả khi shouldStop=true.
            state.queenCol[row] = -1;
            state.usedColumn[col] = false;
            state.diagDiff[d1] = false;
            state.diagSum[d2] = false;

            // Chỉ find-first mới truyền true từ lá lên gốc.
            if (shouldStop) {
                return true;
            }
        }

        return false;
    }

    public static Optional<List<Integer>> findFirst(int n) {
        checkN(n);
        List<List<Integer>> found = new ArrayList<>(1);
        search(0, new State(n), found, true);
        return found.isEmpty()
                ? Optional.empty()
                : Optional.of(found.get(0));
    }

    public static List<List<Integer>> enumerateAll(int n) {
        checkN(n);
        List<List<Integer>> results = new ArrayList<>();
        search(0, new State(n), results, false);
        return List.copyOf(results);
    }

    public static void main(String[] args) {
        Optional<List<Integer>> first4 = findFirst(4);
        List<List<Integer>> all4 = enumerateAll(4);

        System.out.println("First n=4: " + first4);
        System.out.println("All n=4: " + all4);
        System.out.println("Count n=4: " + all4.size());
        System.out.println("Exists n=4: " + first4.isPresent());

        System.out.println("First n=2: " + findFirst(2));
        System.out.println("All n=2: " + enumerateAll(2));
        System.out.println("First n=0: " + findFirst(0));
        System.out.println("All n=0: " + enumerateAll(0));
        System.out.println("First n=1: " + findFirst(1));
    }
}
~~~

Biên dịch/chạy với **JDK 17 hoặc mới hơn**:

~~~bash
javac -encoding UTF-8 BacktrackingSearchModesDemo.java
java BacktrackingSearchModesDemo
~~~

**Stdout chính xác:**

~~~text
First n=4: Optional[[1, 3, 0, 2]]
All n=4: [[1, 3, 0, 2], [2, 0, 3, 1]]
Count n=4: 2
Exists n=4: true
First n=2: Optional.empty
All n=2: []
First n=0: Optional[[]]
All n=0: [[]]
First n=1: Optional[[0]]
~~~

### Vì sao một hàm search phục vụ được hai mục tiêu?

Khi row==n, ta đã đặt đủ n quân hậu và tất cả ràng buộc đã được giữ suốt đường đi. Hàm **ghi một bản sao** của queenCol:

~~~java
solutions.add(snapshot(state.queenCol));
return stopAfterFirst;
~~~

- Với **stopAfterFirst=true**, lá hợp lệ trả true. Mỗi tổ tiên sau khi **undo** sẽ thấy shouldStop=true và return true tiếp, cho tới gốc. Như vậy cả cây dừng sau nghiệm thứ nhất.
- Với **stopAfterFirst=false**, lá hợp lệ trả false. Cha hoàn tác lựa chọn rồi tiếp tục vòng for, nên mọi nhánh hợp lệ khác vẫn được duyệt.
- Một lời gọi **không có nhánh thành công** cũng trả false, nhưng ý nghĩa là “không có yêu cầu dừng từ bên dưới”. Trong chế độ enumerate-all, một cây con có thể **đã thêm nhiều nghiệm** mà vẫn trả false để cho phép tìm tiếp.

**Lưu ý quan trọng:** boolean trả từ search có nghĩa **yêu cầu dừng**, không phải số nghiệm khác 0. Vì vậy hàm công khai findFirst kiểm tra found.isEmpty() để tạo Optional; hàm enumerateAll chỉ dùng danh sách đã được tích lũy.

### Vì sao snapshot trước khi undo?

Nếu lưu tham chiếu tới mảng queenCol (hoặc một List path còn bị sửa), khi quay lui chạy các phép gán lại, những nghiệm đã lưu có thể biến đổi hoặc giống nhau. snapshot tạo một danh sách mới và List.copyOf đảm bảo kết quả đó không đổi.

Trong mẫu này, mọi lời gọi trả về đều đã hoàn tác những lựa chọn nó tự thực hiện. Vì vậy nếu sau này thay cách sử dụng State, quy ước **chọn/hoàn tác đối xứng** vẫn dễ kiểm tra.

### Ý nghĩa của Optional trong trường hợp n=0

- **Optional.empty:** không có nghiệm. Ví dụ n=2.
- **Optional.of(List.of()):** có nghiệm, và nghiệm ấy là một **danh sách rỗng hợp lệ**. Ví dụ n=0 theo quy ước toán học.

Hai trạng thái đó phải phân biệt được. Nếu hàm chỉ trả List và dùng danh sách rỗng cho “không tìm được”, sẽ không biết kết quả trống là nghiệm hợp lệ hay thất bại.

## 8. Chứng minh tính đúng cho hai chế độ

### 8.1. Tính hợp lệ của mọi nghiệm được ghi

Một đường đi bắt đầu từ hàng 0 và mỗi lần đặt đúng một quân hậu ở hàng r. Trước khi chọn (r,c), search kiểm tra không trùng cột và không trùng hai đường chéo. Do các hàng khác nhau theo từng mức đệ quy, mọi quân hậu trong đường đi không tấn công nhau.

Khi row==n, đã có đúng n quân hậu, mỗi hàng một quân và không có xung đột. Vì thế **mọi danh sách ghi ở lá đều là nghiệm hợp lệ**.

### 8.2. Không lặp nghiệm trong enumerate-all

Một nghiệm được biểu diễn bằng mảng queenCol dài n. Với một dãy cột cố định, từ hàng 0 tới hàng n−1 chỉ có **một chuỗi lựa chọn** tạo ra dãy ấy. Mỗi vòng for chỉ thử mỗi cột một lần tại hàng đang xét. Vì vậy cùng một dãy queenCol không thể được ghi hai lần.

Hai nghiệm n=4 có thể là ảnh phản chiếu, nhưng **khác dãy vị trí**. Theo định nghĩa bài toán đang dùng, đó vẫn là hai nghiệm phân biệt.

### 8.3. Không bỏ sót nghiệm trong enumerate-all

Xét một nghiệm hợp lệ X. Ở hàng 0, vòng for xét tất cả cột, nên cuối cùng sẽ xét cột X[0]. Vì X hợp lệ, nhánh ấy không bị kiểm tra xung đột loại bỏ. Tại hàng 1, vẫn có nhánh chọn X[1], v.v. Quy nạp theo số hàng đã đặt cho thấy có một đường DFS đi theo **toàn bộ các cột của X** đến row==n.

Khi stopAfterFirst=false, search **không truyền yêu cầu dừng sau một nghiệm**, nên đường đi của X không bị bỏ qua chỉ vì một nghiệm khác xuất hiện trước. Do đó mọi nghiệm hợp lệ đều được ghi.

### 8.4. Find-first đúng khi dừng sớm

Trong chế độ stopAfterFirst=true, nếu tìm được một lá hoàn chỉnh, tính hợp lệ đã được chứng minh. Hàm truyền true qua mọi mức và không cần xem thêm nhánh nào khác, vì hợp đồng **chỉ yêu cầu một nghiệm**.

Nếu toàn bộ cây đã được duyệt mà không thấy lá hợp lệ, danh sách found vẫn rỗng; thuật toán trả Optional.empty. Không có nghiệm bị bỏ sót trước khi kết luận thất bại, bởi mỗi nhánh hợp lệ đều được duyệt trừ khi đã tìm được một nghiệm.

**Kết luận:** find-first bảo đảm một nghiệm hợp lệ khi tồn tại; enumerate-all bảo đảm đầy đủ tập nghiệm. Dừng sớm là **một phần đặc tả**, không phải mẹo tối ưu vô điều kiện.

## 9. Độ phức tạp: đầu ra quyết định chi phí

Với N quân hậu, mỗi hàng thử tối đa n cột, và việc kiểm tra một vị trí tốn O(1) nhờ các mảng đánh dấu. Vì không có hai quân hậu cùng cột, một cận trên đơn giản cho số nút thử là theo những hoán vị cột chưa dùng; tổng chi phí duyệt có thể chặn bởi **O(n·n!)** thời gian. Điều kiện đường chéo giúp cắt bỏ nhiều nhánh nhưng không loại bỏ tính tăng trưởng rất nhanh.

Gọi S là số nghiệm hợp lệ của bài toán n hậu.

| Chế độ | Thời gian | Bộ nhớ làm việc | Bộ nhớ lưu kết quả |
|---|---|---|---|
| Find first | Tốt hơn khi gặp nghiệm sớm; **xấu nhất vẫn O(n·n!)** | O(n) cho path, flags và stack | O(n) cho một nghiệm |
| Enumerate all | Duyệt đầy đủ cây hợp lệ; cận trên **O(n·n!)** | O(n) | **O(nS)** khi lưu mọi nghiệm |
| Exists | Có thể dừng như find-first, không cần lưu nghiệm nếu chỉ trả boolean | O(n) | O(1) cho đáp án boolean |
| Count all | Không cần lưu danh sách, nhưng phải đi hết các nhánh có thể chứa nghiệm | O(n) | O(1) cho bộ đếm, ngoài kiểm soát tràn số |

Bản Java minh họa dùng enumerateAll(4).size() để đếm, nên **vẫn lưu mọi nghiệm**; đó không phải phiên bản count-only tối ưu bộ nhớ. Muốn đếm mà không lưu, ở lá hợp lệ tăng bộ đếm và **tiếp tục tìm**, thay vì thêm snapshot vào danh sách.

**Chi phí xuất kết quả:** riêng việc lưu hoặc in S nghiệm dài n đã cần ít nhất \(\Omega(nS)\) thời gian thao tác với dữ liệu. Do đó một thuật toán liệt kê đúng **không thể hứa thời gian độc lập với số nghiệm đầu ra**.

**Không bảo đảm find-first luôn nhanh:** với n=2 hoặc n=3, không có nghiệm nên find-first phải khám phá toàn bộ phần cây không bị cắt tỉa, gần giống enumerate-all. Nếu nghiệm đầu tiên nằm rất muộn trong thứ tự DFS, lợi ích dừng sớm cũng nhỏ.

**Độ sâu:** cả hai chế độ đều đi nhiều nhất n hàng, nên stack đệ quy O(n), các mảng cột và đường chéo O(n). Mã giới hạn n≤12 chủ yếu vì việc liệt kê/lưu tất cả nghiệm có thể rất tốn thời gian và RAM khi n tăng.

## 10. “Đầu tiên” phụ thuộc thứ tự duyệt; không đồng nghĩa tối ưu

Nếu duyệt cột tăng dần, findFirst(4) trả [1,3,0,2]. Nếu duyệt cột giảm dần, nghiệm đầu tiên có thể là [2,0,3,1]. Cả hai đều thỏa N quân hậu.

Thứ tự đầu tiên được xác định bởi:
- Thứ tự các biến/trạng thái được xử lý.
- Thứ tự các giá trị được thử ở mỗi bước.
- Quy tắc kiểm tra và cắt tỉa.
- Cách xử lý những lựa chọn bằng nhau khi bài có giá trị trùng.

Trong ví dụ N quân hậu, nếu cố định duyệt hàng tăng và cột tăng, nghiệm đầu tiên tình cờ là **mảng cột nhỏ nhất theo thứ tự từ điển** trong các nghiệm hợp lệ, bởi DFS xét các tiền tố theo thứ tự từ điển. Nhưng đây là tính chất của **thứ tự duyệt được xác định**, không phải bảo đảm chung của mọi chiến lược quay lui.

Nếu bài tối ưu hóa hỏi **chi phí thấp nhất** hay **giá trị lớn nhất**, dừng ở nghiệm hợp lệ đầu tiên thường là sai:
- Find-first chỉ chứng minh **tồn tại** một nghiệm.
- Tìm nghiệm tối ưu phải xét mọi ứng viên có thể tốt hơn, hoặc có **cận dưới/cận trên chứng minh** các nhánh còn lại không thể cải thiện nghiệm hiện tại.
- Trong **branch and bound**, ta có thể cắt bỏ nhánh dựa trên cận an toàn, nhưng điều kiện dừng phải bảo đảm tối ưu, không chỉ là “đã có nghiệm”.

Một trường hợp ngoại lệ hợp lệ: nếu duyệt theo **chi phí không giảm được chứng minh**, hoặc ràng buộc đặc biệt bảo đảm nghiệm đầu tiên tối ưu, có thể dừng; phải chứng minh, không suy diễn từ DFS thông thường.

## 11. Cắt tỉa an toàn ở cả hai chế độ

Cắt tỉa (pruning) có nghĩa loại một nhánh trước khi đi tới lá vì biết nhánh ấy **không thể tạo nghiệm cần tìm**.

Trong N quân hậu, nếu thử một cột/đường chéo đã bị chiếm, mọi cách hoàn thiện bắt đầu bằng lựa chọn đó đều xung đột, nên có thể bỏ nhánh. Đây là cắt tỉa **đúng cho cả find-first và enumerate-all**.

Nhưng điều kiện “đã tìm được một nghiệm” chỉ đủ để bỏ **toàn bộ nhánh còn lại** trong chế độ find-first hoặc exists. Với enumerate-all, chính những nhánh còn lại có thể chứa các nghiệm khác; bỏ chúng sẽ làm mất tính đầy đủ.

### Cắt tỉa cho bài toán tối ưu

Nếu đang tối thiểu hóa chi phí và có nghiệm tốt nhất hiện tại best, chỉ được cắt một nhánh nếu có cận dưới lowerBound của **mọi nghiệm có thể sinh từ nhánh đó**, với lowerBound≥best khi chỉ cần một nghiệm tối ưu. Nếu cần **tất cả nghiệm đồng tối ưu**, cắt khi lowerBound==best có thể bỏ nghiệm tối ưu khác, nên chính sách cắt phải đổi.

Điều này cho thấy cùng một cây tìm kiếm, **yêu cầu đầu ra quyết định điều kiện cắt tỉa hợp lệ**. Tìm một nghiệm, tìm tất cả nghiệm, tìm một nghiệm tối ưu và tìm tất cả nghiệm tối ưu là bốn hợp đồng khác nhau.

### Dừng theo số lượng K là một chế độ khác

“Lấy nhiều nhất K nghiệm” (find K) có thể dừng sau khi ghi K nghiệm, nhưng nó **không phải enumerate-all** nếu còn nghiệm chưa duyệt. Để báo cáo rõ, API nên trả cả:
- Các nghiệm đã lấy.
- Trạng thái kết thúc (đã duyệt hết hay bị giới hạn K/cancel).

Nếu chỉ trả một danh sách dài K, người gọi không thể biết tập nghiệm đầy đủ chỉ có K phần tử hay thuật toán đã **dừng sớm**.

## 12. Lưu kết quả: bộ nhớ, streaming và đếm

**Enumerate-all lưu vào List** rất tiện để học và kiểm thử, nhưng có thể tốn O(nS) bộ nhớ cho S nghiệm dài n. Với dữ liệu lớn, có thể dùng:
- **Callback/Consumer:** ở mỗi lá hợp lệ, gửi một snapshot cho người nhận; không giữ tất cả nghiệm trong RAM.
- **Iterator/generator tự quản lý trạng thái:** cho phép lấy lần lượt các nghiệm, với yêu cầu quản lý việc tạm dừng và phục hồi DFS.
- **Đếm nghiệm:** ở mỗi lá tăng một biến đếm, không lưu path; vẫn phải duyệt các nhánh chứa nghiệm.
- **Giới hạn K nghiệm:** dừng có chủ đích sau K, báo rõ kết quả là danh sách **một phần**.
- **Hủy theo yêu cầu (cancel):** kiểm tra cờ hủy ở các điểm an toàn và trả trạng thái đã hủy; **không tuyên bố đã liệt kê hết**.

Cả callback và streaming vẫn cần định nghĩa **chính sách dừng**. Ví dụ callback có thể trả boolean shouldStop, khi đó cần lan truyền true qua mọi tầng DFS như trong ví dụ Java. Không được để callback giữ một tham chiếu tới path còn đang thay đổi trừ khi hợp đồng quy định rõ việc sao chép.

Nếu chỉ muốn trả lời “có nghiệm không”, lưu toàn bộ danh sách rồi kiểm tra isEmpty() là lãng phí. Nên dùng find-first/exists để dừng khi đã có đủ thông tin.

## 13. Các lỗi thường gặp

1. **Nhầm return tại lá với dừng toàn bộ DFS.** return chỉ kết thúc lời gọi hiện tại; tổ tiên có thể tiếp tục các nhánh khác.
2. **Quên truyền true qua từng lời gọi cha** ở find-first, khiến thuật toán vẫn liệt kê cả cây.
3. **Dùng break để dừng toàn bộ:** break thường chỉ kết thúc **vòng lặp gần nhất**, không thoát mọi mức đệ quy.
4. **Trả false ngay khi một nhánh con thất bại:** kết luận “không có nghiệm” quá sớm, bỏ qua các nhánh anh em.
5. **Dừng sau nghiệm thứ nhất khi yêu cầu enumerate-all:** làm thiếu các nghiệm còn lại.
6. **Tiếp tục duyệt khi chỉ cần một nghiệm**, làm phí thời gian và bộ nhớ không cần thiết.
7. **Coi nghiệm đầu tiên là tối ưu** mà không chứng minh thứ tự duyệt hoặc cận tối ưu.
8. **Lưu tham chiếu path đang bị sửa** thay vì một snapshot, khiến nghiệm đã ghi thay đổi sau khi undo.
9. **Không hoàn tác đầy đủ flags/path** khi nhánh trả true hoặc false, làm trạng thái ô nhiễm giữa các nhánh/lượt gọi.
10. **Dùng danh sách rỗng để biểu thị đồng thời không có nghiệm và nghiệm rỗng.** Cần Optional hoặc cờ riêng.
11. **Dùng danh sách kết quả trong một biến global không reset** giữa các lần chạy, khiến nghiệm các truy vấn trước lẫn vào truy vấn sau.
12. **Đếm số nghiệm bằng cách dừng ở nghiệm đầu tiên:** chỉ biết có ít nhất một, không biết tổng số nghiệm.
13. **Liệt kê có giới hạn K nhưng báo là toàn bộ:** phải nêu rõ bị cắt theo giới hạn.
14. **Cắt tỉa theo giả định không được chứng minh:** có thể bỏ nghiệm hợp lệ, phá tính đầy đủ của enumerate-all.
15. **Không quy định thứ tự duyệt** nhưng test cứng đúng một nghiệm đầu tiên, dẫn tới kết quả không tái lập khi đổi lựa chọn.
16. **Không xác định thế nào là nghiệm phân biệt:** N quân hậu đối xứng có thể được xem là hai nghiệm khác nhau hoặc cùng một lớp tương đương tùy đề bài.
17. **Coi enum-all luôn đa thức:** số nghiệm có thể rất lớn; chi phí xuất dữ liệu không thể bỏ qua.
18. **Khẳng định đã không có nghiệm khi chỉ tìm một phần cây** do timeout, hủy hoặc giới hạn bước; phải phân biệt “chưa tìm thấy” với “đã chứng minh không tồn tại”.
19. **Tái sử dụng State sau khi một nhánh dừng mà chưa undo:** có thể gây lỗi trong những lượt gọi sau.
20. **Mặc định mọi cơ sở rỗng là thất bại:** nhiều bài tổ hợp có **một nghiệm rỗng hợp lệ** khi đầu vào hoặc mục tiêu là rỗng.

## 14. Kiểm thử cả ngữ nghĩa tìm kiếm

Không chỉ kiểm thử một giá trị đầu ra; cần kiểm tra **tính hợp lệ, sự đầy đủ và thời điểm dừng**.

| Đầu vào n | Find-first | Enumerate-all | Diễn giải |
|---|---|---|---|
| 0 | Optional chứa [] | [[]] | Một nghiệm rỗng theo quy ước |
| 1 | [0] | [[0]] | Một nghiệm |
| 2 | Không có | [] | Không có nghiệm |
| 3 | Không có | [] | Không có nghiệm |
| 4 | [1,3,0,2] khi duyệt cột tăng | Hai nghiệm | Phân biệt dừng sớm và liệt kê đầy đủ |

### Kiểm tra một nghiệm N quân hậu

Với mảng queenCol độ dài n:
1. Mỗi cột c nằm trong 0..n−1.
2. Không có hai hàng khác nhau chọn cùng cột.
3. Không có hai hàng r1,r2 mà \(|r_1-r_2|=|queenCol[r_1]-queenCol[r_2]|\).
4. Mỗi hàng được gán đúng một cột.

Với enumerate-all, kiểm tra thêm không có hai mảng queenCol giống nhau. Với n nhỏ, có thể brute force toàn bộ các hoán vị cột và lọc đường chéo để so tập nghiệm với thuật toán quay lui.

### Kiểm tra sự dừng sớm

Có thể thêm bộ đếm số nút đã thăm vào bản thử nghiệm (không bắt buộc trong mã chính):
- Ở n=4, find-first phải dừng sau khi thấy [1,3,0,2]; không sinh nghiệm thứ hai.
- Enumerate-all phải chứa cả hai nghiệm.
- Ở n=2, do không có nghiệm, find-first không được trả true chỉ vì đã thăm một trạng thái chưa hoàn chỉnh.
- Gọi nhiều lần phải cho kết quả độc lập, không bị ảnh hưởng bởi trạng thái cũ.
- Cờ shouldStop chỉ có tác dụng ngừng nếu **mọi mức** kiểm tra và truyền lại nó.

**Trường hợp không có nghiệm và tìm kiếm chưa hoàn thành:** nếu người dùng hủy hoặc vượt giới hạn, không được trả Optional.empty như thể đã chứng minh không có nghiệm. Trong hệ thống thật, nên có trạng thái kết quả riêng như FOUND, EXHAUSTED, CANCELLED hoặc LIMIT_REACHED.

## 15. Khi chọn API nào trong dự án thực tế?

**Find-first/exists** phù hợp khi:
- Cần kiểm tra có thể xếp lịch, điền một cấu hình hợp lệ hay không.
- Cần một nhân chứng để chứng minh ràng buộc khả thi.
- Một nghiệm bất kỳ đủ để tiếp tục quy trình xử lý.
- Ưu tiên giảm thời gian trung bình bằng dừng sớm khi gặp nghiệm.

**Enumerate-all** phù hợp khi:
- Cần hiển thị mọi cách bố trí/cấu hình hợp lệ.
- Cần phân tích tất cả khả năng để đưa ra quyết định tiếp theo.
- Cần đếm, thống kê hoặc kiểm tra phạm vi toàn bộ không gian lời giải.
- Cần xác nhận **không bỏ sót** các trường hợp trong một phép kiểm thử toàn diện nhỏ.

**Find-optimal** là một mục tiêu khác: cần hàm mục tiêu và chiến lược chứng minh tối ưu. Việc tìm thấy một nghiệm sớm chỉ cung cấp **nghiệm khả thi ban đầu**, chưa phải nghiệm tốt nhất.

Trước khi viết DFS, nên làm rõ hợp đồng: **một nghiệm, mọi nghiệm, số nghiệm, nghiệm tối ưu, tất cả nghiệm tối ưu, hay tối đa K nghiệm?** Quyết định đó ảnh hưởng tới kiểu trả về, điều kiện dừng, cắt tỉa và cách quản lý bộ nhớ.

## 16. Bài tập tự kiểm tra

**Câu 1.** Trong dfsAll, gặp một nghiệm rồi return có làm dừng toàn bộ cây tìm kiếm không?

**Đáp án:** Không. Lệnh return chỉ kết thúc lời gọi đang ở lá; các mức cha còn có vòng lặp và có thể duyệt tiếp những nhánh anh em.

**Câu 2.** Trong dfsFirst, sau khi một lời gọi con trả true, lời gọi cha phải làm gì?

**Đáp án:** Hoàn tác phần lựa chọn của cha để giữ trạng thái nhất quán nếu cần, rồi **trả true lên tiếp**; không thử lựa chọn khác.

**Câu 3.** Tại sao lời gọi con trả false không có nghĩa toàn bài vô nghiệm?

**Đáp án:** Nó chỉ chứng minh **nhánh con hiện tại** không sinh nghiệm. Các nhánh anh em có thể thành công; chỉ khi gốc đã xét hết các nhánh mà không gặp nghiệm mới kết luận không có.

**Câu 4.** N quân hậu n=4 có bao nhiêu lời giải theo vị trí?

**Đáp án:** Hai: [1,3,0,2] và [2,0,3,1]. Khi duyệt cột tăng dần, nghiệm đầu tiên là [1,3,0,2].

**Câu 5.** Tại sao n=0 trong ví dụ trả Optional[[]] thay vì Optional.empty?

**Đáp án:** Theo quy ước, cách đặt **không quân hậu lên bàn cờ rỗng** là một nghiệm hợp lệ. Optional[[]] nghĩa là **có** nghiệm rỗng; Optional.empty nghĩa là **không có** nghiệm.

**Câu 6.** Nếu đã tìm thấy một nghiệm tốt, có thể dừng ngay khi đề yêu cầu nghiệm có chi phí thấp nhất không?

**Đáp án:** Không, trừ khi có chứng minh nghiệm đó đã tối ưu, ví dụ qua cận của những nhánh chưa duyệt hoặc một thứ tự duyệt đặc biệt.

**Câu 7.** Liệt kê all nhưng chỉ trả 10 nghiệm đầu tiên có đúng đặc tả enumerate-all không?

**Đáp án:** Không nếu còn nghiệm khác. Đó là chế độ giới hạn K; phải thông báo kết quả chưa đầy đủ khi dừng do K.

**Câu 8.** Vì sao bản Java luôn snapshot queenCol trước khi hoàn tác?

**Đáp án:** Vì queenCol là trạng thái dùng chung, sẽ bị đặt lại khi quay lui. snapshot giữ cố định nghiệm đã tìm được, không bị thay đổi bởi các nhánh khác.

**Câu 9.** Count-all có thể tiết kiệm bộ nhớ hơn enumerate-all không?

**Đáp án:** Có: tăng một bộ đếm tại mỗi lá thay vì lưu cả danh sách nghiệm. Nhưng nếu cần kết quả **đếm chính xác**, vẫn phải khảo sát mọi nhánh có thể chứa nghiệm hoặc dùng phép đếm toán học/DP tương đương.

**Câu 10.** Khi nào false của bộ máy search dùng chung **không** mang nghĩa “không có nghiệm”?

**Đáp án:** Khi boolean được định nghĩa là **shouldStop**. Trong chế độ enumerate-all, hàm có thể đã ghi nhiều nghiệm nhưng vẫn trả false để cho phép tìm tiếp.

**Ghi nhớ:** Quy tắc đi sâu/hoàn tác của quay lui có thể giống nhau trong cả hai chế độ, nhưng **điều kiện dừng khác nhau**. Find-first trả tín hiệu thành công qua mọi tầng và dừng khi gặp một nghiệm; enumerate-all chỉ ghi từng nghiệm rồi tiếp tục duyệt. Luôn tách **một nghiệm hợp lệ**, **mọi nghiệm**, **không có nghiệm**, **nghiệm rỗng** và **tìm kiếm chưa hoàn thành** thành những trạng thái có ý nghĩa rõ ràng.
