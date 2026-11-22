# Sinh lựa chọn, kiểm tra hợp lệ và hoàn tác trạng thái

**Quay lui (backtracking)** là kỹ thuật tìm kiếm xây dựng lời giải từng bước, **sinh các lựa chọn**, **kiểm tra tính hợp lệ** của mỗi lựa chọn rồi thử đi sâu; khi một nhánh kết thúc hoặc bị loại, thuật toán **hoàn tác mọi thay đổi trạng thái** trước khi xét nhánh tiếp theo. Nhờ kiểm tra trên những lời giải dở dang, quay lui có thể bỏ toàn bộ cây con chắc chắn không chứa lời giải hợp lệ, thay vì đợi đến khi tạo đủ cấu hình mới kiểm tra.

Ý tưởng trung tâm là **Choose → Check → Explore → Undo**, hoặc thường hiệu quả hơn là **Check → Choose → Explore → Undo** nếu kiểm tra được trước khi sửa dữ liệu.

Các bài toán điển hình: sinh tổ hợp/hoán vị, N-Queens, Sudoku, chọn tập thỏa điều kiện, đường đi đơn, gán tài nguyên và tối ưu tổ hợp. Dù tình huống khác nhau, mọi cài đặt đúng đều trả lời được: **đang ở tiền tố nào; các lựa chọn tiếp theo gồm gì; điều kiện nào cho phép loại nhánh; những biến nào bị thay đổi; và cách khôi phục chính xác trạng thái cha**.

Bài học sử dụng hai ví dụ Java 17+ hoàn chỉnh: **N-Queens** (ràng buộc cột và đường chéo) và **hoán vị có giá trị lặp** (sinh lựa chọn với `used[]`, loại kết quả trùng, hoàn tác danh sách). Phần chứng minh tính đúng và phân tích độ phức tạp áp dụng cho các bài quay lui tổng quát.

## 1. Cây tìm kiếm và tiền tố quyết định

Một lời giải gồm d lựa chọn liên tiếp \((x_0,x_1,\ldots,x_{d-1})\). Mỗi **nút** của cây tìm kiếm biểu diễn một tiền tố đã quyết định, còn mỗi **cạnh** biểu diễn việc chọn thêm một phương án. Nút lá có thể là lời giải đầy đủ, trạng thái vô nghiệm hoặc trạng thái bị cắt tỉa.

Ví dụ sinh chuỗi nhị phân dài 3:

~~~text
                 []
               /    \
             [0]    [1]
            /  \    /  \
          00   01  10   11
         / \   / \ / \  / \
        000 001 010 011 100 101 110 111
~~~

Không có ràng buộc, có \(2^3=8\) chuỗi. Nếu yêu cầu **không chứa hai số 1 liên tiếp**, nhánh `11` đã vi phạm và có thể bỏ ngay cả `110`, `111`. Đây là **cắt tỉa theo tiền tố** (*pruning*).

Quay lui vẫn có thể phải duyệt rất nhiều nút: có những bài toán ít ràng buộc và số lời giải tăng theo \(2^n\), \(n!\) hoặc các hàm tổ hợp khác. **Đệ quy không tự tạo tối ưu**; lợi ích đến từ việc duyệt có hệ thống, dừng nhánh không hợp lệ sớm và dùng lại dữ liệu phụ trợ khi thay đổi/hoàn tác.

## 2. Thành phần trạng thái và hợp đồng bất biến

Trạng thái cần lưu đủ thông tin để tiếp tục và kiểm tra:

| Phần trạng thái | Vai trò | Ví dụ |
|---|---|---|
| Tiền tố đã chọn | Biết lời giải dở dang | `current=[B,A]` |
| Độ sâu / vị trí | Biết quyết định kế tiếp | Hàng `row` của N-Queens |
| Thông tin hợp lệ | Kiểm tra nhanh ứng viên | `used[]`, cột/đường chéo |
| Dữ liệu tổng hợp | Tối ưu hoặc giới hạn | Tổng điểm, ngân sách còn lại |
| Kết quả | Lưu/đếm những lời giải đủ điều kiện | Danh sách bản sao kết quả |

Một **bất biến** hữu ích là:

> Trước khi gọi `backtrack(depth)`, trạng thái mutable phản ánh **chính xác depth quyết định hiện có**. Khi lời gọi trả về bình thường, trạng thái người gọi nhận lại phải **giống hệt trước lời gọi**, không mang quyết định của bất kỳ nhánh con nào.

Ví dụ sinh hoán vị `[A,B,C]`, khi `current=[B,A]`, `used` phải đánh dấu đúng vị trí của B và A; nếu một cờ thừa vẫn true sau khi hoàn tác, nhánh kế tiếp sẽ bị loại sai.

**Độ sâu là số quyết định**, không nhất thiết bằng số biến true trong một ứng dụng tổng quát. Mối liên hệ cụ thể phải được phát biểu theo mô hình: với hoán vị, `current.size()==depth` và số cờ `used` đúng bằng depth; với N-Queens, số hậu trên bàn cờ bằng hàng tiếp theo.

## 3. Khuôn giải tổng quát

