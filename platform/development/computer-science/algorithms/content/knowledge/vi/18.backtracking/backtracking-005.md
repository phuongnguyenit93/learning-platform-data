# Chọn thứ tự biến và thứ tự thử giá trị trong quay lui

> **Chủ đề:** Computer Science Algorithms → Quay lui (*backtracking*).  
> **Mục tiêu:** Hiểu hai quyết định khác nhau của một bộ giải quay lui: **chọn biến chưa gán nào tiếp theo** (*variable ordering*) và **thử giá trị nào trước cho biến đó** (*value ordering*). Biết cách áp dụng thứ tự cố định, MRV, bậc ràng buộc (*degree heuristic*), LCV, thứ tự ưu tiên theo mục tiêu; kết hợp kiểm tra ràng buộc và lan truyền; chứng minh tính đúng và tính đầy đủ; đánh giá lợi ích bằng số nút và thời gian thực tế. Các ví dụ dùng Java 17+.

## 1. Bối cảnh: cây tìm kiếm quay lui

**Quay lui** là cách xây dựng một lời giải **từng quyết định**, kiểm tra điều kiện, và **hoàn tác** quyết định khi nhánh hiện tại không thể dẫn tới lời giải mong muốn.

Một nút tìm kiếm thường gồm:

- **Trạng thái:** những biến đã có giá trị, những biến còn trống, thông tin ràng buộc liên quan.
- **Danh sách nhánh:** mỗi giá trị có thể thử cho một biến được chọn.
- **Kiểm tra hợp lệ:** không vi phạm các ràng buộc đã biết.
- **Dừng:** khi mọi biến đã được gán và nghiệm thỏa tất cả điều kiện; hoặc khi một nhánh không còn khả năng thành công.

Ví dụ, tô màu đồ thị: mỗi đỉnh là **biến**, mỗi màu là **giá trị**, hai đỉnh có cạnh không được dùng cùng màu. Ở mỗi bước, ta phải trả lời:

1. **Chọn đỉnh nào để tô tiếp?** Đây là **thứ tự biến**.
2. **Thử màu nào đầu tiên cho đỉnh đó?** Đây là **thứ tự giá trị**.

Hai câu hỏi này là độc lập về khái niệm, dù một heuristic có thể dùng thông tin của heuristic kia.

Một khung quay lui chung:

```text
search(assignment):
    if tất cả biến đã gán:
        ghi nhận nghiệm hợp lệ
        return

    X = selectUnassignedVariable(assignment)

    for value in orderLegalValues(X, assignment):
        gán X = value

        if consistent(assignment) and propagationAllowsContinuation():
            search(assignment)

        hoàn tác X = unassigned
```

**Công thức quan trọng:** nếu thuật toán vẫn xét **đủ mọi biến bắt buộc** và **mọi giá trị hợp lệ** khi duyệt hết cây, đổi thứ tự chỉ thay **đường đi qua cây tìm kiếm**, không làm thay đổi **tập nghiệm**. Nhưng nếu dừng sau nghiệm đầu tiên, giới hạn thời gian, hoặc có cắt nhánh theo bound thì thứ tự có thể ảnh hưởng mạnh tới **kết quả đầu tiên** và **lượng công việc thực hiện**.

## 2. Mô hình CSP: biến, miền giá trị, ràng buộc

Bài toán thỏa ràng buộc (*constraint satisfaction problem*, CSP) thường được mô tả bằng:

- `X = {X_1,...,X_n}`: tập biến.
- `D(X_i)`: **miền** những giá trị biến i được phép nhận.
- `C`: các ràng buộc như `A != B`, `sum <= K`, không trùng cột/đường chéo.
- **Nghiệm:** một phép gán đầy đủ cho mọi biến, mỗi giá trị thuộc miền gốc của biến, đồng thời thỏa tất cả ràng buộc.

**Miền hiện tại** (*current domain*) khác với **miền ban đầu**. Ví dụ `D(B)={1,2,3}` nhưng nếu đã gán `A=2` và có ràng buộc `A!=B` thì `B` chỉ còn `{1,3}`. Trong các ví dụ đơn giản, ta có thể **tính lại** miền hiện tại bằng cách lọc các giá trị tương thích với phép gán đã có.

### 2.1. Miền còn lại là khái niệm động

Đặt `D_t(X)` = các giá trị của biến chưa gán X **không vi phạm ngay** ràng buộc với những biến đã gán tại thời điểm t.

Nếu tiến hành **forward checking** hoặc **arc consistency**, miền còn lại còn có thể bị thu hẹp do lan truyền giữa những biến chưa gán. Khi so sánh kích thước miền bằng MRV, phải nói rõ miền đang xét **sau mức lan truyền nào**.

Ví dụ với ràng buộc `A!=B`, sau khi gán `A=1`:

```text
Miền gốc B:  {1,2,3}
Miền còn lại: {2,3}
```

Nếu `D_t(B)=∅`, nhánh hiện tại không thể có nghiệm đầy đủ: B không còn giá trị nào hợp lệ. Ta có thể **quay lui ngay**, không cần tiếp tục gán các biến khác.

### 2.2. CSP thỏa mãn khác bài tối ưu

Bài **thỏa mãn** hỏi có một nghiệm hợp lệ hay không, hoặc liệt kê tất cả nghiệm. Bài **tối ưu** còn có mục tiêu như tối đa lợi nhuận hoặc tối thiểu chi phí. Cùng các biến và ràng buộc, nhưng:

- Với **một nghiệm đầu tiên**, giá trị thử trước có thể quyết định kết quả trả về.
- Với **tất cả nghiệm**, thuật toán cần duyệt hết các nhánh không bị loại an toàn.
- Với **nghiệm tốt nhất**, branch-and-bound có thể tận dụng việc thử phương án hứa hẹn trước để tìm một *incumbent* tốt rồi cắt nhánh bằng chặn trên/chặn dưới.

Thứ tự biến/giá trị **không tự nó là chứng minh tối ưu**. Tính tối ưu đến từ việc xét đủ phương án hoặc cắt theo một bound hợp lệ.

## 3. Chọn thứ tự biến: cố định và động

### 3.1. Thứ tự cố định (*static variable ordering*)

Quy tắc đơn giản nhất: luôn chọn **biến chưa gán đầu tiên** trong một danh sách cố định.

Ví dụ: `A → B → C → D`, hoặc trong Sudoku chọn ô trống đầu tiên theo thứ tự hàng–cột.

**Ưu điểm:**

- Mã ngắn, dễ kiểm tra và dễ dựng nghiệm theo thứ tự.
- Đầu ra có thể xác định, đặc biệt nếu thứ tự giá trị cũng cố định.
- Không tốn chi phí tính lại điểm ưu tiên biến ở mỗi nút.

**Nhược điểm:** có thể thử nhiều biến còn “dễ” trước khi đụng biến “khó”, dẫn tới cây tìm kiếm lớn mới phát hiện mâu thuẫn.

### 3.2. Thứ tự động (*dynamic variable ordering*)

Tại **mỗi nút**, chấm điểm những biến chưa gán bằng thông tin hiện tại, sau đó chọn một biến.

Ví dụ sau một số phép gán:

```text
Biến A: còn 3 giá trị
Biến B: còn 1 giá trị
Biến C: còn 2 giá trị
Biến D: còn 3 giá trị
```

Quy tắc **MRV** sẽ chọn B trước. Sau khi gán B, miền của A,C,D có thể lại thay đổi, vì thế lựa chọn tiếp theo phải được **tính lại**, không nhất thiết theo thứ tự cũ.

**Đổi chác:** thứ tự động có thể giảm số nhánh nhưng tốn thời gian tính miền, bậc ràng buộc và điểm ưu tiên ở mỗi nút. Không được kết luận “dùng heuristic luôn nhanh hơn” chỉ bằng một ví dụ.

## 4. MRV — Minimum Remaining Values (*fail-first*)

**MRV** chọn biến chưa gán có **ít giá trị hợp lệ còn lại nhất**.

Viết bằng công thức:

`X* = argmin_(X chưa gán) |D_t(X)|`.

Nếu hai biến cùng ít giá trị, cần thêm quy tắc hòa để kết quả xác định.

**Trực giác fail-first:** nếu nhánh hiện tại sắp dẫn tới thất bại, nên phát hiện thất bại **càng sớm càng tốt**. Biến có ít lựa chọn thường có nguy cơ gây mâu thuẫn sớm hơn, nên chọn nó trước để giảm công việc ở các nhánh không có nghiệm.

### 4.1. Miền rỗng thì xử lý thế nào?

Nếu một biến chưa gán có `|D_t(X)|=0`, nhánh hiện tại **vô nghiệm**. Không nên chỉ in một thông báo và tiếp tục chọn biến khác; phải **quay lui**, trừ khi bài dùng cơ chế sửa miền/gán khác đã được chứng minh hợp lệ.

Nếu tất cả biến đều đã gán, phải **kiểm tra hoàn chỉnh** và ghi nhận nghiệm. Đừng coi “không còn biến để chọn” là thất bại.

### 4.2. MRV không phải một thuật toán riêng thay thế quay lui

MRV chỉ quyết định **biến nào xuất hiện ở tầng kế tiếp**. Ta vẫn cần:

- Liệt kê/thử các giá trị trong miền của biến được chọn.
- Kiểm tra mọi ràng buộc mới.
- Quay lui và hoàn tác chính xác.
- Tiếp tục cho tới khi đạt yêu cầu “một nghiệm”, “tất cả nghiệm” hoặc “tối ưu”.

