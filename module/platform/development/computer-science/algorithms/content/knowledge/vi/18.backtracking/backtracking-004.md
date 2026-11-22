# Tránh kết quả trùng khi đầu vào có phần tử lặp

## 1. Vấn đề khi quay lui trên dữ liệu có phần tử trùng

**Quay lui (backtracking)** duyệt các lựa chọn từng bước, xây dựng một lời giải tạm rồi hoàn tác bước vừa chọn để thử nhánh khác. Cách này thường dùng cho **tập con, tổ hợp, hoán vị, phân hoạch** và các bài toán tìm kiếm có ràng buộc.

Nếu đầu vào có các phần tử **bằng nhau về giá trị**, nhiều chuỗi chọn **chỉ số khác nhau** có thể tạo cùng một kết quả. Ví dụ mảng [1,2,2] có hai số 2 ở hai vị trí riêng biệt:

~~~text
Chọn vị trí 1: giá trị [2]
Chọn vị trí 2: giá trị [2]

Chọn vị trí 0,1: giá trị [1,2]
Chọn vị trí 0,2: giá trị [1,2]
~~~

Nếu bài yêu cầu **các tập con phân biệt theo giá trị**, in cả hai nhánh sẽ tạo kết quả trùng. Nếu bài yêu cầu **các tổ hợp vị trí chỉ số**, hai lựa chọn này có thể là kết quả khác nhau. Vì vậy, trước khi khử trùng phải xác định **định nghĩa hai kết quả bằng nhau** của đề bài.

Trong bài này, mặc định hai kết quả được coi trùng khi chúng có cùng **dãy giá trị đầu ra**. Với tập con/tổ hợp, ta dùng thứ tự không giảm sau sắp xếp; với hoán vị, **thứ tự vị trí trong kết quả có ý nghĩa**, ví dụ [1,2,1] khác [2,1,1].

Có ba ý tưởng cần phân biệt:
1. **Sắp xếp để đặt các giá trị bằng nhau cạnh nhau** — giúp kiểm tra trùng bằng phần tử trước.
2. **Bỏ lựa chọn tạo nhánh tương đương ở cùng độ sâu** — tránh sinh trùng từ gốc.
3. **Không cấm sử dụng bản sao hợp lệ ở những độ sâu khác nhau** — vì [2,2] có thể là kết quả đúng khi đầu vào có hai số 2.

Mục tiêu là **mỗi kết quả hợp lệ xuất hiện đúng một lần**: không trùng và cũng không bị bỏ sót.

## 2. Hai kiểu kết quả: tập con/tổ hợp và hoán vị

Các bài toán quay lui nhìn gần giống nhau nhưng dùng quy tắc trùng khác nhau.

| Bài toán | Thứ tự đầu ra có ý nghĩa? | Một vị trí được dùng mấy lần? | Quy tắc tránh trùng chính |
|---|---|---|---|
| Tập con phân biệt (unique subsets) | Không | Tối đa một | Sắp xếp, bỏ giá trị bằng nhau ở **cùng vòng lặp của một lời gọi** |
| Tổ hợp có tổng mục tiêu, mỗi món một lần | Không | Tối đa một | Cùng quy tắc bỏ trùng ở độ sâu hiện tại, thêm cắt tỉa theo tổng |
| Hoán vị phân biệt (unique permutations) | Có | Tối đa một | Mảng used + buộc các bản sao bằng nhau được chọn theo thứ tự chỉ số |
| Tổ hợp được tái sử dụng một giá trị | Không | Có thể nhiều | Bài toán khác, thường cho đệ quy tại **i**, không phải i+1 |

**Tập con** có thể có độ dài từ 0 tới n và cần giữ mỗi giá trị chọn đúng theo số bản sao có sẵn. **Hoán vị** sử dụng toàn bộ n phần tử để tạo dãy độ dài n, nhưng thứ tự có thể thay đổi. **Tổ hợp tổng mục tiêu** chọn một phần tập phần tử sao cho tổng bằng một số cho trước.

Đừng sao chép quy tắc của hoán vị sang tập con một cách máy móc. Đối với tập con ta dùng chỉ số **start** giới hạn phần tử phía sau; đối với hoán vị ta có mảng **used** để biết vị trí nào đã nằm trong đường đi hiện tại.

## 3. Công cụ chung: sắp xếp và trạng thái của một lời gọi

Giả sử a là bản sao của mảng đầu vào đã được sắp **không giảm**.

Với [2,1,2], sau khi sắp:

~~~text
a = [1,2,2]
index: 0 1 2
~~~

Nhờ sắp xếp, nếu hai giá trị bằng nhau, chúng nằm cạnh nhau. Một phép kiểm tra a[i]==a[i−1] mới có đủ ý nghĩa để phát hiện nhóm giá trị trùng **kề nhau**. Nếu không sắp xếp, hai giá trị 2 có thể cách xa bởi 1 và kiểm tra chỉ với phần tử trước sẽ bỏ sót trùng.

**Sao chép trước khi sắp** nếu không muốn thay đổi mảng người gọi. Ví dụ Java bên dưới dùng Arrays.copyOf(input,input.length), rồi Arrays.sort(copy).

Một lời gọi quay lui thường có:
- **path**: danh sách các giá trị đã chọn trên đường đi hiện tại.
- **start**: chỉ số nhỏ nhất được phép xét ở bước kế tiếp (tập con/tổ hợp).
- **used[i]**: vị trí i đã chọn hay chưa trong path (hoán vị).
- **remaining**: phần tổng mục tiêu còn phải đạt (tổ hợp tổng).

