# Thiết kế giá trị trả về để kết hợp đủ thông tin trong chia để trị

Một lời gọi đệ quy không nhất thiết chỉ trả về **đáp án cuối cùng của đoạn con**. Trong nhiều thuật toán **chia để trị (divide and conquer)**, muốn kết hợp hai kết quả con thành đáp án của đoạn cha, mỗi nhánh còn phải trả về những **thông tin phụ trợ**: tổng, biên, chiều cao, tiền tố tốt nhất, hậu tố tốt nhất, trạng thái ràng buộc hoặc một bản tóm tắt khác.

**Nguyên tắc trọng tâm:** Giá trị trả về của bài toán con phải là một *bản tóm tắt đủ thông tin để kết hợp* (sufficient summary). Nếu chỉ giữ đáp án cục bộ mà làm mất thông tin về cách đoạn con tương tác với đoạn còn lại, hàm kết hợp sẽ không thể suy ra đáp án đúng của đoạn cha.

Bài học giải thích cách chọn trạng thái trả về, chứng minh công thức kết hợp, xử lý ranh giới và áp dụng qua hai ví dụ điển hình:

1. **Đoạn con có tổng lớn nhất (maximum subarray)**: mỗi nhánh trả về tổng toàn đoạn, tiền tố tốt nhất, hậu tố tốt nhất và đoạn tốt nhất.
2. **Đường kính cây nhị phân (tree diameter)**: mỗi nhánh trả về đồng thời chiều cao và đường kính.

Hai ví dụ cho thấy cùng một tư duy có thể áp dụng cho cả **mảng chia đôi** lẫn **cây chia theo nhánh**.

## 1. Nhìn từ cấu trúc của thuật toán chia để trị

Một bài toán chia để trị thường có ba phần:

- **Chia (divide):** chia bài toán kích thước n thành các bài toán con nhỏ hơn.
- **Giải (conquer):** giải từng bài toán con, thường bằng đệ quy.
- **Kết hợp (combine):** dùng kết quả các bài toán con để tạo kết quả của bài toán lớn hơn.

Ví dụ khung tổng quát:

~~~text
solve(problem):
    if problem là trường hợp cơ sở:
        return summaryBase(problem)

    leftProblem, rightProblem = split(problem)
    leftSummary  = solve(leftProblem)
    rightSummary = solve(rightProblem)

    return combine(leftSummary, rightSummary)
~~~

Trong khung này, kiểu trả về không nhất thiết trùng với kiểu của **câu trả lời cuối cùng**. Hàm solve có thể trả một **record/tuple nhiều trường**, còn hàm ngoài cùng chỉ lấy trường được người dùng yêu cầu.

Cần phân biệt:

- **Đáp án đầu ra:** thông tin cuối cùng đề bài muốn, ví dụ tổng lớn nhất là bao nhiêu.
- **Trạng thái kết hợp:** thông tin cần truyền lên cha để tính cả đáp án và các trường cần cho những cấp cao hơn.
- **Dữ liệu gốc:** mảng/cây vẫn được truyền hoặc truy cập theo phạm vi hợp lệ; trạng thái trả về không nên sao chép toàn bộ dữ liệu nếu không cần.

Mục tiêu thiết kế không phải “trả về càng nhiều càng tốt”, mà là trả về **đúng những thông tin đủ**, với kích thước và chi phí kết hợp phù hợp.

## 2. Vì sao chỉ trả đáp án cục bộ có thể sai?

Xét bài toán **tìm đoạn con liên tiếp không rỗng có tổng lớn nhất**. Với mỗi đoạn, ta có thể biết đoạn con có tổng lớn nhất *nằm hoàn toàn trong đoạn đó*. Nhưng khi ghép hai nửa, đoạn tối ưu của đoạn cha có thể **bắt đầu bên trái và kết thúc bên phải**.

Ví dụ:

~~~text
Trái:  [ 4, -1]
Phải: [ 2,  1]

Đáp án nằm trong trái:  4
Đáp án nằm trong phải: 3
Đáp án của cả đoạn:   6 từ [4, -1, 2, 1]
~~~

Nếu hai nhánh chỉ trả **bestLeft = 4** và **bestRight = 3**, hàm cha không biết liệu có đoạn băng qua điểm chia với tổng 6 hay không. Để tính đoạn băng qua biên, cần:

- **Hậu tố có tổng lớn nhất của nửa trái**.
- **Tiền tố có tổng lớn nhất của nửa phải**.

Và để cha tiếp tục tính tiền tố/hậu tố của chính nó khi ghép với đoạn khác, còn cần **tổng toàn bộ hai nửa**.

Một ví dụ khác là **đường kính cây nhị phân**: chỉ biết đường kính của cây con trái và phải chưa đủ. Đường đi dài nhất của cây cha có thể đi từ nút sâu nhất ở cây con trái, **qua gốc**, sang nút sâu nhất ở cây con phải; vì vậy còn cần **chiều cao của mỗi cây con**.

Hai phản ví dụ chứng tỏ: **“trả lời được cho đoạn con” không đồng nghĩa với “kết hợp được ở đoạn cha”.**