MRV là **heuristic của thứ tự**, không phải quy tắc luôn đảm bảo tìm nghiệm ở ngay nhánh đầu.

## 5. Degree heuristic — phá hòa bằng mức ảnh hưởng

Nếu nhiều biến cùng số lượng giá trị còn lại, có thể chọn biến **ràng buộc với nhiều biến chưa gán nhất**:

`degree_t(X) = số biến chưa gán Y khác X có ràng buộc trực tiếp với X`.

Quy tắc kết hợp phổ biến:

1. **MRV trước:** ít giá trị còn lại nhất.
2. **Degree tie-break:** nếu MRV hòa, chọn biến có nhiều hàng xóm chưa gán nhất.
3. **Tiebreak ổn định:** nếu vẫn hòa, chọn tên biến/chỉ số nhỏ nhất.

**Trực giác:** một biến có nhiều ràng buộc với những biến chưa gán có khả năng **thu hẹp nhiều miền khác** khi được gán, giúp tìm sớm những lựa chọn mâu thuẫn hoặc bắt buộc.

### 5.1. “Degree” phải đúng với mô hình ràng buộc

Đối với đồ thị tô màu, degree thường là số đỉnh kề chưa tô. Với một CSP có ràng buộc nhiều biến (*hyperconstraint*), không thể luôn đếm cạnh nhị phân đơn giản. Cần xác định mức ảnh hưởng từ cấu trúc ràng buộc thực tế.

Ví dụ trong Sudoku, một ô có các ô cùng hàng, cùng cột và cùng hộp; nếu dùng degree, đếm mỗi ô hàng xóm chưa gán **một lần**, tránh cộng trùng ô vừa cùng hàng vừa cùng hộp.

### 5.2. Một biến miền đơn phần tử

Nếu `|D_t(X)|=1`, MRV thường chọn ngay X. Điều này gần với việc thực hiện một phép gán **bắt buộc**, trừ khi các ràng buộc toàn cục có cơ chế mạnh hơn. Có thể dùng lan truyền để gán các biến đơn trị trước; sau khi gán cần tiếp tục kiểm tra những miền bị ảnh hưởng.

## 6. Thứ tự thử giá trị: từ cố định đến LCV

Sau khi chọn biến X, ta còn phải chọn **giá trị nào thử trước**.

### 6.1. Giá trị theo thứ tự cố định

Duyệt tăng dần, giảm dần hoặc theo thứ tự input:

```text
D(X) = {1,2,3}
Thử tăng: 1 → 2 → 3
Thử giảm: 3 → 2 → 1
```

Nếu bài yêu cầu nghiệm đầu tiên theo **thứ tự từ điển của dãy biến cố định**, duyệt biến theo thứ tự cố định và giá trị tăng có thể có ý nghĩa đặc biệt. Dùng MRV tùy ý có thể làm **thay đổi thứ tự sinh nghiệm**; không thể khẳng định kết quả đầu tiên vẫn là nghiệm từ điển nhỏ nhất.

### 6.2. LCV — Least Constraining Value

**LCV** ưu tiên giá trị làm **mất ít lựa chọn nhất** của các biến chưa gán còn lại.

Với bài nhị phân đơn giản, định nghĩa điểm ảnh hưởng ước lượng:

`impact(X=a) = Σ_(Y là hàng xóm chưa gán) ( |D_t(Y)| − |D_(t sau X=a)(Y)| )`.

Giá trị có `impact` nhỏ nhất được thử trước.

Ví dụ một màu của đỉnh X:

- Màu đỏ khiến ba đỉnh kề mất tổng cộng 5 lựa chọn.
- Màu xanh khiến chúng mất tổng cộng 2 lựa chọn.

LCV thử **xanh trước**, vì nó chừa lại nhiều lựa chọn cho các đỉnh tiếp theo.

**LCV không phải định lý “chọn giá trị tốt nhất cho mục tiêu”.** Nó chỉ dự đoán nhánh nào có nhiều chỗ xoay xở nhất. Một nhánh có nhiều giá trị còn lại vẫn có thể vô nghiệm do ràng buộc phức tạp; một nhánh rất chặt lại có thể chứa nghiệm duy nhất.

### 6.3. MRV và LCV tưởng ngược nhau nhưng không mâu thuẫn

- **MRV chọn biến khó trước** (*fail-first*): dễ phát hiện sớm nhánh bất khả thi.
- **LCV thử giá trị ít cản trở trước** (*succeed-first*): tăng khả năng sớm tìm được một nghiệm.

Hai chiến lược phục vụ hai quyết định **khác nhau** và có thể kết hợp ở cùng một nút.

Nếu muốn chứng minh **không có nghiệm** hoặc liệt kê **tất cả nghiệm**, LCV có thể làm tăng công chấm điểm mà không giảm được số nghiệm cần xét. Thứ tự tốt nhất phụ thuộc mục tiêu và cấu trúc đề bài.

## 7. Ví dụ từng bước: bốn biến với ràng buộc khác nhau

Xét CSP:

```text
Biến: A, B, C, D
Miền gốc:
    A ∈ {1,2,3}
    B ∈ {1,2}
    C ∈ {2,3}
    D ∈ {1,2,3}

Ràng buộc:
    A != B
    A != C
    B != C
    C != D
```

Có thể hình dung đồ thị ràng buộc gồm các cạnh `A−B`, `A−C`, `B−C`, `C−D`. Mỗi cạnh yêu cầu hai đầu có **giá trị khác nhau**.

### 7.1. Chọn biến bằng MRV + degree

Ở trạng thái ban đầu, chưa có biến nào được gán:

| Biến | Miền còn lại | MRV: số giá trị | Số hàng xóm chưa gán |
|---|---|---:|---:|
| A | `{1,2,3}` | 3 | 2 (B,C) |
| B | `{1,2}` | **2** | 2 (A,C) |
| C | `{2,3}` | **2** | **3** (A,B,D) |
| D | `{1,2,3}` | 3 | 1 (C) |

MRV hòa giữa **B và C** (cùng hai giá trị). Degree chọn **C** vì C tác động đến **3** biến chưa gán, còn B tác động đến 2.

Nếu duyệt **biến cố định**, ta sẽ chọn **A** trước. Đây là điểm khác biệt đầu tiên giữa hai thứ tự.

### 7.2. Xếp giá trị của C bằng LCV

Miền C là `{2,3}`.

Thử giả định `C=2`:

- A mất giá trị 2 ⇒ còn `{1,3}`: mất 1 lựa chọn.
- B mất giá trị 2 ⇒ còn `{1}`: mất 1 lựa chọn.
- D mất giá trị 2 ⇒ còn `{1,3}`: mất 1 lựa chọn.
- Tổng tác động ước lượng **3**.

Thử giả định `C=3`:

- A mất giá trị 3 ⇒ còn `{1,2}`: mất 1.
- B vốn chỉ có `{1,2}` ⇒ không mất gì: mất 0.
- D mất giá trị 3 ⇒ còn `{1,2}`: mất 1.
- Tổng tác động **2**.

**LCV thử `C=3` trước `C=2`**, vì điểm tác động 2 nhỏ hơn 3.

### 7.3. Sau khi gán C=3

Các miền còn lại:

```text
A ∈ {1,2}
B ∈ {1,2}
D ∈ {1,2}
```

MRV hòa cả ba. Degree chưa gán:

- A còn liên hệ B ⇒ degree 1.
- B còn liên hệ A ⇒ degree 1.
- D chỉ liên hệ C đã gán ⇒ degree 0.

Giữa A và B, quy tắc hòa theo chỉ số chọn **A**. Nếu thử A=1 thì B không được 1 nên chọn B=2; D có thể là 1 hoặc 2. Một nghiệm:

`[A=1, B=2, C=3, D=1]`.

### 7.4. Tất cả nghiệm để đối chiếu

Với ràng buộc trên, có chính xác **6 phép gán đầy đủ**:

```text
[A,B,C,D] = [1,2,3,1]
[A,B,C,D] = [1,2,3,2]
[A,B,C,D] = [2,1,3,1]
[A,B,C,D] = [2,1,3,2]
[A,B,C,D] = [3,1,2,1]
[A,B,C,D] = [3,1,2,3]
```

Thứ tự dùng MRV/LCV và thứ tự cố định có thể duyệt các nhánh khác nhau, nhưng nếu triển khai đúng và **không dừng sớm**, tập sáu nghiệm phải bằng nhau.

## 8. Java 17: thử hai kiểu thứ tự biến/giá trị trên CSP