**Nguyên tắc bất biến:** mỗi lần đệ quy trở về, phải trả lại path và used đúng trạng thái trước khi đi vào nhánh. Mẫu chung là **chọn → đệ quy → bỏ chọn**. Nếu quên hoàn tác, dữ liệu từ nhánh trước sẽ làm sai nhánh sau.

**Đừng nhầm trùng giá trị với trùng vị trí:** các vị trí khác nhau có thể cùng giá trị. Ta không cấm cùng giá trị xuất hiện nhiều lần trong một kết quả nếu đầu vào cung cấp đủ bản sao; ta chỉ cấm **hai nhánh tương đương tạo cùng một kết quả**.

## 4. Sinh tập con không trùng: bỏ phần tử trùng ở cùng tầng

### 4.1. Thuật toán

Với mảng đã sắp a, bắt đầu tại dfs(start=0, path=[]). Mỗi lời gọi:
1. **Ghi nhận bản sao của path** vì mọi tiền tố hợp lệ là một tập con.
2. Duyệt i từ start tới n−1.
3. Nếu **i>start** và a[i]==a[i−1], bỏ qua **lựa chọn i ở vòng lặp này**.
4. Nếu không, thêm a[i], đệ quy dfs(i+1), rồi xóa phần tử vừa thêm.

Giả mã:

~~~text
subsets(start, path):
    output.add(copy(path))

    for i = start .. n-1:
        if i > start AND a[i] == a[i-1]:
            continue

        path.add(a[i])
        subsets(i+1, path)
        path.removeLast()
~~~

**Điều kiện quan trọng nhất:**

~~~java
if (i > start && a[i] == a[i - 1]) {
    continue;
}
~~~

Vế **i>start** có nghĩa chỉ bỏ bản sao ở **cùng danh sách lựa chọn của một lời gọi**. Không được thay bằng **i>0** một cách vô điều kiện, bởi khi ở một lời gọi sâu hơn, phần tử trùng có thể là một **bản sao khác hợp lệ**.

### 4.2. Trace mảng [1,2,2]

Sau khi sắp, thuật toán duyệt theo thứ tự:

~~~text
path=[]
  ghi []
  chọn 1 tại i=0
    ghi [1]
    chọn 2 tại i=1
      ghi [1,2]
      chọn 2 tại i=2 (i==start==2, được chọn)
        ghi [1,2,2]
    thử 2 tại i=2 cùng tầng với 2 tại i=1 -> BỎ
  chọn 2 tại i=1
    ghi [2]
    chọn 2 tại i=2 (i==start==2, được chọn)
      ghi [2,2]
  thử 2 tại i=2 cùng tầng gốc với 2 tại i=1 -> BỎ
~~~

Kết quả theo thứ tự DFS:

~~~text
[[], [1], [1, 2], [1, 2, 2], [2], [2, 2]]
~~~

Chú ý **[2,2] không bị mất**: chọn số 2 đầu tiên ở tầng gốc, rồi chọn số 2 thứ hai **ở tầng con**. Đây là tình huống phân biệt quy tắc đúng và quy tắc bỏ trùng quá mạnh.

### 4.3. Vì sao không sinh trùng và không bỏ sót?

Trong một lời gọi với start cố định, nếu a[i]==a[i−1] và i>start, hai lựa chọn đầu tiên “chọn giá trị này ở vị trí i−1” và “chọn cùng giá trị ở vị trí i” là **tương đương xét theo giá trị**. Nhánh chọn bản sao sớm hơn có thể tạo mọi tập giá trị mà nhánh chọn bản sao muộn hơn có thể tạo, vì nó vẫn còn **ít nhất cùng số lượng bản sao của giá trị ấy** và phần tử lớn hơn phía sau.

Vì vậy bỏ nhánh bắt đầu bằng bản sao muộn hơn ở cùng tầng không làm mất **tập giá trị phân biệt** nào. Lặp quy tắc này tại mọi tầng cho ta một biểu diễn chuẩn: khi ở một mức chọn, luôn thử **bản sao chưa dùng có chỉ số nhỏ nhất** trong nhóm giá trị bằng nhau.

Mặt khác, các nhánh khác nhau đầu tiên ở một tầng chỉ chọn **giá trị khác nhau**. Khi phần đầu tiên khác nhau, các dãy kết quả không giảm không thể giống nhau. Quy nạp theo chiều dài path bảo đảm mỗi tập con theo giá trị xuất hiện một lần.

**Một cách đếm để kiểm tra:** nếu số x xuất hiện f_x lần thì tập con có thể chứa 0,1,...,f_x bản sao của x, tức f_x+1 lựa chọn về số lượng. Các nhóm giá trị độc lập nên tổng số tập con phân biệt là:

\[
U_{\text{subsets}}=\prod_x(f_x+1).
\]

Với [1,2,2], f_1=1, f_2=2, kết quả là (1+1)(2+1)=**6** tập con, đúng như trace.

## 5. Sinh hoán vị không trùng: used và thứ tự của bản sao

### 5.1. Tại sao không thể dùng nguyên quy tắc của tập con?

Khi sinh hoán vị, mỗi bước có thể lấy một phần tử ở **bất kỳ vị trí chưa dùng**, không đơn giản là chỉ số từ start trở đi. Mảng a đã sắp, và mảng **used[i]** ghi vị trí i đã nằm trong hoán vị hiện tại.