## 3. Phương pháp thiết kế một summary đủ thông tin

Có thể tiếp cận có hệ thống bằng năm câu hỏi.

### Câu hỏi 1 — Đáp án của cha có những dạng nào?

Phân loại mọi khả năng để không bỏ sót. Với đoạn con lớn nhất, đáp án của cha hoặc:

1. Nằm **hoàn toàn trong nửa trái**.
2. Nằm **hoàn toàn trong nửa phải**.
3. **Cắt qua ranh giới** giữa hai nửa.

Với đường kính cây, đường đi dài nhất hoặc nằm trong cây con trái, trong cây con phải, hoặc đi qua nút gốc hiện tại.

Chỉ sau khi phân loại đủ các trường hợp mới quyết định dữ liệu cần lấy từ nhánh con.

### Câu hỏi 2 — Muốn tính từng trường hợp, cha cần gì?

Viết công thức kết hợp trước, rồi liệt kê mọi đại lượng mà công thức cần đọc từ con.

- Muốn tính **đáp án cắt qua biên**: cần suffix tốt nhất ở trái + prefix tốt nhất ở phải.
- Muốn tính **prefix tốt nhất của cha**: cần prefix trái, tổng toàn trái và prefix phải.
- Muốn tính **suffix tốt nhất của cha**: cần suffix phải, tổng toàn phải và suffix trái.
- Muốn tính **đường đi qua gốc cây**: cần chiều cao trái và phải.

Nếu một công thức yêu cầu truy cập phần tử ở ngoài trạng thái trả về, đó là tín hiệu cần **bổ sung trường** hoặc chấp nhận quét lại dữ liệu (có thể làm tăng độ phức tạp).

### Câu hỏi 3 — Trạng thái có tự đóng dưới phép kết hợp không?

**Đóng dưới combine (closure)** nghĩa là: kết hợp hai summary hợp lệ phải tạo được **một summary cùng cấu trúc và ý nghĩa** cho cha.

Ví dụ, nếu kiểu kết quả của đoạn con là (total, prefix, suffix, best), thì combine phải tính được **cả bốn trường** của đoạn lớn hơn, chứ không chỉ best. Nhờ vậy kết quả có thể tiếp tục kết hợp ở cấp cao hơn mà không cần biết cách các nhánh đã được chia.

### Câu hỏi 4 — Cơ sở, đoạn rỗng và các phần tử bằng nhau được định nghĩa ra sao?

Phải quyết định:

- Bài có cho phép **đoạn con rỗng** không? Nếu không, ở mảng toàn số âm, đáp án phải là **số âm lớn nhất**, không tự động là 0.
- Mảng rỗng trả gì: giá trị đặc biệt, Optional, null hay ngoại lệ?
- Với nhiều đáp án cùng chất lượng, chọn **vị trí nào**: bắt đầu sớm nhất, đoạn ngắn nhất, kết thúc sớm nhất hay tùy ý?
- Trạng thái của nút null trong cây là gì? Đo chiều cao theo **số nút** hay **số cạnh**?

Một công thức đúng nhưng dùng quy ước khác nhau ở các lớp thường gây lỗi off-by-one.

### Câu hỏi 5 — Kết hợp tốn bao nhiêu chi phí?

Nếu một summary có **kích thước hằng** và combine chỉ dùng O(1) phép tính, chia mảng thành hai nửa đưa đến truy hồi:

**T(n) = 2T(n/2) + O(1) = O(n)**.

Nếu combine phải quét lại một đoạn dài n ở mỗi cấp, truy hồi trở thành:

**T(n) = 2T(n/2) + O(n) = O(n log n)**.

Giữ thêm một vài trường thích hợp có thể giảm được **một bậc độ phức tạp**, chứ không chỉ giúp code rõ ràng hơn.

## 4. Ví dụ chính: đoạn con có tổng lớn nhất

Cho mảng số nguyên a[0..n−1]. Cần tìm một **đoạn liên tiếp không rỗng** a[L..R−1] có tổng lớn nhất, với chỉ số nửa mở **[L, R)**.

Ví dụ:

~~~text
a = [4, -1, 2, 1, -5, 4]
     0   1  2  3   4  5

Đoạn tốt nhất: [0,4) = [4, -1, 2, 1]
Tổng lớn nhất: 4 - 1 + 2 + 1 = 6
~~~

Quy ước **không cho phép đoạn rỗng**. Với a = [-8, -3, -6, -2, -5, -4], kết quả là **−2 tại [3,4)**, không phải 0.

### Summary có bốn giá trị cốt lõi

Với một đoạn **[from, to)** không rỗng, lưu:

| Trường | Ý nghĩa |
| --- | --- |
| **total** | Tổng tất cả phần tử trong đoạn |
| **prefix** | Tổng lớn nhất của một **tiền tố không rỗng**, bắt đầu tại from |
| **suffix** | Tổng lớn nhất của một **hậu tố không rỗng**, kết thúc tại to |
| **best** | Tổng lớn nhất của một đoạn con liên tiếp không rỗng nằm bất kỳ trong [from,to) |