Lưu thành **CspVariableValueOrderingDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class CspVariableValueOrderingDemo {
    static final String[] NAMES = {"A", "B", "C", "D"};

    static final int[][] ORIGINAL_DOMAINS = {
        {1, 2, 3},  // A
        {1, 2},     // B
        {2, 3},     // C
        {1, 2, 3}   // D
    };

    static final boolean[][] EDGE = {
        {false, true,  true,  false},
        {true,  false, true,  false},
        {true,  true,  false, true },
        {false, false, true,  false}
    };

    static final class Stats {
        int calls;
        int tries;
        int solutions;
        int[] first;
    }

    static List<Integer> legalValues(int variable, int[] assignment) {
        List<Integer> legal = new ArrayList<>();

        for (int color : ORIGINAL_DOMAINS[variable]) {
            boolean ok = true;
            for (int other = 0; other < assignment.length; other++) {
                if (EDGE[variable][other]
                        && assignment[other] == color) {
                    ok = false;
                    break;
                }
            }
            if (ok) {
                legal.add(color);
            }
        }
        return legal;
    }

    static int unassignedDegree(int variable, int[] assignment) {
        int result = 0;
        for (int other = 0; other < assignment.length; other++) {
            if (other != variable
                    && EDGE[variable][other]
                    && assignment[other] == 0) {
                result++;
            }
        }
        return result;
    }

    static int chooseVariable(int[] assignment, boolean heuristic) {
        int best = -1;
        int smallestDomain = Integer.MAX_VALUE;
        int largestDegree = -1;

        for (int v = 0; v < assignment.length; v++) {
            if (assignment[v] != 0) {
                continue;
            }
            if (!heuristic) {
                return v; // Thứ tự cố định: A, B, C, D.
            }

            int domainSize = legalValues(v, assignment).size();
            int degree = unassignedDegree(v, assignment);

            if (domainSize < smallestDomain
                    || (domainSize == smallestDomain
                        && degree > largestDegree)) {
                best = v;
                smallestDomain = domainSize;
                largestDegree = degree;
            }
        }
        return best;
    }

    // Tác động LCV: tổng số giá trị bị loại khỏi các đỉnh kề.
    static int impact(int variable, int color, int[] assignment) {
        int before = 0;

        for (int other = 0; other < assignment.length; other++) {
            if (other != variable && EDGE[variable][other]
                    && assignment[other] == 0) {
                before += legalValues(other, assignment).size();
            }
        }

        assignment[variable] = color;
        int after = 0;

        for (int other = 0; other < assignment.length; other++) {
            if (other != variable && EDGE[variable][other]
                    && assignment[other] == 0) {
                after += legalValues(other, assignment).size();
            }
        }

        assignment[variable] = 0;
        return before - after;
    }

    static List<Integer> orderedValues(int variable, int[] assignment,
                                       boolean heuristic) {
        List<Integer> values = legalValues(variable, assignment);

        if (heuristic) {
            values.sort((x, y) -> {
                int byImpact = Integer.compare(
                        impact(variable, x, assignment),
                        impact(variable, y, assignment));
                return byImpact != 0
                        ? byImpact : Integer.compare(x, y);
            });
        }
        return values;
    }

    static boolean forwardCheck(int[] assignment) {
        for (int variable = 0; variable < assignment.length; variable++) {
            if (assignment[variable] == 0
                    && legalValues(variable, assignment).isEmpty()) {
                return false;
            }
        }
        return true;
    }

    static void enumerate(int[] assignment, boolean heuristic, Stats stats) {
        stats.calls++;
        int variable = chooseVariable(assignment, heuristic);

        if (variable == -1) {
            stats.solutions++;
            if (stats.first == null) {
                stats.first = assignment.clone();
            }
            return;
        }

        for (int value : orderedValues(variable, assignment, heuristic)) {
            stats.tries++;
            assignment[variable] = value;

            if (forwardCheck(assignment)) {
                enumerate(assignment, heuristic, stats);
            }
            assignment[variable] = 0; // Hoàn tác đúng nhánh.
        }
    }

    static Stats run(boolean heuristic) {
        Stats stats = new Stats();
        enumerate(new int[NAMES.length], heuristic, stats);
        return stats;
    }

    public static void main(String[] args) {
        int[] empty = new int[NAMES.length];

        System.out.println("Fixed chooses: "
                + NAMES[chooseVariable(empty, false)]);
        System.out.println("MRV+degree chooses: "
                + NAMES[chooseVariable(empty, true)]);
        System.out.println("LCV order for C: "
                + orderedValues(2, empty, true));

        Stats fixed = run(false);
        Stats heuristic = run(true);

        System.out.println("Fixed: solutions=" + fixed.solutions
                + ", calls=" + fixed.calls + ", tries=" + fixed.tries);
        System.out.println("MRV+LCV: solutions=" + heuristic.solutions
                + ", calls=" + heuristic.calls
                + ", tries=" + heuristic.tries);
        System.out.println("First MRV+LCV solution: "
                + Arrays.toString(heuristic.first));
    }
}
```

Chạy bằng Java 17 trở lên:

```bash
javac -encoding UTF-8 CspVariableValueOrderingDemo.java
java CspVariableValueOrderingDemo
```

Stdout:

```text
Fixed chooses: A
MRV+degree chooses: C
LCV order for C: [3, 2]
Fixed: solutions=6, calls=16, tries=16
MRV+LCV: solutions=6, calls=15, tries=14
First MRV+LCV solution: [1, 2, 3, 1]
```

**Đọc kết quả:**

- Cả hai cách duyệt tìm **6 nghiệm**, vì đã duyệt hết các nhánh còn hợp lệ.
- Với **bài thử nhỏ này**, MRV+LCV duyệt **15 lượt gọi đệ quy** và thử **14 phép gán**, ít hơn bản cố định tương ứng 16 và 16.
- Điều đó **không chứng minh** MRV+LCV luôn tốt hơn trên mọi bài hoặc về thời gian thực thi: bản heuristic còn tốn công tính miền, độ ảnh hưởng và sắp giá trị.
- `0` trong `assignment[]` nghĩa là **chưa gán**. Vì các miền thật chỉ chứa 1,2,3, sentinel 0 không xung đột với giá trị hợp lệ.
- `impact()` tạm gán biến rồi trả nó về 0. Nếu quên hoàn tác ở đây, ngay cả việc so sánh thứ tự giá trị cũng **làm hỏng trạng thái tìm kiếm**.
- `forwardCheck()` ở ví dụ chỉ kiểm tra rằng không có biến chưa gán nào có **miền rỗng theo phép gán hiện tại**. Nó chưa phải thuật toán nhất quán cung AC-3 đầy đủ.

### 8.1. Tại sao không tính miền một lần rồi dùng mãi?

Sau khi gán C=3, miền A/B/D đã thay đổi. Nếu chỉ sắp MRV một lần theo miền gốc và không tính lại, ta có **thứ tự biến tĩnh dựa trên MRV ban đầu**, không còn là MRV động theo trạng thái hiện tại.

Trong code, hàm `legalValues()` suy ra miền từ `assignment[]` hiện tại. Cách này dễ chứng minh, dù có thể chậm hơn lưu và lan truyền miền nếu CSP lớn.

## 9. Bất biến và chứng minh bảo toàn tính đầy đủ

Cách chọn thứ tự biến và giá trị chỉ an toàn khi **không bỏ sót nghiệm** vì heuristic.

Giả sử ở một trạng thái S đã gán một phần biến:

1. Mỗi biến chưa gán có một miền hợp lệ đang được xét.
2. Thuật toán chọn **một biến chưa gán X bất kỳ**.
3. Nó duyệt **toàn bộ giá trị hợp lệ** của X, dù theo thứ tự nào.
4. Khi gán X=v, nó bỏ nhánh **chỉ nếu đã có bằng chứng không thể hoàn thiện** thành một nghiệm.
5. Sau khi đi hết nhánh, nó hoàn tác toàn bộ thay đổi, để nhánh kế tiếp xuất phát từ cùng trạng thái S.

Lấy một nghiệm đầy đủ T có thể mở rộng từ S. Trong danh sách giá trị được duyệt của X, chắc chắn có giá trị `T[X]`, vì T thỏa các ràng buộc. Nhánh ứng với giá trị này **không thể bị cắt bởi phép kiểm tra an toàn**; tiếp tục lập luận theo số biến chưa gán, sẽ có một đường đi tới T.

Do đó, nếu thuật toán **duyệt hết**, mọi nghiệm T đều được tìm bất kể chọn X theo MRV, theo degree, thứ tự cố định hay cách chọn khác.

### 9.1. Điều kiện để phép cắt nhánh an toàn

Có thể loại một nhánh khi:

- Có ràng buộc đã **bị vi phạm** và không thể được “sửa” bằng các giá trị tương lai.
- Một biến chưa gán có **miền rỗng** sau một bước lọc miền **đúng**.
- Trong bài tối ưu, có một **chặn trên/chặn dưới hợp lệ** chứng minh nhánh không thể cải thiện nghiệm đang có, phù hợp mục tiêu tìm một optimum.

Không được loại nhánh chỉ vì:

- Giá trị có điểm LCV “xấu”.
- Biến có domain lớn và dự đoán “không hứa hẹn”.
- Một heuristic dự báo nhánh này có ít cơ hội thành công nhưng **không chứng minh vô nghiệm**.

**Heuristic chọn thứ tự** và **quy tắc cắt an toàn** là hai khái niệm khác nhau.

### 9.2. Một nghiệm, tất cả nghiệm, nghiệm từ điển nhỏ nhất

- **Một nghiệm:** dừng ngay khi tìm nghiệm đầu tiên; thứ tự có thể đổi nghiệm trả về.
- **Tất cả nghiệm:** không dừng khi tìm được một nghiệm; chỉ cắt nhánh khi không thể chứa nghiệm mới.
- **Nghiệm từ điển nhỏ nhất theo thứ tự biến cố định:** cần bảo đảm thứ tự duyệt khớp thứ tự từ điển hoặc dùng cơ chế so sánh/kiểm tra bổ sung; dùng MRV động rồi lấy nghiệm đầu tiên không bảo đảm nhỏ nhất.
- **Nghiệm tối ưu:** cần kiểm tra mọi nhánh có thể vượt incumbent hoặc cắt bằng bound chứng minh an toàn.

Nếu hệ thống trả nghiệm phụ thuộc thứ tự, các heuristic tie-break cần được ghi rõ để test ổn định.

## 10. N-Queens: thử giá trị khác thứ tự làm đổi nghiệm đầu tiên

Bài toán đặt `n` quân hậu trên bàn `n×n` sao cho không quân nào cùng hàng, cùng cột hay cùng đường chéo.

Một biểu diễn tự nhiên:

`col[row]` = cột của quân hậu ở hàng `row`.

Trong cách này, ta **cố định thứ tự biến**: chọn hàng `0`, rồi `1`, ..., `n−1`. Miền giá trị cho mỗi hàng là các cột `0..n−1`, nhưng chỉ thử những cột không xung đột với hậu đã đặt trước.

Đây là ví dụ rõ về **value ordering**:

- Thử cột **tăng dần**.
- Thử cột **giảm dần**.

Cả hai đều duyệt đủ cột hợp lệ, nên khi đếm **tất cả nghiệm** chúng phải cho cùng tổng. Nhưng nếu dừng ở **nghiệm đầu tiên**, kết quả có thể khác.

### 10.1. Java 17: N-Queens với hai thứ tự thử cột

Lưu thành **NQueensValueOrderDemo.java**:

```java
import java.util.Arrays;