Với [1,1,2], nếu chỉ dùng quy tắc “i>0 và a[i]==a[i−1] thì bỏ” ở mọi tầng, bản sao số 1 thứ hai **không bao giờ được chọn**, khiến thuật toán không thể tạo hoán vị dài 3.

Ngược lại, nếu không khử trùng, hoán đổi vai trò của hai số 1 ở vị trí 0 và 1 sẽ tạo cùng một dãy giá trị nhiều lần.

### 5.2. Quy tắc chuẩn hóa lựa chọn

Sau khi sắp, khi xét chỉ số i:
1. Nếu used[i] là true, không được chọn lại vị trí đó.
2. Nếu i>0, a[i]==a[i−1] **và used[i−1] là false**, bỏ qua i.
3. Ngược lại, chọn a[i], gán used[i]=true, đệ quy, rồi hoàn tác used[i]=false.

Điều kiện khử trùng:

~~~java
if (i > 0 && a[i] == a[i - 1] && !used[i - 1]) {
    continue;
}
~~~

Ý nghĩa: **không chọn bản sao sau của cùng giá trị trước khi bản sao liền trước đã được chọn trong tiền tố**. Trong một đường đi, các bản sao bằng nhau sẽ được dùng **theo thứ tự chỉ số tăng**. Nhờ đó các hoán đổi chỉ số vô hình giữa các bản sao không tạo hoán vị lặp.

### 5.3. Trace [1,1,2]

~~~text
a=[1(index 0), 1(index 1), 2(index 2)]

Tầng gốc:
  i=0: được chọn 1 đầu tiên.
    Tầng tiếp:
      i=1: được chọn 1 thứ hai vì used[0]==true.
        i=2: được chọn 2 -> [1,1,2].
      i=2: được chọn 2, rồi số 1 thứ hai -> [1,2,1].
  i=1: BỎ vì a[1]==a[0] và used[0]==false.
  i=2: được chọn 2, sau đó 1 đầu tiên, 1 thứ hai -> [2,1,1].
~~~

Danh sách hoán vị phân biệt:

~~~text
[[1, 1, 2], [1, 2, 1], [2, 1, 1]]
~~~

**Vì sao vẫn tạo được [1,1,2]?** Sau khi chọn bản sao 1 ở index 0, used[0]=true; khi xét bản sao thứ hai ở index 1, điều kiện bỏ trùng là false, nên nó **được dùng ở độ sâu tiếp theo**.

### 5.4. Chứng minh không bỏ sót/không lặp

Mỗi hoán vị giá trị của một đa tập đều có thể được gắn chỉ số nguồn theo cách chuẩn: với mỗi nhóm giá trị bằng nhau, lần xuất hiện thứ nhất lấy chỉ số nhỏ nhất trong nhóm, lần thứ hai lấy chỉ số kế tiếp, v.v. Điều kiện **!used[i−1]** đảm bảo thuật toán chỉ sinh đúng các cách gắn chỉ số chuẩn đó.

- **Không bỏ sót:** mọi hoán vị theo giá trị có một cách gắn chỉ số chuẩn và cách ấy luôn được phép.
- **Không trùng:** hai đường đi khác nhau không thể tạo cùng dãy giá trị nếu cả hai đều tuân thủ cách gắn chỉ số chuẩn. Tại vị trí đầu tiên đường đi khác chỉ số nhưng cùng giá trị, một đường đã phải chọn bản sao sau trước bản sao trước, trái với điều kiện skip.

Nếu có n phần tử với các tần suất f_x, số hoán vị phân biệt là:

\[
U_{\text{permutations}}=\frac{n!}{\prod_x f_x!}.
\]

Với [1,1,2], bằng \(3!/2!=3\).

## 6. Tổ hợp có tổng mục tiêu, mỗi vị trí tối đa một lần

Một bài toán tiêu biểu khác: cho n số nguyên **dương** (có thể lặp) và số nguyên target≥0. Liệt kê các tổ hợp giá trị phân biệt có tổng đúng target, mỗi **vị trí đầu vào chỉ được dùng một lần**.

Ví dụ đầu vào:

~~~text
nums = [10, 1, 2, 7, 6, 1, 5]
target = 8
sorted = [1, 1, 2, 5, 6, 7, 10]
~~~

Kết quả cần có:

~~~text
[[1, 1, 6], [1, 2, 5], [1, 7], [2, 6]]
~~~

Đây là dạng thường gọi **Combination Sum II**: cùng một giá trị có thể xuất hiện nhiều lần trong tổ hợp nếu đầu vào có nhiều bản sao, nhưng **không được tái sử dụng một vị trí**.

### 6.1. Trạng thái và chuyển bước

Định nghĩa **dfs(start, remaining, path)**:
- start: chỉ được xét phần tử có chỉ số ≥start.
- remaining: tổng còn thiếu để đạt target.
- path: các giá trị đã chọn, không giảm vì a đã sắp và chỉ số tăng.

Nếu remaining==0, ghi một bản sao path làm nghiệm rồi return.

Trong vòng i từ start..n−1:
- Nếu i>start và a[i]==a[i−1], bỏ nhánh cùng tầng.
- Nếu a[i]>remaining, có thể **break** vì a đã sắp tăng và các số đều dương, không số phía sau nào nhỏ hơn để vừa remaining.
- Nếu chọn, giảm remaining đi a[i], rồi đệ quy ở **i+1**.
- Hoàn tác phần tử vừa chọn.

Giả mã:

~~~text
sumOnce(start, remaining, path):
    if remaining == 0:
        output.add(copy(path))
        return

    for i = start .. n-1:
        if i > start AND a[i] == a[i-1]:
            continue
        if a[i] > remaining:
            break

        path.add(a[i])
        sumOnce(i+1, remaining-a[i], path)
        path.removeLast()
~~~

**Điều kiện break chỉ đúng theo hợp đồng số dương và mảng đã sắp.** Nếu có số âm, một số lớn hơn remaining vẫn có thể được bù bởi số âm phía sau (nếu thứ tự tìm kiếm cho phép). Khi cho phép số 0 hoặc âm, phải phân tích lại điều kiện dừng và cắt tỉa.

### 6.2. Vì sao bỏ trùng ở cùng tầng là đúng?

Một tổ hợp được biểu diễn bằng dãy giá trị không giảm. Nếu tại một tầng có hai lựa chọn cùng giá trị x, chọn bản sao x sớm hơn không làm thiếu bất kỳ tổ hợp nào mà lựa chọn bản sao x muộn hơn có thể tạo: nó còn cho phép chọn các bản sao x kế tiếp ở tầng sâu hơn. Vì vậy có thể bỏ **các nhánh cùng tầng** mở đầu bằng bản sao muộn.

Tuy nhiên ta vẫn cho phép chọn hai số 1 ở các tầng kế tiếp để tạo [1,1,6], vì hai bản sao ở hai **vị trí khác nhau** có trong đầu vào. Dùng start=i+1 đảm bảo **mỗi vị trí tối đa một lần**.

Với target=0 và số dương, tổ hợp rỗng là nghiệm duy nhất, nên đầu ra là **[[]]**. Với target>0 mà không có cách chọn, đầu ra **[]**.

## 7. Java 17+ đầy đủ: ba bộ sinh kết quả phân biệt

Chương trình sau minh họa:
- **subsetsUnique**: tất cả tập con phân biệt theo giá trị.
- **permutationsUnique**: các hoán vị phân biệt, mỗi vị trí dùng một lần.
- **combinationSumOnce**: các tổ hợp phân biệt đạt target với mỗi vị trí dùng tối đa một lần.

Cả ba hàm đều tạo **bản sao mảng trước khi sắp**, không sửa dữ liệu của người gọi. Mọi kết quả là bản sao bất biến của path, nên các lần **backtrack** sau đó không thay đổi kết quả đã ghi.

Lưu tệp **DuplicateAwareBacktrackingDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public final class DuplicateAwareBacktrackingDemo {
    private DuplicateAwareBacktrackingDemo() {
    }

    private static int[] sortedCopy(int[] input) {
        if (input == null) {
            throw new IllegalArgumentException("Null input");
        }
        int[] a = Arrays.copyOf(input, input.length);
        Arrays.sort(a);
        return a;
    }

    public static List<List<Integer>> subsetsUnique(int[] input) {
        int[] a = sortedCopy(input);
        List<List<Integer>> answer = new ArrayList<>();
        dfsSubsets(a, 0, new ArrayList<>(), answer);
        return answer;
    }

    private static void dfsSubsets(
            int[] a, int start, List<Integer> path,
            List<List<Integer>> answer) {
        answer.add(List.copyOf(path));

        for (int i = start; i < a.length; i++) {
            // Bỏ lựa chọn trùng giá trị cùng tầng, không bỏ tầng sâu.
            if (i > start && a[i] == a[i - 1]) {
                continue;
            }

            path.add(a[i]);
            dfsSubsets(a, i + 1, path, answer);
            path.remove(path.size() - 1);
        }
    }

    public static List<List<Integer>> permutationsUnique(int[] input) {
        int[] a = sortedCopy(input);
        List<List<Integer>> answer = new ArrayList<>();
        boolean[] used = new boolean[a.length];

        dfsPermutations(a, used, new ArrayList<>(), answer);
        return answer;
    }

    private static void dfsPermutations(
            int[] a, boolean[] used, List<Integer> path,
            List<List<Integer>> answer) {
        if (path.size() == a.length) {
            answer.add(List.copyOf(path));
            return;
        }

        for (int i = 0; i < a.length; i++) {
            if (used[i]) {
                continue;
            }
            // Bản sao bằng nhau được chọn theo chỉ số tăng.
            if (i > 0 && a[i] == a[i - 1] && !used[i - 1]) {
                continue;
            }

            used[i] = true;
            path.add(a[i]);
            dfsPermutations(a, used, path, answer);
            path.remove(path.size() - 1);
            used[i] = false;
        }
    }

    public static List<List<Integer>> combinationSumOnce(
            int[] input, int target) {
        int[] a = sortedCopy(input);
        if (target < 0) {
            throw new IllegalArgumentException("Negative target");
        }
        for (int x : a) {
            if (x <= 0) {
                throw new IllegalArgumentException(
                        "Combination candidates must be positive");
            }
        }

        List<List<Integer>> answer = new ArrayList<>();
        dfsCombinationSum(a, 0, target, new ArrayList<>(), answer);
        return answer;
    }

    private static void dfsCombinationSum(
            int[] a, int start, int remaining,
            List<Integer> path, List<List<Integer>> answer) {
        if (remaining == 0) {
            answer.add(List.copyOf(path));
            return;
        }

        for (int i = start; i < a.length; i++) {
            if (i > start && a[i] == a[i - 1]) {
                continue;
            }
            // Tất cả số đều dương và đã sắp: số sau còn lớn hơn.
            if (a[i] > remaining) {
                break;
            }

            path.add(a[i]);
            dfsCombinationSum(
                    a, i + 1, remaining - a[i], path, answer);
            path.remove(path.size() - 1);
        }
    }

    public static void main(String[] args) {
        int[] subsetInput = {2, 1, 2};
        System.out.println("Subsets: "
                + subsetsUnique(subsetInput));
        System.out.println("Original: "
                + Arrays.toString(subsetInput));

        System.out.println("Permutations: "
                + permutationsUnique(new int[] {1, 1, 2}));

        System.out.println("Target 8: "
                + combinationSumOnce(
                        new int[] {10, 1, 2, 7, 6, 1, 5}, 8));

        System.out.println("Two zeros: "
                + subsetsUnique(new int[] {0, 0}));
        System.out.println("Empty permutation: "
                + permutationsUnique(new int[] {}));
        System.out.println("Target zero: "
                + combinationSumOnce(new int[] {1, 1, 2}, 0));
        System.out.println("Three twos, target 4: "
                + combinationSumOnce(new int[] {2, 2, 2}, 4));
    }
}
~~~