Nếu bài chỉ yêu cầu **giá trị tổng**, bốn trường số là đủ. Nếu đề cần **vị trí và đoạn con cụ thể**, phải bổ sung chỉ số bắt đầu/kết thúc của prefix, suffix và best; việc lưu riêng giá trị tổng không đủ để tái tạo vị trí trong mọi trường hợp.

Trong Java ở mục 6, ta lưu mỗi ứng viên bằng **Range(start,end,sum)** và cả summary bằng **Summary(from,to,total,prefix,suffix,best)**. Các khoảng con đều dùng **tọa độ toàn mảng**, thuận tiện khi ghép và in kết quả.

### Trường hợp cơ sở

Đoạn chỉ có một phần tử x tại chỉ số i:

- total = x;
- prefix = suffix = best = **Range(i, i+1, x)**.

Không được lấy **max(0,x)** khi bài **không cho phép đoạn rỗng**, vì sẽ sai trên mảng toàn số âm.

Đoạn rỗng không có prefix/suffix/best không rỗng. Đoạn này có thể dùng một **summary rỗng** với total = 0 và ba trường còn lại là null, miễn là combine **xử lý đoạn rỗng riêng trước khi đọc** các trường ấy.

## 5. Công thức kết hợp summary của hai nửa

Giả sử nửa trái L biểu diễn [from, mid), nửa phải R biểu diễn [mid, to), cả hai không rỗng và **đã có summary đúng**.

**Tổng toàn đoạn:**

**total = L.total + R.total**

**Tiền tố tốt nhất:** hoặc nằm trọn trong trái, hoặc lấy **toàn bộ trái** rồi nối với một tiền tố không rỗng bên phải:

**prefix = max(L.prefix, L.total + R.prefix)**

**Hậu tố tốt nhất:** hoặc nằm trọn trong phải, hoặc lấy một hậu tố không rỗng bên trái rồi nối với **toàn bộ phải**:

**suffix = max(R.suffix, L.suffix + R.total)**

**Đoạn con tốt nhất:** hoặc nằm trọn trái, nằm trọn phải, hoặc đi qua biên:

**best = max(L.best, R.best, L.suffix + R.prefix)**

Đây là bốn công thức quan trọng nhất. Tất cả kết quả đều tính trong **O(1)** nếu mỗi summary mang đủ các trường nói trên.

### Chứng minh ba trường hợp của best là đầy đủ

Mọi đoạn con liên tiếp **[i,j)** nằm trong đoạn cha [from,to) có đúng một trong các quan hệ:

1. j ≤ mid: nằm hoàn toàn bên trái.
2. i ≥ mid: nằm hoàn toàn bên phải.
3. i < mid < j: cắt qua biên.

Trường hợp 1 tốt nhất là **L.best**; trường hợp 2 tốt nhất là **R.best**. Trong trường hợp 3, phần nằm bên trái buộc phải kết thúc ở mid (một hậu tố trái), còn phần bên phải buộc phải bắt đầu ở mid (một tiền tố phải). Hai phần được tối đa hóa độc lập nên tốt nhất bằng **L.suffix + R.prefix**.

Không tồn tại trường hợp thứ tư. Vì vậy phép lấy max giữa ba ứng viên trả đáp án đúng.

### Ví dụ minh họa việc ghép

Với trái **[4, −1]**, ta có:

- total = 3;
- prefix = 4 (đoạn [4]);
- suffix = 3 (đoạn [4,−1]);
- best = 4.

Với phải **[2, 1]**, ta có:

- total = 3;
- prefix = 3;
- suffix = 3;
- best = 3.

Kết hợp:

- total = 3 + 3 = **6**;
- prefix = max(4, 3+3) = **6**;
- suffix = max(3, 3+3) = **6**;
- best = max(4, 3, 3+3) = **6**.

Dù **best trái** chỉ 4 và **best phải** chỉ 3, thông tin suffix/prefix giúp nhận ra đoạn tối ưu tổng 6 **vượt qua ranh giới**. Đây là lý do phải thiết kế giá trị trả về giàu thông tin hơn một đáp án cục bộ.

## 6. Java 17+: maximum subarray với chỉ số và quy tắc phá hòa

Chương trình sau có thể biên dịch độc lập trên JDK 17+. Nó trả **tổng lớn nhất**, **khoảng [start,end)** và có quy tắc xác định khi nhiều đoạn có tổng bằng nhau:

1. Ưu tiên **tổng lớn hơn**.
2. Nếu tổng bằng nhau, ưu tiên **chỉ số bắt đầu nhỏ hơn**.
3. Nếu bắt đầu cũng bằng nhau, ưu tiên **chỉ số kết thúc nhỏ hơn** (đoạn ngắn hơn).

Quy tắc này áp dụng **thống nhất** cho prefix, suffix và best. Chẳng hạn với [1,−1,1], có nhiều đoạn đạt tổng 1, nhưng chương trình chọn **[0,1)**.

~~~java
import java.util.Arrays;

public class SufficientSummaryDemo {

    // Khoang nua mo [start, end), co tong sum.
    record Range(int start, int end, long sum) {}

    // Summary cho doan [from, to).
    // prefix, suffix, best = null chi khi doan rong.
    record Summary(int from, int to, long total,
                   Range prefix, Range suffix, Range best) {}