public class NQueensValueOrderDemo {
    static boolean safe(int[] colAtRow, int row, int col) {
        for (int r = 0; r < row; r++) {
            int oldCol = colAtRow[r];
            if (oldCol == col || Math.abs(oldCol - col) == row - r) {
                return false;
            }
        }
        return true;
    }

    static int[] firstRecursive(int[] colAtRow, int row,
                                boolean descending) {
        int n = colAtRow.length;
        if (row == n) {
            return colAtRow.clone();
        }

        for (int step = 0; step < n; step++) {
            int col = descending ? n - 1 - step : step;
            if (!safe(colAtRow, row, col)) {
                continue;
            }
            colAtRow[row] = col;
            int[] answer = firstRecursive(
                    colAtRow, row + 1, descending);
            if (answer != null) {
                return answer;
            }
            colAtRow[row] = -1;
        }
        return null;
    }

    static int[] firstSolution(int n, boolean descending) {
        if (n < 0) {
            throw new IllegalArgumentException("Negative n");
        }
        int[] board = new int[n];
        Arrays.fill(board, -1);
        return firstRecursive(board, 0, descending);
    }

    static long countRecursive(int[] colAtRow, int row) {
        int n = colAtRow.length;
        if (row == n) {
            return 1L;
        }

        long count = 0L;
        for (int col = 0; col < n; col++) {
            if (!safe(colAtRow, row, col)) {
                continue;
            }
            colAtRow[row] = col;
            count += countRecursive(colAtRow, row + 1);
            colAtRow[row] = -1;
        }
        return count;
    }