Biên dịch và chạy với **JDK 17 hoặc mới hơn**:

~~~bash
javac -encoding UTF-8 DuplicateAwareBacktrackingDemo.java
java DuplicateAwareBacktrackingDemo
~~~

**Stdout chính xác:**

~~~text
Subsets: [[], [1], [1, 2], [1, 2, 2], [2], [2, 2]]
Original: [2, 1, 2]
Permutations: [[1, 1, 2], [1, 2, 1], [2, 1, 1]]
Target 8: [[1, 1, 6], [1, 2, 5], [1, 7], [2, 6]]
Two zeros: [[], [0], [0, 0]]
Empty permutation: [[]]
Target zero: [[]]
Three twos, target 4: [[2, 2]]
~~~

### Giải thích các chi tiết của Java

**1. Array sort và bảo toàn đầu vào.** Hàm sortedCopy dùng Arrays.copyOf, rồi Arrays.sort. Do đó biến subsetInput ban đầu vẫn in [2,1,2]. Nếu sắp trực tiếp input, hàm sẽ làm thay đổi dữ liệu của người gọi.

**2. List.copyOf(path) khi ghi kết quả.** Nếu chỉ dùng answer.add(path), tất cả kết quả có thể cùng tham chiếu tới danh sách path sẽ tiếp tục bị thêm/xóa; sau khi quay lui kết thúc, nhiều kết quả thành rỗng hoặc giống nhau. List.copyOf tạo **bản sao không sửa được**, chụp đúng giá trị tại thời điểm ghi.

**3. Quay lui cần hoàn tác đối xứng.** Với tập con/tổ hợp: thêm path.add, đệ quy, rồi path.remove(path.size()−1). Với hoán vị còn phải khôi phục used[i]=false sau khi đi ra khỏi nhánh.

**4. Permutations không dùng start.** Trong hoán vị, sau khi chọn phần tử ở vị trí i, vẫn có thể cần phần tử với chỉ số nhỏ hơn i ở bước sau, miễn chưa used. Dùng start=i+1 như tập con sẽ bỏ mất các thứ tự hợp lệ.

**5. Tổ hợp tổng chỉ cho số dương.** Nhờ a[i]>0, khi remaining==0 có thể ghi nhận và kết thúc nhánh; khi a[i]>remaining có thể break. Nếu cần hỗ trợ số âm hoặc các biến thể tái dùng một món, phải thay đổi mô hình.

**6. Đầu vào rỗng và target=0.** Tập con của mảng rỗng là một tập rỗng, hoán vị của mảng rỗng cũng có một chuỗi rỗng theo quy ước toán học, nên các bộ sinh này có thể trả **[[]]**. Target=0 với các món dương có nghiệm duy nhất là tập rỗng.

**7. Trùng về giá trị, không trùng về vị trí.** Code trả mỗi dãy giá trị đúng một lần. Nếu bài yêu cầu báo mọi tổ hợp **chỉ số** khác nhau, khử trùng theo giá trị là không phù hợp.

**8. Thứ tự output có chủ đích.** Sắp a tăng dần và duyệt i tăng khiến kết quả DFS ổn định, giúp test dễ hơn. Thứ tự danh sách toàn bộ kết quả không phải lúc nào cũng thuộc yêu cầu đề; nếu bài yêu cầu thứ tự từ điển, cần xác minh thứ tự DFS có đúng định nghĩa so sánh được dùng hay không.

## 8. Phân biệt skip cùng tầng và dùng lại cùng giá trị ở tầng sâu

Đây là phần thường gây lỗi nhất.

### 8.1. Quy tắc đúng cho tập con/tổ hợp

~~~java
if (i > start && a[i] == a[i - 1]) {
    continue;
}
~~~

Mỗi lời gọi dfs có một **start riêng**, nên giá trị start đánh dấu **đầu danh sách các lựa chọn cùng tầng**.

Ví dụ a=[2,2]:
- Tầng gốc có start=0. Chọn i=0, rồi xuống tầng con start=1.
- Tại tầng con, i=1 bằng start nên **không skip**, tạo [2,2].
- Quay về tầng gốc, thử i=1 thì i>start và a[1]==a[0], nên **skip**, tránh sinh thêm [2] trùng.

Nếu thay bằng i>0, tầng con cũng skip i=1 và không thể tạo [2,2]; đó là **bỏ sót kết quả** chứ không phải khử trùng tốt hơn.