~~~text
backtrack(state):
    if state hoàn chỉnh:
        if điều kiện cuối cùng được thỏa:
            ghi nhận kết quả
        return

    for choice in generateChoices(state):
        if not isValid(state, choice):
            continue

        apply(state, choice)
        backtrack(state)
        undo(state, choice)
~~~

**GenerateChoices:** phải bao quát các khả năng có thể xuất hiện trong lời giải hợp lệ. Ví dụ ở hàng r của N-Queens, thử mọi cột từ 0 tới n-1. Với hoán vị, thử tất cả chỉ số nguồn chưa dùng.

**isValid:** chỉ loại lựa chọn khi có lý do chứng minh nhánh ấy không thể chứa lời giải được yêu cầu. Đặt thêm một quân hậu cùng cột chắc chắn không hợp lệ; ngược lại, một tổng điểm tạm thời chưa đủ lớn **không nhất thiết** là lý do loại nhánh khi còn cơ hội lấy điểm ở bước sau.

**apply:** sửa mọi cấu trúc liên quan đến lựa chọn – ví dụ thêm phần tử vào `current`, bật cờ visited, cập nhật tổng. Nếu sửa nhiều biến, cần ghi nhớ đủ giá trị trước đó để hoàn tác.

**undo:** là phép nghịch của apply **trên trạng thái cha**, thường thực hiện theo thứ tự ngược thao tác thêm. Nó phải phục hồi chính xác các cờ, biến đếm, mảng, stack và cấu trúc phụ trợ; không được chỉ hoàn tác một phần.

### Kiểm tra trước hoặc sau khi áp dụng

Nếu hợp lệ được xác định từ trạng thái cũ và lựa chọn mới, nên **kiểm tra trước khi apply**. Nhánh bị `continue` không cần hoàn tác.

Nếu chỉ kiểm tra được sau khi sửa:

~~~text
apply(choice)
if partialStateValid():
    backtrack()
undo(choice)              // luôn chạy, kể cả khi valid = false
~~~

Tuyệt đối tránh `continue` sau phép kiểm tra thất bại mà bỏ qua `undo`. Nếu hàm con/callback có thể ném ngoại lệ và hợp đồng yêu cầu trả lại trạng thái, có thể bảo vệ thao tác bằng:

~~~java
applyChoice();
try {
    explore();
} finally {
    undoChoice();
}
~~~

`finally` không sửa được một định nghĩa undo sai, nhưng giúp lời gọi vẫn phục hồi trạng thái khi exception thoát khỏi `explore`.

## 4. Ví dụ N-Queens: sinh lựa chọn và kiểm tra nhanh

Bài toán **N-Queens**: đặt n hậu trên bàn cờ n×n, không có hai hậu nào cùng hàng, cột hoặc đường chéo.

Chọn **mỗi hàng đúng một hậu**, theo thứ tự hàng `row=0,1,...,n-1`. Lúc xử lý hàng r, thử từng cột c. Vì mỗi bước chỉ chọn một hàng chưa xét, điều kiện **không trùng hàng** đã được bảo đảm bởi mô hình, không cần quét lại.

Hai ô \((r_1,c_1)\) và \((r_2,c_2)\) cùng đường chéo khi:

\[
r_1-c_1=r_2-c_2
\quad\text{hoặc}\quad
r_1+c_1=r_2+c_2.
\]

Dùng ba mảng boolean:

~~~text
columnUsed[c]
downUsed[row-col+n-1]
upUsed[row+col]
~~~

Với n≥1, chỉ số đường chéo nằm từ 0 tới 2n-2; hai mảng đường chéo dài `2*n-1`.

Một lựa chọn `(row,col)` **hợp lệ** khi cả ba cờ tương ứng đều false. Việc kiểm tra tốn **O(1)**.

### Chuỗi chọn–kiểm tra–hoàn tác

~~~text
for col = 0 .. n-1:
    down = row - col + n - 1
    up = row + col

    if columnUsed[col] or downUsed[down] or upUsed[up]:
        continue

    queenAtRow[row] = col
    columnUsed[col] = true
    downUsed[down] = true
    upUsed[up] = true

    placeQueen(row+1)

    columnUsed[col] = false
    downUsed[down] = false
    upUsed[up] = false
    queenAtRow[row] = -1
~~~

**Mấu chốt:** thao tác xóa ba cờ ở cuối không phải “xóa toàn bộ cờ”. Nó khôi phục **chính những cờ vừa bật** cho quân hậu của hàng hiện tại. Khi chọn hợp lệ, mỗi cờ ấy trước đó false, nên việc đặt lại false là đúng. Các quân ở hàng trước vẫn giữ nguyên thông tin cờ của chúng.

### Mô phỏng với n=4

Khi thử cột đầu tiên 1, ta có thể đi theo nhánh:

~~~text
Hàng 0: chọn cột 1
Hàng 1: chọn cột 3
Hàng 2: chọn cột 0
Hàng 3: chọn cột 2
=> Lời giải [1,3,0,2]
~~~

Bàn cờ tương ứng:

~~~text
. Q . .
. . . Q
Q . . .
. . Q .
~~~