    // So sanh hai ung vien: tong cao nhat, sau do vi tri som nhat.
    private static Range choose(Range a, Range b) {
        if (a.sum() != b.sum()) {
            return a.sum() > b.sum() ? a : b;
        }
        if (a.start() != b.start()) {
            return a.start() < b.start() ? a : b;
        }
        return a.end() <= b.end() ? a : b;
    }

    // Hai summary cua hai doan lien tiep.
    private static Summary combine(Summary left, Summary right) {
        if (left.to() != right.from()) {
            throw new IllegalArgumentException("Ranges are not adjacent");
        }
        if (left.from() == left.to()) {
            return right;
        }
        if (right.from() == right.to()) {
            return left;
        }

        long total = left.total() + right.total();

        // Prefix: nam o trai, hoac toan trai + prefix phai.
        Range crossPrefix = new Range(
                left.from(), right.prefix().end(),
                left.total() + right.prefix().sum());
        Range prefix = choose(left.prefix(), crossPrefix);

        // Suffix: nam o phai, hoac suffix trai + toan phai.
        Range crossSuffix = new Range(
                left.suffix().start(), right.to(),
                left.suffix().sum() + right.total());
        Range suffix = choose(right.suffix(), crossSuffix);

        // Best: trai, phai, hoac suffix trai + prefix phai.
        Range crossing = new Range(
                left.suffix().start(), right.prefix().end(),
                left.suffix().sum() + right.prefix().sum());
        Range best = choose(
                choose(left.best(), right.best()), crossing);

        return new Summary(
                left.from(), right.to(), total, prefix, suffix, best);
    }

    private static Summary solve(int[] a, int from, int to) {
        if (from == to) {
            return new Summary(from, to, 0L, null, null, null);
        }

        if (to - from == 1) {
            Range one = new Range(from, to, a[from]);
            return new Summary(from, to, a[from], one, one, one);
        }

        int mid = from + (to - from) / 2;
        Summary left = solve(a, from, mid);
        Summary right = solve(a, mid, to);
        return combine(left, right);
    }

    private static void showMaxSubarray(int[] a) {
        Summary answer = solve(a, 0, a.length);
        if (answer.best() == null) {
            System.out.println(Arrays.toString(a)
                    + " -> no non-empty subarray");
            return;
        }

        Range best = answer.best();
        int[] values = Arrays.copyOfRange(
                a, best.start(), best.end());

        System.out.println(Arrays.toString(a)
                + " -> sum=" + best.sum()
                + ", range=[" + best.start()
                + "," + best.end() + ")"
                + ", values=" + Arrays.toString(values));
    }

    // Vi du 2: duong kinh cay theo SO CANH.
    static final class Node {
        final String label;
        Node left;
        Node right;

        Node(String label) {
            this.label = label;
        }
    }

    record TreeInfo(int height, int diameter) {}

    private static TreeInfo treeStats(Node node) {
        if (node == null) {
            // Chieu cao -1 theo so canh; duong kinh cay rong quy uoc 0.
            return new TreeInfo(-1, 0);
        }

        TreeInfo left = treeStats(node.left);
        TreeInfo right = treeStats(node.right);

        int height = Math.max(left.height(), right.height()) + 1;
        int throughRoot = left.height() + right.height() + 2;
        int diameter = Math.max(
                throughRoot,
                Math.max(left.diameter(), right.diameter()));

        return new TreeInfo(height, diameter);
    }

    public static void main(String[] args) {
        showMaxSubarray(new int[] {4, -1, 2, 1, -5, 4});
        showMaxSubarray(new int[] {-8, -3, -6, -2, -5, -4});
        showMaxSubarray(new int[] {1, -1, 1, -1, 1});
        showMaxSubarray(new int[] {2, -4, 3, -1, 2, -5, 4, 1});
        showMaxSubarray(new int[] {});

        Node a = new Node("A");
        Node b = new Node("B");
        Node c = new Node("C");
        Node d = new Node("D");
        Node e = new Node("E");
        Node f = new Node("F");
        a.left = b;
        a.right = c;
        b.left = d;
        b.right = e;
        d.left = f;

        TreeInfo result = treeStats(a);
        System.out.println("Tree: height=" + result.height()
                + ", diameter=" + result.diameter());

        TreeInfo emptyTree = treeStats(null);
        System.out.println("Empty tree: height=" + emptyTree.height()
                + ", diameter=" + emptyTree.diameter());
    }
}
~~~

Lưu vào tệp **SufficientSummaryDemo.java**, biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac SufficientSummaryDemo.java
java SufficientSummaryDemo
~~~

Đầu ra chính xác:

~~~text
[4, -1, 2, 1, -5, 4] -> sum=6, range=[0,4), values=[4, -1, 2, 1]
[-8, -3, -6, -2, -5, -4] -> sum=-2, range=[3,4), values=[-2]
[1, -1, 1, -1, 1] -> sum=1, range=[0,1), values=[1]
[2, -4, 3, -1, 2, -5, 4, 1] -> sum=5, range=[6,8), values=[4, 1]
[] -> no non-empty subarray
Tree: height=3, diameter=4
Empty tree: height=-1, diameter=0
~~~