### 8.2. Quy tắc đúng cho hoán vị

~~~java
if (i > 0 && a[i] == a[i - 1] && !used[i - 1]) {
    continue;
}
~~~

Nếu bản sao trước của cùng giá trị đã nằm trong path, **bản sao sau được phép chọn**. Nếu bản sao trước chưa nằm trong path, chọn bản sao sau trước sẽ tạo nhánh tương đương với nhánh chọn bản sao trước, nên bỏ.

Nếu bỏ vế **!used[i−1]**, [1,1,2] sẽ không tạo được hoán vị dài 3.

Nếu quên vế **a[i]==a[i−1]**, thuật toán sẽ chặn cả phần tử khác giá trị tùy trạng thái used, làm thiếu những hoán vị hợp lệ.

**Cảnh báo về skip kiểu sai:** một số biến thể trình bày điều kiện phụ thuộc used[i−1] theo hướng ngược nhưng kết hợp thêm cơ chế loại trùng cùng tầng riêng; không được thay thế từng mảnh điều kiện giữa các biến thể mà không chứng minh toàn bộ thuật toán. Mẫu trên là một quy tắc chuẩn, nhất quán với phép chọn theo thứ tự chỉ số của các bản sao bằng nhau.

## 9. Những cách khử trùng khác và đánh đổi

### 9.1. Sinh mọi nhánh rồi bỏ trùng bằng Set

Có thể tạo toàn bộ kết quả bằng backtracking ngây thơ, sau đó lưu kết quả vào Set để loại phần tử trùng.

**Ưu điểm:** dễ mô tả trong một số bài nhỏ. **Nhược điểm:** vẫn chạy qua các nhánh trùng, tốn thời gian; cần thêm bộ nhớ cho Set, và phải dùng **bản sao bất biến** của path làm khóa. Nếu dùng danh sách còn bị sửa làm khóa trong hash-based Set, hành vi tìm kiếm sẽ không còn đáng tin vì hashCode thay đổi sau khi chèn.

Với hoán vị của n phần tử có nhiều giá trị lặp, sinh tất cả hoán vị theo vị trí có thể duyệt tới n! lá, dù số hoán vị phân biệt chỉ là \(n!/\prod f_x!\). Skip ngay khi mở nhánh tránh phần lớn công việc dư.

Set vẫn có ích như một **công cụ xác minh** với n nhỏ, hoặc khi cấu trúc trùng phức tạp khiến không có quy tắc canonical đơn giản.

### 9.2. Đếm tần suất thay vì mảng chỉ số

Với hoán vị, một cách khác là nén dữ liệu thành:
- Danh sách các **giá trị phân biệt** x_1,...,x_k.
- Số lượng còn lại count[x_i] của từng giá trị.

Mỗi tầng chọn một giá trị có count>0, giảm count, đệ quy rồi tăng count trở lại. Cách này **tránh trùng tự nhiên**, vì mỗi giá trị chỉ có một nhánh ở mỗi tầng, nhưng cần cấu trúc lưu tần suất phù hợp.

Đối với tập con, có thể chọn **số lượng bản sao** của mỗi giá trị (0..f_x) rồi sang nhóm tiếp theo. Cách này cho đúng \(\prod(f_x+1)\) tập con mà không cần so phần tử kề nhau tại từng lời gọi.

**Khi nào nên dùng?** Nếu tần suất lớn và số lượng giá trị phân biệt ít, thuật toán theo bảng tần suất có thể rõ ràng hơn. Nếu cần chỉ số gốc của từng bản sao, phải lưu thêm ánh xạ và định nghĩa lại thế nào là kết quả phân biệt.

### 9.3. Vì sao không dùng một Set toàn cục các giá trị đã chọn?

Nếu dùng Set<Integer> usedValues cho **mọi độ sâu**, lần chọn giá trị 2 đầu tiên sẽ ngăn chọn bất kỳ giá trị 2 thứ hai, kể cả khi đầu vào có hai bản sao và kết quả [2,2] hợp lệ.

Chỉ khi bài toán thực sự quy định **mỗi giá trị phân biệt chỉ được dùng một lần bất kể tần suất**, mới có thể áp dụng hạn chế đó. Trong bài đang xét, ràng buộc là **mỗi vị trí nguồn tối đa một lần**, khác hoàn toàn.

## 10. Phân tích độ phức tạp theo số kết quả phân biệt

Vì đây là bài **liệt kê**, thời gian và bộ nhớ đầu ra có thể rất lớn ngay cả khi thuật toán tránh sinh trùng hoàn hảo.

### Tập con không trùng

Nếu giá trị x xuất hiện f_x lần, số tập con phân biệt là:

\[
U=\prod_x(f_x+1)\le 2^n.
\]

Với mọi phần tử phân biệt, U=2^n; bản thân việc **xuất tất cả** kết quả đã tốn ít nhất thời gian tỷ lệ với tổng chiều dài các tập con, trong trường hợp xấu là \(\Theta(n2^n)\).

Mỗi nút DFS sao chép path, mỗi vòng lặp xét các vị trí còn lại. Một cận trên đơn giản cho chương trình minh họa là **O(n2^n)** thời gian khi tính cả bản sao kết quả và vòng duyệt, sau O(n log n) để sắp; độ sâu đệ quy O(n), path O(n), không tính bộ nhớ của danh sách kết quả. Bộ nhớ **đầu ra** có thể là O(nU).

### Hoán vị không trùng

