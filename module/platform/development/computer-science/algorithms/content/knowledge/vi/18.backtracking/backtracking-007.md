# Bài toán N quân hậu

**N quân hậu (N-Queens)** là bài toán đặt đúng **N quân hậu** trên bàn cờ **N × N** sao cho không có hai quân nào tấn công nhau. Quân hậu tấn công theo hàng, cột và hai hướng đường chéo. Đây là bài toán kinh điển của **quay lui (backtracking)**: thử đặt một quân, cắt nhánh nếu vi phạm ràng buộc, đi sâu khi hợp lệ và **hoàn tác** lựa chọn để thử cách khác.

Bài học trình bày mô hình trạng thái, ràng buộc theo đường chéo, đệ quy theo hàng, chứng minh tính đúng và đầy đủ, cách đếm/giữ nghiệm, độ phức tạp, bitmask, đối xứng, những biến thể thường gặp và chương trình Java 17+ có đầu ra xác định.

## 1. Phát biểu toán học và quy ước

Các hàng và cột đánh số từ 0 tới N-1. Quân hậu ở `(r,c)` và `(x,y)` tấn công nhau khi:

~~~text
r == x                  // Cùng hàng.
OR c == y              // Cùng cột.
OR r-c == x-y          // Cùng đường chéo chính.
OR r+c == x+y          // Cùng đường chéo phụ.
~~~

Điều kiện đường chéo cũng tương đương `abs(r-x)==abs(c-y)`. Chỉ các ô bên trong bàn cờ được phép chọn.

Bài toán cơ bản cho N là **số nguyên dương**. Một số tài liệu quy ước bàn cờ N=0 có một cấu hình rỗng; ví dụ Java trong bài nhận `1<=N<=14` để tập trung vào bàn cờ có quân và tránh vô tình chạy với N quá lớn. Giới hạn 14 là quyết định triển khai, không phải một định lý về N-Queens.

**Đếm cấu hình:** hai cách đặt hậu ở các tọa độ khác nhau được tính là **hai nghiệm**, kể cả khi chúng là ảnh phản chiếu hoặc xoay của nhau. Các quân hậu không phân biệt tên; đổi danh tính hai quân trên cùng một cấu hình không tạo thêm nghiệm.

### Ví dụ N=4

~~~text
Nghiệm 1:
.Q..
...Q
Q...
..Q.

Nghiệm 2:
..Q.
Q...
...Q
.Q..
~~~

Mỗi dấu `Q` là một hậu; dấu `.` là ô trống. Hai nghiệm có dãy cột theo thứ tự hàng:

~~~text
[1,3,0,2]
[2,0,3,1]
~~~

Nghiệm thứ nhất đặt ở `(0,1),(1,3),(2,0),(3,2)`. Các hiệu `r-c` lần lượt `-1,-2,2,1` và các tổng `r+c` lần lượt `1,4,2,5` đều phân biệt trong từng nhóm. Không có hai quân hậu nào tấn công nhau. N=4 có đúng **2 nghiệm** theo quy ước này.

## 2. Rút gọn cách tìm: một quân trên mỗi hàng

Có N quân và N hàng, trong khi không quân nào được cùng hàng, nên **mỗi hàng bắt buộc có đúng một quân**. Ta đặt quân ở hàng 0, sau đó hàng 1, ..., hàng N-1. Tại hàng r chỉ cần chọn cột c.

Có thể biểu diễn toàn bộ lời giải bằng mảng:

`placement[r]=c`: quân hậu của hàng r ở cột c.

Vì các quân không được chung cột, một lời giải hoàn chỉnh có đúng N cột khác nhau. Dãy `placement` là một **hoán vị** của các cột 0..N-1. Do đó số ứng viên hoàn chỉnh trước khi xét đường chéo chỉ tối đa N!, thay vì thử chọn N ô tùy ý trong N² ô.

Lợi ích của backtracking là **cắt nhánh ngay tại một tiền tố sai**: nếu đã đặt 3 quân mà hàng thứ tư không có cột an toàn, không cần sinh đầy đủ các bàn cờ còn lại từ tiền tố đó. Thuật toán quay về lựa chọn trước để thử cột khác.