**Giải thích điểm thiết kế:**

- **Range** chứa đủ chỉ số và tổng để phục hồi đoạn cụ thể. Nếu chỉ lưu sum, sẽ không in được [start,end) mà không có bước tìm lại.
- **Summary** chứa bốn loại thông tin: total, prefix, suffix, best. Trường from/to xác định ranh giới khi nối hai đoạn.
- Hàm **choose** thực hiện một quy tắc hòa *duy nhất* ở mọi cấp: tổng lớn hơn, bắt đầu sớm hơn, rồi kết thúc sớm hơn.
- **combine** không quét lại mảng: nó chỉ đọc hai summary và tạo summary cha trong **O(1)**.
- **solve** xử lý đoạn rỗng trước; trường hợp một phần tử tạo Range không rỗng, kể cả giá trị âm.
- Không có phép nối mảng nào được thực hiện trong lúc tính summary. **Arrays.copyOfRange** chỉ được gọi lúc trình bày đoạn tốt nhất, không phải trong đệ quy.

**Kết quả quan trọng:** khi code chỉ trả tổng lớn nhất nhưng không cần vị trí, có thể thay Range bằng bốn biến số. Khi cần chính xác *đoạn nào*, ta bổ sung vị trí nhưng vẫn giữ chi phí combine O(1).

## 7. Ví dụ thứ hai: đường kính cây nhị phân

**Đường kính của cây (diameter)** là độ dài của đường đi đơn dài nhất giữa hai nút. Ở đây độ dài được tính bằng **số cạnh**, không phải số nút.

Xét cây:

~~~text
        A
       / \
      B   C
     / \
    D   E
   /
  F
~~~

- Đường dài nhất đi từ **F → D → B → A → C**, gồm **4 cạnh**.
- Chiều cao của cây, tính từ gốc A đến lá sâu nhất F, là **3 cạnh**.
- Nếu chỉ trả đường kính của cây con B là 3 và của cây con C là 0, sẽ **thiếu** đường đi dài 4 đi qua A.

Vì vậy, tại mỗi nút, lời gọi đệ quy trả **TreeInfo(height, diameter)**.

### Cơ sở và công thức kết hợp

Quy ước:

- **height(null) = −1** khi tính chiều cao theo số cạnh.
- **diameter(null) = 0** theo quy ước cho cây rỗng.
- Với lá đơn, height = 0 và diameter = 0.

Giả sử có summary trái (hL, dL) và phải (hR, dR):

**height(node) = 1 + max(hL, hR)**

**throughRoot = hL + hR + 2**

**diameter(node) = max(dL, dR, throughRoot)**

Tại sao cộng 2? Đường qua gốc gồm một nhánh đi xuống trái và một nhánh đi xuống phải; hai cạnh từ nút hiện tại sang gốc hai cây con được tính trong biểu thức. Khi một cây con rỗng có height = −1, biểu thức vẫn hoạt động với đường đi một phía. Khi cả hai cây con rỗng, throughRoot = 0, đúng với một lá.

Cần **trả cả height lẫn diameter**. Nếu chỉ trả height, không biết một đường dài có thể nằm hoàn toàn trong một cây con; nếu chỉ trả diameter, không đủ thông tin tạo đường đi xuyên qua nút hiện tại.

Chương trình Java ở mục 6 đã cài **treeStats** đầy đủ và cho kết quả height = 3, diameter = 4 với cây minh họa.

### Phân tích thời gian

Mỗi nút được xử lý một lần và combine chỉ thực hiện vài phép max/cộng. Với n nút:

- **O(n)** thời gian.
- **O(h)** ngăn xếp đệ quy, trong đó h là chiều cao cây theo số nút/cạnh tương ứng; có thể lên tới O(n) với cây rất lệch, hoặc O(log n) với cây cân bằng.
- Summary là vài số nguyên. Bản cài Java tạo một TreeInfo mỗi lời gọi; tổng số đối tượng cấp phát tỉ lệ với số nút.

Nếu tại mỗi nút lại tự duyệt toàn bộ cây con để tính chiều cao phục vụ đường kính, công việc bị lặp và có thể lên tới **O(n²)** ở cây lệch. Trả đồng thời height và diameter giúp tránh việc tính lại.

## 8. Bổ sung ví dụ ngắn: kiểm tra ngoặc bằng summary

Cho một chuỗi chỉ chứa **'('** và **')'**. Ta biểu diễn '(' bằng **+1**, ')' bằng **−1**. Chuỗi ngoặc đúng khi:

1. **Tổng balance cuối = 0**.
2. **Mọi tiền tố** có balance không âm (không đóng ngoặc trước khi có ngoặc mở).

Nếu hai đoạn L và R được nối lại, chỉ trả **tổng balance** là chưa đủ:

~~~text
"()"  -> tổng balance = 0, hợp lệ
")("  -> tổng balance = 0, không hợp lệ
~~~

Trạng thái đủ thông tin cho đoạn S là:

- **sum:** tổng +1/−1 toàn đoạn.
- **minPrefix:** giá trị balance **nhỏ nhất trong tất cả tiền tố, kể cả tiền tố rỗng** của đoạn, vì vậy minPrefix ≤ 0.