Số hoán vị phân biệt:

\[
P=\frac{n!}{\prod_x f_x!}.
\]

Mỗi kết quả có n phần tử, nên chỉ xuất chúng đã cần \(\Omega(nP)\) thời gian/bộ nhớ dữ liệu đầu ra. Vòng for tại mỗi trạng thái quét tối đa n vị trí và các tiền tố hợp lệ có thể được chặn bởi O(nP), nên một cận trên dễ dùng là **O(n²P)** thời gian cho DFS (ngoài O(n log n) để sắp). Cận này an toàn nhưng không phải lúc nào cũng chặt.

Nếu tất cả phần tử phân biệt, P=n! và chi phí liệt kê là giai thừa. Bộ nhớ làm việc cho path, used và stack là **O(n)**; lưu mọi kết quả cần O(nP).

### Tổ hợp tổng mục tiêu, mỗi vị trí một lần

Mỗi nhánh chỉ lấy hoặc bỏ một vị trí và không dùng lại; số tổ hợp chỉ số có thể tới 2^n. Việc cắt tỉa theo remaining và loại trùng cùng tầng thường giảm đáng kể các nhánh thực tế, nhưng cận trên vẫn có thể là **O(n2^n)** thời gian khi tính cả duyệt và sao chép kết quả, ngoài O(n log n) sắp. Bộ nhớ làm việc O(n), bộ nhớ kết quả theo tổng số phần tử được xuất.

**Quan trọng:** tránh trùng không biến một bài liệt kê có nhiều nghiệm thành bài toán đa thức. Kết quả có thể tăng theo hàm mũ/giai thừa và bản thân việc xuất chúng đã tốn chi phí lớn.

## 11. Kiểm thử tính đúng bằng brute force và bộ dữ liệu nhỏ

**Các điều kiện QA cho mọi bộ sinh:**
1. Mỗi kết quả chỉ dùng tối đa số lần xuất hiện của từng giá trị trong đầu vào.
2. Mỗi kết quả thỏa điều kiện bài toán: tập con/tổ hợp không giảm, hoán vị dùng đủ n phần tử, tổ hợp có tổng đúng target.
3. Không có **hai kết quả có cùng dãy giá trị**.
4. Không bỏ sót: với n nhỏ, so với tập các kết quả khác nhau sinh bằng brute force theo vị trí nguồn.

Các trường hợp nên thử:

| Đầu vào | Bài toán | Kết quả phân biệt đáng chú ý |
|---|---|---|
| [] | Subsets | [[]] |
| [] | Permutations | [[]] |
| [2,2] | Subsets | [[],[2],[2,2]] |
| [1,1,2] | Permutations | 3 hoán vị |
| [0,0] | Subsets | [[],[0],[0,0]] |
| [1,2,3] | Subsets | 8 tập con |
| [3,3,3] | Permutations | Chỉ [[3,3,3]] |
| [2,2,2], target=4 | Sum once | Chỉ [[2,2]] |
| [1,1,2], target=0 | Sum once | [[]] |
| [1,1,2], target=5 | Sum once | [] |
| [10,1,2,7,6,1,5], target=8 | Sum once | 4 tổ hợp theo ví dụ |
| [-1,-1,2] | Subsets/permutations | Vẫn khử trùng đúng vì so giá trị, kể cả âm |

Với n nhỏ, có thể lấy tất cả mask từ 0 tới \(2^n-1\), đổi tập vị trí được chọn thành dãy giá trị đã sắp, đưa vào Set<List<Integer>> và so với đầu ra subsetsUnique. Với hoán vị, sinh tất cả cách hoán đổi vị trí, chuyển thành dãy giá trị rồi khử trùng để làm bộ tham chiếu. Với sum once, lọc các tập con có tổng target.

Các kiểm chứng bằng brute force giúp phát hiện cả **trùng** lẫn **bỏ sót**. Nhưng chúng chỉ áp dụng hữu hạn trường hợp và **không thay thế chứng minh** về cách loại nhánh tương đương ở mục 4–6.

## 12. Lỗi phổ biến khi khử trùng trong backtracking

1. **Không sắp xếp trước khi so a[i] với a[i−1].** Giá trị bằng nhau có thể không đứng liền nhau.
2. **Bỏ mọi phần tử bằng phần tử trước trên toàn cây.** Làm mất những kết quả hợp lệ như [2,2].
3. **Đổi i>start thành i>0 trong subsets.** Một bản sao ở tầng con bị skip dù cần để tạo đủ số lượng.
4. **Trong permutations chỉ kiểm tra used mà không xét giá trị trùng.** Các bản sao cùng giá trị ở chỉ số khác nhau tạo hoán vị lặp.
5. **Trong permutations bỏ mọi a[i]==a[i−1] không xét !used[i−1].** Có thể không bao giờ sử dụng hết các bản sao bằng nhau.
6. **Trong permutations dùng start=i+1.** Mất các thứ tự mà phần tử chỉ số nhỏ hơn xuất hiện sau.
7. **Không hoàn tác used[i] hoặc path.** Trạng thái nhánh sau bị ảnh hưởng bởi nhánh trước.
8. **Ghi answer.add(path) thay vì ghi bản sao.** Các kết quả dùng chung một danh sách path đang thay đổi.
9. **Nhầm hai kết quả cùng giá trị với hai kết quả cùng vị trí nguồn.** Phải tuân thủ định nghĩa trùng theo đề bài.
10. **Cho phép dùng lại một vị trí khi bài yêu cầu mỗi vị trí một lần.** Với sum once phải đệ quy i+1, không phải i.
11. **Dùng điều kiện break a[i]>remaining khi có số âm.** Quy tắc cắt tỉa có thể sai vì số âm có thể bù phần vượt.
12. **Dùng một Set giá trị toàn cục để chống trùng.** Có thể cấm luôn các bản sao hợp lệ ở tầng sâu.
13. **Không xét mảng rỗng và target=0.** Quy ước có một lựa chọn rỗng cần được xử lý minh bạch.
14. **Quên bảo toàn input khi sort.** Nếu hợp đồng hàm không cho sửa mảng nguồn, phải sao chép.
15. **Nghĩ Set loại trùng sẽ giúp tránh duyệt nhánh trùng.** Nếu chỉ lọc ở lá, chi phí duyệt các nhánh trùng vẫn phát sinh.
16. **Không kiểm thử cả số lượng và nội dung.** Đúng số lượng chưa đủ nếu hai kết quả trùng và một kết quả khác bị bỏ sót.
17. **Không tính chi phí ghi kết quả.** Liệt kê hàng triệu tập con có thể hết RAM dù phần logic quay lui đúng.
18. **Nhầm thứ tự DFS với yêu cầu thứ tự từ điển.** Cần kiểm tra rõ cách đề so sánh dãy nếu yêu cầu thứ tự đầu ra.