Không cần có lựa chọn “bỏ qua hàng” trong bài cổ điển: nếu bỏ một hàng sẽ không thể đặt N hậu trên N hàng mà mỗi hàng chỉ có một quân. Với các biến thể chỉ đặt K hậu, K<N, điều này phải thay đổi.

## 3. Mã hóa cột và hai hướng đường chéo

Một cách chậm là thử ứng viên `(r,c)` và so sánh với tất cả r quân đã đặt, tốn O(r) cho mỗi lần kiểm tra. Có thể thay bằng ba mảng Boolean:

- `usedCol[c]`: cột c đã có hậu.
- `usedDiagDown[r-c+N-1]`: đường chéo chính đã có hậu.
- `usedDiagUp[r+c]`: đường chéo phụ đã có hậu.

Chỉ số:

~~~text
r-c thuộc [-(N-1), +(N-1)]
r-c+N-1 thuộc [0, 2N-2]

r+c thuộc [0, 2N-2]
~~~

Vì vậy **hai mảng chéo đều phải dài 2N-1**, còn mảng cột dài N.

Ví dụ với N=4, ô `(0,1)` có `down=0-1+3=2`, `up=0+1=1`. Ô `(1,2)` có `down=1-2+3=2` nên cùng đường chéo chính với ô trước và không được đặt hậu đồng thời.

Phép kiểm tra một ứng viên:

~~~text
safe(row,col) =
    NOT usedCol[col]
    AND NOT usedDiagDown[row-col+N-1]
    AND NOT usedDiagUp[row+col]
~~~

Chỉ cần ba phép tra mảng, **O(1)** thời gian. Không cần `usedRow` vì bất biến thuật toán đã bảo đảm đúng một quân cho mỗi hàng được xử lý.

## 4. Giả mã quay lui

~~~text
ALGORITHM N_QUEENS(N)
    REQUIRE N >= 1

    usedCol[0..N-1] <- false
    usedDiagDown[0..2N-2] <- false
    usedDiagUp[0..2N-2] <- false
    placement[0..N-1] <- unassigned
    count <- 0

    PROCEDURE SEARCH(row)
        IF row = N THEN
            count <- count + 1
            RECORD_BOARD_IF_NEEDED(placement)
            RETURN
        END IF

        FOR col FROM 0 TO N-1 DO
            d1 <- row-col+N-1
            d2 <- row+col
            IF usedCol[col] OR
               usedDiagDown[d1] OR usedDiagUp[d2] THEN
                CONTINUE
            END IF

            // CHỌN.
            placement[row] <- col
            usedCol[col] <- true
            usedDiagDown[d1] <- true
            usedDiagUp[d2] <- true

            // KHÁM PHÁ.
            SEARCH(row+1)

            // HOÀN TÁC.
            usedCol[col] <- false
            usedDiagDown[d1] <- false
            usedDiagUp[d2] <- false
            placement[row] <- unassigned
        END FOR
    END PROCEDURE

    SEARCH(0)
    RETURN count
END ALGORITHM
~~~

**Chọn:** kiểm tra cả ba ràng buộc, đặt quân và đánh dấu.

**Khám phá:** gọi đệ quy cho hàng tiếp theo. Nếu hàng đó không có cột hợp lệ, nhánh tự kết thúc và trở về.

**Hoàn tác:** gỡ đúng quân vừa đặt và trả ba mảng về trạng thái cũ. Đây là bước bắt buộc để những nhánh anh em độc lập với nhau.

**Kết thúc một nghiệm:** chỉ khi `row==N` mới được tăng bộ đếm. Một tiền tố đặt vài quân hợp lệ chưa được coi là một bàn cờ hoàn chỉnh.

### Mô phỏng một nhánh

N=4, chọn cột 0 ở hàng 0, sau đó cột 2 ở hàng 1:

~~~text
Q...
..Q.
....
....
~~~