Công thức kết hợp:

**sum(L+R) = L.sum + R.sum**

**minPrefix(L+R) = min(L.minPrefix, L.sum + R.minPrefix)**

Lý do: một tiền tố của L+R hoặc nằm trọn trong L, hoặc gồm toàn bộ L rồi một tiền tố của R. Chuỗi hoàn chỉnh hợp lệ khi **sum = 0 và minPrefix ≥ 0**.

Với một ký tự '(', summary là (sum=1, minPrefix=0); với ')', summary là (sum=−1, minPrefix=−1). Đoạn rỗng là (0,0) và có thể dùng như phần tử đơn vị khi combine.

Ví dụ này minh họa một quy luật rộng hơn: summary có thể chứa **cực trị của tiền tố**, không chỉ tổng hoặc đáp án cục bộ. Nó còn hữu ích khi xây segment tree cho truy vấn trên các đoạn ngoặc.

## 9. Summary, tính kết hợp và segment tree

Khi bài toán có các đoạn liên tiếp, summary và combine thường được dùng lại trong **segment tree** hoặc **xử lý song song**.

### Phép kết hợp có tính kết hợp (associativity)

Một phép combine trên summary của các đoạn kề nhau cần tái tạo đúng summary của đoạn ghép. Nếu trạng thái, công thức và **quy tắc hòa** được định nghĩa nhất quán, ta mong đợi:

**combine(combine(A,B),C) = combine(A,combine(B,C))**

về mặt ý nghĩa của summary của A+B+C.

Tính kết hợp rất có ích: có thể chia đoạn thành các nhóm khác nhau, trộn theo cây nhị phân hoặc gộp các khối kết quả mà vẫn thu được cùng thông tin.

Với maximum subarray, các trường total/prefix/suffix/best được xác định **theo nội dung của đoạn**, không phụ thuộc cách chia, nên công thức combine đúng có tính kết hợp về nội dung. Với chỉ số, phải đặt quy tắc phá hòa cố định (tổng, start, end) để kết quả **được chọn** cũng nhất quán.

### Phần tử đơn vị (identity) và trường hợp rỗng

Nếu hỗ trợ đoạn rỗng, summary của đoạn rỗng cần được xử lý như **phần tử trung hòa**:

**combine(empty, S) = S** và **combine(S, empty) = S**.

Điều này không có nghĩa là đặt prefix/suffix/best của đoạn rỗng bằng 0 một cách tùy tiện. Với bài toán **đoạn con phải không rỗng**, dùng 0 cho best rỗng sẽ làm kết quả sai khi toàn số âm. Một thiết kế an toàn là dùng một cờ empty hoặc các trường nullable rồi bắt riêng trường hợp rỗng, giống code Java.

### Segment tree với maximum subarray

Mỗi nút segment tree có thể lưu cùng summary (total, prefix, suffix, best):

- Lá trả summary của một phần tử.
- Nút trong lấy **combine(summary trái, summary phải)**.
- Cập nhật một phần tử: tính lại các nút trên đường đi lên gốc, **O(log n)**.
- Truy vấn một đoạn: kết hợp summary từ những khối phủ đoạn, thường **O(log n)** nút được lấy trong quá trình duyệt và gộp với combine O(1).

Đây là lợi ích của thiết kế summary đủ thông tin: một phép combine đúng có thể được tái sử dụng cho đệ quy chia để trị, segment tree và giảm dữ liệu theo khối. Tuy nhiên, phải tôn trọng **thứ tự trái trước phải**: combine của các đoạn liên tiếp có thể **không giao hoán** (không được tùy tiện đổi A và B), dù có tính kết hợp.

## 10. Chi phí bộ nhớ, ngữ nghĩa tham chiếu và tính bất biến

### Giá trị trả về nhỏ, tránh sao chép dữ liệu

Nếu một lời gọi tạo ra mảng con mới hoặc sao chép toàn bộ danh sách đã xử lý, lượng bộ nhớ và thời gian có thể tăng mạnh. Thay vì sao chép, hãy dùng **[from,to)** để mô tả phạm vi rồi chỉ trả summary cỡ hằng.

Đối với maximum subarray trong mã Java:

- Combine là **O(1)**, không duyệt lại các phần tử.
- Có **O(n)** lời gọi ứng với các nút trong cây chia.
- Độ sâu đệ quy là **O(log n)** vì chia gần đôi.
- Code tạo tổng cộng **O(n)** đối tượng Summary/Range trong quá trình chạy; mức sử dụng heap thực tế còn phụ thuộc thu gom rác.
- Chỉ khi in kết quả mới tạo bản sao đoạn được chọn bằng Arrays.copyOfRange, chi phí **O(k)** với k là độ dài đoạn in.

Nếu mục tiêu chỉ cần tổng, có thể giảm cấp phát bằng các record chứa bốn số và không tạo Range. Nếu truy vấn nhiều lần trên cùng mảng có cập nhật, dùng segment tree có thể đáng đổi lấy **O(n)** bộ nhớ lưu nút.