Sau khi lưu lời giải, thuật toán **hoàn tác hậu ở hàng 3**, thử các cột khác; khi hết lựa chọn, hoàn tác hàng 2, quay lại hàng 1 rồi hàng 0. Không có nhánh nào làm thay đổi trạng thái khởi đầu của nhánh anh em.

Với n=4, có đúng **hai lời giải** (không gộp các ảnh đối xứng):

~~~text
[1, 3, 0, 2]
[2, 0, 3, 1]
~~~

Ở dạng `queenAtRow[r]=c`, phần tử thứ r là **cột của hậu trong hàng r**, đều đánh số từ 0. N=2 và N=3 không có lời giải; N=1 có đúng một lời giải. N=8 có **92** lời giải khi phân biệt từng cách xếp trên bàn cờ.

## 5. Bất biến và chứng minh đúng của N-Queens

Trước lời gọi xử lý hàng r:

1. Có **đúng r hậu** ở các hàng \([0,r)\).
2. Các hậu đã đặt **không xung đột**.
3. Mảng `columnUsed` và hai mảng chéo biểu diễn **chính xác** các cột/đường chéo của r hậu.
4. Những ô `queenAtRow[r..n-1]` còn chưa được gán (dùng -1 để dễ kiểm chứng).

**Cơ sở:** r=0, chưa có hậu, các cờ false, mảng vị trí đều -1; bất biến đúng.

**Bước quy nạp:** nếu `(r,c)` có cột hoặc đường chéo đã bị chiếm, đặt hậu đó sẽ vi phạm yêu cầu nên loại nhánh là an toàn. Nếu không, apply đặt thêm một hậu không xung đột và cập nhật cờ, tạo trạng thái đúng ở r+1.

Khi lời gọi con trở về, undo phục hồi ba cờ và vị trí của hậu vừa đặt, nên trạng thái lại đúng với r quân hậu ban đầu.

**Tính đúng của kết quả:** chỉ khi r=n mới ghi lời giải, và từng bước đều giữ không xung đột ⇒ mỗi kết quả hợp lệ.

**Tính đầy đủ:** một lời giải bất kỳ có chính xác một cột ở mỗi hàng. Thuật toán thử mọi cột; những cột của lời giải hợp lệ không bao giờ bị loại vì xung đột với tiền tố của chính nó. Vậy mọi lời giải đều có một đường đi trong cây tìm kiếm.

**Không tạo trùng:** mỗi dãy cột theo hàng xác định duy nhất một đường đi, và được ghi một lần tại lá. Thuật toán không coi các ảnh đối xứng là cùng lời giải trừ khi bài toán yêu cầu thêm bước chuẩn hóa.

## 6. Ví dụ hoán vị: ứng viên theo vị trí và khử trùng

Với danh sách giá trị `[A,A,B]`, nếu coi mỗi **vị trí** là một phần tử khác nhau, có 3! = 6 hoán vị của các vị trí. Nhưng nếu chỉ cần những dãy **giá trị** phân biệt, đáp án gồm:

~~~text
[A, A, B]
[A, B, A]
[B, A, A]
~~~

Quy trình:

1. Sắp giá trị để những bản sao bằng nhau đứng cạnh nhau.
2. Dùng `used[i]` để đánh dấu **vị trí nguồn i** đã được chọn vào tiền tố.
3. Sinh ứng viên i chưa dùng.
4. Bỏ ứng viên có cùng giá trị với bản sao trước đó **nếu bản sao trước chưa được dùng trong tiền tố**:

~~~text
if i > 0 and values[i] == values[i-1] and not used[i-1]:
    skip
~~~

5. Đánh dấu `used[i]=true`, thêm `values[i]` vào `current`, đệ quy, sau đó `current.remove(last)` và `used[i]=false`.

**Vì sao cần điều kiện `!used[i-1]`?** Nếu cả hai bản sao bằng nhau đều chưa được dùng, chọn bản sao sau ở độ sâu này tạo nhánh tương đương với chọn bản sao trước; có thể bỏ một nhánh để tránh kết quả trùng. Nhưng nếu bản sao trước đã nằm trong tiền tố, bản sao sau **phải được phép chọn**, nếu không chẳng bao giờ sinh được `[A,A,B]`.

Không được đơn giản bỏ mọi phần tử bằng phần tử kề trước, vì như vậy sẽ **mất lời giải cần nhiều bản sao**. Quy tắc khử trùng phụ thuộc vào việc đã **sắp giá trị** và `used` gắn với **chỉ số**, không chỉ gắn với giá trị.

### Snapshot kết quả

Khi `current=[A,B,A]` đạt độ dài 3, phải lưu **bản sao**:

~~~java
solutions.add(List.copyOf(current));
~~~

Nếu dùng `solutions.add(current)` với `current` là `ArrayList` mutable dùng lại cho mọi nhánh, những phần tử trong `solutions` có thể cùng trỏ tới một đối tượng. Sau nhiều lần undo, kết quả cũ bị thay đổi hoặc thành danh sách rỗng. Bản sao là một phần của tính đúng khi thuật toán **liệt kê** lời giải.