    static long countAll(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("Negative n");
        }
        int[] board = new int[n];
        Arrays.fill(board, -1);
        return countRecursive(board, 0);
    }

    public static void main(String[] args) {
        System.out.println("n=4 ascending first: "
                + Arrays.toString(firstSolution(4, false)));
        System.out.println("n=4 descending first: "
                + Arrays.toString(firstSolution(4, true)));
        System.out.println("n=4 all solutions: " + countAll(4));
        System.out.println("n=8 all solutions: " + countAll(8));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 NQueensValueOrderDemo.java
java NQueensValueOrderDemo
```

Stdout:

```text
n=4 ascending first: [1, 3, 0, 2]
n=4 descending first: [2, 0, 3, 1]
n=4 all solutions: 2
n=8 all solutions: 92
```

Mảng ví dụ `[1,3,0,2]` nghĩa là quân hậu ở hàng 0 cột 1, hàng 1 cột 3, hàng 2 cột 0, hàng 3 cột 2. Với `n=4`, thử cột giảm tìm nghiệm đối xứng `[2,0,3,1]` trước.

**Cần hiểu đúng:** đoạn code minh họa **thứ tự giá trị** khi thứ tự biến là hàng tăng dần; nó **không thực hiện MRV**. Nếu muốn chọn “hàng nào đặt hậu trước” động bằng MRV, ta phải đánh dấu tập hàng chưa gán, tính những cột hợp lệ theo toàn bộ quân hậu đã đặt (kể cả hàng ở phía sau), và hoàn tác gán theo **hàng bất kỳ**. Không thể chỉ đổi vòng `row++` thành một chọn hàng tùy ý mà giữ nguyên `safe()` vốn chỉ xét các hàng `< row`.

### 10.2. Đánh giá lợi ích thứ tự giá trị ở N-Queens

Thử cột giữa trước, cột ít xung đột dự kiến trước hoặc ưu tiên ngẫu nhiên đôi khi tìm nghiệm đầu tiên nhanh hơn. Nhưng nếu yêu cầu **đếm toàn bộ** và không có phép cắt làm giảm số nút, hoán vị thứ tự thử cột chỉ đổi đường duyệt và có thể cho cùng tổng số nút.

Mã minh họa `countAll(8)` dùng quay lui thuần, không tối ưu bitmask. Tổng số nghiệm `n=8` là **92** khi tính cả những nghiệm đối xứng riêng biệt theo vị trí. Nếu sử dụng loại đối xứng để tránh đếm lặp, phải phân biệt “số nghiệm toàn bộ” với “số lớp nghiệm không tương đương đối xứng”.

## 11. Sudoku 4×4: MRV động giúp gặp ô bị ép sớm hơn

Một Sudoku `4×4` dùng các số `1..4`. Mỗi hàng, mỗi cột và mỗi ô vuông `2×2` phải chứa bốn giá trị khác nhau.

**Biến:** các ô trống.  
**Miền:** các số `1..4` chưa có trong hàng, cột, hộp tương ứng.  
**Ràng buộc:** mỗi nhóm hàng/cột/hộp không có hai ô trùng số.

Ví dụ puzzle (`0` là ô trống):

```text
1 0 0 4
0 4 0 2
2 0 4 0
4 0 0 1
```

Ở trạng thái đầu, ô **hàng 1 cột 3** theo chỉ số 1-based (tức `(0,2)` 0-based) chỉ có thể điền **3**. MRV chọn ô bị ép đó, thay vì nhất thiết chọn ô trống đầu tiên theo thứ tự hàng–cột.

### 11.1. Java 17: so sánh thứ tự ô cố định và MRV

Lưu thành **SudokuMrvDemo.java**:

```java
import java.util.ArrayList;
import java.util.List;

public class SudokuMrvDemo {
    static final class Stats {
        int calls;
        int tries;
        int solutions;
        int[][] first;
    }

    static int[][] copy(int[][] source) {
        int[][] result = new int[source.length][];
        for (int i = 0; i < source.length; i++) {
            result[i] = source[i].clone();
        }
        return result;
    }

    static int[] candidates(int[][] board, int row, int col) {
        boolean[] used = new boolean[5];

        for (int x = 0; x < 4; x++) {
            used[board[row][x]] = true;
            used[board[x][col]] = true;
        }

        int boxRow = (row / 2) * 2;
        int boxCol = (col / 2) * 2;

        for (int r = boxRow; r < boxRow + 2; r++) {
            for (int c = boxCol; c < boxCol + 2; c++) {
                used[board[r][c]] = true;
            }
        }

        List<Integer> values = new ArrayList<>();
        for (int number = 1; number <= 4; number++) {
            if (!used[number]) {
                values.add(number);
            }
        }

        int[] result = new int[values.size()];
        for (int i = 0; i < values.size(); i++) {
            result[i] = values.get(i);
        }
        return result;
    }

    static void search(int[][] board, boolean mrv, Stats stats) {
        stats.calls++;
        int bestRow = -1;
        int bestCol = -1;
        int[] options = null;

        outer:
        for (int r = 0; r < 4; r++) {
            for (int c = 0; c < 4; c++) {
                if (board[r][c] != 0) {
                    continue;
                }

                int[] current = candidates(board, r, c);
                if (options == null
                        || (mrv && current.length < options.length)) {
                    bestRow = r;
                    bestCol = c;
                    options = current;
                }

                if (!mrv) {
                    break outer; // Ô trống đầu theo hàng/cột.
                }
            }
        }

        if (bestRow == -1) {
            stats.solutions++;
            if (stats.first == null) {
                stats.first = copy(board);
            }
            return;
        }

        for (int value : options) {
            stats.tries++;
            board[bestRow][bestCol] = value;
            search(board, mrv, stats);
            board[bestRow][bestCol] = 0;
        }
    }

    static Stats analyze(int[][] puzzle, boolean mrv) {
        int[][] board = copy(puzzle);
        Stats stats = new Stats();
        search(board, mrv, stats);
        return stats;
    }

    public static void main(String[] args) {
        int[][] puzzle = {
            {1, 0, 0, 4},
            {0, 4, 0, 2},
            {2, 0, 4, 0},
            {4, 0, 0, 1}
        };

        Stats fixed = analyze(puzzle, false);
        Stats mrv = analyze(puzzle, true);

        System.out.println("Fixed: solutions=" + fixed.solutions
                + ", calls=" + fixed.calls + ", tries=" + fixed.tries);
        System.out.println("MRV: solutions=" + mrv.solutions
                + ", calls=" + mrv.calls + ", tries=" + mrv.tries);
        System.out.println("Solution:");

        for (int[] row : mrv.first) {
            for (int value : row) {
                System.out.print(value);
            }
            System.out.println();
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 SudokuMrvDemo.java
java SudokuMrvDemo
```

Stdout:

```text
Fixed: solutions=1, calls=11, tries=10
MRV: solutions=1, calls=9, tries=8
Solution:
1234
3412
2143
4321
```

**Phạm vi mã mẫu:** puzzle này đã hợp lệ, kích thước đúng `4×4` và các chữ số thuộc `0..4`. `candidates()` dựa vào tiền đề đó để dùng chỉ số mảng `used[board[r][c]]`. Khi xây solver tổng quát, phải **xác thực bảng ban đầu** (kích thước, giá trị, các ô cho trước có mâu thuẫn không) trước khi gọi tìm kiếm.

`calls` đếm số lần vào hàm `search()`, kể cả trạng thái hoàn thành; `tries` đếm số lần gán một chữ số để thử, không tính việc xác định miền. Đó là chỉ số **nút/lựa chọn**, không phải đơn vị thời gian chạy.

### 11.2. Sự đánh đổi ở ví dụ này

MRV giảm 11 xuống 9 lượt gọi và 10 xuống 8 phép thử, nhưng phải tính miền của **tất cả ô trống** tại mỗi nút để chọn ô có domain nhỏ nhất. Trên puzzle rất nhỏ, overhead có thể khiến phiên bản MRV không nhanh hơn về millisecond.

Với Sudoku lớn, MRV thường hữu ích hơn khi nhiều ô có miền khác nhau, nhưng kết quả thực tế còn phụ thuộc propagation, cách tính candidates, cache, tie-break và cấu trúc puzzle.

## 12. Forward checking, propagation và sự phối hợp với thứ tự

**Forward checking** là cách sau mỗi phép gán kiểm tra/lọc những giá trị của biến chưa gán bị ràng buộc trực tiếp loại trừ. Nếu một biến nào đó không còn giá trị, quay lui sớm.

Ví dụ A,B,C tạo tam giác `A!=B`, `A!=C`, `B!=C`, và chỉ có hai màu `{1,2}`:

- Gán A=1 ⇒ B,C còn `{2}`.
- Gán B=2 ⇒ C không còn giá trị nào.
- Forward checking phát hiện C rỗng và quay lui mà không thử gán C.

### 12.1. Lan truyền mạnh hơn: arc consistency

Với ràng buộc nhị phân, *arc consistency* yêu cầu **mỗi giá trị** trong miền X có ít nhất một giá trị ở miền Y **hỗ trợ** ràng buộc giữa X và Y. Thuật toán AC-3 là một kỹ thuật để lặp việc loại giá trị không có hỗ trợ, cho tới khi không còn thay đổi hoặc xuất hiện miền rỗng.

Khác biệt:

- Kiểm tra trực tiếp như code CSP ở trên chỉ lọc theo **các biến đã gán**.
- Forward checking thường kiểm tra ảnh hưởng trực tiếp của biến vừa gán lên các biến chưa gán.
- Arc consistency có thể tiếp tục truyền ảnh hưởng **giữa các biến chưa gán**, mạnh hơn nhưng cũng tốn công.

### 12.2. Cần hoàn tác cả miền đã sửa

Nếu solver duy trì các miền trong mảng hoặc bitset và loại giá trị khi propagation, quay lui phải **khôi phục đúng những giá trị đã loại ở nhánh hiện tại**.

Các cách thường gặp:

- **Copy-on-recursion:** sao chép dữ liệu miền cho mỗi nhánh; dễ đúng nhưng tốn bộ nhớ/thời gian.
- **Trail/undo log:** ghi các thay đổi vào một danh sách, đánh dấu mốc trước nhánh, rồi khôi phục các thay đổi từ mốc đó khi quay lui.
- **Tính lại domain từ assignment:** không lưu tác động riêng; dễ triển khai trong các demo nhỏ nhưng phải tính lặp.

Nếu chỉ hoàn tác `assignment[X]` mà **quên hoàn tác miền của Y**, các giá trị bị loại ở nhánh trước sẽ tiếp tục vắng ở nhánh sau, khiến thuật toán **bỏ sót nghiệm**. Đây là lỗi phá tính đầy đủ rất nghiêm trọng.

### 12.3. LCV đo trước hay sau propagation?

Một cách LCV chuẩn ước lượng số lựa chọn bị loại khỏi các hàng xóm ngay khi thử `X=v`. Cách mạnh hơn có thể thử propagation tạm, đo tổng domain bị thu hẹp rồi rollback.

Hai cách có chất lượng heuristic và chi phí khác nhau. Bất kể cách nào, quá trình **thử mô phỏng** phải được hoàn tác hoàn toàn trước khi sang giá trị kế tiếp.

## 13. Thứ tự thử giá trị trong bài tối ưu và branch-and-bound

Trong bài **tối ưu**, một giá trị thử sớm có thể giúp tìm một nghiệm hoàn chỉnh chất lượng cao và tạo **incumbent** (nghiệm tốt nhất đã biết).

Nếu ta tìm **cực đại** và có chặn trên an toàn `upperBound(state)`, có thể cắt nhánh khi:

`upperBound(state) <= incumbent`.

Cắt bằng dấu `<=` an toàn nếu chỉ cần **một giá trị tối ưu và một nghiệm đạt nó**. Nếu muốn **liệt kê mọi nghiệm tối ưu**, cắt nhánh có bound **bằng** incumbent có thể bỏ sót nghiệm khác cùng tối ưu; chính sách phải đổi theo yêu cầu.

**Giá trị ưu tiên theo lợi nhuận** có thể giúp tìm incumbent lớn sớm, nhưng không được coi “lấy lợi nhuận lớn nhất trước” là phép chứng minh tối ưu. Chính **upper bound hợp lệ** mới chứng minh nhánh bị cắt không thể vượt nghiệm đã biết.

### 13.1. Ví dụ phân công 3 người cho 3 công việc

Mỗi người được nhận **đúng một** công việc, mỗi công việc dùng **đúng một lần**. Điểm lợi nhuận:

| Người | Công việc 0 | Công việc 1 | Công việc 2 |
|---|---:|---:|---:|
| W0 | 1 | **9** | 2 |
| W1 | 5 | 3 | **8** |
| W2 | **7** | 4 | 6 |

Một nghiệm tối ưu là:

`W0→1` (9), `W1→2` (8), `W2→0` (7), tổng **24**.

Nếu thử việc theo chỉ số tăng `0,1,2`, nhánh hoàn chỉnh đầu tiên chọn `[0,1,2]`, giá trị `1+3+6=10`. Nếu thử công việc có lợi nhuận cao trước cho từng người, nhánh đầu tiên là `[1,2,0]`, giá trị 24 — trùng tối ưu.

### 13.2. Chặn trên an toàn

Ở một trạng thái đã phân công một số người, gọi:

`bound = currentScore + Σ_(người còn lại) max_(việc chưa dùng) profit[người][việc]`.

Chặn này **lạc quan**: mỗi người còn lại được phép chọn công việc có lợi nhất riêng cho họ, kể cả nhiều người cùng thích một công việc. Vì thư giãn ràng buộc “không được dùng chung công việc”, bound không thể thấp hơn giá trị tốt nhất thực sự có thể hoàn thành từ nhánh.

Do đó nếu `bound <= bestScore` thì nhánh không thể cải thiện kết quả đã biết.

### 13.3. Java 17: thứ tự giá trị thay đổi hiệu quả branch-and-bound

Lưu thành **AssignmentValueOrderBnBDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class AssignmentValueOrderBnBDemo {
    static final int[][] PROFIT = {
        {1, 9, 2},
        {5, 3, 8},
        {7, 4, 6}
    };

    static final class Stats {
        int nodes;
        int leaves;
        int pruned;
        int firstValue = Integer.MIN_VALUE;
        int bestValue = Integer.MIN_VALUE;
        int[] bestJobs;
        int[] firstJobs;
    }

    static int optimisticBound(int worker, boolean[] used,
                               int currentValue) {
        int upper = currentValue;

        for (int r = worker; r < PROFIT.length; r++) {
            int bestRemaining = Integer.MIN_VALUE;
            for (int job = 0; job < PROFIT.length; job++) {
                if (!used[job]) {
                    bestRemaining = Math.max(
                            bestRemaining, PROFIT[r][job]);
                }
            }
            upper += bestRemaining;
        }
        return upper;
    }

    static void dfs(int worker, boolean[] used, int[] jobs,
                    int score, boolean preferHighProfit, Stats stats) {
        stats.nodes++;

        if (worker == PROFIT.length) {
            stats.leaves++;

            if (stats.firstJobs == null) {
                stats.firstValue = score;
                stats.firstJobs = jobs.clone();
            }

            if (score > stats.bestValue) {
                stats.bestValue = score;
                stats.bestJobs = jobs.clone();
            }
            return;
        }

        if (optimisticBound(worker, used, score) <= stats.bestValue) {
            stats.pruned++;
            return;
        }

        List<Integer> options = new ArrayList<>();
        for (int job = 0; job < PROFIT.length; job++) {
            if (!used[job]) {
                options.add(job);
            }
        }

        if (preferHighProfit) {
            options.sort((a, b) -> {
                int byProfit = Integer.compare(
                        PROFIT[worker][b], PROFIT[worker][a]);
                return byProfit != 0
                        ? byProfit : Integer.compare(a, b);
            });
        }

        for (int job : options) {
            used[job] = true;
            jobs[worker] = job;
            dfs(worker + 1, used, jobs,
                    score + PROFIT[worker][job],
                    preferHighProfit, stats);
            jobs[worker] = -1;
            used[job] = false;
        }
    }

    static Stats run(boolean preferHighProfit) {
        Stats stats = new Stats();
        int n = PROFIT.length;
        int[] jobs = new int[n];
        Arrays.fill(jobs, -1);

        dfs(0, new boolean[n], jobs, 0, preferHighProfit, stats);
        return stats;
    }

    public static void main(String[] args) {
        Stats ascending = run(false);
        Stats highFirst = run(true);

        System.out.println("Ascending: first=" + ascending.firstValue
                + ", optimum=" + ascending.bestValue
                + ", nodes=" + ascending.nodes
                + ", leaves=" + ascending.leaves
                + ", pruned=" + ascending.pruned);

        System.out.println("High-profit-first: first="
                + highFirst.firstValue
                + ", optimum=" + highFirst.bestValue
                + ", nodes=" + highFirst.nodes
                + ", leaves=" + highFirst.leaves
                + ", pruned=" + highFirst.pruned);

        System.out.println("Best job indices: "
                + Arrays.toString(highFirst.bestJobs));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 AssignmentValueOrderBnBDemo.java
java AssignmentValueOrderBnBDemo
```

Stdout:

```text
Ascending: first=10, optimum=24, nodes=12, leaves=4, pruned=1
High-profit-first: first=24, optimum=24, nodes=7, leaves=1, pruned=3
Best job indices: [1, 2, 0]
```

Trong **ví dụ cụ thể này**, thử lợi nhuận cao trước tìm một nghiệm tối ưu ngay tại lá đầu tiên và cắt thêm nhiều nhánh, giảm số nút từ 12 xuống 7.

**Không suy rộng:** heuristic chọn lợi nhuận cao nhất của người hiện tại có thể dẫn tới nghiệm kém ở các ma trận khác vì công việc tốt nhất cho người này có thể còn quan trọng hơn với người khác. Thuật toán vẫn tối ưu nhờ **duyệt hoặc cắt bằng bound**, không phải nhờ chọn giá trị cục bộ.

**Chi phí:** với n người và n công việc, số phép gán đầy đủ không ràng buộc bổ sung là n!, do đó backtracking có thể tăng rất nhanh. Mỗi nút ở bản minh họa tính upper bound bằng cách quét người/công việc còn lại, và sắp các ứng viên theo điểm; những chi phí này cũng phải tính khi đánh giá tổng thời gian. `int` chỉ phù hợp với điểm nhỏ của ví dụ, cần kiểm tra tràn hoặc dùng `long` cho dữ liệu lớn.

## 14. Độ phức tạp và lý do heuristic không loại bỏ tính hàm mũ

Nếu có n biến, mỗi biến có tối đa d giá trị, cây tìm kiếm đầy đủ có thể có tới:

`1 + d + d² + ... + d^n = O(d^n)` nút

khi d>1 và không có cắt đủ mạnh. Với bài hoán vị n đối tượng, số lá có thể là `n!`; tổng số nút cùng bậc tăng nhanh.

**Chọn thứ tự không thay đổi tập nghiệm** nhưng có thể thay đổi:

- Bao nhiêu nút thất bại bị phát hiện sớm.
- Số lần đánh giá ràng buộc/miền.
- Số lần sao chép hoặc hoàn tác trạng thái.
- Thời điểm tìm thấy nghiệm đầu tiên.
- Thời điểm tìm thấy incumbent tốt, nhờ đó số nhánh bị branch-and-bound cắt.
- Thứ tự xuất nghiệm khi liệt kê.

### 14.1. Overhead của MRV

Nếu mỗi nút chọn biến bằng cách **tính lại miền** của tất cả n biến chưa gán, mỗi miền kiểm tới d giá trị và kiểm tra nhiều ràng buộc, chi phí chọn biến có thể đáng kể. Tùy cách lưu dữ liệu, một lần chọn có thể tốn nhiều hơn `O(n d)` khi mỗi giá trị phải kiểm tra nhiều hàng xóm.

Có thể tối ưu bằng:

- Lưu domain hiện tại bằng bitmask/bitset.
- Duy trì số giá trị còn lại và cập nhật sau mỗi phép lan truyền.
- Giữ hàng đợi các biến miền đơn trị.
- Duy trì danh sách biến chưa gán.
- Chỉ tính lại thông tin của các biến thật sự bị ảnh hưởng.
- Dùng trail để hoàn tác thay vì copy toàn bộ state.

Nhưng mọi cache hoặc tối ưu dữ liệu cần đảm bảo **đúng sau rollback**; cache không nhất quán có thể làm kết quả sai.

### 14.2. Overhead của LCV

LCV có thể thử **tạm từng giá trị ứng viên**, tính tác động lên hàng xóm và sắp thứ tự. Nếu mỗi giá trị có nhiều hàng xóm hoặc cần lan truyền mạnh, điểm số có thể đắt.

Với bài có rất ít nhánh, chi phí tính LCV có thể lớn hơn số nút tiết kiệm được. Nên đo **thời gian thực, số nút, số lần kiểm tra ràng buộc và số lần propagation**, không chỉ đếm độ sâu cây.

### 14.3. Không có bảo đảm luôn tốt

MRV, degree và LCV là những **heuristic hiệu quả trong nhiều CSP**, nhưng không bảo đảm thời gian đa thức hay tốt hơn thứ tự cố định trên mọi trường hợp. Đối với bài có ít biến/miền nhỏ và dễ giải, thứ tự cố định có thể nhanh hơn do overhead thấp.

## 15. Biến thể thứ tự và bài toán đặc thù

### 15.1. Graph coloring

- **Biến:** đỉnh chưa tô.
- **Miền:** màu chưa trùng với màu các đỉnh kề đã tô.
- **MRV:** ưu tiên đỉnh có ít màu còn lại.
- **Degree tie-break:** ưu tiên đỉnh ảnh hưởng nhiều đỉnh chưa tô.
- **LCV:** ưu tiên màu làm các hàng xóm còn nhiều màu.

Nếu cần tìm số màu **ít nhất**, ngoài chọn thứ tự còn phải thiết kế cách thử giới hạn màu/branch-and-bound; giải bài k-colorability với k cố định khác với tối ưu chromatic number.

### 15.2. Sudoku

- **Biến:** ô chưa điền.
- **Miền:** chữ số còn hợp lệ theo hàng, cột, hộp.
- **MRV:** chọn ô ít chữ số khả thi nhất, đặc biệt miền một phần tử.
- **Degree:** nếu hòa, chọn ô ràng buộc với nhiều ô chưa điền nhất.
- **LCV:** thử chữ số ít cản trở các ô kề theo ràng buộc trước.

Trong Sudoku nâng cao, các quy tắc như hidden single, naked pair hoặc các chiến lược đặc thù tạo **lan truyền ràng buộc**, không chỉ thay đổi thứ tự.

### 15.3. N-Queens

- **Biến có thể là hàng**, miền là cột.
- Nếu luôn chọn hàng kế tiếp, đây là **thứ tự biến cố định**.
- Nếu chọn hàng nào có ít cột hợp lệ nhất, đây là **thứ tự biến động**; kiểm tra xung đột phải xét **tất cả** các hàng đã đặt.
- Thử cột giữa/trái/phải trước là **thứ tự giá trị**.
- Nếu chỉ cần đếm nghiệm, thứ tự cột không thay đổi tập nghiệm khi mọi nhánh được duyệt đầy đủ.

### 15.4. Xếp lịch và phân công tài nguyên

- **Biến:** công việc, ca làm hoặc nhân viên.
- **Miền:** thời gian, phòng, người phụ trách.
- **MRV:** công việc chỉ còn ít khung giờ hợp lệ.
- **Degree:** công việc xung đột với nhiều công việc chưa xếp.
- **LCV:** chọn khung giờ ít chặn các công việc khác.
- **Ràng buộc toàn cục:** số phòng, ca tối đa, không trùng lịch, năng lực và nghỉ bắt buộc có thể yêu cầu propagation mạnh hơn chỉ đếm hàng xóm.

### 15.5. Sinh tổ hợp và hoán vị có yêu cầu thứ tự

Nếu đề yêu cầu **in mọi hoán vị theo thứ tự từ điển**, việc cố định vị trí từ trái sang phải và duyệt giá trị tăng là một phần của **hợp đồng đầu ra**. Thay bằng MRV có thể xuất các nghiệm đúng nhưng **sai thứ tự yêu cầu**.

Đối với liệt kê tổ hợp không phân biệt thứ tự, cần ràng buộc chỉ số tăng để tránh sinh cùng tổ hợp theo nhiều hoán vị. Đây là **thiết kế biểu diễn/tập nghiệm**, không đơn thuần là heuristic thứ tự biến.

### 15.6. SAT và các chiến lược nâng cao

Trong SAT (các biến Boolean và ràng buộc mệnh đề), việc chọn biến quyết định và chọn cực tính (`true`/`false` trước) là những dạng variable/value ordering. Bộ giải hiện đại có thể dùng các điểm hoạt động biến, learning từ xung đột, restarts và lan truyền đơn vị; đây là các kỹ thuật vượt xa MRV/LCV cơ bản.

Không nên cố áp LCV dựa vào số hàng xóm đồ thị cho mọi mô hình SAT mà không xét cấu trúc mệnh đề và cơ chế lan truyền riêng.

## 16. Thứ tự ngẫu nhiên, tie-break và tái lập kết quả

Đôi khi ta muốn thay đổi thứ tự để thoát khỏi một mẫu nhánh khó:

- Shuffle danh sách biến hòa điểm.
- Shuffle giá trị khi hòa điểm LCV.
- Dùng seed để tạo thứ tự giả ngẫu nhiên có thể tái lập.

Thứ tự ngẫu nhiên vẫn **bảo toàn tính đầy đủ** nếu chỉ hoán vị các ứng viên được xét, không âm thầm bỏ một số ứng viên. Nhưng nó làm thứ tự nghiệm đầu tiên và hiệu năng khó dự đoán hơn.

Đối với bài học, kiểm thử, và hệ thống yêu cầu đầu ra ổn định, nên đặt tie-break cụ thể:

- MRV nhỏ nhất.
- Degree lớn nhất.
- Chỉ số biến nhỏ nhất.
- LCV impact nhỏ nhất.
- Giá trị số nhỏ nhất.

Ở chương trình CSP phía trên, chính sách này được mã hóa rõ trong vòng chọn biến và comparator giá trị. **Không dựa vào thứ tự duyệt của HashMap** để suy ra tie-break cố định.

## 17. Sai lầm thường gặp và cách sửa

### 17.1. Nhầm chọn biến với chọn giá trị

MRV quyết định **biến X nào**; LCV quyết định **giá trị v nào cho X**. Viết “MRV thử màu xanh trước” mà không giải thích là đang chọn màu cho biến nào sẽ lẫn hai vấn đề.

### 17.2. Dùng miền gốc thay vì miền còn lại

Sau nhiều phép gán, domain bị thu hẹp. Nếu MRV chỉ so kích thước miền gốc, nó không phản ánh trạng thái hiện tại; cần tính/duy trì miền còn lại một cách nhất quán.

### 17.3. Cắt bỏ giá trị có điểm LCV thấp

LCV chỉ xếp thứ tự, không phải tiêu chuẩn loại nghiệm. Nếu bỏ các giá trị “xấu” mà không có chứng minh an toàn, có thể đánh mất nghiệm duy nhất.

### 17.4. Không xử lý miền rỗng

Nếu một biến chưa gán không còn giá trị, nhánh không có nghiệm. Cần quay lui và hoàn tác chứ không tiếp tục gán các biến khác.

### 17.5. Quên hoàn tác phép gán

Sau khi đệ quy xong một nhánh, biến được chọn phải trở về **trạng thái chưa gán** trước khi thử giá trị khác. Nếu không, các phép thử sau bị chi phối bởi nhánh trước.

### 17.6. Quên hoàn tác propagation

Nếu forward checking/AC-3 xóa ứng viên khỏi nhiều domain, phải khôi phục tất cả thay đổi, không chỉ xóa assignment của biến vừa thử.

### 17.7. Cập nhật LCV bằng phép thử tạm nhưng không rollback

Khi chấm tác động của X=a, phải trả X về chưa gán và phục hồi mọi miền bị thay đổi trước khi chấm X=b. Comparator có tác dụng phụ không được hoàn tác sẽ làm kết quả phụ thuộc thứ tự gọi so sánh.

### 17.8. Tính degree gồm cả những biến đã gán

Để phá hòa MRV theo mức ảnh hưởng tương lai, nên đếm **hàng xóm chưa gán**. Nếu chỉ đếm degree tĩnh, vẫn là heuristic khác có thể dùng, nhưng không phản ánh đúng khái niệm *dynamic degree* đã mô tả.

### 17.9. Dùng MRV với hàm kiểm tra sai ngữ nghĩa

Trong N-Queens, nếu gán hàng theo thứ tự bất kỳ, hàm an toàn phải so với **tất cả các hàng đã gán**; hàm chỉ kiểm tra hàng trước đó theo chỉ số không còn đúng.

### 17.10. Dừng ở nghiệm đầu rồi gọi đó là nghiệm tối ưu

Nghiệm hợp lệ đầu tiên chưa chắc có giá trị mục tiêu tốt nhất. Muốn tối ưu cần duyệt hoặc cắt nhánh bằng bound phù hợp.

### 17.11. Cắt nhánh theo một ước lượng không an toàn

Branch-and-bound cần **chặn trên thực sự** khi cực đại hoặc **chặn dưới thực sự** khi cực tiểu. Một dự đoán lợi nhuận “có vẻ cao” nhưng đôi khi thấp hơn optimum thực tế không được dùng làm chặn cắt.

### 17.12. Quên yêu cầu nghiệm từ điển nhỏ nhất

MRV có thể phát hiện nghiệm nhanh nhưng không bảo đảm nghiệm đầu tiên là nhỏ nhất theo thứ tự từ điển của các biến đầu vào. Nếu đề bắt buộc thứ tự xuất nghiệm, phải tuân thủ hoặc thiết kế bước sắp/so sánh riêng.

### 17.13. Báo cáo tốc độ chỉ bằng số nút

Nếu heuristic giảm 10% số nút nhưng làm số phép kiểm tra miền mỗi nút tăng nhiều lần, thời gian tổng có thể cao hơn. Cần đo cả `calls`, `tries`, `constraintChecks` và wall-clock khi so sánh thực tế.

### 17.14. Không kiểm tra dữ liệu CSP ban đầu

Một Sudoku đã có hai số trùng ở hàng cho trước không phải một puzzle hợp lệ. Một graph coloring với miền rỗng từ đầu vô nghiệm ngay. Chọn biến tốt không sửa được **đầu vào không nhất quán**.

### 17.15. Phụ thuộc thứ tự lặp không xác định

Nếu dùng `HashSet`/`HashMap` để chứa ứng viên, thứ tự duyệt có thể thay đổi. Muốn output tái lập, phải sắp hoặc dùng cấu trúc/thứ tự được chỉ định.

### 17.16. Hiểu MRV như thuật toán có bảo đảm đa thức

Trong bài khó, mọi thứ tự có thể vẫn dẫn tới cây tìm kiếm hàm mũ. MRV/LCV là heuristic hữu dụng, không làm CSP tổng quát trở nên dễ giải trong mọi trường hợp.

## 18. Kiểm thử thứ tự biến/giá trị một cách công bằng

### 18.1. Ba nhóm kiểm tra

**Tính đúng:**

- Mọi nghiệm được in thỏa miền gốc và tất cả ràng buộc.
- Mỗi biến bắt buộc được gán đúng một lần.
- Không trả nghiệm nếu còn biến chưa gán.
- Bản có heuristic và bản cố định có **cùng tập nghiệm** khi yêu cầu liệt kê toàn bộ.

**Hoàn tác:**

- Chạy lại từ trạng thái ban đầu cho kết quả như cũ.
- Sau một nhánh thất bại, mọi assignment/domain/trail trở về trạng thái đúng trước nhánh.
- Hàm chấm MRV/LCV không để lại tác dụng phụ.

**Hiệu năng:**

- `calls`: số nút/hàm search được thăm.
- `tries`: số gán giá trị được thử.
- `pruned`: số nhánh bị loại theo quy tắc an toàn.
- `constraintChecks`, `domainRecomputations`, `propagationSteps`: chi phí thực của heuristic.
- Thời gian chạy trên **cùng input, cùng máy, cùng cách đo**, có warmup và nhiều lần chạy nếu muốn so sánh microbenchmark Java.

### 18.2. Những trường hợp biên

| Tình huống | Kỳ vọng |
|---|---|
| Không có biến | Có **một phép gán rỗng** nếu mọi ràng buộc đều thỏa |
| Một biến với một giá trị | Một nghiệm nếu giá trị hợp lệ |
| Một biến có miền rỗng | Không có nghiệm |
| Hai biến `A!=B`, cả hai chỉ có giá trị 1 | Không có nghiệm |
| Hai biến độc lập, mỗi biến có 2 giá trị | `2×2=4` nghiệm |
| Một CSP có nhiều nghiệm | Các thứ tự có thể đổi nghiệm đầu, không đổi tập nghiệm |
| Một CSP có nghiệm duy nhất | Mọi chiến lược đầy đủ trả đúng nghiệm đó |
| Biến có miền đơn trị | MRV thường ưu tiên nó |
| Hai biến cùng MRV nhưng degree khác | Degree chọn biến có nhiều hàng xóm chưa gán hơn |
| Hai giá trị hòa LCV | Thứ tự tie-break phải xác định nếu cần tái lập |
| Tất cả nghiệm bị cắt bằng kiểm tra hợp lệ | Không được báo có nghiệm |
| Tối ưu có hai nghiệm cùng giá trị | Cắt `bound<=best` không phù hợp nếu cần liệt kê **cả hai** |

### 18.3. Oracle độc lập cho CSP nhỏ

Với bốn biến của phần 7, liệt kê tất cả tổ hợp miền gốc:

- A có 3 giá trị, B có 2, C có 2, D có 3 ⇒ **36 phép gán thô**.
- Kiểm bốn ràng buộc `!=` để lọc.
- Đúng **6 nghiệm**.

Có thể so tập nghiệm thu được từ bộ giải cố định và MRV/LCV với oracle 36 phép gán. Nếu tập nghiệm thiếu hoặc thừa, lỗi không chỉ ở hiệu năng thứ tự mà ở **tính đúng/hợp lệ của bước quay lui**.

Với N-Queens `n=4`, có đúng **2 nghiệm**; với Sudoku 4×4 của phần 11, có đúng **1 nghiệm**. Những kết quả này hữu ích để kiểm tra nhưng không chứng minh tổng quát; chứng minh nằm ở bất biến duyệt và quy tắc cắt an toàn.

## 19. Bài tập tự luyện và đáp án

### Bài 1 — Chọn biến MRV

Các biến chưa gán X,Y,Z còn lần lượt 4,1,3 giá trị. Chọn biến nào theo MRV?

**Đáp án:** Y, vì miền hiện tại có một giá trị, ít nhất trong ba biến.

### Bài 2 — Phá hòa bằng degree

A và B đều còn 2 giá trị. A có 5 hàng xóm chưa gán, B có 2. Chọn biến nào theo MRV + degree?

**Đáp án:** A, vì MRV hòa và A ảnh hưởng nhiều biến chưa gán hơn.

### Bài 3 — Tác động LCV

Biến X còn hai giá trị p,q. Thử p làm các hàng xóm mất 7 lựa chọn; thử q chỉ mất 3. Giá trị thử trước?

**Đáp án:** q theo LCV, vì impact=3 nhỏ hơn 7. Điều này không chứng minh nhánh q chắc chắn có nghiệm.

### Bài 4 — CSP bốn biến

Với `A∈{1,2,3}`, `B∈{1,2}`, `C∈{2,3}`, `D∈{1,2,3}` và cạnh ràng buộc A−B, A−C, B−C, C−D, biến nào được MRV + degree chọn ban đầu?

**Đáp án:** C. B và C cùng miền 2, nhưng C có 3 hàng xóm chưa gán còn B có 2.

### Bài 5 — LCV sau khi chọn C

Với CSP ở bài 4, giữa `C=2` và `C=3` thì LCV thử giá trị nào trước?

**Đáp án:** `C=3`. Điểm tác động lên A/B/D lần lượt cho C=2 là 3, còn C=3 là 2.

### Bài 6 — Nghiệm đầu tiên khác nhau

Với N-Queens n=4 và hàng xử lý tăng dần, thử cột tăng và cột giảm cho hai nghiệm đầu khác nhau. Tại sao số nghiệm đếm hết vẫn bằng nhau?

**Đáp án:** thứ tự chỉ hoán vị các nhánh giá trị; cả hai duyệt tất cả vị trí hợp lệ, nên cùng hai nghiệm, dù nghiệm đầu là `[1,3,0,2]` hoặc `[2,0,3,1]`.

### Bài 7 — Quên hoàn tác

Trong graph coloring, sau khi thử `A=đỏ`, solver xóa đỏ khỏi miền B; nhánh thất bại và bỏ A, nhưng không trả màu đỏ vào miền B. Hệ quả?

**Đáp án:** nhánh mới có thể thiếu một giá trị hợp lệ của B, khiến solver bỏ sót nghiệm. Cần dùng copy domain hoặc undo log và rollback đầy đủ.

### Bài 8 — Chứng minh tính đầy đủ

Tại một nút, thuật toán chọn biến X bất kỳ rồi thử lần lượt mọi giá trị hợp lệ của X. Tại sao một nghiệm hoàn chỉnh T không bị bỏ sót chỉ do thay thứ tự biến?

**Đáp án:** T có một giá trị `T[X]` thuộc miền X. Vì nhánh đó được thử, và các kiểm tra cắt chỉ loại những nhánh vô nghiệm, có một nhánh chứa T. Quy nạp theo số biến chưa gán cho kết luận.

### Bài 9 — Nghiệm từ điển nhỏ nhất

Đề yêu cầu in nghiệm thỏa mãn nhỏ nhất theo thứ tự `[A,B,C]`. Có nên dùng MRV tùy ý rồi dừng ở nghiệm đầu không?

**Đáp án:** không bảo đảm. Nghiệm đầu của MRV có thể khác thứ tự từ điển; cần thiết kế thứ tự xuất phù hợp hoặc duyệt/so sánh để lấy nghiệm nhỏ nhất.

### Bài 10 — Branch-and-bound

Ở bài cực đại, incumbent bằng 20, một nhánh có upper bound chứng minh bằng 18. Có thể cắt nhánh không?

**Đáp án:** có, vì dù hoàn thiện tốt nhất nhánh cũng không vượt 18, kém 20. Nhưng một **dự đoán** không phải bound chắc chắn thì không đủ lý do cắt.

### Bài 11 — Cắt khi bằng incumbent

Ở bài cực đại, bound của nhánh bằng incumbent. Nếu đề yêu cầu **liệt kê tất cả nghiệm tối ưu**, có nên cắt ngay với `bound<=incumbent` không?

**Đáp án:** không, vì nhánh có thể chứa nghiệm khác **đúng bằng** incumbent. Muốn liệt kê mọi nghiệm tối ưu phải có chính sách duyệt và lưu tất cả các nhánh có thể đạt giá trị bằng optimum.

### Bài 12 — Tính số tổ hợp thô

Bốn biến có miền gốc kích thước 3,2,2,3. Nếu chưa xét ràng buộc, có bao nhiêu phép gán đầy đủ?

**Đáp án:** `3×2×2×3=36`. MRV/LCV không làm biến mất các phép gán khả thi theo toán học; nó chỉ có thể giúp loại sớm những phép gán không thể là nghiệm.

### Bài 13 — Sudoku MRV

Với Sudoku 4×4, một ô chỉ còn đúng một chữ số hợp lệ, các ô khác còn 2–4 chữ số. MRV nên chọn ô nào?

**Đáp án:** ô chỉ còn một chữ số. Nếu sau propagation có ô domain rỗng, phải quay lui ngay.

### Bài 14 — Overhead heuristic

Cùng một puzzle, MRV giảm từ 1000 xuống 900 nút nhưng phải kiểm tra miền tốn gấp 5 lần mỗi nút. Có thể kết luận MRV nhanh hơn không?

**Đáp án:** không. Số nút chỉ là một thước đo; cần tính chi phí mỗi nút và đo thời gian thực. Lợi ích phụ thuộc số lần kiểm tra ràng buộc và cấu trúc dữ liệu.

### Bài 15 — Chọn ưu tiên cho tối ưu

Trong bài phân công W0/W1/W2, thử việc có lợi nhuận cao nhất của mỗi người trước tạo nghiệm giá trị 24 sớm. Điều gì đảm bảo thuật toán luôn trả optimum?

**Đáp án:** thuật toán branch-and-bound tiếp tục duyệt các nhánh chưa bị loại, và chỉ loại nhánh bằng **chặn trên hợp lệ** không thể vượt incumbent. Thứ tự lợi nhuận chỉ giúp có incumbent tốt sớm hơn.

## 20. Checklist áp dụng cho một bài quay lui mới

1. **Xác định mục tiêu:** tìm một nghiệm, mọi nghiệm, nghiệm nhỏ nhất từ điển hay nghiệm tối ưu?
2. **Xác định biến:** những quyết định nào bắt buộc phải gán?
3. **Định nghĩa miền của mỗi biến:** có cố định hay thay đổi theo các biến đã gán?
4. **Viết ràng buộc rõ ràng:** kiểm tra được từng phần hay chỉ khi hoàn chỉnh?
5. **Quyết định thứ tự biến:** cố định, MRV động, degree phá hòa hay chiến lược chuyên biệt?
6. **Nếu dùng MRV, miền còn lại có được tính đúng từ trạng thái hiện tại không?**
7. **Nếu miền rỗng, có cắt nhánh ngay một cách an toàn không?**
8. **Quyết định thứ tự giá trị:** tăng, giảm, LCV, lợi nhuận cao hay ưu tiên đặc thù đề?
9. **Heuristic có chỉ sắp thứ tự, không bỏ ứng viên khi thiếu chứng minh không?**
10. **Sau khi gán, có kiểm tra mọi ràng buộc liên quan không?**
11. **Có forward checking/propagation phù hợp không?** Nếu có, rollback đầy đủ?
12. **Khi quay lui, mọi biến/domain/cache/trail có trở về trạng thái chính xác không?**
13. **Nếu cần từ điển nhỏ nhất, thứ tự tìm kiếm có khớp yêu cầu không?**
14. **Nếu có tối ưu, bound cắt nhánh có thật sự an toàn không?**
15. **Có quy tắc tie-break để chạy tái lập không?** Khi dùng random, seed có được lưu?
16. **Độ phức tạp còn có thể hàm mũ không?** Đừng coi heuristic là chứng minh thời gian đa thức.
17. **Đã thử input biên?** Miền rỗng, miền đơn trị, không biến, vô nghiệm, nhiều nghiệm, đầu vào mâu thuẫn.
18. **Đã so tập nghiệm với oracle trên bài nhỏ chưa?** Không chỉ so nghiệm đầu.
19. **Đã đo cả số nút và overhead MRV/LCV chưa?** Kiểm tra hiệu năng trên nhiều bộ dữ liệu.
20. **Khi đổi thứ tự biến, hàm kiểm tra hợp lệ có còn đúng không?** Đặc biệt N-Queens hoặc các hàm chỉ xét “các biến trước”.

**Ghi nhớ:** thứ tự biến quyết định **giải quyết biến nào trước**; thứ tự giá trị quyết định **thử lựa chọn nào trước**. MRV và degree hướng tới phát hiện ràng buộc khó sớm, LCV hướng tới giữ nhiều lựa chọn cho bước tiếp theo. Các heuristic có thể thay đổi mạnh thời điểm tìm thấy nghiệm và số nút phải duyệt, nhưng **không được bỏ giá trị/nhánh chỉ vì chúng có điểm heuristic thấp**. Tính đúng và tính đầy đủ đến từ duyệt đủ những nhánh khả thi, kiểm tra/cắt an toàn và **hoàn tác trạng thái chính xác**.