## 13. Bài tập tự kiểm tra

**Câu 1.** Vì sao tập con của [2,2] phải có [2,2] mà không có hai kết quả [2]?

**Đáp án:** Đầu vào có hai bản sao nên có thể dùng cả hai ở **hai tầng** để tạo [2,2]. Nhưng chọn bản sao thứ nhất hay thứ hai **tại tầng gốc** đều tạo cùng [2] xét theo giá trị, nên chỉ cần một nhánh.

**Câu 2.** Trong tập con, điều kiện nào tránh kết quả trùng đúng cách?

**Đáp án:** Sau khi sắp, dùng i>start && a[i]==a[i−1] để bỏ **các lựa chọn trùng ở cùng tầng**. Không dùng i>0 vô điều kiện.

**Câu 3.** Trong hoán vị [1,1,2], vì sao có thể chọn số 1 thứ hai sau khi đã chọn số 1 thứ nhất?

**Đáp án:** Vì used[index của bản sao thứ nhất] là true, điều kiện skip có vế !used[i−1] trở thành false. Cả hai bản sao được dùng theo chỉ số tăng trên đường đi và vẫn tạo được [1,1,2].

**Câu 4.** Công thức số lượng tập con phân biệt của đa tập là gì?

**Đáp án:** Tích \(\prod_x(f_x+1)\), vì với giá trị x xuất hiện f_x lần, ta có f_x+1 lựa chọn số bản sao muốn lấy.

**Câu 5.** Có bao nhiêu hoán vị phân biệt của [1,1,1,2,2]?

**Đáp án:** \(5!/(3!\cdot2!)=10\). Việc đổi nhãn ba bản sao 1 hoặc hai bản sao 2 không tạo hoán vị giá trị mới.

**Câu 6.** Tại sao tổ hợp tổng 8 từ [10,1,2,7,6,1,5] được lấy hai số 1 nhưng không được lấy một vị trí hai lần?

**Đáp án:** Có hai vị trí đầu vào mang giá trị 1, nên có thể chọn cả hai. Nhưng đệ quy dùng start=i+1 nên không xét lại chính vị trí vừa chọn.

**Câu 7.** Khi nào được break nếu a[i]>remaining ở bài tổ hợp tổng?

**Đáp án:** Khi a đã sắp tăng và các số dự tuyển **dương**, nên tất cả số sau không nhỏ hơn a[i]. Nếu cho số âm hoặc thay mô hình, phải chứng minh lại điều kiện cắt tỉa.

**Câu 8.** Nếu mọi phần tử đầu vào bằng nhau, thuật toán hoán vị phân biệt sẽ tạo bao nhiêu kết quả?

**Đáp án:** Chỉ một, vì mọi hoán vị theo chỉ số đều tạo cùng một dãy giá trị.

**Câu 9.** Vì sao cần List.copyOf(path) hoặc bản sao tương đương khi ghi một nghiệm?

**Đáp án:** Path là trạng thái dùng chung đang bị thêm/xóa trong các nhánh; không sao chép sẽ làm những kết quả đã lưu thay đổi theo quá trình backtracking.

**Câu 10.** Dùng Set để lọc trùng ở cuối có luôn tốt bằng skip ở lúc lựa chọn không?

**Đáp án:** Không. Set có thể loại trùng trong kết quả cuối nhưng các nhánh trùng đã bị duyệt tốn thời gian, và phải tốn bộ nhớ lưu khóa. Skip đúng ở cùng tầng thường tránh sinh những nhánh tương đương ngay từ đầu.

**Ghi nhớ:** Với đầu vào có phần tử lặp, **sắp xếp rồi khử trùng tại thời điểm chọn nhánh**. Trong tập con/tổ hợp, bỏ **giá trị trùng cùng tầng** bằng i>start và a[i]==a[i−1]. Trong hoán vị, dùng **used** và chỉ bỏ bản sao sau nếu bản sao liền trước cùng giá trị **chưa được chọn**. Mỗi bản sao hợp lệ vẫn phải được phép tham gia ở những tầng sâu hơn, và mỗi kết quả đầu ra phải là **bản sao độc lập** của path.