### Dùng số nguyên đủ rộng

Tổng đoạn con có thể vượt miền int dù từng phần tử là int. Ví dụ có nhiều phần tử gần Integer.MAX_VALUE, tổng có thể vượt 2,147,483,647. Do đó mẫu Java dùng **long** cho total và các sum. Với dữ liệu kiểu long số lượng lớn, vẫn cần xét nguy cơ tràn long, hoặc sử dụng BigInteger nếu yêu cầu kết quả chính xác ngoài miền long.

### Không dùng trạng thái toàn cục khi có thể trả rõ ràng

Có thể dùng một biến toàn cục để lưu best trong lúc đệ quy, nhưng cách này không tự giải quyết nhu cầu biết prefix/suffix của từng nhánh; hơn nữa dễ tạo lỗi khi gọi lại, chạy song song hoặc tái sử dụng hàm. Trả summary qua **kiểu kết quả rõ ràng** giúp dễ kiểm thử, chứng minh và kết hợp.

Record của Java 17 giúp thể hiện mỗi trường phải có ý nghĩa xác định. Các trường của record là final, nhưng nếu record chứa tham chiếu đến đối tượng mutable, bản thân dữ liệu được tham chiếu vẫn có thể thay đổi; khi đó tính bất biến logic của summary phải được bảo vệ riêng.

## 11. Bảng tổng hợp những mẫu trạng thái thường gặp

| Bài toán | Nếu chỉ trả... thì thiếu gì? | Summary đủ thông tin | Ý tưởng combine |
| --- | --- | --- | --- |
| Tổng đoạn | Có thể chỉ cần tổng | **sum** | sum = L.sum + R.sum |
| Giá trị lớn nhất trên đoạn | Có thể chỉ cần max | **max** | max = max(L.max, R.max) |
| Đoạn con có tổng lớn nhất | Chỉ trả best không biết đoạn cắt biên | **total, prefix, suffix, best** | best = max(L.best, R.best, L.suffix+R.prefix) |
| Đường kính cây nhị phân | Chỉ trả diameter không tính được đường qua gốc | **height, diameter** | diameter = max(dL,dR,hL+hR+2) |
| Chuỗi ngoặc đúng | Chỉ trả sum không phát hiện tiền tố âm | **sum, minPrefix** | minPrefix = min(L.minPrefix,L.sum+R.minPrefix) |
| Đếm bản ghi thỏa điều kiện trong các đoạn độc lập | Chỉ trả boolean không biết số lượng | **count** | count = L.count + R.count |
| Tìm vị trí đầu tiên đạt giá trị lớn nhất | Chỉ trả max không biết vị trí và hòa | **max, index** | chọn theo giá trị, sau đó theo chỉ số |
| Dãy con tăng liên tiếp dài nhất | Chỉ trả best không biết ghép qua biên | **length, first, last, prefixLen, suffixLen, bestLen** | Ghép qua biên nếu L.last < R.first |

**Bảng là gợi ý thiết kế**, không phải một bộ trạng thái cố định cho mọi đề. Nếu yêu cầu đầu ra thay đổi — ví dụ muốn **số lượng các đoạn tối ưu**, **toàn bộ vị trí tối ưu**, hoặc ràng buộc khác — cần điều chỉnh summary và quy tắc combine tương ứng.

## 12. Lỗi thường gặp và quy trình kiểm thử

1. **Chỉ trả đáp án cục bộ.** Không có prefix/suffix để xử lý đoạn cắt biên, hoặc không có height để tính đường đi xuyên qua nút.
2. **Combine không đóng.** Tính được best của cha nhưng quên trả prefix/suffix để ông bà dùng ở cấp tiếp theo.
3. **Không định nghĩa trường hợp cơ sở.** Với mảng rỗng hoặc nút null, truy cập trường không hợp lệ hoặc cộng sai chiều cao.
4. **Tự động cho phép đoạn rỗng.** Đặt best = max(0,x) trong khi đề yêu cầu đoạn không rỗng, gây sai ở mảng toàn số âm.
5. **Sai ranh giới.** Nhầm [from,mid) và [mid,to), dẫn đến bỏ sót hoặc tính trùng phần tử giữa.
6. **Kết hợp sai thứ tự.** Prefix/suffix và các trạng thái phụ thuộc hướng không cho phép tùy tiện đảo L và R.
7. **Tie-breaker không nhất quán.** Hai cách chia mảng có thể chọn đoạn khác nhau dù tổng bằng nhau.
8. **Quét lại để tính thông tin thiếu.** Vừa làm code dài vừa có thể nâng chi phí từ O(n) lên O(n log n) hoặc tệ hơn.
9. **Lạm dụng trạng thái toàn cục.** Khó tái sử dụng, khó chạy song song và dễ tồn tại dữ liệu cũ giữa các lần gọi.
10. **Tràn số khi cộng tổng.** Dùng kiểu đủ rộng theo miền dữ liệu và kích thước đầu vào.
11. **Nhầm số cạnh với số nút.** Đường kính cây được tính theo số cạnh phải có quy ước height(null) = −1 như trong ví dụ.
12. **Dùng phép combine chưa chứng minh.** Thấy công thức có vẻ hợp lý không đủ; cần phân loại hết các khả năng của đáp án và chứng minh không bỏ sót.