## 7. Java 17+: một chương trình chạy được

Ví dụ dưới đây cài đặt cả **N-Queens** và **hoán vị giá trị không trùng**. Các ứng viên được duyệt theo thứ tự tăng và đầu vào hoán vị được sắp, nên stdout có thứ tự xác định.

Trong ví dụ, hàm `nQueens` giới hạn `1<=n<=12` để tránh chủ động liệt kê số kết quả cực lớn; đây là **giới hạn thực hành của demo**, không phải một định lý về N-Queens.

Lưu tệp **BacktrackingChoicesDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

public class BacktrackingChoicesDemo {
    static List<int[]> nQueens(int n) {
        if (n < 1 || n > 12) {
            throw new IllegalArgumentException("n must be in [1,12]");
        }

        int[] queenAtRow = new int[n];
        Arrays.fill(queenAtRow, -1);
        boolean[] columns = new boolean[n];
        boolean[] down = new boolean[2 * n - 1];
        boolean[] up = new boolean[2 * n - 1];

        List<int[]> solutions = new ArrayList<>();
        placeQueen(0, queenAtRow, columns, down, up, solutions);
        return solutions;
    }

    private static void placeQueen(
        int row, int[] queenAtRow, boolean[] columns,
        boolean[] down, boolean[] up, List<int[]> solutions
    ) {
        int n = queenAtRow.length;
        if (row == n) {
            // Snapshot instead of storing a mutable array reference.
            solutions.add(queenAtRow.clone());
            return;
        }

        for (int col = 0; col < n; col++) {
            int d = row - col + n - 1;
            int u = row + col;

            // Check before mutating anything.
            if (columns[col] || down[d] || up[u]) {
                continue;
            }

            // Choose
            queenAtRow[row] = col;
            columns[col] = true;
            down[d] = true;
            up[u] = true;

            // Explore
            placeQueen(row + 1, queenAtRow, columns, down, up, solutions);

            // Undo every change made by this choice.
            columns[col] = false;
            down[d] = false;
            up[u] = false;
            queenAtRow[row] = -1;
        }
    }

    static List<List<String>> uniquePermutations(List<String> input) {
        Objects.requireNonNull(input, "input");
        List<String> values = new ArrayList<>(input);
        for (String value : values) {
            Objects.requireNonNull(value, "element");
        }
        Collections.sort(values);

        List<List<String>> solutions = new ArrayList<>();
        permute(values, new boolean[values.size()],
            new ArrayList<>(), solutions);
        return solutions;
    }

    private static void permute(
        List<String> values, boolean[] used,
        List<String> current, List<List<String>> solutions
    ) {
        if (current.size() == values.size()) {
            solutions.add(List.copyOf(current));
            return;
        }

        for (int i = 0; i < values.size(); i++) {
            if (used[i]) {
                continue;
            }
            if (i > 0 && values.get(i).equals(values.get(i - 1))
                    && !used[i - 1]) {
                continue;
            }

            // Choose
            used[i] = true;
            current.add(values.get(i));

            // Explore
            permute(values, used, current, solutions);

            // Undo
            current.remove(current.size() - 1);
            used[i] = false;
        }
    }