Ở hàng 2, cột 0 đã dùng, cột 2 đã dùng, cột 1 và 3 bị hậu hàng 1 tấn công theo đường chéo. Không còn ứng viên. Thuật toán quay về hàng 1, xóa hậu `(1,2)` và thử cột 3. Nếu toàn bộ nhánh hàng 0 cột 0 thất bại thì chuyển sang cột 1, cuối cùng tìm được nghiệm `[1,3,0,2]` rồi `[2,0,3,1]`.

Cắt nhánh sớm giúp tránh thử tiếp các hàng dưới của một tiền tố đã không còn khả năng hoàn thiện.

## 5. Chứng minh tính đúng đắn

### Bất biến ở `SEARCH(row)`

1. Những hàng `0..row-1` mỗi hàng có đúng một quân, các hàng sau chưa đặt.
2. Không có hai quân đang đặt tấn công nhau.
3. Ba mảng dấu phản ánh chính xác các cột và đường chéo đã được sử dụng.
4. `placement[0..row-1]` khớp với vị trí các quân đang có.

**Cơ sở:** tại hàng 0 chưa có quân và các dấu đều false.

**Bước duy trì:** một ứng viên chỉ được chọn nếu không trùng cột/đường chéo. Gắn các dấu tương ứng bảo đảm bất biến ở hàng tiếp theo. Sau khi khám phá xong, gỡ đúng các dấu vừa thêm khôi phục trạng thái cho việc thử cột kế.

**Tính hợp lệ:** mọi nghiệm chỉ được ghi tại hàng N. Theo bất biến, đã có N quân ở N hàng khác nhau, không trùng cột/đường chéo, nên chắc chắn hợp lệ.

**Tính đầy đủ:** lấy một nghiệm hợp lệ S bất kỳ. Mỗi hàng r của S có một cột `c_r`. Vòng lặp thử **tất cả cột** ở hàng r. Nếu thuật toán đang theo tiền tố đúng của S, ô `(r,c_r)` không bị tấn công bởi tiền tố S nên sẽ được nhận. Quy nạp theo hàng cho thấy thuật toán có một nhánh đến đúng S. Vì vậy không bỏ sót nghiệm.

**Không đếm trùng:** mỗi cấu hình có duy nhất một dãy `placement` theo hàng. Hai nhánh khác nhau phải khác ít nhất một cột đã chọn ở một hàng, nên không thể tạo cùng cấu hình. Mỗi cấu hình được ghi đúng một lần.

**Kết thúc:** chiều sâu đệ quy tối đa N và mỗi mức thử hữu hạn N cột. Cây tìm kiếm hữu hạn, nên thuật toán luôn dừng, kể cả khi không có nghiệm.

## 6. Số nghiệm chuẩn

Theo quy ước **đếm mọi cấu hình tọa độ**, kể cả các cấu hình đối xứng:

| N | Số nghiệm |
| ---: | ---: |
| 1 | 1 |
| 2 | 0 |
| 3 | 0 |
| 4 | 2 |
| 5 | 10 |
| 6 | 4 |
| 7 | 40 |
| 8 | 92 |
| 9 | 352 |
| 10 | 724 |
| 11 | 2.680 |
| 12 | 14.200 |
| 13 | 73.712 |
| 14 | 365.596 |

N=2 và N=3 thật sự **vô nghiệm**, không phải lỗi trả 0. N=8 có **92 cấu hình**, nhưng chỉ có **12 lớp nghiệm cơ bản** khi xem các bàn cờ quay/phản chiếu là tương đương. Hai phép đếm trả lời hai câu hỏi khác nhau.

Đối chiếu các số nhỏ giúp bắt lỗi đường chéo, hoàn tác và đếm trùng, nhưng kiểm thử hữu hạn không thay thế chứng minh ở mục trước.

## 7. Java 17+: chương trình hoàn chỉnh

Chương trình sau cung cấp:

- `solve(n,keep)`: đếm toàn bộ nghiệm bằng ba mảng Boolean, chỉ lưu tối đa `keep` bàn cờ đầu tiên.
- `countWithBitmask(n)`: đếm bằng bitmask theo cùng quy tắc nhưng cấu trúc cài đặt khác để đối chiếu.
- `verifyBoard(board)`: kiểm tra một bàn cờ có đúng một hậu mỗi hàng, không trùng cột/đường chéo.
- `main`: kiểm tra hai cách đếm cho N từ 1 đến 8, in hai nghiệm N=4 và xác nhận bản đếm N=8 không cần lưu bảng.

Tạo tệp **`NQueensDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class NQueensDemo {
    record SolutionResult(long count, List<List<String>> examples) {}

    private static void checkN(int n) {
        if (n < 1 || n > 14) {
            throw new IllegalArgumentException("Use 1 <= n <= 14");
        }
    }

    private static final class Backtracker {
        final int n;
        final int keep;
        final boolean[] usedCol;
        final boolean[] usedDiagDown;
        final boolean[] usedDiagUp;
        final int[] placement;
        final List<List<String>> examples = new ArrayList<>();
        long count = 0L;

        Backtracker(int n, int keep) {
            this.n = n;
            this.keep = keep;
            usedCol = new boolean[n];
            usedDiagDown = new boolean[2 * n - 1];
            usedDiagUp = new boolean[2 * n - 1];
            placement = new int[n];
            Arrays.fill(placement, -1);
        }

        void search(int row) {
            if (row == n) {
                count++;
                if (examples.size() < keep) {
                    examples.add(board());
                }
                return;
            }

            for (int col = 0; col < n; col++) {
                int down = row - col + n - 1;
                int up = row + col;

                if (usedCol[col] ||
                        usedDiagDown[down] || usedDiagUp[up]) {
                    continue;
                }

                placement[row] = col;
                usedCol[col] = true;
                usedDiagDown[down] = true;
                usedDiagUp[up] = true;

                search(row + 1);

                usedCol[col] = false;
                usedDiagDown[down] = false;
                usedDiagUp[up] = false;
                placement[row] = -1;
            }
        }

        List<String> board() {
            List<String> rows = new ArrayList<>();
            for (int r = 0; r < n; r++) {
                char[] line = new char[n];
                Arrays.fill(line, '.');
                line[placement[r]] = 'Q';
                rows.add(new String(line));
            }
            return List.copyOf(rows);
        }
    }

    public static SolutionResult solve(int n, int keep) {
        checkN(n);
        if (keep < 0) {
            throw new IllegalArgumentException("Negative keep");
        }
        Backtracker bt = new Backtracker(n, keep);
        bt.search(0);
        return new SolutionResult(bt.count, List.copyOf(bt.examples));
    }

    private static long countBits(
            long cols, long attackedLeft, long attackedRight,
            long all) {
        if (cols == all) {
            return 1L;
        }

        long available = all &
                ~(cols | attackedLeft | attackedRight);
        long total = 0L;

        while (available != 0L) {
            long bit = available & -available;
            available -= bit;

            total += countBits(
                    cols | bit,
                    ((attackedLeft | bit) << 1) & all,
                    ((attackedRight | bit) >>> 1) & all,
                    all);
        }
        return total;
    }

    public static long countWithBitmask(int n) {
        checkN(n);
        long all = (1L << n) - 1L;
        return countBits(0L, 0L, 0L, all);
    }

    public static boolean verifyBoard(List<String> board) {
        if (board == null || board.isEmpty()) {
            return false;
        }
        int n = board.size();
        boolean[] cols = new boolean[n];
        boolean[] down = new boolean[2 * n - 1];
        boolean[] up = new boolean[2 * n - 1];

        for (int r = 0; r < n; r++) {
            String line = board.get(r);
            if (line == null || line.length() != n) {
                return false;
            }
            int queens = 0;

            for (int c = 0; c < n; c++) {
                char symbol = line.charAt(c);
                if (symbol == '.') {
                    continue;
                }
                if (symbol != 'Q') {
                    return false;
                }

                queens++;
                int d1 = r - c + n - 1;
                int d2 = r + c;
                if (cols[c] || down[d1] || up[d2]) {
                    return false;
                }
                cols[c] = true;
                down[d1] = true;
                up[d2] = true;
            }

            if (queens != 1) {
                return false;
            }
        }
        return true;
    }

    public static void main(String[] args) {
        for (int n = 1; n <= 8; n++) {
            SolutionResult result = solve(n, 0);
            long byBits = countWithBitmask(n);
            if (result.count() != byBits) {
                throw new AssertionError("Mismatch at N=" + n);
            }
            System.out.println("n=" + n +
                    " count=" + result.count());
        }

        SolutionResult four = solve(4, 2);
        System.out.println("first4=" + four.examples().get(0));
        System.out.println("second4=" + four.examples().get(1));
        System.out.println("verifyFirst=" +
                verifyBoard(four.examples().get(0)));
        System.out.println("n8Bitmask=" + countWithBitmask(8));
        System.out.println("n8Stored=" + solve(8, 0).examples().size());
    }
}
~~~

Biên dịch/chạy với JDK 17 trở lên:

~~~bash
javac NQueensDemo.java
java NQueensDemo
~~~

**Đầu ra xác định:**

~~~text
n=1 count=1
n=2 count=0
n=3 count=0
n=4 count=2
n=5 count=10
n=6 count=4
n=7 count=40
n=8 count=92
first4=[.Q.., ...Q, Q..., ..Q.]
second4=[..Q., Q..., ...Q, .Q..]
verifyFirst=true
n8Bitmask=92
n8Stored=0
~~~

`first4` và `second4` là hai bàn cờ hợp lệ N=4 khi thử cột tăng dần. `verifyFirst=true` xác nhận bảng mẫu đầu tiên không vi phạm luật. `n8Bitmask=92` khớp bộ đếm mảng Boolean. `n8Stored=0` **không có nghĩa không có nghiệm**: `solve(8,0)` vẫn đếm đủ 92 nghiệm, nhưng không cấp bộ nhớ lưu từng bảng mẫu.

Mỗi bảng mẫu được tạo thành danh sách các chuỗi mới khi thấy nghiệm; không giữ tham chiếu trực tiếp tới mảng `placement` mutable. Điều này tránh việc các nghiệm đã lưu bị thay đổi sau khi thuật toán quay lui.

## 8. Hiểu bitmask thay cho mảng Boolean

Bitmask sử dụng N bit thấp của kiểu `long` để biểu diễn các cột:

- `cols`: các cột đã được dùng.
- `attackedLeft`: các cột đang bị đường chéo theo hướng dịch trái tấn công.
- `attackedRight`: các cột đang bị đường chéo theo hướng dịch phải tấn công.
- `all=(1L<<n)-1`: mask có N bit 1 hợp lệ.

Cột an toàn tại hàng hiện tại:

~~~text
available = all & ~(cols | attackedLeft | attackedRight)
~~~

Lấy bit 1 thấp nhất bằng `bit=available & -available`, rồi loại nó khỏi tập ứng viên bằng `available-=bit`. Sau khi chọn, cập nhật cho hàng sau:

~~~text
nextCols  = cols | bit
nextLeft  = ((attackedLeft | bit) << 1) & all
nextRight = ((attackedRight | bit) >>> 1) & all
~~~

Tại sao dịch? Quân ở cột c của hàng hiện tại tấn công cột `c-1` và `c+1` ở hàng kế. Trong biểu diễn nhị phân, dịch trái một vị trí tương ứng tăng chỉ số cột, dịch phải một vị trí tương ứng giảm chỉ số cột. Dùng `&all` để loại bit ngoài bàn cờ.

Ví dụ N=4, chọn cột 1 ở hàng 0:

~~~text
all = 1111
bit = 0010

nextCols  = 0010
nextLeft  = 0100
nextRight = 0001

available at row 1 = 1111 & ~(0010 | 0100 | 0001)
                   = 1000
~~~

Chỉ cột 3 còn hợp lệ, đúng với hai quân đầu của nghiệm `[1,3,0,2]`.

**Ưu/nhược điểm:** mảng Boolean dễ giải thích/debug và không phụ thuộc số bit `long`. Bitmask sinh trực tiếp các cột an toàn, thường giảm hằng số chạy, nhưng cần hiểu thao tác nhị phân và giới hạn độ rộng kiểu số. Cả hai vẫn là **quay lui**, chỉ khác cách biểu diễn và xét ứng viên.

## 9. Độ phức tạp

Nếu chỉ yêu cầu các cột không trùng, số dãy cột hoàn chỉnh là **N!**. Ở độ sâu k có nhiều nhất:

`P(N,k)=N!/(N-k)!`

tiền tố hợp lệ theo cột. Tổng số tiền tố có chặn trên O(N!). Bản Boolean xét tối đa N cột tại mỗi nút, với O(1) kiểm tra mỗi cột. Vì vậy một chặn trên an toàn của thời gian tìm kiếm là **O(N·N!)**, chưa tính tạo bảng nghiệm. Ràng buộc đường chéo thường cắt nhiều nhánh, nhưng không biến bài toán thành thuật toán đa thức.

Bộ nhớ phụ của ba mảng đánh dấu, `placement` và ngăn xếp đệ quy sâu tối đa N là **O(N)**. Ở bản bitmask, mỗi frame truyền vài giá trị `long`, nhưng ngăn xếp vẫn có N frame, nên tổng bộ nhớ tìm kiếm vẫn là **O(N)**.

Nếu cần lưu `K` bàn cờ ở dạng N chuỗi, mỗi chuỗi N ký tự, phần đầu ra thêm **O(K·N²)** thời gian dựng và bộ nhớ. Nếu chỉ đếm, có thể đặt `keep=0` và không lưu bàn cờ nào. Trên N rất lớn, số nghiệm còn có thể vượt phạm vi kiểu đếm nếu không được giới hạn, cần lựa chọn kiểu số phù hợp.

**N! không phải số nghiệm thực:** đó là giới hạn số hoán vị khi chưa loại đường chéo. N=8 chỉ có 92 nghiệm dù phải thử nhiều nhánh trung gian hơn 92.

## 10. Đối xứng và tối ưu khi chỉ cần đếm

Phản chiếu trái–phải biến một bàn cờ hợp lệ thành một bàn cờ hợp lệ. Với bàn cờ cổ điển không có ô cấm, những nghiệm có quân đầu tại cột c tương ứng một-một với nghiệm có quân đầu tại cột `N-1-c`.

- N **chẵn**: các cột hàng đầu ghép thành cặp khác nhau, có thể chỉ duyệt nửa trái rồi nhân đôi số nghiệm.
- N **lẻ**: cột giữa phản chiếu về chính nó. Các nghiệm bắt đầu ở cột giữa phải được **đếm riêng**, không nhân đôi cùng nửa trái.
- Nếu **liệt kê mọi bảng**, chỉ nhân đôi số đếm không đủ: cần thực sự tạo các bảng phản chiếu bị bỏ.
- Với **ô bị cấm hoặc hậu cố định** không đối xứng, phép đối ứng có thể không còn đúng.
- Nếu yêu cầu **nghiệm cơ bản**, phải gộp tất cả phép quay/phản chiếu bằng một phép chuẩn hóa, không đơn giản chia mọi số nghiệm cho 8, vì có cấu hình có đối xứng nội tại.

Chương trình Java giữ đủ nhánh, nên đếm N=4 ra 2 và N=8 ra 92 mà không phụ thuộc tối ưu đối xứng.

## 11. Biến thể thường gặp

**Ô cấm:** thêm điều kiện `!blocked[row][col]` khi thử đặt hậu. Mọi quy tắc cột và đường chéo giữ nguyên, nhưng tối ưu đối xứng phải kiểm tra mẫu ô cấm.

**Hậu cố định:** lưu `fixedCol[row]` nếu hàng đã được gán, chỉ thử đúng cột đó; trước khi chạy cần xác minh các quân cố định không xung đột. Không đặt thêm quân thứ hai vào một hàng đã cố định.

**Chỉ tìm một nghiệm:** thay đệ quy đếm bằng hàm trả Boolean. Khi tìm thấy nhánh thành công, sao chép/giữ nghiệm rồi dừng ngay, không tiếp tục duyệt hết. Trường hợp xấu vẫn có thể tốn nhiều nhánh nếu không có nghiệm.

**Chỉ đếm:** bỏ việc tạo bảng, giữ một biến đếm. Có thể dùng bitmask để giảm thao tác.

**K quân hậu trên bàn R×C:** nếu K nhỏ hơn số hàng, một số hàng có thể trống; phải có trạng thái đếm số quân đã đặt và lựa chọn bỏ qua hàng hoặc cách biểu diễn khác.

**Bàn có điểm thưởng:** nếu mỗi ô có điểm và cần tối đa tổng điểm của N hậu, nên thêm tổng điểm hiện tại và cận trên **được chứng minh** nếu muốn cắt nhánh tối ưu. Không cắt một nhánh chỉ vì điểm tạm thời thấp khi các hàng còn lại vẫn có thể cộng điểm lớn.

## 12. Những lỗi thường gặp

1. **Quên một hướng đường chéo** hoặc so sánh sai dấu `r-c`, `r+c`.
2. **Không cộng N-1 vào hiệu `r-c`** làm chỉ số âm.
3. **Dùng mảng đường chéo dài N**, trong khi cần 2N-1.
4. **Quên đánh dấu** cột hoặc đường chéo trước đệ quy.
5. **Quên hoàn tác** hoặc xóa nhầm chỉ số, làm các nhánh tác động lẫn nhau.
6. **Đếm tiền tố hợp lệ** trước khi có đủ N quân.
7. **Đặt nhiều hậu trong một hàng**, phá biểu diễn một-hàng-một-quân.
8. **Không kiểm tra cột**, vì nghĩ kiểm tra hàng và đường chéo là đủ.
9. **Lưu mảng vị trí mutable trực tiếp** vào danh sách nghiệm, khiến các nghiệm sau bị ghi đè.
10. **Dừng sớm** khi đề yêu cầu đếm mọi nghiệm.
11. **Gọi N! là số nghiệm thật** mà không kiểm tra đường chéo.
12. **Nhầm 92 cấu hình N=8 với 12 lớp nghiệm cơ bản**.
13. **Nhân đôi nhóm cột giữa của N lẻ** khi dùng đối xứng.
14. **Dùng tối ưu đối xứng với ô cấm không đối xứng**.
15. **Dịch bit sai hướng** hoặc quên chặn bit ngoài N cột.
16. **Quên chi phí O(N) của stack đệ quy** khi phân tích bitmask.
17. **Nghĩ kiểm tra một ứng viên O(1) tức toàn thuật toán O(N)**.
18. **Không tính O(N²) cho mỗi bảng nghiệm được tạo thành chuỗi**.
19. **Xem N=2,3 trả 0 là lỗi**, trong khi thực sự không có nghiệm.
20. **Không xác định quy ước N=0 và yêu cầu đầu ra** theo đề.
21. **Không xét ràng buộc mới ở biến thể** như bàn không vuông, hậu cố định, ô bị chặn.

## 13. Bài tập có lời giải

**Bài 1.** Hai hậu tại `(0,1)` và `(2,3)` có xung đột? **Giải:** có, vì `r-c` của cả hai bằng -1.

**Bài 2.** Với N=5, ô `(1,4)` có hai chỉ số đường chéo nào? **Giải:** `down=1-4+4=1` và `up=1+4=5`.

**Bài 3.** Vì sao có thể không dùng `usedRow`? **Giải:** mỗi mức đệ quy xử lý đúng một hàng mới, nên các quân đã đặt tự động ở các hàng khác nhau.

**Bài 4.** N=4, dãy `[1,3,0,2]` có hợp lệ không? **Giải:** có; đó là nghiệm `.Q.. / ...Q / Q... / ..Q.`.

**Bài 5.** N=4, dãy `[0,2,1,3]` có hợp lệ không? **Giải:** không, quân ở `(1,2)` và `(2,1)` chung đường chéo.

**Bài 6.** N=2,3 có bao nhiêu nghiệm? **Giải:** đều 0.

**Bài 7.** N=8 có bao nhiêu cấu hình khi các hình phản chiếu được đếm riêng? **Giải:** 92.

**Bài 8.** N=8 có bao nhiêu lớp cơ bản theo quay/phản chiếu? **Giải:** 12.

**Bài 9.** Vì sao phải xóa `usedDiagDown` sau nhánh đệ quy? **Giải:** để dấu chéo của quân đã gỡ không tiếp tục cấm các nhánh kế.

**Bài 10.** Vì sao chỉ đếm khi `row==N`? **Giải:** vì mọi tiền tố ngắn hơn chưa chắc có cách điền đủ N hàng.

**Bài 11.** Chỉ cần số nghiệm N=8, phải lưu 92 bảng không? **Giải:** không; `solve(8,0)` đếm 92 nhưng danh sách bảng mẫu rỗng.

**Bài 12.** Bitmask dịch trái/phải có ý nghĩa gì? **Giải:** đường chéo của quân tại cột c tấn công các cột c-1 và c+1 ở hàng kế tiếp.

**Bài 13.** Tại sao N chẵn có thể nhân đôi số nghiệm khi chỉ duyệt quân đầu ở nửa trái? **Giải:** phép phản chiếu trái–phải ghép một-một nghiệm của cột c với cột N-1-c ở nửa phải.

**Bài 14.** N lẻ có cần xử lý cột giữa riêng? **Giải:** có, vì phản chiếu cột giữa vẫn là cột giữa nên không có cặp cột khác nhau.

**Bài 15.** Bàn có ô cấm không đối xứng có thể nhân đôi dựa trên phản chiếu không? **Giải:** không mặc nhiên, vì ảnh phản chiếu có thể không hợp lệ.

**Bài 16.** N! có phải số nghiệm N-Queens không? **Giải:** không, đó là số hoán vị cột trước khi lọc các xung đột đường chéo.

**Bài 17.** Bộ nhớ stack tối đa của thuật toán đệ quy? **Giải:** O(N), vì mỗi mức xử lý một hàng.

**Bài 18.** Lưu K bảng dạng N dòng, mỗi dòng N ký tự, cần bao nhiêu? **Giải:** O(K·N²) bộ nhớ và công việc tạo đầu ra.

## 14. Checklist triển khai

1. Đề yêu cầu **tìm một nghiệm, đếm tất cả hay liệt kê**? Có gộp nghiệm đối xứng không?
2. Có thống nhất miền N, quy ước N=0 và các ô cấm/hậu cố định không?
3. Có đặt đúng một hậu trên mỗi hàng bằng `placement[row]` không?
4. Có kiểm tra **cột và cả hai hướng chéo**, với chỉ số `row-col+N-1` và `row+col` không?
5. Có đánh dấu đầy đủ trước khi đệ quy và hoàn tác đối xứng sau khi quay về?
6. Chỉ ghi nghiệm khi `row==N`, và dừng sớm đúng lúc nếu chỉ cần một nghiệm?
7. Khi lưu nghiệm, có sao chép bảng thay vì giữ mảng mutable?
8. Nếu dùng bitmask, có lọc bằng `all` và dịch hai hướng đúng?
9. Nếu dùng đối xứng, có xử lý cột giữa khi N lẻ và giữ đúng yêu cầu đầu ra?
10. Đã đối chiếu N=1..8, hai nghiệm N=4 và các trường hợp vô nghiệm?
11. Đã phân tích số nhánh tổ hợp, O(N) bộ nhớ phụ, O(K·N²) đầu ra?
12. Có giới hạn thời gian và kiểu dữ liệu đếm phù hợp cho N lớn?

**Ghi nhớ:** lời giải N quân hậu đúng dựa trên **một quân/hàng**, kiểm tra **cột và hai đường chéo**, chỉ ghi nghiệm khi hoàn thành N hàng, và **hoàn tác trạng thái chính xác** giữa các nhánh. Bitmask hoặc đối xứng giúp giảm thao tác, nhưng không thay thế bất biến và chứng minh của quay lui.