### Bộ kiểm thử cho maximum subarray

| Đầu vào | Tổng tối ưu | Khoảng [start,end) theo quy tắc đã chọn |
| --- | ---: | --- |
| [] | Không có | Không có đoạn không rỗng |
| [5] | 5 | [0,1) |
| [-5] | -5 | [0,1) |
| [-8,-3,-6,-2,-5,-4] | -2 | [3,4) |
| [4,-1,2,1,-5,4] | 6 | [0,4) |
| [1,-1,1,-1,1] | 1 | [0,1) |
| [0,0,0] | 0 | [0,1) |
| [2,-4,3,-1,2,-5,4,1] | 5 | [6,8) |

Các ca này kiểm tra giá trị âm, ranh giới, đoạn rỗng, cực trị bằng nhau và quy tắc phá hòa. Với mảng n nhỏ, có thể đối chiếu thuật toán chia để trị với một **thuật toán vét cạn O(n²)** duyệt mọi [i,j) không rỗng, cộng tổng và dùng cùng tiêu chí chọn (sum giảm, start tăng, end tăng).

### Bộ kiểm thử cho đường kính cây

| Cấu trúc | Chiều cao theo cạnh | Đường kính theo cạnh |
| --- | ---: | ---: |
| Cây rỗng | -1 | 0 |
| Một nút | 0 | 0 |
| Gốc và một con | 1 | 1 |
| Chuỗi bốn nút | 3 | 3 |
| Cây A/B/C/D/E/F ở mục 7 | 3 | 4 |

Với cây rất lệch, phiên bản đệ quy có thể tiêu thụ **O(n)** độ sâu ngăn xếp; Java có nguy cơ StackOverflowError với cây đủ sâu. Khi đó cân nhắc duyệt hậu thứ tự bằng stack tường minh hoặc phương án khác phù hợp giới hạn hệ thống.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao chỉ trả tổng lớn nhất của nửa trái và nửa phải là không đủ để tìm tổng lớn nhất của đoạn cha?  
**Đáp án:** Đoạn tối ưu có thể cắt qua biên. Cần thêm **suffix tốt nhất trái** và **prefix tốt nhất phải** để tạo ứng viên cắt biên.

**Câu 2.** Với L = [4,−1], R = [2,1], tổng tốt nhất của đoạn ghép là bao nhiêu?  
**Đáp án:** 6; hậu tố tốt nhất của L có tổng 3, tiền tố tốt nhất của R có tổng 3, cộng lại được 6.

**Câu 3.** Vì sao summary maximum subarray còn phải giữ **total**?  
**Đáp án:** Muốn tính prefix của đoạn cha có thể cần **toàn bộ nửa trái + prefix phải**, và suffix có thể cần **suffix trái + toàn bộ nửa phải**. Thiếu total sẽ không tính được các trường đó chỉ từ các cực trị cục bộ.

**Câu 4.** Với cây nhị phân, tại sao cần trả (height, diameter), không chỉ diameter?  
**Đáp án:** Cần height của hai cây con để tính đường đi dài nhất **qua nút hiện tại** là hL+hR+2 cạnh.

**Câu 5.** Hai chuỗi "()" và ")(" có tổng balance đều bằng 0. Summary cần thêm gì?  
**Đáp án:** **minPrefix**, vì ")(" có tiền tố balance âm nên không phải chuỗi ngoặc đúng.

**Câu 6.** Với maximum subarray dùng summary cỡ hằng và combine O(1), độ phức tạp thời gian là gì?  
**Đáp án:** **O(n)** vì T(n)=2T(n/2)+O(1).

**Câu 7.** Với mảng toàn số âm, vì sao không được khởi tạo best bằng 0 nếu đề yêu cầu đoạn không rỗng?  
**Đáp án:** 0 đại diện một đoạn rỗng có tổng lớn hơn mọi đoạn âm, nhưng đoạn rỗng bị cấm; đáp án phải là phần tử âm lớn nhất.

## 14. Ghi nhớ

**Thiết kế giá trị trả về** là thiết kế giao diện giữa bài toán con và hàm kết hợp. Hãy bắt đầu bằng việc liệt kê đầy đủ các cách đáp án của cha có thể hình thành; từ đó suy ra những thông tin con phải cung cấp. Định nghĩa trường hợp cơ sở, công thức combine, bất biến và quy tắc hòa rõ ràng. Tốt nhất, summary phải **đủ**, **nhỏ gọn**, **đóng dưới combine**, và có thể kết hợp nhanh mà không quét lại dữ liệu.

Với maximum subarray, bốn trường **total/prefix/suffix/best** là mẫu điển hình. Với đường kính cây, cặp **height/diameter** giúp tính đúng đường đi xuyên qua gốc. Với chuỗi ngoặc, **sum/minPrefix** cho phép phân biệt tổng bằng 0 với tiền tố không hợp lệ. Đây chính là tư duy có thể chuyển từ đệ quy chia để trị sang segment tree, phân tích dãy, xử lý cây và gộp dữ liệu theo khối.