    public static void main(String[] args) {
        List<int[]> boards = nQueens(4);
        System.out.println("NQueens(4): " + boards.size());
        for (int i = 0; i < boards.size(); i++) {
            System.out.println("Board " + (i + 1) + ": "
                + Arrays.toString(boards.get(i)));
        }
        System.out.println("NQueens(2): " + nQueens(2).size());
        System.out.println("NQueens(8): " + nQueens(8).size());
        System.out.println("Unique permutations: "
            + uniquePermutations(List.of("A", "A", "B")));
        System.out.println("Empty permutation count: "
            + uniquePermutations(List.of()).size());
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac BacktrackingChoicesDemo.java
java BacktrackingChoicesDemo
~~~

**Stdout chính xác:**

~~~text
NQueens(4): 2
Board 1: [1, 3, 0, 2]
Board 2: [2, 0, 3, 1]
NQueens(2): 0
NQueens(8): 92
Unique permutations: [[A, A, B], [A, B, A], [B, A, A]]
Empty permutation count: 1
~~~

**Giải thích mã:**

- `queenAtRow[row]=col` lưu vị trí hậu theo từng hàng; các mảng `columns/down/up` dùng để **kiểm tra O(1)** trước khi đặt hậu.
- Cờ được bật trước đệ quy, rồi tắt ngay sau đệ quy. Ở trạng thái hợp lệ, không có hậu trước đó chiếm cùng cờ, nên gán lại false khi undo không phá trạng thái của hậu khác.
- `queenAtRow.clone()` bảo đảm lời giải đã lưu độc lập với các lần sửa mảng sau này.
- Mỗi lời gọi cấp cao tạo mảng cờ và kết quả mới, nên gọi lần lượt n=4, n=2, n=8 **không bị rò trạng thái**.
- Trong `uniquePermutations`, `Collections.sort` kết hợp điều kiện `!used[i-1]` bỏ các nhánh đối xứng do bản sao giá trị trùng, nhưng vẫn cho phép dùng tất cả bản sao để tạo hoán vị đầy đủ.
- Với đầu vào danh sách rỗng, `current.size()==values.size()==0` đúng ngay tại gốc. Theo quy ước toán học có **một hoán vị rỗng**, nên danh sách kết quả có kích thước 1. N-Queens n=0 lại bị từ chối theo chính sách của ví dụ.
- Hàm hoán vị từ chối `null` ở danh sách và phần tử để thao tác so sánh/snapshot có hợp đồng rõ; `nQueens` từ chối n ngoài giới hạn minh họa.
- Các mảng và danh sách tạm thời là biến cục bộ của mỗi lời gọi cấp cao, không dùng trạng thái toàn cục mutable; điều này giúp thử nhiều bài riêng biệt dễ kiểm chứng.

## 8. Cắt tỉa (*pruning*) không được làm mất lời giải

**Cắt tỉa hợp lệ** phải loại một tiền tố mà **không tồn tại cách mở rộng** nào đáp ứng bài toán. Có các nhóm phổ biến:

### 8.1. Vi phạm ràng buộc không thể sửa về sau

N-Queens: hai hậu cùng cột hoặc đường chéo sẽ tiếp tục xung đột, vì bước tiếp theo không di chuyển hậu cũ. Hoán vị: một vị trí nguồn bị chọn hai lần là sai, không thể “chọn thêm” để sửa.

Đây là những ràng buộc **không thể hồi phục chỉ bằng mở rộng tiền tố** (*monotone invalidity*), rất phù hợp với quay lui.

### 8.2. Không đủ tài nguyên để hoàn tất

Ví dụ phải chọn đúng k phần tử nhưng số ứng viên chưa xét nhỏ hơn số lượng còn thiếu: chắc chắn không thể hoàn thành. Có thể loại nhánh mà không làm mất lời giải.

Với bài toán đường đi có giới hạn số bước, nếu đã dùng hết bước mà chưa đạt đích, cũng có thể kết thúc nhánh; nhưng cần cẩn thận phân biệt **đúng K bước** và **không quá K bước**.

### 8.3. Cận cho mục tiêu tối ưu

Nếu đang **tối đa hóa** và đã có điểm tốt nhất `best`, hãy tính **cận trên hợp lệ** `upperBound(state)` cho mọi lời giải có thể kéo dài từ trạng thái hiện tại. Khi:

\[
upperBound(state)\le best,
\]

nhánh không thể cải thiện giá trị tốt nhất nên có thể bỏ **nếu chỉ cần một phương án tối ưu hoặc một giá trị tối ưu**. Nếu đề yêu cầu **liệt kê tất cả phương án cùng giá trị tối ưu**, cắt khi bằng nhau có thể bỏ mất lời giải cần liệt kê.

Trong **tối thiểu hóa**, có thể dùng cận dưới `lowerBound(state)` và loại nhánh khi nó không thể tốt hơn phương án hiện tại.

### Phản ví dụ: tổng có số âm

Giả sử tìm tổng chính xác `target=5`, đã chọn số 8 nhưng còn số -3. Nếu cắt nhánh khi `sum>target`, ta bỏ mất phương án `8+(-3)=5`.

Vì vậy, điều kiện “tổng vượt target thì loại” chỉ an toàn nếu mọi phần tử còn được thêm **không âm** và không có phép giảm/hủy khác. **Không được biến một heuristic thành phép cắt tỉa đúng** khi chưa chứng minh.

## 9. Hoàn tác tại chỗ, sao chép trạng thái và lưu nhật ký thay đổi

Có ba cách tổ chức trạng thái phổ biến.

**Sửa tại chỗ rồi undo:** dùng một `current`, một `used[]` và sửa trực tiếp. Chi phí bộ nhớ làm việc nhỏ, nhưng cần cặp update/undo đầy đủ. Đây là cách trong chương trình Java.

**Sao chép cho mỗi nhánh:** tạo `childState=copy(parentState)`, áp dụng lựa chọn lên bản sao rồi đệ quy. Trạng thái cha không thay đổi nên không cần undo, nhưng việc sao chép có thể đắt khi cây tìm kiếm lớn.

**Nhật ký thay đổi:** nếu một lựa chọn sửa nhiều biến không thể hoàn tác bằng cách gán một giá trị mặc định, lưu `(địa chỉ,giá trị cũ)` cho từng thay đổi và phục hồi theo **thứ tự ngược**. Đây là cách an toàn cho các cấu trúc có thao tác lan truyền ràng buộc phức tạp.

Nếu một đại lượng là **tham số giá trị** như `depth`, `remaining` hay `sum`, có thể truyền `recurse(depth+1,remaining-cost,sum+gain)` và không cần hoàn tác riêng các tham số nguyên đó. Nhưng **mảng hoặc đối tượng mutable** được truyền bằng tham chiếu trong Java vẫn được chia sẻ giữa các lời gọi; Java không tự sao chép mảng khi truyền vào hàm.

### Undo và reset khác nhau

- **Undo:** khôi phục đúng một lựa chọn khi trở về **cha trong cây tìm kiếm**.
- **Reset:** khởi tạo toàn bộ trạng thái của một **lượt giải mới**.

Một thuật toán tốt dùng undo ở mỗi mức, còn lượt gọi cấp cao tạo trạng thái ban đầu riêng. Dùng `Arrays.fill(used,false)` khi quay về một mức sâu thường là **sai**, vì thao tác đó xóa luôn lựa chọn hợp lệ của các mức cha.

## 10. Điều kiện dừng và lưu lời giải

Khi đã xây đủ quyết định:

~~~text
if complete(state):
    if satisfiesFinalConstraints(state):
        saveSnapshot(state)
    return
~~~

Tùy yêu cầu:

- **Kiểm tra tồn tại:** dừng ở lời giải đầu tiên; phải hoàn tác trước khi trả nếu hợp đồng bảo toàn trạng thái.
- **Đếm:** tăng bộ đếm tại mỗi lá hợp lệ; chú ý khả năng số lời giải vượt kiểu `long`.
- **Liệt kê:** lưu bản sao mảng/danh sách; nhớ chi phí đầu ra có thể rất lớn.
- **Tối ưu:** cập nhật `best` và chỉ lưu phương án tốt nhất hoặc nhiều phương án hòa nếu đề yêu cầu.

**Lỗi dừng sớm:**

~~~text
apply(choice)
if backtrack() tìm thấy:
    return true        // undo bị bỏ qua
undo(choice)
~~~

Nếu sau đó người gọi còn sử dụng `state`, hàm trả về true nhưng cờ `used` có thể chưa được phục hồi. Thay bằng:

~~~text
apply(choice)
found = backtrack()
undo(choice)
if found:
    return true
~~~

hoặc dùng `finally` khi cần bảo đảm phục hồi cả trong trường hợp ngoại lệ.

## 11. Chứng minh đúng cho khuôn quay lui tổng quát

**Tính hợp lệ (soundness).** Trạng thái cơ sở hợp lệ. Mỗi bước chỉ áp dụng `choice` khi `isValid` đúng, và bất biến vẫn được giữ. Khi ghi nhận lá, chương trình đã chọn đủ quyết định và kiểm tra tất cả điều kiện cuối ⇒ mọi kết quả xuất ra là lời giải hợp lệ.

**Tính đầy đủ (completeness).** Lấy một lời giải hợp lệ bất kỳ. Ở mỗi độ sâu, quyết định tương ứng của lời giải ấy phải nằm trong `generateChoices`. Vì lời giải hợp lệ, các tiền tố của nó không thể bị loại bởi phép cắt tỉa **đúng**. Do đó thuật toán có một đường đi tạo ra lời giải ấy.

**Không trùng lặp (khi cần).** Nếu mỗi lời giải có duy nhất một chuỗi lựa chọn, kết quả không trùng. Khi có nhiều vị trí mang cùng giá trị như `[A,A,B]`, cần quy tắc đại diện (sắp + bỏ bản sao kề khi bản sao trước chưa dùng) để mọi dãy **giá trị** chỉ có một đường sinh.

**Tính độc lập của nhánh.** Sau đệ quy và undo, trạng thái quay về đúng cha; các lựa chọn anh em không ảnh hưởng nhau. Nếu thiếu điều này, các lập luận hợp lệ/đầy đủ có thể thất bại vì điều kiện kiểm tra dựa trên trạng thái bị ô nhiễm.

Đây là bốn tiêu chuẩn khác nhau. Một chương trình có thể **chỉ sinh lời giải hợp lệ nhưng sinh thiếu**, hoặc **sinh đủ nhưng ghi trùng**, hoặc **ban đầu đúng nhưng gọi lần thứ hai sai** do trạng thái còn sót.

## 12. Phân tích độ phức tạp

Quay lui không có một độ phức tạp chung cố định. Xét:

\[
\text{Tổng thời gian}
\approx
\sum_{\text{nút được thăm}}
(\text{số lựa chọn phải thử}\times\text{chi phí kiểm tra})
+
\text{chi phí lưu đầu ra}.
\]

**N-Queens:** ở hàng 0 có tối đa n cột, những hàng sau không thể chọn cột đã dùng. Nếu bỏ qua ràng buộc đường chéo, số tiền tố ở độ sâu d nhiều nhất \(P(n,d)=n!/(n-d)!\). Tổng nút có cận \(O(n!)\); vòng lặp ở mỗi nút thử tới n cột và kiểm tra O(1). Cận trên đơn giản là **O(n·n!)** thời gian (kể cả chi phí lưu mỗi lời giải dài n với số lời giải không vượt n!). Bộ nhớ làm việc của mảng cờ, cột và stack là **O(n)**; nếu lưu S lời giải cần thêm **O(nS)**.

**Hoán vị n phần tử phân biệt:** có n! kết quả, mỗi bản sao dài n nên chỉ riêng việc xuất tất cả đã cần \(\Omega(n\cdot n!)\). Thuật toán quét n chỉ số ở mỗi mức cho cận **O(n·n!)**, bỏ qua chi phí so sánh chuỗi khi chúng không phải O(1). Bộ nhớ làm việc **O(n)** cho `used`, `current`, stack, ngoài bản sao/sắp input và kết quả.

**Hoán vị có giá trị trùng:** nếu các giá trị phân biệt có số lần xuất hiện \(c_1,c_2,\ldots,c_m\) thì số hoán vị giá trị là \(n!/(c_1!c_2!\cdots c_m!)\). Cắt nhánh đối xứng giảm số kết quả, nhưng chi phí vòng lặp ở mỗi nút vẫn cần được tính; đừng dùng một con số thời gian độc lập khỏi cấu trúc cây và phân bố trùng.

**Xuất kết quả:** nếu không cần mọi lời giải, có thể chỉ đếm, tìm một lời giải, stream qua callback hoặc giữ phương án tốt nhất. Đây là cách giảm bộ nhớ lưu kết quả, nhưng không nhất thiết giảm độ khó của việc tìm kiếm.

## 13. Phương pháp kiểm thử thực hành

Đầu vào nhỏ nên được kiểm bằng **oracle** đơn giản:

| Ca kiểm thử | Kết quả cần có |
|---|---|
| N-Queens n=1 | 1 lời giải `[0]` |
| N-Queens n=2,3 | 0 lời giải |
| N-Queens n=4 | Đúng hai mảng `[1,3,0,2]`, `[2,0,3,1]` |
| N-Queens n=8 | 92 lời giải |
| Mỗi lời giải N-Queens | Không trùng cột, không trùng hiệu/tổng hàng–cột |
| Hoán vị `[A,B,C]` | 6 dãy phân biệt, mỗi dãy dài 3 |
| Hoán vị `[A,A,B]` | Chính xác 3 dãy phân biệt |
| Hoán vị `[A,A,A]` | 1 dãy `[A,A,A]` |
| Hoán vị rỗng | 1 hoán vị rỗng theo quy ước |
| Gọi hàm nhiều lần | Kết quả không phụ thuộc lời gọi trước |
| Đường đệ quy bị loại sớm | Trạng thái cha không đổi |
| Đầu ra đã lưu | Không bị biến đổi bởi undo của các nhánh sau |

Có thể thêm các **assertion kiểm tra trạng thái trước và sau một lựa chọn** trong phiên bản debug: kích thước `current` được phục hồi, số cờ true phù hợp độ sâu, tổng cộng trở về đúng giá trị cũ. Thử nhiều thứ tự sinh lựa chọn khác nhau: tập lời giải phải giữ nguyên (nếu việc sắp xếp/khử trùng vẫn hợp lệ), chỉ thay đổi **thứ tự xuất ra**.

## 14. Những lỗi thường gặp

1. Sinh thiếu lựa chọn làm bỏ sót lời giải hợp lệ.
2. Kiểm tra quá mạnh, cắt nhánh dù còn cách hoàn tất thỏa điều kiện.
3. Kiểm tra sau apply nhưng `continue` trước undo.
4. Bật nhiều cờ nhưng quên tắt một cờ khi hoàn tác.
5. Reset cả mảng cờ thay vì chỉ undo lựa chọn mới, làm xóa quyết định của cha.
6. Lưu tham chiếu `current` thay vì snapshot vào danh sách kết quả.
7. Nhầm độ sâu và số phần tử đã chọn, dẫn đến điều kiện dừng sai.
8. Ghi lời giải ngay tại mọi tiền tố, dù yêu cầu phương án đủ n phần tử.
9. Cấm mọi phần tử trùng, kể cả bản sao phải được dùng trong một hoán vị.
10. Không chống trùng khi đề cần liệt kê dãy giá trị phân biệt.
11. Áp quy tắc chống trùng theo phần tử kề mà quên sắp dữ liệu.
12. Dùng `used` theo giá trị thay vì theo vị trí khi các giá trị trùng nhau.
13. Dừng sớm mà bỏ qua undo, làm rò trạng thái cho người gọi.
14. Không khởi tạo lại biến dùng chung giữa các lượt giải.
15. Đưa một kiểm tra chỉ quyết định được khi hoàn tất vào điều kiện loại tiền tố sai.
16. Phân tích chỉ chi phí kiểm tra O(1) mà bỏ qua số nút theo hàm mũ/giai thừa.
17. Quên chi phí snapshot và bộ nhớ chứa mọi kết quả.
18. Truyền mảng Java vào hàm rồi tưởng mảng được sao chép tự động.
19. Dùng trạng thái mutable chung qua nhiều luồng mà không có cơ chế cách ly.
20. Tối ưu bằng heuristic nhưng không chứng minh điều kiện cắt tỉa an toàn.

## 15. Quy trình thiết kế lời giải quay lui mới

1. Xác định **một lời giải đầy đủ** gồm những quyết định nào.
2. Chọn **độ sâu** và phát biểu ý nghĩa của tiền tố tại độ sâu đó.
3. Liệt kê **toàn bộ lựa chọn ứng viên** cho một nút.
4. Phân biệt **ràng buộc phát hiện được ngay** với ràng buộc chỉ xác minh lúc hoàn chỉnh.
5. Xác định những dữ liệu phụ trợ cần để **kiểm tra nhanh**.
6. Viết **apply** và **undo** cạnh nhau, bảo đảm khôi phục mọi thay đổi.
7. Viết điều kiện **dừng**, xác định có cần snapshot hay chỉ trả boolean/đếm.
8. Chứng minh **bất biến trạng thái** ở đầu/cuối lời gọi.
9. Chứng minh **nhánh bị loại thật sự không thể chứa lời giải**, hoặc được loại vì đối xứng theo đại diện duy nhất.
10. Kiểm tra **tính đầy đủ**: một lời giải bất kỳ có đường đi sinh ra nó không?
11. Ước lượng số nút, chi phí kiểm tra, stack, bộ nhớ và lượng đầu ra.
12. Thử đầu vào nhỏ, giá trị trùng, trạng thái vô nghiệm, gọi lặp và dừng sớm.

Một khuôn bất biến nên ghi ngay trong tài liệu thiết kế:

> “Tại `backtrack(d)`, `current` đại diện chính xác d quyết định hợp lệ và các cờ/biến tổng phản ánh đúng tiền tố đó. Khi lời gọi trả về, dữ liệu mutable thuộc người gọi được bảo toàn.”

## 16. Bài tập tự kiểm tra

**Bài 1.** Sinh hoán vị từ `[1,2,3]`, hiện `current=[2,1]`. Lựa chọn tiếp theo là gì, và undo phải làm gì?

*Đáp án:* Chọn **3**, rồi xóa 3 khỏi cuối danh sách và đặt `used` của vị trí 3 về false khi quay lui.

**Bài 2.** Trong N-Queens n=4, ô (r=2,c=1) có hai chỉ số đường chéo nào?

*Đáp án:* `down=2-1+4-1=4` và `up=2+1=3`. Ngoài cờ cột 1, phải kiểm tra cả hai cờ đường chéo.

**Bài 3.** Nếu chỉ xóa quân hậu khỏi `queenAtRow` nhưng không xóa `downUsed`, lỗi gì có thể xảy ra?

*Đáp án:* Các nhánh sau tưởng đường chéo cũ vẫn bận, **loại sai một số lựa chọn hợp lệ** và có thể thiếu lời giải.

**Bài 4.** Vì sao điều kiện chống trùng hoán vị `[A,A,B]` phải có `!used[i-1]`?

*Đáp án:* Khi bản sao trước đã dùng trong tiền tố, bản sao sau **phải được chọn được** để sinh lời giải chứa cả hai A; chỉ bỏ bản sao sau khi bản sao trước chưa dùng ở cùng mức quyết định.

**Bài 5.** Có an toàn khi dùng `solutions.add(current)` với một danh sách mutable tái sử dụng không?

*Đáp án:* **Không.** Phải dùng bản sao như `List.copyOf(current)` hoặc `new ArrayList<>(current)` để tránh undo làm đổi kết quả đã lưu.

**Bài 6.** Với bài tìm tổng chính xác 5, đã chọn 8 và còn số -3, có thể cắt nhánh chỉ vì tổng hiện tại lớn hơn 5 không?

*Đáp án:* **Không**, vì `8+(-3)=5`. Cần chứng minh cận an toàn trước khi cắt.

**Bài 7.** N-Queens n=4 có bao nhiêu lời giải khi không gộp đối xứng?

*Đáp án:* **2**: `[1,3,0,2]` và `[2,0,3,1]`.

**Bài 8.** Nếu chỉ cần một lời giải và muốn dừng sớm, điều gì có thể sai với `apply; if recurse() return true; undo`?

*Đáp án:* Nhánh trả true **bỏ qua undo**, để lại trạng thái đã sửa. Hãy lấy kết quả đệ quy, undo rồi mới return hoặc dùng `finally` tùy hợp đồng.

**Bài 9.** Vì sao N-Queens có kiểm tra cột O(1) nhưng toàn thuật toán vẫn có thể rất tốn thời gian?

*Đáp án:* O(1) chỉ là **một phép kiểm tra**; số tiền tố ứng viên có thể tăng theo hàm giai thừa. Cắt tỉa giúp giảm việc thực tế nhưng không bảo đảm thời gian đa thức.

**Bài 10.** Với đầu vào hoán vị rỗng, chương trình trả bao nhiêu hoán vị và vì sao?

*Đáp án:* **Một hoán vị rỗng**, theo quy ước tổ hợp; do điều kiện hoàn chỉnh đúng ngay ở gốc.

**Tổng kết:** Quay lui giải bài toán bằng **cây lựa chọn**: sinh ứng viên đầy đủ, kiểm tra ràng buộc đúng, áp dụng lựa chọn, đi sâu và **hoàn tác chính xác để phục hồi trạng thái cha**. Ba yêu cầu nền tảng là **không bỏ lời giải hợp lệ**, **không ghi lời giải không hợp lệ** và **không để một nhánh làm bẩn nhánh anh em**. Khi lưu lời giải phải snapshot; khi tối ưu bằng cắt tỉa cần chứng minh tính an toàn.